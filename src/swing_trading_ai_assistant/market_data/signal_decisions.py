"""Evaluate a source-bound, fail-closed supported decision from retained records."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from swing_trading_ai_assistant.research_comparison.setup_evidence_v4 import (
    assemble_setup_evidence_v4,
)
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (
    canonical_comparison_bytes,
)

from .runtime_source_verifier import runtime_source_sha256
from .signal_decisions_runtime_identity_manifest import (
    SIGNAL_DECISIONS_RUNTIME_SOURCE_SHA256_V2,
)
from .stock_eligibility import evaluate_stock_eligibility_from_record_v2
from .stock_observations import read_stock_observation_v1

SCHEMA: Final = "stock-signal-decision@v2"
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/signal_decisions.py",
    "src/swing_trading_ai_assistant/market_data/stock_eligibility.py",
    "src/swing_trading_ai_assistant/market_data/signal_decisions_cli.py",
)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _instant(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError("eligibility known time invalid")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise ValueError("eligibility known time invalid") from error
    return (
        parsed.replace(tzinfo=UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _runtime_identity() -> str:
    if tuple(SIGNAL_DECISIONS_RUNTIME_SOURCE_SHA256_V2) != _SOURCES:
        raise ValueError("signal decision runtime inventory invalid")
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in SIGNAL_DECISIONS_RUNTIME_SOURCE_SHA256_V2.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("signal decision runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def _valid_request(
    storage_root: object, previous: object, current: object
) -> tuple[Path, str, str]:
    if (
        not isinstance(storage_root, Path)
        or not storage_root.is_absolute()
        or type(previous) is not str
        or type(current) is not str
        or _DIGEST.fullmatch(previous) is None
        or _DIGEST.fullmatch(current) is None
    ):
        raise ValueError("invalid observation request")
    return storage_root, previous, current


def _component(value: object, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError(f"invalid setup evidence {label}")
    return cast(dict[str, object], value)


def _text(value: object, label: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError(f"invalid setup evidence {label}")
    return value


def _boolean(value: object, label: str) -> bool | None:
    if value is None:
        return None
    if type(value) is bool:
        return value
    raise ValueError(f"invalid setup evidence {label}")


def _nonnegative_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid setup evidence {label}")
    return value


def _setup_summary(evidence: dict[str, object]) -> dict[str, object]:
    unsigned = dict(evidence)
    identity = unsigned.pop("result_identity_sha256", None)
    if type(identity) is not str or _DIGEST.fullmatch(identity) is None:
        raise ValueError("setup evidence identity invalid")
    if hashlib.sha256(canonical_comparison_bytes(unsigned)).hexdigest() != identity:
        raise ValueError("setup evidence identity invalid")
    continuity = _component(evidence.get("continuity"), "continuity")
    invalidation = _component(evidence.get("invalidation"), "invalidation")
    age = _component(evidence.get("age"), "age")
    level = _component(evidence.get("level"), "level")
    inclusion = _component(
        evidence.get("level_range_inclusion"), "level range inclusion"
    )
    summary: dict[str, object] = {
        "setup_evidence_identity_sha256": identity,
        "continuity_status": _text(continuity.get("status"), "continuity status"),
        "invalidation_status": _text(invalidation.get("status"), "invalidation status"),
        "candidate_age_status": _text(age.get("status"), "age status"),
        "candidate_age_sessions": _nonnegative_int(
            age.get("completed_sessions_elapsed"), "age sessions"
        ),
        "level_status": _text(level.get("status"), "level status"),
        "level_relation": _text(level.get("relation"), "level relation"),
        "range_inclusion_status": _text(inclusion.get("status"), "inclusion status"),
        "range_inclusion_observed": _boolean(
            inclusion.get("inclusion_observed"), "inclusion observed"
        ),
    }
    return summary


def evaluate_signal_decision_from_records_v2(
    storage_root: Path, previous: str, current: str
) -> dict[str, object]:
    """Re-admit an exact pair and emit a decision that cannot become actionable.

    The incomplete current G03 capability set produces an explicit `NO_TRADE`
    before causal facts can be used as a trade authorization. The causal facts are
    still derived and bound so a later governed policy can reuse them only after
    it provides the missing source evidence.
    """
    root, previous_handle, current_handle = _valid_request(
        storage_root, previous, current
    )
    runtime = _runtime_identity()
    previous_observation = read_stock_observation_v1(root, previous_handle)
    current_observation = read_stock_observation_v1(root, current_handle)
    eligibility = evaluate_stock_eligibility_from_record_v2(root, current_handle)
    evidence = assemble_setup_evidence_v4(previous_observation, current_observation)
    summary = _setup_summary(evidence)
    verified_evidence = eligibility["verified_evidence"]
    known_at = _instant(
        None
        if verified_evidence is None
        else _component(verified_evidence, "eligibility evidence").get("known_at")
    )
    result: dict[str, object] = {
        "schema": SCHEMA,
        "disposition": "NO_TRADE",
        "decision_code": "ELIGIBILITY_EVIDENCE_UNAVAILABLE",
        "symbol": eligibility["symbol"],
        "previous_observation_identity_sha256": previous_handle,
        "current_observation_identity_sha256": current_handle,
        "eligibility": eligibility,
        "setup_evidence": summary,
        "known_at": known_at,
        "runtime_code_identity_sha256": runtime,
    }
    result["decision_identity_sha256"] = _digest(result)
    return result


__all__ = ["SCHEMA", "evaluate_signal_decision_from_records_v2"]
