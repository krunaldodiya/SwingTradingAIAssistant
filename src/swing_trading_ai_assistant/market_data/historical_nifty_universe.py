"""Validated retained Nifty 100/Nifty 500 membership for one decision window."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Final, cast

_SCHEMA: Final = "historical-nifty-universe@v1"
_FILENAME: Final = "historical-nifty100-nifty500.json"
_HEADERS: Final = ("Company Name", "Industry", "Symbol", "Series", "ISIN Code")


@dataclass(frozen=True, slots=True)
class HistoricNiftyUniverse:
    """Official Nifty memberships and their shared data window."""

    nifty100: tuple[str, ...]
    nifty500: tuple[str, ...]
    window_start: date
    window_end: date
    nifty100_source_sha256: str
    nifty500_source_sha256: str


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _symbols(raw: bytes, *, expected_counts: frozenset[int]) -> tuple[str, ...]:
    try:
        rows = list(csv.DictReader(StringIO(raw.decode("utf-8"))))
    except (UnicodeDecodeError, csv.Error):
        raise ValueError("official constituent CSV is invalid") from None
    if not rows or tuple(rows[0]) != _HEADERS:
        raise ValueError("official constituent CSV schema is invalid")
    symbols = tuple(str(row.get("Symbol", "")) for row in rows)
    if (
        len(symbols) not in expected_counts
        or any(not symbol or symbol != symbol.upper() for symbol in symbols)
        or len(set(symbols)) != len(symbols)
    ):
        raise ValueError("official constituent CSV membership is invalid")
    return symbols


def build_historic_nifty_universe(
    nifty100_csv: bytes,
    nifty500_csv: bytes,
    *,
    window_start: date,
    window_end: date,
) -> HistoricNiftyUniverse:
    """Validate two retained official snapshots for one exact OHLCV window."""
    if (
        type(window_start) is not date
        or type(window_end) is not date
        or window_start > window_end
    ):
        raise ValueError("data window is invalid")
    nifty100 = _symbols(nifty100_csv, expected_counts=frozenset((100,)))
    nifty500 = _symbols(nifty500_csv, expected_counts=frozenset((500, 501)))
    if not set(nifty100).issubset(nifty500):
        raise ValueError("Nifty 100 is not a Nifty 500 subset")
    return HistoricNiftyUniverse(
        nifty100=nifty100,
        nifty500=nifty500,
        window_start=window_start,
        window_end=window_end,
        nifty100_source_sha256=_digest(nifty100_csv),
        nifty500_source_sha256=_digest(nifty500_csv),
    )


def _payload(universe: HistoricNiftyUniverse) -> dict[str, object]:
    return {
        "schema": _SCHEMA,
        "nifty100": list(universe.nifty100),
        "nifty500": list(universe.nifty500),
        "window_start": universe.window_start.isoformat(),
        "window_end": universe.window_end.isoformat(),
        "nifty100_source_sha256": universe.nifty100_source_sha256,
        "nifty500_source_sha256": universe.nifty500_source_sha256,
    }


def retain_historic_nifty_universe(root: Path, universe: HistoricNiftyUniverse) -> Path:
    """Persist a reviewed, immutable membership manifest beside private data."""
    if not root.is_absolute():
        raise ValueError("storage root is invalid")
    directory = root / "universe_snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / _FILENAME
    raw = (
        json.dumps(_payload(universe), sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        + b"\n"
    )
    if destination.exists():
        if destination.read_bytes() != raw:
            raise ValueError("historic universe manifest already differs")
        return destination
    destination.write_bytes(raw)
    return destination


def read_historic_nifty_universe(root: Path) -> HistoricNiftyUniverse:
    """Read the exact retained membership manifest; never infer membership from data batches."""
    if not root.is_absolute():
        raise ValueError("storage root is invalid")
    try:
        raw_value = json.loads((root / "universe_snapshots" / _FILENAME).read_text())
        if not isinstance(raw_value, dict):
            raise ValueError
        value = cast(dict[str, object], raw_value)
        if (
            set(value)
            != {
                "schema",
                "nifty100",
                "nifty500",
                "window_start",
                "window_end",
                "nifty100_source_sha256",
                "nifty500_source_sha256",
            }
            or value["schema"] != _SCHEMA
        ):
            raise ValueError
        raw_n100 = value["nifty100"]
        raw_n500 = value["nifty500"]
        start = value["window_start"]
        end = value["window_end"]
        n100_hash = value["nifty100_source_sha256"]
        n500_hash = value["nifty500_source_sha256"]
        if not isinstance(raw_n100, list) or not isinstance(raw_n500, list):
            raise ValueError
        n100_items = cast(list[object], raw_n100)
        n500_items = cast(list[object], raw_n500)
        if (
            not all(type(item) is str for item in n100_items)
            or not all(type(item) is str for item in n500_items)
            or type(start) is not str
            or type(end) is not str
            or type(n100_hash) is not str
            or type(n500_hash) is not str
        ):
            raise ValueError
        universe = HistoricNiftyUniverse(
            nifty100=tuple(cast(list[str], raw_n100)),
            nifty500=tuple(cast(list[str], raw_n500)),
            window_start=date.fromisoformat(start),
            window_end=date.fromisoformat(end),
            nifty100_source_sha256=n100_hash,
            nifty500_source_sha256=n500_hash,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("historic Nifty universe evidence is unavailable") from None
    if (
        len(universe.nifty100) != 100
        or len(universe.nifty500) not in {500, 501}
        or len(set(universe.nifty100)) != 100
        or len(set(universe.nifty500)) != len(universe.nifty500)
        or len(universe.nifty100_source_sha256) != 64
        or len(universe.nifty500_source_sha256) != 64
    ):
        raise ValueError("historic Nifty universe evidence is invalid")
    return universe
