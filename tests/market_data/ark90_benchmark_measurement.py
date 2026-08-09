"""Test-only Plan 03 B01 fresh-child measurement harness."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import platform as runtime_platform
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import duckdb
import psutil
import pyarrow
from ark74_benchmark_fixture import BenchmarkFixturePartition, benchmark_nse_eq_v1

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.historical import (
    HistoricalRequest,
    HistoricalResponse,
)
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.partition_ingestion import (
    PartitionIngestionExecutor,
    canonicalize_upstox_equity_candles,
    normalize_candles,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    publish_partition,
)
from swing_trading_ai_assistant.market_data.range_ingestion import (
    IngestionCommand,
    IngestionCoordinator,
    IngestionReport,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleEvidenceResult,
    ScheduleEvidenceStore,
    ScheduleOutcome,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)
from swing_trading_ai_assistant.market_data.validation import (
    EquityMonthValidationPolicy,
)

_CONTROL_TIMEOUT_S = 30.0
_SAMPLING_INTERVAL_S = 0.01
_MAX_SAMPLING_GAP_MS = 50
_PSUTIL_VERSION = "7.2.2"
_SAMPLER_METHOD = "psutil-parent-child-v1"
_PhaseElapsed = dict[str, int | None]
_SamplerFailure = Literal[
    "sampling_exception",
    "unsupported_num_fds",
    "loop_sampling_exception",
    "too_few_samples",
    "gap_exceeded",
]
_ChildTerminal = Literal["failure", "cancelled", "invalid"]


class ResourceEvidenceStatus(StrEnum):
    """Explicit resource-evidence outcome; invalid is never a partial pass."""

    VALID = "VALID"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class SourceDataShape:
    """The observed row and immutable-artifact shape of one workload."""

    rows_raw: int
    rows_normalized: int
    rows_published: int
    bytes_parquet: int


@dataclass(frozen=True, slots=True)
class BenchmarkCommandLimits:
    """Frozen command and direct-query resource limits for Plan 03 B01--B05."""

    interval: str
    max_attempts_per_partition: int
    max_total_provider_attempts: int
    base_backoff_ms: int
    max_backoff_ms: int
    max_retry_after_ms: int
    max_total_wait_ms: int
    query_connection_count: int
    query_threads: int
    query_memory_limit_bytes: int


@dataclass(frozen=True, slots=True)
class BenchmarkResourceLimits:
    """Frozen parent-child measurement limits for Plan 03 B01--B05."""

    child_control_timeout_s: float
    sampling_interval_ms: int
    max_sampling_gap_ms: int
    minimum_sampler_samples: int
    fd_closure_rule: str


_BENCHMARK_COMMAND_LIMITS = BenchmarkCommandLimits(
    "1m", 3, 1, 1_000, 8_000, 60_000, 120_000, 1, 1, 256 * 1024 * 1024
)
_BENCHMARK_RESOURCE_LIMITS = BenchmarkResourceLimits(
    _CONTROL_TIMEOUT_S,
    int(_SAMPLING_INTERVAL_S * 1_000),
    _MAX_SAMPLING_GAP_MS,
    2,
    "open_fd_end_equals_open_fd_start",
)


@dataclass(frozen=True, slots=True)
class ComparabilityIdentity:
    """The complete frozen Plan 03 identity of one measured observation."""

    workload_id: str
    fixture_id: str
    fixture_version: str
    source_revision: str
    source_tree: str
    lock_identity: str
    schedule_digest: str
    requested_range: str
    schedule_as_of: str
    schedule_source: str
    schedule_release: str
    schedule_timezone: str
    schedule_kind_provenance: tuple[str, ...]
    schedule_closure_provenance: tuple[tuple[str, str], ...]
    policy_version: str
    partition_checksums: tuple[tuple[int, int, str], ...]
    source_data_shape: SourceDataShape
    command_limits: BenchmarkCommandLimits
    resource_limits: BenchmarkResourceLimits
    measurement_method: str
    python_major_minor: str
    pyarrow_major_minor: str
    duckdb_major_minor: str
    psutil_version: str
    sampler_method: str
    cpu_architecture: str
    cpu_count: int
    filesystem_type: str


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
    reconciliation_reasons: tuple[str, ...]
    control_partition_evidence: _ControlPartitionEvidence | None
    comparability_key: ComparabilityIdentity


@dataclass(frozen=True, slots=True)
class _ControlPartitionEvidence:
    """Sanitized unchanged out-of-plan control evidence for B03."""

    physical_identity: tuple[str | int, ...]
    pre_physical_checksum: str
    post_physical_checksum: str
    pre_manifest_fingerprint: str
    post_manifest_fingerprint: str
    manifest_bound_schedule_digest: str


@dataclass(frozen=True, slots=True)
class _PreparedB02:
    root: Path
    fixture: object
    sessions: _NeverProviderSessionFactory
    limiter: _NeverLimiter
    march_checksum: str


@dataclass(frozen=True, slots=True)
class _PreparedB01:
    root: Path
    fixture: object
    sessions: _OneResponseSessionFactory


@dataclass(frozen=True, slots=True)
class _PreparedB03:
    root: Path
    fixture: object
    january: BenchmarkFixturePartition
    february_path: Path
    sessions: _OneResponseSessionFactory
    control_before: tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class _PreparedQuery:
    root: Path
    fixture: object
    paths: tuple[Path, ...]
    manifests: tuple[PartitionManifest, ...]
    workload_id: Literal["B04", "B05"]


@dataclass(frozen=True, slots=True)
class _ChildB01Result:
    fixture_id: str
    schedule_digest: str
    policy_version: str
    checksum: str | None
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
    phase_elapsed_ms: _PhaseElapsed
    outcome: str
    failure_code: str
    partition_outcomes: tuple[str, ...]
    workload_id: str = "B01"
    requested_range: str = "2024-02-01..2024-02-29"
    physical_month_count: int = 1
    partition_checksums: tuple[tuple[int, int, str], ...] = ()
    query_result_count: int | None = None
    query_min_ts: str | None = None
    query_max_ts: str | None = None
    query_elapsed_ms: int | None = None
    reconciliation_reasons: tuple[str, ...] = ()
    control_partition_evidence: _ControlPartitionEvidence | None = None
    schedule_as_of: str = ""
    schedule_source: str = ""
    schedule_release: str = ""
    schedule_timezone: str = ""
    schedule_kind_provenance: tuple[str, ...] = ()
    schedule_closure_provenance: tuple[tuple[str, str], ...] = ()


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


class _PhaseTimers:
    """Test-only monotonic timers around the existing B01 phase boundaries."""

    def __init__(self, *, query_applicable: bool = False) -> None:
        self._events: list[tuple[str, str]] = []
        self._elapsed_ms: _PhaseElapsed = {
            "normalize": 0,
            "validate": 0,
            "publish": 0,
            "catalog": 0,
            "query": 0 if query_applicable else None,
        }

    def call(
        self,
        phase: str,
        action: Callable[..., object],
        *args: object,
        operation: str | None = None,
        **kwargs: object,
    ) -> object:
        self._events.append((phase, operation or action.__name__))
        started = time.monotonic_ns()
        try:
            return action(*args, **kwargs)
        finally:
            elapsed = _elapsed_ms(started, time.monotonic_ns())
            current = self._elapsed_ms[phase]
            if current is not None:
                self._elapsed_ms[phase] = current + elapsed

    def snapshot(self) -> _PhaseElapsed:
        return dict(self._elapsed_ms)

    @property
    def events(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._events)


class _TimedCatalog:
    """Measure catalog operations without changing the production catalog."""

    def __init__(self, root: Path, timers: _PhaseTimers) -> None:
        self._timers = timers
        catalog = timers.call("catalog", DuckDBCatalog, root, operation="construct")
        if not isinstance(catalog, DuckDBCatalog):
            raise RuntimeError("benchmark catalog construction failed")
        self._catalog = catalog

    def __enter__(self) -> _TimedCatalog:
        self._timers.call("catalog", self._catalog.__enter__, operation="open")
        return self

    def __exit__(self, *args: object) -> None:
        self._timers.call("catalog", self._catalog.__exit__, *args, operation="close")

    @property
    def connection(self) -> object:
        return self._catalog.connection

    def get_manifest(self, plan: object) -> object:
        return self._timers.call(
            "catalog", self._catalog.get_manifest, plan, operation="get_manifest"
        )

    def create_manifest(self, manifest: object) -> object:
        return self._timers.call(
            "catalog",
            self._catalog.create_manifest,
            manifest,
            operation="create_manifest",
        )

    def transition_manifest(self, current: object, target: object) -> object:
        return self._timers.call(
            "catalog",
            self._catalog.transition_manifest,
            current,
            target,
            operation="transition_manifest",
        )


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
    child_failure: bool = False,
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
        args=(child_connection, str(child_root), child_failure),
    )
    child.start()
    child_connection.close()
    try:
        result, resources = _control_and_sample_child(
            parent_connection,
            child,
            sampler_failure,
            "B01",
        )
    finally:
        parent_connection.close()
        _stop_child(child)

    return _record_b01(result, resources, iteration_kind, iteration_index, child_root)


def measure_benchmark_workload(
    disposable_parent: Path,
    *,
    workload_id: Literal["B02", "B03", "B04", "B05"],
    iteration_kind: Literal["warmup", "measured"],
    iteration_index: int,
    child_terminal: _ChildTerminal | None = None,
) -> B01MeasurementRecord:
    """Measure one non-B01 Plan 03 workload in its own controlled child."""
    if iteration_kind not in {"warmup", "measured"} or iteration_index < 1:
        raise ValueError("invalid iteration")
    child_root = (
        disposable_parent / f"{workload_id.lower()}-{iteration_kind}-{iteration_index}"
    )
    child_root.mkdir()
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe()
    child = context.Process(
        target=_run_benchmark_child,
        args=(child_connection, workload_id, str(child_root), child_terminal),
    )
    child.start()
    child_connection.close()
    try:
        result, resources = _control_and_sample_child(
            parent_connection, child, None, workload_id
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
        "loop_sampling_exception",
        "too_few_samples",
        "gap_exceeded",
    )


def _run_b01_child(
    connection: Connection, root_text: str, child_failure: bool = False
) -> None:
    prepared: _PreparedB01 | None = None
    try:
        prepared = _prepare_b01(Path(root_text))
        connection.send("READY")
        if connection.recv() != "START":
            return
        if child_failure:
            result = _terminal_result(prepared, "B01_CHILD_FAILED", outcome="FAILED")
        else:
            try:
                result = _execute_b01(prepared)
            except Exception:
                result = _terminal_result(
                    prepared, "B01_CHILD_FAILED", outcome="FAILED"
                )
        connection.send(("DONE", result))
        try:
            _accept_exact_exit(connection)
        except Exception:
            connection.send(("ERROR", "B01_CHILD_FAILED"))
    finally:
        connection.close()


def _run_benchmark_child(
    connection: Connection,
    workload_id: str,
    root_text: str,
    child_terminal: _ChildTerminal | None = None,
) -> None:
    prepared: object | None = None
    try:
        prepared = _prepare_benchmark_workload(workload_id, Path(root_text))
        connection.send("READY")
        if connection.recv() != "START":
            return
        if child_terminal == "failure":
            result = _terminal_result(
                prepared, "BENCHMARK_CHILD_FAILED", outcome="FAILED"
            )
        elif child_terminal == "cancelled":
            result = _terminal_result(
                prepared, "BENCHMARK_CHILD_CANCELLED", outcome="CANCELLED"
            )
        if child_terminal == "invalid":
            connection.send(("INVALID", "BENCHMARK_CHILD_PROTOCOL_INVALID"))
            return
        if child_terminal is None:
            try:
                result = _execute_prepared_benchmark_workload(prepared)
            except Exception:
                result = _terminal_result(
                    prepared, "BENCHMARK_CHILD_FAILED", outcome="FAILED"
                )
        connection.send(("DONE", result))
        try:
            _accept_exact_exit(connection)
        except Exception:
            connection.send(("ERROR", "BENCHMARK_CHILD_FAILED"))
    finally:
        connection.close()


def _prepare_b01(root: Path) -> _PreparedB01:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    partition = fixture.partitions[0]
    sessions = _OneResponseSessionFactory(partition.response)
    return _PreparedB01(root, fixture, sessions)


def _execute_b01(prepared: _PreparedB01) -> _ChildB01Result:
    root = prepared.root
    fixture = prepared.fixture
    partition = fixture.partitions[0]
    sessions = prepared.sessions
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
    timers = _PhaseTimers()
    coordinator = _timed_coordinator(sessions, timers)
    wall_started = time.monotonic_ns()
    cpu_started = time.process_time_ns()
    with (
        patch(
            "swing_trading_ai_assistant.market_data.partition_ingestion.normalize_candles",
            _timed_normalizer(timers),
        ),
        patch(
            "swing_trading_ai_assistant.market_data.partition_ingestion.canonicalize_upstox_equity_candles",
            _timed_canonicalizer(timers),
        ),
        patch(
            "swing_trading_ai_assistant.market_data.validation.EquityMonthValidationPolicy.validate",
            _timed_validator(timers),
        ),
    ):
        report = coordinator.run(command)
    elapsed_cpu_ms = _elapsed_ms(cpu_started, time.process_time_ns())
    elapsed_wall_ms = _elapsed_ms(wall_started, time.monotonic_ns())
    return _child_result(
        report,
        fixture,
        fixture.fixture_id,
        fixture.schedule_digest,
        fixture.validation_policy,
        partition,
        root,
        sessions,
        elapsed_wall_ms,
        elapsed_cpu_ms,
        timers.snapshot(),
    )


def _timed_coordinator(
    sessions: _OneResponseSessionFactory, timers: _PhaseTimers
) -> IngestionCoordinator:
    return IngestionCoordinator(
        session_factory=sessions,
        clock=_FixedClock(),
        run_id_factory=lambda: "ark90-run",
        catalog_factory=lambda root: _TimedCatalog(root, timers),
        lifecycle_executor_factory=_timed_executor_factory(timers),
    )


def _timed_normalizer(timers: _PhaseTimers) -> Callable[..., object]:
    return lambda *args: timers.call("normalize", normalize_candles, *args)


def _timed_canonicalizer(timers: _PhaseTimers) -> Callable[..., object]:
    return lambda *args: timers.call(
        "normalize", canonicalize_upstox_equity_candles, *args
    )


def _timed_validator(timers: _PhaseTimers) -> Callable[..., object]:
    validate = EquityMonthValidationPolicy.validate
    return lambda *args, **kwargs: timers.call("validate", validate, *args, **kwargs)


def _timed_executor_factory(
    timers: _PhaseTimers,
) -> Callable[..., PartitionIngestionExecutor]:
    def factory(**kwargs: object) -> PartitionIngestionExecutor:
        return PartitionIngestionExecutor(
            **kwargs,
            publisher=lambda *args: timers.call("publish", publish_partition, *args),
        )

    return factory


def _child_result(
    report: IngestionReport,
    fixture: object,
    fixture_id: str,
    schedule_digest: str,
    policy_version: str,
    partition: BenchmarkFixturePartition,
    root: Path,
    sessions: _OneResponseSessionFactory,
    elapsed_wall_ms: int,
    elapsed_cpu_ms: int,
    phase_elapsed_ms: _PhaseElapsed,
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
        phase_elapsed_ms,
        report.outcome.value,
        report.failure_code.value,
        tuple(item.outcome.value for item in report.results),
        requested_range=_requested_range(fixture),
        partition_checksums=(
            (partition.plan.year, partition.plan.month, manifest.checksum_sha256),
        ),
        **_schedule_result_fields(fixture),
    )


def _control_and_sample_child(
    connection: Connection,
    child: multiprocessing.Process,
    sampler_failure: _SamplerFailure | None,
    workload_id: str,
) -> tuple[_ChildB01Result, _ResourceEvidence]:
    if not connection.poll(_CONTROL_TIMEOUT_S) or connection.recv() != "READY":
        raise RuntimeError("B01 child did not become ready")
    if child.pid is None:
        raise RuntimeError("B01 child process is unavailable")
    process = psutil.Process(child.pid)
    samples, invalid_blocker = _initial_sample(process, sampler_failure)
    connection.send("START")
    _inject_gap_if_requested(process, samples, sampler_failure, invalid_blocker)
    message, loop_blocker = _wait_for_done(
        connection, process, samples, sampler_failure
    )
    result, completed = _child_message_result(message, workload_id)
    invalid_blocker = _end_sample(
        process,
        samples,
        sampler_failure,
        invalid_blocker
        or loop_blocker
        or (None if completed and child.is_alive() else result.failure_code),
    )
    if completed:
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


def _child_message_result(
    message: tuple[object, object],
    workload_id: str,
) -> tuple[_ChildB01Result, bool]:
    if message[0] == "DONE" and type(message[1]) is _ChildB01Result:
        return message[1], True
    return _invalid_protocol_result(workload_id), False


def _invalid_protocol_result(workload_id: str) -> _ChildB01Result:
    fixture = _fixture_for_workload(workload_id)
    return _ChildB01Result(
        fixture.fixture_id,
        fixture.schedule_digest,
        fixture.validation_policy,
        None,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        {
            "normalize": None,
            "validate": None,
            "publish": None,
            "catalog": None,
            "query": None,
        },
        "FAILED",
        "CHILD_PROTOCOL_INVALID",
        (),
        workload_id=workload_id,
        requested_range=_requested_range(fixture),
        physical_month_count=len(fixture.partitions),
        partition_checksums=(),
    )


def _terminal_result(
    prepared: object, failure_code: str, *, outcome: Literal["FAILED", "CANCELLED"]
) -> _ChildB01Result:
    fixture = _prepared_fixture(prepared)
    checksums = _actual_partition_checksums(fixture, _prepared_root(prepared))
    return _ChildB01Result(
        fixture.fixture_id,
        fixture.schedule_digest,
        fixture.validation_policy,
        checksums[-1][2] if checksums else None,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        {
            "normalize": None,
            "validate": None,
            "publish": None,
            "catalog": None,
            "query": None,
        },
        outcome,
        failure_code,
        (),
        workload_id=_prepared_workload_id(prepared),
        requested_range=_requested_range(fixture),
        physical_month_count=len(fixture.partitions),
        partition_checksums=checksums,
        **_schedule_result_fields(fixture),
    )


def _prepared_fixture(prepared: object) -> object:
    if isinstance(prepared, (_PreparedB01, _PreparedB02, _PreparedB03, _PreparedQuery)):
        return prepared.fixture
    raise RuntimeError("benchmark prepared fixture is unavailable")


def _prepared_root(prepared: object) -> Path:
    if isinstance(prepared, (_PreparedB01, _PreparedB02, _PreparedB03, _PreparedQuery)):
        return prepared.root
    raise RuntimeError("benchmark prepared root is unavailable")


def _prepared_workload_id(prepared: object) -> str:
    if isinstance(prepared, _PreparedB01):
        return "B01"
    if isinstance(prepared, _PreparedB02):
        return "B02"
    if isinstance(prepared, _PreparedB03):
        return "B03"
    if isinstance(prepared, _PreparedQuery):
        return prepared.workload_id
    raise RuntimeError("benchmark workload is unavailable")


def _fixture_for_workload(workload_id: str) -> object:
    ranges = {
        "B01": (date(2024, 2, 1), date(2024, 2, 1)),
        "B02": (date(2024, 1, 1), date(2024, 3, 1)),
        "B03": (date(2024, 2, 1), date(2024, 2, 1)),
        "B04": (date(2024, 2, 1), date(2024, 2, 1)),
        "B05": (date(2023, 1, 1), date(2023, 12, 1)),
    }
    from_month, to_month = ranges[workload_id]
    return benchmark_nse_eq_v1(from_month, to_month)


def _requested_range(fixture: object) -> str:
    partitions = fixture.partitions  # type: ignore[attr-defined]
    first, last = partitions[0].plan, partitions[-1].plan
    return f"{first.from_date.isoformat()}..{last.to_date.isoformat()}"


def _actual_partition_checksums(
    fixture: object, root: Path
) -> tuple[tuple[int, int, str], ...]:
    partitions = fixture.partitions  # type: ignore[attr-defined]
    checksums: list[tuple[int, int, str]] = []
    for partition in partitions:
        path = root / _canonical_path(partition)
        if not path.is_file():
            return ()
        checksums.append((partition.plan.year, partition.plan.month, _checksum(path)))
    return tuple(checksums)


def _schedule_result_fields(fixture: object) -> dict[str, object]:
    schedule = fixture.schedule  # type: ignore[attr-defined]
    return {
        "schedule_as_of": schedule.as_of.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "schedule_source": schedule.source,
        "schedule_release": schedule.source_release,
        "schedule_timezone": schedule.timezone,
        "schedule_kind_provenance": tuple(
            session.kind for session in schedule.sessions
        ),
        "schedule_closure_provenance": tuple(
            (closure.trade_date.isoformat(), closure.reason)
            for closure in schedule.closures
        ),
    }


def _accept_exact_exit(connection: Connection) -> None:
    if connection.recv() != "EXIT":
        raise RuntimeError("B01 child protocol is invalid")


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
    if _max_gap_ns(samples) > _MAX_SAMPLING_GAP_MS * 1_000_000:
        return "max_gap_exceeded"
    return None


def _wait_for_done(
    connection: Connection,
    process: psutil.Process,
    samples: list[_Sample],
    sampler_failure: _SamplerFailure | None,
) -> tuple[tuple[object, object], str | None]:
    deadline = time.monotonic() + _CONTROL_TIMEOUT_S
    blocker: str | None = None
    while not connection.poll(_SAMPLING_INTERVAL_S):
        if time.monotonic() >= deadline:
            raise RuntimeError("B01 child did not complete")
        if sampler_failure is None or sampler_failure == "loop_sampling_exception":
            try:
                if sampler_failure == "loop_sampling_exception":
                    raise RuntimeError("sampling exception")
                samples.append(_sample(process))
            except Exception:
                blocker = "sampling_exception"
    message = connection.recv()
    if type(message) is not tuple or len(message) != 2:
        raise RuntimeError("B01 child protocol is invalid")
    return message, blocker


def _sample(process: psutil.Process) -> _Sample:
    return _Sample(time.monotonic_ns(), process.memory_info().rss, process.num_fds())


def _max_gap_ms(samples: list[_Sample]) -> int:
    return _max_gap_ns(samples) // 1_000_000


def _max_gap_ns(samples: list[_Sample]) -> int:
    if len(samples) < 2:
        return 0
    return max(
        samples[index + 1].monotonic_ns - samples[index].monotonic_ns
        for index in range(len(samples) - 1)
    )


def _resource_evidence(
    samples: list[_Sample], blocker: str | None
) -> _ResourceEvidence:
    if (
        blocker is None
        and len(samples) >= 2
        and samples[-1].open_fds != samples[0].open_fds
    ):
        blocker = "open_fd_not_closed"
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
        workload_id=result.workload_id,
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
        requested_range=result.requested_range,
        physical_month_count=result.physical_month_count,
        partition_checksums=result.partition_checksums,
        elapsed_wall_ms=result.elapsed_wall_ms,
        elapsed_cpu_ms=result.elapsed_cpu_ms,
        phase_elapsed_ms=result.phase_elapsed_ms,
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
        query_result_count=result.query_result_count,
        query_min_ts=result.query_min_ts,
        query_max_ts=result.query_max_ts,
        query_elapsed_ms=result.query_elapsed_ms,
        outcome=result.outcome,
        failure_code=result.failure_code,
        partition_outcomes=result.partition_outcomes,
        reconciliation_reasons=result.reconciliation_reasons,
        control_partition_evidence=result.control_partition_evidence,
        comparability_key=_comparability_identity(result, root),
    )


def _comparability_identity(
    result: _ChildB01Result, root: Path
) -> ComparabilityIdentity:
    return ComparabilityIdentity(
        result.workload_id,
        result.fixture_id,
        result.fixture_id,
        _git_identifier("HEAD"),
        _git_identifier("HEAD^{tree}"),
        hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest(),
        result.schedule_digest,
        result.requested_range,
        result.schedule_as_of,
        result.schedule_source,
        result.schedule_release,
        result.schedule_timezone,
        result.schedule_kind_provenance,
        result.schedule_closure_provenance,
        result.policy_version,
        result.partition_checksums,
        SourceDataShape(
            result.rows_raw,
            result.rows_normalized,
            result.rows_published,
            result.bytes_parquet,
        ),
        _BENCHMARK_COMMAND_LIMITS,
        _BENCHMARK_RESOURCE_LIMITS,
        "monotonic-parent-child-v2",
        runtime_platform.python_version().rsplit(".", 1)[0],
        pyarrow.__version__.rsplit(".", 1)[0],
        duckdb.__version__.rsplit(".", 1)[0],
        psutil.__version__,
        _SAMPLER_METHOD,
        runtime_platform.machine(),
        os.cpu_count() or 1,
        _filesystem_type(root),
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


class _StaticClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class _NeverProviderSessionFactory:
    def __init__(self) -> None:
        self.open_calls = 0

    def open(self) -> object:
        self.open_calls += 1
        raise RuntimeError("B02 must not open a provider session")


class _NeverLimiter:
    def __init__(self) -> None:
        self.acquire_calls = 0
        self.defer_calls = 0

    def acquire(self, *_args: object) -> object:
        self.acquire_calls += 1
        raise RuntimeError("B02 must not acquire a limiter permit")

    def defer_for(self, *_args: object) -> object:
        self.defer_calls += 1
        raise RuntimeError("B02 must not defer a limiter")


def _prepare_benchmark_workload(workload_id: str, root: Path) -> object:
    if workload_id == "B02":
        return _prepare_b02(root)
    if workload_id == "B03":
        return _prepare_b03(root)
    if workload_id == "B04":
        return _prepare_query(root, date(2024, 2, 1), date(2024, 2, 1), "B04")
    if workload_id == "B05":
        return _prepare_query(root, date(2023, 1, 1), date(2023, 12, 1), "B05")
    raise ValueError("unsupported benchmark workload")


def _execute_prepared_benchmark_workload(prepared: object) -> _ChildB01Result:
    if isinstance(prepared, _PreparedB02):
        return _execute_b02(prepared)
    if isinstance(prepared, _PreparedB03):
        return _execute_b03(prepared)
    if isinstance(prepared, _PreparedQuery):
        return _execute_query(prepared)
    raise ValueError("unsupported prepared benchmark workload")


def _retain_schedule(
    root: Path, schedule: ExpectedSessionSchedule
) -> ScheduleEvidenceResult:
    acquired = StorageRootLease.try_acquire(root)
    if acquired.outcome is not LeaseOutcome.ACQUIRED or acquired.lease is None:
        raise RuntimeError("benchmark schedule lease was not acquired")
    with acquired.lease:
        retained = ScheduleEvidenceStore(root, acquired.lease).retain(schedule)
    if retained.outcome is not ScheduleOutcome.RETAINED or retained.digest is None:
        raise RuntimeError("benchmark schedule was not retained")
    return retained


def _seed_verified(
    root: Path,
    partition: BenchmarkFixturePartition,
    schedule: ScheduleEvidenceResult,
    run_id: str,
    *,
    checksum: str | None = None,
) -> PartitionManifest:
    if schedule.digest is None:
        raise RuntimeError("benchmark schedule has no digest")
    published = publish_partition(root, partition.plan, partition.canonical_candles)
    started = datetime(2024, 4, 1, tzinfo=UTC)
    active = PartitionManifest(
        1,
        partition.plan,
        run_id,
        None,
        ManifestState.IN_PROGRESS,
        ValidationOutcome.NOT_RUN,
        f"nse-equity-month@v1+sessions-sha256:{schedule.digest}",
        None,
        None,
        None,
        None,
        None,
        "upstox-historical-v3",
        started,
        started,
        started,
        None,
    )
    verified = verify_manifest(
        active,
        started,
        published.actual_from_ts,
        published.actual_to_ts,
        published.row_count,
        checksum or published.checksum_sha256,
        published.canonical_path,
    )
    with DuckDBCatalog(root) as catalog:
        catalog.create_manifest(active)
        catalog.transition_manifest(active, verified)
    return verified


def _first_nibble_mismatch(checksum: str) -> str:
    if len(checksum) != 64:
        raise ValueError("checksum must be sha256")
    return ("1" if checksum[0] == "0" else "0") + checksum[1:]


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_path(partition: BenchmarkFixturePartition) -> Path:
    plan = partition.plan
    return (
        Path("candles")
        / f"provider={plan.provider}"
        / f"exchange={plan.exchange}"
        / f"segment={plan.segment}"
        / f"instrument_type={plan.instrument_type}"
        / f"security_id={plan.security_id}"
        / f"interval={plan.interval}"
        / f"year={plan.year:04d}"
        / f"month={plan.month:02d}"
        / "bars.parquet"
    )


def _prepare_b02(root: Path) -> _PreparedB02:
    fixture = benchmark_nse_eq_v1(date(2024, 1, 1), date(2024, 3, 1))
    january, february, march = fixture.partitions
    schedule = _retain_schedule(root, fixture.schedule)
    _seed_verified(root, january, schedule, "ark92-b02-january")
    _seed_verified(root, february, schedule, "ark92-b02-february")
    march_published = publish_partition(root, march.plan, march.canonical_candles)
    return _PreparedB02(
        root,
        fixture,
        _NeverProviderSessionFactory(),
        _NeverLimiter(),
        march_published.checksum_sha256,
    )


def _execute_b02(prepared: _PreparedB02) -> _ChildB01Result:
    root = prepared.root
    fixture = prepared.fixture
    sessions = prepared.sessions
    limiter = prepared.limiter
    timers = _PhaseTimers()
    started_wall, started_cpu = time.monotonic_ns(), time.process_time_ns()
    report = IngestionCoordinator(
        session_factory=sessions,  # type: ignore[arg-type]
        limiter=limiter,  # type: ignore[arg-type]
        clock=_StaticClock(datetime(2024, 4, 1, tzinfo=UTC)),
        run_id_factory=lambda: "ark92-b02-recovery",
        catalog_factory=lambda catalog_root: _TimedCatalog(catalog_root, timers),
    ).run(
        IngestionCommand(
            fixture.instrument,
            date(2024, 1, 1),
            date(2024, 3, 31),
            "1m",
            root,
            fixture.schedule,
            fixture.validation_policy,
        )
    )
    return _b02_result(
        report,
        fixture,
        root,
        prepared.march_checksum,
        sessions,
        limiter,
        started_wall,
        started_cpu,
        timers.snapshot(),
    )


def _b02_result(
    report: IngestionReport,
    fixture: object,
    root: Path,
    march_checksum: str,
    sessions: _NeverProviderSessionFactory,
    limiter: _NeverLimiter,
    started_wall: int,
    started_cpu: int,
    phase_elapsed_ms: _PhaseElapsed,
) -> _ChildB01Result:
    if (
        report.outcome.value != "SUCCEEDED"
        or report.failure_code.value != "NONE"
        or tuple(item.outcome.value for item in report.results)
        != ("SKIPPED_VERIFIED", "SKIPPED_VERIFIED", "RECOVERED_LOCALLY")
        or report.provider_attempt_count != 0
        or sessions.open_calls != limiter.acquire_calls != limiter.defer_calls != 0
    ):
        raise RuntimeError("B02 benchmark proof failed")
    typed_fixture = fixture
    if not hasattr(typed_fixture, "partitions"):
        raise RuntimeError("benchmark fixture is invalid")
    checksums = tuple(
        (
            partition.plan.year,
            partition.plan.month,
            _checksum(root / _canonical_path(partition)),
        )
        for partition in typed_fixture.partitions  # type: ignore[union-attr]
    )
    return _ChildB01Result(
        typed_fixture.fixture_id,  # type: ignore[union-attr]
        typed_fixture.schedule_digest,  # type: ignore[union-attr]
        typed_fixture.validation_policy,  # type: ignore[union-attr]
        march_checksum,
        22_500,
        22_500,
        22_500,
        sum(
            (root / _canonical_path(partition)).stat().st_size
            for partition in typed_fixture.partitions
        ),  # type: ignore[union-attr]
        0,
        0,
        0,
        3,
        0,
        _elapsed_ms(started_wall, time.monotonic_ns()),
        _elapsed_ms(started_cpu, time.process_time_ns()),
        {**phase_elapsed_ms, "normalize": None, "validate": None, "publish": None},
        report.outcome.value,
        report.failure_code.value,
        tuple(item.outcome.value for item in report.results),
        workload_id="B02",
        requested_range=_requested_range(typed_fixture),
        physical_month_count=3,
        partition_checksums=checksums,
        **_schedule_result_fields(typed_fixture),
    )


def _prepare_b03(root: Path) -> _PreparedB03:
    january_fixture = benchmark_nse_eq_v1(date(2024, 1, 1), date(2024, 1, 1))
    february_fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    january = january_fixture.partitions[0]
    february = february_fixture.partitions[0]
    january_schedule = _retain_schedule(root, january_fixture.schedule)
    february_schedule = _retain_schedule(root, february_fixture.schedule)
    january_manifest = _seed_verified(
        root, january, january_schedule, "ark92-b03-january-control"
    )
    february_path = root / _canonical_path(february)
    published = publish_partition(root, february.plan, february.canonical_candles)
    _seed_verified(
        root,
        february,
        february_schedule,
        "ark92-b03-february-mismatch",
        checksum=_first_nibble_mismatch(published.checksum_sha256),
    )
    control_before = _control_evidence(january, january_manifest, root)
    return _PreparedB03(
        root,
        february_fixture,
        january,
        february_path,
        _OneResponseSessionFactory(february.response),
        control_before,
    )


def _execute_b03(prepared: _PreparedB03) -> _ChildB01Result:
    root = prepared.root
    february_fixture = prepared.fixture
    january = prepared.january
    february_path = prepared.february_path
    sessions = prepared.sessions
    timers = _PhaseTimers()
    coordinator = IngestionCoordinator(
        session_factory=sessions,
        clock=_StaticClock(datetime(2024, 4, 2, tzinfo=UTC)),
        run_id_factory=lambda: "ark92-b03-repair",
        catalog_factory=lambda catalog_root: _TimedCatalog(catalog_root, timers),
        lifecycle_executor_factory=_timed_executor_factory(timers),
    )
    started_wall, started_cpu = time.monotonic_ns(), time.process_time_ns()
    with (
        patch(
            "swing_trading_ai_assistant.market_data.partition_ingestion.normalize_candles",
            _timed_normalizer(timers),
        ),
        patch(
            "swing_trading_ai_assistant.market_data.partition_ingestion.canonicalize_upstox_equity_candles",
            _timed_canonicalizer(timers),
        ),
        patch(
            "swing_trading_ai_assistant.market_data.validation.EquityMonthValidationPolicy.validate",
            _timed_validator(timers),
        ),
    ):
        report = coordinator.run(
            IngestionCommand(
                february_fixture.instrument,
                date(2024, 2, 1),
                date(2024, 2, 29),
                "1m",
                root,
                february_fixture.schedule,
                february_fixture.validation_policy,
                max_total_provider_attempts=1,
            )
        )
    elapsed_wall_ms = _elapsed_ms(started_wall, time.monotonic_ns())
    elapsed_cpu_ms = _elapsed_ms(started_cpu, time.process_time_ns())
    control_after = _control_evidence(
        january, _catalog_manifest(root, january, timers), root
    )
    return _b03_result(
        report,
        february_fixture,
        february_path,
        sessions,
        elapsed_wall_ms,
        elapsed_cpu_ms,
        timers.snapshot(),
        prepared.control_before,
        control_after,
    )


def _catalog_manifest(
    root: Path, partition: BenchmarkFixturePartition, timers: _PhaseTimers
) -> PartitionManifest:
    with _TimedCatalog(root, timers) as catalog:
        manifest = catalog.get_manifest(partition.plan)
    if not isinstance(manifest, PartitionManifest):
        raise RuntimeError("benchmark control manifest is unavailable")
    return manifest


def _control_evidence(
    partition: BenchmarkFixturePartition, manifest: PartitionManifest, root: Path
) -> tuple[str, str, str]:
    schedule_digest = manifest.validation_policy_version.rsplit(
        "+sessions-sha256:", maxsplit=1
    )[-1]
    return (
        _checksum(root / _canonical_path(partition)),
        _manifest_fingerprint(manifest),
        schedule_digest,
    )


def _b03_result(
    report: IngestionReport,
    fixture: object,
    february_path: Path,
    sessions: _OneResponseSessionFactory,
    elapsed_wall_ms: int,
    elapsed_cpu_ms: int,
    phase_elapsed_ms: _PhaseElapsed,
    control_before: tuple[str, str, str],
    control_after: tuple[str, str, str],
) -> _ChildB01Result:
    if (
        report.outcome.value != "SUCCEEDED"
        or report.failure_code.value != "NONE"
        or len(report.results) != 1
        or report.provider_attempt_count != 1
        or sessions.open_calls != len(sessions.session.requests) != 1
    ):
        raise RuntimeError("B03 benchmark proof failed")
    result = report.results[0]
    reasons = tuple(reason.value for reason in result.reconciliation_reasons)
    manifest = result.final_manifest
    if (
        result.outcome.value != "VERIFIED"
        or result.provider_attempts != 1
        or reasons != ("CHECKSUM_INVALID_OR_MISMATCHED",)
        or not isinstance(manifest, PartitionManifest)
        or manifest.row_count != 7_500
        or manifest.checksum_sha256 != _checksum(february_path)
        or control_before != control_after
    ):
        raise RuntimeError("B03 target-only repair proof failed")
    typed_fixture = fixture
    if not hasattr(typed_fixture, "fixture_id") or not hasattr(
        typed_fixture, "schedule_digest"
    ):
        raise RuntimeError("benchmark fixture is invalid")
    control = _ControlPartitionEvidence(
        (
            "upstox",
            "NSE",
            "NSE_EQ",
            "EQ",
            "INE000A01000",
            "1m",
            2024,
            1,
        ),
        control_before[0],
        control_after[0],
        control_before[1],
        control_after[1],
        control_before[2],
    )
    return _ChildB01Result(
        typed_fixture.fixture_id,  # type: ignore[union-attr]
        typed_fixture.schedule_digest,  # type: ignore[union-attr]
        typed_fixture.validation_policy,  # type: ignore[union-attr]
        manifest.checksum_sha256,
        7_500,
        7_500,
        7_500,
        february_path.stat().st_size,
        1,
        report.provider_attempt_count,
        0,
        0,
        1,
        elapsed_wall_ms,
        elapsed_cpu_ms,
        phase_elapsed_ms,
        report.outcome.value,
        report.failure_code.value,
        (result.outcome.value,),
        workload_id="B03",
        requested_range=_requested_range(typed_fixture),
        physical_month_count=1,
        partition_checksums=((2024, 2, manifest.checksum_sha256),),
        reconciliation_reasons=reasons,
        control_partition_evidence=control,
        **_schedule_result_fields(typed_fixture),
    )


def _manifest_fingerprint(manifest: PartitionManifest) -> str:
    def instant(value: datetime | None) -> str | None:
        return (
            None
            if value is None
            else value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )

    plan = manifest.plan
    projection = {
        "manifest_schema_version": manifest.manifest_schema_version,
        "plan": {
            "provider": plan.provider,
            "instrument_key": plan.instrument_key,
            "security_id": plan.security_id,
            "symbol": plan.symbol,
            "exchange": plan.exchange,
            "segment": plan.segment,
            "instrument_type": plan.instrument_type,
            "interval": plan.interval,
            "year": plan.year,
            "month": plan.month,
            "from_date": plan.from_date.isoformat(),
            "to_date": plan.to_date.isoformat(),
        },
        "ingestion_run_id": manifest.ingestion_run_id,
        "candle_schema_version": manifest.candle_schema_version,
        "state": manifest.state.value,
        "validation_outcome": manifest.validation_outcome.value,
        "validation_policy_version": manifest.validation_policy_version,
        "actual_from_ts": instant(manifest.actual_from_ts),
        "actual_to_ts": instant(manifest.actual_to_ts),
        "row_count": manifest.row_count,
        "checksum_sha256": manifest.checksum_sha256,
        "canonical_path": manifest.canonical_path,
        "source_version": manifest.source_version,
        "created_at": instant(manifest.created_at),
        "attempt_started_at": instant(manifest.attempt_started_at),
        "updated_at": instant(manifest.updated_at),
        "failure_category": None
        if manifest.failure_category is None
        else manifest.failure_category.value,
    }
    return hashlib.sha256(
        json.dumps(
            projection, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _prepare_query(
    root: Path, from_month: date, to_month: date, workload_id: Literal["B04", "B05"]
) -> _PreparedQuery:
    fixture = benchmark_nse_eq_v1(from_month, to_month)
    schedule = _retain_schedule(root, fixture.schedule)
    manifests = tuple(
        _seed_verified(
            root, partition, schedule, f"ark92-{workload_id.lower()}-{index}"
        )
        for index, partition in enumerate(fixture.partitions, start=1)
    )
    paths = tuple(root / _canonical_path(partition) for partition in fixture.partitions)
    return _PreparedQuery(root, fixture, paths, manifests, workload_id)


def _execute_query(prepared: _PreparedQuery) -> _ChildB01Result:
    root = prepared.root
    fixture = prepared.fixture
    paths = prepared.paths
    manifests = prepared.manifests
    workload_id = prepared.workload_id
    started_wall, started_cpu = time.monotonic_ns(), time.process_time_ns()
    timers = _PhaseTimers(query_applicable=True)
    with _TimedCatalog(root, timers) as catalog:
        timers.call(
            "catalog", _configure_benchmark_query, catalog, root, operation="configure"
        )
        aggregate = timers.call(
            "query",
            _fetch_benchmark_aggregate,
            catalog,
            paths,
            fixture,
            manifests,
            operation="execute_and_fetch",
        )
        timers.call(
            "catalog",
            _assert_metadata_relations_only,
            catalog,
            operation="assert_metadata_relations",
        )
    phase_elapsed_ms = timers.snapshot()
    return _query_result(
        aggregate,
        fixture,
        paths,
        manifests,
        workload_id,
        _elapsed_ms(started_wall, time.monotonic_ns()),
        _elapsed_ms(started_cpu, time.process_time_ns()),
        phase_elapsed_ms,
    )


def _configure_benchmark_query(catalog: DuckDBCatalog, root: Path) -> None:
    temp_directory = root / "duckdb-tmp"
    temp_directory.mkdir()
    connection = catalog.connection
    connection.execute("SET TimeZone = 'UTC'")
    connection.execute("SET threads = 1")
    connection.execute("SET memory_limit = '256MB'")
    connection.execute(
        "SET temp_directory = '" + str(temp_directory).replace("'", "''") + "'"
    )
    if (
        connection.execute("SELECT current_setting('threads')").fetchone() != (1,)
        or connection.execute("SELECT current_setting('TimeZone')").fetchone()
        != ("UTC",)
        or connection.execute("SELECT current_setting('temp_directory')").fetchone()
        != (str(temp_directory),)
    ):
        raise RuntimeError("benchmark DuckDB configuration was not applied")


def _fetch_benchmark_aggregate(
    catalog: DuckDBCatalog,
    paths: tuple[Path, ...],
    fixture: object,
    manifests: tuple[PartitionManifest, ...],
) -> object:
    return catalog.connection.execute(
        "SELECT count(*), CAST(min(ts) AS VARCHAR), CAST(max(ts) AS VARCHAR) "
        "FROM read_parquet(?) "
        "WHERE provider = ? AND exchange = ? AND segment = ? "
        "AND instrument_type = ? AND security_id = ? AND interval = ? "
        "AND ts >= ? AND ts <= ?",
        [
            [str(path) for path in paths],
            fixture.partitions[0].plan.provider,  # type: ignore[attr-defined]
            fixture.instrument.exchange,  # type: ignore[attr-defined]
            fixture.instrument.segment,  # type: ignore[attr-defined]
            fixture.instrument.instrument_type,  # type: ignore[attr-defined]
            fixture.instrument.security_id,  # type: ignore[attr-defined]
            "1m",
            manifests[0].actual_from_ts.isoformat(),
            manifests[-1].actual_to_ts.isoformat(),
        ],
    ).fetchone()


def _assert_metadata_relations_only(catalog: DuckDBCatalog) -> None:
    relations = catalog.connection.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()
    if relations != [("ingestion_runs",), ("partitions",), ("schema_migrations",)]:
        raise RuntimeError("benchmark catalog contains non-metadata relations")


def _query_result(
    aggregate: object,
    fixture: object,
    paths: tuple[Path, ...],
    manifests: tuple[PartitionManifest, ...],
    workload_id: Literal["B04", "B05"],
    elapsed_wall_ms: int,
    elapsed_cpu_ms: int,
    phase_elapsed_ms: _PhaseElapsed,
) -> _ChildB01Result:
    if (
        type(aggregate) is not tuple
        or len(aggregate) != 3
        or type(aggregate[0]) is not int
        or type(aggregate[1]) is not str
        or type(aggregate[2]) is not str
        or not hasattr(fixture, "fixture_id")
        or not hasattr(fixture, "schedule_digest")
        or not hasattr(fixture, "validation_policy")
    ):
        raise RuntimeError("benchmark query returned invalid evidence")
    expected_rows = sum(manifest.row_count or 0 for manifest in manifests)
    expected_from = manifests[0].actual_from_ts
    expected_to = manifests[-1].actual_to_ts
    if expected_from is None or expected_to is None:
        raise RuntimeError("benchmark sealed bounds are unavailable")
    if aggregate != (
        expected_rows,
        expected_from.strftime("%Y-%m-%d %H:%M:%S+00"),
        expected_to.strftime("%Y-%m-%d %H:%M:%S+00"),
    ):
        raise RuntimeError("benchmark query does not agree with sealed evidence")
    checksums = tuple(
        (manifest.plan.year, manifest.plan.month, manifest.checksum_sha256)
        for manifest in manifests
    )
    if any(checksum is None for _, _, checksum in checksums):
        raise RuntimeError("benchmark partition checksum is unavailable")
    checksum_records = tuple(
        (year, month, checksum)
        for year, month, checksum in checksums
        if checksum is not None
    )
    return _ChildB01Result(
        fixture.fixture_id,  # type: ignore[union-attr]
        fixture.schedule_digest,  # type: ignore[union-attr]
        fixture.validation_policy,  # type: ignore[union-attr]
        checksum_records[-1][2],
        expected_rows,
        expected_rows,
        expected_rows,
        sum(path.stat().st_size for path in paths),
        0,
        0,
        0,
        0,
        0,
        elapsed_wall_ms,
        elapsed_cpu_ms,
        phase_elapsed_ms,
        "SUCCEEDED",
        "NONE",
        (),
        workload_id=workload_id,
        requested_range=(
            f"{manifests[0].plan.from_date.isoformat()}.."
            f"{manifests[-1].plan.to_date.isoformat()}"
        ),
        physical_month_count=len(manifests),
        partition_checksums=checksum_records,
        query_result_count=aggregate[0],
        query_min_ts=expected_from.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        query_max_ts=expected_to.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        query_elapsed_ms=phase_elapsed_ms["query"],
        **_schedule_result_fields(fixture),
    )


def _elapsed_ms(start_ns: int, end_ns: int) -> int:
    return (end_ns - start_ns) // 1_000_000


def _stop_child(child: multiprocessing.Process) -> None:
    child.join(_CONTROL_TIMEOUT_S)
    if child.is_alive():
        child.terminate()
        child.join(_CONTROL_TIMEOUT_S)
    child.close()
