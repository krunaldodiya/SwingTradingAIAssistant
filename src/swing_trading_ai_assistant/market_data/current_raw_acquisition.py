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
from pathlib import Path
from typing import Literal

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
    if "CALENDAR_PREREQUISITE_MISSING" in inspected.reasons:
        return CurrentRawAcquisitionResultV1("CALENDAR_PREREQUISITE_MISSING", 0)
    if not mapping_missing:
        outcome = (
            "RETAINED_EVIDENCE_READY"
            if _retained_evidence_is_ready(inspected)
            else "NOT_ATTEMPTED"
        )
        return CurrentRawAcquisitionResultV1(outcome, 0)
    return _retain_missing_mapping(
        storage_root, root_identity=root_identity, request=request, control=control
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
            if attempts != 0:
                raise RuntimeError("current raw mapping attempt budget exceeded")
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
    return CurrentRawAcquisitionResultV1("MAPPING_RETAINED", attempts)


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
