"""Pure reconciliation of planned partitions against verified evidence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import TypeVar, cast

from .monthly_request_planner import MAX_PLANNED_MONTHS, PlannedInstrumentMonth
from .schemas import CANDLE_SCHEMA_VERSION

_Model = TypeVar("_Model")


class ReconciliationAction(StrEnum):
    """The only reconciliation outcomes before provider requests are sent."""

    SKIP = "SKIP"
    REQUEST = "REQUEST"


class RequestReason(StrEnum):
    """Stable declaration order for deterministic request explanations."""

    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    DUPLICATE_EVIDENCE = "DUPLICATE_EVIDENCE"
    MANIFEST_NOT_VERIFIED = "MANIFEST_NOT_VERIFIED"
    FILE_MISSING = "FILE_MISSING"
    PATH_INVALID_OR_MISMATCHED = "PATH_INVALID_OR_MISMATCHED"
    CHECKSUM_INVALID_OR_MISMATCHED = "CHECKSUM_INVALID_OR_MISMATCHED"
    SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE = "SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE"
    RECORDED_RANGE_MISMATCHED = "RECORDED_RANGE_MISMATCHED"
    COVERAGE_NOT_PASSED = "COVERAGE_NOT_PASSED"
    QUALITY_NOT_PASSED = "QUALITY_NOT_PASSED"


@dataclass(frozen=True, slots=True)
class PartitionEvidence:
    """One manifest and physical-observation fact set for a planned partition."""

    plan: PlannedInstrumentMonth
    manifest_verified: bool
    file_exists: bool
    recorded_path: str | None
    observed_path: str | None
    recorded_checksum: str | None
    recomputed_checksum: str | None
    recorded_schema_version: int | None
    observed_schema_version: int | None
    physical_compatible: bool
    recorded_from_date: date | None
    recorded_to_date: date | None
    coverage_passed: bool
    quality_passed: bool

    def __init_subclass__(cls) -> None:
        raise TypeError("PartitionEvidence cannot be subclassed")

    def __post_init__(self) -> None:
        if not _has_evidence_runtime_types(self) or not _is_valid_planned_partition(
            self.plan
        ):
            raise ValueError("invalid partition evidence")


@dataclass(frozen=True, slots=True)
class PartitionDecision:
    """Immutable request-or-skip decision for one planned partition."""

    plan: PlannedInstrumentMonth
    action: ReconciliationAction
    reasons: tuple[RequestReason, ...]

    def __init_subclass__(cls) -> None:
        raise TypeError("PartitionDecision cannot be subclassed")

    def __post_init__(self) -> None:
        if (
            not _is_valid_planned_partition(self.plan)
            or type(self.action) is not ReconciliationAction
            or type(self.reasons) is not tuple
            or any(type(reason) is not RequestReason for reason in self.reasons)
            or len(set(self.reasons)) != len(self.reasons)
            or (self.action is ReconciliationAction.SKIP and self.reasons)
            or (self.action is ReconciliationAction.REQUEST and not self.reasons)
            or not _is_reason_declaration_order(self.reasons)
        ):
            raise ValueError("invalid partition decision")


def reconcile_partition_plans(
    plans: Sequence[PlannedInstrumentMonth], evidence: Sequence[PartitionEvidence]
) -> tuple[PartitionDecision, ...]:
    """Return ordered immutable decisions without inspecting files or providers."""
    planned = _validated_sequence(plans, PlannedInstrumentMonth, "plans")
    observed = _validated_sequence(evidence, PartitionEvidence, "evidence")
    planned_keys = tuple(_partition_key(plan) for plan in planned)
    if len(set(planned_keys)) != len(planned_keys):
        raise ValueError("duplicate plans are invalid")

    evidence_by_key: dict[
        tuple[str, str, str, str, str, str, int, int], list[PartitionEvidence]
    ] = {}
    planned_key_set = set(planned_keys)
    for item in observed:
        key = _partition_key(_evidence_plan(item))
        if key not in planned_key_set:
            raise ValueError("orphan evidence is invalid")
        evidence_by_key.setdefault(key, []).append(item)
    if any(
        len(items) == 1 and not _has_evidence_runtime_types(items[0])
        for items in evidence_by_key.values()
    ):
        raise ValueError("invalid partition evidence")

    return tuple(
        _decision_for_plan(plan, evidence_by_key.get(key, []))
        for plan, key in zip(planned, planned_keys, strict=True)
    )


def _validated_sequence(
    values: Sequence[_Model], expected_type: type[_Model], name: str
) -> tuple[_Model, ...]:
    if not isinstance(values, Sequence) or isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
        values, (str, bytes)
    ):
        raise ValueError(f"{name} must be a finite sequence")
    try:
        count = len(values)
    except Exception:
        raise ValueError(
            f"{name} must provide a valid finite sequence length"
        ) from None
    if count > MAX_PLANNED_MONTHS:
        raise ValueError(f"{name} exceed the maximum partition count")

    result: list[_Model] = []
    for index in range(count):
        try:
            value = values[index]
        except Exception:
            raise ValueError(f"{name} sequence is malformed") from None
        if type(value) is not expected_type:
            raise ValueError(
                f"{name} must contain exact {expected_type.__name__} values"
            )
        result.append(value)
    return tuple(result)


def _decision_for_plan(
    plan: PlannedInstrumentMonth, evidence: list[PartitionEvidence]
) -> PartitionDecision:
    if not evidence:
        return PartitionDecision(
            plan, ReconciliationAction.REQUEST, (RequestReason.MISSING_EVIDENCE,)
        )
    if len(evidence) != 1:
        return PartitionDecision(
            plan, ReconciliationAction.REQUEST, (RequestReason.DUPLICATE_EVIDENCE,)
        )

    item = evidence[0]
    reasons = tuple(
        reason
        for passed, reason in (
            (item.manifest_verified, RequestReason.MANIFEST_NOT_VERIFIED),
            (item.file_exists, RequestReason.FILE_MISSING),
            (
                _is_canonical_path(item.recorded_path)
                and _is_canonical_path(item.observed_path)
                and item.observed_path == item.recorded_path,
                RequestReason.PATH_INVALID_OR_MISMATCHED,
            ),
            (
                _is_sha256(item.recorded_checksum)
                and _is_sha256(item.recomputed_checksum)
                and item.recomputed_checksum == item.recorded_checksum,
                RequestReason.CHECKSUM_INVALID_OR_MISMATCHED,
            ),
            (
                _is_schema_version(item.recorded_schema_version)
                and _is_schema_version(item.observed_schema_version)
                and item.observed_schema_version == item.recorded_schema_version
                and item.recorded_schema_version == CANDLE_SCHEMA_VERSION
                and item.physical_compatible,
                RequestReason.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
            ),
            (
                type(item.recorded_from_date) is date
                and type(item.recorded_to_date) is date
                and item.recorded_from_date <= item.recorded_to_date
                and item.recorded_from_date == plan.from_date
                and item.recorded_to_date == plan.to_date,
                RequestReason.RECORDED_RANGE_MISMATCHED,
            ),
            (item.coverage_passed, RequestReason.COVERAGE_NOT_PASSED),
            (item.quality_passed, RequestReason.QUALITY_NOT_PASSED),
        )
        if not passed
    )
    if reasons:
        return PartitionDecision(plan, ReconciliationAction.REQUEST, reasons)
    return PartitionDecision(plan, ReconciliationAction.SKIP, ())


def _is_exact_bool_fields(*values: object) -> bool:
    return all(type(value) is bool for value in values)


def _has_evidence_runtime_types(value: object) -> bool:
    item = cast(PartitionEvidence, value)
    try:
        plan = item.plan
        manifest_verified = item.manifest_verified
        file_exists = item.file_exists
        recorded_path = item.recorded_path
        observed_path = item.observed_path
        recorded_checksum = item.recorded_checksum
        recomputed_checksum = item.recomputed_checksum
        recorded_schema_version = item.recorded_schema_version
        observed_schema_version = item.observed_schema_version
        physical_compatible = item.physical_compatible
        recorded_from_date = item.recorded_from_date
        recorded_to_date = item.recorded_to_date
        coverage_passed = item.coverage_passed
        quality_passed = item.quality_passed
    except AttributeError:
        return False
    return (
        type(plan) is PlannedInstrumentMonth
        and _is_exact_bool_fields(
            manifest_verified,
            file_exists,
            physical_compatible,
            coverage_passed,
            quality_passed,
        )
        and _is_optional_exact_string(recorded_path)
        and _is_optional_exact_string(observed_path)
        and _is_optional_exact_string(recorded_checksum)
        and _is_optional_exact_string(recomputed_checksum)
        and _is_optional_exact_int(recorded_schema_version)
        and _is_optional_exact_int(observed_schema_version)
        and _is_optional_exact_date(recorded_from_date)
        and _is_optional_exact_date(recorded_to_date)
    )


def _is_canonical_path(value: object) -> bool:
    if (
        type(value) is not str
        or not value
        or value.startswith("/")
        or ":" in value
        or "\\" in value
        or not value.isprintable()
    ):
        return False
    return all(
        part not in ("", ".", "..") and part == part.strip()
        for part in value.split("/")
    )


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_schema_version(value: object) -> bool:
    return type(value) is int and value > 0


def _is_optional_exact_string(value: object) -> bool:
    return value is None or type(value) is str


def _is_optional_exact_int(value: object) -> bool:
    return value is None or type(value) is int


def _is_optional_exact_date(value: object) -> bool:
    return value is None or type(value) is date


def _evidence_plan(evidence: PartitionEvidence) -> PlannedInstrumentMonth:
    try:
        return evidence.plan
    except AttributeError:
        raise ValueError("invalid planned partition") from None


def _partition_key(
    plan: object,
) -> tuple[str, str, str, str, str, str, int, int]:
    if type(plan) is not PlannedInstrumentMonth:
        raise ValueError("invalid planned partition")
    try:
        validated = PlannedInstrumentMonth(
            plan.provider,
            plan.instrument_key,
            plan.security_id,
            plan.symbol,
            plan.exchange,
            plan.segment,
            plan.instrument_type,
            plan.interval,
            plan.year,
            plan.month,
            plan.from_date,
            plan.to_date,
        )
    except Exception:
        raise ValueError("invalid planned partition") from None
    return (
        validated.provider,
        validated.exchange,
        validated.segment,
        validated.instrument_type,
        validated.security_id,
        validated.interval,
        validated.year,
        validated.month,
    )


def _is_valid_planned_partition(value: object) -> bool:
    try:
        _partition_key(value)
    except ValueError:
        return False
    return True


def _is_reason_declaration_order(reasons: tuple[RequestReason, ...]) -> bool:
    return tuple(sorted(reasons, key=lambda reason: _REASON_ORDER[reason])) == reasons


_REASON_ORDER = {reason: index for index, reason in enumerate(RequestReason)}
