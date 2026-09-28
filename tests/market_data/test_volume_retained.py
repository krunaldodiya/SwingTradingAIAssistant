"""Volume facts must traverse real temporary-root retained evidence admission."""

import hashlib
import json
from datetime import timedelta

import pytest
from current_raw_acquisition_fixtures import (
    FixtureTokenProvider,
    RecordedWire,
    WireReply,
    control,
    corrupt_action_snapshot,
    historical_body,
    seed_root,
)

import swing_trading_ai_assistant.market_data.current_raw_acquisition as acquisition
import swing_trading_ai_assistant.market_data.current_raw_acquisition_transport as transport
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.volume_analysis import (
    VolumeRequest,
    research_current_volume,
)


def retained(tmp_path, monkeypatch, *, zero=False, action=False):
    root = tmp_path / "root"
    raw = seed_root(root, retained_action=True, action_in_window=action)
    body = json.loads(historical_body())
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
