"""Adversarial V5 admission, independent observation and emission boundaries."""

import json
from dataclasses import replace
from datetime import timedelta

import pytest
import test_agent_analysis_context as fixture
import test_agent_cohort_mappings as mapping_fixture
import test_relative_strength_retained as retained
from current_raw_acquisition_fixtures import remove_action_metadata, seed_root
from test_relative_strength_boundaries import synthetic_isin

import swing_trading_ai_assistant.relative_strength.service as rs_service
from swing_trading_ai_assistant.market_data import agent_analysis_context as api
from swing_trading_ai_assistant.market_data import cli
from swing_trading_ai_assistant.market_data.agent_cohort_request import (
    parse_agent_cohort_mappings,
)
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.corporate_actions import (
    CorporateActionSnapshotStoreV1,
)
from swing_trading_ai_assistant.market_data.current_stock_research import (
    CurrentStockResearchInputError,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.relative_strength.request import (
    canonical_bytes,
    identity,
    member_value,
)


@pytest.fixture
def selected_request():
    return fixture.request_value()


@pytest.fixture
def mock_dossiers(monkeypatch, tmp_path):
    (tmp_path / "root").mkdir(mode=0o700)
    monkeypatch.setattr(
        api.cohort, "run_agent_cohort_research_current", fixture.dossier_report
    )


def run(selected_request, root, **changes):
    opts = fixture.options(selected_request)
    opts.update(changes)
    return api.run_agent_analysis_research_current(
        tuple(m.effective_symbol for m in selected_request.members), root, **opts
    )


@pytest.mark.parametrize("count", [1, 10])
def test_sdk_valid_ordered_bounds(tmp_path, selected_request, mock_dossiers, count):
    selected = tuple(
        replace(
            selected_request.members[0],
            isin=synthetic_isin(i),
            effective_symbol=f"SYM{i:03}",
        )
        for i in range(count)
    )
    selected_request = replace(selected_request, members=selected)
    report = run(selected_request, tmp_path / "root")
    assert [row["requested_symbol"] for row in report["members"]] == [
        m.effective_symbol for m in selected
    ]
    assert [
        row["member"] for row in report["analysis_context"]["volume"]["members"]
    ] == [member_value(m) for m in selected]
    assert len(report["analysis_context"]["relative_strength"]["members"]) == count


@pytest.mark.parametrize(
    "mode",
    [
        "zero",
        "eleven",
        "order",
        "symbol",
        "reference",
        "duplicate",
        "typed_mutation",
        "member_mutation",
        "root",
        "purpose",
        "cohort",
        "mapping",
    ],
)
def test_sdk_invalid_inputs_precede_v4_effects(  # noqa: C901 - explicit mutation matrix.
    tmp_path, selected_request, monkeypatch, mode
):
    monkeypatch.setattr(
        api.cohort, "run_agent_cohort_research_current", fixture.forbidden
    )
    symbols = ("ACME",)
    opts = fixture.options(selected_request)
    root = tmp_path / "absent"
    if mode in {"zero", "eleven", "order"}:
        count = {"zero": 0, "eleven": 11, "order": 2}[mode]
        selected = tuple(
            replace(
                selected_request.members[0],
                isin=synthetic_isin(i),
                effective_symbol=f"SYM{i:03}",
            )
            for i in range(count)
        )
        if count:
            selected_request = replace(selected_request, members=selected)
        else:
            object.__setattr__(selected_request, "members", ())
        symbols = tuple(m.effective_symbol for m in selected)
        if mode == "order":
            symbols = symbols[::-1]
    elif mode == "symbol":
        symbols = ("OTHER",)
    elif mode == "reference":
        object.__setattr__(selected_request, "reference", selected_request.members[0])
    elif mode == "duplicate":
        object.__setattr__(selected_request, "members", selected_request.members * 2)
    elif mode == "typed_mutation":
        object.__setattr__(selected_request, "members", list(selected_request.members))
    elif mode == "member_mutation":
        object.__setattr__(selected_request.members[0], "exchange", "OTHER")
    elif mode == "root":
        root = type(root)("relative")
    elif mode == "purpose":
        opts["context_purpose"] = None
    elif mode == "cohort":
        opts["context_symbols"] = ("PNB",)
    elif mode == "mapping":
        opts["mappings"] = {"members": []}
    opts["analysis_request"] = selected_request
    with pytest.raises(CurrentStockResearchInputError):
        api.run_agent_analysis_research_current(symbols, root, **opts)
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize(
    "mode",
    [
        "missing",
        "public",
        "link",
        "hardlink",
        "oversize",
        "duplicate",
        "unknown",
        "nonfinite",
        "bad_version",
        "malformed",
        "wrong_type",
        "no_option",
        "order",
    ],
)
def test_cli_input_invalid_no_output_or_effect(  # noqa: C901 - explicit input matrix.
    tmp_path, selected_request, monkeypatch, capsys, mode
):
    monkeypatch.setattr(
        api.cohort, "run_agent_cohort_research_current", fixture.forbidden
    )
    args = fixture.arguments(tmp_path, selected_request)
    path = tmp_path / "request.json"
    if mode == "missing":
        path.unlink()
    elif mode == "public":
        path.chmod(0o644)
    elif mode in {"link", "hardlink"}:
        saved = tmp_path / "saved.json"
        path.rename(saved)
        if mode == "link":
            path.symlink_to(saved)
        else:
            path.hardlink_to(saved)
    elif mode == "oversize":
        path.write_bytes(b" " * (64 * 1024 + 1))
    elif mode == "duplicate":
        path.write_bytes(
            selected_request.canonical_bytes.replace(
                b"{", b'{"contract_version":"duplicate",', 1
            )
        )
    elif mode == "unknown":
        path.write_bytes(
            selected_request.canonical_bytes.replace(b"{", b'{"unknown":1,', 1)
        )
    elif mode == "nonfinite":
        path.write_bytes(
            selected_request.canonical_bytes.replace(b"{", b'{"unknown":NaN,', 1)
        )
    elif mode == "bad_version":
        path.write_bytes(selected_request.canonical_bytes.replace(b"@v1", b"@v9"))
    elif mode == "malformed":
        path.write_bytes(b"{")
    elif mode == "wrong_type":
        path.write_bytes(b"[]")
    elif mode == "no_option":
        args = args[:-2]
    elif mode == "order":
        args[args.index("--symbol") + 1] = "BETA"
    assert cli.main(args) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "request_invalid\n"
    assert not (tmp_path / "root").exists()


@pytest.mark.parametrize("version", ["v1", "v2", "v3", "v4"])
def test_legacy_rejects_analysis_option_before_effects(
    tmp_path, selected_request, monkeypatch, capsys, version
):
    monkeypatch.setattr(
        api.cohort, "run_agent_cohort_research_current", fixture.forbidden
    )
    args = fixture.arguments(tmp_path, selected_request)
    args[args.index("--contract-version") + 1] = version
    assert cli.main(args, current_stock_research_v2=fixture.forbidden) == 2
    assert capsys.readouterr().out == "" and not (tmp_path / "root").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "dossier_identity",
        "dossier_order",
        "producer_identity",
        "producer_order",
        "reference",
        "producer_request",
        "result_digest",
    ],
)
def test_identity_substitution_is_terminal(
    tmp_path, selected_request, monkeypatch, mock_dossiers, mutation
):
    if mutation.startswith("dossier"):

        def dossier(*args, **kwargs):
            report = fixture.dossier_report(*args, **kwargs)
            row = report["members"][0]
            if mutation == "dossier_identity":
                row["canonical_stock"] = {
                    "isin": selected_request.reference.isin,
                    "exchange": "NSE",
                    "effective_symbol": "ACME",
                }
            else:
                row["requested_symbol"] = "BETA"
            return report

        monkeypatch.setattr(api.cohort, "run_agent_cohort_research_current", dossier)
    else:
        original = api.research_current_relative_strength

        def altered(*args, **kwargs):
            result = original(*args, **kwargs)
            if mutation == "producer_identity":
                result["members"][0]["member"]["isin"] = selected_request.reference.isin
            elif mutation == "producer_order":
                result["members"][0]["position"] = 1
            elif mutation == "reference":
                result["reference"]["member"] = member_value(
                    selected_request.members[0]
                )
            elif mutation == "producer_request":
                result["request_identity_sha256"] = "f" * 64
            result.pop("result_identity_sha256")
            result["result_identity_sha256"] = (
                "a" * 64 if mutation == "result_digest" else identity(result)
            )
            return result

        monkeypatch.setattr(api, "research_current_relative_strength", altered)
    with pytest.raises(ValueError, match="identity|binding|order"):
        run(selected_request, tmp_path / "root")


def test_identity_match_does_not_claim_common_date_or_basis(
    tmp_path, selected_request, monkeypatch
):

    root, selected_request, _ = retained.retained(tmp_path, monkeypatch)

    def dossier(*args, **kwargs):
        report = fixture.dossier_report(*args, **kwargs)
        report["members"][0]["canonical_stock"] = {
            k: getattr(selected_request.members[0], k)
            for k in ("isin", "exchange", "effective_symbol")
        }
        report["members"][0]["freshness"] = "PREVIOUS_COMPLETED_SESSION"
        return report

    monkeypatch.setattr(api.cohort, "run_agent_cohort_research_current", dossier)
    report = run(selected_request, root)
    row = report["members"][0]
    assert row["decision_session"] == "2026-08-03" and row["price_basis"] == "ADJUSTED"
    assert row["volume_context"]["identity_alignment"] == "CANONICAL_IDENTITY_MATCH"
    assert row["volume_context"]["jointly_comparable_with_stock_dossier"] is False
    context = report["analysis_context"]
    assert context["relative_strength"]["price_basis"] == "RAW"
    assert (
        context["relative_strength"]["sessions"][-1]["session"]
        != row["decision_session"]
    )
    assert (
        context["relative_strength"]["evidence_cutoff"]
        == context["volume"]["evidence_cutoff"]
    )
    assert context["jointly_comparable_with_stock_dossiers"] is False


@pytest.mark.parametrize(
    "stage", ["before", "v4", "volume", "relative_strength", "return", "emission"]
)
def test_overall_deadline_and_final_emission_no_partial_json(  # noqa: C901 - stage/clock matrix.
    tmp_path, selected_request, monkeypatch, capsys, stage
):
    now = (
        selected_request.admission_deadline
        if stage == "before"
        else selected_request.data_selection_time
    )
    calls = []

    def wrap(name, original):
        def wrapped(*args, **kwargs):
            nonlocal now
            calls.append(name)
            result = original(*args, **kwargs)
            if stage == name:
                now = selected_request.admission_deadline
            return result

        return wrapped

    monkeypatch.setattr(
        api.cohort,
        "run_agent_cohort_research_current",
        wrap("v4", fixture.dossier_report),
    )
    monkeypatch.setattr(
        api, "research_current_volume", wrap("volume", api.research_current_volume)
    )
    monkeypatch.setattr(
        api,
        "research_current_relative_strength",
        wrap("relative_strength", api.research_current_relative_strength),
    )
    if stage != "before":
        (tmp_path / "root").mkdir(mode=0o700)
    original_json = api.bounded_analysis_json
    serializations = 0

    def encode(report):
        nonlocal now, serializations
        result = original_json(report)
        serializations += 1
        if stage == "return" or stage == "emission" and serializations == 2:
            now = selected_request.admission_deadline
        return result

    monkeypatch.setattr(api, "bounded_analysis_json", encode)

    class Clock:
        def now(self):
            return now

    assert (
        cli.main(fixture.arguments(tmp_path, selected_request), trusted_clock=Clock())
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "internal_error\n"
    if stage == "before":
        assert calls == [] and not (tmp_path / "root").exists()
    if stage == "v4":
        assert calls == ["v4"]
    if stage == "volume":
        assert calls == ["v4", "volume"]


@pytest.mark.parametrize("mode", ["regression", "rollover"])
def test_clock_cannot_reset_between_services(
    tmp_path, selected_request, monkeypatch, mock_dossiers, mode
):
    now = selected_request.data_selection_time
    original = api.research_current_volume

    def change(*args, **kwargs):
        nonlocal now
        result = original(*args, **kwargs)
        now += timedelta(seconds=-1) if mode == "regression" else timedelta(days=1)
        return result

    monkeypatch.setattr(api, "research_current_volume", change)
    monkeypatch.setattr(api, "research_current_relative_strength", fixture.forbidden)
    with pytest.raises(RuntimeError):
        run(selected_request, tmp_path / "root", clock=lambda: now)


@pytest.mark.parametrize("stage", ["v4", "volume", "relative_strength", "emission"])
def test_root_replacement_terminal_no_partial_output(
    tmp_path, selected_request, monkeypatch, capsys, stage
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)

    def swap():
        root.rename(tmp_path / "original")
        root.mkdir(mode=0o700)

    def wrap(name, original):
        def wrapped(*args, **kwargs):
            result = original(*args, **kwargs)
            if stage == name:
                swap()
            return result

        return wrapped

    monkeypatch.setattr(
        api.cohort,
        "run_agent_cohort_research_current",
        wrap("v4", fixture.dossier_report),
    )
    monkeypatch.setattr(
        api, "research_current_volume", wrap("volume", api.research_current_volume)
    )
    monkeypatch.setattr(
        api,
        "research_current_relative_strength",
        wrap("relative_strength", api.research_current_relative_strength),
    )
    original_json = api.bounded_analysis_json
    count = 0

    def encoded(report):
        nonlocal count
        count += 1
        result = original_json(report)
        if stage == "emission" and count == 2:
            swap()
        return result

    monkeypatch.setattr(api, "bounded_analysis_json", encoded)

    class Clock:
        def now(self):
            return selected_request.data_selection_time

    assert (
        cli.main(fixture.arguments(tmp_path, selected_request), trusted_clock=Clock())
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "internal_error\n"
    assert (tmp_path / "original").exists()


def test_output_four_mebibytes_and_plus_one():
    report = {"value": ""}
    overhead = len(canonical_bytes(report))
    report["value"] = "a" * (4 * 1024 * 1024 - overhead)
    assert len(api.bounded_analysis_json(report)) == 4 * 1024 * 1024
    report["value"] += "a"
    with pytest.raises(ValueError, match="exceeds limit"):
        api.bounded_analysis_json(report)


def test_unexpected_private_diagnostic_never_leaks(
    tmp_path, selected_request, monkeypatch, capsys, mock_dossiers
):
    def fail(*args, **kwargs):
        raise ValueError("PRIVATE_PATH_TOKEN_SECRET")

    monkeypatch.setattr(api, "research_current_volume", fail)

    class Clock:
        def now(self):
            return selected_request.data_selection_time

    assert (
        cli.main(fixture.arguments(tmp_path, selected_request), trusted_clock=Clock())
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "internal_error\n"


@pytest.mark.parametrize("missing", ["calendar", "mapping", "screen", "unsupported"])
def test_real_absence_and_unsupported_context_preserve_price_report(
    tmp_path, monkeypatch, missing
):

    monkeypatch.setattr(
        api.cohort, "run_agent_cohort_research_current", fixture.dossier_report
    )
    root, selected_request, _ = retained.retained(
        tmp_path, monkeypatch, target_action=missing == "unsupported"
    )
    if missing == "calendar":
        selected_request = replace(selected_request, schedule_identity_sha256="a" * 64)
    elif missing == "mapping":
        # An explicit third canonical target has no mapping in this retained snapshot.
        absent = replace(
            selected_request.members[0],
            isin="INE002A01018",
            effective_symbol="RELIANCE",
        )
        selected_request = replace(selected_request, members=(absent,))
    elif missing == "screen":
        remove_action_metadata(root)
    report = run(selected_request, root)
    row = report["members"][0]
    assert row["features"]["PRICE"]["fact"] == {"direction": "UP"}
    reason = {
        "calendar": "CALENDAR_PREREQUISITE_MISSING",
        "mapping": "RAW_MAPPING_UNSUPPORTED",
        "screen": "SCREEN_UNAVAILABLE",
        "unsupported": "ACTION_IN_WINDOW",
    }[missing]
    assert row["volume_context"]["outcome"]["reason"] == reason
    assert row["relative_strength_context"]["outcome"]["reason"] == reason
    assert row["volume_context"]["outcome"]["fact"] is None
    assert report["jointly_comparable"] is True


def test_real_missing_volume_cannot_hide_corrupt_reference(
    tmp_path, selected_request, monkeypatch, capsys
):

    monkeypatch.setattr(
        api.cohort, "run_agent_cohort_research_current", fixture.dossier_report
    )
    root = tmp_path / "root"
    seed_root(root, retained_action=True, request_value=selected_request.raw_input())
    acquired = StorageRootLease.try_acquire_existing(root)
    assert acquired.lease is not None
    with acquired.lease as lease, DuckDBCatalog(root, lease=lease) as catalog:
        metadata, _ = CorporateActionSnapshotStoreV1(root, lease, catalog).resolve(
            isin=selected_request.reference.isin,
            knowledge_cutoff=selected_request.data_selection_time,
        )
        path = root / metadata.relative_object_path
        path.chmod(0o600)
        path.write_bytes(b"PRIVATE_CORRUPT_REFERENCE")
    completed = []
    original = api.research_current_volume

    def observe(*args, **kwargs):
        result = original(*args, **kwargs)
        completed.append(result)
        return result

    monkeypatch.setattr(api, "research_current_volume", observe)

    class Clock:
        def now(self):
            return selected_request.data_selection_time

    assert (
        cli.main(fixture.arguments(tmp_path, selected_request), trusted_clock=Clock())
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "internal_error\n"
    assert (
        len(completed) == 1
        and completed[0]["members"][0]["reason"] == "RAW_BAR_MISSING"
    )


def test_real_held_root_interruption_retry_and_legacy_rollback(
    tmp_path, monkeypatch, capsys
):

    root, selected_request, wire = retained.retained(tmp_path, monkeypatch)
    before = retained.inventory(root)
    acquired = StorageRootLease.try_acquire_existing(root)
    assert acquired.lease is not None
    with acquired.lease, pytest.raises(RuntimeError):
        run(selected_request, root, research=fixture.forbidden)
    original = rs_service._project

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(rs_service, "_project", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run(selected_request, root)
    monkeypatch.setattr(rs_service, "_project", original)
    assert run(selected_request, root) == run(selected_request, root)

    class Clock:
        def now(self):
            return selected_request.data_selection_time

    # Rollback/legacy opt-in: the same retained root is still usable through V1–V4.
    for version in ("v1", "v2", "v3", "v4"):
        args = fixture.arguments(tmp_path, selected_request)[:-2]
        args[args.index("--contract-version") + 1] = version
        if version != "v4":
            args = args[: args.index("--context-symbol")]
        assert (
            cli.main(
                args,
                trusted_clock=Clock(),
                current_stock_research_v2=fixture.unavailable_research(
                    selected_request
                ),
            )
            == 1
        )
        captured = capsys.readouterr()
        report = json.loads(captured.out)
        assert report["contract_version"] == f"agent-current-research-run@{version}"
        assert (
            "analysis_context" not in report
            and "volume_context" not in report["members"][0]
        )
    assert retained.inventory(root) == before and wire.attempts == 2


def test_sdk_revalidates_cohort_mapping_values_before_effects(
    tmp_path, selected_request, monkeypatch
):

    # Reuse the public mapping parser rather than fabricate a dataclass shape.
    value = mapping_fixture._document()
    mapping = parse_agent_cohort_mappings(
        json.dumps(value).encode(),
        tuple(row["effective_symbol"] for row in value["members"]),
    )
    monkeypatch.setattr(
        api.cohort, "run_agent_cohort_research_current", fixture.forbidden
    )
    object.__setattr__(mapping.members[0], "mapping_identity", "a" * 64)
    with pytest.raises(CurrentStockResearchInputError):
        run(
            selected_request,
            tmp_path / "absent",
            mappings=mapping,
            context_symbols=tuple(row["effective_symbol"] for row in value["members"]),
        )
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "OTHER"),
        ("price_basis", "ADJUSTED"),
        ("evidence_cutoff", "2000-01-01T00:00:00.000000Z"),
        ("producer_selection_identity_sha256", "f" * 64),
    ],
)
def test_producer_source_time_or_selection_substitution_rejected(
    tmp_path, selected_request, monkeypatch, mock_dossiers, field, value
):
    original = api.research_current_relative_strength

    def altered(*args, **kwargs):
        result = original(*args, **kwargs)
        result[field] = value
        result.pop("result_identity_sha256")
        result["result_identity_sha256"] = identity(result)
        return result

    monkeypatch.setattr(api, "research_current_relative_strength", altered)
    with pytest.raises(ValueError, match="binding"):
        run(selected_request, tmp_path / "root")


def test_absent_root_rejected_before_v4_or_late_adoption(
    tmp_path, selected_request, monkeypatch
):
    root = tmp_path / "root"
    calls = []

    def create_after_boundary(*args, **kwargs):
        calls.append("v4")
        return fixture.dossier_report(*args, **kwargs)

    monkeypatch.setattr(
        api.cohort, "run_agent_cohort_research_current", create_after_boundary
    )
    assert not root.exists()
    with pytest.raises(RuntimeError):
        run(selected_request, root)
    assert calls == [] and not root.exists()


@pytest.mark.parametrize("unsafe", ["public", "link"])
def test_unsafe_root_stops_before_research(
    tmp_path, selected_request, monkeypatch, unsafe
):
    root = tmp_path / "root"
    if unsafe == "public":
        root.mkdir(mode=0o755)
    else:
        target = tmp_path / "target"
        target.mkdir(mode=0o700)
        root.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(
        api.cohort, "run_agent_cohort_research_current", fixture.forbidden
    )
    with pytest.raises(RuntimeError):
        run(selected_request, root)


def test_oversized_v5_cli_has_no_partial_output(
    tmp_path, selected_request, monkeypatch, capsys
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)

    def oversized(*args, **kwargs):
        report = fixture.dossier_report(*args, **kwargs)
        report["limitations"] = ["a" * (4 * 1024 * 1024)]
        return report

    monkeypatch.setattr(api.cohort, "run_agent_cohort_research_current", oversized)

    class Clock:
        def now(self):
            return selected_request.data_selection_time

    assert (
        cli.main(fixture.arguments(tmp_path, selected_request), trusted_clock=Clock())
        == 2
    )
    output = capsys.readouterr()
    assert output.out == "" and output.err == "internal_error\n"
