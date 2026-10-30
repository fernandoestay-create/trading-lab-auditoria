"""Que pasa si subo el riesgo por operacion? Medido.

A diferencia del apalancamiento, el riesgo por operacion SI es la
restriccion que ataba el tamano. Subirlo escala los resultados... y las
perdidas, y la probabilidad de ruina, en la misma proporcion.
"""
from __future__ import annotations
import sys, tempfile, warnings, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.simplefilter("ignore"); logging.disable(logging.WARNING)

from labcore.backtest import ModeloCostos
from labcore.backtest.cartera_multi import SimuladorCartera
from labcore.datos import INSTRUMENTOS, a_barras, descargar, validar
from labcore.estrategias import CruceMedias, RupturaDeRango
from labcore.riesgo import InstrumentSpec, KillSwitch, RiskEngine, RiskLimits

CAPITAL = 2000.0

def main() -> int:
    mercados = {}
    for sim, cfg in INSTRUMENTOS.items():
        try: d, v = validar(sim, descargar(sim))
        except Exception: continue
        if not v.usable: continue
        mercados[cfg["nombre"]] = (a_barras(d, cfg["spread"]),
            InstrumentSpec(cfg["nombre"], cfg["contrato"], cfg["tick"],
                           cfg["valor_tick"], 0.01, 0.01, 0.01, cfg["grupo"]))
    print(f"US$ {CAPITAL:,.0f} · {len(mercados)} instrumentos · "
          f"subiendo SOLO el riesgo por operacion")
    print("=" * 94)
    print(f"{'riesgo/op':>10} {'equity final':>14} {'anual':>8} {'drawdown':>9} "
          f"{'ops':>5} {'quiebra?':>9} {'peor racha':>11} {'al dia':>9}")
    print("-" * 94)
    for pct in (0.005, 0.01, 0.02, 0.05, 0.10, 0.20):
        lim = RiskLimits(apalancamiento_maximo=5.0, max_open_positions=10,
                         per_trade_risk_pct=pct, daily_loss_limit_pct=0.02,
                         max_drawdown_pct=0.10)
        ks = KillSwitch(Path(tempfile.mkdtemp())/"k.json"); ks.desactivar()
        s = SimuladorCartera(ModeloCostos(slippage_ticks=1.0), lim,
                             RiskEngine(lim, ks), CAPITAL)
        r = s.correr(mercados, lambda: [RupturaDeRango(20), RupturaDeRango(55),
                                        CruceMedias(20, 50)])
        dias = (r.curva[-1][0] - r.curva[0][0]).days if len(r.curva) > 1 else 1
        anos = dias / 365.25
        cagr = ((r.equity/CAPITAL)**(1/anos) - 1) if r.equity > 0 and anos > 0 else -1.0
        # peor racha de perdidas consecutivas
        peor = racha = 0
        for o in r.cerradas:
            racha = racha + 1 if o.pnl_neto <= 0 else 0
            peor = max(peor, racha)
        quiebra = "SI" if r.equity <= CAPITAL * 0.1 else "no"
        # TRAMPA: al subir el riesgo, las primeras operaciones consumen el
        # cupo de apalancamiento y el resto queda vetado. La muestra se
        # derrumba y lo que queda es SUERTE. La fila que se ve mejor suele
        # ser la que tiene menos operaciones. Se marca para que nadie la lea
        # como un resultado.
        aviso = "" if len(r.cerradas) >= 30 else "  <-- MUESTRA INSUFICIENTE, es azar"
        print(f"{pct:>9.1%} {r.equity:>14,.2f} {cagr:>+7.2%} {r.drawdown:>8.1%} "
              f"{len(r.cerradas):>5} {quiebra:>9} {peor:>11} "
              f"US$ {(r.equity-CAPITAL)/dias:>6.3f}{aviso}")
    print("-" * 94)
    print()
    print("RUINA CON 36% DE ACIERTOS: probabilidad de N perdidas seguidas")
    print("-" * 62)
    p = 0.637   # probabilidad de perder una operacion, medida
    for n in (3, 5, 8, 10, 15):
        print(f"  {n:>2} perdidas seguidas: {p**n:>7.2%}  "
              f"-> con {100/n:>5.1f}% de riesgo por operacion, cuenta en cero")
    print()
    print("  Con 36% de aciertos, 8 perdidas seguidas pasan el 2,7% de las")
    print("  veces. No es un escenario raro: es un martes.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
