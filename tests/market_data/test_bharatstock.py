from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

from swing_trading_ai_assistant.market_data import bharatstock
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockError,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.http import (
    HttpResponse,
    HttpResponseBodyTooLarge,
)

_MEMBER = BharatStockInstrument("INE002A01018", "NSE", "RELIANCE")
_START = date(2026, 8, 27)
_END = date(2026, 8, 28)


def _row(session: str, factor: float = 0.5) -> dict[str, object]:
    return {
        "trade_date": session,
        "open": 100,
        "high": 104,
        "low": 98,
        "close": 102,
        "volume": 1000,
        "adjusted_close": 102 * factor,
        "adjustment_factor": factor,
    }


def _identity() -> HttpResponse:
    return HttpResponse(
        200,
        json.dumps(
            {
                "isin": _MEMBER.isin,
                "exchange": "NSE",
                "symbol": "RELIANCE",
            }
        ).encode(),
    )


def _page(rows: list[dict[str, object]], **overrides: int) -> HttpResponse:
    pagination = {
        "page": 1,
        "page_size": 1000,
        "total_items": len(rows),
        "total_pages": 1,
    }
    pagination.update(overrides)
    return HttpResponse(
        200, json.dumps({"data": rows, "pagination": pagination}).encode()
    )


class _Transport:
    def __init__(self, *responses: HttpResponse) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        self.urls.append(url)
        return self.responses.pop(0)


def test_preserves_supplied_prices_and_non_unit_factor_with_inclusive_dates() -> None:
    transport = _Transport(_identity(), _page([_row("2026-08-28"), _row("2026-08-27")]))
    result = BharatStockClient(api_key="test-key", transport=transport).history(
        _MEMBER, _START, _END
    )
    assert tuple(row.session for row in result.rows) == (_START, _END)
    assert result.rows[0].close == Decimal("102")
    assert result.rows[0].adjusted_close == Decimal("51")
    assert result.rows[0].adjustment_factor == Decimal("0.5")
    assert (result.rows[0].open, result.rows[0].high, result.rows[0].low) == (
        Decimal(100),
        Decimal(104),
        Decimal(98),
    )
    assert result.rows[0].volume == 1000
    assert result.request_count == 2
    assert "from=2026-08-27" in transport.urls[1]
    assert "to=2026-08-28" in transport.urls[1]
    assert all(
        "/INE002A01018" in url and "exchange=NSE" in url for url in transport.urls
    )


def test_optional_adjustment_fields_do_not_block_as_provided_history() -> None:
    row = {**_row("2026-08-27"), "adjusted_close": None, "adjustment_factor": None}
    client = BharatStockClient(
        api_key="test-key", transport=_Transport(_identity(), _page([row]))
    )
    price = client.history(_MEMBER, _START, _END).rows[0]
    assert (price.open, price.high, price.low, price.close) == (
        Decimal(100),
        Decimal(104),
        Decimal(98),
        Decimal(102),
    )
    assert price.adjusted_close is None
    assert price.adjustment_factor is None


def test_retains_conflicting_adjustment_fields_without_changing_source_prices() -> None:
    row = {**_row("2026-08-27"), "adjusted_close": 52}
    client = BharatStockClient(
        api_key="test-key", transport=_Transport(_identity(), _page([row]))
    )
    price = client.history(_MEMBER, _START, _END).rows[0]
    assert price.close == Decimal(102)
    assert price.adjusted_close == Decimal(52)
    assert price.adjustment_factor == Decimal("0.5")


def test_invalid_member_does_not_poison_later_member_acquisition() -> None:
    broken = _row("2026-08-27")
    broken["close"] = None
    transport = _Transport(
        _identity(), _page([broken]), _identity(), _page([_row("2026-08-28")])
    )
    client = BharatStockClient(api_key="test-key", transport=transport)
    with pytest.raises(BharatStockError) as error:
        client.history(_MEMBER, _START, _END)
    assert error.value.member_local
    assert client.history(_MEMBER, _START, _END).rows[0].session == _END
    assert client.requests_used == 4


def test_rate_limit_is_sticky_and_never_retried() -> None:
    transport = _Transport(_identity(), HttpResponse(429, b"{}"), _identity())
    client = BharatStockClient(api_key="test-key", transport=transport)
    for _ in range(2):
        with pytest.raises(BharatStockError) as error:
            client.history(_MEMBER, _START, _END)
        assert not error.value.member_local
        assert error.value.category == "RATE_LIMITED"
    assert client.requests_used == 2
    assert len(transport.responses) == 1


@pytest.mark.parametrize(
    "rows",
    [
        [_row("2026-08-27"), _row("2026-08-27")],
        [_row("2026-08-26")],
        [{**_row("2026-08-27"), "volume": True}],
    ],
)
def test_invalid_price_evidence_is_member_local(rows: list[dict[str, object]]) -> None:
    client = BharatStockClient(
        api_key="test-key", transport=_Transport(_identity(), _page(rows))
    )
    with pytest.raises(BharatStockError) as error:
        client.history(_MEMBER, _START, _END)
    assert error.value.member_local


def test_exhausted_request_budget_stops_before_next_http_effect() -> None:
    transport = _Transport(_identity(), _page([_row("2026-08-27")]))
    client = BharatStockClient(api_key="test-key", transport=transport, max_requests=1)
    with pytest.raises(BharatStockError) as error:
        client.history(_MEMBER, _START, _END)
    assert error.value.category == "REQUEST_BUDGET_EXHAUSTED"
    assert not error.value.member_local
    assert client.requests_used == 1


def test_rejects_incoherent_pagination_instead_of_truncating_history() -> None:
    transport = _Transport(_identity(), _page([_row("2026-08-27")], total_items=2))
    client = BharatStockClient(api_key="test-key", transport=transport)
    with pytest.raises(BharatStockError) as error:
        client.history(_MEMBER, _START, _END)
    assert error.value.category == "PAGINATION_INVALID"
    assert error.value.member_local


def test_history_spans_pages_without_losing_boundary_row() -> None:
    start = date(2020, 1, 1)
    end = start + timedelta(days=1000)
    rows = [_row((end - timedelta(days=index)).isoformat()) for index in range(1001)]
    transport = _Transport(
        _identity(),
        _page(rows[:1000], total_items=1001, total_pages=2),
        _page(rows[1000:], page=2, total_items=1001, total_pages=2),
    )
    result = BharatStockClient(api_key="test-key", transport=transport).history(
        _MEMBER, start, end
    )
    assert tuple(row.session for row in result.rows) == tuple(
        start + timedelta(days=index) for index in range(1001)
    )
    assert result.request_count == 3


def test_effect_guard_stops_before_a_later_price_page() -> None:
    start = date(2020, 1, 1)
    end = start + timedelta(days=1000)
    rows = [_row((end - timedelta(days=index)).isoformat()) for index in range(1001)]
    transport = _Transport(
        _identity(),
        _page(rows[:1000], total_items=1001, total_pages=2),
        _page(rows[1000:], page=2, total_items=1001, total_pages=2),
    )
    guard_loss = RuntimeError("effect authority lost")

    def guard() -> None:
        if len(transport.urls) == 2:
            raise guard_loss

    with pytest.raises(RuntimeError) as raised:
        BharatStockClient(api_key="test-key", transport=transport).history(
            _MEMBER, start, end, effect_guard=guard
        )
    assert raised.value is guard_loss
    assert len(transport.urls) == 2


def test_guard_failure_after_credentials_is_not_a_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BHARATSTOCK_API_KEY", "synthetic-test-key")
    read_environment = bharatstock.os.environ.get
    credential_read = False
    failure = HttpResponseBodyTooLarge("guard failure")
    transport = _Transport()

    def environment(key, default=None):
        nonlocal credential_read
        if key == "BHARATSTOCK_API_KEY":
            credential_read = True
        return read_environment(key, default)

    def guard() -> None:
        if credential_read:
            raise failure

    monkeypatch.setattr(bharatstock.os.environ, "get", environment)
    with pytest.raises(HttpResponseBodyTooLarge) as raised:
        BharatStockClient(transport=transport).history(
            _MEMBER, _START, _END, effect_guard=guard
        )
    assert raised.value is failure
    assert transport.urls == []


def test_default_transport_does_not_follow_authenticated_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            observed.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/credential-target")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Redirect)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        monkeypatch.setattr(
            bharatstock, "_BASE", f"http://127.0.0.1:{server.server_port}/v1/stocks/"
        )
        client = BharatStockClient(api_key="test-key")
        with pytest.raises(BharatStockError) as error:
            client.history(_MEMBER, _START, _END)
        assert error.value.category == "REDIRECT_REJECTED"
        assert not error.value.member_local
        assert observed == ["/v1/stocks/INE002A01018?exchange=NSE"]
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()


def test_one_client_does_not_rotate_accounts_when_environment_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BHARATSTOCK_API_KEY", "first-synthetic-key")
    keys: list[str] = []

    class ChangingEnvironment(_Transport):
        def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
            keys.append(headers["X-API-Key"])
            monkeypatch.setenv("BHARATSTOCK_API_KEY", "second-synthetic-key")
            return super().get(url, headers)

    client = BharatStockClient(
        transport=ChangingEnvironment(
            _identity(),
            _page([_row("2026-08-28")]),
        )
    )
    client.history(_MEMBER, _START, _END)
    assert keys == ["first-synthetic-key", "first-synthetic-key"]
