"""Estrategias de aprendizaje automatico, con walk-forward estricto.

La parte que decide si esto vale algo o es basura con decimales:

  EL MODELO SOLO VE EL PASADO. Se entrena con las barras [0 .. t-1] y
  predice la barra t+1. Cuando avanza, se reentrena. Nunca, en ningun
  momento, el entrenamiento incluye el dato que se va a predecir.

Eso se consigue por construccion: la estrategia recibe una VentanaMercado
que fisicamente no alcanza el futuro, y las caracteristicas se calculan
solo con lo que hay dentro de esa ventana.

El reentrenamiento tiene costo de CPU, asi que se hace cada N barras y no
en cada una. Ese N es un parametro declarado, no un detalle escondido.
"""

from __future__ import annotations

import numpy as np

from ..backtest.mercado import VentanaMercado
from ..backtest.motor import Senal
from ..riesgo.modelo import Side
from .clasicas import _atr, _rsi, _sma, _desv


def caracteristicas(v: VentanaMercado, i: int, n_hist: int = 60) -> np.ndarray | None:
    """Vector de caracteristicas en el instante i, SOLO con datos <= i.

    Devuelve None si no hay suficiente historia: una fila con ceros
    rellenados es peor que ninguna fila, porque el modelo aprende del
    relleno.
    """
    if i < n_hist:
        return None
    # tramo() comprueba el tope: si se pide una barra que la estrategia no
    # deberia ver, lanza LookAheadError en vez de devolverla.
    bs = v.tramo(i - n_hist + 1, i)
    cs = tuple(b.close for b in bs)
    if len(cs) < n_hist or cs[-1] <= 0:
        return None
    r = np.diff(np.log(np.array(cs)))
    if r.size < 20:
        return None
    sma20 = _sma(cs[-20:]); sma50 = _sma(cs[-50:]) if len(cs) >= 50 else sma20
    sd20 = _desv(cs[-20:])
    hi = max(b.high for b in bs[-20:]); lo = min(b.low for b in bs[-20:])
    rango = hi - lo
    c = cs[-1]
    f = [
        r[-1], r[-2], r[-3],                      # retornos recientes
        float(np.mean(r[-5:])), float(np.mean(r[-20:])),
        float(np.std(r[-20:])) if r.size >= 20 else 0.0,
        (c / sma20 - 1.0) if sma20 > 0 else 0.0,  # distancia a las medias
        (c / sma50 - 1.0) if sma50 > 0 else 0.0,
        (sma20 / sma50 - 1.0) if sma50 > 0 else 0.0,
        (c - lo) / rango if rango > 0 else 0.5,   # posicion en el rango
        _rsi(cs, 14) / 100.0,
        (sd20 / c) if c > 0 else 0.0,             # volatilidad relativa
        float(np.mean(r[-20:] > 0)),              # fraccion de dias al alza
    ]
    a = np.array(f, dtype=float)
    return a if np.all(np.isfinite(a)) else None


class EstrategiaML:
    """Clasifica si la barra siguiente sube o baja, con walk-forward.

    `modelo` es una fabrica: se llama sin argumentos y devuelve un
    estimador de scikit-learn sin entrenar.
    """

    familia = "machine_learning"

    def __init__(self, nombre: str, modelo, entrenar_con: int = 750,
                 reentrenar_cada: int = 250, umbral: float = 0.56,
                 atr_stop: float = 2.0, rr: float = 2.0,
                 n_hist: int = 60):
        self.nombre = nombre
        self._fabrica = modelo
        self.entrenar_con = entrenar_con
        self.reentrenar_cada = reentrenar_cada
        self.umbral = umbral
        self.atr_stop, self.rr = atr_stop, rr
        self.n_hist = n_hist
        # Hace falta historia para entrenar Y para la ventana de rasgos.
        self.barras_minimas = entrenar_con + n_hist + 2
        self.strategy_id = f"ml-{nombre}-u{umbral:g}"
        self._modelo = None
        self._entrenado_en = -1
        self._fallos = 0
        # CACHE de caracteristicas por indice.
        #
        # Las caracteristicas en el indice i dependen SOLO de barras <= i,
        # asi que una vez calculadas no cambian nunca. Recalcularlas en
        # cada reentrenamiento costaba ~34.500 calculos por modelo e
        # instrumento y hacia que el torneo se pasara de 580 segundos
        # (medido el 2026-10-29). Guardarlas es correcto Y rapido.
        #
        # OJO: la cache guarda por indice, no por contenido. Es valida
        # porque una instancia de estrategia corre sobre UNA serie. Si se
        # reutilizara entre series distintas daria datos de otra serie:
        # por eso el torneo crea instancias nuevas por instrumento.
        self._cache: dict[int, np.ndarray | None] = {}

    def _rasgos(self, v: VentanaMercado, i: int):
        """caracteristicas(i) con memoria. Mismo resultado, sin recalcular."""
        if i not in self._cache:
            self._cache[i] = caracteristicas(v, i, self.n_hist)
        return self._cache[i]

    def _entrenar(self, v: VentanaMercado, hasta: int) -> bool:
        """Entrena con [.. hasta]. La etiqueta de la fila i es el signo del
        retorno de i -> i+1, asi que la ultima fila usable es hasta-1."""
        X, y = [], []
        desde = max(self.n_hist, hasta - self.entrenar_con)
        for i in range(desde, hasta):
            f = self._rasgos(v, i)
            if f is None:
                continue
            # La etiqueta de la fila i usa el cierre de i+1. tramo()
            # garantiza que i+1 ya es PASADO: si no lo fuera, explota.
            par = v.tramo(i, i + 1)
            c0, c1 = par[0].close, par[1].close
            if c0 <= 0:
                continue
            X.append(f)
            y.append(1 if c1 > c0 else 0)
        if len(X) < 200 or len(set(y)) < 2:
            return False
        try:
            m = self._fabrica()
            m.fit(np.array(X), np.array(y))
        except Exception:
            self._fallos += 1
            return False
        self._modelo = m
        self._entrenado_en = hasta
        return True

    def evaluar(self, v: VentanaMercado) -> Senal:
        i = v.listas - 1
        if v.listas < self.barras_minimas:
            return Senal(None)
        # El entrenamiento llega hasta i-1: la etiqueta de la fila i-1 usa
        # el cierre de i, que YA es pasado. Nunca toca i+1.
        if (self._modelo is None
                or i - self._entrenado_en >= self.reentrenar_cada):
            if not self._entrenar(v, i - 1):
                return Senal(None)
        f = self._rasgos(v, i)
        if f is None:
            return Senal(None)
        try:
            p = float(self._modelo.predict_proba(f.reshape(1, -1))[0][1])
        except Exception:
            self._fallos += 1
            return Senal(None)
        atr = _atr(v, 14)
        if atr <= 0:
            return Senal(None)
        sl = atr * self.atr_stop
        if p >= self.umbral:
            return Senal(Side.BUY, sl, sl * self.rr, f"ML p(sube)={p:.3f}")
        if p <= 1.0 - self.umbral:
            return Senal(Side.SELL, sl, sl * self.rr, f"ML p(sube)={p:.3f}")
        return Senal(None)


def catalogo_ml() -> dict:
    """Los tres modelos que pidio el encargo, con hiperparametros
    conservadores a proposito: arboles profundos sobre 750 filas de datos
    financieros memorizan ruido."""
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return {
        "logistica": lambda: make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=1000, C=0.1)),
        "bosque": lambda: RandomForestClassifier(
            n_estimators=120, max_depth=4, min_samples_leaf=30,
            random_state=42, n_jobs=1),
        "gradiente": lambda: GradientBoostingClassifier(
            n_estimators=80, max_depth=2, learning_rate=0.05,
            min_samples_leaf=30, random_state=42),
    }
