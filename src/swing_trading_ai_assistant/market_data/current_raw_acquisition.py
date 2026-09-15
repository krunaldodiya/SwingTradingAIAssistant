"""Bounded retained inspection and missing-work acquisition entrypoint for #188.

The public boundary supplies only the canonical raw projection, storage root and
invocation stop control.  It never supplies a credential, provider key, or an
assertion that physical evidence is complete.  Calendar admission is always
performed before any future effect-planning phase.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from .catalog import DuckDBCatalog
from .current_raw_acquisition_transport import (
    StrictCurrentRawHttpTransportV1,
    StrictCurrentRawOperationV1,
)
from .current_raw_price_context import (
    CurrentRawInvocationControlV1,
    CurrentRawPriceContextInputV1,
    read_retained_current_raw_context_v1,
    validate_admitted_current_raw_context_v1,
)
from .instrument_snapshot import (
    InstrumentSnapshotClientV1,
    InstrumentSnapshotStoreV1,
)
from .schedule_evidence import (
    ScheduleEvidenceStore,
    exact_nse_schedule_source_release_pair_v1,
    schedule_covers_full_calendar_range,
)
from .storage_root_lease import StorageRootLease, StorageRootLeaseError

_IST = ZoneInfo("Asia/Kolkata")


class PlannedSlotDispositionV1(StrEnum):
    REUSABLE = "REUSABLE"
    MISSING = "MISSING"
    BLOCKED_MAPPING = "BLOCKED_MAPPING"
    INVALID = "INVALID"
    CONFLICTED = "CONFLICTED"
    FUTURE_KNOWN = "FUTURE_KNOWN"
    UNVERIFIED = "UNVERIFIED"


class LedgerSlotDispositionV1(StrEnum):
    REUSED = "REUSED"
    NOT_REQUIRED = "NOT_REQUIRED"
    NOT_ATTEMPTED_BLOCKED = "NOT_ATTEMPTED_BLOCKED"
    NOT_ATTEMPTED_SHARED_STOP = "NOT_ATTEMPTED_SHARED_STOP"
    RETAINED = "RETAINED"
    RETAINED_INCOMPLETE = "RETAINED_INCOMPLETE"
    FAILED = "FAILED"
    ABORTED_BEFORE_CATALOG_COMMIT = "ABORTED_BEFORE_CATALOG_COMMIT"


@dataclass(frozen=True, slots=True)
class _PhysicalSlotV1:
    """A bounded provider-sized physical operation, never an admitted fact."""

    key: str
    kind: Literal["MAPPING", "CLOSED", "CURRENT_HISTORY", "INTRADAY", "ACTION"]
    disposition: PlannedSlotDispositionV1
    year: int | None = None
    month: int | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class _MemberPlanV1:
    position: int
    isin: str
    exchange: Literal["NSE"]
    effective_symbol: str
    provider_key: str | None
    closed: tuple[_PhysicalSlotV1, ...]
    current_history: _PhysicalSlotV1 | None
    intraday: _PhysicalSlotV1 | None
    action: _PhysicalSlotV1


@dataclass(frozen=True, slots=True)
class _AcquisitionPlanV1:
    members: tuple[_MemberPlanV1, ...]
    mapping: _PhysicalSlotV1

    def __post_init__(self) -> None:
        if not 1 <= len(self.members) <= 50 or self.mapping.kind != "MAPPING":
            raise ValueError("current raw acquisition plan is invalid")
        if tuple(member.position for member in self.members) != tuple(
            range(len(self.members))
        ):
            raise ValueError("current raw acquisition plan is invalid")
        keys = [self.mapping.key]
        for member in self.members:
            if len(member.closed) > 3 or member.action.kind != "ACTION":
                raise ValueError("current raw acquisition plan is invalid")
            keys.extend(slot.key for slot in member.closed)
            keys.extend(
                slot.key
                for slot in (member.current_history, member.intraday, member.action)
                if slot is not None
            )
        if len(keys) != len(set(keys)) or len(keys) > 5 * len(self.members) + 1:
            raise ValueError("current raw acquisition plan is invalid")

    @property
    def maximum_calls(self) -> int:
        return 5 * len(self.members) + 1


@dataclass(frozen=True, slots=True)
class _LedgerSlotV1:
    key: str
    disposition: LedgerSlotDispositionV1
    attempts: int
    reason: str | None


@dataclass(frozen=True, slots=True)
class _AcquisitionAccountingV1:
    mapping: _LedgerSlotV1
    members: tuple[tuple[_LedgerSlotV1, ...], ...]
    total_calls: int


class _AcquisitionLedgerV1:
    """Invocation-local, position-preserving strict-opener accounting."""

    def __init__(self, plan: _AcquisitionPlanV1) -> None:
        self._plan = plan
        self._slots: dict[str, _LedgerSlotV1] = {}
        self._member_keys: list[list[str]] = []
        self._add(plan.mapping)
        for member in plan.members:
            keys: list[str] = []
            for slot in (
                *member.closed,
                member.current_history,
                member.intraday,
                member.action,
            ):
                if slot is not None:
                    self._add(slot)
                    keys.append(slot.key)
            self._member_keys.append(keys)
        self._shared_stop: str | None = None

    def _add(self, slot: _PhysicalSlotV1) -> None:
        if slot.key in self._slots:
            raise ValueError("duplicate acquisition slot")
        disposition = (
            LedgerSlotDispositionV1.REUSED
            if slot.disposition is PlannedSlotDispositionV1.REUSABLE
            else LedgerSlotDispositionV1.NOT_ATTEMPTED_BLOCKED
            if slot.disposition is not PlannedSlotDispositionV1.MISSING
            else LedgerSlotDispositionV1.NOT_REQUIRED
        )
        self._slots[slot.key] = _LedgerSlotV1(slot.key, disposition, 0, slot.reason)

    def before_open(self, key: str) -> None:
        if self._shared_stop is not None:
            raise RuntimeError("current raw acquisition is stopped")
        slot = self._slots.get(key)
        if (
            slot is None
            or slot.attempts
            or slot.disposition is not LedgerSlotDispositionV1.NOT_REQUIRED
        ):
            raise RuntimeError("current raw acquisition attempt rejected")
        total = sum(value.attempts for value in self._slots.values())
        if total >= self._plan.maximum_calls or total >= 251:
            raise RuntimeError("current raw acquisition attempt budget exceeded")
        self._slots[key] = _LedgerSlotV1(key, slot.disposition, 1, slot.reason)

    def shared_stop(self, reason: str) -> None:
        self._shared_stop = reason
        for key, slot in tuple(self._slots.items()):
            if slot.attempts == 0:
                self._slots[key] = _LedgerSlotV1(
                    key, LedgerSlotDispositionV1.NOT_ATTEMPTED_SHARED_STOP, 0, reason
                )

    def member_stop(self, position: int, reason: str) -> None:
        for key in self._member_keys[position]:
            slot = self._slots[key]
            if slot.attempts == 0:
                self._slots[key] = _LedgerSlotV1(
                    key, LedgerSlotDispositionV1.NOT_ATTEMPTED_BLOCKED, 0, reason
                )

    def snapshot(self) -> _AcquisitionAccountingV1:
        mapping = self._slots[self._plan.mapping.key]
        members = tuple(
            tuple(self._slots[key] for key in keys) for keys in self._member_keys
        )
        total = mapping.attempts + sum(
            slot.attempts for member in members for slot in member
        )
        if total > self._plan.maximum_calls or total > 251:
            raise RuntimeError("current raw acquisition accounting invalid")
        return _AcquisitionAccountingV1(mapping, members, total)


@dataclass(frozen=True, slots=True)
class CurrentRawAcquisitionResultV1:
    """Safe accounting for one bounded acquisition invocation.

    ``RETAINED_EVIDENCE_READY`` means inspection established that no provider
    work is required.  It deliberately does not represent a successful write.
    """

    outcome: Literal[
        "NOT_ATTEMPTED",
        "CALENDAR_PREREQUISITE_MISSING",
        "RETAINED_EVIDENCE_READY",
        "MAPPING_RETAINED",
    ]
    provider_calls: int
    accounting: _AcquisitionAccountingV1 | None = None

    def __post_init__(self) -> None:
        if type(self.provider_calls) is not int or not 0 <= self.provider_calls <= 1:
            raise ValueError("current raw acquisition result is invalid")
        if (self.outcome == "MAPPING_RETAINED") != (self.provider_calls == 1):
            raise ValueError("current raw acquisition result is invalid")
        if self.outcome != "MAPPING_RETAINED" and self.provider_calls != 0:
            raise ValueError("current raw acquisition result is invalid")


def acquire_missing_current_raw_evidence_v1(
    request: CurrentRawPriceContextInputV1,
    storage_root: Path,
    *,
    control: CurrentRawInvocationControlV1,
) -> CurrentRawAcquisitionResultV1:
    """Inspect retained prerequisites before any acquisition effect is possible.

    This deliberately establishes the mandatory calendar/root gate without
    constructing credential or HTTP machinery.  A future writer phase must use
    the same canonical request and a fresh retained admission after closing its
    bounded private transaction; callers cannot bypass this gate with a boolean
    or callback.
    """
    if (
        type(request) is not CurrentRawPriceContextInputV1
        or type(control) is not CurrentRawInvocationControlV1
    ):
        raise ValueError("current raw acquisition input is invalid")
    control.ensure_live()
    root_identity = StorageRootLease.admit_existing_private_identity(storage_root)
    if root_identity is None:
        return CurrentRawAcquisitionResultV1("CALENDAR_PREREQUISITE_MISSING", 0)
    admitted = StorageRootLease.try_admit_read_existing(storage_root)
    if admitted.lease is None:
        if (
            StorageRootLease.admit_existing_private_identity(storage_root)
            != root_identity
        ):
            raise StorageRootLeaseError("current raw acquisition root authority lost")
        return CurrentRawAcquisitionResultV1("CALENDAR_PREREQUISITE_MISSING", 0)
    with admitted.lease as lease:
        if (
            StorageRootLease.admit_existing_private_identity(storage_root)
            != root_identity
        ):
            raise StorageRootLeaseError(
                "current raw acquisition root authority changed"
            )
        if not _physical_calendar_prerequisite_is_proven(
            storage_root, request=request, lease=lease, control=control
        ):
            return CurrentRawAcquisitionResultV1("CALENDAR_PREREQUISITE_MISSING", 0)
        inspected = read_retained_current_raw_context_v1(
            storage_root, request=request, lease=lease, control=control
        )
        mapping_missing = _mapping_fetch_is_required(inspected)
        schedule = (
            ScheduleEvidenceStore(storage_root, lease)
            .resolve(request.schedule_identity_sha256, deadline=control)
            .schedule
        )
        if schedule is None:
            return CurrentRawAcquisitionResultV1("CALENDAR_PREREQUISITE_MISSING", 0)
        selected = tuple(
            item
            for item in schedule.sessions
            if item.close_at <= request.data_selection_time
        )[-21:]
        plan = _plan_physical_slots_v1(
            request, selected, mapping_reusable=not mapping_missing
        )
        ledger = _AcquisitionLedgerV1(plan)
    if "CALENDAR_PREREQUISITE_MISSING" in inspected.reasons:
        return CurrentRawAcquisitionResultV1("CALENDAR_PREREQUISITE_MISSING", 0)
    if not mapping_missing:
        outcome = (
            "RETAINED_EVIDENCE_READY"
            if _retained_evidence_is_ready(inspected)
            else "NOT_ATTEMPTED"
        )
        return CurrentRawAcquisitionResultV1(outcome, 0, ledger.snapshot())
    return _retain_missing_mapping(
        storage_root,
        root_identity=root_identity,
        request=request,
        control=control,
        ledger=ledger,
    )


def _mapping_fetch_is_required(inspected: object) -> bool:
    admitted = getattr(inspected, "admitted", None)
    if admitted is None:
        return False
    projection = validate_admitted_current_raw_context_v1(admitted)
    return any(member.reason == "RAW_MAPPING_MISSING" for member in projection.members)


def _retained_evidence_is_ready(inspected: object) -> bool:
    admitted = getattr(inspected, "admitted", None)
    if admitted is None:
        return False
    projection = validate_admitted_current_raw_context_v1(admitted)
    return all(member.state == "OBSERVED" for member in projection.members)


def _retain_missing_mapping(
    storage_root: Path,
    *,
    root_identity: tuple[int, int],
    request: CurrentRawPriceContextInputV1,
    control: CurrentRawInvocationControlV1,
    ledger: _AcquisitionLedgerV1,
) -> CurrentRawAcquisitionResultV1:
    """Perform the single credential-free BOD mapping effect after revalidation."""
    control.ensure_live()
    acquired = StorageRootLease.try_acquire_existing_identity(
        storage_root, root_identity
    )
    if acquired.lease is None:
        raise StorageRootLeaseError(
            "current raw acquisition write authority unavailable"
        )
    with acquired.lease as lease:
        if (
            StorageRootLease.admit_existing_private_identity(storage_root)
            != root_identity
        ):
            raise StorageRootLeaseError(
                "current raw acquisition root authority changed"
            )
        if not _physical_calendar_prerequisite_is_proven(
            storage_root, request=request, lease=lease, control=control
        ):
            return CurrentRawAcquisitionResultV1("CALENDAR_PREREQUISITE_MISSING", 0)
        attempts = 0

        def before_open() -> None:
            nonlocal attempts
            ledger.before_open("mapping")
            attempts += 1

        with DuckDBCatalog(storage_root, lease=lease) as catalog:
            store = InstrumentSnapshotStoreV1(storage_root, lease, catalog)
            client = InstrumentSnapshotClientV1(
                StrictCurrentRawHttpTransportV1(
                    deadline=request.admission_deadline,
                    now=control.now,
                    operation=StrictCurrentRawOperationV1(
                        "MAPPING",
                        "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
                        4_000_000,
                    ),
                    before_open=before_open,
                ),
                clock=control.now,
            )
            fetched = client.fetch()
            control.ensure_live()
            store.retain(fetched, deadline=control)
            control.ensure_live()
    return CurrentRawAcquisitionResultV1(
        "MAPPING_RETAINED", attempts, ledger.snapshot()
    )


def _physical_calendar_prerequisite_is_proven(
    storage_root: Path,
    *,
    request: CurrentRawPriceContextInputV1,
    lease: StorageRootLease,
    control: CurrentRawInvocationControlV1,
) -> bool:
    """Prove the exact 21-session and physical-month calendar ranges before work.

    This remains deliberately storage-only: mapping, catalog, token and provider
    construction occur only after this predicate succeeds.  It never widens the
    retained schedule or infers a weekday closure.
    """
    control.ensure_live()
    resolved = ScheduleEvidenceStore(storage_root, lease).resolve(
        request.schedule_identity_sha256, deadline=control
    )
    schedule = resolved.schedule
    if schedule is None or not exact_nse_schedule_source_release_pair_v1(
        schedule.source, schedule.source_release
    ):
        return False
    selected = tuple(
        item
        for item in schedule.sessions
        if item.close_at <= request.data_selection_time
    )[-21:]
    if len(selected) != 21:
        return False
    current_month = (
        control.selection_ist_date.year,
        control.selection_ist_date.month,
    )
    for year, month in _selected_months(selected):
        lower = date(year, month, 1)
        upper = (
            selected[-1].trade_date
            if (year, month) == current_month
            else date(year, month, monthrange(year, month)[1])
        )
        if not schedule_covers_full_calendar_range(schedule, lower, upper):
            return False
    control.ensure_live()
    return True


def _plan_physical_slots_v1(
    request: CurrentRawPriceContextInputV1,
    selected: tuple[object, ...],
    *,
    mapping_reusable: bool,
) -> _AcquisitionPlanV1:
    """Derive finite physical slots before any provider key is available."""
    if len(selected) != 21:
        raise ValueError("current raw acquisition plan is invalid")
    months = _selected_months(selected)
    if not 1 <= len(months) <= 3:
        raise ValueError("current raw acquisition plan is invalid")
    current = (
        request.data_selection_time.astimezone(_IST).year,
        request.data_selection_time.astimezone(_IST).month,
    )
    mapping_disposition = (
        PlannedSlotDispositionV1.REUSABLE
        if mapping_reusable
        else PlannedSlotDispositionV1.MISSING
    )
    members: list[_MemberPlanV1] = []
    for position, member in enumerate(request.members):
        raw_disposition = (
            PlannedSlotDispositionV1.MISSING
            if mapping_reusable
            else PlannedSlotDispositionV1.BLOCKED_MAPPING
        )
        closed = tuple(
            _PhysicalSlotV1(
                f"{position}:closed:{year:04d}-{month:02d}",
                "CLOSED",
                raw_disposition,
                year,
                month,
                None if mapping_reusable else "RAW_MAPPING_MISSING",
            )
            for year, month in months
            if (year, month) != current
        )
        is_current = current in months
        current_history = (
            _PhysicalSlotV1(
                f"{position}:current-history:{current[0]:04d}-{current[1]:02d}",
                "CURRENT_HISTORY",
                raw_disposition,
                current[0],
                current[1],
                None if mapping_reusable else "RAW_MAPPING_MISSING",
            )
            if is_current
            else None
        )
        selection_date = request.data_selection_time.astimezone(_IST).date()
        intraday = (
            _PhysicalSlotV1(
                f"{position}:intraday:{selection_date.isoformat()}",
                "INTRADAY",
                raw_disposition,
                current[0],
                current[1],
                None if mapping_reusable else "RAW_MAPPING_MISSING",
            )
            if is_current
            and getattr(selected[-1], "trade_date", None) == selection_date
            else None
        )
        members.append(
            _MemberPlanV1(
                position,
                member.isin,
                member.exchange,
                member.effective_symbol,
                None,
                closed,
                current_history,
                intraday,
                _PhysicalSlotV1(
                    f"{position}:action:{member.isin}",
                    "ACTION",
                    PlannedSlotDispositionV1.MISSING,
                ),
            )
        )
    return _AcquisitionPlanV1(
        tuple(members),
        _PhysicalSlotV1("mapping", "MAPPING", mapping_disposition),
    )


def _selected_months(selected: tuple[object, ...]) -> tuple[tuple[int, int], ...]:
    months: list[tuple[int, int]] = []
    for session in selected:
        trade_date = getattr(session, "trade_date", None)
        if type(trade_date) is not date:
            return ()
        key = (trade_date.year, trade_date.month)
        if key not in months:
            months.append(key)
    return tuple(months)
