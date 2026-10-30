#!/usr/bin/env bash
# Centinela del laboratorio de trading. Corre diario sin supervision.
#
# Hace TRES cosas, en orden de importancia:
#
#  1. VIGILA AL JUEZ. Corre las dos pruebas de calibracion. Si el juez
#     empieza a certificar estrategias sobre ruido, eso es la falla mas
#     grave posible y tiene que gritar. Ya paso una vez (2026-10-28: el
#     Sharpe se anualizaba con sqrt(252) e inflaba 7 veces).
#
#  2. ESPERA LA CREDENCIAL y, cuando aparece, corre la etapa 1 sola:
#     lee los costos REALES de la cuenta. Verifica POR EFECTO que el
#     archivo quedo escrito con contenido, no por codigo de salida.
#
#  3. REGISTRA LA OBSERVACION, no solo el resultado. "No habia nada" y
#     "no pude mirar" se escriben igual si no se anota que se miro.
#
# Avisa con ~/bin/avisar-telegram.sh, que devuelve 0 solo si Telegram
# confirma ok:true. NUNCA con `hermes send`: da "Timed out" con token
# valido (L-203 a L-206).
set -uo pipefail

LAB="$HOME/trading-lab"
LOG="$HOME/logs/trading-lab.log"
AUDIT="$HOME/trading-lab/experimentos/audit_centinela.jsonl"
ENVF="$HOME/.config/exness/env"
COSTOS="$LAB/config/costos_reales.json"
MARCA="$LAB/config/.etapa1_hecha"
AVISAR="$HOME/bin/avisar-telegram.sh"
HOY=$(date +%F)
mkdir -p "$(dirname "$LOG")" "$(dirname "$AUDIT")" "$LAB/config"

log() { echo "[$(date '+%F %T')] $*" >>"$LOG"; }
avisar() {
  if [ -x "$AVISAR" ] && "$AVISAR" "$1" >/dev/null 2>&1; then
    log "aviso entregado"
  else
    log "ATENCION: no pude avisar por Telegram"
    echo "$(date '+%F %T') trading-lab: $1" >>"$HOME/logs/avisos-no-enviados.log"
  fi
}

# Observaciones que se registran SIEMPRE, hayan encontrado algo o no.
juez_ok=false ; potencia_ok=false ; pruebas_ok=false
credencial=false ; etapa1=false ; corridas=0 ; motivo_etapa1=""

# ---------- 1. vigilar al juez ----------
cd "$LAB" || { log "FATAL: no existe $LAB"; exit 1; }

if "$LAB/.venv/bin/python" -m pytest tests/ -q >/tmp/lab_pytest.txt 2>&1; then
  pruebas_ok=true
else
  log "ATENCION: la suite de pruebas FALLA"
  avisar "🔴 Laboratorio de trading: la suite de pruebas falla.
$(tail -3 /tmp/lab_pytest.txt)"
fi

if "$LAB/.venv/bin/python" scripts/prueba_del_juez.py >/tmp/lab_juez.txt 2>&1; then
  juez_ok=true
else
  log "ALARMA: el juez CERTIFICO estrategias sobre ruido"
  avisar "🚨 Laboratorio de trading: EL JUEZ ESTA ROTO.
Certifico estrategias sobre paseos aleatorios, donde no hay nada que encontrar.
Ningun resultado del laboratorio vale hasta arreglarlo.
$(grep -A4 'FALLO DEL JUEZ' /tmp/lab_juez.txt | head -6)"
fi

if "$LAB/.venv/bin/python" scripts/prueba_de_potencia.py >/tmp/lab_pot.txt 2>&1; then
  potencia_ok=true
else
  log "ALARMA: el juez NO detecta una ventaja real (sin potencia)"
  avisar "🔴 Laboratorio de trading: el juez perdio potencia.
No detecto momentum inyectado a proposito. Un juez que rechaza todo es
inutil, no riguroso."
fi

corridas=$(wc -l <"$LAB/experimentos/corridas.jsonl" 2>/dev/null || echo 0)

# ---------- 2. esperar la credencial y correr la etapa 1 ----------
if [ -f "$ENVF" ] && grep -q '^EXN_API_KEY=' "$ENVF" \
   && ! grep -qE '^EXN_API_KEY=<' "$ENVF"; then
  credencial=true
  if [ -f "$MARCA" ]; then
    etapa1=true ; motivo_etapa1="ya estaba hecha"
  else
    log "credencial detectada: corriendo etapa 1"
    "$LAB/.venv/bin/python" scripts/leer_costos_reales.py >/tmp/lab_etapa1.txt 2>&1
    # VERIFICACION POR EFECTO: no basta el codigo de salida. El archivo
    # tiene que existir y tener al menos un instrumento leido.
    n_ins=$("$LAB/.venv/bin/python" - <<'PY' 2>/dev/null || echo 0
import json, pathlib
p = pathlib.Path.home()/"trading-lab/config/costos_reales.json"
print(len(json.loads(p.read_text())["instrumentos"]) if p.exists() else 0)
PY
)
    if [ "${n_ins:-0}" -gt 0 ]; then
      etapa1=true ; motivo_etapa1="corrida hoy, $n_ins instrumentos"
      date +%F >"$MARCA"
      avisar "✅ Laboratorio de trading: ETAPA 1 LISTA.
Lei los costos REALES de tu cuenta de Exness: $n_ins instrumentos.
El backtester deja de usar costos inventados.

$(grep -E '^(EURUSD|XAUUSD|BTCUSD|instrumento)' /tmp/lab_etapa1.txt | head -5)

Falta el spread (es dinamico, sale del WebSocket de ticks).
Siguiente: historico real y torneo sobre datos de verdad."
    else
      motivo_etapa1="FALLO: no se leyo ningun instrumento"
      log "ATENCION: etapa 1 corrio y no leyo NINGUN instrumento"
      avisar "🔴 Laboratorio de trading: la credencial existe pero la etapa 1
no leyo ningun instrumento. Revisa la key, la firma o Allowed IPs.
$(tail -5 /tmp/lab_etapa1.txt)"
    fi
  fi
else
  # Recordatorio SEMANAL, no diario: un aviso diario que no cambia se
  # vuelve ruido y se deja de leer.
  if [ "$(date +%u)" = "1" ]; then
    avisar "⏳ Laboratorio de trading: sigue esperando la API key de Exness.
Es lo UNICO que falta. Se necesitan 3 datos de Key Management:
  1. API key identifier
  2. numero de la cuenta de trading
  3. host del DNS widget
La llave publica a registrar esta en el VPS:
  cat ~/.config/exness/trader_ed25519.pub.pem
Allowed IPs: <IP-DEL-VPS>
Y lo que mas importa: ¿aparece una cuenta DEMO en el selector?"
  fi
fi

# ---------- 2b. resumen diario del trading de papel ----------
# Un resumen que solo sale cuando hay algo que contar. Si lleva dias sin
# cerrar ninguna operacion, eso TAMBIEN se dice: el silencio se lee como
# exito y aqui no lo es.
if [ -f "$LAB/papel/cartera.json" ]; then
  RES_PAPEL=$("$LAB/.venv/bin/python" -W ignore scripts/aprender.py 2>/dev/null | head -40)
  N_TRATOS=$(wc -l <"$LAB/papel/tratos.jsonl" 2>/dev/null || echo 0)
  # Heredoc con delimitador citado: el Python va literal y bash no toca
  # sus comillas. Meterlo en -c "..." rompia el script entero.
  EQ=$("$LAB/.venv/bin/python" - <<'PYEQ' 2>/dev/null
import json, pathlib
d = json.loads((pathlib.Path.home()/"trading-lab/papel/cartera.json").read_text())
print(d["equity"], d["capital_inicial"], len(d["abiertas"]), d["senales_vistas"])
PYEQ
)
  read -r P_EQ P_CAP P_ABI P_SEN <<<"$EQ"
  avisar "📄 Trading de PAPEL — resumen diario (ficticio, no es dinero real)

equity US\$ ${P_EQ:-?} de US\$ ${P_CAP:-?} inicial
posiciones abiertas: ${P_ABI:-?}   senales vistas: ${P_SEN:-?}
operaciones cerradas: $N_TRATOS

$(echo "$RES_PAPEL" | head -18)"
  log "resumen de papel enviado: tratos=$N_TRATOS equity=${P_EQ:-?}"
fi

# ---------- 3. registrar la observacion ----------
printf '{"fecha":"%s","pruebas_ok":%s,"juez_no_certifica_ruido":%s,"juez_con_potencia":%s,"credencial":%s,"etapa1":%s,"motivo_etapa1":"%s","corridas_registradas":%s,"tratos_papel":%s}\n' \
  "$HOY" "$pruebas_ok" "$juez_ok" "$potencia_ok" "$credencial" "$etapa1" \
  "$motivo_etapa1" "$corridas" "${N_TRATOS:-0}" >>"$AUDIT"

log "observacion: pruebas=$pruebas_ok juez=$juez_ok potencia=$potencia_ok credencial=$credencial etapa1=$etapa1 corridas=$corridas"

# Sale con 1 si algo que importa esta mal, para que el cron lo registre.
if ! $pruebas_ok || ! $juez_ok || ! $potencia_ok; then exit 1; fi
exit 0
