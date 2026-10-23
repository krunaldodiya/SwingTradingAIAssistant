"""Direct, bounded BharatStock daily prices with explicit canonical identity."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal, NoReturn, TypeAlias, cast
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .http import (
    HttpResponse,
    HttpResponseBodyTooLarge,
    HttpResponseHeadersInvalid,
    HttpTransport,
    HttpTransportError,
    UrllibHttpTransport,
)

PROVIDER_SOURCE: Final = "bharatstock-api@v1"
BharatStockPriceBasis: TypeAlias = Literal["BHARATSTOCK_SOURCE_REPORTED_OHLC"]
PRICE_BASIS: Final[BharatStockPriceBasis] = "BHARATSTOCK_SOURCE_REPORTED_OHLC"
VOLUME_BASIS: Final = "SOURCE_REPORTED"
_BASE: Final = "https://bharatstockapi.com/v1/stocks/"
_PAGE_SIZE: Final = 1000
_MAX_PAGES: Final = 40
_MAX_BODY: Final = 2 * 1024 * 1024
_ISIN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]\Z")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9&._-]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MAX_NUMBER: Final = Decimal("1e18")
_MAX_DECIMAL_COEFFICIENT_DIGITS: Final = 128
_MIN_DECIMAL_EXPONENT: Final = -128
_MAX_DECIMAL_EXPONENT: Final = 128
_MAX_CANONICAL_DECIMAL_CHARACTERS: Final = 258
_MAX_DECIMAL_OBJECT_BYTES: Final = 192
_MAX_JSON_DECIMAL_CHARACTERS: Final = 512
_MIN_PROVIDER_INTEGER: Final = -(1 << 63)
_MAX_PROVIDER_INTEGER: Final = (1 << 63) - 1


def _bounded_decimal_representation(value: object) -> bool:
    """Keep provider Decimal values bounded before downstream canonicalization."""
    if (
        type(value) is not Decimal
        or sys.getsizeof(value) > _MAX_DECIMAL_OBJECT_BYTES
        or not value.is_finite()
    ):
        return False
    sign, digits, exponent = value.as_tuple()
    if (
        type(exponent) is not int
        or len(digits) > _MAX_DECIMAL_COEFFICIENT_DIGITS
        or not _MIN_DECIMAL_EXPONENT <= exponent <= _MAX_DECIMAL_EXPONENT
    ):
        return False
    fixed_characters = (
        len(digits) + exponent
        if exponent >= 0
        else len(digits) + 1
        if -exponent < len(digits)
        else 2 - exponent
    ) + sign
    return fixed_characters <= _MAX_CANONICAL_DECIMAL_CHARACTERS


def _positive_decimal(value: object) -> bool:
    return type(value) is Decimal and value.is_finite() and 0 < value <= _MAX_NUMBER


def _bounded_provider_positive_decimal(value: object) -> bool:
    return _positive_decimal(value) and _bounded_decimal_representation(value)


def _bounded_json_decimal(value: str) -> Decimal:
    if type(value) is not str or len(value) > _MAX_JSON_DECIMAL_CHARACTERS:
        raise ValueError("invalid price value")
    result = Decimal(value)
    if not _bounded_decimal_representation(result):
        raise ValueError("invalid price value")
    return result


def _bounded_json_int(value: str) -> int:
    if type(value) is not str or len(value) > 20:
        raise ValueError("invalid integer value")
    result = int(value)
    if not _MIN_PROVIDER_INTEGER <= result <= _MAX_PROVIDER_INTEGER:
        raise ValueError("invalid integer value")
    return result


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
            or any(not _positive_decimal(value) for value in values)
            or type(self.volume) is not int
            or not 0 <= self.volume < 1 << 63
            or not self.low
            <= min(self.open, self.close)
            <= max(self.open, self.close)
            <= self.high
        ):
            raise ValueError("invalid BharatStock daily price")


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
            parse_float=_bounded_json_decimal,
            parse_int=_bounded_json_int,
            parse_constant=_invalid_constant,
            object_pairs_hook=_json_object,
        )
    except (ArithmeticError, ValueError, UnicodeError, RecursionError):
        raise BharatStockError("RESPONSE_INVALID", member_local=True) from None
    if type(value) is not dict:
        raise BharatStockError("RESPONSE_INVALID", member_local=True)
    return cast(dict[str, object], value)


def _decimal(value: object) -> Decimal:
    if type(value) not in {int, Decimal}:
        raise ValueError("invalid price value")
    if (
        type(value) is int
        and not _MIN_PROVIDER_INTEGER <= value <= _MAX_PROVIDER_INTEGER
    ):
        raise ValueError("invalid price value")
    result = Decimal(cast(int | Decimal, value))
    if not _bounded_provider_positive_decimal(result):
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
        session_cache_root: Path | None = None,
    ) -> None:
        if type(max_requests) is not int or not 1 <= max_requests <= 2000:
            raise ValueError("invalid BharatStock request budget")
        if session_cache_root is not None and not session_cache_root.is_absolute():
            raise ValueError("invalid session cache root")
        self._api_key = api_key
        self._transport = _transport() if transport is None else transport
        self._max_requests = max_requests
        self._session_cache_root = session_cache_root
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

    def _request(
        self, url: str, *, effect_guard: Callable[[], None] | None = None
    ) -> HttpResponse:
        if effect_guard is not None:
            effect_guard()
        headers = self._request_headers()
        try:
            if effect_guard is not None:
                effect_guard()
            self._requests_used += 1
            try:
                response = self._transport.get(url, headers)
            except HttpTransportError:
                self._stop("TRANSPORT_FAILED")
            except (HttpResponseBodyTooLarge, HttpResponseHeadersInvalid):
                self._stop("RESPONSE_LIMIT_EXCEEDED")
        finally:
            headers.clear()
        if effect_guard is not None:
            effect_guard()
        return response

    def _get(
        self, url: str, *, effect_guard: Callable[[], None] | None = None
    ) -> tuple[dict[str, object], str]:
        response = self._request(url, effect_guard=effect_guard)
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
        *,
        effect_guard: Callable[[], None] | None = None,
        expected_sessions: tuple[date, ...] | None = None,
    ) -> BharatStockHistory:
        _validate_history_request(instrument, start, end)
        if self._session_cache_root is not None and expected_sessions is not None:
            return self._cached_history(
                instrument,
                start,
                end,
                expected_sessions,
                effect_guard=effect_guard,
            )
        history = self._network_history(
            instrument, start, end, effect_guard=effect_guard
        )
        if self._session_cache_root is not None:
            self._write_cached_sessions(instrument, history)
        return history

    def _network_history(
        self,
        instrument: BharatStockInstrument,
        start: date,
        end: date,
        *,
        effect_guard: Callable[[], None] | None = None,
    ) -> BharatStockHistory:
        base = _BASE + instrument.isin
        identity, identity_digest = self._get(
            base + "?" + urlencode({"exchange": instrument.exchange}),
            effect_guard=effect_guard,
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
            payload, digest = self._get(url, effect_guard=effect_guard)
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

    def _session_cache_path(
        self, instrument: BharatStockInstrument, session: date
    ) -> Path:
        root = self._session_cache_root
        if root is None:
            raise ValueError("missing session cache root")
        return (
            root
            / "bharatstock-session-cache-v1"
            / f"isin={instrument.isin}"
            / f"exchange={instrument.exchange}"
            / f"session={session.isoformat()}.json"
        )

    def _read_cached_session(
        self, instrument: BharatStockInstrument, session: date
    ) -> tuple[BharatStockDailyPrice, tuple[str, ...], int, datetime] | None:
        path = self._session_cache_path(instrument, session)
        try:
            payload = json.loads(path.read_bytes())
        except (OSError, ValueError):
            return None
        if type(payload) is not dict:
            return None
        value = cast(dict[str, object], payload)
        if (
            value.get("schema") != "bharatstock-session-cache@v1"
            or value.get("provider") != PROVIDER_SOURCE
            or value.get("price_basis") != PRICE_BASIS
            or value.get("volume_basis") != VOLUME_BASIS
            or value.get("session") != session.isoformat()
            or value.get("isin") != instrument.isin
            or value.get("exchange") != instrument.exchange
            or value.get("symbol") != instrument.symbol
        ):
            return None
        try:
            row = BharatStockDailyPrice(
                session,
                Decimal(str(value["open"])),
                Decimal(str(value["high"])),
                Decimal(str(value["low"])),
                Decimal(str(value["close"])),
                int(cast(int, value["volume"])),
                Decimal(str(value["adjusted_close"]))
                if value.get("adjusted_close") is not None
                else None,
                Decimal(str(value["adjustment_factor"]))
                if value.get("adjustment_factor") is not None
                else None,
            )
            raw_digests = cast(list[object], value["response_sha256s"])
            digests = tuple(cast(list[str], raw_digests))
            request_count = int(cast(int, value["request_count"]))
            retrieved_at = datetime.fromisoformat(cast(str, value["retrieved_at"]))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            return None
        if (
            any(
                type(item) is not str or _DIGEST.fullmatch(item) is None
                for item in digests
            )
            or request_count != len(digests)
            or not 2 <= request_count <= _MAX_PAGES + 1
            or retrieved_at.tzinfo is None
            or retrieved_at.utcoffset() != UTC.utcoffset(None)
        ):
            return None
        return row, digests, request_count, retrieved_at

    def _write_cached_sessions(
        self,
        instrument: BharatStockInstrument,
        history: BharatStockHistory,
    ) -> None:
        if self._session_cache_root is None:
            return
        for row in history.rows:
            path = self._session_cache_path(instrument, row.session)
            payload = {
                "schema": "bharatstock-session-cache@v1",
                "provider": PROVIDER_SOURCE,
                "price_basis": PRICE_BASIS,
                "volume_basis": VOLUME_BASIS,
                "isin": instrument.isin,
                "exchange": instrument.exchange,
                "symbol": instrument.symbol,
                "session": row.session.isoformat(),
                "open": str(row.open),
                "high": str(row.high),
                "low": str(row.low),
                "close": str(row.close),
                "volume": row.volume,
                "adjusted_close": (
                    None if row.adjusted_close is None else str(row.adjusted_close)
                ),
                "adjustment_factor": (
                    None
                    if row.adjustment_factor is None
                    else str(row.adjustment_factor)
                ),
                "response_sha256s": list(history.response_sha256s),
                "request_count": history.request_count,
                "retrieved_at": history.retrieved_at.isoformat(),
            }
            temporary = path.with_name(path.name + ".tmp")
            try:
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                descriptor = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                    0o600,
                )
                try:
                    data = json.dumps(
                        payload,
                        ensure_ascii=True,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                    os.write(descriptor, data)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.replace(temporary, path)
            except OSError:
                with suppress(OSError):
                    os.unlink(temporary)
                continue

    def _cached_history(  # noqa: C901 - explicit cache/compose boundary
        self,
        instrument: BharatStockInstrument,
        start: date,
        end: date,
        expected_sessions: tuple[date, ...],
        *,
        effect_guard: Callable[[], None] | None = None,
    ) -> BharatStockHistory:
        sessions = tuple(expected_sessions)
        if (
            not sessions
            or sessions != tuple(sorted(set(sessions)))
            or sessions[0] < start
            or sessions[-1] > end
        ):
            raise ValueError("invalid expected sessions")
        records: list[tuple[BharatStockDailyPrice, tuple[str, ...], int, datetime]] = []
        missing: list[date] = []
        for session in sessions:
            record = self._read_cached_session(instrument, session)
            if record is None:
                missing.append(session)
            else:
                records.append(record)
        if missing:
            try:
                fetched = self._network_history(
                    instrument,
                    missing[0],
                    missing[-1],
                    effect_guard=effect_guard,
                )
            except BharatStockError as error:
                if not (error.member_local and error.category == "EMPTY_HISTORY"):
                    raise
                fetched = None
            if fetched is not None:
                self._write_cached_sessions(instrument, fetched)
                fetched_rows = {row.session: row for row in fetched.rows}
                records.extend(
                    (
                        fetched_rows[session],
                        fetched.response_sha256s,
                        fetched.request_count,
                        fetched.retrieved_at,
                    )
                    for session in missing
                    if session in fetched_rows
                )
        rows = tuple(
            sorted((record[0] for record in records), key=lambda item: item.session)
        )
        if not rows:
            raise BharatStockError("EMPTY_HISTORY", member_local=True)
        seen: set[str] = set()
        digests: list[str] = []
        for record in records:
            for digest in record[1]:
                if digest not in seen:
                    seen.add(digest)
                    digests.append(digest)
        return BharatStockHistory(
            instrument,
            rows,
            max(record[3] for record in records),
            tuple(digests),
            len(digests),
        )
