"""Provider instrument catalog download and identity resolution."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from io import BytesIO
from typing import cast

from .http import HttpResponseHeaders, HttpTransport, ProviderErrorCategory

UPSTOX_NSE_INSTRUMENTS_URL = (
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
)
DEFAULT_MAX_CATALOG_COMPRESSED_BYTES = 4_000_000
DEFAULT_MAX_CATALOG_DECOMPRESSED_BYTES = 50_000_000


class InstrumentNotFoundError(LookupError):
    """No instrument matches the requested provider identity."""


class AmbiguousInstrumentError(LookupError):
    """More than one instrument matches a supposedly unique identity."""


class CatalogPayloadTooLargeError(ValueError):
    """The decompressed provider catalog exceeded its bounded memory budget."""


class InstrumentCatalogRequestError(RuntimeError):
    """A catalog response failed while retaining safe retry metadata."""

    def __init__(
        self,
        *,
        status_code: int,
        headers: HttpResponseHeaders,
        error_category: ProviderErrorCategory | None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers
        self.error_category = error_category
        super().__init__(f"instrument catalog request returned HTTP {status_code}")


@dataclass(frozen=True)
class Instrument:
    instrument_key: str
    security_id: str
    symbol: str
    exchange: str
    segment: str
    instrument_type: str
    isin: str | None = None
    underlying_key: str | None = None
    expiry: str | None = None
    strike_price: float | None = None
    option_type: str | None = None


class InstrumentCatalog:
    """Immutable provider snapshot parsed into a small internal contract."""

    def __init__(self, instruments: tuple[Instrument, ...]) -> None:
        self._instruments = instruments

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> InstrumentCatalog:
        try:
            records: object = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("instrument catalog is not valid JSON") from exc
        if not isinstance(records, list):
            raise ValueError("instrument catalog must be a JSON array")

        instruments: list[Instrument] = []
        for record in cast(list[object], records):
            if not isinstance(record, dict):
                continue
            fields = cast(dict[str, object], record)
            instrument_key = _text(fields.get("instrument_key"))
            segment = _text(fields.get("segment"))
            symbol = _text(fields.get("trading_symbol"))
            if not instrument_key or not segment or not symbol:
                continue
            isin = _text(fields.get("isin"))
            instrument_type = _text(fields.get("instrument_type"))
            underlying_key = _text(fields.get("underlying_key")) or None
            expiry = _text(fields.get("expiry")) or None
            strike_price = _number(fields.get("strike_price"))
            option_type = _text(fields.get("option_type")) or None
            if option_type is None and instrument_type in {"CE", "PE"}:
                option_type = instrument_type
            instruments.append(
                Instrument(
                    instrument_key=instrument_key,
                    security_id=_security_id(
                        isin=isin,
                        segment=segment,
                        exchange=_text(fields.get("exchange")),
                        symbol=symbol,
                        instrument_type=instrument_type,
                        underlying_key=underlying_key,
                        expiry=expiry,
                        strike_price=strike_price,
                        option_type=option_type,
                    ),
                    symbol=symbol,
                    exchange=_text(fields.get("exchange")),
                    segment=segment,
                    instrument_type=instrument_type,
                    isin=isin or None,
                    underlying_key=underlying_key,
                    expiry=expiry,
                    strike_price=strike_price,
                    option_type=option_type,
                )
            )
        return cls(tuple(instruments))

    def resolve(
        self,
        *,
        segment: str,
        isin: str | None = None,
        instrument_key: str | None = None,
        symbol: str | None = None,
        instrument_type: str | None = None,
        underlying_key: str | None = None,
        expiry: str | None = None,
        strike_price: float | None = None,
        option_type: str | None = None,
    ) -> Instrument:
        """Resolve one catalog instrument using explicit family metadata.

        Equities use ISIN, while indices and derivatives can be selected by their
        documented provider metadata. All supplied fields must match exactly.
        """
        criteria = {
            "isin": isin,
            "instrument_key": instrument_key,
            "symbol": symbol,
            "instrument_type": instrument_type,
            "underlying_key": underlying_key,
            "expiry": expiry,
            "strike_price": strike_price,
            "option_type": option_type,
        }
        if not any(value is not None and value != "" for value in criteria.values()):
            raise ValueError("instrument identity must include a non-segment field")
        matches = [
            instrument
            for instrument in self._instruments
            if instrument.segment == segment
            and all(
                _identity_value(instrument, field_name) == value
                for field_name, value in criteria.items()
                if value is not None
            )
        ]
        if not matches:
            raise InstrumentNotFoundError(
                "instrument was not found for the requested identity"
            )
        if len(matches) > 1:
            raise AmbiguousInstrumentError(
                "multiple instruments matched the requested identity"
            )
        return matches[0]


class InstrumentCatalogClient:
    """Download the current Upstox NSE BOD JSON snapshot without persisting it."""

    def __init__(
        self,
        transport: HttpTransport,
        *,
        max_decompressed_bytes: int = DEFAULT_MAX_CATALOG_DECOMPRESSED_BYTES,
    ) -> None:
        if max_decompressed_bytes <= 0:
            raise ValueError("max_decompressed_bytes must be positive")
        self._transport = transport
        self._max_decompressed_bytes = max_decompressed_bytes

    def fetch_nse_catalog(self) -> InstrumentCatalog:
        response = self._transport.get(
            UPSTOX_NSE_INSTRUMENTS_URL,
            headers={"Accept": "application/json"},
        )
        if response.status_code != 200:
            raise InstrumentCatalogRequestError(
                status_code=response.status_code,
                headers=response.headers,
                error_category=response.error_category,
            )
        try:
            payload = _decompress_gzip_bounded(
                response.body, max_decompressed_bytes=self._max_decompressed_bytes
            )
        except (EOFError, gzip.BadGzipFile) as exc:
            raise ValueError("instrument catalog response is not valid gzip") from exc
        return InstrumentCatalog.from_json_bytes(payload)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _identity_value(instrument: Instrument, field_name: str) -> object:
    # `security_id` was the pre-generalization equity ISIN field. Retaining this
    # fallback lets injected legacy fixtures remain valid while real parsed
    # instruments retain their explicit ISIN separately.
    if field_name == "isin" and instrument.isin is None:
        return instrument.security_id
    return getattr(instrument, field_name)


def _security_id(
    *,
    isin: str,
    segment: str,
    exchange: str,
    symbol: str,
    instrument_type: str,
    underlying_key: str | None,
    expiry: str | None,
    strike_price: float | None,
    option_type: str | None,
) -> str:
    """Return a canonical identity from normalized contract metadata."""
    if isin:
        return isin
    if underlying_key and expiry and instrument_type:
        fields = [segment, underlying_key, expiry, instrument_type]
        if option_type:
            fields.append(option_type)
        if strike_price is not None:
            fields.append(format(strike_price, "g"))
        return ":".join(fields)
    return ":".join(
        _normalized_id_part(value)
        for value in (segment, exchange, instrument_type, symbol)
    )


def _normalized_id_part(value: str) -> str:
    return " ".join(value.upper().split())


def _decompress_gzip_bounded(
    compressed: bytes, *, max_decompressed_bytes: int
) -> bytes:
    with gzip.GzipFile(fileobj=BytesIO(compressed), mode="rb") as gzip_file:
        payload = gzip_file.read(max_decompressed_bytes + 1)
    if len(payload) > max_decompressed_bytes:
        raise CatalogPayloadTooLargeError(
            "instrument catalog decompressed response exceeded limit"
        )
    return payload
