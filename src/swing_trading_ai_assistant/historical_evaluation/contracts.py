"""Pure point-in-time contracts for historical anchor eligibility."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal
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
    if schedule_available and evidence.anchor_is_official_session is False:
        status = AnchorEligibilityStatusV1.EXCLUDED_PREDECLARED
        reasons = [AnchorEligibilityReasonV1.ANCHOR_NOT_OFFICIAL_SESSION]
    elif universe_available and evidence.is_nifty50_member is False:
        status = AnchorEligibilityStatusV1.EXCLUDED_PREDECLARED
        reasons = [AnchorEligibilityReasonV1.NOT_NIFTY50_MEMBER]
    elif reasons:
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
        return reasons in (
            (AnchorEligibilityReasonV1.NOT_NIFTY50_MEMBER,),
            (AnchorEligibilityReasonV1.ANCHOR_NOT_OFFICIAL_SESSION,),
        )
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


FIVE_SESSION_OUTCOME_POLICY_VERSION_V1: Final = "next-open-fifth-close-gross@v1"
_PRICE = re.compile(r"(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,12})?\Z")


class FiveSessionOutcomeStateV1(StrEnum):
    OBSERVED = "OBSERVED"
    NON_FILL = "NON_FILL"
    INCOMPLETE_HORIZON = "INCOMPLETE_HORIZON"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    AMBIGUOUS = "AMBIGUOUS"


class FiveSessionOutcomeReasonV1(StrEnum):
    NONE = "NONE"
    EXACT_NEXT_OPEN_MISSING = "EXACT_NEXT_OPEN_MISSING"
    FIVE_COMPLETED_SESSIONS_UNAVAILABLE = "FIVE_COMPLETED_SESSIONS_UNAVAILABLE"
    SESSION_EVIDENCE_INCOMPLETE = "SESSION_EVIDENCE_INCOMPLETE"
    RAW_CORPORATE_ACTION_WINDOW_AMBIGUOUS = "RAW_CORPORATE_ACTION_WINDOW_AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class OutcomeSessionFactV1:
    session: OfficialSessionV1
    known_at: datetime
    exact_open_text: str | None
    exact_terminal_close_text: str | None
    complete: bool
    evidence_digest_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.session) is not OfficialSessionV1
            or type(self.known_at) is not datetime
            or type(self.complete) is not bool
            or type(self.evidence_digest_sha256) is not str
            or _DIGEST.fullmatch(self.evidence_digest_sha256) is None
            or not _valid_optional_price(self.exact_open_text)
            or not _valid_optional_price(self.exact_terminal_close_text)
        ):
            raise ValueError("invalid outcome session fact")
        object.__setattr__(self, "known_at", _utc(self.known_at, "known_at"))


@dataclass(frozen=True, slots=True)
class FiveSessionOutcomeRequestV1:
    eligible_anchor: AnchorEligibilityObservationV1
    observation_cutoff: datetime
    expected_sessions: tuple[OfficialSessionV1, ...]
    authoritative_schedule_digest_sha256: str
    authoritative_schedule_known_at: datetime
    policy_version: str = FIVE_SESSION_OUTCOME_POLICY_VERSION_V1
    horizon_sessions: int = 5
    threshold_decimal: str = "0.02"

    def __post_init__(self) -> None:
        if (
            type(self.eligible_anchor) is not AnchorEligibilityObservationV1
            or self.eligible_anchor.status is not AnchorEligibilityStatusV1.ELIGIBLE
            or type(self.observation_cutoff) is not datetime
            or self.policy_version != FIVE_SESSION_OUTCOME_POLICY_VERSION_V1
            or self.horizon_sessions != 5
            or self.threshold_decimal != "0.02"
            or type(self.expected_sessions) is not tuple
            or len(self.expected_sessions) != 5
            or type(self.authoritative_schedule_digest_sha256) is not str
            or _DIGEST.fullmatch(self.authoritative_schedule_digest_sha256) is None
            or type(self.authoritative_schedule_known_at) is not datetime
            or any(
                type(item) is not OfficialSessionV1 for item in self.expected_sessions
            )
            or tuple(item.trade_date for item in self.expected_sessions)
            != tuple(sorted({item.trade_date for item in self.expected_sessions}))
            or any(
                item.trade_date <= self.eligible_anchor.decision_session.trade_date
                for item in self.expected_sessions
            )
        ):
            raise ValueError("outcome request requires eligible anchor")
        cutoff = _utc(self.observation_cutoff, "observation_cutoff")
        schedule_known_at = _utc(
            self.authoritative_schedule_known_at, "authoritative_schedule_known_at"
        )
        if cutoff <= self.eligible_anchor.decision_cutoff or schedule_known_at > cutoff:
            raise ValueError("invalid outcome observation cutoff")
        object.__setattr__(self, "observation_cutoff", cutoff)
        object.__setattr__(self, "authoritative_schedule_known_at", schedule_known_at)


@dataclass(frozen=True, slots=True)
class FiveSessionOutcomeEvidenceV1:
    sessions: tuple[OutcomeSessionFactV1, ...]
    raw_corporate_action_in_window: bool
    corporate_action_evidence_digest_sha256: str
    corporate_action_evidence_known_at: datetime
    authoritative_schedule_digest_sha256: str

    def __post_init__(self) -> None:
        dates = tuple(item.session.trade_date for item in self.sessions)
        if (
            type(self.sessions) is not tuple
            or len(self.sessions) > 5
            or any(type(item) is not OutcomeSessionFactV1 for item in self.sessions)
            or dates != tuple(sorted(set(dates)))
            or type(self.raw_corporate_action_in_window) is not bool
            or type(self.corporate_action_evidence_digest_sha256) is not str
            or type(self.corporate_action_evidence_known_at) is not datetime
            or _DIGEST.fullmatch(self.corporate_action_evidence_digest_sha256) is None
            or type(self.authoritative_schedule_digest_sha256) is not str
            or _DIGEST.fullmatch(self.authoritative_schedule_digest_sha256) is None
        ):
            raise ValueError("invalid outcome evidence")
        object.__setattr__(
            self,
            "corporate_action_evidence_known_at",
            _utc(
                self.corporate_action_evidence_known_at,
                "corporate_action_evidence_known_at",
            ),
        )

    def digest_sha256(self) -> str:
        return hashlib.sha256(
            _canonical_bytes(_outcome_evidence_value(self))
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class FiveSessionOutcomeObservationV1:
    state: FiveSessionOutcomeStateV1
    reason: FiveSessionOutcomeReasonV1
    anchor_observation_sha256: str
    evidence_digest_sha256: str
    entry_trade_date: date | None
    entry_at: datetime | None
    exit_trade_date: date | None
    exit_at: datetime | None
    gross_return_percent: str | None
    strictly_gt_2_percent: bool | None
    policy_version: str = FIVE_SESSION_OUTCOME_POLICY_VERSION_V1

    def __post_init__(self) -> None:
        observed = self.state is FiveSessionOutcomeStateV1.OBSERVED
        if (
            type(self.state) is not FiveSessionOutcomeStateV1
            or type(self.reason) is not FiveSessionOutcomeReasonV1
            or not _valid_outcome_state_reason(self.state, self.reason)
            or any(
                type(value) is not str or _DIGEST.fullmatch(value) is None
                for value in (
                    self.anchor_observation_sha256,
                    self.evidence_digest_sha256,
                )
            )
            or self.policy_version != FIVE_SESSION_OUTCOME_POLICY_VERSION_V1
            or observed
            != (
                type(self.entry_trade_date) is date
                and type(self.entry_at) is datetime
                and type(self.exit_trade_date) is date
                and type(self.exit_at) is datetime
                and type(self.gross_return_percent) is str
                and type(self.strictly_gt_2_percent) is bool
            )
        ):
            raise ValueError("invalid outcome observation")

    def canonical_json_bytes(self) -> bytes:
        return _canonical_bytes(
            {
                "anchor_observation_sha256": self.anchor_observation_sha256,
                "entry_at": None
                if self.entry_at is None
                else _timestamp(self.entry_at),
                "entry_trade_date": None
                if self.entry_trade_date is None
                else self.entry_trade_date.isoformat(),
                "evidence_digest_sha256": self.evidence_digest_sha256,
                "exit_at": None if self.exit_at is None else _timestamp(self.exit_at),
                "exit_trade_date": None
                if self.exit_trade_date is None
                else self.exit_trade_date.isoformat(),
                "gross_return_percent": self.gross_return_percent,
                "policy_version": self.policy_version,
                "reason": self.reason.value,
                "state": self.state.value,
                "strictly_gt_2_percent": self.strictly_gt_2_percent,
            }
        )

    @property
    def observation_identity_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json_bytes()).hexdigest()


def _valid_outcome_state_reason(
    state: FiveSessionOutcomeStateV1, reason: FiveSessionOutcomeReasonV1
) -> bool:
    return (state, reason) in {
        (FiveSessionOutcomeStateV1.OBSERVED, FiveSessionOutcomeReasonV1.NONE),
        (
            FiveSessionOutcomeStateV1.NON_FILL,
            FiveSessionOutcomeReasonV1.EXACT_NEXT_OPEN_MISSING,
        ),
        (
            FiveSessionOutcomeStateV1.INCOMPLETE_HORIZON,
            FiveSessionOutcomeReasonV1.FIVE_COMPLETED_SESSIONS_UNAVAILABLE,
        ),
        (
            FiveSessionOutcomeStateV1.INSUFFICIENT_EVIDENCE,
            FiveSessionOutcomeReasonV1.SESSION_EVIDENCE_INCOMPLETE,
        ),
        (
            FiveSessionOutcomeStateV1.AMBIGUOUS,
            FiveSessionOutcomeReasonV1.RAW_CORPORATE_ACTION_WINDOW_AMBIGUOUS,
        ),
    }


def calculate_five_session_outcome_v1(
    request: FiveSessionOutcomeRequestV1,
    evidence: FiveSessionOutcomeEvidenceV1,
) -> FiveSessionOutcomeObservationV1:
    if (
        type(request) is not FiveSessionOutcomeRequestV1
        or type(evidence) is not FiveSessionOutcomeEvidenceV1
    ):
        raise ValueError("invalid outcome calculator input")
    if (
        tuple(item.session for item in evidence.sessions)
        != request.expected_sessions[: len(evidence.sessions)]
        or any(
            item.session.close_at > request.observation_cutoff
            for item in evidence.sessions
        )
        or any(item.known_at > request.observation_cutoff for item in evidence.sessions)
        or evidence.corporate_action_evidence_known_at > request.observation_cutoff
        or evidence.authoritative_schedule_digest_sha256
        != request.authoritative_schedule_digest_sha256
    ):
        raise ValueError("invalid outcome evidence")
    anchor_digest = request.eligible_anchor.observation_digest_sha256
    evidence_digest = evidence.digest_sha256()
    if len(evidence.sessions) < 5:
        return _terminal_outcome(
            FiveSessionOutcomeStateV1.INCOMPLETE_HORIZON,
            FiveSessionOutcomeReasonV1.FIVE_COMPLETED_SESSIONS_UNAVAILABLE,
            anchor_digest,
            evidence_digest,
        )
    if any(not item.complete for item in evidence.sessions):
        return _terminal_outcome(
            FiveSessionOutcomeStateV1.INSUFFICIENT_EVIDENCE,
            FiveSessionOutcomeReasonV1.SESSION_EVIDENCE_INCOMPLETE,
            anchor_digest,
            evidence_digest,
        )
    first, last = evidence.sessions[0], evidence.sessions[-1]
    if first.exact_open_text is None:
        return _terminal_outcome(
            FiveSessionOutcomeStateV1.NON_FILL,
            FiveSessionOutcomeReasonV1.EXACT_NEXT_OPEN_MISSING,
            anchor_digest,
            evidence_digest,
        )
    if last.exact_terminal_close_text is None:
        return _terminal_outcome(
            FiveSessionOutcomeStateV1.INSUFFICIENT_EVIDENCE,
            FiveSessionOutcomeReasonV1.SESSION_EVIDENCE_INCOMPLETE,
            anchor_digest,
            evidence_digest,
        )
    if evidence.raw_corporate_action_in_window:
        return _terminal_outcome(
            FiveSessionOutcomeStateV1.AMBIGUOUS,
            FiveSessionOutcomeReasonV1.RAW_CORPORATE_ACTION_WINDOW_AMBIGUOUS,
            anchor_digest,
            evidence_digest,
        )
    entry = Decimal(first.exact_open_text)
    exit_value = Decimal(last.exact_terminal_close_text)
    percent = ((exit_value / entry - Decimal(1)) * Decimal(100)).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_EVEN
    )
    rendered = format(percent, ".6f")
    return FiveSessionOutcomeObservationV1(
        FiveSessionOutcomeStateV1.OBSERVED,
        FiveSessionOutcomeReasonV1.NONE,
        anchor_digest,
        evidence_digest,
        first.session.trade_date,
        first.session.open_at,
        last.session.trade_date,
        last.session.close_at - timedelta(minutes=1),
        rendered,
        exit_value * Decimal(100) > entry * Decimal(102),
    )


def _terminal_outcome(
    state: FiveSessionOutcomeStateV1,
    reason: FiveSessionOutcomeReasonV1,
    anchor_digest: str,
    evidence_digest: str,
) -> FiveSessionOutcomeObservationV1:
    return FiveSessionOutcomeObservationV1(
        state,
        reason,
        anchor_digest,
        evidence_digest,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def _valid_optional_price(value: object) -> bool:
    if value is None:
        return True
    if type(value) is not str or _PRICE.fullmatch(value) is None:
        return False
    return Decimal(value) > 0


def _outcome_evidence_value(value: FiveSessionOutcomeEvidenceV1) -> dict[str, object]:
    return {
        "corporate_action_evidence_digest_sha256": value.corporate_action_evidence_digest_sha256,
        "corporate_action_evidence_known_at": _timestamp(
            value.corporate_action_evidence_known_at
        ),
        "raw_corporate_action_in_window": value.raw_corporate_action_in_window,
        "authoritative_schedule_digest_sha256": value.authoritative_schedule_digest_sha256,
        "sessions": [
            {
                "complete": item.complete,
                "evidence_digest_sha256": item.evidence_digest_sha256,
                "exact_open_text": item.exact_open_text,
                "known_at": _timestamp(item.known_at),
                "exact_terminal_close_text": item.exact_terminal_close_text,
                "session": _session_value(item.session),
            }
            for item in value.sessions
        ],
    }
