"""ARK-92 collection rules for the Plan 03 benchmark baselines."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import ark90_benchmark_measurement as benchmark_measurement
from ark90_benchmark_measurement import measure_benchmark_workload
from ark92_benchmark_baseline_collection import (
    BaselineCollectionStatus,
    collect_baseline_samples,
    collect_benchmark_baselines,
)


@dataclass(frozen=True, slots=True)
class _IterationRecord:
    workload_id: str
    iteration_kind: str
    iteration_index: int
    outcome: str
    resource_evidence_status: str


def test_non_b01_child_prepares_the_corpus_before_its_start_barrier(
    monkeypatch: object,
) -> None:
    events: list[str] = []

    class _Connection:
        receive_count = 0

        def send(self, message: object) -> None:
            events.append("ready" if message == "READY" else "done")

        def recv(self) -> str:
            self.receive_count += 1
            events.append("start" if self.receive_count == 1 else "exit")
            return "START" if self.receive_count == 1 else "EXIT"

        def close(self) -> None:
            events.append("closed")

    def prepare(*_args: object) -> object:
        events.append("prepared")
        return object()

    def execute(*_args: object) -> object:
        events.append("executed")
        return object()

    patch = monkeypatch  # type: ignore[assignment]
    patch.setattr(benchmark_measurement, "_prepare_benchmark_workload", prepare)
    patch.setattr(
        benchmark_measurement, "_execute_prepared_benchmark_workload", execute
    )

    benchmark_measurement._run_benchmark_child(_Connection(), "B02", "/unused")

    assert events == [
        "prepared",
        "ready",
        "start",
        "executed",
        "done",
        "exit",
        "closed",
    ]


def test_b02_retains_zero_request_resume_evidence_in_a_fresh_child(
    tmp_path: Path,
) -> None:
    record = measure_benchmark_workload(
        tmp_path,
        workload_id="B02",
        iteration_kind="measured",
        iteration_index=1,
    )

    assert record.workload_id == "B02"
    assert record.outcome == "SUCCEEDED"
    assert record.failure_code == "NONE"
    assert record.partition_outcomes == (
        "SKIPPED_VERIFIED",
        "SKIPPED_VERIFIED",
        "RECOVERED_LOCALLY",
    )
    assert record.request_count == record.provider_attempt_count == 0
    assert record.resume_count == 3
    assert record.physical_month_count == len(record.partition_checksums) == 3
    assert all(len(checksum) == 64 for _, _, checksum in record.partition_checksums)


def test_b03_repairs_only_february_and_retains_sanitized_control_evidence(
    tmp_path: Path,
) -> None:
    record = measure_benchmark_workload(
        tmp_path,
        workload_id="B03",
        iteration_kind="measured",
        iteration_index=1,
    )

    assert record.workload_id == "B03"
    assert record.outcome == "SUCCEEDED"
    assert record.failure_code == "NONE"
    assert record.partition_outcomes == ("VERIFIED",)
    assert record.reconciliation_reasons == ("CHECKSUM_INVALID_OR_MISMATCHED",)
    assert (
        record.request_count
        == record.provider_attempt_count
        == record.repair_count
        == 1
    )
    assert tuple((year, month) for year, month, _ in record.partition_checksums) == (
        (2024, 2),
    )
    control = record.control_partition_evidence
    assert control is not None
    assert control.physical_identity[-2:] == (2024, 1)
    assert control.pre_physical_checksum == control.post_physical_checksum
    assert control.pre_manifest_fingerprint == control.post_manifest_fingerprint
    assert len(control.manifest_bound_schedule_digest) == 64


def test_b04_queries_one_sealed_month_through_one_configured_connection(
    tmp_path: Path,
) -> None:
    record = measure_benchmark_workload(
        tmp_path,
        workload_id="B04",
        iteration_kind="measured",
        iteration_index=1,
    )

    assert record.workload_id == "B04"
    assert record.outcome == "SUCCEEDED"
    assert record.failure_code == "NONE"
    assert record.query_result_count == record.rows_published == 7_500
    assert record.query_min_ts == "2024-02-01T03:45:00.000000Z"
    assert record.query_max_ts == "2024-02-20T09:59:00.000000Z"
    assert record.query_elapsed_ms is not None
    assert record.phase_elapsed_ms["query"] == record.query_elapsed_ms


def test_b05_queries_the_twelve_partition_history_shape_with_one_connection(
    tmp_path: Path,
) -> None:
    record = measure_benchmark_workload(
        tmp_path,
        workload_id="B05",
        iteration_kind="measured",
        iteration_index=1,
    )

    assert record.workload_id == "B05"
    assert record.outcome == "SUCCEEDED"
    assert record.failure_code == "NONE"
    assert record.query_result_count == record.rows_published == 90_000
    assert record.query_min_ts == "2023-01-01T03:45:00.000000Z"
    assert record.query_max_ts == "2023-12-20T09:59:00.000000Z"
    assert record.physical_month_count == len(record.partition_checksums) == 12
    assert record.query_elapsed_ms is not None
    assert record.phase_elapsed_ms["query"] == record.query_elapsed_ms


def test_collection_retains_one_warmup_and_exactly_five_ordered_measurements_per_workload(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str, int]] = []

    def measure(
        workload_id: str, iteration_kind: str, iteration_index: int
    ) -> _IterationRecord:
        calls.append((workload_id, iteration_kind, iteration_index))
        is_invalid_b03_measurement = (
            workload_id == "B03"
            and iteration_kind == "measured"
            and iteration_index == 3
        )
        return _IterationRecord(
            workload_id,
            iteration_kind,
            iteration_index,
            "CANCELLED" if is_invalid_b03_measurement else "SUCCEEDED",
            "INVALID" if is_invalid_b03_measurement else "VALID",
        )

    report = collect_baseline_samples(tmp_path, measure)

    expected_calls = [
        (workload_id, iteration_kind, iteration_index)
        for workload_id in ("B01", "B02", "B03", "B04", "B05")
        for iteration_kind, iteration_index in (
            ("warmup", 1),
            *tuple(("measured", index) for index in range(1, 6)),
        )
    ]
    assert calls == expected_calls
    assert tuple(result.workload_id for result in report.results) == (
        "B01",
        "B02",
        "B03",
        "B04",
        "B05",
    )

    b03 = report.results[2]
    assert b03.warmup.iteration_kind == "warmup"
    assert tuple(record.iteration_index for record in b03.measured) == (1, 2, 3, 4, 5)
    assert b03.measured[2].outcome == "CANCELLED"
    assert b03.measured[2].resource_evidence_status == "INVALID"
    assert b03.status is BaselineCollectionStatus.INSUFFICIENT
    assert b03.retained_measurement_count == 5
    assert b03.valid_measurement_count == 4
    assert b03.threshold_claim is None

    assert all(
        result.status is BaselineCollectionStatus.RETAINED
        and result.retained_measurement_count == 5
        and result.valid_measurement_count == 5
        and result.threshold_claim is None
        for result in (*report.results[:2], *report.results[3:])
    )


def test_collection_runs_all_fixed_workloads_in_fresh_children_with_plan03_evidence(  # noqa: C901
    tmp_path: Path,
) -> None:
    report = collect_benchmark_baselines(tmp_path)

    assert tuple(result.workload_id for result in report.results) == (
        "B01",
        "B02",
        "B03",
        "B04",
        "B05",
    )
    for result in report.results:
        assert result.warmup.iteration_kind == "warmup"
        assert result.warmup.iteration_index == 1
        assert (
            tuple(record.iteration_kind for record in result.measured)
            == ("measured",) * 5
        )
        assert tuple(record.iteration_index for record in result.measured) == (
            1,
            2,
            3,
            4,
            5,
        )
        assert result.retained_measurement_count == 5
        assert len(result.measured) == 5
        assert result.threshold_claim is None
        if result.valid_measurement_count == 5:
            assert result.status is BaselineCollectionStatus.RETAINED
        else:
            assert result.status is BaselineCollectionStatus.INSUFFICIENT
            assert 0 <= result.valid_measurement_count < 5

    valid_records = {
        result.workload_id: next(
            (
                record
                for record in result.measured
                if record.outcome == "SUCCEEDED"
                and record.resource_evidence_status == "VALID"
            ),
            None,
        )
        for result in report.results
    }

    for result in report.results:
        record = valid_records[result.workload_id]
        for raw_record in result.measured:
            assert raw_record.workload_id == result.workload_id
            assert raw_record.iteration_kind == "measured"
            assert 1 <= raw_record.iteration_index <= 5
            assert len(raw_record.source_revision) == 40
            assert len(raw_record.source_tree) == 40
            assert len(raw_record.lock_identity) == 64
            assert len(raw_record.schedule_digest) == 64
            assert raw_record.policy_version
            assert raw_record.partition_checksums
        if record is None:
            assert result.status is BaselineCollectionStatus.INSUFFICIENT
            assert 0 <= result.valid_measurement_count < 5
            invalid_records = tuple(
                item
                for item in result.measured
                if item.resource_evidence_status == "INVALID"
            )
            assert invalid_records
            assert all(item.resource_blocker for item in invalid_records)
        else:
            assert record.workload_id == result.workload_id

    b01 = valid_records["B01"]
    if b01 is not None:
        assert b01.rows_published == 7_500
        assert b01.request_count == b01.provider_attempt_count == 1
        assert b01.partition_outcomes == ("VERIFIED",)

    b02 = valid_records["B02"]
    if b02 is not None:
        assert b02.partition_outcomes == (
            "SKIPPED_VERIFIED",
            "SKIPPED_VERIFIED",
            "RECOVERED_LOCALLY",
        )
        assert b02.request_count == b02.provider_attempt_count == 0
        assert b02.resume_count == 3

    b03 = valid_records["B03"]
    if b03 is not None:
        assert b03.request_count == b03.provider_attempt_count == b03.repair_count == 1
        assert b03.partition_checksums and b03.partition_checksums[0][:2] == (2024, 2)

    b04 = valid_records["B04"]
    if b04 is not None:
        assert b04.query_result_count == b04.rows_published == 7_500
        assert b04.query_min_ts == "2024-02-01T03:45:00.000000Z"
        assert b04.query_max_ts == "2024-02-20T09:59:00.000000Z"

    b05 = valid_records["B05"]
    if b05 is not None:
        assert b05.query_result_count == b05.rows_published == 90_000
        assert b05.query_min_ts == "2023-01-01T03:45:00.000000Z"
        assert b05.query_max_ts == "2023-12-20T09:59:00.000000Z"
