"""Credential-safe, non-persistent market-data capability probe."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from typing import Protocol

from .credentials import AccessToken, AccessTokenProvider
from .historical import HistoricalRequest, HistoricalResponse
from .instruments import Instrument, InstrumentCatalog
from .normalization import CandleSchemaError, normalize_candles


class CatalogClient(Protocol):
    def fetch_nse_catalog(self) -> InstrumentCatalog:
        """Fetch a current catalog snapshot without persisting it."""
        ...


class HistoricalClient(Protocol):
    def fetch(
        self, request: HistoricalRequest, token: AccessToken
    ) -> HistoricalResponse:
        """Fetch a historical response without persisting candles."""
        ...


@dataclass(frozen=True)
class ProbeRequest:
    segment: str
    symbol: str
    from_date: date
    to_date: date

    def __post_init__(self) -> None:
        if not self.segment.strip() or not self.symbol.strip():
            raise ValueError("segment and symbol must not be empty")
        if self.from_date > self.to_date:
            raise ValueError("from_date must be on or before to_date")


@dataclass(frozen=True)
class ProbeReport:
    status: int
    row_count: int
    first_timestamp: str | None
    last_timestamp: str | None
    schema_valid: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))


def run_capability_probe(
    request: ProbeRequest,
    *,
    token_provider: AccessTokenProvider,
    catalog_client: CatalogClient,
    historical_client: HistoricalClient,
) -> ProbeReport:
    """Resolve the requested master-catalog symbol and validate its response."""
    token = token_provider.get_access_token()
    catalog = catalog_client.fetch_nse_catalog()
    instrument: Instrument = catalog.resolve(
        segment=request.segment,
        symbol=request.symbol,
    )
    response = historical_client.fetch(
        HistoricalRequest(
            instrument_key=instrument.instrument_key,
            unit="minutes",
            interval=1,
            from_date=request.from_date,
            to_date=request.to_date,
        ),
        token,
    )

    if response.status_code < 200 or response.status_code >= 300:
        return ProbeReport(response.status_code, 0, None, None, False)
    try:
        candles = normalize_candles(response.candles)
    except CandleSchemaError:
        return ProbeReport(
            response.status_code, len(response.candles), None, None, False
        )

    return ProbeReport(
        status=response.status_code,
        row_count=len(candles),
        first_timestamp=candles[0].timestamp.isoformat() if candles else None,
        last_timestamp=candles[-1].timestamp.isoformat() if candles else None,
        # A successful empty JSON array proves only that the route answered. It
        # cannot establish the observed candle schema or entitlement capability.
        schema_valid=bool(candles),
    )
