"""Small shared coordination contracts for bounded market-data workflows."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol


class PublicationGateV1(Protocol):
    """Serialize catalog and immutable-publication phases, never provider waits."""

    def __enter__(self) -> object: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> bool | None: ...
