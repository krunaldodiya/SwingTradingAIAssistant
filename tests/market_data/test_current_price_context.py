"""RED contract tests for Issue #188's public price-context boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from current_raw_acquisition_fixtures import (
    FixtureTokenProvider,
    RecordedWire,
    WireReply,
    action_body,
    historical_body,
    seed_root,
)
from current_raw_acquisition_fixtures import control as fixture_control
from current_raw_acquisition_fixtures import schedule as fixture_schedule

import swing_trading_ai_assistant.market_data.current_raw_acquisition as acquisition_module
import swing_trading_ai_assistant.market_data.current_raw_acquisition_transport as transport_module
from swing_trading_ai_assistant.market_data import (
    current_industry_classification as classification,
)
from swing_trading_ai_assistant.market_data.current_industry_archive_reader import (
    AdmittedCurrentIndustryProjectionV1,
    read_current_industry_archive_exact_v1,
)
from swing_trading_ai_assistant.market_data.current_industry_archive_reader import (
    CurrentIndustryArchiveReferenceV1 as ReaderIndustryReferenceV1,
)
from swing_trading_ai_assistant.market_data.current_raw_acquisition import (
    acquire_missing_current_raw_evidence_v1,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    AdmittedCurrentRawContextV1,
    CurrentRawPriceContextInputV1,
    read_retained_current_raw_context_v1,
    validate_admitted_current_raw_context_v1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.research_packet.current_price_context import (
    CurrentIndustryArchiveReferenceV1,
    CurrentPriceContextBreadthV1,
    CurrentPriceContextMemberV1,
    CurrentPriceContextRequestV1,
    current_price_context_request_from_canonical_json_bytes_v1,
    research_current_price_context_v1,
)
from swing_trading_ai_assistant.sector_analysis.current_raw_industry_participation import (
    reduce_current_raw_industry_participation_v1,
)


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def _member_isin(index: int) -> str:
    prefix = f"INE{index:08d}"
    digits = "".join(str(ord(char) - 55) if char.isalpha() else char for char in prefix)
    for check in range(10):
        values = map(int, reversed(digits + str(check)))
        total = sum(
            value if position % 2 == 0 else (value * 2 - 9 if value > 4 else value * 2)
            for position, value in enumerate(values)
        )
        if total % 10 == 0:
            return prefix + str(check)
    raise AssertionError("unreachable ISIN check digit")


def _member(index: int) -> CurrentPriceContextMemberV1:
    return CurrentPriceContextMemberV1(
        isin=_member_isin(index),
        exchange="NSE",
        instrument_type="EQUITY",
        segment="EQ",
        effective_symbol=f"SYM{index:03d}",
        valid_from=date(2020, 1, 1),
        valid_through=date(2030, 1, 1),
    )


def test_public_request_is_closed_bounded_and_preserves_order() -> None:
    selected_at = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = CurrentPriceContextRequestV1(
        contract_version="current-price-context-request@v1",
        data_selection_time=selected_at,
        admission_deadline=selected_at + timedelta(minutes=30),
        schedule_identity_sha256="a" * 64,
        members=(_member(1),),
        questions=(
            "RAW_MARKET_STRUCTURE",
            "RAW_20_SESSION_DIRECTION",
            "RAW_COHORT_BREADTH",
            "RAW_INDUSTRY_PARTICIPATION",
        ),
        industry_archive_reference=None,
    )

    assert request.members[0].effective_symbol == "SYM001"
    assert request.request_identity_sha256 == CurrentPriceContextRequestV1.identity_of(
        request
    )
    with pytest.raises(ValueError, match="request is invalid"):
        CurrentPriceContextRequestV1(
            contract_version="current-price-context-request@v1",
            data_selection_time=selected_at,
            admission_deadline=selected_at + timedelta(minutes=30),
            schedule_identity_sha256="a" * 64,
            members=(_member(1),),
            questions=("RAW_COHORT_BREADTH",),
            industry_archive_reference=None,
        )


def test_request_rejects_ist_rollover_expired_member_and_duplicate_json_fields() -> (
    None
):
    selected_at = datetime(2026, 9, 15, 18, 20, tzinfo=UTC)
    with pytest.raises(ValueError, match="request is invalid"):
        CurrentPriceContextRequestV1(
            "current-price-context-request@v1",
            selected_at,
            selected_at + timedelta(minutes=20),
            "a" * 64,
            (_member(1),),
            (
                "RAW_MARKET_STRUCTURE",
                "RAW_20_SESSION_DIRECTION",
                "RAW_COHORT_BREADTH",
                "RAW_INDUSTRY_PARTICIPATION",
            ),
            None,
        )
    with pytest.raises(ValueError, match="not valid"):
        CurrentPriceContextRequestV1(
            "current-price-context-request@v1",
            datetime(2031, 1, 1, tzinfo=UTC),
            datetime(2031, 1, 1, 0, 1, tzinfo=UTC),
            "a" * 64,
            (_member(1),),
            (
                "RAW_MARKET_STRUCTURE",
                "RAW_20_SESSION_DIRECTION",
                "RAW_COHORT_BREADTH",
                "RAW_INDUSTRY_PARTICIPATION",
            ),
            None,
        )
    duplicate = (
        b'{"admission_deadline":"2026-09-15T09:30:00.000000Z",'
        b'"contract_version":"current-price-context-request@v1",'
        b'"contract_version":"current-price-context-request@v1",'
        b'"data_selection_time":"2026-09-15T09:00:00.000000Z",'
        b'"industry_archive_reference":null,"members":[],"questions":[], '
        b'"schedule_identity_sha256":"' + b"a" * 64 + b'"}\n'
    )
    with pytest.raises(ValueError, match="request is invalid"):
        current_price_context_request_from_canonical_json_bytes_v1(duplicate)


def _classification_isin(index: int) -> str:
    prefix = f"INE{index:08d}"
    digits = "".join(str(ord(char) - 55) if char.isalpha() else char for char in prefix)
    for check in range(10):
        values = map(int, reversed(digits + str(check)))
        total = sum(
            value if position % 2 == 0 else (value * 2 - 9 if value > 4 else value * 2)
            for position, value in enumerate(values)
        )
        if total % 10 == 0:
            return prefix + str(check)
    raise AssertionError("unreachable ISIN check digit")


def _classification_artifact(
    members: tuple[CurrentPriceContextMemberV1, ...],
) -> bytes:
    header = "Company Name,Industry,Symbol,Series,ISIN Code"
    rows = [
        f"Company {index:03d},Banking,OTHER{index:03d},EQ,"
        f"{_classification_isin(index + 100)}"
        for index in range(100)
    ]
    for index, member in enumerate(members):
        rows[index] = (
            f"Company {index:03d},{'Banking' if index % 2 else 'Technology'},"
            f"{member.effective_symbol},EQ,{member.isin}"
        )
    return ("\n".join((header, *rows)) + "\n").encode()


def _classification_input(
    artifact: bytes,
) -> classification.CurrentIndustryClassificationInputV1:
    digest = hashlib.sha256(artifact).hexdigest()
    value = {
        "contract_version": "current-supplied-cohort-industry-classification@v1",
        "schema_identity_sha256": classification.CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
        "source_url": "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
        "source_authority": "NSE_INDICES",
        "source_domain": "nsearchives.nseindia.com",
        "acquisition_method": "BOUNDED_OFFICIAL_FETCH",
        "artifact_byte_count": len(artifact),
        "artifact_sha256": digest,
        "artifact_revision": f"sha256:{digest}",
        "classification_tier": "INDUSTRY",
        "publisher_published_at": None,
        "publisher_effective_from": None,
        "publisher_effective_through": None,
        "publisher_revision": None,
        "licence_policy_identity_sha256": classification.CURRENT_INDUSTRY_LICENCE_POLICY_IDENTITY_SHA256,
    }
    return (
        classification.CurrentIndustryClassificationInputV1.from_canonical_json_bytes(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        )
    )


def _public_request(
    raw_request: CurrentRawPriceContextInputV1,
    industry: CurrentIndustryArchiveReferenceV1 | None = None,
) -> CurrentPriceContextRequestV1:
    value = raw_request
    return CurrentPriceContextRequestV1(
        "current-price-context-request@v1",
        value.data_selection_time,
        value.admission_deadline,
        value.schedule_identity_sha256,
        value.members,
        (
            "RAW_MARKET_STRUCTURE",
            "RAW_20_SESSION_DIRECTION",
            "RAW_COHORT_BREADTH",
            "RAW_INDUSTRY_PARTICIPATION",
        ),
        industry,
    )


def _retain_industry_for_raw(
    root: Path, raw_request: CurrentRawPriceContextInputV1
) -> CurrentIndustryArchiveReferenceV1:
    admitted = StorageRootLease.try_admit_read_existing(root)
    assert admitted.lease is not None
    with admitted.lease as lease:
        raw = read_retained_current_raw_context_v1(
            root, request=raw_request, lease=lease, control=fixture_control(raw_request)
        )
        assert raw.admitted is not None
        projection = validate_admitted_current_raw_context_v1(raw.admitted)
    artifact = _classification_artifact(raw_request.members)
    classification_input = _classification_input(artifact)
    parsed = classification.parse_current_industry_artifact_v1(
        classification_input, artifact
    )
    assert isinstance(parsed, classification.ParsedCurrentIndustryArtifactV1)
    snapshot = classification.project_current_supplied_cohort_industry_v1(
        parsed,
        projection.canonical_cohort_identity_sha256,
        tuple(
            classification.CurrentIndustryCohortMemberV1(
                item.isin, item.exchange, item.effective_symbol
            )
            for item in raw_request.members
        ),
    )
    assert isinstance(snapshot, classification.PrivateCurrentIndustrySnapshotV1)
    writer = StorageRootLease.try_acquire_existing(root)
    assert writer.lease is not None
    sampled_at = projection.evidence_cutoff - timedelta(seconds=30)
    marker_ns = int(projection.evidence_cutoff.timestamp()) * 1_000_000_000
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(classification, "_trusted_utc_now", lambda: sampled_at)  # pyright: ignore[reportPrivateUsage]

        def marker_mtime(_: int) -> int:
            return marker_ns

        patch.setattr(classification, "_marker_filesystem_mtime_ns", marker_mtime)  # pyright: ignore[reportPrivateUsage]
        try:
            retained = classification.FileCurrentIndustryArchiveV1(root).archive_exact(
                classification_input, artifact, snapshot, writer.lease
            )
        finally:
            writer.lease.close()
    assert isinstance(retained, classification.RetainedCurrentIndustrySnapshotV1)
    return CurrentIndustryArchiveReferenceV1(
        "current-industry-archive-reference@v1",
        retained.snapshot_identity_sha256,
        retained.retained_identity_sha256,
    )


def test_retained_only_public_call_never_attempts_acquisition(tmp_path: Path) -> None:
    selected_at = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = CurrentPriceContextRequestV1(
        contract_version="current-price-context-request@v1",
        data_selection_time=selected_at,
        admission_deadline=selected_at + timedelta(minutes=30),
        schedule_identity_sha256="a" * 64,
        members=(_member(1),),
        questions=(
            "RAW_MARKET_STRUCTURE",
            "RAW_20_SESSION_DIRECTION",
            "RAW_COHORT_BREADTH",
            "RAW_INDUSTRY_PARTICIPATION",
        ),
        industry_archive_reference=None,
    )

    result = research_current_price_context_v1(
        request, tmp_path, clock=_Clock(selected_at)
    )

    assert result.acquisition_mode == "RETAINED_ONLY"
    assert result.acquisition_outcome == "NOT_ATTEMPTED"
    assert "RETained" not in result.canonical_json_bytes().decode()


def test_retained_only_public_composes_real_raw_and_industry_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "retained"
    raw_request = seed_root(root)
    wire = RecordedWire(
        [WireReply(body=historical_body()), WireReply(body=action_body())]
    )
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    assert (
        acquire_missing_current_raw_evidence_v1(
            raw_request, root, control=fixture_control(raw_request)
        ).outcome
        == "ACQUISITION_COMPLETED"
    )
    reference = _retain_industry_for_raw(root, raw_request)
    admitted = StorageRootLease.try_admit_read_existing(root)
    assert admitted.lease is not None
    with admitted.lease as lease:
        raw = read_retained_current_raw_context_v1(
            root, request=raw_request, lease=lease, control=fixture_control(raw_request)
        )
        assert raw.admitted is not None
        archive = read_current_industry_archive_exact_v1(
            ReaderIndustryReferenceV1(
                reference.contract_version,
                reference.snapshot_identity_sha256,
                reference.retained_identity_sha256,
            ),
            storage_root=root,
            lease=lease,
            raw=raw.admitted,
        )
        assert isinstance(archive, AdmittedCurrentIndustryProjectionV1)
        reduced = reduce_current_raw_industry_participation_v1(raw.admitted, archive)
        assert reduced.evidence_state == "OBSERVED"
        assert reduced.groups[0].member_count == 1
        forged_raw = object.__new__(AdmittedCurrentRawContextV1)
        object.__setattr__(forged_raw, "_seal", object())
        forged_industry = object.__new__(AdmittedCurrentIndustryProjectionV1)
        object.__setattr__(forged_industry, "_seal", object())
        with pytest.raises(ValueError, match="not admitted"):
            reduce_current_raw_industry_participation_v1(forged_raw, archive)
        with pytest.raises(ValueError, match="not admitted"):
            reduce_current_raw_industry_participation_v1(raw.admitted, forged_industry)

    result = research_current_price_context_v1(
        _public_request(raw_request, reference),
        root,
        clock=_Clock(raw_request.data_selection_time),
    )

    assert result.acquisition_mode == "RETAINED_ONLY"
    assert result.acquisition_provider_calls == 0
    assert result.members[0].state == "OBSERVED"
    assert result.members[0].direction == "UNCHANGED"
    assert result.breadth is not None and result.breadth.requested_count == 1
    assert result.industry_evidence_state == "OBSERVED"
    assert result.industry_groups[0].member_count == 1
    payload = result.canonical_json_bytes().decode()
    for private in (str(root), "fixture-token", "https://", "Authorization", "raw-"):
        assert private not in payload


def test_acquire_missing_public_exposes_only_safe_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "retained"
    raw_request = seed_root(root)
    wire = RecordedWire(
        [WireReply(body=historical_body()), WireReply(body=action_body())]
    )
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )

    result = research_current_price_context_v1(
        _public_request(raw_request),
        root,
        acquire_missing=True,
        clock=_Clock(raw_request.data_selection_time),
    )

    assert result.acquisition_outcome == "ACQUISITION_COMPLETED"
    assert result.acquisition_provider_calls == wire.attempts == 2
    assert result.members[0].state == "OBSERVED"
    assert "fixture-token" not in result.canonical_json_bytes().decode()


def _acquire_retained_raw(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    raw_request: CurrentRawPriceContextInputV1 | None = None,
    action_in_window: bool = False,
    replies: list[WireReply] | None = None,
) -> CurrentRawPriceContextInputV1:
    request = seed_root(
        root,
        retained_action=True,
        action_in_window=action_in_window,
        request_value=raw_request,
    )
    wire = RecordedWire(
        replies
        if replies is not None
        else [WireReply(body=historical_body()) for _ in request.members]
    )
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    acquired = acquire_missing_current_raw_evidence_v1(
        request, root, control=fixture_control(request)
    )
    assert acquired.outcome == "ACQUISITION_COMPLETED"
    assert acquired.provider_calls == wire.attempts == len(request.members)
    return request


def test_public_retained_member_fact_is_immutable_deterministic_and_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "retained"
    raw_request = _acquire_retained_raw(root, monkeypatch)
    request = _public_request(raw_request)

    first = research_current_price_context_v1(
        request, root, clock=_Clock(raw_request.data_selection_time)
    )
    second = research_current_price_context_v1(
        request, root, clock=_Clock(raw_request.data_selection_time)
    )

    member = first.members[0]
    assert member.state == "OBSERVED"
    assert member.structure is not None and member.direction == "UNCHANGED"
    assert member.mapping_observation_sha256 is not None
    assert member.partition_checksums and member.screen_identity_sha256 is not None
    assert first.breadth is not None
    assert (
        first.breadth.requested_count,
        first.breadth.observed_count,
        first.breadth.advances,
        first.breadth.declines,
        first.breadth.unchanged,
        first.breadth.insufficient_count,
    ) == (1, 1, 0, 0, 1, 0)
    assert first.features[0].readiness == "READY"
    assert first.limitations == (
        "UPSTOX_RAW_ONLY",
        "RETAINED_EVIDENCE_REQUIRED",
        "CURRENT_MAPPING_SCOPE",
    )
    assert first == second
    assert first.result_identity_sha256 == second.result_identity_sha256
    assert first.canonical_json_bytes() == second.canonical_json_bytes()
    with pytest.raises(FrozenInstanceError):
        first.members = ()  # type: ignore[misc]
    assert first.breadth is not None
    with pytest.raises(ValueError, match="result is invalid"):
        replace(
            first,
            breadth=CurrentPriceContextBreadthV1(
                1, 0, 0, 0, 0, 1, None, ("MEMBER_DIRECTION_UNAVAILABLE",)
            ),
            result_identity_sha256="",
        )
    payload = first.canonical_json_bytes().decode()
    for private in (
        str(root),
        "https://",
        "Authorization",
        "fixture-token",
        "raw-",
        "_seal",
        "registry",
        "Traceback",
        "internal_error",
    ):
        assert private not in payload
    partition = next(root.rglob("*.parquet"))
    partition.chmod(0o600)
    partition.write_bytes(b"corrupt")
    corrupted = research_current_price_context_v1(
        request, root, clock=_Clock(raw_request.data_selection_time)
    )
    assert (
        corrupted.members[0].state,
        corrupted.members[0].reason,
        corrupted.members[0].structure,
        corrupted.members[0].direction,
    ) == ("INSUFFICIENT_EVIDENCE", "RAW_PARTITION_CORRUPT", None, None)


def test_public_action_observed_withholds_only_affected_member_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "retained"
    raw_request = _acquire_retained_raw(root, monkeypatch, action_in_window=True)

    result = research_current_price_context_v1(
        _public_request(raw_request),
        root,
        clock=_Clock(raw_request.data_selection_time),
    )

    member = result.members[0]
    assert (member.state, member.reason, member.structure, member.direction) == (
        "INSUFFICIENT_EVIDENCE",
        "ACTION_IN_WINDOW",
        None,
        None,
    )
    assert result.breadth is not None
    assert result.breadth.requested_count == result.breadth.insufficient_count == 1
    assert result.breadth.observed_count == 0
    assert result.features[1].readiness == "WITHHELD"


def test_public_industry_failures_never_suppress_retained_raw_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "retained"
    raw_request = _acquire_retained_raw(root, monkeypatch)
    reference = _retain_industry_for_raw(root, raw_request)
    request = _public_request(raw_request, reference)
    valid = research_current_price_context_v1(
        request, root, clock=_Clock(raw_request.data_selection_time)
    )
    assert valid.industry_evidence_state == "OBSERVED"
    assert valid.industry_groups and valid.members[0].structure is not None
    mismatched = research_current_price_context_v1(
        _public_request(
            raw_request,
            CurrentIndustryArchiveReferenceV1(
                "current-industry-archive-reference@v1", "a" * 64, "b" * 64
            ),
        ),
        root,
        clock=_Clock(raw_request.data_selection_time),
    )
    assert (
        mismatched.industry_evidence_state,
        mismatched.members[0].state,
        mismatched.members[0].direction,
    ) == ("INSUFFICIENT_EVIDENCE", "OBSERVED", "UNCHANGED")

    corrupted = next((root / ".current-industry-classification-v1").glob("raw-*.csv"))
    corrupted.chmod(0o600)
    corrupted.write_bytes(b"corrupt")
    missing = research_current_price_context_v1(
        request, root, clock=_Clock(raw_request.data_selection_time)
    )
    assert missing.industry_evidence_state == "INSUFFICIENT_EVIDENCE"
    assert missing.members[0].state == "OBSERVED"
    assert missing.members[0].structure is not None


def test_public_mixed_two_member_results_preserve_order_and_breadth_denominator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "retained"
    source = seed_root(root, retained_action=True)
    raw_request = CurrentRawPriceContextInputV1(
        source.request_identity_sha256,
        source.data_selection_time,
        source.admission_deadline,
        source.schedule_identity_sha256,
        (source.members[0], _member(2)),
    )
    # Re-seed exact two-member mapping/action evidence using real stores.
    root = tmp_path / "two"
    raw_request = seed_root(root, retained_action=True, request_value=raw_request)
    wire = RecordedWire([WireReply(status=404), WireReply(body=historical_body())])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    acquired = acquire_missing_current_raw_evidence_v1(
        raw_request, root, control=fixture_control(raw_request)
    )
    assert acquired.outcome == "ACQUISITION_PARTIAL" and wire.attempts == 2

    result = research_current_price_context_v1(
        _public_request(raw_request),
        root,
        clock=_Clock(raw_request.data_selection_time),
    )

    assert [item.effective_symbol for item in result.members] == ["ACME", "SYM002"]
    assert [item.state for item in result.members] == [
        "INSUFFICIENT_EVIDENCE",
        "OBSERVED",
    ]
    assert result.members[0].reason == "RAW_PARTITION_CORRUPT"
    assert result.breadth is not None
    assert (
        result.breadth.requested_count,
        result.breadth.observed_count,
        result.breadth.advances,
        result.breadth.declines,
        result.breadth.unchanged,
        result.breadth.insufficient_count,
        result.breadth.label,
    ) == (2, 1, 0, 0, 1, 1, None)


def test_public_n50_success_and_n51_request_rejection_are_effect_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = seed_root(tmp_path / "base")
    members = tuple(_member(index) for index in range(1, 51))
    raw_request = CurrentRawPriceContextInputV1(
        base.request_identity_sha256,
        base.data_selection_time,
        base.admission_deadline,
        base.schedule_identity_sha256,
        members,
    )
    root = tmp_path / "retained"
    seed_root(root, retained_action=True, request_value=raw_request)
    wire = RecordedWire([WireReply(body=historical_body()) for _ in members])
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    acquired = acquire_missing_current_raw_evidence_v1(
        raw_request, root, control=fixture_control(raw_request)
    )
    assert acquired.outcome == "ACQUISITION_COMPLETED"
    assert acquired.provider_calls == wire.attempts == 50
    reference = _retain_industry_for_raw(root, raw_request)
    request = _public_request(raw_request, reference)
    provider_attempts = wire.attempts
    credential_calls = FixtureTokenProvider.calls

    first = research_current_price_context_v1(
        request, root, clock=_Clock(raw_request.data_selection_time)
    )
    second = research_current_price_context_v1(
        request, root, clock=_Clock(raw_request.data_selection_time)
    )

    assert len(first.members) == 50
    assert tuple(item.position for item in first.members) == tuple(range(50))
    assert tuple(item.isin for item in first.members) == tuple(
        member.isin for member in members
    )
    assert all(item.state == "OBSERVED" for item in first.members)
    assert first.breadth is not None
    assert (
        first.breadth.requested_count,
        first.breadth.observed_count,
        first.breadth.advances,
        first.breadth.declines,
        first.breadth.unchanged,
        first.breadth.insufficient_count,
    ) == (50, 50, 0, 0, 50, 0)
    assert first.industry_evidence_state == "OBSERVED"
    assert sum(group.member_count for group in first.industry_groups) == 50
    assert sum(group.unchanged for group in first.industry_groups) == 50
    assert first.acquisition_mode == "RETAINED_ONLY"
    assert first.acquisition_provider_calls == 0
    assert wire.attempts == provider_attempts == 50
    assert FixtureTokenProvider.calls == credential_calls
    assert len(first.canonical_json_bytes()) <= 1_048_576
    payload = first.canonical_json_bytes().decode()
    for private in (str(root), "fixture-token", "https://", "Authorization", "raw-"):
        assert private not in payload
    assert first == second
    assert first.result_identity_sha256 == second.result_identity_sha256
    assert first.canonical_json_bytes() == second.canonical_json_bytes()

    with pytest.raises(ValueError, match="request is invalid"):
        CurrentPriceContextRequestV1(
            "current-price-context-request@v1",
            raw_request.data_selection_time,
            raw_request.admission_deadline,
            raw_request.schedule_identity_sha256,
            members + (_member(51),),
            (
                "RAW_MARKET_STRUCTURE",
                "RAW_20_SESSION_DIRECTION",
                "RAW_COHORT_BREADTH",
                "RAW_INDUSTRY_PARTICIPATION",
            ),
            None,
        )


def test_public_directions_cover_advance_decline_and_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = {
        "ADVANCE": (100.0, 101.0),
        "DECLINE": (101.0, 100.0),
        "UNCHANGED": (100.0, 100.0),
    }
    for direction, (first, last) in expected.items():
        root = tmp_path / direction.lower()
        raw_request = seed_root(root, retained_action=True)
        closes = (
            (90.0, first) + (100.5,) * (len(fixture_schedule().sessions) - 3) + (last,)
        )
        wire = RecordedWire([WireReply(body=historical_body(closes=closes))])
        monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
        monkeypatch.setattr(
            acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
        )
        assert (
            acquire_missing_current_raw_evidence_v1(
                raw_request, root, control=fixture_control(raw_request)
            ).outcome
            == "ACQUISITION_COMPLETED"
        )
        result = research_current_price_context_v1(
            _public_request(raw_request),
            root,
            clock=_Clock(raw_request.data_selection_time),
        )
        assert result.members[0].direction == direction
        assert result.members[0].structure is not None


def test_public_deadline_cancellation_and_unsafe_root_stop_before_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "retained"
    raw_request = seed_root(root)
    wire = RecordedWire([])
    FixtureTokenProvider.calls = 0
    monkeypatch.setattr(transport_module, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    request = _public_request(raw_request)

    with pytest.raises(ValueError, match="deadline exceeded"):
        research_current_price_context_v1(
            request,
            root,
            acquire_missing=True,
            clock=_Clock(raw_request.admission_deadline),
        )

    class _Cancelled:
        def is_cancelled(self) -> bool:
            return True

    cancelled = research_current_price_context_v1(
        request,
        root,
        acquire_missing=True,
        clock=_Clock(raw_request.data_selection_time),
        cancellation=_Cancelled(),
    )
    assert (
        cancelled.acquisition_outcome,
        cancelled.acquisition_provider_calls,
        cancelled.members[0].reason,
    ) == ("STOPPED", 0, "ACQUISITION_STOPPED")
    root.chmod(0o755)
    unsafe = research_current_price_context_v1(
        request,
        root,
        acquire_missing=True,
        clock=_Clock(raw_request.data_selection_time),
    )
    assert (
        unsafe.acquisition_outcome,
        unsafe.acquisition_provider_calls,
        unsafe.members[0].reason,
    ) == ("STOPPED", 0, "ACQUISITION_STOPPED")
    assert wire.attempts == FixtureTokenProvider.calls == 0


def test_public_explicit_acquisition_reports_partial_and_shared_stop_safely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = seed_root(tmp_path / "base", retained_action=True)
    raw_request = CurrentRawPriceContextInputV1(
        base.request_identity_sha256,
        base.data_selection_time,
        base.admission_deadline,
        base.schedule_identity_sha256,
        (base.members[0], _member(2)),
    )
    partial_root = tmp_path / "partial"
    seed_root(partial_root, retained_action=True, request_value=raw_request)
    partial_wire = RecordedWire(
        [WireReply(status=404), WireReply(body=historical_body())]
    )
    monkeypatch.setattr(transport_module, "build_opener", partial_wire.build_opener)
    monkeypatch.setattr(
        acquisition_module, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    partial = research_current_price_context_v1(
        _public_request(raw_request),
        partial_root,
        acquire_missing=True,
        clock=_Clock(raw_request.data_selection_time),
    )
    assert (
        partial.acquisition_outcome,
        partial.acquisition_provider_calls,
        partial.members[0].state,
        partial.members[1].state,
    ) == ("ACQUISITION_PARTIAL", 2, "INSUFFICIENT_EVIDENCE", "OBSERVED")

    stopped_root = tmp_path / "stopped"
    seed_root(stopped_root, retained_action=True, request_value=raw_request)
    stopped_wire = RecordedWire([WireReply(status=401)])
    monkeypatch.setattr(transport_module, "build_opener", stopped_wire.build_opener)
    stopped = research_current_price_context_v1(
        _public_request(raw_request),
        stopped_root,
        acquire_missing=True,
        clock=_Clock(raw_request.data_selection_time),
    )
    assert (
        stopped.acquisition_outcome,
        stopped.acquisition_provider_calls,
        stopped_wire.attempts,
    ) == ("STOPPED", 1, 1)
    payload = stopped.canonical_json_bytes().decode()
    assert "AUTHENTICATION_FAILED" not in payload
    assert "fixture-token" not in payload


def test_public_request_decoder_rejects_malformed_oversize_nested_and_enum_values() -> (
    None
):
    raw = (
        json.dumps(
            {
                "contract_version": "current-price-context-request@v1",
                "data_selection_time": "2026-09-15T09:00:00.000000Z",
                "admission_deadline": "2026-09-15T09:30:00.000000Z",
                "schedule_identity_sha256": "a" * 64,
                "members": [],
                "questions": [],
                "industry_archive_reference": None,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )
    for value in (
        raw.replace(b'"questions":[]', b'"questions":["UNKNOWN"]'),
        raw[:-1] + b',"unknown":true}\n',
        b"[" * 2_000 + b"]" * 2_000,
        b"x" * (64 * 1024 + 1),
    ):
        with pytest.raises(ValueError, match="request is invalid"):
            current_price_context_request_from_canonical_json_bytes_v1(value)
