"""Pruebas de horarios y de la regla de intradia.

Las trampas de esta logica: el horario de verano, el fin de semana, los
feriados, y los minutos justo antes del cierre.
"""
from __future__ import annotations
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from labcore.horarios import (
    NY, bolsa_eeuu_abierta, debe_cerrar_todo, minutos_al_cierre, puede_abrir,
)


def ny(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=NY)


# ---------- la bolsa de EEUU ----------

def test_abierta_un_miercoles_al_mediodia():
    assert bolsa_eeuu_abierta(ny(2026, 11, 4, 12, 0))


@pytest.mark.parametrize("h,mi,esperado", [
    (9, 29, False),   # un minuto antes de abrir
    (9, 30, True),    # justo a la apertura
    (15, 59, True),   # un minuto antes de cerrar
    (16, 0, False),   # justo al cierre: ya cerrada
    (16, 1, False),
    (3, 0, False),
    (22, 0, False),
])
def test_los_bordes_de_la_sesion(h, mi, esperado):
    assert bolsa_eeuu_abierta(ny(2026, 11, 4, h, mi)) is esperado


def test_sabado_y_domingo_cerrada():
    assert not bolsa_eeuu_abierta(ny(2026, 10, 31, 12))   # sabado
    assert not bolsa_eeuu_abierta(ny(2026, 11, 1, 12))    # domingo


def test_feriado_cerrada():
    # Navidad 2026 cae viernes: dia de semana, pero feriado.
    assert ny(2026, 12, 25, 12).weekday() < 5
    assert not bolsa_eeuu_abierta(ny(2026, 12, 25, 12))


def test_el_horario_de_verano_NO_se_calcula_con_un_desplazamiento_fijo():
    """En noviembre EEUU vuelve al horario de invierno. Las 14:00 UTC son
    las 10:00 NY en verano (abierta) y las 09:00 NY en invierno (cerrada).
    Una constante en UTC se equivoca una hora durante semanas."""
    verano = datetime(2026, 10, 15, 13, 45, tzinfo=timezone.utc)
    invierno = datetime(2026, 11, 15, 13, 45, tzinfo=timezone.utc)
    assert verano.astimezone(NY).hour == 9 and verano.astimezone(NY).minute == 45
    assert invierno.astimezone(NY).hour == 8 and invierno.astimezone(NY).minute == 45
    assert bolsa_eeuu_abierta(verano)        # 09:45 NY -> abierta
    assert not bolsa_eeuu_abierta(invierno)  # 08:45 NY -> cerrada


# ---------- la regla de INTRADIA ----------

def test_no_se_abre_una_accion_con_la_bolsa_cerrada():
    ok, por = puede_abrir("EQUITY_US", ny(2026, 11, 4, 20))
    assert not ok and "cerrada" in por.lower()


def test_no_se_abre_una_accion_cerca_del_cierre():
    """Abrir a las 15:50 es abrir para cerrar a la fuerza 10 min despues."""
    ok, por = puede_abrir("EQUITY_US", ny(2026, 11, 4, 15, 50))
    assert not ok and "cierre" in por


def test_si_se_abre_una_accion_con_tiempo_de_sobra():
    ok, _ = puede_abrir("EQUITY_US", ny(2026, 11, 4, 11))
    assert ok


def test_la_cripto_se_puede_abrir_el_fin_de_semana():
    """24/7: es lo unico que opera sabado y domingo."""
    ok, _ = puede_abrir("CRYPTO", ny(2026, 10, 31, 3))
    assert ok


def test_las_divisas_NO_operan_el_fin_de_semana():
    assert not puede_abrir("FOREX", ny(2026, 10, 31, 12))[0]      # sabado
    assert not puede_abrir("FOREX", ny(2026, 11, 1, 12))[0]       # domingo 12:00
    assert puede_abrir("FOREX", ny(2026, 11, 1, 18))[0]           # domingo 18:00
    assert not puede_abrir("FOREX", ny(2026, 10, 30, 18))[0]      # viernes 18:00


# ---------- el cierre forzoso ----------

def test_una_accion_se_cierra_antes_del_cierre_de_la_bolsa():
    cerrar, por = debe_cerrar_todo("EQUITY_US", ny(2026, 11, 4, 15, 55))
    assert cerrar and "cierre" in por


def test_una_accion_abierta_con_la_bolsa_cerrada_se_denuncia():
    cerrar, por = debe_cerrar_todo("EQUITY_US", ny(2026, 11, 4, 20))
    assert cerrar and "cerrada" in por


def test_la_cripto_se_cierra_antes_del_rollover_de_las_17():
    assert not debe_cerrar_todo("CRYPTO", ny(2026, 11, 4, 14))[0]
    assert debe_cerrar_todo("CRYPTO", ny(2026, 11, 4, 16, 55))[0]


def test_la_ventana_de_cierre_es_ESTRECHA():
    """Corregido el 2026-10-30. La version vieja decia "cerrar todo despues
    de las 16:50" para toda la tarde, y eso bloqueaba la apertura de la
    semana: las divisas abren el domingo a las 17:00 NY. Con la invariante
    puesta, el domingo a las 18:00 no se podia abrir -- se perdia la semana.

    Solo hay que cerrar en los 10 minutos previos al rollover."""
    assert debe_cerrar_todo("CRYPTO", ny(2026, 11, 4, 16, 50))[0]
    assert debe_cerrar_todo("CRYPTO", ny(2026, 11, 4, 16, 59))[0]
    # despues del rollover empieza un dia nuevo: ya no hay que cerrar
    assert not debe_cerrar_todo("CRYPTO", ny(2026, 11, 4, 17, 0))[0]
    assert not debe_cerrar_todo("CRYPTO", ny(2026, 11, 4, 18, 0))[0]
    # y el domingo por la tarde, cuando abre la semana de divisas
    assert puede_abrir("FOREX", ny(2026, 11, 1, 18, 0))[0]


def test_el_tope_de_horas_cierra_una_posicion_vieja():
    """La ambiguedad de 'intradia' se resuelve con un tope de HORAS, no
    eligiendo una definicion de 'dia'. Asi se cumple en espiritu con
    cualquiera."""
    from datetime import timedelta, timezone as tz
    ahora = ny(2026, 11, 4, 12, 0)
    joven = ahora - timedelta(hours=2)
    vieja = ahora - timedelta(hours=9)
    assert not debe_cerrar_todo("CRYPTO", ahora, abierta_en=joven)[0]
    cerrar, por = debe_cerrar_todo("CRYPTO", ahora, abierta_en=vieja)
    assert cerrar and "tope" in por


def test_el_tope_de_horas_aplica_aunque_el_mercado_este_abierto():
    from datetime import timedelta
    ahora = ny(2026, 11, 4, 11, 0)
    assert debe_cerrar_todo("EQUITY_US", ahora,
                            abierta_en=ahora - timedelta(hours=8.5))[0]


def test_minutos_al_cierre_es_None_si_esta_cerrada():
    assert minutos_al_cierre(ny(2026, 11, 4, 20)) is None
    assert minutos_al_cierre(ny(2026, 11, 4, 15, 30)) == pytest.approx(30, abs=1)


# ---------- la invariante que se violo ----------

@pytest.mark.parametrize("grupo", ["CRYPTO", "EQUITY_US", "FOREX"])
@pytest.mark.parametrize("h,mi", [
    (3, 0), (9, 0), (9, 31), (12, 0), (15, 45), (15, 55),
    (16, 30), (16, 50), (16, 55), (17, 0), (18, 0), (23, 59),
])
def test_si_hay_que_cerrar_NO_se_puede_abrir(grupo, h, mi):
    """LA INVARIANTE. Si se violan, el sistema abre y cierra en la pasada
    siguiente perdiendo el spread cada vez. Paso de verdad el 2026-10-30:
    tres operaciones reales se fueron en -0,15, -0,35 y -0,84."""
    for dia in (ny(2026, 11, 4, h, mi), ny(2026, 10, 31, h, mi),
                ny(2026, 11, 1, h, mi)):
        cerrar, _ = debe_cerrar_todo(grupo, dia)
        abrir, motivo = puede_abrir(grupo, dia)
        if cerrar:
            assert not abrir, (
                f"{grupo} {dia:%a %H:%M}: hay que cerrar Y deja abrir")


def test_la_cripto_NO_se_abre_en_la_ventana_de_cierre():
    """El caso exacto que fallo y costo tres operaciones reales: cripto
    opera 24/7, pero en los 10 min previos al rollover ya toca cerrar, asi
    que abrir ahi es abrir para cerrar en la pasada siguiente."""
    ok, motivo = puede_abrir("CRYPTO", ny(2026, 11, 4, 16, 55))
    assert not ok and "cerrar" in motivo
    # fuera de esa ventana si se abre
    assert puede_abrir("CRYPTO", ny(2026, 11, 4, 17, 30))[0]


def test_la_cripto_SI_se_abre_en_horario_normal():
    assert puede_abrir("CRYPTO", ny(2026, 11, 4, 10, 0))[0]
    assert puede_abrir("CRYPTO", ny(2026, 11, 4, 2, 0))[0]
    # y el fin de semana, que es cuando es lo unico que opera
    assert puede_abrir("CRYPTO", ny(2026, 10, 31, 10, 0))[0]
