"""Manual holdings snapshot: typed import, append-only storage, and review."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from .accounts import (
    AccountRecord,
    get_account,
    mark_imported,
    snapshot_directory,
)
from .errors import PortfolioError
from .storage import (
    atomic_write,
    now_iso,
    parse_aware_timestamp,
    require_private_directory,
    require_private_file,
    validate_storage_root,
)

SCHEMA_VERSION = 1
SOURCE = "MANUAL_SNAPSHOT"
MAX_INPUT_BYTES = 1_048_576
MAX_SNAPSHOT_BYTES = 4_194_304
MAX_ABS_DECIMAL = Decimal("1e12")
MIN_ABS_DECIMAL = Decimal("1e-9")
REQUIRED_COLUMNS: set[str] = {
    "symbol",
    "exchange",
    "quantity",
    "average_price",
    "last_price",
}
OPTIONAL_COLUMNS: set[str] = {"isin", "previous_close"}
MANDATORY_LIMITATIONS: set[str] = {
    "USER_SUPPLIED_UNVERIFIED",
    "MEMBERSHIP_UNVERIFIED",
    "SECTOR_UNKNOWN",
}
CONDITIONAL_LIMITATIONS: set[str] = {
    "PARTIAL_SNAPSHOT",
    "DAY_CHANGE_UNAVAILABLE",
}
REJECTION_REASONS: set[str] = {
    "COLUMN_COUNT_MISMATCH",
    "SYMBOL_INVALID",
    "UNSUPPORTED_EXCHANGE",
    "DUPLICATE_SYMBOL",
    "INVALID_QUANTITY",
    "INVALID_AVERAGE_PRICE",
    "INVALID_LAST_PRICE",
    "INVALID_PREVIOUS_CLOSE",
    "INVALID_ISIN",
}

_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&.-]{0,19}$")
_ISIN = re.compile(r"^INE[0-9A-Z]{8}[0-9]$")
_DATE = re.compile(r"^\d{8}T\d{12}Z-[0-9a-f]{8}$")
_HOLDING_KEYS: set[str] = {
    "symbol",
    "exchange",
    "isin",
    "quantity",
    "average_price",
    "last_price",
    "previous_close",
}
_SNAPSHOT_KEYS: set[str] = {
    "schema_version",
    "account_id",
    "source",
    "as_of",
    "imported_at",
    "input_sha256",
    "holdings",
    "rejected",
    "limitations",
}


@dataclass(frozen=True)
class Holding:
    symbol: str
    exchange: str
    isin: str | None
    quantity: Decimal
    average_price: Decimal
    last_price: Decimal
    previous_close: Decimal | None


@dataclass(frozen=True)
class RejectedRow:
    row: int
    symbol: str | None
    reason: str


@dataclass(frozen=True)
class Snapshot:
    schema_version: int
    account_id: str
    source: str
    as_of: str
    imported_at: str
    input_sha256: str
    holdings: tuple[Holding, ...]
    rejected: tuple[RejectedRow, ...]
    limitations: tuple[str, ...]
    snapshot_id: str

    def to_dict(self) -> dict[str, object]:
        return _snapshot_to_dict(self)


def _q2(value: Decimal) -> Decimal:
    try:
        return value.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise PortfolioError(
            "SNAPSHOT_CORRUPT", "stored number is out of range"
        ) from exc


def _money(value: Decimal) -> float:
    return float(_q2(value))


def _percent(value: Decimal | None) -> float | None:
    return None if value is None else float(_q2(value))


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PortfolioError("INPUT_UNREADABLE", "snapshot input is not UTF-8") from exc


def _read_input(path: Path) -> bytes:
    candidate = path.expanduser()
    flags = os.O_RDONLY
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise PortfolioError(
            "INPUT_UNREADABLE", "snapshot input is unavailable"
        ) from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise PortfolioError(
                "INPUT_UNREADABLE", "snapshot input must be a regular file"
            )
        if info.st_size > MAX_INPUT_BYTES:
            raise PortfolioError("INPUT_TOO_LARGE", "snapshot input exceeds 1 MiB")
        chunks: list[bytes] = []
        remaining = MAX_INPUT_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    except PortfolioError:
        raise
    except OSError as exc:
        raise PortfolioError(
            "INPUT_UNREADABLE", "snapshot input cannot be read"
        ) from exc
    finally:
        os.close(descriptor)
    if len(raw) > MAX_INPUT_BYTES:
        raise PortfolioError("INPUT_TOO_LARGE", "snapshot input exceeds 1 MiB")
    return raw


def _decimal(text: str, *, reason: str, allow_zero: bool, positive: bool) -> Decimal:
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise PortfolioError(reason, "holding number is invalid") from exc
    if not value.is_finite():
        raise PortfolioError(reason, "holding number is invalid")
    if value != 0 and (abs(value) > MAX_ABS_DECIMAL or abs(value) < MIN_ABS_DECIMAL):
        raise PortfolioError(reason, "holding number is out of range")
    if allow_zero and value < 0:
        raise PortfolioError(reason, "holding number must not be negative")
    if positive and value <= 0:
        raise PortfolioError(reason, "holding number must be positive")
    return value


def _cell(row: list[str], columns: dict[str, int], name: str) -> str:
    return row[columns[name]].strip()


def _parse_row(
    row: list[str],
    columns: dict[str, int],
    *,
    number: int,
    seen: set[str],
) -> Holding | RejectedRow:
    def reject(reason: str, symbol: str | None = None) -> RejectedRow:
        return RejectedRow(row=number, symbol=symbol, reason=reason)

    if len(row) != len(columns):
        return reject("COLUMN_COUNT_MISMATCH")
    raw_symbol = _cell(row, columns, "symbol")
    symbol = raw_symbol.upper()
    if not _SYMBOL.fullmatch(symbol):
        return reject("SYMBOL_INVALID")
    if symbol in seen:
        return reject("DUPLICATE_SYMBOL", symbol)
    seen.add(symbol)
    exchange = _cell(row, columns, "exchange")
    if exchange != "NSE":
        return reject("UNSUPPORTED_EXCHANGE", symbol)
    try:
        quantity = _decimal(
            _cell(row, columns, "quantity"),
            reason="INVALID_QUANTITY",
            allow_zero=True,
            positive=False,
        )
        average_price = _decimal(
            _cell(row, columns, "average_price"),
            reason="INVALID_AVERAGE_PRICE",
            allow_zero=True,
            positive=False,
        )
        last_price = _decimal(
            _cell(row, columns, "last_price"),
            reason="INVALID_LAST_PRICE",
            allow_zero=False,
            positive=True,
        )
        raw_previous = (
            _cell(row, columns, "previous_close") if "previous_close" in columns else ""
        )
        previous_close = (
            None
            if not raw_previous
            else _decimal(
                raw_previous,
                reason="INVALID_PREVIOUS_CLOSE",
                allow_zero=False,
                positive=True,
            )
        )
    except PortfolioError as exc:
        return reject(exc.code, symbol)
    raw_isin = _cell(row, columns, "isin").upper() if "isin" in columns else ""
    if raw_isin and not _ISIN.fullmatch(raw_isin):
        return reject("INVALID_ISIN", symbol)
    return Holding(
        symbol=symbol,
        exchange=exchange,
        isin=raw_isin or None,
        quantity=quantity,
        average_price=average_price,
        last_price=last_price,
        previous_close=previous_close,
    )


def _parse_csv(raw: bytes) -> tuple[tuple[Holding, ...], tuple[RejectedRow, ...]]:
    text = _decode(raw).lstrip("\ufeff")
    try:
        rows = list(csv.reader(io.StringIO(text), strict=True))
    except csv.Error as exc:
        raise PortfolioError(
            "INPUT_HEADER_INVALID", "snapshot CSV is malformed"
        ) from exc
    header_index = next(
        (index for index, row in enumerate(rows) if any(cell.strip() for cell in row)),
        None,
    )
    if header_index is None:
        raise PortfolioError("INPUT_HEADER_INVALID", "snapshot CSV has no header")
    headers = [cell.strip().lower() for cell in rows[header_index]]
    if any(not header for header in headers):
        raise PortfolioError(
            "INPUT_HEADER_INVALID", "snapshot header has a blank column"
        )
    if len(set(headers)) != len(headers):
        raise PortfolioError("INPUT_HEADER_INVALID", "snapshot header has duplicates")
    present = set(headers)
    if REQUIRED_COLUMNS - present:
        raise PortfolioError(
            "INPUT_HEADER_INVALID", "snapshot header is missing a column"
        )
    if present - REQUIRED_COLUMNS - OPTIONAL_COLUMNS:
        raise PortfolioError(
            "INPUT_HEADER_INVALID", "snapshot header has an unknown column"
        )
    columns = {name: index for index, name in enumerate(headers)}
    holdings: list[Holding] = []
    rejected: list[RejectedRow] = []
    seen: set[str] = set()
    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if len(row) <= 1 and (not row or not row[0].strip()):
            continue
        parsed = _parse_row(row, columns, number=offset, seen=seen)
        if isinstance(parsed, Holding):
            holdings.append(parsed)
        else:
            rejected.append(parsed)
    return tuple(holdings), tuple(rejected)


def parse_snapshot(
    raw: bytes,
    *,
    account_id: str,
    as_of: str,
    imported_at: str,
    snapshot_id: str,
) -> Snapshot:
    """Validate one CSV snapshot without touching storage."""

    holdings, rejected = _parse_csv(raw)
    if not holdings:
        raise PortfolioError("NO_VALID_HOLDINGS", "snapshot has no valid holdings")
    limitations = [
        "USER_SUPPLIED_UNVERIFIED",
        "MEMBERSHIP_UNVERIFIED",
        "SECTOR_UNKNOWN",
    ]
    if rejected:
        limitations.append("PARTIAL_SNAPSHOT")
    if any(holding.previous_close is None for holding in holdings):
        limitations.append("DAY_CHANGE_UNAVAILABLE")
    return Snapshot(
        schema_version=SCHEMA_VERSION,
        account_id=account_id,
        source=SOURCE,
        as_of=as_of,
        imported_at=imported_at,
        input_sha256=hashlib.sha256(raw).hexdigest(),
        holdings=holdings,
        rejected=rejected,
        limitations=tuple(limitations),
        snapshot_id=snapshot_id,
    )


def _snapshot_id(moment: datetime) -> str:
    stamp = moment.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{secrets.token_hex(4)}"


def import_snapshot(
    storage_root: Path,
    *,
    account_id: str,
    file_path: Path,
    as_of: str,
    now: datetime | None = None,
) -> Snapshot:
    """Validate, store one append-only snapshot, and update the account."""

    root = validate_storage_root(storage_root)
    account = get_account(root, account_id)
    normalized_as_of = parse_aware_timestamp(as_of, code="AS_OF_INVALID", label="as_of")
    raw = _read_input(file_path)
    moment = now if now is not None else datetime.now(UTC)
    if moment.tzinfo is None:
        raise PortfolioError("INVALID_ARGUMENT", "timestamp must be timezone-aware")
    imported_at = now_iso(moment)
    snapshot = parse_snapshot(
        raw,
        account_id=account.account_id,
        as_of=normalized_as_of,
        imported_at=imported_at,
        snapshot_id=_snapshot_id(moment),
    )
    directory = snapshot_directory(root, account.account_id)
    container = directory.parent
    try:
        container.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise PortfolioError(
            "SNAPSHOT_PERMISSIONS", "snapshot storage is unavailable"
        ) from exc
    require_private_directory(container, code="SNAPSHOT_PERMISSIONS")
    if directory.exists() and not directory.is_dir():
        raise PortfolioError(
            "SNAPSHOT_PERMISSIONS", "snapshot account path is not a directory"
        )
    stamp = snapshot.snapshot_id.split("-", 1)[0]
    if directory.exists() and any(directory.glob(f"{stamp}-*.json")):
        raise PortfolioError("SNAPSHOT_COLLISION", "snapshot timestamp already exists")
    payload = (
        json.dumps(snapshot.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    atomic_write(
        directory,
        f"{snapshot.snapshot_id}.json",
        payload,
        overwrite=False,
        permission_code="SNAPSHOT_PERMISSIONS",
    )
    mark_imported(root, account_id=account.account_id, imported_at=imported_at)
    return snapshot


def _snapshot_to_dict(snapshot: Snapshot) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "account_id": snapshot.account_id,
        "source": SOURCE,
        "as_of": snapshot.as_of,
        "imported_at": snapshot.imported_at,
        "input_sha256": snapshot.input_sha256,
        "holdings": [
            {
                "symbol": holding.symbol,
                "exchange": holding.exchange,
                "isin": holding.isin,
                "quantity": str(holding.quantity),
                "average_price": str(holding.average_price),
                "last_price": str(holding.last_price),
                "previous_close": (
                    None
                    if holding.previous_close is None
                    else str(holding.previous_close)
                ),
            }
            for holding in snapshot.holdings
        ],
        "rejected": [
            {"row": row.row, "symbol": row.symbol, "reason": row.reason}
            for row in snapshot.rejected
        ],
        "limitations": list(snapshot.limitations),
    }


def _validate_limitations(
    raw: object,
    holdings: tuple[Holding, ...],
    rejected: tuple[RejectedRow, ...],
) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot limitations are invalid")
    items = cast("list[object]", raw)
    if not all(isinstance(item, str) for item in items):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot limitations are invalid")
    values = tuple(item for item in items if isinstance(item, str))
    if len(values) != len(set(values)):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot limitations have duplicates")
    present = set(values)
    if not present.issuperset(MANDATORY_LIMITATIONS):
        raise PortfolioError(
            "SNAPSHOT_CORRUPT", "snapshot limitations lack a mandatory label"
        )
    if present - MANDATORY_LIMITATIONS - CONDITIONAL_LIMITATIONS:
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot limitations are unknown")
    if ("PARTIAL_SNAPSHOT" in present) != bool(rejected):
        raise PortfolioError(
            "SNAPSHOT_CORRUPT", "snapshot partial label is inconsistent"
        )
    expected_day = any(holding.previous_close is None for holding in holdings)
    if ("DAY_CHANGE_UNAVAILABLE" in present) != expected_day:
        raise PortfolioError(
            "SNAPSHOT_CORRUPT", "snapshot day-change label is inconsistent"
        )
    return values


def _holdings_from_list(raw: object) -> tuple[Holding, ...]:
    if not isinstance(raw, list) or not raw:
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot holdings are invalid")
    holdings = tuple(_holding_from_dict(item) for item in cast("list[object]", raw))
    symbols = [holding.symbol for holding in holdings]
    if len(symbols) != len(set(symbols)):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot has duplicate holdings")
    return holdings


def _snapshot_from_dict(raw: object, *, snapshot_id: str) -> Snapshot:
    if not isinstance(raw, dict):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot is invalid")
    value = cast("dict[str, object]", raw)
    if set(value) != _SNAPSHOT_KEYS:
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot keys are invalid")
    version = value["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot schema is invalid")
    if version != SCHEMA_VERSION:
        raise PortfolioError("UNSUPPORTED_SCHEMA", "snapshot schema is newer")
    if value["source"] != SOURCE:
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot source is invalid")
    account_id = value["account_id"]
    if not isinstance(account_id, str):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot account is invalid")
    as_of = parse_aware_timestamp(
        str(value["as_of"]), code="SNAPSHOT_CORRUPT", label="as_of"
    )
    imported_at = parse_aware_timestamp(
        str(value["imported_at"]), code="SNAPSHOT_CORRUPT", label="imported_at"
    )
    input_sha256 = value["input_sha256"]
    if not isinstance(input_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", input_sha256
    ):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot input hash is invalid")
    holdings = _holdings_from_list(value["holdings"])
    rejected_raw = value["rejected"]
    if not isinstance(rejected_raw, list):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot rejected rows are invalid")
    rejected = tuple(
        _rejected_from_dict(item) for item in cast("list[object]", rejected_raw)
    )
    limitations = _validate_limitations(value["limitations"], holdings, rejected)
    return Snapshot(
        schema_version=SCHEMA_VERSION,
        account_id=account_id,
        source=SOURCE,
        as_of=as_of,
        imported_at=imported_at,
        input_sha256=input_sha256,
        holdings=holdings,
        rejected=rejected,
        limitations=limitations,
        snapshot_id=snapshot_id,
    )


def _holding_from_dict(raw: object) -> Holding:
    if not isinstance(raw, dict):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot holding is invalid")
    value = cast("dict[str, object]", raw)
    if set(value) != _HOLDING_KEYS:
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot holding keys are invalid")
    symbol = value["symbol"]
    exchange = value["exchange"]
    if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot symbol is invalid")
    if not isinstance(exchange, str) or exchange != "NSE":
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot exchange is invalid")
    isin = value["isin"]
    if isin is not None and (not isinstance(isin, str) or not _ISIN.fullmatch(isin)):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot ISIN is invalid")
    try:
        quantity = _decimal(
            str(value["quantity"]),
            reason="SNAPSHOT_CORRUPT",
            allow_zero=True,
            positive=False,
        )
        average_price = _decimal(
            str(value["average_price"]),
            reason="SNAPSHOT_CORRUPT",
            allow_zero=True,
            positive=False,
        )
        last_price = _decimal(
            str(value["last_price"]),
            reason="SNAPSHOT_CORRUPT",
            allow_zero=False,
            positive=True,
        )
        raw_previous = value["previous_close"]
        previous_close = (
            None
            if raw_previous is None
            else _decimal(
                str(raw_previous),
                reason="SNAPSHOT_CORRUPT",
                allow_zero=False,
                positive=True,
            )
        )
    except PortfolioError as exc:
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot number is invalid") from exc
    return Holding(
        symbol=symbol,
        exchange=exchange,
        isin=isin,
        quantity=quantity,
        average_price=average_price,
        last_price=last_price,
        previous_close=previous_close,
    )


def _rejected_from_dict(raw: object) -> RejectedRow:
    if not isinstance(raw, dict):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot rejected row is invalid")
    value = cast("dict[str, object]", raw)
    if set(value) != {"row", "symbol", "reason"}:
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot rejected keys are invalid")
    row = value["row"]
    symbol = value["symbol"]
    reason = value["reason"]
    if isinstance(row, bool) or not isinstance(row, int) or row < 1:
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot rejected row is invalid")
    if symbol is not None and not isinstance(symbol, str):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot rejected symbol is invalid")
    if not isinstance(reason, str) or reason not in REJECTION_REASONS:
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot rejected reason is invalid")
    return RejectedRow(row=row, symbol=symbol, reason=reason)


def load_latest_snapshot(storage_root: Path, account_id: str) -> Snapshot:
    """Load the newest append-only snapshot for one account."""

    root = validate_storage_root(storage_root)
    get_account(root, account_id)
    directory = snapshot_directory(root, account_id)
    container = directory.parent
    if container.exists():
        require_private_directory(container, code="SNAPSHOT_PERMISSIONS")
    try:
        directory.lstat()
    except FileNotFoundError as exc:
        raise PortfolioError("NO_SNAPSHOT", "account has no snapshot") from exc
    require_private_directory(directory, code="SNAPSHOT_PERMISSIONS")
    files = sorted(
        (path for path in directory.glob("*.json") if path.is_file()),
        key=lambda path: path.name,
        reverse=True,
    )
    if not files:
        raise PortfolioError("NO_SNAPSHOT", "account has no snapshot")
    path = files[0]
    if not _DATE.fullmatch(path.stem):
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot name is invalid")
    require_private_file(path, code="SNAPSHOT_PERMISSIONS")
    if path.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot is too large")
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot is unreadable") from exc
    snapshot = _snapshot_from_dict(raw, snapshot_id=path.stem)
    if snapshot.account_id != account_id:
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot account does not match")
    return snapshot


def review_payload(account: AccountRecord, snapshot: Snapshot) -> dict[str, object]:
    """Compute the deterministic read-only review for one snapshot."""

    if snapshot.account_id != account.account_id:
        raise PortfolioError("SNAPSHOT_CORRUPT", "snapshot account does not match")
    invested = sum(
        (holding.average_price * holding.quantity for holding in snapshot.holdings),
        Decimal("0"),
    )
    current = sum(
        (holding.last_price * holding.quantity for holding in snapshot.holdings),
        Decimal("0"),
    )
    pnl = current - invested
    pnl_pct = (pnl / invested * 100) if invested > 0 else None
    if all(holding.previous_close is not None for holding in snapshot.holdings):
        day_change: Decimal | None = sum(
            (
                (holding.last_price - cast("Decimal", holding.previous_close))
                * holding.quantity
                for holding in snapshot.holdings
            ),
            Decimal("0"),
        )
        previous = current - day_change
        day_change_pct = (day_change / previous * 100) if previous > 0 else None
    else:
        day_change = None
        day_change_pct = None
    rows: list[dict[str, object]] = []
    for holding in snapshot.holdings:
        value = holding.last_price * holding.quantity
        weight = (value / current * 100) if current > 0 else Decimal("0")
        row_pnl = value - (holding.average_price * holding.quantity)
        rows.append(
            {
                "symbol": holding.symbol,
                "exchange": holding.exchange,
                "isin": holding.isin,
                "quantity": float(holding.quantity),
                "average_price": _money(holding.average_price),
                "last_price": _money(holding.last_price),
                "previous_close": (
                    None
                    if holding.previous_close is None
                    else _money(holding.previous_close)
                ),
                "invested": _money(holding.average_price * holding.quantity),
                "current": _money(value),
                "pnl": _money(row_pnl),
                "pnl_pct": _percent(
                    (row_pnl / (holding.average_price * holding.quantity) * 100)
                    if holding.average_price > 0 and holding.quantity > 0
                    else None
                ),
                "weight_pct": _percent(weight),
            }
        )
    rows.sort(key=lambda row: (-cast("float", row["current"]), str(row["symbol"])))
    top_weight = max((cast("float", row["weight_pct"]) for row in rows), default=None)
    return {
        "schema_version": SCHEMA_VERSION,
        "account_id": account.account_id,
        "broker": account.broker,
        "source": SOURCE,
        "snapshot_id": snapshot.snapshot_id,
        "as_of": snapshot.as_of,
        "imported_at": snapshot.imported_at,
        "summary": {
            "holdings": len(rows),
            "invested": _money(invested),
            "current": _money(current),
            "overall_pnl": _money(pnl),
            "overall_pnl_pct": _percent(pnl_pct),
            "day_change": _money(day_change) if day_change is not None else None,
            "day_change_pct": _percent(day_change_pct),
            "top_holding_weight_pct": top_weight,
        },
        "holdings": rows,
        "rejected": [
            {"row": item.row, "symbol": item.symbol, "reason": item.reason}
            for item in snapshot.rejected
        ],
        "limitations": list(snapshot.limitations),
    }
