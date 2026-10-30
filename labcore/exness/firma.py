"""Firma de solicitudes para la API de Exness (EXN-SIGN, version 1).

Extraido del contrato oficial y de /authentication/request-signing.
La doc dice que su `buildSignedHeaders` es "ilustrativo y no provisto",
asi que esto es una implementacion propia y los puntos donde la doc NO
fija el comportamiento estan marcados con LAGUNA.

Esquema: se arma un JSON de 7 campos, se codifica en base64url sin
padding y va en EXN-DATA. Los BYTES DEL JSON (no el base64) se firman
con Ed25519 y la firma, tambien en base64url sin padding, va en EXN-SIGN.

La llave privada NUNCA viaja. Solo viaja la firma.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SIGN_VERSION = "1"


def b64url(data: bytes) -> str:
    """base64url SIN padding, como exige la doc."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def body_hash(cuerpo: bytes) -> str:
    """SHA-256 del cuerpo, en base64url sin padding.

    LAGUNA: la doc no dice explicitamente que hashear cuando NO hay
    cuerpo. Se usa el hash del vacio (que es un valor definido) en vez
    de omitir el campo, porque el campo es obligatorio en el JSON.
    """
    return b64url(hashlib.sha256(cuerpo).digest())


@dataclass(frozen=True)
class Credencial:
    api_key: str
    private_key_path: Path
    account_id: str
    discovery_base_url: str

    @classmethod
    def desde_env(cls, ruta: Path | None = None) -> "Credencial":
        """Lee ~/.config/exness/env. NUNCA de una variable en el codigo."""
        ruta = ruta or Path.home() / ".config" / "exness" / "env"
        if not ruta.exists():
            raise FileNotFoundError(
                f"no existe {ruta}. Crea la credencial con "
                f"scripts/crear_llave_exness.sh y llena ese archivo. "
                f"La llave privada no se pega en ningun chat."
            )
        vals: dict[str, str] = {}
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, v = linea.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
        faltan = {"EXN_API_KEY", "EXN_PRIVATE_KEY_PATH", "EXN_ACCOUNT_ID",
                  "EXN_DISCOVERY_BASE_URL"} - set(vals)
        if faltan:
            raise ValueError(f"faltan en {ruta}: {sorted(faltan)}")
        return cls(
            api_key=vals["EXN_API_KEY"],
            private_key_path=Path(vals["EXN_PRIVATE_KEY_PATH"]).expanduser(),
            account_id=vals["EXN_ACCOUNT_ID"],
            discovery_base_url=vals["EXN_DISCOVERY_BASE_URL"].rstrip("/"),
        )


def cargar_llave(ruta: Path) -> Ed25519PrivateKey:
    k = serialization.load_pem_private_key(
        ruta.read_bytes(), password=None)
    if not isinstance(k, Ed25519PrivateKey):
        raise TypeError(
            f"{ruta} no es una llave Ed25519 (es {type(k).__name__}). "
            f"La API de Exness firma con Ed25519, no con RSA ni EC."
        )
    return k


def firmar(
    *,
    llave: Ed25519PrivateKey,
    api_key: str,
    method: str,
    path: str,
    cuerpo: bytes = b"",
    idempotency_key: str = "",
    timestamp_ms: int | None = None,
) -> dict[str, str]:
    """Devuelve las 6 cabeceras firmadas.

    `path` tiene que ser la ruta CON su query, exactamente como se va a
    enviar -- no una URL completa. La doc insiste en esto y es la causa
    numero uno de 401.

    Para GET, EXN-IDEMPOTENCY-KEY es obligatoria y su valor debe ser
    VACIO: la cabecera se envia, no se omite. En el curl de la doc eso se
    escribe `-H "EXN-IDEMPOTENCY-KEY;"` (con punto y coma). Aqui se
    manda el string vacio, que es lo mismo a nivel HTTP.
    """
    m = method.upper()
    if m == "GET" and idempotency_key:
        raise ValueError(
            "en GET la idempotency key debe ir VACIA (la doc lo exige)")
    if m != "GET" and not (5 <= len(idempotency_key) <= 128):
        raise ValueError(
            f"idempotency key de {len(idempotency_key)} chars; la doc exige "
            f"entre 5 y 128 en operaciones que mutan estado")
    if not path.startswith("/"):
        raise ValueError(f"path debe ser una ruta, no una URL: {path!r}")

    ts = str(timestamp_ms if timestamp_ms is not None
             else int(time.time() * 1000))

    # LAGUNA RESUELTA el 2026-10-30 leyendo /authentication/request-signing
    # y el ejemplo de referencia en /trading/guides/code-examples:
    #
    #   timestamp y sign_version van como NUMEROS, no como texto.
    #
    # El ejemplo oficial muestra {"timestamp": 1773656070123,
    # "sign_version": 1}. Mi primera version los mandaba entre comillas,
    # lo que cambia los bytes firmados y habria dado error 1001
    # AUTH_INVALID_SIGNATURE con una llave perfectamente valida.
    #
    # El orden de los campos es el del ejemplo y no se altera: la firma es
    # sobre los bytes exactos, asi que reordenar rompe. Separadores
    # compactos para igualar JSON.stringify de JavaScript.
    datos = {
        "api_key": api_key,
        "idempotency_key": idempotency_key,
        "timestamp": int(ts),
        "sign_version": int(SIGN_VERSION),
        "method": m,
        "path": path,
        "body_hash": body_hash(cuerpo),
    }
    crudo = json.dumps(datos, separators=(",", ":"), ensure_ascii=False).encode()

    return {
        "EXN-API-KEY": api_key,
        "EXN-IDEMPOTENCY-KEY": idempotency_key,
        "EXN-TIMESTAMP": ts,
        "EXN-SIGN-VERSION": SIGN_VERSION,
        "EXN-DATA": b64url(crudo),
        # Se firman los BYTES DEL JSON, no su base64.
        "EXN-SIGN": b64url(llave.sign(crudo)),
    }
