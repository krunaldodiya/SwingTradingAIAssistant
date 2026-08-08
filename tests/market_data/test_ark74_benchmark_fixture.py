from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from ark74_benchmark_fixture import benchmark_nse_eq_v1

from swing_trading_ai_assistant.market_data.credentials import AccessToken
from swing_trading_ai_assistant.market_data.historical import UpstoxV3HistoricalClient
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V2,
    canonical_schedule_bytes,
    schedule_digest,
)


def test_b01_fixture_has_frozen_february_rows_and_test_only_provenance() -> None:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))

    assert fixture.fixture_id == "benchmark-nse-eq-v1"
    assert fixture.instrument == fixture.partitions[0].instrument
    assert fixture.instrument.isin == "INE000A01000"
    assert fixture.instrument.underlying_key is None
    assert fixture.instrument.expiry is None
    assert fixture.instrument.strike_price is None
    assert fixture.instrument.option_type is None
    assert fixture.validation_policy == "nse-equity-month@v1"
    assert fixture.schedule.schema_version == SCHEDULE_SCHEMA_VERSION_V2
    assert fixture.schedule_bytes == canonical_schedule_bytes(fixture.schedule)
    assert fixture.schedule_digest == schedule_digest(fixture.schedule)
    assert fixture.schedule_digest == (
        "32b239c6e8924bdf4fb676f0f2b8b070c14869e9d3202badc001b20e863b17fd"
    )

    partition = fixture.partitions[0]
    assert partition.plan.year == 2024
    assert partition.plan.month == 2
    assert (
        partition.raw_count == partition.normalized_count == partition.published_count
    )
    assert partition.published_count == 7_500
    assert partition.response.status_code == 200
    assert len(partition.response.headers) == 0
    assert partition.response.error_category is None
    assert len(partition.response.candles) == 7_500

    first, last = partition.canonical_candles[0], partition.canonical_candles[-1]
    assert first.ts == datetime(2024, 2, 1, 3, 45, tzinfo=UTC)
    assert (first.open, first.high, first.low, first.close, first.volume) == (
        float(Decimal(230_000).scaleb(-2)),
        float(Decimal(230_004).scaleb(-2)),
        float(Decimal(229_997).scaleb(-2)),
        float(Decimal(230_001).scaleb(-2)),
        1_097_500,
    )
    assert last.ts == datetime(2024, 2, 20, 9, 59, tzinfo=UTC)
    assert (last.open, last.high, last.low, last.close, last.volume) == (
        float(Decimal(237_499).scaleb(-2)),
        float(Decimal(237_503).scaleb(-2)),
        float(Decimal(237_496).scaleb(-2)),
        float(Decimal(237_500).scaleb(-2)),
        1_104_999,
    )
    assert (
        first.underlying_id is first.expiry is first.strike is first.option_type is None
    )
    assert first.oi is None
    assert first.ingested_at == datetime(2024, 3, 1, tzinfo=UTC)
    assert first.source_version == "upstox-historical-v3"
    assert first.adjustment_state == "raw"


def test_fixture_orders_month_session_and_minute_rows_without_calendar_inference() -> (
    None
):
    fixture = benchmark_nse_eq_v1(date(2024, 1, 1), date(2024, 3, 1))

    assert len(fixture.partitions) == 3
    assert fixture.schedule_digest == (
        "031e66087b1e7ef8d9097e585da5428d777875243c6c06f1b48670e0d2f327b3"
    )
    assert fixture.schedule_bytes == canonical_schedule_bytes(fixture.schedule)
    assert len(fixture.schedule.sessions) == 60
    assert len(fixture.schedule.closures) == 31
    assert tuple((part.plan.year, part.plan.month) for part in fixture.partitions) == (
        (2024, 1),
        (2024, 2),
        (2024, 3),
    )
    assert all(part.published_count == 7_500 for part in fixture.partitions)

    rows = fixture.partitions[1].canonical_candles
    assert rows[374].ts == datetime(2024, 2, 1, 9, 59, tzinfo=UTC)
    assert rows[375].ts == datetime(2024, 2, 2, 3, 45, tzinfo=UTC)
    assert rows[375].ts - rows[374].ts == timedelta(hours=17, minutes=46)
    assert rows == tuple(sorted(rows, key=lambda candle: candle.ts))


def test_b05_fixture_has_the_frozen_twelve_month_shape_and_schedule_digest() -> None:
    fixture = benchmark_nse_eq_v1(date(2023, 1, 1), date(2023, 12, 1))

    assert fixture.schedule_digest == (
        "edf3d0818bf0862dbb171708d6010ef380c77bf44e622ec9166a53e865d8c1db"
    )
    assert fixture.schedule_bytes == canonical_schedule_bytes(fixture.schedule)
    assert len(fixture.partitions) == 12
    assert len(fixture.schedule.sessions) == 240
    assert len(fixture.schedule.closures) == 125
    assert sum(part.published_count for part in fixture.partitions) == 90_000
    assert fixture.partitions[0].canonical_candles[0].ts == datetime(
        2023, 1, 1, 3, 45, tzinfo=UTC
    )
    assert fixture.partitions[-1].canonical_candles[-1].ts == datetime(
        2023, 12, 20, 9, 59, tzinfo=UTC
    )


def test_fixture_is_deterministic_and_independent_of_provider_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("test fixture must not use provider or credentials")

    monkeypatch.setattr(UpstoxV3HistoricalClient, "fetch", fail_if_called)
    monkeypatch.setattr(AccessToken, "reveal", fail_if_called)

    first = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    second = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))

    assert first == second


@pytest.mark.parametrize(
    ("from_month", "to_month"),
    [
        (date(2022, 12, 1), date(2023, 1, 1)),
        (date(2024, 3, 1), date(2024, 4, 1)),
        (date(2023, 1, 2), date(2023, 1, 2)),
        (date(2024, 3, 1), date(2024, 2, 1)),
    ],
)
def test_fixture_rejects_ranges_outside_its_frozen_month_domain(
    from_month: date, to_month: date
) -> None:
    with pytest.raises(ValueError, match="benchmark fixture month range"):
        benchmark_nse_eq_v1(from_month, to_month)
