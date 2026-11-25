import io
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from credentials_fixture import (
    TEST_API,
    TEST_CLIENT,
    TEST_MPIN,
    TEST_RFC_TOTP,
    TEST_TOTP,
)

from swing_trading_ai_assistant.portfolio import angel_one
from swing_trading_ai_assistant.portfolio.angel_one import (
    BASE_URL,
    HOLDINGS_PATH,
    LOGIN_PATH,
    AngelOneClient,
    AngelOneCredentials,
    HoldingsSnapshot,
    generate_totp,
    load_credentials,
    review_payload,
)
from swing_trading_ai_assistant.portfolio.errors import PortfolioError

_NOW = datetime(2026, 11, 23, 12, 35, tzinfo=UTC)
_ENV = {
    "ANGEL_ONE_API_KEY": TEST_API,
    "ANGEL_ONE_CLIENT_CODE": TEST_CLIENT,
    "ANGEL_ONE_PIN": TEST_MPIN,
    "ANGEL_ONE_TOTP_SECRET": TEST_TOTP,
}
_LOGIN = {"status": True, "data": {"jwtToken": "jwt-token"}}
_HOLDINGS = {
    "status": True,
    "data": {
        "holdings": [
            {
                "tradingsymbol": "EXAMPLE1",
                "quantity": "10",
                "t1quantity": "0",
                "averageprice": "100.00",
                "ltp": "105.00",
                "close": "104.00",
                "profitandloss": "50.00",
            },
            {
                "tradingsymbol": "EXAMPLE2",
                "quantity": "20",
                "t1quantity": "0",
                "averageprice": "200.00",
                "ltp": "210.00",
                "close": "208.00",
                "profitandloss": "200.00",
            },
        ],
        "totalholding": {
            "totalinvvalue": "5000.00",
            "totalholdingvalue": "5250.00",
            "totalprofitandloss": "250.00",
        },
    },
}


class FakeTransport:
    def __init__(
        self,
        login: tuple[int, dict[str, object]] = (200, _LOGIN),
        holdings: tuple[int, dict[str, object]] = (200, _HOLDINGS),
    ) -> None:
        self.login = login
        self.holdings = holdings
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        if url.endswith(LOGIN_PATH):
            return self.login
        if url.endswith(HOLDINGS_PATH):
            return self.holdings
        raise AssertionError(url)


def _credentials() -> AngelOneCredentials:
    return AngelOneCredentials(
        api_key=TEST_API,
        client_code=TEST_CLIENT,
        pin=TEST_MPIN,
        totp_secret=TEST_TOTP,
    )


def _client(transport: FakeTransport) -> AngelOneClient:
    return AngelOneClient(
        _credentials(),
        transport=transport,
        clock=_NOW.timestamp,
        public_ip="203.0.113.10",
        environ={},
    )


def test_totp_matches_rfc_vector() -> None:
    assert generate_totp(TEST_RFC_TOTP, at=59) == "287082"


def test_load_credentials_and_missing() -> None:
    credentials = load_credentials("ANGEL_ONE", _ENV)
    assert credentials.client_code == "CLIENT1"
    with pytest.raises(PortfolioError) as error:
        load_credentials("ANGEL_ONE", {})
    assert error.value.code == "CREDENTIALS_MISSING"
    assert "ANGEL_ONE_API_KEY" in error.value.message


def test_login_and_holdings_review() -> None:
    transport = FakeTransport()
    client = _client(transport)
    client.login()
    snapshot = client.holdings()
    assert transport.calls == [
        ("POST", f"{BASE_URL}{LOGIN_PATH}"),
        ("GET", f"{BASE_URL}{HOLDINGS_PATH}"),
    ]
    assert snapshot.invested == Decimal("5000.00")
    assert snapshot.current == Decimal("5250.00")
    assert snapshot.overall_pnl == Decimal("250.00")
    assert snapshot.overall_pnl_pct == Decimal("5.00")
    assert snapshot.day_change == Decimal("50.00")
    payload = review_payload("angel-main", "ANGEL_ONE", snapshot)
    summary = cast("dict[str, object]", payload["summary"])
    assert summary["holdings"] == 2
    assert summary["current"] == 5250.0
    assert summary["top_holding_weight_pct"] == 80.0
    assert payload["limitations"] == [
        "BROKER_READ_ONLY",
        "POINT_IN_TIME_SNAPSHOT",
    ]
    assert "USER_SUPPLIED_UNVERIFIED" not in payload["limitations"]


@pytest.mark.parametrize(
    ("login", "code"),
    [
        ((401, {"status": False, "message": "invalid"}), "AUTH_FAILED"),
        (
            (200, {"status": False, "message": "IP not whitelisted"}),
            "IP_NOT_WHITELISTED",
        ),
        ((200, {"status": True, "data": {}}), "MALFORMED_RESPONSE"),
    ],
)
def test_login_failures(login, code: str) -> None:
    transport = FakeTransport(login=login)
    with pytest.raises(PortfolioError) as error:
        _client(transport).login()
    assert error.value.code == code


def test_holdings_requires_login() -> None:
    with pytest.raises(PortfolioError) as error:
        _client(FakeTransport()).holdings()
    assert error.value.code == "AUTH_FAILED"


def test_holdings_auth_failure() -> None:
    transport = FakeTransport(holdings=(403, {"status": False}))
    client = _client(transport)
    client.login()
    with pytest.raises(PortfolioError) as error:
        client.holdings()
    assert error.value.code == "AUTH_FAILED"


def test_reconciliation_mismatch() -> None:
    payload = {
        "status": True,
        "data": {
            "holdings": _HOLDINGS["data"]["holdings"],
            "totalholding": {
                "totalinvvalue": "999999.00",
                "totalholdingvalue": "5250.00",
                "totalprofitandloss": "250.00",
            },
        },
    }
    client = _client(FakeTransport(holdings=(200, payload)))
    client.login()
    with pytest.raises(PortfolioError) as error:
        client.holdings()
    assert error.value.code == "RECONCILIATION_MISMATCH"


def test_extreme_holdings_total_fails_closed() -> None:
    payload = {
        "status": True,
        "data": {
            "holdings": _HOLDINGS["data"]["holdings"],
            "totalholding": {
                "totalinvvalue": "1e1000000",
                "totalholdingvalue": "5250.00",
                "totalprofitandloss": "250.00",
            },
        },
    }
    client = _client(FakeTransport(holdings=(200, payload)))
    client.login()
    with pytest.raises(PortfolioError) as error:
        client.holdings()
    assert error.value.code == "MALFORMED_RESPONSE"


def test_missing_previous_close_and_t1_limitations() -> None:
    holdings = [dict(row) for row in _HOLDINGS["data"]["holdings"]]
    holdings[0].pop("close")
    holdings[1]["t1quantity"] = "5"
    payload = {
        "status": True,
        "data": {"holdings": holdings},
    }
    client = _client(FakeTransport(holdings=(200, payload)))
    client.login()
    snapshot = client.holdings()
    assert "DAY_CHANGE_UNAVAILABLE" in snapshot.limitations
    assert "T1_QUANTITY_PRESENT" in snapshot.limitations
    assert "TOTAL_NOT_PROVIDED" in snapshot.limitations


def test_malformed_holding_rejected() -> None:
    payload = {
        "status": True,
        "data": {"holdings": [{"tradingsymbol": "", "quantity": "1"}]},
    }
    client = _client(FakeTransport(holdings=(200, payload)))
    client.login()
    with pytest.raises(PortfolioError) as error:
        client.holdings()
    assert error.value.code == "MALFORMED_RESPONSE"


def test_totp_invalid_secret() -> None:
    with pytest.raises(PortfolioError) as error:
        generate_totp("not-base32!")
    assert error.value.code == "MALFORMED_CREDENTIAL"


def test_credentials_repr_is_redacted() -> None:
    assert TEST_CLIENT not in repr(_credentials())
    assert TEST_API not in repr(_credentials())


def test_public_ip_env_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORTFOLIO_PUBLIC_IP", "198.51.100.7")
    client = AngelOneClient(
        _credentials(), environ={"PORTFOLIO_PUBLIC_IP": "198.51.100.7"}
    )
    headers = client._headers()
    assert headers["X-ClientPublicIP"] == "198.51.100.7"
    assert headers["X-PrivateKey"] == TEST_API


def test_holdings_list_without_totals() -> None:
    payload = {
        "status": True,
        "data": [_HOLDINGS["data"]["holdings"][0]],
    }
    client = _client(FakeTransport(holdings=(200, payload)))
    client.login()
    snapshot = client.holdings()
    assert "TOTAL_NOT_PROVIDED" in snapshot.limitations


def test_partial_totals_limitation() -> None:
    payload = {
        "status": True,
        "data": {
            "holdings": _HOLDINGS["data"]["holdings"],
            "totalholding": {"totalinvvalue": "5000.00"},
        },
    }
    client = _client(FakeTransport(holdings=(200, payload)))
    client.login()
    assert "TOTAL_PARTIAL" in client.holdings().limitations


@pytest.mark.parametrize(
    "data",
    [
        "bad",
        {},
        {"holdings": "bad"},
        {"holdings": [], "totalholding": "bad"},
    ],
)
def test_malformed_holdings_payloads(data) -> None:
    client = _client(FakeTransport(holdings=(200, {"status": True, "data": data})))
    client.login()
    with pytest.raises(PortfolioError) as error:
        client.holdings()
    assert error.value.code == "MALFORMED_RESPONSE"


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": "-1"},
        {"ltp": "0"},
        {"averageprice": "bad"},
        {"quantity": "bad"},
        {"profitandloss": "bad"},
    ],
)
def test_invalid_row_values(changes) -> None:
    row = dict(_HOLDINGS["data"]["holdings"][0])
    row.update(changes)
    payload = {"status": True, "data": {"holdings": [row]}}
    client = _client(FakeTransport(holdings=(200, payload)))
    client.login()
    with pytest.raises(PortfolioError) as error:
        client.holdings()
    assert error.value.code == "MALFORMED_RESPONSE"


def test_empty_snapshot_review_has_no_top_weight() -> None:
    snapshot = HoldingsSnapshot(
        rows=(),
        invested=Decimal("0"),
        current=Decimal("0"),
        overall_pnl=Decimal("0"),
        overall_pnl_pct=None,
        day_change=None,
        day_change_pct=None,
        limitations=("DAY_CHANGE_UNAVAILABLE",),
        retrieved_at="2026-11-23T12:35:00+00:00",
    )
    payload = review_payload("angel-main", "ANGEL_ONE", snapshot)
    summary = cast("dict[str, object]", payload["summary"])
    assert summary["top_holding_weight_pct"] is None
    assert summary["holdings"] == 0


class _Response:
    status = 200

    def __init__(self, payload: bytes, url: str = "") -> None:
        self.payload = payload
        self.url = url

    def read(self, _size: int = -1) -> bytes:
        return self.payload

    def geturl(self) -> str:
        return self.url

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args) -> None:
        return None


class _FakeOpener:
    def __init__(self, response=None, error=None) -> None:
        self.response = response
        self.error = error

    def open(self, _request, timeout=20):
        del timeout
        if self.error is not None:
            raise self.error
        return self.response


def _patch_opener(monkeypatch: pytest.MonkeyPatch, opener: _FakeOpener) -> None:
    monkeypatch.setattr(urllib.request, "build_opener", lambda _handler: opener)


def test_default_transport_success(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"status": True}
    url = f"{BASE_URL}{LOGIN_PATH}"
    _patch_opener(
        monkeypatch,
        _FakeOpener(_Response(json.dumps(payload).encode(), url)),
    )
    status, result = angel_one._default_transport("POST", url, {}, b"{}")
    assert status == 200
    assert result == payload


def test_default_transport_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"{BASE_URL}{LOGIN_PATH}"
    error = urllib.error.HTTPError(
        url,
        401,
        "auth",
        {},
        io.BytesIO(b'{"status": false}'),
    )
    _patch_opener(monkeypatch, _FakeOpener(error=error))
    status, result = angel_one._default_transport("POST", url, {}, b"{}")
    assert status == 401
    assert result == {"status": False}


def test_default_transport_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"{BASE_URL}{LOGIN_PATH}"
    _patch_opener(monkeypatch, _FakeOpener(error=urllib.error.URLError("down")))
    with pytest.raises(PortfolioError) as error:
        angel_one._default_transport("POST", url, {}, b"{}")
    assert error.value.code == "PROVIDER_UNAVAILABLE"


def test_default_transport_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"{BASE_URL}{LOGIN_PATH}"
    _patch_opener(monkeypatch, _FakeOpener(_Response(b"not json", url)))
    with pytest.raises(PortfolioError) as error:
        angel_one._default_transport("POST", url, {}, b"{}")
    assert error.value.code == "MALFORMED_RESPONSE"


def test_default_transport_final_url_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = f"{BASE_URL}{LOGIN_PATH}"
    _patch_opener(monkeypatch, _FakeOpener(_Response(b"{}", "https://example.com")))
    with pytest.raises(PortfolioError) as error:
        angel_one._default_transport("POST", url, {}, b"{}")
    assert error.value.code == "PROVIDER_UNAVAILABLE"


def test_default_transport_rejects_foreign_url() -> None:
    with pytest.raises(PortfolioError) as error:
        angel_one._default_transport("GET", "https://example.com", {}, None)
    assert error.value.code == "PROVIDER_UNAVAILABLE"


def test_login_provider_unavailable() -> None:
    client = _client(
        FakeTransport(login=(200, {"status": False, "message": "unknown"}))
    )
    with pytest.raises(PortfolioError) as error:
        client.login()
    assert error.value.code == "PROVIDER_UNAVAILABLE"


def test_no_redirect_handler() -> None:
    with pytest.raises(PortfolioError) as error:
        angel_one._NoRedirect().redirect_request(
            None, None, 302, "", {}, "https://example.com"
        )
    assert error.value.code == "PROVIDER_UNAVAILABLE"


def test_response_size_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(angel_one, "MAX_RESPONSE_BYTES", 1)
    with pytest.raises(PortfolioError) as error:
        angel_one._decode_body(b"{}")
    assert error.value.code == "MALFORMED_RESPONSE"


def test_symbol_control_characters_rejected() -> None:
    row = dict(_HOLDINGS["data"]["holdings"][0])
    row["tradingsymbol"] = "BAD\nSYMBOL"
    payload = {"status": True, "data": {"holdings": [row]}}
    client = _client(FakeTransport(holdings=(200, payload)))
    client.login()
    with pytest.raises(PortfolioError) as error:
        client.holdings()
    assert error.value.code == "MALFORMED_RESPONSE"


def test_symbol_non_ascii_rejected() -> None:
    row = dict(_HOLDINGS["data"]["holdings"][0])
    row["tradingsymbol"] = "ß"
    payload = {"status": True, "data": {"holdings": [row]}}
    client = _client(FakeTransport(holdings=(200, payload)))
    client.login()
    with pytest.raises(PortfolioError) as error:
        client.holdings()
    assert error.value.code == "MALFORMED_RESPONSE"


def test_empty_holdings_have_day_limitation() -> None:
    payload = {"status": True, "data": {"holdings": []}}
    client = _client(FakeTransport(holdings=(200, payload)))
    client.login()
    snapshot = client.holdings()
    assert snapshot.day_change is None
    assert "DAY_CHANGE_UNAVAILABLE" in snapshot.limitations


def test_authenticated_client_code_is_captured() -> None:
    login = {"status": True, "data": {"jwtToken": "jwt", "clientcode": "CLIENT1"}}
    client = _client(FakeTransport(login=(200, login)))
    client.login()
    assert client.authenticated_client_code == "CLIENT1"


def test_pnl_inconsistency_limitation() -> None:
    row = dict(_HOLDINGS["data"]["holdings"][0])
    row["profitandloss"] = "9999.00"
    payload = {"status": True, "data": {"holdings": [row]}}
    client = _client(FakeTransport(holdings=(200, payload)))
    client.login()
    snapshot = client.holdings()
    assert "PNL_INCONSISTENT" in snapshot.limitations
    assert snapshot.overall_pnl == Decimal("50.00")
