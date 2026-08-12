"""One-command persistence for an advancing current equity month."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol

from .catalog import DuckDBCatalog
from .credentials import AccessToken, AccessTokenProvider
from .download_preparation import (
    DownloadPreparationReportV1,
    DownloadPreparationRequestV1,
    PreparationOutcomeV1,
    PreparedDownloadV1,
)
from .historical import (
    AccountRateLimiter,
    CancellationToken,
    HistoricalRequest,
    HistoricalResponse,
)
from .intraday import IntradayRequest, IntradayResponse
from .monthly_request_planner import PlannedInstrumentMonth, plan_upstox_equity_months
from .normalization import normalize_candles
from .open_month import (
    OpenMonthPlanV1,
    OpenMonthScheduleV1,
    open_month_schedule_from_evidence,
    plan_open_month,
)
from .partition_publication import publish_provisional_partition_under_lease
from .provisional_metadata import (
    ProvisionalPartitionMetadataV1,
    metadata_from_publication,
)
from .provisional_store import latest_provisional_partition
from .provisional_validation import validate_provisional_advance
from .schedule_evidence import SCHEDULE_SCHEMA_VERSION_V3
from .schemas import CanonicalCandle
from .storage_root_lease import LeaseOutcome, StorageRootLease
from .upstox_canonical import canonicalize_upstox_equity_candles
from .workflow_coordination import PublicationGateV1

_HISTORICAL_SOURCE_V3: Final = "upstox-historical-v3"


class OpenMonthDownloadOutcomeV1(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    ALREADY_CURRENT = "ALREADY_CURRENT"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class OpenMonthDownloadFailureCodeV1(StrEnum):
    NONE = "NONE"
    INVALID_INPUT = "INVALID_INPUT"
    PREPARATION_FAILED = "PREPARATION_FAILED"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    CREDENTIALS_UNAVAILABLE = "CREDENTIALS_UNAVAILABLE"
    HISTORICAL_UNAVAILABLE = "HISTORICAL_UNAVAILABLE"
    INTRADAY_UNAVAILABLE = "INTRADAY_UNAVAILABLE"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PUBLICATION_FAILED = "PUBLICATION_FAILED"
    CATALOG_UNAVAILABLE = "CATALOG_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class OpenMonthDownloadRequestV1:
    segment: str
    symbol: str
    from_date: date
    to_date: date
    storage_root: Path

    def __post_init__(self) -> None:
        if (
            type(self.segment) is not str
            or type(self.symbol) is not str
            or type(self.from_date) is not date
            or type(self.to_date) is not date
            or self.from_date > self.to_date
            or self.from_date < date(2022, 1, 1)
            or not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
                self.storage_root, Path
            )
            or not self.storage_root.is_absolute()
            or ".." in self.storage_root.parts
            or any(
                marker in part for part in self.storage_root.parts for marker in "~*?[]"
            )
        ):
            raise ValueError("invalid open-month download request")


@dataclass(frozen=True, slots=True)
class OpenMonthDownloadReportV1:
    outcome: OpenMonthDownloadOutcomeV1
    failure_code: OpenMonthDownloadFailureCodeV1
    metadata: ProvisionalPartitionMetadataV1 | None
    snapshot_attempt_count: int
    historical_attempt_count: int
    intraday_attempt_count: int
    appended_count: int
    missing_count: int

    def __post_init__(self) -> None:
        counts = (
            self.snapshot_attempt_count,
            self.historical_attempt_count,
            self.intraday_attempt_count,
            self.appended_count,
            self.missing_count,
        )
        success = self.outcome in {
            OpenMonthDownloadOutcomeV1.SUCCEEDED,
            OpenMonthDownloadOutcomeV1.ALREADY_CURRENT,
        }
        if (
            type(self.outcome) is not OpenMonthDownloadOutcomeV1
            or type(self.failure_code) is not OpenMonthDownloadFailureCodeV1
            or success != (self.failure_code is OpenMonthDownloadFailureCodeV1.NONE)
            or (success and self.metadata is None)
            or any(type(value) is not int or value < 0 for value in counts)
            or self.snapshot_attempt_count > 1
            or self.historical_attempt_count > 1
            or self.intraday_attempt_count > 1
        ):
            raise ValueError("invalid open-month download report")


@dataclass(frozen=True, slots=True)
class _ProviderBatchV1:
    historical_rows: tuple[CanonicalCandle, ...]
    intraday_rows: tuple[CanonicalCandle, ...]
    historical_attempts: int
    intraday_attempts: int


class OpenMonthPreparationPortV1(Protocol):
    def prepare_open_month(
        self, request: DownloadPreparationRequestV1
    ) -> DownloadPreparationReportV1: ...

    def prepare_open_month_under_lease(
        self, request: DownloadPreparationRequestV1, lease: StorageRootLease
    ) -> DownloadPreparationReportV1: ...


class HistoricalClientPortV1(Protocol):
    def fetch(
        self, request: HistoricalRequest, token: AccessToken
    ) -> HistoricalResponse: ...


class IntradayClientPortV1(Protocol):
    def fetch(
        self, request: IntradayRequest, token: AccessToken
    ) -> IntradayResponse: ...


class OpenMonthClockV1(Protocol):
    def now(self) -> datetime: ...


class OpenMonthDownloadServiceV1:
    """Fetch missing history once and advance only today's immutable prefix."""

    def __init__(
        self,
        preparation: OpenMonthPreparationPortV1,
        historical: HistoricalClientPortV1,
        intraday: IntradayClientPortV1,
        token_provider: AccessTokenProvider,
        *,
        clock: OpenMonthClockV1,
        limiter: AccountRateLimiter | None = None,
        publication_gate: PublicationGateV1 | None = None,
    ) -> None:
        self._preparation = preparation
        self._historical = historical
        self._intraday = intraday
        self._token_provider = token_provider
        self._clock = clock
        self._limiter = limiter
        self._publication_gate = publication_gate

    def download(self, request: object) -> OpenMonthDownloadReportV1:
        return self._download(request, None)

    def download_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> OpenMonthDownloadReportV1:
        """Advance while a bounded parent workflow owns the exact root."""
        if type(lease) is not StorageRootLease:
            return _failure(
                OpenMonthDownloadOutcomeV1.REJECTED,
                OpenMonthDownloadFailureCodeV1.INVALID_INPUT,
            )
        return self._download(request, lease)

    def _download(
        self, request: object, lease: StorageRootLease | None
    ) -> OpenMonthDownloadReportV1:
        if type(request) is not OpenMonthDownloadRequestV1:
            return _failure(
                OpenMonthDownloadOutcomeV1.REJECTED,
                OpenMonthDownloadFailureCodeV1.INVALID_INPUT,
            )
        invocation = _now(self._clock)
        if invocation is None:
            return _failure(
                OpenMonthDownloadOutcomeV1.FAILED,
                OpenMonthDownloadFailureCodeV1.INVALID_INPUT,
            )
        try:
            preparation_request = DownloadPreparationRequestV1(
                request.segment,
                request.symbol,
                request.from_date,
                request.to_date,
                request.storage_root,
                invocation,
            )
            preparation = (
                self._preparation.prepare_open_month(preparation_request)
                if lease is None
                else self._preparation.prepare_open_month_under_lease(
                    preparation_request, lease
                )
            )
        except Exception:
            return _failure(
                OpenMonthDownloadOutcomeV1.FAILED,
                OpenMonthDownloadFailureCodeV1.PREPARATION_FAILED,
            )
        preparation = _validated_preparation(preparation)
        if preparation is None or preparation.prepared is None:
            attempts = (
                preparation.snapshot_attempt_count if preparation is not None else 0
            )
            return _failure(
                OpenMonthDownloadOutcomeV1.UNAVAILABLE,
                OpenMonthDownloadFailureCodeV1.PREPARATION_FAILED,
                snapshot_attempts=attempts,
            )
        return self._download_prepared(
            request, invocation, preparation.prepared, supplied_lease=lease
        )

    def _download_prepared(
        self,
        request: OpenMonthDownloadRequestV1,
        invocation: datetime,
        prepared: PreparedDownloadV1,
        *,
        supplied_lease: StorageRootLease | None = None,
    ) -> OpenMonthDownloadReportV1:
        snapshot_attempts = prepared.snapshot_attempt_count
        try:
            if prepared.schedule.schema_version != SCHEDULE_SCHEMA_VERSION_V3:
                raise ValueError
            schedule = open_month_schedule_from_evidence(prepared.schedule)
            open_plan = plan_open_month(
                request.from_date, request.to_date, schedule, invocation
            )
            physical_plan = plan_upstox_equity_months(
                prepared.instrument,
                open_plan.month_start,
                request.to_date,
                "1m",
            )[0]
        except Exception:
            return _failure(
                OpenMonthDownloadOutcomeV1.REJECTED,
                OpenMonthDownloadFailureCodeV1.INVALID_INPUT,
                snapshot_attempts=snapshot_attempts,
            )

        if supplied_lease is not None:
            try:
                with supplied_lease.root_operation(request.storage_root) as operation:
                    operation.ensure_live()
                return self._advance_under_lease(
                    request,
                    invocation,
                    prepared,
                    schedule,
                    open_plan,
                    physical_plan,
                    supplied_lease,
                )
            except Exception:
                return _failure(
                    OpenMonthDownloadOutcomeV1.FAILED,
                    OpenMonthDownloadFailureCodeV1.PUBLICATION_FAILED,
                    snapshot_attempts=snapshot_attempts,
                )

        lease_result = StorageRootLease.try_acquire(request.storage_root)
        if (
            lease_result.outcome is not LeaseOutcome.ACQUIRED
            or lease_result.lease is None
        ):
            return _failure(
                OpenMonthDownloadOutcomeV1.UNAVAILABLE,
                OpenMonthDownloadFailureCodeV1.STORAGE_UNAVAILABLE,
                snapshot_attempts=snapshot_attempts,
            )
        try:
            with lease_result.lease as lease:
                return self._advance_under_lease(
                    request,
                    invocation,
                    prepared,
                    schedule,
                    open_plan,
                    physical_plan,
                    lease,
                )
        except Exception:
            return _failure(
                OpenMonthDownloadOutcomeV1.FAILED,
                OpenMonthDownloadFailureCodeV1.PUBLICATION_FAILED,
                snapshot_attempts=snapshot_attempts,
            )

    def _advance_under_lease(
        self,
        request: OpenMonthDownloadRequestV1,
        invocation: datetime,
        prepared: PreparedDownloadV1,
        schedule: OpenMonthScheduleV1,
        open_plan: OpenMonthPlanV1,
        physical_plan: PlannedInstrumentMonth,
        lease: StorageRootLease,
    ) -> OpenMonthDownloadReportV1:
        # The exact domain types were constructed above; local imports would only
        # duplicate their validators. Any mutation fails in the called boundaries.
        intraday_target = open_plan.last_completed_bar_start
        effective_target = _effective_target_cutoff(schedule, open_plan)
        existing = self._existing_under_gate(
            request, invocation, physical_plan, effective_target, lease
        )
        metadata = existing[0] if existing is not None else None
        existing_rows = existing[1] if existing is not None else ()
        pending_history = _pending_history_range(schedule, open_plan, existing_rows)
        if (
            metadata is not None
            and effective_target is not None
            and metadata.cutoff == effective_target
            and metadata.schedule_digest_sha256 == open_plan.schedule_digest
            and metadata.published_at <= invocation
            and pending_history is None
        ):
            return OpenMonthDownloadReportV1(
                OpenMonthDownloadOutcomeV1.ALREADY_CURRENT,
                OpenMonthDownloadFailureCodeV1.NONE,
                metadata,
                prepared.snapshot_attempt_count,
                0,
                0,
                0,
                0,
            )

        need_intraday = intraday_target is not None and (
            metadata is None or metadata.cutoff < intraday_target
        )
        fetched = self._fetch_missing(
            prepared, invocation, pending_history, need_intraday
        )
        if isinstance(fetched, OpenMonthDownloadReportV1):
            return fetched
        historical_attempts = fetched.historical_attempts
        intraday_attempts = fetched.intraday_attempts

        return self._validate_and_publish_guarded(
            request,
            invocation,
            prepared,
            schedule,
            open_plan,
            physical_plan,
            lease,
            existing_rows,
            fetched,
            historical_attempts,
            intraday_attempts,
        )

    def _existing_under_gate(
        self,
        request: OpenMonthDownloadRequestV1,
        invocation: datetime,
        physical_plan: PlannedInstrumentMonth,
        target: datetime | None,
        lease: StorageRootLease,
    ) -> tuple[ProvisionalPartitionMetadataV1, tuple[CanonicalCandle, ...]] | None:
        gate = self._publication_gate
        if gate is None:
            return self._load_existing(
                request, invocation, physical_plan, target, lease
            )
        with gate:
            return self._load_existing(
                request, invocation, physical_plan, target, lease
            )

    @staticmethod
    def _load_existing(
        request: OpenMonthDownloadRequestV1,
        invocation: datetime,
        physical_plan: PlannedInstrumentMonth,
        target: datetime | None,
        lease: StorageRootLease,
    ) -> tuple[ProvisionalPartitionMetadataV1, tuple[CanonicalCandle, ...]] | None:
        return (
            None
            if target is None
            else latest_provisional_partition(
                request.storage_root,
                lease,
                physical_plan,
                cutoff_lte=target,
                published_at_lte=invocation,
            )
        )

    def _validate_and_publish_guarded(
        self,
        request: OpenMonthDownloadRequestV1,
        invocation: datetime,
        prepared: PreparedDownloadV1,
        schedule: OpenMonthScheduleV1,
        open_plan: OpenMonthPlanV1,
        physical_plan: PlannedInstrumentMonth,
        lease: StorageRootLease,
        existing_rows: tuple[CanonicalCandle, ...],
        fetched: _ProviderBatchV1,
        historical_attempts: int,
        intraday_attempts: int,
    ) -> OpenMonthDownloadReportV1:
        gate = self._publication_gate
        if gate is None:
            return self._validate_and_publish(
                request,
                invocation,
                prepared,
                schedule,
                open_plan,
                physical_plan,
                lease,
                existing_rows,
                fetched,
                historical_attempts,
                intraday_attempts,
            )
        with gate:
            return self._validate_and_publish(
                request,
                invocation,
                prepared,
                schedule,
                open_plan,
                physical_plan,
                lease,
                existing_rows,
                fetched,
                historical_attempts,
                intraday_attempts,
            )

    def _validate_and_publish(
        self,
        request: OpenMonthDownloadRequestV1,
        invocation: datetime,
        prepared: PreparedDownloadV1,
        schedule: OpenMonthScheduleV1,
        open_plan: OpenMonthPlanV1,
        physical_plan: PlannedInstrumentMonth,
        lease: StorageRootLease,
        existing_rows: tuple[CanonicalCandle, ...],
        fetched: _ProviderBatchV1,
        historical_attempts: int,
        intraday_attempts: int,
    ) -> OpenMonthDownloadReportV1:

        try:
            validation = validate_provisional_advance(
                schedule,
                open_plan,
                existing_rows,
                fetched.historical_rows,
                fetched.intraday_rows,
            )
        except Exception:
            return _failure(
                OpenMonthDownloadOutcomeV1.FAILED,
                OpenMonthDownloadFailureCodeV1.VALIDATION_FAILED,
                snapshot_attempts=prepared.snapshot_attempt_count,
                historical_attempts=historical_attempts,
                intraday_attempts=intraday_attempts,
            )
        if not validation.candles or validation.actual_cutoff is None:
            return _failure(
                OpenMonthDownloadOutcomeV1.PARTIAL,
                OpenMonthDownloadFailureCodeV1.VALIDATION_FAILED,
                snapshot_attempts=prepared.snapshot_attempt_count,
                historical_attempts=historical_attempts,
                intraday_attempts=intraday_attempts,
                missing=validation.missing_count,
            )
        try:
            published = publish_provisional_partition_under_lease(
                request.storage_root,
                lease,
                physical_plan,
                validation.actual_cutoff,
                validation.schedule_digest,
                validation.candles,
            )
            published_at = max(
                invocation,
                prepared.snapshot_retrieved_at,
                validation.actual_cutoff,
            ).astimezone(UTC)
            metadata = metadata_from_publication(
                plan=published.plan,
                schedule_digest_sha256=published.schedule_digest,
                cutoff=published.cutoff,
                session_complete=validation.session_complete,
                actual_from_ts=published.actual_from_ts,
                actual_to_ts=published.actual_to_ts,
                row_count=published.row_count,
                checksum_sha256=published.checksum_sha256,
                byte_size=published.byte_size,
                relative_path=published.canonical_path,
                instrument_snapshot_digest_sha256=prepared.snapshot_digest_sha256,
                instrument_snapshot_retrieved_at=prepared.snapshot_retrieved_at,
                published_at=published_at,
                historical_attempt_count=historical_attempts,
                intraday_attempt_count=intraday_attempts,
            )
            with DuckDBCatalog(request.storage_root, lease=lease) as catalog:
                catalog.save_provisional_partition(metadata)
        except Exception:
            return _failure(
                OpenMonthDownloadOutcomeV1.FAILED,
                OpenMonthDownloadFailureCodeV1.CATALOG_UNAVAILABLE,
                snapshot_attempts=prepared.snapshot_attempt_count,
                historical_attempts=historical_attempts,
                intraday_attempts=intraday_attempts,
            )
        outcome = (
            OpenMonthDownloadOutcomeV1.SUCCEEDED
            if validation.complete_to_target
            else OpenMonthDownloadOutcomeV1.PARTIAL
        )
        code = (
            OpenMonthDownloadFailureCodeV1.NONE
            if outcome is OpenMonthDownloadOutcomeV1.SUCCEEDED
            else OpenMonthDownloadFailureCodeV1.VALIDATION_FAILED
        )
        return OpenMonthDownloadReportV1(
            outcome,
            code,
            metadata,
            prepared.snapshot_attempt_count,
            historical_attempts,
            intraday_attempts,
            validation.appended_count,
            validation.missing_count,
        )

    def _fetch_missing(
        self,
        prepared: PreparedDownloadV1,
        invocation: datetime,
        pending_history: tuple[date, date] | None,
        need_intraday: bool,
    ) -> _ProviderBatchV1 | OpenMonthDownloadReportV1:
        token: AccessToken | None = None
        if pending_history is not None or need_intraday:
            try:
                token = self._token_provider.get_access_token()
            except Exception:
                return _failure(
                    OpenMonthDownloadOutcomeV1.UNAVAILABLE,
                    OpenMonthDownloadFailureCodeV1.CREDENTIALS_UNAVAILABLE,
                    snapshot_attempts=prepared.snapshot_attempt_count,
                )
        historical_rows: tuple[CanonicalCandle, ...] = ()
        intraday_rows: tuple[CanonicalCandle, ...] = ()
        historical_attempts = int(pending_history is not None)
        intraday_attempts = int(need_intraday)
        if pending_history is not None:
            try:
                self._admit_provider_request()
                historical_from, historical_to = pending_history
                response = self._historical.fetch(
                    HistoricalRequest(
                        prepared.instrument.instrument_key,
                        "minutes",
                        1,
                        historical_from,
                        historical_to,
                    ),
                    token,  # type: ignore[arg-type]
                )
                historical_rows = _canonical_rows(
                    response, prepared, invocation, intraday=False
                )
            except Exception:
                return _failure(
                    OpenMonthDownloadOutcomeV1.UNAVAILABLE,
                    OpenMonthDownloadFailureCodeV1.HISTORICAL_UNAVAILABLE,
                    snapshot_attempts=prepared.snapshot_attempt_count,
                    historical_attempts=historical_attempts,
                )
        if need_intraday:
            try:
                self._admit_provider_request()
                response = self._intraday.fetch(
                    IntradayRequest(prepared.instrument.instrument_key),
                    token,  # type: ignore[arg-type]
                )
                intraday_rows = _canonical_rows(
                    response, prepared, invocation, intraday=True
                )
            except Exception:
                return _failure(
                    OpenMonthDownloadOutcomeV1.UNAVAILABLE,
                    OpenMonthDownloadFailureCodeV1.INTRADAY_UNAVAILABLE,
                    snapshot_attempts=prepared.snapshot_attempt_count,
                    historical_attempts=historical_attempts,
                    intraday_attempts=intraday_attempts,
                )
        return _ProviderBatchV1(
            historical_rows,
            intraday_rows,
            historical_attempts,
            intraday_attempts,
        )

    def _admit_provider_request(self) -> None:
        if self._limiter is None:
            return
        self._limiter.acquire(CancellationToken(), timedelta(seconds=120))


def _validated_preparation(
    value: object,
) -> DownloadPreparationReportV1 | None:
    try:
        if type(value) is not DownloadPreparationReportV1:
            raise ValueError
        prepared = value.prepared
        if prepared is not None:
            if type(prepared) is not PreparedDownloadV1:
                raise ValueError
            prepared = replace(prepared)
        result = replace(value, prepared=prepared)
        if result.outcome is not PreparationOutcomeV1.SUCCEEDED:
            return result
        return result if result.prepared is not None else None
    except Exception:
        return None


def _effective_target_cutoff(
    schedule: OpenMonthScheduleV1, plan: OpenMonthPlanV1
) -> datetime | None:
    if plan.last_completed_bar_start is not None:
        return plan.last_completed_bar_start
    if plan.historical_to is None:
        return None
    candidates = tuple(
        session.close_at - timedelta(minutes=1)
        for session in schedule.sessions
        if session.trade_date <= plan.historical_to
    )
    return max(candidates).astimezone(UTC) if candidates else None


def _pending_history_range(
    schedule: OpenMonthScheduleV1,
    plan: OpenMonthPlanV1,
    existing: tuple[CanonicalCandle, ...],
) -> tuple[date, date] | None:
    if plan.historical_from is None or plan.historical_to is None:
        return None
    existing_by_timestamp = {candle.ts: candle for candle in existing}
    pending_dates: list[date] = []
    for session in schedule.sessions:
        if not plan.historical_from <= session.trade_date <= plan.historical_to:
            continue
        timestamp = session.open_at
        final_timestamp = session.close_at - timedelta(minutes=1)
        while timestamp <= final_timestamp:
            candle = existing_by_timestamp.get(timestamp)
            if candle is None or candle.source_version != _HISTORICAL_SOURCE_V3:
                pending_dates.append(session.trade_date)
                break
            timestamp += timedelta(minutes=1)
    if not pending_dates:
        return None
    historical_from = plan.historical_from if not existing else min(pending_dates)
    return historical_from, max(pending_dates)


def _canonical_rows(
    response: HistoricalResponse | IntradayResponse,
    prepared: PreparedDownloadV1,
    ingested_at: datetime,
    *,
    intraday: bool,
) -> tuple[CanonicalCandle, ...]:
    if not 200 <= response.status_code < 300 or response.error_category is not None:
        raise ValueError
    normalized = normalize_candles(response.candles)
    rows = canonicalize_upstox_equity_candles(
        normalized, prepared.instrument, ingested_at
    )
    if intraday:
        return tuple(
            replace(value, source_version="upstox-intraday-v3") for value in rows
        )
    return rows


def _now(clock: OpenMonthClockV1) -> datetime | None:
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


def _failure(
    outcome: OpenMonthDownloadOutcomeV1,
    code: OpenMonthDownloadFailureCodeV1,
    *,
    snapshot_attempts: int = 0,
    historical_attempts: int = 0,
    intraday_attempts: int = 0,
    missing: int = 0,
) -> OpenMonthDownloadReportV1:
    return OpenMonthDownloadReportV1(
        outcome,
        code,
        None,
        snapshot_attempts,
        historical_attempts,
        intraday_attempts,
        0,
        missing,
    )
