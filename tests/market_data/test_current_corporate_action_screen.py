"""Focused provider-neutral Plan-21 current corporate-action screen contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from swing_trading_ai_assistant.market_data import current_corporate_action_screen
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.corporate_actions import (
    CorporateActionAmbiguousError,
    CorporateActionCorruptError,
    CorporateActionMissingError,
    CorporateActionSnapshotStoreV1,
    CorporateActionStaleError,
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
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)

_SOURCE = "upstox-fundamentals-v2"
_RELEASE = "sha256:" + "b" * 64
_S0 = date(2026, 7, 6)
_S20 = date(2026, 8, 3)
_CLOSE = datetime(2026, 8, 3, 10, tzinfo=UTC)
_CUTOFF = datetime(2026, 8, 4, 12, tzinfo=UTC)
_SELECTED_AT = datetime(2026, 8, 4, 12, tzinfo=UTC)


class _Transport:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        assert url and headers
        return HttpResponse(200, self.payload)


@dataclass
class _Scenario:
    root: Path
    lease: StorageRootLease
    catalog: DuckDBCatalog
    schedule_store: ScheduleEvidenceStore
    action_store: CorporateActionSnapshotStoreV1
    manifest: CurrentSuppliedCohortManifestV1
    schedule_sha256: str

    def close(self) -> None:
        self.catalog.__exit__(None, None, None)
        self.lease.close()


def _isin(index: int) -> str:
    prefix = f"INE{index:05d}A01"
    for check in range(10):
        candidate = prefix + str(check)
        total = 0
        for position, character in enumerate(
            reversed("".join(str(ord(c) - 55) if c.isalpha() else c for c in candidate))
        ):
            digit = int(character)
            if position % 2:
                digit *= 2
                digit = digit // 10 + digit % 10
            total += digit
        if total % 10 == 0:
            return candidate
    raise AssertionError


def _schedule() -> ExpectedSessionSchedule:
    sessions = tuple(
        ScheduleSession(
            day,
            datetime(2026, 7, 6, 3, 45, tzinfo=UTC) + timedelta(days=offset),
            datetime(2026, 7, 6, 10, tzinfo=UTC) + timedelta(days=offset),
            "REGULAR",
        )
        for offset in range((_S20 - _S0).days + 1)
        if (day := _S0 + timedelta(days=offset)).weekday() < 5
    )
    closures = tuple(
        ScheduleClosure(day, "WEEKEND")
        for offset in range((_S20 - _S0).days + 1)
        if (day := _S0 + timedelta(days=offset)).weekday() >= 5
    )
    return ExpectedSessionSchedule(
        SCHEDULE_SCHEMA_VERSION_V2,
        "nse-authoritative-calendar",
        _RELEASE,
        _CUTOFF,
        "Asia/Kolkata",
        _S0,
        _S20,
        sessions,
        closures,
    )


def _payload(kind: str | None = None, effective: date = _S20) -> bytes:
    events: list[dict[str, object]] = []
    if kind:
        details = [
            {"name": "Record date", "value": effective.strftime("%d %b %Y")},
            {
                "name": "Announcement date",
                "value": min(_S0, effective).strftime("%d %b %Y"),
            },
            {
                "name": f"Ex {kind.lower()} date",
                "value": effective.strftime("%d %b %Y"),
            },
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
                ]
            )
        else:
            event["ratio"] = "1:1"
            details.append({"name": "Ratio", "value": "1:1"})
        events = [event]
    return json.dumps(
        {"data": events, "status": "success"}, separators=(",", ":")
    ).encode()


def _scenario(tmp_path: Path, count: int = 2, *, retain: bool = True) -> _Scenario:
    root = tmp_path / "retained"
    root.mkdir(mode=0o700)
    acquisition = StorageRootLease.try_acquire(root)
    assert (
        acquisition.outcome is LeaseOutcome.ACQUIRED and acquisition.lease is not None
    )
    lease = acquisition.lease
    catalog = DuckDBCatalog(root, lease=lease)
    catalog.__enter__()
    schedule_store = ScheduleEvidenceStore(root, lease)
    schedule = _schedule()
    digest = schedule_digest(schedule)
    schedule_store.retain(schedule)
    manifest = CurrentSuppliedCohortManifestV1(
        _SELECTED_AT,
        tuple(
            CurrentCohortMemberV1(_isin(index), f"EQ{index}")
            for index in range(1, count + 1)
        ),
    )
    scenario = _Scenario(
        root,
        lease,
        catalog,
        schedule_store,
        CorporateActionSnapshotStoreV1(root, lease, catalog),
        manifest,
        digest,
    )
    if retain:
        for member in manifest.members:
            scenario.action_store.retain(
                UpstoxCorporateActionsClientV1(
                    _Transport(_payload()), clock=lambda: _CUTOFF
                ).fetch(member.isin, "fixture-token")
            )
    return scenario


def _api() -> Any:
    return current_corporate_action_screen


def _input(api: Any, scenario: _Scenario, provider_id: str = "upstox") -> Any:
    return api.CurrentSuppliedCohortCorporateActionScreenInputV1(
        scenario.manifest,
        _S0,
        _S20,
        _CUTOFF,
        scenario.schedule_sha256,
        "nse-authoritative-calendar",
        _RELEASE,
        provider_id,
    )


def _resolve(api: Any, scenario: _Scenario) -> Any:
    return api.CurrentSuppliedCohortCorporateActionScreenResolverV1(
        scenario.schedule_store,
        api.UpstoxCorporateActionScreenProviderV1(scenario.action_store),
    ).resolve_exact(_input(api, scenario), scenario.lease)


def test_generic_public_contract_round_trip_and_no_old_names(tmp_path: Path) -> None:
    api = _api()
    scenario = _scenario(tmp_path)
    try:
        private = _resolve(api, scenario)
        report = private.to_public_report()
        assert report.screen_state is api.CorporateActionScreenStateV1.SCREENED
        assert (
            report.coverage_limitation
            is api.CorporateActionScreenCoverageLimitationV1.PROVIDER_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE
        )
        assert (
            report.runtime_code_identity_sha256
            == api.current_corporate_action_screen_runtime_code_identity_v1()
        )
        assert report.report_identity_sha256 == api._sha256(report.value(False))
        replay = api.PrivateCorporateActionScreenResultV1.from_canonical_json_bytes(
            private.canonical_json_bytes()
        )
        assert (
            replay.private_result_identity_sha256
            == private.private_result_identity_sha256
        )
        with pytest.raises(ValueError):
            replay.to_public_report()
        assert (
            api.CurrentSuppliedCohortCorporateActionScreenInputV1.from_canonical_json_bytes(
                _input(api, scenario).canonical_json_bytes()
            ).input_identity_sha256
            == _input(api, scenario).input_identity_sha256
        )
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(
            _input(api, scenario)
        )
        assert (
            api.CurrentSuppliedCohortCorporateActionScreenRequestV1.from_canonical_json_bytes(
                request.canonical_json_bytes()
            ).request_identity_sha256
            == request.request_identity_sha256
        )
        assert (
            api.CurrentSuppliedCohortCorporateActionScreenReportV1.from_canonical_json_bytes(
                report.canonical_json_bytes()
            ).report_identity_sha256
            == report.report_identity_sha256
        )
        adversarial = json.loads(report.canonical_json_bytes())
        adversarial["screen_state"] = None
        adversarial["reason"] = "CORPORATE_ACTION_SCREEN_INSUFFICIENT"
        with pytest.raises(ValueError):
            api.CurrentSuppliedCohortCorporateActionScreenReportV1.from_canonical_json_bytes(
                json.dumps(adversarial, sort_keys=True, separators=(",", ":")).encode()
                + b"\n"
            )
        for old in (
            "CurrentSuppliedCohort" + "UpstoxActionScreenInputV1",
            "Private" + "UpstoxActionScreenResultV1",
            "Private" + "UpstoxActionScreenResolverPortV1",
        ):
            assert not hasattr(api, old)
        assert (
            "upstox"
            not in str(
                api.CurrentSuppliedCohortCorporateActionScreenReportV1.__annotations__
            ).lower()
        )
    finally:
        scenario.close()


def test_adapter_mismatch_fails_before_schedule_or_provider_call(
    tmp_path: Path,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path)
    calls: list[str] = []

    @dataclass(frozen=True)
    class Fake:
        descriptor: Any

        def resolve_exact(self, request: Any, isin: str, lease: Any) -> Any:
            calls.append(isin)
            raise AssertionError

    try:
        fake = Fake(
            api.CorporateActionScreenProviderDescriptorV1(
                "other", "1" * 64, "2" * 64, "3" * 64, "4" * 64
            )
        )
        resolver = api.CurrentSuppliedCohortCorporateActionScreenResolverV1(
            scenario.schedule_store, fake
        )
        with pytest.raises(ValueError):
            resolver.resolve_exact(_input(api, scenario), scenario.lease)
        assert calls == []
    finally:
        scenario.close()


def test_exact_sorted_per_isin_calls_and_second_descriptor_port(tmp_path: Path) -> None:
    api = _api()
    scenario = _scenario(tmp_path, count=5)
    calls: list[str] = []
    descriptor = api.CorporateActionScreenProviderDescriptorV1(
        "fixture", "1" * 64, "2" * 64, "3" * 64, "4" * 64
    )

    @dataclass(frozen=True)
    class Fake:
        descriptor: Any

        def resolve_exact(self, request: Any, isin: str, lease: Any) -> Any:
            calls.append(isin)
            return api.PrivateCorporateActionScreenProviderResultV1(
                isin,
                self.descriptor.provider_id,
                self.descriptor.capability_identity_sha256,
                self.descriptor.source_identity_sha256,
                self.descriptor.snapshot_schema_identity_sha256,
                self.descriptor.policy_identity_sha256,
                "5" * 64,
                1,
                _CUTOFF,
                request.decision_cutoff,
                (),
                api.ProviderObservationOutcomeV1.AVAILABLE,
            )

    try:
        result = api.CurrentSuppliedCohortCorporateActionScreenResolverV1(
            scenario.schedule_store, Fake(descriptor)
        ).resolve_exact(_input(api, scenario, "fixture"), scenario.lease)
        assert calls == sorted(member.isin for member in scenario.manifest.members)
        assert (
            result.outcome
            is api.PrivateCorporateActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
        )
        assert result.selected_snapshot_set_identity_sha256 is not None
    finally:
        scenario.close()


@pytest.mark.parametrize("kind", ["BONUS", "SPLIT", "RIGHTS"])
def test_upstox_adapter_maps_all_supported_non_dividend_kinds(
    tmp_path: Path, kind: str
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, count=1, retain=False)
    try:
        isin = scenario.manifest.members[0].isin
        scenario.action_store.retain(
            UpstoxCorporateActionsClientV1(
                _Transport(_payload(kind)), clock=lambda: _CUTOFF
            ).fetch(isin, "fixture-token")
        )
        result = _resolve(api, scenario)
        assert (
            result.outcome is api.PrivateCorporateActionScreenOutcomeV1.ACTION_OBSERVED
        )
        assert (
            result.to_public_report().reason
            is api.CorporateActionScreenReasonV1.CORPORATE_ACTION_SCREEN_INSUFFICIENT
        )
    finally:
        scenario.close()


def test_missing_snapshot_is_insufficient_after_matching_provider(
    tmp_path: Path,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, retain=False)
    try:
        result = _resolve(api, scenario)
        assert result.outcome is api.PrivateCorporateActionScreenOutcomeV1.MISSING
        report = result.to_public_report()
        assert (
            report.screen_state is None
            and report.reason
            is api.CorporateActionScreenReasonV1.CORPORATE_ACTION_SCREEN_INSUFFICIENT
        )
    finally:
        scenario.close()


@pytest.mark.parametrize(
    ("error_type", "expected"),
    [
        (CorporateActionMissingError, "MISSING"),
        (CorporateActionStaleError, "STALE"),
        (CorporateActionAmbiguousError, "AMBIGUOUS"),
        (CorporateActionCorruptError, "CORRUPT"),
    ],
)
def test_upstox_adapter_maps_each_plan09_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
    expected: str,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, count=1)
    try:

        def fail(**_kwargs: object) -> None:
            raise error_type("fixture")

        monkeypatch.setattr(scenario.action_store, "resolve", fail)
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(
            _input(api, scenario)
        )
        result = api.UpstoxCorporateActionScreenProviderV1(
            scenario.action_store
        ).resolve_exact(request, scenario.manifest.members[0].isin, scenario.lease)
        assert result.outcome.value == expected
        assert result.snapshot_identity_sha256 is None
    finally:
        scenario.close()


@pytest.mark.parametrize("count", (1, 5, 50))
def test_ready_empty_snapshots_cover_every_permitted_cohort_size(
    tmp_path: Path, count: int
) -> None:
    scenario = _scenario(tmp_path, count)
    try:
        result = _resolve(_api(), scenario)
        assert result.outcome.value == "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"
        assert len(result.member_results) == count
    finally:
        scenario.close()


@pytest.mark.parametrize("kind", ("DIVIDEND", "BONUS", "SPLIT", "RIGHTS"))
@pytest.mark.parametrize(
    ("effective", "expected"),
    (
        (_S0 - timedelta(days=1), "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"),
        (_S0, "ACTION_OBSERVED"),
        (_S0 + timedelta(days=10), "ACTION_OBSERVED"),
        (_S20, "ACTION_OBSERVED"),
        (_S20 + timedelta(days=1), "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"),
    ),
)
def test_all_supported_kinds_use_only_inclusive_effective_date_window(
    tmp_path: Path, kind: str, effective: date, expected: str
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1, retain=False)
    try:
        isin = scenario.manifest.members[0].isin
        scenario.action_store.retain(
            UpstoxCorporateActionsClientV1(
                _Transport(_payload(kind, effective)), clock=lambda: _CUTOFF
            ).fetch(isin, "fixture-token")
        )
        assert _resolve(api, scenario).outcome.value == expected
    finally:
        scenario.close()


def _fake_provider(
    api: Any,
    descriptor: Any,
    outcomes: tuple[Any, ...],
    retrieved_at: datetime = _CUTOFF,
) -> Any:
    @dataclass(frozen=True)
    class Fake:
        descriptor: Any
        outcomes: tuple[Any, ...]

        def resolve_exact(self, request: Any, isin: str, lease: Any) -> Any:
            outcome = self.outcomes[len(calls)]
            calls.append(isin)
            if outcome is not api.ProviderObservationOutcomeV1.AVAILABLE:
                return api.PrivateCorporateActionScreenProviderResultV1(
                    isin,
                    self.descriptor.provider_id,
                    self.descriptor.capability_identity_sha256,
                    self.descriptor.source_identity_sha256,
                    self.descriptor.snapshot_schema_identity_sha256,
                    self.descriptor.policy_identity_sha256,
                    None,
                    None,
                    None,
                    request.decision_cutoff,
                    (),
                    outcome,
                )
            return api.PrivateCorporateActionScreenProviderResultV1(
                isin,
                self.descriptor.provider_id,
                self.descriptor.capability_identity_sha256,
                self.descriptor.source_identity_sha256,
                self.descriptor.snapshot_schema_identity_sha256,
                self.descriptor.policy_identity_sha256,
                "5" * 64,
                1,
                retrieved_at,
                request.decision_cutoff,
                (),
                outcome,
            )

    calls: list[str] = []
    return Fake(descriptor, outcomes), calls


@pytest.mark.parametrize(
    ("provider_outcome", "retrieved_at", "expected"),
    (
        ("MISSING", _CUTOFF, "MISSING"),
        ("STALE", _CUTOFF, "STALE"),
        ("AMBIGUOUS", _CUTOFF, "AMBIGUOUS"),
        ("CORRUPT", _CUTOFF, "CORRUPT"),
        ("AVAILABLE", _CLOSE - timedelta(microseconds=1), "STALE"),
        ("AVAILABLE", _CLOSE, "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"),
        ("AVAILABLE", _CUTOFF, "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"),
    ),
)
def test_generic_provider_observation_is_classified_only_by_aggregate(
    tmp_path: Path, provider_outcome: str, retrieved_at: datetime, expected: str
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    descriptor = api.CorporateActionScreenProviderDescriptorV1(
        "fixture", "1" * 64, "2" * 64, "3" * 64, "4" * 64
    )
    try:
        outcome = api.ProviderObservationOutcomeV1(provider_outcome)
        provider, calls = _fake_provider(api, descriptor, (outcome,), retrieved_at)
        result = api.CurrentSuppliedCohortCorporateActionScreenResolverV1(
            scenario.schedule_store, provider
        ).resolve_exact(_input(api, scenario, "fixture"), scenario.lease)
        assert calls == [scenario.manifest.members[0].isin]
        assert result.outcome.value == expected
    finally:
        scenario.close()


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    (
        (("MISSING", "STALE"), "MISSING"),
        (("STALE", "AMBIGUOUS"), "STALE"),
        (("AMBIGUOUS", "CORRUPT"), "AMBIGUOUS"),
        (("CORRUPT", "AVAILABLE"), "CORRUPT"),
        (("AVAILABLE", "MISSING"), "MISSING"),
        (("AVAILABLE", "AVAILABLE"), "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"),
    ),
)
def test_mixed_member_outcomes_use_frozen_precedence(
    tmp_path: Path, outcomes: tuple[str, str], expected: str
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 2)
    descriptor = api.CorporateActionScreenProviderDescriptorV1(
        "fixture", "1" * 64, "2" * 64, "3" * 64, "4" * 64
    )
    try:
        provider, _ = _fake_provider(
            api,
            descriptor,
            tuple(api.ProviderObservationOutcomeV1(item) for item in outcomes),
        )
        result = api.CurrentSuppliedCohortCorporateActionScreenResolverV1(
            scenario.schedule_store, provider
        ).resolve_exact(_input(api, scenario, "fixture"), scenario.lease)
        assert result.outcome.value == expected
    finally:
        scenario.close()


@pytest.mark.parametrize(
    ("schedule", "expected"),
    (
        (None, "SCHEDULE_UNAVAILABLE"),
        (_schedule(), None),
        (replace(_schedule(), source="other"), "SCHEDULE_UNAVAILABLE"),
    ),
)
def test_schedule_admission_handles_exact_source_and_availability(
    tmp_path: Path, schedule: object, expected: str | None
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(
            _input(api, scenario)
        )
        outcome, close = api._schedule_close(request, schedule)
        if expected is None:
            assert outcome is None
            assert close == _CLOSE
        else:
            assert outcome is not None and outcome.value == expected
            assert close is None
    finally:
        scenario.close()


@pytest.mark.parametrize(
    "mutation",
    ("unknown", "missing", "wrong_type", "conditional_nullability"),
)
def test_provider_result_canonical_schema_is_closed(
    tmp_path: Path, mutation: str
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(
            _input(api, scenario)
        )
        result = api.UpstoxCorporateActionScreenProviderV1(
            scenario.action_store
        ).resolve_exact(request, scenario.manifest.members[0].isin, scenario.lease)
        raw = json.loads(result.canonical_json_bytes())
        if mutation == "unknown":
            raw["unexpected"] = 0
        elif mutation == "missing":
            raw.pop("knowledge_cutoff")
        elif mutation == "wrong_type":
            raw["snapshot_byte_count"] = "one"
        else:
            raw["snapshot_identity_sha256"] = None
        with pytest.raises(ValueError):
            api.PrivateCorporateActionScreenProviderResultV1.from_canonical_json_bytes(
                json.dumps(raw, sort_keys=True, separators=(",", ":")).encode() + b"\n"
            )
    finally:
        scenario.close()


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("snapshot_sha256", "0" * 64),
        ("byte_count", 1),
        ("event_count", 1),
    ),
)
def test_upstox_adapter_rejects_exact_metadata_tuple_substitutions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    replacement: object,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    original = scenario.action_store.resolve
    try:

        def substituted(**kwargs: object) -> tuple[Any, Any]:
            metadata, snapshot = original(**kwargs)
            object.__setattr__(metadata, field, replacement)
            return metadata, snapshot

        monkeypatch.setattr(scenario.action_store, "resolve", substituted)
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(
            _input(api, scenario)
        )
        result = api.UpstoxCorporateActionScreenProviderV1(
            scenario.action_store
        ).resolve_exact(request, scenario.manifest.members[0].isin, scenario.lease)
        assert result.outcome is api.ProviderObservationOutcomeV1.CORRUPT
    finally:
        scenario.close()


@pytest.mark.parametrize(
    ("effective", "expected"),
    (
        (_S0 - timedelta(days=1), "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"),
        (_S0, "ACTION_OBSERVED"),
        (_S20, "ACTION_OBSERVED"),
        (_S20 + timedelta(days=1), "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"),
    ),
)
def test_aggregate_event_classification_is_independent_of_provider_adapter(
    tmp_path: Path, effective: date, expected: str
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    descriptor = api.CorporateActionScreenProviderDescriptorV1(
        "fixture", "1" * 64, "2" * 64, "3" * 64, "4" * 64
    )
    event = api.NormalizedSupportedCorporateActionEventV1(
        api.SupportedCorporateActionKindV1.SPLIT, effective
    )
    try:

        @dataclass(frozen=True)
        class Fake:
            descriptor: Any

            def resolve_exact(self, request: Any, isin: str, lease: Any) -> Any:
                return api.PrivateCorporateActionScreenProviderResultV1(
                    isin,
                    "fixture",
                    "1" * 64,
                    "2" * 64,
                    "3" * 64,
                    "4" * 64,
                    "5" * 64,
                    1,
                    _CUTOFF,
                    request.decision_cutoff,
                    (event,),
                    api.ProviderObservationOutcomeV1.AVAILABLE,
                )

        resolved = api.CurrentSuppliedCohortCorporateActionScreenResolverV1(
            scenario.schedule_store, Fake(descriptor)
        ).resolve_exact(_input(api, scenario, "fixture"), scenario.lease)
        assert resolved.outcome.value == expected
    finally:
        scenario.close()


def test_stores_expose_only_read_only_root_and_lease_bindings(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path, 1)
    try:
        assert scenario.schedule_store.storage_root == scenario.root
        assert scenario.action_store.storage_root == scenario.root
        assert scenario.schedule_store.lease is scenario.lease
        assert scenario.action_store.lease is scenario.lease
    finally:
        scenario.close()


def test_runtime_identity_is_reused_by_private_and_public_results(
    tmp_path: Path,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        private = _resolve(api, scenario)
        assert private.runtime_code_identity_sha256 == (
            private.to_public_report().runtime_code_identity_sha256
        )
    finally:
        scenario.close()


@pytest.mark.parametrize(
    "schema_version", (SCHEDULE_SCHEMA_VERSION_V2, SCHEDULE_SCHEMA_VERSION_V3)
)
def test_both_schedule_schema_versions_derive_exact_twenty_position_close(
    tmp_path: Path, schema_version: int
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        schedule = replace(_schedule(), schema_version=schema_version)
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(
            _input(api, scenario)
        )
        outcome, close = api._schedule_close(request, schedule)
        assert outcome is None and close == _CLOSE
    finally:
        scenario.close()


@pytest.mark.parametrize(
    ("sessions", "cutoff", "expected"),
    (
        (_schedule().sessions, _CUTOFF, None),
        (
            _schedule().sessions,
            _CLOSE - timedelta(microseconds=1),
            "SCHEDULE_LATE",
        ),
        (_schedule().sessions[:-1], _CUTOFF, "SCHEDULE_CONTINUITY_UNPROVEN"),
    ),
)
def test_schedule_close_and_continuity_boundaries(
    tmp_path: Path,
    sessions: tuple[ScheduleSession, ...],
    cutoff: datetime,
    expected: str | None,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        schedule = replace(_schedule(), sessions=sessions)
        input_value = api.CurrentSuppliedCohortCorporateActionScreenInputV1(
            CurrentSuppliedCohortManifestV1(
                datetime(2026, 7, 6, 12, tzinfo=UTC), scenario.manifest.members
            ),
            _S0,
            _S20,
            cutoff,
            scenario.schedule_sha256,
            "nse-authoritative-calendar",
            _RELEASE,
            "upstox",
        )
        outcome, _ = api._schedule_close(
            api.CurrentSuppliedCohortCorporateActionScreenRequestV1(input_value),
            schedule,
        )
        assert (None if outcome is None else outcome.value) == expected
    finally:
        scenario.close()


@pytest.mark.parametrize("byte_count", (1, 2))
def test_selected_set_projection_binds_snapshot_byte_count(
    tmp_path: Path, byte_count: int
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    descriptor = api.CorporateActionScreenProviderDescriptorV1(
        "fixture", "1" * 64, "2" * 64, "3" * 64, "4" * 64
    )
    try:
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(
            _input(api, scenario, "fixture")
        )
        provider = api.PrivateCorporateActionScreenProviderResultV1(
            scenario.manifest.members[0].isin,
            "fixture",
            "1" * 64,
            "2" * 64,
            "3" * 64,
            "4" * 64,
            "5" * 64,
            byte_count,
            _CUTOFF,
            request.decision_cutoff,
            (),
            api.ProviderObservationOutcomeV1.AVAILABLE,
        )
        row = api.PrivateCorporateActionScreenMemberResultV1(
            provider, api.AggregateMemberOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
        )
        assert api._selected_snapshot_set_hash(request, descriptor, "6" * 64, [row])
    finally:
        scenario.close()


def test_request_exposes_no_derived_close_and_member_rows_are_private(
    tmp_path: Path,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(
            _input(api, scenario)
        )
        private = _resolve(api, scenario)
        report_bytes = private.to_public_report().canonical_json_bytes()
        assert not hasattr(request, "derived" + "_decision_session_close_at")
        assert private.member_results and b"INE" not in report_bytes
    finally:
        scenario.close()


def test_invalid_provider_result_is_mapped_to_corrupt_after_the_exact_call(
    tmp_path: Path,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    descriptor = api.CorporateActionScreenProviderDescriptorV1(
        "fixture", "1" * 64, "2" * 64, "3" * 64, "4" * 64
    )
    try:

        @dataclass(frozen=True)
        class Fake:
            descriptor: Any

            def resolve_exact(self, request: Any, isin: str, lease: Any) -> Any:
                result = api.PrivateCorporateActionScreenProviderResultV1(
                    isin,
                    "fixture",
                    "1" * 64,
                    "2" * 64,
                    "3" * 64,
                    "4" * 64,
                    "5" * 64,
                    1,
                    _CUTOFF,
                    request.decision_cutoff,
                    (),
                    api.ProviderObservationOutcomeV1.AVAILABLE,
                )
                object.__setattr__(
                    result,
                    "retrieved_at",
                    request.decision_cutoff + timedelta(microseconds=1),
                )
                return result

        resolved = api.CurrentSuppliedCohortCorporateActionScreenResolverV1(
            scenario.schedule_store, Fake(descriptor)
        ).resolve_exact(_input(api, scenario, "fixture"), scenario.lease)
        assert resolved.outcome.value == "CORRUPT"
    finally:
        scenario.close()


def test_admitted_request_is_isolated_from_input_manifest_mutation(
    tmp_path: Path,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        input_value = _input(api, scenario)
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(input_value)
        object.__setattr__(input_value.cohort_manifest, "members", ())
        assert len(request.cohort_manifest.members) == 1
    finally:
        scenario.close()


@pytest.mark.parametrize("provider_id", ("UPSTOX", "", "provider_with_underscore"))
def test_provider_descriptor_rejects_noncanonical_provider_ids(
    provider_id: str,
) -> None:
    api = _api()
    with pytest.raises(ValueError):
        api.CorporateActionScreenProviderDescriptorV1(
            provider_id, "1" * 64, "2" * 64, "3" * 64, "4" * 64
        )


def test_private_canonical_replay_is_non_authorizing_even_after_row_reduction(
    tmp_path: Path,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 50)
    try:
        private = _resolve(api, scenario)
        replay = json.loads(private.canonical_json_bytes())
        replay["member_results"] = replay["member_results"][:1]
        replay["selected_snapshot_set_identity_sha256"] = "f" * 64
        replay.pop("private_result_identity_sha256")
        replay["private_result_identity_sha256"] = api._sha256(replay)
        restored = api.PrivateCorporateActionScreenResultV1.from_canonical_json_bytes(
            json.dumps(replay, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        )
        assert len(restored.member_results) == 1
        with pytest.raises(ValueError):
            restored.to_public_report()
    finally:
        scenario.close()
