"""Stable, bounded public report models and JSON rendering."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta, timezone
from enum import StrEnum
from typing import Generic, Literal, TypeVar, cast

from .historical import HistoricalFetchCode
from .manifest_lifecycle import FailureCategory
from .partition_reconciliation import RequestReason
from .range_ingestion import PartitionOutcome, RunFailureCode
from .validation import (
    SUPPORTED_EQUITY_MONTH_VALIDATION_POLICIES,
    ValidationReason,
    supported_equity_month_policy_digest,
)

MAX_PUBLIC_JSON_BYTES_V1 = 8_388_608
MAX_DOWNLOAD_PROVIDER_ATTEMPTS_V1 = 37
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MONTH = re.compile(r"[0-9]{4}-[0-9]{2}\Z")


class PublicCommandStatusV1(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class PublicFailureCodeV1(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_PREVIEW_INSTRUMENT = "UNSUPPORTED_PREVIEW_INSTRUMENT"
    UNSUPPORTED_TIMEFRAME = "UNSUPPORTED_TIMEFRAME"
    QUERY_BOUNDS_EXCEEDED = "QUERY_BOUNDS_EXCEEDED"
    SCHEDULE_EVIDENCE_UNAVAILABLE = "SCHEDULE_EVIDENCE_UNAVAILABLE"
    INSTRUMENT_SNAPSHOT_UNAVAILABLE = "INSTRUMENT_SNAPSHOT_UNAVAILABLE"
    INSTRUMENT_NOT_FOUND = "INSTRUMENT_NOT_FOUND"
    INSTRUMENT_AMBIGUOUS = "INSTRUMENT_AMBIGUOUS"
    CREDENTIALS_UNAVAILABLE = "CREDENTIALS_UNAVAILABLE"
    QUERY_CATALOG_UNAVAILABLE = "QUERY_CATALOG_UNAVAILABLE"
    QUERY_RESOURCE_LIMIT_EXCEEDED = "QUERY_RESOURCE_LIMIT_EXCEEDED"
    QUERY_TIMEOUT = "QUERY_TIMEOUT"
    OUTPUT_LIMIT_EXCEEDED = "OUTPUT_LIMIT_EXCEEDED"
    COVERAGE_INSUFFICIENT = "COVERAGE_INSUFFICIENT"
    INGESTION_REJECTED = "INGESTION_REJECTED"
    INGESTION_UNAVAILABLE = "INGESTION_UNAVAILABLE"
    INGESTION_FAILED = "INGESTION_FAILED"
    INGESTION_CANCELLED = "INGESTION_CANCELLED"
    UNCLASSIFIED_FAILURE = "UNCLASSIFIED_FAILURE"


class CoverageStateV1(StrEnum):
    VERIFIED = "VERIFIED"
    MISSING = "MISSING"
    INSUFFICIENT = "INSUFFICIENT"
    STALE = "STALE"
    CORRUPT = "CORRUPT"
    SCHEDULE_UNPROVEN = "SCHEDULE_UNPROVEN"


class CandleFieldV1(StrEnum):
    TS = "ts"
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"


@dataclass(frozen=True, slots=True)
class PublicFailureV1:
    code: PublicFailureCodeV1
    run_failure_code: RunFailureCode | None
    historical_fetch_code: HistoricalFetchCode | None
    failure_category: FailureCategory | None
    validation_reason: ValidationReason | None
    months: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.code) is not PublicFailureCodeV1
            or type(self.run_failure_code) not in (RunFailureCode, type(None))
            or type(self.historical_fetch_code) not in (HistoricalFetchCode, type(None))
            or type(self.failure_category) not in (FailureCategory, type(None))
            or type(self.validation_reason) not in (ValidationReason, type(None))
            or type(self.months) is not tuple
            or any(
                type(value) is not str or _MONTH.fullmatch(value) is None
                for value in self.months
            )
            or len(set(self.months)) != len(self.months)
        ):
            raise ValueError("invalid public failure")


@dataclass(frozen=True, slots=True)
class PublicMonthEvidenceV1:
    month: str
    partition_outcome: PartitionOutcome
    reconciliation_reasons: tuple[RequestReason, ...]
    provider_attempt_count: int
    actual_from_ts: datetime | None
    actual_to_ts: datetime | None
    row_count: int | None
    checksum_sha256: str | None
    candle_schema_version: int | None
    validation_policy_version: str | None
    schedule_digest_sha256: str | None
    failure_category: FailureCategory | None
    validation_reason: ValidationReason | None
    historical_fetch_code: HistoricalFetchCode | None

    def __post_init__(self) -> None:
        if (
            type(self.month) is not str
            or _MONTH.fullmatch(self.month) is None
            or type(self.partition_outcome) is not PartitionOutcome
            or type(self.reconciliation_reasons) is not tuple
            or any(
                type(item) is not RequestReason for item in self.reconciliation_reasons
            )
            or type(self.provider_attempt_count) is not int
            or self.provider_attempt_count < 0
            or self.provider_attempt_count > 3
            or not _optional_utc(self.actual_from_ts)
            or not _optional_utc(self.actual_to_ts)
            or type(self.row_count) not in (int, type(None))
            or (self.row_count is not None and self.row_count < 0)
            or not _optional_digest(self.checksum_sha256)
            or type(self.candle_schema_version) not in (int, type(None))
            or type(self.validation_policy_version) not in (str, type(None))
            or (
                self.validation_policy_version is not None
                and not self.validation_policy_version
            )
            or not _optional_digest(self.schedule_digest_sha256)
            or type(self.failure_category) not in (FailureCategory, type(None))
            or type(self.validation_reason) not in (ValidationReason, type(None))
            or type(self.historical_fetch_code) not in (HistoricalFetchCode, type(None))
        ):
            raise ValueError("invalid public month evidence")
        if (self.actual_from_ts is None) != (self.actual_to_ts is None):
            raise ValueError("invalid public month evidence")
        if self.partition_outcome is PartitionOutcome.NOT_ATTEMPTED and any(
            value is not None
            for value in (
                self.actual_from_ts,
                self.actual_to_ts,
                self.row_count,
                self.checksum_sha256,
                self.candle_schema_version,
                self.validation_policy_version,
                self.schedule_digest_sha256,
                self.failure_category,
                self.validation_reason,
                self.historical_fetch_code,
            )
        ):
            raise ValueError("invalid public month evidence")


@dataclass(frozen=True, slots=True)
class PublicDownloadRequestV1:
    segment: str
    symbol: str
    from_date: date
    to_date: date

    def __post_init__(self) -> None:
        if (
            type(self.segment) is not str
            or type(self.symbol) is not str
            or type(self.from_date) is not date
            or type(self.to_date) is not date
            or self.from_date > self.to_date
        ):
            raise ValueError("invalid public download request")


@dataclass(frozen=True, slots=True)
class DownloadPayloadV1:
    request: PublicDownloadRequestV1
    started_at: datetime
    completed_at: datetime
    planned_count: int
    skipped_count: int
    locally_recovered_count: int
    verified_count: int
    failed_count: int
    not_attempted_count: int
    cancelled_count: int
    instrument_snapshot_digest_sha256: str
    instrument_snapshot_retrieved_at: datetime
    instrument_snapshot_attempt_count: int
    historical_attempt_count: int
    months: tuple[PublicMonthEvidenceV1, ...]

    def __post_init__(self) -> None:
        try:
            validated_request = replace(self.request)
            validated_months = tuple(replace(item) for item in self.months)
        except (TypeError, ValueError):
            raise ValueError("invalid download payload") from None
        counts = (
            self.planned_count,
            self.skipped_count,
            self.locally_recovered_count,
            self.verified_count,
            self.failed_count,
            self.not_attempted_count,
            self.cancelled_count,
            self.instrument_snapshot_attempt_count,
            self.historical_attempt_count,
        )
        if (
            type(self.request) is not PublicDownloadRequestV1
            or validated_request != self.request
            or not _utc(self.started_at)
            or not _utc(self.completed_at)
            or self.completed_at < self.started_at
            or any(type(value) is not int or value < 0 for value in counts)
            or self.instrument_snapshot_attempt_count > 1
            or self.historical_attempt_count > 3 * self.planned_count
            or type(self.instrument_snapshot_digest_sha256) is not str
            or _DIGEST.fullmatch(self.instrument_snapshot_digest_sha256) is None
            or not _utc(self.instrument_snapshot_retrieved_at)
            or type(self.months) is not tuple
            or any(type(item) is not PublicMonthEvidenceV1 for item in self.months)
            or validated_months != self.months
            or any(item.provider_attempt_count > 3 for item in self.months)
            or self.planned_count != len(self.months)
            or self.historical_attempt_count
            != sum(item.provider_attempt_count for item in self.months)
            or self.skipped_count
            != sum(
                item.partition_outcome is PartitionOutcome.SKIPPED_VERIFIED
                for item in self.months
            )
            or self.locally_recovered_count
            != sum(
                item.partition_outcome is PartitionOutcome.RECOVERED_LOCALLY
                for item in self.months
            )
            or self.verified_count
            != sum(
                item.partition_outcome is PartitionOutcome.VERIFIED
                for item in self.months
            )
            or self.failed_count
            != sum(
                item.partition_outcome is PartitionOutcome.FAILED
                for item in self.months
            )
            or self.not_attempted_count
            != sum(
                item.partition_outcome is PartitionOutcome.NOT_ATTEMPTED
                for item in self.months
            )
            or self.cancelled_count
            != sum(
                item.partition_outcome is PartitionOutcome.CANCELLED
                for item in self.months
            )
        ):
            raise ValueError("invalid download payload")


@dataclass(frozen=True, slots=True)
class PublicCoverageRequestV1:
    segment: str
    symbol: str
    from_date: date
    to_date: date

    def __post_init__(self) -> None:
        if (
            type(self.segment) is not str
            or type(self.symbol) is not str
            or type(self.from_date) is not date
            or type(self.to_date) is not date
            or self.from_date > self.to_date
            or self.from_date < date(2022, 1, 1)
            or _coverage_month_count(self.from_date, self.to_date) > 12
        ):
            raise ValueError("invalid public coverage request")


@dataclass(frozen=True, slots=True)
class PublicCoverageMonthV1:
    month: str
    coverage_state: CoverageStateV1
    actual_from_ts: datetime | None
    actual_to_ts: datetime | None
    row_count: int | None
    checksum_sha256: str | None
    candle_schema_version: int | None
    validation_policy_version: str | None
    schedule_digest_sha256: str | None
    failure_category: FailureCategory | None
    validation_reason: ValidationReason | None

    def __post_init__(self) -> None:
        policy_digest = supported_equity_month_policy_digest(
            self.validation_policy_version
        )
        policy_supported = self.validation_policy_version is None or (
            self.validation_policy_version in SUPPORTED_EQUITY_MONTH_VALIDATION_POLICIES
            or policy_digest is not None
        )
        facts = (
            self.actual_from_ts,
            self.actual_to_ts,
            self.row_count,
            self.checksum_sha256,
            self.candle_schema_version,
            self.validation_policy_version,
            self.schedule_digest_sha256,
        )
        if (
            type(self.month) is not str
            or _MONTH.fullmatch(self.month) is None
            or type(self.coverage_state) is not CoverageStateV1
            or not _optional_utc(self.actual_from_ts)
            or not _optional_utc(self.actual_to_ts)
            or (self.actual_from_ts is None) != (self.actual_to_ts is None)
            or type(self.row_count) not in (int, type(None))
            or (self.row_count is not None and self.row_count < 0)
            or not _optional_digest(self.checksum_sha256)
            or type(self.candle_schema_version) not in (int, type(None))
            or type(self.validation_policy_version) not in (str, type(None))
            or not policy_supported
            or not _optional_digest(self.schedule_digest_sha256)
            or self.schedule_digest_sha256 != policy_digest
            or type(self.failure_category) not in (FailureCategory, type(None))
            or type(self.validation_reason) not in (ValidationReason, type(None))
        ):
            raise ValueError("invalid public coverage month")
        if self.coverage_state is CoverageStateV1.VERIFIED and (
            any(value is None for value in facts)
            or self.failure_category is not None
            or self.validation_reason is not ValidationReason.NONE
        ):
            raise ValueError("invalid public coverage month")
        if self.coverage_state is CoverageStateV1.MISSING and (
            any(value is not None for value in facts)
            or self.failure_category is not None
            or self.validation_reason is not None
        ):
            raise ValueError("invalid public coverage month")


@dataclass(frozen=True, slots=True)
class CoveragePayloadV1:
    request: PublicCoverageRequestV1
    overall_state: CoverageStateV1
    planned_count: int
    verified_count: int
    missing_count: int
    insufficient_count: int
    stale_count: int
    corrupt_count: int
    schedule_unproven_count: int
    months: tuple[PublicCoverageMonthV1, ...]

    def __post_init__(self) -> None:
        try:
            request = replace(self.request)
            months = tuple(replace(item) for item in self.months)
        except (TypeError, ValueError):
            raise ValueError("invalid coverage payload") from None
        counts = {
            CoverageStateV1.VERIFIED: self.verified_count,
            CoverageStateV1.MISSING: self.missing_count,
            CoverageStateV1.INSUFFICIENT: self.insufficient_count,
            CoverageStateV1.STALE: self.stale_count,
            CoverageStateV1.CORRUPT: self.corrupt_count,
            CoverageStateV1.SCHEDULE_UNPROVEN: self.schedule_unproven_count,
        }
        if (
            type(self.request) is not PublicCoverageRequestV1
            or request != self.request
            or type(self.overall_state) is not CoverageStateV1
            or type(self.planned_count) is not int
            or self.planned_count < 0
            or self.planned_count == 0
            or self.planned_count > 12
            or any(type(value) is not int or value < 0 for value in counts.values())
            or type(self.months) is not tuple
            or any(type(item) is not PublicCoverageMonthV1 for item in self.months)
            or months != self.months
            or self.planned_count != len(self.months)
            or tuple(item.month for item in self.months)
            != _coverage_month_labels(self.request)
            or any(
                count != sum(item.coverage_state is state for item in self.months)
                for state, count in counts.items()
            )
            or sum(counts.values()) != self.planned_count
            or (
                self.overall_state is CoverageStateV1.VERIFIED
                and self.verified_count != self.planned_count
            )
            or (
                self.overall_state is not CoverageStateV1.VERIFIED
                and counts[self.overall_state] == 0
            )
            or self.overall_state
            is not next(
                (
                    item.coverage_state
                    for item in self.months
                    if item.coverage_state is not CoverageStateV1.VERIFIED
                ),
                CoverageStateV1.VERIFIED,
            )
        ):
            raise ValueError("invalid coverage payload")


@dataclass(frozen=True, slots=True)
class PublicQueryRequestV1:
    segment: str
    symbol: str
    from_date: date
    to_date: date
    timeframe: Literal["1m"]
    fields: tuple[CandleFieldV1, ...]
    max_rows: int

    def __post_init__(self) -> None:
        declaration_order = {value: index for index, value in enumerate(CandleFieldV1)}
        if (
            type(self.segment) is not str
            or type(self.symbol) is not str
            or type(self.from_date) is not date
            or type(self.to_date) is not date
            or self.from_date > self.to_date
            or self.from_date < date(2022, 1, 1)
            or _coverage_month_count(self.from_date, self.to_date) > 12
            or type(self.timeframe) is not str
            or self.timeframe != "1m"
            or type(self.fields) is not tuple
            or not 1 <= len(self.fields) <= len(CandleFieldV1)
            or any(type(value) is not CandleFieldV1 for value in self.fields)
            or len(set(self.fields)) != len(self.fields)
            or tuple(sorted(self.fields, key=declaration_order.__getitem__))
            != self.fields
            or type(self.max_rows) is not int
            or not 1 <= self.max_rows <= 10_000
        ):
            raise ValueError("invalid public query request")


@dataclass(frozen=True, slots=True)
class PublicQueryRowV1:
    ts: datetime
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None

    def __post_init__(self) -> None:
        prices = (self.open, self.high, self.low, self.close)
        if (
            not _utc(self.ts)
            or self.ts.second != 0
            or self.ts.microsecond != 0
            or any(
                value is not None
                and (type(value) is not float or not math.isfinite(value) or value < 0)
                for value in prices
            )
            or type(self.volume) not in (int, type(None))
            or (self.volume is not None and self.volume < 0)
        ):
            raise ValueError("invalid public query row")


@dataclass(frozen=True, slots=True)
class QueryPayloadV1:
    request: PublicQueryRequestV1
    row_count: int
    months: tuple[PublicCoverageMonthV1, ...]
    rows: tuple[PublicQueryRowV1, ...]

    def __post_init__(self) -> None:
        try:
            request = replace(self.request)
            months = tuple(replace(value) for value in self.months)
            rows = tuple(replace(value) for value in self.rows)
        except (TypeError, ValueError):
            raise ValueError("invalid query payload") from None
        selected = set(request.fields)
        start = datetime(
            request.from_date.year,
            request.from_date.month,
            request.from_date.day,
            tzinfo=_IST,
        ).astimezone(UTC)
        after = request.to_date + timedelta(days=1)
        end = datetime(after.year, after.month, after.day, tzinfo=_IST).astimezone(UTC)
        if (
            type(self.request) is not PublicQueryRequestV1
            or request != self.request
            or type(self.row_count) is not int
            or self.row_count != len(rows)
            or self.row_count > request.max_rows
            or type(self.months) is not tuple
            or any(type(value) is not PublicCoverageMonthV1 for value in self.months)
            or months != self.months
            or tuple(value.month for value in months)
            != _month_labels_from_dates(request.from_date, request.to_date)
            or type(self.rows) is not tuple
            or any(type(value) is not PublicQueryRowV1 for value in self.rows)
            or rows != self.rows
            or any(not start <= value.ts < end for value in rows)
            or any(
                left.ts >= right.ts for left, right in zip(rows, rows[1:], strict=False)
            )
            or any(
                (value.open is not None) != (CandleFieldV1.OPEN in selected)
                or (value.high is not None) != (CandleFieldV1.HIGH in selected)
                or (value.low is not None) != (CandleFieldV1.LOW in selected)
                or (value.close is not None) != (CandleFieldV1.CLOSE in selected)
                or (value.volume is not None) != (CandleFieldV1.VOLUME in selected)
                for value in rows
            )
            or (
                any(
                    value.coverage_state is not CoverageStateV1.VERIFIED
                    for value in months
                )
                and bool(rows)
            )
        ):
            raise ValueError("invalid query payload")


PayloadT_co = TypeVar("PayloadT_co", covariant=True)


@dataclass(frozen=True, slots=True)
class PublicCommandReportV1(Generic[PayloadT_co]):
    contract_version: Literal["v1"]
    command: Literal["download", "coverage", "query"]
    status: PublicCommandStatusV1
    failure: PublicFailureV1 | None
    provider_attempt_count: int
    payload: PayloadT_co | None

    def __post_init__(self) -> None:
        if (
            self.contract_version != "v1"
            or self.command not in {"download", "coverage", "query"}
            or type(self.status) is not PublicCommandStatusV1
            or type(self.failure) not in (PublicFailureV1, type(None))
            or type(self.provider_attempt_count) is not int
            or self.provider_attempt_count < 0
            or (self.status is PublicCommandStatusV1.SUCCEEDED)
            != (self.failure is None)
            or not _valid_payload_presence(self.command, self.status, self.payload)
        ):
            raise ValueError("invalid public command report")
        if self.command == "download" and (
            self.provider_attempt_count > MAX_DOWNLOAD_PROVIDER_ATTEMPTS_V1
            or type(self.payload) not in (DownloadPayloadV1, type(None))
            or (
                type(self.payload) is DownloadPayloadV1
                and self.provider_attempt_count
                != self.payload.instrument_snapshot_attempt_count
                + self.payload.historical_attempt_count
            )
        ):
            raise ValueError("invalid public command report")
        if self.command == "coverage" and (
            self.provider_attempt_count != 0
            or type(self.payload) not in (CoveragePayloadV1, type(None))
            or not _valid_coverage_report(self.status, self.failure, self.payload)
        ):
            raise ValueError("invalid public command report")
        if self.command == "query" and (
            self.provider_attempt_count != 0
            or type(self.payload) not in (QueryPayloadV1, type(None))
            or not _valid_query_report(self.status, self.failure, self.payload)
        ):
            raise ValueError("invalid public command report")


DownloadReportV1 = PublicCommandReportV1[DownloadPayloadV1]
CoverageReportV1 = PublicCommandReportV1[CoveragePayloadV1]
QueryReportV1 = PublicCommandReportV1[QueryPayloadV1]


def _valid_coverage_report(
    status: PublicCommandStatusV1,
    failure: PublicFailureV1 | None,
    payload: object,
) -> bool:
    if payload is None:
        return status not in {
            PublicCommandStatusV1.SUCCEEDED,
            PublicCommandStatusV1.PARTIAL,
            PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
        }
    if type(payload) is not CoveragePayloadV1:
        return False
    if payload.overall_state is CoverageStateV1.VERIFIED:
        return status is PublicCommandStatusV1.SUCCEEDED and failure is None
    affected = tuple(
        item.month
        for item in payload.months
        if item.coverage_state is not CoverageStateV1.VERIFIED
    )
    return (
        status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
        and failure is not None
        and failure.code is PublicFailureCodeV1.COVERAGE_INSUFFICIENT
        and failure.run_failure_code is None
        and failure.historical_fetch_code is None
        and failure.failure_category is None
        and failure.validation_reason is None
        and failure.months == affected
    )


def _valid_query_report(
    status: PublicCommandStatusV1,
    failure: PublicFailureV1 | None,
    payload: object,
) -> bool:
    if payload is None:
        allowed = {
            PublicCommandStatusV1.REJECTED: {
                PublicFailureCodeV1.INVALID_INPUT,
                PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
                PublicFailureCodeV1.UNSUPPORTED_TIMEFRAME,
                PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED,
                PublicFailureCodeV1.INSTRUMENT_NOT_FOUND,
                PublicFailureCodeV1.INSTRUMENT_AMBIGUOUS,
            },
            PublicCommandStatusV1.UNAVAILABLE: {
                PublicFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            },
            PublicCommandStatusV1.FAILED: {
                PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED,
                PublicFailureCodeV1.QUERY_TIMEOUT,
                PublicFailureCodeV1.OUTPUT_LIMIT_EXCEEDED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            },
        }
        return (
            failure is not None
            and failure.code in allowed.get(status, set())
            and failure.run_failure_code is None
            and failure.historical_fetch_code is None
            and failure.failure_category is None
            and failure.validation_reason is None
            and failure.months == ()
        )
    if type(payload) is not QueryPayloadV1:
        return False
    affected = tuple(
        value.month
        for value in payload.months
        if value.coverage_state is not CoverageStateV1.VERIFIED
    )
    if not affected:
        return status is PublicCommandStatusV1.SUCCEEDED and failure is None
    return (
        status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
        and failure is not None
        and failure.code is PublicFailureCodeV1.COVERAGE_INSUFFICIENT
        and failure.run_failure_code is None
        and failure.historical_fetch_code is None
        and failure.failure_category is None
        and failure.validation_reason is None
        and failure.months == affected
        and payload.row_count == 0
    )


def _valid_payload_presence(
    command: str, status: PublicCommandStatusV1, payload: object
) -> bool:
    required = status in {
        PublicCommandStatusV1.SUCCEEDED,
        PublicCommandStatusV1.PARTIAL,
    } or (
        command in {"coverage", "query"}
        and status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
    )
    return required == (payload is not None)


def public_exit_code(status: PublicCommandStatusV1) -> int:
    if type(status) is not PublicCommandStatusV1:
        return 5
    return {
        PublicCommandStatusV1.SUCCEEDED: 0,
        PublicCommandStatusV1.REJECTED: 2,
        PublicCommandStatusV1.PARTIAL: 3,
        PublicCommandStatusV1.INSUFFICIENT_EVIDENCE: 3,
        PublicCommandStatusV1.UNAVAILABLE: 4,
        PublicCommandStatusV1.FAILED: 5,
        PublicCommandStatusV1.CANCELLED: 130,
    }[status]


def render_download_report_json(report: DownloadReportV1) -> bytes:
    """Render only the allowlisted v1 download fields."""
    try:
        value = _download_report_value(report)
        encoded = _json_bytes(value)
    except Exception:
        encoded = _json_bytes(
            _terminal_failure_value(0, PublicFailureCodeV1.UNCLASSIFIED_FAILURE)
        )
    if len(encoded) <= MAX_PUBLIC_JSON_BYTES_V1:
        return encoded
    attempts = _bounded_download_attempts(report)
    overflow = _json_bytes(
        _terminal_failure_value(attempts, PublicFailureCodeV1.OUTPUT_LIMIT_EXCEEDED)
    )
    if len(overflow) > MAX_PUBLIC_JSON_BYTES_V1:
        raise ValueError("public JSON ceiling cannot contain terminal report")
    return overflow


def render_coverage_report_json(report: CoverageReportV1) -> bytes:
    """Render only the allowlisted v1 coverage fields."""
    try:
        encoded = _json_bytes(_coverage_report_value(report))
    except Exception:
        encoded = _json_bytes(
            _coverage_terminal_failure_value(PublicFailureCodeV1.UNCLASSIFIED_FAILURE)
        )
    if len(encoded) <= MAX_PUBLIC_JSON_BYTES_V1:
        return encoded
    overflow = _json_bytes(
        _coverage_terminal_failure_value(PublicFailureCodeV1.OUTPUT_LIMIT_EXCEEDED)
    )
    if len(overflow) > MAX_PUBLIC_JSON_BYTES_V1:
        raise ValueError("public JSON ceiling cannot contain terminal report")
    return overflow


def render_query_report_json(report: QueryReportV1) -> bytes:
    """Render only the requested, allowlisted v1 candle fields."""
    try:
        encoded = _json_bytes(_query_report_value(report))
    except Exception:
        encoded = _json_bytes(
            _query_terminal_failure_value(PublicFailureCodeV1.UNCLASSIFIED_FAILURE)
        )
    if len(encoded) <= MAX_PUBLIC_JSON_BYTES_V1:
        return encoded
    overflow = _json_bytes(
        _query_terminal_failure_value(PublicFailureCodeV1.OUTPUT_LIMIT_EXCEEDED)
    )
    if len(overflow) > MAX_PUBLIC_JSON_BYTES_V1:
        raise ValueError("public JSON ceiling cannot contain terminal report")
    return overflow


def _bounded_download_attempts(report: object) -> int:
    if (
        type(report) is PublicCommandReportV1
        and report.command == "download"
        and type(report.provider_attempt_count) is int
        and 0 <= report.provider_attempt_count <= MAX_DOWNLOAD_PROVIDER_ATTEMPTS_V1
    ):
        return report.provider_attempt_count
    return 0


def _download_report_value(report: object) -> dict[str, object]:
    if type(report) is not PublicCommandReportV1:
        raise ValueError
    untyped = cast(PublicCommandReportV1[object], report)
    if untyped.payload is not None and type(untyped.payload) is not DownloadPayloadV1:
        raise ValueError
    failure: PublicFailureV1 | None = (
        replace(untyped.failure) if untyped.failure is not None else None
    )
    typed_payload = untyped.payload
    payload: DownloadPayloadV1 | None = (
        replace(typed_payload) if typed_payload is not None else None
    )
    validated: DownloadReportV1 = PublicCommandReportV1(
        untyped.contract_version,
        untyped.command,
        untyped.status,
        failure,
        untyped.provider_attempt_count,
        payload,
    )
    if validated.command != "download":
        raise ValueError
    return {
        "contract_version": validated.contract_version,
        "command": validated.command,
        "status": validated.status.value,
        "failure": _failure_value(validated.failure),
        "provider_attempt_count": validated.provider_attempt_count,
        "payload": _payload_value(validated.payload),
    }


def _failure_value(value: PublicFailureV1 | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "code": value.code.value,
        "run_failure_code": _enum_value(value.run_failure_code),
        "historical_fetch_code": _enum_value(value.historical_fetch_code),
        "failure_category": _enum_value(value.failure_category),
        "validation_reason": _enum_value(value.validation_reason),
        "months": list(value.months),
    }


def _coverage_report_value(report: object) -> dict[str, object]:
    if type(report) is not PublicCommandReportV1:
        raise ValueError
    untyped = cast(PublicCommandReportV1[object], report)
    if untyped.payload is not None and type(untyped.payload) is not CoveragePayloadV1:
        raise ValueError
    failure = replace(untyped.failure) if untyped.failure is not None else None
    typed_payload = untyped.payload
    payload = replace(typed_payload) if typed_payload is not None else None
    validated: CoverageReportV1 = PublicCommandReportV1(
        untyped.contract_version,
        untyped.command,
        untyped.status,
        failure,
        untyped.provider_attempt_count,
        payload,
    )
    if validated.command != "coverage":
        raise ValueError
    return {
        "contract_version": validated.contract_version,
        "command": validated.command,
        "status": validated.status.value,
        "failure": _failure_value(validated.failure),
        "provider_attempt_count": validated.provider_attempt_count,
        "payload": _coverage_payload_value(validated.payload),
    }


def _query_report_value(report: object) -> dict[str, object]:
    if type(report) is not PublicCommandReportV1:
        raise ValueError
    untyped = cast(PublicCommandReportV1[object], report)
    if untyped.payload is not None and type(untyped.payload) is not QueryPayloadV1:
        raise ValueError
    failure = replace(untyped.failure) if untyped.failure is not None else None
    typed_payload = untyped.payload
    payload = replace(typed_payload) if typed_payload is not None else None
    validated: QueryReportV1 = PublicCommandReportV1(
        untyped.contract_version,
        untyped.command,
        untyped.status,
        failure,
        untyped.provider_attempt_count,
        payload,
    )
    if validated.command != "query":
        raise ValueError
    return {
        "contract_version": validated.contract_version,
        "command": validated.command,
        "status": validated.status.value,
        "failure": _failure_value(validated.failure),
        "provider_attempt_count": validated.provider_attempt_count,
        "payload": _query_payload_value(validated.payload),
    }


def _coverage_payload_value(
    value: CoveragePayloadV1 | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "request": {
            "segment": value.request.segment,
            "symbol": value.request.symbol,
            "from_date": value.request.from_date.isoformat(),
            "to_date": value.request.to_date.isoformat(),
        },
        "overall_state": value.overall_state.value,
        "planned_count": value.planned_count,
        "verified_count": value.verified_count,
        "missing_count": value.missing_count,
        "insufficient_count": value.insufficient_count,
        "stale_count": value.stale_count,
        "corrupt_count": value.corrupt_count,
        "schedule_unproven_count": value.schedule_unproven_count,
        "months": [_coverage_month_value(item) for item in value.months],
    }


def _coverage_month_value(value: PublicCoverageMonthV1) -> dict[str, object]:
    return {
        "month": value.month,
        "coverage_state": value.coverage_state.value,
        "actual_from_ts": _optional_instant(value.actual_from_ts),
        "actual_to_ts": _optional_instant(value.actual_to_ts),
        "row_count": value.row_count,
        "checksum_sha256": value.checksum_sha256,
        "candle_schema_version": value.candle_schema_version,
        "validation_policy_version": value.validation_policy_version,
        "schedule_digest_sha256": value.schedule_digest_sha256,
        "failure_category": _enum_value(value.failure_category),
        "validation_reason": _enum_value(value.validation_reason),
    }


def _coverage_terminal_failure_value(code: PublicFailureCodeV1) -> dict[str, object]:
    value = _terminal_failure_value(0, code)
    value["command"] = "coverage"
    return value


def _query_payload_value(value: QueryPayloadV1 | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "request": {
            "segment": value.request.segment,
            "symbol": value.request.symbol,
            "from_date": value.request.from_date.isoformat(),
            "to_date": value.request.to_date.isoformat(),
            "timeframe": value.request.timeframe,
            "fields": [field.value for field in value.request.fields],
            "max_rows": value.request.max_rows,
        },
        "row_count": value.row_count,
        "months": [_coverage_month_value(month) for month in value.months],
        "rows": [_query_row_value(row, value.request.fields) for row in value.rows],
    }


def _query_row_value(
    row: PublicQueryRowV1, fields: tuple[CandleFieldV1, ...]
) -> dict[str, object]:
    values: dict[str, object] = {}
    for field in fields:
        if field is CandleFieldV1.TS:
            values[field.value] = _instant(row.ts)
        elif field is CandleFieldV1.OPEN:
            values[field.value] = row.open
        elif field is CandleFieldV1.HIGH:
            values[field.value] = row.high
        elif field is CandleFieldV1.LOW:
            values[field.value] = row.low
        elif field is CandleFieldV1.CLOSE:
            values[field.value] = row.close
        elif field is CandleFieldV1.VOLUME:
            values[field.value] = row.volume
        else:
            raise ValueError
    return values


def _query_terminal_failure_value(code: PublicFailureCodeV1) -> dict[str, object]:
    value = _terminal_failure_value(0, code)
    value["command"] = "query"
    return value


def _payload_value(value: DownloadPayloadV1 | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "request": {
            "segment": value.request.segment,
            "symbol": value.request.symbol,
            "from_date": value.request.from_date.isoformat(),
            "to_date": value.request.to_date.isoformat(),
        },
        "started_at": _instant(value.started_at),
        "completed_at": _instant(value.completed_at),
        "planned_count": value.planned_count,
        "skipped_count": value.skipped_count,
        "locally_recovered_count": value.locally_recovered_count,
        "verified_count": value.verified_count,
        "failed_count": value.failed_count,
        "not_attempted_count": value.not_attempted_count,
        "cancelled_count": value.cancelled_count,
        "instrument_snapshot_digest_sha256": value.instrument_snapshot_digest_sha256,
        "instrument_snapshot_retrieved_at": _instant(
            value.instrument_snapshot_retrieved_at
        ),
        "instrument_snapshot_attempt_count": value.instrument_snapshot_attempt_count,
        "historical_attempt_count": value.historical_attempt_count,
        "months": [_month_value(item) for item in value.months],
    }


def _month_value(value: PublicMonthEvidenceV1) -> dict[str, object]:
    return {
        "month": value.month,
        "partition_outcome": value.partition_outcome.value,
        "reconciliation_reasons": [item.value for item in value.reconciliation_reasons],
        "provider_attempt_count": value.provider_attempt_count,
        "actual_from_ts": _optional_instant(value.actual_from_ts),
        "actual_to_ts": _optional_instant(value.actual_to_ts),
        "row_count": value.row_count,
        "checksum_sha256": value.checksum_sha256,
        "candle_schema_version": value.candle_schema_version,
        "validation_policy_version": value.validation_policy_version,
        "schedule_digest_sha256": value.schedule_digest_sha256,
        "failure_category": _enum_value(value.failure_category),
        "validation_reason": _enum_value(value.validation_reason),
        "historical_fetch_code": _enum_value(value.historical_fetch_code),
    }


def _terminal_failure_value(
    attempts: int, code: PublicFailureCodeV1
) -> dict[str, object]:
    return {
        "contract_version": "v1",
        "command": "download",
        "status": "FAILED",
        "failure": {
            "code": code.value,
            "run_failure_code": None,
            "historical_fetch_code": None,
            "failure_category": None,
            "validation_reason": None,
            "months": [],
        },
        "provider_attempt_count": attempts,
        "payload": None,
    }


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _enum_value(value: StrEnum | None) -> str | None:
    return value.value if value is not None else None


def _instant(value: datetime) -> str:
    if not _utc(value):
        raise ValueError
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _optional_instant(value: datetime | None) -> str | None:
    return None if value is None else _instant(value)


def _utc(value: object) -> bool:
    return type(value) is datetime and value.utcoffset() == timedelta(0)


def _optional_utc(value: object) -> bool:
    return value is None or _utc(value)


def _optional_digest(value: object) -> bool:
    return value is None or (
        type(value) is str and _DIGEST.fullmatch(value) is not None
    )


def _coverage_month_count(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month + 1


def _coverage_month_labels(request: PublicCoverageRequestV1) -> tuple[str, ...]:
    return _month_labels_from_dates(request.from_date, request.to_date)


def _month_labels_from_dates(start: date, end: date) -> tuple[str, ...]:
    labels: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        labels.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return tuple(labels)


_IST = timezone(timedelta(hours=5, minutes=30))
