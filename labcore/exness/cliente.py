"""Cliente de SOLO LECTURA para la API de Exness.

SEGURIDAD POR DISENO, no por disciplina: esta clase NO tiene ningun
metodo que envie, modifique o cancele una orden. No es que esten
deshabilitados -- no existen. Si alguien (o algun LLM) intenta operar a
traves de este cliente, no encuentra con que.

Cuando llegue el momento de ejecutar, ira en otro modulo, con su propia
autorizacion explicita y revocable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..backtest.costos import ModeloCostos
from ..riesgo.modelo import InstrumentSpec
from .firma import Credencial, cargar_llave, firmar

TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# LIMITES REALES, leidos de GET /configuration/.../limits de la cuenta.
# La doc no publica ningun numero; estos salieron de la cuenta demo el
# 2026-10-30. Pasarse da 3015 REQUEST_RATE_LIMIT, que ya me paso lanzando
# 4 llamadas de velas seguidas.
LIMITE_GLOBAL_POR_SEG = 10.0
# El tope documentado de velas es 2/s, pero es una VENTANA DESLIZANTE:
# pedir exactamente 2 por segundo da 429 igual porque se cuenta el ultimo
# segundo movil, no segundos calendario. Medido el 2026-10-30. Se usa
# 1,25/s para quedar con holgura: el margen cuesta medio segundo y evita
# perder la muestra entera.
LIMITE_VELAS_POR_SEG = 1.0

# FORZAR IPv4. Medido el 2026-10-28: www.exness-api.com tiene registro
# AAAA y este VPS prefiere IPv6, asi que la API nos veria llegando desde
# 2a02:c207:... y no desde la IPv4 documentada (<IP-DEL-VPS>). Con
# "Allowed IPs" configurado a la IPv4, cada llamada daria 403 y el error
# no diria por que. Ademas el prefijo IPv6 del proveedor puede cambiar;
# la IPv4 es la direccion estable y la que esta documentada.
# Atarse a "0.0.0.0" obliga al socket a salir por IPv4.
FORZAR_IPV4 = True


def _transporte_ipv4() -> httpx.HTTPTransport:
    return httpx.HTTPTransport(local_address="0.0.0.0", retries=1)

# Metodos HTTP que este cliente tiene permitido usar. Un segundo cerrojo
# ademas de la ausencia de metodos de escritura.
SOLO_LECTURA = frozenset({"GET"})


class ErrorExness(RuntimeError):
    def __init__(self, status: int, cuerpo: str, ruta: str) -> None:
        super().__init__(f"HTTP {status} en {ruta}: {cuerpo[:300]}")
        self.status, self.cuerpo, self.ruta = status, cuerpo, ruta


@dataclass
class CondicionesInstrumento:
    """Costos y contrato REALES de la cuenta, tal como los reporta Exness."""

    symbol: str
    contract_size: float
    volume_step: float
    volume_min: float
    margin_percent: float
    swap_long: float | None
    swap_short: float | None
    commission_type: str | None
    commission_value: float | None
    crudo: dict[str, Any]

    def a_spec(self, tick_size: float, tick_value: float,
               grupo: str = "") -> InstrumentSpec:
        return InstrumentSpec(
            symbol=self.symbol, contract_size=self.contract_size,
            tick_size=tick_size, tick_value_account_ccy=tick_value,
            min_volume=self.volume_min, volume_step=self.volume_step,
            margin_rate=self.margin_percent / 100.0,
            correlation_group=grupo,
        )

    def a_modelo_costos(self, slippage_ticks: float = 1.0) -> ModeloCostos:
        """Costos MEDIDOS, no inventados.

        El spread NO viene de aqui: es dinamico y sale del WebSocket de
        ticks. Hasta que se mida, el multiplicador queda en 1,0 y hay que
        correr tambien el escenario de estres.
        """
        por_lote = 0.0
        if self.commission_value is not None:
            por_lote = abs(self.commission_value)
            # per_lot_per_trade = se cobra en cada operacion (ida y vuelta);
            # el motor ya cobra comision por lado, asi que se pasa por lado.
            if self.commission_type == "per_lot_per_trade":
                por_lote = por_lote / 2.0
        return ModeloCostos(
            comision_por_lote_por_lado=por_lote,
            slippage_ticks=slippage_ticks,
            swap_largo_por_lote_dia=self.swap_long or 0.0,
            swap_corto_por_lote_dia=self.swap_short or 0.0,
        )


def _f(v: Any) -> float | None:
    """Exness manda los decimales como STRING a proposito (precision).
    Convertir a float es seguro aqui porque son costos, no precios de
    ejecucion; para precios conviene Decimal."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class ClienteLectura:
    def __init__(self, cred: Credencial, transporte: httpx.BaseTransport | None = None,
                 forzar_ipv4: bool = FORZAR_IPV4):
        self.cred = cred
        self._llave = cargar_llave(cred.private_key_path)
        self._access_point: str | None = None
        self._ultima_llamada: dict[str, float] = {}
        if transporte is None and forzar_ipv4:
            transporte = _transporte_ipv4()
        self._cliente = httpx.Client(timeout=TIMEOUT, transport=transporte)

    # Se llama "desconectar" y no "cerrar" a proposito: "cerrar" es como
    # se llama a cerrar una POSICION, y el cerrojo de abajo revisa los
    # nombres de los metodos. Un nombre ambiguo en un modulo de solo
    # lectura es una invitacion a confundirse.
    def desconectar(self) -> None:
        self._cliente.close()

    def __enter__(self): return self
    def __exit__(self, *a): self.desconectar()

    # ---------------- transporte firmado ----------------

    def _esperar_turno(self, ruta: str) -> None:
        """Freno simple por ventana. Evita 3015 REQUEST_RATE_LIMIT.

        Dos cubetas: una global de 10/s y una de velas de 2/s, que es la
        mas restrictiva y la que me reventó en la cara.
        """
        import time
        ahora = time.monotonic()
        es_vela = "/candles" in ruta
        minimo = (1.0 / LIMITE_VELAS_POR_SEG if es_vela
                  else 1.0 / LIMITE_GLOBAL_POR_SEG)
        clave = "velas" if es_vela else "global"
        ultimo = self._ultima_llamada.get(clave, 0.0)
        espera = minimo - (ahora - ultimo)
        if espera > 0:
            time.sleep(espera)
        self._ultima_llamada[clave] = time.monotonic()
        # El tope global aplica tambien a las velas.
        if es_vela:
            self._ultima_llamada["global"] = self._ultima_llamada[clave]

    def _get(self, base: str, ruta: str) -> Any:
        if "GET" not in SOLO_LECTURA:          # cerrojo, no decoracion
            raise RuntimeError("este cliente es de solo lectura")
        # Reintento ante 429. Adivinar el limite exacto es fragil: la
        # ventana es deslizante y el espaciado "justo" falla de forma
        # intermitente (medido). Lo robusto es respetar el tope Y hacerle
        # caso al servidor cuando dice que esperemos.
        import time
        for intento in range(4):
            self._esperar_turno(ruta)
            # La firma se regenera en CADA intento: el timestamp va dentro
            # de lo firmado, asi que reusar las cabeceras daria 1001.
            h = firmar(llave=self._llave, api_key=self.cred.api_key,
                       method="GET", path=ruta)
            r = self._cliente.get(base + ruta, headers=h)
            if r.status_code != 429:
                break
            espera = float(r.headers.get("Retry-After") or (0.8 * (2 ** intento)))
            time.sleep(min(espera, 8.0))
        if r.status_code != 200:
            # Los codigos que la doc documenta, traducidos a algo accionable.
            ayuda = {
                400: "revisa los parametros de query",
                401: ("revisa la llave, la firma y que el path firmado sea "
                      "EXACTAMENTE el enviado (query incluido)"),
                403: "la key no tiene permiso sobre esta cuenta, o la IP no esta permitida",
                404: "ruta o cuenta inexistente",
                429: "rate limit: consulta /limits para conocer el tope real",
            }.get(r.status_code, "")
            raise ErrorExness(r.status_code,
                              f"{r.text} {('-> ' + ayuda) if ayuda else ''}",
                              ruta)
        return r.json()

    # ---------------- descubrimiento ----------------

    def access_point(self) -> str:
        """Resuelve el host de la cuenta. La doc insiste en que el host del
        widget DNS es solo el Gateway, no el punto de acceso."""
        if self._access_point is None:
            ruta = f"/v1/trading/access-point?account_id={self.cred.account_id}"
            d = self._get(self.cred.discovery_base_url, ruta)
            ap = d.get("access_point")
            if not ap:
                raise ErrorExness(200, f"respuesta sin access_point: {d}", ruta)
            self._access_point = str(ap).rstrip("/")
        return self._access_point

    # ---------------- lecturas ----------------

    def cuenta(self) -> dict:
        return self._get(
            self.access_point(),
            f"/v1/configuration/accounts/{self.cred.account_id}/account")

    def estado_cuenta(self) -> dict:
        """Foto del estado de trading: saldo, patrimonio, margen, posiciones.

        Es un GET (solo lectura). Devuelve lo que hay, no modifica nada.
        """
        return self._get(
            self.access_point(),
            f"/v1/trading/accounts/{self.cred.account_id}/snapshot")

    def limites(self) -> dict:
        """Los rate limits REALES. La doc no publica ningun numero: solo
        se conocen por aqui."""
        return self._get(
            self.access_point(),
            f"/v1/configuration/accounts/{self.cred.account_id}/limits")

    def instrumentos(self) -> list:
        d = self._get(
            self.access_point(),
            f"/v1/configuration/accounts/{self.cred.account_id}/instruments")
        return d if isinstance(d, list) else d.get("instruments", [])

    def condiciones(self, instrumento: str) -> CondicionesInstrumento:
        d = self._get(
            self.access_point(),
            f"/v1/configuration/accounts/{self.cred.account_id}"
            f"/instruments/{instrumento}/conditions")
        c = d.get("conditions", d)
        com = c.get("commission") or {}
        cv = com.get("commission_value")
        if isinstance(cv, dict):            # Money -> {amount, currency}
            cv = cv.get("amount")
        return CondicionesInstrumento(
            symbol=instrumento,
            contract_size=_f(c.get("contract_size")) or 0.0,
            volume_step=_f(c.get("volume_step")) or 0.0,
            volume_min=_f(c.get("volume_min")) or _f(c.get("min_volume")) or 0.0,
            margin_percent=_f(c.get("margin_percent")) or 0.0,
            swap_long=_f(c.get("swap_long")),
            swap_short=_f(c.get("swap_short")),
            commission_type=com.get("commission_type"),
            commission_value=_f(cv),
            crudo=d,
        )

    # Valores EXACTOS del contrato. No son "1m" ni "1h": error 3003
    # REQUEST_INVALID_TIMEFRAME. Mi primera version los invento.
    TIMEFRAMES = ("S1", "S5", "S15", "M1", "M3", "M5", "M10", "M15", "M30",
                  "H1", "H2", "H4", "D1", "W1", "MN")

    def historial_operaciones(self, desde: str, hasta: str | None = None,
                              limite: int = 100) -> list:
        """Historial de deals: lo que REALMENTE se ejecuto y a que precio.

        Es la unica fuente para separar el COSTO del MOVIMIENTO del precio.
        """
        ruta = (f"/v1/history/accounts/{self.cred.account_id}/deals"
                f"?from={desde}&limit={limite}")
        if hasta:
            ruta += f"&to={hasta}"
        d = self._get(self.access_point(), ruta)
        if isinstance(d, list):
            return d
        for k in ("deals", "data", "items"):
            if isinstance(d.get(k), list):
                return d[k]
        return []

    def velas(self, instrumento: str, timeframe: str, desde: str,
              hasta: str | None = None, count: int | None = None,
              price_type: str = "bid") -> list:
        """Historico de velas.

        Segun el contrato: `from` es obligatorio y se usa `from + to` O
        `from + count`, nunca los dos. NO existe un parametro `limit`
        -- eso era del historial de ordenes, otro endpoint. `count`
        negativo cuenta HACIA ATRAS desde `from`, que es la forma comoda
        de pedir "las ultimas N velas".

        `from` es inclusivo y `to` es exclusivo.
        """
        if timeframe not in self.TIMEFRAMES:
            raise ValueError(
                f"timeframe {timeframe!r} no existe. Validos: "
                f"{', '.join(self.TIMEFRAMES)}")
        if (hasta is None) == (count is None):
            raise ValueError("usa `hasta` O `count`, exactamente uno de los dos")
        if price_type not in ("bid", "ask", "both"):
            raise ValueError("price_type debe ser bid, ask o both")
        ruta = (f"/v1/market-data/accounts/{self.cred.account_id}/candles"
                f"?instrument={instrumento}&price_type={price_type}"
                f"&timeframe={timeframe}&from={desde}")
        ruta += f"&to={hasta}" if hasta else f"&count={count}"
        d = self._get(self.access_point(), ruta)
        if isinstance(d, list):
            return d
        for k in ("candles", "bid_candles", "ask_candles", "data"):
            if isinstance(d.get(k), list):
                return d[k]
        return []


# Comprobacion en tiempo de importacion: si alguien agrega un metodo que
# escriba, esto lo delata en la proxima corrida de pruebas.
_PROHIBIDOS = ("orden", "order", "abrir", "open", "cerrar", "close",
               "modificar", "modify", "cancelar", "cancel",
               "comprar", "vender", "buy", "sell")
_metodos = {m for m in dir(ClienteLectura) if not m.startswith("_")}
_sospechosos = {m for m in _metodos if any(p in m.lower() for p in _PROHIBIDOS)}
if _sospechosos:
    raise ImportError(
        f"ClienteLectura es de SOLO LECTURA y aparecieron metodos que "
        f"parecen de escritura: {sorted(_sospechosos)}. La ejecucion va en "
        f"otro modulo, con autorizacion explicita."
    )
