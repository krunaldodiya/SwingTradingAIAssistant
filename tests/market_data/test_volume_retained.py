"""Volume facts must traverse real temporary-root retained evidence admission."""

import hashlib
import json
from dataclasses import replace
from datetime import timedelta

import pytest
from current_raw_acquisition_fixtures import (
    FixtureTokenProvider,
    RecordedWire,
    WireReply,
    control,
    corrupt_action_snapshot,
    historical_body,
    members,
    remove_action_metadata,
    schedule,
    seed_root,
)
from current_raw_acquisition_fixtures import request as raw_request

import swing_trading_ai_assistant.market_data.current_raw_acquisition as acquisition
import swing_trading_ai_assistant.market_data.current_raw_acquisition_transport as transport
import swing_trading_ai_assistant.market_data.current_raw_price_context as raw_context
import swing_trading_ai_assistant.volume_analysis.service as volume_service
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.volume_analysis import (
    VolumeRequest,
    research_current_volume,
)


def retained(tmp_path, monkeypatch, *, zero=False, action=False, schedule_value=None):
    root = tmp_path / "root"
    raw = seed_root(
        root,
        retained_action=True,
        action_in_window=action,
        schedule_value=schedule_value,
    )
    body = json.loads(
        historical_body(None if schedule_value is None else schedule_value.sessions)
    )
    if zero:
        for candle in body["data"]["candles"]:
            candle[5] = 0
    wire = RecordedWire([WireReply(body=json.dumps(body).encode())])
    monkeypatch.setattr(transport, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    result = acquisition.acquire_missing_current_raw_evidence_v1(
        raw, root, control=control(raw)
    )
    assert result.outcome == "ACQUISITION_COMPLETED"
    assert wire.attempts == 1
    request = VolumeRequest(
        raw.data_selection_time,
        raw.admission_deadline,
        raw.schedule_identity_sha256,
        raw.members,
    )
    return root, request, wire


def inventory(root):
    return {
        str(path.relative_to(root)): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mode,
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def test_real_retained_volume_and_cli_are_identical_and_do_not_write(
    tmp_path, monkeypatch, capsys
):
    root, request, wire = retained(tmp_path, monkeypatch)
    before = inventory(root)
    result = research_current_volume(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["state"] == "OBSERVED"
    assert result["members"][0]["fact"] == {
        "baseline_numerator": 10,
        "baseline_denominator": 1,
        "relative_numerator": 1,
        "relative_denominator": 1,
        "relation": "EQUAL",
    }
    assert len(result["sessions"]) == 21
    assert result["members"][0]["source"]["partition_checksums"]
    assert result["members"][0]["source"]["screen_identity_sha256"]
    path = tmp_path / "request.json"
    path.write_bytes(request.canonical_bytes)
    path.chmod(0o600)

    class Clock:
        def now(self):
            return request.data_selection_time

    status = main(
        [
            "volume-context-current",
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
    assert status == 0 and not captured.err
    assert json.loads(captured.out) == result
    assert wire.attempts == 1
    assert inventory(root) == before
    assert str(root) not in captured.out and "fixture-token" not in captured.out


@pytest.mark.parametrize(
    "zero,action,reason",
    [
        (True, False, "ZERO_BASELINE"),
        (False, True, "ACTION_IN_WINDOW"),
        (True, True, "ACTION_IN_WINDOW"),
    ],
)
def test_zero_baseline_and_action_precedence(
    tmp_path, monkeypatch, zero, action, reason
):
    root, request, _ = retained(tmp_path, monkeypatch, zero=zero, action=action)
    result = research_current_volume(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["state"] == "NONREADY"
    assert result["members"][0]["reason"] == reason
    assert result["members"][0]["fact"] is None


def test_held_root_is_terminal_even_with_zero_baseline(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch, zero=True)
    before = inventory(root)
    acquired = StorageRootLease.try_acquire_existing(root)
    assert acquired.lease is not None
    with acquired.lease, pytest.raises(RuntimeError):
        research_current_volume(
            request, root, clock=lambda: request.data_selection_time
        )
    assert inventory(root) == before


def test_deadline_expiry_never_emits_partial_json(tmp_path, monkeypatch, capsys):
    root, request, _ = retained(tmp_path, monkeypatch)
    path = tmp_path / "request.json"
    path.write_bytes(request.canonical_bytes)
    path.chmod(0o600)

    class Clock:
        def now(self):
            return request.admission_deadline + timedelta(seconds=1)

    status = main(
        [
            "volume-context-current",
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
    assert status == 2 and captured.out == ""
    assert captured.err == "internal_error\n"


def test_corrupt_action_evidence_is_terminal_even_with_zero_volume(
    tmp_path, monkeypatch
):
    root, request, _ = retained(tmp_path, monkeypatch, zero=True)
    corrupt_action_snapshot(root)
    with pytest.raises(RuntimeError):
        research_current_volume(
            request, root, clock=lambda: request.data_selection_time
        )


@pytest.mark.parametrize(
    "missing,reason", [("mapping", "RAW_MAPPING_MISSING"), ("bars", "RAW_BAR_MISSING")]
)
def test_absent_dependency_is_nonready_without_writes(tmp_path, missing, reason):
    root = tmp_path / "root"
    raw = seed_root(root, retained_action=True, retain_mapping=missing != "mapping")
    request = VolumeRequest(
        raw.data_selection_time,
        raw.admission_deadline,
        raw.schedule_identity_sha256,
        raw.members,
    )
    before = inventory(root)
    result = research_current_volume(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["state"] == "NONREADY"
    assert result["members"][0]["reason"] == reason
    assert result["members"][0]["fact"] is None
    assert inventory(root) == before


def test_missing_screen_is_nonready(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    remove_action_metadata(root)
    result = research_current_volume(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["members"][0]["reason"] == "SCREEN_UNAVAILABLE"
    assert result["members"][0]["fact"] is None


def test_special_session_is_not_compared_to_regular_baseline(tmp_path, monkeypatch):
    original = schedule()
    altered = replace(
        original,
        sessions=original.sessions[:-1]
        + (replace(original.sessions[-1], kind="SPECIAL"),),
    )
    root, request, _ = retained(tmp_path, monkeypatch, schedule_value=altered)
    result = research_current_volume(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["members"][0]["reason"] == "SESSION_COMPARABILITY_UNSUPPORTED"
    assert result["members"][0]["fact"] is None


def test_corrupt_catalog_is_terminal_when_calendar_is_missing(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    request = replace(request, schedule_identity_sha256="a" * 64)
    catalog = root / "catalog.duckdb"
    catalog.write_bytes(b"corrupt")
    with pytest.raises(RuntimeError):
        research_current_volume(
            request, root, clock=lambda: request.data_selection_time
        )


def test_missing_member_does_not_suppress_admitted_member_and_order_is_preserved(
    tmp_path, monkeypatch
):
    root, request, _ = retained(tmp_path, monkeypatch)
    request = replace(request, members=tuple(reversed(members(2))))
    result = research_current_volume(
        request, root, clock=lambda: request.data_selection_time
    )
    assert [item["member"]["isin"] for item in result["members"]] == [
        item.isin for item in request.members
    ]
    assert result["members"][0]["fact"] is None
    assert result["members"][1]["fact"]["relation"] == "EQUAL"
    assert result["state"] == "NONREADY"


@pytest.mark.parametrize("tamper", ["parquet", "root"])
def test_source_or_root_replacement_during_math_is_terminal(
    tmp_path, monkeypatch, tamper
):
    root, request, _ = retained(tmp_path, monkeypatch)
    calculate = volume_service.calculate_volume

    def altered(grid):
        if tamper == "parquet":
            path = next(root.rglob("*.parquet"))
            path.chmod(0o600)
            path.write_bytes(b"changed")
        else:
            root.rename(tmp_path / "old-root")
            root.mkdir(mode=0o700)
        return calculate(grid)

    monkeypatch.setattr(volume_service, "calculate_volume", altered)
    with pytest.raises((ValueError, RuntimeError)):
        research_current_volume(
            request, root, clock=lambda: request.data_selection_time
        )


def test_interruption_releases_lease_and_retry_uses_identical_evidence(
    tmp_path, monkeypatch
):
    root, request, _ = retained(tmp_path, monkeypatch)
    before = inventory(root)
    project = volume_service._project

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(volume_service, "_project", interrupted)
    with pytest.raises(KeyboardInterrupt):
        research_current_volume(
            request, root, clock=lambda: request.data_selection_time
        )
    assert inventory(root) == before
    monkeypatch.setattr(volume_service, "_project", project)
    one = research_current_volume(
        request, root, clock=lambda: request.data_selection_time
    )
    two = research_current_volume(
        request, root, clock=lambda: request.data_selection_time
    )
    assert one == two
    assert inventory(root) == before


def test_forged_producer_token_is_not_admitted(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    read = volume_service.read_retained_current_raw_context_v1

    def forged(*args, **kwargs):
        outcome = read(*args, **kwargs)
        fake = object.__new__(raw_context.AdmittedCurrentRawContextV1)
        object.__setattr__(fake, "_seal", object())
        return replace(outcome, admitted=fake)

    monkeypatch.setattr(volume_service, "read_retained_current_raw_context_v1", forged)
    with pytest.raises(ValueError, match="not admitted"):
        research_current_volume(
            request, root, clock=lambda: request.data_selection_time
        )


def test_result_identity_covers_exact_payload(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    result = research_current_volume(
        request, root, clock=lambda: request.data_selection_time
    )
    expected = result.pop("result_identity_sha256")
    encoded = (
        json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    assert hashlib.sha256(encoded).hexdigest() == expected


def test_corrupt_calendar_is_terminal(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    path = (
        root
        / "calendar-schedules"
        / "sha256"
        / (request.schedule_identity_sha256 + ".json")
    )
    path.chmod(0o600)
    path.write_bytes(b"{}")
    with pytest.raises(RuntimeError):
        research_current_volume(
            request, root, clock=lambda: request.data_selection_time
        )


def test_volume_missing_partition_mode_preserves_legacy_projection(tmp_path):
    root = tmp_path / "root"
    raw = seed_root(root, retained_action=True)
    acquired = StorageRootLease.try_acquire_existing(root)
    assert acquired.lease is not None
    with acquired.lease as lease:
        legacy = raw_context.read_retained_current_raw_context_v1(
            root, request=raw, lease=lease, control=control(raw)
        )
        assert legacy.admitted is not None
        assert (
            raw_context.validate_admitted_current_raw_context_v1(legacy.admitted)
            .members[0]
            .reason
            == "RAW_PARTITION_CORRUPT"
        )
        volume = raw_context.read_retained_current_raw_context_v1(
            root,
            request=raw,
            lease=lease,
            control=control(raw),
            distinguish_missing_partitions=True,
        )
        assert volume.admitted is not None
        assert (
            raw_context.validate_admitted_current_raw_context_v1(volume.admitted)
            .members[0]
            .reason
            == "RAW_BAR_MISSING"
        )


def test_producer_token_for_another_request_is_rejected(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    read = volume_service.read_retained_current_raw_context_v1

    def substitute(*args, **kwargs):
        kwargs["request"] = replace(kwargs["request"], request_identity_sha256="f" * 64)
        return read(*args, **kwargs)

    monkeypatch.setattr(
        volume_service, "read_retained_current_raw_context_v1", substitute
    )
    with pytest.raises((ValueError, RuntimeError)):
        research_current_volume(
            request, root, clock=lambda: request.data_selection_time
        )


def test_future_known_bar_source_never_produces_volume(tmp_path, monkeypatch):
    root, request, _ = retained(tmp_path, monkeypatch)
    read = raw_context._member_rows

    def future(*args, **kwargs):
        rows, checksums, times = read(*args, **kwargs)
        return rows, checksums, tuple(request.admission_deadline for _ in times)

    monkeypatch.setattr(raw_context, "_member_rows", future)
    result = research_current_volume(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["members"][0]["fact"] is None
    assert result["members"][0]["reason"] == "SOURCE_FUTURE_KNOWN"


@pytest.mark.parametrize("partial", [True, False])
def test_only_latest_twenty_one_completed_sessions_are_selected(tmp_path, partial):
    original = schedule()
    selected = original.sessions[-1].close_at - timedelta(seconds=30 if partial else 0)
    calendar = replace(original, as_of=selected)
    root = tmp_path / "root"
    raw = seed_root(root, schedule_value=calendar, retain_mapping=False)
    request = VolumeRequest(
        selected,
        selected + timedelta(minutes=20),
        raw.schedule_identity_sha256,
        raw.members,
    )
    result = research_current_volume(request, root, clock=lambda: selected)
    expected = [
        item.trade_date.isoformat()
        for item in calendar.sessions
        if item.close_at <= selected
    ][-21:]
    assert [item["session"] for item in result["sessions"]] == expected
    assert len(expected) == 21
    assert all(item["fact"] is None for item in result["members"])


def test_future_known_calendar_is_not_used(tmp_path):
    calendar = schedule()
    root = tmp_path / "root"
    raw = seed_root(
        root,
        schedule_value=replace(calendar, as_of=calendar.as_of + timedelta(seconds=1)),
    )
    request = VolumeRequest(
        raw.data_selection_time,
        raw.admission_deadline,
        raw.schedule_identity_sha256,
        raw.members,
    )
    result = research_current_volume(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["members"][0]["reason"] == "CALENDAR_FUTURE_KNOWN"
    assert result["members"][0]["fact"] is None


def test_unequal_regular_session_duration_is_unsupported(tmp_path):
    original = schedule()
    last = original.sessions[-1]
    calendar = replace(
        original,
        sessions=original.sessions[:-1]
        + (replace(last, close_at=last.close_at + timedelta(minutes=1)),),
    )
    root = tmp_path / "root"
    raw = seed_root(root, schedule_value=calendar, retain_mapping=False)
    request = VolumeRequest(
        raw.data_selection_time,
        raw.admission_deadline,
        raw.schedule_identity_sha256,
        raw.members,
    )
    result = research_current_volume(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["members"][0]["reason"] == "SESSION_COMPARABILITY_UNSUPPORTED"
    assert result["members"][0]["fact"] is None


@pytest.mark.parametrize(
    "mutation,reason",
    [("missing", "RAW_BAR_MISSING"), ("conflict", None), ("invalid", None)],
)
def test_raw_minute_failure_cannot_be_averaged_away(
    tmp_path, monkeypatch, mutation, reason
):
    root, request, _ = retained(tmp_path, monkeypatch)
    read = raw_context._member_rows

    def changed(*args, **kwargs):
        rows, checksums, times = read(*args, **kwargs)
        changed_rows = (
            rows[1:]
            if mutation == "missing"
            else (rows[0], *rows)
            if mutation == "conflict"
            else (object(), *rows[1:])
        )
        return changed_rows, checksums, times

    monkeypatch.setattr(raw_context, "_member_rows", changed)
    if reason is None:
        with pytest.raises(RuntimeError):
            research_current_volume(
                request, root, clock=lambda: request.data_selection_time
            )
    else:
        result = research_current_volume(
            request, root, clock=lambda: request.data_selection_time
        )
        assert result["members"][0]["reason"] == reason
        assert result["members"][0]["fact"] is None


def test_over_range_daily_volume_withholds_only_affected_member(tmp_path, monkeypatch):
    value = schedule()
    value = replace(
        value,
        sessions=tuple(
            replace(item, close_at=item.open_at + timedelta(minutes=2))
            for item in value.sessions
        ),
    )
    raw = raw_request(value, members=members(2))
    root = tmp_path / "root"
    seed_root(root, retained_action=True, schedule_value=value, request_value=raw)

    def body(volume):
        candles = [
            [
                (item.open_at + timedelta(minutes=offset)).isoformat(),
                100.0,
                101.0,
                99.0,
                100.5,
                volume,
                None,
            ]
            for item in value.sessions
            for offset in range(2)
        ]
        return json.dumps({"status": "success", "data": {"candles": candles}}).encode()

    wire = RecordedWire([WireReply(body=body(2**62)), WireReply(body=body(10))])
    monkeypatch.setattr(transport, "build_opener", wire.build_opener)
    monkeypatch.setattr(
        acquisition, "EnvironmentAccessTokenProvider", FixtureTokenProvider
    )
    acquired = acquisition.acquire_missing_current_raw_evidence_v1(
        raw, root, control=control(raw)
    )
    assert acquired.outcome == "ACQUISITION_COMPLETED"
    request = VolumeRequest(
        raw.data_selection_time,
        raw.admission_deadline,
        raw.schedule_identity_sha256,
        raw.members,
    )
    before = inventory(root)
    result = research_current_volume(
        request, root, clock=lambda: request.data_selection_time
    )
    assert result["state"] == "NONREADY"
    assert result["members"][0]["state"] == "UNSUPPORTED"
    assert result["members"][0]["reason"] == "VOLUME_RANGE_UNSUPPORTED"
    assert result["members"][0]["fact"] is None
    assert result["members"][1]["state"] == "OBSERVED"
    assert result["members"][1]["fact"]["baseline_numerator"] == 20
    assert result["members"][1]["fact"]["relation"] == "EQUAL"
    assert inventory(root) == before
    assert wire.attempts == 2
