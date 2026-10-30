"""Envio de ordenes a Exness. Modulo SEPARADO del cliente de lectura.

Esta en su propio archivo a proposito: el cliente de lectura no puede
operar porque no tiene el codigo, y este modulo hay que importarlo
explicitamente. No se llega aqui por accidente.

CINCO CERROJOS, en orden, y todos tienen que ceder para que salga una orden:

  1. El entorno tiene que ser DEMO, salvo autorizacion escrita para REAL.
  2. Se CONSULTA A LA API si la cuenta es demo. No se confia en el .env:
     un archivo mal escrito no puede convertir una cuenta real en demo.
  3. El motor de riesgo tiene que aprobar. Es el mismo que usa el
     backtester: si fuera otro, el historial de pruebas no probaria nada.
  4. El volumen y los precios tienen que cumplir las reglas del
     instrumento, leidas de la API, no supuestas.
  5. `permitir_envio=True` explicito en la llamada.

Y despues de enviar: el POST devuelve un ACK (202), NO una confirmacion.
El resultado final llega por eventos. Por eso toda orden se reconcilia
consultando el estado de la operacion antes de darla por hecha.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

import httpx

from ..riesgo.modelo import (
    AccountState, InstrumentSpec, ProposedOrder, Quote, RiskDecision, Side,
)
from ..riesgo.motor import RiskEngine
from .cliente import TIMEOUT, ErrorExness, _transporte_ipv4
from .entorno import Config, Entorno
from .firma import cargar_llave, firmar


class EjecucionBloqueada(RuntimeError):
    """Un cerrojo no cedio. No se envio nada."""


@dataclass
class Ack:
    operation_id: str
    crudo: dict

    def __str__(self) -> str:
        return f"ACK operation_id={self.operation_id}"


def _cuantizar(valor: float, digitos: int) -> str:
    """Precio con a lo sumo `point_digits` decimales, como exige el contrato.

    Se trunca hacia abajo, no se redondea: redondear hacia arriba un stop
    puede dejarlo del lado equivocado del precio.
    """
    q = Decimal(1).scaleb(-digitos)
    return str(Decimal(str(valor)).quantize(q, rounding=ROUND_DOWN))


def _cuantizar_volumen(vol: float, paso: float, minimo: float,
                       maximo: float) -> str:
    """Volumen multiplo exacto de volume_step, dentro de min y max."""
    p = Decimal(str(paso))
    v = (Decimal(str(vol)) / p).to_integral_value(rounding=ROUND_DOWN) * p
    if v < Decimal(str(minimo)):
        raise EjecucionBloqueada(
            f"volumen {vol} queda en {v} tras ajustar al paso {paso}, "
            f"bajo el minimo {minimo} del instrumento")
    if v > Decimal(str(maximo)):
        raise EjecucionBloqueada(
            f"volumen {v} sobre el maximo {maximo} del instrumento")
    return str(v.normalize() if v == v.to_integral() else v)


class Ejecutor:
    def __init__(self, cfg: Config, cliente_lectura, riesgo: RiskEngine) -> None:
        self.cfg = cfg
        self.lectura = cliente_lectura      # para condiciones y estado
        self.riesgo = riesgo
        self._llave = cargar_llave(cfg.private_key_path)
        self._http = httpx.Client(timeout=TIMEOUT, transport=_transporte_ipv4())
        self._es_demo: bool | None = None
        self.enviadas: list[Ack] = []

    def desconectar(self) -> None:
        self._http.close()

    def __enter__(self): return self
    def __exit__(self, *a): self.desconectar()

    # ---------- cerrojo 2: preguntarle a la API, no al archivo ----------

    def confirmar_demo(self) -> bool:
        """Pregunta a la API si la cuenta es demo. Se cachea por sesion."""
        if self._es_demo is None:
            d = self.lectura.cuenta()
            if "is_demo" not in d:
                raise EjecucionBloqueada(
                    "la API no devolvio is_demo: no puedo confirmar que la "
                    "cuenta sea de practica, asi que no envio nada")
            self._es_demo = bool(d["is_demo"])
        return self._es_demo

    # ---------- envio ----------

    def abrir_posicion(
        self,
        instrumento: str,
        side: Side,
        volumen: float,
        stop_loss: float,
        take_profit: float | None,
        cuenta: AccountState,
        spec: InstrumentSpec,
        quote: Quote,
        *,
        permitir_envio: bool = False,
    ) -> tuple[Ack | None, RiskDecision | None, str]:
        """Abre una posicion a mercado. Devuelve (ack, decision, explicacion)."""

        # --- cerrojo 1: entorno ---
        if self.cfg.entorno is not Entorno.DEMO:
            raise EjecucionBloqueada(
                "este modulo solo opera en DEMO en esta etapa. REAL requiere "
                "una autorizacion aparte y explicita de Fernando.")

        # --- cerrojo 2: la API confirma que es demo ---
        if not self.confirmar_demo():
            raise EjecucionBloqueada(
                "la API dice is_demo=False: NO es una cuenta de practica. "
                "No envio nada.")

        # --- cerrojo 4: reglas del instrumento, leidas de la API ---
        k = self.lectura.condiciones(instrumento)
        cond = k.crudo.get("conditions", k.crudo)
        digitos = int(cond.get("point_digits", 5))
        vmax = float(cond.get("volume_max", 200))
        if cond.get("trade_mode") == "trading_disabled":
            raise EjecucionBloqueada(
                f"{instrumento}: trade_mode=trading_disabled")
        vol_txt = _cuantizar_volumen(volumen, k.volume_step, k.volume_min, vmax)
        sl_txt = _cuantizar(stop_loss, digitos)
        tp_txt = _cuantizar(take_profit, digitos) if take_profit else None

        # --- cerrojo 3: el MISMO motor de riesgo del backtester ---
        orden = ProposedOrder(
            client_order_id=uuid.uuid4().hex[:16], symbol=instrumento,
            side=side, volume=float(vol_txt),
            reference_price=quote.ask if side is Side.BUY else quote.bid,
            stop_loss=float(sl_txt),
            take_profit=float(tp_txt) if tp_txt else None,
            strategy_id="manual-prueba-swap")
        d = self.riesgo.evaluar(orden, cuenta, spec, quote)
        if not d.approved:
            return None, d, f"VETADA por riesgo: {d.reason_text}"

        # --- cerrojo 5: autorizacion explicita en la llamada ---
        if not permitir_envio:
            return None, d, (
                "SIMULACRO: paso los 4 cerrojos y el motor de riesgo, pero "
                "permitir_envio=False, asi que NO se envio nada.")

        cuerpo = {"instrument": instrumento, "side": side.value.lower(),
                  "volume": vol_txt, "stop_loss_price": sl_txt}
        if tp_txt:
            cuerpo["take_profit_price"] = tp_txt
        crudo = json.dumps(cuerpo, separators=(",", ":")).encode()

        ruta = f"/v1/trading/accounts/{self.cfg.account_id}/positions"
        # La clave de idempotencia es obligatoria y entre 5 y 128 caracteres
        # en todo lo que modifica estado. Evita que un reintento abra dos.
        idem = f"tl-{uuid.uuid4().hex}"
        cab = firmar(llave=self._llave, api_key=self.cfg.api_key,
                     method="POST", path=ruta, cuerpo=crudo,
                     idempotency_key=idem)
        cab["Content-Type"] = "application/json"

        r = self._http.post(self.lectura.access_point() + ruta,
                            content=crudo, headers=cab)
        if r.status_code != 202:
            raise ErrorExness(r.status_code, r.text, ruta)
        resp = r.json()
        op = str(resp.get("operation_id") or resp.get("id") or "")
        ack = Ack(operation_id=op, crudo=resp)
        self.enviadas.append(ack)
        return ack, d, (
            f"ENVIADA. {ack}. El POST devuelve un ACK, no una confirmacion: "
            f"hay que reconciliar con el estado de la operacion.")

    def cerrar_posicion(self, position_id: str, volumen: float | None = None,
                        *, permitir_envio: bool = False) -> tuple[Ack | None, str]:
        """Cierra una posicion. Sin `volumen`, cierra el total.

        Pasa por los mismos cerrojos de entorno que la apertura. NO pasa
        por el motor de riesgo a proposito: cerrar REDUCE exposicion, y un
        motor de riesgo que impida cerrar es un peligro, no una proteccion.
        """
        if self.cfg.entorno is not Entorno.DEMO:
            raise EjecucionBloqueada("solo DEMO en esta etapa")
        if not self.confirmar_demo():
            raise EjecucionBloqueada("la API dice is_demo=False")
        if not permitir_envio:
            return None, "SIMULACRO: no se envio el cierre"

        ruta = (f"/v1/trading/accounts/{self.cfg.account_id}"
                f"/positions/{position_id}")
        # Sin cuerpo = cierre total, segun el contrato: "if volume is
        # omitted, the whole remaining position volume is closed".
        cuerpo = (json.dumps({"volume": str(volumen)},
                             separators=(",", ":")).encode()
                  if volumen else b"")
        idem = f"tl-close-{uuid.uuid4().hex}"
        cab = firmar(llave=self._llave, api_key=self.cfg.api_key,
                     method="DELETE", path=ruta, cuerpo=cuerpo,
                     idempotency_key=idem)
        if cuerpo:
            cab["Content-Type"] = "application/json"
        r = self._http.request("DELETE", self.lectura.access_point() + ruta,
                               content=cuerpo or None, headers=cab)
        if r.status_code != 202:
            raise ErrorExness(r.status_code, r.text, ruta)
        resp = r.json()
        ack = Ack(str(resp.get("operation_id") or ""), resp)
        self.enviadas.append(ack)
        return ack, f"CIERRE ENVIADO. {ack}"

    # ---------- reconciliacion ----------

    def estado_operacion(self, operation_id: str) -> dict:
        ruta = (f"/v1/trading/accounts/{self.cfg.account_id}"
                f"/operations/{operation_id}")
        cab = firmar(llave=self._llave, api_key=self.cfg.api_key,
                     method="GET", path=ruta)
        r = self._http.get(self.lectura.access_point() + ruta, headers=cab)
        if r.status_code != 200:
            raise ErrorExness(r.status_code, r.text, ruta)
        return r.json()
