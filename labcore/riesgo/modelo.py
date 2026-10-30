"""Tipos del motor de riesgo.

Deliberadamente sin dependencias externas: este modulo no importa pandas,
ni red, ni nada que pueda fallar en caliente. El motor de riesgo tiene que
poder evaluar una orden aunque el resto del sistema este caido.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class RejectCode(str, Enum):
    """Un codigo por regla. Se registra en el log y se cuenta por separado."""

    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    MISSING_STOP_LOSS = "MISSING_STOP_LOSS"
    STOP_ON_WRONG_SIDE = "STOP_ON_WRONG_SIDE"
    PER_TRADE_RISK_EXCEEDED = "PER_TRADE_RISK_EXCEEDED"
    DAILY_LOSS_LIMIT_HIT = "DAILY_LOSS_LIMIT_HIT"
    MAX_DRAWDOWN_HIT = "MAX_DRAWDOWN_HIT"
    MAX_OPEN_POSITIONS = "MAX_OPEN_POSITIONS"
    LEVERAGE_EXCEEDED = "LEVERAGE_EXCEEDED"
    INSTRUMENT_EXPOSURE_EXCEEDED = "INSTRUMENT_EXPOSURE_EXCEEDED"
    CORRELATED_EXPOSURE_EXCEEDED = "CORRELATED_EXPOSURE_EXCEEDED"
    INSUFFICIENT_FREE_MARGIN = "INSUFFICIENT_FREE_MARGIN"
    SPREAD_ANOMALOUS = "SPREAD_ANOMALOUS"
    QUOTE_STALE = "QUOTE_STALE"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    MARKET_CLOSED = "MARKET_CLOSED"
    VOLATILITY_EXTREME = "VOLATILITY_EXTREME"
    SIZE_BELOW_MINIMUM = "SIZE_BELOW_MINIMUM"
    SIZE_NOT_ON_STEP = "SIZE_NOT_ON_STEP"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class RiskLimits:
    """Limites del laboratorio. Son parametros de experimento, NO una
    autorizacion para arriesgar capital real."""

    per_trade_risk_pct: float = 0.005        # 0,5% del patrimonio
    daily_loss_limit_pct: float = 0.02       # 2% de perdida diaria
    max_drawdown_pct: float = 0.10           # 10% -> suspension
    max_open_positions: int = 3
    # Apalancamiento: tope de nocional TOTAL sobre patrimonio. 5.0 = 5x.
    # No se usa el maximo del broker automaticamente (regla del encargo).
    apalancamiento_maximo: float = 5.0
    # Exposicion por instrumento y por grupo, como fraccion del nocional
    # total permitido. 0.4 = ningun instrumento se lleva mas del 40%.
    max_instrument_exposure_pct: float = 0.40
    max_correlated_exposure_pct: float = 0.60
    max_spread_multiple: float = 3.0         # x la mediana reciente
    max_quote_age_s: float = 5.0
    min_free_margin_ratio: float = 2.0       # margen libre / margen requerido
    require_stop_loss: bool = True
    max_atr_multiple: float = 4.0            # x el ATR tipico del instrumento


@dataclass(frozen=True)
class InstrumentSpec:
    """Contrato del instrumento. Se llena desde el broker, nunca a mano."""

    symbol: str
    contract_size: float
    tick_size: float
    tick_value_account_ccy: float
    min_volume: float
    volume_step: float
    margin_rate: float          # fraccion del nocional
    correlation_group: str = "" # p.ej. "USD_MAJOR", "METALS", "CRYPTO"


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    ts: datetime
    median_spread: float | None = None   # mediana reciente, misma unidad que (ask-bid)
    atr: float | None = None

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def mid(self) -> float:
        return (self.ask + self.bid) / 2.0


@dataclass(frozen=True)
class OpenPosition:
    symbol: str
    side: Side
    volume: float
    entry_price: float
    stop_loss: float | None
    correlation_group: str = ""


@dataclass(frozen=True)
class AccountState:
    equity: float
    balance: float
    free_margin: float
    used_margin: float
    peak_equity: float               # maximo historico, para el drawdown
    realized_pnl_today: float        # negativo si se perdio
    # P&L de lo que sigue ABIERTO, valorizado al ultimo precio.
    #
    # AGUJERO CERRADO el 2026-10-29: antes la perdida diaria y el drawdown
    # solo miraban lo CERRADO. Con tres posiciones abiertas sangrando, el
    # corte del 2% no se disparaba nunca -- el sistema se quedaba ciego
    # justo cuando mas importa. Un broker real te llama a margen por el
    # patrimonio, no por lo realizado.
    unrealized_pnl: float = 0.0
    open_positions: tuple[OpenPosition, ...] = ()
    market_open: bool = True
    recent_client_order_ids: frozenset[str] = frozenset()


    @property
    def equity_efectivo(self) -> float:
        """Patrimonio contando lo abierto. Es el numero que importa."""
        return self.equity + self.unrealized_pnl

    @property
    def perdida_dia_total(self) -> float:
        """Perdida del dia contando lo abierto. Negativa si se pierde."""
        return self.realized_pnl_today + self.unrealized_pnl


@dataclass(frozen=True)
class ProposedOrder:
    client_order_id: str
    symbol: str
    side: Side
    volume: float
    reference_price: float           # precio al que se evalua (ask si compra)
    stop_loss: float | None
    take_profit: float | None = None
    strategy_id: str = "desconocida"


@dataclass
class RiskDecision:
    approved: bool
    rejects: list[RejectCode] = field(default_factory=list)
    detail: dict[str, object] = field(default_factory=dict)
    evaluated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def reject(self, code: RejectCode, **detail: object) -> None:
        self.approved = False
        if code not in self.rejects:
            self.rejects.append(code)
        self.detail.update(detail)

    @property
    def reason_text(self) -> str:
        if self.approved:
            return "aprobada"
        return ", ".join(c.value for c in self.rejects)
