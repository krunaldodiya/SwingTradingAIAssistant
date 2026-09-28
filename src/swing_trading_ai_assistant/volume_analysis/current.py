"""Plan 39 exact arithmetic; pure results do not establish evidence admission."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Literal


@dataclass(frozen=True, slots=True)
class VolumeCalculation:
    """Exact baseline and ratio, not a retained or admitted research result."""

    baseline_numerator: int
    baseline_denominator: int
    relative_numerator: int
    relative_denominator: int
    relation: Literal["ABOVE", "EQUAL", "BELOW"]


def calculate_volume(volumes: tuple[int, ...]) -> VolumeCalculation | None:
    """Compare the last session with precisely its twenty predecessors.

    None denotes a zero baseline. Input order must already be established by
    the evidence boundary; this arithmetic helper makes no provenance claim.
    """
    if (
        type(volumes) is not tuple
        or len(volumes) != 21
        or any(
            type(value) is not int or not 0 <= value <= 2**63 - 1 for value in volumes
        )
    ):
        raise ValueError("invalid completed-session volume grid")
    total = sum(volumes[:-1])
    if total == 0:
        return None
    baseline = Fraction(total, 20)
    relative = Fraction(20 * volumes[-1], total)
    relation: Literal["ABOVE", "EQUAL", "BELOW"] = (
        "ABOVE" if relative > 1 else "BELOW" if relative < 1 else "EQUAL"
    )
    return VolumeCalculation(
        baseline.numerator,
        baseline.denominator,
        relative.numerator,
        relative.denominator,
        relation,
    )
