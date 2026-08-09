"""Test-only Plan 03 B01--B05 baseline collection support."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, TypeVar

from ark90_benchmark_measurement import (
    ComparabilityIdentity,
    measure_b01,
    measure_benchmark_workload,
)

_WORKLOAD_IDS = ("B01", "B02", "B03", "B04", "B05")
_MEASURED_ITERATION_COUNT = 5


class BaselineIterationRecord(Protocol):
    """The sanitized fields needed to retain one measured workload result."""

    workload_id: str
    iteration_kind: str
    iteration_index: int
    outcome: str
    resource_evidence_status: str
    comparability_key: ComparabilityIdentity


RecordT = TypeVar("RecordT", bound=BaselineIterationRecord)
MeasureIteration = Callable[[str, str, int], RecordT]


class BaselineCollectionStatus(StrEnum):
    """Whether the retained set can later support threshold evaluation."""

    RETAINED = "RETAINED"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class BaselineWorkloadResult:
    """Raw ordered observations for one Plan 03 workload, without a threshold."""

    workload_id: str
    warmup: BaselineIterationRecord
    measured: tuple[BaselineIterationRecord, ...]
    status: BaselineCollectionStatus
    retained_measurement_count: int
    valid_measurement_count: int
    threshold_claim: None = None


@dataclass(frozen=True, slots=True)
class BaselineCollectionReport:
    """Raw evidence collected by ARK-92 for the five fixed workloads."""

    results: tuple[BaselineWorkloadResult, ...]


def collect_benchmark_baselines(disposable_parent: Path) -> BaselineCollectionReport:
    """Collect all fixed workloads through their real fresh-child measurements."""

    def measure(workload_id: str, kind: str, index: int) -> object:
        if workload_id == "B01":
            return measure_b01(
                disposable_parent, iteration_kind=kind, iteration_index=index
            )  # type: ignore[arg-type]
        return measure_benchmark_workload(
            disposable_parent,
            workload_id=workload_id,
            iteration_kind=kind,
            iteration_index=index,  # type: ignore[arg-type]
        )

    return collect_baseline_samples(disposable_parent, measure)


def collect_baseline_samples(
    disposable_parent: Path,
    measure_iteration: MeasureIteration[RecordT],
) -> BaselineCollectionReport:
    """Collect one warm-up plus five unreplaced measured observations per workload.

    The supplied measurement operation owns the required fresh-child invocation.
    This collector deliberately keeps every returned record in call order and
    assigns no statistical threshold: ARK-93 owns all comparisons and summaries.
    """
    disposable_parent.mkdir(parents=True, exist_ok=True)
    results = tuple(
        _collect_workload(workload_id, measure_iteration)
        for workload_id in _WORKLOAD_IDS
    )
    return BaselineCollectionReport(results)


def _collect_workload(
    workload_id: str, measure_iteration: MeasureIteration[RecordT]
) -> BaselineWorkloadResult:
    warmup = measure_iteration(workload_id, "warmup", 1)
    measured = tuple(
        measure_iteration(workload_id, "measured", iteration_index)
        for iteration_index in range(1, _MEASURED_ITERATION_COUNT + 1)
    )
    _validate_records(workload_id, warmup, measured)
    valid_records = tuple(record for record in measured if _is_valid_record(record))
    reference_key = valid_records[0].comparability_key if valid_records else None
    valid_count = sum(
        record.comparability_key == reference_key for record in valid_records
    )
    return BaselineWorkloadResult(
        workload_id,
        warmup,
        measured,
        (
            BaselineCollectionStatus.RETAINED
            if valid_count == _MEASURED_ITERATION_COUNT
            else BaselineCollectionStatus.INSUFFICIENT
        ),
        len(measured),
        valid_count,
    )


def _validate_records(
    workload_id: str,
    warmup: BaselineIterationRecord,
    measured: tuple[BaselineIterationRecord, ...],
) -> None:
    expected = (("warmup", 1),) + tuple(
        ("measured", index) for index in range(1, _MEASURED_ITERATION_COUNT + 1)
    )
    actual = ((warmup.iteration_kind, warmup.iteration_index),) + tuple(
        (record.iteration_kind, record.iteration_index) for record in measured
    )
    if (
        warmup.workload_id != workload_id
        or any(record.workload_id != workload_id for record in measured)
        or actual != expected
    ):
        raise ValueError("measurement record does not match its configured iteration")


def _is_valid_record(record: BaselineIterationRecord) -> bool:
    return (
        record.outcome == "SUCCEEDED"
        and record.resource_evidence_status == "VALID"
        and type(record.comparability_key) is ComparabilityIdentity
    )
