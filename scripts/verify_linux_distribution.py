"""Build and challenge the Linux wheel/OCI distribution from one exact wheel.

Run after ``uv build``. Docker receives a temporary two-file context: the wheel
and hash-checked runtime requirements exported from the repository lock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = "swing_trading_ai_assistant._examples.single_stock_research_demo"
EXPECTED_SYNTHETIC_IDENTITY = (
    "03b7175c3a06c95c778b88ee4be6e7f2edb668eaf8cf7e7618ec327c96228c6a"
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


def _container(image: str, *, entrypoint: str | None = None) -> list[str]:
    command = [
        "docker",
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
    command = _container(image)
    command[2:2] = ["--user", user, "--mount", mount]
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
    if admitted.returncode != 1 or json.loads(admitted.stdout)["stage"] == "storage":
        raise RuntimeError("owner-mapped private volume was not admitted")
    _assert_storage_stop(_mounted_request(image, private, user="10002:10002"))
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


def verify(wheel: Path, receipt: Path | None) -> dict[str, object]:
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
    with tempfile.TemporaryDirectory(prefix="issue167-distribution-") as temp:
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
            "docker",
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
            "--tag",
            image,
            str(context),
        ]
        _require_success(_run(build, timeout=600), "OCI build")
        altered_digest = [
            "0" * 64 if item == f"WHEEL_SHA256={wheel_digest}" else item
            for item in build
        ]
        rejected = _run(altered_digest, timeout=120)
        if rejected.returncode == 0 or b"wheel digest mismatch" not in (
            rejected.stdout + rejected.stderr
        ):
            raise RuntimeError("altered wheel digest was admitted")
        outcomes = _verify_cli(image, python, scratch)
        config = _run(
            ["docker", "image", "inspect", image, "--format", "{{json .Config}}"]
        )
        _require_success(config, "image inspection")
        image_config = json.loads(config.stdout)
        if image_config["User"] != "10001:10001" or any(
            "BHARATSTOCK_API_KEY" in item for item in image_config["Env"]
        ):
            raise RuntimeError("image user or environment is unsafe")
        _verify_mounts(image, scratch)
        _verify_image_source(image, scratch)
        inspection = _run(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
        _require_success(inspection, "image identity")
        result: dict[str, object] = {
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
        }
        if receipt is not None:
            receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(verify(args.wheel.resolve(), args.receipt), indent=2, sort_keys=True)
    )


if __name__ == "__main__":
    main()
