"""Catalog-first access to immutable provisional one-minute snapshots."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from .catalog import DuckDBCatalog
from .monthly_request_planner import PlannedInstrumentMonth
from .provisional_metadata import ProvisionalPartitionMetadataV1
from .public_coverage import read_partition_under_lease
from .schemas import CanonicalCandle
from .storage_root_lease import StorageRootLease


class ProvisionalPartitionUnavailableV1(RuntimeError):
    """The latest catalog row or its immutable Parquet evidence is unusable."""


def latest_provisional_partition(
    root: Path,
    lease: StorageRootLease,
    plan: PlannedInstrumentMonth,
    *,
    cutoff_lte: datetime | None = None,
    published_at_lte: datetime | None = None,
) -> tuple[ProvisionalPartitionMetadataV1, tuple[CanonicalCandle, ...]] | None:
    """Resolve and verify the newest cutoff under one live root admission."""
    try:
        with DuckDBCatalog(root, read_only=True, lease=lease) as catalog:
            metadata = catalog.latest_provisional_partition(
                plan,
                cutoff_lte=cutoff_lte,
                published_at_lte=published_at_lte,
            )
            catalog.ensure_read_identity()
        if metadata is None:
            return None
        rows = load_provisional_partition(root, lease, metadata)
        return metadata, rows
    except Exception:
        raise ProvisionalPartitionUnavailableV1(
            "provisional partition unavailable"
        ) from None


def load_provisional_partition(
    root: Path,
    lease: StorageRootLease,
    metadata: ProvisionalPartitionMetadataV1,
) -> tuple[CanonicalCandle, ...]:
    """Verify catalog identity, checksum, bounds, and every row identity."""
    try:
        if type(metadata) is not ProvisionalPartitionMetadataV1:
            raise ValueError
        metadata = replace(metadata)
        digest, rows = read_partition_under_lease(root, lease, metadata.relative_path)
        plan = metadata.plan
        expected_identity = (
            plan.provider,
            plan.instrument_key,
            plan.security_id,
            plan.symbol,
            plan.exchange,
            plan.segment,
            plan.instrument_type,
            plan.interval,
        )
        if (
            digest != metadata.checksum_sha256
            or len(rows) != metadata.row_count
            or not rows
            or rows[0].ts != metadata.actual_from_ts
            or rows[-1].ts != metadata.actual_to_ts
            or rows[-1].ts != metadata.cutoff
            or any(
                (
                    row.provider,
                    row.instrument_key,
                    row.security_id,
                    row.symbol,
                    row.exchange,
                    row.segment,
                    row.instrument_type,
                    row.interval,
                )
                != expected_identity
                for row in rows
            )
        ):
            raise ValueError
        return rows
    except Exception:
        raise ProvisionalPartitionUnavailableV1(
            "provisional partition unavailable"
        ) from None
