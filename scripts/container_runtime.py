"""Select one usable container engine before creating any CI resources."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys


def select_runtime(requested: str | None = None) -> str:
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
            if probe.returncode == 0 and isinstance(json.loads(probe.stdout), dict):
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
    try:
        print(select_runtime())
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
