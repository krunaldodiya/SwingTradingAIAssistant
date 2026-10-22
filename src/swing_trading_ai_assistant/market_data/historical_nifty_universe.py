"""Verified retained Nifty 50/Next 50/100/200 membership for one decision window."""

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

_SCHEMA: Final = "retained-nifty-universe@v3"
_FILENAME: Final = "nifty-universe-v3.json"
_HEADERS: Final = ("Company Name", "Industry", "Symbol", "Series", "ISIN Code")
_SHA256: Final = re.compile(r"[0-9a-f]{64}\Z")
_OFFICIAL_HOST: Final = "nsearchives.nseindia.com"
_NIFTY50_URL: Final = (
    "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv"
)
_NIFTYNEXT50_URL: Final = (
    "https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv"
)
_NIFTY100_URL: Final = (
    "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv"
)
_NIFTY200_URL: Final = (
    "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv"
)
_LIST_COUNTS: Final = {
    "nifty50": 50,
    "niftynext50": 50,
    "nifty100": 100,
    "nifty200": 200,
}
_LISTS: Final = ("nifty50", "niftynext50", "nifty100", "nifty200")


@dataclass(frozen=True, slots=True)
class HistoricNiftyUniverse:
    """Verified official memberships and their shared retained OHLCV window."""

    nifty50: tuple[str, ...]
    niftynext50: tuple[str, ...]
    nifty100: tuple[str, ...]
    nifty200: tuple[str, ...]
    window_start: date
    window_end: date
    nifty50_source_url: str
    niftynext50_source_url: str
    nifty100_source_url: str
    nifty200_source_url: str
    retrieved_at: datetime
    nifty50_source_sha256: str
    niftynext50_source_sha256: str
    nifty100_source_sha256: str
    nifty200_source_sha256: str
    nifty50_source_csv: bytes
    niftynext50_source_csv: bytes
    nifty100_source_csv: bytes
    nifty200_source_csv: bytes


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _official_url(value: str, expected: str) -> str:
    parsed = urlparse(value)
    if (
        value != expected
        or parsed.scheme != "https"
        or parsed.hostname != _OFFICIAL_HOST
        or not parsed.path
    ):
        raise ValueError("official constituent source URL is invalid")
    return value


def _symbols(raw: bytes, *, expected_count: int) -> tuple[str, ...]:
    try:
        rows = list(csv.DictReader(StringIO(raw.decode("utf-8"))))
    except (UnicodeDecodeError, csv.Error):
        raise ValueError("official constituent CSV is invalid") from None
    if not rows or tuple(rows[0]) != _HEADERS:
        raise ValueError("official constituent CSV schema is invalid")
    symbols = tuple(str(row.get("Symbol", "")) for row in rows)
    if (
        len(symbols) != expected_count
        or any(not symbol or symbol != symbol.upper() for symbol in symbols)
        or len(set(symbols)) != len(symbols)
    ):
        raise ValueError("official constituent CSV membership is invalid")
    return symbols


def build_historic_nifty_universe(
    nifty50_csv: bytes,
    niftynext50_csv: bytes,
    nifty100_csv: bytes,
    nifty200_csv: bytes,
    *,
    window_start: date,
    window_end: date,
    nifty50_source_url: str,
    niftynext50_source_url: str,
    nifty100_source_url: str,
    nifty200_source_url: str,
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
    nifty50 = _symbols(nifty50_csv, expected_count=_LIST_COUNTS["nifty50"])
    niftynext50 = _symbols(niftynext50_csv, expected_count=_LIST_COUNTS["niftynext50"])
    nifty100 = _symbols(nifty100_csv, expected_count=_LIST_COUNTS["nifty100"])
    nifty200 = _symbols(nifty200_csv, expected_count=_LIST_COUNTS["nifty200"])
    if (
        not set(nifty50).isdisjoint(niftynext50)
        or set(nifty50) | set(niftynext50) != set(nifty100)
        or not set(nifty100).issubset(nifty200)
    ):
        raise ValueError("official constituent memberships are inconsistent")
    return HistoricNiftyUniverse(
        nifty50=nifty50,
        niftynext50=niftynext50,
        nifty100=nifty100,
        nifty200=nifty200,
        window_start=window_start,
        window_end=window_end,
        nifty50_source_url=_official_url(nifty50_source_url, _NIFTY50_URL),
        niftynext50_source_url=_official_url(niftynext50_source_url, _NIFTYNEXT50_URL),
        nifty100_source_url=_official_url(nifty100_source_url, _NIFTY100_URL),
        nifty200_source_url=_official_url(nifty200_source_url, _NIFTY200_URL),
        retrieved_at=retrieved_at,
        nifty50_source_sha256=_digest(nifty50_csv),
        niftynext50_source_sha256=_digest(niftynext50_csv),
        nifty100_source_sha256=_digest(nifty100_csv),
        nifty200_source_sha256=_digest(nifty200_csv),
        nifty50_source_csv=nifty50_csv,
        niftynext50_source_csv=niftynext50_csv,
        nifty100_source_csv=nifty100_csv,
        nifty200_source_csv=nifty200_csv,
    )


def _payload(universe: HistoricNiftyUniverse) -> dict[str, object]:
    verified = build_historic_nifty_universe(
        universe.nifty50_source_csv,
        universe.niftynext50_source_csv,
        universe.nifty100_source_csv,
        universe.nifty200_source_csv,
        window_start=universe.window_start,
        window_end=universe.window_end,
        nifty50_source_url=universe.nifty50_source_url,
        niftynext50_source_url=universe.niftynext50_source_url,
        nifty100_source_url=universe.nifty100_source_url,
        nifty200_source_url=universe.nifty200_source_url,
        retrieved_at=universe.retrieved_at,
    )
    if verified != universe:
        raise ValueError("universe evidence does not match its official source bytes")
    payload: dict[str, object] = {
        "schema": _SCHEMA,
        "retrieved_at": universe.retrieved_at.isoformat().replace("+00:00", "Z"),
        "window_start": universe.window_start.isoformat(),
        "window_end": universe.window_end.isoformat(),
    }
    for name in _LISTS:
        payload[f"{name}_source_csv_base64"] = base64.b64encode(
            cast(bytes, getattr(universe, f"{name}_source_csv"))
        ).decode()
        payload[f"{name}_source_url"] = getattr(universe, f"{name}_source_url")
        payload[f"{name}_source_sha256"] = getattr(universe, f"{name}_source_sha256")
    return payload


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
            "retrieved_at",
            "window_start",
            "window_end",
        }
        for name in _LISTS:
            required.update(
                {
                    f"{name}_source_csv_base64",
                    f"{name}_source_url",
                    f"{name}_source_sha256",
                }
            )
        if set(value) != required or value["schema"] != _SCHEMA:
            raise ValueError
        source_keys = tuple(key for key in required if key != "schema")
        if any(type(value[key]) is not str for key in source_keys):
            raise ValueError
        sources: dict[str, bytes] = {}
        source_hashes: list[str] = []
        for name in _LISTS:
            sources[name] = base64.b64decode(
                cast(str, value[f"{name}_source_csv_base64"]), validate=True
            )
            source_hashes.append(cast(str, value[f"{name}_source_sha256"]))
        if any(_SHA256.fullmatch(item) is None for item in source_hashes):
            raise ValueError
        retrieved_at = datetime.fromisoformat(
            cast(str, value["retrieved_at"]).replace("Z", "+00:00")
        )
        universe = build_historic_nifty_universe(
            sources["nifty50"],
            sources["niftynext50"],
            sources["nifty100"],
            sources["nifty200"],
            window_start=date.fromisoformat(cast(str, value["window_start"])),
            window_end=date.fromisoformat(cast(str, value["window_end"])),
            nifty50_source_url=cast(str, value["nifty50_source_url"]),
            niftynext50_source_url=cast(str, value["niftynext50_source_url"]),
            nifty100_source_url=cast(str, value["nifty100_source_url"]),
            nifty200_source_url=cast(str, value["nifty200_source_url"]),
            retrieved_at=retrieved_at,
        )
        if source_hashes != [
            universe.nifty50_source_sha256,
            universe.niftynext50_source_sha256,
            universe.nifty100_source_sha256,
            universe.nifty200_source_sha256,
        ]:
            raise ValueError
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise ValueError(
            "retained official Nifty universe evidence is unavailable"
        ) from None
    return universe
