from __future__ import annotations

import json
from datetime import date

import pytest

from swing_trading_ai_assistant.market_data.credentials import AccessToken
from swing_trading_ai_assistant.market_data.historical import (
    HistoricalRequest,
    HistoricalResponse,
)
from swing_trading_ai_assistant.market_data.instruments import (
    Instrument,
    InstrumentCatalog,
)
from swing_trading_ai_assistant.market_data.probe import (
    ProbeRequest,
    run_capability_probe,
)


class TokenProvider:
    def get_access_token(self) -> AccessToken:
        return AccessToken("must-never-appear")


class CatalogClient:
    def fetch_nse_catalog(self) -> InstrumentCatalog:
        return InstrumentCatalog(
            (
                Instrument(
                    instrument_key="NSE_EQ|INE002A01018",
                    security_id="INE002A01018",
                    symbol="RELIANCE",
                    exchange="NSE",
                    segment="NSE_EQ",
                    instrument_type="EQ",
                ),
            )
        )


class HistoricalClient:
    def fetch(self, request: object, token: AccessToken) -> HistoricalResponse:
        assert token.reveal() == "must-never-appear"
        return HistoricalResponse(
            status_code=200,
            candles=[
                ["2026-07-31T09:16:00+05:30", 1401, 1403, 1400, 1402, 1200, 10],
                ["2026-07-31T09:15:00+05:30", 1400, 1402, 1399, 1401, 1000, 9],
            ],
        )


def test_probe_reports_only_approved_metadata() -> None:
    report = run_capability_probe(
        ProbeRequest(
            segment="NSE_EQ",
            symbol="RELIANCE",
            from_date=date(2026, 7, 31),
            to_date=date(2026, 7, 31),
        ),
        token_provider=TokenProvider(),
        catalog_client=CatalogClient(),
        historical_client=HistoricalClient(),
    )

    output = json.loads(report.to_json())

    assert output == {
        "status": 200,
        "row_count": 2,
        "first_timestamp": "2026-07-31T09:15:00+05:30",
        "last_timestamp": "2026-07-31T09:16:00+05:30",
        "schema_valid": True,
    }
    assert "must-never-appear" not in report.to_json()
    assert "instrument_key" not in output


def test_probe_does_not_treat_an_empty_success_response_as_capable() -> None:
    class EmptyHistoricalClient:
        def fetch(self, request: object, token: AccessToken) -> HistoricalResponse:
            return HistoricalResponse(status_code=200, candles=[])

    report = run_capability_probe(
        ProbeRequest(
            segment="NSE_EQ",
            symbol="RELIANCE",
            from_date=date(2026, 7, 31),
            to_date=date(2026, 7, 31),
        ),
        token_provider=TokenProvider(),
        catalog_client=CatalogClient(),
        historical_client=EmptyHistoricalClient(),
    )

    assert report.status == 200
    assert report.row_count == 0
    assert report.schema_valid is False


def test_probe_resolves_the_requested_symbol_from_the_master_catalog() -> None:
    class MultiInstrumentCatalogClient:
        def fetch_nse_catalog(self) -> InstrumentCatalog:
            return InstrumentCatalog(
                (
                    Instrument(
                        instrument_key="NSE_EQ|INE002A01018",
                        security_id="INE002A01018",
                        symbol="RELIANCE",
                        exchange="NSE",
                        segment="NSE_EQ",
                        instrument_type="EQ",
                    ),
                    Instrument(
                        instrument_key="NSE_EQ|INE467B01029",
                        security_id="INE467B01029",
                        symbol="TCS",
                        exchange="NSE",
                        segment="NSE_EQ",
                        instrument_type="EQ",
                    ),
                )
            )

    class RequestedInstrumentHistoricalClient:
        def fetch(
            self, request: HistoricalRequest, token: AccessToken
        ) -> HistoricalResponse:
            assert request.instrument_key == "NSE_EQ|INE467B01029"
            return HistoricalResponse(
                status_code=200,
                candles=[
                    [
                        "2026-07-31T09:15:00+05:30",
                        3000,
                        3002,
                        2999,
                        3001,
                        1000,
                        0,
                    ]
                ],
            )

    report = run_capability_probe(
        ProbeRequest(
            segment="NSE_EQ",
            symbol="TCS",
            from_date=date(2026, 7, 31),
            to_date=date(2026, 7, 31),
        ),
        token_provider=TokenProvider(),
        catalog_client=MultiInstrumentCatalogClient(),
        historical_client=RequestedInstrumentHistoricalClient(),
    )

    assert report.schema_valid is True


@pytest.mark.parametrize(("segment", "symbol"), [("", "TCS"), ("NSE_EQ", "")])
def test_probe_request_rejects_an_empty_master_catalog_selector(
    segment: str, symbol: str
) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        ProbeRequest(
            segment=segment,
            symbol=symbol,
            from_date=date(2026, 7, 31),
            to_date=date(2026, 7, 31),
        )
