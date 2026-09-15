"""Admission-capability contracts for the current Industry archive reader."""

from __future__ import annotations

import copy
import pickle
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.current_industry_archive_reader import (
    AdmittedCurrentIndustryProjectionV1,
    CurrentIndustryArchiveReferenceV1,
    current_industry_projection_is_admitted_v1,
    read_current_industry_archive_exact_v1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease


def _forged() -> AdmittedCurrentIndustryProjectionV1:
    candidate = object.__new__(AdmittedCurrentIndustryProjectionV1)
    for name, value in (
        ("snapshot_identity_sha256", "a" * 64),
        ("retained_identity_sha256", "b" * 64),
        ("original_cohort_identity_sha256", "c" * 64),
        ("known_at", datetime(2026, 9, 15, 9, tzinfo=UTC)),
        ("rows", (("INE000A01001", "NSE", "AAA", "Banks"),)),
        ("raw_input_identity_sha256", "d" * 64),
        ("raw_request_identity_sha256", "e" * 64),
        ("ordered_selection_identity_sha256", "f" * 64),
        ("canonical_cohort_identity_sha256", "0" * 64),
        ("comparison_session", datetime(2026, 9, 1, tzinfo=UTC).date()),
        ("decision_session", datetime(2026, 9, 30, tzinfo=UTC).date()),
        ("evidence_cutoff", datetime(2026, 9, 15, 9, tzinfo=UTC)),
        ("_seal", object()),
    ):
        object.__setattr__(candidate, name, value)
    return candidate


def test_industry_projection_cannot_be_constructed_copied_or_serialized() -> None:
    with pytest.raises(TypeError, match="constructor unavailable"):
        AdmittedCurrentIndustryProjectionV1()  # type: ignore[call-arg]
    candidate = _forged()
    assert current_industry_projection_is_admitted_v1(candidate) is False
    for operation in (
        lambda: copy.copy(candidate),
        lambda: copy.deepcopy(candidate),
        lambda: pickle.dumps(candidate),
        lambda: replace(candidate),
    ):
        with pytest.raises(TypeError):
            operation()


def test_reader_refuses_a_caller_forged_raw_authority_before_archive_io(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire_private_empty(tmp_path)
    assert acquired.lease is not None
    try:
        with pytest.raises(ValueError, match="not admitted"):
            read_current_industry_archive_exact_v1(
                CurrentIndustryArchiveReferenceV1(
                    "current-industry-archive-reference@v1", "a" * 64, "b" * 64
                ),
                storage_root=tmp_path,
                lease=acquired.lease,
                raw=object(),  # type: ignore[arg-type]
            )
    finally:
        acquired.lease.close()
