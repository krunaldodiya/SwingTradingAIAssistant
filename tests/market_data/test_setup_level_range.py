"""Independent inclusive-range expectations through the actual admitted producer."""

from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext
from typing import cast

import pytest
import test_setup_age as age_fixtures
from test_current_stock_research import _NOW, _Clock
from test_setup_invalidation import _anchored, _AnchoredPrices
from test_setup_level import admitted as level_admitted
from test_setup_observation_comparison import _args
from test_setup_screen import _service

from swing_trading_ai_assistant.market_data.bharatstock import BharatStockClient
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
from swing_trading_ai_assistant.research_comparison.setup_level import (
    observe_setup_level_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (
    canonical_comparison_bytes,
)

MODULE = "swing_trading_ai_assistant.research_comparison.setup_level_range"


@pytest.fixture(scope="module")
def admitted(tmp_path_factory):
    return level_admitted.__wrapped__(tmp_path_factory)


def _range(previous, current):
    return importlib.import_module(MODULE).observe_setup_level_range_v1(
        previous, current
    )


def test_actual_cli_distinguishes_spanning_from_clear_above(tmp_path, capsys):
    path = MODULE + "_cli"
    if importlib.util.find_spec(path) is None:
        path = "swing_trading_ai_assistant.research_comparison.setup_level_cli"
    main = importlib.import_module(path).main
    previous = _anchored(tmp_path / "previous")
    old_relations = []
    for name, low, expected in (
        ("spans", 120, "CONTAINS_LEVEL"),
        ("clear", 132, "ENTIRELY_ABOVE"),
    ):
        current = _anchored(tmp_path / name, later=True, close=134, wick=low)
        args = _args(tmp_path)
        args[0] = "setup-level-range"
        args[args.index("--current-selection-time") + 1] = (
            current.data_selection_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )
        values, calls = iter((previous, current)), []

        def service(symbol, root, *, _calls=calls, _values=values, **kwargs):
            _calls.append((symbol, root, kwargs))
            return next(_values)

        assert main(args, observation_service=service) == 0
        output = capsys.readouterr()
        report = json.loads(output.out)
        assert not output.err
        assert report["status"] == "OBSERVED" and report["range_relation"] == expected
        assert calls == [
            (
                "PNB",
                tmp_path,
                {
                    "question": "CURRENT_STRUCTURE",
                    "selection_time": v.data_selection_time,
                },
            )
            for v in (previous, current)
        ]
        assert output.out.encode() == canonical_comparison_bytes(
            _range(previous, current)
        )
        old_relations.append(observe_setup_level_v1(previous, current)["relation"])
    assert old_relations == ["ABOVE", "ABOVE"]


class _RangePrices(_AnchoredPrices):
    def __init__(self, now, low, high, close):
        super().__init__(now, later=True, close=close, wick=low)
        self.high = Decimal(high)

    def history(self, instrument, start, end, **kwargs):
        history = super().history(instrument, start, end, **kwargs)
        return replace(
            history,
            rows=history.rows[:-1]
            + (replace(history.rows[-1], high=self.high, open=history.rows[-1].close),),
        )


@pytest.fixture(scope="module")
def ranges(tmp_path_factory):
    root = tmp_path_factory.mktemp("level-range")
    result = {"previous": _anchored(root / "previous")}
    for name, low, high, close in (
        ("contains", 120, 139, 134),
        ("above", 132, 139, 134),
        ("below", 120, 129, 125),
        ("low_equal", 130, 139, 134),
        ("high_equal", 120, 130, 125),
        ("invalidated_below", 80, 129, 89),
        ("nearest_above", "130.0000000000000000000000000001", 139, 134),
        ("nearest_below", 120, "129.9999999999999999999999999999", 125),
    ):
        child = root / name
        child.mkdir(mode=0o700)
        clock = _Clock()
        clock.value = _NOW + timedelta(days=1)
        result[name] = _service()(
            "PNB",
            child,
            question="CURRENT_STRUCTURE",
            clock=clock,
            price_client=cast(
                BharatStockClient, _RangePrices(clock.value, low, high, close)
            ),
        )
    return result


@pytest.mark.parametrize(
    "name,expected",
    [
        ("contains", "CONTAINS_LEVEL"),
        ("above", "ENTIRELY_ABOVE"),
        ("below", "ENTIRELY_BELOW"),
        ("low_equal", "CONTAINS_LEVEL"),
        ("high_equal", "CONTAINS_LEVEL"),
        ("nearest_above", "ENTIRELY_ABOVE"),
        ("nearest_below", "ENTIRELY_BELOW"),
    ],
)
def test_exact_inclusive_range_and_witness(ranges, name, expected):
    previous, current = ranges["previous"], ranges[name]
    with localcontext() as context:
        context.prec = 2
        report = _range(previous, current)
    level = observe_setup_level_v1(previous, current)
    assert report["status"] == "OBSERVED" and report["range_relation"] == expected
    assert report["witness"] == level["witness"]
    assert report["level_identity_sha256"] == level["result_identity_sha256"]
    raw = canonical_comparison_bytes(report)
    for private in (
        b'"low"',
        b'"high"',
        b'"open"',
        b'"close"',
        b"storage_root",
        b"api_key",
    ):
        assert private not in raw
    unsigned = dict(report)
    digest = unsigned.pop("result_identity_sha256")
    assert digest == hashlib.sha256(canonical_comparison_bytes(unsigned)).hexdigest()


@pytest.mark.parametrize(
    "previous,current",
    [
        ("baseline", "baseline"),
        ("baseline", "refresh"),
        ("baseline", "unknown"),
        ("baseline", "revision"),
        ("baseline", "outside"),
        ("baseline", "other_stock"),
        ("negative_base", "negative"),
        ("unknown_base", "negative"),
        ("previous", "invalidated"),
        ("previous", "newer_high"),
    ],
)
def test_upstream_states_original_anchor_and_independent_facts(
    admitted, previous, current
):
    a, b = admitted[previous], admitted[current]
    level = observe_setup_level_v1(a, b)
    report = _range(a, b)
    assert report["status"] == level["status"] and report["witness"] == level["witness"]
    if level["status"] != "OBSERVED":
        assert report["range_relation"] is None and report["reason"] == level["reason"]
    else:
        assert report["range_relation"] in (
            "CONTAINS_LEVEL",
            "ENTIRELY_ABOVE",
            "ENTIRELY_BELOW",
        )


def test_pure_repeat_concurrency_and_inputs(ranges):
    a, b = ranges["previous"], ranges["above"]
    before = copy.deepcopy((a, b))
    expected = _range(a, b)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: _range(a, b), range(4))) == [expected] * 4
    assert (a, b) == before


def test_range_does_not_replace_invalidation_age_or_close(ranges):
    previous, current = ranges["previous"], ranges["invalidated_below"]
    assert _range(previous, current)["range_relation"] == "ENTIRELY_BELOW"
    assert observe_setup_invalidation_v1(previous, current)["status"] == "INVALIDATED"
    assert observe_setup_age_v1(previous, current)["completed_sessions_elapsed"] == 1
    assert observe_setup_level_v1(previous, current)["relation"] == "BELOW"


@pytest.mark.parametrize("kind", ["missing", "extra", "changed"])
@pytest.mark.parametrize("state", ["above", "previous"])
def test_runtime_inventory_fails_even_replay(ranges, monkeypatch, kind, state):
    api = importlib.import_module(MODULE)
    manifest = dict(api.SETUP_LEVEL_RANGE_RUNTIME_SOURCE_SHA256_V1)
    if kind == "missing":
        manifest.pop(next(iter(manifest)))
    elif kind == "extra":
        manifest["src/extra.py"] = "0" * 64
    else:
        manifest[next(iter(manifest))] = "0" * 64
    monkeypatch.setattr(api, "SETUP_LEVEL_RANGE_RUNTIME_SOURCE_SHA256_V1", manifest)
    with pytest.raises(ValueError):
        _range(ranges["previous"], ranges[state])


def test_authored_observation_rejected(ranges):
    with pytest.raises((ValueError, TypeError, AttributeError)):
        _range({"status": "MATCH"}, ranges["above"])


@pytest.mark.parametrize("failure", [ValueError, KeyboardInterrupt])
def test_second_call_failure_atomic_redacted(ranges, tmp_path, capsys, failure):
    main = importlib.import_module(MODULE + "_cli").main
    args = _args(tmp_path)
    args[0] = "setup-level-range"
    args[args.index("--current-selection-time") + 1] = ranges[
        "above"
    ].data_selection_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    calls = []

    def service(*a, **kw):
        calls.append(kw)
        if len(calls) == 2:
            raise failure("private sentinel")
        return ranges["previous"]

    assert main(args, observation_service=service) == 2
    out = capsys.readouterr()
    assert out.out == "" and out.err == "setup_level_range_failed\n" and len(calls) == 2


def test_invalid_request_precedes_service(tmp_path, capsys):
    main = importlib.import_module(MODULE + "_cli").main

    def forbidden(*a, **kw):
        raise AssertionError("service called")

    assert main(["setup-level-range"], observation_service=forbidden) == 2
    out = capsys.readouterr()
    assert out.out == "" and out.err == "request_invalid\n"


def test_upstream_source_integrity_before_unknown(admitted, monkeypatch):
    api = importlib.import_module(
        "swing_trading_ai_assistant.research_comparison.setup_level"
    )
    manifest = api.SETUP_LEVEL_RUNTIME_SOURCE_SHA256_V1
    monkeypatch.setitem(manifest, next(iter(manifest)), "0" * 64)
    with pytest.raises(ValueError):
        _range(admitted["baseline"], admitted["unknown"])


def test_original_high_despite_newer_pivot(admitted):
    previous, current = admitted["baseline"], admitted["newer_high"]
    feature = current.packet.members[0].feature("MARKET_STRUCTURE")
    highs = [p for p in feature.fact.calculation.pivots if p.kind == "SWING_HIGH"]
    assert highs[-1].price == Decimal(140)
    assert feature.source_bars[-1].high < highs[-1].price
    report = _range(previous, current)
    assert report["range_relation"] == "CONTAINS_LEVEL"
    assert (
        report["witness"]["original_high_pivot_session"] < highs[-1].session.isoformat()
    )


def test_latest_only_despite_an_earlier_spanning_bar(admitted, tmp_path, monkeypatch):
    original = age_fixtures._AgePrices

    class LatestClear(original):
        def history(self, instrument, start, end, **kwargs):
            history = super().history(instrument, start, end, **kwargs)
            return replace(
                history,
                rows=history.rows[:-1] + (replace(history.rows[-1], low=Decimal(132)),),
            )

    monkeypatch.setattr(age_fixtures, "_AgePrices", LatestClear)
    current = age_fixtures._advanced(tmp_path / "later", 3)
    feature = current.packet.members[0].feature("MARKET_STRUCTURE")
    assert feature.source_bars[-1].low > Decimal(130)
    assert any(b.low <= Decimal(130) <= b.high for b in feature.source_bars[-3:-1])
    report = _range(admitted["baseline"], current)
    assert (
        report["status"] == "OBSERVED" and report["range_relation"] == "ENTIRELY_ABOVE"
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
    report = _range(previous, current)
    assert report["status"] == status
    assert report["range_relation"] is None and report["witness"] is None
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
    assert _range(value, value)["status"] == "REPLAY"
    original = getattr(target, field)
    try:
        object.__setattr__(target, field, changed)
        with pytest.raises((ValueError, TypeError)):
            _range(value, unknown) if side == "previous" else _range(unknown, value)
    finally:
        object.__setattr__(target, field, original)


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
    args[0] = "setup-level-range"
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
        _range(previous, current)
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
    args[0] = "setup-level-range"
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
    args[0] = "setup-level-range"
    with monkeypatch.context() as patch:
        if stage == "comparison":
            patch.setattr(cli, "observe_setup_level_range_v1", interrupt)
        if stage == "serialization":
            patch.setattr(cli, "canonical_comparison_bytes", interrupt)
        assert cli.main(args, observation_service=service) == 2
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "setup_level_range_failed\n")
    assert cli.main(args, observation_service=lambda *a, **kw: value) == 0
    out = capsys.readouterr()
    assert (
        out.out.encode() == canonical_comparison_bytes(_range(value, value))
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
    args[0] = "setup-level-range"
    assert (
        importlib.import_module(MODULE + "_cli").main(
            args, observation_service=lambda *a, **kw: value
        )
        == 2
    )
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "setup_level_range_failed\n")


def test_output_bound_exact_plus_one_and_terminal_cli(
    admitted, tmp_path, capsys, monkeypatch
):
    report = _range(admitted["baseline"], admitted["baseline"])
    report["padding"] = ""
    overhead = len(canonical_comparison_bytes(report))
    report["padding"] = "x" * (encoding.MAX_OUTPUT - overhead)
    assert len(canonical_comparison_bytes(report)) == 1024 * 1024
    report["padding"] += "x"
    with pytest.raises(ValueError):
        canonical_comparison_bytes(report)
    monkeypatch.setattr(encoding, "MAX_OUTPUT", 1)
    args = _args(tmp_path)
    args[0] = "setup-level-range"
    assert (
        importlib.import_module(MODULE + "_cli").main(
            args, observation_service=lambda *a, **kw: admitted["baseline"]
        )
        == 2
    )
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "setup_level_range_failed\n")


@pytest.mark.parametrize("limitations", [("x",) * 33, ("x" * 1025,)])
def test_metadata_limit_plus_one_before_unknown(admitted, limitations):
    value = copy.copy(admitted["baseline"])
    object.__setattr__(value, "limitations", limitations)
    with pytest.raises(ValueError):
        _range(value, admitted["unknown"])
