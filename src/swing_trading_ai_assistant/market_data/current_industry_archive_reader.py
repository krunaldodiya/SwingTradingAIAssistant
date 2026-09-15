"""Existing-only reader for the immutable current Industry archive.

It deliberately does not call the classification writer: absence is a local
Industry outcome and must not create a directory, receipt, marker or ``known_at``.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from . import current_industry_classification as classification
from .storage_root_lease import StorageRootLease, StorageRootLeaseError


@dataclass(frozen=True, slots=True)
class CurrentIndustryArchiveReferenceV1:
    contract_version: Literal["current-industry-archive-reference@v1"]
    snapshot_identity_sha256: str
    retained_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            self.contract_version != "current-industry-archive-reference@v1"
            or not classification._valid_digest(self.snapshot_identity_sha256)  # pyright: ignore[reportPrivateUsage]
            or not classification._valid_digest(self.retained_identity_sha256)  # pyright: ignore[reportPrivateUsage]
        ):
            raise ValueError("current industry archive reference is invalid")


@dataclass(frozen=True, slots=True)
class CurrentIndustryReadFailureV1:
    state: Literal[
        "UNSUPPORTED", "INSUFFICIENT_EVIDENCE", "MALFORMED_EVIDENCE", "CONFLICTED"
    ]
    reason: str


@dataclass(frozen=True, slots=True)
class AdmittedCurrentIndustryProjectionV1:
    """Producer-minted private projection; callers receive no source rows."""

    snapshot_identity_sha256: str
    retained_identity_sha256: str
    original_cohort_identity_sha256: str
    known_at: datetime
    rows: tuple[tuple[str, str, str, str], ...]

    def __post_init__(self) -> None:
        if self.known_at.tzinfo is not UTC or not self.rows:
            raise ValueError("current industry projection is invalid")


def read_current_industry_archive_exact_v1(  # noqa: C901 -- one ordered existing-only verification transaction
    reference: CurrentIndustryArchiveReferenceV1,
    *,
    storage_root: Path,
    lease: StorageRootLease,
    cutoff: datetime,
) -> AdmittedCurrentIndustryProjectionV1 | CurrentIndustryReadFailureV1:
    """Reconstruct one named current archive without scanning or repairing it."""
    if type(reference) is not CurrentIndustryArchiveReferenceV1:
        raise ValueError("current industry reader input is invalid")
    if type(cutoff) is not datetime or cutoff.tzinfo is not UTC:
        raise ValueError("current industry reader cutoff is invalid")
    try:
        with lease.read_operation(storage_root) as operation:
            root = operation.descriptor
            directory = os.open(
                ".current-industry-classification-v1",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=root,
            )
            try:
                snapshot_raw = _read(
                    directory,
                    f"snapshot-{reference.snapshot_identity_sha256}.json",
                    262_144,
                )
                receipt_raw = _read(
                    directory,
                    f"retained-{reference.snapshot_identity_sha256}.json",
                    262_144,
                )
                marker_raw = _read(
                    directory,
                    f"completion-{reference.snapshot_identity_sha256}.json",
                    16_384,
                )
                if snapshot_raw is None or receipt_raw is None or marker_raw is None:
                    return CurrentIndustryReadFailureV1(
                        "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_MISSING"
                    )
                candidate = classification._retained_candidate_from_receipt(receipt_raw)  # pyright: ignore[reportPrivateUsage]
                candidate_value = cast(Any, candidate)
                if (
                    candidate_value.retained_identity_sha256
                    != reference.retained_identity_sha256
                ):
                    return CurrentIndustryReadFailureV1(
                        "CONFLICTED", "CLASSIFICATION_RECEIPT_SUBSTITUTED"
                    )
                snapshot = classification._snapshot_with_identity(  # pyright: ignore[reportPrivateUsage]
                    classification._snapshot(  # pyright: ignore[reportPrivateUsage]
                        evidence_state="PROJECTED",
                        schema_identity_sha256=candidate_value.schema_identity_sha256,
                        runtime_code_identity_sha256=candidate_value.snapshot_runtime_code_identity_sha256,
                        input_identity_sha256=candidate_value.input_identity_sha256,
                        artifact_sha256=candidate_value.artifact_sha256,
                        artifact_revision=candidate_value.artifact_revision,
                        cohort_identity_sha256=candidate_value.cohort_identity_sha256,
                        cohort_size=candidate_value.cohort_size,
                        private_rows=candidate_value._private_rows,
                        snapshot_identity_sha256="",
                    )
                )
                if (
                    snapshot.snapshot_identity_sha256
                    != reference.snapshot_identity_sha256
                    or snapshot.canonical_json_bytes() != snapshot_raw
                ):
                    return CurrentIndustryReadFailureV1(
                        "CONFLICTED", "CLASSIFICATION_SNAPSHOT_SUBSTITUTED"
                    )
                raw_name = f"raw-{snapshot.artifact_sha256}.csv"
                raw = _read(directory, raw_name, 1_048_576)
                if raw is None:
                    return CurrentIndustryReadFailureV1(
                        "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARTIFACT_MISSING"
                    )
                if hashlib.sha256(raw).hexdigest() != snapshot.artifact_sha256:
                    return CurrentIndustryReadFailureV1(
                        "CONFLICTED", "CLASSIFICATION_ARTIFACT_SUBSTITUTED"
                    )
                marker_known_at = classification._completion_marker_known_at(  # pyright: ignore[reportPrivateUsage]
                    marker_raw, receipt_raw, snapshot
                )  # pyright: ignore[reportPrivateUsage]
                if marker_known_at != candidate.known_at:
                    return CurrentIndustryReadFailureV1(
                        "CONFLICTED", "CLASSIFICATION_MARKER_SUBSTITUTED"
                    )
                operation.ensure_live()
            finally:
                os.close(directory)
    except FileNotFoundError:
        return CurrentIndustryReadFailureV1(
            "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_MISSING"
        )
    except (StorageRootLeaseError, OSError):
        raise
    except ValueError:
        return CurrentIndustryReadFailureV1(
            "MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED"
        )
    if candidate.known_at > cutoff:
        return CurrentIndustryReadFailureV1(
            "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_FUTURE_KNOWN"
        )
    rows = tuple(
        (row.isin, row.exchange, row.effective_symbol, row.industry)
        for row in snapshot.private_rows
    )
    return AdmittedCurrentIndustryProjectionV1(
        reference.snapshot_identity_sha256,
        reference.retained_identity_sha256,
        snapshot.cohort_identity_sha256,
        candidate.known_at,
        rows,
    )


def _read(directory: int, name: str, maximum: int) -> bytes | None:
    value = classification._read_stable_private_object(directory, name, maximum)  # pyright: ignore[reportPrivateUsage]
    return None if value is None else value[0]
