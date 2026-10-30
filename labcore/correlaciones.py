"""Grupos de correlacion DERIVADOS de los datos, no escritos a mano.

Los grupos que puse a mano (CRYPTO, METALS, EQUITY_US...) son etiquetas de
categoria, no de riesgo. Medido sobre 1.984 dias:

  BTCUSD / ETHUSD   +0,83   -> la MISMA apuesta
  QQQ    / SPY      +0,94   -> el MISMO activo
  XAUUSD / XAGUSD   +0,78   -> la misma apuesta
  BTCUSD / WTI      +0,03   -> de verdad distintos

Con etiquetas a mano, operar BTCUSD y ETHUSD a la vez "diversifica". Con
la correlacion medida, es una sola posicion del doble de tamano. Esa
diferencia es la que vacia cuentas.

La cobertura se CALCULA, no se mantiene a mano: toda lista escrita a mano
se desincroniza de la realidad.
"""

from __future__ import annotations

import json
from pathlib import Path

CACHE = Path.home() / "trading-lab" / "config" / "grupos_correlacion.json"

# Umbral para considerar dos instrumentos "el mismo riesgo". 0,70 es alto a
# proposito: por debajo de eso hay diversificacion real aunque imperfecta.
UMBRAL = 0.70


def agrupar(matriz: dict[str, dict[str, float]],
            umbral: float = UMBRAL) -> dict[str, str]:
    """Une en un grupo todo lo que esta correlacionado por encima del umbral.

    Es union-find simple: si A~B y B~C, los tres quedan en el mismo grupo
    aunque A y C no lleguen al umbral entre si. Es lo conservador: el
    riesgo se propaga por la cadena.
    """
    padre: dict[str, str] = {k: k for k in matriz}

    def raiz(x: str) -> str:
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for a in matriz:
        for b, v in matriz[a].items():
            if a != b and b in padre and abs(v) >= umbral:
                ra, rb = raiz(a), raiz(b)
                if ra != rb:
                    padre[rb] = ra

    # Nombre del grupo: el miembro alfabeticamente primero, para que sea
    # estable entre corridas y legible en los logs.
    miembros: dict[str, list[str]] = {}
    for k in padre:
        miembros.setdefault(raiz(k), []).append(k)
    out = {}
    for r, ms in miembros.items():
        nombre = f"GRUPO_{sorted(ms)[0]}" if len(ms) > 1 else f"SOLO_{ms[0]}"
        for m in ms:
            out[m] = nombre
    return out


def guardar(grupos: dict[str, str], matriz: dict | None = None,
            ruta: Path | None = None) -> None:
    f = ruta or CACHE
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(
        {"umbral": UMBRAL, "grupos": grupos,
         "matriz": matriz or {}}, indent=2, ensure_ascii=False),
        encoding="utf-8")


def cargar(ruta: Path | None = None) -> dict[str, str]:
    """Grupos medidos. Si no hay archivo, devuelve vacio y quien llame
    tiene que decidir -- NO se inventa un grupo por defecto, porque un
    grupo equivocado hace pasar riesgo concentrado por diversificado."""
    f = ruta or CACHE
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("grupos", {})
    except (json.JSONDecodeError, OSError):
        return {}


def grupo_de(instrumento: str, grupos: dict[str, str] | None = None,
             respaldo: str = "") -> str:
    g = grupos if grupos is not None else cargar()
    if instrumento in g:
        return g[instrumento]
    # Sin medicion: se devuelve el respaldo que pase quien llama, y si no
    # hay, un grupo PROPIO del instrumento. Nunca se lo mete en un grupo
    # ajeno por adivinanza.
    return respaldo or f"SIN_MEDIR_{instrumento}"


def informe(ruta: Path | None = None) -> str:
    f = ruta or CACHE
    if not f.exists():
        return "No hay grupos medidos todavia. Corre scripts/medir_correlaciones.py"
    d = json.loads(f.read_text(encoding="utf-8"))
    g = d.get("grupos", {})
    por: dict[str, list[str]] = {}
    for ins, gr in g.items():
        por.setdefault(gr, []).append(ins)
    l = [f"GRUPOS DE RIESGO MEDIDOS (umbral {d.get('umbral', UMBRAL):.2f})",
         "=" * 62]
    for gr, ms in sorted(por.items(), key=lambda kv: -len(kv[1])):
        marca = "  <- UNA sola apuesta" if len(ms) > 1 else ""
        l.append(f"  {gr:<22} {', '.join(sorted(ms))}{marca}")
    l.append("")
    l.append("Dos instrumentos del mismo grupo NO diversifican: el motor de")
    l.append("riesgo los trata como una posicion del tamano sumado.")
    return "\n".join(l)
