"""The raw session capture is incremental, additive, and provider-bounded."""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportIndexIssue=false

from __future__ import annotations

import contextlib
import csv
import hashlib
import importlib.util
import io
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.bharatstock import (
    PRICE_BASIS,
    PROVIDER_SOURCE,
    VOLUME_BASIS,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.historical_nifty_universe import (
    build_historic_nifty_universe,
    retain_historic_nifty_universe,
)

_SPEC = importlib.util.spec_from_file_location(
    "capture_bharatstock_current",
    Path(__file__).parents[1] / "scripts" / "capture_bharatstock_current.py",
)
assert _SPEC is not None and _SPEC.loader is not None
capture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(capture)

END = "2026-11-13"
STAGE_START = "2025-10-01"
_NIFTY50 = tuple(f"A{index:03d}" for index in range(50))
_NIFTYNEXT50 = tuple(f"B{index:03d}" for index in range(50))
_NIFTY100 = _NIFTY50 + _NIFTYNEXT50
_NIFTY200 = _NIFTY100 + tuple(f"C{index:03d}" for index in range(100))
_URLS = {
    "nifty50": "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
    "niftynext50": (
        "https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv"
    ),
    "nifty100": "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
    "nifty200": "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv",
}


def _csv(symbols: tuple[str, ...], *, isin_base: int) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(("Company Name", "Industry", "Symbol", "Series", "ISIN Code"))
    for offset, symbol in enumerate(symbols):
        writer.writerow(
            (
                f"Company {symbol}",
                "Industry",
                symbol,
                "EQ",
                f"INE{isin_base + offset:09d}",
            )
        )
    return buffer.getvalue().encode()


def _universe(root: Path) -> None:
    universe = build_historic_nifty_universe(
        _csv(_NIFTY50, isin_base=0),
        _csv(_NIFTYNEXT50, isin_base=50),
        _csv(_NIFTY100, isin_base=0),
        _csv(_NIFTY200, isin_base=0),
        window_start=date(2026, 1, 1),
        window_end=date(2026, 12, 31),
        nifty50_source_url=_URLS["nifty50"],
        niftynext50_source_url=_URLS["niftynext50"],
        nifty100_source_url=_URLS["nifty100"],
        nifty200_source_url=_URLS["nifty200"],
        retrieved_at=datetime(2026, 11, 14, tzinfo=UTC),
    )
    retain_historic_nifty_universe(root, universe)


def _member(index: int) -> tuple[str, str]:
    return f"INE{index:09d}", _NIFTY200[index]


def _write_session(
    store: Path,
    isin: str,
    symbol: str,
    session: str,
    **overrides: object,
) -> Path:
    """Write one cache entry that the capture script and client both accept."""
    path = (
        store
        / "bharatstock-session-cache-v1"
        / f"isin={isin}"
        / "exchange=NSE"
        / f"session={session}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "schema": "bharatstock-session-cache@v1",
        "provider": PROVIDER_SOURCE,
        "price_basis": PRICE_BASIS,
        "volume_basis": VOLUME_BASIS,
        "isin": isin,
        "exchange": "NSE",
        "symbol": symbol,
        "session": session,
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": 1000,
        "adjusted_close": None,
        "adjustment_factor": None,
        "response_sha256s": ["a" * 64, "b" * 64],
        "request_count": 2,
        "retrieved_at": "2026-11-13T00:00:00+00:00",
    }
    payload.update(overrides)
    body = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode()
    payload["record_sha256"] = hashlib.sha256(body).hexdigest()
    path.write_text(json.dumps(payload, sort_keys=True))
    return path


class _Row:
    def __init__(self, session: date) -> None:
        self.session = session


class _History:
    def __init__(self, rows: tuple[_Row, ...]) -> None:
        self.rows = rows


class _FakeClient:
    calls: list[tuple[str, date, date]] = []
    constructions: list[str] = []
    writes_cache = True

    def __init__(self, *, session_cache_root: Path, max_requests: int) -> None:
        self.root = session_cache_root
        self.max_requests = max_requests
        self.requests_used = 0
        type(self).constructions.append("client")

    def _rows(self, start: date, end: date) -> tuple[date, ...]:
        return (start,) if start == end else (start, end)

    def history(self, instrument: BharatStockInstrument, start: date, end: date):
        type(self).calls.append((instrument.symbol, start, end))
        self.requests_used = 1
        sessions = self._rows(start, end)
        if type(self).writes_cache:
            for session in sessions:
                _write_session(
                    self.root, instrument.isin, instrument.symbol, session.isoformat()
                )
        return _History(tuple(_Row(session) for session in sessions))


class _SilentClient(_FakeClient):
    writes_cache = False


class _FailingClient(_FakeClient):
    def history(self, instrument: BharatStockInstrument, start: date, end: date):
        type(self).calls.append((instrument.symbol, start, end))
        # A failed attempt still consumed provider quota.
        self.requests_used = 2
        raise capture.BharatStockError("RESPONSE_INVALID", member_local=True)


class _FlakyClient(_FakeClient):
    attempts = 0

    def history(self, instrument: BharatStockInstrument, start: date, end: date):
        type(self).attempts += 1
        self.requests_used = 1
        if type(self).attempts == 1:
            raise capture.BharatStockError("TRANSPORT_FAILED", member_local=False)
        return super().history(instrument, start, end)


class _RateLimitedClient(_FakeClient):
    def history(self, instrument: BharatStockInstrument, start: date, end: date):
        self.requests_used = 1
        raise capture.BharatStockError("RATE_LIMITED", member_local=False)


def _run(tmp_path: Path, *extra: str) -> tuple[int, dict[str, object]]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = capture.main(
            [
                "--storage-root",
                str(tmp_path / "store"),
                "--universe-snapshot",
                str(
                    tmp_path / "store" / "universe_snapshots" / "nifty-universe-v3.json"
                ),
                "--start",
                STAGE_START,
                "--end",
                END,
                "--checkpoint",
                str(tmp_path / "checkpoint.json"),
                "--delay",
                "0",
                *extra,
            ]
        )
    return code, json.loads(output.getvalue())


def _reset() -> None:
    _FakeClient.calls = []
    _FakeClient.constructions = []
    _FlakyClient.attempts = 0


def test_dry_run_is_provider_free(tmp_path: Path) -> None:
    _universe(tmp_path / "store")
    _reset()

    code, summary = _run(tmp_path, "--limit", "2", "--dry-run")

    assert code == 0
    assert summary["status"] == "DRY_RUN"
    assert summary["pending_symbols"] == 2
    assert summary["requests_used"] == 0
    assert _FakeClient.constructions == []
    universe = tmp_path / "store" / "universe_snapshots" / "nifty-universe-v3.json"
    identity = summary["universe"]
    assert identity["sha256"] == hashlib.sha256(universe.read_bytes()).hexdigest()
    assert identity["schema"] == "retained-nifty-universe@v3"
    assert identity["members"] == 200
    assert summary["universe_snapshot_sha256"] == identity["sha256"]
    assert (
        summary["runtime"]["sha256"]
        == hashlib.sha256(Path(str(capture.__file__)).read_bytes()).hexdigest()
    )


def test_invalid_universe_snapshot_is_rejected_before_any_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store")
    snapshot = tmp_path / "store" / "universe_snapshots" / "nifty-universe-v3.json"
    payload = json.loads(snapshot.read_text())
    payload["schema"] = "retained-nifty-universe@v2"
    snapshot.write_text(json.dumps(payload))
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FakeClient)

    with contextlib.redirect_stdout(io.StringIO()):
        code = capture.main(
            [
                "--storage-root",
                str(tmp_path / "store"),
                "--universe-snapshot",
                str(snapshot),
                "--start",
                STAGE_START,
                "--end",
                END,
                "--checkpoint",
                str(tmp_path / "checkpoint.json"),
                "--delay",
                "0",
            ]
        )

    assert code == 2
    assert _FakeClient.constructions == []
    assert _FakeClient.calls == []


def test_existing_sessions_are_skipped_without_a_provider_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store")
    for index in range(2):
        isin, symbol = _member(index)
        _write_session(tmp_path / "store", isin, symbol, END)
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FakeClient)

    code, summary = _run(tmp_path, "--limit", "2")

    assert code == 1
    assert _FakeClient.calls == []
    assert _FakeClient.constructions == []
    assert summary["status"] == "INCOMPLETE"
    assert summary["requests_used"] == 0
    assert summary["symbols"]["A000"]["status"] == "SKIPPED"
    assert summary["symbols"]["A001"]["status"] == "SKIPPED"
    assert summary["remaining_pending"] == 198


def test_invalid_but_self_consistent_cache_record_is_not_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store")
    isin, symbol = _member(0)
    # The digest is recomputed over the corrupt row, so only the full client
    # validation can reject it: low must not exceed close.
    _write_session(tmp_path / "store", isin, symbol, END, low="102")
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FakeClient)

    code, summary = _run(tmp_path, "--limit", "1")

    assert code == 1
    assert _FakeClient.calls == [(symbol, date(2025, 10, 1), date(2026, 11, 13))]
    assert summary["symbols"][symbol]["status"] == "COMPLETE"


def test_incremental_fetch_starts_after_the_newest_cached_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store")
    isin, symbol = _member(0)
    _write_session(tmp_path / "store", isin, symbol, "2026-11-10")
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FakeClient)

    code, summary = _run(tmp_path, "--limit", "1")

    assert code == 1
    assert _FakeClient.calls == [(symbol, date(2026, 11, 11), date(2026, 11, 13))]
    assert summary["status"] == "INCOMPLETE"
    assert summary["symbols"][symbol]["fetch_start"] == "2026-11-11"
    assert summary["symbols"][symbol]["sessions_written"] == 2
    assert summary["symbols"][symbol]["sessions_expected"] == 2
    assert summary["latest_session"] == END
    # The pre-existing session file is untouched and still readable.
    assert (
        tmp_path
        / "store"
        / "bharatstock-session-cache-v1"
        / f"isin={isin}"
        / "exchange=NSE"
        / "session=2026-11-10.json"
    ).is_file()


def test_member_without_a_cached_session_fetches_the_bounded_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store")
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FakeClient)

    code, summary = _run(tmp_path, "--limit", "1")

    assert code == 1
    assert _FakeClient.calls == [(_NIFTY200[0], date(2025, 10, 1), date(2026, 11, 13))]
    assert summary["symbols"][_NIFTY200[0]]["fetch_start"] == STAGE_START


def test_rerun_makes_no_provider_call_for_a_captured_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store")
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FakeClient)
    code, first = _run(tmp_path, "--limit", "2")
    assert code == 1
    assert first["completed"] == 2

    _reset()
    code, second = _run(tmp_path)

    assert code == 0
    # Both captured members are re-checked against the cache and skipped with
    # no provider request of their own.
    assert second["symbols"][_NIFTY200[0]]["status"] == "SKIPPED"
    assert second["symbols"][_NIFTY200[1]]["status"] == "SKIPPED"
    assert second["skipped"] == 2
    assert len(_FakeClient.calls) == 198
    assert second["requests_used"] == 198


def test_missing_cache_write_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store")
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _SilentClient)

    code, summary = _run(tmp_path, "--limit", "1")

    assert code == 1
    assert summary["status"] == "INCOMPLETE"
    record = summary["symbols"][_NIFTY200[0]]
    assert record["status"] == "FAILED"
    assert record["error"] == "SESSION_CACHE_WRITE_MISSING"
    assert record["sessions_written"] == 0
    assert record["sessions_expected"] == 2
    assert summary["remaining_pending"] == 200


def test_member_failure_is_incomplete_and_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store")
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FailingClient)

    code, summary = _run(tmp_path, "--limit", "1")

    assert code == 1
    assert summary["status"] == "INCOMPLETE"
    assert summary["failed"] == 1
    assert summary["failed_isins"] == ["INE000000000"]
    assert summary["remaining_pending"] == 200
    assert summary["symbols"]["A000"]["status"] == "FAILED"
    assert summary["symbols"]["A000"]["error"] == "RESPONSE_INVALID"


def test_quota_reports_failed_attempts_and_the_configured_maximum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store")
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FlakyClient)
    monkeypatch.setattr(capture, "RETRY_DELAYS", (0.0,))

    code, summary = _run(tmp_path, "--limit", "1")

    assert code == 1
    assert _FlakyClient.attempts == 2
    # The failed attempt's request is counted, not discarded.
    assert summary["requests_used"] == 2
    assert summary["requests_configured_max"] == (
        capture.MAX_REQUESTS_PER_MEMBER * capture.PER_MEMBER_ATTEMPTS
    )
    assert summary["max_requests_per_member"] == capture.MAX_REQUESTS_PER_MEMBER


def test_rate_limit_is_a_nonzero_typed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store")
    monkeypatch.setattr(capture, "BharatStockClient", _RateLimitedClient)

    code, summary = _run(tmp_path, "--limit", "1")

    assert code == 3
    assert summary["status"] == "RATE_LIMITED"
    assert summary["completed"] == 0
    assert summary["requests_used"] == 1
    assert summary["symbols"]["A000"]["status"] == "RATE_LIMITED"
