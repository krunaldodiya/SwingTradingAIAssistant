"""Pure observed reduction for the frozen Market Regime V1 rule.

The reducer accepts only the complete, immutable verified fact graph.  It performs
no acquisition, I/O, time, calendar, random, storage, or provider operation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from .boundary import (
    canonical_json_lf,
    parse_canonical_json_lf,
    validate_canonical_decimal,
    validate_local_date,
    validate_sha256,
    validate_utc_instant,
)
from .facts import (
    VerifiedMarketRegimeFactsV1,
    validate_verified_market_regime_facts_v1,
)

__all__ = [
    "MarketRegimeLabelV1",
    "MarketRegimeReportV1",
    "reduce_observed_market_regime_v1",
]


class MarketRegimeLabelV1(StrEnum):
    """The closed observed label set."""

    BROAD_ADVANCE = "BROAD_ADVANCE"
    BROAD_DECLINE = "BROAD_DECLINE"
    MIXED_PARTICIPATION = "MIXED_PARTICIPATION"


def _label(advances: int, declines: int) -> MarketRegimeLabelV1:
    if advances >= 30:
        return MarketRegimeLabelV1.BROAD_ADVANCE
    if declines >= 30:
        return MarketRegimeLabelV1.BROAD_DECLINE
    return MarketRegimeLabelV1.MIXED_PARTICIPATION


@dataclass(frozen=True, slots=True)
class MarketRegimeReportV1:
    """Canonical aggregate-only public Market Regime report."""

    contract_version: str
    calculation_version: str
    request_identity_sha256: str
    input_identity_sha256: str
    source_policy_identity_sha256: str
    validation_policy_identity_sha256: str
    policy_identity_sha256: str
    code_identity_sha256: str
    decision_session: str
    comparison_session: str
    decision_market_close: str
    evidence_cutoff: str
    lookback_official_sessions: int
    required_member_count: int
    threshold_count: int
    evidence_state: str
    regime_label: MarketRegimeLabelV1
    advances: int
    declines: int
    unchanged: int
    primary_reason: None
    additional_reasons: tuple[()]
    report_identity_sha256: str

    _FIELDS = frozenset(
        {
            "contract_version",
            "calculation_version",
            "request_identity_sha256",
            "input_identity_sha256",
            "source_policy_identity_sha256",
            "validation_policy_identity_sha256",
            "policy_identity_sha256",
            "code_identity_sha256",
            "decision_session",
            "comparison_session",
            "decision_market_close",
            "evidence_cutoff",
            "lookback_official_sessions",
            "required_member_count",
            "threshold_count",
            "evidence_state",
            "regime_label",
            "advances",
            "declines",
            "unchanged",
            "primary_reason",
            "additional_reasons",
            "report_identity_sha256",
        }
    )

    def __post_init__(self) -> None:
        if (
            self.contract_version != "nifty50-market-regime@v1"
            or self.calculation_version != "nifty50-market-regime-classifier@v1"
            or self.lookback_official_sessions != 20
            or self.required_member_count != 50
            or self.threshold_count != 30
            or self.evidence_state != "OBSERVED"
        ):
            raise ValueError("invalid observed report constants")
        for identity in (
            self.request_identity_sha256,
            self.input_identity_sha256,
            self.source_policy_identity_sha256,
            self.validation_policy_identity_sha256,
            self.policy_identity_sha256,
            self.code_identity_sha256,
            self.report_identity_sha256,
        ):
            validate_sha256(identity)
        validate_local_date(self.decision_session)
        validate_local_date(self.comparison_session)
        validate_utc_instant(self.decision_market_close)
        validate_utc_instant(self.evidence_cutoff)
        if self.decision_market_close >= self.evidence_cutoff:
            raise ValueError("decision close must precede evidence cutoff")
        if not isinstance(self.regime_label, MarketRegimeLabelV1):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("regime label must be closed")
        counts = (self.advances, self.declines, self.unchanged)
        if any(type(value) is not int or not 0 <= value <= 50 for value in counts):
            raise ValueError("observed counts must be integers in [0, 50]")
        if sum(counts) != 50 or self.regime_label is not _label(
            self.advances, self.declines
        ):
            raise ValueError("observed counts and label are inconsistent")
        if self.primary_reason is not None or self.additional_reasons != ():
            raise ValueError("observed report cannot carry insufficiency reasons")
        expected_identity = hashlib.sha256(
            canonical_json_lf(self._identity_projection())
        ).hexdigest()
        if self.report_identity_sha256 != expected_identity:
            raise ValueError("report identity mismatch")

    def _identity_projection(self) -> dict[str, object]:
        return {
            "additional_reasons": [],
            "advances": self.advances,
            "calculation_version": self.calculation_version,
            "code_identity_sha256": self.code_identity_sha256,
            "comparison_session": self.comparison_session,
            "contract_version": self.contract_version,
            "decision_market_close": self.decision_market_close,
            "decision_session": self.decision_session,
            "declines": self.declines,
            "evidence_cutoff": self.evidence_cutoff,
            "evidence_state": self.evidence_state,
            "input_identity_sha256": self.input_identity_sha256,
            "lookback_official_sessions": self.lookback_official_sessions,
            "policy_identity_sha256": self.policy_identity_sha256,
            "primary_reason": None,
            "regime_label": self.regime_label,
            "request_identity_sha256": self.request_identity_sha256,
            "required_member_count": self.required_member_count,
            "source_policy_identity_sha256": self.source_policy_identity_sha256,
            "threshold_count": self.threshold_count,
            "unchanged": self.unchanged,
            "validation_policy_identity_sha256": self.validation_policy_identity_sha256,
        }

    @classmethod
    def observed(
        cls,
        facts: VerifiedMarketRegimeFactsV1,
        advances: int,
        declines: int,
        unchanged: int,
    ) -> MarketRegimeReportV1:
        sessions = facts.schedule.sessions
        values: dict[str, object] = {
            "contract_version": "nifty50-market-regime@v1",
            "calculation_version": "nifty50-market-regime-classifier@v1",
            "request_identity_sha256": facts.request.request_identity_sha256,
            "input_identity_sha256": facts.input_identity_sha256,
            "source_policy_identity_sha256": facts.source_policy_identity_sha256,
            "validation_policy_identity_sha256": facts.validation_policy_identity_sha256,
            "policy_identity_sha256": facts.policy_identity_sha256,
            "code_identity_sha256": facts.code_identity_sha256,
            "decision_session": facts.request.decision_session,
            "comparison_session": sessions[0].session_date,
            "decision_market_close": sessions[20].close_at,
            "evidence_cutoff": sessions[21].open_at,
            "lookback_official_sessions": 20,
            "required_member_count": 50,
            "threshold_count": 30,
            "evidence_state": "OBSERVED",
            "regime_label": _label(advances, declines),
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "primary_reason": None,
            "additional_reasons": (),
        }
        identity = hashlib.sha256(canonical_json_lf(values)).hexdigest()
        return cls(**values, report_identity_sha256=identity)  # type: ignore[arg-type]

    def canonical_json_bytes(self) -> bytes:
        raw = canonical_json_lf(self)
        if len(raw) > 65_536:
            raise ValueError("public report exceeds 64 KiB")
        return raw

    @classmethod
    def verify_identity(cls, raw: object) -> bool:
        """Parse and semantically verify one closed canonical public report."""
        if type(raw) is not bytes:
            return False
        try:
            value = parse_canonical_json_lf(raw, max_bytes=65_536)
            if not isinstance(value, dict):
                return False
            fields = cast("dict[str, object]", value)
            if set(fields) != set(cls._FIELDS):
                return False
            label_value = fields["regime_label"]
            reasons_value = fields["additional_reasons"]
            if not isinstance(label_value, str) or not isinstance(reasons_value, list):
                return False
            if reasons_value:
                return False
            normalized = dict(fields)
            normalized["regime_label"] = MarketRegimeLabelV1(label_value)
            normalized["additional_reasons"] = ()
            cls(**normalized)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        return True


def reduce_observed_market_regime_v1(
    facts: object,
) -> MarketRegimeReportV1:
    """Reduce one complete verified fact graph with exact Decimal comparisons."""
    if not isinstance(facts, VerifiedMarketRegimeFactsV1):
        raise TypeError("observed reduction requires VerifiedMarketRegimeFactsV1")
    validate_verified_market_regime_facts_v1(facts)
    sessions = facts.schedule.sessions
    prior = facts.prior_closes
    current = facts.current_closes
    comparability = facts.comparability
    members = facts.membership.members
    if (
        len(sessions) != 22
        or len(members) != 50
        or len(prior) != 50
        or len(current) != 50
        or len(comparability) != 50
    ):
        raise ValueError("observed reduction requires exact 22/50 cardinalities")
    if (
        sessions[20].session_date != facts.request.decision_session
        or facts.membership.decision_session != facts.request.decision_session
        or sessions[20].close_at >= sessions[21].open_at
    ):
        raise ValueError("verified endpoint equations are inconsistent")
    member_isins = tuple(member.isin for member in members)
    prior_isins = tuple(close.isin for close in prior)
    current_isins = tuple(close.isin for close in current)
    comparable_isins = tuple(item.isin for item in comparability)
    if not (
        member_isins == prior_isins == current_isins == comparable_isins
        and len(set(member_isins)) == 50
    ):
        raise ValueError("verified member equations are inconsistent")

    advances = declines = unchanged = 0
    for prior_close, current_close in zip(prior, current, strict=True):
        if (
            prior_close.session_date != sessions[0].session_date
            or current_close.session_date != sessions[20].session_date
            or prior_close.market_scope_ends_at != sessions[0].close_at
            or current_close.market_scope_ends_at != sessions[20].close_at
        ):
            raise ValueError("verified close endpoint is inconsistent")
        prior_value = validate_canonical_decimal(prior_close.close)
        current_value = validate_canonical_decimal(current_close.close)
        if current_value > prior_value:
            advances += 1
        elif current_value < prior_value:
            declines += 1
        else:
            unchanged += 1

    return MarketRegimeReportV1.observed(facts, advances, declines, unchanged)
