"""Strict, bounded Upstox Full Market Quotes V3 observations for one NSE equity."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final, cast
from urllib.parse import urlencode

from .http import (
    HttpResponse,
    HttpResponseBodyTooLarge,
    HttpResponseHeadersInvalid,
    HttpTransport,
    HttpTransportError,
)

UPSTOX_FULL_QUOTE_URL_V3: Final = "https://api.upstox.com/v3/market-quote/quotes"
UPSTOX_FULL_QUOTE_SOURCE_V3: Final = "upstox-full-market-quotes-v3"
UPSTOX_FULL_QUOTE_ADAPTER_RELEASE_V3: Final = "full-quote-v3"
MAX_FULL_QUOTE_RESPONSE_BYTES_V3: Final = 1024 * 1024
MAX_FULL_QUOTE_JSON_DEPTH_V3: Final = 32
_ISIN: Final = re.compile(r"INE[A-Z0-9]{8}[0-9]\Z")
_SYMBOL: Final = re.compile(r"[A-Z0-9][A-Z0-9&._-]{0,63}\Z")
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_MAX_DECIMAL: Final = Decimal("1e18")
_QUOTE_FIELDS: Final = frozenset(
    {
        "ohlc",
        "depth",
        "timestamp",
        "instrument_token",
        "symbol",
        "last_price",
        "volume",
        "average_price",
        "oi",
        "net_change",
        "total_buy_quantity",
        "total_sell_quantity",
        "lower_circuit_limit",
        "upper_circuit_limit",
        "last_trade_time",
        "oi_day_high",
        "oi_day_low",
        "prev_close_price",
        "year_high",
        "year_low",
        "previous_oi",
        "indicative_equilibrium_price",
        "reference_price",
        "indicative_equilibrium_quantity",
        "indicative_imbalance_quantity_total",
        "indicative_imbalance_quantity_market",
        "cas_eligible",
    }
)


class UpstoxFullQuoteError(RuntimeError):
    """A sanitized failure at the full-quote provider boundary."""


class UpstoxFullQuoteUnavailableError(UpstoxFullQuoteError):
    """The provider could not supply a quote observation."""


class UpstoxFullQuoteAuthenticationError(UpstoxFullQuoteError):
    """The provider rejected the configured access token."""


class UpstoxFullQuoteAuthorizationError(UpstoxFullQuoteError):
    """The configured token lacks quote access."""


class UpstoxFullQuoteRateLimitedError(UpstoxFullQuoteError):
    """The provider rate limited the one bounded quote read."""


class UpstoxFullQuoteProviderResponseError(UpstoxFullQuoteError):
    """The provider returned a non-successful HTTP response."""


class UpstoxFullQuoteCorruptError(UpstoxFullQuoteError):
    """The provider response was malformed or did not bind the requested equity."""


@dataclass(frozen=True, slots=True)
class UpstoxFullQuoteV3:
    """Canonicalized, identity-bound V3 quote projection without request secrets."""

    instrument_key: str
    symbol: str
    source: str
    adapter_release: str
    quote_timestamp: datetime
    retrieved_at: datetime
    last_price: Decimal
    lower_circuit_limit: Decimal
    upper_circuit_limit: Decimal
    best_bid: Decimal
    best_ask: Decimal
    total_buy_quantity: int
    total_sell_quantity: int
    last_trade_time_millis: int
    response_sha256: str
    quote_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            not _valid_instrument_key(self.instrument_key)
            or _SYMBOL.fullmatch(self.symbol) is None
            or self.source != UPSTOX_FULL_QUOTE_SOURCE_V3
            or self.adapter_release != UPSTOX_FULL_QUOTE_ADAPTER_RELEASE_V3
            or not _aware(self.quote_timestamp)
            or not _aware(self.retrieved_at)
            or any(
                not _positive_decimal(value)
                for value in (
                    self.last_price,
                    self.lower_circuit_limit,
                    self.upper_circuit_limit,
                )
            )
            or any(
                not _nonnegative_decimal(value)
                for value in (self.best_bid, self.best_ask)
            )
            or self.lower_circuit_limit >= self.upper_circuit_limit
            or type(self.total_buy_quantity) is not int
            or type(self.total_sell_quantity) is not int
            or self.total_buy_quantity < 0
            or self.total_sell_quantity < 0
            or type(self.last_trade_time_millis) is not int
            or self.last_trade_time_millis < 0
            or _DIGEST.fullmatch(self.response_sha256) is None
            or _DIGEST.fullmatch(self.quote_identity_sha256) is None
        ):
            raise ValueError("invalid Upstox full quote")
        quote_timestamp = self.quote_timestamp.astimezone(UTC)
        retrieved_at = self.retrieved_at.astimezone(UTC)
        object.__setattr__(self, "quote_timestamp", quote_timestamp)
        object.__setattr__(self, "retrieved_at", retrieved_at)
        if self.quote_identity_sha256 != _quote_identity(self._value()):
            raise ValueError("invalid Upstox full quote")

    def _value(self) -> dict[str, object]:
        return {
            "instrument_key": self.instrument_key,
            "symbol": self.symbol,
            "source": self.source,
            "adapter_release": self.adapter_release,
            "quote_timestamp": _timestamp(self.quote_timestamp),
            "retrieved_at": _timestamp(self.retrieved_at),
            "last_price": _decimal_text(self.last_price),
            "lower_circuit_limit": _decimal_text(self.lower_circuit_limit),
            "upper_circuit_limit": _decimal_text(self.upper_circuit_limit),
            "best_bid": _decimal_text(self.best_bid),
            "best_ask": _decimal_text(self.best_ask),
            "total_buy_quantity": self.total_buy_quantity,
            "total_sell_quantity": self.total_sell_quantity,
            "last_trade_time_millis": self.last_trade_time_millis,
            "response_sha256": self.response_sha256,
        }

    def canonical_json_bytes(self) -> bytes:
        return _canonical_bytes(
            {**self._value(), "quote_identity_sha256": self.quote_identity_sha256}
        )


class UpstoxFullQuoteV3Client:
    """Fetch one V3 quote with closed schema and exact NSE-equity binding."""

    def __init__(
        self, transport: HttpTransport, *, clock: Callable[[], datetime]
    ) -> None:
        if not callable(clock):
            raise ValueError("invalid full quote clock")
        self._transport = transport
        self._clock = clock

    def fetch(self, isin: str, symbol: str, access_token: str) -> UpstoxFullQuoteV3:
        """Read exactly one quote; no response body or token crosses this boundary."""
        if (
            _ISIN.fullmatch(isin) is None
            or _SYMBOL.fullmatch(symbol) is None
            or not _valid_token(access_token)
        ):
            raise UpstoxFullQuoteUnavailableError("full quote request unavailable")
        instrument_key = f"NSE_EQ|{isin}"
        url = f"{UPSTOX_FULL_QUOTE_URL_V3}?{urlencode({'instrument_key': instrument_key})}"
        try:
            response = self._transport.get(
                url,
                {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
        except (
            HttpTransportError,
            HttpResponseBodyTooLarge,
            HttpResponseHeadersInvalid,
        ):
            raise UpstoxFullQuoteUnavailableError(
                "full quote request unavailable"
            ) from None
        if response.status_code == 401:
            raise UpstoxFullQuoteAuthenticationError("full quote authentication failed")
        if response.status_code == 403:
            raise UpstoxFullQuoteAuthorizationError("full quote authorization failed")
        if response.status_code == 429:
            raise UpstoxFullQuoteRateLimitedError("full quote rate limited")
        if response.status_code != 200:
            raise UpstoxFullQuoteProviderResponseError(
                "full quote response unavailable"
            )
        if response.response_url not in {None, url}:
            raise UpstoxFullQuoteCorruptError("full quote response corrupt")
        try:
            quote = _parse_quote(response, instrument_key, symbol, self._clock())
        except UpstoxFullQuoteCorruptError:
            raise
        except (ArithmeticError, TypeError, ValueError, OverflowError):
            raise UpstoxFullQuoteCorruptError("full quote response corrupt") from None
        return quote


def _parse_quote(  # noqa: C901 - strict closed provider schema validation
    response: HttpResponse,
    instrument_key: str,
    symbol: str,
    retrieved_at: datetime,
) -> UpstoxFullQuoteV3:
    if len(response.body) > MAX_FULL_QUOTE_RESPONSE_BYTES_V3 or not _aware(
        retrieved_at
    ):
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    try:
        payload = json.loads(
            response.body.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_float=Decimal,
            parse_constant=_reject_constant,
        )
        _assert_depth(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError):
        raise UpstoxFullQuoteCorruptError("full quote response corrupt") from None
    outer = _object(payload)
    if set(outer) != {"status", "data"}:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    data = outer["data"]
    response_key = f"NSE_EQ:{symbol}"
    if outer["status"] != "success":
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    data_object = _object(data)
    if set(data_object) != {response_key}:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    quote = data_object[response_key]
    raw = _object(quote)
    if frozenset(raw) != _QUOTE_FIELDS:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    if raw["instrument_token"] != instrument_key or raw["symbol"] != symbol:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    ohlc = _object(raw["ohlc"])
    depth = _object(raw["depth"])
    if set(ohlc) != {"open", "high", "low", "close", "volume", "ts"} or set(depth) != {
        "buy",
        "sell",
    }:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    open_price = _positive_decimal_value(ohlc["open"])
    high = _positive_decimal_value(ohlc["high"])
    low = _positive_decimal_value(ohlc["low"])
    close = _positive_decimal_value(ohlc["close"])
    if not low <= min(open_price, close) <= max(open_price, close) <= high:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    _nonnegative_int(ohlc["volume"])
    _nonnegative_int(ohlc["ts"])
    buy = _depth_levels(depth["buy"], side="buy")
    sell = _depth_levels(depth["sell"], side="sell")
    timestamp = _provider_timestamp(raw["timestamp"])
    last_trade_time = _milliseconds(raw["last_trade_time"])
    last_price = _positive_decimal_value(raw["last_price"])
    lower = _positive_decimal_value(raw["lower_circuit_limit"])
    upper = _positive_decimal_value(raw["upper_circuit_limit"])
    if lower >= upper:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    if any(
        price > 0 and not lower <= price <= upper
        for price, _quantity, _orders in (*buy, *sell)
    ):
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    _positive_decimal_value(raw["average_price"])
    _nonnegative_decimal_value(raw["oi"])
    _finite_decimal_value(raw["net_change"])
    total_buy = _nonnegative_int(raw["total_buy_quantity"])
    total_sell = _nonnegative_int(raw["total_sell_quantity"])
    _nonnegative_decimal_value(raw["oi_day_high"])
    _nonnegative_decimal_value(raw["oi_day_low"])
    _positive_decimal_value(raw["prev_close_price"])
    year_high = _positive_decimal_value(raw["year_high"])
    year_low = _positive_decimal_value(raw["year_low"])
    if year_low > year_high:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    _nonnegative_decimal_value(raw["previous_oi"])
    _nonnegative_decimal_value(raw["indicative_equilibrium_price"])
    _positive_decimal_value(raw["reference_price"])
    _nonnegative_int(raw["indicative_equilibrium_quantity"])
    _nonnegative_int(raw["indicative_imbalance_quantity_total"])
    _nonnegative_int(raw["indicative_imbalance_quantity_market"])
    if type(raw["cas_eligible"]) is not bool:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    values: dict[str, object] = {
        "instrument_key": instrument_key,
        "symbol": symbol,
        "source": UPSTOX_FULL_QUOTE_SOURCE_V3,
        "adapter_release": UPSTOX_FULL_QUOTE_ADAPTER_RELEASE_V3,
        "quote_timestamp": _timestamp(timestamp),
        "retrieved_at": _timestamp(retrieved_at),
        "last_price": _decimal_text(last_price),
        "lower_circuit_limit": _decimal_text(lower),
        "upper_circuit_limit": _decimal_text(upper),
        "best_bid": _decimal_text(buy[0][0]),
        "best_ask": _decimal_text(sell[0][0]),
        "total_buy_quantity": total_buy,
        "total_sell_quantity": total_sell,
        "last_trade_time_millis": last_trade_time,
        "response_sha256": hashlib.sha256(response.body).hexdigest(),
    }
    return UpstoxFullQuoteV3(
        instrument_key,
        symbol,
        UPSTOX_FULL_QUOTE_SOURCE_V3,
        UPSTOX_FULL_QUOTE_ADAPTER_RELEASE_V3,
        timestamp,
        retrieved_at,
        last_price,
        lower,
        upper,
        buy[0][0],
        sell[0][0],
        total_buy,
        total_sell,
        last_trade_time,
        cast(str, values["response_sha256"]),
        _quote_identity(values),
    )


def _depth_levels(value: object, *, side: str) -> tuple[tuple[Decimal, int, int], ...]:
    if type(value) is not list:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    levels_value = cast(list[object], value)
    if len(levels_value) != 5:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    levels: list[tuple[Decimal, int, int]] = []
    for item in levels_value:
        row = _object(item)
        if set(row) != {"price", "quantity", "orders"}:
            raise UpstoxFullQuoteCorruptError("full quote response corrupt")
        price = _nonnegative_decimal_value(row["price"])
        quantity = _nonnegative_int(row["quantity"])
        orders = _nonnegative_int(row["orders"])
        if price == 0 and (quantity != 0 or orders != 0):
            raise UpstoxFullQuoteCorruptError("full quote response corrupt")
        levels.append((price, quantity, orders))
    prices = tuple(item[0] for item in levels if item[0] > 0)
    if any(item[0] == 0 for item in levels[: len(prices)]) or any(
        item[0] > 0 for item in levels[len(prices) :]
    ):
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    if side == "buy" and prices != tuple(sorted(prices, reverse=True)):
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    if side == "sell" and prices != tuple(sorted(prices)):
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    return tuple(levels)


def _object(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    return cast(dict[str, object], value)


def _provider_timestamp(value: object) -> datetime:
    if type(value) is not str or len(value) > 64:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt") from error
    if not _aware(parsed):
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    return parsed.astimezone(UTC)


def _milliseconds(value: object) -> int:
    if type(value) is not str or not value.isdigit() or len(value) > 16:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    return int(value)


def _positive_decimal_value(value: object) -> Decimal:
    result = _finite_decimal_value(value)
    if result <= 0:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    return result


def _nonnegative_decimal_value(value: object) -> Decimal:
    result = _finite_decimal_value(value)
    if result < 0:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    return result


def _finite_decimal_value(value: object) -> Decimal:
    if type(value) not in {int, Decimal}:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    result = Decimal(cast(int | Decimal, value))
    if not result.is_finite() or abs(result) > _MAX_DECIMAL:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    return result


def _nonnegative_int(value: object) -> int:
    if type(value) is not int or value < 0:
        raise UpstoxFullQuoteCorruptError("full quote response corrupt")
    return value


def _positive_decimal(value: object) -> bool:
    return type(value) is Decimal and value.is_finite() and 0 < value <= _MAX_DECIMAL


def _nonnegative_decimal(value: object) -> bool:
    return type(value) is Decimal and value.is_finite() and 0 <= value <= _MAX_DECIMAL


def _valid_instrument_key(value: object) -> bool:
    return type(value) is str and bool(
        re.fullmatch(r"NSE_EQ\|INE[A-Z0-9]{8}[0-9]", value)
    )


def _valid_token(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= 4096
        and all(0x21 <= ord(character) <= 0x7E for character in value)
    )


def _aware(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )


def _quote_identity(value: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("invalid JSON constant")


def _assert_depth(value: object, depth: int = 0) -> None:
    if depth > MAX_FULL_QUOTE_JSON_DEPTH_V3:
        raise ValueError("JSON nesting too deep")
    if type(value) is dict:
        for child in cast(dict[str, object], value).values():
            _assert_depth(child, depth + 1)
    elif type(value) is list:
        for child in cast(list[object], value):
            _assert_depth(child, depth + 1)


__all__ = [
    "UPSTOX_FULL_QUOTE_ADAPTER_RELEASE_V3",
    "UPSTOX_FULL_QUOTE_SOURCE_V3",
    "UPSTOX_FULL_QUOTE_URL_V3",
    "UpstoxFullQuoteAuthenticationError",
    "UpstoxFullQuoteAuthorizationError",
    "UpstoxFullQuoteCorruptError",
    "UpstoxFullQuoteError",
    "UpstoxFullQuoteProviderResponseError",
    "UpstoxFullQuoteRateLimitedError",
    "UpstoxFullQuoteUnavailableError",
    "UpstoxFullQuoteV3",
    "UpstoxFullQuoteV3Client",
]
