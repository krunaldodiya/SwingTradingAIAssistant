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


def _trade_id(isin: str, exchange: str, entry_session: str) -> str:
    """Return the stable identity for one canonical instrument setup."""
    seed = f"{isin}:{exchange}:{entry_session}"
    return hashlib.sha256(seed.encode()).hexdigest()


def _retained_event_close(
    storage_root: Path,
    isin: str,
    exchange: str,
    entry_session: str,
) -> tuple[Decimal, int, int] | None:
    """Return the integrity-checked event close and its cache diagnostics."""
    try:
        entry_day = date.fromisoformat(entry_session)
    except ValueError:
        return None
    bars, unreadable = _load_retained_bars(storage_root, isin, exchange)
    bars, implausible = _drop_implausible_moves(bars)
    entry_price = bars.get(entry_day, {}).get("close")
    if entry_price is None:
        return None
    return entry_price, unreadable, implausible


def _existing_record(path: Path) -> dict[str, object] | None:
    """Return a readable record when a canonical setup already exists."""
    try:
        return cast(dict[str, object], json.loads(path.read_text()))
    except (OSError, ValueError):
        return None


def log_candidates_from_scan(
    storage_root: Path,
    scan_result: dict[str, object],
) -> list[dict[str, object]]:
    """Register newly identified candidates into the paper-observations-v1 registry."""
    if not storage_root.is_absolute():
        raise ValueError("invalid storage root")

    registry_dir = storage_root / "paper-observations-v1"
    registry_dir.mkdir(mode=0o700, exist_ok=True)

    # A retained page is stored as an envelope holding the scan; accept either
    # shape so "--log-scan page.json" cannot silently log nothing.
    inner = scan_result.get("scan")
    if isinstance(inner, dict):
        scan_result = cast(dict[str, object], inner)
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
        stop_str = str(summary.get("supporting_stop_reference_inr", "0"))
        if not symbol or not isin or not exchange:
            continue
        # The entry is the close of the session the setup was detected in, never
        # the price on the day it was noticed: a candidate is republished for up
        # to five sessions, and using the later price measures a trade nobody
        # could have taken.
        try:
            stop_price = Decimal(stop_str)
        except InvalidOperation:
            continue
        event_close = _retained_event_close(storage_root, isin, exchange, entry_session)
        if event_close is None:
            # Without a valid event-session close there is no honest entry price.
            continue
        entry_price, unreadable, implausible = event_close

        risk = entry_price - stop_price
        if risk <= 0:
            continue

        # Identity is the canonical instrument setup, not the day it was observed,
        # so re-running a pass cannot register the same candidate twice.
        trade_id = _trade_id(isin, exchange, entry_session)
        trade_file = registry_dir / f"{trade_id}.json"

        existing = _existing_record(trade_file)
        if existing is not None:
            logged.append(existing)
            continue

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
            "data_quality": {
                "unreadable_records": unreadable,
                "implausible_bars": implausible,
            },
        }
        record["record_identity_sha256"] = _digest(record)
        trade_file.write_bytes(_canonical_bytes(record))
        logged.append(record)
    return logged


_MAX_SESSION_MOVE: Final = Decimal("0.25")
_HORIZON_SESSIONS: Final = 10


def _load_retained_bars(
    storage_root: Path, isin: str, exchange: str
) -> tuple[dict[date, dict[str, Any]], int]:
    """Read the bars the scan itself retained for this instrument.

    ``adjusted_daily`` is maintained by a separate pipeline and can lag the
    sessions being tracked, so forward evaluation must not depend on it. The
    retained per-session cache always ends at a session the scan observed.
    Returns the bars and the number of unreadable records rejected.
    """
    base = (
        storage_root
        / "bharatstock-session-cache-v1"
        / f"isin={isin}"
        / f"exchange={exchange}"
    )
    bars: dict[date, dict[str, Any]] = {}
    rejected = 0
    if not isin or not base.is_dir():
        return bars, rejected
    for path in sorted(base.glob("session=*.json")):
        try:
            payload: object = json.loads(path.read_text())
        except (OSError, ValueError):
            rejected += 1
            continue
        row = cast(dict[str, object], payload) if isinstance(payload, dict) else {}
        try:
            session = date.fromisoformat(str(row["session"]))
            high = Decimal(str(row["high"]))
            low = Decimal(str(row["low"]))
            close = Decimal(str(row["close"]))
        except (KeyError, ArithmeticError, ValueError):
            rejected += 1
            continue
        if not all(value.is_finite() for value in (high, low, close)):
            rejected += 1
            continue
        if low <= 0 or close <= 0 or high < low or close > high or close < low:
            rejected += 1
            continue
        bars[session] = {"high": high, "low": low, "close": close}
    return bars, rejected


def _drop_implausible_moves(
    bars: dict[date, dict[str, Any]],
) -> tuple[dict[date, dict[str, Any]], int]:
    """Discard bars whose session range is impossible for an NSE instrument.

    Indian circuit limits cap a session's move well below 25%. A bar outside that
    band is an adjusted/unadjusted splice or a mis-joined row, and reading it as
    price action produces absurd multiples (the failure this guard exists for).
    """
    kept: dict[date, dict[str, Any]] = {}
    dropped = 0
    previous_close: Decimal | None = None
    for session in sorted(bars):
        bar = bars[session]
        if previous_close is not None:
            upper = previous_close * (Decimal("1") + _MAX_SESSION_MOVE)
            lower = previous_close * (Decimal("1") - _MAX_SESSION_MOVE)
            if (
                bar["high"] > upper
                or bar["low"] < lower
                or bar["close"] > upper
                or bar["close"] < lower
            ):
                dropped += 1
                continue
        kept[session] = bar
        previous_close = bar["close"]
    return kept, dropped


def _evaluate_forward_trade(
    record: dict[str, object],
    bars: dict[date, dict[str, Any]],
) -> dict[str, object]:
    entry_session = date.fromisoformat(str(record.get("entry_session", "")))
    entry_price = Decimal(str(record.get("entry_price_inr", "0")))
    stop_price = Decimal(str(record.get("stop_reference_inr", "0")))
    risk = Decimal(str(record.get("risk_per_share_inr", "0")))
    target_2r = Decimal(str(record.get("target_2r_inr", "0")))

    forward_sessions = sorted([s for s in bars if s > entry_session])[
        :_HORIZON_SESSIONS
    ]
    max_r = Decimal("0.0")
    sessions_held = 0
    status = "ACTIVE"
    exit_session = None
    exit_price = None
    return_r = None

    for held, s in enumerate(forward_sessions, 1):
        b = bars[s]
        high: Decimal = b["high"]
        close: Decimal = b["close"]
        sessions_held = held

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

    if status == "ACTIVE" and len(forward_sessions) >= _HORIZON_SESSIONS:
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

        isin = str(record.get("isin") or "")
        exchange = str(record.get("exchange") or "NSE")
        bars, unreadable = _load_retained_bars(storage_root, isin, exchange)
        bars, implausible = _drop_implausible_moves(bars)
        # Recorded before evaluation so the identity digest covers it.
        record["data_quality"] = {
            "unreadable_records": unreadable,
            "implausible_bars": implausible,
        }
        updated = _evaluate_forward_trade(record, bars)

        trade_file.write_bytes(_canonical_bytes(updated))
        updated_records.append(updated)

    return updated_records


def _canonical_record(
    *,
    symbol: str,
    entry_session: str,
    entry_price: Decimal,
    stop_price: Decimal,
    isin: str,
    exchange: str,
    data_quality: dict[str, int],
) -> dict[str, object]:
    """Build one registry record from a setup and its event-session close."""
    risk = entry_price - stop_price
    return {
        "schema": RECORD_SCHEMA,
        "trade_id": _trade_id(isin, exchange, entry_session),
        "symbol": symbol,
        "isin": isin,
        "exchange": exchange,
        "entry_session": entry_session,
        "entry_price_inr": _decimal_text(entry_price),
        "stop_reference_inr": _decimal_text(stop_price),
        "risk_per_share_inr": _decimal_text(risk),
        "target_1r_inr": _decimal_text(entry_price + risk),
        "target_2r_inr": _decimal_text(entry_price + (risk * Decimal("2"))),
        "target_3r_inr": _decimal_text(entry_price + (risk * Decimal("3"))),
        "status": "ACTIVE",
        "exit_session": None,
        "exit_price_inr": None,
        "return_multiple_r": None,
        "max_r_reached": "0.0",
        "sessions_held": 0,
        "data_quality": data_quality,
    }


def _repair_group(
    storage_root: Path,
    registry_dir: Path,
    group: list[tuple[Path, dict[str, object]]],
    *,
    dry_run: bool,
) -> tuple[str, int]:
    """Return the outcome for one canonical-instrument setup and removals."""
    diagnostics = group[0][1]
    symbol = str(diagnostics.get("symbol", ""))
    isin = str(diagnostics.get("isin") or "")
    exchange = str(diagnostics.get("exchange") or "")
    entry_session = str(diagnostics.get("entry_session", ""))
    if not symbol or not isin or not exchange:
        return "unrepairable", 0
    if any(str(other.get("symbol", "")) != symbol for _path, other in group[1:]):
        return "identity_conflict", 0
    try:
        entry_day = date.fromisoformat(entry_session)
        stop_prices = {
            Decimal(str(record.get("stop_reference_inr", "0")))
            for _path, record in group
        }
    except (InvalidOperation, ValueError):
        return "unrepairable", 0
    if len(stop_prices) != 1:
        return "stop_conflict", 0
    stop_price = stop_prices.pop()
    bars, unreadable = _load_retained_bars(storage_root, isin, exchange)
    bars, implausible = _drop_implausible_moves(bars)
    entry_price = bars.get(entry_day, {}).get("close")
    if entry_price is None or stop_price <= 0 or entry_price <= stop_price:
        return "unrepairable", 0

    record = _evaluate_forward_trade(
        _canonical_record(
            symbol=symbol,
            entry_session=entry_session,
            entry_price=entry_price,
            stop_price=stop_price,
            isin=isin,
            exchange=exchange,
            data_quality={
                "unreadable_records": unreadable,
                "implausible_bars": implausible,
            },
        ),
        bars,
    )
    # One record survives per setup; the rest are duplicates regardless of whether
    # their legacy filename happens to match the canonical one.
    removed = max(0, len(group) - 1)
    if not dry_run:
        target = registry_dir / f"{record['trade_id']}.json"
        target.write_bytes(_canonical_bytes(record))
        for path, _record in group:
            if path != target:
                path.unlink(missing_ok=True)
    return "repaired", removed


def repair_registry(  # noqa: C901 - one pass over the whole registry
    storage_root: Path, *, dry_run: bool = False
) -> dict[str, object]:
    """Rewrite the registry as one canonical record per setup.

    Records written before the entry price came from the event-session close carry
    a price-derived identity, so the same setup was registered again on every pass.
    This groups by ``(isin, exchange, entry_session)``, re-prices from retained
    bars, keeps the canonical record and removes the duplicates.

    A setup whose canonical identity, session close or stop is invalid is left
    untouched and reported. A conflicting symbol or stop is also left untouched;
    selecting one would destroy measurement history. Inventing an entry price
    would be worse than an admitted gap.
    """
    registry_dir = storage_root / "paper-observations-v1"
    counters = {
        "records_read": 0,
        "repaired": 0,
        "duplicates_removed": 0,
        "unrepairable": 0,
        "identity_conflicts": 0,
        "stop_conflicts": 0,
    }
    if not registry_dir.is_dir():
        return {"schema": "paper-registry-repair@v1", "dry_run": dry_run, **counters}

    grouped: dict[tuple[str, str, str], list[tuple[Path, dict[str, object]]]] = {}
    for trade_file in sorted(registry_dir.glob("*.json")):
        if len(trade_file.stem) != 64:
            continue
        try:
            record = cast(dict[str, object], json.loads(trade_file.read_text()))
        except (OSError, ValueError):
            continue
        counters["records_read"] += 1
        symbol = str(record.get("symbol", ""))
        identity = (
            str(record.get("isin") or ""),
            str(record.get("exchange") or ""),
            str(record.get("entry_session", "")),
        )
        # Broken identities must remain individual records: grouping them could
        # discard unrelated history without a canonical basis for comparison.
        key = identity if symbol and all(identity) else (trade_file.name, "", "")
        grouped.setdefault(key, []).append((trade_file, record))

    for group in grouped.values():
        outcome, removed = _repair_group(
            storage_root, registry_dir, group, dry_run=dry_run
        )
        counters["duplicates_removed"] += removed
        if outcome != "repaired":
            counters["unrepairable"] += 1
            if outcome == "identity_conflict":
                counters["identity_conflicts"] += 1
            if outcome == "stop_conflict":
                counters["stop_conflicts"] += 1
        else:
            counters["repaired"] += 1

    return {
        "schema": "paper-registry-repair@v1",
        "dry_run": dry_run,
        "setups": len(grouped),
        **counters,
    }


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
