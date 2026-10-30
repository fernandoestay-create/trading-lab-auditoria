#!/usr/bin/env bash
# Muestrea el spread REAL de Exness cada vez que corre.
#
# Por que importa: el "costo casi cero" que medi venia de UN instante
# tranquilo. El spread se ensancha en noticias, en el cierre y en la
# madrugada -- justo cuando una estrategia de ruptura suele disparar. Un
# solo dato no es una distribucion.
#
# La demo usa el MISMO feed de precios que la cuenta real, asi que el
# spread medido aqui SI es el real. Lo que la demo probablemente esconde
# es la EJECUCION (slippage, requotes, rechazos), no el precio cotizado.
set -uo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export PATH="<HOME>/.local/bin:/usr/local/bin:/usr/bin:/bin"
LAB="$HOME/trading-lab"
exec 9>"$HOME/.trading-lab-spread.lock"
flock -n 9 || exit 0

"$LAB/.venv/bin/python" -W ignore - <<'PY' 2>/dev/null >>"$LAB/experimentos/spread_observado.jsonl"
import sys, json
from datetime import datetime, timezone
sys.path.insert(0, '<HOME>/trading-lab')
from labcore.exness.cliente import ClienteLectura, ErrorExness
from labcore.exness.entorno import cargar
from labcore.exness.firma import Credencial

# Pocos instrumentos y de familias distintas: el tope de velas es 2/s y
# cada uno cuesta DOS llamadas (bid y ask).
FOCO = ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "US500", "AAPL"]

cfg = cargar()
c = ClienteLectura(Credencial(cfg.api_key, cfg.private_key_path,
                              cfg.account_id, cfg.discovery_base_url))
ahora = datetime.now(timezone.utc)
desde = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")
try:
    for ins in FOCO:
        fila = {"ts": ahora.isoformat(), "instrumento": ins}
        try:
            for tipo in ("bid", "ask"):
                v = c.velas(ins, "M1", desde, count=-1, price_type=tipo)
                if v:
                    fila[tipo] = float(v[0].get("close") or v[0].get("c"))
        except ErrorExness as e:
            fila["error"] = f"{e}"[:120]
        if "bid" in fila and "ask" in fila and fila["bid"] > 0:
            fila["spread"] = round(fila["ask"] - fila["bid"], 6)
            fila["spread_pct"] = round(fila["spread"] / fila["bid"], 8)
        print(json.dumps(fila, ensure_ascii=False))
finally:
    c.desconectar()
PY
exit 0
