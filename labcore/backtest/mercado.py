"""Series de mercado con ventana que NO alcanza el futuro.

El look-ahead bias no se evita con disciplina del programador: se evita
haciendo que el dato futuro sea INALCANZABLE desde donde corre la
estrategia. Una estrategia recibe una VentanaMercado y no tiene ninguna
referencia al resto de la serie.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Barra:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    # Spread en unidades de precio AL NIVEL DE ESTA BARRA.
    #
    # BUG CORREGIDO 2026-10-29: antes se pasaba un monto fijo para toda la
    # serie. Con AAPL eso aplicaba un spread de US$0,02 al precio de 1980
    # (US$0,10 ajustado por splits), o sea un 20% del precio, y cada
    # operacion perdia 3,7 veces su riesgo teorico. El spread se modela
    # como FRACCION del precio (puntos basicos) y se convierte a monto
    # barra por barra. Ver ingesta.a_barras().
    spread: float

    @property
    def bid_close(self) -> float:
        return self.close - self.spread / 2.0

    @property
    def ask_close(self) -> float:
        return self.close + self.spread / 2.0


class LookAheadError(RuntimeError):
    """Se intento leer una barra que la estrategia no deberia poder ver."""


class VentanaMercado:
    """Vista de solo lectura de barras[0 .. i], cerrada en i.

    `self[-1]` es la ultima barra CERRADA. No existe forma de llegar a
    barras[i+1] desde aqui: no se guarda la lista completa, se guarda el
    indice y la lista es privada con comprobacion de tope.
    """

    __slots__ = ("_barras", "_i", "symbol")

    def __init__(self, barras: list[Barra], i: int, symbol: str) -> None:
        self._barras = barras
        self._i = i
        self.symbol = symbol

    def __len__(self) -> int:
        return self._i + 1

    def __getitem__(self, k: int) -> Barra:
        n = self._i + 1
        if isinstance(k, slice):
            raise TypeError("usa ultimas(n), no slices: un slice puede filtrar el futuro")
        j = k + n if k < 0 else k
        if j < 0 or j > self._i:
            raise LookAheadError(
                f"la estrategia pidio la barra {k} (indice {j}) con solo "
                f"{n} barras cerradas: eso es mirar el futuro"
            )
        return self._barras[j]

    def ultimas(self, n: int) -> tuple[Barra, ...]:
        if n <= 0:
            raise ValueError("n debe ser positivo")
        desde = max(0, self._i + 1 - n)
        return tuple(self._barras[desde : self._i + 1])

    def cierres(self, n: int) -> tuple[float, ...]:
        return tuple(b.close for b in self.ultimas(n))

    def tramo(self, desde: int, hasta: int) -> tuple[Barra, ...]:
        """Barras [desde, hasta], ambas incluidas, con tope comprobado.

        Existe para que el codigo de caracteristicas de los modelos no
        tenga que tocar la lista privada. Acceder a `_barras` directo
        funciona solo si quien lo escribe es cuidadoso con los indices, y
        la razon de ser de esta clase es NO depender de eso.
        """
        if desde < 0 or hasta > self._i or desde > hasta:
            raise LookAheadError(
                f"se pidio el tramo [{desde}, {hasta}] con solo "
                f"{self._i + 1} barras cerradas"
            )
        return tuple(self._barras[desde : hasta + 1])

    @property
    def actual(self) -> Barra:
        return self._barras[self._i]

    @property
    def listas(self) -> int:
        """Cuantas barras cerradas hay. Una estrategia que necesita 200 y
        recibe 50 tiene que decirlo, no devolver una senal con basura."""
        return self._i + 1
