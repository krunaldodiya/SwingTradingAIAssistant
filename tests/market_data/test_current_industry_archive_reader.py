"""Focused existing-only reader contracts for the current Industry archive."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data import (
    current_industry_classification as classification,
)
from swing_trading_ai_assistant.market_data.current_industry_archive_reader import (
    AdmittedCurrentIndustryProjectionV1,
    CurrentIndustryArchiveReferenceV1,
    current_industry_projection_is_admitted_v1,
    read_current_industry_archive_exact_v1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease


def _isin(index: int) -> str:
    prefix = f"INE{index:08d}"
    digits = "".join(str(ord(char) - 55) if char.isalpha() else char for char in prefix)
    for check in range(10):
        total = sum(
            value if position % 2 == 0 else (value * 2 - 9 if value > 4 else value * 2)
            for position, value in enumerate(map(int, reversed(digits + str(check))))
        )
        if total % 10 == 0:
            return prefix + str(check)
    raise AssertionError("unreachable ISIN check digit")


def _artifact() -> bytes:
    header = "Company Name,Industry,Symbol,Series,ISIN Code"
    rows = [
        f"Company {index:03d},Banking,SYM{index:03d},EQ,{_isin(index)}"
        for index in range(100)
    ]
    return ("\n".join((header, *rows)) + "\n").encode()


def _input(artifact: bytes) -> classification.CurrentIndustryClassificationInputV1:
    digest = hashlib.sha256(artifact).hexdigest()
    value = {
        "contract_version": "current-supplied-cohort-industry-classification@v1",
        "schema_identity_sha256": classification.CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
        "source_url": "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
        "source_authority": "NSE_INDICES",
        "source_domain": "nsearchives.nseindia.com",
        "acquisition_method": "BOUNDED_OFFICIAL_FETCH",
        "artifact_byte_count": len(artifact),
        "artifact_sha256": digest,
        "artifact_revision": f"sha256:{digest}",
        "classification_tier": "INDUSTRY",
        "publisher_published_at": None,
        "publisher_effective_from": None,
        "publisher_effective_through": None,
        "publisher_revision": None,
        "licence_policy_identity_sha256": classification.CURRENT_INDUSTRY_LICENCE_POLICY_IDENTITY_SHA256,
    }
    return (
        classification.CurrentIndustryClassificationInputV1.from_canonical_json_bytes(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        )
    )


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


def test_real_archive_reader_reconstructs_artifact_and_mints_capability(
    tmp_path: Path,
) -> None:
    artifact = _artifact()
    input_value = _input(artifact)
    parsed = classification.parse_current_industry_artifact_v1(input_value, artifact)
    assert type(parsed) is classification.ParsedCurrentIndustryArtifactV1
    snapshot = classification.project_current_supplied_cohort_industry_v1(
        parsed,
        "a" * 64,
        tuple(
            classification.CurrentIndustryCohortMemberV1(
                _isin(index), "NSE", f"SYM{index:03d}"
            )
            for index in range(2)
        ),
    )
    assert type(snapshot) is classification.PrivateCurrentIndustrySnapshotV1
    tmp_path.chmod(0o700)
    write = StorageRootLease.try_acquire_private_empty(tmp_path)
    assert write.lease is not None
    try:
        retained = classification.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            input_value, artifact, snapshot, write.lease
        )
    finally:
        write.lease.close()
    assert type(retained) is classification.RetainedCurrentIndustrySnapshotV1
    read = StorageRootLease.try_admit_read_existing(tmp_path)
    assert read.lease is not None
    try:
        outcome = read_current_industry_archive_exact_v1(
            CurrentIndustryArchiveReferenceV1(
                "current-industry-archive-reference@v1",
                retained.snapshot_identity_sha256,
                retained.retained_identity_sha256,
            ),
            storage_root=tmp_path,
            lease=read.lease,
            cutoff=retained.known_at + timedelta(seconds=1),
        )
    finally:
        read.lease.close()

    assert type(outcome) is AdmittedCurrentIndustryProjectionV1
    assert current_industry_projection_is_admitted_v1(outcome)
    assert len(outcome.rows) == 2


def test_industry_projection_cannot_be_constructed_or_copied_into_admission() -> None:
    with pytest.raises(TypeError, match="constructor unavailable"):
        AdmittedCurrentIndustryProjectionV1(  # type: ignore[call-arg]
            "a" * 64,
            "b" * 64,
            "c" * 64,
            datetime(2026, 9, 15, 9, tzinfo=UTC),
            (),
        )

    # Decoded/copied values are never equivalent to an owner-private read.
    candidate = object.__new__(AdmittedCurrentIndustryProjectionV1)
    for name, value in (
        ("snapshot_identity_sha256", "a" * 64),
        ("retained_identity_sha256", "b" * 64),
        ("original_cohort_identity_sha256", "c" * 64),
        ("known_at", datetime(2026, 9, 15, 9, tzinfo=UTC)),
        ("rows", (("INE000A01001", "NSE", "AAA", "Banks"),)),
        ("_seal", object()),
    ):
        object.__setattr__(candidate, name, value)
    assert current_industry_projection_is_admitted_v1(candidate) is False
    assert current_industry_projection_is_admitted_v1(copy.copy(candidate)) is False
