"""Command-line adapter for market-data diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

from dotenv import load_dotenv

from swing_trading_ai_assistant.market_regime.current_supplied_cohort import (
    CurrentSuppliedCohortMarketRegimeInputV1,
    DirectCurrentCohortArchiveReaderV1,
    DirectCurrentCohortScheduleResolverV1,
    current_supplied_cohort_market_regime_runtime_code_identity_v1,
    evaluate_current_supplied_cohort_market_regime_v1,
)

from .account_rate_limit import ThreadSafeAccountRateLimiterV1
from .bounded_nifty50_workflow import (
    BoundedNifty50DownloadReportV1,
    BoundedNifty50DownloadRequestV1,
    BoundedNifty50DownloadServiceV1,
    CanonicalFileNifty50UniverseSourceV1,
    Nifty50BatchOutcomeV1,
    bounded_nifty50_exit_code,
    render_bounded_nifty50_download_json,
)
from .credentials import AccessToken, EnvironmentAccessTokenProvider
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
    HistoricalRequest,
    HistoricalResponse,
    UpstoxV3HistoricalClient,
)
from .historical_revision_store import (
    HistoricalOhlcvImportOutcomeV1,
    HistoricalOhlcvImportResultV1,
    HistoricalOhlcvRevisionStoreV1,
)
from .http import DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES, UrllibHttpTransport
from .instrument_snapshot import InstrumentSnapshotClientV1
from .instruments import DEFAULT_MAX_CATALOG_COMPRESSED_BYTES, InstrumentCatalogClient
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
from .storage_root_lease import StorageRootLease
from .workflow_coordination import PublicationGateV1

_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_DEFAULT_STORAGE_DIRECTORY = "SwingTradingAIAssistantData"


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
        raise RuntimeError("authoritative schedule source is not configured")


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
        except Exception:
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
    parser = argparse.ArgumentParser(
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
    historical_import = commands.add_parser(
        "historical-ohlcv-import",
        help="store one strict operator-local historical daily OHLCV revision",
    )
    historical_import.add_argument(
        "--request-file", type=Path, required=True, metavar="ABSOLUTE_JSON_FILE"
    )
    historical_import.add_argument(
        "--source-policy-file",
        type=Path,
        required=True,
        metavar="ABSOLUTE_JSON_FILE",
    )
    historical_import.add_argument(
        "--source-artifact-file",
        type=Path,
        required=True,
        metavar="ABSOLUTE_ARTIFACT_FILE",
    )
    historical_import.add_argument(
        "--receipt-file", type=Path, required=True, metavar="ABSOLUTE_JSON_FILE"
    )
    historical_import.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        metavar="ABSOLUTE_OWNER_PRIVATE_ROOT",
    )
    historical_import.add_argument("--output", choices=("json",), required=True)
    historical_read = commands.add_parser(
        "historical-ohlcv-read",
        help="read one exact immutable historical daily OHLCV revision",
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


def main(
    argv: list[str] | None = None,
    *,
    download_service: PublicDownloadPortV1 | None = None,
    coverage_service: PublicCoveragePortV1 | None = None,
    query_service: PublicQueryPortV1 | None = None,
    current_cohort_service: CurrentCohortServicePortV1 | None = None,
    trusted_clock: _ClockV1 | None = None,
) -> int:
    if not _admit_regime_current_argv(argv):
        sys.stderr.write("invalid regime-current request\n")
        return 2
    args = build_parser().parse_args(argv)
    if args.command == "probe-upstox":
        return _run_probe(args)
    if args.command == "cohort-current":
        return _run_current_cohort_command(
            args, current_cohort_service, trusted_clock or _SystemClock()
        )
    if args.command == "regime-current":
        return _run_current_regime_command(args)
    if args.command == "historical-ohlcv-import":
        return _run_historical_ohlcv_import_command(args)
    if args.command == "historical-ohlcv-read":
        return _run_historical_ohlcv_read_command(args)
    return _run_public_command(args, download_service, coverage_service, query_service)


def _run_historical_ohlcv_import_command(args: argparse.Namespace) -> int:
    try:
        storage_root = _admit_historical_storage_root(args.storage_root)
        result = HistoricalOhlcvRevisionStoreV1(
            storage_root.path, storage_root.identity
        ).import_exact(
            _read_historical_local_file(args.request_file, 1_048_576, storage_root),
            _read_historical_local_file(
                args.source_policy_file, 1_048_576, storage_root
            ),
            _read_historical_local_file(
                args.source_artifact_file, 134_217_728, storage_root
            ),
            _read_historical_local_file(args.receipt_file, 1_048_576, storage_root),
        )
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        sys.stderr.write("invalid historical-ohlcv-import request\n")
        return 2
    return _render_historical_ohlcv_result(result)


def _run_historical_ohlcv_read_command(args: argparse.Namespace) -> int:
    try:
        storage_root = _admit_historical_storage_root(args.storage_root)
        result = HistoricalOhlcvRevisionStoreV1(
            storage_root.path, storage_root.identity
        ).read_exact(args.revision_sha256)
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        sys.stderr.write("invalid historical-ohlcv-read request\n")
        return 2
    return _render_historical_ohlcv_result(result)


def _render_historical_ohlcv_result(result: HistoricalOhlcvImportResultV1) -> int:
    payload: dict[str, object] = {
        "outcome": str(result.outcome),
        "revision_sha256": result.revision_sha256,
    }
    if result.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS:
        payload["revision"] = result.revision
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0 if result.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS else 1


def _absolute_no_follow_parts(path: object) -> tuple[str, ...]:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError
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
        raise ValueError
    return tuple(normalized)


def _admit_historical_storage_root(
    value: object,
) -> _AdmittedHistoricalStorageRootV1:
    parts = _absolute_no_follow_parts(value)
    path = Path("/", *parts)
    identity = StorageRootLease.admit_existing_private_identity(path)
    if identity is None:
        raise ValueError
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
    parent_identities = {(os.fstat(parent).st_dev, os.fstat(parent).st_ino)}
    descriptor: int | None = None
    try:
        for part in parts[:-1]:
            next_parent = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent,
            )
            os.close(parent)
            parent = next_parent
            metadata = os.fstat(parent)
            parent_identities.add((metadata.st_dev, metadata.st_ino))
        if (
            storage_root.identity in parent_identities
            or parts[: len(storage_root.path_parts)] == storage_root.path_parts
        ):
            raise ValueError
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
            raise ValueError
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
            raise ValueError
        return admitted.raw
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


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
        except (OSError, ValueError):
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
            sys.stdout.write(render_coverage_report_json(report).decode("utf-8"))
            return public_exit_code(report.status)
        batch = _default_bounded_read_service().execute(request)
        sys.stdout.write(render_bounded_nifty50_read_json(batch).decode("utf-8"))
        return bounded_nifty50_exit_code(batch.outcome)
    if query_service is not None or args.symbol is not None:
        service = query_service or _default_nifty50_query_service()
        report = service.query(request)
        sys.stdout.write(render_query_report_json(report).decode("utf-8"))
        return public_exit_code(report.status)
    batch = _default_bounded_read_service().execute(request)
    sys.stdout.write(render_bounded_nifty50_read_json(batch).decode("utf-8"))
    return bounded_nifty50_exit_code(batch.outcome)


def _run_current_regime_command(args: argparse.Namespace) -> int:
    lease: StorageRootLease | None = None
    report_bytes: bytes | None = None
    exit_code = 2
    failed = False
    try:
        input_file = args.input_file
        root = args.storage_root
        if (
            type(input_file) is not type(Path())
            or not input_file.is_absolute()
            or type(root) is not type(Path())
            or not root.is_absolute()
        ):
            raise ValueError
        # Runtime source verification is a pre-report structural boundary.
        current_supplied_cohort_market_regime_runtime_code_identity_v1()
        admitted_root, identity = _admit_existing_storage_root(root)
        acquired = StorageRootLease.try_acquire_existing_identity(
            admitted_root, identity
        )
        if acquired.lease is None:
            raise ValueError
        lease = acquired.lease
        admitted_input = (
            CurrentSuppliedCohortMarketRegimeInputV1.from_canonical_json_bytes(
                _read_current_regime_input(input_file)
            )
        )
        report = evaluate_current_supplied_cohort_market_regime_v1(
            admitted_input,
            DirectCurrentCohortArchiveReaderV1(admitted_root, lease),
            DirectCurrentCohortScheduleResolverV1(admitted_root, lease),
        )
        report_bytes = report.canonical_json_bytes()
        exit_code = 0 if report.evidence_state == "OBSERVED" else 1
    except (OSError, RuntimeError, UnicodeError, ValueError):
        failed = True
    finally:
        if lease is not None:
            try:
                lease.close()
            except RuntimeError:
                failed = True
    if failed or report_bytes is None:
        sys.stderr.write("invalid regime-current request\n")
        return 2
    sys.stdout.write(report_bytes.decode("utf-8"))
    return exit_code


def _read_current_regime_input(path: Path) -> bytes:
    if not path.is_absolute():
        raise ValueError
    parts = path.parts[1:]
    if not parts:
        raise ValueError
    descriptor = os.open(
        "/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    try:
        for part in parts[:-1]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        file_descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=descriptor,
        )
        try:
            before = os.fstat(file_descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) & 0o077
                or before.st_size < 1
                or before.st_size > 16 * 1024
            ):
                raise ValueError
            raw = os.read(file_descriptor, 16 * 1024 + 1)
            after = os.fstat(file_descriptor)
            if len(raw) != before.st_size or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError
            return raw
        finally:
            os.close(file_descriptor)
    finally:
        os.close(descriptor)


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
            raise ValueError
        if cutoff > _trusted_now(trusted_clock):
            raise ValueError
        if not _valid_storage_root(storage_root):
            raise ValueError
        manifest = parse_current_cohort_manifest_bytes_v1(
            _read_cohort_file(cohort_file)
        )
        request = CurrentCohortMarketDataRequestV1(
            manifest,
            cutoff,
            include_partial,
            CURRENT_COHORT_SOURCE_POLICY_IDENTITY_SHA256_V1,
            CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1,
        )
        service = injected
        expected_root_identity: tuple[int, int] | None = None
        if service is None:
            storage_root, expected_root_identity = _admit_existing_storage_root(
                storage_root
            )
        else:
            storage_root = _prepare_storage_root(storage_root)
        if service is None:
            policy = CurrentSuppliedCohortAdmissionPolicyV1(manifest.members)
            query_clock = _FixedClock(cutoff)
            service = CurrentCohortMarketDataServiceV1(
                policy=policy,
                universe_resolver=RetainedCurrentNifty50UniverseResolverV1(
                    storage_root
                ),
                resolver=RetainedCurrentCohortInstrumentResolverV1(
                    storage_root, cutoff
                ),
                query_port=CurrentCohortRetainedQueryPortV1(
                    _default_query_service(policy, clock=query_clock),
                    OpenMonthOneMinuteQueryServiceV1(
                        policy,
                        clock=query_clock,
                        allow_prior_month=True,
                    ),
                ),
                query_factory=CurrentCohortQueryRequestFactoryV1(storage_root),
                storage_root=storage_root,
                archive_port=ImmutableCurrentFactArchiveV1(storage_root),
                expected_root_identity=expected_root_identity,
            )
        report = service.evaluate(request)
        sys.stdout.write(report.canonical_json_bytes().decode("utf-8"))
        return 0 if report.evidence_state is CurrentEvidenceStateV1.COMPLETE else 1
    except (AttributeError, OSError, RecursionError, TypeError, ValueError):
        sys.stderr.write("invalid cohort-current request\n")
        return 2


def _read_cohort_file(path: Path) -> bytes:
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
    )
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size < 1
            or metadata.st_size > MAX_COHORT_FILE_BYTES_V1
        ):
            raise ValueError
        raw = os.read(descriptor, MAX_COHORT_FILE_BYTES_V1 + 1)
        if len(raw) != metadata.st_size:
            raise ValueError
        return raw
    finally:
        os.close(descriptor)


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
        sys.stdout.write(rendered.decode("utf-8"))
        return bounded_nifty50_exit_code(outcome)
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
    sys.stdout.write(rendered.decode("utf-8"))
    return public_exit_code(status)


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
        sys.stdout.write(render_download_report_json(report).decode("utf-8"))
        return public_exit_code(report.status)
    service = _default_bounded_download_service(
        universe_source, args.schedule_file, args.closed_schedule_file
    )
    if args.symbol is not None:
        report = service.download_single(request)
        sys.stdout.write(render_download_report_json(report).decode("utf-8"))
        return public_exit_code(report.status)
    batch_report = service.download(request)
    sys.stdout.write(render_bounded_nifty50_download_json(batch_report).decode("utf-8"))
    return bounded_nifty50_exit_code(batch_report.outcome)


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
        raise ValueError("invalid storage root")
    canonical = value.resolve(strict=False)
    canonical.mkdir(mode=0o700, parents=True, exist_ok=True)
    canonical = canonical.resolve(strict=True)
    metadata = canonical.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ValueError("invalid storage root")
    return canonical


def _admit_existing_storage_root(value: object) -> tuple[Path, tuple[int, int]]:
    """Admit one pre-existing link-free root for identity-pinned cohort reads."""
    if type(value) is not type(Path()) or not _valid_storage_root(value):
        raise ValueError("invalid storage root")
    identity = StorageRootLease.admit_existing_private_identity(value)
    if identity is None:
        raise ValueError("invalid storage root")
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
