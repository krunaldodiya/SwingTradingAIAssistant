"""Stable, bounded public report models and JSON rendering."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Generic, Literal, TypeVar, cast

from .historical import HistoricalFetchCode
from .manifest_lifecycle import FailureCategory
from .partition_reconciliation import RequestReason
from .range_ingestion import PartitionOutcome, RunFailureCode
from .validation import ValidationReason

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
            or (
                self.status
                in {PublicCommandStatusV1.SUCCEEDED, PublicCommandStatusV1.PARTIAL}
            )
            != (self.payload is not None)
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


DownloadReportV1 = PublicCommandReportV1[DownloadPayloadV1]


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
