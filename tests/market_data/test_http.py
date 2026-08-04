from __future__ import annotations

import gzip
import hashlib
import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from swing_trading_ai_assistant.market_data.http import (
    HttpResponseBodyTooLarge,
    HttpTransportError,
    ProviderErrorCategory,
    SameOriginAuthorizationRedirectHandler,
    UrllibHttpTransport,
)


class FakeResponse:
    status = 200

    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self._body = BytesIO(body)
        self.headers = Message()
        for name, value in (headers or {}).items():
            self.headers[name] = value

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _realistic_compressed_nse_catalog() -> bytes:
    """Build a deterministic, valid catalog comparable to the live gzip size."""
    records = [
        {
            "segment": "NSE_EQ" if index % 3 == 0 else "NSE_FO",
            "name": f"INSTRUMENT {_catalog_name(index)}",
            "exchange": "NSE",
            "isin": f"INE{index:06d}A01018",
            "instrument_type": "EQ" if index % 3 == 0 else "CE",
            "instrument_key": f"NSE_EQ|INE{index:06d}A01018",
            "trading_symbol": f"NSE{index:06d}",
        }
        for index in range(40_000)
    ]
    return gzip.compress(json.dumps(records, separators=(",", ":")).encode())


def _catalog_name(index: int) -> str:
    return hashlib.sha256(f"2026-08-04:{index}".encode()).hexdigest()


def test_transport_bounds_success_bodies_and_preserves_headers() -> None:
    transport = UrllibHttpTransport(
        max_body_bytes=3,
        opener=lambda request, timeout: FakeResponse(
            b"1234", {"X-Request-Id": "request-123"}
        ),
    )

    with pytest.raises(HttpResponseBodyTooLarge):
        transport.get("https://api.upstox.com/example", headers={})


def test_transport_sends_a_stable_application_user_agent() -> None:
    observed_requests: list[Request] = []

    def opener(request: Request, timeout: float) -> FakeResponse:
        observed_requests.append(request)
        return FakeResponse(b"{}")

    UrllibHttpTransport(opener=opener).get("https://api.upstox.com/example", headers={})

    assert len(observed_requests) == 1
    assert (
        observed_requests[0].get_header("User-agent") == "SwingTradingAIAssistant/0.1"
    )


def test_transport_preserves_an_explicit_caller_user_agent() -> None:
    observed_requests: list[Request] = []

    def opener(request: Request, timeout: float) -> FakeResponse:
        observed_requests.append(request)
        return FakeResponse(b"{}")

    UrllibHttpTransport(opener=opener).get(
        "https://api.upstox.com/example",
        headers={"user-agent": "caller/1.0"},
    )

    assert len(observed_requests) == 1
    assert observed_requests[0].get_header("User-agent") == "caller/1.0"


def test_default_transport_rejects_a_realistic_compressed_nse_catalog() -> None:
    catalog = _realistic_compressed_nse_catalog()
    assert len(catalog) > 1_900_000

    transport = UrllibHttpTransport(
        opener=lambda request, timeout: FakeResponse(
            catalog, {"Content-Length": str(len(catalog))}
        )
    )

    with pytest.raises(HttpResponseBodyTooLarge):
        transport.get("https://assets.upstox.com/market-quote/instruments", headers={})


def test_transport_bounds_http_error_bodies() -> None:
    def opener(request: Request, timeout: float) -> FakeResponse:
        raise HTTPError(
            request.full_url,
            429,
            "too many requests",
            Message(),
            BytesIO(b"1234"),
        )

    transport = UrllibHttpTransport(max_body_bytes=3, opener=opener)

    with pytest.raises(HttpResponseBodyTooLarge):
        transport.get("https://api.upstox.com/example", headers={})


def test_transport_returns_non_2xx_category_and_headers() -> None:
    def opener(request: Request, timeout: float) -> FakeResponse:
        headers = Message()
        headers["Retry-After"] = "12"
        headers["X-Request-Id"] = "request-123"
        raise HTTPError(
            request.full_url, 429, "too many requests", headers, BytesIO(b"{}")
        )

    response = UrllibHttpTransport(opener=opener).get(
        "https://api.upstox.com/example", headers={}
    )

    assert response.error_category is ProviderErrorCategory.RATE_LIMITED
    assert response.headers == {"Retry-After": "12", "X-Request-Id": "request-123"}


def test_transport_redacts_network_error_details() -> None:
    def opener(request: Request, timeout: float) -> FakeResponse:
        raise URLError("https://bad.example/?token=should-not-appear")

    with pytest.raises(HttpTransportError) as exc_info:
        UrllibHttpTransport(opener=opener).get(
            "https://api.upstox.com/example", headers={}
        )

    assert exc_info.value.category is ProviderErrorCategory.NETWORK
    assert "should-not-appear" not in str(exc_info.value)


def test_cross_origin_redirect_drops_authorization_but_same_origin_keeps_it() -> None:
    handler = SameOriginAuthorizationRedirectHandler()
    request = Request(
        "https://api.upstox.com/original",
        headers={"Authorization": "Bearer secret", "Accept": "application/json"},
    )

    cross_origin = handler.redirect_request(
        request, None, 302, "redirect", {}, "https://other.example/target"
    )
    same_origin = handler.redirect_request(
        request, None, 302, "redirect", {}, "https://api.upstox.com/target"
    )

    assert cross_origin is not None
    assert cross_origin.get_header("Authorization") is None
    assert same_origin is not None
    assert same_origin.get_header("Authorization") == "Bearer secret"
