from __future__ import annotations

from pathlib import Path

import pytest
from ark90_benchmark_measurement import (
    ResourceEvidenceStatus,
    measure_b01,
)


def test_b01_fresh_child_measurement_records_complete_sanitized_evidence(
    tmp_path: Path,
) -> None:
    record = measure_b01(tmp_path, iteration_kind="measured", iteration_index=1)

    assert record.workload_id == "B01"
    assert record.iteration_kind == "measured"
    assert record.iteration_index == 1
    assert record.fixture_id == "benchmark-nse-eq-v1"
    assert record.fixture_version == "benchmark-nse-eq-v1"
    assert record.schedule_digest == (
        "32b239c6e8924bdf4fb676f0f2b8b070c14869e9d3202badc001b20e863b17fd"
    )
    assert record.policy_version == "nse-equity-month@v1"
    assert record.requested_range == "2024-02-01..2024-02-29"
    assert record.physical_month_count == 1
    assert len(record.partition_checksums) == 1
    assert record.partition_checksums[0][:2] == (2024, 2)
    assert len(record.partition_checksums[0][2]) == 64
    assert record.rows_raw == record.rows_normalized == record.rows_published == 7_500
    assert record.bytes_parquet > 0
    assert record.request_count == record.provider_attempt_count == 1
    assert record.retry_count == record.resume_count == record.repair_count == 0
    assert record.outcome == "SUCCEEDED"
    assert record.failure_code == "NONE"
    assert record.partition_outcomes == ("VERIFIED",)
    assert record.phase_elapsed_ms == {
        "normalize": None,
        "validate": None,
        "publish": None,
        "catalog": None,
        "query": None,
    }
    assert record.query_result_count is None
    assert record.query_min_ts is None
    assert record.query_max_ts is None
    assert record.query_elapsed_ms is None
    assert record.elapsed_wall_ms >= 0
    assert record.elapsed_cpu_ms >= 0
    assert record.throughput_rows_per_s is not None
    assert record.sampler_method == "psutil-parent-child-v1"
    assert record.psutil_version == "7.2.2"
    if record.resource_evidence_status is ResourceEvidenceStatus.VALID:
        assert record.peak_rss_bytes is not None
        assert record.open_fd_start is not None
        assert record.open_fd_peak is not None
        assert record.open_fd_end == record.open_fd_start
        assert record.open_fd_peak >= record.open_fd_start
        assert record.sampler_sample_count >= 2
        assert record.sampler_max_gap_ms is not None
        assert record.sampler_max_gap_ms <= 50
    else:
        assert record.resource_blocker == "max_gap_exceeded"
        assert record.peak_rss_bytes is None
        assert record.open_fd_start is None
        assert record.open_fd_peak is None
        assert record.open_fd_end is None
        assert record.sampler_sample_count == 0
        assert record.sampler_max_gap_ms is None
    assert record.source_revision
    assert record.source_tree
    assert len(record.lock_identity) == 64
    assert record.python_version
    assert record.platform
    assert record.cpu_model
    assert record.cpu_count > 0
    assert record.memory_total_bytes > 0
    assert record.filesystem_type
    assert record.duckdb_version
    assert record.pyarrow_version
    assert record.os_version

    rendered = repr(record)
    for forbidden in (str(tmp_path), "NSE_EQ|", "TESTEQ", "INE000A01000", "pid="):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    ("failure", "expected", "sample_count", "has_gap"),
    [
        ("sampling_exception", "sampling_exception", 0, False),
        ("unsupported_num_fds", "unsupported_num_fds", 0, False),
        ("too_few_samples", "too_few_samples", 1, False),
        ("gap_exceeded", "max_gap_exceeded", 2, True),
    ],
)
def test_b01_invalid_resource_sampling_retains_sampler_provenance(
    tmp_path: Path,
    failure: str,
    expected: str,
    sample_count: int,
    has_gap: bool,
) -> None:
    record = measure_b01(
        tmp_path,
        iteration_kind="warmup",
        iteration_index=1,
        sampler_failure=failure,
    )

    assert record.resource_evidence_status is ResourceEvidenceStatus.INVALID
    assert record.resource_blocker == expected
    assert record.open_fd_start is None
    assert record.open_fd_peak is None
    assert record.open_fd_end is None
    assert record.peak_rss_bytes is None
    assert record.sampler_sample_count >= sample_count
    if has_gap:
        assert record.sampler_max_gap_ms is not None
        assert record.sampler_max_gap_ms > 50
    else:
        assert record.sampler_max_gap_ms is None
    assert record.outcome == "SUCCEEDED"
    assert record.request_count == record.provider_attempt_count == 1


def test_b01_rejects_nonpositive_iteration_and_unknown_sampler_failure(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="iteration"):
        measure_b01(tmp_path, iteration_kind="measured", iteration_index=0)
    with pytest.raises(ValueError, match="sampler failure"):
        measure_b01(
            tmp_path,
            iteration_kind="measured",
            iteration_index=1,
            sampler_failure="unknown",
        )
