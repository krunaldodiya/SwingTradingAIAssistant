"""Verified retained Nifty 100/Nifty 500 membership for one decision window."""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import StringIO
from pathlib import Path
from typing import Final, cast
from urllib.parse import urlparse

_SCHEMA: Final = "retained-nifty-universe@v2"
_FILENAME: Final = "nifty100-nifty500.json"
_HEADERS: Final = ("Company Name", "Industry", "Symbol", "Series", "ISIN Code")
_SHA256: Final = re.compile(r"[0-9a-f]{64}\Z")
_OFFICIAL_HOST: Final = "nsearchives.nseindia.com"


@dataclass(frozen=True, slots=True)
class HistoricNiftyUniverse:
    """Verified official memberships and their shared retained OHLCV window."""

    nifty100: tuple[str, ...]
    nifty500: tuple[str, ...]
    window_start: date
    window_end: date
    nifty100_source_url: str
    nifty500_source_url: str
    retrieved_at: datetime
    nifty100_source_sha256: str
    nifty500_source_sha256: str
    nifty100_source_csv: bytes
    nifty500_source_csv: bytes


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _official_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != _OFFICIAL_HOST or not parsed.path:
        raise ValueError("official constituent source URL is invalid")
    return value


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
    nifty100_source_url: str,
    nifty500_source_url: str,
    retrieved_at: datetime,
) -> HistoricNiftyUniverse:
    """Validate retained official snapshots before they can drive a scan."""
    if (
        type(window_start) is not date
        or type(window_end) is not date
        or window_start > window_end
        or type(retrieved_at) is not datetime
        or retrieved_at.tzinfo is None
        or retrieved_at.utcoffset() != UTC.utcoffset(retrieved_at)
    ):
        raise ValueError("universe evidence time is invalid")
    nifty100 = _symbols(nifty100_csv, expected_counts=frozenset((100,)))
    nifty500 = _symbols(nifty500_csv, expected_counts=frozenset((500, 501)))
    if not set(nifty100).issubset(nifty500):
        raise ValueError("Nifty 100 is not a Nifty 500 subset")
    return HistoricNiftyUniverse(
        nifty100=nifty100,
        nifty500=nifty500,
        window_start=window_start,
        window_end=window_end,
        nifty100_source_url=_official_url(nifty100_source_url),
        nifty500_source_url=_official_url(nifty500_source_url),
        retrieved_at=retrieved_at,
        nifty100_source_sha256=_digest(nifty100_csv),
        nifty500_source_sha256=_digest(nifty500_csv),
        nifty100_source_csv=nifty100_csv,
        nifty500_source_csv=nifty500_csv,
    )


def _payload(universe: HistoricNiftyUniverse) -> dict[str, object]:
    verified = build_historic_nifty_universe(
        universe.nifty100_source_csv,
        universe.nifty500_source_csv,
        window_start=universe.window_start,
        window_end=universe.window_end,
        nifty100_source_url=universe.nifty100_source_url,
        nifty500_source_url=universe.nifty500_source_url,
        retrieved_at=universe.retrieved_at,
    )
    if verified != universe:
        raise ValueError("universe evidence does not match its official source bytes")
    return {
        "schema": _SCHEMA,
        "nifty100_source_csv_base64": base64.b64encode(
            universe.nifty100_source_csv
        ).decode(),
        "nifty500_source_csv_base64": base64.b64encode(
            universe.nifty500_source_csv
        ).decode(),
        "nifty100_source_url": universe.nifty100_source_url,
        "nifty500_source_url": universe.nifty500_source_url,
        "retrieved_at": universe.retrieved_at.isoformat().replace("+00:00", "Z"),
        "window_start": universe.window_start.isoformat(),
        "window_end": universe.window_end.isoformat(),
        "nifty100_source_sha256": universe.nifty100_source_sha256,
        "nifty500_source_sha256": universe.nifty500_source_sha256,
    }


def retain_historic_nifty_universe(root: Path, universe: HistoricNiftyUniverse) -> Path:
    """Persist immutable source bytes and derived memberships beside private data."""
    if not root.is_absolute():
        raise ValueError("storage root is invalid")
    directory = root / "universe_snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / _FILENAME
    raw = (
        json.dumps(_payload(universe), sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )
    if destination.exists():
        if destination.read_bytes() != raw:
            raise ValueError("retained universe manifest already differs")
        return destination
    destination.write_bytes(raw)
    return destination


def read_historic_nifty_universe(root: Path) -> HistoricNiftyUniverse:
    """Recompute memberships from retained official source bytes before scanning."""
    if not root.is_absolute():
        raise ValueError("storage root is invalid")
    try:
        raw_value = json.loads((root / "universe_snapshots" / _FILENAME).read_text())
        if not isinstance(raw_value, dict):
            raise ValueError
        value = cast(dict[str, object], raw_value)
        required = {
            "schema",
            "nifty100_source_csv_base64",
            "nifty500_source_csv_base64",
            "nifty100_source_url",
            "nifty500_source_url",
            "retrieved_at",
            "window_start",
            "window_end",
            "nifty100_source_sha256",
            "nifty500_source_sha256",
        }
        if set(value) != required or value["schema"] != _SCHEMA:
            raise ValueError
        source_keys = (
            "nifty100_source_csv_base64",
            "nifty500_source_csv_base64",
            "nifty100_source_url",
            "nifty500_source_url",
            "retrieved_at",
            "window_start",
            "window_end",
            "nifty100_source_sha256",
            "nifty500_source_sha256",
        )
        if any(type(value[key]) is not str for key in source_keys):
            raise ValueError
        n100_csv = base64.b64decode(
            cast(str, value["nifty100_source_csv_base64"]), validate=True
        )
        n500_csv = base64.b64decode(
            cast(str, value["nifty500_source_csv_base64"]), validate=True
        )
        source_hashes = (
            cast(str, value["nifty100_source_sha256"]),
            cast(str, value["nifty500_source_sha256"]),
        )
        if any(_SHA256.fullmatch(item) is None for item in source_hashes):
            raise ValueError
        retrieved_at = datetime.fromisoformat(
            cast(str, value["retrieved_at"]).replace("Z", "+00:00")
        )
        universe = build_historic_nifty_universe(
            n100_csv,
            n500_csv,
            window_start=date.fromisoformat(cast(str, value["window_start"])),
            window_end=date.fromisoformat(cast(str, value["window_end"])),
            nifty100_source_url=cast(str, value["nifty100_source_url"]),
            nifty500_source_url=cast(str, value["nifty500_source_url"]),
            retrieved_at=retrieved_at,
        )
        if source_hashes != (
            universe.nifty100_source_sha256,
            universe.nifty500_source_sha256,
        ):
            raise ValueError
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise ValueError(
            "retained official Nifty universe evidence is unavailable"
        ) from None
    return universe
