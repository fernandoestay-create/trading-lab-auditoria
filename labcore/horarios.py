"""Horarios de mercado y la regla de INTRADIA.

Dos reglas de Fernando, del 2026-10-30:

  1. SIEMPRE intradia. Ninguna posicion pasa de un dia para otro.
     Consecuencia feliz: si nunca se mantiene de un dia al otro, el swap
     NO se cobra nunca -- y la ambiguedad de 100x en swap_long (si esta
     en moneda o en puntos) deja de importar. La restriccion elimina la
     incertidumbre en vez de tener que medirla.

  2. Acciones e indices SOLO con la bolsa abierta. Nada con bolsa cerrada.
     Operar un CFD de accion fuera de hora significa spreads anchos y
     ejecucion mala, cuando se puede operar.

El horario de la bolsa de EEUU se calcula con zona horaria real
(America/New_York), no con un desplazamiento fijo: en noviembre y marzo
cambia el horario de verano y una constante en UTC se equivoca una hora
durante semanas.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

# TOPE DE TIEMPO EN POSICION. Resuelve una ambiguedad real de la regla de
# Fernando ("siempre intradia, nada que pase de un dia"):
#
#   El "dia" del broker termina en el rollover de las 17:00 NY, no a
#   medianoche. Una posicion abierta a las 18:00 y cerrada al dia
#   siguiente a las 16:50 NO cruza ningun rollover y NO paga swap -- pero
#   dura 23 horas y en calendario cruza la medianoche.
#
# En vez de elegir una definicion de "dia" y defenderla, se pone un tope
# de HORAS. Asi la regla se cumple en espiritu con cualquier definicion:
# ninguna posicion dura mucho, sin importar a que hora se abrio.
MAX_HORAS_EN_POSICION = 8.0
APERTURA_NY = time(9, 30)
CIERRE_NY = time(16, 0)

# Minutos antes del cierre a partir de los cuales ya no se ABRE nada.
# Abrir a las 15:58 es abrir para cerrar a la fuerza dos minutos despues.
MARGEN_NO_ABRIR_MIN = 30
# Minutos antes del cierre en que se CIERRA todo lo que quede abierto.
MARGEN_CERRAR_MIN = 10

# Feriados de la bolsa de EEUU. Lista PARCIAL y declarada como tal: si
# falta uno, el sistema creera que el mercado esta abierto y las ordenes
# seran rechazadas por el broker (MARKET_SESSION_CLOSED), que es un fallo
# visible y no una perdida. Se amplia cuando aparezca alguno.
FERIADOS_EEUU = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16),
    date(2026, 4, 3), date(2026, 5, 25), date(2026, 6, 19),
    date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26),
    date(2026, 12, 25),
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15),
    date(2027, 3, 26), date(2027, 5, 31), date(2027, 6, 18),
    date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25),
    date(2027, 12, 24),
}

# Grupos que dependen del horario de la bolsa de EEUU.
GRUPOS_BOLSA = {"EQUITY_US", "INDEX_US"}
# Grupos que operan 24/7.
GRUPOS_CONTINUOS = {"CRYPTO"}


def _ahora_ny(ahora: datetime | None = None) -> datetime:
    return (ahora or datetime.now(timezone.utc)).astimezone(NY)


def bolsa_eeuu_abierta(ahora: datetime | None = None) -> bool:
    n = _ahora_ny(ahora)
    if n.weekday() >= 5:            # sabado o domingo
        return False
    if n.date() in FERIADOS_EEUU:
        return False
    return APERTURA_NY <= n.time() < CIERRE_NY


def minutos_al_cierre(ahora: datetime | None = None) -> float | None:
    """Minutos hasta el cierre de la bolsa. None si ya esta cerrada."""
    n = _ahora_ny(ahora)
    if not bolsa_eeuu_abierta(n):
        return None
    cierre = n.replace(hour=CIERRE_NY.hour, minute=CIERRE_NY.minute,
                       second=0, microsecond=0)
    return (cierre - n).total_seconds() / 60.0


def debe_cerrar_todo(grupo: str, ahora: datetime | None = None,
                     abierta_en: datetime | None = None) -> tuple[bool, str]:
    """Hay que CERRAR lo abierto ya, por la regla de intradia?

    Si se pasa `abierta_en`, tambien corta por tiempo en posicion.
    """
    n = _ahora_ny(ahora)
    # Tope de horas: se revisa PRIMERO porque no depende del grupo ni del
    # horario del mercado. Una posicion vieja se cierra, punto.
    if abierta_en is not None:
        horas = ((ahora or datetime.now(timezone.utc)) - abierta_en).total_seconds() / 3600
        if horas >= MAX_HORAS_EN_POSICION:
            return True, (f"lleva {horas:.1f} h abierta, el tope es "
                          f"{MAX_HORAS_EN_POSICION:g} h")
    if grupo in GRUPOS_BOLSA:
        m = minutos_al_cierre(ahora)
        if m is None:
            return True, "la bolsa esta cerrada y quedo una posicion abierta"
        if m <= MARGEN_CERRAR_MIN:
            return True, f"faltan {m:.0f} min para el cierre de la bolsa"
        return False, ""
    # El corte es el rollover de las 17:00 NY, que es cuando el broker
    # cobraria el swap.
    #
    # VENTANA ESTRECHA, corregida el 2026-10-30. Antes decia "cerrar todo
    # despues de las 16:50" para TODA la tarde y la noche, y eso bloqueaba
    # la apertura de la semana: el mercado de divisas abre el domingo a las
    # 17:00 NY. Con la regla vieja, el domingo a las 18:00 "habia que
    # cerrar" y por la invariante no se podia abrir -- se perdia la semana.
    #
    # Solo hay que cerrar en los 10 minutos previos al rollover. Despues de
    # las 17:00 empieza un dia de trading nuevo y abrir es legitimo: una
    # posicion abierta a las 18:00 y cerrada al dia siguiente a las 16:50
    # no cruza ningun rollover y no paga swap.
    if time(16, 50) <= n.time() < time(17, 0):
        falta = (time(17, 0).hour * 60) - (n.hour * 60 + n.minute)
        return True, f"faltan {falta} min para el rollover de las 17:00 NY"
    return False, ""


def puede_abrir(grupo: str, ahora: datetime | None = None) -> tuple[bool, str]:
    """Se puede ABRIR una posicion nueva en este grupo, ahora?

    INVARIANTE, violada y corregida el 2026-10-30: si debe_cerrar_todo()
    dice que hay que cerrar, puede_abrir() TIENE que decir que no. Antes
    `puede_abrir("CRYPTO")` devolvia True sin mirar la hora mientras
    `debe_cerrar_todo("CRYPTO")` ya decia True pasadas las 16:50 NY. El
    sistema abria y cerraba en la pasada siguiente, perdiendo el spread
    cada vez. Tres operaciones reales se fueron asi: -0,15, -0,35 y -0,84.
    """
    # Se consulta PRIMERO el cierre forzoso: nunca abrir lo que habria que
    # cerrar de inmediato. La comprobacion va antes de cualquier otra.
    hay_que_cerrar, por_que = debe_cerrar_todo(grupo, ahora)
    if hay_que_cerrar:
        return False, f"no se abre porque ya toca cerrar: {por_que}"
    if grupo in GRUPOS_CONTINUOS:
        return True, ""
    if grupo in GRUPOS_BOLSA:
        if not bolsa_eeuu_abierta(ahora):
            n = _ahora_ny(ahora)
            return False, (f"bolsa de EEUU CERRADA ({n:%a %H:%M} de Nueva York)")
        m = minutos_al_cierre(ahora) or 0
        if m < MARGEN_NO_ABRIR_MIN:
            return False, (f"faltan {m:.0f} min para el cierre; no se abre "
                           f"con menos de {MARGEN_NO_ABRIR_MIN}")
        return True, ""
    # Divisas, metales y energia: de domingo por la tarde a viernes por la
    # tarde en Nueva York. Fuera de eso, cerrado.
    n = _ahora_ny(ahora)
    if n.weekday() == 5:                                    # sabado
        return False, "mercado cerrado (sabado)"
    if n.weekday() == 6 and n.time() < time(17, 0):         # domingo temprano
        return False, "mercado cerrado (domingo antes de las 17:00 NY)"
    if n.weekday() == 4 and n.time() >= time(17, 0):        # viernes tarde
        return False, "mercado cerrado (viernes despues de las 17:00 NY)"
    return True, ""




def resumen(ahora: datetime | None = None) -> str:
    n = _ahora_ny(ahora)
    l = [f"hora Nueva York   {n:%a %Y-%m-%d %H:%M}",
         f"bolsa de EEUU     {'ABIERTA' if bolsa_eeuu_abierta(n) else 'cerrada'}"]
    m = minutos_al_cierre(n)
    if m is not None:
        l.append(f"cierra en         {m:.0f} min")
    for g in ("CRYPTO", "EQUITY_US", "FOREX"):
        ok, por = puede_abrir(g, n)
        cerrar, por2 = debe_cerrar_todo(g, n)
        l.append(f"  {g:<11} abrir={'SI' if ok else 'no'}"
                 f"{'  (' + por + ')' if por else ''}"
                 f"{'   CERRAR TODO: ' + por2 if cerrar else ''}")
    return "\n".join(l)
