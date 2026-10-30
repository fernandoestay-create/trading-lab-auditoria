"""Informe de cierre del dia, en lenguaje de dueno, no de programador.

Fernando pidio: "no me mandes los datos, al final del dia dime las
operaciones, como ganaste o perdiste, y que aprendiste". Esto es eso.

Tres bloques, en este orden:
  1. COMO SALIMOS: el resultado, en plata.
  2. QUE PASO: las operaciones, con su razon de apertura y de cierre.
  3. QUE APRENDIMOS: lo que los numeros permiten concluir y, sobre todo,
     lo que NO permiten. Un dia no es una ventaja.
Y al final, los problemas OPERATIVOS: latencia, errores, disponibilidad.
"""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labcore.telemetria import informe as informe_tel, leer as leer_tel


def deals_demo(horas: int = 24):
    """Operaciones REALES ejecutadas en la cuenta demo, leidas del broker.

    Es la fuente de verdad: lo que diga esto es lo que paso, por encima de
    cualquier registro local.
    """
    try:
        from labcore.exness.cliente import ClienteLectura
        from labcore.exness.entorno import cargar
        from labcore.exness.firma import Credencial
        cfg = cargar()
        c = ClienteLectura(Credencial(cfg.api_key, cfg.private_key_path,
                                      cfg.account_id, cfg.discovery_base_url))
        try:
            desde = (datetime.now(timezone.utc) -
                     timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%SZ")
            ds = c.historial_operaciones(desde)
            snap = c.estado_cuenta()
            return ds, snap, None
        finally:
            c.desconectar()
    except Exception as e:
        return [], {}, f"{type(e).__name__}: {e}"

BASE = Path.home() / "trading-lab" / "papel"
MINIMO_PARA_CONCLUIR = 30


def main() -> int:
    hoy = datetime.now(timezone.utc).date()
    desde = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    c = json.loads((BASE / "cartera.json").read_text())
    f = BASE / "tratos.jsonl"
    todos = [json.loads(l) for l in f.read_text().splitlines() if l.strip()] if f.exists() else []
    dia = [t for t in todos if t["cerrada_en"][:10] == str(hoy)]

    L = []
    L.append("=" * 68)
    L.append(f"CIERRE DEL DIA — {hoy}   (operaciones FICTICIAS, no es dinero real)")
    L.append("=" * 68)

    # ---------- 0. LA CUENTA DEMO REAL, que es lo que importa ----------
    ds, snap, err = deals_demo()
    L.append("")
    L.append("CUENTA DEMO DE EXNESS — lo que de verdad paso")
    L.append("-" * 44)
    if err:
        L.append(f"  NO pude leer la cuenta: {err[:120]}")
        L.append("  ATENCION: sin esto el informe esta incompleto.")
    else:
        st = snap.get("account_state", {})
        abiertas = snap.get("positions") or []
        cierres = [d.get("deal", d) for d in ds
                   if (d.get("deal", d) or {}).get("type") == "close"]
        # OJO: no usar 'c' como variable de bucle aqui -- pisa la cartera
        # que se carga mas abajo. Me paso y el informe exploto.
        res = sum(float(((op.get("profit") or {}).get("amount")) or 0)
                  for op in cierres)
        L.append(f"  saldo                  US$ {float(st.get('balance', 0)):8.2f}")
        L.append(f"  patrimonio             US$ {float(st.get('equity', 0)):8.2f}")
        L.append(f"  posiciones abiertas    {len(abiertas)}")
        L.append(f"  operaciones cerradas   {len(cierres)} en 24 h")
        if cierres:
            g = [op for op in cierres
                 if float(((op.get("profit") or {}).get("amount")) or 0) > 0]
            L.append(f"  resultado              US$ {res:+8.2f}  "
                     f"({len(g)} ganadas, {len(cierres)-len(g)} perdidas)")
            L.append("")
            L.append("  operacion por operacion:")
            for op in cierres:
                pr = float(((op.get("profit") or {}).get("amount")) or 0)
                L.append(f"    {str(op.get('create_time',''))[11:16]}  "
                         f"{op.get('instrument',''):<10} "
                         f"{op.get('direction',''):<5} "
                         f"{'GANO ' if pr > 0 else 'PERDIO'} "
                         f"US$ {pr:+7.2f}   @ {op.get('price','')}")
        else:
            L.append("  Hoy no se cerro ninguna operacion en la demo.")
        if abiertas:
            L.append("")
            L.append("  abiertas ahora:")
            for p in abiertas:
                L.append(f"    {p.get('instrument',''):<10} "
                         f"{p.get('direction',''):<5} {p.get('volume','')} "
                         f"@ {p.get('open_price','')}   swap {p.get('swap','0')}")
                if str(p.get("swap", "0")) not in ("0", "0.0", ""):
                    L.append("    ATENCION: esta posicion pago SWAP. La regla "
                             "de intradia deberia haberla cerrado antes.")

    # ---------- 1. COMO SALIMOS (simulacion en papel, para comparar) ----------
    cap = c["capital_inicial"]
    realizado_dia = sum(t["pnl_neto"] for t in dia)
    realizado_total = sum(t["pnl_neto"] for t in todos)
    L.append("")
    L.append("SIMULACION EN PAPEL (corre en paralelo, para comparar)")
    L.append("-" * 44)
    if not dia:
        L.append("  Hoy no se cerro ninguna operacion.")
    else:
        g = [t for t in dia if t["pnl_neto"] > 0]
        L.append(f"  resultado de HOY       US$ {realizado_dia:+8.2f}")
        L.append(f"  operaciones            {len(dia)}  ({len(g)} ganadas, "
                 f"{len(dia)-len(g)} perdidas)")
        L.append(f"  la mejor               US$ {max(t['pnl_neto'] for t in dia):+8.2f}")
        L.append(f"  la peor                US$ {min(t['pnl_neto'] for t in dia):+8.2f}")
    L.append(f"  capital inicial        US$ {cap:8.2f}")
    L.append(f"  equity ahora           US$ {c['equity']:8.2f}  "
             f"({(c['equity']-cap)/cap:+.2%} acumulado)")
    L.append(f"  posiciones abiertas    {len(c['abiertas'])}")
    L.append(f"  acumulado desde el inicio  US$ {realizado_total:+.2f} "
             f"en {len(todos)} operaciones")

    # ---------- 2. QUE PASO ----------
    if dia:
        L.append("")
        L.append("QUE PASO, operacion por operacion")
        L.append("-" * 68)
        for t in dia:
            signo = "GANO " if t["pnl_neto"] > 0 else "PERDIO"
            L.append(f"  {t['cerrada_en'][11:16]}  {t['instrumento']:<9} "
                     f"{t['side']:<5} {signo} US$ {t['pnl_neto']:+7.2f}  "
                     f"({t['resultado_r']:+.2f}R)")
            L.append(f"            abrio por: {t['razon_apertura']}")
            L.append(f"            cerro por: {t['razon_cierre']}")

    # ---------- 3. QUE APRENDIMOS ----------
    L.append("")
    L.append("QUE APRENDIMOS")
    L.append("-" * 44)
    n = len(todos)
    if n < MINIMO_PARA_CONCLUIR:
        L.append(f"  Con {n} operaciones NO se puede concluir nada todavia.")
        L.append(f"  Hacen falta {MINIMO_PARA_CONCLUIR} para que una cifra")
        L.append(f"  signifique algo, y ~100 para confiar en ella.")
    else:
        rs = [t["resultado_r"] for t in todos]
        gan = sum(1 for r in rs if r > 0)
        L.append(f"  {n} operaciones: {gan} aciertos ({gan/n:.0%}), "
                 f"{sum(rs):+.2f}R acumulados, {sum(rs)/n:+.3f}R por operacion")
        # el resultado depende de UNA operacion afortunada?
        sin_mejor = sum(rs) - max(rs)
        if sum(rs) > 0 and sin_mejor <= 0:
            L.append("  ATENCION: todo el resultado viene de UNA operacion. "
                     "Eso es suerte, no ventaja.")
        # por estrategia y por direccion
        for clave, titulo in (("estrategia", "por estrategia"),
                              ("side", "por direccion")):
            g = defaultdict(list)
            for t in todos:
                g[t[clave]].append(t["resultado_r"])
            partes = [f"{k}: {sum(v):+.1f}R en {len(v)}" for k, v in
                      sorted(g.items(), key=lambda kv: -sum(kv[1]))]
            L.append(f"  {titulo}  " + "   ".join(partes[:4]))
        # concentracion direccional
        lados = Counter(t["side"] for t in todos)
        dom = lados.most_common(1)[0]
        if dom[1] / n > 0.7:
            L.append(f"  {dom[1]} de {n} fueron {dom[0]}. Eso es UNA apuesta "
                     f"direccional, no diversificacion: si el mercado gira, "
                     f"pierden juntas.")
        # motivo de cierre
        mot = Counter(t["razon_cierre"] for t in todos)
        L.append("  cierres  " + "   ".join(f"{k}: {v}" for k, v in mot.most_common()))

    # ---------- 4. PROBLEMAS OPERATIVOS ----------
    tel = [m for m in leer_tel() if str(m.get("ts", "")) >= desde]
    L.append("")
    L.append("PROBLEMAS OPERATIVOS (ultimas 24 h)")
    L.append("-" * 44)
    errs = [m for m in tel if m.get("tipo") == "error"]
    pasadas = [m for m in tel if m.get("tipo") == "pasada"]
    ant = [float(m["valor"]) for m in tel
           if m.get("tipo") == "antiguedad_dato" and m.get("valor") is not None]
    lat = [float(m["ms"]) for m in tel
           if m.get("tipo") == "latencia_api" and m.get("ms") is not None]
    if pasadas:
        ok = sum(1 for m in pasadas if m.get("detalle", {}).get("ok"))
        L.append(f"  pasadas            {len(pasadas)}   completas {ok}   "
                 f"disponibilidad {ok/len(pasadas):.1%}")
        esperadas = 24 * 12          # cada 5 min
        if len(pasadas) < esperadas * 0.9:
            L.append(f"  ATENCION: se esperaban ~{esperadas} pasadas y hubo "
                     f"{len(pasadas)}. Faltaron {esperadas-len(pasadas)}.")
    if lat:
        lat.sort()
        L.append(f"  latencia de datos  mediana {lat[len(lat)//2]:.0f} ms   "
                 f"peor {max(lat):.0f} ms")
    if ant:
        ant.sort()
        L.append(f"  antiguedad al decidir  mediana {ant[len(ant)//2]:.0f}s   "
                 f"peor {max(ant):.0f}s")
    if errs:
        c2 = Counter((m.get("detalle", {}).get("excepcion") or "?") for m in errs)
        L.append(f"  errores            {len(errs)}: " +
                 ", ".join(f"{k} x{v}" for k, v in c2.most_common(4)))
    else:
        L.append("  errores            ninguno")
    L.append("")
    L.append("=" * 68)
    L.append("Recordatorio: spread MEDIDO de la cuenta, pero la ejecucion de")
    L.append("una demo es mejor que la real (no hay slippage ni requotes).")
    L.append("=" * 68)

    texto = "\n".join(L)
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
