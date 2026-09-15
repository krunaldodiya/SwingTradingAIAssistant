"""Focused status-first transport contracts for Issue #188."""

from __future__ import annotations

import gzip
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
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


def _opener(*_handlers: object) -> _Opener:
    return _Opener(_UnauthorizedResponse())


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
            1_000_000,
        ),
    )

    with pytest.raises(transport.CurrentRawProviderResponseError):
        strict.get("https://api.upstox.com/v3/historical-candle/anything", {})

    assert not opened


def test_unauthorized_status_stops_before_response_body_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transport, "build_opener", _opener)
    now = datetime(2026, 9, 15, 9, tzinfo=UTC)

    with pytest.raises(transport.CurrentRawAuthenticationError):
        transport.get_strict_current_raw_v1(
            "https://api.upstox.com/v2/fundamentals/INE000A01001/corporate-actions",
            headers={},
            timeout_seconds=1,
            deadline=now + timedelta(minutes=1),
            now=lambda: now,
        )
