from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq

from equity_data_downloader import download_daily_ohlcv
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockDailyPrice,
    BharatStockHistory,
    BharatStockInstrument,
)


def test_canonical_source_download_reuses_exact_parquet_without_acquisition(
    tmp_path: Path,
) -> None:
    member = BharatStockInstrument("INE002A01018", "NSE", "RELIANCE")
    calls = []

    class Client:
        def history(self, instrument, start, end):
            calls.append((instrument, start, end))
            return BharatStockHistory(
                member,
                (
                    BharatStockDailyPrice(
                        date(2026, 8, 27),
                        Decimal(100),
                        Decimal(104),
                        Decimal(98),
                        Decimal(102),
                        1000,
                        Decimal(51),
                        Decimal("0.5"),
                    ),
                ),
                datetime(2026, 8, 28, tzinfo=UTC),
                ("a" * 64, "b" * 64),
                2,
            )

    receipt = download_daily_ohlcv(
        (member,),
        date(2026, 8, 27),
        date(2026, 8, 28),
        tmp_path,
        client=Client(),
    )
    again = download_daily_ohlcv(
        (member,),
        date(2026, 8, 27),
        date(2026, 8, 28),
        tmp_path,
        client=Client(),
    )
    assert receipt.provider == "BHARATSTOCK"
    assert receipt.price_basis == "BHARATSTOCK_SOURCE_REPORTED_OHLC"
    assert again.outcome == "REUSED"
    assert len(calls) == 1
    assert receipt.destination == again.destination
    table = pq.ParquetFile(receipt.destination).read()
    assert table.to_pylist() == [
        {
            "isin": member.isin,
            "exchange": "NSE",
            "symbol": "RELIANCE",
            "session": date(2026, 8, 27),
            "open": 100.0,
            "high": 104.0,
            "low": 98.0,
            "close": 102.0,
            "volume": 1000,
            "source_open": 100.0,
            "source_high": 104.0,
            "source_low": 98.0,
            "source_close": 102.0,
            "source_adjusted_close": 51.0,
            "source_adjustment_factor": 0.5,
        }
    ]
    assert not (tmp_path / ".cache").exists()
    assert table.schema.metadata[b"price_basis"] == (
        b"BHARATSTOCK_SOURCE_REPORTED_OHLC"
    )
