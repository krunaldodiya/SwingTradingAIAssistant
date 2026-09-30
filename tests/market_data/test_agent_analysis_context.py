"""V5 consumer contract; retained analysis is real, stock acquisition is isolated."""

import json
from copy import deepcopy
from dataclasses import replace

import test_relative_strength_retained as rs_fixture
import test_volume_retained as volume_fixture
from current_raw_acquisition_fixtures import members
from current_raw_acquisition_fixtures import request as raw_request

from swing_trading_ai_assistant.market_data import agent_analysis_context as api
from swing_trading_ai_assistant.market_data import cli
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)
from swing_trading_ai_assistant.relative_strength import RelativeStrengthRequest
from swing_trading_ai_assistant.relative_strength.request import identity
from swing_trading_ai_assistant.volume_analysis import (
    VolumeRequest,
    research_current_volume,
)


def request_value(count=1):
    selected = deepcopy(members(count + 1))
    raw = raw_request(members=selected)
    return RelativeStrengthRequest(
        raw.data_selection_time,
        raw.admission_deadline,
        raw.schedule_identity_sha256,
        selected[-1],
        selected[:-1],
    )


def dossier_report(symbols, root, **kwargs):
    # This double proves orchestration only, never stock provider admission.
    root.mkdir(mode=0o700, exist_ok=True)
    return {
        "contract_version": "agent-current-research-run@v4",
        "jointly_comparable": True,
        "limitations": [],
        "members": [
            {
                "requested_symbol": symbol,
                "canonical_stock": None,
                "features": {"PRICE": {"fact": {"direction": "UP"}}},
                "price_basis": "ADJUSTED",
                "decision_session": "2026-08-03",
            }
            for symbol in symbols
        ],
    }


def arguments(tmp_path, request):
    path = tmp_path / "request.json"
    path.write_bytes(request.canonical_bytes)
    path.chmod(0o600)
    return [
        "research-run-current",
        "--contract-version",
        "v5",
        "--symbol",
        request.members[0].effective_symbol,
        "--storage-root",
        str(tmp_path / "root"),
        "--output",
        "json",
        "--context-symbol",
        "PNB",
        "--context-symbol",
        "INFY",
        "--context-purpose",
        "Explicit comparison",
        "--analysis-input-file",
        str(path),
    ]


def test_v5_cli_missing_context_keeps_price_exit(tmp_path, monkeypatch, capsys):
    request = request_value()
    (tmp_path / "root").mkdir(mode=0o700)
    monkeypatch.setattr(
        cli.analysis.cohort, "run_agent_cohort_research_current", dossier_report
    )

    class Clock:
        def now(self):
            return request.data_selection_time

    # V5 is not yet implemented: this first discriminating red is the rejected
    # public version/option, not an import or fixture setup error.
    status = cli.main(arguments(tmp_path, request), trusted_clock=Clock())
    output = capsys.readouterr()
    assert status == 0 and output.err == ""
    report = json.loads(output.out)
    assert report["contract_version"] == "agent-current-research-run@v5"
    assert report["analysis_context"]["volume"]["state"] == "NONREADY"
    assert report["analysis_context"]["relative_strength"]["state"] == "NONREADY"
    assert (
        report["members"][0]["volume_context"]["identity_alignment"]
        == "DOSSIER_IDENTITY_UNAVAILABLE"
    )


def options(request):
    return {
        "analysis_request": request,
        "context_symbols": ("PNB", "INFY"),
        "context_purpose": "Explicit comparison",
        "mappings": None,
        "research": unavailable_research(request),
        "confirm_research": forbidden,
        "previous_research": forbidden,
        "clock": lambda: request.data_selection_time,
    }


def forbidden(*args, **kwargs):
    raise AssertionError("unexpected research/provider effect")


def unavailable_research(request):

    def research(symbol, root, **kwargs):
        return CurrentStockResearchResultV2(
            "current-stock-research@v2",
            "UNAVAILABLE",
            "mapping",
            "MAPPING_UNAVAILABLE",
            kwargs["question"],
            symbol,
            request.data_selection_time,
            request.admission_deadline,
            "a" * 64,
            None,
            ("Synthetic stock dependency unavailable",),
        )

    return research


def test_real_retained_services_through_real_v4_sdk_and_cli(
    tmp_path, monkeypatch, capsys
):

    root, request, wire = rs_fixture.retained(tmp_path, monkeypatch)
    before = rs_fixture.inventory(root)
    expected_volume = research_current_volume(
        VolumeRequest(
            request.data_selection_time,
            request.admission_deadline,
            request.schedule_identity_sha256,
            request.members,
        ),
        root,
        clock=lambda: request.data_selection_time,
    )
    expected_rs = api.research_current_relative_strength(
        request, root, clock=lambda: request.data_selection_time
    )
    report = api.run_agent_analysis_research_current(
        ("ACME",), root, **options(request)
    )
    assert report["analysis_context"]["volume"] == expected_volume
    assert report["analysis_context"]["relative_strength"] == expected_rs
    assert expected_volume["members"][0]["fact"]["relation"] == "EQUAL"
    assert (
        expected_rs["members"][0]["fact"]["difference_percentage_points_numerator"] == 5
    )
    assert report["members"][0]["research_status"] == "UNAVAILABLE"
    assert (
        report["members"][0]["relative_strength_context"]["identity_alignment"]
        == "DOSSIER_IDENTITY_UNAVAILABLE"
    )
    assert report["result_identity_sha256"] == identity(
        {k: v for k, v in report.items() if k != "result_identity_sha256"}
    )

    class Clock:
        def now(self):
            return request.data_selection_time

    assert (
        cli.main(
            arguments(tmp_path, request),
            trusted_clock=Clock(),
            current_stock_research_v2=unavailable_research(request),
            current_stock_research_confirm_v2=forbidden,
            current_stock_research_previous_v2=forbidden,
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.err == "" and json.loads(captured.out) == report
    assert wire.attempts == 2 and rs_fixture.inventory(root) == before
    for private in (
        str(root),
        "fixture-token",
        "candles",
        "endpoint",
        "PRIVATE_NOTICE_BODY",
    ):
        assert private not in captured.out


def test_missing_reference_keeps_real_volume_and_price_facts(tmp_path, monkeypatch):

    root, volume_request, wire = volume_fixture.retained(tmp_path, monkeypatch)
    request = RelativeStrengthRequest(
        volume_request.data_selection_time,
        volume_request.admission_deadline,
        volume_request.schedule_identity_sha256,
        members(2)[1],
        volume_request.members,
    )
    monkeypatch.setattr(api.cohort, "run_agent_cohort_research_current", dossier_report)
    before = volume_fixture.inventory(root)
    report = api.run_agent_analysis_research_current(
        ("ACME",), root, **options(request)
    )
    assert report["jointly_comparable"] is True
    assert report["jointly_comparable_scope"] == "PRICE_FEATURES_ONLY"
    assert (
        report["analysis_context"]["relative_strength"]["reference"]["state"]
        != "OBSERVED"
    )
    assert report["members"][0]["features"]["PRICE"]["fact"] == {"direction": "UP"}
    assert (
        report["members"][0]["volume_context"]["outcome"]["fact"]["relation"] == "EQUAL"
    )
    assert (
        report["members"][0]["relative_strength_context"]["outcome"][
            "comparison_reason"
        ]
        == "REFERENCE_UNAVAILABLE"
    )
    assert wire.attempts == 1 and volume_fixture.inventory(root) == before


def test_real_zero_baseline_does_not_hide_relative_price_equality(
    tmp_path, monkeypatch
):

    original = rs_fixture.historical_body

    def zero_body(*args, **kwargs):
        value = json.loads(original(*args, **kwargs))
        for bar in value["data"]["candles"]:
            bar[5] = 0
        return json.dumps(value).encode()

    monkeypatch.setattr(rs_fixture, "historical_body", zero_body)
    root, request, wire = rs_fixture.retained(tmp_path, monkeypatch, reference_last=220)
    monkeypatch.setattr(api.cohort, "run_agent_cohort_research_current", dossier_report)
    report = api.run_agent_analysis_research_current(
        ("ACME",), root, **options(request)
    )
    assert (
        report["analysis_context"]["volume"]["members"][0]["reason"] == "ZERO_BASELINE"
    )
    assert (
        report["analysis_context"]["relative_strength"]["members"][0]["fact"][
            "relation"
        ]
        == "EQUAL"
    )
    assert report["jointly_comparable"] is True and wire.attempts == 2


def test_missing_target_is_local_and_order_preserved(tmp_path, monkeypatch):

    root, request, wire = rs_fixture.retained(tmp_path, monkeypatch)
    absent = replace(
        request.members[0], isin="INE002A01018", effective_symbol="RELIANCE"
    )
    request = replace(request, members=(absent, *request.members))
    monkeypatch.setattr(api.cohort, "run_agent_cohort_research_current", dossier_report)
    report = api.run_agent_analysis_research_current(
        ("RELIANCE", "ACME"), root, **options(request)
    )
    first, second = report["members"]
    assert first["volume_context"]["outcome"]["fact"] is None
    assert first["relative_strength_context"]["outcome"]["fact"] is None
    assert second["volume_context"]["outcome"]["state"] == "OBSERVED"
    assert second["relative_strength_context"]["outcome"]["fact"]["relation"] == "ABOVE"
    assert wire.attempts == 2
