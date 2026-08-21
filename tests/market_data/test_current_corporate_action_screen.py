"""Focused provider-neutral Plan-21 current corporate-action screen contracts."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
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
    store: CorporateActionSnapshotStoreV1
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
    writer = DuckDBCatalog(root, lease=lease)
    writer.__enter__()
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
    writer_store = CorporateActionSnapshotStoreV1(root, lease, writer)
    if retain:
        for member in manifest.members:
            writer_store.retain(
                UpstoxCorporateActionsClientV1(
                    _Transport(_payload()), clock=lambda: _CUTOFF
                ).fetch(member.isin, "fixture-token")
            )
    writer.__exit__(None, None, None)
    catalog = DuckDBCatalog(root, read_only=True, lease=lease)
    catalog.__enter__()
    return _Scenario(
        root,
        lease,
        catalog,
        schedule_store,
        CorporateActionSnapshotStoreV1(root, lease, catalog),
        manifest,
        digest,
    )


def _retain(scenario: _Scenario, snapshot: object) -> None:
    scenario.catalog.__exit__(None, None, None)
    writer = DuckDBCatalog(scenario.root, lease=scenario.lease)
    writer.__enter__()
    try:
        CorporateActionSnapshotStoreV1(scenario.root, scenario.lease, writer).retain(
            snapshot
        )
    finally:
        writer.__exit__(None, None, None)
    scenario.catalog = DuckDBCatalog(
        scenario.root, read_only=True, lease=scenario.lease
    )
    scenario.catalog.__enter__()
    scenario.store = CorporateActionSnapshotStoreV1(
        scenario.root, scenario.lease, scenario.catalog
    )


def _api() -> Any:
    return current_corporate_action_screen


def _input(api: Any, scenario: _Scenario, provider_id: str = "UPSTOX") -> Any:
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
        api.UpstoxCorporateActionScreenProviderV1(scenario.store),
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
                "OTHER", "1" * 64, "2" * 64, "3" * 64, "4" * 64
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


def test_nonexact_store_fails_before_schedule_or_provider_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    scenario = _scenario(tmp_path)
    calls: list[str] = []

    def fail_schedule(_digest: str) -> Any:
        calls.append("schedule")
        raise AssertionError

    try:
        provider = api.UpstoxCorporateActionScreenProviderV1(scenario.store)
        object.__setattr__(provider, "store", object())
        monkeypatch.setattr(scenario.schedule_store, "resolve", fail_schedule)
        resolver = api.CurrentSuppliedCohortCorporateActionScreenResolverV1(
            scenario.schedule_store, provider
        )
        with pytest.raises(ValueError):
            resolver.resolve_exact(_input(api, scenario), scenario.lease)
        assert calls == []
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
        _retain(
            scenario,
            UpstoxCorporateActionsClientV1(
                _Transport(_payload(kind)), clock=lambda: _CUTOFF
            ).fetch(isin, "fixture-token"),
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

        monkeypatch.setattr(scenario.store, "resolve", fail)
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(
            _input(api, scenario)
        )
        result = api.UpstoxCorporateActionScreenProviderV1(
            scenario.store
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
        _retain(
            scenario,
            UpstoxCorporateActionsClientV1(
                _Transport(_payload(kind, effective)), clock=lambda: _CUTOFF
            ).fetch(isin, "fixture-token"),
        )
        assert _resolve(api, scenario).outcome.value == expected
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
            scenario.store
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
    original = scenario.store.resolve
    try:

        def substituted(**kwargs: object) -> tuple[Any, Any]:
            metadata, snapshot = original(**kwargs)
            object.__setattr__(metadata, field, replacement)
            return metadata, snapshot

        monkeypatch.setattr(scenario.store, "resolve", substituted)
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(
            _input(api, scenario)
        )
        result = api.UpstoxCorporateActionScreenProviderV1(
            scenario.store
        ).resolve_exact(request, scenario.manifest.members[0].isin, scenario.lease)
        assert result.outcome is api.ProviderObservationOutcomeV1.CORRUPT
    finally:
        scenario.close()


def test_stores_bind_one_concrete_read_only_catalog_root_and_lease(
    tmp_path: Path,
) -> None:
    scenario = _scenario(tmp_path, 1)
    try:
        assert scenario.schedule_store.storage_root == scenario.root
        assert scenario.store.storage_root == scenario.root
        assert scenario.schedule_store.lease is scenario.lease
        assert scenario.store.lease is scenario.lease
        assert type(scenario.store.catalog) is DuckDBCatalog
        assert scenario.store.catalog.storage_root == scenario.root
        assert scenario.store.catalog.lease is scenario.lease
        assert scenario.store.catalog.read_only is True
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
    ("as_of", "expected"),
    (
        (
            _CLOSE - timedelta(microseconds=1),
            "SCHEDULE_CONTINUITY_UNPROVEN",
        ),
        (_CLOSE, "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"),
        (_CUTOFF, "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"),
    ),
)
def test_v3_schedule_requires_s20_close_before_provider_resolution(
    tmp_path: Path, as_of: datetime, expected: str
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        retained = scenario.schedule_store.retain(
            replace(
                _schedule(),
                schema_version=SCHEDULE_SCHEMA_VERSION_V3,
                as_of=as_of,
            )
        )
        assert retained.digest is not None
        input_value = api.CurrentSuppliedCohortCorporateActionScreenInputV1(
            scenario.manifest,
            _S0,
            _S20,
            _CUTOFF,
            retained.digest,
            "nse-authoritative-calendar",
            _RELEASE,
            "UPSTOX",
        )
        private = api.CurrentSuppliedCohortCorporateActionScreenResolverV1(
            scenario.schedule_store,
            api.UpstoxCorporateActionScreenProviderV1(scenario.store),
        ).resolve_exact(input_value, scenario.lease)
        assert private.outcome.value == expected
        if expected == "SCHEDULE_CONTINUITY_UNPROVEN":
            assert private.member_results == ()
            assert private.to_public_report().screen_state is None
        else:
            assert private.to_public_report().screen_state.value == "SCREENED"
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
            "UPSTOX",
        )
        outcome, _ = api._schedule_close(
            api.CurrentSuppliedCohortCorporateActionScreenRequestV1(input_value),
            schedule,
        )
        assert (None if outcome is None else outcome.value) == expected
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


@pytest.mark.parametrize("provider_id", ("", "provider_with_underscore"))
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


@pytest.mark.parametrize("retain", (True, False), ids=("ready", "insufficient"))
@pytest.mark.parametrize("mutation", ("outcome", "close", "hash", "rows", "descriptor"))
def test_sealed_private_result_rejects_every_content_mutation(
    tmp_path: Path, retain: bool, mutation: str
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 2, retain=retain)
    try:
        private = _resolve(api, scenario)
        if mutation == "outcome":
            object.__setattr__(
                private, "outcome", api.PrivateCorporateActionScreenOutcomeV1.CORRUPT
            )
        elif mutation == "close":
            object.__setattr__(private, "decision_session_close_at", _CUTOFF)
        elif mutation == "hash":
            object.__setattr__(private, "private_result_identity_sha256", "f" * 64)
        elif mutation == "rows":
            object.__setattr__(private, "member_results", private.member_results[:1])
        else:
            object.__setattr__(private, "provider_id", "NSE")
        with pytest.raises(ValueError):
            private.to_public_report()
    finally:
        scenario.close()


@pytest.mark.parametrize(("days", "valid"), ((63, True), (64, False)))
def test_input_bounds_calendar_span_before_schedule_materialization(
    tmp_path: Path, days: int, valid: bool
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        arguments = (
            scenario.manifest,
            _S0,
            _S0 + timedelta(days=days),
            _CUTOFF,
            scenario.schedule_sha256,
            "nse-authoritative-calendar",
            _RELEASE,
            "UPSTOX",
        )
        if valid:
            assert api.CurrentSuppliedCohortCorporateActionScreenInputV1(*arguments)
        else:
            with pytest.raises(ValueError):
                api.CurrentSuppliedCohortCorporateActionScreenInputV1(*arguments)
    finally:
        scenario.close()


def test_input_rejects_every_non_luhn_or_non_uppercase_manifest_isin(
    tmp_path: Path,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        assert all(api._valid_isin(_isin(index)) for index in range(1, 51))
        assert not api._valid_isin(_isin(1)[:-1] + "9")
        assert not api._valid_isin(_isin(1).lower())
        object.__setattr__(scenario.manifest.members[0], "isin", _isin(1)[:-1] + "9")
        with pytest.raises(ValueError):
            _input(api, scenario)
    finally:
        scenario.close()


def test_date_extremes_fail_before_schedule_date_allocation(tmp_path: Path) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        with pytest.raises(ValueError):
            api.CurrentSuppliedCohortCorporateActionScreenInputV1(
                scenario.manifest,
                date.min,
                date.max,
                _CUTOFF,
                scenario.schedule_sha256,
                "nse-authoritative-calendar",
                _RELEASE,
                "UPSTOX",
            )
    finally:
        scenario.close()


@pytest.mark.parametrize(
    ("as_of", "expected"),
    ((_CUTOFF, None), (_CUTOFF + timedelta(microseconds=1), "SCHEDULE_LATE")),
)
def test_schedule_as_of_is_bounded_by_decision_cutoff(
    tmp_path: Path, as_of: datetime, expected: str | None
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(
            _input(api, scenario)
        )
        outcome, _ = api._schedule_close(request, replace(_schedule(), as_of=as_of))
        assert (None if outcome is None else outcome.value) == expected
    finally:
        scenario.close()


def test_provider_result_event_and_aggregate_event_budgets_are_private_corrupt(
    tmp_path: Path,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 2)
    try:
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(
            _input(api, scenario)
        )
        descriptor = api.UpstoxCorporateActionScreenProviderV1(
            scenario.store
        ).descriptor
        event = api.NormalizedSupportedCorporateActionEventV1(
            api.SupportedCorporateActionKindV1.DIVIDEND, _S0
        )
        accepted = api.PrivateCorporateActionScreenProviderResultV1(
            scenario.manifest.members[0].isin,
            descriptor.provider_id,
            descriptor.capability_identity_sha256,
            descriptor.source_identity_sha256,
            descriptor.snapshot_schema_identity_sha256,
            descriptor.policy_identity_sha256,
            "5" * 64,
            1,
            _CUTOFF,
            request.decision_cutoff,
            (event,) * 1000,
            api.ProviderObservationOutcomeV1.AVAILABLE,
        )
        assert (
            api.PrivateCorporateActionScreenProviderResultV1.from_canonical_json_bytes(
                accepted.canonical_json_bytes()
            )
            == accepted
        )
        with pytest.raises(ValueError):
            api.PrivateCorporateActionScreenProviderResultV1(
                scenario.manifest.members[0].isin,
                descriptor.provider_id,
                descriptor.capability_identity_sha256,
                descriptor.source_identity_sha256,
                descriptor.snapshot_schema_identity_sha256,
                descriptor.policy_identity_sha256,
                "5" * 64,
                1,
                _CUTOFF,
                request.decision_cutoff,
                (event,) * 1001,
                api.ProviderObservationOutcomeV1.AVAILABLE,
            )
        rows = tuple(
            api.PrivateCorporateActionScreenMemberResultV1(
                api.PrivateCorporateActionScreenProviderResultV1(
                    member.isin,
                    descriptor.provider_id,
                    descriptor.capability_identity_sha256,
                    descriptor.source_identity_sha256,
                    descriptor.snapshot_schema_identity_sha256,
                    descriptor.policy_identity_sha256,
                    "5" * 64,
                    1,
                    _CUTOFF,
                    request.decision_cutoff,
                    (event,) * count,
                    api.ProviderObservationOutcomeV1.AVAILABLE,
                ),
                api.AggregateMemberOutcomeV1.ACTION_OBSERVED,
            )
            for member, count in zip(scenario.manifest.members, (500, 501), strict=True)
        )
        private = api._aggregate(
            request,
            descriptor,
            "6" * 64,
            _CLOSE,
            api.PrivateCorporateActionScreenOutcomeV1.ACTION_OBSERVED,
            rows,
            None,
        )
        assert private.outcome is api.PrivateCorporateActionScreenOutcomeV1.CORRUPT
        assert private.to_public_report().screen_state is None
    finally:
        scenario.close()


def test_runtime_manifest_rejects_universe_snapshot_source_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    source_root = Path(api.__file__).parent
    module_root = tmp_path / "market_data"
    module_root.mkdir()
    assert (
        "universe_snapshot.py" in api.CORPORATE_ACTION_SCREEN_RUNTIME_SOURCE_SHA256_V1
    )
    for name in (
        *api.CORPORATE_ACTION_SCREEN_RUNTIME_SOURCE_SHA256_V1,
        "current_corporate_action_screen_runtime_identity_manifest.py",
    ):
        shutil.copyfile(source_root / name, module_root / name)
    universe_snapshot = module_root / "universe_snapshot.py"
    universe_snapshot.write_bytes(universe_snapshot.read_bytes() + b"\n")
    monkeypatch.setattr(api, "_verify_runtime_module_loader", lambda *_: None)
    monkeypatch.setattr(
        api, "__file__", str(module_root / "current_corporate_action_screen.py")
    )

    with pytest.raises(ValueError, match="runtime code identity unavailable"):
        api.current_corporate_action_screen_runtime_code_identity_v1()


def test_resolver_calls_concrete_upstox_once_per_member_in_ascending_isin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 5)
    calls: list[str] = []
    original = api.UpstoxCorporateActionScreenProviderV1.resolve_exact

    def record(provider: Any, request: Any, isin: str, lease: Any) -> Any:
        calls.append(isin)
        return original(provider, request, isin, lease)

    try:
        monkeypatch.setattr(
            api.UpstoxCorporateActionScreenProviderV1, "resolve_exact", record
        )
        assert _resolve(api, scenario).outcome.value == (
            "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"
        )
        assert calls == sorted(member.isin for member in scenario.manifest.members)
    finally:
        scenario.close()


@pytest.mark.parametrize(
    ("retrieved_at", "expected"),
    (
        (_CLOSE - timedelta(microseconds=1), "STALE"),
        (_CLOSE, "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"),
    ),
)
def test_concrete_upstox_retrieval_time_uses_close_inclusively(
    tmp_path: Path, retrieved_at: datetime, expected: str
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1, retain=False)
    try:
        _retain(
            scenario,
            UpstoxCorporateActionsClientV1(
                _Transport(_payload()), clock=lambda: retrieved_at
            ).fetch(scenario.manifest.members[0].isin, "fixture-token"),
        )
        assert _resolve(api, scenario).outcome.value == expected
    finally:
        scenario.close()


@pytest.mark.parametrize(
    ("retrieved_at", "row_outcome", "aggregate_outcome"),
    (
        (
            _CLOSE - timedelta(microseconds=1),
            "STALE",
            "STALE",
        ),
        (
            _CLOSE,
            "ACTION_OBSERVED",
            "ACTION_OBSERVED",
        ),
    ),
)
def test_concrete_upstox_stale_snapshot_precedes_in_window_action_inspection(
    tmp_path: Path,
    retrieved_at: datetime,
    row_outcome: str,
    aggregate_outcome: str,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1, retain=False)
    try:
        _retain(
            scenario,
            UpstoxCorporateActionsClientV1(
                _Transport(_payload("DIVIDEND", _S20)),
                clock=lambda: retrieved_at,
            ).fetch(scenario.manifest.members[0].isin, "fixture-token"),
        )
        private = _resolve(api, scenario)
        assert private.member_results[0].row_outcome.value == row_outcome
        assert private.outcome.value == aggregate_outcome
    finally:
        scenario.close()


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    (
        (("MISSING", "STALE"), "MISSING"),
        (("STALE", "AMBIGUOUS"), "STALE"),
        (("AMBIGUOUS", "CORRUPT"), "AMBIGUOUS"),
        (("CORRUPT", "ACTION"), "CORRUPT"),
        (("ACTION", "SCREENED"), "ACTION_OBSERVED"),
    ),
)
def test_concrete_upstox_mixed_member_outcome_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcomes: tuple[str, str],
    expected: str,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 2)

    def result_for(provider: Any, request: Any, isin: str, lease: Any) -> Any:
        index = [member.isin for member in scenario.manifest.members].index(isin)
        semantic_outcome = outcomes[index]
        descriptor = provider.descriptor
        if semantic_outcome in {"MISSING", "STALE", "AMBIGUOUS", "CORRUPT"}:
            return api._provider_failure(
                descriptor,
                isin,
                request.decision_cutoff,
                api.ProviderObservationOutcomeV1(semantic_outcome),
            )
        events = (
            (
                api.NormalizedSupportedCorporateActionEventV1(
                    api.SupportedCorporateActionKindV1.DIVIDEND, _S0
                ),
            )
            if semantic_outcome == "ACTION"
            else ()
        )
        return api.PrivateCorporateActionScreenProviderResultV1(
            isin,
            descriptor.provider_id,
            descriptor.capability_identity_sha256,
            descriptor.source_identity_sha256,
            descriptor.snapshot_schema_identity_sha256,
            descriptor.policy_identity_sha256,
            "4" * 64,
            1,
            _CUTOFF,
            request.decision_cutoff,
            events,
            api.ProviderObservationOutcomeV1.AVAILABLE,
        )

    try:
        monkeypatch.setattr(
            api.UpstoxCorporateActionScreenProviderV1, "resolve_exact", result_for
        )
        assert _resolve(api, scenario).outcome.value == expected
    finally:
        scenario.close()


def test_corrupt_returned_provider_result_becomes_private_corrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    original = api.UpstoxCorporateActionScreenProviderV1.resolve_exact

    def corrupt(provider: Any, request: Any, isin: str, lease: Any) -> Any:
        result = original(provider, request, isin, lease)
        object.__setattr__(result, "snapshot_byte_count", 0)
        return result

    try:
        monkeypatch.setattr(
            api.UpstoxCorporateActionScreenProviderV1, "resolve_exact", corrupt
        )
        private = _resolve(api, scenario)
        assert private.outcome is api.PrivateCorporateActionScreenOutcomeV1.CORRUPT
        assert private.to_public_report().screen_state is None
    finally:
        scenario.close()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        + b"\n"
    ).hexdigest()


def _selected_snapshot_set_oracle(
    request: Any, descriptor: Any, runtime: str, members: tuple[Any, ...]
) -> str:
    snapshots = []
    for member in sorted(members, key=lambda item: item.provider_result.isin):
        result = member.provider_result
        snapshots.append(
            {
                "isin": result.isin,
                "provider_id": result.provider_id,
                "provider_capability_identity_sha256": (
                    result.provider_capability_identity_sha256
                ),
                "provider_source_identity_sha256": result.provider_source_identity_sha256,
                "provider_snapshot_schema_identity_sha256": (
                    result.provider_snapshot_schema_identity_sha256
                ),
                "provider_policy_identity_sha256": result.provider_policy_identity_sha256,
                "snapshot_identity_sha256": result.snapshot_identity_sha256,
                "snapshot_byte_count": result.snapshot_byte_count,
                "retrieved_at": result.retrieved_at.astimezone(UTC).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
                "knowledge_cutoff": result.knowledge_cutoff.astimezone(UTC).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
                "normalized_supported_events": [
                    {
                        "kind": event.kind.value,
                        "effective_date": event.effective_date.isoformat(),
                    }
                    for event in result.normalized_supported_events
                ],
            }
        )
    return _canonical_sha256(
        {
            "contract_version": request.contract_version,
            "input_identity_sha256": request.input_identity_sha256,
            "request_identity_sha256": request.request_identity_sha256,
            "runtime_code_identity_sha256": runtime,
            "cohort_identity_sha256": request.cohort_manifest.cohort_identity_sha256,
            "comparison_session": request.comparison_session.isoformat(),
            "decision_cutoff": request.decision_cutoff.astimezone(UTC).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "decision_session": request.decision_session.isoformat(),
            "schedule_evidence_sha256": request.schedule_evidence_sha256,
            "schedule_source": request.schedule_source,
            "schedule_source_release": request.schedule_source_release,
            "provider_id": descriptor.provider_id,
            "provider_capability_identity_sha256": (
                descriptor.capability_identity_sha256
            ),
            "provider_source_identity_sha256": descriptor.source_identity_sha256,
            "provider_snapshot_schema_identity_sha256": (
                descriptor.snapshot_schema_identity_sha256
            ),
            "provider_policy_identity_sha256": descriptor.policy_identity_sha256,
            "screen_schema_identity_sha256": request.screen_schema_identity_sha256,
            "screen_policy_identity_sha256": request.screen_policy_identity_sha256,
            "snapshots": snapshots,
        }
    )


def test_selected_snapshot_set_hash_binds_known_retained_metadata_and_byte_count(
    tmp_path: Path,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 2)
    try:
        private = _resolve(api, scenario)
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(
            _input(api, scenario)
        )
        descriptor = api.UpstoxCorporateActionScreenProviderV1(
            scenario.store
        ).descriptor
        assert (
            _selected_snapshot_set_oracle(
                request,
                descriptor,
                private.runtime_code_identity_sha256,
                private.member_results,
            )
            == private.selected_snapshot_set_identity_sha256
        )
        first = private.member_results[0]
        changed = replace(
            first,
            provider_result=replace(
                first.provider_result,
                snapshot_byte_count=first.provider_result.snapshot_byte_count + 1,
            ),
        )
        assert (
            _selected_snapshot_set_oracle(
                request,
                descriptor,
                private.runtime_code_identity_sha256,
                (changed, *private.member_results[1:]),
            )
            != private.selected_snapshot_set_identity_sha256
        )
    finally:
        scenario.close()


@pytest.mark.parametrize("origin", ("fake", "foreign", "writable", "suppressed"))
def test_catalog_origin_rejections_happen_before_schedule_or_store_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, origin: str
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    calls: list[str] = []

    class SuppressingCatalog(DuckDBCatalog):
        def latest_corporate_action_snapshots(
            self, *, isin: str, knowledge_cutoff: datetime
        ) -> tuple[Any, ...]:
            calls.append("suppressed-latest")
            raise AssertionError

    catalog: object
    if origin == "fake":
        catalog = object()
    elif origin == "foreign":
        catalog = DuckDBCatalog(
            scenario.root / "foreign", read_only=True, lease=scenario.lease
        )
    elif origin == "writable":
        catalog = DuckDBCatalog(scenario.root, lease=scenario.lease)
    else:
        catalog = SuppressingCatalog(
            scenario.root, read_only=True, lease=scenario.lease
        )

    def fail_schedule(_digest: str) -> Any:
        calls.append("schedule")
        raise AssertionError

    def fail_store(**kwargs: object) -> Any:
        calls.append("store")
        raise AssertionError

    try:
        object.__setattr__(scenario.store, "_catalog", catalog)
        monkeypatch.setattr(scenario.schedule_store, "resolve", fail_schedule)
        monkeypatch.setattr(scenario.store, "resolve", fail_store)
        with pytest.raises(ValueError, match="invalid Plan-21 resolution"):
            _resolve(api, scenario)
        assert calls == []
    finally:
        scenario.close()


@pytest.mark.parametrize(
    "mutation", ("type", "digest", "canonical", "sha", "source", "as_of")
)
def test_resolver_rejects_corrupt_schedule_results_before_provider_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    calls: list[str] = []
    original = scenario.schedule_store.resolve
    result = original(scenario.schedule_sha256)
    assert result.schedule is not None and result.canonical_bytes is not None
    corrupted: object
    if mutation == "type":
        corrupted = object()
    elif mutation == "digest":
        corrupted = replace(result, digest="0" * 64)
    elif mutation == "canonical":
        corrupted = replace(result, canonical_bytes=result.canonical_bytes + b" ")
    elif mutation == "sha":
        corrupted = replace(
            result,
            canonical_bytes=api.canonical_schedule_bytes(result.schedule),
            digest="f" * 64,
        )
    elif mutation == "source":
        corrupted = replace(result, schedule=replace(result.schedule, source="other"))
    else:
        corrupted = replace(
            result,
            schedule=replace(
                result.schedule, as_of=_CUTOFF + timedelta(microseconds=1)
            ),
        )

    def corrupt_schedule(_digest: str) -> object:
        return corrupted

    def fail_provider(provider: Any, request: Any, isin: str, lease: Any) -> Any:
        calls.append(isin)
        raise AssertionError

    try:
        monkeypatch.setattr(scenario.schedule_store, "resolve", corrupt_schedule)
        monkeypatch.setattr(
            api.UpstoxCorporateActionScreenProviderV1,
            "resolve_exact",
            fail_provider,
        )
        private = _resolve(api, scenario)
        assert (
            private.outcome
            is api.PrivateCorporateActionScreenOutcomeV1.SCHEDULE_UNAVAILABLE
        )
        assert calls == []
    finally:
        scenario.close()


def test_frozen_plan21_identity_projections_match_independent_json_oracles() -> None:
    api = _api()
    plan = (
        Path(__file__).parents[2]
        / "docs/plans/21-current-supplied-cohort-corporate-action-screen-contract.md"
    )
    blocks = re.findall(r"```json\n(.*?)\n```", plan.read_text(encoding="utf-8"), re.S)
    assert len(blocks) == 6
    oracles = {
        name: _canonical_sha256(json.loads(block))
        for name, block in zip(
            (
                "upstox_source",
                "upstox_policy",
                "upstox_capability",
                "screen_schema",
                "screen_policy",
                "selected_snapshot_set",
            ),
            blocks,
            strict=True,
        )
    }
    assert oracles == {
        "upstox_source": api.UPSTOX_CORPORATE_ACTION_SCREEN_SOURCE_IDENTITY_SHA256_V1,
        "upstox_policy": api.UPSTOX_CORPORATE_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1,
        "upstox_capability": (
            api.UPSTOX_CORPORATE_ACTION_SCREEN_CAPABILITY_IDENTITY_SHA256_V1
        ),
        "screen_schema": api.CURRENT_CORPORATE_ACTION_SCREEN_SCHEMA_IDENTITY_SHA256_V1,
        "screen_policy": api.CURRENT_CORPORATE_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1,
        "selected_snapshot_set": api.SELECTED_SNAPSHOT_SET_SCHEMA_IDENTITY_SHA256_V1,
    }
    assert len(set(oracles.values())) == len(oracles)


@pytest.mark.parametrize(
    ("label", "limit_name", "expected_limit"),
    (
        ("input", "_MAX_INPUT_REQUEST_PUBLIC_DTO_BYTES", 16 * 1024),
        ("request", "_MAX_INPUT_REQUEST_PUBLIC_DTO_BYTES", 16 * 1024),
        ("report", "_MAX_INPUT_REQUEST_PUBLIC_DTO_BYTES", 16 * 1024),
        ("provider", "_MAX_PROVIDER_RESULT_DTO_BYTES", 128 * 1024),
        ("private", "_MAX_PRIVATE_AGGREGATE_DTO_BYTES", 256 * 1024),
    ),
)
def test_dto_serializers_and_parsers_enforce_symmetric_byte_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    limit_name: str,
    expected_limit: int,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)
    try:
        input_value = _input(api, scenario)
        request = api.CurrentSuppliedCohortCorporateActionScreenRequestV1(input_value)
        private = _resolve(api, scenario)
        report = private.to_public_report()
        provider = private.member_results[0].provider_result
        value = {
            "input": input_value,
            "request": request,
            "report": report,
            "provider": provider,
            "private": private,
        }[label]
        parser = {
            "input": api.CurrentSuppliedCohortCorporateActionScreenInputV1,
            "request": api.CurrentSuppliedCohortCorporateActionScreenRequestV1,
            "report": api.CurrentSuppliedCohortCorporateActionScreenReportV1,
            "provider": api.PrivateCorporateActionScreenProviderResultV1,
            "private": api.PrivateCorporateActionScreenResultV1,
        }[label]
        raw = value.canonical_json_bytes()
        assert getattr(api, limit_name) == expected_limit
        monkeypatch.setattr(api, limit_name, len(raw))
        assert value.canonical_json_bytes() == raw
        assert parser.from_canonical_json_bytes(raw).canonical_json_bytes() == raw
        monkeypatch.setattr(api, limit_name, len(raw) - 1)
        with pytest.raises(ValueError):
            value.canonical_json_bytes()
        with pytest.raises(ValueError):
            parser.from_canonical_json_bytes(raw)
    finally:
        scenario.close()


def test_fifty_member_private_round_trip_is_unsealed_and_nonpublishing(
    tmp_path: Path,
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 50)
    try:
        private = _resolve(api, scenario)
        raw = private.canonical_json_bytes()
        assert len(raw) <= 256 * 1024
        replay = api.PrivateCorporateActionScreenResultV1.from_canonical_json_bytes(raw)
        assert replay.canonical_json_bytes() == raw
        assert replay._publication_seal is None
        with pytest.raises(ValueError, match="unsealed private Plan-21 result"):
            replay.to_public_report()
    finally:
        scenario.close()


def test_resolution_has_zero_network_write_or_scan_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    scenario = _scenario(tmp_path, 1)

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError

    try:
        monkeypatch.setattr(UpstoxCorporateActionsClientV1, "fetch", fail)
        monkeypatch.setattr(CorporateActionSnapshotStoreV1, "retain", fail)
        monkeypatch.setattr(Path, "glob", fail)
        monkeypatch.setattr(Path, "iterdir", fail)
        monkeypatch.setattr(Path, "rglob", fail)
        assert _resolve(api, scenario).outcome.value == (
            "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"
        )
    finally:
        scenario.close()
