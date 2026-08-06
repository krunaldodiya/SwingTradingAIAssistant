"""Upstox V3 historical-candle provider adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import NoReturn, cast
from urllib.parse import quote

from .credentials import AccessToken
from .http import (
    HttpResponse,
    HttpResponseBodyTooLarge,
    HttpResponseHeaders,
    HttpResponseHeadersInvalid,
    HttpTransport,
    ProviderErrorCategory,
)

UPSTOX_API_BASE_URL = "https://api.upstox.com"

_V3_INTERVAL_LIMITS = {
    "minutes": range(1, 301),
    "hours": range(1, 6),
    "days": range(1, 2),
    "weeks": range(1, 2),
    "months": range(1, 2),
}


def _empty_headers() -> HttpResponseHeaders:
    return HttpResponseHeaders()


@dataclass(frozen=True)
class HistoricalRequest:
    instrument_key: str
    unit: str
    interval: int
    from_date: date
    to_date: date

    def __post_init__(self) -> None:
        if not self.instrument_key.strip():
            raise ValueError("instrument_key must not be empty")
        allowed_intervals = _V3_INTERVAL_LIMITS.get(self.unit)
        if allowed_intervals is None:
            raise ValueError("unit is not supported by Upstox Historical V3")
        if self.interval not in allowed_intervals:
            raise ValueError(
                "interval is not supported for this Upstox Historical V3 unit"
            )
        if self.from_date > self.to_date:
            raise ValueError("from_date must be on or before to_date")
        if (
            self.unit == "minutes"
            and self.interval <= 15
            and (self.from_date.year, self.from_date.month)
            != (self.to_date.year, self.to_date.month)
        ):
            raise ValueError("1-15 minute requests must fit within one calendar month")


@dataclass(frozen=True)
class HistoricalResponse:
    status_code: int
    candles: list[list[object]]
    headers: HttpResponseHeaders = field(default_factory=_empty_headers)
    error_category: ProviderErrorCategory | None = None


class UpstoxV3HistoricalClient:
    """Translate the internal request into the documented Upstox V3 route."""

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def fetch(
        self, request: HistoricalRequest, token: AccessToken
    ) -> HistoricalResponse:
        instrument_key = quote(request.instrument_key, safe="")
        url = (
            f"{UPSTOX_API_BASE_URL}/v3/historical-candle/{instrument_key}/"
            f"{request.unit}/{request.interval}/{request.to_date.isoformat()}/"
            f"{request.from_date.isoformat()}"
        )
        oversized = False
        invalid_headers = False
        response: HttpResponse | None = None
        try:
            response = self._transport.get(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token.reveal()}",
                },
            )
        except HttpResponseBodyTooLarge:
            oversized = True
        except HttpResponseHeadersInvalid:
            invalid_headers = True
        if oversized:
            del instrument_key, request, self, token, url, response
            _raise_body_too_large()
        if invalid_headers:
            del instrument_key, request, self, token, url, response
            _raise_invalid_response_headers()
        response = cast(HttpResponse, response)
        if response.status_code < 200 or response.status_code >= 300:
            return HistoricalResponse(
                status_code=response.status_code,
                candles=[],
                headers=response.headers,
                error_category=response.error_category,
            )

        try:
            payload: object = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("historical response is not valid JSON") from exc
        payload_record = (
            cast(dict[str, object], payload) if isinstance(payload, dict) else {}
        )
        data = payload_record.get("data")
        data_record = cast(dict[str, object], data) if isinstance(data, dict) else {}
        candles = data_record.get("candles")
        if not isinstance(candles, list):
            raise ValueError("historical response does not contain a candles array")
        candle_rows = cast(list[object], candles)
        if any(not isinstance(row, list) for row in candle_rows):
            raise ValueError("historical response does not contain a candles array")
        return HistoricalResponse(
            status_code=response.status_code,
            candles=cast(list[list[object]], candles),
            headers=response.headers,
            error_category=response.error_category,
        )


def _raise_body_too_large() -> NoReturn:
    raise HttpResponseBodyTooLarge(
        "market-data provider response exceeded limit"
    ) from None


def _raise_invalid_response_headers() -> NoReturn:
    raise HttpResponseHeadersInvalid from None
