from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _schedule(root: Path, *, closed: str | None) -> None:
    directory = root / "calendar-schedules" / "sha256"
    directory.mkdir(parents=True)
    value = {
        "as_of": "2026-10-01T00:00:00.000000Z",
        "covered_from": "2026-10-01",
        "covered_to": "2026-10-31",
        "closures": ([{"trade_date": closed, "reason": "TEST"}] if closed else []),
        "sessions": [
            {
                "trade_date": day,
                "kind": "REGULAR",
                "open_at": "2026-10-01T03:45:00.000000Z",
                "close_at": "2026-10-01T10:00:00.000000Z",
            }
            for day in (
                "2026-10-01",
                "2026-10-02",
                "2026-10-05",
                "2026-10-06",
                "2026-10-07",
                "2026-10-08",
                "2026-10-09",
                "2026-10-12",
                "2026-10-13",
                "2026-10-14",
                "2026-10-15",
                "2026-10-16",
                "2026-10-19",
                "2026-10-20",
                "2026-10-21",
                "2026-10-22",
                "2026-10-23",
                "2026-10-26",
                "2026-10-27",
                "2026-10-28",
                "2026-10-29",
                "2026-10-30",
            )
        ],
        "schema_version": "3",
        "source": "test",
        "source_release": "test",
        "timezone": "Asia/Kolkata",
    }
    (directory / f"{'a' * 64}.json").write_text(json.dumps(value))


def _run(
    script: Path, root: Path, log: Path, date: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(root),
        "SWING_LOG_DIR": str(log),
        "SWING_DATE_OVERRIDE": date,
        "SWING_DRY_RUN": "1",
    }
    return subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )


def test_runner_skips_nse_holiday(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed="2026-10-20")
    result = _run(script, tmp_path, tmp_path / "log", "2026-10-20")
    assert result.returncode == 0
    assert result.stdout.strip() == "SKIP holiday"


def test_runner_skips_duplicate_page(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed=None)
    log = tmp_path / "log"
    log.mkdir()
    (log / "scan-2026-10-23.json").write_text("{}")
    result = _run(script, tmp_path, log, "2026-10-23")
    assert result.returncode == 0
    assert result.stdout.strip() == "SKIP duplicate"
