from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    PartitionValidationError,
    PublicationConflictError,
    PublicationOutcome,
    provisional_partition_relative_path,
    publish_provisional_partition,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle


def _plan() -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|INE002A01018",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2026,
        8,
        date(2026, 8, 1),
        date(2026, 8, 11),
    )


def _candle(
    minute: int,
    *,
    close: float = 100.5,
    source: str = "upstox-historical-v3",
    ingested_at: datetime = datetime(2026, 8, 11, 10, tzinfo=UTC),
) -> CanonicalCandle:
    return CanonicalCandle(
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
        ts=datetime(2026, 8, 11, 3, minute, tzinfo=UTC),
        open=100.0,
        high=max(close, 101.0),
        low=99.0,
        close=close,
        volume=10,
        oi=None,
        ingested_at=ingested_at,
        source_version=source,
        adjustment_state="raw",
    )


def test_publish_provisional_uses_cutoff_path_and_is_idempotent(tmp_path: Path) -> None:
    rows = (_candle(45), _candle(46, source="upstox-intraday-v3"))
    cutoff = rows[-1].ts
    digest = "a" * 64

    first = publish_provisional_partition(tmp_path, _plan(), cutoff, digest, rows)
    repeated = publish_provisional_partition(
        tmp_path, _plan(), cutoff, digest, tuple(reversed(rows))
    )

    assert first.outcome is PublicationOutcome.PUBLISHED
    assert repeated.outcome is PublicationOutcome.ALREADY_PRESENT
    assert repeated.checksum_sha256 == first.checksum_sha256
    assert first.canonical_path == (
        "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/instrument_type=EQ/"
        "security_id=INE002A01018/interval=1m/year=2026/month=08/provisional/"
        f"schedule_sha256={digest}/cutoff=20260811T034600Z/bars.parquet"
    )
    assert (tmp_path / first.canonical_path).is_file()
    assert not (
        tmp_path / "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
        "instrument_type=EQ/security_id=INE002A01018/interval=1m/"
        "year=2026/month=08/bars.parquet"
    ).exists()


def test_later_cutoff_publishes_new_snapshot_without_changing_prior(
    tmp_path: Path,
) -> None:
    digest = "b" * 64
    earlier_rows = (_candle(45),)
    earlier = publish_provisional_partition(
        tmp_path, _plan(), earlier_rows[-1].ts, digest, earlier_rows
    )
    earlier_bytes = (tmp_path / earlier.canonical_path).read_bytes()
    later_rows = (
        *earlier_rows,
        _candle(
            46,
            source="upstox-intraday-v3",
            ingested_at=datetime(2026, 8, 11, 11, tzinfo=UTC),
        ),
    )
    later = publish_provisional_partition(
        tmp_path, _plan(), later_rows[-1].ts, digest, later_rows
    )

    assert later.canonical_path != earlier.canonical_path
    assert (tmp_path / earlier.canonical_path).read_bytes() == earlier_bytes
    assert (tmp_path / later.canonical_path).is_file()


def test_same_cutoff_different_rows_is_no_clobber_conflict(tmp_path: Path) -> None:
    rows = (_candle(45),)
    publish_provisional_partition(tmp_path, _plan(), rows[-1].ts, "c" * 64, rows)

    with pytest.raises(PublicationConflictError):
        publish_provisional_partition(
            tmp_path,
            _plan(),
            rows[-1].ts,
            "c" * 64,
            (_candle(45, close=100.75),),
        )


@pytest.mark.parametrize(
    ("cutoff", "schedule_digest", "rows"),
    [
        (datetime(2026, 8, 11, 3, 44, tzinfo=UTC), "d" * 64, (_candle(45),)),
        (datetime(2026, 8, 11, 3, 45), "d" * 64, (_candle(45),)),
        (datetime(2026, 8, 11, 3, 45, tzinfo=UTC), "invalid", (_candle(45),)),
        (datetime(2026, 8, 11, 3, 45, tzinfo=UTC), "d" * 64, ()),
    ],
)
def test_provisional_publication_rejects_invalid_identity(
    tmp_path: Path,
    cutoff: datetime,
    schedule_digest: str,
    rows: tuple[CanonicalCandle, ...],
) -> None:
    with pytest.raises(PartitionValidationError):
        publish_provisional_partition(tmp_path, _plan(), cutoff, schedule_digest, rows)


def test_relative_path_requires_exact_utc_minute_and_digest() -> None:
    assert provisional_partition_relative_path(
        _plan(), datetime(2026, 8, 11, 3, 45, tzinfo=UTC), "e" * 64
    ).endswith("schedule_sha256=" + "e" * 64 + "/cutoff=20260811T034500Z/bars.parquet")
    with pytest.raises(PartitionValidationError):
        provisional_partition_relative_path(
            _plan(), datetime(2026, 8, 11, 3, 45, 1, tzinfo=UTC), "e" * 64
        )
