"""Installed acceptance closes every nested field against independently regenerated original APIs."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
from test_linux_container_runtime import load

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def actual_reports():
    spec = importlib.util.spec_from_file_location(
        "inclusion_demo", ROOT / "examples/causal_setup_level_range_inclusion_demo.py"
    )
    assert spec is not None and spec.loader is not None
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    result = {}
    original_argv = sys.argv
    try:
        for scenario in demo.SCENARIOS:
            output, errors = demo._Output(), io.StringIO()
            sys.argv = ["demo", "--scenario", scenario]
            with redirect_stdout(output), redirect_stderr(errors):
                code = demo.main()
            raw = output.buffer.getvalue()
            result[scenario] = (
                json.loads(raw),
                raw,
                copy.deepcopy(demo.QUALIFICATION_REFERENCES),
                code,
            )
            assert code == (1 if scenario == "unknown" else 0)
            assert "not current market data" in errors.getvalue()
    finally:
        sys.argv = original_argv
    return result


def test_real_producer_complete_installed_contract(actual_reports, monkeypatch):
    verifier = load(monkeypatch)
    for scenario, (value, raw, references, _) in actual_reports.items():
        checker = getattr(verifier, "_check_installed_range_inclusion", None)
        if checker is None:
            # Existing installed surface does not accept the new bounded fact.
            verifier._check_installed_level_range(value, raw, "contains")
        else:
            checker(value, raw, scenario, references)


def _reseal(value):
    unsigned = dict(value)
    unsigned.pop("result_identity_sha256", None)
    value["result_identity_sha256"] = hashlib.sha256(_bytes(unsigned)).hexdigest()


def _bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


@pytest.mark.parametrize("scenario", ["earlier", "replay", "unknown", "refresh"])
@pytest.mark.parametrize(
    "field",
    [
        "contract_version",
        "criterion",
        "runtime_code_identity_sha256",
        "latest_range_identity_sha256",
        "level_identity_sha256",
        "continuity_identity_sha256",
        "continuity_status",
        "status",
        "reason",
        "previous_observation_identity_sha256",
        "current_observation_identity_sha256",
        "inclusion_observed",
        "evaluated_post_event_bars",
        "first_inclusion",
        "limitations",
        "extra",
    ],
)
def test_resealed_envelope_and_facts_rejected(
    actual_reports, monkeypatch, scenario, field
):
    value, _, references, _ = actual_reports[scenario]
    value = copy.deepcopy(value)
    value[field] = (
        {"PRIVATE_BODY": "not permitted"}
        if field in ("evaluated_post_event_bars", "first_inclusion", "extra")
        else 1
        if field == "inclusion_observed"
        else ["invented"]
        if field == "limitations"
        else "0" * 64
    )
    _reseal(value)
    with pytest.raises((ValueError, TypeError, KeyError)):
        load(monkeypatch)._check_installed_range_inclusion(
            value, _bytes(value), scenario, references
        )


@pytest.mark.parametrize("side", ["previous", "current"])
@pytest.mark.parametrize(
    "path",
    [
        ("status",),
        ("reason",),
        ("session",),
        ("data_selection_time",),
        ("price_basis",),
        ("source_profile",),
        ("feature_availability",),
        ("feature_support",),
        ("feature_comparability",),
        ("feature_known_at",),
        ("research_runtime_code_identity_sha256",),
        ("research_result_identity_sha256",),
        ("feature_source_identity_sha256",),
        ("capture_revision_identity_sha256",),
        ("schedule_identity_sha256",),
        ("candidate_identity_sha256",),
        ("canonical_stock", "isin"),
        ("canonical_stock", "exchange"),
        ("canonical_stock", "effective_symbol"),
        ("canonical_stock", "mapping_identity_sha256"),
        ("extra",),
    ],
)
def test_resealed_nested_rows_rejected_against_originals(
    actual_reports, monkeypatch, side, path
):
    value, _, references, _ = actual_reports["earlier"]
    value = copy.deepcopy(value)
    node = value[side]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = "plausible_but_wrong"
    _reseal(value)
    with pytest.raises(ValueError):
        load(monkeypatch)._check_installed_range_inclusion(
            value, _bytes(value), "earlier", references
        )


@pytest.mark.parametrize(
    "path",
    [
        ("previous", "candidate", "event"),
        ("previous", "candidate", "prior_trend"),
        ("previous", "candidate", "pivot_session"),
        ("previous", "candidate", "pivot_confirmation_session"),
        ("previous", "candidate", "event_identity_sha256"),
        ("previous", "candidate", "pivot_identity_sha256"),
        ("previous", "candidate", "extra"),
        ("witness", "original_event_session"),
        ("witness", "original_high_pivot_session"),
        ("witness", "original_high_confirmation_session"),
        ("witness", "original_high_identity_sha256"),
        ("witness", "represented_event_identity_sha256"),
        ("witness", "represented_high_identity_sha256"),
        ("witness", "current_completed_session"),
        ("witness", "current_bar_identity_sha256"),
        ("witness", "extra"),
    ],
)
def test_resealed_nested_anchor_witness_rejected(actual_reports, monkeypatch, path):
    value, _, references, _ = actual_reports["earlier"]
    value = copy.deepcopy(value)
    node = value
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = "0" * 64
    _reseal(value)
    with pytest.raises(ValueError):
        load(monkeypatch)._check_installed_range_inclusion(
            value, _bytes(value), "earlier", references
        )


@pytest.mark.parametrize(
    "mutation", ["order", "first", "bar_hash", "event_bar", "extra_bar", "row_extra"]
)
def test_resealed_chronology_rejected(actual_reports, monkeypatch, mutation):
    value, _, references, _ = actual_reports["earlier"]
    value = copy.deepcopy(value)
    rows = value["evaluated_post_event_bars"]
    if mutation == "order":
        rows.reverse()
    elif mutation == "first":
        value["first_inclusion"] = copy.deepcopy(rows[-1])
    elif mutation == "bar_hash":
        rows[0]["bar_identity_sha256"] = "0" * 64
    elif mutation == "event_bar":
        rows[0]["session"] = "2026-08-25"
    elif mutation == "extra_bar":
        rows.append(copy.deepcopy(rows[-1]))
    else:
        rows[0]["extra"] = "PRIVATE_PATH"
    _reseal(value)
    with pytest.raises(ValueError):
        load(monkeypatch)._check_installed_range_inclusion(
            value, _bytes(value), "earlier", references
        )


@pytest.mark.parametrize("reference", ["level", "latest_range"])
@pytest.mark.parametrize(
    "field",
    ["extra", "limitations", "previous", "witness", "runtime_code_identity_sha256"],
)
def test_corrupted_original_reference_cannot_be_resealed_into_admission(
    actual_reports, monkeypatch, reference, field
):
    value, _, references, _ = actual_reports["earlier"]
    references = copy.deepcopy(references)
    references[reference][field] = "0" * 64
    _reseal(references[reference])
    with pytest.raises((ValueError, TypeError, KeyError)):
        load(monkeypatch)._check_installed_range_inclusion(
            value, _bytes(value), "earlier", references
        )


def test_canonical_and_bound_enforced(actual_reports, monkeypatch):
    value, raw, references, _ = actual_reports["earlier"]
    verifier = load(monkeypatch)
    for bad in (
        raw.rstrip(b"\n"),
        json.dumps(value).encode(),
        b"x" * (1024 * 1024 + 1),
    ):
        with pytest.raises(ValueError):
            verifier._check_installed_range_inclusion(value, bad, "earlier", references)


def test_installed_probe_uses_isolated_runtime_and_strict_scenario_map(
    actual_reports, monkeypatch, tmp_path
):
    verifier = load(monkeypatch)
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        scenario = command[-2]
        _, raw, references, code = actual_reports[scenario]
        Path(command[-1]).write_text(json.dumps(references))
        return subprocess.CompletedProcess(
            command, code, raw, b"SYNTHETIC RANGE INCLUSION: not current market data\n"
        )

    monkeypatch.setattr(verifier, "_run", run)
    result = verifier._verify_installed_range_inclusion(
        Path("/isolated/bin/python"), tmp_path
    )
    assert set(result) == set(actual_reports) and len(commands) == 13
    for command, kwargs in commands:
        assert command[:3] == ["/isolated/bin/python", "-I", "-c"]
        assert (
            "sys.prefix" in command[3]
            and "original_range" in command[3]
            and "original_level" in command[3]
        )
        assert "sys.modules" in command[3] and "O_NOFOLLOW" in command[3]
        assert kwargs["cwd"] == tmp_path and "PYTHONPATH" not in kwargs["env"]
    assert result["earlier"]["first_inclusion"]["session"] == "2026-08-26"
    assert result["none"]["inclusion_observed"] is False


@pytest.mark.parametrize(
    "failure",
    ["exit", "privacy", "oversize", "missing_marker", "resealed", "reference"],
)
def test_installed_probe_failures_are_terminal(
    actual_reports, monkeypatch, tmp_path, failure
):
    verifier = load(monkeypatch)

    def run(command, **kwargs):
        value, raw, references, code = actual_reports[command[-2]]
        value, references = copy.deepcopy(value), copy.deepcopy(references)
        stderr = b"SYNTHETIC RANGE INCLUSION: not current market data\n"
        if failure == "exit":
            code = 2
        elif failure == "privacy":
            raw = b'{"body":"PRIVATE_BODY"}'
        elif failure == "oversize":
            raw = b"x" * (1024 * 1024 + 1)
        elif failure == "missing_marker":
            stderr = b""
        elif failure == "resealed":
            value["first_inclusion"] = None
            _reseal(value)
            raw = _bytes(value)
        else:
            references["level"]["extra"] = "leak"
        Path(command[-1]).write_text(json.dumps(references))
        return subprocess.CompletedProcess(command, code, raw, stderr)

    monkeypatch.setattr(verifier, "_run", run)
    with pytest.raises(RuntimeError):
        verifier._verify_installed_range_inclusion(
            Path("/isolated/bin/python"), tmp_path
        )
