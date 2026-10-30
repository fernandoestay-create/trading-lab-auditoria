"""Operador de papel: una pasada. Lo llama el cron cada 15 minutos.

Opera FICTICIAMENTE sobre precios REALES de cripto (24/7, barras de 15
minutos). No toca Exness, no envia ninguna orden, no mueve un peso.

Reutiliza las MISMAS piezas que el backtester y el mismo motor de riesgo:
si usara reglas distintas, el historial de papel no probaria nada sobre lo
que haria en produccion.

Uso:
    lab python scripts/operar_papel.py
    lab python scripts/operar_papel.py --capital 1000 --reiniciar
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.simplefilter("ignore")
import logging
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
for _m in ("py.warnings", "urllib3", "peewee"):
    logging.getLogger(_m).setLevel(logging.CRITICAL)

from labcore.backtest import Backtester, ModeloCostos
from labcore.backtest.mercado import Barra, VentanaMercado
from labcore.backtest.motor import MotivoCierre
from labcore.estrategias import CruceMedias, RupturaDeRango
from labcore.costos_medidos import cargar as cargar_spreads, para as spread_para
from labcore.horarios import debe_cerrar_todo, puede_abrir, resumen as resumen_horario
from labcore.telemetria import Medicion, anotar as anotar_tel, antiguedad_del_dato, medir
from labcore.papel import Cartera, PosicionPapel, TratoPapel
from labcore.riesgo import (
    AccountState, InstrumentSpec, KillSwitch, RiskEngine, RiskLimits, Side,
)

RUTA = Path.home() / "trading-lab" / "papel"
LOG = Path.home() / "logs" / "trading-lab-papel.log"

# Cripto: opera 24/7, asi que un "dia" de papel es un dia completo de verdad.
# Los spreads son MODELADOS (referencia publica), no medidos en la cuenta.
# UNIVERSO AMPLIO. Aprendido de los escaneres comerciales (Trade Ideas,
# Scanz): escanean cientos de instrumentos, no ocho.
#
# No es por avaricia: es la UNICA palanca que aumenta las observaciones
# independientes. Con un Sharpe de 0,5 hacen falta ~13 anos de serie por
# estrategia; 40 instrumentos acumulan en un mes lo que uno acumula en
# cuarenta. Y hacia adelante no es data snooping: las reglas ya estan
# fijas y estos precios no existian cuando se eligieron.
#
# El grupo de correlacion importa: todas las criptos se mueven juntas, asi
# que el motor de riesgo las trata como UN riesgo, no como diversificacion.
def _c(sim, spread):   # cripto, 24/7
    return dict(simbolo=sim, spread=spread, grupo="CRYPTO")
def _a(sim, spread):   # accion o ETF de EEUU, horario de bolsa
    return dict(simbolo=sim, spread=spread, grupo="EQUITY_US")

UNIVERSO = {
    # --- cripto (24/7, donde US$1.000 alcanza a dimensionar) ---
    "BTCUSD":  _c("BTC-USD",  25.0),   "ETHUSD":  _c("ETH-USD",  1.50),
    "SOLUSD":  _c("SOL-USD",  0.08),   "XRPUSD":  _c("XRP-USD",  0.0015),
    "DOGEUSD": _c("DOGE-USD", 0.0004), "ADAUSD":  _c("ADA-USD",  0.0008),
    "LTCUSD":  _c("LTC-USD",  0.12),   "LINKUSD": _c("LINK-USD", 0.01),
    "AVAXUSD": _c("AVAX-USD", 0.02),   "DOTUSD":  _c("DOT-USD",  0.004),
    "MATICUSD":_c("MATIC-USD",0.0006), "ATOMUSD": _c("ATOM-USD", 0.004),
    "UNIUSD":  _c("UNI-USD",  0.008),  "AAVEUSD": _c("AAVE-USD", 0.30),
    "NEARUSD": _c("NEAR-USD", 0.003),  "FILUSD":  _c("FIL-USD",  0.004),
    "ETCUSD":  _c("ETC-USD",  0.02),   "XLMUSD":  _c("XLM-USD",  0.0003),
    "BCHUSD":  _c("BCH-USD",  0.50),   "ALGOUSD": _c("ALGO-USD", 0.0004),
    # --- ETFs e indices (muy liquidos, spread chico) ---
    "SPY": _a("SPY", 0.02),  "QQQ": _a("QQQ", 0.02),
    "IWM": _a("IWM", 0.02),  "DIA": _a("DIA", 0.03),
    "GLD": _a("GLD", 0.02),  "SLV": _a("SLV", 0.01),
    "USO": _a("USO", 0.02),  "TLT": _a("TLT", 0.02),
    "XLE": _a("XLE", 0.02),  "XLF": _a("XLF", 0.01),
    "EEM": _a("EEM", 0.01),  "FXI": _a("FXI", 0.02),
    # --- acciones liquidas ---
    "AAPL": _a("AAPL", 0.02), "MSFT": _a("MSFT", 0.03),
    "NVDA": _a("NVDA", 0.03), "AMZN": _a("AMZN", 0.03),
    "GOOGL":_a("GOOGL",0.02), "META": _a("META", 0.05),
    "TSLA": _a("TSLA", 0.03), "AMD":  _a("AMD",  0.02),
}
INTERVALO = "5m"
PERIODO = "5d"


def registrar(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"[{datetime.now(timezone.utc):%F %T}] {msg}\n")


def bajar(simbolo: str, spread: float) -> list[Barra]:
    import yfinance as yf
    d = yf.Ticker(simbolo).history(period=PERIODO, interval=INTERVALO)
    if d.empty:
        return []
    d = d.tz_convert("UTC") if d.index.tz else d.tz_localize("UTC")
    d = d[~d.index.duplicated(keep="first")].sort_index()
    cols = ["Open", "High", "Low", "Close"]
    d = d[~(d[cols].isna().any(axis=1) | (d["High"] < d["Low"])
            | (d[cols] <= 0).any(axis=1))]
    return [
        Barra(ts=ix.to_pydatetime(), open=float(r.Open), high=float(r.High),
              low=float(r.Low), close=float(r.Close),
              volume=float(r.Volume or 0), spread=spread)
        for ix, r in d.iterrows()
    ]


def valorizar_abiertas(c, precios: dict[str, float],
                       spreads: dict[str, tuple[float, str]] | None = None) -> float:
    """P&L de lo abierto al ultimo precio, descontando el medio spread de
    salida. Sin esto el sistema queda ciego justo cuando mas importa."""
    total = 0.0
    for p in c.abiertas:
        px = precios.get(p.instrumento)
        if px is None:
            continue
        medio = ((spreads or {}).get(p.instrumento, (UNIVERSO[p.instrumento]["spread"], ""))[0]) / 2
        if p.side == "BUY":
            total += ((px - medio) - p.precio_entrada) * p.volume
        else:
            total += (p.precio_entrada - (px + medio)) * p.volume
    return total


def spec_de(nombre: str, grupo: str) -> InstrumentSpec:
    # 1 "lote" = 1 unidad del activo; tick 0,01 y valor del tick 0,01.
    return InstrumentSpec(
        symbol=nombre, contract_size=1, tick_size=0.01,
        tick_value_account_ccy=0.01, min_volume=0.01, volume_step=0.01,
        margin_rate=0.01, correlation_group=grupo)


def main() -> int:
    ap = argparse.ArgumentParser()
    # US$500 es el saldo REAL de la cuenta demo (leido de la API el
    # 2026-10-30). Simular con 1.000 cuando la cuenta tiene 500 hace que
    # el forward test mida algo que no podria pasar.
    ap.add_argument("--capital", type=float, default=500.0)
    ap.add_argument("--reiniciar", action="store_true")
    args = ap.parse_args()

    if args.reiniciar and (RUTA / "cartera.json").exists():
        (RUTA / "cartera.json").unlink()
        registrar("cartera reiniciada por peticion explicita")

    c = Cartera.cargar(RUTA, capital_inicial=args.capital)
    ks = KillSwitch()
    if ks.activo():
        registrar(f"KILL SWITCH ACTIVO: {ks.motivo()}. No se opera.")
        print(f"KILL SWITCH ACTIVO: {ks.motivo()}")
        return 0

    # Limites pedidos por Fernando: apalancamiento 5x y varias posiciones
    # simultaneas. El riesgo por operacion se mantiene en 0,5% y la perdida
    # diaria en 2%: son lo que separa una racha mala de una cuenta vacia.
    limites = RiskLimits(
        apalancamiento_maximo=5.0,
        max_open_positions=6,
        per_trade_risk_pct=0.005,
        daily_loss_limit_pct=0.02,
        max_drawdown_pct=0.10,
    )
    riesgo = RiskEngine(limites, ks)
    costos = ModeloCostos(comision_por_lote_por_lado=0.0, slippage_ticks=1.0)
    hoy = datetime.now(timezone.utc).strftime("%F")
    eventos: list[str] = []
    mirados = 0

    # Primera vuelta: bajar todo y quedarse con el ultimo precio de cada
    # uno, para poder valorizar lo abierto ANTES de decidir nada.
    # Tabla de spreads MEDIDOS de la cuenta. Se carga una vez por pasada.
    # Los valores del UNIVERSO eran estimaciones mias; estos salen del
    # muestreo cada 10 min contra la API, con su margen por incertidumbre.
    tabla_spreads = cargar_spreads()
    mercado: dict[str, list] = {}
    precios: dict[str, float] = {}
    spreads_usados: dict[str, tuple[float, str]] = {}
    import time as _t
    t0_pasada = _t.perf_counter()
    for nombre, cfg in UNIVERSO.items():
        _t0 = _t.perf_counter()
        try:
            bs = bajar(cfg["simbolo"], cfg["spread"])
        except Exception as e:
            anotar_tel(Medicion(__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc).isoformat(),
                "error", f"bajar:{nombre}",
                ms=(_t.perf_counter()-_t0)*1000,
                detalle={"excepcion": type(e).__name__, "mensaje": str(e)[:160]}))
            continue
        anotar_tel(Medicion(__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
            "latencia_api", f"datos:{cfg['grupo']}",
            ms=(_t.perf_counter()-_t0)*1000, detalle={"instrumento": nombre}))
        if len(bs) < 60:
            continue
        # ANTIGUEDAD: cuanto tiempo paso desde el cierre de la ultima vela.
        # Es la ventana de ceguera con la que decidimos.
        antiguedad_del_dato(bs[-1].ts, nombre)
        # Reconstruir las barras con el spread medido al precio de cada una.
        sp_monto, sp_origen = spread_para(nombre, bs[-1].close, tabla_spreads)
        frac = sp_monto / bs[-1].close if bs[-1].close else 0.0
        bs = [type(b)(b.ts, b.open, b.high, b.low, b.close, b.volume,
                      b.close * frac) for b in bs]
        mercado[nombre] = bs
        precios[nombre] = bs[-1].close
        spreads_usados[nombre] = (sp_monto, sp_origen)

    no_realizado = valorizar_abiertas(c, precios, spreads_usados)
    equity_efectivo = c.equity + no_realizado
    pnl_realizado_hoy = sum(
        tr.pnl_neto for tr in c.cerradas if tr.cerrada_en[:10] == hoy)
    perdida_hoy = pnl_realizado_hoy + no_realizado
    registrar(f"valorizacion: no_realizado={no_realizado:.2f} "
              f"equity_efectivo={equity_efectivo:.2f} "
              f"perdida_hoy={perdida_hoy:.2f}")

    # --- REGLA DE INTRADIA: ninguna posicion pasa de un dia para otro ---
    # Se revisa ANTES del corte por perdida: aunque la cuenta vaya bien,
    # si llego la hora hay que cerrar. Asi el swap NUNCA se cobra y la
    # ambiguedad de 100x en swap_long deja de importar.
    a_cerrar = []
    for pos in c.abiertas:
        grupo = UNIVERSO.get(pos.instrumento, {}).get("grupo", "CRYPTO")
        hay_que, por_que = debe_cerrar_todo(grupo)
        if hay_que:
            a_cerrar.append((pos, por_que))
    if a_cerrar:
        registrar(f"INTRADIA: cerrando {len(a_cerrar)} posicion(es) por horario")
        evs = []
        for pos, por_que in a_cerrar:
            px = precios.get(pos.instrumento)
            if px is None:
                registrar(f"  {pos.instrumento}: sin precio, NO pude cerrar "
                          f"-- queda abierta y hay que revisarla")
                continue
            medio = UNIVERSO[pos.instrumento]["spread"] / 2
            salida = px - medio if pos.side == "BUY" else px + medio
            delta = (salida - pos.precio_entrada if pos.side == "BUY"
                     else pos.precio_entrada - salida)
            pnl = delta * pos.volume
            c.cerradas.append(TratoPapel(
                instrumento=pos.instrumento, estrategia=pos.estrategia,
                side=pos.side, volume=pos.volume,
                precio_entrada=pos.precio_entrada, precio_salida=salida,
                stop_loss=pos.stop_loss, abierta_en=pos.abierta_en,
                cerrada_en=datetime.now(timezone.utc).isoformat(),
                razon_apertura=pos.razon_apertura,
                razon_cierre="CIERRE_INTRADIA",
                riesgo_inicial=pos.riesgo_inicial, pnl_bruto=pnl,
                costo_comision=0.0, costo_swap=0.0, pnl_neto=pnl,
                resultado_r=pnl/pos.riesgo_inicial if pos.riesgo_inicial else 0.0))
            c.abiertas.remove(pos)
            c.equity += pnl
            c.peak_equity = max(c.peak_equity, c.equity)
            evs.append(f"CIERRA {pos.instrumento} {pos.side} por INTRADIA "
                       f"({por_que}): US$ {pnl:+.2f}")
        c.guardar(RUTA)
        for ev in evs:
            print(ev)
        eventos.extend(evs)
        no_realizado = valorizar_abiertas(c, precios, spreads_usados)
        equity_efectivo = c.equity + no_realizado

    # CORTE DURO antes de cualquier decision: si la perdida del dia
    # (cerrada + abierta) paso el tope, se cierra TODO a precio de mercado.
    # Negarse a abrir mas no sirve si lo abierto sigue sangrando.
    tope_dia = c.capital_inicial * 0.02
    if perdida_hoy <= -tope_dia and c.abiertas:
        registrar(f"CORTE DIARIO: perdida {perdida_hoy:.2f} supera "
                  f"el tope de {tope_dia:.2f}. Cerrando TODO.")
        eventos_corte = []
        for pos in list(c.abiertas):
            px = precios.get(pos.instrumento)
            if px is None:
                continue
            medio = UNIVERSO[pos.instrumento]["spread"] / 2
            salida = px - medio if pos.side == "BUY" else px + medio
            delta = (salida - pos.precio_entrada if pos.side == "BUY"
                     else pos.precio_entrada - salida)
            pnl = delta * pos.volume
            c.cerradas.append(TratoPapel(
                instrumento=pos.instrumento, estrategia=pos.estrategia,
                side=pos.side, volume=pos.volume,
                precio_entrada=pos.precio_entrada, precio_salida=salida,
                stop_loss=pos.stop_loss, abierta_en=pos.abierta_en,
                cerrada_en=datetime.now(timezone.utc).isoformat(),
                razon_apertura=pos.razon_apertura,
                razon_cierre="CORTE_PERDIDA_DIARIA",
                riesgo_inicial=pos.riesgo_inicial, pnl_bruto=pnl,
                costo_comision=0.0, costo_swap=0.0, pnl_neto=pnl,
                resultado_r=pnl / pos.riesgo_inicial if pos.riesgo_inicial else 0.0))
            c.abiertas.remove(pos)
            c.equity += pnl
            eventos_corte.append(
                f"CIERRA {pos.instrumento} {pos.side} por CORTE DIARIO: "
                f"US$ {pnl:+.2f}")
        c.guardar(RUTA)
        for ev in eventos_corte:
            print(ev)
        print()
        print(f"CORTE DE PERDIDA DIARIA: se cerro todo. "
              f"perdida del dia US$ {perdida_hoy:+.2f} "
              f"(tope US$ {-tope_dia:.2f})")
        print(c.resumen())
        return 0

    # --- recolectar TODOS los candidatos antes de abrir ninguno ---
    # Aprendido de los escaneres: con 40 instrumentos pueden aparecer 10
    # senales a la vez y el cupo de riesgo alcanza para 6. Tomar "la
    # primera que aparezca" es dejar que el orden del diccionario decida
    # donde va tu plata. Se rankean y se abren los mejores.
    candidatos = []
    for nombre, barras in mercado.items():
        cfg = UNIVERSO[nombre]
        mirados += 1
        spec = spec_de(nombre, cfg["grupo"])
        bt = Backtester(spec, costos, riesgo, capital_inicial=equity_efectivo)
        ultima, previa = barras[-1], barras[-2]

        # --- 1. gestionar lo abierto contra la ultima barra ---
        for pos in list(c.abiertas):
            if pos.instrumento != nombre:
                continue
            from labcore.backtest.motor import Operacion
            op = Operacion(
                symbol=pos.instrumento, strategy_id=pos.estrategia,
                side=Side(pos.side), volume=pos.volume,
                ts_apertura=datetime.fromisoformat(pos.abierta_en),
                precio_apertura=pos.precio_entrada, stop_loss=pos.stop_loss,
                take_profit=pos.take_profit, riesgo_inicial=pos.riesgo_inicial)
            salida = bt._revisar_salida(op, ultima)
            if salida is None:
                continue
            precio, motivo = salida
            bt._cerrar(op, ultima.ts, precio, motivo)
            r = op.pnl_neto / pos.riesgo_inicial if pos.riesgo_inicial else 0.0
            c.cerradas.append(TratoPapel(
                instrumento=nombre, estrategia=pos.estrategia, side=pos.side,
                volume=pos.volume, precio_entrada=pos.precio_entrada,
                precio_salida=precio, stop_loss=pos.stop_loss,
                abierta_en=pos.abierta_en, cerrada_en=ultima.ts.isoformat(),
                razon_apertura=pos.razon_apertura,
                razon_cierre=motivo.value, riesgo_inicial=pos.riesgo_inicial,
                pnl_bruto=op.pnl_bruto, costo_comision=op.costo_comision,
                costo_swap=op.costo_swap, pnl_neto=op.pnl_neto,
                resultado_r=r))
            c.abiertas.remove(pos)
            c.equity += op.pnl_neto
            c.peak_equity = max(c.peak_equity, c.equity)
            signo = "GANA" if op.pnl_neto > 0 else "PIERDE"
            eventos.append(
                f"CIERRA {nombre} {pos.side} por {motivo.value}: "
                f"{signo} US$ {op.pnl_neto:+.2f} ({r:+.2f}R)")

        # --- 2. buscar senal nueva ---
        # Solo se salta si YA hay posicion en ESTE instrumento. En otros,
        # se puede abrir en paralelo: el tope lo pone el motor de riesgo.
        if any(p.instrumento == nombre for p in c.abiertas):
            continue
        # Varias estrategias a la vez. Operar hacia ADELANTE no es data
        # snooping: estos precios no existian cuando se eligieron las reglas.
        # La primera que senale se lleva el cupo del instrumento.
        # REGLA: nada con la bolsa cerrada. Operar un CFD de accion fuera
        # de hora significa spread ancho y mala ejecucion, cuando se puede.
        se_puede, motivo_horario = puede_abrir(cfg["grupo"])
        if not se_puede:
            continue

        senal = None
        for e in (RupturaDeRango(20), RupturaDeRango(55), CruceMedias(20, 50)):
            if len(barras) - 1 < e.barras_minimas:
                continue
            v = VentanaMercado(barras, len(barras) - 2, nombre)
            s = e.evaluar(v)
            if s.side is not None:
                senal, elegida = s, e
                break
        if senal is None:
            continue
        c.senales_vistas += 1
        # Fuerza de la senal: cuanto se movio la barra de ruptura en
        # relacion a su propio stop. Mas alto = ruptura mas decidida.
        # Es un criterio de DESEMPATE, no una prediccion.
        ult = barras[-1]
        fuerza = (abs(ult.close - ult.open) / senal.stop_loss_distancia
                  if senal.stop_loss_distancia > 0 else 0.0)
        candidatos.append((fuerza, nombre, barras, elegida, senal))
        continue

    # Los mejores primero. El motor de riesgo sigue teniendo la ultima
    # palabra: puede vetar a cualquiera por apalancamiento o correlacion.
    candidatos.sort(key=lambda x: -x[0])
    if candidatos:
        registrar(f"candidatos: {len(candidatos)} -> " + ", ".join(
            f"{n}({f:.2f})" for f, n, *_ in candidatos[:8]))

    for fuerza, nombre, barras, e, senal in candidatos:
        cfg = UNIVERSO[nombre]
        spec = spec_de(nombre, cfg["grupo"])
        bt = Backtester(spec, costos, riesgo, capital_inicial=equity_efectivo)
        ultima = barras[-1]

        _t_senal = _t.perf_counter()
        orden, motivo_no = bt._construir_orden(
            senal, ultima, equity_efectivo, e.strategy_id, len(barras))
        if orden is None:
            c.sin_poder_dimensionar += 1
            registrar(f"{nombre}: senal sin poder dimensionar -> {motivo_no}")
            continue

        cuenta = AccountState(
            equity=c.equity, balance=c.equity, free_margin=c.equity * 0.9,
            used_margin=c.equity * 0.1, peak_equity=c.peak_equity,
            realized_pnl_today=pnl_realizado_hoy,
            # Lo abierto, valorizado: sin esto los cortes quedan ciegos.
            unrealized_pnl=valorizar_abiertas(c, precios, spreads_usados),
            # CRITICO: el motor de riesgo tiene que ver TODAS las posiciones
            # abiertas, no una tupla vacia. Si no, el tope de apalancamiento
            # y el de posiciones simultaneas no se pueden aplicar.
            open_positions=tuple(
                __import__("labcore.riesgo.modelo", fromlist=["OpenPosition"])
                .OpenPosition(p.instrumento, Side(p.side), p.volume,
                              p.precio_entrada, p.stop_loss, "CRYPTO")
                for p in c.abiertas),
            market_open=True)
        from labcore.riesgo.modelo import Quote
        medio = costos.spread_efectivo(ultima.spread) / 2
        q = Quote(nombre, ultima.close - medio, ultima.close + medio,
                  datetime.now(timezone.utc), medio * 2, None)
        d = riesgo.evaluar(orden, cuenta, spec, q)
        c.ordenes_evaluadas += 1
        if not d.approved:
            c.ordenes_vetadas += 1
            for cod in d.rejects:
                c.vetos_por_codigo[cod.value] = \
                    c.vetos_por_codigo.get(cod.value, 0) + 1
            registrar(f"{nombre}: orden VETADA -> {d.reason_text}")
            continue

        anotar_tel(Medicion(__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
            "reaccion", f"senal-a-orden:{nombre}",
            ms=(_t.perf_counter()-_t_senal)*1000,
            detalle={"estrategia": e.strategy_id}))
        c.abiertas.append(PosicionPapel(
            instrumento=nombre, estrategia=e.strategy_id,
            side=orden.side.value, volume=orden.volume,
            precio_entrada=orden.reference_price, stop_loss=orden.stop_loss,
            take_profit=orden.take_profit,
            riesgo_inicial=bt._valor_por_precio(
                orden.volume, abs(orden.reference_price - orden.stop_loss)),
            abierta_en=ultima.ts.isoformat(),
            razon_apertura=senal.motivo))
        eventos.append(
            f"ABRE {nombre} {orden.side.value} {orden.volume:.4f} @ "
            f"{orden.reference_price:,.2f} stop {orden.stop_loss:,.2f} "
            f"({senal.motivo})")

    if c.ultimo_dia != hoy:
        c.dias_operados += 1
        c.ultimo_dia = hoy
    c.guardar(RUTA)

    cerrados_hoy = sum(1 for tr in c.cerradas
                       if tr.razon_cierre == "CIERRE_INTRADIA")
    medidos = sum(1 for _, o in spreads_usados.values() if o.startswith("medido"))
    registrar(f"spreads: {medidos}/{len(spreads_usados)} medidos, "
              f"el resto asumido al 0,1%")
    registrar(f"horario: {resumen_horario().splitlines()[1]} | "
              f"cierres_por_intradia_acumulados={cerrados_hoy}")
    registrar(f"pasada: instrumentos_mirados={mirados} eventos={len(eventos)} "
              f"abiertas={len(c.abiertas)} cerradas={len(c.cerradas)} "
              f"equity={c.equity:.2f}")
    if mirados == 0:
        registrar("ATENCION: no se pudo mirar NINGUN instrumento")
        print("ATENCION: no se pudo mirar ningun instrumento")
        return 1

    anotar_tel(Medicion(__import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat(),
        "pasada", "ciclo_papel", ms=(_t.perf_counter()-t0_pasada)*1000,
        detalle={"ok": mirados > 0, "instrumentos": mirados,
                 "eventos": len(eventos), "abiertas": len(c.abiertas)}))
    for ev in eventos:
        print(ev)
    if not eventos:
        print(f"sin movimientos. {len(c.abiertas)} posicion(es) abierta(s).")
    nr = valorizar_abiertas(c, precios, spreads_usados)
    print()
    print(c.resumen())
    if c.abiertas:
        print(f"no realizado US$ {nr:+.2f}   "
              f"TOTAL AHORA US$ {c.equity + nr:,.2f} "
              f"({(c.equity + nr - c.capital_inicial)/c.capital_inicial:+.2%})")
    # Si hubo eventos, se dejan para que el cron los avise.
    (RUTA / "ultimos_eventos.json").write_text(
        json.dumps(eventos, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
