"""Que pasa si subo el apalancamiento? Medido, no opinado.

Corre la MISMA cartera sobre los MISMOS datos reales variando solo el
apalancamiento maximo. Todo lo demas identico: instrumentos, estrategias,
periodo, costos, riesgo por operacion.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.simplefilter("ignore")
import logging
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

from labcore.backtest import ModeloCostos
from labcore.backtest.cartera_multi import SimuladorCartera
from labcore.datos import INSTRUMENTOS, a_barras, descargar, validar
from labcore.estrategias import CruceMedias, RupturaDeRango
from labcore.riesgo import InstrumentSpec, KillSwitch, RiskEngine, RiskLimits

CAPITAL = 2000.0


def ests():
    return [RupturaDeRango(20), RupturaDeRango(55), CruceMedias(20, 50)]


def main() -> int:
    print(f"CARTERA REAL, US$ {CAPITAL:,.0f}, variando SOLO el apalancamiento")
    print("Mismos instrumentos, estrategias, periodo y costos.")
    print()
    mercados = {}
    for sim, cfg in INSTRUMENTOS.items():
        if cfg["grupo"] not in ("CRYPTO", "METALS", "ENERGY", "EQUITY_US"):
            continue
        try:
            d, v = validar(sim, descargar(sim))
        except Exception:
            continue
        if not v.usable:
            continue
        mercados[cfg["nombre"]] = (
            a_barras(d, cfg["spread"]),
            InstrumentSpec(
                symbol=cfg["nombre"], contract_size=cfg["contrato"],
                tick_size=cfg["tick"],
                tick_value_account_ccy=cfg["valor_tick"],
                min_volume=0.01, volume_step=0.01, margin_rate=0.01,
                correlation_group=cfg["grupo"]))
    print(f"instrumentos: {len(mercados)} -> {', '.join(sorted(mercados))}")
    bar = min(len(b) for b, _ in mercados.values())
    print(f"barras diarias (el mas corto): {bar}")
    print()
    print("=" * 86)
    print(f"{'apalanc':>8} {'equity final':>14} {'retorno':>9} {'drawdown':>9} "
          f"{'ops':>5} {'aciertos':>9} {'vetadas':>8} {'max visto':>10}")
    print("-" * 86)

    filas = []
    for lev in (1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0):
        lim = RiskLimits(
            apalancamiento_maximo=lev, max_open_positions=10,
            per_trade_risk_pct=0.005, daily_loss_limit_pct=0.02,
            max_drawdown_pct=0.10)
        import tempfile
        ks = KillSwitch(Path(tempfile.mkdtemp()) / "k.json")
        ks.desactivar()
        s = SimuladorCartera(
            ModeloCostos(slippage_ticks=1.0), lim,
            RiskEngine(lim, ks), capital_inicial=CAPITAL)
        r = s.correr(mercados, ests)
        n = len(r.cerradas)
        gan = sum(1 for o in r.cerradas if o.pnl_neto > 0)
        print(f"{lev:>7.0f}x {r.equity:>14,.2f} {r.retorno_pct:>+8.1%} "
              f"{r.drawdown:>8.1%} {n:>5} "
              f"{(gan/n if n else 0):>8.1%} {r.vetadas:>8} "
              f"{r.max_apalancamiento_visto:>9.2f}x")
        filas.append((lev, r))

    print("-" * 86)
    print()
    print("RIESGO DE RUINA: que movimiento en contra te deja en cero")
    print("-" * 56)
    for lev in (1, 2, 5, 10, 20, 50, 100):
        print(f"  {lev:>4}x -> un movimiento adverso de "
              f"{100/lev:>5.1f}% borra la cuenta")
    print()
    print("  Referencia medida: BTC se mueve mas de 5% en un dia con")
    print("  frecuencia. A 20x o mas, un dia normal te liquida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
