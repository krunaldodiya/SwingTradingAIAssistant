from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone

import pytest

from swing_trading_ai_assistant.market_data.instruments import Instrument
from swing_trading_ai_assistant.market_data.normalization import Candle
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle
from swing_trading_ai_assistant.market_data.upstox_canonical import (
    MAX_UPSTOX_EQUITY_CANDLES,
    canonicalize_upstox_equity_candles,
)


def _instrument(**overrides: object) -> Instrument:
    values: dict[str, object] = {
        "instrument_key": "NSE_EQ|INE002A01018",
        "security_id": "INE002A01018",
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "segment": "NSE_EQ",
        "instrument_type": "EQ",
        "isin": "INE002A01018",
    }
    values.update(overrides)
    return Instrument(**values)  # type: ignore[arg-type]


def _candle(**overrides: object) -> Candle:
    values: dict[str, object] = {
        "timestamp": datetime(
            2026, 8, 3, 9, 15, tzinfo=timezone(timedelta(hours=5, minutes=30))
        ),
        "open": 1400.0,
        "high": 1403.0,
        "low": 1399.0,
        "close": 1402.0,
        "volume": 9_223_372_036_854_775_808,
        "oi": None,
    }
    values.update(overrides)
    return Candle(**values)  # type: ignore[arg-type]


def test_canonicalizes_normalized_equity_candle_with_upstox_provenance() -> None:
    ingested_at = datetime(2026, 8, 5, 4, 30, 45, 12, tzinfo=UTC)

    result = canonicalize_upstox_equity_candles([_candle()], _instrument(), ingested_at)

    assert result == (
        CanonicalCandle(
            provider="upstox",
            instrument_key="NSE_EQ|INE002A01018",
            security_id="INE002A01018",
            symbol="RELIANCE",
            exchange="NSE",
            segment="NSE_EQ",
            instrument_type="EQ",
            underlying_id=None,
            expiry=None,
            strike=None,
            option_type=None,
            interval="1m",
            ts=datetime(2026, 8, 3, 3, 45, tzinfo=UTC),
            open=1400.0,
            high=1403.0,
            low=1399.0,
            close=1402.0,
            volume=9_223_372_036_854_775_808,
            oi=None,
            ingested_at=ingested_at,
            source_version="upstox-historical-v3",
            adjustment_state="raw",
        ),
    )


@pytest.mark.parametrize("oi", [None, 0, 0.0])
def test_accepts_absent_or_zero_source_open_interest(oi: float | None) -> None:
    assert (
        len(
            canonicalize_upstox_equity_candles(
                [_candle(oi=oi)], _instrument(), datetime(2026, 8, 5, tzinfo=UTC)
            )
        )
        == 1
    )


def test_rejects_positive_source_open_interest() -> None:
    with pytest.raises(ValueError, match="open interest"):
        canonicalize_upstox_equity_candles(
            [_candle(oi=1.0)], _instrument(), datetime(2026, 8, 5, tzinfo=UTC)
        )


@pytest.mark.parametrize(
    "oi", [-1, float("nan"), float("inf"), float("-inf"), True, "0"]
)
def test_rejects_nonzero_or_invalid_source_open_interest(oi: object) -> None:
    with pytest.raises(ValueError, match="open interest"):
        canonicalize_upstox_equity_candles(
            [_candle(oi=oi)], _instrument(), datetime(2026, 8, 5, tzinfo=UTC)
        )


@pytest.mark.parametrize(
    "instrument",
    [
        _instrument(exchange="BSE"),
        _instrument(underlying_key="NSE_INDEX|NIFTY 50"),
        _instrument(expiry="2026-08-27"),
        _instrument(strike_price=25000.0),
        _instrument(option_type="CE"),
    ],
)
def test_rejects_contradictory_equity_identity(instrument: Instrument) -> None:
    with pytest.raises(ValueError, match="NSE/NSE_EQ/EQ"):
        canonicalize_upstox_equity_candles(
            [], instrument, datetime(2026, 8, 5, tzinfo=UTC)
        )


@pytest.mark.parametrize("ingested_at", [datetime(2026, 8, 5), "secret"])
def test_validates_ingestion_timestamp_for_empty_input(ingested_at: object) -> None:
    with pytest.raises(ValueError, match="ingested_at"):
        canonicalize_upstox_equity_candles([], _instrument(), ingested_at)  # type: ignore[arg-type]


def test_rejects_non_sequence_and_stops_before_later_elements_on_duplicate() -> None:
    def generator() -> object:
        yield _candle()

    with pytest.raises(ValueError, match="sequence"):
        canonicalize_upstox_equity_candles(
            generator(), _instrument(), datetime(2026, 8, 5, tzinfo=UTC)
        )  # type: ignore[arg-type]


def test_sorts_utc_output_and_allows_empty_input() -> None:
    later = _candle(timestamp=datetime(2026, 8, 3, 9, 16, tzinfo=UTC))
    earlier = _candle(timestamp=datetime(2026, 8, 3, 9, 15, tzinfo=UTC))

    result = canonicalize_upstox_equity_candles(
        [later, earlier], _instrument(), datetime(2026, 8, 5, tzinfo=UTC)
    )

    assert [candle.ts for candle in result] == [earlier.timestamp, later.timestamp]
    assert (
        canonicalize_upstox_equity_candles(
            [], _instrument(), datetime(2026, 8, 5, tzinfo=UTC)
        )
        == ()
    )


@pytest.mark.parametrize(
    "candles",
    [
        [_candle(), _candle()],
        [_candle(), _candle(close=1401.0)],
    ],
)
def test_rejects_identical_and_conflicting_duplicate_canonical_keys(
    candles: list[Candle],
) -> None:
    with pytest.raises(ValueError, match="duplicate canonical candle key"):
        canonicalize_upstox_equity_candles(
            candles, _instrument(), datetime(2026, 8, 5, tzinfo=UTC)
        )


def test_incremental_duplicate_uses_ark31_error_and_short_circuits() -> None:
    class ExplodingSequence(list[Candle]):
        def __getitem__(self, index: int) -> Candle:
            if index == 2:
                raise AssertionError("later item touched")
            return super().__getitem__(index)

    candles = ExplodingSequence([_candle(), _candle(close=1401.0), _candle()])
    with pytest.raises(Exception) as exc_info:
        canonicalize_upstox_equity_candles(
            candles, _instrument(), datetime(2026, 8, 5, tzinfo=UTC)
        )
    assert type(exc_info.value).__name__ == "DuplicateCandleKeyError"
    assert exc_info.value.key == (
        "upstox",
        "NSE_EQ|INE002A01018",
        "1m",
        datetime(2026, 8, 3, 3, 45, tzinfo=UTC),
    )


@pytest.mark.parametrize("candles", [["bad"], [object()]])
def test_rejects_non_candle_elements_before_attribute_access(
    candles: list[object],
) -> None:
    with pytest.raises(ValueError, match="exact normalized Candle"):
        canonicalize_upstox_equity_candles(
            candles, _instrument(), datetime(2026, 8, 5, tzinfo=UTC)
        )  # type: ignore[arg-type]


def test_bounds_sequence_before_item_access() -> None:
    class Oversized(Sequence[Candle]):
        def __len__(self) -> int:
            return MAX_UPSTOX_EQUITY_CANDLES + 1

        def __getitem__(self, index: int) -> Candle:
            raise AssertionError("item touched")

    with pytest.raises(ValueError, match="maximum"):
        canonicalize_upstox_equity_candles(
            Oversized(), _instrument(), datetime(2026, 8, 5, tzinfo=UTC)
        )


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 8, 3, 9, 15),
        datetime(2026, 8, 3, 9, 15, 1, tzinfo=UTC),
    ],
)
def test_rejects_naive_and_off_minute_normalized_timestamps(
    timestamp: datetime,
) -> None:
    with pytest.raises(ValueError, match="ts"):
        canonicalize_upstox_equity_candles(
            [_candle(timestamp=timestamp)],
            _instrument(),
            datetime(2026, 8, 5, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "instrument",
    [
        _instrument(segment="NSE_FO", instrument_type="FUT"),
        _instrument(segment="NSE_EQ", instrument_type="CE"),
    ],
)
def test_rejects_contaminated_non_equity_instruments(instrument: Instrument) -> None:
    with pytest.raises(ValueError, match="NSE_EQ/EQ"):
        canonicalize_upstox_equity_candles(
            [_candle()], instrument, datetime(2026, 8, 5, tzinfo=UTC)
        )


def test_errors_do_not_echo_sensitive_identity_text() -> None:
    sensitive = "UPSTOX_ACCESS_TOKEN=secret-payload"
    contaminated = _instrument(segment=sensitive, instrument_type="FUT")

    with pytest.raises(ValueError) as exc_info:
        canonicalize_upstox_equity_candles(
            [_candle()], contaminated, datetime(2026, 8, 5, tzinfo=UTC)
        )

    assert sensitive not in str(exc_info.value)
    assert sensitive not in repr(exc_info.value)
