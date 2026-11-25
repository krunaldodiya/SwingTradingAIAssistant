"""Read-only Angel One SmartAPI connector.

Only the documented read endpoints for login, holdings, positions, the order
book, the trade book, and GTT rule listing are implemented. No order placement,
modification, cancellation, position conversion, GTT mutation, profile, or
generic request surface exists.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import socket
import struct
import time
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, DecimalException, InvalidOperation, localcontext
from typing import Any, TypeVar, cast

from .credentials import missing_credentials
from .errors import PortfolioError
from .records import (
    GttRecord,
    GttSnapshot,
    HoldingRow,
    HoldingsSnapshot,
    OrderRecord,
    OrdersSnapshot,
    PositionRecord,
    PositionsSnapshot,
    Section,
    TradeRecord,
    TradesSnapshot,
)

Transport = Callable[
    [str, str, Mapping[str, str], bytes | None], tuple[int, dict[str, object]]
]

BASE_URL = "https://apiconnect.angelone.in"
LOGIN_PATH = "/rest/auth/angelbroking/user/v1/loginByPassword"
HOLDINGS_PATH = "/rest/secure/angelbroking/portfolio/v1/getAllHolding"
POSITIONS_PATH = "/rest/secure/angelbroking/order/v1/getPosition"
ORDERS_PATH = "/rest/secure/angelbroking/order/v1/getOrderBook"
TRADES_PATH = "/rest/secure/angelbroking/order/v1/getTradeBook"
GTT_LIST_PATH = "/rest/secure/angelbroking/gtt/v1/ruleList"
ALLOWED_URLS = frozenset(
    {
        f"{BASE_URL}{LOGIN_PATH}",
        f"{BASE_URL}{HOLDINGS_PATH}",
        f"{BASE_URL}{POSITIONS_PATH}",
        f"{BASE_URL}{ORDERS_PATH}",
        f"{BASE_URL}{TRADES_PATH}",
        f"{BASE_URL}{GTT_LIST_PATH}",
    }
)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_ABS_DECIMAL = Decimal("1e18")
MIN_ABS_DECIMAL = Decimal("1e-18")
GTT_PAGE_SIZE = 50
MAX_GTT_PAGES = 20
RECONCILIATION_TOLERANCE = Decimal("5.00")
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&.-]{0,19}$")
_EXCHANGE = re.compile(r"^[A-Z]{2,8}$")
_IDENTIFIER = re.compile(r"^[!-~]{1,128}$")
_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
T = TypeVar("T")


@dataclass(frozen=True, repr=False)
class AngelOneCredentials:
    api_key: str
    client_code: str
    pin: str
    totp_secret: str

    def __repr__(self) -> str:
        return "AngelOneCredentials(<redacted>)"


def load_credentials(
    prefix: str, environ: Mapping[str, str] | None = None
) -> AngelOneCredentials:
    source = environ if environ is not None else os.environ
    missing = missing_credentials(prefix, source)
    if missing:
        raise PortfolioError(
            "CREDENTIALS_MISSING",
            f"missing environment variables: {', '.join(missing)}",
        )
    return AngelOneCredentials(
        api_key=source[f"{prefix}_API_KEY"].strip(),
        client_code=source[f"{prefix}_CLIENT_CODE"].strip(),
        pin=source[f"{prefix}_PIN"].strip(),
        totp_secret=source[f"{prefix}_TOTP_SECRET"].strip().replace(" ", "").upper(),
    )


def generate_totp(secret: str, *, at: float | None = None) -> str:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    try:
        key = base64.b32decode(normalized + padding)
    except (binascii.Error, ValueError) as exc:
        raise PortfolioError(
            "MALFORMED_CREDENTIAL", "TOTP secret is not valid base32"
        ) from exc
    if not key:
        raise PortfolioError("MALFORMED_CREDENTIAL", "TOTP secret is empty")
    counter = int(at if at is not None else time.time()) // 30
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()  # noqa: S324
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def _local_ip() -> str:
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _mac_address() -> str:
    try:
        with open("/sys/class/net/eth0/address", encoding="ascii") as handle:
            value = handle.read().strip()
    except OSError:
        return "00:00:00:00:00:00"
    return value or "00:00:00:00:00:00"


def _public_ip(environ: Mapping[str, str]) -> str:
    return environ.get("PORTFOLIO_PUBLIC_IP", "").strip() or _local_ip()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: Any,
        headers: Any,
        newurl: str,
    ) -> Any:
        raise PortfolioError("PROVIDER_UNAVAILABLE", "broker redirect refused")


def _decode_body(raw: bytes) -> object:
    if len(raw) > MAX_RESPONSE_BYTES:
        raise PortfolioError("MALFORMED_RESPONSE", "broker response is too large")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise PortfolioError(
            "MALFORMED_RESPONSE", "Angel One returned invalid JSON"
        ) from None


def _default_transport(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None
) -> tuple[int, dict[str, object]]:
    if url not in ALLOWED_URLS:
        raise PortfolioError("PROVIDER_UNAVAILABLE", "invalid broker endpoint")
    request_headers = dict(headers)
    request_headers.setdefault("User-Agent", "swing-trading-ai-assistant/0.1")
    request = urllib.request.Request(  # noqa: S310
        url, data=body, headers=request_headers, method=method
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=20) as response:
            if response.geturl() != url:
                raise PortfolioError(
                    "PROVIDER_UNAVAILABLE", "broker endpoint redirected"
                )
            payload: object = _decode_body(response.read(MAX_RESPONSE_BYTES + 1))
            status = response.status
    except PortfolioError:
        raise
    except urllib.error.HTTPError as exc:
        try:
            payload = _decode_body(exc.read(MAX_RESPONSE_BYTES + 1))
        except PortfolioError:
            payload = {}
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        raise PortfolioError(
            "PROVIDER_UNAVAILABLE", "Angel One is unavailable"
        ) from None
    if not isinstance(payload, dict):
        raise PortfolioError(
            "MALFORMED_RESPONSE", "Angel One returned an invalid payload"
        )
    return status, cast("dict[str, object]", payload)


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid") from exc
    if not number.is_finite():
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid")
    magnitude = abs(number)
    if magnitude != 0 and (magnitude > MAX_ABS_DECIMAL or magnitude < MIN_ABS_DECIMAL):
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is out of range")
    return number


def _optional_decimal(value: object, field: str) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _decimal(value, field)


def _q2(value: Decimal) -> Decimal:
    try:
        return value.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise PortfolioError(
            "MALFORMED_RESPONSE", "broker number is out of range"
        ) from exc


def _money(value: Decimal) -> float:
    return float(_q2(value))


def _percent(value: Decimal | None) -> float | None:
    return None if value is None else float(_q2(value))


class AngelOneClient:
    """One short-lived, read-only Angel One session."""

    broker = "ANGEL_ONE"
    capabilities = frozenset(Section)

    def __init__(
        self,
        credentials: AngelOneCredentials,
        *,
        transport: Transport | None = None,
        clock: Callable[[], float] | None = None,
        public_ip: str | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._credentials = credentials
        self._transport = transport or _default_transport
        self._clock = clock or time.time
        self._environ = environ if environ is not None else os.environ
        self._public_ip = public_ip or _public_ip(self._environ)
        self._local_ip = _local_ip()
        self._mac = _mac_address()
        self._token: str | None = None
        self._authenticated_client_code: str | None = None

    def __repr__(self) -> str:
        return "AngelOneClient(<redacted>)"

    @property
    def authenticated_client_code(self) -> str | None:
        return self._authenticated_client_code

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": self._local_ip,
            "X-ClientPublicIP": self._public_ip,
            "X-MACAddress": self._mac,
            "X-PrivateKey": self._credentials.api_key,
        }

    def login(self) -> None:
        body = json.dumps(
            {
                "clientcode": self._credentials.client_code,
                "password": self._credentials.pin,
                "totp": generate_totp(self._credentials.totp_secret, at=self._clock()),
            }
        ).encode("utf-8")
        status, payload = self._transport(
            "POST", f"{BASE_URL}{LOGIN_PATH}", self._headers(), body
        )
        if status != 200 or payload.get("status") is not True:
            raise self._login_error(status, payload)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise PortfolioError(
                "MALFORMED_RESPONSE", "Angel One login response is invalid"
            )
        values = cast("dict[str, object]", data)
        token = values.get("jwtToken")
        if not isinstance(token, str) or not token:
            raise PortfolioError(
                "MALFORMED_RESPONSE", "Angel One login response has no token"
            )
        self._token = token
        authenticated = values.get("clientcode")
        if isinstance(authenticated, str) and authenticated:
            self._authenticated_client_code = authenticated

    def holdings(self) -> HoldingsSnapshot:
        if self._token is None:
            raise PortfolioError("AUTH_FAILED", "login is required before holdings")
        headers = self._headers()
        headers["Authorization"] = f"Bearer {self._token}"
        status, payload = self._transport(
            "GET", f"{BASE_URL}{HOLDINGS_PATH}", headers, None
        )
        if status != 200 or payload.get("status") is not True:
            raise self._holdings_error(status, payload)
        data = payload.get("data")
        if isinstance(data, list):
            raw_rows: object = cast("list[object]", data)
            totals: object = None
        elif isinstance(data, dict):
            mapping = cast("dict[str, object]", data)
            raw_rows = mapping.get("holdings")
            totals = mapping.get("totalholding")
        else:
            raise PortfolioError(
                "MALFORMED_RESPONSE", "Angel One holdings response is invalid"
            )
        if not isinstance(raw_rows, list):
            raise PortfolioError(
                "MALFORMED_RESPONSE", "Angel One holdings list is missing"
            )
        with localcontext() as context:
            context.prec = 60
            try:
                rows = tuple(
                    _holding_row(row) for row in cast("list[object]", raw_rows)
                )
            except DecimalException as exc:
                raise PortfolioError(
                    "MALFORMED_RESPONSE", "Angel One holdings values are invalid"
                ) from exc
            raw_row_list = cast("list[object]", raw_rows)
            limitations: list[str] = []
            if any(row.t1_quantity > 0 for row in rows):
                limitations.append("T1_QUANTITY_PRESENT")
            if _pnl_inconsistent(raw_row_list, rows):
                limitations.append("PNL_INCONSISTENT")
            invested = sum((row.invested for row in rows), Decimal("0"))
            current = sum((row.current for row in rows), Decimal("0"))
            overall_pnl = sum((row.pnl for row in rows), Decimal("0"))
            overall_pnl_pct = (overall_pnl / invested * 100) if invested > 0 else None
            if not rows or any(row.previous_close is None for row in rows):
                day_change: Decimal | None = None
                day_change_pct: Decimal | None = None
                limitations.append("DAY_CHANGE_UNAVAILABLE")
            else:
                day_change = sum(
                    (row.day_change for row in rows if row.day_change is not None),
                    Decimal("0"),
                )
                previous_value = current - day_change
                day_change_pct = (
                    (day_change / previous_value * 100) if previous_value > 0 else None
                )
            _reconcile(totals, invested, current, overall_pnl, limitations)
            ordered = tuple(sorted(rows, key=lambda row: (-row.current, row.symbol)))
            return HoldingsSnapshot(
                rows=ordered,
                invested=_q2(invested),
                current=_q2(current),
                overall_pnl=_q2(overall_pnl),
                overall_pnl_pct=(
                    None if overall_pnl_pct is None else _q2(overall_pnl_pct)
                ),
                day_change=None if day_change is None else _q2(day_change),
                day_change_pct=(
                    None if day_change_pct is None else _q2(day_change_pct)
                ),
                limitations=tuple(limitations),
                retrieved_at=self._retrieved_at(),
            )

    def _require_token(self) -> str:
        if self._token is None:
            raise PortfolioError("AUTH_FAILED", "login is required before records")
        return self._token

    def _authorized_headers(self) -> dict[str, str]:
        headers = self._headers()
        headers["Authorization"] = f"Bearer {self._require_token()}"
        return headers

    def _retrieved_at(self) -> str:
        return datetime.fromtimestamp(self._clock(), tz=UTC).isoformat(
            timespec="seconds"
        )

    def _get_list(self, path: str, label: str) -> list[object]:
        status, payload = self._transport(
            "GET", f"{BASE_URL}{path}", self._authorized_headers(), None
        )
        return self._records_data(status, payload, label)

    def _post_list(
        self, path: str, body: Mapping[str, object], label: str
    ) -> list[object]:
        status, payload = self._transport(
            "POST",
            f"{BASE_URL}{path}",
            self._authorized_headers(),
            json.dumps(body).encode("utf-8"),
        )
        return self._records_data(status, payload, label)

    def _records_data(
        self,
        status: int,
        payload: Mapping[str, object],
        label: str,
    ) -> list[object]:
        if status != 200 or payload.get("status") is not True:
            raise self._records_error(status, payload, label)
        if "data" not in payload:
            raise PortfolioError(
                "MALFORMED_RESPONSE", f"Angel One {label} data is missing"
            )
        data = payload["data"]
        if data is None:
            return []
        if not isinstance(data, list):
            raise PortfolioError(
                "MALFORMED_RESPONSE", f"Angel One {label} rows are invalid"
            )
        return cast("list[object]", data)

    def positions(self) -> PositionsSnapshot:
        records, limitations = _parse_records(
            self._get_list(POSITIONS_PATH, "positions"),
            _position_row,
            "positions",
        )
        return PositionsSnapshot(
            rows=tuple(records),
            limitations=tuple(dict.fromkeys(limitations)),
            retrieved_at=self._retrieved_at(),
        )

    def orders(self) -> OrdersSnapshot:
        records, limitations = _parse_records(
            self._get_list(ORDERS_PATH, "orders"),
            _order_row,
            "orders",
        )
        return OrdersSnapshot(
            rows=tuple(records),
            limitations=tuple(dict.fromkeys(limitations)),
            retrieved_at=self._retrieved_at(),
        )

    def trades(self) -> TradesSnapshot:
        records, limitations = _parse_records(
            self._get_list(TRADES_PATH, "trades"),
            _trade_row,
            "trades",
        )
        return TradesSnapshot(
            rows=tuple(records),
            limitations=tuple(dict.fromkeys(limitations)),
            retrieved_at=self._retrieved_at(),
        )

    def gtt_rules(self) -> GttSnapshot:
        records: list[GttRecord] = []
        limitations: list[str] = []
        for page in range(1, MAX_GTT_PAGES + 1):
            rows = self._post_list(
                GTT_LIST_PATH,
                {"status": ["FORALL"], "page": page, "count": GTT_PAGE_SIZE},
                "GTT rules",
            )
            page_records, page_limitations = _parse_records(rows, _gtt_row, "GTT rules")
            records.extend(page_records)
            limitations.extend(page_limitations)
            if len(rows) < GTT_PAGE_SIZE:
                break
        else:
            limitations.append("GTT_RESULTS_TRUNCATED")
        return GttSnapshot(
            rows=tuple(records),
            limitations=tuple(dict.fromkeys(limitations)),
            retrieved_at=self._retrieved_at(),
        )

    def _login_error(
        self, status: int, payload: Mapping[str, object]
    ) -> PortfolioError:
        message = str(payload.get("message") or "").lower()
        if "ip" in message and ("whitelist" in message or "static" in message):
            return PortfolioError(
                "IP_NOT_WHITELISTED",
                "Angel One rejected this public IP; add it to the SmartAPI whitelist",
            )
        if status in {401, 403} or payload.get("errorcode"):
            return PortfolioError("AUTH_FAILED", "Angel One rejected the credentials")
        return PortfolioError("PROVIDER_UNAVAILABLE", "Angel One login failed")

    def _holdings_error(
        self, status: int, payload: Mapping[str, object]
    ) -> PortfolioError:
        message = str(payload.get("message") or "").lower()
        if "ip" in message and ("whitelist" in message or "static" in message):
            return PortfolioError(
                "IP_NOT_WHITELISTED",
                "Angel One rejected this public IP; add it to the SmartAPI whitelist",
            )
        if status in {401, 403}:
            return PortfolioError("AUTH_FAILED", "Angel One session is not authorized")
        return PortfolioError(
            "PROVIDER_UNAVAILABLE", "Angel One holdings request failed"
        )

    def _records_error(
        self,
        status: int,
        payload: Mapping[str, object],
        label: str,
    ) -> PortfolioError:
        message = str(payload.get("message") or "").lower()
        if "ip" in message and ("whitelist" in message or "static" in message):
            return PortfolioError(
                "IP_NOT_WHITELISTED",
                "Angel One rejected this public IP; add it to the SmartAPI whitelist",
            )
        if status in {401, 403}:
            return PortfolioError("AUTH_FAILED", "Angel One session is not authorized")
        return PortfolioError(
            "PROVIDER_UNAVAILABLE", f"Angel One {label} request failed"
        )


def _holding_row(raw: object) -> HoldingRow:
    if not isinstance(raw, dict):
        raise PortfolioError("MALFORMED_RESPONSE", "holding row is invalid")
    row = cast("dict[str, object]", raw)
    raw_symbol = row.get("tradingsymbol")
    if not isinstance(raw_symbol, str):
        raise PortfolioError("MALFORMED_RESPONSE", "holding symbol is invalid")
    stripped_symbol = raw_symbol.strip()
    if not stripped_symbol.isascii():
        raise PortfolioError("MALFORMED_RESPONSE", "holding symbol is invalid")
    symbol = stripped_symbol.upper()
    if not _SYMBOL.fullmatch(symbol):
        raise PortfolioError("MALFORMED_RESPONSE", "holding symbol is invalid")
    quantity = _decimal(row.get("quantity"), "quantity")
    t1_quantity = _decimal(row.get("t1quantity", "0"), "t1quantity")
    average_price = _decimal(row.get("averageprice"), "averageprice")
    last_price = _decimal(row.get("ltp"), "ltp")
    if quantity < 0 or t1_quantity < 0 or average_price < 0 or last_price <= 0:
        raise PortfolioError("MALFORMED_RESPONSE", "holding values are invalid")
    previous_close = _optional_decimal(row.get("close"), "close")
    if previous_close is not None and previous_close <= 0:
        previous_close = None
    if row.get("profitandloss") is not None:
        _decimal(row["profitandloss"], "profitandloss")
    exchange = _optional_exchange(row.get("exchange"))
    symbol_token = _optional_identifier(row.get("symboltoken"), "symboltoken")
    isin = _optional_isin(row.get("isin"))
    invested = average_price * quantity
    current = last_price * quantity
    pnl = current - invested
    pnl_pct = (pnl / invested * 100) if invested > 0 else None
    if previous_close is None:
        day_change = None
        day_pct = None
    else:
        day_change = (last_price - previous_close) * quantity
        day_pct = (last_price / previous_close - 1) * 100
    return HoldingRow(
        symbol=symbol,
        quantity=quantity,
        t1_quantity=t1_quantity,
        average_price=_q2(average_price),
        last_price=_q2(last_price),
        previous_close=None if previous_close is None else _q2(previous_close),
        invested=_q2(invested),
        current=_q2(current),
        pnl=_q2(pnl),
        pnl_pct=None if pnl_pct is None else _q2(pnl_pct),
        day_change=None if day_change is None else _q2(day_change),
        day_pct=None if day_pct is None else _q2(day_pct),
        exchange=exchange,
        symbol_token=symbol_token,
        isin=isin,
    )


def _record_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PortfolioError("MALFORMED_RESPONSE", f"{label} row is invalid")
    return cast("dict[str, object]", value)


def _parse_records(
    raw_rows: list[object],
    parser: Callable[[object], tuple[T, tuple[str, ...]]],
    label: str,
) -> tuple[list[T], list[str]]:
    records: list[T] = []
    limitations: list[str] = []
    try:
        for raw in raw_rows:
            record, record_limitations = parser(raw)
            records.append(record)
            limitations.extend(record_limitations)
    except DecimalException as exc:
        raise PortfolioError(
            "MALFORMED_RESPONSE", f"Angel One {label} values are invalid"
        ) from exc
    return records, limitations


def _record_text(value: object, field: str, *, max_len: int = 128) -> str:
    if not isinstance(value, str):
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid")
    text = value.strip()
    if not text or len(text) > max_len or not text.isascii():
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid")
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid")
    return text


def _optional_record_text(
    value: object, field: str, *, max_len: int = 128
) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _record_text(value, field, max_len=max_len)


def _optional_message_text(
    value: object, field: str, *, max_len: int = 200
) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid")
    text = value.strip()
    if len(text) > max_len:
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid")
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("C") or category in {"Zl", "Zp"}:
            raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid")
    return text


def _record_symbol(value: object) -> str:
    if not isinstance(value, str):
        raise PortfolioError("MALFORMED_RESPONSE", "symbol is invalid")
    text = value.strip()
    if not text.isascii():
        raise PortfolioError("MALFORMED_RESPONSE", "symbol is invalid")
    text = text.upper()
    if not _SYMBOL.fullmatch(text):
        raise PortfolioError("MALFORMED_RESPONSE", "symbol is invalid")
    return text


def _record_exchange(value: object) -> str:
    text = _record_text(value, "exchange", max_len=8).upper()
    if not _EXCHANGE.fullmatch(text):
        raise PortfolioError("MALFORMED_RESPONSE", "exchange is invalid")
    return text


def _optional_exchange(value: object) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _record_exchange(value)


def _record_identifier(value: object, field: str) -> str:
    if isinstance(value, (bool, float)) or value is None:
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid")
    text = str(value).strip()
    if not _IDENTIFIER.fullmatch(text):
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid")
    return text


def _optional_identifier(value: object, field: str) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _record_identifier(value, field)


def _optional_isin(value: object) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise PortfolioError("MALFORMED_RESPONSE", "isin is invalid")
    text = value.strip()
    if not text.isascii():
        raise PortfolioError("MALFORMED_RESPONSE", "isin is invalid")
    text = text.upper()
    if not _ISIN.fullmatch(text):
        raise PortfolioError("MALFORMED_RESPONSE", "isin is invalid")
    return text


def _non_negative(value: object, field: str) -> Decimal:
    number = _decimal(value, field)
    if number < 0:
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid")
    return number


def _positive(value: object, field: str) -> Decimal:
    number = _decimal(value, field)
    if number <= 0:
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid")
    return number


def _optional_positive(value: object, field: str) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    number = _decimal(value, field)
    if number == 0:
        return None
    if number < 0:
        raise PortfolioError("MALFORMED_RESPONSE", f"{field} is invalid")
    return number


def _optional_non_negative(value: object, field: str) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _non_negative(value, field)


def _upper_text(value: object, field: str, *, max_len: int = 32) -> str:
    return _record_text(value, field, max_len=max_len).upper()


def _optional_upper_text(value: object, field: str, *, max_len: int = 32) -> str | None:
    text = _optional_record_text(value, field, max_len=max_len)
    return None if text is None else text.upper()


def _record_side(value: object) -> str:
    side = _upper_text(value, "transactiontype", max_len=8)
    if side not in {"BUY", "SELL"}:
        raise PortfolioError("MALFORMED_RESPONSE", "transactiontype is invalid")
    return side


def _position_row(raw: object) -> tuple[PositionRecord, tuple[str, ...]]:
    row = _record_mapping(raw, "position")
    symbol = _record_symbol(row.get("tradingsymbol"))
    exchange = _record_exchange(row.get("exchange"))
    symbol_token = _optional_identifier(row.get("symboltoken"), "symboltoken")
    product_type = _upper_text(row.get("producttype"), "producttype")
    instrument_type = _optional_upper_text(
        row.get("instrumenttype"), "instrumenttype", max_len=16
    )
    quantity = _decimal(row.get("netqty"), "netqty")
    average_price = _non_negative(row.get("avgnetprice"), "avgnetprice")
    last_price = _optional_positive(row.get("ltp"), "ltp")
    broker_pnl = _optional_decimal(row.get("pnl"), "pnl")
    unrealised_pnl = _optional_decimal(row.get("unrealised"), "unrealised")
    realised_pnl = _optional_decimal(row.get("realised"), "realised")
    multiplier = _optional_decimal(row.get("multiplier"), "multiplier")
    limitations: list[str] = []
    is_equity = instrument_type in {None, "EQ"}
    if broker_pnl is not None:
        pnl = broker_pnl
        pnl_source = "BROKER"
    elif unrealised_pnl is not None:
        pnl = unrealised_pnl
        pnl_source = "BROKER"
    elif last_price is not None and is_equity:
        pnl = (last_price - average_price) * quantity
        pnl_source = "DERIVED"
        limitations.append("POSITION_PNL_DERIVED_FROM_LTP")
    else:
        pnl = None
        pnl_source = None
        limitations.append("POSITION_PNL_UNAVAILABLE")
        if not is_equity:
            limitations.append("POSITION_PNL_DERIVATION_UNSUPPORTED")
    if last_price is None:
        limitations.append("POSITION_LTP_UNAVAILABLE")
    pnl_pct: Decimal | None = None
    if pnl is not None:
        cost = abs(average_price * quantity)
        if cost > 0:
            pnl_pct = pnl / cost * 100
    reported_at = _optional_record_text(
        row.get("updateddate"), "updateddate", max_len=64
    ) or _optional_record_text(row.get("createddate"), "createddate", max_len=64)
    return (
        PositionRecord(
            symbol=symbol,
            exchange=exchange,
            symbol_token=symbol_token,
            product_type=product_type,
            instrument_type=instrument_type,
            quantity=quantity,
            average_price=_q2(average_price),
            last_price=None if last_price is None else _q2(last_price),
            pnl=None if pnl is None else _q2(pnl),
            pnl_pct=None if pnl_pct is None else _q2(pnl_pct),
            realised_pnl=None if realised_pnl is None else _q2(realised_pnl),
            unrealised_pnl=(None if unrealised_pnl is None else _q2(unrealised_pnl)),
            multiplier=multiplier,
            pnl_source=pnl_source,
            reported_at=reported_at,
        ),
        tuple(limitations),
    )


def _order_row(raw: object) -> tuple[OrderRecord, tuple[str, ...]]:
    row = _record_mapping(raw, "order")
    raw_order_id = row.get("uniqueorderid")
    if raw_order_id is None or (
        isinstance(raw_order_id, str) and not raw_order_id.strip()
    ):
        raw_order_id = row.get("orderid")
    order_id = _record_identifier(raw_order_id, "orderid")
    exchange_order_id = _optional_identifier(
        row.get("exchangeorderid"), "exchangeorderid"
    )
    parent_order_id = _optional_identifier(row.get("parentorderid"), "parentorderid")
    symbol = _record_symbol(row.get("tradingsymbol"))
    exchange = _record_exchange(row.get("exchange"))
    symbol_token = _optional_identifier(row.get("symboltoken"), "symboltoken")
    side = _record_side(row.get("transactiontype"))
    order_type = _upper_text(row.get("ordertype"), "ordertype", max_len=24)
    product_type = _upper_text(row.get("producttype"), "producttype", max_len=24)
    variety = _optional_upper_text(row.get("variety"), "variety", max_len=24)
    status = _upper_text(
        row.get("orderstatus") or row.get("status"), "orderstatus", max_len=64
    )
    status_message = _optional_message_text(row.get("text"), "text")
    quantity = _non_negative(row.get("quantity"), "quantity")
    filled_quantity = _non_negative(row.get("filledshares"), "filledshares")
    pending_quantity = _non_negative(row.get("unfilledshares"), "unfilledshares")
    price = _non_negative(row.get("price"), "price")
    trigger_price = _optional_positive(row.get("triggerprice"), "triggerprice")
    average_fill_price = _optional_positive(row.get("averageprice"), "averageprice")
    validity = _optional_upper_text(row.get("duration"), "duration", max_len=16)
    reported_at = _optional_record_text(
        row.get("updatetime"), "updatetime", max_len=64
    ) or _optional_record_text(row.get("exchtime"), "exchtime", max_len=64)
    return (
        OrderRecord(
            order_id=order_id,
            exchange_order_id=exchange_order_id,
            parent_order_id=parent_order_id,
            symbol=symbol,
            exchange=exchange,
            symbol_token=symbol_token,
            side=side,
            order_type=order_type,
            product_type=product_type,
            variety=variety,
            status=status,
            status_message=status_message,
            quantity=quantity,
            filled_quantity=filled_quantity,
            pending_quantity=pending_quantity,
            price=_q2(price),
            trigger_price=None if trigger_price is None else _q2(trigger_price),
            average_fill_price=(
                None if average_fill_price is None else _q2(average_fill_price)
            ),
            validity=validity,
            reported_at=reported_at,
        ),
        (),
    )


def _trade_row(raw: object) -> tuple[TradeRecord, tuple[str, ...]]:
    row = _record_mapping(raw, "trade")
    trade_id = _record_identifier(row.get("fillid"), "fillid")
    order_id = _record_identifier(row.get("orderid"), "orderid")
    symbol = _record_symbol(row.get("tradingsymbol"))
    exchange = _record_exchange(row.get("exchange"))
    symbol_token = _optional_identifier(row.get("symboltoken"), "symboltoken")
    side = _record_side(row.get("transactiontype"))
    product_type = _upper_text(row.get("producttype"), "producttype", max_len=24)
    quantity = _positive(row.get("fillsize"), "fillsize")
    price = _positive(row.get("fillprice"), "fillprice")
    raw_value = row.get("tradevalue")
    limitations: tuple[str, ...] = ()
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        trade_value = quantity * price
        limitations = ("TRADE_VALUE_COMPUTED",)
    else:
        trade_value = _non_negative(raw_value, "tradevalue")
    reported_at = _optional_record_text(row.get("filltime"), "filltime", max_len=32)
    return (
        TradeRecord(
            trade_id=trade_id,
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            symbol_token=symbol_token,
            side=side,
            product_type=product_type,
            quantity=quantity,
            price=_q2(price),
            trade_value=_q2(trade_value),
            reported_at=reported_at,
        ),
        limitations,
    )


def _gtt_row(raw: object) -> tuple[GttRecord, tuple[str, ...]]:
    row = _record_mapping(raw, "GTT rule")
    rule_id = _record_identifier(row.get("id"), "id")
    symbol = _record_symbol(row.get("tradingsymbol"))
    exchange = _record_exchange(row.get("exchange"))
    symbol_token = _optional_identifier(row.get("symboltoken"), "symboltoken")
    side = _record_side(row.get("transactiontype"))
    product_type = _upper_text(row.get("producttype"), "producttype", max_len=24)
    gtt_type = _optional_upper_text(row.get("gttType"), "gttType", max_len=16)
    quantity = _positive(row.get("qty"), "qty")
    disclosed_quantity = _optional_non_negative(row.get("disclosedqty"), "disclosedqty")
    price = _positive(row.get("price"), "price")
    trigger_price = _positive(row.get("triggerprice"), "triggerprice")
    stoploss_price = _optional_positive(row.get("stoplossprice"), "stoplossprice")
    stoploss_trigger_price = _optional_positive(
        row.get("stoplosstriggerprice"), "stoplosstriggerprice"
    )
    status = _optional_upper_text(row.get("status"), "status", max_len=64)
    limitations: list[str] = []
    if status is None:
        limitations.append("GTT_STATUS_UNAVAILABLE")
    created_at = _optional_record_text(
        row.get("createddate"), "createddate", max_len=64
    )
    updated_at = _optional_record_text(
        row.get("updateddate"), "updateddate", max_len=64
    )
    expires_at = _optional_record_text(row.get("expirydate"), "expirydate", max_len=64)
    return (
        GttRecord(
            rule_id=rule_id,
            symbol=symbol,
            exchange=exchange,
            symbol_token=symbol_token,
            side=side,
            product_type=product_type,
            gtt_type=gtt_type,
            quantity=quantity,
            disclosed_quantity=disclosed_quantity,
            price=_q2(price),
            trigger_price=_q2(trigger_price),
            stoploss_price=None if stoploss_price is None else _q2(stoploss_price),
            stoploss_trigger_price=(
                None if stoploss_trigger_price is None else _q2(stoploss_trigger_price)
            ),
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            expires_at=expires_at,
        ),
        tuple(limitations),
    )


def _pnl_inconsistent(raw_rows: object, rows: tuple[HoldingRow, ...]) -> bool:
    if not isinstance(raw_rows, list):
        return False
    for raw, row in zip(cast("list[object]", raw_rows), rows, strict=False):
        if not isinstance(raw, dict) or "profitandloss" not in raw:
            continue
        try:
            provided = _decimal(
                cast("dict[str, object]", raw)["profitandloss"], "profitandloss"
            )
        except PortfolioError:
            continue
        if abs(provided - row.pnl) > RECONCILIATION_TOLERANCE:
            return True
    return False


def _reconcile(
    totals: object,
    invested: Decimal,
    current: Decimal,
    overall_pnl: Decimal,
    limitations: list[str],
) -> None:
    if totals is None:
        limitations.append("TOTAL_NOT_PROVIDED")
        return
    if not isinstance(totals, dict):
        raise PortfolioError("MALFORMED_RESPONSE", "holding totals are invalid")
    total = cast("dict[str, object]", totals)
    pairs = (
        ("totalinvvalue", invested),
        ("totalholdingvalue", current),
        ("totalprofitandloss", overall_pnl),
    )
    checked = 0
    for key, expected in pairs:
        if key not in total:
            continue
        raw = _decimal(total[key], key)
        checked += 1
        if abs(raw - expected) > RECONCILIATION_TOLERANCE:
            raise PortfolioError(
                "RECONCILIATION_MISMATCH",
                "broker totals do not reconcile with holding rows",
            )
    if checked != len(pairs):
        limitations.append("TOTAL_PARTIAL")


def review_payload(
    account_id: str, broker: str, snapshot: HoldingsSnapshot
) -> dict[str, object]:
    with localcontext() as context:
        context.prec = 60
        return {
            "schema_version": 1,
            "account_id": account_id,
            "broker": broker,
            "source": "ANGEL_ONE_HOLDINGS",
            "retrieved_at": snapshot.retrieved_at,
            "summary": {
                "holdings": len(snapshot.rows),
                "invested": _money(snapshot.invested),
                "current": _money(snapshot.current),
                "overall_pnl": _money(snapshot.overall_pnl),
                "overall_pnl_pct": _percent(snapshot.overall_pnl_pct),
                "day_change": (
                    None if snapshot.day_change is None else _money(snapshot.day_change)
                ),
                "day_change_pct": _percent(snapshot.day_change_pct),
                "top_holding_weight_pct": _top_weight(snapshot),
            },
            "holdings": [
                {
                    "symbol": row.symbol,
                    "quantity": float(row.quantity),
                    "t1_quantity": float(row.t1_quantity),
                    "average_price": _money(row.average_price),
                    "last_price": _money(row.last_price),
                    "previous_close": (
                        None
                        if row.previous_close is None
                        else _money(row.previous_close)
                    ),
                    "invested": _money(row.invested),
                    "current": _money(row.current),
                    "pnl": _money(row.pnl),
                    "pnl_pct": _percent(row.pnl_pct),
                    "day_change": (
                        None if row.day_change is None else _money(row.day_change)
                    ),
                    "day_pct": _percent(row.day_pct),
                }
                for row in snapshot.rows
            ],
            "limitations": ["BROKER_READ_ONLY", "POINT_IN_TIME_SNAPSHOT"]
            + list(snapshot.limitations),
        }


def _top_weight(snapshot: HoldingsSnapshot) -> float | None:
    if snapshot.current <= 0 or not snapshot.rows:
        return None
    weight = max(row.current for row in snapshot.rows) / snapshot.current * 100
    return float(_q2(weight))


__all__ = [
    "AngelOneClient",
    "AngelOneCredentials",
    "GttRecord",
    "GttSnapshot",
    "HoldingRow",
    "HoldingsSnapshot",
    "OrderRecord",
    "OrdersSnapshot",
    "PositionRecord",
    "PositionsSnapshot",
    "Section",
    "TradeRecord",
    "TradesSnapshot",
    "generate_totp",
    "load_credentials",
    "review_payload",
]
