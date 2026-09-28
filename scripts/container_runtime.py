"""Select one usable container engine before creating any CI resources."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys


def _admitted_podman(info: dict, allow_job_engine: bool) -> bool:
    host = info.get("host")
    security = host.get("security") if isinstance(host, dict) else None
    rootless = security.get("rootless") if isinstance(security, dict) else None
    return rootless is True or (
        rootless is False
        and allow_job_engine
        and os.environ.get("CONTAINER_HOST") == "unix:///ci/podman.sock"
    )


def select_runtime(
    requested: str | None = None, *, allow_job_engine: bool = False
) -> str:
    choice = (
        os.environ.get("SWING_CONTAINER_RUNTIME", "auto")
        if requested is None
        else requested
    )
    if choice not in {"auto", "podman", "docker"}:
        raise ValueError("SWING_CONTAINER_RUNTIME must be auto, podman or docker")
    candidates = ("podman", "docker") if choice == "auto" else (choice,)
    for name in candidates:
        executable = shutil.which(name)
        if executable is None:
            continue
        try:
            probe = subprocess.run(  # noqa: S603 -- closed runtime names; no shell
                [executable, "info", "--format", "{{json .}}"],
                capture_output=True,
                timeout=10,
                check=False,
            )
            if probe.returncode == 0:
                info = json.loads(probe.stdout)
                if isinstance(info, dict) and (
                    name == "docker" or _admitted_podman(info, allow_job_engine)
                ):
                    return executable
        except (OSError, subprocess.TimeoutExpired, ValueError):
            continue
    if choice != "auto":
        raise RuntimeError(
            f"{choice} unavailable; check its installation and engine access"
        )
    raise RuntimeError(
        "No usable Podman or Docker engine; check installation and engine access"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-engine", action="store_true")
    args = parser.parse_args()
    try:
        print(select_runtime(allow_job_engine=args.job_engine))
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
