"""Pruebas del cliente de lectura, contra un servidor simulado.

Las respuestas simuladas usan la forma y los VALORES DE EJEMPLO del
contrato OpenAPI oficial (trading.public.yaml), no una inventada por mi.
Asi, si Exness cambia el contrato, estas pruebas se vuelven falsas y hay
que volver a mirar -- que es lo que uno quiere.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from labcore.exness.cliente import (
    ClienteLectura, CondicionesInstrumento, ErrorExness, SOLO_LECTURA,
)
from labcore.exness.firma import Credencial

GATEWAY = "https://gw.example"
ACCESS_POINT = "https://ap.example"
CUENTA = "152706877"


@pytest.fixture
def cred(tmp_path) -> Credencial:
    k = tmp_path / "k.pem"
    k.write_bytes(Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    return Credencial(api_key="apikey-1", private_key_path=k,
                      account_id=CUENTA, discovery_base_url=GATEWAY)


# Valores de ejemplo tomados del contrato oficial (lineas 1901-1924).
CONDICIONES_EURUSD = {
    "conditions": {
        "margin_currency": "EUR",
        "margin_percent": "1",
        "contract_size": "100000",
        "volume_step": "0.01",
        "volume_min": "0.01",
        "swap_long": "-6.35",
        "swap_short": "2.14",
        "commission": {
            "commission_type": "per_lot_per_trade",
            "commission_value": {"amount": "7.00", "currency": "USD"},
        },
    }
}


def servidor(registro: list | None = None, fallos: dict | None = None):
    """Transporte simulado que ademas GUARDA lo que se le pidio, para poder
    comprobar las cabeceras firmadas y las rutas exactas."""
    fallos = fallos or {}
    def manejar(req: httpx.Request) -> httpx.Response:
        ruta = req.url.raw_path.decode()
        if registro is not None:
            registro.append((req.method, str(req.url), dict(req.headers)))
        for patron, (code, cuerpo) in fallos.items():
            if patron in ruta:
                return httpx.Response(code, text=cuerpo)
        if "/v1/trading/access-point" in ruta:
            return httpx.Response(200, json={"access_point": ACCESS_POINT,
                                             "account_id": CUENTA})
        if ruta.endswith("/conditions"):
            return httpx.Response(200, json=CONDICIONES_EURUSD)
        if ruta.endswith("/limits"):
            return httpx.Response(200, json={
                "limits": {"rest": {"global_account_rate":
                                    {"limit": 30, "window_seconds": 1}}}})
        if ruta.endswith("/account"):
            return httpx.Response(200, json={
                "currency": "USD", "leverage": "200",
                "margin_call_level": "60", "stopout_level": "0",
                "trade_mode": "enabled"})
        if ruta.endswith("/instruments"):
            return httpx.Response(200, json={"instruments": ["EURUSD", "XAUUSD"]})
        if "/candles" in ruta:
            return httpx.Response(200, json={"candles": [
                {"time": "2026-01-02T00:00:00Z", "open": "1.1", "high": "1.2",
                 "low": "1.0", "close": "1.15", "volume": "100"}]})
        return httpx.Response(404, text="ruta no simulada: " + ruta)
    return httpx.MockTransport(manejar)


# ---------- el cerrojo de solo lectura ----------

def test_el_cliente_NO_tiene_metodos_para_operar():
    """La garantia estructural: no se puede operar porque no hay con que."""
    publicos = {m for m in dir(ClienteLectura) if not m.startswith("_")}
    prohibidos = ("order", "orden", "abrir", "open", "cerrar", "close",
                  "comprar", "vender", "buy", "sell", "cancel", "modify")
    assert not {m for m in publicos if any(p in m.lower() for p in prohibidos)}
    assert SOLO_LECTURA == frozenset({"GET"})


def test_todas_las_peticiones_son_GET(cred):
    reg = []
    with ClienteLectura(cred, transporte=servidor(reg)) as c:
        c.cuenta(); c.limites(); c.instrumentos()
        c.condiciones("EURUSD")
        c.velas("EURUSD", "D1", "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z")
    assert reg and {m for m, _, _ in reg} == {"GET"}


# ---------- descubrimiento ----------

def test_resuelve_el_access_point_y_lo_usa_para_lo_demas(cred):
    reg = []
    with ClienteLectura(cred, transporte=servidor(reg)) as c:
        assert c.access_point() == ACCESS_POINT
        c.cuenta()
    assert reg[0][1].startswith(GATEWAY)      # descubrimiento al Gateway
    assert reg[1][1].startswith(ACCESS_POINT) # el resto al punto de acceso


def test_el_access_point_se_resuelve_UNA_vez(cred):
    reg = []
    with ClienteLectura(cred, transporte=servidor(reg)) as c:
        c.cuenta(); c.limites(); c.instrumentos()
    assert sum(1 for _, u, _ in reg if "access-point" in u) == 1


def test_la_firma_viaja_en_cada_peticion(cred):
    reg = []
    with ClienteLectura(cred, transporte=servidor(reg)) as c:
        c.cuenta()
    for _, _, h in reg:
        for cab in ("exn-api-key", "exn-sign", "exn-data",
                    "exn-timestamp", "exn-sign-version"):
            assert cab in h, cab
        assert h["exn-idempotency-key"] == ""   # GET: presente y vacia


def test_el_path_firmado_coincide_con_el_enviado(cred):
    """Causa numero uno de 401 segun la doc."""
    import base64
    reg = []
    with ClienteLectura(cred, transporte=servidor(reg)) as c:
        c.velas("EURUSD", "D1", "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z")
    for _, url, h in reg:
        d = base64.urlsafe_b64decode(
            h["exn-data"] + "=" * (-len(h["exn-data"]) % 4))
        firmado = json.loads(d)["path"]
        enviado = httpx.URL(url).raw_path.decode()
        assert firmado == enviado, f"firmado {firmado!r} != enviado {enviado!r}"


# ---------- los costos REALES llegan al backtester ----------

def test_las_condiciones_se_leen_del_formato_oficial(cred):
    with ClienteLectura(cred, transporte=servidor()) as c:
        k = c.condiciones("EURUSD")
    assert isinstance(k, CondicionesInstrumento)
    assert k.contract_size == 100_000
    assert k.volume_step == 0.01
    assert k.swap_long == -6.35      # Exness los manda como STRING
    assert k.swap_short == 2.14
    assert k.margin_percent == 1.0
    assert k.commission_type == "per_lot_per_trade"
    assert k.commission_value == 7.00


def test_las_condiciones_se_convierten_en_spec_y_costos(cred):
    with ClienteLectura(cred, transporte=servidor()) as c:
        k = c.condiciones("EURUSD")
    spec = k.a_spec(tick_size=0.00001, tick_value=1.0, grupo="USD_MAJOR")
    assert spec.margin_rate == 0.01          # 1% -> fraccion
    assert spec.min_volume == 0.01
    costos = k.a_modelo_costos()
    # per_lot_per_trade cubre ida y vuelta; el motor cobra por lado -> 7/2
    assert costos.comision_por_lote_por_lado == 3.50
    assert costos.swap_largo_por_lote_dia == -6.35
    assert costos.swap_corto_por_lote_dia == 2.14


def test_los_costos_reales_cambian_el_resultado_del_backtest(cred):
    """La prueba que importa: que esto efectivamente reemplace lo inventado."""
    from datetime import datetime, timedelta, timezone
    from labcore.backtest import Backtester, Barra, ModeloCostos
    from labcore.riesgo import KillSwitch, RiskEngine, RiskLimits
    from labcore.estrategias import CruceMedias
    import random

    with ClienteLectura(cred, transporte=servidor()) as c:
        k = c.condiciones("EURUSD")
    spec = k.a_spec(0.00001, 1.0, "USD_MAJOR")
    reales = k.a_modelo_costos()

    rng = random.Random(5)
    d0 = datetime(2020, 1, 6, tzinfo=timezone.utc)
    bs, p = [], 1.1
    for i in range(600):
        cl = p * (1 + rng.gauss(0, 0.005)); r = abs(rng.gauss(0, 0.003)) * p
        bs.append(Barra(d0 + timedelta(days=i), p, max(p, cl) + r / 2,
                        min(p, cl) - r / 2, cl, 1000.0, 0.00002))
        p = cl

    def correr(costos, tag):
        e = CruceMedias(10, 30)
        m = RiskEngine(RiskLimits(), KillSwitch(Path(f"/tmp/ks-{tag}.json")))
        return Backtester(spec, costos, m, 10_000.0,
                          barras_minimas=e.barras_minimas).correr(bs, e)

    sin_medir = correr(ModeloCostos(), "sm")
    con_reales = correr(reales, "cr")
    assert sin_medir.operaciones and con_reales.operaciones
    # El swap real (-6,35/lote/dia) y la comision tienen que doler.
    assert con_reales.equity_final < sin_medir.equity_final


# ---------- errores traducidos a algo accionable ----------

@pytest.mark.parametrize("code,pista", [
    (401, "path firmado"), (403, "IP no esta permitida"),
    (429, "rate limit"), (404, "inexistente"), (400, "parametros"),
])
def test_los_errores_explican_que_revisar(cred, code, pista):
    t = servidor(fallos={"/account": (code, "error del servidor")})
    with ClienteLectura(cred, transporte=t) as c:
        with pytest.raises(ErrorExness) as ei:
            c.cuenta()
    assert str(code) in str(ei.value)
    assert pista.split()[0] in str(ei.value)


def test_access_point_sin_campo_se_denuncia(cred):
    t = servidor(fallos={"access-point": (200, json.dumps({"account_id": CUENTA}))})
    with ClienteLectura(cred, transporte=t) as c:
        with pytest.raises(ErrorExness, match="sin access_point"):
            c.cuenta()


def test_timeframe_invalido_se_rechaza_antes_de_salir(cred):
    """La API devuelve 3003 REQUEST_INVALID_TIMEFRAME. Mejor atajarlo aca."""
    with ClienteLectura(cred, transporte=servidor()) as c:
        for mal in ("1m", "1h", "15min", "", "D2"):
            with pytest.raises(ValueError, match="no existe"):
                c.velas("EURUSD", mal, "2026-01-01T00:00:00Z", count=-10)


def test_hay_que_usar_hasta_O_count_pero_no_los_dos(cred):
    """El contrato: 'count cannot be used together with to'."""
    with ClienteLectura(cred, transporte=servidor()) as c:
        with pytest.raises(ValueError, match="exactamente uno"):
            c.velas("EURUSD", "D1", "2026-01-01T00:00:00Z",
                    hasta="2026-02-01T00:00:00Z", count=-10)
        with pytest.raises(ValueError, match="exactamente uno"):
            c.velas("EURUSD", "D1", "2026-01-01T00:00:00Z")


def test_price_type_invalido_se_rechaza(cred):
    with ClienteLectura(cred, transporte=servidor()) as c:
        with pytest.raises(ValueError, match="bid, ask o both"):
            c.velas("EURUSD", "D1", "2026-01-01T00:00:00Z", count=-10,
                    price_type="mid")


def test_los_timeframes_son_los_del_contrato():
    """Si Exness cambia la lista, esta prueba se vuelve falsa y hay que mirar."""
    assert ClienteLectura.TIMEFRAMES == (
        "S1", "S5", "S15", "M1", "M3", "M5", "M10", "M15", "M30",
        "H1", "H2", "H4", "D1", "W1", "MN")


def test_velas_con_count_negativo_arma_bien_la_query(cred):
    reg = []
    with ClienteLectura(cred, transporte=servidor(reg)) as c:
        c.velas("EURUSD", "M15", "2026-01-01T00:00:00Z", count=-30)
    url = [u for _, u, _ in reg if "candles" in u][0]
    assert "timeframe=M15" in url and "count=-30" in url
    assert "limit=" not in url          # el parametro no existe
    assert "price_type=bid" in url
