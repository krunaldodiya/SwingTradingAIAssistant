"""Composite capture writes both stores incrementally and independently."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "capture_provider_data.sh"
STAMP = "2026-11-14"


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


def _raw_script(
    path: Path,
    *,
    status: str = "COMPLETE",
    exit_code: int = 0,
    failed: int = 0,
    remaining_pending: int = 0,
    requests_used: int = 101,
    configured_max: int = 2400,
) -> None:
    complete = status == "COMPLETE"
    payload = {
        "schema": "raw-session-capture@v1",
        "status": status,
        "members": 101,
        "completed": 101 if complete else 100,
        "skipped": 0,
        "failed": failed,
        "failed_isins": [] if failed == 0 else ["INE000000000"],
        "requests_used": requests_used,
        "requests_configured_max": configured_max,
        "requests_configured_max_basis": (
            "MAX_REQUESTS_PER_MEMBER * PER_MEMBER_ATTEMPTS * symbols_considered"
        ),
        "max_requests_per_member": 8,
        "sessions_written": 101,
        "latest_session": "2026-11-13",
        "remaining_pending": remaining_pending,
        "start": "2026-10-01",
        "end": STAMP,
        "universe_snapshot": "universe.json",
        "universe_snapshot_sha256": "f" * 64,
        "runtime": {"path": str(path), "sha256": "e" * 64, "python": "3.14.0"},
        "started_at": "2026-11-14T14:40:00+0530",
        "completed_at": "2026-11-14T14:45:00+0530",
        "symbols": {
            "S0": {"status": "FAILED" if failed else "COMPLETE", "requests_used": 1},
            "S1": {"status": "SKIPPED", "requests_used": 0},
        },
    }
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"print(json.dumps({payload!r}))\n"
        f"raise SystemExit({exit_code})\n"
    )
    path.chmod(0o755)


def _downloader(path: Path, *, fail_calls: tuple[int, ...] = ()) -> None:
    path.write_text(
        f"#!{sys.executable}\n"
        "import os\n"
        "import sys\n"
        'with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as handle:\n'
        '    handle.write(" ".join(sys.argv[1:]) + "\\n")\n'
        'count_path = os.environ["STUB_COUNT"]\n'
        "count = 0\n"
        "if os.path.exists(count_path):\n"
        '    count = int(open(count_path, encoding="utf-8").read())\n'
        "count += 1\n"
        'open(count_path, "w", encoding="utf-8").write(str(count))\n'
        f"raise SystemExit(1 if count in {set(fail_calls)!r} else 0)\n"
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


def _adjusted(store: Path, session: str) -> None:
    """Retain one adjusted dataset whose newest session is ``session``."""
    import pyarrow as pa  # noqa: PLC0415 - test-only optional dependency
    import pyarrow.parquet as pq  # noqa: PLC0415

    directory = (
        store / "adjusted_daily" / "provider=bharatstock" / f"request={'a' * 64}"
    )
    directory.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {
                "session": pa.array([date.fromisoformat(session)], type=pa.date32()),
                "symbol": ["S0"],
                "close": pa.array([100.5]),
            }
        ),
        directory / "data.parquet",
    )


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
        "SWING_DATE_OVERRIDE": STAMP,
        "SWING_CAPTURE_START": "2026-10-01",
        "SWING_CAPTURE_PYTHON": sys.executable,
        "SWING_CAPTURE_RAW_SCRIPT": str(raw),
        "SWING_CAPTURE_DOWNLOADER": str(downloader),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(root / "calls.log"),
        "STUB_COUNT": str(root / "calls.count"),
    }
    return subprocess.run(  # noqa: S603 - trusted repository test script
        [str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )


def _requires_parquet() -> None:
    __import__("pyarrow")


def _calls(root: Path) -> list[str]:
    path = root / "calls.log"
    return path.read_text().splitlines() if path.exists() else []


def _receipt(root: Path) -> dict[str, object]:
    return json.loads((root / "log" / f"capture-{STAMP}.json").read_text())


def test_capture_writes_both_stores_and_complete_receipt(tmp_path: Path) -> None:
    _requires_parquet()
    _universe(tmp_path / "store")
    raw = tmp_path / "raw.py"
    downloader = tmp_path / "downloader"
    doppler = tmp_path / "doppler"
    _raw_script(raw)
    _downloader(downloader)
    _doppler(doppler)

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 0, result.stderr
    receipt = _receipt(tmp_path)
    assert receipt["schema"] == "provider-capture@v2"
    assert receipt["status"] == "COMPLETE"
    assert receipt["sessions"]["status"] == "COMPLETE"
    assert receipt["failed"] == 0
    assert receipt["remaining_pending"] == 0
    assert receipt["latest_session"] == "2026-11-13"
    assert receipt["universe_snapshot_sha256"] == "f" * 64
    assert receipt["symbols"]["S1"]["status"] == "SKIPPED"
    assert receipt["adjusted"]["status"] == "COMPLETE"
    assert receipt["adjusted"]["batches"] == 2
    assert receipt["adjusted"]["batch_exit_codes"] == [0, 0]
    assert receipt["adjusted"]["requests_used"] == 101
    assert receipt["quota"]["raw"]["requests_used"] == 101
    assert receipt["quota"]["raw"]["requests_configured_max"] == 2400
    assert receipt["quota"]["adjusted"]["requests_configured_max"] == 4000
    assert receipt["runtime"]["raw"]["sha256"] == "e" * 64
    assert (
        receipt["runtime"]["composite"]["sha256"]
        == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    )
    assert receipt["timestamps"]["started_at"]
    assert receipt["timestamps"]["completed_at"]
    calls = _calls(tmp_path)
    assert len(calls) == 2
    assert all("--start 2026-10-01" in call for call in calls)
    assert all(f"--end {STAMP}" in call for call in calls)
    assert not any("scan" in call or "research" in call for call in calls)


def test_adjusted_current_is_skipped_without_a_downloader_call(
    tmp_path: Path,
) -> None:
    _requires_parquet()
    _universe(tmp_path / "store")
    _adjusted(tmp_path / "store", STAMP)
    raw = tmp_path / "raw.py"
    downloader = tmp_path / "downloader"
    doppler = tmp_path / "doppler"
    _raw_script(raw)
    _downloader(downloader)
    _doppler(doppler)

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 0, result.stderr
    assert _calls(tmp_path) == []
    receipt = _receipt(tmp_path)
    assert receipt["status"] == "COMPLETE"
    assert receipt["adjusted"]["status"] == "SKIPPED"
    assert receipt["adjusted"]["batches"] == 0
    assert receipt["adjusted"]["requests_used"] == 0
    assert receipt["adjusted"]["requests_configured_max"] == 0
    assert receipt["adjusted"]["newest_retained_before"] == STAMP


def test_adjusted_range_starts_after_the_newest_retained_session(
    tmp_path: Path,
) -> None:
    _requires_parquet()
    _universe(tmp_path / "store")
    _adjusted(tmp_path / "store", "2026-11-10")
    raw = tmp_path / "raw.py"
    downloader = tmp_path / "downloader"
    doppler = tmp_path / "doppler"
    _raw_script(raw)
    _downloader(downloader)
    _doppler(doppler)

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 0, result.stderr
    calls = _calls(tmp_path)
    assert len(calls) == 2
    assert all("--start 2026-11-11" in call for call in calls)
    assert all(f"--end {STAMP}" in call for call in calls)
    receipt = _receipt(tmp_path)
    assert receipt["adjusted"]["newest_retained_before"] == "2026-11-10"


def test_raw_failure_is_an_incomplete_nonzero_receipt(tmp_path: Path) -> None:
    _requires_parquet()
    _universe(tmp_path / "store")
    raw = tmp_path / "raw.py"
    downloader = tmp_path / "downloader"
    doppler = tmp_path / "doppler"
    _raw_script(raw, status="INCOMPLETE", exit_code=1, failed=1, remaining_pending=1)
    _downloader(downloader)
    _doppler(doppler)

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 1
    receipt = _receipt(tmp_path)
    assert receipt["status"] == "INCOMPLETE"
    assert receipt["failed"] == 1
    assert receipt["remaining_pending"] == 1
    assert receipt["failed_isins"] == ["INE000000000"]
    # One failing sub-step does not stop the other.
    assert receipt["adjusted"]["status"] == "COMPLETE"
    assert len(_calls(tmp_path)) == 2


def test_adjusted_failure_preserves_raw_and_fails_the_receipt(
    tmp_path: Path,
) -> None:
    _requires_parquet()
    _universe(tmp_path / "store")
    raw = tmp_path / "raw.py"
    downloader = tmp_path / "downloader"
    doppler = tmp_path / "doppler"
    _raw_script(raw)
    _downloader(downloader, fail_calls=(2,))
    _doppler(doppler)

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 1
    receipt = _receipt(tmp_path)
    assert receipt["status"] == "INCOMPLETE"
    # Captured raw sessions are still recorded and readable.
    assert receipt["sessions"]["status"] == "COMPLETE"
    assert (tmp_path / "log" / f"capture-sessions-{STAMP}.json").is_file()
    assert receipt["adjusted"]["status"] == "INCOMPLETE"
    assert receipt["adjusted"]["batch_exit_codes"] == [0, 1]
    assert receipt["adjusted"]["error"] == "ADJUSTED_BATCH_FAILED"
    # The failed batch was still submitted, so quota counts its instruments.
    assert receipt["adjusted"]["requests_used"] == 101
    assert receipt["adjusted"]["requests_configured_max"] == 4000
