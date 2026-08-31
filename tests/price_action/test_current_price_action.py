"""Sprint 19 current/live Price Action MVP contracts."""

from __future__ import annotations

import sys
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext
from importlib import util
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import swing_trading_ai_assistant.price_action as price_action_package
import swing_trading_ai_assistant.price_action.current_live as current_live
import swing_trading_ai_assistant.price_action.current_same_pass as same_pass
from swing_trading_ai_assistant.market_structure.current_same_pass import (
    evaluate_current_same_pass_market_structure_v1,
)
from swing_trading_ai_assistant.price_action.current_live import (
    CurrentPriceActionMemberV1,
    CurrentPriceActionReportV1,
    current_price_action_runtime_code_identity_v1,
)


def _v3_fixture_module() -> Any:
    path = (
        Path(__file__).parents[1]
        / "market_regime"
        / "test_current_supplied_cohort_v3.py"
    )
    name = "price_action_current_supplied_cohort_v3_fixture"
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
    fixture = _v3_fixture_module()
    capture: dict[str, Any] = {}
    fixture.test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        exercise_archive_contracts=False,
        capture=capture,
        **fixture_kwargs,
    )
    return capture["candidate"].context_object, fixture


def _expected_market_structure(context: Any) -> Any:
    return evaluate_current_same_pass_market_structure_v1(
        context.request,
        context.raw_result,
        context.corporate_action_screen,
    )


def _evaluate(context: Any) -> Any:
    return same_pass.evaluate_current_same_pass_price_action_v1(
        context.request,
        context.raw_result,
        context.corporate_action_screen,
        _expected_market_structure(context),
    )


def _direction(left: Decimal, right: Decimal) -> str:
    if left > right:
        return "UP"
    if left < right:
        return "DOWN"
    return "UNCHANGED"


def test_exact_boundary_projects_only_hand_computed_s19_s20_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _ = _exact_context(tmp_path, monkeypatch)

    report = _evaluate(context)

    assert report.evidence_state == "OBSERVED"
    assert report.members is not None
    assert report.temporal_scope == "CURRENT_SAME_PASS_ONLY"
    assert report.historical_availability_claim is False
    assert report.reasons == ()
    assert len(report.members) == len(context.request.members)
    assert report.raw_grid_identity_sha256 == (
        context.raw_result.raw_grid.raw_grid_identity_sha256
    )
    assert report.corporate_action_screen_identity_sha256 == (
        context.corporate_action_screen.public_report.report_identity_sha256
    )
    assert report.market_structure_report_identity_sha256 == (
        _expected_market_structure(context).report_identity_sha256
    )

    first = report.members[0]
    assert context.raw_result.raw_grid is not None
    bars = tuple(
        bar for bar in context.raw_result.raw_grid.bars if bar.isin == first.isin
    )
    previous, current = bars[-2:]
    assert first.previous_session == previous.session
    assert first.session == current.session
    assert first.previous_bar_identity_sha256 == previous.raw_bar_identity_sha256
    assert first.current_bar_identity_sha256 == current.raw_bar_identity_sha256
    assert first.candle_direction == _direction(current.close, current.open)
    assert first.session_range_state == (
        "FLAT" if current.high == current.low else "NON_FLAT"
    )
    assert first.range_size == Decimal("4")
    assert first.body_size == Decimal("0")
    assert first.upper_wick_size == Decimal("2")
    assert first.lower_wick_size == Decimal("2")
    assert first.open_vs_previous_close == "UNCHANGED"
    assert first.open_to_previous_close_distance == Decimal("0")
    assert first.close_vs_previous_close == "UNCHANGED"
    assert first.close_to_previous_close_distance == Decimal("0")
    assert first.range_size == (
        first.upper_wick_size + first.body_size + first.lower_wick_size
    )
    assert b'"open":' not in report.canonical_json_bytes()
    assert b'"high":' not in report.canonical_json_bytes()
    assert b'"pivots":' not in report.canonical_json_bytes()


def test_asymmetric_down_candle_and_prior_close_relations_are_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(tmp_path, monkeypatch)
    raw_test = fixture._fixture_module("test_current_same_pass_daily")
    assert context.raw_result.raw_grid is not None
    grid = context.raw_result.raw_grid
    previous = raw_test._rehashed(
        type(grid.bars[-2]),
        grid.bars[-2],
        "raw_bar_identity_sha256",
        open=Decimal("100"),
        high=Decimal("100"),
        low=Decimal("100"),
        close=Decimal("100"),
    )
    current = raw_test._rehashed(
        type(grid.bars[-1]),
        grid.bars[-1],
        "raw_bar_identity_sha256",
        open=Decimal("107"),
        high=Decimal("113"),
        low=Decimal("91"),
        close=Decimal("95"),
    )
    changed_grid = raw_test._rehashed(
        type(grid),
        grid,
        "raw_grid_identity_sha256",
        bars=(*grid.bars[:-2], previous, current),
    )
    changed_raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        raw_grid=changed_grid,
    )

    report = same_pass.evaluate_current_same_pass_price_action_v1(
        context.request,
        changed_raw,
        context.corporate_action_screen,
        evaluate_current_same_pass_market_structure_v1(
            context.request,
            changed_raw,
            context.corporate_action_screen,
        ),
    )

    assert report.members is not None
    member = report.members[0]
    assert member.candle_direction == "DOWN"
    assert member.session_range_state == "NON_FLAT"
    assert (
        member.range_size,
        member.body_size,
        member.upper_wick_size,
        member.lower_wick_size,
    ) == (
        Decimal("22"),
        Decimal("12"),
        Decimal("6"),
        Decimal("4"),
    )
    assert member.open_vs_previous_close == "UP"
    assert member.open_to_previous_close_distance == Decimal("7")
    assert member.close_vs_previous_close == "DOWN"
    assert member.close_to_previous_close_distance == Decimal("5")


def test_flat_and_equality_facts_remain_observed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(tmp_path, monkeypatch)
    raw_test = fixture._fixture_module("test_current_same_pass_daily")
    assert context.raw_result.raw_grid is not None
    grid = context.raw_result.raw_grid
    flat_bar = raw_test._rehashed(
        type(grid.bars[-1]),
        grid.bars[-1],
        "raw_bar_identity_sha256",
        open=Decimal("100"),
        high=Decimal("100"),
        low=Decimal("100"),
        close=Decimal("100"),
    )
    flat_grid = raw_test._rehashed(
        type(grid), grid, "raw_grid_identity_sha256", bars=(*grid.bars[:-1], flat_bar)
    )
    flat_raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        raw_grid=flat_grid,
    )
    report = same_pass.evaluate_current_same_pass_price_action_v1(
        context.request,
        flat_raw,
        context.corporate_action_screen,
        evaluate_current_same_pass_market_structure_v1(
            context.request, flat_raw, context.corporate_action_screen
        ),
    )

    assert report.evidence_state == "OBSERVED"
    assert report.members is not None
    member = report.members[0]
    assert member.candle_direction == "UNCHANGED"
    assert member.session_range_state == "FLAT"
    assert (
        member.range_size,
        member.body_size,
        member.upper_wick_size,
        member.lower_wick_size,
        member.open_to_previous_close_distance,
        member.close_to_previous_close_distance,
    ) == (Decimal(0),) * 6
    assert member.open_vs_previous_close == "UNCHANGED"
    assert member.close_vs_previous_close == "UNCHANGED"


def test_exact_fifty_member_cohort_remains_complete_and_canonical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _ = _exact_context(
        tmp_path,
        monkeypatch,
        raw_directions=(("UNCHANGED",) * 50),
        adjusted_directions=(("UNCHANGED",) * 50),
    )

    report = _evaluate(context)

    assert report.evidence_state == "OBSERVED"
    assert report.members is not None
    assert len(report.members) == 50
    assert tuple(member.isin for member in report.members) == tuple(
        sorted(member.isin for member in context.request.members)
    )


def test_zero_and_limit_plus_one_cohorts_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _ = _exact_context(
        tmp_path,
        monkeypatch,
        raw_directions=(("UNCHANGED",) * 50),
        adjusted_directions=(("UNCHANGED",) * 50),
    )
    exact = _expected_market_structure(context)

    for members in (
        (),
        (*context.request.members, context.request.members[0]),
    ):
        invalid = deepcopy(context.request)
        object.__setattr__(invalid, "members", members)
        with pytest.raises(ValueError):
            same_pass.evaluate_current_same_pass_price_action_v1(
                invalid,
                context.raw_result,
                context.corporate_action_screen,
                exact,
            )


def test_public_member_enforces_canonical_equity_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _evaluate(_exact_context(tmp_path, monkeypatch)[0])
    assert report.members is not None
    member: CurrentPriceActionMemberV1 = report.members[0]

    with pytest.raises(ValueError):
        replace(member, isin="INVALID")
    with pytest.raises(ValueError):
        replace(member, exchange="BSE")
    with pytest.raises(ValueError):
        replace(member, effective_symbol="X" * 65)

    class CallerExchange:
        invoked = False

        def __ne__(self, other: object) -> bool:
            del other
            type(self).invoked = True
            raise RuntimeError("caller comparison must not run")

    with pytest.raises(ValueError, match="member fields"):
        replace(member, exchange=cast(Any, CallerExchange()))
    assert not CallerExchange.invoked
    with pytest.raises(ValueError, match="bounded representation"):
        replace(member, range_size=Decimal("1e129"))
    with pytest.raises(ValueError, match="bounded representation"):
        replace(member, range_size=Decimal("1" * 129))


def test_decimal_context_does_not_change_report_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _ = _exact_context(tmp_path, monkeypatch)

    with localcontext() as low_precision:
        low_precision.prec = 2
        first = _evaluate(context)
    with localcontext() as high_precision:
        high_precision.prec = 80
        second = _evaluate(context)

    assert first.canonical_json_bytes() == second.canonical_json_bytes()
    assert first.report_identity_sha256 == second.report_identity_sha256


def test_configuration_identity_binds_session_count_and_numeric_bounds() -> None:
    preimage = current_live._configuration_identity_preimage_v1()  # pyright: ignore[reportPrivateUsage]
    assert preimage["session_count"] == 21
    assert preimage["decimal_bounds"] == {
        "coefficient_digits_max": 128,
        "exponent_min": -128,
        "exponent_max": 128,
        "canonical_characters_max": 258,
    }
    mutated = {**preimage, "session_count": 22}
    assert (
        current_live.current_price_action_identity_sha256_v1(mutated, omit=frozenset())
        != current_live.CONFIGURATION_IDENTITY_SHA256_V1
    )


def test_exact_market_structure_is_required_and_natural_insufficiency_is_admissible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _ = _exact_context(tmp_path, monkeypatch)
    exact = _expected_market_structure(context)

    report = same_pass.evaluate_current_same_pass_price_action_v1(
        context.request,
        context.raw_result,
        context.corporate_action_screen,
        exact,
    )

    assert report.evidence_state == "OBSERVED"
    assert report.members is not None
    assert tuple(
        member.market_structure_member_identity_sha256 for member in report.members
    ) == tuple(member.member_identity_sha256 for member in exact.members or ())


def test_nonidentical_market_structure_returns_no_member_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _ = _exact_context(tmp_path, monkeypatch)
    substituted = deepcopy(_expected_market_structure(context))
    object.__setattr__(substituted, "runtime_code_identity_sha256", "0" * 64)
    substituted.__post_init__()

    report = same_pass.evaluate_current_same_pass_price_action_v1(
        context.request,
        context.raw_result,
        context.corporate_action_screen,
        substituted,
    )

    assert report.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert report.members is None
    assert report.raw_grid_identity_sha256 is None
    assert report.corporate_action_screen_identity_sha256 is None
    assert report.market_structure_report_identity_sha256 is None
    assert report.reasons == ("MARKET_STRUCTURE_BINDING_MISMATCH",)


def test_hostile_supplied_market_structure_is_rejected_without_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CallerScalar:
        invoked = False
        __hash__ = object.__hash__

        def __eq__(self, other: object) -> bool:
            del other
            type(self).invoked = True
            raise RuntimeError("caller callback must not run")

    context, _ = _exact_context(tmp_path, monkeypatch)
    hostile = deepcopy(_expected_market_structure(context))
    object.__setattr__(hostile, "evidence_state", CallerScalar())

    with pytest.raises(ValueError, match="Price Action caller objects"):
        same_pass.evaluate_current_same_pass_price_action_v1(
            context.request,
            context.raw_result,
            context.corporate_action_screen,
            hostile,
        )
    assert not CallerScalar.invoked


def test_combined_upstream_and_market_structure_mismatch_reasons_are_ordered(
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
    raw_test = fixture._fixture_module("test_current_same_pass_daily")
    raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        evidence_state="INSUFFICIENT_EVIDENCE",
        raw_grid=None,
        reasons=("RAW_BAR_MISSING",),
    )
    supplied = deepcopy(
        evaluate_current_same_pass_market_structure_v1(
            context.request, raw, context.corporate_action_screen
        )
    )
    object.__setattr__(supplied, "runtime_code_identity_sha256", "0" * 64)
    supplied.__post_init__()

    report = same_pass.evaluate_current_same_pass_price_action_v1(
        context.request, raw, context.corporate_action_screen, supplied
    )

    assert report.members is None
    assert report.reasons == (
        "RAW_EVIDENCE_INSUFFICIENT",
        "CORPORATE_ACTION_SCREEN_INSUFFICIENT",
        "MARKET_STRUCTURE_INSUFFICIENT",
        "MARKET_STRUCTURE_BINDING_MISMATCH",
    )


def test_upstream_insufficiency_maps_to_closed_precedence_without_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(tmp_path, monkeypatch)
    raw_test = fixture._fixture_module("test_current_same_pass_daily")
    raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        evidence_state="INSUFFICIENT_EVIDENCE",
        raw_grid=None,
        reasons=("RAW_BAR_MISSING",),
    )
    expected = evaluate_current_same_pass_market_structure_v1(
        context.request,
        raw,
        context.corporate_action_screen,
    )

    report = same_pass.evaluate_current_same_pass_price_action_v1(
        context.request,
        raw,
        context.corporate_action_screen,
        expected,
    )

    assert report.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert report.members is None
    assert report.reasons == (
        "RAW_EVIDENCE_INSUFFICIENT",
        "MARKET_STRUCTURE_INSUFFICIENT",
    )


def test_complete_upstream_reason_projection_and_price_action_precedence() -> None:
    upstream = current_live.PRICE_ACTION_REASON_ORDER_V1[:-2]
    report = SimpleNamespace(reasons=upstream)

    assert same_pass._market_structure_reasons(  # pyright: ignore[reportPrivateUsage]
        cast(Any, report)
    ) == set(upstream)
    assert (
        current_live.ordered_price_action_reasons_v1(
            {
                *upstream,
                "MARKET_STRUCTURE_INSUFFICIENT",
                "MARKET_STRUCTURE_BINDING_MISMATCH",
            }
        )
        == current_live.PRICE_ACTION_REASON_ORDER_V1
    )


def test_boundary_rejects_malformed_and_hostile_caller_values() -> None:
    class CallerValue:
        invoked = False
        __hash__ = object.__hash__

        def __eq__(self, other: object) -> bool:
            del other
            type(self).invoked = True
            raise RuntimeError("caller code must not run")

    with pytest.raises(ValueError):
        same_pass.evaluate_current_same_pass_price_action_v1(
            cast(Any, CallerValue()),
            cast(Any, object()),
            cast(Any, object()),
            cast(Any, object()),
        )
    assert not CallerValue.invoked


def test_hostile_nested_iterable_and_unbounded_decimal_stop_before_delegate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CallerIterable:
        invoked = False

        def __iter__(self) -> Any:
            type(self).invoked = True
            raise RuntimeError("caller iteration must not run")

    context, _ = _exact_context(tmp_path, monkeypatch)
    exact = _expected_market_structure(context)
    invalid = deepcopy(context.raw_result)
    object.__setattr__(invalid, "resolved_sessions", CallerIterable())
    delegated = False

    def forbidden_delegate(*arguments: object, **keywords: object) -> Any:
        nonlocal delegated
        del arguments, keywords
        delegated = True
        raise AssertionError("Market Structure delegate must not run")

    monkeypatch.setattr(
        same_pass,
        "evaluate_current_same_pass_market_structure_v1",
        forbidden_delegate,
    )
    with pytest.raises(ValueError, match="caller objects"):
        same_pass.evaluate_current_same_pass_price_action_v1(
            context.request,
            invalid,
            context.corporate_action_screen,
            exact,
        )
    assert not CallerIterable.invoked
    assert not delegated

    unbounded = deepcopy(context.raw_result)
    assert unbounded.raw_grid is not None
    object.__setattr__(unbounded.raw_grid.bars[-1], "open", Decimal("1e1000000"))
    with pytest.raises(ValueError, match="caller objects"):
        same_pass.evaluate_current_same_pass_price_action_v1(
            context.request,
            unbounded,
            context.corporate_action_screen,
            exact,
        )
    assert not delegated


def test_partial_current_session_is_metamorphically_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(tmp_path, monkeypatch, include_partial=True)
    raw_test = fixture._fixture_module("test_current_same_pass_daily")
    unavailable_partial = raw_test.raw_daily._partial_failure(
        context.request, "PARTIAL_SOURCE_UNAVAILABLE"
    )
    unavailable_raw = raw_test._rehashed(
        type(context.raw_result),
        context.raw_result,
        "raw_result_identity_sha256",
        partial_current_session=unavailable_partial,
    )
    observed = _evaluate(context)
    unavailable = same_pass.evaluate_current_same_pass_price_action_v1(
        context.request,
        unavailable_raw,
        context.corporate_action_screen,
        evaluate_current_same_pass_market_structure_v1(
            context.request,
            unavailable_raw,
            context.corporate_action_screen,
        ),
    )

    assert observed.canonical_json_bytes() == unavailable.canonical_json_bytes()
    assert observed.report_identity_sha256 == unavailable.report_identity_sha256


def test_report_constructor_and_evaluator_effect_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, fixture = _exact_context(tmp_path, monkeypatch)
    raw_test = fixture._fixture_module("test_current_same_pass_daily")

    def forbidden(*arguments: object, **keywords: object) -> None:
        del arguments, keywords
        raise AssertionError("Price Action evaluation attempted I/O")

    with pytest.raises(ValueError, match="exact evidence boundary"):
        CurrentPriceActionReportV1()
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(raw_test.raw_daily, "ZoneInfo", forbidden)

    assert _evaluate(context).evidence_state == "OBSERVED"


def test_public_exports_and_runtime_substitution_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert price_action_package.__all__ == [
        "CurrentPriceActionMemberV1",
        "CurrentPriceActionReportV1",
        "evaluate_current_same_pass_price_action_v1",
    ]

    def substituted_runtime_source(*arguments: object, **keywords: object) -> str:
        del arguments, keywords
        return "0" * 64

    monkeypatch.setattr(
        current_live,
        "runtime_source_sha256",
        substituted_runtime_source,
    )
    with pytest.raises(ValueError, match="runtime identity"):
        current_price_action_runtime_code_identity_v1()
