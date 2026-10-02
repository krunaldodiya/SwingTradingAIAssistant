"""V6 consumer: hypothetical assumptions remain separate from market evidence."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta

import pytest
import test_agent_analysis_context as fixture
import test_relative_strength_retained as retained
from test_relative_strength_boundaries import synthetic_isin

from swing_trading_ai_assistant.market_data import agent_loss_context as api
from swing_trading_ai_assistant.market_data import cli
from swing_trading_ai_assistant.market_data.current_stock_research import (
    CurrentStockResearchInputError,
)
from swing_trading_ai_assistant.relative_strength.request import identity


def scenario(request):
    member = request.members[0]
    return {
        "schema": "equity-loss-scenario-request@v1",
        "instrument": {
            "isin": member.isin,
            "exchange": "NSE",
            "symbol": member.effective_symbol,
        },
        "side": "LONG",
        "currency": "INR",
        "bar_frequency": "1d",
        "holding_sessions": 5,
        "entry_price": "100.00",
        "stop_price": "95.00",
        "quantity": 10,
    }


def arguments(tmp_path, request):
    args = fixture.arguments(tmp_path, request)
    args[args.index("v5")] = "v6"
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(scenario(request)))
    path.chmod(0o600)
    return [*args, "--loss-scenario-input-file", str(path)]


def test_v6_cli_missing_context_keeps_price_and_scenario(tmp_path, monkeypatch, capsys):
    request = fixture.request_value()
    (tmp_path / "root").mkdir(mode=0o700)
    monkeypatch.setattr(
        cli.analysis.cohort, "run_agent_cohort_research_current", fixture.dossier_report
    )

    class Clock:
        def now(self):
            return request.data_selection_time

    status = cli.main(arguments(tmp_path, request), trusted_clock=Clock())
    output = capsys.readouterr()
    assert status == 0 and output.err == ""
    report = json.loads(output.out)
    assert report["contract_version"] == "agent-current-research-run@v6"
    context = report["loss_scenario_context"]
    assert context["result"]["amounts"]["gross_scenario_loss"] == "50.00"
    assert context["jointly_comparable_with_market_evidence"] is False
    assert context["result"]["risk_eligibility"] == "NOT_ASSESSED"
    assert report["analysis_context"]["volume"]["state"] == "NONREADY"


def run(request, root, supplied=None, **changes):
    opts = fixture.options(request)
    opts.update(changes)
    return api.run_agent_loss_research_current(
        tuple(member.effective_symbol for member in request.members),
        root,
        loss_scenario_request=scenario(request) if supplied is None else supplied,
        **opts,
    )


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    request = fixture.request_value()
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(
        cli.analysis.cohort, "run_agent_cohort_research_current", fixture.dossier_report
    )
    return request, root


@pytest.mark.parametrize("count,index", [(1, 0), (10, 0), (10, 9)])
def test_exact_target_and_other_targets_not_requested(prepared, count, index):
    request, root = prepared
    request = replace(
        request,
        members=tuple(
            replace(
                request.members[0],
                isin=synthetic_isin(i),
                effective_symbol=f"SYM{i:03}",
            )
            for i in range(count)
        ),
    )
    supplied = scenario(request)
    target = request.members[index]
    supplied["instrument"] = {
        "isin": target.isin,
        "exchange": target.exchange,
        "symbol": target.effective_symbol,
    }
    report = run(request, root, supplied)
    assert [row["requested_symbol"] for row in report["members"]] == [
        m.effective_symbol for m in request.members
    ]
    contexts = [row["loss_scenario_context"] for row in report["members"]]
    assert [
        i for i, value in enumerate(contexts) if value["state"] == "CALCULATED"
    ] == [index]
    assert (
        contexts[index]["dossier_identity_alignment"] == "DOSSIER_IDENTITY_UNAVAILABLE"
    )
    assert all(
        value == {"state": "NOT_REQUESTED"}
        for i, value in enumerate(contexts)
        if i != index
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("quantity", 0),
        ("quantity", True),
        ("quantity", 1_000_001),
        ("holding_sessions", 1),
        ("holding_sessions", 21),
        ("entry_price", 100),
        ("entry_price", "1e2"),
        ("stop_price", "100.00"),
        ("side", "SHORT"),
        ("unknown", "private-value"),
        (
            "instrument",
            {"isin": "INE002A01018", "exchange": "NSE", "symbol": "UNKNOWN"},
        ),
        ("instrument", {"isin": "INE002A01018", "exchange": "BSE", "symbol": "ACME"}),
    ],
)
def test_invalid_sdk_scenario_precedes_research(tmp_path, monkeypatch, key, value):
    request = fixture.request_value()
    supplied = scenario(request)
    supplied[key] = value
    monkeypatch.setattr(
        cli.analysis.cohort, "run_agent_cohort_research_current", fixture.forbidden
    )
    root = tmp_path / "absent"
    with pytest.raises(CurrentStockResearchInputError):
        run(request, root, supplied)
    assert not root.exists()


def test_reference_only_and_wrong_isin_are_rejected(tmp_path):
    request = fixture.request_value()
    supplied = scenario(request)
    for instrument in (
        {
            "isin": request.reference.isin,
            "exchange": "NSE",
            "symbol": request.reference.effective_symbol,
        },
        {**supplied["instrument"], "isin": request.reference.isin},
    ):
        with pytest.raises(CurrentStockResearchInputError):
            run(request, tmp_path / "absent", {**supplied, "instrument": instrument})
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("version", ["v1", "v2", "v3", "v4", "v5"])
def test_legacy_rejects_scenario_before_effects(tmp_path, monkeypatch, capsys, version):
    request = fixture.request_value()
    args = arguments(tmp_path, request)
    args[args.index("v6")] = version
    monkeypatch.setattr(
        cli.analysis.cohort, "run_agent_cohort_research_current", fixture.forbidden
    )
    assert cli.main(args) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "request_invalid\n"
    assert not (tmp_path / "root").exists()


@pytest.mark.parametrize(
    "mode",
    [
        "missing_option",
        "missing",
        "public",
        "symlink",
        "hardlink",
        "directory",
        "oversized",
        "malformed",
        "duplicate",
        "invalid_utf8",
        "null",
    ],
)
def test_cli_private_scenario_rejection_before_effects(
    tmp_path, monkeypatch, capsys, mode
):
    request = fixture.request_value()
    args = arguments(tmp_path, request)
    path = tmp_path / "scenario.json"
    if mode == "missing_option":
        args = args[:-2]
    elif mode == "missing":
        path.unlink()
    elif mode == "public":
        path.chmod(0o644)
    elif mode == "symlink":
        path.rename(tmp_path / "target.json")
        path.symlink_to(tmp_path / "target.json")
    elif mode == "hardlink":
        (tmp_path / "alias.json").hardlink_to(path)
    elif mode == "directory":
        path.unlink()
        path.mkdir()
    else:
        path.write_bytes(
            {
                "oversized": b" " * 65537,
                "malformed": b"{private-value",
                "duplicate": b'{"schema":"x","schema":"y"}',
                "invalid_utf8": b"\xff",
                "null": b"null",
            }[mode]
        )
    monkeypatch.setattr(
        cli.analysis.cohort, "run_agent_cohort_research_current", fixture.forbidden
    )
    assert cli.main(args) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "request_invalid\n"
    assert not (tmp_path / "root").exists()


def test_result_identity_retry_and_unchanged_v5(prepared):
    request, root = prepared
    opts = fixture.options(request)
    v5 = cli.analysis.run_agent_analysis_research_current(("ACME",), root, **opts)
    supplied = scenario(request)
    original = deepcopy(supplied)
    report = run(request, root, supplied)
    assert report == run(request, root, supplied)
    assert supplied == original
    assert report["source_v5_result_identity_sha256"] == v5["result_identity_sha256"]
    assert report["analysis_context"] == v5["analysis_context"]
    assert report["members"][0]["features"] == v5["members"][0]["features"]
    assert report["result_identity_sha256"] == identity(
        {k: v for k, v in report.items() if k != "result_identity_sha256"}
    )
    second = run(request, root, {**supplied, "quantity": 11})
    assert second["result_identity_sha256"] != report["result_identity_sha256"]
    result = report["loss_scenario_context"]["result"]
    assert result["amounts"] == {
        "entry_notional": "1000.00",
        "stop_proceeds": "950.00",
        "loss_per_share": "5.00",
        "gross_scenario_loss": "50.00",
    }
    assert result["instrument_verification"] == "NOT_PERFORMED"
    assert result["market_evidence"] == "NOT_USED"
    assert result["costs_and_slippage"] == "EXCLUDED"
    assert not any(
        key in result for key in ("observed_at", "evidence_cutoff", "decision_session")
    )


@pytest.mark.parametrize("mismatch", [False, True])
def test_dossier_canonical_binding(prepared, monkeypatch, mismatch):
    request, root = prepared

    def report(*args, **kwargs):
        value = fixture.dossier_report(*args, **kwargs)
        value["members"][0]["canonical_stock"] = {
            "isin": request.reference.isin if mismatch else request.members[0].isin,
            "exchange": "NSE",
            "effective_symbol": "ACME",
        }
        return value

    monkeypatch.setattr(
        cli.analysis.cohort, "run_agent_cohort_research_current", report
    )
    if mismatch:
        with pytest.raises(ValueError, match="identity invalid"):
            run(request, root)
    else:
        result = run(request, root)
        assert (
            result["members"][0]["loss_scenario_context"]["dossier_identity_alignment"]
            == "CANONICAL_IDENTITY_MATCH"
        )
        assert (
            result["loss_scenario_context"]["result"]["instrument_verification"]
            == "NOT_PERFORMED"
        )


def test_v6_deadline_checked_after_composition(prepared, monkeypatch, capsys):
    request, root = prepared
    current = request.data_selection_time
    original = cli.analysis.bounded_analysis_json

    def bound(value):
        nonlocal current
        raw = original(value)
        if value["contract_version"] == "agent-current-research-run@v6":
            current = request.admission_deadline + timedelta(seconds=1)
        return raw

    monkeypatch.setattr(cli.analysis, "bounded_analysis_json", bound)

    class Clock:
        def now(self):
            return current

    assert cli.main(arguments(root.parent, request), trusted_clock=Clock()) == 2
    output = capsys.readouterr()
    assert output.out == "" and "private" not in output.err


def test_v6_output_bound_rejects_before_emission(prepared, monkeypatch, capsys):
    request, root = prepared
    original = cli.analysis.bounded_analysis_json

    def bound(value):
        if value["contract_version"] == "agent-current-research-run@v6":
            value["excess"] = "x" * cli.analysis.MAX_REPORT_BYTES
        return original(value)

    monkeypatch.setattr(cli.analysis, "bounded_analysis_json", bound)

    class Clock:
        def now(self):
            return request.data_selection_time

    assert cli.main(arguments(root.parent, request), trusted_clock=Clock()) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("error", [ValueError("private-input"), KeyboardInterrupt()])
def test_runtime_failure_and_interruption_never_emit(
    tmp_path, monkeypatch, capsys, error
):
    request = fixture.request_value()

    def fail(*args):
        raise error

    monkeypatch.setattr(api, "calculate_loss_scenario", fail)
    if isinstance(error, KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            cli.main(arguments(tmp_path, request))
    else:
        assert cli.main(arguments(tmp_path, request)) == 2
    output = capsys.readouterr()
    assert output.out == "" and "private-input" not in output.err
    assert not (tmp_path / "root").exists()


def test_real_retained_services_and_unavailable_stock(tmp_path, monkeypatch, capsys):
    root, request, _ = retained.retained(tmp_path, monkeypatch)
    before = retained.inventory(root)
    report = run(request, root)
    result = report["loss_scenario_context"]["result"]
    assert result["amounts"]["gross_scenario_loss"] == "50.00"
    assert (
        report["analysis_context"]["volume"]["members"][0]["fact"]["relation"]
        == "EQUAL"
    )
    assert (
        report["analysis_context"]["relative_strength"]["members"][0]["fact"][
            "difference_percentage_points_numerator"
        ]
        == 5
    )
    assert report["members"][0]["research_status"] == "UNAVAILABLE"
    assert retained.inventory(root) == before

    class Clock:
        def now(self):
            return request.data_selection_time

    assert (
        cli.main(
            arguments(tmp_path, request),
            trusted_clock=Clock(),
            current_stock_research_v2=fixture.unavailable_research(request),
        )
        == 1
    )
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["loss_scenario_context"]["result"] == result
    assert retained.inventory(root) == before


@pytest.mark.parametrize("version", ["v2", "v3"])
def test_v6_rejects_new_scenario_before_any_research(
    tmp_path, monkeypatch, capsys, version
):
    request = fixture.request_value()
    supplied = scenario(request) | {
        "schema": f"equity-loss-scenario-request@{version}",
        "round_trip_costs": "12.34",
    }
    if version == "v3":
        supplied["assumed_exit_price"] = "93.00"
    monkeypatch.setattr(
        api.analysis, "_prepare_agent_analysis_research_current", fixture.forbidden
    )
    root = tmp_path / "root"
    with pytest.raises(CurrentStockResearchInputError):
        run(request, root, supplied)
    assert not root.exists()
    args = arguments(tmp_path, request)
    (tmp_path / "scenario.json").write_text(json.dumps(supplied))
    assert cli.main(args) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "request_invalid\n"
    assert not root.exists()
