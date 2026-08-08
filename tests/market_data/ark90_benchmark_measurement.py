"""Test-only Plan 03 B01 fresh-child measurement harness."""

from __future__ import annotations

import hashlib
import multiprocessing
import os
import platform as runtime_platform
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Literal

import duckdb
import psutil
import pyarrow
from ark74_benchmark_fixture import BenchmarkFixturePartition, benchmark_nse_eq_v1

from swing_trading_ai_assistant.market_data.historical import (
    HistoricalRequest,
    HistoricalResponse,
)
from swing_trading_ai_assistant.market_data.range_ingestion import (
    IngestionCommand,
    IngestionCoordinator,
    IngestionReport,
)

_CONTROL_TIMEOUT_S = 30.0
_SAMPLING_INTERVAL_S = 0.01
_MAX_SAMPLING_GAP_MS = 50
_PSUTIL_VERSION = "7.2.2"
_SAMPLER_METHOD = "psutil-parent-child-v1"
_PhaseElapsed = dict[str, int | None]
_SamplerFailure = Literal[
    "sampling_exception", "unsupported_num_fds", "too_few_samples", "gap_exceeded"
]


class ResourceEvidenceStatus(StrEnum):
    """Explicit resource-evidence outcome; invalid is never a partial pass."""

    VALID = "VALID"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class B01MeasurementRecord:
    """Sanitized Plan 03 section 5.2 evidence for one B01 iteration."""

    workload_id: str
    iteration_kind: str
    iteration_index: int
    source_revision: str
    source_tree: str
    lock_identity: str
    python_version: str
    platform: str
    cpu_model: str
    cpu_count: int
    memory_total_bytes: int
    filesystem_type: str
    duckdb_version: str
    pyarrow_version: str
    os_version: str
    fixture_id: str
    fixture_version: str
    schedule_digest: str
    policy_version: str
    requested_range: str
    physical_month_count: int
    partition_checksums: tuple[tuple[int, int, str], ...]
    elapsed_wall_ms: int
    elapsed_cpu_ms: int
    phase_elapsed_ms: _PhaseElapsed
    rows_raw: int
    rows_normalized: int
    rows_published: int
    bytes_parquet: int
    throughput_rows_per_s: float | None
    request_count: int
    provider_attempt_count: int
    retry_count: int
    resume_count: int
    repair_count: int
    peak_rss_bytes: int | None
    open_fd_start: int | None
    open_fd_peak: int | None
    open_fd_end: int | None
    sampler_method: str
    psutil_version: str
    sampler_sample_count: int
    sampler_max_gap_ms: int | None
    resource_evidence_status: ResourceEvidenceStatus
    resource_blocker: str | None
    query_result_count: int | None
    query_min_ts: str | None
    query_max_ts: str | None
    query_elapsed_ms: int | None
    outcome: str
    failure_code: str
    partition_outcomes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ChildB01Result:
    fixture_id: str
    schedule_digest: str
    policy_version: str
    checksum: str
    rows_raw: int
    rows_normalized: int
    rows_published: int
    bytes_parquet: int
    request_count: int
    provider_attempt_count: int
    retry_count: int
    resume_count: int
    repair_count: int
    elapsed_wall_ms: int
    elapsed_cpu_ms: int
    outcome: str
    failure_code: str
    partition_outcomes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ResourceEvidence:
    peak_rss_bytes: int | None
    open_fd_start: int | None
    open_fd_peak: int | None
    open_fd_end: int | None
    sample_count: int
    max_gap_ms: int | None
    status: ResourceEvidenceStatus
    blocker: str | None


@dataclass(frozen=True, slots=True)
class _Sample:
    monotonic_ns: int
    rss_bytes: int
    open_fds: int


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2024, 3, 1, tzinfo=UTC)


class _OneResponseSession:
    def __init__(self, response: HistoricalResponse) -> None:
        self._response = response
        self.requests: list[HistoricalRequest] = []

    def fetch(self, request: HistoricalRequest) -> HistoricalResponse:
        self.requests.append(request)
        return self._response


class _OneResponseSessionFactory:
    def __init__(self, response: HistoricalResponse) -> None:
        self.open_calls = 0
        self.session = _OneResponseSession(response)

    def open(self) -> _OneResponseSession:
        self.open_calls += 1
        return self.session


def measure_b01(
    disposable_parent: Path,
    *,
    iteration_kind: Literal["warmup", "measured"],
    iteration_index: int,
    sampler_failure: _SamplerFailure | None = None,
) -> B01MeasurementRecord:
    """Measure one real B01 ingestion in a fresh child with parent sampling."""
    if iteration_kind not in {"warmup", "measured"} or iteration_index < 1:
        raise ValueError("invalid iteration")
    if sampler_failure not in {None, *get_args_for_sampler_failure()}:
        raise ValueError("invalid sampler failure")
    if psutil.__version__ != _PSUTIL_VERSION:
        raise RuntimeError("locked psutil version is unavailable")

    child_root = disposable_parent / f"b01-{iteration_kind}-{iteration_index}"
    child_root.mkdir()
    parent_connection, child_connection = multiprocessing.get_context("spawn").Pipe()
    child = multiprocessing.get_context("spawn").Process(
        target=_run_b01_child,
        args=(child_connection, str(child_root)),
    )
    child.start()
    child_connection.close()
    try:
        result, resources = _control_and_sample_child(
            parent_connection,
            child,
            sampler_failure,
        )
    finally:
        parent_connection.close()
        _stop_child(child)

    return _record_b01(result, resources, iteration_kind, iteration_index, child_root)


def get_args_for_sampler_failure() -> tuple[_SamplerFailure, ...]:
    """Keep the explicit test-only invalid-sampling injection set closed."""
    return (
        "sampling_exception",
        "unsupported_num_fds",
        "too_few_samples",
        "gap_exceeded",
    )


def _run_b01_child(connection: Connection, root_text: str) -> None:
    try:
        connection.send("READY")
        if connection.recv() != "START":
            return
        connection.send(("DONE", _execute_b01(Path(root_text))))
        connection.recv()
    except Exception:
        connection.send(("ERROR", "B01_CHILD_FAILED"))
    finally:
        connection.close()


def _execute_b01(root: Path) -> _ChildB01Result:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    partition = fixture.partitions[0]
    sessions = _OneResponseSessionFactory(partition.response)
    command = IngestionCommand(
        fixture.instrument,
        date(2024, 2, 1),
        date(2024, 2, 29),
        "1m",
        root,
        fixture.schedule,
        fixture.validation_policy,
        max_total_provider_attempts=1,
    )
    coordinator = IngestionCoordinator(
        session_factory=sessions,
        clock=_FixedClock(),
        run_id_factory=lambda: "ark90-run",
    )
    wall_started = time.monotonic_ns()
    cpu_started = time.process_time_ns()
    report = coordinator.run(command)
    elapsed_cpu_ms = _elapsed_ms(cpu_started, time.process_time_ns())
    elapsed_wall_ms = _elapsed_ms(wall_started, time.monotonic_ns())
    return _child_result(
        report,
        fixture.fixture_id,
        fixture.schedule_digest,
        fixture.validation_policy,
        partition,
        root,
        sessions,
        elapsed_wall_ms,
        elapsed_cpu_ms,
    )


def _child_result(
    report: IngestionReport,
    fixture_id: str,
    schedule_digest: str,
    policy_version: str,
    partition: BenchmarkFixturePartition,
    root: Path,
    sessions: _OneResponseSessionFactory,
    elapsed_wall_ms: int,
    elapsed_cpu_ms: int,
) -> _ChildB01Result:
    result = report.results[0]
    manifest = result.final_manifest
    if (
        report.outcome.value != "SUCCEEDED"
        or report.failure_code.value != "NONE"
        or manifest is None
        or manifest.row_count != 7_500
        or len(sessions.session.requests) != 1
        or sessions.open_calls != 1
    ):
        raise RuntimeError("B01_CHILD_FAILED")
    artifact = root / manifest.canonical_path
    return _ChildB01Result(
        fixture_id,
        schedule_digest,
        policy_version,
        manifest.checksum_sha256,
        partition.raw_count,
        partition.normalized_count,
        manifest.row_count,
        artifact.stat().st_size,
        len(sessions.session.requests),
        report.provider_attempt_count,
        0,
        0,
        0,
        elapsed_wall_ms,
        elapsed_cpu_ms,
        report.outcome.value,
        report.failure_code.value,
        tuple(item.outcome.value for item in report.results),
    )


def _control_and_sample_child(
    connection: Connection,
    child: multiprocessing.Process,
    sampler_failure: _SamplerFailure | None,
) -> tuple[_ChildB01Result, _ResourceEvidence]:
    if not connection.poll(_CONTROL_TIMEOUT_S) or connection.recv() != "READY":
        raise RuntimeError("B01 child did not become ready")
    if child.pid is None:
        raise RuntimeError("B01 child process is unavailable")
    process = psutil.Process(child.pid)
    samples, invalid_blocker = _initial_sample(process, sampler_failure)
    connection.send("START")
    _inject_gap_if_requested(process, samples, sampler_failure, invalid_blocker)
    message = _wait_for_done(connection, process, samples, sampler_failure)
    result = _done_child_result(message)
    invalid_blocker = _end_sample(process, samples, sampler_failure, invalid_blocker)
    connection.send("EXIT")
    invalid_blocker = _sampling_blocker(samples, sampler_failure, invalid_blocker)
    resources = _resource_evidence(samples, invalid_blocker)
    return result, resources


def _initial_sample(
    process: psutil.Process, sampler_failure: _SamplerFailure | None
) -> tuple[list[_Sample], str | None]:
    if sampler_failure == "sampling_exception":
        return [], "sampling_exception"
    if sampler_failure == "unsupported_num_fds":
        return [], "unsupported_num_fds"
    try:
        return [_sample(process)], None
    except Exception:
        return [], "sampling_exception"


def _inject_gap_if_requested(
    process: psutil.Process,
    samples: list[_Sample],
    sampler_failure: _SamplerFailure | None,
    invalid_blocker: str | None,
) -> None:
    if sampler_failure != "gap_exceeded" or invalid_blocker is not None:
        return
    time.sleep((_MAX_SAMPLING_GAP_MS + 1) / 1_000)
    samples.append(_sample(process))


def _done_child_result(message: tuple[object, object]) -> _ChildB01Result:
    if message[0] != "DONE" or type(message[1]) is not _ChildB01Result:
        raise RuntimeError("B01 child failed")
    return message[1]


def _end_sample(
    process: psutil.Process,
    samples: list[_Sample],
    sampler_failure: _SamplerFailure | None,
    invalid_blocker: str | None,
) -> str | None:
    if sampler_failure == "too_few_samples":
        return "too_few_samples"
    if invalid_blocker is not None:
        return invalid_blocker
    try:
        samples.append(_sample(process))
    except Exception:
        return "sampling_exception"
    return None


def _sampling_blocker(
    samples: list[_Sample],
    sampler_failure: _SamplerFailure | None,
    invalid_blocker: str | None,
) -> str | None:
    if sampler_failure == "too_few_samples":
        return "too_few_samples"
    if invalid_blocker is not None:
        return invalid_blocker
    if _max_gap_ms(samples) > _MAX_SAMPLING_GAP_MS:
        return "max_gap_exceeded"
    return None


def _wait_for_done(
    connection: Connection,
    process: psutil.Process,
    samples: list[_Sample],
    sampler_failure: _SamplerFailure | None,
) -> tuple[object, object]:
    deadline = time.monotonic() + _CONTROL_TIMEOUT_S
    while not connection.poll(_SAMPLING_INTERVAL_S):
        if time.monotonic() >= deadline:
            raise RuntimeError("B01 child did not complete")
        if sampler_failure is None:
            samples.append(_sample(process))
    message = connection.recv()
    if type(message) is not tuple or len(message) != 2:
        raise RuntimeError("B01 child protocol is invalid")
    return message


def _sample(process: psutil.Process) -> _Sample:
    return _Sample(time.monotonic_ns(), process.memory_info().rss, process.num_fds())


def _max_gap_ms(samples: list[_Sample]) -> int:
    if len(samples) < 2:
        return 0
    return max(
        _elapsed_ms(samples[index].monotonic_ns, samples[index + 1].monotonic_ns)
        for index in range(len(samples) - 1)
    )


def _resource_evidence(
    samples: list[_Sample], blocker: str | None
) -> _ResourceEvidence:
    if blocker is not None or len(samples) < 2:
        return _ResourceEvidence(
            None,
            None,
            None,
            None,
            len(samples),
            _max_gap_ms(samples) if len(samples) >= 2 else None,
            ResourceEvidenceStatus.INVALID,
            blocker or "too_few_samples",
        )
    return _ResourceEvidence(
        max(sample.rss_bytes for sample in samples),
        samples[0].open_fds,
        max(sample.open_fds for sample in samples),
        samples[-1].open_fds,
        len(samples),
        _max_gap_ms(samples),
        ResourceEvidenceStatus.VALID,
        None,
    )


def _record_b01(
    result: _ChildB01Result,
    resources: _ResourceEvidence,
    iteration_kind: str,
    iteration_index: int,
    root: Path,
) -> B01MeasurementRecord:
    return B01MeasurementRecord(
        workload_id="B01",
        iteration_kind=iteration_kind,
        iteration_index=iteration_index,
        source_revision=_git_identifier("HEAD"),
        source_tree=_git_identifier("HEAD^{tree}"),
        lock_identity=hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest(),
        python_version=runtime_platform.python_version(),
        platform=runtime_platform.system(),
        cpu_model=runtime_platform.machine(),
        cpu_count=os.cpu_count() or 1,
        memory_total_bytes=psutil.virtual_memory().total,
        filesystem_type=_filesystem_type(root),
        duckdb_version=duckdb.__version__,
        pyarrow_version=pyarrow.__version__,
        os_version=f"{runtime_platform.system()}-{runtime_platform.release()}",
        fixture_id=result.fixture_id,
        fixture_version=result.fixture_id,
        schedule_digest=result.schedule_digest,
        policy_version=result.policy_version,
        requested_range="2024-02-01..2024-02-29",
        physical_month_count=1,
        partition_checksums=((2024, 2, result.checksum),),
        elapsed_wall_ms=result.elapsed_wall_ms,
        elapsed_cpu_ms=result.elapsed_cpu_ms,
        phase_elapsed_ms={
            "normalize": None,
            "validate": None,
            "publish": None,
            "catalog": None,
            "query": None,
        },
        rows_raw=result.rows_raw,
        rows_normalized=result.rows_normalized,
        rows_published=result.rows_published,
        bytes_parquet=result.bytes_parquet,
        throughput_rows_per_s=(
            None
            if result.elapsed_wall_ms == 0
            else result.rows_normalized / (result.elapsed_wall_ms / 1_000)
        ),
        request_count=result.request_count,
        provider_attempt_count=result.provider_attempt_count,
        retry_count=result.retry_count,
        resume_count=result.resume_count,
        repair_count=result.repair_count,
        peak_rss_bytes=resources.peak_rss_bytes,
        open_fd_start=resources.open_fd_start,
        open_fd_peak=resources.open_fd_peak,
        open_fd_end=resources.open_fd_end,
        sampler_method=_SAMPLER_METHOD,
        psutil_version=psutil.__version__,
        sampler_sample_count=resources.sample_count,
        sampler_max_gap_ms=resources.max_gap_ms,
        resource_evidence_status=resources.status,
        resource_blocker=resources.blocker,
        query_result_count=None,
        query_min_ts=None,
        query_max_ts=None,
        query_elapsed_ms=None,
        outcome=result.outcome,
        failure_code=result.failure_code,
        partition_outcomes=result.partition_outcomes,
    )


def _git_identifier(revision: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ["git", "rev-parse", revision],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _filesystem_type(root: Path) -> str:
    resolved = root.resolve()
    matches = [
        partition
        for partition in psutil.disk_partitions(all=True)
        if str(resolved).startswith(partition.mountpoint)
    ]
    return (
        max(matches, key=lambda partition: len(partition.mountpoint)).fstype
        if matches
        else "unknown"
    )


def _elapsed_ms(start_ns: int, end_ns: int) -> int:
    return (end_ns - start_ns) // 1_000_000


def _stop_child(child: multiprocessing.Process) -> None:
    child.join(_CONTROL_TIMEOUT_S)
    if child.is_alive():
        child.terminate()
        child.join(_CONTROL_TIMEOUT_S)
    child.close()
