"""Plan 41 admission crosses the real retained producer and CLI boundary."""

import hashlib
import json
from dataclasses import replace
from datetime import timedelta

import pytest
from current_raw_acquisition_fixtures import (
    FixedClock,
    FixtureTokenProvider,
    RecordedWire,
    StaticTransport,
    WireReply,
    action_body,
    control,
    corrupt_action_snapshot,
    historical_body,
    members,
    remove_action_metadata,
    schedule,
    seed_root,
)
from current_raw_acquisition_fixtures import (
    request as raw_request,
)

import swing_trading_ai_assistant.market_data.current_raw_acquisition as acquisition
import swing_trading_ai_assistant.market_data.current_raw_acquisition_transport as transport
import swing_trading_ai_assistant.market_data.current_raw_price_context as raw_context
import swing_trading_ai_assistant.relative_strength.service as service
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.corporate_actions import (
    CorporateActionSnapshotStoreV1,
    UpstoxCorporateActionsClientV1,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextMemberV1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.relative_strength import (
    RelativeStrengthRequest,
    research_current_relative_strength,
)


def inventory(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def retained(
    tmp_path,
    monkeypatch,
    *,
    reference_action=False,
    target_action=False,
    reference_last=210,
):
    reference, target = members(2)[::-1]
    initial = raw_request(members=(reference, target))
    root = tmp_path / "root"
    seeded = seed_root(root, retained_action=False, request_value=initial)
    acquired = StorageRootLease.try_acquire_existing(root)
    assert acquired.lease is not None
    with acquired.lease as lease, DuckDBCatalog(root, lease=lease) as catalog:
        store = CorporateActionSnapshotStoreV1(root, lease, catalog)
        for member, action in ((reference, reference_action), (target, target_action)):
            snapshot = UpstoxCorporateActionsClientV1(
                StaticTransport(action_body(in_window=action)),
                clock=FixedClock().now,
            ).fetch_strict(member.isin, "fixture-token")
            store.retain(snapshot)
    sessions = len(schedule().sessions)
    wire = RecordedWire(
        [
            WireReply(
                body=historical_body(closes=(200,) * (sessions - 1) + (reference_last,))
            ),
            WireReply(body=historical_body(closes=(100,) * (sessions - 1) + (110,))),
        ]
    )
    monkeypatch.setattr(transport, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    completed = acquisition.acquire_missing_current_raw_evidence_v1(
        seeded, root, control=control(seeded)
    )
    assert completed.outcome == "ACQUISITION_COMPLETED"
    assert wire.attempts == 2
    request = RelativeStrengthRequest(
        seeded.data_selection_time,
        seeded.admission_deadline,
        seeded.schedule_identity_sha256,
        reference,
        (target,),
    )
    return root, request, wire


def test_retained_producer_sdk_cli_exact_and_read_only(tmp_path, monkeypatch, capsys):
    root, request, wire = retained(tmp_path, monkeypatch)
    before = inventory(root)
    result = research_current_relative_strength(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["state"] == "OBSERVED"
    assert result["reference"]["state"] == "OBSERVED"
    assert result["members"][0]["fact"] == {
        "target_change_numerator": 1,
        "target_change_denominator": 10,
        "reference_change_numerator": 1,
        "reference_change_denominator": 20,
        "difference_percentage_points_numerator": 5,
        "difference_percentage_points_denominator": 1,
        "relation": "ABOVE",
    }
    assert len(result["sessions"]) == 21
    assert result["producer_members"][0] == result["reference"]["member"]
    assert result["reference"]["source"]["screen_identity_sha256"]
    assert result["members"][0]["source"]["partition_checksums"]
    path = tmp_path / "request.json"
    path.write_bytes(request.canonical_bytes)
    path.chmod(0o600)

    class Clock:
        def now(self):
            return request.data_selection_time

    status = main(
        [
            "relative-strength-current",
            "--input-file",
            str(path),
            "--storage-root",
            str(root),
            "--output",
            "json",
        ],
        trusted_clock=Clock(),
    )
    captured = capsys.readouterr()
    assert status == 0 and captured.err == ""
    assert json.loads(captured.out) == result
    assert wire.attempts == 2 and inventory(root) == before
    assert str(root) not in captured.out and "fixture-token" not in captured.out


def test_missing_reference_keeps_target_status(tmp_path):
    reference, target = members(2)[::-1]
    seeded = raw_request(members=(reference, target))
    root = tmp_path / "root"
    seed_root(root, retained_action=True, request_value=seeded)
    request = RelativeStrengthRequest(
        seeded.data_selection_time,
        seeded.admission_deadline,
        seeded.schedule_identity_sha256,
        reference,
        (target,),
    )
    result = research_current_relative_strength(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["state"] == "NONREADY"
    assert result["reference"]["reason"] == "RAW_BAR_MISSING"
    assert result["members"][0]["reason"] == "RAW_BAR_MISSING"
    assert result["members"][0]["comparison_reason"] == "REFERENCE_UNAVAILABLE"
    assert result["members"][0]["fact"] is None


def test_corrupt_target_with_missing_reference_is_terminal(tmp_path):
    reference, target = members(2)[::-1]
    seeded = raw_request(members=(reference, target))
    root = tmp_path / "root"
    seed_root(root, retained_action=True, request_value=seeded)
    corrupt_action_snapshot(root)
    request = RelativeStrengthRequest(
        seeded.data_selection_time,
        seeded.admission_deadline,
        seeded.schedule_identity_sha256,
        reference,
        (target,),
    )
    with pytest.raises(RuntimeError):
        research_current_relative_strength(
            request, root, clock=lambda: request.data_selection_time
        )


def test_cli_deadline_never_emits_partial_json(tmp_path, capsys):
    reference, target = members(2)[::-1]
    seeded = raw_request(members=(reference, target))
    request = RelativeStrengthRequest(
        seeded.data_selection_time,
        seeded.admission_deadline,
        seeded.schedule_identity_sha256,
        reference,
        (target,),
    )
    path = tmp_path / "request.json"
    path.write_bytes(request.canonical_bytes)
    path.chmod(0o600)

    class Clock:
        def now(self):
            return request.admission_deadline + timedelta(seconds=1)

    status = main(
        [
            "relative-strength-current",
            "--input-file",
            str(path),
            "--storage-root",
            str(tmp_path / "absent"),
            "--output",
            "json",
        ],
        trusted_clock=Clock(),
    )
    output = capsys.readouterr()
    assert status == 2 and output.out == "" and output.err == "internal_error\n"


@pytest.mark.parametrize(
    "reference_action,target_action", [(True, False), (False, True)]
)
def test_action_screen_withholds_exact_instrument(
    tmp_path, monkeypatch, reference_action, target_action
):
    root, request, _ = retained(
        tmp_path,
        monkeypatch,
        reference_action=reference_action,
        target_action=target_action,
    )
    result = research_current_relative_strength(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["state"] == "NONREADY"
    if reference_action:
        assert result["reference"]["reason"] == "ACTION_IN_WINDOW"
        assert result["members"][0]["state"] == "OBSERVED"
        assert result["members"][0]["comparison_reason"] == "REFERENCE_UNAVAILABLE"
    else:
        assert result["reference"]["state"] == "OBSERVED"
        assert result["members"][0]["reason"] == "ACTION_IN_WINDOW"
    assert result["members"][0]["fact"] is None


def test_observed_reference_does_not_substitute_missing_target(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    missing = CurrentPriceContextMemberV1(
        "INE002A01018",
        "NSE",
        "EQUITY",
        "EQ",
        "RELIANCE",
        request.reference.valid_from,
        request.reference.valid_through,
    )
    changed = replace(request, members=(missing, *request.members))
    result = research_current_relative_strength(
        changed, root, clock=lambda: changed.data_selection_time
    )
    assert result["reference"]["state"] == "OBSERVED"
    assert [item["member"]["effective_symbol"] for item in result["members"]] == [
        "RELIANCE",
        "ACME",
    ]
    assert result["members"][0]["fact"] is None
    assert result["members"][0]["reason"] == "RAW_MAPPING_UNSUPPORTED"
    assert result["members"][1]["fact"]["relation"] == "ABOVE"


@pytest.mark.parametrize("tamper", ["parquet", "root"])
def test_source_replaced_during_arithmetic_is_terminal(tmp_path, monkeypatch, tamper):
    root, request, _ = retained(tmp_path, monkeypatch)
    calculate = service.calculate_relative_strength

    def altered(*args):
        if tamper == "parquet":
            path = next(root.rglob("*.parquet"))
            path.chmod(0o600)
            path.write_bytes(b"changed")
        else:
            root.rename(tmp_path / "old-root")
            root.mkdir(mode=0o700)
        return calculate(*args)

    monkeypatch.setattr(service, "calculate_relative_strength", altered)
    with pytest.raises((ValueError, RuntimeError)):
        research_current_relative_strength(
            request, root, clock=lambda: request.data_selection_time
        )


def test_forged_admission_and_request_substitution_are_terminal(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    read = service.read_retained_current_raw_context_v1

    def forged(*args, **kwargs):
        outcome = read(*args, **kwargs)
        fake = object.__new__(raw_context.AdmittedCurrentRawContextV1)
        object.__setattr__(fake, "_seal", object())
        return replace(outcome, admitted=fake)

    monkeypatch.setattr(service, "read_retained_current_raw_context_v1", forged)
    with pytest.raises(ValueError, match="not admitted"):
        research_current_relative_strength(
            request, root, clock=lambda: request.data_selection_time
        )

    def substitute(*args, **kwargs):
        kwargs["request"] = replace(kwargs["request"], request_identity_sha256="f" * 64)
        return read(*args, **kwargs)

    monkeypatch.setattr(service, "read_retained_current_raw_context_v1", substitute)
    with pytest.raises((ValueError, RuntimeError)):
        research_current_relative_strength(
            request, root, clock=lambda: request.data_selection_time
        )


def test_future_known_retained_minutes_withhold_fact(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    read = raw_context._member_rows

    def future(*args, **kwargs):
        rows, checksums, times = read(*args, **kwargs)
        return rows, checksums, tuple(request.admission_deadline for _ in times)

    monkeypatch.setattr(raw_context, "_member_rows", future)
    result = research_current_relative_strength(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["state"] == "NONREADY"
    assert result["reference"]["reason"] == "SOURCE_FUTURE_KNOWN"
    assert result["members"][0]["reason"] == "SOURCE_FUTURE_KNOWN"
    assert result["members"][0]["fact"] is None


@pytest.mark.parametrize("mode", ["special", "unequal"])
def test_noncomparable_completed_sessions_are_unsupported(tmp_path, mode):
    original = schedule()
    last = original.sessions[-1]
    changed_last = (
        replace(last, kind="SPECIAL")
        if mode == "special"
        else replace(last, close_at=last.close_at + timedelta(minutes=1))
    )
    altered = replace(original, sessions=original.sessions[:-1] + (changed_last,))
    reference, target = members(2)[::-1]
    seeded = raw_request(altered, members=(reference, target))
    root = tmp_path / "root"
    seed_root(root, schedule_value=altered, request_value=seeded)
    request = RelativeStrengthRequest(
        seeded.data_selection_time,
        seeded.admission_deadline,
        seeded.schedule_identity_sha256,
        reference,
        (target,),
    )
    result = research_current_relative_strength(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["reference"]["reason"] == "SESSION_COMPARABILITY_UNSUPPORTED"
    assert result["members"][0]["reason"] == "SESSION_COMPARABILITY_UNSUPPORTED"
    assert result["members"][0]["fact"] is None


def test_missing_calendar_and_corrupt_catalog_precedence(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    missing_calendar = replace(request, schedule_identity_sha256="a" * 64)
    first = research_current_relative_strength(
        missing_calendar, root, clock=lambda: missing_calendar.data_selection_time
    )
    assert first["reference"]["reason"] == "CALENDAR_PREREQUISITE_MISSING"
    assert first["members"][0]["fact"] is None
    (root / "catalog.duckdb").write_bytes(b"corrupt")
    with pytest.raises(RuntimeError):
        research_current_relative_strength(
            missing_calendar, root, clock=lambda: missing_calendar.data_selection_time
        )


def test_corrupt_screen_with_missing_reference_is_terminal(tmp_path):
    reference, target = members(2)[::-1]
    seeded = raw_request(members=(reference, target))
    root = tmp_path / "root"
    seed_root(root, retained_action=True, request_value=seeded)
    corrupt_action_snapshot(root)
    request = RelativeStrengthRequest(
        seeded.data_selection_time,
        seeded.admission_deadline,
        seeded.schedule_identity_sha256,
        reference,
        (target,),
    )
    with pytest.raises(RuntimeError):
        research_current_relative_strength(
            request, root, clock=lambda: request.data_selection_time
        )


def test_held_root_interrupt_and_explicit_retry_are_read_only(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    before = inventory(root)
    acquired = StorageRootLease.try_acquire_existing(root)
    assert acquired.lease is not None
    with acquired.lease, pytest.raises(RuntimeError):
        research_current_relative_strength(
            request, root, clock=lambda: request.data_selection_time
        )
    project = service._project

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(service, "_project", interrupted)
    with pytest.raises(KeyboardInterrupt):
        research_current_relative_strength(
            request, root, clock=lambda: request.data_selection_time
        )
    monkeypatch.setattr(service, "_project", project)
    one = research_current_relative_strength(
        request, root, clock=lambda: request.data_selection_time
    )
    two = research_current_relative_strength(
        request, root, clock=lambda: request.data_selection_time
    )
    assert one == two and inventory(root) == before


def test_result_identity_covers_exact_public_payload(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    result = research_current_relative_strength(
        request, root, clock=lambda: request.data_selection_time
    )
    expected = result.pop("result_identity_sha256")
    encoded = (
        json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    assert hashlib.sha256(encoded).hexdigest() == expected


def test_missing_reference_does_not_hide_observed_target(tmp_path, monkeypatch):
    reference, target = members(2)[::-1]
    both = raw_request(members=(reference, target))
    root = tmp_path / "root"
    seed_root(root, retained_action=True, request_value=both)
    target_only = raw_request(members=(target,))
    wire = RecordedWire([WireReply(body=historical_body())])
    monkeypatch.setattr(transport, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    completed = acquisition.acquire_missing_current_raw_evidence_v1(
        target_only, root, control=control(target_only)
    )
    assert completed.outcome == "ACQUISITION_COMPLETED"
    request = RelativeStrengthRequest(
        both.data_selection_time,
        both.admission_deadline,
        both.schedule_identity_sha256,
        reference,
        (target,),
    )
    result = research_current_relative_strength(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["reference"]["reason"] == "RAW_BAR_MISSING"
    assert result["members"][0]["state"] == "OBSERVED"
    assert result["members"][0]["reason"] is None
    assert result["members"][0]["comparison_reason"] == "REFERENCE_UNAVAILABLE"
    assert result["members"][0]["fact"] is None


def test_missing_mapping_and_screen_are_local_nonready(tmp_path, monkeypatch):
    reference, target = members(2)[::-1]
    both = raw_request(members=(reference, target))
    root = tmp_path / "mapping-root"
    seed_root(root, retained_action=True, retain_mapping=False, request_value=both)
    request = RelativeStrengthRequest(
        both.data_selection_time,
        both.admission_deadline,
        both.schedule_identity_sha256,
        reference,
        (target,),
    )
    mapping = research_current_relative_strength(
        request, root, clock=lambda: request.data_selection_time
    )
    assert mapping["reference"]["reason"] == "RAW_MAPPING_MISSING"
    assert mapping["members"][0]["reason"] == "RAW_MAPPING_MISSING"
    positive_root, positive_request, _ = retained(tmp_path, monkeypatch)
    remove_action_metadata(positive_root)
    screened = research_current_relative_strength(
        positive_request,
        positive_root,
        clock=lambda: positive_request.data_selection_time,
    )
    assert screened["reference"]["state"] == "OBSERVED"
    assert screened["members"][0]["reason"] == "SCREEN_UNAVAILABLE"
    assert screened["members"][0]["fact"] is None


def test_mapping_validity_and_future_calendar_withhold_comparison(tmp_path):
    reference, target = members(2)[::-1]
    both = raw_request(members=(reference, target))
    root = tmp_path / "root"
    seed_root(root, retained_action=True, request_value=both)
    request = RelativeStrengthRequest(
        both.data_selection_time,
        both.admission_deadline,
        both.schedule_identity_sha256,
        reference,
        (target,),
    )
    later = replace(
        request,
        data_selection_time=request.data_selection_time + timedelta(days=1),
        admission_deadline=request.admission_deadline + timedelta(days=1),
    )
    stale = research_current_relative_strength(
        later, root, clock=lambda: later.data_selection_time
    )
    assert stale["reference"]["reason"] == "RAW_MAPPING_STALE"
    assert stale["members"][0]["fact"] is None

    future_schedule = replace(
        schedule(), as_of=both.data_selection_time + timedelta(seconds=1)
    )
    future_root = tmp_path / "future-root"
    seeded = raw_request(future_schedule, members=(reference, target))
    seed_root(future_root, schedule_value=future_schedule, request_value=seeded)
    future_request = RelativeStrengthRequest(
        seeded.data_selection_time,
        seeded.admission_deadline,
        seeded.schedule_identity_sha256,
        reference,
        (target,),
    )
    future = research_current_relative_strength(
        future_request, future_root, clock=lambda: future_request.data_selection_time
    )
    assert future["reference"]["reason"] == "CALENDAR_FUTURE_KNOWN"
    assert future["members"][0]["fact"] is None


def test_latest_twenty_one_completed_sessions_exclude_partial(tmp_path):
    original = schedule()
    selected = original.sessions[-1].close_at - timedelta(seconds=30)
    calendar = replace(original, as_of=selected)
    reference, target = members(2)[::-1]
    seeded = raw_request(calendar, selection=selected, members=(reference, target))
    root = tmp_path / "root"
    seed_root(root, schedule_value=calendar, request_value=seeded, retained_action=True)
    request = RelativeStrengthRequest(
        selected,
        seeded.admission_deadline,
        seeded.schedule_identity_sha256,
        reference,
        (target,),
    )
    result = research_current_relative_strength(request, root, clock=lambda: selected)
    expected = [
        item.trade_date.isoformat()
        for item in calendar.sessions
        if item.close_at <= selected
    ][-21:]
    assert len(expected) == 21
    assert [item["session"] for item in result["sessions"]] == expected
    assert result["members"][0]["fact"] is None


def test_admitted_endpoint_outside_numeric_bound_withholds_reference(
    tmp_path, monkeypatch
):
    root, request, _ = retained(tmp_path, monkeypatch, reference_last=1e17)
    result = research_current_relative_strength(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["reference"]["state"] == "UNSUPPORTED"
    assert result["reference"]["reason"] == "PRICE_RANGE_UNSUPPORTED"
    assert result["members"][0]["state"] == "OBSERVED"
    assert result["members"][0]["comparison_reason"] == "REFERENCE_UNAVAILABLE"


@pytest.mark.parametrize(
    "field,value",
    [("provider", "OTHER"), ("price_basis", "ADJUSTED"), ("bar_basis", "1d-other")],
)
def test_producer_source_or_basis_substitution_is_terminal(
    tmp_path, monkeypatch, field, value
):
    root, request, _ = retained(tmp_path, monkeypatch)
    binding = service.admitted_current_raw_context_binding_v1

    def substituted(token):
        projection, root_identity = binding(token)
        return replace(projection, **{field: value}), root_identity

    monkeypatch.setattr(service, "admitted_current_raw_context_binding_v1", substituted)
    with pytest.raises(RuntimeError):
        research_current_relative_strength(
            request, root, clock=lambda: request.data_selection_time
        )


def test_corrupt_partition_and_missing_reference_are_terminal(tmp_path, monkeypatch):
    reference, target = members(2)[::-1]
    both = raw_request(members=(reference, target))
    root = tmp_path / "root"
    seed_root(root, retained_action=True, request_value=both)
    target_only = raw_request(members=(target,))
    wire = RecordedWire([WireReply(body=historical_body())])
    monkeypatch.setattr(transport, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    completed = acquisition.acquire_missing_current_raw_evidence_v1(
        target_only, root, control=control(target_only)
    )
    assert completed.outcome == "ACQUISITION_COMPLETED"
    request = RelativeStrengthRequest(
        both.data_selection_time,
        both.admission_deadline,
        both.schedule_identity_sha256,
        reference,
        (target,),
    )
    path = next(root.rglob("*.parquet"))
    path.chmod(0o600)
    path.write_bytes(b"corrupt")
    with pytest.raises(RuntimeError):
        research_current_relative_strength(
            request, root, clock=lambda: request.data_selection_time
        )


def test_deadline_during_retained_read_is_terminal(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    now = request.data_selection_time
    read = raw_context._member_rows

    def delayed(*args, **kwargs):
        nonlocal now
        rows = read(*args, **kwargs)
        now = request.admission_deadline
        return rows

    monkeypatch.setattr(raw_context, "_member_rows", delayed)
    with pytest.raises(RuntimeError):
        research_current_relative_strength(request, root, clock=lambda: now)


def test_evidence_changed_during_result_identity_is_terminal(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    original = service.identity

    def altered(value):
        if (
            isinstance(value, dict)
            and value.get("contract_version") == "current-relative-strength@v1"
        ):
            path = next(root.rglob("*.parquet"))
            path.chmod(0o600)
            path.write_bytes(b"changed")
        return original(value)

    monkeypatch.setattr(service, "identity", altered)
    with pytest.raises((ValueError, RuntimeError)):
        research_current_relative_strength(
            request, root, clock=lambda: request.data_selection_time
        )
