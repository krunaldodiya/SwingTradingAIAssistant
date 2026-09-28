"""Command-line adapter for market-data diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any, Literal, Never, Protocol, cast

from dotenv import load_dotenv

from swing_trading_ai_assistant.market_regime.current_supplied_cohort import (
    CurrentSuppliedCohortMarketRegimeInputV1,
    DirectCurrentCohortArchiveReaderV1,
    DirectCurrentCohortScheduleResolverV1,
    current_supplied_cohort_market_regime_runtime_code_identity_v1,
    evaluate_current_supplied_cohort_market_regime_v1,
)
from swing_trading_ai_assistant.research_packet.current_price_context import (
    current_price_context_request_from_canonical_json_bytes_v1,
    research_current_price_context_v1,
)
from swing_trading_ai_assistant.research_packet.current_price_context_v2 import (
    current_price_context_request_from_canonical_json_bytes_v2,
    research_current_price_context_v2,
)
from swing_trading_ai_assistant.volume_analysis import (
    research_current_volume,
    volume_request_from_json,
)
from swing_trading_ai_assistant.volume_analysis.request import (
    canonical_bytes as volume_json,
)

from .account_rate_limit import ThreadSafeAccountRateLimiterV1
from .agent_cohort_context import run_agent_cohort_research_current
from .agent_cohort_request import (
    parse_agent_cohort_mappings,
    validate_agent_cohort_request,
)
from .agent_event_context import run_agent_event_research_current
from .agent_research_run import (
    run_agent_research_current,
    run_agent_swing_research_current,
)
from .bounded_nifty50_workflow import (
    BoundedNifty50DownloadReportV1,
    BoundedNifty50DownloadRequestV1,
    BoundedNifty50DownloadServiceV1,
    CanonicalFileNifty50UniverseSourceV1,
    Nifty50BatchOutcomeV1,
    bounded_nifty50_exit_code,
    render_bounded_nifty50_download_json,
)
from .credentials import (
    AccessToken,
    CredentialNotFoundError,
    EnvironmentAccessTokenProvider,
)
from .current_cohort import (
    CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1,
    CURRENT_COHORT_SOURCE_POLICY_IDENTITY_SHA256_V1,
    MAX_COHORT_FILE_BYTES_V1,
    CurrentCohortMarketDataReportV1,
    CurrentCohortMarketDataRequestV1,
    CurrentCohortMarketDataServiceV1,
    CurrentCohortQueryRequestFactoryV1,
    CurrentCohortRetainedQueryPortV1,
    CurrentEvidenceStateV1,
    CurrentSuppliedCohortAdmissionPolicyV1,
    ImmutableCurrentFactArchiveV1,
    RetainedCurrentCohortInstrumentResolverV1,
    RetainedCurrentNifty50UniverseResolverV1,
    parse_current_cohort_manifest_bytes_v1,
)
from .current_stock_research import (
    CurrentStockResearchInputError,
    CurrentStockResearchResultV1,
    research_current_stock_v1,
)
from .current_stock_research_v2 import (
    CurrentStockResearchResultV2,
    QuestionV2,
    confirm_latest_completed_stock_v2,
    research_current_stock_v2,
    research_previous_completed_stock_v2,
)
from .daily_ohlcv import (
    DailyQueryServiceV1,
    DuckDBDailyOHLCVEngineV1,
    RetainedDailyScheduleResolverV1,
    TimeframeQueryServiceV1,
)
from .download_preparation import (
    AuthoritativeScheduleInputV1,
    CanonicalFileScheduleSourceV1,
    DownloadPreparationServiceV1,
)
from .equity_admission import EquityAdmissionPolicyV1
from .historical import (
    AccountRateLimiter,
    HistoricalPayloadError,
    HistoricalRequest,
    HistoricalResponse,
    UpstoxV3HistoricalClient,
)
from .historical_revision_store import (
    HistoricalOhlcvImportOutcomeV1,
    HistoricalOhlcvImportResultV1,
    HistoricalOhlcvRevisionStoreV1,
)
from .historical_upstox_raw import complete_upstox_raw_historical_ohlcv_v1
from .http import (
    DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES,
    HttpResponseBodyTooLarge,
    HttpResponseHeadersInvalid,
    HttpTransportError,
    UrllibHttpTransport,
)
from .instrument_snapshot import InstrumentSnapshotClientV1
from .instruments import (
    DEFAULT_MAX_CATALOG_COMPRESSED_BYTES,
    AmbiguousInstrumentError,
    CatalogPayloadTooLargeError,
    InstrumentCatalogClient,
    InstrumentCatalogPayloadError,
    InstrumentCatalogRequestError,
    InstrumentNotFoundError,
)
from .intraday import UpstoxV3IntradayClient
from .intraday_views import (
    DerivedIntradayQueryServiceV1,
    DuckDBIntradayViewEngineV1,
    OpenMonthDerivedIntradayQueryServiceV1,
    RetainedOpenMonthScheduleResolverV1,
)
from .nifty50_read_workflow import (
    BoundedNifty50ReadRequestV1,
    BoundedPointInTimeNifty50ReadServiceV1,
    PointInTimeNifty50CoverageServiceV1,
    PointInTimeNifty50QueryServiceV1,
    bounded_nifty50_read_terminal,
    render_bounded_nifty50_read_json,
)
from .open_month_coverage import (
    CurrentAwareCoverageServiceV1,
    OpenMonthCoverageServiceV1,
)
from .open_month_download import OpenMonthDownloadServiceV1
from .open_month_query import (
    CurrentAwareQueryServiceV1,
    OpenMonthOneMinuteQueryServiceV1,
)
from .preview_admission import PreviewAdmissionPolicyV1
from .probe import ProbeRequest, run_capability_probe
from .public_contract import (
    MAX_DAILY_QUERY_ROWS_V1,
    CandleFieldV1,
    CoverageReportV1,
    DownloadReportV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicFailureCodeV1,
    PublicFailureV1,
    PublicQueryRequestV1,
    QueryReportV1,
    public_exit_code,
    render_coverage_report_json,
    render_download_report_json,
    render_query_report_json,
)
from .public_coverage import (
    CoverageRequestV1,
    StoredCoverageEvaluatorV1,
    StoredCoverageServiceV1,
)
from .public_download import (
    CurrentAwareSingleSymbolDownloadServiceV1,
    SingleSymbolDownloadRequestV1,
    SingleSymbolDownloadServiceV1,
)
from .public_query import (
    DuckDBOneMinuteQueryEngineV1,
    OneMinuteQueryServiceV1,
    QueryRequestV1,
)
from .range_ingestion import (
    IngestionCoordinator,
    ProviderSessionAuthenticationError,
)
from .schedule_evidence import ScheduleEvidenceValidationError
from .storage_root_lease import StorageRootLease, StorageRootLeaseError
from .watchlist_screen import screen_watchlist_current
from .workflow_coordination import PublicationGateV1

_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_DEFAULT_STORAGE_DIRECTORY = "SwingTradingAIAssistantData"


class _RequestInvalid(ValueError):
    """An explicitly rejected CLI input or storage admission."""

    def __init__(self, *, already_reported: bool = False) -> None:
        self.already_reported = already_reported


def _render_request_invalid(error: _RequestInvalid) -> None:
    if not error.already_reported:
        sys.stderr.write("request_invalid\n")


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        self.exit(2, "request_invalid\n")


def _parse_cli_args(argv: list[str] | None) -> argparse.Namespace:
    try:
        return build_parser().parse_args(argv)
    except SystemExit as error:
        if argv and argv[0] == "price-context-current":
            raise _RequestInvalid(already_reported=True) from error
        raise


class PublicDownloadPortV1(Protocol):
    def download(self, request: object) -> DownloadReportV1: ...


class PublicCoveragePortV1(Protocol):
    def coverage(self, request: object) -> CoverageReportV1: ...


class PublicQueryPortV1(Protocol):
    def query(self, request: object) -> QueryReportV1: ...


class CurrentCohortServicePortV1(Protocol):
    def evaluate(
        self, request: CurrentCohortMarketDataRequestV1
    ) -> CurrentCohortMarketDataReportV1: ...


class CurrentStockResearchPortV1(Protocol):
    def __call__(
        self, symbol: str, storage_root: Path, *, refresh: bool = False
    ) -> CurrentStockResearchResultV1: ...


class CurrentStockResearchPortV2(Protocol):
    def __call__(
        self,
        symbol: str,
        storage_root: Path,
        *,
        question: QuestionV2,
        refresh: bool = False,
    ) -> CurrentStockResearchResultV2: ...


class _ClockV1(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class _CommandAdmissionV1:
    request: object
    universe_source: CanonicalFileNifty50UniverseSourceV1 | None
    admitted: bool
    invalid_universe_source: bool = False


@dataclass(frozen=True, slots=True)
class _AdmittedHistoricalStorageRootV1:
    path: Path
    identity: tuple[int, int]
    path_parts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _AdmittedHistoricalLocalFileV1:
    path_parts: tuple[str, ...]
    identity: tuple[int, int]
    raw: bytes


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class _FixedClock:
    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant


def _trusted_now(clock: _ClockV1) -> datetime:
    value = clock.now()
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError("invalid trusted clock")
    return value


class _UnavailableAuthoritativeScheduleSource:
    def load(self) -> AuthoritativeScheduleInputV1:
        raise ScheduleEvidenceValidationError(
            "authoritative schedule source is not configured"
        )


class _LazyEnvironmentAccessTokenProvider:
    """Read the process environment only when a provider call is actually needed."""

    def get_access_token(self) -> AccessToken:
        return EnvironmentAccessTokenProvider().get_access_token()


class _HistoricalProviderSession:
    def __init__(self, client: UpstoxV3HistoricalClient, token: AccessToken) -> None:
        self._client = client
        self._token = token

    def fetch(self, request: HistoricalRequest) -> HistoricalResponse:
        return self._client.fetch(request, self._token)


class _HistoricalProviderSessionFactory:
    def __init__(
        self,
        client: UpstoxV3HistoricalClient,
        token_provider: _LazyEnvironmentAccessTokenProvider,
    ) -> None:
        self._client = client
        self._token_provider = token_provider

    def open(self) -> _HistoricalProviderSession:
        try:
            token = self._token_provider.get_access_token()
        except CredentialNotFoundError:
            raise ProviderSessionAuthenticationError from None
        return _HistoricalProviderSession(self._client, token)


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


def _utc_instant(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "expected UTC instant YYYY-MM-DDTHH:MM:SS.ffffffZ"
        ) from error
    return parsed


def build_parser() -> argparse.ArgumentParser:
    probe_from, probe_to = _default_probe_range(date.today())
    parser = _ArgumentParser(
        prog="market-data",
        description=(
            "Deterministic market-data diagnostics and persistent preview commands."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser(
        "download",
        help="persist one or many point-in-time Nifty 50 one-minute downloads",
    )
    _add_persistent_range_arguments(download)
    selection = download.add_mutually_exclusive_group(required=True)
    selection.add_argument("--symbol", help="one Nifty 50 trading symbol")
    selection.add_argument(
        "--symbols",
        type=_symbols,
        help="comma-separated Nifty 50 trading symbols",
    )
    selection.add_argument(
        "--universe",
        choices=("nifty50-current",),
        help="all members of the retained point-in-time Nifty 50 snapshot",
    )
    download.add_argument(
        "--universe-file",
        type=Path,
        metavar="ABSOLUTE_PATH",
        help="canonical point-in-time Nifty 50 JSON to retain before download",
    )
    download.add_argument(
        "--universe-as-of",
        type=_date,
        metavar="YYYY-MM-DD",
        help="membership date; defaults to the requested end date",
    )
    download.add_argument(
        "--workers",
        type=int,
        choices=range(1, 9),
        default=4,
        metavar="1..8",
        help="bounded concurrent provider workers (default: 4)",
    )
    download.add_argument(
        "--schedule-file",
        type=Path,
        metavar="ABSOLUTE_PATH",
        help="canonical authoritative schedule JSON for this download",
    )
    download.add_argument(
        "--closed-schedule-file",
        type=Path,
        metavar="ABSOLUTE_PATH",
        help=(
            "canonical v2 schedule for closed months when the range also "
            "touches the current month"
        ),
    )
    coverage = commands.add_parser(
        "coverage",
        help="prove retained scheduled-minute coverage without provider access",
    )
    _add_persistent_range_arguments(coverage)
    _add_read_selection(coverage)
    query = commands.add_parser(
        "query",
        help="query bounded verified candles without provider access",
    )
    _add_persistent_range_arguments(query)
    _add_read_selection(query)
    query.add_argument("--timeframe", required=True)
    query.add_argument("--fields", required=True)
    query.add_argument("--max-rows", type=int, required=True)
    cohort_current = commands.add_parser(
        "cohort-current",
        help="return retained current market-data for an owner-supplied cohort",
    )
    cohort_current.add_argument(
        "--cohort-file", type=Path, required=True, metavar="ABSOLUTE_JSON_FILE"
    )
    cohort_current.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        metavar="ABSOLUTE_OWNER_PRIVATE_ROOT",
    )
    cohort_current.add_argument("--cutoff", type=_utc_instant, required=True)
    cohort_current.add_argument(
        "--include-partial-current-session", action="store_true"
    )
    cohort_current.add_argument("--output", choices=("json",), required=True)
    regime_current = commands.add_parser(
        "regime-current",
        help="return one aggregate market-regime fact from immutable supplied-cohort evidence",
    )
    regime_current.add_argument(
        "--input-file", type=Path, required=True, metavar="ABSOLUTE_OWNER_PRIVATE_JSON"
    )
    regime_current.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        metavar="ABSOLUTE_OWNER_PRIVATE_ROOT",
    )
    regime_current.add_argument("--output", choices=("json",), required=True)
    volume_context = commands.add_parser(
        "volume-context-current",
        help="compare retained completed-session volume with its prior-session baseline",
    )
    volume_context.add_argument("--input-file", type=Path, required=True)
    volume_context.add_argument("--storage-root", type=Path, required=True)
    volume_context.add_argument("--output", choices=("json",), required=True)
    price_context_current = commands.add_parser(
        "price-context-current",
        help="return independent retained raw current-price context",
    )
    price_context_current.add_argument(
        "--input-file", type=Path, required=True, metavar="ABSOLUTE_OWNER_PRIVATE_JSON"
    )
    price_context_current.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        metavar="ABSOLUTE_OWNER_PRIVATE_ROOT",
    )
    price_context_current.add_argument("--acquire-missing", action="store_true")
    price_context_current.add_argument(
        "--contract-version", choices=("v1", "v2"), default="v1"
    )
    price_context_current.add_argument("--output", choices=("json",), required=True)
    historical_upstox_raw = commands.add_parser(
        "historical-ohlcv-upstox-raw",
        help="complete one retained Upstox raw daily OHLCV revision",
    )
    historical_upstox_raw.add_argument(
        "--request-file", type=Path, required=True, metavar="ABSOLUTE_JSON_FILE"
    )
    historical_upstox_raw.add_argument(
        "--source-storage-root",
        type=Path,
        default=Path.home() / "SwingTradingAIAssistantData",
        metavar="ABSOLUTE_OWNER_PRIVATE_ROOT",
    )
    historical_upstox_raw.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        metavar="ABSOLUTE_OWNER_PRIVATE_ROOT",
    )
    historical_upstox_raw.add_argument("--output", choices=("json",), required=True)
    historical_read = commands.add_parser(
        "historical-ohlcv-upstox-raw-read",
        help="read one exact immutable retained Upstox raw daily OHLCV revision",
    )
    historical_read.add_argument(
        "--revision-sha256", required=True, metavar="LOWERCASE_SHA256"
    )
    historical_read.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        metavar="ABSOLUTE_OWNER_PRIVATE_ROOT",
    )
    historical_read.add_argument("--output", choices=("json",), required=True)
    research_current = commands.add_parser(
        "research-current",
        help="prepare versioned current-stock research from completed sessions",
    )
    research_current.add_argument("--symbol", required=True)
    research_current.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        metavar="ABSOLUTE_OWNER_PRIVATE_ROOT",
    )
    research_current.add_argument("--refresh", action="store_true")
    research_current.add_argument(
        "--contract-version", choices=("v1", "v2"), default="v1"
    )
    research_current.add_argument(
        "--question",
        choices=(
            "LATEST_COMPLETED_CANDLE",
            "PRICE_BEHAVIOR",
            "CURRENT_STRUCTURE",
            "INTEGRATED_CURRENT_RESEARCH",
        ),
    )
    research_current.add_argument("--output", choices=("json",), required=True)
    watchlist = commands.add_parser(
        "watchlist-screen-current",
        help="screen an explicit bounded stock list using admitted V2 price facts",
    )
    watchlist.add_argument("--symbol", action="append", required=True)
    watchlist.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        metavar="ABSOLUTE_OWNER_PRIVATE_ROOT",
    )
    watchlist.add_argument(
        "--close-direction", choices=("UP", "DOWN", "UNCHANGED"), required=True
    )
    watchlist.add_argument("--output", choices=("json",), required=True)
    agent_run = commands.add_parser(
        "research-run-current",
        help="return compact admitted current research facts for an explicit stock list",
    )
    agent_run.add_argument("--symbol", action="append", required=True)
    agent_run.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        metavar="ABSOLUTE_OWNER_PRIVATE_ROOT",
    )
    agent_run.add_argument("--output", choices=("json",), required=True)
    agent_run.add_argument(
        "--contract-version", choices=("v1", "v2", "v3", "v4"), default="v1"
    )
    agent_run.add_argument(
        "--context-symbol",
        action="append",
        help="V4: repeat for each of 2–50 ordered comparison stocks",
    )
    agent_run.add_argument(
        "--context-purpose",
        help="V4: describe the comparison group (1–160 printable characters)",
    )
    agent_run.add_argument(
        "--context-mappings-file",
        type=Path,
        metavar="ABSOLUTE_PRIVATE_JSON",
        help=(
            "V4: private JSON declaring dated cohort mappings; omission leaves "
            "cohort context insufficient while stock research continues"
        ),
    )
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
        default=probe_from,
        metavar="YYYY-MM-DD",
        help=(
            "optional actual date, for example 2026-08-03; defaults to up to "
            "4 days ending yesterday within one calendar month"
        ),
    )
    probe.add_argument(
        "--to",
        dest="to_date",
        type=_date,
        default=probe_to,
        metavar="YYYY-MM-DD",
        help="optional actual date; defaults to yesterday",
    )
    return parser


def main(  # noqa: C901 - command dispatch remains explicit.
    argv: list[str] | None = None,
    *,
    download_service: PublicDownloadPortV1 | None = None,
    coverage_service: PublicCoveragePortV1 | None = None,
    query_service: PublicQueryPortV1 | None = None,
    current_cohort_service: CurrentCohortServicePortV1 | None = None,
    current_stock_research: CurrentStockResearchPortV1 | None = None,
    current_stock_research_v2: CurrentStockResearchPortV2 | None = None,
    current_stock_research_confirm_v2: Callable[
        [str, Path, CurrentStockResearchResultV2], CurrentStockResearchResultV2
    ]
    | None = None,
    current_stock_research_previous_v2: Callable[
        [str, Path, CurrentStockResearchResultV2], CurrentStockResearchResultV2
    ]
    | None = None,
    trusted_clock: _ClockV1 | None = None,
) -> int:
    try:
        if not _admit_regime_current_argv(argv):
            sys.stderr.write("invalid regime-current request\n")
            return 2
        args = _parse_cli_args(argv)
        if args.command == "probe-upstox":
            return _run_probe(args)
        if args.command == "cohort-current":
            return _run_current_cohort_command(
                args, current_cohort_service, trusted_clock or _SystemClock()
            )
        if args.command == "research-current":
            return _run_research_current_command(
                args, current_stock_research, current_stock_research_v2
            )
        if args.command == "watchlist-screen-current":
            return _run_watchlist_screen_command(args, current_stock_research_v2)
        if args.command == "research-run-current":
            return _run_agent_research_command(
                args,
                current_stock_research_v2,
                current_stock_research_confirm_v2,
                current_stock_research_previous_v2,
            )
        if args.command == "volume-context-current":
            return _run_volume_command(args, trusted_clock or _SystemClock())
        if args.command in {"regime-current", "price-context-current"}:
            return _run_current_packet_command(args, trusted_clock or _SystemClock())
        if args.command == "historical-ohlcv-upstox-raw":
            return _run_historical_ohlcv_upstox_raw_command(args)
        if args.command == "historical-ohlcv-upstox-raw-read":
            return _run_historical_ohlcv_upstox_raw_read_command(args)
        return _run_public_command(
            args, download_service, coverage_service, query_service
        )
    except _RequestInvalid as error:
        _render_request_invalid(error)
        return 2
    except Exception:
        sys.stderr.write("internal_error\n")
        return 2


def _run_watchlist_screen_command(
    args: argparse.Namespace, service: CurrentStockResearchPortV2 | None
) -> int:
    try:
        report = screen_watchlist_current(
            tuple(args.symbol),
            args.storage_root,
            direction=args.close_direction,
            research=research_current_stock_v2 if service is None else service,
        )
    except CurrentStockResearchInputError:
        sys.stderr.write("request_invalid\n")
        return 2
    payload = (
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    sys.stdout.buffer.write(payload)
    members = cast(list[dict[str, object]], report["members"])
    return 0 if all(row["status"] != "UNKNOWN" for row in members) else 1


def _run_agent_research_command(
    args: argparse.Namespace,
    service: CurrentStockResearchPortV2 | None,
    confirm_service: Callable[
        [str, Path, CurrentStockResearchResultV2], CurrentStockResearchResultV2
    ]
    | None,
    previous_service: Callable[
        [str, Path, CurrentStockResearchResultV2], CurrentStockResearchResultV2
    ]
    | None,
) -> int:
    try:
        context_options = (
            args.context_symbol,
            args.context_purpose,
            args.context_mappings_file,
        )
        if args.contract_version != "v4" and any(
            value is not None for value in context_options
        ):
            raise CurrentStockResearchInputError("context requires V4")
        mappings = None
        context_symbols = tuple(args.context_symbol or ())
        if args.contract_version == "v4":
            validate_agent_cohort_request(
                tuple(args.symbol),
                args.storage_root,
                context_symbols,
                args.context_purpose,
            )
            if args.context_mappings_file is not None:
                try:
                    raw = _read_current_regime_input(args.context_mappings_file)
                except (OSError, _RequestInvalid):
                    raise CurrentStockResearchInputError(
                        "invalid cohort mappings file"
                    ) from None
                mappings = parse_agent_cohort_mappings(raw, context_symbols)
        if args.contract_version in {"v2", "v3", "v4"}:
            runner = run_agent_swing_research_current
            if args.contract_version == "v3":
                runner = run_agent_event_research_current
            elif args.contract_version == "v4":
                runner = partial(
                    run_agent_cohort_research_current,
                    context_symbols=context_symbols,
                    context_purpose=args.context_purpose,
                    mappings=mappings,
                )
            report = runner(
                tuple(args.symbol),
                args.storage_root,
                research=(
                    partial(research_current_stock_v2, terminal_missing_diagnostic=True)
                    if service is None
                    else service
                ),
                confirm_research=(
                    confirm_latest_completed_stock_v2
                    if confirm_service is None
                    else confirm_service
                ),
                previous_research=(
                    research_previous_completed_stock_v2
                    if previous_service is None
                    else previous_service
                ),
            )
        else:
            report = run_agent_research_current(
                tuple(args.symbol),
                args.storage_root,
                research=research_current_stock_v2 if service is None else service,
            )
    except CurrentStockResearchInputError:
        sys.stderr.write("request_invalid\n")
        return 2
    payload = (
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    sys.stdout.buffer.write(payload)
    members = cast(list[dict[str, object]], report["members"])
    return (
        0
        if all(
            row["features"]
            and all(
                feature["fact"] is not None
                for feature in cast(
                    dict[str, dict[str, object]], row["features"]
                ).values()
            )
            for row in members
        )
        else 1
    )


def _run_research_current_command(
    args: argparse.Namespace,
    service: CurrentStockResearchPortV1 | None,
    service_v2: CurrentStockResearchPortV2 | None,
) -> int:
    try:
        if args.contract_version == "v2":
            if args.question is None:
                raise CurrentStockResearchInputError("V2 requires a research question")
            result_v2 = (
                research_current_stock_v2(
                    args.symbol,
                    args.storage_root,
                    question=args.question,
                    refresh=args.refresh,
                )
                if service_v2 is None
                else service_v2(
                    args.symbol,
                    args.storage_root,
                    question=args.question,
                    refresh=args.refresh,
                )
            )
            payload = result_v2.canonical_json_bytes()
            status = result_v2.status
        else:
            if args.question is not None:
                raise CurrentStockResearchInputError("V1 does not accept a question")
            result_v1 = (
                research_current_stock_v1(
                    args.symbol, args.storage_root, refresh=args.refresh
                )
                if service is None
                else service(args.symbol, args.storage_root, refresh=args.refresh)
            )
            payload = result_v1.canonical_json_bytes()
            status = result_v1.status
    except CurrentStockResearchInputError:
        sys.stderr.write("request_invalid\n")
        return 2
    sys.stdout.buffer.write(payload)
    return 0 if status in {"OBSERVED", "READY"} else 1


def _run_historical_ohlcv_upstox_raw_command(args: argparse.Namespace) -> int:
    try:
        storage_root = _admit_historical_storage_root(args.storage_root)
        source_root = _admit_historical_storage_root(args.source_storage_root)
        request_raw = _read_historical_local_file(
            args.request_file, 1_048_576, storage_root
        )
    except (OSError, StorageRootLeaseError, _RequestInvalid):
        sys.stderr.write("invalid historical-ohlcv-upstox-raw request\n")
        return 2
    result = complete_upstox_raw_historical_ohlcv_v1(
        request_raw, source_root.path, storage_root.path, storage_root.identity
    )
    return _render_historical_ohlcv_result(result)


def _run_historical_ohlcv_upstox_raw_read_command(args: argparse.Namespace) -> int:
    try:
        storage_root = _admit_historical_storage_root(args.storage_root)
    except (OSError, StorageRootLeaseError, _RequestInvalid):
        sys.stderr.write("invalid historical-ohlcv-upstox-raw-read request\n")
        return 2
    result = HistoricalOhlcvRevisionStoreV1(
        storage_root.path, storage_root.identity
    ).read_exact(args.revision_sha256)
    return _render_historical_ohlcv_result(result)


def _render_historical_ohlcv_result(result: HistoricalOhlcvImportResultV1) -> int:
    payload: dict[str, object] = {
        "outcome": str(result.outcome),
        "revision_sha256": result.revision_sha256,
    }
    if result.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS:
        payload["revision"] = result.revision
    exit_code = 0 if result.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS else 1
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return exit_code


def _absolute_no_follow_parts(path: object) -> tuple[str, ...]:
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or any("\x00" in part for part in path.parts)
    ):
        raise _RequestInvalid
    normalized: list[str] = []
    for part in path.parts:
        if part in {"/", "."}:
            continue
        if part == "..":
            if normalized:
                normalized.pop()
            continue
        normalized.append(part)
    if not normalized:
        raise _RequestInvalid
    return tuple(normalized)


def _admit_historical_storage_root(
    value: object,
) -> _AdmittedHistoricalStorageRootV1:
    parts = _absolute_no_follow_parts(value)
    path = Path("/", *parts)
    identity = StorageRootLease.admit_existing_private_identity(path)
    if identity is None:
        raise _RequestInvalid
    return _AdmittedHistoricalStorageRootV1(path, identity, parts)


def _read_historical_local_file(
    path: object,
    maximum: int,
    storage_root: _AdmittedHistoricalStorageRootV1,
) -> bytes:
    if maximum < 1:
        raise ValueError
    parts = _absolute_no_follow_parts(path)
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    descriptor: int | None = None
    active_exception: BaseException | None = None
    try:
        metadata = os.fstat(parent)
        parent_identities = {(metadata.st_dev, metadata.st_ino)}
        for part in parts[:-1]:
            previous_parent = parent
            parent = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent,
            )
            os.close(previous_parent)
            metadata = os.fstat(parent)
            parent_identities.add((metadata.st_dev, metadata.st_ino))
        if (
            storage_root.identity in parent_identities
            or parts[: len(storage_root.path_parts)] == storage_root.path_parts
        ):
            raise _RequestInvalid
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
            dir_fd=parent,
        )
        before = os.fstat(descriptor)
        named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size < 1
            or before.st_size > maximum
            or (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise _RequestInvalid
        raw = bytearray()
        while len(raw) <= maximum:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(descriptor)
        named_after = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        admitted = _AdmittedHistoricalLocalFileV1(
            parts, (before.st_dev, before.st_ino), bytes(raw)
        )
        if (
            len(admitted.raw) != before.st_size
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_mode != after.st_mode
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
            or admitted.identity != (named_after.st_dev, named_after.st_ino)
        ):
            raise _RequestInvalid
        return admitted.raw
    except BaseException as error:
        active_exception = error
        raise
    finally:
        _close_cli_file_descriptors((descriptor, parent), active_exception)


def _admit_regime_current_argv(argv: list[str] | None) -> bool:
    raw = sys.argv[1:] if argv is None else argv
    if not raw or raw[0] != "regime-current":
        return True
    if not all(type(value) is str for value in raw) or len(raw) != 7:
        return False
    values: dict[str, str] = {}
    for flag, value in zip(raw[1::2], raw[2::2], strict=True):
        if flag not in {"--input-file", "--storage-root", "--output"} or flag in values:
            return False
        values[flag] = value
    input_file = values.get("--input-file")
    root = values.get("--storage-root")
    if (
        input_file is None
        or root is None
        or any(
            "\x00" in value or not Path(value).is_absolute()
            for value in (input_file, root)
        )
    ):
        return False
    return values.get("--output") == "json"


def _run_public_command(
    args: argparse.Namespace,
    download_service: PublicDownloadPortV1 | None,
    coverage_service: PublicCoveragePortV1 | None,
    query_service: PublicQueryPortV1 | None,
) -> int:
    injected = {
        "download": download_service,
        "coverage": coverage_service,
        "query": query_service,
    }[args.command]
    public = injected is not None or args.symbol is not None
    admission = _command_request(args, injected is not None)
    if not admission.admitted:
        if admission.invalid_universe_source or not public:
            return _render_admission_terminal(args, False, public)
    else:
        try:
            args.storage_root = _prepare_storage_root(args.storage_root)
        except (OSError, _RequestInvalid):
            return _render_admission_terminal(args, True, public)
        admission = _command_request(args, injected is not None)
    request = admission.request
    if args.command == "download":
        return _run_download_command(
            args, download_service, request, admission.universe_source
        )
    if args.command == "coverage":
        if coverage_service is not None or args.symbol is not None:
            service = coverage_service or _default_nifty50_coverage_service()
            report = service.coverage(request)
            exit_code = public_exit_code(report.status)
            sys.stdout.write(render_coverage_report_json(report).decode("utf-8"))
            return exit_code
        batch = _default_bounded_read_service().execute(request)
        exit_code = bounded_nifty50_exit_code(batch.outcome)
        sys.stdout.write(render_bounded_nifty50_read_json(batch).decode("utf-8"))
        return exit_code
    if query_service is not None or args.symbol is not None:
        service = query_service or _default_nifty50_query_service()
        report = service.query(request)
        exit_code = public_exit_code(report.status)
        sys.stdout.write(render_query_report_json(report).decode("utf-8"))
        return exit_code
    batch = _default_bounded_read_service().execute(request)
    exit_code = bounded_nifty50_exit_code(batch.outcome)
    sys.stdout.write(render_bounded_nifty50_read_json(batch).decode("utf-8"))
    return exit_code


def _run_current_packet_command(args: argparse.Namespace, clock: _ClockV1) -> int:
    if args.command == "regime-current":
        return _run_current_regime_command(args)
    return _run_price_context_current_command(args, clock)


def _run_price_context_current_command(
    args: argparse.Namespace, clock: _ClockV1
) -> int:
    """Run the closed price-context request without exposing private paths.

    Only the descriptor-relative request-file admission is a request-invalid
    boundary.  A valid request that encounters storage, runtime, or provider
    faults must reach ``main``'s fixed #145 ``internal_error`` boundary.
    """
    request_v1 = None
    request_v2 = None
    try:
        input_file = args.input_file
        root = args.storage_root
        if (
            type(input_file) is not type(Path())
            or not input_file.is_absolute()
            or type(root) is not type(Path())
            or not root.is_absolute()
            or type(args.acquire_missing) is not bool
            or args.contract_version not in ("v1", "v2")
            or (args.contract_version == "v2" and args.acquire_missing)
        ):
            raise _RequestInvalid
        raw = _read_current_regime_input(input_file)
        if args.contract_version == "v1":
            request_v1 = current_price_context_request_from_canonical_json_bytes_v1(raw)
        else:
            request_v2 = current_price_context_request_from_canonical_json_bytes_v2(raw)
    except (OSError, ValueError, _RequestInvalid):
        raise _RequestInvalid from None
    if args.contract_version == "v1":
        if request_v1 is None:
            raise RuntimeError("V1 price-context request was not decoded")
        result_v1 = research_current_price_context_v1(
            request_v1, root, acquire_missing=args.acquire_missing, clock=clock
        )
        sys.stdout.write(result_v1.canonical_json_bytes().decode("utf-8"))
        return (
            0 if all(item.state == "OBSERVED" for item in result_v1.features[:3]) else 1
        )
    if request_v2 is None:
        raise RuntimeError("V2 price-context request was not decoded")
    result_v2 = research_current_price_context_v2(request_v2, root, clock=clock)
    sys.stdout.write(result_v2.canonical_json_bytes().decode("utf-8"))
    return (
        0
        if all(
            item.state == "OBSERVED"
            for item in result_v2.completed_context.features[:3]
        )
        else 1
    )


def _run_current_regime_command(args: argparse.Namespace) -> int:
    admitted = False
    try:
        input_file = args.input_file
        root = args.storage_root
        if (
            type(input_file) is not type(Path())
            or not input_file.is_absolute()
            or type(root) is not type(Path())
            or not root.is_absolute()
        ):
            raise _RequestInvalid
        # Runtime identity rejection remains a pre-report structural boundary.
        try:
            current_supplied_cohort_market_regime_runtime_code_identity_v1()
        except ValueError:
            raise _RequestInvalid from None
        admitted_root, identity = _admit_existing_storage_root(root)
        acquired = StorageRootLease.try_acquire_existing_identity(
            admitted_root, identity
        )
        if acquired.lease is None:
            raise _RequestInvalid
        with acquired.lease as lease:
            raw = _read_current_regime_input(input_file)
            try:
                admitted_input = (
                    CurrentSuppliedCohortMarketRegimeInputV1.from_canonical_json_bytes(
                        raw
                    )
                )
            except (RecursionError, ValueError):
                raise _RequestInvalid from None
            admitted = True
            report = evaluate_current_supplied_cohort_market_regime_v1(
                admitted_input,
                DirectCurrentCohortArchiveReaderV1(admitted_root, lease),
                DirectCurrentCohortScheduleResolverV1(admitted_root, lease),
            )
            report_bytes = report.canonical_json_bytes()
            exit_code = 0 if report.evidence_state == "OBSERVED" else 1
    except (OSError, StorageRootLeaseError, _RequestInvalid):
        if admitted:
            raise
        sys.stderr.write("invalid regime-current request\n")
        return 2
    sys.stdout.write(report_bytes.decode("utf-8"))
    return exit_code


def _run_volume_command(args: argparse.Namespace, clock: _ClockV1) -> int:
    try:
        request = volume_request_from_json(_read_current_regime_input(args.input_file))
    except ValueError:
        raise _RequestInvalid from None
    result = research_current_volume(request, args.storage_root, clock=clock.now)
    output = volume_json(result).decode("ascii")
    # Assemble and verify the complete response before the first stdout write.
    sys.stdout.write(output)
    return 0 if result["state"] == "OBSERVED" else 1


def _read_current_regime_input(path: Path) -> bytes:
    if not path.is_absolute():
        raise _RequestInvalid
    parts = path.parts[1:]
    if not parts:
        raise _RequestInvalid
    descriptor = os.open(
        "/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    file_descriptor: int | None = None
    active_exception: BaseException | None = None
    try:
        for part in parts[:-1]:
            previous_descriptor = descriptor
            descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(previous_descriptor)
        file_descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=descriptor,
        )
        before = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) & 0o077
            or before.st_size < 1
            or before.st_size > 64 * 1024
        ):
            raise _RequestInvalid
        raw = os.read(file_descriptor, 64 * 1024 + 1)
        after = os.fstat(file_descriptor)
        if len(raw) != before.st_size or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise _RequestInvalid
        return raw
    except BaseException as error:
        active_exception = error
        raise
    finally:
        _close_cli_file_descriptors((file_descriptor, descriptor), active_exception)


def _run_current_cohort_command(
    args: argparse.Namespace,
    injected: CurrentCohortServicePortV1 | None,
    trusted_clock: _ClockV1,
) -> int:
    try:
        cohort_file = args.cohort_file
        storage_root = args.storage_root
        cutoff = args.cutoff
        include_partial = args.include_partial_current_session
        if (
            type(cohort_file) is not type(Path())
            or not cohort_file.is_absolute()
            or type(storage_root) is not type(Path())
            or not storage_root.is_absolute()
            or type(cutoff) is not datetime
            or cutoff.tzinfo is None
            or cutoff.utcoffset() != timedelta(0)
            or type(include_partial) is not bool
        ):
            raise _RequestInvalid
        if cutoff > _trusted_now(trusted_clock):
            raise _RequestInvalid
        if not _valid_storage_root(storage_root):
            raise _RequestInvalid
        raw = _read_cohort_file(cohort_file)
        try:
            manifest = parse_current_cohort_manifest_bytes_v1(raw)
            request = CurrentCohortMarketDataRequestV1(
                manifest,
                cutoff,
                include_partial,
                CURRENT_COHORT_SOURCE_POLICY_IDENTITY_SHA256_V1,
                CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1,
            )
        except (RecursionError, ValueError):
            raise _RequestInvalid from None
        service = injected
        expected_root_identity: tuple[int, int] | None = None
        if service is None:
            storage_root, expected_root_identity = _admit_existing_storage_root(
                storage_root
            )
        else:
            storage_root = _prepare_storage_root(storage_root)
    except (OSError, StorageRootLeaseError, _RequestInvalid):
        sys.stderr.write("invalid cohort-current request\n")
        return 2
    if service is None:
        policy = CurrentSuppliedCohortAdmissionPolicyV1(manifest.members)
        query_clock = _FixedClock(cutoff)
        service = CurrentCohortMarketDataServiceV1(
            policy=policy,
            universe_resolver=RetainedCurrentNifty50UniverseResolverV1(storage_root),
            resolver=RetainedCurrentCohortInstrumentResolverV1(storage_root, cutoff),
            query_port=CurrentCohortRetainedQueryPortV1(
                _default_query_service(policy, clock=query_clock),
                OpenMonthOneMinuteQueryServiceV1(
                    policy, clock=query_clock, allow_prior_month=True
                ),
            ),
            query_factory=CurrentCohortQueryRequestFactoryV1(storage_root),
            storage_root=storage_root,
            archive_port=ImmutableCurrentFactArchiveV1(storage_root),
            expected_root_identity=expected_root_identity,
        )
    report = service.evaluate(request)
    rendered = report.canonical_json_bytes().decode("utf-8")
    exit_code = 0 if report.evidence_state is CurrentEvidenceStateV1.COMPLETE else 1
    sys.stdout.write(rendered)
    return exit_code


def _read_cohort_file(path: Path) -> bytes:
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
    )
    active_exception: BaseException | None = None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size < 1
            or metadata.st_size > MAX_COHORT_FILE_BYTES_V1
        ):
            raise _RequestInvalid
        raw = os.read(descriptor, MAX_COHORT_FILE_BYTES_V1 + 1)
        if len(raw) != metadata.st_size:
            raise _RequestInvalid
        return raw
    except BaseException as error:
        active_exception = error
        raise
    finally:
        _close_cli_file_descriptors((descriptor,), active_exception)


def _close_cli_file_descriptors(
    descriptors: tuple[int | None, ...], active_exception: BaseException | None
) -> None:
    pending = active_exception
    for descriptor in descriptors:
        if descriptor is None:
            continue
        try:
            os.close(descriptor)
        except BaseException as error:  # noqa: BLE001 - finish cleanup before propagation
            if pending is None:
                pending = error
    if active_exception is None and pending is not None:
        raise pending


def _command_request(args: argparse.Namespace, injected: bool) -> _CommandAdmissionV1:
    source, source_valid = _command_universe_source(args, injected)
    if not source_valid:
        return _CommandAdmissionV1(object(), None, False, True)
    try:
        public = injected or args.symbol is not None
        request, request_admitted = _build_command_request(args, injected, public)
    except (AttributeError, ValueError):
        return _CommandAdmissionV1(object(), source, False)
    if args.segment != "NSE_EQ" and not injected:
        return _CommandAdmissionV1(object(), source, False)
    admitted = (
        request_admitted
        and args.segment == "NSE_EQ"
        and _valid_storage_root(args.storage_root)
    )
    return _CommandAdmissionV1(request, source, admitted)


def _command_universe_source(
    args: argparse.Namespace, injected: bool
) -> tuple[CanonicalFileNifty50UniverseSourceV1 | None, bool]:
    if args.command != "download" or injected or args.universe_file is None:
        return None, True
    try:
        return CanonicalFileNifty50UniverseSourceV1(args.universe_file), True
    except ValueError:
        return None, False


def _build_command_request(
    args: argparse.Namespace, injected: bool, public: bool
) -> tuple[object, bool]:
    if args.command == "download":
        return _download_command_request(args, injected), True
    if args.command == "coverage":
        prototype = CoverageRequestV1(
            args.segment,
            args.symbol or (args.symbols or ("NIFTY50",))[0],
            args.from_date,
            args.to_date,
            args.storage_root,
        )
        request: object = (
            prototype
            if public
            else BoundedNifty50ReadRequestV1(args.symbols, prototype, args.workers)
        )
        return request, True
    prototype = QueryRequestV1(
        args.segment,
        args.symbol or (args.symbols or ("NIFTY50",))[0],
        args.from_date,
        args.to_date,
        args.timeframe,
        tuple(args.fields.split(",")),
        args.max_rows,
        args.storage_root,
    )
    request = (
        prototype
        if public
        else BoundedNifty50ReadRequestV1(args.symbols, prototype, args.workers)
    )
    daily_rows_valid = not (
        prototype.timeframe == "1d" and prototype.max_rows > MAX_DAILY_QUERY_ROWS_V1
    )
    public_request_valid = not public or _valid_public_query_request(prototype)
    return request, daily_rows_valid and public_request_valid


def _download_command_request(args: argparse.Namespace, injected: bool) -> object:
    if injected:
        symbol = args.symbol
        if type(symbol) is not str:
            raise ValueError
        return SingleSymbolDownloadRequestV1(
            args.segment,
            symbol,
            args.from_date,
            args.to_date,
            args.storage_root,
        )
    request = BoundedNifty50DownloadRequestV1(
        symbols=(args.symbol,) if args.symbol is not None else args.symbols,
        universe_as_of=args.universe_as_of or args.to_date,
        knowledge_cutoff=_SystemClock().now(),
        from_date=args.from_date,
        to_date=args.to_date,
        storage_root=args.storage_root,
        workers=args.workers,
    )
    touched = (
        (args.to_date.year - args.from_date.year) * 12
        + args.to_date.month
        - args.from_date.month
        + 1
    )
    if touched > 12:
        raise ValueError
    return request


def _valid_public_query_request(prototype: QueryRequestV1) -> bool:
    try:
        PublicQueryRequestV1(
            prototype.segment,
            prototype.symbol,
            prototype.from_date,
            prototype.to_date,
            prototype.timeframe,  # type: ignore[arg-type]
            tuple(CandleFieldV1(value) for value in prototype.fields),
            prototype.max_rows,
        )
    except ValueError:
        return False
    return True


def _render_admission_terminal(
    args: argparse.Namespace, unavailable: bool, public: bool
) -> int:
    outcome = (
        Nifty50BatchOutcomeV1.UNAVAILABLE
        if unavailable
        else Nifty50BatchOutcomeV1.REJECTED
    )
    if not public:
        if args.command == "download":
            batch = BoundedNifty50DownloadReportV1(outcome, None, (), 0, 0)
            rendered = render_bounded_nifty50_download_json(batch)
        else:
            batch = bounded_nifty50_read_terminal(args.command, outcome)
            rendered = render_bounded_nifty50_read_json(batch)
        exit_code = bounded_nifty50_exit_code(outcome)
        sys.stdout.write(rendered.decode("utf-8"))
        return exit_code
    command: Literal["download", "coverage", "query"] = args.command
    code = (
        PublicFailureCodeV1.INGESTION_UNAVAILABLE
        if unavailable and command == "download"
        else PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE
        if unavailable
        else PublicFailureCodeV1.INVALID_INPUT
    )
    status = (
        PublicCommandStatusV1.UNAVAILABLE
        if unavailable
        else PublicCommandStatusV1.REJECTED
    )
    report: PublicCommandReportV1[Any] = PublicCommandReportV1(
        "v1",
        command,
        status,
        PublicFailureV1(code, None, None, None, None, ()),
        0,
        None,
    )
    if command == "download":
        rendered = render_download_report_json(report)
    elif command == "coverage":
        rendered = render_coverage_report_json(report)
    else:
        rendered = render_query_report_json(report)
    exit_code = public_exit_code(status)
    sys.stdout.write(rendered.decode("utf-8"))
    return exit_code


def _valid_storage_root(value: object) -> bool:
    return (
        type(value) is type(Path())
        and value.is_absolute()
        and ".." not in value.parts
        and not any(marker in part for part in value.parts for marker in "~*?[]")
    )


def _default_download_service(
    schedule_file: Path | None = None,
    closed_schedule_file: Path | None = None,
    *,
    policy: EquityAdmissionPolicyV1 | None = None,
    limiter: AccountRateLimiter | None = None,
    publication_gate: PublicationGateV1 | None = None,
) -> CurrentAwareSingleSymbolDownloadServiceV1:
    clock = _SystemClock()
    admission = policy or PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE")
    catalog_transport = UrllibHttpTransport(
        max_body_bytes=DEFAULT_MAX_CATALOG_COMPRESSED_BYTES
    )
    provider_transport = UrllibHttpTransport(
        max_body_bytes=DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES
    )
    historical = UpstoxV3HistoricalClient(provider_transport)
    token_provider = _LazyEnvironmentAccessTokenProvider()
    open_preparation = DownloadPreparationServiceV1(
        admission,
        (
            _UnavailableAuthoritativeScheduleSource()
            if schedule_file is None
            else CanonicalFileScheduleSourceV1(schedule_file)
        ),
        InstrumentSnapshotClientV1(catalog_transport, clock=clock.now),
        clock=clock,
        publication_gate=publication_gate,
        limiter=limiter,
    )
    closed_path = closed_schedule_file or schedule_file
    closed_preparation = DownloadPreparationServiceV1(
        admission,
        (
            _UnavailableAuthoritativeScheduleSource()
            if closed_path is None
            else CanonicalFileScheduleSourceV1(closed_path)
        ),
        InstrumentSnapshotClientV1(catalog_transport, clock=clock.now),
        clock=clock,
        publication_gate=publication_gate,
        limiter=limiter,
    )
    closed = SingleSymbolDownloadServiceV1(
        closed_preparation,
        IngestionCoordinator(
            session_factory=_HistoricalProviderSessionFactory(
                historical, token_provider
            ),
            limiter=limiter,
            publication_gate=publication_gate,
        ),
        clock=clock,
    )
    open_month = OpenMonthDownloadServiceV1(
        open_preparation,
        historical,
        UpstoxV3IntradayClient(provider_transport),
        token_provider,
        clock=clock,
        limiter=limiter,
        publication_gate=publication_gate,
    )
    return CurrentAwareSingleSymbolDownloadServiceV1(closed, open_month, clock=clock)


def _run_download_command(
    args: argparse.Namespace,
    download_service: PublicDownloadPortV1 | None,
    request: object,
    universe_source: CanonicalFileNifty50UniverseSourceV1 | None,
) -> int:
    if download_service is not None:
        report = download_service.download(request)
        exit_code = public_exit_code(report.status)
        sys.stdout.write(render_download_report_json(report).decode("utf-8"))
        return exit_code
    service = _default_bounded_download_service(
        universe_source, args.schedule_file, args.closed_schedule_file
    )
    if args.symbol is not None:
        report = service.download_single(request)
        exit_code = public_exit_code(report.status)
        sys.stdout.write(render_download_report_json(report).decode("utf-8"))
        return exit_code
    batch_report = service.download(request)
    exit_code = bounded_nifty50_exit_code(batch_report.outcome)
    sys.stdout.write(render_bounded_nifty50_download_json(batch_report).decode("utf-8"))
    return exit_code


def _default_bounded_download_service(
    universe_source: CanonicalFileNifty50UniverseSourceV1 | None,
    schedule_file: Path | None,
    closed_schedule_file: Path | None,
) -> BoundedNifty50DownloadServiceV1:
    publication_gate = threading.RLock()
    limiter = ThreadSafeAccountRateLimiterV1()
    return BoundedNifty50DownloadServiceV1(
        universe_source,
        lambda policy: _default_download_service(
            schedule_file,
            closed_schedule_file,
            policy=policy,
            limiter=limiter,
            publication_gate=publication_gate,
        ),
        clock=_SystemClock(),
    )


def _default_probe_range(today: date) -> tuple[date, date]:
    probe_to = today - timedelta(days=1)
    month_start = date(probe_to.year, probe_to.month, 1)
    return max(month_start, probe_to - timedelta(days=3)), probe_to


def _default_coverage_service(
    policy: EquityAdmissionPolicyV1 | None = None,
) -> CurrentAwareCoverageServiceV1:
    admission = policy or PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE")
    clock = _SystemClock()
    closed = StoredCoverageServiceV1(
        admission,
        StoredCoverageEvaluatorV1(),
        clock=clock,
    )
    return CurrentAwareCoverageServiceV1(
        closed,
        OpenMonthCoverageServiceV1(admission, clock=clock),
        clock=clock,
    )


def _default_query_service(
    policy: EquityAdmissionPolicyV1 | None = None,
    *,
    clock: _ClockV1 | None = None,
) -> CurrentAwareQueryServiceV1:
    admission = policy or PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE")
    evaluator = StoredCoverageEvaluatorV1()
    query_clock = clock or _SystemClock()
    retained_schedule = RetainedDailyScheduleResolverV1()
    open_minute = OpenMonthOneMinuteQueryServiceV1(admission, clock=query_clock)
    closed = TimeframeQueryServiceV1(
        OneMinuteQueryServiceV1(
            admission,
            evaluator,
            engine=DuckDBOneMinuteQueryEngineV1(),
            clock=query_clock,
        ),
        DailyQueryServiceV1(
            admission,
            evaluator,
            resolver=retained_schedule,
            engine=DuckDBDailyOHLCVEngineV1(),
            clock=query_clock,
        ),
        intraday_service=DerivedIntradayQueryServiceV1(
            admission,
            evaluator,
            resolver=retained_schedule,
            engine=DuckDBIntradayViewEngineV1(),
            clock=query_clock,
        ),
    )
    return CurrentAwareQueryServiceV1(
        closed,
        open_minute,
        open_intraday_service=OpenMonthDerivedIntradayQueryServiceV1(
            open_minute,
            RetainedOpenMonthScheduleResolverV1(),
            clock=query_clock,
        ),
        clock=query_clock,
    )


def _default_nifty50_coverage_service() -> PointInTimeNifty50CoverageServiceV1:
    return PointInTimeNifty50CoverageServiceV1(
        _default_coverage_service, clock=_SystemClock()
    )


def _default_nifty50_query_service() -> PointInTimeNifty50QueryServiceV1:
    return PointInTimeNifty50QueryServiceV1(
        _default_query_service, clock=_SystemClock()
    )


def _default_bounded_read_service() -> BoundedPointInTimeNifty50ReadServiceV1:
    return BoundedPointInTimeNifty50ReadServiceV1(
        _default_coverage_service,
        _default_query_service,
        clock=_SystemClock(),
    )


def _add_read_selection(command: argparse.ArgumentParser) -> None:
    selection = command.add_mutually_exclusive_group(required=True)
    selection.add_argument("--symbol", help="one Nifty 50 trading symbol")
    selection.add_argument(
        "--symbols", type=_symbols, help="comma-separated Nifty 50 trading symbols"
    )
    selection.add_argument(
        "--universe",
        choices=("nifty50-current",),
        help="all members of the retained point-in-time Nifty 50 snapshot",
    )
    command.add_argument(
        "--workers",
        type=int,
        choices=range(1, 9),
        default=4,
        metavar="1..8",
        help="bounded concurrent read workers (default: 4)",
    )


def _add_persistent_range_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--segment", required=True)
    command.add_argument(
        "--from", dest="from_date", type=_date, required=True, metavar="YYYY-MM-DD"
    )
    command.add_argument(
        "--to", dest="to_date", type=_date, required=True, metavar="YYYY-MM-DD"
    )
    command.add_argument(
        "--storage-root",
        type=Path,
        default=_default_storage_root(),
        metavar="ABSOLUTE_PATH",
        help=(
            "persistent data directory (default: ~/SwingTradingAIAssistantData; "
            "created recursively when missing)"
        ),
    )
    command.add_argument("--output", choices=("json",), required=True)


def _default_storage_root() -> Path:
    return Path.home() / _DEFAULT_STORAGE_DIRECTORY


def _prepare_storage_root(value: object) -> Path:
    """Create and validate an owner-private canonical CLI storage root."""
    if type(value) is not type(Path()) or not _valid_storage_root(value):
        return Path()
    if value.is_symlink():
        raise _RequestInvalid
    canonical = value.resolve(strict=False)
    canonical.mkdir(mode=0o700, parents=True, exist_ok=True)
    canonical = canonical.resolve(strict=True)
    metadata = canonical.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise _RequestInvalid
    return canonical


def _admit_existing_storage_root(value: object) -> tuple[Path, tuple[int, int]]:
    """Admit one pre-existing link-free root for identity-pinned cohort reads."""
    if type(value) is not type(Path()) or not _valid_storage_root(value):
        raise _RequestInvalid
    identity = StorageRootLease.admit_existing_private_identity(value)
    if identity is None:
        raise _RequestInvalid
    return value, identity


def _symbols(value: str) -> tuple[str, ...]:
    symbols = tuple(value.split(","))
    if (
        not symbols
        or len(symbols) > 50
        or len(set(symbols)) != len(symbols)
        or any(
            not symbol or re.fullmatch(r"[A-Z0-9][A-Z0-9.&_-]{0,31}", symbol) is None
            for symbol in symbols
        )
    ):
        raise argparse.ArgumentTypeError(
            "expected 1 to 50 unique comma-separated symbols"
        )
    return symbols


def _run_probe(args: argparse.Namespace) -> int:
    try:
        request = ProbeRequest(
            segment=args.segment,
            symbol=args.symbol,
            from_date=args.from_date,
            to_date=args.to_date,
        )
    except ValueError:
        raise _RequestInvalid from None
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
            request,
            token_provider=EnvironmentAccessTokenProvider(),
            catalog_client=InstrumentCatalogClient(catalog_transport),
            historical_client=UpstoxV3HistoricalClient(historical_transport),
        )
    except (
        CredentialNotFoundError,
        InstrumentNotFoundError,
        AmbiguousInstrumentError,
        InstrumentCatalogRequestError,
        InstrumentCatalogPayloadError,
        CatalogPayloadTooLargeError,
        HistoricalPayloadError,
        HttpTransportError,
        HttpResponseBodyTooLarge,
        HttpResponseHeadersInvalid,
    ):
        sys.stderr.write("probe_failed\n")
        return 2
    rendered = report.to_json()
    exit_code = 0 if report.status == 200 and report.schema_valid else 1
    print(rendered)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
