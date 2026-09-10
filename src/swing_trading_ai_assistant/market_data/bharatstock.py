"""Direct, bounded BharatStock daily prices with explicit canonical identity."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Final, Literal, NoReturn, TypeAlias, cast
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .http import (
    HttpResponseBodyTooLarge,
    HttpResponseHeadersInvalid,
    HttpTransport,
    HttpTransportError,
    UrllibHttpTransport,
)

PROVIDER_SOURCE: Final = "bharatstock-api@v1"
BharatStockPriceBasis: TypeAlias = Literal[
    "BHARATSTOCK_SOURCE_REPORTED_OHLC", "BHARATSTOCK_FACTOR_APPLIED_OHLC"
]
PRICE_BASIS: Final[BharatStockPriceBasis] = "BHARATSTOCK_SOURCE_REPORTED_OHLC"
FACTOR_APPLIED_PRICE_BASIS: Final[BharatStockPriceBasis] = (
    "BHARATSTOCK_FACTOR_APPLIED_OHLC"
)
VOLUME_BASIS: Final = "SOURCE_REPORTED"
_BASE: Final = "https://bharatstockapi.com/v1/stocks/"
_PAGE_SIZE: Final = 1000
_MAX_PAGES: Final = 40
_MAX_BODY: Final = 2 * 1024 * 1024
_ISIN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]\Z")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9&._-]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MAX_NUMBER: Final = Decimal("1e18")


def price_basis_for_adjustment(apply_adjustment: bool) -> BharatStockPriceBasis:
    if type(apply_adjustment) is not bool:
        raise ValueError("apply_adjustment must be a boolean")
    return FACTOR_APPLIED_PRICE_BASIS if apply_adjustment else PRICE_BASIS


class BharatStockError(RuntimeError):
    """A sanitized provider failure, distinct from an unexpected software error."""

    def __init__(self, category: str, *, member_local: bool) -> None:
        self.category = category
        self.member_local = member_local
        super().__init__(f"BharatStock acquisition failed: {category}")


@dataclass(frozen=True, slots=True)
class BharatStockInstrument:
    isin: str
    exchange: str
    symbol: str

    def __post_init__(self) -> None:
        if (
            type(self.isin) is not str
            or _ISIN.fullmatch(self.isin) is None
            or type(self.exchange) is not str
            or self.exchange not in {"NSE", "BSE"}
            or type(self.symbol) is not str
            or _SYMBOL.fullmatch(self.symbol) is None
        ):
            raise ValueError("invalid BharatStock instrument identity")


@dataclass(frozen=True, slots=True)
class BharatStockDailyPrice:
    """Provider OHLCV and separate optional adjustment evidence, never preprocessed."""

    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    adjusted_close: Decimal | None
    adjustment_factor: Decimal | None

    def __post_init__(self) -> None:
        values = (
            self.open,
            self.high,
            self.low,
            self.close,
            *(
                value
                for value in (self.adjusted_close, self.adjustment_factor)
                if value is not None
            ),
        )
        if (
            type(self.session) is not date
            or any(
                type(value) is not Decimal
                or not value.is_finite()
                or not 0 < value <= _MAX_NUMBER
                for value in values
            )
            or type(self.volume) is not int
            or not 0 <= self.volume < 1 << 63
            or not self.low
            <= min(self.open, self.close)
            <= max(self.open, self.close)
            <= self.high
        ):
            raise ValueError("invalid BharatStock daily price")

    def project_ohlc(
        self, *, apply_adjustment: bool = False
    ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """Select original prices or apply the reported factor once to originals."""
        price_basis_for_adjustment(apply_adjustment)
        if not apply_adjustment:
            return self.open, self.high, self.low, self.close
        factor = self.adjustment_factor
        if factor is None:
            raise ValueError("BharatStock adjustment factor is unavailable")
        with localcontext(Context(prec=64, rounding=ROUND_HALF_EVEN)):
            close = self.close * factor
            if self.adjusted_close is not None and self.adjusted_close != close:
                raise ValueError("inconsistent BharatStock adjustment")
            return self.open * factor, self.high * factor, self.low * factor, close

    def project_close(self, *, apply_adjustment: bool = False) -> Decimal:
        return self.project_ohlc(apply_adjustment=apply_adjustment)[3]


@dataclass(frozen=True, slots=True)
class BharatStockHistory:
    instrument: BharatStockInstrument
    rows: tuple[BharatStockDailyPrice, ...]
    retrieved_at: datetime
    response_sha256s: tuple[str, ...]
    request_count: int

    def __post_init__(self) -> None:
        if (
            type(self.instrument) is not BharatStockInstrument
            or type(self.rows) is not tuple
            or not 1 <= len(self.rows) <= _PAGE_SIZE * _MAX_PAGES
            or any(type(row) is not BharatStockDailyPrice for row in self.rows)
            or type(self.retrieved_at) is not datetime
            or self.retrieved_at.tzinfo is None
            or self.retrieved_at.utcoffset() != UTC.utcoffset(None)
            or type(self.response_sha256s) is not tuple
            or type(self.request_count) is not int
            or not 2 <= self.request_count <= _MAX_PAGES + 1
            or self.request_count != len(self.response_sha256s)
            or any(
                type(value) is not str or _DIGEST.fullmatch(value) is None
                for value in self.response_sha256s
            )
        ):
            raise ValueError("invalid BharatStock history")
        sessions = tuple(row.session for row in self.rows)
        if sessions != tuple(sorted(set(sessions))):
            raise ValueError("invalid BharatStock history sessions")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> Request | None:
        return None


def _transport() -> HttpTransport:
    return UrllibHttpTransport(
        timeout_seconds=30,
        max_body_bytes=_MAX_BODY,
        opener=build_opener(_NoRedirect()).open,
    )


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValueError("non-finite JSON value")


def _decode(body: bytes) -> dict[str, object]:
    try:
        value: object = json.loads(
            body.decode("utf-8"),
            parse_float=Decimal,
            parse_constant=_invalid_constant,
            object_pairs_hook=_json_object,
        )
    except (ValueError, UnicodeError, RecursionError):
        raise BharatStockError("RESPONSE_INVALID", member_local=True) from None
    if type(value) is not dict:
        raise BharatStockError("RESPONSE_INVALID", member_local=True)
    return cast(dict[str, object], value)


def _decimal(value: object) -> Decimal:
    if type(value) not in {int, Decimal}:
        raise ValueError("invalid price value")
    result = Decimal(cast(int | Decimal, value))
    if not result.is_finite() or not 0 < result <= _MAX_NUMBER:
        raise ValueError("invalid price value")
    return result


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else _decimal(value)


def _price(value: object, start: date, end: date) -> BharatStockDailyPrice:
    if type(value) is not dict:
        raise ValueError("invalid daily price")
    row = cast(dict[str, object], value)
    raw_date = row.get("trade_date")
    if type(raw_date) is not str:
        raise ValueError("invalid trade date")
    session = date.fromisoformat(raw_date)
    if session.isoformat() != raw_date or not start <= session <= end:
        raise ValueError("trade date outside requested range")
    volume = row.get("volume")
    if type(volume) is not int:
        raise ValueError("invalid volume")
    return BharatStockDailyPrice(
        session,
        _decimal(row.get("open")),
        _decimal(row.get("high")),
        _decimal(row.get("low")),
        _decimal(row.get("close")),
        volume,
        _optional_decimal(row.get("adjusted_close")),
        _optional_decimal(row.get("adjustment_factor")),
    )


def _page_metadata(
    payload: dict[str, object],
    page: int,
) -> tuple[list[object], int, int]:
    raw = payload.get("pagination")
    data = payload.get("data")
    if type(raw) is not dict or type(data) is not list:
        raise BharatStockError("PAGINATION_INVALID", member_local=True)
    meta = cast(dict[str, object], raw)
    rows = cast(list[object], data)
    fields = tuple(
        meta.get(key) for key in ("page", "page_size", "total_items", "total_pages")
    )
    if any(type(value) is not int for value in fields):
        raise BharatStockError("PAGINATION_INVALID", member_local=True)
    actual_page, page_size, total_items, total_pages = cast(
        tuple[int, int, int, int], fields
    )
    calculated_pages = (total_items + _PAGE_SIZE - 1) // _PAGE_SIZE
    if (
        actual_page != page
        or page_size != _PAGE_SIZE
        or not 0 <= total_items <= _PAGE_SIZE * _MAX_PAGES
        or total_pages != calculated_pages
        and not (total_items == 0 and total_pages == 1)
        or not 0 <= total_pages <= _MAX_PAGES
        or len(rows) != min(_PAGE_SIZE, max(0, total_items - (page - 1) * _PAGE_SIZE))
    ):
        raise BharatStockError("PAGINATION_INVALID", member_local=True)
    return rows, total_items, total_pages


def _validate_history_request(
    instrument: BharatStockInstrument, start: date, end: date
) -> None:
    if type(instrument) is not BharatStockInstrument:
        raise ValueError("invalid BharatStock instrument")
    instrument.__post_init__()
    if (
        type(start) is not date
        or type(end) is not date
        or not start <= end
        or (end - start).days > 36525
    ):
        raise ValueError("invalid BharatStock date range")


class BharatStockClient:
    """One serial, bounded acquisition run; shared failures stop further effects."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        transport: HttpTransport | None = None,
        max_requests: int = 2000,
    ) -> None:
        if type(max_requests) is not int or not 1 <= max_requests <= 2000:
            raise ValueError("invalid BharatStock request budget")
        self._api_key = api_key
        self._transport = _transport() if transport is None else transport
        self._max_requests = max_requests
        self._requests_used = 0
        self._shared_failure: str | None = None

    @property
    def requests_used(self) -> int:
        return self._requests_used

    def _stop(self, category: str) -> NoReturn:
        self._shared_failure = category
        raise BharatStockError(category, member_local=False)

    def _request_headers(self) -> dict[str, str]:
        if self._shared_failure is not None:
            self._stop(self._shared_failure)
        if self._requests_used >= self._max_requests:
            self._stop("REQUEST_BUDGET_EXHAUSTED")
        if self._api_key is None:
            self._api_key = os.environ.get("BHARATSTOCK_API_KEY")
        key = self._api_key
        if (
            type(key) is not str
            or not 1 <= len(key) <= 512
            or any(not 33 <= ord(char) <= 126 for char in key)
        ):
            self._stop("AUTHENTICATION")
        return {"X-API-Key": key, "Accept": "application/json"}

    def _get(self, url: str) -> tuple[dict[str, object], str]:
        headers = self._request_headers()
        self._requests_used += 1
        try:
            response = self._transport.get(url, headers)
        except HttpTransportError:
            self._stop("TRANSPORT_FAILED")
        except (HttpResponseBodyTooLarge, HttpResponseHeadersInvalid):
            self._stop("RESPONSE_LIMIT_EXCEEDED")
        finally:
            headers.clear()
        if len(response.body) > _MAX_BODY:
            self._stop("RESPONSE_LIMIT_EXCEEDED")
        status = response.status_code
        if 300 <= status < 400 or response.response_url not in {None, url}:
            self._stop("REDIRECT_REJECTED")
        if status in {401, 403}:
            self._stop("AUTHENTICATION" if status == 401 else "AUTHORIZATION")
        if status == 429:
            self._stop("RATE_LIMITED")
        if status == 408 or status >= 500:
            self._stop("PROVIDER_UNAVAILABLE")
        if status != 200:
            raise BharatStockError(
                "NOT_FOUND" if status == 404 else "REQUEST_REJECTED", member_local=True
            )
        return _decode(response.body), hashlib.sha256(response.body).hexdigest()

    def history(
        self,
        instrument: BharatStockInstrument,
        start: date,
        end: date,
    ) -> BharatStockHistory:
        _validate_history_request(instrument, start, end)
        base = _BASE + instrument.isin
        identity, identity_digest = self._get(
            base + "?" + urlencode({"exchange": instrument.exchange})
        )
        if any(
            identity.get(name) != getattr(instrument, name)
            for name in ("isin", "exchange", "symbol")
        ):
            raise BharatStockError("IDENTITY_MISMATCH", member_local=True)
        rows: list[BharatStockDailyPrice] = []
        digests = [identity_digest]
        expected: tuple[int, int] | None = None
        for page in range(1, _MAX_PAGES + 1):
            url = (
                base
                + "/prices?"
                + urlencode(
                    {
                        "exchange": instrument.exchange,
                        "from": start.isoformat(),
                        "to": end.isoformat(),
                        "page": page,
                        "page_size": _PAGE_SIZE,
                    }
                )
            )
            payload, digest = self._get(url)
            data, total_items, total_pages = _page_metadata(payload, page)
            if expected is not None and expected != (total_items, total_pages):
                raise BharatStockError("PAGINATION_INVALID", member_local=True)
            expected = (total_items, total_pages)
            digests.append(digest)
            try:
                for value in data:
                    row = _price(value, start, end)
                    if rows and row.session >= rows[-1].session:
                        raise ValueError("duplicate or unordered provider sessions")
                    rows.append(row)
            except ValueError:
                raise BharatStockError(
                    "PRICE_EVIDENCE_INVALID", member_local=True
                ) from None
            if page >= total_pages:
                break
        if not rows:
            raise BharatStockError("EMPTY_HISTORY", member_local=True)
        return BharatStockHistory(
            instrument,
            tuple(reversed(rows)),
            datetime.now(UTC),
            tuple(digests),
            len(digests),
        )
