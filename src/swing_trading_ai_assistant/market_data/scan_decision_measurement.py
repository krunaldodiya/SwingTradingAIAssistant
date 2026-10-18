"""Reproducible G09 measurement over retained scanner decision evidence."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Final, cast

from .runtime_source_verifier import runtime_source_sha256
from .scan_decision_evidence import (
    CONTRACT_VERSION as EVIDENCE_CONTRACT_VERSION,
)
from .scan_decision_evidence import (
    ScanDecisionEvidenceUnavailable,
    list_scan_decision_evidence_handles_v1,
    read_scan_decision_evidence_v1,
)
from .scan_decision_measurement_runtime_identity_manifest import (
    SCAN_DECISION_MEASUREMENT_RUNTIME_SOURCE_SHA256_V1,
)

SCHEMA: Final = "scan-decision-measurement@v1"
_INSTANT: Final = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")
_MAX_RECORDS: Final = 4096
_MAX_CONVENTION_CHARS: Final = 200
_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/scan_decision_measurement.py",
    "src/swing_trading_ai_assistant/market_data/scan_decision_evidence.py",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
)

_EXECUTION_ASSUMPTIONS: Final = (
    "Measurement aggregates retained scan-decision-evidence@v1 records only; "
    "it makes no provider, capture, or network call.",
    "Every symbol decision comes from the scanner's canonical decision "
    "pipeline (the retained pair policy plus the additive safety gate); "
    "optional Plan 58/60 context is reported but never used to compute any "
    "decision, safety, selection, or capacity number.",
    "Counts describe scan snapshots, not executed trades: no fill, cost, "
    "slippage, or return simulation is performed.",
    "Coverage is reported exactly as retained; no rule, threshold, or policy is "
    "relaxed to change any measured number.",
)

_EXTERNAL_PREREQUISITES: Final = (
    (
        "PER_DECISION_DATE_HISTORICAL_BACKFILL",
        "Retained scans cover only admitted scan snapshots; per-decision-date "
        "historical backfill and a generic replay engine are external evidence "
        "(Future #139), not produced here.",
    ),
    (
        "OUT_OF_SAMPLE_OR_WALK_FORWARD_EVIDENCE",
        "No forward-measured opportunity or outcome series exists in admitted "
        "evidence; the time split only partitions retained scans and is not "
        "out-of-sample validation.",
    ),
    (
        "EXECUTION_COST_SLIPPAGE_CONVENTION",
        "No accepted fill, cost, or slippage convention is supplied; any "
        "decision-support qualification requires one to be named and approved.",
    ),
    (
        "AI_MODEL_SOURCE_AND_PROMPT_OUTPUT_PROVENANCE",
        "No named approved model/source with immutable prompt/output provenance "
        "is supplied; this measurement performs no AI evaluation and invents no "
        "result.",
    ),
    (
        "RETURN_OR_PROFITABILITY_EVIDENCE",
        "No return or profitability evidence is produced or implied by this "
        "measurement.",
    ),
)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _runtime_identity() -> str:
    manifest_sources = tuple(
        str(k) for k in SCAN_DECISION_MEASUREMENT_RUNTIME_SOURCE_SHA256_V1
    )
    if manifest_sources != _SOURCES:
        raise ValueError("scan decision measurement runtime inventory invalid")
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for (
        relative,
        expected,
    ) in SCAN_DECISION_MEASUREMENT_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, str(relative))
        if actual != expected:
            raise ValueError("scan decision measurement runtime identity invalid")
        observed[str(relative)] = actual
    return _digest(observed)


def _rate(count: int, total: int) -> str:
    if total == 0:
        return "0.00%"
    return f"{count / total * 100:.2f}%"


def _counts(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _rates(counter: Counter[str], total: int) -> dict[str, str]:
    return {key: _rate(counter[key], total) for key in sorted(counter)}


def _timestamp(record: dict[str, object]) -> str:
    scan = cast(dict[str, object], record["scan"])
    value = scan.get("scan_timestamp")
    if type(value) is not str or _INSTANT.fullmatch(value) is None:
        raise ValueError("invalid scan timestamp")
    return value


def _metrics(records: Sequence[dict[str, object]]) -> dict[str, object]:
    """Compute one independent metric block from a closed record subset."""
    decision: Counter[str] = Counter()
    safety: Counter[str] = Counter()
    exclusions: Counter[str] = Counter()
    universe: Counter[str] = Counter()
    inclusion_status: Counter[str] = Counter()
    inclusion_observed: Counter[str] = Counter()
    close_status: Counter[str] = Counter()
    close_relation: Counter[str] = Counter()
    symbols: set[str] = set()
    raw_qualified = 0
    selected = 0
    candidates_with_context = 0
    for record in records:
        scan = cast(dict[str, object], record["scan"])
        universe[str(scan["universe_type"])] += 1
        for item in cast(list[object], scan["candidates"]):
            candidate = cast(dict[str, object], item)
            symbols.add(str(candidate["symbol"]))
            decision[str(candidate["decision"])] += 1
            eligibility = cast(dict[str, object], candidate["safety_eligibility"])
            safety[str(eligibility["status"])] += 1
            raw_qualified += 1
            selected += 1
            context = candidate.get("optional_context")
            if type(context) is not dict:
                continue
            admitted = cast(dict[str, object], context)
            inclusion_status[str(admitted.get("level_range_inclusion_status"))] += 1
            inclusion_observed[str(admitted.get("level_range_inclusion_observed"))] += 1
            close_status[str(admitted.get("first_inclusion_close_status"))] += 1
            close_relation[str(admitted.get("first_inclusion_close_relation"))] += 1
            candidates_with_context += 1
        for item in cast(list[object], scan["other_stocks"]):
            stock = cast(dict[str, object], item)
            symbols.add(str(stock["symbol"]))
            decision[str(stock["decision"])] += 1
            safety[str(stock["safety_status"])] += 1
            if stock["decision"] == "RESEARCH_CANDIDATE":
                raw_qualified += 1
            reason = stock.get("failed_rule")
            exclusions[
                str(reason) if reason is not None else "NO_EXCLUSION_REASON_RECORDED"
            ] += 1
    total = sum(decision.values())
    families: Counter[str] = Counter(
        reason.split(" (", 1)[0] for reason in exclusions.elements()
    )
    return {
        "coverage": {
            "scan_count": len(records),
            "symbol_observations": total,
            "distinct_symbols": len(symbols),
            "mean_symbol_observations_per_scan": (
                f"{total / len(records):.2f}" if records else "0.00"
            ),
            "universe_types": _counts(universe),
        },
        "decision_counts": _counts(decision),
        "decision_rates": _rates(decision, total),
        "safety_counts": _counts(safety),
        "safety_rates": _rates(safety, total),
        "raw_policy_qualified": raw_qualified,
        "selected_basket_candidates": selected,
        "candidate_retention_rate": _rate(selected, raw_qualified),
        "basket_selection_loss": raw_qualified - selected,
        "exclusion_reasons": _counts(exclusions),
        "exclusion_reason_families": _counts(families),
        "optional_context": {
            "measured_separately_from_decision": True,
            "candidates_with_context": candidates_with_context,
            "candidates_without_context": selected - candidates_with_context,
            "level_range_inclusion_status": _counts(inclusion_status),
            "level_range_inclusion_observed": _counts(inclusion_observed),
            "first_inclusion_close_status": _counts(close_status),
            "first_inclusion_close_relation": _counts(close_relation),
        },
    }


def _evidence_block(
    records: Sequence[dict[str, object]], handles: Sequence[str]
) -> dict[str, object]:
    timestamps = [_timestamp(record) for record in records]
    runtime: set[str] = set()
    roots: set[str] = set()
    for record in records:
        scan = cast(dict[str, object], record["scan"])
        runtime.add(str(scan["runtime_code_identity_sha256"]))
        roots.add(str(scan["storage_root_sha256"]))
    return {
        "contract_version": EVIDENCE_CONTRACT_VERSION,
        "record_count": len(records),
        "handles": list(handles),
        "scan_timestamp_first": min(timestamps) if timestamps else None,
        "scan_timestamp_last": max(timestamps) if timestamps else None,
        "runtime_code_identity_sha256": sorted(runtime),
        "storage_root_sha256": sorted(roots),
    }


def _time_splits(
    records: Sequence[dict[str, object]], split_at: str | None
) -> dict[str, object] | None:
    if split_at is None:
        return None
    earlier = [record for record in records if _timestamp(record) < split_at]
    later = [record for record in records if _timestamp(record) >= split_at]
    return {
        "split_at": split_at,
        "earlier": _metrics(earlier),
        "later": _metrics(later),
        "future_leakage_guard": (
            "Each split is computed only from records whose own scan timestamp "
            "falls in that split; later records never contribute to "
            "earlier-split metrics."
        ),
    }


def _qualification(execution_convention: str | None) -> dict[str, object]:
    statuses = {
        identifier: "PENDING_EXTERNAL_EVIDENCE"
        for identifier, _ in _EXTERNAL_PREREQUISITES
    }
    if execution_convention is not None:
        statuses["EXECUTION_COST_SLIPPAGE_CONVENTION"] = "PROVIDED_BY_CALLER"
    return {
        "mandatory_policy_measured": True,
        "optional_context_measured_separately": True,
        "ai_evaluation_performed": False,
        "execution_convention": execution_convention,
        "statuses": statuses,
        "statements": dict(_EXTERNAL_PREREQUISITES),
    }


def measure_scan_decision_evidence_v1(
    root: Path,
    *,
    split_at: str | None = None,
    execution_convention: str | None = None,
) -> dict[str, object]:
    """Aggregate retained, admitted scanner decision evidence for G09 review.

    The measurement is deterministic for a fixed store and runtime: it reads no
    clock, calls no provider, and performs no AI evaluation. Every record must
    re-admit under the current runtime identity; otherwise the measurement
    fails closed instead of reporting partial or substituted numbers.
    """
    if split_at is not None and (
        type(split_at) is not str or _INSTANT.fullmatch(split_at) is None
    ):
        raise ValueError("invalid split instant")
    if execution_convention is not None and (
        type(execution_convention) is not str
        or not 1 <= len(execution_convention) <= _MAX_CONVENTION_CHARS
    ):
        raise ValueError("invalid execution convention")
    handles = list_scan_decision_evidence_handles_v1(root)
    if len(handles) > _MAX_RECORDS:
        raise ScanDecisionEvidenceUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    records: list[dict[str, object]] = []
    try:
        records = [read_scan_decision_evidence_v1(root, handle) for handle in handles]
        records.sort(
            key=lambda record: (
                _timestamp(record),
                str(record["decision_evidence_handle"]),
            )
        )
    except ScanDecisionEvidenceUnavailable:
        raise
    except Exception as error:  # noqa: BLE001 - closed measurement boundary
        raise ScanDecisionEvidenceUnavailable(
            "DECISION_EVIDENCE_UNAVAILABLE"
        ) from error
    report: dict[str, object] = {
        "schema": SCHEMA,
        "evidence": _evidence_block(records, handles),
        "totals": _metrics(records),
        "time_splits": _time_splits(records, split_at),
        "execution_assumptions": list(_EXECUTION_ASSUMPTIONS),
        "qualification": _qualification(execution_convention),
        "measurement_runtime_code_identity_sha256": _runtime_identity(),
    }
    report["result_identity_sha256"] = _digest(report)
    return report
