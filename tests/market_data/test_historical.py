from __future__ import annotations

import json
import traceback
from collections.abc import Callable, Iterable
from datetime import date
from email.message import Message
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from swing_trading_ai_assistant.market_data.credentials import AccessToken
from swing_trading_ai_assistant.market_data.historical import (
    HistoricalRequest,
    UpstoxV3HistoricalClient,
)
from swing_trading_ai_assistant.market_data.http import (
    HttpResponse,
    HttpResponseBodyTooLarge,
    HttpResponseHeaders,
    HttpResponseHeadersInvalid,
    ProviderErrorCategory,
    UrllibHttpTransport,
)

_FAKE_BEARER = "fake-bearer-must-not-survive"


def _project_traceback_values(error: BaseException) -> tuple[object, ...]:
    package_directory = (
        Path(
            __import__(
                "swing_trading_ai_assistant.market_data.historical",
                fromlist=["__file__"],
            ).__file__
        )
        .resolve()
        .parents[1]
    )
    values: list[object] = []
    current = error.__traceback__
    while current is not None:
        frame_path = Path(current.tb_frame.f_code.co_filename).resolve()
        if frame_path.is_relative_to(package_directory):
            values.extend(current.tb_frame.f_locals.values())
        current = current.tb_next
    return tuple(values)


def _walk_retained_objects(values: Iterable[object]) -> tuple[object, ...]:
    retained: list[object] = []
    pending = list(values)
    seen: set[int] = set()
    while pending:
        value = pending.pop()
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        retained.append(value)
        if isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            pending.extend(value)
        elif hasattr(value, "__dict__"):
            pending.extend(vars(value).values())
    return tuple(retained)


class _OversizedResponse:
    status = 200

    def __init__(self) -> None:
        self._body = BytesIO(b"1234")
        self.headers = Message()

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def __enter__(self) -> _OversizedResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _oversized_success(request: Request, timeout: float) -> object:
    return _OversizedResponse()


def _oversized_http_error(request: Request, timeout: float) -> object:
    raise HTTPError(
        request.full_url,
        429,
        "too many requests",
        Message(),
        BytesIO(b"1234"),
    )


class _InvalidHeaders:
    def items(self) -> list[tuple[str, str]]:
        return [("X Invalid", "header-secret")]


class _InvalidHeadersResponse:
    status = 200

    def __init__(self) -> None:
        self._body = BytesIO(b"body-secret")
        self.headers = _InvalidHeaders()

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def __enter__(self) -> _InvalidHeadersResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _invalid_headers_success(request: Request, timeout: float) -> object:
    return _InvalidHeadersResponse()


def _invalid_headers_http_error(request: Request, timeout: float) -> object:
    raise HTTPError(
        request.full_url,
        429,
        "too many requests",
        _InvalidHeaders(),
        BytesIO(b"body-secret"),
    )


class RecordingTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        self.requests.append((url, headers))
        return self.response


def test_historical_client_uses_official_v3_minute_path() -> None:
    payload = {"status": "success", "data": {"candles": []}}
    transport = RecordingTransport(
        HttpResponse(status_code=200, body=json.dumps(payload).encode())
    )
    client = UpstoxV3HistoricalClient(transport)
    request = HistoricalRequest(
        instrument_key="NSE_EQ|INE002A01018",
        unit="minutes",
        interval=1,
        from_date=date(2026, 7, 27),
        to_date=date(2026, 7, 31),
    )

    response = client.fetch(request, AccessToken("test-token"))

    assert response.status_code == 200
    assert response.candles == []
    assert transport.requests == [
        (
            "https://api.upstox.com/v3/historical-candle/"
            "NSE_EQ%7CINE002A01018/minutes/1/2026-07-31/2026-07-27",
            {
                "Accept": "application/json",
                "Authorization": "Bearer test-token",
            },
        )
    ]


def test_historical_request_rejects_backwards_dates() -> None:
    with pytest.raises(ValueError, match="from_date"):
        HistoricalRequest(
            instrument_key="NSE_EQ|INE002A01018",
            unit="minutes",
            interval=1,
            from_date=date(2026, 8, 1),
            to_date=date(2026, 7, 31),
        )


@pytest.mark.parametrize(
    ("unit", "interval"),
    [
        ("minutes", 301),
        ("hours", 6),
        ("days", 2),
        ("weeks", 2),
        ("months", 2),
    ],
)
def test_historical_request_rejects_unsupported_v3_unit_interval_pairs(
    unit: str, interval: int
) -> None:
    with pytest.raises(ValueError, match="interval"):
        HistoricalRequest(
            instrument_key="NSE_EQ|INE002A01018",
            unit=unit,
            interval=interval,
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
        )


@pytest.mark.parametrize("interval", [1, 15])
def test_historical_request_limits_one_to_fifteen_minute_ranges_to_one_month(
    interval: int,
) -> None:
    with pytest.raises(ValueError, match="one calendar month"):
        HistoricalRequest(
            instrument_key="NSE_EQ|INE002A01018",
            unit="minutes",
            interval=interval,
            from_date=date(2026, 7, 1),
            to_date=date(2026, 8, 1),
        )


def test_historical_client_preserves_retry_and_request_headers_for_non_2xx() -> None:
    transport = RecordingTransport(
        HttpResponse(
            status_code=429,
            body=b'{"errors":[]}',
            headers=HttpResponseHeaders.from_items(
                (("Retry-After", "12"), ("X-Request-Id", "request-123"))
            ),
        )
    )

    response = UpstoxV3HistoricalClient(transport).fetch(
        HistoricalRequest(
            instrument_key="NSE_EQ|INE002A01018",
            unit="minutes",
            interval=1,
            from_date=date(2026, 7, 31),
            to_date=date(2026, 7, 31),
        ),
        AccessToken("test-token"),
    )

    assert response.candles == []
    assert response.headers.items() == (
        ("Retry-After", "12"),
        ("X-Request-Id", "request-123"),
    )
    assert response.error_category is ProviderErrorCategory.RATE_LIMITED


def test_historical_client_rejects_malformed_success_payload() -> None:
    transport = RecordingTransport(HttpResponse(status_code=200, body=b'{"data": {}}'))
    client = UpstoxV3HistoricalClient(transport)
    request = HistoricalRequest(
        instrument_key="NSE_EQ|INE002A01018",
        unit="minutes",
        interval=1,
        from_date=date(2026, 7, 31),
        to_date=date(2026, 7, 31),
    )

    with pytest.raises(ValueError, match="candles"):
        client.fetch(request, AccessToken("test-token"))


@pytest.mark.parametrize("opener", [_oversized_success, _oversized_http_error])
def test_oversized_authenticated_response_traceback_retains_no_secret_state(
    opener: Callable[..., object],
) -> None:
    token = AccessToken(_FAKE_BEARER)
    client = UpstoxV3HistoricalClient(
        UrllibHttpTransport(max_body_bytes=3, opener=opener)
    )
    request = HistoricalRequest(
        instrument_key="NSE_EQ|INE002A01018",
        unit="minutes",
        interval=1,
        from_date=date(2026, 7, 31),
        to_date=date(2026, 7, 31),
    )

    with pytest.raises(HttpResponseBodyTooLarge) as exc_info:
        client.fetch(request, token)

    error = exc_info.value
    rendered = "".join(
        traceback.TracebackException.from_exception(error, capture_locals=True).format()
    )
    retained = _walk_retained_objects(_project_traceback_values(error))

    assert _FAKE_BEARER not in rendered
    assert not any(value is token for value in retained)
    assert not any(isinstance(value, (Request, HTTPError)) for value in retained)
    assert not any(_FAKE_BEARER in repr(value) for value in retained)
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.mark.parametrize(
    "opener", [_invalid_headers_success, _invalid_headers_http_error]
)
def test_invalid_authenticated_response_headers_leave_no_secret_state_in_traceback(
    opener: Callable[..., object],
) -> None:
    token = AccessToken(_FAKE_BEARER)
    client = UpstoxV3HistoricalClient(UrllibHttpTransport(opener=opener))
    token_identity = id(token)
    client_identity = id(client)
    provider_identity = id(client._transport)
    request = HistoricalRequest(
        instrument_key="NSE_EQ|INE002A01018",
        unit="minutes",
        interval=1,
        from_date=date(2026, 7, 31),
        to_date=date(2026, 7, 31),
    )

    with pytest.raises(HttpResponseHeadersInvalid) as exc_info:
        client.fetch(request, token)

    error = exc_info.value
    del request, client, token
    rendered = "".join(
        traceback.TracebackException.from_exception(error, capture_locals=True).format()
    )
    retained = _walk_retained_objects(_project_traceback_values(error))

    assert _FAKE_BEARER not in rendered
    assert "body-secret" not in rendered
    assert "header-secret" not in rendered
    assert "NSE_EQ" not in rendered
    assert "api.upstox.com" not in rendered
    assert not any(
        id(value) in (token_identity, client_identity, provider_identity)
        for value in retained
    )
    assert not any(isinstance(value, (Request, HTTPError)) for value in retained)
    assert not any(
        secret in repr(value)
        for value in retained
        for secret in (
            _FAKE_BEARER,
            "body-secret",
            "header-secret",
            "NSE_EQ",
            "api.upstox.com",
        )
    )
    assert error.__cause__ is None
    assert error.__context__ is None
