"""Independent raw-direction arithmetic for ``current-price-context@v1``.

This module intentionally has no provider, storage, V4, or BharatStock dependency.
It owns only the exact endpoint direction and supplied-cohort denominator rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

RawDirectionV1 = Literal["ADVANCE", "DECLINE", "UNCHANGED"]


@dataclass(frozen=True, slots=True)
class RawDirectionMemberV1:
    """One private producer-minted endpoint direction, or a withheld direction."""

    isin: str
    direction: RawDirectionV1 | None

    def __post_init__(self) -> None:
        if type(self.isin) is not str or not self.isin:
            raise ValueError("raw direction member ISIN is invalid")
        if self.direction not in ("ADVANCE", "DECLINE", "UNCHANGED", None):
            raise ValueError("raw direction is invalid")


@dataclass(frozen=True, slots=True)
class RawCohortBreadthV1:
    requested_count: int
    advances: int | None
    declines: int | None
    unchanged: int | None
    label: Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"] | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.requested_count) is not int or not 1 <= self.requested_count <= 50:
            raise ValueError("raw breadth requested count is invalid")
        observed = self.label is not None
        if observed:
            if self.reasons or None in (self.advances, self.declines, self.unchanged):
                raise ValueError("observed raw breadth is incomplete")
            advances = self.advances
            declines = self.declines
            unchanged = self.unchanged
            if advances is None or declines is None or unchanged is None:
                raise ValueError("observed raw breadth is incomplete")
            if advances + declines + unchanged != self.requested_count:
                raise ValueError("raw breadth denominator changed")
        elif (
            self.advances is not None
            or self.declines is not None
            or self.unchanged is not None
            or not self.reasons
        ):
            raise ValueError("withheld raw breadth is invalid")


def raw_direction_v1(first_close: object, last_close: object) -> RawDirectionV1:
    """Return the closed S0/S20 raw direction without rounding or tolerance."""
    if not isinstance(first_close, Decimal) or not isinstance(last_close, Decimal):
        raise ValueError("raw endpoint closes must be Decimal")
    if (
        not first_close.is_finite()
        or not last_close.is_finite()
        or first_close <= 0
        or last_close <= 0
    ):
        raise ValueError("raw endpoint closes must be positive finite decimals")
    if last_close > first_close:
        return "ADVANCE"
    if last_close < first_close:
        return "DECLINE"
    return "UNCHANGED"


def reduce_raw_cohort_breadth_v1(
    members: tuple[RawDirectionMemberV1, ...], *, requested_count: int
) -> RawCohortBreadthV1:
    """Reduce exactly the supplied cohort; never silently remove a member."""
    if type(members) is not tuple or type(requested_count) is not int:
        raise ValueError("raw breadth inputs are invalid")
    if not 1 <= requested_count <= 50 or len(members) != requested_count:
        raise ValueError("raw breadth cohort size is invalid")
    if any(type(member) is not RawDirectionMemberV1 for member in members):
        raise ValueError("raw breadth members are invalid")
    if len({member.isin for member in members}) != requested_count:
        raise ValueError("raw breadth members are not unique")
    if any(member.direction is None for member in members):
        return RawCohortBreadthV1(
            requested_count, None, None, None, None, ("MEMBER_DIRECTION_UNAVAILABLE",)
        )
    advances = sum(member.direction == "ADVANCE" for member in members)
    declines = sum(member.direction == "DECLINE" for member in members)
    unchanged = requested_count - advances - declines
    if advances * 5 >= requested_count * 3:
        label = "BROAD_ADVANCE"
    elif declines * 5 >= requested_count * 3:
        label = "BROAD_DECLINE"
    else:
        label = "MIXED_PARTICIPATION"
    return RawCohortBreadthV1(requested_count, advances, declines, unchanged, label, ())
