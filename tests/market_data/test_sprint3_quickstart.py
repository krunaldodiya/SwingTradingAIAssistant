"""Credential-free end-to-end proof for the Sprint 3 public preview."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.download_preparation import (
    AuthoritativeScheduleInputV1,
    DownloadPreparationServiceV1,
)
from swing_trading_ai_assistant.market_data.historical import (
    HistoricalRequest,
    HistoricalResponse,
)
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    FetchedInstrumentSnapshotV1,
)
from swing_trading_ai_assistant.market_data.instruments import InstrumentCatalog
from swing_trading_ai_assistant.market_data.preview_admission import (
    PreviewAdmissionPolicyV1,
)
from swing_trading_ai_assistant.market_data.public_download import (
    SingleSymbolDownloadServiceV1,
)
from swing_trading_ai_assistant.market_data.range_ingestion import IngestionCoordinator
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleSession,
    canonical_schedule_bytes,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.market_data.universe_snapshot import (
    Nifty50ConstituentV1,
    Nifty50UniverseSnapshotV1,
    Nifty50UniverseStoreV1,
)

_NOW = datetime(2026, 8, 10, 4, 0, tzinfo=UTC)
_TRADE_DATE = date(2026, 7, 1)
_RELIANCE = {
    "segment": "NSE_EQ",
    "name": "RELIANCE INDUSTRIES LIMITED",
    "exchange": "NSE",
    "isin": "INE002A01018",
    "instrument_type": "EQ",
    "instrument_key": "NSE_EQ|INE002A01018",
    "trading_symbol": "RELIANCE",
}


def _isin(index: int) -> str:
    prefix = f"INE{index:06d}A0"
    for digit in "0123456789":
        candidate = prefix + digit
        expanded = "".join(
            str(ord(value) - 55) if value.isalpha() else value for value in candidate
        )
        total = sum(
            (int(value) * 2 // 10 + int(value) * 2 % 10) if position % 2 else int(value)
            for position, value in enumerate(reversed(expanded))
        )
        if total % 10 == 0:
            return candidate
    raise AssertionError


def _retain_universe(root: Path) -> None:
    members = [Nifty50ConstituentV1("INE002A01018", "RELIANCE", "ENERGY")] + [
        Nifty50ConstituentV1(_isin(index), f"SYM{index:02d}", "FINANCIALS")
        for index in range(49)
    ]
    members.sort(key=lambda member: member.isin)
    observed = datetime(2026, 6, 30, tzinfo=UTC)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(root, lease=acquired.lease) as catalog:
        Nifty50UniverseStoreV1(root, acquired.lease, catalog).retain(
            Nifty50UniverseSnapshotV1(
                1,
                "nifty-50",
                date(2026, 7, 1),
                date(2026, 9, 30),
                "nse-archive",
                "2026-q3",
                observed,
                observed,
                "nse-archive",
                "2026-q3",
                observed,
                observed,
                tuple(members),
            )
        )


class _Clock:
    def now(self) -> datetime:
        return _NOW


class _ScheduleSource:
    def __init__(self, schedule: ExpectedSessionSchedule) -> None:
        self.value = AuthoritativeScheduleInputV1(
            schedule, canonical_schedule_bytes(schedule)
        )

    def load(self) -> AuthoritativeScheduleInputV1:
        return self.value


class _SnapshotSource:
    def __init__(self) -> None:
        self.calls = 0
        decompressed = json.dumps([_RELIANCE], separators=(",", ":")).encode()
        compressed = gzip.compress(decompressed, mtime=0)
        self.value = FetchedInstrumentSnapshotV1(
            datetime(2026, 8, 10, 3, 0, tzinfo=UTC),
            date(2026, 8, 10),
            compressed,
            decompressed,
            hashlib.sha256(compressed).hexdigest(),
            hashlib.sha256(decompressed).hexdigest(),
            InstrumentCatalog.from_json_bytes(decompressed),
            '"quickstart-v1"',
            "Mon, 10 Aug 2026 02:00:00 GMT",
        )

    def fetch(self) -> FetchedInstrumentSnapshotV1:
        self.calls += 1
        return self.value


class _HistoricalSession:
    def __init__(self, response: HistoricalResponse) -> None:
        self.response = response
        self.requests: list[HistoricalRequest] = []

    def fetch(self, request: HistoricalRequest) -> HistoricalResponse:
        self.requests.append(request)
        return self.response


class _HistoricalSessions:
    def __init__(self, response: HistoricalResponse) -> None:
        self.open_calls = 0
        self.session = _HistoricalSession(response)

    def open(self) -> _HistoricalSession:
        self.open_calls += 1
        return self.session


def _schedule() -> ExpectedSessionSchedule:
    return ExpectedSessionSchedule(
        2,
        "nse-authoritative-quickstart",
        "release-2026-08-01",
        datetime(2026, 8, 1, tzinfo=UTC),
        "Asia/Kolkata",
        date(2026, 7, 1),
        date(2026, 7, 31),
        (
            ScheduleSession(
                _TRADE_DATE,
                datetime(2026, 7, 1, 3, 45, tzinfo=UTC),
                datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
                "regular",
            ),
        ),
        tuple(
            ScheduleClosure(date(2026, 7, 1) + timedelta(days=offset), "closed")
            for offset in range(1, 31)
        ),
    )


def _historical_response() -> HistoricalResponse:
    opening = datetime(2026, 7, 1, 3, 45, tzinfo=UTC)
    rows = [
        [
            (opening + timedelta(minutes=index)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            100.0,
            101.0,
            99.0,
            100.5,
            1_000 + index,
            None,
        ]
        for index in range(375)
    ]
    return HistoricalResponse(200, rows)


def _command(root: Path, name: str, *, timeframe: str | None = None) -> list[str]:
    values = [
        name,
        "--segment",
        "NSE_EQ",
        "--symbol",
        "RELIANCE",
        "--from",
        "2026-07-01",
        "--to",
        "2026-07-01" if name == "query" else "2026-07-31",
    ]
    if timeframe is not None:
        values.extend(
            [
                "--timeframe",
                timeframe,
                "--fields",
                "ts,open,high,low,close,volume",
                "--max-rows",
                "31" if timeframe == "1d" else "1000",
            ]
        )
    return values + ["--storage-root", str(root), "--output", "json"]


def _invoke(capsys, argv: list[str], **services: object) -> dict[str, object]:
    assert main(argv, **services) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "SUCCEEDED"
    assert str(output).find("quickstart-token") == -1
    return output


def test_clean_quickstart_proves_persistent_repeat_and_read_workflow(
    tmp_path: Path, capsys
) -> None:
    readme = Path("README.md").read_text()
    preview_contract = Path("docs/plans/04-public-preview-contract.md").read_text()
    assert "## Downloader v1 quickstart" in readme
    assert "SCHEDULE_EVIDENCE_UNAVAILABLE" in preview_contract
    assert "provenance-complete supplied NSE schedule evidence" in readme
    assert "tests/market_data/test_sprint3_quickstart.py" in readme
    assert "--symbols RELIANCE,SBIN,TCS" in readme
    assert "--universe nifty50-current" in readme
    assert "latest completed authoritative session" in readme
    assert "Upstox remains primary for live/raw OHLCV" in readme
    assert "yfinance is a separate adjusted-daily research provider" in readme
    assert "~/SwingTradingAIAssistantData" in readme

    schedule = _schedule()
    snapshots = _SnapshotSource()
    sessions = _HistoricalSessions(_historical_response())
    service = SingleSymbolDownloadServiceV1(
        DownloadPreparationServiceV1(
            PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
            _ScheduleSource(schedule),
            snapshots,
        ),
        IngestionCoordinator(
            session_factory=sessions,
            clock=_Clock(),
            run_id_factory=iter(("quickstart-first", "quickstart-repeat")).__next__,
        ),
        clock=_Clock(),
    )

    first = _invoke(capsys, _command(tmp_path, "download"), download_service=service)
    repeat = _invoke(capsys, _command(tmp_path, "download"), download_service=service)
    _retain_universe(tmp_path)
    coverage = _invoke(capsys, _command(tmp_path, "coverage"))
    minute = _invoke(capsys, _command(tmp_path, "query", timeframe="1m"))
    five_minute = _invoke(capsys, _command(tmp_path, "query", timeframe="5m"))
    daily = _invoke(capsys, _command(tmp_path, "query", timeframe="1d"))

    assert first["provider_attempt_count"] == 2
    assert first["payload"]["verified_count"] == 1
    assert repeat["provider_attempt_count"] == 0
    assert repeat["payload"]["skipped_count"] == 1
    assert snapshots.calls == sessions.open_calls == len(sessions.session.requests) == 1
    assert coverage["provider_attempt_count"] == 0
    assert coverage["payload"]["months"][0]["coverage_state"] == "VERIFIED"
    assert minute["provider_attempt_count"] == 0
    assert minute["payload"]["row_count"] == 375
    assert five_minute["provider_attempt_count"] == 0
    assert five_minute["payload"]["row_count"] == 75
    assert (
        five_minute["payload"]["calculation_version"] == "nse-session-intraday-ohlcv@v1"
    )
    assert five_minute["payload"]["bucket_minutes"] == 5
    assert daily["provider_attempt_count"] == 0
    assert daily["payload"]["row_count"] == 1
    assert daily["payload"]["calculation_version"] == "nse-session-ohlcv@v1"
    assert daily["payload"]["adjustment_state"] == "raw"
    for output in (first, repeat, coverage, minute, five_minute, daily):
        assert str(tmp_path) not in json.dumps(output)
    assert (tmp_path / "catalog.duckdb").is_file()
    assert tuple(tmp_path.rglob("bars.parquet"))
