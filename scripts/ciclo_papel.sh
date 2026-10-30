#!/usr/bin/env bash
# Una pasada del operador de papel + aviso a Telegram si hubo movimiento.
# Lo llama el cron cada 15 minutos. No toca Exness. No mueve un peso.
set -uo pipefail
LAB="$HOME/trading-lab"

# UNA pasada a la vez. Si una se alarga (40 llamadas de red), el cron de
# los 5 minutos dispara la siguiente y se solapan: dos procesos escriben
# la misma cartera y el resultado es cualquiera. Tres pasadas vacias el
# 2026-10-30 apuntaban a esto. -n = si ya hay una corriendo, sale sin
# hacer nada y lo dice (no es un error).
exec 9>"$HOME/.trading-lab-papel.lock"
if ! flock -n 9; then
  echo "otra pasada esta corriendo; esta se salta (no es un error)"
  exit 0
fi

# El cron arranca con un entorno MINIMO y systemd-run --user necesita la
# sesion de usuario. Sin esto fallaba en silencio y salia con 0: tres
# ciclos sin dejar rastro y nadie se enteraba (verificado 2026-10-29).
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
export PATH="<HOME>/.local/bin:/usr/local/bin:/usr/bin:/bin"
AVISAR="$HOME/bin/avisar-telegram.sh"
# PYTHONWARNINGS=ignore y -W ignore: yfinance arrastra avisos de pandas que
# ensucian el log y esconden lo que importa. Los errores reales siguen
# saliendo porque el script los imprime el mismo.
SAL=$(systemd-run --user --quiet --pipe --wait --slice=trading-lab.slice \
  --nice=15 -p IOSchedulingClass=idle -p MemoryMax=1536M \
  -p "Environment=PYTHONWARNINGS=ignore" \
  --working-directory="$LAB" \
  -- "$LAB/.venv/bin/python" -W ignore scripts/operar_papel.py 2>/dev/null)
rc=$?
echo "$SAL"
# Un fallo silencioso es peor que un fallo: si no produjo NADA, se acusa.
if [ -z "$SAL" ]; then
  echo "ATENCION: el operador no produjo ninguna salida (rc=$rc). "\
       "Probablemente systemd-run --user no pudo arrancar."
  echo "$(date '+%F %T') papel: pasada VACIA, rc=$rc" \
    >>"$HOME/logs/avisos-no-enviados.log"
  [ -x "$AVISAR" ] && "$AVISAR" "🔴 Trading de papel: el operador no
produjo ninguna salida. Revisa ~/logs/trading-lab-papel-cron.log" \
    >/dev/null 2>&1
  exit 1
fi
# AVISOS POR OPERACION: APAGADOS.
# Fernando, 2026-10-30: "no me mandes los datos, al final del dia dime las
# operaciones, como ganaste o perdiste y que aprendiste". El informe de
# cierre lo manda informe_dia.py una vez al dia. Aqui solo se avisa de
# emergencias (el bloque de abajo, cuando la pasada sale vacia).
AVISAR_POR_OPERACION=no
EV=$(echo "$SAL" | grep -E "^(ABRE|CIERRA) " || true)
if [ "$AVISAR_POR_OPERACION" = "si" ] && [ -n "$EV" ] && [ -x "$AVISAR" ]; then
  RES=$(echo "$SAL" | sed -n '/^capital inicial/,/^aciertos/p')
  if "$AVISAR" "📄 Trading de PAPEL (ficticio, no es dinero real)

$EV

$RES" >/dev/null 2>&1; then
    # Se registra el envio EXITOSO. Antes solo se anotaban los fallos, asi
    # que no habia forma de contar cuantos avisos se mandaron de verdad.
    echo "$(date '+%F %T') aviso entregado: $(echo "$EV" | tr '\n' ';')" \
      >>"$HOME/logs/trading-lab-avisos.log"
  else
    echo "$(date '+%F %T') papel: no pude avisar" \
      >>"$HOME/logs/avisos-no-enviados.log"
  fi
fi
exit $rc
