"""Telemetria operativa: lo que decide si esto puede operar de verdad.

Un backtest puede dar hermoso y el sistema ser inoperable en vivo. Lo que
mata un sistema automatico no suele ser la estrategia: es la plomeria.
Esto mide las seis cosas que importan y que nadie mide hasta que duele:

  1. LATENCIA de cada llamada a la API, por endpoint. Si pedir un precio
     tarda 2 segundos, la señal ya es vieja cuando llega la orden.
  2. ANTIGUEDAD DEL DATO: cuanto tiempo paso entre el cierre de la vela y
     el momento en que la decidimos usar.
  3. TIEMPO DE REACCION: de la senal al envio de la orden.
  4. ERRORES por tipo y por codigo. Un 429 no es lo mismo que un 1001.
  5. DISPONIBILIDAD: pasadas que corrieron contra pasadas que debieron.
  6. DESLIZAMIENTO: precio que pedi contra precio al que me llenaron.

Todo se escribe a disco. Una metrica que no persiste es una anecdota.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

RUTA = Path.home() / "trading-lab" / "experimentos" / "telemetria.jsonl"


@dataclass
class Medicion:
    ts: str
    tipo: str                 # latencia_api | antiguedad_dato | reaccion | error | pasada | deslizamiento
    nombre: str               # endpoint, instrumento o etapa
    ms: float | None = None
    valor: float | None = None
    detalle: dict = field(default_factory=dict)


def anotar(m: Medicion, ruta: Path | None = None) -> None:
    f = ruta or RUTA
    f.parent.mkdir(parents=True, exist_ok=True)
    linea = json.dumps(asdict(m), ensure_ascii=False) + "\n"
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(linea)
        fh.flush()
        os.fsync(fh.fileno())


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def medir(tipo: str, nombre: str, ruta: Path | None = None, **detalle):
    """Mide cuanto tarda un bloque y lo anota, incluso si lanza.

    Si lanza, se anota como error CON su duracion: una llamada que falla
    a los 20 segundos informa distinto que una que falla al instante.
    """
    t0 = time.perf_counter()
    try:
        yield
    except Exception as e:
        anotar(Medicion(ahora(), "error", nombre,
                        ms=(time.perf_counter() - t0) * 1000,
                        detalle={**detalle, "excepcion": type(e).__name__,
                                 "mensaje": str(e)[:200]}), ruta)
        raise
    else:
        anotar(Medicion(ahora(), tipo, nombre,
                        ms=(time.perf_counter() - t0) * 1000,
                        detalle=detalle), ruta)


def antiguedad_del_dato(ts_vela: datetime, nombre: str,
                        ruta: Path | None = None) -> float:
    """Segundos entre el cierre de la vela y ahora. Es la ventana de
    ceguera: si es grande, decidimos con informacion vieja."""
    seg = (datetime.now(timezone.utc) - ts_vela).total_seconds()
    anotar(Medicion(ahora(), "antiguedad_dato", nombre, valor=seg), ruta)
    return seg


def deslizamiento(nombre: str, pedido: float, obtenido: float, side: str,
                  ruta: Path | None = None) -> float:
    """Diferencia entre el precio que pedi y el que me dieron, EN CONTRA.

    Positivo = me fue peor que lo pedido. Es el costo invisible que un
    backtest asume en cero y que en vivo aparece.
    """
    peor = (obtenido - pedido) if side.upper() == "BUY" else (pedido - obtenido)
    anotar(Medicion(ahora(), "deslizamiento", nombre, valor=peor,
                    detalle={"pedido": pedido, "obtenido": obtenido,
                             "side": side,
                             "pct": peor / pedido if pedido else None}), ruta)
    return peor


# ---------------- lectura e informe ----------------

def leer(ruta: Path | None = None) -> list[dict]:
    f = ruta or RUTA
    if not f.exists():
        return []
    out = []
    for i, l in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        l = l.strip()
        if not l:
            continue
        try:
            out.append(json.loads(l))
        except json.JSONDecodeError:
            out.append({"tipo": "CORRUPTA", "nombre": f"linea-{i}"})
    return out


def _percentil(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def informe(ruta: Path | None = None, desde: str | None = None) -> str:
    ms = leer(ruta)
    if desde:
        ms = [m for m in ms if str(m.get("ts", "")) >= desde]
    if not ms:
        return "Sin mediciones de telemetria todavia."

    l = ["=" * 78, "TELEMETRIA OPERATIVA", "=" * 78]

    # --- latencia por endpoint ---
    lat: dict[str, list[float]] = {}
    for m in ms:
        if m.get("tipo") == "latencia_api" and m.get("ms") is not None:
            lat.setdefault(m["nombre"], []).append(float(m["ms"]))
    if lat:
        l += ["", "LATENCIA DE LA API (milisegundos)",
              f"{'endpoint':<26} {'n':>5} {'mediana':>9} {'p90':>9} "
              f"{'p99':>9} {'peor':>9}", "-" * 72]
        for k, v in sorted(lat.items(), key=lambda kv: -_percentil(kv[1], 0.5)):
            l.append(f"{k:<26} {len(v):>5} {_percentil(v,0.5):>9.0f} "
                     f"{_percentil(v,0.9):>9.0f} {_percentil(v,0.99):>9.0f} "
                     f"{max(v):>9.0f}")

    # --- antiguedad del dato ---
    ant = [float(m["valor"]) for m in ms
           if m.get("tipo") == "antiguedad_dato" and m.get("valor") is not None]
    if ant:
        l += ["", "ANTIGUEDAD DEL DATO al decidir (segundos)",
              f"  mediana {_percentil(ant,0.5):.0f}s   p90 {_percentil(ant,0.9):.0f}s"
              f"   peor {max(ant):.0f}s   n={len(ant)}"]
        if _percentil(ant, 0.9) > 300:
            l.append("  ATENCION: 9 de cada 10 decisiones usan datos de mas de "
                     "5 minutos. Para intradia eso es mucho.")

    # --- tiempo de reaccion ---
    rea = [float(m["ms"]) for m in ms
           if m.get("tipo") == "reaccion" and m.get("ms") is not None]
    if rea:
        l += ["", "TIEMPO DE REACCION, de la senal al envio (ms)",
              f"  mediana {_percentil(rea,0.5):.0f}   p90 {_percentil(rea,0.9):.0f}"
              f"   peor {max(rea):.0f}   n={len(rea)}"]

    # --- deslizamiento ---
    des = [float(m["valor"]) for m in ms
           if m.get("tipo") == "deslizamiento" and m.get("valor") is not None]
    if des:
        contra = sum(1 for d in des if d > 0)
        l += ["", "DESLIZAMIENTO (positivo = peor que lo pedido)",
              f"  n={len(des)}   en contra {contra}/{len(des)}   "
              f"mediana {_percentil(des,0.5):+.4f}   peor {max(des):+.4f}"]

    # --- errores ---
    errs: dict[str, int] = {}
    for m in ms:
        if m.get("tipo") == "error":
            k = (m.get("detalle", {}).get("excepcion") or "?")
            msg = str(m.get("detalle", {}).get("mensaje") or "")
            for cod in ("1000", "1001", "1002", "3003", "3015", "429", "404", "403"):
                if cod in msg:
                    k = f"{k}/{cod}"
                    break
            errs[k] = errs.get(k, 0) + 1
    total_ops = sum(1 for m in ms if m.get("tipo") in ("latencia_api", "error"))
    l += ["", "ERRORES"]
    if errs:
        for k, v in sorted(errs.items(), key=lambda kv: -kv[1]):
            l.append(f"  {k:<30} {v:>5}")
        l.append(f"  tasa de error: {sum(errs.values())}/{total_ops} "
                 f"({sum(errs.values())/total_ops:.1%})" if total_ops else "")
    else:
        l.append("  ninguno")

    # --- disponibilidad ---
    pas = [m for m in ms if m.get("tipo") == "pasada"]
    if pas:
        ok = sum(1 for m in pas if m.get("detalle", {}).get("ok"))
        l += ["", "DISPONIBILIDAD",
              f"  pasadas {len(pas)}   completas {ok}   "
              f"disponibilidad {ok/len(pas):.1%}"]

    l.append("=" * 78)
    return "\n".join(l)
