from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest


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
        **_capture_env(root, log),
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


def _capture_receipt(**overrides: object) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema": "provider-capture@v2",
        "status": "COMPLETE",
        "failed": 0,
        "remaining_pending": 0,
        "sessions": {"status": "COMPLETE", "remaining_pending": 0},
        "adjusted": {"status": "COMPLETE"},
    }
    receipt.update(overrides)
    return receipt


def _capture_env(
    tmp_path: Path,
    log: Path,
    *,
    receipt: dict[str, object] | None = None,
    capture_exit: int = 0,
) -> dict[str, str]:
    """Stub the capture preflight: log the call, write a receipt, exit typed."""
    source = tmp_path / "capture-source.json"
    source.write_text(json.dumps(_capture_receipt() if receipt is None else receipt))
    calls = tmp_path / "capture-calls.log"
    stub = tmp_path / "capture-stub"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$*" >> "$CAPTURE_STUB_LOG"\n'
        'cp "$CAPTURE_STUB_SOURCE" "$CAPTURE_STUB_RECEIPT" 2>/dev/null || true\n'
        f"exit {capture_exit}\n"
    )
    stub.chmod(0o755)
    return {
        "SWING_CAPTURE_COMMAND": str(stub),
        "SWING_CAPTURE_SERVICE": "swing-data-capture-test.service",
        "SWING_CAPTURE_SERVICE_STATE_COMMAND": "printf 'inactive\\n'",
        "SWING_CAPTURE_WAIT_SECONDS": "0",
        "SWING_CAPTURE_POLL_SECONDS": "0",
        "CAPTURE_STUB_LOG": str(calls),
        "CAPTURE_STUB_SOURCE": str(source),
        "CAPTURE_STUB_RECEIPT": str(log / "capture-2026-10-23.json"),
    }


def _capture_calls(tmp_path: Path) -> list[str]:
    path = tmp_path / "capture-calls.log"
    return path.read_text().splitlines() if path.exists() else []


def _run_full(
    script: Path, root: Path, log: Path, doppler: Path, stub_log: Path, source: Path
) -> subprocess.CompletedProcess[str]:
    ledger = root / "ledger"
    (ledger / "entries" / "2026").mkdir(parents=True, exist_ok=True)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(root),
        "SWING_LOG_DIR": str(log),
        **_capture_env(root, log),
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
        **_capture_env(tmp_path, log),
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
        **_capture_env(tmp_path, tmp_path / "daily-scan"),
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
    # The coverage stage runs last; stub it so these tests stay about wiring.
    coverage = scripts / "check_ledger_coverage.py"
    coverage.write_text("#!/usr/bin/env python3\nraise SystemExit(0)\n")
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
        **_capture_env(tmp_path, log),
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
        **_capture_env(tmp_path, log),
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
        **_capture_env(tmp_path, log),
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
        **_capture_env(tmp_path, log),
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
        **_capture_env(tmp_path, log),
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


def test_runner_writes_breadth_trend_artifact(tmp_path: Path) -> None:
    """The scheduled runner writes parseable output without accepting raw pages."""
    script = Path(__file__).parents[1] / "scripts" / "daily_after_close_scan.sh"
    log = tmp_path / "log"
    log.mkdir()
    source = tmp_path / "scan-source.json"
    _page(source, ["AAA"])
    doppler = tmp_path / "doppler"
    stub_log = tmp_path / "calls.log"
    _stub_doppler(doppler, stub_log, source)
    ledger = tmp_path / "ledger"
    (ledger / "entries" / "2026").mkdir(parents=True)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(tmp_path),
        "SWING_LOG_DIR": str(log),
        **_capture_env(tmp_path, log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(script.parents[1]),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_LEDGER_ROOT": str(ledger),
        "SWING_RCLONE_BIN": "/bin/true",
    }
    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    report = json.loads((log / "breadth-2026-10-23.json").read_text())
    assert report["schema"] == "market-breadth-trend@v1"
    assert report["sessions_observed"] == 0


def test_scan_failure_discards_the_page(tmp_path: Path) -> None:
    """A failed scan must not leave a page a later reader could trust."""
    script = Path(__file__).parents[1] / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed=None)
    log = tmp_path / "log"
    log.mkdir()
    doppler = tmp_path / "doppler-fail"
    doppler.write_text(
        "#!/usr/bin/env bash\n"
        'case "$*" in\n'
        '  *" scan "*) echo "{"partial":" ; exit 1 ;;\n'
        "  *) echo '{}' ;;\n"
        "esac\n"
    )
    doppler.chmod(0o755)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(tmp_path),
        "SWING_LOG_DIR": str(log),
        **_capture_env(tmp_path, log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_REPO": str(script.parents[1]),
        "DOPPLER_BIN": str(doppler),
        "SWING_LEDGER_ROOT": str(tmp_path / "ledger"),
        "SWING_RCLONE_BIN": "/bin/true",
    }

    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 1
    assert not (log / "scan-2026-10-23.json").exists()
    err = (log / "scan-2026-10-23.err").read_text()
    assert "exit_code=1" in err


def test_coverage_gap_fails_the_pass(tmp_path: Path) -> None:
    """A pass with no ledger entry for this session is not delivered."""
    repo, _ = _ledger_stub_repo(tmp_path)
    (repo / "scripts" / "check_ledger_coverage.py").write_text(
        "#!/usr/bin/env python3\nraise SystemExit(1)\n"
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
    ledger = tmp_path / "ledger"
    (ledger / "entries" / "2026").mkdir(parents=True)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(tmp_path),
        "SWING_LOG_DIR": str(log),
        **_capture_env(tmp_path, log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(repo),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_LEDGER_ROOT": str(ledger),
        "SWING_RCLONE_BIN": "/bin/true",
        "LEDGER_CALL_LOG": str(tmp_path / "ledger.log"),
    }

    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 1
    err = (log / "scan-2026-10-23.err").read_text()
    assert "coverage_exit=1" in err
    assert "coverage gap for 2026-10-23" in err


def test_coverage_check_targets_the_current_page_handle(tmp_path: Path) -> None:
    """The gate must check this page, not a date window that may exclude it."""
    repo, _ = _ledger_stub_repo(tmp_path)
    coverage_log = tmp_path / "coverage.log"
    (repo / "scripts" / "check_ledger_coverage.py").write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "with open(os.environ['COVERAGE_LOG'], 'w') as handle:\n"
        "    handle.write(' '.join(sys.argv[1:]))\n"
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
    ledger = tmp_path / "ledger"
    (ledger / "entries" / "2026").mkdir(parents=True)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(tmp_path),
        "SWING_LOG_DIR": str(log),
        **_capture_env(tmp_path, log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(repo),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_LEDGER_ROOT": str(ledger),
        "SWING_RCLONE_BIN": "/bin/true",
        "LEDGER_CALL_LOG": str(tmp_path / "ledger.log"),
        "COVERAGE_LOG": str(coverage_log),
    }

    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    args = coverage_log.read_text()
    assert f"--handle {'0' * 64}" in args
    assert "--since" not in args


def test_scan_timeout_discards_the_page_and_reports_124(tmp_path: Path) -> None:
    """A stalled provider call must fail fast, not eat the whole pass."""
    script = Path(__file__).parents[1] / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed=None)
    log = tmp_path / "log"
    log.mkdir()
    doppler = tmp_path / "doppler-slow"
    doppler.write_text("#!/usr/bin/env bash\nsleep 30\n")
    doppler.chmod(0o755)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(tmp_path),
        "SWING_LOG_DIR": str(log),
        **_capture_env(tmp_path, log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_REPO": str(script.parents[1]),
        "DOPPLER_BIN": str(doppler),
        "SWING_LEDGER_ROOT": str(tmp_path / "ledger"),
        "SWING_RCLONE_BIN": "/bin/true",
        "SWING_SCAN_TIMEOUT": "1",
    }

    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False, timeout=60
    )

    assert result.returncode == 124
    assert not (log / "scan-2026-10-23.json").exists()
    err = (log / "scan-2026-10-23.err").read_text()
    assert "exit_code=124" in err
    assert "scan exceeded 1s; page discarded" in err


def test_runner_reuses_complete_capture_receipt(tmp_path: Path) -> None:
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
    (log / "capture-2026-10-23.json").write_text(json.dumps(_capture_receipt()))

    result = _run_full(script, tmp_path, log, doppler, stub_log, source)

    assert result.returncode == 0
    # A complete receipt skips the preflight capture entirely.
    assert _capture_calls(tmp_path) == []
    scan_call = next(
        call for call in stub_log.read_text().splitlines() if " scan " in call
    )
    assert "--reuse-captured-terminal" in scan_call


def _preflight_fixture(
    tmp_path: Path, *, candidates: list[str] | None = None
) -> tuple[Path, Path, Path, Path, Path, Path]:
    script = Path(__file__).parents[1] / "scripts" / "daily_after_close_scan.sh"
    _schedule(tmp_path, closed=None)
    log = tmp_path / "log"
    log.mkdir(exist_ok=True)
    source = tmp_path / "scan-source.json"
    _page(source, [] if candidates is None else candidates)
    doppler = tmp_path / "doppler"
    stub_log = tmp_path / "calls.log"
    _stub_doppler(doppler, stub_log, source)
    return script, log, source, doppler, stub_log, tmp_path


def test_runner_runs_capture_before_scan_when_receipt_missing(
    tmp_path: Path,
) -> None:
    script, log, source, doppler, stub_log, root = _preflight_fixture(tmp_path)

    result = _run_full(script, root, log, doppler, stub_log, source)

    assert result.returncode == 0
    assert len(_capture_calls(root)) == 1
    scan_call = next(
        call for call in stub_log.read_text().splitlines() if " scan " in call
    )
    assert "--reuse-captured-terminal" in scan_call
    assert "CAPTURE_INCOMPLETE" not in (log / "scan-2026-10-23.err").read_text()


def test_runner_records_capture_incomplete_and_does_not_reuse(tmp_path: Path) -> None:
    script, log, source, doppler, stub_log, root = _preflight_fixture(tmp_path)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(root),
        "SWING_LOG_DIR": str(log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(script.parents[1]),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_LEDGER_ROOT": str(root / "ledger"),
        "SWING_RCLONE_BIN": "/bin/true",
        **_capture_env(
            root,
            log,
            receipt=_capture_receipt(
                status="INCOMPLETE",
                failed=1,
                remaining_pending=1,
                sessions={"status": "INCOMPLETE", "remaining_pending": 1},
            ),
            capture_exit=1,
        ),
    }
    (root / "ledger" / "entries" / "2026").mkdir(parents=True, exist_ok=True)

    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0
    assert len(_capture_calls(root)) == 1
    scan_call = next(
        call for call in stub_log.read_text().splitlines() if " scan " in call
    )
    assert "--reuse-captured-terminal" not in scan_call
    assert "CAPTURE_INCOMPLETE" in (log / "scan-2026-10-23.err").read_text()


def test_runner_waits_for_an_active_head_start_without_duplicating_it(
    tmp_path: Path,
) -> None:
    script, log, source, doppler, stub_log, root = _preflight_fixture(tmp_path)
    status = root / "capture-status"
    status.write_text(
        "#!/usr/bin/env bash\n"
        'count=0; [ -f "$STATUS_COUNT" ] && count=$(cat "$STATUS_COUNT")\n'
        'count=$((count + 1)); echo "$count" > "$STATUS_COUNT"\n'
        'if [ "$count" -lt 3 ]; then echo activating; exit 0; fi\n'
        'cp "$CAPTURE_STUB_SOURCE" "$CAPTURE_STUB_RECEIPT"\n'
        "echo inactive\n"
    )
    status.chmod(0o755)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(root),
        "SWING_LOG_DIR": str(log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(script.parents[1]),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_LEDGER_ROOT": str(root / "ledger"),
        "SWING_RCLONE_BIN": "/bin/true",
        **(
            _capture_env(root, log)
            | {
                "SWING_CAPTURE_SERVICE_STATE_COMMAND": str(status),
                "SWING_CAPTURE_WAIT_SECONDS": "30",
                "SWING_CAPTURE_POLL_SECONDS": "0",
                "STATUS_COUNT": str(root / "status.count"),
            }
        ),
    }
    (root / "ledger" / "entries" / "2026").mkdir(parents=True, exist_ok=True)

    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0
    # The runner waited instead of launching a duplicate capture.
    assert _capture_calls(root) == []
    assert int((root / "status.count").read_text().strip()) >= 3
    preflight = (log / "capture-preflight-2026-10-23.log").read_text()
    assert "waiting for swing-data-capture-test.service" in preflight
    assert "completed the capture" in preflight
    scan_call = next(
        call for call in stub_log.read_text().splitlines() if " scan " in call
    )
    assert "--reuse-captured-terminal" in scan_call


def test_runner_never_duplicates_a_head_start_that_outlasts_the_wait(
    tmp_path: Path,
) -> None:
    script, log, source, doppler, stub_log, root = _preflight_fixture(tmp_path)
    active = root / "capture-active"
    active.write_text("#!/usr/bin/env bash\necho deactivating\n")
    active.chmod(0o755)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(root),
        "SWING_LOG_DIR": str(log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(script.parents[1]),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_LEDGER_ROOT": str(root / "ledger"),
        "SWING_RCLONE_BIN": "/bin/true",
        **(
            _capture_env(root, log)
            | {
                "SWING_CAPTURE_SERVICE_STATE_COMMAND": str(active),
                "SWING_CAPTURE_WAIT_SECONDS": "0",
                "SWING_CAPTURE_POLL_SECONDS": "0",
            }
        ),
    }
    (root / "ledger" / "entries" / "2026").mkdir(parents=True, exist_ok=True)

    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0
    assert _capture_calls(root) == []
    preflight = (log / "capture-preflight-2026-10-23.log").read_text()
    assert "not starting a duplicate" in preflight
    scan_call = next(
        call for call in stub_log.read_text().splitlines() if " scan " in call
    )
    assert "--reuse-captured-terminal" not in scan_call
    assert "CAPTURE_INCOMPLETE" in (log / "scan-2026-10-23.err").read_text()


def test_preflight_budget_fits_the_scan_service_timeout() -> None:
    """Wait + preflight capture + scan must stay inside the service deadline."""
    root = Path(__file__).parents[1]
    script = (root / "scripts" / "daily_after_close_scan.sh").read_text()
    unit = (root / "scripts" / "systemd" / "swing-daily-scan.service").read_text()

    def default(name: str) -> int:
        match = re.search(rf"\$\{{{name}:-([0-9]+)\}}", script)
        assert match is not None, name
        return int(match.group(1))

    wait = default("SWING_CAPTURE_WAIT_SECONDS")
    capture = default("SWING_CAPTURE_TIMEOUT")
    scan = default("SWING_SCAN_TIMEOUT")
    service = re.search(r"^TimeoutStartSec=([0-9]+)$", unit, re.M)
    assert service is not None
    assert (wait, capture, scan) == (600, 1200, 1200)
    assert wait + capture + scan <= int(service.group(1))


def test_timed_out_preflight_does_not_leave_a_child_process(
    tmp_path: Path,
) -> None:
    script, log, source, doppler, stub_log, root = _preflight_fixture(tmp_path)
    orphan = root / "orphan.pid"
    stub = root / "capture-orphan"
    stub.write_text(
        '#!/usr/bin/env bash\nsleep 60 &\necho $! > "$ORPHAN_PID"\nsleep 60\n'
    )
    stub.chmod(0o755)
    env = os.environ | {
        "SWING_STORAGE_ROOT": str(root),
        "SWING_LOG_DIR": str(log),
        "SWING_DATE_OVERRIDE": "2026-10-23",
        "SWING_ALLOW_OVERWRITE": "1",
        "SWING_REPO": str(script.parents[1]),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(stub_log),
        "STUB_SOURCE": str(source),
        "SWING_LEDGER_ROOT": str(root / "ledger"),
        "SWING_RCLONE_BIN": "/bin/true",
        "SWING_CAPTURE_COMMAND": str(stub),
        "SWING_CAPTURE_SERVICE_STATE_COMMAND": "printf 'inactive\\n'",
        "SWING_CAPTURE_WAIT_SECONDS": "0",
        "SWING_CAPTURE_POLL_SECONDS": "0",
        "SWING_CAPTURE_TIMEOUT": "1",
        "SWING_CAPTURE_KILL_AFTER": "1",
        "ORPHAN_PID": str(orphan),
    }
    (root / "ledger" / "entries" / "2026").mkdir(parents=True, exist_ok=True)

    result = subprocess.run(  # noqa: S603 - trusted repository test script
        [str(script)], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0
    pid = int(orphan.read_text().strip())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("a timed-out preflight left its child process running")
    scan_call = next(
        call for call in stub_log.read_text().splitlines() if " scan " in call
    )
    assert "--reuse-captured-terminal" not in scan_call
