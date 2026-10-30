"""Pruebas del firmador Ed25519.

Sin servidor no se puede probar que Exness ACEPTE la firma. Lo que SI se
puede probar, y es lo que importa, es que la firma sea criptograficamente
correcta: se firma con la privada y se verifica con la publica. Si ese
ciclo cierra, lo que quede por fallar es la serializacion, no la cripto.
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from labcore.exness.firma import (
    Credencial, SIGN_VERSION, b64url, body_hash, cargar_llave, firmar,
)


@pytest.fixture
def llave():
    return Ed25519PrivateKey.generate()


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ---------- el ciclo firmar/verificar ----------

def test_la_firma_se_verifica_con_la_publica(llave):
    h = firmar(llave=llave, api_key="k1", method="GET",
               path="/v1/trading/access-point?account_id=123456")
    crudo = _b64url_decode(h["EXN-DATA"])
    # Si esto no lanza, la firma es valida para esos bytes exactos.
    llave.public_key().verify(_b64url_decode(h["EXN-SIGN"]), crudo)


def test_se_firman_los_BYTES_DEL_JSON_no_su_base64(llave):
    """Firmar el base64 en vez del JSON es el error clasico aqui."""
    h = firmar(llave=llave, api_key="k1", method="GET", path="/v1/x")
    crudo = _b64url_decode(h["EXN-DATA"])
    pub = llave.public_key()
    pub.verify(_b64url_decode(h["EXN-SIGN"]), crudo)     # correcto
    with pytest.raises(InvalidSignature):
        pub.verify(_b64url_decode(h["EXN-SIGN"]), h["EXN-DATA"].encode())


def test_otra_llave_no_valida_la_firma(llave):
    h = firmar(llave=llave, api_key="k1", method="GET", path="/v1/x")
    otra = Ed25519PrivateKey.generate().public_key()
    with pytest.raises(InvalidSignature):
        otra.verify(_b64url_decode(h["EXN-SIGN"]), _b64url_decode(h["EXN-DATA"]))


def test_cambiar_un_caracter_del_path_invalida_la_firma(llave):
    h = firmar(llave=llave, api_key="k1", method="GET", path="/v1/x?a=1")
    datos = json.loads(_b64url_decode(h["EXN-DATA"]))
    datos["path"] = "/v1/x?a=2"
    alterado = json.dumps(datos, separators=(",", ":")).encode()
    with pytest.raises(InvalidSignature):
        llave.public_key().verify(_b64url_decode(h["EXN-SIGN"]), alterado)


# ---------- la forma exacta que exige la doc ----------

def test_las_seis_cabeceras_y_sus_nombres_literales(llave):
    h = firmar(llave=llave, api_key="miKey", method="GET", path="/v1/x")
    assert set(h) == {
        "EXN-API-KEY", "EXN-IDEMPOTENCY-KEY", "EXN-TIMESTAMP",
        "EXN-SIGN-VERSION", "EXN-DATA", "EXN-SIGN",
    }
    assert h["EXN-API-KEY"] == "miKey"
    assert h["EXN-SIGN-VERSION"] == SIGN_VERSION == "1"


def test_el_json_firmado_tiene_los_siete_campos_de_la_doc(llave):
    h = firmar(llave=llave, api_key="k", method="POST",
               path="/v1/trading/accounts/1/orders", cuerpo=b'{"a":1}',
               idempotency_key="abc12")
    d = json.loads(_b64url_decode(h["EXN-DATA"]))
    assert list(d) == ["api_key", "idempotency_key", "timestamp",
                       "sign_version", "method", "path", "body_hash"]


def test_base64url_sin_padding():
    assert "=" not in b64url(b"abcd")
    assert "+" not in b64url(bytes(range(256)))
    assert "/" not in b64url(bytes(range(256)))


def test_body_hash_es_sha256_en_base64url(llave):
    cuerpo = b'{"volume":"0.10"}'
    esperado = b64url(hashlib.sha256(cuerpo).digest())
    h = firmar(llave=llave, api_key="k", method="POST", path="/v1/x",
               cuerpo=cuerpo, idempotency_key="abc12")
    assert json.loads(_b64url_decode(h["EXN-DATA"]))["body_hash"] == esperado


def test_cuerpo_vacio_usa_el_hash_del_vacio(llave):
    h = firmar(llave=llave, api_key="k", method="GET", path="/v1/x")
    assert (json.loads(_b64url_decode(h["EXN-DATA"]))["body_hash"]
            == b64url(hashlib.sha256(b"").digest()))


# ---------- las reglas que causan 401 ----------

def test_en_GET_la_idempotency_key_va_VACIA_pero_la_cabecera_SE_ENVIA(llave):
    h = firmar(llave=llave, api_key="k", method="GET", path="/v1/x")
    assert "EXN-IDEMPOTENCY-KEY" in h       # se envia
    assert h["EXN-IDEMPOTENCY-KEY"] == ""   # vacia


def test_GET_con_idempotency_key_se_rechaza_antes_de_salir(llave):
    with pytest.raises(ValueError, match="VACIA"):
        firmar(llave=llave, api_key="k", method="GET", path="/v1/x",
               idempotency_key="abc12")


@pytest.mark.parametrize("ik", ["", "abc", "x" * 129])
def test_POST_exige_idempotency_key_entre_5_y_128(llave, ik):
    with pytest.raises(ValueError, match="idempotency"):
        firmar(llave=llave, api_key="k", method="POST", path="/v1/x",
               idempotency_key=ik)


def test_una_URL_completa_se_rechaza_debe_ser_ruta(llave):
    """La doc insiste: el path firmado NO es una URL completa."""
    with pytest.raises(ValueError, match="ruta, no una URL"):
        firmar(llave=llave, api_key="k", method="GET",
               path="https://host/v1/x")


def test_el_timestamp_va_en_milisegundos(llave):
    h = firmar(llave=llave, api_key="k", method="GET", path="/v1/x",
               timestamp_ms=1761672000000)
    assert h["EXN-TIMESTAMP"] == "1761672000000"
    assert len(h["EXN-TIMESTAMP"]) == 13


# ---------- carga de credencial y de llave ----------

def test_una_llave_que_no_es_ed25519_se_rechaza_con_mensaje_claro(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    p = tmp_path / "rsa.pem"
    p.write_bytes(rsa.generate_private_key(public_exponent=65537, key_size=2048)
                  .private_bytes(serialization.Encoding.PEM,
                                 serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption()))
    with pytest.raises(TypeError, match="Ed25519"):
        cargar_llave(p)


def test_la_llave_generada_por_el_script_se_carga(tmp_path):
    """Cierra el ciclo con el script que corre Fernando en su Mac."""
    import subprocess
    from pathlib import Path
    script = Path.home() / "trading-lab" / "scripts" / "crear_llave_exness.sh"
    r = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                       env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stdout + r.stderr
    k = cargar_llave(tmp_path / ".config" / "exness" / "trader_ed25519.pem")
    h = firmar(llave=k, api_key="k", method="GET", path="/v1/x")
    k.public_key().verify(_b64url_decode(h["EXN-SIGN"]),
                          _b64url_decode(h["EXN-DATA"]))


def test_sin_archivo_env_el_mensaje_dice_que_hacer(tmp_path):
    with pytest.raises(FileNotFoundError, match="crear_llave_exness"):
        Credencial.desde_env(tmp_path / "no-existe")


def test_env_incompleto_dice_QUE_falta(tmp_path):
    p = tmp_path / "env"
    p.write_text("EXN_API_KEY=abc\n", encoding="utf-8")
    with pytest.raises(ValueError, match="EXN_ACCOUNT_ID"):
        Credencial.desde_env(p)


def test_env_completo_se_lee_y_normaliza(tmp_path):
    p = tmp_path / "env"
    p.write_text(
        '# comentario\n'
        'EXN_API_KEY="abc"\n'
        'EXN_PRIVATE_KEY_PATH=/tmp/k.pem\n'
        'EXN_ACCOUNT_ID=152706877\n'
        'EXN_DISCOVERY_BASE_URL=https://gw.example/\n',
        encoding="utf-8")
    c = Credencial.desde_env(p)
    assert c.api_key == "abc"
    assert c.account_id == "152706877"
    assert c.discovery_base_url == "https://gw.example"   # sin slash final
