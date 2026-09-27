"""Registry digest selection must not depend on Docker's alias ordering."""

from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/registry_digest.py"
IMAGE = "ghcr.io/owner/project"
REGISTRY = f"{IMAGE}@sha256:{'a' * 64}"
LOCAL = f"local-build@sha256:{'b' * 64}"


@pytest.mark.parametrize("digests", ([LOCAL, REGISTRY], [REGISTRY, LOCAL], [REGISTRY]))
def test_selects_exact_registry_regardless_of_local_alias_order(
    digests: list[str],
) -> None:
    select = runpy.run_path(str(SCRIPT))["select_registry_digest"]
    assert select(digests, IMAGE) == REGISTRY


@pytest.mark.parametrize(
    "digests",
    (
        [],
        [LOCAL],
        [f"{IMAGE}-other@sha256:{'a' * 64}"],
        [REGISTRY, f"{IMAGE}@sha256:{'c' * 64}"],
        [REGISTRY, REGISTRY],
        [f"{IMAGE}@sha256:short"],
        [f"{IMAGE}@sha512:{'a' * 64}"],
        [REGISTRY, None],
        None,
        {"digest": REGISTRY},
    ),
)
def test_rejects_missing_ambiguous_or_malformed_registry_identity(
    digests: object,
) -> None:
    select = runpy.run_path(str(SCRIPT))["select_registry_digest"]
    with pytest.raises(ValueError):
        select(digests, IMAGE)


@pytest.mark.parametrize("payload,exit_code", (([LOCAL, REGISTRY], 0), ([LOCAL], 2)))
def test_cli_emits_only_verified_digest_or_empty_stdout(
    payload: list[str], exit_code: int
) -> None:
    result = subprocess.run(  # noqa: S603 - Fixed interpreter/script; no shell or input arguments.
        [sys.executable, str(SCRIPT), IMAGE],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == exit_code
    assert result.stdout == (REGISTRY + "\n" if exit_code == 0 else "")
    if exit_code:
        assert "Registry digest rejected:" in result.stderr
