"""Pruebas del interruptor DEMO/REAL.

Lo que se prueba es que NO se pueda llegar a REAL por descuido.
"""
from __future__ import annotations
import pytest
from labcore.exness.entorno import Config, Entorno, cargar


def env(tmp_path, **kv):
    p = tmp_path / ".env"
    p.write_text("\n".join(f"{k}={v}" for k, v in kv.items()), encoding="utf-8")
    return p


@pytest.fixture
def llave(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    p = tmp_path / "k.pem"
    p.write_bytes(Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    return p


def test_el_defecto_es_DEMO(tmp_path, llave, monkeypatch):
    monkeypatch.delenv("TRADING_LAB_ENTORNO", raising=False)
    f = env(tmp_path, EXNESS_API_KEY_DEMO="exnsk-x" * 6,
            EXNESS_PRIVATE_KEY_DEMO=str(llave), EXNESS_ACCOUNT_ID_DEMO="<CUENTA-DEMO>")
    assert cargar(ruta_env=f).entorno is Entorno.DEMO


@pytest.mark.parametrize("entrada", [None, "demo", "DEMO", " Demo ", Entorno.DEMO])
def test_variantes_de_entrada_dan_DEMO(tmp_path, llave, monkeypatch, entrada):
    monkeypatch.delenv("TRADING_LAB_ENTORNO", raising=False)
    f = env(tmp_path, EXNESS_API_KEY_DEMO="exnsk-x" * 6,
            EXNESS_PRIVATE_KEY_DEMO=str(llave), EXNESS_ACCOUNT_ID_DEMO="1")
    assert cargar(entrada, ruta_env=f).entorno is Entorno.DEMO


def test_REAL_sin_autorizacion_explicita_se_bloquea(tmp_path, llave, monkeypatch):
    monkeypatch.delenv("TRADING_LAB_AUTORIZO_REAL", raising=False)
    f = env(tmp_path, EXNESS_API_KEY_REAL="exnsk-y" * 6,
            EXNESS_PRIVATE_KEY_REAL=str(llave), EXNESS_ACCOUNT_ID_REAL="999")
    with pytest.raises(PermissionError, match="TRADING_LAB_AUTORIZO_REAL"):
        cargar("REAL", ruta_env=f)


def test_REAL_por_variable_de_ambiente_tambien_se_bloquea(tmp_path, llave, monkeypatch):
    """El camino menos obvio: poner TRADING_LAB_ENTORNO=REAL y nada mas."""
    monkeypatch.setenv("TRADING_LAB_ENTORNO", "REAL")
    monkeypatch.delenv("TRADING_LAB_AUTORIZO_REAL", raising=False)
    f = env(tmp_path, EXNESS_API_KEY_REAL="exnsk-y" * 6,
            EXNESS_PRIVATE_KEY_REAL=str(llave), EXNESS_ACCOUNT_ID_REAL="999")
    with pytest.raises(PermissionError):
        cargar(ruta_env=f)


def test_REAL_con_autorizacion_pero_sin_credencial_falla_claro(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_LAB_AUTORIZO_REAL", "si")
    f = env(tmp_path, EXNESS_API_KEY_DEMO="exnsk-x" * 6)
    with pytest.raises(ValueError, match="EXNESS_API_KEY_REAL"):
        cargar("REAL", ruta_env=f)


def test_demo_y_real_usan_llaves_DISTINTAS(tmp_path, llave, monkeypatch):
    """Una equivocacion en demo no puede alcanzar la cuenta real."""
    monkeypatch.setenv("TRADING_LAB_AUTORIZO_REAL", "si")
    otra = tmp_path / "real.pem"
    otra.write_bytes(llave.read_bytes())
    f = env(tmp_path,
            EXNESS_API_KEY_DEMO="exnsk-demo" + "x"*20,
            EXNESS_PRIVATE_KEY_DEMO=str(llave), EXNESS_ACCOUNT_ID_DEMO="111",
            EXNESS_API_KEY_REAL="exnsk-real" + "y"*20,
            EXNESS_PRIVATE_KEY_REAL=str(otra), EXNESS_ACCOUNT_ID_REAL="222")
    d, r = cargar("DEMO", ruta_env=f), cargar("REAL", ruta_env=f)
    assert d.api_key != r.api_key
    assert d.private_key_path != r.private_key_path
    assert d.account_id != r.account_id


def test_la_clave_NUNCA_se_imprime_completa(tmp_path, llave, monkeypatch):
    monkeypatch.delenv("TRADING_LAB_ENTORNO", raising=False)
    clave = "exnsk-" + "a" * 64
    f = env(tmp_path, EXNESS_API_KEY_DEMO=clave,
            EXNESS_PRIVATE_KEY_DEMO=str(llave), EXNESS_ACCOUNT_ID_DEMO="1")
    texto = cargar(ruta_env=f).describir()
    assert clave not in texto
    assert "…" in texto
    # y la ruta de la privada aparece, pero su CONTENIDO no
    assert llave.read_text()[:40] not in texto


def test_cuenta_no_numerica_se_rechaza(tmp_path, llave, monkeypatch):
    monkeypatch.delenv("TRADING_LAB_ENTORNO", raising=False)
    f = env(tmp_path, EXNESS_API_KEY_DEMO="exnsk-x"*6,
            EXNESS_PRIVATE_KEY_DEMO=str(llave), EXNESS_ACCOUNT_ID_DEMO="abc")
    with pytest.raises(ValueError, match="digitos"):
        cargar(ruta_env=f)
