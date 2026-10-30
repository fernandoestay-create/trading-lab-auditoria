#!/usr/bin/env bash
# Demostracion del laboratorio. No necesita credencial ni internet.
# Uso:  ~/trading-lab/scripts/probar.sh
set -uo pipefail
LAB="$HOME/trading-lab"; cd "$LAB" || exit 1
PY="$LAB/.venv/bin/python"
L() { printf '\n\033[1m%s\033[0m\n%s\n' "$1" "$(printf '=%.0s' {1..72})"; }

L "1. QUE HACE: el motor de riesgo rechaza una orden mala"
$PY - <<'PY'
import sys; sys.path.insert(0,'<HOME>/trading-lab')
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from labcore.riesgo import *

spec = InstrumentSpec("EURUSD",100_000,0.00001,1.0,0.01,0.01,0.01,"USD_MAJOR")
m = RiskEngine(RiskLimits(), KillSwitch(Path(tempfile.mkdtemp())/'k.json'))
cta = AccountState(10_000,10_000,9_000,1_000,10_000,0.0)
q = Quote("EURUSD",1.08000,1.08002,datetime.now(timezone.utc),0.00002,0.004)

casos = [
  ("orden sana",            dict(volume=0.09, stop_loss=1.07500)),
  ("sin stop loss",         dict(volume=0.09, stop_loss=None)),
  ("arriesga mas del 0,5%", dict(volume=0.50, stop_loss=1.07500)),
  ("stop al lado al reves", dict(volume=0.09, stop_loss=1.09000)),
]
for nombre, kw in casos:
    o = ProposedOrder("id-1","EURUSD",Side.BUY,reference_price=1.08002,**kw)
    d = m.evaluar(o, cta, spec, q)
    print(f"  {nombre:<24} -> {'APROBADA' if d.approved else 'RECHAZADA: '+d.reason_text}")
print()
print("  " + m.resumen())
PY

L "2. QUE NO HACE: no puede enviar ordenes. El codigo no existe."
$PY -c "
import sys; sys.path.insert(0,'<HOME>/trading-lab')
from labcore.exness.cliente import ClienteLectura
pub = [x for x in dir(ClienteLectura) if not x.startswith('_')]
print('  metodos del cliente de Exness:', ', '.join(sorted(pub)))
print()
print('  Ninguno envia, modifica ni cancela una orden. No estan desactivados:')
print('  no existen. Un cerrojo rompe la importacion si alguien agrega uno.')
"

L "3. EL JUEZ no certifica nada sobre datos sin señal"
$PY scripts/prueba_del_juez.py 2>&1 | grep -E "^(1|2|3|4|5|6|7|8|9) |VEREDICTO|NINGUNA|estrategia  " | head -12
$PY scripts/prueba_del_juez.py >/dev/null 2>&1 && echo "  --> PASA: sobre 3 paseos aleatorios no certifico ninguna" || echo "  --> FALLA"

L "4. ...pero SI detecta una ventaja cuando existe de verdad"
$PY scripts/prueba_de_potencia.py 2>&1 | grep -E "CALIFICAN|ruptura-10|SOBREVIVE" | head -4
$PY scripts/prueba_de_potencia.py >/dev/null 2>&1 && echo "  --> PASA: detecto el momentum inyectado" || echo "  --> FALLA"

L "5. COMO SE CONECTA CON EXNESS (hoy: sin credencial)"
$PY scripts/leer_costos_reales.py 2>&1 | head -8

L "6. TODO QUEDA ESCRITO EN DISCO, auditable"
$PY -c "
import duckdb, os
os.chdir('<HOME>/trading-lab')
print(duckdb.sql('''SELECT etiqueta, count(*) AS corridas,
  round(max(CAST(r.desempeno.sharpe AS DOUBLE)),3) AS sharpe_max
  FROM read_json_auto('experimentos/corridas.jsonl'), UNNEST(resultados) AS u(r)
  GROUP BY etiqueta''').to_df().to_string(index=False))
"
echo
echo "Para auditar una corrida y ver sobre QUE datos se midio:"
echo "  ~/bin/lab python -c \"from labcore.experimentos import RegistroExperimentos as R; print(R().auditar(R().corridas()[0]['run_id']))\""
