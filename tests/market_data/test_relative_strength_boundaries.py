"""Plan 41 request, storage and clock failures emit no partial CLI result."""

import json
import os
from datetime import UTC, date, datetime, timedelta

import pytest

import swing_trading_ai_assistant.market_data.cli as cli
import swing_trading_ai_assistant.relative_strength.current as arithmetic
import swing_trading_ai_assistant.relative_strength.service as service
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextMemberV1,
)
from swing_trading_ai_assistant.relative_strength import (
    RelativeStrengthRequest,
    research_current_relative_strength,
)
from swing_trading_ai_assistant.relative_strength.request import canonical_bytes


def request():
    selected = datetime(2026, 9, 15, 9, tzinfo=UTC)
    reference = CurrentPriceContextMemberV1(
        "INE467B01037",
        "NSE",
        "EQUITY",
        "EQ",
        "BETA",
        date(2020, 1, 1),
        date(2030, 1, 1),
    )
    target = CurrentPriceContextMemberV1(
        "INE467B01029",
        "NSE",
        "EQUITY",
        "EQ",
        "ACME",
        date(2020, 1, 1),
        date(2030, 1, 1),
    )
    return RelativeStrengthRequest(
        selected, selected + timedelta(minutes=20), "a" * 64, reference, (target,)
    )


def synthetic_isin(index):
    prefix = f"INE{index:08d}"
    digits = "".join(str(ord(char) - 55) if char.isalpha() else char for char in prefix)
    for check in range(10):
        values = list(map(int, reversed(digits + str(check))))
        total = sum(
            value if position % 2 == 0 else (2 * value // 10 + 2 * value % 10)
            for position, value in enumerate(values)
        )
        if total % 10 == 0:
            return prefix + str(check)
    raise AssertionError("check digit unavailable")


def _private_request(tmp_path, value):
    path = tmp_path / "request.json"
    path.write_bytes(value.canonical_bytes)
    path.chmod(0o600)
    return path


@pytest.mark.parametrize(
    "unsafe", ["public", "symlink", "hardlink", "directory", "fifo", "oversize"]
)
def test_unsafe_input_has_no_output_or_root_creation(tmp_path, capsys, unsafe):
    value = request()
    root = tmp_path / "absent"
    path = tmp_path / "request.json"
    if unsafe == "directory":
        path.mkdir()
    elif unsafe == "fifo":
        os.mkfifo(path, 0o600)
    else:
        path.write_bytes(
            value.canonical_bytes if unsafe != "oversize" else b" " * 65537
        )
        path.chmod(0o644 if unsafe == "public" else 0o600)
        if unsafe in {"symlink", "hardlink"}:
            other = tmp_path / "other.json"
            path.rename(other)
            if unsafe == "symlink":
                path.symlink_to(other)
            else:
                os.link(other, path)
    status = main(
        [
            "relative-strength-current",
            "--input-file",
            str(path),
            "--storage-root",
            str(root),
            "--output",
            "json",
        ]
    )
    output = capsys.readouterr()
    assert status == 2 and output.out == ""
    assert not root.exists()


def test_absent_root_is_typed_nonready_without_creation(tmp_path, capsys):
    value = request()
    path = _private_request(tmp_path, value)
    root = tmp_path / "absent"

    class Clock:
        def now(self):
            return value.data_selection_time

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
    output = capsys.readouterr()
    assert status == 1 and output.err == ""
    result = json.loads(output.out)
    assert result["reference"]["reason"] == "CALENDAR_PREREQUISITE_MISSING"
    assert result["members"][0]["comparison_reason"] == "REFERENCE_UNAVAILABLE"
    assert not root.exists()


def test_forty_nine_targets_remain_bounded_and_ordered_on_missing_calendar(tmp_path):
    original = request()
    targets = tuple(
        CurrentPriceContextMemberV1(
            synthetic_isin(index),
            "NSE",
            "EQUITY",
            "EQ",
            f"S{index}",
            date(2020, 1, 1),
            date(2030, 1, 1),
        )
        for index in range(49)
    )
    value = RelativeStrengthRequest(
        original.data_selection_time,
        original.admission_deadline,
        original.schedule_identity_sha256,
        original.reference,
        targets,
    )
    result = research_current_relative_strength(
        value, tmp_path / "absent", clock=lambda: value.data_selection_time
    )
    assert result["requested_count"] == 49
    assert [item["member"]["isin"] for item in result["members"]] == [
        item.isin for item in targets
    ]
    assert all(
        item["comparison_reason"] == "REFERENCE_UNAVAILABLE"
        for item in result["members"]
    )
    assert len(canonical_bytes(result)) <= 1024 * 1024


@pytest.mark.parametrize("mutation", ["unknown", "version", "constant"])
def test_invalid_json_cli_rejects_before_storage(tmp_path, capsys, mutation):
    value = request()
    decoded = json.loads(value.canonical_bytes)
    if mutation == "unknown":
        decoded["unknown"] = 1
    elif mutation == "version":
        decoded["contract_version"] = "wrong"
    else:
        decoded["unknown"] = float("nan")
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(decoded, allow_nan=True))
    path.chmod(0o600)
    root = tmp_path / "absent"
    status = main(
        [
            "relative-strength-current",
            "--input-file",
            str(path),
            "--storage-root",
            str(root),
            "--output",
            "json",
        ]
    )
    output = capsys.readouterr()
    assert status == 2 and output.out == "" and not root.exists()


@pytest.mark.parametrize("case", ["file", "symlink", "public"])
def test_unsafe_root_is_terminal(tmp_path, case):
    value = request()
    root = tmp_path / "root"
    if case == "file":
        root.write_text("wrong type")
    elif case == "symlink":
        target = tmp_path / "target"
        target.mkdir(mode=0o700)
        root.symlink_to(target)
    else:
        root.mkdir(mode=0o755)
    with pytest.raises((ValueError, RuntimeError, OSError)):
        research_current_relative_strength(
            value, root, clock=lambda: value.data_selection_time
        )


@pytest.mark.parametrize(
    "case", ["before", "deadline", "regression", "rollover", "naive"]
)
def test_clock_failure_stops_without_storage_effect(tmp_path, case):
    value = request()
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    values = {
        "before": [value.data_selection_time - timedelta(microseconds=1)],
        "deadline": [value.admission_deadline],
        "regression": [
            value.data_selection_time + timedelta(seconds=2),
            value.data_selection_time,
        ],
        "rollover": [
            value.data_selection_time,
            datetime(2026, 9, 15, 18, 30, tzinfo=UTC),
        ],
        "naive": [value.data_selection_time.replace(tzinfo=None)],
    }[case]

    def clock():
        return values.pop(0) if len(values) > 1 else values[0]

    with pytest.raises((ValueError, RuntimeError)):
        research_current_relative_strength(value, root, clock=clock)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("case", ["deadline", "rollover", "regression", "naive"])
def test_cli_checks_clock_after_serialization(tmp_path, monkeypatch, capsys, case):
    value = request()
    path = _private_request(tmp_path, value)
    current = value.data_selection_time + timedelta(seconds=1)
    serialize = cli.relative_strength_json

    def delayed(payload):
        nonlocal current
        output = serialize(payload)
        current = {
            "deadline": value.admission_deadline,
            "rollover": datetime(2026, 9, 15, 18, 30, tzinfo=UTC),
            "regression": value.data_selection_time,
            "naive": value.data_selection_time.replace(tzinfo=None),
        }[case]
        return output

    class Clock:
        def now(self):
            return current

    monkeypatch.setattr(cli, "relative_strength_json", delayed)
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


def test_runtime_source_origin_substitution_rejected_before_storage(
    tmp_path, monkeypatch
):
    value = request()
    copied = tmp_path / "current.py"
    copied.write_text("# unrelated source")
    monkeypatch.setattr(arithmetic, "__file__", str(copied))
    with pytest.raises(ValueError, match="runtime.*identity invalid"):
        research_current_relative_strength(
            value, tmp_path / "absent", clock=lambda: value.data_selection_time
        )
    assert not (tmp_path / "absent").exists()


def test_runtime_manifest_digest_substitution_rejected_before_storage(
    tmp_path, monkeypatch
):
    value = request()
    original = service.RELATIVE_STRENGTH_RUNTIME_SOURCE_SHA256_V1
    substituted = dict(original)
    key = "src/swing_trading_ai_assistant/relative_strength/current.py"
    substituted[key] = "0" * 64
    monkeypatch.setattr(
        service, "RELATIVE_STRENGTH_RUNTIME_SOURCE_SHA256_V1", substituted
    )
    with pytest.raises(ValueError, match="runtime identity invalid"):
        research_current_relative_strength(
            value, tmp_path / "absent", clock=lambda: value.data_selection_time
        )
    assert not (tmp_path / "absent").exists()
