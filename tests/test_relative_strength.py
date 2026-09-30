"""Exact Plan 41 math and closed request behavior."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext

import pytest

from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextMemberV1,
)
from swing_trading_ai_assistant.relative_strength import (
    RelativeStrengthRequest,
    calculate_relative_strength,
    relative_strength_request_from_json,
)


def member(isin="INE467B01029", symbol="ACME"):
    return CurrentPriceContextMemberV1(
        isin, "NSE", "EQUITY", "EQ", symbol, date(2020, 1, 1), date(2030, 1, 1)
    )


def synthetic_isin(index):
    prefix = f"INE{index:08d}"
    digits = "".join(str(ord(char) - 55) if char.isalpha() else char for char in prefix)
    for check in range(10):
        values = list(map(int, reversed(digits + str(check))))
        total = sum(
            value if position % 2 == 0 else (2 * value // 10 + 2 * value % 10)
            for position, value in enumerate(values)
        )
        if total % 10 == 0:
            return prefix + str(check)
    raise AssertionError("check digit unavailable")


def request(targets=None, reference=None):
    selected = datetime(2026, 9, 15, 9, tzinfo=UTC)
    return RelativeStrengthRequest(
        selected,
        selected + timedelta(minutes=20),
        "a" * 64,
        member("INE467B01037", "BETA") if reference is None else reference,
        (member(),) if targets is None else targets,
    )


@pytest.mark.parametrize(
    "prices,expected",
    [
        (("100", "110", "200", "210"), (1, 10, 1, 20, 5, 1, "ABOVE")),
        (("100", "95", "200", "180"), (-1, 20, -1, 10, 5, 1, "ABOVE")),
        (("100", "90", "200", "210"), (-1, 10, 1, 20, -15, 1, "BELOW")),
        (("100", "110", "200", "220"), (1, 10, 1, 10, 0, 1, "EQUAL")),
        (("1", "1.0000000000000001", "2", "2"), (1, 10**16, 0, 1, 1, 10**14, "ABOVE")),
    ],
)
def test_independent_exact_price_comparison(prices, expected):
    with localcontext() as context:
        context.prec = 3
        result = calculate_relative_strength(*(Decimal(value) for value in prices))
    assert (
        result.target_change_numerator,
        result.target_change_denominator,
        result.reference_change_numerator,
        result.reference_change_denominator,
        result.difference_percentage_points_numerator,
        result.difference_percentage_points_denominator,
        result.relation,
    ) == expected


def test_numeric_boundary_and_limit_plus_one():
    bound = Decimal("1" + "0" * 30 + "1")
    assert (
        calculate_relative_strength(
            bound, bound, Decimal("1e16"), Decimal("1e-16")
        ).relation
        == "ABOVE"
    )
    for invalid in (Decimal("1" + "0" * 31 + "1"), Decimal("1e17"), Decimal("1e-17")):
        with pytest.raises(ValueError, match="PRICE_RANGE_UNSUPPORTED"):
            calculate_relative_strength(invalid, Decimal(1), Decimal(1), Decimal(1))


def test_request_round_trip_and_roles():
    value = request()
    assert relative_strength_request_from_json(value.canonical_bytes) == value
    assert value.raw_input().members == (value.reference, *value.members)
    assert value.raw_input().request_identity_sha256 == value.request_identity_sha256


def test_forty_nine_targets_and_order_identity():
    targets = tuple(member(synthetic_isin(index), f"S{index}") for index in range(49))
    first = request(targets=targets)
    reverse = request(targets=tuple(reversed(targets)))
    assert len(first.raw_input().members) == 50
    assert first.raw_input().members[0] == first.reference
    assert first.request_identity_sha256 != reverse.request_identity_sha256
    assert (
        first.raw_input().ordered_selection_identity_sha256
        != reverse.raw_input().ordered_selection_identity_sha256
    )
    assert len(first.canonical_bytes) <= 64 * 1024


def test_reference_change_binds_distinct_request_and_producer():
    first = request()
    second = request(reference=member(synthetic_isin(99), "REF99"))
    assert first.request_identity_sha256 != second.request_identity_sha256
    assert (
        first.raw_input().ordered_selection_identity_sha256
        != second.raw_input().ordered_selection_identity_sha256
    )


def test_request_byte_limit_and_duplicate_nested_key():
    value = request()
    exact = value.canonical_bytes + b" " * (65536 - len(value.canonical_bytes))
    assert relative_strength_request_from_json(exact) == value
    with pytest.raises(ValueError):
        relative_strength_request_from_json(exact + b" ")
    nested = value.canonical_bytes.replace(b'"isin":', b'"isin":"bad","isin":')
    with pytest.raises(ValueError):
        relative_strength_request_from_json(nested)


def test_sdk_rechecks_member_mutation_and_temporal_interval():
    value = request()
    with pytest.raises(ValueError):
        RelativeStrengthRequest(
            value.data_selection_time,
            value.data_selection_time + timedelta(minutes=31),
            value.schedule_identity_sha256,
            value.reference,
            value.members,
        )
    with pytest.raises(ValueError):
        RelativeStrengthRequest(
            value.data_selection_time,
            value.admission_deadline,
            value.schedule_identity_sha256,
            value.reference,
            list(value.members),
        )


@pytest.mark.parametrize(
    "bad",
    [Decimal(0), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 1, "1", True],
)
def test_arithmetic_rejects_nonadmitted_endpoints(bad):
    with pytest.raises(ValueError):
        calculate_relative_strength(bad, Decimal(1), Decimal(1), Decimal(1))


@pytest.mark.parametrize("count", [0, 50])
def test_target_count_rejected(count):
    targets = tuple(
        member(synthetic_isin(index), f"S{index}") for index in range(count)
    )
    with pytest.raises(ValueError):
        request(targets=targets)


@pytest.mark.parametrize(
    "case",
    ["overlap", "alias", "duplicate", "field", "constant", "version", "oversize"],
)
def test_closed_request_rejects_before_effects(case):
    value = request()
    if case == "overlap":
        with pytest.raises(ValueError):
            request(reference=member())
        return
    if case == "alias":
        with pytest.raises(ValueError):
            request(reference=member("INE467B01037", "ACME"))
        return
    if case == "duplicate":
        raw = value.canonical_bytes.replace(b'"members":', b'"members":[],"members":')
    elif case == "oversize":
        raw = b" " * 65537
    else:
        decoded = json.loads(value.canonical_bytes)
        if case == "field":
            decoded["unknown"] = 1
        elif case == "constant":
            decoded["unknown"] = float("nan")
        else:
            decoded["contract_version"] = "wrong@v1"
        raw = json.dumps(decoded, allow_nan=True).encode()
    with pytest.raises(ValueError):
        relative_strength_request_from_json(raw)
