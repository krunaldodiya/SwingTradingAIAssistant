# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false, reportOperatorIssue=false, reportOptionalMemberAccess=false, reportOptionalOperand=false, reportReturnType=false
"""RED contract tests for Plan27 aggregate-only Industry Participation V2."""

from __future__ import annotations

import hashlib
import importlib
import importlib.machinery
import importlib.util
import inspect
import json
import shutil
import socket
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn

import pytest

from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

_PRIVATE_CONTEXTS: dict[int, Any] = {}

_PLAN27_INDUSTRY_SCHEMA_PREIMAGE = json.loads(
    (
        Path(__file__).parent / "data" / "plan27_industry_v2_schema_preimage.json"
    ).read_text(encoding="utf-8")
)


def _api() -> Any:
    return importlib.import_module(
        "swing_trading_ai_assistant.sector_analysis.current_industry_participation_v2"
    )


def test_industry_v2_runtime_identity_supports_installed_package_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _api()
    manifest = importlib.import_module(module._RUNTIME_MANIFEST_MODULE)
    baseline = module.current_industry_participation_runtime_code_identity_v2()
    installed_root = tmp_path / "site-packages"
    for loaded, relative_path in (
        (module, module._SOURCE_PATH),
        (manifest, module._RUNTIME_MANIFEST_PATH),
    ):
        installed = installed_root.joinpath(*relative_path.split("/")[1:])
        installed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(loaded.__file__, installed)
        monkeypatch.setattr(loaded, "__file__", str(installed))
        monkeypatch.setattr(
            loaded,
            "__loader__",
            importlib.machinery.SourceFileLoader(loaded.__name__, str(installed)),
        )

    assert module.current_industry_participation_runtime_code_identity_v2() == baseline
    source = installed_root.joinpath(
        "swing_trading_ai_assistant/sector_analysis/"
        "current_industry_participation_v2.py"
    )
    with source.open("ab") as copied:
        copied.write(b"\n")

    with pytest.raises(
        ValueError, match="industry participation v2 runtime identity invalid"
    ):
        module.current_industry_participation_runtime_code_identity_v2()


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


def _v3_test_module() -> ModuleType:
    return _test_module(
        "market_regime/test_current_supplied_cohort_v3.py",
        "test_current_supplied_cohort_v3",
    )


def _private_lease(tmp_path: Path) -> StorageRootLease:
    tmp_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire_private_empty(tmp_path)
    assert acquired.lease is not None
    return acquired.lease


def _retained_context(tmp_path: Path) -> Any:
    tmp_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    """Capture the real V3 public composition result after archive validation."""
    v3_test = _v3_test_module()
    v3_api = v3_test._v3()
    captured: list[tuple[Any, Any]] = []
    original = v3_api.FileCurrentSamePassMarketContextArchiveV1.archive_exact

    def capture(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        if type(result) is v3_api.RetainedCurrentSamePassMarketContextV3:
            captured.append((result, args[1].context_object))
        return result

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            v3_api.FileCurrentSamePassMarketContextArchiveV1, "archive_exact", capture
        )
        v3_test.test_outer_composition_retains_real_context_and_archive_files(
            tmp_path, monkeypatch
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
        raise ValueError("the real V3 integration fixture is observed-only")
    context, private_context = _retained_context(tmp_path / "context")
    _PRIVATE_CONTEXTS[id(context)] = private_context
    classification = _retained_classification(
        tmp_path / "classification", context, private_context
    )
    return context, classification


def _v3_request(context: Any) -> Any:
    return _PRIVATE_CONTEXTS[id(context)].request


def _v3_ledger_known_at(context: Any, position: int) -> Any:
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


def test_reducer_accepts_only_the_exact_sealed_retained_v3_context_and_two_inputs(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)

    assert tuple(
        inspect.signature(api.reduce_current_industry_participation_v2).parameters
    ) == (
        "market_context",
        "classification",
    )
    assert api.reduce_current_industry_participation_v2(
        context, classification
    ).evidence_state == ("OBSERVED")
    for bad_context, bad_classification in (
        (object(), classification),
        (context, object()),
    ):
        with pytest.raises(TypeError):
            api.reduce_current_industry_participation_v2(
                bad_context, bad_classification
            )


def test_observed_v2_rows_are_aggregate_only_sorted_reconciled_and_identified(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)
    result = api.reduce_current_industry_participation_v2(context, classification)
    regime = context.market_regime_report

    assert (
        result.contract_version == "current-supplied-cohort-industry-participation@v2"
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


@pytest.mark.parametrize("key", ("semantic_type", "unit", "nullability", "bounds"))
def test_industry_schema_preimage_is_complete_independent_and_rejects_every_field_drift(
    key: str,
) -> None:
    api = _api()
    metadata = api.current_industry_participation_schema_metadata_v2()

    assert api._canonical(metadata) == api._canonical(_PLAN27_INDUSTRY_SCHEMA_PREIMAGE)
    assert (
        api.current_industry_participation_schema_metadata_digest_v2(metadata)
        == "0382b0bbb769dd9ec7dfea9229bd00ecc65d25c404d94481fb5f0a82472661fd"
        == api.SCHEMA_IDENTITY_SHA256
    )

    for row_index, row in enumerate(_PLAN27_INDUSTRY_SCHEMA_PREIMAGE["type_rows"]):
        for field_index, _field in enumerate(row["ordered_fields"]):
            mutated = deepcopy(metadata)
            mutated["type_rows"][row_index]["ordered_fields"][field_index][key] = (
                "FORGED"
            )
            with pytest.raises(ValueError, match="frozen contract"):
                api.current_industry_participation_schema_identity_from_metadata_v2(
                    mutated
                )

    state = deepcopy(metadata)
    state["state_projections"] = ()
    with pytest.raises(ValueError, match="frozen contract"):
        api.current_industry_participation_schema_identity_from_metadata_v2(state)

    unknown = deepcopy(metadata)
    unknown["unexpected"] = "FORGED"
    with pytest.raises(ValueError, match="unknown Industry schema metadata key"):
        api.current_industry_participation_schema_metadata_digest_v2(unknown)


def test_observed_v2_binds_current_classification_and_context_sessions_exactly(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)
    result = api.reduce_current_industry_participation_v2(context, classification)
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
def test_industry_v2_binds_schema_to_non_crossable_source_url(
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
    result = api.reduce_current_industry_participation_v2(context, classification)
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
    assert api.current_industry_participation_is_exact_valid_v2(result, context)
    assert not api._industry_value_is_exact_unsealed_v2(
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
    assert not api.current_industry_participation_is_exact_valid_v2(result, context)

    object.__setattr__(result, "source_url", expected_url)
    object.__setattr__(result, "report_identity_sha256", original_identity)
    assert api.current_industry_participation_is_exact_valid_v2(result, context)


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

    result = api.reduce_current_industry_participation_v2(context, classification)

    _assert_failure(
        result,
        "INSUFFICIENT_EVIDENCE",
        ("CLASSIFICATION_FUTURE_KNOWN",),
    )
    assert result.known_at == classification.known_at
    assert api.current_industry_participation_is_exact_valid_v2(result, context)
    future_date = _retained_classification(
        tmp_path / "future-date-classification",
        context,
        private_context,
        known_at=context.market_regime_report.decision_cutoff + timedelta(days=1),
    )
    future_date_result = api.reduce_current_industry_participation_v2(
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
def test_classification_failures_remain_independent_closed_redacted_v2_results(
    tmp_path: Path,
    reason: str,
    state: str,
) -> None:
    api = _api()
    context, _classification = _inputs(tmp_path)

    result = api.reduce_current_industry_participation_v2(
        context,
        _classification_failure(reason),
    )

    _assert_failure(result, state, (reason,))


def test_classification_insufficiency_is_closed_and_redacted(tmp_path: Path) -> None:
    api = _api()
    context, _classification = _inputs(tmp_path)

    result = api.reduce_current_industry_participation_v2(
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

    result = api.reduce_current_industry_participation_v2(context, classification)

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
    v3 = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v3"
    )

    def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("Industry V2 performed an effect or direction evaluation")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(
        v3,
        "evaluate_current_supplied_cohort_market_regime_v3",
        forbidden,
        raising=False,
    )

    assert (
        api.reduce_current_industry_participation_v2(
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
    observed = api.reduce_current_industry_participation_v2(context, classification)
    failure = api.reduce_current_industry_participation_v2(
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
        api.reduce_current_industry_participation_v2(context, classification)

    context, classification = _inputs(tmp_path / "spliced")
    object.__setattr__(classification, "cohort_identity_sha256", "f" * 64)
    result = api.reduce_current_industry_participation_v2(context, classification)
    _assert_failure(result, "MALFORMED_EVIDENCE", ("COHORT_BINDING_MISMATCH",))

    context, classification = _inputs(tmp_path / "bounds")
    object.__setattr__(context.market_regime_report, "cohort_size", 51)
    with pytest.raises((TypeError, ValueError)):
        api.reduce_current_industry_participation_v2(context, classification)


def test_invalid_classification_drops_forged_provenance_but_valid_stale_retains_it(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)

    object.__setattr__(classification, "retained_identity_sha256", "f" * 64)
    invalid = api.reduce_current_industry_participation_v2(context, classification)
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
    result = api.reduce_current_industry_participation_v2(context, stale)

    _assert_failure(
        result,
        "INSUFFICIENT_EVIDENCE",
        ("CLASSIFICATION_SESSION_STALE",),
    )
    assert result.classification_identity_sha256 == stale.retained_identity_sha256
    assert result.known_at == stale.known_at


def test_industry_v1_contract_remains_the_frozen_v1_behavior(tmp_path: Path) -> None:
    v1 = importlib.import_module(
        "swing_trading_ai_assistant.sector_analysis.current_industry_participation"
    )
    v1_tests = _test_module(
        "sector_analysis/test_current_industry_participation.py",
        "test_current_industry_participation",
    )

    result = v1_tests._reduce(tmp_path / "v1")

    assert (
        result.contract_version == "current-supplied-cohort-industry-participation@v1"
    )
    assert result.evidence_state == "OBSERVED"
    assert callable(v1.reduce_current_industry_participation_v1)


def test_exact_industry_validator_rejects_forged_upstream_binding(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)
    result = api.reduce_current_industry_participation_v2(context, classification)

    assert api.current_industry_participation_is_exact_valid_v2(result, context)
    forged = object.__new__(type(result))
    for name in result.__dataclass_fields__:
        object.__setattr__(forged, name, getattr(result, name))
    object.__setattr__(forged, "market_regime_report_identity_sha256", "0" * 64)
    assert not api.current_industry_participation_is_exact_valid_v2(forged, context)

    forged_registry_seal = object.__new__(type(result._reducer_seal))
    object.__setattr__(forged, "_reducer_seal", forged_registry_seal)
    assert not api.current_industry_participation_is_exact_valid_v2(forged, context)


def test_exact_industry_validator_rejects_rehashed_registered_result_then_recovers(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)
    result = api.reduce_current_industry_participation_v2(context, classification)
    original_known_at = result.known_at
    original_identity = result.report_identity_sha256

    object.__setattr__(result, "known_at", original_known_at - timedelta(seconds=1))
    object.__setattr__(
        result,
        "report_identity_sha256",
        api._object_identity_without(result, "report_identity_sha256", "_reducer_seal"),
    )
    assert not api.current_industry_participation_is_exact_valid_v2(result, context)

    object.__setattr__(result, "known_at", original_known_at)
    object.__setattr__(result, "report_identity_sha256", original_identity)
    assert api.current_industry_participation_is_exact_valid_v2(result, context)


def test_industry_seal_is_opaque_and_does_not_retain_classification(
    tmp_path: Path,
) -> None:
    api = _api()
    context, classification = _inputs(tmp_path)
    observed = api.reduce_current_industry_participation_v2(context, classification)

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
    assert api.current_industry_participation_is_exact_valid_v2(observed, context)
