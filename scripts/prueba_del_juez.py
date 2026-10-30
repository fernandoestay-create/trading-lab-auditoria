"""LA PRUEBA MAS IMPORTANTE DEL LABORATORIO.

Se corre el torneo completo sobre un PASEO ALEATORIO puro: una serie
generada sin ninguna estructura, donde por construccion no hay nada que
descubrir. Ninguna estrategia deberia calificar.

Si el juez certifica algo aqui, el juez esta roto, y todo lo que diga
sobre datos reales no vale nada. Esta es la prueba que decide si se puede
confiar en el resto del sistema.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labcore.backtest import Barra, ModeloCostos
from labcore.estrategias import (
    Aleatoria, BandasBollinger, ComprarYMantener, CruceMedias, MACD,
    RSIReversion, RupturaDeRango, ZScoreReversion,
)
from labcore.experimentos import RegistroExperimentos
from labcore.metricas import Torneo
from labcore.riesgo import InstrumentSpec

UTC = timezone.utc

EURUSD = InstrumentSpec(
    symbol="EURUSD", contract_size=100_000, tick_size=0.00001,
    tick_value_account_ccy=1.0, min_volume=0.01, volume_step=0.01,
    margin_rate=0.01, correlation_group="USD_MAJOR",
)


def paseo_aleatorio(n: int, semilla: int, s0: float = 1.1000,
                    sigma: float = 0.0055, spread: float = 0.00012) -> list[Barra]:
    """Serie SIN estructura: incrementos normales independientes.

    sigma diario de 0,55% y spread de 1,2 pips son del orden de EURUSD,
    pero la serie es sintetica a proposito: aqui no se mide ninguna
    estrategia, se mide el JUEZ.
    """
    rng = np.random.default_rng(semilla)
    pasos = rng.normal(0.0, sigma, n)
    cierres = s0 * np.exp(np.cumsum(pasos))
    d0 = datetime(2015, 1, 5, tzinfo=UTC)
    bs: list[Barra] = []
    prev = s0
    for i, c in enumerate(cierres):
        rango = abs(rng.normal(0.0, sigma * 0.6)) * prev
        o = prev
        h = max(o, c) + rango / 2
        l = min(o, c) - rango / 2
        bs.append(Barra(ts=d0 + timedelta(days=i), open=o, high=h, low=l,
                        close=float(c), volume=1000.0, spread=spread))
        prev = float(c)
    return bs


def participantes():
    return [
        CruceMedias(20, 50), CruceMedias(10, 100), MACD(),
        RupturaDeRango(20), RSIReversion(), BandasBollinger(),
        ZScoreReversion(), Aleatoria(prob=0.05, semilla=7),
        ComprarYMantener(),
    ]


def main() -> int:
    # Costos declarados como NO MEDIDOS. Son del orden correcto para
    # EURUSD, pero hay que reemplazarlos midiendo la cuenta real.
    costos = ModeloCostos(
        comision_por_lote_por_lado=3.50,
        slippage_ticks=1.0,
        swap_largo_por_lote_dia=-2.50,
        swap_corto_por_lote_dia=-1.20,
    )
    registro = RegistroExperimentos()
    fallos, ids, sharpes_absurdos = [], [], []

    # Sobre un paseo aleatorio, ningun Sharpe POSITIVO deberia ser grande.
    # Solo se acota el lado positivo: una estrategia que PIERDE sobre ruido
    # puede tener Sharpe muy negativo con toda razon, porque los costos la
    # castigan sistematicamente -- eso es correcto, no un bug.
    # Medido: con la anualizacion correcta el maximo positivo es 0,41; con el
    # bug del sqrt(252) sube a 2,20. El tope de 1,0 separa los dos con holgura.
    TOPE_SHARPE_SOBRE_RUIDO = 1.0
    for semilla in (11, 23, 37):
        barras = paseo_aleatorio(3000, semilla)   # ~12 anos de barras diarias
        t = Torneo(EURUSD, costos, barras, capital_inicial=10_000.0,
                   periodos_por_ano=252.0)
        t.correr(participantes())
        print()
        print(f"### PASEO ALEATORIO, semilla {semilla} "
              f"(no hay senal que encontrar) ###")
        print(t.informe())
        # L-129: el numero que no se escribe a disco no es una metrica.
        rid = registro.anotar_torneo(
            t, etiqueta="prueba-del-juez/paseo-aleatorio",
            datos_descripcion=("serie SINTETICA: paseo aleatorio sin estructura, "
                               "sigma diario 0,55%, spread 1,2 pips"),
            semilla=semilla,
            extra={"proposito": "especificidad: el juez NO debe certificar nada"},
        )
        ids.append(rid)
        print(f"corrida registrada: {rid}  ->  {registro.ruta}")
        cal = t.califican()
        if cal:
            fallos.append((semilla, [p.strategy_id for p in cal]))

        # Segunda guardia: que las CIFRAS sean sanas, no solo el veredicto.
        # Un Sharpe inflado que nadie certifica sigue siendo un numero falso
        # que termina copiado en un informe (L-129).
        for part in t.participantes:
            s = part.desempeno.sharpe
            if s > TOPE_SHARPE_SOBRE_RUIDO:
                sharpes_absurdos.append((semilla, part.strategy_id, round(s, 3)))

    print()
    print("#" * 108)
    if sharpes_absurdos:
        print("FALLO DEL JUEZ: las cifras estan infladas.")
        print(f"Sobre un paseo aleatorio ningun Sharpe deberia pasar de "
              f"{TOPE_SHARPE_SOBRE_RUIDO}, y estos lo pasan:")
        for s, sid, v in sharpes_absurdos[:10]:
            print(f"  semilla {s}: {sid} -> Sharpe {v}")
        print()
        print("Causa mas probable: la anualizacion del Sharpe. Tiene que usar")
        print("la frecuencia REAL de operaciones (operaciones / anos de datos),")
        print("no sqrt(252), que asume una operacion diaria.")
        print("Es el bug del 2026-10-28 y volvio.")
        return 1
    if fallos:
        print("FALLO DEL JUEZ: certifico estrategias sobre datos sin senal.")
        for s, ids in fallos:
            print(f"  semilla {s}: {', '.join(ids)}")
        print("No se puede confiar en este laboratorio hasta arreglarlo.")
        return 1
    print("EL JUEZ PASA LA PRUEBA: sobre tres paseos aleatorios distintos")
    print("no certifico ninguna estrategia. Es la condicion MINIMA para")
    print("que sus veredictos sobre datos reales signifiquen algo.")
    print("(Condicion necesaria, no suficiente: pasar esto no prueba que")
    print(" el juez detecte una ventaja real cuando SI exista.)")
    print()
    print("Corridas persistidas y auditables:")
    for rid in ids:
        print(f"  {rid}")
    print(f"Para auditar cualquiera:  lab python -c \"from labcore.experimentos "
          f"import RegistroExperimentos as R; print(R().auditar('{ids[0]}'))\"")
    print("#" * 108)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
