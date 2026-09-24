"""Verify the admitted release in WSL2 and the real Docker Desktop engine.

Run through verify_windows_distribution.ps1. No provider or owner data is used.
The release pins deliberately change only through review, never tag discovery.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

RELEASE = "25ca85b21700b580d62b84959cd4e83582801adb"
IMAGE = "ghcr.io/krunaldodiya/swingtradingaiassistant@sha256:68f6bf010dd5a50be0a4eb3fb37a9c95b74059077cbc84320486342ee6d03a5b"
PRIOR = "7e43491210d34a386e2bc14aa7c8b0d96e13b282"
PRIOR_IMAGE = "ghcr.io/krunaldodiya/swingtradingaiassistant@sha256:0483beb72f3e94bdac88c5e61d7d6a5543d6051c6f80c6924d52a781336a81bd"
WHEEL_SHA = "f3c790add4731d4f25a389a739fdc9d2cb0494c1dabae4ef052f780eba2c0c49"
LOCK_SHA = "04fcc498a40f141db3afac2d51500045c4975cf3dcc6f779b3ed9bc440526030"
POSITIVE_SHA = "105e5b437f1daca41539b955088842b704b1ee49518036668a53a6bdebbfeef0"
DEMO = "swing_trading_ai_assistant._examples.single_stock_research_demo"


def run(
    args: list[str], *, cwd: Path, env=None, expected=0, timeout=600, log=None
) -> bytes:
    result = subprocess.run(  # noqa: S603 - fixed tools, reviewed pinned artifacts
        args, cwd=cwd, env=env, capture_output=True, timeout=timeout, check=False
    )
    if log is not None:
        log.write_bytes(result.stdout + result.stderr)
    if result.returncode != expected:
        raise RuntimeError(
            f"{args[0]}: exit {result.returncode}: {result.stderr[-2000:]!r}"
        )
    return result.stdout


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def verify(repo: Path, host: dict, uv: str, evidence: Path) -> dict:
    require("microsoft" in platform.release().lower(), "WSL2 kernel required")
    require(
        platform.machine() == "x86_64" and os.getuid() != 0, "non-root x64 required"
    )
    require(host["os"].startswith("Microsoft Windows 11"), "Windows 11 host required")
    require(host["wsl_version"] == 2, "distribution must use WSL2")
    require(
        not run(["git", "status", "--porcelain"], cwd=repo), "dirty verifier source"
    )
    run(["git", "merge-base", "--is-ancestor", RELEASE, "HEAD"], cwd=repo)
    engine = json.loads(run(["docker", "info", "--format", "{{json .}}"], cwd=repo))
    require(
        engine["OperatingSystem"] == "Docker Desktop", "real Docker Desktop required"
    )
    require(engine["OSType"] == "linux", "Linux containers required")
    evidence.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema": "windows-distribution@v1",
        "host": host,
        "kernel": platform.release(),
        "verifier_commit": run(["git", "rev-parse", "HEAD"], cwd=repo).decode().strip(),
        "verifier_tree": run(["git", "rev-parse", "HEAD^{tree}"], cwd=repo)
        .decode()
        .strip(),
        "source_commit": RELEASE,
        "image": IMAGE,
        "prior_image": PRIOR_IMAGE,
        "engine_version": engine["ServerVersion"],
        "distribution_release": Path("/etc/os-release").read_text(),
        "home_filesystem": run(["stat", "-f", "-c", "%T", str(Path.home())], cwd=repo)
        .decode()
        .strip(),
        "status": "RUNNING",
        "checks": [],
    }
    receipt_path = evidence / "windows-distribution-receipt.json"

    def record(name: str) -> None:
        receipt["checks"].append(name)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        print(name, flush=True)

    try:
        with tempfile.TemporaryDirectory(
            prefix="windows-conformance-", dir=Path.home()
        ) as tmp:
            scratch = Path(tmp)
            source = scratch / "source"
            run(["git", "clone", "--no-hardlinks", str(repo), str(source)], cwd=scratch)
            run(["git", "checkout", "--detach", RELEASE], cwd=source)
            run(
                [uv, "sync", "--python", "3.11", "--extra", "dev", "--frozen"],
                cwd=source,
            )
            run(
                [uv, "build", "--no-build-isolation", "--python", ".venv/bin/python"],
                cwd=source,
            )
            wheel = next((source / "dist").glob("*.whl"))
            lock = scratch / "requirements.txt"
            lock.write_bytes(
                run(
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
                    cwd=source,
                )
            )
            require(
                digest(wheel) == WHEEL_SHA and digest(lock) == LOCK_SHA,
                "published artifact hashes differ",
            )
            receipt.update(wheel_sha256=digest(wheel), requirements_sha256=digest(lock))
            python = scratch / "installed/bin/python"
            run(
                [uv, "venv", "--python", "3.11", str(python.parent.parent)], cwd=scratch
            )
            run(
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
                    str(lock),
                ],
                cwd=scratch,
            )
            run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--link-mode",
                    "copy",
                    "--no-deps",
                    str(wheel),
                ],
                cwd=scratch,
            )
            receipt["python"] = (
                run([str(python), "--version"], cwd=scratch).decode().strip()
            )
            spec = importlib.util.spec_from_file_location(
                "linux_verifier", source / "scripts/verify_linux_distribution.py"
            )
            require(
                spec is not None and spec.loader is not None, "missing release verifier"
            )
            verifier = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(verifier)
            for image, revision in ((IMAGE, RELEASE), (PRIOR_IMAGE, PRIOR)):
                run(["docker", "pull", "--platform", "linux/amd64", image], cwd=scratch)
                details = json.loads(
                    run(["docker", "image", "inspect", image], cwd=scratch)
                )[0]
                require(image in details["RepoDigests"], "registry digest mismatch")
                require(
                    details["Config"]["Labels"]["org.opencontainers.image.revision"]
                    == revision,
                    "image source mismatch",
                )
                require(
                    details["Config"]["User"] == "10001:10001",
                    "image default user mismatch",
                )
                require(
                    not any(
                        any(
                            word in item.split("=", 1)[0].upper()
                            for word in ("TOKEN", "SECRET", "PASSWORD", "API_KEY")
                        )
                        for item in details["Config"]["Env"]
                    ),
                    "credential environment in image",
                )
                if image == IMAGE:
                    require(
                        details["Config"]["Labels"][
                            "org.swingtradingaiassistant.wheel.sha256"
                        ]
                        == WHEEL_SHA,
                        "image wheel mismatch",
                    )
                    require(
                        details["Config"]["Labels"][
                            "org.swingtradingaiassistant.requirements.sha256"
                        ]
                        == LOCK_SHA,
                        "image lock mismatch",
                    )
                    receipt["image_id"] = details["Id"]
                inspection = verifier._container(image, entrypoint="python")
                # Read-only inspection, no host mounts: root can inspect /root.
                inspection[2:2] = ["--user", "0:0"]
                run(
                    [
                        *inspection,
                        "-c",
                        "from pathlib import Path; assert not any(Path(p).exists() for p in ('/data','/Users','/root/.docker/config.json','/home/app/.docker/config.json','/home/app/SwingTradingAIAssistantData'))",
                    ],
                    cwd=scratch,
                )
            record("published digest, source, wheel, lock and image-content checks")
            receipt["outcomes"] = verifier._verify_cli(IMAGE, python, scratch)
            require(
                receipt["outcomes"]["complete"]["stdout_sha256"] == POSITIVE_SHA,
                "Linux baseline differs",
            )
            record("clean installed WSL/OCI CLI positive and malformed byte equality")
            verifier._verify_mounts(IMAGE, scratch)
            record(
                "Desktop WSL-ext4 owner, wrong-owner, broad-mode, readonly, symlink matrix"
            )
            verifier._verify_image_source(IMAGE, scratch)
            record("runtime source substitution refused")
            verifier._verify_interrupted_run(IMAGE)
            record("container interruption exits 137 and removes disposable container")
            prior_wheel, prior_lock = verifier._verify_rollback(PRIOR, uv, scratch)
            receipt.update(
                prior_wheel_sha256=prior_wheel, prior_requirements_sha256=prior_lock
            )
            record("prior installed-wheel rollback CLI")
            receipt["installed_tests"] = conformance_tests(
                verifier, source, scratch, python, evidence
            )
            record(
                "installed WSL and published OCI research authorization, retention, retry and sanitization tests"
            )
            persistence(verifier, scratch)
            record(
                "synthetic host backup, restore, recreation, upgrade and digest rollback"
            )
            receipt["status"] = "PASS"
    except Exception as exc:
        receipt["status"] = "FAIL"
        receipt["failure_type"] = type(exc).__name__
        raise
    finally:
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def conformance_tests(
    verifier, source: Path, scratch: Path, python: Path, evidence: Path
) -> dict:
    """Use existing deterministic tests against installed artifacts, without src/.

    Only pytest's own locked tooling is exposed via PYTHONPATH. Application and
    runtime dependencies continue to resolve from each installed artifact.
    """
    tools = scratch / "test-tools"
    tools.mkdir()
    (tools / "sitecustomize.py").write_text(
        "import sys\n"
        "def deny_network(event, args):\n"
        "    if event.startswith('socket.'):\n"
        "        raise RuntimeError('offline conformance denies network')\n"
        "sys.addaudithook(deny_network)\n"
    )
    site = source / ".venv/lib/python3.11/site-packages"
    for name in ("pytest", "_pytest", "pluggy", "iniconfig", "packaging", "pygments"):
        shutil.copytree(site / name, tools / name)
    shutil.copyfile(site / "py.py", tools / "py.py")
    tests = scratch / "tests"
    tests.mkdir()
    shutil.copyfile(
        source / "tests/market_data/test_current_stock_research.py",
        tests / "test_research.py",
    )
    args = [
        "-m",
        "pytest",
        "-q",
        "-c",
        "/dev/null",
        "--import-mode=importlib",
        "-o",
        "addopts=",
        "--durations=10",
        "-p",
        "no:cacheprovider",
    ]
    env = {
        "HOME": str(scratch),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(tools),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    native_log = evidence / "wsl-installed-tests.txt"
    native = run([str(python), *args, str(tests)], cwd=scratch, env=env, log=native_log)
    container = verifier._container(IMAGE, entrypoint="python")
    # 185 tests retain separate roots until session teardown. Keep their data
    # on the actual private WSL filesystem, not the application's 64 MiB /tmp.
    data = scratch / "container-test-data"
    data.mkdir(mode=0o700)
    container[2:2] = [
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--mount",
        f"type=bind,src={data},dst=/test-data",
        "--mount",
        f"type=bind,src={tools},dst=/test-tools,readonly",
        "--mount",
        f"type=bind,src={tests},dst=/tests,readonly",
        "--env",
        "PYTHONPATH=/test-tools",
        "--env",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        "--env",
        "TMPDIR=/test-data",
        "--env",
        "HOME=/test-data",
    ]
    image_log = evidence / "oci-installed-tests.txt"
    output = run([*container, *args, "/tests"], cwd=scratch, log=image_log)
    return {
        "wsl_log_sha256": digest(native_log),
        "oci_log_sha256": digest(image_log),
        "wsl_summary": native.decode().splitlines()[-1],
        "oci_summary": output.decode().splitlines()[-1],
    }


def persistence(verifier, scratch: Path) -> None:
    root = scratch / "retained-synthetic"
    root.mkdir(mode=0o700)
    marker = root / "fixture.json"
    marker.write_bytes(
        run([*verifier._container(IMAGE, entrypoint="python"), "-m", DEMO], cwd=scratch)
    )
    marker.chmod(0o600)
    expected, inode = digest(marker), marker.stat().st_ino
    backup = scratch / "backup.tar"
    run(["tar", "-cf", str(backup), "-C", str(root), "."], cwd=scratch)
    restored = scratch / "restored"
    restored.mkdir(mode=0o700)
    run(["tar", "-xf", str(backup), "-C", str(restored)], cwd=scratch)
    require(digest(restored / marker.name) == expected, "backup restore mismatch")
    for image in (PRIOR_IMAGE, IMAGE, PRIOR_IMAGE):
        cmd = verifier._container(image, entrypoint="python")
        cmd[2:2] = [
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--mount",
            f"type=bind,src={root},dst=/data",
        ]
        program = "import hashlib,pathlib,sys; p=pathlib.Path('/data/fixture.json'); assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[1]"
        run([*cmd, "-c", program, expected], cwd=scratch)
    require(
        digest(marker) == expected and marker.stat().st_ino == inode,
        "rollback changed host data",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument(
        "--uv",
        default=str(
            Path.home() / ".local/share/issue208/tools/uv-x86_64-unknown-linux-gnu/uv"
        ),
    )
    options = parser.parse_args()
    verify(
        options.repo.resolve(),
        json.loads(options.host.read_text(encoding="utf-8-sig")),
        options.uv,
        options.evidence,
    )
