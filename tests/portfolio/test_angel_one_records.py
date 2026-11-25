import json

import pytest
from credentials_fixture import TEST_API, TEST_CLIENT, TEST_MPIN, TEST_TOTP

from swing_trading_ai_assistant.portfolio import angel_one
from swing_trading_ai_assistant.portfolio.angel_one import (
    BASE_URL,
    GTT_LIST_PATH,
    LOGIN_PATH,
    ORDERS_PATH,
    POSITIONS_PATH,
    TRADES_PATH,
    AngelOneClient,
    AngelOneCredentials,
)
from swing_trading_ai_assistant.portfolio.errors import PortfolioError

_LOGIN = {"status": True, "data": {"jwtToken": "jwt-token"}}

_POSITIONS = {
    "status": True,
    "data": [
        {
            "tradingsymbol": "EXAMPLE1-EQ",
            "exchange": "NSE",
            "symboltoken": "1001",
            "producttype": "DELIVERY",
            "instrumenttype": "",
            "netqty": "10",
            "avgnetprice": "100.00",
            "ltp": "105.00",
            "pnl": "50.00",
            "unrealised": "50.00",
            "realised": "0",
            "multiplier": "1",
            "updateddate": "25-Nov-2026 10:00:00",
        }
    ],
}

_ORDERS = {
    "status": True,
    "data": [
        {
            "orderid": 201020000000080,
            "uniqueorderid": "order-uuid-1",
            "exchangeorderid": "1100000000048358",
            "tradingsymbol": "EXAMPLE1-EQ",
            "exchange": "NSE",
            "transactiontype": "BUY",
            "ordertype": "LIMIT",
            "producttype": "DELIVERY",
            "variety": "NORMAL",
            "orderstatus": "complete",
            "text": "",
            "quantity": "10",
            "filledshares": "10",
            "unfilledshares": "0",
            "price": "100.00",
            "triggerprice": "0",
            "averageprice": "100.50",
            "duration": "DAY",
            "updatetime": "25-Nov-2026 10:00:00",
        }
    ],
}

_TRADES = {
    "status": True,
    "data": [
        {
            "fillid": "50005750",
            "orderid": "201020000000095",
            "tradingsymbol": "EXAMPLE2-EQ",
            "exchange": "NSE",
            "transactiontype": "BUY",
            "producttype": "DELIVERY",
            "fillsize": "1",
            "fillprice": "175.00",
            "tradevalue": "175.00",
            "filltime": "13:27:53",
        }
    ],
}


def _gtt_row(rule_id: int, *, status: str | None = "NEW") -> dict[str, object]:
    return {
        "id": rule_id,
        "tradingsymbol": "EXAMPLE1",
        "exchange": "BSE",
        "symboltoken": "5001",
        "transactiontype": "SELL",
        "producttype": "DELIVERY",
        "gttType": "SINGLE",
        "qty": 5,
        "disclosedqty": 0,
        "price": 187.95,
        "triggerprice": 200.0,
        "stoplossprice": 0.0,
        "stoplosstriggerprice": 0.0,
        "status": status,
        "createddate": "2026-11-19T15:39:26.395+05:30",
        "updateddate": "2026-11-19T15:39:26.395+05:30",
        "expirydate": "2027-11-20T15:39:26.395+05:30",
    }


class FakeTransport:
    def __init__(
        self,
        *,
        positions=_POSITIONS,
        orders=_ORDERS,
        trades=_TRADES,
        gtt_pages: dict[int, dict[str, object]] | None = None,
    ) -> None:
        self.positions = positions
        self.orders = orders
        self.trades = trades
        self.gtt_pages = gtt_pages or {1: {"status": True, "data": [_gtt_row(1)]}}
        self.calls: list[tuple[str, str, bytes | None]] = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        if url.endswith(LOGIN_PATH):
            return 200, _LOGIN
        if url.endswith(POSITIONS_PATH):
            return 200, self.positions
        if url.endswith(ORDERS_PATH):
            return 200, self.orders
        if url.endswith(TRADES_PATH):
            return 200, self.trades
        if url.endswith(GTT_LIST_PATH):
            page = json.loads(body)["page"]
            return 200, self.gtt_pages[page]
        raise AssertionError(url)


def _client(transport: FakeTransport) -> AngelOneClient:
    return AngelOneClient(
        AngelOneCredentials(
            api_key=TEST_API,
            client_code=TEST_CLIENT,
            pin=TEST_MPIN,
            totp_secret=TEST_TOTP,
        ),
        transport=transport,
        clock=lambda: 1_800_000_000,
        public_ip="203.0.113.10",
        environ={},
    )


def _logged_in(transport: FakeTransport) -> AngelOneClient:
    client = _client(transport)
    client.login()
    return client


def test_positions_parse_broker_pnl() -> None:
    client = _logged_in(FakeTransport())
    snapshot = client.positions()
    assert len(snapshot.rows) == 1
    row = snapshot.rows[0]
    assert row.symbol == "EXAMPLE1-EQ"
    assert row.exchange == "NSE"
    assert row.symbol_token == "1001"  # noqa: S105 - synthetic token
    assert row.quantity == 10
    assert row.average_price == 100
    assert row.last_price == 105
    assert row.pnl == 50
    assert row.pnl_pct == 5
    assert row.pnl_source == "BROKER"
    assert snapshot.limitations == ()


def test_positions_derive_pnl_from_ltp() -> None:
    payload = {
        "status": True,
        "data": [
            {
                "tradingsymbol": "EXAMPLE1-EQ",
                "exchange": "NSE",
                "producttype": "DELIVERY",
                "netqty": "10",
                "avgnetprice": "100.00",
                "ltp": "105.00",
            }
        ],
    }
    snapshot = _logged_in(FakeTransport(positions=payload)).positions()
    row = snapshot.rows[0]
    assert row.pnl == 50
    assert row.pnl_source == "DERIVED"
    assert "POSITION_PNL_DERIVED_FROM_LTP" in snapshot.limitations


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("netqty", "1e100000"),
        ("netqty", "1e1000000"),
        ("netqty", "1e-1000000000"),
        ("avgnetprice", "1e500000"),
        ("ltp", "1e-100000"),
    ],
)
def test_extreme_position_numerics_fail_closed(field: str, value: str) -> None:
    row = dict(_POSITIONS["data"][0], **{field: value})
    with pytest.raises(PortfolioError) as error:
        _logged_in(FakeTransport(positions={"status": True, "data": [row]})).positions()
    assert error.value.code == "MALFORMED_RESPONSE"


def test_missing_data_is_malformed() -> None:
    with pytest.raises(PortfolioError) as error:
        _logged_in(FakeTransport(positions={"status": True})).positions()
    assert error.value.code == "MALFORMED_RESPONSE"


def test_blank_optional_position_numerics_are_absent() -> None:
    row = dict(
        _POSITIONS["data"][0],
        pnl="",
        unrealised="",
        realised="",
        multiplier="",
    )
    snapshot = _logged_in(
        FakeTransport(positions={"status": True, "data": [row]})
    ).positions()
    data = snapshot.rows[0]
    assert data.pnl_source == "DERIVED"
    assert data.realised_pnl is None
    assert data.unrealised_pnl is None
    assert data.multiplier is None


def test_non_ascii_symbol_rejected_before_uppercase() -> None:
    row = dict(_POSITIONS["data"][0], tradingsymbol="ß")
    with pytest.raises(PortfolioError) as error:
        _logged_in(FakeTransport(positions={"status": True, "data": [row]})).positions()
    assert error.value.code == "MALFORMED_RESPONSE"


def test_non_equity_without_ltp_still_flags_derivation_unsupported() -> None:
    row = dict(
        _POSITIONS["data"][0],
        instrumenttype="FUT",
        ltp=None,
        pnl=None,
        unrealised=None,
    )
    snapshot = _logged_in(
        FakeTransport(positions={"status": True, "data": [row]})
    ).positions()
    assert "POSITION_PNL_UNAVAILABLE" in snapshot.limitations
    assert "POSITION_PNL_DERIVATION_UNSUPPORTED" in snapshot.limitations
    assert "POSITION_LTP_UNAVAILABLE" in snapshot.limitations


def test_non_equity_position_pnl_is_not_derived() -> None:
    payload = {
        "status": True,
        "data": [
            {
                "tradingsymbol": "EXAMPLE1-FUT",
                "exchange": "NFO",
                "producttype": "CARRYFORWARD",
                "instrumenttype": "FUT",
                "netqty": "1",
                "avgnetprice": "100.00",
                "ltp": "105.00",
            }
        ],
    }
    snapshot = _logged_in(FakeTransport(positions=payload)).positions()
    assert snapshot.rows[0].pnl is None
    assert "POSITION_PNL_DERIVATION_UNSUPPORTED" in snapshot.limitations


def test_positions_without_ltp_or_pnl_are_explicit() -> None:
    payload = {
        "status": True,
        "data": [
            {
                "tradingsymbol": "EXAMPLE1-EQ",
                "exchange": "NSE",
                "producttype": "DELIVERY",
                "netqty": "10",
                "avgnetprice": "100.00",
            }
        ],
    }
    snapshot = _logged_in(FakeTransport(positions=payload)).positions()
    row = snapshot.rows[0]
    assert row.pnl is None
    assert row.pnl_source is None
    assert "POSITION_PNL_UNAVAILABLE" in snapshot.limitations
    assert "POSITION_LTP_UNAVAILABLE" in snapshot.limitations


def test_null_data_is_an_empty_section() -> None:
    empty = {"status": True, "data": None}
    transport = FakeTransport(positions=empty, orders=empty, trades=empty)
    client = _logged_in(transport)
    assert client.positions().rows == ()
    assert client.orders().rows == ()
    assert client.trades().rows == ()


def test_orders_parse_status_and_ids() -> None:
    snapshot = _logged_in(FakeTransport()).orders()
    row = snapshot.rows[0]
    assert row.order_id == "order-uuid-1"
    assert row.exchange_order_id == "1100000000048358"
    assert row.side == "BUY"
    assert row.status == "COMPLETE"
    assert row.trigger_price is None
    assert row.average_fill_price == 100.5
    assert row.reported_at == "25-Nov-2026 10:00:00"


def test_order_falls_back_to_orderid_and_keeps_exchange_id() -> None:
    row = dict(_ORDERS["data"][0])
    row.pop("uniqueorderid")
    snapshot = _logged_in(
        FakeTransport(orders={"status": True, "data": [row]})
    ).orders()
    assert snapshot.rows[0].order_id == "201020000000080"
    assert snapshot.rows[0].exchange_order_id == "1100000000048358"


def test_float_order_id_rejected() -> None:
    row = dict(_ORDERS["data"][0], uniqueorderid=float("nan"))
    with pytest.raises(PortfolioError) as error:
        _logged_in(FakeTransport(orders={"status": True, "data": [row]})).orders()
    assert error.value.code == "MALFORMED_RESPONSE"


def test_order_status_message_allows_currency_but_not_controls() -> None:
    payload = {
        "status": True,
        "data": [dict(_ORDERS["data"][0], text="Rejected: ₹ shortfall")],
    }
    snapshot = _logged_in(FakeTransport(orders=payload)).orders()
    assert snapshot.rows[0].status_message == "Rejected: ₹ shortfall"
    unsafe = {
        "status": True,
        "data": [dict(_ORDERS["data"][0], text="bad\nmessage")],
    }
    with pytest.raises(PortfolioError) as error:
        _logged_in(FakeTransport(orders=unsafe)).orders()
    assert error.value.code == "MALFORMED_RESPONSE"


def test_trades_parse_and_compute_missing_value() -> None:
    payload = {
        "status": True,
        "data": [dict(_TRADES["data"][0], tradevalue=None)],
    }
    snapshot = _logged_in(FakeTransport(trades=payload)).trades()
    row = snapshot.rows[0]
    assert row.trade_id == "50005750"
    assert row.trade_value == 175
    assert "TRADE_VALUE_COMPUTED" in snapshot.limitations


def test_gtt_rules_parse_and_flag_missing_status() -> None:
    payload = {"status": True, "data": [_gtt_row(1, status=None)]}
    snapshot = _logged_in(FakeTransport(gtt_pages={1: payload})).gtt_rules()
    row = snapshot.rows[0]
    assert row.rule_id == "1"
    assert row.symbol == "EXAMPLE1"
    assert row.exchange == "BSE"
    assert row.gtt_type == "SINGLE"
    assert row.stoploss_price is None
    assert row.status is None
    assert "GTT_STATUS_UNAVAILABLE" in snapshot.limitations


def test_gtt_rules_paginate() -> None:
    first = [_gtt_row(index) for index in range(1, 51)]
    second = [_gtt_row(51)]
    transport = FakeTransport(
        gtt_pages={
            1: {"status": True, "data": first},
            2: {"status": True, "data": second},
        }
    )
    snapshot = _logged_in(transport).gtt_rules()
    assert len(snapshot.rows) == 51
    gtt_calls = [call for call in transport.calls if call[1].endswith(GTT_LIST_PATH)]
    assert len(gtt_calls) == 2
    assert json.loads(gtt_calls[0][2])["page"] == 1
    assert json.loads(gtt_calls[1][2])["page"] == 2


def test_gtt_page_bound_flags_truncation() -> None:
    page_rows = [_gtt_row(1_000 + index) for index in range(50)]
    pages = {
        page: {"status": True, "data": page_rows}
        for page in range(1, angel_one.MAX_GTT_PAGES + 1)
    }
    snapshot = _logged_in(FakeTransport(gtt_pages=pages)).gtt_rules()
    assert len(snapshot.rows) == 1_000
    assert "GTT_RESULTS_TRUNCATED" in snapshot.limitations


def test_malformed_records_fail_closed() -> None:
    position = {
        "status": True,
        "data": [
            {
                "tradingsymbol": "",
                "exchange": "NSE",
                "producttype": "DELIVERY",
                "netqty": "1",
                "avgnetprice": "1",
            }
        ],
    }
    with pytest.raises(PortfolioError) as error:
        _logged_in(FakeTransport(positions=position)).positions()
    assert error.value.code == "MALFORMED_RESPONSE"

    order = {
        "status": True,
        "data": [dict(_ORDERS["data"][0], quantity="-1")],
    }
    with pytest.raises(PortfolioError) as error:
        _logged_in(FakeTransport(orders=order)).orders()
    assert error.value.code == "MALFORMED_RESPONSE"

    trade = {
        "status": True,
        "data": [dict(_TRADES["data"][0], fillid="")],
    }
    with pytest.raises(PortfolioError) as error:
        _logged_in(FakeTransport(trades=trade)).trades()
    assert error.value.code == "MALFORMED_RESPONSE"


def test_only_read_endpoints_are_allowlisted() -> None:
    read_paths = (
        LOGIN_PATH,
        angel_one.HOLDINGS_PATH,
        POSITIONS_PATH,
        ORDERS_PATH,
        TRADES_PATH,
        GTT_LIST_PATH,
    )
    for path in read_paths:
        assert f"{BASE_URL}{path}" in angel_one.ALLOWED_URLS
    forbidden = (
        "/rest/secure/angelbroking/order/v1/placeOrder",
        "/rest/secure/angelbroking/order/v1/modifyOrder",
        "/rest/secure/angelbroking/order/v1/cancelOrder",
        "/rest/secure/angelbroking/order/v1/convertPosition",
        "/rest/secure/angelbroking/gtt/v1/createRule",
        "/rest/secure/angelbroking/gtt/v1/modifyRule",
        "/rest/secure/angelbroking/gtt/v1/cancelRule",
    )
    for path in forbidden:
        url = f"{BASE_URL}{path}"
        assert url not in angel_one.ALLOWED_URLS
        with pytest.raises(PortfolioError) as error:
            angel_one._default_transport("POST", url, {}, b"{}")
        assert error.value.code == "PROVIDER_UNAVAILABLE"
