"""Build and challenge the Linux wheel/OCI distribution from one exact wheel.

Run after ``uv build``. The selected engine receives a temporary two-file context: the wheel
and hash-checked runtime requirements exported from the repository lock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import tomllib
import uuid
from pathlib import Path

from container_runtime import select_runtime

_RUNTIME: str | None = None
_PODMAN_ROOTLESS = False
_PODMAN_GENERATION = Path("/ci/podman-engine-generation")


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


def _check_installed_level(value: dict, raw: bytes, scenario: str) -> None:
    observed = scenario in ("above", "at", "below")
    status = "OBSERVED" if observed else scenario.upper()
    reason = (
        "LATEST_COMPLETED_CLOSE_COMPARED_WITH_ORIGINAL_BROKEN_HIGH"
        if observed
        else "IDENTICAL_ADMITTED_OBSERVATION"
        if scenario == "replay"
        else "CURRENT_STRUCTURE_UNKNOWN"
    )
    if (
        set(value)
        != {
            "contract_version",
            "criterion",
            "runtime_code_identity_sha256",
            "previous_observation_identity_sha256",
            "current_observation_identity_sha256",
            "continuity_identity_sha256",
            "continuity_status",
            "previous",
            "current",
            "status",
            "reason",
            "relation",
            "witness",
            "limitations",
            "result_identity_sha256",
        }
        or value["contract_version"] != "causal-setup-level@v1"
        or value["criterion"] != "LATEST_COMPLETED_CLOSE_VS_ORIGINAL_BROKEN_HIGH@v1"
        or (value["status"], value["reason"]) != (status, reason)
        or value["continuity_status"] != ("SAME_EVENT" if observed else status)
        or value["relation"] != (scenario.upper() if observed else None)
        or value["previous"]["status"] != "MATCH"
        or value["current"]["status"]
        != ("NO_MATCH" if observed else "MATCH" if scenario == "replay" else "UNKNOWN")
        or raw != _interpretation_bytes(value)
        or type(value["limitations"]) is not list
        or not value["limitations"]
        or any(type(item) is not str or not item for item in value["limitations"])
    ):
        raise ValueError("level envelope invalid")
    digests = [
        value[key]
        for key in (
            "runtime_code_identity_sha256",
            "previous_observation_identity_sha256",
            "current_observation_identity_sha256",
            "continuity_identity_sha256",
            "result_identity_sha256",
        )
    ]
    witness = value["witness"]
    if observed:
        candidate = value["previous"]["candidate"]
        if (
            type(witness) is not dict
            or set(witness)
            != {
                "original_event_session",
                "original_high_pivot_session",
                "original_high_confirmation_session",
                "original_event_identity_sha256",
                "original_high_identity_sha256",
                "represented_event_identity_sha256",
                "represented_high_identity_sha256",
                "current_completed_session",
                "current_bar_identity_sha256",
            }
            or any(
                witness[key] != candidate[source]
                for key, source in (
                    ("original_event_session", "event_session"),
                    ("original_high_pivot_session", "pivot_session"),
                    (
                        "original_high_confirmation_session",
                        "pivot_confirmation_session",
                    ),
                    ("original_event_identity_sha256", "event_identity_sha256"),
                    ("original_high_identity_sha256", "pivot_identity_sha256"),
                )
            )
            or not witness["original_high_pivot_session"]
            < witness["original_high_confirmation_session"]
            < witness["original_event_session"]
            < witness["current_completed_session"]
            or witness["original_event_session"] != value["previous"]["session"]
            or witness["current_completed_session"] != value["current"]["session"]
        ):
            raise ValueError("level witness invalid")
        digests += [witness[key] for key in witness if key.endswith("sha256")]
    elif witness is not None:
        raise ValueError("level invented witness")
    if any(
        type(d) is not str
        or len(d) != 64
        or any(c not in "0123456789abcdef" for c in d)
        for d in digests
    ):
        raise ValueError("level identity invalid")
    if (
        scenario == "replay"
        and value["previous_observation_identity_sha256"]
        != value["current_observation_identity_sha256"]
    ):
        raise ValueError("level replay identity invalid")
    unsigned = dict(value)
    identity = unsigned.pop("result_identity_sha256")
    if identity != hashlib.sha256(_interpretation_bytes(unsigned)).hexdigest():
        raise ValueError("level result digest invalid")


def _verify_installed_level(
    python: Path, scratch: Path
) -> dict[str, dict[str, object]]:
    """Qualify the installed SDK and actual CLI, never a mocked acceptance report."""
    probe = "\n".join(
        (
            "import pathlib, runpy, sys",
            "sys.dont_write_bytecode = True",
            "import swing_trading_ai_assistant.research_comparison.setup_level as sdk",
            "import swing_trading_ai_assistant.research_comparison.setup_level_cli as cli",
            "for module in (sdk, cli):",
            "    if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "        raise RuntimeError('level import escaped installed environment')",
            "fixture, scenario = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "runpy.run_path(fixture, run_name='__main__')",
        )
    )
    safe_env = {
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    outcomes = {}
    for scenario in ("above", "at", "below", "replay", "unknown"):
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/causal_setup_level_demo.py"),
                scenario,
            ],
            cwd=scratch,
            env=safe_env,
        )
        code = 1 if scenario == "unknown" else 0
        if (
            observed.returncode != code
            or len(observed.stdout) > 1024 * 1024
            or b"SYNTHETIC" not in observed.stderr
            or b"not current market data" not in observed.stderr
            or any(
                token in observed.stdout
                for token in (
                    b'"close"',
                    b'"open"',
                    b'"high"',
                    b'"low"',
                    b'"price"',
                    b'"volume"',
                    b'"bars"',
                    b'"body"',
                    str(scratch).encode(),
                )
            )
        ):
            raise RuntimeError("installed level execution failed")
        try:
            value = json.loads(observed.stdout)
            _check_installed_level(value, observed.stdout, scenario)
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("installed level result invalid") from error
        outcomes[scenario] = {
            "exit": code,
            "status": value["status"],
            "relation": value["relation"],
            "continuity_status": value["continuity_status"],
            "current_projection_status": value["current"]["status"],
            "result_identity_sha256": value["result_identity_sha256"],
            "runtime_code_identity_sha256": value["runtime_code_identity_sha256"],
            "continuity_identity_sha256": value["continuity_identity_sha256"],
            "previous_observation_identity_sha256": value[
                "previous_observation_identity_sha256"
            ],
            "current_observation_identity_sha256": value[
                "current_observation_identity_sha256"
            ],
            "witness": value["witness"],
            "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            "imports": "SDK and injected CLI under installed sys.prefix with -I; actual outputs equal; synthetic descriptive fact only",
        }
    return outcomes


def _check_level_range_row(row: object, side: str, scenario: str) -> None:
    """Close the redacted row for these fixed synthetic installed scenarios."""
    unknown = side == "current" and scenario == "unknown"
    later = side == "current" and scenario not in ("replay", "unknown")
    status = "UNKNOWN" if unknown else "NO_MATCH" if later else "MATCH"
    instant = (
        "2026-08-26T04:16:00.000000Z"
        if unknown
        else "2026-08-27T04:15:00.000000Z"
        if later
        else "2026-08-26T04:15:00.000000Z"
    )
    scalars = {
        "requested_symbol": "PNB",
        "status": status,
        "reason": "INSUFFICIENT_STRUCTURE"
        if unknown
        else "OBSERVED_COMPARABLE_STRUCTURE",
        "research_status": "READY",
        "research_stage": "complete",
        "data_selection_time": instant,
        "research_evidence_known_at": instant,
        "feature_known_at": instant,
        "session": "2026-08-26" if later else "2026-08-25",
        "price_basis": "BHARATSTOCK_SOURCE_REPORTED_OHLC",
        "feature_availability": "OBSERVED",
        "feature_support": "SUPPORTED",
        "feature_comparability": "SUPPORTED",
        "source_profile": "BHARATSTOCK_CAPTURE_FORWARD_DAILY_V3",
        "structure_state": "INSUFFICIENT_STRUCTURE" if unknown else "CONFIRMED",
    }
    digest_fields = {
        "research_runtime_code_identity_sha256",
        "research_result_identity_sha256",
        "feature_source_identity_sha256",
        "capture_revision_identity_sha256",
        "schedule_identity_sha256",
    }
    if (
        type(row) is not dict
        or set(row)
        != set(scalars)
        | digest_fields
        | {"canonical_stock", "candidate", "candidate_identity_sha256"}
        or any(
            type(row[key]) is not str or row[key] != expected
            for key, expected in scalars.items()
        )
    ):
        raise ValueError("level range redacted row invalid")
    stock = row["canonical_stock"]
    if (
        type(stock) is not dict
        or set(stock)
        != {"isin", "exchange", "effective_symbol", "mapping_identity_sha256"}
        or (stock["isin"], stock["exchange"], stock["effective_symbol"])
        != ("INE160A01022", "NSE", "PNB")
    ):
        raise ValueError("level range stock invalid")
    digests = [row[key] for key in digest_fields] + [stock["mapping_identity_sha256"]]
    candidate = row["candidate"]
    if status == "MATCH":
        candidate_scalars = {
            "event": "BOS",
            "direction": "UP",
            "prior_trend": "UPTREND",
            "event_session": "2026-08-25",
            "pivot_session": "2026-08-19",
            "pivot_confirmation_session": "2026-08-21",
        }
        if (
            type(candidate) is not dict
            or set(candidate)
            != set(candidate_scalars)
            | {"event_identity_sha256", "pivot_identity_sha256"}
            or any(
                type(candidate[key]) is not str or candidate[key] != expected
                for key, expected in candidate_scalars.items()
            )
        ):
            raise ValueError("level range candidate invalid")
        digests += [
            candidate["event_identity_sha256"],
            candidate["pivot_identity_sha256"],
            row["candidate_identity_sha256"],
        ]
        bound = {
            key: row[key]
            for key in (
                "canonical_stock",
                "price_basis",
                "source_profile",
                "capture_revision_identity_sha256",
                "feature_source_identity_sha256",
                "candidate",
            )
        }
        bound["criterion"] = "LATEST_COMPLETED_UPWARD_BOS@v1"
        if (
            row["candidate_identity_sha256"]
            != hashlib.sha256(_interpretation_bytes(bound)).hexdigest()
        ):
            raise ValueError("level range candidate binding invalid")
    elif candidate is not None or row["candidate_identity_sha256"] is not None:
        raise ValueError("level range invented candidate")
    if any(
        type(d) is not str or re.fullmatch(r"[0-9a-f]{64}", d) is None for d in digests
    ):
        raise ValueError("level range row identity invalid")


def _check_installed_level_range(value: dict, raw: bytes, scenario: str) -> None:
    observed = scenario in ("contains", "above", "below", "low-equal", "high-equal")
    status = "OBSERVED" if observed else scenario.upper()
    reason = (
        "LATEST_COMPLETED_RANGE_COMPARED_WITH_ORIGINAL_BROKEN_HIGH"
        if observed
        else "IDENTICAL_ADMITTED_OBSERVATION"
        if scenario == "replay"
        else "CURRENT_STRUCTURE_UNKNOWN"
    )
    if (
        set(value)
        != {
            "contract_version",
            "criterion",
            "runtime_code_identity_sha256",
            "previous_observation_identity_sha256",
            "current_observation_identity_sha256",
            "level_identity_sha256",
            "continuity_identity_sha256",
            "continuity_status",
            "previous",
            "current",
            "status",
            "reason",
            "range_relation",
            "witness",
            "limitations",
            "result_identity_sha256",
        }
        or value["contract_version"] != "causal-setup-level-range@v1"
        or value["criterion"] != "LATEST_COMPLETED_RANGE_VS_ORIGINAL_BROKEN_HIGH@v1"
        or (value["status"], value["reason"]) != (status, reason)
        or value["continuity_status"] != ("SAME_EVENT" if observed else status)
        or value["range_relation"]
        != (
            {
                "contains": "CONTAINS_LEVEL",
                "above": "ENTIRELY_ABOVE",
                "below": "ENTIRELY_BELOW",
                "low-equal": "CONTAINS_LEVEL",
                "high-equal": "CONTAINS_LEVEL",
            }[scenario]
            if observed
            else None
        )
        or value["previous"]["status"] != "MATCH"
        or value["current"]["status"]
        != ("NO_MATCH" if observed else "MATCH" if scenario == "replay" else "UNKNOWN")
        or raw != _interpretation_bytes(value)
        or value["limitations"]
        != [
            "Inclusive low/high range of the latest completed post-event bar only; not first or any-bar contact.",
            "Range inclusion does not prove an exact traded tick, intrabar ordering, a reclaim or a successful retest.",
            "No confirmation, invalidation, validity, eligibility, recommendation, effectiveness or trade authorization is inferred.",
            "Original unchanged causal high and completed bar must remain represented and fully admitted in the finite21-session window.",
            "No tolerance, threshold, expiry, persistence, monitoring, new acquisition or external model.",
        ]
    ):
        raise ValueError("level envelope invalid")
    for side in ("previous", "current"):
        _check_level_range_row(value[side], side, scenario)
    if scenario == "replay" and value["previous"] != value["current"]:
        raise ValueError("level range replay rows invalid")
    digests = [
        value[key]
        for key in (
            "runtime_code_identity_sha256",
            "previous_observation_identity_sha256",
            "current_observation_identity_sha256",
            "level_identity_sha256",
            "continuity_identity_sha256",
            "result_identity_sha256",
        )
    ]
    witness = value["witness"]
    if observed:
        candidate = value["previous"]["candidate"]
        if (
            type(witness) is not dict
            or set(witness)
            != {
                "original_event_session",
                "original_high_pivot_session",
                "original_high_confirmation_session",
                "original_event_identity_sha256",
                "original_high_identity_sha256",
                "represented_event_identity_sha256",
                "represented_high_identity_sha256",
                "current_completed_session",
                "current_bar_identity_sha256",
            }
            or any(
                witness[key] != candidate[source]
                for key, source in (
                    ("original_event_session", "event_session"),
                    ("original_high_pivot_session", "pivot_session"),
                    (
                        "original_high_confirmation_session",
                        "pivot_confirmation_session",
                    ),
                    ("original_event_identity_sha256", "event_identity_sha256"),
                    ("original_high_identity_sha256", "pivot_identity_sha256"),
                )
            )
            or not witness["original_high_pivot_session"]
            < witness["original_high_confirmation_session"]
            < witness["original_event_session"]
            < witness["current_completed_session"]
            or witness["original_event_session"] != value["previous"]["session"]
            or witness["current_completed_session"] != value["current"]["session"]
        ):
            raise ValueError("level witness invalid")
        digests += [witness[key] for key in witness if key.endswith("sha256")]
    elif witness is not None:
        raise ValueError("level invented witness")
    if any(
        type(d) is not str
        or len(d) != 64
        or any(c not in "0123456789abcdef" for c in d)
        for d in digests
    ):
        raise ValueError("level identity invalid")
    if (
        scenario == "replay"
        and value["previous_observation_identity_sha256"]
        != value["current_observation_identity_sha256"]
    ):
        raise ValueError("level replay identity invalid")
    unsigned = dict(value)
    identity = unsigned.pop("result_identity_sha256")
    if identity != hashlib.sha256(_interpretation_bytes(unsigned)).hexdigest():
        raise ValueError("level result digest invalid")


def _verify_installed_level_range(
    python: Path, scratch: Path
) -> dict[str, dict[str, object]]:
    """Qualify the installed SDK and actual CLI, never a mocked acceptance report."""
    probe = "\n".join(
        (
            "import pathlib, runpy, sys",
            "sys.dont_write_bytecode = True",
            "import swing_trading_ai_assistant.research_comparison.setup_level_range as sdk",
            "import swing_trading_ai_assistant.research_comparison.setup_level_range_cli as cli",
            "for module in (sdk, cli):",
            "    if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "        raise RuntimeError('level import escaped installed environment')",
            "fixture, scenario = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "runpy.run_path(fixture, run_name='__main__')",
        )
    )
    safe_env = {
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    outcomes = {}
    for scenario in (
        "contains",
        "above",
        "below",
        "low-equal",
        "high-equal",
        "replay",
        "unknown",
    ):
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/causal_setup_level_range_demo.py"),
                scenario,
            ],
            cwd=scratch,
            env=safe_env,
        )
        code = 1 if scenario == "unknown" else 0
        if (
            observed.returncode != code
            or len(observed.stdout) > 1024 * 1024
            or b"SYNTHETIC" not in observed.stderr
            or b"not current market data" not in observed.stderr
            or any(
                token in observed.stdout
                for token in (
                    b'"close"',
                    b'"open"',
                    b'"high"',
                    b'"low"',
                    b'"price"',
                    b'"volume"',
                    b'"bars"',
                    b'"body"',
                    str(scratch).encode(),
                )
            )
        ):
            raise RuntimeError("installed level range execution failed")
        try:
            value = json.loads(observed.stdout)
            _check_installed_level_range(value, observed.stdout, scenario)
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("installed level range result invalid") from error
        outcomes[scenario] = {
            "exit": code,
            "status": value["status"],
            "range_relation": value["range_relation"],
            "continuity_status": value["continuity_status"],
            "current_projection_status": value["current"]["status"],
            "result_identity_sha256": value["result_identity_sha256"],
            "runtime_code_identity_sha256": value["runtime_code_identity_sha256"],
            "level_identity_sha256": value["level_identity_sha256"],
            "continuity_identity_sha256": value["continuity_identity_sha256"],
            "previous_observation_identity_sha256": value[
                "previous_observation_identity_sha256"
            ],
            "current_observation_identity_sha256": value[
                "current_observation_identity_sha256"
            ],
            "witness": value["witness"],
            "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            "imports": "SDK and injected CLI under installed sys.prefix with -I; actual outputs equal; synthetic descriptive fact only",
        }
    return outcomes


def _check_legacy_evidence_identity(identity: object) -> None:
    if type(identity) is not str or re.fullmatch(r"[0-9a-f]{64}", identity) is None:
        raise ValueError("evidence v2 legacy identity invalid")


def _check_installed_evidence_v2(value: dict, raw: bytes, scenario: str) -> None:
    """Falsify mixed revisions, fabricated facts and plausible-but-wrong bundles."""
    expected_versions = {
        "continuity": "causal-setup-event-continuity@v1",
        "invalidation": "causal-setup-invalidation@v1",
        "age": "causal-setup-age@v1",
        "level": "causal-setup-level@v1",
    }
    if (
        set(value)
        != {
            "contract_version",
            "criterion",
            "runtime_code_identity_sha256",
            "previous_observation_identity_sha256",
            "current_observation_identity_sha256",
            "continuity",
            "invalidation",
            "age",
            "level",
            "legacy_evidence_identity_sha256",
            "limitations",
            "result_identity_sha256",
        }
        or value["contract_version"] != "causal-setup-evidence@v2"
        or value["criterion"] != "LATEST_COMPLETED_UPWARD_BOS@v1"
        or raw
        != (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ):
        raise ValueError("evidence envelope disagrees with contract")
    for report in (value, *(value[name] for name in expected_versions)):
        unsigned = dict(report)
        identity = unsigned.pop("result_identity_sha256")
        if (
            identity
            != hashlib.sha256(
                (
                    json.dumps(unsigned, sort_keys=True, separators=(",", ":")) + "\n"
                ).encode()
            ).hexdigest()
        ):
            raise ValueError("evidence result identity invalid")
        for field in (
            "result_identity_sha256",
            "runtime_code_identity_sha256",
            "previous_observation_identity_sha256",
            "current_observation_identity_sha256",
        ):
            digest = report[field]
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
            ):
                raise ValueError("evidence digest invalid")
    continuity, invalidation, age = (
        value[name] for name in ("continuity", "invalidation", "age")
    )
    for name, version in expected_versions.items():
        report = value[name]
        if (
            report["contract_version"] != version
            or any(
                report[field] != value[field]
                for field in (
                    "previous_observation_identity_sha256",
                    "current_observation_identity_sha256",
                )
            )
            or any(report[side] != continuity[side] for side in ("previous", "current"))
        ):
            raise ValueError("evidence pair binding invalid")
    if any(
        value[name]["continuity_identity_sha256"]
        != continuity["result_identity_sha256"]
        for name in ("age", "invalidation", "level")
    ):
        raise ValueError("evidence continuity binding invalid")
    level_scenario = {"invalidated": "below", "no-trade": "above"}.get(
        scenario, scenario
    )
    _check_installed_level(
        value["level"], _interpretation_bytes(value["level"]), level_scenario
    )
    _check_legacy_evidence_identity(value["legacy_evidence_identity_sha256"])
    scenario = (
        "same-event" if scenario in ("above", "at", "below", "no-trade") else scenario
    )
    expected = {
        "same-event": (
            "SAME_EVENT",
            "NO_CONTRADICTION_OBSERVED",
            "OBSERVED",
            1,
            "NO_MATCH",
        ),
        "invalidated": ("SAME_EVENT", "INVALIDATED", "OBSERVED", 1, "NO_MATCH"),
        "replay": ("REPLAY", "REPLAY", "REPLAY", 0, "MATCH"),
        "unknown": ("UNKNOWN", "UNKNOWN", "UNKNOWN", None, "UNKNOWN"),
    }[scenario]
    if (
        continuity["status"],
        invalidation["status"],
        age["status"],
        age["completed_sessions_elapsed"],
        age["current"]["status"],
    ) != expected or (
        expected[3] is not None and type(age["completed_sessions_elapsed"]) is not int
    ):
        raise ValueError("evidence facts disagree with contract")
    _check_evidence_witness(invalidation, scenario)


def _check_installed_interpretation_v2(value: dict, raw: bytes, scenario: str) -> None:
    labels = {
        "verification": "STRUCTURED_BINDING_ONLY",
        "explanation_accuracy": "NOT_ASSESSED",
        "external_authorship": "CALLER_SUPPLIED_NOT_AUTHENTICATED",
        "actionable_recommendation": "NOT_ASSESSED",
        "eligibility": "NOT_ASSESSED",
        "effectiveness": "NOT_ASSESSED",
    }
    if (
        set(value)
        != set(labels)
        | {
            "contract_version",
            "evidence",
            "external_response",
            "external_response_identity_sha256",
            "runtime_code_identity_sha256",
            "result_identity_sha256",
            "limitations",
        }
        or value["contract_version"] != "external-setup-interpretation-check@v2"
        or any(value[key] != expected for key, expected in labels.items())
        or raw != _interpretation_bytes(value)
        or type(value["limitations"]) is not list
        or not value["limitations"]
        or any(type(item) is not str or not item for item in value["limitations"])
    ):
        raise ValueError("interpretation envelope invalid")
    evidence = value["evidence"]
    _check_installed_evidence_v2(
        evidence,
        _interpretation_bytes(evidence),
        scenario,
    )
    response = value["external_response"]
    if (
        set(response)
        != {"schema", "evidence_identity_sha256", "disposition", "explanation", "facts"}
        or response["schema"] != "external-setup-interpretation-request@v2"
        or response["evidence_identity_sha256"] != evidence["result_identity_sha256"]
        or response["disposition"]
        != ("NO_TRADE" if scenario == "no-trade" else "RESEARCH_ONLY")
        or response["explanation"]
        != "Caller-authored synthetic research posture; facts unchanged, narrative accuracy and eligibility unassessed."
        or set(response["facts"]) != {"continuity", "invalidation", "age", "level"}
    ):
        raise ValueError("interpretation caller binding invalid")
    for name in ("continuity", "invalidation", "age", "level"):
        facts = response["facts"][name]
        keys = {"result_identity_sha256", "status"}
        if name == "age":
            keys.add("completed_sessions_elapsed")
            count = facts["completed_sessions_elapsed"]
            if count is not None and type(count) is not int:
                raise ValueError("interpretation count invalid")
        keys |= {"level": {"relation"}}.get(name, set())
        if set(facts) != keys or any(facts[key] != evidence[name][key] for key in keys):
            raise ValueError("interpretation facts invalid")
    unsigned = dict(value)
    identity = unsigned.pop("result_identity_sha256")
    if (
        identity != hashlib.sha256(_interpretation_bytes(unsigned)).hexdigest()
        or value["external_response_identity_sha256"]
        != hashlib.sha256(_interpretation_bytes(response)).hexdigest()
    ):
        raise ValueError("interpretation digest invalid")
    for key in (
        "runtime_code_identity_sha256",
        "result_identity_sha256",
        "external_response_identity_sha256",
    ):
        digest = value[key]
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise ValueError("interpretation identity invalid")


def _verify_installed_level_interpretation_v2(
    python: Path, scratch: Path
) -> dict[str, dict[str, object]]:
    """Qualify real installed SDK+CLI; the fixture asserts byte-for-byte equality."""
    probe = "\n".join(
        (
            "import pathlib, runpy, sys",
            "sys.dont_write_bytecode = True",
            "import swing_trading_ai_assistant.research_comparison.setup_interpretation_v2 as sdk",
            "import swing_trading_ai_assistant.research_comparison.setup_interpretation_v2_cli as cli",
            "for module in (sdk, cli):",
            "    if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "        raise RuntimeError('interpretation import escaped installed environment')",
            "fixture, scenario = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "runpy.run_path(fixture, run_name='__main__')",
        )
    )
    safe_env = {
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    outcomes = {}
    for scenario in (
        "above",
        "at",
        "below",
        "invalidated",
        "replay",
        "unknown",
        "no-trade",
        "false-claim",
    ):
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/causal_setup_level_interpretation_v2_demo.py"),
                scenario,
            ],
            cwd=scratch,
            env=safe_env,
        )
        code = 2 if scenario == "false-claim" else 1 if scenario == "unknown" else 0
        if (
            observed.returncode != code
            or len(observed.stdout) > 1024 * 1024
            or b"SYNTHETIC CALLER-AUTHORED" not in observed.stderr
            or b"not current market data" not in observed.stderr
            or any(
                token in observed.stdout
                for token in (
                    b'"close"',
                    b'"open"',
                    b'"high"',
                    b'"low"',
                    b'"price"',
                    b'"volume"',
                    str(scratch).encode(),
                )
            )
        ):
            raise RuntimeError("installed interpretation execution failed")
        if scenario == "false-claim":
            if observed.stdout or not observed.stderr.endswith(
                b"setup_interpretation_failed\n"
            ):
                raise RuntimeError("installed interpretation false claim accepted")
            outcomes[scenario] = {
                "exit": 2,
                "rejected": True,
                "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            }
            continue
        try:
            value = json.loads(observed.stdout)
            _check_installed_interpretation_v2(value, observed.stdout, scenario)
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("installed interpretation result invalid") from error
        evidence = value["evidence"]
        outcomes[scenario] = {
            "exit": code,
            "continuity_status": evidence["continuity"]["status"],
            "invalidation_status": evidence["invalidation"]["status"],
            "age_status": evidence["age"]["status"],
            "level_status": evidence["level"]["status"],
            "relation": evidence["level"]["relation"],
            "legacy_evidence_identity_sha256": evidence[
                "legacy_evidence_identity_sha256"
            ],
            "completed_sessions_elapsed": evidence["age"]["completed_sessions_elapsed"],
            "disposition": value["external_response"]["disposition"],
            "result_identity_sha256": value["result_identity_sha256"],
            "runtime_code_identity_sha256": value["runtime_code_identity_sha256"],
            "evidence_identity_sha256": evidence["result_identity_sha256"],
            "external_response_identity_sha256": value[
                "external_response_identity_sha256"
            ],
            "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            "imports": "SDK and injected CLI under installed sys.prefix with -I; actual outputs equal; no model evaluated",
        }
    return outcomes


def _interpretation_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _check_installed_interpretation(value: dict, raw: bytes, scenario: str) -> None:
    labels = {
        "verification": "STRUCTURED_BINDING_ONLY",
        "explanation_accuracy": "NOT_ASSESSED",
        "external_authorship": "CALLER_SUPPLIED_NOT_AUTHENTICATED",
        "actionable_recommendation": "NOT_ASSESSED",
        "eligibility": "NOT_ASSESSED",
        "effectiveness": "NOT_ASSESSED",
    }
    if (
        set(value)
        != set(labels)
        | {
            "contract_version",
            "evidence",
            "external_response",
            "external_response_identity_sha256",
            "runtime_code_identity_sha256",
            "result_identity_sha256",
            "limitations",
        }
        or value["contract_version"] != "external-setup-interpretation-check@v1"
        or any(value[key] != expected for key, expected in labels.items())
        or raw != _interpretation_bytes(value)
        or type(value["limitations"]) is not list
        or not value["limitations"]
        or any(type(item) is not str or not item for item in value["limitations"])
    ):
        raise ValueError("interpretation envelope invalid")
    evidence = value["evidence"]
    _check_installed_evidence(
        evidence,
        _interpretation_bytes(evidence),
        "same-event" if scenario == "no-trade" else scenario,
    )
    response = value["external_response"]
    if (
        set(response)
        != {"schema", "evidence_identity_sha256", "disposition", "explanation", "facts"}
        or response["schema"] != "external-setup-interpretation-request@v1"
        or response["evidence_identity_sha256"] != evidence["result_identity_sha256"]
        or response["disposition"]
        != ("NO_TRADE" if scenario == "no-trade" else "RESEARCH_ONLY")
        or response["explanation"]
        != "Caller-authored synthetic research posture; facts unchanged, narrative accuracy and eligibility unassessed."
        or set(response["facts"]) != {"continuity", "invalidation", "age"}
    ):
        raise ValueError("interpretation caller binding invalid")
    for name in ("continuity", "invalidation", "age"):
        facts = response["facts"][name]
        keys = {"result_identity_sha256", "status"}
        if name == "age":
            keys.add("completed_sessions_elapsed")
            count = facts["completed_sessions_elapsed"]
            if count is not None and type(count) is not int:
                raise ValueError("interpretation count invalid")
        if set(facts) != keys or any(facts[key] != evidence[name][key] for key in keys):
            raise ValueError("interpretation facts invalid")
    unsigned = dict(value)
    identity = unsigned.pop("result_identity_sha256")
    if (
        identity != hashlib.sha256(_interpretation_bytes(unsigned)).hexdigest()
        or value["external_response_identity_sha256"]
        != hashlib.sha256(_interpretation_bytes(response)).hexdigest()
    ):
        raise ValueError("interpretation digest invalid")
    for key in (
        "runtime_code_identity_sha256",
        "result_identity_sha256",
        "external_response_identity_sha256",
    ):
        digest = value[key]
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise ValueError("interpretation identity invalid")


def _verify_installed_interpretation(
    python: Path, scratch: Path
) -> dict[str, dict[str, object]]:
    """Qualify real installed SDK+CLI; the fixture asserts byte-for-byte equality."""
    probe = "\n".join(
        (
            "import pathlib, runpy, sys",
            "sys.dont_write_bytecode = True",
            "import swing_trading_ai_assistant.research_comparison.setup_interpretation as sdk",
            "import swing_trading_ai_assistant.research_comparison.setup_interpretation_cli as cli",
            "for module in (sdk, cli):",
            "    if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "        raise RuntimeError('interpretation import escaped installed environment')",
            "fixture, scenario = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "runpy.run_path(fixture, run_name='__main__')",
        )
    )
    safe_env = {
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    outcomes = {}
    for scenario in (
        "same-event",
        "invalidated",
        "replay",
        "unknown",
        "no-trade",
        "false-claim",
    ):
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/causal_setup_interpretation_demo.py"),
                scenario,
            ],
            cwd=scratch,
            env=safe_env,
        )
        code = 2 if scenario == "false-claim" else 1 if scenario == "unknown" else 0
        if (
            observed.returncode != code
            or len(observed.stdout) > 1024 * 1024
            or b"SYNTHETIC CALLER-AUTHORED" not in observed.stderr
            or b"not current market data" not in observed.stderr
            or any(
                token in observed.stdout
                for token in (
                    b'"close"',
                    b'"open"',
                    b'"high"',
                    b'"low"',
                    b'"price"',
                    b'"volume"',
                    str(scratch).encode(),
                )
            )
        ):
            raise RuntimeError("installed interpretation execution failed")
        if scenario == "false-claim":
            if observed.stdout or not observed.stderr.endswith(
                b"setup_interpretation_failed\n"
            ):
                raise RuntimeError("installed interpretation false claim accepted")
            outcomes[scenario] = {
                "exit": 2,
                "rejected": True,
                "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            }
            continue
        try:
            value = json.loads(observed.stdout)
            _check_installed_interpretation(value, observed.stdout, scenario)
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("installed interpretation result invalid") from error
        evidence = value["evidence"]
        outcomes[scenario] = {
            "exit": code,
            "continuity_status": evidence["continuity"]["status"],
            "invalidation_status": evidence["invalidation"]["status"],
            "age_status": evidence["age"]["status"],
            "completed_sessions_elapsed": evidence["age"]["completed_sessions_elapsed"],
            "disposition": value["external_response"]["disposition"],
            "result_identity_sha256": value["result_identity_sha256"],
            "runtime_code_identity_sha256": value["runtime_code_identity_sha256"],
            "evidence_identity_sha256": evidence["result_identity_sha256"],
            "external_response_identity_sha256": value[
                "external_response_identity_sha256"
            ],
            "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            "imports": "SDK and injected CLI under installed sys.prefix with -I; actual outputs equal; no model evaluated",
        }
    return outcomes


def _verify_installed_evidence(
    python: Path, scratch: Path
) -> dict[str, dict[str, object]]:
    """Check the coherent handoff from isolated installed SDK and actual CLI."""
    probe = "\n".join(
        (
            "import pathlib, runpy, sys",
            "sys.dont_write_bytecode = True",
            "import swing_trading_ai_assistant.research_comparison.setup_evidence as sdk",
            "import swing_trading_ai_assistant.research_comparison.setup_evidence_cli as cli",
            "for module in (sdk, cli):",
            "    if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "        raise RuntimeError('evidence import escaped installed environment')",
            "fixture, scenario = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "runpy.run_path(fixture, run_name='__main__')",
        )
    )
    safe_env = {
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    outcomes = {}
    for scenario in ("same-event", "invalidated", "replay", "unknown"):
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/causal_setup_evidence_demo.py"),
                scenario,
            ],
            cwd=scratch,
            env=safe_env,
        )
        code = 1 if scenario == "unknown" else 0
        if (
            observed.returncode != code
            or len(observed.stdout) > 1024 * 1024
            or b"SYNTHETIC" not in observed.stderr
            or b"not current market data" not in observed.stderr
            or any(
                token in observed.stdout
                for token in (
                    b'"close"',
                    b'"open"',
                    b'"high"',
                    b'"low"',
                    b'"price"',
                    b'"volume"',
                    str(scratch).encode(),
                )
            )
        ):
            raise RuntimeError("installed evidence execution failed")
        try:
            value = json.loads(observed.stdout)
            _check_installed_evidence(value, observed.stdout, scenario)
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("installed evidence result invalid") from error
        outcomes[scenario] = {
            "exit": code,
            "continuity_status": value["continuity"]["status"],
            "invalidation_status": value["invalidation"]["status"],
            "age_status": value["age"]["status"],
            "completed_sessions_elapsed": value["age"]["completed_sessions_elapsed"],
            "result_identity_sha256": value["result_identity_sha256"],
            "runtime_code_identity_sha256": value["runtime_code_identity_sha256"],
            "previous_observation_identity_sha256": value[
                "previous_observation_identity_sha256"
            ],
            "current_observation_identity_sha256": value[
                "current_observation_identity_sha256"
            ],
            "component_identities": {
                name: value[name]["result_identity_sha256"]
                for name in ("continuity", "invalidation", "age")
            },
            "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            "imports": "SDK and injected CLI under installed sys.prefix with -I; exactly one admitted pair",
        }
    return outcomes


def _check_installed_evidence(value: dict, raw: bytes, scenario: str) -> None:
    """Falsify mixed revisions, fabricated facts and plausible-but-wrong bundles."""
    expected_versions = {
        "continuity": "causal-setup-event-continuity@v1",
        "invalidation": "causal-setup-invalidation@v1",
        "age": "causal-setup-age@v1",
    }
    if (
        set(value)
        != {
            "contract_version",
            "criterion",
            "runtime_code_identity_sha256",
            "previous_observation_identity_sha256",
            "current_observation_identity_sha256",
            "continuity",
            "invalidation",
            "age",
            "limitations",
            "result_identity_sha256",
        }
        or value["contract_version"] != "causal-setup-evidence@v1"
        or value["criterion"] != "LATEST_COMPLETED_UPWARD_BOS@v1"
        or raw
        != (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ):
        raise ValueError("evidence envelope disagrees with contract")
    for report in (value, *(value[name] for name in expected_versions)):
        unsigned = dict(report)
        identity = unsigned.pop("result_identity_sha256")
        if (
            identity
            != hashlib.sha256(
                (
                    json.dumps(unsigned, sort_keys=True, separators=(",", ":")) + "\n"
                ).encode()
            ).hexdigest()
        ):
            raise ValueError("evidence result identity invalid")
        for field in (
            "result_identity_sha256",
            "runtime_code_identity_sha256",
            "previous_observation_identity_sha256",
            "current_observation_identity_sha256",
        ):
            digest = report[field]
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
            ):
                raise ValueError("evidence digest invalid")
    continuity, invalidation, age = (value[name] for name in expected_versions)
    for name, version in expected_versions.items():
        report = value[name]
        if (
            report["contract_version"] != version
            or any(
                report[field] != value[field]
                for field in (
                    "previous_observation_identity_sha256",
                    "current_observation_identity_sha256",
                )
            )
            or any(report[side] != continuity[side] for side in ("previous", "current"))
        ):
            raise ValueError("evidence pair binding invalid")
    if any(
        value[name]["continuity_identity_sha256"]
        != continuity["result_identity_sha256"]
        for name in ("age", "invalidation")
    ):
        raise ValueError("evidence continuity binding invalid")
    expected = {
        "same-event": (
            "SAME_EVENT",
            "NO_CONTRADICTION_OBSERVED",
            "OBSERVED",
            1,
            "NO_MATCH",
        ),
        "invalidated": ("SAME_EVENT", "INVALIDATED", "OBSERVED", 1, "NO_MATCH"),
        "replay": ("REPLAY", "REPLAY", "REPLAY", 0, "MATCH"),
        "unknown": ("UNKNOWN", "UNKNOWN", "UNKNOWN", None, "UNKNOWN"),
    }[scenario]
    if (
        continuity["status"],
        invalidation["status"],
        age["status"],
        age["completed_sessions_elapsed"],
        age["current"]["status"],
    ) != expected or (
        expected[3] is not None and type(age["completed_sessions_elapsed"]) is not int
    ):
        raise ValueError("evidence facts disagree with contract")
    _check_evidence_witness(invalidation, scenario)


def _check_evidence_witness(invalidation: dict, scenario: str) -> None:
    """Bind the observed contradiction to the original causal supporting low."""
    witness = invalidation["contradiction"]
    if scenario == "invalidated":
        original, current_low = (
            invalidation["original_supporting_low"],
            invalidation["current_supporting_low"],
        )
        if (
            witness is None
            or witness["event"] != "CHOCH"
            or witness["direction"] != "DOWN"
            or witness["prior_trend"] != "UPTREND"
            or original["kind"] != "SWING_LOW"
            or original["relation"] != "HL"
            or not original["pivot_session"]
            < original["pivot_confirmation_session"]
            < invalidation["previous"]["candidate"]["event_session"]
            < witness["event_session"]
            or any(
                original[key] != current_low[key]
                for key in (
                    "kind",
                    "relation",
                    "pivot_session",
                    "pivot_confirmation_session",
                )
            )
            or any(
                witness[key] != current_low[key]
                for key in (
                    "pivot_session",
                    "pivot_confirmation_session",
                    "pivot_identity_sha256",
                )
            )
        ):
            raise ValueError("evidence contradiction witness invalid")
    elif witness is not None:
        raise ValueError("evidence invented contradiction")


def _verify_installed_age(python: Path, scratch: Path) -> dict[str, dict[str, object]]:
    """Exercise installed age SDK/CLI and retain exact public-output evidence."""
    probe = "\n".join(
        (
            "import pathlib, runpy, sys",
            "sys.dont_write_bytecode = True",
            "import swing_trading_ai_assistant.research_comparison.setup_age as sdk",
            "import swing_trading_ai_assistant.research_comparison.setup_age_cli as cli",
            "for module in (sdk, cli):",
            "    if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "        raise RuntimeError('age import escaped installed environment')",
            "fixture, scenario = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "runpy.run_path(fixture, run_name='__main__')",
        )
    )
    safe_env = {
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    outcomes: dict[str, dict[str, object]] = {}
    for scenario, status, continuity, current, count, code in (
        ("same-event", "OBSERVED", "SAME_EVENT", "NO_MATCH", 1, 0),
        ("replay", "REPLAY", "REPLAY", "MATCH", 0, 0),
        ("unknown", "UNKNOWN", "UNKNOWN", "UNKNOWN", None, 1),
    ):
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/causal_setup_age_demo.py"),
                scenario,
            ],
            cwd=scratch,
            env=safe_env,
        )
        if (
            observed.returncode != code
            or len(observed.stdout) > 1024 * 1024
            or b"SYNTHETIC" not in observed.stderr
            or b"not current market data" not in observed.stderr
            or any(
                token in observed.stdout
                for token in (
                    b'"close"',
                    b'"open"',
                    b'"high"',
                    b'"low"',
                    b'"price"',
                    b'"volume"',
                    str(scratch).encode(),
                )
            )
        ):
            raise RuntimeError("installed age execution failed")
        value = json.loads(observed.stdout)
        digests = tuple(
            value[key]
            for key in (
                "result_identity_sha256",
                "runtime_code_identity_sha256",
                "previous_observation_identity_sha256",
                "current_observation_identity_sha256",
                "continuity_identity_sha256",
            )
        )
        if (
            value["contract_version"] != "causal-setup-age@v1"
            or value["criterion"]
            != "ADMITTED_COMPLETED_SESSIONS_SINCE_ORIGINAL_UPWARD_BOS@v1"
            or value["status"] != status
            or value["continuity_status"] != continuity
            or value["current"]["status"] != current
            or value["completed_sessions_elapsed"] != count
            or (
                count is not None
                and type(value["completed_sessions_elapsed"]) is not int
            )
            or any(
                not isinstance(d, str)
                or len(d) != 64
                or any(c not in "0123456789abcdef" for c in d)
                for d in digests
            )
        ):
            raise RuntimeError("installed age result disagrees with contract")
        unsigned = dict(value)
        identity = unsigned.pop("result_identity_sha256")
        canonical = (
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        if (
            identity != hashlib.sha256(canonical).hexdigest()
            or observed.stdout
            != (
                json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        ):
            raise RuntimeError("installed age result identity invalid")
        _verify_age_endpoints(value, count)
        outcomes[scenario] = {
            "exit": code,
            "status": status,
            "completed_sessions_elapsed": count,
            "continuity_status": continuity,
            "current_projection_status": current,
            "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            "result_identity_sha256": digests[0],
            "runtime_code_identity_sha256": digests[1],
            "previous_observation_identity_sha256": digests[2],
            "current_observation_identity_sha256": digests[3],
            "imports": "SDK and actual injected CLI resolved under installed sys.prefix with -I",
        }
    return outcomes


def _verify_age_endpoints(value, count: int | None) -> None:
    if count is None:
        if any(
            value[key] is not None
            for key in (
                "original_event_session",
                "current_completed_session",
                "schedules",
            )
        ):
            raise RuntimeError("installed age fabricated count evidence")
    else:
        original, latest = (
            value["original_event_session"],
            value["current_completed_session"],
        )
        if (
            original != value["previous"]["candidate"]["event_session"]
            or not isinstance(original, str)
            or not isinstance(latest, str)
            or (count == 0 and original != latest)
            or (count > 0 and original >= latest)
            or not isinstance(value["schedules"], dict)
            or set(value["schedules"]) != {"previous", "current"}
        ):
            raise RuntimeError("installed age endpoint invalid")
        for schedule in value["schedules"].values():
            for key in ("evidence_identity_sha256", "schedule_identity_sha256"):
                digest = schedule[key]
                if (
                    not isinstance(digest, str)
                    or len(digest) != 64
                    or any(c not in "0123456789abcdef" for c in digest)
                ):
                    raise RuntimeError("installed age schedule identity invalid")


def _verify_installed_continuity(
    python: Path, scratch: Path
) -> dict[str, dict[str, object]]:
    """Exercise the new SDK/CLI from the clean wheel using reviewed source fixtures.

    Isolation removes checkout/PYTHONPATH imports. Both changed public modules
    must resolve inside the installed environment before the synthetic producer
    loads. The fixture is source-checkout evidence, not an installed entrypoint.
    """
    probe = "\n".join(
        (
            "import pathlib, runpy, sys",
            "sys.dont_write_bytecode = True",
            "import swing_trading_ai_assistant.research_comparison.setup_event_continuity as sdk",
            "import swing_trading_ai_assistant.research_comparison.setup_event_continuity_cli as cli",
            "for module in (sdk, cli):",
            "    if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "        raise RuntimeError('continuity import escaped installed environment')",
            "fixture, scenario = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "runpy.run_path(fixture, run_name='__main__')",
        )
    )
    safe_env = {
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    outcomes: dict[str, dict[str, object]] = {}
    for scenario, status, current_status, code in (
        ("same-event", "SAME_EVENT", "NO_MATCH", 0),
        ("unknown", "UNKNOWN", "UNKNOWN", 1),
    ):
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/causal_setup_event_continuity_demo.py"),
                scenario,
            ],
            cwd=scratch,
            env=safe_env,
        )
        if (
            observed.returncode != code
            or len(observed.stdout) > 1024 * 1024
            or b"SYNTHETIC" not in observed.stderr
            or b"not current market data" not in observed.stderr
        ):
            raise RuntimeError("installed continuity execution failed")
        value = json.loads(observed.stdout)
        digests = (
            value["result_identity_sha256"],
            value["runtime_code_identity_sha256"],
        )
        if (
            value["contract_version"] != "causal-setup-event-continuity@v1"
            or value["status"] != status
            or value["current"]["status"] != current_status
            or any(
                not isinstance(digest, str)
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
                for digest in digests
            )
            or any(
                token in observed.stdout
                for token in (
                    b'"close"',
                    b'"open"',
                    b'"high"',
                    b'"low"',
                    str(scratch).encode(),
                )
            )
        ):
            raise RuntimeError("installed continuity result disagrees with contract")
        outcomes[scenario] = {
            "exit": code,
            "status": status,
            "current_projection_status": current_status,
            "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            "result_identity_sha256": digests[0],
            "runtime_code_identity_sha256": digests[1],
            "imports": "SDK and injected CLI resolved under installed sys.prefix with -I",
        }
    return outcomes


def _verify_installed_invalidation(
    python: Path, scratch: Path
) -> dict[str, dict[str, object]]:
    """Exercise the new SDK/CLI from the clean wheel using reviewed source fixtures.

    Isolation removes checkout/PYTHONPATH imports. Both changed public modules
    must resolve inside the installed environment before the synthetic producer
    loads. The fixture is source-checkout evidence, not an installed entrypoint.
    """
    probe = "\n".join(
        (
            "import pathlib, runpy, sys",
            "sys.dont_write_bytecode = True",
            "import swing_trading_ai_assistant.research_comparison.setup_invalidation as sdk",
            "import swing_trading_ai_assistant.research_comparison.setup_invalidation_cli as cli",
            "for module in (sdk, cli):",
            "    if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "        raise RuntimeError('invalidation import escaped installed environment')",
            "fixture, scenario = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "runpy.run_path(fixture, run_name='__main__')",
        )
    )
    safe_env = {
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    outcomes: dict[str, dict[str, object]] = {}
    for scenario, status, current_status, code in (
        ("invalidated", "INVALIDATED", "NO_MATCH", 0),
        ("no-contradiction", "NO_CONTRADICTION_OBSERVED", "NO_MATCH", 0),
        ("unknown", "UNKNOWN", "UNKNOWN", 1),
    ):
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/causal_setup_invalidation_demo.py"),
                scenario,
            ],
            cwd=scratch,
            env=safe_env,
        )
        if (
            observed.returncode != code
            or len(observed.stdout) > 1024 * 1024
            or b"SYNTHETIC" not in observed.stderr
            or b"not current market data" not in observed.stderr
        ):
            raise RuntimeError("installed invalidation execution failed")
        value = json.loads(observed.stdout)
        digests = (
            value["result_identity_sha256"],
            value["runtime_code_identity_sha256"],
        )
        if (
            value["contract_version"] != "causal-setup-invalidation@v1"
            or value["criterion"] != "LATER_DOWN_CHOCH_OF_ORIGINAL_CONFIRMED_HL@v1"
            or value["status"] != status
            or value["current"]["status"] != current_status
            or any(
                not isinstance(digest, str)
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
                for digest in digests
            )
            or any(
                token in observed.stdout
                for token in (
                    b'"close"',
                    b'"open"',
                    b'"high"',
                    b'"low"',
                    str(scratch).encode(),
                )
            )
        ):
            raise RuntimeError("installed invalidation result disagrees with contract")
        unsigned = dict(value)
        identity = unsigned.pop("result_identity_sha256")
        canonical = (
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        if identity != hashlib.sha256(canonical).hexdigest():
            raise RuntimeError("installed invalidation result identity invalid")
        witness = value["contradiction"]
        if status == "INVALIDATED":
            original = value["original_supporting_low"]
            current_low = value["current_supporting_low"]
            candidate = value["previous"]["candidate"]
            if (
                witness is None
                or witness["event"] != "CHOCH"
                or witness["direction"] != "DOWN"
                or witness["prior_trend"] != "UPTREND"
                or original["kind"] != "SWING_LOW"
                or original["relation"] != "HL"
                or not original["pivot_session"]
                < original["pivot_confirmation_session"]
                < candidate["event_session"]
                < witness["event_session"]
                or any(
                    original[key] != current_low[key]
                    for key in (
                        "kind",
                        "relation",
                        "pivot_session",
                        "pivot_confirmation_session",
                    )
                )
                or witness["pivot_identity_sha256"]
                != current_low["pivot_identity_sha256"]
                or witness["pivot_session"] != original["pivot_session"]
                or witness["pivot_confirmation_session"]
                != original["pivot_confirmation_session"]
            ):
                raise RuntimeError("installed invalidation witness invalid")
        elif witness is not None:
            raise RuntimeError("installed invalidation invented contradiction")
        outcomes[scenario] = {
            "exit": code,
            "status": status,
            "current_projection_status": current_status,
            "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            "result_identity_sha256": digests[0],
            "runtime_code_identity_sha256": digests[1],
            "imports": "SDK and injected CLI resolved under installed sys.prefix with -I",
        }
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


def _podman_generation() -> int:
    descriptor = os.open(
        _PODMAN_GENERATION, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    )
    try:
        info = os.fstat(descriptor)
        value = os.read(descriptor, 3)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o640
            or value not in (b"1\n", b"2\n")
        ):
            raise RuntimeError("invalid private Podman recovery evidence")
        return int(value)
    finally:
        os.close(descriptor)


def _job_podman() -> bool:
    return (
        Path(_engine()).name == "podman"
        and not _PODMAN_ROOTLESS
        and os.environ.get("CONTAINER_HOST") == "unix:///ci/podman.sock"
    )


def _wait_for_podman_recovery(before: int) -> None:
    deadline = time.monotonic() + 10
    while True:
        elapsed = time.monotonic() >= deadline
        generation = _podman_generation()
        # Remote cancellation can answer info before asynchronous cleanup aborts.
        # Observe the original service for the full cancellation window; a
        # replacement has already crossed that abort boundary.
        if generation == before + 1 or elapsed:
            try:
                health = _run([_engine(), "info", "--format", "{{json .}}"], timeout=1)
            except subprocess.TimeoutExpired:
                pass
            else:
                if health.returncode == 0:
                    return
        if elapsed:
            break
        time.sleep(0.1)
    raise RuntimeError("private Podman engine did not recover after interruption")


def _verify_interrupted_build(build: list[str], image: str) -> None:
    generation = _podman_generation() if _job_podman() else None
    if generation is not None and generation != 1:
        raise RuntimeError("private Podman engine restarted before interruption")
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
    if generation is not None:
        _wait_for_podman_recovery(generation)
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
        continuity = _verify_installed_continuity(python, scratch)
        invalidation = _verify_installed_invalidation(python, scratch)
        age = _verify_installed_age(python, scratch)
        evidence = _verify_installed_evidence(python, scratch)
        interpretation = _verify_installed_interpretation(python, scratch)
        level = _verify_installed_level(python, scratch)
        level_interpretation = _verify_installed_level_interpretation_v2(
            python, scratch
        )
        level_range = _verify_installed_level_range(python, scratch)
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
            "installed_setup_event_continuity": continuity,
            "installed_setup_invalidation": invalidation,
            "installed_setup_age": age,
            "installed_setup_evidence": evidence,
            "installed_setup_interpretation": interpretation,
            "installed_setup_level": level,
            "installed_setup_level_range": level_range,
            "installed_setup_level_interpretation_v2": level_interpretation,
            "mount_checks": "owner mapped, wrong UID, broad mode, read-only, symlink",
            "source_substitution": "rejected",
            "interrupted_build_and_run": "rejected; current image remained available",
            "private_podman_service_restarts": (
                _podman_generation() - 1 if _job_podman() else 0
            ),
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
