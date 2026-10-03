"""Continuity expectations from independently admitted synthetic observations."""

from __future__ import annotations

import hashlib
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import cast

import pytest
from test_current_stock_research import _NOW, _Clock
from test_setup_observation_comparison import _args, _observe, _TimedPrices
from test_setup_screen import _service

from swing_trading_ai_assistant.market_data.bharatstock import BharatStockClient
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (
    MAX_OUTPUT,
    canonical_comparison_bytes,
    compare_setup_observations_v1,
)

MODULE = "swing_trading_ai_assistant.research_comparison.setup_event_continuity"


class _RollingPrices(_TimedPrices):
    def history(self, instrument, start, end, **kwargs):
        history = super().history(instrument, start, end, **kwargs)
        # Preserve yesterday's bars at their original sessions. Add one completed
        # neutral bar; the original break moves from position 20 to position 19.
        prior = _TimedPrices("positive", self.shift, _NOW).history(
            instrument, start - timedelta(days=1), end - timedelta(days=1), **kwargs
        )
        last = replace(
            history.rows[-1],
            open=Decimal(134),
            high=Decimal(139),
            low=Decimal(120),
            close=Decimal(134),
        )
        return replace(history, rows=prior.rows[1:] + (last,))


def _rolling_observe(root, *, shift=0):
    root.mkdir(mode=0o700)
    clock = _Clock()
    clock.value = _NOW + timedelta(days=1)
    return _service()(
        "PNB",
        root,
        question="CURRENT_STRUCTURE",
        clock=clock,
        price_client=cast(
            BharatStockClient, _RollingPrices("positive", shift, clock.value)
        ),
    )


def test_real_producer_replay(tmp_path):
    observe = importlib.import_module(MODULE).observe_setup_event_continuity_v1
    previous = _observe(tmp_path / "previous")
    result = observe(previous, previous)
    assert result["status"] == "REPLAY"
    assert result["contract_version"] == "causal-setup-event-continuity@v1"


@pytest.mark.parametrize("shift,expected", [(0, "SAME_EVENT"), (1, "REVISED_EVENT")])
def test_old_event_remains_even_when_latest_screen_is_absent(tmp_path, shift, expected):
    observe = importlib.import_module(MODULE).observe_setup_event_continuity_v1
    previous = _observe(tmp_path / "previous")
    current = _rolling_observe(tmp_path / "current", shift=shift)
    latest = compare_setup_observations_v1(previous, current)
    assert latest["status"] == "ABSENT"
    result = observe(previous, current)
    assert result["status"] == expected
    assert result["current"]["status"] == "NO_MATCH"
    assert (
        result["current_representation"]["event_session"]
        == result["previous"]["candidate"]["event_session"]
    )
    assert (
        result["current_representation"]["event_identity_sha256"]
        != result["previous"]["candidate"]["event_identity_sha256"]
    )


@pytest.mark.parametrize(
    "before,after,days,expected",
    [
        ("negative", "positive", 0, "NO_BASELINE"),
        ("positive", "negative", 0, "NOT_REPRESENTED"),
        ("positive", "insufficient", 0, "UNKNOWN"),
        ("insufficient", "positive", 0, "UNKNOWN"),
        ("positive", "positive", 35, "OUTSIDE_WINDOW"),
    ],
)
def test_distinct_missing_evidence_states(tmp_path, before, after, days, expected):
    observe = importlib.import_module(MODULE).observe_setup_event_continuity_v1
    previous = _observe(tmp_path / "previous", before)
    current = _observe(tmp_path / "current", after, days=days, minutes=1)
    assert observe(previous, current)["status"] == expected


def test_actual_cli_replay(tmp_path, capsys):
    main = importlib.import_module(MODULE + "_cli").main
    previous = _observe(tmp_path / "previous")
    args = _args(tmp_path)
    args[0] = "setup-event-continuity"
    assert main(args, observation_service=lambda *a, **kw: previous) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "REPLAY"


@pytest.mark.parametrize(
    "mode,expected", [("negative", "NO_BASELINE"), ("insufficient", "UNKNOWN")]
)
def test_replay_does_not_invent_baseline(tmp_path, mode, expected):
    observe = importlib.import_module(MODULE).observe_setup_event_continuity_v1
    value = _observe(tmp_path / "observed", mode)
    assert observe(value, value)["status"] == expected


def test_noncomparable_precedes_unknown_and_reversed_time(tmp_path):
    observe = importlib.import_module(MODULE).observe_setup_event_continuity_v1
    previous = _observe(tmp_path / "previous")
    current = _observe(tmp_path / "current", "insufficient", minutes=1, symbol="TCS")
    result = observe(previous, current)
    assert (result["status"], result["reason"]) == (
        "NON_COMPARABLE",
        "INCOMPATIBLE_STOCK",
    )
    result = observe(current, previous)
    assert result["status"] == "NON_COMPARABLE"


@pytest.mark.parametrize("side", ["previous", "current"])
@pytest.mark.parametrize(
    "mutation",
    ["runtime", "diagnostic", "anchor", "duplicate", "packet_identity", "knowledge"],
)
def test_integrity_terminal_with_unknown(tmp_path, side, mutation):
    observe = importlib.import_module(MODULE).observe_setup_event_continuity_v1
    value = _observe(tmp_path / "observed")
    unknown = _observe(tmp_path / "unknown", "insufficient", minutes=1)
    calculation = value.packet.members[0].feature("MARKET_STRUCTURE").fact.calculation
    if mutation == "runtime":
        object.__setattr__(value, "runtime_code_identity_sha256", "0" * 64)
    elif mutation == "diagnostic":
        object.__setattr__(value, "code", "PRIVATE_TOKEN")
    elif mutation == "anchor":
        object.__setattr__(calculation, "pivots", ())
    elif mutation == "duplicate":
        object.__setattr__(
            calculation, "events", calculation.events + calculation.events
        )
    elif mutation == "knowledge":
        object.__setattr__(
            value,
            "evidence_known_at",
            value.acquisition_deadline + timedelta(minutes=1),
        )
    else:
        object.__setattr__(value.packet, "result_identity_sha256", "0" * 64)
    with pytest.raises(ValueError):
        observe(value, unknown) if side == "previous" else observe(unknown, value)


@pytest.mark.parametrize("mutation", ["missing", "extra", "digest"])
def test_runtime_closed_inventory(tmp_path, monkeypatch, mutation):
    module = importlib.import_module(MODULE)
    value = _observe(tmp_path / "observed")
    mapping = dict(module.SETUP_EVENT_CONTINUITY_RUNTIME_SOURCE_SHA256_V1)
    first = next(iter(mapping))
    if mutation == "missing":
        del mapping[first]
    elif mutation == "extra":
        mapping["src/unapproved.py"] = "0" * 64
    else:
        mapping[first] = "0" * 64
    monkeypatch.setattr(
        module, "SETUP_EVENT_CONTINUITY_RUNTIME_SOURCE_SHA256_V1", mapping
    )
    with pytest.raises(ValueError):
        module.observe_setup_event_continuity_v1(value, value)


def test_retry_concurrency_privacy_identity_and_no_writes(tmp_path):
    observe = importlib.import_module(MODULE).observe_setup_event_continuity_v1
    value = _observe(tmp_path / "observed")
    original = value.canonical_json_bytes()
    files = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: observe(value, value), range(3)))
    assert all(r == results[0] for r in results)
    assert original == value.canonical_json_bytes()
    assert files == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    text = json.dumps(results[0])
    assert str(tmp_path) not in text
    assert all(
        f'"{field}"' not in text
        for field in ("close", "price", "broken_level", "bars", "body")
    )
    result = dict(results[0])
    identity = result.pop("result_identity_sha256")
    assert identity == hashlib.sha256(canonical_comparison_bytes(result)).hexdigest()


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--symbol", "pnb"),
        ("--storage-root", "relative"),
        ("--previous-selection-time", "invalid"),
        ("--previous-selection-time", "2027-01-01T00:00:00.000000Z"),
    ],
)
def test_cli_request_rejected_before_effects(tmp_path, capsys, flag, value):
    main = importlib.import_module(MODULE + "_cli").main
    args = _args(tmp_path)
    args[0] = "setup-event-continuity"
    args[args.index(flag) + 1] = value
    calls = []
    assert main(args, observation_service=lambda *a, **kw: calls.append(1)) == 2
    assert calls == []
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "request_invalid\n")


@pytest.mark.parametrize("interruption", [ValueError, KeyboardInterrupt])
def test_cli_second_call_interrupted_no_partial_output(tmp_path, capsys, interruption):
    main = importlib.import_module(MODULE + "_cli").main
    value = _observe(tmp_path / "observed")
    calls = []

    def service(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise interruption("PRIVATE_BODY_PATH")
        return value

    args = _args(tmp_path)
    args[0] = "setup-event-continuity"
    assert main(args, observation_service=service) == 2
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "setup_event_continuity_failed\n")


@pytest.mark.parametrize("limitations", [("x",) * 33, ("x" * 1025,)])
def test_metadata_bound_before_serialization(tmp_path, limitations):
    observe = importlib.import_module(MODULE).observe_setup_event_continuity_v1
    value = replace(_observe(tmp_path / "observed"), limitations=limitations)
    with pytest.raises(ValueError):
        observe(value, value)


def test_output_limit_and_plus_one():
    report = {"x": ""}
    size = len(canonical_comparison_bytes(report))
    report["x"] = "a" * (MAX_OUTPUT - size)
    assert len(canonical_comparison_bytes(report)) == MAX_OUTPUT
    report["x"] += "a"
    with pytest.raises(ValueError):
        canonical_comparison_bytes(report)
