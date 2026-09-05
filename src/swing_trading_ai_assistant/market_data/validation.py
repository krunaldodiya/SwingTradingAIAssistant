"""Pure schedule-bound validation for one canonical NSE equity month."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Final, cast

from .monthly_request_planner import PlannedInstrumentMonth
from .schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleEvidenceResult,
    ScheduleEvidenceValidationError,
    ScheduleOutcome,
    canonical_schedule_bytes,
)
from .schemas import CanonicalCandle

MAX_CANONICAL_EQUITY_CANDLES = 65_536
EQUITY_MONTH_VALIDATION_POLICY_V1: Final = "nse-equity-month@v1"
SUPPORTED_EQUITY_MONTH_VALIDATION_POLICIES: Final = (EQUITY_MONTH_VALIDATION_POLICY_V1,)
_SCHEDULE_POLICY_SEPARATOR = "+sessions-sha256:"
_BOUND_POLICY_RE = re.compile(
    rf"{re.escape(EQUITY_MONTH_VALIDATION_POLICY_V1)}"
    r"\+sessions-sha256:([0-9a-f]{64})\Z"
)


class ValidationReason(StrEnum):
    """Stable reasons for schedule-bound validation evidence."""

    NONE = "NONE"
    SCHEDULE_DIGEST_MISSING = "SCHEDULE_DIGEST_MISSING"
    SCHEDULE_DIGEST_MISMATCH = "SCHEDULE_DIGEST_MISMATCH"
    SCHEDULE_RETAINED_BYTES_INVALID = "SCHEDULE_RETAINED_BYTES_INVALID"
    SCHEDULE_COVERAGE_INCOMPLETE = "SCHEDULE_COVERAGE_INCOMPLETE"
    COVERAGE_EXPECTED_BAR_MISSING = "COVERAGE_EXPECTED_BAR_MISSING"
    COVERAGE_OFF_SESSION_BAR = "COVERAGE_OFF_SESSION_BAR"
    QUALITY_INVALID_OHLC = "QUALITY_INVALID_OHLC"
    QUALITY_INVALID_VOLUME = "QUALITY_INVALID_VOLUME"


@dataclass(frozen=True, slots=True)
class ValidationEvidence:
    """Immutable evidence produced by one validation-policy invocation."""

    plan: PlannedInstrumentMonth
    policy_version: str
    schedule_digest: str | None
    raw_row_count: int
    normalized_row_count: int
    row_count: int
    actual_from_ts: datetime | None
    actual_to_ts: datetime | None
    coverage_passed: bool
    quality_passed: bool
    reason: ValidationReason

    def __init_subclass__(cls) -> None:
        raise TypeError("ValidationEvidence cannot be subclassed")

    def __post_init__(self) -> None:
        if type(self.plan) is not PlannedInstrumentMonth:
            raise ValueError("invalid validation evidence")
        if not _valid_policy_version(self.policy_version):
            raise ValueError("invalid validation evidence")
        _validate_evidence_counts(self)
        _validate_evidence_timestamps(self)
        _validate_evidence_outcome(self)
        _validate_evidence_policy(self)

    @property
    def failure_reason(self) -> ValidationReason:
        """Return the stable reason under the report-oriented name."""
        return self.reason


def _validate_evidence_counts(evidence: ValidationEvidence) -> None:
    if evidence.schedule_digest is not None and not _valid_digest(
        evidence.schedule_digest
    ):
        raise ValueError("invalid validation evidence")
    if (
        type(evidence.raw_row_count) is not int
        or type(evidence.normalized_row_count) is not int
        or type(evidence.row_count) is not int
        or evidence.raw_row_count < 0
        or evidence.raw_row_count < evidence.normalized_row_count
        or evidence.normalized_row_count < 0
        or evidence.normalized_row_count != evidence.row_count
        or not 0 <= evidence.row_count <= MAX_CANONICAL_EQUITY_CANDLES
    ):
        raise ValueError("invalid validation evidence")


def _validate_evidence_timestamps(evidence: ValidationEvidence) -> None:
    if not _valid_evidence_timestamp(evidence.actual_from_ts, evidence.plan) or not (
        _valid_evidence_timestamp(evidence.actual_to_ts, evidence.plan)
    ):
        raise ValueError("invalid validation evidence")
    has_from = evidence.actual_from_ts is not None
    has_to = evidence.actual_to_ts is not None
    if has_from != has_to or has_from != (evidence.row_count > 0):
        raise ValueError("invalid validation evidence")
    if (
        evidence.actual_from_ts is not None
        and evidence.actual_to_ts is not None
        and (
            evidence.actual_from_ts > evidence.actual_to_ts
            or evidence.row_count
            > (evidence.actual_to_ts - evidence.actual_from_ts) // timedelta(minutes=1)
            + 1
        )
    ):
        raise ValueError("invalid validation evidence")


def _validate_evidence_outcome(evidence: ValidationEvidence) -> None:
    if (
        type(evidence.coverage_passed) is not bool
        or type(evidence.quality_passed) is not bool
        or type(evidence.reason) is not ValidationReason
        or (evidence.coverage_passed and evidence.row_count == 0)
        or not _reason_matches_outcome(
            evidence.reason, evidence.coverage_passed, evidence.quality_passed
        )
    ):
        raise ValueError("invalid validation evidence")


def _validate_evidence_policy(evidence: ValidationEvidence) -> None:
    policy_digest = _policy_digest(evidence.policy_version)
    if evidence.schedule_digest is not None and policy_digest is None:
        raise ValueError("invalid validation evidence")
    if (evidence.coverage_passed or evidence.quality_passed) and (
        not _valid_digest(evidence.schedule_digest)
        or policy_digest != evidence.schedule_digest
    ):
        raise ValueError("invalid validation evidence")


class EquityMonthValidationPolicy:
    """Validate one full closed NSE equity month without I/O or side effects."""

    def __init__(self, policy_version: str) -> None:
        if not _valid_policy_version(policy_version):
            raise ValueError("policy_version must be a nonblank built-in string")
        self._policy_version = policy_version

    @property
    def policy_version(self) -> str:
        """Return the unbound policy name and version supplied by the caller."""
        return self._policy_version

    def validate(
        self,
        plan: PlannedInstrumentMonth,
        candles: Sequence[CanonicalCandle],
        expected_sessions: ScheduleEvidenceResult,
        raw_row_count: int,
        normalized_row_count: int,
    ) -> ValidationEvidence:
        """Return deterministic coverage, quality, and provenance evidence."""
        _validate_plan(plan)
        values = _validated_candles(candles, plan)
        _validate_row_counts(raw_row_count, normalized_row_count, len(values))
        actual_from, actual_to = _actual_coverage(values)
        schedule, digest, schedule_reason = _resolved_schedule(expected_sessions)
        if schedule_reason is not None:
            return _evidence(
                plan,
                self._policy_version,
                digest,
                raw_row_count,
                normalized_row_count,
                actual_from,
                actual_to,
                False,
                False,
                schedule_reason,
            )

        if schedule is None:
            return _evidence(
                plan,
                self._policy_version,
                digest,
                raw_row_count,
                normalized_row_count,
                actual_from,
                actual_to,
                False,
                False,
                ValidationReason.SCHEDULE_DIGEST_MISSING,
            )
        policy_version, policy_reason = _bound_policy_version(
            self._policy_version, digest
        )
        if policy_reason is not None:
            return _evidence(
                plan,
                self._policy_version,
                digest,
                raw_row_count,
                normalized_row_count,
                actual_from,
                actual_to,
                False,
                False,
                policy_reason,
            )

        expected, schedule_reason = _expected_bars(plan, schedule)
        if schedule_reason is not None:
            return _evidence(
                plan,
                policy_version,
                digest,
                raw_row_count,
                normalized_row_count,
                actual_from,
                actual_to,
                False,
                False,
                schedule_reason,
            )

        actual = {candle.ts for candle in values}
        coverage_passed = not (expected - actual) and not (actual - expected)
        quality_passed, quality_reason = _quality_result(values)
        reason = (
            ValidationReason.COVERAGE_EXPECTED_BAR_MISSING
            if expected - actual
            else ValidationReason.COVERAGE_OFF_SESSION_BAR
            if actual - expected
            else quality_reason
        )
        return _evidence(
            plan,
            policy_version,
            digest,
            raw_row_count,
            normalized_row_count,
            actual_from,
            actual_to,
            coverage_passed,
            quality_passed,
            reason,
        )


def _evidence(
    plan: PlannedInstrumentMonth,
    policy_version: str,
    digest: str | None,
    raw_row_count: int,
    normalized_row_count: int,
    actual_from: datetime | None,
    actual_to: datetime | None,
    coverage_passed: bool,
    quality_passed: bool,
    reason: ValidationReason,
) -> ValidationEvidence:
    if _valid_digest(digest) and _policy_digest(policy_version) is None:
        policy_version += _SCHEDULE_POLICY_SEPARATOR + cast(str, digest)
    return ValidationEvidence(
        plan,
        policy_version,
        digest,
        raw_row_count,
        normalized_row_count,
        normalized_row_count,
        actual_from,
        actual_to,
        coverage_passed,
        quality_passed,
        reason,
    )


def _validate_plan(plan: object) -> None:
    if type(plan) is not PlannedInstrumentMonth:
        raise ValueError("plan must be an exact PlannedInstrumentMonth")
    expected_from = date(plan.year, plan.month, 1)
    next_month = date(
        plan.year + (plan.month == 12), 1 if plan.month == 12 else plan.month + 1, 1
    )
    expected_to = next_month - timedelta(days=1)
    if (
        plan.interval != "1m"
        or plan.from_date != expected_from
        or plan.to_date != expected_to
    ):
        raise ValueError("plan must be one exact canonical calendar month")


def _validated_candles(
    candles: object, plan: PlannedInstrumentMonth
) -> tuple[CanonicalCandle, ...]:
    if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)):
        raise ValueError("candles must be a finite sequence")
    sequence = cast(Sequence[object], candles)
    try:
        count = len(sequence)
    except Exception:
        raise ValueError(
            "candles must provide a valid finite sequence length"
        ) from None
    if count > MAX_CANONICAL_EQUITY_CANDLES:
        raise ValueError("candles exceed the maximum one-month equity count")
    values: list[CanonicalCandle] = []
    seen: set[datetime] = set()
    for index in range(count):
        try:
            candle = sequence[index]
        except Exception:
            raise ValueError("candles sequence is malformed") from None
        if type(candle) is not CanonicalCandle:
            raise ValueError("candles must contain exact CanonicalCandle values")
        if (
            candle.provider != plan.provider
            or candle.instrument_key != plan.instrument_key
            or candle.security_id != plan.security_id
            or candle.symbol != plan.symbol
            or candle.exchange != plan.exchange
            or candle.segment != plan.segment
            or candle.instrument_type != plan.instrument_type
            or candle.interval != plan.interval
            or not _candle_timestamp_matches_month(candle.ts, plan)
        ):
            raise ValueError("candles do not match the canonical month plan")
        if (
            candle.underlying_id is not None
            or candle.expiry is not None
            or candle.strike is not None
            or candle.option_type is not None
            or candle.oi is not None
        ):
            raise ValueError("NSE equity candles cannot contain derivative metadata")
        if candle.ts in seen:
            raise ValueError("candles contain duplicate canonical timestamps")
        seen.add(candle.ts)
        values.append(candle)
    return tuple(values)


def _validate_row_counts(raw: object, normalized: object, candle_count: int) -> None:
    if (
        type(raw) is not int
        or type(normalized) is not int
        or raw < 0
        or normalized < 0
        or raw < normalized
        or normalized != candle_count
    ):
        raise ValueError("raw and normalized row counts are inconsistent")


def _actual_coverage(
    candles: Sequence[CanonicalCandle],
) -> tuple[datetime | None, datetime | None]:
    if not candles:
        return None, None
    timestamps = [candle.ts for candle in candles]
    return min(timestamps), max(timestamps)


def _resolved_schedule(
    value: object,
) -> tuple[
    ExpectedSessionSchedule | None,
    str | None,
    ValidationReason | None,
]:
    if value is None:
        return None, None, ValidationReason.SCHEDULE_DIGEST_MISSING
    if type(value) is not ScheduleEvidenceResult:
        return None, None, ValidationReason.SCHEDULE_RETAINED_BYTES_INVALID
    if value.outcome is ScheduleOutcome.FAILED:
        reported_digest = value.digest if _valid_digest(value.digest) else None
        reason = (
            ValidationReason.SCHEDULE_DIGEST_MISSING
            if reported_digest is None
            else ValidationReason.SCHEDULE_RETAINED_BYTES_INVALID
        )
        return None, reported_digest, reason
    if (
        value.schedule is None
        or type(value.canonical_bytes) is not bytes
        or type(value.digest) is not str
    ):
        return (
            None,
            value.digest if _valid_digest(value.digest) else None,
            ValidationReason.SCHEDULE_DIGEST_MISSING,
        )
    try:
        canonical = canonical_schedule_bytes(value.schedule)
    except ScheduleEvidenceValidationError:
        return (
            None,
            value.digest if _valid_digest(value.digest) else None,
            ValidationReason.SCHEDULE_RETAINED_BYTES_INVALID,
        )
    actual_digest = hashlib.sha256(value.canonical_bytes).hexdigest()
    if value.canonical_bytes != canonical:
        return (
            None,
            value.digest if _valid_digest(value.digest) else None,
            ValidationReason.SCHEDULE_RETAINED_BYTES_INVALID,
        )
    if actual_digest != value.digest:
        return (
            None,
            value.digest if _valid_digest(value.digest) else None,
            ValidationReason.SCHEDULE_DIGEST_MISMATCH,
        )
    return value.schedule, actual_digest, None


def _bound_policy_version(
    policy_version: str, digest: str | None
) -> tuple[str, ValidationReason | None]:
    if not _valid_digest(digest):
        return policy_version, ValidationReason.SCHEDULE_DIGEST_MISSING
    supplied_digest = _policy_digest(policy_version)
    if supplied_digest is None:
        return policy_version + _SCHEDULE_POLICY_SEPARATOR + cast(str, digest), None
    if supplied_digest != digest:
        return policy_version, ValidationReason.SCHEDULE_DIGEST_MISMATCH
    return policy_version, None


def _expected_bars(
    plan: PlannedInstrumentMonth, schedule: ExpectedSessionSchedule
) -> tuple[set[datetime], ValidationReason | None]:
    if schedule.covered_from > plan.from_date or schedule.covered_to < plan.to_date:
        return set(), ValidationReason.SCHEDULE_COVERAGE_INCOMPLETE
    expected: set[datetime] = set()
    for session in schedule.sessions:
        if not plan.from_date <= session.trade_date <= plan.to_date:
            continue
        current = session.open_at
        while current < session.close_at:
            if len(expected) >= MAX_CANONICAL_EQUITY_CANDLES:
                return set(), ValidationReason.SCHEDULE_COVERAGE_INCOMPLETE
            expected.add(current)
            current += timedelta(minutes=1)
    if not expected:
        return set(), ValidationReason.SCHEDULE_COVERAGE_INCOMPLETE
    return expected, None


def _quality_result(
    candles: Sequence[CanonicalCandle],
) -> tuple[bool, ValidationReason]:
    invalid_ohlc = False
    invalid_volume = False
    for candle in candles:
        if _invalid_ohlc(candle):
            invalid_ohlc = True
        if type(candle.volume) is not int or candle.volume < 0:
            invalid_volume = True
    if invalid_ohlc:
        return False, ValidationReason.QUALITY_INVALID_OHLC
    if invalid_volume:
        return False, ValidationReason.QUALITY_INVALID_VOLUME
    return True, ValidationReason.NONE


def _valid_policy_version(value: object) -> bool:
    return type(value) is str and (
        value in SUPPORTED_EQUITY_MONTH_VALIDATION_POLICIES
        or supported_equity_month_policy_digest(value) is not None
    )


def supported_equity_month_policy_digest(value: object) -> str | None:
    """Return the digest only for the frozen supported bound policy."""
    if type(value) is not str:
        return None
    match = _BOUND_POLICY_RE.fullmatch(value)
    return match.group(1) if match is not None else None


def _policy_digest(value: object) -> str | None:
    return supported_equity_month_policy_digest(value)


def _reason_matches_outcome(
    reason: ValidationReason, coverage_passed: bool, quality_passed: bool
) -> bool:
    if reason is ValidationReason.NONE:
        return coverage_passed and quality_passed
    if reason in {
        ValidationReason.SCHEDULE_DIGEST_MISSING,
        ValidationReason.SCHEDULE_DIGEST_MISMATCH,
        ValidationReason.SCHEDULE_RETAINED_BYTES_INVALID,
        ValidationReason.SCHEDULE_COVERAGE_INCOMPLETE,
    }:
        return not coverage_passed and not quality_passed
    if reason in {
        ValidationReason.COVERAGE_EXPECTED_BAR_MISSING,
        ValidationReason.COVERAGE_OFF_SESSION_BAR,
    }:
        return not coverage_passed
    if reason in {
        ValidationReason.QUALITY_INVALID_OHLC,
        ValidationReason.QUALITY_INVALID_VOLUME,
    }:
        return coverage_passed and not quality_passed
    return False


def _valid_digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_price(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(float(cast(int | float, value)))
    except (OverflowError, TypeError, ValueError):
        return False


def _invalid_ohlc(candle: CanonicalCandle) -> bool:
    prices = (candle.open, candle.high, candle.low, candle.close)
    if not all(_valid_price(value) for value in prices):
        return True
    return (
        min(prices) < 0
        or candle.high < max(candle.open, candle.close, candle.low)
        or candle.low > min(candle.open, candle.close, candle.high)
    )


def _candle_timestamp_matches_month(
    value: object, plan: PlannedInstrumentMonth
) -> bool:
    if type(value) is not datetime:
        return False
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            return False
        timestamp = value.astimezone(UTC)
    except (OverflowError, TypeError, ValueError):
        return False
    return plan.from_date <= timestamp.date() <= plan.to_date


def _valid_evidence_timestamp(
    value: datetime | None, plan: PlannedInstrumentMonth
) -> bool:
    if value is None:
        return True
    return (
        type(value) is datetime
        and value.tzinfo is UTC
        and value.second == 0
        and value.microsecond == 0
        and plan.from_date <= value.date() <= plan.to_date
    )
