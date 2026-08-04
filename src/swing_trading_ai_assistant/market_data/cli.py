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
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    yesterday = date.today() - timedelta(days=1)
    parser = argparse.ArgumentParser(prog="market-data")
    commands = parser.add_subparsers(dest="command", required=True)
    probe = commands.add_parser(
        "probe-upstox",
        help="validate a master-catalog instrument without writing candle data",
    )
    probe.add_argument("--segment", required=True)
    probe.add_argument("--symbol", required=True)
    probe.add_argument(
        "--from", dest="from_date", type=_date, default=yesterday - timedelta(days=3)
    )
    probe.add_argument("--to", dest="to_date", type=_date, default=yesterday)
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
