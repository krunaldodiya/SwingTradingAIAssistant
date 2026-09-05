"""Execute one requestable canonical equity-month ingestion lifecycle."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from .catalog import CatalogPersistenceError, CatalogStorageError
from .historical import (
    CancellationRequested,
    CancellationSignal,
    HistoricalFetchCode,
    HistoricalFetchResult,
)
from .instruments import Instrument
from .manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    fail_manifest,
    retry_manifest,
    verify_manifest,
)
from .monthly_request_planner import PlannedInstrumentMonth, plan_upstox_equity_months
from .normalization import normalize_candles
from .partition_publication import (
    PartitionPublicationError,
    PartitionValidationError,
    PartitionWriteError,
    PublicationConflictError,
    PublicationOutcomeUnknown,
    PublishedPartitionEvidence,
    publish_partition,
)
from .schedule_evidence import ScheduleEvidenceResult
from .schemas import CANDLE_SCHEMA_VERSION, CanonicalCandle
from .upstox_canonical import canonicalize_upstox_equity_candles
from .validation import EquityMonthValidationPolicy, ValidationEvidence

_SOURCE_VERSION = "upstox-historical-v3"
_POLICY_SEPARATOR = "+sessions-sha256:"
_MAX_PUBLIC_ATTEMPTS = 1_000_000
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SAFE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")


def _validate_result_types(result: PartitionLifecycleResult) -> None:
    if type(result.plan) is not PlannedInstrumentMonth:
        raise ValueError("invalid partition lifecycle result")
    if type(result.outcome) is not PartitionLifecycleOutcome:
        raise ValueError("invalid partition lifecycle result")
    if (
        type(result.ingestion_run_id) is not str
        or _SAFE_ID.fullmatch(result.ingestion_run_id) is None
        or type(result.provider_attempts) is not int
        or not 0 <= result.provider_attempts <= _MAX_PUBLIC_ATTEMPTS
        or (
            result.error_code is not None
            and (
                type(result.error_code) is not str
                or _SAFE_CODE.fullmatch(result.error_code) is None
            )
        )
        or (
            result.failure_category is not None
            and type(result.failure_category) is not FailureCategory
        )
        or (
            result.final_manifest is not None
            and type(result.final_manifest) is not PartitionManifest
        )
    ):
        raise ValueError("invalid partition lifecycle result")


def _valid_result_outcome(result: PartitionLifecycleResult) -> bool:
    if result.outcome is PartitionLifecycleOutcome.SKIPPED_VERIFIED:
        return (
            result.final_manifest is not None
            and result.final_manifest.state is ManifestState.VERIFIED
            and result.provider_attempts == 0
            and result.failure_category is None
            and result.error_code is None
        )
    if result.outcome is PartitionLifecycleOutcome.VERIFIED:
        return (
            result.final_manifest is not None
            and result.final_manifest.state is ManifestState.VERIFIED
            and result.provider_attempts > 0
            and result.failure_category is None
            and result.error_code is None
        )
    if result.outcome is PartitionLifecycleOutcome.FAILED:
        return (
            result.final_manifest is not None
            and result.final_manifest.state is ManifestState.FAILED
            and result.failure_category is not None
            and result.failure_category is not FailureCategory.INTERRUPTED
            and result.error_code is not None
            and result.error_code != "CANCELLED"
            and result.final_manifest.failure_category is result.failure_category
        )
    if result.error_code != "CANCELLED":
        return False
    if result.final_manifest is None:
        return result.provider_attempts == 0 and result.failure_category is None
    return (
        result.failure_category is FailureCategory.INTERRUPTED
        and result.final_manifest.state is ManifestState.FAILED
        and result.final_manifest.failure_category is FailureCategory.INTERRUPTED
    )


class PartitionLifecycleOutcome(StrEnum):
    VERIFIED = "VERIFIED"
    SKIPPED_VERIFIED = "SKIPPED_VERIFIED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class PartitionLifecycleResult:
    """Sanitized evidence for one requested partition attempt."""

    plan: PlannedInstrumentMonth
    outcome: PartitionLifecycleOutcome
    ingestion_run_id: str
    provider_attempts: int
    final_manifest: PartitionManifest | None
    failure_category: FailureCategory | None
    error_code: str | None

    def __post_init__(self) -> None:
        _validate_result_types(self)
        if self.final_manifest is not None and (
            self.final_manifest.plan != self.plan
            or self.final_manifest.ingestion_run_id != self.ingestion_run_id
        ):
            raise ValueError("invalid partition lifecycle result")
        if not _valid_result_outcome(self):
            raise ValueError("invalid partition lifecycle result")


class PartitionFetcher(Protocol):
    def fetch(self, plan: PlannedInstrumentMonth) -> HistoricalFetchResult:
        """Return one already bounded Child F result."""

        ...


class PartitionCatalog(Protocol):
    def get_manifest(self, plan: PlannedInstrumentMonth) -> PartitionManifest | None:
        """Return the current manifest for the physical identity."""

        ...

    def create_manifest(self, manifest: PartitionManifest) -> None:
        """Create the first IN_PROGRESS manifest."""

        ...

    def transition_manifest(
        self, current: PartitionManifest, target: PartitionManifest
    ) -> None:
        """Persist one exact ARK-40 transition and terminal history."""

        ...


class UtcClock(Protocol):
    def now(self) -> datetime:
        """Return an aware UTC timestamp."""

        ...


class PartitionLifecycleConflict(RuntimeError):
    """The supplied request is not a requestable current partition."""


class PartitionCatalogFailure(RuntimeError):
    """Catalog persistence failed after the lifecycle began."""


class PartitionClockFailure(RuntimeError):
    """Injected clock access failed without exposing its cause."""


def _default_publisher(
    storage_root: Path,
    plan: PlannedInstrumentMonth,
    candles: Sequence[CanonicalCandle],
) -> PublishedPartitionEvidence:
    return publish_partition(storage_root, plan, candles)


class PartitionIngestionExecutor:
    """Compose Child F, Child E, publication, and ARK-40 lifecycle evidence."""

    def __init__(
        self,
        *,
        instrument: Instrument,
        expected_sessions: ScheduleEvidenceResult,
        validation_policy: EquityMonthValidationPolicy,
        fetcher: PartitionFetcher,
        catalog: PartitionCatalog,
        storage_root: Path,
        clock: UtcClock,
        run_id: str,
        cancellation: CancellationSignal,
        publisher: Callable[
            [Path, PlannedInstrumentMonth, Sequence[CanonicalCandle]],
            PublishedPartitionEvidence,
        ] = _default_publisher,
    ) -> None:
        if type(instrument) is not Instrument:
            raise ValueError("a resolved instrument is required")
        if type(expected_sessions) is not ScheduleEvidenceResult:
            raise ValueError("schedule evidence is required")
        if type(validation_policy) is not EquityMonthValidationPolicy:
            raise ValueError("an equity-month validation policy is required")
        if type(run_id) is not str or _SAFE_ID.fullmatch(run_id) is None:
            raise ValueError("invalid partition lifecycle input")
        self._instrument = instrument
        self._expected_sessions = expected_sessions
        self._validation_policy = validation_policy
        self._fetcher = fetcher
        self._catalog = catalog
        self._storage_root = storage_root
        self._clock = clock
        self._run_id = run_id
        self._cancellation = cancellation
        self._publisher = publisher

    def execute(self, plan: PlannedInstrumentMonth) -> PartitionLifecycleResult:
        """Run one requestable plan exactly once through the lifecycle."""
        if self._cancelled():
            return self._cancelled_result(plan)
        _validate_request_plan(plan, self._instrument)
        current = self._fetch_current(plan)
        if self._cancelled():
            return self._cancelled_result(plan)
        skipped = self._skip_verified_if_requested(plan, current)
        if skipped is not None:
            return skipped
        try:
            active = self._start_manifest(plan, current)
        except PartitionCatalogFailure:
            raise
        except PartitionClockFailure:
            if self._cancelled():
                return self._cancelled_result(plan)
            raise
        if active is None:
            return self._cancelled_result(plan)
        if self._cancelled():
            return self._terminal_failure(
                active, FailureCategory.INTERRUPTED, 0, "CANCELLED"
            )
        return self._fetch_and_continue(active, plan)

    def _fetch_current(self, plan: PlannedInstrumentMonth) -> PartitionManifest | None:
        try:
            current = self._catalog.get_manifest(plan)
        except (CatalogPersistenceError, CatalogStorageError):
            if self._cancelled():
                return None
            raise PartitionCatalogFailure("catalog access failed") from None
        if current is not None and type(current) is not PartitionManifest:
            raise PartitionCatalogFailure("catalog returned invalid manifest") from None
        if current is not None and current.plan != plan:
            raise PartitionCatalogFailure(
                "catalog returned manifest for non-requested contract"
            ) from None
        return current

    def _skip_verified_if_requested(
        self, plan: PlannedInstrumentMonth, current: PartitionManifest | None
    ) -> PartitionLifecycleResult | None:
        if current is None or current.state is not ManifestState.VERIFIED:
            return None
        return PartitionLifecycleResult(
            plan,
            PartitionLifecycleOutcome.SKIPPED_VERIFIED,
            current.ingestion_run_id,
            0,
            current,
            None,
            None,
        )

    def _fetch_and_continue(
        self, active: PartitionManifest, plan: PlannedInstrumentMonth
    ) -> PartitionLifecycleResult:
        try:
            fetched = self._fetcher.fetch(plan)
        except CancellationRequested:
            return self._terminal_failure(
                active, FailureCategory.INTERRUPTED, 0, "CANCELLED"
            )
        except Exception:
            if self._cancelled():
                return self._terminal_failure(
                    active, FailureCategory.INTERRUPTED, 0, "CANCELLED"
                )
            return self._terminal_failure(
                active,
                FailureCategory.PROVIDER_NON_RETRYABLE,
                0,
                "PROVIDER_CONTRACT",
            )
        if type(fetched) is not HistoricalFetchResult:
            return self._terminal_failure(
                active,
                FailureCategory.PROVIDER_NON_RETRYABLE,
                0,
                "PROVIDER_CONTRACT",
            )
        attempts = _attempts(fetched)
        if self._cancelled():
            return self._terminal_failure(
                active, FailureCategory.INTERRUPTED, attempts, "CANCELLED"
            )
        if fetched.failure is not None:
            category = _provider_category(fetched.failure.code)
            outcome = (
                PartitionLifecycleOutcome.CANCELLED
                if fetched.failure.code is HistoricalFetchCode.CANCELLED
                else PartitionLifecycleOutcome.FAILED
            )
            return self._terminal_failure(
                active, category, attempts, fetched.failure.code.value, outcome
            )
        return self._normalize_and_continue(active, plan, fetched, attempts)

    def _normalize_and_continue(
        self,
        active: PartitionManifest,
        plan: PlannedInstrumentMonth,
        fetched: HistoricalFetchResult,
        attempts: int,
    ) -> PartitionLifecycleResult:
        response = fetched.response
        if response is None:
            return self._terminal_failure(
                active,
                FailureCategory.PROVIDER_NON_RETRYABLE,
                attempts,
                "PROVIDER_CONTRACT",
            )
        if not response.candles:
            return self._terminal_failure(
                active, FailureCategory.EMPTY_RESPONSE, attempts, "EMPTY_RESPONSE"
            )

        try:
            normalized = normalize_candles(response.candles)
            ingested_at = fetched.retrieved_at
            if ingested_at is None:
                raise ValueError("successful fetch has no retrieval timestamp")
            canonical = canonicalize_upstox_equity_candles(
                normalized, self._instrument, ingested_at
            )
        except Exception:
            if self._cancelled():
                return self._terminal_failure(
                    active, FailureCategory.INTERRUPTED, attempts, "CANCELLED"
                )
            return self._terminal_failure(
                active,
                FailureCategory.NORMALIZATION_FAILED,
                attempts,
                "NORMALIZATION_FAILED",
            )
        if self._cancelled():
            return self._terminal_failure(
                active, FailureCategory.INTERRUPTED, attempts, "CANCELLED"
            )
        return self._validate_and_publish(
            active, plan, response.candles, normalized, canonical, attempts
        )

    def _validate_and_publish(
        self,
        active: PartitionManifest,
        plan: PlannedInstrumentMonth,
        raw_candles: list[list[object]],
        normalized: Sequence[object],
        canonical: Sequence[CanonicalCandle],
        attempts: int,
    ) -> PartitionLifecycleResult:
        validation = self._run_validation(plan, canonical, raw_candles, normalized)
        if validation is None:
            return self._validation_failure(active, attempts)
        if not validation.coverage_passed or not validation.quality_passed:
            if self._cancelled():
                return self._terminal_failure(
                    active, FailureCategory.INTERRUPTED, attempts, "CANCELLED"
                )
            return self._terminal_failure(
                active,
                FailureCategory.VALIDATION_FAILED,
                attempts,
                validation.reason.value,
                row_count=validation.row_count,
                actual_from_ts=validation.actual_from_ts,
                actual_to_ts=validation.actual_to_ts,
                candle_schema_version=CANDLE_SCHEMA_VERSION,
            )
        if self._cancelled():
            return self._terminal_failure(
                active, FailureCategory.INTERRUPTED, attempts, "CANCELLED"
            )

        try:
            published = self._publish(plan, canonical, active)
        except Exception as error:
            return self._publication_failure(active, attempts, error)
        if self._cancelled():
            return self._terminal_failure(
                active,
                FailureCategory.INTERRUPTED,
                attempts,
                "CANCELLED",
                row_count=published.row_count,
                actual_from_ts=published.actual_from_ts,
                actual_to_ts=published.actual_to_ts,
                checksum_sha256=published.checksum_sha256,
                canonical_path=published.canonical_path,
                candle_schema_version=published.candle_schema_version,
            )
        try:
            verified = verify_manifest(
                active,
                max(_utc_now(self._clock), active.updated_at),
                published.actual_from_ts,
                published.actual_to_ts,
                published.row_count,
                published.checksum_sha256,
                published.canonical_path,
            )
        except Exception:
            if self._cancelled():
                return self._terminal_failure(
                    active, FailureCategory.INTERRUPTED, attempts, "CANCELLED"
                )
            raise
        if self._cancelled():
            return self._terminal_failure(
                active,
                FailureCategory.INTERRUPTED,
                attempts,
                "CANCELLED",
                row_count=published.row_count,
                actual_from_ts=published.actual_from_ts,
                actual_to_ts=published.actual_to_ts,
                checksum_sha256=published.checksum_sha256,
                canonical_path=published.canonical_path,
                candle_schema_version=published.candle_schema_version,
            )
        self._transition(active, verified)
        return PartitionLifecycleResult(
            plan,
            PartitionLifecycleOutcome.VERIFIED,
            active.ingestion_run_id,
            attempts,
            verified,
            None,
            None,
        )

    def _run_validation(
        self,
        plan: PlannedInstrumentMonth,
        canonical: Sequence[CanonicalCandle],
        raw_candles: Sequence[object],
        normalized: Sequence[object],
    ) -> ValidationEvidence | None:
        try:
            validation = self._validation_policy.validate(
                plan,
                canonical,
                self._expected_sessions,
                raw_row_count=len(raw_candles),
                normalized_row_count=len(normalized),
            )
        except Exception:
            return None
        return validation if type(validation) is ValidationEvidence else None

    def _validation_failure(
        self, active: PartitionManifest, attempts: int
    ) -> PartitionLifecycleResult:
        if self._cancelled():
            return self._terminal_failure(
                active, FailureCategory.INTERRUPTED, attempts, "CANCELLED"
            )
        return self._terminal_failure(
            active, FailureCategory.VALIDATION_FAILED, attempts, "VALIDATION_ERROR"
        )

    def _publish(
        self,
        plan: PlannedInstrumentMonth,
        canonical: Sequence[CanonicalCandle],
        active: PartitionManifest,
    ) -> PublishedPartitionEvidence:
        published = self._publisher(self._storage_root, plan, canonical)
        _validate_publication(published, plan, canonical, active)
        return published

    def _publication_failure(
        self, active: PartitionManifest, attempts: int, error: Exception
    ) -> PartitionLifecycleResult:
        if self._cancelled():
            return self._terminal_failure(
                active, FailureCategory.INTERRUPTED, attempts, "CANCELLED"
            )
        category = _trusted_publication_category(error)
        return self._terminal_failure(active, category, attempts, category.value)

    def _start_manifest(
        self, plan: PlannedInstrumentMonth, current: PartitionManifest | None
    ) -> PartitionManifest | None:
        now = _utc_now(self._clock)
        policy_version = _bound_policy_version(
            self._validation_policy.policy_version, self._expected_sessions.digest
        )
        if current is None:
            active = PartitionManifest(
                1,
                plan,
                self._run_id,
                None,
                ManifestState.IN_PROGRESS,
                ValidationOutcome.NOT_RUN,
                policy_version,
                None,
                None,
                None,
                None,
                None,
                _SOURCE_VERSION,
                now,
                now,
                now,
                None,
            )
            try:
                self._catalog.create_manifest(active)
            except (CatalogPersistenceError, CatalogStorageError):
                authoritative, reconciled = self._recover_active_manifest(plan, active)
                if reconciled is not None:
                    return reconciled
                if authoritative and self._cancelled():
                    return None
                raise PartitionCatalogFailure("catalog create failed") from None
            return active
        if current.state is not ManifestState.FAILED:
            raise PartitionLifecycleConflict("partition is not requestable")
        retry_started_at = max(now, current.updated_at + timedelta(microseconds=1))
        active = retry_manifest(
            current,
            self._run_id,
            _SOURCE_VERSION,
            policy_version,
            retry_started_at,
            retry_started_at,
        )
        self._transition(current, active)
        return active

    def _recover_active_manifest(
        self, plan: PlannedInstrumentMonth, attempted: PartitionManifest
    ) -> tuple[bool, PartitionManifest | None]:
        try:
            observed = self._catalog.get_manifest(plan)
            if observed is None:
                return True, None
            if type(observed) is not PartitionManifest or observed != attempted:
                return False, None
        except (CatalogPersistenceError, CatalogStorageError):
            raise PartitionCatalogFailure("catalog create failed") from None
        return True, observed

    def _terminal_failure(
        self,
        active: PartitionManifest,
        category: FailureCategory,
        attempts: int,
        error_code: str,
        outcome: PartitionLifecycleOutcome = PartitionLifecycleOutcome.FAILED,
        *,
        row_count: int | None = None,
        actual_from_ts: datetime | None = None,
        actual_to_ts: datetime | None = None,
        checksum_sha256: str | None = None,
        canonical_path: str | None = None,
        candle_schema_version: int | None = None,
    ) -> PartitionLifecycleResult:
        if self._cancelled():
            category = FailureCategory.INTERRUPTED
            error_code = "CANCELLED"
            outcome = PartitionLifecycleOutcome.CANCELLED
        if (
            category is FailureCategory.INTERRUPTED
            and outcome is PartitionLifecycleOutcome.FAILED
        ):
            outcome = PartitionLifecycleOutcome.CANCELLED
        try:
            updated_at = _utc_now(self._clock)
        except PartitionClockFailure:
            if not self._cancelled():
                raise
            updated_at = active.updated_at
            category = FailureCategory.INTERRUPTED
            error_code = "CANCELLED"
            outcome = PartitionLifecycleOutcome.CANCELLED
        failed = fail_manifest(
            active,
            updated_at,
            category,
            row_count=row_count,
            actual_from_ts=actual_from_ts,
            actual_to_ts=actual_to_ts,
            checksum_sha256=checksum_sha256,
            canonical_path=canonical_path,
            candle_schema_version=candle_schema_version,
        )
        self._transition(active, failed)
        return PartitionLifecycleResult(
            active.plan,
            outcome,
            active.ingestion_run_id,
            attempts,
            failed,
            category,
            error_code,
        )

    def _transition(
        self, current: PartitionManifest, target: PartitionManifest
    ) -> None:
        try:
            self._catalog.transition_manifest(current, target)
        except (CatalogPersistenceError, CatalogStorageError):
            if self._cancelled():
                raise PartitionCatalogFailure("catalog persistence cancelled") from None
            raise PartitionCatalogFailure("catalog persistence failed") from None

    def _cancelled(self) -> bool:
        try:
            return self._cancellation.is_cancelled()
        except Exception:
            return True

    def _cancelled_result(
        self, plan: PlannedInstrumentMonth
    ) -> PartitionLifecycleResult:
        if type(plan) is not PlannedInstrumentMonth:
            raise ValueError("a planned instrument month is required")
        return PartitionLifecycleResult(
            plan,
            PartitionLifecycleOutcome.CANCELLED,
            self._run_id,
            0,
            None,
            None,
            "CANCELLED",
        )


def _attempts(result: HistoricalFetchResult) -> int:
    return result.attempts


def _provider_category(code: HistoricalFetchCode) -> FailureCategory:
    if code is HistoricalFetchCode.CANCELLED:
        return FailureCategory.INTERRUPTED
    if code in {
        HistoricalFetchCode.PROVIDER_RETRYABLE,
        HistoricalFetchCode.ATTEMPT_BUDGET_EXHAUSTED,
        HistoricalFetchCode.RETRY_WAIT_BOUND_EXCEEDED,
    }:
        return FailureCategory.PROVIDER_RETRYABLE
    return FailureCategory.PROVIDER_NON_RETRYABLE


def _trusted_publication_category(error: Exception) -> FailureCategory:
    if type(error) is PartitionValidationError:
        return FailureCategory.VALIDATION_FAILED
    if type(error) is PartitionWriteError:
        return FailureCategory.WRITE_FAILED
    if type(error) in {
        PartitionPublicationError,
        PublicationConflictError,
        PublicationOutcomeUnknown,
    }:
        return FailureCategory.PUBLICATION_FAILED
    return FailureCategory.PUBLICATION_FAILED


def _bound_policy_version(policy_version: str, digest: str | None) -> str:
    if digest is None or _POLICY_SEPARATOR in policy_version:
        return policy_version
    return policy_version + _POLICY_SEPARATOR + digest


def _utc_now(clock: UtcClock) -> datetime:
    try:
        value = clock.now()
        if type(value) is not datetime or value.tzinfo is None:
            raise ValueError
        result = value.astimezone(UTC)
    except Exception:
        raise PartitionClockFailure("clock access failed") from None
    return result


def _validate_publication(
    published: object,
    plan: PlannedInstrumentMonth,
    canonical: Sequence[CanonicalCandle],
    active: PartitionManifest,
) -> None:
    if type(published) is not PublishedPartitionEvidence or not canonical:
        raise ValueError("publisher returned invalid evidence")
    if (
        published.plan != plan
        or published.plan != active.plan
        or published.candle_schema_version != CANDLE_SCHEMA_VERSION
        or published.row_count != len(canonical)
        or published.actual_from_ts != canonical[0].ts
        or published.actual_to_ts != canonical[-1].ts
        or published.source_version != active.source_version
        or published.source_version != _SOURCE_VERSION
        or any(candle.source_version != active.source_version for candle in canonical)
    ):
        raise ValueError("publisher returned invalid evidence")


def _validate_request_plan(
    plan: object, instrument: Instrument
) -> PlannedInstrumentMonth:
    if type(plan) is not PlannedInstrumentMonth:
        raise ValueError("a planned instrument month is required")
    try:
        plans = plan_upstox_equity_months(
            instrument, plan.from_date, plan.to_date, plan.interval
        )
    except Exception:
        raise ValueError("instrument identity or canonical month is invalid") from None
    if len(plans) != 1 or plans[0] != plan:
        raise ValueError("instrument identity or canonical month is invalid")
    return plan
