"""Installed live broker portfolio CLI."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn, cast

from .accounts import (
    AccountRecord,
    add_account,
    get_account,
    identity_matches,
    list_accounts,
    verify_account,
)
from .angel_one import review_payload
from .brokers import BrokerConnector, open_connector
from .errors import PortfolioError
from .payloads import (
    STATUS_OK,
    STATUS_UNAVAILABLE,
    STATUS_UNSUPPORTED,
    RecordSnapshot,
    section_body,
    section_limitations,
    section_payload,
    section_records,
    snapshot_payload,
)
from .records import SECTION_ORDER, Section

_RIGHT = frozenset({2, 3, 4, 5, 6, 7})
_INVALID_CODES = frozenset(
    {
        "INVALID_ARGUMENT",
        "ACCOUNT_ID_INVALID",
        "DISPLAY_NAME_INVALID",
        "BROKER_UNSUPPORTED",
        "CREDENTIAL_PREFIX_INVALID",
        "CREDENTIALS_MISSING",
        "MALFORMED_CREDENTIAL",
        "AUTH_FAILED",
        "IP_NOT_WHITELISTED",
        "PROVIDER_UNAVAILABLE",
        "MALFORMED_RESPONSE",
        "RECONCILIATION_MISMATCH",
        "IDENTITY_MISMATCH",
        "IO_ERROR",
        "REGISTRY_PERMISSIONS",
        "REGISTRY_TOO_LARGE",
        "UNSUPPORTED_SCHEMA",
        "MANUAL_PORTFOLIO_RETIRED",
    }
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise PortfolioError("INVALID_ARGUMENT", "invalid command arguments")


def _money(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{value:,.2f}"


def _percent(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{value:,.2f}%"


def _quantity(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    right: frozenset[int] = frozenset(),
) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    lines = [
        "  ".join(
            header.rjust(widths[index])
            if index in right
            else header.ljust(widths[index])
            for index, header in enumerate(headers)
        ),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend(
        "  ".join(
            cell.rjust(widths[index]) if index in right else cell.ljust(widths[index])
            for index, cell in enumerate(row)
        )
        for row in rows
    )
    return "\n".join(lines)


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PortfolioError("MALFORMED_RESPONSE", message)
    return cast("dict[str, object]", value)


def _objects(value: object, message: str) -> list[object]:
    if not isinstance(value, list):
        raise PortfolioError("MALFORMED_RESPONSE", message)
    return cast("list[object]", value)


def _error_json(code: str, message: str) -> str:
    return json.dumps(
        {"status": "error", "error_code": code, "message": message},
        sort_keys=True,
        allow_nan=False,
    )


def _account_payload(record: AccountRecord) -> dict[str, object]:
    return {"schema_version": 1, "account": record.to_dict()}


def _emit_account(record: AccountRecord, output: str) -> int:
    if output == "json":
        print(
            json.dumps(
                _account_payload(record), indent=2, sort_keys=True, allow_nan=False
            )
        )
        return 0
    print(
        _table(
            ("Account", "Broker", "Name", "Status", "Last verified"),
            [
                (
                    record.account_id,
                    record.broker,
                    record.display_name,
                    record.last_status,
                    record.last_verified_at,
                )
            ],
        )
    )
    return 0


def _emit_accounts(records: Sequence[AccountRecord], output: str) -> int:
    if output == "json":
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "accounts": [record.to_dict() for record in records],
                },
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
        )
        return 0
    if not records:
        print("No connected broker accounts.")
        return 0
    print(
        _table(
            ("Account", "Broker", "Name", "Status", "Last verified"),
            [
                (
                    record.account_id,
                    record.broker,
                    record.display_name,
                    record.last_status,
                    record.last_verified_at,
                )
                for record in records
            ],
        )
    )
    return 0


def _emit_review(payload: dict[str, object], output: str) -> int:
    if output == "json":
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
        return 0
    summary = _mapping(payload["summary"], "review summary is invalid")
    print(
        f"Account {payload['account_id']} ({payload['broker']}) "
        f"at {payload['retrieved_at']} | source {payload['source']}"
    )
    print(
        "Invested {invested} | Current {current} | P&L {pnl} ({pct}) | "
        "Day {day} ({day_pct})".format(
            invested=_money(summary.get("invested")),
            current=_money(summary.get("current")),
            pnl=_money(summary.get("overall_pnl")),
            pct=_percent(summary.get("overall_pnl_pct")),
            day=_money(summary.get("day_change")),
            day_pct=_percent(summary.get("day_change_pct")),
        )
    )
    rows = _objects(payload["holdings"], "review holdings are invalid")
    table_rows: list[tuple[str, str, str, str, str, str, str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        row = cast("dict[str, object]", item)
        table_rows.append(
            (
                str(row["symbol"]),
                _quantity(row["quantity"]),
                _money(row["average_price"]),
                _money(row["last_price"]),
                _money(row["current"]),
                _money(row["pnl"]),
                _percent(row["pnl_pct"]),
                _percent(row["day_pct"]),
            )
        )
    print(
        _table(
            ("Symbol", "Qty", "Avg", "LTP", "Value", "P&L", "P&L %", "Day %"),
            table_rows,
            right=_RIGHT,
        )
    )
    limitations = _objects(payload["limitations"], "review limitations are invalid")
    if limitations:
        print("Limitations: " + ", ".join(str(item) for item in limitations))
    return 0


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _open_client(
    storage_root: Path, account_id: str
) -> tuple[AccountRecord, BrokerConnector]:
    account = get_account(storage_root, account_id)
    identity, client = open_connector(account.broker, account.credential_prefix)
    if not identity_matches(
        storage_root,
        account_id=account.account_id,
        client_code=identity,
    ):
        raise PortfolioError(
            "IDENTITY_MISMATCH",
            "credentials do not match the registered broker identity",
        )
    client.login()
    authenticated = client.authenticated_client_code
    if authenticated is not None and authenticated != identity:
        raise PortfolioError(
            "IDENTITY_MISMATCH",
            "authenticated broker identity does not match the registered account",
        )
    return account, client


def _fetch_snapshot(client: BrokerConnector, section: Section) -> RecordSnapshot:
    if section is Section.HOLDINGS:
        return client.holdings()
    if section is Section.POSITIONS:
        return client.positions()
    if section is Section.ORDERS:
        return client.orders()
    if section is Section.TRADES:
        return client.trades()
    return client.gtt_rules()


def _section_source(client: BrokerConnector, section: Section) -> str:
    return f"{client.broker}_{section.value.upper()}"


def _section_body_safe(client: BrokerConnector, section: Section) -> dict[str, object]:
    source = _section_source(client, section)
    if section not in client.capabilities:
        return section_body(
            section,
            status=STATUS_UNSUPPORTED,
            source=source,
            error_code="SECTION_UNSUPPORTED",
            message="broker does not support this section",
        )
    try:
        snapshot = _fetch_snapshot(client, section)
        records = section_records(section, snapshot)
        limitations = section_limitations(section, snapshot)
    except PortfolioError as exc:
        return section_body(
            section,
            status=STATUS_UNAVAILABLE,
            source=source,
            error_code=exc.code,
            message=exc.message,
        )
    return section_body(
        section,
        status=STATUS_OK,
        source=source,
        records=records,
        limitations=limitations,
    )


def _cell(value: object) -> str:
    return "-" if value is None else str(value)


def _section_table(section: str, records: Sequence[object]) -> str:
    rows = [
        cast("dict[str, object]", item) for item in records if isinstance(item, dict)
    ]
    if section == Section.HOLDINGS.value:
        return _table(
            ("Symbol", "Exch", "Qty", "Avg", "LTP", "Value", "P&L", "P&L %"),
            [
                (
                    _cell(row.get("symbol")),
                    _cell(row.get("exchange")),
                    _quantity(row.get("quantity")),
                    _money(row.get("average_price")),
                    _money(row.get("last_price")),
                    _money(row.get("current")),
                    _money(row.get("pnl")),
                    _percent(row.get("pnl_pct")),
                )
                for row in rows
            ],
            right=_RIGHT,
        )
    if section == Section.POSITIONS.value:
        return _table(
            ("Symbol", "Exch", "Product", "Qty", "Avg", "LTP", "P&L"),
            [
                (
                    _cell(row.get("symbol")),
                    _cell(row.get("exchange")),
                    _cell(row.get("product_type")),
                    _quantity(row.get("quantity")),
                    _money(row.get("average_price")),
                    _money(row.get("last_price")),
                    _money(row.get("pnl")),
                )
                for row in rows
            ],
            right=_RIGHT,
        )
    if section == Section.ORDERS.value:
        return _table(
            ("Time", "Symbol", "Side", "Qty", "Filled", "Price", "Type", "Status"),
            [
                (
                    _cell(row.get("reported_at")),
                    _cell(row.get("symbol")),
                    _cell(row.get("side")),
                    _quantity(row.get("quantity")),
                    _quantity(row.get("filled_quantity")),
                    _money(row.get("price")),
                    _cell(row.get("order_type")),
                    _cell(row.get("status")),
                )
                for row in rows
            ],
            right=_RIGHT,
        )
    if section == Section.TRADES.value:
        return _table(
            ("Time", "Symbol", "Side", "Qty", "Price", "Value", "Order"),
            [
                (
                    _cell(row.get("reported_at")),
                    _cell(row.get("symbol")),
                    _cell(row.get("side")),
                    _quantity(row.get("quantity")),
                    _money(row.get("price")),
                    _money(row.get("trade_value")),
                    _cell(row.get("order_id")),
                )
                for row in rows
            ],
            right=_RIGHT,
        )
    return _table(
        ("Symbol", "Side", "Qty", "Trigger", "Limit", "Status", "Expires"),
        [
            (
                _cell(row.get("symbol")),
                _cell(row.get("side")),
                _quantity(row.get("quantity")),
                _money(row.get("trigger_price")),
                _money(row.get("price")),
                _cell(row.get("status")),
                _cell(row.get("expires_at")),
            )
            for row in rows
        ],
        right=_RIGHT,
    )


def _emit_section(payload: dict[str, object], output: str) -> int:
    if output == "json":
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
        return 0
    print(
        f"{str(payload['section']).title()} | {payload['status']} | "
        f"{payload['source']} at {payload['retrieved_at']}"
    )
    records = _objects(payload["records"], "section records are invalid")
    if records:
        print(_section_table(str(payload["section"]), records))
    else:
        print("No records.")
    limitations = _objects(payload["limitations"], "section limitations are invalid")
    if limitations:
        print("Limitations: " + ", ".join(str(item) for item in limitations))
    return 0


def _emit_snapshot(payload: dict[str, object], output: str) -> int:
    if output == "json":
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    else:
        sections = _mapping(payload["sections"], "snapshot sections are invalid")
        rows: list[tuple[str, str, str, str]] = []
        for section in SECTION_ORDER:
            body = _mapping(sections.get(section.value), "snapshot section is invalid")
            rows.append(
                (
                    section.value,
                    str(body["status"]),
                    str(len(_objects(body["records"], "section records are invalid"))),
                    str(body["source"]),
                )
            )
        print("Read-only broker snapshot")
        print(_table(("Section", "Status", "Records", "Source"), rows, right=_RIGHT))
        limitations = _objects(
            payload["limitations"], "snapshot limitations are invalid"
        )
        if limitations:
            print("Limitations: " + ", ".join(str(item) for item in limitations))
    sections = _mapping(payload["sections"], "snapshot sections are invalid")
    complete = all(
        _mapping(sections.get(section.value), "snapshot section is invalid").get(
            "status"
        )
        == STATUS_OK
        for section in SECTION_ORDER
    )
    return 0 if complete else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="portfolio",
        description="Live, read-only broker accounts, records, and review.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    accounts = commands.add_parser("accounts", help="manage broker accounts")
    account_commands = accounts.add_subparsers(dest="account_command", required=True)

    add = account_commands.add_parser("add", help="register a broker account")
    add.add_argument("--storage-root", type=Path, required=True)
    add.add_argument("--account-id", required=True)
    add.add_argument("--display-name", required=True)
    add.add_argument("--broker", default="angel-one")
    add.add_argument("--credential-prefix", required=True)
    add.add_argument("--output", choices=("json", "table"), default="table")

    listing = account_commands.add_parser("list", help="list broker accounts")
    listing.add_argument("--storage-root", type=Path, required=True)
    listing.add_argument("--output", choices=("json", "table"), default="table")

    verify = account_commands.add_parser("verify", help="re-verify a broker account")
    verify.add_argument("--storage-root", type=Path, required=True)
    verify.add_argument("--account", required=True)
    verify.add_argument("--output", choices=("json", "table"), default="table")

    review = commands.add_parser("review", help="fetch and review live holdings")
    review.add_argument("--storage-root", type=Path, required=True)
    review.add_argument("--account", required=True)
    review.add_argument("--output", choices=("json", "table"), default="table")

    record_commands = {
        "holdings": "fetch live holdings records",
        "positions": "fetch live position records",
        "orders": "fetch the live order book",
        "trades": "fetch the live trade book",
        "gtt": "fetch live GTT rules",
    }
    for name, help_text in record_commands.items():
        record = commands.add_parser(name, help=help_text)
        record.add_argument("--storage-root", type=Path, required=True)
        record.add_argument("--account", required=True)
        record.add_argument("--output", choices=("json", "table"), default="table")

    snapshot = commands.add_parser(
        "snapshot", help="fetch every supported read-only record section"
    )
    snapshot.add_argument("--storage-root", type=Path, required=True)
    snapshot.add_argument("--account", required=True)
    snapshot.add_argument("--output", choices=("json", "table"), default="table")
    return parser


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "accounts":
        if args.account_command == "add":
            return _emit_account(
                add_account(
                    args.storage_root,
                    account_id=args.account_id,
                    broker=args.broker,
                    display_name=args.display_name,
                    credential_prefix=args.credential_prefix,
                ),
                args.output,
            )
        if args.account_command == "list":
            return _emit_accounts(list_accounts(args.storage_root), args.output)
        if args.account_command == "verify":
            return _emit_account(
                verify_account(args.storage_root, account_id=args.account),
                args.output,
            )
    if args.command == "review":
        account, client = _open_client(args.storage_root, args.account)
        snapshot = client.holdings()
        return _emit_review(
            review_payload(account.account_id, account.broker, snapshot),
            args.output,
        )
    if args.command in {"holdings", "positions", "orders", "trades", "gtt"}:
        section = Section(args.command)
        account, client = _open_client(args.storage_root, args.account)
        if section not in client.capabilities:
            raise PortfolioError(
                "SECTION_UNSUPPORTED",
                "broker does not support this section",
            )
        retrieved_at = _now()
        snapshot = _fetch_snapshot(client, section)
        body = section_body(
            section,
            status=STATUS_OK,
            source=_section_source(client, section),
            records=section_records(section, snapshot),
            limitations=section_limitations(section, snapshot),
        )
        payload = section_payload(
            account_id=account.account_id,
            broker=account.broker,
            section=section,
            retrieved_at=retrieved_at,
            body=body,
        )
        return _emit_section(payload, args.output)
    if args.command == "snapshot":
        account, client = _open_client(args.storage_root, args.account)
        retrieved_at = _now()
        capabilities = tuple(
            section for section in SECTION_ORDER if section in client.capabilities
        )
        sections = {
            section.value: _section_body_safe(client, section)
            for section in SECTION_ORDER
        }
        payload = snapshot_payload(
            account_id=account.account_id,
            broker=account.broker,
            retrieved_at=retrieved_at,
            capabilities=capabilities,
            sections=sections,
        )
        return _emit_snapshot(payload, args.output)
    raise PortfolioError("INVALID_ARGUMENT", "unknown command")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        return _dispatch(args)
    except PortfolioError as exc:
        print(_error_json(exc.code, exc.message), file=sys.stderr)
        return 2 if exc.code in _INVALID_CODES else 1
    except OSError:
        print(
            _error_json("IO_ERROR", "private storage is unavailable"), file=sys.stderr
        )
        return 2
    except Exception:
        print(_error_json("INTERNAL_ERROR", "internal error"), file=sys.stderr)
        return 2


__all__ = ["main"]
