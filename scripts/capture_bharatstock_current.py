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
import base64
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.market_data.bharatstock import (
    PRICE_BASIS,
    PROVIDER_SOURCE,
    VOLUME_BASIS,
    BharatStockClient,
    BharatStockError,
    BharatStockInstrument,
)

RETRY_DELAYS = (5.0, 15.0)
MAX_REQUESTS_PER_MEMBER = 8
PER_MEMBER_ATTEMPTS = 1 + len(RETRY_DELAYS)
SESSION_CACHE_DIRECTORY = "bharatstock-session-cache-v1"
SESSION_CACHE_SCHEMA = "bharatstock-session-cache@v1"
_SESSION_FILE = re.compile(r"session=(\d{4}-\d{2}-\d{2})\.json\Z")
_COMPLETE_STATUSES = frozenset({"COMPLETE", "SKIPPED"})


def _universe(path: Path) -> list[tuple[str, str]]:
    payload = json.loads(path.read_text())
    encoded = payload.get("nifty200_source_csv_base64")
    if not isinstance(encoded, str):
        raise ValueError("universe snapshot has no nifty200 CSV")
    rows = list(csv.DictReader(io.StringIO(base64.b64decode(encoded).decode())))
    members: list[tuple[str, str]] = []
    for row in rows:
        isin = (row.get("ISIN Code") or "").strip()
        symbol = (row.get("Symbol") or "").strip()
        if isin and symbol:
            members.append((isin, symbol))
    return members


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


def _cached_session_record(
    path: Path, isin: str, exchange: str, symbol: str, session: date
) -> bool:
    """Mirror the cache reader's exact validity checks without a provider call."""
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    try:
        value: object = json.loads(raw)
    except ValueError:
        return False
    if type(value) is not dict:
        return False
    payload = cast(dict[str, object], value)
    record_sha = payload.pop("record_sha256", None)
    body = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode()
    return (
        type(record_sha) is str
        and record_sha == hashlib.sha256(body).hexdigest()
        and payload.get("schema") == SESSION_CACHE_SCHEMA
        and payload.get("provider") == PROVIDER_SOURCE
        and payload.get("price_basis") == PRICE_BASIS
        and payload.get("volume_basis") == VOLUME_BASIS
        and payload.get("session") == session.isoformat()
        and payload.get("isin") == isin
        and payload.get("exchange") == exchange
        and payload.get("symbol") == symbol
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
        if _cached_session_record(directory / name, isin, exchange, symbol, session):
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
        latest = max((row.session for row in history.rows), default=None)
        record.update(
            {
                "status": "COMPLETE",
                "latest_session": (
                    latest.isoformat()
                    if latest is not None
                    else record["latest_session"]
                ),
                "sessions_written": len(history.rows),
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

    members = _universe(args.universe_snapshot)
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
    pending = [(isin, symbol) for isin, symbol in members if isin not in completed]
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
        "universe_snapshot": str(args.universe_snapshot),
        "universe_snapshot_sha256": hashlib.sha256(
            args.universe_snapshot.read_bytes()
        ).hexdigest(),
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

    requests_used = 0
    sessions_written = 0
    latest_session: date | None = None
    completed_this_run = 0
    skipped_this_run = 0

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
        persist()
        if status == "RATE_LIMITED":
            summary.update(
                {
                    "status": "RATE_LIMITED",
                    "completed": completed_this_run,
                    "skipped": skipped_this_run,
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
    print(json.dumps(summary, sort_keys=True))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
