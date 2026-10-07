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


def _check_installed_evidence_v3(
    value: dict, raw: bytes, scenario: str, references: dict
) -> None:
    """Compare all nested bytes with separately regenerated, source-closed APIs."""
    if set(references) != {
        "legacy_v1",
        "legacy_v2",
        "level",
        "level_range",
        "evidence_runtime",
        "interpretation_runtime",
    }:
        raise ValueError("v3 independent references invalid")
    legacy, original, level, level_range = (
        references[name] for name in ("legacy_v2", "legacy_v1", "level", "level_range")
    )
    level_scenario = {
        "contains": "above",
        "low-equal": "above",
        "high-equal": "below",
        "invalidated": "below",
        "no-trade": "above",
    }.get(scenario, scenario)
    range_scenario = {"invalidated": "below", "no-trade": "contains"}.get(
        scenario, scenario
    )
    old_scenario = (
        scenario if scenario in ("invalidated", "replay", "unknown") else "same-event"
    )
    _check_installed_level(level, _interpretation_bytes(level), level_scenario)
    _check_installed_level_range(
        level_range, _interpretation_bytes(level_range), range_scenario
    )
    _check_installed_evidence_v2(
        legacy,
        _interpretation_bytes(legacy),
        "invalidated" if scenario == "invalidated" else level_scenario,
    )
    _check_installed_evidence(original, _interpretation_bytes(original), old_scenario)
    # Preserve original Plan54 AND Plan56 references, not a resealed candidate projection.
    if (
        _interpretation_bytes(legacy["level"]) != _interpretation_bytes(level)
        or legacy["legacy_evidence_identity_sha256"]
        != original["result_identity_sha256"]
        or any(
            _interpretation_bytes(legacy[name]) != _interpretation_bytes(original[name])
            for name in ("continuity", "invalidation", "age")
        )
        or level_range["level_identity_sha256"] != level["result_identity_sha256"]
        or any(
            level_range[key] != level[key]
            for key in (
                "previous",
                "current",
                "previous_observation_identity_sha256",
                "current_observation_identity_sha256",
                "continuity_identity_sha256",
                "continuity_status",
                "status",
                "witness",
            )
        )
    ):
        raise ValueError("v3 independent upstream reference invalid")
    for name in ("continuity", "invalidation", "age", "level"):
        for side in ("previous", "current"):
            _check_level_range_row(legacy[name][side], side, range_scenario)
    expected = dict(legacy)
    expected.pop("result_identity_sha256")
    expected.update(
        contract_version="causal-setup-evidence@v3",
        legacy_evidence_v2_identity_sha256=legacy["result_identity_sha256"],
        level_range=level_range,
        runtime_code_identity_sha256=references["evidence_runtime"],
        limitations=[
            *legacy["limitations"],
            "Inclusive latest low/high containment is descriptive; it proves no exact traded tick, successful retest, confirmation, validity or eligibility.",
        ],
    )
    expected["result_identity_sha256"] = hashlib.sha256(
        _interpretation_bytes(expected)
    ).hexdigest()
    if raw != _interpretation_bytes(value) or raw != _interpretation_bytes(expected):
        raise ValueError("v3 exact nested evidence invalid")


def _check_installed_interpretation_v3(
    value: dict, raw: bytes, scenario: str, references: dict
) -> None:
    """Falsify a resealed mutation at any nested depth without trusting its seal."""
    evidence = value["evidence"]
    _check_installed_evidence_v3(
        evidence, _interpretation_bytes(evidence), scenario, references
    )
    facts = {
        name: {
            key: evidence[name][key]
            for key in (
                "result_identity_sha256",
                "status",
                *(
                    ("completed_sessions_elapsed",)
                    if name == "age"
                    else ("relation",)
                    if name == "level"
                    else ("range_relation",)
                    if name == "level_range"
                    else ()
                ),
            )
        }
        for name in ("continuity", "invalidation", "age", "level", "level_range")
    }
    response = {
        "schema": "external-setup-interpretation-request@v3",
        "evidence_identity_sha256": evidence["result_identity_sha256"],
        "disposition": "NO_TRADE" if scenario == "no-trade" else "RESEARCH_ONLY",
        "explanation": "Caller-authored synthetic research posture; facts unchanged, narrative accuracy and eligibility unassessed.",
        "facts": facts,
    }
    expected = {
        "contract_version": "external-setup-interpretation-check@v3",
        "evidence": evidence,
        "external_response": response,
        "external_response_identity_sha256": hashlib.sha256(
            _interpretation_bytes(response)
        ).hexdigest(),
        "runtime_code_identity_sha256": references["interpretation_runtime"],
        "verification": "STRUCTURED_BINDING_ONLY",
        "explanation_accuracy": "NOT_ASSESSED",
        "external_authorship": "CALLER_SUPPLIED_NOT_AUTHENTICATED",
        "actionable_recommendation": "NOT_ASSESSED",
        "eligibility": "NOT_ASSESSED",
        "effectiveness": "NOT_ASSESSED",
        "limitations": [
            "Only structured claims and exact admitted evidence references are checked; success grants no trade authorization.",
            "Explanation is untrusted caller text; its truth, usefulness and external model authorship are not verified.",
            "Caller research-only/no-trade posture is preserved without a tool recommendation, eligibility, effectiveness or expiry policy.",
            "Continuity, invalidation, age, close and range remain independent; range inclusion proves no exact traded tick, successful retest or confirmation; age or ABOVE cannot override contradiction/missing evidence and BELOW does not establish structural invalidation.",
        ],
    }
    expected["result_identity_sha256"] = hashlib.sha256(
        _interpretation_bytes(expected)
    ).hexdigest()
    if (
        len(raw) > 1024 * 1024
        or raw != _interpretation_bytes(value)
        or raw != _interpretation_bytes(expected)
    ):
        raise ValueError("v3 exact interpretation invalid")


def _verify_installed_range_interpretation_v3(
    python: Path, scratch: Path
) -> dict[str, dict[str, object]]:
    """Actual isolated installed execution with independent original component receipts."""
    probe = "\n".join(
        (
            "import json, os, pathlib, runpy, sys",
            "sys.dont_write_bytecode = True",
            "from swing_trading_ai_assistant.research_comparison import setup_interpretation_v3 as sdk, setup_interpretation_v3_cli as cli, setup_evidence_v3 as bundle, setup_evidence_v3_cli as bundle_cli, setup_evidence_v2 as old, setup_evidence as v1, setup_level as level, setup_level_range as level_range",
            "for module in (sdk, cli, bundle, bundle_cli, old, v1, level, level_range):",
            "    if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "        raise RuntimeError('v3 import escaped installed environment')",
            "fixture, scenario, reference = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "namespace = runpy.run_path(fixture, run_name='installed_qualification')",
            "code = namespace['main']()",
            "references = namespace['main'].__globals__['QUALIFICATION_REFERENCES']",
            "descriptor = os.open(reference, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)",
            "with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:",
            "    stream.write(json.dumps(references, sort_keys=True, separators=(',', ':')) + '\\n')",
            "raise SystemExit(code)",
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
    for scenario in (
        "contains",
        "above",
        "below",
        "low-equal",
        "high-equal",
        "invalidated",
        "replay",
        "unknown",
        "no-trade",
        "false-claim",
    ):
        reference = scratch / ("v3-original-references-" + scenario + ".json")
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/causal_setup_range_interpretation_v3_demo.py"),
                scenario,
                str(reference),
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
                    b'"bars"',
                    b'"body"',
                    b'"api_key"',
                    str(scratch).encode(),
                )
            )
        ):
            raise RuntimeError("installed v3 execution failed")
        if scenario == "false-claim":
            if observed.stdout or not observed.stderr.endswith(
                b"setup_interpretation_failed\n"
            ):
                raise RuntimeError("installed v3 false range accepted")
            outcomes[scenario] = {
                "exit": 2,
                "rejected": True,
                "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            }
            continue
        try:
            references = json.loads(reference.read_bytes())
            value = json.loads(observed.stdout)
            _check_installed_interpretation_v3(
                value, observed.stdout, scenario, references
            )
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError("installed v3 result invalid") from error
        evidence = value["evidence"]
        outcomes[scenario] = {
            "exit": code,
            "statuses": {
                name: evidence[name]["status"]
                for name in (
                    "continuity",
                    "invalidation",
                    "age",
                    "level",
                    "level_range",
                )
            },
            "relation": evidence["level"]["relation"],
            "range_relation": evidence["level_range"]["range_relation"],
            "completed_sessions_elapsed": evidence["age"]["completed_sessions_elapsed"],
            "disposition": value["external_response"]["disposition"],
            "result_identity_sha256": value["result_identity_sha256"],
            "runtime_code_identity_sha256": value["runtime_code_identity_sha256"],
            "evidence_identity_sha256": evidence["result_identity_sha256"],
            "legacy_evidence_v2_identity_sha256": evidence[
                "legacy_evidence_v2_identity_sha256"
            ],
            "level_identity_sha256": evidence["level"]["result_identity_sha256"],
            "range_identity_sha256": evidence["level_range"]["result_identity_sha256"],
            "original_references_sha256": hashlib.sha256(
                reference.read_bytes()
            ).hexdigest(),
            "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            "imports": "Installed SDK and both injected CLIs with -I; original v1/v2/Plan54/Plan56 APIs independently regenerated; all nested canonical bytes exact; no model evaluated",
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


def _check_inclusion_reference_row(row: object, side: str, scenario: str) -> None:
    """Close the redacted row for these fixed synthetic installed scenarios."""
    unknown = side == "current" and scenario == "unknown"
    later = side == "current" and scenario not in ("replay", "unknown", "refresh")
    status = "UNKNOWN" if unknown else "NO_MATCH" if later else "MATCH"
    instant = (
        "2026-08-26T04:16:00.000000Z"
        if unknown or side == "current" and scenario == "refresh"
        else "2026-08-28T04:15:00.000000Z"
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
        "session": "2026-08-27" if later else "2026-08-25",
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


def _check_inclusion_latest_reference(value: dict, raw: bytes, scenario: str) -> None:
    observed = scenario not in ("replay", "unknown", "refresh")
    status = (
        "OBSERVED"
        if observed
        else "NO_LATER_SESSION"
        if scenario == "refresh"
        else scenario.upper()
    )
    reason = (
        "LATEST_COMPLETED_RANGE_COMPARED_WITH_ORIGINAL_BROKEN_HIGH"
        if observed
        else "IDENTICAL_ADMITTED_OBSERVATION"
        if scenario == "replay"
        else "NO_COMPLETED_SESSION_AFTER_ORIGINAL_EVENT"
        if scenario == "refresh"
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
        or value["continuity_status"]
        != ("SAME_EVENT" if observed or scenario == "refresh" else status)
        or value["range_relation"]
        != (
            (
                "CONTAINS_LEVEL"
                if scenario in ("latest", "multiple", "invalidated")
                else "ENTIRELY_ABOVE"
            )
            if observed
            else None
        )
        or value["previous"]["status"] != "MATCH"
        or value["current"]["status"]
        != (
            "NO_MATCH"
            if observed
            else "MATCH"
            if scenario in ("replay", "refresh")
            else "UNKNOWN"
        )
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
        _check_inclusion_reference_row(value[side], side, scenario)
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


def _check_installed_range_inclusion(
    value: dict, raw: bytes, scenario: str, references: dict
) -> None:
    """Close all fields against original independently regenerated Plan54/56 APIs."""
    if set(references) != {
        "level",
        "latest_range",
        "evaluated_post_event_bars",
        "first_inclusion",
        "runtime_code_identity_sha256",
    }:
        raise ValueError("range inclusion reference inventory invalid")
    level, latest = references["level"], references["latest_range"]
    _check_inclusion_latest_reference(latest, _interpretation_bytes(latest), scenario)
    observed = scenario not in ("replay", "unknown", "refresh")
    expected_level = dict(latest)
    expected_level.pop("range_relation")
    expected_level.pop("level_identity_sha256")
    expected_level.pop("result_identity_sha256")
    expected_level.update(
        contract_version="causal-setup-level@v1",
        criterion="LATEST_COMPLETED_CLOSE_VS_ORIGINAL_BROKEN_HIGH@v1",
        runtime_code_identity_sha256=level["runtime_code_identity_sha256"],
        reason="LATEST_COMPLETED_CLOSE_COMPARED_WITH_ORIGINAL_BROKEN_HIGH"
        if observed
        else latest["reason"],
        relation=("BELOW" if scenario == "invalidated" else "ABOVE")
        if observed
        else None,
        limitations=[
            "Exact completed-close relation only; no intrabar path, touch or retest claim.",
            "ABOVE is not confirmation, validity, eligibility, recommendation, effectiveness or trade authorization.",
            "BELOW is not structural invalidation; Plan50 remains an independent fact.",
            "The original unchanged causal high must remain represented in the finite admitted window.",
            "No tolerance, threshold, expiry, persistence, monitoring or external model.",
        ],
    )
    expected_level["result_identity_sha256"] = hashlib.sha256(
        _interpretation_bytes(expected_level)
    ).hexdigest()
    if (
        _interpretation_bytes(level) != _interpretation_bytes(expected_level)
        or latest["level_identity_sha256"] != level["result_identity_sha256"]
    ):
        raise ValueError("range inclusion original level reference invalid")
    for identity in (
        level["runtime_code_identity_sha256"],
        references["runtime_code_identity_sha256"],
    ):
        if type(identity) is not str or re.fullmatch(r"[0-9a-f]{64}", identity) is None:
            raise ValueError("range inclusion reference runtime invalid")
    evaluated = references["evaluated_post_event_bars"]
    first = references["first_inclusion"]
    if observed:
        if (
            type(evaluated) is not list
            or len(evaluated) != 2
            or any(
                type(row) is not dict or set(row) != {"session", "bar_identity_sha256"}
                for row in evaluated
            )
            or [row["session"] for row in evaluated] != ["2026-08-26", "2026-08-27"]
            or any(
                type(row["bar_identity_sha256"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", row["bar_identity_sha256"]) is None
                for row in evaluated
            )
            or evaluated[-1]["bar_identity_sha256"]
            != latest["witness"]["current_bar_identity_sha256"]
        ):
            raise ValueError("range inclusion admitted reference bars invalid")
        index = {
            "earlier": 0,
            "none": None,
            "latest": 1,
            "multiple": 0,
            "low-equal": 0,
            "high-equal": 0,
            "nearest-above": None,
            "nearest-below": None,
            "event-only": None,
            "invalidated": 0,
        }[scenario]
        if first != (evaluated[index] if index is not None else None):
            raise ValueError("range inclusion first reference invalid")
    elif evaluated is not None or first is not None:
        raise ValueError("range inclusion invented reference facts")
    expected = dict(latest)
    expected.pop("range_relation")
    expected.pop("result_identity_sha256")
    expected.update(
        contract_version="causal-setup-level-range-inclusion@v1",
        criterion="EARLIEST_COMPLETED_POST_EVENT_RANGE_INCLUSION@v1",
        runtime_code_identity_sha256=references["runtime_code_identity_sha256"],
        latest_range_identity_sha256=latest["result_identity_sha256"],
        reason="COMPLETED_POST_EVENT_RANGE_INCLUSION_EVALUATED"
        if observed
        else latest["reason"],
        inclusion_observed=(first is not None) if observed else None,
        evaluated_post_event_bars=evaluated,
        first_inclusion=first,
        limitations=[
            "Earliest inclusive completed-bar range only within the fully admitted current post-event window; not first lifetime contact.",
            "Range inclusion proves no exact traded tick, intrabar ordering, reclaim, successful retest or confirmation.",
            "No validity, eligibility, recommendation, effectiveness, expiry or trade authorization is inferred; structural invalidation remains independent.",
            "Original unchanged causal high and event must remain represented in the finite21-session window; missing evidence is not a negative finding.",
            "No tolerance, threshold, history store, persistence, monitoring, new acquisition or external model.",
        ],
    )
    expected["result_identity_sha256"] = hashlib.sha256(
        _interpretation_bytes(expected)
    ).hexdigest()
    if (
        len(raw) > 1024 * 1024
        or raw != _interpretation_bytes(value)
        or raw != _interpretation_bytes(expected)
    ):
        raise ValueError("range inclusion exact installed result invalid")


def _verify_installed_range_inclusion(
    python: Path, scratch: Path
) -> dict[str, dict[str, object]]:
    """Actual -I installed SDK/CLI and original transitive component closure."""
    probe = "\n".join(
        (
            "import json, os, pathlib, runpy, sys",
            "sys.dont_write_bytecode = True",
            "from swing_trading_ai_assistant.research_comparison import setup_level_range_inclusion as sdk, setup_level_range_inclusion_cli as cli, setup_level_range as original_range, setup_level as original_level",
            "for name, module in tuple(sys.modules.items()):",
            "    if name.startswith('swing_trading_ai_assistant') and getattr(module, '__file__', None):",
            "        if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "            raise RuntimeError('inclusion import escaped installed environment')",
            "fixture, scenario, reference = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "namespace = runpy.run_path(fixture, run_name='installed_qualification')",
            "code = namespace['main']()",
            "references = namespace['main'].__globals__['QUALIFICATION_REFERENCES']",
            "descriptor = os.open(reference, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)",
            "with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:",
            "    stream.write(json.dumps(references, sort_keys=True, separators=(',', ':')) + '\\n')",
            "raise SystemExit(code)",
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
    for scenario in (
        "earlier",
        "none",
        "latest",
        "multiple",
        "low-equal",
        "high-equal",
        "nearest-above",
        "nearest-below",
        "event-only",
        "invalidated",
        "replay",
        "unknown",
        "refresh",
    ):
        reference = scratch / (
            "range-inclusion-original-references-" + scenario + ".json"
        )
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/causal_setup_level_range_inclusion_demo.py"),
                scenario,
                str(reference),
            ],
            cwd=scratch,
            env=safe_env,
        )
        code = 1 if scenario == "unknown" else 0
        if (
            observed.returncode != code
            or len(observed.stdout) > 1024 * 1024
            or b"SYNTHETIC RANGE INCLUSION" not in observed.stderr
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
                    b'"api_key"',
                    str(scratch).encode(),
                )
            )
        ):
            raise RuntimeError("installed range inclusion execution failed")
        try:
            references = json.loads(reference.read_bytes())
            value = json.loads(observed.stdout)
            _check_installed_range_inclusion(
                value, observed.stdout, scenario, references
            )
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError("installed range inclusion result invalid") from error
        outcomes[scenario] = {
            "exit": code,
            "status": value["status"],
            "inclusion_observed": value["inclusion_observed"],
            "first_inclusion": value["first_inclusion"],
            "evaluated_post_event_bars": value["evaluated_post_event_bars"],
            "result_identity_sha256": value["result_identity_sha256"],
            "runtime_code_identity_sha256": value["runtime_code_identity_sha256"],
            "latest_range_identity_sha256": value["latest_range_identity_sha256"],
            "level_identity_sha256": value["level_identity_sha256"],
            "previous_observation_identity_sha256": value[
                "previous_observation_identity_sha256"
            ],
            "current_observation_identity_sha256": value[
                "current_observation_identity_sha256"
            ],
            "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            "imports": "-I installed SDK/CLI/transitive runtime under sys.prefix; exact SDK/CLI equality; strict original Plan54/56 nested closure; synthetic descriptive fact only",
        }
    return outcomes


_V4_REFERENCE_KEYS = {
    "age": {
        "completed_sessions_elapsed",
        "continuity_identity_sha256",
        "continuity_status",
        "contract_version",
        "criterion",
        "current",
        "current_completed_session",
        "current_observation_identity_sha256",
        "limitations",
        "original_event_session",
        "previous",
        "previous_observation_identity_sha256",
        "reason",
        "result_identity_sha256",
        "runtime_code_identity_sha256",
        "schedules",
        "status",
    },
    "continuity": {
        "comparison_identity_sha256",
        "comparison_status",
        "contract_version",
        "criterion",
        "current",
        "current_observation_identity_sha256",
        "current_representation",
        "limitations",
        "previous",
        "previous_observation_identity_sha256",
        "reason",
        "result_identity_sha256",
        "runtime_code_identity_sha256",
        "status",
    },
    "invalidation": {
        "continuity_identity_sha256",
        "continuity_status",
        "contract_version",
        "contradiction",
        "criterion",
        "current",
        "current_observation_identity_sha256",
        "current_supporting_low",
        "limitations",
        "original_supporting_low",
        "previous",
        "previous_observation_identity_sha256",
        "reason",
        "result_identity_sha256",
        "runtime_code_identity_sha256",
        "status",
    },
    "v1": {
        "age",
        "continuity",
        "contract_version",
        "criterion",
        "current_observation_identity_sha256",
        "invalidation",
        "limitations",
        "previous_observation_identity_sha256",
        "result_identity_sha256",
        "runtime_code_identity_sha256",
    },
}

_V4_FIXED_LIMITATIONS = {
    "age": [
        "Age is a descriptive count under the current admitted schedule; not expiry, "
        "validity, active status or holding horizon.",
        "Age does not reverse invalidation or establish eligibility, recommendation "
        "or effectiveness.",
        "Count requires unchanged original event and anchor representation in the "
        "finite admitted window.",
        "No calendar-day substitution, future evidence, persistence or monitoring.",
    ],
    "continuity": [
        "Event representation is not validity, invalidation, expiry or a new "
        "trading opportunity.",
        "Rolling-window loss and missing evidence do not establish event "
        "removal or publisher correction lineage.",
        "No persistence, monitoring, eligibility, recommendation or "
        "effectiveness claim.",
    ],
    "interpretation": [
        "Only structured claims and exact admitted evidence references are "
        "checked; success grants no trade authorization.",
        "Explanation is untrusted caller text; its truth, usefulness and "
        "external model authorship are not verified.",
        "Caller research-only/no-trade posture is preserved without a tool "
        "recommendation, eligibility, effectiveness or expiry policy.",
        "Continuity, invalidation, age, close, latest range and earliest "
        "completed inclusion remain independent; inclusion within the "
        "finite admitted window proves no exact tick, lifetime first "
        "contact, successful retest or confirmation; age/ABOVE cannot "
        "override contradiction/missing evidence.",
    ],
    "invalidation": [
        "INVALIDATED contradicts only this original upward continuation "
        "premise; the historical BOS remains a fact.",
        "Absence of this witness never establishes validity, trade "
        "eligibility or profitability.",
        "Revisions, unknown evidence and rolling-window absence do not "
        "establish contradiction.",
        "No expiry, persistence, monitoring, recommendation or effectiveness claim.",
    ],
    "v1": [
        "The deterministic tool owns admitted facts, timing, identities and "
        "provenance; the external AI owns contextual recommendation or no-trade "
        "reasoning.",
        "The AI must not invent or recompute market facts, mint provenance or override "
        "integrity failures.",
        "Continuity and age do not imply validity or override observed structural "
        "contradiction.",
        "Actionable recommendation, eligibility and effectiveness are not assessed; no "
        "active or tradable candidate verdict is produced.",
        "Optional analytical context must not become hidden hard filters without an "
        "accepted strategy contract.",
        "No expiry, persistence, monitoring or broker-order authority is granted.",
    ],
}


def _v4_sealed(value: dict, keys: set[str]) -> None:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("v4 original closed envelope invalid")
    unsigned = dict(value)
    identity = unsigned.pop("result_identity_sha256")
    if identity != hashlib.sha256(_interpretation_bytes(unsigned)).hexdigest():
        raise ValueError("v4 original unsigned identity invalid")
    for key, digest in value.items():
        if (
            key.endswith("sha256")
            and digest is not None
            and (
                type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            )
        ):
            raise ValueError("v4 original digest invalid")


def _check_v4_original_continuity(
    continuity, latest, scenario, status, reason, observed
):
    if (
        continuity["criterion"],
        continuity["status"],
        continuity["reason"],
        continuity["comparison_status"],
    ) != (
        "LATEST_COMPLETED_UPWARD_BOS@v1",
        status,
        reason,
        "UNKNOWN"
        if scenario == "unknown"
        else "REPLAY"
        if scenario == "replay"
        else "ABSENT"
        if observed
        else "SAME_EVENT",
    ):
        raise ValueError("v4 original continuity semantics invalid")
    representation = continuity["current_representation"]
    candidate = latest["previous"]["candidate"]
    if scenario == "unknown":
        if representation is not None:
            raise ValueError("v4 unknown representation invented")
    elif (
        type(representation) is not dict
        or set(representation) != set(candidate)
        or any(
            representation[key] != candidate[key]
            for key in candidate
            if not key.endswith("sha256")
        )
        or any(
            re.fullmatch(r"[0-9a-f]{64}", representation[key]) is None
            for key in candidate
            if key.endswith("sha256")
        )
    ):
        raise ValueError("v4 original representation invalid")
    elif (
        observed
        and (
            representation["event_identity_sha256"]
            != latest["witness"]["represented_event_identity_sha256"]
            or representation["pivot_identity_sha256"]
            != latest["witness"]["represented_high_identity_sha256"]
        )
        or scenario == "replay"
        and representation != candidate
    ):
        raise ValueError("v4 original represented anchor invalid")


def _check_v4_original_invalidation(invalidation, scenario, status, reason):
    invalid_status = (
        "INVALIDATED"
        if scenario == "invalidated"
        else "NO_CONTRADICTION_OBSERVED"
        if status == "SAME_EVENT"
        else status
    )
    invalid_reason = (
        "LATER_DOWN_CHOCH_OF_ORIGINAL_CONFIRMED_HL"
        if scenario == "invalidated"
        else "NO_LATER_CHOCH_OF_ORIGINAL_HL"
        if status == "SAME_EVENT"
        else reason
    )
    if (invalidation["criterion"], invalidation["status"], invalidation["reason"]) != (
        "LATER_DOWN_CHOCH_OF_ORIGINAL_CONFIRMED_HL@v1",
        invalid_status,
        invalid_reason,
    ):
        raise ValueError("v4 independent invalidation semantics invalid")
    low_keys = {
        "kind",
        "relation",
        "pivot_session",
        "pivot_confirmation_session",
        "pivot_identity_sha256",
    }
    for key in ("original_supporting_low", "current_supporting_low"):
        low = invalidation[key]
        if status != "SAME_EVENT":
            if low is not None:
                raise ValueError("v4 inconclusive low invented")
        elif (
            type(low) is not dict
            or set(low) != low_keys
            or (
                low["kind"],
                low["relation"],
                low["pivot_session"],
                low["pivot_confirmation_session"],
            )
            != ("SWING_LOW", "HL", "2026-08-14", "2026-08-18")
            or re.fullmatch(r"[0-9a-f]{64}", low["pivot_identity_sha256"]) is None
        ):
            raise ValueError("v4 original supporting low invalid")
    _check_evidence_witness(
        invalidation, "invalidated" if scenario == "invalidated" else "same-event"
    )
    if scenario == "invalidated":
        witness = invalidation["contradiction"]
        if (
            set(witness)
            != {
                "event",
                "direction",
                "prior_trend",
                "event_session",
                "pivot_session",
                "pivot_confirmation_session",
                "event_identity_sha256",
                "pivot_identity_sha256",
            }
            or witness["event_session"] != "2026-08-26"
            or any(
                re.fullmatch(r"[0-9a-f]{64}", witness[key]) is None
                for key in witness
                if key.endswith("sha256")
            )
        ):
            raise ValueError("v4 original contradiction closed witness invalid")


def _check_v4_original_age(age, latest, scenario, status, reason):
    count = (
        None if scenario == "unknown" else 0 if scenario in ("replay", "refresh") else 2
    )
    if (
        (
            age["criterion"],
            age["status"],
            age["reason"],
            age["completed_sessions_elapsed"],
        )
        != (
            "ADMITTED_COMPLETED_SESSIONS_SINCE_ORIGINAL_UPWARD_BOS@v1",
            "OBSERVED" if status == "SAME_EVENT" else status,
            "COMPLETED_SESSIONS_SINCE_ORIGINAL_EVENT"
            if status == "SAME_EVENT"
            else reason,
            count,
        )
        or count is not None
        and type(age["completed_sessions_elapsed"]) is not int
    ):
        raise ValueError("v4 original age semantics invalid")
    _verify_age_endpoints(age, count)
    if count is not None:
        if age["current_completed_session"] != latest["current"]["session"]:
            raise ValueError("v4 original age latest endpoint invalid")
        for side, schedule in age["schedules"].items():
            if (
                type(schedule) is not dict
                or set(schedule)
                != {
                    "source",
                    "source_release",
                    "evidence_identity_sha256",
                    "schedule_identity_sha256",
                    "feature_known_at",
                }
                or (
                    schedule["source"] != "nse-upstox-composed-calendar"
                    or type(schedule["source_release"]) is not str
                    or re.fullmatch(
                        r"composed-calendar@v1=[0-9a-f]{64}", schedule["source_release"]
                    )
                    is None
                    or schedule["feature_known_at"] != latest[side]["feature_known_at"]
                    or schedule["schedule_identity_sha256"]
                    != latest[side]["schedule_identity_sha256"]
                )
            ):
                raise ValueError("v4 original schedule metadata invalid")


def _check_v4_original_evidence(
    original: dict, scenario: str, inclusion_refs: dict
) -> None:
    """Close original three-fact envelopes independently of candidate seals."""
    latest = inclusion_refs["latest_range"]
    observed = scenario not in ("replay", "unknown", "refresh")
    status = (
        "UNKNOWN"
        if scenario == "unknown"
        else "REPLAY"
        if scenario == "replay"
        else "SAME_EVENT"
    )
    reason = (
        "CURRENT_STRUCTURE_UNKNOWN"
        if scenario == "unknown"
        else "IDENTICAL_ADMITTED_OBSERVATION"
        if scenario == "replay"
        else "SAME_ADMITTED_EVENT_AND_ANCHOR"
    )
    common = {
        key: latest[key]
        for key in (
            "previous",
            "current",
            "previous_observation_identity_sha256",
            "current_observation_identity_sha256",
        )
    }
    continuity, invalidation, age = (
        original[name] for name in ("continuity", "invalidation", "age")
    )
    for name in ("continuity", "invalidation", "age"):
        report = original[name]
        _v4_sealed(report, _V4_REFERENCE_KEYS[name])
        if (
            any(report[key] != expected for key, expected in common.items())
            or report["limitations"] != _V4_FIXED_LIMITATIONS[name]
        ):
            raise ValueError("v4 original pair or limitations invalid")
        if (
            report["contract_version"]
            != "causal-setup-"
            + ("event-continuity" if name == "continuity" else name)
            + "@v1"
        ):
            raise ValueError("v4 original version invalid")
    _check_v4_original_continuity(
        continuity, latest, scenario, status, reason, observed
    )
    for report in (invalidation, age):
        if (
            report["continuity_identity_sha256"] != continuity["result_identity_sha256"]
            or report["continuity_status"] != status
        ):
            raise ValueError("v4 original continuity reference invalid")
    _check_v4_original_invalidation(invalidation, scenario, status, reason)
    _check_v4_original_age(age, latest, scenario, status, reason)
    _v4_sealed(original, _V4_REFERENCE_KEYS["v1"])
    if (
        original["contract_version"] != "causal-setup-evidence@v1"
        or original["criterion"] != "LATEST_COMPLETED_UPWARD_BOS@v1"
        or original["limitations"] != _V4_FIXED_LIMITATIONS["v1"]
        or any(original[key] != common[key] for key in common if key.endswith("sha256"))
    ):
        raise ValueError("v4 original bundle envelope invalid")


def _check_installed_evidence_v4(
    value: dict, raw: bytes, scenario: str, references: dict
) -> None:
    if set(references) != {
        "legacy_v1",
        "legacy_v2",
        "legacy_v3",
        "inclusion_references",
        "evidence_runtime",
        "interpretation_runtime",
    }:
        raise ValueError("v4 independent reference inventory invalid")
    actual = (
        "earlier"
        if scenario in ("no-trade", "false-claim", "false-session")
        else scenario
    )
    inclusion_refs = references["inclusion_references"]
    inclusion = value["level_range_inclusion"]
    _check_installed_range_inclusion(
        inclusion, _interpretation_bytes(inclusion), actual, inclusion_refs
    )
    v1, v2, v3 = (references[name] for name in ("legacy_v1", "legacy_v2", "legacy_v3"))
    _check_v4_original_evidence(v1, actual, inclusion_refs)
    continuity = v1["continuity"]
    for component in (
        inclusion_refs["level"],
        inclusion_refs["latest_range"],
        inclusion,
    ):
        if (
            component["continuity_identity_sha256"]
            != continuity["result_identity_sha256"]
            or component["continuity_status"] != continuity["status"]
        ):
            raise ValueError("v4 original range continuity reference invalid")
    expected = dict(v1)
    expected.pop("result_identity_sha256")
    expected.update(
        contract_version="causal-setup-evidence@v2",
        legacy_evidence_identity_sha256=v1["result_identity_sha256"],
        level=inclusion_refs["level"],
        runtime_code_identity_sha256=v2["runtime_code_identity_sha256"],
        limitations=[
            *v1["limitations"],
            "ABOVE/AT/BELOW is a descriptive completed-close relation; ABOVE does not confirm validity or eligibility and BELOW does not establish structural invalidation.",
        ],
    )
    expected["result_identity_sha256"] = hashlib.sha256(
        _interpretation_bytes(expected)
    ).hexdigest()
    if _interpretation_bytes(v2) != _interpretation_bytes(expected):
        raise ValueError("v4 original v2 reference invalid")
    expected.pop("result_identity_sha256")
    expected.update(
        contract_version="causal-setup-evidence@v3",
        legacy_evidence_v2_identity_sha256=v2["result_identity_sha256"],
        level_range=inclusion_refs["latest_range"],
        runtime_code_identity_sha256=v3["runtime_code_identity_sha256"],
        limitations=[
            *v2["limitations"],
            "Inclusive latest low/high containment is descriptive; it proves no exact traded tick, successful retest, confirmation, validity or eligibility.",
        ],
    )
    expected["result_identity_sha256"] = hashlib.sha256(
        _interpretation_bytes(expected)
    ).hexdigest()
    if _interpretation_bytes(v3) != _interpretation_bytes(expected):
        raise ValueError("v4 original v3 reference invalid")
    expected.pop("result_identity_sha256")
    expected.update(
        contract_version="causal-setup-evidence@v4",
        legacy_evidence_v3_identity_sha256=v3["result_identity_sha256"],
        level_range_inclusion=inclusion,
        runtime_code_identity_sha256=references["evidence_runtime"],
        limitations=[
            *v3["limitations"],
            "Earliest inclusive completed range only in the admitted post-event window; no first lifetime contact, exact traded tick, successful retest, confirmation, validity or eligibility is established.",
        ],
    )
    expected["result_identity_sha256"] = hashlib.sha256(
        _interpretation_bytes(expected)
    ).hexdigest()
    if (
        len(raw) > 1024 * 1024
        or raw != _interpretation_bytes(value)
        or raw != _interpretation_bytes(expected)
    ):
        raise ValueError("v4 exact six-fact evidence invalid")


def _check_installed_interpretation_v4(
    value: dict, raw: bytes, scenario: str, references: dict
) -> None:
    evidence = value["evidence"]
    _check_installed_evidence_v4(
        evidence, _interpretation_bytes(evidence), scenario, references
    )
    additional = {
        "age": ("completed_sessions_elapsed",),
        "level": ("relation",),
        "level_range": ("range_relation",),
        "level_range_inclusion": ("inclusion_observed", "first_inclusion"),
    }
    response = {
        "schema": "external-setup-interpretation-request@v4",
        "evidence_identity_sha256": evidence["result_identity_sha256"],
        "disposition": "NO_TRADE" if scenario == "no-trade" else "RESEARCH_ONLY",
        "explanation": "Caller-authored synthetic research posture; facts unchanged, narrative accuracy and eligibility unassessed.",
        "facts": {
            name: {
                key: evidence[name][key]
                for key in (
                    "result_identity_sha256",
                    "status",
                    *additional.get(name, ()),
                )
            }
            for name in (
                "continuity",
                "invalidation",
                "age",
                "level",
                "level_range",
                "level_range_inclusion",
            )
        },
    }
    expected = {
        "contract_version": "external-setup-interpretation-check@v4",
        "evidence": evidence,
        "external_response": response,
        "external_response_identity_sha256": hashlib.sha256(
            _interpretation_bytes(response)
        ).hexdigest(),
        "runtime_code_identity_sha256": references["interpretation_runtime"],
        "verification": "STRUCTURED_BINDING_ONLY",
        "explanation_accuracy": "NOT_ASSESSED",
        "external_authorship": "CALLER_SUPPLIED_NOT_AUTHENTICATED",
        "actionable_recommendation": "NOT_ASSESSED",
        "eligibility": "NOT_ASSESSED",
        "effectiveness": "NOT_ASSESSED",
        "limitations": _V4_FIXED_LIMITATIONS["interpretation"],
    }
    expected["result_identity_sha256"] = hashlib.sha256(
        _interpretation_bytes(expected)
    ).hexdigest()
    if (
        len(raw) > 1024 * 1024
        or raw != _interpretation_bytes(value)
        or raw != _interpretation_bytes(expected)
    ):
        raise ValueError("v4 exact checked interpretation invalid")


def _verify_installed_inclusion_interpretation_v4(
    python: Path, scratch: Path
) -> dict[str, dict[str, object]]:
    """Actual isolated installed execution with independent original component receipts."""
    probe = "\n".join(
        (
            "import json, os, pathlib, runpy, sys",
            "sys.dont_write_bytecode = True",
            "from swing_trading_ai_assistant.research_comparison import setup_interpretation_v4 as sdk, setup_interpretation_v4_cli as cli, setup_evidence_v4 as bundle, setup_evidence_v4_cli as bundle_cli, setup_evidence_v2 as old, setup_evidence as v1, setup_level as level, setup_level_range as level_range",
            "for name, module in tuple(sys.modules.items()):",
            "    if name.startswith('swing_trading_ai_assistant') and getattr(module, '__file__', None) and not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "        raise RuntimeError('v4 import escaped installed environment')",
            "fixture, scenario, reference = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "namespace = runpy.run_path(fixture, run_name='installed_qualification')",
            "code = namespace['main']()",
            "references = namespace['main'].__globals__['QUALIFICATION_REFERENCES']",
            "descriptor = os.open(reference, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)",
            "with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:",
            "    stream.write(json.dumps(references, sort_keys=True, separators=(',', ':')) + '\\n')",
            "raise SystemExit(code)",
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
    for scenario in (
        "earlier",
        "none",
        "latest",
        "multiple",
        "low-equal",
        "high-equal",
        "nearest-above",
        "nearest-below",
        "event-only",
        "invalidated",
        "replay",
        "unknown",
        "refresh",
        "no-trade",
        "false-claim",
        "false-session",
    ):
        reference = scratch / ("v4-original-references-" + scenario + ".json")
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/causal_setup_inclusion_interpretation_v4_demo.py"),
                scenario,
                str(reference),
            ],
            cwd=scratch,
            env=safe_env,
        )
        code = (
            2
            if scenario in ("false-claim", "false-session")
            else 1
            if scenario == "unknown"
            else 0
        )
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
                    b'"bars"',
                    b'"body"',
                    b'"api_key"',
                    str(scratch).encode(),
                )
            )
        ):
            raise RuntimeError("installed v4 execution failed")
        if scenario in ("false-claim", "false-session"):
            if observed.stdout or not observed.stderr.endswith(
                b"setup_interpretation_failed\n"
            ):
                raise RuntimeError("installed v4 false range accepted")
            outcomes[scenario] = {
                "exit": 2,
                "rejected": True,
                "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            }
            continue
        try:
            references = json.loads(reference.read_bytes())
            value = json.loads(observed.stdout)
            _check_installed_interpretation_v4(
                value, observed.stdout, scenario, references
            )
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError("installed v4 result invalid") from error
        evidence = value["evidence"]
        outcomes[scenario] = {
            "exit": code,
            "statuses": {
                name: evidence[name]["status"]
                for name in (
                    "continuity",
                    "invalidation",
                    "age",
                    "level",
                    "level_range",
                    "level_range_inclusion",
                )
            },
            "relation": evidence["level"]["relation"],
            "range_relation": evidence["level_range"]["range_relation"],
            "inclusion_observed": evidence["level_range_inclusion"][
                "inclusion_observed"
            ],
            "first_inclusion": evidence["level_range_inclusion"]["first_inclusion"],
            "legacy_evidence_v3_identity_sha256": evidence[
                "legacy_evidence_v3_identity_sha256"
            ],
            "completed_sessions_elapsed": evidence["age"]["completed_sessions_elapsed"],
            "disposition": value["external_response"]["disposition"],
            "result_identity_sha256": value["result_identity_sha256"],
            "runtime_code_identity_sha256": value["runtime_code_identity_sha256"],
            "evidence_identity_sha256": evidence["result_identity_sha256"],
            "legacy_evidence_v2_identity_sha256": evidence[
                "legacy_evidence_v2_identity_sha256"
            ],
            "level_identity_sha256": evidence["level"]["result_identity_sha256"],
            "range_identity_sha256": evidence["level_range"]["result_identity_sha256"],
            "original_references_sha256": hashlib.sha256(
                reference.read_bytes()
            ).hexdigest(),
            "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            "imports": "Installed SDK and both injected CLIs with -I; original v1/v2/Plan54/Plan56 APIs independently regenerated; all nested canonical bytes exact; no model evaluated",
        }
    return outcomes


def _check_installed_first_inclusion_close(
    value: dict, raw: bytes, scenario: str, references: dict
) -> None:
    """Bind every new field to the exact admitted original inclusion chain."""
    if set(references) != {
        "range_inclusion",
        "inclusion_references",
        "runtime_code_identity_sha256",
    }:
        raise ValueError("first inclusion close reference inventory invalid")
    base_scenario = (
        "earlier"
        if scenario
        in ("first-below", "first-at", "close-nearest-below", "close-nearest-above")
        else scenario
    )
    original = references["range_inclusion"]
    _check_installed_range_inclusion(
        original,
        _interpretation_bytes(original),
        base_scenario,
        references["inclusion_references"],
    )
    runtime = references["runtime_code_identity_sha256"]
    if type(runtime) is not str or re.fullmatch(r"[0-9a-f]{64}", runtime) is None:
        raise ValueError("first inclusion close reference runtime invalid")
    relation = {
        "earlier": "ABOVE",
        "first-below": "BELOW",
        "first-at": "AT",
        "close-nearest-below": "BELOW",
        "close-nearest-above": "ABOVE",
        "latest": "ABOVE",
        "multiple": "ABOVE",
        "low-equal": "ABOVE",
        "high-equal": "BELOW",
        "invalidated": "BELOW",
        "none": None,
        "nearest-above": None,
        "nearest-below": None,
        "event-only": None,
        "replay": None,
        "unknown": None,
        "refresh": None,
    }[scenario]
    expected = dict(original)
    expected.pop("result_identity_sha256")
    expected.update(
        contract_version="causal-setup-first-inclusion-close@v1",
        criterion="EARLIEST_COMPLETED_RANGE_INCLUSION_CLOSE_VS_ORIGINAL_BROKEN_HIGH@v1",
        runtime_code_identity_sha256=runtime,
        range_inclusion_identity_sha256=original["result_identity_sha256"],
        first_close_relation=relation,
        limitations=[
            "Exact final close of the earliest range-including completed session in the admitted post-event window only; not first lifetime contact.",
            "No intrabar ordering, exact traded tick, reclaim, successful retest or confirmation is established.",
            "ABOVE/AT/BELOW and NO_INCLUSION imply no validity, eligibility, recommendation, effectiveness, expiry or trade authorization; structural invalidation is independent.",
            "Original unchanged causal high/event and all source rows must remain represented and fully admitted in the finite21-session window; missing evidence is not NO_INCLUSION.",
            "No tolerance, threshold, history store, persistence, monitoring, new acquisition or external model.",
        ],
    )
    if original["status"] == "OBSERVED":
        expected.update(
            status="OBSERVED" if relation is not None else "NO_INCLUSION",
            reason="FIRST_RANGE_INCLUSION_COMPLETED_CLOSE_COMPARED_WITH_ORIGINAL_BROKEN_HIGH"
            if relation is not None
            else "NO_COMPLETED_POST_EVENT_RANGE_INCLUSION_OBSERVED",
        )
    expected["result_identity_sha256"] = hashlib.sha256(
        _interpretation_bytes(expected)
    ).hexdigest()
    if (
        len(raw) > 1024 * 1024
        or raw != _interpretation_bytes(value)
        or raw != _interpretation_bytes(expected)
    ):
        raise ValueError("first inclusion close exact installed result invalid")


def _verify_installed_first_inclusion_close(
    python: Path, scratch: Path
) -> dict[str, dict[str, object]]:
    """Actual -I installed SDK/CLI and original transitive component closure."""
    probe = "\n".join(
        (
            "import json, os, pathlib, runpy, sys",
            "sys.dont_write_bytecode = True",
            "from swing_trading_ai_assistant.research_comparison import setup_first_inclusion_close as sdk, setup_first_inclusion_close_cli as cli, setup_level_range as original_range, setup_level as original_level",
            "for name, module in tuple(sys.modules.items()):",
            "    if name.startswith('swing_trading_ai_assistant') and getattr(module, '__file__', None):",
            "        if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "            raise RuntimeError('inclusion import escaped installed environment')",
            "fixture, scenario, reference = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "namespace = runpy.run_path(fixture, run_name='installed_qualification')",
            "code = namespace['main']()",
            "references = namespace['main'].__globals__['QUALIFICATION_REFERENCES']",
            "descriptor = os.open(reference, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)",
            "with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:",
            "    stream.write(json.dumps(references, sort_keys=True, separators=(',', ':')) + '\\n')",
            "raise SystemExit(code)",
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
    for scenario in (
        "earlier",
        "first-below",
        "first-at",
        "close-nearest-below",
        "close-nearest-above",
        "none",
        "latest",
        "multiple",
        "low-equal",
        "high-equal",
        "nearest-above",
        "nearest-below",
        "event-only",
        "invalidated",
        "replay",
        "unknown",
        "refresh",
    ):
        reference = scratch / (
            "first-inclusion-close-original-references-" + scenario + ".json"
        )
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/causal_setup_first_inclusion_close_demo.py"),
                scenario,
                str(reference),
            ],
            cwd=scratch,
            env=safe_env,
        )
        code = 1 if scenario == "unknown" else 0
        if (
            observed.returncode != code
            or len(observed.stdout) > 1024 * 1024
            or b"SYNTHETIC FIRST INCLUSION CLOSE" not in observed.stderr
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
                    b'"api_key"',
                    str(scratch).encode(),
                )
            )
        ):
            raise RuntimeError("installed first inclusion close execution failed")
        try:
            references = json.loads(reference.read_bytes())
            value = json.loads(observed.stdout)
            _check_installed_first_inclusion_close(
                value, observed.stdout, scenario, references
            )
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError(
                "installed first inclusion close result invalid"
            ) from error
        outcomes[scenario] = {
            "exit": code,
            "status": value["status"],
            "inclusion_observed": value["inclusion_observed"],
            "first_close_relation": value["first_close_relation"],
            "first_inclusion": value["first_inclusion"],
            "evaluated_post_event_bars": value["evaluated_post_event_bars"],
            "result_identity_sha256": value["result_identity_sha256"],
            "runtime_code_identity_sha256": value["runtime_code_identity_sha256"],
            "range_inclusion_identity_sha256": value["range_inclusion_identity_sha256"],
            "latest_range_identity_sha256": value["latest_range_identity_sha256"],
            "level_identity_sha256": value["level_identity_sha256"],
            "previous_observation_identity_sha256": value[
                "previous_observation_identity_sha256"
            ],
            "current_observation_identity_sha256": value[
                "current_observation_identity_sha256"
            ],
            "stdout_sha256": hashlib.sha256(observed.stdout).hexdigest(),
            "imports": "-I installed SDK/CLI/transitive runtime under sys.prefix; exact SDK/CLI equality; strict original Plan54/58 nested closure; first completed close only",
        }
    return outcomes


def _verify_installed_setup_research(python: Path, scratch: Path) -> dict[str, object]:
    """Qualify the new public path with installed SDK imports and original references."""
    probe = "\n".join(
        (
            "import sys, os, pathlib, json, runpy",
            "import swing_trading_ai_assistant.market_data.agent_setup_research",
            "for name, module in tuple(sys.modules.items()):",
            "    if name.startswith('swing_trading_ai_assistant') and getattr(module, '__file__', None):",
            "        if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "            raise RuntimeError('setup research import escaped installed environment')",
            "fixture, scenario, reference = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "namespace = runpy.run_path(fixture, run_name='installed_qualification')",
            "code = namespace['main']()",
            "values = namespace['QUALIFICATION_REFERENCES']",
            "descriptor = os.open(reference, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)",
            "with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:",
            "    stream.write(json.dumps(values, sort_keys=True, separators=(',', ':')) + '\\n')",
            "raise SystemExit(code)",
        )
    )
    safe_env = {
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    cases = {
        "positive": (0, "MATCH"),
        "negative": (0, "NO_MATCH"),
        "insufficient": (1, "UNKNOWN"),
        "geometry-missing": (1, "MATCH"),
        "comparison-missing": (1, "MATCH"),
        "interrupted": (2, None),
        "corrupt": (2, None),
        "invalid-request": (2, None),
    }
    outcomes: dict[str, object] = {}
    for scenario, (code, status) in cases.items():
        reference = scratch / ("setup-research-original-" + scenario + ".json")
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/current_setup_research_demo.py"),
                scenario,
                str(reference),
            ],
            cwd=scratch,
            env=safe_env,
        )
        if (
            observed.returncode != code
            or b"SYNTHETIC SETUP RESEARCH" not in observed.stderr
            or b"not current market data" not in observed.stderr
        ):
            raise RuntimeError("installed setup research scenario failed: " + scenario)
        original = json.loads(reference.read_bytes())
        calls = original["producer_calls"]
        if any(call[1:] != ["INTEGRATED_CURRENT_RESEARCH", False] for call in calls):
            raise RuntimeError("installed setup research producer profile mismatch")
        if code == 2:
            diagnostic = (
                b"request_invalid\n"
                if scenario == "invalid-request"
                else b"setup_research_failed\n"
            )
            if (
                observed.stdout
                or not observed.stderr.endswith(diagnostic)
                or (scenario == "invalid-request" and calls)
            ):
                raise RuntimeError("installed setup research failure leaked output")
        else:
            if (
                len(calls) != 1
                or len(observed.stdout) > 1024 * 1024
                or any(
                    token in observed.stdout
                    for token in (
                        b'"price"',
                        b'"bars"',
                        b'"open"',
                        b'"close"',
                        b'"body"',
                        b'"api_key"',
                        str(scratch).encode(),
                    )
                )
            ):
                raise RuntimeError("installed setup research bounds/privacy failed")
            report = json.loads(observed.stdout)
            identity = report.pop("result_identity_sha256")
            digest = hashlib.sha256(
                (
                    json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
                ).encode()
            ).hexdigest()
            base_digest = hashlib.sha256(
                (
                    json.dumps(
                        report["research"], sort_keys=True, separators=(",", ":")
                    )
                    + "\n"
                ).encode()
            ).hexdigest()
            if (
                report["contract_version"] != "agent-current-setup-research@v1"
                or report["members"][0]["status"] != status
                or identity != digest
                or identity != original["same_observation_sdk_identity"]
                or report["base_research_report_identity_sha256"] != base_digest
                or base_digest != original["base_research_identity"]
            ):
                raise RuntimeError("installed setup research SDK/CLI identity mismatch")
        outcomes[scenario] = {
            "exit": code,
            "candidate_status": status,
            "producer_calls": len(calls),
            "installed_sdk_cli_binding": "verified",
            "stdout_bytes": len(observed.stdout),
        }
    return outcomes


def _verify_selection_research_child(child: dict[str, object]) -> None:
    if (
        child["contract_version"] != "agent-current-setup-research@v1"
        or not 1 <= len(child["members"]) <= 10
        or len(
            (json.dumps(child, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
        > 1024 * 1024
    ):
        raise RuntimeError("installed whole-list child contract invalid")
    child_body = {k: v for k, v in child.items() if k != "result_identity_sha256"}
    if (
        child["result_identity_sha256"]
        != hashlib.sha256(
            (
                json.dumps(child_body, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        ).hexdigest()
    ):
        raise RuntimeError("installed whole-list child identity invalid")


def _verify_selection_research_report(
    raw_output: bytes, original: dict[str, object], count: int, scenario: str
) -> None:
    report = json.loads(raw_output)
    if set(report) != {
        "contract_version",
        "runtime_code_identity_sha256",
        "selection",
        "requested_order_identity_sha256",
        "canonical_order_identity_sha256",
        "reports",
        "research_jointly_comparable",
        "candidate_jointly_comparable",
        "limitations",
        "result_identity_sha256",
    }:
        raise RuntimeError("installed whole-list schema invalid")
    identity = report.pop("result_identity_sha256")
    raw = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
    rows = [row for child in report["reports"] for row in child["members"]]
    if (
        report["contract_version"] != "agent-current-setup-research-selection@v1"
        or identity != hashlib.sha256(raw).hexdigest()
        or identity != original["same_observation_sdk_identity"]
        or hashlib.sha256(raw_output).hexdigest() != original["whole_output_sha256"]
        or [row["requested_symbol"] for row in rows]
        != [f"S{i:03d}" for i in range(count)]
        or len(report["reports"]) != (count + 9) // 10
        or report["selection"]["kind"]
        != ("RETAINED_NIFTY100" if scenario == "default100" else "EXPLICIT_SYMBOLS")
        or report["requested_order_identity_sha256"]
        != hashlib.sha256(
            (
                json.dumps([f"S{i:03d}" for i in range(count)], separators=(",", ":"))
                + "\n"
            ).encode()
        ).hexdigest()
    ):
        raise RuntimeError("installed whole-list identity/order invalid")
    for child in report["reports"]:
        _verify_selection_research_child(child)
    if scenario == "unknown-later":
        if (
            rows[10]["status"] != "UNKNOWN"
            or report["canonical_order_identity_sha256"] is not None
            or report["candidate_jointly_comparable"]
            or report["research_jointly_comparable"]
        ):
            raise RuntimeError("installed whole-list unknown member lost")
    elif scenario == "negative":
        if rows[0]["status"] != "NO_MATCH":
            raise RuntimeError("installed whole-list negative invalid")
    elif (
        any(row["status"] != "MATCH" for row in rows)
        or not report["candidate_jointly_comparable"]
        or report["research_jointly_comparable"] != (scenario != "geometry-missing")
    ):
        raise RuntimeError("installed whole-list observed member invalid")
    if scenario == "default100" and (
        report["selection"]["knowledge_basis"] != "CURRENT_AT_RETRIEVAL"
        or report["selection"]["selection_identity_sha256"]
        != report["canonical_order_identity_sha256"]
        or len(report["selection"]["expected_members"]) != 100
    ):
        raise RuntimeError("installed whole-list selector binding invalid")


def _verify_installed_selection_research(
    python: Path, scratch: Path
) -> dict[str, object]:
    """Prove the whole-list path in the isolated installed wheel, with exact SDK bytes."""
    probe = "\n".join(
        (
            "import sys, os, pathlib, json, runpy",
            "import swing_trading_ai_assistant.market_data.setup_research_selection",
            "import swing_trading_ai_assistant.market_data.cli",
            "def verify_imports():",
            "    for name, module in tuple(sys.modules.items()):",
            "        if name.startswith('swing_trading_ai_assistant') and getattr(module, '__file__', None):",
            "            if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):",
            "                raise RuntimeError('whole-list import escaped installed environment')",
            "verify_imports()",
            "fixture, scenario, reference = sys.argv[1:]",
            "sys.argv = [fixture, '--scenario', scenario]",
            "namespace = runpy.run_path(fixture, run_name='installed_qualification')",
            "code = namespace['main']()",
            "verify_imports()",
            "values = namespace['QUALIFICATION_REFERENCES']",
            "descriptor = os.open(reference, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)",
            "with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:",
            "    stream.write(json.dumps(values, sort_keys=True, separators=(',', ':')) + '\\n')",
            "raise SystemExit(code)",
        )
    )
    safe_env = {
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    cases = {
        "explicit11": (0, 11, None),
        "default100": (0, 100, None),
        "unknown-later": (1, 11, None),
        "negative": (0, 1, None),
        "geometry-missing": (1, 1, None),
        "interrupted": (2, 11, b"selection_research_failed\n"),
        "canonical-conflict": (2, 11, b"request_invalid\n"),
        "invalid101": (2, 0, b"request_invalid\n"),
        "selection-unavailable": (1, 0, b"selection_unavailable\n"),
    }
    outcomes: dict[str, object] = {}
    for scenario, (code, count, diagnostic) in cases.items():
        reference = scratch / ("selection-research-original-" + scenario + ".json")
        observed = _run(
            [
                str(python),
                "-I",
                "-c",
                probe,
                str(ROOT / "examples/setup_research_selection_demo.py"),
                scenario,
                str(reference),
            ],
            cwd=scratch,
            env=safe_env,
        )
        if (
            observed.returncode != code
            or b"SYNTHETIC WHOLE-LIST RESEARCH" not in observed.stderr
            or b"not current market data" not in observed.stderr
        ):
            raise RuntimeError("installed whole-list scenario failed: " + scenario)
        original = json.loads(reference.read_bytes())
        calls = original["producer_calls"]
        if calls != [
            [f"S{i:03d}", "INTEGRATED_CURRENT_RESEARCH", False] for i in range(count)
        ]:
            raise RuntimeError(
                "installed whole-list producer count/order/profile invalid"
            )
        if diagnostic is not None:
            if observed.stdout or not observed.stderr.endswith(diagnostic):
                raise RuntimeError("installed whole-list terminal output invalid")
        else:
            if len(observed.stdout) > 11 * 1024 * 1024 or any(
                token in observed.stdout
                for token in (
                    b'"price"',
                    b'"bars"',
                    b'"open"',
                    b'"close"',
                    b'"body"',
                    b'"source_bytes"',
                    b'"api_key"',
                    str(scratch).encode(),
                )
            ):
                raise RuntimeError("installed whole-list bounds/privacy invalid")
            _verify_selection_research_report(
                observed.stdout, original, count, scenario
            )
        outcomes[scenario] = {
            "exit": code,
            "producer_calls": len(calls),
            "installed_sdk_cli_binding": "verified",
            "stdout_bytes": len(observed.stdout),
        }
    return outcomes


def _verify_installed_stock_observations(
    python: Path, scratch: Path
) -> dict[str, object]:
    """Exercise the new console command using only wheel-admitted synthetic records."""
    root = scratch / "stock-observation-evidence"
    root.mkdir(mode=0o700)
    safe_env = {
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    probe = "\n".join(
        (
            "import sys, json, pathlib, hashlib",
            "from datetime import UTC, datetime",
            "import swing_trading_ai_assistant._examples.single_stock_research_demo as demo",
            "from swing_trading_ai_assistant.market_data.current_stock_research_v2 import research_current_stock_v2",
            "from swing_trading_ai_assistant.market_data.stock_observations import record_stock_observation_v1",
            "def deny_network(event, args):",
            "    if event.startswith('socket.'): raise RuntimeError('synthetic installed probe denies network')",
            "sys.addaudithook(deny_network)",
            "root = pathlib.Path(sys.argv[1]); values = []",
            "for day in (26, 27):",
            "    demo.NOW = datetime(2026, 8, day, 4, 15, tzinfo=UTC)",
            "    source = demo.SyntheticOfficialSources('complete')",
            "    result = research_current_stock_v2('PNB', root, question='PRICE_BEHAVIOR', refresh=False, clock=demo.SyntheticClock(), calendar_transport=source, snapshot_transport=source, price_client=demo.SyntheticPrices('complete'))",
            "    handle = record_stock_observation_v1(root, result)",
            "    values.append({'handle': handle, 'result': json.loads(result.canonical_json_bytes())})",
            "for name, module in tuple(sys.modules.items()):",
            "    if name.startswith('swing_trading_ai_assistant') and getattr(module, '__file__', None):",
            "        if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()): raise RuntimeError('observation import escaped installed wheel')",
            "print(json.dumps(values, sort_keys=True, separators=(',', ':')))",
        )
    )
    created = _run(
        [str(python), "-I", "-c", probe, str(root)], cwd=scratch, env=safe_env
    )
    _require_success(created, "installed synthetic observation records")
    originals = json.loads(created.stdout)
    command = python.parent / "stock-observations"
    for original in originals:
        read = _run(
            [
                str(command),
                "read",
                "--storage-root",
                str(root),
                "--observation",
                original["handle"],
                "--output",
                "json",
            ],
            cwd=scratch,
            env=safe_env,
        )
        _require_success(read, "installed exact observation readback")
        output = json.loads(read.stdout)
        if (
            output["status"] != "READ"
            or output["observation_identity_sha256"] != original["handle"]
            or output["research"] != original["result"]
        ):
            raise RuntimeError("installed original observation changed")
    compared = _run(
        [
            str(command),
            "compare",
            "--storage-root",
            str(root),
            "--previous",
            originals[0]["handle"],
            "--current",
            originals[1]["handle"],
            "--output",
            "json",
        ],
        cwd=scratch,
        env=safe_env,
    )
    _require_success(compared, "installed retained comparison")
    comparison_result = json.loads(compared.stdout)
    if (
        comparison_result["status"] != "COMPARABLE"
        or comparison_result["previous_observation_identity_sha256"]
        != originals[0]["handle"]
        or comparison_result["current_observation_identity_sha256"]
        != originals[1]["handle"]
    ):
        raise RuntimeError("installed comparison handle substitution")
    missing = _run(
        [
            str(command),
            "read",
            "--storage-root",
            str(root),
            "--observation",
            "a" * 64,
            "--output",
            "json",
        ],
        cwd=scratch,
        env=safe_env,
    )
    if missing.returncode != 1 or json.loads(missing.stdout) != {
        "contract_version": "stock-observations@v1",
        "status": "UNAVAILABLE",
        "code": "OBSERVATION_RECORD_UNAVAILABLE",
    }:
        raise RuntimeError("installed missing baseline was not explicit")
    help_result = _run([str(command), "--help"], cwd=scratch, env=safe_env)
    _require_success(help_result, "installed observation help")
    for output in (created.stdout, compared.stdout, missing.stdout):
        if any(
            token in output
            for token in (str(root).encode(), b'"source_bars"', b'"api_key"')
        ):
            raise RuntimeError("installed observation privacy boundary failed")
    return {
        "synthetic_only": True,
        "recorded": 2,
        "original_readback": "exact",
        "console_comparison": "COMPARABLE",
        "missing_baseline": "explicit",
        "installed_imports": "isolated wheel",
    }


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
        range_interpretation_v3 = _verify_installed_range_interpretation_v3(
            python, scratch
        )
        range_inclusion = _verify_installed_range_inclusion(python, scratch)
        inclusion_interpretation_v4 = _verify_installed_inclusion_interpretation_v4(
            python, scratch
        )
        first_inclusion_close = _verify_installed_first_inclusion_close(python, scratch)
        setup_research = _verify_installed_setup_research(python, scratch)
        selection_research = _verify_installed_selection_research(python, scratch)
        stock_observations = _verify_installed_stock_observations(python, scratch)
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
            "installed_setup_range_interpretation_v3": range_interpretation_v3,
            "installed_setup_level_range_inclusion": range_inclusion,
            "installed_setup_inclusion_interpretation_v4": inclusion_interpretation_v4,
            "installed_setup_first_inclusion_close": first_inclusion_close,
            "installed_current_setup_research": setup_research,
            "installed_whole_selection_research": selection_research,
            "installed_stock_observations": stock_observations,
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
