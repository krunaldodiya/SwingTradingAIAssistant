"""Read-only Angel One SmartAPI connector.

Only login and getAllHolding are implemented. No order, position, trade-book,
profile, or generic request surface exists.
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
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, cast

from .credentials import missing_credentials
from .errors import PortfolioError

Transport = Callable[
    [str, str, Mapping[str, str], bytes | None], tuple[int, dict[str, object]]
]

BASE_URL = "https://apiconnect.angelone.in"
LOGIN_PATH = "/rest/auth/angelbroking/user/v1/loginByPassword"
HOLDINGS_PATH = "/rest/secure/angelbroking/portfolio/v1/getAllHolding"
ALLOWED_URLS = frozenset({f"{BASE_URL}{LOGIN_PATH}", f"{BASE_URL}{HOLDINGS_PATH}"})
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
RECONCILIATION_TOLERANCE = Decimal("5.00")
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&.-]{0,19}$")


@dataclass(frozen=True, repr=False)
class AngelOneCredentials:
    api_key: str
    client_code: str
    pin: str
    totp_secret: str

    def __repr__(self) -> str:
        return "AngelOneCredentials(<redacted>)"


@dataclass(frozen=True)
class HoldingRow:
    symbol: str
    quantity: Decimal
    t1_quantity: Decimal
    average_price: Decimal
    last_price: Decimal
    previous_close: Decimal | None
    invested: Decimal
    current: Decimal
    pnl: Decimal
    pnl_pct: Decimal | None
    day_change: Decimal | None
    day_pct: Decimal | None


@dataclass(frozen=True)
class HoldingsSnapshot:
    rows: tuple[HoldingRow, ...]
    invested: Decimal
    current: Decimal
    overall_pnl: Decimal
    overall_pnl_pct: Decimal | None
    day_change: Decimal | None
    day_change_pct: Decimal | None
    limitations: tuple[str, ...]
    retrieved_at: str


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
        raise PortfolioError("MALFORMED_RESPONSE", f"holding {field} is invalid")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PortfolioError(
            "MALFORMED_RESPONSE", f"holding {field} is invalid"
        ) from exc
    if not number.is_finite():
        raise PortfolioError("MALFORMED_RESPONSE", f"holding {field} is invalid")
    return number


def _optional_decimal(value: object, field: str) -> Decimal | None:
    if value is None:
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
            rows = tuple(_holding_row(row) for row in cast("list[object]", raw_rows))
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
                retrieved_at=datetime.fromtimestamp(self._clock(), tz=UTC).isoformat(
                    timespec="seconds"
                ),
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
    "HoldingRow",
    "HoldingsSnapshot",
    "generate_totp",
    "load_credentials",
    "review_payload",
]
