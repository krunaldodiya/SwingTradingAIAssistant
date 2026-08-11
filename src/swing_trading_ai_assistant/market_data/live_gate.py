"""Pure same-response comparison used by the owner-authorized live gate."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, Protocol

from .catalog import DuckDBCatalog
from .credentials import AccessToken, CredentialNotFoundError
from .download_preparation import (
    DownloadPreparationReportV1,
    DownloadPreparationRequestV1,
    PreparationOutcomeV1,
)
from .historical import HistoricalRequest, HistoricalResponse, RetryPolicy
from .instruments import Instrument
from .normalization import normalize_candles
from .parquet import iter_candles_from_parquet
from .range_ingestion import (
    IngestionCommand,
    IngestionCoordinator,
    IngestionReport,
    PartitionOutcome,
    PartitionResult,
    ProviderSessionAuthenticationError,
    RunFailureCode,
)
from .schemas import CanonicalCandle
from .storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
    StorageRootLeaseOperation,
)
from .upstox_canonical import canonicalize_upstox_equity_candles

_HEX_40: Final = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64: Final = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_CODE: Final = re.compile(r"[A-Z][A-Z0-9_]{0,79}\Z")
_SAFE_PATH_COMPONENT: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._=-]{0,127}\Z")
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_MAX_PARQUET_BYTES: Final = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SameResponseComparison:
    """Sanitized result; no row values, indices, aliases, or paths escape."""

    normalized_count: int
    selected_count: int
    mismatch_count: int
    passed: bool


@dataclass(frozen=True, slots=True)
class LiveGateTerminalV1:
    """Sanitized terminal state retained once by the manual adapter."""

    result: str
    code: str
    request_count: int
    provider_attempt_count: int
    raw_count: int
    normalized_count: int
    selected_count: int
    mismatch_count: int
    comparison_passed: bool
    schedule_digest: str | None
    schedule_version: int | None
    schedule_as_of: str | None
    checksum: str | None
    first_ts: str | None
    last_ts: str | None
    source_revision: str
    policy_version: str


class PreparationPort(Protocol):
    def prepare_under_lease(
        self, request: DownloadPreparationRequestV1, lease: StorageRootLease
    ) -> DownloadPreparationReportV1: ...


class TappedSessionFactory(Protocol):
    response: HistoricalResponse | None
    request_count: int


class CoordinatorFactory(Protocol):
    def __call__(self, sessions: TappedSessionFactory) -> IngestionCoordinator: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class HistoricalClientPortV1(Protocol):
    def fetch(
        self, request: HistoricalRequest, token: AccessToken
    ) -> HistoricalResponse: ...


class LazyTappedUpstoxSessionFactoryV1:
    """Load one credential lazily and retain the sole provider response in memory."""

    def __init__(
        self,
        client: HistoricalClientPortV1,
        credential_loader: Callable[[], AccessToken],
    ) -> None:
        self._client = client
        self._credential_loader = credential_loader
        self._opened = False
        self.response: HistoricalResponse | None = None
        self.request_count = 0

    def open(self) -> _TappedUpstoxSessionV1:
        if self._opened:
            raise ProviderSessionAuthenticationError from None
        try:
            token = self._credential_loader()
            if type(token) is not AccessToken:
                raise CredentialNotFoundError
        except Exception:
            raise ProviderSessionAuthenticationError from None
        self._opened = True
        return _TappedUpstoxSessionV1(self, token)

    def fetch_once(
        self, request: HistoricalRequest, token: AccessToken
    ) -> HistoricalResponse:
        if self.request_count != 0:
            raise RuntimeError("live gate request budget exhausted")
        self.request_count = 1
        response = self._client.fetch(request, token)
        if type(response) is not HistoricalResponse:
            raise RuntimeError("live gate provider response invalid")
        self.response = response
        return response


class _TappedUpstoxSessionV1:
    def __init__(
        self, owner: LazyTappedUpstoxSessionFactoryV1, token: AccessToken
    ) -> None:
        self._owner = owner
        self._token = token

    def fetch(self, request: HistoricalRequest) -> HistoricalResponse:
        return self._owner.fetch_once(request, self._token)


class LiveGateServiceV1:
    """One-shot composition of the existing preparation and ingestion boundaries."""

    def __init__(
        self,
        preparation: PreparationPort,
        coordinator_factory: CoordinatorFactory,
        sessions: TappedSessionFactory,
        *,
        clock: Clock,
        source_revision: str,
        max_parquet_rows: int = 100_000,
    ) -> None:
        if (
            _HEX_40.fullmatch(source_revision) is None
            or type(max_parquet_rows) is not int
            or not 1 <= max_parquet_rows <= 100_000
        ):
            raise ValueError("invalid live gate configuration")
        self._preparation = preparation
        self._coordinator_factory = coordinator_factory
        self._sessions = sessions
        self._clock = clock
        self._source_revision = source_revision
        self._max_parquet_rows = max_parquet_rows

    def run(self, request: DownloadPreparationRequestV1) -> LiveGateTerminalV1:
        lease_result = StorageRootLease.try_acquire(request.storage_root)
        if (
            lease_result.outcome is not LeaseOutcome.ACQUIRED
            or lease_result.lease is None
        ):
            return self._terminal("REJECTED", "ROOT_PRECONDITION_FAILED")
        try:
            with (
                lease_result.lease as lease,
                lease.root_operation(request.storage_root) as root_operation,
            ):
                if not _private_empty_root(root_operation):
                    return self._terminal("REJECTED", "ROOT_PRECONDITION_FAILED")
                try:
                    prepared_report = self._preparation.prepare_under_lease(
                        request, lease
                    )
                except Exception:
                    return self._terminal("FAILED", "PREPARATION_UNAVAILABLE")
                if (
                    prepared_report.outcome is not PreparationOutcomeV1.SUCCEEDED
                    or prepared_report.prepared is None
                ):
                    return self._terminal("BLOCKED", prepared_report.failure_code.value)
                prepared = prepared_report.prepared
                root_operation.ensure_live()
                command = IngestionCommand(
                    prepared.instrument,
                    request.from_date,
                    request.to_date,
                    "1m",
                    request.storage_root,
                    prepared.schedule,
                    "nse-equity-month@v1",
                    RetryPolicy(
                        1,
                        timedelta(0),
                        timedelta(0),
                        timedelta(0),
                        timedelta(0),
                    ),
                    1,
                )
                try:
                    report = self._coordinator_factory(self._sessions).run_under_lease(
                        command, lease
                    )
                except Exception:
                    return self._terminal("FAILED", "INGESTION_UNAVAILABLE")
                root_operation.ensure_live()
                terminal = self._terminal_from_report(
                    report, command, prepared.schedule_digest_sha256, lease
                )
                root_operation.ensure_live()
                return terminal
        except Exception:
            return self._terminal("FAILED", "ROOT_AUTHORITY_LOST")

    def _terminal_from_report(
        self,
        report: IngestionReport,
        command: IngestionCommand,
        digest: str,
        lease: StorageRootLease,
    ) -> LiveGateTerminalV1:
        result = report.results[0] if len(report.results) == 1 else None
        request_missing = self._sessions.request_count != 1
        cancelled = report.failure_code is RunFailureCode.CANCELLED
        if (
            result is None
            or result.outcome is not PartitionOutcome.VERIFIED
            or result.final_manifest is None
            or request_missing
            or self._sessions.response is None
        ):
            return LiveGateTerminalV1(
                "CANCELLED"
                if cancelled
                else "BLOCKED"
                if request_missing
                else "FAILED",
                (
                    "CANCELLED"
                    if cancelled
                    else "LIVE_REQUEST_NOT_EXECUTED"
                    if request_missing and report.failure_code is RunFailureCode.NONE
                    else _failure_code(report, result)
                ),
                self._sessions.request_count,
                report.provider_attempt_count,
                0,
                0,
                0,
                0,
                False,
                digest,
                command.expected_sessions.schema_version,
                _timestamp(command.expected_sessions.as_of),
                None,
                None,
                None,
                self._source_revision,
                command.validation_policy_version,
            )
        manifest = result.final_manifest
        if manifest.canonical_path is None or manifest.checksum_sha256 is None:
            return LiveGateTerminalV1(
                "FAILED",
                "SEALED_EVIDENCE_UNAVAILABLE",
                1,
                report.provider_attempt_count,
                0,
                0,
                0,
                0,
                False,
                digest,
                command.expected_sessions.schema_version,
                _timestamp(command.expected_sessions.as_of),
                None,
                None,
                None,
                self._source_revision,
                command.validation_policy_version,
            )
        try:
            with DuckDBCatalog(
                command.storage_root, read_only=True, lease=lease
            ) as catalog:
                if catalog.get_manifest(result.plan) != manifest:
                    raise ValueError("catalog manifest changed")
                sealed = _read_sealed_partition(
                    command.storage_root,
                    lease,
                    manifest.canonical_path,
                    manifest.checksum_sha256,
                    self._max_parquet_rows,
                )
                catalog.ensure_read_identity()
                if catalog.get_manifest(result.plan) != manifest:
                    raise ValueError("catalog manifest changed")
            comparison = compare_same_response(
                self._sessions.response,
                sealed,
                command.instrument,
                self._now(),
                manifest.checksum_sha256,
                digest,
                self._source_revision,
            )
        except Exception:
            return LiveGateTerminalV1(
                "FAILED",
                "COMPARISON_UNAVAILABLE",
                1,
                report.provider_attempt_count,
                0,
                0,
                0,
                0,
                False,
                digest,
                command.expected_sessions.schema_version,
                _timestamp(command.expected_sessions.as_of),
                manifest.checksum_sha256,
                None,
                None,
                self._source_revision,
                command.validation_policy_version,
            )
        return LiveGateTerminalV1(
            "VERIFIED" if comparison.passed else "FAILED",
            "NONE" if comparison.passed else "SAMPLE_MISMATCH",
            1,
            report.provider_attempt_count,
            len(self._sessions.response.candles),
            comparison.normalized_count,
            comparison.selected_count,
            comparison.mismatch_count,
            comparison.passed,
            digest,
            command.expected_sessions.schema_version,
            _timestamp(command.expected_sessions.as_of),
            manifest.checksum_sha256,
            _timestamp(sealed[0].ts) if sealed else None,
            _timestamp(sealed[-1].ts) if sealed else None,
            self._source_revision,
            command.validation_policy_version,
        )

    def _now(self) -> datetime:
        value = self._clock.now()
        if type(value) is not datetime:
            raise ValueError("invalid clock")
        return value

    def _terminal(self, result: str, code: str) -> LiveGateTerminalV1:
        return LiveGateTerminalV1(
            result,
            code,
            0,
            0,
            0,
            0,
            0,
            0,
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            self._source_revision,
            "nse-equity-month@v1",
        )


def _private_empty_root(operation: StorageRootLeaseOperation) -> bool:
    try:
        info = os.fstat(operation.descriptor)
        names = os.listdir(operation.descriptor)
        operation.ensure_live()
        return bool(
            stat.S_ISDIR(info.st_mode)
            and stat.S_IMODE(info.st_mode) == 0o700
            and info.st_uid == os.geteuid()
            and names == [".ingestion.lock"]
        )
    except Exception:
        return False


def _failure_code(report: IngestionReport, result: PartitionResult | None) -> str:
    if (
        result is not None
        and result.error_code is not None
        and _SAFE_CODE.fullmatch(result.error_code) is not None
    ):
        return result.error_code
    return report.failure_code.value


def _read_sealed_partition(
    root: Path,
    lease: StorageRootLease,
    relative_path: str,
    expected_checksum: str,
    max_rows: int,
) -> tuple[CanonicalCandle, ...]:
    if (
        type(relative_path) is not str
        or relative_path.startswith("/")
        or _HEX_64.fullmatch(expected_checksum) is None
    ):
        raise ValueError("invalid sealed partition identity")
    parts = tuple(relative_path.split("/"))
    if not parts or any(_SAFE_PATH_COMPONENT.fullmatch(part) is None for part in parts):
        raise ValueError("invalid sealed partition path")
    parent: int | None = None
    descriptor: int | None = None
    try:
        with lease.root_operation(root) as operation:
            parent, descriptor = _open_partition_descriptor(operation.descriptor, parts)
            before = os.fstat(descriptor)
            _validate_partition_file(before)
            digest, candles = _decode_partition(descriptor, max_rows)
            after = os.fstat(descriptor)
            entry = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            operation.ensure_live()
        if not (
            digest == expected_checksum
            and _file_identity(before) == _file_identity(after) == _file_identity(entry)
        ):
            raise ValueError("sealed partition changed")
        return candles
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent is not None:
            os.close(parent)


def _open_partition_descriptor(
    root_descriptor: int, parts: tuple[str, ...]
) -> tuple[int, int]:
    parent = os.dup(root_descriptor)
    try:
        for component in parts[:-1]:
            child = os.open(component, _DIRECTORY_FLAGS, dir_fd=parent)
            os.close(parent)
            parent = child
        return parent, os.open(parts[-1], _FILE_FLAGS, dir_fd=parent)
    except Exception:
        os.close(parent)
        raise


def _validate_partition_file(value: os.stat_result) -> None:
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) != 0o600
        or not 0 < value.st_size <= _MAX_PARQUET_BYTES
    ):
        raise ValueError("invalid sealed partition file")


def _decode_partition(
    descriptor: int, max_rows: int
) -> tuple[str, tuple[CanonicalCandle, ...]]:
    digest_before = _sha256_descriptor(descriptor)
    with os.fdopen(os.dup(descriptor), "rb") as handle:
        candles: list[CanonicalCandle] = []
        with iter_candles_from_parquet(
            handle,
            max_rows=max_rows,
            max_uncompressed_bytes=128_000_000,
            max_batch_decoded_bytes=16_000_000,
            max_text_field_bytes=1024,
        ) as reader:
            for batch in reader:
                candles.extend(batch)
                if len(candles) > max_rows:
                    raise ValueError("sealed partition row bound exceeded")
    if not candles:
        raise ValueError("sealed partition is empty")
    if digest_before != _sha256_descriptor(descriptor):
        raise ValueError("sealed partition bytes changed")
    return digest_before, tuple(candles)


def _sha256_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while chunk := os.pread(descriptor, 1_048_576, offset):
        digest.update(chunk)
        offset += len(chunk)
    return digest.hexdigest()


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_uid,
        stat.S_IFMT(value.st_mode),
        stat.S_IMODE(value.st_mode),
    )


def compare_same_response(
    response: HistoricalResponse,
    sealed: Sequence[CanonicalCandle],
    instrument: Instrument,
    ingested_at: datetime,
    checksum: str,
    schedule_digest: str,
    source_revision: str,
) -> SameResponseComparison:
    """Compare deterministic positions from the one retained response in memory."""
    if (
        type(response) is not HistoricalResponse
        or type(instrument) is not Instrument
        or _HEX_64.fullmatch(checksum) is None
        or _HEX_64.fullmatch(schedule_digest) is None
        or _HEX_40.fullmatch(source_revision) is None
    ):
        raise ValueError("invalid live gate comparison input")
    normalized = normalize_candles(response.candles)
    canonical = canonicalize_upstox_equity_candles(normalized, instrument, ingested_at)
    if not canonical or len(canonical) != len(sealed):
        return SameResponseComparison(len(canonical), 0, 1, False)
    selected = _sample_indices(
        len(canonical), checksum, schedule_digest, source_revision
    )
    mismatch_count = sum(
        _ohlcv_key(canonical[index]) != _ohlcv_key(sealed[index]) for index in selected
    )
    return SameResponseComparison(
        len(canonical), len(selected), mismatch_count, mismatch_count == 0
    )


def _sample_indices(
    n: int, checksum: str, digest: str, revision: str
) -> tuple[int, ...]:
    selected = [0]
    if n > 1:
        selected.append(n - 1)
    seed = f"same-response-sample-v1|{checksum}|{digest}|{revision}|{n}".encode("ascii")
    for counter in range(64):
        candidate = (
            int.from_bytes(
                hashlib.sha256(seed + b"|" + str(counter).encode("ascii")).digest(),
                "big",
            )
            % n
        )
        if candidate not in selected:
            selected.append(candidate)
        if len(selected) == 10:
            break
    return tuple(selected)


def same_response_sample_indices(
    normalized_count: int, checksum: str, digest: str, source_revision: str
) -> tuple[int, ...]:
    """Return the bounded deterministic indices frozen by Plan 03."""
    if (
        type(normalized_count) is not int
        or normalized_count < 1
        or _HEX_64.fullmatch(checksum) is None
        or _HEX_64.fullmatch(digest) is None
        or _HEX_40.fullmatch(source_revision) is None
    ):
        raise ValueError("invalid sample inputs")
    return _sample_indices(normalized_count, checksum, digest, source_revision)


def _ohlcv_key(candle: CanonicalCandle) -> tuple[object, ...]:
    return (
        candle.ts,
        candle.open,
        candle.high,
        candle.low,
        candle.close,
        candle.volume,
    )


def _timestamp(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )
