"""Modelo de costos. Si esto esta optimista, TODO lo de arriba es ficcion.

Los cuatro costos y el orden en que muerden:
  1. spread   - se paga al entrar y al salir, siempre, en cada operacion
  2. comision - por lote y por lado
  3. slippage - diferencia entre el precio que pediste y el que te dieron
  4. swap     - por noche de posicion abierta (triple el miercoles)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class ModeloCostos:
    comision_por_lote_por_lado: float = 0.0
    slippage_ticks: float = 0.0
    swap_largo_por_lote_dia: float = 0.0    # negativo = te cobran
    swap_corto_por_lote_dia: float = 0.0
    multiplicador_spread: float = 1.0        # 3.0 = prueba de estres
    # Miercoles: el mercado contabiliza el fin de semana. Si esto es 1.0
    # estas subestimando el costo de cualquier estrategia que aguante noches.
    swap_triple_dia_semana: int = 2          # 2 = miercoles (lunes=0)
    swap_triple_factor: float = 3.0

    def spread_efectivo(self, spread_barra: float) -> float:
        return spread_barra * self.multiplicador_spread

    def comision(self, volumen: float) -> float:
        """Un lado. Se cobra al entrar Y al salir."""
        return abs(volumen) * self.comision_por_lote_por_lado

    def slippage_precio(self, tick_size: float, es_compra: bool,
                        precio: float | None = None) -> float:
        """El slippage SIEMPRE va en tu contra. Un modelo que lo pone
        simetrico o aleatorio con media cero es un modelo optimista.

        Si se pasa `precio`, el slippage se acota a 5 puntos basicos de
        ese precio. Sin ese tope, 1 tick de US$0,01 sobre una accion que
        valia US$0,10 en 1980 es un 10% de slippage por operacion
        (bug detectado el 2026-10-29).
        """
        d = self.slippage_ticks * tick_size
        if precio is not None and precio > 0:
            d = min(d, precio * 0.0005)
        return d if es_compra else -d

    def noches_de_swap(self, apertura: datetime, cierre: datetime) -> float:
        """Noches ponderadas entre apertura y cierre, con el triple del
        miercoles contado como corresponde."""
        if cierre <= apertura:
            return 0.0
        total = 0.0
        d: date = apertura.date()
        while d < cierre.date():
            factor = (
                self.swap_triple_factor
                if d.weekday() == self.swap_triple_dia_semana
                else 1.0
            )
            total += factor
            d += timedelta(days=1)
        return total

    def swap(self, volumen: float, es_largo: bool,
             apertura: datetime, cierre: datetime) -> float:
        tasa = self.swap_largo_por_lote_dia if es_largo else self.swap_corto_por_lote_dia
        return tasa * abs(volumen) * self.noches_de_swap(apertura, cierre)


# Sin medir, no se inventa. Estos valores son PLACEHOLDER declarados como
# tales: hay que reemplazarlos midiendo la cuenta real durante 30 dias.
# Un modelo de costos heredado de un blog es peor que ninguno, porque
# produce un backtest que parece creible.
COSTOS_SIN_MEDIR = ModeloCostos()
