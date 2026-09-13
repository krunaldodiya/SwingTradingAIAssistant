"""Producer-owned mapping successor tests for Issue #187."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.current_research_binding_v2 import (
    AdmittedCurrentResearchBindingV2,
    resolve_current_research_binding_v2,
    validate_current_research_binding_v2,
)
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    SNAPSHOT_SOURCE_V1,
    FetchedInstrumentSnapshotV1,
    InstrumentSnapshotStoreV1,
)
from swing_trading_ai_assistant.market_data.instruments import InstrumentCatalog
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

_SELECTED = datetime(2026, 8, 26, 9, tzinfo=UTC)
_CUTOFF = datetime(2026, 8, 26, 9, 5, tzinfo=UTC)
_INSTRUMENT = {
    "segment": "NSE_EQ",
    "name": "Alpha Limited",
    "exchange": "NSE",
    "isin": "INE002A01018",
    "instrument_type": "EQ",
    "instrument_key": "NSE_EQ|INE002A01018",
    "trading_symbol": "ALPHA",
}


def _binding(root: Path):
    decompressed = json.dumps([_INSTRUMENT], separators=(",", ":")).encode()
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
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    lease = acquired.lease
    with lease:
        with DuckDBCatalog(root, lease=lease) as catalog:
            InstrumentSnapshotStoreV1(root, lease, catalog).retain(fetched)
        with DuckDBCatalog(root, lease=lease) as catalog:
            resolved = InstrumentSnapshotStoreV1(root, lease, catalog).resolve_equity(
                source=SNAPSHOT_SOURCE_V1,
                segment="NSE_EQ",
                symbol="ALPHA",
                as_of=fetched.retrieved_at,
            )
        return resolve_current_research_binding_v2(
            root,
            lease,
            resolved,
            selected_at=_SELECTED,
            decision_cutoff=_CUTOFF,
            schedule_identity_sha256="a" * 64,
        )


def test_mapping_successor_revalidates_retained_snapshot_and_exact_fields(
    tmp_path: Path,
) -> None:
    root = tmp_path / "mapping"
    root.mkdir(mode=0o700)
    binding = _binding(root)
    projection = validate_current_research_binding_v2(binding)
    member = projection.members[0]

    assert projection.origin == "RETAINED_INSTRUMENT_SNAPSHOT"
    assert projection.selected_at == _SELECTED
    assert (member.isin, member.exchange, member.effective_symbol) == (
        "INE002A01018",
        "NSE",
        "ALPHA",
    )
    assert (
        member.mapping_valid_from == member.mapping_valid_through == date(2026, 8, 26)
    )
    assert member.discovery_retrieved_at == datetime(2026, 8, 26, 8, tzinfo=UTC)


def test_mapping_binding_rejects_constructed_copied_and_mutated_values(
    tmp_path: Path,
) -> None:
    root = tmp_path / "mapping-negative"
    root.mkdir(mode=0o700)
    binding = _binding(root)
    with pytest.raises(TypeError, match="producer-minted"):
        AdmittedCurrentResearchBindingV2()
    with pytest.raises(ValueError, match="not admitted"):
        validate_current_research_binding_v2(object())
    object.__setattr__(
        binding.projection.members[0], "provider_mapping_revision", "substituted"
    )
    with pytest.raises(ValueError, match="not admitted"):
        validate_current_research_binding_v2(binding)
