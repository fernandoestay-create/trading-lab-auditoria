#!/usr/bin/env bash
# Una pasada del operador EN VIVO sobre la cuenta DEMO de Exness.
# Envia ordenes de verdad, con dinero de practica. La cuenta real sigue
# bloqueada y requiere autorizacion escrita aparte.
set -uo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export PATH="<HOME>/.local/bin:/usr/local/bin:/usr/bin:/bin"
LAB="$HOME/trading-lab"
AVISAR="$HOME/bin/avisar-telegram.sh"

# Una pasada a la vez. Dos procesos mandando ordenes a la misma cuenta es
# la forma mas rapida de abrir el doble de lo que se quiso.
exec 9>"$HOME/.trading-lab-demo.lock"
if ! flock -n 9; then
  echo "otra pasada esta corriendo; esta se salta"
  exit 0
fi

SAL=$(systemd-run --user --quiet --pipe --wait --slice=trading-lab.slice \
  --nice=10 -p MemoryMax=1536M -p "Environment=PYTHONWARNINGS=ignore" \
  --working-directory="$LAB" \
  -- "$LAB/.venv/bin/python" -W ignore scripts/operar_demo.py --enviar 2>&1)
rc=$?
echo "$SAL"

if [ -z "$SAL" ]; then
  echo "ATENCION: pasada VACIA (rc=$rc)"
  echo "$(date '+%F %T') demo: pasada VACIA rc=$rc" >>"$HOME/logs/avisos-no-enviados.log"
  exit 1
fi

# Solo avisa de EMERGENCIAS. Las operaciones van en el informe del dia.
URG=$(echo "$SAL" | grep -E "KILL SWITCH|ERROR DEL BROKER|NO pude cerrar|ABORTO" || true)
if [ -n "$URG" ] && [ -x "$AVISAR" ]; then
  "$AVISAR" "🔴 Trading demo — algo que requiere tu atencion:

$URG" >/dev/null 2>&1 \
    && echo "$(date '+%F %T') aviso de emergencia entregado" >>"$HOME/logs/trading-lab-avisos.log"
fi
exit 0
