"""Bounded #188 missing-evidence acquisition admission.

This module deliberately owns only effect admission and shared-stop precedence.
Concrete provider work is supplied by the production composition after a retained
calendar has proved the physical plan; a missing prerequisite cannot read a
credential or touch a provider.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal


@dataclass(frozen=True, slots=True)
class CurrentRawAcquisitionRequestV1:
    contract_version: Literal["current-raw-acquisition@v1"]
    schedule_identity_sha256: str
    requested_at: datetime
    deadline: datetime
    member_count: int
    physical_coverage_complete: bool

    def __post_init__(self) -> None:
        if (
            self.contract_version != "current-raw-acquisition@v1"
            or not _digest(self.schedule_identity_sha256)
            or not _utc(self.requested_at)
            or not _utc(self.deadline)
            or not 1 <= self.member_count <= 50
            or type(self.physical_coverage_complete) is not bool
            or not self.requested_at < self.deadline
            or self.deadline - self.requested_at > timedelta(minutes=30)
        ):
            raise ValueError("current raw acquisition request is invalid")


@dataclass(frozen=True, slots=True)
class CurrentRawAcquisitionResultV1:
    outcome: Literal[
        "NOT_ATTEMPTED",
        "CALENDAR_PREREQUISITE_MISSING",
        "CREDENTIALS_UNAVAILABLE",
        "READY",
    ]
    provider_calls: int

    def __post_init__(self) -> None:
        if self.provider_calls < 0 or (
            self.outcome != "READY" and self.provider_calls != 0
        ):
            raise ValueError("current raw acquisition result is invalid")


def acquire_missing_current_raw_evidence_v1(
    request: CurrentRawAcquisitionRequestV1,
    credential: Callable[[], str],
) -> CurrentRawAcquisitionResultV1:
    """Admit the calendar before lazily obtaining a provider credential.

    No network operation occurs in this narrow admission primitive.  The caller
    can use ``READY`` only to begin the separately bounded serial effect plan.
    """
    if type(request) is not CurrentRawAcquisitionRequestV1 or not callable(credential):
        raise ValueError("current raw acquisition input is invalid")
    if not request.physical_coverage_complete:
        return CurrentRawAcquisitionResultV1("CALENDAR_PREREQUISITE_MISSING", 0)
    token = credential()
    if type(token) is not str or not token:
        return CurrentRawAcquisitionResultV1("CREDENTIALS_UNAVAILABLE", 0)
    return CurrentRawAcquisitionResultV1("READY", 0)


def _digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _utc(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is UTC
