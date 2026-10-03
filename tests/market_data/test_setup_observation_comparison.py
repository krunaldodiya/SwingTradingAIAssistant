"""Behavioral tests using actual synthetic producer admission."""

from __future__ import annotations

import importlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest
from test_current_stock_research import _NOW, _Clock
from test_setup_screen import _service, _SetupPrices

from swing_trading_ai_assistant.market_data.bharatstock import BharatStockClient

MODULE = "swing_trading_ai_assistant.research_comparison.setup_observation_comparison"


class _TimedPrices(_SetupPrices):
    def __init__(self, mode, shift, now):
        super().__init__(mode, shift)
        self.now = now

    def history(self, instrument, start, end, **kwargs):
        history = super().history(instrument, start, end, **kwargs)
        sessions = tuple(
            start + timedelta(days=offset)
            for offset in range((end - start).days + 1)
            if (start + timedelta(days=offset)).weekday() < 5
        )[-len(history.rows) :]
        return replace(
            history,
            retrieved_at=self.now,
            rows=tuple(
                replace(row, session=session)
                for row, session in zip(history.rows, sessions, strict=True)
            ),
        )


def _observe(root, mode="positive", *, minutes=0, days=0, shift=0, symbol="PNB"):
    root.mkdir(mode=0o700)
    clock = _Clock()
    clock.value = _NOW + timedelta(minutes=minutes, days=days)
    return _service(mode)(
        symbol,
        root,
        question="CURRENT_STRUCTURE",
        clock=clock,
        price_client=cast(BharatStockClient, _TimedPrices(mode, shift, clock.value)),
    )


@pytest.mark.parametrize(
    "before,after,shift,expected",
    [
        ("positive", "positive", 0, "SAME_EVENT"),
        ("positive", "positive", 1, "REVISED_EVENT"),
        ("negative", "negative", 0, "NO_MATCH"),
        ("negative", "positive", 0, "APPEARED"),
        ("positive", "negative", 0, "ABSENT"),
        ("positive", "insufficient", 0, "UNKNOWN"),
        ("insufficient", "positive", 0, "UNKNOWN"),
    ],
)
def test_real_producer_factual_cases(tmp_path, before, after, shift, expected):
    compare = importlib.import_module(MODULE).compare_setup_observations_v1
    previous = _observe(tmp_path / "previous", before)
    current = _observe(tmp_path / "current", after, minutes=1, shift=shift)
    result = compare(previous, current)
    assert result["status"] == expected
    assert (
        result["previous_observation_identity_sha256"]
        != result["current_observation_identity_sha256"]
    )
    assert "not invalidation or expiry" in " ".join(result["limitations"])


def test_new_completed_session_is_different_event_not_new_opportunity(tmp_path):
    compare = importlib.import_module(MODULE).compare_setup_observations_v1
    previous = _observe(tmp_path / "previous")
    current = _observe(tmp_path / "current", days=1)
    result = compare(previous, current)
    assert result["status"] == "DIFFERENT_EVENT"
    assert (
        result["previous"]["candidate"]["event_session"]
        < result["current"]["candidate"]["event_session"]
    )


def test_different_stock_is_noncomparable_before_unknown(tmp_path):
    compare = importlib.import_module(MODULE).compare_setup_observations_v1
    previous = _observe(tmp_path / "previous")
    current = _observe(tmp_path / "current", "insufficient", minutes=1, symbol="TCS")
    result = compare(previous, current)
    assert result["status"] == "NON_COMPARABLE"
    assert result["reason"] == "INCOMPATIBLE_STOCK"


@pytest.mark.parametrize(
    "field,value",
    [
        ("runtime_code_identity_sha256", "0" * 64),
        ("evidence_known_at", _NOW - timedelta(days=1)),
        ("code", "PRIVATE_BODY_ALPHABET_SAFE"),
        ("question", "PRICE_BEHAVIOR"),
    ],
)
@pytest.mark.parametrize("side", ["previous", "current"])
def test_mutation_terminal_even_with_unknown(tmp_path, field, value, side):
    compare = importlib.import_module(MODULE).compare_setup_observations_v1
    previous = _observe(tmp_path / "previous")
    current = _observe(tmp_path / "current", "insufficient", minutes=1)
    object.__setattr__(previous if side == "previous" else current, field, value)
    with pytest.raises(ValueError):
        compare(previous, current)


def test_reversed_time_noncomparable(tmp_path):
    compare = importlib.import_module(MODULE).compare_setup_observations_v1
    previous = _observe(tmp_path / "previous")
    current = _observe(tmp_path / "current", minutes=1)
    result = compare(current, previous)
    assert result["status"] == "NON_COMPARABLE"
    assert result["reason"] == "INVALID_TEMPORAL_ORDER"


def _args(root, *, minutes=0):
    return [
        "setup-compare",
        "--symbol",
        "PNB",
        "--storage-root",
        str(root),
        "--previous-selection-time",
        "2026-08-26T04:15:00.000000Z",
        "--current-selection-time",
        (_NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "--output",
        "json",
    ]


def test_actual_cli_replay(tmp_path, capsys):
    main = importlib.import_module(MODULE + "_cli").main

    observation = _observe(tmp_path / "observed")
    calls = []

    def service(symbol, root, *, question, selection_time):
        calls.append((symbol, question, selection_time))
        return observation

    assert main(_args(tmp_path), observation_service=service) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == "REPLAY"
    assert len(calls) == 2
    assert all(call[1] == "CURRENT_STRUCTURE" for call in calls)
    assert output.err == ""


def test_cli_interrupted_second_call_no_partial_output(tmp_path, capsys):
    main = importlib.import_module(MODULE + "_cli").main

    observation = _observe(tmp_path / "observed")
    calls = []

    def service(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise ValueError("PRIVATE_PATH_AND_PROVIDER_BODY")
        return observation

    assert main(_args(tmp_path), observation_service=service) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "setup_comparison_failed\n"


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--symbol", "pnb"),
        ("--symbol", ""),
        ("--symbol", "P" * 33),
        ("--storage-root", "relative"),
        ("--previous-selection-time", "2026-08-26"),
        ("--previous-selection-time", "2026-08-27T04:15:00.000000Z"),
    ],
)
def test_cli_invalid_request_zero_effects(tmp_path, capsys, flag, value):
    main = importlib.import_module(MODULE + "_cli").main

    args = _args(tmp_path)
    args[args.index(flag) + 1] = value
    calls = []
    assert main(args, observation_service=lambda *a, **kw: calls.append(1)) == 2
    assert calls == []
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "request_invalid\n"


def test_concurrent_pure_comparison_does_not_write(tmp_path):

    compare = importlib.import_module(MODULE).compare_setup_observations_v1
    observation = _observe(tmp_path / "observed")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: compare(observation, observation), range(4)))
    assert all(result == results[0] for result in results)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_output_limit_and_plus_one():
    module = importlib.import_module(MODULE)
    report = {"x": ""}
    overhead = len(module.canonical_comparison_bytes(report))
    report["x"] = "a" * (module.MAX_OUTPUT - overhead)
    assert len(module.canonical_comparison_bytes(report)) == module.MAX_OUTPUT
    report["x"] += "a"
    with pytest.raises(ValueError):
        module.canonical_comparison_bytes(report)


@pytest.mark.parametrize("mutation", ["missing", "extra", "digest"])
def test_runtime_manifest_closed_inventory(tmp_path, monkeypatch, mutation):
    module = importlib.import_module(MODULE)
    observation = _observe(tmp_path / "observed")
    mapping = dict(module.SETUP_COMPARISON_RUNTIME_SOURCE_SHA256_V1)
    first = next(iter(mapping))
    if mutation == "missing":
        del mapping[first]
    elif mutation == "extra":
        mapping["src/swing_trading_ai_assistant/market_data/__init__.py"] = "0" * 64
    else:
        mapping[first] = "0" * 64
    monkeypatch.setattr(module, "SETUP_COMPARISON_RUNTIME_SOURCE_SHA256_V1", mapping)
    with pytest.raises(ValueError):
        module.compare_setup_observations_v1(observation, observation)


@pytest.mark.parametrize("side", ["previous", "current"])
@pytest.mark.parametrize("mutation", ["anchor", "duplicate", "packet_identity"])
def test_packet_integrity_failure_precedes_unknown(tmp_path, side, mutation):
    compare = importlib.import_module(MODULE).compare_setup_observations_v1
    observed = _observe(tmp_path / "observed")
    unknown = _observe(tmp_path / "unknown", "insufficient", minutes=1)
    packet = observed.packet
    calculation = packet.members[0].feature("MARKET_STRUCTURE").fact.calculation
    if mutation == "anchor":
        object.__setattr__(calculation, "pivots", ())
    elif mutation == "duplicate":
        object.__setattr__(
            calculation, "events", calculation.events + calculation.events
        )
    else:
        object.__setattr__(packet, "result_identity_sha256", "0" * 64)
    with pytest.raises(ValueError):
        compare(observed, unknown) if side == "previous" else compare(unknown, observed)


@pytest.mark.parametrize("mode", ["negative", "insufficient"])
def test_replay_retains_original_detection_state(tmp_path, mode):
    compare = importlib.import_module(MODULE).compare_setup_observations_v1
    observation = _observe(tmp_path / "observed", mode)
    result = compare(observation, observation)
    assert result["status"] == "REPLAY"
    assert result["previous"]["status"] == (
        "NO_MATCH" if mode == "negative" else "UNKNOWN"
    )


def test_nonpacket_unknown_and_private_symbol_rejection(tmp_path):
    from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (  # noqa: PLC0415
        CurrentStockResearchResultV2,
        _runtime_identity,
    )

    compare = importlib.import_module(MODULE).compare_setup_observations_v1
    observed = _observe(tmp_path / "observed")
    unknown = CurrentStockResearchResultV2(
        "current-stock-research@v2",
        "UNAVAILABLE",
        "mapping",
        "MAPPING_UNAVAILABLE",
        "CURRENT_STRUCTURE",
        "PNB",
        _NOW + timedelta(minutes=1),
        _NOW + timedelta(minutes=31),
        _runtime_identity(),
        None,
        ("not_trade_eligibility",),
    )
    assert compare(observed, unknown)["status"] == "UNKNOWN"
    unsafe = replace(unknown, symbol="PRIVATE_PATH_TOKEN/OWNER")
    with pytest.raises(ValueError):
        compare(unsafe, unsafe)


@pytest.mark.parametrize("limitations", [("x",) * 33, ("x" * 1025,)])
def test_input_limitations_bound_before_serialization(tmp_path, limitations):
    compare = importlib.import_module(MODULE).compare_setup_observations_v1
    observed = _observe(tmp_path / "observed")
    changed = replace(observed, limitations=limitations)
    with pytest.raises(ValueError):
        compare(changed, changed)


def test_public_candidate_comparison_exists_and_replays_admitted_observation(
    tmp_path: Path,
) -> None:
    assert importlib.util.find_spec(MODULE) is not None, (
        "candidate comparison SDK absent"
    )
    compare = importlib.import_module(MODULE).compare_setup_observations_v1
    observation = _service("positive")("PNB", tmp_path, question="CURRENT_STRUCTURE")
    result = compare(observation, observation)
    assert result["status"] == "REPLAY"
    assert result["previous"]["status"] == "MATCH"
    assert result == compare(observation, observation)
    assert (
        result["previous_observation_identity_sha256"]
        == result["current_observation_identity_sha256"]
    )
    serialized = json.dumps(result)
    assert str(tmp_path) not in serialized
    assert '"close"' not in serialized


def test_comparison_admits_both_inputs_before_replay(tmp_path: Path) -> None:
    compare = importlib.import_module(MODULE).compare_setup_observations_v1
    observation = _service("positive")("PNB", tmp_path, question="CURRENT_STRUCTURE")
    forged = replace(observation, runtime_code_identity_sha256="0" * 64)
    with pytest.raises(ValueError):
        compare(forged, forged)


def test_equal_selection_nonidentical_observations_not_comparable(
    tmp_path: Path,
) -> None:
    compare = importlib.import_module(MODULE).compare_setup_observations_v1
    first_root, second_root = tmp_path / "first", tmp_path / "second"
    first_root.mkdir(mode=0o700)
    second_root.mkdir(mode=0o700)
    first = _service("positive")("PNB", first_root, question="CURRENT_STRUCTURE")
    second = _service("negative")("PNB", second_root, question="CURRENT_STRUCTURE")
    result = compare(first, second)
    assert result["status"] == "NON_COMPARABLE"
    assert result["reason"] == "INVALID_TEMPORAL_ORDER"
