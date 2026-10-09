from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from swing_trading_ai_assistant.market_data.http import HttpResponse
from swing_trading_ai_assistant.market_data.upstox_full_quote_v3 import (
    UpstoxFullQuoteAuthenticationError,
    UpstoxFullQuoteCorruptError,
    UpstoxFullQuoteV3Client,
)

_ISIN = "INE002A01018"
_SYMBOL = "RELIANCE"
_TOKEN = "private-upstox-token"  # noqa: S105 - deterministic fake credential
_RETRIEVED = datetime(2026, 10, 9, 4, 31, tzinfo=UTC)


class _RecordingTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        self.calls.append((url, dict(headers)))
        return self.response


def _depth(price: str, quantity: int) -> list[dict[str, object]]:
    return [
        {
            "price": float(Decimal(price) - Decimal(index) / Decimal("20")),
            "quantity": quantity - index,
            "orders": 1 + index,
        }
        for index in range(5)
    ]


def _payload(**overrides: object) -> bytes:
    quote: dict[str, object] = {
        "ohlc": {
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 102.0,
            "volume": 100_000,
            "ts": 1_760_000_000_000,
        },
        "depth": {
            "buy": _depth("101.9", 5_000),
            "sell": [
                {
                    "price": float(Decimal("102.1") + Decimal(index) / Decimal("20")),
                    "quantity": 4_000 - index,
                    "orders": 1 + index,
                }
                for index in range(5)
            ],
        },
        "timestamp": "2026-10-09T10:00:00.000+05:30",
        "instrument_token": f"NSE_EQ|{_ISIN}",
        "symbol": _SYMBOL,
        "last_price": 102.0,
        "volume": 100_000,
        "average_price": 101.0,
        "oi": 0,
        "net_change": 1.0,
        "total_buy_quantity": 15_000,
        "total_sell_quantity": 12_000,
        "lower_circuit_limit": 81.6,
        "upper_circuit_limit": 122.4,
        "last_trade_time": "1760000000000",
        "oi_day_high": 0,
        "oi_day_low": 0,
        "prev_close_price": 101.0,
        "year_high": 130.0,
        "year_low": 70.0,
        "previous_oi": 0,
        "indicative_equilibrium_price": 102.0,
        "reference_price": 101.0,
        "indicative_equilibrium_quantity": 0,
        "indicative_imbalance_quantity_total": 0,
        "indicative_imbalance_quantity_market": 0,
        "cas_eligible": True,
    }
    quote.update(overrides)
    return json.dumps(
        {"status": "success", "data": {f"NSE_EQ:{_SYMBOL}": quote}},
        separators=(",", ":"),
    ).encode()


def _client(payload: bytes | None = None, *, status: int = 200):
    transport = _RecordingTransport(
        HttpResponse(status, _payload() if payload is None else payload)
    )
    return UpstoxFullQuoteV3Client(transport, clock=lambda: _RETRIEVED), transport


def test_quote_client_binds_exact_nse_equity_identity_and_redacts_token() -> None:
    client, transport = _client()

    quote = client.fetch(_ISIN, _SYMBOL, _TOKEN)

    assert transport.calls == [
        (
            f"https://api.upstox.com/v3/market-quote/quotes?instrument_key=NSE_EQ%7C{_ISIN}",
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {_TOKEN}",
            },
        )
    ]
    assert quote.instrument_key == f"NSE_EQ|{_ISIN}"
    assert quote.symbol == _SYMBOL
    assert quote.last_price == Decimal("102")
    assert quote.lower_circuit_limit == Decimal("81.6")
    assert quote.upper_circuit_limit == Decimal("122.4")
    assert quote.best_bid == Decimal("101.9")
    assert quote.best_ask == Decimal("102.1")
    assert quote.quote_timestamp == datetime(2026, 10, 9, 4, 30, tzinfo=UTC)
    assert quote.retrieved_at == _RETRIEVED
    assert len(quote.response_sha256) == 64
    assert len(quote.quote_identity_sha256) == 64
    assert _TOKEN.encode() not in quote.canonical_json_bytes()


@pytest.mark.parametrize(
    "payload",
    (
        b'{"status":"success","status":"success","data":{}}',
        json.dumps({"status": "failure", "data": {}}).encode(),
        json.dumps({"status": "success", "data": {}, "extra": True}).encode(),
        _payload(symbol="OTHER"),
        _payload(instrument_token="NSE_EQ|INE848E01016"),  # noqa: S106 - public test ISIN
        _payload(extra_provider_field="not admitted"),
    ),
)
def test_quote_client_rejects_schema_or_identity_substitution(payload: bytes) -> None:
    client, _ = _client(payload)

    with pytest.raises(UpstoxFullQuoteCorruptError):
        client.fetch(_ISIN, _SYMBOL, _TOKEN)


def test_quote_client_keeps_authentication_failure_typed_and_private() -> None:
    client, _ = _client(b'{"secret":"private-upstox-token"}', status=401)

    with pytest.raises(UpstoxFullQuoteAuthenticationError) as caught:
        client.fetch(_ISIN, _SYMBOL, _TOKEN)

    assert _TOKEN not in str(caught.value)


def test_quote_client_rejects_depth_outside_reported_circuit_range() -> None:
    client, _ = _client(
        _payload(
            depth={
                "buy": _depth("130", 5_000),
                "sell": [
                    {
                        "price": float(Decimal("130.1") + Decimal(index) / 20),
                        "quantity": 4_000 - index,
                        "orders": 1 + index,
                    }
                    for index in range(5)
                ],
            }
        )
    )

    with pytest.raises(UpstoxFullQuoteCorruptError):
        client.fetch(_ISIN, _SYMBOL, _TOKEN)
