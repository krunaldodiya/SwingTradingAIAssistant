"""ARK-92 collection rules for the Plan 03 benchmark baselines."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import ark90_benchmark_measurement as benchmark_measurement
import ark92_benchmark_baseline_collection as baseline_collection
import pytest
from ark90_benchmark_measurement import (
    B01MeasurementRecord,
    BenchmarkCommandLimits,
    BenchmarkResourceLimits,
    ComparabilityIdentity,
    ResourceEvidenceStatus,
    SourceDataShape,
    _b02_zero_side_effect_counters,
    _b03_observed_request_evidence_is_exact,
    _Sample,
    _sampling_blocker,
    measure_b01,
    measure_benchmark_workload,
)
from ark92_benchmark_baseline_collection import (
    BaselineCollectionReport,
    BaselineCollectionStatus,
    BaselineWorkloadResult,
    _comparable_valid_count,
    collect_baseline_samples,
    collect_benchmark_baselines,
    write_baseline_artifact,
)
from ark92_benchmark_baseline_collection import main as persist_baseline_artifact


def _identity() -> ComparabilityIdentity:
    return ComparabilityIdentity(
        "B01",
        "fixture",
        "fixture-v1",
        "revision",
        "tree",
        "lock",
        "digest",
        "range",
        "2024-03-01T00:00:00.000000Z",
        "source",
        "release",
        "timezone",
        ("kind",),
        (("closure", "reason"),),
        "policy",
        ((2024, 2, "checksum"),),
        SourceDataShape(1, 1, 1, 1),
        BenchmarkCommandLimits("1m", 1, 1, 0, 0, 0, 0, 1, 1, 1),
        BenchmarkResourceLimits(1.0, 10, 50, 2, "closed"),
        "method",
        "3.13",
        "25.0",
        "1.5",
        "7.2.2",
        "sampler",
        "arch",
        1,
        "filesystem",
    )


@dataclass(frozen=True, slots=True)
class _IterationRecord:
    workload_id: str
    iteration_kind: str
    iteration_index: int
    outcome: str
    resource_evidence_status: str
    comparability_key: object = field(default_factory=_identity)


def _artifact_record(
    workload_id: str,
    iteration_kind: str,
    iteration_index: int,
    *,
    outcome: str = "SUCCEEDED",
    failure_code: str = "NONE",
) -> B01MeasurementRecord:
    return B01MeasurementRecord(
        workload_id,
        iteration_kind,
        iteration_index,
        "a" * 40,
        "b" * 40,
        "c" * 64,
        "3.13.7",
        "macOS",
        "cpu",
        1,
        1_024,
        "apfs",
        "1.5.0",
        "25.0.0",
        "macOS 15",
        "fixture",
        "fixture-v1",
        "d" * 64,
        "policy",
        "2024-02-01..2024-02-29",
        1,
        ((2024, 2, "e" * 64),),
        1,
        1,
        {"normalize": 1, "validate": 1, "publish": 1, "catalog": 1, "query": None},
        1,
        1,
        1,
        1,
        1.0,
        0,
        0,
        0,
        0,
        0,
        1_024,
        3,
        3,
        3,
        "psutil-parent-child-v1",
        "7.2.2",
        2,
        10,
        ResourceEvidenceStatus.VALID,
        None,
        None,
        None,
        None,
        None,
        outcome,
        failure_code,
        ("VERIFIED",),
        (),
        None,
        replace(
            _identity(),
            workload_id=workload_id,
            fixture_id="fixture",
            fixture_version="fixture-v1",
            source_revision="a" * 40,
            source_tree="b" * 40,
            lock_identity="c" * 64,
            schedule_digest="d" * 64,
            requested_range="2024-02-01..2024-02-29",
            policy_version="policy",
            partition_checksums=((2024, 2, "e" * 64),),
            source_data_shape=SourceDataShape(1, 1, 1, 1),
            sampler_method="psutil-parent-child-v1",
            psutil_version="7.2.2",
            cpu_count=1,
            filesystem_type="apfs",
        ),
    )


def _artifact_report() -> BaselineCollectionReport:
    results = []
    for workload_id in ("B01", "B02", "B03", "B04", "B05"):
        measured = tuple(
            _artifact_record(workload_id, "measured", index) for index in range(1, 6)
        )
        if workload_id == "B03":
            measured = (
                measured[0],
                measured[1],
                replace(
                    measured[2],
                    outcome="CANCELLED",
                    failure_code="BENCHMARK_CHILD_CANCELLED",
                ),
                replace(
                    measured[3], outcome="FAILED", failure_code="CHILD_PROTOCOL_INVALID"
                ),
                measured[4],
            )
        valid_measurement_count = sum(
            record.outcome == "SUCCEEDED" for record in measured
        )
        results.append(
            BaselineWorkloadResult(
                workload_id,
                _artifact_record(workload_id, "warmup", 1),
                measured,
                (
                    BaselineCollectionStatus.RETAINED
                    if valid_measurement_count == 5
                    else BaselineCollectionStatus.INSUFFICIENT
                ),
                5,
                valid_measurement_count,
            )
        )
    return BaselineCollectionReport(tuple(results))


def test_write_baseline_artifact_serializes_complete_sanitized_report_atomically(
    tmp_path: Path,
) -> None:
    output = tmp_path / "baseline.json"

    write_baseline_artifact(_artifact_report(), output)

    payload = json.loads(output.read_text())
    assert tuple(item["workload_id"] for item in payload["results"]) == (
        "B01",
        "B02",
        "B03",
        "B04",
        "B05",
    )
    b03 = payload["results"][2]
    assert b03["status"] == "INSUFFICIENT"
    assert b03["threshold_claim"] is None
    assert [item["iteration_index"] for item in b03["measured"]] == [1, 2, 3, 4, 5]
    assert [item["outcome"] for item in b03["measured"]][2:4] == [
        "CANCELLED",
        "FAILED",
    ]
    assert set(b03["warmup"]) == set(B01MeasurementRecord.__dataclass_fields__)
    assert "path" not in json.dumps(payload).lower()


def test_comparable_valid_count_excludes_one_mismatched_valid_identity() -> None:
    records = tuple(_artifact_record("B01", "measured", index) for index in range(1, 6))
    mismatched = replace(
        records[4], comparability_key=replace(_identity(), workload_id="B02")
    )

    assert _comparable_valid_count(records[:4] + (mismatched,)) == 4


def test_write_baseline_artifact_rejects_unsafe_or_incomplete_evidence_without_temp(
    tmp_path: Path,
) -> None:
    report = _artifact_report()
    unsafe = replace(
        report.results[0],
        warmup=replace(report.results[0].warmup, platform="/private/raw-payload"),
    )

    with pytest.raises(ValueError, match="unsanitized"):
        write_baseline_artifact(
            replace(report, results=(unsafe,) + report.results[1:]),
            tmp_path / "baseline.json",
        )

    assert tuple(tmp_path.iterdir()) == ()


@pytest.mark.parametrize(
    ("field_name", "unsafe_value"),
    (
        ("cpu_model", "SELECT * FROM candle_copy"),
        ("platform", "NSE_EQ|TESTEQ"),
        ("os_version", '{"raw_payload":"secret"}'),
        ("cpu_model", "instrument_key=NSE_EQ|TESTEQ"),
        ("fixture_id", "fixture?access_token=secret"),
        ("query_min_ts", "https://provider.example/raw"),
    ),
)
def test_write_baseline_artifact_rejects_nonapproved_text_evidence(
    tmp_path: Path, field_name: str, unsafe_value: str
) -> None:
    report = _artifact_report()
    record = report.results[0].warmup
    identity = (
        replace(record.comparability_key, **{field_name: unsafe_value})
        if field_name in ComparabilityIdentity.__dataclass_fields__
        else record.comparability_key
    )
    unsafe = replace(
        report.results[0],
        warmup=replace(
            record, comparability_key=identity, **{field_name: unsafe_value}
        ),
    )

    with pytest.raises(ValueError, match="unsanitized"):
        write_baseline_artifact(
            replace(report, results=(unsafe,) + report.results[1:]),
            tmp_path / "baseline.json",
        )

    assert tuple(tmp_path.iterdir()) == ()


def test_write_baseline_artifact_rejects_unsafe_nested_identity_evidence(
    tmp_path: Path,
) -> None:
    report = _artifact_report()
    record = report.results[0].warmup
    unsafe_identity = replace(
        record.comparability_key,
        command_limits=replace(
            record.comparability_key.command_limits,
            interval="SELECT * FROM candles",
        ),
        resource_limits=replace(
            record.comparability_key.resource_limits,
            fd_closure_rule="NSE_EQ|TESTEQ",
        ),
    )
    unsafe = replace(
        report.results[0], warmup=replace(record, comparability_key=unsafe_identity)
    )

    with pytest.raises(ValueError, match="unsanitized"):
        write_baseline_artifact(
            replace(report, results=(unsafe,) + report.results[1:]),
            tmp_path / "baseline.json",
        )

    assert tuple(tmp_path.iterdir()) == ()


def test_write_baseline_artifact_rejects_untyped_nested_identity_limits(
    tmp_path: Path,
) -> None:
    report = _artifact_report()
    record = report.results[0].warmup
    for field_name in ("command_limits", "resource_limits"):
        mismatched_identity = replace(
            record.comparability_key,
            **{field_name: "invalid"},  # type: ignore[arg-type]
        )
        mismatched = replace(
            report.results[0],
            warmup=replace(record, comparability_key=mismatched_identity),
        )

        with pytest.raises(ValueError, match="identity"):
            write_baseline_artifact(
                replace(report, results=(mismatched,) + report.results[1:]),
                tmp_path / "baseline.json",
            )

        assert tuple(tmp_path.iterdir()) == ()


def test_write_baseline_artifact_preserves_safe_typed_control_evidence(
    tmp_path: Path,
) -> None:
    report = _artifact_report()
    control = benchmark_measurement._ControlPartitionEvidence(
        ("synthetic", "NSE", "NSE_EQ", "EQ", "fixture", "1m", 2024, 1),
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "d" * 64,
        "e" * 64,
    )
    b03 = replace(
        report.results[2],
        warmup=replace(report.results[2].warmup, control_partition_evidence=control),
    )
    output = tmp_path / "baseline.json"

    write_baseline_artifact(
        replace(report, results=(*report.results[:2], b03, *report.results[3:])),
        output,
    )

    payload = json.loads(output.read_text())
    assert payload["results"][2]["warmup"]["control_partition_evidence"] == {
        "physical_identity": [
            "synthetic",
            "NSE",
            "NSE_EQ",
            "EQ",
            "fixture",
            "1m",
            2024,
            1,
        ],
        "pre_physical_checksum": "a" * 64,
        "post_physical_checksum": "b" * 64,
        "pre_manifest_fingerprint": "c" * 64,
        "post_manifest_fingerprint": "d" * 64,
        "manifest_bound_schedule_digest": "e" * 64,
    }


@pytest.mark.parametrize(
    "record_field",
    (
        "workload_id",
        "fixture_id",
        "fixture_version",
        "source_revision",
        "source_tree",
        "lock_identity",
        "schedule_digest",
        "policy_version",
        "requested_range",
        "partition_checksums",
        "rows_raw",
        "rows_normalized",
        "rows_published",
        "bytes_parquet",
        "cpu_count",
        "filesystem_type",
        "sampler_method",
        "psutil_version",
    ),
)
def test_write_baseline_artifact_rejects_every_direct_identity_contradiction(
    tmp_path: Path, record_field: str
) -> None:
    report = _artifact_report()
    record = report.results[0].warmup
    key = record.comparability_key
    changed_key = _contradict_identity_field(key, record_field)
    contradictory = replace(
        report.results[0], warmup=replace(record, comparability_key=changed_key)
    )

    with pytest.raises(ValueError, match="contradicts"):
        write_baseline_artifact(
            replace(report, results=(contradictory,) + report.results[1:]),
            tmp_path / "baseline.json",
        )

    assert tuple(tmp_path.iterdir()) == ()


def _contradict_identity_field(
    identity: ComparabilityIdentity, record_field: str
) -> ComparabilityIdentity:
    if record_field in SourceDataShape.__dataclass_fields__:
        shape = replace(
            identity.source_data_shape,
            **{record_field: getattr(identity.source_data_shape, record_field) + 1},
        )
        return replace(identity, source_data_shape=shape)
    if record_field == "partition_checksums":
        checksums = ((2024, 1, "f" * 64), *identity.partition_checksums)
        return replace(identity, partition_checksums=checksums)
    if record_field == "workload_id":
        return replace(identity, workload_id="B02")
    return replace(identity, **{record_field: "different"})


def test_write_baseline_artifact_rejects_partition_checksum_order_change(
    tmp_path: Path,
) -> None:
    report = _artifact_report()
    record = report.results[0].warmup
    checksums = ((2024, 1, "f" * 64), (2024, 2, "e" * 64))
    record = replace(record, physical_month_count=2, partition_checksums=checksums)
    reversed_identity = replace(
        record.comparability_key,
        partition_checksums=tuple(reversed(checksums)),
    )
    contradictory = replace(
        report.results[0], warmup=replace(record, comparability_key=reversed_identity)
    )

    with pytest.raises(ValueError, match="contradicts"):
        write_baseline_artifact(
            replace(report, results=(contradictory,) + report.results[1:]),
            tmp_path / "baseline.json",
        )

    assert tuple(tmp_path.iterdir()) == ()


@pytest.mark.parametrize("measured_count", (4, 6))
def test_write_baseline_artifact_rejects_missing_or_extra_iterations(
    tmp_path: Path, measured_count: int
) -> None:
    report = _artifact_report()
    measured = report.results[0].measured
    if measured_count < len(measured):
        changed = measured[:measured_count]
    else:
        changed = measured + (replace(measured[-1], iteration_index=6),)
    incomplete = replace(report.results[0], measured=changed)

    with pytest.raises(ValueError, match="incomplete"):
        write_baseline_artifact(
            replace(report, results=(incomplete,) + report.results[1:]),
            tmp_path / "baseline.json",
        )

    assert tuple(tmp_path.iterdir()) == ()


@pytest.mark.parametrize(
    "results",
    (
        lambda report: report.results[1:],
        lambda report: report.results + (report.results[0],),
    ),
)
def test_write_baseline_artifact_rejects_missing_or_extra_workloads(
    tmp_path: Path, results: object
) -> None:
    report = _artifact_report()
    changed_results = results(report)  # type: ignore[operator]

    with pytest.raises(ValueError, match="workloads"):
        write_baseline_artifact(
            replace(report, results=changed_results), tmp_path / "baseline.json"
        )

    assert tuple(tmp_path.iterdir()) == ()


def test_write_baseline_artifact_never_overwrites_existing_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "baseline.json"
    output.write_text("existing")

    with pytest.raises(FileExistsError):
        write_baseline_artifact(_artifact_report(), output)

    assert output.read_text() == "existing"


def test_write_baseline_artifact_cleans_up_after_temporary_write_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "baseline.json"

    def write_then_fail(temporary: Path, _encoded: bytes) -> None:
        temporary.write_bytes(b"partial")
        raise OSError("write failed")

    monkeypatch.setattr(baseline_collection, "_write_temporary", write_then_fail)

    with pytest.raises(OSError, match="write failed"):
        write_baseline_artifact(_artifact_report(), output)

    assert not output.exists()
    assert tuple(tmp_path.iterdir()) == ()


def test_write_baseline_artifact_cleans_up_after_fsync_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "baseline.json"

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr(baseline_collection.os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="fsync failed"):
        write_baseline_artifact(_artifact_report(), output)

    assert not output.exists()
    assert tuple(tmp_path.iterdir()) == ()


def test_write_baseline_artifact_preserves_concurrent_destination_and_cleans_temp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "baseline.json"

    def competing_link(_temporary: Path, destination: Path) -> None:
        destination.write_text("concurrent artifact")
        raise FileExistsError("destination exists")

    monkeypatch.setattr(baseline_collection.os, "link", competing_link)

    with pytest.raises(FileExistsError, match="destination exists"):
        write_baseline_artifact(_artifact_report(), output)

    assert output.read_text() == "concurrent artifact"
    assert tuple(tmp_path.iterdir()) == (output,)


def test_write_baseline_artifact_rejects_duplicate_incomplete_and_nonfinite_rows(
    tmp_path: Path,
) -> None:
    report = _artifact_report()
    duplicate_workload = replace(report, results=(report.results[0],) * 5)
    duplicate_iteration = replace(
        report.results[0],
        measured=(
            report.results[0].measured[0],
            replace(report.results[0].measured[1], iteration_index=1),
        )
        + report.results[0].measured[2:],
    )
    incomplete = replace(report.results[0], warmup=object())  # type: ignore[arg-type]
    nonfinite = replace(
        report.results[0],
        warmup=replace(report.results[0].warmup, throughput_rows_per_s=float("nan")),
    )

    for malformed in (
        duplicate_workload,
        replace(report, results=(duplicate_iteration,) + report.results[1:]),
        replace(report, results=(incomplete,) + report.results[1:]),
        replace(report, results=(nonfinite,) + report.results[1:]),
    ):
        with pytest.raises(ValueError):
            write_baseline_artifact(malformed, tmp_path / "baseline.json")
        assert tuple(tmp_path.iterdir()) == ()


def test_persistence_entry_point_uses_disposable_root_and_never_retries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[Path] = []
    output = tmp_path / "artifact" / "baseline.json"
    work_root = tmp_path / "artifact" / "work"
    monkeypatch.setattr(baseline_collection, "_ARTIFACTS_ROOT", tmp_path / "artifact")
    monkeypatch.setattr(
        baseline_collection,
        "collect_benchmark_baselines",
        lambda root: calls.append(root) or _artifact_report(),
    )

    assert (
        persist_baseline_artifact(
            ["--output", str(output), "--work-root", str(work_root)]
        )
        == 0
    )
    assert calls == [work_root]
    assert output.is_file()

    assert (
        persist_baseline_artifact(
            ["--output", str(output), "--work-root", str(work_root)]
        )
        == 2
    )
    assert calls == [work_root]


@pytest.mark.parametrize(
    ("output_suffix", "work_suffix", "setup", "expected_code"),
    (
        ("outside.json", "work", None, "PERSISTENCE_FAILED"),
        ("artifact/same", "artifact/same", None, "OUTPUT_WORK_ROOT_OVERLAP"),
        ("artifact/output.json", "artifact", None, "OUTPUT_WORK_ROOT_OVERLAP"),
        (
            "artifact/output.json",
            "artifact/output.json/work",
            None,
            "OUTPUT_WORK_ROOT_OVERLAP",
        ),
        ("artifact/output.json", "artifact/work", "work", "WORK_ROOT_EXISTS"),
    ),
)
def test_persistence_entry_point_rejects_invalid_paths_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    output_suffix: str,
    work_suffix: str,
    setup: str | None,
    expected_code: str,
) -> None:
    artifact_root = tmp_path / "artifact"
    output = tmp_path / output_suffix
    work_root = tmp_path / work_suffix
    calls: list[Path] = []
    artifact_root.mkdir()
    if setup == "work":
        work_root.mkdir(parents=True)
    monkeypatch.setattr(baseline_collection, "_ARTIFACTS_ROOT", artifact_root)
    monkeypatch.setattr(
        baseline_collection,
        "collect_benchmark_baselines",
        lambda root: calls.append(root) or _artifact_report(),
    )

    assert (
        persist_baseline_artifact(
            ["--output", str(output), "--work-root", str(work_root)]
        )
        == 2
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"baseline artifact collection failed: {expected_code}\n"
    assert str(tmp_path) not in captured.err
    assert "Traceback" not in captured.err
    assert calls == []


def test_persistence_entry_point_rejects_malformed_arguments_without_paths(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert persist_baseline_artifact(["--output", "/private/not-allowed"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "baseline artifact collection failed: INVALID_ARGUMENTS\n"
    assert "/private/not-allowed" not in captured.err
    assert "Traceback" not in captured.err


def test_sampling_gap_over_limit_is_invalid_before_millisecond_display_rounding() -> (
    None
):
    samples = [_Sample(0, 1, 1), _Sample(50_000_001, 1, 1)]

    assert _sampling_blocker(samples, None, None) == "max_gap_exceeded"


def test_b02_zero_side_effect_proof_rejects_chained_comparison_counter_pattern() -> (
    None
):
    assert not _b02_zero_side_effect_counters(0, 1, 0, 0)
    assert _b02_zero_side_effect_counters(0, 0, 0, 0)


def test_b03_request_evidence_rejects_hostile_asymmetric_counter_pattern() -> None:
    # The former chained expression accepts this mismatched evidence because
    # its second comparison is false.  Each B03 counter must be exact instead.
    assert (0 != 1 != 1) is False
    assert not _b03_observed_request_evidence_is_exact(0, 1)
    assert not _b03_observed_request_evidence_is_exact(1, 0)
    assert _b03_observed_request_evidence_is_exact(1, 1)


def test_equal_untyped_comparability_values_are_retained_but_insufficient(
    tmp_path: Path,
) -> None:
    untyped_identity = object()

    def measure(workload_id: str, kind: str, index: int) -> _IterationRecord:
        return _IterationRecord(
            workload_id,
            kind,
            index,
            "SUCCEEDED",
            "VALID",
            untyped_identity,
        )

    report = collect_baseline_samples(tmp_path, measure)
    b01 = report.results[0]

    assert b01.retained_measurement_count == 5
    assert b01.valid_measurement_count == 0
    assert b01.status is BaselineCollectionStatus.INSUFFICIENT
    assert b01.threshold_claim is None


def test_ordinary_terminal_observations_are_typed_done_results_with_actual_provenance(
    tmp_path: Path,
) -> None:
    failed = measure_benchmark_workload(
        tmp_path,
        workload_id="B02",
        iteration_kind="measured",
        iteration_index=1,
        child_terminal="failure",
    )
    cancelled = measure_benchmark_workload(
        tmp_path,
        workload_id="B02",
        iteration_kind="measured",
        iteration_index=2,
        child_terminal="cancelled",
    )

    assert (failed.outcome, failed.failure_code) == (
        "FAILED",
        "BENCHMARK_CHILD_FAILED",
    )
    assert (cancelled.outcome, cancelled.failure_code) == (
        "CANCELLED",
        "BENCHMARK_CHILD_CANCELLED",
    )
    for record in (failed, cancelled):
        assert tuple(
            (year, month) for year, month, _ in record.partition_checksums
        ) == (
            (2024, 1),
            (2024, 2),
            (2024, 3),
        )
        assert all(
            checksum != "0" * 64 for _, _, checksum in record.partition_checksums
        )
        assert record.requested_range == "2024-01-01..2024-03-31"
        assert record.resource_evidence_status.value == "VALID"
        assert record.open_fd_end == record.open_fd_start


def test_comparability_identity_includes_each_frozen_plan03_dimension() -> None:
    field_names = tuple(ComparabilityIdentity.__dataclass_fields__)

    assert field_names == (
        "workload_id",
        "fixture_id",
        "fixture_version",
        "source_revision",
        "source_tree",
        "lock_identity",
        "schedule_digest",
        "requested_range",
        "schedule_as_of",
        "schedule_source",
        "schedule_release",
        "schedule_timezone",
        "schedule_kind_provenance",
        "schedule_closure_provenance",
        "policy_version",
        "partition_checksums",
        "source_data_shape",
        "command_limits",
        "resource_limits",
        "measurement_method",
        "python_major_minor",
        "pyarrow_major_minor",
        "duckdb_major_minor",
        "psutil_version",
        "sampler_method",
        "cpu_architecture",
        "cpu_count",
        "filesystem_type",
    )


def test_each_comparability_identity_dimension_mismatch_is_insufficient(
    tmp_path: Path,
) -> None:
    base = _identity()

    for field_name in ComparabilityIdentity.__dataclass_fields__:
        changed = replace(base, **{field_name: (getattr(base, field_name), "other")})

        def measure(
            workload_id: str,
            kind: str,
            index: int,
            changed_identity: ComparabilityIdentity = changed,
        ) -> _IterationRecord:
            identity = (
                changed_identity
                if (workload_id, kind, index) == ("B01", "measured", 5)
                else base
            )
            return _IterationRecord(
                workload_id, kind, index, "SUCCEEDED", "VALID", identity
            )

        report = collect_baseline_samples(tmp_path / field_name, measure)

        assert report.results[0].status is BaselineCollectionStatus.INSUFFICIENT
        assert report.results[0].valid_measurement_count == 4


def test_real_child_failure_is_sanitized_retained_and_does_not_stop_collection(
    tmp_path: Path,
) -> None:
    failed = measure_b01(
        tmp_path,
        iteration_kind="measured",
        iteration_index=1,
        child_failure=True,
    )

    assert failed.outcome == "FAILED"
    assert failed.failure_code == "B01_CHILD_FAILED"
    assert failed.rows_published == 0
    assert failed.partition_checksums == ()
    assert failed.resource_evidence_status.value == "VALID"
    assert failed.resource_blocker is None
    assert "Exception" not in failed.failure_code
    assert len(failed.source_revision) == len(failed.source_tree) == 40
    assert len(failed.lock_identity) == len(failed.schedule_digest) == 64

    calls: list[tuple[str, str, int]] = []

    def measure(workload_id: str, kind: str, index: int) -> _IterationRecord:
        calls.append((workload_id, kind, index))
        if (workload_id, kind, index) == ("B03", "measured", 3):
            return _IterationRecord(workload_id, kind, index, "FAILED", "INVALID")
        return _IterationRecord(workload_id, kind, index, "SUCCEEDED", "VALID")

    report = collect_baseline_samples(tmp_path / "collection", measure)

    assert calls[-1] == ("B05", "measured", 5)
    assert report.results[2].status is BaselineCollectionStatus.INSUFFICIENT
    assert report.results[2].measured[2].outcome == "FAILED"


def test_non_b01_child_terminal_failures_are_retained_with_its_own_provenance(
    tmp_path: Path,
) -> None:
    records = tuple(
        measure_benchmark_workload(
            tmp_path,
            workload_id="B02",
            iteration_kind="measured",
            iteration_index=index,
            child_terminal=terminal,
        )
        for index, terminal in enumerate(("failure", "cancelled", "invalid"), start=1)
    )

    assert tuple(record.workload_id for record in records) == ("B02",) * 3
    assert tuple(record.outcome for record in records) == (
        "FAILED",
        "CANCELLED",
        "FAILED",
    )
    assert tuple(record.failure_code for record in records) == (
        "BENCHMARK_CHILD_FAILED",
        "BENCHMARK_CHILD_CANCELLED",
        "CHILD_PROTOCOL_INVALID",
    )
    for record in records[:2]:
        assert record.rows_published == 0
        assert record.resource_evidence_status.value == "VALID"
        assert record.resource_blocker is None
        assert record.physical_month_count == len(record.partition_checksums) == 3
        assert all(
            checksum != "0" * 64 for _, _, checksum in record.partition_checksums
        )
        assert len(record.source_revision) == len(record.source_tree) == 40
        assert len(record.lock_identity) == len(record.schedule_digest) == 64

    malformed = records[2]
    assert malformed.resource_evidence_status.value == "INVALID"
    assert malformed.resource_blocker == malformed.failure_code
    assert malformed.partition_checksums == ()


def test_valid_measurement_with_mismatched_comparability_key_is_insufficient(
    tmp_path: Path,
) -> None:
    base = _identity()
    changed = replace(base, source_tree="other-tree")

    def measure(workload_id: str, kind: str, index: int) -> _IterationRecord:
        return _IterationRecord(
            workload_id,
            kind,
            index,
            "SUCCEEDED",
            "VALID",
            changed if (workload_id, kind, index) == ("B02", "measured", 4) else base,
        )

    report = collect_baseline_samples(tmp_path, measure)
    b02 = report.results[1]

    assert b02.retained_measurement_count == 5
    assert b02.valid_measurement_count == 4
    assert b02.status is BaselineCollectionStatus.INSUFFICIENT


def test_b02_and_query_catalog_phases_are_measured_at_execution(
    monkeypatch: object, tmp_path: Path
) -> None:
    calls: list[str] = []
    base = benchmark_measurement._PhaseTimers

    class _RecordingTimers(base):
        def call(self, phase: str, *args: object, **kwargs: object) -> object:
            calls.append(phase)
            return super().call(phase, *args, **kwargs)

    monkeypatch.setattr(benchmark_measurement, "_PhaseTimers", _RecordingTimers)
    (tmp_path / "b02").mkdir()
    (tmp_path / "b04").mkdir()
    b02 = benchmark_measurement._execute_prepared_benchmark_workload(
        benchmark_measurement._prepare_benchmark_workload("B02", tmp_path / "b02")
    )
    b02_catalog_calls = calls.count("catalog")
    b04 = benchmark_measurement._execute_prepared_benchmark_workload(
        benchmark_measurement._prepare_benchmark_workload("B04", tmp_path / "b04")
    )
    b04_catalog_calls = calls.count("catalog") - b02_catalog_calls

    assert b02.phase_elapsed_ms["catalog"] is not None
    assert b04.phase_elapsed_ms["catalog"] is not None
    assert b04.phase_elapsed_ms["query"] is not None
    assert b02_catalog_calls >= 5  # open, reconciliation operations, and close
    assert b04_catalog_calls == 5  # construct, open, configuration, assertion, close
    assert "query" in calls


def test_catalog_timer_records_construction_and_b03_control_lookup_boundaries(
    monkeypatch: object, tmp_path: Path
) -> None:
    timers: list[benchmark_measurement._PhaseTimers] = []
    base = benchmark_measurement._PhaseTimers

    class _RecordingTimers(base):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            timers.append(self)

    monkeypatch.setattr(benchmark_measurement, "_PhaseTimers", _RecordingTimers)
    (tmp_path / "b03").mkdir()
    (tmp_path / "b04").mkdir()
    benchmark_measurement._execute_prepared_benchmark_workload(
        benchmark_measurement._prepare_benchmark_workload("B03", tmp_path / "b03")
    )
    benchmark_measurement._execute_prepared_benchmark_workload(
        benchmark_measurement._prepare_benchmark_workload("B04", tmp_path / "b04")
    )

    assert timers[0].events[-5:] == (
        ("catalog", "construct"),
        ("catalog", "open"),
        ("catalog", "get_manifest"),
        ("catalog", "close"),
        ("measurement", "b03_total_complete"),
    )
    assert timers[1].events == (
        ("catalog", "construct"),
        ("catalog", "open"),
        ("catalog", "configure"),
        ("query", "execute_and_fetch"),
        ("catalog", "assert_metadata_relations"),
        ("catalog", "close"),
    )


def test_b03_total_timing_ends_after_post_repair_control_lookup(
    monkeypatch: object, tmp_path: Path
) -> None:
    timers: list[benchmark_measurement._PhaseTimers] = []
    base = benchmark_measurement._PhaseTimers

    class _RecordingTimers(base):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            timers.append(self)

    monkeypatch.setattr(benchmark_measurement, "_PhaseTimers", _RecordingTimers)
    (tmp_path / "b03").mkdir()
    benchmark_measurement._execute_prepared_benchmark_workload(
        benchmark_measurement._prepare_benchmark_workload("B03", tmp_path / "b03")
    )

    assert timers[0].events[-5:] == (
        ("catalog", "construct"),
        ("catalog", "open"),
        ("catalog", "get_manifest"),
        ("catalog", "close"),
        ("measurement", "b03_total_complete"),
    )


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
    assert record.phase_elapsed_ms == {
        "normalize": None,
        "validate": None,
        "publish": None,
        "catalog": record.phase_elapsed_ms["catalog"],
        "query": record.query_elapsed_ms,
    }


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
    assert record.phase_elapsed_ms["normalize"] is None
    assert record.phase_elapsed_ms["validate"] is None
    assert record.phase_elapsed_ms["publish"] is None


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
