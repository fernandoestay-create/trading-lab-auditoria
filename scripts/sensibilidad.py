"""Sensibilidad de parametros: la forma HONESTA de afinar.

Afinar buscando el mejor parametro es sobreajustar con otro nombre. Lo que
de verdad informa es la FORMA de la superficie:

  * Si el resultado solo funciona en N=20 y se cae en 18 y 22, es un
    accidente del dato. Esa es la firma del sobreajuste.
  * Si funciona parecido en todo un rango de N, hay algo estructural.

Por eso aqui no se elige el ganador: se mira si la vecindad acompana.
Lo pide la Fase F del encargo ("sensibilidad de parametros").
"""
from __future__ import annotations
import sys, warnings, logging, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.simplefilter("ignore"); logging.disable(logging.WARNING)

from labcore.backtest import Backtester, ModeloCostos
from labcore.datos import INSTRUMENTOS, a_barras, descargar, validar
from labcore.estrategias import RupturaDeRango
from labcore.riesgo import InstrumentSpec, KillSwitch, RiskEngine, RiskLimits

CAPITAL = 2000.0
# El universo donde la ruptura sobrevivio: cripto. Se mide ahi y en dos
# controles de otra familia, para ver si el patron es del activo o general.
FOCO = ["BTCUSD", "ETHUSD", "SOLUSD", "XAUUSD", "SPY"]
NS = [5, 10, 15, 20, 25, 30, 40, 55, 70, 100]


def main() -> int:
    datos = {}
    for sim, cfg in INSTRUMENTOS.items():
        if cfg["nombre"] not in FOCO:
            continue
        try: d, v = validar(sim, descargar(sim))
        except Exception: continue
        if not v.usable: continue
        datos[cfg["nombre"]] = (a_barras(d.tail(4000), cfg["spread"]), cfg)

    print("SENSIBILIDAD DE LA RUPTURA DE RANGO AL PARAMETRO N")
    print(f"US$ {CAPITAL:,.0f} · ultimas 4.000 barras diarias")
    print("No se busca el mejor N: se mira si la VECINDAD acompana.")
    print("=" * 96)
    print(f"{'activo':<9} " + " ".join(f"{('N='+str(n)):>8}" for n in NS))
    print("-" * 96)

    filas = {}
    for nombre, (barras, cfg) in datos.items():
        spec = InstrumentSpec(nombre, cfg["contrato"], cfg["tick"],
                              cfg["valor_tick"], 0.01, 0.01, 0.01, cfg["grupo"])
        fila = []
        for n in NS:
            e = RupturaDeRango(n)
            m = RiskEngine(RiskLimits(),
                           KillSwitch(Path(tempfile.mkdtemp())/"k.json"))
            r = Backtester(spec, ModeloCostos(slippage_ticks=1.0), m, CAPITAL,
                           barras_minimas=e.barras_minimas).correr(barras, e)
            cerr = [o for o in r.operaciones if not o.abierta]
            fila.append((n, r.equity_final - CAPITAL, len(cerr)))
        filas[nombre] = fila
        print(f"{nombre:<9} " + " ".join(f"{d:>+8.0f}" for _, d, _ in fila))
    print(f"{'(ops)':<9} " + " ".join(f"{'':>8}" for _ in NS))
    for nombre, fila in filas.items():
        print(f"{nombre:<9} " + " ".join(f"{o:>8}" for _, _, o in fila))

    print("-" * 96)
    print()
    print("LECTURA")
    print("-" * 70)
    for nombre, fila in filas.items():
        pos = [n for n, d, o in fila if d > 0 and o >= 30]
        tot = [n for n, d, o in fila if o >= 30]
        if not tot:
            print(f"  {nombre:<9} ningun N alcanza 30 operaciones: no se puede leer")
            continue
        frac = len(pos) / len(tot)
        # contiguidad: los N positivos son vecinos o estan dispersos?
        cont = ""
        if pos:
            idx = [NS.index(n) for n in pos]
            huecos = sum(1 for a, b in zip(idx, idx[1:]) if b - a > 1)
            cont = "contiguos" if huecos == 0 else f"{huecos} hueco(s)"
        veredicto = ("ROBUSTO" if frac >= 0.7 and cont == "contiguos"
                     else "FRAGIL" if frac <= 0.4
                     else "DUDOSO")
        print(f"  {nombre:<9} positivos en {len(pos)}/{len(tot)} valores de N "
              f"({frac:.0%}) {cont:<12} -> {veredicto}")
    print()
    print("  ROBUSTO  = funciona en la mayoria del rango y sin huecos")
    print("  FRAGIL   = funciona en pocos N -> probablemente accidente del dato")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
