from typing import Literal

from swing_trading_ai_assistant.market_regime.current_raw_price_context import (
    RawDirectionMemberV1,
    reduce_raw_cohort_breadth_v1,
)


def test_exact_inclusive_raw_cohort_breadth_preserves_supplied_denominator() -> None:
    """The new raw lane is independent of V4/second-price-provider context."""
    members = (
        RawDirectionMemberV1("INE000A01001", "ADVANCE"),
        RawDirectionMemberV1("INE000A01002", "ADVANCE"),
        RawDirectionMemberV1("INE000A01003", "ADVANCE"),
        RawDirectionMemberV1("INE000A01004", "DECLINE"),
        RawDirectionMemberV1("INE000A01005", "UNCHANGED"),
    )

    breadth = reduce_raw_cohort_breadth_v1(members, requested_count=5)

    assert breadth.label == "BROAD_ADVANCE"
    assert (breadth.advances, breadth.declines, breadth.unchanged) == (3, 1, 1)
    assert breadth.requested_count == 5


def test_exact_public_breadth_boundaries_cover_one_and_fifty_members() -> None:
    cases: tuple[
        tuple[
            int,
            int,
            Literal["ADVANCE", "DECLINE"],
            Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"],
        ],
        ...,
    ] = (
        (1, 1, "ADVANCE", "BROAD_ADVANCE"),
        (1, 1, "DECLINE", "BROAD_DECLINE"),
        (50, 30, "ADVANCE", "BROAD_ADVANCE"),
        (50, 29, "ADVANCE", "MIXED_PARTICIPATION"),
        (50, 30, "DECLINE", "BROAD_DECLINE"),
    )
    for total, directional, direction, expected_label in cases:
        members = tuple(
            RawDirectionMemberV1(
                f"INE{index:08d}", direction if index < directional else "UNCHANGED"
            )
            for index in range(total)
        )

        breadth = reduce_raw_cohort_breadth_v1(members, requested_count=total)

        assert breadth.requested_count == total
        assert breadth.label == expected_label
        assert (breadth.advances, breadth.declines, breadth.unchanged) == (
            directional if direction == "ADVANCE" else 0,
            directional if direction == "DECLINE" else 0,
            total - directional,
        )


def test_missing_member_withholds_whole_cohort_aggregate_without_reducing_n() -> None:
    breadth = reduce_raw_cohort_breadth_v1(
        (
            RawDirectionMemberV1("INE000A01001", "ADVANCE"),
            RawDirectionMemberV1("INE000A01002", None),
        ),
        requested_count=2,
    )

    assert breadth.label is None
    assert breadth.requested_count == 2
    assert breadth.reasons == ("MEMBER_DIRECTION_UNAVAILABLE",)
