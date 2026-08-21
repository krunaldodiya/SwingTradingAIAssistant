"""Concrete yfinance boundary for adjusted-daily-close acquisition."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Final, Protocol, cast

import pandas as pd
import yfinance

_YFINANCE_MODULE: Final[ModuleType] = cast(ModuleType, yfinance)


class _PandasFrame(Protocol):
    @property
    def empty(self) -> bool: ...

    @property
    def index(self) -> Iterable[object]: ...

    @property
    def columns(self) -> object: ...

    def __getitem__(self, key: str) -> object: ...


class _PandasColumnGroup(Protocol):
    def __getitem__(self, key: str) -> object: ...


class _PandasSeries(Protocol):
    def tolist(self) -> list[object]: ...


@dataclass(frozen=True, slots=True)
class YfinanceAdjustedDailyDownloadAdapter:
    """Normalize public ``yfinance.download`` frames for the service port."""

    def download(self, **kwargs: object) -> Mapping[str, object]:
        """Call yfinance once and expose only the expected Close frame shape."""
        response = _public_download(**kwargs)
        if response is None:
            return {}
        if not isinstance(response, pd.DataFrame):
            return _invalid_frame()

        frame = cast(_PandasFrame, response)
        if frame.empty:
            return {}
        tickers = _tickers(kwargs.get("tickers"))
        sessions = _session_dates(frame.index)
        timezone = _index_timezone(frame.index)
        provider_source = _provider_source()
        if (
            tickers is None
            or sessions is None
            or timezone is None
            or provider_source is None
        ):
            return _invalid_frame()
        close: dict[str, tuple[object, ...]] = {}
        for ticker in tickers:
            values = _close_values(frame, ticker)
            if values is None:
                return _invalid_frame()
            close[ticker] = values

        return {
            "timezone": timezone,
            "index": sessions,
            "close": close,
            "retrieved_at": datetime.now(UTC),
            "provider_source": provider_source,
            "temporal_label": "REVISED_NON_PIT",
        }


def _public_download(**kwargs: object) -> object:
    public_download: object = _YFINANCE_MODULE.__dict__.get("download")
    if not callable(public_download):
        raise RuntimeError("yfinance.download unavailable")
    return public_download(**kwargs)


def _tickers(value: object) -> tuple[str, ...] | None:
    if type(value) is str:
        return (value,)
    if type(value) is not tuple:
        return None
    raw_tickers = cast(tuple[object, ...], value)
    tickers: list[str] = []
    for ticker in raw_tickers:
        if type(ticker) is not str or not ticker:
            return None
        tickers.append(ticker)
    return tuple(tickers) if tickers else None


def _index_timezone(index: object) -> str | None:
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        return None
    timezone = index.tz
    zone_name = getattr(timezone, "key", None) or getattr(timezone, "zone", None)
    return "Asia/Kolkata" if zone_name == "Asia/Kolkata" else None


def _provider_source() -> str | None:
    version = _YFINANCE_MODULE.__dict__.get("__version__")
    return f"yfinance=={version}" if type(version) is str and version else None


def _session_dates(index: Iterable[object]) -> tuple[date, ...] | None:
    sessions = tuple(_session_date(value) for value in index)
    if any(session is None for session in sessions):
        return None
    return tuple(cast(date, session) for session in sessions)


def _session_date(value: object) -> date | None:
    if type(value) is date:
        return value
    as_date = getattr(value, "date", None)
    if not callable(as_date):
        return None
    result = as_date()
    return result if type(result) is date else None


def _close_values(frame: _PandasFrame, ticker: str) -> tuple[object, ...] | None:
    if not isinstance(frame.columns, pd.MultiIndex):
        return None
    for outer, inner in (("Close", ticker), (ticker, "Close")):
        try:
            grouped = frame[outer]
        except KeyError:
            continue
        if not isinstance(grouped, pd.DataFrame):
            continue
        values = cast(_PandasColumnGroup, grouped)[inner]
        if isinstance(values, pd.Series):
            return tuple(cast(_PandasSeries, values).tolist())
    return None


def _invalid_frame() -> Mapping[str, object]:
    return {"timezone": None, "index": (), "close": {}}
