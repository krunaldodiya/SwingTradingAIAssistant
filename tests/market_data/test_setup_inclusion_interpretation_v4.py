"""Six-fact consumer binding, tested with actual admitted producer observations."""

from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import json

import pytest
import test_setup_level_range_inclusion as producer
from test_setup_observation_comparison import _args
from test_setup_range_interpretation_v3 import _response as legacy_response

from swing_trading_ai_assistant.research_comparison.setup_evidence_v3 import (
    assemble_setup_evidence_v3,
)
from swing_trading_ai_assistant.research_comparison.setup_level_range_inclusion import (
    observe_setup_level_range_inclusion_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (
    canonical_comparison_bytes,
)

PREFIX = "swing_trading_ai_assistant.research_comparison."


@pytest.fixture(scope="module")
def chronological(tmp_path_factory):
    # This existing fixture injects an explicit fixed test clock into every
    # actual producer call; no demonstration module clock or audit state is used.
    return producer.chronological.__wrapped__(tmp_path_factory)


def _bundle(previous, current):
    path = PREFIX + "setup_evidence_v4"
    version = "v4" if importlib.util.find_spec(path) else "v3"
    return getattr(
        importlib.import_module(PREFIX + "setup_evidence_" + version),
        "assemble_setup_evidence_" + version,
    )(previous, current)


def _response(evidence, disposition="RESEARCH_ONLY"):
    response = legacy_response(evidence, disposition)
    response["schema"] = "external-setup-interpretation-request@v4"
    response["facts"]["level_range_inclusion"] = {
        key: evidence["level_range_inclusion"][key]
        for key in (
            "result_identity_sha256",
            "status",
            "inclusion_observed",
            "first_inclusion",
        )
    }
    return response


def _api():
    return importlib.import_module(PREFIX + "setup_interpretation_v4")


def _check(previous, current, response):
    return _api().check_setup_interpretation_v4(previous, current, response)


def _cli(tmp_path, previous, current, response, *, service=None, evidence=False):
    command = "setup-evidence-v4" if evidence else "setup-interpretation-v4"
    args = _args(tmp_path)
    args[0] = command
    for side, observed in (("previous", previous), ("current", current)):
        args[args.index("--" + side + "-selection-time") + 1] = (
            observed.data_selection_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )
    if not evidence:
        path = tmp_path / "response.json"
        path.write_bytes(json.dumps(response).encode())
        path.chmod(0o600)
        args += ["--interpretation-file", str(path)]
    if service is None:
        values = iter((previous, current))

        def service(*args, **kwargs):
            return next(values)

    module = "setup_evidence_v4_cli" if evidence else "setup_interpretation_v4_cli"
    return importlib.import_module(PREFIX + module).main(
        args, observation_service=service
    )


@pytest.mark.parametrize("name,expected", [("earlier", True), ("none", False)])
def test_actual_six_fact_pair_and_both_clis(
    chronological, tmp_path, capsys, name, expected
):
    previous, current = chronological["previous"], chronological[name]
    evidence = _bundle(previous, current)
    # Existing v3 is a usable five-fact path, but cannot carry this sixth fact.
    assert evidence.get("level_range_inclusion") is not None
    inclusion = evidence["level_range_inclusion"]
    assert inclusion["inclusion_observed"] is expected
    assert inclusion == observe_setup_level_range_inclusion_v1(previous, current)
    legacy = assemble_setup_evidence_v3(previous, current)
    for component in ("continuity", "invalidation", "age", "level", "level_range"):
        assert evidence[component] == legacy[component]
    assert (
        evidence["legacy_evidence_v3_identity_sha256"]
        == legacy["result_identity_sha256"]
    )
    assert evidence["level_range"]["range_relation"] == "ENTIRELY_ABOVE"
    assert inclusion["first_inclusion"] == (
        {
            "session": "2026-08-26",
            "bar_identity_sha256": current.packet.members[0]
            .feature("MARKET_STRUCTURE")
            .source_bars[-2]
            .source_row_identity_sha256,
        }
        if expected
        else None
    )
    response = _response(evidence)
    checked = _check(previous, current, response)
    assert checked["contract_version"] == "external-setup-interpretation-check@v4"
    assert checked["verification"] == "STRUCTURED_BINDING_ONLY"
    assert checked["eligibility"] == checked["explanation_accuracy"] == "NOT_ASSESSED"
    assert checked["external_response"] == response
    for use_evidence in (True, False):
        values, calls = iter((previous, current)), []

        def service(symbol, root, *, _calls=calls, _values=values, **kwargs):
            _calls.append((symbol, root, kwargs))
            return next(_values)

        assert (
            _cli(
                tmp_path,
                previous,
                current,
                response,
                service=service,
                evidence=use_evidence,
            )
            == 0
        )
        output = capsys.readouterr()
        assert output.err == ""
        assert output.out.encode() == canonical_comparison_bytes(
            evidence if use_evidence else checked
        )
        assert calls == [
            (
                "PNB",
                tmp_path,
                {
                    "question": "CURRENT_STRUCTURE",
                    "selection_time": v.data_selection_time,
                },
            )
            for v in (previous, current)
        ]
    forged = copy.deepcopy(response)
    forged["facts"]["level_range_inclusion"]["inclusion_observed"] = not expected
    with pytest.raises(ValueError):
        _check(previous, current, forged)
    if expected:
        forged = copy.deepcopy(response)
        forged["facts"]["level_range_inclusion"]["first_inclusion"]["session"] = (
            "2026-08-27"
        )
        with pytest.raises(ValueError):
            _check(previous, current, forged)


@pytest.fixture(scope="module")
def admitted_response(chronological):
    pair = chronological["previous"], chronological["earlier"]
    return pair, _response(_bundle(*pair))


@pytest.mark.parametrize(
    "field,value",
    [
        ("inclusion_observed", 0),
        ("inclusion_observed", 1),
        ("inclusion_observed", "true"),
        ("inclusion_observed", []),
        ("status", True),
        ("status", "observed"),
        ("status", "X" * 33),
        ("result_identity_sha256", "A" * 64),
        ("first_inclusion", True),
        ("first_inclusion", []),
        ("first_inclusion", {}),
    ],
)
def test_new_claim_types_precede_any_observation_access(
    admitted_response, monkeypatch, field, value
):
    _, original = admitted_response
    response = copy.deepcopy(original)
    response["facts"]["level_range_inclusion"][field] = value
    calls = []
    monkeypatch.setattr(
        _api(), "assemble_setup_evidence_v4", lambda *args: calls.append(args)
    )
    with pytest.raises(ValueError):
        _check(None, None, response)
    with pytest.raises(ValueError):
        _api().setup_interpretation_request_v4_from_json(json.dumps(response).encode())
    assert not calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("session", "2026-02-30"),
        ("session", "2026-2-03"),
        ("session", "20260826"),
        ("session", "２０２６-０８-２６"),
        ("session", "0000-01-01"),
        ("session", "2026-08-26T00:00:00Z"),
        ("session", None),
        ("session", 20260826),
        ("bar_identity_sha256", "A" * 64),
        ("bar_identity_sha256", "0" * 63),
        ("bar_identity_sha256", None),
    ],
)
def test_first_session_is_closed_real_canonical_date(admitted_response, field, value):
    _, original = admitted_response
    response = copy.deepcopy(original)
    response["facts"]["level_range_inclusion"]["first_inclusion"][field] = value
    with pytest.raises(ValueError):
        _check(None, None, response)
    with pytest.raises(ValueError):
        _api().setup_interpretation_request_v4_from_json(json.dumps(response).encode())


@pytest.mark.parametrize("depth", ["level_range_inclusion", "first_inclusion"])
@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_new_claim_closed_at_each_depth(admitted_response, depth, mutation):
    _, original = admitted_response
    response = copy.deepcopy(original)
    target = response["facts"]["level_range_inclusion"]
    if depth == "first_inclusion":
        target = target[depth]
    if mutation == "extra":
        target["private_extra"] = 1
    else:
        target.pop(next(iter(target)))
    with pytest.raises(ValueError):
        _check(None, None, response)


@pytest.mark.parametrize(
    "name",
    [
        "level_range_inclusion",
        "inclusion_observed",
        "first_inclusion",
        "session",
        "bar_identity_sha256",
    ],
)
def test_new_nested_duplicate_keys_rejected(admitted_response, name):
    raw = json.dumps(admitted_response[1])
    key = json.dumps(name) + ":"
    raw = raw.replace(key, key + "null," + key, 1)
    with pytest.raises(ValueError):
        _api().setup_interpretation_request_v4_from_json(raw.encode())


@pytest.mark.parametrize(
    "field,value",
    [
        ("inclusion_observed", False),
        ("inclusion_observed", None),
        ("first_inclusion", None),
        ("status", "UNKNOWN"),
        ("result_identity_sha256", "0" * 64),
        ("session", "2026-08-27"),
        ("bar_identity_sha256", "0" * 64),
    ],
)
def test_well_formed_false_new_claims_fail_binding(admitted_response, field, value):
    pair, original = admitted_response
    response = copy.deepcopy(original)
    target = response["facts"]["level_range_inclusion"]
    if field in ("session", "bar_identity_sha256"):
        target = target["first_inclusion"]
    target[field] = value
    assert (
        _api().setup_interpretation_request_v4_from_json(json.dumps(response).encode())
        == response
    )
    with pytest.raises(ValueError, match="binding"):
        _check(*pair, response)


@pytest.mark.parametrize("scenario", ["earlier", "previous"])
@pytest.mark.parametrize(
    "field",
    [
        "previous_observation_identity_sha256",
        "current_observation_identity_sha256",
        "previous",
        "current",
        "continuity_identity_sha256",
        "continuity_status",
        "level_identity_sha256",
        "latest_range_identity_sha256",
        "status",
        "witness",
        "result_identity_sha256",
    ],
)
def test_resealed_inclusion_join_terminal_including_replay(
    chronological, monkeypatch, scenario, field
):
    pair = chronological["previous"], chronological[scenario]
    module = importlib.import_module(PREFIX + "setup_evidence_v4")
    false = copy.deepcopy(observe_setup_level_range_inclusion_v1(*pair))
    false[field] = {} if field in ("previous", "current", "witness") else "0" * 64
    if field != "result_identity_sha256":
        unsigned = dict(false)
        unsigned.pop("result_identity_sha256")
        false["result_identity_sha256"] = hashlib.sha256(
            canonical_comparison_bytes(unsigned)
        ).hexdigest()
    monkeypatch.setattr(
        module, "observe_setup_level_range_inclusion_v1", lambda *args: false
    )
    with pytest.raises(ValueError):
        _bundle(*pair)


def test_both_original_builders_called_once_on_identical_pair(
    admitted_response, monkeypatch
):
    pair, _ = admitted_response
    module = importlib.import_module(PREFIX + "setup_evidence_v4")
    legacy, inclusion = (
        module.assemble_setup_evidence_v3,
        module.observe_setup_level_range_inclusion_v1,
    )
    calls = []

    def old(*args):
        calls.append(("v3", args))
        return legacy(*args)

    def original(*args):
        calls.append(("inclusion", args))
        return inclusion(*args)

    monkeypatch.setattr(module, "assemble_setup_evidence_v3", old)
    monkeypatch.setattr(module, "observe_setup_level_range_inclusion_v1", original)
    _bundle(*pair)
    assert calls == [("v3", pair), ("inclusion", pair)]


def test_normalized_first_row_does_not_alias_caller_input(admitted_response):
    _, response = admitted_response
    snapshot = copy.deepcopy(response)
    parsed = _api().setup_interpretation_request_v4_from_json(
        json.dumps(response).encode()
    )
    parsed["facts"]["level_range_inclusion"]["first_inclusion"]["session"] = (
        "2026-08-27"
    )
    assert response == snapshot
