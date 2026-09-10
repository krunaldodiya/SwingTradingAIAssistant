# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false, reportOperatorIssue=false, reportOptionalMemberAccess=false, reportOptionalOperand=false, reportReturnType=false
"""RED contract tests for Plan27 aggregate-only Industry Participation V4."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import socket
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn

import pytest

from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

_PRIVATE_CONTEXTS: dict[int, Any] = {}


def _api() -> Any:
    return importlib.import_module(
        "swing_trading_ai_assistant.sector_analysis.current_industry_participation_v4"
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


def _v4_test_module() -> ModuleType:
    return _test_module(
        "market_regime/test_current_supplied_cohort_v4.py",
        "test_current_supplied_cohort_v4",
    )


def _private_lease(tmp_path: Path) -> StorageRootLease:
    tmp_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire_private_empty(tmp_path)
    assert acquired.lease is not None
    return acquired.lease


def _retained_context(tmp_path: Path) -> Any:
    """Capture the default real V4 composition after archive validation."""
    return _retained_context_for_directions(tmp_path, None)


def _retained_context_for_directions(
    tmp_path: Path, directions: tuple[str, ...] | None
) -> tuple[Any, Any]:
    tmp_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    v4_test = _v4_test_module()
    v4_api = v4_test._v4()
    captured: list[tuple[Any, Any]] = []
    original = v4_api.FileCurrentSamePassMarketContextArchiveV1.archive_exact

    def capture(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        if type(result) is v4_api.RetainedCurrentSamePassMarketContextV4:
            captured.append((result, args[1].context_object))
        return result

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            v4_api.FileCurrentSamePassMarketContextArchiveV1, "archive_exact", capture
        )
        kwargs = (
            {}
            if directions is None
            else {
                "raw_directions": directions,
                "adjusted_directions": directions,
                "exercise_archive_contracts": False,
            }
        )
        v4_test.test_outer_composition_retains_real_context_and_archive_files(
            tmp_path, monkeypatch, **kwargs
        )
    assert captured
    return captured[0]


def _retained_classification(
    tmp_path: Path,
    context: Any,
    private_context: Any,
    *,
    industries: tuple[str, ...] = ("Technology",),
    row_order: tuple[int, ...] | None = None,
    known_at: datetime | None = None,
    legacy: bool = False,
) -> Any:
    classification_test = _classification_test_module()
    classification_api = classification_test._api()
    members = private_context.request.members
    report = context.market_regime_report
    artifact = classification_test._artifact(
        industry_at=dict(enumerate(industries)),
        symbol_at={
            index: member.effective_symbol for index, member in enumerate(members)
        },
        isin_at={index: member.isin for index, member in enumerate(members)},
        row_order=row_order,
    )
    classification_input = (
        classification_test._legacy_input(classification_api, artifact)
        if legacy
        else classification_test._input(classification_api, artifact)
    )
    parsed = classification_api.parse_current_industry_artifact_v1(
        classification_input, artifact
    )
    cohort = tuple(
        classification_api.CurrentIndustryCohortMemberV1(
            isin=member.isin,
            exchange="NSE",
            effective_symbol=member.effective_symbol,
        )
        for member in members
    )
    snapshot = classification_api.project_current_supplied_cohort_industry_v1(
        parsed,
        report.canonical_cohort_identity_sha256,
        cohort,
    )
    lease = _private_lease(tmp_path)
    archive = classification_api.FileCurrentIndustryArchiveV1(tmp_path)
    if known_at is None:
        known_at = report.decision_cutoff

    sampled_at = known_at - timedelta(seconds=30)

    def marker_filesystem_mtime_ns(*_args: object) -> int:
        return int(known_at.timestamp()) * 1_000_000_000

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            classification_api,
            "_trusted_utc_now",
            lambda: sampled_at,
        )
        monkeypatch.setattr(
            classification_api,
            "_marker_filesystem_mtime_ns",
            marker_filesystem_mtime_ns,
        )
        try:
            return archive.archive_exact(
                classification_input,
                artifact,
                snapshot,
                lease,
            )
        finally:
            lease.close()


def _inputs(tmp_path: Path, **context_kwargs: object) -> tuple[Any, Any]:
    if context_kwargs:
        raise ValueError("the real V4 integration fixture is observed-only")
    context, private_context = _retained_context(tmp_path / "context")
    _PRIVATE_CONTEXTS[id(context)] = private_context
    classification = _retained_classification(
        tmp_path / "classification", context, private_context
    )
    return context, classification


def _v4_request(context: Any) -> Any:
    return _PRIVATE_CONTEXTS[id(context)].request


def _v4_ledger_known_at(context: Any, position: int) -> Any:
    return _PRIVATE_CONTEXTS[id(context)].component_ledger[position].known_at


def _classification_failure(reason: str) -> Any:
    classification_api = _classification_test_module()._api()
    malformed = {
        "CLASSIFICATION_ARTIFACT_MALFORMED",
        "CLASSIFICATION_AMBIGUOUS",
        "CLASSIFICATION_CONFLICTING",
        "COHORT_BINDING_MISMATCH",
        "MEMBER_IDENTITY_MISMATCH",
    }
    unsupported = {
        "CLASSIFICATION_SOURCE_UNSUPPORTED",
        "CLASSIFICATION_TIER_UNSUPPORTED",
        "CLASSIFICATION_MEMBER_UNSUPPORTED",
    }
    state = (
        "MALFORMED_EVIDENCE"
        if reason in malformed
        else "UNSUPPORTED_CAPABILITY"
        if reason in unsupported
        else "INSUFFICIENT_EVIDENCE"
    )
    return classification_api.CurrentIndustryClassificationFailureV1(
        evidence_state=state,
        reasons=(reason,),
    )


def _assert_failure(result: Any, state: str, reasons: tuple[str, ...]) -> None:
    assert result.evidence_state == state
    assert result.reasons == reasons
    assert result.industries is None
    encoded = result.canonical_json_bytes().decode()
    for private_value in ("INE002A01018", "M001", "NSE", "ADVANCE", "Banking"):
        assert private_value not in encoded


def test_observed_v4_rows_are_aggregate_only_sorted_reconciled_and_identified(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)
    result = api.reduce_current_industry_participation_v4(context, classification)
    regime = context.market_regime_report

    assert (
        result.contract_version == "current-supplied-cohort-industry-participation@v4"
    )
    assert result.evidence_state == "OBSERVED"
    assert result.classification_tier == "INDUSTRY"
    assert (
        tuple(row.industry for row in result.industries)
        == tuple(sorted(row.industry for row in result.industries))
        == ("Technology",)
    )
    assert all(
        row.member_count == row.advances + row.declines + row.unchanged
        for row in result.industries
    )
    assert sum(row.member_count for row in result.industries) == result.cohort_size
    assert sum(row.advances for row in result.industries) == regime.advances
    assert sum(row.declines for row in result.industries) == regime.declines
    assert sum(row.unchanged for row in result.industries) == regime.unchanged
    assert (
        result.report_identity_sha256
        == hashlib.sha256(
            result.canonical_json_bytes(include_identity=False)
        ).hexdigest()
    )
    assert all(
        row.row_identity_sha256
        == hashlib.sha256(row.canonical_json_bytes(include_identity=False)).hexdigest()
        for row in result.industries
    )


def test_peer_ordered_v4_classification_preserves_the_whole_cohort(
    tmp_path: Path,
) -> None:
    api = _api()
    directions = ("ADVANCE", "DECLINE", "UNCHANGED")
    context, private_context = _retained_context_for_directions(
        tmp_path / "context", directions
    )
    assert len(private_context.request.members) == len(directions)
    classification = _retained_classification(
        tmp_path / "classification",
        context,
        private_context,
        industries=("Technology", "Banking", "Technology"),
        row_order=tuple(reversed(range(100))),
    )

    result = api.reduce_current_industry_participation_v4(context, classification)

    assert tuple(
        (row.industry, row.member_count, row.advances, row.declines, row.unchanged)
        for row in result.industries
    ) == (
        ("Banking", 1, 0, 1, 0),
        ("Technology", 2, 1, 0, 1),
    )
    assert sum(row.member_count for row in result.industries) == result.cohort_size
    assert (
        sum(row.advances for row in result.industries),
        sum(row.declines for row in result.industries),
        sum(row.unchanged for row in result.industries),
    ) == (
        context.market_regime_report.advances,
        context.market_regime_report.declines,
        context.market_regime_report.unchanged,
    )
    assert api.current_industry_participation_is_exact_valid_v4(result, context)


def test_observed_v4_binds_current_classification_and_context_sessions_exactly(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)
    result = api.reduce_current_industry_participation_v4(context, classification)
    regime = context.market_regime_report

    assert result.market_regime_report_identity_sha256 == regime.report_identity_sha256
    assert (
        result.classification_input_identity_sha256
        == classification.input_identity_sha256
    )
    assert result.artifact_sha256 == classification.artifact_sha256
    assert result.snapshot_identity_sha256 == classification.snapshot_identity_sha256
    assert result.archive_identity_sha256 == classification.archive_identity_sha256
    assert (
        result.archive_receipt_identity_sha256
        == classification.archive_receipt_identity_sha256
    )
    assert (
        result.retained_classification_identity_sha256
        == classification.retained_identity_sha256
    )
    assert (
        result.canonical_cohort_identity_sha256
        == regime.canonical_cohort_identity_sha256
    )
    assert result.decision_session == regime.decision_session
    assert result.comparison_session == regime.comparison_session
    assert result.decision_cutoff == regime.decision_cutoff
    assert result.known_at == classification.known_at
    assert result.known_at <= result.decision_cutoff
    assert result.known_at.astimezone(api._IST).date() != result.decision_session


@pytest.mark.parametrize(
    ("legacy", "expected_url", "crossed_url"),
    (
        (
            False,
            "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
            "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv",
        ),
        (
            True,
            "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv",
            "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
        ),
    ),
)
def test_industry_v4_binds_schema_to_non_crossable_source_url(
    tmp_path: Path,
    legacy: bool,
    expected_url: str,
    crossed_url: str,
) -> None:
    api = _api()
    classification_api = _classification_test_module()._api()
    context, private_context = _retained_context(tmp_path / "context")
    classification = _retained_classification(
        tmp_path / "classification",
        context,
        private_context,
        legacy=legacy,
    )
    result = api.reduce_current_industry_participation_v4(context, classification)
    expected_schema = (
        classification_api.LEGACY_CLASSIFICATION_SCHEMA_IDENTITY_SHA256
        if legacy
        else classification_api.CLASSIFICATION_SCHEMA_IDENTITY_SHA256
    )
    crossed_schema = (
        classification_api.CLASSIFICATION_SCHEMA_IDENTITY_SHA256
        if legacy
        else classification_api.LEGACY_CLASSIFICATION_SCHEMA_IDENTITY_SHA256
    )

    assert classification.schema_identity_sha256 == expected_schema
    assert result.source_url == expected_url
    assert api._classification_source_url(expected_schema) == expected_url
    assert api.current_industry_participation_is_exact_valid_v4(result, context)
    assert not api._industry_value_is_exact_unsealed_v4(
        result,
        context,
        crossed_schema,
    )

    original_identity = result.report_identity_sha256
    object.__setattr__(result, "source_url", crossed_url)
    object.__setattr__(
        result,
        "report_identity_sha256",
        api._object_identity_without(result, "report_identity_sha256", "_reducer_seal"),
    )
    assert not api.current_industry_participation_is_exact_valid_v4(result, context)

    object.__setattr__(result, "source_url", expected_url)
    object.__setattr__(result, "report_identity_sha256", original_identity)
    assert api.current_industry_participation_is_exact_valid_v4(result, context)


def test_future_known_classification_failure_is_exact_and_retains_its_time(
    tmp_path: Path,
) -> None:
    api = _api()
    context, private_context = _retained_context(tmp_path / "context")
    classification = _retained_classification(
        tmp_path / "classification",
        context,
        private_context,
        known_at=context.market_regime_report.decision_cutoff + timedelta(minutes=1),
    )

    result = api.reduce_current_industry_participation_v4(context, classification)

    _assert_failure(
        result,
        "INSUFFICIENT_EVIDENCE",
        ("CLASSIFICATION_FUTURE_KNOWN",),
    )
    assert result.known_at == classification.known_at
    assert api.current_industry_participation_is_exact_valid_v4(result, context)
    future_date = _retained_classification(
        tmp_path / "future-date-classification",
        context,
        private_context,
        known_at=context.market_regime_report.decision_cutoff + timedelta(days=1),
    )
    future_date_result = api.reduce_current_industry_participation_v4(
        context, future_date
    )
    _assert_failure(
        future_date_result,
        "INSUFFICIENT_EVIDENCE",
        ("CLASSIFICATION_FUTURE_KNOWN", "CLASSIFICATION_SESSION_STALE"),
    )


@pytest.mark.parametrize(
    ("reason", "state"),
    (
        ("CLASSIFICATION_ARTIFACT_MISSING", "INSUFFICIENT_EVIDENCE"),
        ("CLASSIFICATION_ARTIFACT_MALFORMED", "MALFORMED_EVIDENCE"),
        ("CLASSIFICATION_SOURCE_UNSUPPORTED", "UNSUPPORTED_CAPABILITY"),
        ("CLASSIFICATION_TIER_UNSUPPORTED", "UNSUPPORTED_CAPABILITY"),
        ("CLASSIFICATION_MEMBER_UNSUPPORTED", "UNSUPPORTED_CAPABILITY"),
        ("CLASSIFICATION_AMBIGUOUS", "MALFORMED_EVIDENCE"),
        ("CLASSIFICATION_CONFLICTING", "MALFORMED_EVIDENCE"),
        ("COHORT_BINDING_MISMATCH", "MALFORMED_EVIDENCE"),
        ("MEMBER_IDENTITY_MISMATCH", "MALFORMED_EVIDENCE"),
        ("CLASSIFICATION_FUTURE_KNOWN", "INSUFFICIENT_EVIDENCE"),
        ("CLASSIFICATION_SESSION_STALE", "INSUFFICIENT_EVIDENCE"),
        ("CLASSIFICATION_ARCHIVE_FAILED", "INSUFFICIENT_EVIDENCE"),
    ),
)
def test_classification_failures_remain_independent_closed_redacted_v4_results(
    tmp_path: Path,
    reason: str,
    state: str,
) -> None:
    api = _api()
    context, _classification = _inputs(tmp_path)

    result = api.reduce_current_industry_participation_v4(
        context,
        _classification_failure(reason),
    )

    _assert_failure(result, state, (reason,))


def test_classification_insufficiency_is_closed_and_redacted(tmp_path: Path) -> None:
    api = _api()
    context, _classification = _inputs(tmp_path)

    result = api.reduce_current_industry_participation_v4(
        context,
        _classification_failure("CLASSIFICATION_ARCHIVE_FAILED"),
    )

    _assert_failure(
        result,
        "INSUFFICIENT_EVIDENCE",
        ("CLASSIFICATION_ARCHIVE_FAILED",),
    )


def test_failure_state_precedence_and_global_reason_order_are_closed(
    tmp_path: Path,
) -> None:
    api = _api()
    context, _classification = _inputs(tmp_path)
    classification_api = _classification_test_module()._api()
    classification = classification_api.CurrentIndustryClassificationFailureV1(
        evidence_state="MALFORMED_EVIDENCE",
        reasons=(
            "CLASSIFICATION_ARTIFACT_MALFORMED",
            "CLASSIFICATION_MEMBER_UNSUPPORTED",
            "CLASSIFICATION_ARCHIVE_FAILED",
        ),
    )

    result = api.reduce_current_industry_participation_v4(context, classification)

    _assert_failure(
        result,
        "MALFORMED_EVIDENCE",
        (
            "CLASSIFICATION_ARTIFACT_MALFORMED",
            "CLASSIFICATION_MEMBER_UNSUPPORTED",
            "CLASSIFICATION_ARCHIVE_FAILED",
        ),
    )


def test_reducer_neither_recomputes_direction_nor_performs_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)
    v4 = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v4"
    )

    def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("Industry V4 performed an effect or direction evaluation")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(
        v4,
        "evaluate_current_supplied_cohort_market_regime_v4",
        forbidden,
        raising=False,
    )

    assert (
        api.reduce_current_industry_participation_v4(
            context,
            classification,
        ).evidence_state
        == "OBSERVED"
    )


def test_observed_and_failure_outputs_never_leak_private_members_or_raw_evidence(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)
    observed = api.reduce_current_industry_participation_v4(context, classification)
    failure = api.reduce_current_industry_participation_v4(
        context,
        _classification_failure("CLASSIFICATION_ARTIFACT_MISSING"),
    )

    for result in (observed, failure):
        encoded = result.canonical_json_bytes().decode()
        for private_value in ("INE002A01018", "M001", "ADVANCE", "Company 000"):
            assert private_value not in encoded


def test_rejects_wrong_context_seal_splices_and_structural_bounds(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)

    object.__setattr__(context, "_archive_seal", object())
    with pytest.raises((TypeError, ValueError)):
        api.reduce_current_industry_participation_v4(context, classification)

    context, classification = _inputs(tmp_path / "spliced")
    object.__setattr__(classification, "cohort_identity_sha256", "f" * 64)
    result = api.reduce_current_industry_participation_v4(context, classification)
    _assert_failure(result, "MALFORMED_EVIDENCE", ("COHORT_BINDING_MISMATCH",))

    context, classification = _inputs(tmp_path / "bounds")
    object.__setattr__(context.market_regime_report, "cohort_size", 51)
    with pytest.raises((TypeError, ValueError)):
        api.reduce_current_industry_participation_v4(context, classification)


def test_invalid_classification_drops_forged_provenance_but_valid_stale_retains_it(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)

    object.__setattr__(classification, "retained_identity_sha256", "f" * 64)
    invalid = api.reduce_current_industry_participation_v4(context, classification)
    _assert_failure(invalid, "MALFORMED_EVIDENCE", ("COHORT_BINDING_MISMATCH",))
    assert invalid.classification_identity_sha256 is None
    assert invalid.known_at is None

    context, private_context = _retained_context(tmp_path / "stale-context")
    stale = _retained_classification(
        tmp_path / "stale-classification",
        context,
        private_context,
        known_at=context.market_regime_report.decision_cutoff - timedelta(days=2),
    )
    assert (
        stale.known_at.astimezone(api._IST).date()
        != context.market_regime_report.decision_cutoff.astimezone(api._IST).date()
    )
    result = api.reduce_current_industry_participation_v4(context, stale)

    _assert_failure(
        result,
        "INSUFFICIENT_EVIDENCE",
        ("CLASSIFICATION_SESSION_STALE",),
    )
    assert result.classification_identity_sha256 == stale.retained_identity_sha256
    assert result.known_at == stale.known_at


def test_exact_industry_validator_rejects_forged_upstream_binding(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)
    result = api.reduce_current_industry_participation_v4(context, classification)

    assert api.current_industry_participation_is_exact_valid_v4(result, context)
    forged = object.__new__(type(result))
    for name in result.__dataclass_fields__:
        object.__setattr__(forged, name, getattr(result, name))
    object.__setattr__(forged, "market_regime_report_identity_sha256", "0" * 64)
    assert not api.current_industry_participation_is_exact_valid_v4(forged, context)

    forged_registry_seal = object.__new__(type(result._reducer_seal))
    object.__setattr__(forged, "_reducer_seal", forged_registry_seal)
    assert not api.current_industry_participation_is_exact_valid_v4(forged, context)


def test_exact_industry_validator_rejects_rehashed_registered_result_then_recovers(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)
    result = api.reduce_current_industry_participation_v4(context, classification)
    original_known_at = result.known_at
    original_identity = result.report_identity_sha256

    object.__setattr__(result, "known_at", original_known_at - timedelta(seconds=1))
    object.__setattr__(
        result,
        "report_identity_sha256",
        api._object_identity_without(result, "report_identity_sha256", "_reducer_seal"),
    )
    assert not api.current_industry_participation_is_exact_valid_v4(result, context)

    object.__setattr__(result, "known_at", original_known_at)
    object.__setattr__(result, "report_identity_sha256", original_identity)
    assert api.current_industry_participation_is_exact_valid_v4(result, context)


def test_industry_seal_is_opaque_and_does_not_retain_classification(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)
    observed = api.reduce_current_industry_participation_v4(context, classification)

    assert all(
        not hasattr(observed._reducer_seal, name)
        for name in (
            "candidate",
            "classification",
            "context",
            "event",
            "marker",
            "raw",
            "receipt",
            "root",
            "token",
        )
    )
    object.__setattr__(classification._private_rows[0], "industry", "Forged")
    assert api.current_industry_participation_is_exact_valid_v4(observed, context)


def test_reordered_selection_retains_observed_industry_counts(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}
    _v4_test_module().test_v4_preserves_supplied_member_order_but_rejects_identity_bridge_drift(
        tmp_path / "context", capture=captured
    )
    context = captured["retained"]
    private_context = captured["candidate"].context_object
    classification = _retained_classification(
        tmp_path / "classification",
        context,
        private_context,
        industries=("Technology", "Banks"),
    )
    result = _api().reduce_current_industry_participation_v4(context, classification)
    assert result.evidence_state == "OBSERVED"
    assert tuple(
        (row.industry, row.member_count, row.unchanged) for row in result.industries
    ) == (("Banks", 1, 1), ("Technology", 1, 1))
    assert _api().current_industry_participation_is_exact_valid_v4(result, context)
