"""RED contracts for literal current Industry participation from raw directions."""

from __future__ import annotations

from swing_trading_ai_assistant.sector_analysis.current_raw_industry_participation import (
    RawIndustryDirectionV1,
    reduce_current_raw_industry_participation_v1,
)


def test_raw_industry_reducer_withholds_aggregate_when_a_member_is_unavailable() -> (
    None
):
    result = reduce_current_raw_industry_participation_v1(
        (
            RawIndustryDirectionV1("INE000A01001", "NSE", "AAA", "Banking", "ADVANCE"),
            RawIndustryDirectionV1("INE000A01002", "NSE", "BBB", "Banking", None),
        ),
        requested_count=2,
    )

    assert result.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert result.requested_count == 2
    assert result.groups == ()
    assert result.reasons == ("MEMBER_DIRECTION_UNAVAILABLE",)


def test_raw_industry_reducer_uses_literal_industry_and_complete_denominator() -> None:
    result = reduce_current_raw_industry_participation_v1(
        (
            RawIndustryDirectionV1("INE000A01001", "NSE", "AAA", "Banking", "ADVANCE"),
            RawIndustryDirectionV1("INE000A01002", "NSE", "BBB", "Banking", "DECLINE"),
        ),
        requested_count=2,
    )

    assert result.evidence_state == "OBSERVED"
    assert result.groups[0].industry == "Banking"
    assert (
        result.groups[0].member_count,
        result.groups[0].advances,
        result.groups[0].declines,
    ) == (2, 1, 1)
