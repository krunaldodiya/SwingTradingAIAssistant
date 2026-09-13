"""Retained member-local Event V2 tests for Issue #187."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data import current_event_notice_v2 as event_v2
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.current_event_notice import (
    EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
    CurrentEventNoticeInputV1,
)
from swing_trading_ai_assistant.market_data.current_research_binding_v2 import (
    resolve_current_research_binding_v2,
)
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    SNAPSHOT_SOURCE_V1,
    FetchedInstrumentSnapshotV1,
    InstrumentSnapshotStoreV1,
)
from swing_trading_ai_assistant.market_data.instruments import InstrumentCatalog
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

_KNOWN = datetime(2026, 8, 26, 9, tzinfo=UTC)
_CUTOFF = datetime(2026, 8, 26, 9, 5, tzinfo=UTC)
_HEADER = (
    "SYMBOL,COMPANY NAME,SUBJECT,DETAILS,BROADCAST DATE/TIME,RECEIPT,"
    "DISSEMINATION,DIFFERENCE,ATTACHMENT"
)
_INSTRUMENTS = [
    {
        "segment": "NSE_EQ",
        "name": "Alpha Limited",
        "exchange": "NSE",
        "isin": "INE002A01018",
        "instrument_type": "EQ",
        "instrument_key": "NSE_EQ|INE002A01018",
        "trading_symbol": "ALPHA",
    },
    {
        "segment": "NSE_EQ",
        "name": "Punjab National Bank",
        "exchange": "NSE",
        "isin": "INE160A01022",
        "instrument_type": "EQ",
        "instrument_key": "NSE_EQ|INE160A01022",
        "trading_symbol": "PNB",
    },
]


def _artifact() -> bytes:
    rows = [
        (
            "ALPHA,Alpha Limited,Board update,Duplicate disclosure,"
            "26-Aug-2026 14:00:00,2026-08-26 13:59:00,"
            "26-Aug-2026 14:00:01,00:00:01,-"
        ),
        (
            "ALPHA,Alpha Limited,Board update,Duplicate disclosure,"
            "26-Aug-2026 14:00:00,2026-08-26 13:59:00,"
            "26-Aug-2026 14:00:01,00:00:01,-"
        ),
        (
            "PNB,Punjab National Bank,Board meeting,Quarterly update,"
            "26-Aug-2026 14:00:00,2026-08-26 13:59:00,"
            "26-Aug-2026 14:00:01,00:00:01,-"
        ),
    ]
    return ("\ufeff" + "\n".join((_HEADER, *rows)) + "\n").encode()


def _input(raw: bytes) -> CurrentEventNoticeInputV1:
    return CurrentEventNoticeInputV1(
        schema_identity_sha256=EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
        source_url=(
            "https://www.nseindia.com/companies-listing/"
            "corporate-filings-announcements?tabIndex=equity"
        ),
        source_segment="Equity",
        source_window="1D",
        source_filename="CF-AN-equities-25-08-2026-to-26-08-2026.csv",
        artifact_identity_sha256=hashlib.sha256(raw).hexdigest(),
        acquisition_method="BOUNDED_OFFICIAL_FETCH",
        licence_policy_identity="nse-bounded-official-fetch-owner-private-v1",
        source_has_bom=True,
    )


def _mapping(root: Path, lease: StorageRootLease):
    decompressed = json.dumps(_INSTRUMENTS, separators=(",", ":")).encode()
    compressed = gzip.compress(decompressed, mtime=0)
    fetched = FetchedInstrumentSnapshotV1(
        datetime(2026, 8, 26, 8, tzinfo=UTC),
        date(2026, 8, 26),
        compressed,
        decompressed,
        hashlib.sha256(compressed).hexdigest(),
        hashlib.sha256(decompressed).hexdigest(),
        InstrumentCatalog.from_json_bytes(decompressed),
        None,
        None,
    )
    with DuckDBCatalog(root, lease=lease) as catalog:
        InstrumentSnapshotStoreV1(root, lease, catalog).retain(fetched)
    with DuckDBCatalog(root, lease=lease) as catalog:
        store = InstrumentSnapshotStoreV1(root, lease, catalog)
        resolved = tuple(
            store.resolve_equity(
                source=SNAPSHOT_SOURCE_V1,
                segment="NSE_EQ",
                symbol=item["trading_symbol"],
                as_of=fetched.retrieved_at,
            )
            for item in _INSTRUMENTS
        )
    return resolve_current_research_binding_v2(
        root,
        lease,
        resolved,
        selected_at=_KNOWN,
        decision_cutoff=_CUTOFF,
        schedule_identity_sha256="a" * 64,
    )


def test_retained_v2_local_duplicate_preserves_unaffected_member_and_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "event-v2"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    raw = _artifact()
    monkeypatch.setattr(event_v2, "_trusted_utc_now", lambda: _KNOWN)
    with acquired.lease as lease:
        mapping = _mapping(root, lease)
        first = event_v2.retain_current_event_notices_v2(
            root, lease, _input(raw), raw, mapping
        )
        second = event_v2.retain_current_event_notices_v2(
            root, lease, _input(raw), raw, mapping
        )

    assert first == second
    assert first.known_at == _KNOWN
    assert first.members[0].support == "CONFLICTED"
    assert first.members[0].notices == ()
    assert first.members[1].availability == "NOTICES_ADMITTED"
    assert len(first.members[1].notices) == 1
    serialized = first.canonical_json_bytes()
    assert b'"subject"' not in serialized
    assert b'"details"' not in serialized
    assert b'"attachment_url"' not in serialized
    assert b'"source_company_name"' not in serialized
    assert event_v2.validate_retained_current_event_notice_v2(first) is first


def test_event_v2_post_admission_mutation_and_future_source_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "event-v2-negative"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    raw = _artifact()
    monkeypatch.setattr(event_v2, "_trusted_utc_now", lambda: _KNOWN)
    with acquired.lease as lease:
        mapping = _mapping(root, lease)
        retained = event_v2.retain_current_event_notices_v2(
            root, lease, _input(raw), raw, mapping
        )
    object.__setattr__(retained, "known_at", _CUTOFF)
    with pytest.raises(ValueError, match="not admitted"):
        event_v2.validate_retained_current_event_notice_v2(retained)

    later = tmp_path / "event-v2-future"
    later.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(later)
    assert acquired.lease is not None
    monkeypatch.setattr(
        event_v2, "_trusted_utc_now", lambda: datetime(2026, 8, 27, 9, tzinfo=UTC)
    )
    with acquired.lease as lease:
        mapping = _mapping(later, lease)
        with pytest.raises(ValueError, match="source-time"):
            event_v2.retain_current_event_notices_v2(
                later, lease, _input(raw), raw, mapping
            )
