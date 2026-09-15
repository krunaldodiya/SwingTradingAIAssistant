"""Aggregate-only literal-Industry participation over jointly admitted evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from swing_trading_ai_assistant.market_data.current_industry_archive_reader import (
    AdmittedCurrentIndustryProjectionV1,
    admitted_current_industry_binding_v1,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    AdmittedCurrentRawContextV1,
    admitted_current_raw_context_binding_v1,
)


@dataclass(frozen=True, slots=True)
class CurrentRawIndustryGroupV1:
    industry: str
    member_count: int
    advances: int
    declines: int
    unchanged: int

    def __post_init__(self) -> None:
        if (
            type(self.industry) is not str
            or not self.industry
            or type(self.member_count) is not int
            or not 1 <= self.member_count <= 50
            or any(
                type(value) is not int or value < 0
                for value in (self.advances, self.declines, self.unchanged)
            )
            or self.advances + self.declines + self.unchanged != self.member_count
        ):
            raise ValueError("raw Industry group is invalid")


@dataclass(frozen=True, slots=True)
class CurrentRawIndustryParticipationV1:
    evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
    requested_count: int
    groups: tuple[CurrentRawIndustryGroupV1, ...]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        observed = self.evidence_state == "OBSERVED"
        if (
            type(self.requested_count) is not int
            or not 1 <= self.requested_count <= 50
            or type(self.groups) is not tuple
            or any(
                type(group) is not CurrentRawIndustryGroupV1 for group in self.groups
            )
            or tuple(group.industry for group in self.groups)
            != tuple(sorted(group.industry for group in self.groups))
            or len({group.industry for group in self.groups}) != len(self.groups)
            or (
                observed
                and (
                    not self.groups
                    or self.reasons
                    or sum(group.member_count for group in self.groups)
                    != self.requested_count
                )
            )
            or (not observed and (self.groups or not self.reasons))
        ):
            raise ValueError("raw Industry participation is invalid")


def reduce_current_raw_industry_participation_v1(
    raw: AdmittedCurrentRawContextV1,
    classification: AdmittedCurrentIndustryProjectionV1,
) -> CurrentRawIndustryParticipationV1:
    """Join one exact raw capability with its reader-bound Industry capability."""
    raw_projection, raw_root = admitted_current_raw_context_binding_v1(raw)
    industry, industry_root, bound_raw_id = admitted_current_industry_binding_v1(
        classification
    )
    if (
        bound_raw_id != id(raw)
        or industry_root != raw_root
        or industry.raw_input_identity_sha256 != raw_projection.input_identity_sha256
        or industry.raw_request_identity_sha256
        != raw_projection.request_identity_sha256
        or industry.ordered_selection_identity_sha256
        != raw_projection.ordered_selection_identity_sha256
        or industry.canonical_cohort_identity_sha256
        != raw_projection.canonical_cohort_identity_sha256
        or industry.comparison_session != raw_projection.sessions[0].session
        or industry.decision_session != raw_projection.sessions[-1].session
        or industry.evidence_cutoff != raw_projection.evidence_cutoff
    ):
        raise ValueError("raw Industry participation binding is invalid")
    members = tuple(
        (member.isin, member.exchange, member.effective_symbol)
        for member in raw_projection.members
    )
    rows = industry.rows
    if (
        type(rows) is not tuple
        or len(rows) != len(members)
        or tuple(row[:3] for row in rows) != tuple(sorted(row[:3] for row in rows))
        or len({row[:3] for row in rows}) != len(rows)
        or {row[:3] for row in rows} != set(members)
        or any(
            type(row) is not tuple
            or len(row) != 4
            or any(type(value) is not str or not value for value in row)
            for row in rows
        )
    ):
        raise ValueError("raw Industry participation input is invalid")
    directions = {
        (member.isin, member.exchange, member.effective_symbol): member.direction
        for member in raw_projection.members
    }
    if any(direction is None for direction in directions.values()):
        return CurrentRawIndustryParticipationV1(
            "INSUFFICIENT_EVIDENCE",
            len(members),
            (),
            ("MEMBER_DIRECTION_UNAVAILABLE",),
        )
    totals: dict[str, list[int]] = {}
    for isin, exchange, symbol, industry_name in rows:
        direction = directions[(isin, exchange, symbol)]
        if direction is None:
            raise ValueError("raw Industry participation input is invalid")
        values = totals.setdefault(industry_name, [0, 0, 0, 0])
        values[0] += 1
        values[{"ADVANCE": 1, "DECLINE": 2, "UNCHANGED": 3}[direction]] += 1
    groups = tuple(
        CurrentRawIndustryGroupV1(industry_name, *totals[industry_name])
        for industry_name in sorted(totals)
    )
    return CurrentRawIndustryParticipationV1("OBSERVED", len(members), groups, ())
