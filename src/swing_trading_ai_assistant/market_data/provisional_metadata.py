"""Typed catalog evidence for one immutable open-month data cutoff."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

from .monthly_request_planner import PlannedInstrumentMonth
from .partition_publication import provisional_partition_relative_path

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._|:-]{0,127}\Z")
MAX_PROVISIONAL_ROWS_V1 = 65_536
MAX_PROVISIONAL_BYTES_V1 = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ProvisionalPartitionMetadataV1:
    """Immutable metadata for the latest known prefix of one calendar month."""

    schema_version: int
    provider: str
    instrument_key: str
    security_id: str
    symbol: str
    exchange: str
    segment: str
    instrument_type: str
    interval: str
    year: int
    month: int
    from_date: date
    to_date: date
    schedule_digest_sha256: str
    cutoff: datetime
    session_complete: bool
    actual_from_ts: datetime
    actual_to_ts: datetime
    row_count: int
    checksum_sha256: str
    byte_size: int
    relative_path: str
    instrument_snapshot_digest_sha256: str
    instrument_snapshot_retrieved_at: datetime
    published_at: datetime
    historical_attempt_count: int
    intraday_attempt_count: int

    def __post_init__(self) -> None:
        text_values = (
            self.provider,
            self.instrument_key,
            self.security_id,
            self.symbol,
            self.exchange,
            self.segment,
            self.instrument_type,
            self.interval,
        )
        attempts = (self.historical_attempt_count, self.intraday_attempt_count)
        if (
            type(self.schema_version) is not int
            or self.schema_version != 1
            or any(
                type(value) is not str or _SAFE_TEXT.fullmatch(value) is None
                for value in text_values
            )
            or type(self.year) is not int
            or type(self.month) is not int
            or not 1 <= self.month <= 12
            or type(self.from_date) is not date
            or type(self.to_date) is not date
            or self.from_date > self.to_date
            or (self.from_date.year, self.from_date.month) != (self.year, self.month)
            or (self.to_date.year, self.to_date.month) != (self.year, self.month)
            or not _utc_minute(self.cutoff)
            or not _utc_minute(self.actual_from_ts)
            or not _utc_minute(self.actual_to_ts)
            or not _utc(self.instrument_snapshot_retrieved_at)
            or not _utc(self.published_at)
            or type(self.session_complete) is not bool
            or type(self.row_count) is not int
            or not 1 <= self.row_count <= MAX_PROVISIONAL_ROWS_V1
            or type(self.byte_size) is not int
            or not 1 <= self.byte_size <= MAX_PROVISIONAL_BYTES_V1
            or any(
                type(value) is not str or _DIGEST.fullmatch(value) is None
                for value in (
                    self.schedule_digest_sha256,
                    self.checksum_sha256,
                    self.instrument_snapshot_digest_sha256,
                )
            )
            or any(type(value) is not int or not 0 <= value <= 1 for value in attempts)
            or self.actual_from_ts > self.actual_to_ts
            or self.actual_to_ts != self.cutoff
            or self.published_at < self.actual_to_ts
            or self.instrument_snapshot_retrieved_at > self.published_at
        ):
            raise ValueError("invalid provisional partition metadata")
        plan = self.plan
        if self.relative_path != provisional_partition_relative_path(
            plan, self.cutoff, self.schedule_digest_sha256
        ):
            raise ValueError("invalid provisional partition metadata")

    @property
    def plan(self) -> PlannedInstrumentMonth:
        return PlannedInstrumentMonth(
            self.provider,
            self.instrument_key,
            self.security_id,
            self.symbol,
            self.exchange,
            self.segment,
            self.instrument_type,
            self.interval,
            self.year,
            self.month,
            self.from_date,
            self.to_date,
        )


def metadata_from_publication(
    *,
    plan: PlannedInstrumentMonth,
    schedule_digest_sha256: str,
    cutoff: datetime,
    session_complete: bool,
    actual_from_ts: datetime,
    actual_to_ts: datetime,
    row_count: int,
    checksum_sha256: str,
    byte_size: int,
    relative_path: str,
    instrument_snapshot_digest_sha256: str,
    instrument_snapshot_retrieved_at: datetime,
    published_at: datetime,
    historical_attempt_count: int,
    intraday_attempt_count: int,
) -> ProvisionalPartitionMetadataV1:
    """Build one flattened catalog row from already validated domain evidence."""
    return ProvisionalPartitionMetadataV1(
        1,
        plan.provider,
        plan.instrument_key,
        plan.security_id,
        plan.symbol,
        plan.exchange,
        plan.segment,
        plan.instrument_type,
        plan.interval,
        plan.year,
        plan.month,
        plan.from_date,
        plan.to_date,
        schedule_digest_sha256,
        cutoff.astimezone(UTC),
        session_complete,
        actual_from_ts.astimezone(UTC),
        actual_to_ts.astimezone(UTC),
        row_count,
        checksum_sha256,
        byte_size,
        relative_path,
        instrument_snapshot_digest_sha256,
        instrument_snapshot_retrieved_at.astimezone(UTC),
        published_at.astimezone(UTC),
        historical_attempt_count,
        intraday_attempt_count,
    )


def _utc_minute(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is UTC
        and value.second == 0
        and value.microsecond == 0
    )


def _utc(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is UTC
