"""Public single-symbol download application service."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from .download_preparation import (
    DownloadPreparationReportV1,
    DownloadPreparationRequestV1,
    PreparationFailureCodeV1,
    PreparationOutcomeV1,
    PreparedDownloadV1,
)
from .historical import HistoricalFetchCode, RetryPolicy
from .manifest_lifecycle import FailureCategory, ManifestState, ValidationOutcome
from .monthly_request_planner import plan_upstox_equity_months
from .partition_reconciliation import RequestReason
from .public_contract import (
    DownloadPayloadV1,
    DownloadReportV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicDownloadRequestV1,
    PublicFailureCodeV1,
    PublicFailureV1,
    PublicMonthEvidenceV1,
)
from .range_ingestion import (
    IngestionCommand,
    IngestionReport,
    IngestionRunOutcome,
    PartitionOutcome,
    PartitionResult,
    RunFailureCode,
)
from .validation import EQUITY_MONTH_VALIDATION_POLICY_V1, ValidationReason

MAX_TOUCHED_MONTHS_V1 = 12
_POLICY_PREFIX = EQUITY_MONTH_VALIDATION_POLICY_V1 + "+sessions-sha256:"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_COMPLETED = frozenset(
    {
        PartitionOutcome.SKIPPED_VERIFIED,
        PartitionOutcome.RECOVERED_LOCALLY,
        PartitionOutcome.VERIFIED,
    }
)

_RUN_OUTCOMES = (
    IngestionRunOutcome.SUCCEEDED,
    IngestionRunOutcome.PARTIAL,
    IngestionRunOutcome.FAILED,
    IngestionRunOutcome.CANCELLED,
    IngestionRunOutcome.ALREADY_RUNNING,
    IngestionRunOutcome.REJECTED,
)
_RUN_CODES = (
    RunFailureCode.NONE,
    RunFailureCode.UNSUPPORTED_INTERVAL,
    RunFailureCode.ALREADY_RUNNING,
    RunFailureCode.PARTITION_NOT_CLOSED,
    RunFailureCode.SCHEDULE_UNSUPPORTED,
    RunFailureCode.STORAGE_UNSAFE,
    RunFailureCode.CATALOG_UNAVAILABLE,
    RunFailureCode.ATTEMPT_BUDGET_INSUFFICIENT,
    RunFailureCode.ATTEMPT_BUDGET_EXHAUSTED,
    RunFailureCode.MAPPING_MIGRATION_REQUIRED,
    RunFailureCode.RETRY_WAIT_BOUND_EXCEEDED,
    RunFailureCode.AUTHENTICATION_FAILED,
    RunFailureCode.AUTHORIZATION_FAILED,
    RunFailureCode.LOCAL_REPAIR_BLOCKED,
    RunFailureCode.CANCELLED,
    RunFailureCode.PARTITION_FAILURE,
)
_PARTITION_OUTCOMES = (
    PartitionOutcome.SKIPPED_VERIFIED,
    PartitionOutcome.RECOVERED_LOCALLY,
    PartitionOutcome.VERIFIED,
    PartitionOutcome.FAILED,
    PartitionOutcome.NOT_ATTEMPTED,
    PartitionOutcome.CANCELLED,
)
_HISTORICAL_CODES = (
    HistoricalFetchCode.AUTHENTICATION_FAILED,
    HistoricalFetchCode.AUTHORIZATION_FAILED,
    HistoricalFetchCode.PROVIDER_CLIENT,
    HistoricalFetchCode.PROVIDER_CONTRACT,
    HistoricalFetchCode.PROVIDER_RETRYABLE,
    HistoricalFetchCode.ATTEMPT_BUDGET_EXHAUSTED,
    HistoricalFetchCode.RETRY_WAIT_BOUND_EXCEEDED,
    HistoricalFetchCode.CANCELLED,
)
_FAILURE_CATEGORIES = (
    FailureCategory.INTERRUPTED,
    FailureCategory.EMPTY_RESPONSE,
    FailureCategory.PROVIDER_RETRYABLE,
    FailureCategory.PROVIDER_NON_RETRYABLE,
    FailureCategory.NORMALIZATION_FAILED,
    FailureCategory.VALIDATION_FAILED,
    FailureCategory.WRITE_FAILED,
    FailureCategory.PUBLICATION_FAILED,
    FailureCategory.FILE_MISSING,
    FailureCategory.PATH_INVALID_OR_MISMATCHED,
    FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED,
    FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
    FailureCategory.COVERAGE_NOT_PASSED,
    FailureCategory.QUALITY_NOT_PASSED,
)
_VALIDATION_REASONS = (
    ValidationReason.NONE,
    ValidationReason.SCHEDULE_DIGEST_MISSING,
    ValidationReason.SCHEDULE_DIGEST_MISMATCH,
    ValidationReason.SCHEDULE_RETAINED_BYTES_INVALID,
    ValidationReason.SCHEDULE_COVERAGE_INCOMPLETE,
    ValidationReason.COVERAGE_EXPECTED_BAR_MISSING,
    ValidationReason.COVERAGE_OFF_SESSION_BAR,
    ValidationReason.QUALITY_INVALID_OHLC,
    ValidationReason.QUALITY_INVALID_VOLUME,
)
_REQUEST_REASONS = (
    RequestReason.MISSING_EVIDENCE,
    RequestReason.DUPLICATE_EVIDENCE,
    RequestReason.MANIFEST_NOT_VERIFIED,
    RequestReason.FILE_MISSING,
    RequestReason.PATH_INVALID_OR_MISMATCHED,
    RequestReason.CHECKSUM_INVALID_OR_MISMATCHED,
    RequestReason.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
    RequestReason.RECORDED_RANGE_MISMATCHED,
    RequestReason.COVERAGE_NOT_PASSED,
    RequestReason.QUALITY_NOT_PASSED,
)


@dataclass(frozen=True, slots=True)
class SingleSymbolDownloadRequestV1:
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
            or _month_count(self.from_date, self.to_date) > MAX_TOUCHED_MONTHS_V1
            or not _valid_root(self.storage_root)
        ):
            raise ValueError("invalid single-symbol download request")


class DownloadPreparationPortV1(Protocol):
    def prepare(
        self, request: DownloadPreparationRequestV1
    ) -> DownloadPreparationReportV1: ...


class IngestionCoordinatorPortV1(Protocol):
    def run(self, command: IngestionCommand) -> IngestionReport: ...


@runtime_checkable
class DownloadClockV1(Protocol):
    def now(self) -> datetime: ...


class SingleSymbolDownloadServiceV1:
    """Prepare, ingest once, and convert to the stable public contract."""

    def __init__(
        self,
        preparation: DownloadPreparationPortV1,
        coordinator: IngestionCoordinatorPortV1,
        *,
        clock: DownloadClockV1 | object,
    ) -> None:
        self._preparation = preparation
        self._coordinator = coordinator
        self._clock = clock

    def download(self, request: object) -> DownloadReportV1:
        if type(request) is not SingleSymbolDownloadRequestV1:
            return _terminal_report(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.INVALID_INPUT,
                attempts=0,
            )
        invocation_time = _clock_now(self._clock)
        if invocation_time is None:
            return _terminal_report(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
                attempts=0,
            )
        try:
            prepared_report = self._preparation.prepare(
                DownloadPreparationRequestV1(
                    request.segment,
                    request.symbol,
                    request.from_date,
                    request.to_date,
                    request.storage_root,
                    invocation_time,
                )
            )
        except Exception:
            return _terminal_report(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
                attempts=0,
            )
        validated_preparation = _revalidate_preparation_report(prepared_report)
        if validated_preparation is None:
            return _terminal_report(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
                attempts=0,
            )
        prepared_report = validated_preparation
        if (
            prepared_report.outcome is not PreparationOutcomeV1.SUCCEEDED
            or prepared_report.prepared is None
        ):
            return _preparation_failure_report(prepared_report)
        prepared = prepared_report.prepared
        try:
            command = _ingestion_command(request, prepared)
            source_report = self._coordinator.run(command)
        except Exception:
            return _terminal_report(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
                attempts=prepared_report.snapshot_attempt_count,
            )
        try:
            return _convert_ingestion_report(request, prepared_report, source_report)
        except Exception:
            return _terminal_report(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
                attempts=prepared_report.snapshot_attempt_count,
            )


def _ingestion_command(
    request: SingleSymbolDownloadRequestV1, prepared: PreparedDownloadV1
) -> IngestionCommand:
    count = _month_count(request.from_date, request.to_date)
    return IngestionCommand(
        instrument=prepared.instrument,
        from_date=request.from_date,
        to_date=request.to_date,
        interval="1m",
        storage_root=request.storage_root,
        expected_sessions=prepared.schedule,
        validation_policy_version=_POLICY_PREFIX + prepared.schedule_digest_sha256,
        retry_policy=RetryPolicy(),
        max_total_provider_attempts=3 * count,
    )


def _convert_ingestion_report(
    request: SingleSymbolDownloadRequestV1,
    prepared_report: DownloadPreparationReportV1,
    source: object,
) -> DownloadReportV1:
    attempts = prepared_report.snapshot_attempt_count
    prepared = prepared_report.prepared
    if prepared is None:
        return _terminal_report(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            attempts=attempts,
        )
    validated_source = _revalidate_source_report(source, request, prepared)
    if validated_source is None:
        return _terminal_report(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            attempts=attempts,
        )
    source = validated_source
    attempts += source.provider_attempt_count
    detail = _run_detail(source.failure_code)
    if detail is None or not _status_combination_valid(source, detail[0]):
        return _terminal_report(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            attempts=attempts,
        )
    detail_class, failure_code = detail
    status = _public_status(source.outcome, detail_class)
    if status is None:
        return _terminal_report(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            attempts=attempts,
        )
    months = tuple(_month_evidence(item) for item in source.results)
    include_payload = status in {
        PublicCommandStatusV1.SUCCEEDED,
        PublicCommandStatusV1.PARTIAL,
    }
    payload = (
        DownloadPayloadV1(
            PublicDownloadRequestV1(
                request.segment, request.symbol, request.from_date, request.to_date
            ),
            source.started_at,
            source.completed_at,
            source.planned_count,
            source.skipped_count,
            source.locally_recovered_count,
            source.verified_count,
            source.failed_count,
            source.not_attempted_count,
            source.cancelled_count,
            prepared.snapshot_digest_sha256,
            prepared.snapshot_retrieved_at,
            prepared_report.snapshot_attempt_count,
            source.provider_attempt_count,
            months,
        )
        if include_payload
        else None
    )
    failure = None
    if failure_code is not None:
        affected = tuple(
            item.month for item in months if item.partition_outcome not in _COMPLETED
        )
        nested = next(
            (item for item in months if item.month in affected),
            None,
        )
        failure = PublicFailureV1(
            failure_code,
            source.failure_code,
            nested.historical_fetch_code if nested is not None else None,
            nested.failure_category if nested is not None else None,
            nested.validation_reason if nested is not None else None,
            affected,
        )
    return PublicCommandReportV1("v1", "download", status, failure, attempts, payload)


def _preparation_failure_report(source: object) -> DownloadReportV1:
    validated = _revalidate_preparation_report(source)
    if validated is None:
        return _terminal_report(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            attempts=0,
        )
    source = validated
    mapping = {
        PreparationFailureCodeV1.INVALID_INPUT: (
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INVALID_INPUT,
        ),
        PreparationFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT: (
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
        ),
        PreparationFailureCodeV1.SCHEDULE_UNAVAILABLE: (
            PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
            PublicFailureCodeV1.SCHEDULE_EVIDENCE_UNAVAILABLE,
        ),
        PreparationFailureCodeV1.STORAGE_UNAVAILABLE: (
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INGESTION_UNAVAILABLE,
        ),
        PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE: (
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE,
        ),
        PreparationFailureCodeV1.INSTRUMENT_NOT_FOUND: (
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INSTRUMENT_NOT_FOUND,
        ),
        PreparationFailureCodeV1.INSTRUMENT_AMBIGUOUS: (
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INSTRUMENT_AMBIGUOUS,
        ),
        PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_CORRUPT: (
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
        ),
    }
    selected = mapping.get(source.failure_code)
    if (
        source.outcome is PreparationOutcomeV1.SUCCEEDED
        or source.prepared is not None
        or selected is None
    ):
        return _terminal_report(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            attempts=source.snapshot_attempt_count,
        )
    status, code = selected
    return _terminal_report(status, code, attempts=source.snapshot_attempt_count)


def _revalidate_preparation_report(
    source: object,
) -> DownloadPreparationReportV1 | None:
    if type(source) is not DownloadPreparationReportV1:
        return None
    try:
        if (
            type(source.outcome) is not PreparationOutcomeV1
            or type(source.failure_code) is not PreparationFailureCodeV1
        ):
            return None
        prepared = source.prepared
        if prepared is not None:
            if type(prepared) is not PreparedDownloadV1:
                return None
            prepared = replace(prepared)
        return replace(source, prepared=prepared)
    except (AttributeError, TypeError, ValueError):
        return None


def _terminal_report(
    status: PublicCommandStatusV1,
    code: PublicFailureCodeV1,
    *,
    attempts: int,
) -> DownloadReportV1:
    return PublicCommandReportV1(
        "v1",
        "download",
        status,
        PublicFailureV1(code, None, None, None, None, ()),
        attempts,
        None,
    )


def _revalidate_source_report(
    source: object,
    request: SingleSymbolDownloadRequestV1,
    prepared: PreparedDownloadV1,
) -> IngestionReport | None:
    if (
        tuple(IngestionRunOutcome) != _RUN_OUTCOMES
        or tuple(RunFailureCode) != _RUN_CODES
        or tuple(PartitionOutcome) != _PARTITION_OUTCOMES
        or tuple(HistoricalFetchCode) != _HISTORICAL_CODES
        or tuple(FailureCategory) != _FAILURE_CATEGORIES
        or tuple(ValidationReason) != _VALIDATION_REASONS
        or tuple(RequestReason) != _REQUEST_REASONS
        or type(source) is not IngestionReport
    ):
        return None
    try:
        validated_results = tuple(_revalidate_result(item) for item in source.results)
        validated_source = replace(source, results=validated_results)
        if (
            not 0 <= validated_source.planned_count <= MAX_TOUCHED_MONTHS_V1
            or validated_source.provider_attempt_count
            > 3 * validated_source.planned_count
        ):
            return None
    except (AttributeError, TypeError, ValueError):
        return None
    try:
        expected_plans = plan_upstox_equity_months(
            prepared.instrument, request.from_date, request.to_date, "1m"
        )
    except Exception:
        return None
    if tuple(item.plan for item in validated_source.results) != expected_plans:
        return None
    seen: set[tuple[int, int]] = set()
    previous: tuple[int, int] | None = None
    for result in validated_source.results:
        plan = result.plan
        key = (plan.year, plan.month)
        if (
            type(result) is not PartitionResult
            or plan.segment != request.segment
            or plan.symbol != request.symbol
            or plan.interval != "1m"
            or plan.from_date < request.from_date
            or plan.to_date > request.to_date
            or key in seen
            or (previous is not None and key <= previous)
            or result.provider_attempts > 3
            or not _nested_result_valid(
                result, validated_source.failure_code, prepared.schedule_digest_sha256
            )
        ):
            return None
        seen.add(key)
        previous = key
    return validated_source if _exact_run_shape(validated_source) else None


def _revalidate_result(result: object) -> PartitionResult:
    if type(result) is not PartitionResult:
        raise ValueError
    manifest = result.final_manifest
    if manifest is not None:
        manifest = replace(manifest)
    return replace(result, final_manifest=manifest)


def _exact_run_shape(source: IngestionReport) -> bool:
    outcomes = tuple(item.outcome for item in source.results)
    completed = sum(item in _COMPLETED for item in outcomes)
    failed = sum(item is PartitionOutcome.FAILED for item in outcomes)
    not_attempted = sum(item is PartitionOutcome.NOT_ATTEMPTED for item in outcomes)
    cancelled = sum(item is PartitionOutcome.CANCELLED for item in outcomes)
    if source.outcome is IngestionRunOutcome.SUCCEEDED:
        return completed == len(outcomes)
    if source.outcome is IngestionRunOutcome.ALREADY_RUNNING:
        return not_attempted == len(outcomes)
    if source.outcome is IngestionRunOutcome.REJECTED:
        return completed == cancelled == 0
    if source.outcome is IngestionRunOutcome.FAILED:
        return completed == cancelled == 0 and failed + not_attempted == len(outcomes)
    if source.outcome is IngestionRunOutcome.CANCELLED:
        return completed == 0 and cancelled > 0
    return source.outcome is IngestionRunOutcome.PARTIAL and completed > 0


def _nested_result_valid(
    result: PartitionResult, run_code: RunFailureCode, schedule_digest: str
) -> bool:
    if not _manifest_matches_result(result, schedule_digest):
        return False
    if not _outcome_manifest_shape_valid(result):
        return False
    return _error_code_matches_run(result.error_code, run_code)


def _manifest_matches_result(result: PartitionResult, schedule_digest: str) -> bool:
    manifest = result.final_manifest
    if manifest is None:
        return True
    try:
        replace(manifest)
    except (TypeError, ValueError):
        return False
    return (
        manifest.plan == result.plan
        and manifest.validation_policy_version == _POLICY_PREFIX + schedule_digest
        and manifest.failure_category == result.failure_category
    )


def _outcome_manifest_shape_valid(result: PartitionResult) -> bool:
    manifest = result.final_manifest
    if result.outcome in _COMPLETED and (
        manifest is None
        or manifest.state is not ManifestState.VERIFIED
        or manifest.validation_outcome is not ValidationOutcome.PASSED
    ):
        return False
    if result.outcome is PartitionOutcome.FAILED and (
        (manifest is not None and manifest.state is not ManifestState.FAILED)
        or result.failure_category is FailureCategory.INTERRUPTED
    ):
        return False
    if result.outcome is PartitionOutcome.CANCELLED:
        if manifest is None:
            if result.provider_attempts != 0 or result.failure_category is not None:
                return False
        elif (
            manifest.state is not ManifestState.FAILED
            or result.failure_category is not FailureCategory.INTERRUPTED
        ):
            return False
    return True


def _error_code_matches_run(error_code: str | None, run_code: RunFailureCode) -> bool:
    historical = _historical_code(error_code)
    if historical is None:
        return error_code is None or _known_nonhistorical_code(error_code, run_code)
    if historical is HistoricalFetchCode.CANCELLED:
        return run_code is RunFailureCode.CANCELLED
    if historical is HistoricalFetchCode.AUTHENTICATION_FAILED:
        return run_code is RunFailureCode.AUTHENTICATION_FAILED
    if historical is HistoricalFetchCode.AUTHORIZATION_FAILED:
        return run_code is RunFailureCode.AUTHORIZATION_FAILED
    return run_code in {
        RunFailureCode.PARTITION_FAILURE,
        RunFailureCode.ATTEMPT_BUDGET_EXHAUSTED,
        RunFailureCode.RETRY_WAIT_BOUND_EXCEEDED,
    }


def _known_nonhistorical_code(value: str, run_code: RunFailureCode) -> bool:
    try:
        parsed = RunFailureCode(value)
    except ValueError:
        return False
    return parsed is run_code


def _status_combination_valid(source: IngestionReport, detail_class: str) -> bool:
    if source.outcome is IngestionRunOutcome.SUCCEEDED:
        return source.failure_code is RunFailureCode.NONE and detail_class == "SUCCESS"
    if source.outcome is IngestionRunOutcome.PARTIAL:
        return (
            source.failure_code is not RunFailureCode.NONE and detail_class != "SUCCESS"
        )
    if source.outcome is IngestionRunOutcome.CANCELLED:
        return (
            source.failure_code is RunFailureCode.CANCELLED
            and detail_class == "CANCELLED"
        )
    return source.failure_code is not RunFailureCode.NONE and detail_class not in {
        "SUCCESS",
        "CANCELLED",
    }


def _run_detail(
    code: RunFailureCode,
) -> tuple[str, PublicFailureCodeV1 | None] | None:
    if code is RunFailureCode.NONE:
        return "SUCCESS", None
    if code in {
        RunFailureCode.UNSUPPORTED_INTERVAL,
        RunFailureCode.PARTITION_NOT_CLOSED,
        RunFailureCode.ATTEMPT_BUDGET_INSUFFICIENT,
    }:
        return "REJECTED", PublicFailureCodeV1.INGESTION_REJECTED
    if code is RunFailureCode.SCHEDULE_UNSUPPORTED:
        return "INSUFFICIENT", PublicFailureCodeV1.SCHEDULE_EVIDENCE_UNAVAILABLE
    if code in {
        RunFailureCode.ALREADY_RUNNING,
        RunFailureCode.STORAGE_UNSAFE,
        RunFailureCode.CATALOG_UNAVAILABLE,
        RunFailureCode.AUTHORIZATION_FAILED,
    }:
        return "UNAVAILABLE", PublicFailureCodeV1.INGESTION_UNAVAILABLE
    if code is RunFailureCode.AUTHENTICATION_FAILED:
        return "UNAVAILABLE", PublicFailureCodeV1.CREDENTIALS_UNAVAILABLE
    if code in {
        RunFailureCode.ATTEMPT_BUDGET_EXHAUSTED,
        RunFailureCode.MAPPING_MIGRATION_REQUIRED,
        RunFailureCode.RETRY_WAIT_BOUND_EXCEEDED,
        RunFailureCode.LOCAL_REPAIR_BLOCKED,
        RunFailureCode.PARTITION_FAILURE,
    }:
        return "FAILED", PublicFailureCodeV1.INGESTION_FAILED
    if code is RunFailureCode.CANCELLED:
        return "CANCELLED", PublicFailureCodeV1.INGESTION_CANCELLED
    return None


def _public_status(
    outcome: IngestionRunOutcome, detail_class: str
) -> PublicCommandStatusV1 | None:
    if outcome is IngestionRunOutcome.SUCCEEDED:
        return PublicCommandStatusV1.SUCCEEDED
    if outcome is IngestionRunOutcome.PARTIAL:
        return PublicCommandStatusV1.PARTIAL
    if outcome is IngestionRunOutcome.CANCELLED:
        return PublicCommandStatusV1.CANCELLED
    return {
        "REJECTED": PublicCommandStatusV1.REJECTED,
        "INSUFFICIENT": PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
        "UNAVAILABLE": PublicCommandStatusV1.UNAVAILABLE,
        "FAILED": PublicCommandStatusV1.FAILED,
    }.get(detail_class)


def _month_evidence(result: PartitionResult) -> PublicMonthEvidenceV1:
    if result.outcome is PartitionOutcome.NOT_ATTEMPTED:
        return PublicMonthEvidenceV1(
            _month(result),
            result.outcome,
            result.reconciliation_reasons,
            result.provider_attempts,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
    manifest = result.final_manifest
    policy = manifest.validation_policy_version if manifest is not None else None
    return PublicMonthEvidenceV1(
        _month(result),
        result.outcome,
        result.reconciliation_reasons,
        result.provider_attempts,
        manifest.actual_from_ts if manifest is not None else None,
        manifest.actual_to_ts if manifest is not None else None,
        manifest.row_count if manifest is not None else None,
        manifest.checksum_sha256 if manifest is not None else None,
        manifest.candle_schema_version if manifest is not None else None,
        policy,
        _policy_digest(policy),
        result.failure_category,
        _validation_reason(result),
        _historical_code(result.error_code),
    )


def _validation_reason(result: PartitionResult) -> ValidationReason | None:
    manifest = result.final_manifest
    if (
        manifest is not None
        and manifest.validation_outcome is ValidationOutcome.PASSED
        and result.failure_category is None
    ):
        return ValidationReason.NONE
    return None


def _historical_code(value: str | None) -> HistoricalFetchCode | None:
    if value is None:
        return None
    try:
        return HistoricalFetchCode(value)
    except ValueError:
        return None


def _policy_digest(value: str | None) -> str | None:
    if value is None or not value.startswith(_POLICY_PREFIX):
        return None
    digest = value.removeprefix(_POLICY_PREFIX)
    return digest if _DIGEST.fullmatch(digest) is not None else None


def _month(result: PartitionResult) -> str:
    return f"{result.plan.year:04d}-{result.plan.month:02d}"


def _clock_now(clock: object) -> datetime | None:
    try:
        if isinstance(clock, DownloadClockV1):
            candidate: object = clock.now()
        elif callable(clock):
            candidate = cast(Callable[[], object], clock)()
        else:
            return None
    except Exception:
        return None
    if type(candidate) is not datetime or candidate.tzinfo is None:
        return None
    return candidate.astimezone(UTC)


def _valid_root(value: object) -> bool:
    return (
        isinstance(value, Path)
        and value.is_absolute()
        and ".." not in value.parts
        and not any(character in part for part in value.parts for character in "~*?[]")
    )


def _month_count(from_date: date, to_date: date) -> int:
    return (to_date.year - from_date.year) * 12 + to_date.month - from_date.month + 1
