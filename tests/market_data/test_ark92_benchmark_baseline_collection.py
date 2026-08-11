"""ARK-92 collection rules for the Plan 03 benchmark baselines."""

from __future__ import annotations

import hashlib
import json
import stat
import subprocess
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
    ArtifactReceiptV1,
    BaselineCollectionReport,
    BaselineCollectionStatus,
    BaselineWorkloadResult,
    _comparable_valid_count,
    collect_baseline_samples,
    collect_benchmark_baselines,
    read_baseline_artifact,
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
        "Asia/Kolkata",
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
    checksum_months = {
        "B01": ((2024, 2),),
        "B02": ((2024, 1), (2024, 2), (2024, 3)),
        "B03": ((2024, 2),),
        "B04": ((2024, 2),),
        "B05": tuple((2023, month) for month in range(1, 13)),
    }[workload_id]
    checksums = tuple(
        (year, month, f"{month:x}" * 64) for year, month in checksum_months
    )
    control = (
        benchmark_measurement._ControlPartitionEvidence(
            ("synthetic", "NSE", "NSE_EQ", "EQ", "fixture", "1m", 2024, 1),
            "a" * 64,
            "a" * 64,
            "b" * 64,
            "b" * 64,
            "d" * 64,
        )
        if workload_id == "B03" and outcome == "SUCCEEDED"
        else None
    )
    partition_outcomes, reconciliation_reasons, counts = {
        "B01": (("VERIFIED",), (), (1, 1, 0, 0, 0)),
        "B02": (
            ("SKIPPED_VERIFIED", "SKIPPED_VERIFIED", "RECOVERED_LOCALLY"),
            (),
            (0, 0, 0, 3, 0),
        ),
        "B03": (("VERIFIED",), ("CHECKSUM_INVALID_OR_MISMATCHED",), (1, 1, 0, 0, 1)),
        "B04": ((), (), (0, 0, 0, 0, 0)),
        "B05": ((), (), (0, 0, 0, 0, 0)),
    }[workload_id]
    return B01MeasurementRecord(
        workload_id,
        iteration_kind,
        iteration_index,
        "a" * 40,
        "b" * 40,
        "c" * 64,
        "3.13.7",
        "macOS",
        "arch",
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
        len(checksums),
        checksums,
        1,
        1,
        {"normalize": 1, "validate": 1, "publish": 1, "catalog": 1, "query": None},
        1,
        1,
        1,
        1,
        1.0,
        counts[0],
        counts[1],
        counts[2],
        counts[3],
        counts[4],
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
        partition_outcomes,
        reconciliation_reasons,
        control,
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
            partition_checksums=checksums,
            source_data_shape=SourceDataShape(1, 1, 1, 1),
            sampler_method="psutil-parent-child-v1",
            psutil_version="7.2.2",
            cpu_architecture="arch",
            cpu_count=1,
            filesystem_type="apfs",
        ),
    )


def _terminal_artifact_record(
    workload_id: str,
    iteration_kind: str,
    iteration_index: int,
    *,
    outcome: str,
    failure_code: str,
) -> B01MeasurementRecord:
    base = _artifact_record(workload_id, iteration_kind, iteration_index)
    protocol_invalid = failure_code == "CHILD_PROTOCOL_INVALID"
    checksums = () if protocol_invalid else base.partition_checksums
    return replace(
        base,
        outcome=outcome,
        failure_code=failure_code,
        phase_elapsed_ms={
            "normalize": None,
            "validate": None,
            "publish": None,
            "catalog": None,
            "query": None,
        },
        rows_raw=0,
        rows_normalized=0,
        rows_published=0,
        bytes_parquet=0,
        throughput_rows_per_s=None,
        request_count=0,
        provider_attempt_count=0,
        retry_count=0,
        resume_count=0,
        repair_count=0,
        resource_evidence_status=(
            ResourceEvidenceStatus.INVALID
            if protocol_invalid
            else ResourceEvidenceStatus.VALID
        ),
        resource_blocker="CHILD_PROTOCOL_INVALID" if protocol_invalid else None,
        peak_rss_bytes=None if protocol_invalid else base.peak_rss_bytes,
        open_fd_start=None if protocol_invalid else base.open_fd_start,
        open_fd_peak=None if protocol_invalid else base.open_fd_peak,
        open_fd_end=None if protocol_invalid else base.open_fd_end,
        partition_outcomes=(),
        reconciliation_reasons=(),
        control_partition_evidence=None,
        query_result_count=None,
        query_min_ts=None,
        query_max_ts=None,
        query_elapsed_ms=None,
        partition_checksums=checksums,
        comparability_key=replace(
            base.comparability_key,
            partition_checksums=checksums,
            source_data_shape=SourceDataShape(0, 0, 0, 0),
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
                _terminal_artifact_record(
                    "B03",
                    "measured",
                    3,
                    outcome="CANCELLED",
                    failure_code="BENCHMARK_CHILD_CANCELLED",
                ),
                _terminal_artifact_record(
                    "B03",
                    "measured",
                    4,
                    outcome="FAILED",
                    failure_code="CHILD_PROTOCOL_INVALID",
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


def _allow_stable_source(monkeypatch: pytest.MonkeyPatch) -> None:
    identity = baseline_collection._SourceIdentityV1("a" * 40, "b" * 40, "c" * 64)
    monkeypatch.setattr(
        baseline_collection, "_capture_source_identity", lambda: identity
    )
    monkeypatch.setattr(
        baseline_collection,
        "_source_identity_matches",
        lambda value: value == identity,
    )


def test_write_baseline_artifact_serializes_complete_sanitized_report_atomically(
    tmp_path: Path,
) -> None:
    output = tmp_path / "baseline.json"

    receipt = write_baseline_artifact(_artifact_report(), output)

    assert receipt == ArtifactReceiptV1(
        "ark92-baseline-receipt-v1",
        output.stat().st_size,
        hashlib.sha256(output.read_bytes()).hexdigest(),
    )
    assert stat.S_IMODE(output.stat().st_mode) == 0o400
    payload = read_baseline_artifact(output, receipt)
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


def test_ark93_reader_rejects_changed_or_replaced_artifact(
    tmp_path: Path,
) -> None:
    output = tmp_path / "baseline.json"
    receipt = write_baseline_artifact(_artifact_report(), output)
    original = output.read_bytes()
    output.chmod(0o600)
    output.write_bytes(original.replace(b'"B01"', b'"B00"', 1))
    output.chmod(0o400)

    with pytest.raises(ValueError, match="immutable baseline artifact"):
        read_baseline_artifact(output, receipt)

    output.unlink()
    outside = tmp_path / "outside.json"
    outside.write_bytes(original)
    outside.chmod(0o400)
    output.symlink_to(outside)
    with pytest.raises(ValueError, match="immutable baseline artifact"):
        read_baseline_artifact(output, receipt)


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
    if field_name == "cpu_model":
        identity = replace(identity, cpu_architecture=unsafe_value)
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


def test_identity_text_validation_accepts_timezone_and_rejects_separator_obfuscated_secret(
    tmp_path: Path,
) -> None:
    report = _artifact_report()
    record = report.results[0].warmup
    timezone_record = replace(
        record,
        comparability_key=replace(
            record.comparability_key, schedule_timezone="Asia/Kolkata"
        ),
    )
    write_baseline_artifact(
        replace(
            report,
            results=(
                replace(report.results[0], warmup=timezone_record),
                *report.results[1:],
            ),
        ),
        tmp_path / "timezone.json",
    )

    unsafe = replace(
        record,
        cpu_model="ACCESS-TOKEN",
        comparability_key=replace(
            record.comparability_key, cpu_architecture="ACCESS-TOKEN"
        ),
    )
    with pytest.raises(ValueError, match="unsanitized"):
        baseline_collection._serialize_record(unsafe)


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
        "a" * 64,
        "b" * 64,
        "b" * 64,
        "d" * 64,
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
        "post_physical_checksum": "a" * 64,
        "pre_manifest_fingerprint": "b" * 64,
        "post_manifest_fingerprint": "b" * 64,
        "manifest_bound_schedule_digest": "d" * 64,
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


@pytest.mark.parametrize(
    "mutate",
    (
        lambda record: replace(record, cpu_model="different-architecture"),
        lambda record: replace(record, python_version="3.14.1"),
        lambda record: replace(
            record,
            phase_elapsed_ms={
                "normalize": -1,
                "validate": 1,
                "publish": 1,
                "catalog": 1,
                "query": None,
            },
        ),
        lambda record: replace(record, physical_month_count=2),
        lambda record: replace(
            record, partition_checksums=(record.partition_checksums[0],) * 2
        ),
        lambda record: replace(record, peak_rss_bytes=None),
        lambda record: replace(record, sampler_max_gap_ms=51),
        lambda record: replace(
            record,
            resource_evidence_status=ResourceEvidenceStatus.INVALID,
            resource_blocker=None,
        ),
        lambda record: replace(record, outcome="SUCCEEDED", failure_code="FAILED"),
        lambda record: replace(
            record,
            control_partition_evidence=benchmark_measurement._ControlPartitionEvidence(
                ("only",), "a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64
            ),
        ),
    ),
)
def test_write_baseline_artifact_rejects_final_matrix_invariants(
    tmp_path: Path, mutate: object
) -> None:
    report = _artifact_report()
    record = report.results[0].warmup
    malformed = mutate(record)  # type: ignore[operator]

    with pytest.raises(ValueError):
        baseline_collection._serialize_record(malformed)


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

    def write_then_fail(descriptor: int, _encoded: bytes) -> None:
        baseline_collection.os.write(descriptor, b"partial")
        raise OSError("write failed")

    monkeypatch.setattr(baseline_collection, "_write_temporary_fd", write_then_fail)

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

    def competing_link(_temporary: str, destination: str, **kwargs: object) -> None:
        output.write_text("concurrent artifact")
        raise FileExistsError("destination exists")

    monkeypatch.setattr(baseline_collection.os, "link", competing_link)

    with pytest.raises(FileExistsError, match="destination exists"):
        write_baseline_artifact(_artifact_report(), output)

    assert output.read_text() == "concurrent artifact"
    assert tuple(tmp_path.iterdir()) == (output,)


def test_write_baseline_artifact_keeps_linked_output_after_directory_fsync_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "baseline.json"
    calls = 0
    actual_fsync = baseline_collection.os.fsync

    def fail_directory_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("directory fsync failed")
        actual_fsync(descriptor)

    monkeypatch.setattr(baseline_collection.os, "fsync", fail_directory_fsync)

    with pytest.raises(OSError, match="directory fsync failed"):
        write_baseline_artifact(_artifact_report(), output)

    assert output.is_file()
    assert tuple(tmp_path.iterdir()) == (output,)


def test_write_baseline_artifact_rejects_symlinked_parent_without_following_it(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(target, target_is_directory=True)

    with pytest.raises(OSError):
        write_baseline_artifact(_artifact_report(), linked_parent / "baseline.json")

    assert tuple(target.iterdir()) == ()


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
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[Path] = []
    output = tmp_path / "artifact" / "baseline.json"
    work_root = tmp_path / "artifact" / "work"
    monkeypatch.setattr(baseline_collection, "_ARTIFACTS_ROOT", tmp_path / "artifact")
    _allow_stable_source(monkeypatch)

    def collect_from_frozen_root(root: Path) -> BaselineCollectionReport:
        calls.append(root)
        assert benchmark_measurement._BENCHMARK_RUNTIME.process_context == "fork"
        assert benchmark_measurement._BENCHMARK_RUNTIME.source_identity == (
            "a" * 40,
            "b" * 40,
            "c" * 64,
        )
        return _artifact_report()

    monkeypatch.setattr(
        baseline_collection,
        "collect_benchmark_baselines",
        collect_from_frozen_root,
    )

    assert (
        persist_baseline_artifact(
            ["--output", str(output), "--work-root", str(work_root)]
        )
        == 0
    )
    assert len(calls) == 1
    assert benchmark_measurement._BENCHMARK_RUNTIME.process_context == "spawn"
    assert benchmark_measurement._BENCHMARK_RUNTIME.source_identity is None
    assert calls[0] != work_root
    assert calls[0] == Path(".")
    assert output.is_file()
    assert stat.S_IMODE(output.stat().st_mode) == 0o400
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == {
        "byte_count": output.stat().st_size,
        "schema_version": "ark92-baseline-receipt-v1",
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }

    assert (
        persist_baseline_artifact(
            ["--output", str(output), "--work-root", str(work_root)]
        )
        == 2
    )
    assert len(calls) == 1


def test_persistence_rejects_dangling_output_symlink_without_redirecting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir(mode=0o700)
    output = artifact_root / "baseline.json"
    redirected = artifact_root / "redirected.json"
    output.symlink_to(redirected)
    monkeypatch.setattr(baseline_collection, "_ARTIFACTS_ROOT", artifact_root)

    assert (
        persist_baseline_artifact(
            [
                "--output",
                str(output),
                "--work-root",
                str(artifact_root / "work"),
            ]
        )
        == 2
    )
    assert capsys.readouterr().err.endswith("OUTPUT_EXISTS\n")
    assert output.is_symlink()
    assert not redirected.exists()


def test_persistence_rejects_public_output_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir(mode=0o777)
    monkeypatch.setattr(baseline_collection, "_ARTIFACTS_ROOT", artifact_root)

    assert (
        persist_baseline_artifact(
            [
                "--output",
                str(artifact_root / "baseline.json"),
                "--work-root",
                str(artifact_root / "work"),
            ]
        )
        == 2
    )
    assert capsys.readouterr().err.endswith("PERSISTENCE_FAILED\n")
    assert tuple(artifact_root.iterdir()) == ()


def test_persistence_rejects_private_child_below_public_artifact_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir(mode=0o777)
    private_child = artifact_root / "private"
    private_child.mkdir(mode=0o700)
    monkeypatch.setattr(baseline_collection, "_ARTIFACTS_ROOT", artifact_root)

    assert (
        persist_baseline_artifact(
            [
                "--output",
                str(private_child / "baseline.json"),
                "--work-root",
                str(private_child / "work"),
            ]
        )
        == 2
    )
    assert capsys.readouterr().err.endswith("PERSISTENCE_FAILED\n")
    assert tuple(private_child.iterdir()) == ()


def test_persistence_rejects_dirty_reviewed_source_before_collection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir(mode=0o700)
    calls: list[Path] = []
    monkeypatch.setattr(baseline_collection, "_ARTIFACTS_ROOT", artifact_root)
    monkeypatch.setattr(
        baseline_collection.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, " M source.py\n", ""
        ),
    )
    monkeypatch.setattr(
        baseline_collection,
        "collect_benchmark_baselines",
        lambda root: calls.append(root) or _artifact_report(),
    )

    assert (
        persist_baseline_artifact(
            [
                "--output",
                str(artifact_root / "baseline.json"),
                "--work-root",
                str(artifact_root / "work"),
            ]
        )
        == 2
    )
    assert capsys.readouterr().err.endswith("SOURCE_UNCLEAN\n")
    assert calls == []


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


def test_persistence_entry_point_sanitizes_unexpected_collection_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir(mode=0o700)
    monkeypatch.setattr(baseline_collection, "_ARTIFACTS_ROOT", artifact_root)
    _allow_stable_source(monkeypatch)

    def fail_once(_root: Path) -> BaselineCollectionReport:
        raise RuntimeError(str(tmp_path))

    monkeypatch.setattr(baseline_collection, "collect_benchmark_baselines", fail_once)

    assert (
        persist_baseline_artifact(
            [
                "--output",
                str(artifact_root / "baseline.json"),
                "--work-root",
                str(artifact_root / "work"),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.err == "baseline artifact collection failed: COLLECTION_FAILED\n"
    assert str(tmp_path) not in captured.err


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


@pytest.mark.parametrize(
    ("terminal", "outcome", "failure_code"),
    (
        ("cancelled", "CANCELLED", "BENCHMARK_CHILD_CANCELLED"),
        ("invalid", "FAILED", "CHILD_PROTOCOL_INVALID"),
    ),
)
def test_b01_cancelled_and_protocol_invalid_iterations_are_retained(
    tmp_path: Path, terminal: str, outcome: str, failure_code: str
) -> None:
    record = measure_b01(
        tmp_path,
        iteration_kind="measured",
        iteration_index=1,
        child_terminal=terminal,  # type: ignore[arg-type]
    )

    assert record.outcome == outcome
    assert record.failure_code == failure_code
    assert record.rows_raw == record.rows_normalized == record.rows_published == 0
    assert record.request_count == record.provider_attempt_count == 0
    assert record.partition_outcomes == ()


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


@pytest.mark.parametrize(
    ("workload_id", "months"),
    (
        ("B01", ((2024, 2),)),
        ("B02", ((2024, 1), (2024, 2), (2024, 3))),
        ("B03", ((2024, 2),)),
        ("B04", ((2024, 2),)),
        ("B05", tuple((2023, month) for month in range(1, 13))),
    ),
)
def test_write_baseline_artifact_requires_exact_plan03_checksum_months(
    tmp_path: Path, workload_id: str, months: tuple[tuple[int, int], ...]
) -> None:
    report = _artifact_report()
    index = ("B01", "B02", "B03", "B04", "B05").index(workload_id)
    record = report.results[index].warmup
    checksums = tuple((year, month, "f" * 64) for year, month in months)
    wrong_month = (checksums[0][0], checksums[0][1] % 12 + 1, "e" * 64)
    malformed_checksums = (wrong_month, *checksums[1:])
    malformed = replace(
        record,
        partition_checksums=malformed_checksums,
        comparability_key=replace(
            record.comparability_key, partition_checksums=malformed_checksums
        ),
    )

    with pytest.raises(ValueError, match="physical workload"):
        baseline_collection._serialize_record(malformed)


def test_successful_b03_control_keeps_its_own_manifest_bound_digest(
    tmp_path: Path,
) -> None:
    report = _artifact_report()
    record = report.results[2].warmup
    control = replace(
        record.control_partition_evidence,
        manifest_bound_schedule_digest="c" * 64,
    )
    b03 = replace(
        report.results[2], warmup=replace(record, control_partition_evidence=control)
    )

    write_baseline_artifact(
        replace(report, results=(*report.results[:2], b03, *report.results[3:])),
        tmp_path / "baseline.json",
    )


@pytest.mark.parametrize("field_name", ("fixture_id", "platform", "cpu_model"))
def test_write_baseline_artifact_rejects_opaque_uri_text(
    tmp_path: Path, field_name: str
) -> None:
    report = _artifact_report()
    record = report.results[0].warmup
    identity = record.comparability_key
    if field_name == "fixture_id":
        identity = replace(identity, fixture_id="https:opaque")
    if field_name == "cpu_model":
        identity = replace(identity, cpu_architecture="https:opaque")
    unsafe = replace(
        record,
        comparability_key=identity,
        **{field_name: "https:opaque"},
    )

    with pytest.raises(ValueError, match="unsanitized"):
        baseline_collection._serialize_record(unsafe)


def test_child_protocol_invalid_is_retained_with_closed_invalid_resource_evidence(
    tmp_path: Path,
) -> None:
    report = _artifact_report()
    record = report.results[2].measured[3]
    invalid = replace(
        record,
        resource_evidence_status=ResourceEvidenceStatus.INVALID,
        resource_blocker="CHILD_PROTOCOL_INVALID",
        peak_rss_bytes=None,
        open_fd_start=None,
        open_fd_peak=None,
        open_fd_end=None,
    )
    b03 = replace(
        report.results[2],
        measured=(
            *report.results[2].measured[:3],
            invalid,
            report.results[2].measured[4],
        ),
    )

    write_baseline_artifact(
        replace(report, results=(*report.results[:2], b03, *report.results[3:])),
        tmp_path / "baseline.json",
    )

    payload = json.loads((tmp_path / "baseline.json").read_text())
    retained = payload["results"][2]["measured"][3]
    assert retained["outcome"] == "FAILED"
    assert (
        retained["failure_code"]
        == retained["resource_blocker"]
        == "CHILD_PROTOCOL_INVALID"
    )
    assert retained["resource_evidence_status"] == "INVALID"


@pytest.mark.parametrize(
    "mutate",
    (
        lambda record: replace(record, partition_outcomes=("VERIFIED",)),
        lambda record: replace(record, resume_count=2),
        lambda record: replace(
            record, reconciliation_reasons=("CHECKSUM_INVALID_OR_MISMATCHED",)
        ),
    ),
)
def test_successful_workload_requires_exact_partition_and_count_cardinality(
    mutate: object,
) -> None:
    record = _artifact_record("B02", "measured", 1)

    with pytest.raises(ValueError, match="successful workload"):
        baseline_collection._serialize_record(mutate(record))  # type: ignore[operator]


def test_successful_b03_requires_its_exact_repair_cardinality() -> None:
    record = _artifact_record("B03", "measured", 1)

    with pytest.raises(ValueError, match="successful workload"):
        baseline_collection._serialize_record(replace(record, repair_count=0))


def test_write_baseline_artifact_rejects_symlinked_ancestor_without_creating_outside(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        write_baseline_artifact(_artifact_report(), linked / "nested" / "baseline.json")

    assert tuple(outside.iterdir()) == ()


def test_collect_then_serialize_keeps_distinct_b03_control_digest(
    tmp_path: Path,
) -> None:
    def measure(workload_id: str, kind: str, index: int) -> B01MeasurementRecord:
        record = _artifact_record(workload_id, kind, index)
        if workload_id == "B03":
            return replace(
                record,
                control_partition_evidence=replace(
                    record.control_partition_evidence,
                    manifest_bound_schedule_digest="c" * 64,
                ),
            )
        return record

    report = collect_baseline_samples(tmp_path / "work", measure)
    write_baseline_artifact(report, tmp_path / "baseline.json")

    payload = json.loads((tmp_path / "baseline.json").read_text())
    b03 = payload["results"][2]["warmup"]
    assert (
        b03["control_partition_evidence"]["manifest_bound_schedule_digest"]
        != b03["schedule_digest"]
    )


@pytest.mark.parametrize("field_name", ("cpu_count", "physical_month_count"))
def test_write_baseline_artifact_rejects_bool_as_integer_measurement(
    field_name: str,
) -> None:
    record = _artifact_report().results[0].warmup

    with pytest.raises(ValueError):
        baseline_collection._serialize_record(replace(record, **{field_name: True}))


@pytest.mark.parametrize("exception", (KeyboardInterrupt, SystemExit))
def test_persistence_entry_point_propagates_process_control_exceptions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, exception: type[BaseException]
) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir(mode=0o700)
    monkeypatch.setattr(baseline_collection, "_ARTIFACTS_ROOT", artifact_root)
    _allow_stable_source(monkeypatch)

    def abort(_root: Path) -> BaselineCollectionReport:
        raise exception()

    monkeypatch.setattr(baseline_collection, "collect_benchmark_baselines", abort)

    with pytest.raises(exception):
        persist_baseline_artifact(
            [
                "--output",
                str(artifact_root / "baseline.json"),
                "--work-root",
                str(artifact_root / "work"),
            ]
        )


def test_persistence_rejects_work_root_substitution_before_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.mkdir()
    output = artifact_root / "baseline.json"
    work_root = artifact_root / "work"
    monkeypatch.setattr(baseline_collection, "_ARTIFACTS_ROOT", artifact_root)
    _allow_stable_source(monkeypatch)

    held = tmp_path / "held-work"

    def substitute(root: Path) -> BaselineCollectionReport:
        work_root.rename(held)
        work_root.symlink_to(outside, target_is_directory=True)
        (root / "descriptor-bound.txt").write_text("bound")
        work_root.unlink()
        held.rename(work_root)
        return _artifact_report()

    monkeypatch.setattr(baseline_collection, "collect_benchmark_baselines", substitute)

    assert (
        persist_baseline_artifact(
            ["--output", str(output), "--work-root", str(work_root)]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["schema_version"] == (
        "ark92-baseline-receipt-v1"
    )
    assert output.exists()
    assert (work_root / "descriptor-bound.txt").read_text() == "bound"
    assert tuple(outside.iterdir()) == ()


def test_persistence_stops_if_reviewed_source_identity_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir(mode=0o700)
    identity = baseline_collection._SourceIdentityV1("a" * 40, "b" * 40, "c" * 64)
    checks = iter((True, False))
    monkeypatch.setattr(baseline_collection, "_ARTIFACTS_ROOT", artifact_root)
    monkeypatch.setattr(
        baseline_collection, "_capture_source_identity", lambda: identity
    )
    monkeypatch.setattr(
        baseline_collection,
        "_source_identity_matches",
        lambda _value: next(checks),
    )
    monkeypatch.setattr(
        baseline_collection,
        "collect_benchmark_baselines",
        lambda _root: _artifact_report(),
    )

    assert (
        persist_baseline_artifact(
            [
                "--output",
                str(artifact_root / "baseline.json"),
                "--work-root",
                str(artifact_root / "work"),
            ]
        )
        == 2
    )
    assert capsys.readouterr().err.endswith("SOURCE_CHANGED\n")
    assert not (artifact_root / "baseline.json").exists()


@pytest.mark.parametrize(
    "record",
    (
        replace(
            _terminal_artifact_record(
                "B01",
                "measured",
                1,
                outcome="FAILED",
                failure_code="B01_CHILD_FAILED",
            ),
            outcome="FAILED",
            failure_code="BENCHMARK_CHILD_FAILED",
        ),
        replace(
            _terminal_artifact_record(
                "B02",
                "measured",
                1,
                outcome="FAILED",
                failure_code="BENCHMARK_CHILD_FAILED",
            ),
            outcome="FAILED",
            failure_code="B01_CHILD_FAILED",
        ),
        replace(
            _terminal_artifact_record(
                "B02",
                "measured",
                1,
                outcome="FAILED",
                failure_code="BENCHMARK_CHILD_FAILED",
            ),
            outcome="CANCELLED",
            failure_code="BENCHMARK_CHILD_FAILED",
        ),
        replace(
            _terminal_artifact_record(
                "B02",
                "measured",
                1,
                outcome="FAILED",
                failure_code="BENCHMARK_CHILD_FAILED",
            ),
            outcome="FAILED",
            failure_code="BENCHMARK_CHILD_CANCELLED",
        ),
        replace(
            _terminal_artifact_record(
                "B02",
                "measured",
                1,
                outcome="FAILED",
                failure_code="BENCHMARK_CHILD_FAILED",
            ),
            outcome="FAILED",
            failure_code="BENCHMARK_CHILD_PROTOCOL_INVALID",
        ),
    ),
)
def test_terminal_failure_code_matrix_is_closed(record: B01MeasurementRecord) -> None:
    with pytest.raises(ValueError, match="terminal outcome"):
        baseline_collection._serialize_record(record)


@pytest.mark.parametrize(
    "changes",
    (
        {"request_count": 1},
        {"provider_attempt_count": 1},
        {"retry_count": 1},
        {"resume_count": 1},
        {"repair_count": 1},
        {"rows_raw": 1},
        {"rows_normalized": 1},
        {"rows_published": 1},
        {"bytes_parquet": 1},
        {"throughput_rows_per_s": 1.0},
        {"partition_outcomes": ("VERIFIED",)},
        {"reconciliation_reasons": ("CHECKSUM_INVALID_OR_MISMATCHED",)},
        {
            "phase_elapsed_ms": {
                "normalize": 1,
                "validate": None,
                "publish": None,
                "catalog": None,
                "query": None,
            }
        },
        {"query_result_count": 1},
        {"query_min_ts": "2024-02-01T03:45:00.000000Z"},
        {"query_max_ts": "2024-02-01T03:45:00.000000Z"},
        {"query_elapsed_ms": 1},
    ),
)
def test_non_success_records_reject_success_or_activity_evidence(
    changes: dict[str, object],
) -> None:
    base = _terminal_artifact_record(
        "B02",
        "measured",
        1,
        outcome="FAILED",
        failure_code="BENCHMARK_CHILD_FAILED",
    )
    shape_values = {
        "rows_raw": changes.get("rows_raw", base.rows_raw),
        "rows_normalized": changes.get("rows_normalized", base.rows_normalized),
        "rows_published": changes.get("rows_published", base.rows_published),
        "bytes_parquet": changes.get("bytes_parquet", base.bytes_parquet),
    }
    record = replace(
        base,
        comparability_key=replace(
            base.comparability_key,
            source_data_shape=SourceDataShape(**shape_values),  # type: ignore[arg-type]
        ),
        **changes,
    )

    with pytest.raises(ValueError, match="terminal workload"):
        baseline_collection._serialize_record(record)


@pytest.mark.parametrize(
    "phase_evidence",
    (object(), {"normalize": None}),
)
def test_non_success_phase_shape_fails_closed_as_value_error(
    phase_evidence: object,
) -> None:
    record = replace(
        _terminal_artifact_record(
            "B02",
            "measured",
            1,
            outcome="FAILED",
            failure_code="BENCHMARK_CHILD_FAILED",
        ),
        phase_elapsed_ms=phase_evidence,  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="terminal workload"):
        baseline_collection._serialize_record(record)


@pytest.mark.parametrize(
    "changes",
    (
        {
            "resource_evidence_status": ResourceEvidenceStatus.VALID,
            "resource_blocker": None,
            "peak_rss_bytes": 1,
            "open_fd_start": 1,
            "open_fd_peak": 1,
            "open_fd_end": 1,
        },
        {"resource_blocker": "sampling_exception"},
    ),
)
def test_protocol_invalid_requires_exact_closed_resource_pairing(
    changes: dict[str, object],
) -> None:
    values = {
        "resource_evidence_status": ResourceEvidenceStatus.INVALID,
        "resource_blocker": "CHILD_PROTOCOL_INVALID",
        "peak_rss_bytes": None,
        "open_fd_start": None,
        "open_fd_peak": None,
        "open_fd_end": None,
        **changes,
    }
    record = replace(
        _terminal_artifact_record(
            "B02",
            "measured",
            1,
            outcome="FAILED",
            failure_code="CHILD_PROTOCOL_INVALID",
        ),
        **values,
    )

    with pytest.raises(ValueError, match="protocol"):
        baseline_collection._serialize_record(record)


@pytest.mark.parametrize("text", ("s.e.l.e.c.t", "u n i o n", "pr-ag-ma"))
def test_obfuscated_sql_text_is_rejected(text: str) -> None:
    record = replace(_artifact_record("B01", "measured", 1), platform=text)

    with pytest.raises(ValueError, match="unsanitized"):
        baseline_collection._serialize_record(record)


def test_artifact_evidence_has_explicit_text_sequence_numeric_and_byte_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _artifact_record("B01", "measured", 1)
    oversized_text = replace(base, platform="A" * 513)
    oversized_number = replace(base, memory_total_bytes=2**63)
    oversized_sequence = replace(
        base,
        comparability_key=replace(
            base.comparability_key,
            schedule_closure_provenance=tuple(
                ("closure", "source") for _ in range(367)
            ),
        ),
    )

    for record in (oversized_text, oversized_number, oversized_sequence):
        with pytest.raises(ValueError, match="bounded|unsanitized|numeric"):
            baseline_collection._serialize_record(record)

    monkeypatch.setattr(baseline_collection, "_MAX_ARTIFACT_BYTES", 10)
    with pytest.raises(ValueError, match="artifact.*bound"):
        baseline_collection._serialize_report(_artifact_report())


def test_plan_pre_registers_the_one_shot_durable_artifact_boundary() -> None:
    plan = (
        Path(__file__).resolve().parents[2]
        / "docs/plans/03-reliance-operational-validation-and-benchmarks.md"
    ).read_text()

    assert "### 5.5 Durable one-shot baseline artifact" in plan
    assert "hard maximum of 4,000,000 bytes" in plan
    assert "ark92-baseline-artifact-v1" in plan
    assert "one warm-up, five measured records" in plan
    assert "threshold_claim=null" in plan
    assert "strings are at most 512 bytes" in plan
    assert "ordered evidence at most 366 items" in plan
    assert "integer evidence at most signed 64-bit maximum" in plan
    assert "tests/market_data/ark92_benchmark_baseline_collection.py" in plan
    assert "ark92-b01-b05-baseline-v1.json" in plan
    assert "ARK-93 consumes that exact immutable file" in plan


def test_persistence_rejects_work_root_permission_substitution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir(mode=0o700)
    output = artifact_root / "baseline.json"
    work_root = artifact_root / "work"
    monkeypatch.setattr(baseline_collection, "_ARTIFACTS_ROOT", artifact_root)
    _allow_stable_source(monkeypatch)

    def substitute(root: Path) -> BaselineCollectionReport:
        root.chmod(0o777)
        return _artifact_report()

    monkeypatch.setattr(baseline_collection, "collect_benchmark_baselines", substitute)

    assert (
        persist_baseline_artifact(
            ["--output", str(output), "--work-root", str(work_root)]
        )
        == 2
    )
    assert (
        capsys.readouterr().err
        == "baseline artifact collection failed: WORK_ROOT_SUBSTITUTED\n"
    )
    assert not output.exists()


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
