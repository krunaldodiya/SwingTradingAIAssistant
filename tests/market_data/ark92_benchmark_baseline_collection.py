"""Test-only Plan 03 B01--B05 baseline collection support."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, fields
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
    "access_token",
    "access token",
    "api_key",
    "api-key",
    "cookie",
    "credential",
    "instrument_key",
    "instrument-key",
    "provider_alias",
    "provider-alias",
    "raw-payload",
    "raw_payload",
    "raw_alias",
)
_SQL_TEXT = re.compile(
    r"(?:^|[^a-z])(select|insert|update|delete|drop|alter|create|attach|detach|"
    r"pragma|vacuum|copy|union)(?:$|[^a-z])",
    re.IGNORECASE,
)
_SAFE_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+\-]*")
_SAFE_ENVIRONMENT_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:@+\-]*")
_SAFE_TIMEZONE = re.compile(r"[A-Za-z]+/[A-Za-z_]+")
_RFC3339_MICROSECONDS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z")
_REQUESTED_RANGE = re.compile(r"\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}")
_HEX_40 = re.compile(r"[0-9a-f]{40}")
_HEX_64 = re.compile(r"[0-9a-f]{64}")
_PHYSICAL_MONTH_COUNTS = {"B01": 1, "B02": 3, "B03": 1, "B04": 1, "B05": 12}
_PHYSICAL_MONTHS = {
    "B01": ((2024, 2),),
    "B02": ((2024, 1), (2024, 2), (2024, 3)),
    "B03": ((2024, 2),),
    "B04": ((2024, 2),),
    "B05": tuple((2023, month) for month in range(1, 13)),
}
_SUCCESS_WORKLOAD_EVIDENCE = {
    "B01": (("VERIFIED",), (), (1, 1, 0, 0, 0)),
    "B02": (
        ("SKIPPED_VERIFIED", "SKIPPED_VERIFIED", "RECOVERED_LOCALLY"),
        (),
        (0, 0, 0, 3, 0),
    ),
    "B03": (("VERIFIED",), ("CHECKSUM_INVALID_OR_MISMATCHED",), (1, 1, 0, 0, 1)),
    "B04": ((), (), (0, 0, 0, 0, 0)),
    "B05": ((), (), (0, 0, 0, 0, 0)),
}
_FAILURE_CODES = frozenset(
    (
        "B01_CHILD_FAILED",
        "BENCHMARK_CHILD_CANCELLED",
        "BENCHMARK_CHILD_FAILED",
        "BENCHMARK_CHILD_PROTOCOL_INVALID",
        "CHILD_PROTOCOL_INVALID",
    )
)
_PARTITION_OUTCOMES = frozenset(("VERIFIED", "SKIPPED_VERIFIED", "RECOVERED_LOCALLY"))
_RECONCILIATION_REASONS = frozenset(("CHECKSUM_INVALID_OR_MISMATCHED",))
_RESOURCE_BLOCKERS = frozenset(
    (
        "sampling_exception",
        "unsupported_num_fds",
        "loop_sampling_exception",
        "too_few_samples",
        "max_gap_exceeded",
        "open_fd_not_closed",
        "CHILD_PROTOCOL_INVALID",
    )
)
_URI_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")


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


class _ArtifactCliFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


class _ArtifactArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise _ArtifactCliFailure("INVALID_ARGUMENTS")


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
    parser = _ArtifactArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    work_root_fd: int | None = None
    try:
        arguments = parser.parse_args(argv)
        output = _artifact_path(arguments.output, "output")
        work_root = _artifact_path(arguments.work_root, "work root")
        if output.exists():
            raise _ArtifactCliFailure("OUTPUT_EXISTS")
        if _paths_overlap(output, work_root):
            raise _ArtifactCliFailure("OUTPUT_WORK_ROOT_OVERLAP")
        if work_root.exists():
            raise _ArtifactCliFailure("WORK_ROOT_EXISTS")
        work_root_fd = _open_artifact_directory(work_root)
        report = collect_benchmark_baselines(work_root)
        if not _path_matches_directory_descriptor(work_root, work_root_fd):
            raise _ArtifactCliFailure("WORK_ROOT_SUBSTITUTED")
        write_baseline_artifact(report, output)
    except _ArtifactCliFailure as error:
        print(f"baseline artifact collection failed: {error.code}", file=sys.stderr)
        return 2
    except (ValueError, FileExistsError, OSError):
        print(
            "baseline artifact collection failed: PERSISTENCE_FAILED", file=sys.stderr
        )
        return 2
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        print("baseline artifact collection failed: COLLECTION_FAILED", file=sys.stderr)
        return 2
    finally:
        if work_root_fd is not None:
            os.close(work_root_fd)
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
    valid_count = _comparable_valid_count(measured)
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


def _comparable_valid_count(records: tuple[BaselineIterationRecord, ...]) -> int:
    valid_records = tuple(record for record in records if _is_valid_record(record))
    reference_key = valid_records[0].comparability_key if valid_records else None
    return sum(record.comparability_key == reference_key for record in valid_records)


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
    valid_count = _comparable_valid_count(result.measured)
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
    _validate_record_identity(record)
    _validate_record_contract(record)
    return {
        "workload_id": _serialize_workload_id(record.workload_id),
        "iteration_kind": _serialize_iteration_kind(record.iteration_kind),
        "iteration_index": _serialize_positive_int(record.iteration_index),
        "source_revision": _serialize_hex(record.source_revision, _HEX_40),
        "source_tree": _serialize_hex(record.source_tree, _HEX_40),
        "lock_identity": _serialize_hex(record.lock_identity, _HEX_64),
        "python_version": _serialize_label(record.python_version),
        "platform": _serialize_environment_text(record.platform),
        "cpu_model": _serialize_environment_text(record.cpu_model),
        "cpu_count": _serialize_positive_int(record.cpu_count),
        "memory_total_bytes": _serialize_nonnegative_int(record.memory_total_bytes),
        "filesystem_type": _serialize_label(record.filesystem_type),
        "duckdb_version": _serialize_label(record.duckdb_version),
        "pyarrow_version": _serialize_label(record.pyarrow_version),
        "os_version": _serialize_environment_text(record.os_version),
        "fixture_id": _serialize_label(record.fixture_id),
        "fixture_version": _serialize_label(record.fixture_version),
        "schedule_digest": _serialize_hex(record.schedule_digest, _HEX_64),
        "policy_version": _serialize_label(record.policy_version),
        "requested_range": _serialize_requested_range(record.requested_range),
        "physical_month_count": _serialize_nonnegative_int(record.physical_month_count),
        "partition_checksums": _serialize_partition_checksums(
            record.partition_checksums
        ),
        "elapsed_wall_ms": _serialize_nonnegative_int(record.elapsed_wall_ms),
        "elapsed_cpu_ms": _serialize_nonnegative_int(record.elapsed_cpu_ms),
        "phase_elapsed_ms": _serialize_phase_elapsed(record.phase_elapsed_ms),
        "rows_raw": _serialize_nonnegative_int(record.rows_raw),
        "rows_normalized": _serialize_nonnegative_int(record.rows_normalized),
        "rows_published": _serialize_nonnegative_int(record.rows_published),
        "bytes_parquet": _serialize_nonnegative_int(record.bytes_parquet),
        "throughput_rows_per_s": _serialize_optional_nonnegative_float(
            record.throughput_rows_per_s
        ),
        "request_count": _serialize_nonnegative_int(record.request_count),
        "provider_attempt_count": _serialize_nonnegative_int(
            record.provider_attempt_count
        ),
        "retry_count": _serialize_nonnegative_int(record.retry_count),
        "resume_count": _serialize_nonnegative_int(record.resume_count),
        "repair_count": _serialize_nonnegative_int(record.repair_count),
        "peak_rss_bytes": _serialize_optional_nonnegative_int(record.peak_rss_bytes),
        "open_fd_start": _serialize_optional_nonnegative_int(record.open_fd_start),
        "open_fd_peak": _serialize_optional_nonnegative_int(record.open_fd_peak),
        "open_fd_end": _serialize_optional_nonnegative_int(record.open_fd_end),
        "sampler_method": _serialize_label(record.sampler_method),
        "psutil_version": _serialize_label(record.psutil_version),
        "sampler_sample_count": _serialize_nonnegative_int(record.sampler_sample_count),
        "sampler_max_gap_ms": _serialize_optional_nonnegative_int(
            record.sampler_max_gap_ms
        ),
        "resource_evidence_status": _serialize_resource_status(
            record.resource_evidence_status
        ),
        "resource_blocker": _serialize_optional_label(record.resource_blocker),
        "query_result_count": _serialize_optional_nonnegative_int(
            record.query_result_count
        ),
        "query_min_ts": _serialize_optional_timestamp(record.query_min_ts),
        "query_max_ts": _serialize_optional_timestamp(record.query_max_ts),
        "query_elapsed_ms": _serialize_optional_nonnegative_int(
            record.query_elapsed_ms
        ),
        "outcome": _serialize_outcome(record.outcome),
        "failure_code": _serialize_outcome(record.failure_code),
        "partition_outcomes": _serialize_labels(record.partition_outcomes),
        "reconciliation_reasons": _serialize_labels(record.reconciliation_reasons),
        "control_partition_evidence": _serialize_control_partition_evidence(
            record.control_partition_evidence
        ),
        "comparability_key": _serialize_comparability_identity(
            record.comparability_key
        ),
    }


def _validate_record_identity(record: B01MeasurementRecord) -> None:
    key = record.comparability_key
    if type(key) is not ComparabilityIdentity:
        raise ValueError("measurement comparability identity is invalid")
    if (
        type(key.source_data_shape) is not SourceDataShape
        or type(key.command_limits) is not BenchmarkCommandLimits
        or type(key.resource_limits) is not BenchmarkResourceLimits
    ):
        raise ValueError("measurement comparability identity is invalid")
    direct_pairs = (
        (record.workload_id, key.workload_id),
        (record.fixture_id, key.fixture_id),
        (record.fixture_version, key.fixture_version),
        (record.source_revision, key.source_revision),
        (record.source_tree, key.source_tree),
        (record.lock_identity, key.lock_identity),
        (record.schedule_digest, key.schedule_digest),
        (record.policy_version, key.policy_version),
        (record.requested_range, key.requested_range),
        (record.partition_checksums, key.partition_checksums),
        (record.rows_raw, key.source_data_shape.rows_raw),
        (record.rows_normalized, key.source_data_shape.rows_normalized),
        (record.rows_published, key.source_data_shape.rows_published),
        (record.bytes_parquet, key.source_data_shape.bytes_parquet),
        (record.cpu_count, key.cpu_count),
        (record.filesystem_type, key.filesystem_type),
        (record.sampler_method, key.sampler_method),
        (record.psutil_version, key.psutil_version),
    )
    if any(left != right for left, right in direct_pairs):
        raise ValueError("measurement record contradicts comparability identity")


def _validate_record_contract(record: B01MeasurementRecord) -> None:
    key = record.comparability_key
    if (
        record.cpu_model != key.cpu_architecture
        or _major_minor(record.python_version) != key.python_major_minor
        or _major_minor(record.pyarrow_version) != key.pyarrow_major_minor
        or _major_minor(record.duckdb_version) != key.duckdb_major_minor
    ):
        raise ValueError("measurement record contradicts comparability identity")
    _validate_physical_shape(record)
    _validate_resource_evidence(record)
    _validate_terminal_evidence(record)
    _validate_control_evidence(record)


def _major_minor(value: object) -> str:
    if type(value) is not str:
        raise ValueError("invalid version evidence")
    matched = re.fullmatch(r"(\d+)\.(\d+)(?:\.\d+)?", value)
    if matched is None:
        raise ValueError("invalid version evidence")
    return f"{matched.group(1)}.{matched.group(2)}"


def _validate_physical_shape(record: B01MeasurementRecord) -> None:
    expected_count = _PHYSICAL_MONTH_COUNTS.get(record.workload_id)
    if expected_count is None or type(record.physical_month_count) is not int:
        raise ValueError("invalid physical workload evidence")
    if record.physical_month_count != expected_count:
        raise ValueError("invalid physical workload evidence")
    checksums = record.partition_checksums
    if type(checksums) is not tuple:
        raise ValueError("invalid physical workload evidence")
    if any(type(item) is not tuple or len(item) != 3 for item in checksums):
        raise ValueError("invalid physical workload evidence")
    months = tuple((item[0], item[1]) for item in checksums)
    if any(
        type(year) is not int or type(month) is not int for year, month in months
    ) or months != tuple(sorted(months)):
        raise ValueError("invalid physical workload evidence")
    if len(set(months)) != len(months):
        raise ValueError("invalid physical workload evidence")
    expected_months = _PHYSICAL_MONTHS[record.workload_id]
    if record.outcome == "SUCCEEDED" and months != expected_months:
        raise ValueError("invalid physical workload evidence")
    if record.outcome != "SUCCEEDED" and months not in ((), expected_months):
        raise ValueError("invalid terminal workload evidence")


def _validate_resource_evidence(record: B01MeasurementRecord) -> None:
    key = record.comparability_key.resource_limits
    if type(record.resource_evidence_status) is not ResourceEvidenceStatus:
        raise ValueError("invalid resource evidence status")
    if record.resource_evidence_status is ResourceEvidenceStatus.VALID:
        fields_to_require = (
            record.peak_rss_bytes,
            record.open_fd_start,
            record.open_fd_peak,
            record.open_fd_end,
            record.sampler_max_gap_ms,
        )
        if any(value is None for value in fields_to_require):
            raise ValueError("valid resource evidence is incomplete")
        if (
            record.resource_blocker is not None
            or record.sampler_sample_count < key.minimum_sampler_samples
            or record.sampler_max_gap_ms > key.max_sampling_gap_ms  # type: ignore[operator]
            or record.open_fd_start != record.open_fd_end
            or record.open_fd_peak < record.open_fd_start  # type: ignore[operator]
            or record.open_fd_peak < record.open_fd_end  # type: ignore[operator]
        ):
            raise ValueError("valid resource evidence is inconsistent")
        return
    if record.resource_blocker not in _RESOURCE_BLOCKERS or any(
        value is not None
        for value in (
            record.peak_rss_bytes,
            record.open_fd_start,
            record.open_fd_peak,
            record.open_fd_end,
        )
    ):
        raise ValueError("invalid resource evidence is inconsistent")


def _validate_terminal_evidence(record: B01MeasurementRecord) -> None:
    if record.outcome not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
        raise ValueError("invalid terminal outcome")
    if (record.outcome == "SUCCEEDED") != (record.failure_code == "NONE"):
        raise ValueError("invalid terminal outcome")
    if record.outcome != "SUCCEEDED" and record.failure_code not in _FAILURE_CODES:
        raise ValueError("invalid terminal outcome")
    if (
        type(record.partition_outcomes) is not tuple
        or any(value not in _PARTITION_OUTCOMES for value in record.partition_outcomes)
        or type(record.reconciliation_reasons) is not tuple
        or any(
            value not in _RECONCILIATION_REASONS
            for value in record.reconciliation_reasons
        )
    ):
        raise ValueError("invalid terminal evidence")
    if record.outcome == "SUCCEEDED":
        outcomes, reasons, counts = _SUCCESS_WORKLOAD_EVIDENCE[record.workload_id]
        if (
            record.partition_outcomes != outcomes
            or record.reconciliation_reasons != reasons
            or (
                record.request_count,
                record.provider_attempt_count,
                record.retry_count,
                record.resume_count,
                record.repair_count,
            )
            != counts
        ):
            raise ValueError("invalid successful workload evidence")


def _validate_control_evidence(record: B01MeasurementRecord) -> None:
    evidence = record.control_partition_evidence
    if record.workload_id != "B03":
        if evidence is not None:
            raise ValueError("control evidence is only valid for B03")
        return
    if record.outcome != "SUCCEEDED":
        if evidence is not None:
            raise ValueError("terminal B03 evidence must be incomplete")
        return
    if type(evidence) is not _ControlPartitionEvidence:
        raise ValueError("successful B03 evidence requires a control")
    identity = evidence.physical_identity
    if (
        type(identity) is not tuple
        or len(identity) != 8
        or any(type(value) is not str for value in identity[:6])
        or type(identity[6]) is not int
        or type(identity[7]) is not int
        or evidence.pre_physical_checksum != evidence.post_physical_checksum
        or evidence.pre_manifest_fingerprint != evidence.post_manifest_fingerprint
    ):
        raise ValueError("invalid B03 control evidence")


def _serialize_phase_elapsed(value: object) -> dict[str, int | None]:
    if type(value) is not dict or set(value) != _PHASE_FIELDS:
        raise ValueError("phase timing evidence is incomplete")
    if any(
        item is not None and (type(item) is not int or item < 0)
        for item in value.values()
    ):
        raise ValueError("phase timing evidence is invalid")
    return {phase: value[phase] for phase in sorted(_PHASE_FIELDS)}


def _serialize_workload_id(value: object) -> str:
    if type(value) is not str or value not in _WORKLOAD_IDS:
        raise ValueError("unsanitized workload evidence")
    return value


def _serialize_iteration_kind(value: object) -> str:
    if value not in {"warmup", "measured"}:
        raise ValueError("unsanitized iteration evidence")
    return value


def _serialize_outcome(value: object) -> str:
    if type(value) is not str or not re.fullmatch(r"[A-Z0-9_]+", value):
        raise ValueError("unsanitized outcome evidence")
    return value


def _serialize_label(value: object) -> str:
    if type(value) is not str or not _SAFE_LABEL.fullmatch(value):
        raise ValueError("unsanitized label evidence")
    _reject_sensitive_text(value)
    return value


def _serialize_timezone(value: object) -> str:
    if type(value) is not str or not _SAFE_TIMEZONE.fullmatch(value):
        raise ValueError("unsanitized timezone evidence")
    _reject_sensitive_text(value, allow_timezone_separator=True)
    return value


def _serialize_environment_text(value: object) -> str:
    if type(value) is not str or not _SAFE_ENVIRONMENT_TEXT.fullmatch(value):
        raise ValueError("unsanitized environment evidence")
    _reject_sensitive_text(value)
    return value


def _reject_sensitive_text(
    value: str, *, allow_timezone_separator: bool = False
) -> None:
    lowered = value.lower()
    normalized = re.sub(r"[^a-z0-9]", "", lowered)
    if (
        _URI_SCHEME.search(value) is not None
        or ("/" in value and not allow_timezone_separator)
        or "\\" in value
        or "|" in value
        or any(marker in lowered for marker in _SENSITIVE_TEXT)
        or any(
            marker in normalized
            for marker in (
                "authorization",
                "bearer",
                "password",
                "secret",
                "token",
                "accesstoken",
                "apikey",
                "cookie",
                "credential",
                "instrumentkey",
                "provideralias",
                "rawpayload",
                "rawalias",
            )
        )
        or _SQL_TEXT.search(value) is not None
    ):
        raise ValueError("unsanitized path or secret evidence")


def _serialize_hex(value: object, expected: re.Pattern[str]) -> str:
    if type(value) is not str or not expected.fullmatch(value):
        raise ValueError("unsanitized digest evidence")
    return value


def _serialize_requested_range(value: object) -> str:
    if type(value) is not str or not _REQUESTED_RANGE.fullmatch(value):
        raise ValueError("unsanitized range evidence")
    return value


def _serialize_timestamp(value: object) -> str:
    if type(value) is not str or not _RFC3339_MICROSECONDS.fullmatch(value):
        raise ValueError("unsanitized timestamp evidence")
    return value


def _serialize_optional_timestamp(value: object) -> str | None:
    return None if value is None else _serialize_timestamp(value)


def _serialize_nonnegative_int(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("invalid numeric measurement evidence")
    return value


def _serialize_positive_int(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("invalid numeric measurement evidence")
    return value


def _serialize_optional_nonnegative_int(value: object) -> int | None:
    return None if value is None else _serialize_nonnegative_int(value)


def _serialize_optional_nonnegative_float(value: object) -> float | None:
    if value is None:
        return None
    if type(value) is not float or not math.isfinite(value) or value < 0:
        raise ValueError("nonfinite measurement evidence")
    return value


def _serialize_resource_status(value: object) -> str:
    if type(value) is not ResourceEvidenceStatus:
        raise ValueError("invalid resource evidence status")
    return value.value


def _serialize_optional_label(value: object) -> str | None:
    return None if value is None else _serialize_label(value)


def _serialize_labels(value: object) -> list[str]:
    if type(value) is not tuple:
        raise ValueError("unsanitized ordered evidence")
    return [_serialize_outcome(item) for item in value]


def _serialize_label_tuple(value: object) -> list[str]:
    if type(value) is not tuple:
        raise ValueError("unsanitized ordered evidence")
    return [_serialize_label(item) for item in value]


def _serialize_partition_checksums(value: object) -> list[list[int | str]]:
    if type(value) is not tuple:
        raise ValueError("unsanitized partition checksum evidence")
    serialized: list[list[int | str]] = []
    for item in value:
        if type(item) is not tuple or len(item) != 3:
            raise ValueError("unsanitized partition checksum evidence")
        year, month, checksum = item
        if type(year) is not int or type(month) is not int or not 1 <= month <= 12:
            raise ValueError("unsanitized partition checksum evidence")
        serialized.append([year, month, _serialize_hex(checksum, _HEX_64)])
    return serialized


def _serialize_source_data_shape(value: object) -> dict[str, int]:
    if type(value) is not SourceDataShape:
        raise ValueError("measurement comparability identity is invalid")
    return {
        "rows_raw": _serialize_nonnegative_int(value.rows_raw),
        "rows_normalized": _serialize_nonnegative_int(value.rows_normalized),
        "rows_published": _serialize_nonnegative_int(value.rows_published),
        "bytes_parquet": _serialize_nonnegative_int(value.bytes_parquet),
    }


def _serialize_command_limits(value: object) -> dict[str, int | str]:
    if type(value) is not BenchmarkCommandLimits:
        raise ValueError("measurement comparability identity is invalid")
    return {
        "interval": _serialize_label(value.interval),
        "max_attempts_per_partition": _serialize_positive_int(
            value.max_attempts_per_partition
        ),
        "max_total_provider_attempts": _serialize_nonnegative_int(
            value.max_total_provider_attempts
        ),
        "base_backoff_ms": _serialize_nonnegative_int(value.base_backoff_ms),
        "max_backoff_ms": _serialize_nonnegative_int(value.max_backoff_ms),
        "max_retry_after_ms": _serialize_nonnegative_int(value.max_retry_after_ms),
        "max_total_wait_ms": _serialize_nonnegative_int(value.max_total_wait_ms),
        "query_connection_count": _serialize_positive_int(value.query_connection_count),
        "query_threads": _serialize_positive_int(value.query_threads),
        "query_memory_limit_bytes": _serialize_positive_int(
            value.query_memory_limit_bytes
        ),
    }


def _serialize_resource_limits(value: object) -> dict[str, float | int | str]:
    if type(value) is not BenchmarkResourceLimits:
        raise ValueError("measurement comparability identity is invalid")
    timeout = value.child_control_timeout_s
    if type(timeout) is not float or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("invalid resource limit evidence")
    return {
        "child_control_timeout_s": timeout,
        "sampling_interval_ms": _serialize_positive_int(value.sampling_interval_ms),
        "max_sampling_gap_ms": _serialize_positive_int(value.max_sampling_gap_ms),
        "minimum_sampler_samples": _serialize_positive_int(
            value.minimum_sampler_samples
        ),
        "fd_closure_rule": _serialize_label(value.fd_closure_rule),
    }


def _serialize_control_partition_evidence(
    value: object,
) -> dict[str, object] | None:
    if value is None:
        return None
    if (
        type(value) is not _ControlPartitionEvidence
        or type(value.physical_identity) is not tuple
    ):
        raise ValueError("unsanitized control partition evidence")
    physical_identity = []
    for item in value.physical_identity:
        if type(item) is int:
            physical_identity.append(_serialize_nonnegative_int(item))
        else:
            physical_identity.append(_serialize_label(item))
    return {
        "physical_identity": physical_identity,
        "pre_physical_checksum": _serialize_hex(value.pre_physical_checksum, _HEX_64),
        "post_physical_checksum": _serialize_hex(value.post_physical_checksum, _HEX_64),
        "pre_manifest_fingerprint": _serialize_hex(
            value.pre_manifest_fingerprint, _HEX_64
        ),
        "post_manifest_fingerprint": _serialize_hex(
            value.post_manifest_fingerprint, _HEX_64
        ),
        "manifest_bound_schedule_digest": _serialize_hex(
            value.manifest_bound_schedule_digest, _HEX_64
        ),
    }


def _serialize_comparability_identity(value: object) -> dict[str, object]:
    if type(value) is not ComparabilityIdentity:
        raise ValueError("measurement comparability identity is invalid")
    return {
        "workload_id": _serialize_workload_id(value.workload_id),
        "fixture_id": _serialize_label(value.fixture_id),
        "fixture_version": _serialize_label(value.fixture_version),
        "source_revision": _serialize_hex(value.source_revision, _HEX_40),
        "source_tree": _serialize_hex(value.source_tree, _HEX_40),
        "lock_identity": _serialize_hex(value.lock_identity, _HEX_64),
        "schedule_digest": _serialize_hex(value.schedule_digest, _HEX_64),
        "requested_range": _serialize_requested_range(value.requested_range),
        "schedule_as_of": _serialize_timestamp(value.schedule_as_of),
        "schedule_source": _serialize_label(value.schedule_source),
        "schedule_release": _serialize_label(value.schedule_release),
        "schedule_timezone": _serialize_timezone(value.schedule_timezone),
        "schedule_kind_provenance": _serialize_label_tuple(
            value.schedule_kind_provenance
        ),
        "schedule_closure_provenance": _serialize_schedule_closures(
            value.schedule_closure_provenance
        ),
        "policy_version": _serialize_label(value.policy_version),
        "partition_checksums": _serialize_partition_checksums(
            value.partition_checksums
        ),
        "source_data_shape": _serialize_source_data_shape(value.source_data_shape),
        "command_limits": _serialize_command_limits(value.command_limits),
        "resource_limits": _serialize_resource_limits(value.resource_limits),
        "measurement_method": _serialize_label(value.measurement_method),
        "python_major_minor": _serialize_label(value.python_major_minor),
        "pyarrow_major_minor": _serialize_label(value.pyarrow_major_minor),
        "duckdb_major_minor": _serialize_label(value.duckdb_major_minor),
        "psutil_version": _serialize_label(value.psutil_version),
        "sampler_method": _serialize_label(value.sampler_method),
        "cpu_architecture": _serialize_label(value.cpu_architecture),
        "cpu_count": _serialize_positive_int(value.cpu_count),
        "filesystem_type": _serialize_label(value.filesystem_type),
    }


def _serialize_schedule_closures(value: object) -> list[list[str]]:
    if type(value) is not tuple:
        raise ValueError("unsanitized schedule closure evidence")
    serialized: list[list[str]] = []
    for item in value:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError("unsanitized schedule closure evidence")
        serialized.append([_serialize_label(item[0]), _serialize_label(item[1])])
    return serialized


def _write_no_overwrite(output: Path, encoded: bytes) -> None:
    directory_fd = _open_artifact_directory(output.parent)
    temporary_name = f".{output.name}.{uuid.uuid4().hex}.tmp"
    try:
        _ensure_absent(output.name, directory_fd)
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        try:
            _write_temporary_fd(temporary_fd, encoded)
        finally:
            os.close(temporary_fd)
        os.link(
            temporary_name,
            output.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        os.fsync(directory_fd)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary_name, dir_fd=directory_fd)
        os.close(directory_fd)


def _open_artifact_directory(directory: Path) -> int:
    absolute = Path(os.path.abspath(directory))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for component in absolute.parts[1:]:
            try:
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(component, 0o700, dir_fd=descriptor)
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _path_matches_directory_descriptor(path: Path, descriptor: int) -> bool:
    try:
        current = os.stat(path)
    except OSError:
        return False
    held = os.fstat(descriptor)
    return (current.st_dev, current.st_ino) == (held.st_dev, held.st_ino)


def _ensure_absent(name: str, directory_fd: int) -> None:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise FileExistsError("baseline artifact already exists")


def _write_temporary_fd(descriptor: int, encoded: bytes) -> None:
    written = 0
    while written < len(encoded):
        written += os.write(descriptor, encoded[written:])
    os.fsync(descriptor)


def _artifact_path(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=False)
    root = _ARTIFACTS_ROOT.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} must be under gitignored artifacts") from error
    return resolved


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


if __name__ == "__main__":
    raise SystemExit(main())
