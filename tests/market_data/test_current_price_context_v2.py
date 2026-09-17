"""Public RED contract tests for Issue #189's one-shot V2 boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import pytest
from current_raw_acquisition_fixtures import (
    FixtureTokenProvider,
    RecordedWire,
    WireReply,
    action_body,
    current_history_body,
    current_month_schedule,
    historical_body,
    mapping_body,
    seed_root,
)
from current_raw_acquisition_fixtures import (
    members as raw_members,
)
from current_raw_acquisition_fixtures import (
    request as raw_request,
)

import swing_trading_ai_assistant.market_data.current_raw_acquisition as acquisition_module
import swing_trading_ai_assistant.market_data.current_raw_acquisition_transport as transport_module
import swing_trading_ai_assistant.research_packet as research_packet
import swing_trading_ai_assistant.research_packet.current_price_context as packet_v1
import swing_trading_ai_assistant.research_packet.current_price_context_v2 as packet_v2
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.cli import build_parser, main
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentRawInvocationControlV1,
    CurrentRawPriceContextInputV1,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    provisional_partition_relative_path,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleSession,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)
from swing_trading_ai_assistant.research_packet.current_price_context import (
    CurrentPriceContextMemberV1,
)
from swing_trading_ai_assistant.research_packet.current_price_context_runtime_identity_manifest import (
    CURRENT_PRICE_CONTEXT_RUNTIME_SOURCE_SHA256_V1,
)

_Mode = Literal["RETAINED_ONLY", "ACQUIRE_MISSING", "REFRESH_ONCE"]

_QUESTIONS = (
    "RAW_MARKET_STRUCTURE",
    "RAW_20_SESSION_DIRECTION",
    "RAW_COHORT_BREADTH",
    "RAW_INDUSTRY_PARTICIPATION",
)


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class _AdvancingClock:
    def __init__(self, value: datetime, step: timedelta, maximum: datetime) -> None:
        self.value = value
        self.step = step
        self.maximum = maximum
        self.observed: list[datetime] = []

    def now(self) -> datetime:
        value = self.value
        self.observed.append(value)
        self.value = min(self.value + self.step, self.maximum)
        return value


def _member() -> CurrentPriceContextMemberV1:
    return CurrentPriceContextMemberV1(
        isin="INE467B01029",
        exchange="NSE",
        instrument_type="EQUITY",
        segment="EQ",
        effective_symbol="TCS",
        valid_from=date(2020, 1, 1),
        valid_through=date(2030, 1, 1),
    )


def _request_value(**updates: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "contract_version": "current-price-context-request@v2",
        "data_selection_time": "2026-09-15T09:00:00.000000Z",
        "admission_deadline": "2026-09-15T09:30:00.000000Z",
        "schedule_identity_sha256": "a" * 64,
        "members": [
            {
                "isin": "INE467B01029",
                "exchange": "NSE",
                "instrument_type": "EQUITY",
                "segment": "EQ",
                "effective_symbol": "TCS",
                "valid_from": "2020-01-01",
                "valid_through": "2030-01-01",
            }
        ],
        "questions": list(_QUESTIONS),
        "industry_archive_reference": None,
        "execution_mode": "RETAINED_ONLY",
        "include_current_session": False,
    }
    value.update(updates)
    return value


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _reseal_result(value: dict[str, Any]) -> bytes:
    without_identity = {
        key: item for key, item in value.items() if key != "result_identity_sha256"
    }
    value["result_identity_sha256"] = hashlib.sha256(
        _canonical(without_identity)
    ).hexdigest()
    return _canonical(value)


def test_v2_request_decoder_is_closed_and_publicly_exported() -> None:
    decoder = packet_v2.current_price_context_request_from_canonical_json_bytes_v2
    request = decoder(_canonical(_request_value()))

    assert request.contract_version == "current-price-context-request@v2"
    assert request.execution_mode == "RETAINED_ONLY"
    assert request.include_current_session is False
    assert request.members == (_member(),)
    assert len(request.canonical_json_bytes()) <= 65_536
    assert research_packet.CurrentPriceContextRequestV2 is type(request)

    with pytest.raises(ValueError, match="request is invalid"):
        decoder(_canonical(_request_value(unknown=True)))
    with pytest.raises(ValueError, match="request is invalid"):
        decoder(_canonical(_request_value(execution_mode="POLL")))
    duplicate = _canonical(_request_value()).replace(
        b'"execution_mode":"RETAINED_ONLY",',
        b'"execution_mode":"RETAINED_ONLY","execution_mode":"RETAINED_ONLY",',
    )
    with pytest.raises(ValueError, match="request is invalid"):
        decoder(duplicate)


@pytest.mark.parametrize(
    ("mode", "include_current_session"),
    (
        ("RETAINED_ONLY", False),
        ("ACQUIRE_MISSING", True),
        ("REFRESH_ONCE", True),
    ),
)
def test_v2_request_accepts_only_the_three_one_shot_modes(
    mode: _Mode, include_current_session: bool
) -> None:
    request = packet_v2.CurrentPriceContextRequestV2(
        contract_version="current-price-context-request@v2",
        data_selection_time=datetime(2026, 9, 15, 9, tzinfo=UTC),
        admission_deadline=datetime(2026, 9, 15, 9, 30, tzinfo=UTC),
        schedule_identity_sha256="a" * 64,
        members=(_member(),),
        questions=_QUESTIONS,
        industry_archive_reference=None,
        execution_mode=mode,
        include_current_session=include_current_session,
    )

    assert request.execution_mode == mode
    assert b"poll" not in request.canonical_json_bytes().lower()
    assert b"stream" not in request.canonical_json_bytes().lower()


def test_v2_retained_only_preserves_completed_result_and_never_opens_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = packet_v2.CurrentPriceContextRequestV2(
        "current-price-context-request@v2",
        selected_at,
        selected_at + timedelta(minutes=30),
        "a" * 64,
        (_member(),),
        _QUESTIONS,
        None,
        "RETAINED_ONLY",
        False,
    )

    def unexpected_provider(*_: object, **__: object) -> object:
        raise AssertionError("retained-only V2 opened a provider")

    monkeypatch.setattr(transport_module, "build_opener", unexpected_provider)
    result = packet_v2.research_current_price_context_v2(
        request, tmp_path / "missing-root", clock=_Clock(selected_at)
    )

    assert result.contract_version == "current-price-context@v2"
    assert result.execution_mode == "RETAINED_ONLY"
    assert result.completed_context.contract_version == "current-price-context@v1"
    assert result.completed_context.members[0].state == "DEPENDENCY_BLOCKED"
    assert result.current_session[0].state == "NOT_REQUESTED"
    assert result.provider_calls_attempted == 0
    assert result.provider_calls_completed == 0
    encoded = result.canonical_json_bytes()
    assert len(encoded) <= 1_048_576
    decoded = packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
        encoded
    )
    assert decoded.canonical_json_bytes() == encoded
    assert research_packet.CurrentPriceContextResultV2 is type(result)
    assert research_packet.CurrentPriceContextFreshnessEntryV2 is type(
        result.freshness_ledger[0]
    )
    assert {entry.source for entry in result.freshness_ledger} == {
        "CALENDAR",
        "MAPPING",
        "CURRENT_SESSION",
        "CORPORATE_ACTION",
        "INDUSTRY",
    }
    assert (
        sum(entry.provider_calls_attempted for entry in result.freshness_ledger)
        == result.provider_calls_attempted
    )
    assert str(tmp_path).encode() not in encoded


def test_v2_acquire_missing_shares_one_mapping_call_for_two_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
    schedule_value = current_month_schedule(selected_at)
    members = raw_members(2)
    request_value = raw_request(schedule_value, selection=selected_at, members=members)
    root = tmp_path / "root"
    seed_root(
        root,
        schedule_value=schedule_value,
        request_value=request_value,
        retain_mapping=False,
    )
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    wire = RecordedWire(
        [
            WireReply(
                body=mapping_body(members),
                headers=(("Content-Type", "application/gzip"),),
            ),
            WireReply(body=historical_body()),
            WireReply(body=historical_body()),
            WireReply(body=action_body()),
            WireReply(body=action_body()),
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)

    result = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "ACQUIRE_MISSING"),
        root,
        clock=_Clock(selected_at),
    )

    mapping_entries = tuple(
        item for item in result.freshness_ledger if item.source == "MAPPING"
    )
    assert wire.attempts == 5
    assert result.provider_call_budget == 5 * len(members) + 1 == 11
    assert result.provider_calls_attempted == result.provider_calls_completed == 5
    assert len(result.freshness_ledger) <= 5 * len(members) + 3
    assert tuple(item.state for item in mapping_entries) == ("ACQUIRED",)
    assert tuple(
        (
            item.position,
            item.isin,
            item.effective_symbol,
            item.provider_calls_attempted,
            item.provider_calls_completed,
        )
        for item in mapping_entries
    ) == ((None, None, None, 1, 1),)
    assert (
        sum(item.provider_calls_attempted for item in result.freshness_ledger)
        == result.provider_calls_attempted
    )
    assert (
        sum(item.provider_calls_completed for item in result.freshness_ledger)
        == result.provider_calls_completed
    )
    assert all(item.state == "OBSERVED" for item in result.completed_context.members)

    moved_mapping_call = json.loads(result.canonical_json_bytes())
    moved_entries = [
        item
        for item in moved_mapping_call["freshness_ledger"]
        if item["source"] == "MAPPING"
    ]
    moved_entries[0].update(
        state="REUSED", provider_calls_attempted=0, provider_calls_completed=0
    )
    with pytest.raises(ValueError, match="result is invalid"):
        packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
            _reseal_result(moved_mapping_call)
        )


def test_v2_result_decoder_rejects_resealed_request_reason_price_and_time_mutations(
    tmp_path: Path,
) -> None:
    selected_at = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = packet_v2.CurrentPriceContextRequestV2(
        "current-price-context-request@v2",
        selected_at,
        selected_at + timedelta(minutes=30),
        "a" * 64,
        (_member(),),
        _QUESTIONS,
        None,
        "RETAINED_ONLY",
        False,
    )
    result = packet_v2.research_current_price_context_v2(
        request, tmp_path / "missing-root", clock=_Clock(selected_at)
    )
    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2

    changed_member = json.loads(result.canonical_json_bytes())
    changed_member["request_members"][0]["effective_symbol"] = "INFY"
    with pytest.raises(ValueError, match="result is invalid"):
        decoder(_reseal_result(changed_member))

    changed_reason = json.loads(result.canonical_json_bytes())
    changed_reason["current_session"][0]["reason"] = "OWNER_FREE_TEXT"
    with pytest.raises(ValueError, match="result is invalid"):
        decoder(_reseal_result(changed_reason))

    changed_price = json.loads(result.canonical_json_bytes())
    provisional = changed_price["current_session"][0]
    provisional.update(
        {
            "state": "OBSERVED",
            "label": "PARTIAL_CURRENT_SESSION",
            "reason": None,
            "last_completed_minute": "2026-09-15T08:59:00.000000Z",
            "observed_price": "1e1000000",
            "cumulative_source_volume": 1,
            "source_version": "upstox-intraday-v3",
            "partition_checksum_sha256": "b" * 64,
            "source_cutoff": "2026-09-15T08:59:00.000000Z",
            "published_at": "2026-09-15T09:00:00.000000Z",
            "known_at": "2026-09-15T09:00:00.000000Z",
        }
    )
    with pytest.raises(ValueError, match="result is invalid"):
        decoder(_reseal_result(changed_price))

    changed_time = json.loads(result.canonical_json_bytes())
    changed_time["freshness_ledger"][0]["known_at"] = "2026-09-15T09:31:00.000000Z"
    with pytest.raises(ValueError, match="result is invalid"):
        decoder(_reseal_result(changed_time))


def test_v2_sdk_cancellation_is_public_sticky_and_normalizes_callback_defects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = packet_v2.CurrentPriceContextRequestV2(
        "current-price-context-request@v2",
        selected_at,
        selected_at + timedelta(minutes=30),
        "a" * 64,
        (_member(),),
        _QUESTIONS,
        None,
        "RETAINED_ONLY",
        False,
    )

    assert (
        research_packet.CurrentRawCancellationV1 is packet_v2.CurrentRawCancellationV1
    )

    class Cancelled:
        def is_cancelled(self) -> bool:
            return True

    class Broken:
        def is_cancelled(self) -> bool:
            raise RuntimeError("callback detail must not escape")

    def unexpected_provider(*_: object, **__: object) -> object:
        raise AssertionError("cancelled V2 opened a provider")

    monkeypatch.setattr(transport_module, "build_opener", unexpected_provider)
    with pytest.raises(packet_v2.CurrentRawInvocationStoppedV1):
        packet_v2.research_current_price_context_v2(
            request,
            tmp_path / "missing-root",
            clock=_Clock(selected_at),
            cancellation=Cancelled(),
        )
    with pytest.raises(ValueError, match="callback is invalid"):
        packet_v2.research_current_price_context_v2(
            request,
            tmp_path / "missing-root",
            clock=_Clock(selected_at),
            cancellation=Broken(),
        )


def test_v2_runtime_manifest_rejects_source_substitution_before_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = packet_v2.CurrentPriceContextRequestV2(
        "current-price-context-request@v2",
        selected_at,
        selected_at + timedelta(minutes=30),
        "a" * 64,
        (_member(),),
        _QUESTIONS,
        None,
        "RETAINED_ONLY",
        False,
    )

    def substituted_hash(*_: object) -> str:
        return "0" * 64

    monkeypatch.setattr(packet_v2, "runtime_source_sha256", substituted_hash)

    with pytest.raises(ValueError, match="runtime identity is invalid"):
        packet_v2.research_current_price_context_v2(
            request, tmp_path / "missing-root", clock=_Clock(selected_at)
        )


def test_price_context_cli_adds_v2_selector_without_changing_v1_default() -> None:
    common = [
        "price-context-current",
        "--input-file",
        "/owner/request.json",
        "--storage-root",
        "/owner/private-root",
        "--output",
        "json",
    ]
    old = build_parser().parse_args(common)
    selected = build_parser().parse_args([*common, "--contract-version", "v2"])

    assert old.contract_version == "v1"
    assert selected.contract_version == "v2"


def test_price_context_cli_emits_the_v2_response_only_when_selected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_bytes(_canonical(_request_value()))
    request_file.chmod(0o600)
    selected_at = datetime(2026, 9, 15, 9, tzinfo=UTC)

    exit_code = main(
        [
            "price-context-current",
            "--input-file",
            str(request_file),
            "--storage-root",
            str(tmp_path / "missing-root"),
            "--contract-version",
            "v2",
            "--output",
            "json",
        ],
        trusted_clock=_Clock(selected_at),
    )

    emitted = capsys.readouterr()
    value = json.loads(emitted.out)
    assert exit_code == 1
    assert emitted.err == ""
    assert value["contract_version"] == "current-price-context@v2"
    assert value["execution_mode"] == "RETAINED_ONLY"
    assert value["completed_context"]["contract_version"] == "current-price-context@v1"


def _active_schedule(selection: datetime) -> ExpectedSessionSchedule:
    value = current_month_schedule(selection)
    sessions = tuple(
        replace(
            item,
            close_at=item.close_at + timedelta(minutes=3),
            kind="SPECIAL",
        )
        if item.trade_date == date(2026, 9, 30)
        else item
        for item in value.sessions
    )
    return replace(value, sessions=sessions)


def _active_raw_request(
    schedule_value: ExpectedSessionSchedule, selection: datetime
) -> CurrentRawPriceContextInputV1:
    return raw_request(schedule_value, selection=selection)


def _v2_from_raw(
    value: CurrentRawPriceContextInputV1,
    mode: _Mode,
) -> packet_v2.CurrentPriceContextRequestV2:
    return packet_v2.CurrentPriceContextRequestV2(
        "current-price-context-request@v2",
        value.data_selection_time,
        value.admission_deadline,
        value.schedule_identity_sha256,
        value.members,
        _QUESTIONS,
        None,
        mode,
        True,
    )


def _intraday_payload(day: date, closes: tuple[float, ...]) -> bytes:
    start = datetime(day.year, day.month, day.day, 3, 45, tzinfo=UTC)
    candles = [
        [
            (start + timedelta(minutes=offset)).isoformat(),
            close,
            close + 1,
            close - 1,
            close,
            10,
            None,
        ]
        for offset, close in enumerate(closes)
    ]
    return json.dumps({"status": "success", "data": {"candles": candles}}).encode()


def test_v2_refresh_once_appends_full_minutes_and_refuses_changed_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_selection = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(first_selection)
    first_raw = _active_raw_request(schedule_value, first_selection)
    root = tmp_path / "root"
    seed_root(
        root,
        schedule_value=schedule_value,
        request_value=first_raw,
    )
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    first_wire = RecordedWire(
        [
            WireReply(
                body=current_history_body(schedule_value, through=date(2026, 9, 29))
            ),
            WireReply(body=action_body()),
            WireReply(body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0, 102.0))),
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", first_wire.build_opener)

    first = packet_v2.research_current_price_context_v2(
        _v2_from_raw(first_raw, "ACQUIRE_MISSING"),
        root,
        clock=_Clock(first_selection),
    )

    assert (
        next(
            item
            for item in schedule_value.sessions
            if item.trade_date == date(2026, 9, 30)
        ).kind
        == "SPECIAL"
    )
    assert first_wire.attempts == 3
    assert first.provider_calls_attempted == 3
    assert first.current_session[0].state == "OBSERVED"
    assert first.current_session[0].last_completed_minute == datetime(
        2026, 9, 30, 3, 46, tzinfo=UTC
    )
    assert first.current_session[0].observed_price == "101.0"
    assert first.current_session[0].cumulative_source_volume == 20
    assert (
        next(
            item for item in first.freshness_ledger if item.source == "CURRENT_SESSION"
        ).state
        == "ACQUIRED"
    )

    refresh_selection = datetime(2026, 9, 30, 3, 48, 30, tzinfo=UTC)
    refresh_raw = _active_raw_request(schedule_value, refresh_selection)
    refresh_wire = RecordedWire(
        [
            WireReply(
                body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0, 102.0, 103.0))
            )
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", refresh_wire.build_opener)
    refreshed = packet_v2.research_current_price_context_v2(
        _v2_from_raw(refresh_raw, "REFRESH_ONCE"),
        root,
        clock=_Clock(refresh_selection),
    )

    assert refresh_wire.attempts == 1
    assert refreshed.refreshed_physical_objects == 1
    assert refreshed.current_session[0].state == "OBSERVED"
    assert refreshed.current_session[0].last_completed_minute == datetime(
        2026, 9, 30, 3, 47, tzinfo=UTC
    )
    assert refreshed.current_session[0].observed_price == "102.0"
    assert refreshed.current_session[0].cumulative_source_volume == 30
    assert (
        next(
            item
            for item in refreshed.freshness_ledger
            if item.source == "CURRENT_SESSION"
        ).state
        == "APPENDED"
    )
    retained_checksum = refreshed.current_session[0].partition_checksum_sha256

    identical_wire = RecordedWire(
        [
            WireReply(
                body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0, 102.0, 103.0))
            )
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", identical_wire.build_opener)
    identical = packet_v2.research_current_price_context_v2(
        _v2_from_raw(refresh_raw, "REFRESH_ONCE"),
        root,
        clock=_Clock(refresh_selection),
    )

    assert identical_wire.attempts == 1
    assert (
        identical.current_session[0].source_cutoff
        == refreshed.current_session[0].source_cutoff
    )
    assert (
        next(
            item
            for item in identical.freshness_ledger
            if item.source == "CURRENT_SESSION"
        ).state
        == "REFRESHED"
    )

    conflict_wire = RecordedWire(
        [
            WireReply(
                body=_intraday_payload(date(2026, 9, 30), (99.0, 101.0, 102.0, 103.0))
            )
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", conflict_wire.build_opener)
    conflicted = packet_v2.research_current_price_context_v2(
        _v2_from_raw(refresh_raw, "REFRESH_ONCE"),
        root,
        clock=_Clock(refresh_selection),
    )

    assert conflict_wire.attempts == 1
    assert conflicted.completed_context.members[0].state == "OBSERVED"
    assert conflicted.current_session[0].state == "CONFLICTED"
    assert conflicted.current_session[0].reason == "PROVISIONAL_EVIDENCE_CONFLICTED"
    assert conflicted.current_session[0].observed_price is None
    assert (
        next(
            item
            for item in conflicted.freshness_ledger
            if item.source == "CURRENT_SESSION"
        ).state
        == "CONFLICTED"
    )

    retained_wire = RecordedWire([])
    monkeypatch.setattr(transport_module, "build_opener", retained_wire.build_opener)
    retained = packet_v2.research_current_price_context_v2(
        _v2_from_raw(refresh_raw, "RETAINED_ONLY"),
        root,
        clock=_Clock(refresh_selection),
    )
    assert retained_wire.attempts == 0
    assert retained.current_session[0].state == "OBSERVED"
    assert retained.current_session[0].partition_checksum_sha256 == retained_checksum
    assert schedule_digest(schedule_value) == refresh_raw.schedule_identity_sha256


def test_v2_advancing_clock_keeps_current_session_target_selection_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    request_value = _active_raw_request(schedule_value, selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    wire = RecordedWire(
        [
            WireReply(
                body=current_history_body(schedule_value, through=date(2026, 9, 29))
            ),
            WireReply(body=action_body()),
            WireReply(body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0, 102.0))),
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    clock = _AdvancingClock(
        selected_at, timedelta(seconds=5), selected_at + timedelta(minutes=2)
    )

    result = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "ACQUIRE_MISSING"), root, clock=clock
    )

    target = datetime(2026, 9, 30, 3, 46, tzinfo=UTC)
    current = result.current_session[0]
    ledger = next(
        item for item in result.freshness_ledger if item.source == "CURRENT_SESSION"
    )
    assert wire.attempts == result.provider_calls_attempted == 3
    assert wire.requests[-1].full_url.endswith("/NSE_EQ%7CINE467B01029/minutes/1")
    assert clock.observed[-1] - clock.observed[0] >= timedelta(minutes=1)
    assert max(clock.observed) < request_value.admission_deadline
    assert result.acquisition_started_at is not None
    assert result.acquisition_completed_at is not None
    assert result.inspection_time < result.acquisition_started_at
    assert result.acquisition_started_at <= result.acquisition_completed_at
    assert result.acquisition_completed_at <= result.evidence_cutoff
    assert result.evidence_cutoff < request_value.admission_deadline
    assert current.last_completed_minute == target
    assert current.observed_price == "101.0"
    assert current.source_cutoff == target
    assert ledger.source_cutoff == target
    assert current.known_at is not None
    assert current.known_at <= result.evidence_cutoff


@pytest.mark.parametrize(
    ("action_reply", "member_reason", "action_state", "completed_calls"),
    (
        (WireReply(status=404), "SCREEN_UNAVAILABLE", "UNAVAILABLE", 6),
        (
            WireReply(body=action_body(in_window=True)),
            "ACTION_IN_WINDOW",
            "ACQUIRED",
            6,
        ),
    ),
    ids=("action-acquisition-fails-locally", "action-observed"),
)
def test_v2_action_non_admission_preserves_provisional_and_truthful_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action_reply: WireReply,
    member_reason: str,
    action_state: str,
    completed_calls: int,
) -> None:
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    request_value = raw_request(
        schedule_value, selection=selected_at, members=raw_members(2)
    )
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    wire = RecordedWire(
        [
            WireReply(
                body=current_history_body(schedule_value, through=date(2026, 9, 29))
            ),
            WireReply(
                body=current_history_body(schedule_value, through=date(2026, 9, 29))
            ),
            action_reply,
            WireReply(body=action_body()),
            WireReply(body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0))),
            WireReply(body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0))),
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)

    result = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "ACQUIRE_MISSING"),
        root,
        clock=_Clock(selected_at),
    )

    completed = result.completed_context.members[0]
    partition = next(
        item
        for item in result.freshness_ledger
        if item.source == "CURRENT_HISTORY" and item.position == 0
    )
    action = next(
        item
        for item in result.freshness_ledger
        if item.source == "CORPORATE_ACTION" and item.position == 0
    )
    provisional = next(
        item
        for item in result.freshness_ledger
        if item.source == "CURRENT_SESSION" and item.position == 0
    )

    assert completed.state == "INSUFFICIENT_EVIDENCE"
    assert completed.reason == member_reason
    assert completed.partition_checksums == ()
    assert completed.raw_source_times == ()
    assert result.current_session[0].state == "OBSERVED"
    assert result.current_session[0].last_completed_minute == datetime(
        2026, 9, 30, 3, 46, tzinfo=UTC
    )
    assert partition.state == "UNAVAILABLE"
    assert partition.physical_identity_sha256 is None
    assert partition.source_cutoff is None
    assert (partition.provider_calls_attempted, partition.provider_calls_completed) == (
        1,
        1,
    )
    assert action.state == action_state
    assert (action.provider_calls_attempted, action.provider_calls_completed) == (1, 1)
    assert provisional.state == "ACQUIRED"
    assert provisional.physical_identity_sha256 is not None
    assert (
        provisional.provider_calls_attempted,
        provisional.provider_calls_completed,
    ) == (
        1,
        1,
    )
    other_completed = result.completed_context.members[1]
    other_partition = next(
        item
        for item in result.freshness_ledger
        if item.source == "CURRENT_HISTORY" and item.position == 1
    )
    assert other_completed.state == "OBSERVED"
    assert other_partition.state == "ACQUIRED"
    assert (
        other_partition.physical_identity_sha256 in other_completed.partition_checksums
    )
    assert result.current_session[1].state == "OBSERVED"
    assert wire.attempts == 6
    assert wire.replies == []
    assert result.provider_calls_attempted == 6
    assert result.provider_calls_completed == completed_calls
    assert (
        sum(item.provider_calls_attempted for item in result.freshness_ledger)
        == result.provider_calls_attempted
    )
    assert (
        sum(item.provider_calls_completed for item in result.freshness_ledger)
        == result.provider_calls_completed
    )


@pytest.mark.parametrize(
    ("selected_at", "expected_state", "expected_reason"),
    (
        (
            datetime(2026, 9, 30, 3, 44, 59, tzinfo=UTC),
            "NOT_APPLICABLE",
            "CURRENT_SESSION_NOT_APPLICABLE",
        ),
        (
            datetime(2026, 9, 30, 3, 45, 30, tzinfo=UTC),
            "UNAVAILABLE",
            "NO_FULLY_COMPLETED_MINUTE",
        ),
        (
            datetime(2026, 9, 26, 9, 0, tzinfo=UTC),
            "NOT_APPLICABLE",
            "CURRENT_SESSION_NOT_APPLICABLE",
        ),
    ),
    ids=("pre-open", "before-first-full-minute", "weekend"),
)
def test_v2_retained_schedule_boundaries_never_open_intraday(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selected_at: datetime,
    expected_state: str,
    expected_reason: str,
) -> None:
    full_schedule = current_month_schedule(
        max(selected_at, datetime(2026, 9, 30, 3, 45, tzinfo=UTC))
    )
    selection_date = selected_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
    schedule_value = replace(
        full_schedule,
        as_of=selected_at,
        covered_to=selection_date,
        sessions=tuple(
            item for item in full_schedule.sessions if item.trade_date <= selection_date
        ),
        closures=tuple(
            item for item in full_schedule.closures if item.trade_date <= selection_date
        ),
    )
    request_value = raw_request(schedule_value, selection=selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    sentinel = RecordedWire([])
    monkeypatch.setattr(transport_module, "build_opener", sentinel.build_opener)

    result = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "RETAINED_ONLY"),
        root,
        clock=_Clock(selected_at),
    )

    assert sentinel.attempts == 0
    assert result.completed_context.contract_version == "current-price-context@v1"
    assert result.current_session[0].state == expected_state
    assert result.current_session[0].reason == expected_reason
    assert result.current_session[0].last_completed_minute is None


@pytest.mark.parametrize(
    "offset",
    (timedelta(0), timedelta(microseconds=1)),
    ids=("exact-close", "close-plus-epsilon"),
)
def test_v2_exact_close_uses_only_v1_completed_session_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offset: timedelta,
) -> None:
    close_at = datetime(2026, 9, 30, 3, 49, tzinfo=UTC)
    selected_at = close_at + offset
    schedule_value = _active_schedule(selected_at)
    request_value = raw_request(schedule_value, selection=selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    bootstrap = RecordedWire(
        [
            WireReply(
                body=current_history_body(schedule_value, through=date(2026, 9, 29))
            ),
            WireReply(
                body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0, 102.0, 103.0))
            ),
            WireReply(body=action_body()),
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", bootstrap.build_opener)
    control = CurrentRawInvocationControlV1(
        _Clock(selected_at),
        selection=request_value.data_selection_time,
        deadline=request_value.admission_deadline,
    )
    completed = acquisition_module.acquire_missing_current_raw_evidence_v1(
        request_value, root, control=control
    )
    assert completed.outcome == "ACQUISITION_COMPLETED"
    assert bootstrap.attempts == 3

    sentinel = RecordedWire([])
    monkeypatch.setattr(transport_module, "build_opener", sentinel.build_opener)
    result = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "REFRESH_ONCE"),
        root,
        clock=_Clock(selected_at),
    )

    assert sentinel.attempts == 0
    assert result.completed_context.members[0].state == "OBSERVED"
    assert result.current_session[0].state == "NOT_APPLICABLE"
    assert result.current_session[0].reason == "CURRENT_SESSION_NOT_APPLICABLE"
    assert result.provider_calls_attempted == 0


def _cross_month_active_schedule(selection: datetime) -> ExpectedSessionSchedule:
    first = date(2026, 8, 1)
    last = date(2026, 10, 1)
    holidays = {date(2026, 9, 1), date(2026, 9, 2)}
    days = tuple(
        first + timedelta(days=offset) for offset in range((last - first).days + 1)
    )
    sessions = tuple(
        ScheduleSession(
            day,
            datetime(day.year, day.month, day.day, 3, 45, tzinfo=UTC),
            datetime(
                day.year, day.month, day.day, 3, 49 if day == last else 46, tzinfo=UTC
            ),
            "SPECIAL" if day == last else "REGULAR",
        )
        for day in days
        if day.weekday() < 5 and day not in holidays
    )
    closures = tuple(
        ScheduleClosure(day, "HOLIDAY" if day in holidays else "WEEKEND")
        for day in days
        if day.weekday() >= 5 or day in holidays
    )
    return ExpectedSessionSchedule(
        SCHEDULE_SCHEMA_VERSION_V3,
        "nse-authoritative-calendar",
        "sha256:" + "b" * 64,
        selection,
        "Asia/Kolkata",
        first,
        last,
        sessions,
        closures,
    )


def test_v2_cross_month_ledger_uses_completed_plan_partition_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 10, 1, 3, 47, 30, tzinfo=UTC)
    schedule_value = _cross_month_active_schedule(selected_at)
    request_value = raw_request(schedule_value, selection=selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    august = tuple(
        item for item in schedule_value.sessions if item.trade_date.month == 8
    )
    september = tuple(
        item for item in schedule_value.sessions if item.trade_date.month == 9
    )
    wire = RecordedWire(
        [
            WireReply(body=historical_body(august)),
            WireReply(body=historical_body(september)),
            WireReply(body=action_body()),
            WireReply(body=_intraday_payload(date(2026, 10, 1), (100.0, 101.0))),
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)

    result = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "ACQUIRE_MISSING"),
        root,
        clock=_Clock(selected_at),
    )

    completed_member = result.completed_context.members[0]
    completed_partitions = tuple(
        item
        for item in result.freshness_ledger
        if item.source in {"CLOSED_MONTH", "CURRENT_HISTORY"}
    )
    assert wire.attempts == 4
    assert completed_member.state == "OBSERVED"
    assert len(completed_member.partition_checksums) == 2
    assert tuple(item.physical_identity_sha256 for item in completed_partitions) == (
        completed_member.partition_checksums
    )
    assert tuple(item.source_cutoff for item in completed_partitions) == (
        completed_member.raw_source_times
    )
    assert [item.slot for item in completed_partitions] == ["2026-08", "2026-09"]
    assert (
        sum(item.source == "CURRENT_SESSION" for item in result.freshness_ledger) == 1
    )

    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2
    encoded = result.canonical_json_bytes()

    def value() -> dict[str, Any]:
        return json.loads(encoded)

    malformed: list[dict[str, Any]] = []

    changed_closed_digest = value()
    changed_closed_digest["freshness_ledger"][2]["physical_identity_sha256"] = "f" * 64
    malformed.append(changed_closed_digest)

    changed_closed_clock = value()
    changed_closed_clock["freshness_ledger"][2]["source_cutoff"] = (
        "2026-09-30T03:45:00.000000Z"
    )
    malformed.append(changed_closed_clock)

    changed_calendar_identity = value()
    changed_calendar_identity["freshness_ledger"][0]["physical_identity_sha256"] = (
        "f" * 64
    )
    malformed.append(changed_calendar_identity)

    changed_calendar_state = value()
    changed_calendar_state["freshness_ledger"][0]["state"] = "UNAVAILABLE"
    malformed.append(changed_calendar_state)

    industry_index = len(result.freshness_ledger) - 1
    changed_industry_identity = value()
    changed_industry_identity["freshness_ledger"][industry_index][
        "physical_identity_sha256"
    ] = "f" * 64
    malformed.append(changed_industry_identity)

    changed_industry_state = value()
    changed_industry_state["freshness_ledger"][industry_index]["state"] = "UNAVAILABLE"
    malformed.append(changed_industry_state)

    changed_industry_clock = value()
    changed_industry_clock["freshness_ledger"][industry_index]["known_at"] = (
        "2026-10-01T03:47:30.000000Z"
    )
    malformed.append(changed_industry_clock)

    missing_partition = value()
    del missing_partition["freshness_ledger"][2]
    malformed.append(missing_partition)

    duplicate_partition = value()
    duplicate = dict(duplicate_partition["freshness_ledger"][2])
    duplicate["slot"] = "2026-07"
    duplicate_partition["freshness_ledger"].insert(2, duplicate)
    malformed.append(duplicate_partition)

    reordered_partitions = value()
    ledger = reordered_partitions["freshness_ledger"]
    ledger[2], ledger[3] = ledger[3], ledger[2]
    malformed.append(reordered_partitions)

    resealed_source = value()
    resealed_source["freshness_ledger"][2].update(
        source="CURRENT_HISTORY",
        correction_rule="CURRENT_MONTH_IDENTICAL_OVERLAP_OR_INTRADAY_TO_HISTORICAL_FINALIZATION",
    )
    malformed.append(resealed_source)

    resealed_slot = value()
    resealed_slot["freshness_ledger"][2]["slot"] = "2026-06"
    malformed.append(resealed_slot)

    for index, mutated in enumerate(malformed):
        try:
            decoder(_reseal_result(mutated))
        except ValueError as error:
            assert "result is invalid" in str(error)
        else:
            pytest.fail(f"resealed ledger mutation {index} was accepted")


def test_v2_alias_only_reuses_canonical_provisional_but_identity_drift_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    old_member = _member()
    alias_member = replace(old_member, effective_symbol="TCSNEW")
    first_raw = raw_request(
        schedule_value, selection=selected_at, members=(old_member,)
    )
    root = tmp_path / "root"
    seed_root(
        root,
        schedule_value=schedule_value,
        request_value=first_raw,
        mapping_members=(old_member, alias_member),
    )
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    first_wire = RecordedWire(
        [
            WireReply(
                body=current_history_body(schedule_value, through=date(2026, 9, 29))
            ),
            WireReply(body=action_body()),
            WireReply(body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0))),
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", first_wire.build_opener)
    first = packet_v2.research_current_price_context_v2(
        _v2_from_raw(first_raw, "ACQUIRE_MISSING"),
        root,
        clock=_Clock(selected_at),
    )
    old_checksum = first.current_session[0].partition_checksum_sha256
    assert first.current_session[0].state == "OBSERVED"

    alias_raw = raw_request(
        schedule_value, selection=selected_at, members=(alias_member,)
    )
    sentinel = RecordedWire([])
    monkeypatch.setattr(transport_module, "build_opener", sentinel.build_opener)
    alias = packet_v2.research_current_price_context_v2(
        _v2_from_raw(alias_raw, "RETAINED_ONLY"),
        root,
        clock=_Clock(selected_at),
    )

    assert sentinel.attempts == 0
    assert alias.completed_context.members[0].state == "OBSERVED"
    assert alias.current_session[0].state == "OBSERVED"
    assert alias.current_session[0].effective_symbol == "TCSNEW"
    assert alias.current_session[0].partition_checksum_sha256 == old_checksum

    def unexpected_symbol_lookup(*_: object, **__: object) -> object:
        raise AssertionError(
            "refresh selected the current symbol instead of security ID"
        )

    monkeypatch.setattr(
        acquisition_module.DuckDBCatalog,
        "latest_provisional_partition_for_symbol",
        unexpected_symbol_lookup,
    )
    refresh_wire = RecordedWire(
        [WireReply(body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0)))]
    )
    monkeypatch.setattr(transport_module, "build_opener", refresh_wire.build_opener)
    alias_refresh = packet_v2.research_current_price_context_v2(
        _v2_from_raw(alias_raw, "REFRESH_ONCE"),
        root,
        clock=_Clock(selected_at),
    )
    assert refresh_wire.attempts == 1
    assert alias_refresh.current_session[0].state == "OBSERVED"
    assert alias_refresh.current_session[0].partition_checksum_sha256 == old_checksum
    assert (
        next(
            item
            for item in alias_refresh.freshness_ledger
            if item.source == "CURRENT_SESSION"
        ).state
        == "REFRESHED"
    )

    original_lookup = (
        packet_v2.DuckDBCatalog.latest_provisional_partition_for_security_id
    )

    def mismatched_provider_key(
        catalog: packet_v2.DuckDBCatalog, **query: object
    ) -> object:
        metadata = original_lookup(catalog, **query)  # type: ignore[arg-type]
        if metadata is None:
            return None
        wrong_plan = replace(metadata.plan, instrument_key="NSE_EQ|DIFFERENT")
        return replace(
            metadata,
            instrument_key=wrong_plan.instrument_key,
            relative_path=provisional_partition_relative_path(
                wrong_plan,
                metadata.cutoff,
                metadata.schedule_digest_sha256,
                metadata.checksum_sha256,
            ),
        )

    monkeypatch.setattr(
        packet_v2.DuckDBCatalog,
        "latest_provisional_partition_for_security_id",
        mismatched_provider_key,
    )
    wrong_provider = packet_v2.research_current_price_context_v2(
        _v2_from_raw(alias_raw, "RETAINED_ONLY"),
        root,
        clock=_Clock(selected_at),
    )
    assert wrong_provider.completed_context.members[0].state != "OBSERVED"
    assert wrong_provider.current_session[0].state == "CONFLICTED"
    monkeypatch.setattr(
        packet_v2.DuckDBCatalog,
        "latest_provisional_partition_for_security_id",
        original_lookup,
    )

    drift_member = replace(alias_member, isin="INE467B01037")
    drift_raw = raw_request(
        schedule_value, selection=selected_at, members=(drift_member,)
    )
    drift = packet_v2.research_current_price_context_v2(
        _v2_from_raw(drift_raw, "RETAINED_ONLY"),
        root,
        clock=_Clock(selected_at),
    )

    assert sentinel.attempts == 0
    assert drift.completed_context.members[0].state != "OBSERVED"
    assert drift.current_session[0].state != "OBSERVED"


def test_v2_competing_schedule_provisional_remains_unadmitted_and_unmodified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    request_value = _active_raw_request(schedule_value, selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    initial_wire = RecordedWire(
        [
            WireReply(
                body=current_history_body(schedule_value, through=date(2026, 9, 29))
            ),
            WireReply(body=action_body()),
            WireReply(body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0))),
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", initial_wire.build_opener)
    initial = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "ACQUIRE_MISSING"),
        root,
        clock=_Clock(selected_at),
    )
    expected_schedule = schedule_digest(schedule_value)
    wrong_schedule = "f" * 64
    identity = StorageRootLease.admit_existing_private_identity(root)
    assert identity is not None
    acquired = StorageRootLease.try_acquire_existing_identity(root, identity)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    try:
        with DuckDBCatalog(root, lease=acquired.lease) as catalog:
            current = catalog.latest_provisional_partition_for_security_id(
                segment="NSE_EQ",
                security_id=request_value.members[0].isin,
                year=2026,
                month=9,
                cutoff_lte=request_value.admission_deadline,
                published_at_lte=request_value.admission_deadline,
                schedule_digest_sha256=expected_schedule,
            )
            assert current is not None
            competing = replace(
                current,
                schedule_digest_sha256=wrong_schedule,
                relative_path=provisional_partition_relative_path(
                    current.plan,
                    current.cutoff,
                    wrong_schedule,
                    current.checksum_sha256,
                ),
            )
            competing_path = root / competing.relative_path
            competing_path.parent.mkdir(parents=True, exist_ok=True)
            competing_path.write_bytes((root / current.relative_path).read_bytes())
            catalog.save_provisional_partition(competing)
            assert (
                catalog.latest_provisional_partition_for_security_id(
                    segment="NSE_EQ",
                    security_id=request_value.members[0].isin,
                    year=2026,
                    month=9,
                    cutoff_lte=request_value.admission_deadline,
                    published_at_lte=request_value.admission_deadline,
                    schedule_digest_sha256=wrong_schedule,
                )
                == competing
            )
            before = catalog.list_provisional_partitions(current.plan)
    finally:
        acquired.lease.close()

    retained_wire = RecordedWire([])
    monkeypatch.setattr(transport_module, "build_opener", retained_wire.build_opener)
    retained = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "RETAINED_ONLY"),
        root,
        clock=_Clock(selected_at),
    )
    assert retained_wire.attempts == 0
    assert retained.current_session[0].state == "OBSERVED"
    assert (
        retained.current_session[0].partition_checksum_sha256
        == initial.current_session[0].partition_checksum_sha256
    )

    refresh_wire = RecordedWire(
        [WireReply(body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0)))]
    )
    monkeypatch.setattr(transport_module, "build_opener", refresh_wire.build_opener)
    refreshed = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "REFRESH_ONCE"),
        root,
        clock=_Clock(selected_at),
    )
    assert refresh_wire.attempts == 1
    assert refreshed.current_session[0].state == "OBSERVED"
    assert (
        refreshed.current_session[0].partition_checksum_sha256
        == initial.current_session[0].partition_checksum_sha256
    )

    identity = StorageRootLease.admit_existing_private_identity(root)
    assert identity is not None
    acquired = StorageRootLease.try_acquire_existing_identity(root, identity)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    try:
        with DuckDBCatalog(root, lease=acquired.lease) as catalog:
            assert catalog.list_provisional_partitions(current.plan) == before
            assert (
                catalog.latest_provisional_partition_for_security_id(
                    segment="NSE_EQ",
                    security_id=request_value.members[0].isin,
                    year=2026,
                    month=9,
                    cutoff_lte=request_value.admission_deadline,
                    published_at_lte=request_value.admission_deadline,
                    schedule_digest_sha256=wrong_schedule,
                )
                == competing
            )
    finally:
        acquired.lease.close()


def test_v2_rejects_omitted_v1_runtime_source_before_acquisition_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
    schedule_value = current_month_schedule(selected_at)
    members = raw_members(1)
    request_value = raw_request(schedule_value, selection=selected_at, members=members)
    root = tmp_path / "root"
    seed_root(
        root,
        schedule_value=schedule_value,
        request_value=request_value,
        retain_mapping=False,
    )
    wire = RecordedWire(
        [
            WireReply(
                body=mapping_body(members),
                headers=(("Content-Type", "application/gzip"),),
            )
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)

    def substituted_hash(*args: object) -> str:
        relative = args[-1]
        assert isinstance(relative, str)
        if relative.endswith("corporate_actions.py"):
            return "0" * 64
        return CURRENT_PRICE_CONTEXT_RUNTIME_SOURCE_SHA256_V1[relative]

    monkeypatch.setattr(packet_v1, "runtime_source_sha256", substituted_hash)

    with pytest.raises(ValueError, match="runtime identity is invalid"):
        packet_v2.research_current_price_context_v2(
            _v2_from_raw(request_value, "ACQUIRE_MISSING"),
            root,
            clock=_Clock(selected_at),
        )
    assert wire.attempts == 0


def test_v2_result_requires_an_exact_ordered_physical_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
    schedule_value = current_month_schedule(selected_at)
    request_value = raw_request(schedule_value, selection=selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    result = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "RETAINED_ONLY"), root, clock=_Clock(selected_at)
    )
    value = json.loads(result.canonical_json_bytes())

    assert value["physical_plan"] == [
        {
            "source": item.source,
            "slot": item.slot,
            "position": item.position,
        }
        for item in result.freshness_ledger
    ]

    del value["physical_plan"][1]
    with pytest.raises(ValueError, match="result is invalid"):
        packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
            _reseal_result(value)
        )


def test_v2_latches_transient_cancellation_across_inner_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = packet_v2.CurrentPriceContextRequestV2(
        "current-price-context-request@v2",
        selected_at,
        selected_at + timedelta(minutes=30),
        "a" * 64,
        (_member(),),
        _QUESTIONS,
        None,
        "ACQUIRE_MISSING",
        False,
    )
    cancellation_seen = {"value": False}

    class TransientCancellation:
        def is_cancelled(self) -> bool:
            return cancellation_seen["value"]

    def interrupted_acquisition(
        *_: object, control: CurrentRawInvocationControlV1, **__: object
    ) -> acquisition_module.CurrentRawAcquisitionResultV1:
        cancellation_seen["value"] = True
        with pytest.raises(packet_v2.CurrentRawInvocationStoppedV1):
            control.ensure_live()
        cancellation_seen["value"] = False
        return acquisition_module.CurrentRawAcquisitionResultV1("STOPPED", 0)

    monkeypatch.setattr(
        packet_v2, "acquire_missing_current_raw_evidence_v1", interrupted_acquisition
    )

    with pytest.raises(packet_v2.CurrentRawInvocationStoppedV1):
        packet_v2.research_current_price_context_v2(
            request,
            tmp_path / "missing-root",
            clock=_Clock(selected_at),
            cancellation=TransientCancellation(),
        )
