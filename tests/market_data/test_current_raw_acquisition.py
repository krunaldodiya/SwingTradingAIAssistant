"""Focused native retained-inspection contracts for #188 acquisition replanning."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request

import pytest

import swing_trading_ai_assistant.market_data.current_raw_acquisition as acquisition_module
import swing_trading_ai_assistant.market_data.current_raw_acquisition_transport as transport_module
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.current_raw_acquisition import (
    acquire_missing_current_raw_evidence_v1,
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


def _member(index: int = 0) -> CurrentPriceContextMemberV1:
    return CurrentPriceContextMemberV1(
        "INE467B01029" if index == 0 else f"INE{index:09d}",
        "NSE",
        "EQUITY",
        "EQ",
        "ACME" if index == 0 else f"ACME{index}",
        date(2020, 1, 1),
        date(2030, 1, 1),
    )


def _request(
    now: datetime, members: tuple[CurrentPriceContextMemberV1, ...] | None = None
) -> CurrentRawPriceContextInputV1:
    return CurrentRawPriceContextInputV1(
        "a" * 64,
        now,
        now + timedelta(minutes=30),
        "b" * 64,
        (_member(),) if members is None else members,
    )


def _sessions(start: date, count: int = 21) -> tuple[ScheduleSession, ...]:
    return tuple(
        ScheduleSession(
            start + timedelta(days=index),
            datetime.combine(start + timedelta(days=index), datetime.min.time(), UTC)
            + timedelta(hours=3, minutes=45),
            datetime.combine(start + timedelta(days=index), datetime.min.time(), UTC)
            + timedelta(hours=10),
            "REGULAR",
        )
        for index in range(count)
    )


def _retain_schedule(root: Path, schedule: ExpectedSessionSchedule) -> None:
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    try:
        assert ScheduleEvidenceStore(root, acquired.lease).retain(
            schedule
        ).digest == schedule_digest(schedule)
        with DuckDBCatalog(root, lease=acquired.lease):
            pass
    finally:
        acquired.lease.close()


def test_exact_physical_preplan_uses_selection_month_and_completed_today_boundary() -> (
    None
):
    selection = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
    plan = acquisition_module._plan_physical_slots_v1(  # pyright: ignore[reportPrivateUsage]
        _request(selection), _sessions(date(2026, 9, 10)), mapping_reusable=False
    )

    assert plan.maximum_calls == 6
    assert [slot.kind for slot in plan.members[0].closed] == ["CLOSED"]
    assert plan.members[0].current_history is None
    assert plan.members[0].intraday is None
    assert plan.members[0].closed[0].disposition.value == "BLOCKED_MAPPING"


def test_completed_today_preplan_reserves_intraday_after_history() -> None:
    selection = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
    plan = acquisition_module._plan_physical_slots_v1(  # pyright: ignore[reportPrivateUsage]
        _request(selection), _sessions(date(2026, 9, 11)), mapping_reusable=False
    )

    assert [slot.kind for slot in plan.members[0].closed] == ["CLOSED"]
    assert plan.members[0].current_history is not None
    assert plan.members[0].intraday is not None
    assert plan.members[0].intraday.disposition.value == "BLOCKED_MAPPING"


def test_ledger_refuses_reusable_nonacquirable_and_duplicate_slots() -> None:
    selection = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
    plan = acquisition_module._plan_physical_slots_v1(  # pyright: ignore[reportPrivateUsage]
        _request(selection), _sessions(date(2026, 9, 10)), mapping_reusable=False
    )
    ledger = acquisition_module._AcquisitionLedgerV1(plan)  # pyright: ignore[reportPrivateUsage]
    ledger.before_open("mapping")
    ledger.member_stop(0, "PROVIDER_REFUSED")

    with pytest.raises(RuntimeError, match="attempt rejected"):
        ledger.before_open("mapping")
    with pytest.raises(RuntimeError, match="attempt rejected"):
        ledger.before_open(plan.members[0].closed[0].key)
    snapshot = ledger.snapshot()
    assert snapshot.total_calls == 1
    assert snapshot.mapping.attempts == 1
    assert all(slot.attempts == 0 for slot in snapshot.members[0])


def test_n50_has_exact_three_month_251_bound_and_n51_is_rejected_before_effects() -> (
    None
):
    selection = datetime(2026, 3, 16, 10, 1, tzinfo=UTC)
    selected = (
        _sessions(date(2026, 1, 10), 7)
        + _sessions(date(2026, 2, 10), 7)
        + _sessions(date(2026, 3, 10), 7)
    )
    members = tuple(_member(index) for index in range(50))
    plan = acquisition_module._plan_physical_slots_v1(  # pyright: ignore[reportPrivateUsage]
        _request(selection, members), selected, mapping_reusable=False
    )

    assert plan.maximum_calls == 251
    assert len(acquisition_module._plan_slots(plan)) == 251  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ValueError, match="input is invalid"):
        _request(selection, members + (_member(50),))


def test_missing_calendar_prerequisite_is_zero_effect(tmp_path: Path) -> None:
    now = datetime(2026, 9, 15, 9, tzinfo=UTC)
    result = acquire_missing_current_raw_evidence_v1(
        _request(now),
        tmp_path,
        control=CurrentRawInvocationControlV1(
            _Clock(now), selection=now, deadline=now + timedelta(minutes=30)
        ),
    )

    assert result.outcome == "CALENDAR_PREREQUISITE_MISSING"
    assert result.provider_calls == 0


def test_missing_mapping_retains_once_then_freshly_replans_with_native_provider_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real store/catalog inspector does not infer raw/action readiness."""
    selection = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
    sessions = _sessions(date(2026, 9, 1), 31)
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
    _retain_schedule(tmp_path, schedule)
    body = gzip.compress(
        json.dumps(
            [
                {
                    "segment": "NSE_EQ",
                    "name": "Acme Limited",
                    "exchange": "NSE",
                    "isin": "INE467B01029",
                    "instrument_type": "EQ",
                    "instrument_key": "NSE_EQ|INE467B01029",
                    "trading_symbol": "ACME",
                }
            ],
            separators=(",", ":"),
        ).encode(),
        mtime=0,
    )
    requested: list[str] = []

    class _Response:
        headers = SimpleNamespace(items=lambda: (("Content-Type", "application/gzip"),))

        def getcode(self) -> int:
            return 200

        def geturl(self) -> str:
            return UPSTOX_NSE_INSTRUMENTS_URL

        def read(self, size: int) -> bytes:
            assert size == 4_000_001
            return body

        def close(self) -> None:
            return None

    class _Opener:
        def open(self, request: Request, *, timeout: float) -> _Response:
            assert timeout > 0
            requested.append(request.full_url)
            return _Response()

    def build_opener(*_handlers: object) -> _Opener:
        return _Opener()

    monkeypatch.setattr(transport_module, "build_opener", build_opener)
    request = _request(selection)
    request = CurrentRawPriceContextInputV1(
        request.request_identity_sha256,
        request.data_selection_time,
        request.admission_deadline,
        schedule_digest(schedule),
        request.members,
    )
    result = acquire_missing_current_raw_evidence_v1(
        request,
        tmp_path,
        control=CurrentRawInvocationControlV1(
            _Clock(selection), selection=selection, deadline=request.admission_deadline
        ),
    )

    assert result.outcome == "STOPPED"
    assert result.provider_calls == 1
    assert requested == [UPSTOX_NSE_INSTRUMENTS_URL]
    assert result.plan is not None
    assert result.plan.members[0].provider_key == "NSE_EQ|INE467B01029"
    assert (
        result.accounting is not None
        and result.accounting.mapping.disposition.value == "RETAINED"
        and result.accounting.members[0][0].disposition.value
        == "NOT_ATTEMPTED_SHARED_STOP"
    )
