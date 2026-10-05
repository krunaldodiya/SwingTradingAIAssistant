"""Coherent evidence expectations through real producer admission and actual CLI."""

import hashlib
import importlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from test_setup_event_continuity import _rolling_observe
from test_setup_invalidation import _anchored
from test_setup_observation_comparison import _args, _observe

from swing_trading_ai_assistant.research_comparison import (
    setup_observation_comparison as encoding,
)

MODULE = "swing_trading_ai_assistant.research_comparison.setup_evidence"


def test_actual_cli_obtains_one_pair_for_three_consistent_facts(tmp_path, capsys):
    path = MODULE + "_cli"
    if importlib.util.find_spec(path) is None:
        path = "swing_trading_ai_assistant.research_comparison.setup_age_cli"
    main = importlib.import_module(path).main
    previous = _anchored(tmp_path / "previous")
    current = _anchored(tmp_path / "current", later=True, close=134, wick=120)
    args = _args(tmp_path)
    args[0] = "setup-evidence"
    args[args.index("--current-selection-time") + 1] = (
        current.data_selection_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    values, calls = iter((previous, current)), []

    def service(symbol, root, **kwargs):
        calls.append((symbol, root, kwargs))
        return next(values)

    assert main(args, observation_service=service) == 0
    output = capsys.readouterr()
    assert not output.err
    report = json.loads(output.out)
    assert report["contract_version"] == "causal-setup-evidence@v1"
    assert report["continuity"]["status"] == "SAME_EVENT"
    assert report["invalidation"]["status"] == "NO_CONTRADICTION_OBSERVED"
    assert report["age"]["completed_sessions_elapsed"] == 1
    assert report["age"]["current"]["status"] == "NO_MATCH"
    assert [c[2]["question"] for c in calls] == ["CURRENT_STRUCTURE"] * 2
    assert [c[2]["selection_time"] for c in calls] == [
        previous.data_selection_time,
        current.data_selection_time,
    ]
    for component in ("continuity", "invalidation", "age"):
        for side in ("previous", "current"):
            field = side + "_observation_identity_sha256"
            assert report[component][field] == report[field]
    assert (
        report["invalidation"]["continuity_identity_sha256"]
        == report["continuity"]["result_identity_sha256"]
    )
    assert (
        report["age"]["continuity_identity_sha256"]
        == report["continuity"]["result_identity_sha256"]
    )
    assert "status" not in report


def _assemble(previous, current):
    return importlib.import_module(MODULE).assemble_setup_evidence_v1(previous, current)


def _cli(tmp_path, previous, current, capsys):
    args = _args(tmp_path)
    args[0] = "setup-evidence"
    for side, value in (("previous", previous), ("current", current)):
        args[args.index("--" + side + "-selection-time") + 1] = (
            value.data_selection_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )
    values = iter((previous, current))
    code = importlib.import_module(MODULE + "_cli").main(
        args, observation_service=lambda *a, **k: next(values)
    )
    return code, capsys.readouterr()


def test_observed_contradiction_survives_independently_observed_age(tmp_path, capsys):
    previous = _anchored(tmp_path / "p")
    current = _anchored(tmp_path / "c", later=True)
    code, output = _cli(tmp_path, previous, current, capsys)
    assert code == 0 and not output.err
    report = json.loads(output.out)
    assert report["continuity"]["status"] == "SAME_EVENT"
    assert report["invalidation"]["status"] == "INVALIDATED"
    assert report["invalidation"]["contradiction"]["event"] == "CHOCH"
    assert (
        report["age"]["status"] == "OBSERVED"
        and report["age"]["completed_sessions_elapsed"] == 1
    )
    assert (
        not {"status", "active", "valid", "eligible", "readiness", "recommendation"}
        & report.keys()
    )


@pytest.mark.parametrize(
    "before,after,days,minutes,continuity,age,code",
    [
        ("negative", "positive", 0, 1, "NO_BASELINE", "NO_BASELINE", 0),
        ("positive", "negative", 0, 1, "NOT_REPRESENTED", "NOT_REPRESENTED", 1),
        ("positive", "insufficient", 0, 1, "UNKNOWN", "UNKNOWN", 1),
        ("insufficient", "positive", 0, 1, "UNKNOWN", "UNKNOWN", 1),
        ("positive", "positive", 35, 1, "OUTSIDE_WINDOW", "OUTSIDE_WINDOW", 1),
        ("positive", "positive", 0, 1, "SAME_EVENT", "OBSERVED", 0),
    ],
)
def test_independent_evidence_states_and_cli_exits(
    tmp_path, capsys, before, after, days, minutes, continuity, age, code
):
    previous = _observe(tmp_path / "p", before)
    current = _observe(tmp_path / "c", after, days=days, minutes=minutes)
    actual, output = _cli(tmp_path, previous, current, capsys)
    assert actual == code and not output.err
    report = json.loads(output.out)
    assert report["continuity"]["status"] == continuity
    assert report["age"]["status"] == age
    if age not in ("OBSERVED", "REPLAY"):
        assert report["age"]["completed_sessions_elapsed"] is None


def test_replay_and_source_only_refresh_are_not_new_opportunities(tmp_path, capsys):
    previous = _anchored(tmp_path / "p")
    code, output = _cli(tmp_path, previous, previous, capsys)
    assert code == 0
    report = json.loads(output.out)
    assert [report[k]["status"] for k in ("continuity", "invalidation", "age")] == [
        "REPLAY"
    ] * 3
    assert report["age"]["completed_sessions_elapsed"] == 0
    current = _observe(tmp_path / "c", minutes=1)
    report = _assemble(_observe(tmp_path / "b"), current)
    assert report["continuity"]["status"] == "SAME_EVENT"
    assert report["age"]["completed_sessions_elapsed"] == 0
    assert (
        report["previous_observation_identity_sha256"]
        != report["current_observation_identity_sha256"]
    )


def test_factual_revision_remains_inconclusive(tmp_path, capsys):
    previous = _observe(tmp_path / "p")
    current = _rolling_observe(tmp_path / "c", shift=1)
    code, output = _cli(tmp_path, previous, current, capsys)
    assert code == 1
    report = json.loads(output.out)
    assert report["continuity"]["status"] == "REVISED_EVENT"
    assert report["invalidation"]["status"] == "REVISED_EVIDENCE"
    assert (
        report["age"]["status"] == "REVISED_EVENT"
        and report["age"]["completed_sessions_elapsed"] is None
    )


def test_revised_low_is_not_hidden_by_unchanged_event_and_age(tmp_path, capsys):
    previous = _anchored(tmp_path / "p")
    current = _anchored(tmp_path / "c", later=True, low_revision=1)
    code, output = _cli(tmp_path, previous, current, capsys)
    assert code == 1
    report = json.loads(output.out)
    assert report["continuity"]["status"] == "SAME_EVENT"
    assert report["invalidation"]["status"] == "REVISED_EVIDENCE"
    assert report["age"]["completed_sessions_elapsed"] == 1


@pytest.mark.parametrize("side", ["previous", "current"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("runtime_code_identity_sha256", "0" * 64),
        ("code", "PRIVATE_PAYLOAD"),
        ("limitations", ("x" * 1025,)),
        ("question", "PRICE_BEHAVIOR"),
    ],
)
def test_complete_input_integrity_precedes_unknown(tmp_path, side, field, value):
    previous = _observe(tmp_path / "p")
    current = _observe(tmp_path / "c", "insufficient", minutes=1)
    object.__setattr__(previous if side == "previous" else current, field, value)
    with pytest.raises(ValueError):
        _assemble(previous, current)


@pytest.mark.parametrize("mutation", ["duplicate", "order", "type", "limit", "release"])
def test_corrupt_session_admission_is_terminal_with_unknown(tmp_path, mutation):
    previous = _observe(tmp_path / "p")
    current = _observe(tmp_path / "c", "insufficient", minutes=1)
    source = previous.packet.source("MARKET_STRUCTURE")
    sessions = source.admitted_sessions
    values = {
        "duplicate": sessions[:-1] + (sessions[-2],),
        "order": tuple(reversed(sessions)),
        "type": sessions[:-1] + ("2026-08-25",),
        "limit": sessions + (sessions[-1] + timedelta(days=1),),
    }
    object.__setattr__(
        source,
        "schedule_source_release" if mutation == "release" else "admitted_sessions",
        "unsupported" if mutation == "release" else values[mutation],
    )
    with pytest.raises(ValueError):
        _assemble(previous, current)


@pytest.mark.parametrize(
    "field",
    [
        "previous_observation_identity_sha256",
        "current_observation_identity_sha256",
        "previous",
        "current",
        "continuity_identity_sha256",
        "result_identity_sha256",
    ],
)
def test_component_substitution_is_terminal_even_if_resealed(
    tmp_path, monkeypatch, field
):
    api = importlib.import_module(MODULE)
    previous = _anchored(tmp_path / "p")
    current = _anchored(tmp_path / "c", later=True)
    original = api.observe_setup_age_v1

    def substituted(*args):
        value = original(*args)
        value[field] = {} if field in ("previous", "current") else "0" * 64
        if field != "result_identity_sha256":
            unsigned = dict(value)
            unsigned.pop("result_identity_sha256")
            value["result_identity_sha256"] = hashlib.sha256(
                encoding.canonical_comparison_bytes(unsigned)
            ).hexdigest()
        return value

    monkeypatch.setattr(api, "observe_setup_age_v1", substituted)
    with pytest.raises(ValueError, match="evidence .* invalid"):
        _assemble(previous, current)


@pytest.mark.parametrize("mutation", ["missing", "extra", "digest"])
def test_own_closed_source_inventory_cannot_be_substituted(
    tmp_path, monkeypatch, mutation
):
    api = importlib.import_module(MODULE)
    previous = _anchored(tmp_path / "p")
    mapping = dict(api.SETUP_EVIDENCE_RUNTIME_SOURCE_SHA256_V1)
    first = next(iter(mapping))
    if mutation == "missing":
        del mapping[first]
    elif mutation == "extra":
        mapping["unexpected"] = "0" * 64
    else:
        mapping[first] = "0" * 64
    monkeypatch.setattr(api, "SETUP_EVIDENCE_RUNTIME_SOURCE_SHA256_V1", mapping)
    with pytest.raises(ValueError, match="evidence runtime"):
        _assemble(previous, previous)


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--symbol", "bad/stock"),
        ("--symbol", "P" * 33),
        ("--storage-root", "relative"),
        ("--current-selection-time", "invalid"),
        ("--previous-selection-time", "2026-09-01T04:15:00.000000Z"),
    ],
)
def test_invalid_cli_request_has_zero_effects(tmp_path, capsys, flag, value):
    args = _args(tmp_path)
    args[0] = "setup-evidence"
    args[args.index(flag) + 1] = value

    def service(*a, **k):
        pytest.fail("invalid request performed effect")

    assert (
        importlib.import_module(MODULE + "_cli").main(args, observation_service=service)
        == 2
    )
    output = capsys.readouterr()
    assert not output.out and output.err == "request_invalid\n"


@pytest.mark.parametrize("failure", ["interrupted", "selector", "late-component"])
def test_terminal_failure_has_fixed_diagnostic_and_no_partial_stdout(
    tmp_path, capsys, monkeypatch, failure
):
    previous = _anchored(tmp_path / "p")
    current = _anchored(tmp_path / "c", later=True)
    if failure == "selector":
        object.__setattr__(current, "symbol", "TCS")
    args = _args(tmp_path)
    args[0] = "setup-evidence"
    args[args.index("--current-selection-time") + 1] = (
        current.data_selection_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    calls = []

    def service(*a, **k):
        calls.append(k)
        if len(calls) == 2 and failure == "interrupted":
            raise KeyboardInterrupt("PRIVATE")
        return previous if len(calls) == 1 else current

    if failure == "late-component":

        def interrupt(*a, **k):
            raise KeyboardInterrupt("PRIVATE_LATER")

        monkeypatch.setattr(
            importlib.import_module(MODULE), "observe_setup_age_v1", interrupt
        )
    assert (
        importlib.import_module(MODULE + "_cli").main(args, observation_service=service)
        == 2
    )
    output = capsys.readouterr()
    assert not output.out and output.err == "setup_evidence_failed\n"
    assert len(calls) == 2


def test_repeated_concurrent_evidence_preserves_inputs_files_and_private_bounds(
    tmp_path,
):
    previous = _anchored(tmp_path / "p")
    current = _anchored(tmp_path / "c", later=True)
    snapshots = [v.canonical_json_bytes() for v in (previous, current)]
    files = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    report = _assemble(previous, current)
    raw = encoding.canonical_comparison_bytes(report)
    unsigned = dict(report)
    identity = unsigned.pop("result_identity_sha256")
    assert (
        identity
        == hashlib.sha256(encoding.canonical_comparison_bytes(unsigned)).hexdigest()
    )
    assert len(raw) <= 1024 * 1024
    assert not any(
        t in raw
        for t in (
            b'"close"',
            b'"open"',
            b'"high"',
            b'"low"',
            b'"price"',
            b'"volume"',
            str(tmp_path).encode(),
        )
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _assemble(previous, current), range(2)))
    assert all(encoding.canonical_comparison_bytes(v) == raw for v in results)
    assert [v.canonical_json_bytes() for v in (previous, current)] == snapshots
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == files


def test_exact_whole_bundle_bound_and_plus_one_are_atomic(
    tmp_path, capsys, monkeypatch
):
    previous = _anchored(tmp_path / "p")
    report = _assemble(previous, previous)
    value = dict(report)
    value["padding"] = ""
    overhead = len(encoding.canonical_comparison_bytes(value))
    value["padding"] = "x" * (encoding.MAX_OUTPUT - overhead)
    assert len(encoding.canonical_comparison_bytes(value)) == encoding.MAX_OUTPUT
    value["padding"] += "x"
    with pytest.raises(ValueError):
        encoding.canonical_comparison_bytes(value)
    # Each real component fits this bound but the whole bundle does not.
    largest = max(
        len(encoding.canonical_comparison_bytes(report[k]))
        for k in ("continuity", "invalidation", "age")
    )
    monkeypatch.setattr(encoding, "MAX_OUTPUT", largest + 100)
    with pytest.raises(ValueError, match="output limit"):
        _assemble(previous, previous)
    code, output = _cli(tmp_path, previous, previous, capsys)
    assert code == 2 and not output.out and output.err == "setup_evidence_failed\n"


def test_incompatible_stocks_and_reversed_time_are_not_combined(tmp_path):
    previous = _observe(tmp_path / "p")
    current = _observe(tmp_path / "c", minutes=1, symbol="TCS")
    report = _assemble(previous, current)
    assert all(
        report[k]["status"] == "NON_COMPARABLE"
        for k in ("continuity", "invalidation", "age")
    )
    current = _observe(tmp_path / "d", minutes=1)
    report = _assemble(current, previous)
    assert all(
        report[k]["status"] == "NON_COMPARABLE"
        for k in ("continuity", "invalidation", "age")
    )
