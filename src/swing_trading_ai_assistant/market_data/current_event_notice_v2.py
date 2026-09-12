"""Additive redacted member-local Event V2 projection for Issue #187.

It consumes only V1's already admitted parsed artifact.  V1's whole-cohort
projection remains untouched; this successor isolates relevant-row conflicts
without exposing notice bodies or private rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Literal, cast

from .current_event_notice import (
    CurrentEventCohortMemberV1,
    CurrentEventNoticeFailureV1,
    ParsedCurrentEventNoticeArtifactV1,
    _identity,  # pyright: ignore[reportPrivateUsage]
    _member_result,  # pyright: ignore[reportPrivateUsage]
    _projection_failure,  # pyright: ignore[reportPrivateUsage]
    _relevant_row_failure,  # pyright: ignore[reportPrivateUsage]
)


@dataclass(frozen=True, slots=True)
class CurrentEventNoticeRedactedObservationV2:
    observation_identity_sha256: str
    deduplication_identity_sha256: str


@dataclass(frozen=True, slots=True)
class CurrentEventNoticeMemberOutcomeV2:
    member: CurrentEventCohortMemberV1
    availability: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
    support: Literal["SUPPORTED", "CONFLICTED", "NOT_ESTABLISHED"]
    reason: str | None
    outcome: Literal["NOTICES_ADMITTED", "NO_MATCHING_NOTICE_IN_SNAPSHOT"] | None
    notices: tuple[CurrentEventNoticeRedactedObservationV2, ...]

    def __post_init__(self) -> None:
        observed = self.availability == "OBSERVED"
        if observed != (self.outcome is not None) or observed != (self.reason is None):
            raise ValueError("invalid Event V2 member outcome")
        if not observed and (self.support == "SUPPORTED" or self.notices):
            raise ValueError("invalid Event V2 member outcome")
        if self.outcome == "NO_MATCHING_NOTICE_IN_SNAPSHOT" and self.notices:
            raise ValueError("invalid Event V2 member outcome")


@dataclass(frozen=True, slots=True)
class AdmittedCurrentEventNoticeEvidenceV2:
    """Redacted projection with a trusted, non-backdated admission time."""

    contract_version: Literal["current-event-notice-evidence@v2"]
    schema_identity_sha256: str
    artifact_identity_sha256: str
    cohort_identity_sha256: str
    known_at: datetime
    members: tuple[CurrentEventNoticeMemberOutcomeV2, ...]

    def __post_init__(self) -> None:
        known_at = self.known_at
        if (
            self.contract_version != "current-event-notice-evidence@v2"
            or any(
                type(value) is not str
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
                for value in (
                    self.schema_identity_sha256,
                    self.artifact_identity_sha256,
                    self.cohort_identity_sha256,
                )
            )
            or type(known_at) is not datetime
            or known_at.tzinfo is None
            or known_at.utcoffset() != UTC.utcoffset(None)
            or type(self.members) is not tuple
            or not self.members
            or any(
                type(item) is not CurrentEventNoticeMemberOutcomeV2
                for item in self.members
            )
            or len({(item.member.isin, item.member.exchange) for item in self.members})
            != len(self.members)
            or self.cohort_identity_sha256
            != _event_cohort_identity(tuple(item.member for item in self.members))
        ):
            raise ValueError("invalid admitted Event V2 evidence")
        object.__setattr__(self, "known_at", known_at.astimezone(UTC))

    @property
    def evidence_identity_sha256(self) -> str:
        return sha256(self.canonical_json_bytes()).hexdigest()

    def canonical_json_bytes(self) -> bytes:
        return (
            json.dumps(
                _wire(self), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
            + b"\n"
        )


def _member_value(member: CurrentEventCohortMemberV1) -> dict[str, object]:
    return {
        "isin": member.isin,
        "exchange": member.exchange,
        "listed_equity_segment": member.listed_equity_segment,
        "symbol": member.symbol,
        "effective_from": member.effective_from.isoformat(),
        "effective_through": member.effective_through.isoformat(),
        "provider_mapping_revision": member.provider_mapping_revision,
    }


def _event_cohort_identity(
    members: tuple[CurrentEventCohortMemberV1, ...],
) -> str:
    return _identity(
        {
            "members": [
                _member_value(member)
                for member in sorted(members, key=lambda item: item.isin)
            ]
        }
    )


def _wire(value: object) -> object:
    if type(value) is date:
        return value.isoformat()
    if type(value) is datetime:
        return (
            value.astimezone(UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _wire(getattr(value, item.name)) for item in fields(value)}
    if type(value) is tuple:
        return [_wire(item) for item in cast(tuple[object, ...], value)]
    if type(value) is list:
        return [_wire(item) for item in cast(list[object], value)]
    return value


def project_current_supplied_cohort_event_outcomes_v2(
    parsed: ParsedCurrentEventNoticeArtifactV1,
    members: tuple[CurrentEventCohortMemberV1, ...],
) -> tuple[CurrentEventNoticeMemberOutcomeV2, ...] | CurrentEventNoticeFailureV1:
    """Project redacted outcomes; only a relevant member conflict is local."""
    if (
        type(parsed) is not ParsedCurrentEventNoticeArtifactV1
        or type(members) is not tuple
    ):
        raise TypeError("event V2 projection invalid")
    shared = _projection_failure(parsed, members)
    if shared is not None:
        return shared
    outcomes: list[CurrentEventNoticeMemberOutcomeV2] = []
    for member in members:
        reason = _relevant_row_failure(parsed.private_rows, frozenset((member.symbol,)))
        if reason is not None:
            outcomes.append(
                CurrentEventNoticeMemberOutcomeV2(
                    member, "INSUFFICIENT_EVIDENCE", "CONFLICTED", reason, None, ()
                )
            )
            continue
        result = _member_result(member, parsed.private_rows)
        outcomes.append(
            CurrentEventNoticeMemberOutcomeV2(
                member,
                "OBSERVED",
                "SUPPORTED",
                None,
                result.outcome,
                tuple(
                    CurrentEventNoticeRedactedObservationV2(
                        notice.observation_identity_sha256,
                        notice.deduplication_identity_sha256,
                    )
                    for notice in result.notices
                ),
            )
        )
    return tuple(outcomes)


def admit_current_supplied_cohort_event_evidence_v2(
    parsed: ParsedCurrentEventNoticeArtifactV1,
    members: tuple[CurrentEventCohortMemberV1, ...],
    *,
    known_at: datetime,
) -> AdmittedCurrentEventNoticeEvidenceV2 | CurrentEventNoticeFailureV1:
    """Bind redacted V2 outcomes to the caller's retained evidence time.

    This boundary deliberately refuses to mint a fresh clock timestamp for an
    older parsed artifact. Callers must carry forward the immutable retention
    time established by their evidence owner.
    """
    if (
        type(known_at) is not datetime
        or known_at.tzinfo is None
        or known_at.utcoffset() != UTC.utcoffset(None)
    ):
        raise ValueError("invalid Event V2 known_at")
    projected = project_current_supplied_cohort_event_outcomes_v2(parsed, members)
    if isinstance(projected, CurrentEventNoticeFailureV1):
        return projected
    return AdmittedCurrentEventNoticeEvidenceV2(
        "current-event-notice-evidence@v2",
        parsed.schema_identity_sha256,
        parsed.artifact_identity_sha256,
        _event_cohort_identity(members),
        known_at,
        projected,
    )
