"""Motor de riesgo: funcion pura, deniega por defecto.

Reglas de diseno (no negociables):
  1. Sin red, sin LLM, sin estado mutable global. Entra estado, sale decision.
  2. DENIEGA POR DEFECTO: la orden se aprueba solo si pasa TODAS las
     comprobaciones. Una excepcion dentro de una regla -> rechazo, no permiso.
  3. Cada rechazo deja su codigo. El resumen cuenta PAREJAS (evaluadas /
     aprobadas), porque un contador solo es publicitario.
  4. Toda comprobacion que no se pueda hacer por falta de dato se cuenta
     como fallo, no como aprobacion: "no pude mirar" != "no habia nada".
"""

from __future__ import annotations

import math

from .kill_switch import KillSwitch
from .modelo import (
    AccountState,
    InstrumentSpec,
    ProposedOrder,
    Quote,
    RejectCode,
    RiskDecision,
    RiskLimits,
    Side,
)


def riesgo_por_operacion(
    orden: ProposedOrder, spec: InstrumentSpec
) -> float | None:
    """Perdida en moneda de la cuenta si el stop se ejecuta al precio exacto.

    Devuelve None si no hay stop: la ausencia de stop es riesgo
    INDETERMINADO, no riesgo cero.
    """
    if orden.stop_loss is None:
        return None
    distancia = abs(orden.reference_price - orden.stop_loss)
    if spec.tick_size <= 0:
        return None
    ticks = distancia / spec.tick_size
    return ticks * spec.tick_value_account_ccy * orden.volume


def margen_requerido(
    orden: ProposedOrder, spec: InstrumentSpec
) -> float:
    nocional = orden.volume * spec.contract_size * orden.reference_price
    return nocional * spec.margin_rate


def exposicion_nocional(
    volume: float, price: float, spec: InstrumentSpec
) -> float:
    return volume * spec.contract_size * price


class RiskEngine:
    def __init__(
        self,
        limits: RiskLimits | None = None,
        kill_switch: KillSwitch | None = None,
    ) -> None:
        self.limits = limits or RiskLimits()
        self.kill_switch = kill_switch or KillSwitch()
        self.evaluadas = 0
        self.aprobadas = 0
        self.rechazos: dict[str, int] = {}

    # ---------------- API publica ----------------

    def evaluar(
        self,
        orden: ProposedOrder,
        cuenta: AccountState,
        spec: InstrumentSpec,
        quote: Quote,
    ) -> RiskDecision:
        self.evaluadas += 1
        d = RiskDecision(approved=True)
        try:
            self._evaluar(orden, cuenta, spec, quote, d)
        except Exception as exc:  # noqa: BLE001 - a proposito: cualquier fallo rechaza
            d.reject(RejectCode.INVALID_INPUT, excepcion=repr(exc))
        if d.approved:
            self.aprobadas += 1
        for c in d.rejects:
            self.rechazos[c.value] = self.rechazos.get(c.value, 0) + 1
        return d

    def resumen(self) -> str:
        """Pareja obligatoria: cuantas entraron y cuantas salieron."""
        linea = (
            f"riesgo: evaluadas={self.evaluadas} aprobadas={self.aprobadas} "
            f"rechazadas={self.evaluadas - self.aprobadas}"
        )
        if self.evaluadas and self.aprobadas == 0:
            linea += "  ATENCION: se evaluaron ordenes y NINGUNA fue aprobada"
        if self.rechazos:
            top = sorted(self.rechazos.items(), key=lambda kv: -kv[1])
            linea += " | " + ", ".join(f"{k}={v}" for k, v in top)
        return linea

    # ---------------- reglas ----------------

    def _evaluar(
        self,
        o: ProposedOrder,
        a: AccountState,
        s: InstrumentSpec,
        q: Quote,
        d: RiskDecision,
    ) -> None:
        L = self.limits

        # 0. Corte global. Se mira primero y no se negocia.
        if self.kill_switch.activo():
            d.reject(
                RejectCode.KILL_SWITCH_ACTIVE, motivo=self.kill_switch.motivo()
            )
            return  # si esta cortado, no hay nada mas que evaluar

        # 1. Integridad de la entrada.
        if o.volume <= 0 or not math.isfinite(o.volume):
            d.reject(RejectCode.INVALID_INPUT, volume=o.volume)
        if not math.isfinite(o.reference_price) or o.reference_price <= 0:
            d.reject(RejectCode.INVALID_INPUT, reference_price=o.reference_price)
        if o.symbol != s.symbol or o.symbol != q.symbol:
            d.reject(
                RejectCode.INVALID_INPUT,
                desalineado={"orden": o.symbol, "spec": s.symbol, "quote": q.symbol},
            )
        if not d.approved:
            return

        # 2. Duplicados (idempotencia).
        if o.client_order_id in a.recent_client_order_ids:
            d.reject(RejectCode.DUPLICATE_ORDER, client_order_id=o.client_order_id)

        # 3. Mercado abierto.
        if not a.market_open:
            d.reject(RejectCode.MARKET_CLOSED)

        # 4. Cotizacion fresca. Sin ts utilizable -> rechazo.
        edad = (d.evaluated_at - q.ts).total_seconds()
        if edad > L.max_quote_age_s or edad < -L.max_quote_age_s:
            d.reject(RejectCode.QUOTE_STALE, edad_s=round(edad, 3))

        # 5. Spread anomalo. Sin mediana de referencia NO se asume normal.
        if q.median_spread is None or q.median_spread <= 0:
            d.reject(RejectCode.SPREAD_ANOMALOUS, motivo="sin mediana de referencia")
        elif q.spread > q.median_spread * L.max_spread_multiple:
            d.reject(
                RejectCode.SPREAD_ANOMALOUS,
                spread=q.spread,
                mediana=q.median_spread,
                multiplo=round(q.spread / q.median_spread, 2),
            )

        # 6. Volatilidad extrema (si hay ATR y una distancia de stop que comparar).
        if q.atr is not None and q.atr > 0 and o.stop_loss is not None:
            dist = abs(o.reference_price - o.stop_loss)
            if dist > q.atr * L.max_atr_multiple:
                d.reject(
                    RejectCode.VOLATILITY_EXTREME,
                    distancia_stop=dist,
                    atr=q.atr,
                )

        # 7. Stop loss obligatorio y en el lado correcto.
        if L.require_stop_loss and o.stop_loss is None:
            d.reject(RejectCode.MISSING_STOP_LOSS)
        elif o.stop_loss is not None:
            mal_lado = (
                o.side is Side.BUY and o.stop_loss >= o.reference_price
            ) or (o.side is Side.SELL and o.stop_loss <= o.reference_price)
            if mal_lado:
                d.reject(
                    RejectCode.STOP_ON_WRONG_SIDE,
                    side=o.side.value,
                    stop=o.stop_loss,
                    precio=o.reference_price,
                )

        # 8. Tamano conforme al contrato.
        if o.volume < s.min_volume:
            d.reject(RejectCode.SIZE_BELOW_MINIMUM, volume=o.volume, min=s.min_volume)
        if s.volume_step > 0:
            pasos = o.volume / s.volume_step
            if abs(pasos - round(pasos)) > 1e-9:
                d.reject(RejectCode.SIZE_NOT_ON_STEP, volume=o.volume, step=s.volume_step)

        # 9. Riesgo por operacion.
        if a.equity <= 0:
            d.reject(RejectCode.INVALID_INPUT, equity=a.equity)
            return
        riesgo = riesgo_por_operacion(o, s)
        if riesgo is None:
            d.reject(RejectCode.PER_TRADE_RISK_EXCEEDED, motivo="riesgo indeterminado")
        else:
            # Sobre el patrimonio EFECTIVO: si ya vas perdiendo en lo
            # abierto, el 0,5% se calcula sobre lo que de verdad tienes.
            tope = a.equity_efectivo * L.per_trade_risk_pct
            d.detail["riesgo_abs"] = round(riesgo, 2)
            d.detail["riesgo_pct"] = round(riesgo / a.equity, 5)
            if riesgo > tope:
                d.reject(
                    RejectCode.PER_TRADE_RISK_EXCEEDED,
                    riesgo=round(riesgo, 2),
                    tope=round(tope, 2),
                )

        # 10. Perdida diaria, contando lo ABIERTO.
        # Si solo se mirara lo cerrado, tres posiciones sangrando no
        # gatillarian el corte del 2% jamas.
        perdida = a.perdida_dia_total
        if perdida < 0:
            perdida_pct = abs(perdida) / a.equity
            d.detail["perdida_dia_pct"] = round(perdida_pct, 5)
            d.detail["perdida_dia_realizada"] = round(a.realized_pnl_today, 2)
            d.detail["perdida_dia_no_realizada"] = round(a.unrealized_pnl, 2)
            if perdida_pct >= L.daily_loss_limit_pct:
                d.reject(
                    RejectCode.DAILY_LOSS_LIMIT_HIT,
                    perdida_pct=round(perdida_pct, 5),
                )

        # 11. Drawdown de suspension, sobre el patrimonio EFECTIVO.
        if a.peak_equity > 0:
            dd = (a.peak_equity - a.equity_efectivo) / a.peak_equity
            d.detail["drawdown_pct"] = round(dd, 5)
            if dd >= L.max_drawdown_pct:
                d.reject(RejectCode.MAX_DRAWDOWN_HIT, drawdown_pct=round(dd, 5))

        # 12. Posiciones simultaneas.
        if len(a.open_positions) >= L.max_open_positions:
            d.reject(
                RejectCode.MAX_OPEN_POSITIONS,
                abiertas=len(a.open_positions),
                tope=L.max_open_positions,
            )

        # 13. Apalancamiento y exposicion.
        # El tope total es patrimonio x apalancamiento_maximo. Los topes por
        # instrumento y por grupo son fracciones de ESE total, no del
        # patrimonio: antes habia una constante magica (_APALANC_REF = 100)
        # escondida en la formula, que es la peor forma de fijar un limite.
        nueva = exposicion_nocional(o.volume, o.reference_price, s)
        tope_total = a.equity * L.apalancamiento_maximo
        todas = sum(
            p.volume * s.contract_size * p.entry_price
            for p in a.open_positions
        )
        d.detail["nocional_total"] = round(todas + nueva, 2)
        d.detail["apalancamiento_resultante"] = (
            round((todas + nueva) / a.equity, 2) if a.equity > 0 else None)
        if todas + nueva > tope_total:
            d.reject(
                RejectCode.LEVERAGE_EXCEEDED,
                nocional=round(todas + nueva, 2),
                tope=round(tope_total, 2),
                apalancamiento_maximo=L.apalancamiento_maximo,
            )
        mismo = sum(
            exposicion_nocional(p.volume, p.entry_price, s)
            for p in a.open_positions
            if p.symbol == o.symbol
        )
        if mismo + nueva > tope_total * L.max_instrument_exposure_pct:
            d.reject(
                RejectCode.INSTRUMENT_EXPOSURE_EXCEEDED,
                nocional=round(mismo + nueva, 2),
                tope=round(tope_total * L.max_instrument_exposure_pct, 2),
            )
        if s.correlation_group:
            grupo = sum(
                p.volume * s.contract_size * p.entry_price
                for p in a.open_positions
                if p.correlation_group == s.correlation_group
            )
            if grupo + nueva > tope_total * L.max_correlated_exposure_pct:
                d.reject(
                    RejectCode.CORRELATED_EXPOSURE_EXCEEDED,
                    grupo=s.correlation_group,
                    nocional=round(grupo + nueva, 2),
                    tope=round(tope_total * L.max_correlated_exposure_pct, 2),
                )

        # 14. Margen libre. No se usa el apalancamiento maximo por defecto.
        req = margen_requerido(o, s)
        d.detail["margen_requerido"] = round(req, 2)
        if req <= 0 or a.free_margin < req * L.min_free_margin_ratio:
            d.reject(
                RejectCode.INSUFFICIENT_FREE_MARGIN,
                libre=round(a.free_margin, 2),
                requerido=round(req, 2),
                ratio_minimo=L.min_free_margin_ratio,
            )

