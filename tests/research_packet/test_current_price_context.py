"""RED contract tests for Issue #188's public price-context boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.current_raw_acquisition as acquisition_module
import swing_trading_ai_assistant.market_data.current_raw_acquisition_transport as transport_module
from swing_trading_ai_assistant.market_data import (
    current_industry_classification as classification,
)
from swing_trading_ai_assistant.market_data.current_raw_acquisition import (
    acquire_missing_current_raw_evidence_v1,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentRawPriceContextInputV1,
    read_retained_current_raw_context_v1,
    validate_admitted_current_raw_context_v1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.research_packet.current_price_context import (
    CurrentIndustryArchiveReferenceV1,
    CurrentPriceContextMemberV1,
    CurrentPriceContextRequestV1,
    current_price_context_request_from_canonical_json_bytes_v1,
    research_current_price_context_v1,
)
from tests.market_data.current_raw_acquisition_fixtures import (
    FixtureTokenProvider,
    RecordedWire,
    WireReply,
    action_body,
    historical_body,
    seed_root,
)
from tests.market_data.current_raw_acquisition_fixtures import (
    control as fixture_control,
)


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def _member(index: int) -> CurrentPriceContextMemberV1:
    return CurrentPriceContextMemberV1(
        isin=f"INE000A01{index:03d}",
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


def _classification_artifact(member: CurrentPriceContextMemberV1) -> bytes:
    header = "Company Name,Industry,Symbol,Series,ISIN Code"
    rows = [
        f"Company {index:03d},Banking,{'ACME' if index == 0 else f'SYM{index:03d}'},EQ,{'INE467B01029' if index == 0 else _classification_isin(index)}"
        for index in range(100)
    ]
    rows[0] = f"Company 000,Banking,{member.effective_symbol},EQ,{member.isin}"
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
    member = raw_request.members[0]
    artifact = _classification_artifact(member)
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
