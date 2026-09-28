"""Build and challenge the Linux wheel/OCI distribution from one exact wheel.

Run after ``uv build``. The selected engine receives a temporary two-file context: the wheel
and hash-checked runtime requirements exported from the repository lock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import tomllib
import uuid
from pathlib import Path

from container_runtime import select_runtime

_RUNTIME: str | None = None
_PODMAN_ROOTLESS = False


def _engine() -> str:
    if _RUNTIME is None:
        raise RuntimeError("container engine must be selected before execution")
    return _RUNTIME


ROOT = Path(__file__).resolve().parents[1]
DEMO = "swing_trading_ai_assistant._examples.single_stock_research_demo"
EXPECTED_SYNTHETIC_IDENTITY = (
    "19fbcbc4ced367dccda69631b7793546cfa2d2aaa330153ba030d7edb5941ed2"
)
MUTABLE_SOURCE = (
    ROOT / "src/swing_trading_ai_assistant/market_structure/current_live.py"
)
IMAGE_SOURCE = (
    "/opt/app/lib/python3.11/site-packages/"
    "swing_trading_ai_assistant/market_structure/current_live.py"
)


def _run(
    args: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603 - bounded fixed local tools and arguments
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _require_success(result: subprocess.CompletedProcess[bytes], label: str) -> None:
    if result.returncode:
        raise RuntimeError(
            f"{label} failed ({result.returncode}): "
            f"{result.stderr.decode(errors='replace')[-2500:]}"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _container(
    image: str, *, entrypoint: str | None = None, user: str = "10001:10001"
) -> list[str]:
    command = [
        _engine(),
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m",  # noqa: S108 - isolated container tmpfs
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
    ]
    command.extend(("--user", user))
    if _PODMAN_ROOTLESS:
        command.append("--userns=keep-id")
    if entrypoint is not None:
        command.extend(("--entrypoint", entrypoint))
    return [*command, image]


def _research_request(root: str) -> list[str]:
    return [
        "research-current",
        "--symbol",
        "PNB",
        "--storage-root",
        root,
        "--contract-version",
        "v2",
        "--question",
        "PRICE_BEHAVIOR",
        "--output",
        "json",
    ]


def _mounted_request(
    image: str,
    root: Path,
    *,
    user: str,
    readonly: bool = False,
    selected: str = "/data",
) -> subprocess.CompletedProcess[bytes]:
    mount = f"type=bind,src={root},dst=/data"
    if readonly:
        mount += ",readonly"
    command = _container(image, user=user)
    command[2:2] = ["--mount", mount]
    return _run([*command, *_research_request(selected)])


def _assert_storage_stop(result: subprocess.CompletedProcess[bytes]) -> None:
    if result.returncode != 1:
        raise RuntimeError("unsafe mounted root did not fail with exit 1")
    value = json.loads(result.stdout)
    if (value["status"], value["stage"], value["code"], value["packet"]) != (
        "UNAVAILABLE",
        "storage",
        "STORAGE_UNSAFE_OR_HELD",
        None,
    ):
        raise RuntimeError("unsafe mounted root escaped the storage gate")


def _verify_cli(
    image: str, python: Path, scratch: Path
) -> dict[str, dict[str, object]]:
    safe_env = {
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
    }
    native_help = _run(
        [str(python.parent / "market-data"), "--help"], cwd=scratch, env=safe_env
    )
    image_help = _run([*_container(image), "--help"])
    _require_success(native_help, "native CLI")
    _require_success(image_help, "container CLI")
    if native_help.stdout != image_help.stdout:
        raise RuntimeError("installed CLI help differs across runtimes")
    outcomes: dict[str, dict[str, object]] = {}
    for scenario, expected_exit in (("complete", 0), ("malformed", 2)):
        native = _run(
            [str(python), "-m", DEMO, "--scenario", scenario],
            cwd=scratch,
            env=safe_env,
        )
        container = _run(
            [
                *_container(image, entrypoint="python"),
                "-m",
                DEMO,
                "--scenario",
                scenario,
            ]
        )
        if (
            native.returncode != expected_exit
            or container.returncode != expected_exit
            or native.stdout != container.stdout
            or native.stderr != container.stderr
        ):
            raise RuntimeError(f"native/container {scenario} result diverged")
        outcomes[scenario] = {
            "exit": expected_exit,
            "stdout_sha256": hashlib.sha256(native.stdout).hexdigest(),
        }
        if scenario == "complete":
            value = json.loads(native.stdout)
            identity = value["packet"]["result_identity_sha256"]
            if value["status"] != "READY" or identity != EXPECTED_SYNTHETIC_IDENTITY:
                raise RuntimeError("positive research fixture identity changed")
            outcomes[scenario]["result_identity_sha256"] = identity
        elif native.stdout or b"request_invalid" not in native.stderr:
            raise RuntimeError("malformed fixture returned plausible research")
    return outcomes


def _verify_mounts(image: str, scratch: Path) -> None:
    private = scratch / "private"
    private.mkdir(mode=0o700)
    mapped_user = f"{os.getuid()}:{os.getgid()}"
    admitted = _mounted_request(image, private, user=mapped_user)
    admitted_value = json.loads(admitted.stdout)
    if (
        admitted.returncode != 1
        or admitted_value["stage"] != "calendar"
        or admitted_value["code"] != "HTTP_FAILURE"
    ):
        raise RuntimeError("owner-mapped private volume was not admitted")
    sentinel = private / "preexisting-owner-data"
    sentinel.write_text("unchanged synthetic marker\n")
    wrong_user = f"{os.getuid() + 1}:{os.getgid() + 1}"
    _assert_storage_stop(_mounted_request(image, private, user=wrong_user))
    broad = scratch / "broad"
    broad.mkdir(mode=0o755)
    _assert_storage_stop(_mounted_request(image, broad, user=mapped_user))
    readonly = scratch / "readonly"
    readonly.mkdir(mode=0o700)
    _assert_storage_stop(
        _mounted_request(image, readonly, user=mapped_user, readonly=True)
    )
    child = private / "child"
    child.mkdir(mode=0o700)
    (private / "link").symlink_to("child", target_is_directory=True)
    _assert_storage_stop(
        _mounted_request(image, private, user=mapped_user, selected="/data/link")
    )
    if sentinel.read_text() != "unchanged synthetic marker\n":
        raise RuntimeError("mounted owner data was changed by the image")


def _verify_image_source(image: str, scratch: Path) -> None:
    tampered = scratch / "tampered.py"
    tampered.write_bytes(MUTABLE_SOURCE.read_bytes() + b"\n")
    substituted = _container(image)
    substituted[2:2] = [
        "--mount",
        f"type=bind,src={tampered},dst={IMAGE_SOURCE},readonly",
    ]
    changed = _run([*substituted, "--help"])
    if (
        changed.returncode == 0
        or changed.stdout
        or b"Market Structure runtime identity invalid" not in changed.stderr
    ):
        raise RuntimeError("altered image source produced a public CLI result")


def _verify_interrupted_build(build: list[str], image: str) -> None:
    interrupted_image = f"{image}-interrupted-{uuid.uuid4().hex[:8]}"
    interrupted_build = build.copy()
    interrupted_build[interrupted_build.index("--tag") + 1] = interrupted_image
    interrupted_build.insert(-1, "--no-cache")
    process = subprocess.Popen(  # noqa: S603 - fixed Docker command under review
        interrupted_build,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
        else:
            raise RuntimeError("build ended before interruption was exercised")
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
    if _run([_engine(), "image", "inspect", interrupted_image]).returncode == 0:
        raise RuntimeError("interrupted build published an image")


def _verify_interrupted_run(image: str) -> None:
    run_name = f"issue167-interrupted-{uuid.uuid4().hex[:8]}"
    run_command = [
        *_container(image, entrypoint="python")[:-1],
        "--name",
        run_name,
        image,
        "-c",
        "import time; time.sleep(30)",
    ]
    process = subprocess.Popen(  # noqa: S603 - fixed Docker command under review
        run_command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            running = _run(
                [_engine(), "inspect", run_name, "--format", "{{.State.Running}}"]
            )
            if running.returncode == 0 and running.stdout.strip() == b"true":
                break
            if process.poll() is not None:
                raise RuntimeError("container exited before interruption")
            time.sleep(0.1)
        else:
            raise RuntimeError("container never became ready for interruption")
        _require_success(
            _run([_engine(), "kill", "--signal=KILL", run_name]),
            "container interruption",
        )
        interrupted_stdout, _ = process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            _run([_engine(), "kill", "--signal=KILL", run_name])
            process.communicate(timeout=10)
    if process.returncode != 137 or interrupted_stdout:
        raise RuntimeError("interrupted container run did not fail closed")
    if _run([_engine(), "inspect", run_name]).returncode == 0:
        raise RuntimeError("interrupted container was not removed")


def _verify_interruption(build: list[str], image: str) -> None:
    current_before = _run([_engine(), "image", "inspect", image, "--format", "{{.Id}}"])
    _require_success(current_before, "current image before interruption")
    _verify_interrupted_build(build, image)
    _verify_interrupted_run(image)
    current_after = _run([_engine(), "image", "inspect", image, "--format", "{{.Id}}"])
    _require_success(current_after, "current image after interruption")
    if current_before.stdout != current_after.stdout:
        raise RuntimeError("interruption changed the current image")


def _verify_rollback(prior_commit: str, uv: str, scratch: Path) -> tuple[str, str]:
    if len(prior_commit) != 40 or any(
        character not in "0123456789abcdef" for character in prior_commit
    ):
        raise ValueError("prior commit must be a full lowercase Git SHA")
    _require_success(
        _run(["git", "merge-base", "--is-ancestor", prior_commit, "HEAD"]),
        "prior commit ancestry",
    )
    prior_source = scratch / "prior-source"
    prior_source.mkdir()
    archive = scratch / "prior.tar"
    _require_success(
        _run(["git", "archive", "--format=tar", f"--output={archive}", prior_commit]),
        "prior source archive",
    )
    _require_success(
        _run(["tar", "-xf", str(archive), "-C", str(prior_source)]),
        "prior source extraction",
    )
    prior_export = _run(
        [
            uv,
            "export",
            "--locked",
            "--no-dev",
            "--format",
            "requirements-txt",
            "--no-emit-project",
            "--no-header",
            "--no-annotate",
        ],
        cwd=prior_source,
    )
    _require_success(prior_export, "prior lock export")
    prior_requirements = scratch / "prior-requirements.txt"
    prior_requirements.write_bytes(prior_export.stdout)
    prior_dist = scratch / "prior-dist"
    _require_success(
        _run(
            [
                uv,
                "build",
                "--no-build-isolation",
                "--python",
                str(ROOT / ".venv/bin/python"),
                "--out-dir",
                str(prior_dist),
            ],
            cwd=prior_source,
        ),
        "prior source distribution and wheel",
    )
    prior_wheels = list(prior_dist.glob("*.whl"))
    if len(prior_wheels) != 1:
        raise RuntimeError("rollback requires one prior wheel")
    prior_venv = scratch / "prior-venv"
    _require_success(
        _run([uv, "venv", "--python", "3.11", str(prior_venv)]), "prior venv"
    )
    prior_python = str(prior_venv / "bin/python")
    _require_success(
        _run(
            [
                uv,
                "pip",
                "install",
                "--python",
                prior_python,
                "--link-mode",
                "copy",
                "--require-hashes",
                "-r",
                str(prior_requirements),
            ]
        ),
        "prior locked dependencies",
    )
    _require_success(
        _run(
            [
                uv,
                "pip",
                "install",
                "--python",
                prior_python,
                "--link-mode",
                "copy",
                "--no-deps",
                str(prior_wheels[0]),
            ]
        ),
        "prior wheel install",
    )
    _require_success(
        _run([str(prior_venv / "bin/market-data"), "--help"], cwd=scratch),
        "prior CLI rollback run",
    )
    return _sha256(prior_wheels[0]), _sha256(prior_requirements)


def verify(wheel: Path, receipt: Path | None, prior_commit: str) -> dict[str, object]:
    global _RUNTIME, _PODMAN_ROOTLESS  # noqa: PLW0603 -- fixed for one verifier invocation
    _RUNTIME = select_runtime(allow_job_engine=True)
    runtime_name = Path(_RUNTIME).name
    info = _run([_RUNTIME, "info", "--format", "{{json .}}"])
    _require_success(info, "selected engine information")
    engine_info = json.loads(info.stdout)
    _PODMAN_ROOTLESS = (
        runtime_name == "podman" and engine_info["host"]["security"]["rootless"]
    )
    version = _run([_RUNTIME, "version", "--format", "{{json .}}"])
    _require_success(version, "selected engine version")
    runtime_version = json.loads(version.stdout)
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError("one built application wheel is required")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    version = project["project"]["version"]
    if not wheel.name.startswith(f"swing_trading_ai_assistant-{version}-"):
        raise ValueError("wheel version disagrees with pyproject.toml")
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required")
    head = _run(["git", "rev-parse", "HEAD"]).stdout.decode().strip()
    tree = _run(["git", "rev-parse", "HEAD^{tree}"]).stdout.decode().strip()
    dirty = bool(_run(["git", "status", "--porcelain=v1"]).stdout)
    revision = f"{head}-dirty" if dirty else head
    tag_revision = f"{head[:12]}-dirty" if dirty else head[:12]
    image = f"swing-trading-ai-assistant:{version}-{tag_revision}"
    with tempfile.TemporaryDirectory(
        prefix="issue167-distribution-", dir=Path.home()
    ) as temp:
        scratch = Path(temp)
        context = scratch / "build-context"
        context.mkdir()
        requirements = context / "requirements.txt"
        export = _run(
            [
                uv,
                "export",
                "--locked",
                "--no-dev",
                "--format",
                "requirements-txt",
                "--no-emit-project",
                "--no-header",
                "--no-annotate",
            ]
        )
        _require_success(export, "lock export")
        requirements.write_bytes(export.stdout)
        staged_wheel = context / wheel.name
        shutil.copyfile(wheel, staged_wheel)
        if set(context.iterdir()) != {requirements, staged_wheel}:
            raise RuntimeError("unexpected Docker build-context content")
        wheel_digest = _sha256(staged_wheel)
        python = scratch / "venv/bin/python"
        _require_success(
            _run([uv, "venv", "--python", "3.11", str(python.parent.parent)]),
            "native venv",
        )
        _require_success(
            _run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--link-mode",
                    "copy",
                    "--require-hashes",
                    "-r",
                    str(requirements),
                ]
            ),
            "locked native dependencies",
        )
        _require_success(
            _run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--link-mode",
                    "copy",
                    "--no-deps",
                    str(staged_wheel),
                ]
            ),
            "clean native wheel",
        )
        build = [
            _engine(),
            "build",
            "--platform",
            "linux/amd64",
            "--file",
            str(ROOT / "Containerfile"),
            "--build-arg",
            f"APP_VERSION={version}",
            "--build-arg",
            f"SOURCE_REVISION={revision}",
            "--build-arg",
            f"WHEEL_SHA256={wheel_digest}",
            "--build-arg",
            f"REQUIREMENTS_SHA256={_sha256(requirements)}",
            "--tag",
            image,
            str(context),
        ]
        _require_success(_run(build, timeout=600), "OCI build")
        altered_digest = [
            f"WHEEL_SHA256={'0' * 64}"
            if item == f"WHEEL_SHA256={wheel_digest}"
            else item
            for item in build
        ]
        rejected = _run(altered_digest, timeout=120)
        if rejected.returncode == 0 or b"wheel digest mismatch" not in (
            rejected.stdout + rejected.stderr
        ):
            raise RuntimeError("altered wheel digest was admitted")
        _verify_interruption(build, image)
        outcomes = _verify_cli(image, python, scratch)
        config = _run(
            [_engine(), "image", "inspect", image, "--format", "{{json .Config}}"]
        )
        _require_success(config, "image inspection")
        image_config = json.loads(config.stdout)
        if image_config["User"] != "10001:10001" or any(
            "BHARATSTOCK_API_KEY" in item for item in image_config["Env"]
        ):
            raise RuntimeError("image user or environment is unsafe")
        labels = image_config["Labels"]
        if (
            labels.get("org.opencontainers.image.revision") != revision
            or labels.get("org.opencontainers.image.version") != version
            or labels.get("org.opencontainers.image.source")
            != "https://github.com/krunaldodiya/SwingTradingAIAssistant"
            or labels.get("org.swingtradingaiassistant.wheel.sha256") != wheel_digest
            or labels.get("org.swingtradingaiassistant.requirements.sha256")
            != _sha256(requirements)
        ):
            raise RuntimeError("image source/version labels disagree with build")
        _verify_mounts(image, scratch)
        _verify_image_source(image, scratch)
        prior_wheel_digest, prior_requirements_digest = _verify_rollback(
            prior_commit, uv, scratch
        )
        inspection = _run([_engine(), "image", "inspect", image, "--format", "{{.Id}}"])
        _require_success(inspection, "image identity")
        result: dict[str, object] = {
            "container_runtime": runtime_name,
            "container_runtime_version": runtime_version,
            "source_commit": head,
            "source_tree": tree,
            "source_dirty": dirty,
            "version": version,
            "wheel_sha256": wheel_digest,
            "requirements_sha256": _sha256(requirements),
            "local_image_id": inspection.stdout.decode().strip(),
            "image_tag": image,
            "outcomes": outcomes,
            "mount_checks": "owner mapped, wrong UID, broad mode, read-only, symlink",
            "source_substitution": "rejected",
            "interrupted_build_and_run": "rejected; current image remained available",
            "rollback_prior_commit": prior_commit,
            "rollback_prior_wheel_sha256": prior_wheel_digest,
            "rollback_prior_requirements_sha256": prior_requirements_digest,
            "rollback_prior_cli": "installed and ran",
        }
        if receipt is not None:
            receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--prior-commit", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            verify(args.wheel.resolve(), args.receipt, args.prior_commit),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
