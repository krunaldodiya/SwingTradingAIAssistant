"""Producer-owned mapping successor tests for Issue #187."""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import fields
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data import current_research_binding_v2
from swing_trading_ai_assistant.market_data.adjusted_daily.service_v3 import (
    mapping_identity_v3,
)
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.current_research_binding_v2 import (
    AdmittedCurrentResearchBindingV2,
    CurrentResearchMappingMemberV2,
    CurrentResearchMappingProjectionV2,
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


def _binding(
    root: Path,
    *,
    selected_at: datetime = _SELECTED,
    decision_cutoff: datetime = _CUTOFF,
    snapshot_retrieved_at: datetime = datetime(2026, 8, 26, 8, tzinfo=UTC),
    snapshot_observation_date: date = date(2026, 8, 26),
    instruments: tuple[dict[str, str], ...] = (_INSTRUMENT,),
    schedule_identity_sha256: str = "a" * 64,
):
    decompressed = json.dumps(list(instruments), separators=(",", ":")).encode()
    compressed = gzip.compress(decompressed, mtime=0)
    fetched = FetchedInstrumentSnapshotV1(
        snapshot_retrieved_at,
        snapshot_observation_date,
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
            resolved = tuple(
                InstrumentSnapshotStoreV1(root, lease, catalog).resolve_equity(
                    source=SNAPSHOT_SOURCE_V1,
                    segment="NSE_EQ",
                    symbol=item["trading_symbol"],
                    as_of=fetched.retrieved_at,
                )
                for item in instruments
            )
        return resolve_current_research_binding_v2(
            root,
            lease,
            resolved,
            selected_at=selected_at,
            decision_cutoff=decision_cutoff,
            schedule_identity_sha256=schedule_identity_sha256,
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


def test_mapping_uses_selected_ist_date_across_utc_rollover(tmp_path: Path) -> None:
    selected = datetime(2026, 8, 25, 18, 31, tzinfo=UTC)
    cutoff = selected + timedelta(minutes=5)
    retrieved = selected - timedelta(minutes=1)
    root = tmp_path / "current-ist-snapshot"
    root.mkdir(mode=0o700)
    binding = _binding(
        root,
        selected_at=selected,
        decision_cutoff=cutoff,
        snapshot_retrieved_at=retrieved,
        snapshot_observation_date=date(2026, 8, 26),
    )
    assert validate_current_research_binding_v2(binding).members[0].valid_from == date(
        2026, 8, 26
    )

    stale_root = tmp_path / "previous-utc-date-snapshot"
    stale_root.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="invalid fetched instrument snapshot"):
        _binding(
            stale_root,
            selected_at=selected,
            decision_cutoff=cutoff,
            snapshot_retrieved_at=retrieved,
            snapshot_observation_date=date(2026, 8, 25),
        )


def _same_pass_member(
    member: CurrentResearchMappingMemberV2,
) -> CurrentResearchMappingMemberV2:
    return CurrentResearchMappingMemberV2(
        member.isin,
        member.exchange,
        member.effective_symbol,
        member.instrument_type,
        member.segment,
        member.valid_from,
        member.valid_through,
        member.provider_symbol,
        member.mapping_version,
        member.mapping_valid_from,
        member.mapping_valid_through,
        mapping_identity_v3(
            isin=member.isin,
            exchange=member.exchange,
            instrument_type=member.instrument_type,
            segment=member.segment,
            effective_symbol=member.effective_symbol,
            provider_symbol=member.provider_symbol,
            mapping_valid_from=member.mapping_valid_from,
            mapping_valid_through=member.mapping_valid_through,
        ),
        member.provider_mapping_revision,
        None,
        None,
        None,
        ("RAW_MAPPING_MISSING",),
    )


def _fully_rehashed_projection(
    projection: CurrentResearchMappingProjectionV2,
    member: CurrentResearchMappingMemberV2,
) -> CurrentResearchMappingProjectionV2:
    values = {
        item.name: getattr(projection, item.name)
        for item in fields(CurrentResearchMappingProjectionV2)
    }
    values["members"] = (member,)
    values["mapping_projection_identity_sha256"] = current_research_binding_v2._digest(  # pyright: ignore[reportPrivateUsage]
        {
            name: value
            for name, value in values.items()
            if name != "mapping_projection_identity_sha256"
        }
    )
    return CurrentResearchMappingProjectionV2(**values)


@pytest.mark.parametrize(
    "origin", ("RETAINED_INSTRUMENT_SNAPSHOT", "RETAINED_SAME_PASS_CONTEXT")
)
@pytest.mark.parametrize("interval", ("canonical", "provider"))
def test_mapping_projection_rejects_fully_rehashed_selected_date_interval_substitution(
    tmp_path: Path, origin: str, interval: str
) -> None:
    root = tmp_path / "mapping-interval-negative"
    root.mkdir(mode=0o700)
    snapshot = validate_current_research_binding_v2(_binding(root))
    if origin == "RETAINED_INSTRUMENT_SNAPSHOT":
        projection = snapshot
        member = snapshot.members[0]
    else:
        base = _same_pass_member(snapshot.members[0])
        values = {
            item.name: getattr(snapshot, item.name)
            for item in fields(CurrentResearchMappingProjectionV2)
        }
        values.update(
            origin=origin,
            members=(base,),
            context_identity_sha256="b" * 64,
            context_object_sha256="c" * 64,
            context_receipt_identity_sha256="d" * 64,
            completion_marker_identity_sha256="e" * 64,
            retained_context_identity_sha256="f" * 64,
            canonical_cohort_identity_sha256=current_research_binding_v2._digest(  # pyright: ignore[reportPrivateUsage]
                (base,)
            ),
        )
        values["mapping_projection_identity_sha256"] = (
            current_research_binding_v2._digest(  # pyright: ignore[reportPrivateUsage]
                {
                    name: value
                    for name, value in values.items()
                    if name != "mapping_projection_identity_sha256"
                }
            )
        )
        projection = CurrentResearchMappingProjectionV2(**values)
        member = base
    selected = projection.selected_at.date()
    if interval == "canonical":
        substituted = CurrentResearchMappingMemberV2(
            member.isin,
            member.exchange,
            member.effective_symbol,
            member.instrument_type,
            member.segment,
            selected + timedelta(days=1),
            selected + timedelta(days=2),
            member.provider_symbol,
            member.mapping_version,
            member.mapping_valid_from,
            member.mapping_valid_through,
            member.mapping_identity_sha256,
            member.provider_mapping_revision,
            member.discovery_source,
            member.discovery_observation_identity_sha256,
            member.discovery_retrieved_at,
            member.discovery_failure_reasons,
        )
    else:
        mapping_valid_from = selected + timedelta(days=1)
        mapping_identity = (
            member.mapping_identity_sha256
            if origin == "RETAINED_INSTRUMENT_SNAPSHOT"
            else mapping_identity_v3(
                isin=member.isin,
                exchange=member.exchange,
                instrument_type=member.instrument_type,
                segment=member.segment,
                effective_symbol=member.effective_symbol,
                provider_symbol=member.provider_symbol,
                mapping_valid_from=mapping_valid_from,
                mapping_valid_through=None,
            )
        )
        substituted = CurrentResearchMappingMemberV2(
            member.isin,
            member.exchange,
            member.effective_symbol,
            member.instrument_type,
            member.segment,
            member.valid_from,
            member.valid_through,
            member.provider_symbol,
            member.mapping_version,
            mapping_valid_from,
            None,
            mapping_identity,
            member.provider_mapping_revision,
            member.discovery_source,
            member.discovery_observation_identity_sha256,
            member.discovery_retrieved_at,
            member.discovery_failure_reasons,
        )
    with pytest.raises(ValueError, match="mapping projection"):
        _fully_rehashed_projection(projection, substituted)


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
