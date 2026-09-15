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
