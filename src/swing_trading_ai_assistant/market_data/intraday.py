"""Upstox V3 current-day one-minute candle provider adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
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
MAX_INTRADAY_CANDLES = 500
_MAX_PROVIDER_JSON_NESTING = 64


def _empty_headers() -> HttpResponseHeaders:
    return HttpResponseHeaders()


@dataclass(frozen=True, slots=True)
class IntradayRequest:
    """The instrument identity accepted by Upstox's current-day route."""

    instrument_key: str

    def __post_init__(self) -> None:
        if not self.instrument_key.strip():
            raise ValueError("instrument_key must not be empty")


@dataclass(frozen=True, slots=True)
class IntradayResponse:
    """Bounded raw provider result; canonical candle validation happens downstream."""

    status_code: int
    candles: list[list[object]]
    headers: HttpResponseHeaders = field(default_factory=_empty_headers)
    error_category: ProviderErrorCategory | None = None


class UpstoxV3IntradayClient:
    """Fetch current-day one-minute candles through the documented V3 endpoint."""

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def fetch(self, request: IntradayRequest, token: AccessToken) -> IntradayResponse:
        instrument_key = quote(request.instrument_key, safe="")
        url = (
            f"{UPSTOX_API_BASE_URL}/v3/historical-candle/intraday/"
            f"{instrument_key}/minutes/1"
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
            return IntradayResponse(
                status_code=response.status_code,
                candles=[],
                headers=response.headers,
                error_category=response.error_category,
            )

        status_code = response.status_code
        headers = response.headers
        error_category = response.error_category
        decode_status, candles = _decode_success_candles(response.body)
        del instrument_key, request, response, self, token, url
        if decode_status is _SuccessDecodeStatus.MALFORMED_JSON:
            _raise_malformed_intraday_json()
        if decode_status is _SuccessDecodeStatus.INVALID_ENVELOPE:
            _raise_invalid_success_envelope()
        if decode_status is _SuccessDecodeStatus.INVALID_CANDLES:
            _raise_invalid_candles_array()
        return IntradayResponse(
            status_code=status_code,
            candles=candles,
            headers=headers,
            error_category=error_category,
        )


class _SuccessDecodeStatus(StrEnum):
    VALID = "VALID"
    MALFORMED_JSON = "MALFORMED_JSON"
    INVALID_ENVELOPE = "INVALID_ENVELOPE"
    INVALID_CANDLES = "INVALID_CANDLES"


class _RejectedProviderJSON(ValueError):
    pass


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _RejectedProviderJSON
        result[key] = value
    return result


def _reject_nonstandard_json_constant(value: str) -> NoReturn:
    del value
    raise _RejectedProviderJSON


def _decode_success_candles(
    body: bytes,
) -> tuple[_SuccessDecodeStatus, list[list[object]]]:
    if not _json_nesting_within_limit(body):
        return _SuccessDecodeStatus.MALFORMED_JSON, []
    try:
        payload: object = json.loads(
            body,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (Exception, MemoryError):
        return _SuccessDecodeStatus.MALFORMED_JSON, []
    if type(payload) is not dict:
        return _SuccessDecodeStatus.INVALID_ENVELOPE, []
    payload_record = cast(dict[str, object], payload)
    data = payload_record.get("data")
    if (
        set(payload_record) != {"status", "data"}
        or payload_record.get("status") != "success"
        or type(data) is not dict
    ):
        return _SuccessDecodeStatus.INVALID_ENVELOPE, []
    data_record = cast(dict[str, object], data)
    if set(data_record) != {"candles"}:
        return _SuccessDecodeStatus.INVALID_ENVELOPE, []
    candles = data_record.get("candles")
    if type(candles) is not list:
        return _SuccessDecodeStatus.INVALID_CANDLES, []
    candle_rows = cast(list[object], candles)
    if len(candle_rows) > MAX_INTRADAY_CANDLES or any(
        type(row) is not list or len(row) != 7 for row in candle_rows
    ):
        return _SuccessDecodeStatus.INVALID_CANDLES, []
    return _SuccessDecodeStatus.VALID, cast(list[list[object]], candles)


def _json_nesting_within_limit(value: bytes) -> bool:
    depth = 0
    in_string = False
    escaped = False
    for byte in value:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x5B, 0x7B):
            depth += 1
            if depth > _MAX_PROVIDER_JSON_NESTING:
                return False
        elif byte in (0x5D, 0x7D):
            depth -= 1
    return True


def _raise_malformed_intraday_json() -> NoReturn:
    raise ValueError("intraday response is not valid JSON") from None


def _raise_invalid_success_envelope() -> NoReturn:
    raise ValueError("intraday response is not a valid success envelope") from None


def _raise_invalid_candles_array() -> NoReturn:
    raise ValueError(
        "intraday response does not contain a valid candles array"
    ) from None


def _raise_body_too_large() -> NoReturn:
    raise HttpResponseBodyTooLarge(
        "market-data provider response exceeded limit"
    ) from None


def _raise_invalid_response_headers() -> NoReturn:
    raise HttpResponseHeadersInvalid from None
