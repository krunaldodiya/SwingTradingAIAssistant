"""Existing-only reader for the immutable current Industry archive.

It deliberately does not call the classification writer: absence is a local
Industry outcome and must not create a directory, receipt, marker or ``known_at``.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import weakref
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
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
                _validate_snapshot_bytes(snapshot_raw, reference)
                _validate_receipt_bytes(receipt_raw, reference)
                candidate = classification._retained_candidate_from_receipt(  # pyright: ignore[reportPrivateUsage]
                    receipt_raw
                )
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
                expected_known_at = _validate_marker_bytes(
                    marker_raw, receipt_raw, reference.snapshot_identity_sha256
                )
                marker_known_at = classification._completion_marker_known_at(  # pyright: ignore[reportPrivateUsage]
                    marker_raw, receipt_raw, snapshot
                )
                if (
                    marker_known_at != expected_known_at
                    or marker_known_at != candidate.known_at
                ):
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
                if not _marker_mtime_at_or_before(
                    directory, marker_name, candidate.known_at
                ):
                    _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
                _validate_archive_directory(root, directory)
                _validate_archive_root(root)
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
    """Read one stable existing-only archive object with reader-owned validation."""
    value = _read_stable_private_object(directory, name, maximum)
    return None if value is None else value[0]


def _read_stable_private_object(
    parent: int, name: str, maximum: int
) -> tuple[bytes, os.stat_result] | None:
    """Reject malformed named private files without borrowing writer error wrappers."""
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent,
        )
    except FileNotFoundError:
        return None
    active_error: BaseException | None = None
    try:
        named_before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        opened_before = os.fstat(descriptor)
        if (
            maximum < 0
            or opened_before.st_size > maximum
            or not _private_regular_object(opened_before, opened_before.st_size)
            or not _same_metadata(named_before, opened_before)
        ):
            _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
        chunks: list[bytes] = []
        remaining = opened_before.st_size
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        opened_after = os.fstat(descriptor)
        named_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (
            not _same_metadata(opened_before, opened_after)
            or not _same_metadata(named_before, named_after)
            or not _same_metadata(opened_after, named_after)
            or not _private_regular_object(named_after, len(raw))
        ):
            _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
        return raw, named_after
    except BaseException as error:
        active_error = error
        raise
    finally:
        try:
            os.close(descriptor)
        except BaseException:
            if active_error is None:
                raise


def _private_regular_object(info: os.stat_result, size: int) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == 0o400
        and info.st_nlink == 1
        and info.st_size == size
    )


def _same_metadata(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        first.st_dev,
        first.st_ino,
        first.st_mode,
        first.st_uid,
        first.st_nlink,
        first.st_size,
        first.st_mtime_ns,
        first.st_ctime_ns,
    ) == (
        second.st_dev,
        second.st_ino,
        second.st_mode,
        second.st_uid,
        second.st_nlink,
        second.st_size,
        second.st_mtime_ns,
        second.st_ctime_ns,
    )


def _object_bytes(raw: bytes) -> dict[str, object]:
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
    if type(decoded) is not dict:
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
    value = cast(dict[str, object], decoded)
    if _canonical(value) != raw:
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
    return value


def _digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _private_rows(value: object, cohort_size: int) -> None:
    if type(value) is not list or not 1 <= cohort_size <= 50:
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
    rows = cast(list[object], value)
    if len(rows) != cohort_size:
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
    expected = {"effective_symbol", "exchange", "industry", "isin", "symbol"}
    parsed_rows: list[dict[str, str]] = []
    for row in rows:
        if type(row) is not dict:
            _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
        candidate = cast(dict[str, object], row)
        if set(candidate) != expected or any(
            type(candidate[field]) is not str for field in expected
        ):
            _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
        parsed = cast(dict[str, str], candidate)
        if (
            parsed["exchange"] != "NSE"
            or parsed["effective_symbol"] != parsed["symbol"]
        ):
            _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
        parsed_rows.append(parsed)
    identities = tuple(row["isin"] for row in parsed_rows)
    if identities != tuple(sorted(identities)) or len(set(identities)) != len(rows):
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")


def _validate_snapshot_bytes(
    raw: bytes, reference: CurrentIndustryArchiveReferenceV1
) -> None:
    if hashlib.sha256(raw).hexdigest() != reference.snapshot_identity_sha256:
        _refuse("CONFLICTED", "CLASSIFICATION_SNAPSHOT_SUBSTITUTED")
    value = _object_bytes(raw)
    expected = {
        "artifact_sha256",
        "artifact_revision",
        "cohort_identity_sha256",
        "cohort_size",
        "evidence_state",
        "input_identity_sha256",
        "private_rows",
        "runtime_code_identity_sha256",
        "schema_identity_sha256",
    }
    if (
        set(value) != expected
        or value["evidence_state"] != "PROJECTED"
        or value["schema_identity_sha256"]
        not in classification._CLASSIFICATION_SCHEMA_IDENTITIES  # pyright: ignore[reportPrivateUsage]
        or value["runtime_code_identity_sha256"]
        != classification._CLASSIFICATION_RUNTIME_IDENTITY  # pyright: ignore[reportPrivateUsage]
        or any(
            not _digest(value[field])
            for field in (
                "artifact_sha256",
                "cohort_identity_sha256",
                "input_identity_sha256",
                "runtime_code_identity_sha256",
                "schema_identity_sha256",
            )
        )
        or type(value["artifact_revision"]) is not str
        or value["artifact_revision"] != f"sha256:{value['artifact_sha256']}"
        or type(value["cohort_size"]) is not int
    ):
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
    _private_rows(value["private_rows"], value["cohort_size"])


def _validate_receipt_bytes(
    raw: bytes, reference: CurrentIndustryArchiveReferenceV1
) -> None:
    value = _object_bytes(raw)
    expected = {
        "archive_identity_sha256",
        "archive_receipt_identity_sha256",
        "artifact_revision",
        "artifact_sha256",
        "cohort_identity_sha256",
        "cohort_size",
        "evidence_state",
        "input_identity_sha256",
        "known_at",
        "private_rows",
        "publisher_effective_from",
        "publisher_effective_through",
        "publisher_published_at",
        "publisher_revision",
        "receipt_version",
        "retained_identity_sha256",
        "schema_identity_sha256",
        "snapshot_identity_sha256",
        "snapshot_runtime_code_identity_sha256",
    }
    if (
        set(value) != expected
        or value["receipt_version"] != "retained-current-industry-receipt@v1"
        or value["evidence_state"] != "RETAINED"
        or value["schema_identity_sha256"]
        not in classification._CLASSIFICATION_SCHEMA_IDENTITIES  # pyright: ignore[reportPrivateUsage]
        or value["snapshot_runtime_code_identity_sha256"]
        != classification._CLASSIFICATION_RUNTIME_IDENTITY  # pyright: ignore[reportPrivateUsage]
        or any(
            not _digest(value[field])
            for field in (
                "archive_identity_sha256",
                "archive_receipt_identity_sha256",
                "artifact_sha256",
                "cohort_identity_sha256",
                "input_identity_sha256",
                "retained_identity_sha256",
                "schema_identity_sha256",
                "snapshot_identity_sha256",
                "snapshot_runtime_code_identity_sha256",
            )
        )
        or value["snapshot_identity_sha256"] != reference.snapshot_identity_sha256
        or value["retained_identity_sha256"] != reference.retained_identity_sha256
        or type(value["artifact_revision"]) is not str
        or value["artifact_revision"] != f"sha256:{value['artifact_sha256']}"
        or type(value["cohort_size"]) is not int
        or any(
            value[field] is not None
            for field in (
                "publisher_effective_from",
                "publisher_effective_through",
                "publisher_published_at",
                "publisher_revision",
            )
        )
    ):
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
    _private_rows(value["private_rows"], value["cohort_size"])
    _parse_known_at(value["known_at"])


def _parse_known_at(value: object) -> datetime:
    if type(value) is not str:
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
    try:
        known_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
    if known_at.tzinfo is not UTC or known_at.utcoffset() != UTC.utcoffset(known_at):
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
    if known_at.isoformat(timespec="microseconds").replace("+00:00", "Z") != value:
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
    return known_at


def _validate_marker_bytes(
    raw: bytes, receipt_raw: bytes, snapshot_identity: str
) -> datetime:
    value = _object_bytes(raw)
    if (
        set(value)
        != {
            "completion_marker_version",
            "known_at",
            "receipt_sha256",
            "snapshot_identity_sha256",
        }
        or value["completion_marker_version"]
        != "retained-current-industry-completion@v1"
        or value["receipt_sha256"] != hashlib.sha256(receipt_raw).hexdigest()
        or value["snapshot_identity_sha256"] != snapshot_identity
    ):
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
    return _parse_known_at(value["known_at"])


def _marker_mtime_at_or_before(directory: int, name: str, known_at: datetime) -> bool:
    info = os.stat(name, dir_fd=directory, follow_symlinks=False)
    epoch = datetime(1970, 1, 1, tzinfo=known_at.tzinfo)
    delta = known_at - epoch
    deadline_ns = (
        delta.days * 86_400 + delta.seconds
    ) * 1_000_000_000 + delta.microseconds * 1_000
    return max(info.st_mtime_ns, info.st_ctime_ns) <= deadline_ns


def _validate_archive_root(root: int) -> None:
    info = os.fstat(root)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")


def _validate_archive_directory(root: int, directory: int) -> None:
    opened = os.fstat(directory)
    named = os.stat(
        ".current-industry-classification-v1", dir_fd=root, follow_symlinks=False
    )
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or stat.S_IMODE(opened.st_mode) != 0o700
        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
    ):
        _refuse("MALFORMED_EVIDENCE", "CLASSIFICATION_ARCHIVE_MALFORMED")
