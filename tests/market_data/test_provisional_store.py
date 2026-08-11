from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

import swing_trading_ai_assistant.market_data.provisional_store as provisional_store
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    publish_provisional_partition,
)
from swing_trading_ai_assistant.market_data.provisional_metadata import (
    metadata_from_publication,
)
from swing_trading_ai_assistant.market_data.provisional_store import (
    ProvisionalPartitionUnavailableV1,
    latest_provisional_partition,
    load_provisional_partition,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease


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


def _candle(minute: int) -> CanonicalCandle:
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
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10,
        oi=None,
        ingested_at=datetime(2026, 8, 11, 8, tzinfo=UTC),
        source_version="upstox-intraday-v3",
        adjustment_state="raw",
    )


def _publish(root, rows: tuple[CanonicalCandle, ...]):
    digest = "a" * 64
    evidence = publish_provisional_partition(root, _plan(), rows[-1].ts, digest, rows)
    return metadata_from_publication(
        plan=_plan(),
        schedule_digest_sha256=digest,
        cutoff=rows[-1].ts,
        session_complete=False,
        actual_from_ts=rows[0].ts,
        actual_to_ts=rows[-1].ts,
        row_count=len(rows),
        checksum_sha256=evidence.checksum_sha256,
        byte_size=evidence.byte_size,
        relative_path=evidence.canonical_path,
        instrument_snapshot_digest_sha256="b" * 64,
        instrument_snapshot_retrieved_at=datetime(2026, 8, 11, 3, 30, tzinfo=UTC),
        published_at=datetime(2026, 8, 11, 8, tzinfo=UTC),
        historical_attempt_count=0,
        intraday_attempt_count=1,
    )


def test_latest_provisional_partition_is_catalog_first_and_exact(tmp_path) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease as lease:
        earlier = _publish(tmp_path, (_candle(45),))
        later = _publish(tmp_path, (_candle(45), _candle(46)))
        with DuckDBCatalog(tmp_path, lease=lease) as catalog:
            catalog.save_provisional_partition(earlier)
            catalog.save_provisional_partition(later)
        resolved = latest_provisional_partition(tmp_path, lease, _plan())
        assert resolved == (later, (_candle(45), _candle(46)))


def test_provisional_store_fails_closed_on_catalog_or_object_drift(tmp_path) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease as lease:
        metadata = _publish(tmp_path, (_candle(45),))
        with DuckDBCatalog(tmp_path, lease=lease) as catalog:
            catalog.save_provisional_partition(metadata)
        target = tmp_path / metadata.relative_path
        target.write_bytes(b"foreign")
        with pytest.raises(ProvisionalPartitionUnavailableV1):
            load_provisional_partition(tmp_path, lease, metadata)
        with pytest.raises(ProvisionalPartitionUnavailableV1):
            latest_provisional_partition(tmp_path, lease, _plan())


def test_load_provisional_partition_rejects_non_metadata_and_wrong_row_identity(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease as lease:
        with pytest.raises(ProvisionalPartitionUnavailableV1):
            load_provisional_partition(tmp_path, lease, object())  # type: ignore[arg-type]

        metadata = _publish(tmp_path, (_candle(45),))
        wrong_row = replace(_candle(45), symbol="OTHER")
        monkeypatch.setattr(
            provisional_store,
            "read_partition_under_lease",
            lambda root, lease, relative_path: (metadata.checksum_sha256, (wrong_row,)),
        )
        with pytest.raises(ProvisionalPartitionUnavailableV1):
            load_provisional_partition(tmp_path, lease, metadata)
