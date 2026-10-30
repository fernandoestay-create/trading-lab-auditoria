"""Restricciones estructurales que no son bugs, son limites del contrato.

Se fijan en pruebas para que si alguien cambia capital, lote minimo o
limite de riesgo, se entere en el momento y no por un benchmark que
aparece con cero operaciones.
"""

from __future__ import annotations

import pytest

from labcore.backtest import Backtester, ModeloCostos
from labcore.riesgo import InstrumentSpec, KillSwitch, RiskEngine, RiskLimits

EURUSD = InstrumentSpec(
    symbol="EURUSD", contract_size=100_000, tick_size=0.00001,
    tick_value_account_ccy=1.0, min_volume=0.01, volume_step=0.01,
    margin_rate=0.01, correlation_group="USD_MAJOR",
)


@pytest.fixture
def bt(tmp_path):
    m = RiskEngine(RiskLimits(), KillSwitch(tmp_path / "ks.json"))
    return Backtester(EURUSD, ModeloCostos(), m, capital_inicial=10_000.0)


def test_el_stop_mas_ancho_operable_son_5000_ticks(bt):
    """Con 10.000 USD y 0,5% de riesgo, el lote minimo fija el stop maximo.

    50 USD de riesgo / 0,01 lotes = 5.000 USD por lote = 5.000 ticks.
    Mas ancho que eso y el tamano cae bajo el minimo del contrato.
    """
    justo = 5_000 * EURUSD.tick_size          # 0,05000
    assert bt._volumen_por_riesgo(10_000.0, justo, 0.005) >= EURUSD.min_volume
    demasiado = 5_100 * EURUSD.tick_size      # 0,05100
    assert bt._volumen_por_riesgo(10_000.0, demasiado, 0.005) < EURUSD.min_volume


def test_una_senal_imposible_de_dimensionar_se_cuenta_y_se_denuncia(bt):
    """No puede verse igual que "no hubo oportunidades"."""
    from datetime import datetime, timedelta, timezone

    from labcore.backtest import Barra, Senal
    from labcore.riesgo import Side

    class StopAbsurdo:
        strategy_id = "stop-absurdo"
        barras_minimas = 2

        def evaluar(self, v):
            return Senal(Side.BUY, 1.0, 2.0, "stop de 100.000 ticks")

    d0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
    bs = [Barra(d0 + timedelta(days=i), 1.1, 1.11, 1.09, 1.1, 1000.0, 0.00002)
          for i in range(6)]
    r = bt.correr(bs, StopAbsurdo())
    assert r.senales_generadas > 0
    assert r.senales_sin_orden == r.senales_generadas
    assert r.operaciones == []
    assert "NINGUNA senal pudo convertirse en orden" in r.resumen()
    assert any("VOLUMEN_BAJO_EL_MINIMO" in k for k in r.sin_orden_por_motivo)


def test_la_pasiva_SI_opera_con_la_configuracion_actual(bt, tmp_path):
    """Un benchmark que no opera no es vara de nada."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from prueba_de_potencia import serie_con_momentum

    from labcore.estrategias import ComprarYMantener

    e = ComprarYMantener()
    m = RiskEngine(RiskLimits(), KillSwitch(tmp_path / "ks2.json"))
    b = Backtester(EURUSD, ModeloCostos(), m, 10_000.0,
                   barras_minimas=e.barras_minimas)
    r = b.correr(serie_con_momentum(500, 11), e)
    assert r.senales_generadas == 1
    assert len(r.operaciones) == 1, r.resumen()
