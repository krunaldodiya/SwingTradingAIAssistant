"""Retained-only Volume admission under one exclusive, existing root lease."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.corporate_actions import (
    CorporateActionMissingError,
    CorporateActionSnapshotStoreV1,
    CorporateActionStaleError,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentRawInvocationControlV1,
    CurrentRawMemberProjectionV1,
    admitted_current_raw_context_binding_v1,
    admitted_current_raw_volumes_v1,
    read_retained_current_raw_context_v1,
    recheck_retained_current_raw_context_v1,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ScheduleEvidenceStore,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    StorageRootLease,
    StorageRootLeaseError,
)

from .current import calculate_volume
from .request import VolumeRequest, canonical_bytes, identity, instant, member_value
from .runtime_identity_manifest import VOLUME_RUNTIME_SOURCE_SHA256_V1

_LIMITATIONS = (
    "Source-reported unadjusted Upstox volume; no independent exchange certification.",
    "Corporate-action screening is nonexhaustive provider evidence, not proof of no action.",
    "Descriptive completed-session context, not a signal, ranking or trade eligibility.",
    "Current retained knowledge only; no historical point-in-time claim.",
    "Owner-private output; existing source-use restrictions apply.",
)
_FATAL_REASONS = frozenset(
    {
        "RAW_MAPPING_CORRUPT",
        "RAW_PARTITION_CORRUPT",
        "RAW_BAR_INVALID",
        "RAW_BAR_CONFLICTED",
        "SCHEDULE_AUTHORITY_CHANGED",
    }
)
_CALCULATION = {
    "version": "completed-session-volume@v1",
    "baseline_sessions": 20,
    "current_in_baseline": False,
    "arithmetic": "exact-reduced-rational",
    "grid": "21-regular-equal-duration-completed-sessions",
    "zero_baseline": "withheld",
    "volume_range": [0, 2**63 - 1],
}


@dataclass(frozen=True)
class _Clock:
    sample: Callable[[], datetime]

    def now(self) -> datetime:
        return self.sample()


def volume_runtime_identity() -> str:
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in VOLUME_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        digest = runtime_source_sha256(module, root, relative)
        if digest != expected:
            raise ValueError("volume runtime identity invalid")
        observed[relative] = digest
    return identity(observed)


@contextmanager
def _retained_lease(root: Path) -> Generator[StorageRootLease | None, None, None]:
    authority = StorageRootLease.capture_root_authority(root)
    if authority.state == "ABSENT":
        yield None
        StorageRootLease.ensure_root_authority(root, authority)
        return
    # An empty owner-created directory has no lock or calendar yet. Pin and
    # lock that directory without creating a lock file or following a new link.
    descriptor = os.open(
        root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    try:
        metadata = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) != authority.identity:
            raise StorageRootLeaseError("volume root authority changed")
        if not os.listdir(descriptor):
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if os.listdir(descriptor):
                raise StorageRootLeaseError("volume root authority changed")
            yield None
            if os.listdir(descriptor):
                raise StorageRootLeaseError("volume root authority changed")
        else:
            if authority.identity is None:
                raise StorageRootLeaseError("volume root authority unavailable")
            acquired = StorageRootLease.try_acquire_existing_identity(
                root, authority.identity
            )
            if acquired.lease is None:
                raise StorageRootLeaseError("volume root unavailable or held")
            with acquired.lease as lease:
                yield lease
        StorageRootLease.ensure_root_authority(root, authority)
    finally:
        os.close(descriptor)


def _source(member: CurrentRawMemberProjectionV1) -> dict[str, object]:
    return {
        "mapping_observation_sha256": member.mapping_observation_sha256,
        "mapping_retrieved_at": None
        if member.mapping_retrieved_at is None
        else instant(member.mapping_retrieved_at),
        "partition_checksums": list(member.partition_checksums),
        "raw_source_times": [instant(value) for value in member.raw_source_times],
        "screen_identity_sha256": member.screen_identity_sha256,
        "screen_knowledge_at": None
        if member.screen_knowledge_at is None
        else instant(member.screen_knowledge_at),
    }


def _withheld(
    request: VolumeRequest, state: str, reason: str
) -> list[dict[str, object]]:
    return [
        {
            "position": position,
            "member": member_value(member),
            "state": state,
            "reason": reason,
            "fact": None,
            "source": None,
        }
        for position, member in enumerate(request.members)
    ]


def _screen_integrity(
    request: VolumeRequest,
    root: Path,
    lease: StorageRootLease,
    control: CurrentRawInvocationControlV1,
) -> tuple[object, ...] | None:
    # The legacy price reader intentionally collapses unavailable screening.
    # Volume requires corrupt evidence to be terminal, even if another member
    # or input is missing. Inspect all requested screens through their real
    # retained store before reduction, and bind the same receipts afterwards.
    with lease.read_operation(root) as operation:
        try:
            os.stat(
                "catalog.duckdb", dir_fd=operation.descriptor, follow_symlinks=False
            )
        except FileNotFoundError:
            return None
    cutoff = control.retain_evidence_cutoff()
    receipts: list[object] = []
    with DuckDBCatalog(root, read_only=True, lease=lease) as catalog:
        store = CorporateActionSnapshotStoreV1(root, lease, catalog)
        for member in request.members:
            control.ensure_live()
            try:
                metadata, snapshot = store.resolve(
                    isin=member.isin, knowledge_cutoff=cutoff
                )
                receipts.append((metadata, snapshot.canonical_json_bytes()))
            except (CorporateActionMissingError, CorporateActionStaleError) as error:
                receipts.append(type(error).__name__)
        catalog.ensure_read_identity()
    return tuple(receipts)


def _read_members(
    request: VolumeRequest,
    root: Path,
    lease: StorageRootLease,
    control: CurrentRawInvocationControlV1,
) -> tuple[list[dict[str, object]], list[dict[str, object]], str | None]:
    screens = _screen_integrity(request, root, lease, control)
    store = ScheduleEvidenceStore(root, lease)
    schedule, absent = store._resolve_raw_history(  # pyright: ignore[reportPrivateUsage]
        request.schedule_identity_sha256, deadline=control
    )
    if schedule.schedule is None:
        if not absent:
            raise StorageRootLeaseError("volume calendar integrity failed")
        members = _withheld(
            request, "DEPENDENCY_BLOCKED", "CALENDAR_PREREQUISITE_MISSING"
        )
        sessions: list[dict[str, object]] = []
        schedule_as_of = None
    else:
        if screens is None:
            members = _withheld(request, "DEPENDENCY_BLOCKED", "RAW_MAPPING_MISSING")
            sessions = []
        else:
            members, sessions = _project(request, root, lease, control)
        schedule_as_of = instant(schedule.schedule.as_of)
    if _screen_integrity(request, root, lease, control) != screens:
        raise StorageRootLeaseError("volume screen authority changed")
    final, final_absent = store._resolve_raw_history(  # pyright: ignore[reportPrivateUsage]
        request.schedule_identity_sha256, deadline=control
    )
    if final_absent != absent or final.canonical_bytes != schedule.canonical_bytes:
        raise StorageRootLeaseError("volume calendar authority changed")
    return members, sessions, schedule_as_of


def _project(  # noqa: C901 -- ordered integrity, comparability and math admission
    request: VolumeRequest,
    root: Path,
    lease: StorageRootLease,
    control: CurrentRawInvocationControlV1,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    raw = read_retained_current_raw_context_v1(
        root,
        request=request.raw_input(),
        lease=lease,
        control=control,
        distinguish_missing_partitions=True,
    )
    if any(reason in _FATAL_REASONS for reason in raw.reasons):
        raise StorageRootLeaseError("volume retained integrity failed")
    if raw.admitted is None:
        repeated = read_retained_current_raw_context_v1(
            root,
            request=request.raw_input(),
            lease=lease,
            control=control,
            distinguish_missing_partitions=True,
        )
        if repeated != raw:
            raise StorageRootLeaseError("volume retained authority changed")
        return _withheld(request, raw.state, raw.reasons[0]), []
    projection, root_identity = admitted_current_raw_context_binding_v1(raw.admitted)
    expected = request.raw_input()
    if (
        projection.input_identity_sha256 != expected.input_identity_sha256
        or projection.request_identity_sha256 != expected.request_identity_sha256
        or projection.ordered_selection_identity_sha256
        != expected.ordered_selection_identity_sha256
        or projection.canonical_cohort_identity_sha256
        != expected.canonical_cohort_identity_sha256
        or projection.member_inputs != request.members
        or projection.data_selection_time != request.data_selection_time
        or projection.schedule_identity_sha256 != request.schedule_identity_sha256
        or projection.evidence_cutoff != control.evidence_cutoff
        or root_identity != StorageRootLease.admit_existing_private_identity(root)
    ):
        raise StorageRootLeaseError("volume producer selection binding invalid")
    if (projection.provider, projection.price_basis, projection.bar_basis) != (
        "UPSTOX",
        "RAW",
        "1d-derived-from-retained-1m",
    ):
        raise StorageRootLeaseError("volume source basis invalid")
    if any(member.reason in _FATAL_REASONS for member in projection.members):
        raise StorageRootLeaseError("volume retained integrity failed")
    volumes = admitted_current_raw_volumes_v1(raw.admitted)
    sessions: list[dict[str, object]] = [
        {
            "position": item.position,
            "session": item.session.isoformat(),
            "open_at": instant(item.open_at),
            "close_at": instant(item.close_at),
            "kind": item.kind,
        }
        for item in projection.sessions
    ]
    comparable = (
        all(item.kind == "REGULAR" for item in projection.sessions)
        and len({item.close_at - item.open_at for item in projection.sessions}) == 1
    )
    members: list[dict[str, object]] = []
    for member, grid in zip(projection.members, volumes, strict=True):
        state, reason, fact = member.state, member.reason, None
        if not comparable:
            state, reason = "UNSUPPORTED", "SESSION_COMPARABILITY_UNSUPPORTED"
        elif any(
            time > projection.evidence_cutoff
            for time in (
                *member.raw_source_times,
                *(
                    (member.mapping_retrieved_at,)
                    if member.mapping_retrieved_at is not None
                    else ()
                ),
                *(
                    (member.screen_knowledge_at,)
                    if member.screen_knowledge_at is not None
                    else ()
                ),
            )
        ):
            state, reason = "INSUFFICIENT_EVIDENCE", "SOURCE_FUTURE_KNOWN"
        elif member.state == "OBSERVED":
            if grid is None:
                raise StorageRootLeaseError("volume producer binding unavailable")
            calculated = calculate_volume(grid)
            if calculated is None:
                state, reason = "INSUFFICIENT_EVIDENCE", "ZERO_BASELINE"
            else:
                fact = asdict(calculated)
        members.append(
            {
                "position": member.position,
                "member": member_value(request.members[member.position]),
                "state": state,
                "reason": reason,
                "fact": fact,
                "source": _source(member),
            }
        )
    recheck_retained_current_raw_context_v1(
        raw.admitted,
        root,
        lease=lease,
        control=control,
        distinguish_missing_partitions=True,
    )
    return members, sessions


def research_current_volume(
    request: VolumeRequest,
    storage_root: Path,
    *,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Return owner-private facts only after source, clock and root final checks.

    Malformed input, corrupt evidence and lost authority raise before a result;
    absence and unsupported evidence produce typed member outcomes. No provider
    adapter, credential lookup or mutating store is called by this boundary.
    """
    if type(request) is not VolumeRequest or not isinstance(storage_root, Path):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError("invalid volume request")
    # Reconstruct to detect illicit mutation of a frozen public request/member.
    validated = VolumeRequest(
        request.data_selection_time,
        request.admission_deadline,
        request.schedule_identity_sha256,
        request.members,
    )
    control = CurrentRawInvocationControlV1(
        _Clock(clock or (lambda: datetime.now(UTC))),
        selection=validated.data_selection_time,
        deadline=validated.admission_deadline,
    )
    control.ensure_live()
    runtime = volume_runtime_identity()
    with _retained_lease(storage_root) as lease:
        control.ensure_live()
        control.retain_evidence_cutoff()
        if lease is None:
            members = _withheld(
                validated, "DEPENDENCY_BLOCKED", "CALENDAR_PREREQUISITE_MISSING"
            )
            sessions: list[dict[str, object]] = []
            schedule_as_of = None
        else:
            members, sessions, schedule_as_of = _read_members(
                validated, storage_root, lease, control
            )
        control.ensure_live()
        cutoff = control.evidence_cutoff
        if cutoff is None:
            raise RuntimeError("volume evidence cutoff unavailable")
        raw_input = validated.raw_input()
        result: dict[str, object] = {
            "contract_version": "current-volume-context@v1",
            "request_identity_sha256": validated.request_identity_sha256,
            "ordered_selection_identity_sha256": raw_input.ordered_selection_identity_sha256,
            "canonical_cohort_identity_sha256": raw_input.canonical_cohort_identity_sha256,
            "schedule_identity_sha256": validated.schedule_identity_sha256,
            "schedule_as_of": schedule_as_of,
            "data_selection_time": instant(validated.data_selection_time),
            "admission_deadline": instant(validated.admission_deadline),
            "evidence_cutoff": instant(cutoff),
            "runtime_code_identity_sha256": runtime,
            "calculation_identity_sha256": identity(_CALCULATION),
            "provider": "UPSTOX",
            "volume_basis": "RAW",
            "bar_basis": "1d-derived-from-retained-1m",
            "acquisition_mode": "RETAINED_ONLY",
            "provider_calls": 0,
            "requested_count": len(validated.members),
            "sessions": sessions,
            "members": members,
            "limitations": list(_LIMITATIONS),
            "state": "OBSERVED"
            if all(member["state"] == "OBSERVED" for member in members)
            else "NONREADY",
            "source_bindings_identity_sha256": identity(
                [member["source"] for member in members]
            ),
        }
        result["result_identity_sha256"] = identity(result)
        if len(canonical_bytes(result)) > 1024 * 1024:
            raise ValueError("volume result exceeds limit")
    control.ensure_live()
    return result
