"""Source-bound checks for the fail-closed G04 repair boundary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import timedelta
from inspect import signature
from pathlib import Path
from typing import cast

import pytest
from test_current_stock_research import _NOW, _Clock
from test_setup_invalidation import _AnchoredPrices
from test_setup_screen import _service

from swing_trading_ai_assistant.market_data.bharatstock import BharatStockClient
from swing_trading_ai_assistant.market_data.signal_decisions import (
    _runtime_identity,
    evaluate_signal_decision_from_records_v2,
)
from swing_trading_ai_assistant.market_data.signal_decisions_cli import main as cli_main
from swing_trading_ai_assistant.market_data.stock_observations import (
    record_stock_observation_v1,
)


def _structure_observation(root: Path, *, later: bool = False, symbol: str = "PNB"):
    root.mkdir(mode=0o700, exist_ok=True)
    clock = _Clock()
    clock.value = _NOW + timedelta(days=int(later))
    return _service()(
        symbol,
        root,
        question="CURRENT_STRUCTURE",
        clock=clock,
        price_client=cast(
            BharatStockClient,
            _AnchoredPrices(clock.value, later=later, close=134, wick=120),
        ),
    )


@pytest.fixture
def retained_pair(tmp_path: Path) -> tuple[Path, str, str]:
    previous = _structure_observation(tmp_path)
    previous_handle = record_stock_observation_v1(tmp_path, previous)
    current = _structure_observation(tmp_path, later=True)
    current_handle = record_stock_observation_v1(tmp_path, current)
    return tmp_path, previous_handle, current_handle


def test_matching_admitted_pair_cannot_emit_an_actionable_signal(retained_pair) -> None:
    root, previous, current = retained_pair

    result = evaluate_signal_decision_from_records_v2(root, previous, current)

    assert result["schema"] == "stock-signal-decision@v2"
    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "ELIGIBILITY_EVIDENCE_UNAVAILABLE"
    assert result["previous_observation_identity_sha256"] == previous
    assert result["current_observation_identity_sha256"] == current
    assert result["eligibility"]["status"] == "UNKNOWN"
    assert (
        result["setup_evidence"]["invalidation_status"] == "NO_CONTRADICTION_OBSERVED"
    )
    assert result["setup_evidence"]["level_relation"] == "ABOVE"
    assert len(result["decision_identity_sha256"]) == 64
    public = json.dumps(result, sort_keys=True)
    assert "ACTIONABLE" not in public
    assert "entry_reference" not in public
    assert "stop_loss_reference" not in public
    assert "source_bars" not in public


def test_sdk_has_no_raw_eligibility_or_price_input_surface() -> None:
    parameters = set(signature(evaluate_signal_decision_from_records_v2).parameters)
    assert parameters == {"storage_root", "previous", "current"}
    assert (
        not {
            "eligibility",
            "setup_match",
            "invalidation_status",
            "level_relation",
            "broken_high",
            "latest_close",
        }
        & parameters
    )


def test_noncomparable_retained_pair_remains_no_trade(tmp_path: Path) -> None:
    previous = record_stock_observation_v1(tmp_path, _structure_observation(tmp_path))
    current = record_stock_observation_v1(
        tmp_path,
        _structure_observation(tmp_path, later=True, symbol="RELIANCE"),
    )

    result = evaluate_signal_decision_from_records_v2(tmp_path, previous, current)

    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "ELIGIBILITY_EVIDENCE_UNAVAILABLE"
    assert result["setup_evidence"]["continuity_status"] == "NON_COMPARABLE"


def test_real_cli_reads_only_retained_handles(retained_pair, capsys) -> None:
    root, previous, current = retained_pair

    code = cli_main(
        [
            "evaluate",
            "--storage-root",
            str(root),
            "--previous-observation",
            previous,
            "--current-observation",
            current,
            "--output",
            "json",
        ]
    )

    assert code == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert captured.err == ""
    assert result["disposition"] == "NO_TRADE"
    assert result["current_observation_identity_sha256"] == current


def test_cli_rejects_removed_raw_json_interface_before_record_access(
    tmp_path: Path, capsys
) -> None:
    code = cli_main(
        [
            "evaluate",
            "--storage-root",
            str(tmp_path),
            "--previous-observation",
            "a" * 64,
            "--current-observation",
            "b" * 64,
            "--input-json",
            str(tmp_path / "forged.json"),
            "--output",
            "json",
        ]
    )

    assert code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "request_invalid\n"
    assert not (tmp_path / "forged.json").exists()


def test_cli_hides_missing_record_root(tmp_path: Path, capsys) -> None:
    root = tmp_path / "private-root"
    code = cli_main(
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
    result = json.loads(captured.out)
    assert result == {
        "code": "OBSERVATION_RECORD_UNAVAILABLE",
        "contract_version": "stock-signal-decision@v2",
        "status": "UNAVAILABLE",
    }
    assert str(root) not in captured.out + captured.err
    assert not root.exists()


def test_runtime_identity() -> None:
    assert len(_runtime_identity()) == 64


@pytest.mark.parametrize(
    "arguments",
    (
        ("check-eligibility", "--observation", "a" * 64),
        (
            "evaluate",
            "--previous-observation",
            "a" * 64,
            "--current-observation",
            "b" * 64,
        ),
    ),
)
def test_installed_command_hides_missing_record_root(
    tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    root = tmp_path / "private-root"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = Path(sys.executable).with_name("signal-decisions")

    completed = subprocess.run(  # noqa: S603 - controlled installed command
        [
            str(command),
            arguments[0],
            "--storage-root",
            str(root),
            *arguments[1:],
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
        "code": "OBSERVATION_RECORD_UNAVAILABLE",
        "contract_version": "stock-signal-decision@v2",
        "status": "UNAVAILABLE",
    }
    assert str(root).encode() not in completed.stdout
    assert not root.exists()
