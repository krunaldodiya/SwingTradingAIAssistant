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
