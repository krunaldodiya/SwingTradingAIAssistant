#!/usr/bin/env python3
"""Bounded, resumable raw BharatStock session capture.

Writes the existing ``bharatstock-session-cache-v1`` cache that research reads.
It never reads the exchange calendar, scanner pair state, safety policy, or
research result. A provider failure is reported; it is not converted into a
research fact.
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
from typing import cast

from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockError,
    BharatStockInstrument,
)

RETRY_DELAYS = (5.0, 15.0)


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
        return {"version": 1, "completed": [], "failed": {}}
    if not isinstance(value, dict):
        return {"version": 1, "completed": [], "failed": {}}
    return cast(dict[str, object], value)


def _save_checkpoint(path: Path, value: dict[str, object]) -> None:
    value["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def _fetch(
    storage_root: Path,
    isin: str,
    symbol: str,
    start: date,
    end: date,
) -> tuple[int, int, date | None]:
    client = BharatStockClient(session_cache_root=storage_root, max_requests=8)
    history = client.history(BharatStockInstrument(isin, "NSE", symbol), start, end)
    latest = max((row.session for row in history.rows), default=None)
    return len(history.rows), client.requests_used, latest


def main(argv: list[str] | None = None) -> int:  # noqa: C901
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

    if not args.storage_root.is_absolute() or not args.universe_snapshot.is_absolute():
        sys.stderr.write("absolute storage and universe paths required\n")
        return 2
    if args.start > args.end or args.delay < 0:
        sys.stderr.write("invalid range or delay\n")
        return 2
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)

    members = _universe(args.universe_snapshot)
    checkpoint = _load_checkpoint(args.checkpoint)
    completed: set[str] = set(cast(list[str], checkpoint.get("completed") or []))
    failed: dict[str, object] = dict(
        cast(dict[str, object], checkpoint.get("failed") or {})
    )
    pending = [(isin, symbol) for isin, symbol in members if isin not in completed]
    if args.limit is not None:
        pending = pending[: args.limit]

    summary: dict[str, object] = {
        "status": "DRY_RUN" if args.dry_run else "IN_PROGRESS",
        "members": len(members),
        "pending_symbols": len(pending),
        "completed": 0,
        "failed": 0,
        "requests_used": 0,
        "sessions_written": 0,
        "latest_session": None,
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
        "checkpoint": str(args.checkpoint),
    }
    if args.dry_run:
        summary["symbols"] = [symbol for _isin, symbol in pending]
        print(json.dumps(summary, sort_keys=True))
        return 0

    done = 0
    total_requests = 0
    total_rows = 0
    latest_session: date | None = None

    for isin, symbol in pending:
        attempt = 0
        while True:
            try:
                rows, requests, latest = _fetch(
                    args.storage_root, isin, symbol, args.start, args.end
                )
                total_requests += requests
                total_rows += rows
                if latest is not None and (
                    latest_session is None or latest > latest_session
                ):
                    latest_session = latest
                break
            except BharatStockError as error:
                if error.category == "RATE_LIMITED":
                    _save_checkpoint(
                        args.checkpoint,
                        {
                            "version": 1,
                            "completed": sorted(completed),
                            "failed": failed,
                        },
                    )
                    summary.update(
                        {
                            "status": "RATE_LIMITED",
                            "completed": done,
                            "failed": len(failed),
                            "requests_used": total_requests,
                            "sessions_written": total_rows,
                            "latest_session": (
                                None
                                if latest_session is None
                                else latest_session.isoformat()
                            ),
                        }
                    )
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

        if isin in failed:
            continue
        completed.add(isin)
        failed.pop(isin, None)
        done += 1
        _save_checkpoint(
            args.checkpoint,
            {
                "version": 1,
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
            "requests_used": total_requests,
            "sessions_written": total_rows,
            "latest_session": (
                None if latest_session is None else latest_session.isoformat()
            ),
            "remaining_pending": sum(
                1 for isin, _symbol in members if isin not in completed
            ),
        }
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
