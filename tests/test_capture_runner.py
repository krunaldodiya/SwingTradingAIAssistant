"""Composite capture writes both stores independently of research/calendar."""

from __future__ import annotations

import base64
import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "capture_provider_data.sh"


def _universe(root: Path, count: int = 101) -> None:
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


def _raw_script(path: Path, *, status: str = "COMPLETE", exit_code: int = 0) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({\n"
        f'  "status": {status!r},\n'
        '  "members": 101,\n'
        '  "completed": 101,\n'
        '  "failed": 0,\n'
        '  "requests_used": 101,\n'
        '  "sessions_written": 101,\n'
        '  "latest_session": "2026-11-13",\n'
        '  "remaining_pending": 0 if ' + repr(status) + ' == "COMPLETE" else 101,\n'
        "}))\n"
        f"raise SystemExit({exit_code})\n"
    )
    path.chmod(0o755)


def _downloader(path: Path) -> None:
    path.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$STUB_LOG"\nexit 0\n')
    path.chmod(0o755)


def _doppler(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env bash\n"
        'while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do shift; done\n'
        "shift\n"
        'exec "$@"\n'
    )
    path.chmod(0o755)


def _run(
    root: Path,
    raw: Path,
    downloader: Path,
    doppler: Path,
) -> subprocess.CompletedProcess[str]:
    env = os.environ | {
        "SWING_REPO": str(SCRIPT.parents[1]),
        "SWING_STORAGE_ROOT": str(root / "store"),
        "SWING_LOG_DIR": str(root / "log"),
        "SWING_DATE_OVERRIDE": "2026-11-14",
        "SWING_CAPTURE_START": "2026-10-01",
        "SWING_CAPTURE_PYTHON": sys.executable,
        "SWING_CAPTURE_RAW_SCRIPT": str(raw),
        "SWING_CAPTURE_DOWNLOADER": str(downloader),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(root / "calls.log"),
    }
    return subprocess.run(  # noqa: S603 - trusted repository test script
        [str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )


def test_capture_writes_both_stores_and_complete_receipt(tmp_path: Path) -> None:
    _universe(tmp_path / "store")
    raw = tmp_path / "raw.py"
    downloader = tmp_path / "downloader"
    doppler = tmp_path / "doppler"
    _raw_script(raw)
    _downloader(downloader)
    _doppler(doppler)

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 0, result.stderr
    receipt = json.loads((tmp_path / "log" / "capture-2026-11-14.json").read_text())
    assert receipt["status"] == "COMPLETE"
    assert receipt["sessions"]["status"] == "COMPLETE"
    assert receipt["latest_session"] == "2026-11-13"
    assert receipt["adjusted"]["batch_exit_codes"] == [0, 0]
    assert receipt["requests_used"] == 103
    calls = (tmp_path / "calls.log").read_text().splitlines()
    assert len(calls) == 2
    assert all("--start 2026-10-01" in call for call in calls)
    assert all("--end 2026-11-14" in call for call in calls)
    assert not any("scan" in call or "research" in call for call in calls)


def test_capture_incomplete_receipt_still_runs_adjusted_stage(tmp_path: Path) -> None:
    _universe(tmp_path / "store")
    raw = tmp_path / "raw.py"
    downloader = tmp_path / "downloader"
    doppler = tmp_path / "doppler"
    _raw_script(raw, status="INCOMPLETE", exit_code=1)
    _downloader(downloader)
    _doppler(doppler)

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 1
    receipt = json.loads((tmp_path / "log" / "capture-2026-11-14.json").read_text())
    assert receipt["status"] == "INCOMPLETE"
    assert len((tmp_path / "calls.log").read_text().splitlines()) == 2
