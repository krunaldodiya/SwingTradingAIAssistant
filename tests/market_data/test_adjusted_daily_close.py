"""Focused MVP acceptance tests for Issue #127 adjusted daily close."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast

import pandas as pd
import yfinance
from pytest import MonkeyPatch

from swing_trading_ai_assistant.market_data.adjusted_daily import (
    AdjustedDailyCloseFailure,
    AdjustedDailyCloseSuccess,
    YfinanceAdjustedDailyDownloadAdapter,
    acquire_adjusted_daily_close_v1,
    serialize_public_result_v1,
)

_S0 = date(2026, 7, 6)
_S20 = date(2026, 8, 3)
_CUTOFF = datetime(2026, 8, 4, 12, tzinfo=UTC)


@dataclass
class _Provider:
    result: object
    calls: list[dict[str, object]] = field(
        default_factory=lambda: cast(list[dict[str, object]], [])
    )

    def download(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.result, BaseException):
            raise self.result
        return deepcopy(self.result)


def _sessions() -> tuple[date, ...]:
    return tuple(
        _S0 + timedelta(days=offset)
        for offset in range((_S20 - _S0).days + 1)
        if (_S0 + timedelta(days=offset)).weekday() < 5
    )


def _member(index: int, symbol: str, provider_symbol: str) -> dict[str, str]:
    return {
        "isin": {1: "INE002A01018", 2: "INE062A01020"}[index],
        "project_symbol": symbol,
        "provider_symbol": provider_symbol,
    }


def _request(*, members: tuple[dict[str, str], ...] | None = None) -> dict[str, object]:
    mapped_members = members or (
        _member(1, "RELIANCE", "RELIANCE.NS"),
        _member(2, "SBIN", "SBIN.NS"),
    )
    return {
        "provider_id": "YFINANCE",
        "price_basis": "ADJUSTED",
        "decision_cutoff": _CUTOFF,
        "plan19_cohort": {
            "members": [
                {
                    "isin": member["isin"],
                    "project_symbol": member["project_symbol"],
                }
                for member in mapped_members
            ]
        },
        "plan21_schedule": {"sessions": _sessions()},
        "mapped_members": list(mapped_members),
    }


def _frame(
    *,
    sessions: tuple[date, ...] | None = None,
    closes: dict[str, tuple[float, ...]] | None = None,
) -> dict[str, object]:
    return {
        "timezone": "Asia/Kolkata",
        "index": sessions or _sessions(),
        "close": closes
        or {
            "RELIANCE.NS": tuple(100 + offset for offset in range(21)),
            "SBIN.NS": tuple(200 + offset for offset in range(21)),
        },
    }


def _acquire(request: dict[str, object], provider: _Provider) -> object:
    return acquire_adjusted_daily_close_v1(request, provider=provider)


def test_requires_explicit_yfinance_adjusted_selection_and_frozen_download() -> None:
    provider = _Provider(_frame())
    invalid_request = _request()
    invalid_request["provider_id"] = "UPSTOX"

    invalid = _acquire(invalid_request, provider)
    assert invalid == AdjustedDailyCloseFailure(
        "INVALID_REQUEST", "PROVIDER_SELECTION_INVALID"
    )
    assert provider.calls == []

    result = _acquire(_request(), provider)

    assert isinstance(result, AdjustedDailyCloseSuccess)
    assert provider.calls == [
        {
            "tickers": ("RELIANCE.NS", "SBIN.NS"),
            "start": "2026-07-06",
            "end": "2026-08-04",
            "interval": "1d",
            "actions": False,
            "threads": False,
            "ignore_tz": False,
            "group_by": "ticker",
            "auto_adjust": True,
            "back_adjust": False,
            "repair": False,
            "keepna": True,
            "progress": False,
            "prepost": False,
            "rounding": False,
            "timeout": 10,
            "multi_level_index": True,
        }
    ]


def test_rejects_missing_or_nonunique_supplied_member_mapping_before_fetch() -> None:
    provider = _Provider(_frame())
    request = _request(
        members=(
            _member(1, "RELIANCE", "ONE.NS"),
            _member(2, "SBIN", "ONE.NS"),
        )
    )

    duplicate = _acquire(request, provider)
    assert duplicate == AdjustedDailyCloseFailure(
        "INVALID_REQUEST", "MEMBER_MAPPING_INVALID"
    )
    assert provider.calls == []

    missing_mapping = _request()
    missing_mapping["mapped_members"] = None
    missing = _acquire(missing_mapping, provider)
    assert missing == AdjustedDailyCloseFailure(
        "INVALID_REQUEST", "MEMBER_MAPPING_INVALID"
    )
    assert provider.calls == []


def test_normalizes_exact_s0_and_s20_adjusted_close_facts() -> None:
    provider = _Provider(
        _frame(
            closes={
                "SBIN.NS": tuple(200 + offset for offset in range(21)),
                "RELIANCE.NS": tuple(100 + offset for offset in range(21)),
            }
        )
    )

    result = _acquire(_request(), provider)

    assert isinstance(result, AdjustedDailyCloseSuccess)
    handoff = result.handoff
    assert handoff.provider_id == "YFINANCE"
    assert handoff.price_basis == "ADJUSTED"
    assert handoff.decision_cutoff == _CUTOFF
    assert handoff.comparison_session == _S0
    assert handoff.decision_session == _S20
    assert [
        (fact.project_symbol, fact.s0.adjusted_close, fact.s20.adjusted_close)
        for fact in handoff.members
    ] == [
        ("RELIANCE", Decimal("100"), Decimal("120")),
        ("SBIN", Decimal("200"), Decimal("220")),
    ]


def test_rejects_invalid_schedule_before_fetch_and_incomplete_frame_after_fetch() -> (
    None
):
    provider = _Provider(_frame())
    invalid_schedule = _request()
    invalid_schedule["plan21_schedule"] = {"sessions": _sessions()[:-1]}

    schedule_result = _acquire(invalid_schedule, provider)
    assert schedule_result == AdjustedDailyCloseFailure(
        "INVALID_REQUEST", "SCHEDULE_INVALID"
    )
    assert provider.calls == []

    incomplete = _acquire(
        _request(),
        _Provider(_frame(closes={"RELIANCE.NS": (100.0,) * 21})),
    )
    assert incomplete == AdjustedDailyCloseFailure(
        "INSUFFICIENT_DATA", "FRAME_SCHEMA_INVALID"
    )


def test_classifies_empty_and_failing_provider_responses_without_facts() -> None:
    empty = _acquire(_request(), _Provider({}))
    failed = _acquire(_request(), _Provider(RuntimeError("transport detail")))

    assert empty == AdjustedDailyCloseFailure("INSUFFICIENT_DATA", "PROVIDER_EMPTY")
    assert failed == AdjustedDailyCloseFailure(
        "PROVIDER_FAILURE", "PROVIDER_CALL_FAILED"
    )


def test_public_result_is_redacted_and_never_mutates_raw_upstox_data() -> None:
    raw_upstox = {
        "price_basis": "RAW",
        "s0_identity": "raw-s0-identity",
        "s20_identity": "raw-s20-identity",
    }

    result = _acquire(_request(), _Provider(_frame()))

    assert isinstance(result, AdjustedDailyCloseSuccess)
    assert raw_upstox == {
        "price_basis": "RAW",
        "s0_identity": "raw-s0-identity",
        "s20_identity": "raw-s20-identity",
    }
    assert serialize_public_result_v1(result) == {
        "code": "SUCCESS",
        "provider_id": "YFINANCE",
        "price_basis": "ADJUSTED",
        "contract_version": "provider-neutral-adjusted-daily-close@v1-mvp",
    }


def test_yfinance_adapter_calls_public_download_and_normalizes_close(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    frame = pd.DataFrame(
        {
            ("Close", "RELIANCE.NS"): [100.5, 101.25],
            ("Open", "RELIANCE.NS"): [99.0, 100.0],
        },
        index=pd.DatetimeIndex(("2024-01-02", "2024-01-03")),
    )
    frame.columns = pd.MultiIndex.from_tuples(frame.columns, names=("Price", "Ticker"))

    def fake_download(**kwargs: object) -> pd.DataFrame:
        calls.append(kwargs)
        return frame

    monkeypatch.setattr(yfinance, "download", fake_download)
    adapter = YfinanceAdjustedDailyDownloadAdapter()
    call = {
        "tickers": ("RELIANCE.NS",),
        "start": "2024-01-02",
        "end": "2024-01-04",
        "interval": "1d",
        "auto_adjust": True,
    }

    assert adapter.download(**call) == {
        "timezone": "Asia/Kolkata",
        "index": (date(2024, 1, 2), date(2024, 1, 3)),
        "close": {"RELIANCE.NS": (100.5, 101.25)},
    }
    assert calls == [call]
