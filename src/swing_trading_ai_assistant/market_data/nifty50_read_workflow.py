"""Point-in-time Nifty 50 admission wrappers for zero-provider reads."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from .bounded_nifty50_workflow import Nifty50BatchOutcomeV1
from .catalog import DuckDBCatalog
from .equity_admission import Nifty50AdmissionPolicyV1
from .public_contract import (
    CandleFieldV1,
    CoverageReportV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicFailureCodeV1,
    PublicFailureV1,
    PublicQueryRequestV1,
    QueryReportV1,
    render_coverage_report_json,
    render_query_report_json,
)
from .public_coverage import CoverageRequestV1
from .public_query import QueryRequestV1
from .storage_root_lease import LeaseOutcome, StorageRootLease
from .universe_snapshot import (
    Nifty50UniverseStoreV1,
    UniverseSnapshotAmbiguousError,
    UniverseSnapshotCorruptError,
    UniverseSnapshotNotFoundError,
    UniverseSnapshotStaleError,
)

_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9._-]{0,31}\Z")
_MAX_SYMBOLS = 50
_MAX_WORKERS = 8
MAX_BATCH_QUERY_ROWS_V1 = 5_000
MAX_BATCH_READ_JSON_BYTES_V1 = 8 * 1024 * 1024


class ReadWorkflowClockV1(Protocol):
    def now(self) -> datetime: ...


class CoverageUnderLeasePortV1(Protocol):
    def coverage_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> CoverageReportV1: ...


class QueryUnderLeasePortV1(Protocol):
    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> QueryReportV1: ...


class CoverageFactoryV1(Protocol):
    def __call__(
        self, policy: Nifty50AdmissionPolicyV1
    ) -> CoverageUnderLeasePortV1: ...


class QueryFactoryV1(Protocol):
    def __call__(self, policy: Nifty50AdmissionPolicyV1) -> QueryUnderLeasePortV1: ...


class PointInTimeNifty50CoverageServiceV1:
    def __init__(
        self, factory: CoverageFactoryV1, *, clock: ReadWorkflowClockV1
    ) -> None:
        self._factory = factory
        self._clock = clock

    def coverage(self, request: object) -> CoverageReportV1:
        if type(request) is not CoverageRequestV1:
            return _coverage_terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        invocation = _now(self._clock)
        if invocation is None:
            return _coverage_terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            )
        acquired = StorageRootLease.try_admit_read_existing(request.storage_root)
        if acquired.outcome is not LeaseOutcome.ACQUIRED or acquired.lease is None:
            return _coverage_terminal(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )
        try:
            with acquired.lease as lease:
                policy = _policy(request, invocation, lease)
                return self._factory(policy).coverage_under_lease(request, lease)
        except UniverseSnapshotStaleError:
            return _coverage_terminal(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )
        except ValueError:
            return _coverage_terminal(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
            )
        except Exception:
            return _coverage_terminal(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )


class PointInTimeNifty50QueryServiceV1:
    def __init__(self, factory: QueryFactoryV1, *, clock: ReadWorkflowClockV1) -> None:
        self._factory = factory
        self._clock = clock

    def query(self, request: object) -> QueryReportV1:
        if type(request) is not QueryRequestV1:
            return _query_terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        invocation = _now(self._clock)
        if invocation is None:
            return _query_terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            )
        acquired = StorageRootLease.try_admit_read_existing(request.storage_root)
        if acquired.outcome is not LeaseOutcome.ACQUIRED or acquired.lease is None:
            return _query_terminal(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )
        try:
            with acquired.lease as lease:
                policy = _policy(request, invocation, lease)
                return self._factory(policy).query_under_lease(request, lease)
        except UniverseSnapshotStaleError:
            return _query_terminal(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )
        except ValueError:
            return _query_terminal(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
            )
        except Exception:
            return _query_terminal(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )


@dataclass(frozen=True, slots=True)
class BoundedNifty50ReadRequestV1:
    symbols: tuple[str, ...] | None
    prototype: CoverageRequestV1 | QueryRequestV1
    workers: int = 4

    def __post_init__(self) -> None:
        if (
            (
                self.symbols is not None
                and (
                    type(self.symbols) is not tuple
                    or not self.symbols
                    or len(self.symbols) > _MAX_SYMBOLS
                    or any(
                        type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
                        for symbol in self.symbols
                    )
                    or len(set(self.symbols)) != len(self.symbols)
                )
            )
            or type(self.prototype) not in (CoverageRequestV1, QueryRequestV1)
            or (
                type(self.prototype) is QueryRequestV1
                and not _valid_query_prototype(self.prototype)
            )
            or type(self.workers) is not int
            or not 1 <= self.workers <= _MAX_WORKERS
            or (
                type(self.prototype) is QueryRequestV1
                and self.prototype.max_rows
                * (_MAX_SYMBOLS if self.symbols is None else len(self.symbols))
                > MAX_BATCH_QUERY_ROWS_V1
            )
        ):
            raise ValueError("invalid bounded Nifty 50 read request")


def _valid_query_prototype(request: QueryRequestV1) -> bool:
    if (
        request.timeframe != "1m"
        or not request.storage_root.is_absolute()
        or any(
            character in part
            for part in request.storage_root.parts
            for character in "~*?[]"
        )
    ):
        return False
    try:
        PublicQueryRequestV1(
            request.segment,
            request.symbol,
            request.from_date,
            request.to_date,
            "1m",
            tuple(CandleFieldV1(value) for value in request.fields),
            request.max_rows,
        )
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class Nifty50ReadResultV1:
    symbol: str
    report: PublicCommandReportV1[Any]

    def __post_init__(self) -> None:
        if (
            type(self.symbol) is not str
            or _SYMBOL.fullmatch(self.symbol) is None
            or type(self.report) is not PublicCommandReportV1
            or self.report.provider_attempt_count != 0
        ):
            raise ValueError("invalid Nifty 50 read result")


@dataclass(frozen=True, slots=True)
class BoundedNifty50ReadReportV1:
    command: str
    outcome: Nifty50BatchOutcomeV1
    universe_snapshot_sha256: str | None
    results: tuple[Nifty50ReadResultV1, ...]
    worker_count: int

    def __post_init__(self) -> None:
        if (
            self.command not in ("coverage", "query")
            or type(self.outcome) is not Nifty50BatchOutcomeV1
            or (
                self.universe_snapshot_sha256 is not None
                and (
                    type(self.universe_snapshot_sha256) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", self.universe_snapshot_sha256)
                    is None
                )
            )
            or type(self.results) is not tuple
            or len(self.results) > _MAX_SYMBOLS
            or any(type(result) is not Nifty50ReadResultV1 for result in self.results)
            or any(result.report.command != self.command for result in self.results)
            or len({result.symbol for result in self.results}) != len(self.results)
            or type(self.worker_count) is not int
            or not 0 <= self.worker_count <= _MAX_WORKERS
            or self.worker_count > len(self.results)
            or bool(self.results) != bool(self.worker_count)
            or bool(self.results) != (self.universe_snapshot_sha256 is not None)
            or (
                bool(self.results) and self.outcome is not _aggregate_read(self.results)
            )
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
            raise ValueError("invalid bounded Nifty 50 read report")


class BoundedPointInTimeNifty50ReadServiceV1:
    """Resolve one retained universe and inspect/query members under one lease."""

    def __init__(
        self,
        coverage_factory: CoverageFactoryV1,
        query_factory: QueryFactoryV1,
        *,
        clock: ReadWorkflowClockV1,
    ) -> None:
        self._coverage_factory = coverage_factory
        self._query_factory = query_factory
        self._clock = clock

    def execute(self, request: object) -> BoundedNifty50ReadReportV1:
        if type(request) is not BoundedNifty50ReadRequestV1:
            return _empty_read("coverage", Nifty50BatchOutcomeV1.REJECTED)
        command = (
            "coverage" if type(request.prototype) is CoverageRequestV1 else "query"
        )
        invocation = _now(self._clock)
        if invocation is None:
            return _empty_read(command, Nifty50BatchOutcomeV1.FAILED)
        prototype = request.prototype
        acquired = StorageRootLease.try_admit_read_existing(prototype.storage_root)
        if acquired.outcome is not LeaseOutcome.ACQUIRED or acquired.lease is None:
            return _empty_read(command, Nifty50BatchOutcomeV1.UNAVAILABLE)
        try:
            with acquired.lease as lease:
                with DuckDBCatalog(
                    prototype.storage_root, read_only=True, lease=lease
                ) as catalog:
                    resolved = Nifty50UniverseStoreV1(
                        prototype.storage_root, lease, catalog
                    ).resolve(as_of=prototype.to_date, knowledge_cutoff=invocation)
                    if (
                        resolved.snapshot.effective_from > prototype.from_date
                        or resolved.snapshot.effective_to < prototype.to_date
                    ):
                        raise UniverseSnapshotStaleError(
                            "universe snapshot does not cover request"
                        )
                    catalog.ensure_read_identity()
                policy = Nifty50AdmissionPolicyV1(
                    resolved.metadata.snapshot_sha256,
                    resolved.snapshot,
                    request.symbols,
                )
                port = (
                    self._coverage_factory(policy)
                    if command == "coverage"
                    else self._query_factory(policy)
                )
                worker_count = min(request.workers, len(policy.ordered_symbols))

                def execute_symbol(symbol: str) -> Nifty50ReadResultV1:
                    return self._execute_symbol(command, prototype, symbol, port, lease)

                with ThreadPoolExecutor(
                    max_workers=worker_count,
                    thread_name_prefix=f"nifty50-{command}",
                ) as executor:
                    results = tuple(
                        executor.map(execute_symbol, policy.ordered_symbols)
                    )
                return BoundedNifty50ReadReportV1(
                    command,
                    _aggregate_read(results),
                    resolved.metadata.snapshot_sha256,
                    results,
                    worker_count,
                )
        except ValueError:
            return _empty_read(command, Nifty50BatchOutcomeV1.REJECTED)
        except (UniverseSnapshotNotFoundError, UniverseSnapshotStaleError):
            return _empty_read(command, Nifty50BatchOutcomeV1.UNAVAILABLE)
        except (UniverseSnapshotAmbiguousError, UniverseSnapshotCorruptError):
            return _empty_read(command, Nifty50BatchOutcomeV1.FAILED)
        except Exception:
            return _empty_read(command, Nifty50BatchOutcomeV1.FAILED)

    @staticmethod
    def _execute_symbol(
        command: str,
        prototype: CoverageRequestV1 | QueryRequestV1,
        symbol: str,
        port: CoverageUnderLeasePortV1 | QueryUnderLeasePortV1,
        lease: StorageRootLease,
    ) -> Nifty50ReadResultV1:
        try:
            per_symbol = replace(prototype, symbol=symbol)
            report: PublicCommandReportV1[Any]
            if command == "coverage":
                report = cast(
                    PublicCommandReportV1[Any],
                    cast(CoverageUnderLeasePortV1, port).coverage_under_lease(
                        per_symbol, lease
                    ),
                )
            else:
                report = cast(
                    PublicCommandReportV1[Any],
                    cast(QueryUnderLeasePortV1, port).query_under_lease(
                        per_symbol, lease
                    ),
                )
            if type(report) is not PublicCommandReportV1:
                raise ValueError
            validated = replace(report)
            if validated.command != command or validated.provider_attempt_count != 0:
                raise ValueError
            return Nifty50ReadResultV1(symbol, validated)
        except Exception:
            terminal = (
                _coverage_terminal(
                    PublicCommandStatusV1.FAILED,
                    PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
                )
                if command == "coverage"
                else _query_terminal(
                    PublicCommandStatusV1.FAILED,
                    PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
                )
            )
            return Nifty50ReadResultV1(symbol, terminal)


def render_bounded_nifty50_read_json(report: BoundedNifty50ReadReportV1) -> bytes:
    if type(report) is not BoundedNifty50ReadReportV1:
        report = _empty_read("coverage", Nifty50BatchOutcomeV1.FAILED)
    try:
        validated = replace(
            report,
            results=tuple(
                replace(result, report=replace(result.report))
                for result in report.results
            ),
        )
    except Exception:
        validated = _empty_read("coverage", Nifty50BatchOutcomeV1.FAILED)

    def render_result(result: Nifty50ReadResultV1) -> object:
        if validated.command == "coverage":
            encoded = render_coverage_report_json(cast(CoverageReportV1, result.report))
        else:
            encoded = render_query_report_json(cast(QueryReportV1, result.report))
        return json.loads(encoded)

    value = {
        "contract_version": "v1",
        "command": validated.command,
        "scope": "nifty50",
        "status": validated.outcome.value,
        "universe_snapshot_sha256": validated.universe_snapshot_sha256,
        "provider_attempt_count": 0,
        "worker_count": validated.worker_count,
        "results": [
            {
                "symbol": result.symbol,
                "report": render_result(result),
            }
            for result in validated.results
        ],
    }
    encoded = (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()
    if len(encoded) > MAX_BATCH_READ_JSON_BYTES_V1:
        encoded = (
            json.dumps(
                {
                    "contract_version": "v1",
                    "command": validated.command,
                    "scope": "nifty50",
                    "status": Nifty50BatchOutcomeV1.FAILED.value,
                    "universe_snapshot_sha256": None,
                    "provider_attempt_count": 0,
                    "worker_count": 0,
                    "results": [],
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode()
    return encoded


def _aggregate_read(
    results: tuple[Nifty50ReadResultV1, ...],
) -> Nifty50BatchOutcomeV1:
    statuses = {result.report.status for result in results}
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
    if statuses == {PublicCommandStatusV1.CANCELLED}:
        return Nifty50BatchOutcomeV1.CANCELLED
    return Nifty50BatchOutcomeV1.FAILED


def _empty_read(
    command: str, outcome: Nifty50BatchOutcomeV1
) -> BoundedNifty50ReadReportV1:
    return BoundedNifty50ReadReportV1(command, outcome, None, (), 0)


def bounded_nifty50_read_terminal(
    command: str, outcome: Nifty50BatchOutcomeV1
) -> BoundedNifty50ReadReportV1:
    """Build a command-preserving empty aggregate for CLI admission failures."""
    if (
        command not in ("coverage", "query")
        or type(outcome) is not Nifty50BatchOutcomeV1
    ):
        return _empty_read("coverage", Nifty50BatchOutcomeV1.FAILED)
    return _empty_read(command, outcome)


def _policy(
    request: CoverageRequestV1 | QueryRequestV1,
    invocation: datetime,
    lease: StorageRootLease,
) -> Nifty50AdmissionPolicyV1:
    with DuckDBCatalog(request.storage_root, read_only=True, lease=lease) as catalog:
        resolved = Nifty50UniverseStoreV1(request.storage_root, lease, catalog).resolve(
            as_of=request.to_date, knowledge_cutoff=invocation
        )
        if (
            resolved.snapshot.effective_from > request.from_date
            or resolved.snapshot.effective_to < request.to_date
        ):
            raise UniverseSnapshotStaleError("universe snapshot does not cover request")
        catalog.ensure_read_identity()
    return Nifty50AdmissionPolicyV1(
        resolved.metadata.snapshot_sha256,
        resolved.snapshot,
        (request.symbol,),
    )


def _now(clock: ReadWorkflowClockV1) -> datetime | None:
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


def _coverage_terminal(
    status: PublicCommandStatusV1, code: PublicFailureCodeV1
) -> CoverageReportV1:
    return PublicCommandReportV1(
        "v1",
        "coverage",
        status,
        PublicFailureV1(code, None, None, None, None, ()),
        0,
        None,
    )


def _query_terminal(
    status: PublicCommandStatusV1, code: PublicFailureCodeV1
) -> QueryReportV1:
    return PublicCommandReportV1(
        "v1",
        "query",
        status,
        PublicFailureV1(code, None, None, None, None, ()),
        0,
        None,
    )
