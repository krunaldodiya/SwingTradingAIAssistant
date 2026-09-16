"""Existing-only reader for the immutable current Industry archive.

It deliberately does not call the classification writer: absence is a local
Industry outcome and must not create a directory, receipt, marker or ``known_at``.
"""

from __future__ import annotations

import hashlib
import json
import os
import weakref
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, NoReturn, cast
from zoneinfo import ZoneInfo

from . import current_industry_classification as classification
from .current_raw_price_context import (
    AdmittedCurrentRawContextV1,
    admitted_current_raw_context_binding_v1,
)
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
class _IndustryProjectionDataV1:
    """Registry-private verified archive projection, never caller authority."""

    snapshot_identity_sha256: str
    retained_identity_sha256: str
    original_cohort_identity_sha256: str
    known_at: datetime
    rows: tuple[tuple[str, str, str, str], ...]
    raw_input_identity_sha256: str
    raw_request_identity_sha256: str
    ordered_selection_identity_sha256: str
    canonical_cohort_identity_sha256: str
    comparison_session: date
    decision_session: date
    evidence_cutoff: datetime


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True, repr=False)
class AdmittedCurrentIndustryProjectionV1:
    """Opaque reader-minted authority for one exact raw capability."""

    _seal: object = field(repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("current Industry projection constructor unavailable")

    def __repr__(self) -> str:
        return "AdmittedCurrentIndustryProjectionV1()"

    def __copy__(self) -> AdmittedCurrentIndustryProjectionV1:
        raise TypeError("current Industry projection copy unavailable")

    def __deepcopy__(self, memo: object) -> AdmittedCurrentIndustryProjectionV1:
        del memo
        raise TypeError("current Industry projection copy unavailable")

    def __reduce__(self) -> str:
        raise TypeError("current Industry projection serialization unavailable")

    def __getstate__(self) -> object:
        raise TypeError("current Industry projection serialization unavailable")


_ADMITTED_PROJECTIONS: dict[
    int,
    tuple[
        weakref.ReferenceType[AdmittedCurrentIndustryProjectionV1],
        _IndustryProjectionDataV1,
        bytes,
        object,
        tuple[int, int],
        int,
    ],
] = {}


def _mint_admitted_current_industry_projection_v1(
    *,
    snapshot_identity_sha256: str,
    retained_identity_sha256: str,
    original_cohort_identity_sha256: str,
    known_at: datetime,
    rows: tuple[tuple[str, str, str, str], ...],
    raw: AdmittedCurrentRawContextV1,
) -> AdmittedCurrentIndustryProjectionV1:
    raw_projection, root_identity = admitted_current_raw_context_binding_v1(raw)
    projection = object.__new__(AdmittedCurrentIndustryProjectionV1)
    seal = object()
    values = _IndustryProjectionDataV1(
        snapshot_identity_sha256=snapshot_identity_sha256,
        retained_identity_sha256=retained_identity_sha256,
        original_cohort_identity_sha256=original_cohort_identity_sha256,
        known_at=known_at,
        rows=rows,
        raw_input_identity_sha256=raw_projection.input_identity_sha256,
        raw_request_identity_sha256=raw_projection.request_identity_sha256,
        ordered_selection_identity_sha256=raw_projection.ordered_selection_identity_sha256,
        canonical_cohort_identity_sha256=raw_projection.canonical_cohort_identity_sha256,
        comparison_session=raw_projection.sessions[0].session,
        decision_session=raw_projection.sessions[-1].session,
        evidence_cutoff=raw_projection.evidence_cutoff,
    )
    object.__setattr__(projection, "_seal", seal)
    identity = id(projection)

    def _forget(_reference: object, *, _identity: int = identity) -> None:
        _ADMITTED_PROJECTIONS.pop(_identity, None)

    _ADMITTED_PROJECTIONS[identity] = (
        weakref.ref(projection, _forget),
        values,
        _canonical(values),
        seal,
        root_identity,
        id(raw),
    )
    return projection


def current_industry_projection_is_admitted_v1(value: object) -> bool:
    """Return whether ``value`` is the exact reader-minted capability."""
    if type(value) is not AdmittedCurrentIndustryProjectionV1:
        return False
    entry = _ADMITTED_PROJECTIONS.get(id(value))
    if entry is None or entry[0]() is not value:
        return False
    return entry[2] == _canonical(entry[1]) and entry[3] is object.__getattribute__(
        value, "_seal"
    )


def admitted_current_industry_binding_v1(
    value: object,
) -> tuple[_IndustryProjectionDataV1, tuple[int, int], int]:
    if not current_industry_projection_is_admitted_v1(value):
        raise ValueError("current Industry projection is not admitted")
    projection = cast(AdmittedCurrentIndustryProjectionV1, value)
    entry = _ADMITTED_PROJECTIONS[id(projection)]
    return entry[1], entry[4], entry[5]


class _IndustryLocalRefusal(Exception):
    def __init__(
        self,
        state: Literal[
            "UNSUPPORTED", "INSUFFICIENT_EVIDENCE", "MALFORMED_EVIDENCE", "CONFLICTED"
        ],
        reason: str,
    ) -> None:
        self.state: Literal[
            "UNSUPPORTED", "INSUFFICIENT_EVIDENCE", "MALFORMED_EVIDENCE", "CONFLICTED"
        ] = state
        self.reason = reason


def _local_failure(
    storage_root: Path,
    root_identity: tuple[int, int],
    refusal: _IndustryLocalRefusal,
) -> CurrentIndustryReadFailureV1:
    """A local archive refusal never masks a concurrent shared-root loss."""
    if StorageRootLease.admit_existing_private_identity(storage_root) != root_identity:
        raise StorageRootLeaseError("current Industry root authority lost")
    return CurrentIndustryReadFailureV1(refusal.state, refusal.reason)


def _refuse(
    state: Literal[
        "UNSUPPORTED", "INSUFFICIENT_EVIDENCE", "MALFORMED_EVIDENCE", "CONFLICTED"
    ],
    reason: str,
) -> NoReturn:
    raise _IndustryLocalRefusal(state, reason)


def _reread_exact(directory: int, name: str, expected: bytes, maximum: int) -> None:
    """Reject same-name replacement after calculation and before admission."""
    if _read(directory, name, maximum) != expected:
        _refuse("CONFLICTED", "CLASSIFICATION_ARCHIVE_SUBSTITUTED")


def read_current_industry_archive_exact_v1(  # noqa: C901 -- one ordered existing-only verification transaction
    reference: CurrentIndustryArchiveReferenceV1,
    *,
    storage_root: Path,
    lease: StorageRootLease,
    raw: AdmittedCurrentRawContextV1,
) -> AdmittedCurrentIndustryProjectionV1 | CurrentIndustryReadFailureV1:
    """Reconstruct one named archive bound to one admitted raw selection."""
    if type(reference) is not CurrentIndustryArchiveReferenceV1:
        raise ValueError("current industry reader input is invalid")
    raw_projection, raw_root_identity = admitted_current_raw_context_binding_v1(raw)
    if (
        StorageRootLease.admit_existing_private_identity(storage_root)
        != raw_root_identity
    ):
        raise StorageRootLeaseError("current Industry root authority lost")
    try:
        with lease.read_operation(storage_root) as operation:
            root = operation.descriptor
            directory = os.open(
                ".current-industry-classification-v1",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=root,
            )
            active_error: BaseException | None = None
            try:
                snapshot_name = f"snapshot-{reference.snapshot_identity_sha256}.json"
                receipt_name = f"retained-{reference.snapshot_identity_sha256}.json"
                marker_name = f"completion-{reference.snapshot_identity_sha256}.json"
                snapshot_raw = _read(directory, snapshot_name, 262_144)
                receipt_raw = _read(directory, receipt_name, 262_144)
                marker_raw = _read(directory, marker_name, 16_384)
                if snapshot_raw is None or receipt_raw is None or marker_raw is None:
                    _refuse("INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_MISSING")
                candidate = classification._retained_candidate_from_receipt(receipt_raw)  # pyright: ignore[reportPrivateUsage]
                candidate_value = cast(Any, candidate)
                if (
                    candidate_value.retained_identity_sha256
                    != reference.retained_identity_sha256
                ):
                    _refuse("CONFLICTED", "CLASSIFICATION_RECEIPT_SUBSTITUTED")
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
                    _refuse("CONFLICTED", "CLASSIFICATION_SNAPSHOT_SUBSTITUTED")
                raw_name = f"raw-{snapshot.artifact_sha256}.csv"
                raw_bytes = _read(directory, raw_name, 1_048_576)
                if raw_bytes is None:
                    _refuse("INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARTIFACT_MISSING")
                if hashlib.sha256(raw_bytes).hexdigest() != snapshot.artifact_sha256:
                    _refuse("CONFLICTED", "CLASSIFICATION_ARTIFACT_SUBSTITUTED")
                input_value = classification.CurrentIndustryClassificationInputV1(
                    {
                        "contract_version": "current-supplied-cohort-industry-classification@v1",
                        "schema_identity_sha256": classification.CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
                        "source_url": "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
                        "source_authority": "NSE_INDICES",
                        "source_domain": "nsearchives.nseindia.com",
                        "acquisition_method": "BOUNDED_OFFICIAL_FETCH",
                        "artifact_byte_count": len(raw_bytes),
                        "artifact_sha256": snapshot.artifact_sha256,
                        "artifact_revision": f"sha256:{snapshot.artifact_sha256}",
                        "classification_tier": "INDUSTRY",
                        "publisher_published_at": None,
                        "publisher_effective_from": None,
                        "publisher_effective_through": None,
                        "publisher_revision": None,
                        "licence_policy_identity_sha256": classification.CURRENT_INDUSTRY_LICENCE_POLICY_IDENTITY_SHA256,
                    }
                )
                if input_value.input_identity_sha256 != snapshot.input_identity_sha256:
                    _refuse("UNSUPPORTED", "UNSUPPORTED_CLASSIFICATION_SCHEMA")
                parsed = classification.parse_current_industry_artifact_v1(
                    input_value, raw_bytes
                )
                if (
                    type(parsed)
                    is classification.CurrentIndustryClassificationFailureV1
                ):
                    _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARTIFACT_MALFORMED")
                reproduced = classification.project_current_supplied_cohort_industry_v1(
                    cast(classification.ParsedCurrentIndustryArtifactV1, parsed),
                    snapshot.cohort_identity_sha256,
                    tuple(
                        classification.CurrentIndustryCohortMemberV1(
                            isin=row.isin,
                            exchange=row.exchange,
                            effective_symbol=row.effective_symbol,
                        )
                        for row in snapshot.private_rows
                    ),
                )
                if (
                    type(reproduced)
                    is classification.CurrentIndustryClassificationFailureV1
                    or reproduced.canonical_json_bytes() != snapshot_raw
                ):
                    _refuse("CONFLICTED", "CLASSIFICATION_PROJECTION_SUBSTITUTED")
                marker_known_at = classification._completion_marker_known_at(  # pyright: ignore[reportPrivateUsage]
                    marker_raw, receipt_raw, snapshot
                )
                if marker_known_at != candidate.known_at:
                    _refuse("CONFLICTED", "CLASSIFICATION_MARKER_SUBSTITUTED")
                rows = tuple(
                    (row.isin, row.exchange, row.effective_symbol, row.industry)
                    for row in snapshot.private_rows
                )
                expected = tuple(
                    (member.isin, member.exchange, member.effective_symbol)
                    for member in raw_projection.members
                )
                if len(rows) != len(expected) or {row[:3] for row in rows} != set(
                    expected
                ):
                    _refuse("CONFLICTED", "CLASSIFICATION_COHORT_BINDING_MISMATCH")
                if candidate.known_at > raw_projection.evidence_cutoff:
                    _refuse("INSUFFICIENT_EVIDENCE", "CLASSIFICATION_FUTURE_KNOWN")
                if (
                    candidate.known_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
                    != raw_projection.evidence_cutoff.astimezone(
                        ZoneInfo("Asia/Kolkata")
                    ).date()
                ):
                    _refuse("INSUFFICIENT_EVIDENCE", "CLASSIFICATION_STALE")
                _reread_exact(directory, raw_name, raw_bytes, 1_048_576)
                _reread_exact(directory, snapshot_name, snapshot_raw, 262_144)
                _reread_exact(directory, receipt_name, receipt_raw, 262_144)
                _reread_exact(directory, marker_name, marker_raw, 16_384)
                classification._validate_archive_directory(root, directory)  # pyright: ignore[reportPrivateUsage]
                classification._validate_archive_root(root)  # pyright: ignore[reportPrivateUsage]
                operation.ensure_live()
            except BaseException as error:
                active_error = error
                raise
            finally:
                try:
                    os.close(directory)
                except BaseException:
                    if active_error is None:
                        raise
    except _IndustryLocalRefusal as refusal:
        return _local_failure(storage_root, raw_root_identity, refusal)
    except FileNotFoundError:
        return _local_failure(
            storage_root,
            raw_root_identity,
            _IndustryLocalRefusal(
                "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_MISSING"
            ),
        )
    if (
        StorageRootLease.admit_existing_private_identity(storage_root)
        != raw_root_identity
    ):
        raise StorageRootLeaseError("current Industry root authority lost")
    return _mint_admitted_current_industry_projection_v1(
        snapshot_identity_sha256=reference.snapshot_identity_sha256,
        retained_identity_sha256=reference.retained_identity_sha256,
        original_cohort_identity_sha256=snapshot.cohort_identity_sha256,
        known_at=candidate.known_at,
        rows=rows,
        raw=raw,
    )


def _wire(value: object) -> object:
    if type(value) is datetime:
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if type(value) is date:
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _wire(getattr(value, item.name)) for item in fields(value)}
    if type(value) is tuple:
        return [_wire(item) for item in cast(tuple[object, ...], value)]
    if type(value) is dict:
        return {
            str(key): _wire(item)
            for key, item in cast(dict[object, object], value).items()
        }
    return value


def _canonical(value: object) -> bytes:
    return (
        json.dumps(_wire(value), sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )


def _read(directory: int, name: str, maximum: int) -> bytes | None:
    """Translate only the archive reader's stable-object validation refusal."""
    try:
        value = classification._read_stable_private_object(directory, name, maximum)  # pyright: ignore[reportPrivateUsage]
    except ValueError:
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
    return None if value is None else value[0]
