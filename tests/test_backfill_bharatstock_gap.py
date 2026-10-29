from __future__ import annotations

import base64
import importlib.util
import json
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest


def _module() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "backfill_bharatstock_gap.py"
    spec = importlib.util.spec_from_file_location("backfill_bharatstock_gap", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _calendar(
    root: Path, covered_from: str, covered_to: str, sessions: list[str]
) -> None:
    directory = root / "calendar-schedules" / "sha256"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{covered_from}.json").write_text(
        json.dumps(
            {
                "covered_from": covered_from,
                "covered_to": covered_to,
                "as_of": f"{covered_from}T00:00:00.000000Z",
                "sessions": [{"trade_date": session} for session in sessions],
            }
        )
    )


def _universe(path: Path, rows: list[tuple[str, str]]) -> None:
    csv_text = "Symbol,ISIN Code,Series\n" + "".join(
        f"{symbol},{isin},EQ\n" for isin, symbol in rows
    )
    path.write_text(
        json.dumps(
            {"nifty200_source_csv_base64": base64.b64encode(csv_text.encode()).decode()}
        )
    )


def _cache(root: Path, isin: str, session: str) -> None:
    path = (
        root
        / "bharatstock-session-cache-v1"
        / f"isin={isin}"
        / "exchange=NSE"
        / f"session={session}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")


def test_sessions_union_across_calendar_windows(tmp_path: Path) -> None:
    module = _module()
    _calendar(tmp_path, "2026-08-01", "2026-08-31", ["2026-08-03", "2026-08-04"])
    _calendar(tmp_path, "2026-09-01", "2026-09-30", ["2026-09-01", "2026-09-02"])
    assert module._sessions(tmp_path, date(2026, 8, 1), date(2026, 9, 21)) == (
        date(2026, 8, 3),
        date(2026, 8, 4),
        date(2026, 9, 1),
        date(2026, 9, 2),
    )


def test_missing_tracks_cached_sessions(tmp_path: Path) -> None:
    module = _module()
    sessions = (date(2026, 8, 3), date(2026, 8, 4))
    _cache(tmp_path, "INE000000001", "2026-08-03")
    assert module._missing(tmp_path, "INE000000001", sessions) == [date(2026, 8, 4)]


def test_dry_run_reports_pending_symbols(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _module()
    _calendar(tmp_path, "2026-08-01", "2026-09-30", ["2026-08-03"])
    universe = tmp_path / "universe.json"
    _universe(universe, [("INE000000001", "AAA"), ("INE000000002", "BBB")])
    _cache(tmp_path, "INE000000001", "2026-08-03")
    checkpoint = tmp_path / "checkpoint.json"
    code = module.main(
        [
            "--storage-root",
            str(tmp_path),
            "--universe-snapshot",
            str(universe),
            "--start",
            "2026-08-01",
            "--end",
            "2026-09-21",
            "--checkpoint",
            str(checkpoint),
            "--dry-run",
        ]
    )
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["pending_symbols"] == 1
    assert report["symbols"] == ["BBB"]
    assert report["pending_rows"] == 1
