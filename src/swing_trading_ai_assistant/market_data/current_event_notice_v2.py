"""Archive-bound, member-local current event evidence for Issue #187."""

from __future__ import annotations

import hashlib
import json
import os
import weakref
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final, Literal, cast
from zoneinfo import ZoneInfo

from .current_event_notice import (
    CurrentEventCohortMemberV1,
    CurrentEventNoticeFailureV1,
    CurrentEventNoticeInputV1,
    CurrentEventNoticeMemberResultV1,
    CurrentEventNoticeV1,
    RetainedCurrentEventNoticeSnapshotV1,
    _member_result,  # pyright: ignore[reportPrivateUsage]
    _open_archive,  # pyright: ignore[reportPrivateUsage]
    _parse_filename,  # pyright: ignore[reportPrivateUsage]
    _publish_object,  # pyright: ignore[reportPrivateUsage]
    _read_stable_private_object,  # pyright: ignore[reportPrivateUsage]
    _relevant_row_failure,  # pyright: ignore[reportPrivateUsage]
    _trusted_utc_now,  # pyright: ignore[reportPrivateUsage]
    current_event_notice_runtime_code_identity_v1,
    parse_current_event_notice_artifact_v1,
    validate_retained_current_event_notice_v1,
)
from .current_event_notice_v2_runtime_identity_manifest import (
    CURRENT_EVENT_NOTICE_RUNTIME_SOURCE_SHA256_V2,
)
from .current_research_binding_v2 import (
    AdmittedCurrentResearchBindingV2,
    CurrentResearchMappingMemberV2,
    CurrentResearchMappingProjectionV2,
    validate_current_research_binding_v2,
)
from .runtime_source_verifier import runtime_source_sha256
from .storage_root_lease import StorageRootLease

_CONTRACT: Final = "current-event-notice@v2"
_SCHEMA_IDENTITY: Final = hashlib.sha256(
    b"current-event-notice-schema@v2\n"
).hexdigest()
_CONFIGURATION_IDENTITY: Final = hashlib.sha256(
    b"archive-bound-local-mapping-conflict-retry-integrity@v2\n"
).hexdigest()


def _wire(value: object) -> object:
    if type(value) is datetime:
        return (
            value.astimezone(UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if type(value) is date:
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _wire(getattr(value, item.name))
            for item in fields(value)
            if not item.name.startswith("_")
        }
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
        json.dumps(
            _wire(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _valid_digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _instant(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(None)
    ):
        raise ValueError("invalid current event V2 timestamp")
    return value.astimezone(UTC)


def current_event_notice_runtime_code_identity_v2() -> str:
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in CURRENT_EVENT_NOTICE_RUNTIME_SOURCE_SHA256_V2.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("current event V2 runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


@dataclass(frozen=True, slots=True)
class CurrentEventAcquisitionAttemptV2:
    attempt_number: int
    attempted_at: datetime
    outcome: Literal["FAILED", "RETAINED"]
    failure_code: str | None
    artifact_identity_sha256: str | None
    snapshot_identity_sha256: str | None

    def __post_init__(self) -> None:
        attempted = _instant(self.attempted_at)
        if (
            type(self.attempt_number) is not int
            or not 1 <= self.attempt_number <= 10
            or self.outcome not in {"FAILED", "RETAINED"}
            or (
                self.outcome == "FAILED"
                and (
                    type(self.failure_code) is not str
                    or not self.failure_code
                    or self.artifact_identity_sha256 is not None
                    or self.snapshot_identity_sha256 is not None
                )
            )
            or (
                self.outcome == "RETAINED"
                and (
                    self.failure_code is not None
                    or not _valid_digest(self.artifact_identity_sha256)
                    or not _valid_digest(self.snapshot_identity_sha256)
                )
            )
        ):
            raise ValueError("invalid current event acquisition attempt")
        object.__setattr__(self, "attempted_at", attempted)


@dataclass(frozen=True, slots=True)
class CurrentEventNoticeSummaryV2:
    """Body-free event fact safe for the integrated research envelope."""

    broadcast_at: str
    receipt_at: str
    dissemination_at: str
    observation_identity_sha256: str
    deduplication_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            any(
                type(value) is not str or not 1 <= len(value.encode()) <= 4_096
                for value in (
                    self.broadcast_at,
                    self.receipt_at,
                    self.dissemination_at,
                )
            )
            or not _valid_digest(self.observation_identity_sha256)
            or not _valid_digest(self.deduplication_identity_sha256)
        ):
            raise ValueError("invalid current event notice summary")


@dataclass(frozen=True, slots=True)
class CurrentEventMemberProjectionV2:
    mapping: CurrentResearchMappingMemberV2
    availability: Literal[
        "NOTICES_ADMITTED", "NO_MATCHING_NOTICE_IN_SNAPSHOT", "NOT_ESTABLISHED"
    ]
    support: Literal["SUPPORTED", "CONFLICTED", "NOT_ESTABLISHED"]
    reason: str | None
    notices: tuple[CurrentEventNoticeSummaryV2, ...]
    event_source_member_identity_sha256: str | None

    def __post_init__(self) -> None:
        if (
            type(self.mapping) is not CurrentResearchMappingMemberV2
            or self.availability
            not in {
                "NOTICES_ADMITTED",
                "NO_MATCHING_NOTICE_IN_SNAPSHOT",
                "NOT_ESTABLISHED",
            }
            or self.support not in {"SUPPORTED", "CONFLICTED", "NOT_ESTABLISHED"}
            or type(self.notices) is not tuple
            or any(
                type(item) is not CurrentEventNoticeSummaryV2 for item in self.notices
            )
            or (self.availability == "NOTICES_ADMITTED") != bool(self.notices)
            or (
                self.availability
                in {
                    "NOTICES_ADMITTED",
                    "NO_MATCHING_NOTICE_IN_SNAPSHOT",
                }
                and (
                    self.support != "SUPPORTED"
                    or self.reason is not None
                    or not _valid_digest(self.event_source_member_identity_sha256)
                )
            )
            or (
                self.availability == "NOT_ESTABLISHED"
                and (
                    self.support not in {"CONFLICTED", "NOT_ESTABLISHED"}
                    or type(self.reason) is not str
                    or not self.reason
                    or self.event_source_member_identity_sha256 is not None
                    or self.notices
                )
            )
        ):
            raise ValueError("invalid current event member projection")


@dataclass(frozen=True, slots=True, init=False, repr=False, weakref_slot=True)
class RetainedCurrentEventNoticeProjectionV2:
    contract_version: Literal["current-event-notice@v2"]
    schema_identity_sha256: str
    configuration_identity_sha256: str
    runtime_code_identity_sha256: str
    mapping_projection: CurrentResearchMappingProjectionV2
    source_contract_version: str
    source_schema_identity_sha256: str
    source_runtime_code_identity_sha256: str
    source_url: str
    source_segment: str
    source_window: str
    source_filename: str
    source_encoding: Literal["UTF-8"]
    source_has_bom: bool
    acquisition_method: Literal["BOUNDED_OFFICIAL_FETCH", "OPERATOR_ACQUIRED"]
    licence_policy_identity: str
    artifact_identity_sha256: str
    snapshot_identity_sha256: str
    archive_identity_sha256: str
    receipt_identity_sha256: str
    retained_identity_sha256: str
    known_at: datetime
    decision_cutoff: datetime
    attempts: tuple[CurrentEventAcquisitionAttemptV2, ...]
    members: tuple[CurrentEventMemberProjectionV2, ...]
    result_identity_sha256: str
    _seal: object = field(repr=False, compare=False, hash=False)

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("current event V2 projections are producer-minted only")

    def canonical_json_bytes(self) -> bytes:
        return _canonical(self)


_RETAINED: dict[
    int,
    tuple[weakref.ReferenceType[RetainedCurrentEventNoticeProjectionV2], bytes, object],
] = {}


def _admit(value: RetainedCurrentEventNoticeProjectionV2) -> None:
    value_id = id(value)
    seal = object.__getattribute__(value, "_seal")

    def discard(
        reference: weakref.ReferenceType[RetainedCurrentEventNoticeProjectionV2],
    ) -> None:
        entry = _RETAINED.get(value_id)
        if entry is not None and entry[0] is reference:
            _RETAINED.pop(value_id, None)

    _RETAINED[value_id] = (
        weakref.ref(value, discard),
        value.canonical_json_bytes(),
        seal,
    )


def current_event_notice_semantics_are_valid_v2(value: object) -> bool:
    """Validate redacted Event semantics without asserting archive admission."""
    if type(value) is not RetainedCurrentEventNoticeProjectionV2:
        return False
    try:
        value.mapping_projection.__post_init__()
        for attempt in value.attempts:
            attempt.__post_init__()
        for member in value.members:
            member.__post_init__()
        return _validate_projection(value)
    except (TypeError, ValueError):
        return False


def validate_retained_current_event_notice_v2(
    value: object,
) -> RetainedCurrentEventNoticeProjectionV2:
    if type(value) is not RetainedCurrentEventNoticeProjectionV2:
        raise ValueError("current event V2 projection is not admitted")
    entry = _RETAINED.get(id(value))
    if (
        entry is None
        or entry[0]() is not value
        or entry[1] != value.canonical_json_bytes()
        or entry[2] is not object.__getattribute__(value, "_seal")
        or not current_event_notice_semantics_are_valid_v2(value)
    ):
        raise ValueError("current event V2 projection is not admitted")
    return value


def _validate_attempts(
    attempts: tuple[CurrentEventAcquisitionAttemptV2, ...],
    retained: RetainedCurrentEventNoticeSnapshotV1,
    cutoff: datetime,
) -> bool:
    return (
        type(attempts) is tuple
        and 1 <= len(attempts) <= 10
        and all(type(item) is CurrentEventAcquisitionAttemptV2 for item in attempts)
        and tuple(item.attempt_number for item in attempts)
        == tuple(range(1, len(attempts) + 1))
        and tuple(item.attempted_at for item in attempts)
        == tuple(sorted(item.attempted_at for item in attempts))
        and all(item.attempted_at <= cutoff for item in attempts)
        and all(item.outcome == "FAILED" for item in attempts[:-1])
        and attempts[-1].outcome == "RETAINED"
        and attempts[-1].artifact_identity_sha256 == retained.artifact_identity_sha256
        and attempts[-1].snapshot_identity_sha256 == retained.snapshot_identity_sha256
    )


def _validate_projection(value: RetainedCurrentEventNoticeProjectionV2) -> bool:
    try:
        mapping = value.mapping_projection
        known = _instant(value.known_at)
        cutoff = _instant(value.decision_cutoff)
    except ValueError:
        return False
    if (
        value.contract_version != _CONTRACT
        or value.schema_identity_sha256 != _SCHEMA_IDENTITY
        or value.configuration_identity_sha256 != _CONFIGURATION_IDENTITY
        or value.runtime_code_identity_sha256
        != current_event_notice_runtime_code_identity_v2()
        or known > cutoff
        or cutoff != mapping.decision_cutoff
        or any(
            not _valid_digest(item)
            for item in (
                value.source_schema_identity_sha256,
                value.source_runtime_code_identity_sha256,
                value.artifact_identity_sha256,
                value.snapshot_identity_sha256,
                value.archive_identity_sha256,
                value.receipt_identity_sha256,
                value.retained_identity_sha256,
            )
        )
        or type(value.source_contract_version) is not str
        or not value.source_contract_version
        or type(value.source_url) is not str
        or not value.source_url.startswith("https://")
        or type(value.licence_policy_identity) is not str
        or not value.licence_policy_identity
        or tuple(item.mapping for item in value.members) != mapping.members
        or type(value.attempts) is not tuple
        or not 1 <= len(value.attempts) <= 10
        or tuple(item.attempt_number for item in value.attempts)
        != tuple(range(1, len(value.attempts) + 1))
        or tuple(item.attempted_at for item in value.attempts)
        != tuple(sorted(item.attempted_at for item in value.attempts))
        or any(item.attempted_at > cutoff for item in value.attempts)
        or any(item.outcome != "FAILED" for item in value.attempts[:-1])
        or value.attempts[-1].outcome != "RETAINED"
        or value.attempts[-1].artifact_identity_sha256 != value.artifact_identity_sha256
        or value.attempts[-1].snapshot_identity_sha256 != value.snapshot_identity_sha256
    ):
        return False
    preimage = {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if item.name not in {"result_identity_sha256", "_seal"}
    }
    return value.result_identity_sha256 == _digest(preimage)


def _source_member_identity(item: CurrentEventNoticeMemberResultV1) -> str:
    return _digest(item.value()["member"])


def _notice_summary(item: CurrentEventNoticeV1) -> CurrentEventNoticeSummaryV2:
    return CurrentEventNoticeSummaryV2(
        item.broadcast_at,
        item.receipt_at,
        item.dissemination_at,
        item.observation_identity_sha256,
        item.deduplication_identity_sha256,
    )


def _member_projection(
    mapping: CurrentResearchMappingMemberV2,
    by_isin: dict[str, CurrentEventNoticeMemberResultV1],
) -> CurrentEventMemberProjectionV2:
    source = by_isin.get(mapping.isin)
    if source is None:
        return CurrentEventMemberProjectionV2(
            mapping,
            "NOT_ESTABLISHED",
            "NOT_ESTABLISHED",
            "EVENT_MEMBER_NOT_IN_RETAINED_SNAPSHOT",
            (),
            None,
        )
    member = source.member
    if (
        member.exchange != mapping.exchange
        or member.symbol != mapping.effective_symbol
        or member.effective_from != mapping.valid_from
        or member.effective_through != mapping.valid_through
        or member.provider_mapping_revision != mapping.provider_mapping_revision
    ):
        return CurrentEventMemberProjectionV2(
            mapping,
            "NOT_ESTABLISHED",
            "CONFLICTED",
            "EVENT_MAPPING_CONFLICT",
            (),
            None,
        )
    return CurrentEventMemberProjectionV2(
        mapping,
        source.outcome,
        "SUPPORTED",
        None,
        tuple(_notice_summary(item) for item in source.notices),
        _source_member_identity(source),
    )


def project_retained_current_event_notices_v2(
    root: Path,
    lease: StorageRootLease,
    retained: RetainedCurrentEventNoticeSnapshotV1,
    mapping_binding: AdmittedCurrentResearchBindingV2,
    attempts: tuple[CurrentEventAcquisitionAttemptV2, ...],
) -> RetainedCurrentEventNoticeProjectionV2:
    """Revalidate archive bytes, then project mapping conflicts per member."""
    if not root.is_absolute() or type(lease) is not StorageRootLease:
        raise ValueError("current event V2 archive input invalid")
    retained = validate_retained_current_event_notice_v1(root, lease, retained)
    mapping = validate_current_research_binding_v2(mapping_binding)
    cutoff = mapping.decision_cutoff
    if not _validate_attempts(attempts, retained, cutoff):
        raise ValueError("current event V2 retry integrity invalid")
    source_date = _parse_filename(retained.source_filename)
    if (
        retained.known_at > cutoff
        or source_date is None
        or source_date != retained.known_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
    ):
        raise ValueError("current event V2 source-time integrity invalid")
    runtime = current_event_notice_runtime_code_identity_v2()
    by_isin = {item.member.isin: item for item in retained.members}
    members = tuple(_member_projection(item, by_isin) for item in mapping.members)
    preimage = {
        "contract_version": _CONTRACT,
        "schema_identity_sha256": _SCHEMA_IDENTITY,
        "configuration_identity_sha256": _CONFIGURATION_IDENTITY,
        "runtime_code_identity_sha256": runtime,
        "mapping_projection": mapping,
        "source_contract_version": retained.contract_version,
        "source_schema_identity_sha256": retained.schema_identity_sha256,
        "source_runtime_code_identity_sha256": retained.runtime_code_identity_sha256,
        "source_url": retained.source_url,
        "source_segment": retained.source_segment,
        "source_window": retained.source_window,
        "source_filename": retained.source_filename,
        "source_encoding": retained.source_encoding,
        "source_has_bom": retained.source_has_bom,
        "acquisition_method": retained.acquisition_method,
        "licence_policy_identity": retained.licence_policy_identity,
        "artifact_identity_sha256": retained.artifact_identity_sha256,
        "snapshot_identity_sha256": retained.snapshot_identity_sha256,
        "archive_identity_sha256": retained.archive_identity_sha256,
        "receipt_identity_sha256": retained.receipt_identity_sha256,
        "retained_identity_sha256": retained.retained_identity_sha256,
        "known_at": retained.known_at,
        "decision_cutoff": cutoff,
        "attempts": attempts,
        "members": members,
    }
    value = object.__new__(RetainedCurrentEventNoticeProjectionV2)
    for name, item in {
        **preimage,
        "result_identity_sha256": _digest(preimage),
        "_seal": object(),
    }.items():
        object.__setattr__(value, name, item)
    if not _validate_projection(value):
        raise ValueError("current event V2 projection invalid")
    _admit(value)
    return value


def retain_current_event_notices_v2(  # noqa: C901 - explicit logical commit
    root: Path,
    lease: StorageRootLease,
    event_input: CurrentEventNoticeInputV1,
    artifact: bytes,
    mapping_binding: AdmittedCurrentResearchBindingV2,
    prior_failed_attempts: tuple[CurrentEventAcquisitionAttemptV2, ...] = (),
) -> RetainedCurrentEventNoticeProjectionV2:
    """Retain bounded member-local outcomes in the Event V2 namespace."""
    if (
        not root.is_absolute()
        or type(lease) is not StorageRootLease
        or type(event_input) is not CurrentEventNoticeInputV1
        or type(artifact) is not bytes
        or len(artifact) > 1024 * 1024
        or type(prior_failed_attempts) is not tuple
        or len(prior_failed_attempts) > 9
        or any(
            type(item) is not CurrentEventAcquisitionAttemptV2
            or item.outcome != "FAILED"
            for item in prior_failed_attempts
        )
    ):
        raise ValueError("current event V2 retention input invalid")
    mapping = validate_current_research_binding_v2(mapping_binding)
    parsed = parse_current_event_notice_artifact_v1(event_input, artifact)
    if isinstance(parsed, CurrentEventNoticeFailureV1):
        raise ValueError(",".join(parsed.reasons))
    if len(parsed.private_rows) > 2_000:
        raise ValueError("current event V2 aggregate bounds")
    for row in parsed.private_rows:
        for value in (
            row.symbol,
            row.company_name,
            row.subject,
            row.details,
            row.broadcast_at,
            row.receipt_at,
            row.dissemination_at,
            row.difference,
            row.attachment_url,
        ):
            if type(value) is not str or len(value.encode()) > 4_096:
                raise ValueError("current event V2 string bounds")
    if len(parsed.private_rows) * 24 + len(mapping.members) * 16 > 50_000:
        raise ValueError("current event V2 node bounds")
    runtime = current_event_notice_runtime_code_identity_v2()
    source_runtime = current_event_notice_runtime_code_identity_v1()
    known_at = _instant(_trusted_utc_now())
    source_date = _parse_filename(event_input.source_filename)
    if (
        source_date is None
        or source_date != known_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
        or known_at > mapping.decision_cutoff
    ):
        raise ValueError("current event V2 source-time integrity invalid")
    local_members: list[CurrentEventMemberProjectionV2] = []
    for member in mapping.members:
        failure = _relevant_row_failure(
            parsed.private_rows, frozenset({member.effective_symbol})
        )
        if failure is not None:
            local_members.append(
                CurrentEventMemberProjectionV2(
                    member,
                    "NOT_ESTABLISHED",
                    "CONFLICTED",
                    failure,
                    (),
                    None,
                )
            )
            continue
        source_result = _member_result(
            CurrentEventCohortMemberV1(
                member.isin,
                member.exchange,
                "NSE_EQ",
                member.effective_symbol,
                member.valid_from,
                member.valid_through,
                member.provider_mapping_revision,
            ),
            parsed.private_rows,
        )
        local_members.append(
            CurrentEventMemberProjectionV2(
                member,
                source_result.outcome,
                "SUPPORTED",
                None,
                tuple(_notice_summary(item) for item in source_result.notices),
                _source_member_identity(source_result),
            )
        )
    members = tuple(local_members)
    projection_core = {
        "contract_version": _CONTRACT,
        "schema_identity_sha256": _SCHEMA_IDENTITY,
        "configuration_identity_sha256": _CONFIGURATION_IDENTITY,
        "runtime_code_identity_sha256": runtime,
        "mapping_projection": mapping,
        "source_contract_version": "current-event-notice@v1",
        "source_schema_identity_sha256": event_input.schema_identity_sha256,
        "source_runtime_code_identity_sha256": source_runtime,
        "source_url": event_input.source_url,
        "source_segment": event_input.source_segment,
        "source_window": event_input.source_window,
        "source_filename": event_input.source_filename,
        "source_encoding": event_input.source_encoding,
        "source_has_bom": event_input.source_has_bom,
        "acquisition_method": event_input.acquisition_method,
        "licence_policy_identity": event_input.licence_policy_identity,
        "artifact_identity_sha256": event_input.artifact_identity_sha256,
        "known_at": known_at,
        "decision_cutoff": mapping.decision_cutoff,
        "members": members,
    }
    projection_raw = _canonical(projection_core)
    snapshot_identity = hashlib.sha256(projection_raw).hexdigest()
    archive_identity = _digest(
        {
            "protocol": "current-event-notice-v2-archive@v1",
            "artifact_identity_sha256": event_input.artifact_identity_sha256,
            "snapshot_identity_sha256": snapshot_identity,
        }
    )
    receipt_core = {
        "protocol": "current-event-notice-v2-receipt@v1",
        "archive_identity_sha256": archive_identity,
        "artifact_identity_sha256": event_input.artifact_identity_sha256,
        "snapshot_identity_sha256": snapshot_identity,
        "runtime_code_identity_sha256": runtime,
        "known_at": known_at,
    }
    receipt_identity = _digest(receipt_core)
    retained_identity = _digest(
        {
            **receipt_core,
            "receipt_identity_sha256": receipt_identity,
            "mapping_projection_identity_sha256": (
                mapping.mapping_projection_identity_sha256
            ),
        }
    )
    receipt_raw = _canonical(
        {
            **receipt_core,
            "receipt_identity_sha256": receipt_identity,
            "retained_identity_sha256": retained_identity,
        }
    )
    marker_raw = _canonical(
        {
            "protocol": "current-event-notice-v2-complete@v1",
            "archive_identity_sha256": archive_identity,
            "receipt_identity_sha256": receipt_identity,
            "retained_identity_sha256": retained_identity,
        }
    )
    names_and_values = (
        (f"v2-{event_input.artifact_identity_sha256}.raw.csv", artifact, 1024 * 1024),
        (f"v2-{snapshot_identity}.projection.json", projection_raw, 1024 * 1024),
        (f"v2-{archive_identity}.receipt.json", receipt_raw, 64 * 1024),
        (f"v2-{archive_identity}.complete.json", marker_raw, 64 * 1024),
    )
    with lease.root_operation(root) as operation:
        directory = _open_archive(operation.descriptor)
        try:
            for name, expected, maximum in names_and_values:
                existing = _read_stable_private_object(directory, name, maximum)
                if existing is None:
                    _publish_object(directory, name, expected, maximum)
                elif existing[0] != expected:
                    raise ValueError("current event V2 immutable archive conflict")
            for name, expected, maximum in names_and_values:
                observed = _read_stable_private_object(directory, name, maximum)
                if observed is None or observed[0] != expected:
                    raise ValueError("current event V2 stable readback invalid")
            os.fsync(directory)
        finally:
            os.close(directory)
    attempts = prior_failed_attempts + (
        CurrentEventAcquisitionAttemptV2(
            len(prior_failed_attempts) + 1,
            known_at,
            "RETAINED",
            None,
            event_input.artifact_identity_sha256,
            snapshot_identity,
        ),
    )
    preimage = {
        **projection_core,
        "snapshot_identity_sha256": snapshot_identity,
        "archive_identity_sha256": archive_identity,
        "receipt_identity_sha256": receipt_identity,
        "retained_identity_sha256": retained_identity,
        "attempts": attempts,
    }
    value = object.__new__(RetainedCurrentEventNoticeProjectionV2)
    for name, item in {
        **preimage,
        "result_identity_sha256": _digest(preimage),
        "_seal": object(),
    }.items():
        object.__setattr__(value, name, item)
    if not _validate_projection(value):
        raise ValueError("current event V2 retained projection invalid")
    _admit(value)
    return value


__all__ = [
    "CurrentEventAcquisitionAttemptV2",
    "CurrentEventMemberProjectionV2",
    "RetainedCurrentEventNoticeProjectionV2",
    "current_event_notice_runtime_code_identity_v2",
    "current_event_notice_semantics_are_valid_v2",
    "project_retained_current_event_notices_v2",
    "retain_current_event_notices_v2",
    "validate_retained_current_event_notice_v2",
]
