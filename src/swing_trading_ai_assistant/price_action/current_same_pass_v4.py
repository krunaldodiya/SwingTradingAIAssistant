"""Exact current same-pass evidence projection into current/live Price Action."""

from __future__ import annotations

import types
from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import (
    Annotated,
    Any,
    Final,
    Literal,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from swing_trading_ai_assistant.market_data.current_corporate_action_screen import (
    PublishedCurrentCorporateActionScreenV1,
)
from swing_trading_ai_assistant.market_data.current_same_pass_daily_v4 import (
    CurrentSamePassMarketRegimeRequestV4,
    PrivateCurrentSamePassRawDailyResultV1,
)
from swing_trading_ai_assistant.market_structure.current_live import (
    CurrentMarketStructureMemberV1,
    CurrentMarketStructureReportV1,
    MarketStructureEventV1,
    MarketStructurePivotV1,
    current_market_structure_identity_sha256_v1,
    ordered_market_structure_reasons_v1,
)
from swing_trading_ai_assistant.market_structure.current_same_pass_v4 import (
    evaluate_current_same_pass_market_structure_v4,
)
from swing_trading_ai_assistant.price_action.current_live import (
    PRICE_ACTION_BYTES_MAX_V1,
    PRICE_ACTION_COHORT_SIZE_MAX_V1,
    PRICE_ACTION_COHORT_SIZE_MIN_V1,
    PRICE_ACTION_GRAPH_DEPTH_MAX_V1,
    PRICE_ACTION_GRAPH_NODES_MAX_V1,
    PRICE_ACTION_INTEGER_BITS_MAX_V1,
    PRICE_ACTION_MARKET_STRUCTURE_EVENTS_PER_MEMBER_MAX_V1,
    PRICE_ACTION_MARKET_STRUCTURE_PIVOTS_PER_MEMBER_MAX_V1,
    PRICE_ACTION_SESSION_COUNT_V1,  # pyright: ignore[reportPrivateUsage]
    PRICE_ACTION_STRING_BYTES_MAX_V1,
    PRICE_ACTION_STRING_CHARACTERS_MAX_V1,
    PRICE_ACTION_TUPLE_ITEMS_MAX_V1,
    CurrentPriceActionMemberV1,
    CurrentPriceActionReportV1,
    _absolute_exact_difference,  # pyright: ignore[reportPrivateUsage]
    _direction,  # pyright: ignore[reportPrivateUsage]
    _exact_difference,  # pyright: ignore[reportPrivateUsage]
    _finite_decimal_parts,  # pyright: ignore[reportPrivateUsage]
    _mint_current_price_action_report_v1,  # pyright: ignore[reportPrivateUsage]
    _positive_exact_difference_is_bounded,  # pyright: ignore[reportPrivateUsage]
    _positive_finite_decimal,  # pyright: ignore[reportPrivateUsage]
    ordered_price_action_reasons_v1,
)


def _resolved_type_hints(expected_type: type[Any]) -> dict[str, Any]:
    return get_type_hints(expected_type)


def _safe_typed_value(  # noqa: C901
    value: object,
    expected_type: Any,
    *,
    depth: int,
    remaining: list[int],
) -> bool:
    if depth > PRICE_ACTION_GRAPH_DEPTH_MAX_V1 or remaining[0] <= 0:
        return False
    remaining[0] -= 1
    origin = get_origin(expected_type)
    arguments = get_args(expected_type)
    if origin is Literal:
        return any(
            type(value) is type(option) and value == option for option in arguments
        )
    if origin in (Annotated, Final):
        return _safe_typed_value(
            value,
            arguments[0],
            depth=depth + 1,
            remaining=remaining,
        )
    if origin in (Union, types.UnionType):
        return any(
            _safe_typed_value(
                value,
                option,
                depth=depth + 1,
                remaining=remaining,
            )
            for option in arguments
        )
    if origin is tuple:
        if type(value) is not tuple:
            return False
        tuple_value = cast(tuple[object, ...], value)
        if len(tuple_value) > PRICE_ACTION_TUPLE_ITEMS_MAX_V1:
            return False
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return all(
                _safe_typed_value(
                    item,
                    arguments[0],
                    depth=depth + 1,
                    remaining=remaining,
                )
                for item in tuple_value
            )
        return len(tuple_value) == len(arguments) and all(
            _safe_typed_value(
                item,
                item_type,
                depth=depth + 1,
                remaining=remaining,
            )
            for item, item_type in zip(tuple_value, arguments, strict=True)
        )
    if origin is list:
        if type(value) is not list:
            return False
        list_value = cast(list[object], value)
        return len(list_value) <= PRICE_ACTION_TUPLE_ITEMS_MAX_V1 and all(
            _safe_typed_value(
                item,
                arguments[0],
                depth=depth + 1,
                remaining=remaining,
            )
            for item in list_value
        )
    if origin is dict:
        if type(value) is not dict:
            return False
        dict_value = cast(dict[object, object], value)
        return len(dict_value) <= PRICE_ACTION_TUPLE_ITEMS_MAX_V1 and all(
            _safe_typed_value(
                key,
                arguments[0],
                depth=depth + 1,
                remaining=remaining,
            )
            and _safe_typed_value(
                item,
                arguments[1],
                depth=depth + 1,
                remaining=remaining,
            )
            for key, item in dict_value.items()
        )
    if expected_type is type(None):
        return value is None
    if expected_type is Any:
        return False
    if expected_type is object:
        return type(value) is object
    if expected_type is str:
        return (
            type(value) is str
            and len(value) <= PRICE_ACTION_STRING_CHARACTERS_MAX_V1
            and len(value.encode("utf-8")) <= PRICE_ACTION_STRING_BYTES_MAX_V1
        )
    if expected_type is bytes:
        return type(value) is bytes and len(value) <= PRICE_ACTION_BYTES_MAX_V1
    if expected_type is bool:
        return type(value) is bool
    if expected_type is int:
        return (
            type(value) is int
            and value.bit_length() <= PRICE_ACTION_INTEGER_BITS_MAX_V1
        )
    if expected_type is float:
        return type(value) is float and value == value and abs(value) != float("inf")
    if expected_type is Decimal:
        if type(value) is not Decimal:
            return False
        try:
            _finite_decimal_parts(value)
        except ValueError:
            return False
        return True
    if expected_type is datetime:
        return (
            type(value) is datetime and object.__getattribute__(value, "tzinfo") is UTC
        )
    if expected_type is date:
        return type(value) is date
    if isinstance(expected_type, type) and issubclass(expected_type, Enum):
        return type(value) is expected_type
    if not (
        isinstance(expected_type, type)
        and is_dataclass(expected_type)
        and type(value) is expected_type
    ):
        return False
    hints = _resolved_type_hints(expected_type)
    return all(
        field.name in hints
        and _safe_typed_value(
            object.__getattribute__(value, field.name),
            hints[field.name],
            depth=depth + 1,
            remaining=remaining,
        )
        for field in fields(expected_type)
    )


def _derived_price_action_values_are_bounded(
    request: CurrentSamePassMarketRegimeRequestV4,
    raw: PrivateCurrentSamePassRawDailyResultV1,
) -> bool:
    grid = raw.raw_grid
    if grid is None:
        return True
    for member in request.members:
        bars = tuple(bar for bar in grid.bars if bar.isin == member.isin)
        if len(bars) != PRICE_ACTION_SESSION_COUNT_V1:
            return False
        previous, current = bars[-2:]
        pairs = (
            (current.high, current.low),
            (current.high, current.open),
            (current.high, current.close),
            (current.close, current.open),
            (current.open, current.low),
            (current.close, current.low),
            (current.open, previous.close),
            (current.close, previous.close),
        )
        if not all(
            _positive_exact_difference_is_bounded(left, right) for left, right in pairs
        ):
            return False
    return True


def _market_structure_member_resources_are_bounded(
    members: tuple[CurrentMarketStructureMemberV1, ...],
) -> bool:
    return PRICE_ACTION_COHORT_SIZE_MIN_V1 <= len(
        members
    ) <= PRICE_ACTION_COHORT_SIZE_MAX_V1 and all(
        len(member.pivots) <= PRICE_ACTION_MARKET_STRUCTURE_PIVOTS_PER_MEMBER_MAX_V1
        and len(member.events) <= PRICE_ACTION_MARKET_STRUCTURE_EVENTS_PER_MEMBER_MAX_V1
        for member in members
    )


def _bounded_caller_objects(
    request: CurrentSamePassMarketRegimeRequestV4,
    raw: PrivateCurrentSamePassRawDailyResultV1,
    screen: PublishedCurrentCorporateActionScreenV1,
    market_structure: CurrentMarketStructureReportV1,
) -> bool:
    remaining: list[int] = [PRICE_ACTION_GRAPH_NODES_MAX_V1]
    if not all(
        _safe_typed_value(
            value,
            expected_type,
            depth=0,
            remaining=remaining,
        )
        for value, expected_type in (
            (request, CurrentSamePassMarketRegimeRequestV4),
            (raw, PrivateCurrentSamePassRawDailyResultV1),
            (screen, PublishedCurrentCorporateActionScreenV1),
            (market_structure, CurrentMarketStructureReportV1),
        )
    ):
        return False
    if (
        not PRICE_ACTION_COHORT_SIZE_MIN_V1
        <= len(request.members)
        <= PRICE_ACTION_COHORT_SIZE_MAX_V1
        or len(raw.resolved_sessions) != PRICE_ACTION_SESSION_COUNT_V1
        or not _derived_price_action_values_are_bounded(request, raw)
    ):
        return False
    grid = raw.raw_grid
    if grid is not None and (
        len(grid.sessions) != PRICE_ACTION_SESSION_COUNT_V1
        or len(grid.bars)
        > PRICE_ACTION_COHORT_SIZE_MAX_V1 * PRICE_ACTION_SESSION_COUNT_V1
        or len(grid.source_rows)
        > PRICE_ACTION_COHORT_SIZE_MAX_V1 * PRICE_ACTION_SESSION_COUNT_V1
    ):
        return False
    members = market_structure.members
    if members is None:
        return True
    return _market_structure_member_resources_are_bounded(members)


def _is_digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _safe_decimal(value: object, *, nonnegative: bool = False) -> bool:
    return (
        type(value) is Decimal
        and value.is_finite()
        and (value >= 0 if nonnegative else value > 0)
    )


def _safe_pivot(value: object) -> bool:
    if type(value) is not MarketStructurePivotV1:
        return False
    if not (
        type(value.kind) is str
        and value.kind in ("SWING_HIGH", "SWING_LOW")
        and type(value.position) is int
        and type(value.confirmation_position) is int
        and type(value.session) is date
        and type(value.confirmation_session) is date
        and _safe_decimal(value.price)
        and (type(value.relation) is str or value.relation is None)
        and value.relation in ("HH", "LH", "HL", "LL", None)
        and (
            type(value.unclassified_reason) is str or value.unclassified_reason is None
        )
        and value.unclassified_reason in ("INITIAL", "EQUAL_PRICE", None)
        and _is_digest(value.source_bar_identity_sha256)
        and type(value.comparison_bar_identities_sha256) is tuple
        and len(value.comparison_bar_identities_sha256) == 4
        and all(_is_digest(digest) for digest in value.comparison_bar_identities_sha256)
        and _is_digest(value.pivot_identity_sha256)
    ):
        return False
    return value.pivot_identity_sha256 == current_market_structure_identity_sha256_v1(
        value, omit=frozenset({"pivot_identity_sha256"})
    )


def _safe_event(value: object) -> bool:
    if type(value) is not MarketStructureEventV1:
        return False
    if not (
        type(value.event) is str
        and value.event in ("BOS", "CHOCH")
        and type(value.direction) is str
        and value.direction in ("UP", "DOWN")
        and type(value.position) is int
        and type(value.session) is date
        and _safe_decimal(value.close)
        and _safe_decimal(value.broken_level)
        and type(value.prior_trend) is str
        and value.prior_trend in ("UPTREND", "DOWNTREND")
        and all(
            _is_digest(digest)
            for digest in (
                value.broken_pivot_identity_sha256,
                value.previous_close_bar_identity_sha256,
                value.current_close_bar_identity_sha256,
                value.event_identity_sha256,
            )
        )
    ):
        return False
    return value.event_identity_sha256 == current_market_structure_identity_sha256_v1(
        value, omit=frozenset({"event_identity_sha256"})
    )


def _safe_member(value: object) -> bool:
    if type(value) is not CurrentMarketStructureMemberV1:
        return False
    if not (
        all(
            type(item) is str and item
            for item in (value.isin, value.exchange, value.effective_symbol)
        )
        and type(value.input_bar_identities_sha256) is tuple
        and len(value.input_bar_identities_sha256) == PRICE_ACTION_SESSION_COUNT_V1
        and all(_is_digest(digest) for digest in value.input_bar_identities_sha256)
        and type(value.structure_state) is str
        and value.structure_state in ("CONFIRMED", "INSUFFICIENT_STRUCTURE")
        and type(value.trend) is str
        and value.trend
        in ("UPTREND", "DOWNTREND", "RANGE_OR_TRANSITION", "INSUFFICIENT_STRUCTURE")
        and type(value.pivots) is tuple
        and type(value.events) is tuple
        and all(_safe_pivot(pivot) for pivot in value.pivots)
        and all(_safe_event(event) for event in value.events)
        and _is_digest(value.member_identity_sha256)
    ):
        return False
    return value.member_identity_sha256 == current_market_structure_identity_sha256_v1(
        value, omit=frozenset({"member_identity_sha256"})
    )


def _safe_market_structure_report(value: object) -> bool:
    if type(value) is not CurrentMarketStructureReportV1:
        return False
    if not (
        type(value.contract_version) is str
        and value.contract_version == "current-supplied-cohort-market-structure@v1"
        and all(
            _is_digest(digest)
            for digest in (
                value.schema_identity_sha256,
                value.calculation_identity_sha256,
                value.configuration_identity_sha256,
                value.runtime_code_identity_sha256,
                value.request_identity_sha256,
                value.canonical_cohort_identity_sha256,
                value.schedule_identity_sha256,
                value.report_identity_sha256,
            )
        )
        and type(value.decision_cutoff) is datetime
        and value.decision_cutoff.tzinfo is UTC
        and type(value.comparison_session) is date
        and type(value.decision_session) is date
        and value.comparison_session < value.decision_session
        and type(value.evidence_state) is str
        and value.evidence_state in ("OBSERVED", "INSUFFICIENT_EVIDENCE")
        and type(value.temporal_scope) is str
        and value.temporal_scope == "CURRENT_SAME_PASS_ONLY"
        and type(value.historical_availability_claim) is bool
        and value.historical_availability_claim is False
        and type(value.reasons) is tuple
        and all(type(reason) is str for reason in value.reasons)
        and ordered_market_structure_reasons_v1(set(value.reasons)) == value.reasons
    ):
        return False
    success = (
        value.raw_grid_identity_sha256,
        value.corporate_action_screen_identity_sha256,
    )
    if value.evidence_state == "OBSERVED":
        if not (
            type(value.members) is tuple
            and value.members
            and not value.reasons
            and all(_is_digest(digest) for digest in success)
            and all(_safe_member(member) for member in value.members)
        ):
            return False
    elif not (
        value.members is None
        and value.reasons
        and all(digest is None for digest in success)
    ):
        return False
    return value.report_identity_sha256 == current_market_structure_identity_sha256_v1(
        value, omit=frozenset({"report_identity_sha256"})
    )


def _same_bytes(
    supplied: CurrentMarketStructureReportV1,
    expected: CurrentMarketStructureReportV1,
) -> bool:
    return supplied.canonical_json_bytes() == expected.canonical_json_bytes()


def _market_structure_reasons(report: CurrentMarketStructureReportV1) -> set[str]:
    return {
        reason
        for reason in report.reasons
        if reason
        in {
            "RAW_EVIDENCE_INSUFFICIENT",
            "RAW_RESULT_BINDING_MISMATCH",
            "RAW_GRID_BINDING_MISMATCH",
            "SESSION_WINDOW_INVALID",
            "MEMBER_GRID_INCOMPLETE",
            "RAW_BAR_FUTURE_KNOWN",
            "CORPORATE_ACTION_SCREEN_INSUFFICIENT",
            "CORPORATE_ACTION_SCREEN_BINDING_MISMATCH",
        }
    }


def _insufficient(
    raw: PrivateCurrentSamePassRawDailyResultV1,
    expected: CurrentMarketStructureReportV1,
    reasons: set[str],
) -> CurrentPriceActionReportV1:
    if (
        type(raw.resolved_sessions) is not tuple
        or len(raw.resolved_sessions) != PRICE_ACTION_SESSION_COUNT_V1
        or type(raw.resolved_sessions[19].session) is not date
    ):
        raise ValueError("validated raw sessions are malformed")
    return _mint_current_price_action_report_v1(
        evidence_state="INSUFFICIENT_EVIDENCE",
        request_identity_sha256=expected.request_identity_sha256,
        canonical_cohort_identity_sha256=expected.canonical_cohort_identity_sha256,
        schedule_identity_sha256=expected.schedule_identity_sha256,
        decision_cutoff=expected.decision_cutoff,
        comparison_session=expected.comparison_session,
        previous_session=raw.resolved_sessions[19].session,
        decision_session=expected.decision_session,
        raw_grid_identity_sha256=None,
        corporate_action_screen_identity_sha256=None,
        market_structure_report_identity_sha256=None,
        members=None,
        reasons=ordered_price_action_reasons_v1(reasons),
    )


def _bar_by_member(
    raw: PrivateCurrentSamePassRawDailyResultV1,
) -> dict[str, tuple[Any, ...]]:
    grid = raw.raw_grid
    if grid is None:
        raise ValueError("observed raw grid is absent")
    return {
        isin: tuple(bar for bar in grid.bars if bar.isin == isin)
        for isin in {bar.isin for bar in grid.bars}
    }


def _member(
    raw_bars: tuple[Any, ...], market_structure_member: CurrentMarketStructureMemberV1
) -> CurrentPriceActionMemberV1:
    if len(raw_bars) != PRICE_ACTION_SESSION_COUNT_V1:
        raise ValueError("validated raw member has an invalid session count")
    previous, current = raw_bars[19], raw_bars[20]
    for name in ("open", "high", "low", "close"):
        _positive_finite_decimal(getattr(current, name), f"current raw {name}")
    _positive_finite_decimal(previous.close, "previous raw close")
    if (
        not current.low
        <= min(current.open, current.close)
        <= max(current.open, current.close)
        <= current.high
    ):
        raise ValueError("validated raw bar violates OHLC geometry")
    range_size = _exact_difference(current.high, current.low)
    body_size = _absolute_exact_difference(current.close, current.open)
    upper_wick_size = _exact_difference(current.high, max(current.open, current.close))
    lower_wick_size = _exact_difference(min(current.open, current.close), current.low)
    return CurrentPriceActionMemberV1(
        isin=market_structure_member.isin,
        exchange=market_structure_member.exchange,
        effective_symbol=market_structure_member.effective_symbol,
        previous_session=previous.session,
        session=current.session,
        previous_bar_identity_sha256=previous.raw_bar_identity_sha256,
        current_bar_identity_sha256=current.raw_bar_identity_sha256,
        market_structure_member_identity_sha256=market_structure_member.member_identity_sha256,
        candle_direction=_direction(current.close, current.open),
        session_range_state="FLAT" if current.high == current.low else "NON_FLAT",
        range_size=range_size,
        body_size=body_size,
        upper_wick_size=upper_wick_size,
        lower_wick_size=lower_wick_size,
        open_vs_previous_close=_direction(current.open, previous.close),
        open_to_previous_close_distance=_absolute_exact_difference(
            current.open, previous.close
        ),
        close_vs_previous_close=_direction(current.close, previous.close),
        close_to_previous_close_distance=_absolute_exact_difference(
            current.close, previous.close
        ),
    )


def evaluate_current_same_pass_price_action_v4(
    request: CurrentSamePassMarketRegimeRequestV4,
    raw: PrivateCurrentSamePassRawDailyResultV1,
    screen: PublishedCurrentCorporateActionScreenV1,
    market_structure: CurrentMarketStructureReportV1,
) -> CurrentPriceActionReportV1:
    """Return exact S19/S20 Price Action facts without external effects."""
    if (
        type(request) is not CurrentSamePassMarketRegimeRequestV4
        or type(raw) is not PrivateCurrentSamePassRawDailyResultV1
        or type(screen) is not PublishedCurrentCorporateActionScreenV1
        or type(market_structure) is not CurrentMarketStructureReportV1
        or not _bounded_caller_objects(request, raw, screen, market_structure)
    ):
        raise ValueError("invalid Price Action caller objects")

    expected = evaluate_current_same_pass_market_structure_v4(request, raw, screen)
    if not _safe_market_structure_report(market_structure):
        raise ValueError("invalid Price Action Market Structure caller object")
    if not _safe_market_structure_report(expected):
        raise ValueError("invalid exact Market Structure result")

    matches = _same_bytes(market_structure, expected)
    if expected.evidence_state == "INSUFFICIENT_EVIDENCE":
        reasons = _market_structure_reasons(expected)
        reasons.add("MARKET_STRUCTURE_INSUFFICIENT")
        if not matches:
            reasons.add("MARKET_STRUCTURE_BINDING_MISMATCH")
        return _insufficient(raw, expected, reasons)
    if not matches:
        return _insufficient(raw, expected, {"MARKET_STRUCTURE_BINDING_MISMATCH"})

    if expected.members is None or raw.raw_grid is None:
        raise ValueError("validated observed evidence is absent")
    by_isin = _bar_by_member(raw)
    members = tuple(
        _member(by_isin[member.isin], member) for member in expected.members
    )
    if (
        len(members) != len(expected.members)
        or not PRICE_ACTION_COHORT_SIZE_MIN_V1
        <= len(members)
        <= PRICE_ACTION_COHORT_SIZE_MAX_V1
    ):
        raise ValueError("validated Price Action cohort is invalid")
    ordered = tuple(
        sorted(
            members, key=lambda item: (item.isin, item.exchange, item.effective_symbol)
        )
    )
    previous_session = ordered[0].previous_session
    decision_session = ordered[0].session
    if any(
        member.previous_session != previous_session
        or member.session != decision_session
        for member in ordered
    ):
        raise ValueError("validated Price Action sessions differ by member")
    return _mint_current_price_action_report_v1(
        evidence_state="OBSERVED",
        request_identity_sha256=expected.request_identity_sha256,
        canonical_cohort_identity_sha256=expected.canonical_cohort_identity_sha256,
        schedule_identity_sha256=expected.schedule_identity_sha256,
        decision_cutoff=expected.decision_cutoff,
        comparison_session=expected.comparison_session,
        previous_session=previous_session,
        decision_session=decision_session,
        raw_grid_identity_sha256=expected.raw_grid_identity_sha256,
        corporate_action_screen_identity_sha256=(
            expected.corporate_action_screen_identity_sha256
        ),
        market_structure_report_identity_sha256=expected.report_identity_sha256,
        members=ordered,
        reasons=(),
    )
