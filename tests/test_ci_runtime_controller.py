"""Exercise disposable controller orchestration without providers or host effects."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_self_hosted_ci.sh"


def fixture_tools(
    tmp_path, runtime, *, copy_failure=False, engine_failure=False, failure=""
):
    binary = tmp_path / "bin"
    binary.mkdir()
    log = tmp_path / "calls.jsonl"
    engine = binary / runtime
    engine.write_text(f"""#!{sys.executable}
import json,os,signal,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ["PROBE_LOG"],"a") as f:f.write(json.dumps([Path(sys.argv[0]).name,*args])+"\\n")
if args[0]=="info":
 print('{{"host":{{"security":{{"rootless":true}}}}}}');sys.exit({int(engine_failure)})
if args[0]=="cp":sys.exit({int(copy_failure)})
if args[0]=="version":print('{{"Client":{{"Version":"fixture"}}}}')
if args[0]=="run" and "--name" in args:
 name=args[args.index("--name")+1]
 if name.endswith("-{failure}"):sys.exit(19)
 if name.endswith("-runner") and {failure!r} in {{"SIGINT","SIGTERM"}}:
  os.kill(os.getppid(),getattr(signal,{failure!r}))
""")
    engine.chmod(0o700)
    gh = binary / "gh"
    gh.write_text(f"""#!{sys.executable}
import json,sys,os
from pathlib import Path
if "DELETE" in sys.argv:Path(os.environ["PROBE_LOG"]+".unregistered").touch()
if "POST" in sys.argv:
 if {failure!r}=="registration":sys.exit(23)
 print(json.dumps({{"runner":{{"id":42}},"encoded_jit_config":"synthetic-registration"}}))
""")
    gh.chmod(0o700)
    env = dict(
        os.environ,
        PATH=str(binary) + ":" + os.environ["PATH"],
        SWING_CONTAINER_RUNTIME=runtime,
        SWING_CI_STATE=str(tmp_path / "state"),
        SWING_CI_RUNNER_IMAGE="sha256:" + "a" * 64,
        PROBE_LOG=str(log),
    )
    return env, log


@pytest.mark.parametrize("runtime", ["podman", "docker"])
def test_selected_engine_owns_entire_job_and_scoped_cleanup(tmp_path, runtime):
    env, log = fixture_tools(tmp_path, runtime)
    result = subprocess.run(  # noqa: S603 -- fixed controller with synthetic tools
        ["/bin/bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert all(call[0] == runtime for call in calls)
    assert calls[0][1] == "info"
    assert any(call[1:3] == ["volume", "rm"] for call in calls)
    assert not any("prune" in call for call in calls)
    jobs = list((tmp_path / "state/jobs").iterdir())
    assert len(jobs) == 1
    assert not (jobs[0] / "jit").exists()
    if runtime == "podman":
        runs = [call for call in calls if call[1] == "run"]
        assert all("--userns=keep-id:uid=1000,gid=1000" in call for call in runs)
        assert any("CONTAINER_HOST=unix:///ci/podman.sock" in call for call in runs)
        assert not any("DOCKER_HOST=tcp://engine:2375" in call for call in runs)
    assert json.loads((jobs[0] / "runtime.json").read_text())["runtime"] == runtime


def test_failed_preflight_does_not_create_resources(tmp_path):
    env, log = fixture_tools(tmp_path, "podman", engine_failure=True)
    result = subprocess.run(  # noqa: S603 -- fixed controller with synthetic tools
        ["/bin/bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode != 0
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(calls) == 1 and calls[0][1] == "info"
    assert not (tmp_path / "state").exists()


def test_receipt_failure_preserves_job_resources(tmp_path):
    env, log = fixture_tools(tmp_path, "podman", copy_failure=True)
    result = subprocess.run(  # noqa: S603 -- fixed controller with synthetic tools
        ["/bin/bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode != 0
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert any(call[1] == "cp" for call in calls)
    job = next((tmp_path / "state/jobs").iterdir())
    assert not (job / "jit").exists()
    assert not (job / "registration.json").exists()
    assert Path(str(log) + ".unregistered").exists()
    assert (job / "controller-exit").read_text().strip() == "1"
    assert not any(
        call[1] == "rm" or call[1:3] in [["volume", "rm"], ["network", "rm"]]
        for call in calls
    )


@pytest.mark.parametrize("runtime", ["podman", "docker"])
@pytest.mark.parametrize(
    "failure", ["engine", "registration", "runner", "SIGINT", "SIGTERM"]
)
def test_failed_job_never_switches_engine_and_cleans_own_resources(
    tmp_path, runtime, failure
):
    env, log = fixture_tools(tmp_path, runtime, failure=failure)
    result = subprocess.run(  # noqa: S603 -- fixed controller with synthetic tools
        ["/bin/bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == {"registration": 23, "SIGINT": 130, "SIGTERM": 143}.get(
        failure, 19
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert all(call[0] == runtime for call in calls)
    created = next(call[3] for call in calls if call[1:3] == ["volume", "create"])
    assert any(call[1:] == ["volume", "rm", created] for call in calls)
    assert not any("prune" in call for call in calls)
    job = next((tmp_path / "state/jobs").iterdir())
    assert int((job / "controller-exit").read_text()) == result.returncode
    assert not (job / "jit").exists()


def test_hanging_copy_is_bounded_and_still_erases_registration(tmp_path):
    env, log = fixture_tools(tmp_path, "podman")
    binary = tmp_path / "bin"
    engine = binary / "podman"
    engine.write_text(
        engine.read_text().replace(
            'if args[0]=="cp":sys.exit(0)',
            'if args[0]=="cp":\n import time;time.sleep(60)',
        )
    )
    deadline = binary / "timeout"
    deadline.write_text(f"""#!{sys.executable}
import os,sys
assert sys.argv[1]=="--kill-after=2s"
assert 0 < int(sys.argv[2].removesuffix("s")) <= 20
os.execv("/usr/bin/timeout", ["timeout","--kill-after=0.1s","0.2s",*sys.argv[3:]])
""")
    deadline.chmod(0o700)
    process = subprocess.Popen(  # noqa: S603 -- synthetic tools, isolated process group
        ["/bin/bash", str(SCRIPT)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        _, stderr = process.communicate(timeout=4)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=2)
    assert process.returncode == 1, stderr
    job = next((tmp_path / "state/jobs").iterdir())
    assert not (job / "jit").exists()
    assert Path(str(log) + ".unregistered").exists()
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert not any(call[1] == "rm" or call[1:3] == ["volume", "rm"] for call in calls)


def test_removal_failure_does_not_skip_credential_cleanup(tmp_path):
    env, log = fixture_tools(tmp_path, "podman")
    engine = tmp_path / "bin/podman"
    engine.write_text(engine.read_text() + '\nif args[0]=="rm":sys.exit(21)\n')
    result = subprocess.run(  # noqa: S603 -- isolated synthetic engine
        ["/bin/bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 1
    job = next((tmp_path / "state/jobs").iterdir())
    assert not (job / "jit").exists()
    assert Path(str(log) + ".unregistered").exists()
    assert (job / "controller-exit").read_text().strip() == "1"


def test_engine_teardown_failure_cannot_report_success(tmp_path):
    env, log = fixture_tools(tmp_path, "podman")
    engine = tmp_path / "bin/podman"
    engine.write_text(
        engine.read_text()
        + '\nif args[0]=="rm" and any(a.endswith("-engine") for a in args):sys.exit(21)\n'
    )
    result = subprocess.run(  # noqa: S603 -- isolated synthetic engine
        ["/bin/bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 1
    job = next((tmp_path / "state/jobs").iterdir())
    assert (job / "controller-exit").read_text().strip() == "1"
    assert not (job / "jit").exists()
