"""Focused native retained-inspection contracts for #188 acquisition replanning."""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request

import pytest
from current_raw_acquisition_fixtures import (
    FixtureTokenProvider,
    MutableCancellation,
    MutableClock,
    RecordedWire,
    WireReply,
    action_body,
    conflict_action_snapshot,
    corrupt_action_snapshot,
    current_history_body,
    current_month_request,
    historical_body,
    intraday_body,
    remove_action_metadata,
    seed_root,
    url_error,
)
from current_raw_acquisition_fixtures import control as fixture_control
from current_raw_acquisition_fixtures import members as fixture_members
from current_raw_acquisition_fixtures import schedule as fixture_schedule

import swing_trading_ai_assistant.market_data.current_raw_acquisition as acquisition_module
import swing_trading_ai_assistant.market_data.current_raw_acquisition_transport as transport_module
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.credentials import (
    AccessToken,
    CredentialNotFoundError,
)
from swing_trading_ai_assistant.market_data.current_raw_acquisition import (
    acquire_missing_current_raw_evidence_v1,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextMemberV1,
    CurrentRawInvocationControlV1,
    CurrentRawPriceContextInputV1,
    read_retained_current_raw_context_v1,
    validate_admitted_current_raw_context_v1,
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

_FIXTURE_SELECTION = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _member_isin(index: int) -> str:
    if index == 0:
        return "INE467B01029"
    prefix = f"INE{index:08d}"
    digits = "".join(str(ord(char) - 55) if char.isalpha() else char for char in prefix)
    for check in range(10):
        total = sum(
            value if position % 2 == 0 else (value * 2 - 9 if value > 4 else value * 2)
            for position, value in enumerate(map(int, reversed(digits + str(check))))
        )
        if total % 10 == 0:
            return prefix + str(check)
    raise AssertionError("unreachable ISIN check digit")


def _member(index: int = 0) -> CurrentPriceContextMemberV1:
    return CurrentPriceContextMemberV1(
        _member_isin(index),
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
    assert validate_admitted_current_raw_context_v1(fresh.admitted).members[
        0
    ].state == ("OBSERVED")

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


def _expired_control(
    request: CurrentRawPriceContextInputV1,
) -> CurrentRawInvocationControlV1:
    return CurrentRawInvocationControlV1(
        _Clock(request.data_selection_time),
        selection=request.data_selection_time,
        deadline=request.data_selection_time,
    )


def _cancelled_control(
    request: CurrentRawPriceContextInputV1,
) -> CurrentRawInvocationControlV1:
    cancellation = MutableCancellation()
    cancellation.cancelled = True
    return CurrentRawInvocationControlV1(
        _Clock(request.data_selection_time),
        selection=request.data_selection_time,
        deadline=request.admission_deadline,
        cancellation=cancellation,
    )


@pytest.mark.parametrize(
    "control_factory",
    [_expired_control, _cancelled_control],
    ids=["deadline", "cancellation"],
)
def test_initial_deadline_or_cancellation_is_zero_effect(
    tmp_path: Path,
    control_factory: Callable[
        [CurrentRawPriceContextInputV1], CurrentRawInvocationControlV1
    ],
) -> None:
    request = seed_root(tmp_path / "retained", retained_action=True)
    result = acquire_missing_current_raw_evidence_v1(
        request,
        tmp_path / "retained",
        control=control_factory(request),
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
    member_state = validate_admitted_current_raw_context_v1(retained.admitted).members[
        0
    ]
    assert member_state.state == ("INSUFFICIENT_EVIDENCE" if in_window else "OBSERVED")
    assert member_state.reason == ("ACTION_IN_WINDOW" if in_window else None)

    reused = acquire_missing_current_raw_evidence_v1(
        request, root, control=fixture_control(request)
    )
    assert reused.outcome == "RETAINED_EVIDENCE_READY"
    assert reused.provider_calls == 0
    assert wire.attempts == 1


def _current_root(
    root: Path, *, completed_today: bool
) -> tuple[CurrentRawPriceContextInputV1, ExpectedSessionSchedule]:
    request, schedule = current_month_request(completed_today=completed_today)
    assert seed_root(root, schedule_value=schedule, request_value=request) == request
    return request, schedule


def _current_control(
    request: CurrentRawPriceContextInputV1,
    cancellation: MutableCancellation | None = None,
) -> CurrentRawInvocationControlV1:
    return CurrentRawInvocationControlV1(
        _Clock(request.data_selection_time),
        selection=request.data_selection_time,
        deadline=request.admission_deadline,
        cancellation=cancellation,
    )


@pytest.mark.parametrize(
    "completed_today", [False, True], ids=["history", "history-intraday"]
)
def test_current_month_acquisition_publishes_real_partition_then_reuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, completed_today: bool
) -> None:
    root = tmp_path / "retained"
    request, schedule = _current_root(root, completed_today=completed_today)
    today = request.data_selection_time.date()
    wire = RecordedWire(
        [
            WireReply(
                body=current_history_body(schedule, through=today - timedelta(days=1))
            ),
            *(
                [WireReply(body=intraday_body(schedule, day=today))]
                if completed_today
                else []
            ),
            WireReply(body=action_body()),
        ]
    )
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )

    result = acquire_missing_current_raw_evidence_v1(
        request, root, control=_current_control(request)
    )

    expected_urls = [
        "https://api.upstox.com/v3/historical-candle/"
        "NSE_EQ%7CINE467B01029/minutes/1/2026-09-29/2026-09-01"
    ]
    if completed_today:
        expected_urls.append(
            "https://api.upstox.com/v3/historical-candle/intraday/"
            "NSE_EQ%7CINE467B01029/minutes/1"
        )
    expected_urls.append(
        "https://api.upstox.com/v2/fundamentals/INE467B01029/corporate-actions"
    )
    assert result.outcome == "ACQUISITION_COMPLETED"
    assert result.provider_calls == wire.attempts == len(expected_urls)
    assert FixtureTokenProvider.calls == 1
    assert [item.full_url for item in wire.requests] == expected_urls
    assert all(
        item.get_header("Authorization") == "Bearer fixture-token"
        for item in wire.requests
    )
    assert result.accounting is not None
    member = result.accounting.members[0]
    assert [slot.attempts for slot in member] == (
        [1, 1, 1] if completed_today else [1, 1]
    )
    assert all(slot.disposition.value == "RETAINED" for slot in member if slot.attempts)
    assert "fixture-token" not in repr(result)

    admitted = StorageRootLease.try_admit_read_existing(root)
    assert admitted.lease is not None
    with admitted.lease as lease:
        fresh = read_retained_current_raw_context_v1(
            root, request=request, lease=lease, control=_current_control(request)
        )
    assert fresh.state == "OBSERVED" and fresh.admitted is not None
    assert validate_admitted_current_raw_context_v1(fresh.admitted).members[
        0
    ].state == ("OBSERVED")

    reused = acquire_missing_current_raw_evidence_v1(
        request, root, control=_current_control(request)
    )
    assert reused.outcome == "RETAINED_EVIDENCE_READY"
    assert reused.provider_calls == 0
    assert wire.attempts == len(expected_urls)


@pytest.mark.parametrize(
    "reply",
    [
        WireReply(status=404),
        WireReply(status=408),
        WireReply(status=500),
        url_error(),
        WireReply(body=b"{}", response_url="https://wrong.example/"),
        WireReply(body=b"{}"),
        WireReply(body=b"x" * 1_000_001),
        WireReply(
            body=b"{}",
            headers=(
                ("Content-Type", "application/json"),
                ("Content-Encoding", "gzip"),
            ),
        ),
        WireReply(body=b'{"status":"success","data":{"candles":[]}}'),
    ],
    ids=[
        "404",
        "408",
        "500",
        "network",
        "redirect",
        "bad",
        "oversize",
        "encoded",
        "parser",
    ],
)
def test_current_history_local_refusals_do_not_publish_a_partial_current_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reply: WireReply
) -> None:
    root = tmp_path / "retained"
    request, _schedule = _current_root(root, completed_today=False)
    wire = RecordedWire([reply])
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )

    result = acquire_missing_current_raw_evidence_v1(
        request, root, control=_current_control(request)
    )

    assert result.outcome == "ACQUISITION_BLOCKED"
    assert result.provider_calls == wire.attempts == FixtureTokenProvider.calls == 1
    assert result.accounting is not None
    history, action = result.accounting.members[0]
    assert (history.attempts, history.disposition.value, history.reason) == (
        1,
        "ABORTED_BEFORE_CATALOG_COMMIT",
        "PROVIDER_OR_DATA_FAILURE",
    )
    assert action.attempts == 0
    admitted = StorageRootLease.try_admit_read_existing(root)
    assert admitted.lease is not None
    with admitted.lease as lease:
        fresh = read_retained_current_raw_context_v1(
            root, request=request, lease=lease, control=_current_control(request)
        )
    assert fresh.state == "OBSERVED" and fresh.admitted is not None
    assert (
        validate_admitted_current_raw_context_v1(fresh.admitted).members[0].reason
        == "RAW_PARTITION_CORRUPT"
    )


def test_current_missing_token_and_unsafe_root_stop_before_the_opener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MissingToken:
        def get_access_token(self) -> AccessToken:
            raise CredentialNotFoundError("fixture-token")

    root = tmp_path / "retained"
    request, _schedule = _current_root(root, completed_today=False)
    wire = RecordedWire([WireReply(body=b"{}")])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", MissingToken
    )

    missing_token = acquire_missing_current_raw_evidence_v1(
        request, root, control=_current_control(request)
    )
    assert missing_token.outcome == "STOPPED"
    assert missing_token.provider_calls == wire.attempts == 0
    assert "fixture-token" not in repr(missing_token)

    root.chmod(0o755)
    unsafe_root = acquire_missing_current_raw_evidence_v1(
        request, root, control=_current_control(request)
    )
    assert unsafe_root.outcome == "STOPPED"
    assert unsafe_root.provider_calls == wire.attempts == 0


@pytest.mark.parametrize(
    "stage", ["history", "intraday"], ids=["between", "before-publication"]
)
def test_current_interruption_discards_all_staged_current_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    root = tmp_path / "retained"
    request, schedule = _current_root(root, completed_today=True)
    cancellation = MutableCancellation()
    history = WireReply(
        body=current_history_body(
            schedule, through=request.data_selection_time.date() - timedelta(days=1)
        )
    )
    intraday = WireReply(
        body=intraday_body(schedule, day=request.data_selection_time.date())
    )
    (history if stage == "history" else intraday).on_read = lambda: setattr(
        cancellation, "cancelled", True
    )
    wire = RecordedWire([history, intraday, WireReply(body=action_body())])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )

    result = acquire_missing_current_raw_evidence_v1(
        request, root, control=_current_control(request, cancellation)
    )

    expected_calls = 1 if stage == "history" else 2
    assert result.outcome == "STOPPED"
    assert result.provider_calls == wire.attempts == expected_calls
    assert result.accounting is not None
    slots = result.accounting.members[0]
    assert [slot.disposition.value for slot in slots[:2]] == [
        "ABORTED_BEFORE_CATALOG_COMMIT",
        "NOT_ATTEMPTED_SHARED_STOP"
        if stage == "history"
        else "ABORTED_BEFORE_CATALOG_COMMIT",
    ]
    assert slots[-1].attempts == 0


def test_current_root_replacement_before_publication_stops_without_catalog_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "retained"
    request, schedule = _current_root(root, completed_today=False)
    displaced = tmp_path / "displaced"

    def replace_root() -> None:
        root.rename(displaced)
        root.mkdir(mode=0o700)

    wire = RecordedWire(
        [
            WireReply(
                body=current_history_body(
                    schedule,
                    through=request.data_selection_time.date() - timedelta(days=1),
                ),
                on_read=replace_root,
            )
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )

    result = acquire_missing_current_raw_evidence_v1(
        request, root, control=_current_control(request)
    )

    assert result.outcome == "STOPPED"
    assert result.provider_calls == wire.attempts == 1
    assert result.accounting is not None
    assert (
        result.accounting.members[0][0].disposition.value
        == "ABORTED_BEFORE_CATALOG_COMMIT"
    )
    assert not (root / "market_data.duckdb").exists()
    assert not any(
        path.name == "provisional_partitions" for path in displaced.iterdir()
    )


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (corrupt_action_snapshot, "ACTION_CORRUPT"),
        (conflict_action_snapshot, "ACTION_AMBIGUOUS"),
    ],
    ids=["corrupt", "conflicted"],
)
def test_preexisting_action_defects_are_explicit_and_never_repaired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[Path], None],
    reason: str,
) -> None:
    root = tmp_path / "retained"
    request = seed_root(root, retained_action=True)
    bootstrap = RecordedWire([WireReply(body=historical_body())])
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
    mutate(root)
    wire = RecordedWire([])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)

    result = acquire_missing_current_raw_evidence_v1(
        request, root, control=fixture_control(request)
    )

    assert result.outcome == "ACQUISITION_BLOCKED"
    assert result.provider_calls == wire.attempts == 0
    assert result.plan is not None
    assert result.plan.members[0].action.reason == reason


def _two_member_request() -> CurrentRawPriceContextInputV1:
    return CurrentRawPriceContextInputV1(
        "c" * 64,
        _FIXTURE_SELECTION,
        _FIXTURE_SELECTION + timedelta(minutes=20),
        schedule_digest(fixture_schedule()),
        fixture_members(2),
    )


def test_two_members_continue_after_local_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "retained"
    request = seed_root(root, retained_action=True, request_value=_two_member_request())
    wire = RecordedWire([WireReply(status=404), WireReply(body=historical_body())])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )

    result = acquire_missing_current_raw_evidence_v1(
        request, root, control=fixture_control(request)
    )

    assert result.outcome == "ACQUISITION_PARTIAL"
    assert result.provider_calls == wire.attempts == 2
    assert result.accounting is not None
    first, second = result.accounting.members
    assert first[0].disposition.value == "FAILED"
    assert second[0].disposition.value == "RETAINED"


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        (WireReply(status=401), "AUTHENTICATION_FAILED"),
        (WireReply(status=429), "RATE_LIMITED"),
    ],
)
def test_two_members_shared_provider_stops_prevent_every_later_opener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reply: WireReply, reason: str
) -> None:
    root = tmp_path / "retained"
    request = seed_root(root, retained_action=True, request_value=_two_member_request())
    wire = RecordedWire([reply])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )

    result = acquire_missing_current_raw_evidence_v1(
        request, root, control=fixture_control(request)
    )

    assert result.outcome == "STOPPED"
    assert result.provider_calls == wire.attempts == 1
    assert result.accounting is not None
    assert all(
        slot.reason == reason for member in result.accounting.members for slot in member
    )


@pytest.mark.parametrize("stop", ["deadline", "cancellation"])
def test_two_members_deadline_or_cancellation_stops_before_every_later_opener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop: str
) -> None:
    root = tmp_path / "retained"
    request = seed_root(root, retained_action=True, request_value=_two_member_request())
    clock = MutableClock(request.data_selection_time)
    cancellation = MutableCancellation()

    def stop_after_first_response() -> None:
        if stop == "deadline":
            clock.now_value = request.admission_deadline
        else:
            cancellation.cancelled = True

    wire = RecordedWire(
        [WireReply(body=historical_body(), on_read=stop_after_first_response)]
    )
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    control = CurrentRawInvocationControlV1(
        clock,
        selection=request.data_selection_time,
        deadline=request.admission_deadline,
        cancellation=cancellation,
    )

    result = acquire_missing_current_raw_evidence_v1(request, root, control=control)

    assert result.outcome == "STOPPED"
    assert result.provider_calls == wire.attempts == 1
    assert result.accounting is not None
    assert all(
        slot.attempts == 0
        for member in result.accounting.members[1:]
        for slot in member
    )
