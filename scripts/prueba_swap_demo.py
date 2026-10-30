"""Abre UNA posicion demo minima para medir el swap real.

Objetivo unico: zanjar si swap_long esta en moneda de la cuenta o en
puntos. Entre las dos lecturas hay 100x de diferencia en BTCUSD, y de eso
depende si una estrategia de cripto apalancado es viable o ficcion.

NO es trading: es una medicion. Se abre, se deja pasar la noche, se lee
el swap cobrado y se cierra.

Uso:
    lab python scripts/prueba_swap_demo.py              # simulacro
    lab python scripts/prueba_swap_demo.py --enviar     # envia de verdad
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labcore.exness.cliente import ClienteLectura
from labcore.exness.ejecucion import EjecucionBloqueada, Ejecutor
from labcore.exness.entorno import cargar
from labcore.exness.firma import Credencial
from labcore.riesgo import (
    AccountState, InstrumentSpec, KillSwitch, Quote, RiskEngine, RiskLimits, Side,
)

INSTRUMENTO = "BTCUSD"     # donde la ambiguedad del swap es de 100x
RIESGO_USD = 10.0          # autorizado por Fernando


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--enviar", action="store_true")
    ap.add_argument("--instrumento", default=INSTRUMENTO)
    ap.add_argument("--lado", default="BUY", choices=["BUY", "SELL"])
    args = ap.parse_args()

    cfg = cargar()
    print("=" * 74)
    print(f"{'ENVIO REAL' if args.enviar else 'SIMULACRO (no envia nada)'} — "
          f"medicion del swap")
    print("=" * 74)
    print(cfg.describir())
    print()

    cli = ClienteLectura(Credencial(cfg.api_key, cfg.private_key_path,
                                    cfg.account_id, cfg.discovery_base_url))
    try:
        # --- estado y precio actuales, de la API ---
        snap = cli.estado_cuenta()
        st = snap.get("account_state", snap)
        equity = float(st.get("equity", 0))
        balance = float(st.get("balance", 0))
        abiertas = len(snap.get("positions") or [])
        print(f"saldo {balance:,.2f}   patrimonio {equity:,.2f}   "
              f"posiciones abiertas {abiertas}")

        ins = args.instrumento
        k = cli.condiciones(ins)
        cond = k.crudo.get("conditions", k.crudo)
        dig = int(cond.get("point_digits", 2))

        # Precio actual desde la ultima vela de 1 minuto.
        ahora = datetime.now(timezone.utc)
        # count NEGATIVO = las ultimas N velas hacia atras desde `from`.
        velas = cli.velas(ins, "M1",
                          ahora.strftime("%Y-%m-%dT%H:%M:%SZ"), count=-5)
        if not velas:
            print("no pude leer el precio actual: sin velas")
            return 1
        ult = velas[-1]
        px = float(ult.get("close") or ult.get("c"))
        print(f"{ins}: precio {px:,.{dig}f}   contrato {k.contract_size:g}   "
              f"vol_min {k.volume_min:g}   paso {k.volume_step:g}   "
              f"{dig} decimales")
        print(f"swap_long {k.swap_long}   swap_short {k.swap_short}")
        print()

        # --- tamano: el MINIMO, y el stop puesto para arriesgar ~RIESGO_USD ---
        vol = k.volume_min
        # valor de 1 unidad de precio = contract_size * volumen
        val_por_punto = k.contract_size * vol
        dist = RIESGO_USD / val_por_punto if val_por_punto else 0
        side = Side[args.lado]
        sl = px - dist if side is Side.BUY else px + dist
        tp = px + dist * 2 if side is Side.BUY else px - dist * 2
        print(f"volumen {vol:g} (el minimo)   nocional US$ "
              f"{k.contract_size*vol*px:,.2f}")
        print(f"stop a {dist:,.2f} de distancia ({dist/px:.2%}) -> "
              f"riesgo US$ {dist*val_por_punto:,.2f}")
        print(f"entrada ~{px:,.{dig}f}   stop {sl:,.{dig}f}   objetivo {tp:,.{dig}f}")
        print()

        # --- limites para ESTA medicion, declarados ---
        # 2% por operacion en vez de 0,5%: Fernando autorizo US$10 sobre una
        # demo de US$500. Es una medicion de una vez, no trading de estrategia.
        lim = RiskLimits(per_trade_risk_pct=0.025, daily_loss_limit_pct=0.10,
                         max_drawdown_pct=0.20, max_open_positions=3,
                         apalancamiento_maximo=5.0,
                         max_spread_multiple=5.0, max_quote_age_s=300.0)
        ks = KillSwitch(); ks.desactivar(por="prueba de swap")
        motor = RiskEngine(lim, ks)

        spread = px * 0.0003
        cta = AccountState(
            equity=equity, balance=balance, free_margin=equity * 0.95,
            used_margin=float(st.get("used_margin", 0)), peak_equity=equity,
            realized_pnl_today=0.0, unrealized_pnl=0.0,
            open_positions=(), market_open=True)
        q = Quote(ins, px - spread/2, px + spread/2,
                  datetime.now(timezone.utc), spread, None)
        spec = InstrumentSpec(ins, k.contract_size, 10 ** -dig,
                              10 ** -dig * k.contract_size,
                              k.volume_min, k.volume_step,
                              k.margin_percent/100, "CRYPTO")

        with Ejecutor(cfg, cli, motor) as ex:
            print(f"la API confirma is_demo = {ex.confirmar_demo()}")
            print()
            try:
                ack, d, expl = ex.abrir_posicion(
                    ins, side, vol, sl, tp, cta, spec, q,
                    permitir_envio=args.enviar)
            except EjecucionBloqueada as e:
                print(f"CERROJO: {e}")
                return 1
            print(expl)
            if d is not None:
                print(f"riesgo calculado: {d.detail.get('riesgo_abs')} "
                      f"({d.detail.get('riesgo_pct')})  "
                      f"margen requerido: {d.detail.get('margen_requerido')}")
            if ack:
                print()
                print("--- reconciliacion: estado de la operacion ---")
                try:
                    print(json.dumps(ex.estado_operacion(ack.operation_id),
                                     indent=2, ensure_ascii=False)[:900])
                except Exception as e:
                    print(f"  (aun no disponible: {type(e).__name__}: "
                          f"{str(e)[:100]})")
                print()
                print("--- posiciones segun la API ---")
                s2 = cli.estado_cuenta()
                print(json.dumps(s2.get("positions") or [], indent=2)[:700])
    finally:
        cli.desconectar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
