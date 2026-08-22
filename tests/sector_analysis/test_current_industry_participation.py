"""RED contract tests for aggregate-only current Industry Participation V1."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import socket
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, NoReturn

import pytest

from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

_COHORT = "a" * 64


def _api() -> Any:
    return importlib.import_module(
        "swing_trading_ai_assistant.sector_analysis.current_industry_participation"
    )


def _test_module(relative: str, name: str) -> ModuleType:
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    path = Path(__file__).parents[1] / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _classification_test_module() -> ModuleType:
    return _test_module(
        "market_data/test_current_industry_classification.py",
        "test_current_industry_classification",
    )


def _v2_test_module() -> ModuleType:
    return _test_module(
        "market_regime/test_current_supplied_cohort_v2.py",
        "test_current_supplied_cohort_v2",
    )


def _private_lease(tmp_path: Path) -> StorageRootLease:
    if not tmp_path.exists():
        tmp_path.mkdir(mode=0o700)
    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire_private_empty(tmp_path)
    assert acquired.lease is not None
    return acquired.lease


def _retained_classification(
    tmp_path: Path,
    *,
    industries: tuple[str, str, str] = ("Banking", "Pharma", "Technology"),
    row_order: tuple[int, ...] | None = None,
) -> tuple[Any, Any, Any, Any, Any]:
    classification_test = _classification_test_module()
    classification_api = classification_test._api()
    v2 = _v2_test_module()
    raw_v1_report, raw_private_grid = v2._raw_evidence()
    adjusted_handoff = v2._handoff(raw_v1_report, raw_private_grid)
    screen = v2._screen(raw_v1_report, raw_private_grid)
    artifact = classification_test._artifact(
        industry_at=dict(enumerate(industries)),
        symbol_at={index: member.symbol for index, member in enumerate(v2._members())},
        isin_at={index: member.isin for index, member in enumerate(v2._members())},
        row_order=row_order,
    )
    parsed = classification_test._parse(classification_api, artifact)
    members = tuple(
        classification_api.CurrentIndustryCohortMemberV1(
            isin=member.isin, exchange="NSE", effective_symbol=member.symbol
        )
        for member in v2._members()
    )
    snapshot = classification_api.project_current_supplied_cohort_industry_v1(
        parsed,
        _COHORT,
        members,
    )
    lease = _private_lease(tmp_path)
    archive = classification_api.FileCurrentIndustryArchiveV1(tmp_path)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            classification_api,
            "_trusted_utc_now",
            lambda: raw_v1_report.decision_cutoff,
        )
        try:
            retained = archive.archive_exact(
                classification_test._input(classification_api, artifact),
                artifact,
                snapshot,
                lease,
            )
        finally:
            lease.close()
    return raw_v1_report, raw_private_grid, screen, adjusted_handoff, retained


def _reduce(
    tmp_path: Path,
    *,
    industries: tuple[str, str, str] = ("Banking", "Pharma", "Technology"),
    row_order: tuple[int, ...] | None = None,
    **overrides: object,
) -> Any:
    api = _api()
    values = _retained_classification(
        tmp_path, industries=industries, row_order=row_order
    )
    arguments: dict[str, Any] = dict(
        zip(
            (
                "raw_v1_report",
                "raw_private_grid",
                "retained_screen",
                "adjusted_handoff",
                "classification",
            ),
            values,
            strict=True,
        )
    )
    arguments.update(overrides)
    return api.reduce_current_industry_participation_v1(**arguments)


def _classification_failure(reason: str) -> Any:
    classification_api = _classification_test_module()._api()
    state = (
        "MALFORMED_EVIDENCE"
        if reason
        in {
            "CLASSIFICATION_ARTIFACT_MALFORMED",
            "CLASSIFICATION_AMBIGUOUS",
            "CLASSIFICATION_CONFLICTING",
            "COHORT_BINDING_MISMATCH",
            "MEMBER_IDENTITY_MISMATCH",
        }
        else (
            "UNSUPPORTED_CAPABILITY"
            if reason
            in {
                "CLASSIFICATION_SOURCE_UNSUPPORTED",
                "CLASSIFICATION_TIER_UNSUPPORTED",
                "CLASSIFICATION_MEMBER_UNSUPPORTED",
            }
            else "INSUFFICIENT_EVIDENCE"
        )
    )
    return classification_api.CurrentIndustryClassificationFailureV1(
        evidence_state=state,
        reasons=(reason,),
    )


def _assert_non_observed(result: Any, state: str, reasons: tuple[str, ...]) -> None:
    assert result.evidence_state == state
    assert result.reasons == reasons
    assert result.industries is None
    encoded = result.canonical_json_bytes().decode()
    for secret in ("INE002A01018", "M001", "NSE", "ADVANCE", "Company 000", "Banking"):
        assert secret not in encoded


def test_reduces_one_same_pass_observed_cohort_to_deterministic_industry_counts(
    tmp_path: Path,
) -> None:
    result = _reduce(tmp_path)

    assert result.evidence_state == "OBSERVED"
    assert (
        result.contract_version == "current-supplied-cohort-industry-participation@v1"
    )
    assert result.classification_tier == "INDUSTRY"
    assert (
        result.source_url
        == "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"
    )
    assert result.source_authority == "NSE_INDICES"
    assert result.known_at == result.decision_cutoff
    assert (
        result.publisher_published_at,
        result.publisher_effective_from,
        result.publisher_effective_through,
        result.publisher_revision,
    ) == (None, None, None, None)
    assert tuple(row.industry for row in result.industries) == (
        "Banking",
        "Pharma",
        "Technology",
    )
    assert all(
        row.member_count == row.advances + row.declines + row.unchanged
        for row in result.industries
    )
    assert sum(row.member_count for row in result.industries) == result.cohort_size == 3
    assert (
        sum(row.advances for row in result.industries)
        == result.market_regime_advances
        == 1
    )
    assert (
        sum(row.declines for row in result.industries)
        == result.market_regime_declines
        == 1
    )
    assert (
        sum(row.unchanged for row in result.industries)
        == result.market_regime_unchanged
        == 1
    )
    assert result.reasons == ()
    encoded = result.canonical_json_bytes().decode()
    for secret in (
        "INE002A01018",
        "M001",
        "ADVANCE",
        "Company 000",
        str(tmp_path),
    ):
        assert secret not in encoded


def test_report_identity_freezes_complete_observed_schema_except_itself(
    tmp_path: Path,
) -> None:
    result = _reduce(tmp_path)

    assert (
        result.report_identity_sha256
        == hashlib.sha256(
            result.canonical_json_bytes(include_identity=False)
        ).hexdigest()
    )
    payload = result.canonical_json_bytes().decode()
    assert "archive_receipt_identity_sha256" in payload
    assert "snapshot_runtime_code_identity_sha256" in payload
    assert "classification_schema_identity_sha256" in payload


def test_observed_report_is_sealed_and_canonically_includes_empty_reasons(
    tmp_path: Path,
) -> None:
    api = _api()
    result = _reduce(tmp_path)
    values = {
        name: getattr(result, name)
        for name in api.CurrentIndustryParticipationReportV1.__dataclass_fields__
    }

    assert b'"reasons":[]' in result.canonical_json_bytes()
    with pytest.raises(TypeError, match="constructor unavailable"):
        api.CurrentIndustryParticipationReportV1(**values)


@pytest.mark.parametrize("size", (1, 5, 50))
def test_aggregate_counts_reconcile_for_supported_cohort_bounds(
    tmp_path: Path, size: int
) -> None:
    api = _api()
    classification_test = _classification_test_module()
    classification_api = classification_test._api()
    artifact = classification_test._artifact()
    snapshot = classification_api.project_current_supplied_cohort_industry_v1(
        classification_test._parse(classification_api, artifact),
        "c" * 64,
        classification_test._members(classification_api, size),
    )
    lease = _private_lease(tmp_path)
    archive = classification_api.FileCurrentIndustryArchiveV1(tmp_path)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            classification_api, "_trusted_utc_now", lambda: classification_test._CUTOFF
        )
        try:
            retained = archive.archive_exact(
                classification_test._input(classification_api, artifact),
                artifact,
                snapshot,
                lease,
            )
        finally:
            lease.close()
    directions = ("ADVANCE", "DECLINE", "UNCHANGED")
    handoff = SimpleNamespace(
        members=tuple(
            SimpleNamespace(
                isin=row.isin,
                exchange=row.exchange,
                effective_symbol=row.effective_symbol,
                direction=directions[index % 3],
            )
            for index, row in enumerate(retained._private_rows)
        )
    )
    report = SimpleNamespace(
        cohort_size=size,
        advances=sum(member.direction == "ADVANCE" for member in handoff.members),
        declines=sum(member.direction == "DECLINE" for member in handoff.members),
        unchanged=sum(member.direction == "UNCHANGED" for member in handoff.members),
    )

    industries, failure = api._aggregate_industries(retained, handoff, report)

    assert failure is None
    assert sum(row.member_count for row in industries) == size
    assert sum(row.advances for row in industries) == report.advances
    assert sum(row.declines for row in industries) == report.declines
    assert sum(row.unchanged for row in industries) == report.unchanged


def test_equivalent_industry_input_permutations_preserve_canonical_aggregate_rows(
    tmp_path: Path,
) -> None:
    first = _reduce(tmp_path / "first")
    second = _reduce(tmp_path / "second", row_order=tuple(reversed(range(100))))

    assert first.evidence_state == second.evidence_state == "OBSERVED"
    assert tuple(
        (row.industry, row.member_count, row.advances, row.declines, row.unchanged)
        for row in first.industries
    ) == tuple(
        (row.industry, row.member_count, row.advances, row.declines, row.unchanged)
        for row in second.industries
    )


@pytest.mark.parametrize(
    ("mutator", "state", "reasons"),
    (
        (
            "market-regime-unavailable",
            "INSUFFICIENT_EVIDENCE",
            ("MARKET_REGIME_UNAVAILABLE",),
        ),
        (
            "classification-artifact-missing",
            "INSUFFICIENT_EVIDENCE",
            ("CLASSIFICATION_ARTIFACT_MISSING",),
        ),
        (
            "classification-artifact-malformed",
            "MALFORMED_EVIDENCE",
            ("CLASSIFICATION_ARTIFACT_MALFORMED",),
        ),
        (
            "classification-source-unsupported",
            "UNSUPPORTED_CAPABILITY",
            ("CLASSIFICATION_SOURCE_UNSUPPORTED",),
        ),
        (
            "classification-tier-unsupported",
            "UNSUPPORTED_CAPABILITY",
            ("CLASSIFICATION_TIER_UNSUPPORTED",),
        ),
        (
            "classification-ambiguous",
            "MALFORMED_EVIDENCE",
            ("CLASSIFICATION_AMBIGUOUS",),
        ),
        (
            "classification-conflicting",
            "MALFORMED_EVIDENCE",
            ("CLASSIFICATION_CONFLICTING",),
        ),
        ("cohort-binding-mismatch", "MALFORMED_EVIDENCE", ("COHORT_BINDING_MISMATCH",)),
        (
            "member-identity-mismatch",
            "MALFORMED_EVIDENCE",
            ("MEMBER_IDENTITY_MISMATCH",),
        ),
        (
            "classification-member-unsupported",
            "UNSUPPORTED_CAPABILITY",
            ("CLASSIFICATION_MEMBER_UNSUPPORTED",),
        ),
        (
            "classification-future-known",
            "INSUFFICIENT_EVIDENCE",
            ("CLASSIFICATION_FUTURE_KNOWN",),
        ),
        (
            "classification-session-stale",
            "INSUFFICIENT_EVIDENCE",
            ("CLASSIFICATION_SESSION_STALE",),
        ),
        (
            "classification-archive-failed",
            "INSUFFICIENT_EVIDENCE",
            ("CLASSIFICATION_ARCHIVE_FAILED",),
        ),
    ),
)
def test_every_admitted_classification_boundary_is_a_whole_redacted_result(
    tmp_path: Path, mutator: str, state: str, reasons: tuple[str, ...]
) -> None:
    api = _api()
    raw_v1_report, raw_private_grid, screen, adjusted_handoff, retained = (
        _retained_classification(tmp_path)
    )
    classification = (
        retained
        if mutator == "market-regime-unavailable"
        else _classification_failure(reasons[0])
    )
    if mutator == "market-regime-unavailable":
        adjusted_handoff = replace(adjusted_handoff, temporal_label="HISTORICAL")
    result = api.reduce_current_industry_participation_v1(
        raw_v1_report,
        raw_private_grid,
        screen,
        adjusted_handoff,
        classification,
    )
    _assert_non_observed(result, state, reasons)


def test_multifault_precedence_is_malformed_then_unsupported_then_insufficient(
    tmp_path: Path,
) -> None:
    api = _api()
    raw_v1_report, raw_private_grid, screen, adjusted_handoff, _retained = (
        _retained_classification(tmp_path)
    )
    classification_api = _classification_test_module()._api()
    classification = classification_api.CurrentIndustryClassificationFailureV1(
        evidence_state="MALFORMED_EVIDENCE",
        reasons=(
            "CLASSIFICATION_ARTIFACT_MALFORMED",
            "CLASSIFICATION_MEMBER_UNSUPPORTED",
            "CLASSIFICATION_ARCHIVE_FAILED",
        ),
    )
    result = api.reduce_current_industry_participation_v1(
        raw_v1_report, raw_private_grid, screen, adjusted_handoff, classification
    )
    _assert_non_observed(
        result,
        "MALFORMED_EVIDENCE",
        (
            "CLASSIFICATION_ARTIFACT_MALFORMED",
            "CLASSIFICATION_MEMBER_UNSUPPORTED",
            "CLASSIFICATION_ARCHIVE_FAILED",
        ),
    )


def test_rejects_spliced_snapshot_binding_without_partial_rows(
    tmp_path: Path,
) -> None:
    raw_v1_report, raw_private_grid, screen, adjusted_handoff, retained = (
        _retained_classification(tmp_path)
    )
    object.__setattr__(retained, "cohort_identity_sha256", "f" * 64)
    result = _reduce(
        tmp_path / "other",
        raw_v1_report=raw_v1_report,
        raw_private_grid=raw_private_grid,
        retained_screen=screen,
        adjusted_handoff=adjusted_handoff,
        classification=retained,
    )
    _assert_non_observed(result, "MALFORMED_EVIDENCE", ("COHORT_BINDING_MISMATCH",))


def test_reducer_performs_no_network_filesystem_clock_or_public_handoff_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    raw_v1_report, raw_private_grid, screen, adjusted_handoff, retained = (
        _retained_classification(tmp_path)
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("reducer performed forbidden I/O")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(
        api,
        "evaluate_current_supplied_cohort_market_regime_v2",
        forbidden,
        raising=False,
    )
    result = api.reduce_current_industry_participation_v1(
        raw_v1_report, raw_private_grid, screen, adjusted_handoff, retained
    )
    assert result.evidence_state == "OBSERVED"


def test_reducer_merges_independent_market_and_classification_failures(
    tmp_path: Path,
) -> None:
    api = _api()
    raw_v1_report, raw_private_grid, screen, adjusted_handoff, _retained = (
        _retained_classification(tmp_path)
    )
    classification = _classification_failure("CLASSIFICATION_ARCHIVE_FAILED")
    unavailable = replace(adjusted_handoff, temporal_label="HISTORICAL")

    result = api.reduce_current_industry_participation_v1(
        raw_v1_report, raw_private_grid, screen, unavailable, classification
    )

    _assert_non_observed(
        result,
        "INSUFFICIENT_EVIDENCE",
        ("MARKET_REGIME_UNAVAILABLE", "CLASSIFICATION_ARCHIVE_FAILED"),
    )


def test_reducer_rejects_spliced_retention_receipt_and_private_rows(
    tmp_path: Path,
) -> None:
    raw_v1_report, raw_private_grid, screen, adjusted_handoff, retained = (
        _retained_classification(tmp_path)
    )
    object.__setattr__(retained, "archive_receipt_identity_sha256", "f" * 64)

    result = _reduce(
        tmp_path / "receipt",
        raw_v1_report=raw_v1_report,
        raw_private_grid=raw_private_grid,
        retained_screen=screen,
        adjusted_handoff=adjusted_handoff,
        classification=retained,
    )

    _assert_non_observed(result, "MALFORMED_EVIDENCE", ("COHORT_BINDING_MISMATCH",))


def test_reducer_uses_precomputed_runtime_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    raw_v1_report, raw_private_grid, screen, adjusted_handoff, retained = (
        _retained_classification(tmp_path)
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("reducer read runtime source")

    monkeypatch.setattr(
        api, "current_industry_participation_runtime_code_identity_v1", forbidden
    )
    result = api.reduce_current_industry_participation_v1(
        raw_v1_report, raw_private_grid, screen, adjusted_handoff, retained
    )

    assert result.evidence_state == "OBSERVED"


def test_frozen_v1_public_sector_and_market_evaluators_keep_their_existing_behavior() -> (
    None
):
    market_v1 = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort"
    )
    sector_v1 = importlib.import_module(
        "swing_trading_ai_assistant.sector_analysis.participation"
    )
    assert callable(market_v1.CurrentSuppliedCohortMarketRegimeReportV1)
    assert callable(sector_v1.reduce_sector_participation_v1)


def test_reducer_merges_retained_temporal_and_cohort_faults_without_handoff(
    tmp_path: Path,
) -> None:
    api = _api()
    raw_v1_report, raw_private_grid, screen, adjusted_handoff, retained = (
        _retained_classification(tmp_path)
    )
    classification_api = _classification_test_module()._api()
    insufficient_screen = _v2_test_module()._screen(
        raw_v1_report, raw_private_grid, state="action"
    )
    known_at = retained.known_at + timedelta(days=1)
    snapshot = classification_api._snapshot_with_identity(
        classification_api._snapshot(
            schema_identity_sha256=retained.schema_identity_sha256,
            evidence_state="PROJECTED",
            runtime_code_identity_sha256=retained.snapshot_runtime_code_identity_sha256,
            input_identity_sha256=retained.input_identity_sha256,
            artifact_sha256=retained.artifact_sha256,
            artifact_revision=retained.artifact_revision,
            cohort_identity_sha256="f" * 64,
            cohort_size=retained.cohort_size,
            private_rows=retained._private_rows,
            snapshot_identity_sha256="",
        )
    )
    archive_identity = classification_api._identity(
        {
            "raw_artifact_sha256": retained.artifact_sha256,
            "snapshot_identity_sha256": snapshot.snapshot_identity_sha256,
        }
    )
    receipt = classification_api._identity(
        {
            "archive_identity_sha256": archive_identity,
            "artifact_sha256": retained.artifact_sha256,
            "input_identity_sha256": retained.input_identity_sha256,
            "known_at": classification_api._instant(known_at),
            "snapshot_identity_sha256": snapshot.snapshot_identity_sha256,
        }
    )
    values = {
        name: getattr(retained, name)
        for name in retained.__dataclass_fields__
        if name not in {"_seal", "retained_identity_sha256"}
    }
    values.update(
        cohort_identity_sha256=snapshot.cohort_identity_sha256,
        snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        archive_identity_sha256=archive_identity,
        archive_receipt_identity_sha256=receipt,
        known_at=known_at,
    )
    faulted_retained = classification_api._retained_with_identity(**values)
    report, handoff = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v2"
    )._evaluate_current_supplied_cohort_market_regime_with_handoff_v2(
        raw_v1_report, raw_private_grid, insufficient_screen, adjusted_handoff
    )
    assert report.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert handoff is None

    result = api.reduce_current_industry_participation_v1(
        raw_v1_report,
        raw_private_grid,
        insufficient_screen,
        adjusted_handoff,
        faulted_retained,
    )

    _assert_non_observed(
        result,
        "MALFORMED_EVIDENCE",
        (
            "MARKET_REGIME_UNAVAILABLE",
            "COHORT_BINDING_MISMATCH",
            "CLASSIFICATION_FUTURE_KNOWN",
            "CLASSIFICATION_SESSION_STALE",
        ),
    )


@pytest.mark.parametrize(
    "argument_name",
    (
        "raw_v1_report",
        "raw_private_grid",
        "retained_screen",
        "adjusted_handoff",
        "classification",
    ),
)
def test_reducer_rejects_wrong_top_level_types_before_market_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argument_name: str
) -> None:
    api = _api()
    values = dict(
        zip(
            (
                "raw_v1_report",
                "raw_private_grid",
                "retained_screen",
                "adjusted_handoff",
                "classification",
            ),
            _retained_classification(tmp_path),
            strict=True,
        )
    )
    values[argument_name] = object()

    def forbidden(*_: object) -> NoReturn:
        raise AssertionError("market evaluation must not run")

    monkeypatch.setattr(
        api,
        "_evaluate_current_supplied_cohort_market_regime_with_handoff_v2",
        forbidden,
    )

    with pytest.raises(TypeError, match="industry participation input invalid"):
        api.reduce_current_industry_participation_v1(**values)
