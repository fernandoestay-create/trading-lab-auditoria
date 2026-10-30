"""Estado AL MINUTO de la cartera de papel, con lo abierto valorizado.

El equity contable solo cambia al cerrar una operacion. Si solo miras eso,
tres posiciones abiertas se ven como "sin cambios" aunque esten perdiendo.
Aqui se valoriza lo abierto al ultimo precio real (mark to market) y se
separa con claridad:

  REALIZADO    -> ya cerrado, es plata contada
  NO REALIZADO -> abierto, puede cambiar de signo en minutos
"""

from __future__ import annotations

import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.simplefilter("ignore")
import logging
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

from labcore.papel import Cartera
from operar_papel import RUTA, UNIVERSO


def precio_actual(simbolo: str) -> tuple[float, datetime] | None:
    import yfinance as yf
    d = yf.Ticker(simbolo).history(period="1d", interval="5m")
    if d.empty:
        return None
    d = d.tz_convert("UTC") if d.index.tz else d.tz_localize("UTC")
    return float(d["Close"].iloc[-1]), d.index[-1].to_pydatetime()


def main() -> int:
    c = Cartera.cargar(RUTA)
    ahora = datetime.now(timezone.utc)
    print("=" * 76)
    print(f"CARTERA DE PAPEL — {ahora:%F %H:%M} UTC   (FICTICIA, no es dinero real)")
    print("=" * 76)

    realizado = sum(t.pnl_neto for t in c.cerradas)
    no_realizado = 0.0
    nocional = 0.0
    fallos = 0

    if c.abiertas:
        print("\nPOSICIONES ABIERTAS, valorizadas al ultimo precio real:")
        print(f"{'activo':<9} {'dir':<5} {'tamano':>10} {'entrada':>11} "
              f"{'ahora':>11} {'stop':>11} {'resultado':>11} {'en R':>7}")
        print("-" * 80)
        for p in c.abiertas:
            cfg = UNIVERSO.get(p.instrumento)
            px = precio_actual(cfg["simbolo"]) if cfg else None
            if px is None:
                fallos += 1
                print(f"{p.instrumento:<9} {p.side:<5} "
                      f"{'(no pude leer el precio)':>52}")
                continue
            precio, _ = px
            # Al cerrar se paga el medio spread de salida: se descuenta aqui
            # para no mostrar una ganancia que no existe.
            medio = cfg["spread"] / 2
            if p.side == "BUY":
                salida = precio - medio
                delta = salida - p.precio_entrada
            else:
                salida = precio + medio
                delta = p.precio_entrada - salida
            pnl = delta * p.volume
            no_realizado += pnl
            nocional += p.volume * precio
            r = pnl / p.riesgo_inicial if p.riesgo_inicial else 0.0
            print(f"{p.instrumento:<9} {p.side:<5} {p.volume:>10.4f} "
                  f"{p.precio_entrada:>11,.4f} {precio:>11,.4f} "
                  f"{p.stop_loss:>11,.4f} {pnl:>+11.2f} {r:>+7.2f}")
    else:
        print("\nsin posiciones abiertas.")

    eq = c.equity + no_realizado
    print()
    print(f"capital inicial       US$ {c.capital_inicial:>10,.2f}")
    print(f"realizado (cerrado)   US$ {realizado:>+10,.2f}   "
          f"{len(c.cerradas)} operacion(es)")
    print(f"no realizado (abierto)US$ {no_realizado:>+10,.2f}   "
          f"{len(c.abiertas)} posicion(es)")
    print(f"{'-'*46}")
    print(f"TOTAL AHORA           US$ {eq:>10,.2f}   "
          f"({(eq-c.capital_inicial)/c.capital_inicial:+.2%})")
    if nocional:
        print(f"apalancamiento        {nocional/eq:>10.2f}x   (tope 5,00x)")
    print()
    print(f"senales vistas={c.senales_vistas}  evaluadas={c.ordenes_evaluadas}  "
          f"vetadas={c.ordenes_vetadas}  sin_dimensionar={c.sin_poder_dimensionar}")
    if fallos:
        print(f"ATENCION: no pude leer el precio de {fallos} posicion(es). "
              f"El total de arriba esta INCOMPLETO.")
    if c.abiertas:
        print()
        print("El no realizado puede cambiar de signo en minutos. Solo el "
              "realizado es plata contada.")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
