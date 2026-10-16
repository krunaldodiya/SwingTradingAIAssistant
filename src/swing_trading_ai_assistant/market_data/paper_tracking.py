"""Paper observation tracking registry and forward candidate monitoring."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final, cast

import pyarrow.parquet as _pyarrow_parquet  # pyright: ignore[reportMissingImports]

from .paper_tracking_runtime_identity_manifest import (
    PAPER_TRACKING_RUNTIME_SOURCE_SHA256_V1,
)
from .runtime_source_verifier import runtime_source_sha256

RECORD_SCHEMA: Final = "paper-trade-record@v1"
REPORT_SCHEMA: Final = "paper-tracking-report@v1"
_PARQUET: Any = cast(Any, _pyarrow_parquet)
_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/paper_tracking.py",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _runtime_identity() -> str:
    manifest_sources = tuple(str(k) for k in PAPER_TRACKING_RUNTIME_SOURCE_SHA256_V1)
    if manifest_sources != _SOURCES:
        raise ValueError("paper tracking runtime inventory invalid")
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in PAPER_TRACKING_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, str(relative))
        if actual != expected:
            raise ValueError("paper tracking runtime identity invalid")
        observed[str(relative)] = actual
    return _digest(observed)


def log_candidates_from_scan(
    storage_root: Path,
    scan_result: dict[str, object],
) -> list[dict[str, object]]:
    """Register newly identified candidates into the paper-observations-v1 registry."""
    if not storage_root.is_absolute():
        raise ValueError("invalid storage root")

    registry_dir = storage_root / "paper-observations-v1"
    registry_dir.mkdir(mode=0o700, exist_ok=True)

    candidates = cast(list[dict[str, object]], scan_result.get("candidates", []))
    logged: list[dict[str, object]] = []

    for c in candidates:
        if c.get("decision") != "RESEARCH_CANDIDATE":
            continue
        summary = cast(dict[str, object], c.get("candidate_summary", {}))
        symbol = str(c.get("symbol", ""))
        isin = str(c.get("isin", ""))
        exchange = str(c.get("exchange", "NSE"))
        entry_session = str(summary.get("event_session", ""))
        price_str = str(summary.get("current_price_inr", "0"))
        stop_str = str(summary.get("supporting_stop_reference_inr", "0"))

        entry_price = Decimal(price_str)
        stop_price = Decimal(stop_str)
        risk = entry_price - stop_price
        if risk <= 0:
            continue

        trade_seed = f"{symbol}:{entry_session}:{_decimal_text(entry_price)}:{_decimal_text(stop_price)}"
        trade_id = hashlib.sha256(trade_seed.encode("utf-8")).hexdigest()
        trade_file = registry_dir / f"{trade_id}.json"

        if trade_file.exists():
            try:
                existing = cast(dict[str, object], json.loads(trade_file.read_text()))
                logged.append(existing)
                continue
            except (OSError, ValueError):
                pass

        target_1r = entry_price + risk
        target_2r = entry_price + (risk * Decimal("2"))
        target_3r = entry_price + (risk * Decimal("3"))

        record: dict[str, object] = {
            "schema": RECORD_SCHEMA,
            "trade_id": trade_id,
            "symbol": symbol,
            "isin": isin,
            "exchange": exchange,
            "entry_session": entry_session,
            "entry_price_inr": _decimal_text(entry_price),
            "stop_reference_inr": _decimal_text(stop_price),
            "risk_per_share_inr": _decimal_text(risk),
            "target_1r_inr": _decimal_text(target_1r),
            "target_2r_inr": _decimal_text(target_2r),
            "target_3r_inr": _decimal_text(target_3r),
            "status": "ACTIVE",
            "exit_session": None,
            "exit_price_inr": None,
            "return_multiple_r": None,
            "max_r_reached": "0.0",
            "sessions_held": 0,
        }
        record["record_identity_sha256"] = _digest(record)
        trade_file.write_bytes(_canonical_bytes(record))
        logged.append(record)

    return logged


def _load_historical_bars_for_symbol(
    storage_root: Path, symbol: str
) -> dict[date, dict[str, Any]]:
    bars: dict[date, dict[str, Any]] = {}
    adjusted_dir = storage_root / "adjusted_daily" / "provider=bharatstock"
    if not adjusted_dir.exists():
        return bars

    for pq_file in adjusted_dir.rglob("*.parquet"):
        try:
            table: Any = _PARQUET.read_table(pq_file)
            symbols_col = table["symbol"].to_pylist()
            if symbol not in symbols_col:
                continue
            sessions = table["session"].to_pylist()
            highs = table["high"].to_pylist()
            lows = table["low"].to_pylist()
            closes = table["close"].to_pylist()
            for s, bar_high, bar_low, bar_close in zip(
                sessions, highs, lows, closes, strict=False
            ):
                if isinstance(s, date):
                    bars[s] = {
                        "high": Decimal(str(bar_high)),
                        "low": Decimal(str(bar_low)),
                        "close": Decimal(str(bar_close)),
                    }
        except (OSError, ValueError):
            continue
    return bars


def _evaluate_forward_trade(
    record: dict[str, object],
    bars: dict[date, dict[str, Any]],
) -> dict[str, object]:
    entry_session = date.fromisoformat(str(record.get("entry_session", "")))
    entry_price = Decimal(str(record.get("entry_price_inr", "0")))
    stop_price = Decimal(str(record.get("stop_reference_inr", "0")))
    risk = Decimal(str(record.get("risk_per_share_inr", "0")))
    target_2r = Decimal(str(record.get("target_2r_inr", "0")))

    forward_sessions = sorted([s for s in bars if s > entry_session])
    max_r = Decimal("0.0")
    sessions_held = len(forward_sessions)
    status = "ACTIVE"
    exit_session = None
    exit_price = None
    return_r = None

    for s in forward_sessions:
        b = bars[s]
        high: Decimal = b["high"]
        close: Decimal = b["close"]

        r_reached = (high - entry_price) / risk if risk > 0 else Decimal("0")
        if r_reached > max_r:
            max_r = r_reached

        if close < stop_price:
            status = "INVALIDATED"
            exit_session = s.isoformat()
            exit_price = close
            return_r = (close - entry_price) / risk if risk > 0 else Decimal("-1.0")
            break

        if high >= target_2r:
            status = "TARGET_REACHED"
            exit_session = s.isoformat()
            exit_price = target_2r
            return_r = Decimal("2.0")
            break

    if status == "ACTIVE" and sessions_held >= 10:
        status = "WINDOW_EXPIRED"
        last_s = forward_sessions[-1]
        last_close: Decimal = bars[last_s]["close"]
        exit_session = last_s.isoformat()
        exit_price = last_close
        return_r = (last_close - entry_price) / risk if risk > 0 else Decimal("0")

    updated = dict(record)
    updated.update(
        {
            "status": status,
            "sessions_held": sessions_held,
            "max_r_reached": f"{max_r:+.2f}R",
            "exit_session": exit_session,
            "exit_price_inr": _decimal_text(exit_price)
            if exit_price is not None
            else None,
            "return_multiple_r": f"{return_r:+.2f}R" if return_r is not None else None,
        }
    )
    updated["record_identity_sha256"] = _digest(updated)
    return updated


def update_paper_trades(storage_root: Path) -> list[dict[str, object]]:
    """Evaluate and update forward lifecycle status for all tracked paper trades."""
    registry_dir = storage_root / "paper-observations-v1"
    if not registry_dir.exists():
        return []

    updated_records: list[dict[str, object]] = []

    for trade_file in sorted(registry_dir.glob("*.json")):
        if len(trade_file.stem) != 64:
            continue
        try:
            record: dict[str, object] = cast(
                dict[str, object], json.loads(trade_file.read_text())
            )
        except (OSError, ValueError):
            continue

        if record.get("status") != "ACTIVE":
            updated_records.append(record)
            continue

        symbol = str(record.get("symbol", ""))
        bars = _load_historical_bars_for_symbol(storage_root, symbol)
        updated = _evaluate_forward_trade(record, bars)

        trade_file.write_bytes(_canonical_bytes(updated))
        updated_records.append(updated)

    return updated_records


def generate_tracking_report(
    storage_root: Path, clock: Callable[[], datetime] | None = None
) -> dict[str, object]:
    """Generate aggregate performance report across all paper-tracked trades."""
    now = datetime.now(UTC) if clock is None else clock()
    trades = update_paper_trades(storage_root)

    total = len(trades)
    active = sum(1 for t in trades if t.get("status") == "ACTIVE")
    invalidated = sum(1 for t in trades if t.get("status") == "INVALIDATED")
    target_reached = sum(1 for t in trades if t.get("status") == "TARGET_REACHED")
    expired = sum(1 for t in trades if t.get("status") == "WINDOW_EXPIRED")

    resolved_trades = [
        t
        for t in trades
        if t.get("status") in {"INVALIDATED", "TARGET_REACHED", "WINDOW_EXPIRED"}
    ]
    wins = 0
    total_r = Decimal("0.0")

    for t in resolved_trades:
        ret_str = str(t.get("return_multiple_r", "")).rstrip("R")
        if ret_str:
            try:
                r_val = Decimal(ret_str)
                total_r += r_val
                if r_val > Decimal("0"):
                    wins += 1
            except InvalidOperation:
                pass

    win_rate = (
        f"{(wins / len(resolved_trades) * 100):.1f}%" if resolved_trades else None
    )
    avg_r = (
        f"{(total_r / Decimal(len(resolved_trades))):+.2f}R"
        if resolved_trades
        else None
    )

    report: dict[str, object] = {
        "schema": REPORT_SCHEMA,
        "report_timestamp": _instant(now),
        "storage_root_sha256": _digest(str(storage_root)),
        "total_tracked_trades": total,
        "active_trades_count": active,
        "invalidated_count": invalidated,
        "target_reached_count": target_reached,
        "expired_count": expired,
        "win_rate_percent": win_rate,
        "average_r_return": avg_r,
        "trades": trades,
        "runtime_code_identity_sha256": _runtime_identity(),
    }
    report["result_identity_sha256"] = _digest(report)
    return report


def format_tracking_table(report: dict[str, object]) -> str:
    """Format terminal ASCII tracking portfolio table."""
    total = report.get("total_tracked_trades", 0)
    active = report.get("active_trades_count", 0)
    target_reached = report.get("target_reached_count", 0)
    invalidated = report.get("invalidated_count", 0)
    expired = report.get("expired_count", 0)
    win_rate = report.get("win_rate_percent") or "N/A"
    avg_r = report.get("average_r_return") or "N/A"
    ts = str(report.get("report_timestamp", ""))

    lines: list[str] = [
        "=" * 88,
        f"FORWARD PAPER OBSERVATION TRACKER (G11) — {ts}",
        "=" * 88,
        f"Total: {total} | Active: {active} | Targets Reached: {target_reached} | Invalidated: {invalidated} | Expired: {expired}",
        f"Win Rate: {win_rate} | Average Return: {avg_r}",
        "-" * 88,
    ]

    trades = cast(list[dict[str, object]], report.get("trades", []))
    if not trades:
        lines.append("No paper trades currently registered in paper-observations-v1.")
        lines.append("-" * 88)
        return "\n".join(lines)

    lines.append(
        f"{'SYMBOL':<10} {'STATUS':<14} {'ENTRY DATE':<12} {'ENTRY':<10} {'STOP':<10} {'2R TARGET':<11} {'MAX R':<8} {'RETURN':<8} {'HELD':<6}"
    )
    lines.append("-" * 88)

    for t in trades:
        sym = str(t.get("symbol", ""))
        st = str(t.get("status", ""))
        entry_d = str(t.get("entry_session", ""))
        entry_p = f"INR {t.get('entry_price_inr', '')}"
        stop_p = f"INR {t.get('stop_reference_inr', '')}"
        tgt_2r = f"INR {t.get('target_2r_inr', '')}"
        max_r = str(t.get("max_r_reached", "0.0R"))
        ret_r = str(t.get("return_multiple_r") or "—")
        held = f"{t.get('sessions_held', 0)}d"

        lines.append(
            f"{sym:<10} {st:<14} {entry_d:<12} {entry_p:<10} {stop_p:<10} {tgt_2r:<11} {max_r:<8} {ret_r:<8} {held:<6}"
        )
    lines.append("-" * 88)

    return "\n".join(lines)
