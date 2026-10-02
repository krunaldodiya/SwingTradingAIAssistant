"""Plan 43 assumptions-only arithmetic and actual command boundary."""

import hashlib
import json
import os
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import ROUND_DOWN, localcontext
from pathlib import Path
from unittest.mock import Mock

import pytest

from swing_trading_ai_assistant.market_data import cli
from swing_trading_ai_assistant.market_data import loss_scenario as loss


def request(version="v1"):
    value = {
        "schema": f"equity-loss-scenario-request@{version}",
        "instrument": {"isin": "INE002A01018", "exchange": "NSE", "symbol": "EXAMPLE"},
        "side": "LONG",
        "currency": "INR",
        "bar_frequency": "1d",
        "holding_sessions": 5,
        "entry_price": "100.00",
        "stop_price": "95.00",
        "quantity": 10,
    }
    if version in ("v2", "v3"):
        value["round_trip_costs"] = "12.34"
    if version == "v3":
        value["assumed_exit_price"] = "93.00"
    return value


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


def calculator_for(version):
    return getattr(
        loss, "calculate_loss_scenario" + ("" if version == "v1" else "_" + version)
    )


def calculate(value=None, version="v1"):
    return calculator_for(version)(request(version) if value is None else value)


def parse(raw, version):
    parser = getattr(
        loss,
        "loss_scenario_request"
        + ("" if version == "v1" else "_" + version)
        + "_from_json",
    )
    return parser(raw)


def command(path, version):
    return ["loss-scenario", "--contract-version", version, "--input-file", str(path)]


def test_actual_cli_v2_first_working_slice(tmp_path):
    data = request() | {
        "schema": "equity-loss-scenario-request@v2",
        "round_trip_costs": "12.34",
    }
    path = private_input(tmp_path, json.dumps(data).encode())
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "from swing_trading_ai_assistant.market_data.cli import main; raise SystemExit(main())",
            "loss-scenario",
            "--contract-version",
            "v2",
            "--input-file",
            str(path),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    value = json.loads(result.stdout)
    assert value["schema"] == "equity-loss-scenario@v2"
    assert value["amounts"] == {
        "entry_notional": "1000.00",
        "stop_proceeds": "950.00",
        "loss_per_share": "5.00",
        "gross_scenario_loss": "50.00",
        "assumed_round_trip_costs": "12.34",
        "scenario_loss_including_assumed_costs": "62.34",
    }


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
@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_invalid_field_matrix(key, values, version):
    for value in values:
        data = request(version) | {key: value}
        with pytest.raises(loss.LossScenarioInputError):
            calculate(data, version)
        with pytest.raises(loss.LossScenarioInputError):
            parse(json.dumps(data).encode(), version)


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
@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_invalid_instrument(key, value, version):
    data = request(version)
    data["instrument"][key] = value
    with pytest.raises(loss.LossScenarioInputError):
        calculate(data, version)


@pytest.mark.parametrize("quantity,holding", [(1, 2), (1000000, 20)])
@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_inclusive_bounds(quantity, holding, version):
    data = request(version) | {"quantity": quantity, "holding_sessions": holding}
    data["instrument"]["symbol"] = "A" * 32
    assert calculate(data, version)["assumptions"] == data


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
@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_malformed_json(raw, version):
    with pytest.raises(loss.LossScenarioInputError):
        parse(raw, version)


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_closed_schema_and_sdk_revalidation(version):
    for key in request(version):
        data = request(version)
        del data[key]
        with pytest.raises(loss.LossScenarioInputError):
            calculate(data, version)
    for value in [[], None, 1, request(version) | {"extra": 1}]:
        with pytest.raises(loss.LossScenarioInputError):
            calculator_for(version)(value)
    data = request(version)
    data["instrument"]["extra"] = "ignored?"
    with pytest.raises(loss.LossScenarioInputError):
        calculate(data, version)
    parsed = parse(json.dumps(request(version)).encode(), version)
    parsed["quantity"] = True
    with pytest.raises(loss.LossScenarioInputError):
        calculate(parsed, version)
    assert parse(
        json.dumps(request(version)).encode()
        + b" " * (65536 - len(json.dumps(request(version)).encode())),
        version,
    ) == request(version)


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
@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_private_cli_rejection_without_effects(tmp_path, capsys, mode, version):  # noqa: C901 - explicit file adversaries
    path = private_input(tmp_path, json.dumps(request(version)).encode())
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
            json.dumps(request(version))
            .replace('"LONG"', '"LONG", "side":"LONG"')
            .encode()
        )
    elif mode == "utf8":
        path.write_bytes(b"\xff")
    service = Mock(side_effect=AssertionError("must not call service"))
    assert (
        cli.main(
            command(path, version),
            download_service=service,
            current_stock_research=service,
        )
        == 2
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "request_invalid\n"
    service.assert_not_called()


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_runtime_substitution_is_sanitized(tmp_path, monkeypatch, capsys, version):
    path = private_input(tmp_path, json.dumps(request(version)).encode())
    before = path.read_bytes()
    monkeypatch.setattr(loss, "runtime_source_sha256", lambda *args: "0" * 64)
    assert cli.main(command(path, version)) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "internal_error\n"
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "error", [RuntimeError("SECRET /private/path"), KeyboardInterrupt()]
)
@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_failure_or_interrupt_never_emits_partial_json(
    tmp_path, monkeypatch, capsys, error, version
):
    path = private_input(tmp_path, json.dumps(request(version)).encode())
    monkeypatch.setattr(
        cli,
        "calculate_loss_scenario" + ("" if version == "v1" else "_" + version),
        Mock(side_effect=error),
    )
    if isinstance(error, KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            cli.main(command(path, version))
    else:
        assert cli.main(command(path, version)) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "" if isinstance(error, KeyboardInterrupt) else "internal_error\n"
    )


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_output_boundary_and_no_emission(tmp_path, monkeypatch, capsys, version):
    # A JSON string object adds 9 bytes: {"x":""} plus LF.
    assert len(loss.loss_scenario_result_bytes({"x": "a" * (16384 - 9)})) == 16384
    with pytest.raises(ValueError, match="output bound"):
        loss.loss_scenario_result_bytes({"x": "a" * (16384 - 8)})
    path = private_input(tmp_path, json.dumps(request(version)).encode())
    monkeypatch.setattr(
        cli,
        "calculate_loss_scenario" + ("" if version == "v1" else "_" + version),
        lambda _: {"x": "a" * 16384},
    )
    assert cli.main(command(path, version)) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_retry_has_no_effects_or_credentials(tmp_path, monkeypatch, capsys, version):
    path = private_input(tmp_path, json.dumps(request(version)).encode())
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
    assert cli.main(command(path, version)) == 0
    first = capsys.readouterr()
    assert cli.main(command(path, version)) == 0
    assert capsys.readouterr() == first
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_runtime_source_path_substitution(tmp_path, monkeypatch, capsys, version):
    path = private_input(tmp_path, json.dumps(request(version)).encode())
    monkeypatch.setattr(loss, "__file__", str(tmp_path / "loss_scenario.py"))
    assert cli.main(command(path, version)) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "internal_error\n"


@pytest.mark.parametrize("raw", [None, "{}", bytearray(b"{}"), b'{"x":1e9999}'])
@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_parser_nonbytes_and_nonfinite(raw, version):
    with pytest.raises(loss.LossScenarioInputError):
        parse(raw, version)


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_nested_closed_identity_and_duplicate_keys(version):
    for instrument in [
        None,
        [],
        {},
        request(version)["instrument"] | {"provider": "invented"},
    ]:
        with pytest.raises(loss.LossScenarioInputError):
            calculate(request(version) | {"instrument": instrument}, version)
    raw = (
        json.dumps(request(version))
        .replace('"NSE"', '"NSE", "exchange": "NSE"')
        .encode()
    )
    with pytest.raises(loss.LossScenarioInputError):
        parse(raw, version)


@pytest.mark.parametrize(
    "entry,stop,quantity,costs,expected",
    [
        (
            "100.00",
            "95.00",
            10,
            "0.00",
            ["1000.00", "950.00", "5.00", "50.00", "0.00", "50.00"],
        ),
        ("0.02", "0.01", 1, "0.01", ["0.02", "0.01", "0.01", "0.01", "0.01", "0.02"]),
        (
            "10.01",
            "9.99",
            99,
            "0.03",
            ["990.99", "989.01", "0.02", "1.98", "0.03", "2.01"],
        ),
        (
            "0.02",
            "0.01",
            1,
            "999999999.99",
            ["0.02", "0.01", "0.01", "0.01", "999999999.99", "1000000000.00"],
        ),
        (
            "999999999.99",
            "0.01",
            1000000,
            "999999999.99",
            [
                "999999999990000.00",
                "10000.00",
                "999999999.98",
                "999999999980000.00",
                "999999999.99",
                "1000000999979999.99",
            ],
        ),
    ],
)
def test_v2_exact_independent_amounts(entry, stop, quantity, costs, expected):
    data = request("v2") | {
        "entry_price": entry,
        "stop_price": stop,
        "quantity": quantity,
        "round_trip_costs": costs,
    }
    original = loss.calculate_loss_scenario_v2(data)
    with localcontext() as context:
        context.prec = 1
        context.rounding = ROUND_DOWN
        assert loss.calculate_loss_scenario_v2(data) == original
    assert list(original["amounts"].values()) == expected


@pytest.mark.parametrize(
    "value",
    [
        "-0.01",
        "-0.00",
        "+0.01",
        "1000000000.00",
        "1e2",
        "1e999999",
        "01.00",
        "00.00",
        " 0.00",
        "0.00\n",
        "0",
        "0.0",
        "0.001",
        "NaN",
        "Infinity",
        "9" * 10000,
        0,
        0.0,
        True,
        False,
        None,
        {},
        [],
    ],
)
@pytest.mark.parametrize("version", ["v2", "v3"])
def test_invalid_costs_sdk_parser_and_cli(tmp_path, capsys, value, version):
    data = request(version) | {"round_trip_costs": value}
    with pytest.raises(loss.LossScenarioInputError):
        calculate(data, version)
    with pytest.raises(loss.LossScenarioInputError):
        parse(json.dumps(data).encode(), version)
    path = private_input(tmp_path, json.dumps(data).encode())
    assert cli.main(command(path, version)) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "request_invalid\n"


def test_v2_identities_labels_and_mutated_costs():
    data = request("v2")
    parsed = loss.loss_scenario_request_v2_from_json(json.dumps(data).encode())
    result = loss.calculate_loss_scenario_v2(parsed)
    assert result["amounts"]["scenario_loss_including_assumed_costs"] == "62.34"
    assert result == loss.calculate_loss_scenario_v2(dict(reversed(list(data.items()))))

    def independent_hash(value):
        raw = (
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    assert result["request_identity_sha256"] == independent_hash(data)
    without_identity = result.copy()
    digest = without_identity.pop("result_identity_sha256")
    assert digest == independent_hash(without_identity)
    observed = {
        name: hashlib.sha256(
            (Path(__file__).resolve().parents[2] / name).read_bytes()
        ).hexdigest()
        for name in loss.LOSS_SCENARIO_RUNTIME_SOURCE_SHA256_V1
    }
    assert result["runtime_code_identity_sha256"] == independent_hash(observed)
    assert result["calculation_version"] == "integer-paise-long-loss-with-costs@v2"
    for key, expected in {
        "input_basis": "CALLER_SUPPLIED_ASSUMPTIONS",
        "instrument_verification": "NOT_PERFORMED",
        "market_evidence": "NOT_USED",
        "risk_eligibility": "NOT_ASSESSED",
        "costs_basis": "CALLER_SUPPLIED_AGGREGATE",
        "cost_completeness": "NOT_VERIFIED",
        "slippage": "EXCLUDED",
        "currency": "INR",
    }.items():
        assert result[key] == expected
    assert "costs_and_slippage" not in result
    assert result["limitations"] == [
        "Stop execution is not guaranteed; actual losses may exceed this scenario.",
        "No fee or tax schedule was calculated or verified.",
        "Costs are caller assumptions; their completeness is not verified.",
        "Slippage is excluded.",
        "No liquidity, event, gap, portfolio or trade suitability assessment was performed.",
    ]
    for key, value in [
        ("entry_price", "100.01"),
        ("stop_price", "94.99"),
        ("quantity", 11),
        ("holding_sessions", 6),
        ("round_trip_costs", "12.35"),
    ]:
        changed = loss.calculate_loss_scenario_v2(data | {key: value})
        assert changed["request_identity_sha256"] != result["request_identity_sha256"]
        assert changed["result_identity_sha256"] != digest
    parsed["round_trip_costs"] = False
    with pytest.raises(loss.LossScenarioInputError):
        loss.calculate_loss_scenario_v2(parsed)
    assert result["assumptions"]["round_trip_costs"] == "12.34"


@pytest.mark.parametrize(
    "raw",
    [
        b'{"secret":"PRIVATE-MARKER"}',
        b"\xff",
        json.dumps(request("v2") | {"round_trip_costs": "PRIVATE-MARKER"}).encode(),
    ],
)
def test_v2_invalid_precedes_runtime_corruption(tmp_path, monkeypatch, capsys, raw):
    path = private_input(tmp_path, raw)
    runtime = Mock(side_effect=RuntimeError("PRIVATE-MARKER /private/path"))
    calculator = Mock(side_effect=AssertionError("must validate first"))
    monkeypatch.setattr(loss, "loss_scenario_runtime_identity", runtime)
    monkeypatch.setattr(cli, "calculate_loss_scenario_v2", calculator)
    assert cli.main(command(path, "v2")) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "request_invalid\n"
    runtime.assert_not_called()
    calculator.assert_not_called()
    with pytest.raises(loss.LossScenarioInputError):
        loss.calculate_loss_scenario_v2(request("v2") | {"round_trip_costs": False})
    runtime.assert_not_called()


def test_v2_version_isolation_and_v1_rollback(tmp_path, monkeypatch, capsys):
    for version in ("v1", "v2"):
        other = "v1" if version == "v2" else "v2"
        with pytest.raises(loss.LossScenarioInputError):
            parse(json.dumps(request(other)).encode(), version)
        with pytest.raises(loss.LossScenarioInputError):
            calculate(request(other), version)
    path = private_input(tmp_path)
    assert cli.main(["loss-scenario", "--input-file", str(path)]) == 0
    default = capsys.readouterr()
    assert cli.main(command(path, "v1")) == 0
    assert capsys.readouterr() == default
    result = json.loads(default.out)
    assert result["schema"] == "equity-loss-scenario@v1"
    assert result["costs_and_slippage"] == "EXCLUDED"
    assert result["amounts"]["gross_scenario_loss"] == "50.00"
    assert "assumed_round_trip_costs" not in result["amounts"]
    reader = Mock(side_effect=AssertionError("must reject version before read"))
    monkeypatch.setattr(cli, "_read_current_regime_input", reader)
    with pytest.raises(SystemExit) as error:
        cli.main(command(path, "v4"))
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "request_invalid\n"
    reader.assert_not_called()


@pytest.mark.parametrize("version", ["v2", "v3"])
def test_concurrent_actual_commands_are_identical_and_effect_free(tmp_path, version):
    path = private_input(tmp_path, json.dumps(request(version)).encode())
    before = path.read_bytes()

    def invoke(_):
        return subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-c",
                "from swing_trading_ai_assistant.market_data.cli import main; raise SystemExit(main())",
                *command(path, version),
            ],
            capture_output=True,
            check=False,
        )

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(invoke, range(3)))
    assert all(result.returncode == 0 and result.stderr == b"" for result in results)
    assert len({result.stdout for result in results}) == 1
    assert (
        json.loads(results[0].stdout)["amounts"][
            "planned_loss_including_assumed_costs"
            if version == "v3"
            else "scenario_loss_including_assumed_costs"
        ]
        == "62.34"
    )
    assert path.read_bytes() == before
    assert sorted(item.name for item in tmp_path.iterdir()) == [path.name]


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff",
        b"{",
        b'{"private-marker":"NEVER-ECHO"}',
        json.dumps(request("v2"))
        .replace('"12.34"', '"12.34", "round_trip_costs":"0.00"')
        .encode(),
        json.dumps(request("v2")).replace('"NSE"', '"NSE", "exchange":"NSE"').encode(),
        json.dumps(request("v1")).encode(),
    ],
)
def test_actual_v2_cli_rejects_invalid_input_without_leaks(tmp_path, raw):
    path = private_input(tmp_path, raw)
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "from swing_trading_ai_assistant.market_data.cli import main; raise SystemExit(main())",
            *command(path, "v2"),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == b"" and result.stderr == b"request_invalid\n"
    assert path.read_bytes() == raw


@pytest.mark.parametrize("version", ["v2", "v3"])
def test_interruption_then_explicit_retry_preserves_input(
    tmp_path, monkeypatch, capsys, version
):
    path = private_input(tmp_path, json.dumps(request(version)).encode())
    before = path.read_bytes()
    with monkeypatch.context() as interrupted:
        interrupted.setattr(
            cli, "loss_scenario_result_bytes", Mock(side_effect=KeyboardInterrupt())
        )
        with pytest.raises(KeyboardInterrupt):
            cli.main(command(path, version))
    output = capsys.readouterr()
    assert output.out == "" and output.err == ""
    assert path.read_bytes() == before
    assert cli.main(command(path, version)) == 0
    first = capsys.readouterr()
    assert cli.main(command(path, version)) == 0
    assert capsys.readouterr() == first
    assert (
        json.loads(first.out)["amounts"][
            "planned_loss_including_assumed_costs"
            if version == "v3"
            else "scenario_loss_including_assumed_costs"
        ]
        == "62.34"
    )
    assert path.read_bytes() == before
    assert sorted(item.name for item in tmp_path.iterdir()) == [path.name]


def test_actual_cli_v3_first_working_slice(tmp_path):
    path = private_input(tmp_path, json.dumps(request("v3")).encode())
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "from swing_trading_ai_assistant.market_data.cli import main; raise SystemExit(main())",
            *command(path, "v3"),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    value = json.loads(result.stdout)
    assert value == calculate(version="v3")
    assert value["schema"] == "equity-loss-scenario@v3"
    assert value["amounts"] == {
        "entry_notional": "1000.00",
        "planned_stop_proceeds": "950.00",
        "planned_loss_per_share": "5.00",
        "planned_gross_loss": "50.00",
        "assumed_exit_proceeds": "930.00",
        "assumed_exit_loss_per_share": "7.00",
        "assumed_exit_gross_loss": "70.00",
        "assumed_round_trip_costs": "12.34",
        "planned_loss_including_assumed_costs": "62.34",
        "assumed_exit_loss_including_assumed_costs": "82.34",
        "additional_loss_from_assumed_exit": "20.00",
    }


@pytest.mark.parametrize(
    "entry,stop,exit_price,quantity,costs,planned,assumed,extra",
    [
        ("0.03", "0.02", "0.01", 1, "0.00", "0.01", "0.02", "0.01"),
        ("10.01", "9.99", "9.98", 99, "0.01", "1.99", "2.98", "0.99"),
        (
            "0.03",
            "0.02",
            "0.01",
            1,
            "999999999.99",
            "1000000000.00",
            "1000000000.01",
            "0.01",
        ),
        (
            "999999999.99",
            "999999999.98",
            "0.01",
            1000000,
            "999999999.99",
            "1000009999.99",
            "1000000999979999.99",
            "999999999970000.00",
        ),
    ],
)
def test_v3_exact_boundary_comparison(
    entry, stop, exit_price, quantity, costs, planned, assumed, extra
):
    data = request("v3") | {
        "entry_price": entry,
        "stop_price": stop,
        "assumed_exit_price": exit_price,
        "quantity": quantity,
        "round_trip_costs": costs,
    }
    ordinary = calculate(data, "v3")
    with localcontext() as context:
        context.prec = 1
        context.rounding = ROUND_DOWN
        assert calculate(data, "v3") == ordinary
    amounts = ordinary["amounts"]
    assert amounts["planned_loss_including_assumed_costs"] == planned
    assert amounts["assumed_exit_loss_including_assumed_costs"] == assumed
    assert amounts["additional_loss_from_assumed_exit"] == extra
    assert amounts["assumed_round_trip_costs"] == costs
    assert (
        calculate(data | {"round_trip_costs": "0.00"}, "v3")["amounts"][
            "additional_loss_from_assumed_exit"
        ]
        == extra
    )


@pytest.mark.parametrize(
    "value",
    [
        "0.00",
        "95.00",
        "95.01",
        "100.00",
        "1000000000.00",
        "-1.00",
        "+1.00",
        " 93.00",
        "93.00\n",
        "093.00",
        "93.0",
        "1e0",
        "9" * 10000,
        93.0,
        True,
        False,
        None,
        {},
        [],
    ],
)
def test_v3_invalid_assumed_exit_at_all_boundaries(
    tmp_path, monkeypatch, capsys, value
):
    data = request("v3") | {"assumed_exit_price": value}
    runtime = Mock(side_effect=RuntimeError("PRIVATE-MARKER /private/path"))
    monkeypatch.setattr(loss, "loss_scenario_runtime_identity", runtime)
    with pytest.raises(loss.LossScenarioInputError):
        calculate(data, "v3")
    with pytest.raises(loss.LossScenarioInputError):
        parse(json.dumps(data).encode(), "v3")
    path = private_input(tmp_path, json.dumps(data).encode())
    assert cli.main(command(path, "v3")) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "request_invalid\n"
    runtime.assert_not_called()


def test_v3_complete_identities_labels_and_mutations():
    data = request("v3")
    parsed = parse(json.dumps(data).encode(), "v3")
    result = calculate(parsed, "v3")
    assert result == calculate(dict(reversed(list(data.items()))), "v3")

    def digest(value):
        return hashlib.sha256(
            (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        ).hexdigest()

    assert result["request_identity_sha256"] == digest(data)
    without = result.copy()
    identity = without.pop("result_identity_sha256")
    assert identity == digest(without)
    observed = {
        name: hashlib.sha256(
            (Path(__file__).resolve().parents[2] / name).read_bytes()
        ).hexdigest()
        for name in loss.LOSS_SCENARIO_RUNTIME_SOURCE_SHA256_V1
    }
    assert result["runtime_code_identity_sha256"] == digest(observed)
    for key, expected in {
        "input_basis": "CALLER_SUPPLIED_ASSUMPTIONS",
        "instrument_verification": "NOT_PERFORMED",
        "market_evidence": "NOT_USED",
        "risk_eligibility": "NOT_ASSESSED",
        "costs_basis": "CALLER_SUPPLIED_AGGREGATE",
        "cost_completeness": "NOT_VERIFIED",
        "comparison_costs": "SAME_ASSUMED_AGGREGATE",
        "assumed_exit_basis": "CALLER_SUPPLIED_PRICE",
        "execution_model": "NOT_USED",
        "calculation_version": "integer-paise-long-loss-assumed-exit@v3",
    }.items():
        assert result[key] == expected
    assert "slippage" not in result and "costs_and_slippage" not in result
    assert result["limitations"] == [
        "Stop execution is not guaranteed; actual losses may exceed either scenario.",
        "The assumed exit price is a caller assumption, not a forecast or maximum-loss bound.",
        "No fee or tax schedule was calculated or verified.",
        "Costs are caller assumptions; their completeness is not verified.",
        "The same aggregate whole-position costs are assumed for both scenarios; execution-price movement is separate from costs.",
        "No empirical gap or slippage model was used.",
        "No liquidity, event, gap, portfolio or trade suitability assessment was performed.",
    ]
    changes = {
        "entry_price": "100.01",
        "stop_price": "94.99",
        "assumed_exit_price": "92.99",
        "quantity": 11,
        "holding_sessions": 6,
        "round_trip_costs": "12.35",
        "instrument": data["instrument"] | {"symbol": "OTHER"},
    }
    for key, value in changes.items():
        changed = calculate(data | {key: value}, "v3")
        assert changed["request_identity_sha256"] != result["request_identity_sha256"]
        assert changed["result_identity_sha256"] != identity
    parsed["assumed_exit_price"] = "95.00"
    with pytest.raises(loss.LossScenarioInputError):
        calculate(parsed, "v3")
    assert result["assumptions"] == data


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_all_versions_reject_other_requests(version):
    for other in {"v1", "v2", "v3"} - {version}:
        with pytest.raises(loss.LossScenarioInputError):
            parse(json.dumps(request(other)).encode(), version)
        with pytest.raises(loss.LossScenarioInputError):
            calculate(request(other), version)


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff",
        b"{",
        b'{"private-marker":"NEVER-ECHO"}',
        json.dumps(request("v3"))
        .replace('"93.00"', '"93.00", "assumed_exit_price":"92.00"')
        .encode(),
        json.dumps(request("v3")).replace('"NSE"', '"NSE", "exchange":"NSE"').encode(),
        json.dumps(request("v2")).encode(),
    ],
)
def test_actual_v3_invalid_input_precedes_corruption_without_leaks(
    tmp_path, monkeypatch, capsys, raw
):
    path = private_input(tmp_path, raw)
    runtime = Mock(side_effect=RuntimeError("NEVER-ECHO /private/path"))
    monkeypatch.setattr(loss, "loss_scenario_runtime_identity", runtime)
    assert cli.main(command(path, "v3")) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "request_invalid\n"
    runtime.assert_not_called()
    completed = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "from swing_trading_ai_assistant.market_data.cli import main; raise SystemExit(main())",
            *command(path, "v3"),
        ],
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2
    assert completed.stdout == b"" and completed.stderr == b"request_invalid\n"
    assert path.read_bytes() == raw
