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


def _page(path: Path, candidates: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "decision_evidence_handle": "0" * 64,
                "schema": "scan-decision-evidence-envelope@v1",
                "scan": {
                    "schema": "swing-trade-scan@v3",
                    "scan_timestamp": "2026-10-23T15:00:00.000000Z",
                    "candidates": [{"symbol": symbol} for symbol in candidates],
                },
            }
        )
    )


def _stub_doppler(path: Path, log: Path, page: Path) -> None:
    """Record calls and replay the page for the scan stage only."""
    path.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$*" >> "$STUB_LOG"\n'
        'case "$*" in\n'
        '  *" scan "*) cat "$STUB_SOURCE" ;;\n'
        "  *) echo '{}' ;;\n"
        "esac\n"
    )
    path.chmod(0o755)
    log.write_text("")


def _run_full(
    script: Path, root: Path, log: Path, doppler: Path, stub_log: Path, source: Path
) -> subprocess.CompletedProcess[str]:
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(root),
        "SWING_LOG_DIR": str(log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(script.parents[1]),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
    }
    return subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )


def test_runner_skips_analysis_without_candidates(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed=None)
    log = tmp_path / "log"
    log.mkdir()
    source = tmp_path / "scan-source.json"
    _page(source, [])
    _page(log / "scan-2026-10-23.json", [])
    doppler = tmp_path / "doppler"
    stub_log = tmp_path / "calls.log"
    _stub_doppler(doppler, stub_log, log / "scan-2026-10-23.json")
    result = _run_full(script, tmp_path, log, doppler, stub_log, source)
    assert result.returncode == 0
    assert not (log / "analysis-2026-10-23.json").exists()
    assert not (log / "research-2026-10-23.json").exists()
    assert "analysis skipped" in (log / "scan-2026-10-23.err").read_text()


def test_runner_runs_analysis_and_research_for_candidates(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed=None)
    log = tmp_path / "log"
    log.mkdir()
    source = tmp_path / "scan-source.json"
    _page(source, ["AAA", "BBB"])
    _page(log / "scan-2026-10-23.json", ["AAA", "BBB"])
    doppler = tmp_path / "doppler"
    stub_log = tmp_path / "calls.log"
    _stub_doppler(doppler, stub_log, log / "scan-2026-10-23.json")
    result = _run_full(script, tmp_path, log, doppler, stub_log, source)
    assert result.returncode == 0
    assert (log / "analysis-2026-10-23.json").exists()
    assert (log / "research-2026-10-23.json").exists()
    calls = stub_log.read_text().splitlines()
    assert any("scan" in call for call in calls)
    assert any("swing-analysis" in call for call in calls)
    research = next(call for call in calls if "research-run-current" in call)
    assert "--symbol AAA" in research
    assert "--symbol BBB" in research
