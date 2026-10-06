"""Full typed admission and atomic evidence-CLI effects for the new six-fact boundary."""

import copy
import importlib
from datetime import timedelta
from decimal import Decimal

import pytest
import test_setup_inclusion_consumer_contract_v4 as cases
from test_setup_inclusion_consumer_contract_v4 import PREFIX, _bundle, _cli, _response


@pytest.fixture(scope="module")
def admission_cases(tmp_path_factory):
    return cases.admission_cases.__wrapped__(tmp_path_factory)


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    return cases.pair.__wrapped__(tmp_path_factory)


@pytest.mark.parametrize("side", ["previous", "current"])
@pytest.mark.parametrize(
    "mutation",
    [
        "runtime",
        "diagnostics",
        "knowledge",
        "mapping",
        "packet",
        "source",
        "bar",
        "bar_identity",
        "count",
        "anchor_missing",
        "anchor_duplicate",
        "broken_level",
        "event_duplicate",
    ],
)
def test_complete_admission_terminal_before_unknown(admission_cases, side, mutation):
    value = copy.copy(admission_cases["baseline"])
    unknown = admission_cases["unknown"]
    feature = value.packet.members[0].feature("MARKET_STRUCTURE")
    calculation = feature.fact.calculation
    target, field, changed = {
        "runtime": (value, "runtime_code_identity_sha256", "0" * 64),
        "diagnostics": (value, "code", "PRIVATE_TOKEN_PATH"),
        "knowledge": (
            value,
            "evidence_known_at",
            value.acquisition_deadline + timedelta(minutes=1),
        ),
        "mapping": (
            value.packet.mapping_projection.members[0],
            "mapping_version",
            "forged",
        ),
        "packet": (value.packet, "result_identity_sha256", "0" * 64),
        "source": (
            value.packet.source("MARKET_STRUCTURE"),
            "admitted_sessions",
            tuple(reversed(value.packet.source("MARKET_STRUCTURE").admitted_sessions)),
        ),
        "bar": (feature.source_bars[-1], "close", Decimal("NaN")),
        "bar_identity": (
            feature.source_bars[-1],
            "source_row_identity_sha256",
            "0" * 64,
        ),
        "count": (
            feature,
            "source_bars",
            feature.source_bars + (feature.source_bars[-1],),
        ),
        "anchor_missing": (calculation, "pivots", ()),
        "anchor_duplicate": (
            calculation,
            "pivots",
            calculation.pivots + calculation.pivots,
        ),
        "broken_level": (calculation.events[-1], "broken_level", Decimal(1)),
        "event_duplicate": (
            calculation,
            "events",
            calculation.events + calculation.events,
        ),
    }[mutation]
    assert _bundle(value, value)["level_range"]["status"] == "REPLAY"
    original = getattr(target, field)
    try:
        object.__setattr__(target, field, changed)
        with pytest.raises((ValueError, TypeError)):
            _bundle(value, unknown) if side == "previous" else _bundle(unknown, value)
    finally:
        object.__setattr__(target, field, original)


def test_authored_component_and_bundle_are_not_observations(pair):
    evidence = _bundle(*pair)
    for authored in (evidence, evidence["level_range"], None):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            _bundle(authored, pair[1])


@pytest.mark.parametrize("stage", ["first", "second", "compose", "serialize"])
@pytest.mark.parametrize("failure", [ValueError, KeyboardInterrupt])
def test_evidence_cli_atomic_interruption_and_explicit_retry(
    tmp_path, pair, capsys, monkeypatch, stage, failure
):
    cli = importlib.import_module(PREFIX + "setup_evidence_v4_cli")
    calls = []

    def failed(*args):
        raise failure("PRIVATE_TOKEN_PATH")

    def service(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == (1 if stage == "first" else 2) and stage in (
            "first",
            "second",
        ):
            return failed()
        return pair[len(calls) - 1]

    with monkeypatch.context() as patch:
        if stage == "compose":
            patch.setattr(cli, "assemble_setup_evidence_v4", failed)
        elif stage == "serialize":
            patch.setattr(cli, "canonical_comparison_bytes", failed)
        assert (
            _cli(tmp_path, *pair, None, service=service, command="setup-evidence-v4")
            == 2
        )
    result = capsys.readouterr()
    assert result.out == "" and result.err == "setup_evidence_failed\n"
    assert len(calls) == (1 if stage == "first" else 2)
    assert _cli(tmp_path, *pair, None, command="setup-evidence-v4") == 0
    assert not capsys.readouterr().err


@pytest.mark.parametrize("stage", ["compose", "serialize"])
def test_checker_interruptions_do_not_emit_partial_evidence(
    tmp_path, pair, capsys, monkeypatch, stage
):
    sdk = importlib.import_module(PREFIX + "setup_interpretation_v4")
    cli = importlib.import_module(PREFIX + "setup_interpretation_v4_cli")
    response = _response(_bundle(*pair))

    def failed(*args):
        raise KeyboardInterrupt("PRIVATE_TOKEN_PATH")

    with monkeypatch.context() as patch:
        if stage == "compose":
            patch.setattr(sdk, "assemble_setup_evidence_v4", failed)
        else:
            patch.setattr(cli, "canonical_comparison_bytes", failed)
        assert _cli(tmp_path, *pair, response) == 2
    result = capsys.readouterr()
    assert result.out == "" and result.err == "setup_interpretation_failed\n"
    assert _cli(tmp_path, *pair, response) == 0
    assert not capsys.readouterr().err
