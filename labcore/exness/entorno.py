"""Interruptor DEMO / REAL. Por defecto DEMO, siempre.

Regla dura: pasar a REAL exige una variable de entorno explicita Y que
exista la credencial real. No hay forma de llegar a REAL por descuido ni
por un valor por defecto mal puesto.

Cada entorno usa su PROPIA llave privada y su PROPIA API key. Asi se
puede revocar una sin tocar la otra, y una equivocacion en demo no puede
alcanzar la cuenta real.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

RAIZ = Path.home() / "trading-lab"
ENV_FILE = RAIZ / ".env"


class Entorno(str, Enum):
    DEMO = "DEMO"
    REAL = "REAL"


@dataclass(frozen=True)
class Config:
    entorno: Entorno
    api_key: str
    private_key_path: Path
    account_id: str
    discovery_base_url: str

    @property
    def es_real(self) -> bool:
        return self.entorno is Entorno.REAL

    def describir(self) -> str:
        """Nunca imprime la clave completa: solo prefijo y sufijo."""
        k = self.api_key
        censurada = (f"{k[:10]}…{k[-4:]}" if len(k) > 18 else f"{'*' * len(k)}")
        return (
            f"entorno       {self.entorno.value}"
            f"{'  ⚠️  DINERO REAL' if self.es_real else '  (cuenta de practica)'}\n"
            f"api key       {censurada}  ({len(k)} caracteres)\n"
            f"cuenta        {self.account_id}\n"
            f"gateway       {self.discovery_base_url}\n"
            f"llave privada {self.private_key_path}  (no se imprime)"
        )


def _leer_env(ruta: Path) -> dict[str, str]:
    if not ruta.exists():
        return {}
    out: dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# Host del widget DNS. Es el GATEWAY, no el punto de acceso de la cuenta:
# el punto de acceso se DESCUBRE con /v1/trading/access-point y no se fija.
# La doc es explicita: "Do not copy a hostname from an example or guess the
# Gateway URL from an account Access Point."
GATEWAYS = ("https://api.exness.com", "https://api.exness-api.com")


def cargar(entorno: Entorno | str | None = None,
           ruta_env: Path | None = None) -> Config:
    """Carga la configuracion. DEMO por defecto, SIEMPRE.

    Para usar REAL hacen falta DOS cosas a la vez:
      1. pedirlo explicitamente (parametro o TRADING_LAB_ENTORNO=REAL)
      2. que existan EXNESS_API_KEY_REAL y su llave privada propia
    """
    vals = _leer_env(ruta_env or ENV_FILE)
    pedido = entorno or os.environ.get("TRADING_LAB_ENTORNO") or Entorno.DEMO
    # OJO: en Python 3.12 str(Entorno.DEMO) devuelve "Entorno.DEMO", no
    # "DEMO". Hay que tomar .value cuando ya es una instancia del enum.
    e = pedido if isinstance(pedido, Entorno) else Entorno(str(pedido).strip().upper())

    if e is Entorno.REAL:
        # Cerrojo: REAL no se activa sin autorizacion explicita en el entorno.
        if os.environ.get("TRADING_LAB_AUTORIZO_REAL") != "si":
            raise PermissionError(
                "El entorno REAL requiere TRADING_LAB_AUTORIZO_REAL=si en el "
                "ambiente. No se activa por un valor por defecto ni por un "
                "parametro suelto: tiene que ser una decision escrita."
            )
        api_key = vals.get("EXNESS_API_KEY_REAL", "")
        # Nombre que pidio Fernando: ..._PATH. Se acepta el otro por si
        # quedo escrito en algun .env viejo.
        priv = Path(vals.get("EXNESS_PRIVATE_KEY_REAL_PATH")
                    or vals.get("EXNESS_PRIVATE_KEY_REAL")
                    or str(Path.home()/".config/trading-lab/exness_real_private.pem"))
        cuenta = vals.get("EXNESS_ACCOUNT_ID_REAL", "")
        falta = "EXNESS_API_KEY_REAL"
    else:
        api_key = vals.get("EXNESS_API_KEY_DEMO", "")
        priv = Path(vals.get("EXNESS_PRIVATE_KEY_DEMO_PATH")
                    or vals.get("EXNESS_PRIVATE_KEY_DEMO")
                    or str(Path.home()/".config/exness/trader_ed25519.pem"))
        cuenta = vals.get("EXNESS_ACCOUNT_ID_DEMO", "<CUENTA-DEMO>")
        falta = "EXNESS_API_KEY_DEMO"

    if not api_key:
        raise ValueError(
            f"falta {falta} en {ruta_env or ENV_FILE}. "
            f"No se pide por chat ni se pasa por parametro."
        )
    priv = priv.expanduser()
    if not priv.exists():
        raise FileNotFoundError(f"no existe la llave privada en {priv}")
    if not cuenta.isdigit():
        raise ValueError(f"el numero de cuenta debe ser solo digitos: {cuenta!r}")

    gw = vals.get("EXNESS_GATEWAY", GATEWAYS[0]).rstrip("/")
    return Config(entorno=e, api_key=api_key, private_key_path=priv,
                  account_id=cuenta, discovery_base_url=gw)
