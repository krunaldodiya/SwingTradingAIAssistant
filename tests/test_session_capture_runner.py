"""The raw session capture is incremental, additive, and provider-bounded."""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false

from __future__ import annotations

import base64
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
from datetime import date
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.bharatstock import (
    PRICE_BASIS,
    PROVIDER_SOURCE,
    VOLUME_BASIS,
    BharatStockInstrument,
)

_SPEC = importlib.util.spec_from_file_location(
    "capture_bharatstock_current",
    Path(__file__).parents[1] / "scripts" / "capture_bharatstock_current.py",
)
assert _SPEC is not None and _SPEC.loader is not None
capture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(capture)

END = "2026-11-13"


def _universe(root: Path, count: int) -> None:
    rows = [
        {"ISIN Code": f"INE{index:09d}", "Symbol": f"S{index}"}
        for index in range(count)
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["ISIN Code", "Symbol"])
    writer.writeheader()
    writer.writerows(rows)
    directory = root / "universe_snapshots"
    directory.mkdir(parents=True)
    (directory / "nifty-universe-v3.json").write_text(
        json.dumps(
            {
                "nifty200_source_csv_base64": base64.b64encode(
                    buffer.getvalue().encode()
                ).decode()
            }
        )
    )


def _write_session(store: Path, isin: str, symbol: str, session: str) -> Path:
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

    def __init__(self, *, session_cache_root: Path, max_requests: int) -> None:
        self.root = session_cache_root
        self.max_requests = max_requests
        self.requests_used = 0
        type(self).constructions.append("client")

    def history(self, instrument: BharatStockInstrument, start: date, end: date):
        type(self).calls.append((instrument.symbol, start, end))
        self.requests_used = 1
        _write_session(self.root, instrument.isin, instrument.symbol, start.isoformat())
        _write_session(self.root, instrument.isin, instrument.symbol, end.isoformat())
        return _History((_Row(start), _Row(end)))


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
                "2025-10-01",
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
    _universe(tmp_path / "store", 2)
    _reset()

    code, summary = _run(tmp_path, "--dry-run")

    assert code == 0
    assert summary["status"] == "DRY_RUN"
    assert summary["pending_symbols"] == 2
    assert summary["requests_used"] == 0
    assert _FakeClient.constructions == []
    universe = tmp_path / "store" / "universe_snapshots" / "nifty-universe-v3.json"
    assert (
        summary["universe_snapshot_sha256"]
        == hashlib.sha256(universe.read_bytes()).hexdigest()
    )
    assert (
        summary["runtime"]["sha256"]
        == hashlib.sha256(Path(capture.__file__).read_bytes()).hexdigest()
    )


def test_existing_sessions_are_skipped_without_a_provider_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store", 2)
    _write_session(tmp_path / "store", "INE000000000", "S0", END)
    _write_session(tmp_path / "store", "INE000000001", "S1", END)
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FakeClient)

    code, summary = _run(tmp_path)

    assert code == 0
    assert _FakeClient.calls == []
    assert _FakeClient.constructions == []
    assert summary["status"] == "COMPLETE"
    assert summary["requests_used"] == 0
    symbols = summary["symbols"]
    assert symbols["S0"]["status"] == "SKIPPED"
    assert symbols["S1"]["status"] == "SKIPPED"
    assert summary["remaining_pending"] == 0


def test_incremental_fetch_starts_after_the_newest_cached_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store", 1)
    _write_session(tmp_path / "store", "INE000000000", "S0", "2026-11-10")
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FakeClient)

    code, summary = _run(tmp_path)

    assert code == 0
    assert _FakeClient.calls == [("S0", date(2026, 11, 11), date(2026, 11, 13))]
    assert summary["status"] == "COMPLETE"
    assert summary["symbols"]["S0"]["fetch_start"] == "2026-11-11"
    assert summary["symbols"]["S0"]["sessions_written"] == 2
    assert summary["latest_session"] == END
    # The pre-existing session file is untouched and still readable.
    assert (
        tmp_path
        / "store"
        / "bharatstock-session-cache-v1"
        / "isin=INE000000000"
        / "exchange=NSE"
        / "session=2026-11-10.json"
    ).is_file()


def test_rerun_makes_no_provider_call_for_captured_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store", 2)
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FakeClient)
    code, first = _run(tmp_path, "--limit", "1")
    # A limited run leaves the other member pending, so it is truthfully
    # INCOMPLETE even though its own member completed.
    assert code == 1
    assert first["status"] == "INCOMPLETE"
    assert first["completed"] == 1
    assert first["remaining_pending"] == 1

    _reset()
    code, second = _run(tmp_path)

    assert code == 0
    # The first member's newest session reaches the requested end, so the
    # checkpoint and cache both prevent a provider request; only the
    # still-missing member is fetched.
    assert [call[0] for call in _FakeClient.calls] == ["S1"]
    assert second["symbols"]["S0"]["status"] == "SKIPPED"
    assert second["skipped"] == 1
    assert second["requests_used"] == 1
    assert second["remaining_pending"] == 0
    assert second["status"] == "COMPLETE"


def test_member_failure_is_incomplete_and_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store", 1)
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FailingClient)

    code, summary = _run(tmp_path)

    assert code == 1
    assert summary["status"] == "INCOMPLETE"
    assert summary["failed"] == 1
    assert summary["failed_isins"] == ["INE000000000"]
    assert summary["remaining_pending"] == 1
    assert summary["symbols"]["S0"]["status"] == "FAILED"
    assert summary["symbols"]["S0"]["error"] == "RESPONSE_INVALID"


def test_quota_reports_failed_attempts_and_the_configured_maximum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store", 1)
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FlakyClient)
    monkeypatch.setattr(capture, "RETRY_DELAYS", (0.0,))

    code, summary = _run(tmp_path)

    assert code == 0
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
    _universe(tmp_path / "store", 1)
    monkeypatch.setattr(capture, "BharatStockClient", _RateLimitedClient)

    code, summary = _run(tmp_path)

    assert code == 3
    assert summary["status"] == "RATE_LIMITED"
    assert summary["completed"] == 0
    assert summary["requests_used"] == 1
    assert summary["symbols"]["S0"]["status"] == "RATE_LIMITED"


def test_member_without_a_cached_session_fetches_the_bounded_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store", 1)
    _reset()
    monkeypatch.setattr(capture, "BharatStockClient", _FakeClient)

    code, summary = _run(tmp_path)

    assert code == 0
    assert _FakeClient.calls == [("S0", date(2025, 10, 1), date(2026, 11, 13))]
    assert summary["symbols"]["S0"]["fetch_start"] == "2025-10-01"
