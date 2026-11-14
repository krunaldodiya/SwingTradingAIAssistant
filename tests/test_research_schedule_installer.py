"""The installer check treats the PRD-optional capture head start as optional."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "install_research_schedule.sh"
_UNITS = (
    "swing-data-capture.service",
    "swing-data-capture.timer",
    "swing-daily-scan.service",
    "swing-daily-scan.timer",
    "research-ledger-sync.service",
    "research-ledger-sync.timer",
)


def _env(
    tmp_path: Path,
    *,
    capture_enabled: bool,
    scan_enabled: bool = True,
    sync_enabled: bool = True,
    missing: str | None = None,
) -> dict[str, str]:
    units = tmp_path / "config" / "systemd" / "user"
    units.mkdir(parents=True, exist_ok=True)
    for name in _UNITS:
        if name != missing:
            (units / name).write_text("[Unit]\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    systemctl = bin_dir / "systemctl"
    systemctl.write_text(
        "#!/usr/bin/env bash\n"
        'case "$*" in\n'
        '  *"is-enabled swing-data-capture.timer"*)\n'
        f"    exit {0 if capture_enabled else 1} ;;\n"
        '  *"is-enabled swing-daily-scan.timer"*)\n'
        f"    exit {0 if scan_enabled else 1} ;;\n"
        '  *"is-enabled research-ledger-sync.timer"*)\n'
        f"    exit {0 if sync_enabled else 1} ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    systemctl.chmod(0o755)
    return os.environ | {
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
    }


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - trusted repository test script
        [str(SCRIPT), "--check"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_accepts_a_disabled_optional_capture_timer(tmp_path: Path) -> None:
    result = _run(_env(tmp_path, capture_enabled=False))

    assert result.returncode == 0, result.stderr
    assert "optional: swing-data-capture.timer" in result.stdout
    assert "enabled: swing-daily-scan.timer" in result.stdout


def test_check_still_fails_without_the_required_scan_timer(tmp_path: Path) -> None:
    result = _run(_env(tmp_path, capture_enabled=True, scan_enabled=False))

    assert result.returncode == 1
    assert "MISSING: swing-daily-scan.timer" in result.stderr


def test_check_requires_the_capture_timer_file_but_not_its_enablement(
    tmp_path: Path,
) -> None:
    missing = _run(
        _env(
            tmp_path,
            capture_enabled=False,
            missing="swing-data-capture.timer",
        )
    )

    assert missing.returncode == 1
    assert "MISSING: swing-data-capture.timer" in missing.stderr

    disabled = _run(_env(tmp_path, capture_enabled=False))

    assert disabled.returncode == 0
