"""Pruebas de las estrategias de aprendizaje automatico.

Lo que se prueba no es que acierten: es que NO VEAN EL FUTURO. Un modelo
con fuga de datos acierta magnificamente y no sirve para nada.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from labcore.backtest.mercado import Barra, LookAheadError, VentanaMercado
from labcore.estrategias import EstrategiaML, caracteristicas, catalogo_ml

UTC = timezone.utc


def serie(n=1200, semilla=3):
    rng = np.random.default_rng(semilla)
    d0 = datetime(2015, 1, 1, tzinfo=UTC)
    bs, p = [], 100.0
    for i in range(n):
        c = p * float(np.exp(rng.normal(0, 0.012)))
        r = abs(rng.normal(0, 0.006)) * p
        bs.append(Barra(d0 + timedelta(days=i), p, max(p, c) + r/2,
                        min(p, c) - r/2, c, 1000.0, c * 0.0002))
        p = c
    return bs


# ---------- el futuro sigue siendo inalcanzable ----------

def test_tramo_rechaza_el_futuro():
    bs = serie(100)
    v = VentanaMercado(bs, 50, "X")
    assert len(v.tramo(40, 50)) == 11
    with pytest.raises(LookAheadError):
        v.tramo(40, 51)
    with pytest.raises(LookAheadError):
        v.tramo(-1, 50)


def test_las_caracteristicas_no_miran_mas_alla_de_i():
    """Mismo i, series con futuros DISTINTOS -> mismas caracteristicas.
    Si el futuro influyera, los vectores diferirian."""
    a = serie(400, semilla=1)
    b = list(a[:200]) + serie(400, semilla=99)[200:]   # mismo pasado, otro futuro
    fa = caracteristicas(VentanaMercado(a, 150, "X"), 150)
    fb = caracteristicas(VentanaMercado(b, 150, "X"), 150)
    assert fa is not None and fb is not None
    assert np.allclose(fa, fb)


def test_sin_historia_suficiente_devuelve_None():
    """Una fila rellenada con ceros es peor que ninguna fila."""
    v = VentanaMercado(serie(100), 10, "X")
    assert caracteristicas(v, 10, n_hist=60) is None


def test_la_estrategia_se_calla_hasta_tener_para_entrenar():
    cat = catalogo_ml()
    e = EstrategiaML("logistica", cat["logistica"], entrenar_con=300,
                     reentrenar_cada=100, n_hist=60)
    bs = serie(1200)
    for i in (100, 200, 350):
        assert e.evaluar(VentanaMercado(bs, i, "X")).side is None


def test_el_entrenamiento_nunca_toca_la_barra_que_predice():
    """La prueba central: se registra el indice maximo que pidio el
    modelo y tiene que ser <= el ultimo cerrado."""
    bs = serie(1200)
    pedidos: list[int] = []

    class Espia(VentanaMercado):
        def tramo(self, desde, hasta):
            pedidos.append(hasta)
            return super().tramo(desde, hasta)

    cat = catalogo_ml()
    e = EstrategiaML("logistica", cat["logistica"], entrenar_con=400,
                     reentrenar_cada=1000, n_hist=60)
    i = 900
    e.evaluar(Espia(bs, i, "X"))
    assert pedidos, "la estrategia no pidio ninguna barra"
    assert max(pedidos) <= i, f"pidio la barra {max(pedidos)} con i={i}"


@pytest.mark.parametrize("nombre", ["logistica", "bosque", "gradiente"])
def test_los_tres_modelos_entrenan_y_predicen(nombre):
    cat = catalogo_ml()
    e = EstrategiaML(nombre, cat[nombre], entrenar_con=400,
                     reentrenar_cada=1000, n_hist=60)
    s = e.evaluar(VentanaMercado(serie(1200), 900, "X"))
    assert s.side is None or s.side.value in ("BUY", "SELL")
    assert e._fallos == 0


def test_un_modelo_que_explota_no_opera():
    """Deniega por defecto: si el modelo falla, no hay senal."""
    class Roto:
        def fit(self, X, y): raise RuntimeError("fallo inyectado")
    e = EstrategiaML("roto", lambda: Roto(), entrenar_con=400,
                     reentrenar_cada=1000, n_hist=60)
    assert e.evaluar(VentanaMercado(serie(1200), 900, "X")).side is None
    assert e._fallos >= 1
