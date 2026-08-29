from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

import pytest

from swing_trading_ai_assistant.historical_evaluation import (
    capability_validation,
    capability_validation_service,
)
from swing_trading_ai_assistant.historical_evaluation.capability_validation import (
    AvailabilityStateV1,
    CanonicalEquityV1,
    HistoricalAvailabilityEntryV1,
    HistoricalBarKnowledgeV1,
    HistoricalComparabilityProvenanceV1,
    HistoricalDecisionPointV1,
    HistoricalEvidenceFeatureV1,
    HistoricalEvidenceRevisionV1,
    HistoricalStudyDeclarationV1,
    HistoricalStudyProfileV1,
    HistoricalStudyRegionV1,
    HistoricalValidationReasonV1,
    HistoricalValidationReportV1,
    HistoricalValidationRequestV1,
    HistoricalValidationRuntimeIdentityError,
    MarketStructureReadinessGateV1,
    ProfileQualificationOutcomeV1,
    ProfileValidationResultV1,
    build_blocked_historical_validation_report_v1,
    capability_validation_current_identities_v1,
    evaluate_capability_aware_historical_validation_v1,
    historical_evidence_from_sprint15_revision_v1,
    parse_historical_validation_request_v1,
)
from swing_trading_ai_assistant.historical_evaluation.capability_validation_cli import (
    main as validation_cli_main,
)
from swing_trading_ai_assistant.historical_evaluation.capability_validation_service import (
    HistoricalValidationServiceV1,
)
from swing_trading_ai_assistant.market_data.historical_revision_store import (
    HistoricalOhlcvImportOutcomeV1,
    HistoricalOhlcvImportResultV1,
)

_MEMBER = CanonicalEquityV1("INE002A01018", "NSE")
_OTHER_MEMBER = CanonicalEquityV1("INE062A01020", "NSE")
_REVISION = "1" * 64
_SOURCE = "2" * 64
_CONTEXT_REVISION = "3" * 64
_RECEIPT = "4" * 64
_SCHEMA = "5" * 64
_EVIDENCE_RUNTIME = "6" * 64
_EVIDENCE_CONFIGURATION = "7" * 64
_BASE = datetime(2025, 1, 1, 10, tzinfo=UTC)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _points() -> tuple[HistoricalDecisionPointV1, ...]:
    return tuple(
        HistoricalDecisionPointV1(
            session=date(2025, 1, offset + 1),
            decision_cutoff=_BASE + timedelta(days=offset),
            region=region,
        )
        for offset, region in enumerate(HistoricalStudyRegionV1)
    )


def _comparability_provenance(
    points: tuple[HistoricalDecisionPointV1, ...],
) -> tuple[HistoricalComparabilityProvenanceV1, ...]:
    return tuple(
        HistoricalComparabilityProvenanceV1(
            member=_MEMBER,
            session=point.session,
            source_identity_sha256=_SOURCE,
            classification_receipt_sha256=_RECEIPT,
            evidence_revision_sha256=_CONTEXT_REVISION,
            published_at=point.decision_cutoff - timedelta(hours=2),
            known_at=point.decision_cutoff - timedelta(hours=1),
        )
        for point in points
    )


def _evidence(
    *,
    temporal_status: str = "POINT_IN_TIME",
    corporate_action_status: str = "EVALUATED",
    comparability_status: str = "ESTABLISHED",
) -> HistoricalEvidenceRevisionV1:
    points = _points()
    return HistoricalEvidenceRevisionV1(
        revision_contract_version="test-pit-revision@v1",
        revision_sha256=_REVISION,
        cohort=(_MEMBER,),
        sessions=tuple(point.session for point in points),
        interval="1d",
        source_profile="TEST_PIT",
        price_basis="SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED",
        temporal_status=temporal_status,
        corporate_action_status=corporate_action_status,
        comparability_status=comparability_status,
        permitted_use="OWNER_PRIVATE_RESEARCH",
        bars=tuple(
            HistoricalBarKnowledgeV1(
                member=_MEMBER,
                session=point.session,
                known_at=point.decision_cutoff - timedelta(hours=1),
            )
            for point in points
        ),
        comparability_provenance=(
            _comparability_provenance(points)
            if corporate_action_status == "EVALUATED"
            and comparability_status == "ESTABLISHED"
            else ()
        ),
        source_identity_sha256=_SOURCE,
        schema_identity_sha256=_SCHEMA,
        runtime_code_identity_sha256=_EVIDENCE_RUNTIME,
        configuration_identity_sha256=_EVIDENCE_CONFIGURATION,
        limitation="FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION",
    )


def _evidence_with_extra_session() -> HistoricalEvidenceRevisionV1:
    evidence = _evidence()
    session = evidence.sessions[-1] + timedelta(days=1)
    return replace(
        evidence,
        sessions=(*evidence.sessions, session),
        bars=(
            *evidence.bars,
            HistoricalBarKnowledgeV1(
                member=_MEMBER,
                session=session,
                known_at=_BASE + timedelta(days=3, hours=23),
            ),
        ),
        comparability_provenance=(
            *evidence.comparability_provenance,
            HistoricalComparabilityProvenanceV1(
                member=_MEMBER,
                session=session,
                source_identity_sha256=_SOURCE,
                classification_receipt_sha256=_RECEIPT,
                evidence_revision_sha256=_CONTEXT_REVISION,
                published_at=_BASE + timedelta(days=3, hours=22),
                known_at=_BASE + timedelta(days=3, hours=23),
            ),
        ),
    )


def _entry(
    point: HistoricalDecisionPointV1,
    feature: HistoricalEvidenceFeatureV1,
    *,
    state: AvailabilityStateV1 = AvailabilityStateV1.AVAILABLE,
    known_at: datetime | None = None,
) -> HistoricalAvailabilityEntryV1:
    available = state in {
        AvailabilityStateV1.AVAILABLE,
        AvailabilityStateV1.STALE,
    }
    conflicted = state is AvailabilityStateV1.CONFLICTED
    revision = (
        _REVISION
        if feature is HistoricalEvidenceFeatureV1.DAILY_OHLCV
        else _CONTEXT_REVISION
    )
    return HistoricalAvailabilityEntryV1(
        feature=feature,
        member=_MEMBER,
        session=point.session,
        interval=(
            "1d"
            if feature
            in {
                HistoricalEvidenceFeatureV1.DAILY_OHLCV,
                HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY,
            }
            else "as_of"
        ),
        decision_cutoff=point.decision_cutoff,
        state=state,
        source_identity_sha256=_SOURCE,
        classification_receipt_sha256=_RECEIPT,
        evidence_revision_sha256=(revision if available or conflicted else None),
        published_at=(
            point.decision_cutoff - timedelta(hours=2) if available else None
        ),
        known_at=(
            known_at
            if known_at is not None
            else point.decision_cutoff - timedelta(hours=1)
            if available
            else None
        ),
    )


def _request(
    *,
    entries: tuple[HistoricalAvailabilityEntryV1, ...] | None = None,
    thresholds: dict[HistoricalStudyProfileV1, int] | None = None,
    cohort_identity_sha256: str | None = None,
) -> HistoricalValidationRequestV1:
    points = _points()
    if entries is None:
        entries = tuple(
            _entry(point, feature)
            for point in points
            for feature in HistoricalEvidenceFeatureV1
        )
    thresholds = thresholds or {}
    schema, runtime, configuration = capability_validation_current_identities_v1()
    return HistoricalValidationRequestV1(
        contract_version="capability-aware-historical-validation-gate@v1",
        evaluated_at=_BASE + timedelta(days=10),
        evidence_revision_sha256=_REVISION,
        cohort_identity_sha256=cohort_identity_sha256
        or _evidence().cohort_identity_sha256,
        cohort=(_MEMBER,),
        decision_points=points,
        studies=tuple(
            HistoricalStudyDeclarationV1(
                profile=profile,
                minimum_coverage_bps=thresholds.get(profile, 10_000),
            )
            for profile in HistoricalStudyProfileV1
        ),
        availability_ledger=entries,
        schema_identity_sha256=schema,
        runtime_code_identity_sha256=runtime,
        configuration_identity_sha256=configuration,
    )


def _request_bytes_with_entries(
    entries: tuple[HistoricalAvailabilityEntryV1, ...],
) -> bytes:
    ordered = tuple(
        sorted(
            entries,
            key=lambda entry: (
                entry.session,
                tuple(HistoricalEvidenceFeatureV1).index(entry.feature),
                entry.member.isin,
                entry.member.exchange,
            ),
        )
    )
    value = _request().canonical_value()
    rows = [entry.canonical_value() for entry in ordered]
    value["availability_ledger"] = rows
    value["ledger_identity_sha256"] = _sha(rows)
    value.pop("request_identity_sha256")
    value["request_identity_sha256"] = _sha(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _result_for_profile(
    report: HistoricalValidationReportV1, profile: HistoricalStudyProfileV1
) -> ProfileValidationResultV1:
    return next(value for value in report.profile_results if value.profile is profile)


def test_complete_point_in_time_profiles_approve_market_structure_start() -> None:
    report = evaluate_capability_aware_historical_validation_v1(_request(), _evidence())

    assert (
        report.gate is MarketStructureReadinessGateV1.APPROVED_TO_START_MARKET_STRUCTURE
    )
    assert report.gate_reasons == ()
    assert [result.outcome for result in report.profile_results] == [
        ProfileQualificationOutcomeV1.QUALIFIED,
        ProfileQualificationOutcomeV1.QUALIFIED,
        ProfileQualificationOutcomeV1.QUALIFIED,
    ]
    assert [result.total_required_cells for result in report.profile_results] == [
        8,
        12,
        12,
    ]
    assert all(result.coverage_bps == 10_000 for result in report.profile_results)
    assert (
        report.canonical_json_bytes()
        == evaluate_capability_aware_historical_validation_v1(
            _request(), _evidence()
        ).canonical_json_bytes()
    )
    assert len(report.report_identity_sha256) == 64


def test_non_daily_evidence_revision_is_rejected_before_qualification() -> None:
    with pytest.raises(ValueError, match="historical evidence revision is invalid"):
        replace(_evidence(), interval="1m")


def test_request_grid_must_equal_the_complete_evidence_grid() -> None:
    with pytest.raises(ValueError, match="decision grid mismatch"):
        evaluate_capability_aware_historical_validation_v1(
            _request(), _evidence_with_extra_session()
        )


@pytest.mark.parametrize(
    ("missing_feature", "blocked_profile", "unaffected_profile"),
    (
        (
            HistoricalEvidenceFeatureV1.SECTOR_CLASSIFICATION,
            HistoricalStudyProfileV1.OHLCV_PLUS_SECTOR,
            HistoricalStudyProfileV1.OHLCV_PLUS_NEWS_EVENTS,
        ),
        (
            HistoricalEvidenceFeatureV1.NEWS_EVENTS,
            HistoricalStudyProfileV1.OHLCV_PLUS_NEWS_EVENTS,
            HistoricalStudyProfileV1.OHLCV_PLUS_SECTOR,
        ),
    ),
)
def test_missing_context_evidence_blocks_only_its_profile(
    missing_feature: HistoricalEvidenceFeatureV1,
    blocked_profile: HistoricalStudyProfileV1,
    unaffected_profile: HistoricalStudyProfileV1,
) -> None:
    entries = tuple(
        _entry(
            point,
            feature,
            state=(
                AvailabilityStateV1.NOT_RETAINED
                if feature is missing_feature
                else AvailabilityStateV1.AVAILABLE
            ),
        )
        for point in _points()
        for feature in HistoricalEvidenceFeatureV1
    )
    report = evaluate_capability_aware_historical_validation_v1(
        _request(entries=entries), _evidence()
    )

    blocked = _result_for_profile(report, blocked_profile)
    assert blocked.outcome is ProfileQualificationOutcomeV1.INSUFFICIENT_EVIDENCE
    assert blocked.state_counts[AvailabilityStateV1.NOT_RETAINED] == 4
    assert HistoricalValidationReasonV1.EVIDENCE_NOT_RETAINED in blocked.reasons
    assert (
        _result_for_profile(report, HistoricalStudyProfileV1.OHLCV_ONLY).outcome
        is ProfileQualificationOutcomeV1.QUALIFIED
    )
    assert (
        _result_for_profile(report, unaffected_profile).outcome
        is ProfileQualificationOutcomeV1.QUALIFIED
    )
    assert (
        report.gate is MarketStructureReadinessGateV1.APPROVED_TO_START_MARKET_STRUCTURE
    )


@pytest.mark.parametrize(
    ("state", "expected_reason"),
    (
        (
            AvailabilityStateV1.NOT_PUBLISHED,
            HistoricalValidationReasonV1.EVIDENCE_NOT_PUBLISHED,
        ),
        (
            AvailabilityStateV1.NOT_RETAINED,
            HistoricalValidationReasonV1.EVIDENCE_NOT_RETAINED,
        ),
        (
            AvailabilityStateV1.SOURCE_GAP,
            HistoricalValidationReasonV1.EVIDENCE_SOURCE_GAP,
        ),
        (AvailabilityStateV1.STALE, HistoricalValidationReasonV1.EVIDENCE_STALE),
        (
            AvailabilityStateV1.CONFLICTED,
            HistoricalValidationReasonV1.EVIDENCE_CONFLICTED,
        ),
        (
            AvailabilityStateV1.UNLICENSED,
            HistoricalValidationReasonV1.EVIDENCE_UNLICENSED,
        ),
    ),
)
@pytest.mark.parametrize("point_index", range(4))
def test_each_nonavailable_state_remains_in_denominator(
    state: AvailabilityStateV1,
    expected_reason: HistoricalValidationReasonV1,
    point_index: int,
) -> None:
    first = _points()[point_index]
    entries = list(_request().availability_ledger)
    target = next(
        index
        for index, value in enumerate(entries)
        if value.session == first.session
        and value.feature is HistoricalEvidenceFeatureV1.DAILY_OHLCV
    )
    entries[target] = _entry(
        first, HistoricalEvidenceFeatureV1.DAILY_OHLCV, state=state
    )

    report = evaluate_capability_aware_historical_validation_v1(
        _request(entries=tuple(entries)), _evidence()
    )
    result = _result_for_profile(report, HistoricalStudyProfileV1.OHLCV_ONLY)

    assert result.outcome is ProfileQualificationOutcomeV1.INSUFFICIENT_EVIDENCE
    assert result.total_required_cells == 8
    assert result.available_cells == 7
    assert result.coverage_bps == 8_750
    assert result.state_counts[state] == 1
    expected_profile_reasons = {
        expected_reason,
        HistoricalValidationReasonV1.COVERAGE_BELOW_PREDECLARED_THRESHOLD,
    }
    assert result.reasons == tuple(
        reason
        for reason in HistoricalValidationReasonV1
        if reason in expected_profile_reasons
    )
    assert report.gate is MarketStructureReadinessGateV1.BLOCKED
    assert report.gate_reasons == tuple(
        reason
        for reason in HistoricalValidationReasonV1
        if reason
        in {
            *expected_profile_reasons,
            HistoricalValidationReasonV1.OHLCV_ONLY_NOT_QUALIFIED,
        }
    )


def test_future_known_available_cell_fails_closed_without_dropping_date() -> None:
    first = _points()[0]
    entries = list(_request().availability_ledger)
    target = next(
        index
        for index, value in enumerate(entries)
        if value.session == first.session
        and value.feature is HistoricalEvidenceFeatureV1.DAILY_OHLCV
    )
    entries[target] = _entry(
        first,
        HistoricalEvidenceFeatureV1.DAILY_OHLCV,
        known_at=first.decision_cutoff + timedelta(seconds=1),
    )

    report = evaluate_capability_aware_historical_validation_v1(
        _request(entries=tuple(entries)), _evidence()
    )
    result = _result_for_profile(report, HistoricalStudyProfileV1.OHLCV_ONLY)

    assert result.outcome is ProfileQualificationOutcomeV1.INSUFFICIENT_EVIDENCE
    assert HistoricalValidationReasonV1.FUTURE_KNOWN_EVIDENCE in result.reasons
    assert result.total_required_cells == 8
    assert report.gate is MarketStructureReadinessGateV1.BLOCKED


def test_future_known_stale_cell_is_fatal_despite_permissive_threshold() -> None:
    first = _points()[0]
    entries = list(_request().availability_ledger)
    target = next(
        index
        for index, value in enumerate(entries)
        if value.session == first.session
        and value.feature is HistoricalEvidenceFeatureV1.SECTOR_CLASSIFICATION
    )
    entries[target] = _entry(
        first,
        HistoricalEvidenceFeatureV1.SECTOR_CLASSIFICATION,
        state=AvailabilityStateV1.STALE,
        known_at=first.decision_cutoff + timedelta(seconds=1),
    )
    request = _request(
        entries=tuple(entries),
        thresholds={HistoricalStudyProfileV1.OHLCV_PLUS_SECTOR: 9_000},
    )

    report = evaluate_capability_aware_historical_validation_v1(request, _evidence())
    result = _result_for_profile(report, HistoricalStudyProfileV1.OHLCV_PLUS_SECTOR)

    assert result.coverage_bps == 9_166
    assert result.outcome is ProfileQualificationOutcomeV1.INSUFFICIENT_EVIDENCE
    assert HistoricalValidationReasonV1.FUTURE_KNOWN_EVIDENCE in result.reasons


def test_missing_cell_is_insufficient_and_duplicate_or_extra_cell_is_invalid() -> None:
    entries = _request().availability_ledger
    missing_report = evaluate_capability_aware_historical_validation_v1(
        _request(entries=entries[:-1]), _evidence()
    )
    assert HistoricalValidationReasonV1.AVAILABILITY_LEDGER_INCOMPLETE in (
        _result_for_profile(
            missing_report, HistoricalStudyProfileV1.OHLCV_PLUS_NEWS_EVENTS
        ).reasons
    )

    with pytest.raises(ValueError, match="availability ledger is invalid"):
        _request(entries=(*entries, entries[0]))

    with pytest.raises(ValueError, match="availability entry is invalid"):
        replace(entries[0], interval="as_of")


def test_lower_predeclared_ohlcv_threshold_never_authorizes_market_structure() -> None:
    first = _points()[0]
    entries = tuple(
        _entry(
            point,
            feature,
            state=(
                AvailabilityStateV1.NOT_RETAINED
                if point == first and feature is HistoricalEvidenceFeatureV1.DAILY_OHLCV
                else AvailabilityStateV1.AVAILABLE
            ),
        )
        for point in _points()
        for feature in HistoricalEvidenceFeatureV1
    )
    request = _request(
        entries=entries,
        thresholds={HistoricalStudyProfileV1.OHLCV_ONLY: 8_000},
    )
    report = evaluate_capability_aware_historical_validation_v1(request, _evidence())

    assert (
        _result_for_profile(report, HistoricalStudyProfileV1.OHLCV_ONLY).outcome
        is ProfileQualificationOutcomeV1.QUALIFIED
    )
    assert report.gate is MarketStructureReadinessGateV1.BLOCKED
    assert (
        HistoricalValidationReasonV1.GATE_COVERAGE_THRESHOLD_BELOW_100_PERCENT
        in report.gate_reasons
    )


def test_region_and_cohort_substitution_are_rejected() -> None:
    points = _points()
    with pytest.raises(ValueError, match="decision regions are invalid"):
        replace(
            _request(),
            decision_points=(
                replace(points[0], region=HistoricalStudyRegionV1.OUT_OF_SAMPLE),
                *points[1:],
            ),
        )

    with pytest.raises(ValueError, match="cohort identity mismatch"):
        evaluate_capability_aware_historical_validation_v1(
            _request(cohort_identity_sha256="f" * 64), _evidence()
        )


def test_sprint15_raw_revision_preserves_non_pit_and_comparability_limits() -> None:
    revision: dict[str, Any] = {
        "contract_version": "fixed-cohort-historical-ohlcv-upstox-raw-revision-store@v1",
        "research_scope": "FIXED_COHORT_RETROSPECTIVE",
        "source_profile": "UPSTOX_RAW",
        "cohort": [
            {
                "isin": _MEMBER.isin,
                "exchange": _MEMBER.exchange,
                "listed_equity_segment": "EQUITY",
                "effective_symbol": "RELIANCE",
                "symbol_effective_from": "2020-01-01",
                "symbol_effective_to": None,
                "provider_mapping": {},
            }
        ],
        "from_session": "2025-01-01",
        "to_session": "2025-01-04",
        "interval": "1d",
        "expected_sessions": [point.session.isoformat() for point in _points()],
        "price_basis": "RAW",
        "temporal_status": "REVISED_NON_PIT",
        "corporate_action_status": "NOT_EVALUATED",
        "comparability_status": "NOT_ESTABLISHED",
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
        "source_policy_sha256": _SOURCE,
        "schema_identity_sha256": _SCHEMA,
        "runtime_code_identity_sha256": _EVIDENCE_RUNTIME,
        "configuration_identity_sha256": _EVIDENCE_CONFIGURATION,
        "context_status": "HISTORICAL_CONTEXT_NOT_EVALUATED",
        "limitation": "FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION",
        "bars": [
            {
                "isin": _MEMBER.isin,
                "exchange": _MEMBER.exchange,
                "session": point.session.isoformat(),
                "known_at": (point.decision_cutoff + timedelta(days=30)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "price_basis": "RAW",
            }
            for point in _points()
        ],
    }
    revision["revision_sha256"] = _sha(revision)
    evidence = historical_evidence_from_sprint15_revision_v1(revision)
    entries = tuple(
        _entry(point, feature, state=AvailabilityStateV1.NOT_RETAINED)
        for point in _points()
        for feature in HistoricalEvidenceFeatureV1
    )
    request = replace(
        _request(entries=entries),
        evidence_revision_sha256=evidence.revision_sha256,
        cohort_identity_sha256=evidence.cohort_identity_sha256,
    )

    report = evaluate_capability_aware_historical_validation_v1(request, evidence)

    assert report.gate is MarketStructureReadinessGateV1.BLOCKED
    assert report.evidence_temporal_status == "REVISED_NON_PIT"
    assert report.evidence_comparability_status == "NOT_ESTABLISHED"
    assert report.limitation == (
        "FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION"
    )


def test_canonical_request_round_trips_without_losing_identities() -> None:
    request = _request()

    parsed = parse_historical_validation_request_v1(request.canonical_json_bytes())

    assert parsed == request
    assert parsed.request_identity_sha256 == request.request_identity_sha256
    assert parsed.ledger_identity_sha256 == request.ledger_identity_sha256


def test_parser_rejects_stale_runtime_identity_before_store_access() -> None:
    stale = replace(_request(), runtime_code_identity_sha256="f" * 64)

    with pytest.raises(
        ValueError, match="historical validation request JSON is invalid"
    ):
        parse_historical_validation_request_v1(stale.canonical_json_bytes())


@pytest.mark.parametrize(
    "raw",
    (
        b'{"duplicate":1,"duplicate":2}\n',
        b'{"float":1.0}\n',
        b"{}\n",
        b"{}",
        b"[" * 2_048 + b"]" * 2_048 + b"\n",
    ),
)
def test_request_parser_rejects_duplicate_float_unknown_and_noncanonical_json(
    raw: bytes,
) -> None:
    with pytest.raises(
        ValueError, match="historical validation request JSON is invalid"
    ):
        parse_historical_validation_request_v1(raw)


@pytest.mark.parametrize("mismatch", ("member", "session", "cutoff"))
def test_cli_rejects_out_of_grid_ledger_before_service_access(
    mismatch: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    entries = list(_request().availability_ledger)
    entry = entries[0]
    if mismatch == "member":
        entries[0] = replace(entry, member=_OTHER_MEMBER)
    elif mismatch == "session":
        entries[0] = replace(entry, session=date(2025, 2, 1))
    else:
        entries[0] = replace(
            entry, decision_cutoff=entry.decision_cutoff + timedelta(minutes=1)
        )
    request_path = _write_request_file(
        tmp_path, _request_bytes_with_entries(tuple(entries))
    )
    called = False

    def evaluate(
        self: object, request: HistoricalValidationRequestV1
    ) -> HistoricalValidationReportV1:
        del self, request
        nonlocal called
        called = True
        raise AssertionError

    monkeypatch.setattr(
        capability_validation_service.HistoricalValidationServiceV1,
        "evaluate",
        evaluate,
    )

    exit_code = validation_cli_main(
        [
            "--request-file",
            str(request_path),
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "request_invalid\n"
    assert not called


def test_unavailable_exact_revision_returns_complete_blocked_accounting() -> None:
    report = build_blocked_historical_validation_report_v1(_request())

    assert report.gate is MarketStructureReadinessGateV1.BLOCKED
    assert report.evidence_identity_sha256 is None
    assert (
        HistoricalValidationReasonV1.EVIDENCE_REVISION_UNAVAILABLE
        in report.gate_reasons
    )
    assert [result.total_required_cells for result in report.profile_results] == [
        8,
        12,
        12,
    ]
    assert all(result.available_cells == 0 for result in report.profile_results)


def test_unavailable_report_includes_sub_100_percent_gate_threshold_reason() -> None:
    report = build_blocked_historical_validation_report_v1(
        _request(thresholds={HistoricalStudyProfileV1.OHLCV_ONLY: 8_000})
    )

    assert report.gate_reasons == tuple(
        reason
        for reason in HistoricalValidationReasonV1
        if reason
        in {
            HistoricalValidationReasonV1.EVIDENCE_REVISION_UNAVAILABLE,
            HistoricalValidationReasonV1.COVERAGE_BELOW_PREDECLARED_THRESHOLD,
            HistoricalValidationReasonV1.GATE_COVERAGE_THRESHOLD_BELOW_100_PERCENT,
            HistoricalValidationReasonV1.OHLCV_ONLY_NOT_QUALIFIED,
        }
    )


def test_service_reads_only_the_exact_named_revision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requested: list[str] = []

    def read_exact(self: object, revision_sha256: str) -> HistoricalOhlcvImportResultV1:
        del self
        requested.append(revision_sha256)
        return HistoricalOhlcvImportResultV1(
            HistoricalOhlcvImportOutcomeV1.SUCCESS,
            _REVISION,
            {"revision_sha256": _REVISION},
        )

    def project_revision(
        revision: Mapping[str, Any],
    ) -> HistoricalEvidenceRevisionV1:
        del revision
        return _evidence()

    monkeypatch.setattr(
        capability_validation_service.HistoricalOhlcvRevisionStoreV1,
        "read_exact",
        read_exact,
    )
    monkeypatch.setattr(
        capability_validation_service,
        "historical_evidence_from_sprint15_revision_v1",
        project_revision,
    )

    report = HistoricalValidationServiceV1(tmp_path).evaluate(_request())

    assert requested == [_REVISION]
    assert (
        report.gate is MarketStructureReadinessGateV1.APPROVED_TO_START_MARKET_STRUCTURE
    )


def test_service_rejects_stale_identity_before_exact_store_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    called = False

    def read_exact(self: object, revision_sha256: str) -> HistoricalOhlcvImportResultV1:
        del self, revision_sha256
        nonlocal called
        called = True
        raise AssertionError

    monkeypatch.setattr(
        capability_validation_service.HistoricalOhlcvRevisionStoreV1,
        "read_exact",
        read_exact,
    )
    stale = replace(_request(), runtime_code_identity_sha256="f" * 64)

    with pytest.raises(ValueError, match="validation request identity mismatch"):
        HistoricalValidationServiceV1(tmp_path).evaluate(stale)
    assert not called


@pytest.mark.parametrize(
    ("request_kind", "expected_reason"),
    (
        ("cohort", HistoricalValidationReasonV1.COHORT_IDENTITY_MISMATCH),
        ("grid", HistoricalValidationReasonV1.DECISION_GRID_MISMATCH),
        ("omitted_grid", HistoricalValidationReasonV1.DECISION_GRID_MISMATCH),
    ),
)
def test_cli_returns_blocked_report_for_exact_revision_binding_mismatch(
    request_kind: str,
    expected_reason: HistoricalValidationReasonV1,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def read_exact(self: object, revision_sha256: str) -> HistoricalOhlcvImportResultV1:
        del self, revision_sha256
        return HistoricalOhlcvImportResultV1(
            HistoricalOhlcvImportOutcomeV1.SUCCESS,
            _REVISION,
            {"revision_sha256": _REVISION},
        )

    def project_revision(
        revision: Mapping[str, Any],
    ) -> HistoricalEvidenceRevisionV1:
        del revision
        return (
            _evidence_with_extra_session()
            if request_kind == "omitted_grid"
            else _evidence()
        )

    monkeypatch.setattr(
        capability_validation_service.HistoricalOhlcvRevisionStoreV1,
        "read_exact",
        read_exact,
    )
    monkeypatch.setattr(
        capability_validation_service,
        "historical_evidence_from_sprint15_revision_v1",
        project_revision,
    )
    if request_kind == "cohort":
        ledger = tuple(
            replace(entry, member=_OTHER_MEMBER)
            for entry in _request().availability_ledger
        )
        request = replace(
            _request(),
            cohort=(_OTHER_MEMBER,),
            cohort_identity_sha256=_sha([_OTHER_MEMBER.canonical_value()]),
            availability_ledger=ledger,
        )
    elif request_kind == "grid":
        points = (
            *_points()[:3],
            replace(
                _points()[3],
                session=date(2025, 1, 5),
                decision_cutoff=_BASE + timedelta(days=4),
            ),
        )
        request = replace(
            _request(),
            decision_points=points,
            availability_ledger=tuple(
                _entry(point, feature)
                for point in points
                for feature in HistoricalEvidenceFeatureV1
            ),
        )
    else:
        request = _request()
    request_path = _write_request_file(tmp_path, request.canonical_json_bytes())

    exit_code = validation_cli_main(
        [
            "--request-file",
            str(request_path),
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["gate"] == "BLOCKED"
    assert expected_reason.value in output["gate_reasons"]


def test_service_maps_unavailable_exact_read_to_blocked_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def unavailable(self: object, revision: str) -> HistoricalOhlcvImportResultV1:
        del self, revision
        return HistoricalOhlcvImportResultV1(
            HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
        )

    monkeypatch.setattr(
        capability_validation_service.HistoricalOhlcvRevisionStoreV1,
        "read_exact",
        unavailable,
    )

    report = HistoricalValidationServiceV1(tmp_path).evaluate(_request())

    assert report.gate is MarketStructureReadinessGateV1.BLOCKED
    assert (
        HistoricalValidationReasonV1.EVIDENCE_REVISION_UNAVAILABLE
        in report.gate_reasons
    )


def test_service_classifies_outer_revision_substitution_as_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def substituted(self: object, revision: str) -> HistoricalOhlcvImportResultV1:
        del self, revision
        return HistoricalOhlcvImportResultV1(
            HistoricalOhlcvImportOutcomeV1.SUCCESS,
            "f" * 64,
            {"revision_sha256": "f" * 64},
        )

    monkeypatch.setattr(
        capability_validation_service.HistoricalOhlcvRevisionStoreV1,
        "read_exact",
        substituted,
    )

    report = HistoricalValidationServiceV1(tmp_path).evaluate(_request())

    assert report.gate is MarketStructureReadinessGateV1.BLOCKED
    assert (
        HistoricalValidationReasonV1.EVIDENCE_REVISION_IDENTITY_MISMATCH
        in report.gate_reasons
    )
    assert (
        HistoricalValidationReasonV1.EVIDENCE_REVISION_UNAVAILABLE
        not in report.gate_reasons
    )


def _write_request_file(tmp_path: Path, raw: bytes) -> Path:
    path = tmp_path / "request.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


def test_cli_reports_outer_revision_substitution_as_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def substituted(self: object, revision: str) -> HistoricalOhlcvImportResultV1:
        del self, revision
        return HistoricalOhlcvImportResultV1(
            HistoricalOhlcvImportOutcomeV1.SUCCESS,
            "f" * 64,
            {"revision_sha256": "f" * 64},
        )

    monkeypatch.setattr(
        capability_validation_service.HistoricalOhlcvRevisionStoreV1,
        "read_exact",
        substituted,
    )
    request_path = _write_request_file(tmp_path, _request().canonical_json_bytes())

    exit_code = validation_cli_main(
        [
            "--request-file",
            str(request_path),
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["gate"] == "BLOCKED"
    assert (
        HistoricalValidationReasonV1.EVIDENCE_REVISION_IDENTITY_MISMATCH.value
        in output["gate_reasons"]
    )


@pytest.mark.parametrize(
    ("report_kind", "expected_exit"),
    (("approved", 0), ("blocked", 1)),
)
def test_cli_emits_canonical_report_and_truthful_exit(
    report_kind: str,
    expected_exit: int,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _request()
    report = (
        evaluate_capability_aware_historical_validation_v1(request, _evidence())
        if report_kind == "approved"
        else build_blocked_historical_validation_report_v1(request)
    )

    def evaluate(
        self: object, supplied: HistoricalValidationRequestV1
    ) -> HistoricalValidationReportV1:
        del self, supplied
        return report

    monkeypatch.setattr(
        capability_validation_service.HistoricalValidationServiceV1,
        "evaluate",
        evaluate,
    )
    request_path = _write_request_file(tmp_path, request.canonical_json_bytes())

    exit_code = validation_cli_main(
        [
            "--request-file",
            str(request_path),
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == expected_exit
    assert captured.out.encode() == report.canonical_json_bytes()
    assert captured.err == ""


def test_cli_separates_invalid_request_from_internal_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid_path = _write_request_file(tmp_path, b"{}\n")
    arguments = [
        "--request-file",
        str(invalid_path),
        "--storage-root",
        str(tmp_path),
        "--output",
        "json",
    ]

    assert validation_cli_main(arguments) == 2
    invalid = capsys.readouterr()
    assert invalid.out == ""
    assert invalid.err == "request_invalid\n"

    request_path = _write_request_file(tmp_path, _request().canonical_json_bytes())
    arguments[1] = str(request_path)

    def raise_internal(
        self: object, supplied: HistoricalValidationRequestV1
    ) -> NoReturn:
        del self, supplied
        raise RuntimeError("private")

    monkeypatch.setattr(
        capability_validation_service.HistoricalValidationServiceV1,
        "evaluate",
        raise_internal,
    )

    assert validation_cli_main(arguments) == 2
    internal = capsys.readouterr()
    assert internal.out == ""
    assert internal.err == "internal_error\n"
    assert "private" not in internal.err


def test_installed_cli_entry_point_is_declared() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text())

    assert project["project"]["scripts"]["historical-validation-gate"] == (
        "swing_trading_ai_assistant.entrypoints.historical_validation_gate:main"
    )


def test_bounds_and_temporal_order_fail_before_reduction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="historical evidence revision is invalid"):
        replace(_evidence(), cohort=())

    members = tuple(CanonicalEquityV1(f"INE{index:09d}", "NSE") for index in range(51))
    with pytest.raises(ValueError, match="historical evidence revision is invalid"):
        replace(
            _evidence(),
            cohort=members,
            bars=tuple(
                HistoricalBarKnowledgeV1(
                    member=member,
                    session=point.session,
                    known_at=point.decision_cutoff - timedelta(hours=1),
                )
                for member in members
                for point in _points()
            ),
        )

    sessions = tuple(date(2024, 1, 1) + timedelta(days=index) for index in range(367))
    with pytest.raises(ValueError, match="historical evidence revision is invalid"):
        replace(
            _evidence(),
            sessions=sessions,
            bars=tuple(
                HistoricalBarKnowledgeV1(
                    member=_MEMBER,
                    session=session,
                    known_at=_BASE - timedelta(hours=1),
                )
                for session in sessions
            ),
        )
    with pytest.raises(ValueError, match="study declaration is invalid"):
        HistoricalStudyDeclarationV1(HistoricalStudyProfileV1.OHLCV_ONLY, 0)
    with pytest.raises(ValueError, match="study declaration is invalid"):
        HistoricalStudyDeclarationV1(HistoricalStudyProfileV1.OHLCV_ONLY, 10_001)
    with pytest.raises(ValueError, match="decision regions are invalid"):
        replace(_request(), decision_points=_points()[:3])
    with pytest.raises(ValueError, match="decision regions are invalid"):
        replace(
            _request(),
            evaluated_at=_points()[-1].decision_cutoff - timedelta(seconds=1),
        )

    entries = _request().availability_ledger
    assert capability_validation.MAX_LEDGER_ENTRIES_V1 == 73_200
    with monkeypatch.context() as bounded:
        bounded.setattr(
            capability_validation, "MAX_LEDGER_ENTRIES_V1", len(entries) - 1
        )
        with pytest.raises(ValueError, match="availability ledger is invalid"):
            _request(entries=entries)

    monkeypatch.setattr(capability_validation, "MAX_REQUEST_BYTES_V1", 10)
    with pytest.raises(
        ValueError, match="historical validation request JSON is invalid"
    ):
        parse_historical_validation_request_v1(_request().canonical_json_bytes())


def test_revision_substitution_and_bar_time_mismatch_are_distinct() -> None:
    first = _points()[0]
    baseline = list(_request().availability_ledger)
    target = next(
        index
        for index, entry in enumerate(baseline)
        if entry.feature is HistoricalEvidenceFeatureV1.DAILY_OHLCV
        and entry.session == first.session
    )
    baseline[target] = replace(
        baseline[target], evidence_revision_sha256=_CONTEXT_REVISION
    )
    substitution = evaluate_capability_aware_historical_validation_v1(
        _request(entries=tuple(baseline)), _evidence()
    )
    assert HistoricalValidationReasonV1.EVIDENCE_REVISION_SUBSTITUTION in (
        _result_for_profile(substitution, HistoricalStudyProfileV1.OHLCV_ONLY).reasons
    )

    baseline[target] = replace(
        _entry(first, HistoricalEvidenceFeatureV1.DAILY_OHLCV),
        source_identity_sha256="8" * 64,
    )
    source_substitution = evaluate_capability_aware_historical_validation_v1(
        _request(entries=tuple(baseline)), _evidence()
    )
    assert HistoricalValidationReasonV1.EVIDENCE_REVISION_SUBSTITUTION in (
        _result_for_profile(
            source_substitution, HistoricalStudyProfileV1.OHLCV_ONLY
        ).reasons
    )

    baseline[target] = _entry(
        first,
        HistoricalEvidenceFeatureV1.DAILY_OHLCV,
        known_at=first.decision_cutoff - timedelta(hours=2),
    )
    mismatch = evaluate_capability_aware_historical_validation_v1(
        _request(entries=tuple(baseline)), _evidence()
    )
    assert HistoricalValidationReasonV1.BAR_KNOWN_TIME_MISMATCH in (
        _result_for_profile(mismatch, HistoricalStudyProfileV1.OHLCV_ONLY).reasons
    )


def test_combined_reasons_follow_closed_precedence() -> None:
    points = _points()
    future_known = points[0].decision_cutoff + timedelta(seconds=1)
    evidence = _evidence(temporal_status="REVISED_NON_PIT")
    evidence = replace(
        evidence,
        bars=tuple(
            replace(bar, known_at=future_known)
            if bar.session == points[0].session
            else bar
            for bar in evidence.bars
        ),
    )
    entries = list(_request().availability_ledger)

    def target(feature: HistoricalEvidenceFeatureV1, session: date) -> int:
        return next(
            index
            for index, entry in enumerate(entries)
            if entry.feature is feature and entry.session == session
        )

    entries[target(HistoricalEvidenceFeatureV1.DAILY_OHLCV, points[0].session)] = (
        _entry(
            points[0],
            HistoricalEvidenceFeatureV1.DAILY_OHLCV,
            known_at=future_known,
        )
    )
    entries[
        target(
            HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY,
            points[1].session,
        )
    ] = _entry(
        points[1],
        HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY,
        state=AvailabilityStateV1.CONFLICTED,
    )
    entries[target(HistoricalEvidenceFeatureV1.DAILY_OHLCV, points[2].session)] = (
        _entry(
            points[2],
            HistoricalEvidenceFeatureV1.DAILY_OHLCV,
            state=AvailabilityStateV1.STALE,
        )
    )
    del entries[
        target(
            HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY,
            points[3].session,
        )
    ]

    report = evaluate_capability_aware_historical_validation_v1(
        _request(entries=tuple(entries)), evidence
    )
    result = _result_for_profile(report, HistoricalStudyProfileV1.OHLCV_ONLY)
    expected = {
        HistoricalValidationReasonV1.REVISION_NOT_POINT_IN_TIME,
        HistoricalValidationReasonV1.FUTURE_KNOWN_EVIDENCE,
        HistoricalValidationReasonV1.AVAILABILITY_LEDGER_INCOMPLETE,
        HistoricalValidationReasonV1.EVIDENCE_CONFLICTED,
        HistoricalValidationReasonV1.EVIDENCE_STALE,
        HistoricalValidationReasonV1.COVERAGE_BELOW_PREDECLARED_THRESHOLD,
    }

    assert result.reasons == tuple(
        reason for reason in HistoricalValidationReasonV1 if reason in expected
    )
    assert report.gate_reasons == tuple(
        reason
        for reason in HistoricalValidationReasonV1
        if reason
        in {
            *expected,
            HistoricalValidationReasonV1.OHLCV_ONLY_NOT_QUALIFIED,
        }
    )


def test_non_pit_revision_cannot_be_available_by_ledger_assertion() -> None:
    report = evaluate_capability_aware_historical_validation_v1(
        _request(), _evidence(temporal_status="REVISED_NON_PIT")
    )
    result = _result_for_profile(report, HistoricalStudyProfileV1.OHLCV_ONLY)

    assert report.gate is MarketStructureReadinessGateV1.BLOCKED
    assert HistoricalValidationReasonV1.REVISION_NOT_POINT_IN_TIME in result.reasons
    assert result.available_cells == 4
    assert result.total_required_cells == 8


def test_raw_unavailable_cells_preserve_revision_level_reasons() -> None:
    evidence = _evidence(
        temporal_status="REVISED_NON_PIT",
        corporate_action_status="NOT_EVALUATED",
        comparability_status="NOT_ESTABLISHED",
    )
    entries = tuple(
        _entry(
            point,
            feature,
            state=(
                AvailabilityStateV1.NOT_RETAINED
                if feature
                in {
                    HistoricalEvidenceFeatureV1.DAILY_OHLCV,
                    HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY,
                }
                else AvailabilityStateV1.AVAILABLE
            ),
        )
        for point in _points()
        for feature in HistoricalEvidenceFeatureV1
    )
    report = evaluate_capability_aware_historical_validation_v1(
        _request(entries=entries), evidence
    )
    result = _result_for_profile(report, HistoricalStudyProfileV1.OHLCV_ONLY)
    expected = {
        HistoricalValidationReasonV1.REVISION_NOT_POINT_IN_TIME,
        HistoricalValidationReasonV1.COMPARABILITY_EVIDENCE_NOT_PROVEN,
        HistoricalValidationReasonV1.EVIDENCE_NOT_RETAINED,
        HistoricalValidationReasonV1.COVERAGE_BELOW_PREDECLARED_THRESHOLD,
    }

    assert result.reasons == tuple(
        reason for reason in HistoricalValidationReasonV1 if reason in expected
    )
    assert report.gate_reasons == tuple(
        reason
        for reason in HistoricalValidationReasonV1
        if reason
        in {
            *expected,
            HistoricalValidationReasonV1.OHLCV_ONLY_NOT_QUALIFIED,
        }
    )


def test_request_only_digest_cannot_prove_unverified_comparability() -> None:
    evidence = _evidence(
        corporate_action_status="NOT_EVALUATED",
        comparability_status="NOT_ESTABLISHED",
    )

    report = evaluate_capability_aware_historical_validation_v1(_request(), evidence)
    result = _result_for_profile(report, HistoricalStudyProfileV1.OHLCV_ONLY)

    assert report.gate is MarketStructureReadinessGateV1.BLOCKED
    assert (
        HistoricalValidationReasonV1.COMPARABILITY_EVIDENCE_NOT_PROVEN in result.reasons
    )
    assert result.available_cells == 4


@pytest.mark.parametrize(
    "field",
    (
        "source_identity_sha256",
        "classification_receipt_sha256",
        "evidence_revision_sha256",
        "published_at",
        "known_at",
    ),
)
@pytest.mark.parametrize(
    "state",
    (AvailabilityStateV1.AVAILABLE, AvailabilityStateV1.STALE),
)
def test_recomputed_request_cannot_forge_bound_comparability_provenance(
    field: str,
    state: AvailabilityStateV1,
) -> None:
    first = _points()[0]
    entries = list(_request().availability_ledger)
    target = next(
        index
        for index, entry in enumerate(entries)
        if entry.session == first.session
        and entry.feature is HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY
    )
    replacement_value: str | datetime
    if field == "published_at":
        replacement_value = first.decision_cutoff - timedelta(hours=3)
    elif field == "known_at":
        replacement_value = first.decision_cutoff - timedelta(minutes=30)
    else:
        replacement_value = "f" * 64
    entries[target] = replace(
        entries[target],
        state=state,
        **{field: replacement_value},
    )

    thresholds = (
        {HistoricalStudyProfileV1.OHLCV_ONLY: 8_000}
        if state is AvailabilityStateV1.STALE
        else None
    )
    report = evaluate_capability_aware_historical_validation_v1(
        _request(entries=tuple(entries), thresholds=thresholds), _evidence()
    )
    result = _result_for_profile(report, HistoricalStudyProfileV1.OHLCV_ONLY)

    assert report.gate is MarketStructureReadinessGateV1.BLOCKED
    assert result.outcome is ProfileQualificationOutcomeV1.INSUFFICIENT_EVIDENCE
    assert HistoricalValidationReasonV1.EVIDENCE_REVISION_SUBSTITUTION in result.reasons
    assert result.available_cells == 7


def test_raw_revision_cannot_prove_comparability_with_its_own_identity() -> None:
    evidence = _evidence(
        corporate_action_status="NOT_EVALUATED",
        comparability_status="NOT_ESTABLISHED",
    )
    entries = tuple(
        (
            replace(entry, evidence_revision_sha256=evidence.revision_sha256)
            if entry.feature
            is HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY
            else entry
        )
        for entry in _request().availability_ledger
    )

    report = evaluate_capability_aware_historical_validation_v1(
        _request(entries=entries), evidence
    )
    result = _result_for_profile(report, HistoricalStudyProfileV1.OHLCV_ONLY)

    assert report.gate is MarketStructureReadinessGateV1.BLOCKED
    assert result.outcome is ProfileQualificationOutcomeV1.INSUFFICIENT_EVIDENCE
    assert (
        HistoricalValidationReasonV1.COMPARABILITY_EVIDENCE_NOT_PROVEN in result.reasons
    )


def test_tampered_ledger_identity_and_publication_order_are_rejected() -> None:
    value = json.loads(_request().canonical_json_bytes())
    value["availability_ledger"][0]["entry_identity_sha256"] = "f" * 64
    tampered = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(
        ValueError, match="historical validation request JSON is invalid"
    ):
        parse_historical_validation_request_v1(tampered)

    first = _points()[0]
    with pytest.raises(ValueError, match="availability entry is invalid"):
        HistoricalAvailabilityEntryV1(
            feature=HistoricalEvidenceFeatureV1.DAILY_OHLCV,
            member=_MEMBER,
            session=first.session,
            interval="1d",
            decision_cutoff=first.decision_cutoff,
            state=AvailabilityStateV1.AVAILABLE,
            source_identity_sha256=_SOURCE,
            classification_receipt_sha256=_RECEIPT,
            evidence_revision_sha256=_REVISION,
            published_at=first.decision_cutoff - timedelta(hours=1),
            known_at=first.decision_cutoff - timedelta(hours=2),
        )


def test_public_report_contains_no_member_or_source_payload() -> None:
    raw = evaluate_capability_aware_historical_validation_v1(
        _request(), _evidence()
    ).canonical_json_bytes()

    assert _MEMBER.isin.encode() not in raw
    assert b"RELIANCE" not in raw
    assert b"/Users/" not in raw
    assert b"provider_mapping" not in raw


def test_cli_rejects_world_readable_and_symlinked_request_before_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    called = False

    def evaluate(self: object, supplied: object) -> object:
        del self, supplied
        nonlocal called
        called = True
        raise AssertionError

    monkeypatch.setattr(
        capability_validation_service.HistoricalValidationServiceV1,
        "evaluate",
        evaluate,
    )
    world_readable = tmp_path / "world.json"
    world_readable.write_bytes(_request().canonical_json_bytes())
    world_readable.chmod(0o644)
    arguments = [
        "--request-file",
        str(world_readable),
        "--storage-root",
        str(tmp_path),
        "--output",
        "json",
    ]
    assert validation_cli_main(arguments) == 2
    assert capsys.readouterr().err == "request_invalid\n"

    target = _write_request_file(tmp_path, _request().canonical_json_bytes())
    link = tmp_path / "request-link.json"
    link.symlink_to(target)
    arguments[1] = str(link)
    assert validation_cli_main(arguments) == 2
    assert capsys.readouterr().err == "request_invalid\n"
    target.write_bytes(
        replace(
            _request(), runtime_code_identity_sha256="f" * 64
        ).canonical_json_bytes()
    )
    arguments[1] = str(target)
    assert validation_cli_main(arguments) == 2
    assert capsys.readouterr().err == "request_invalid\n"
    assert not called


def test_cli_rejects_symlinked_ancestors_and_noncanonical_path_segments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    called = False

    def evaluate(self: object, supplied: object) -> object:
        del self, supplied
        nonlocal called
        called = True
        raise AssertionError

    monkeypatch.setattr(
        capability_validation_service.HistoricalValidationServiceV1,
        "evaluate",
        evaluate,
    )
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    target = _write_request_file(real_parent, _request().canonical_json_bytes())
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    invalid_paths = (
        f"{linked_parent}/{target.name}",
        f"{real_parent}/../{real_parent.name}/{target.name}",
        f"{real_parent}//{target.name}",
        f"{real_parent}/./{target.name}",
    )

    for invalid_path in invalid_paths:
        assert (
            validation_cli_main(
                [
                    "--request-file",
                    invalid_path,
                    "--storage-root",
                    str(tmp_path),
                    "--output",
                    "json",
                ]
            )
            == 2
        )
        assert capsys.readouterr().err == "request_invalid\n"
    assert not called


def test_service_rejects_success_payload_with_invalid_revision_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def invalid_revision(self: object, revision: str) -> HistoricalOhlcvImportResultV1:
        del self, revision
        return HistoricalOhlcvImportResultV1(
            HistoricalOhlcvImportOutcomeV1.SUCCESS,
            _REVISION,
            {"revision_sha256": _REVISION},
        )

    monkeypatch.setattr(
        capability_validation_service.HistoricalOhlcvRevisionStoreV1,
        "read_exact",
        invalid_revision,
    )

    report = HistoricalValidationServiceV1(tmp_path).evaluate(_request())

    assert report.gate is MarketStructureReadinessGateV1.BLOCKED
    assert (
        HistoricalValidationReasonV1.EVIDENCE_REVISION_IDENTITY_MISMATCH
        in report.gate_reasons
    )


def test_runtime_source_substitution_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = capability_validation.read_runtime_source

    def substituted(root: Path, relative: str) -> bytes:
        if relative.endswith("/capability_validation.py"):
            return b"substituted"
        return original(root, relative)

    monkeypatch.setattr(capability_validation, "read_runtime_source", substituted)

    with pytest.raises(
        HistoricalValidationRuntimeIdentityError,
        match="historical validation runtime identity invalid",
    ):
        capability_validation._loaded_runtime_code_identity()  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize(
    ("relative_path", "raises"),
    (
        ("historical_evaluation/capability_validation_service.py", False),
        ("historical_evaluation/__init__.py", True),
        ("__init__.py", False),
        ("entrypoints/__init__.py", False),
        ("historical_evaluation/__init__.py", False),
        ("market_data/__init__.py", False),
    ),
)
def test_installed_entrypoint_sanitizes_preimport_or_identity_failure(
    relative_path: str,
    raises: bool,
    tmp_path: Path,
) -> None:
    package_root = Path(capability_validation.__file__).resolve().parent.parent
    isolated_site = tmp_path / "site"
    isolated_package = isolated_site / package_root.name
    shutil.copytree(package_root, isolated_package)
    target = isolated_package.joinpath(*relative_path.split("/"))
    if raises:
        target.write_bytes(
            b"raise RuntimeError('private initializer fault')\n" + target.read_bytes()
        )
    else:
        target.write_bytes(target.read_bytes() + b"\n# substituted\n")
    request_path = _write_request_file(tmp_path, _request().canonical_json_bytes())
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(isolated_site)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    completed = subprocess.run(  # noqa: S603 - trusted isolated interpreter
        [
            sys.executable,
            "-c",
            (
                "from swing_trading_ai_assistant.entrypoints."
                "historical_validation_gate import main;"
                "raise SystemExit(main())"
            ),
            "--request-file",
            str(request_path),
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
    )

    assert completed.returncode == 2
    assert completed.stdout == b""
    assert completed.stderr == b"internal_error\n"


def test_request_fifo_is_rejected_without_blocking(tmp_path: Path) -> None:
    package_root = Path(capability_validation.__file__).resolve().parent.parent
    request_fifo = tmp_path / "request.fifo"
    os.mkfifo(request_fifo, 0o600)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(package_root.parent)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    completed = subprocess.run(  # noqa: S603 - trusted isolated interpreter
        [
            sys.executable,
            "-c",
            (
                "from swing_trading_ai_assistant.historical_evaluation."
                "capability_validation_cli import main;"
                "raise SystemExit(main())"
            ),
            "--request-file",
            str(request_fifo),
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        timeout=2,
    )

    assert completed.returncode == 2
    assert completed.stdout == b""
    assert completed.stderr == b"request_invalid\n"
