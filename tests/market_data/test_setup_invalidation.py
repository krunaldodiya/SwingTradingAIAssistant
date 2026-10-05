"""Anchored contradiction expectations using the actual admitted producer."""

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
from swing_trading_ai_assistant.research_comparison import (
    setup_observation_comparison as encoding,
)
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (
    canonical_comparison_bytes,
)

MODULE = "swing_trading_ai_assistant.research_comparison.setup_invalidation"


class _AnchoredPrices(_TimedPrices):
    def __init__(
        self, now, *, later=False, close=89, wick=80, original=True, low_revision=0
    ):
        super().__init__("positive", 0, now)
        self.later, self.close, self.wick = later, close, wick
        self.original, self.low_revision = original, low_revision

    def history(self, instrument, start, end, **kwargs):
        history = super().history(instrument, start, end, **kwargs)
        prior = super().history(
            instrument,
            start - timedelta(days=int(self.later)),
            end - timedelta(days=int(self.later)),
            **kwargs,
        )
        rows = list(prior.rows)
        if self.original:
            # Prevent S18 from confirming a new low on the original BOS day.
            # The original pre-BOS HL is S13, price 90, confirmed at S15.
            rows[18] = replace(rows[18], low=Decimal(98))
            rows[19] = replace(rows[19], low=Decimal(99))
        if self.low_revision:
            rows[13] = replace(rows[13], low=rows[13].low + self.low_revision)
        if self.later:
            last = replace(
                history.rows[-1],
                open=Decimal(134),
                high=Decimal(139),
                low=Decimal(self.wick),
                close=Decimal(self.close),
            )
            rows = rows[1:] + [last]
        return replace(history, rows=tuple(rows))


def _anchored(root, *, later=False, **kwargs):
    root.mkdir(mode=0o700)
    clock = _Clock()
    clock.value = _NOW + timedelta(days=int(later))
    return _service()(
        "PNB",
        root,
        question="CURRENT_STRUCTURE",
        clock=clock,
        price_client=cast(
            BharatStockClient, _AnchoredPrices(clock.value, later=later, **kwargs)
        ),
    )


def test_actual_cli_anchored_contradiction(tmp_path, capsys):
    main = importlib.import_module(MODULE + "_cli").main
    previous = _anchored(tmp_path / "previous")
    current = _anchored(tmp_path / "current", later=True)
    args = _args(tmp_path)
    args[0] = "setup-invalidation"
    args[args.index("--current-selection-time") + 1] = (
        current.data_selection_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    values = iter((previous, current))
    assert main(args, observation_service=lambda *a, **kw: next(values)) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "INVALIDATED"
    assert report["contradiction"]["event"] == "CHOCH"
    assert (
        report["contradiction"]["pivot_session"]
        == report["original_supporting_low"]["pivot_session"]
    )


@pytest.mark.parametrize("close,wick", [(134, 120), (100, 80), (90, 80)])
def test_absence_wick_or_equal_close_does_not_invalidate(tmp_path, close, wick):
    observe = importlib.import_module(MODULE).observe_setup_invalidation_v1
    previous = _anchored(tmp_path / "previous")
    current = _anchored(tmp_path / "current", later=True, close=close, wick=wick)
    report = observe(previous, current)
    assert report["status"] == "NO_CONTRADICTION_OBSERVED"
    assert report["current"]["status"] == "NO_MATCH"
    assert report["contradiction"] is None


def test_later_confirmed_other_low_choch_is_not_original_contradiction(tmp_path):
    observe = importlib.import_module(MODULE).observe_setup_invalidation_v1
    previous = _anchored(tmp_path / "previous", original=False)
    current = _anchored(
        tmp_path / "current", later=True, close=95, wick=80, original=False
    )
    calculation = current.packet.members[0].feature("MARKET_STRUCTURE").fact.calculation
    assert any(e.event == "CHOCH" and e.direction == "DOWN" for e in calculation.events)
    report = observe(previous, current)
    assert report["status"] == "NO_CONTRADICTION_OBSERVED"
    assert (
        report["original_supporting_low"]["pivot_confirmation_session"]
        < report["previous"]["candidate"]["event_session"]
    )


def test_supporting_low_revision_is_not_invalidation(tmp_path):
    observe = importlib.import_module(MODULE).observe_setup_invalidation_v1
    previous = _anchored(tmp_path / "previous")
    current = _anchored(tmp_path / "current", later=True, low_revision=1)
    report = observe(previous, current)
    assert report["status"] == "REVISED_EVIDENCE"
    assert report["reason"] == "ORIGINAL_SUPPORTING_LOW_REVISED"
    assert report["contradiction"] is None


@pytest.mark.parametrize(
    "before,after,days,shift,expected",
    [
        ("positive", "positive", 0, 0, "NO_CONTRADICTION_OBSERVED"),
        ("positive", "positive", 0, 1, "REVISED_EVIDENCE"),
        ("positive", "negative", 0, 0, "NOT_REPRESENTED"),
        ("negative", "positive", 0, 0, "NO_BASELINE"),
        ("negative", "insufficient", 0, 0, "NO_BASELINE"),
        ("insufficient", "positive", 0, 0, "UNKNOWN"),
        ("positive", "insufficient", 0, 0, "UNKNOWN"),
        ("positive", "positive", 35, 0, "OUTSIDE_WINDOW"),
    ],
)
def test_admitted_revision_absence_unknown_and_window_states(
    tmp_path, before, after, days, shift, expected
):
    observe = importlib.import_module(MODULE).observe_setup_invalidation_v1
    previous = _observe(tmp_path / "previous", before)
    current = _observe(tmp_path / "current", after, days=days, minutes=1, shift=shift)
    report = observe(previous, current)
    assert report["status"] == expected
    assert report["contradiction"] is None


@pytest.mark.parametrize(
    "mode,expected",
    [("positive", "REPLAY"), ("negative", "NO_BASELINE"), ("insufficient", "UNKNOWN")],
)
def test_replay_never_creates_new_contradiction(tmp_path, mode, expected):
    observe = importlib.import_module(MODULE).observe_setup_invalidation_v1
    value = _observe(tmp_path / "value", mode)
    assert observe(value, value)["status"] == expected


def test_noncomparable_and_reversed_time(tmp_path):
    observe = importlib.import_module(MODULE).observe_setup_invalidation_v1
    before = _observe(tmp_path / "previous")
    after = _observe(tmp_path / "current", "insufficient", minutes=1, symbol="TCS")
    assert observe(before, after)["status"] == "NON_COMPARABLE"
    assert observe(after, before)["status"] == "NON_COMPARABLE"


@pytest.mark.parametrize("side", ["previous", "current"])
@pytest.mark.parametrize(
    "mutation",
    [
        "type",
        "runtime",
        "diagnostic",
        "anchor",
        "duplicate",
        "packet_identity",
        "knowledge",
        "metadata",
    ],
)
def test_integrity_precedes_unknown(tmp_path, side, mutation):
    observe = importlib.import_module(MODULE).observe_setup_invalidation_v1
    value = _anchored(tmp_path / "value", later=True)
    unknown = _observe(tmp_path / "unknown", "insufficient", minutes=1)
    calculation = value.packet.members[0].feature("MARKET_STRUCTURE").fact.calculation
    if mutation == "type":
        value = {}
    elif mutation == "runtime":
        object.__setattr__(value, "runtime_code_identity_sha256", "0" * 64)
    elif mutation == "diagnostic":
        object.__setattr__(value, "code", "PRIVATE_TOKEN")
    elif mutation == "anchor":
        object.__setattr__(calculation, "pivots", ())
    elif mutation == "duplicate":
        object.__setattr__(
            calculation, "events", calculation.events + calculation.events
        )
    elif mutation == "packet_identity":
        object.__setattr__(value.packet, "result_identity_sha256", "0" * 64)
    elif mutation == "metadata":
        object.__setattr__(value, "limitations", ("x" * 1025,))
    else:
        object.__setattr__(
            value,
            "evidence_known_at",
            value.acquisition_deadline + timedelta(minutes=1),
        )
    with pytest.raises(ValueError):
        observe(value, unknown) if side == "previous" else observe(unknown, value)


@pytest.mark.parametrize("mutation", ["missing", "extra", "digest"])
def test_runtime_inventory_closed(tmp_path, monkeypatch, mutation):
    module = importlib.import_module(MODULE)
    value = _observe(tmp_path / "value")
    mapping = dict(module.SETUP_INVALIDATION_RUNTIME_SOURCE_SHA256_V1)
    first = next(iter(mapping))
    if mutation == "missing":
        del mapping[first]
    elif mutation == "extra":
        mapping["src/unapproved.py"] = "0" * 64
    else:
        mapping[first] = "0" * 64
    monkeypatch.setattr(module, "SETUP_INVALIDATION_RUNTIME_SOURCE_SHA256_V1", mapping)
    with pytest.raises(ValueError):
        module.observe_setup_invalidation_v1(value, value)


def test_concurrent_retry_identity_privacy_and_no_writes(tmp_path):
    observe = importlib.import_module(MODULE).observe_setup_invalidation_v1
    before = _anchored(tmp_path / "before")
    after = _anchored(tmp_path / "after", later=True)
    original = (before.canonical_json_bytes(), after.canonical_json_bytes())
    files = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(lambda _: observe(before, after), range(3)))
    assert all(r == reports[0] for r in reports)
    assert original == (before.canonical_json_bytes(), after.canonical_json_bytes())
    assert files == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    raw = canonical_comparison_bytes(reports[0])
    assert str(tmp_path).encode() not in raw
    assert all(
        ('"' + f + '"').encode() not in raw
        for f in ("close", "price", "broken_level", "bars", "body")
    )
    unsigned = dict(reports[0])
    identity = unsigned.pop("result_identity_sha256")
    assert identity == hashlib.sha256(canonical_comparison_bytes(unsigned)).hexdigest()
    assert (
        reports[0]["previous_observation_identity_sha256"]
        == hashlib.sha256(original[0]).hexdigest()
    )
    assert (
        reports[0]["current_observation_identity_sha256"]
        == hashlib.sha256(original[1]).hexdigest()
    )
    assert (
        reports[0]["original_supporting_low"]["pivot_identity_sha256"]
        != reports[0]["current_supporting_low"]["pivot_identity_sha256"]
    )


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--symbol", "pnb"),
        ("--storage-root", "relative"),
        ("--previous-selection-time", "invalid"),
        ("--previous-selection-time", "2027-01-01T00:00:00.000000Z"),
    ],
)
def test_cli_request_invalid_before_calls(tmp_path, capsys, flag, value):
    main = importlib.import_module(MODULE + "_cli").main
    args = _args(tmp_path)
    args[0] = "setup-invalidation"
    args[args.index(flag) + 1] = value
    calls = []
    assert main(args, observation_service=lambda *a, **kw: calls.append(1)) == 2
    output = capsys.readouterr()
    assert calls == [] and output.out == "" and output.err == "request_invalid\n"


@pytest.mark.parametrize("failure", ["interruption", "selector", "internal"])
def test_second_cli_call_failure_has_no_partial_stdout(tmp_path, capsys, failure):
    main = importlib.import_module(MODULE + "_cli").main
    before = _anchored(tmp_path / "value")
    calls = []

    def port(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return before
        if failure == "interruption":
            raise KeyboardInterrupt()
        if failure == "internal":
            raise RuntimeError("PRIVATE_PATH_OR_TOKEN")
        return before

    args = _args(tmp_path)
    args[0] = "setup-invalidation"
    args[args.index("--current-selection-time") + 1] = (
        _NOW + timedelta(minutes=1)
    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    assert main(args, observation_service=port) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "setup_invalidation_failed\n"
    assert len(calls) == 2 and all(c["question"] == "CURRENT_STRUCTURE" for c in calls)


def test_output_bound_and_plus_one(tmp_path, monkeypatch):
    module = importlib.import_module(MODULE)
    value = _observe(tmp_path / "value")
    report = module.observe_setup_invalidation_v1(value, value)
    raw = encoding.canonical_comparison_bytes(report)
    monkeypatch.setattr(encoding, "MAX_OUTPUT", len(raw))
    assert encoding.canonical_comparison_bytes(report) == raw
    monkeypatch.setattr(encoding, "MAX_OUTPUT", len(raw) - 1)
    with pytest.raises(ValueError):
        encoding.canonical_comparison_bytes(report)
