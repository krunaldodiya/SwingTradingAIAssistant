"""Existing-only admission edge for Issue #188 raw price-context evidence.

The edge intentionally performs no provider, credential, writer, repair, or
calendar acquisition action.  It records a typed prerequisite when a retained
calendar and its physical plan are unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from .schedule_evidence import ScheduleEvidenceStore
from .storage_root_lease import StorageRootLease


@dataclass(frozen=True, slots=True)
class RetainedCurrentRawContextOutcomeV1:
    state: Literal["OBSERVED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"]
    reason: str | None
    selected_session_count: int = 0

    def __post_init__(self) -> None:
        if self.state == "OBSERVED" and self.reason is not None:
            raise ValueError("observed raw context cannot have a reason")
        if self.state != "OBSERVED" and (
            type(self.reason) is not str or not self.reason
        ):
            raise ValueError("unavailable raw context requires a reason")
        if (
            type(self.selected_session_count) is not int
            or not 0 <= self.selected_session_count <= 21
        ):
            raise ValueError("retained raw context session count is invalid")


def read_retained_current_raw_context_v1(
    storage_root: Path,
    *,
    schedule_identity_sha256: str,
    data_selection_time: datetime | None = None,
    admission_deadline: datetime | None = None,
) -> RetainedCurrentRawContextOutcomeV1:
    """Resolve the exact retained official schedule under one read lease.

    This edge is deliberately existing-only: it never supplies schedule bytes,
    creates a root, restores evidence, reads credentials, or contacts a
    provider. The selected sessions are a prerequisite for the later mapping,
    partition and screen stages and are never inferred from weekdays.
    """
    if (
        not storage_root.is_absolute()
        or not _digest(schedule_identity_sha256)
        or (data_selection_time is not None and not _utc(data_selection_time))
        or (admission_deadline is not None and not _utc(admission_deadline))
        or (data_selection_time is None) != (admission_deadline is None)
        or (
            data_selection_time is not None
            and admission_deadline is not None
            and data_selection_time >= admission_deadline
        )
    ):
        raise ValueError("retained raw context input is invalid")
    admitted = StorageRootLease.try_admit_read_existing(storage_root)
    if admitted.lease is None:
        return RetainedCurrentRawContextOutcomeV1(
            "DEPENDENCY_BLOCKED", "CALENDAR_PREREQUISITE_MISSING"
        )
    with admitted.lease as lease:
        schedule_result = ScheduleEvidenceStore(storage_root, lease).resolve(
            schedule_identity_sha256
        )
        if schedule_result.schedule is None:
            return RetainedCurrentRawContextOutcomeV1(
                "DEPENDENCY_BLOCKED", "CALENDAR_PREREQUISITE_MISSING"
            )
        if data_selection_time is None:
            return RetainedCurrentRawContextOutcomeV1(
                "INSUFFICIENT_EVIDENCE", "RAW_MEMBER_EVIDENCE_REQUIRED"
            )
        completed = tuple(
            session
            for session in schedule_result.schedule.sessions
            if session.close_at <= data_selection_time
        )
        selected = completed[-21:]
        if (
            len(selected) != 21
            or (selected[-1].trade_date - selected[0].trade_date).days + 1 > 64
        ):
            return RetainedCurrentRawContextOutcomeV1(
                "INSUFFICIENT_EVIDENCE", "COMPLETED_SESSION_WINDOW_UNAVAILABLE"
            )
        # The schedule object and root are rechecked before handing its exact
        # selected window to the mapping/partition stage.
        final_schedule = ScheduleEvidenceStore(storage_root, lease).resolve(
            schedule_identity_sha256
        )
        if (
            final_schedule.canonical_bytes != schedule_result.canonical_bytes
            or final_schedule.schedule is None
        ):
            return RetainedCurrentRawContextOutcomeV1(
                "INSUFFICIENT_EVIDENCE", "SCHEDULE_AUTHORITY_CHANGED"
            )
        with lease.read_operation(storage_root) as operation:
            operation.ensure_live()
        return RetainedCurrentRawContextOutcomeV1(
            "INSUFFICIENT_EVIDENCE", "RAW_MEMBER_EVIDENCE_REQUIRED", len(selected)
        )


def _utc(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is UTC


def _digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
