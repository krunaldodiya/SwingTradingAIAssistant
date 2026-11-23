"""Installed read-only portfolio CLI."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from .accounts import (
    AccountRecord,
    add_account,
    get_account,
    list_accounts,
)
from .errors import PortfolioError
from .snapshot import (
    Snapshot,
    import_snapshot,
    load_latest_snapshot,
    review_payload,
)

_RIGHT = frozenset({2, 3, 4, 5, 6, 7, 8})


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PortfolioError("SNAPSHOT_CORRUPT", message)
    return cast("dict[str, object]", value)


def _objects(value: object, message: str) -> list[object]:
    if not isinstance(value, list):
        raise PortfolioError("SNAPSHOT_CORRUPT", message)
    return cast("list[object]", value)


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
            ("Account", "Broker", "Name", "Created", "Last import"),
            [
                (
                    record.account_id,
                    record.broker,
                    record.display_name,
                    record.created_at,
                    record.last_import_at or "-",
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
        print("No portfolio accounts.")
        return 0
    print(
        _table(
            ("Account", "Broker", "Name", "Created", "Last import"),
            [
                (
                    record.account_id,
                    record.broker,
                    record.display_name,
                    record.created_at,
                    record.last_import_at or "-",
                )
                for record in records
            ],
        )
    )
    return 0


def _import_payload(snapshot: Snapshot) -> dict[str, object]:
    return {
        "schema_version": 1,
        "account_id": snapshot.account_id,
        "snapshot_id": snapshot.snapshot_id,
        "as_of": snapshot.as_of,
        "imported_at": snapshot.imported_at,
        "holdings": len(snapshot.holdings),
        "rejected": [
            {"row": item.row, "symbol": item.symbol, "reason": item.reason}
            for item in snapshot.rejected
        ],
        "limitations": list(snapshot.limitations),
    }


def _emit_import(snapshot: Snapshot, output: str) -> int:
    payload = _import_payload(snapshot)
    if output == "json":
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
        return 0
    print(
        f"Imported {payload['holdings']} holding(s) for {payload['account_id']} "
        f"as of {payload['as_of']} (snapshot {payload['snapshot_id']})"
    )
    rejected = _objects(payload["rejected"], "import rejected rows are invalid")
    if rejected:
        rejected_rows: list[tuple[str, str, str]] = []
        for item in rejected:
            if isinstance(item, dict):
                row = cast("dict[str, object]", item)
                rejected_rows.append(
                    (str(row["row"]), str(row["symbol"] or "-"), str(row["reason"]))
                )
        print(_table(("Row", "Symbol", "Reason"), rejected_rows))
    limitations = _objects(payload["limitations"], "import limitations are invalid")
    if limitations:
        print("Limitations: " + ", ".join(str(item) for item in limitations))
    return 0


def _emit_review(payload: dict[str, object], output: str) -> int:
    if output == "json":
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
        return 0
    summary = _mapping(payload["summary"], "review summary is invalid")
    print(
        f"Account {payload['account_id']} ({payload['broker']}) "
        f"as of {payload['as_of']} | snapshot {payload['snapshot_id']}"
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
                _percent(row["weight_pct"]),
            )
        )
    print(
        _table(
            ("Symbol", "Qty", "Avg", "LTP", "Value", "P&L", "P&L %", "Weight"),
            table_rows,
            right=_RIGHT,
        )
    )
    limitations = _objects(payload["limitations"], "review limitations are invalid")
    if limitations:
        print("Limitations: " + ", ".join(str(item) for item in limitations))
    rejected = _objects(payload["rejected"], "review rejected rows are invalid")
    if rejected:
        print("Rejected rows: " + str(len(rejected)))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="portfolio",
        description="Read-only manual portfolio registry and review.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    accounts = commands.add_parser("accounts", help="manage portfolio accounts")
    account_commands = accounts.add_subparsers(dest="account_command", required=True)

    add = account_commands.add_parser("add", help="register one manual account")
    add.add_argument("--storage-root", type=Path, required=True)
    add.add_argument("--account-id", required=True)
    add.add_argument("--display-name", required=True)
    add.add_argument("--broker", choices=("manual",), default="manual")
    add.add_argument("--output", choices=("json", "table"), default="table")

    listing = account_commands.add_parser("list", help="list accounts")
    listing.add_argument("--storage-root", type=Path, required=True)
    listing.add_argument("--output", choices=("json", "table"), default="table")

    importer = commands.add_parser("import", help="import a manual CSV snapshot")
    importer.add_argument("--storage-root", type=Path, required=True)
    importer.add_argument("--account", required=True)
    importer.add_argument("--file", type=Path, required=True)
    importer.add_argument("--as-of", required=True)
    importer.add_argument("--output", choices=("json", "table"), default="table")

    review = commands.add_parser("review", help="review the latest snapshot")
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
                    display_name=args.display_name,
                    broker=args.broker,
                ),
                args.output,
            )
        if args.account_command == "list":
            return _emit_accounts(list_accounts(args.storage_root), args.output)
    if args.command == "import":
        snapshot = import_snapshot(
            args.storage_root,
            account_id=args.account,
            file_path=args.file,
            as_of=args.as_of,
        )
        return _emit_import(snapshot, args.output)
    if args.command == "review":
        account = get_account(args.storage_root, args.account)
        snapshot = load_latest_snapshot(args.storage_root, args.account)
        return _emit_review(review_payload(account, snapshot), args.output)
    raise PortfolioError("INVALID_ARGUMENT", "unknown command")


_INVALID_CODES = frozenset(
    {
        "INVALID_ARGUMENT",
        "ACCOUNT_ID_INVALID",
        "CREDENTIAL_PREFIX_INVALID",
        "DISPLAY_NAME_INVALID",
        "BROKER_UNSUPPORTED",
        "INPUT_UNREADABLE",
        "INPUT_TOO_LARGE",
        "INPUT_HEADER_INVALID",
        "AS_OF_INVALID",
        "NO_VALID_HOLDINGS",
    }
)


def _error_json(code: str, message: str) -> str:
    return json.dumps(
        {"status": "error", "error_code": code, "message": message},
        sort_keys=True,
        allow_nan=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except PortfolioError as exc:
        print(_error_json(exc.code, exc.message), file=sys.stderr)
        return 2 if exc.code in _INVALID_CODES else 1
    except OSError:
        print(
            _error_json("IO_ERROR", "private storage is unavailable"), file=sys.stderr
        )
        return 1
    except Exception:
        print(_error_json("INTERNAL_ERROR", "internal error"), file=sys.stderr)
        return 2


__all__ = ["main"]
