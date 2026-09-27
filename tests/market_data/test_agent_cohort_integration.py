"""Synthetic public V4 acquisition uses real producers and immutable retainers."""

from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import partial
from pathlib import Path

import pytest
import test_current_industry_classification as classifications
import test_current_stock_research as stocks

from swing_trading_ai_assistant.market_data import agent_cohort_context as api
from swing_trading_ai_assistant.market_data import cli
from swing_trading_ai_assistant.market_data import (
    current_event_notice_v2 as event_archive,
)
from swing_trading_ai_assistant.market_data import (
    current_evidence_acquisition as acquisition,
)
from swing_trading_ai_assistant.market_data import (
    current_industry_classification as industry_archive,
)
from swing_trading_ai_assistant.market_data.agent_cohort_request import (
    parse_agent_cohort_mappings,
)
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockDailyPrice,
    BharatStockHistory,
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    research_current_stock_v2,
)
from swing_trading_ai_assistant.market_data.http import (
    HttpResponse,
    HttpResponseHeaders,
)


def _load_fixture():
    name = "agent_cohort_regime_fixture"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).parents[1] / "market_regime/test_bharatstock_regime_v4.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class IndustrySource:
    def __init__(self, members):
        self.calls = []
        self.body = classifications._artifact(
            isin_at={i: m.isin for i, m in enumerate(members)},
            symbol_at={i: m.effective_symbol for i, m in enumerate(members)},
            industry_at={0: "Banking", 1: "Technology"},
        )

    def get(self, url, headers):
        self.calls.append(url)
        assert url == acquisition.INDUSTRY_URL
        return HttpResponse(
            200,
            self.body,
            HttpResponseHeaders.from_items((("Content-Type", "text/csv"),)),
            request_url=url,
            response_url=url,
        )


class NoEventSource:
    def get(self, url, headers):
        return HttpResponse(503, b"unavailable", request_url=url, response_url=url)


class AdjustedPrices:
    def __init__(self, clock):
        self.clock = clock
        self.calls = []

    def history(self, instrument, first, last):
        self.calls.append((instrument, first, last))
        sessions = [
            first + timedelta(days=i)
            for i in range((last - first).days + 1)
            if (first + timedelta(days=i)).weekday() < 5
        ]
        return BharatStockHistory(
            instrument,
            tuple(
                BharatStockDailyPrice(
                    s,
                    Decimal("100"),
                    Decimal("102"),
                    Decimal("99"),
                    Decimal("101"),
                    1000,
                    Decimal("101"),
                    Decimal("1"),
                )
                for s in sessions
            ),
            self.clock.now(),
            ("a" * 64, "b" * 64),
            2,
        )


def _setup(tmp_path, monkeypatch, *, count=2):
    fixture = _load_fixture()
    screen = fixture._screen_fixture()
    scenario = screen._scenario(tmp_path, count=count)
    request, _ = fixture._request(scenario, screen)
    members = request.members
    root = scenario.root
    scenario.close()
    clock = stocks._Clock()
    clock.value = datetime(2026, 8, 4, 12, tzinfo=UTC)
    official = stocks._OfficialSources()
    official.rows.extend(
        {
            "segment": "NSE_EQ",
            "name": f"Company{i}",
            "exchange": "NSE",
            "isin": m.isin,
            "instrument_type": "EQ",
            "instrument_key": f"NSE_EQ|{m.isin}",
            "trading_symbol": m.effective_symbol,
        }
        for i, m in enumerate(members)
    )
    prices = stocks._Prices(clock)
    prices.full_history = True
    research = partial(
        research_current_stock_v2,
        clock=clock,
        calendar_transport=official,
        snapshot_transport=official,
        price_client=prices,
        terminal_missing_diagnostic=True,
    )

    class Evidence(fixture._TemporaryRetainedEvidence):
        def mappings_under_lease(self, request, lease):
            return tuple(
                fixture._mapping_receipt(m, cutoff=clock.now() + timedelta(minutes=3))
                for m in request.members
            )

    def advance(_seconds):
        clock.value += timedelta(seconds=1)

    monkeypatch.setattr(api.regime.time, "sleep", advance)
    monkeypatch.setattr(industry_archive, "_trusted_utc_now", clock.now)
    monkeypatch.setattr(
        industry_archive,
        "_marker_filesystem_mtime_ns",
        lambda *_: int(clock.now().timestamp()) * 1_000_000_000,
    )
    monkeypatch.setattr(event_archive, "_trusted_utc_now", clock.now)
    mapping_file = tmp_path / "cohort.json"
    mapping_file.write_text(
        json.dumps(
            {
                "contract_version": "agent-current-cohort-mappings@v1",
                "members": [m.value() for m in members],
            }
        )
    )
    mapping_file.chmod(0o600)
    source = IndustrySource(members)
    adjusted = AdjustedPrices(clock)
    kwargs = {
        "research": research,
        "confirm_research": lambda *args: None,
        "previous_research": lambda *args: None,
        "clock": clock.now,
        "calendar_transport": official,
        "snapshot_transport": official,
        "industry_transport": source,
        "adjusted_provider": adjusted,
        "raw_evidence": Evidence(),
        "event_transport": NoEventSource(),
    }
    return root, mapping_file, members, kwargs, source, adjusted


def test_serialized_cli_positive_cohort_retains_real_producers(
    tmp_path, monkeypatch, capsys
):
    root, mapping_file, members, kwargs, source, adjusted = _setup(
        tmp_path, monkeypatch
    )
    original = api.run_agent_cohort_research_current

    def runner(symbols, storage_root, **provided):
        provided.update(kwargs)
        return original(symbols, storage_root, **provided)

    monkeypatch.setattr(cli, "run_agent_cohort_research_current", runner)
    code = cli.main(
        [
            "research-run-current",
            "--symbol",
            "PNB",
            "--storage-root",
            str(root),
            "--output",
            "json",
            "--contract-version",
            "v4",
            "--context-symbol",
            members[0].effective_symbol,
            "--context-symbol",
            members[1].effective_symbol,
            "--context-purpose",
            "My explicit comparison cohort",
            "--context-mappings-file",
            str(mapping_file),
        ]
    )
    output = capsys.readouterr()
    assert code == 0, output.err
    report = json.loads(output.out)
    context = report["cohort_context"]
    assert context["market_regime"]["availability"] == "OBSERVED", context
    assert context["market_regime"]["fact"]["unchanged"] == 2
    assert context["market_regime"]["fact"]["regime"] == "MIXED_PARTICIPATION"
    assert context["industry_participation"]["availability"] == "OBSERVED", context
    assert (
        sum(row["unchanged"] for row in context["industry_participation"]["fact"]) == 2
    )
    assert source.calls == [acquisition.INDUSTRY_URL]
    assert len(adjusted.calls) == 2
    assert context["cohort_size"] == 2
    assert context["price_basis"] == "BHARATSTOCK_SOURCE_REPORTED_OHLC"
    assert context["raw_price_basis"] == "RAW"
    assert len(context["schedule_evidence_sha256"]) == 64
    assert (
        root
        / "calendar-schedules"
        / "sha256"
        / (context["schedule_evidence_sha256"] + ".json")
    ).is_file()
    for row in report["members"]:
        references = [
            e
            for e in row["context"]
            if e["feature"] in {"MARKET_REGIME", "INDUSTRY_PARTICIPATION"}
        ]
        assert len(references) == 2
        assert all(e["availability"] == "OBSERVED" for e in references)
        assert all(
            e["jointly_comparable_with_stock_dossier"] is False for e in references
        )
    assert context["jointly_comparable_with_stock_dossiers"] is False
    assert len(tuple(root.rglob("retained-*.json"))) >= 1
    for forbidden in [
        str(root),
        str(mapping_file),
        "Company0",
        "raw_grid",
        "mapping_receipts",
        "instrument_key",
    ]:
        assert forbidden not in output.out


def _run_api(root, mapping_file, members, kwargs):
    return api.run_agent_cohort_research_current(
        ("PNB",),
        root,
        context_symbols=tuple(m.effective_symbol for m in members),
        context_purpose="Explicit cohort",
        mappings=parse_agent_cohort_mappings(
            mapping_file.read_bytes(), tuple(m.effective_symbol for m in members)
        ),
        **kwargs,
    )


def test_industry_source_absence_preserves_real_regime_and_prices(
    tmp_path, monkeypatch
):
    root, path, members, kwargs, source, _ = _setup(tmp_path, monkeypatch)
    source.get = lambda url, headers: HttpResponse(
        503, b"private body", request_url=url, response_url=url
    )
    report = _run_api(root, path, members, kwargs)
    assert report["cohort_context"]["market_regime"]["availability"] == "OBSERVED"
    assert report["cohort_context"]["industry_participation"]["fact"] is None
    assert report["cohort_context"]["industry_participation"]["reasons"] == [
        "HTTP_FAILURE"
    ]
    assert report["members"][0]["features"]["CANDLE_GEOMETRY"]["fact"] is not None


def test_malformed_industry_preserves_regime_without_classification_claim(
    tmp_path, monkeypatch
):
    root, path, members, kwargs, source, _ = _setup(tmp_path, monkeypatch)
    source.body = b"not classification"
    report = _run_api(root, path, members, kwargs)
    assert report["cohort_context"]["market_regime"]["availability"] == "OBSERVED"
    assert report["cohort_context"]["industry_participation"]["reasons"] == [
        "CLASSIFICATION_ARTIFACT_MALFORMED"
    ]


def test_expired_declared_interval_is_whole_context_insufficiency(
    tmp_path, monkeypatch
):
    root, path, members, kwargs, source, adjusted = _setup(tmp_path, monkeypatch)
    doc = json.loads(path.read_bytes())
    doc["members"][0]["valid_from"] = "2026-08-01"
    path.write_text(json.dumps(doc))
    report = _run_api(root, path, members, kwargs)
    context = report["cohort_context"]
    assert context["cohort_size"] == 2
    assert context["market_regime"]["fact"] is None
    assert context["market_regime"]["reasons"] == [
        "MAPPING_EFFECTIVE_FOR_FACT_WINDOW_REQUIRED"
    ]
    assert source.calls == adjusted.calls == []


def test_current_identity_conflict_never_rewrites_owner_interval(tmp_path, monkeypatch):
    root, path, members, kwargs, source, adjusted = _setup(tmp_path, monkeypatch)
    # Current instrument lookup conflicts with the correctly fingerprinted owner document.
    kwargs["snapshot_transport"].rows[-1]["isin"] = "INE467B01029"
    kwargs["snapshot_transport"].rows[-1]["instrument_key"] = "NSE_EQ|INE467B01029"
    report = _run_api(root, path, members, kwargs)
    assert report["cohort_context"]["market_regime"]["reasons"] == [
        "CURRENT_MAPPING_CONFLICTED"
    ]
    assert source.calls == adjusted.calls == []


def test_optional_industry_failure_cannot_mask_corrupted_retained_context(
    tmp_path, monkeypatch
):
    root, path, members, kwargs, source, _ = _setup(tmp_path, monkeypatch)

    def corrupt(url, headers):
        artifacts = list(root.rglob("context-*.json"))
        assert artifacts
        target = artifacts[0]
        mode = target.stat().st_mode & 0o777
        target.chmod(0o600)
        target.write_bytes(b"corrupt")
        target.chmod(mode)
        return HttpResponse(503, b"private", request_url=url, response_url=url)

    source.get = corrupt
    with pytest.raises(ValueError):
        _run_api(root, path, members, kwargs)


def test_missing_raw_member_withholds_whole_cohort_without_shrinking(
    tmp_path, monkeypatch
):
    root, path, members, kwargs, source, adjusted = _setup(tmp_path, monkeypatch)
    evidence = kwargs["raw_evidence"]
    original = evidence.query_and_project_under_lease

    def missing(*args):
        rows, bars = original(*args)
        return rows, tuple(bar for bar in bars if bar.isin != members[-1].isin)

    evidence.query_and_project_under_lease = missing
    report = _run_api(root, path, members, kwargs)
    context = report["cohort_context"]
    assert context["cohort_size"] == 2
    assert context["market_regime"]["availability"] == "INSUFFICIENT_EVIDENCE"
    assert context["market_regime"]["fact"] is None
    assert context["industry_participation"]["fact"] is None
    assert source.calls == []
    assert adjusted.calls == []


def test_reordered_context_retains_requested_order_separate_from_canonical(
    tmp_path, monkeypatch
):
    root, path, members, kwargs, source, _ = _setup(tmp_path, monkeypatch)
    reversed_members = tuple(reversed(members))
    path.write_text(
        json.dumps(
            {
                "contract_version": "agent-current-cohort-mappings@v1",
                "members": [m.value() for m in reversed_members],
            }
        )
    )
    report = _run_api(root, path, reversed_members, kwargs)
    context = report["cohort_context"]
    assert context["requested_symbols"] == [
        m.effective_symbol for m in reversed_members
    ]
    assert context["ordered_list_identity_sha256"] != api._identity(
        [m.effective_symbol for m in members]
    )
    assert context["canonical_members"] == [m.value() for m in reversed_members]
    assert context["market_regime"]["fact"]["unchanged"] == 2
    assert report["members"][0]["requested_symbol"] == "PNB"
    assert source.calls == [acquisition.INDUSTRY_URL]


@pytest.mark.parametrize(
    "fault", ["unexpected", "interrupt", "backward", "cutoff", "rollover"]
)
def test_industry_effect_time_and_failure_boundaries(tmp_path, monkeypatch, fault):
    root, path, members, kwargs, source, _ = _setup(tmp_path, monkeypatch)
    original = source.get
    clock = kwargs["clock"].__self__

    def effect(url, headers):
        if fault == "unexpected":
            raise ValueError("arbitrary failure")
        if fault == "interrupt":
            raise KeyboardInterrupt
        if fault == "backward":
            clock.value -= timedelta(minutes=5)
        elif fault == "cutoff":
            clock.value += timedelta(minutes=30)
        elif fault == "rollover":
            clock.value += timedelta(days=1)
        return original(url, headers)

    source.get = effect
    if fault in {"unexpected", "interrupt", "backward"}:
        with pytest.raises(KeyboardInterrupt if fault == "interrupt" else ValueError):
            _run_api(root, path, members, kwargs)
    else:
        context = _run_api(root, path, members, kwargs)["cohort_context"]
        assert context["market_regime"]["availability"] == "OBSERVED"
        assert context["industry_participation"]["fact"] is None
        assert context["industry_participation"]["reasons"] == [
            "ACQUISITION_DATE_ROLLOVER"
            if fault == "rollover"
            else "ACQUISITION_CUTOFF_EXCEEDED"
        ]
        assert not tuple(
            (root / ".current-industry-classification-v1").glob("retained-*.json")
        )


def test_raw_source_mismatch_is_fatal_not_optional(tmp_path, monkeypatch):
    root, path, members, kwargs, source, _ = _setup(tmp_path, monkeypatch)
    kwargs["raw_evidence"].mismatch_source = True
    with pytest.raises(ValueError):
        _run_api(root, path, members, kwargs)
    assert source.calls == []


@pytest.mark.parametrize("fault", ["seal", "request"])
def test_forged_retained_context_cannot_project(tmp_path, monkeypatch, fault):
    root, path, members, kwargs, source, _ = _setup(tmp_path, monkeypatch)
    original = (
        api.regime.acquire_build_and_retain_current_supplied_cohort_market_regime_v4
    )

    def forged(*args, **options):
        retained = original(*args, **options)
        if fault == "seal":
            object.__setattr__(retained, "_archive_seal", object())
        else:
            object.__setattr__(
                retained.market_regime_report, "request_identity_sha256", "0" * 64
            )
        return retained

    monkeypatch.setattr(
        api.regime,
        "acquire_build_and_retain_current_supplied_cohort_market_regime_v4",
        forged,
    )
    with pytest.raises(ValueError):
        _run_api(root, path, members, kwargs)
    assert source.calls == []


def test_missing_bounded_physical_month_never_widens_or_falls_back(
    tmp_path, monkeypatch
):
    root, path, members, kwargs, source, adjusted = _setup(tmp_path, monkeypatch)
    kwargs["clock"].__self__.value = datetime(2026, 8, 20, 12, tzinfo=UTC)
    doc = json.loads(path.read_bytes())
    for member in doc["members"]:
        member["valid_through"] = "2026-08-20"
    path.write_text(json.dumps(doc))
    context = _run_api(root, path, members, kwargs)["cohort_context"]
    assert context["market_regime"]["reasons"] == [
        "PHYSICAL_MONTH_CALENDAR_UNAVAILABLE"
    ]
    assert context["market_regime"]["fact"] is None
    assert source.calls == adjusted.calls == []


def test_calendar_source_failure_remains_explicit_without_context_effects(
    tmp_path, monkeypatch
):
    root, path, members, kwargs, source, adjusted = _setup(tmp_path, monkeypatch)
    kwargs["calendar_transport"] = NoEventSource()
    context = _run_api(root, path, members, kwargs)["cohort_context"]
    assert context["market_regime"]["availability"] == "INSUFFICIENT_EVIDENCE"
    assert context["market_regime"]["fact"] is None
    assert source.calls == adjusted.calls == []


def test_new_explicit_command_reuses_exact_classification_artifact(
    tmp_path, monkeypatch
):
    root, path, members, kwargs, source, _ = _setup(tmp_path, monkeypatch)
    first = _run_api(root, path, members, kwargs)
    original_raw = {
        p.name: p.read_bytes()
        for p in (root / ".current-industry-classification-v1").glob("raw-*.csv")
    }
    assert original_raw
    second = _run_api(root, path, members, kwargs)
    assert first["cohort_context"]["market_regime"]["availability"] == "OBSERVED"
    assert second["cohort_context"]["market_regime"]["availability"] == "OBSERVED"
    assert {
        p.name: p.read_bytes()
        for p in (root / ".current-industry-classification-v1").glob("raw-*.csv")
    } == original_raw
    assert source.calls == [acquisition.INDUSTRY_URL] * 2


def _capture_v3(monkeypatch):
    observations = []
    original = api.run_agent_event_research_current

    def observe(*args, **kwargs):
        report = original(*args, **kwargs)
        observations.append(deepcopy(report))
        return report

    monkeypatch.setattr(api, "run_agent_event_research_current", observe)
    return observations


def _assert_price_event_preservation(report, predecessor):
    assert report["jointly_comparable"] == predecessor["jointly_comparable"]
    for current, previous in zip(
        report["members"], predecessor["members"], strict=True
    ):
        for key in (
            "features",
            "research_status",
            "selected_evidence_end_session",
            "event_context",
            "data_selection_time",
            "research_evidence_known_at",
        ):
            assert current[key] == previous[key], key


def test_ten_research_stocks_and_two_context_members_remain_independent(
    tmp_path, monkeypatch
):
    root, path, members, kwargs, source, adjusted = _setup(
        tmp_path, monkeypatch, count=10
    )
    observations = _capture_v3(monkeypatch)
    context_members = members[:2]
    document = {
        "contract_version": "agent-current-cohort-mappings@v1",
        "members": [m.value() for m in context_members],
    }
    mappings = parse_agent_cohort_mappings(
        json.dumps(document).encode(),
        tuple(m.effective_symbol for m in context_members),
    )
    report = api.run_agent_cohort_research_current(
        tuple(m.effective_symbol for m in members),
        root,
        context_symbols=tuple(m.effective_symbol for m in context_members),
        context_purpose="Explicit comparison",
        mappings=mappings,
        **kwargs,
    )
    assert len(report["members"]) == 10
    assert report["cohort_context"]["cohort_size"] == 2
    assert report["cohort_context"]["market_regime"]["fact"]["unchanged"] == 2
    _assert_price_event_preservation(report, observations[0])
    assert all(
        feature["fact"] is not None
        for row in report["members"]
        for feature in row["features"].values()
    )
    assert len(adjusted.calls) == 2
    assert source.calls == [acquisition.INDUSTRY_URL]


@pytest.mark.parametrize("lagged", [False, True])
def test_same_and_lagged_stock_end_sessions_never_imply_joint_context(
    tmp_path, monkeypatch, lagged
):
    root, path, members, kwargs, _, _ = _setup(tmp_path, monkeypatch)
    research = kwargs["research"]
    prices = research.keywords["price_client"]
    options = {
        name: research.keywords[name]
        for name in (
            "clock",
            "calendar_transport",
            "snapshot_transport",
            "price_client",
        )
    }
    if lagged:
        history = prices.history
        latest = kwargs["clock"]().date()

        def missing(instrument, first, last, *, effect_guard=None):
            if first == last == latest:
                raise stocks.BharatStockError("EMPTY_HISTORY", member_local=True)
            result = history(instrument, first, last, effect_guard=effect_guard)
            return replace(
                result, rows=tuple(row for row in result.rows if row.session != latest)
            )

        prices.history = missing
        kwargs["confirm_research"] = partial(
            stocks.workflow_v2.confirm_latest_completed_stock_v2, **options
        )
        kwargs["previous_research"] = partial(
            stocks.workflow_v2.research_previous_completed_stock_v2, **options
        )
    report = _run_api(root, path, members, kwargs)
    row = report["members"][0]
    context = report["cohort_context"]
    assert context["market_regime"]["availability"] == "OBSERVED"
    assert row["selected_evidence_end_session"] == (
        "2026-08-03" if lagged else "2026-08-04"
    )
    assert context["market_regime"]["fact"]["decision_session"] == "2026-08-04"
    assert context["jointly_comparable_with_stock_dossiers"] is False
    assert row["lag_official_sessions"] == (1 if lagged else 0)
    assert row["data_selection_time"] != context["known_at"]


def test_optional_industry_failure_cannot_mask_retained_calendar_corruption(
    tmp_path, monkeypatch
):
    root, path, members, kwargs, source, _ = _setup(tmp_path, monkeypatch)

    def corrupt(url, headers):
        targets = list(root.rglob("*.json"))
        schedules = [p for p in targets if "schedule" in str(p.relative_to(root))]
        assert schedules
        for target in schedules:
            mode = target.stat().st_mode & 0o777
            target.chmod(0o600)
            target.write_bytes(b"corrupt")
            target.chmod(mode)
        return HttpResponse(503, b"private", request_url=url, response_url=url)

    source.get = corrupt
    with pytest.raises(ValueError):
        _run_api(root, path, members, kwargs)


@pytest.mark.parametrize("reason", ["RAW_BAR_STALE", "RAW_BAR_MISSING"])
def test_closed_raw_absence_preserves_denominator_and_price_features(
    tmp_path, monkeypatch, reason
):
    root, path, members, kwargs, source, adjusted = _setup(tmp_path, monkeypatch)
    observations = _capture_v3(monkeypatch)
    kwargs["raw_evidence"].query_and_project_under_lease = lambda *args: reason
    report = _run_api(root, path, members, kwargs)
    context = report["cohort_context"]
    assert context["cohort_size"] == 2
    assert context["market_regime"]["fact"] is None
    assert context["market_regime"]["availability"] == "INSUFFICIENT_EVIDENCE"
    _assert_price_event_preservation(report, observations[0])
    assert all(
        feature["fact"] is not None
        for feature in report["members"][0]["features"].values()
    )
    assert source.calls == adjusted.calls == []


@pytest.mark.parametrize(
    "reason",
    ["RAW_MAPPING_STALE", "RAW_MAPPING_CONFLICTED", "RAW_ACQUISITION_UNAVAILABLE"],
)
def test_ambiguous_legacy_mapping_or_acquisition_failure_is_fatal(
    tmp_path, monkeypatch, reason
):
    root, path, members, kwargs, source, _ = _setup(tmp_path, monkeypatch)
    kwargs["raw_evidence"].mappings_under_lease = lambda *args: reason
    with pytest.raises(ValueError):
        _run_api(root, path, members, kwargs)
    assert source.calls == []
