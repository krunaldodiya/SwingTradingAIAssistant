from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

import pytest

APPROVED_PRIVATE_SOURCE_TESTS = frozenset(
    {
        "tests/market_data/test_historical_upstox_raw.py::test_real_retained_reliance_july_initial_and_exact_retry",
        "tests/market_data/test_historical_upstox_raw.py::test_real_retained_reliance_append_is_source_backed_and_preserves_known_at",
        "tests/market_data/test_historical_upstox_raw.py::test_real_current_august_provisional_partition_is_insufficient",
        "tests/market_data/test_historical_upstox_raw.py::test_real_current_fifty_member_schedule_conflict_fails_closed",
    }
)


class _CollectedItem(Protocol):
    nodeid: str

    def iter_markers(self, name: str | None = None) -> Iterable[object]: ...


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[_CollectedItem]) -> None:
    marked = {item.nodeid for item in items if any(item.iter_markers("private_source"))}
    unexpected = marked - APPROVED_PRIVATE_SOURCE_TESTS
    if unexpected:
        names = ", ".join(sorted(unexpected))
        raise pytest.UsageError(f"unapproved private_source test(s): {names}")
