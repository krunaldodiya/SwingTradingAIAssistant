from __future__ import annotations

import pytest

from swing_trading_ai_assistant.market_data import cli
from swing_trading_ai_assistant.market_data.http import (
    DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES,
)
from swing_trading_ai_assistant.market_data.instruments import (
    DEFAULT_MAX_CATALOG_COMPRESSED_BYTES,
)
from swing_trading_ai_assistant.market_data.probe import ProbeReport


def test_cli_explains_that_documentation_date_placeholders_must_be_replaced(
    capsys,
) -> None:
    with pytest.raises(SystemExit, match="2"):
        cli.build_parser().parse_args(
            [
                "probe-upstox",
                "--segment",
                "NSE_EQ",
                "--symbol",
                "RELIANCE",
                "--from",
                "YYYY-MM-DD",
            ]
        )

    assert (
        "replace YYYY-MM-DD with an actual date, for example 2026-08-03"
        in capsys.readouterr().err
    )


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


def test_cli_redacts_provider_failures(monkeypatch, capsys) -> None:
    def run_probe(*args: object, **kwargs: object) -> ProbeReport:
        raise ValueError("secret-token")

    monkeypatch.setattr(cli, "run_capability_probe", run_probe)

    exit_code = cli.main(
        ["probe-upstox", "--segment", "NSE_EQ", "--symbol", "RELIANCE"]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == "probe_failed:ValueError\n"
    assert "secret-token" not in captured.err
