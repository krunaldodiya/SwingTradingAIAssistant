"""Bounded one-or-many point-in-time Nifty 50 download orchestration."""

from __future__ import annotations

import json
import os
import re
import stat
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from .catalog import DuckDBCatalog
from .equity_admission import (
    Nifty50AdmissionPolicyV1,
    Nifty50AdmissionValidationError,
)
from .public_contract import (
    MAX_DOWNLOAD_PROVIDER_ATTEMPTS_V1,
    DownloadReportV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicFailureCodeV1,
    PublicFailureV1,
    validate_download_report_v1,
)
from .public_download import SingleSymbolDownloadRequestV1
from .storage_root_lease import LeaseOutcome, StorageRootLease
from .universe_snapshot import (
    MAX_UNIVERSE_JSON_BYTES_V1,
    Nifty50UniverseSnapshotV1,
    Nifty50UniverseStoreV1,
    UniverseSnapshotAmbiguousError,
    UniverseSnapshotCorruptError,
    UniverseSnapshotNotFoundError,
    UniverseSnapshotStaleError,
)

_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.&_-]{0,31}\Z")
_ISIN = re.compile(r"INE[A-Z0-9]{8}[0-9]\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MAX_SYMBOLS = 50
_MAX_WORKERS = 8


class Nifty50BatchOutcomeV1(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class BoundedNifty50DownloadRequestV1:
    """Select explicit members, or all 50 when symbols is None."""

    symbols: tuple[str, ...] | None
    universe_as_of: date
    knowledge_cutoff: datetime
    from_date: date
    to_date: date
    storage_root: Path
    workers: int = 4

    def __post_init__(self) -> None:
        symbols = self.symbols
        if (
            (
                symbols is not None
                and (
                    type(symbols) is not tuple
                    or not symbols
                    or len(symbols) > _MAX_SYMBOLS
                    or any(
                        type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
                        for symbol in symbols
                    )
                    or len(set(symbols)) != len(symbols)
                )
            )
            or type(self.universe_as_of) is not date
            or type(self.knowledge_cutoff) is not datetime
            or self.knowledge_cutoff.tzinfo is None
            or self.knowledge_cutoff.utcoffset() is None
            or type(self.from_date) is not date
            or type(self.to_date) is not date
            or self.from_date > self.to_date
            or self.from_date < date(2022, 1, 1)
            or type(self.storage_root) is not type(Path())
            or not self.storage_root.is_absolute()
            or ".." in self.storage_root.parts
            or any(
                marker in part for part in self.storage_root.parts for marker in "~*?[]"
            )
            or type(self.workers) is not int
            or not 1 <= self.workers <= _MAX_WORKERS
        ):
            raise ValueError("invalid bounded Nifty 50 download request")
        object.__setattr__(
            self, "knowledge_cutoff", self.knowledge_cutoff.astimezone(UTC)
        )


@dataclass(frozen=True, slots=True)
class Nifty50SymbolDownloadResultV1:
    symbol: str
    isin: str
    status: PublicCommandStatusV1
    failure_code: PublicFailureCodeV1 | None
    provider_attempt_count: int

    def __post_init__(self) -> None:
        if (
            type(self.symbol) is not str
            or _SYMBOL.fullmatch(self.symbol) is None
            or type(self.isin) is not str
            or _ISIN.fullmatch(self.isin) is None
            or type(self.status) is not PublicCommandStatusV1
            or type(self.failure_code) not in (PublicFailureCodeV1, type(None))
            or (self.status is PublicCommandStatusV1.SUCCEEDED)
            != (self.failure_code is None)
            or type(self.provider_attempt_count) is not int
            or not 0 <= self.provider_attempt_count <= MAX_DOWNLOAD_PROVIDER_ATTEMPTS_V1
        ):
            raise ValueError("invalid Nifty 50 symbol result")


@dataclass(frozen=True, slots=True)
class BoundedNifty50DownloadReportV1:
    outcome: Nifty50BatchOutcomeV1
    universe_snapshot_sha256: str | None
    results: tuple[Nifty50SymbolDownloadResultV1, ...]
    provider_attempt_count: int
    worker_count: int

    def __post_init__(self) -> None:
        digest = self.universe_snapshot_sha256
        if (
            type(self.outcome) is not Nifty50BatchOutcomeV1
            or (
                digest is not None
                and (type(digest) is not str or _DIGEST.fullmatch(digest) is None)
            )
            or type(self.results) is not tuple
            or len(self.results) > _MAX_SYMBOLS
            or any(
                type(item) is not Nifty50SymbolDownloadResultV1 for item in self.results
            )
            or len({item.symbol for item in self.results}) != len(self.results)
            or type(self.provider_attempt_count) is not int
            or self.provider_attempt_count
            != sum(item.provider_attempt_count for item in self.results)
            or self.provider_attempt_count
            > _MAX_SYMBOLS * MAX_DOWNLOAD_PROVIDER_ATTEMPTS_V1
            or type(self.worker_count) is not int
            or not 0 <= self.worker_count <= _MAX_WORKERS
            or self.worker_count > len(self.results)
            or (bool(self.results) != bool(self.worker_count))
            or (bool(self.results) != (digest is not None))
            or (bool(self.results) and self.outcome is not _aggregate(self.results))
            or (
                not self.results
                and self.outcome
                not in {
                    Nifty50BatchOutcomeV1.REJECTED,
                    Nifty50BatchOutcomeV1.UNAVAILABLE,
                    Nifty50BatchOutcomeV1.FAILED,
                    Nifty50BatchOutcomeV1.CANCELLED,
                }
            )
        ):
            raise ValueError("invalid bounded Nifty 50 download report")


class UniverseSnapshotSourceV1(Protocol):
    def load(self) -> Nifty50UniverseSnapshotV1: ...


@dataclass(frozen=True, slots=True)
class CanonicalFileNifty50UniverseSourceV1:
    """Read one bounded immutable caller-supplied canonical universe file."""

    path: Path

    def __post_init__(self) -> None:
        if (
            type(self.path) is not type(Path())
            or not self.path.is_absolute()
            or ".." in self.path.parts
            or any(marker in part for part in self.path.parts for marker in "~*?[]")
        ):
            raise ValueError("invalid universe source path")

    def load(self) -> Nifty50UniverseSnapshotV1:
        descriptor = -1
        active_error: BaseException | None = None
        try:
            descriptor = os.open(
                self.path,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            )
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or not 0 < before.st_size <= MAX_UNIVERSE_JSON_BYTES_V1
                or before.st_mode & 0o022
            ):
                raise UniverseSnapshotCorruptError("universe snapshot corrupt")
            chunks: list[bytes] = []
            remaining = before.st_size
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
            entry = os.stat(self.path, follow_symlinks=False)
            if (
                len(payload) != before.st_size
                or _file_identity(before) != _file_identity(after)
                or _file_identity(after) != _file_identity(entry)
            ):
                raise UniverseSnapshotCorruptError("universe snapshot corrupt")
            return Nifty50UniverseSnapshotV1.from_canonical_json_bytes(payload)
        except OSError:
            active_error = UniverseSnapshotCorruptError("universe snapshot corrupt")
            raise active_error from None
        except BaseException as error:
            active_error = error
            raise
        finally:
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except BaseException:
                    if active_error is None:
                        raise


class Nifty50SymbolDownloadPortV1(Protocol):
    def download_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> DownloadReportV1: ...


class Nifty50SymbolDownloadFactoryV1(Protocol):
    def __call__(
        self, policy: Nifty50AdmissionPolicyV1
    ) -> Nifty50SymbolDownloadPortV1: ...


class Nifty50WorkflowClockV1(Protocol):
    def now(self) -> datetime: ...


class BoundedNifty50DownloadServiceV1:
    """Resolve one PIT universe once and execute members under one root lease."""

    def __init__(
        self,
        universe_source: UniverseSnapshotSourceV1 | None,
        symbol_service_factory: Nifty50SymbolDownloadFactoryV1,
        *,
        clock: Nifty50WorkflowClockV1,
    ) -> None:
        self._universe_source = universe_source
        self._symbol_service_factory = symbol_service_factory
        self._clock = clock

    def download(self, request: object) -> BoundedNifty50DownloadReportV1:
        if type(request) is not BoundedNifty50DownloadRequestV1:
            return _empty(Nifty50BatchOutcomeV1.REJECTED)
        invocation = _now(self._clock)
        if invocation is None or request.knowledge_cutoff > invocation:
            return _empty(Nifty50BatchOutcomeV1.REJECTED)
        acquired = StorageRootLease.try_acquire(request.storage_root)
        if acquired.outcome is not LeaseOutcome.ACQUIRED or acquired.lease is None:
            return _empty(Nifty50BatchOutcomeV1.UNAVAILABLE)
        try:
            with acquired.lease as lease:
                policy = self._resolve_policy(request, lease)
                service = self._symbol_service_factory(policy)
                worker_count = min(request.workers, len(policy.ordered_symbols))

                def download_symbol(symbol: str) -> Nifty50SymbolDownloadResultV1:
                    return self._download_symbol(
                        request, policy, service, symbol, lease
                    )

                with ThreadPoolExecutor(
                    max_workers=worker_count,
                    thread_name_prefix="nifty50-download",
                ) as executor:
                    results = tuple(
                        executor.map(download_symbol, policy.ordered_symbols)
                    )
                return BoundedNifty50DownloadReportV1(
                    _aggregate(results),
                    policy.universe_snapshot_sha256,
                    results,
                    sum(item.provider_attempt_count for item in results),
                    worker_count,
                )
        except Nifty50AdmissionValidationError:
            return _empty(Nifty50BatchOutcomeV1.REJECTED)
        except (UniverseSnapshotNotFoundError, UniverseSnapshotStaleError):
            return _empty(Nifty50BatchOutcomeV1.UNAVAILABLE)
        except (UniverseSnapshotAmbiguousError, UniverseSnapshotCorruptError):
            return _empty(Nifty50BatchOutcomeV1.FAILED)
        except Exception:
            return _empty(Nifty50BatchOutcomeV1.FAILED)

    def download_single(self, request: object) -> DownloadReportV1:
        """Run one PIT-admitted member while retaining its public report shape."""
        if (
            type(request) is not BoundedNifty50DownloadRequestV1
            or request.symbols is None
            or len(request.symbols) != 1
        ):
            return _single_terminal(PublicCommandStatusV1.REJECTED)
        invocation = _now(self._clock)
        if invocation is None or request.knowledge_cutoff > invocation:
            return _single_terminal(PublicCommandStatusV1.REJECTED)
        acquired = StorageRootLease.try_acquire(request.storage_root)
        if acquired.outcome is not LeaseOutcome.ACQUIRED or acquired.lease is None:
            return _single_terminal(PublicCommandStatusV1.UNAVAILABLE)
        try:
            with acquired.lease as lease:
                policy = self._resolve_policy(request, lease)
                symbol = request.symbols[0]
                report = self._symbol_service_factory(policy).download_under_lease(
                    SingleSymbolDownloadRequestV1(
                        "NSE_EQ",
                        symbol,
                        request.from_date,
                        request.to_date,
                        request.storage_root,
                    ),
                    lease,
                )
                try:
                    return validate_download_report_v1(report)
                except Exception:
                    return _single_terminal(PublicCommandStatusV1.FAILED)
        except Nifty50AdmissionValidationError:
            return _single_terminal(PublicCommandStatusV1.REJECTED)
        except (UniverseSnapshotNotFoundError, UniverseSnapshotStaleError):
            return _single_terminal(PublicCommandStatusV1.UNAVAILABLE)
        except Exception:
            return _single_terminal(PublicCommandStatusV1.FAILED)

    def _resolve_policy(
        self,
        request: BoundedNifty50DownloadRequestV1,
        lease: StorageRootLease,
    ) -> Nifty50AdmissionPolicyV1:
        with DuckDBCatalog(request.storage_root, lease=lease) as catalog:
            store = Nifty50UniverseStoreV1(request.storage_root, lease, catalog)
            if self._universe_source is not None:
                snapshot = self._universe_source.load()
                if type(snapshot) is not Nifty50UniverseSnapshotV1:
                    raise UniverseSnapshotCorruptError("universe snapshot corrupt")
                store.retain(snapshot)
            resolved = store.resolve(
                as_of=request.universe_as_of,
                knowledge_cutoff=request.knowledge_cutoff,
            )
            if (
                resolved.snapshot.effective_from > request.from_date
                or resolved.snapshot.effective_to < request.to_date
            ):
                raise UniverseSnapshotStaleError(
                    "universe snapshot does not cover request"
                )
        return Nifty50AdmissionPolicyV1(
            resolved.metadata.snapshot_sha256,
            resolved.snapshot,
            request.symbols,
        )

    def _download_symbol(
        self,
        request: BoundedNifty50DownloadRequestV1,
        policy: Nifty50AdmissionPolicyV1,
        service: Nifty50SymbolDownloadPortV1,
        symbol: str,
        lease: StorageRootLease,
    ) -> Nifty50SymbolDownloadResultV1:
        member = next(
            value for value in policy.universe.constituents if value.symbol == symbol
        )
        try:
            report = service.download_under_lease(
                SingleSymbolDownloadRequestV1(
                    "NSE_EQ",
                    symbol,
                    request.from_date,
                    request.to_date,
                    request.storage_root,
                ),
                lease,
            )
            if type(report) is not PublicCommandReportV1:
                raise ValueError
            validated = replace(report)
            failure_code = None if validated.failure is None else validated.failure.code
            return Nifty50SymbolDownloadResultV1(
                symbol,
                member.isin,
                validated.status,
                failure_code,
                validated.provider_attempt_count,
            )
        except Exception:
            return Nifty50SymbolDownloadResultV1(
                symbol,
                member.isin,
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
                0,
            )


def _now(clock: Nifty50WorkflowClockV1) -> datetime | None:
    try:
        value = clock.now()
        if (
            type(value) is not datetime
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError
        return value.astimezone(UTC)
    except Exception:
        return None


def _aggregate(
    results: tuple[Nifty50SymbolDownloadResultV1, ...],
) -> Nifty50BatchOutcomeV1:
    statuses = {item.status for item in results}
    if statuses == {PublicCommandStatusV1.SUCCEEDED}:
        return Nifty50BatchOutcomeV1.SUCCEEDED
    if PublicCommandStatusV1.SUCCEEDED in statuses:
        return Nifty50BatchOutcomeV1.PARTIAL
    if statuses == {PublicCommandStatusV1.REJECTED}:
        return Nifty50BatchOutcomeV1.REJECTED
    if statuses and statuses <= {
        PublicCommandStatusV1.UNAVAILABLE,
        PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
    }:
        return Nifty50BatchOutcomeV1.UNAVAILABLE
    if statuses and statuses <= {PublicCommandStatusV1.CANCELLED}:
        return Nifty50BatchOutcomeV1.CANCELLED
    return Nifty50BatchOutcomeV1.FAILED


def _empty(outcome: Nifty50BatchOutcomeV1) -> BoundedNifty50DownloadReportV1:
    return BoundedNifty50DownloadReportV1(outcome, None, (), 0, 0)


def _single_terminal(status: PublicCommandStatusV1) -> DownloadReportV1:
    code = (
        PublicFailureCodeV1.INVALID_INPUT
        if status is PublicCommandStatusV1.REJECTED
        else PublicFailureCodeV1.UNCLASSIFIED_FAILURE
    )
    return PublicCommandReportV1(
        "v1",
        "download",
        status,
        PublicFailureV1(code, None, None, None, None, ()),
        0,
        None,
    )


def render_bounded_nifty50_download_json(
    report: BoundedNifty50DownloadReportV1,
) -> bytes:
    """Render a bounded allowlisted aggregate without paths or provider details."""
    if type(report) is not BoundedNifty50DownloadReportV1:
        report = _empty(Nifty50BatchOutcomeV1.FAILED)
    try:
        validated = replace(
            report, results=tuple(replace(item) for item in report.results)
        )
    except Exception:
        validated = _empty(Nifty50BatchOutcomeV1.FAILED)
    value = {
        "contract_version": "v1",
        "command": "download",
        "scope": "nifty50",
        "status": validated.outcome.value,
        "universe_snapshot_sha256": validated.universe_snapshot_sha256,
        "provider_attempt_count": validated.provider_attempt_count,
        "worker_count": validated.worker_count,
        "results": [
            {
                "symbol": item.symbol,
                "isin": item.isin,
                "status": item.status.value,
                "failure_code": (
                    None if item.failure_code is None else item.failure_code.value
                ),
                "provider_attempt_count": item.provider_attempt_count,
            }
            for item in validated.results
        ],
    }
    return (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()


def bounded_nifty50_exit_code(outcome: Nifty50BatchOutcomeV1) -> int:
    return {
        Nifty50BatchOutcomeV1.SUCCEEDED: 0,
        Nifty50BatchOutcomeV1.PARTIAL: 3,
        Nifty50BatchOutcomeV1.REJECTED: 2,
        Nifty50BatchOutcomeV1.UNAVAILABLE: 4,
        Nifty50BatchOutcomeV1.FAILED: 5,
        Nifty50BatchOutcomeV1.CANCELLED: 130,
    }.get(outcome, 5)


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )
