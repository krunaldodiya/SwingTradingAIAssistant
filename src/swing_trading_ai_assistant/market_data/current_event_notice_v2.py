"""Archive-bound, member-local current event evidence for Issue #187."""

from __future__ import annotations

import hashlib
import json
import os
import weakref
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final, Literal, cast
from zoneinfo import ZoneInfo

from .current_event_notice import (
    _ARCHIVE_LOCK,  # pyright: ignore[reportPrivateUsage]
    CurrentEventCohortMemberV1,
    CurrentEventNoticeFailureV1,
    CurrentEventNoticeInputV1,
    CurrentEventNoticeMemberResultV1,
    CurrentEventNoticeV1,
    RetainedCurrentEventNoticeSnapshotV1,
    _event_datetime,  # pyright: ignore[reportPrivateUsage]
    _input_failure,  # pyright: ignore[reportPrivateUsage]
    _member_result,  # pyright: ignore[reportPrivateUsage]
    _open_archive,  # pyright: ignore[reportPrivateUsage]
    _parse_filename,  # pyright: ignore[reportPrivateUsage]
    _parse_filename_range,  # pyright: ignore[reportPrivateUsage]
    _publish_object,  # pyright: ignore[reportPrivateUsage]
    _read_stable_private_object,  # pyright: ignore[reportPrivateUsage]
    _receipt_datetime,  # pyright: ignore[reportPrivateUsage]
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
    b"current-event-notice-schema@v3\n"
).hexdigest()
_CONFIGURATION_IDENTITY: Final = hashlib.sha256(
    b"archive-bound-local-mapping-producer-attempt-logical-commit@v3\n"
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


@dataclass(frozen=True, slots=True, init=False)
class CurrentEventAcquisitionAttemptV2:
    """A producer-minted terminal retention attempt, never caller history."""

    attempt_number: int
    attempted_at: datetime
    outcome: Literal["RETAINED"]
    failure_code: None
    artifact_identity_sha256: str

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("current event attempts are producer-minted only")

    def __post_init__(self) -> None:
        attempted = _instant(self.attempted_at)
        if (
            self.attempt_number != 1
            or self.outcome != "RETAINED"
            or self.failure_code is not None
            or not _valid_digest(self.artifact_identity_sha256)
        ):
            raise ValueError("invalid current event acquisition attempt")
        object.__setattr__(self, "attempted_at", attempted)


def _retained_attempt(
    known_at: datetime, artifact_identity_sha256: str
) -> CurrentEventAcquisitionAttemptV2:
    result = object.__new__(CurrentEventAcquisitionAttemptV2)
    object.__setattr__(result, "attempt_number", 1)
    object.__setattr__(result, "attempted_at", _instant(known_at))
    object.__setattr__(result, "outcome", "RETAINED")
    object.__setattr__(result, "failure_code", None)
    object.__setattr__(result, "artifact_identity_sha256", artifact_identity_sha256)
    result.__post_init__()
    return result


def _attempt_history_identity(
    attempts: tuple[CurrentEventAcquisitionAttemptV2, ...],
) -> str:
    return _digest(
        {"protocol": "current-event-notice-v2-attempt-history@v1", "attempts": attempts}
    )


def _v2_archive_identity(projection: Mapping[str, object]) -> str:
    mapping = cast(CurrentResearchMappingProjectionV2, projection["mapping_projection"])
    return _digest(
        {
            "protocol": "current-event-notice-v2-archive@v3",
            "contract_version": projection["contract_version"],
            "schema_identity_sha256": projection["schema_identity_sha256"],
            "configuration_identity_sha256": projection[
                "configuration_identity_sha256"
            ],
            "runtime_code_identity_sha256": projection["runtime_code_identity_sha256"],
            "retention_origin": projection["retention_origin"],
            "artifact_identity_sha256": projection["artifact_identity_sha256"],
            "mapping_projection_identity_sha256": (
                mapping.mapping_projection_identity_sha256
            ),
            "decision_cutoff": projection["decision_cutoff"],
            "members": projection["members"],
            "source_contract_version": projection["source_contract_version"],
            "source_schema_identity_sha256": projection[
                "source_schema_identity_sha256"
            ],
            "source_runtime_code_identity_sha256": projection[
                "source_runtime_code_identity_sha256"
            ],
            "source_url": projection["source_url"],
            "source_segment": projection["source_segment"],
            "source_window": projection["source_window"],
            "source_filename": projection["source_filename"],
            "source_encoding": projection["source_encoding"],
            "source_has_bom": projection["source_has_bom"],
            "acquisition_method": projection["acquisition_method"],
            "licence_policy_identity": projection["licence_policy_identity"],
        }
    )


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
            or _event_datetime(self.broadcast_at) is None
            or _receipt_datetime(self.receipt_at) is None
            or _event_datetime(self.dissemination_at) is None
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
    retention_origin: Literal["ADOPTED_EVENT_V1", "RETAINED_EVENT_V2"]
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
    attempt_history_identity_sha256: str
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
            member.mapping.__post_init__()
            for notice in member.notices:
                notice.__post_init__()
            member.__post_init__()
        return _validate_projection(value)
    except (TypeError, ValueError):
        return False


def validate_retained_current_event_notice_v2(
    value: object,
) -> RetainedCurrentEventNoticeProjectionV2:
    if type(value) is not RetainedCurrentEventNoticeProjectionV2:
        raise ValueError("current event V2 projection is not admitted")
    if not current_event_notice_semantics_are_valid_v2(value):
        raise ValueError("current event V2 projection is not admitted")
    entry = _RETAINED.get(id(value))
    if (
        entry is None
        or entry[0]() is not value
        or entry[1] != value.canonical_json_bytes()
        or entry[2] is not object.__getattribute__(value, "_seal")
    ):
        raise ValueError("current event V2 projection is not admitted")
    return value


def _validate_attempts(
    attempts: object,
    artifact_identity_sha256: str,
    known_at: datetime,
    cutoff: datetime,
) -> bool:
    if type(attempts) is not tuple:
        return False
    values = cast(tuple[object, ...], attempts)
    return (
        len(values) == 1
        and type(values[0]) is CurrentEventAcquisitionAttemptV2
        and values[0].attempted_at == known_at
        and values[0].attempted_at <= cutoff
        and values[0].artifact_identity_sha256 == artifact_identity_sha256
        and values[0] == _retained_attempt(known_at, artifact_identity_sha256)
    )


def _validate_projection(  # noqa: C901 - exact source/archive equations
    value: RetainedCurrentEventNoticeProjectionV2,
) -> bool:
    try:
        mapping = value.mapping_projection
        known = _instant(value.known_at)
        cutoff = _instant(value.decision_cutoff)
        source_input = CurrentEventNoticeInputV1(
            schema_identity_sha256=value.source_schema_identity_sha256,
            source_url=value.source_url,
            source_segment=value.source_segment,
            source_window=value.source_window,
            source_filename=value.source_filename,
            artifact_identity_sha256=value.artifact_identity_sha256,
            acquisition_method=value.acquisition_method,
            licence_policy_identity=value.licence_policy_identity,
            source_encoding=value.source_encoding,
            source_has_bom=value.source_has_bom,
        )
    except (TypeError, ValueError):
        return False
    source_range = _parse_filename_range(value.source_filename)
    expected_source_members = tuple(
        _digest(
            {
                "isin": member.mapping.isin,
                "exchange": member.mapping.exchange,
                "listed_equity_segment": "NSE_EQ",
                "symbol": member.mapping.effective_symbol,
                "effective_from": member.mapping.valid_from,
                "effective_through": member.mapping.valid_through,
                "provider_mapping_revision": member.mapping.provider_mapping_revision,
            }
        )
        if member.availability != "NOT_ESTABLISHED"
        else None
        for member in value.members
    )
    notices = tuple(notice for member in value.members for notice in member.notices)
    notice_dates_valid = source_range is not None and all(
        source_range[0] <= cast(datetime, parser(text)).date() <= source_range[1]
        for notice in notices
        for text, parser in (
            (notice.broadcast_at, _event_datetime),
            (notice.receipt_at, _receipt_datetime),
            (notice.dissemination_at, _event_datetime),
        )
    )
    if (
        value.contract_version != _CONTRACT
        or value.schema_identity_sha256 != _SCHEMA_IDENTITY
        or value.configuration_identity_sha256 != _CONFIGURATION_IDENTITY
        or value.runtime_code_identity_sha256
        != current_event_notice_runtime_code_identity_v2()
        or value.retention_origin not in {"ADOPTED_EVENT_V1", "RETAINED_EVENT_V2"}
        or known > cutoff
        or cutoff != mapping.decision_cutoff
        or source_range is None
        or source_range[1] != known.astimezone(ZoneInfo("Asia/Kolkata")).date()
        or not notice_dates_valid
        or len({item.observation_identity_sha256 for item in notices}) != len(notices)
        or len({item.deduplication_identity_sha256 for item in notices}) != len(notices)
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
        or value.source_contract_version != "current-event-notice@v1"
        or value.source_runtime_code_identity_sha256
        != current_event_notice_runtime_code_identity_v1()
        or _input_failure(source_input) is not None
        or tuple(item.event_source_member_identity_sha256 for item in value.members)
        != expected_source_members
        or tuple(item.mapping for item in value.members) != mapping.members
        or any(
            item.reason
            not in {
                None,
                "EVENT_MEMBER_NOT_IN_RETAINED_SNAPSHOT",
                "EVENT_MAPPING_CONFLICT",
                "CORRECTION_LINEAGE_UNAVAILABLE",
                "EVENT_DUPLICATE",
                "EVENT_CONFLICTED",
            }
            for item in value.members
        )
        or not _validate_attempts(
            value.attempts, value.artifact_identity_sha256, known, cutoff
        )
        or not _valid_digest(value.attempt_history_identity_sha256)
        or value.attempt_history_identity_sha256
        != _attempt_history_identity(value.attempts)
    ):
        return False
    projection_core = {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if item.name
        not in {
            "snapshot_identity_sha256",
            "archive_identity_sha256",
            "receipt_identity_sha256",
            "retained_identity_sha256",
            "result_identity_sha256",
            "_seal",
        }
    }
    if value.retention_origin == "RETAINED_EVENT_V2":
        snapshot_identity = hashlib.sha256(_canonical(projection_core)).hexdigest()
        archive_identity = _v2_archive_identity(projection_core)
        receipt_core = {
            "protocol": "current-event-notice-v2-receipt@v2",
            "archive_identity_sha256": archive_identity,
            "artifact_identity_sha256": value.artifact_identity_sha256,
            "snapshot_identity_sha256": snapshot_identity,
            "runtime_code_identity_sha256": value.runtime_code_identity_sha256,
            "known_at": known,
            "attempt_history_identity_sha256": (value.attempt_history_identity_sha256),
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
        if (
            value.snapshot_identity_sha256 != snapshot_identity
            or value.archive_identity_sha256 != archive_identity
            or value.receipt_identity_sha256 != receipt_identity
            or value.retained_identity_sha256 != retained_identity
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
) -> RetainedCurrentEventNoticeProjectionV2:
    """Revalidate archive bytes, then project mapping conflicts per member."""
    if not root.is_absolute() or type(lease) is not StorageRootLease:
        raise ValueError("current event V2 archive input invalid")
    retained = validate_retained_current_event_notice_v1(root, lease, retained)
    mapping = validate_current_research_binding_v2(mapping_binding)
    cutoff = mapping.decision_cutoff
    attempts = (
        _retained_attempt(retained.known_at, retained.artifact_identity_sha256),
    )
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
        "retention_origin": "ADOPTED_EVENT_V1",
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
        "attempt_history_identity_sha256": _attempt_history_identity(attempts),
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
) -> RetainedCurrentEventNoticeProjectionV2:
    """Retain bounded member-local outcomes in the Event V2 namespace."""
    if (
        not root.is_absolute()
        or type(lease) is not StorageRootLease
        or type(event_input) is not CurrentEventNoticeInputV1
        or type(artifact) is not bytes
        or len(artifact) > 1024 * 1024
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
    ):
        raise ValueError("current event V2 source-time integrity invalid")
    attempts = (_retained_attempt(known_at, event_input.artifact_identity_sha256),)
    attempt_history_identity = _attempt_history_identity(attempts)
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
        "retention_origin": "RETAINED_EVENT_V2",
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
        "attempts": attempts,
        "attempt_history_identity_sha256": attempt_history_identity,
        "members": members,
    }
    projection_raw = _canonical(projection_core)
    snapshot_identity = hashlib.sha256(projection_raw).hexdigest()
    # The logical commit key deliberately excludes retention time and snapshot
    # bytes.  A retry must discover the same durable commit before sampling a
    # new clock value.
    archive_identity = _v2_archive_identity(projection_core)
    receipt_core = {
        "protocol": "current-event-notice-v2-receipt@v2",
        "archive_identity_sha256": archive_identity,
        "artifact_identity_sha256": event_input.artifact_identity_sha256,
        "snapshot_identity_sha256": snapshot_identity,
        "runtime_code_identity_sha256": runtime,
        "known_at": known_at,
        "attempt_history_identity_sha256": attempt_history_identity,
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
            "protocol": "current-event-notice-v2-complete@v3",
            "archive_identity_sha256": archive_identity,
            "receipt_identity_sha256": receipt_identity,
            "retained_identity_sha256": retained_identity,
            "attempt_history_identity_sha256": attempt_history_identity,
        }
    )
    names_and_values = (
        (f"v2-{event_input.artifact_identity_sha256}.raw.csv", artifact, 1024 * 1024),
        (f"v2-{archive_identity}.projection.json", projection_raw, 1024 * 1024),
        (f"v2-{archive_identity}.receipt.json", receipt_raw, 64 * 1024),
        (f"v2-{archive_identity}.complete.json", marker_raw, 64 * 1024),
    )
    # V1 and V2 share deterministic pending names in the private archive.
    # Hold the archive owner lock across discovery, publication and readback.
    with _ARCHIVE_LOCK, lease.root_operation(root) as operation:
        directory = _open_archive(operation.descriptor)
        try:
            existing_objects = tuple(
                _read_stable_private_object(directory, name, maximum)
                for name, _, maximum in names_and_values
            )
            presence = tuple(item is not None for item in existing_objects)
            if presence not in {
                (False, False, False, False),
                (True, False, False, False),
                (True, True, False, False),
                (True, True, True, False),
                (True, True, True, True),
            }:
                raise ValueError("current event V2 immutable archive conflict")
            stored = existing_objects[1]
            if stored is None and known_at > mapping.decision_cutoff:
                raise ValueError("current event retention exceeded decision cutoff")
            if stored is not None:
                try:
                    stored_core = json.loads(stored[0])
                    stored_known = datetime.fromisoformat(
                        stored_core["known_at"].replace("Z", "+00:00")
                    )
                except (KeyError, TypeError, ValueError):
                    raise ValueError(
                        "current event V2 immutable archive conflict"
                    ) from None
                known_at = _instant(stored_known)
                attempts = (
                    _retained_attempt(known_at, event_input.artifact_identity_sha256),
                )
                attempt_history_identity = _attempt_history_identity(attempts)
                projection_core["known_at"] = known_at
                projection_core["attempts"] = attempts
                projection_core["attempt_history_identity_sha256"] = (
                    attempt_history_identity
                )
                projection_raw = _canonical(projection_core)
                snapshot_identity = hashlib.sha256(projection_raw).hexdigest()
                receipt_core["snapshot_identity_sha256"] = snapshot_identity
                receipt_core["known_at"] = known_at
                receipt_core["attempt_history_identity_sha256"] = (
                    attempt_history_identity
                )
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
                        "protocol": "current-event-notice-v2-complete@v3",
                        "archive_identity_sha256": archive_identity,
                        "receipt_identity_sha256": receipt_identity,
                        "retained_identity_sha256": retained_identity,
                        "attempt_history_identity_sha256": attempt_history_identity,
                    }
                )
                names_and_values = (
                    (
                        f"v2-{event_input.artifact_identity_sha256}.raw.csv",
                        artifact,
                        1024 * 1024,
                    ),
                    (
                        f"v2-{archive_identity}.projection.json",
                        projection_raw,
                        1024 * 1024,
                    ),
                    (f"v2-{archive_identity}.receipt.json", receipt_raw, 64 * 1024),
                    (f"v2-{archive_identity}.complete.json", marker_raw, 64 * 1024),
                )
            # Validate the complete observed prefix before publishing its next
            # object. A corrupt receipt or marker must never cause repair of an
            # earlier missing/conflicting object.
            for existing, (_, expected, _) in zip(
                existing_objects, names_and_values, strict=True
            ):
                if existing is not None and existing[0] != expected:
                    raise ValueError("current event V2 immutable archive conflict")
            for existing, (name, expected, maximum) in zip(
                existing_objects, names_and_values, strict=True
            ):
                if existing is None:
                    _publish_object(directory, name, expected, maximum)
            for name, expected, maximum in names_and_values:
                observed = _read_stable_private_object(directory, name, maximum)
                if observed is None or observed[0] != expected:
                    raise ValueError("current event V2 stable readback invalid")
            os.fsync(directory)
        finally:
            os.close(directory)
    attempts = (_retained_attempt(known_at, event_input.artifact_identity_sha256),)
    preimage = {
        **projection_core,
        "snapshot_identity_sha256": snapshot_identity,
        "archive_identity_sha256": archive_identity,
        "receipt_identity_sha256": receipt_identity,
        "retained_identity_sha256": retained_identity,
        "attempts": attempts,
        "attempt_history_identity_sha256": _attempt_history_identity(attempts),
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
