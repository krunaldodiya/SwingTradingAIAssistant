from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

import pytest

from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    MAX_PLANNED_MONTHS,
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.partition_reconciliation import (
    PartitionDecision,
    PartitionEvidence,
    ReconciliationAction,
    RequestReason,
    reconcile_partition_plans,
)


class _DateSubclass(date):
    pass


class _StrSubclass(str):
    pass


def _plan(month: int = 1) -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|INE002A01018",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2022,
        month,
        date(2022, month, 1),
        date(2022, month, 28),
    )


def _evidence(plan: PlannedInstrumentMonth, **overrides: object) -> PartitionEvidence:
    values: dict[str, object] = {
        "plan": plan,
        "manifest_verified": True,
        "file_exists": True,
        "recorded_path": "data/candles/reliance-2022-01.parquet",
        "observed_path": "data/candles/reliance-2022-01.parquet",
        "recorded_checksum": "a" * 64,
        "recomputed_checksum": "a" * 64,
        "recorded_schema_version": 1,
        "observed_schema_version": 1,
        "physical_compatible": True,
        "recorded_from_date": plan.from_date,
        "recorded_to_date": plan.to_date,
        "coverage_passed": True,
        "quality_passed": True,
    }
    values.update(overrides)
    return PartitionEvidence(**values)  # type: ignore[arg-type]


def test_skips_one_fully_verified_matching_partition_with_no_reasons() -> None:
    plan = _plan()
    assert reconcile_partition_plans((plan,), (_evidence(plan),)) == (
        PartitionDecision(plan, ReconciliationAction.SKIP, ()),
    )


@pytest.mark.parametrize(
    "override,reason",
    [
        ({"manifest_verified": False}, RequestReason.MANIFEST_NOT_VERIFIED),
        ({"file_exists": False}, RequestReason.FILE_MISSING),
        (
            {"observed_path": "data/candles/other.parquet"},
            RequestReason.PATH_INVALID_OR_MISMATCHED,
        ),
        (
            {"recomputed_checksum": "b" * 64},
            RequestReason.CHECKSUM_INVALID_OR_MISMATCHED,
        ),
        (
            {"observed_schema_version": 2},
            RequestReason.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
        ),
        (
            {"physical_compatible": False},
            RequestReason.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
        ),
        (
            {"recorded_to_date": date(2022, 1, 27)},
            RequestReason.RECORDED_RANGE_MISMATCHED,
        ),
        ({"coverage_passed": False}, RequestReason.COVERAGE_NOT_PASSED),
        ({"quality_passed": False}, RequestReason.QUALITY_NOT_PASSED),
    ],
)
def test_requests_for_each_independent_evidence_failure(
    override: dict[str, object], reason: RequestReason
) -> None:
    plan = _plan()
    result = reconcile_partition_plans((plan,), (_evidence(plan, **override),))
    assert result == (PartitionDecision(plan, ReconciliationAction.REQUEST, (reason,)),)


def test_requests_missing_evidence_without_inspecting_other_facts() -> None:
    plan = _plan()
    assert reconcile_partition_plans((plan,), ()) == (
        PartitionDecision(
            plan, ReconciliationAction.REQUEST, (RequestReason.MISSING_EVIDENCE,)
        ),
    )


def test_requests_duplicate_evidence_without_inspecting_or_selecting_duplicates() -> (
    None
):
    plan = _plan()
    duplicate = object.__new__(PartitionEvidence)
    object.__setattr__(duplicate, "plan", plan)
    assert reconcile_partition_plans((plan,), (_evidence(plan), duplicate)) == (
        PartitionDecision(
            plan, ReconciliationAction.REQUEST, (RequestReason.DUPLICATE_EVIDENCE,)
        ),
    )


def test_requests_multiple_failures_in_public_declaration_order() -> None:
    plan = _plan()
    result = reconcile_partition_plans(
        (plan,),
        (
            _evidence(
                plan,
                manifest_verified=False,
                file_exists=False,
                observed_path=None,
                recomputed_checksum=None,
                observed_schema_version=None,
                physical_compatible=False,
                recorded_to_date=date(2022, 1, 27),
                coverage_passed=False,
                quality_passed=False,
            ),
        ),
    )
    assert result[0].reasons == (
        RequestReason.MANIFEST_NOT_VERIFIED,
        RequestReason.FILE_MISSING,
        RequestReason.PATH_INVALID_OR_MISMATCHED,
        RequestReason.CHECKSUM_INVALID_OR_MISMATCHED,
        RequestReason.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
        RequestReason.RECORDED_RANGE_MISMATCHED,
        RequestReason.COVERAGE_NOT_PASSED,
        RequestReason.QUALITY_NOT_PASSED,
    )


def test_requests_matching_but_unsupported_schema_version() -> None:
    plan = _plan()
    result = reconcile_partition_plans(
        (plan,),
        (
            _evidence(
                plan,
                recorded_schema_version=2,
                observed_schema_version=2,
            ),
        ),
    )
    assert result[0].reasons == (RequestReason.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,)


def test_verified_rerun_has_zero_requests() -> None:
    plans = (_plan(1), _plan(2))
    decisions = reconcile_partition_plans(
        plans, tuple(_evidence(plan) for plan in plans)
    )
    assert all(decision.action is ReconciliationAction.SKIP for decision in decisions)


def test_coverage_boolean_prevents_max_timestamp_from_becoming_completeness_proof() -> (
    None
):
    plan = _plan()
    result = reconcile_partition_plans(
        (plan,), (_evidence(plan, coverage_passed=False),)
    )
    assert result[0].reasons == (RequestReason.COVERAGE_NOT_PASSED,)
    assert not hasattr(_evidence(plan), "max_ts")


@pytest.mark.parametrize(
    "field,value",
    [
        ("recorded_path", 1),
        ("observed_path", 1),
        ("recorded_checksum", 1),
        ("recomputed_checksum", 1),
        ("recorded_schema_version", True),
        ("observed_schema_version", True),
        ("recorded_from_date", datetime(2022, 1, 1)),
        ("recorded_to_date", _DateSubclass(2022, 1, 28)),
        ("manifest_verified", 1),
        ("file_exists", 1),
        ("physical_compatible", 1),
        ("coverage_passed", 1),
        ("quality_passed", 1),
    ],
)
def test_evidence_rejects_wrong_runtime_scalar_types(field: str, value: object) -> None:
    plan = _plan()
    with pytest.raises(ValueError):
        _evidence(plan, **{field: value})


def test_evidence_and_decision_models_are_immutable_and_sealed() -> None:
    plan = _plan()
    evidence = _evidence(plan)
    decision = PartitionDecision(plan, ReconciliationAction.SKIP, ())
    with pytest.raises((AttributeError, TypeError)):
        evidence.file_exists = False  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        decision.action = ReconciliationAction.REQUEST  # type: ignore[misc]
    with pytest.raises(TypeError, match="cannot be subclassed"):

        class _EvidenceBypass(PartitionEvidence):
            pass

    with pytest.raises(TypeError, match="cannot be subclassed"):

        class _DecisionBypass(PartitionDecision):
            pass


def test_public_models_revalidate_mutated_embedded_plan() -> None:
    plan = _plan()
    object.__setattr__(plan, "security_id", 1)
    with pytest.raises(ValueError, match="invalid partition evidence"):
        _evidence(plan)
    with pytest.raises(ValueError, match="invalid partition decision"):
        PartitionDecision(plan, ReconciliationAction.SKIP, ())


@pytest.mark.parametrize(
    "action,reasons",
    [
        (ReconciliationAction.SKIP, (RequestReason.FILE_MISSING,)),
        (ReconciliationAction.REQUEST, ()),
        (ReconciliationAction.REQUEST, (RequestReason.FILE_MISSING,) * 2),
        (
            ReconciliationAction.REQUEST,
            (RequestReason.QUALITY_NOT_PASSED, RequestReason.FILE_MISSING),
        ),
    ],
)
def test_decision_rejects_invalid_action_reason_invariants(
    action: ReconciliationAction, reasons: tuple[RequestReason, ...]
) -> None:
    with pytest.raises(ValueError, match="invalid partition decision"):
        PartitionDecision(_plan(), action, reasons)


@pytest.mark.parametrize(
    "override,reason",
    [
        ({"recorded_path": None}, RequestReason.PATH_INVALID_OR_MISMATCHED),
        ({"observed_path": None}, RequestReason.PATH_INVALID_OR_MISMATCHED),
        (
            {"recorded_path": "/absolute/path.parquet"},
            RequestReason.PATH_INVALID_OR_MISMATCHED,
        ),
        (
            {"observed_path": "C:/drive/path.parquet"},
            RequestReason.PATH_INVALID_OR_MISMATCHED,
        ),
        (
            {"observed_path": "data/ bad .parquet"},
            RequestReason.PATH_INVALID_OR_MISMATCHED,
        ),
        (
            {"observed_path": "data/control\x01.parquet"},
            RequestReason.PATH_INVALID_OR_MISMATCHED,
        ),
        (
            {"observed_path": "data/control\x80.parquet"},
            RequestReason.PATH_INVALID_OR_MISMATCHED,
        ),
        (
            {"observed_path": "data/control\x85.parquet"},
            RequestReason.PATH_INVALID_OR_MISMATCHED,
        ),
        (
            {"observed_path": "data/control\x9f.parquet"},
            RequestReason.PATH_INVALID_OR_MISMATCHED,
        ),
        (
            {"observed_path": "data/hidden\u202epath.parquet"},
            RequestReason.PATH_INVALID_OR_MISMATCHED,
        ),
        ({"recorded_checksum": None}, RequestReason.CHECKSUM_INVALID_OR_MISMATCHED),
        (
            {"recomputed_checksum": "A" * 64},
            RequestReason.CHECKSUM_INVALID_OR_MISMATCHED,
        ),
        (
            {"recorded_schema_version": None},
            RequestReason.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
        ),
        (
            {"observed_schema_version": 0},
            RequestReason.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
        ),
        ({"recorded_from_date": None}, RequestReason.RECORDED_RANGE_MISMATCHED),
        ({"recorded_to_date": None}, RequestReason.RECORDED_RANGE_MISMATCHED),
        (
            {
                "recorded_from_date": date(2022, 1, 28),
                "recorded_to_date": date(2022, 1, 1),
            },
            RequestReason.RECORDED_RANGE_MISMATCHED,
        ),
    ],
)
def test_incomplete_or_corrupt_evidence_content_maps_to_one_request_reason(
    override: dict[str, object], reason: RequestReason
) -> None:
    plan = _plan()
    assert reconcile_partition_plans((plan,), (_evidence(plan, **override),)) == (
        PartitionDecision(plan, ReconciliationAction.REQUEST, (reason,)),
    )


@pytest.mark.parametrize(
    "path",
    [
        "data/control\x80.parquet",
        "data/control\x85.parquet",
        "data/control\x9f.parquet",
        "data/hidden\u202epath.parquet",
    ],
)
def test_nonprintable_paths_are_invalid_even_when_recorded_and_observed_match(
    path: str,
) -> None:
    plan = _plan()
    decision = reconcile_partition_plans(
        (plan,), (_evidence(plan, recorded_path=path, observed_path=path),)
    )
    assert decision[0].reasons == (RequestReason.PATH_INVALID_OR_MISMATCHED,)


def test_rejects_duplicate_plans_and_orphan_evidence() -> None:
    plan = _plan()
    with pytest.raises(ValueError, match="duplicate plans"):
        reconcile_partition_plans((plan, plan), ())
    with pytest.raises(ValueError, match="orphan evidence"):
        reconcile_partition_plans((plan,), (_evidence(_plan(2)),))


def test_partition_key_rejects_duplicate_plans_despite_mutable_identity_or_range() -> (
    None
):
    plan = _plan()
    same_key_different_symbol_and_range = PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|MUTABLE",
        "INE002A01018",
        "RENAMED",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2022,
        1,
        date(2022, 1, 2),
        date(2022, 1, 28),
    )
    with pytest.raises(ValueError, match="duplicate plans"):
        reconcile_partition_plans((plan, same_key_different_symbol_and_range), ())


def test_evidence_matches_the_physical_key_not_mutable_identity_or_range() -> None:
    plan = _plan()
    equivalent_key = PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|MUTABLE",
        "INE002A01018",
        "RENAMED",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2022,
        1,
        date(2022, 1, 2),
        date(2022, 1, 28),
    )
    decision = reconcile_partition_plans(
        (plan,),
        (
            _evidence(
                equivalent_key,
                recorded_from_date=plan.from_date,
                recorded_to_date=plan.to_date,
            ),
        ),
    )
    assert decision[0].action is ReconciliationAction.SKIP


def test_reconciliation_revalidates_bypassed_plans_and_evidence_identity() -> None:
    invalid_plan = _plan()
    object.__setattr__(invalid_plan, "security_id", 1)
    with pytest.raises(ValueError, match="invalid planned partition"):
        reconcile_partition_plans((invalid_plan,), ())

    uninitialized_plan = object.__new__(PlannedInstrumentMonth)
    with pytest.raises(ValueError, match="invalid planned partition"):
        reconcile_partition_plans((uninitialized_plan,), ())

    plan = _plan()
    uninitialized_evidence_plan = object.__new__(PlannedInstrumentMonth)
    evidence = _evidence(plan)
    object.__setattr__(evidence, "plan", uninitialized_evidence_plan)
    with pytest.raises(ValueError, match="invalid planned partition"):
        reconcile_partition_plans((plan,), (evidence,))


def test_mixed_batch_schedules_corrupt_partition_independently() -> None:
    plans = (_plan(1), _plan(2))
    decisions = reconcile_partition_plans(
        plans,
        (
            _evidence(plans[0], recomputed_checksum=None),
            _evidence(plans[1]),
        ),
    )
    assert decisions == (
        PartitionDecision(
            plans[0],
            ReconciliationAction.REQUEST,
            (RequestReason.CHECKSUM_INVALID_OR_MISMATCHED,),
        ),
        PartitionDecision(plans[1], ReconciliationAction.SKIP, ()),
    )


def test_rejects_malformed_exact_evidence_before_decision_construction() -> None:
    plan = _plan()
    malformed = object.__new__(PartitionEvidence)
    object.__setattr__(malformed, "plan", plan)
    with pytest.raises(ValueError, match="invalid partition evidence"):
        reconcile_partition_plans((plan,), (malformed,))


def test_sanitizes_uninitialized_exact_evidence_without_a_plan() -> None:
    evidence = object.__new__(PartitionEvidence)
    with pytest.raises(ValueError, match="invalid planned partition") as exc_info:
        reconcile_partition_plans((_plan(),), (evidence,))
    assert exc_info.value.__cause__ is None
    assert "AttributeError" not in str(exc_info.value)


def test_sanitizes_exact_evidence_with_a_mutated_non_plan_identity() -> None:
    evidence = _evidence(_plan())
    object.__setattr__(evidence, "plan", object())
    with pytest.raises(ValueError, match="invalid planned partition") as exc_info:
        reconcile_partition_plans((_plan(),), (evidence,))
    assert exc_info.value.__cause__ is None
    assert "AttributeError" not in str(exc_info.value)


def test_rejects_generators_malformed_sequences_and_oversize_before_retention() -> None:
    plan = _plan()
    with pytest.raises(ValueError, match="sequence"):
        reconcile_partition_plans((item for item in (plan,)), ())

    class _Malformed(Sequence[PlannedInstrumentMonth]):
        def __len__(self) -> int:
            return 1

        def __getitem__(self, index: int) -> PlannedInstrumentMonth:
            raise IndexError

    with pytest.raises(ValueError, match="malformed"):
        reconcile_partition_plans(_Malformed(), ())

    class _Oversized(Sequence[PlannedInstrumentMonth]):
        def __len__(self) -> int:
            return MAX_PLANNED_MONTHS + 1

        def __getitem__(self, index: int) -> PlannedInstrumentMonth:
            raise AssertionError("oversized inputs must not be retained or indexed")

    with pytest.raises(ValueError, match="maximum"):
        reconcile_partition_plans(_Oversized(), ())

    class _OversizedEvidence(Sequence[PartitionEvidence]):
        def __len__(self) -> int:
            return MAX_PLANNED_MONTHS + 1

        def __getitem__(self, index: int) -> PartitionEvidence:
            raise AssertionError("oversized evidence must not be retained or indexed")

    with pytest.raises(ValueError, match="maximum"):
        reconcile_partition_plans((), _OversizedEvidence())


def test_rejects_wrong_exact_element_types_for_plan_and_evidence_sequences() -> None:
    with pytest.raises(ValueError, match="exact PlannedInstrumentMonth"):
        reconcile_partition_plans((object(),), ())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exact PartitionEvidence"):
        reconcile_partition_plans((), (object(),))  # type: ignore[arg-type]


@pytest.mark.parametrize("operation", ["length", "item"])
def test_sanitizes_secret_sequence_exceptions(operation: str) -> None:
    class _Exploding(Sequence[PlannedInstrumentMonth]):
        def __len__(self) -> int:
            if operation == "length":
                raise RuntimeError("secret-token")
            return 1

        def __getitem__(self, index: int) -> PlannedInstrumentMonth:
            raise RuntimeError("secret-token")

    with pytest.raises(ValueError, match="sequence") as exc_info:
        reconcile_partition_plans(_Exploding(), ())
    assert "secret-token" not in str(exc_info.value)


def test_is_deterministic_and_output_is_an_immutable_tuple() -> None:
    plan = _plan()
    first = reconcile_partition_plans((plan,), (_evidence(plan),))
    assert first == reconcile_partition_plans((plan,), (_evidence(plan),))
    with pytest.raises(TypeError):
        first[0] = first[0]  # type: ignore[index]
