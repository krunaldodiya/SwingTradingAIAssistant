"""Strict v3 qualification rejects resealed nested corruption against original APIs."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
from test_linux_container_runtime import load

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def actual_reports():
    spec = importlib.util.spec_from_file_location(
        "range_interpretation_demo",
        ROOT / "examples/causal_setup_range_interpretation_v3_demo.py",
    )
    assert spec is not None and spec.loader is not None
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    result = {}
    for scenario in (
        "contains",
        "above",
        "below",
        "low-equal",
        "high-equal",
        "invalidated",
        "replay",
        "unknown",
        "no-trade",
        "false-claim",
    ):
        stream = io.BytesIO()
        output, errors = io.TextIOWrapper(stream, encoding="utf-8"), io.StringIO()
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(sys, "argv", [str(spec.origin), "--scenario", scenario])
            with redirect_stdout(output), redirect_stderr(errors):
                code = demo.main()
        output.flush()
        raw = stream.getvalue()
        result[scenario] = (
            code,
            raw,
            errors.getvalue(),
            copy.deepcopy(demo.QUALIFICATION_REFERENCES),
        )
    return result


@pytest.mark.parametrize(
    "scenario",
    [
        "contains",
        "above",
        "below",
        "low-equal",
        "high-equal",
        "invalidated",
        "replay",
        "unknown",
        "no-trade",
    ],
)
def test_actual_producer_sdk_cli_and_independent_original_references(
    actual_reports, monkeypatch, scenario
):
    api = load(monkeypatch)
    code, raw, errors, references = actual_reports[scenario]
    assert code == (1 if scenario == "unknown" else 0)
    assert "SYNTHETIC CALLER-AUTHORED" in errors
    assert "not current market data" in errors
    value = json.loads(raw)
    api._check_installed_interpretation_v3(value, raw, scenario, references)
    for name in ("continuity", "invalidation", "age", "level"):
        assert value["evidence"][name] == references["legacy_v2"][name]
    assert value["evidence"]["level_range"] == references["level_range"]
    assert (
        value["evidence"]["level_range"]["level_identity_sha256"]
        == references["level"]["result_identity_sha256"]
    )


def test_actual_false_range_has_empty_output_and_fixed_diagnostic(actual_reports):
    code, raw, errors, references = actual_reports["false-claim"]
    assert code == 2 and raw == b""
    assert errors.endswith("setup_interpretation_failed\n")
    assert references["level_range"]["range_relation"] == "CONTAINS_LEVEL"


def _seal_tree(value):
    if type(value) is dict:
        for item in value.values():
            _seal_tree(item)
        if "result_identity_sha256" in value:
            unsigned = {
                key: item
                for key, item in value.items()
                if key != "result_identity_sha256"
            }
            value["result_identity_sha256"] = hashlib.sha256(
                (
                    json.dumps(unsigned, sort_keys=True, separators=(",", ":")) + "\n"
                ).encode()
            ).hexdigest()
    elif type(value) is list:
        for item in value:
            _seal_tree(item)


@pytest.mark.parametrize(
    "path,value",
    [
        (("evidence", "level_range", "range_relation"), "ENTIRELY_ABOVE"),
        (("evidence", "level_range", "status"), "UNKNOWN"),
        (("evidence", "level_range", "level_identity_sha256"), "0" * 64),
        (
            ("evidence", "level_range", "witness", "current_bar_identity_sha256"),
            "0" * 64,
        ),
        (
            ("evidence", "level", "witness", "represented_high_identity_sha256"),
            "0" * 64,
        ),
        (
            (
                "evidence",
                "continuity",
                "current_representation",
                "event_identity_sha256",
            ),
            "0" * 64,
        ),
        (
            (
                "evidence",
                "invalidation",
                "original_supporting_low",
                "pivot_identity_sha256",
            ),
            "0" * 64,
        ),
        (("evidence", "age", "completed_sessions_elapsed"), True),
        (
            ("evidence", "age", "schedules", "current", "schedule_identity_sha256"),
            "0" * 64,
        ),
        (("evidence", "age", "current", "canonical_stock", "isin"), "INE062A01020"),
        (
            ("evidence", "age", "current", "feature_known_at"),
            "2026-08-28T00:00:00.000000Z",
        ),
        (
            (
                "evidence",
                "continuity",
                "previous",
                "candidate",
                "pivot_confirmation_session",
            ),
            "2026-08-26",
        ),
        (("evidence", "level", "current", "price_basis"), "ADJUSTED"),
        (
            ("evidence", "level_range", "current", "capture_revision_identity_sha256"),
            "0" * 64,
        ),
        (("evidence", "legacy_evidence_v2_identity_sha256"), "0" * 64),
        (("runtime_code_identity_sha256",), "0" * 64),
        (("evidence", "runtime_code_identity_sha256"), "0" * 64),
        (("verification",), "AI_APPROVED"),
        (("external_response", "disposition"), "BUY"),
        (("external_response", "facts", "level_range", "range_relation"), None),
    ],
)
def test_resealed_nested_corruption_cannot_become_current_qualification(
    actual_reports, monkeypatch, path, value
):
    api = load(monkeypatch)
    _, raw, _, references = actual_reports["contains"]
    bad = json.loads(raw)
    target = bad
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    _seal_tree(bad)
    candidate = api._interpretation_bytes(bad)
    with pytest.raises((ValueError, KeyError, TypeError)):
        api._check_installed_interpretation_v3(bad, candidate, "contains", references)


@pytest.mark.parametrize(
    "component", ["continuity", "invalidation", "age", "level", "level_range"]
)
@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_closed_every_nested_component_even_after_resealing(
    actual_reports, monkeypatch, component, mutation
):
    api = load(monkeypatch)
    _, raw, _, references = actual_reports["contains"]
    value = json.loads(raw)
    if mutation == "extra":
        value["evidence"][component]["body"] = "PRIVATE_BODY"
    else:
        del value["evidence"][component]["reason"]
    _seal_tree(value)
    with pytest.raises((ValueError, KeyError, TypeError)):
        api._check_installed_interpretation_v3(
            value, api._interpretation_bytes(value), "contains", references
        )


def test_runtime_probe_enforces_isolation_and_independent_reference_file(
    monkeypatch, tmp_path
):
    api = load(monkeypatch)
    observed = []

    def run(args, **kwargs):
        observed.append((args, kwargs))
        raise RuntimeError("source checks only; no simulated acceptance")

    monkeypatch.setattr(api, "_run", run)
    with pytest.raises(RuntimeError, match="source checks only"):
        api._verify_installed_range_interpretation_v3(
            tmp_path / "venv/bin/python", tmp_path
        )
    args, kwargs = observed[0]
    assert args[1:3] == ["-I", "-c"]
    compile(args[3], "installed-v3-probe", "exec")
    assert "sys.prefix" in args[3] and "QUALIFICATION_REFERENCES" in args[3]
    assert "setup_level_range" in args[3] and "setup_evidence_v2" in args[3]
    assert args[-2] == "contains" and args[-1].endswith(
        "v3-original-references-contains.json"
    )
    assert kwargs["cwd"] == tmp_path and "PYTHONPATH" not in kwargs["env"]
