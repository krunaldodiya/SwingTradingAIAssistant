"""Public BharatStock retained-capture research consumer contracts."""

from __future__ import annotations

import importlib.util
import tracemalloc
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_UP, Decimal, Inexact, localcontext
from pathlib import Path
from typing import Literal, cast

import pytest

from swing_trading_ai_assistant.market_data import bharatstock_capture as capture
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockDailyPrice,
    BharatStockError,
    BharatStockHistory,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.bharatstock_capture import (
    CaptureMemberResultV2,
    CaptureRequestV2,
    CaptureRevisionV2,
    capture_bharatstock_v2,
    read_bharatstock_capture_binding_v2,
    schedule_identity_v2,
    selection_identity_v2,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceStore,
    ScheduleSession,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.research_packet import bharatstock_v2
from swing_trading_ai_assistant.research_packet.bharatstock import (
    build_bharatstock_research_packet_v1,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockCaptureRequestProvenanceV2,
    BharatStockFeatureInputV2,
    build_bharatstock_research_packet_v2,
)

_CUTOFF = datetime(2026, 8, 31, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("reason", "expected"),
    (
        ("NOT_FOUND", ("INSUFFICIENT_EVIDENCE", "NOT_ESTABLISHED", "NOT_ESTABLISHED")),
        (
            "IDENTITY_MISMATCH",
            ("INSUFFICIENT_EVIDENCE", "CONFLICTED", "NOT_ESTABLISHED"),
        ),
        (
            "EMPTY_HISTORY",
            ("INSUFFICIENT_EVIDENCE", "NOT_ESTABLISHED", "NOT_ESTABLISHED"),
        ),
        (
            "AUTHENTICATION",
            ("INSUFFICIENT_EVIDENCE", "NOT_ESTABLISHED", "NOT_ESTABLISHED"),
        ),
    ),
)
def test_v2_finite_producer_failure_reason_mapping(
    reason: str, expected: tuple[str, str, str]
) -> None:
    assert bharatstock_v2._failure_outcome(reason) == expected  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize(
    "reason", ("UNRECOGNIZED_PROVIDER_DEFECT", "AUTHENTICATION_FAILED")
)
def test_v2_unknown_producer_reason_is_fatal(reason: str) -> None:
    with pytest.raises(ValueError, match="unexpected BharatStock"):
        bharatstock_v2._failure_outcome(reason)  # pyright: ignore[reportPrivateUsage]


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


def test_capture_structure_is_explicitly_source_reported_basis() -> None:
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


def test_v2_requested_slot_provenance_is_exact_and_bounded() -> None:
    request = _revision_with_history(1).request
    provenance = BharatStockCaptureRequestProvenanceV2(
        request.request_identity_sha256,
        request.schedule_identity_sha256,
        request.decision_cutoff,
        request.sessions,
    )
    assert provenance.requested_sessions == request.sessions
    with pytest.raises(ValueError, match="provenance"):
        BharatStockCaptureRequestProvenanceV2(
            request.request_identity_sha256,
            request.schedule_identity_sha256,
            request.decision_cutoff,
            (),
        )


def test_v2_rejects_constructed_capture_without_owner_mapping_binding() -> None:
    revision = _revision_with_history(1)
    with pytest.raises(ValueError, match="input slot"):
        BharatStockFeatureInputV2(
            "CANDLE_GEOMETRY", "RETAINED_REVISION", revision.request.sessions, None
        )
    with pytest.raises(TypeError):
        build_bharatstock_research_packet_v2(())  # type: ignore[call-arg]


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


def test_packet_uses_supplied_ohlc_and_source_volume() -> None:
    packet = build_bharatstock_research_packet_v1(_revision("OBSERVED"))

    bars = packet.members[0].adjusted_bars
    assert bars is not None
    assert packet.price_basis == "BHARATSTOCK_SOURCE_REPORTED_OHLC"
    assert (bars[0].open, bars[0].high, bars[0].low, bars[0].close, bars[0].volume) == (
        Decimal("10"),
        Decimal("12"),
        Decimal("9"),
        Decimal("11"),
        100,
    )


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


def test_compact_optional_decimal_exponents_do_not_expand_research_memory() -> None:
    original = _revision_with_history(2)

    def with_factor(factor: Decimal) -> CaptureRevisionV2:
        member = original.members[0]
        history = replace(
            member.history,
            rows=tuple(
                replace(
                    row, adjustment_factor=factor, adjusted_close=row.close * factor
                )
                for row in member.history.rows
            ),
        )
        members = (replace(member, history=history),)
        return replace(
            original,
            members=members,
            actual_coverage_identity_sha256=capture._coverage_identity(members),
        )

    ordinary = with_factor(Decimal("1e-10"))
    tiny = with_factor(Decimal("1e-100000"))
    assert len(tiny.canonical_json_bytes()) < 4096
    build_bharatstock_research_packet_v1(ordinary)

    def measured(revision):
        tracemalloc.start()
        try:
            packet = build_bharatstock_research_packet_v1(revision)
            return packet, tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

    ordinary_packet, ordinary_peak = measured(ordinary)
    tiny_packet, tiny_peak = measured(tiny)
    assert tiny_peak < ordinary_peak + 128 * 1024
    assert (
        tiny_packet.members[0].price_action.body_size
        == ordinary_packet.members[0].price_action.body_size
    )


def test_v2_real_capture_hundred_member_coverage_and_feature_independence(
    tmp_path: Path,
) -> None:
    """Exercise V2 only through retained mapping and retained capture admission."""
    sessions = tuple(
        date(2026, 7, 29) + timedelta(days=index)
        for index in range(29)
        if (date(2026, 7, 29) + timedelta(days=index)).weekday() < 5
    )
    cutoff = datetime(2026, 8, 26, 12, tzinfo=UTC)
    schedule = ExpectedSessionSchedule(
        3,
        "nse-upstox-composed-calendar",
        "composed-calendar@v1=" + "6" * 64,
        cutoff,
        "Asia/Kolkata",
        sessions[0],
        sessions[-1],
        tuple(
            ScheduleSession(
                item,
                datetime.combine(item, datetime.min.time(), UTC)
                + timedelta(hours=3, minutes=45),
                datetime.combine(item, datetime.min.time(), UTC) + timedelta(hours=10),
                "REGULAR",
            )
            for item in sessions
        ),
        tuple(
            ScheduleClosure(date(2026, 7, 29) + timedelta(days=index), "WEEKEND")
            for index in range(29)
            if (date(2026, 7, 29) + timedelta(days=index)) not in sessions
        ),
    )
    root = tmp_path / "retained"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    with acquired.lease as lease:
        retained_schedule = ScheduleEvidenceStore(root, lease).retain(schedule)
    assert retained_schedule.digest is not None
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    with acquired.lease as lease:
        resolved_schedule = ScheduleEvidenceStore(root, lease).resolve(
            retained_schedule.digest
        )
    assert resolved_schedule.schedule is not None
    validated_schedule = resolved_schedule.schedule
    mapping_spec = importlib.util.spec_from_file_location(
        "binding_fixture",
        Path(__file__).parents[1]
        / "market_data"
        / "test_current_research_binding_v2.py",
    )
    assert mapping_spec is not None and mapping_spec.loader is not None
    mapping_fixture = importlib.util.module_from_spec(mapping_spec)
    mapping_spec.loader.exec_module(mapping_fixture)
    catalog_rows = tuple(
        {
            "segment": "NSE_EQ",
            "name": f"Member {index}",
            "exchange": "NSE",
            "isin": f"INE{index:09d}",
            "instrument_type": "EQ",
            "instrument_key": f"NSE_EQ|INE{index:09d}",
            "trading_symbol": f"S{index:03d}",
        }
        for index in range(100)
    )
    schedule_identity = schedule_identity_v2(resolved_schedule.schedule)
    mapping_binding = mapping_fixture._binding(
        root,
        selected_at=cutoff,
        decision_cutoff=cutoff,
        snapshot_retrieved_at=cutoff - timedelta(minutes=5),
        snapshot_observation_date=cutoff.date(),
        instruments=catalog_rows,
        schedule_identity_sha256=schedule_identity,
    )
    mapping = mapping_fixture.validate_current_research_binding_v2(mapping_binding)
    members = tuple(item.instrument for item in mapping.members)

    class Client:
        def __init__(
            self,
            missing: set[str] | None = None,
            conflict: bool = False,
            mismatched_adjustment: bool = False,
            failure_reason: str = "EMPTY_HISTORY",
        ) -> None:
            self.missing: set[str] = set() if missing is None else missing
            self.conflict = conflict
            self.mismatched_adjustment = mismatched_adjustment
            self.failure_reason = failure_reason

        def history(
            self,
            instrument: BharatStockInstrument,
            start: date,
            end: date,
            *,
            effect_guard: object = None,
        ) -> BharatStockHistory:
            del effect_guard
            if self.conflict:
                raise BharatStockError("IDENTITY_MISMATCH", member_local=True)
            if instrument.isin in self.missing:
                raise BharatStockError(self.failure_reason, member_local=True)
            window = tuple(item for item in sessions if start <= item <= end)
            factor = (
                Decimal("1")
                if not self.mismatched_adjustment or start == sessions[-1]
                else Decimal("2")
            )
            close = Decimal("11") if factor == 1 else Decimal("12")
            return BharatStockHistory(
                instrument,
                tuple(
                    BharatStockDailyPrice(
                        item,
                        Decimal("10"),
                        Decimal("12"),
                        Decimal("9"),
                        close,
                        100,
                        close * factor,
                        factor,
                    )
                    for item in window
                ),
                cutoff,
                ("a" * 64, "b" * 64),
                2,
            )

    captured_slots: dict[str, tuple[BharatStockFeatureInputV2, ...]] = {}

    def packet(client: Client, name: str) -> bharatstock_v2.BharatStockResearchPacketV2:
        capture_root = tmp_path / name
        capture_root.mkdir(mode=0o700)
        acquired = StorageRootLease.try_acquire(capture_root)
        assert acquired.lease is not None
        with acquired.lease as lease:
            retained = ScheduleEvidenceStore(capture_root, lease).retain(schedule)
        assert retained.digest is not None
        slots: list[BharatStockFeatureInputV2] = []
        windows: tuple[
            tuple[
                Literal[
                    "CANDLE_GEOMETRY", "PREVIOUS_CLOSE_COMPARISON", "MARKET_STRUCTURE"
                ],
                tuple[date, ...],
            ],
            ...,
        ] = (
            ("CANDLE_GEOMETRY", sessions[-1:]),
            ("PREVIOUS_CLOSE_COMPARISON", sessions[-2:]),
            ("MARKET_STRUCTURE", sessions),
        )
        for feature, window in windows:
            request = CaptureRequestV2(
                members,
                window,
                cutoff,
                schedule_digest(validated_schedule),
                validated_schedule.source,
                validated_schedule.source_release,
                schedule_identity,
                selection_identity_v2(members),
            )
            result = capture_bharatstock_v2(
                request,
                capture_root,
                capture_root,
                client=cast(BharatStockClient, client),
                clock=lambda: cutoff,
            )
            assert result.revision is not None
            revision = result.revision
            binding = read_bharatstock_capture_binding_v2(
                capture_root, revision.revision_identity_sha256
            )
            assert type(binding) is capture.RetainedCaptureBindingV2
            slots.append(
                BharatStockFeatureInputV2(
                    feature,
                    "RETAINED_REVISION",
                    window,
                    retained_capture=binding,
                    request_provenance=BharatStockCaptureRequestProvenanceV2(
                        revision.request.request_identity_sha256,
                        revision.request.schedule_identity_sha256,
                        revision.request.decision_cutoff,
                        revision.request.sessions,
                    ),
                )
            )
        captured_slots[name] = tuple(slots)
        return build_bharatstock_research_packet_v2(tuple(slots), mapping_binding)

    complete = packet(Client(), "complete")
    assert (
        tuple(
            (item.requested, item.observed, item.insufficient)
            for item in complete.coverage
        )
        == ((100, 100, 0),) * 3
    )
    assert tuple(member.member for member in complete.members) == members
    for position, feature in enumerate(
        ("CANDLE_GEOMETRY", "PREVIOUS_CLOSE_COMPARISON", "MARKET_STRUCTURE")
    ):
        independent = build_bharatstock_research_packet_v2(
            tuple(
                slot
                if index == position
                else BharatStockFeatureInputV2(
                    (
                        "CANDLE_GEOMETRY",
                        "PREVIOUS_CLOSE_COMPARISON",
                        "MARKET_STRUCTURE",
                    )[index],
                    "UNREQUESTED",
                    (),
                )
                for index, slot in enumerate(captured_slots["complete"])
            ),
            mapping_binding,
        )
        assert independent.requested_features == (feature,)
        assert tuple(
            member.features[0].fact for member in independent.members
        ) == tuple(member.features[position].fact for member in complete.members)
    local = {members[index].isin for index in (0, 49, 99)}
    partial = packet(Client(local), "partial")
    assert (
        tuple(
            (item.requested, item.observed, item.insufficient, item.not_attempted)
            for item in partial.coverage
        )
        == ((100, 97, 3, 0),) * 3
    )
    assert partial.members[1:49] == complete.members[1:49]
    assert partial.members[50:99] == complete.members[50:99]
    assert partial.members[99].features[0].availability == "INSUFFICIENT_EVIDENCE"
    not_found = packet(Client(local, failure_reason="NOT_FOUND"), "not-found")
    assert tuple(item.insufficient for item in not_found.coverage) == (3, 3, 3)
    assert tuple(item.unsupported for item in not_found.coverage) == (0, 0, 0)
    unavailable = packet(Client({item.isin for item in members}), "unavailable")
    assert tuple(item.observed for item in unavailable.coverage) == (0, 0, 0)
    assert tuple(item.insufficient for item in unavailable.coverage) == (100, 100, 100)
    conflicted = packet(Client(conflict=True), "conflicted")
    assert all(
        feature.support == "CONFLICTED"
        for member in conflicted.members
        for feature in member.features
    )
    blocked = packet(Client(mismatched_adjustment=True), "blocked")
    assert tuple(item.dependency_blocked for item in blocked.coverage) == (0, 100, 100)
    assert tuple(member.features[0].fact for member in blocked.members) == tuple(
        member.features[0].fact for member in complete.members
    )
    assert all(
        member.features[0].availability == "OBSERVED"
        and tuple(item.availability for item in member.features[1:])
        == ("DEPENDENCY_BLOCKED", "DEPENDENCY_BLOCKED")
        for member in blocked.members
    )
