"""No partial output or writes at Volume request, clock and storage boundaries."""

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

import swing_trading_ai_assistant.market_data.cli as cli
import swing_trading_ai_assistant.volume_analysis.current as arithmetic
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextMemberV1,
)
from swing_trading_ai_assistant.volume_analysis import (
    VolumeRequest,
    research_current_volume,
)


def request():
    selected = datetime(2026, 9, 15, 9, tzinfo=UTC)
    return VolumeRequest(
        selected,
        selected + timedelta(minutes=20),
        "a" * 64,
        (
            CurrentPriceContextMemberV1(
                "INE467B01029",
                "NSE",
                "EQUITY",
                "EQ",
                "TCS",
                selected.date(),
                selected.date(),
            ),
        ),
    )


@pytest.mark.parametrize(
    "unsafe", ["public", "symlink", "hardlink", "directory", "fifo", "oversize"]
)
def test_unsafe_input_is_rejected_before_output_or_root_creation(
    tmp_path, capsys, unsafe
):
    data = request()
    root = tmp_path / "absent"
    path = tmp_path / "request.json"
    if unsafe == "directory":
        path.mkdir()
    elif unsafe == "fifo":
        os.mkfifo(path, 0o600)
    else:
        path.write_bytes(data.canonical_bytes if unsafe != "oversize" else b" " * 65537)
        path.chmod(0o644 if unsafe == "public" else 0o600)
        if unsafe in {"symlink", "hardlink"}:
            target = tmp_path / "other.json"
            path.rename(target)
            if unsafe == "symlink":
                path.symlink_to(target)
            else:
                os.link(target, path)
    status = main(
        [
            "volume-context-current",
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
    assert output.err in {"internal_error\n", "request_invalid\n"}
    assert not root.exists()


@pytest.mark.parametrize(
    "case", ["before", "deadline", "regression", "rollover", "naive"]
)
def test_clock_failure_stops_without_files(tmp_path, case):
    data = request()
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    values = {
        "before": [data.data_selection_time - timedelta(microseconds=1)],
        "deadline": [data.admission_deadline],
        "regression": [
            data.data_selection_time + timedelta(seconds=2),
            data.data_selection_time,
        ],
        "rollover": [
            data.data_selection_time,
            datetime(2026, 9, 15, 18, 30, tzinfo=UTC),
        ],
        "naive": [data.data_selection_time.replace(tzinfo=None)],
    }[case]

    def clock():
        return values.pop(0) if len(values) > 1 else values[0]

    with pytest.raises((ValueError, RuntimeError)):
        research_current_volume(data, root, clock=clock)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("case", ["public", "symlink", "file"])
def test_unsafe_root_is_terminal(tmp_path, case):
    data = request()
    root = tmp_path / "root"
    if case == "file":
        root.write_text("not a directory")
    elif case == "symlink":
        target = tmp_path / "target"
        target.mkdir(mode=0o700)
        root.symlink_to(target)
    else:
        root.mkdir(mode=0o755)
    with pytest.raises((ValueError, RuntimeError, OSError)):
        research_current_volume(data, root, clock=lambda: data.data_selection_time)


def test_absent_root_cli_outputs_typed_nonready_and_does_not_create_it(
    tmp_path, capsys
):
    data = request()
    path = tmp_path / "request.json"
    path.write_bytes(data.canonical_bytes)
    path.chmod(0o600)
    root = tmp_path / "absent"

    class Clock:
        def now(self):
            return data.data_selection_time

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
    output = capsys.readouterr()
    assert status == 1 and output.err == ""
    assert json.loads(output.out)["state"] == "NONREADY"
    assert not root.exists()


def test_runtime_source_origin_substitution_is_rejected(tmp_path, monkeypatch):
    data = request()
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    copied = tmp_path / "current.py"
    copied.write_text("# unrelated runtime")
    monkeypatch.setattr(arithmetic, "__file__", str(copied))
    with pytest.raises(ValueError, match="runtime source identity invalid"):
        research_current_volume(data, root, clock=lambda: data.data_selection_time)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("case", ["deadline", "rollover", "regression", "naive"])
def test_cli_checks_clock_after_serialization(tmp_path, monkeypatch, capsys, case):
    data = request()
    path = tmp_path / "request.json"
    path.write_bytes(data.canonical_bytes)
    path.chmod(0o600)
    current = data.data_selection_time + timedelta(seconds=1)
    serialize = cli.volume_json

    def delayed(value):
        nonlocal current
        output = serialize(value)
        current = {
            "deadline": data.admission_deadline,
            "rollover": datetime(2026, 9, 15, 18, 30, tzinfo=UTC),
            "regression": data.data_selection_time,
            "naive": data.data_selection_time.replace(tzinfo=None),
        }[case]
        return output

    class Clock:
        def now(self):
            return current

    monkeypatch.setattr(cli, "volume_json", delayed)
    status = main(
        [
            "volume-context-current",
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
    assert status == 2
    assert output.out == ""
    assert output.err == "internal_error\n"
