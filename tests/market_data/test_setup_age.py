"""Session age expectations through actual admitted producer and CLI."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import cast

import pytest
from test_current_stock_research import (
    _NOW,
    _Clock,
    _declare_closures,
    _watchlist_sources,
)
from test_setup_event_continuity import _rolling_observe
from test_setup_invalidation import _anchored
from test_setup_observation_comparison import _args, _observe, _TimedPrices
from test_setup_screen import _service

from swing_trading_ai_assistant.market_data.bharatstock import BharatStockClient
from swing_trading_ai_assistant.research_comparison import (
    setup_observation_comparison as encoding,
)

MODULE = "swing_trading_ai_assistant.research_comparison.setup_age"


def test_actual_cli_original_event_has_one_completed_session_elapsed(tmp_path, capsys):
    # Before delivery, the existing observation CLI rejects this missing command.
    # Installed acceptance separately requires both new modules to be installed.
    path = MODULE + "_cli"
    if importlib.util.find_spec(path) is None:
        path = (
            "swing_trading_ai_assistant.research_comparison.setup_event_continuity_cli"
        )
    main = importlib.import_module(path).main
    previous = _observe(tmp_path / "previous")
    current = _rolling_observe(tmp_path / "current")
    args = _args(tmp_path)
    args[0] = "setup-age"
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
    assert report["completed_sessions_elapsed"] == 1
    assert report["continuity_status"] == "SAME_EVENT"
    assert report["current"]["status"] == "NO_MATCH"
    assert [c[2]["question"] for c in calls] == ["CURRENT_STRUCTURE"] * 2
    assert [c[2]["selection_time"] for c in calls] == [
        previous.data_selection_time,
        current.data_selection_time,
    ]


def _age(previous, current):
    return importlib.import_module(MODULE).observe_setup_age_v1(previous, current)


class _AgePrices(_TimedPrices):
    def __init__(self, now, closures=()):
        super().__init__("positive", 0, now)
        self.closures = closures

    def history(self, instrument, start, end, **kwargs):
        template = super().history(instrument, start, end, **kwargs)
        prior = _TimedPrices("positive", 0, _NOW).history(
            instrument,
            _NOW.date() - timedelta(days=35),
            _NOW.date() - timedelta(days=1),
            **kwargs,
        )
        originals = {row.session: row for row in prior.rows}
        sessions = tuple(
            start + timedelta(days=i)
            for i in range((end - start).days + 1)
            if (start + timedelta(days=i)).weekday() < 5
            and start + timedelta(days=i) not in self.closures
        )[-21:]
        neutral = replace(
            template.rows[-1],
            open=Decimal(134),
            high=Decimal(139),
            low=Decimal(120),
            close=Decimal(134),
        )
        return replace(
            template,
            rows=tuple(originals.get(s, replace(neutral, session=s)) for s in sessions),
        )


def _advanced(root, days, closures=()):
    root.mkdir(mode=0o700)
    clock, sources = _Clock(), _watchlist_sources()
    clock.value = _NOW + timedelta(days=days)
    if closures:
        _declare_closures(sources, list(closures))
    return _service()(
        "PNB",
        root,
        question="CURRENT_STRUCTURE",
        clock=clock,
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(BharatStockClient, _AgePrices(clock.value, closures)),
    )


@pytest.mark.parametrize(
    "days,closures,count", [(2, (), 2), (6, (), 4), (4, (date(2026, 8, 28),), 2)]
)
def test_counts_admitted_sessions_across_weekend_and_declared_holiday(
    tmp_path, days, closures, count
):
    previous = _observe(tmp_path / "previous")
    current = _advanced(tmp_path / "current", days, closures)
    report = _age(previous, current)
    assert report["status"] == "OBSERVED"
    assert report["completed_sessions_elapsed"] == count
    assert report["current_completed_session"] > report["original_event_session"]


def test_revised_calendar_overlap_with_unchanged_event_has_no_count(tmp_path):
    previous = _observe(tmp_path / "previous")
    current = _advanced(tmp_path / "current", 1, (date(2026, 7, 31),))
    report = _age(previous, current)
    assert report["continuity_status"] == "SAME_EVENT"
    assert report["status"] == "NON_COMPARABLE"
    assert report["reason"] == "INCOMPATIBLE_ADMITTED_SESSION_OVERLAP"
    assert report["completed_sessions_elapsed"] is None


def test_unavailable_calendar_never_infers_age(tmp_path):
    previous = _observe(tmp_path / "previous")
    current = _advanced(tmp_path / "current", 6, (date(2026, 8, 28),))
    assert current.code == "INSUFFICIENT_COMPLETED_SESSIONS"
    report = _age(previous, current)
    assert report["status"] == "NON_COMPARABLE"
    assert report["reason"] == "CANONICAL_STOCK_UNAVAILABLE"
    assert report["completed_sessions_elapsed"] is None


def test_different_admitted_schedule_family_has_no_count(tmp_path, monkeypatch):
    previous = _observe(tmp_path / "previous")
    current = _rolling_observe(tmp_path / "current")
    api = importlib.import_module(MODULE)
    original = api._schedule

    def schedule(observation):
        value = original(observation)
        if observation is current:
            value["source"] = "nse-authoritative-calendar"
            value["source_release"] = "sha256:" + "0" * 64
        return value

    # Branch discriminator below complete admission, not source qualification.
    monkeypatch.setattr(api, "_schedule", schedule)
    report = _age(previous, current)
    assert report["status"] == "NON_COMPARABLE"
    assert report["reason"] == "INCOMPATIBLE_SCHEDULE_SOURCE"
    assert report["completed_sessions_elapsed"] is None


@pytest.mark.parametrize("replay", [True, False])
def test_replay_and_same_session_refresh_count_zero_with_distinct_status(
    tmp_path, replay
):
    previous = _observe(tmp_path / "previous")
    current = previous if replay else _observe(tmp_path / "current", minutes=1)
    report = _age(previous, current)
    assert report["status"] == ("REPLAY" if replay else "OBSERVED")
    assert report["completed_sessions_elapsed"] == 0
    assert report["original_event_session"] == report["current_completed_session"]


@pytest.mark.parametrize(
    "before,after,days,expected",
    [
        ("negative", "positive", 0, "NO_BASELINE"),
        ("positive", "negative", 0, "NOT_REPRESENTED"),
        ("positive", "insufficient", 0, "UNKNOWN"),
        ("insufficient", "positive", 0, "UNKNOWN"),
        ("positive", "positive", 35, "OUTSIDE_WINDOW"),
        ("positive", "positive", -1, "NON_COMPARABLE"),
    ],
)
def test_inconclusive_states_have_no_age(tmp_path, before, after, days, expected):
    previous = _observe(tmp_path / "previous", before)
    current = _observe(tmp_path / "current", after, days=days, minutes=1)
    report = _age(previous, current)
    assert report["status"] == expected
    assert all(
        report[k] is None
        for k in (
            "completed_sessions_elapsed",
            "original_event_session",
            "current_completed_session",
            "schedules",
        )
    )


def test_revised_event_is_not_an_aged_unchanged_candidate(tmp_path):
    previous = _observe(tmp_path / "previous")
    current = _rolling_observe(tmp_path / "current", shift=1)
    report = _age(previous, current)
    assert report["status"] == "REVISED_EVENT"
    assert report["completed_sessions_elapsed"] is None


def test_age_does_not_reverse_observed_invalidation(tmp_path):
    previous = _anchored(tmp_path / "previous")
    current = _anchored(tmp_path / "current", later=True)
    invalidation = importlib.import_module(
        MODULE.replace("setup_age", "setup_invalidation")
    ).observe_setup_invalidation_v1(previous, current)
    assert invalidation["status"] == "INVALIDATED"
    report = _age(previous, current)
    assert report["status"] == "OBSERVED" and report["completed_sessions_elapsed"] == 1
    assert "does not reverse invalidation" in " ".join(report["limitations"])


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
def test_full_integrity_precedes_unknown(tmp_path, side, field, value):
    previous = _observe(tmp_path / "previous")
    current = _observe(tmp_path / "current", "insufficient", minutes=1)
    target = previous if side == "previous" else current
    object.__setattr__(target, field, value)
    with pytest.raises(ValueError):
        _age(previous, current)


@pytest.mark.parametrize("mutation", ["duplicate", "order", "type", "limit", "release"])
def test_corrupt_admitted_session_source_is_terminal_with_unknown(tmp_path, mutation):
    previous = _observe(tmp_path / "previous")
    current = _observe(tmp_path / "current", "insufficient", minutes=1)
    source = previous.packet.source("MARKET_STRUCTURE")
    sessions = source.admitted_sessions
    if mutation == "release":
        object.__setattr__(source, "schedule_source_release", "unsupported")
    else:
        values = {
            "duplicate": sessions[:-1] + (sessions[-2],),
            "order": tuple(reversed(sessions)),
            "type": sessions[:-1] + ("2026-08-25",),
            "limit": sessions + (sessions[-1] + timedelta(days=1),),
        }
        object.__setattr__(source, "admitted_sessions", values[mutation])
    with pytest.raises(ValueError):
        _age(previous, current)


@pytest.mark.parametrize("inventory", [False, True])
def test_own_runtime_manifest_rejects_substitution(tmp_path, monkeypatch, inventory):
    previous = _observe(tmp_path / "previous")
    api = importlib.import_module(MODULE)
    source = api.SETUP_AGE_RUNTIME_SOURCE_SHA256_V1
    monkeypatch.setitem(
        source, "unexpected" if inventory else next(iter(source)), "0" * 64
    )
    with pytest.raises(ValueError, match="age runtime"):
        _age(previous, previous)


def test_identity_privacy_retry_and_concurrent_pure_calls(tmp_path):
    previous = _observe(tmp_path / "previous")
    current = _rolling_observe(tmp_path / "current")
    snapshots = [o.canonical_json_bytes() for o in (previous, current)]
    report = _age(previous, current)
    raw = encoding.canonical_comparison_bytes(report)
    unsigned = dict(report)
    identity = unsigned.pop("result_identity_sha256")
    assert (
        identity
        == hashlib.sha256(encoding.canonical_comparison_bytes(unsigned)).hexdigest()
    )
    assert (
        report["schedules"]["previous"]["source_release"]
        != report["schedules"]["current"]["source_release"]
    )
    assert (
        report["schedules"]["previous"]["schedule_identity_sha256"]
        != report["schedules"]["current"]["schedule_identity_sha256"]
    )
    assert not any(
        token in raw
        for token in (
            b'"close"',
            b'"open"',
            b'"high"',
            b'"low"',
            str(tmp_path).encode(),
        )
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _age(previous, current), range(2)))
    assert all(encoding.canonical_comparison_bytes(r) == raw for r in results)
    assert [o.canonical_json_bytes() for o in (previous, current)] == snapshots


@pytest.mark.parametrize("mutation", ["symbol", "root", "time"])
def test_cli_request_is_admitted_before_effects(tmp_path, capsys, mutation):
    main = importlib.import_module(MODULE + "_cli").main
    args = _args(tmp_path)
    args[0] = "setup-age"
    flag, value = {
        "symbol": ("--symbol", "bad/stock"),
        "root": ("--storage-root", "relative"),
        "time": ("--current-selection-time", "invalid"),
    }[mutation]
    args[args.index(flag) + 1] = value

    def service(*a, **kw):
        pytest.fail("invalid request performed observation effect")

    assert main(args, observation_service=service) == 2
    output = capsys.readouterr()
    assert not output.out and output.err == "request_invalid\n"


def test_interrupted_second_call_has_fixed_diagnostic_no_partial_stdout(
    tmp_path, capsys
):
    previous = _observe(tmp_path / "previous")
    calls = []

    def service(*a, **kw):
        calls.append(kw)
        if len(calls) == 2:
            raise KeyboardInterrupt("PRIVATE_INTERRUPTION")
        return previous

    args = _args(tmp_path)
    args[0] = "setup-age"
    assert (
        importlib.import_module(MODULE + "_cli").main(args, observation_service=service)
        == 2
    )
    output = capsys.readouterr()
    assert not output.out and output.err == "setup_age_failed\n"


def test_output_bound_is_terminal_in_cli(tmp_path, capsys, monkeypatch):
    value = _observe(tmp_path / "previous")
    monkeypatch.setattr(encoding, "MAX_OUTPUT", 1)
    args = _args(tmp_path)
    args[0] = "setup-age"
    assert (
        importlib.import_module(MODULE + "_cli").main(
            args, observation_service=lambda *a, **k: value
        )
        == 2
    )
    output = capsys.readouterr()
    assert not output.out and output.err == "setup_age_failed\n"


def test_exact_output_limit_and_limit_plus_one(tmp_path):
    previous = _observe(tmp_path / "previous")
    value = _age(previous, previous)
    value["padding"] = ""
    overhead = len(encoding.canonical_comparison_bytes(value))
    value["padding"] = "x" * (encoding.MAX_OUTPUT - overhead)
    assert len(encoding.canonical_comparison_bytes(value)) == encoding.MAX_OUTPUT
    value["padding"] += "x"
    with pytest.raises(ValueError, match="output limit"):
        encoding.canonical_comparison_bytes(value)


def test_cli_rejects_returned_selector_without_partial_result(tmp_path, capsys):
    previous = _observe(tmp_path / "previous")
    current = _observe(tmp_path / "current", minutes=1, symbol="TCS")
    args = _args(tmp_path)
    args[0] = "setup-age"
    args[args.index("--current-selection-time") + 1] = (
        current.data_selection_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    values = iter((previous, current))
    assert (
        importlib.import_module(MODULE + "_cli").main(
            args, observation_service=lambda *a, **k: next(values)
        )
        == 2
    )
    output = capsys.readouterr()
    assert not output.out and output.err == "setup_age_failed\n"
