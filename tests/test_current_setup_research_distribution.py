"""Actual public CLI scenarios and fail-closed installed acceptance."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_linux_container_runtime import load

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def actual_reports():
    # Isolate the fixed clock and audit hooks from all other fixture modules.
    program = """
import copy, io, json, runpy, sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / 'src'))
demo = runpy.run_path(str(root / 'examples/current_setup_research_demo.py'))
class Output:
    def __init__(self):
        self.buffer = io.BytesIO()
results = {}
for scenario in ('positive', 'negative', 'insufficient', 'geometry-missing',
                 'comparison-missing', 'interrupted', 'corrupt', 'invalid-request'):
    output, errors = Output(), io.StringIO()
    sys.argv = ['demo', '--scenario', scenario]
    with redirect_stdout(output), redirect_stderr(errors):
        code = demo['main']()
    results[scenario] = {'raw': output.buffer.getvalue().hex(), 'code': code,
                         'references': copy.deepcopy(demo['QUALIFICATION_REFERENCES']),
                         'errors': errors.getvalue()}
sys.stdout.write(json.dumps(results))
"""
    result = subprocess.run(  # noqa: S603 - fixed producer, closed synthetic scenarios
        [sys.executable, "-c", program, str(ROOT)],
        capture_output=True,
        check=True,
        timeout=180,
    )
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


def test_real_cli_and_installed_acceptance(actual_reports, monkeypatch, tmp_path):
    verifier = load(monkeypatch)
    commands = []
    original = _runner(actual_reports)

    def run(command, **kwargs):
        commands.append((command, kwargs))
        return original(command, **kwargs)

    monkeypatch.setattr(verifier, "_run", run)
    outcomes = verifier._verify_installed_setup_research(
        Path("/isolated/bin/python"), tmp_path
    )
    assert len(commands) == 8 and set(outcomes) == set(actual_reports)
    for command, kwargs in commands:
        assert command[:3] == ["/isolated/bin/python", "-I", "-c"]
        assert "sys.prefix" in command[3] and "O_NOFOLLOW" in command[3]
        assert "PYTHONPATH" not in kwargs["env"] and kwargs["cwd"] == tmp_path
    assert outcomes["positive"]["candidate_status"] == "MATCH"
    assert outcomes["negative"]["candidate_status"] == "NO_MATCH"
    assert outcomes["insufficient"]["exit"] == 1
    for scenario in ("geometry-missing", "comparison-missing"):
        assert outcomes[scenario]["candidate_status"] == "MATCH"
        assert outcomes[scenario]["exit"] == 1
    assert outcomes["interrupted"]["producer_calls"] == 2
    assert outcomes["invalid-request"]["producer_calls"] == 0


@pytest.mark.parametrize(
    "failure",
    [
        "exit",
        "privacy",
        "oversize",
        "marker",
        "resealed",
        "reference",
        "profile",
        "partial",
    ],
)
def test_installed_probe_rejects_corruption(
    actual_reports, monkeypatch, tmp_path, failure
):
    reports = copy.deepcopy(actual_reports)
    positive = reports["positive"]
    if failure == "exit":
        positive["code"] = 2
    elif failure == "privacy":
        positive["raw"] = b'{"api_key":"PRIVATE"}'.hex()
    elif failure == "oversize":
        positive["raw"] = (b"x" * (1024 * 1024 + 1)).hex()
    elif failure == "marker":
        positive["errors"] = ""
    elif failure == "resealed":
        value = json.loads(bytes.fromhex(positive["raw"]))
        value.pop("result_identity_sha256")
        value["members"][0]["candidate"] = None

        def raw(obj):
            return (
                json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()

        value["result_identity_sha256"] = hashlib.sha256(raw(value)).hexdigest()
        positive["raw"] = raw(value).hex()
    elif failure == "reference":
        positive["references"]["base_research_identity"] = "0" * 64
    elif failure == "profile":
        positive["references"]["producer_calls"][0][1] = "CURRENT_STRUCTURE"
    else:
        reports["interrupted"]["raw"] = positive["raw"]
    verifier = load(monkeypatch)
    monkeypatch.setattr(verifier, "_run", _runner(reports))
    with pytest.raises(RuntimeError):
        verifier._verify_installed_setup_research(
            Path("/isolated/bin/python"), tmp_path
        )
