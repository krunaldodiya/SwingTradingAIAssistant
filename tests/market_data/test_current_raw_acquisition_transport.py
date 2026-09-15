"""Focused status-first transport contracts for Issue #188."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from swing_trading_ai_assistant.market_data import (
    current_raw_acquisition_transport as transport,
)


class _ForbiddenBody:
    def read(self, *_: object) -> bytes:
        raise AssertionError("non-success transport read its response body")

    def close(self) -> None:
        return None


class _UnauthorizedResponse(_ForbiddenBody):
    getcode = staticmethod(lambda: 401)
    geturl = staticmethod(lambda: "https://example.invalid/path")
    headers = SimpleNamespace(items=lambda: ())


class _Opener:
    def __init__(self, response: _ForbiddenBody) -> None:
        self._response = response

    def open(self, _request: object, *, timeout: float) -> _ForbiddenBody:
        assert timeout > 0
        return self._response


def _opener(*_handlers: object) -> _Opener:
    return _Opener(_UnauthorizedResponse())


def test_unauthorized_status_stops_before_response_body_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transport, "build_opener", _opener)
    now = datetime(2026, 9, 15, 9, tzinfo=UTC)

    with pytest.raises(transport.CurrentRawAuthenticationError):
        transport.get_strict_current_raw_v1(
            "https://example.invalid/path",
            headers={},
            timeout_seconds=1,
            deadline=now + timedelta(minutes=1),
            now=lambda: now,
        )
