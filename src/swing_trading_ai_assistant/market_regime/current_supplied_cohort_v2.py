"""Pure V2 comparability gate for current supplied-cohort Market Regime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final, Literal

from swing_trading_ai_assistant.market_data.adjusted_daily import (
    AdjustedCloseFact,
    AdjustedDailyCloseHandoffV2,
    AdjustedDailyMemberFactsV2,
)
from swing_trading_ai_assistant.market_data.current_corporate_action_screen import (
    AggregateMemberOutcomeV1,
    PrivateCorporateActionScreenOutcomeV1,
    PrivateCorporateActionScreenResultV1,
    ProviderObservationOutcomeV1,
)

from .current_supplied_cohort import (
    CurrentCohortMemberV1,
    CurrentSuppliedCohortMarketRegimeReportV1,
    PrivateCurrentCohortArchiveGridProjectionV1,
    PrivateCurrentCohortMemberCloseProjectionV1,
)

CONTRACT_VERSION: Final = "current-supplied-cohort-market-regime@v2"


@dataclass(frozen=True, slots=True)
class CurrentSuppliedCohortMarketRegimeReportV2:
    """Aggregate-only result; private members never cross this boundary."""

    contract_version: Literal["current-supplied-cohort-market-regime@v2"]
    raw_report_identity_sha256: str
    corporate_action_screen_identity_sha256: str
    cohort_identity_sha256: str
    cohort_size: int
    decision_cutoff: datetime
    decision_session: date
    comparison_session: date | None
    evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
    regime_label: str | None
    advances: int | None
    declines: int | None
    unchanged: int | None
    reasons: tuple[str, ...]

    def value(self) -> dict[str, object]:
        """Return the redacted, aggregate-only public representation."""
        return {
            "contract_version": self.contract_version,
            "raw_report_identity_sha256": self.raw_report_identity_sha256,
            "corporate_action_screen_identity_sha256": (
                self.corporate_action_screen_identity_sha256
            ),
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "cohort_size": self.cohort_size,
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "decision_session": self.decision_session.isoformat(),
            "comparison_session": (
                None
                if self.comparison_session is None
                else self.comparison_session.isoformat()
            ),
            "evidence_state": self.evidence_state,
            "regime_label": self.regime_label,
            "advances": self.advances,
            "declines": self.declines,
            "unchanged": self.unchanged,
            "reasons": list(self.reasons),
        }


def evaluate_current_supplied_cohort_market_regime_v2(
    raw_v1_report: CurrentSuppliedCohortMarketRegimeReportV1,
    raw_private_grid: PrivateCurrentCohortArchiveGridProjectionV1,
    retained_screen: PrivateCorporateActionScreenResultV1,
    adjusted_handoff: AdjustedDailyCloseHandoffV2,
) -> CurrentSuppliedCohortMarketRegimeReportV2:
    """Preserve V1 breadth only when every sealed source agrees on direction.

    The function intentionally receives evidence only.  It does not call a
    provider, open storage, consult the clock, or retain any input.
    """
    raw_identity = (
        raw_v1_report.report_identity_sha256
        if type(raw_v1_report) is CurrentSuppliedCohortMarketRegimeReportV1
        else ""
    )
    screen_identity = (
        retained_screen.private_result_identity_sha256
        if type(retained_screen) is PrivateCorporateActionScreenResultV1
        else ""
    )
    if not _valid_raw_report_and_grid(raw_v1_report, raw_private_grid):
        return _insufficient(
            raw_v1_report, raw_identity, screen_identity, "RAW_V1_CLOSURE_INVALID"
        )
    if not _valid_screen(raw_v1_report, raw_private_grid, retained_screen):
        return _insufficient(
            raw_v1_report,
            raw_identity,
            screen_identity,
            "CORPORATE_ACTION_SCREEN_INSUFFICIENT",
        )
    if not _valid_adjusted_handoff(raw_v1_report, raw_private_grid, adjusted_handoff):
        return _insufficient(
            raw_v1_report,
            raw_identity,
            screen_identity,
            "ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID",
        )

    raw_directions = _directions(
        raw_private_grid.sessions[0].members,
        raw_private_grid.sessions[-1].members,
    )
    adjusted_directions = _adjusted_directions(adjusted_handoff.members)
    if raw_directions != adjusted_directions:
        return _insufficient(
            raw_v1_report,
            raw_identity,
            screen_identity,
            "RAW_ADJUSTED_DIRECTION_CONFLICT",
        )

    return CurrentSuppliedCohortMarketRegimeReportV2(
        contract_version=CONTRACT_VERSION,
        raw_report_identity_sha256=raw_identity,
        corporate_action_screen_identity_sha256=screen_identity,
        cohort_identity_sha256=raw_v1_report.cohort_identity_sha256,
        cohort_size=raw_v1_report.cohort_size,
        decision_cutoff=raw_v1_report.decision_cutoff,
        decision_session=raw_v1_report.decision_session,
        comparison_session=raw_v1_report.comparison_session,
        evidence_state="OBSERVED",
        regime_label=raw_v1_report.regime_label,
        advances=raw_v1_report.advances,
        declines=raw_v1_report.declines,
        unchanged=raw_v1_report.unchanged,
        reasons=(),
    )


def _insufficient(
    raw_report: object, raw_identity: str, screen_identity: str, reason: str
) -> CurrentSuppliedCohortMarketRegimeReportV2:
    """Build a whole-result failure with only a validated raw denominator."""
    if type(raw_report) is CurrentSuppliedCohortMarketRegimeReportV1:
        cohort_identity = raw_report.cohort_identity_sha256
        cohort_size = raw_report.cohort_size
        decision_cutoff = raw_report.decision_cutoff
        decision_session = raw_report.decision_session
    else:
        cohort_identity = ""
        cohort_size = 0
        decision_cutoff = datetime.min.replace(tzinfo=UTC)
        decision_session = date.min
    return CurrentSuppliedCohortMarketRegimeReportV2(
        contract_version=CONTRACT_VERSION,
        raw_report_identity_sha256=raw_identity,
        corporate_action_screen_identity_sha256=screen_identity,
        cohort_identity_sha256=cohort_identity,
        cohort_size=cohort_size,
        decision_cutoff=decision_cutoff,
        decision_session=decision_session,
        comparison_session=None,
        evidence_state="INSUFFICIENT_EVIDENCE",
        regime_label=None,
        advances=None,
        declines=None,
        unchanged=None,
        reasons=(reason,),
    )


def _valid_raw_report_and_grid(report: object, grid: object) -> bool:
    if (
        type(report) is not CurrentSuppliedCohortMarketRegimeReportV1
        or type(grid) is not PrivateCurrentCohortArchiveGridProjectionV1
        or report.contract_version != "current-supplied-cohort-market-regime@v1"
        or report.evidence_state != "OBSERVED"
        or report.reasons
        or report.comparison_session is None
        or report.regime_label
        not in {"BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"}
        or None in (report.advances, report.declines, report.unchanged)
        or grid.cohort_identity_sha256 != report.cohort_identity_sha256
        or grid.cohort_size != report.cohort_size
        or len(grid.sessions) != 21
        or grid.sessions[0].session != report.comparison_session
        or grid.sessions[-1].session != report.decision_session
        or tuple(session.session for session in grid.sessions)
        != tuple(sorted(session.session for session in grid.sessions))
        or len({session.session for session in grid.sessions}) != 21
        or tuple(session.archive_object_sha256 for session in grid.sessions)
        != report.archive_object_sha256s
        or any(
            session.request_identity_sha256 != report.request_identity_sha256
            or session.report_identity_sha256 != report.report_identity_sha256
            for session in grid.sessions
        )
    ):
        return False
    members = tuple(member.member for member in grid.sessions[0].members)
    if len(members) != report.cohort_size or len(set(members)) != report.cohort_size:
        return False
    if any(
        tuple(member.member for member in session.members) != members
        for session in grid.sessions
    ):
        return False
    directions = _directions(grid.sessions[0].members, grid.sessions[-1].members)
    advances = directions.count("UP")
    declines = directions.count("DOWN")
    unchanged = directions.count("FLAT")
    label = (
        "BROAD_ADVANCE"
        if advances * 5 >= report.cohort_size * 3
        else "BROAD_DECLINE"
        if declines * 5 >= report.cohort_size * 3
        else "MIXED_PARTICIPATION"
    )
    return (advances, declines, unchanged, label) == (
        report.advances,
        report.declines,
        report.unchanged,
        report.regime_label,
    )


def _valid_screen(
    report: CurrentSuppliedCohortMarketRegimeReportV1,
    grid: PrivateCurrentCohortArchiveGridProjectionV1,
    screen: object,
) -> bool:
    if (
        type(screen) is not PrivateCorporateActionScreenResultV1
        or screen.contract_version
        != "current-supplied-cohort-corporate-action-screen@v1"
        or screen.outcome
        != PrivateCorporateActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
        or screen.selected_snapshot_set_identity_sha256 is None
        or screen.cohort_identity_sha256 != report.cohort_identity_sha256
        or screen.comparison_session != report.comparison_session
        or screen.decision_session != report.decision_session
        or screen.decision_cutoff != report.decision_cutoff
        or screen.schedule_evidence_sha256 != report.schedule_evidence_sha256
        or screen.schedule_source != report.schedule_source
        or screen.schedule_source_release != report.schedule_source_release
        or len(screen.member_results) != report.cohort_size
    ):
        return False
    raw_isins = {member.member.isin for member in grid.sessions[0].members}
    screen_isins = tuple(
        result.provider_result.isin for result in screen.member_results
    )
    return (
        len(set(screen_isins)) == report.cohort_size
        and set(screen_isins) == raw_isins
        and all(
            result.row_outcome
            == AggregateMemberOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
            and result.provider_result.outcome == ProviderObservationOutcomeV1.AVAILABLE
            and result.provider_result.snapshot_identity_sha256 is not None
            and result.provider_result.snapshot_byte_count is not None
            and result.provider_result.retrieved_at is not None
            and not result.provider_result.normalized_supported_events
            for result in screen.member_results
        )
    )


def _valid_adjusted_handoff(
    report: CurrentSuppliedCohortMarketRegimeReportV1,
    grid: PrivateCurrentCohortArchiveGridProjectionV1,
    handoff: object,
) -> bool:
    if (
        type(handoff) is not AdjustedDailyCloseHandoffV2
        or handoff.contract_version != "provider-neutral-adjusted-daily-close@v2"
        or handoff.provider_id != "YFINANCE"
        or handoff.price_basis != "ADJUSTED"
        or not handoff.provider_source
        or handoff.temporal_label != "CURRENT_PROSPECTIVE"
        or handoff.decision_cutoff != report.decision_cutoff
        or handoff.retrieved_at.tzinfo is not UTC
        or handoff.retrieved_at > report.decision_cutoff
        or handoff.comparison_session != report.comparison_session
        or handoff.decision_session != report.decision_session
        or len(handoff.members) != report.cohort_size
    ):
        return False
    raw_members = tuple(member.member for member in grid.sessions[0].members)
    adjusted_members = handoff.members
    if (
        tuple(member.isin for member in adjusted_members)
        != tuple(member.isin for member in raw_members)
        or len({member.isin for member in adjusted_members}) != report.cohort_size
    ):
        return False
    return all(
        _valid_adjusted_member(
            member, raw_member, report.comparison_session, report.decision_session
        )
        for member, raw_member in zip(adjusted_members, raw_members, strict=True)
    )


def _valid_adjusted_member(
    member: AdjustedDailyMemberFactsV2,
    raw_member: CurrentCohortMemberV1,
    comparison_session: date | None,
    decision_session: date,
) -> bool:
    if comparison_session is None:
        return False
    if (
        type(member) is not AdjustedDailyMemberFactsV2
        or member.effective_symbol != raw_member.symbol
        or member.exchange not in {"NSE", "BSE"}
        or member.instrument_type != "EQUITY"
        or member.segment != "EQ"
        or member.mapping_version != "yfinance-symbol-mapping@v1"
        or len(member.mapping_identity) != 64
        or member.valid_from > comparison_session
        or member.valid_through is not None
        and member.valid_through < decision_session
        or member.mapping_valid_from > comparison_session
        or member.mapping_valid_through is not None
        and member.mapping_valid_through < decision_session
        or not _valid_adjusted_close(member.s0, comparison_session)
        or not _valid_adjusted_close(member.s20, decision_session)
    ):
        return False
    return all(character in "0123456789abcdef" for character in member.mapping_identity)


def _valid_adjusted_close(fact: object, session: date) -> bool:
    return (
        type(fact) is AdjustedCloseFact
        and fact.session == session
        and type(fact.adjusted_close) is Decimal
        and fact.adjusted_close.is_finite()
        and fact.adjusted_close > 0
    )


def _directions(
    prior_members: tuple[PrivateCurrentCohortMemberCloseProjectionV1, ...],
    current_members: tuple[PrivateCurrentCohortMemberCloseProjectionV1, ...],
) -> tuple[str, ...]:
    return tuple(
        "UP"
        if current.close > prior.close
        else "DOWN"
        if current.close < prior.close
        else "FLAT"
        for prior, current in zip(prior_members, current_members, strict=True)
    )


def _adjusted_directions(
    members: tuple[AdjustedDailyMemberFactsV2, ...],
) -> tuple[str, ...]:
    return tuple(
        "UP"
        if member.s20.adjusted_close > member.s0.adjusted_close
        else "DOWN"
        if member.s20.adjusted_close < member.s0.adjusted_close
        else "FLAT"
        for member in members
    )
