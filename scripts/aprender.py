"""Aprender del diario de operaciones de papel.

No "entrena" nada: MIDE. Lee cada trato ficticio y responde preguntas que
cambian decisiones: que estrategia aporta y cual resta, en que instrumento,
a que hora, y si el resultado se explica por una sola operacion con suerte.

El resultado se expresa en R (multiplos del riesgo inicial) para poder
comparar operaciones de instrumentos con precios muy distintos.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RUTA = Path.home() / "trading-lab" / "papel" / "tratos.jsonl"


def cargar() -> list[dict]:
    if not RUTA.exists():
        return []
    return [json.loads(l) for l in RUTA.read_text(encoding="utf-8").splitlines() if l.strip()]


def agrupar(tratos: list[dict], clave) -> list[tuple]:
    g = defaultdict(list)
    for t in tratos:
        g[clave(t)].append(t)
    filas = []
    for k, ts in g.items():
        rs = [t["resultado_r"] for t in ts]
        gan = [r for r in rs if r > 0]
        filas.append((k, len(ts), sum(rs), sum(rs) / len(ts),
                      len(gan) / len(ts), max(rs), min(rs)))
    return sorted(filas, key=lambda f: -f[2])


def tabla(titulo: str, filas: list[tuple], ancho: int = 22) -> None:
    print(f"\n{titulo}")
    print(f"{'':<{ancho}} {'ops':>4} {'total R':>9} {'prom R':>8} "
          f"{'aciertos':>9} {'mejor':>7} {'peor':>7}")
    print("-" * (ancho + 48))
    for k, n, tot, prom, win, mx, mn in filas:
        print(f"{str(k):<{ancho}} {n:>4} {tot:>+9.2f} {prom:>+8.3f} "
              f"{win:>8.1%} {mx:>+7.2f} {mn:>+7.2f}")


def main() -> int:
    ts = cargar()
    if not ts:
        print("Todavia no hay ninguna operacion de papel cerrada.")
        print(f"El diario vive en {RUTA}")
        print("El operador corre cada 15 minutos; dale tiempo.")
        return 0

    total_r = sum(t["resultado_r"] for t in ts)
    total_usd = sum(t["pnl_neto"] for t in ts)
    gan = [t for t in ts if t["pnl_neto"] > 0]
    print("=" * 72)
    print(f"DIARIO DE PAPEL — {len(ts)} operaciones cerradas")
    print("=" * 72)
    print(f"resultado      US$ {total_usd:+,.2f}   ({total_r:+.2f}R)")
    print(f"aciertos       {len(gan)}/{len(ts)} ({len(gan)/len(ts):.1%})")
    print(f"promedio       {total_r/len(ts):+.3f}R por operacion")

    # ¿El resultado depende de UNA sola operacion afortunada?
    rs = sorted((t["resultado_r"] for t in ts), reverse=True)
    if len(rs) > 1:
        sin_mejor = total_r - rs[0]
        print(f"sin la mejor   {sin_mejor:+.2f}R", end="")
        if total_r > 0 and sin_mejor <= 0:
            print("   ATENCION: todo el resultado viene de UNA operacion")
        else:
            print()

    tabla("POR ESTRATEGIA", agrupar(ts, lambda t: t["estrategia"]))
    tabla("POR INSTRUMENTO", agrupar(ts, lambda t: t["instrumento"]))
    tabla("POR DIRECCION", agrupar(ts, lambda t: t["side"]), ancho=10)
    tabla("POR MOTIVO DE CIERRE", agrupar(ts, lambda t: t["razon_cierre"]))
    tabla("POR HORA DE ENTRADA (UTC)",
          agrupar(ts, lambda t: f"{t['abierta_en'][11:13]}:00"), ancho=10)

    print()
    print("QUE SE APRENDE, en seco:")
    por_est = agrupar(ts, lambda t: t["estrategia"])
    malas = [f for f in por_est if f[2] < 0 and f[1] >= 5]
    for k, n, tot, prom, *_ in malas:
        print(f"  - {k} resta {tot:+.2f}R en {n} operaciones: candidata a retirar")
    if len(ts) < 30:
        print(f"  - con {len(ts)} operaciones NO se puede concluir nada todavia.")
        print(f"    Hacen falta al menos 30, y 100 para que signifique algo.")
    if not malas and len(ts) >= 30:
        print("  - ninguna estrategia resta de forma clara todavia.")
    print()
    print("ADVERTENCIA: son operaciones FICTICIAS sobre precios reales, con")
    print("spread MODELADO (no medido en la cuenta). No es dinero real y no")
    print("es evidencia de rentabilidad futura.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
