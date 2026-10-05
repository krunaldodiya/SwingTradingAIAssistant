"""Distribution checks retain isolation and ownership across engines."""

import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "linux_distribution", ROOT / "scripts/verify_linux_distribution.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _age_output(scenario):
    count = {"same-event": 1, "replay": 0, "unknown": None}[scenario]
    schedule = {
        "source": "nse-upstox-composed-calendar",
        "source_release": "composed-calendar@v1=" + "c" * 64,
        "evidence_identity_sha256": "d" * 64,
        "schedule_identity_sha256": "e" * 64,
        "feature_known_at": "2026-08-27T04:15:00.000000Z",
    }
    return {
        "contract_version": "causal-setup-age@v1",
        "criterion": "ADMITTED_COMPLETED_SESSIONS_SINCE_ORIGINAL_UPWARD_BOS@v1",
        "status": {"same-event": "OBSERVED", "replay": "REPLAY", "unknown": "UNKNOWN"}[
            scenario
        ],
        "continuity_status": {
            "same-event": "SAME_EVENT",
            "replay": "REPLAY",
            "unknown": "UNKNOWN",
        }[scenario],
        "completed_sessions_elapsed": count,
        "original_event_session": "2026-08-25" if count is not None else None,
        "current_completed_session": "2026-08-26"
        if count
        else "2026-08-25"
        if count == 0
        else None,
        "schedules": {"previous": dict(schedule), "current": dict(schedule)}
        if count is not None
        else None,
        "previous": {"candidate": {"event_session": "2026-08-25"}},
        "current": {
            "status": "NO_MATCH" if count == 1 else "MATCH" if count == 0 else "UNKNOWN"
        },
        "runtime_code_identity_sha256": "b" * 64,
        "previous_observation_identity_sha256": "f" * 64,
        "current_observation_identity_sha256": "a" * 64,
        "continuity_identity_sha256": "9" * 64,
    }


def _sealed_age(value):
    value = dict(value)
    value.pop("result_identity_sha256", None)
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    value["result_identity_sha256"] = hashlib.sha256(raw).hexdigest()
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def test_installed_age_gate_probes_isolated_sdk_cli_and_three_outcomes(
    monkeypatch, tmp_path
):
    api = load(monkeypatch)
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            args,
            1 if args[-1] == "unknown" else 0,
            _sealed_age(_age_output(args[-1])),
            b"SYNTHETIC: not current market data.\n",
        )

    monkeypatch.setattr(api, "_run", run)
    python = tmp_path / "venv/bin/python"
    outcomes = api._verify_installed_age(python, tmp_path)
    assert set(outcomes) == {"same-event", "replay", "unknown"}
    assert outcomes["same-event"]["completed_sessions_elapsed"] == 1
    for args, kwargs in calls:
        assert args[:3] == [str(python), "-I", "-c"]
        assert "setup_age as sdk" in args[3] and "setup_age_cli as cli" in args[3]
        assert "sys.prefix" in args[3] and "is_relative_to" in args[3]
        assert kwargs["cwd"] == tmp_path
        assert (
            "PYTHONPATH" not in kwargs["env"]
            and "BHARATSTOCK_API_KEY" not in kwargs["env"]
        )


@pytest.mark.parametrize(
    "failure",
    [
        "count",
        "bool",
        "status",
        "exit",
        "digest",
        "leak",
        "schedule",
        "endpoint",
        "fabricated-unknown",
        "criterion",
        "noncanonical",
    ],
)
def test_installed_age_gate_rejects_plausible_wrong_evidence(
    monkeypatch, tmp_path, failure
):
    api = load(monkeypatch)

    def run(args, **kwargs):
        scenario = args[-1]
        value = _age_output(scenario)
        mutations = {
            "count": ("completed_sessions_elapsed", 2),
            "bool": ("completed_sessions_elapsed", True),
            "status": ("status", "VALID"),
            "criterion": ("criterion", "CALENDAR_DAYS"),
            "leak": ("close", 134),
            "endpoint": ("current_completed_session", "2026-08-25"),
        }
        if failure in mutations:
            key, replacement = mutations[failure]
            value[key] = replacement
        if failure == "schedule" and value["schedules"]:
            value["schedules"]["current"]["schedule_identity_sha256"] = "invalid"
        if failure == "fabricated-unknown" and scenario == "unknown":
            value["schedules"] = {}
        raw = _sealed_age(value)
        if failure == "digest":
            value = json.loads(raw)
            value["result_identity_sha256"] = "0" * 64
            raw = (
                json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        if failure == "noncanonical":
            raw = json.dumps(json.loads(raw)).encode()
        return subprocess.CompletedProcess(
            args,
            2 if failure == "exit" else 1 if scenario == "unknown" else 0,
            raw,
            b"SYNTHETIC: not current market data.\n",
        )

    monkeypatch.setattr(api, "_run", run)
    with pytest.raises(RuntimeError, match="age"):
        api._verify_installed_age(tmp_path / "venv/bin/python", tmp_path)


@pytest.mark.parametrize(
    "runtime, rootless", [("docker", False), ("podman", False), ("podman", True)]
)
def test_container_retains_restrictions_and_explicit_user(
    monkeypatch, runtime, rootless
):
    api = load(monkeypatch)
    monkeypatch.setattr(api, "_RUNTIME", "/bin/" + runtime, raising=False)
    monkeypatch.setattr(api, "_PODMAN_ROOTLESS", rootless, raising=False)
    command = api._container("fixture-image", user="1000:1000")
    assert command[0] == "/bin/" + runtime
    assert command[command.index("--user") + 1] == "1000:1000"
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command and "no-new-privileges" in command
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert ("--userns=keep-id" in command) == rootless


def test_unselected_engine_cannot_run(monkeypatch):
    api = load(monkeypatch)
    with pytest.raises(RuntimeError, match="selected"):
        api._container("fixture-image")


def test_remote_build_recovery_waits_for_responsive_replacement(monkeypatch, tmp_path):
    api = load(monkeypatch)
    generation = tmp_path / "generation"
    generation.write_text("1\n")
    generation.chmod(0o640)
    monkeypatch.setattr(api, "_PODMAN_GENERATION", generation, raising=False)
    monkeypatch.setattr(api, "_RUNTIME", "/usr/bin/podman")
    monkeypatch.setenv("CONTAINER_HOST", "unix:///ci/podman.sock")
    monkeypatch.setattr(api, "_PODMAN_ROOTLESS", False)
    reads = []

    def run(args, **kwargs):
        reads.append(args)
        return subprocess.CompletedProcess(
            args, 0 if generation.read_text() == "2\n" else 125, b"{}", b""
        )

    monkeypatch.setattr(api, "_run", run)
    monkeypatch.setattr(api.time, "sleep", lambda _: generation.write_text("2\n"))
    api._wait_for_podman_recovery(1)
    assert generation.read_text() == "2\n"
    assert reads and all("info" in args for args in reads)


@pytest.mark.parametrize("restarted", [False, True])
def test_remote_build_recovery_accepts_healthy_service(
    monkeypatch, tmp_path, restarted
):
    api = load(monkeypatch)
    generation = tmp_path / "generation"
    generation.write_text("2\n" if restarted else "1\n")
    generation.chmod(0o640)
    monkeypatch.setattr(api, "_PODMAN_GENERATION", generation)
    monkeypatch.setattr(api, "_RUNTIME", "/usr/bin/podman")
    ticks = iter([0, 1, 11])
    observed = []

    def clock():
        value = next(ticks)
        observed.append(value)
        return value

    def health(args, **kwargs):
        # A live first service can still be processing the cancelled build.
        # Do not accept its early response as completion of the observation window.
        if not restarted:
            assert observed[-1] >= 10
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(api, "_run", health)
    monkeypatch.setattr(api.time, "monotonic", clock)
    monkeypatch.setattr(api.time, "sleep", lambda _: None)
    api._wait_for_podman_recovery(1)
    assert api._podman_generation() - 1 == int(restarted)


@pytest.mark.parametrize("generation_value", ["1\n", "2\n"])
def test_remote_build_recovery_rejects_unresponsive_service(
    monkeypatch, tmp_path, generation_value
):
    api = load(monkeypatch)
    generation = tmp_path / "generation"
    generation.write_text(generation_value)
    generation.chmod(0o640)
    monkeypatch.setattr(api, "_PODMAN_GENERATION", generation)
    monkeypatch.setattr(api, "_RUNTIME", "/usr/bin/podman")
    monkeypatch.setattr(
        api, "_run", lambda args, **kwargs: subprocess.CompletedProcess(args, 125)
    )
    ticks = iter([0, 1, 11])
    monkeypatch.setattr(api.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(api.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="recover"):
        api._wait_for_podman_recovery(1)


@pytest.mark.parametrize(
    "case", ["zero", "third", "extra", "mode", "symlink", "hardlink", "fifo"]
)
def test_private_engine_generation_rejects_untrusted_shape(monkeypatch, tmp_path, case):
    api = load(monkeypatch)
    generation = tmp_path / "generation"
    generation.write_text(
        {"zero": "0\n", "third": "3\n", "extra": "2\nx"}.get(case, "2\n")
    )
    generation.chmod(0o666 if case == "mode" else 0o640)
    if case == "fifo":
        generation.unlink()
        os.mkfifo(generation, 0o640)
    elif case == "symlink":
        target = generation.rename(tmp_path / "target")
        generation.symlink_to(target)
    elif case == "hardlink":
        (tmp_path / "second").hardlink_to(generation)
    monkeypatch.setattr(api, "_PODMAN_GENERATION", generation)
    with pytest.raises((RuntimeError, OSError)):
        api._podman_generation()


def test_job_engine_already_restarted_fails_before_build(monkeypatch, tmp_path):
    api = load(monkeypatch)
    generation = tmp_path / "generation"
    generation.write_text("2\n")
    generation.chmod(0o640)
    monkeypatch.setattr(api, "_PODMAN_GENERATION", generation)
    monkeypatch.setattr(api, "_RUNTIME", "/usr/bin/podman")
    monkeypatch.setenv("CONTAINER_HOST", "unix:///ci/podman.sock")
    with pytest.raises(RuntimeError, match="before interruption"):
        api._verify_interrupted_build(["podman", "build", "--tag", "test", "."], "test")


def test_installed_continuity_requires_new_behavior(monkeypatch, tmp_path):
    api = load(monkeypatch)
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        scenario = args[-1]
        value = {
            "contract_version": "causal-setup-event-continuity@v1",
            "status": "SAME_EVENT" if scenario == "same-event" else "UNKNOWN",
            "current": {
                "status": "NO_MATCH" if scenario == "same-event" else "UNKNOWN"
            },
            "result_identity_sha256": "a" * 64,
            "runtime_code_identity_sha256": "b" * 64,
        }
        return subprocess.CompletedProcess(
            args,
            0 if scenario == "same-event" else 1,
            json.dumps(value).encode(),
            b"SYNTHETIC: not current market data.\n",
        )

    monkeypatch.setattr(api, "_run", run)
    python = tmp_path / "venv/bin/python"
    outcomes = api._verify_installed_continuity(python, tmp_path)
    assert set(outcomes) == {"same-event", "unknown"}
    for args, kwargs in calls:
        assert args[:3] == [str(python), "-I", "-c"]
        assert "is_relative_to" in args[3] and "sys.prefix" in args[3]
        assert kwargs["cwd"] == tmp_path
        assert "PYTHONPATH" not in kwargs["env"]
        assert "BHARATSTOCK_API_KEY" not in kwargs["env"]


@pytest.mark.parametrize(
    "failure", ["wrong-status", "wrong-exit", "leak", "bad-digest", "wrong-contract"]
)
def test_installed_continuity_rejects_plausible_wrong_output(
    monkeypatch, tmp_path, failure
):
    api = load(monkeypatch)

    def run(args, **kwargs):
        value = {
            "contract_version": "wrong"
            if failure == "wrong-contract"
            else "causal-setup-event-continuity@v1",
            "status": "NOT_REPRESENTED" if failure == "wrong-status" else "SAME_EVENT",
            "current": {"status": "NO_MATCH"},
            "result_identity_sha256": "short" if failure == "bad-digest" else "a" * 64,
            "runtime_code_identity_sha256": "b" * 64,
        }
        if failure == "leak":
            value["close"] = 100
        return subprocess.CompletedProcess(
            args,
            2 if failure == "wrong-exit" else 0,
            json.dumps(value).encode(),
            b"SYNTHETIC: not current market data.\n",
        )

    monkeypatch.setattr(api, "_run", run)
    with pytest.raises(RuntimeError, match="continuity"):
        api._verify_installed_continuity(tmp_path / "venv/bin/python", tmp_path)


def _invalidation_output(scenario):
    low = {
        "kind": "SWING_LOW",
        "relation": "HL",
        "pivot_session": "2026-08-17",
        "pivot_confirmation_session": "2026-08-19",
        "pivot_identity_sha256": "c" * 64,
    }
    value = {
        "contract_version": "causal-setup-invalidation@v1",
        "criterion": "LATER_DOWN_CHOCH_OF_ORIGINAL_CONFIRMED_HL@v1",
        "status": {
            "invalidated": "INVALIDATED",
            "no-contradiction": "NO_CONTRADICTION_OBSERVED",
            "unknown": "UNKNOWN",
        }[scenario],
        "current": {"status": "UNKNOWN" if scenario == "unknown" else "NO_MATCH"},
        "previous": {"candidate": {"event_session": "2026-08-26"}},
        "original_supporting_low": low,
        "current_supporting_low": low,
        "contradiction": None,
        "runtime_code_identity_sha256": "b" * 64,
    }
    if scenario == "invalidated":
        value["contradiction"] = {
            "event": "CHOCH",
            "direction": "DOWN",
            "prior_trend": "UPTREND",
            "event_session": "2026-08-27",
            "pivot_session": low["pivot_session"],
            "pivot_confirmation_session": low["pivot_confirmation_session"],
            "pivot_identity_sha256": low["pivot_identity_sha256"],
        }
    return value


def _sealed_invalidation(value):
    value = dict(value)
    value.pop("result_identity_sha256", None)
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    value["result_identity_sha256"] = hashlib.sha256(raw).hexdigest()
    return json.dumps(value).encode()


def test_installed_invalidation_gate_probes_sdk_cli_and_three_outcomes(
    monkeypatch, tmp_path
):
    api = load(monkeypatch)
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        scenario = args[-1]
        return subprocess.CompletedProcess(
            args,
            1 if scenario == "unknown" else 0,
            _sealed_invalidation(_invalidation_output(scenario)),
            b"SYNTHETIC: not current market data.\n",
        )

    monkeypatch.setattr(api, "_run", run)
    python = tmp_path / "venv/bin/python"
    outcomes = api._verify_installed_invalidation(python, tmp_path)
    assert set(outcomes) == {"invalidated", "no-contradiction", "unknown"}
    for args, kwargs in calls:
        assert args[:3] == [str(python), "-I", "-c"]
        assert (
            "setup_invalidation as sdk" in args[3]
            and "setup_invalidation_cli as cli" in args[3]
        )
        assert "is_relative_to" in args[3] and "sys.prefix" in args[3]
        assert kwargs["cwd"] == tmp_path
        assert (
            "PYTHONPATH" not in kwargs["env"]
            and "BHARATSTOCK_API_KEY" not in kwargs["env"]
        )


@pytest.mark.parametrize(
    "failure",
    [
        "status",
        "exit",
        "leak",
        "digest",
        "contract",
        "criterion",
        "anchor",
        "later",
        "direction",
        "missing-witness",
        "fabricated-witness",
    ],
)
def test_installed_invalidation_rejects_wrong_evidence(monkeypatch, tmp_path, failure):
    api = load(monkeypatch)

    def run(args, **kwargs):
        scenario = args[-1]
        value = _invalidation_output(scenario)
        mutations = {
            "status": (("status",), "VALID"),
            "leak": (("close",), 89),
            "contract": (("contract_version",), "wrong"),
            "criterion": (("criterion",), "ANY_OPPOSITE_EVENT"),
            "anchor": (("contradiction", "pivot_session"), "2026-08-18"),
            "later": (("contradiction", "event_session"), "2026-08-26"),
            "direction": (("contradiction", "direction"), "UP"),
            "missing-witness": (("contradiction",), None),
            "fabricated-witness": (("contradiction",), {}),
        }
        if failure in mutations and (
            failure != "fabricated-witness" or scenario == "no-contradiction"
        ):
            keys, replacement = mutations[failure]
            target = value
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = replacement
        raw = _sealed_invalidation(value)
        if failure == "digest":
            parsed = json.loads(raw)
            parsed["result_identity_sha256"] = "a" * 64
            raw = json.dumps(parsed).encode()
        return subprocess.CompletedProcess(
            args,
            2 if failure == "exit" else 1 if scenario == "unknown" else 0,
            raw,
            b"SYNTHETIC: not current market data.\n",
        )

    monkeypatch.setattr(api, "_run", run)
    with pytest.raises(RuntimeError, match="invalidation"):
        api._verify_installed_invalidation(tmp_path / "venv/bin/python", tmp_path)


def _evidence_output(scenario):
    age = _age_output("same-event" if scenario == "invalidated" else scenario)
    current = age["current"]
    previous = age["previous"]
    continuity = {
        "contract_version": "causal-setup-event-continuity@v1",
        "criterion": "LATEST_COMPLETED_UPWARD_BOS@v1",
        "status": {
            "same-event": "SAME_EVENT",
            "invalidated": "SAME_EVENT",
            "replay": "REPLAY",
            "unknown": "UNKNOWN",
        }[scenario],
        "runtime_code_identity_sha256": "b" * 64,
        "previous_observation_identity_sha256": "f" * 64,
        "current_observation_identity_sha256": "a" * 64,
        "previous": previous,
        "current": current,
    }
    continuity = json.loads(_sealed_age(continuity))
    invalidation = _invalidation_output(
        "invalidated"
        if scenario == "invalidated"
        else "unknown"
        if scenario == "unknown"
        else "no-contradiction"
    )
    if scenario == "replay":
        invalidation["status"] = "REPLAY"
    for key in (
        "previous_observation_identity_sha256",
        "current_observation_identity_sha256",
        "previous",
        "current",
    ):
        invalidation[key] = continuity[key]
    for value in (age, invalidation):
        value["continuity_identity_sha256"] = continuity["result_identity_sha256"]
    age = json.loads(_sealed_age(age))
    invalidation = json.loads(_sealed_age(invalidation))
    return {
        "contract_version": "causal-setup-evidence@v1",
        "criterion": "LATEST_COMPLETED_UPWARD_BOS@v1",
        "runtime_code_identity_sha256": "b" * 64,
        "previous_observation_identity_sha256": "f" * 64,
        "current_observation_identity_sha256": "a" * 64,
        "continuity": continuity,
        "invalidation": invalidation,
        "age": age,
        "limitations": ["No eligibility."],
    }


def test_installed_evidence_checks_isolated_imports_and_coherent_four_outcomes(
    monkeypatch, tmp_path
):
    api = load(monkeypatch)
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            args,
            1 if args[-1] == "unknown" else 0,
            _sealed_age(_evidence_output(args[-1])),
            b"SYNTHETIC: not current market data.\n",
        )

    monkeypatch.setattr(api, "_run", run)
    result = api._verify_installed_evidence(tmp_path / "venv/bin/python", tmp_path)
    assert set(result) == {"same-event", "invalidated", "replay", "unknown"}
    assert result["invalidated"]["invalidation_status"] == "INVALIDATED"
    assert result["invalidated"]["completed_sessions_elapsed"] == 1
    for args, kwargs in calls:
        assert args[1:3] == ["-I", "-c"]
        assert (
            "setup_evidence as sdk" in args[3]
            and "setup_evidence_cli as cli" in args[3]
        )
        assert "sys.prefix" in args[3] and "is_relative_to" in args[3]
        assert (
            kwargs["cwd"] == tmp_path
            and "PYTHONPATH" not in kwargs["env"]
            and "BHARATSTOCK_API_KEY" not in kwargs["env"]
        )


@pytest.mark.parametrize(
    "failure",
    [
        "pair",
        "projection",
        "continuity",
        "nested-digest",
        "top-digest",
        "count",
        "bool",
        "status",
        "exit",
        "noncanonical",
        "leak",
        "invented-unknown",
        "aggregate",
        "witness",
    ],
)
def test_installed_evidence_rejects_plausible_wrong_or_mixed_reports(
    monkeypatch, tmp_path, failure
):
    api = load(monkeypatch)

    def run(args, **kwargs):
        scenario = args[-1]
        value = _evidence_output(scenario)
        mutations = {
            "pair": ("age", "current_observation_identity_sha256", "0" * 64),
            "projection": ("age", "current", {"status": "MATCH"}),
            "continuity": ("age", "continuity_identity_sha256", "0" * 64),
            "count": ("age", "completed_sessions_elapsed", 2),
            "bool": ("age", "completed_sessions_elapsed", True),
            "status": ("invalidation", "status", "VALID"),
        }
        if failure in mutations:
            component, field, replacement = mutations[failure]
            value[component][field] = replacement
        envelope_mutations = {"leak": ("price", 134), "aggregate": ("status", "ACTIVE")}
        if failure in envelope_mutations:
            field, replacement = envelope_mutations[failure]
            value[field] = replacement
        if failure == "invented-unknown" and scenario == "unknown":
            value["age"]["completed_sessions_elapsed"] = 0
        if failure == "witness" and scenario == "invalidated":
            value["invalidation"]["contradiction"] = None
        for name in ("age", "invalidation"):
            value[name] = json.loads(_sealed_age(value[name]))
        if failure == "nested-digest":
            value["age"]["result_identity_sha256"] = "0" * 64
        raw = _sealed_age(value)
        if failure == "top-digest":
            raw = raw.replace(
                b'"result_identity_sha256":', b'"bad_result_identity_sha256":'
            )
        if failure == "noncanonical":
            raw = json.dumps(json.loads(raw), indent=2).encode()
        return subprocess.CompletedProcess(
            args,
            2 if failure == "exit" else 1 if scenario == "unknown" else 0,
            raw,
            b"SYNTHETIC: not current market data.\n",
        )

    monkeypatch.setattr(api, "_run", run)
    with pytest.raises(RuntimeError, match="installed evidence"):
        api._verify_installed_evidence(tmp_path / "venv/bin/python", tmp_path)


def _interpretation_output(scenario):
    evidence = json.loads(
        _sealed_age(
            _evidence_output("same-event" if scenario == "no-trade" else scenario)
        )
    )
    facts = {
        name: {
            "result_identity_sha256": evidence[name]["result_identity_sha256"],
            "status": evidence[name]["status"],
        }
        for name in ("continuity", "invalidation", "age")
    }
    facts["age"]["completed_sessions_elapsed"] = evidence["age"][
        "completed_sessions_elapsed"
    ]
    response = {
        "schema": "external-setup-interpretation-request@v1",
        "evidence_identity_sha256": evidence["result_identity_sha256"],
        "disposition": "NO_TRADE" if scenario == "no-trade" else "RESEARCH_ONLY",
        "explanation": "Caller-authored synthetic research posture; facts unchanged, narrative accuracy and eligibility unassessed.",
        "facts": facts,
    }
    return {
        "contract_version": "external-setup-interpretation-check@v1",
        "evidence": evidence,
        "external_response": response,
        "external_response_identity_sha256": hashlib.sha256(
            (
                json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        ).hexdigest(),
        "runtime_code_identity_sha256": "b" * 64,
        "verification": "STRUCTURED_BINDING_ONLY",
        "external_authorship": "CALLER_SUPPLIED_NOT_AUTHENTICATED",
        "explanation_accuracy": "NOT_ASSESSED",
        "actionable_recommendation": "NOT_ASSESSED",
        "eligibility": "NOT_ASSESSED",
        "effectiveness": "NOT_ASSESSED",
        "limitations": ["Only factual binding; no trade authorization."],
    }


def test_installed_interpretation_probes_six_isolated_sdk_cli_cases(
    monkeypatch, tmp_path
):
    api = load(monkeypatch)
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        scenario = args[-1]
        return subprocess.CompletedProcess(
            args,
            2 if scenario == "false-claim" else 1 if scenario == "unknown" else 0,
            b""
            if scenario == "false-claim"
            else _sealed_age(_interpretation_output(scenario)),
            b"SYNTHETIC CALLER-AUTHORED: not current market data.\n"
            + (b"setup_interpretation_failed\n" if scenario == "false-claim" else b""),
        )

    monkeypatch.setattr(api, "_run", run)
    outcomes = api._verify_installed_interpretation(
        tmp_path / "venv/bin/python", tmp_path
    )
    assert set(outcomes) == {
        "same-event",
        "invalidated",
        "replay",
        "unknown",
        "no-trade",
        "false-claim",
    }
    assert outcomes["false-claim"]["exit"] == 2
    assert outcomes["invalidated"]["invalidation_status"] == "INVALIDATED"
    for args, kwargs in calls:
        assert args[1:3] == ["-I", "-c"]
        assert (
            "setup_interpretation as sdk" in args[3]
            and "setup_interpretation_cli as cli" in args[3]
        )
        assert "sys.prefix" in args[3] and "is_relative_to" in args[3]
        assert kwargs["cwd"] == tmp_path
        assert (
            "PYTHONPATH" not in kwargs["env"]
            and "BHARATSTOCK_API_KEY" not in kwargs["env"]
        )


@pytest.mark.parametrize(
    "failure",
    [
        "reference",
        "claim",
        "omission",
        "bool",
        "label",
        "authorship",
        "actionable",
        "digest",
        "narrative",
        "exit",
        "false-claim",
        "partial",
        "noncanonical",
        "overflow",
        "private-path",
    ],
)
def test_installed_interpretation_rejects_plausible_wrong_reports(
    monkeypatch, tmp_path, failure
):
    api = load(monkeypatch)

    def run(args, **kwargs):
        scenario = args[-1]
        code = 2 if scenario == "false-claim" else 1 if scenario == "unknown" else 0
        stderr = b"SYNTHETIC CALLER-AUTHORED: not current market data.\n"
        if scenario == "false-claim":
            return subprocess.CompletedProcess(
                args,
                0 if failure == "false-claim" else code,
                b"partial" if failure == "partial" else b"",
                stderr + b"setup_interpretation_failed\n",
            )
        value = _interpretation_output(scenario)
        mutations = {
            "reference": (("external_response", "evidence_identity_sha256"), "0" * 64),
            "claim": (
                ("external_response", "facts", "invalidation", "status"),
                "ACTIVE",
            ),
            "bool": (
                ("external_response", "facts", "age", "completed_sessions_elapsed"),
                True,
            ),
            "label": (("verification",), "AI_APPROVED"),
            "authorship": (("external_authorship",), "VERIFIED"),
            "actionable": (("external_response", "disposition"), "BUY"),
            "narrative": (("external_response", "explanation"), "APPROVED"),
            "private-path": (("external_response", "explanation"), str(tmp_path)),
        }
        if failure in mutations:
            keys, replacement = mutations[failure]
            target = value
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = replacement
        elif failure == "omission":
            del value["external_response"]["facts"]["age"]
        response = value["external_response"]
        value["external_response_identity_sha256"] = hashlib.sha256(
            (
                json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        ).hexdigest()
        raw = _sealed_age(value)
        if failure == "digest":
            value["result_identity_sha256"] = "0" * 64
            raw = json.dumps(value).encode()
        elif failure == "noncanonical":
            raw = json.dumps(value, indent=2).encode()
        elif failure == "overflow":
            raw += b" " * (1024 * 1024)
        return subprocess.CompletedProcess(
            args, 2 if failure == "exit" else code, raw, stderr
        )

    monkeypatch.setattr(api, "_run", run)
    with pytest.raises(RuntimeError, match="installed interpretation"):
        api._verify_installed_interpretation(tmp_path / "venv/bin/python", tmp_path)


def _level_output(scenario):
    observed = scenario in ("above", "at", "below")
    candidate = {
        "event_session": "2026-08-25",
        "pivot_session": "2026-08-19",
        "pivot_confirmation_session": "2026-08-21",
        "event_identity_sha256": "a" * 64,
        "pivot_identity_sha256": "b" * 64,
    }
    return {
        "contract_version": "causal-setup-level@v1",
        "criterion": "LATEST_COMPLETED_CLOSE_VS_ORIGINAL_BROKEN_HIGH@v1",
        "runtime_code_identity_sha256": "c" * 64,
        "previous_observation_identity_sha256": "d" * 64,
        "current_observation_identity_sha256": "d" * 64
        if scenario == "replay"
        else "e" * 64,
        "continuity_identity_sha256": "f" * 64,
        "continuity_status": "SAME_EVENT" if observed else scenario.upper(),
        "status": "OBSERVED" if observed else scenario.upper(),
        "reason": "LATEST_COMPLETED_CLOSE_COMPARED_WITH_ORIGINAL_BROKEN_HIGH"
        if observed
        else "IDENTICAL_ADMITTED_OBSERVATION"
        if scenario == "replay"
        else "CURRENT_STRUCTURE_UNKNOWN",
        "relation": scenario.upper() if observed else None,
        "previous": {
            "candidate": candidate,
            "status": "MATCH",
            "session": "2026-08-25",
        },
        "current": {
            "status": "NO_MATCH"
            if observed
            else "MATCH"
            if scenario == "replay"
            else "UNKNOWN",
            "session": "2026-08-26" if observed else "2026-08-25",
        },
        "witness": {
            "original_event_session": candidate["event_session"],
            "original_high_pivot_session": candidate["pivot_session"],
            "original_high_confirmation_session": candidate[
                "pivot_confirmation_session"
            ],
            "original_event_identity_sha256": candidate["event_identity_sha256"],
            "original_high_identity_sha256": candidate["pivot_identity_sha256"],
            "represented_event_identity_sha256": "1" * 64,
            "represented_high_identity_sha256": "2" * 64,
            "current_completed_session": "2026-08-26",
            "current_bar_identity_sha256": "3" * 64,
        }
        if observed
        else None,
        "limitations": ["Descriptive level only; no eligibility."],
    }


def test_installed_level_gate_probes_five_isolated_actual_sdk_cli_cases(
    monkeypatch, tmp_path
):
    api = load(monkeypatch)
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            args,
            1 if args[-1] == "unknown" else 0,
            _sealed_age(_level_output(args[-1])),
            b"SYNTHETIC: not current market data.\n",
        )

    monkeypatch.setattr(api, "_run", run)
    method = getattr(api, "_verify_installed_level", api._verify_installed_age)
    outcomes = method(tmp_path / "venv/bin/python", tmp_path)
    assert set(outcomes) == {"above", "at", "below", "replay", "unknown"}
    for args, kwargs in calls:
        assert args[1:3] == ["-I", "-c"]
        assert "setup_level as sdk" in args[3] and "setup_level_cli as cli" in args[3]
        assert "sys.prefix" in args[3] and "is_relative_to" in args[3]
        assert (
            kwargs["cwd"] == tmp_path
            and "PYTHONPATH" not in kwargs["env"]
            and "BHARATSTOCK_API_KEY" not in kwargs["env"]
        )


@pytest.mark.parametrize(
    "failure",
    [
        "relation",
        "status",
        "reason",
        "criterion",
        "contract",
        "extra",
        "witness",
        "anchor",
        "endpoint",
        "confirmation",
        "digest",
        "runtime",
        "replay",
        "unknown",
        "exit",
        "noncanonical",
        "overflow",
        "private-path",
        "partial",
    ],
)
def test_installed_level_gate_rejects_resealed_wrong_reports(  # noqa: C901 - closed adversarial matrix
    monkeypatch, tmp_path, failure
):
    api = load(monkeypatch)

    def run(args, **kwargs):  # noqa: C901 - closed adversarial matrix
        scenario = args[-1]
        value = _level_output(scenario)
        changed = {
            "relation": ("relation", "AT"),
            "status": ("status", "VALID"),
            "reason": ("reason", "CONFIRMED"),
            "criterion": ("criterion", "RETEST"),
            "contract": ("contract_version", "causal-setup-level@v2"),
            "extra": ("price", 130),
            "runtime": ("runtime_code_identity_sha256", "invalid"),
        }
        if failure in changed:
            key, replacement = changed[failure]
            value[key] = replacement
        if failure == "witness" and value["witness"]:
            value["witness"]["unexpected"] = "sealed"
        if failure == "anchor" and value["witness"]:
            value["witness"]["original_high_identity_sha256"] = "0" * 64
        if failure == "endpoint" and value["witness"]:
            value["witness"]["current_completed_session"] = "2026-08-25"
        if failure == "confirmation" and value["witness"]:
            value["witness"]["original_high_confirmation_session"] = "2026-08-26"
        if failure == "replay" and scenario == "replay":
            value["current_observation_identity_sha256"] = "0" * 64
        if failure == "unknown" and scenario == "unknown":
            value["witness"] = {}
        if failure == "private-path":
            value["limitations"] = [str(tmp_path)]
        raw = _sealed_age(value)
        if failure == "digest":
            value = json.loads(raw)
            value["result_identity_sha256"] = "0" * 64
            raw = (
                json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        if failure == "noncanonical":
            raw = json.dumps(json.loads(raw), indent=2).encode()
        if failure == "overflow":
            raw = b"x" * (1024 * 1024 + 1)
        if failure == "partial":
            raw = b"{"
        return subprocess.CompletedProcess(
            args,
            2 if failure == "exit" else 1 if scenario == "unknown" else 0,
            raw,
            b"SYNTHETIC: not current market data.\n",
        )

    monkeypatch.setattr(api, "_run", run)
    with pytest.raises(RuntimeError, match="installed level"):
        api._verify_installed_level(tmp_path / "venv/bin/python", tmp_path)


def _level_interpretation_v2_output(scenario):
    old_scenario = (
        "same-event"
        if scenario in ("above", "at", "below", "no-trade", "false-claim")
        else scenario
    )
    legacy = json.loads(_sealed_age(_evidence_output(old_scenario)))
    evidence = dict(legacy)
    evidence["contract_version"] = "causal-setup-evidence@v2"
    evidence["legacy_evidence_identity_sha256"] = legacy["result_identity_sha256"]
    level_scenario = {
        "invalidated": "below",
        "no-trade": "above",
        "false-claim": "above",
    }.get(scenario, scenario)
    level = _level_output(level_scenario)
    # Synthetic qualification data joins exact shared projection rows, then seals.
    previous, current = level["previous"], level["current"]
    for name in ("continuity", "invalidation", "age"):
        component = dict(evidence[name])
        component["previous"], component["current"] = previous, current
        if scenario == "replay":
            component["current_observation_identity_sha256"] = component[
                "previous_observation_identity_sha256"
            ]
        evidence[name] = json.loads(_sealed_age(component))
    for name in ("invalidation", "age"):
        evidence[name]["continuity_identity_sha256"] = evidence["continuity"][
            "result_identity_sha256"
        ]
        evidence[name] = json.loads(_sealed_age(evidence[name]))
    for key in (
        "previous_observation_identity_sha256",
        "current_observation_identity_sha256",
    ):
        evidence[key] = evidence["continuity"][key]
        level[key] = evidence[key]
    level["continuity_identity_sha256"] = evidence["continuity"][
        "result_identity_sha256"
    ]
    evidence["level"] = json.loads(_sealed_age(level))
    evidence = json.loads(_sealed_age(evidence))
    response = _interpretation_output(
        old_scenario
        if old_scenario != "same-event"
        else "no-trade"
        if scenario == "no-trade"
        else "same-event"
    )
    response["contract_version"] = "external-setup-interpretation-check@v2"
    response["evidence"] = evidence
    request = response["external_response"]
    request["schema"] = "external-setup-interpretation-request@v2"
    request["evidence_identity_sha256"] = evidence["result_identity_sha256"]
    request["facts"] = {
        name: {key: evidence[name][key] for key in ("result_identity_sha256", "status")}
        for name in ("continuity", "invalidation", "age", "level")
    }
    request["facts"]["age"]["completed_sessions_elapsed"] = evidence["age"][
        "completed_sessions_elapsed"
    ]
    request["facts"]["level"]["relation"] = level["relation"]
    response["external_response_identity_sha256"] = hashlib.sha256(
        (json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    return response


def test_installed_level_interpretation_v2_probes_eight_isolated_paths(
    monkeypatch, tmp_path
):
    api = load(monkeypatch)
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        scenario = args[-1]
        return subprocess.CompletedProcess(
            args,
            2 if scenario == "false-claim" else 1 if scenario == "unknown" else 0,
            b""
            if scenario == "false-claim"
            else _sealed_age(_level_interpretation_v2_output(scenario)),
            b"SYNTHETIC CALLER-AUTHORED: not current market data.\n"
            + (b"setup_interpretation_failed\n" if scenario == "false-claim" else b""),
        )

    monkeypatch.setattr(api, "_run", run)
    result = api._verify_installed_level_interpretation_v2(
        tmp_path / "venv/bin/python", tmp_path
    )
    assert set(result) == {
        "above",
        "at",
        "below",
        "invalidated",
        "replay",
        "unknown",
        "no-trade",
        "false-claim",
    }
    assert result["below"]["relation"] == "BELOW"
    assert result["invalidated"]["invalidation_status"] == "INVALIDATED"
    assert result["false-claim"]["rejected"]
    for args, kwargs in calls:
        assert args[1:3] == ["-I", "-c"]
        assert "setup_interpretation_v2 as sdk" in args[3] and "sys.prefix" in args[3]
        assert kwargs["cwd"] == tmp_path and "PYTHONPATH" not in kwargs["env"]


@pytest.mark.parametrize(
    "mutation",
    [
        "relation",
        "component-pair",
        "component-digest",
        "claim",
        "legacy-hash",
        "schema",
        "version",
        "raw-price",
        "noncanonical",
        "overflow",
        "false-accepted",
        "exit",
    ],
)
def test_installed_level_interpretation_v2_rejects_wrong_resealed_reports(  # noqa: C901 - closed adversarial matrix
    monkeypatch, tmp_path, mutation
):
    api = load(monkeypatch)

    def run(args, **kwargs):  # noqa: C901 - closed adversarial matrix
        scenario = args[-1]
        value = _level_interpretation_v2_output(
            "above" if scenario == "false-claim" else scenario
        )
        level = value["evidence"]["level"]
        if mutation == "relation":
            level["relation"] = "AT"
        elif mutation == "component-pair":
            level["current_observation_identity_sha256"] = "0" * 64
        elif mutation == "component-digest":
            level["result_identity_sha256"] = "0" * 64
        elif mutation == "claim":
            value["external_response"]["facts"]["level"]["relation"] = "BELOW"
        elif mutation == "legacy-hash":
            value["evidence"]["legacy_evidence_identity_sha256"] = "wrong"
        elif mutation == "schema":
            value["external_response"]["schema"] = (
                "external-setup-interpretation-request@v1"
            )
        elif mutation == "version":
            value["contract_version"] = "external-setup-interpretation-check@v1"
        elif mutation == "raw-price":
            value["price"] = 130
        if mutation != "component-digest":
            value["evidence"]["level"] = json.loads(_sealed_age(level))
        value["evidence"] = json.loads(_sealed_age(value["evidence"]))
        raw = _sealed_age(value)
        if mutation == "noncanonical":
            raw = json.dumps(json.loads(raw), indent=2).encode()
        elif mutation == "overflow":
            raw = b"x" * (1024 * 1024 + 1)
        code = 2 if scenario == "false-claim" else 1 if scenario == "unknown" else 0
        if mutation == "exit":
            code = 3
        if scenario == "false-claim" and mutation != "false-accepted":
            raw = b""
        return subprocess.CompletedProcess(
            args,
            code,
            raw,
            b"SYNTHETIC CALLER-AUTHORED: not current market data.\n"
            + (b"setup_interpretation_failed\n" if scenario == "false-claim" else b""),
        )

    monkeypatch.setattr(api, "_run", run)
    with pytest.raises(RuntimeError):
        api._verify_installed_level_interpretation_v2(
            tmp_path / "venv/bin/python", tmp_path
        )


def _level_range_output(scenario):
    value = _level_output(
        "above"
        if scenario in ("contains", "above", "below", "low-equal", "high-equal")
        else scenario
    )
    value["contract_version"] = "causal-setup-level-range@v1"
    value["criterion"] = "LATEST_COMPLETED_RANGE_VS_ORIGINAL_BROKEN_HIGH@v1"
    value["level_identity_sha256"] = "d" * 64
    value.pop("relation")
    value["range_relation"] = {
        "contains": "CONTAINS_LEVEL",
        "above": "ENTIRELY_ABOVE",
        "below": "ENTIRELY_BELOW",
        "low-equal": "CONTAINS_LEVEL",
        "high-equal": "CONTAINS_LEVEL",
    }.get(scenario)
    if scenario not in ("replay", "unknown"):
        value["reason"] = "LATEST_COMPLETED_RANGE_COMPARED_WITH_ORIGINAL_BROKEN_HIGH"
    return value


def test_installed_level_range_gate_seven_isolated_actual_sdk_cli_cases(
    monkeypatch, tmp_path
):
    api = load(monkeypatch)
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            args,
            1 if args[-1] == "unknown" else 0,
            _sealed_age(_level_range_output(args[-1])),
            b"SYNTHETIC: not current market data.\n",
        )

    monkeypatch.setattr(api, "_run", run)
    result = api._verify_installed_level_range(tmp_path / "venv/bin/python", tmp_path)
    assert set(result) == {
        "contains",
        "above",
        "below",
        "low-equal",
        "high-equal",
        "replay",
        "unknown",
    }
    for args, kwargs in calls:
        assert (
            args[1:3] == ["-I", "-c"]
            and "setup_level_range as sdk" in args[3]
            and "setup_level_range_cli as cli" in args[3]
        )
        assert "sys.prefix" in args[3] and "is_relative_to" in args[3]
        assert (
            kwargs["cwd"] == tmp_path
            and "PYTHONPATH" not in kwargs["env"]
            and "BHARATSTOCK_API_KEY" not in kwargs["env"]
        )


@pytest.mark.parametrize(
    "failure",
    [
        "relation",
        "status",
        "reason",
        "contract",
        "criterion",
        "extra",
        "runtime",
        "level",
        "witness",
        "anchor",
        "endpoint",
        "digest",
        "replay",
        "unknown",
        "exit",
        "noncanonical",
        "overflow",
        "partial",
        "private-path",
    ],
)
def test_installed_level_range_gate_rejects_resealed_wrong_reports(  # noqa: C901 - closed adversarial matrix
    monkeypatch, tmp_path, failure
):
    api = load(monkeypatch)

    def run(args, **kwargs):  # noqa: C901 - explicit adversarial acceptance matrix
        scenario = args[-1]
        value = _level_range_output(scenario)
        fields = {
            "relation": ("range_relation", "AT"),
            "status": ("status", "VALID"),
            "reason": ("reason", "RETEST_CONFIRMED"),
            "contract": ("contract_version", "causal-setup-level@v1"),
            "criterion": ("criterion", "RETEST"),
            "extra": ("price", 130),
            "runtime": ("runtime_code_identity_sha256", "invalid"),
            "level": ("level_identity_sha256", False),
        }
        if failure in fields:
            key, changed = fields[failure]
            value[key] = changed
        if failure == "witness" and value["witness"]:
            value["witness"]["extra"] = True
        if failure == "anchor" and value["witness"]:
            value["witness"]["original_high_identity_sha256"] = "0" * 64
        if failure == "endpoint" and value["witness"]:
            value["witness"]["current_completed_session"] = "2026-08-25"
        if failure == "replay" and scenario == "replay":
            value["current_observation_identity_sha256"] = "0" * 64
        if failure == "unknown" and scenario == "unknown":
            value["range_relation"] = "CONTAINS_LEVEL"
        if failure == "private-path":
            value["limitations"] = [str(tmp_path)]
        raw = _sealed_age(value)
        if failure == "digest":
            value = json.loads(raw)
            value["result_identity_sha256"] = "0" * 64
            raw = (
                json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        if failure == "noncanonical":
            raw = json.dumps(json.loads(raw), indent=2).encode()
        if failure == "overflow":
            raw = b"x" * (1024 * 1024 + 1)
        if failure == "partial":
            raw = b"{"
        return subprocess.CompletedProcess(
            args,
            2 if failure == "exit" else 1 if scenario == "unknown" else 0,
            raw,
            b"SYNTHETIC: not current market data.\n",
        )

    monkeypatch.setattr(api, "_run", run)
    with pytest.raises(RuntimeError, match="installed level range"):
        api._verify_installed_level_range(tmp_path / "venv/bin/python", tmp_path)
