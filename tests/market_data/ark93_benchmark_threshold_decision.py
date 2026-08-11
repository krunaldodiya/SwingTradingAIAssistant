"""Derive the frozen Plan 03 regression thresholds from retained evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast

from ark92_benchmark_baseline_collection import (
    ArtifactReceiptV1,
    B03MeasurementErrorRepairReceiptV1,
    _artifact_path,
    _ArtifactCliFailure,
    _capture_source_identity,
    _deserialize_report,
    _expected_source_identity,
    _path_entry_exists,
    _publish_no_overwrite,
    _serialize_receipt,
    _source_identity_matches,
    _verify_loaded_module_snapshot,
    read_b03_measurement_error_repair,
    read_baseline_artifact,
)

_DECISION_SCHEMA_VERSION = "ark93-threshold-decision-v1"
_DECISION_RECEIPT_SCHEMA_VERSION = "ark93-threshold-decision-receipt-v1"
_BASE_RECEIPT = ArtifactReceiptV1(
    "ark92-baseline-receipt-v1",
    220_934,
    "1b69e0f4b70983582e889ef22be4c5dcb9051985b001be46ac305a87c86bd755",
)
_B03_REPAIR_RECEIPT = B03MeasurementErrorRepairReceiptV1(
    "ark92-b03-measurement-error-repair-receipt-v1",
    30_641,
    "d64cf2e3a971c052e70975571efb60d336469e24ef1080f1ab441615e67f884c",
)


class ThresholdStatusV1(StrEnum):
    THRESHOLD_ACCEPTED = "THRESHOLD_ACCEPTED"
    UNSET = "UNSET"


class ThresholdRecord(Protocol):
    outcome: str
    resource_evidence_status: object
    comparability_key: object
    elapsed_wall_ms: int
    phase_elapsed_ms: object
    throughput_rows_per_s: float | None
    peak_rss_bytes: int | None
    open_fd_start: int | None
    open_fd_peak: int | None
    open_fd_end: int | None
    query_elapsed_ms: int | None


class Receipt(Protocol):
    schema_version: str
    byte_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class MetricThresholdV1:
    metric: str
    direction: str
    sorted_values: tuple[int | float, ...]
    minimum: int | float
    median: int | float
    maximum: int | float
    spread: int | float
    stable: bool
    threshold: int | float | None


@dataclass(frozen=True, slots=True)
class WorkloadThresholdDecisionV1:
    workload_id: str
    evidence_source: str
    status: ThresholdStatusV1
    metrics: tuple[MetricThresholdV1, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkThresholdDecisionV1:
    decision_revision: str
    decision_tree: str
    b03_original_status: str
    results: tuple[WorkloadThresholdDecisionV1, ...]


@dataclass(frozen=True, slots=True)
class DecisionReceiptV1:
    schema_version: str
    byte_count: int
    sha256: str


def summarize_values(
    metric: str,
    values: tuple[int | float, ...],
    direction: str,
) -> MetricThresholdV1:
    """Apply Plan 03's exact five-value median/spread threshold rule."""
    if (
        type(metric) is not str
        or not metric
        or direction not in {"LOWER", "HIGHER"}
        or type(values) is not tuple
        or len(values) != 5
        or any(type(value) not in {int, float} or value < 0 for value in values)
    ):
        raise ValueError("invalid threshold values")
    ordered = tuple(sorted(values))
    minimum, median, maximum = ordered[0], ordered[2], ordered[4]
    spread = ordered[3] - ordered[1]
    stable = (median == 0 and spread == 0) or (median > 0 and spread <= median)
    threshold: int | float | None = None
    if stable:
        threshold = (
            median + 3 * spread if direction == "LOWER" else max(0, median - 3 * spread)
        )
    return MetricThresholdV1(
        metric,
        direction,
        ordered,
        minimum,
        median,
        maximum,
        spread,
        stable,
        threshold,
    )


def derive_workload_threshold(
    workload_id: str,
    records: tuple[ThresholdRecord, ...],
    evidence_source: str,
) -> WorkloadThresholdDecisionV1:
    """Derive all applicable local metrics, or deterministically return UNSET."""
    if workload_id not in {"B01", "B02", "B03", "B04", "B05"}:
        raise ValueError("invalid workload")
    if evidence_source not in {"BASELINE", "B03_REPAIR"}:
        raise ValueError("invalid evidence source")
    if not _records_are_eligible(records):
        return WorkloadThresholdDecisionV1(
            workload_id, evidence_source, ThresholdStatusV1.UNSET, ()
        )
    try:
        metrics = _summaries(records)
    except ValueError:
        return WorkloadThresholdDecisionV1(
            workload_id, evidence_source, ThresholdStatusV1.UNSET, ()
        )
    status = (
        ThresholdStatusV1.THRESHOLD_ACCEPTED
        if metrics and all(metric.stable for metric in metrics)
        else ThresholdStatusV1.UNSET
    )
    return WorkloadThresholdDecisionV1(workload_id, evidence_source, status, metrics)


def derive_threshold_decision(
    base_path: Path,
    repair_path: Path,
    *,
    decision_revision: str,
    decision_tree: str,
) -> BenchmarkThresholdDecisionV1:
    """Authenticate both retained artifacts and derive all five workload decisions."""
    base_payload = read_baseline_artifact(base_path, _BASE_RECEIPT)
    base = _deserialize_report(base_payload)
    repair = read_b03_measurement_error_repair(
        repair_path, _B03_REPAIR_RECEIPT, base_path, _BASE_RECEIPT
    )
    selected = (
        base.results[0],
        base.results[1],
        repair.result,
        base.results[3],
        base.results[4],
    )
    decisions = tuple(
        derive_workload_threshold(
            result.workload_id,
            cast(tuple[ThresholdRecord, ...], result.measured),
            "B03_REPAIR" if result.workload_id == "B03" else "BASELINE",
        )
        for result in selected
    )
    return BenchmarkThresholdDecisionV1(
        decision_revision,
        decision_tree,
        "MEASUREMENT_ERROR_RETAINED",
        decisions,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-artifact", type=Path, required=True)
    parser.add_argument("--b03-repair-artifact", type=Path, required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--expected-tree", required=True)
    try:
        arguments = parser.parse_args(argv)
        output = _artifact_path(arguments.output, "output")
        base_path = _artifact_path(arguments.base_artifact, "base artifact")
        repair_path = _artifact_path(
            arguments.b03_repair_artifact, "B03 repair artifact"
        )
        if _path_entry_exists(output):
            raise ValueError("threshold decision already exists")
        expected = _expected_source_identity(
            arguments.expected_revision, arguments.expected_tree
        )
        actual = _capture_source_identity()
        if actual != expected or not _source_identity_matches(actual):
            raise ValueError("threshold source mismatch")
        _verify_loaded_module_snapshot(actual)
        decision = derive_threshold_decision(
            base_path,
            repair_path,
            decision_revision=actual.revision,
            decision_tree=actual.tree,
        )
        encoded = _serialize_decision(decision)
        if not _source_identity_matches(actual):
            raise ValueError("threshold source changed")
        byte_count, sha256 = _publish_no_overwrite(output, encoded)
        receipt = DecisionReceiptV1(
            _DECISION_RECEIPT_SCHEMA_VERSION, byte_count, sha256
        )
        print(_serialize_receipt(receipt))  # type: ignore[arg-type]
        return 0
    except _ArtifactCliFailure:
        print("threshold decision failed: SOURCE_ADMISSION_FAILED", file=sys.stderr)
        return 2
    except (ValueError, OSError):
        print("threshold decision failed: EVIDENCE_INVALID", file=sys.stderr)
        return 2


def _serialize_decision(decision: BenchmarkThresholdDecisionV1) -> bytes:
    payload = {
        "schema_version": _DECISION_SCHEMA_VERSION,
        "decision_revision": decision.decision_revision,
        "decision_tree": decision.decision_tree,
        "base_receipt": _receipt_payload(_BASE_RECEIPT),
        "b03_repair_receipt": _receipt_payload(_B03_REPAIR_RECEIPT),
        "b03_original_status": decision.b03_original_status,
        "results": [
            {
                "workload_id": result.workload_id,
                "evidence_source": result.evidence_source,
                "status": result.status.value,
                "metrics": [
                    {
                        "metric": metric.metric,
                        "direction": metric.direction,
                        "sorted_values": list(metric.sorted_values),
                        "minimum": metric.minimum,
                        "median": metric.median,
                        "maximum": metric.maximum,
                        "spread": metric.spread,
                        "stable": metric.stable,
                        "threshold": metric.threshold,
                    }
                    for metric in result.metrics
                ],
            }
            for result in decision.results
        ],
    }
    return (
        json.dumps(payload, allow_nan=False, ensure_ascii=True, sort_keys=True) + "\n"
    ).encode("utf-8")


def _receipt_payload(receipt: Receipt) -> dict[str, object]:
    return {
        "schema_version": receipt.schema_version,
        "byte_count": receipt.byte_count,
        "sha256": receipt.sha256,
    }


def _records_are_eligible(records: tuple[ThresholdRecord, ...]) -> bool:
    if type(records) is not tuple or len(records) != 5:
        return False
    reference = records[0].comparability_key
    return all(
        record.outcome == "SUCCEEDED"
        and str(record.resource_evidence_status) == "VALID"
        and record.comparability_key == reference
        and type(record.open_fd_start) is int
        and type(record.open_fd_peak) is int
        and type(record.open_fd_end) is int
        and record.open_fd_end == record.open_fd_start
        for record in records
    )


def _summaries(
    records: tuple[ThresholdRecord, ...],
) -> tuple[MetricThresholdV1, ...]:
    summaries = [
        summarize_values(
            "elapsed_wall_ms",
            tuple(record.elapsed_wall_ms for record in records),
            "LOWER",
        ),
        summarize_values(
            "peak_rss_bytes",
            tuple(_required_int(record.peak_rss_bytes) for record in records),
            "LOWER",
        ),
        summarize_values(
            "open_fd_peak_delta",
            tuple(
                _required_int(record.open_fd_peak) - _required_int(record.open_fd_start)
                for record in records
            ),
            "LOWER",
        ),
    ]
    _append_optional_metric(
        summaries,
        "throughput_rows_per_s",
        tuple(record.throughput_rows_per_s for record in records),
        "HIGHER",
    )
    _append_optional_metric(
        summaries,
        "query_elapsed_ms",
        tuple(record.query_elapsed_ms for record in records),
        "LOWER",
    )
    phase_maps = tuple(record.phase_elapsed_ms for record in records)
    if any(value is not None for value in phase_maps):
        if any(type(value) is not dict for value in phase_maps):
            raise ValueError("inconsistent phase evidence")
        keys = ("normalize", "validate", "publish", "catalog", "query")
        for key in keys:
            _append_optional_metric(
                summaries,
                f"phase_{key}_elapsed_ms",
                tuple(value[key] for value in phase_maps),  # type: ignore[index]
                "LOWER",
            )
    return tuple(summaries)


def _append_optional_metric(
    output: list[MetricThresholdV1],
    name: str,
    values: tuple[int | float | None, ...],
    direction: str,
) -> None:
    if all(value is None for value in values):
        return
    if any(value is None for value in values):
        raise ValueError("inconsistent optional metric")
    output.append(summarize_values(name, values, direction))  # type: ignore[arg-type]


def _required_int(value: int | None) -> int:
    if type(value) is not int:
        raise ValueError("missing required resource evidence")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
