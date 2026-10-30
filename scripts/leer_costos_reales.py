"""ETAPA 1: leer los costos REALES de la cuenta y guardarlos.

Es la primera vez que este laboratorio toca datos de verdad. Solo lectura:
ninguna orden, ni simulada ni real.

Uso (en cuanto exista ~/.config/exness/env):
    lab python scripts/leer_costos_reales.py
    lab python scripts/leer_costos_reales.py --instrumentos EURUSD XAUUSD BTCUSD

Lo que hace, en orden:
  1. Resuelve el access point de la cuenta.
  2. Lee el estado de la cuenta y los RATE LIMITS reales (que la doc no
     publica: solo se conocen asi).
  3. Lee las condiciones de cada instrumento: swap, comision, contrato.
  4. Lo guarda en config/costos_reales.json, fechado.

Lo que NO puede hacer: el spread, que es dinamico y sale del WebSocket de
ticks. Hasta medirlo, hay que correr tambien el escenario de estres.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labcore.exness.cliente import ClienteLectura, ErrorExness
from labcore.exness.firma import Credencial

SALIDA = Path(__file__).resolve().parents[1] / "config" / "costos_reales.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instrumentos", nargs="+",
                    default=["EURUSD", "XAUUSD", "BTCUSD"])
    args = ap.parse_args()

    try:
        cred = Credencial.desde_env()
    except (FileNotFoundError, ValueError) as e:
        print(f"CREDENCIAL NO DISPONIBLE: {e}")
        print()
        print("Esto es lo esperado hasta que crees la API key. Pasos:")
        print("  1. bash scripts/crear_llave_exness.sh   (en tu computador)")
        print("  2. Exness -> Personal Area -> Key Management")
        print("  3. llenar ~/.config/exness/env")
        return 2

    print(f"cuenta       : {cred.account_id}")
    print(f"gateway      : {cred.discovery_base_url}")
    print(f"llave privada: {cred.private_key_path} (no se imprime)")
    print()

    salida: dict = {
        "medido_en": datetime.now(timezone.utc).isoformat(),
        "account_id": cred.account_id,
        "instrumentos": {},
        "no_medido": ["spread (es dinamico: sale del WebSocket de ticks)"],
    }

    with ClienteLectura(cred) as c:
        try:
            print(f"access point : {c.access_point()}")
        except ErrorExness as e:
            print(f"FALLO EL DESCUBRIMIENTO: {e}")
            return 1

        try:
            cuenta = c.cuenta()
            salida["cuenta"] = cuenta
            print(f"moneda       : {cuenta.get('currency')}")
            print(f"apalancamiento: {cuenta.get('leverage')}")
            print(f"trade_mode   : {cuenta.get('trade_mode')}")
            if cuenta.get("trade_mode") != "enabled":
                print("  ATENCION: la cuenta NO esta habilitada para operar")
        except ErrorExness as e:
            print(f"no pude leer la cuenta: {e}")

        try:
            lim = c.limites()
            salida["limites"] = lim
            print()
            print("RATE LIMITS REALES (la doc no publica ningun numero):")
            print(json.dumps(lim, indent=2, ensure_ascii=False)[:900])
        except ErrorExness as e:
            print(f"no pude leer los limites: {e}")

        try:
            disponibles = c.instrumentos()
            salida["instrumentos_disponibles"] = disponibles
            nombres = {
                (i if isinstance(i, str) else i.get("instrument") or i.get("name"))
                for i in disponibles
            }
            print()
            print(f"instrumentos en la cuenta: {len(nombres)}")
            faltan = [i for i in args.instrumentos if i not in nombres]
            if faltan and nombres:
                print(f"  OJO: pedidos y NO disponibles: {faltan}")
        except ErrorExness as e:
            print(f"no pude listar instrumentos: {e}")

        print()
        print(f"{'instrumento':<10} {'swap largo':>11} {'swap corto':>11} "
              f"{'comision':>10} {'tipo':<22} {'contrato':>10} {'margen':>8}")
        print("-" * 88)
        leidos = 0
        for ins in args.instrumentos:
            try:
                k = c.condiciones(ins)
            except ErrorExness as e:
                print(f"{ins:<10} no pude leerlo: {e}")
                continue
            leidos += 1
            salida["instrumentos"][ins] = {
                "condiciones": k.crudo,
                "derivado": {
                    "swap_long": k.swap_long, "swap_short": k.swap_short,
                    "commission_type": k.commission_type,
                    "commission_value": k.commission_value,
                    "contract_size": k.contract_size,
                    "volume_min": k.volume_min, "volume_step": k.volume_step,
                    "margin_percent": k.margin_percent,
                    "comision_por_lote_por_lado":
                        k.a_modelo_costos().comision_por_lote_por_lado,
                },
            }
            print(f"{ins:<10} {str(k.swap_long):>11} {str(k.swap_short):>11} "
                  f"{str(k.commission_value):>10} "
                  f"{str(k.commission_type):<22} "
                  f"{k.contract_size:>10.0f} {k.margin_percent:>7.2f}%")

    # Pareja obligatoria: cuantos pedi y cuantos consegui.
    print("-" * 88)
    print(f"pedidos={len(args.instrumentos)} leidos={leidos}")
    if leidos == 0:
        print("ATENCION: no se leyo NINGUN instrumento. No hay nada que guardar.")
        return 1

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(salida, indent=2, ensure_ascii=False),
                      encoding="utf-8")
    print()
    print(f"guardado en {SALIDA}")
    print("Ahora el backtester puede usar costos MEDIDOS en vez de inventados.")
    print("Falta el spread: corre igual el escenario de estres hasta medirlo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
