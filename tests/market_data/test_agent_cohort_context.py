"""Sprint25: independently retained cohort facts beside current stock research."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
import test_agent_cohort_mappings as mapping_fixture

from swing_trading_ai_assistant.market_data import cli


def _args(root, version="v4"):
    return [
        "research-run-current",
        "--symbol",
        "PNB",
        "--storage-root",
        str(root),
        "--output",
        "json",
        "--contract-version",
        version,
    ]


def test_cli_accepts_explicit_v4_cohort(tmp_path):
    args = cli._parse_cli_args(
        _args(tmp_path)
        + [
            "--context-symbol",
            "TCS",
            "--context-symbol",
            "PNB",
            "--context-purpose",
            "My explicit research comparison group",
        ]
    )
    assert args.contract_version == "v4"
    assert args.context_symbol == ["TCS", "PNB"]
    assert args.context_purpose == "My explicit research comparison group"


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_old_contract_rejects_context_before_effects(tmp_path, capsys, version):
    def forbidden(*args, **kwargs):
        pytest.fail("price acquisition before input rejection")

    code = cli.main(
        _args(tmp_path, version)
        + [
            "--context-symbol",
            "TCS",
            "--context-symbol",
            "PNB",
            "--context-purpose",
            "Comparison",
        ],
        current_stock_research_v2=forbidden,
    )
    assert code == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("option", ["--context-purpose", "--context-mappings-file"])
@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_each_context_option_rejected_by_old_versions(
    tmp_path, capsys, option, version
):
    def forbidden(*args, **kwargs):
        pytest.fail("acquisition before rejection")

    assert (
        cli.main(
            _args(tmp_path, version) + [option, "unused"],
            current_stock_research_v2=forbidden,
        )
        == 2
    )
    assert capsys.readouterr().out == ""


def _context_args(root):
    return _args(root) + [
        "--context-symbol",
        "SYM000",
        "--context-symbol",
        "SYM001",
        "--context-purpose",
        "Explicit comparison",
    ]


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "relative",
        "public",
        "symlink",
        "hardlink",
        "directory",
        "malformed",
        "oversize",
    ],
)
def test_bad_mapping_file_rejected_before_runner(tmp_path, monkeypatch, capsys, kind):
    path = tmp_path / "cohort.json"
    if kind not in {"missing", "directory"}:
        path.write_bytes(b"{}")
        path.chmod(0o600)
    if kind == "relative":
        path = type(path)("cohort.json")
    elif kind == "public":
        path.chmod(0o644)
    elif kind == "symlink":
        target = tmp_path / "link.json"
        target.symlink_to(path)
        path = target
    elif kind == "hardlink":
        (tmp_path / "linked.json").hardlink_to(path)
    elif kind == "directory":
        path.mkdir()
    elif kind == "oversize":
        path.write_bytes(b" " * 65537)

    def forbidden(*args, **kwargs):
        pytest.fail("runner reached invalid file")

    monkeypatch.setattr(cli, "run_agent_cohort_research_current", forbidden)
    assert (
        cli.main(_context_args(tmp_path) + ["--context-mappings-file", str(path)]) == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "request_invalid\n"


@pytest.mark.parametrize("supplied", [False, True])
def test_cli_passes_parsed_mapping_authority_to_runner(
    tmp_path, monkeypatch, capsys, supplied
):
    args = _context_args(tmp_path)
    if supplied:
        path = tmp_path / "cohort.json"
        path.write_text(json.dumps(mapping_fixture._document()))
        path.chmod(0o600)
        args += ["--context-mappings-file", str(path)]
    calls = []

    def runner(symbols, root, **kwargs):
        calls.append((symbols, root, kwargs))
        return {"members": [{"features": {"price": {"fact": 1}}}]}

    monkeypatch.setattr(cli, "run_agent_cohort_research_current", runner)
    assert cli.main(args) == 0
    assert len(calls) == 1
    symbols, root, options = calls[0]
    assert symbols == ("PNB",)
    assert root == tmp_path
    assert options["context_symbols"] == ("SYM000", "SYM001")
    assert (options["mappings"] is not None) == supplied
    assert json.loads(capsys.readouterr().out)["members"]


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("private provider body /private/path"), KeyboardInterrupt()],
)
def test_fatal_runner_failure_never_emits_partial_json(
    tmp_path, monkeypatch, capsys, failure
):
    def runner(*args, **kwargs):
        raise failure

    monkeypatch.setattr(cli, "run_agent_cohort_research_current", runner)
    if isinstance(failure, KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            cli.main(_context_args(tmp_path))
    else:
        assert cli.main(_context_args(tmp_path)) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "" if isinstance(failure, KeyboardInterrupt) else "internal_error\n"
    )


@pytest.mark.parametrize("fact, expected", [(None, 1), (1, 0)])
@pytest.mark.parametrize("availability", ["OBSERVED", "INSUFFICIENT_EVIDENCE"])
def test_context_availability_does_not_change_price_exit(
    tmp_path, monkeypatch, capsys, fact, expected, availability
):
    def runner(*args, **kwargs):
        return {
            "members": [{"features": {"price": {"fact": fact}}}],
            "cohort_context": {"market_regime": {"availability": availability}},
        }

    monkeypatch.setattr(cli, "run_agent_cohort_research_current", runner)
    assert cli.main(_context_args(tmp_path)) == expected
    assert (
        json.loads(capsys.readouterr().out)["cohort_context"]["market_regime"][
            "availability"
        ]
        == availability
    )


@pytest.mark.parametrize("kind", ["malformed_file", "missing_purpose", "old_version"])
def test_actual_module_cli_rejects_bad_input_without_json(tmp_path, kind):
    args = _context_args(tmp_path)
    if kind == "malformed_file":
        path = tmp_path / "invalid.json"
        path.write_bytes(b"{}")
        path.chmod(0o600)
        args += ["--context-mappings-file", str(path)]
    elif kind == "missing_purpose":
        args = args[:-2]
    else:
        args[args.index("v4")] = "v3"
    # Fixed module and synthetic local arguments; no shell or user input.
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "swing_trading_ai_assistant.market_data.cli", *args],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "request_invalid\n"
