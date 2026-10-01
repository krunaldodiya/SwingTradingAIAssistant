"""Plan 43 assumptions-only arithmetic and actual command boundary."""

import hashlib
import json
import os
import socket
import subprocess
import sys
from decimal import ROUND_DOWN, localcontext
from pathlib import Path
from unittest.mock import Mock

import pytest

from swing_trading_ai_assistant.market_data import cli
from swing_trading_ai_assistant.market_data import loss_scenario as loss


def request():
    return {
        "schema": "equity-loss-scenario-request@v1",
        "instrument": {"isin": "INE002A01018", "exchange": "NSE", "symbol": "EXAMPLE"},
        "side": "LONG",
        "currency": "INR",
        "bar_frequency": "1d",
        "holding_sessions": 5,
        "entry_price": "100.00",
        "stop_price": "95.00",
        "quantity": 10,
    }


def test_actual_cli_first_working_slice(tmp_path: Path):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(request()))
    path.chmod(0o600)
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "from swing_trading_ai_assistant.market_data.cli import main; raise SystemExit(main())",
            "loss-scenario",
            "--input-file",
            str(path),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    value = json.loads(result.stdout)
    assert value["amounts"] == {
        "entry_notional": "1000.00",
        "stop_proceeds": "950.00",
        "loss_per_share": "5.00",
        "gross_scenario_loss": "50.00",
    }
    assert value["risk_eligibility"] == "NOT_ASSESSED"


def calculate(value=None):
    return loss.calculate_loss_scenario(request() if value is None else value)


@pytest.mark.parametrize(
    "entry,stop,quantity,expected",
    [
        ("0.02", "0.01", 1, ["0.02", "0.01", "0.01", "0.01"]),
        ("10.01", "9.99", 99, ["990.99", "989.01", "0.02", "1.98"]),
        (
            "999999999.99",
            "0.01",
            1000000,
            ["999999999990000.00", "10000.00", "999999999.98", "999999999980000.00"],
        ),
    ],
)
def test_independent_amounts_and_decimal_context(entry, stop, quantity, expected):
    value = request() | {"entry_price": entry, "stop_price": stop, "quantity": quantity}
    ordinary = calculate(value)
    with localcontext() as context:
        context.prec = 1
        context.rounding = ROUND_DOWN
        result = calculate(value)
    assert result == ordinary
    assert list(result["amounts"].values()) == expected


@pytest.mark.parametrize(
    "key,values",
    [
        ("quantity", [0, 1000001, True, False, 1.0, "1", None, {}, []]),
        ("holding_sessions", [1, 21, True, 2.0, "2", None]),
        ("schema", ["v1", None, [], 1]),
        ("side", ["SHORT", "long", None]),
        ("currency", ["USD", None]),
        ("bar_frequency", ["1m", "1w", None]),
        (
            "entry_price",
            [
                "0.00",
                "-1.00",
                "+1.00",
                " 100.00",
                "100.00\n",
                "01.00",
                "1",
                "1.0",
                "1.000",
                "1e2",
                "1000000000.00",
                "9" * 10000,
                100.0,
                True,
                None,
                {},
                [],
            ],
        ),
        (
            "stop_price",
            [
                "100.00",
                "101.00",
                "0.00",
                "-1.00",
                "NaN",
                "Infinity",
                "1e999999",
                95,
                None,
            ],
        ),
    ],
)
def test_invalid_field_matrix(key, values):
    for value in values:
        data = request() | {key: value}
        with pytest.raises(loss.LossScenarioInputError):
            calculate(data)
        with pytest.raises(loss.LossScenarioInputError):
            loss.loss_scenario_request_from_json(json.dumps(data).encode())


@pytest.mark.parametrize(
    "key,value",
    [
        ("isin", "INE002A01019"),
        ("isin", "US0378331005"),
        ("isin", "ine002a01018"),
        ("isin", "INE002A0101A"),
        ("isin", "IN"),
        ("isin", None),
        ("symbol", "a"),
        ("symbol", ""),
        ("symbol", "A" * 33),
        ("symbol", "A/B"),
        ("symbol", "A\n"),
        ("exchange", "BSE"),
        ("symbol", {}),
    ],
)
def test_invalid_instrument(key, value):
    data = request()
    data["instrument"][key] = value
    with pytest.raises(loss.LossScenarioInputError):
        calculate(data)


@pytest.mark.parametrize("quantity,holding", [(1, 2), (1000000, 20)])
def test_inclusive_bounds(quantity, holding):
    data = request() | {"quantity": quantity, "holding_sessions": holding}
    data["instrument"]["symbol"] = "A" * 32
    assert calculate(data)["assumptions"] == data


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\xff",
        b"[]",
        b"null",
        b"true",
        b"NaN",
        b"Infinity",
        b"-Infinity",
        b"{}",
        b"{",
        b"0",
        b" " * 65537,
        b'{"schema":1,"schema":2}',
        b'{"instrument":{"isin":1,"isin":2}}',
        b"[" * 1500 + b"]" * 1500,
    ],
)
def test_malformed_json(raw):
    with pytest.raises(loss.LossScenarioInputError):
        loss.loss_scenario_request_from_json(raw)


def test_closed_schema_and_sdk_revalidation():
    for key in request():
        data = request()
        del data[key]
        with pytest.raises(loss.LossScenarioInputError):
            calculate(data)
    for value in [[], None, 1, request() | {"extra": 1}]:
        with pytest.raises(loss.LossScenarioInputError):
            loss.calculate_loss_scenario(value)
    data = request()
    data["instrument"]["extra"] = "ignored?"
    with pytest.raises(loss.LossScenarioInputError):
        calculate(data)
    parsed = loss.loss_scenario_request_from_json(json.dumps(request()).encode())
    parsed["quantity"] = True
    with pytest.raises(loss.LossScenarioInputError):
        calculate(parsed)
    assert (
        loss.loss_scenario_request_from_json(
            json.dumps(request()).encode()
            + b" " * (65536 - len(json.dumps(request()).encode()))
        )
        == request()
    )


def test_identity_complete_result_and_assumptions():
    data = request()
    original = calculate(data)
    reordered = dict(reversed(list(data.items())))
    assert calculate(reordered) == original
    assert (
        original["request_identity_sha256"]
        == hashlib.sha256(loss.canonical_bytes(data)).hexdigest()
    )
    without_identity = original.copy()
    digest = without_identity.pop("result_identity_sha256")
    assert digest == hashlib.sha256(loss.canonical_bytes(without_identity)).hexdigest()
    for key, value in [
        ("holding_sessions", 6),
        ("quantity", 11),
        ("stop_price", "94.99"),
    ]:
        changed = calculate(data | {key: value})
        assert changed["request_identity_sha256"] != original["request_identity_sha256"]
        assert changed["result_identity_sha256"] != digest
    data["instrument"]["symbol"] = "CHANGED"
    assert original["assumptions"]["instrument"]["symbol"] == "EXAMPLE"
    assert original["input_basis"] == "CALLER_SUPPLIED_ASSUMPTIONS"
    assert original["instrument_verification"] == "NOT_PERFORMED"
    assert original["market_evidence"] == "NOT_USED"
    assert original["costs_and_slippage"] == "EXCLUDED"
    assert "actual losses may exceed" in original["limitations"][0]
    assert "Fees, taxes and slippage" in original["limitations"][1]
    assert (
        "liquidity, event, gap, portfolio or trade suitability"
        in original["limitations"][2]
    )


def private_input(tmp_path, raw=None):
    path = tmp_path / "secret-owner-scenario.json"
    path.write_bytes(json.dumps(request()).encode() if raw is None else raw)
    path.chmod(0o600)
    return path


@pytest.mark.parametrize(
    "mode",
    [
        "missing",
        "relative",
        "public",
        "symlink",
        "parent_symlink",
        "hardlink",
        "directory",
        "fifo",
        "oversized",
        "malformed",
        "duplicate",
        "utf8",
    ],
)
def test_private_cli_rejection_without_effects(tmp_path, capsys, mode):  # noqa: C901 - explicit file adversaries
    path = private_input(tmp_path)
    if mode == "missing":
        path.unlink()
    elif mode == "relative":
        path = Path("relative.json")
    elif mode == "public":
        path.chmod(0o644)
    elif mode == "symlink":
        link = tmp_path / "link.json"
        link.symlink_to(path)
        path = link
    elif mode == "parent_symlink":
        link = tmp_path / "link-dir"
        link.symlink_to(tmp_path, target_is_directory=True)
        path = link / path.name
    elif mode == "hardlink":
        os.link(path, tmp_path / "hardlink.json")
    elif mode == "directory":
        path = tmp_path
    elif mode == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    elif mode == "oversized":
        path.write_bytes(b" " * 65537)
    elif mode == "malformed":
        path.write_bytes(b'{"secret":"never reveal","quantity":false}')
    elif mode == "duplicate":
        path.write_bytes(
            json.dumps(request()).replace('"LONG"', '"LONG", "side":"LONG"').encode()
        )
    elif mode == "utf8":
        path.write_bytes(b"\xff")
    service = Mock(side_effect=AssertionError("must not call service"))
    assert (
        cli.main(
            ["loss-scenario", "--input-file", str(path)],
            download_service=service,
            current_stock_research=service,
        )
        == 2
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "request_invalid\n"
    service.assert_not_called()


def test_runtime_substitution_is_sanitized(tmp_path, monkeypatch, capsys):
    path = private_input(tmp_path)
    before = path.read_bytes()
    monkeypatch.setattr(loss, "runtime_source_sha256", lambda *args: "0" * 64)
    assert cli.main(["loss-scenario", "--input-file", str(path)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "internal_error\n"
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "error", [RuntimeError("SECRET /private/path"), KeyboardInterrupt()]
)
def test_failure_or_interrupt_never_emits_partial_json(
    tmp_path, monkeypatch, capsys, error
):
    path = private_input(tmp_path)
    monkeypatch.setattr(cli, "calculate_loss_scenario", Mock(side_effect=error))
    if isinstance(error, KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            cli.main(["loss-scenario", "--input-file", str(path)])
    else:
        assert cli.main(["loss-scenario", "--input-file", str(path)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "" if isinstance(error, KeyboardInterrupt) else "internal_error\n"
    )


def test_output_boundary_and_no_emission(tmp_path, monkeypatch, capsys):
    # A JSON string object adds 9 bytes: {"x":""} plus LF.
    assert len(loss.loss_scenario_result_bytes({"x": "a" * (16384 - 9)})) == 16384
    with pytest.raises(ValueError, match="output bound"):
        loss.loss_scenario_result_bytes({"x": "a" * (16384 - 8)})
    path = private_input(tmp_path)
    monkeypatch.setattr(cli, "calculate_loss_scenario", lambda _: {"x": "a" * 16384})
    assert cli.main(["loss-scenario", "--input-file", str(path)]) == 2
    assert capsys.readouterr().out == ""


def test_retry_has_no_effects_or_credentials(tmp_path, monkeypatch, capsys):
    path = private_input(tmp_path)
    before = path.read_bytes()
    # Reject unexpected filesystem writes and sockets across the actual command.
    original_open = os.open

    def read_only_open(name, flags, *args, **kwargs):
        assert not flags & (os.O_CREAT | os.O_WRONLY | os.O_RDWR | os.O_TRUNC)
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", read_only_open)

    monkeypatch.setattr(
        socket, "socket", Mock(side_effect=AssertionError("network forbidden"))
    )
    for name in ("UPSTOX_ACCESS_TOKEN", "UPSTOX_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert cli.main(["loss-scenario", "--input-file", str(path)]) == 0
    first = capsys.readouterr()
    assert cli.main(["loss-scenario", "--input-file", str(path)]) == 0
    assert capsys.readouterr() == first
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]


def test_runtime_source_path_substitution(tmp_path, monkeypatch, capsys):
    path = private_input(tmp_path)
    monkeypatch.setattr(loss, "__file__", str(tmp_path / "loss_scenario.py"))
    assert cli.main(["loss-scenario", "--input-file", str(path)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "internal_error\n"


@pytest.mark.parametrize("raw", [None, "{}", bytearray(b"{}"), b'{"x":1e9999}'])
def test_parser_nonbytes_and_nonfinite(raw):
    with pytest.raises(loss.LossScenarioInputError):
        loss.loss_scenario_request_from_json(raw)


def test_nested_closed_identity_and_duplicate_keys():
    for instrument in [
        None,
        [],
        {},
        request()["instrument"] | {"provider": "invented"},
    ]:
        with pytest.raises(loss.LossScenarioInputError):
            calculate(request() | {"instrument": instrument})
    raw = json.dumps(request()).replace('"NSE"', '"NSE", "exchange": "NSE"').encode()
    with pytest.raises(loss.LossScenarioInputError):
        loss.loss_scenario_request_from_json(raw)
