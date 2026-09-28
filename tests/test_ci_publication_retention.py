"""Retain a verified publication receipt even when credential logout fails."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_verified_receipt_survives_failed_logout(tmp_path):
    workflow = (ROOT / ".github/workflows/publish-oci.yml").read_text()
    step = workflow.split("      - name: Publish commit-qualified image")[1]
    block = step.split("        run: |\n", 1)[1].split("\n      - name:", 1)[0]
    block = textwrap.dedent(block)
    # Start after the unchanged registry identity checks, at receipt creation.
    tail = block[block.index("jq -n --arg source") :]
    binary = tmp_path / "bin"
    binary.mkdir()
    jq = binary / "jq"
    jq.write_text(
        f'#!{sys.executable}\nprint(\'{{"source_commit":"fixture","digest":"fixture-digest"}}\')\n'
    )
    jq.chmod(0o700)
    runtime = binary / "podman"
    runtime.write_text('#!/bin/sh\ntest "$1" = logout || exit 99\nexit 47\n')
    runtime.chmod(0o700)
    scratch = tmp_path / "temp"
    scratch.mkdir()
    receipt = scratch / "linux-distribution-receipt.json"
    receipt.write_text('{"source_commit":"fixture"}\n')
    env = dict(
        os.environ,
        PATH=str(binary) + ":" + os.environ["PATH"],
        RUNNER_TEMP=str(scratch),
        SWING_CI_ARTIFACTS=str(tmp_path / "artifacts"),
        GITHUB_RUN_ID="123",
        GITHUB_RUN_ATTEMPT="1",
        GITHUB_OUTPUT=str(tmp_path / "outputs"),
        GITHUB_STEP_SUMMARY=str(tmp_path / "summary"),
        ADMITTED_SHA="fixture",
        image="fixture",
        tag="fixture",
        digest="fixture-digest",
        local_id="fixture",
        published_id="fixture",
        receipt=str(receipt),
        runtime=str(runtime),
    )
    result = subprocess.run(  # noqa: S603 -- fixed workflow tail and synthetic engine
        ["/bin/bash", "-c", "set -euo pipefail\n" + tail],
        env=env,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 47, result.stderr
    retained = tmp_path / "artifacts/123-1"
    assert (retained / "oci-publication-receipt.json").read_bytes() == (
        scratch / "oci-publication-receipt.json"
    ).read_bytes()
    assert (
        retained / "linux-distribution-receipt.json"
    ).read_bytes() == receipt.read_bytes()
