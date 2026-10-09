"""Objective capability-specific stock eligibility and safety gating (G03)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any, Final, TypeGuard, cast

from .runtime_source_verifier import runtime_source_sha256
from .stock_eligibility_runtime_identity_manifest import (
    STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V1,
)

SCHEMA: Final = "stock-eligibility@v1"
MINIMUM_COMPLETED_SESSIONS: Final = 21
MINIMUM_CLOSE_PRICE_INR: Final = 10.0
_ISIN_PATTERN: Final = re.compile(r"^INE[A-Z0-9]{9}$")
_SYMBOL_PATTERN: Final = re.compile(r"[A-Z0-9](?:[A-Z0-9.&_-]{0,30}[A-Z0-9])?\Z")
_RUNTIME_SOURCES = ("src/swing_trading_ai_assistant/market_data/stock_eligibility.py",)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _runtime_identity() -> str:
    sources = STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V1
    if tuple(sources) != _RUNTIME_SOURCES:
        raise ValueError("stock eligibility runtime scope invalid")
    root = Path(__file__).parent.parent
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("stock eligibility runtime identity invalid")
    return hashlib.sha256(
        ":".join(f"{k}={v}" for k, v in sorted(sources.items())).encode("utf-8")
    ).hexdigest()


def _check_mapping(
    symbol: str, series: object, exchange: object, isin: object
) -> tuple[list[str], list[str]]:
    if (
        type(series) is not str
        or type(exchange) is not str
        or type(isin) is not str
        or not series.strip()
        or not exchange.strip()
        or not isin.strip()
    ):
        return [], ["MAPPING_UNVERIFIED"]
    if (
        series.strip().upper() != "EQ"
        or exchange.strip().upper() != "NSE"
        or not _ISIN_PATTERN.match(isin.strip().upper())
        or _SYMBOL_PATTERN.fullmatch(symbol) is None
    ):
        return ["UNSUPPORTED_MAPPING"], []
    return [], []


def _is_string_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    if not isinstance(value, Mapping):
        return False
    return all(type(key) is str for key in cast(Mapping[object, object], value))


def _is_mapping_sequence(
    value: object,
) -> TypeGuard[Sequence[Mapping[str, object]]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return False
    return all(
        _is_string_object_mapping(item) for item in cast(Sequence[object], value)
    )


def _is_bar_sequence(value: object) -> TypeGuard[Sequence[Mapping[str, object]]]:
    return _is_mapping_sequence(value)


def _is_event_snapshot(
    value: object,
) -> TypeGuard[Sequence[Mapping[str, object]]]:
    return _is_mapping_sequence(value)


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        numeric = float(value)
    except OverflowError:
        return None
    return numeric if math.isfinite(numeric) else None


def _validate_bar(
    bar: Mapping[str, object],
) -> tuple[date, float, float, float, float, float] | None:
    raw_date = bar.get("date")
    if type(raw_date) is not str:
        return None
    try:
        session_date = date.fromisoformat(raw_date)
    except ValueError:
        return None
    if session_date.isoformat() != raw_date:
        return None

    open_price = _finite_number(bar.get("open"))
    high_price = _finite_number(bar.get("high"))
    low_price = _finite_number(bar.get("low"))
    close_price = _finite_number(bar.get("close"))
    volume = _finite_number(bar.get("volume"))
    if (
        open_price is None
        or high_price is None
        or low_price is None
        or close_price is None
        or volume is None
    ):
        return None

    if (
        open_price <= 0
        or high_price <= 0
        or low_price <= 0
        or close_price <= 0
        or volume < 0
    ):
        return None
    values_within_range = (
        low_price <= open_price <= high_price and low_price <= close_price <= high_price
    )
    if not values_within_range:
        return None
    return session_date, open_price, high_price, low_price, close_price, volume


def _check_bars(
    bars: object,
) -> tuple[list[str], list[str], int, float | None, float | None]:
    if not _is_bar_sequence(bars):
        return [], ["DATA_UNVERIFIED"], 0, None, None

    session_count = len(bars)
    if session_count < MINIMUM_COMPLETED_SESSIONS:
        return ["INSUFFICIENT_HISTORY"], [], session_count, None, None

    total_volume = 0.0
    zero_volume = False
    latest_close: float | None = None
    previous_date: date | None = None

    for bar in bars:
        validated = _validate_bar(bar)
        if validated is None:
            return ["DATA_QUALITY_INVALID"], [], session_count, None, None
        session_date, _, _, _, close_price, volume = validated
        if previous_date is not None and session_date <= previous_date:
            return ["DATA_QUALITY_INVALID"], [], session_count, None, None
        previous_date = session_date
        total_volume += volume
        if volume == 0:
            zero_volume = True
        latest_close = close_price

    failures: list[str] = []
    avg_volume = total_volume / session_count
    if zero_volume or avg_volume <= 0:
        failures.append("INSUFFICIENT_LIQUIDITY")

    if latest_close is not None and latest_close < MINIMUM_CLOSE_PRICE_INR:
        failures.append("PRICE_INTEGRITY_FAILED")

    return failures, [], session_count, latest_close, avg_volume


def _check_events(
    event_notices: object,
) -> tuple[list[str], list[str], bool | None]:
    if event_notices is None or not _is_event_snapshot(event_notices):
        return [], ["EVENT_RISK_UNVERIFIED"], None
    if event_notices:
        return ["EVENT_RISK_DETECTED"], [], True
    return [], [], False


def evaluate_stock_eligibility(
    *,
    symbol: str,
    series: str,
    exchange: str,
    isin: str,
    bars: Sequence[dict[str, Any]],
    event_notices: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate objective stock eligibility and safety gates fail-closed."""
    runtime = _runtime_identity()
    if type(symbol) is not str or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    clean_symbol = symbol.strip().upper()

    mapping_failures, mapping_unknown = _check_mapping(
        clean_symbol, series, exchange, isin
    )
    bar_failures, bar_unknown, session_count, latest_close, avg_volume = _check_bars(
        bars
    )
    event_failures, event_unknown, event_risk_flag = _check_events(event_notices)
    failure_reasons = [
        *mapping_failures,
        *mapping_unknown,
        *bar_failures,
        *bar_unknown,
        *event_failures,
        *event_unknown,
    ]

    status = (
        "INELIGIBLE"
        if mapping_failures or bar_failures or event_failures
        else "UNKNOWN"
        if mapping_unknown or bar_unknown or event_unknown
        else "ELIGIBLE"
    )

    result_payload: dict[str, Any] = {
        "schema": SCHEMA,
        "symbol": clean_symbol,
        "status": status,
        "failure_reasons": failure_reasons,
        "evaluated_sessions_count": session_count,
        "latest_close_price": latest_close,
        "average_daily_volume": avg_volume,
        "event_risk_flag": event_risk_flag,
        "runtime_code_identity_sha256": runtime,
    }

    provenance_hash = hashlib.sha256(_canonical_bytes(result_payload)).hexdigest()
    result_payload["provenance_sha256"] = provenance_hash
    return result_payload
