from __future__ import annotations

import json
import os
import subprocess
import sys
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
    ledger = root / "ledger"
    (ledger / "entries" / "2026").mkdir(parents=True, exist_ok=True)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(root),
        "SWING_LOG_DIR": str(log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(script.parents[1]),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_LEDGER_ROOT": str(ledger),
        "SWING_RCLONE_BIN": "/bin/true",
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


def test_runner_scopes_doppler_explicitly(tmp_path: Path) -> None:
    """Credentials must be injected by an explicit project/config scope.

    The runner must not depend on a global Doppler configuration: an unscoped
    ``doppler run`` silently produces a credential-free scan, which the provider
    rejects per symbol and which then looks like a no-candidate market result.
    """
    script = Path(__file__).parents[1] / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed=None)
    log = tmp_path / "log"
    log.mkdir()
    source = tmp_path / "scan-source.json"
    _page(source, [])
    doppler = tmp_path / "doppler"
    stub_log = tmp_path / "calls.log"
    _stub_doppler(doppler, stub_log, source)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(tmp_path),
        "SWING_LOG_DIR": str(log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_REPO": str(script.parents[1]),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_DOPPLER_PROJECT": "test-project",
        "SWING_DOPPLER_CONFIG": "test-config",
        "SWING_LEDGER_ROOT": str(tmp_path / "ledger"),
        "SWING_RCLONE_BIN": "/bin/true",
    }
    (tmp_path / "ledger" / "entries" / "2026").mkdir(parents=True)
    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    calls = stub_log.read_text().splitlines()
    scan_call = next(call for call in calls if "scan" in call)
    assert "--project test-project --config test-config" in scan_call


def test_runner_writes_diary_pages_under_storage_root(tmp_path: Path) -> None:
    """The default diary directory must live inside the private evidence store."""
    script = Path(__file__).parents[1] / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed=None)
    source = tmp_path / "scan-source.json"
    _page(source, [])
    doppler = tmp_path / "doppler"
    stub_log = tmp_path / "calls.log"
    _stub_doppler(doppler, stub_log, source)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(tmp_path),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_REPO": str(script.parents[1]),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_LEDGER_ROOT": str(tmp_path / "ledger"),
        "SWING_RCLONE_BIN": "/bin/true",
    }
    (tmp_path / "ledger" / "entries" / "2026").mkdir(parents=True)
    env.pop("SWING_LOG_DIR", None)
    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert (tmp_path / "daily-scan" / "scan-2026-10-23.json").exists()


def _ledger_stub_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Build a stub repo whose ledger writer records its invocation."""
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    real_script = Path(__file__).parents[1] / "scripts" / "daily_after_close_scan.sh"
    (scripts / "daily_after_close_scan.sh").write_text(real_script.read_text())
    (scripts / "daily_after_close_scan.sh").chmod(0o755)
    venv_bin = repo / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(sys.executable)
    stub = scripts / "write_scan_ledger_entry.py"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "with open(os.environ['LEDGER_CALL_LOG'], 'a') as handle:\n"
        "    handle.write(' '.join(sys.argv[1:]) + '\\n')\n"
    )
    return repo, stub


def test_runner_writes_ledger_entry_for_real_pass(tmp_path: Path) -> None:
    """A real pass must reach the ledger, not just the diary directory."""
    repo, _ = _ledger_stub_repo(tmp_path)
    script = repo / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed=None)
    log = tmp_path / "log"
    log.mkdir()
    source = tmp_path / "scan-source.json"
    _page(source, ["AAA"])
    doppler = tmp_path / "doppler"
    stub_log = tmp_path / "calls.log"
    _stub_doppler(doppler, stub_log, source)
    ledger_calls = tmp_path / "ledger.log"
    ledger_root = tmp_path / "ledger"
    (ledger_root / "entries" / "2026").mkdir(parents=True)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(tmp_path),
        "SWING_LOG_DIR": str(log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(repo),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_LEDGER_ROOT": str(ledger_root),
        # No real rclone on CI, and the sync stage is fatal by design.
        "SWING_RCLONE_BIN": "/bin/true",
        "LEDGER_CALL_LOG": str(ledger_calls),
    }
    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    calls = ledger_calls.read_text().splitlines()
    assert len(calls) == 1
    assert "--ledger-root" in calls[0]
    assert "--status unconfirmed" in calls[0]
    assert "--analysis-json" in calls[0]
    assert "--research-json" in calls[0]


def test_runner_fails_without_configured_ledger_root(tmp_path: Path) -> None:
    """A scheduled pass without a ledger root has not met the delivery gate."""
    script = Path(__file__).parents[1] / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed=None)
    log = tmp_path / "log"
    log.mkdir()
    source = tmp_path / "scan-source.json"
    _page(source, ["AAA"])
    doppler = tmp_path / "doppler"
    stub_log = tmp_path / "calls.log"
    _stub_doppler(doppler, stub_log, source)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(tmp_path),
        "SWING_LOG_DIR": str(log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(Path(__file__).parents[1]),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
    }
    env.pop("SWING_LEDGER_ROOT", None)
    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 1
    err = (log / "scan-2026-10-23.err").read_text()
    assert "ledger failed: SWING_LEDGER_ROOT is not set" in err


def test_runner_syncs_ledger_off_device_after_write(tmp_path: Path) -> None:
    """A pass must push its entry to the remote, not wait for the hourly timer."""
    repo, _ = _ledger_stub_repo(tmp_path)
    script = repo / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed=None)
    log = tmp_path / "log"
    log.mkdir()
    source = tmp_path / "scan-source.json"
    _page(source, ["AAA"])
    doppler = tmp_path / "doppler"
    stub_log = tmp_path / "calls.log"
    _stub_doppler(doppler, stub_log, source)
    rclone = tmp_path / "rclone"
    rclone_log = tmp_path / "rclone.log"
    rclone.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$RCLONE_LOG"\n')
    rclone.chmod(0o755)
    ledger_root = tmp_path / "ledger"
    (ledger_root / "entries" / "2026").mkdir(parents=True)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(tmp_path),
        "SWING_LOG_DIR": str(log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(repo),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_LEDGER_ROOT": str(ledger_root),
        "LEDGER_CALL_LOG": str(tmp_path / "ledger.log"),
        "SWING_RCLONE_BIN": str(rclone),
        "SWING_SYNC_LOG_DIR": str(tmp_path),
        "RCLONE_LOG": str(rclone_log),
    }
    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    calls = rclone_log.read_text().splitlines()
    assert len(calls) == 1
    assert "copy" in calls[0]
    assert str(ledger_root) in calls[0]
    assert "gdrive:SwingResearchLedger" in calls[0]
    assert "--update" in calls[0]


def test_runner_fails_when_ledger_write_fails(tmp_path: Path) -> None:
    """A pass that cannot record itself must not report success."""
    repo, stub = _ledger_stub_repo(tmp_path)
    stub.write_text(
        "import sys\nprint('ledger_entry_failed: no space', file=sys.stderr)\nsys.exit(2)\n"
    )
    script = repo / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed=None)
    log = tmp_path / "log"
    log.mkdir()
    source = tmp_path / "scan-source.json"
    _page(source, ["AAA"])
    doppler = tmp_path / "doppler"
    stub_log = tmp_path / "calls.log"
    _stub_doppler(doppler, stub_log, source)
    ledger_root = tmp_path / "ledger"
    (ledger_root / "entries" / "2026").mkdir(parents=True)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(tmp_path),
        "SWING_LOG_DIR": str(log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(repo),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_LEDGER_ROOT": str(ledger_root),
        "SWING_RCLONE_BIN": "/bin/true",
        "LEDGER_CALL_LOG": str(tmp_path / "ledger.log"),
    }
    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
    assert "ledger_exit=2" in (log / "scan-2026-10-23.err").read_text()


def test_runner_fails_when_off_device_sync_fails(tmp_path: Path) -> None:
    """A ledger that never left the device is still single copy."""
    repo, _ = _ledger_stub_repo(tmp_path)
    script = repo / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed=None)
    log = tmp_path / "log"
    log.mkdir()
    source = tmp_path / "scan-source.json"
    _page(source, ["AAA"])
    doppler = tmp_path / "doppler"
    stub_log = tmp_path / "calls.log"
    _stub_doppler(doppler, stub_log, source)
    rclone = tmp_path / "rclone-fail"
    rclone.write_text("#!/usr/bin/env bash\nexit 7\n")
    rclone.chmod(0o755)
    ledger_root = tmp_path / "ledger"
    (ledger_root / "entries" / "2026").mkdir(parents=True)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(tmp_path),
        "SWING_LOG_DIR": str(log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(repo),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_LEDGER_ROOT": str(ledger_root),
        "SWING_RCLONE_BIN": str(rclone),
        "SWING_SYNC_LOG_DIR": str(tmp_path),
        "LEDGER_CALL_LOG": str(tmp_path / "ledger.log"),
    }
    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 7
    assert "ledger_sync_exit=7" in (log / "scan-2026-10-23.err").read_text()
