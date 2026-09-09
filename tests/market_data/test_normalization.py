from __future__ import annotations

from datetime import datetime

import pytest

from swing_trading_ai_assistant.market_data.normalization import (
    CandleSchemaError,
    normalize_candles,
)


def test_normalizes_sorts_and_deduplicates_upstox_candles() -> None:
    raw = [
        ["2026-07-31T09:16:00+05:30", 1401, 1403, 1400, 1402, 1200, 10],
        ["2026-07-31T09:15:00+05:30", 1400, 1402, 1399, 1401, 1000, 9],
        ["2026-07-31T09:15:00+05:30", 1400, 1402, 1399, 1401, 1000, 9],
    ]

    candles = normalize_candles(raw)

    assert len(candles) == 2
    assert candles[0].timestamp == datetime.fromisoformat("2026-07-31T09:15:00+05:30")
    assert candles[-1].timestamp == datetime.fromisoformat("2026-07-31T09:16:00+05:30")
    assert candles[0].volume == 1000


@pytest.mark.parametrize(
    "raw",
    [
        [["not-a-timestamp", 1, 2, 0.5, 1.5, 100, 0]],
        [["2026-07-31T09:15:00+05:30", 1, 2, 0.5, 1.5]],
        [["2026-07-31T09:15:00+05:30", 1, 1.4, 0.5, 1.5, 100, 0]],
        [["2026-07-31T09:15:00+05:30", 1, 2, 0.5, 1.5, -1, 0]],
    ],
)
def test_rejects_invalid_candle_schema(raw: list[list[object]]) -> None:
    with pytest.raises(CandleSchemaError):
        normalize_candles(raw)


def test_rejects_provider_integer_that_overflows_float() -> None:
    raw = [["2026-07-31T09:15:00+05:30", 10**999, 2, 0.5, 1.5, 100, 0]]

    with pytest.raises(CandleSchemaError):
        normalize_candles(raw)


@pytest.mark.parametrize("error_type", (ValueError, MemoryError))
def test_preserves_unrelated_numeric_conversion_fault(
    error_type: type[Exception],
) -> None:
    failure = error_type("synthetic numeric conversion fault")

    class NumericFault(int):
        def __float__(self) -> float:
            raise failure

    with pytest.raises(error_type) as raised:
        normalize_candles(
            [["2026-07-31T09:15:00+05:30", NumericFault(1), 2, 0.5, 1.5, 100, 0]]
        )

    assert raised.value is failure
