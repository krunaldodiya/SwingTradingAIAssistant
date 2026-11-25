"""Broker-neutral read-only portfolio record types."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Section(StrEnum):
    """One read-only broker record section."""

    HOLDINGS = "holdings"
    POSITIONS = "positions"
    ORDERS = "orders"
    TRADES = "trades"
    GTT = "gtt"


SECTION_ORDER: tuple[Section, ...] = (
    Section.HOLDINGS,
    Section.POSITIONS,
    Section.ORDERS,
    Section.TRADES,
    Section.GTT,
)


@dataclass(frozen=True)
class HoldingRow:
    symbol: str
    quantity: Decimal
    t1_quantity: Decimal
    average_price: Decimal
    last_price: Decimal
    previous_close: Decimal | None
    invested: Decimal
    current: Decimal
    pnl: Decimal
    pnl_pct: Decimal | None
    day_change: Decimal | None
    day_pct: Decimal | None
    exchange: str | None = None
    symbol_token: str | None = None
    isin: str | None = None


@dataclass(frozen=True)
class HoldingsSnapshot:
    rows: tuple[HoldingRow, ...]
    invested: Decimal
    current: Decimal
    overall_pnl: Decimal
    overall_pnl_pct: Decimal | None
    day_change: Decimal | None
    day_change_pct: Decimal | None
    limitations: tuple[str, ...]
    retrieved_at: str


@dataclass(frozen=True)
class PositionRecord:
    symbol: str
    exchange: str
    symbol_token: str | None
    product_type: str
    instrument_type: str | None
    quantity: Decimal
    average_price: Decimal
    last_price: Decimal | None
    pnl: Decimal | None
    pnl_pct: Decimal | None
    realised_pnl: Decimal | None
    unrealised_pnl: Decimal | None
    multiplier: Decimal | None
    pnl_source: str | None
    reported_at: str | None


@dataclass(frozen=True)
class PositionsSnapshot:
    rows: tuple[PositionRecord, ...]
    limitations: tuple[str, ...]
    retrieved_at: str


@dataclass(frozen=True)
class OrderRecord:
    order_id: str
    exchange_order_id: str | None
    parent_order_id: str | None
    symbol: str
    exchange: str
    symbol_token: str | None
    side: str
    order_type: str
    product_type: str
    variety: str | None
    status: str
    status_message: str | None
    quantity: Decimal
    filled_quantity: Decimal
    pending_quantity: Decimal
    price: Decimal
    trigger_price: Decimal | None
    average_fill_price: Decimal | None
    validity: str | None
    reported_at: str | None


@dataclass(frozen=True)
class OrdersSnapshot:
    rows: tuple[OrderRecord, ...]
    limitations: tuple[str, ...]
    retrieved_at: str


@dataclass(frozen=True)
class TradeRecord:
    trade_id: str
    order_id: str
    symbol: str
    exchange: str
    symbol_token: str | None
    side: str
    product_type: str
    quantity: Decimal
    price: Decimal
    trade_value: Decimal
    reported_at: str | None


@dataclass(frozen=True)
class TradesSnapshot:
    rows: tuple[TradeRecord, ...]
    limitations: tuple[str, ...]
    retrieved_at: str


@dataclass(frozen=True)
class GttRecord:
    rule_id: str
    symbol: str
    exchange: str
    symbol_token: str | None
    side: str
    product_type: str
    gtt_type: str | None
    quantity: Decimal
    disclosed_quantity: Decimal | None
    price: Decimal
    trigger_price: Decimal
    stoploss_price: Decimal | None
    stoploss_trigger_price: Decimal | None
    status: str | None
    created_at: str | None
    updated_at: str | None
    expires_at: str | None


@dataclass(frozen=True)
class GttSnapshot:
    rows: tuple[GttRecord, ...]
    limitations: tuple[str, ...]
    retrieved_at: str


__all__ = [
    "GttRecord",
    "GttSnapshot",
    "HoldingRow",
    "HoldingsSnapshot",
    "OrderRecord",
    "OrdersSnapshot",
    "PositionRecord",
    "PositionsSnapshot",
    "SECTION_ORDER",
    "Section",
    "TradeRecord",
    "TradesSnapshot",
]
