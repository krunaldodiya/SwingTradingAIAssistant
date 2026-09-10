"""CLI for configured-root structured daily OHLCV persistence."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from swing_trading_ai_assistant.market_data.bharatstock import BharatStockInstrument

from .core import (
    DownloadError,
    PersistenceError,
    default_storage_root,
    download_daily_ohlcv,
)


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from None


def _instrument(value: str) -> BharatStockInstrument:
    try:
        isin, exchange, symbol = value.split(":")
        return BharatStockInstrument(isin, exchange, symbol)
    except ValueError:
        raise argparse.ArgumentTypeError("expected ISIN:NSE-or-BSE:SYMBOL") from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="equity-data-download",
        epilog="New acquisition uses BHARATSTOCK_API_KEY; exact retained reads need no key.",
    )
    parser.add_argument(
        "--instrument",
        action="append",
        required=True,
        type=_instrument,
        help="ISIN:EXCHANGE:SYMBOL; repeat in the requested order",
    )
    parser.add_argument("--start", required=True, type=_date, help="inclusive date")
    parser.add_argument("--end", required=True, type=_date, help="inclusive date")
    parser.add_argument(
        "--storage-root",
        type=Path,
        default=default_storage_root(),
        help="single structured-data root",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        receipt = download_daily_ohlcv(
            tuple(arguments.instrument),
            arguments.start,
            arguments.end,
            arguments.storage_root,
        )
    except ValueError as error:
        sys.stderr.write(f"invalid request: {error}\n")
        return 2
    except (DownloadError, PersistenceError) as error:
        sys.stderr.write(f"download failed: {error}\n")
        return 1
    payload = {
        "destination": str(receipt.destination),
        "end": receipt.end.isoformat(),
        "format": "PARQUET",
        "outcome": receipt.outcome,
        "price_basis": receipt.price_basis,
        "provider": receipt.provider,
        "provider_version": receipt.provider_version,
        "retrieved_at": receipt.retrieved_at.isoformat().replace("+00:00", "Z"),
        "row_count": receipt.row_count,
        "rows_by_instrument": dict(receipt.rows_by_instrument),
        "request_identity_sha256": receipt.request_identity_sha256,
        "start": receipt.start.isoformat(),
        "instruments": [
            {"isin": item.isin, "exchange": item.exchange, "symbol": item.symbol}
            for item in receipt.instruments
        ],
        "volume_basis": receipt.volume_basis,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
