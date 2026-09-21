"""Focused status-first transport contracts for Issue #188."""

from __future__ import annotations

import gzip
from datetime import UTC, datetime, timedelta
from email.message import Message
from io import BytesIO
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request

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
    geturl = staticmethod(
        lambda: "https://api.upstox.com/v2/fundamentals/INE000A01001/corporate-actions"
    )
    headers = SimpleNamespace(items=lambda: ())


class _Opener:
    def __init__(self, response: _ForbiddenBody) -> None:
        self._response = response

    def open(self, _request: object, *, timeout: float) -> _ForbiddenBody:
        assert timeout > 0
        return self._response


class _MappingResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.headers = SimpleNamespace(
            items=lambda: (("Content-Type", "application/gzip"),)
        )

    def getcode(self) -> int:
        return 200

    def geturl(self) -> str:
        return "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"

    def read(self, size: int) -> bytes:
        assert size == 4_000_001
        return self._body

    def close(self) -> None:
        return None


class _MappingOpener:
    def __init__(self, response: _MappingResponse) -> None:
        self._response = response

    def open(self, request: Request, *, timeout: float) -> _MappingResponse:
        assert request.full_url == self._response.geturl()
        assert timeout > 0
        return self._response


def test_mapping_transport_accepts_bounded_gzip_through_real_strict_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 9, 15, 9, tzinfo=UTC)
    body = gzip.compress(b"[]", mtime=0)

    def mapping_opener(*_handlers: object) -> _MappingOpener:
        return _MappingOpener(_MappingResponse(body))

    monkeypatch.setattr(transport, "build_opener", mapping_opener)

    response = transport.StrictCurrentRawHttpTransportV1(
        deadline=now + timedelta(minutes=1), now=lambda: now
    ).get(
        "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
        {"Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.body == body
    assert response.headers.get_single("Content-Type") == "application/gzip"


def test_operation_descriptor_rejects_an_unplanned_url_before_opening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 9, 15, 9, tzinfo=UTC)
    opened = False

    def forbidden_opener(*_handlers: object) -> _Opener:
        nonlocal opened
        opened = True
        return _Opener(_UnauthorizedResponse())

    monkeypatch.setattr(transport, "build_opener", forbidden_opener)
    strict = transport.StrictCurrentRawHttpTransportV1(
        deadline=now + timedelta(minutes=1),
        now=lambda: now,
        operation=transport.StrictCurrentRawOperationV1(
            "ACTION",
            "https://api.upstox.com/v2/fundamentals/INE000A01001/corporate-actions",
            1_048_576,
        ),
    )

    with pytest.raises(transport.CurrentRawProviderResponseError):
        strict.get("https://api.upstox.com/v3/historical-candle/anything", {})

    assert not opened


@pytest.mark.parametrize(
    ("kind", "expected_callback"),
    (("terminal-status", 0), ("body-timeout", 0), ("complete-success", 1)),
)
def test_response_completion_callback_only_follows_a_bounded_successful_body_read(
    monkeypatch: pytest.MonkeyPatch, kind: str, expected_callback: int
) -> None:
    now = datetime(2026, 9, 15, 9, tzinfo=UTC)

    class Response(_ForbiddenBody):
        headers = SimpleNamespace(items=lambda: (("Content-Type", "application/json"),))

        def getcode(self) -> int:
            return 404 if kind == "terminal-status" else 200

        def geturl(self) -> str:
            return (
                "https://api.upstox.com/v2/fundamentals/INE000A01001/corporate-actions"
            )

        def read(self, *_: object) -> bytes:
            if kind == "body-timeout":
                raise TimeoutError("deterministic body timeout")
            if kind == "terminal-status":
                raise AssertionError("terminal status must not read its body")
            return b'{"status":"success","data":[]}'

    def opener(*_: object) -> _Opener:
        return _Opener(Response())

    monkeypatch.setattr(transport, "build_opener", opener)
    completed: list[None] = []

    def response_completed() -> None:
        completed.append(None)

    if kind == "complete-success":
        response = transport.get_strict_current_raw_v1(
            "https://api.upstox.com/v2/fundamentals/INE000A01001/corporate-actions",
            headers={},
            timeout_seconds=1,
            deadline=now + timedelta(minutes=1),
            now=lambda: now,
            response_completed=response_completed,
        )
        assert response.body
    else:
        with pytest.raises(transport.CurrentRawProviderResponseError):
            transport.get_strict_current_raw_v1(
                "https://api.upstox.com/v2/fundamentals/INE000A01001/corporate-actions",
                headers={},
                timeout_seconds=1,
                deadline=now + timedelta(minutes=1),
                now=lambda: now,
                response_completed=response_completed,
            )
    assert len(completed) == expected_callback


@pytest.mark.parametrize(
    ("status", "error"),
    (
        (401, transport.CurrentRawAuthenticationError),
        (403, transport.CurrentRawAuthorizationError),
        (429, transport.CurrentRawRateLimitedError),
        (404, transport.CurrentRawProviderResponseError),
    ),
)
def test_raised_http_error_marks_one_terminal_response_without_reading_or_masking_status(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    error: type[Exception],
) -> None:
    """urllib raises HTTPError; it remains a completed terminal response."""
    now = datetime(2026, 9, 15, 9, tzinfo=UTC)
    url = "https://api.upstox.com/v2/fundamentals/INE000A01001/corporate-actions"

    class ForbiddenErrorBody(BytesIO):
        close_calls = 0

        def read(self, *_: object) -> bytes:
            raise AssertionError("raised HTTPError body must not be read")

        def close(self) -> None:
            type(self).close_calls += 1
            if type(self).close_calls == 1:
                raise OSError("raised HTTPError close must be subordinate")
            super().close()

    class RaisedErrorOpener:
        def open(self, _request: object, *, timeout: float) -> _ForbiddenBody:
            assert timeout > 0
            raise HTTPError(url, status, "fixture", Message(), ForbiddenErrorBody())

    def raised_error_opener(*_handlers: object) -> RaisedErrorOpener:
        return RaisedErrorOpener()

    monkeypatch.setattr(transport, "build_opener", raised_error_opener)
    terminal: list[None] = []

    with pytest.raises(error):
        transport.get_strict_current_raw_v1(
            url,
            headers={},
            timeout_seconds=1,
            deadline=now + timedelta(minutes=1),
            now=lambda: now,
            terminal_response=lambda: terminal.append(None),
        )

    assert terminal == [None]


@pytest.mark.parametrize(
    ("status", "error"),
    (
        (401, transport.CurrentRawAuthenticationError),
        (403, transport.CurrentRawAuthorizationError),
        (429, transport.CurrentRawRateLimitedError),
    ),
)
def test_status_first_shared_stops_never_read_oversized_or_misleading_bodies(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    error: type[Exception],
) -> None:
    class Response(_ForbiddenBody):
        headers = SimpleNamespace(items=lambda: (("Content-Type", "application/json"),))

        def getcode(self) -> int:
            return status

        def geturl(self) -> str:
            return (
                "https://api.upstox.com/v2/fundamentals/INE000A01001/corporate-actions"
            )

    def opener(*_handlers: object) -> _Opener:
        return _Opener(Response())

    monkeypatch.setattr(transport, "build_opener", opener)
    now = datetime(2026, 9, 15, 9, tzinfo=UTC)

    with pytest.raises(error):
        transport.get_strict_current_raw_v1(
            "https://api.upstox.com/v2/fundamentals/INE000A01001/corporate-actions",
            headers={},
            timeout_seconds=1,
            deadline=now + timedelta(minutes=1),
            now=lambda: now,
        )
