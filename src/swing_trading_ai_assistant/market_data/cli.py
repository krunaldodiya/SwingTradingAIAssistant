"""Command-line adapter for market-data diagnostics."""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from dotenv import load_dotenv

from .credentials import EnvironmentAccessTokenProvider
from .historical import UpstoxV3HistoricalClient
from .http import DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES, UrllibHttpTransport
from .instruments import DEFAULT_MAX_CATALOG_COMPRESSED_BYTES, InstrumentCatalogClient
from .probe import ProbeRequest, run_capability_probe


def _date(value: str) -> date:
    if value == "YYYY-MM-DD":
        raise argparse.ArgumentTypeError(
            "replace YYYY-MM-DD with an actual date, for example 2026-08-03"
        )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected an actual date in YYYY-MM-DD format"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    yesterday = date.today() - timedelta(days=1)
    parser = argparse.ArgumentParser(
        prog="market-data",
        description=(
            "Market-data diagnostics. The public CLI currently validates provider "
            "access; it does not run the persistent downloader."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    probe = commands.add_parser(
        "probe-upstox",
        help="validate a master-catalog instrument without writing candle data",
        description=(
            "Validate Upstox catalog resolution and a small historical response in "
            "memory. This diagnostic does not run the persistent downloader or "
            "write market data."
        ),
    )
    probe.add_argument("--segment", required=True, help="exchange segment, e.g. NSE_EQ")
    probe.add_argument("--symbol", required=True, help="trading symbol, e.g. RELIANCE")
    probe.add_argument(
        "--from",
        dest="from_date",
        type=_date,
        default=yesterday - timedelta(days=3),
        metavar="YYYY-MM-DD",
        help="optional actual date, for example 2026-08-03; defaults to 4 days ago",
    )
    probe.add_argument(
        "--to",
        dest="to_date",
        type=_date,
        default=yesterday,
        metavar="YYYY-MM-DD",
        help="optional actual date; defaults to yesterday",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    if args.command != "probe-upstox":
        raise AssertionError("unreachable command")

    # The public NSE catalog measured 1,934,668 compressed bytes on 2026-08-04.
    # Keep its 4 MB cap separate from the smaller authenticated historical cap.
    catalog_transport = UrllibHttpTransport(
        max_body_bytes=DEFAULT_MAX_CATALOG_COMPRESSED_BYTES
    )
    historical_transport = UrllibHttpTransport(
        max_body_bytes=DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES
    )
    try:
        report = run_capability_probe(
            ProbeRequest(
                segment=args.segment,
                symbol=args.symbol,
                from_date=args.from_date,
                to_date=args.to_date,
            ),
            token_provider=EnvironmentAccessTokenProvider(),
            catalog_client=InstrumentCatalogClient(catalog_transport),
            historical_client=UpstoxV3HistoricalClient(historical_transport),
        )
    except Exception as exc:
        # Print only the exception class. Adapter messages and secrets never cross
        # this diagnostic boundary on failure.
        print(f"probe_failed:{type(exc).__name__}", file=sys.stderr)
        return 2
    print(report.to_json())
    return 0 if report.status == 200 and report.schema_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
