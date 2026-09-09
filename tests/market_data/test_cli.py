from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import date
from pathlib import Path
from typing import Never

import pytest

from swing_trading_ai_assistant.market_data import cli, historical
from swing_trading_ai_assistant.market_data.bounded_nifty50_workflow import (
    BoundedNifty50DownloadReportV1,
    Nifty50BatchOutcomeV1,
)
from swing_trading_ai_assistant.market_data.credentials import AccessToken
from swing_trading_ai_assistant.market_data.http import (
    DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES,
    HttpResponse,
)
from swing_trading_ai_assistant.market_data.instruments import (
    DEFAULT_MAX_CATALOG_COMPRESSED_BYTES,
)
from swing_trading_ai_assistant.market_data.probe import ProbeReport
from swing_trading_ai_assistant.market_data.public_contract import (
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicFailureCodeV1,
    PublicFailureV1,
)


def _persistent_command(command: str, storage_root: Path | None = None) -> list[str]:
    values = [
        command,
        "--segment",
        "NSE_EQ",
        "--symbol",
        "RELIANCE",
        "--from",
        "2026-07-01",
        "--to",
        "2026-07-31",
    ]
    if command == "query":
        values.extend(
            [
                "--timeframe",
                "1d",
                "--fields",
                "ts,open,high,low,close,volume",
                "--max-rows",
                "31",
            ]
        )
    if storage_root is not None:
        values.extend(["--storage-root", str(storage_root)])
    return values + ["--output", "json"]


@pytest.mark.parametrize(
    ("today", "expected"),
    (
        (date(2026, 8, 1), (date(2026, 7, 28), date(2026, 7, 31))),
        (date(2026, 8, 3), (date(2026, 8, 1), date(2026, 8, 2))),
        (date(2026, 8, 10), (date(2026, 8, 6), date(2026, 8, 9))),
    ),
)
def test_probe_default_range_never_crosses_a_calendar_month(
    today: date, expected: tuple[date, date]
) -> None:
    assert cli._default_probe_range(today) == expected


def test_symbol_list_parser_accepts_real_ampersand_alias_and_preserves_dot() -> None:
    assert cli._symbols("M&M,BAJAJ-AUTO,ABC.DEF") == (
        "M&M",
        "BAJAJ-AUTO",
        "ABC.DEF",
    )


@pytest.mark.parametrize("value", ("&M", "M/M", "M M", "m&m", "M&M,"))
def test_symbol_list_parser_rejects_unsafe_widening(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        cli._symbols(value)


def test_download_accepts_an_explicit_authoritative_schedule_file(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    schedule_file = tmp_path / "nse-schedule.json"
    args = cli.build_parser().parse_args(
        [
            "download",
            "--segment",
            "NSE_EQ",
            "--symbol",
            "RELIANCE",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-31",
            "--storage-root",
            str(storage_root),
            "--schedule-file",
            str(schedule_file),
            "--output",
            "json",
        ]
    )

    assert args.schedule_file == schedule_file


@pytest.mark.parametrize(
    "command",
    (
        _persistent_command("download"),
        _persistent_command("coverage"),
        _persistent_command("query"),
    ),
)
def test_persistent_commands_default_to_the_user_data_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, command: list[str]
) -> None:
    expected = tmp_path / "SwingTradingAIAssistantData"
    monkeypatch.setattr(cli, "_default_storage_root", lambda: expected, raising=False)

    args = cli.build_parser().parse_args(command)

    assert args.storage_root == expected


def test_default_storage_root_is_under_the_user_home() -> None:
    assert cli._default_storage_root() == Path.home() / "SwingTradingAIAssistantData"


@pytest.mark.parametrize("explicit", (False, True))
def test_cli_recursively_creates_default_and_explicit_storage_roots_before_use(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys, explicit: bool
) -> None:
    expected = tmp_path / "missing" / "nested" / "market-data"
    if not explicit:
        monkeypatch.setattr(cli, "_default_storage_root", lambda: expected)
    report = PublicCommandReportV1(
        "v1",
        "download",
        PublicCommandStatusV1.REJECTED,
        PublicFailureV1(PublicFailureCodeV1.INVALID_INPUT, None, None, None, None, ()),
        0,
        None,
    )

    class Service:
        def download(self, request: object) -> PublicCommandReportV1:
            assert request.storage_root == expected  # type: ignore[attr-defined]
            assert expected.is_dir()
            return report

    assert (
        cli.main(
            _persistent_command("download", expected if explicit else None),
            download_service=Service(),
        )
        == 2
    )
    assert '"status":"REJECTED"' in capsys.readouterr().out


def test_cli_accepts_official_ampersand_symbol_selection() -> None:
    assert cli._symbols("M&M,RELIANCE") == ("M&M", "RELIANCE")


def test_storage_root_creation_fails_closed_for_unsafe_or_blocked_paths(
    tmp_path: Path,
) -> None:
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")

    assert not cli._prepare_storage_root(Path("relative")).is_absolute()
    assert not cli._prepare_storage_root(tmp_path / "data*").is_absolute()
    with pytest.raises(OSError):
        cli._prepare_storage_root(blocked / "child")


@pytest.mark.parametrize("value", ("20260701", "2026-W27-3"))
def test_cli_rejects_noncanonical_iso_date_forms(value: str) -> None:
    with pytest.raises(SystemExit, match="2"):
        cli.build_parser().parse_args(
            [
                "probe-upstox",
                "--segment",
                "NSE_EQ",
                "--symbol",
                "RELIANCE",
                "--from",
                value,
            ]
        )


def test_probe_help_distinguishes_the_diagnostic_from_the_downloader(capsys) -> None:
    with pytest.raises(SystemExit, match="0"):
        cli.build_parser().parse_args(["probe-upstox", "--help"])

    help_text = capsys.readouterr().out
    assert "does not run the persistent downloader or write market data" in help_text
    assert "actual date, for example 2026-08-03" in help_text


def test_cli_prints_approved_report_and_returns_success(monkeypatch, capsys) -> None:
    dotenv_calls: list[bool] = []

    def run_probe(*args: object, **kwargs: object) -> ProbeReport:
        return ProbeReport(
            200, 1, "2026-07-31T09:15:00+05:30", "2026-07-31T09:15:00+05:30", True
        )

    monkeypatch.setattr(cli, "load_dotenv", lambda: dotenv_calls.append(True))
    monkeypatch.setattr(cli, "run_capability_probe", run_probe)

    exit_code = cli.main(
        [
            "probe-upstox",
            "--segment",
            "NSE_EQ",
            "--symbol",
            "RELIANCE",
            "--from",
            "2026-07-31",
            "--to",
            "2026-07-31",
        ]
    )

    assert exit_code == 0
    assert dotenv_calls == [True]
    assert capsys.readouterr().out == (
        '{"status":200,"row_count":1,"first_timestamp":"2026-07-31T09:15:00+05:30",'
        '"last_timestamp":"2026-07-31T09:15:00+05:30","schema_valid":true}\n'
    )


def test_cli_uses_the_larger_catalog_budget_without_raising_historical_budget(
    monkeypatch, capsys
) -> None:
    budgets: list[int] = []
    clients: dict[str, object] = {}

    class RecordingTransport:
        def __init__(
            self, *, max_body_bytes: int = DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES
        ) -> None:
            budgets.append(max_body_bytes)

    def catalog_client(transport: object) -> object:
        clients["catalog"] = transport
        return object()

    def historical_client(transport: object) -> object:
        clients["historical"] = transport
        return object()

    def run_probe(request: object, **kwargs: object) -> ProbeReport:
        assert request.segment == "NSE_EQ"
        assert request.symbol == "TCS"
        assert kwargs["catalog_client"] is not kwargs["historical_client"]
        return ProbeReport(200, 1, None, None, True)

    monkeypatch.setattr(cli, "UrllibHttpTransport", RecordingTransport)
    monkeypatch.setattr(cli, "InstrumentCatalogClient", catalog_client)
    monkeypatch.setattr(cli, "UpstoxV3HistoricalClient", historical_client)
    monkeypatch.setattr(cli, "run_capability_probe", run_probe)

    exit_code = cli.main(["probe-upstox", "--segment", "NSE_EQ", "--symbol", "TCS"])

    assert exit_code == 0
    assert budgets == [
        DEFAULT_MAX_CATALOG_COMPRESSED_BYTES,
        DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES,
    ]
    assert clients["catalog"] is not clients["historical"]
    assert capsys.readouterr().err == ""


def test_default_single_download_keeps_public_report_json_and_exit_contract(
    monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path
) -> None:
    report = PublicCommandReportV1(
        "v1",
        "download",
        PublicCommandStatusV1.REJECTED,
        PublicFailureV1(PublicFailureCodeV1.INVALID_INPUT, None, None, None, None, ()),
        0,
        None,
    )

    class Service:
        def download_single(self, request: object) -> object:
            assert request.symbols == ("RELIANCE",)  # type: ignore[attr-defined]
            return report

    universe_file = tmp_path / "nifty50-universe.json"

    def service(source: object, *_args: object) -> Service:
        assert isinstance(source, cli.CanonicalFileNifty50UniverseSourceV1)
        assert source.path == universe_file
        return Service()

    monkeypatch.setattr(cli, "_default_bounded_download_service", service)
    assert (
        cli.main(
            [
                "download",
                "--segment",
                "NSE_EQ",
                "--symbol",
                "RELIANCE",
                "--from",
                "2026-07-01",
                "--to",
                "2026-07-31",
                "--storage-root",
                str(tmp_path),
                "--universe-file",
                str(universe_file),
                "--output",
                "json",
            ]
        )
        == 2
    )
    assert capsys.readouterr().out == (
        '{"contract_version":"v1","command":"download","status":"REJECTED",'
        '"failure":{"code":"INVALID_INPUT","run_failure_code":null,'
        '"historical_fetch_code":null,"failure_category":null,'
        '"validation_reason":null,"months":[]},"provider_attempt_count":0,'
        '"payload":null}\n'
    )


def test_default_multi_download_keeps_the_bounded_aggregate_contract(
    monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path
) -> None:
    report = BoundedNifty50DownloadReportV1(
        Nifty50BatchOutcomeV1.REJECTED, None, (), 0, 0
    )

    class Service:
        def download(self, request: object) -> BoundedNifty50DownloadReportV1:
            assert request.symbols == ("RELIANCE", "SBIN")  # type: ignore[attr-defined]
            return report

    monkeypatch.setattr(
        cli, "_default_bounded_download_service", lambda *_args: Service()
    )

    assert (
        cli.main(
            [
                "download",
                "--segment",
                "NSE_EQ",
                "--symbols",
                "RELIANCE,SBIN",
                "--from",
                "2026-07-01",
                "--to",
                "2026-07-31",
                "--storage-root",
                str(tmp_path),
                "--output",
                "json",
            ]
        )
        == 2
    )
    assert '"scope":"nifty50"' in capsys.readouterr().out


@pytest.mark.parametrize(
    "error_type",
    (AssertionError, KeyError, RuntimeError, TypeError, ValueError, Exception),
)
def test_unexpected_execution_fault_emits_no_market_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    error_type: type[Exception],
) -> None:
    error = error_type("private/path/token/provider-payload")

    class FailingCoverage:
        def coverage(self, _request: object) -> Never:
            raise error

    exit_code = cli.main(
        _persistent_command("coverage", tmp_path), coverage_service=FailingCoverage()
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "internal_error\n"


def test_cli_rejects_unknown_arguments_without_echoing_private_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        cli.main(
            _persistent_command("coverage", tmp_path)
            + ["--private-input=private/path/token"]
        )
    assert exited.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "request_invalid\n"


def test_cli_does_not_publish_report_before_exit_status_is_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = PublicCommandReportV1(
        "v1",
        "coverage",
        PublicCommandStatusV1.REJECTED,
        PublicFailureV1(PublicFailureCodeV1.INVALID_INPUT, None, None, None, None, ()),
        0,
        None,
    )

    class Coverage:
        def coverage(self, _request: object) -> PublicCommandReportV1[object]:
            return report

    def fail_exit_code(_status: object) -> Never:
        raise RuntimeError("private/path/token")

    monkeypatch.setattr(cli, "public_exit_code", fail_exit_code)
    assert (
        cli.main(
            _persistent_command("coverage", tmp_path),
            coverage_service=Coverage(),  # type: ignore[arg-type]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "internal_error\n"


def test_probe_fault_does_not_disclose_a_dynamic_exception_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_error = type("private-provider-token-" * 1024, (Exception,), {})

    def run_probe(*_args: object, **_kwargs: object) -> Never:
        raise private_error("private/path/provider-payload")

    monkeypatch.setattr(cli, "run_capability_probe", run_probe)

    exit_code = cli.main(
        ["probe-upstox", "--segment", "NSE_EQ", "--symbol", "RELIANCE"]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "internal_error\n"


def _range_command(
    command: str, selection: str, root: Path, *, months: int = 1
) -> list[str]:
    end = "2026-07-31" if months == 1 else "2026-07-01"
    start = "2026-07-01" if months == 1 else "2025-07-01"
    values = [
        command,
        "--segment",
        "NSE_EQ",
        selection,
        "RELIANCE" if selection == "--symbol" else "RELIANCE,SBIN",
        "--from",
        start,
        "--to",
        end,
        "--storage-root",
        str(root),
    ]
    if command == "query":
        values.extend(
            [
                "--timeframe",
                "1d",
                "--fields",
                "ts,open,high,low,close,volume",
                "--max-rows",
                "31",
            ]
        )
    return values + ["--output", "json"]


@pytest.mark.parametrize("command", ("download", "coverage", "query"))
def test_invalid_default_bounded_range_does_not_create_root_or_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
    command: str,
) -> None:
    root = tmp_path / "must-not-exist"
    service_name = {
        "download": "_default_bounded_download_service",
        "coverage": "_default_bounded_read_service",
        "query": "_default_bounded_read_service",
    }[command]
    monkeypatch.setattr(
        cli,
        service_name,
        lambda *_args: pytest.fail("default service must not be constructed"),
    )

    assert cli.main(_range_command(command, "--symbols", root, months=13)) == 2

    assert not root.exists()
    assert json.loads(capsys.readouterr().out) == {
        "command": command,
        "contract_version": "v1",
        "provider_attempt_count": 0,
        "results": [],
        "scope": "nifty50",
        "status": "REJECTED",
        "universe_snapshot_sha256": None,
        "worker_count": 0,
    }


@pytest.mark.parametrize("command", ("download", "coverage", "query"))
def test_invalid_injected_range_preserves_service_classification_without_mkdir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
    command: str,
) -> None:
    root = tmp_path / "must-not-exist"
    calls: list[object] = []
    report = PublicCommandReportV1(
        "v1",
        command,  # type: ignore[arg-type]
        PublicCommandStatusV1.REJECTED,
        PublicFailureV1(
            PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED,
            None,
            None,
            None,
            None,
            (),
        ),
        0,
        None,
    )

    class Service:
        def download(self, request: object) -> PublicCommandReportV1[object]:
            calls.append(request)
            return report

        def coverage(self, request: object) -> PublicCommandReportV1[object]:
            calls.append(request)
            return report

        def query(self, request: object) -> PublicCommandReportV1[object]:
            calls.append(request)
            return report

    kwargs = {f"{command}_service": Service()}
    assert cli.main(_range_command(command, "--symbol", root, months=13), **kwargs) == 2  # type: ignore[arg-type]

    assert len(calls) == 1
    assert not root.exists()
    assert json.loads(capsys.readouterr().out)["failure"]["code"] == (
        "QUERY_BOUNDS_EXCEEDED"
    )


@pytest.mark.parametrize("command", ("download", "coverage", "query"))
@pytest.mark.parametrize("selection", ("--symbol", "--symbols"))
def test_mkdir_oserror_renders_scope_correct_unavailable_without_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
    command: str,
    selection: str,
) -> None:
    def blocked(_root: object) -> Path:
        raise OSError("private-path")

    monkeypatch.setattr(cli, "_prepare_storage_root", blocked)
    for service_name in (
        "_default_bounded_download_service",
        "_default_nifty50_coverage_service",
        "_default_nifty50_query_service",
        "_default_bounded_read_service",
    ):
        monkeypatch.setattr(
            cli,
            service_name,
            lambda *_args: pytest.fail("service must not be constructed"),
        )

    expected_exit = 4
    assert (
        cli.main(_range_command(command, selection, tmp_path / "blocked"))
        == expected_exit
    )

    value = json.loads(capsys.readouterr().out)
    if selection == "--symbols":
        assert value == {
            "command": command,
            "contract_version": "v1",
            "provider_attempt_count": 0,
            "results": [],
            "scope": "nifty50",
            "status": "UNAVAILABLE",
            "universe_snapshot_sha256": None,
            "worker_count": 0,
        }
    else:
        expected_code = (
            "INGESTION_UNAVAILABLE"
            if command == "download"
            else "QUERY_CATALOG_UNAVAILABLE"
        )
        assert value == {
            "contract_version": "v1",
            "command": command,
            "status": "UNAVAILABLE",
            "failure": {
                "code": expected_code,
                "run_failure_code": None,
                "historical_fetch_code": None,
                "failure_category": None,
                "validation_reason": None,
                "months": [],
            },
            "provider_attempt_count": 0,
            "payload": None,
        }


@pytest.mark.parametrize("route", ("default-single", "bounded", "injected"))
def test_daily_query_row_limit_is_rejected_before_root_admission_with_exact_classification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    route: str,
) -> None:
    root = tmp_path / "must-not-exist"
    command = _range_command(
        "query", "--symbol" if route == "default-single" else "--symbols", root
    )
    command[command.index("31")] = "367"
    report = PublicCommandReportV1(
        "v1",
        "query",
        PublicCommandStatusV1.REJECTED,
        PublicFailureV1(
            PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED,
            None,
            None,
            None,
            None,
            (),
        ),
        0,
        None,
    )
    calls: list[object] = []

    class Service:
        def query(self, request: object) -> PublicCommandReportV1[object]:
            calls.append(request)
            return report

    monkeypatch.setattr(
        cli,
        "_prepare_storage_root",
        lambda _root: pytest.fail("storage root must not be prepared"),
    )
    kwargs: dict[str, object] = {}
    if route == "default-single":
        monkeypatch.setattr(cli, "_default_nifty50_query_service", Service)
    elif route == "bounded":
        monkeypatch.setattr(
            cli,
            "_default_bounded_read_service",
            lambda: pytest.fail("bounded service must not be constructed"),
        )
    else:
        kwargs["query_service"] = Service()

    assert cli.main(command, **kwargs) == 2  # type: ignore[arg-type]

    assert not root.exists()
    value = json.loads(capsys.readouterr().out)
    if route == "bounded":
        assert calls == []
        assert value == {
            "command": "query",
            "contract_version": "v1",
            "provider_attempt_count": 0,
            "results": [],
            "scope": "nifty50",
            "status": "REJECTED",
            "universe_snapshot_sha256": None,
            "worker_count": 0,
        }
    else:
        assert len(calls) == 1
        assert calls[0].max_rows == 367  # type: ignore[attr-defined]
        assert value == {
            "command": "query",
            "contract_version": "v1",
            "failure": {
                "code": "QUERY_BOUNDS_EXCEEDED",
                "failure_category": None,
                "historical_fetch_code": None,
                "months": [],
                "run_failure_code": None,
                "validation_reason": None,
            },
            "payload": None,
            "provider_attempt_count": 0,
            "status": "REJECTED",
        }


@pytest.mark.parametrize("selection", ("--symbol", "--symbols"))
def test_invalid_default_universe_source_is_terminal_before_root_or_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    selection: str,
) -> None:
    root = tmp_path / "must-not-exist"
    command = _range_command("download", selection, root)
    command[command.index("--output") : command.index("--output")] = [
        "--universe-file",
        "relative-universe.json",
    ]
    monkeypatch.setattr(
        cli,
        "_prepare_storage_root",
        lambda _root: pytest.fail("storage root must not be prepared"),
    )
    monkeypatch.setattr(
        cli,
        "_default_bounded_download_service",
        lambda *_args: pytest.fail("download service must not be constructed"),
    )

    assert cli.main(command) == 2

    assert not root.exists()
    captured = capsys.readouterr()
    assert captured.err == ""
    value = json.loads(captured.out)
    if selection == "--symbols":
        assert value == {
            "command": "download",
            "contract_version": "v1",
            "provider_attempt_count": 0,
            "results": [],
            "scope": "nifty50",
            "status": "REJECTED",
            "universe_snapshot_sha256": None,
            "worker_count": 0,
        }
    else:
        assert value == {
            "command": "download",
            "contract_version": "v1",
            "failure": {
                "code": "INVALID_INPUT",
                "failure_category": None,
                "historical_fetch_code": None,
                "months": [],
                "run_failure_code": None,
                "validation_reason": None,
            },
            "payload": None,
            "provider_attempt_count": 0,
            "status": "REJECTED",
        }


@pytest.mark.parametrize("command", ("download", "coverage", "query"))
def test_invalid_injected_segment_preserves_typed_request_without_mkdir(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    root = tmp_path / "must-not-exist"
    calls: list[object] = []
    report = PublicCommandReportV1(
        "v1",
        command,  # type: ignore[arg-type]
        PublicCommandStatusV1.REJECTED,
        PublicFailureV1(
            PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
            None,
            None,
            None,
            None,
            (),
        ),
        0,
        None,
    )

    class Service:
        def download(self, request: object) -> PublicCommandReportV1[object]:
            calls.append(request)
            return report

        def coverage(self, request: object) -> PublicCommandReportV1[object]:
            calls.append(request)
            return report

        def query(self, request: object) -> PublicCommandReportV1[object]:
            calls.append(request)
            return report

    argv = _range_command(command, "--symbol", root)
    argv[argv.index("NSE_EQ")] = "BSE_EQ"
    assert cli.main(argv, **{f"{command}_service": Service()}) == 2  # type: ignore[arg-type]

    assert len(calls) == 1
    assert calls[0].segment == "BSE_EQ"
    assert not root.exists()
    assert json.loads(capsys.readouterr().out)["failure"]["code"] == (
        "UNSUPPORTED_PREVIEW_INSTRUMENT"
    )


def _install_synthetic_probe(
    monkeypatch: pytest.MonkeyPatch, source: str, payload: bytes
) -> None:
    catalog_payload = gzip.compress(
        json.dumps(
            [
                {
                    "segment": "NSE_EQ",
                    "exchange": "NSE",
                    "isin": "INE002A01018",
                    "instrument_type": "EQ",
                    "instrument_key": "NSE_EQ|INE002A01018",
                    "trading_symbol": "RELIANCE",
                }
            ]
        ).encode()
    )

    class TokenProvider:
        def get_access_token(self) -> AccessToken:
            return AccessToken("synthetic-probe-token")

    class Transport:
        def __init__(self, *, max_body_bytes: int) -> None:
            del max_body_bytes

        def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
            if url.endswith("/NSE.json.gz"):
                body = payload if source == "catalog" else catalog_payload
            else:
                body = payload
            return HttpResponse(status_code=200, body=body)

    monkeypatch.setattr(cli, "load_dotenv", lambda: False)
    monkeypatch.setattr(cli, "EnvironmentAccessTokenProvider", TokenProvider)
    monkeypatch.setattr(cli, "UrllibHttpTransport", Transport)


@pytest.mark.parametrize(
    "source,payload",
    (
        ("historical", b"{"),
        ("historical", b'{"status":"success","data":[]}'),
        ("historical", b'{"status":"success","data":{"candles":{}}}'),
        ("catalog", gzip.compress(b"[" * 2000 + b"]" * 2000, mtime=0)),
        ("catalog", gzip.compress(b"[" + b"9" * 5000 + b"]", mtime=0)),
        ("catalog", bytes.fromhex("1f8b0800000000000003070000000000000000")),
    ),
    ids=(
        "historical-json",
        "historical-envelope",
        "historical-candles",
        "catalog-depth",
        "catalog-integer-limit",
        "catalog-deflate",
    ),
)
def test_real_probe_keeps_malformed_provider_payloads_recognized(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    source: str,
    payload: bytes,
) -> None:
    _install_synthetic_probe(monkeypatch, source, payload)
    prior_integer_limit = sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(4300)
        status = cli.main(
            ["probe-upstox", "--segment", "NSE_EQ", "--symbol", "RELIANCE"]
        )
    finally:
        sys.set_int_max_str_digits(prior_integer_limit)
    output = capsys.readouterr()
    assert (status, output.out, output.err) == (2, "", "probe_failed\n")


def test_real_probe_reports_historical_decoder_defect_as_internal_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_synthetic_probe(
        monkeypatch, "historical", b'{"status":"success","data":{"candles":[]}}'
    )
    failure = RuntimeError("private/path/token")
    calls: list[str] = []

    def fail_object(_pairs: object) -> Never:
        calls.append("decode")
        raise failure

    monkeypatch.setattr(historical, "_unique_json_object", fail_object)
    status = cli.main(["probe-upstox", "--segment", "NSE_EQ", "--symbol", "RELIANCE"])
    output = capsys.readouterr()
    assert calls == ["decode"]
    assert (status, output.out, output.err) == (2, "", "internal_error\n")


@pytest.mark.parametrize("reader", ("cohort", "regime", "historical"))
@pytest.mark.parametrize("failure_kind", ("admission", "read"))
def test_local_reader_preserves_primary_failure_and_closes_all_descriptors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    reader: str,
    failure_kind: str,
) -> None:
    path = (tmp_path / "input.json").resolve()
    path.write_bytes(b"" if failure_kind == "admission" else b"{}")
    path.chmod(0o600)
    metadata = path.stat()
    identity = (metadata.st_dev, metadata.st_ino)
    root = (tmp_path / "storage").resolve()
    root.mkdir(mode=0o700)
    admitted_root = cli._admit_historical_storage_root(root)
    primary = AssertionError("primary local read failure")
    cleanup_error = (
        AssertionError("secondary admission close failure")
        if failure_kind == "admission"
        else OSError("secondary read close failure")
    )
    opened: set[int] = set()
    real_open, real_close = cli.os.open, cli.os.close
    real_read, real_fstat = cli.os.read, cli.os.fstat

    def track_open(
        path: str | Path,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.add(descriptor)
        return descriptor

    def is_input(descriptor: int) -> bool:
        current = real_fstat(descriptor)
        return (current.st_dev, current.st_ino) == identity

    def fail_read(descriptor: int, size: int) -> bytes:
        if is_input(descriptor):
            raise primary
        return real_read(descriptor, size)

    def close_after_failure(descriptor: int) -> None:
        target = is_input(descriptor)
        real_close(descriptor)
        opened.discard(descriptor)
        if target:
            raise cleanup_error

    monkeypatch.setattr(cli.os, "open", track_open)
    monkeypatch.setattr(cli.os, "read", fail_read)
    monkeypatch.setattr(cli.os, "close", close_after_failure)
    expected = cli._RequestInvalid if failure_kind == "admission" else AssertionError
    with pytest.raises(expected) as raised:
        if reader == "cohort":
            cli._read_cohort_file(path)
        elif reader == "regime":
            cli._read_current_regime_input(path)
        else:
            cli._read_historical_local_file(path, 1024, admitted_root)

    if failure_kind == "read":
        assert raised.value is primary
    assert not opened


@pytest.mark.parametrize("reader", ("historical", "regime"))
def test_traversal_close_fault_preserves_primary_and_closes_owned_descriptors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    reader: str,
) -> None:
    input_file = tmp_path / "nested" / "input.json"
    input_file.parent.mkdir()
    input_file.write_bytes(b"{}")
    input_file.chmod(0o600)
    storage_root = tmp_path / "storage"
    storage_root.mkdir(mode=0o700)
    admitted_root = cli._admit_historical_storage_root(storage_root)
    primary = AssertionError("traversal close fault")
    cleanup_error = OSError("secondary descriptor cleanup fault")
    opened: set[int] = set()
    replacement: int | None = None
    replacement_owned = False
    real_open, real_close = cli.os.open, cli.os.close

    def track_open(
        path: str | Path,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.add(descriptor)
        return descriptor

    def close_with_fault(descriptor: int) -> None:
        nonlocal replacement, replacement_owned
        if descriptor not in opened:
            if descriptor == replacement:
                replacement_owned = False
            real_close(descriptor)
            return
        opened.remove(descriptor)
        real_close(descriptor)
        if replacement is None:
            replacement = real_open("/dev/null", cli.os.O_RDONLY | cli.os.O_CLOEXEC)
            replacement_owned = True
            assert replacement == descriptor
            raise primary
        raise cleanup_error

    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(cli.os, "open", track_open)
            scoped.setattr(cli.os, "close", close_with_fault)
            with pytest.raises(AssertionError) as raised:
                if reader == "historical":
                    cli._read_historical_local_file(input_file, 1024, admitted_root)
                else:
                    cli._read_current_regime_input(input_file)
            assert raised.value is primary
        assert not opened
        assert replacement is not None
        assert replacement_owned
        cli.os.fstat(replacement)
    finally:
        for descriptor in opened:
            real_close(descriptor)
        if replacement_owned and replacement is not None:
            real_close(replacement)
