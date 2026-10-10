"""Public V3 CLI behavior and installed-entry-point coverage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.signal_decisions_v3_cli as cli_module


def test_v3_cli_preserves_v2_missing_record_boundary(tmp_path: Path, capsys) -> None:
    root = tmp_path / "private-root"

    code = cli_module.main(
        [
            "check-eligibility",
            "--storage-root",
            str(root),
            "--observation",
            "a" * 64,
            "--output",
            "json",
        ]
    )

    assert code == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "code": "OBSERVATION_RECORD_UNAVAILABLE",
        "contract_version": "stock-signal-decision@v2",
        "status": "UNAVAILABLE",
    }
    assert str(root) not in captured.out
    assert not root.exists()


@pytest.mark.parametrize(
    "arguments",
    (
        (
            "check-eligibility-v3",
            "--storage-root",
            "relative-root",
            "--observation",
            "a" * 64,
            "--output",
            "json",
        ),
        (
            "evaluate-v3",
            "--storage-root",
            "/absolute-root",
            "--previous-observation",
            "not-a-handle",
            "--current-observation",
            "b" * 64,
            "--output",
            "json",
        ),
    ),
)
def test_v3_cli_rejects_invalid_request_before_record_access(
    arguments: tuple[str, ...], capsys
) -> None:
    code = cli_module.main(list(arguments))

    assert code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "request_invalid\n"


def test_v3_cli_hides_missing_record_or_provider_boundary(
    tmp_path: Path, capsys
) -> None:
    root = tmp_path / "private-root"

    code = cli_module.main(
        [
            "check-eligibility-v3",
            "--storage-root",
            str(root),
            "--observation",
            "a" * 64,
            "--output",
            "json",
        ]
    )

    assert code == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "code": "OBSERVATION_OR_PROVIDER_UNAVAILABLE",
        "contract_version": "stock-signal-decision@v3",
        "status": "UNAVAILABLE",
    }
    assert str(root) not in captured.out
    assert not root.exists()


def test_v3_cli_emits_result_and_uses_versioned_exit_codes(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    monkeypatch.setattr(
        cli_module,
        "_v3_result",
        lambda _request: {"schema": "stock-eligibility@v3", "status": "ELIGIBLE"},
    )

    eligible_code = cli_module.main(
        [
            "check-eligibility-v3",
            "--storage-root",
            str(root),
            "--observation",
            "a" * 64,
            "--output",
            "json",
        ]
    )

    assert eligible_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "schema": "stock-eligibility@v3",
        "status": "ELIGIBLE",
    }
    monkeypatch.setattr(
        cli_module,
        "_v3_result",
        lambda _request: {
            "schema": "stock-signal-decision@v3",
            "disposition": "NO_TRADE",
        },
    )

    no_trade_code = cli_module.main(
        [
            "evaluate-v3",
            "--storage-root",
            str(root),
            "--previous-observation",
            "a" * 64,
            "--current-observation",
            "b" * 64,
            "--output",
            "json",
        ]
    )

    assert no_trade_code == 1
    assert json.loads(capsys.readouterr().out) == {
        "disposition": "NO_TRADE",
        "schema": "stock-signal-decision@v3",
    }


def test_installed_signal_decisions_command_hides_v3_missing_record_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private-root"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = Path(sys.executable).with_name("signal-decisions")

    completed = subprocess.run(  # noqa: S603 - controlled installed command
        [
            str(command),
            "check-eligibility-v3",
            "--storage-root",
            str(root),
            "--observation",
            "a" * 64,
            "--output",
            "json",
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
    )

    assert completed.returncode == 1
    assert completed.stderr == b""
    assert json.loads(completed.stdout) == {
        "code": "OBSERVATION_OR_PROVIDER_UNAVAILABLE",
        "contract_version": "stock-signal-decision@v3",
        "status": "UNAVAILABLE",
    }
    assert str(root).encode() not in completed.stdout
    assert not root.exists()
