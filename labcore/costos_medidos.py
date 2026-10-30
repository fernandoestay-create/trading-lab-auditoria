"""Spreads MEDIDOS de la cuenta, no inventados.

Antes el laboratorio usaba spreads que yo puse a ojo: 25 para BTCUSD
cuando el real promedia 2,7 y llega a 8,6. Eso hacia el backtest 3 a 9
veces mas pesimista de lo real, y en el otro extremo podia volverlo
optimista cuando el spread se ensancha.

Dos decisiones que importan:

  1. Se usa el MAXIMO observado, no el promedio. Para modelar un costo,
     equivocarse por pesimista cuesta oportunidades; equivocarse por
     optimista cuesta plata. El percentil alto es la eleccion correcta.

  2. El margen por incertidumbre se ANCLA a la medicion y se encoge a
     medida que llegan muestras. Un factor fijo alto (lo que hice
     primero) le ponia a BTCUSD un spread de 76,50 cuando el medido
     promedia 2,69 -- 27 veces mas. Eso no es prudencia: es un numero
     arbitrario que mata cualquier estrategia y no informa de nada.

  3. CERO muestras si recibe un valor alto por defecto y queda marcado.
     Rellenar con una cifra plausible es como se cuelan los backtests
     mentirosos.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

MUESTRAS = Path.home() / "trading-lab" / "experimentos" / "spread_observado.jsonl"

# Fraccion del precio que se asume cuando NO hay ninguna medicion.
# Deliberadamente alta (0,1% = 10 puntos basicos): un instrumento sin
# medir tiene que verse caro hasta que se mida.
SIN_MEDIR_PCT = 0.001

# Muestras minimas para confiar en el maximo observado. Con 2 muestras el
# maximo es casi seguro una subestimacion de lo que pasa en un dia malo.
MINIMO_MUESTRAS = 20


@dataclass(frozen=True)
class SpreadMedido:
    instrumento: str
    muestras: int
    pct_promedio: float
    pct_maximo: float
    confiable: bool

    @property
    def factor_incertidumbre(self) -> float:
        """Margen sobre el maximo observado, por tener poca muestra.

        Va de 3,0 con una sola muestra a 1,25 con la muestra minima. Es
        multiplicativo sobre lo MEDIDO, no un valor absoluto inventado:
        con pocas muestras el maximo observado subestima el dia malo, y
        el factor cubre esa brecha sin perder el anclaje al dato real.
        """
        if self.muestras >= MINIMO_MUESTRAS:
            return 1.25
        if self.muestras <= 1:
            return 3.0
        # Interpolacion lineal entre 3,0 y 1,25.
        avance = (self.muestras - 1) / max(MINIMO_MUESTRAS - 1, 1)
        return 3.0 - avance * (3.0 - 1.25)

    @property
    def pct_a_usar(self) -> float:
        """Maximo observado x el margen por incertidumbre."""
        return self.pct_maximo * self.factor_incertidumbre

    def monto(self, precio: float) -> float:
        return precio * self.pct_a_usar


def cargar(ruta: Path | None = None) -> dict[str, SpreadMedido]:
    f = ruta or MUESTRAS
    if not f.exists():
        return {}
    por: dict[str, list[float]] = {}
    for linea in f.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            d = json.loads(linea)
        except json.JSONDecodeError:
            continue           # una linea corrupta no invalida el resto
        p = d.get("spread_pct")
        if p is None or not isinstance(p, (int, float)) or p <= 0:
            continue
        por.setdefault(d["instrumento"], []).append(float(p))
    out = {}
    for ins, ps in por.items():
        out[ins] = SpreadMedido(
            instrumento=ins, muestras=len(ps),
            pct_promedio=sum(ps) / len(ps), pct_maximo=max(ps),
            confiable=len(ps) >= MINIMO_MUESTRAS)
    return out


def para(instrumento: str, precio: float,
         tabla: dict[str, SpreadMedido] | None = None) -> tuple[float, str]:
    """Spread en unidades de precio + de donde salio. Siempre dice su origen."""
    t = tabla if tabla is not None else cargar()
    m = t.get(instrumento)
    if m is None:
        return precio * SIN_MEDIR_PCT, "SIN MEDIR (asumido 0,1%)"
    origen = (f"medido, {m.muestras} muestras, max {m.pct_maximo:.5%} "
              f"x{m.factor_incertidumbre:.2f}")
    return m.monto(precio), origen


def informe(tabla: dict[str, SpreadMedido] | None = None) -> str:
    t = tabla if tabla is not None else cargar()
    if not t:
        return ("Todavia no hay muestras de spread. El muestreo corre cada "
                "10 min; hasta entonces todo instrumento se asume al 0,1%.")
    l = [f"{'instrumento':<10} {'muestras':>9} {'prom':>10} {'maximo':>10} "
         f"{'margen':>8} {'se usa':>10} {'confiable':>10}"]
    l.append("-" * 72)
    for ins, m in sorted(t.items(), key=lambda kv: -kv[1].pct_a_usar):
        l.append(f"{ins:<10} {m.muestras:>9} {m.pct_promedio:>9.5%} "
                 f"{m.pct_maximo:>9.5%} {m.factor_incertidumbre:>7.2f}x "
                 f"{m.pct_a_usar:>9.5%} {'si' if m.confiable else 'NO':>10}")
    l.append("-" * 72)
    l.append("Se usa el MAXIMO, no el promedio: equivocarse por pesimista")
    l.append("cuesta oportunidades; por optimista cuesta plata.")
    l.append(f"El margen va de 3,00x con una muestra a 1,25x con "
             f"{MINIMO_MUESTRAS}, anclado a lo medido.")
    return "\n".join(l)
