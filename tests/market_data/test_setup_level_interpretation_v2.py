"""Versioned consumer handoff preserves and checks the same admitted level pair."""

import copy
import hashlib
import importlib
import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_setup_event_continuity import _rolling_observe
from test_setup_interpretation import _response as old_response
from test_setup_invalidation import _anchored
from test_setup_observation_comparison import _args, _observe

from swing_trading_ai_assistant.research_comparison import (
    setup_observation_comparison as encoding,
)
from swing_trading_ai_assistant.research_comparison.setup_evidence import (
    assemble_setup_evidence_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_level import (
    observe_setup_level_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (
    canonical_comparison_bytes,
)

MODULE = "swing_trading_ai_assistant.research_comparison.setup_interpretation_v2"
PREFIX = "swing_trading_ai_assistant.research_comparison."


def _bundle(p, c):
    return importlib.import_module(
        PREFIX + "setup_evidence_v2"
    ).assemble_setup_evidence_v2(p, c)


def _response(evidence, disposition="RESEARCH_ONLY"):
    response = old_response(evidence, disposition)
    response["schema"] = "external-setup-interpretation-request@v2"
    response["facts"]["level"] = {
        key: evidence["level"][key]
        for key in ("result_identity_sha256", "status", "relation")
    }
    return response


def _cli(tmp_path, p, c, response, *, service=None, command="setup-interpretation-v2"):
    args = _args(tmp_path)
    args[0] = command
    for side, value in (("previous", p), ("current", c)):
        args[args.index("--" + side + "-selection-time") + 1] = (
            value.data_selection_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )
    if command == "setup-interpretation-v2":
        path = tmp_path / "response.json"
        path.write_bytes(json.dumps(response).encode())
        path.chmod(0o600)
        args += ["--interpretation-file", str(path)]
    if service is None:
        values = iter((p, c))

        def service(*a, **kw):
            return next(values)

    name = PREFIX + (
        "setup_interpretation_v2_cli"
        if command == "setup-interpretation-v2"
        else "setup_evidence_v2_cli"
    )
    return importlib.import_module(name).main(args, observation_service=service)


def test_actual_cli_preserves_and_checks_level_from_one_pair(tmp_path, capsys):
    p = _anchored(tmp_path / "p")
    c = _anchored(tmp_path / "c", later=True, close=134, wick=120)
    bundle = _bundle(p, c)
    response = _response(bundle)
    values, calls = iter((p, c)), []

    def service(symbol, root, **kwargs):
        calls.append((symbol, root, kwargs))
        return next(values)

    assert _cli(tmp_path, p, c, response, service=service) == 0
    output = capsys.readouterr()
    assert not output.err
    result = json.loads(output.out)
    assert result["contract_version"] == "external-setup-interpretation-check@v2"
    assert result["evidence"] == bundle
    assert bundle["contract_version"] == "causal-setup-evidence@v2"
    assert bundle["level"]["relation"] == "ABOVE"
    assert bundle["invalidation"]["status"] == "NO_CONTRADICTION_OBSERVED"
    assert result["external_response"] == response
    assert result["verification"] == "STRUCTURED_BINDING_ONLY"
    assert result["explanation_accuracy"] == result["eligibility"] == "NOT_ASSESSED"
    assert [x[2]["selection_time"] for x in calls] == [
        p.data_selection_time,
        c.data_selection_time,
    ]
    assert [x[2]["question"] for x in calls] == ["CURRENT_STRUCTURE"] * 2
    assert output.out.encode() == canonical_comparison_bytes(result)
    old = assemble_setup_evidence_v1(p, c)
    assert bundle["legacy_evidence_identity_sha256"] == old["result_identity_sha256"]
    for name in ("continuity", "invalidation", "age"):
        assert bundle[name] == old[name]
    assert bundle["level"] == observe_setup_level_v1(p, c)


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    root = tmp_path_factory.mktemp("interpretation-pair")
    return _anchored(root / "p"), _anchored(root / "c", later=True)


def _api():
    return importlib.import_module(MODULE)


def _check(previous, current, response):
    return _api().check_setup_interpretation_v2(previous, current, response)


@pytest.mark.parametrize("disposition", ["RESEARCH_ONLY", "NO_TRADE"])
def test_contradiction_does_not_change_caller_posture_or_age(pair, disposition):
    evidence = _bundle(*pair)
    request = _response(evidence, disposition)
    report = _check(*pair, request)
    assert report["evidence"]["invalidation"]["status"] == "INVALIDATED"
    assert report["evidence"]["age"]["completed_sessions_elapsed"] == 1
    assert report["external_response"]["disposition"] == disposition
    assert report["actionable_recommendation"] == "NOT_ASSESSED"


@pytest.mark.parametrize(
    "before,after,days,status,code",
    [
        ("positive", "insufficient", 0, "UNKNOWN", 1),
        ("insufficient", "positive", 0, "UNKNOWN", 1),
        ("positive", "negative", 0, "NOT_REPRESENTED", 1),
        ("negative", "positive", 0, "NO_BASELINE", 0),
        ("positive", "positive", 35, "OUTSIDE_WINDOW", 1),
    ],
)
def test_independent_inconclusive_states(
    tmp_path, capsys, before, after, days, status, code
):
    p = _observe(tmp_path / "p", before)
    c = _observe(tmp_path / "c", after, days=days, minutes=1)
    evidence = _bundle(p, c)
    request = _response(evidence, "NO_TRADE")
    assert _cli(tmp_path, p, c, request) == code
    output = capsys.readouterr()
    assert not output.err
    report = json.loads(output.out)
    assert report["evidence"] == evidence
    assert report["evidence"]["continuity"]["status"] == status
    assert report["evidence"]["age"]["completed_sessions_elapsed"] is None


def test_replay_revisions_and_noncomparable_preserved(tmp_path):
    p = _anchored(tmp_path / "p")
    replay = _check(p, p, _response(_bundle(p, p)))
    assert replay["evidence"]["age"]["completed_sessions_elapsed"] == 0
    for c in (
        _anchored(tmp_path / "low", later=True, low_revision=1),
        _rolling_observe(tmp_path / "event", shift=1),
        _observe(tmp_path / "other", symbol="SBIN", minutes=1),
    ):
        evidence = _bundle(p, c)
        assert _check(p, c, _response(evidence))["evidence"] == evidence
        assert evidence["invalidation"]["status"] in (
            "REVISED_EVIDENCE",
            "NON_COMPARABLE",
        )


@pytest.mark.parametrize("name", ["continuity", "invalidation", "age", "level"])
@pytest.mark.parametrize("field", ["status", "result_identity_sha256"])
def test_false_structured_claim_rejected(pair, name, field):
    request = _response(_bundle(*pair))
    request["facts"][name][field] = "UNKNOWN" if field == "status" else "0" * 64
    with pytest.raises(ValueError, match="binding"):
        _check(*pair, request)


@pytest.mark.parametrize("mutation", ["bundle", "swapped", "omitted", "count", "null"])
def test_false_binding_cannot_be_resealed_as_caller_response(pair, mutation):
    request = _response(_bundle(*pair))
    if mutation == "bundle":
        request["evidence_identity_sha256"] = "0" * 64
    elif mutation == "swapped":
        request["facts"]["continuity"], request["facts"]["invalidation"] = (
            request["facts"]["invalidation"],
            request["facts"]["continuity"],
        )
    elif mutation == "omitted":
        del request["facts"]["invalidation"]
    else:
        request["facts"]["age"]["completed_sessions_elapsed"] = (
            0 if mutation == "count" else None
        )
    with pytest.raises(ValueError):
        _check(*pair, request)


@pytest.mark.parametrize(
    "path,value",
    [
        (("schema",), "unsupported"),
        (("disposition",), "BUY"),
        (("disposition",), "ELIGIBLE"),
        (("disposition",), []),
        (("evidence_identity_sha256",), "A" * 64),
        (("evidence_identity_sha256",), "0" * 63),
        (("explanation",), ""),
        (("explanation",), " \n\t"),
        (("explanation",), "x" * 2049),
        (("explanation",), "hidden\x00body"),
        (("explanation",), "\ud800"),
        (("explanation",), 3),
        (("facts", "age", "completed_sessions_elapsed"), True),
        (("facts", "age", "completed_sessions_elapsed"), -1),
        (("facts", "age", "completed_sessions_elapsed"), 21),
        (("facts", "age", "completed_sessions_elapsed"), 1.0),
        (("facts", "continuity", "status"), "UNKNOWN1"),
        (("facts", "continuity", "status"), "X" * 33),
        (("facts", "continuity", "status"), "unknown"),
        (("facts", "continuity"), []),
    ],
)
def test_malformed_direct_and_json_response_precedes_evidence(
    pair, monkeypatch, path, value
):
    request = _response(_bundle(*pair))
    target = request
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    calls = []
    monkeypatch.setattr(
        _api(), "assemble_setup_evidence_v2", lambda *args: calls.append(args)
    )
    with pytest.raises(ValueError):
        _check(None, None, request)
    with pytest.raises(ValueError):
        _api().setup_interpretation_request_v2_from_json(json.dumps(request).encode())
    assert not calls


@pytest.mark.parametrize(
    "path",
    [(), ("facts",), ("facts", "age"), ("facts", "continuity"), ("facts", "level")],
)
@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_closed_shape_at_every_depth(pair, path, mutation):
    request = _response(_bundle(*pair))
    target = request
    for key in path:
        target = target[key]
    if mutation == "extra":
        target["unexpected"] = 0
    else:
        target.pop(next(iter(target)))
    with pytest.raises(ValueError):
        _check(None, None, request)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b" ",
        b"\xff",
        b"[]",
        b"null",
        b"NaN",
        b"Infinity",
        b"{" + b" " * 65536,
        b"[" * 2000 + b"]" * 2000,
    ],
)
def test_parser_rejects_malformed_nonfinite_overdeep_and_bounds(raw):
    with pytest.raises(ValueError):
        _api().setup_interpretation_request_v2_from_json(raw)


@pytest.mark.parametrize(
    "name",
    ["schema", "facts", "status", "completed_sessions_elapsed", "relation", "level"],
)
def test_duplicate_keys_at_all_levels_rejected(pair, name):
    request = _response(_bundle(*pair))
    raw = json.dumps(request)
    token = json.dumps(name) + ":"
    raw = raw.replace(token, token + "null, " + token, 1)
    with pytest.raises(ValueError):
        _api().setup_interpretation_request_v2_from_json(raw.encode())


def test_limits_and_unassessed_prose(pair):
    request = _response(_bundle(*pair))
    # This checker explicitly does not certify or semantically censor narrative.
    prefix = "BUY is an unsupported caller assertion.\n\t"
    request["explanation"] = prefix + "अ" * (2048 - len(prefix))
    assert len(request["explanation"]) == 2048
    raw = json.dumps(request).encode()
    padded = raw + b" " * (65536 - len(raw))
    assert _api().setup_interpretation_request_v2_from_json(padded) == request
    with pytest.raises(ValueError):
        _api().setup_interpretation_request_v2_from_json(padded + b" ")
    assert _check(*pair, request)["explanation_accuracy"] == "NOT_ASSESSED"
    for count in (0, 20, None):
        request["facts"]["age"]["completed_sessions_elapsed"] = count
        assert (
            _api().setup_interpretation_request_v2_from_json(
                json.dumps(request).encode()
            )
            == request
        )


def test_pure_retry_and_concurrent_input_preservation(pair):
    request = _response(_bundle(*pair))
    before = copy.deepcopy(request)
    expected = _check(*pair, request)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: _check(*pair, request), range(8)))
    assert all(report == expected for report in results)
    assert request == before
    assert _check(*pair, request) == expected


@pytest.mark.parametrize("field", ["code", "runtime_code_identity_sha256", "question"])
def test_producer_integrity_terminal_even_with_unknown(tmp_path, field):
    p = _observe(tmp_path / "p")
    c = _observe(tmp_path / "c", "insufficient", minutes=1)
    request = _response(_bundle(p, c))
    object.__setattr__(p, field, "PRIVATE_MARKET_BODY")
    with pytest.raises(ValueError):
        _check(p, c, request)


@pytest.mark.parametrize("mutation", ["missing", "extra", "substituted"])
def test_closed_runtime_inventory(pair, monkeypatch, mutation):
    request = _response(_bundle(*pair))
    sources = dict(_api().SETUP_INTERPRETATION_RUNTIME_SOURCE_SHA256_V2)
    if mutation == "missing":
        sources.pop(next(iter(sources)))
    elif mutation == "extra":
        sources["unexpected.py"] = "0" * 64
    else:
        sources[next(iter(sources))] = "0" * 64
    monkeypatch.setattr(
        _api(), "SETUP_INTERPRETATION_RUNTIME_SOURCE_SHA256_V2", sources
    )
    with pytest.raises(ValueError, match="runtime"):
        _check(*pair, request)


def _file_args(tmp_path, pair, request):
    path = tmp_path / "response.json"
    path.write_bytes(json.dumps(request).encode())
    path.chmod(0o600)
    args = _args(tmp_path)
    args[0] = "setup-interpretation-v2"
    args += ["--interpretation-file", str(path)]
    for side, obs in zip(("previous", "current"), pair, strict=True):
        args[args.index("--" + side + "-selection-time") + 1] = (
            obs.data_selection_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )
    return args, path


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "relative",
        "public",
        "symlink",
        "parent-symlink",
        "hardlink",
        "directory",
        "fifo",
        "oversized",
        "wrong-owner",
        "malformed",
    ],
)
def test_private_reader_rejects_before_calls(
    tmp_path, pair, capsys, monkeypatch, mutation
):
    cli = importlib.import_module(MODULE + "_cli")
    args, path = _file_args(tmp_path, pair, _response(_bundle(*pair)))
    if mutation == "missing":
        path.unlink()
    elif mutation == "relative":
        args[-1] = "response.json"
    elif mutation == "public":
        path.chmod(0o644)
    elif mutation in ("symlink", "hardlink"):
        alias = tmp_path / "alias.json"
        alias.symlink_to(path) if mutation == "symlink" else os.link(path, alias)
        args[-1] = str(alias)
    elif mutation == "parent-symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        args[-1] = str(alias / path.name)
    elif mutation in ("directory", "fifo"):
        path.unlink()
        path.mkdir() if mutation == "directory" else os.mkfifo(path, 0o600)
    elif mutation == "oversized":
        path.write_bytes(b"x" * 65537)
    elif mutation == "wrong-owner":
        monkeypatch.setattr(os, "geteuid", lambda: path.stat().st_uid + 1)
    else:
        path.write_bytes(b'{"schema": NaN}')
    calls = []
    assert cli.main(args, observation_service=lambda *a, **k: calls.append(a)) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "request_invalid\n" and not calls


@pytest.mark.parametrize("stage", ["read", "second", "check", "overflow", "stale"])
def test_atomic_fixed_failure_and_explicit_retry(
    tmp_path, pair, capsys, monkeypatch, stage
):
    cli = importlib.import_module(MODULE + "_cli")
    request = _response(_bundle(*pair))
    args, _ = _file_args(tmp_path, pair, request)
    calls = []

    def interrupted(*a, **k):
        raise KeyboardInterrupt("PRIVATE_BODY")

    def service(*a, **k):
        calls.append(k)
        if stage == "second" and len(calls) == 2:
            return interrupted()
        return pair[len(calls) - 1]

    with monkeypatch.context() as patch:
        if stage == "read":
            patch.setattr(cli, "_read_current_regime_input", interrupted)
        elif stage == "check":
            patch.setattr(cli, "check_setup_interpretation_v2", interrupted)
        elif stage == "overflow":
            # The admitted bundle fits; only the complete interpretation overflows.
            bound = len(canonical_comparison_bytes(_bundle(*pair))) + 1
            patch.setattr(encoding, "MAX_OUTPUT", bound)
        elif stage == "stale":
            request["evidence_identity_sha256"] = "0" * 64
            _file_args(tmp_path, pair, request)
        assert cli.main(args, observation_service=service) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "setup_interpretation_failed\n"
    assert len(calls) == (0 if stage == "read" else 2)
    assert _cli(tmp_path, *pair, _response(_bundle(*pair))) == 0
    assert not capsys.readouterr().err


@pytest.mark.parametrize(
    "field,value",
    [("symbol", "SBIN"), ("question", "PRICE_BEHAVIOR"), ("data_selection_time", None)],
)
def test_selector_mismatch_fails_before_second_call(
    tmp_path, pair, capsys, field, value
):
    calls = []
    bad = copy.copy(pair[0])
    object.__setattr__(bad, field, value)

    def service(*a, **k):
        calls.append(k)
        return bad

    assert (
        _cli(
            tmp_path,
            *pair,
            _response(_bundle(*pair)),
            service=service,
        )
        == 2
    )
    output = capsys.readouterr()
    assert len(calls) == 1
    assert output.out == "" and output.err == "setup_interpretation_failed\n"


def test_mutation_during_private_read_closes_descriptors(
    tmp_path, pair, monkeypatch, capsys
):
    cli = importlib.import_module(MODULE + "_cli")
    args, path = _file_args(tmp_path, pair, _response(_bundle(*pair)))
    read, close = os.read, os.close
    read_fds, closed = [], []

    def mutated(fd, bound):
        value = read(fd, bound)
        read_fds.append(fd)
        path.write_bytes(b"x")
        return value

    def tracked(fd):
        closed.append(fd)
        close(fd)

    monkeypatch.setattr(os, "read", mutated)
    monkeypatch.setattr(os, "close", tracked)
    calls = []
    assert cli.main(args, observation_service=lambda *a, **k: calls.append(a)) == 2
    assert read_fds and set(read_fds) <= set(closed) and not calls
    output = capsys.readouterr()
    assert output.out == "" and output.err == "request_invalid\n"


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--symbol", "PRIVATE\nBODY"),
        ("--storage-root", "relative"),
        ("--previous-selection-time", "invalid"),
        ("--previous-selection-time", "2026-09-30T00:00:00.000000Z"),
        ("--current-selection-time", "2026-08-26T04:15:00+01:00"),
        ("--output", "yaml"),
    ],
)
def test_selector_validation_precedes_file_reads(
    tmp_path, pair, capsys, monkeypatch, flag, value
):
    cli = importlib.import_module(MODULE + "_cli")
    args, _ = _file_args(tmp_path, pair, _response(_bundle(*pair)))
    args[args.index(flag) + 1] = value
    reads, calls = [], []
    monkeypatch.setattr(cli, "_read_current_regime_input", reads.append)
    assert cli.main(args, observation_service=lambda *a, **k: calls.append(a)) == 2
    output = capsys.readouterr()
    assert not reads and not calls
    assert output.out == "" and output.err == "request_invalid\n"


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_every_own_source_and_shared_reader_is_bound(pair, monkeypatch, index):
    api = _api()
    request = _response(_bundle(*pair))
    selected = tuple(api.SETUP_INTERPRETATION_RUNTIME_SOURCE_SHA256_V2)[index]
    original = api.runtime_source_sha256
    calls = []

    def substituted(module, root, relative):
        calls.append(relative)
        return "0" * 64 if relative == selected else original(module, root, relative)

    monkeypatch.setattr(api, "runtime_source_sha256", substituted)
    with pytest.raises(ValueError, match="runtime"):
        _check(*pair, request)
    assert selected in calls


def test_interrupted_actual_private_read_closes_descriptors(
    tmp_path, pair, monkeypatch, capsys
):
    cli = importlib.import_module(MODULE + "_cli")
    args, _ = _file_args(tmp_path, pair, _response(_bundle(*pair)))
    close = os.close
    opened, closed, calls = [], [], []

    def interrupted(fd, bound):
        opened.append(fd)
        raise KeyboardInterrupt("PRIVATE_BODY")

    def tracked(fd):
        closed.append(fd)
        close(fd)

    monkeypatch.setattr(os, "read", interrupted)
    monkeypatch.setattr(os, "close", tracked)
    assert cli.main(args, observation_service=lambda *a, **k: calls.append(a)) == 2
    assert opened and set(opened) <= set(closed) and not calls
    output = capsys.readouterr()
    assert output.out == "" and output.err == "setup_interpretation_failed\n"


def test_actual_cli_reads_once_checks_once_and_regenerates_once(
    tmp_path, pair, capsys, monkeypatch
):
    cli, sdk = importlib.import_module(MODULE + "_cli"), _api()
    request = _response(_bundle(*pair))
    read, check, assemble = (
        cli._read_current_regime_input,
        cli.check_setup_interpretation_v2,
        sdk.assemble_setup_evidence_v2,
    )
    counts = {"read": 0, "check": 0, "assemble": 0}

    def reader(*args):
        counts["read"] += 1
        return read(*args)

    def checker(*args):
        counts["check"] += 1
        return check(*args)

    def assembler(*args):
        counts["assemble"] += 1
        assert args == pair
        return assemble(*args)

    monkeypatch.setattr(cli, "_read_current_regime_input", reader)
    monkeypatch.setattr(cli, "check_setup_interpretation_v2", checker)
    monkeypatch.setattr(sdk, "assemble_setup_evidence_v2", assembler)
    assert _cli(tmp_path, *pair, request) == 0
    assert counts == {"read": 1, "check": 1, "assemble": 1}
    assert not capsys.readouterr().err


@pytest.mark.parametrize(
    "close,relation,invalid",
    [
        (134, "ABOVE", False),
        (130, "AT", False),
        (100, "BELOW", False),
        (89, "BELOW", True),
    ],
)
def test_level_independent_from_structural_invalidation(
    tmp_path, capsys, close, relation, invalid
):
    p = _anchored(tmp_path / "p")
    c = _anchored(tmp_path / "c", later=True, close=close, wick=80)
    bundle = _bundle(p, c)
    assert bundle["level"]["relation"] == relation
    assert bundle["invalidation"]["status"] == (
        "INVALIDATED" if invalid else "NO_CONTRADICTION_OBSERVED"
    )
    assert bundle["age"]["completed_sessions_elapsed"] == 1
    for disposition in ("RESEARCH_ONLY", "NO_TRADE"):
        result = _check(p, c, _response(bundle, disposition))
        assert result["external_response"]["disposition"] == disposition
    assert _cli(tmp_path, p, c, None, command="setup-evidence-v2") == 0
    assert json.loads(capsys.readouterr().out) == bundle


@pytest.mark.parametrize(
    "value", ["BELOW", "AT", None, True, 1, [], "above", "", "ELIGIBLE"]
)
def test_changed_or_malformed_level_relation_terminal(pair, value):
    bundle = _bundle(*pair)
    request = _response(bundle)
    if request["facts"]["level"]["relation"] == value:
        value = "ABOVE"
    request["facts"]["level"]["relation"] = value
    with pytest.raises(ValueError):
        _check(*pair, request)


@pytest.mark.parametrize(
    "mutation",
    [
        "v1-schema",
        "missing-level",
        "extra-level-key",
        "boolean-status",
        "malformed-hash",
        "different-pair",
    ],
)
def test_level_response_closed_shape_and_version(pair, mutation):
    request = _response(_bundle(*pair))
    if mutation == "v1-schema":
        request["schema"] = "external-setup-interpretation-request@v1"
    elif mutation == "missing-level":
        del request["facts"]["level"]
    elif mutation == "extra-level-key":
        request["facts"]["level"]["valid"] = True
    elif mutation == "boolean-status":
        request["facts"]["level"]["status"] = True
    elif mutation == "malformed-hash":
        request["facts"]["level"]["result_identity_sha256"] = "A" * 64
    else:
        request["facts"]["level"]["result_identity_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        _check(*pair, request)


@pytest.mark.parametrize(
    "mutation",
    [
        "previous",
        "current",
        "previous_observation_identity_sha256",
        "current_observation_identity_sha256",
        "continuity_identity_sha256",
        "result_identity_sha256",
        "relation",
    ],
)
def test_level_composition_substitution_terminal(pair, monkeypatch, mutation):
    module = importlib.import_module(PREFIX + "setup_evidence_v2")
    actual = observe_setup_level_v1(*pair)
    bad = copy.deepcopy(actual)
    bad[mutation] = {} if mutation in ("previous", "current") else "0" * 64
    if mutation != "result_identity_sha256":
        unsigned = dict(bad)
        unsigned.pop("result_identity_sha256")
        # A changed relation without resealing challenges the full component seal.
        if mutation != "relation":
            bad["result_identity_sha256"] = hashlib.sha256(
                canonical_comparison_bytes(unsigned)
            ).hexdigest()
    monkeypatch.setattr(module, "observe_setup_level_v1", lambda *a: bad)
    with pytest.raises(ValueError):
        _bundle(*pair)


@pytest.mark.parametrize("mutation", ["missing", "extra", "substituted"])
def test_evidence_v2_closed_runtime_inventory(pair, monkeypatch, mutation):
    module = importlib.import_module(PREFIX + "setup_evidence_v2")
    sources = dict(module.SETUP_EVIDENCE_RUNTIME_SOURCE_SHA256_V2)
    if mutation == "missing":
        sources.pop(next(iter(sources)))
    elif mutation == "extra":
        sources["unexpected.py"] = "0" * 64
    else:
        sources[next(iter(sources))] = "0" * 64
    monkeypatch.setattr(module, "SETUP_EVIDENCE_RUNTIME_SOURCE_SHA256_V2", sources)
    with pytest.raises(ValueError, match="runtime"):
        _bundle(*pair)


def test_exact_whole_output_bound_and_plus_one(pair, monkeypatch):
    bundle = _bundle(*pair)
    request = _response(bundle)
    result = _check(*pair, request)
    size = len(canonical_comparison_bytes(result))
    monkeypatch.setattr(encoding, "MAX_OUTPUT", size)
    assert canonical_comparison_bytes(
        _check(*pair, request)
    ) == canonical_comparison_bytes(result)
    monkeypatch.setattr(encoding, "MAX_OUTPUT", size - 1)
    with pytest.raises(ValueError):
        _check(*pair, request)
