"""Real producer fixture isolation and strict six-fact installed qualification."""

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_linux_container_runtime import load

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = (
    "earlier",
    "none",
    "latest",
    "multiple",
    "low-equal",
    "high-equal",
    "nearest-above",
    "nearest-below",
    "event-only",
    "invalidated",
    "replay",
    "unknown",
    "refresh",
    "no-trade",
    "false-claim",
    "false-session",
)


@pytest.fixture(scope="module")
def verifier():
    with pytest.MonkeyPatch.context() as patch:
        return load(patch)


@pytest.fixture(scope="module")
def actual_scenarios():
    # All mutable demonstration clock and audit-hook state lives in one fresh
    # bounded subprocess, never in the pytest process or another fixture.
    code = """
import copy, contextlib, io, json, runpy, sys
fixture, scenarios = sys.argv[1:]
module = runpy.run_path(fixture, run_name='qualification_test')
class Output(io.StringIO):
    def __init__(self):
        super().__init__()
        self.buffer = io.BytesIO()
results = {}
for scenario in json.loads(scenarios):
    sys.argv = [fixture, '--scenario', scenario]
    stream = Output()
    with contextlib.redirect_stdout(stream):
        status = module['main']()
    results[scenario] = dict(exit=status, raw=stream.buffer.getvalue().hex(), references=copy.deepcopy(module['main'].__globals__['QUALIFICATION_REFERENCES']))
sys.stdout.write(json.dumps(results))
"""
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(  # noqa: S603 - fixed guarded producer and bounded scenarios
        [
            sys.executable,
            "-c",
            code,
            str(ROOT / "examples/causal_setup_inclusion_interpretation_v4_demo.py"),
            json.dumps(SCENARIOS),
        ],
        capture_output=True,
        env=env,
        timeout=180,
        check=True,
    )
    assert b"not current market data" in result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_actual_guarded_sdk_both_cli_and_strict_qualifier(
    verifier, actual_scenarios, scenario
):
    result = actual_scenarios[scenario]
    raw = bytes.fromhex(result["raw"])
    assert result["exit"] == (
        2 if scenario.startswith("false-") else 1 if scenario == "unknown" else 0
    )
    if scenario.startswith("false-"):
        assert raw == b""
        return
    value = json.loads(raw)
    check = getattr(
        verifier,
        "_check_installed_interpretation_v4",
        verifier._check_installed_interpretation_v3,
    )
    check(value, raw, scenario, result["references"])


def _seal(value):
    value.pop("result_identity_sha256", None)
    value["result_identity_sha256"] = hashlib.sha256(
        (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()


@pytest.mark.parametrize(
    "path,value",
    [
        (("evidence", "level_range_inclusion", "inclusion_observed"), False),
        (
            ("evidence", "level_range_inclusion", "first_inclusion", "session"),
            "2026-08-27",
        ),
        (
            (
                "evidence",
                "level_range_inclusion",
                "first_inclusion",
                "bar_identity_sha256",
            ),
            "0" * 64,
        ),
        (("evidence", "level_range_inclusion", "evaluated_post_event_bars"), []),
        (
            ("evidence", "level_range_inclusion", "witness", "original_event_session"),
            "2026-08-24",
        ),
        (("evidence", "level_range_inclusion", "current", "reason"), "INVENTED"),
        (
            ("evidence", "continuity", "current_representation", "event_session"),
            "2026-08-24",
        ),
        (
            ("evidence", "invalidation", "original_supporting_low", "pivot_session"),
            "2026-08-13",
        ),
        (("evidence", "age", "completed_sessions_elapsed"), 1),
        (
            ("evidence", "age", "schedules", "current", "feature_known_at"),
            "2026-08-29T04:15:00.000000Z",
        ),
        (("evidence", "level", "relation"), "BELOW"),
        (("evidence", "level_range", "range_relation"), "CONTAINS_LEVEL"),
        (("evidence", "legacy_evidence_v3_identity_sha256"), "0" * 64),
        (("evidence", "runtime_code_identity_sha256"), "0" * 64),
        (
            (
                "external_response",
                "facts",
                "level_range_inclusion",
                "inclusion_observed",
            ),
            None,
        ),
        (("verification",), "VERIFIED_RECOMMENDATION"),
        (("eligibility",), "ELIGIBLE"),
        (("limitations",), []),
    ],
)
def test_resealed_corruption_rejected_at_every_depth(
    verifier, actual_scenarios, path, value
):
    original = actual_scenarios["earlier"]
    forged = json.loads(bytes.fromhex(original["raw"]))
    target = forged
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    for name in (
        "continuity",
        "invalidation",
        "age",
        "level",
        "level_range",
        "level_range_inclusion",
    ):
        _seal(forged["evidence"][name])
    _seal(forged["evidence"])
    _seal(forged)
    raw = verifier._interpretation_bytes(forged)
    with pytest.raises((ValueError, KeyError, TypeError)):
        verifier._check_installed_interpretation_v4(
            forged, raw, "earlier", original["references"]
        )


@pytest.mark.parametrize(
    "name",
    [
        "legacy_v1",
        "legacy_v2",
        "legacy_v3",
        "inclusion_references",
        "evidence_runtime",
        "interpretation_runtime",
    ],
)
@pytest.mark.parametrize("mutation", ["missing", "changed"])
def test_independent_reference_inventory_and_bytes_closed(
    verifier, actual_scenarios, name, mutation
):
    original = actual_scenarios["earlier"]
    references = copy.deepcopy(original["references"])
    if mutation == "missing":
        del references[name]
    elif name.endswith("runtime"):
        references[name] = "0" * 64
    else:
        references[name]["unexpected"] = True
    raw = bytes.fromhex(original["raw"])
    with pytest.raises((ValueError, KeyError, TypeError)):
        verifier._check_installed_interpretation_v4(
            json.loads(raw), raw, "earlier", references
        )


@pytest.mark.parametrize("mutation", ["whitespace", "missing-lf", "extra", "nonfinite"])
def test_qualifier_canonical_bytes_and_closed_envelope(
    verifier, actual_scenarios, mutation
):
    original = actual_scenarios["earlier"]
    raw = bytes.fromhex(original["raw"])
    value = json.loads(raw)
    if mutation == "whitespace":
        raw += b" "
    elif mutation == "missing-lf":
        raw = raw[:-1]
    else:
        value["private_extra"] = float("nan") if mutation == "nonfinite" else True
        raw = verifier._interpretation_bytes(value)
    with pytest.raises((ValueError, KeyError, TypeError)):
        verifier._check_installed_interpretation_v4(
            value, raw, "earlier", original["references"]
        )
