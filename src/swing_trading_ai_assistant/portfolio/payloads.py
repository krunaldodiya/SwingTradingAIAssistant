"""Serialization for broker-neutral read-only records."""

from __future__ import annotations

from decimal import Decimal
from typing import cast

from .records import (
    GttRecord,
    GttSnapshot,
    HoldingRow,
    HoldingsSnapshot,
    OrderRecord,
    OrdersSnapshot,
    PositionRecord,
    PositionsSnapshot,
    Section,
    TradeRecord,
    TradesSnapshot,
)

SCHEMA_VERSION = 1
STATUS_OK = "OK"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_UNSUPPORTED = "UNSUPPORTED"


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def _quantity(value: Decimal) -> float:
    return float(value)


def _optional_money(value: Decimal | None) -> float | None:
    return None if value is None else _money(value)


def _optional_quantity(value: Decimal | None) -> float | None:
    return None if value is None else _quantity(value)


def holding_record(row: HoldingRow) -> dict[str, object]:
    return {
        "symbol": row.symbol,
        "exchange": row.exchange,
        "symbol_token": row.symbol_token,
        "isin": row.isin,
        "quantity": _quantity(row.quantity),
        "t1_quantity": _quantity(row.t1_quantity),
        "average_price": _money(row.average_price),
        "last_price": _money(row.last_price),
        "previous_close": _optional_money(row.previous_close),
        "invested": _money(row.invested),
        "current": _money(row.current),
        "pnl": _money(row.pnl),
        "pnl_pct": _optional_money(row.pnl_pct),
        "day_change": _optional_money(row.day_change),
        "day_pct": _optional_money(row.day_pct),
    }


def position_record(row: PositionRecord) -> dict[str, object]:
    return {
        "symbol": row.symbol,
        "exchange": row.exchange,
        "symbol_token": row.symbol_token,
        "product_type": row.product_type,
        "instrument_type": row.instrument_type,
        "quantity": _quantity(row.quantity),
        "average_price": _money(row.average_price),
        "last_price": _optional_money(row.last_price),
        "pnl": _optional_money(row.pnl),
        "pnl_pct": _optional_money(row.pnl_pct),
        "realised_pnl": _optional_money(row.realised_pnl),
        "unrealised_pnl": _optional_money(row.unrealised_pnl),
        "multiplier": _optional_quantity(row.multiplier),
        "pnl_source": row.pnl_source,
        "reported_at": row.reported_at,
    }


def order_record(row: OrderRecord) -> dict[str, object]:
    return {
        "order_id": row.order_id,
        "exchange_order_id": row.exchange_order_id,
        "parent_order_id": row.parent_order_id,
        "symbol": row.symbol,
        "exchange": row.exchange,
        "symbol_token": row.symbol_token,
        "side": row.side,
        "order_type": row.order_type,
        "product_type": row.product_type,
        "variety": row.variety,
        "status": row.status,
        "status_message": row.status_message,
        "quantity": _quantity(row.quantity),
        "filled_quantity": _quantity(row.filled_quantity),
        "pending_quantity": _quantity(row.pending_quantity),
        "price": _money(row.price),
        "trigger_price": _optional_money(row.trigger_price),
        "average_fill_price": _optional_money(row.average_fill_price),
        "validity": row.validity,
        "reported_at": row.reported_at,
    }


def trade_record(row: TradeRecord) -> dict[str, object]:
    return {
        "trade_id": row.trade_id,
        "order_id": row.order_id,
        "symbol": row.symbol,
        "exchange": row.exchange,
        "symbol_token": row.symbol_token,
        "side": row.side,
        "product_type": row.product_type,
        "quantity": _quantity(row.quantity),
        "price": _money(row.price),
        "trade_value": _money(row.trade_value),
        "reported_at": row.reported_at,
    }


def gtt_record(row: GttRecord) -> dict[str, object]:
    return {
        "rule_id": row.rule_id,
        "symbol": row.symbol,
        "exchange": row.exchange,
        "symbol_token": row.symbol_token,
        "side": row.side,
        "product_type": row.product_type,
        "gtt_type": row.gtt_type,
        "quantity": _quantity(row.quantity),
        "disclosed_quantity": _optional_quantity(row.disclosed_quantity),
        "price": _money(row.price),
        "trigger_price": _money(row.trigger_price),
        "stoploss_price": _optional_money(row.stoploss_price),
        "stoploss_trigger_price": _optional_money(row.stoploss_trigger_price),
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "expires_at": row.expires_at,
    }


RecordSnapshot = (
    HoldingsSnapshot | PositionsSnapshot | OrdersSnapshot | TradesSnapshot | GttSnapshot
)


def section_records(
    section: Section, snapshot: RecordSnapshot
) -> list[dict[str, object]]:
    if section is Section.HOLDINGS:
        return [holding_record(row) for row in cast("HoldingsSnapshot", snapshot).rows]
    if section is Section.POSITIONS:
        return [
            position_record(row) for row in cast("PositionsSnapshot", snapshot).rows
        ]
    if section is Section.ORDERS:
        return [order_record(row) for row in cast("OrdersSnapshot", snapshot).rows]
    if section is Section.TRADES:
        return [trade_record(row) for row in cast("TradesSnapshot", snapshot).rows]
    return [gtt_record(row) for row in cast("GttSnapshot", snapshot).rows]


def section_limitations(section: Section, snapshot: RecordSnapshot) -> tuple[str, ...]:
    if section is Section.HOLDINGS:
        return cast("HoldingsSnapshot", snapshot).limitations
    if section is Section.POSITIONS:
        return cast("PositionsSnapshot", snapshot).limitations
    if section is Section.ORDERS:
        return cast("OrdersSnapshot", snapshot).limitations
    if section is Section.TRADES:
        return cast("TradesSnapshot", snapshot).limitations
    return cast("GttSnapshot", snapshot).limitations


def section_body(
    section: Section,
    *,
    status: str,
    source: str,
    records: list[dict[str, object]] | None = None,
    limitations: tuple[str, ...] = (),
    error_code: str | None = None,
    message: str | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "status": status,
        "source": source,
        "records": [] if records is None else records,
        "limitations": list(limitations),
    }
    if error_code is not None:
        body["error_code"] = error_code
    if message is not None:
        body["message"] = message
    return body


def section_payload(
    *,
    account_id: str,
    broker: str,
    section: Section,
    retrieved_at: str,
    body: dict[str, object],
) -> dict[str, object]:
    limitations = ["BROKER_READ_ONLY", "POINT_IN_TIME_SNAPSHOT"]
    raw_limitations = body.get("limitations")
    if isinstance(raw_limitations, list):
        values = cast("list[object]", raw_limitations)
        limitations.extend(str(item) for item in values)
    return {
        "schema_version": SCHEMA_VERSION,
        "account_id": account_id,
        "broker": broker,
        "section": section.value,
        "retrieved_at": retrieved_at,
        **body,
        "limitations": list(dict.fromkeys(limitations)),
    }


def snapshot_payload(
    *,
    account_id: str,
    broker: str,
    retrieved_at: str,
    capabilities: tuple[Section, ...],
    sections: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "account_id": account_id,
        "broker": broker,
        "retrieved_at": retrieved_at,
        "capabilities": [section.value for section in capabilities],
        "sections": sections,
        "limitations": ["BROKER_READ_ONLY", "POINT_IN_TIME_SNAPSHOT"],
    }


__all__ = [
    "RecordSnapshot",
    "SCHEMA_VERSION",
    "STATUS_OK",
    "STATUS_UNAVAILABLE",
    "STATUS_UNSUPPORTED",
    "gtt_record",
    "holding_record",
    "order_record",
    "position_record",
    "section_body",
    "section_limitations",
    "section_payload",
    "section_records",
    "snapshot_payload",
    "trade_record",
]
