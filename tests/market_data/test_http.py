from __future__ import annotations

import gzip
import hashlib
import json
import threading
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from swing_trading_ai_assistant.market_data.http import (
    HttpResponseBodyTooLarge,
    HttpResponseHeaders,
    HttpResponseHeadersInvalid,
    HttpTransportError,
    ProviderErrorCategory,
    SameOriginAuthorizationRedirectHandler,
    UrllibHttpTransport,
)


class HeaderItems:
    def __init__(self, items: list[tuple[object, object]]) -> None:
        self._items = items

    def items(self) -> list[tuple[object, object]]:
        return self._items


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
    assert response.headers.items() == (
        ("Retry-After", "12"),
        ("X-Request-Id", "request-123"),
    )


def test_transport_preserves_ordered_repeated_headers_and_lookup_is_case_insensitive() -> (
    None
):
    response_headers = HeaderItems(
        [
            ("X-Trace", "first"),
            ("retry-after", "1"),
            ("x-trace", "second"),
        ]
    )

    response = UrllibHttpTransport(
        opener=lambda request, timeout: _response_with_headers(response_headers)
    ).get("https://api.upstox.com/example", headers={})

    assert response.headers.items() == (
        ("X-Trace", "first"),
        ("retry-after", "1"),
        ("x-trace", "second"),
    )
    assert response.headers.get_all("X-TRACE") == ("first", "second")
    assert response.headers.get_single("RETRY-AFTER") == "1"
    assert response.headers.get_single("x-trace") is None


@pytest.mark.parametrize(
    ("items", "expected_error"),
    [
        ([("X" * 256, "exact")], None),
        ([("X" * 257, "too-long")], HttpResponseHeadersInvalid),
        ([("X-Value", "v" * 4_096)], None),
        ([("X-Value", "v" * 4_097)], HttpResponseHeadersInvalid),
        ([(f"X-{index}", "value") for index in range(128)], None),
        ([(f"X-{index}", "value") for index in range(129)], HttpResponseHeadersInvalid),
    ],
)
def test_transport_enforces_exact_header_bounds(
    items: list[tuple[object, object]],
    expected_error: type[Exception] | None,
) -> None:
    transport = UrllibHttpTransport(
        opener=lambda request, timeout: _response_with_headers(HeaderItems(items))
    )

    if expected_error is None:
        response = transport.get("https://api.upstox.com/example", headers={})
        assert len(response.headers) == len(items)
    else:
        with pytest.raises(expected_error):
            transport.get("https://api.upstox.com/example", headers={})


@pytest.mark.parametrize(
    ("items", "expected_error"),
    [
        ([("X-Obs-Text", "\xff" * 4_096)], None),
        ([("X-Tab", "one\ttwo")], None),
        ([("X-Value", "euro-\u20ac")], HttpResponseHeadersInvalid),
        ([("X-\xe9", "value")], HttpResponseHeadersInvalid),
    ],
)
def test_transport_enforces_exact_latin_1_header_grammar(
    items: list[tuple[object, object]],
    expected_error: type[Exception] | None,
) -> None:
    transport = UrllibHttpTransport(
        opener=lambda request, timeout: _response_with_headers(HeaderItems(items))
    )

    if expected_error is None:
        response = transport.get("https://api.upstox.com/example", headers={})
        assert response.headers.items() == tuple(items)
    else:
        with pytest.raises(expected_error):
            transport.get("https://api.upstox.com/example", headers={})


@pytest.mark.parametrize(
    "items",
    [
        [("", "value")],
        [("X Invalid", "value")],
        [("X-Name", "value\r\nInjected: yes")],
        [("X-Name", "value\x00")],
        [("X-Name", "value\x7f")],
        [("Bad Name", "Bearer secret")],
        [("X-Name", object())],
        [(object(), "value")],
        [("X-Name", "value", "extra")],
    ],
)
def test_transport_rejects_invalid_header_structure_with_one_sanitized_error(
    items: list[tuple[object, ...]],
) -> None:
    transport = UrllibHttpTransport(
        opener=lambda request, timeout: _response_with_headers(
            HeaderItems(items),
            body=b"response-body-secret",
        )  # type: ignore[arg-type]
    )

    with pytest.raises(HttpResponseHeadersInvalid) as exc_info:
        transport.get("https://api.upstox.com/example", headers={})

    assert (
        str(exc_info.value) == "market-data provider response contained invalid headers"
    )
    assert "Bearer secret" not in str(exc_info.value)
    assert "response-body-secret" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_response_headers_are_immutable_and_copy_input_arrival_order() -> None:
    items = [["X-Test", "before"]]
    headers = HttpResponseHeaders.from_items(items)
    items[0][1] = "after"

    assert headers.items() == (("X-Test", "before"),)
    with pytest.raises(AttributeError):
        headers.fields = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        headers.fields[0] = headers.fields[0]  # type: ignore[index]


def _response_with_headers(
    headers: HeaderItems, *, body: bytes = b"{}"
) -> FakeResponse:
    response = FakeResponse(body)
    response.headers = headers
    return response


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


def test_real_cross_origin_redirect_never_forwards_authorization() -> None:
    received_authorization: list[str | None] = []

    class TargetHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            received_authorization.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_: object) -> None:
            return None

    target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
    target_url = f"http://127.0.0.1:{target.server_port}/target"

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", target_url)
            self.end_headers()

        def log_message(self, *_: object) -> None:
            return None

    source = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    threads = tuple(
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in (source, target)
    )
    for thread in threads:
        thread.start()
    try:
        response = UrllibHttpTransport(timeout_seconds=2).get(
            f"http://127.0.0.1:{source.server_port}/source",
            headers={"Authorization": "Bearer fake-test-token"},
        )
    finally:
        for server in (source, target):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)

    assert response.status_code == 200
    assert received_authorization == [None]
