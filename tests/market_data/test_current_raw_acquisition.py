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
from swing_trading_ai_assistant.market_data.credentials import CredentialNotFoundError
from swing_trading_ai_assistant.market_data.current_raw_acquisition import (
    acquire_missing_current_raw_evidence_v1,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextMemberV1,
    CurrentRawInvocationControlV1,
    CurrentRawPriceContextInputV1,
    read_retained_current_raw_context_v1,
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
from tests.market_data.current_raw_acquisition_fixtures import (
    FixtureTokenProvider,
    RecordedWire,
    WireReply,
    action_body,
    historical_body,
    remove_action_metadata,
    seed_root,
    url_error,
)
from tests.market_data.current_raw_acquisition_fixtures import (
    control as fixture_control,
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


def test_closed_month_acquisition_retains_real_partition_and_reuses_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One admitted closed month reaches the native catalog and fresh reader."""
    request = seed_root(tmp_path / "retained", retained_action=True)
    wire = RecordedWire([WireReply(body=historical_body())])
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )

    result = acquire_missing_current_raw_evidence_v1(
        request, tmp_path / "retained", control=fixture_control(request)
    )

    assert result.outcome == "ACQUISITION_COMPLETED"
    assert result.provider_calls == wire.attempts == FixtureTokenProvider.calls == 1
    assert [item.full_url for item in wire.requests] == [
        "https://api.upstox.com/v3/historical-candle/"
        "NSE_EQ%7CINE467B01029/minutes/1/2026-09-30/2026-09-01"
    ]
    assert wire.requests[0].get_header("Authorization") == "Bearer fixture-token"
    assert result.plan is not None
    assert result.plan.members[0].closed[0].disposition.value == "REUSABLE"
    assert result.plan.members[0].action.disposition.value == "REUSABLE"
    assert result.accounting is not None
    assert result.accounting.members[0][0].disposition.value == "RETAINED"
    assert all(slot.attempts == 0 for slot in result.accounting.members[0][1:])
    admitted = StorageRootLease.try_admit_read_existing(tmp_path / "retained")
    assert admitted.lease is not None
    with admitted.lease as lease:
        fresh = read_retained_current_raw_context_v1(
            tmp_path / "retained",
            request=request,
            lease=lease,
            control=fixture_control(request),
        )
    assert fresh.state == "OBSERVED" and fresh.admitted is not None
    assert fresh.admitted.projection.members[0].state == "OBSERVED"

    reused = acquire_missing_current_raw_evidence_v1(
        request, tmp_path / "retained", control=fixture_control(request)
    )
    assert reused.outcome == "RETAINED_EVIDENCE_READY"
    assert reused.provider_calls == 0
    assert wire.attempts == 1


@pytest.mark.parametrize(
    "reply",
    [
        WireReply(status=404),
        WireReply(status=408),
        WireReply(status=500),
        url_error(),
        WireReply(body=historical_body(), response_url="https://wrong.example/"),
        WireReply(body=b"{}"),
    ],
    ids=["404", "408", "500", "network", "redirect", "bad-body"],
)
def test_closed_month_local_provider_refusals_never_retry_or_retain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reply: WireReply
) -> None:
    request = seed_root(tmp_path / "retained", retained_action=True)
    wire = RecordedWire([reply])
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )

    result = acquire_missing_current_raw_evidence_v1(
        request, tmp_path / "retained", control=fixture_control(request)
    )

    assert result.outcome == "ACQUISITION_BLOCKED"
    assert result.provider_calls == wire.attempts == FixtureTokenProvider.calls == 1
    assert result.accounting is not None
    assert result.accounting.members[0][0].disposition.value == "FAILED"
    assert result.accounting.members[0][0].reason == "PROVIDER_OR_DATA_FAILURE"
    assert result.plan is not None
    assert result.plan.members[0].closed[0].disposition.value == "MISSING"


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (401, "AUTHENTICATION_FAILED"),
        (403, "AUTHORIZATION_FAILED"),
        (429, "RATE_LIMITED"),
    ],
)
def test_closed_month_shared_provider_stops_preserve_opened_slot_accounting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    reason: str,
) -> None:
    request = seed_root(tmp_path / "retained", retained_action=True)
    wire = RecordedWire([WireReply(status=status)])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )

    result = acquire_missing_current_raw_evidence_v1(
        request, tmp_path / "retained", control=fixture_control(request)
    )

    assert result.outcome == "STOPPED"
    assert result.provider_calls == wire.attempts == 1
    assert result.accounting is not None
    closed = result.accounting.members[0][0]
    assert (closed.attempts, closed.disposition.value, closed.reason) == (
        1,
        "FAILED",
        reason,
    )
    assert all(slot.reason == reason for slot in result.accounting.members[0][1:])


def test_closed_month_missing_token_stops_before_the_opener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MissingToken:
        def get_access_token(self) -> object:
            raise CredentialNotFoundError("fixture")

    request = seed_root(tmp_path / "retained", retained_action=True)
    wire = RecordedWire([WireReply(body=historical_body())])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", MissingToken
    )

    result = acquire_missing_current_raw_evidence_v1(
        request, tmp_path / "retained", control=fixture_control(request)
    )

    assert result.outcome == "STOPPED"
    assert result.provider_calls == wire.attempts == 0
    assert result.accounting is not None
    assert result.accounting.members[0][0].reason == "AUTHENTICATION_FAILED"


@pytest.mark.parametrize(
    "reply",
    [
        WireReply(status=404),
        WireReply(body=b"x" * 1_048_577),
        WireReply(
            body=action_body(),
            headers=(
                ("Content-Type", "application/json"),
                ("Content-Encoding", "gzip"),
            ),
        ),
    ],
    ids=["404", "oversize", "encoded"],
)
def test_action_local_failures_preserve_admissible_raw_without_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reply: WireReply
) -> None:
    root = tmp_path / "retained"
    request = seed_root(root)
    bootstrap = RecordedWire(
        [WireReply(body=historical_body()), WireReply(body=action_body())]
    )
    monkeypatch.setattr(transport_module, "build_opener", bootstrap.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    assert (
        acquire_missing_current_raw_evidence_v1(
            request, root, control=fixture_control(request)
        ).outcome
        == "ACQUISITION_COMPLETED"
    )
    remove_action_metadata(root)

    wire = RecordedWire([reply])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    result = acquire_missing_current_raw_evidence_v1(
        request, root, control=fixture_control(request)
    )

    assert result.outcome == "ACQUISITION_BLOCKED"
    assert result.provider_calls == wire.attempts == 1
    assert result.accounting is not None
    assert result.accounting.members[0][0].disposition.value == "REUSED"
    assert result.accounting.members[0][-1].disposition.value == "FAILED"


@pytest.mark.parametrize(
    "control_factory",
    [
        lambda request: CurrentRawInvocationControlV1(
            _Clock(request.data_selection_time),
            selection=request.data_selection_time,
            deadline=request.data_selection_time,
        ),
        lambda request: CurrentRawInvocationControlV1(
            _Clock(request.data_selection_time),
            selection=request.data_selection_time,
            deadline=request.admission_deadline,
            cancellation=SimpleNamespace(is_cancelled=lambda: True),
        ),
    ],
    ids=["deadline", "cancellation"],
)
def test_initial_deadline_or_cancellation_is_zero_effect(
    tmp_path: Path, control_factory: object
) -> None:
    request = seed_root(tmp_path / "retained", retained_action=True)
    result = acquire_missing_current_raw_evidence_v1(
        request,
        tmp_path / "retained",
        control=control_factory(request),  # type: ignore[operator]
    )
    assert result.outcome == "STOPPED"
    assert result.provider_calls == 0


@pytest.mark.parametrize(
    ("in_window", "expected_reason", "expected_outcome"),
    [
        (False, None, "ACQUISITION_COMPLETED"),
        (True, "ACTION_IN_WINDOW", "ACQUISITION_COMPLETED"),
    ],
)
def test_action_acquisition_retains_singleton_screen_and_reuses_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    in_window: bool,
    expected_reason: str | None,
    expected_outcome: str,
) -> None:
    """The action GET follows real reusable raw evidence and seals Plan-21 state."""
    root = tmp_path / "retained"
    request = seed_root(root)
    FixtureTokenProvider.calls = 0
    bootstrap = RecordedWire(
        [WireReply(body=historical_body()), WireReply(body=action_body())]
    )
    monkeypatch.setattr(transport_module, "build_opener", bootstrap.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    assert (
        acquire_missing_current_raw_evidence_v1(
            request, root, control=fixture_control(request)
        ).outcome
        == "ACQUISITION_COMPLETED"
    )
    assert bootstrap.attempts == 2
    remove_action_metadata(root)

    wire = RecordedWire([WireReply(body=action_body(in_window=in_window))])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    FixtureTokenProvider.calls = 0
    result = acquire_missing_current_raw_evidence_v1(
        request, root, control=fixture_control(request)
    )

    assert result.provider_calls == wire.attempts == FixtureTokenProvider.calls == 1
    assert [item.full_url for item in wire.requests] == [
        "https://api.upstox.com/v2/fundamentals/INE467B01029/corporate-actions"
    ]
    assert wire.requests[0].get_header("Authorization") == "Bearer fixture-token"
    assert result.plan is not None
    assert result.plan.members[0].action.disposition.value == "REUSABLE"
    assert result.plan.members[0].action.reason == expected_reason
    assert result.outcome == expected_outcome
    assert result.accounting is not None
    assert result.accounting.members[0][-1].disposition.value == "RETAINED"
    assert all(slot.attempts == 0 for slot in result.accounting.members[0][:-1])
    admitted = StorageRootLease.try_admit_read_existing(root)
    assert admitted.lease is not None
    with admitted.lease as lease:
        retained = read_retained_current_raw_context_v1(
            root,
            request=request,
            lease=lease,
            control=fixture_control(request),
        )
    assert retained.state == "OBSERVED" and retained.admitted is not None
    member_state = retained.admitted.projection.members[0]
    assert member_state.state == ("INSUFFICIENT_EVIDENCE" if in_window else "OBSERVED")
    assert member_state.reason == ("SCREEN_UNAVAILABLE" if in_window else None)

    reused = acquire_missing_current_raw_evidence_v1(
        request, root, control=fixture_control(request)
    )
    assert reused.outcome == "RETAINED_EVIDENCE_READY"
    assert reused.provider_calls == 0
    assert wire.attempts == 1
