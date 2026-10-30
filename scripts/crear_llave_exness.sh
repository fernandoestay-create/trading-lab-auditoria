#!/usr/bin/env bash
# Genera el par de llaves Ed25519 para la API de Exness EN TU COMPUTADOR.
#
# La llave PRIVADA no se sube a ninguna parte, no se pega en ningun chat y
# no se commitea. A Exness se le registra solo la PUBLICA.
#
# Uso:  bash crear_llave_exness.sh
set -euo pipefail

DEST="$HOME/.config/exness"
PRIV="$DEST/trader_ed25519.pem"
PUB="$DEST/trader_ed25519.pub.pem"

# --- 1. Elegir un OpenSSL que SI soporte Ed25519 -------------------------
# En macOS /usr/bin/openssl suele ser LibreSSL y no sirve. La doc de Exness
# lo advierte explicitamente.
OPENSSL_BIN="${OPENSSL_BIN:-openssl}"
if [[ "$(uname -s)" == "Darwin" ]]; then
  if command -v brew >/dev/null 2>&1 && brew --prefix openssl@3 >/dev/null 2>&1; then
    OPENSSL_BIN="$(brew --prefix openssl@3)/bin/openssl"
  fi
fi
echo "openssl elegido : $OPENSSL_BIN"
"$OPENSSL_BIN" version

# Comprobar por EFECTO que soporta Ed25519, no por el numero de version.
if ! "$OPENSSL_BIN" genpkey -algorithm ed25519 -out /dev/null 2>/dev/null; then
  echo
  echo "ERROR: este openssl NO soporta Ed25519."
  echo "En macOS:  brew install openssl@3   y vuelve a correr este script."
  exit 1
fi
echo "Ed25519     : soportado (probado generando una llave de descarte)"

# --- 2. No sobrescribir una llave que ya existe --------------------------
mkdir -p "$DEST"; chmod 700 "$DEST"
if [[ -f "$PRIV" ]]; then
  echo
  echo "ERROR: ya existe $PRIV"
  echo "Si de verdad quieres reemplazarla, muevela primero:"
  echo "  mv '$PRIV' '$PRIV.viejo-\$(date +%Y%m%d)'"
  exit 1
fi

# --- 3. Generar el par ---------------------------------------------------
umask 077
"$OPENSSL_BIN" genpkey -algorithm ed25519 -out "$PRIV"
chmod 600 "$PRIV"
"$OPENSSL_BIN" pkey -in "$PRIV" -pubout -out "$PUB"
chmod 644 "$PUB"

echo
echo "=========================================================="
echo " LLAVE PRIVADA (NO la compartas, NO la pegues en un chat)"
if [[ "$(uname -s)" == "Darwin" ]]; then
  PERMS="$(stat -f '%Lp' "$PRIV")"
else
  PERMS="$(stat -c '%a' "$PRIV")"
fi
echo "   $PRIV   (permisos $PERMS)"
echo
echo " LLAVE PUBLICA (esta SI se registra en Exness)"
echo "   $PUB"
echo "=========================================================="
echo
echo "Contenido de la PUBLICA, para pegar en Key Management:"
echo "----------------------------------------------------------"
cat "$PUB"
echo "----------------------------------------------------------"
echo
echo "PASOS EN EXNESS (Personal Area -> Key Management):"
echo "  1. Crear una API key nueva."
echo "  2. Elegir la opcion \"I'll use my own public key\" y pegar lo de arriba."
echo "  3. Nombre de la key: trading-lab   (una key DEDICADA a este proyecto)"
echo "  4. Fecha de expiracion: ponle una. Una key sin expiracion es un riesgo."
echo "  5. Trading account: selecciona la cuenta que puede usar esta key."
echo "  6. Allowed IPs: ojo, lee la nota de abajo antes de llenar esto."
echo "  7. Copiar el API key identifier y el host del DNS widget."
echo
echo "DESPUES, guarda el identificador (NO es secreto, pero igual va fuera de git):"
echo "  cat > $DEST/env <<'EOF'"
echo "  EXN_API_KEY=<el identificador que te dio Exness>"
echo "  EXN_ACCOUNT_ID=<numero de tu cuenta de trading>"
echo "  EXN_DISCOVERY_BASE_URL=<host del DNS widget, sin slash final>"
echo "  EXN_PRIVATE_KEY_PATH=$PRIV"
echo "  EOF"
echo "  chmod 600 $DEST/env"
echo
echo "NOTA SOBRE 'Allowed IPs' -- esto decide donde puede operar el laboratorio:"
echo "  * Si pones solo la IP de tu casa, el laboratorio del VPS NO podra conectarse."
echo "  * Si el laboratorio corre en el VPS, la IP que va es <IP-DEL-VPS>."
echo "  * Tu IP publica actual la ves con:  curl -s https://ifconfig.me"
echo "  * Puedes dejarlo vacio al principio y restringirlo despues."
