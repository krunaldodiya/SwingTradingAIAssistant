from __future__ import annotations

import json
from email.message import Message
from io import BytesIO

import pytest

from swing_trading_ai_assistant.market_data.credentials import AccessToken
from swing_trading_ai_assistant.market_data.http import (
    HttpResponse,
    HttpResponseBodyTooLarge,
    HttpResponseHeaders,
    HttpResponseHeadersInvalid,
    ProviderErrorCategory,
    UrllibHttpTransport,
)
from swing_trading_ai_assistant.market_data.intraday import (
    IntradayRequest,
    IntradayResponse,
    UpstoxV3IntradayClient,
)


class RecordingTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        self.requests.append((url, headers))
        return self.response


class RaisingTransport:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        del url, headers
        self.calls += 1
        raise self.error


class _Response:
    status = 200

    def __init__(self, body: bytes) -> None:
        self._body = BytesIO(body)
        self.headers = Message()

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _success(candles: object) -> HttpResponse:
    return HttpResponse(
        status_code=200,
        body=json.dumps({"status": "success", "data": {"candles": candles}}).encode(),
    )


def test_intraday_client_uses_documented_escaped_one_minute_route_once() -> None:
    transport = RecordingTransport(_success([]))

    response = UpstoxV3IntradayClient(transport).fetch(
        IntradayRequest("NSE_EQ|INE002A01018/a b"), AccessToken("test-token")
    )

    assert response.status_code == 200
    assert response.candles == []
    assert transport.requests == [
        (
            "https://api.upstox.com/v3/historical-candle/intraday/"
            "NSE_EQ%7CINE002A01018%2Fa%20b/minutes/1",
            {
                "Accept": "application/json",
                "Authorization": "Bearer test-token",
            },
        )
    ]


def test_intraday_client_leaves_user_agent_injection_to_transport() -> None:
    observed_headers: dict[str, str] = {}

    def opener(request: object, timeout: float) -> object:
        del timeout
        observed_headers.update(request.headers)  # type: ignore[attr-defined]
        return _Response(b'{"status":"success","data":{"candles":[]}}')

    response = UpstoxV3IntradayClient(UrllibHttpTransport(opener=opener)).fetch(
        IntradayRequest("NSE_EQ|INE002A01018"), AccessToken("test-token")
    )

    assert response.candles == []
    assert observed_headers["User-agent"] == "SwingTradingAIAssistant/0.1"
    assert observed_headers["Authorization"] == "Bearer test-token"


def test_intraday_client_preserves_non_success_metadata_without_parsing_body() -> None:
    headers = HttpResponseHeaders.from_items(
        (("Retry-After", "12"), ("X-Request-Id", "request-123"))
    )
    transport = RecordingTransport(
        HttpResponse(status_code=429, body=b"not-json", headers=headers)
    )

    response = UpstoxV3IntradayClient(transport).fetch(
        IntradayRequest("NSE_EQ|INE002A01018"), AccessToken("test-token")
    )

    assert response.status_code == 429
    assert response.candles == []
    assert response.headers is headers
    assert response.error_category is ProviderErrorCategory.RATE_LIMITED


@pytest.mark.parametrize(
    "body",
    [
        b'{"status":"success","data":{"candles":[]},"data":{"candles":[]}}',
        b'{"status":"success","data":{"candles":[]},"extra":true}',
        b'{"status":"success","data":{"candles":[]},"value":NaN}',
        b"{" + (b"[" * 65) + (b"]" * 65) + b"}",
    ],
)
def test_intraday_client_rejects_noncanonical_success_json(body: bytes) -> None:
    transport = RecordingTransport(HttpResponse(status_code=200, body=body))

    with pytest.raises(ValueError, match="valid (JSON|success envelope)"):
        UpstoxV3IntradayClient(transport).fetch(
            IntradayRequest("NSE_EQ|INE002A01018"), AccessToken("test-token")
        )


@pytest.mark.parametrize(
    "candles",
    [
        {},
        [1],
        [[1, 2, 3]],
        [[1, 2, 3, 4, 5, 6, 7, 8]],
        [[1, 2, 3, 4, 5, 6, float("inf")]],
        [[1, 2, 3, 4, 5, 6, float("nan")]],
        [[1, 2, 3, 4, 5, 6, 7]] * 501,
    ],
)
def test_intraday_client_rejects_invalid_or_oversized_candle_arrays(
    candles: object,
) -> None:
    transport = RecordingTransport(_success(candles))

    with pytest.raises(ValueError, match="(valid JSON|candles array)"):
        UpstoxV3IntradayClient(transport).fetch(
            IntradayRequest("NSE_EQ|INE002A01018"), AccessToken("test-token")
        )


def test_intraday_client_preserves_raw_candle_types_for_downstream_validation() -> None:
    candles = [["2026-08-11T09:15:00+05:30", 1, 2.5, 0, 2, 100, None]]
    transport = RecordingTransport(_success(candles))

    response = UpstoxV3IntradayClient(transport).fetch(
        IntradayRequest("NSE_EQ|INE002A01018"), AccessToken("test-token")
    )

    assert response.candles == candles


def test_intraday_request_rejects_blank_instrument_key() -> None:
    with pytest.raises(ValueError, match="instrument_key"):
        IntradayRequest("  ")


def test_intraday_response_default_headers_and_invalid_envelopes_are_bounded() -> None:
    assert IntradayResponse(200, []).headers == HttpResponseHeaders()
    for body in (
        b"[]",
        b'{"status":"success","data":{"candles":[],"extra":null}}',
        b'{"status":"success","data":{"candles":["a\\\\b\\"c"]}}',
    ):
        with pytest.raises(
            ValueError, match="valid (JSON|success envelope|candles array)"
        ):
            UpstoxV3IntradayClient(RecordingTransport(HttpResponse(200, body))).fetch(
                IntradayRequest("NSE_EQ|INE002A01018"), AccessToken("test-token")
            )


@pytest.mark.parametrize(
    "error_type",
    [HttpResponseBodyTooLarge, HttpResponseHeadersInvalid],
)
def test_intraday_client_preserves_safe_transport_boundaries(
    error_type: type[Exception],
) -> None:
    transport = RaisingTransport(
        error_type("body-secret")
        if error_type is HttpResponseBodyTooLarge
        else error_type()
    )

    with pytest.raises(error_type) as raised:
        UpstoxV3IntradayClient(transport).fetch(
            IntradayRequest("NSE_EQ|INE002A01018"), AccessToken("test-token")
        )

    assert transport.calls == 1
    assert "body-secret" not in str(raised.value)
