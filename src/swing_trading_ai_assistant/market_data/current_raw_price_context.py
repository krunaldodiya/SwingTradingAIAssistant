"""Existing-only admission edge for Issue #188 raw price-context evidence.

The edge intentionally performs no provider, credential, writer, repair, or
calendar acquisition action.  It records a typed prerequisite when a retained
calendar and its physical plan are unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class RetainedCurrentRawContextOutcomeV1:
    state: Literal["OBSERVED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"]
    reason: str | None

    def __post_init__(self) -> None:
        if self.state == "OBSERVED" and self.reason is not None:
            raise ValueError("observed raw context cannot have a reason")
        if self.state != "OBSERVED" and (
            type(self.reason) is not str or not self.reason
        ):
            raise ValueError("unavailable raw context requires a reason")


def read_retained_current_raw_context_v1(
    storage_root: Path, *, schedule_identity_sha256: str
) -> RetainedCurrentRawContextOutcomeV1:
    """Check the retained root without creating it or accessing a provider.

    A calendar schedule is deliberately not inferred from weekdays or arbitrary
    files.  Full retained evidence reconstruction is reached only after a
    concrete exact schedule binding is supplied by the production runtime.
    """
    if not storage_root.is_absolute() or not _digest(schedule_identity_sha256):
        raise ValueError("retained raw context input is invalid")
    try:
        root = storage_root.lstat()
    except FileNotFoundError:
        return RetainedCurrentRawContextOutcomeV1(
            "DEPENDENCY_BLOCKED", "CALENDAR_PREREQUISITE_MISSING"
        )
    if not root:
        raise AssertionError("unreachable storage metadata")
    return RetainedCurrentRawContextOutcomeV1(
        "DEPENDENCY_BLOCKED", "CALENDAR_PREREQUISITE_MISSING"
    )


def _digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
