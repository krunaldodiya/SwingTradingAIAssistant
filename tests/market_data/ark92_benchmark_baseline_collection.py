"""Test-only Plan 03 B01--B05 baseline collection support."""

from __future__ import annotations

import argparse
import json
import math
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, TypeVar

from ark90_benchmark_measurement import (
    B01MeasurementRecord,
    BenchmarkCommandLimits,
    BenchmarkResourceLimits,
    ComparabilityIdentity,
    ResourceEvidenceStatus,
    SourceDataShape,
    _ControlPartitionEvidence,
    measure_b01,
    measure_benchmark_workload,
)

_WORKLOAD_IDS = ("B01", "B02", "B03", "B04", "B05")
_MEASURED_ITERATION_COUNT = 5
_ARTIFACT_SCHEMA_VERSION = "ark92-baseline-artifact-v1"
_ARTIFACTS_ROOT = Path(__file__).resolve().parents[2] / "artifacts"
_PHASE_FIELDS = frozenset(("normalize", "validate", "publish", "catalog", "query"))
_SENSITIVE_TEXT = (
    "authorization",
    "bearer ",
    "password",
    "secret",
    "token=",
    "raw-payload",
    "raw_payload",
    "raw_alias",
)
_NESTED_EVIDENCE_TYPES = (
    ComparabilityIdentity,
    SourceDataShape,
    BenchmarkCommandLimits,
    BenchmarkResourceLimits,
    _ControlPartitionEvidence,
)


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


def write_baseline_artifact(report: BaselineCollectionReport, output: Path) -> None:
    """Persist one complete sanitized report without replacing an existing artifact."""
    encoded = _serialize_report(report)
    _write_no_overwrite(output, encoded)


def main(argv: list[str] | None = None) -> int:
    """Collect once into an explicit new artifact and disposable work root."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    arguments = parser.parse_args(argv)
    output = _artifact_path(arguments.output, "output")
    work_root = _artifact_path(arguments.work_root, "work root")
    if output.exists():
        raise FileExistsError(f"baseline artifact already exists: {output}")
    if work_root.exists():
        raise FileExistsError(f"disposable work root already exists: {work_root}")
    if work_root == output.parent or work_root in output.parents:
        raise ValueError("output must not be inside the disposable work root")

    report = collect_benchmark_baselines(work_root)
    write_baseline_artifact(report, output)
    return 0


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


def _serialize_report(report: BaselineCollectionReport) -> bytes:
    if (
        type(report) is not BaselineCollectionReport
        or type(report.results) is not tuple
    ):
        raise ValueError("baseline report is incomplete")
    if tuple(result.workload_id for result in report.results) != _WORKLOAD_IDS:
        raise ValueError("baseline report has duplicate or missing workloads")
    payload = {
        "schema_version": _ARTIFACT_SCHEMA_VERSION,
        "results": [_serialize_workload(result) for result in report.results],
    }
    return (
        json.dumps(payload, allow_nan=False, ensure_ascii=True, sort_keys=True) + "\n"
    ).encode("utf-8")


def _serialize_workload(result: BaselineWorkloadResult) -> dict[str, object]:
    if type(result) is not BaselineWorkloadResult or type(result.measured) is not tuple:
        raise ValueError("baseline workload evidence is incomplete")
    if type(result.warmup) is not B01MeasurementRecord or any(
        type(record) is not B01MeasurementRecord for record in result.measured
    ):
        raise ValueError("measurement record has missing or extra fields")
    if len(result.measured) != _MEASURED_ITERATION_COUNT:
        raise ValueError("baseline workload has an incomplete measured set")
    _validate_records(result.workload_id, result.warmup, result.measured)
    valid_count = sum(_is_valid_record(record) for record in result.measured)
    expected_status = (
        BaselineCollectionStatus.RETAINED
        if valid_count == _MEASURED_ITERATION_COUNT
        else BaselineCollectionStatus.INSUFFICIENT
    )
    if (
        result.retained_measurement_count != _MEASURED_ITERATION_COUNT
        or result.valid_measurement_count != valid_count
        or result.status is not expected_status
        or result.threshold_claim is not None
    ):
        raise ValueError("baseline workload status is inconsistent")
    return {
        "workload_id": result.workload_id,
        "warmup": _serialize_record(result.warmup),
        "measured": [_serialize_record(record) for record in result.measured],
        "status": result.status.value,
        "retained_measurement_count": result.retained_measurement_count,
        "valid_measurement_count": result.valid_measurement_count,
        "threshold_claim": None,
    }


def _serialize_record(record: BaselineIterationRecord) -> dict[str, object]:
    if type(record) is not B01MeasurementRecord:
        raise ValueError("measurement record has missing or extra fields")
    expected_fields = tuple(B01MeasurementRecord.__dataclass_fields__)
    if tuple(field.name for field in fields(record)) != expected_fields:
        raise ValueError("measurement record has missing or extra fields")
    serialized: dict[str, object] = {}
    for field_name in expected_fields:
        value = getattr(record, field_name)
        serialized[field_name] = (
            _serialize_phase_elapsed(value)
            if field_name == "phase_elapsed_ms"
            else _serialize_value(value)
        )
    return serialized


def _serialize_phase_elapsed(value: object) -> dict[str, int | None]:
    if type(value) is not dict or set(value) != _PHASE_FIELDS:
        raise ValueError("phase timing evidence is incomplete")
    if any(item is not None and type(item) is not int for item in value.values()):
        raise ValueError("phase timing evidence is invalid")
    return {phase: value[phase] for phase in sorted(_PHASE_FIELDS)}


def _serialize_value(value: object) -> object:
    if isinstance(value, ResourceEvidenceStatus):
        return value.value
    if type(value) is str:
        lowered = value.lower()
        if (
            "/" in value
            or "\\" in value
            or any(marker in lowered for marker in _SENSITIVE_TEXT)
        ):
            raise ValueError("unsanitized path or secret evidence")
        return value
    if value is None or type(value) is bool or type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("nonfinite measurement evidence")
        return value
    if type(value) is tuple:
        return [_serialize_value(item) for item in value]
    if is_dataclass(value) and type(value) in _NESTED_EVIDENCE_TYPES:
        return {
            field.name: _serialize_value(getattr(value, field.name))
            for field in fields(value)
        }
    raise ValueError("unsupported or unsanitized measurement evidence")


def _write_no_overwrite(output: Path, encoded: bytes) -> None:
    if output.exists():
        raise FileExistsError(f"baseline artifact already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.parent / f".{output.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def _artifact_path(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=False)
    root = _ARTIFACTS_ROOT.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} must be under gitignored artifacts") from error
    return resolved


if __name__ == "__main__":
    raise SystemExit(main())
