"""The raw session capture is additive, resumable, and independent of research."""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false

from __future__ import annotations

import base64
import contextlib
import csv
import importlib.util
import io
import json
from datetime import date
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.bharatstock import BharatStockInstrument

_SPEC = importlib.util.spec_from_file_location(
    "capture_bharatstock_current",
    Path(__file__).parents[1] / "scripts" / "capture_bharatstock_current.py",
)
assert _SPEC is not None and _SPEC.loader is not None
capture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(capture)


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


class _FakeClient:
    calls: list[str] = []
    root: Path

    def __init__(self, *, session_cache_root: Path, max_requests: int) -> None:
        self.root = session_cache_root
        self.requests_used = 0

    def history(self, instrument: BharatStockInstrument, start: date, end: date):
        type(self).calls.append(instrument.symbol)
        self.requests_used = 1
        path = (
            self.root
            / "bharatstock-session-cache-v1"
            / f"isin={instrument.isin}"
            / "exchange=NSE"
            / f"session={end.isoformat()}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")

        class _Row:
            session = end

        class _History:
            rows = (_Row(),)

        return _History()


class _RateLimitedClient(_FakeClient):
    def history(self, instrument: BharatStockInstrument, start: date, end: date):
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
                "2026-11-13",
                "--checkpoint",
                str(tmp_path / "checkpoint.json"),
                "--delay",
                "0",
                *extra,
            ]
        )
    return code, json.loads(output.getvalue())


def test_dry_run_is_provider_free(tmp_path: Path) -> None:
    _universe(tmp_path / "store", 2)

    code, summary = _run(tmp_path, "--dry-run")

    assert code == 0
    assert summary["status"] == "DRY_RUN"
    assert summary["pending_symbols"] == 2
    assert "requests_used" in summary


def test_capture_writes_cache_and_skips_completed_on_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store", 2)
    _FakeClient.calls = []
    monkeypatch.setattr(capture, "BharatStockClient", _FakeClient)

    code, first = _run(tmp_path, "--limit", "1")

    assert code == 0
    assert first["completed"] == 1
    assert first["requests_used"] == 1
    assert first["latest_session"] == "2026-11-13"

    code, second = _run(tmp_path)

    assert code == 0
    assert second["completed"] == 1
    assert second["pending_symbols"] == 1
    assert second["remaining_pending"] == 0


def test_rate_limit_is_a_nonzero_typed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _universe(tmp_path / "store", 1)
    monkeypatch.setattr(capture, "BharatStockClient", _RateLimitedClient)

    code, summary = _run(tmp_path)

    assert code == 3
    assert summary["status"] == "RATE_LIMITED"
    assert summary["completed"] == 0
