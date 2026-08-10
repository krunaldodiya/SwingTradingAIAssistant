"""Command-line adapter for market-data diagnostics."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

from .credentials import EnvironmentAccessTokenProvider
from .download_preparation import (
    AuthoritativeScheduleInputV1,
    DownloadPreparationServiceV1,
)
from .historical import UpstoxV3HistoricalClient
from .http import DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES, UrllibHttpTransport
from .instrument_snapshot import InstrumentSnapshotClientV1
from .instruments import DEFAULT_MAX_CATALOG_COMPRESSED_BYTES, InstrumentCatalogClient
from .preview_admission import PreviewAdmissionPolicyV1
from .probe import ProbeRequest, run_capability_probe
from .public_contract import (
    DownloadReportV1,
    public_exit_code,
    render_download_report_json,
)
from .public_download import (
    SingleSymbolDownloadRequestV1,
    SingleSymbolDownloadServiceV1,
)
from .range_ingestion import IngestionCoordinator

_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


class PublicDownloadPortV1(Protocol):
    def download(self, request: object) -> DownloadReportV1: ...


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class _UnavailableAuthoritativeScheduleSource:
    def load(self) -> AuthoritativeScheduleInputV1:
        raise RuntimeError("authoritative schedule source is not configured")


def _date(value: str) -> date:
    if value == "YYYY-MM-DD":
        raise argparse.ArgumentTypeError(
            "replace YYYY-MM-DD with an actual date, for example 2026-08-03"
        )
    if _DATE.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("expected an actual date in YYYY-MM-DD format")
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
            "Deterministic market-data diagnostics and persistent preview commands."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser(
        "download",
        help="persist one admitted closed-range one-minute download",
    )
    download.add_argument("--segment", required=True)
    download.add_argument("--symbol", required=True)
    download.add_argument(
        "--from", dest="from_date", type=_date, required=True, metavar="YYYY-MM-DD"
    )
    download.add_argument(
        "--to", dest="to_date", type=_date, required=True, metavar="YYYY-MM-DD"
    )
    download.add_argument(
        "--storage-root", type=Path, required=True, metavar="ABSOLUTE_PATH"
    )
    download.add_argument("--output", choices=("json",), required=True)
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


def main(
    argv: list[str] | None = None,
    *,
    download_service: PublicDownloadPortV1 | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "download":
        service = download_service or _default_download_service()
        try:
            request: object = SingleSymbolDownloadRequestV1(
                args.segment,
                args.symbol,
                args.from_date,
                args.to_date,
                args.storage_root,
            )
        except ValueError:
            request = object()
        report = service.download(request)
        sys.stdout.write(render_download_report_json(report).decode("utf-8"))
        return public_exit_code(report.status)
    if args.command == "probe-upstox":
        return _run_probe(args)
    raise AssertionError("unreachable command")


def _default_download_service() -> SingleSymbolDownloadServiceV1:
    clock = _SystemClock()
    transport = UrllibHttpTransport(max_body_bytes=DEFAULT_MAX_CATALOG_COMPRESSED_BYTES)
    preparation = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        _UnavailableAuthoritativeScheduleSource(),
        InstrumentSnapshotClientV1(transport, clock=clock.now),
    )
    return SingleSymbolDownloadServiceV1(
        preparation, IngestionCoordinator(), clock=clock
    )


def _run_probe(args: argparse.Namespace) -> int:
    load_dotenv()
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
