"""Aggregate-only literal-Industry participation over admitted raw directions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

_Direction = Literal["ADVANCE", "DECLINE", "UNCHANGED"]


@dataclass(frozen=True, slots=True)
class RawIndustryDirectionV1:
    """Private producer handoff; no classification source rows are public."""

    isin: str
    exchange: Literal["NSE"]
    effective_symbol: str
    industry: str
    direction: _Direction | None

    def __post_init__(self) -> None:
        if (
            type(self.isin) is not str
            or not self.isin
            or self.exchange != "NSE"
            or type(self.effective_symbol) is not str
            or not self.effective_symbol
            or type(self.industry) is not str
            or not self.industry
            or self.direction not in ("ADVANCE", "DECLINE", "UNCHANGED", None)
        ):
            raise ValueError("raw Industry direction is invalid")


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
            or self.member_count < 1
            or min(self.advances, self.declines, self.unchanged) < 0
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
            not 1 <= self.requested_count <= 50
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
    directions: tuple[RawIndustryDirectionV1, ...], *, requested_count: int
) -> CurrentRawIndustryParticipationV1:
    """Reduce the complete admitted cohort without sector inference or shrinking N."""
    if (
        type(directions) is not tuple
        or type(requested_count) is not int
        or not 1 <= requested_count <= 50
        or len(directions) != requested_count
        or any(
            type(direction) is not RawIndustryDirectionV1 for direction in directions
        )
        or len(
            {(item.isin, item.exchange, item.effective_symbol) for item in directions}
        )
        != requested_count
    ):
        raise ValueError("raw Industry participation input is invalid")
    if any(item.direction is None for item in directions):
        return CurrentRawIndustryParticipationV1(
            "INSUFFICIENT_EVIDENCE",
            requested_count,
            (),
            ("MEMBER_DIRECTION_UNAVAILABLE",),
        )
    totals: dict[str, list[int]] = {}
    for item in directions:
        values = totals.setdefault(item.industry, [0, 0, 0, 0])
        values[0] += 1
        values[{"ADVANCE": 1, "DECLINE": 2, "UNCHANGED": 3}[item.direction]] += 1  # type: ignore[index]
    groups = tuple(
        CurrentRawIndustryGroupV1(industry, *totals[industry])
        for industry in sorted(totals)
    )
    return CurrentRawIndustryParticipationV1("OBSERVED", requested_count, groups, ())
