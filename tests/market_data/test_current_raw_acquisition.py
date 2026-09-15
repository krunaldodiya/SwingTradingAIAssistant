"""Focused retained-prerequisite contracts for #188 acquisition planning."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.current_raw_acquisition as acquisition_module
import swing_trading_ai_assistant.market_data.current_raw_acquisition_transport as transport_module
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.current_raw_acquisition import (
    acquire_missing_current_raw_evidence_v1,
)
from swing_trading_ai_assistant.market_data.current_raw_acquisition_transport import (
    StrictCurrentRawResponseV1,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextMemberV1,
    CurrentRawInvocationControlV1,
    CurrentRawPriceContextInputV1,
)
from swing_trading_ai_assistant.market_data.instruments import (
    UPSTOX_NSE_INSTRUMENTS_URL,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleEvidenceStore,
    ScheduleSession,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _request(now: datetime) -> CurrentRawPriceContextInputV1:
    return CurrentRawPriceContextInputV1(
        "a" * 64,
        now,
        now + timedelta(minutes=30),
        "b" * 64,
        (
            CurrentPriceContextMemberV1(
                "INE000A01001",
                "NSE",
                "EQUITY",
                "EQ",
                "ACME",
                date(2020, 1, 1),
                date(2030, 1, 1),
            ),
        ),
    )


def test_missing_calendar_prerequisite_uses_root_and_control_not_callback(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = _request(now)
    result = acquire_missing_current_raw_evidence_v1(
        request,
        tmp_path,
        control=CurrentRawInvocationControlV1(
            _Clock(now), selection=now, deadline=request.admission_deadline
        ),
    )
    assert result.outcome == "CALENDAR_PREREQUISITE_MISSING"
    assert result.provider_calls == 0


def test_missing_mapping_fetches_once_without_constructing_a_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real retained calendar/catalog admits exactly one credential-free fetch."""
    selection = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
    sessions = tuple(
        ScheduleSession(
            date(2026, 9, 1) + timedelta(days=offset),
            datetime(2026, 9, 1, 3, 45, tzinfo=UTC) + timedelta(days=offset),
            datetime(2026, 9, 1, 10, tzinfo=UTC) + timedelta(days=offset),
            "REGULAR",
        )
        for offset in range(31)
    )
    schedule = ExpectedSessionSchedule(
        schema_version=SCHEDULE_SCHEMA_VERSION_V3,
        source="nse-authoritative-calendar",
        source_release=f"sha256:{'a' * 64}",
        as_of=selection,
        timezone="Asia/Kolkata",
        covered_from=sessions[0].trade_date,
        covered_to=sessions[-1].trade_date,
        sessions=sessions,
    )
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.outcome is LeaseOutcome.ACQUIRED
    assert acquired.lease is not None
    try:
        retained = ScheduleEvidenceStore(tmp_path, acquired.lease).retain(schedule)
        assert retained.digest == schedule_digest(schedule)
        with DuckDBCatalog(tmp_path, lease=acquired.lease):
            pass
    finally:
        acquired.lease.close()

    requested: list[tuple[str, dict[str, str]]] = []
    body = gzip.compress(
        json.dumps(
            [
                {
                    "segment": "NSE_EQ",
                    "name": "Acme Limited",
                    "exchange": "NSE",
                    "isin": "INE000A01001",
                    "instrument_type": "EQ",
                    "instrument_key": "NSE_EQ|INE000A01001",
                    "trading_symbol": "ACME",
                }
            ],
            separators=(",", ":"),
        ).encode(),
        mtime=0,
    )

    def strict_get(
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        deadline: datetime,
        now: object,
        maximum_body_bytes: int,
        before_open: object | None = None,
    ) -> StrictCurrentRawResponseV1:
        del timeout_seconds, deadline, now, maximum_body_bytes
        assert callable(before_open)
        before_open()
        requested.append((url, headers.copy()))
        return StrictCurrentRawResponseV1(
            200, url, (("Content-Type", "application/json"),), body
        )

    monkeypatch.setattr(transport_module, "get_strict_current_raw_v1", strict_get)
    request = CurrentRawPriceContextInputV1(
        "a" * 64,
        selection,
        selection + timedelta(minutes=30),
        schedule_digest(schedule),
        (_request(selection).members[0],),
    )
    result = acquire_missing_current_raw_evidence_v1(
        request,
        tmp_path,
        control=CurrentRawInvocationControlV1(
            _Clock(selection), selection=selection, deadline=request.admission_deadline
        ),
    )

    assert result.outcome == "MAPPING_RETAINED"
    assert result.provider_calls == 1
    assert requested == [(UPSTOX_NSE_INSTRUMENTS_URL, {"Accept": "application/json"})]

    second = acquire_missing_current_raw_evidence_v1(
        request,
        tmp_path,
        control=CurrentRawInvocationControlV1(
            _Clock(selection), selection=selection, deadline=request.admission_deadline
        ),
    )

    assert second.outcome == "NOT_ATTEMPTED"
    assert second.provider_calls == 0
    assert requested == [(UPSTOX_NSE_INSTRUMENTS_URL, {"Accept": "application/json"})]


def test_missing_physical_calendar_coverage_stops_before_retained_work_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The selected sessions alone cannot authorize mapping/catalog inspection."""
    selection = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
    sessions = tuple(
        ScheduleSession(
            date(2026, 9, 11) + timedelta(days=offset),
            datetime(2026, 9, 11, 3, 45, tzinfo=UTC) + timedelta(days=offset),
            datetime(2026, 9, 11, 10, tzinfo=UTC) + timedelta(days=offset),
            "REGULAR",
        )
        for offset in range(21)
    )
    schedule = ExpectedSessionSchedule(
        schema_version=SCHEDULE_SCHEMA_VERSION_V3,
        source="nse-authoritative-calendar",
        source_release=f"sha256:{'a' * 64}",
        as_of=selection,
        timezone="Asia/Kolkata",
        covered_from=sessions[0].trade_date,
        covered_to=sessions[-1].trade_date,
        sessions=sessions,
    )
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.outcome is LeaseOutcome.ACQUIRED
    assert acquired.lease is not None
    try:
        retained = ScheduleEvidenceStore(tmp_path, acquired.lease).retain(schedule)
        assert retained.digest == schedule_digest(schedule)
    finally:
        acquired.lease.close()

    def forbidden_retained_work(*args: object, **kwargs: object) -> object:
        raise AssertionError("retained mapping/catalog inspection must not run")

    monkeypatch.setattr(
        acquisition_module,
        "read_retained_current_raw_context_v1",
        forbidden_retained_work,
    )
    request = CurrentRawPriceContextInputV1(
        "a" * 64,
        selection,
        selection + timedelta(minutes=30),
        schedule_digest(schedule),
        (_request(selection).members[0],),
    )
    result = acquire_missing_current_raw_evidence_v1(
        request,
        tmp_path,
        control=CurrentRawInvocationControlV1(
            _Clock(selection),
            selection=selection,
            deadline=selection + timedelta(minutes=30),
        ),
    )

    assert result.outcome == "CALENDAR_PREREQUISITE_MISSING"
    assert result.provider_calls == 0
