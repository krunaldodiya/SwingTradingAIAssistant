"""Focused existing-only reader contracts for the current Industry archive."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from swing_trading_ai_assistant.market_data.current_industry_archive_reader import (
    CurrentIndustryArchiveReferenceV1,
    read_current_industry_archive_exact_v1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease


def test_missing_named_archive_is_local_insufficiency_and_creates_nothing(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire_private_empty(tmp_path)
    assert acquired.lease is not None
    before = tuple(tmp_path.iterdir())
    try:
        outcome = read_current_industry_archive_exact_v1(
            CurrentIndustryArchiveReferenceV1(
                "current-industry-archive-reference@v1", "a" * 64, "b" * 64
            ),
            storage_root=tmp_path,
            lease=acquired.lease,
            cutoff=datetime(2026, 9, 15, 9, tzinfo=UTC),
        )
    finally:
        acquired.lease.close()

    assert type(outcome).__name__ == "CurrentIndustryReadFailureV1"
    assert outcome.state == "INSUFFICIENT_EVIDENCE"  # type: ignore[union-attr]
    assert outcome.reason == "CLASSIFICATION_ARCHIVE_MISSING"  # type: ignore[union-attr]
    assert tuple(tmp_path.iterdir()) == before
