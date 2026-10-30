"""Simulador de CARTERA: varios instrumentos y varias posiciones a la vez,
compartiendo un solo capital, con tope de apalancamiento.

Es distinto del backtester de un instrumento: aqui el riesgo es COMPARTIDO.
La pérdida diaria, el drawdown y el apalancamiento se cuentan sobre el
patrimonio total, no por instrumento. Eso cambia los resultados: una
estrategia que se ve bien aislada puede quedar vetada porque otra ya tomó
el cupo de riesgo.

Las tres cosas que esto respeta y una simulacion por instrumento no puede:
  1. El apalancamiento es un tope de la CARTERA, no de cada operacion.
  2. La perdida diaria del 2% la puede gatillar cualquier instrumento y
     corta para TODOS.
  3. El drawdown del 10% suspende la cartera completa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..riesgo.modelo import (
    AccountState, InstrumentSpec, OpenPosition, ProposedOrder, Quote,
    RejectCode, RiskLimits, Side,
)
from ..riesgo.motor import RiskEngine
from .costos import ModeloCostos
from .mercado import Barra, VentanaMercado
from .motor import MotivoCierre, Operacion


@dataclass
class ResultadoCartera:
    capital_inicial: float
    equity: float
    peak_equity: float
    curva: list[tuple[datetime, float]] = field(default_factory=list)
    cerradas: list[Operacion] = field(default_factory=list)
    senales: int = 0
    ordenes_evaluadas: int = 0
    vetadas: int = 0
    vetos: dict[str, int] = field(default_factory=dict)
    sin_dimensionar: int = 0
    max_simultaneas: int = 0
    max_apalancamiento_visto: float = 0.0

    @property
    def retorno_pct(self) -> float:
        return (self.equity - self.capital_inicial) / self.capital_inicial

    @property
    def drawdown(self) -> float:
        picos, peor, pico = 0.0, 0.0, self.capital_inicial
        for _, e in self.curva:
            pico = max(pico, e)
            peor = max(peor, (pico - e) / pico if pico > 0 else 0.0)
        return peor

    def resumen(self) -> str:
        n = len(self.cerradas)
        gan = [o for o in self.cerradas if o.pnl_neto > 0]
        l = [
            f"capital US$ {self.capital_inicial:,.0f} -> "
            f"US$ {self.equity:,.2f}  ({self.retorno_pct:+.2%})",
            f"drawdown maximo {self.drawdown:.2%}   "
            f"apalancamiento maximo visto {self.max_apalancamiento_visto:.2f}x",
            f"senales={self.senales} evaluadas={self.ordenes_evaluadas} "
            f"vetadas={self.vetadas} sin_dimensionar={self.sin_dimensionar}",
            f"operaciones cerradas={n}  simultaneas maximo={self.max_simultaneas}",
        ]
        if n:
            l.append(f"aciertos {len(gan)}/{n} ({len(gan)/n:.1%})")
        if self.senales and not n:
            l.append("ATENCION: hubo senales y NINGUNA operacion se cerro")
        if self.vetos:
            l.append("vetos: " + ", ".join(
                f"{k}={v}" for k, v in sorted(self.vetos.items(),
                                              key=lambda kv: -kv[1])))
        return "\n".join(l)


class SimuladorCartera:
    def __init__(self, costos: ModeloCostos, limites: RiskLimits,
                 riesgo: RiskEngine, capital_inicial: float = 1000.0) -> None:
        self.costos = costos
        self.limites = limites
        self.riesgo = riesgo
        self.capital_inicial = capital_inicial

    def _valor(self, spec: InstrumentSpec, vol: float, delta: float) -> float:
        return (delta / spec.tick_size) * spec.tick_value_account_ccy * vol

    def _volumen(self, spec: InstrumentSpec, equity: float,
                 dist: float) -> float:
        """Tamano por riesgo, redondeado HACIA ABAJO al paso del contrato."""
        if dist <= 0:
            return 0.0
        por_lote = self._valor(spec, 1.0, dist)
        if por_lote <= 0:
            return 0.0
        bruto = (equity * self.limites.per_trade_risk_pct) / por_lote
        paso = spec.volume_step
        return (int(bruto / paso)) * paso if paso > 0 else bruto

    def correr(self, mercados: dict[str, tuple[list[Barra], InstrumentSpec]],
               fabrica_estrategias) -> ResultadoCartera:
        """mercados: nombre -> (barras, spec). Las barras se alinean por ts."""
        # Indice temporal comun: solo los instantes que existen en algun
        # instrumento, en orden. Cada instrumento se consulta por su propio
        # indice para no inventar barras que no existen.
        por_ts: dict[datetime, list[str]] = {}
        idx: dict[str, dict[datetime, int]] = {}
        for nombre, (bs, _) in mercados.items():
            idx[nombre] = {b.ts: i for i, b in enumerate(bs)}
            for b in bs:
                por_ts.setdefault(b.ts, []).append(nombre)
        tiempos = sorted(por_ts)

        r = ResultadoCartera(capital_inicial=self.capital_inicial,
                             equity=self.capital_inicial,
                             peak_equity=self.capital_inicial)
        ests = {n: fabrica_estrategias() for n in mercados}
        abiertas: list[tuple[Operacion, InstrumentSpec]] = []
        pnl_dia, dia = 0.0, tiempos[0].date() if tiempos else None
        suspendida = False

        for k, ts in enumerate(tiempos[:-1]):
            if dia is not None and ts.date() != dia:
                dia, pnl_dia = ts.date(), 0.0

            # --- 1. gestionar lo abierto con la barra SIGUIENTE de cada uno ---
            for op, spec in list(abiertas):
                bs, _ = mercados[op.symbol]
                i = idx[op.symbol].get(ts)
                if i is None or i + 1 >= len(bs):
                    continue
                sig = bs[i + 1]
                largo = op.side is Side.BUY
                toco_stop = (sig.low <= op.stop_loss if largo
                             else sig.high >= op.stop_loss)
                toco_tp = (op.take_profit is not None and
                           (sig.high >= op.take_profit if largo
                            else sig.low <= op.take_profit))
                if not (toco_stop or toco_tp):
                    continue
                nivel = op.stop_loss if toco_stop else op.take_profit
                motivo = (MotivoCierre.STOP_LOSS if toco_stop
                          else MotivoCierre.TAKE_PROFIT)
                medio = self.costos.spread_efectivo(sig.spread) / 2
                desliz = abs(self.costos.slippage_precio(spec.tick_size, True, nivel))
                precio = (nivel - medio - desliz if largo
                          else nivel + medio + desliz)
                delta = (precio - op.precio_apertura if largo
                         else op.precio_apertura - precio)
                op.pnl_bruto = self._valor(spec, op.volume, delta)
                op.costo_comision += self.costos.comision(op.volume)
                op.costo_swap = self.costos.swap(
                    op.volume, largo, op.ts_apertura, sig.ts)
                op.pnl_neto = op.pnl_bruto - op.costo_comision + op.costo_swap
                op.ts_cierre, op.precio_cierre, op.motivo_cierre = \
                    sig.ts, precio, motivo
                r.equity += op.pnl_neto
                pnl_dia += op.pnl_neto
                r.peak_equity = max(r.peak_equity, r.equity)
                r.cerradas.append(op)
                abiertas.remove((op, spec))

            r.curva.append((ts, r.equity))
            if r.equity <= 0:
                suspendida = True
            if suspendida:
                continue

            # --- 2. senales de cada instrumento con barra en este instante ---
            for nombre in por_ts[ts]:
                bs, spec = mercados[nombre]
                i = idx[nombre][ts]
                if i + 1 >= len(bs):
                    continue
                if any(o.symbol == nombre for o, _ in abiertas):
                    continue
                v = VentanaMercado(bs, i, nombre)
                senal = None
                for e in ests[nombre]:
                    if v.listas < getattr(e, "barras_minimas", 0):
                        continue
                    s = e.evaluar(v)
                    if s.side is not None:
                        senal, elegida = s, e
                        break
                if senal is None:
                    continue
                r.senales += 1
                sig = bs[i + 1]
                es_compra = senal.side is Side.BUY
                medio = self.costos.spread_efectivo(sig.spread) / 2
                precio = sig.open + (medio if es_compra else -medio)
                precio += self.costos.slippage_precio(spec.tick_size, es_compra, sig.open)
                vol = self._volumen(spec, r.equity, senal.stop_loss_distancia)
                if vol < spec.min_volume:
                    r.sin_dimensionar += 1
                    continue
                sl = (precio - senal.stop_loss_distancia if es_compra
                      else precio + senal.stop_loss_distancia)
                tp = None
                if senal.take_profit_distancia > 0:
                    tp = (precio + senal.take_profit_distancia if es_compra
                          else precio - senal.take_profit_distancia)
                orden = ProposedOrder(
                    client_order_id=f"{nombre}-{k}", symbol=nombre,
                    side=senal.side, volume=round(vol, 8),
                    reference_price=precio, stop_loss=sl, take_profit=tp,
                    strategy_id=getattr(elegida, "strategy_id", "?"))

                # Estado COMPARTIDO: lo abierto de todos los instrumentos.
                pos = tuple(
                    OpenPosition(o.symbol, o.side, o.volume, o.precio_apertura,
                                 o.stop_loss, sp.correlation_group)
                    for o, sp in abiertas)
                cuenta = AccountState(
                    equity=r.equity, balance=r.equity,
                    free_margin=r.equity * 0.9, used_margin=r.equity * 0.1,
                    peak_equity=r.peak_equity, realized_pnl_today=pnl_dia,
                    open_positions=pos, market_open=True)
                from datetime import timezone
                q = Quote(nombre, precio - medio, precio + medio,
                          datetime.now(timezone.utc), medio * 2, None)
                d = self.riesgo.evaluar(orden, cuenta, spec, q)
                r.ordenes_evaluadas += 1
                lev = d.detail.get("apalancamiento_resultante")
                if isinstance(lev, (int, float)):
                    r.max_apalancamiento_visto = max(
                        r.max_apalancamiento_visto, float(lev))
                if not d.approved:
                    r.vetadas += 1
                    for c in d.rejects:
                        r.vetos[c.value] = r.vetos.get(c.value, 0) + 1
                    if RejectCode.MAX_DRAWDOWN_HIT in d.rejects:
                        suspendida = True
                    continue
                op = Operacion(
                    symbol=nombre, strategy_id=orden.strategy_id,
                    side=orden.side, volume=orden.volume, ts_apertura=sig.ts,
                    precio_apertura=precio, stop_loss=sl, take_profit=tp,
                    riesgo_inicial=self._valor(spec, orden.volume,
                                               abs(precio - sl)),
                    costo_comision=self.costos.comision(orden.volume))
                abiertas.append((op, spec))
                r.max_simultaneas = max(r.max_simultaneas, len(abiertas))

        return r
