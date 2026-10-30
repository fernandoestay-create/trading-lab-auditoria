"""Operador EN VIVO sobre la cuenta DEMO de Exness.

Diferencia clave con el de papel: aqui la fuente de verdad son las
posiciones que reporta la API, no un archivo local. Eso cambia el diseño
entero -- se RECONCILIA contra el broker en cada pasada en vez de llevar
la cuenta uno mismo. Un archivo local y el broker se desincronizan, y
cuando pasa, el archivo miente con confianza.

Cerrojos, todos en cada pasada:
  1. entorno DEMO (REAL exige autorizacion escrita aparte)
  2. la API confirma is_demo=True -- no se confia en el .env
  3. el instrumento tiene trade_mode=enabled
  4. el horario permite abrir (reglas de Fernando: intradia, bolsa abierta)
  5. el MISMO motor de riesgo del backtester aprueba
  6. volumen y precios cumpliendo las reglas del instrumento, de la API

Y antes que todo: si llego la hora del rollover, CIERRA todo. La regla de
intradia manda sobre cualquier senal.

Uso:
    lab python scripts/operar_demo.py            # simulacro, no envia
    lab python scripts/operar_demo.py --enviar   # opera de verdad (demo)
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labcore.backtest.costos import ModeloCostos
from labcore.backtest.mercado import Barra, VentanaMercado
from labcore.estrategias import CruceMedias, RupturaDeRango
from labcore.exness.cliente import ClienteLectura, ErrorExness
from labcore.exness.ejecucion import EjecucionBloqueada, Ejecutor
from labcore.exness.entorno import cargar
from labcore.exness.firma import Credencial
from labcore.horarios import debe_cerrar_todo, puede_abrir
from labcore.riesgo import (
    AccountState, InstrumentSpec, KillSwitch, OpenPosition, Quote, RiskEngine,
    RiskLimits, Side,
)
from labcore.telemetria import Medicion, anotar, antiguedad_del_dato

LOG = Path.home() / "logs" / "trading-lab-demo.log"

# UNIVERSO. Nombres reales de la cuenta, verificados contra la API.
#
# Los grupos NO son categorias: son grupos de RIESGO derivados de la
# correlacion medida sobre 1.984 dias (labcore/correlaciones.py). Dos
# instrumentos del mismo grupo no diversifican -- el motor de riesgo los
# trata como una posicion del tamano sumado.
#
# Medido: BTCUSD/ETHUSD +0,83 y oro/plata +0,78 son UNA apuesta cada par.
# Los unicos genuinamente independientes son el petroleo, el cobre, el gas
# y EURUSD. Un instrumento sin medir recibe su PROPIO grupo: meterlo en uno
# ajeno por adivinanza hace pasar riesgo concentrado por diversificado.
#
# `horario` decide cuando se puede abrir: CRYPTO opera 24/7, el resto no.
UNIVERSO = {
    # --- 24/7: lo unico operable el fin de semana ---
    "BTCUSD":    {"grupo": "GRUPO_CRIPTO", "tf": "M5", "horario": "CRYPTO"},
    "ETHUSD":    {"grupo": "GRUPO_CRIPTO", "tf": "M5", "horario": "CRYPTO"},
    "XAUUSD247": {"grupo": "GRUPO_METALES", "tf": "M5", "horario": "CRYPTO"},
    # --- independientes de verdad (abren de domingo a viernes) ---
    "USOIL":     {"grupo": "SOLO_PETROLEO", "tf": "M5", "horario": "FOREX"},
    "UKOIL":     {"grupo": "SOLO_PETROLEO", "tf": "M5", "horario": "FOREX"},
    "XCUUSD":    {"grupo": "SOLO_COBRE",    "tf": "M5", "horario": "FOREX"},
    "XNGUSD":    {"grupo": "SOLO_GAS",      "tf": "M5", "horario": "FOREX"},
    "EURUSD":    {"grupo": "SOLO_EURUSD",   "tf": "M5", "horario": "FOREX"},
    # --- metales en horario normal (mismo grupo que el oro 24/7) ---
    "XAUUSD":    {"grupo": "GRUPO_METALES", "tf": "M5", "horario": "FOREX"},
    "XAGUSD":    {"grupo": "GRUPO_METALES", "tf": "M5", "horario": "FOREX"},
    # --- indices (una sola apuesta entre si y con las acciones de EEUU) ---
    "US500":     {"grupo": "GRUPO_ACCIONES_EEUU", "tf": "M5", "horario": "EQUITY_US"},
    "US30":      {"grupo": "GRUPO_ACCIONES_EEUU", "tf": "M5", "horario": "EQUITY_US"},
    # --- otras divisas mayores, cada una su grupo hasta medirlas ---
    "GBPUSD":    {"grupo": "SOLO_GBPUSD", "tf": "M5", "horario": "FOREX"},
    "USDJPY":    {"grupo": "SOLO_USDJPY", "tf": "M5", "horario": "FOREX"},
    "AUDUSD":    {"grupo": "SOLO_AUDUSD", "tf": "M5", "horario": "FOREX"},
}

# 1% del patrimonio por operacion. Con US$500 son US$5.
# Mas bajo que esto y los stops quedan tan pegados al precio que el ruido
# los barre; mas alto y dos perdidas seguidas pesan demasiado. Es un
# parametro declarado, no un numero comodo.
RIESGO_POR_OPERACION = 0.01


def registrar(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"[{datetime.now(timezone.utc):%F %T}] {msg}\n")


def ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def barras_de(cli: ClienteLectura, ins: str, tf: str,
              n: int = 120) -> list[Barra]:
    """Velas reales de Exness. price_type=bid; el spread se agrega aparte."""
    desde = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    t0 = time.perf_counter()
    vs = cli.velas(ins, tf, desde, count=-n, price_type="bid")
    anotar(Medicion(ahora_iso(), "latencia_api", f"velas:{ins}",
                    ms=(time.perf_counter() - t0) * 1000))
    out = []
    for v in vs:
        ts = v.get("time") or v.get("t") or v.get("open_time")
        if isinstance(ts, str):
            d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            d = datetime.fromtimestamp(float(ts) / 1000, timezone.utc)
        o, h, l, c = (float(v.get(k) or v.get(k[0]))
                      for k in ("open", "high", "low", "close"))
        out.append(Barra(d, o, h, l, c, float(v.get("volume") or 0), 0.0))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--enviar", action="store_true")
    args = ap.parse_args()

    cfg = cargar()
    if cfg.es_real:
        print("ABORTO: este script es solo para DEMO.")
        return 2

    cli = ClienteLectura(Credencial(cfg.api_key, cfg.private_key_path,
                                    cfg.account_id, cfg.discovery_base_url))
    ks = KillSwitch()
    if ks.activo():
        registrar(f"KILL SWITCH: {ks.motivo()}")
        print(f"KILL SWITCH ACTIVO: {ks.motivo()}")
        return 0

    limites = RiskLimits(
        per_trade_risk_pct=RIESGO_POR_OPERACION,
        daily_loss_limit_pct=0.03, max_drawdown_pct=0.10,
        max_open_positions=5, apalancamiento_maximo=5.0,
        max_spread_multiple=5.0, max_quote_age_s=600.0,
        max_correlated_exposure_pct=0.80)
    motor = RiskEngine(limites, ks)
    eventos: list[str] = []
    t0_pasada = time.perf_counter()

    try:
        # --- estado REAL, del broker ---
        t0 = time.perf_counter()
        snap = cli.estado_cuenta()
        anotar(Medicion(ahora_iso(), "latencia_api", "snapshot",
                        ms=(time.perf_counter() - t0) * 1000))
        st = snap.get("account_state", {})
        equity = float(st.get("equity", 0))
        balance = float(st.get("balance", 0))
        posiciones = snap.get("positions") or []
        print(f"cuenta {cfg.account_id} (demo)   saldo {balance:,.2f}   "
              f"patrimonio {equity:,.2f}   abiertas {len(posiciones)}")

        with Ejecutor(cfg, cli, motor) as ex:
            if not ex.confirmar_demo():
                print("ABORTO: la API dice is_demo=False")
                return 2

            # --- REGLA DE INTRADIA: manda sobre cualquier senal ---
            for p in list(posiciones):
                ins = p["instrument"]
                hor = UNIVERSO.get(ins, {}).get("horario", "CRYPTO")
                # Tambien se pasa cuando se abrio: el tope de 8 horas
                # resuelve la ambiguedad de "intradia" sin depender de
                # donde se ponga el limite del dia.
                ab = p.get("create_time")
                abierta = None
                if ab:
                    try:
                        abierta = datetime.fromisoformat(
                            str(ab).replace("Z", "+00:00"))
                    except ValueError:
                        abierta = None
                hay_que, por_que = debe_cerrar_todo(hor, abierta_en=abierta)
                if not hay_que:
                    continue
                print(f"INTRADIA: cerrando {ins} ({por_que})")
                if args.enviar:
                    try:
                        ack, expl = ex.cerrar_posicion(p["position_id"],
                                                       permitir_envio=True)
                        eventos.append(f"CIERRA {ins} por INTRADIA: {expl}")
                        registrar(f"cierre intradia {ins}: {expl}")
                    except (ErrorExness, EjecucionBloqueada) as e:
                        registrar(f"ATENCION: no pude cerrar {ins}: {e}")
                        print(f"  NO pude cerrar: {e}")
                else:
                    eventos.append(f"[simulacro] cerraria {ins} por INTRADIA")
            if eventos:
                time.sleep(2)
                snap = cli.estado_cuenta()
                posiciones = snap.get("positions") or []
                st = snap.get("account_state", {})
                equity = float(st.get("equity", equity))

            abiertas_por_ins = {p["instrument"] for p in posiciones}

            # --- buscar senales ---
            for ins, meta in UNIVERSO.items():
                if ins in abiertas_por_ins:
                    continue
                se_puede, motivo = puede_abrir(meta["horario"])
                if not se_puede:
                    registrar(f"{ins}: no se abre, {motivo}")
                    continue

                k = cli.condiciones(ins)
                cond = k.crudo.get("conditions", k.crudo)
                if cond.get("trade_mode") != "enabled":
                    registrar(f"{ins}: trade_mode={cond.get('trade_mode')}")
                    continue
                dig = int(cond.get("point_digits", 2))

                try:
                    bs = barras_de(cli, ins, meta["tf"])
                except ErrorExness as e:
                    registrar(f"{ins}: no pude leer velas: {e}")
                    continue
                if len(bs) < 60:
                    registrar(f"{ins}: solo {len(bs)} velas")
                    continue
                antiguedad_del_dato(bs[-1].ts, ins)

                # spread real del momento, de las condiciones del instrumento
                px = bs[-1].close
                spread = float(cond.get("spread") or 0) or px * 0.0002
                bs = [Barra(b.ts, b.open, b.high, b.low, b.close, b.volume,
                            b.close * (spread / px)) for b in bs]

                senal, elegida = None, None
                for e in (RupturaDeRango(20), RupturaDeRango(55),
                          CruceMedias(20, 50)):
                    if len(bs) - 1 < e.barras_minimas:
                        continue
                    s = e.evaluar(VentanaMercado(bs, len(bs) - 2, ins))
                    if s.side is not None:
                        senal, elegida = s, e
                        break
                if senal is None:
                    continue

                spec = InstrumentSpec(
                    ins, k.contract_size, 10 ** -dig,
                    10 ** -dig * k.contract_size, k.volume_min,
                    k.volume_step, k.margin_percent / 100, meta["grupo"])
                # El grupo de riesgo es el MEDIDO, no la categoria: con el,
                # el motor veta abrir dos cosas que son la misma apuesta.
                val_por_punto = k.contract_size
                vol = (equity * RIESGO_POR_OPERACION) / (
                    senal.stop_loss_distancia * val_por_punto)
                vol = max(vol, 0)
                es_compra = senal.side is Side.BUY
                entrada = px + (spread / 2 if es_compra else -spread / 2)
                sl = (entrada - senal.stop_loss_distancia if es_compra
                      else entrada + senal.stop_loss_distancia)
                tp = (entrada + senal.take_profit_distancia if es_compra
                      else entrada - senal.take_profit_distancia)

                cta = AccountState(
                    equity=equity, balance=balance,
                    free_margin=equity * 0.9,
                    used_margin=float(st.get("used_margin", 0)),
                    peak_equity=max(equity, balance),
                    realized_pnl_today=0.0, unrealized_pnl=equity - balance,
                    open_positions=tuple(
                        OpenPosition(p["instrument"],
                                     Side.BUY if p["direction"] == "buy" else Side.SELL,
                                     float(p["volume"]), float(p["open_price"]),
                                     None,
                                     UNIVERSO.get(p["instrument"], {}).get(
                                         "grupo", f"SIN_MEDIR_{p['instrument']}"))
                        for p in posiciones),
                    market_open=True)
                q = Quote(ins, px - spread / 2, px + spread / 2,
                          datetime.now(timezone.utc), spread, None)

                t_senal = time.perf_counter()
                try:
                    ack, d, expl = ex.abrir_posicion(
                        ins, senal.side, vol, sl, tp, cta, spec, q,
                        permitir_envio=args.enviar)
                except EjecucionBloqueada as e:
                    print(f"  {ins}: CERROJO: {e}")
                    registrar(f"{ins}: cerrojo: {e}")
                    continue
                except ErrorExness as e:
                    print(f"  {ins}: ERROR DEL BROKER: {e}")
                    registrar(f"{ins}: error del broker: {e}")
                    anotar(Medicion(ahora_iso(), "error", f"abrir:{ins}",
                                    detalle={"mensaje": str(e)[:200]}))
                    continue
                anotar(Medicion(ahora_iso(), "reaccion", f"senal-a-orden:{ins}",
                                ms=(time.perf_counter() - t_senal) * 1000))
                linea = (f"{ins} {senal.side.value} {vol:.4f} @ ~{entrada:,.{dig}f} "
                         f"stop {sl:,.{dig}f} tp {tp:,.{dig}f} ({senal.motivo})")
                if ack:
                    eventos.append(f"ABRE {linea}")
                    registrar(f"ABRE {linea} -> {ack}")
                    print(f"  ABRE {linea}")
                else:
                    print(f"  {ins}: {expl}")
                    registrar(f"{ins}: {expl}")

        print()
        print(motor.resumen())
        # Una pasada que no encuentra nada tiene que DECIRLO en el log, no
        # solo en pantalla. Si no, no hay forma de distinguir "no habia
        # senal" de "el cron no corrio" -- y las dos se ven igual.
        registrar(f"pasada: mirados={len(UNIVERSO)} "
                  f"senales_evaluadas={motor.evaluadas} "
                  f"aprobadas={motor.aprobadas} eventos={len(eventos)} "
                  f"abiertas={len(posiciones)} equity={equity:.2f}")
        if not eventos:
            print("sin movimientos.")
    finally:
        anotar(Medicion(ahora_iso(), "pasada", "operar_demo",
                        ms=(time.perf_counter() - t0_pasada) * 1000,
                        detalle={"ok": True, "eventos": len(eventos)}))
        cli.desconectar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
