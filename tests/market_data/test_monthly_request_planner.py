from __future__ import annotations

from datetime import date, datetime

import pytest

from swing_trading_ai_assistant.market_data import monthly_request_planner
from swing_trading_ai_assistant.market_data.instruments import Instrument
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    MAX_PLANNED_MONTHS,
    PlannedInstrumentMonth,
    plan_upstox_equity_months,
)


class _DateSubclass(date):
    pass


class _StrSubclass(str):
    pass


class _EqualityImpersonator:
    __hash__ = object.__hash__

    def __eq__(self, other: object) -> bool:
        return True


class _EqualityThrower:
    __hash__ = object.__hash__

    def __eq__(self, other: object) -> bool:
        raise AssertionError("input equality must not be evaluated")


def _instrument(**overrides: object) -> Instrument:
    values: dict[str, object] = {
        "instrument_key": "NSE_EQ|ID",
        "security_id": "ID",
        "symbol": "ABC",
        "exchange": "NSE",
        "segment": "NSE_EQ",
        "instrument_type": "EQ",
        "isin": "ID",
    }
    values.update(overrides)
    return Instrument(**values)  # type: ignore[arg-type]


def test_plans_partial_full_and_leap_calendar_months() -> None:
    result = plan_upstox_equity_months(
        _instrument(), date(2024, 1, 31), date(2024, 3, 2), "1m"
    )
    assert [
        (item.from_date, item.to_date, item.year, item.month) for item in result
    ] == [
        (date(2024, 1, 31), date(2024, 1, 31), 2024, 1),
        (date(2024, 2, 1), date(2024, 2, 29), 2024, 2),
        (date(2024, 3, 1), date(2024, 3, 2), 2024, 3),
    ]


def test_same_day_cross_year_and_deterministic_equality() -> None:
    instrument = _instrument(symbol="XYZ", instrument_key="NSE_EQ|XYZ")
    assert plan_upstox_equity_months(
        instrument, date(2022, 12, 31), date(2023, 1, 1), "1m"
    ) == plan_upstox_equity_months(
        instrument, date(2022, 12, 31), date(2023, 1, 1), "1m"
    )
    plans = plan_upstox_equity_months(
        instrument, date(2022, 12, 31), date(2023, 1, 1), "1m"
    )
    assert [(p.from_date, p.to_date) for p in plans] == [
        (date(2022, 12, 31), date(2022, 12, 31)),
        (date(2023, 1, 1), date(2023, 1, 1)),
    ]


def test_plans_one_actual_same_day_with_complete_identity_and_provenance() -> None:
    instrument = _instrument(
        instrument_key="NSE_EQ|XYZ", security_id="INE000X", symbol="XYZ", isin="INE000X"
    )
    assert plan_upstox_equity_months(
        instrument, date(2024, 2, 29), date(2024, 2, 29), "1m"
    ) == (
        PlannedInstrumentMonth(
            provider="upstox",
            instrument_key="NSE_EQ|XYZ",
            security_id="INE000X",
            symbol="XYZ",
            exchange="NSE",
            segment="NSE_EQ",
            instrument_type="EQ",
            interval="1m",
            year=2024,
            month=2,
            from_date=date(2024, 2, 29),
            to_date=date(2024, 2, 29),
        ),
    )


@pytest.mark.parametrize(
    "from_date,to_date",
    [
        (date(2021, 12, 31), date(2022, 1, 1)),
        (date(2022, 1, 1), date(2021, 12, 31)),
        (date(2021, 1, 1), date(2021, 1, 2)),
    ],
)
def test_rejects_pre2022_and_reversed_ranges(from_date: date, to_date: date) -> None:
    with pytest.raises(ValueError):
        plan_upstox_equity_months(_instrument(), from_date, to_date, "1m")


@pytest.mark.parametrize("value", [datetime(2022, 1, 1), True, "2022-01-01"])
def test_rejects_non_exact_date_inputs(value: object) -> None:
    with pytest.raises(ValueError, match="dates"):
        plan_upstox_equity_months(_instrument(), value, date(2022, 1, 1), "1m")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "from_date,to_date",
    [
        (_DateSubclass(2022, 1, 1), date(2022, 1, 1)),
        (date(2022, 1, 1), _DateSubclass(2022, 1, 1)),
        (date(2023, 4, 2), date(2023, 4, 1)),
    ],
)
def test_rejects_exact_date_contract_violations_after_minimum_date(
    from_date: object, to_date: object
) -> None:
    with pytest.raises(ValueError):
        plan_upstox_equity_months(_instrument(), from_date, to_date, "1m")  # type: ignore[arg-type]


@pytest.mark.parametrize("interval", ["3m", "5m", "15m", "1h", 1, True])
def test_rejects_unsupported_interval(interval: object) -> None:
    with pytest.raises(ValueError, match="interval"):
        plan_upstox_equity_months(
            _instrument(), date(2022, 1, 1), date(2022, 1, 1), interval
        )  # type: ignore[arg-type]


@pytest.mark.parametrize("interval", [_StrSubclass("1m"), _StrSubclass("3m")])
def test_rejects_string_subclass_intervals(interval: object) -> None:
    with pytest.raises(ValueError, match="interval"):
        plan_upstox_equity_months(
            _instrument(), date(2022, 1, 1), date(2022, 1, 1), interval
        )  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "override",
    [
        {"exchange": "BSE"},
        {"segment": "NSE_FO"},
        {"instrument_type": "FUT"},
        {"underlying_key": "x"},
        {"expiry": "x"},
        {"strike_price": 1.0},
        {"option_type": "CE"},
    ],
)
def test_rejects_contaminated_identity(override: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="NSE/NSE_EQ/EQ"):
        plan_upstox_equity_months(
            _instrument(**override), date(2022, 1, 1), date(2022, 1, 1), "1m"
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("instrument_key", ""),
        ("instrument_key", " NSE_EQ|ID"),
        ("instrument_key", "NSE_EQ|ID "),
        ("security_id", ""),
        ("security_id", " ID"),
        ("security_id", "ID "),
        ("symbol", ""),
        ("symbol", " ABC"),
        ("symbol", "ABC "),
        ("isin", ""),
        ("isin", " ID"),
        ("isin", "ID "),
        ("isin", "OTHER"),
        ("isin", 1),
        ("isin", None),
        ("instrument_key", 1),
        ("security_id", 1),
        ("symbol", 1),
        ("exchange", 1),
        ("segment", 1),
        ("instrument_type", 1),
    ],
)
def test_rejects_noncanonical_or_unresolved_instrument_identity(
    field: str, value: object
) -> None:
    with pytest.raises(ValueError, match="NSE/NSE_EQ/EQ"):
        plan_upstox_equity_months(
            _instrument(**{field: value}), date(2022, 1, 1), date(2022, 1, 1), "1m"
        )


@pytest.mark.parametrize("value", [_EqualityImpersonator(), _EqualityThrower()])
def test_rejects_identity_values_without_evaluating_custom_equality(
    value: object,
) -> None:
    instrument = _instrument()
    object.__setattr__(instrument, "isin", value)
    with pytest.raises(ValueError, match="NSE/NSE_EQ/EQ"):
        plan_upstox_equity_months(instrument, date(2022, 1, 1), date(2022, 1, 1), "1m")


def test_rejects_instrument_subclass_even_with_the_same_field_values() -> None:
    class _InstrumentSubclass(Instrument):
        pass

    instrument = _InstrumentSubclass(**_instrument().__dict__)
    with pytest.raises(ValueError, match="NSE/NSE_EQ/EQ"):
        plan_upstox_equity_months(instrument, date(2022, 1, 1), date(2022, 1, 1), "1m")


def test_months_have_exact_union_adjacency_and_unique_identity() -> None:
    plans = plan_upstox_equity_months(
        _instrument(), date(2023, 11, 30), date(2024, 2, 2), "1m"
    )
    assert plans[0].from_date == date(2023, 11, 30)
    assert plans[-1].to_date == date(2024, 2, 2)
    assert len({(plan.year, plan.month) for plan in plans}) == len(plans)
    for left, right in zip(plans[:-1], plans[1:], strict=True):
        assert left.to_date.toordinal() + 1 == right.from_date.toordinal()


def test_supports_natural_date_bound_and_exact_month_count() -> None:
    assert MAX_PLANNED_MONTHS == 95_736
    plans = plan_upstox_equity_months(
        _instrument(), date(9999, 12, 1), date(9999, 12, 31), "1m"
    )
    assert len(plans) == 1


def test_plans_complete_natural_date_range() -> None:
    plans = plan_upstox_equity_months(
        _instrument(), date(2022, 1, 1), date(9999, 12, 31), "1m"
    )
    assert len(plans) == MAX_PLANNED_MONTHS == 95_736
    assert plans[-1].to_date == date(9999, 12, 31)
    assert (plans[-1].year, plans[-1].month) == (9999, 12)
    assert plans[0].from_date == date(2022, 1, 1)


def test_rejects_count_above_natural_bound_before_plan_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def construction_must_not_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("plan construction must not occur")

    monkeypatch.setattr(
        monthly_request_planner,
        "_month_count",
        lambda _from, _to: MAX_PLANNED_MONTHS + 1,
    )
    monkeypatch.setattr(
        monthly_request_planner, "PlannedInstrumentMonth", construction_must_not_run
    )
    with pytest.raises(ValueError, match="natural bound"):
        plan_upstox_equity_months(
            _instrument(), date(2022, 1, 1), date(2022, 1, 1), "1m"
        )


def test_output_tuple_and_models_are_immutable() -> None:
    plans = plan_upstox_equity_months(
        _instrument(), date(2022, 1, 1), date(2022, 2, 1), "1m"
    )
    with pytest.raises(TypeError):
        plans[0] = plans[1]  # type: ignore[index]
    with pytest.raises((AttributeError, TypeError)):
        plans[0].month = 2  # type: ignore[misc]


def test_public_model_cannot_be_subclassed_to_bypass_validation() -> None:
    with pytest.raises(TypeError, match="cannot be subclassed"):

        class _InvalidBypass(PlannedInstrumentMonth):
            def __post_init__(self) -> None:
                pass


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "other"),
        ("provider", " upstox"),
        ("provider", 1),
        ("provider", _StrSubclass("upstox")),
        ("instrument_key", ""),
        ("instrument_key", " k"),
        ("instrument_key", 1),
        ("instrument_key", _StrSubclass("k")),
        ("security_id", ""),
        ("security_id", " i "),
        ("security_id", 1),
        ("security_id", _StrSubclass("i")),
        ("symbol", ""),
        ("symbol", " s "),
        ("symbol", 1),
        ("symbol", _StrSubclass("s")),
        ("exchange", "BSE"),
        ("exchange", 1),
        ("exchange", _StrSubclass("NSE")),
        ("segment", "NSE_FO"),
        ("segment", 1),
        ("segment", _StrSubclass("NSE_EQ")),
        ("instrument_type", "FUT"),
        ("instrument_type", 1),
        ("instrument_type", _StrSubclass("EQ")),
        ("interval", "3m"),
        ("interval", _StrSubclass("1m")),
        ("interval", 1),
        ("year", True),
        ("year", 2021),
        ("year", 10_000),
        ("month", True),
        ("month", 0),
        ("month", 13),
        ("from_date", datetime(2022, 1, 1)),
        ("from_date", _DateSubclass(2022, 1, 1)),
        ("to_date", datetime(2022, 1, 1)),
        ("to_date", _DateSubclass(2022, 1, 1)),
        ("to_date", date(2022, 2, 1)),
    ],
)
def test_public_model_rejects_invalid_construction(field: str, value: object) -> None:
    values: dict[str, object] = {
        "provider": "upstox",
        "instrument_key": "k",
        "security_id": "i",
        "symbol": "s",
        "exchange": "NSE",
        "segment": "NSE_EQ",
        "instrument_type": "EQ",
        "interval": "1m",
        "year": 2022,
        "month": 1,
        "from_date": date(2022, 1, 1),
        "to_date": date(2022, 1, 2),
    }
    values[field] = value
    with pytest.raises(ValueError, match="invalid planned"):
        PlannedInstrumentMonth(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "from_date,to_date",
    [
        (date(2022, 1, 2), date(2022, 1, 1)),
        (date(2022, 2, 1), date(2022, 2, 1)),
        (date(2022, 1, 1), date(2022, 2, 1)),
    ],
)
def test_public_model_rejects_invalid_range_or_month_match(
    from_date: date, to_date: date
) -> None:
    with pytest.raises(ValueError, match="invalid planned"):
        PlannedInstrumentMonth(
            "upstox",
            "k",
            "i",
            "s",
            "NSE",
            "NSE_EQ",
            "EQ",
            "1m",
            2022,
            1,
            from_date,
            to_date,
        )


@pytest.mark.parametrize(
    "field", ["provider", "exchange", "segment", "instrument_type"]
)
@pytest.mark.parametrize("value", [_EqualityImpersonator(), _EqualityThrower()])
def test_public_model_rejects_non_string_identity_without_custom_equality(
    field: str, value: object
) -> None:
    values: dict[str, object] = {
        "provider": "upstox",
        "instrument_key": "k",
        "security_id": "i",
        "symbol": "s",
        "exchange": "NSE",
        "segment": "NSE_EQ",
        "instrument_type": "EQ",
        "interval": "1m",
        "year": 2022,
        "month": 1,
        "from_date": date(2022, 1, 1),
        "to_date": date(2022, 1, 2),
    }
    values[field] = value
    with pytest.raises(ValueError, match="invalid planned"):
        PlannedInstrumentMonth(**values)  # type: ignore[arg-type]
