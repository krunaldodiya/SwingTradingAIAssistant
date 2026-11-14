#!/usr/bin/env python3
"""Per-cohort adjusted-daily coverage planning for the capture preflight.

The adjusted store is keyed by exact request identity, so one global "newest
retained session" cannot tell whether every member is current. This module
reads the retained store per instrument, splits the governed Nifty 200
membership into fixed 100-member cohorts, and reports for each cohort whether
it is fully current, which members are missing, and the bounded newer range
that starts after its oldest missing instrument.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Final, cast

import pyarrow.parquet as pq  # pyright: ignore[reportMissingImports]

from swing_trading_ai_assistant.market_data.historical_nifty_universe import (
    read_historic_nifty_universe,
)

COHORT_SIZE: Final = 100
UNIVERSE_MEMBERS: Final = 200
ADJUSTED_RELATIVE: Final = Path("adjusted_daily") / "provider=bharatstock"
SNAPSHOT_RELATIVE: Final = Path("universe_snapshots") / "nifty-universe-v3.json"


def _instrument_key(isin: str, exchange: str, symbol: str) -> str:
    return f"{isin}:{exchange}:{symbol}"


def _universe_members(storage_root: Path) -> tuple[str, ...]:
    """Membership admitted only by the governed official-snapshot reader."""
    universe = read_historic_nifty_universe(storage_root)
    try:
        rows = list(
            csv.DictReader(io.StringIO(universe.nifty200_source_csv.decode("utf-8")))
        )
    except (UnicodeDecodeError, csv.Error):
        raise ValueError("governed Nifty 200 CSV is invalid") from None
    members: list[str] = []
    for row in rows:
        isin = (row.get("ISIN Code") or "").strip()
        symbol = (row.get("Symbol") or "").strip()
        if not isin or not symbol:
            raise ValueError("governed Nifty 200 membership is invalid")
        members.append(_instrument_key(isin, "NSE", symbol))
    if (
        len(members) != UNIVERSE_MEMBERS
        or len(set(members)) != UNIVERSE_MEMBERS
        or tuple(universe.nifty200) != tuple(member.split(":")[2] for member in members)
    ):
        raise ValueError("governed Nifty 200 membership is invalid")
    return tuple(members)


def _runtime_identity() -> dict[str, object]:
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


def _snapshot_identity(storage_root: Path) -> dict[str, object]:
    universe = read_historic_nifty_universe(storage_root)
    path = storage_root / SNAPSHOT_RELATIVE
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, ValueError):
        raise ValueError("retained universe snapshot is unreadable") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("schema"), str):
        raise ValueError("retained universe snapshot schema is invalid")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "schema": payload["schema"],
        "members": len(universe.nifty200),
        "nifty200_source_sha256": universe.nifty200_source_sha256,
        "window_start": universe.window_start.isoformat(),
        "window_end": universe.window_end.isoformat(),
        "retrieved_at": universe.retrieved_at.isoformat(),
    }


def _session_date(value: object) -> date | None:
    if type(value) is date:
        return cast(date, value)
    if type(value) is datetime:
        return cast(datetime, value).date()
    if type(value) is str:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def retained_sessions(storage_root: Path) -> dict[str, date]:
    """Newest retained adjusted session per composite instrument key.

    The production dataset stores ``isin``, ``exchange``, and ``symbol`` as
    separate columns; the universe key is their composite. Reading only
    ``symbol`` would never match a cohort member.
    """
    newest: dict[str, date] = {}
    for path in sorted(
        (storage_root / ADJUSTED_RELATIVE).rglob("*.parquet"),
    ):
        try:
            table = pq.read_table(
                path, columns=["isin", "exchange", "symbol", "session"]
            )
            isins = table.column("isin").to_pylist()
            exchanges = table.column("exchange").to_pylist()
            symbols = table.column("symbol").to_pylist()
            sessions = table.column("session").to_pylist()
        except Exception:  # noqa: BLE001, S112 - unreadable dataset is not coverage
            continue
        for isin, exchange, symbol, raw_session in zip(
            isins, exchanges, symbols, sessions, strict=True
        ):
            session = _session_date(raw_session)
            if (
                type(isin) is not str
                or not isin
                or type(exchange) is not str
                or not exchange
                or type(symbol) is not str
                or not symbol
                or session is None
            ):
                continue
            key = _instrument_key(isin, exchange, symbol)
            observed = newest.get(key)
            if observed is None or session > observed:
                newest[key] = session
    return newest


def _cohorts(members: tuple[str, ...]) -> list[tuple[str, ...]]:
    return [
        members[offset : offset + COHORT_SIZE]
        for offset in range(0, len(members), COHORT_SIZE)
    ]


def _missing(
    cohort: tuple[str, ...], retained: dict[str, date], stamp: date
) -> list[str]:
    return [key for key in cohort if key not in retained or retained[key] < stamp]


def plan(storage_root: Path, stamp: date, stage_start: date) -> dict[str, object]:
    if stage_start > stamp:
        raise ValueError("stage start is after the requested end")
    members = _universe_members(storage_root)
    retained = retained_sessions(storage_root)
    cohorts: list[dict[str, object]] = []
    for index, cohort in enumerate(_cohorts(members)):
        missing = _missing(cohort, retained, stamp)
        unretained = sum(1 for key in missing if key not in retained)
        if not missing:
            cohorts.append(
                {
                    "index": index,
                    "status": "SKIPPED",
                    "members": len(cohort),
                    "current": len(cohort),
                    "missing": [],
                    "unretained_missing": 0,
                    "start": None,
                    "oldest_missing": None,
                }
            )
            continue
        oldest_missing = min(
            missing,
            key=lambda key: (
                key in retained,
                retained.get(key, date.min),
            ),
        )
        oldest_newest = retained.get(oldest_missing)
        start = (
            stage_start
            if oldest_newest is None
            else max(oldest_newest + timedelta(days=1), stage_start)
        )
        if start > stamp:
            raise ValueError("cohort plan range is invalid")
        cohorts.append(
            {
                "index": index,
                "status": "PENDING",
                "members": len(cohort),
                "current": len(cohort) - len(missing),
                "missing": missing,
                "unretained_missing": unretained,
                "start": start.isoformat(),
                "oldest_missing": oldest_missing,
            }
        )
    return {
        "schema": "adjusted-cohort-plan@v1",
        "stamp": stamp.isoformat(),
        "stage_start": stage_start.isoformat(),
        "cohort_size": COHORT_SIZE,
        "members": len(members),
        "status": (
            "SKIPPED"
            if all(cohort["status"] == "SKIPPED" for cohort in cohorts)
            else "PENDING"
        ),
        "universe": _snapshot_identity(storage_root),
        "runtime": _runtime_identity(),
        "cohorts": cohorts,
    }


def verify(storage_root: Path, stamp: date, cohort_index: int) -> dict[str, object]:
    members = _universe_members(storage_root)
    cohorts = _cohorts(members)
    if not 0 <= cohort_index < len(cohorts):
        raise ValueError("cohort index is out of range")
    retained = retained_sessions(storage_root)
    missing = _missing(cohorts[cohort_index], retained, stamp)
    return {
        "index": cohort_index,
        "status": "COMPLETE" if not missing else "INCOMPLETE",
        "members": len(cohorts[cohort_index]),
        "missing": missing,
        "missing_count": len(missing),
    }


def _tsv(value: dict[str, object]) -> str:
    cohorts = cast(list[dict[str, object]], value["cohorts"])
    return "\n".join(
        "|".join(
            (
                str(cohort["index"]),
                str(cohort["status"]),
                str(cohort["members"]),
                str(cohort.get("start") or ""),
                str(len(cast(list[str], cohort["missing"]))),
                str(cohort["unretained_missing"]),
                ",".join(cast(list[str], cohort["missing"])),
                str(cohort["oldest_missing"] or ""),
            )
        )
        for cohort in cohorts
    )


def main(argv: list[str] | None = None) -> int:  # noqa: C901 - CLI dispatch
    parser = argparse.ArgumentParser(prog="capture-adjusted-cohorts")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("members", "identity", "plan", "verify"):
        command = sub.add_parser(name)
        command.add_argument("--storage-root", type=Path, required=True)
        if name == "plan":
            command.add_argument("--stamp", type=date.fromisoformat, required=True)
            command.add_argument(
                "--stage-start", type=date.fromisoformat, required=True
            )
            command.add_argument("--json-out", type=Path)
            command.add_argument("--format", choices=("json", "tsv"), default="json")
        if name == "verify":
            command.add_argument("--stamp", type=date.fromisoformat, required=True)
            command.add_argument("--cohort-index", type=int, required=True)
            command.add_argument("--format", choices=("json", "tsv"), default="json")
    args = parser.parse_args(argv)
    root = args.storage_root
    try:
        if not root.is_absolute():
            raise ValueError("storage root must be absolute")
        if args.command == "members":
            for member in _universe_members(root):
                print(member)
            return 0
        if args.command == "identity":
            print(json.dumps(_snapshot_identity(root), sort_keys=True))
            return 0
        if args.command == "plan":
            value = plan(root, args.stamp, args.stage_start)
            if args.json_out is not None:
                args.json_out.write_text(
                    json.dumps(value, indent=2, sort_keys=True) + "\n"
                )
            print(
                json.dumps(value, sort_keys=True)
                if args.format == "json"
                else _tsv(value)
            )
            return 0
        value = verify(root, args.stamp, args.cohort_index)
        if args.format == "json":
            print(json.dumps(value, sort_keys=True))
        else:
            print(
                "|".join(
                    (
                        str(value["index"]),
                        str(value["status"]),
                        str(value["missing_count"]),
                        ",".join(cast(list[str], value["missing"])),
                    )
                )
            )
        return 0
    except ValueError as error:
        sys.stderr.write(f"capture_invalid: {error}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
