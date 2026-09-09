from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.instruments as instruments_module
from swing_trading_ai_assistant.market_data.http import (
    HttpResponse,
    HttpResponseHeaders,
    ProviderErrorCategory,
)
from swing_trading_ai_assistant.market_data.instruments import (
    AmbiguousInstrumentError,
    CatalogPayloadTooLargeError,
    InstrumentCatalog,
    InstrumentCatalogClient,
    InstrumentCatalogPayloadError,
    InstrumentCatalogRequestError,
    InstrumentNotFoundError,
)

RELIANCE = {
    "segment": "NSE_EQ",
    "name": "RELIANCE INDUSTRIES LIMITED",
    "exchange": "NSE",
    "isin": "INE002A01018",
    "instrument_type": "EQ",
    "instrument_key": "NSE_EQ|INE002A01018",
    "trading_symbol": "RELIANCE",
}

GENERALIZED_INSTRUMENT_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "upstox_generalized_instruments.json"
)


class StaticTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        self.requests.append((url, headers))
        return self.response


def test_catalog_client_downloads_and_decompresses_official_nse_json() -> None:
    body = gzip.compress(json.dumps([RELIANCE]).encode())
    transport = StaticTransport(HttpResponse(status_code=200, body=body))
    client = InstrumentCatalogClient(transport)

    catalog = client.fetch_nse_catalog()

    instrument = catalog.resolve(segment="NSE_EQ", isin="INE002A01018")
    assert instrument.symbol == "RELIANCE"
    assert instrument.instrument_key == "NSE_EQ|INE002A01018"
    assert transport.requests == [
        (
            "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
            {"Accept": "application/json"},
        )
    ]


def test_catalog_client_classifies_provider_integer_that_overflows_float() -> None:
    payload = json.dumps([RELIANCE | {"strike_price": 10**999}]).encode()
    client = InstrumentCatalogClient(
        StaticTransport(HttpResponse(status_code=200, body=gzip.compress(payload)))
    )

    with pytest.raises(InstrumentCatalogPayloadError):
        client.fetch_nse_catalog()


@pytest.mark.parametrize("error_type", (ValueError, MemoryError))
def test_catalog_preserves_unrelated_numeric_conversion_fault(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    failure = error_type("synthetic numeric conversion fault")

    class NumericFault(int):
        def __float__(self) -> float:
            raise failure

    monkeypatch.setattr(
        instruments_module,
        "_parse_catalog_json_int",
        NumericFault,
    )

    with pytest.raises(error_type) as raised:
        InstrumentCatalog.from_json_bytes(
            b'[{"segment":"NSE_EQ","exchange":"NSE","instrument_key":"NSE_EQ|X",'
            b'"trading_symbol":"X","strike_price":1}]'
        )

    assert raised.value is failure


def test_catalog_resolution_requires_exact_segment_and_isin() -> None:
    catalog = InstrumentCatalog.from_json_bytes(json.dumps([RELIANCE]).encode())

    with pytest.raises(InstrumentNotFoundError):
        catalog.resolve(segment="NSE_FO", isin="INE002A01018")


def test_catalog_rejects_ambiguous_identity() -> None:
    catalog = InstrumentCatalog.from_json_bytes(
        json.dumps([RELIANCE, RELIANCE]).encode()
    )

    with pytest.raises(AmbiguousInstrumentError):
        catalog.resolve(segment="NSE_EQ", isin="INE002A01018")


def test_catalog_rejects_non_array_payload() -> None:
    with pytest.raises(ValueError, match="array"):
        InstrumentCatalog.from_json_bytes(b'{"data": []}')


def test_catalog_client_bounds_gzip_decompression() -> None:
    body = gzip.compress(json.dumps([RELIANCE]).encode())
    client = InstrumentCatalogClient(
        StaticTransport(HttpResponse(status_code=200, body=body)),
        max_decompressed_bytes=3,
    )

    with pytest.raises(CatalogPayloadTooLargeError):
        client.fetch_nse_catalog()


def test_catalog_client_preserves_retry_metadata_on_a_non_200_response() -> None:
    client = InstrumentCatalogClient(
        StaticTransport(
            HttpResponse(
                status_code=429,
                body=b"{}",
                headers=HttpResponseHeaders.from_items(
                    (("Retry-After", "12"), ("X-Request-Id", "request-123"))
                ),
            )
        )
    )

    with pytest.raises(InstrumentCatalogRequestError) as exc_info:
        client.fetch_nse_catalog()

    assert exc_info.value.error_category is ProviderErrorCategory.RATE_LIMITED
    assert exc_info.value.headers.items() == (
        ("Retry-After", "12"),
        ("X-Request-Id", "request-123"),
    )


def test_catalog_resolves_non_equity_instruments_from_explicit_metadata() -> None:
    catalog = InstrumentCatalog.from_json_bytes(
        GENERALIZED_INSTRUMENT_FIXTURE.read_bytes()
    )

    index = catalog.resolve(segment="NSE_INDEX", symbol="NIFTY 50")
    future = catalog.resolve(
        segment="NSE_FO",
        instrument_type="FUT",
        underlying_key="NSE_INDEX|Nifty 50",
        expiry="2026-08-27",
    )
    option = catalog.resolve(
        segment="NSE_FO",
        instrument_type="CE",
        underlying_key="NSE_INDEX|Nifty 50",
        expiry="2026-08-27",
        strike_price=25000,
    )

    assert index.isin is None
    assert index.security_id == "NSE_INDEX:NSE:INDEX:NIFTY 50"
    assert index.security_id != index.instrument_key
    assert future.underlying_key == "NSE_INDEX|Nifty 50"
    assert future.expiry == "2026-08-27"
    assert option.strike_price == 25000
    assert option.option_type == "CE"


def test_catalog_requires_an_explicit_non_isin_identity() -> None:
    catalog = InstrumentCatalog.from_json_bytes(
        json.dumps(
            [json.loads(GENERALIZED_INSTRUMENT_FIXTURE.read_bytes())[0]]
        ).encode()
    )

    with pytest.raises(ValueError, match="identity"):
        catalog.resolve(segment="NSE_INDEX")
