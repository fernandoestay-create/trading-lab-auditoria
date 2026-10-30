"""Registro de experimentos: si no persiste, no es una metrica.

Esto existe por L-129 del workspace: el Revisor EIA se vendia con un "76%
de recall en backtesting" que nadie podia reproducir, porque el script
imprimia por pantalla y no escribia sus insumos a disco. El numero se
transcribio A MANO desde la consola y se replico a siete documentos.

Para que un numero de este laboratorio sea auditable hace falta guardar
cuatro cosas, no solo el resultado:
  1. QUE datos lo produjeron  -> huella sha256 de las barras exactas
  2. CON QUE parametros        -> costos, limites de riesgo, n_pruebas
  3. CON QUE codigo            -> sha de git, y si el arbol estaba sucio
  4. QUE salio                 -> metricas completas de CADA participante

Formato: JSONL append-only. Se elige sobre una base de datos a proposito:
es auditable con `grep`, versionable en git, y no se puede editar una
corrida pasada sin que el diff lo muestre. DuckDB lee JSONL directo, asi
que no se pierde capacidad de consulta.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

RUTA_DEFECTO = Path.home() / "trading-lab" / "experimentos" / "corridas.jsonl"


def huella_barras(barras) -> str:
    """sha256 de las barras EXACTAS que se usaron.

    Es lo que permite responder "¿sobre que lo mediste?" sin volver a
    correr nada. Si manana la serie cambia, la huella cambia y el numero
    viejo queda atado a datos que ya no existen -- visible, no silencioso.
    """
    h = hashlib.sha256()
    for b in barras:
        h.update(
            f"{b.ts.isoformat()}|{b.open!r}|{b.high!r}|{b.low!r}|"
            f"{b.close!r}|{b.volume!r}|{b.spread!r}\n".encode()
        )
    return h.hexdigest()


def version_codigo() -> dict[str, object]:
    """SHA de git y si el arbol estaba sucio.

    Un resultado producido con el arbol sucio NO es reproducible, y eso
    se registra en vez de ocultarse.
    """
    raiz = Path(__file__).resolve().parents[2]
    def _git(*args: str) -> str | None:
        try:
            return subprocess.run(
                ["git", "-C", str(raiz), *args],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout.strip()
        except (subprocess.SubprocessError, OSError, FileNotFoundError):
            return None
    sha = _git("rev-parse", "HEAD")
    estado = _git("status", "--porcelain")
    return {
        "git_sha": sha,
        "arbol_sucio": bool(estado) if estado is not None else None,
        "archivos_sucios": (
            [l[3:] for l in estado.splitlines()][:20] if estado else []
        ),
        "reproducible": bool(sha) and estado == "",
    }


def _serializable(x):
    if is_dataclass(x) and not isinstance(x, type):
        return {k: _serializable(v) for k, v in asdict(x).items()}
    if isinstance(x, dict):
        return {str(k): _serializable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_serializable(v) for v in x]
    if isinstance(x, datetime):
        return x.isoformat()
    if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))):
        # NaN e infinito no son JSON validos. Se guardan como texto para
        # que no se conviertan en null silenciosamente.
        return {"NaN": "NaN", "inf": "Infinity", "-inf": "-Infinity"}[
            "NaN" if x != x else ("inf" if x > 0 else "-inf")
        ]
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    return repr(x)


class RegistroExperimentos:
    def __init__(self, ruta: Path | None = None) -> None:
        self.ruta = ruta or RUTA_DEFECTO
        self.ruta.parent.mkdir(parents=True, exist_ok=True)

    def anotar_torneo(
        self,
        torneo,
        *,
        etiqueta: str,
        datos_descripcion: str,
        semilla: int | None = None,
        extra: dict | None = None,
    ) -> str:
        """Persiste una corrida completa y devuelve su identificador."""
        run_id = uuid.uuid4().hex[:12]
        califican = [p.strategy_id for p in torneo.califican()]
        fila = {
            "run_id": run_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "etiqueta": etiqueta,
            # --- 1. que datos ---
            "datos": {
                "descripcion": datos_descripcion,
                "semilla": semilla,
                "n_barras": len(torneo.barras),
                "huella_sha256": huella_barras(torneo.barras),
                "desde": torneo.barras[0].ts.isoformat() if torneo.barras else None,
                "hasta": torneo.barras[-1].ts.isoformat() if torneo.barras else None,
            },
            # --- 2. con que parametros ---
            "parametros": {
                "instrumento": _serializable(torneo.spec),
                "costos": _serializable(torneo.costos),
                "limites_riesgo": _serializable(torneo.limites),
                "capital_inicial": torneo.capital_inicial,
                "n_pruebas_declaradas": len(torneo.participantes),
            },
            # --- 3. con que codigo ---
            "codigo": version_codigo(),
            # --- 4. que salio, de CADA participante, no solo del ganador ---
            "resultados": [
                {
                    "strategy_id": p.strategy_id,
                    "familia": p.familia,
                    "puntaje": _serializable(torneo._puntaje(p.desempeno)),
                    "desempeno": _serializable(p.desempeno),
                    "resumen_corrida": p.resumen_corrida,
                }
                for p in torneo.ranking()
            ],
            "califican": califican,
            "veredicto": (
                "NINGUNA CALIFICA" if not califican
                else f"CALIFICAN {len(califican)} EN MUESTRA"
            ),
        }
        if extra:
            fila["extra"] = _serializable(extra)

        # Append atomico: se escribe la linea completa de una vez y se
        # fuerza a disco. Un corte no puede dejar media linea de JSON.
        linea = json.dumps(fila, ensure_ascii=False) + "\n"
        with open(self.ruta, "a", encoding="utf-8") as fh:
            fh.write(linea)
            fh.flush()
            os.fsync(fh.fileno())
        return run_id

    # ---------------- lectura y auditoria ----------------

    def corridas(self) -> list[dict]:
        if not self.ruta.exists():
            return []
        out = []
        for i, l in enumerate(self.ruta.read_text(encoding="utf-8").splitlines(), 1):
            l = l.strip()
            if not l:
                continue
            try:
                out.append(json.loads(l))
            except json.JSONDecodeError:
                # Una linea corrupta se DENUNCIA, no se salta en silencio.
                out.append({"run_id": f"CORRUPTA-linea-{i}", "error": l[:120]})
        return out

    def auditar(self, run_id: str) -> str:
        """Responde '¿sobre que lo mediste?' para una corrida concreta."""
        for c in self.corridas():
            if c.get("run_id") == run_id:
                d, cod = c["datos"], c["codigo"]
                ls = [
                    f"corrida {run_id}  ({c['ts']})",
                    f"etiqueta      : {c['etiqueta']}",
                    f"datos         : {d['descripcion']}",
                    f"                {d['n_barras']} barras, "
                    f"{d['desde']} -> {d['hasta']}",
                    f"huella datos  : {d['huella_sha256']}",
                    f"semilla       : {d['semilla']}",
                    f"codigo        : {cod['git_sha']} "
                    f"(reproducible: {cod['reproducible']})",
                    f"n_pruebas     : {c['parametros']['n_pruebas_declaradas']}",
                    f"veredicto     : {c['veredicto']}",
                    "",
                    "participantes (todos, no solo el ganador):",
                ]
                for r in c["resultados"]:
                    de = r["desempeno"]
                    ls.append(
                        f"  {r['strategy_id']:<26} ops={de['n_operaciones']:>4} "
                        f"sharpe={de['sharpe']} desinf={de['sharpe_desinflado']} "
                        f"t={de['t_stat']}"
                    )
                return "\n".join(ls)
        return f"no existe la corrida {run_id} en {self.ruta}"
