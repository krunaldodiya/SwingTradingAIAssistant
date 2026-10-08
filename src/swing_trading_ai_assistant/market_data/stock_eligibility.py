"""Objective capability-specific stock eligibility and safety gating (G03)."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from .runtime_source_verifier import runtime_source_sha256
from .stock_eligibility_runtime_identity_manifest import (
    STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V1,
)

SCHEMA: Final = "stock-eligibility@v1"
_ISIN_PATTERN: Final = re.compile(r"^INE[A-Z0-9]{9}$")
_RISK_KEYWORDS: Final = (
    "SUSPENSION",
    "DELISTING",
    "AMALGAMATION",
    "SCHEME OF ARRANGEMENT",
    "CAPITAL REDUCTION",
    "WINDING UP",
)
_RUNTIME_SOURCES = ("src/swing_trading_ai_assistant/market_data/stock_eligibility.py",)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


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


def _check_mapping(series: str, exchange: str, isin: str) -> list[str]:
    if (
        series.strip().upper() != "EQ"
        or exchange.strip().upper() != "NSE"
        or not _ISIN_PATTERN.match(isin.strip().upper())
    ):
        return ["UNSUPPORTED_MAPPING"]
    return []


def _validate_bar(
    bar: dict[str, Any],
) -> tuple[bool, float, float, float, float, float]:
    try:
        o = float(bar["open"])  # pyright: ignore[reportIndexIssue]
        h = float(bar["high"])  # pyright: ignore[reportIndexIssue]
        low_val = float(bar["low"])  # pyright: ignore[reportIndexIssue]
        c = float(bar["close"])  # pyright: ignore[reportIndexIssue]
        v = float(bar["volume"])  # pyright: ignore[reportIndexIssue]
    except (KeyError, TypeError, ValueError):
        return False, 0.0, 0.0, 0.0, 0.0, 0.0

    if o <= 0 or h <= 0 or low_val <= 0 or c <= 0 or v < 0:
        return False, 0.0, 0.0, 0.0, 0.0, 0.0
    if not (low_val <= o <= h and low_val <= c <= h):
        return False, 0.0, 0.0, 0.0, 0.0, 0.0
    return True, o, h, low_val, c, v


def _check_bars(
    bars: Sequence[dict[str, Any]],
    minimum_sessions: int,
    minimum_close_price: float,
) -> tuple[list[str], float | None, float | None]:
    if len(bars) < minimum_sessions:
        return ["INSUFFICIENT_HISTORY"], None, None

    total_volume = 0.0
    zero_volume = False
    latest_close: float | None = None

    for i, bar in enumerate(bars):
        valid, _, _, _, c, v = _validate_bar(bar)
        if not valid:
            return ["DATA_QUALITY_INVALID"], None, None
        total_volume += v
        if v == 0:
            zero_volume = True
        if i == len(bars) - 1:
            latest_close = c

    failures: list[str] = []
    avg_volume = total_volume / len(bars)
    if zero_volume or avg_volume < 1000.0:
        failures.append("INSUFFICIENT_LIQUIDITY")

    if latest_close is not None and latest_close < minimum_close_price:
        failures.append("PRICE_INTEGRITY_FAILED")

    return failures, latest_close, avg_volume


def _check_events(
    event_notices: Sequence[dict[str, Any]] | None,
) -> tuple[list[str], bool]:
    if not event_notices:
        return [], False
    for notice in event_notices:
        text_corpus = (
            str(notice.get("subject", ""))
            + " "
            + str(notice.get("description", ""))
            + " "
            + str(notice.get("category", ""))
        ).upper()
        if any(keyword in text_corpus for keyword in _RISK_KEYWORDS):
            return ["EVENT_RISK_DETECTED"], True
    return [], False


def evaluate_stock_eligibility(
    *,
    symbol: str,
    series: str,
    exchange: str,
    isin: str,
    bars: Sequence[dict[str, Any]],
    event_notices: Sequence[dict[str, Any]] | None = None,
    minimum_sessions: int = 21,
    minimum_close_price: float = 10.0,
) -> dict[str, Any]:
    """Evaluate objective stock eligibility and safety gates fail-closed."""
    runtime = _runtime_identity()
    if not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    clean_symbol = symbol.strip().upper()

    failure_reasons: list[str] = []
    failure_reasons.extend(_check_mapping(series, exchange, isin))

    bar_failures, latest_close, avg_volume = _check_bars(
        bars, minimum_sessions, minimum_close_price
    )
    failure_reasons.extend(bar_failures)

    event_failures, event_risk_flag = _check_events(event_notices)
    failure_reasons.extend(event_failures)

    status = "ELIGIBLE" if not failure_reasons else "INELIGIBLE"

    result_payload: dict[str, Any] = {
        "schema": SCHEMA,
        "symbol": clean_symbol,
        "status": status,
        "failure_reasons": failure_reasons,
        "evaluated_sessions_count": len(bars),
        "latest_close_price": latest_close,
        "average_daily_volume": avg_volume,
        "event_risk_flag": event_risk_flag,
        "runtime_code_identity_sha256": runtime,
    }

    provenance_hash = hashlib.sha256(_canonical_bytes(result_payload)).hexdigest()
    result_payload["provenance_sha256"] = provenance_hash
    return result_payload
