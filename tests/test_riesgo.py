"""Pruebas del motor de riesgo.

Lo que se prueba no es que apruebe: es que RECHACE cuando corresponde.
Un motor de riesgo que aprueba todo pasa cualquier prueba mal escrita.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from labcore.riesgo import (
    AccountState, InstrumentSpec, KillSwitch, OpenPosition, ProposedOrder,
    Quote, RejectCode, RiskEngine, RiskLimits, Side, riesgo_por_operacion,
)

AHORA = lambda: datetime.now(timezone.utc)  # noqa: E731

# EURUSD con cuenta en USD: 1 lote = 100.000 EUR, tick 0,00001 = 1 USD
EURUSD = InstrumentSpec(
    symbol="EURUSD", contract_size=100_000, tick_size=0.00001,
    tick_value_account_ccy=1.0, min_volume=0.01, volume_step=0.01,
    margin_rate=0.01, correlation_group="USD_MAJOR",
)


def quote(bid=1.08000, ask=1.08002, edad_s=0.0, mediana=0.00002, atr=0.0040):
    return Quote(
        symbol="EURUSD", bid=bid, ask=ask,
        ts=AHORA() - timedelta(seconds=edad_s),
        median_spread=mediana, atr=atr,
    )


def cuenta(**kw):
    base = dict(
        equity=10_000.0, balance=10_000.0, free_margin=9_000.0,
        used_margin=1_000.0, peak_equity=10_000.0, realized_pnl_today=0.0,
    )
    base.update(kw)
    return AccountState(**base)


def orden(**kw):
    base = dict(
        client_order_id="abc-1", symbol="EURUSD", side=Side.BUY, volume=0.09,
        reference_price=1.08002, stop_loss=1.07500, strategy_id="prueba",
    )
    base.update(kw)
    return ProposedOrder(**base)


@pytest.fixture
def motor(tmp_path):
    # Kill switch aislado por prueba: nunca el del sistema.
    return RiskEngine(RiskLimits(), KillSwitch(tmp_path / "ks.json"))


# ---------- el camino feliz tiene que existir, si no el resto no prueba nada ----------

def test_la_orden_por_defecto_del_fixture_es_legal():
    """Si el fixture base fuera ilegal, los demas test pasarian por accidente."""
    assert riesgo_por_operacion(orden(), EURUSD) / 10_000 < 0.005


def test_orden_sana_se_aprueba(motor):
    d = motor.evaluar(orden(), cuenta(), EURUSD, quote())
    assert d.approved, d.reason_text


def test_riesgo_calculado_coincide_con_la_aritmetica():
    # 502 pips de 0,00001 -> 502 ticks * 1 USD * 0,10 lotes = 50,2 USD
    r = riesgo_por_operacion(orden(volume=0.10), EURUSD)
    assert r == pytest.approx(50.2, abs=0.01)
    # y 50,2 sobre 10.000 es 0,502%, justo sobre el tope de 0,5%
    assert r / 10_000 > 0.005


def test_riesgo_sobre_el_tope_se_rechaza(motor):
    # 0,10 lotes arriesgan 0,502%: dos milesimas sobre el tope, tiene que caer
    d = motor.evaluar(orden(volume=0.10), cuenta(), EURUSD, quote())
    assert not d.approved
    assert RejectCode.PER_TRADE_RISK_EXCEEDED in d.rejects


# ---------- cada regla, por separado ----------

def test_sin_stop_loss_se_rechaza(motor):
    d = motor.evaluar(orden(stop_loss=None), cuenta(), EURUSD, quote())
    assert RejectCode.MISSING_STOP_LOSS in d.rejects


def test_stop_del_lado_equivocado_se_rechaza(motor):
    d = motor.evaluar(orden(stop_loss=1.09000), cuenta(), EURUSD, quote())
    assert RejectCode.STOP_ON_WRONG_SIDE in d.rejects


def test_stop_del_lado_equivocado_en_venta(motor):
    d = motor.evaluar(
        orden(side=Side.SELL, stop_loss=1.07500), cuenta(), EURUSD, quote()
    )
    assert RejectCode.STOP_ON_WRONG_SIDE in d.rejects


def test_perdida_diaria_alcanzada_corta(motor):
    d = motor.evaluar(orden(), cuenta(realized_pnl_today=-200.0), EURUSD, quote())
    assert RejectCode.DAILY_LOSS_LIMIT_HIT in d.rejects


def test_perdida_diaria_justo_bajo_el_tope_pasa(motor):
    d = motor.evaluar(orden(), cuenta(realized_pnl_today=-199.0), EURUSD, quote())
    assert RejectCode.DAILY_LOSS_LIMIT_HIT not in d.rejects


def test_drawdown_de_suspension_corta(motor):
    d = motor.evaluar(
        orden(), cuenta(equity=9_000.0, peak_equity=10_000.0), EURUSD, quote()
    )
    assert RejectCode.MAX_DRAWDOWN_HIT in d.rejects


def test_cotizacion_vieja_se_rechaza(motor):
    d = motor.evaluar(orden(), cuenta(), EURUSD, quote(edad_s=30))
    assert RejectCode.QUOTE_STALE in d.rejects


def test_cotizacion_del_futuro_tambien_se_rechaza(motor):
    # reloj desincronizado: no se asume que esta bien
    d = motor.evaluar(orden(), cuenta(), EURUSD, quote(edad_s=-30))
    assert RejectCode.QUOTE_STALE in d.rejects


def test_spread_abierto_se_rechaza(motor):
    # spread de 0,00020 contra una mediana de 0,00002 = 10x
    d = motor.evaluar(
        orden(reference_price=1.08020), cuenta(), EURUSD, quote(ask=1.08020)
    )
    assert RejectCode.SPREAD_ANOMALOUS in d.rejects


def test_sin_mediana_de_spread_no_se_asume_normal(motor):
    """'No pude mirar' no es 'no habia nada'."""
    d = motor.evaluar(orden(), cuenta(), EURUSD, quote(mediana=None))
    assert RejectCode.SPREAD_ANOMALOUS in d.rejects


def test_orden_duplicada_se_rechaza(motor):
    c = cuenta(recent_client_order_ids=frozenset({"abc-1"}))
    d = motor.evaluar(orden(), c, EURUSD, quote())
    assert RejectCode.DUPLICATE_ORDER in d.rejects


def test_mercado_cerrado_se_rechaza(motor):
    d = motor.evaluar(orden(), cuenta(market_open=False), EURUSD, quote())
    assert RejectCode.MARKET_CLOSED in d.rejects


def test_tope_de_posiciones_simultaneas(motor):
    pos = tuple(
        OpenPosition("EURUSD", Side.BUY, 0.01, 1.08, 1.07, "USD_MAJOR")
        for _ in range(3)
    )
    d = motor.evaluar(orden(), cuenta(open_positions=pos), EURUSD, quote())
    assert RejectCode.MAX_OPEN_POSITIONS in d.rejects


def test_margen_libre_insuficiente(motor):
    d = motor.evaluar(orden(), cuenta(free_margin=10.0), EURUSD, quote())
    assert RejectCode.INSUFFICIENT_FREE_MARGIN in d.rejects


def test_volumen_fuera_del_paso_del_contrato(motor):
    d = motor.evaluar(orden(volume=0.007), cuenta(), EURUSD, quote())
    assert RejectCode.SIZE_BELOW_MINIMUM in d.rejects


def test_volumen_no_multiplo_del_paso(motor):
    d = motor.evaluar(orden(volume=0.015, stop_loss=1.07900), cuenta(), EURUSD, quote())
    assert RejectCode.SIZE_NOT_ON_STEP in d.rejects


# ---------- kill switch ----------

def test_kill_switch_bloquea_todo(tmp_path):
    ks = KillSwitch(tmp_path / "ks.json")
    ks.activar("prueba de corte", por="pytest")
    m = RiskEngine(RiskLimits(), ks)
    d = m.evaluar(orden(), cuenta(), EURUSD, quote())
    assert not d.approved
    assert d.rejects == [RejectCode.KILL_SWITCH_ACTIVE]


def test_kill_switch_sobrevive_al_reinicio(tmp_path):
    ruta = tmp_path / "ks.json"
    KillSwitch(ruta).activar("corte por drawdown")
    # otra instancia, como si el proceso se hubiera reiniciado
    assert KillSwitch(ruta).activo() is True


def test_kill_switch_corrupto_se_asume_cortado(tmp_path):
    ruta = tmp_path / "ks.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("{esto no es json", encoding="utf-8")
    assert KillSwitch(ruta).activo() is True


def test_kill_switch_se_puede_desactivar(tmp_path):
    ks = KillSwitch(tmp_path / "ks.json")
    ks.activar("x")
    ks.desactivar(por="fernando")
    assert ks.activo() is False


# ---------- comportamiento ante basura ----------

@pytest.mark.parametrize(
    "kw",
    [
        {"volume": 0.0},
        {"volume": -0.1},
        {"volume": float("nan")},
        {"reference_price": 0.0},
        {"reference_price": float("inf")},
        {"symbol": "XAUUSD"},
    ],
)
def test_entradas_invalidas_se_rechazan(motor, kw):
    d = motor.evaluar(orden(**kw), cuenta(), EURUSD, quote())
    assert not d.approved
    assert RejectCode.INVALID_INPUT in d.rejects


def test_equity_cero_no_divide_por_cero(motor):
    d = motor.evaluar(orden(), cuenta(equity=0.0), EURUSD, quote())
    assert not d.approved


def test_una_excepcion_dentro_de_una_regla_rechaza(motor, monkeypatch):
    """Deniega por defecto: si el motor se cae, NO aprueba."""
    def explota(*a, **k):
        raise RuntimeError("fallo inyectado")

    monkeypatch.setattr("labcore.riesgo.motor.riesgo_por_operacion", explota)
    d = motor.evaluar(orden(), cuenta(), EURUSD, quote())
    assert not d.approved
    assert RejectCode.INVALID_INPUT in d.rejects


# ---------- el resumen tiene que delatar el fallo silencioso ----------

def test_resumen_informa_pareja_y_se_acusa_a_si_mismo(motor):
    for _ in range(3):
        motor.evaluar(orden(stop_loss=None), cuenta(), EURUSD, quote())
    r = motor.resumen()
    assert "evaluadas=3" in r and "aprobadas=0" in r
    assert "ATENCION" in r


# ---------- el agujero del P&L no realizado (cerrado 2026-10-29) ----------

def test_perdida_diaria_NO_REALIZADA_tambien_corta(motor):
    """El agujero: con posiciones abiertas sangrando, el corte del 2% no
    se disparaba porque solo se miraba lo cerrado."""
    c = cuenta(realized_pnl_today=0.0, unrealized_pnl=-250.0)
    d = motor.evaluar(orden(), c, EURUSD, quote())
    assert RejectCode.DAILY_LOSS_LIMIT_HIT in d.rejects
    assert d.detail["perdida_dia_no_realizada"] == -250.0


def test_realizado_y_no_realizado_se_SUMAN(motor):
    """Ni -150 ni -100 pasan el 2% por separado; juntos si."""
    solo_real = motor.evaluar(
        orden(), cuenta(realized_pnl_today=-150.0), EURUSD, quote())
    assert RejectCode.DAILY_LOSS_LIMIT_HIT not in solo_real.rejects
    solo_abierto = motor.evaluar(
        orden(), cuenta(unrealized_pnl=-100.0), EURUSD, quote())
    assert RejectCode.DAILY_LOSS_LIMIT_HIT not in solo_abierto.rejects
    juntos = motor.evaluar(
        orden(), cuenta(realized_pnl_today=-150.0, unrealized_pnl=-100.0),
        EURUSD, quote())
    assert RejectCode.DAILY_LOSS_LIMIT_HIT in juntos.rejects


def test_el_drawdown_cuenta_lo_abierto(motor):
    """Un broker real te llama a margen por el patrimonio, no por lo
    realizado. El drawdown del 10% tiene que verlo igual."""
    c = cuenta(equity=10_000.0, peak_equity=10_000.0, unrealized_pnl=-1_100.0)
    d = motor.evaluar(orden(), c, EURUSD, quote())
    assert RejectCode.MAX_DRAWDOWN_HIT in d.rejects
    assert d.detail["drawdown_pct"] >= 0.10


def test_el_tope_por_operacion_usa_el_patrimonio_EFECTIVO(motor):
    """Si ya vas perdiendo en lo abierto, el 0,5% se calcula sobre lo que
    de verdad tienes, no sobre el saldo contable."""
    # 0,09 lotes arriesgan 45,18. Con equity efectivo de 8.000, el tope
    # son 40,00 -> tiene que caer. Con 10.000 pasaba.
    sano = motor.evaluar(orden(), cuenta(), EURUSD, quote())
    assert RejectCode.PER_TRADE_RISK_EXCEEDED not in sano.rejects
    apretado = motor.evaluar(
        orden(), cuenta(unrealized_pnl=-2_000.0), EURUSD, quote())
    assert RejectCode.PER_TRADE_RISK_EXCEEDED in apretado.rejects


def test_ganancia_no_realizada_no_regala_margen_de_perdida(motor):
    """Simetria: si lo abierto GANA, el patrimonio efectivo sube y el
    corte diario no se gatilla. Es correcto, pero hay que verificarlo."""
    c = cuenta(realized_pnl_today=-250.0, unrealized_pnl=+150.0)
    d = motor.evaluar(orden(), c, EURUSD, quote())
    # -250 +150 = -100 sobre 10.000 = 1%, bajo el 2%
    assert RejectCode.DAILY_LOSS_LIMIT_HIT not in d.rejects
