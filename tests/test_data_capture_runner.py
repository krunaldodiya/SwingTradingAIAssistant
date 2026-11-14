"""Independent provider capture runs before research with its own failure domain."""

from __future__ import annotations

import base64
import csv
import io
import json
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "capture_provider_data.sh"


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


def _downloader(path: Path, exit_code: int = 0) -> None:
    path.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$*" >> "$STUB_LOG"\n'
        f"exit {exit_code}\n"
    )
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
    tmp_path: Path, downloader: Path, doppler: Path
) -> subprocess.CompletedProcess[str]:
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(tmp_path / "store"),
        "SWING_LOG_DIR": str(tmp_path / "log"),
        "SWING_DATE_OVERRIDE": "2026-11-14",
        "SWING_CAPTURE_DOWNLOADER": str(downloader),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(tmp_path / "calls.log"),
    }
    return subprocess.run(  # noqa: S603 - trusted repository test script
        [str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )


def test_capture_runs_independently_in_bounded_batches(tmp_path: Path) -> None:
    _universe(tmp_path / "store", 101)
    downloader = tmp_path / "downloader"
    doppler = tmp_path / "doppler"
    _downloader(downloader)
    _doppler(doppler)

    result = _run(tmp_path, downloader, doppler)

    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "calls.log").read_text().splitlines()
    assert len(calls) == 2
    assert all("--storage-root" in call for call in calls)
    assert "--start 2026-09-30" in calls[0]
    assert "--end 2026-11-14" in calls[0]
    assert not any("scan" in call or "research" in call for call in calls)


def test_capture_failure_is_nonzero_and_still_independent(tmp_path: Path) -> None:
    _universe(tmp_path / "store", 2)
    downloader = tmp_path / "downloader"
    doppler = tmp_path / "doppler"
    _downloader(downloader, 1)
    _doppler(doppler)

    result = _run(tmp_path, downloader, doppler)

    assert result.returncode == 1
    assert (tmp_path / "log" / "capture-2026-11-14.err").exists()
