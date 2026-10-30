"""Prueba de SOLO LECTURA contra la cuenta demo de Exness.

No envia ninguna orden: el cliente no tiene metodos para hacerlo.
Imprime la clave censurada, nunca completa, y nunca la llave privada.

Secuencia, exactamente la de /trading/get-started/access-point-host-discovery:
  1. Firmar GET /v1/trading/access-point?account_id=... contra el GATEWAY
  2. Usar el access_point devuelto para todo lo demas
  3. Leer cuenta, limites e instrumentos
"""
from __future__ import annotations
import json, sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labcore.exness.cliente import ClienteLectura, ErrorExness
from labcore.exness.entorno import GATEWAYS, cargar
from labcore.exness.firma import Credencial


def main() -> int:
    cfg = cargar()                      # DEMO por defecto
    print("=" * 72)
    print("PRUEBA DE SOLO LECTURA — EXNESS")
    print("=" * 72)
    print(cfg.describir())
    if cfg.es_real:
        print("\nABORTO: esta prueba es solo para DEMO.")
        return 2
    print()

    cred = Credencial(api_key=cfg.api_key, private_key_path=cfg.private_key_path,
                      account_id=cfg.account_id,
                      discovery_base_url=cfg.discovery_base_url)

    # --- 1. descubrimiento del punto de acceso ---
    # Se prueban los gateways que muestra el panel, en orden. El host NO
    # queda fijo: lo que se usa despues es el access_point devuelto.
    ap, usado, ultimo_error = None, None, None
    for gw in (cfg.discovery_base_url, *[g for g in GATEWAYS if g != cfg.discovery_base_url]):
        c = ClienteLectura(Credencial(cred.api_key, cred.private_key_path,
                                      cred.account_id, gw))
        try:
            ap = c.access_point()
            usado = gw
            c.desconectar()
            break
        except ErrorExness as e:
            ultimo_error = f"{gw} -> {e}"
            print(f"  gateway {gw}: {str(e)[:150]}")
        except Exception as e:  # red, DNS, TLS
            ultimo_error = f"{gw} -> {type(e).__name__}: {e}"
            print(f"  gateway {gw}: {type(e).__name__}: {str(e)[:120]}")
        finally:
            try: c.desconectar()
            except Exception: pass

    if ap is None:
        print()
        print("FALLO EL DESCUBRIMIENTO DEL PUNTO DE ACCESO.")
        print(f"ultimo error: {ultimo_error}")
        print()
        print("Que revisar, segun /authentication/request-signing:")
        print("  1000 AUTH_INVALID_API_KEY     -> la clave, su expiracion,")
        print("                                   y api_key dentro de EXN-DATA")
        print("  1001 AUTH_INVALID_SIGNATURE   -> EXN-DATA/EXN-SIGN, la llave")
        print("                                   privada, la serializacion,")
        print("                                   el body_hash, el timestamp")
        print("  1002 AUTH_PERMISSION_DENIED   -> acceso a la cuenta, IP de")
        print("                                   origen, permisos de la key")
        return 1

    print(f"  punto de acceso descubierto: {ap}")
    print(f"  (gateway que respondio: {usado})")
    print()

    cli = ClienteLectura(Credencial(cred.api_key, cred.private_key_path,
                                    cred.account_id, usado))
    fallos = 0
    try:
        for titulo, fn in (("CUENTA", cli.cuenta),
                           ("LIMITES (rate limits reales)", cli.limites),
                           ("INSTRUMENTOS", cli.instrumentos)):
            print(f"--- {titulo} ---")
            try:
                d = fn()
                s = json.dumps(d, indent=2, ensure_ascii=False)
                # Censura por si acaso: la clave nunca debe salir en pantalla.
                s = s.replace(cfg.api_key, f"{cfg.api_key[:10]}…CENSURADA")
                print(s[:1400] + ("\n  …(recortado)" if len(s) > 1400 else ""))
            except ErrorExness as e:
                fallos += 1
                print(f"  FALLO: {e}")
            print()
    finally:
        cli.desconectar()

    print("=" * 72)
    if fallos:
        print(f"LECTURA PARCIAL: {fallos} de 3 llamadas fallaron.")
        return 1
    print("LECTURA COMPLETA OK. Ninguna orden enviada.")
    print("El cliente NO tiene metodos para operar: el codigo no existe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
