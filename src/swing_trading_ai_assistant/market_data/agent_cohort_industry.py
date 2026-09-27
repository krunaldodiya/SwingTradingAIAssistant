"""Narrow owner-private Industry source edge for agent cohort research.

This edge neither acquires events nor calculates Industry or Market Regime facts.
The existing parser, cohort projector and immutable archive own those contracts.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import current_evidence_acquisition as acquisition
from .current_industry_classification import (
    CurrentIndustryClassificationFailureV1,
    CurrentIndustryCohortMemberV1,
    FileCurrentIndustryArchiveV1,
    ParsedCurrentIndustryArtifactV1,
    PrivateCurrentIndustrySnapshotV1,
    RetainedCurrentIndustrySnapshotV1,
    parse_current_industry_artifact_v1,
    project_current_supplied_cohort_industry_v1,
    revalidate_retained_current_industry_snapshot_v1,
)
from .http import HttpTransport
from .storage_root_lease import StorageRootLease

_IST = ZoneInfo("Asia/Kolkata")


class RetainedIndustryAcquisitionError(acquisition.CurrentEvidenceAcquisitionError):
    """Keep exact retained evidence available when the later time check expires."""

    def __init__(self, code: str, retained: RetainedCurrentIndustrySnapshotV1) -> None:
        super().__init__(code)
        self.retained = retained


class _IndustryWindow:
    def __init__(
        self,
        root: Path,
        lease: StorageRootLease,
        clock: Callable[[], datetime],
        selected_at: datetime,
        decision_cutoff: datetime,
    ) -> None:
        if (
            not _utc(selected_at)
            or not _utc(decision_cutoff)
            or not selected_at < decision_cutoff <= selected_at + timedelta(minutes=30)
            or selected_at.astimezone(_IST).date()
            != decision_cutoff.astimezone(_IST).date()
        ):
            raise ValueError("invalid cohort Industry time window")
        self.root, self.lease, self.clock = root, lease, clock
        self.selected_at, self.cutoff = selected_at, decision_cutoff
        self.last = selected_at

    def authority(self) -> None:
        with self.lease.root_operation(self.root) as operation:
            operation.ensure_live()

    def check(self) -> datetime:
        self.authority()
        now = self.clock()
        if not _utc(now) or now < self.last:
            raise ValueError("invalid cohort Industry clock")
        self.last = now
        if now.astimezone(_IST).date() != self.selected_at.astimezone(_IST).date():
            raise acquisition.CurrentEvidenceAcquisitionError(
                "ACQUISITION_DATE_ROLLOVER"
            )
        if now > self.cutoff:
            raise acquisition.CurrentEvidenceAcquisitionError(
                "ACQUISITION_CUTOFF_EXCEEDED"
            )
        return now

    def before_effect(self) -> datetime:
        now = self.check()
        if now + timedelta(seconds=30) > self.cutoff:
            raise acquisition.CurrentEvidenceAcquisitionError(
                "ACQUISITION_CUTOFF_EXCEEDED"
            )
        return now


def _utc(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def acquire_and_retain_agent_industry(  # noqa: C901 -- source checks and final integrity precedence.
    root: Path,
    lease: StorageRootLease,
    cohort_identity: str,
    members: tuple[CurrentIndustryCohortMemberV1, ...],
    *,
    selected_at: datetime,
    decision_cutoff: datetime,
    transport: HttpTransport | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[
    RetainedCurrentIndustrySnapshotV1 | CurrentIndustryClassificationFailureV1, datetime
]:
    """Fetch once, retain exact admitted classification, and return its observation.

    Closed transport/parser outcomes stay typed. Corruption, retention failure,
    clock reversal and interruption propagate fatally. An existing receipt older
    than this observation raises the archive's distinct temporal incompatibility.
    """
    if (
        type(cohort_identity) is not str
        or len(cohort_identity) != 64
        or any(char not in "0123456789abcdef" for char in cohort_identity)
        or type(members) is not tuple
        or not 2 <= len(members) <= 50
        or any(type(member) is not CurrentIndustryCohortMemberV1 for member in members)
        or len({member.isin for member in members}) != len(members)
        or len({member.effective_symbol for member in members}) != len(members)
    ):
        raise ValueError("invalid cohort Industry request")
    window = _IndustryWindow(
        root,
        lease,
        (lambda: datetime.now(UTC)) if clock is None else clock,
        selected_at,
        decision_cutoff,
    )
    retained: object = None
    try:
        window.before_effect()
        observation = acquisition._fetch_exact(  # pyright: ignore[reportPrivateUsage]
            acquisition.BoundedOfficialHttpSessionV1()
            if transport is None
            else transport,
            window.check,
            url=acquisition.INDUSTRY_URL,
            headers={"Accept": "text/csv"},
            maximum_bytes=acquisition._MAX_INDUSTRY_BYTES,  # pyright: ignore[reportPrivateUsage]
            content_type="text/csv",
            require_content_disposition=False,
        )
        if (
            not acquisition._official_observation_is_exact_v1(observation)  # pyright: ignore[reportPrivateUsage]
            or observation.request_url != acquisition.INDUSTRY_URL
            or not selected_at <= observation.known_at <= decision_cutoff
        ):
            raise ValueError("cohort Industry observation binding mismatch")
        window.check()
        source = acquisition._industry_input(observation)  # pyright: ignore[reportPrivateUsage]
        parsed = parse_current_industry_artifact_v1(source, observation.body)
        if type(parsed) is CurrentIndustryClassificationFailureV1:
            return parsed, observation.known_at
        if type(parsed) is not ParsedCurrentIndustryArtifactV1:
            raise TypeError("unexpected Industry parser result")
        projected = project_current_supplied_cohort_industry_v1(
            parsed, cohort_identity, members
        )
        if type(projected) is CurrentIndustryClassificationFailureV1:
            return projected, observation.known_at
        if type(projected) is not PrivateCurrentIndustrySnapshotV1:
            raise TypeError("unexpected Industry projection result")
        window.before_effect()
        retained = FileCurrentIndustryArchiveV1(root).archive_exact(
            source, observation.body, projected, lease, observed_at=observation.known_at
        )
        if type(retained) is not RetainedCurrentIndustrySnapshotV1:
            raise ValueError("cohort Industry retention failed")
        if (
            retained.cohort_identity_sha256 != cohort_identity
            or retained.cohort_size != len(members)
            or retained.artifact_sha256 != observation.body_sha256
            or not observation.known_at <= retained.known_at
        ):
            raise ValueError("cohort Industry retention binding mismatch")
        window.check()
        if retained.known_at > decision_cutoff:
            raise acquisition.CurrentEvidenceAcquisitionError(
                "ACQUISITION_CUTOFF_EXCEEDED"
            )
        return retained, observation.known_at
    except acquisition.CurrentEvidenceAcquisitionError as error:
        if type(retained) is RetainedCurrentIndustrySnapshotV1:
            raise RetainedIndustryAcquisitionError(error.code.value, retained) from None
        raise
    finally:
        if type(retained) is RetainedCurrentIndustrySnapshotV1:
            revalidate_retained_current_industry_snapshot_v1(retained, root, lease)
        # Optional absence/expiry may never conceal lost storage authority.
        window.authority()
