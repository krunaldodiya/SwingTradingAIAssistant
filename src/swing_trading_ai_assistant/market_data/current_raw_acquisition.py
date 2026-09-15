"""Bounded retained inspection and missing-work acquisition entrypoint for #188.

The public boundary supplies only the canonical raw projection, storage root and
invocation stop control.  It never supplies a credential, provider key, or an
assertion that physical evidence is complete.  Calendar admission is always
performed before any future effect-planning phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .current_raw_price_context import (
    CurrentRawInvocationControlV1,
    CurrentRawPriceContextInputV1,
    read_retained_current_raw_context_v1,
)
from .storage_root_lease import StorageRootLease


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
    ]
    provider_calls: int

    def __post_init__(self) -> None:
        if self.provider_calls != 0:
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
    admitted = StorageRootLease.try_admit_read_existing(storage_root)
    if admitted.lease is None:
        return CurrentRawAcquisitionResultV1("CALENDAR_PREREQUISITE_MISSING", 0)
    with admitted.lease as lease:
        inspected = read_retained_current_raw_context_v1(
            storage_root, request=request, lease=lease, control=control
        )
    if "CALENDAR_PREREQUISITE_MISSING" in inspected.reasons:
        return CurrentRawAcquisitionResultV1("CALENDAR_PREREQUISITE_MISSING", 0)
    return CurrentRawAcquisitionResultV1("RETAINED_EVIDENCE_READY", 0)
