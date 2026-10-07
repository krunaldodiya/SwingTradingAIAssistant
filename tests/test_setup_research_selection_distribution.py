"""Source-mode demonstrations challenge the installed verifier; hosted wheel is separate."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_linux_container_runtime import load

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def actual_reports():
    program = """
import copy, io, json, runpy, sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'src'))
demo=runpy.run_path(str(root/'examples/setup_research_selection_demo.py'))
class Output:
    def __init__(self):self.buffer=io.BytesIO()
reports={}
for scenario in ('explicit11','default100','unknown-later','negative','geometry-missing',
                 'interrupted','canonical-conflict','invalid101','selection-unavailable'):
    output,errors=Output(),io.StringIO();sys.argv=['demo','--scenario',scenario]
    with redirect_stdout(output),redirect_stderr(errors):code=demo['main']()
    reports[scenario]={'code':code,'raw':output.buffer.getvalue().hex(),
                      'errors':errors.getvalue(),'references':copy.deepcopy(demo['QUALIFICATION_REFERENCES'])}
sys.stdout.write(json.dumps(reports))
"""
    result = subprocess.run(  # noqa: S603 - fixed synthetic source-mode probe
        [sys.executable, "-c", program, str(ROOT)],
        capture_output=True,
        check=True,
        timeout=240,
    )  # noqa: S603 - fixed source-mode synthetic qualification
    return json.loads(result.stdout)


def _runner(reports):
    def run(command, **kwargs):
        value = reports[command[-2]]
        Path(command[-1]).write_text(json.dumps(value["references"]))
        return subprocess.CompletedProcess(
            command,
            value["code"],
            bytes.fromhex(value["raw"]),
            value["errors"].encode(),
        )

    return run


def test_actual_demo_and_installed_verifier_contract(
    actual_reports, monkeypatch, tmp_path
):
    verifier = load(monkeypatch)
    commands = []
    runner = _runner(actual_reports)

    def run(command, **kwargs):
        commands.append((command, kwargs))
        return runner(command, **kwargs)

    monkeypatch.setattr(verifier, "_run", run)
    result = verifier._verify_installed_selection_research(
        Path("/isolated/bin/python"), tmp_path
    )
    assert len(commands) == 9 and set(result) == set(actual_reports)
    assert result["default100"]["producer_calls"] == 100
    assert result["explicit11"]["producer_calls"] == 11
    assert result["unknown-later"]["exit"] == 1
    assert result["selection-unavailable"]["producer_calls"] == 0
    for command, kwargs in commands:
        assert command[:3] == ["/isolated/bin/python", "-I", "-c"]
        assert "sys.prefix" in command[3] and "O_NOFOLLOW" in command[3]
        assert "PYTHONPATH" not in kwargs["env"] and kwargs["cwd"] == tmp_path


@pytest.mark.parametrize(
    "fault",
    [
        "missing-member",
        "sdk-identity",
        "producer-order",
        "future-membership",
        "unknown-as-observed",
        "terminal-partial-output",
        "invalid-has-effects",
    ],
)
def test_installed_verifier_rejects_forged_or_incomplete_receipt(
    actual_reports, monkeypatch, tmp_path, fault
):
    reports = copy.deepcopy(actual_reports)
    scenario = "explicit11"
    if fault == "terminal-partial-output":
        scenario = "interrupted"
        reports[scenario]["raw"] = b"{}".hex()
    elif fault == "invalid-has-effects":
        scenario = "invalid101"
        reports[scenario]["references"]["producer_calls"] = [
            ["S000", "INTEGRATED_CURRENT_RESEARCH", False]
        ]
    elif fault == "sdk-identity":
        reports[scenario]["references"]["same_observation_sdk_identity"] = "0" * 64
    elif fault == "producer-order":
        reports[scenario]["references"]["producer_calls"].reverse()
    else:
        if fault == "future-membership":
            scenario = "default100"
        if fault == "unknown-as-observed":
            scenario = "unknown-later"
        report = json.loads(bytes.fromhex(reports[scenario]["raw"]))
        if fault == "missing-member":
            report["reports"][-1]["members"].clear()
        elif fault == "future-membership":
            report["selection"]["knowledge_basis"] = "HISTORICAL_BEFORE_RETRIEVAL"
        else:
            report["reports"][-1]["members"][0]["status"] = "MATCH"
        reports[scenario]["raw"] = (
            (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
            .encode()
            .hex()
        )
    verifier = load(monkeypatch)
    monkeypatch.setattr(verifier, "_run", _runner(reports))
    with pytest.raises(RuntimeError):
        verifier._verify_installed_selection_research(
            Path("/isolated/bin/python"), tmp_path
        )
