"""Independent chronological inclusive-range expectations on actual producer pairs."""

from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext

import pytest
import test_setup_level as level_fixtures
import test_setup_level_range as range_fixtures
from test_current_stock_research import _NOW, _Clock
from test_setup_invalidation import _anchored
from test_setup_observation_comparison import _args, _TimedPrices
from test_setup_screen import _service

from swing_trading_ai_assistant.research_comparison import (
    setup_observation_comparison as encoding,
)
from swing_trading_ai_assistant.research_comparison.setup_invalidation import (
    observe_setup_invalidation_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_level_range import (
    observe_setup_level_range_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (
    canonical_comparison_bytes,
)

MODULE = "swing_trading_ai_assistant.research_comparison.setup_level_range_inclusion"


def _observe(previous, current):
    return importlib.import_module(MODULE).observe_setup_level_range_inclusion_v1(
        previous, current
    )


@pytest.fixture(scope="module")
def admitted(tmp_path_factory):
    return level_fixtures.admitted.__wrapped__(tmp_path_factory)


@pytest.fixture(scope="module")
def ranges(tmp_path_factory):
    return range_fixtures.ranges.__wrapped__(tmp_path_factory)


@pytest.fixture(scope="module")
def chronological(tmp_path_factory):
    root = tmp_path_factory.mktemp("range-inclusion")
    result = {"previous": _anchored(root / "previous")}
    for name, first, second, close in (
        ("earlier", 120, 132, 134),
        ("none", 132, 132, 134),
        ("latest", 132, 120, 134),
        ("multiple", 120, 120, 134),
        ("invalidated", 80, 80, 89),
    ):
        result[name] = _current(root / name, first, second, close)
    return result


class _TwoBars(_TimedPrices):
    def __init__(self, first=120, second=132, close=134):
        super().__init__("positive", 0, _NOW + timedelta(days=2))
        self.first, self.second, self.close = first, second, close

    def history(self, instrument, start, end, **kwargs):
        current = super().history(instrument, start, end, **kwargs)
        previous = super().history(
            instrument, start - timedelta(days=2), end - timedelta(days=2), **kwargs
        )
        rows = list(previous.rows)
        rows[18] = replace(rows[18], low=Decimal(98))
        rows[19] = replace(rows[19], low=Decimal(99))
        extras = [
            replace(
                row,
                open=Decimal(134),
                high=Decimal(139),
                low=Decimal(low),
                close=Decimal(self.close),
            )
            for row, low in zip(
                current.rows[-2:], (self.first, self.second), strict=True
            )
        ]
        return replace(current, rows=tuple(rows[2:] + extras))


def _current(root, first=120, second=132, close=134):
    root.mkdir(mode=0o700)
    clock = _Clock()
    clock.value = _NOW + timedelta(days=2)
    return _service()(
        "PNB",
        root,
        question="CURRENT_STRUCTURE",
        clock=clock,
        price_client=_TwoBars(first, second, close),
    )


def test_actual_producer_exposes_earlier_inclusion_beyond_latest_range(tmp_path):
    previous = _anchored(tmp_path / "previous")
    path = (
        MODULE
        if importlib.util.find_spec(MODULE)
        else MODULE.removesuffix("_inclusion")
    )
    module = importlib.import_module(path)
    observe = getattr(
        module,
        "observe_setup_level_range_inclusion_v1",
        module.__dict__.get("observe_setup_level_range_v1"),
    )
    for name, first, expected in (("earlier", 120, True), ("none", 132, False)):
        current = _current(tmp_path / name, first)
        result = observe(previous, current)
        assert result["status"] == "OBSERVED"
        assert result.get("inclusion_observed") is expected
        assert result["first_inclusion"] == (
            {
                "session": "2026-08-26",
                "bar_identity_sha256": current.packet.members[0]
                .feature("MARKET_STRUCTURE")
                .source_bars[-2]
                .source_row_identity_sha256,
            }
            if expected
            else None
        )


@pytest.mark.parametrize(
    "name,index", [("earlier", 0), ("none", None), ("latest", 1), ("multiple", 0)]
)
def test_earliest_complete_chronology_excludes_event(chronological, name, index):
    previous, current = chronological["previous"], chronological[name]
    report = _observe(previous, current)
    bars = current.packet.members[0].feature("MARKET_STRUCTURE").source_bars
    expected = [
        {
            "session": "2026-08-26",
            "bar_identity_sha256": bars[-2].source_row_identity_sha256,
        },
        {
            "session": "2026-08-27",
            "bar_identity_sha256": bars[-1].source_row_identity_sha256,
        },
    ]
    assert report["evaluated_post_event_bars"] == expected
    assert report["first_inclusion"] == (expected[index] if index is not None else None)
    assert report["inclusion_observed"] is (index is not None)
    assert report["witness"]["original_event_session"] == "2026-08-25"
    assert (
        report["latest_range_identity_sha256"]
        == observe_setup_level_range_v1(previous, current)["result_identity_sha256"]
    )


@pytest.mark.parametrize(
    "name,expected",
    [
        ("contains", True),
        ("above", False),
        ("below", False),
        ("low_equal", True),
        ("high_equal", True),
        ("nearest_above", False),
        ("nearest_below", False),
    ],
)
def test_exact_inclusion_and_decimal_context(ranges, name, expected):
    previous, current = ranges["previous"], ranges[name]
    report = _observe(previous, current)
    assert report["inclusion_observed"] is expected
    for precision in (1, 5, 60):
        with localcontext() as context:
            context.prec = precision
            assert _observe(previous, current) == report
    assert len(report["evaluated_post_event_bars"]) == 1
    assert report["first_inclusion"] == (
        report["evaluated_post_event_bars"][0] if expected else None
    )


def test_independent_structural_invalidation_does_not_override(chronological, admitted):
    previous, current = chronological["previous"], chronological["invalidated"]
    assert observe_setup_invalidation_v1(previous, current)["status"] == "INVALIDATED"
    assert _observe(previous, current)["inclusion_observed"] is True
    report = _observe(admitted["baseline"], admitted["newer_high"])
    assert (
        report["witness"]["original_high_identity_sha256"]
        == report["previous"]["candidate"]["pivot_identity_sha256"]
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
def test_non_factual_fields_null_and_upstream_meaning_retained(
    admitted, left, right, status
):
    previous, current = admitted[left], admitted[right]
    upstream = observe_setup_level_range_v1(previous, current)
    report = _observe(previous, current)
    assert report["status"] == status and report["reason"] == upstream["reason"]
    for key in ("inclusion_observed", "evaluated_post_event_bars", "first_inclusion"):
        assert report[key] is None
    assert report["witness"] == upstream["witness"]


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
        "fact_identity",
        "calculation_identity",
        "bar_session",
    ],
)
def test_complete_admission_terminal_even_with_unknown(admitted, side, mutation):
    value = copy.copy(admitted["baseline"])
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
        "bar": (feature.source_bars[-2], "close", Decimal("NaN")),
        "bar_identity": (
            feature.source_bars[-2],
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
        "fact_identity": (
            feature.fact,
            "adjusted_bar_identities_sha256",
            ("0" * 64,) * 21,
        ),
        "calculation_identity": (
            calculation,
            "input_bar_identities_sha256",
            ("0" * 64,) * 21,
        ),
        "bar_session": (
            feature.source_bars[-2],
            "session",
            feature.source_bars[-1].session,
        ),
    }[mutation]
    assert _observe(value, value)["status"] == "REPLAY"
    original = getattr(target, field)
    try:
        object.__setattr__(target, field, changed)
        with pytest.raises((ValueError, TypeError)):
            _observe(value, admitted["unknown"]) if side == "previous" else _observe(
                admitted["unknown"], value
            )
    finally:
        object.__setattr__(target, field, original)


@pytest.mark.parametrize("state", ["baseline", "unknown"])
@pytest.mark.parametrize("mutation", ["missing", "extra", "changed"])
def test_closed_source_inventory_terminal_before_semantics(
    admitted, monkeypatch, state, mutation
):
    sdk = importlib.import_module(MODULE)
    sources = dict(sdk.SETUP_LEVEL_RANGE_INCLUSION_RUNTIME_SOURCE_SHA256_V1)
    if mutation == "missing":
        sources.pop(next(iter(sources)))
    elif mutation == "extra":
        sources["arbitrary.py"] = "0" * 64
    else:
        sources[next(iter(sources))] = "0" * 64
    monkeypatch.setattr(
        sdk, "SETUP_LEVEL_RANGE_INCLUSION_RUNTIME_SOURCE_SHA256_V1", sources
    )
    with pytest.raises(ValueError):
        _observe(admitted["baseline"], admitted[state])


def test_transitive_runtime_substitution_terminal(admitted, monkeypatch):
    upstream = importlib.import_module(MODULE.removesuffix("_inclusion"))
    sources = dict(upstream.SETUP_LEVEL_RANGE_RUNTIME_SOURCE_SHA256_V1)
    sources[next(iter(sources))] = "0" * 64
    monkeypatch.setattr(upstream, "SETUP_LEVEL_RANGE_RUNTIME_SOURCE_SHA256_V1", sources)
    with pytest.raises(ValueError):
        _observe(admitted["baseline"], admitted["unknown"])


@pytest.mark.parametrize("other", ["baseline", "unknown", "other_stock"])
@pytest.mark.parametrize("side", ["previous", "current"])
def test_integrity_precedes_replay_unknown_and_noncomparability(admitted, other, side):
    corrupt = copy.copy(admitted["baseline"])
    object.__setattr__(corrupt, "runtime_code_identity_sha256", "0" * 64)
    with pytest.raises(ValueError):
        if side == "previous":
            _observe(corrupt, admitted[other])
        else:
            _observe(admitted[other], corrupt)


def test_closed_output_pure_concurrency_and_once_upstream(chronological, monkeypatch):
    sdk = importlib.import_module(MODULE)
    previous, current = chronological["previous"], chronological["earlier"]
    original = sdk.observe_setup_level_range_v1
    calls = []

    def recording(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(sdk, "observe_setup_level_range_v1", recording)
    before = copy.deepcopy((previous, current))
    report = _observe(previous, current)
    assert calls == [(previous, current)]
    expected_keys = set(original(previous, current)) - {"range_relation"} | {
        "inclusion_observed",
        "evaluated_post_event_bars",
        "first_inclusion",
        "latest_range_identity_sha256",
    }
    assert set(report) == expected_keys
    unsigned = dict(report)
    identity = unsigned.pop("result_identity_sha256")
    assert identity == hashlib.sha256(canonical_comparison_bytes(unsigned)).hexdigest()
    raw = canonical_comparison_bytes(report)
    for token in (
        b'"price"',
        b'"high"',
        b'"low"',
        b'"close"',
        b'"volume"',
        b'"bars"',
        b'"body"',
        b'"storage_root"',
    ):
        assert token not in raw
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert (
            list(pool.map(lambda _: _observe(previous, current), range(4)))
            == [report] * 4
        )
    assert (previous, current) == before
    report["first_inclusion"]["session"] = "tampered"
    assert _observe(previous, current)["first_inclusion"]["session"] == "2026-08-26"


@pytest.mark.parametrize(
    "left,right,code",
    [
        ("previous", "above", 0),
        ("baseline", "baseline", 0),
        ("baseline", "refresh", 0),
        ("baseline", "unknown", 1),
        ("negative_base", "refresh", 0),
        ("baseline", "negative", 1),
        ("baseline", "outside", 1),
        ("baseline", "revision", 1),
    ],
)
def test_actual_cli_exact_bytes_selectors_and_once(
    admitted, tmp_path, capsys, monkeypatch, left, right, code
):
    cli = importlib.import_module(MODULE + "_cli")
    previous, current = admitted[left], admitted[right]
    args = _args(tmp_path)
    args[0] = "setup-level-range-inclusion"
    for flag, value in (
        ("--previous-selection-time", previous.data_selection_time),
        ("--current-selection-time", current.data_selection_time),
    ):
        args[args.index(flag) + 1] = value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    values, calls, computations = iter((previous, current)), [], []

    def service(symbol, root, **kwargs):
        calls.append((symbol, root, kwargs))
        return next(values)

    original = cli.observe_setup_level_range_inclusion_v1

    def observe(*pair):
        computations.append(pair)
        return original(*pair)

    monkeypatch.setattr(cli, "observe_setup_level_range_inclusion_v1", observe)
    assert cli.main(args, observation_service=service) == code
    out = capsys.readouterr()
    assert not out.err and out.out.encode() == canonical_comparison_bytes(
        _observe(previous, current)
    )
    assert computations == [(previous, current)]
    assert calls == [
        (
            "PNB",
            tmp_path,
            {"question": "CURRENT_STRUCTURE", "selection_time": v.data_selection_time},
        )
        for v in (previous, current)
    ]


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--symbol", "invalid / symbol"),
        ("--storage-root", "relative"),
        ("--previous-selection-time", "2026-08-27T00:00:00Z"),
        ("--current-selection-time", "invalid"),
        ("--output", "text"),
    ],
)
def test_cli_malformed_zero_calls(tmp_path, capsys, flag, value):
    args = _args(tmp_path)
    args[0] = "setup-level-range-inclusion"
    args[args.index(flag) + 1] = value
    calls = []
    assert (
        importlib.import_module(MODULE + "_cli").main(
            args, observation_service=lambda *a, **k: calls.append(1)
        )
        == 2
    )
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "request_invalid\n") and not calls


@pytest.mark.parametrize("stage", ["first", "second", "comparison", "serialization"])
@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_cli_failure_interruption_and_explicit_retry(
    admitted, tmp_path, capsys, monkeypatch, stage, failure
):
    cli = importlib.import_module(MODULE + "_cli")
    args = _args(tmp_path)
    args[0] = "setup-level-range-inclusion"
    calls = []

    def interrupt(*a, **k):
        raise failure("PRIVATE_TOKEN_PATH")

    def service(*a, **k):
        calls.append(1)
        if stage == "first" or stage == "second" and len(calls) == 2:
            interrupt()
        return admitted["baseline"]

    with monkeypatch.context() as patch:
        if stage == "comparison":
            patch.setattr(cli, "observe_setup_level_range_inclusion_v1", interrupt)
        if stage == "serialization":
            patch.setattr(cli, "canonical_comparison_bytes", interrupt)
        assert cli.main(args, observation_service=service) == 2
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "setup_level_range_inclusion_failed\n")
    assert cli.main(args, observation_service=lambda *a, **k: admitted["baseline"]) == 0
    out = capsys.readouterr()
    assert (
        out.out.encode()
        == canonical_comparison_bytes(
            _observe(admitted["baseline"], admitted["baseline"])
        )
        and not out.err
    )


@pytest.mark.parametrize(
    "field,value",
    [("symbol", "TCS"), ("question", "PRICE_BEHAVIOR"), ("data_selection_time", None)],
)
def test_cli_returned_selector_substitution_redacted(
    admitted, tmp_path, capsys, field, value
):
    observation = copy.copy(admitted["baseline"])
    object.__setattr__(observation, field, value)
    args = _args(tmp_path)
    args[0] = "setup-level-range-inclusion"
    assert (
        importlib.import_module(MODULE + "_cli").main(
            args, observation_service=lambda *a, **k: observation
        )
        == 2
    )
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "setup_level_range_inclusion_failed\n")


def test_whole_output_boundary_plus_one_no_partial(
    admitted, tmp_path, capsys, monkeypatch
):
    report = _observe(admitted["baseline"], admitted["baseline"])
    report["padding"] = ""
    report["padding"] = "x" * (
        encoding.MAX_OUTPUT - len(canonical_comparison_bytes(report))
    )
    assert len(canonical_comparison_bytes(report)) == 1024 * 1024
    report["padding"] += "x"
    with pytest.raises(ValueError):
        canonical_comparison_bytes(report)
    monkeypatch.setattr(encoding, "MAX_OUTPUT", 1)
    args = _args(tmp_path)
    args[0] = "setup-level-range-inclusion"
    assert (
        importlib.import_module(MODULE + "_cli").main(
            args, observation_service=lambda *a, **k: admitted["baseline"]
        )
        == 2
    )
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "setup_level_range_inclusion_failed\n")


@pytest.mark.parametrize("limits", [("x",) * 33, ("x" * 1025,)])
def test_metadata_plus_one_terminal_before_unknown(admitted, limits):
    value = copy.copy(admitted["baseline"])
    object.__setattr__(value, "limitations", limits)
    with pytest.raises(ValueError):
        _observe(value, admitted["unknown"])


def test_metadata_exact_boundary_and_authored_report_rejection(admitted):
    value = copy.copy(admitted["baseline"])
    object.__setattr__(value, "limitations", ("x" * 1024,) * 32)
    assert _observe(value, value)["status"] == "REPLAY"
    with pytest.raises((TypeError, ValueError)):
        _observe(_observe(value, value), value)
