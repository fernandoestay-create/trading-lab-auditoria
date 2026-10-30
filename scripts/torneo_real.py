"""Torneo sobre DATOS REALES, con el capital que diga el usuario.

Primera vez que el laboratorio mira mercados de verdad. Todo lo anterior
fue sintetico y servia para probar al juez, no para medir estrategias.

Uso:
    lab python scripts/torneo_real.py --capital 1000
    lab python scripts/torneo_real.py --capital 1000 --estres 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labcore.backtest import ModeloCostos
from labcore.datos import INSTRUMENTOS, a_barras, descargar, guardar, validar
from labcore.estrategias import (
    Aleatoria, BandasBollinger, ComprarYMantener, CruceMedias, MACD,
    RSIReversion, RupturaDeRango, ZScoreReversion,
)
from labcore.experimentos import RegistroExperimentos
from labcore.metricas import Torneo
from labcore.riesgo import InstrumentSpec, RiskLimits


def estrategias():
    return [CruceMedias(20, 50), CruceMedias(10, 100), MACD(),
            RupturaDeRango(20), RupturaDeRango(55), RSIReversion(),
            BandasBollinger(), ZScoreReversion(),
            Aleatoria(prob=0.04, semilla=7), ComprarYMantener()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--estres", type=float, default=1.0,
                    help="multiplicador del spread")
    ap.add_argument("--solo", nargs="*", default=None)
    args = ap.parse_args()

    registro = RegistroExperimentos()
    print(f"CAPITAL: US$ {args.capital:,.0f}   "
          f"riesgo por operacion 0,5% = US$ {args.capital*0.005:,.2f}   "
          f"spread x{args.estres:g}")
    print()
    print("Descargando y VALIDANDO datos reales...")
    datos: dict[str, tuple] = {}
    for sim, cfg in INSTRUMENTOS.items():
        if args.solo and cfg["nombre"] not in args.solo:
            continue
        try:
            d, v = validar(sim, descargar(sim))
        except Exception as e:
            print(f"  {cfg['nombre']:<10} FALLO: {type(e).__name__}: {str(e)[:50]}")
            continue
        print(f"  {v}")
        if not v.usable:
            continue
        guardar(sim, cfg["nombre"], d)
        datos[cfg["nombre"]] = (a_barras(d, cfg["spread"]), cfg)

    print(f"\ninstrumentos pedidos={len(INSTRUMENTOS)} usables={len(datos)}")
    if not datos:
        print("ATENCION: ningun instrumento usable. No hay nada que medir.")
        return 1

    # El universo de pruebas es TODO el barrido: instrumentos x estrategias.
    # Si se declarara solo 10 por torneo, la correccion por busqueda
    # multiple quedaria 7 veces mas debil de lo que corresponde.
    n_total = len(datos) * len(estrategias())
    print(f"universo de pruebas declarado: {len(datos)} instrumentos x "
          f"{len(estrategias())} estrategias = {n_total} combinaciones")

    filas = []
    for nombre, (barras, cfg) in datos.items():
        spec = InstrumentSpec(
            symbol=nombre, contract_size=cfg["contrato"], tick_size=cfg["tick"],
            tick_value_account_ccy=cfg["valor_tick"], min_volume=0.01,
            volume_step=0.01, margin_rate=0.01,
            correlation_group=cfg["grupo"])
        costos = ModeloCostos(comision_por_lote_por_lado=0.0, slippage_ticks=1.0,
                              swap_largo_por_lote_dia=0.0,
                              swap_corto_por_lote_dia=0.0,
                              multiplicador_spread=args.estres)
        t = Torneo(spec, costos, barras, capital_inicial=args.capital,
                   limites=RiskLimits())
        t.correr(estrategias(), n_pruebas_totales=n_total)
        rid = registro.anotar_torneo(
            t, etiqueta=f"torneo-real/{nombre}",
            datos_descripcion=f"yfinance diario, spread MODELADO x{args.estres:g}",
            extra={"capital": args.capital, "estres_spread": args.estres,
                   "advertencia": "spread y swap NO medidos en la cuenta real",
                   "n_pruebas_del_barrido": n_total})
        cal = t.califican()
        mejor = t.ranking()[0] if t.ranking() else None
        sin_orden = sum(
            1 for p in t.participantes
            if "NINGUNA senal pudo convertirse en orden" in p.resumen_corrida)
        filas.append((nombre, cfg["grupo"], len(barras), len(cal),
                      mejor, sin_orden, rid))

    print()
    print("=" * 112)
    print(f"{'instrumento':<10} {'grupo':<11} {'barras':>7} {'califican':>10} "
          f"{'mejor':<20} {'ops':>5} {'sharpe':>7} {'t':>6} {'no operables':>13}")
    print("-" * 112)
    for nombre, grupo, nb, ncal, mejor, sin_orden, _ in sorted(
            filas, key=lambda f: -f[3]):
        if mejor:
            d = mejor.desempeno
            print(f"{nombre:<10} {grupo:<11} {nb:>7} {ncal:>10} "
                  f"{mejor.strategy_id:<20} {d.n_operaciones:>5} "
                  f"{d.sharpe:>7.2f} {d.t_stat:>6.2f} {sin_orden:>13}")
    print("-" * 112)
    total_cal = sum(f[3] for f in filas)
    if total_cal == 0:
        print(f"VEREDICTO: NINGUNA ESTRATEGIA CALIFICA EN NINGUN INSTRUMENTO")
        print(f"({len(datos)} instrumentos x 10 estrategias = {len(datos)*10} "
              f"combinaciones probadas, todas rechazadas)")
        print("La recomendacion es NO OPERAR. Es un resultado, no un error.")
    else:
        print(f"CALIFICAN {total_cal} combinaciones, y SOLO EN MUESTRA:")
        for nombre, _, _, ncal, mejor, _, rid in filas:
            if ncal:
                print(f"  {nombre}: {mejor.strategy_id} -> {mejor.desempeno.veredicto}")
                print(f"     corrida {rid}")
    print("=" * 112)
    print(f"corridas registradas en {registro.ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
