"""Public BharatStock retained-capture research consumer contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_UP, Decimal, Inexact, localcontext

import pytest

from swing_trading_ai_assistant.market_data import bharatstock_capture as capture
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockDailyPrice,
    BharatStockHistory,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.bharatstock_capture import (
    CaptureMemberResultV2,
    CaptureRequestV2,
    CaptureRevisionV2,
    selection_identity_v2,
)
from swing_trading_ai_assistant.research_packet.bharatstock import (
    build_bharatstock_research_packet_v1,
)

_CUTOFF = datetime(2026, 8, 31, 12, tzinfo=UTC)


def _sessions(session_count: int = 21) -> tuple[date, ...]:
    return tuple(
        date(2026, 8, 1) + timedelta(days=index) for index in range(session_count)
    )


def _revision_with_history(session_count: int) -> CaptureRevisionV2:
    sessions = _sessions(session_count)
    member = _instrument(0)
    history = BharatStockHistory(
        member,
        tuple(
            BharatStockDailyPrice(
                session,
                Decimal("10"),
                Decimal("12"),
                Decimal("9"),
                Decimal("11"),
                100,
                Decimal("5.5"),
                Decimal("0.5"),
            )
            for session in sessions
        ),
        _CUTOFF,
        ("d" * 64, "e" * 64),
        2,
    )
    request = CaptureRequestV2(
        (member,),
        sessions,
        _CUTOFF,
        "a" * 64,
        "nse-upstox-composed-calendar",
        "composed-calendar@v1=" + "a" * 64,
        "b" * 64,
        selection_identity_v2((member,)),
    )
    outcomes = (CaptureMemberResultV2(member, "OBSERVED", None, history),)
    return CaptureRevisionV2(
        request, outcomes, capture._coverage_identity(outcomes), None, _CUTOFF
    )


def _instrument(index: int) -> BharatStockInstrument:
    return BharatStockInstrument(f"INE{index:09d}", "NSE", f"EQ{index:03d}")


def _history(
    member: BharatStockInstrument, *, invalid: bool = False
) -> BharatStockHistory:
    rows = tuple(
        BharatStockDailyPrice(
            session=session,
            open=Decimal("10") + index,
            high=Decimal("12") + index,
            low=Decimal("9") + index,
            close=Decimal("11") + index,
            volume=100 + index,
            adjusted_close=(Decimal("11") + index) * Decimal("0.5"),
            adjustment_factor=Decimal("0.5"),
        )
        for index, session in enumerate(_sessions())
    )
    if invalid:
        object.__setattr__(rows[0], "adjustment_factor", Decimal("0"))
    return BharatStockHistory(member, rows, _CUTOFF, ("d" * 64, "e" * 64), 2)


def _revision(
    *states: str, invalid: bool = False, shared_failure: str | None = None
) -> CaptureRevisionV2:
    members = tuple(_instrument(index) for index in range(len(states)))
    request = CaptureRequestV2(
        members,
        _sessions(),
        _CUTOFF,
        "a" * 64,
        "nse-upstox-composed-calendar",
        "composed-calendar@v1=" + "a" * 64,
        "b" * 64,
        selection_identity_v2(members),
    )
    outcomes = tuple(
        CaptureMemberResultV2(
            member,
            state,
            None
            if state == "OBSERVED"
            else "BLOCKED_BY_SHARED_FAILURE"
            if state == "NOT_ATTEMPTED"
            else shared_failure or "MISSING_HISTORY",
            _history(member, invalid=invalid) if state == "OBSERVED" else None,
        )
        for member, state in zip(members, states, strict=True)
    )
    return CaptureRevisionV2(
        request, outcomes, capture._coverage_identity(outcomes), shared_failure, _CUTOFF
    )


def test_complete_hundred_preserves_every_member_and_full_denominator() -> None:
    packet = build_bharatstock_research_packet_v1(_revision(*("OBSERVED",) * 100))

    assert packet.coverage.requested == 100
    assert packet.coverage.observed == 100
    assert packet.coverage.insufficient == packet.coverage.not_attempted == 0
    assert packet.aggregate_evidence_state == "OBSERVED"
    assert tuple(member.member for member in packet.members) == tuple(
        _instrument(index) for index in range(100)
    )
    assert all(
        member.market_structure is not None and member.price_action is not None
        for member in packet.members
    )


def test_capture_structure_is_explicitly_adjusted_basis_not_raw_bar_context() -> None:
    packet = build_bharatstock_research_packet_v1(_revision("OBSERVED"))

    fact = packet.members[0].market_structure
    assert fact is not None
    assert fact.price_basis == "BHARATSTOCK_SOURCE_REPORTED_OHLC"
    assert fact.adjusted_bar_identities_sha256 == tuple(
        bar.source_row_identity_sha256 for bar in packet.members[0].adjusted_bars or ()
    )


def test_one_local_insufficiency_keeps_valid_members_but_withholds_aggregate() -> None:
    complete = build_bharatstock_research_packet_v1(_revision(*("OBSERVED",) * 99))
    packet = build_bharatstock_research_packet_v1(
        _revision(*(("OBSERVED",) * 99 + ("INSUFFICIENT_EVIDENCE",)))
    )

    assert (
        packet.coverage.requested,
        packet.coverage.observed,
        packet.coverage.insufficient,
    ) == (100, 99, 1)
    assert packet.aggregate_evidence_state == "INSUFFICIENT_EVIDENCE"
    assert packet.members[-1].reason == "MISSING_HISTORY"
    assert (
        packet.members[-1].market_structure is packet.members[-1].price_action is None
    )
    assert packet.members[:-1] == complete.members
    assert packet.members[49].market_structure is not None
    assert packet.members[50].market_structure is not None


def test_invalid_adjusted_history_and_shared_stop_are_explicit() -> None:
    with pytest.raises(ValueError):
        build_bharatstock_research_packet_v1(_revision("OBSERVED", invalid=True))
    stopped = build_bharatstock_research_packet_v1(
        _revision(
            "OBSERVED",
            "INSUFFICIENT_EVIDENCE",
            "NOT_ATTEMPTED",
            shared_failure="RATE_LIMITED",
        )
    )

    assert stopped.coverage.requested == 3
    assert (
        stopped.coverage.observed
        == stopped.coverage.insufficient
        == stopped.coverage.not_attempted
        == 1
    )
    assert stopped.shared_failure == "RATE_LIMITED"
    assert stopped.members[1].reason == stopped.members[2].reason == "RATE_LIMITED"


def test_reordered_capture_is_a_distinct_selection_and_preserves_member_math() -> None:
    first = _revision("OBSERVED", "OBSERVED")
    members = tuple(reversed(first.request.members))
    second = CaptureRevisionV2(
        CaptureRequestV2(
            members,
            _sessions(),
            _CUTOFF,
            "a" * 64,
            "nse-upstox-composed-calendar",
            "composed-calendar@v1=" + "a" * 64,
            "b" * 64,
            selection_identity_v2(members),
        ),
        tuple(reversed(first.members)),
        capture._coverage_identity(tuple(reversed(first.members))),
        None,
        _CUTOFF,
    )

    forward = build_bharatstock_research_packet_v1(first)
    reverse = build_bharatstock_research_packet_v1(second)
    assert forward.selection_identity_sha256 != reverse.selection_identity_sha256
    assert tuple(item.member for item in reverse.members) == tuple(
        reversed(tuple(item.member for item in forward.members))
    )
    assert forward.members[0].price_action == reverse.members[1].price_action


@pytest.mark.parametrize(
    ("session_count", "structure_observed"),
    ((2, False), (21, True), (24, True)),
)
def test_feature_windows_preserve_short_exact_and_long_history(
    session_count: int, structure_observed: bool
) -> None:
    sessions = _sessions(session_count)
    member = build_bharatstock_research_packet_v1(
        _revision_with_history(session_count)
    ).members[0]

    assert member.price_basis == "BHARATSTOCK_SOURCE_REPORTED_OHLC"
    assert tuple(bar.session for bar in member.adjusted_bars or ()) == sessions
    assert member.price_action_evidence_state == "OBSERVED"
    assert member.price_action is not None
    assert (
        member.price_action.previous_session,
        member.price_action.session,
    ) == sessions[-2:]
    assert (member.market_structure_evidence_state == "OBSERVED") is structure_observed
    if structure_observed:
        assert member.market_structure is not None
        assert member.market_structure.adjusted_bar_identities_sha256 == tuple(
            bar.source_row_identity_sha256 for bar in (member.adjusted_bars or ())[-21:]
        )
    else:
        assert member.market_structure is None
        assert member.market_structure_reason == "INSUFFICIENT_HISTORY"


def test_one_session_withholds_both_feature_facts_explicitly() -> None:
    member = build_bharatstock_research_packet_v1(_revision_with_history(1)).members[0]

    assert member.market_structure is member.price_action is None
    assert member.market_structure_evidence_state == "INSUFFICIENT_EVIDENCE"
    assert member.price_action_evidence_state == "INSUFFICIENT_EVIDENCE"
    assert (
        member.market_structure_reason
        == member.price_action_reason
        == "INSUFFICIENT_HISTORY"
    )


def test_admitted_facts_ignore_the_callers_decimal_context() -> None:
    revision = _revision("OBSERVED")
    expected = build_bharatstock_research_packet_v1(revision)
    with localcontext() as caller:
        caller.prec = 2
        caller.rounding = ROUND_UP
        caller.traps[Inexact] = True
        actual = build_bharatstock_research_packet_v1(revision)
        assert caller.prec == 2
        assert caller.rounding == ROUND_UP
        assert caller.traps[Inexact]
    assert actual == expected
    assert actual.coverage.observed == 1
    fact = actual.members[0].price_action
    assert fact is not None
    assert fact.range_size == Decimal("3")
    assert fact.body_size == Decimal("1")


def test_selected_price_mode_changes_prices_once_without_changing_volume() -> None:
    original = _revision("OBSERVED")
    opted_in = replace(
        original,
        request=replace(original.request, apply_adjustment=True),
        price_basis=None,
    )
    source = build_bharatstock_research_packet_v1(original)
    adjusted = build_bharatstock_research_packet_v1(opted_in)
    source_bars = source.members[0].adjusted_bars
    adjusted_bars = adjusted.members[0].adjusted_bars
    assert source_bars is not None and adjusted_bars is not None
    assert source.price_basis == "BHARATSTOCK_SOURCE_REPORTED_OHLC"
    assert adjusted.price_basis == "BHARATSTOCK_FACTOR_APPLIED_OHLC"
    for raw, projected in zip(source_bars, adjusted_bars, strict=True):
        assert (projected.open, projected.high, projected.low, projected.close) == (
            raw.open / 2,
            raw.high / 2,
            raw.low / 2,
            raw.close / 2,
        )
        assert projected.volume == raw.volume
    assert build_bharatstock_research_packet_v1(original) == source


def test_three_missing_members_leave_ninety_seven_results_usable() -> None:
    complete = build_bharatstock_research_packet_v1(_revision(*("OBSERVED",) * 97))
    packet = build_bharatstock_research_packet_v1(
        _revision(*(("OBSERVED",) * 97 + ("INSUFFICIENT_EVIDENCE",) * 3))
    )
    assert packet.members[:97] == complete.members
    assert (
        packet.coverage.requested,
        packet.coverage.observed,
        packet.coverage.insufficient,
        packet.coverage.not_attempted,
    ) == (100, 97, 3, 0)
    assert packet.aggregate_evidence_state == "INSUFFICIENT_EVIDENCE"
    assert all(member.reason == "MISSING_HISTORY" for member in packet.members[97:])


def test_rejects_unvalidated_arbitrary_input() -> None:
    with pytest.raises(ValueError):
        build_bharatstock_research_packet_v1(object())
