"""Sprint 18 current/live Market Structure MVP contracts."""

from __future__ import annotations

import sys
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, tzinfo
from decimal import Decimal, localcontext
from importlib import util
from pathlib import Path
from typing import Any, cast

import pytest

import swing_trading_ai_assistant.market_structure.current_live_runtime_identity_manifest as runtime_manifest
import swing_trading_ai_assistant.market_structure.current_same_pass_v4 as same_pass
from swing_trading_ai_assistant.market_structure.current_live import (
    CALCULATION_IDENTITY_SHA256_V1,
    SCHEMA_IDENTITY_SHA256_V1,
    CurrentMarketStructureReportV1,
    _calculation_identity_preimage_v1,  # pyright: ignore[reportPrivateUsage]
    _CurrentMarketStructureInputV1,  # pyright: ignore[reportPrivateUsage]
    _CurrentMarketStructureMemberInputV1,  # pyright: ignore[reportPrivateUsage]
    _evaluate_current_market_structure_v1,  # pyright: ignore[reportPrivateUsage]
    _MarketStructureBarV1,  # pyright: ignore[reportPrivateUsage]
    _schema_identity_preimage_v1,  # pyright: ignore[reportPrivateUsage]
    current_market_structure_identity_sha256_v1,
    current_market_structure_runtime_code_identity_v1,
)

_CUTOFF = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)
_DIGESTS = tuple(character * 64 for character in "abcdef")


def _sessions() -> tuple[date, ...]:
    result: list[date] = []
    value = date(2026, 8, 3)
    while len(result) < 21:
        if value.weekday() < 5:
            result.append(value)
        value += timedelta(days=1)
    return tuple(result)


def _bar(
    position: int,
    *,
    high: int | Decimal,
    low: int | Decimal,
    close: int | Decimal,
) -> _MarketStructureBarV1:
    high_value = Decimal(high)
    low_value = Decimal(low)
    close_value = Decimal(close)
    open_value = min(max(Decimal("100"), low_value), high_value)
    return _MarketStructureBarV1(
        session=_sessions()[position],
        open=open_value,
        high=high_value,
        low=low_value,
        close=close_value,
        volume=1000 + position,
        raw_bar_identity_sha256=f"{position + 1:064x}",
    )


def _structured_bars() -> tuple[_MarketStructureBarV1, ...]:
    highs = [
        103,
        104,
        105,
        106,
        110,
        106,
        105,
        106,
        107,
        108,
        115,
        108,
        107,
        108,
        112,
        118,
        120,
        108,
        107,
        130,
        140,
    ]
    lows = [
        97,
        96,
        95,
        94,
        93,
        92,
        90,
        92,
        93,
        94,
        96,
        96,
        95,
        96,
        97,
        98,
        97,
        93,
        94,
        95,
        96,
    ]
    closes = [
        100,
        100,
        100,
        100,
        100,
        100,
        100,
        101,
        102,
        103,
        104,
        105,
        106,
        107,
        110,
        116,
        110,
        94,
        96,
        97,
        98,
    ]
    return tuple(
        _bar(position, high=high, low=low, close=close)
        for position, (high, low, close) in enumerate(
            zip(highs, lows, closes, strict=True)
        )
    )


def _flat_bars() -> tuple[_MarketStructureBarV1, ...]:
    return tuple(
        _bar(position, high=105 + position, low=95 + position, close=100 + position)
        for position in range(21)
    )


def _uptrend_bars() -> tuple[_MarketStructureBarV1, ...]:
    bars = list(_structured_bars())
    bars[16] = replace(
        bars[16],
        high=Decimal("110"),
        raw_bar_identity_sha256="a" * 64,
    )
    bars[18] = replace(
        bars[18],
        low=Decimal("92"),
        raw_bar_identity_sha256="b" * 64,
    )
    bars[19] = replace(
        bars[19],
        low=Decimal("91"),
        raw_bar_identity_sha256="c" * 64,
    )
    return tuple(bars)


def _downtrend_bars() -> tuple[_MarketStructureBarV1, ...]:
    highs = (
        110,
        111,
        112,
        113,
        120,
        113,
        112,
        113,
        112,
        111,
        115,
        111,
        110,
        111,
        112,
        113,
        112,
        111,
        110,
        109,
        108,
    )
    lows = (
        105,
        104,
        103,
        102,
        101,
        100,
        98,
        100,
        101,
        100,
        99,
        98,
        95,
        98,
        99,
        100,
        101,
        102,
        103,
        104,
        105,
    )
    return tuple(
        _bar(
            position,
            high=high,
            low=low,
            close=(Decimal(high) + Decimal(low)) / 2,
        )
        for position, (high, low) in enumerate(zip(highs, lows, strict=True))
    )


def _member(
    *,
    isin: str = "INE002A01018",
    symbol: str = "RELIANCE",
    bars: tuple[_MarketStructureBarV1, ...] | None = None,
) -> _CurrentMarketStructureMemberInputV1:
    return _CurrentMarketStructureMemberInputV1(
        isin=isin,
        exchange="NSE",
        effective_symbol=symbol,
        bars=_structured_bars() if bars is None else bars,
    )


def _request(
    members: tuple[_CurrentMarketStructureMemberInputV1, ...] | None = None,
) -> _CurrentMarketStructureInputV1:
    return _CurrentMarketStructureInputV1(
        decision_cutoff=_CUTOFF,
        comparison_session=_sessions()[0],
        decision_session=_sessions()[-1],
        request_identity_sha256=_DIGESTS[0],
        canonical_cohort_identity_sha256=_DIGESTS[1],
        schedule_identity_sha256=_DIGESTS[2],
        raw_grid_identity_sha256=_DIGESTS[4],
        corporate_action_screen_identity_sha256=_DIGESTS[5],
        members=(_member(),) if members is None else members,
    )


def test_observed_structure_freezes_confirmed_relations_and_close_breaks() -> None:
    report = _evaluate_current_market_structure_v1(_request())

    assert report.evidence_state == "OBSERVED"
    assert report.temporal_scope == "CURRENT_SAME_PASS_ONLY"
    assert report.historical_availability_claim is False
    assert report.reasons == ()
    assert report.members is not None
    member = report.members[0]

    assert [
        (pivot.kind, pivot.relation, pivot.unclassified_reason)
        for pivot in member.pivots
    ] == [
        ("SWING_HIGH", None, "INITIAL"),
        ("SWING_LOW", None, "INITIAL"),
        ("SWING_HIGH", "HH", None),
        ("SWING_LOW", "HL", None),
        ("SWING_HIGH", "HH", None),
        ("SWING_LOW", "LL", None),
    ]
    assert [
        (event.event, event.direction, event.session) for event in member.events
    ] == [
        ("BOS", "UP", _sessions()[15]),
        ("CHOCH", "DOWN", _sessions()[17]),
    ]
    assert member.trend == "RANGE_OR_TRANSITION"
    assert member.structure_state == "CONFIRMED"
    assert all(pivot.position <= 18 for pivot in member.pivots)


def test_break_uses_only_pivots_confirmed_before_event_session() -> None:
    bars = list(_structured_bars())
    bars[13] = replace(
        bars[13],
        high=Decimal("120"),
        raw_bar_identity_sha256="8" * 64,
    )
    bars[15] = replace(
        bars[15],
        high=Decimal("118"),
        close=Decimal("116"),
        raw_bar_identity_sha256="9" * 64,
    )

    report = _evaluate_current_market_structure_v1(
        _request((_member(bars=tuple(bars)),))
    )

    assert report.members is not None
    assert any(
        event.event == "BOS"
        and event.direction == "UP"
        and event.position == 15
        and event.broken_level == Decimal("115")
        for event in report.members[0].events
    )


def test_strict_tie_and_right_edge_never_create_pivots() -> None:
    bars = list(_structured_bars())
    bars[3] = replace(bars[3], high=bars[4].high, raw_bar_identity_sha256="f" * 64)
    report = _evaluate_current_market_structure_v1(
        _request((_member(bars=tuple(bars)),))
    )
    assert report.members is not None
    pivots = report.members[0].pivots

    assert _sessions()[4] not in {pivot.session for pivot in pivots}
    assert _sessions()[19] not in {pivot.session for pivot in pivots}
    assert _sessions()[20] not in {pivot.session for pivot in pivots}


def test_natural_lack_of_pivots_is_observed_insufficient_structure() -> None:
    report = _evaluate_current_market_structure_v1(
        _request((_member(bars=_flat_bars()),))
    )
    assert report.evidence_state == "OBSERVED"
    assert report.members is not None
    member = report.members[0]
    assert member.pivots == ()
    assert member.events == ()
    assert member.trend == "INSUFFICIENT_STRUCTURE"
    assert member.structure_state == "INSUFFICIENT_STRUCTURE"
    assert report.reasons == ()


def test_member_permutation_is_canonical_and_byte_stable() -> None:
    first = _member()
    second = _member(isin="INE040A01034", symbol="HDFCBANK", bars=_flat_bars())

    forward = _evaluate_current_market_structure_v1(_request((first, second)))
    reverse = _evaluate_current_market_structure_v1(_request((second, first)))

    assert forward == reverse
    assert forward.canonical_json_bytes() == reverse.canonical_json_bytes()
    assert forward.report_identity_sha256 == reverse.report_identity_sha256


def test_schema_and_calculation_identities_bind_modeled_semantics() -> None:
    schema = _schema_identity_preimage_v1()
    changed_schema = deepcopy(schema)
    cast(dict[str, object], changed_schema["pivot"])["kind"] = "OTHER"
    assert (
        current_market_structure_identity_sha256_v1(changed_schema, omit=frozenset())
        != SCHEMA_IDENTITY_SHA256_V1
    )

    calculation = _calculation_identity_preimage_v1()
    changed_calculation = deepcopy(calculation)
    cast(dict[str, object], changed_calculation["break"])["eligible_pivot"] = (
        "confirmation_position<=break_position"
    )
    assert (
        current_market_structure_identity_sha256_v1(
            changed_calculation, omit=frozenset()
        )
        != CALCULATION_IDENTITY_SHA256_V1
    )


def test_large_decimal_price_serializes_as_fixed_point() -> None:
    bars = list(_structured_bars())
    bars[4] = replace(
        bars[4],
        high=Decimal("1E+50"),
        raw_bar_identity_sha256="7" * 64,
    )
    report = _evaluate_current_market_structure_v1(
        _request((_member(bars=tuple(bars)),))
    )

    serialized = report.canonical_json_bytes()
    assert b"100000000000000000000000000000000000000000000000000" in serialized
    assert b"1E+50" not in serialized


def test_decimal_serialization_is_independent_of_ambient_precision() -> None:
    bars = list(_structured_bars())
    bars[4] = replace(
        bars[4],
        high=Decimal("12345678901234567890.1234500"),
        raw_bar_identity_sha256="6" * 64,
    )
    request = _request((_member(bars=tuple(bars)),))

    with localcontext() as context:
        context.prec = 6
        low_precision = _evaluate_current_market_structure_v1(request)
    with localcontext() as context:
        context.prec = 50
        high_precision = _evaluate_current_market_structure_v1(request)

    assert low_precision.canonical_json_bytes() == high_precision.canonical_json_bytes()
    assert low_precision.report_identity_sha256 == high_precision.report_identity_sha256


def test_report_constructor_cannot_mint_observed_evidence() -> None:
    with pytest.raises(ValueError, match="exact evidence boundary"):
        CurrentMarketStructureReportV1()


def test_pure_evaluator_performs_no_filesystem_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*arguments: object, **keywords: object) -> None:
        del arguments, keywords
        raise AssertionError("pure Market Structure evaluator attempted filesystem I/O")

    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)

    report = _evaluate_current_market_structure_v1(_request())
    assert report.evidence_state == "OBSERVED"


def test_covered_runtime_source_digest_substitution_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "src/swing_trading_ai_assistant/market_structure/current_live.py"
    monkeypatch.setitem(
        runtime_manifest.CURRENT_MARKET_STRUCTURE_RUNTIME_SOURCE_DIGESTS_V1,
        path,
        "0" * 64,
    )
    with pytest.raises(ValueError, match="runtime identity invalid"):
        current_market_structure_runtime_code_identity_v1()


@pytest.mark.parametrize("count", (0, 20, 22))
def test_input_rejects_empty_or_non_twenty_one_session_grid(count: int) -> None:
    bars = _flat_bars()[:count]
    if count == 22:
        final = bars[-1]
        bars += (
            replace(
                final,
                session=final.session + timedelta(days=1),
                raw_bar_identity_sha256="c" * 64,
            ),
        )
    with pytest.raises(ValueError, match="market structure member input"):
        _member(bars=bars)


def test_equal_same_kind_pivot_is_explicit_not_forced_relation() -> None:
    bars = list(_structured_bars())
    bars[10] = replace(bars[10], high=Decimal("110"), raw_bar_identity_sha256="e" * 64)
    report = _evaluate_current_market_structure_v1(
        _request((_member(bars=tuple(bars)),))
    )
    assert report.members is not None
    equal = [
        pivot
        for pivot in report.members[0].pivots
        if pivot.kind == "SWING_HIGH" and pivot.session == _sessions()[10]
    ]
    assert len(equal) == 1
    assert equal[0].relation is None
    assert equal[0].unclassified_reason == "EQUAL_PRICE"


def test_wick_without_close_crossing_emits_no_break() -> None:
    bars = list(_structured_bars())
    bars[15] = replace(bars[15], close=Decimal("114"), raw_bar_identity_sha256="d" * 64)
    report = _evaluate_current_market_structure_v1(
        _request((_member(bars=tuple(bars)),))
    )
    assert report.members is not None
    assert not any(
        event.session == _sessions()[15] for event in report.members[0].events
    )


def test_confirmed_level_is_consumed_after_first_close_crossing() -> None:
    bars = list(_structured_bars())
    bars[14] = replace(
        bars[14],
        high=Decimal("118"),
        raw_bar_identity_sha256="1" * 64,
    )
    bars[16] = replace(
        bars[16],
        high=Decimal("110"),
        raw_bar_identity_sha256="2" * 64,
    )
    bars[18] = replace(
        bars[18],
        high=Decimal("117"),
        close=Decimal("116"),
        raw_bar_identity_sha256="3" * 64,
    )
    report = _evaluate_current_market_structure_v1(
        _request((_member(bars=tuple(bars)),))
    )
    assert report.members is not None
    assert [
        event.position
        for event in report.members[0].events
        if event.direction == "UP" and event.broken_level == Decimal("115")
    ] == [15]


def test_older_unconsumed_level_remains_available_after_newer_cross() -> None:
    bars = list(_downtrend_bars())
    bars[15] = replace(
        bars[15],
        high=Decimal("117"),
        close=Decimal("116"),
        raw_bar_identity_sha256="4" * 64,
    )
    bars[17] = replace(
        bars[17],
        high=Decimal("122"),
        close=Decimal("121"),
        raw_bar_identity_sha256="5" * 64,
    )

    report = _evaluate_current_market_structure_v1(
        _request((_member(bars=tuple(bars)),))
    )

    assert report.members is not None
    assert [
        (event.event, event.direction, event.position, event.broken_level)
        for event in report.members[0].events
        if event.direction == "UP"
    ] == [
        ("CHOCH", "UP", 15, Decimal("115")),
        ("CHOCH", "UP", 17, Decimal("120")),
    ]


def test_downtrend_event_table_emits_bos_down_and_choch_up() -> None:
    bars = list(_downtrend_bars())
    bars[15] = replace(
        bars[15],
        low=Decimal("94"),
        close=Decimal("94"),
        raw_bar_identity_sha256="4" * 64,
    )
    bars[17] = replace(
        bars[17],
        high=Decimal("117"),
        close=Decimal("116"),
        raw_bar_identity_sha256="5" * 64,
    )

    report = _evaluate_current_market_structure_v1(
        _request((_member(bars=tuple(bars)),))
    )

    assert report.members is not None
    assert [
        (event.event, event.direction, event.position)
        for event in report.members[0].events
    ] == [("BOS", "DOWN", 15), ("CHOCH", "UP", 17)]


def test_trend_truth_table_is_exact_and_non_scored() -> None:
    members = (
        _member(isin="UP", symbol="UP", bars=_uptrend_bars()),
        _member(isin="DOWN", symbol="DOWN", bars=_downtrend_bars()),
        _member(isin="MIXED", symbol="MIXED", bars=_structured_bars()),
    )
    report = _evaluate_current_market_structure_v1(_request(members))
    assert report.members is not None
    assert {member.effective_symbol: member.trend for member in report.members} == {
        "UP": "UPTREND",
        "DOWN": "DOWNTREND",
        "MIXED": "RANGE_OR_TRANSITION",
    }


def test_exact_fifty_member_bound_is_complete_and_fifty_one_is_rejected() -> None:
    members = tuple(
        _member(
            isin=f"ISIN{position:02d}", symbol=f"EQ{position:02d}", bars=_flat_bars()
        )
        for position in range(50)
    )
    report = _evaluate_current_market_structure_v1(_request(members))
    assert report.members is not None
    assert len(report.members) == 50

    with pytest.raises(ValueError, match="1 to 50 members"):
        _request(members + (_member(isin="ISIN50", symbol="EQ50", bars=_flat_bars()),))


def _v4_fixture_module() -> Any:
    path = (
        Path(__file__).parents[1]
        / "market_regime"
        / "test_current_supplied_cohort_v4.py"
    )
    name = "market_structure_current_supplied_cohort_v4_fixture"
    spec = util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _exact_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    **fixture_kwargs: Any,
) -> tuple[Any, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    fixture = _v4_fixture_module()
    capture: dict[str, Any] = {}
    fixture.test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        exercise_archive_contracts=False,
        capture=capture,
        **fixture_kwargs,
    )
    return capture["candidate"].context_object, fixture


def test_exact_same_pass_boundary_projects_validated_completed_grid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _ = _exact_context(tmp_path, monkeypatch)

    report = same_pass.evaluate_current_same_pass_market_structure_v4(
        context.request,
        context.raw_result,
        context.corporate_action_screen,
    )

    assert report.evidence_state == "OBSERVED"
    assert report.members is not None
    assert tuple(member.isin for member in report.members) == tuple(
        member.isin for member in context.request.members
    )
    assert report.comparison_session == context.raw_result.comparison_session
    assert report.decision_session == context.raw_result.decision_session
    assert report.raw_grid_identity_sha256 == (
        context.raw_result.raw_grid.raw_grid_identity_sha256
    )
    assert report.canonical_json_bytes().endswith(b"\n")


def test_same_pass_boundary_reports_cross_input_failures_in_frozen_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, _ = _exact_context(tmp_path / "first", monkeypatch)
    second, _ = _exact_context(
        tmp_path / "second",
        monkeypatch,
        raw_directions=("UP", "UP"),
        adjusted_directions=("UP", "UP"),
    )

    report = same_pass.evaluate_current_same_pass_market_structure_v4(
        first.request,
        second.raw_result,
        second.corporate_action_screen,
    )

    assert report.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert report.members is None
    assert report.reasons == (
        "RAW_RESULT_BINDING_MISMATCH",
        "RAW_GRID_BINDING_MISMATCH",
        "MEMBER_GRID_INCOMPLETE",
        "CORPORATE_ACTION_SCREEN_BINDING_MISMATCH",
    )
    assert report.raw_grid_identity_sha256 is None
    assert report.corporate_action_screen_identity_sha256 is None


def test_same_pass_boundary_rejects_malformed_caller_objects() -> None:
    with pytest.raises(ValueError, match="caller objects"):
        same_pass.evaluate_current_same_pass_market_structure_v4(
            cast(Any, object()),
            cast(Any, object()),
            cast(Any, object()),
        )


def test_exact_boundary_maps_valid_raw_insufficiency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(tmp_path, monkeypatch)
    raw_test = fixture._fixture_module("test_current_same_pass_daily_v4")
    raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        evidence_state="INSUFFICIENT_EVIDENCE",
        raw_grid=None,
        reasons=("RAW_BAR_MISSING",),
    )
    assert raw_test.raw_daily.current_same_pass_raw_daily_result_is_exact_valid_v4(
        raw, context.request
    )

    report = same_pass.evaluate_current_same_pass_market_structure_v4(
        context.request,
        raw,
        context.corporate_action_screen,
    )

    assert report.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert report.reasons == ("RAW_EVIDENCE_INSUFFICIENT",)


def test_exact_boundary_maps_valid_unavailable_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _ = _exact_context(
        tmp_path,
        monkeypatch,
        screen_retain=False,
        expected_plan22_calls=0,
        expected_effects=("raw-mapping", "screen"),
        expect_archive_failure=True,
    )

    report = same_pass.evaluate_current_same_pass_market_structure_v4(
        context.request,
        context.raw_result,
        context.corporate_action_screen,
    )

    assert report.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert report.reasons == ("CORPORATE_ACTION_SCREEN_INSUFFICIENT",)


def test_partial_current_session_state_is_not_projected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(
        tmp_path,
        monkeypatch,
        include_partial=True,
    )
    raw_test = fixture._fixture_module("test_current_same_pass_daily_v4")
    unavailable_partial = raw_test.raw_daily._partial_failure(
        context.request, "PARTIAL_SOURCE_UNAVAILABLE"
    )
    unavailable_raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        partial_current_session=unavailable_partial,
    )
    assert raw_test.raw_daily.current_same_pass_raw_daily_result_is_exact_valid_v4(
        unavailable_raw, context.request
    )

    observed = same_pass.evaluate_current_same_pass_market_structure_v4(
        context.request,
        context.raw_result,
        context.corporate_action_screen,
    )
    unavailable = same_pass.evaluate_current_same_pass_market_structure_v4(
        context.request,
        unavailable_raw,
        context.corporate_action_screen,
    )

    assert observed.canonical_json_bytes() == unavailable.canonical_json_bytes()
    assert observed.report_identity_sha256 == unavailable.report_identity_sha256


def test_partial_row_known_at_must_equal_snapshot_known_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(
        tmp_path,
        monkeypatch,
        include_partial=True,
    )
    raw_test = fixture._fixture_module("test_current_same_pass_daily_v4")
    partial = context.raw_result.partial_current_session
    assert partial.rows is not None and partial.as_of is not None
    changed_row = raw_test._rehashed(
        type(partial.rows[0]),
        partial.rows[0],
        "partial_current_session_row_identity_sha256",
        known_at=partial.as_of,
    )
    changed_partial = raw_test._rehashed(
        type(partial),
        partial,
        "partial_snapshot_identity_sha256",
        rows=(changed_row,),
    )
    raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        partial_current_session=changed_partial,
    )

    report = same_pass.evaluate_current_same_pass_market_structure_v4(
        context.request,
        raw,
        context.corporate_action_screen,
    )

    assert report.reasons == ("RAW_RESULT_BINDING_MISMATCH",)


def test_partial_mapping_substitution_returns_reasons_instead_of_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(
        tmp_path / "first",
        monkeypatch,
        include_partial=True,
    )
    foreign, _ = _exact_context(
        tmp_path / "foreign",
        monkeypatch,
        include_partial=True,
        raw_directions=("UP", "UP"),
        adjusted_directions=("UP", "UP"),
    )
    raw_test = fixture._fixture_module("test_current_same_pass_daily_v4")
    assert foreign.raw_result.mapping_receipts is not None
    raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        mapping_receipts=(foreign.raw_result.mapping_receipts[-1],),
    )

    report = same_pass.evaluate_current_same_pass_market_structure_v4(
        context.request,
        raw,
        context.corporate_action_screen,
    )

    assert report.reasons == (
        "RAW_RESULT_BINDING_MISMATCH",
        "RAW_GRID_BINDING_MISMATCH",
    )


def test_include_partial_rejects_not_requested_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(
        tmp_path,
        monkeypatch,
        include_partial=True,
    )
    raw_test = fixture._fixture_module("test_current_same_pass_daily_v4")
    not_requested = raw_test.raw_daily._not_requested_partial()
    raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        partial_current_session=not_requested,
    )

    report = same_pass.evaluate_current_same_pass_market_structure_v4(
        context.request,
        raw,
        context.corporate_action_screen,
    )

    assert report.reasons == ("RAW_RESULT_BINDING_MISMATCH",)


def test_intrinsically_invalid_partial_row_raises_before_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(
        tmp_path,
        monkeypatch,
        include_partial=True,
    )
    raw_test = fixture._fixture_module("test_current_same_pass_daily_v4")
    partial = context.raw_result.partial_current_session
    assert partial.rows is not None
    row = deepcopy(partial.rows[0])
    object.__setattr__(row, "provider", "YFINANCE")
    object.__setattr__(
        row,
        "partial_current_session_row_identity_sha256",
        raw_test.raw_daily._identity(
            row, "partial_current_session_row_identity_sha256"
        ),
    )
    changed_partial = raw_test._rehashed(
        type(partial),
        partial,
        "partial_snapshot_identity_sha256",
        rows=(row,),
    )
    raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        partial_current_session=changed_partial,
    )

    with pytest.raises(ValueError, match="caller objects"):
        same_pass.evaluate_current_same_pass_market_structure_v4(
            context.request,
            raw,
            context.corporate_action_screen,
        )


def test_raw_session_with_invalid_seal_raises_before_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(tmp_path, monkeypatch)
    raw_test = fixture._fixture_module("test_current_same_pass_daily_v4")
    changed_session = deepcopy(context.raw_result.resolved_sessions[0])
    object.__setattr__(changed_session, "session_identity_sha256", "0" * 64)
    raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        resolved_sessions=(
            changed_session,
            *context.raw_result.resolved_sessions[1:],
        ),
    )

    with pytest.raises(ValueError, match="caller objects"):
        same_pass.evaluate_current_same_pass_market_structure_v4(
            context.request,
            raw,
            context.corporate_action_screen,
        )


@pytest.mark.parametrize(
    "substituted_field",
    (
        "schema_identity_sha256",
        "latest_completed_session_resolution_identity_sha256",
        "raw_mapping_set_identity_sha256",
    ),
)
def test_raw_grid_contract_substitution_has_independent_binding_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted_field: str,
) -> None:
    context, fixture = _exact_context(tmp_path, monkeypatch)
    raw_test = fixture._fixture_module("test_current_same_pass_daily_v4")
    assert context.raw_result.raw_grid is not None
    grid = raw_test._rehashed(
        type(context.raw_result.raw_grid),
        context.raw_result.raw_grid,
        "raw_grid_identity_sha256",
        **{substituted_field: "0" * 64},
    )
    raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        raw_grid=grid,
    )

    report = same_pass.evaluate_current_same_pass_market_structure_v4(
        context.request,
        raw,
        context.corporate_action_screen,
    )

    assert report.reasons == ("RAW_GRID_BINDING_MISMATCH",)


def test_source_binding_conflict_does_not_mask_later_future_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(tmp_path, monkeypatch)
    raw_test = fixture._fixture_module("test_current_same_pass_daily_v4")
    assert context.raw_result.raw_grid is not None
    original_grid = context.raw_result.raw_grid

    first_source = raw_test._rehashed(
        type(original_grid.source_rows[0]),
        original_grid.source_rows[0],
        "source_receipt_identity_sha256",
        plan_symbol="WRONG",
    )
    first_bar = raw_test._rehashed(
        type(original_grid.bars[0]),
        original_grid.bars[0],
        "raw_bar_identity_sha256",
        source_receipt_identity_sha256=first_source.source_receipt_identity_sha256,
    )
    last_source = raw_test._rehashed(
        type(original_grid.source_rows[-1]),
        original_grid.source_rows[-1],
        "source_receipt_identity_sha256",
        query_completed_at=context.request.decision_cutoff + timedelta(microseconds=1),
    )
    last_bar = raw_test._rehashed(
        type(original_grid.bars[-1]),
        original_grid.bars[-1],
        "raw_bar_identity_sha256",
        source_receipt_identity_sha256=last_source.source_receipt_identity_sha256,
    )
    grid = raw_test._rehashed(
        type(original_grid),
        original_grid,
        "raw_grid_identity_sha256",
        source_rows=(
            first_source,
            *original_grid.source_rows[1:-1],
            last_source,
        ),
        bars=(first_bar, *original_grid.bars[1:-1], last_bar),
    )
    raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        raw_grid=grid,
    )

    report = same_pass.evaluate_current_same_pass_market_structure_v4(
        context.request,
        raw,
        context.corporate_action_screen,
    )

    assert report.reasons == (
        "RAW_GRID_BINDING_MISMATCH",
        "RAW_BAR_FUTURE_KNOWN",
    )


def test_exact_boundary_rejects_intrinsically_malformed_inner_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _ = _exact_context(tmp_path, monkeypatch)
    raw = deepcopy(context.raw_result)
    object.__setattr__(raw, "request_identity_sha256", "f" * 64)

    with pytest.raises(ValueError, match="caller objects"):
        same_pass.evaluate_current_same_pass_market_structure_v4(
            context.request,
            raw,
            context.corporate_action_screen,
        )


def test_exact_boundary_rejects_intrinsically_malformed_request_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _ = _exact_context(tmp_path, monkeypatch)
    request = deepcopy(context.request)
    object.__setattr__(
        request.members[0],
        "provider_mapping_revision",
        "invalid revision",
    )

    with pytest.raises(ValueError, match="caller objects"):
        same_pass.evaluate_current_same_pass_market_structure_v4(
            request,
            context.raw_result,
            context.corporate_action_screen,
        )


def test_exact_boundary_never_invokes_caller_nested_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CallerMember:
        invoked = False

        def __post_init__(self) -> None:
            type(self).invoked = True
            raise RuntimeError("caller code executed")

    context, _ = _exact_context(tmp_path, monkeypatch)
    request = deepcopy(context.request)
    object.__setattr__(request, "members", (CallerMember(),))

    with pytest.raises(ValueError, match="caller objects"):
        same_pass.evaluate_current_same_pass_market_structure_v4(
            request,
            context.raw_result,
            context.corporate_action_screen,
        )
    assert not CallerMember.invoked


def test_exact_boundary_never_invokes_caller_nested_scalar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CallerScalar:
        invoked = False

        def __ne__(self, other: object) -> bool:
            type(self).invoked = True
            raise RuntimeError(f"caller comparison executed against {other}")

    context, _ = _exact_context(tmp_path, monkeypatch)
    request = deepcopy(context.request)
    object.__setattr__(request.members[0], "exchange", CallerScalar())

    with pytest.raises(ValueError, match="caller objects"):
        same_pass.evaluate_current_same_pass_market_structure_v4(
            request,
            context.raw_result,
            context.corporate_action_screen,
        )
    assert not CallerScalar.invoked


def test_exact_boundary_never_invokes_caller_request_scalar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CallerScalar:
        invoked = False

        def __ne__(self, other: object) -> bool:
            type(self).invoked = True
            raise RuntimeError(f"caller comparison executed against {other}")

    context, _ = _exact_context(tmp_path, monkeypatch)
    request = deepcopy(context.request)
    object.__setattr__(request, "contract_version", CallerScalar())

    with pytest.raises(ValueError, match="caller objects"):
        same_pass.evaluate_current_same_pass_market_structure_v4(
            request,
            context.raw_result,
            context.corporate_action_screen,
        )
    assert not CallerScalar.invoked


def test_exact_boundary_never_invokes_caller_timezone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CallerTimezone(tzinfo):
        invoked = False

        def utcoffset(self, value: datetime | None) -> timedelta:
            type(self).invoked = True
            raise RuntimeError(f"caller timezone executed for {type(value)}")

    context, _ = _exact_context(tmp_path, monkeypatch)
    request = deepcopy(context.request)
    hostile_cutoff = datetime(2026, 8, 24, 10, tzinfo=CallerTimezone())
    assert not CallerTimezone.invoked
    object.__setattr__(request, "decision_cutoff", hostile_cutoff)

    with pytest.raises(ValueError, match="caller objects"):
        same_pass.evaluate_current_same_pass_market_structure_v4(
            request,
            context.raw_result,
            context.corporate_action_screen,
        )
    assert not CallerTimezone.invoked


def test_raw_bar_rejects_provider_or_price_basis_mix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _ = _exact_context(tmp_path, monkeypatch)
    assert context.raw_result.raw_grid is not None
    bar = context.raw_result.raw_grid.bars[0]

    with pytest.raises(ValueError, match="invalid same-pass raw bar"):
        replace(bar, provider="YFINANCE")


def test_string_ohlc_is_malformed_even_when_screen_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(
        tmp_path,
        monkeypatch,
        screen_retain=False,
        expected_plan22_calls=0,
        expected_effects=("raw-mapping", "screen"),
        expect_archive_failure=True,
    )
    raw_test = fixture._fixture_module("test_current_same_pass_daily_v4")
    assert context.raw_result.raw_grid is not None
    grid = context.raw_result.raw_grid
    original = grid.bars[0]
    string_bar = raw_test._rehashed(
        type(original),
        original,
        "raw_bar_identity_sha256",
        open="100",
        high="102",
        low="098",
        close="101",
    )
    string_grid = raw_test._rehashed(
        type(grid),
        grid,
        "raw_grid_identity_sha256",
        bars=(string_bar, *grid.bars[1:]),
    )
    string_raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        raw_grid=string_grid,
    )

    with pytest.raises(ValueError, match="caller objects"):
        same_pass.evaluate_current_same_pass_market_structure_v4(
            context.request,
            string_raw,
            context.corporate_action_screen,
        )


def test_exact_boundary_performs_no_evaluation_time_filesystem_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, fixture = _exact_context(tmp_path, monkeypatch)
    raw_test = fixture._fixture_module("test_current_same_pass_daily_v4")

    def forbidden(*arguments: object, **keywords: object) -> None:
        del arguments, keywords
        raise AssertionError("exact Market Structure boundary attempted filesystem I/O")

    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(raw_test.raw_daily, "ZoneInfo", forbidden)

    report = same_pass.evaluate_current_same_pass_market_structure_v4(
        context.request,
        context.raw_result,
        context.corporate_action_screen,
    )
    assert report.evidence_state == "OBSERVED"
