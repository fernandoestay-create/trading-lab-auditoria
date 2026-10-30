"""Las estrategias clasicas, tal como estan publicadas.

Estas NO las invento ni las optimizo: son las que estan en los libros de
analisis tecnico desde hace decadas. El punto de pasarlas por el
laboratorio es exactamente ese: si el juez no logra certificar ni una de
las conocidas, eso es el resultado del experimento, no un fracaso.

Cada estrategia declara barras_minimas. Una que necesita 200 barras y
recibe 50 NO devuelve una senal con basura: devuelve Senal(None).
"""

from __future__ import annotations

import random

from ..backtest.mercado import VentanaMercado
from ..backtest.motor import Senal
from ..riesgo.modelo import Side


def _sma(xs: tuple[float, ...]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _ema(xs: tuple[float, ...], n: int) -> float:
    if not xs:
        return 0.0
    k = 2.0 / (n + 1.0)
    e = xs[0]
    for x in xs[1:]:
        e = x * k + e * (1 - k)
    return e


def _atr(v: VentanaMercado, n: int) -> float:
    bs = v.ultimas(n + 1)
    if len(bs) < 2:
        return 0.0
    trs = []
    for prev, cur in zip(bs, bs[1:]):
        trs.append(max(cur.high - cur.low,
                       abs(cur.high - prev.close),
                       abs(cur.low - prev.close)))
    return sum(trs) / len(trs) if trs else 0.0


def _rsi(cierres: tuple[float, ...], n: int) -> float:
    if len(cierres) < n + 1:
        return 50.0
    sub = cierres[-(n + 1):]
    sube = [max(b - a, 0.0) for a, b in zip(sub, sub[1:])]
    baja = [max(a - b, 0.0) for a, b in zip(sub, sub[1:])]
    mg, ml = sum(sube) / n, sum(baja) / n
    if ml == 0:
        return 100.0 if mg > 0 else 50.0
    rs = mg / ml
    return 100.0 - 100.0 / (1.0 + rs)


def _desv(xs: tuple[float, ...]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _sma(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


# ======================== TENDENCIA ========================

class CruceMedias:
    """Cruce de medias moviles. La estrategia mas publicada que existe."""

    familia = "tendencia"

    def __init__(self, rapida: int = 20, lenta: int = 50,
                 atr_stop: float = 2.0, rr: float = 2.0):
        self.rapida, self.lenta = rapida, lenta
        self.atr_stop, self.rr = atr_stop, rr
        self.barras_minimas = lenta + 2
        self.strategy_id = f"cruce-medias-{rapida}-{lenta}"

    def evaluar(self, v: VentanaMercado) -> Senal:
        if v.listas < self.barras_minimas:
            return Senal(None)
        cs = v.cierres(self.lenta + 1)
        r_ahora, r_antes = _sma(cs[-self.rapida:]), _sma(cs[-self.rapida - 1:-1])
        l_ahora, l_antes = _sma(cs[-self.lenta:]), _sma(cs[-self.lenta - 1:-1])
        atr = _atr(v, 14)
        if atr <= 0:
            return Senal(None)
        sl = atr * self.atr_stop
        if r_antes <= l_antes and r_ahora > l_ahora:
            return Senal(Side.BUY, sl, sl * self.rr, "cruce al alza")
        if r_antes >= l_antes and r_ahora < l_ahora:
            return Senal(Side.SELL, sl, sl * self.rr, "cruce a la baja")
        return Senal(None)


class MACD:
    familia = "tendencia"

    def __init__(self, rapida: int = 12, lenta: int = 26, senal: int = 9,
                 atr_stop: float = 2.0, rr: float = 2.0):
        self.rapida, self.lenta, self.senal_n = rapida, lenta, senal
        self.atr_stop, self.rr = atr_stop, rr
        self.barras_minimas = lenta + senal + 2
        self.strategy_id = f"macd-{rapida}-{lenta}-{senal}"

    def _macd_hist(self, cs: tuple[float, ...]) -> float:
        linea = _ema(cs, self.rapida) - _ema(cs, self.lenta)
        return linea

    def evaluar(self, v: VentanaMercado) -> Senal:
        if v.listas < self.barras_minimas:
            return Senal(None)
        cs = v.cierres(self.barras_minimas)
        ahora = self._macd_hist(cs)
        antes = self._macd_hist(cs[:-1])
        atr = _atr(v, 14)
        if atr <= 0:
            return Senal(None)
        sl = atr * self.atr_stop
        if antes <= 0 < ahora:
            return Senal(Side.BUY, sl, sl * self.rr, "MACD cruza arriba")
        if antes >= 0 > ahora:
            return Senal(Side.SELL, sl, sl * self.rr, "MACD cruza abajo")
        return Senal(None)


class RupturaDeRango:
    """Ruptura de maximos y minimos de N barras (estilo Donchian/turtle).

    DOS FILTROS que pidio Fernando el 2026-10-30: "debemos tener algo de
    tolerancia para seguir la tendencia y que no sean movimientos
    minusculos".

      * `margen_atr`: el precio tiene que SUPERAR el rango por una
        fraccion del ATR, no solo tocarlo. Tocar el maximo por un centavo
        no es una ruptura: es ruido que ademas dispara la comision.

      * `vol_minima_pct`: si el ATR es diminuto respecto al precio, no
        esta pasando nada y cualquier "ruptura" es ruido. Se salta.

    Los dos por defecto en 0 para no cambiar en silencio lo ya medido:
    quien los quiera, los pide. Su efecto se mide, no se supone.
    """

    familia = "tendencia"

    def __init__(self, n: int = 20, atr_stop: float = 2.0, rr: float = 2.0,
                 margen_atr: float = 0.0, vol_minima_pct: float = 0.0):
        self.n = n
        self.atr_stop, self.rr = atr_stop, rr
        self.margen_atr = margen_atr
        self.vol_minima_pct = vol_minima_pct
        self.barras_minimas = n + 2
        sufijo = ""
        if margen_atr:
            sufijo += f"-m{margen_atr:g}"
        if vol_minima_pct:
            sufijo += f"-v{vol_minima_pct:g}"
        self.strategy_id = f"ruptura-{n}{sufijo}"

    def evaluar(self, v: VentanaMercado) -> Senal:
        if v.listas < self.barras_minimas:
            return Senal(None)
        bs = v.ultimas(self.n + 1)
        previas, actual = bs[:-1], bs[-1]
        atr = _atr(v, 14)
        if atr <= 0:
            return Senal(None)
        # Filtro de volatilidad: si no esta pasando nada, no hay ruptura
        # que valga. Evita operar en mercados dormidos donde el costo se
        # come cualquier movimiento.
        if self.vol_minima_pct and actual.close > 0:
            if atr / actual.close < self.vol_minima_pct:
                return Senal(None)
        sl = atr * self.atr_stop
        margen = atr * self.margen_atr
        techo = max(b.high for b in previas)
        piso = min(b.low for b in previas)
        if actual.close > techo + margen:
            exceso = (actual.close - techo) / atr
            return Senal(Side.BUY, sl, sl * self.rr,
                         f"ruptura de {self.n} arriba por {exceso:.2f} ATR")
        if actual.close < piso - margen:
            exceso = (piso - actual.close) / atr
            return Senal(Side.SELL, sl, sl * self.rr,
                         f"ruptura de {self.n} abajo por {exceso:.2f} ATR")
        return Senal(None)


# ======================== REVERSION A LA MEDIA ========================

class RSIReversion:
    familia = "reversion"

    def __init__(self, n: int = 14, bajo: float = 30.0, alto: float = 70.0,
                 atr_stop: float = 1.5, rr: float = 1.5):
        self.n, self.bajo, self.alto = n, bajo, alto
        self.atr_stop, self.rr = atr_stop, rr
        self.barras_minimas = n + 16
        self.strategy_id = f"rsi-{n}-{int(bajo)}-{int(alto)}"

    def evaluar(self, v: VentanaMercado) -> Senal:
        if v.listas < self.barras_minimas:
            return Senal(None)
        cs = v.cierres(self.n + 2)
        r = _rsi(cs, self.n)
        atr = _atr(v, 14)
        if atr <= 0:
            return Senal(None)
        sl = atr * self.atr_stop
        if r < self.bajo:
            return Senal(Side.BUY, sl, sl * self.rr, f"RSI {r:.0f} sobrevendido")
        if r > self.alto:
            return Senal(Side.SELL, sl, sl * self.rr, f"RSI {r:.0f} sobrecomprado")
        return Senal(None)


class BandasBollinger:
    familia = "reversion"

    def __init__(self, n: int = 20, k: float = 2.0,
                 atr_stop: float = 1.5, rr: float = 1.5):
        self.n, self.k = n, k
        self.atr_stop, self.rr = atr_stop, rr
        self.barras_minimas = n + 16
        self.strategy_id = f"bollinger-{n}-{k:g}"

    def evaluar(self, v: VentanaMercado) -> Senal:
        if v.listas < self.barras_minimas:
            return Senal(None)
        cs = v.cierres(self.n)
        m, sd = _sma(cs), _desv(cs)
        if sd <= 0:
            return Senal(None)
        c = cs[-1]
        atr = _atr(v, 14)
        if atr <= 0:
            return Senal(None)
        sl = atr * self.atr_stop
        if c < m - self.k * sd:
            return Senal(Side.BUY, sl, sl * self.rr, "bajo la banda inferior")
        if c > m + self.k * sd:
            return Senal(Side.SELL, sl, sl * self.rr, "sobre la banda superior")
        return Senal(None)


class ZScoreReversion:
    familia = "reversion"

    def __init__(self, n: int = 50, umbral: float = 2.0,
                 atr_stop: float = 1.5, rr: float = 1.5):
        self.n, self.umbral = n, umbral
        self.atr_stop, self.rr = atr_stop, rr
        self.barras_minimas = n + 16
        self.strategy_id = f"zscore-{n}-{umbral:g}"

    def evaluar(self, v: VentanaMercado) -> Senal:
        if v.listas < self.barras_minimas:
            return Senal(None)
        cs = v.cierres(self.n)
        m, sd = _sma(cs), _desv(cs)
        if sd <= 0:
            return Senal(None)
        z = (cs[-1] - m) / sd
        atr = _atr(v, 14)
        if atr <= 0:
            return Senal(None)
        sl = atr * self.atr_stop
        if z < -self.umbral:
            return Senal(Side.BUY, sl, sl * self.rr, f"z={z:.2f}")
        if z > self.umbral:
            return Senal(Side.SELL, sl, sl * self.rr, f"z={z:.2f}")
        return Senal(None)


# ======================== BENCHMARKS (obligatorios) ========================

class Aleatoria:
    """Senal al azar con la MISMA frecuencia y el mismo manejo de riesgo.

    Es el benchmark que mas duele y el que mas gente omite: si tu
    estrategia no le gana a esto, lo que medias era el manejo de riesgo
    y los costos, no la senal.
    """

    familia = "benchmark"

    def __init__(self, prob: float = 0.05, semilla: int = 42,
                 atr_stop: float = 2.0, rr: float = 2.0):
        self.prob, self.atr_stop, self.rr = prob, atr_stop, rr
        self.barras_minimas = 16
        self._rng = random.Random(semilla)
        self.strategy_id = f"aleatoria-p{prob:g}-s{semilla}"

    def evaluar(self, v: VentanaMercado) -> Senal:
        if v.listas < self.barras_minimas:
            return Senal(None)
        if self._rng.random() >= self.prob:
            return Senal(None)
        atr = _atr(v, 14)
        if atr <= 0:
            return Senal(None)
        sl = atr * self.atr_stop
        side = Side.BUY if self._rng.random() < 0.5 else Side.SELL
        return Senal(side, sl, sl * self.rr, "azar")


class ComprarYMantener:
    """Compra una vez y no vuelve a senalar. El benchmark pasivo."""

    familia = "benchmark"

    # RESTRICCION ESTRUCTURAL, medida el 2026-10-28:
    # con lote minimo 0,01 y riesgo 0,5% sobre 10.000 USD, el stop mas
    # ancho operable son ~5.000 ticks (0,05 en EURUSD, unos 500 pips).
    # 50xATR y 8xATR daban un tamano bajo el minimo del contrato, asi que
    # la pasiva nunca abria y el benchmark no era vara de nada.
    # 6xATR entra con holgura. Si cambias el capital o el lote minimo,
    # este numero cambia: no lo heredes, recalculalo.
    def __init__(self, atr_stop: float = 6.0):
        self.atr_stop = atr_stop
        self.barras_minimas = 16
        self._ya = False
        self.strategy_id = "comprar-y-mantener"

    def evaluar(self, v: VentanaMercado) -> Senal:
        if self._ya or v.listas < self.barras_minimas:
            return Senal(None)
        atr = _atr(v, 14)
        if atr <= 0:
            return Senal(None)
        self._ya = True
        return Senal(Side.BUY, atr * self.atr_stop, 0.0, "pasiva")


CATALOGO = {
    "cruce-medias": CruceMedias, "macd": MACD, "ruptura": RupturaDeRango,
    "rsi": RSIReversion, "bollinger": BandasBollinger, "zscore": ZScoreReversion,
    "aleatoria": Aleatoria, "comprar-y-mantener": ComprarYMantener,
}
