#!/usr/bin/env python3
"""Bounded, resumable, incremental raw BharatStock session capture.

Writes the existing ``bharatstock-session-cache-v1`` cache that research reads.
A member whose newest retained session already reaches the requested end is
skipped without a provider request; otherwise only the missing newer range is
fetched. It never reads the exchange calendar, scanner pair state, safety
policy, or research result. A provider failure is reported; it is not converted
into a research fact.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.market_data.bharatstock import (
    _MAX_PAGES,
    PRICE_BASIS,
    PROVIDER_SOURCE,
    VOLUME_BASIS,
    BharatStockClient,
    BharatStockDailyPrice,
    BharatStockError,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.historical_nifty_universe import (
    read_historic_nifty_universe,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)

RETRY_DELAYS = (5.0, 15.0)
MAX_REQUESTS_PER_MEMBER = 8
PER_MEMBER_ATTEMPTS = 1 + len(RETRY_DELAYS)
SESSION_CACHE_DIRECTORY = "bharatstock-session-cache-v1"
SESSION_CACHE_SCHEMA = "bharatstock-session-cache@v1"
_SESSION_FILE = re.compile(r"session=(\d{4}-\d{2}-\d{2})\.json\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_COMPLETE_STATUSES = frozenset({"COMPLETE", "SKIPPED", "NO_NEWER_SESSION"})


GOVERNED_SNAPSHOT = Path("universe_snapshots") / "nifty-universe-v3.json"
MAX_CACHED_REQUEST_COUNT = _MAX_PAGES + 1


def _governed_universe(
    storage_root: Path, snapshot: Path
) -> tuple[list[tuple[str, str]], dict[str, object]]:
    """Admit membership only through the governed official-snapshot reader."""
    if snapshot != storage_root / GOVERNED_SNAPSHOT:
        raise ValueError("universe snapshot is not the governed retained path")
    universe = read_historic_nifty_universe(storage_root)
    try:
        raw = snapshot.read_bytes()
        payload = json.loads(raw)
    except (OSError, ValueError):
        raise ValueError("retained universe snapshot is unreadable") from None
    if type(payload) is not dict or type(payload.get("schema")) is not str:
        raise ValueError("retained universe snapshot schema is invalid")
    try:
        rows = list(
            csv.DictReader(io.StringIO(universe.nifty200_source_csv.decode("utf-8")))
        )
    except (UnicodeDecodeError, csv.Error):
        raise ValueError("governed Nifty 200 CSV is invalid") from None
    members: list[tuple[str, str]] = []
    for row in rows:
        isin = (row.get("ISIN Code") or "").strip()
        symbol = (row.get("Symbol") or "").strip()
        if not isin or not symbol:
            raise ValueError("governed Nifty 200 membership is invalid")
        members.append((isin, symbol))
    if (
        len(members) != 200
        or len({item[0] for item in members}) != 200
        or tuple(universe.nifty200) != tuple(symbol for _isin, symbol in members)
    ):
        raise ValueError("governed Nifty 200 membership is invalid")
    return members, {
        "path": str(snapshot),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "schema": payload["schema"],
        "members": len(members),
        "nifty200_source_sha256": universe.nifty200_source_sha256,
        "window_start": universe.window_start.isoformat(),
        "window_end": universe.window_end.isoformat(),
        "retrieved_at": universe.retrieved_at.isoformat(),
    }


def _load_checkpoint(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {"version": 2, "completed": [], "failed": {}, "symbols": {}}
    if not isinstance(value, dict):
        return {"version": 2, "completed": [], "failed": {}, "symbols": {}}
    return cast(dict[str, object], value)


def _save_checkpoint(path: Path, value: dict[str, object]) -> None:
    value["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def _acquire_lease(storage_root: Path) -> StorageRootLease | None:
    """Hold the storage-root lease so a manual capture is visible to the preflight."""
    try:
        result = StorageRootLease.try_acquire(storage_root)
    except Exception:  # noqa: BLE001 - a root we cannot lease is not writable
        return None
    if result.outcome is not LeaseOutcome.ACQUIRED or result.lease is None:
        return None
    return result.lease


def _script_identity() -> dict[str, object]:
    path = Path(__file__).resolve()
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        digest = None
    return {
        "path": str(path),
        "sha256": digest,
        "python": sys.version.split()[0],
    }


def _session_directory(storage_root: Path, isin: str, exchange: str) -> Path:
    return (
        storage_root / SESSION_CACHE_DIRECTORY / f"isin={isin}" / f"exchange={exchange}"
    )


def _session_path(
    storage_root: Path, isin: str, exchange: str, symbol: str, session: date
) -> Path:
    return (
        _session_directory(storage_root, isin, exchange)
        / f"session={session.isoformat()}.json"
    )


def _cached_session_record(
    storage_root: Path,
    isin: str,
    exchange: str,
    symbol: str,
    session: date,
) -> bool:
    """Mirror the client cache reader, including the row and digest checks.

    Identity and the record digest alone do not make a cache entry usable: the
    client also validates the OHLC/volume row, the response digest tuple, and
    the retrieval instant. A record that fails any of those is treated as
    absent so capture cannot skip a member on unusable data.
    """
    try:
        raw = _session_path(storage_root, isin, exchange, symbol, session).read_bytes()
        value: object = json.loads(raw)
    except (OSError, ValueError):
        return False
    if type(value) is not dict:
        return False
    payload = cast(dict[str, object], value)
    record_sha = payload.pop("record_sha256", None)
    body = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode()
    if (
        type(record_sha) is not str
        or record_sha != hashlib.sha256(body).hexdigest()
        or payload.get("schema") != SESSION_CACHE_SCHEMA
        or payload.get("provider") != PROVIDER_SOURCE
        or payload.get("price_basis") != PRICE_BASIS
        or payload.get("volume_basis") != VOLUME_BASIS
        or payload.get("session") != session.isoformat()
        or payload.get("isin") != isin
        or payload.get("exchange") != exchange
        or payload.get("symbol") != symbol
    ):
        return False
    try:
        BharatStockDailyPrice(
            session,
            Decimal(str(payload["open"])),
            Decimal(str(payload["high"])),
            Decimal(str(payload["low"])),
            Decimal(str(payload["close"])),
            int(cast(int, payload["volume"])),
            (
                Decimal(str(payload["adjusted_close"]))
                if payload.get("adjusted_close") is not None
                else None
            ),
            (
                Decimal(str(payload["adjustment_factor"]))
                if payload.get("adjustment_factor") is not None
                else None
            ),
        )
        raw_digests = cast(list[object], payload["response_sha256s"])
        digests = tuple(cast(list[str], raw_digests))
        request_count = int(cast(int, payload["request_count"]))
        retrieved_at = datetime.fromisoformat(cast(str, payload["retrieved_at"]))
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return False
    return not (
        any(
            type(item) is not str or _DIGEST.fullmatch(item) is None for item in digests
        )
        or request_count != len(digests)
        or not 2 <= request_count <= MAX_CACHED_REQUEST_COUNT
        or retrieved_at.tzinfo is None
        or retrieved_at.utcoffset() != UTC.utcoffset(None)
    )


def _newest_cached_session(
    storage_root: Path, isin: str, exchange: str, symbol: str
) -> date | None:
    """Return the newest readable session, or None when nothing valid is retained."""
    directory = _session_directory(storage_root, isin, exchange)
    try:
        names = sorted(os.listdir(directory), reverse=True)
    except OSError:
        return None
    for name in names:
        match = _SESSION_FILE.match(name)
        if match is None:
            continue
        try:
            session = date.fromisoformat(match.group(1))
        except ValueError:
            continue
        if _cached_session_record(storage_root, isin, exchange, symbol, session):
            return session
    return None


def _capture_member(
    storage_root: Path, isin: str, symbol: str, start: date, end: date
) -> dict[str, object]:
    """Capture one member incrementally; return its typed per-symbol record."""
    record: dict[str, object] = {
        "isin": isin,
        "symbol": symbol,
        "latest_session": None,
        "sessions_written": 0,
        "requests_used": 0,
        "fetch_start": None,
        "error": None,
    }
    newest = _newest_cached_session(storage_root, isin, "NSE", symbol)
    if newest is not None and newest >= end:
        record.update({"status": "SKIPPED", "latest_session": newest.isoformat()})
        return record
    # No retained session means the bounded stage window is fetched; an older
    # session only needs its successor range, never the whole window again.
    fetch_start = start if newest is None else max(newest + timedelta(days=1), start)
    if fetch_start > end:
        record.update({"status": "SKIPPED", "latest_session": newest.isoformat()})
        return record
    record["fetch_start"] = fetch_start.isoformat()
    if newest is not None:
        record["latest_session"] = newest.isoformat()

    instrument = BharatStockInstrument(isin, "NSE", symbol)
    requests_used = 0
    attempt = 0
    while True:
        client = BharatStockClient(
            session_cache_root=storage_root, max_requests=MAX_REQUESTS_PER_MEMBER
        )
        try:
            history = client.history(instrument, fetch_start, end)
        except BharatStockError as error:
            requests_used += client.requests_used
            category = error.category
            if (
                category == "EMPTY_HISTORY"
                and newest is not None
                and fetch_start > start
            ):
                # Only the successor range was requested and the provider has no
                # session there yet (a weekend, holiday, or unpublished close).
                # The retained session stays the latest fact; this is a typed
                # no-newer-session outcome, not a data failure. A full bounded
                # window with no retained session is still a real failure.
                record.update(
                    {
                        "status": "NO_NEWER_SESSION",
                        "latest_session": newest.isoformat(),
                        "requests_used": requests_used,
                        "error": None,
                    }
                )
                return record
            if category in {"PROVIDER_UNAVAILABLE", "TRANSPORT_FAILED"} and (
                attempt < len(RETRY_DELAYS)
            ):
                time.sleep(RETRY_DELAYS[attempt])
                attempt += 1
                continue
            record.update(
                {
                    "status": (
                        "RATE_LIMITED" if category == "RATE_LIMITED" else "FAILED"
                    ),
                    "requests_used": requests_used,
                    "error": category,
                }
            )
            return record
        except Exception as error:  # noqa: BLE001 - bounded operator script
            requests_used += client.requests_used
            record.update(
                {
                    "status": "FAILED",
                    "requests_used": requests_used,
                    "error": type(error).__name__,
                }
            )
            return record
        requests_used += client.requests_used
        expected = tuple(row.session for row in history.rows)
        verified = tuple(
            session
            for session in expected
            if _cached_session_record(storage_root, isin, "NSE", symbol, session)
        )
        latest = max(expected, default=None)
        if len(verified) != len(expected):
            missing = tuple(
                session.isoformat() for session in expected if session not in verified
            )
            record.update(
                {
                    "status": "FAILED",
                    "latest_session": (None if latest is None else latest.isoformat()),
                    "sessions_written": len(verified),
                    "sessions_expected": len(expected),
                    "missing_sessions": list(missing),
                    "requests_used": requests_used,
                    "error": "SESSION_CACHE_WRITE_MISSING",
                }
            )
            return record
        record.update(
            {
                "status": "COMPLETE",
                "latest_session": (
                    latest.isoformat()
                    if latest is not None
                    else record["latest_session"]
                ),
                "sessions_written": len(verified),
                "sessions_expected": len(expected),
                "requests_used": requests_used,
            }
        )
        return record


def main(argv: list[str] | None = None) -> int:  # noqa: C901 - stage boundaries
    parser = argparse.ArgumentParser(prog="capture-bharatstock-current")
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--universe-snapshot", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not args.storage_root.is_absolute() or not args.universe_snapshot.is_absolute():
        sys.stderr.write("absolute storage and universe paths required\n")
        return 2
    if args.start > args.end or args.delay < 0:
        sys.stderr.write("invalid range or delay\n")
        return 2
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)

    try:
        members, universe_identity = _governed_universe(
            args.storage_root, args.universe_snapshot
        )
    except ValueError as error:
        sys.stderr.write(f"capture_invalid: {error}\n")
        return 2
    end_stamp = args.end.isoformat()
    checkpoint = _load_checkpoint(args.checkpoint)
    # A checkpoint for a different requested end cannot vouch for this run: the
    # cache check below is cheap and exact, so re-evaluate every member.
    resuming = checkpoint.get("end") == end_stamp
    completed: set[str] = (
        set(cast(list[str], checkpoint.get("completed") or [])) if resuming else set()
    )
    failed: dict[str, object] = (
        dict(cast(dict[str, object], checkpoint.get("failed") or {}))
        if resuming
        else {}
    )
    statuses: dict[str, dict[str, object]] = (
        {
            symbol: dict(cast(dict[str, object], value))
            for symbol, value in cast(
                dict[str, object], checkpoint.get("symbols") or {}
            ).items()
            if type(value) is dict
        }
        if resuming
        else {}
    )
    # Every member is re-checked against its retained cache each run; the
    # checkpoint only orders still-missing members first and bounds --limit.
    # This keeps per-symbol status truthful even if a cached file was removed.
    pending: list[tuple[str, str]] = [
        (isin, symbol) for isin, symbol in members if isin not in completed
    ] + [(isin, symbol) for isin, symbol in members if isin in completed]
    if args.limit is not None:
        pending = pending[: args.limit]

    summary: dict[str, object] = {
        "schema": "raw-session-capture@v1",
        "status": "DRY_RUN" if args.dry_run else "IN_PROGRESS",
        "stamp": end_stamp,
        "members": len(members),
        "pending_symbols": len(pending),
        "completed": 0,
        "skipped": 0,
        "failed": len(failed),
        "failed_isins": sorted(failed),
        "requests_used": 0,
        "requests_configured_max": (
            MAX_REQUESTS_PER_MEMBER * PER_MEMBER_ATTEMPTS * len(pending)
        ),
        "requests_configured_max_basis": (
            "MAX_REQUESTS_PER_MEMBER * PER_MEMBER_ATTEMPTS * symbols_considered"
        ),
        "max_requests_per_member": MAX_REQUESTS_PER_MEMBER,
        "sessions_written": 0,
        "latest_session": None,
        "start": args.start.isoformat(),
        "end": end_stamp,
        "checkpoint": str(args.checkpoint),
        "universe": universe_identity,
        "universe_snapshot": str(args.universe_snapshot),
        "universe_snapshot_sha256": universe_identity["sha256"],
        "runtime": _script_identity(),
        "started_at": started_at,
        "symbols": {},
    }
    if args.dry_run:
        summary["symbols"] = {
            symbol: {"isin": isin, "symbol": symbol, "status": "PENDING"}
            for isin, symbol in pending
        }
        summary["pending_symbols"] = len(pending)
        summary["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        print(json.dumps(summary, sort_keys=True))
        return 0

    lease = _acquire_lease(args.storage_root)
    if lease is None:
        summary.update(
            {
                "status": "STORAGE_ROOT_BUSY",
                "error": "STORAGE_ROOT_BUSY",
                "completed": 0,
                "skipped": 0,
                "requests_used": 0,
                "sessions_written": 0,
                "symbols": {},
                "remaining_pending": len(members),
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
        print(json.dumps(summary, sort_keys=True))
        return 4

    requests_used = 0
    sessions_written = 0
    latest_session: date | None = None
    completed_this_run = 0
    skipped_this_run = 0
    no_newer_this_run = 0

    def persist() -> None:
        _save_checkpoint(
            args.checkpoint,
            {
                "version": 2,
                "end": end_stamp,
                "start": args.start.isoformat(),
                "completed": sorted(completed),
                "failed": failed,
                "symbols": statuses,
                "requests_used": requests_used,
            },
        )

    for isin, symbol in pending:
        record = _capture_member(args.storage_root, isin, symbol, args.start, args.end)
        statuses[symbol] = record
        requests_used += cast(int, record["requests_used"])
        sessions_written += cast(int, record["sessions_written"])
        latest_raw = record.get("latest_session")
        if isinstance(latest_raw, str):
            observed = date.fromisoformat(latest_raw)
            if latest_session is None or observed > latest_session:
                latest_session = observed
        status = record["status"]
        if status in _COMPLETE_STATUSES:
            completed.add(isin)
            failed.pop(isin, None)
        else:
            failed[isin] = record.get("error") or status
        if status == "COMPLETE":
            completed_this_run += 1
        elif status == "SKIPPED":
            skipped_this_run += 1
        elif status == "NO_NEWER_SESSION":
            no_newer_this_run += 1
        persist()
        if status == "RATE_LIMITED":
            summary.update(
                {
                    "status": "RATE_LIMITED",
                    "completed": completed_this_run,
                    "skipped": skipped_this_run,
                    "no_newer_session": no_newer_this_run,
                    "failed": len(failed),
                    "failed_isins": sorted(failed),
                    "requests_used": requests_used,
                    "sessions_written": sessions_written,
                    "latest_session": (
                        None if latest_session is None else latest_session.isoformat()
                    ),
                    "symbols": statuses,
                    "remaining_pending": sum(
                        1 for isin, _symbol in members if isin not in completed
                    ),
                    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
            lease.close()
            print(json.dumps(summary, sort_keys=True))
            return 3
        time.sleep(args.delay * 1.1)

    remaining_pending = sum(1 for isin, _symbol in members if isin not in completed)
    complete = remaining_pending == 0 and not failed
    summary.update(
        {
            "status": "COMPLETE" if complete else "INCOMPLETE",
            "completed": completed_this_run,
            "skipped": skipped_this_run,
            "no_newer_session": no_newer_this_run,
            "failed": len(failed),
            "failed_isins": sorted(failed),
            "requests_used": requests_used,
            "sessions_written": sessions_written,
            "latest_session": (
                None if latest_session is None else latest_session.isoformat()
            ),
            "symbols": statuses,
            "remaining_pending": remaining_pending,
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )
    lease.close()
    print(json.dumps(summary, sort_keys=True))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
