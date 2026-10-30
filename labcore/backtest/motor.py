"""Motor de backtesting dirigido por eventos.

Las cuatro decisiones que deciden si el resultado es honesto o ficcion:

  1. La senal se calcula al CIERRE de la barra i y se ejecuta a la APERTURA
     de la barra i+1. Nunca al cierre de i: ese precio no existia cuando
     se tomo la decision.
  2. Si en una misma barra el rango pudo tocar el stop Y el objetivo, se
     asume que toco el STOP. Sin datos intrabarra no se sabe cual ocurrio
     primero, y el supuesto optimista es el que infla los backtests.
  3. El spread se paga en la entrada y en la salida, con el spread de ESA
     barra, no con un promedio.
  4. El motor de riesgo decide el tamano y puede vetar. El backtest usa el
     MISMO motor que usaria en produccion: si no, no esta probando nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..riesgo.modelo import (
    AccountState, InstrumentSpec, ProposedOrder, Quote, RejectCode, Side,
)
from ..riesgo.motor import RiskEngine
from .costos import ModeloCostos
from .mercado import Barra, VentanaMercado


class MotivoCierre(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    SENAL_CONTRARIA = "SENAL_CONTRARIA"
    FIN_DE_DATOS = "FIN_DE_DATOS"


@dataclass
class Senal:
    """Lo que devuelve una estrategia. Deliberadamente NO incluye el tamano:
    el tamano lo decide el motor de riesgo, no la estrategia."""

    side: Side | None                 # None = sin senal
    stop_loss_distancia: float = 0.0  # en unidades de precio, >0
    take_profit_distancia: float = 0.0
    motivo: str = ""


@dataclass
class Operacion:
    symbol: str
    strategy_id: str
    side: Side
    volume: float
    ts_apertura: datetime
    precio_apertura: float            # ya con spread y slippage aplicados
    stop_loss: float
    take_profit: float | None
    riesgo_inicial: float
    ts_cierre: datetime | None = None
    precio_cierre: float | None = None
    motivo_cierre: MotivoCierre | None = None
    costo_comision: float = 0.0
    costo_swap: float = 0.0
    pnl_bruto: float = 0.0
    pnl_neto: float = 0.0

    @property
    def abierta(self) -> bool:
        return self.ts_cierre is None


@dataclass
class ResultadoBacktest:
    operaciones: list[Operacion] = field(default_factory=list)
    curva_equity: list[tuple[datetime, float]] = field(default_factory=list)
    capital_inicial: float = 0.0
    barras_procesadas: int = 0
    senales_generadas: int = 0
    ordenes_evaluadas: int = 0
    ordenes_vetadas: int = 0
    vetos_por_codigo: dict[str, int] = field(default_factory=dict)
    # Senales que ni siquiera llegaron a ser una orden. Sin esto, una
    # estrategia estructuralmente imposible de dimensionar se ve igual
    # que una que no encontro oportunidades: "0 operaciones".
    senales_sin_orden: int = 0
    sin_orden_por_motivo: dict[str, int] = field(default_factory=dict)

    @property
    def equity_final(self) -> float:
        return self.curva_equity[-1][1] if self.curva_equity else self.capital_inicial

    def resumen(self) -> str:
        """Pareja obligatoria: cuantas entraron y cuantas SALIERON."""
        cerradas = [o for o in self.operaciones if not o.abierta]
        linea = (
            f"barras={self.barras_procesadas} senales={self.senales_generadas} "
            f"ordenes_evaluadas={self.ordenes_evaluadas} "
            f"vetadas={self.ordenes_vetadas} "
            f"operaciones_cerradas={len(cerradas)} "
            f"equity={self.equity_final:.2f}"
        )
        if self.senales_generadas > 0 and not self.operaciones:
            linea += ("  ATENCION: hubo senales y NINGUNA operacion se abrio "
                      "- revisa los vetos de riesgo antes de creer este resultado")
        if self.senales_sin_orden:
            linea += f" sin_orden={self.senales_sin_orden}"
            if self.senales_sin_orden == self.senales_generadas:
                linea += ("  ATENCION: NINGUNA senal pudo convertirse en orden. "
                          "Esta estrategia es imposible de dimensionar con el "
                          "limite de riesgo actual, no es que no haya senales")
        if self.barras_procesadas > 0 and self.senales_generadas == 0:
            linea += ("  ATENCION: se procesaron barras y la estrategia no "
                      "genero NINGUNA senal - probablemente esta rota")
        if self.sin_orden_por_motivo:
            linea += " | sin orden: " + "; ".join(
                f"{k} x{v}" for k, v in sorted(
                    self.sin_orden_por_motivo.items(), key=lambda kv: -kv[1])
            )
        if self.vetos_por_codigo:
            linea += " | vetos: " + ", ".join(
                f"{k}={v}" for k, v in sorted(
                    self.vetos_por_codigo.items(), key=lambda kv: -kv[1])
            )
        return linea


class Backtester:
    def __init__(
        self,
        spec: InstrumentSpec,
        costos: ModeloCostos,
        riesgo: RiskEngine,
        capital_inicial: float = 10_000.0,
        barras_minimas: int = 0,
    ) -> None:
        self.spec = spec
        self.costos = costos
        self.riesgo = riesgo
        self.capital_inicial = capital_inicial
        self.barras_minimas = barras_minimas

    # ---------- utilidades de valoracion ----------

    def _valor_por_precio(self, volumen: float, delta_precio: float) -> float:
        """Convierte un movimiento de precio a moneda de la cuenta."""
        return (delta_precio / self.spec.tick_size) * \
            self.spec.tick_value_account_ccy * volumen

    def _volumen_por_riesgo(
        self, equity: float, distancia_stop: float, riesgo_pct: float
    ) -> float:
        """Tamano que arriesga exactamente riesgo_pct, redondeado HACIA ABAJO
        al paso del contrato. Hacia abajo a proposito: redondear hacia arriba
        viola el limite de riesgo."""
        if distancia_stop <= 0:
            return 0.0
        valor_por_lote = self._valor_por_precio(1.0, distancia_stop)
        if valor_por_lote <= 0:
            return 0.0
        bruto = (equity * riesgo_pct) / valor_por_lote
        paso = self.spec.volume_step
        if paso <= 0:
            return bruto
        return (int(bruto / paso)) * paso

    # ---------- bucle principal ----------

    def correr(self, barras: list[Barra], estrategia) -> ResultadoBacktest:
        r = ResultadoBacktest(capital_inicial=self.capital_inicial)
        equity = self.capital_inicial
        peak = equity
        abierta: Operacion | None = None
        pnl_dia = 0.0
        dia_actual = barras[0].ts.date() if barras else None
        sid = getattr(estrategia, "strategy_id", estrategia.__class__.__name__)

        # i recorre las barras CERRADAS. La ejecucion ocurre en i+1, asi que
        # el bucle se detiene una barra antes del final a proposito.
        for i in range(len(barras) - 1):
            cerrada = barras[i]
            siguiente = barras[i + 1]
            r.barras_procesadas += 1

            if cerrada.ts.date() != dia_actual:
                dia_actual = cerrada.ts.date()
                pnl_dia = 0.0

            # 1. Gestionar la posicion abierta contra el RANGO de la barra
            #    siguiente, con el desempate pesimista.
            if abierta is not None:
                cierre = self._revisar_salida(abierta, siguiente)
                if cierre is not None:
                    precio, motivo = cierre
                    self._cerrar(abierta, siguiente.ts, precio, motivo)
                    equity += abierta.pnl_neto
                    pnl_dia += abierta.pnl_neto
                    peak = max(peak, equity)
                    abierta = None

            # 2. Pedir senal con una ventana que no alcanza el futuro.
            if i + 1 < self.barras_minimas:
                r.curva_equity.append((cerrada.ts, equity))
                continue
            ventana = VentanaMercado(barras, i, self.spec.symbol)
            senal: Senal = estrategia.evaluar(ventana)
            if senal.side is not None:
                r.senales_generadas += 1

            # 3. Convertir senal en orden, pasarla por el MISMO motor de riesgo.
            if senal.side is not None and abierta is None:
                orden, motivo_no = self._construir_orden(
                    senal, siguiente, equity, sid, i)
                if orden is None:
                    r.senales_sin_orden += 1
                    r.sin_orden_por_motivo[motivo_no] = \
                        r.sin_orden_por_motivo.get(motivo_no, 0) + 1
                else:
                    cuenta = AccountState(
                        equity=equity, balance=equity,
                        free_margin=equity * 0.9, used_margin=equity * 0.1,
                        peak_equity=peak, realized_pnl_today=pnl_dia,
                        open_positions=(), market_open=True,
                    )
                    spread_ef = self.costos.spread_efectivo(cerrada.spread)
                    # La regla de frescura de cotizacion compara contra el
                    # reloj de pared. En backtest el reloj es la barra, asi
                    # que se pasa "ahora" para que esa UNICA regla no vete
                    # por una razon que no existe en una simulacion. Todas
                    # las demas reglas se aplican igual que en produccion.
                    quote = Quote(
                        symbol=self.spec.symbol,
                        bid=siguiente.open - spread_ef / 2,
                        ask=siguiente.open + spread_ef / 2,
                        ts=_ahora_utc(),
                        median_spread=spread_ef,
                        atr=None,
                    )
                    d = self.riesgo.evaluar(orden, cuenta, self.spec, quote)
                    r.ordenes_evaluadas += 1
                    if d.approved:
                        abierta = self._abrir(orden, siguiente, siguiente.ts)
                        r.operaciones.append(abierta)
                    else:
                        r.ordenes_vetadas += 1
                        for c in d.rejects:
                            r.vetos_por_codigo[c.value] = \
                                r.vetos_por_codigo.get(c.value, 0) + 1

            r.curva_equity.append((cerrada.ts, equity))

        # 4. Lo que quede abierto se cierra al ultimo precio disponible. No se
        #    deja "flotando en ganancia": eso es una forma de look-ahead.
        if abierta is not None and barras:
            ult = barras[-1]
            precio = self._precio_salida(abierta, ult.close, ult)
            self._cerrar(abierta, ult.ts, precio, MotivoCierre.FIN_DE_DATOS)
            equity += abierta.pnl_neto
            r.curva_equity.append((ult.ts, equity))

        return r

    # ---------- piezas ----------

    def _construir_orden(
        self, senal: Senal, ejecucion: Barra, equity: float,
        sid: str, i: int,
    ) -> tuple[ProposedOrder | None, str]:
        if senal.stop_loss_distancia <= 0:
            return None, "SIN_DISTANCIA_DE_STOP"
        es_compra = senal.side is Side.BUY
        spread_ef = self.costos.spread_efectivo(ejecucion.spread)
        precio = ejecucion.open + (spread_ef / 2 if es_compra else -spread_ef / 2)
        precio += self.costos.slippage_precio(self.spec.tick_size, es_compra,
                                              ejecucion.open)
        vol = self._volumen_por_riesgo(
            equity, senal.stop_loss_distancia,
            self.riesgo.limits.per_trade_risk_pct)
        if vol < self.spec.min_volume:
            # Caso real y silencioso: un stop muy ancho hace que el tamano
            # que cabe en el tope de riesgo quede bajo el minimo del
            # contrato. La estrategia es imposible de operar con este
            # limite de riesgo, no es que no haya oportunidades.
            return None, (
                f"VOLUMEN_BAJO_EL_MINIMO (calculado {vol:.5f} < "
                f"{self.spec.min_volume} del contrato; stop de "
                f"{senal.stop_loss_distancia:.5f} es demasiado ancho para "
                f"arriesgar solo {self.riesgo.limits.per_trade_risk_pct:.2%})")
        sl = (precio - senal.stop_loss_distancia if es_compra
              else precio + senal.stop_loss_distancia)
        tp = None
        if senal.take_profit_distancia > 0:
            tp = (precio + senal.take_profit_distancia if es_compra
                  else precio - senal.take_profit_distancia)
        return ProposedOrder(
            client_order_id=f"{sid}-{i}", symbol=self.spec.symbol,
            side=senal.side, volume=round(vol, 8), reference_price=precio,
            stop_loss=sl, take_profit=tp, strategy_id=sid,
        ), ""

    def _abrir(self, o: ProposedOrder, b: Barra, ts: datetime) -> Operacion:
        return Operacion(
            symbol=o.symbol, strategy_id=o.strategy_id, side=o.side,
            volume=o.volume, ts_apertura=ts, precio_apertura=o.reference_price,
            stop_loss=o.stop_loss, take_profit=o.take_profit,
            riesgo_inicial=self._valor_por_precio(
                o.volume, abs(o.reference_price - o.stop_loss)),
            costo_comision=self.costos.comision(o.volume),
        )

    def _precio_salida(self, op: Operacion, nivel: float, b: Barra) -> float:
        """Precio al que REALMENTE se cierra, no el nivel que se toco.

        Una posicion larga entro al ask y sale al bid: el spread se paga
        en los DOS lados. Cobrarlo solo en la entrada hace que el spread
        se cancele contra un stop/objetivo fijado relativo a la entrada,
        y produce un backtest que no empeora al ensanchar el spread.
        El slippage, igual que en la entrada, va siempre en contra.
        """
        largo = op.side is Side.BUY
        medio = self.costos.spread_efectivo(b.spread) / 2.0
        desliz = abs(self.costos.slippage_precio(self.spec.tick_size, True, nivel))
        # salir de un largo es VENDER: peor precio es mas abajo
        return nivel - medio - desliz if largo else nivel + medio + desliz

    def _revisar_salida(
        self, op: Operacion, b: Barra
    ) -> tuple[float, MotivoCierre] | None:
        """DESEMPATE PESIMISTA: si el rango pudo tocar stop y objetivo, gana
        el stop. Sin datos intrabarra no se sabe el orden, y el supuesto
        optimista es el que produce backtests mentirosos."""
        largo = op.side is Side.BUY
        toco_stop = b.low <= op.stop_loss if largo else b.high >= op.stop_loss
        toco_tp = (
            op.take_profit is not None
            and (b.high >= op.take_profit if largo else b.low <= op.take_profit)
        )
        if toco_stop:
            return self._precio_salida(op, op.stop_loss, b), MotivoCierre.STOP_LOSS
        if toco_tp:
            return (self._precio_salida(op, op.take_profit, b),  # type: ignore[arg-type]
                    MotivoCierre.TAKE_PROFIT)
        return None

    def _cerrar(
        self, op: Operacion, ts: datetime, precio: float, motivo: MotivoCierre
    ) -> None:
        op.ts_cierre = ts
        op.precio_cierre = precio
        op.motivo_cierre = motivo
        delta = (precio - op.precio_apertura) if op.side is Side.BUY \
            else (op.precio_apertura - precio)
        op.pnl_bruto = self._valor_por_precio(op.volume, delta)
        op.costo_comision += self.costos.comision(op.volume)   # el lado de salida
        op.costo_swap = self.costos.swap(
            op.volume, op.side is Side.BUY, op.ts_apertura, ts)
        op.pnl_neto = op.pnl_bruto - op.costo_comision + op.costo_swap


def _ahora_utc() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc)
