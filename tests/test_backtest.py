"""Pruebas del backtester con cifras calculadas A MANO.

Un backtester que nadie verifico es un generador de numeros bonitos.
Cada cifra esperada de este archivo esta calculada aparte, en el
comentario, para que el test falle si el motor cambia de criterio.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from labcore.backtest import (
    Backtester, Barra, LookAheadError, ModeloCostos, MotivoCierre, Senal,
    VentanaMercado,
)
from labcore.riesgo import InstrumentSpec, KillSwitch, RiskEngine, RiskLimits, Side

EURUSD = InstrumentSpec(
    symbol="EURUSD", contract_size=100_000, tick_size=0.00001,
    tick_value_account_ccy=1.0, min_volume=0.01, volume_step=0.01,
    margin_rate=0.01, correlation_group="USD_MAJOR",
)
UTC = timezone.utc


def barra(d: datetime, o, h, l, c, spread=0.00002, vol=1000.0) -> Barra:
    return Barra(ts=d, open=o, high=h, low=l, close=c, volume=vol, spread=spread)


@pytest.fixture
def motor_riesgo(tmp_path):
    return RiskEngine(RiskLimits(), KillSwitch(tmp_path / "ks.json"))


class UnaSolaSenal:
    """Senala comprar en la primera llamada y despues se calla."""

    strategy_id = "una-sola"

    def __init__(self, sl=0.00500, tp=0.01000, side=Side.BUY):
        self.llamadas = 0
        self.sl, self.tp, self.side = sl, tp, side

    def evaluar(self, v: VentanaMercado) -> Senal:
        self.llamadas += 1
        if self.llamadas == 1:
            return Senal(self.side, self.sl, self.tp, "primera barra")
        return Senal(None)


# ======================= 1. EL FUTURO ES INALCANZABLE =======================

def test_ventana_no_entrega_la_barra_siguiente():
    bs = [barra(datetime(2026, 1, 5, tzinfo=UTC) + timedelta(days=i),
                1.1, 1.1, 1.1, 1.1) for i in range(5)]
    v = VentanaMercado(bs, 2, "EURUSD")
    assert len(v) == 3
    assert v[-1] is bs[2]          # la ultima CERRADA
    with pytest.raises(LookAheadError):
        v[3]                        # la siguiente: prohibida
    with pytest.raises(LookAheadError):
        v[4]


def test_ventana_rechaza_slices():
    """Un slice es la via mas facil de filtrar el futuro sin darse cuenta."""
    bs = [barra(datetime(2026, 1, 5, tzinfo=UTC), 1.1, 1.1, 1.1, 1.1)] * 3
    with pytest.raises(TypeError):
        VentanaMercado(bs, 1, "EURUSD")[0:3]


def test_ultimas_nunca_devuelve_mas_de_lo_cerrado():
    bs = [barra(datetime(2026, 1, 5, tzinfo=UTC) + timedelta(days=i),
                1.1, 1.1, 1.1, 1.0 + i) for i in range(10)]
    v = VentanaMercado(bs, 3, "EURUSD")
    assert v.cierres(100) == (1.0, 2.0, 3.0, 4.0)   # 4, no 10
    assert v.ultimas(2)[-1] is bs[3]


def test_una_estrategia_fisgona_explota(motor_riesgo):
    class Fisgona:
        strategy_id = "fisgona"

        def evaluar(self, v):
            v[len(v)]               # intenta la barra siguiente
            return Senal(None)

    bs = [barra(datetime(2026, 1, 5, tzinfo=UTC) + timedelta(days=i),
                1.1, 1.11, 1.09, 1.1) for i in range(5)]
    bt = Backtester(EURUSD, ModeloCostos(), motor_riesgo)
    with pytest.raises(LookAheadError):
        bt.correr(bs, Fisgona())


# ================== 2. LA EJECUCION OCURRE EN LA BARRA SIGUIENTE ==================

def test_entra_a_la_apertura_de_la_siguiente_no_al_cierre_de_la_actual(motor_riesgo):
    d0 = datetime(2026, 1, 5, tzinfo=UTC)
    bs = [
        barra(d0,                      1.09000, 1.09100, 1.08900, 1.09000),
        barra(d0 + timedelta(days=1),  1.10000, 1.10100, 1.09900, 1.10050),
        barra(d0 + timedelta(days=2),  1.10050, 1.10200, 1.09800, 1.10100),
    ]
    bt = Backtester(EURUSD, ModeloCostos(), motor_riesgo)
    r = bt.correr(bs, UnaSolaSenal(tp=0.0))
    assert len(r.operaciones) == 1
    op = r.operaciones[0]
    # apertura de bs[1] = 1.10000, + medio spread (0.00001) = 1.10001.
    # NO 1.09000 (cierre de bs[0]) ni 1.10050 (cierre de bs[1]).
    assert op.precio_apertura == pytest.approx(1.10001, abs=1e-9)
    assert op.ts_apertura == bs[1].ts


# ================== 3. TAMANO: REDONDEA HACIA ABAJO, NUNCA PASA EL TOPE ==================

def test_volumen_calculado_a_mano(motor_riesgo):
    bt = Backtester(EURUSD, ModeloCostos(), motor_riesgo, capital_inicial=10_000.0)
    # riesgo 0,5% de 10.000 = 50 USD. Stop de 0,00500 = 500 ticks.
    # 1 lote mueve 500 ticks * 1 USD = 500 USD. 50/500 = 0,10 lotes exactos.
    assert bt._volumen_por_riesgo(10_000.0, 0.00500, 0.005) == pytest.approx(0.10)


def test_volumen_redondea_hacia_abajo(motor_riesgo):
    bt = Backtester(EURUSD, ModeloCostos(), motor_riesgo)
    # 50 / (333 ticks * 1) = 0,15015 lotes -> paso 0,01 -> 0,15, no 0,16.
    v = bt._volumen_por_riesgo(10_000.0, 0.00333, 0.005)
    assert v == pytest.approx(0.15)
    # y el riesgo resultante queda BAJO el tope, nunca encima
    assert (0.00333 / 0.00001) * 1.0 * v <= 50.0


# ================== 4. DESEMPATE PESIMISTA ==================

def test_si_la_barra_toca_stop_y_objetivo_gana_el_stop(motor_riesgo):
    d0 = datetime(2026, 1, 5, tzinfo=UTC)
    bs = [
        barra(d0,                     1.09000, 1.09100, 1.08900, 1.09000),
        barra(d0 + timedelta(days=1), 1.10000, 1.10100, 1.09900, 1.10050),
        # rango que abarca el stop (1,09501) Y el objetivo (1,11001)
        barra(d0 + timedelta(days=2), 1.10050, 1.12000, 1.09000, 1.11000),
    ]
    bt = Backtester(EURUSD, ModeloCostos(), motor_riesgo)
    r = bt.correr(bs, UnaSolaSenal())
    op = r.operaciones[0]
    assert op.motivo_cierre is MotivoCierre.STOP_LOSS
    # el stop esta en 1,09501, pero se SALE al bid: 1,09501 - 0,00001 = 1,09500
    assert op.precio_cierre == pytest.approx(1.09500, abs=1e-9)
    # perdida bruta = 501 ticks * 1 USD * 0,10 = -50,10
    assert op.pnl_bruto == pytest.approx(-50.10, abs=0.01)
    # OJO: el riesgo NOMINAL era 50,00 y la perdida REAL es 50,10. El medio
    # spread de salida se paga igual. El tope de riesgo del motor se calcula
    # sobre la distancia al stop y por eso subestima la perdida real en
    # medio spread por operacion. Esta anotado en el informe de limitaciones.
    assert op.riesgo_inicial == pytest.approx(50.0, abs=0.01)
    assert abs(op.pnl_bruto) > op.riesgo_inicial


# ================== 5. P&L NETO CALCULADO A MANO, CON LOS CUATRO COSTOS ==================

def test_pnl_neto_con_spread_comision_y_swap(motor_riesgo):
    # Fechas elegidas para que la noche NO sea miercoles.
    d1 = datetime(2026, 1, 5, tzinfo=UTC)   # lunes
    assert d1.weekday() == 0, "la prueba asume que el 5-ene-2026 es lunes"
    bs = [
        barra(d1,                     1.09000, 1.09100, 1.08900, 1.09000),
        barra(d1 + timedelta(days=1), 1.10000, 1.10100, 1.09900, 1.10050),  # martes
        barra(d1 + timedelta(days=2), 1.10050, 1.12000, 1.09600, 1.11500),  # miercoles
    ]
    costos = ModeloCostos(
        comision_por_lote_por_lado=3.50,
        slippage_ticks=0.0,
        swap_largo_por_lote_dia=-14.20,
    )
    bt = Backtester(EURUSD, costos, motor_riesgo, capital_inicial=10_000.0)
    r = bt.correr(bs, UnaSolaSenal())
    op = r.operaciones[0]

    # entrada  = 1,10000 + 0,00001 (medio spread, se compra al ask) = 1,10001
    # objetivo = 1,10001 + 0,01000 = 1,11001; el high de bs[2] (1,12000) lo toca
    # salida   = 1,11001 - 0,00001 (medio spread, se vende al bid)  = 1,11000
    # bruto    = 999 ticks * 1 USD * 0,10 lotes       =  +99,90
    # comision = 0,10 * 3,50 * 2 lados                =    0,70
    # swap     = 1 noche (mar->mie) * -14,20 * 0,10   =   -1,42
    # neto     = 99,90 - 0,70 - 1,42                  =   97,78
    assert op.motivo_cierre is MotivoCierre.TAKE_PROFIT
    assert op.precio_cierre == pytest.approx(1.11000, abs=1e-9)
    assert op.pnl_bruto == pytest.approx(99.90, abs=0.01)
    assert op.costo_comision == pytest.approx(0.70, abs=0.001)
    assert op.costo_swap == pytest.approx(-1.42, abs=0.001)
    assert op.pnl_neto == pytest.approx(97.78, abs=0.01)
    assert r.equity_final == pytest.approx(10_097.78, abs=0.01)


def test_el_slippage_siempre_va_en_contra(motor_riesgo):
    c = ModeloCostos(slippage_ticks=5.0)
    assert c.slippage_precio(0.00001, es_compra=True) == pytest.approx(0.00005)
    assert c.slippage_precio(0.00001, es_compra=False) == pytest.approx(-0.00005)


def test_swap_triple_del_miercoles():
    c = ModeloCostos(swap_largo_por_lote_dia=-10.0)
    mie = datetime(2026, 1, 7, tzinfo=UTC)
    assert mie.weekday() == 2, "la prueba asume que el 7-ene-2026 es miercoles"
    # una sola noche, y es la del miercoles: cuenta triple
    assert c.noches_de_swap(mie, mie + timedelta(days=1)) == pytest.approx(3.0)
    assert c.swap(1.0, True, mie, mie + timedelta(days=1)) == pytest.approx(-30.0)
    # un martes cuenta simple
    mar = mie - timedelta(days=1)
    assert c.noches_de_swap(mar, mar + timedelta(days=1)) == pytest.approx(1.0)


def test_misma_sesion_no_paga_swap():
    c = ModeloCostos(swap_largo_por_lote_dia=-10.0)
    t = datetime(2026, 1, 6, 10, tzinfo=UTC)
    assert c.swap(1.0, True, t, t + timedelta(hours=4)) == 0.0


def test_estres_de_spread_empeora_el_resultado(motor_riesgo, tmp_path):
    d1 = datetime(2026, 1, 5, tzinfo=UTC)
    bs = [
        barra(d1,                     1.09000, 1.09100, 1.08900, 1.09000),
        barra(d1 + timedelta(days=1), 1.10000, 1.10100, 1.09900, 1.10050),
        barra(d1 + timedelta(days=2), 1.10050, 1.12000, 1.09600, 1.11500),
    ]
    def correr(mult):
        m = RiskEngine(RiskLimits(), KillSwitch(tmp_path / f"ks{mult}.json"))
        bt = Backtester(EURUSD, ModeloCostos(multiplicador_spread=mult), m)
        return bt.correr(bs, UnaSolaSenal())
    normal = correr(1.0)
    estres = correr(5.0)
    assert estres.operaciones[0].pnl_neto < normal.operaciones[0].pnl_neto


# ================== 6. EL RESUMEN SE ACUSA A SI MISMO ==================

def test_sin_senales_el_resumen_lo_dice(motor_riesgo):
    class Muda:
        strategy_id = "muda"
        def evaluar(self, v):
            return Senal(None)

    d0 = datetime(2026, 1, 5, tzinfo=UTC)
    bs = [barra(d0 + timedelta(days=i), 1.1, 1.11, 1.09, 1.1) for i in range(6)]
    r = Backtester(EURUSD, ModeloCostos(), motor_riesgo).correr(bs, Muda())
    assert r.senales_generadas == 0
    assert "ATENCION" in r.resumen() and "NINGUNA senal" in r.resumen()


def test_senales_todas_vetadas_lo_dice_y_cuenta_los_codigos(motor_riesgo):
    """El caso peligroso: la estrategia funciona pero el riesgo veta todo.
    Sin este aviso se lee como 'no habia oportunidades'."""
    d0 = datetime(2026, 1, 5, tzinfo=UTC)
    bs = [barra(d0 + timedelta(days=i), 1.1, 1.11, 1.09, 1.1) for i in range(6)]
    motor_riesgo.kill_switch.activar("prueba: todo vetado")
    r = Backtester(EURUSD, ModeloCostos(), motor_riesgo).correr(bs, UnaSolaSenal())
    assert r.senales_generadas >= 1
    assert r.ordenes_vetadas >= 1
    assert r.operaciones == []
    assert "ATENCION" in r.resumen()
    assert r.vetos_por_codigo.get("KILL_SWITCH_ACTIVE", 0) >= 1


def test_lo_que_queda_abierto_se_cierra_no_flota_en_ganancia(motor_riesgo):
    d0 = datetime(2026, 1, 5, tzinfo=UTC)
    bs = [
        barra(d0,                     1.09000, 1.09100, 1.08900, 1.09000),
        barra(d0 + timedelta(days=1), 1.10000, 1.10100, 1.09900, 1.10050),
        # ni stop ni objetivo: la operacion sigue abierta al terminar los datos
        barra(d0 + timedelta(days=2), 1.10050, 1.10200, 1.09800, 1.10100),
    ]
    r = Backtester(EURUSD, ModeloCostos(), motor_riesgo).correr(bs, UnaSolaSenal())
    op = r.operaciones[0]
    assert not op.abierta
    assert op.motivo_cierre is MotivoCierre.FIN_DE_DATOS


def test_el_motor_de_riesgo_del_backtest_es_el_mismo_de_produccion(motor_riesgo):
    """Si el backtest usara reglas distintas, no estaria probando nada."""
    d0 = datetime(2026, 1, 5, tzinfo=UTC)
    bs = [barra(d0 + timedelta(days=i), 1.1, 1.11, 1.09, 1.1) for i in range(6)]
    bt = Backtester(EURUSD, ModeloCostos(), motor_riesgo)
    bt.correr(bs, UnaSolaSenal())
    assert motor_riesgo.evaluadas > 0
    assert "evaluadas=" in motor_riesgo.resumen()
