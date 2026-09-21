"""Public RED contract tests for Issue #189's one-shot V2 boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from http.client import IncompleteRead
from pathlib import Path
from typing import Any, Literal, cast
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
    RootAuthorityV1,
    StorageRootLease,
    StorageRootLeaseError,
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
    assert all(
        (
            item.physical_identity_sha256,
            item.source_cutoff,
            item.prior_source_cutoff,
            item.published_at,
            item.known_at,
        )
        == (None, None, None, None, None)
        for item in mapping_entries
    )
    assert all(
        member.mapping_observation_sha256 is not None
        and member.mapping_retrieved_at is not None
        for member in result.completed_context.members
    )
    assert (
        sum(item.provider_calls_attempted for item in result.freshness_ledger)
        == result.provider_calls_attempted
    )
    assert (
        sum(item.provider_calls_completed for item in result.freshness_ledger)
        == result.provider_calls_completed
    )
    assert all(item.state == "OBSERVED" for item in result.completed_context.members)
    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2
    assert decoder(result.canonical_json_bytes()) == result

    contradicted_mapping = json.loads(result.canonical_json_bytes())
    contradicted_entry = next(
        item
        for item in contradicted_mapping["freshness_ledger"]
        if item["source"] == "MAPPING"
    )
    contradicted_entry["state"] = "UNAVAILABLE"
    with pytest.raises(ValueError, match="result is invalid"):
        packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
            _reseal_result(contradicted_mapping)
        )

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


def test_v2_decoder_rejects_reused_admitted_mapping_reseal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A completed admitted member requires its zero-call Mapping reuse state."""
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
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    monkeypatch.setattr(
        transport_module,
        "build_opener",
        RecordedWire(
            [
                WireReply(
                    body=mapping_body(members),
                    headers=(("Content-Type", "application/gzip"),),
                ),
                WireReply(body=historical_body()),
                WireReply(body=action_body()),
            ]
        ).build_opener,
    )
    packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "ACQUIRE_MISSING"), root, clock=_Clock(selected_at)
    )
    retained = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "RETAINED_ONLY"), root, clock=_Clock(selected_at)
    )
    assert retained.completed_context.members[0].state == "OBSERVED"
    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2
    assert decoder(retained.canonical_json_bytes()) == retained
    resealed = json.loads(retained.canonical_json_bytes())
    mapping = next(
        item for item in resealed["freshness_ledger"] if item["source"] == "MAPPING"
    )
    assert (
        mapping["state"],
        mapping["provider_calls_attempted"],
        mapping["provider_calls_completed"],
    ) == ("REUSED", 0, 0)
    mapping["state"] = "UNAVAILABLE"
    resealed["reused_physical_objects"] -= 1
    with pytest.raises(ValueError, match="result is invalid"):
        packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
            _reseal_result(resealed)
        )


def test_v2_decoder_rejects_reused_mapping_reseal_after_downstream_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A retained Mapping remains required after a downstream partition refusal."""
    selected_at = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
    schedule_value = current_month_schedule(selected_at)
    request_value = raw_request(schedule_value, selection=selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    monkeypatch.setattr(
        transport_module,
        "build_opener",
        RecordedWire(
            [WireReply(body=historical_body()), WireReply(body=action_body())]
        ).build_opener,
    )
    admitted = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "ACQUIRE_MISSING"), root, clock=_Clock(selected_at)
    )
    assert admitted.completed_context.members[0].state == "OBSERVED"

    partition = next(root.rglob("*.parquet"))
    partition.chmod(0o600)
    partition.write_bytes(b"corrupt")
    downstream_failure = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "RETAINED_ONLY"), root, clock=_Clock(selected_at)
    )
    assert (
        downstream_failure.completed_context.members[0].state,
        downstream_failure.completed_context.members[0].reason,
    ) == ("INSUFFICIENT_EVIDENCE", "RAW_PARTITION_CORRUPT")
    assert (
        next(
            item
            for item in downstream_failure.freshness_ledger
            if item.source == "MAPPING"
        ).state
    ) == "REUSED"
    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2
    assert decoder(downstream_failure.canonical_json_bytes()) == downstream_failure

    resealed = json.loads(downstream_failure.canonical_json_bytes())
    mapping = next(
        item for item in resealed["freshness_ledger"] if item["source"] == "MAPPING"
    )
    assert (
        mapping["state"],
        mapping["provider_calls_attempted"],
        mapping["provider_calls_completed"],
    ) == ("REUSED", 0, 0)
    mapping["state"] = "UNAVAILABLE"
    resealed["reused_physical_objects"] -= 1
    with pytest.raises(ValueError, match="result is invalid"):
        decoder(_reseal_result(resealed))


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

    for field, value in (
        ("provider_calls_attempted", 1),
        ("provider_calls_completed", 1),
        ("reused_physical_objects", 1),
        ("refreshed_physical_objects", 1),
        ("acquisition_started_at", "2026-09-15T09:00:00.000000Z"),
        ("acquisition_completed_at", "2026-09-15T09:00:00.000000Z"),
    ):
        changed_accounting = json.loads(result.canonical_json_bytes())
        changed_accounting[field] = value
        with pytest.raises(ValueError, match="result is invalid"):
            decoder(_reseal_result(changed_accounting))


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


def _retain_active_v2_prefix(
    root: Path,
    schedule_value: ExpectedSessionSchedule,
    request_value: CurrentRawPriceContextInputV1,
    monkeypatch: pytest.MonkeyPatch,
) -> packet_v2.CurrentPriceContextResultV2:
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    wire = RecordedWire(
        [
            *(
                WireReply(
                    body=current_history_body(schedule_value, through=date(2026, 9, 29))
                )
                for _ in request_value.members
            ),
            *(WireReply(body=action_body()) for _ in request_value.members),
            *(
                WireReply(body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0)))
                for _ in request_value.members
            ),
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    result = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "ACQUIRE_MISSING"),
        root,
        clock=_Clock(request_value.data_selection_time),
    )
    assert wire.attempts == 3 * len(request_value.members)
    assert all(item.state == "OBSERVED" for item in result.completed_context.members)
    assert all(item.state == "OBSERVED" for item in result.current_session)
    return result


@pytest.mark.parametrize(
    "mutation",
    ("closed-session", "pre-open-session", "stale-completed-minute"),
)
def test_v2_decoder_rejects_resealed_non_active_or_stale_observed_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    request_value = _active_raw_request(schedule_value, selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    result = _retain_active_v2_prefix(root, schedule_value, request_value, monkeypatch)
    value = json.loads(result.canonical_json_bytes())

    if mutation in {"closed-session", "pre-open-session"}:
        selection = value["planning_witness"]["selection_session"]
        assert selection is not None
        field = "close_at" if mutation == "closed-session" else "open_at"
        selection[field] = "2026-09-30T03:47:00.000000Z"
        for collection in ("physical_plan", "freshness_ledger"):
            current = next(
                item
                for item in value[collection]
                if item["source"] == "CURRENT_SESSION"
            )
            current["slot"] = "current-session"
    else:
        stale = "2026-09-30T03:45:00.000000Z"
        value["current_session"][0]["last_completed_minute"] = stale
        value["current_session"][0]["source_cutoff"] = stale
        current = next(
            item
            for item in value["freshness_ledger"]
            if item["source"] == "CURRENT_SESSION"
        )
        current["source_cutoff"] = stale

    with pytest.raises(ValueError, match="result is invalid"):
        packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
            _reseal_result(value)
        )


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
    refreshed_entry = next(
        item for item in refreshed.freshness_ledger if item.source == "CURRENT_SESSION"
    )
    assert refreshed_entry.state == "APPENDED"
    prior_cutoff = refreshed_entry.prior_source_cutoff
    final_cutoff = refreshed_entry.source_cutoff
    assert prior_cutoff is not None
    assert final_cutoff is not None
    assert prior_cutoff < final_cutoff
    appended_as_refreshed = json.loads(refreshed.canonical_json_bytes())
    next(
        item
        for item in appended_as_refreshed["freshness_ledger"]
        if item["source"] == "CURRENT_SESSION"
    )["state"] = "REFRESHED"
    with pytest.raises(ValueError, match="result is invalid"):
        packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
            _reseal_result(appended_as_refreshed)
        )

    # The runtime derived APPENDED from the captured retained prefix.  At the
    # response boundary, a self-consistent history reseal is deliberately not
    # authenticated against those retained bytes.
    response_only_reseal = json.loads(refreshed.canonical_json_bytes())
    response_entry = next(
        item
        for item in response_only_reseal["freshness_ledger"]
        if item["source"] == "CURRENT_SESSION"
    )
    response_entry["state"] = "REFRESHED"
    response_entry["prior_source_cutoff"] = response_entry["source_cutoff"]
    response_decoded = (
        packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
            _reseal_result(response_only_reseal)
        )
    )
    response_decoded_entry = next(
        item
        for item in response_decoded.freshness_ledger
        if item.source == "CURRENT_SESSION"
    )
    assert refreshed_entry.state == "APPENDED"
    assert prior_cutoff < final_cutoff
    assert (
        response_decoded_entry.state,
        response_decoded_entry.prior_source_cutoff,
    ) == ("REFRESHED", response_decoded_entry.source_cutoff)
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

    contradicted_action = json.loads(result.canonical_json_bytes())
    action_entry = next(
        item
        for item in contradicted_action["freshness_ledger"]
        if item["source"] == "CORPORATE_ACTION" and item["position"] == 0
    )
    action_entry["state"] = (
        "ACQUIRED" if action_entry["state"] == "UNAVAILABLE" else "UNAVAILABLE"
    )
    with pytest.raises(ValueError, match="result is invalid"):
        packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
            _reseal_result(contradicted_action)
        )


@pytest.mark.parametrize(
    ("calendar_kind", "completed_reason"),
    (
        ("twenty-completed", "COMPLETED_SESSION_WINDOW_UNAVAILABLE"),
        ("future-known", "CALENDAR_FUTURE_KNOWN"),
    ),
)
def test_v2_calendar_insufficiency_returns_typed_refusals_without_provider_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    calendar_kind: Literal["twenty-completed", "future-known"],
    completed_reason: str,
) -> None:
    """V2 must not turn retained-calendar refusal into a constructor failure."""
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    if calendar_kind == "twenty-completed":
        removed = schedule_value.sessions[0]
        schedule_value = replace(
            schedule_value,
            sessions=schedule_value.sessions[1:],
            closures=tuple(
                sorted(
                    (
                        *schedule_value.closures,
                        ScheduleClosure(removed.trade_date, "HOLIDAY"),
                    ),
                    key=lambda item: item.trade_date,
                )
            ),
        )
    else:
        schedule_value = replace(
            schedule_value, as_of=selected_at + timedelta(minutes=1)
        )
    request_value = raw_request(schedule_value, selection=selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    wire = RecordedWire([])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)

    result = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "RETAINED_ONLY"), root, clock=_Clock(selected_at)
    )

    assert wire.attempts == 0
    assert result.provider_calls_attempted == result.provider_calls_completed == 0
    assert all(
        (item.state, item.reason) == ("INSUFFICIENT_EVIDENCE", completed_reason)
        for item in result.completed_context.members
    )
    assert all(
        (item.state, item.reason) == ("UNAVAILABLE", "CALENDAR_PREREQUISITE_MISSING")
        for item in result.current_session
    )
    assert tuple(
        item.state
        for item in result.freshness_ledger
        if item.source in {"CALENDAR", "MAPPING"}
    ) == ("UNAVAILABLE", "UNAVAILABLE")
    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2
    assert decoder(result.canonical_json_bytes()) == result


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
    selection_date = selected_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
    if expected_state == "NOT_APPLICABLE" and selection_date.weekday() >= 5:
        days = tuple(date(2026, 8, 1) + timedelta(days=index) for index in range(57))
        schedule_value = ExpectedSessionSchedule(
            SCHEDULE_SCHEMA_VERSION_V3,
            "nse-authoritative-calendar",
            "sha256:" + "a" * 64,
            selected_at,
            "Asia/Kolkata",
            days[0],
            days[-1],
            tuple(
                ScheduleSession(
                    day,
                    datetime(day.year, day.month, day.day, 3, 45, tzinfo=UTC),
                    datetime(day.year, day.month, day.day, 3, 46, tzinfo=UTC),
                    "REGULAR",
                )
                for day in days
                if day.weekday() < 5
            ),
            tuple(
                ScheduleClosure(day, "WEEKEND") for day in days if day.weekday() >= 5
            ),
        )
    else:
        full_schedule = current_month_schedule(
            max(selected_at, datetime(2026, 9, 30, 3, 45, tzinfo=UTC))
        )
        schedule_value = replace(
            full_schedule,
            as_of=selected_at,
            covered_to=selection_date,
            sessions=tuple(
                item
                for item in full_schedule.sessions
                if item.trade_date <= selection_date
            ),
            closures=tuple(
                item
                for item in full_schedule.closures
                if item.trade_date <= selection_date
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
    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2
    assert decoder(result.canonical_json_bytes()) == result

    resealed = json.loads(result.canonical_json_bytes())
    resealed["current_session"][0].update(
        state=(
            "UNAVAILABLE" if expected_state == "NOT_APPLICABLE" else "NOT_APPLICABLE"
        ),
        reason=(
            "CALENDAR_PREREQUISITE_MISSING"
            if expected_state == "NOT_APPLICABLE"
            else "CURRENT_SESSION_NOT_APPLICABLE"
        ),
    )
    with pytest.raises(ValueError, match="result is invalid"):
        decoder(_reseal_result(resealed))


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
    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2
    assert decoder(result.canonical_json_bytes()) == result
    resealed = json.loads(result.canonical_json_bytes())
    resealed["current_session"][0].update(
        state="UNAVAILABLE", reason="CALENDAR_PREREQUISITE_MISSING"
    )
    with pytest.raises(ValueError, match="result is invalid"):
        decoder(_reseal_result(resealed))


def test_v2_fresh_exact_close_projects_completed_history_calls_without_provisional_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selection_day = date(2026, 9, 30)
    selected_at = datetime(2026, 9, 30, 3, 49, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    request_value = raw_request(schedule_value, selection=selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    wire_replies = [
        WireReply(
            body=current_history_body(
                schedule_value, through=selection_day - timedelta(days=1)
            )
        ),
        WireReply(body=_intraday_payload(selection_day, (100.0, 101.0, 102.0, 103.0))),
        WireReply(body=action_body()),
    ]
    expected_calls = 3
    wire = RecordedWire(wire_replies)
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)

    result = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "ACQUIRE_MISSING"), root, clock=_Clock(selected_at)
    )

    history = next(
        entry for entry in result.freshness_ledger if entry.source == "CURRENT_HISTORY"
    )
    current = next(
        entry for entry in result.freshness_ledger if entry.source == "CURRENT_SESSION"
    )
    assert wire.attempts == result.provider_calls_attempted == expected_calls
    assert result.provider_calls_completed == expected_calls
    assert (history.provider_calls_attempted, history.provider_calls_completed) == (
        2,
        2,
    )
    assert (current.provider_calls_attempted, current.provider_calls_completed) == (
        0,
        0,
    )
    assert result.current_session[0].state == "NOT_APPLICABLE"


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


@pytest.mark.parametrize(
    "mutation",
    (
        "in-range-false-month",
        "omission",
        "duplicate",
        "reorder",
        "wrong-source",
        "wrong-correction",
        "paired-month-substitution",
        "wrong-active-month-slot",
        "unavailable-member-plan-and-ledger-omission",
    ),
)
def test_v2_result_requires_an_exact_ordered_physical_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
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

    if mutation == "in-range-false-month":
        value["physical_plan"][1]["source"] = "CLOSED_MONTH"
        value["physical_plan"][1]["slot"] = "2026-09"
    elif mutation == "omission":
        del value["physical_plan"][1]
    elif mutation == "duplicate":
        value["physical_plan"].insert(1, value["physical_plan"][0].copy())
    elif mutation == "reorder":
        value["physical_plan"].reverse()
    elif mutation == "wrong-source":
        value["physical_plan"][0]["source"] = "MAPPING"
        value["physical_plan"][0]["slot"] = "mapping"
    elif mutation == "wrong-correction":
        value["freshness_ledger"][0]["correction_rule"] = "SELECTION_DATE_MAPPING"
    elif mutation == "paired-month-substitution":
        closed = next(
            index
            for index, item in enumerate(value["freshness_ledger"])
            if item["source"] == "CLOSED_MONTH"
        )
        value["freshness_ledger"][closed]["slot"] = "2026-08"
        value["physical_plan"][closed]["slot"] = "2026-08"
    elif mutation == "wrong-active-month-slot":
        current = next(
            index
            for index, item in enumerate(value["freshness_ledger"])
            if item["source"] == "CURRENT_SESSION"
        )
        value["freshness_ledger"][current]["slot"] = "2026-08"
        value["physical_plan"][current]["slot"] = "2026-08"
    else:
        closed = next(
            index
            for index, item in enumerate(value["freshness_ledger"])
            if item["source"] == "CLOSED_MONTH"
        )
        del value["freshness_ledger"][closed]
        del value["physical_plan"][closed]

    with pytest.raises(ValueError, match="result is invalid"):
        packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
            _reseal_result(value)
        )


def test_v2_selection_owned_exact_provisional_generation_reuses_before_later_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    exact_request = _active_raw_request(schedule_value, selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=exact_request)
    first = _retain_active_v2_prefix(root, schedule_value, exact_request, monkeypatch)
    assert first.current_session[0].source_cutoff == datetime(
        2026, 9, 30, 3, 46, tzinfo=UTC
    )

    later_selection = selected_at + timedelta(minutes=1)
    later_request = _active_raw_request(schedule_value, later_selection)
    later_wire = RecordedWire(
        [WireReply(body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0, 102.0)))]
    )
    monkeypatch.setattr(transport_module, "build_opener", later_wire.build_opener)
    later = packet_v2.research_current_price_context_v2(
        _v2_from_raw(later_request, "REFRESH_ONCE"),
        root,
        clock=_Clock(later_selection),
    )
    assert later_wire.attempts == 1
    assert later.current_session[0].source_cutoff == datetime(
        2026, 9, 30, 3, 47, tzinfo=UTC
    )

    reused_wire = RecordedWire([])
    monkeypatch.setattr(transport_module, "build_opener", reused_wire.build_opener)
    advanced = _AdvancingClock(
        selected_at + timedelta(minutes=2),
        timedelta(seconds=5),
        exact_request.admission_deadline - timedelta(seconds=1),
    )
    reused = packet_v2.research_current_price_context_v2(
        _v2_from_raw(exact_request, "ACQUIRE_MISSING"), root, clock=advanced
    )
    current = reused.current_session[0]
    ledger = next(
        item for item in reused.freshness_ledger if item.source == "CURRENT_SESSION"
    )
    assert reused_wire.attempts == reused.provider_calls_attempted == 0
    assert current.state == "OBSERVED"
    assert (
        current.source_cutoff
        == current.last_completed_minute
        == datetime(2026, 9, 30, 3, 46, tzinfo=UTC)
    )
    assert ledger.state == "REUSED" and ledger.source_cutoff == current.source_cutoff
    assert max(advanced.observed) > later_selection


@pytest.mark.parametrize(
    ("failure", "reply", "completed_calls"),
    (
        ("terminal-404", WireReply(status=404), 1),
        ("malformed", WireReply(body=b"{}"), 1),
        (
            "body-timeout",
            WireReply(
                body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0)),
                on_read=lambda: (_ for _ in ()).throw(TimeoutError("fixture")),
            ),
            0,
        ),
        (
            "incomplete-body",
            WireReply(
                body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0)),
                on_read=lambda: (_ for _ in ()).throw(IncompleteRead(b"partial", 10)),
            ),
            0,
        ),
    ),
)
def test_v2_refresh_failure_overlays_only_current_member_and_preserves_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    reply: WireReply,
    completed_calls: int,
) -> None:
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    request_value = _active_raw_request(schedule_value, selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    first = _retain_active_v2_prefix(root, schedule_value, request_value, monkeypatch)
    retained_bytes = {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    wire = RecordedWire([reply])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)

    refreshed = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "REFRESH_ONCE"), root, clock=_Clock(selected_at)
    )

    current = refreshed.current_session[0]
    current_ledger = next(
        item for item in refreshed.freshness_ledger if item.source == "CURRENT_SESSION"
    )
    assert wire.attempts == refreshed.provider_calls_attempted == 1
    assert refreshed.provider_calls_completed == completed_calls
    assert refreshed.completed_context.members[0].state == "OBSERVED"
    assert (
        refreshed.completed_context.members[0].partition_checksums
        == first.completed_context.members[0].partition_checksums
    )
    assert current.state == "UNAVAILABLE"
    assert current.reason == "PROVISIONAL_EVIDENCE_UNAVAILABLE"
    assert all(
        value is None
        for value in (
            current.last_completed_minute,
            current.observed_price,
            current.cumulative_source_volume,
            current.source_version,
            current.partition_checksum_sha256,
            current.source_cutoff,
            current.published_at,
            current.known_at,
        )
    )
    assert (
        current_ledger.provider_calls_attempted,
        current_ledger.provider_calls_completed,
    ) == (
        1,
        completed_calls,
    )
    assert {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    } == retained_bytes, failure


@pytest.mark.parametrize(
    "status", (404, 401, 403, 429), ids=("local", "401", "403", "429")
)
def test_v2_refresh_failure_precedence_keeps_prior_members_and_stops_only_shared_openers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    request_value = raw_request(
        schedule_value, selection=selected_at, members=raw_members(2)
    )
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    _retain_active_v2_prefix(root, schedule_value, request_value, monkeypatch)
    replies = [WireReply(status=status)]
    if status == 404:
        replies.append(
            WireReply(body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0)))
        )
    wire = RecordedWire(replies)
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)

    result = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "REFRESH_ONCE"), root, clock=_Clock(selected_at)
    )

    assert wire.attempts == (2 if status == 404 else 1)
    assert all(item.state == "OBSERVED" for item in result.completed_context.members)
    assert result.current_session[0].state == "UNAVAILABLE"
    assert result.current_session[1].state == "OBSERVED"
    assert result.provider_calls_attempted == wire.attempts
    assert result.provider_calls_completed == wire.attempts


def test_v2_root_replacement_at_retained_and_effectful_seams_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    request_value = _active_raw_request(schedule_value, selected_at)

    retained_root = tmp_path / "retained-root"
    seed_root(retained_root, schedule_value=schedule_value, request_value=request_value)
    retained_wire = RecordedWire([])
    monkeypatch.setattr(transport_module, "build_opener", retained_wire.build_opener)
    original_cutoffs = packet_v2._current_session_cutoff_identities  # pyright: ignore[reportPrivateUsage]

    def replace_after_retained_read(*args: object, **kwargs: object) -> object:
        result = original_cutoffs(*cast(Any, args), **cast(Any, kwargs))
        retained_root.rename(tmp_path / "retained-displaced")
        retained_root.mkdir(mode=0o700)
        replacement = StorageRootLease.try_acquire_private_empty(retained_root)
        assert replacement.lease is not None
        replacement.lease.close()
        return result

    monkeypatch.setattr(
        packet_v2,
        "_current_session_cutoff_identities",
        replace_after_retained_read,
    )
    with pytest.raises(StorageRootLeaseError, match="root authority"):
        packet_v2.research_current_price_context_v2(
            _v2_from_raw(request_value, "RETAINED_ONLY"),
            retained_root,
            clock=_Clock(selected_at),
        )
    assert retained_wire.attempts == 0
    assert not (retained_root / "market_data.duckdb").exists()
    monkeypatch.setattr(
        packet_v2,
        "_current_session_cutoff_identities",
        original_cutoffs,
    )

    effectful_root = tmp_path / "effectful-root"
    seed_root(
        effectful_root, schedule_value=schedule_value, request_value=request_value
    )
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    effectful_wire = RecordedWire(
        [
            WireReply(
                body=current_history_body(schedule_value, through=date(2026, 9, 29))
            ),
            WireReply(body=action_body()),
            WireReply(body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0))),
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", effectful_wire.build_opener)
    original_publish = acquisition_module.publish_provisional_partition_under_lease

    def replace_before_publication(*args: object, **kwargs: object) -> object:
        effectful_root.rename(tmp_path / "effectful-displaced")
        effectful_root.mkdir(mode=0o700)
        replacement = StorageRootLease.try_acquire_private_empty(effectful_root)
        assert replacement.lease is not None
        replacement.lease.close()
        return original_publish(*cast(Any, args), **cast(Any, kwargs))

    monkeypatch.setattr(
        acquisition_module,
        "publish_provisional_partition_under_lease",
        replace_before_publication,
    )
    with pytest.raises(StorageRootLeaseError, match="root authority"):
        packet_v2.research_current_price_context_v2(
            _v2_from_raw(request_value, "ACQUIRE_MISSING"),
            effectful_root,
            clock=_Clock(selected_at),
        )
    assert effectful_wire.attempts == FixtureTokenProvider.calls == 1
    assert len(effectful_wire.replies) == 2
    assert not (effectful_root / "market_data.duckdb").exists()


def test_v2_final_v1_read_never_adopts_a_restored_replacement_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    request_value = _active_raw_request(schedule_value, selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    _retain_active_v2_prefix(root, schedule_value, request_value, monkeypatch)
    original_identity = (root.stat().st_dev, root.stat().st_ino)

    replacement = tmp_path / "replacement"
    displaced = tmp_path / "displaced"
    seed_root(
        replacement,
        schedule_value=schedule_value,
        request_value=request_value,
    )
    replacement_identity = (replacement.stat().st_dev, replacement.stat().st_ino)
    real_storage_root_lease = packet_v1.StorageRootLease
    real_admit = real_storage_root_lease.try_admit_read_existing
    real_identity = real_storage_root_lease.admit_existing_private_identity
    real_recheck = packet_v1.recheck_retained_current_raw_context_v1
    swapped = False

    def restore_original_root() -> None:
        nonlocal swapped
        if not swapped:
            return
        root.rename(replacement)
        displaced.rename(root)
        swapped = False

    class SwapBeforeV1Read:
        @staticmethod
        def try_admit_read_existing(
            candidate: object,
            expected_root_identity: tuple[int, int] | None = None,
        ) -> object:
            nonlocal swapped
            assert candidate == root
            root.rename(displaced)
            replacement.rename(root)
            swapped = True
            admitted = real_admit(candidate, expected_root_identity)
            if admitted.lease is None:
                restore_original_root()
            return admitted

        @staticmethod
        def admit_existing_private_identity(
            candidate: object,
        ) -> tuple[int, int] | None:
            return real_identity(candidate)

        @staticmethod
        def ensure_root_authority(
            candidate: object, authority: RootAuthorityV1
        ) -> None:
            real_storage_root_lease.ensure_root_authority(candidate, authority)

    def restore_after_recheck(*args: object, **kwargs: object) -> object:
        try:
            return real_recheck(*cast(Any, args), **cast(Any, kwargs))
        finally:
            restore_original_root()

    monkeypatch.setattr(packet_v1, "StorageRootLease", SwapBeforeV1Read)
    monkeypatch.setattr(
        packet_v1,
        "recheck_retained_current_raw_context_v1",
        restore_after_recheck,
    )
    no_wire = RecordedWire([])
    monkeypatch.setattr(transport_module, "build_opener", no_wire.build_opener)

    with pytest.raises(StorageRootLeaseError, match="root authority"):
        packet_v2.research_current_price_context_v2(
            _v2_from_raw(request_value, "RETAINED_ONLY"),
            root,
            clock=_Clock(selected_at),
        )

    restore_original_root()
    assert no_wire.attempts == 0
    assert (root.stat().st_dev, root.stat().st_ino) == original_identity
    assert (replacement.stat().st_dev, replacement.stat().st_ino) == (
        replacement_identity
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


def test_v2_decoder_rebinds_planning_witness_minutes_close_and_topology(
    tmp_path: Path,
) -> None:
    selected_at = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
    schedule_value = current_month_schedule(selected_at)
    request_value = raw_request(schedule_value, selection=selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    result = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "RETAINED_ONLY"), root, clock=_Clock(selected_at)
    )
    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2
    exact_limit = json.loads(result.canonical_json_bytes())
    minute_counts = (476,) * 20 + (480,)
    for session, minutes in zip(
        exact_limit["planning_witness"]["completed_sessions"],
        minute_counts,
        strict=True,
    ):
        opened = datetime.fromisoformat(session["open_at"].replace("Z", "+00:00"))
        session["close_at"] = (
            (opened + timedelta(minutes=minutes))
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    exact_decoded = decoder(_reseal_result(exact_limit))
    assert (
        sum(
            int((item.close_at - item.open_at).total_seconds() // 60)
            for item in exact_decoded.planning_witness.completed_sessions
        )
        == 10_000
    )

    subminute_shift = json.loads(result.canonical_json_bytes())
    session = subminute_shift["planning_witness"]["completed_sessions"][0]
    for field in ("open_at", "close_at"):
        instant = datetime.fromisoformat(session[field].replace("Z", "+00:00"))
        session[field] = (
            (instant + timedelta(microseconds=1))
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )

    chronology = json.loads(result.canonical_json_bytes())
    sessions = chronology["planning_witness"]["completed_sessions"]
    sessions[0], sessions[1] = sessions[1], sessions[0]

    overnight_close = json.loads(result.canonical_json_bytes())
    session = overnight_close["planning_witness"]["completed_sessions"][0]
    opened = datetime.fromisoformat(session["open_at"].replace("Z", "+00:00"))
    session["close_at"] = (
        (opened + timedelta(hours=20, minutes=45))
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )

    above_limit = json.loads(_reseal_result(exact_limit))
    final = above_limit["planning_witness"]["completed_sessions"][-1]
    closed = datetime.fromisoformat(final["close_at"].replace("Z", "+00:00"))
    final["close_at"] = (
        (closed + timedelta(minutes=1))
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )

    for value in (subminute_shift, chronology, overnight_close, above_limit):
        with pytest.raises(ValueError, match="result is invalid"):
            decoder(_reseal_result(value))

    unavailable_root = tmp_path / "unavailable-root"
    seed_root(
        unavailable_root,
        schedule_value=schedule_value,
        request_value=request_value,
        retain_mapping=False,
    )
    unavailable = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "RETAINED_ONLY"),
        unavailable_root,
        clock=_Clock(selected_at),
    )
    topology = json.loads(unavailable.canonical_json_bytes())
    topology["planning_witness"].update(completed_sessions=[], selection_session=None)
    retained = [
        item
        for item in topology["freshness_ledger"]
        if item["source"] not in {"CLOSED_MONTH", "CURRENT_HISTORY"}
    ]
    topology["freshness_ledger"] = retained
    topology["physical_plan"] = [
        item
        for item in topology["physical_plan"]
        if item["source"] not in {"CLOSED_MONTH", "CURRENT_HISTORY"}
    ]
    with pytest.raises(ValueError, match="result is invalid"):
        decoder(_reseal_result(topology))


def test_v2_first_trading_day_exact_close_projects_intraday_into_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 10, 1, 3, 49, tzinfo=UTC)
    schedule_value = _cross_month_active_schedule(selected_at)
    request_value = raw_request(schedule_value, selection=selected_at)
    september = tuple(
        item for item in schedule_value.sessions if item.trade_date.month == 9
    )

    for action, expected_state in (
        (WireReply(body=action_body()), "OBSERVED"),
        (WireReply(status=404), "INSUFFICIENT_EVIDENCE"),
    ):
        root = tmp_path / expected_state
        seed_root(root, schedule_value=schedule_value, request_value=request_value)
        FixtureTokenProvider.calls = 0
        monkeypatch.setattr(
            acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
        )
        wire = RecordedWire(
            [
                WireReply(body=historical_body(september)),
                WireReply(
                    body=_intraday_payload(
                        date(2026, 10, 1), (100.0, 101.0, 102.0, 103.0)
                    )
                ),
                action,
            ]
        )
        monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)

        result = packet_v2.research_current_price_context_v2(
            _v2_from_raw(request_value, "ACQUIRE_MISSING"),
            root,
            clock=_Clock(selected_at),
        )

        history = next(
            item for item in result.freshness_ledger if item.source == "CURRENT_HISTORY"
        )
        current = next(
            item for item in result.freshness_ledger if item.source == "CURRENT_SESSION"
        )
        assert wire.attempts == result.provider_calls_attempted == 3
        assert (history.slot, history.provider_calls_attempted) == ("2026-10", 1)
        assert history.provider_calls_completed == 1
        assert (current.provider_calls_attempted, current.provider_calls_completed) == (
            0,
            0,
        )
        assert result.current_session[0].state == "NOT_APPLICABLE"
        assert result.completed_context.members[0].state == expected_state

        retained_wire = RecordedWire([])
        monkeypatch.setattr(
            transport_module, "build_opener", retained_wire.build_opener
        )
        retained = packet_v2.research_current_price_context_v2(
            _v2_from_raw(request_value, "RETAINED_ONLY"),
            root,
            clock=_Clock(selected_at),
        )
        retained_history = next(
            item
            for item in retained.freshness_ledger
            if item.source == "CURRENT_HISTORY"
        )
        retained_action = next(
            item
            for item in retained.freshness_ledger
            if item.source == "CORPORATE_ACTION"
        )
        assert retained_wire.attempts == retained.provider_calls_attempted == 0
        assert (
            retained_history.state,
            retained_history.provider_calls_attempted,
            retained_history.provider_calls_completed,
        ) == (
            "REUSED" if expected_state == "OBSERVED" else "UNAVAILABLE",
            0,
            0,
        )
        assert retained_action.state == (
            "REUSED" if expected_state == "OBSERVED" else "UNAVAILABLE"
        )
        assert retained.current_session[0].state == "NOT_APPLICABLE"
        assert retained.completed_context.members[0].state == expected_state

        contradicted_action = json.loads(retained.canonical_json_bytes())
        action_entry = next(
            item
            for item in contradicted_action["freshness_ledger"]
            if item["source"] == "CORPORATE_ACTION"
        )
        action_entry["state"] = (
            "REUSED" if action_entry["state"] == "UNAVAILABLE" else "UNAVAILABLE"
        )
        with pytest.raises(ValueError, match="result is invalid"):
            packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
                _reseal_result(contradicted_action)
            )


def test_v2_combined_local_provisional_failure_shared_stop_and_industry_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    members = (
        *raw_members(2),
        replace(raw_members(2)[1], isin="INE009A01021", effective_symbol="ICICIBANK"),
    )
    request_value = raw_request(schedule_value, selection=selected_at, members=members)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    bootstrap = RecordedWire(
        [
            *(
                WireReply(
                    body=current_history_body(schedule_value, through=date(2026, 9, 29))
                )
                for _ in members
            ),
            *(WireReply(body=action_body()) for _ in members),
            *(
                WireReply(body=_intraday_payload(date(2026, 9, 30), (100.0, 101.0)))
                for _ in members
            ),
        ]
    )
    monkeypatch.setattr(transport_module, "build_opener", bootstrap.build_opener)
    reference = packet_v1.CurrentIndustryArchiveReferenceV1(
        "current-industry-archive-reference@v1", "a" * 64, "b" * 64
    )
    request = packet_v2.CurrentPriceContextRequestV2(
        "current-price-context-request@v2",
        request_value.data_selection_time,
        request_value.admission_deadline,
        request_value.schedule_identity_sha256,
        members,
        _QUESTIONS,
        reference,
        "ACQUIRE_MISSING",
        True,
    )
    initial = packet_v2.research_current_price_context_v2(
        request, root, clock=_Clock(selected_at)
    )
    assert bootstrap.attempts == 3 * len(members)
    assert all(item.state == "OBSERVED" for item in initial.completed_context.members)
    assert initial.completed_context.industry_evidence_state == "INSUFFICIENT_EVIDENCE"

    refresh = replace(
        request, execution_mode="REFRESH_ONCE", request_identity_sha256=""
    )
    wire = RecordedWire([WireReply(status=404), WireReply(status=401)])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    result = packet_v2.research_current_price_context_v2(
        refresh, root, clock=_Clock(selected_at)
    )

    current = tuple(
        item for item in result.freshness_ledger if item.source == "CURRENT_SESSION"
    )
    assert wire.attempts == result.provider_calls_attempted == 2
    assert result.provider_calls_completed == 2
    assert all(item.state == "OBSERVED" for item in result.completed_context.members)
    assert tuple(item.state for item in result.current_session) == (
        "UNAVAILABLE",
        "UNAVAILABLE",
        "OBSERVED",
    )
    assert tuple(item.provider_calls_attempted for item in current) == (1, 1, 0)
    assert tuple(item.provider_calls_completed for item in current) == (1, 1, 0)
    assert result.completed_context.industry_evidence_state == "INSUFFICIENT_EVIDENCE"
    assert result.freshness_ledger[-1].state == "UNAVAILABLE"


def test_v2_final_return_rechecks_root_identity_after_witness_reread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    request_value = _active_raw_request(schedule_value, selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    original = packet_v2._planning_witness_from_retained  # pyright: ignore[reportPrivateUsage]
    calls = 0

    def replace_after_final_witness(*args: object, **kwargs: object) -> object:
        nonlocal calls
        witness = original(*cast(Any, args), **cast(Any, kwargs))
        calls += 1
        if calls == 2:
            root.rename(tmp_path / "displaced")
            root.mkdir(mode=0o700)
            replacement = StorageRootLease.try_acquire_private_empty(root)
            assert replacement.lease is not None
            replacement.lease.close()
        return witness

    monkeypatch.setattr(
        packet_v2, "_planning_witness_from_retained", replace_after_final_witness
    )
    with pytest.raises(StorageRootLeaseError, match="root authority"):
        packet_v2.research_current_price_context_v2(
            _v2_from_raw(request_value, "RETAINED_ONLY"),
            root,
            clock=_Clock(selected_at),
        )


def test_v2_absent_root_never_adopts_a_transient_replacement_at_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ABSENT invocation authority is not an unconstrained read authority."""
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    request_value = _active_raw_request(schedule_value, selected_at)
    root = tmp_path / "missing-root"
    replacement = tmp_path / "replacement"
    seed_root(replacement, schedule_value=schedule_value, request_value=request_value)
    original_ensure = StorageRootLease.ensure_root_authority
    ensured = False

    def replace_before_revalidation(
        root_arg: object, authority: RootAuthorityV1
    ) -> None:
        nonlocal ensured
        if ensured:
            return original_ensure(root_arg, authority)
        ensured = True
        replacement.rename(root)
        return original_ensure(root_arg, authority)

    monkeypatch.setattr(
        StorageRootLease,
        "ensure_root_authority",
        replace_before_revalidation,
    )
    with pytest.raises(StorageRootLeaseError, match="root authority"):
        packet_v2.research_current_price_context_v2(
            _v2_from_raw(request_value, "RETAINED_ONLY"),
            root,
            clock=_Clock(selected_at),
        )
    assert root.is_dir()


def test_v2_decoder_rejects_missing_calendar_and_no_evidence_reseals(
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
        True,
    )
    result = packet_v2.research_current_price_context_v2(
        request, tmp_path / "missing-root", clock=_Clock(selected_at)
    )
    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2
    assert result.current_session[0].reason == "CALENDAR_PREREQUISITE_MISSING"
    assert decoder(result.canonical_json_bytes()) == result
    mapping = next(item for item in result.freshness_ledger if item.source == "MAPPING")
    assert (
        mapping.state,
        mapping.provider_calls_attempted,
        mapping.provider_calls_completed,
    ) == ("UNAVAILABLE", 0, 0)

    resealed = json.loads(result.canonical_json_bytes())
    mapping = next(
        item for item in resealed["freshness_ledger"] if item["source"] == "MAPPING"
    )
    mapping["state"] = "REUSED"
    resealed["reused_physical_objects"] += 1
    with pytest.raises(ValueError, match="result is invalid"):
        decoder(_reseal_result(resealed))

    resealed = json.loads(result.canonical_json_bytes())
    resealed["current_session"][0].update(
        state="NOT_APPLICABLE", reason="CURRENT_SESSION_NOT_APPLICABLE"
    )
    with pytest.raises(ValueError, match="result is invalid"):
        decoder(_reseal_result(resealed))

    resealed = json.loads(result.canonical_json_bytes())
    ledger = next(
        item
        for item in resealed["freshness_ledger"]
        if item["source"] == "CURRENT_SESSION"
    )
    ledger["state"] = "REUSED"
    resealed["reused_physical_objects"] = 1
    with pytest.raises(ValueError, match="result is invalid"):
        decoder(_reseal_result(resealed))

    for state, reason, source in (
        ("UNAVAILABLE", "PROVISIONAL_EVIDENCE_STALE", "CURRENT_SESSION"),
        ("NOT_APPLICABLE", "CURRENT_SESSION_NOT_APPLICABLE", "CURRENT_SESSION"),
        ("CONFLICTED", "PROVISIONAL_EVIDENCE_CONFLICTED", "CURRENT_SESSION"),
        ("UNAVAILABLE", "CALENDAR_PREREQUISITE_MISSING", "MAPPING"),
        ("UNAVAILABLE", "CALENDAR_PREREQUISITE_MISSING", "CORPORATE_ACTION"),
    ):
        resealed = json.loads(result.canonical_json_bytes())
        if source == "CURRENT_SESSION":
            resealed["current_session"][0].update(state=state, reason=reason)
        entry = next(
            item for item in resealed["freshness_ledger"] if item["source"] == source
        )
        entry["state"] = "CONFLICTED"
        with pytest.raises(ValueError, match="result is invalid"):
            decoder(_reseal_result(resealed))


def _no_witness_schedule(
    calendar_kind: Literal["twenty-active", "future-active", "pre-open", "weekend"],
    selected_at: datetime,
) -> ExpectedSessionSchedule:
    if calendar_kind == "weekend":
        full_schedule = current_month_schedule(datetime(2026, 9, 30, 3, 45, tzinfo=UTC))
        selection_date = selected_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
        return replace(
            full_schedule,
            as_of=selected_at,
            covered_to=selection_date,
            sessions=tuple(
                item
                for item in full_schedule.sessions
                if item.trade_date <= selection_date
            ),
            closures=tuple(
                item
                for item in full_schedule.closures
                if item.trade_date <= selection_date
            ),
        )
    schedule_value = _active_schedule(selected_at)
    if calendar_kind == "future-active":
        return replace(schedule_value, as_of=selected_at + timedelta(minutes=1))
    removed = schedule_value.sessions[0]
    return replace(
        schedule_value,
        sessions=schedule_value.sessions[1:],
        closures=tuple(
            sorted(
                (
                    *schedule_value.closures,
                    ScheduleClosure(removed.trade_date, "HOLIDAY"),
                ),
                key=lambda item: item.trade_date,
            )
        ),
    )


def _unexpected_token_provider(*_: object, **__: object) -> object:
    raise AssertionError("Calendar-prerequisite refusal accessed a token")


def _no_witness_runtime_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    calendar_kind: Literal["twenty-active", "future-active", "pre-open", "weekend"],
    mode: _Mode,
) -> packet_v2.CurrentPriceContextResultV2:
    selected_at = (
        datetime(2026, 9, 26, 9, tzinfo=UTC)
        if calendar_kind == "weekend"
        else datetime(
            2026,
            9,
            30,
            3,
            44,
            59,
            tzinfo=UTC,
        )
        if calendar_kind == "pre-open"
        else datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    )
    schedule_value = _no_witness_schedule(calendar_kind, selected_at)
    request_value = raw_request(schedule_value, selection=selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    monkeypatch.setattr(transport_module, "build_opener", _unexpected_token_provider)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", _unexpected_token_provider
    )
    return packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, mode), root, clock=_Clock(selected_at)
    )


def _missing_no_witness_runtime_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, mode: _Mode
) -> packet_v2.CurrentPriceContextResultV2:
    selected_at = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = packet_v2.CurrentPriceContextRequestV2(
        "current-price-context-request@v2",
        selected_at,
        selected_at + timedelta(minutes=30),
        "a" * 64,
        (_member(),),
        _QUESTIONS,
        None,
        mode,
        True,
    )
    monkeypatch.setattr(transport_module, "build_opener", _unexpected_token_provider)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", _unexpected_token_provider
    )
    return packet_v2.research_current_price_context_v2(
        request, tmp_path / "missing-root", clock=_Clock(selected_at)
    )


def _assert_no_witness_zero_effects(
    result: packet_v2.CurrentPriceContextResultV2,
) -> None:
    assert result.provider_calls_attempted == result.provider_calls_completed == 0
    assert result.acquisition_started_at is result.acquisition_completed_at is None
    assert all(
        (item.state, item.reason) == ("UNAVAILABLE", "CALENDAR_PREREQUISITE_MISSING")
        for item in result.current_session
    )
    assert all(
        (item.provider_calls_attempted, item.provider_calls_completed) == (0, 0)
        for item in result.freshness_ledger
        if item.source not in {"CALENDAR", "INDUSTRY"}
    )


@pytest.mark.parametrize("mode", ("RETAINED_ONLY", "ACQUIRE_MISSING", "REFRESH_ONCE"))
@pytest.mark.parametrize("calendar_kind", ("twenty-active", "future-active"))
def test_v2_active_no_witness_refusals_round_trip_without_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: _Mode,
    calendar_kind: Literal["twenty-active", "future-active"],
) -> None:
    """Active no-witness results must be conservative in every one-shot mode."""
    result = _no_witness_runtime_result(
        tmp_path, monkeypatch, calendar_kind=calendar_kind, mode=mode
    )

    _assert_no_witness_zero_effects(result)
    assert all(
        (member.state, member.reason)
        == (
            "INSUFFICIENT_EVIDENCE",
            {
                "twenty-active": "COMPLETED_SESSION_WINDOW_UNAVAILABLE",
                "future-active": "CALENDAR_FUTURE_KNOWN",
            }[calendar_kind],
        )
        for member in result.completed_context.members
    )
    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2
    assert decoder(result.canonical_json_bytes()) == result


@pytest.mark.parametrize("mode", ("RETAINED_ONLY", "ACQUIRE_MISSING", "REFRESH_ONCE"))
def test_v2_missing_calendar_no_witness_refuses_in_every_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: _Mode
) -> None:
    result = _missing_no_witness_runtime_result(tmp_path, monkeypatch, mode=mode)

    _assert_no_witness_zero_effects(result)
    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2
    assert decoder(result.canonical_json_bytes()) == result


@pytest.mark.parametrize("mode", ("RETAINED_ONLY", "ACQUIRE_MISSING", "REFRESH_ONCE"))
@pytest.mark.parametrize("calendar_kind", ("pre-open", "weekend"))
def test_v2_inactive_no_witness_refuses_without_inferring_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: _Mode,
    calendar_kind: Literal["pre-open", "weekend"],
) -> None:
    """No witness means the runtime cannot claim an inactive market phase."""
    result = _no_witness_runtime_result(
        tmp_path, monkeypatch, calendar_kind=calendar_kind, mode=mode
    )

    _assert_no_witness_zero_effects(result)
    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2
    assert decoder(result.canonical_json_bytes()) == result


@pytest.mark.parametrize("mode", ("RETAINED_ONLY", "ACQUIRE_MISSING", "REFRESH_ONCE"))
@pytest.mark.parametrize("calendar_kind", ("missing", "twenty-active", "future-active"))
def test_v2_decoder_rejects_no_witness_not_applicable_reseals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: _Mode,
    calendar_kind: Literal["missing", "twenty-active", "future-active"],
) -> None:
    """A freshness timestamp cannot substitute for a validated phase witness."""
    result = (
        _missing_no_witness_runtime_result(tmp_path, monkeypatch, mode=mode)
        if calendar_kind == "missing"
        else _no_witness_runtime_result(
            tmp_path,
            monkeypatch,
            calendar_kind=calendar_kind,
            mode=mode,
        )
    )
    resealed = json.loads(result.canonical_json_bytes())
    resealed["current_session"][0].update(
        state="NOT_APPLICABLE", reason="CURRENT_SESSION_NOT_APPLICABLE"
    )

    with pytest.raises(ValueError, match="result is invalid"):
        packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
            _reseal_result(resealed)
        )


@pytest.mark.parametrize("calls", ((1, 1), (1, 0)), ids=("completed", "attempted"))
@pytest.mark.parametrize("source", ("MAPPING", "CORPORATE_ACTION", "CURRENT_SESSION"))
@pytest.mark.parametrize("mode", ("RETAINED_ONLY", "ACQUIRE_MISSING", "REFRESH_ONCE"))
@pytest.mark.parametrize("calendar_kind", ("missing", "twenty-active", "future-active"))
def test_v2_decoder_rejects_no_witness_downstream_call_reseals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    calls: tuple[int, int],
    source: Literal["MAPPING", "CORPORATE_ACTION", "CURRENT_SESSION"],
    mode: _Mode,
    calendar_kind: Literal["missing", "twenty-active", "future-active"],
) -> None:
    """Calendar-prerequisite bytes cannot claim later provider effects."""
    result = (
        _missing_no_witness_runtime_result(tmp_path, monkeypatch, mode=mode)
        if calendar_kind == "missing"
        else _no_witness_runtime_result(
            tmp_path,
            monkeypatch,
            calendar_kind=calendar_kind,
            mode=mode,
        )
    )
    resealed = json.loads(result.canonical_json_bytes())
    entry = next(
        item for item in resealed["freshness_ledger"] if item["source"] == source
    )
    entry["provider_calls_attempted"], entry["provider_calls_completed"] = calls
    resealed["provider_calls_attempted"], resealed["provider_calls_completed"] = calls
    resealed["acquisition_started_at"] = resealed["inspection_time"]
    resealed["acquisition_completed_at"] = resealed["evidence_cutoff"]

    with pytest.raises(ValueError, match="result is invalid"):
        packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
            _reseal_result(resealed)
        )


@pytest.mark.parametrize("mode", ("RETAINED_ONLY", "ACQUIRE_MISSING", "REFRESH_ONCE"))
def test_v2_no_witness_not_requested_current_session_remains_zero_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: _Mode
) -> None:
    """The optional-current-session false path remains a truthful no-effect result."""
    result = _no_witness_runtime_result(
        tmp_path, monkeypatch, calendar_kind="twenty-active", mode=mode
    )
    request = packet_v2.CurrentPriceContextRequestV2(
        "current-price-context-request@v2",
        result.data_selection_time,
        result.admission_deadline,
        result.schedule_identity_sha256,
        result.request_members,
        result.questions,
        result.industry_archive_reference,
        mode,
        False,
    )
    # Reuse the exact retained root, but keep provider/token sentinels installed.
    root = tmp_path / "root"
    result = packet_v2.research_current_price_context_v2(
        request, root, clock=_Clock(result.data_selection_time)
    )

    assert all(
        item.state == item.reason == "NOT_REQUESTED" for item in result.current_session
    )
    assert result.provider_calls_attempted == result.provider_calls_completed == 0
    assert result.acquisition_started_at is result.acquisition_completed_at is None


def test_v2_decoder_rejects_failed_mapping_success_reseals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
    schedule_value = current_month_schedule(selected_at)
    request_value = raw_request(schedule_value, selection=selected_at)
    root = tmp_path / "root"
    seed_root(
        root,
        schedule_value=schedule_value,
        request_value=request_value,
        retain_mapping=False,
    )
    wire = RecordedWire([WireReply(status=404)])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    result = packet_v2.research_current_price_context_v2(
        _v2_from_raw(request_value, "ACQUIRE_MISSING"), root, clock=_Clock(selected_at)
    )
    mapping = next(item for item in result.freshness_ledger if item.source == "MAPPING")
    assert (
        mapping.state,
        mapping.provider_calls_attempted,
        mapping.provider_calls_completed,
    ) == (
        "UNAVAILABLE",
        1,
        1,
    )

    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2
    for state in ("REUSED", "ACQUIRED", "CONFLICTED"):
        resealed = json.loads(result.canonical_json_bytes())
        entry = next(
            item for item in resealed["freshness_ledger"] if item["source"] == "MAPPING"
        )
        entry["state"] = state
        with pytest.raises(ValueError, match="result is invalid"):
            decoder(_reseal_result(resealed))


def test_v2_decoder_rejects_active_phase_pair_and_mode_reseals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    request_value = _active_raw_request(schedule_value, selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    result = _retain_active_v2_prefix(root, schedule_value, request_value, monkeypatch)
    decoder = packet_v2.current_price_context_result_from_canonical_json_bytes_v2

    for state, reason, ledger_state in (
        ("NOT_APPLICABLE", "CURRENT_SESSION_NOT_APPLICABLE", "UNAVAILABLE"),
        ("UNAVAILABLE", "PROVISIONAL_EVIDENCE_UNAVAILABLE", "CONFLICTED"),
    ):
        resealed = json.loads(result.canonical_json_bytes())
        current = resealed["current_session"][0]
        for field in (
            "last_completed_minute",
            "observed_price",
            "cumulative_source_volume",
            "source_version",
            "partition_checksum_sha256",
            "source_cutoff",
            "published_at",
            "known_at",
        ):
            current[field] = None
        current.update(state=state, label=None, reason=reason)
        entry = next(
            item
            for item in resealed["freshness_ledger"]
            if item["source"] == "CURRENT_SESSION"
        )
        entry.update(
            state=ledger_state,
            physical_identity_sha256=None,
            source_cutoff=None,
            published_at=None,
            known_at=None,
        )
        with pytest.raises(ValueError, match="result is invalid"):
            decoder(_reseal_result(resealed))

    for state in ("REFRESHED", "APPENDED"):
        resealed = json.loads(result.canonical_json_bytes())
        entry = next(
            item
            for item in resealed["freshness_ledger"]
            if item["source"] == "CURRENT_SESSION"
        )
        entry["state"] = state
        resealed["refreshed_physical_objects"] = 1
        with pytest.raises(ValueError, match="result is invalid"):
            decoder(_reseal_result(resealed))


def test_v2_response_only_decoder_limit_and_runtime_retained_value_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A self-consistent price reseal is not attestation; runtime uses verified rows."""
    selected_at = datetime(2026, 9, 30, 3, 47, 30, tzinfo=UTC)
    schedule_value = _active_schedule(selected_at)
    request_value = _active_raw_request(schedule_value, selected_at)
    root = tmp_path / "root"
    seed_root(root, schedule_value=schedule_value, request_value=request_value)
    result = _retain_active_v2_prefix(root, schedule_value, request_value, monkeypatch)

    assert (
        result.current_session[0].observed_price,
        result.current_session[0].cumulative_source_volume,
    ) == (
        "101.0",
        20,
    )
    resealed = json.loads(result.canonical_json_bytes())
    resealed["current_session"][0].update(
        observed_price="999.0", cumulative_source_volume=999
    )
    current = next(
        item
        for item in resealed["freshness_ledger"]
        if item["source"] == "CURRENT_SESSION"
    )
    assert (
        current["physical_identity_sha256"]
        == result.current_session[0].partition_checksum_sha256
    )
    decoded = packet_v2.current_price_context_result_from_canonical_json_bytes_v2(
        _reseal_result(resealed)
    )
    assert (
        decoded.current_session[0].observed_price,
        decoded.current_session[0].cumulative_source_volume,
    ) == (
        "999.0",
        999,
    )


@pytest.mark.parametrize("mode", ("RETAINED_ONLY", "ACQUIRE_MISSING", "REFRESH_ONCE"))
@pytest.mark.parametrize("include_current", (False, True))
def test_v2_true_absence_is_zero_effect_missing_calendar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: _Mode, include_current: bool
) -> None:
    selected = datetime(2026, 9, 15, 9, tzinfo=UTC)
    root = tmp_path / "genuinely-absent"
    request = packet_v2.CurrentPriceContextRequestV2(
        "current-price-context-request@v2",
        selected,
        selected + timedelta(minutes=30),
        "a" * 64,
        (_member(),),
        _QUESTIONS,
        None,
        mode,
        include_current,
    )
    opener_calls = 0

    def forbidden_opener(*args: object, **kwargs: object) -> object:
        nonlocal opener_calls
        opener_calls += 1
        raise AssertionError("absence must not open a provider")

    monkeypatch.setattr(transport_module, "build_opener", forbidden_opener)
    assert not root.exists() and not root.is_symlink()
    result = packet_v2.research_current_price_context_v2(
        request, root, clock=_Clock(selected)
    )
    assert result.provider_calls_attempted == result.provider_calls_completed == 0
    assert opener_calls == 0
    assert all(
        item.state == "DEPENDENCY_BLOCKED"
        and item.reason == "CALENDAR_PREREQUISITE_MISSING"
        for item in result.completed_context.members
    )
    expected = (
        ("UNAVAILABLE", "CALENDAR_PREREQUISITE_MISSING")
        if include_current
        else ("NOT_REQUESTED", "NOT_REQUESTED")
    )
    assert all((item.state, item.reason) == expected for item in result.current_session)
    assert all(
        item.state in {"UNAVAILABLE", "NOT_REQUESTED"}
        for item in result.freshness_ledger
    )
    assert not root.exists() and not root.is_symlink()


@pytest.mark.parametrize("kind", ("dangling", "live", "file", "nonprivate"))
def test_root_authority_rejects_unsafe_named_root(
    tmp_path: Path, kind: Literal["dangling", "live", "file", "nonprivate"]
) -> None:
    root = tmp_path / "unsafe"
    target = tmp_path / "target"
    if kind == "dangling":
        root.symlink_to(tmp_path / "missing-target")
    elif kind == "live":
        target.mkdir()
        (target / "sentinel").write_bytes(b"unchanged")
        root.symlink_to(target, target_is_directory=True)
    elif kind == "file":
        root.write_bytes(b"unchanged")
    else:
        root.mkdir(mode=0o755)
    before = (root.lstat().st_mode, root.readlink() if root.is_symlink() else None)
    with pytest.raises(
        StorageRootLeaseError, match="storage root authority unavailable"
    ):
        StorageRootLease.capture_root_authority(root)
    assert (
        root.lstat().st_mode,
        root.readlink() if root.is_symlink() else None,
    ) == before
    if kind == "live":
        assert (target / "sentinel").read_bytes() == b"unchanged"


@pytest.mark.parametrize("mode", ("ACQUIRE_MISSING", "REFRESH_ONCE"))
def test_v2_absent_root_late_creation_at_acquisition_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: _Mode
) -> None:
    selected = datetime(2026, 9, 15, 9, tzinfo=UTC)
    root = tmp_path / "absent"
    replacement = tmp_path / "replacement"
    request = packet_v2.CurrentPriceContextRequestV2(
        "current-price-context-request@v2",
        selected,
        selected + timedelta(minutes=30),
        "a" * 64,
        (_member(),),
        _QUESTIONS,
        None,
        mode,
        False,
    )
    original = packet_v2.acquire_missing_current_raw_evidence_v1

    def create_then_admit(*args: object, **kwargs: object) -> object:
        replacement.mkdir(mode=0o700)
        replacement.rename(root)
        return original(*cast(Any, args), **cast(Any, kwargs))

    monkeypatch.setattr(
        packet_v2, "acquire_missing_current_raw_evidence_v1", create_then_admit
    )
    with pytest.raises(StorageRootLeaseError, match="root authority"):
        packet_v2.research_current_price_context_v2(
            request, root, clock=_Clock(selected)
        )
    assert root.is_dir() and tuple(root.iterdir()) == ()
