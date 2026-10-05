"""Causal broken-high relations through admitted producer observations."""

from __future__ import annotations

# Every fixture is produced by the real typed service, independently of the SDK.
import copy
import hashlib
import importlib
import importlib.util
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from test_setup_age import _advanced
from test_setup_event_continuity import _rolling_observe
from test_setup_invalidation import _anchored
from test_setup_observation_comparison import _args, _observe

from swing_trading_ai_assistant.research_comparison import (
    setup_observation_comparison as encoding,
)
from swing_trading_ai_assistant.research_comparison.setup_age import (
    observe_setup_age_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_event_continuity import (
    observe_setup_event_continuity_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_invalidation import (
    observe_setup_invalidation_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (
    canonical_comparison_bytes,
)

MODULE = "swing_trading_ai_assistant.research_comparison.setup_level"


def _level(previous, current):
    return importlib.import_module(MODULE).observe_setup_level_v1(previous, current)


def test_actual_cli_latest_close_above_original_broken_high(tmp_path, capsys):
    path = MODULE + "_cli"
    if importlib.util.find_spec(path) is None:
        path = "swing_trading_ai_assistant.research_comparison.setup_age_cli"
    main = importlib.import_module(path).main
    previous = _anchored(tmp_path / "previous")
    current = _anchored(tmp_path / "current", later=True, close=134, wick=120)
    args = _args(tmp_path)
    args[0] = "setup-level"
    args[args.index("--current-selection-time") + 1] = (
        current.data_selection_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    values = iter((previous, current))
    calls = []

    def service(symbol, root, **kwargs):
        calls.append((symbol, root, kwargs))
        return next(values)

    assert main(args, observation_service=service) == 0
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert not output.err
    assert report["status"] == "OBSERVED"
    assert report["relation"] == "ABOVE"
    assert report["continuity_status"] == "SAME_EVENT"
    assert report["current"]["status"] == "NO_MATCH"
    assert calls == [
        (
            "PNB",
            tmp_path,
            {
                "question": "CURRENT_STRUCTURE",
                "selection_time": value.data_selection_time,
            },
        )
        for value in (previous, current)
    ]
    assert output.out.encode() == canonical_comparison_bytes(_level(previous, current))
    identity = report.pop("result_identity_sha256")
    assert identity == hashlib.sha256(canonical_comparison_bytes(report)).hexdigest()


@pytest.fixture(scope="module")
def admitted(tmp_path_factory):
    root = tmp_path_factory.mktemp("level-admission")
    results = {"previous": _anchored(root / "previous")}
    for name, close, wick in (
        ("above", 134, 120),
        ("at", 130, 120),
        ("below", 100, 80),
        ("invalidated", 89, 80),
        ("nearest_above", Decimal("130.0000000000000000000000000001"), 120),
        ("nearest_below", Decimal("129.9999999999999999999999999999"), 120),
    ):
        results[name] = _anchored(root / name, later=True, close=close, wick=wick)
    for name, mode, days, minutes, symbol, shift in (
        ("baseline", "positive", 0, 0, "PNB", 0),
        ("refresh", "positive", 0, 1, "PNB", 0),
        ("unknown", "insufficient", 0, 1, "PNB", 0),
        ("unknown_base", "insufficient", 0, 0, "PNB", 0),
        ("negative_base", "negative", 0, 0, "PNB", 0),
        ("negative", "negative", 0, 1, "PNB", 0),
        ("outside", "positive", 35, 0, "PNB", 0),
        ("other_stock", "insufficient", 0, 1, "TCS", 0),
    ):
        results[name] = _observe(
            root / name, mode, days=days, minutes=minutes, symbol=symbol, shift=shift
        )
    results["revision"] = _rolling_observe(root / "revision", shift=1)
    results["newer_high"] = _advanced(root / "newer_high", 3)
    return results


@pytest.mark.parametrize(
    "name,relation",
    [
        ("above", "ABOVE"),
        ("at", "AT"),
        ("below", "BELOW"),
        ("invalidated", "BELOW"),
        ("nearest_above", "ABOVE"),
        ("nearest_below", "BELOW"),
    ],
)
def test_exact_relation_and_decimal_context(admitted, name, relation):
    previous, current = admitted["previous"], admitted[name]
    expected = _level(previous, current)
    assert (expected["status"], expected["relation"]) == ("OBSERVED", relation)
    assert (
        expected["reason"]
        == "LATEST_COMPLETED_CLOSE_COMPARED_WITH_ORIGINAL_BROKEN_HIGH"
    )
    for precision in (1, 5, 60):
        with localcontext() as context:
            context.prec = precision
            assert _level(previous, current) == expected
    witness = expected["witness"]
    baseline = expected["previous"]["candidate"]
    continuity = observe_setup_event_continuity_v1(previous, current)
    assert (
        witness["original_event_identity_sha256"] == baseline["event_identity_sha256"]
    )
    assert witness["original_high_identity_sha256"] == baseline["pivot_identity_sha256"]
    assert (
        witness["represented_high_identity_sha256"]
        == continuity["current_representation"]["pivot_identity_sha256"]
    )
    assert (
        witness["original_high_confirmation_session"]
        < witness["original_event_session"]
        < witness["current_completed_session"]
    )
    feature = current.packet.members[0].feature("MARKET_STRUCTURE")
    assert (
        witness["current_bar_identity_sha256"]
        == feature.source_bars[-1].source_row_identity_sha256
        == feature.fact.calculation.input_bar_identities_sha256[-1]
    )


def test_distinct_relation_and_independent_structural_invalidation(admitted):
    previous = admitted["previous"]
    for name, invalidated in (
        ("above", False),
        ("below", False),
        ("invalidated", True),
    ):
        current = admitted[name]
        assert (
            observe_setup_event_continuity_v1(previous, current)["status"]
            == "SAME_EVENT"
        )
        invalidation = observe_setup_invalidation_v1(previous, current)
        assert invalidation["status"] == (
            "INVALIDATED" if invalidated else "NO_CONTRADICTION_OBSERVED"
        )
        assert (
            observe_setup_age_v1(previous, current)["completed_sessions_elapsed"] == 1
        )
        report = _level(previous, current)
        assert report["relation"] == ("ABOVE" if name == "above" else "BELOW")
        assert not any(
            key in report
            for key in ("eligible", "valid", "recommended", "trade", "invalidation")
        )


def test_newer_confirmed_high_cannot_replace_original(admitted):
    previous, current = admitted["baseline"], admitted["newer_high"]
    pivots = (
        current.packet.members[0].feature("MARKET_STRUCTURE").fact.calculation.pivots
    )
    highs = [p for p in pivots if p.kind == "SWING_HIGH"]
    assert highs[-1].price == Decimal(140)
    report = _level(previous, current)
    assert (
        report["relation"] == "ABOVE"
    )  # latest134 is above original130 but below newer140
    assert (
        report["witness"]["original_high_pivot_session"] < highs[-1].session.isoformat()
    )


@pytest.mark.parametrize(
    "left,right,status",
    [
        ("baseline", "baseline", "REPLAY"),
        ("baseline", "refresh", "NO_LATER_SESSION"),
        ("baseline", "unknown", "UNKNOWN"),
        ("unknown_base", "refresh", "UNKNOWN"),
        ("negative_base", "refresh", "NO_BASELINE"),
        ("baseline", "negative", "NOT_REPRESENTED"),
        ("baseline", "outside", "OUTSIDE_WINDOW"),
        ("baseline", "revision", "REVISED_EVENT"),
        ("baseline", "other_stock", "NON_COMPARABLE"),
        ("refresh", "baseline", "NON_COMPARABLE"),
    ],
)
def test_non_relation_states_retain_admitted_meaning(admitted, left, right, status):
    previous, current = admitted[left], admitted[right]
    report = _level(previous, current)
    assert report["status"] == status
    assert report["relation"] is None and report["witness"] is None
    continuity = observe_setup_event_continuity_v1(previous, current)
    assert report["continuity_identity_sha256"] == continuity["result_identity_sha256"]
    if status == "NO_LATER_SESSION":
        assert report["reason"] == "NO_COMPLETED_SESSION_AFTER_ORIGINAL_EVENT"
    else:
        assert report["reason"] == continuity["reason"]


@pytest.mark.parametrize("side", ["previous", "current"])
@pytest.mark.parametrize(
    "mutation",
    [
        "runtime",
        "diagnostics",
        "knowledge",
        "mapping",
        "packet",
        "source",
        "bar",
        "bar_identity",
        "count",
        "anchor_missing",
        "anchor_duplicate",
        "broken_level",
        "event_duplicate",
    ],
)
def test_complete_admission_terminal_before_unknown(admitted, side, mutation):
    value = copy.copy(admitted["baseline"])
    unknown = admitted["unknown"]
    feature = value.packet.members[0].feature("MARKET_STRUCTURE")
    calculation = feature.fact.calculation
    target, field, changed = {
        "runtime": (value, "runtime_code_identity_sha256", "0" * 64),
        "diagnostics": (value, "code", "PRIVATE_TOKEN_PATH"),
        "knowledge": (
            value,
            "evidence_known_at",
            value.acquisition_deadline + timedelta(minutes=1),
        ),
        "mapping": (
            value.packet.mapping_projection.members[0],
            "mapping_version",
            "forged",
        ),
        "packet": (value.packet, "result_identity_sha256", "0" * 64),
        "source": (
            value.packet.source("MARKET_STRUCTURE"),
            "admitted_sessions",
            tuple(reversed(value.packet.source("MARKET_STRUCTURE").admitted_sessions)),
        ),
        "bar": (feature.source_bars[-1], "close", Decimal("NaN")),
        "bar_identity": (
            feature.source_bars[-1],
            "source_row_identity_sha256",
            "0" * 64,
        ),
        "count": (
            feature,
            "source_bars",
            feature.source_bars + (feature.source_bars[-1],),
        ),
        "anchor_missing": (calculation, "pivots", ()),
        "anchor_duplicate": (
            calculation,
            "pivots",
            calculation.pivots + calculation.pivots,
        ),
        "broken_level": (calculation.events[-1], "broken_level", Decimal(1)),
        "event_duplicate": (
            calculation,
            "events",
            calculation.events + calculation.events,
        ),
    }[mutation]
    assert _level(value, value)["status"] == "REPLAY"
    original = getattr(target, field)
    try:
        object.__setattr__(target, field, changed)
        with pytest.raises((ValueError, TypeError)):
            _level(value, unknown) if side == "previous" else _level(unknown, value)
    finally:
        object.__setattr__(target, field, original)


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "digest", "continuity_digest"]
)
def test_source_inventory_terminal_even_with_unknown(admitted, monkeypatch, mutation):
    module = importlib.import_module(MODULE)
    if mutation == "continuity_digest":
        upstream = importlib.import_module(
            MODULE.replace("setup_level", "setup_event_continuity")
        )
        mapping = upstream.SETUP_EVENT_CONTINUITY_RUNTIME_SOURCE_SHA256_V1
        monkeypatch.setitem(mapping, next(iter(mapping)), "0" * 64)
    else:
        mapping = dict(module.SETUP_LEVEL_RUNTIME_SOURCE_SHA256_V1)
        first = next(iter(mapping))
        if mutation == "missing":
            del mapping[first]
        elif mutation == "extra":
            mapping["src/unapproved.py"] = "0" * 64
        else:
            mapping[first] = "0" * 64
        monkeypatch.setattr(module, "SETUP_LEVEL_RUNTIME_SOURCE_SHA256_V1", mapping)
    with pytest.raises(ValueError):
        _level(admitted["baseline"], admitted["unknown"])


def test_pure_retry_concurrency_privacy_and_once_continuity(admitted, monkeypatch):
    module = importlib.import_module(MODULE)
    original = module.observe_setup_event_continuity_v1
    calls = []

    def observe(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(module, "observe_setup_event_continuity_v1", observe)
    previous, current = admitted["previous"], admitted["above"]
    snapshots = [o.canonical_json_bytes() for o in (previous, current)]
    report = _level(previous, current)
    assert len(calls) == 1
    raw = canonical_comparison_bytes(report)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _level(previous, current), range(3)))
    assert all(canonical_comparison_bytes(r) == raw for r in results)
    assert snapshots == [o.canonical_json_bytes() for o in (previous, current)]
    assert not any(
        token in raw
        for token in (
            b'"close"',
            b'"price"',
            b'"bars"',
            b'"volume"',
            b'"broken_level"',
            b'"body"',
            b"/tmp/",
        )
    )


@pytest.mark.parametrize(
    "left,right,code",
    [
        ("previous", "above", 0),
        ("previous", "at", 0),
        ("previous", "below", 0),
        ("baseline", "baseline", 0),
        ("baseline", "refresh", 0),
        ("baseline", "unknown", 1),
        ("negative_base", "refresh", 0),
        ("baseline", "negative", 1),
        ("baseline", "outside", 1),
        ("baseline", "revision", 1),
    ],
)
def test_cli_exit_and_exact_complete_bytes(
    admitted, tmp_path, capsys, left, right, code
):
    previous, current = admitted[left], admitted[right]
    args = _args(tmp_path)
    args[0] = "setup-level"
    for side, value in (("previous", previous), ("current", current)):
        args[args.index("--" + side + "-selection-time") + 1] = (
            value.data_selection_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )
    values = iter((previous, current))
    assert (
        importlib.import_module(MODULE + "_cli").main(
            args, observation_service=lambda *a, **kw: next(values)
        )
        == code
    )
    out = capsys.readouterr()
    assert out.err == "" and out.out.encode() == canonical_comparison_bytes(
        _level(previous, current)
    )


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--symbol", "pnb"),
        ("--symbol", "bad/stock"),
        ("--storage-root", "relative"),
        ("--previous-selection-time", "invalid"),
        ("--current-selection-time", "2026-08-26T04:15:00+05:30"),
        ("--previous-selection-time", "2027-01-01T00:00:00.000000Z"),
        ("--output", "text"),
    ],
)
def test_cli_invalid_requests_have_zero_effects(tmp_path, capsys, flag, value):
    args = _args(tmp_path)
    args[0] = "setup-level"
    args[args.index(flag) + 1] = value
    calls = []
    assert (
        importlib.import_module(MODULE + "_cli").main(
            args, observation_service=lambda *a, **k: calls.append(1)
        )
        == 2
    )
    assert not calls
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "request_invalid\n")


@pytest.mark.parametrize("stage", ["first", "second", "comparison", "serialization"])
@pytest.mark.parametrize("exception", [ValueError, KeyboardInterrupt])
def test_cli_interruption_and_explicit_retry(
    admitted, tmp_path, capsys, monkeypatch, stage, exception
):
    cli = importlib.import_module(MODULE + "_cli")
    value = admitted["baseline"]

    def interrupt(*a, **kw):
        raise exception("PRIVATE_BODY_PATH")

    calls = []

    def service(*a, **kw):
        calls.append(1)
        if (stage == "first" and len(calls) == 1) or (
            stage == "second" and len(calls) == 2
        ):
            interrupt()
        return value

    args = _args(tmp_path)
    args[0] = "setup-level"
    with monkeypatch.context() as patch:
        if stage == "comparison":
            patch.setattr(cli, "observe_setup_level_v1", interrupt)
        if stage == "serialization":
            patch.setattr(cli, "canonical_comparison_bytes", interrupt)
        assert cli.main(args, observation_service=service) == 2
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "setup_level_failed\n")
    assert cli.main(args, observation_service=lambda *a, **kw: value) == 0
    out = capsys.readouterr()
    assert (
        out.out.encode() == canonical_comparison_bytes(_level(value, value))
        and not out.err
    )


@pytest.mark.parametrize(
    "field,changed",
    [("symbol", "TCS"), ("question", "PRICE_BEHAVIOR"), ("data_selection_time", None)],
)
def test_returned_selectors_fail_without_partial_output(
    admitted, tmp_path, capsys, field, changed
):
    value = copy.copy(admitted["baseline"])
    object.__setattr__(value, field, changed)
    args = _args(tmp_path)
    args[0] = "setup-level"
    assert (
        importlib.import_module(MODULE + "_cli").main(
            args, observation_service=lambda *a, **kw: value
        )
        == 2
    )
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "setup_level_failed\n")


def test_output_bound_exact_plus_one_and_terminal_cli(
    admitted, tmp_path, capsys, monkeypatch
):
    report = _level(admitted["baseline"], admitted["baseline"])
    report["padding"] = ""
    overhead = len(canonical_comparison_bytes(report))
    report["padding"] = "x" * (encoding.MAX_OUTPUT - overhead)
    assert len(canonical_comparison_bytes(report)) == 1024 * 1024
    report["padding"] += "x"
    with pytest.raises(ValueError):
        canonical_comparison_bytes(report)
    monkeypatch.setattr(encoding, "MAX_OUTPUT", 1)
    args = _args(tmp_path)
    args[0] = "setup-level"
    assert (
        importlib.import_module(MODULE + "_cli").main(
            args, observation_service=lambda *a, **kw: admitted["baseline"]
        )
        == 2
    )
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "setup_level_failed\n")


@pytest.mark.parametrize("limitations", [("x",) * 33, ("x" * 1025,)])
def test_metadata_limit_plus_one_before_unknown(admitted, limitations):
    value = copy.copy(admitted["baseline"])
    object.__setattr__(value, "limitations", limitations)
    with pytest.raises(ValueError):
        _level(value, admitted["unknown"])


def test_caller_authored_report_cannot_substitute_for_typed_admission(admitted):
    with pytest.raises(ValueError):
        _level({}, admitted["unknown"])


@pytest.mark.parametrize(
    "scenario,relation,status,code",
    [
        ("above", "ABOVE", "OBSERVED", 0),
        ("at", "AT", "OBSERVED", 0),
        ("below", "BELOW", "OBSERVED", 0),
        ("replay", None, "REPLAY", 0),
        ("unknown", None, "UNKNOWN", 1),
    ],
)
def test_guarded_real_producer_demo(scenario, relation, status, code):
    root = Path(__file__).resolve().parents[2]
    path = root / "examples/causal_setup_level_demo.py"
    if not path.exists():
        path = root / "examples/causal_setup_evidence_demo.py"
        scenario = {"above": "same-event", "at": "same-event", "below": "wick"}.get(
            scenario, scenario
        )
    result = subprocess.run(  # noqa: S603 - fixed project fixture and closed scenario
        [sys.executable, str(path), "--scenario", scenario],
        cwd=root,
        capture_output=True,
        check=False,
    )
    assert result.returncode == code
    report = json.loads(result.stdout)
    assert report["contract_version"] == "causal-setup-level@v1"
    assert (report["relation"], report["status"]) == (relation, status)
    assert b"SYNTHETIC" in result.stderr and b"not current market data" in result.stderr


@pytest.mark.parametrize(
    "mutation", ["price_basis", "source_profile", "latest_session"]
)
def test_unsupported_basis_or_changed_bar_session_is_terminal(admitted, mutation):
    value = copy.copy(admitted["above"])
    feature = value.packet.members[0].feature("MARKET_STRUCTURE")
    targets = {
        "price_basis": (value.packet.members[0], "price_basis", "RAW"),
        "source_profile": (
            value.packet.source("MARKET_STRUCTURE"),
            "source_profile",
            "SUBSTITUTED_SOURCE",
        ),
        "latest_session": (
            feature.source_bars[-1],
            "session",
            feature.source_bars[-1].session - timedelta(days=1),
        ),
    }
    target, field, changed = targets[mutation]
    assert _level(admitted["previous"], value)["status"] == "OBSERVED"
    original = getattr(target, field)
    try:
        object.__setattr__(target, field, changed)
        with pytest.raises(ValueError):
            _level(admitted["previous"], value)
    finally:
        object.__setattr__(target, field, original)


def test_metadata_exact_limit_remains_admitted(admitted):
    value = copy.copy(admitted["baseline"])
    object.__setattr__(value, "limitations", ("x" * 1024,) * 32)
    assert _level(value, value)["status"] == "REPLAY"
