#!/usr/bin/env bash
# Manda el informe de cierre del dia por Telegram. UNA vez al dia.
set -uo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export PATH="<HOME>/.local/bin:/usr/local/bin:/usr/bin:/bin"
LAB="$HOME/trading-lab"
TXT=$("$LAB/.venv/bin/python" -W ignore "$LAB/scripts/informe_dia.py" 2>/dev/null)
if [ -z "$TXT" ]; then
  echo "$(date '+%F %T') informe_dia: salida VACIA" >>"$HOME/logs/avisos-no-enviados.log"
  "$HOME/bin/avisar-telegram.sh" "🔴 Trading lab: el informe del dia salio vacio" >/dev/null 2>&1
  exit 1
fi
# Telegram corta cerca de 4096 caracteres.
if "$HOME/bin/avisar-telegram.sh" "$(echo "$TXT" | head -c 3800)" >/dev/null 2>&1; then
  echo "$(date '+%F %T') informe del dia entregado" >>"$HOME/logs/trading-lab-avisos.log"
else
  echo "$(date '+%F %T') informe_dia: no pude avisar" >>"$HOME/logs/avisos-no-enviados.log"
  exit 1
fi
# Copia a disco: si Telegram falla, el informe no se pierde.
mkdir -p "$LAB/experimentos/informes"
echo "$TXT" > "$LAB/experimentos/informes/$(date +%F).txt"
exit 0
