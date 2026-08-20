from __future__ import annotations

"""RED contract tests for the standalone Plan-21 Upstox action screen.

The Plan-21 module is deliberately imported only at execution time.  This keeps
collection and the retained-evidence fixtures meaningful while this test-first
contract precedes its production surface.
"""

import hashlib
import importlib
import inspect
import json
import os
import socket
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data import corporate_actions as action_module
from swing_trading_ai_assistant.market_data.corporate_actions import (
    CorporateActionSnapshotStoreV1,
    UpstoxCorporateActionsClientV1,
)
from swing_trading_ai_assistant.market_data.current_cohort import (
    CurrentCohortMemberV1,
    CurrentSuppliedCohortManifestV1,
)
from swing_trading_ai_assistant.market_data.http import HttpResponse
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V2,
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceStore,
    ScheduleSession,
    canonical_schedule_bytes,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)

_CONTRACT_VERSION = "current-supplied-cohort-upstox-action-screen@v1"
_SCREEN_MODULE = "swing_trading_ai_assistant.market_data.current_corporate_action_screen"
_SOURCE = "upstox-fundamentals-v2"
_SOURCE_IDENTITY = "3853a15b853b73a945065486ca96b48d4ee3625e4ed7c6e4927579e2b0b372a2"
_SNAPSHOT_SCHEMA_IDENTITY = "de03833b00d0d286fc3d0116f7ce81b8694547d43b13250f7415d6c95fdbbf8a"
_SCREEN_SCHEMA_IDENTITY = "a789cbdd1c554ddd0e5029d02e263491af73c1b23754366cd78e2b2f3d75dbde"
_POLICY_IDENTITY = "36d3c8ed4ce51acf4c9373bcc39d8e45b72621ea222abafa6468df9e31b20020"
_SELECTED_SET_SCHEMA_IDENTITY = "a655abdd1ee44337ad28d9b6f9d148927d831d9eeb7cdeccdde68f90945d0775"
_SCHEDULE_SOURCE = "nse-authoritative-calendar"
_SCHEDULE_RELEASE = "sha256:" + "b" * 64
_S0 = date(2026, 7, 6)
_S20 = date(2026, 8, 3)
_CLOSE = datetime(2026, 8, 3, 10, tzinfo=UTC)
_CUTOFF = datetime(2026, 8, 4, 12, tzinfo=UTC)
_SELECTED_AT = datetime(2026, 8, 4, 12, tzinfo=UTC)


class _Transport:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        self.calls.append((url, dict(headers)))
        return HttpResponse(200, self.payload)


@dataclass
class _Scenario:
    root: Path
    lease: StorageRootLease
    catalog: DuckDBCatalog
    schedule_store: ScheduleEvidenceStore
    action_store: CorporateActionSnapshotStoreV1
    schedule: ExpectedSessionSchedule
    schedule_sha256: str
    manifest: CurrentSuppliedCohortManifestV1
    snapshot_metadata: dict[str, Any] = field(default_factory=dict)

    def close(self) -> None:
        self.catalog.__exit__(None, None, None)
        self.lease.close()


def _module() -> ModuleType:
    """Skip semantic RED checks only until their Plan-21 module exists."""
    return pytest.importorskip(_SCREEN_MODULE)


def _api() -> ModuleType:
    return _assert_api(_module())


def _assert_api(module: ModuleType) -> ModuleType:
    required = (
        "CurrentSuppliedCohortUpstoxActionScreenInputV1",
        "CurrentSuppliedCohortUpstoxActionScreenRequestV1",
        "PrivateUpstoxActionScreenResultV1",
        "CurrentSuppliedCohortUpstoxActionScreenReportV1",
        "PrivateUpstoxActionScreenResolverV1",
        "PrivateUpstoxActionScreenResolverPortV1",
        "PrivateUpstoxActionScreenOutcomeV1",
        "CurrentSuppliedCohortUpstoxActionScreenStateV1",
        "CURRENT_UPSTOX_ACTION_SCREEN_CONTRACT_VERSION_V1",
        "CURRENT_UPSTOX_ACTION_SCREEN_SCHEMA_IDENTITY_SHA256_V1",
        "CURRENT_UPSTOX_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1",
        "CURRENT_UPSTOX_ACTION_SCREEN_SOURCE_IDENTITY_SHA256_V1",
        "SELECTED_SNAPSHOT_SET_SCHEMA_IDENTITY_SHA256_V1",
    )
    missing = [name for name in required if not hasattr(module, name)]
    assert not missing, f"Plan-21 API missing: {', '.join(missing)}"
    return module


def _valid_isin(index: int) -> str:
    """Create deterministic distinct ISINs accepted by the existing Luhn rule."""
    prefix = f"INE{index:05d}A01"
    for check in range(10):
        candidate = prefix + str(check)
        expanded = "".join(
            str(ord(char) - 55) if char.isalpha() else char for char in candidate
        )
        total = 0
        for position, char in enumerate(reversed(expanded)):
            digit = int(char)
            if position % 2:
                digit *= 2
                digit = digit // 10 + digit % 10
            total += digit
        if total % 10 == 0:
            return candidate
    raise AssertionError("test ISIN generation failed")


def _members(count: int) -> tuple[CurrentCohortMemberV1, ...]:
    return tuple(
        CurrentCohortMemberV1(_valid_isin(index), f"EQ{index:02d}")
        for index in range(1, count + 1)
    )


def _schedule(
    schema_version: int,
    *,
    source: str = _SCHEDULE_SOURCE,
    source_release: str = _SCHEDULE_RELEASE,
) -> ExpectedSessionSchedule:
    sessions = tuple(
        ScheduleSession(
            _S0 + timedelta(days=offset),
            datetime(2026, 7, 6, 3, 45, tzinfo=UTC) + timedelta(days=offset),
            datetime(2026, 7, 6, 10, tzinfo=UTC) + timedelta(days=offset),
            "REGULAR",
        )
        for offset in range((_S20 - _S0).days + 1)
        if (_S0 + timedelta(days=offset)).weekday() < 5
    )
    closures = tuple(
        ScheduleClosure(_S0 + timedelta(days=offset), "WEEKEND")
        for offset in range((_S20 - _S0).days + 1)
        if (_S0 + timedelta(days=offset)).weekday() >= 5
    )
    return ExpectedSessionSchedule(
        schema_version=schema_version,
        source=source,
        source_release=source_release,
        as_of=_CUTOFF,
        timezone="Asia/Kolkata",
        covered_from=_S0,
        covered_to=_S20,
        sessions=sessions,
        closures=closures,
    )


def _payload(
    kind: str | None,
    effective: date = _S20,
    *,
    record_date: date | None = None,
) -> bytes:
    if kind is None:
        events: list[dict[str, object]] = []
    else:
        announced = min(_S0, effective)
        record = effective if record_date is None else record_date
        details: list[dict[str, str]] = [
            {"name": "Record date", "value": record.strftime("%d %b %Y")},
            {"name": "Announcement date", "value": announced.strftime("%d %b %Y")},
        ]
        event: dict[str, object] = {
            "event_details": details,
            "ratio": None,
            "amount": None,
            "expiry_date": effective.strftime("%d %b %Y"),
            "name": kind.title(),
        }
        if kind == "DIVIDEND":
            event["amount"] = 5.5
            details.extend(
                [
                    {"name": "Dividend type", "value": "Final"},
                    {"name": "Amount", "value": "5.5"},
                    {"name": "Ex dividend date", "value": effective.strftime("%d %b %Y")},
                ]
            )
        else:
            ratio = {"BONUS": "1:1", "SPLIT": "2:1", "RIGHTS": "1:5"}[kind]
            event["ratio"] = ratio
            details.extend(
                [
                    {"name": "Ratio", "value": ratio},
                    {"name": f"Ex {kind.lower()} date", "value": effective.strftime("%d %b %Y")},
                ]
            )
        events = [event]
    return json.dumps({"data": events, "status": "success"}, separators=(",", ":")).encode()


def _retain_snapshot(
    scenario: _Scenario,
    isin: str,
    *,
    kind: str | None = None,
    effective: date = _S20,
    record_date: date | None = None,
    retrieved_at: datetime = _CUTOFF,
) -> Any:
    transport = _Transport(_payload(kind, effective, record_date=record_date))
    snapshot = UpstoxCorporateActionsClientV1(
        transport, clock=lambda: retrieved_at
    ).fetch(isin, "fixture-token")
    metadata = scenario.action_store.retain(snapshot)
    scenario.snapshot_metadata[isin] = metadata
    assert len(transport.calls) == 1
    return metadata


def _scenario(
    tmp_path: Path,
    count: int,
    schema_version: int = SCHEDULE_SCHEMA_VERSION_V2,
    *,
    snapshots: bool = True,
    retained_schedule_source: str = _SCHEDULE_SOURCE,
    retained_schedule_release: str = _SCHEDULE_RELEASE,
) -> _Scenario:
    root = tmp_path / "retained"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    lease = acquired.lease
    catalog = DuckDBCatalog(root, lease=lease)
    catalog.__enter__()
    schedule_store = ScheduleEvidenceStore(root, lease)
    schedule = _schedule(
        schema_version,
        source=retained_schedule_source,
        source_release=retained_schedule_release,
    )
    schedule_sha256 = schedule_digest(schedule)
    retained = schedule_store.retain(schedule)
    assert retained.digest_sha256 == schedule_sha256
    scenario = _Scenario(
        root, lease, catalog, schedule_store,
        CorporateActionSnapshotStoreV1(root, lease, catalog), schedule, schedule_sha256,
        CurrentSuppliedCohortManifestV1(_SELECTED_AT, _members(count)),
    )
    if snapshots:
        for member in scenario.manifest.members:
            _retain_snapshot(scenario, member.isin)
    return scenario


def _input(
    module: ModuleType,
    scenario: _Scenario,
    *,
    comparison_session: date = _S0,
    decision_session: date = _S20,
    decision_cutoff: datetime = _CUTOFF,
    schedule_evidence_sha256: str | None = None,
    schedule_source: str = _SCHEDULE_SOURCE,
    schedule_source_release: str = _SCHEDULE_RELEASE,
    corporate_action_source: str = _SOURCE,
    corporate_action_source_identity_sha256: str = _SOURCE_IDENTITY,
    snapshot_schema_identity_sha256: str = _SNAPSHOT_SCHEMA_IDENTITY,
    screen_schema_identity_sha256: str = _SCREEN_SCHEMA_IDENTITY,
    screen_policy_identity_sha256: str = _POLICY_IDENTITY,
) -> Any:
    return module.CurrentSuppliedCohortUpstoxActionScreenInputV1(
        scenario.manifest,
        comparison_session,
        decision_session,
        decision_cutoff,
        scenario.schedule_sha256
        if schedule_evidence_sha256 is None
        else schedule_evidence_sha256,
        schedule_source,
        schedule_source_release,
        corporate_action_source,
        corporate_action_source_identity_sha256,
        snapshot_schema_identity_sha256,
        screen_schema_identity_sha256,
        screen_policy_identity_sha256,
    )


def _request(module: ModuleType, scenario: _Scenario, **overrides: Any) -> Any:
    return module.CurrentSuppliedCohortUpstoxActionScreenRequestV1(
        _input(module, scenario, **overrides)
    )


def _resolve(module: ModuleType, scenario: _Scenario) -> tuple[Any, Any, Any]:
    resolver = module.PrivateUpstoxActionScreenResolverV1(
        scenario.schedule_store, scenario.action_store
    )
    request = _request(module, scenario)
    private = resolver.resolve_exact(request, scenario.lease)
    return private, private.to_public_report(), request


def _canonical(value: Any) -> bytes:
    return value.canonical_json_bytes()


_PUBLIC_FIELDS = (
    "contract_version", "input_identity_sha256", "request_identity_sha256",
    "cohort_identity_sha256", "comparison_session", "decision_session",
    "decision_session_close_at", "decision_cutoff", "schedule_evidence_sha256",
    "schedule_source", "schedule_source_release", "corporate_action_source",
    "corporate_action_source_identity_sha256", "snapshot_schema_identity_sha256",
    "screen_schema_identity_sha256", "screen_policy_identity_sha256",
    "code_identity_sha256", "evidence_state", "screen_state",
    "coverage_limitation", "selected_snapshot_set_identity_sha256", "reason",
    "report_identity_sha256",
)


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _expected_selected_snapshot_set(scenario: _Scenario) -> str:
    expected_isins = tuple(sorted(member.isin for member in scenario.manifest.members))
    assert tuple(sorted(scenario.snapshot_metadata)) == expected_isins
    projection = {
        "cohort_identity_sha256": scenario.manifest.cohort_identity_sha256,
        "comparison_session": _S0.isoformat(),
        "decision_cutoff": _instant(_CUTOFF),
        "decision_session": _S20.isoformat(),
        "schedule_evidence_sha256": scenario.schedule_sha256,
        "schedule_source": _SCHEDULE_SOURCE,
        "schedule_source_release": _SCHEDULE_RELEASE,
        "snapshots": [
            {
                "isin": isin,
                "snapshot_digest_sha256": scenario.snapshot_metadata[isin].snapshot_sha256,
                "source": scenario.snapshot_metadata[isin].source,
                "source_release": scenario.snapshot_metadata[isin].source_release,
                "snapshot_schema_identity_sha256": _SNAPSHOT_SCHEMA_IDENTITY,
                "retrieved_at": _instant(scenario.snapshot_metadata[isin].retrieved_at),
            }
            for isin in expected_isins
        ],
    }
    assert tuple(projection) == (
        "cohort_identity_sha256", "comparison_session", "decision_cutoff",
        "decision_session", "schedule_evidence_sha256", "schedule_source",
        "schedule_source_release", "snapshots",
    )
    assert all(
        tuple(row) == (
            "isin", "snapshot_digest_sha256", "source", "source_release",
            "snapshot_schema_identity_sha256", "retrieved_at",
        )
        for row in projection["snapshots"]
    )
    return hashlib.sha256(
        json.dumps(projection, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        + b"\n"
    ).hexdigest()


def _assert_public_redaction(report: Any, private: Any, request: Any) -> None:
    public = _canonical(report)
    value = report.value()
    assert tuple(value) == _PUBLIC_FIELDS
    assert report.contract_version == _CONTRACT_VERSION
    assert report.input_identity_sha256 == request.input_identity_sha256
    assert report.request_identity_sha256 == request.request_identity_sha256
    assert report.cohort_identity_sha256 == private.cohort_identity_sha256
    assert report.comparison_session == private.comparison_session
    assert report.decision_session == private.decision_session
    assert report.decision_cutoff == private.decision_cutoff
    assert report.schedule_evidence_sha256 == private.schedule_evidence_sha256
    assert report.schedule_source == private.schedule_source
    assert report.schedule_source_release == private.schedule_source_release
    assert report.corporate_action_source == _SOURCE
    assert report.corporate_action_source_identity_sha256 == private.source_identity_sha256
    assert report.snapshot_schema_identity_sha256 == private.snapshot_schema_identity_sha256
    assert report.screen_schema_identity_sha256 == _SCREEN_SCHEMA_IDENTITY
    assert report.screen_policy_identity_sha256 == _POLICY_IDENTITY
    assert type(report.code_identity_sha256) is str and len(report.code_identity_sha256) == 64
    assert report.coverage_limitation == "UPSTOX_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE"
    forbidden = (
        b"INE", b"EQ", b"DIVIDEND", b"BONUS", b"SPLIT", b"RIGHTS",
        b"snapshot.json", b"corporate_action_snapshots", b"event_details",
        b"RAW_CLOSE_NO_BREAK_PROVEN", b"NO_BREAK",
    )
    assert not any(item in public for item in forbidden)
    if private.outcome.value != "SCREENED_NO_SUPPORTED_ACTION_OBSERVED":
        assert private.outcome.value.encode() not in public
    if report.screen_state is None:
        assert report.evidence_state.value == "INSUFFICIENT_EVIDENCE"
        assert report.decision_session_close_at is None
        assert report.selected_snapshot_set_identity_sha256 is None
        assert report.reason == "CORPORATE_ACTION_SCREEN_INSUFFICIENT"
    else:
        assert report.evidence_state.value == "SCREENED"
        assert report.screen_state.value == "UPSTOX_SCREENED_NO_SUPPORTED_ACTION_OBSERVED"
        assert report.decision_session_close_at == _CLOSE
        assert report.selected_snapshot_set_identity_sha256 is not None
        assert report.reason is None


def test_plan21_module_surface_and_frozen_identities_are_exact() -> None:
    module = _assert_api(importlib.import_module(_SCREEN_MODULE))

    assert module.CURRENT_UPSTOX_ACTION_SCREEN_CONTRACT_VERSION_V1 == _CONTRACT_VERSION
    assert module.CURRENT_UPSTOX_ACTION_SCREEN_SCHEMA_IDENTITY_SHA256_V1 == _SCREEN_SCHEMA_IDENTITY
    assert module.CURRENT_UPSTOX_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1 == _POLICY_IDENTITY
    assert module.CURRENT_UPSTOX_ACTION_SCREEN_SOURCE_IDENTITY_SHA256_V1 == _SOURCE_IDENTITY
    assert tuple(inspect.signature(module.PrivateUpstoxActionScreenResolverPortV1.resolve_exact).parameters) == (
        "self", "request", "lease",
    )
    assert module.SELECTED_SNAPSHOT_SET_SCHEMA_IDENTITY_SHA256_V1 == _SELECTED_SET_SCHEMA_IDENTITY


@pytest.mark.parametrize("count", (1, 5, 50))
def test_ready_empty_retained_snapshots_screen_every_permitted_cohort_size(
    tmp_path: Path, count: int
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, count)
    try:
        private, report, request = _resolve(module, scenario)
    finally:
        scenario.close()

    assert private.outcome == module.PrivateUpstoxActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
    assert private.decision_session_close_at == _CLOSE
    assert private.selected_snapshot_set_identity_sha256 is not None
    assert report.screen_state == module.CurrentSuppliedCohortUpstoxActionScreenStateV1.SCREENED
    assert report.reason is None
    assert report.selected_snapshot_set_identity_sha256 == private.selected_snapshot_set_identity_sha256
    _assert_public_redaction(report, private, request)


@pytest.mark.parametrize("schema_version", (SCHEDULE_SCHEMA_VERSION_V2, SCHEDULE_SCHEMA_VERSION_V3))
def test_schedule_v2_and_v3_derive_the_same_exact_s20_close(
    tmp_path: Path, schema_version: int
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1, schema_version)
    try:
        private, report, request = _resolve(module, scenario)
    finally:
        scenario.close()

    assert len(scenario.schedule.sessions) == 21
    assert scenario.schedule.sessions[0].trade_date == _S0
    assert scenario.schedule.sessions[20].trade_date == _S20
    assert private.decision_session_close_at == _CLOSE
    assert report.decision_session_close_at == _CLOSE


@pytest.mark.parametrize("retrieved_at", (_CLOSE, _CUTOFF))
def test_equal_close_and_equal_cutoff_snapshots_are_fresh_and_selectable(
    tmp_path: Path, retrieved_at: datetime
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1, snapshots=False)
    try:
        member = scenario.manifest.members[0]
        _retain_snapshot(scenario, member.isin, retrieved_at=retrieved_at)
        private, _, _ = _resolve(module, scenario)
    finally:
        scenario.close()

    assert private.outcome == module.PrivateUpstoxActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
    assert private.selected_snapshot_set_identity_sha256 is not None


def test_selected_snapshot_set_hash_is_independently_projected_from_retained_metadata(
    tmp_path: Path,
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 5)
    try:
        private, report, request = _resolve(module, scenario)
        expected_hash = _expected_selected_snapshot_set(scenario)
    finally:
        scenario.close()

    assert private.selected_snapshot_set_identity_sha256 == expected_hash
    assert report.selected_snapshot_set_identity_sha256 == expected_hash
    _assert_public_redaction(report, private, request)


@pytest.mark.parametrize("kind", ("DIVIDEND", "BONUS", "SPLIT", "RIGHTS"))
@pytest.mark.parametrize("effective", (_S0, date(2026, 7, 20), _S20))
def test_supported_actions_at_every_inclusive_window_boundary_fail_closed(
    tmp_path: Path, kind: str, effective: date
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1, snapshots=False)
    try:
        _retain_snapshot(scenario, scenario.manifest.members[0].isin, kind=kind, effective=effective)
        private, report, request = _resolve(module, scenario)
    finally:
        scenario.close()

    assert private.outcome == module.PrivateUpstoxActionScreenOutcomeV1.ACTION_OBSERVED
    assert private.decision_session_close_at == _CLOSE
    assert private.selected_snapshot_set_identity_sha256 is None
    assert report.screen_state is None and report.decision_session_close_at is None
    assert report.reason == "CORPORATE_ACTION_SCREEN_INSUFFICIENT"
    _assert_public_redaction(report, private, request)


@pytest.mark.parametrize("effective", (_S0 - timedelta(days=1), _S20 + timedelta(days=1)))
@pytest.mark.parametrize("kind", ("DIVIDEND", "BONUS", "SPLIT", "RIGHTS"))
def test_supported_action_outside_window_does_not_block_provider_limited_screen(
    tmp_path: Path, kind: str, effective: date
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1, snapshots=False)
    try:
        _retain_snapshot(scenario, scenario.manifest.members[0].isin, kind=kind, effective=effective)
        private, report, request = _resolve(module, scenario)
    finally:
        scenario.close()

    assert private.outcome == module.PrivateUpstoxActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
    assert report.screen_state == module.CurrentSuppliedCohortUpstoxActionScreenStateV1.SCREENED
    assert report.coverage_limitation == "UPSTOX_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE"
    _assert_public_redaction(report, private, request)


@pytest.mark.parametrize(
    ("effective", "record_date", "expected"),
    (
        (_S0 - timedelta(days=1), _S20, "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"),
        (_S20, _S20 + timedelta(days=1), "ACTION_OBSERVED"),
    ),
)
def test_only_plan09_effective_date_not_record_or_provider_ex_date_controls_window(
    tmp_path: Path, effective: date, record_date: date, expected: str
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1, snapshots=False)
    try:
        _retain_snapshot(
            scenario, scenario.manifest.members[0].isin, kind="DIVIDEND",
            effective=effective, record_date=record_date,
        )
        private, report, request = _resolve(module, scenario)
    finally:
        scenario.close()

    assert private.outcome.value == expected
    _assert_public_redaction(report, private, request)


def test_date_only_event_visibility_reuses_plan09_without_expanding_the_screen(tmp_path: Path) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1, snapshots=False)
    try:
        _retain_snapshot(scenario, scenario.manifest.members[0].isin, kind="DIVIDEND", effective=_S20)
        private, report, request = _resolve(module, scenario)
    finally:
        scenario.close()

    assert private.outcome == module.PrivateUpstoxActionScreenOutcomeV1.ACTION_OBSERVED
    assert report.reason == "CORPORATE_ACTION_SCREEN_INSUFFICIENT"


@pytest.mark.parametrize(
    ("scenario_kwargs", "overrides", "expected"),
    (
        ({}, {"schedule_evidence_sha256": "a" * 64}, "SCHEDULE_MISSING"),
        (
            {"retained_schedule_source": "other-authoritative-calendar"},
            {},
            "SCHEDULE_AMBIGUOUS",
        ),
        (
            {"retained_schedule_release": "sha256:" + "c" * 64},
            {},
            "SCHEDULE_AMBIGUOUS",
        ),
        ({"snapshots": False}, {"decision_cutoff": datetime(2026, 8, 3, 9, 59, tzinfo=UTC)}, "SCHEDULE_LATE"),
        ({}, {"comparison_session": date(2026, 7, 7)}, "SCHEDULE_CONTINUITY_UNPROVEN"),
        ({}, {"decision_session": date(2026, 7, 31)}, "SCHEDULE_CONTINUITY_UNPROVEN"),
    ),
)
def test_schedule_binding_close_and_exact_twenty_position_failures_are_private_and_generic(
    tmp_path: Path,
    scenario_kwargs: dict[str, object],
    overrides: dict[str, object],
    expected: str,
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1, **scenario_kwargs)
    if "decision_cutoff" in overrides:
        scenario.manifest = CurrentSuppliedCohortManifestV1(
            datetime(2026, 7, 6, 12, tzinfo=UTC), scenario.manifest.members
        )
    try:
        resolver = module.PrivateUpstoxActionScreenResolverV1(
            scenario.schedule_store, scenario.action_store
        )
        request = _request(module, scenario, **overrides)
        private = resolver.resolve_exact(request, scenario.lease)
        report = private.to_public_report()
    finally:
        scenario.close()

    assert private.outcome.value == expected
    assert private.decision_session_close_at is None
    assert private.selected_snapshot_set_identity_sha256 is None
    _assert_public_redaction(report, private, request)


@pytest.mark.parametrize(("kind", "retrieved_at", "expected"), (
    (None, None, "MISSING"),
    (None, _CLOSE - timedelta(microseconds=1), "STALE"),
    (None, _CUTOFF + timedelta(microseconds=1), "STALE"),
    ("DIVIDEND", _CUTOFF, "AMBIGUOUS"),
))
def test_plan09_missing_stale_ambiguous_and_latest_snapshot_semantics(
    tmp_path: Path, kind: str | None, retrieved_at: datetime | None, expected: str
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1, snapshots=False)
    try:
        if retrieved_at is not None:
            _retain_snapshot(
                scenario, scenario.manifest.members[0].isin, retrieved_at=retrieved_at
            )
        if kind is not None:
            _retain_snapshot(
                scenario, scenario.manifest.members[0].isin, kind=kind,
                effective=_S0 - timedelta(days=1), retrieved_at=_CUTOFF,
            )
        private, report, request = _resolve(module, scenario)
    finally:
        scenario.close()

    assert private.outcome.value == expected
    assert private.decision_session_close_at == _CLOSE
    assert private.selected_snapshot_set_identity_sha256 is None
    assert report.reason == "CORPORATE_ACTION_SCREEN_INSUFFICIENT"
    _assert_public_redaction(report, private, request)


@pytest.mark.parametrize("case", ("root_replaced", "snapshot_directory_replaced"))
def test_action_read_attachment_revalidation_maps_to_corrupt_and_generic_public_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1)
    metadata = scenario.snapshot_metadata[scenario.manifest.members[0].isin]
    displaced = tmp_path / f"{case}.displaced"
    original_read = action_module.read_bounded_storage_object
    try:
        def read_then_replace(*args: Any, **kwargs: Any) -> bytes:
            payload = original_read(*args, **kwargs)
            if case == "root_replaced":
                scenario.root.rename(displaced)
                scenario.root.mkdir(mode=0o700)
            else:
                digest_directory = (scenario.root / metadata.relative_object_path).parent
                digest_directory.rename(displaced)
                digest_directory.mkdir(mode=0o700)
            return payload

        monkeypatch.setattr(action_module, "read_bounded_storage_object", read_then_replace)
        resolver = module.PrivateUpstoxActionScreenResolverV1(
            scenario.schedule_store, scenario.action_store
        )
        request = _request(module, scenario)
        private = resolver.resolve_exact(request, scenario.lease)
        report = private.to_public_report()
    finally:
        scenario.close()

    assert private.outcome == module.PrivateUpstoxActionScreenOutcomeV1.CORRUPT
    _assert_public_redaction(report, private, request)


@pytest.mark.parametrize(
    ("overrides", "generic_outcome"),
    (
        ({"corporate_action_source": "other-provider"}, None),
        ({"corporate_action_source_identity_sha256": "a" * 64}, None),
        ({"snapshot_schema_identity_sha256": "a" * 64}, None),
        ({"screen_schema_identity_sha256": "a" * 64}, None),
        ({"screen_policy_identity_sha256": "a" * 64}, None),
        ({"schedule_evidence_sha256": "a" * 64}, "SCHEDULE_MISSING"),
        ({"schedule_source": "other-authoritative-calendar"}, None),
        ({"schedule_source_release": "sha256:" + "c" * 64}, "SCHEDULE_AMBIGUOUS"),
        ({"corporate_action_source": ""}, None),
        ({"corporate_action_source_identity_sha256": "A" * 64}, None),
        ({"snapshot_schema_identity_sha256": "sha256:" + "a" * 64}, None),
        ({"screen_schema_identity_sha256": "0" * 63}, None),
        ({"screen_policy_identity_sha256": "A" * 64}, None),
        ({"schedule_evidence_sha256": "A" * 64}, None),
        ({"schedule_source": ""}, None),
        ({"schedule_source_release": "sha256:" + "A" * 64}, None),
    ),
)
def test_every_frozen_input_binding_rejects_structurally_or_maps_valid_schedule_mismatches(
    tmp_path: Path, overrides: dict[str, object], generic_outcome: str | None
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        if generic_outcome is None:
            with pytest.raises(ValueError):
                _input(module, scenario, **overrides)
        else:
            request = _request(module, scenario, **overrides)
            private = module.PrivateUpstoxActionScreenResolverV1(
                scenario.schedule_store, scenario.action_store
            ).resolve_exact(request, scenario.lease)
            report = private.to_public_report()
            assert private.outcome.value == generic_outcome
            _assert_public_redaction(report, private, request)
    finally:
        scenario.close()

_PRIVATE_FIELDS = (
    "cohort_identity_sha256", "comparison_session", "decision_session",
    "decision_session_close_at", "decision_cutoff", "schedule_evidence_sha256",
    "schedule_source", "schedule_source_release", "source_identity_sha256",
    "snapshot_schema_identity_sha256", "outcome",
    "selected_snapshot_set_identity_sha256",
)


def _closed_schema_bytes(value: Any, mutation: str, wrong_field: str) -> bytes:
    raw = json.loads(_canonical(value))
    if mutation == "unknown":
        raw["unexpected"] = 0
    elif mutation == "missing":
        raw.pop(next(iter(raw)))
    elif mutation == "wrong_type":
        raw[wrong_field] = 0
    elif mutation == "conditional_nullability":
        raw[wrong_field] = None if raw[wrong_field] is not None else "not-null"
    else:
        raise AssertionError(f"unknown mutation {mutation}")
    return json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


@pytest.mark.parametrize("mutation", ("unknown", "missing", "wrong_type", "conditional_nullability"))
def test_all_frozen_dtos_canonically_roundtrip_and_reject_closed_shape_violations(
    tmp_path: Path, mutation: str
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        input_value = _input(module, scenario)
        request = _request(module, scenario)
        private, report, _ = _resolve(module, scenario)
        cases = (
            (input_value, "decision_cutoff"),
            (request, "cohort_manifest"),
            (private, "selected_snapshot_set_identity_sha256"),
            (report, "reason"),
        )
        for value, field_name in cases:
            parser = type(value).from_canonical_json_bytes
            assert parser(_canonical(value)) == value
            with pytest.raises(ValueError):
                parser(_closed_schema_bytes(value, mutation, field_name))
    finally:
        scenario.close()


def test_input_request_private_and_public_types_have_exact_fields_nullability_and_hashes(
    tmp_path: Path,
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        input_value = _input(module, scenario)
        request = _request(module, scenario)
        private, report, request = _resolve(module, scenario)
    finally:
        scenario.close()

    assert tuple(input_value.value()) == (
        "contract_version", "cohort_manifest", "comparison_session", "decision_session",
        "decision_cutoff", "schedule_evidence_sha256", "schedule_source", "schedule_source_release",
        "corporate_action_source", "corporate_action_source_identity_sha256", "snapshot_schema_identity_sha256",
        "screen_schema_identity_sha256", "screen_policy_identity_sha256", "input_identity_sha256",
    )
    assert tuple(request.value()) == (
        "contract_version", "input_identity_sha256", "cohort_manifest",
        "comparison_session", "decision_session", "decision_cutoff",
        "schedule_evidence_sha256", "schedule_source", "schedule_source_release",
        "corporate_action_source", "corporate_action_source_identity_sha256",
        "snapshot_schema_identity_sha256", "screen_schema_identity_sha256",
        "screen_policy_identity_sha256", "request_identity_sha256",
    )
    assert tuple(private.value()) == _PRIVATE_FIELDS
    assert input_value.input_identity_sha256 == hashlib.sha256(input_value.canonical_json_bytes(include_identity=False)).hexdigest()
    assert request.request_identity_sha256 == hashlib.sha256(request.canonical_json_bytes(include_identity=False)).hexdigest()
    assert report.report_identity_sha256 == hashlib.sha256(report.canonical_json_bytes(include_identity=False)).hexdigest()
    assert private.selected_snapshot_set_identity_sha256 == _expected_selected_snapshot_set(scenario)
    _assert_public_redaction(report, private, request)


def _retained_tree_state(root: Path) -> tuple[tuple[str, int, str], ...]:
    entries: list[tuple[str, int, str]] = []
    for directory, names, files in os.walk(root):
        names.sort()
        for name in sorted(files):
            path = Path(directory) / name
            entries.append((
                str(path.relative_to(root)),
                path.stat().st_mode & 0o777,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            ))
    return tuple(entries)


def _catalog_state(catalog: DuckDBCatalog) -> tuple[tuple[object, ...], ...]:
    return tuple(catalog.connection.execute(
        "SELECT * FROM corporate_action_snapshots ORDER BY isin, snapshot_sha256"
    ).fetchall())


def test_resolver_has_zero_effects_and_uses_only_exact_schedule_and_manifest_resolutions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 5)
    tree_before, catalog_before = _retained_tree_state(scenario.root), _catalog_state(scenario.catalog)
    schedule_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    action_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    original_schedule_resolve = scenario.schedule_store.resolve
    original_action_resolve = scenario.action_store.resolve
    try:
        def schedule_resolve(*args: object, **kwargs: object) -> Any:
            schedule_calls.append((args, kwargs))
            return original_schedule_resolve(*args, **kwargs)

        def action_resolve(*args: object, **kwargs: object) -> Any:
            action_calls.append((args, kwargs))
            return original_action_resolve(*args, **kwargs)

        with monkeypatch.context() as traps:
            traps.setattr(scenario.schedule_store, "resolve", schedule_resolve)
            traps.setattr(scenario.action_store, "resolve", action_resolve)
            def forbidden(*_args: object, **_kwargs: object) -> None:
                raise AssertionError("Plan-21 resolver performed a forbidden effect")

            for owner, name in (
                (os, "listdir"), (os, "scandir"), (os, "write"), (os, "replace"),
                (os, "rename"), (os, "unlink"), (os, "mkdir"), (socket, "create_connection"),
                (time, "sleep"), (Path, "iterdir"), (Path, "glob"), (Path, "rglob"),
                (Path, "write_bytes"), (Path, "mkdir"),
                (UpstoxCorporateActionsClientV1, "fetch"),
                (CorporateActionSnapshotStoreV1, "retain"),
                (ScheduleEvidenceStore, "retain"),
                (action_module.AdjustmentAvailabilityServiceV1, "inspect"),
            ):
                traps.setattr(owner, name, forbidden)
            private, report, request = _resolve(module, scenario)
    finally:
        tree_after, catalog_after = _retained_tree_state(scenario.root), _catalog_state(scenario.catalog)
        scenario.close()

    assert private.outcome == module.PrivateUpstoxActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
    assert schedule_calls == [((scenario.schedule_sha256,), {})]
    assert len(action_calls) == len(scenario.manifest.members)
    assert {
        (call_args, tuple(sorted(call_kwargs.items())))
        for call_args, call_kwargs in action_calls
    } == {
        ((), (("isin", member.isin), ("knowledge_cutoff", _CUTOFF)))
        for member in scenario.manifest.members
    }
    assert tree_after == tree_before
    assert catalog_after == catalog_before
    _assert_public_redaction(report, private, request)


def test_retained_noncohort_action_is_never_resolved_or_screened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1)
    outsider = _valid_isin(99)
    _retain_snapshot(scenario, outsider, kind="RIGHTS", effective=_S20)
    calls: list[dict[str, object]] = []
    original_resolve = scenario.action_store.resolve
    try:
        def resolve(*args: object, **kwargs: object) -> Any:
            calls.append(kwargs)
            return original_resolve(*args, **kwargs)

        monkeypatch.setattr(scenario.action_store, "resolve", resolve)
        private, report, request = _resolve(module, scenario)
    finally:
        scenario.close()

    assert private.outcome == module.PrivateUpstoxActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
    assert calls == [{
        "isin": scenario.manifest.members[0].isin,
        "knowledge_cutoff": _CUTOFF,
    }]
    _assert_public_redaction(report, private, request)




def test_public_n1_action_insufficiency_cannot_disclose_event_or_claim_no_break(tmp_path: Path) -> None:
    module = _api()
    scenario = _scenario(tmp_path, 1, snapshots=False)
    try:
        _retain_snapshot(scenario, scenario.manifest.members[0].isin, kind="SPLIT", effective=_S20)
        private, report, request = _resolve(module, scenario)
    finally:
        scenario.close()

    assert private.outcome == module.PrivateUpstoxActionScreenOutcomeV1.ACTION_OBSERVED
    _assert_public_redaction(report, private, request)
