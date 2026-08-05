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
