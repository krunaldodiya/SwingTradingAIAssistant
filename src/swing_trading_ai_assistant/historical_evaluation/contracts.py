"""Pure point-in-time contracts for historical anchor eligibility."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from enum import StrEnum
from typing import ClassVar, Final

ANCHOR_ELIGIBILITY_SCHEMA_VERSION_V1: Final = 1
ANCHOR_ELIGIBILITY_CONTRACT_VERSION_V1: Final = "nifty50-anchor-eligibility@v1"
_IST: Final = timezone(timedelta(hours=5, minutes=30))
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_ISIN: Final = re.compile(r"INE[A-Z0-9]{8}[0-9]\Z")
_SYMBOL: Final = re.compile(r"[A-Z0-9][A-Z0-9.&_-]{0,31}\Z")


class EvidenceAvailabilityV1(StrEnum):
    """Availability of one exact evidence object at a decision boundary."""

    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    AMBIGUOUS = "AMBIGUOUS"


class AnchorEligibilityStatusV1(StrEnum):
    """Exhaustive result states for one requested historical anchor."""

    ELIGIBLE = "ELIGIBLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    EXCLUDED_PREDECLARED = "EXCLUDED_PREDECLARED"


class AnchorEligibilityReasonV1(StrEnum):
    """Stable reason codes for anchor eligibility version 1."""

    UNIVERSE_MISSING = "UNIVERSE_MISSING"
    UNIVERSE_AMBIGUOUS = "UNIVERSE_AMBIGUOUS"
    UNIVERSE_NOT_KNOWN_AT_CUTOFF = "UNIVERSE_NOT_KNOWN_AT_CUTOFF"
    MEMBERSHIP_UNDETERMINED = "MEMBERSHIP_UNDETERMINED"
    SCHEDULE_MISSING = "SCHEDULE_MISSING"
    SCHEDULE_AMBIGUOUS = "SCHEDULE_AMBIGUOUS"
    SCHEDULE_NOT_KNOWN_AT_CUTOFF = "SCHEDULE_NOT_KNOWN_AT_CUTOFF"
    ANCHOR_NOT_OFFICIAL_SESSION = "ANCHOR_NOT_OFFICIAL_SESSION"
    RAW_CANDLES_MISSING = "RAW_CANDLES_MISSING"
    RAW_CANDLES_AMBIGUOUS = "RAW_CANDLES_AMBIGUOUS"
    RAW_CANDLES_NOT_KNOWN_AT_CUTOFF = "RAW_CANDLES_NOT_KNOWN_AT_CUTOFF"
    ANCHOR_BAR_MISSING = "ANCHOR_BAR_MISSING"
    CORPORATE_ACTIONS_MISSING = "CORPORATE_ACTIONS_MISSING"
    CORPORATE_ACTIONS_AMBIGUOUS = "CORPORATE_ACTIONS_AMBIGUOUS"
    CORPORATE_ACTIONS_NOT_KNOWN_AT_CUTOFF = "CORPORATE_ACTIONS_NOT_KNOWN_AT_CUTOFF"
    NOT_NIFTY50_MEMBER = "NOT_NIFTY50_MEMBER"


@dataclass(frozen=True, slots=True)
class OfficialSessionV1:
    """One authoritative official NSE session, independent of a provider."""

    trade_date: date
    open_at: datetime
    close_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.trade_date) is not date
            or type(self.open_at) is not datetime
            or type(self.close_at) is not datetime
        ):
            raise ValueError("invalid official session")
        open_at = _utc(self.open_at, "open_at")
        close_at = _utc(self.close_at, "close_at")
        if (
            open_at.second != 0
            or open_at.microsecond != 0
            or close_at.second != 0
            or close_at.microsecond != 0
            or close_at <= open_at
            or open_at.astimezone(_IST).date() != self.trade_date
            or close_at.astimezone(_IST).date() != self.trade_date
        ):
            raise ValueError("invalid official session")
        object.__setattr__(self, "open_at", open_at)
        object.__setattr__(self, "close_at", close_at)

    def __init_subclass__(cls) -> None:
        raise TypeError("OfficialSessionV1 cannot be subclassed")


@dataclass(frozen=True, slots=True)
class PointInTimeEvidenceV1:
    """Identity and knowledge time of one immutable evidence object."""

    state: EvidenceAvailabilityV1
    known_at: datetime | None
    evidence_digest_sha256: str | None

    def __post_init__(self) -> None:
        if type(self.state) is not EvidenceAvailabilityV1:
            raise ValueError("invalid point-in-time evidence")
        if self.state is EvidenceAvailabilityV1.AVAILABLE:
            if (
                type(self.known_at) is not datetime
                or type(self.evidence_digest_sha256) is not str
                or _DIGEST.fullmatch(self.evidence_digest_sha256) is None
            ):
                raise ValueError("invalid point-in-time evidence")
            object.__setattr__(self, "known_at", _utc(self.known_at, "known_at"))
        elif self.known_at is not None or self.evidence_digest_sha256 is not None:
            raise ValueError("invalid point-in-time evidence")

    def __init_subclass__(cls) -> None:
        raise TypeError("PointInTimeEvidenceV1 cannot be subclassed")


@dataclass(frozen=True, slots=True)
class AnchorEligibilityRequestV1:
    """One post-close stock/session decision cutoff to classify."""

    schema_version: int
    isin: str
    symbol: str
    decision_session: OfficialSessionV1
    decision_cutoff: datetime

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != ANCHOR_ELIGIBILITY_SCHEMA_VERSION_V1
            or type(self.isin) is not str
            or _ISIN.fullmatch(self.isin) is None
            or type(self.symbol) is not str
            or _SYMBOL.fullmatch(self.symbol) is None
            or type(self.decision_session) is not OfficialSessionV1
            or type(self.decision_cutoff) is not datetime
        ):
            raise ValueError("invalid anchor eligibility request")
        cutoff = _utc(self.decision_cutoff, "decision_cutoff")
        if cutoff != self.decision_session.close_at:
            raise ValueError("decision cutoff must equal official close")
        object.__setattr__(self, "decision_cutoff", cutoff)

    def __init_subclass__(cls) -> None:
        raise TypeError("AnchorEligibilityRequestV1 cannot be subclassed")


@dataclass(frozen=True, slots=True)
class AnchorEligibilityEvidenceV1:
    """Decision-side evidence only; future prices cannot enter this contract."""

    universe: PointInTimeEvidenceV1
    schedule: PointInTimeEvidenceV1
    anchor_candles: PointInTimeEvidenceV1
    corporate_actions: PointInTimeEvidenceV1
    is_nifty50_member: bool | None
    anchor_is_official_session: bool | None
    anchor_bar_complete: bool | None

    schema_version: ClassVar[int] = ANCHOR_ELIGIBILITY_SCHEMA_VERSION_V1

    def __post_init__(self) -> None:
        if (
            type(self.universe) is not PointInTimeEvidenceV1
            or type(self.schedule) is not PointInTimeEvidenceV1
            or type(self.anchor_candles) is not PointInTimeEvidenceV1
            or type(self.corporate_actions) is not PointInTimeEvidenceV1
            or type(self.is_nifty50_member) not in (bool, type(None))
            or type(self.anchor_is_official_session) not in (bool, type(None))
            or type(self.anchor_bar_complete) not in (bool, type(None))
        ):
            raise ValueError("invalid anchor eligibility evidence")

    def __init_subclass__(cls) -> None:
        raise TypeError("AnchorEligibilityEvidenceV1 cannot be subclassed")

    def canonical_json_bytes(self) -> bytes:
        """Return the exact decision-side evidence-digest representation."""
        value = {
            "anchor_bar_complete": self.anchor_bar_complete,
            "anchor_candles": _evidence_value(self.anchor_candles),
            "anchor_is_official_session": self.anchor_is_official_session,
            "corporate_actions": _evidence_value(self.corporate_actions),
            "is_nifty50_member": self.is_nifty50_member,
            "schedule": _evidence_value(self.schedule),
            "schema_version": self.schema_version,
            "universe": _evidence_value(self.universe),
        }
        return _canonical_bytes(value)

    def digest_sha256(self) -> str:
        """Return SHA-256 of the exact evidence representation."""
        return hashlib.sha256(self.canonical_json_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class AnchorEligibilityObservationV1:
    """One deterministic, content-addressable eligibility observation."""

    schema_version: int
    isin: str
    symbol: str
    decision_session: OfficialSessionV1
    decision_cutoff: datetime
    status: AnchorEligibilityStatusV1
    reasons: tuple[AnchorEligibilityReasonV1, ...]
    evidence_digest_sha256: str

    def __post_init__(self) -> None:
        valid_request = AnchorEligibilityRequestV1(
            self.schema_version,
            self.isin,
            self.symbol,
            self.decision_session,
            self.decision_cutoff,
        )
        if (
            type(self.status) is not AnchorEligibilityStatusV1
            or type(self.reasons) is not tuple
            or any(
                type(reason) is not AnchorEligibilityReasonV1 for reason in self.reasons
            )
            or len(set(self.reasons)) != len(self.reasons)
            or type(self.evidence_digest_sha256) is not str
            or _DIGEST.fullmatch(self.evidence_digest_sha256) is None
            or not _valid_status_reasons(self.status, self.reasons)
        ):
            raise ValueError("invalid anchor eligibility observation")
        object.__setattr__(self, "decision_cutoff", valid_request.decision_cutoff)

    def __init_subclass__(cls) -> None:
        raise TypeError("AnchorEligibilityObservationV1 cannot be subclassed")

    def canonical_json_bytes(self) -> bytes:
        """Return the exact versioned observation representation."""
        return _canonical_bytes(
            {
                "decision_cutoff": _timestamp(self.decision_cutoff),
                "decision_session": _session_value(self.decision_session),
                "evidence_digest_sha256": self.evidence_digest_sha256,
                "isin": self.isin,
                "reasons": [reason.value for reason in self.reasons],
                "schema_version": self.schema_version,
                "status": self.status.value,
                "symbol": self.symbol,
            }
        )

    @property
    def observation_digest_sha256(self) -> str:
        """Return SHA-256 of the exact observation representation."""
        return hashlib.sha256(self.canonical_json_bytes()).hexdigest()


def classify_anchor_eligibility_v1(
    request: AnchorEligibilityRequestV1,
    evidence: AnchorEligibilityEvidenceV1,
) -> AnchorEligibilityObservationV1:
    """Classify an anchor using evidence known no later than its cutoff."""
    if (
        type(request) is not AnchorEligibilityRequestV1
        or type(evidence) is not AnchorEligibilityEvidenceV1
    ):
        raise ValueError("invalid anchor eligibility classification input")

    reasons: list[AnchorEligibilityReasonV1] = []
    universe_available = _append_evidence_reason(
        reasons,
        evidence.universe,
        request.decision_cutoff,
        AnchorEligibilityReasonV1.UNIVERSE_MISSING,
        AnchorEligibilityReasonV1.UNIVERSE_AMBIGUOUS,
        AnchorEligibilityReasonV1.UNIVERSE_NOT_KNOWN_AT_CUTOFF,
    )
    if universe_available and evidence.is_nifty50_member is None:
        reasons.append(AnchorEligibilityReasonV1.MEMBERSHIP_UNDETERMINED)

    schedule_available = _append_evidence_reason(
        reasons,
        evidence.schedule,
        request.decision_cutoff,
        AnchorEligibilityReasonV1.SCHEDULE_MISSING,
        AnchorEligibilityReasonV1.SCHEDULE_AMBIGUOUS,
        AnchorEligibilityReasonV1.SCHEDULE_NOT_KNOWN_AT_CUTOFF,
    )
    if schedule_available and evidence.anchor_is_official_session is not True:
        reasons.append(AnchorEligibilityReasonV1.ANCHOR_NOT_OFFICIAL_SESSION)

    candles_available = _append_evidence_reason(
        reasons,
        evidence.anchor_candles,
        request.decision_cutoff,
        AnchorEligibilityReasonV1.RAW_CANDLES_MISSING,
        AnchorEligibilityReasonV1.RAW_CANDLES_AMBIGUOUS,
        AnchorEligibilityReasonV1.RAW_CANDLES_NOT_KNOWN_AT_CUTOFF,
    )
    if candles_available and evidence.anchor_bar_complete is not True:
        reasons.append(AnchorEligibilityReasonV1.ANCHOR_BAR_MISSING)

    _append_evidence_reason(
        reasons,
        evidence.corporate_actions,
        request.decision_cutoff,
        AnchorEligibilityReasonV1.CORPORATE_ACTIONS_MISSING,
        AnchorEligibilityReasonV1.CORPORATE_ACTIONS_AMBIGUOUS,
        AnchorEligibilityReasonV1.CORPORATE_ACTIONS_NOT_KNOWN_AT_CUTOFF,
    )

    reasons.sort(key=_reason_order)
    if reasons:
        status = AnchorEligibilityStatusV1.INSUFFICIENT_EVIDENCE
    elif evidence.is_nifty50_member is False:
        status = AnchorEligibilityStatusV1.EXCLUDED_PREDECLARED
        reasons.append(AnchorEligibilityReasonV1.NOT_NIFTY50_MEMBER)
    else:
        status = AnchorEligibilityStatusV1.ELIGIBLE

    return AnchorEligibilityObservationV1(
        schema_version=request.schema_version,
        isin=request.isin,
        symbol=request.symbol,
        decision_session=request.decision_session,
        decision_cutoff=request.decision_cutoff,
        status=status,
        reasons=tuple(reasons),
        evidence_digest_sha256=evidence.digest_sha256(),
    )


def _append_evidence_reason(
    reasons: list[AnchorEligibilityReasonV1],
    evidence: PointInTimeEvidenceV1,
    cutoff: datetime,
    missing: AnchorEligibilityReasonV1,
    ambiguous: AnchorEligibilityReasonV1,
    future: AnchorEligibilityReasonV1,
) -> bool:
    if evidence.state is EvidenceAvailabilityV1.MISSING:
        reasons.append(missing)
        return False
    if evidence.state is EvidenceAvailabilityV1.AMBIGUOUS:
        reasons.append(ambiguous)
        return False
    if evidence.known_at is None or evidence.known_at > cutoff:
        reasons.append(future)
        return False
    return True


def _reason_order(reason: AnchorEligibilityReasonV1) -> int:
    return tuple(AnchorEligibilityReasonV1).index(reason)


def _valid_status_reasons(
    status: AnchorEligibilityStatusV1,
    reasons: tuple[AnchorEligibilityReasonV1, ...],
) -> bool:
    if status is AnchorEligibilityStatusV1.ELIGIBLE:
        return not reasons
    if status is AnchorEligibilityStatusV1.EXCLUDED_PREDECLARED:
        return reasons == (AnchorEligibilityReasonV1.NOT_NIFTY50_MEMBER,)
    return bool(reasons) and AnchorEligibilityReasonV1.NOT_NIFTY50_MEMBER not in reasons


def _evidence_value(evidence: PointInTimeEvidenceV1) -> dict[str, object]:
    return {
        "evidence_digest_sha256": evidence.evidence_digest_sha256,
        "known_at": None
        if evidence.known_at is None
        else _timestamp(evidence.known_at),
        "state": evidence.state.value,
    }


def _session_value(session: OfficialSessionV1) -> dict[str, str]:
    return {
        "close_at": _timestamp(session.close_at),
        "open_at": _timestamp(session.open_at),
        "trade_date": session.trade_date.isoformat(),
    }


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _utc(value: datetime, field: str) -> datetime:
    try:
        aware = value.tzinfo is not None and value.utcoffset() is not None
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be timezone-aware") from exc
    if not aware:
        raise ValueError(f"{field} must be timezone-aware")
    try:
        return value.astimezone(UTC)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{field} cannot be converted to UTC") from exc
