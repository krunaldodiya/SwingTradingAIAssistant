"""Exact Plan 41 arithmetic; pure math alone cannot admit retained evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Literal


@dataclass(frozen=True, slots=True)
class RelativeStrengthCalculation:
    target_change_numerator: int
    target_change_denominator: int
    reference_change_numerator: int
    reference_change_denominator: int
    difference_percentage_points_numerator: int
    difference_percentage_points_denominator: int
    relation: Literal["ABOVE", "EQUAL", "BELOW"]


def _endpoint(value: Decimal) -> Fraction:
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise ValueError("invalid close")
    coefficient = value.as_tuple().digits
    exponent = value.as_tuple().exponent
    if len(coefficient) > 32 or type(exponent) is not int or not -16 <= exponent <= 16:
        raise ValueError("PRICE_RANGE_UNSUPPORTED")
    numerator, denominator = value.as_integer_ratio()
    return Fraction(numerator, denominator)


def calculate_relative_strength(
    target_first: Decimal,
    target_last: Decimal,
    reference_first: Decimal,
    reference_last: Decimal,
) -> RelativeStrengthCalculation:
    """Compare endpoint ratios without ambient Decimal context or tolerance."""
    target_start, target_end, reference_start, reference_end = (
        _endpoint(value)
        for value in (target_first, target_last, reference_first, reference_last)
    )
    target_ratio = target_end / target_start
    reference_ratio = reference_end / reference_start
    target_change = target_ratio - 1
    reference_change = reference_ratio - 1
    difference = 100 * (target_ratio - reference_ratio)
    relation: Literal["ABOVE", "EQUAL", "BELOW"] = (
        "ABOVE" if difference > 0 else "BELOW" if difference < 0 else "EQUAL"
    )
    return RelativeStrengthCalculation(
        target_change.numerator,
        target_change.denominator,
        reference_change.numerator,
        reference_change.denominator,
        difference.numerator,
        difference.denominator,
        relation,
    )


def fractional_price_change(first: Decimal, last: Decimal) -> Fraction:
    """Validate both endpoints independently of the other instrument."""
    return _endpoint(last) / _endpoint(first) - 1
