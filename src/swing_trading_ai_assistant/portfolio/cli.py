"""Installed live broker portfolio CLI."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
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
from .angel_one import AngelOneClient, load_credentials, review_payload
from .errors import PortfolioError

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


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="portfolio",
        description="Live, read-only broker portfolio accounts and review.",
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
        account = get_account(args.storage_root, args.account)
        credentials = load_credentials(account.credential_prefix)
        if not identity_matches(
            args.storage_root,
            account_id=account.account_id,
            client_code=credentials.client_code,
        ):
            raise PortfolioError(
                "IDENTITY_MISMATCH",
                "credentials do not match the registered broker identity",
            )
        client = AngelOneClient(credentials)
        client.login()
        authenticated = client.authenticated_client_code
        if authenticated is not None and authenticated != credentials.client_code:
            raise PortfolioError(
                "IDENTITY_MISMATCH",
                "authenticated broker identity does not match the registered account",
            )
        snapshot = client.holdings()
        return _emit_review(
            review_payload(account.account_id, account.broker, snapshot),
            args.output,
        )
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
