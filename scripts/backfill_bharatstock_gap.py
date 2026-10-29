#!/usr/bin/env python3
"""Bounded, resumable BharatStock daily-session backfill.

Fetches only a requested date range and writes sessions through the existing
``BharatStockClient.history`` cache path. One symbol at a time; stops on rate
limiting; resumes from a checkpoint.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockError,
    BharatStockInstrument,
)

CACHE_DIR = "bharatstock-session-cache-v1"
CHECKPOINT_VERSION = 1
RETRY_DELAYS = (5.0, 15.0)


def _universe(path: Path) -> list[tuple[str, str]]:
    payload = json.loads(path.read_text())
    encoded = payload.get("nifty200_source_csv_base64")
    if not isinstance(encoded, str):
        raise ValueError("universe snapshot has no nifty200 CSV")
    rows = list(csv.DictReader(io.StringIO(base64.b64decode(encoded).decode())))
    out: list[tuple[str, str]] = []
    for row in rows:
        isin = (row.get("ISIN Code") or "").strip()
        symbol = (row.get("Symbol") or "").strip()
        if isin and symbol:
            out.append((isin, symbol))
    return out


def _sessions(storage_root: Path, start: date, end: date) -> tuple[date, ...]:
    """Union sessions from every retained calendar overlapping the range.

    Calendar records are rolling windows, so no single record necessarily spans
    both boundaries. Session dates themselves are immutable.
    """
    found: set[date] = set()
    for path in (storage_root / "calendar-schedules" / "sha256").glob("*.json"):
        try:
            value = json.loads(path.read_text())
            covered_from = date.fromisoformat(value["covered_from"])
            covered_to = date.fromisoformat(value["covered_to"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if covered_to < start or covered_from > end:
            continue
        for item in value.get("sessions", []):
            if not isinstance(item, dict):
                continue
            raw = item.get("trade_date")
            if not isinstance(raw, str):
                continue
            try:
                session = date.fromisoformat(raw)
            except ValueError:
                continue
            if start <= session <= end:
                found.add(session)
    if not found:
        raise ValueError("no retained calendar covers the requested range")
    return tuple(sorted(found))


def _cache_path(root: Path, isin: str, session: date) -> Path:
    return (
        root
        / CACHE_DIR
        / f"isin={isin}"
        / "exchange=NSE"
        / f"session={session.isoformat()}.json"
    )


def _missing(root: Path, isin: str, sessions: tuple[date, ...]) -> list[date]:
    return [
        session
        for session in sessions
        if not _cache_path(root, isin, session).is_file()
    ]


def _load_checkpoint(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {"version": CHECKPOINT_VERSION, "completed": [], "failed": {}}
    if not isinstance(value, dict):
        return {"version": CHECKPOINT_VERSION, "completed": [], "failed": {}}
    return value


def _save_checkpoint(path: Path, value: dict[str, object]) -> None:
    value["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def _fetch(
    storage_root: Path, instrument: BharatStockInstrument, start: date, end: date
) -> None:
    client = BharatStockClient(session_cache_root=storage_root, max_requests=8)
    client.history(instrument, start, end)


def main(argv: list[str] | None = None) -> int:  # noqa: C901
    parser = argparse.ArgumentParser(prog="backfill-bharatstock-gap")
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--universe-snapshot", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.storage_root.is_absolute() or not args.universe_snapshot.is_absolute():
        sys.stderr.write("absolute storage and universe paths required\n")
        return 2
    if args.start > args.end or args.delay < 0:
        sys.stderr.write("invalid range or delay\n")
        return 2

    sessions = _sessions(args.storage_root, args.start, args.end)
    members = _universe(args.universe_snapshot)
    checkpoint = _load_checkpoint(args.checkpoint)
    completed = set(checkpoint.get("completed") or [])
    failed = dict(checkpoint.get("failed") or {})

    pending: list[tuple[str, str, list[date]]] = []
    for isin, symbol in members:
        missing = _missing(args.storage_root, isin, sessions)
        if missing and isin not in completed:
            pending.append((isin, symbol, missing))
    if args.limit is not None:
        pending = pending[: args.limit]

    summary = {
        "requested_sessions": len(sessions),
        "members": len(members),
        "pending_symbols": len(pending),
        "pending_rows": sum(len(item[2]) for item in pending),
        "dry_run": args.dry_run,
    }
    if args.dry_run:
        summary["symbols"] = [item[1] for item in pending]
        print(json.dumps(summary, sort_keys=True))
        return 0

    done = 0
    for isin, symbol, missing in pending:
        instrument = BharatStockInstrument(isin, "NSE", symbol)
        attempt = 0
        while True:
            try:
                _fetch(args.storage_root, instrument, args.start, args.end)
                break
            except BharatStockError as error:
                if error.category == "RATE_LIMITED":
                    _save_checkpoint(
                        args.checkpoint,
                        {
                            "version": CHECKPOINT_VERSION,
                            "completed": sorted(completed),
                            "failed": failed,
                        },
                    )
                    summary.update({"status": "RATE_LIMITED", "completed": done})
                    print(json.dumps(summary, sort_keys=True))
                    return 3
                if error.category in {
                    "PROVIDER_UNAVAILABLE",
                    "TRANSPORT_FAILED",
                } and attempt < len(RETRY_DELAYS):
                    time.sleep(RETRY_DELAYS[attempt])
                    attempt += 1
                    continue
                failed[isin] = error.category
                break
            except Exception as error:  # noqa: BLE001 - bounded operator script
                failed[isin] = type(error).__name__
                break
        remaining = _missing(args.storage_root, isin, tuple(missing))
        if remaining:
            failed[isin] = "INCOMPLETE_AFTER_FETCH"
        else:
            completed.add(isin)
            failed.pop(isin, None)
            done += 1
        _save_checkpoint(
            args.checkpoint,
            {
                "version": CHECKPOINT_VERSION,
                "completed": sorted(completed),
                "failed": failed,
            },
        )
        time.sleep(args.delay * 1.1)

    summary.update(
        {
            "status": "COMPLETE",
            "completed": done,
            "failed": len(failed),
            "remaining_pending": sum(
                len(_missing(args.storage_root, isin, sessions))
                for isin, _ in members
                if isin not in completed
            ),
        }
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
