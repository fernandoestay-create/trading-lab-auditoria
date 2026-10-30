"""La prueba complementaria: el juez detecta una ventaja REAL?

Un juez que rechaza todo pasa la prueba del paseo aleatorio por la razon
equivocada: seria inutil, no riguroso. Aqui se inyecta una ventaja de
verdad --momentum con autocorrelacion positiva fuerte, algo que NO existe
en los mercados liquidos-- y se exige que el laboratorio la certifique.

Las dos pruebas juntas acotan al juez por los dos lados:
  - prueba_del_juez.py      : no certifica ruido   (especificidad)
  - prueba_de_potencia.py   : si certifica senal   (sensibilidad)
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labcore.backtest import Barra, ModeloCostos
from labcore.estrategias import Aleatoria, ComprarYMantener, CruceMedias, RupturaDeRango
from labcore.experimentos import RegistroExperimentos
from labcore.metricas import Torneo
from labcore.riesgo import InstrumentSpec

UTC = timezone.utc
EURUSD = InstrumentSpec(
    symbol="EURUSD", contract_size=100_000, tick_size=0.00001,
    tick_value_account_ccy=1.0, min_volume=0.01, volume_step=0.01,
    margin_rate=0.01, correlation_group="USD_MAJOR",
)


def serie_con_momentum(n: int, semilla: int, phi: float = 0.35,
                       s0: float = 1.1000, sigma: float = 0.0055,
                       spread: float = 0.00012) -> list[Barra]:
    """AR(1) con phi positivo: el retorno de hoy predice el de manana.

    phi=0,35 es una ventaja enorme y deliberadamente irreal. El punto no
    es simular un mercado: es comprobar que el juez la ve.
    """
    rng = np.random.default_rng(semilla)
    e = rng.normal(0.0, sigma, n)
    r = np.zeros(n)
    for i in range(1, n):
        r[i] = phi * r[i - 1] + e[i]
    cierres = s0 * np.exp(np.cumsum(r))
    d0 = datetime(2015, 1, 5, tzinfo=UTC)
    bs, prev = [], s0
    for i, c in enumerate(cierres):
        rango = abs(rng.normal(0.0, sigma * 0.6)) * prev
        bs.append(Barra(ts=d0 + timedelta(days=i), open=prev,
                        high=max(prev, c) + rango / 2,
                        low=min(prev, c) - rango / 2,
                        close=float(c), volume=1000.0, spread=spread))
        prev = float(c)
    return bs


def main() -> int:
    costos = ModeloCostos(comision_por_lote_por_lado=3.50, slippage_ticks=1.0,
                          swap_largo_por_lote_dia=-2.50,
                          swap_corto_por_lote_dia=-1.20)
    # INSTANCIAS NUEVAS por semilla, a proposito: varias estrategias
    # tienen estado (el generador de Aleatoria, la bandera de
    # ComprarYMantener). Reutilizar la instancia hacia que la pasiva
    # disparara en la primera serie y nunca mas -- se veia como "0
    # operaciones" en vez de como un bug.
    def ests():
        return [CruceMedias(10, 30), CruceMedias(20, 50), RupturaDeRango(10),
                RupturaDeRango(20), Aleatoria(prob=0.08, semilla=7),
                ComprarYMantener()]

    registro = RegistroExperimentos()
    detectadas = 0
    for semilla in (11, 23, 37):
        barras = serie_con_momentum(3000, semilla)
        t = Torneo(EURUSD, costos, barras, capital_inicial=10_000.0)
        t.correr(ests())
        rid = registro.anotar_torneo(
            t, etiqueta="prueba-de-potencia/momentum-ar1",
            datos_descripcion=("serie SINTETICA: AR(1) con phi=0,35, momentum "
                               "real e irrealmente fuerte, inyectado a proposito"),
            semilla=semilla,
            extra={"proposito": "sensibilidad: el juez SI debe detectarla",
                   "phi": 0.35},
        )
        print(f"\n### SERIE CON MOMENTUM REAL (AR(1) phi=0,35), semilla {semilla} ###")
        print(t.informe())
        print(f"corrida registrada: {rid}")
        if t.califican():
            detectadas += 1

    print()
    print("#" * 108)
    if detectadas == 0:
        print("FALLO DE POTENCIA: el juez no detecto una ventaja que SI existe.")
        print("Un juez que rechaza todo es inutil, no riguroso. Hay que")
        print("revisar si las barreras quedaron imposibles de superar.")
        return 1
    print(f"EL JUEZ TIENE POTENCIA: detecto la ventaja en {detectadas} de 3 series.")
    print("Junto con prueba_del_juez.py, el laboratorio queda acotado por")
    print("los dos lados: no certifica ruido y si certifica senal real.")
    print("#" * 108)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
