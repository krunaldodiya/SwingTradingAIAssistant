"""Immutable, source-bound scanner decision evidence for later G09 qualification."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from contextlib import ExitStack
from pathlib import Path
from typing import Final, cast

from . import capture_forward_adjusted_ohlcv as private_store
from . import current_stock_research as legacy
from .signal_decisions_scan_v3 import (
    _runtime_identity as _scanner_runtime_identity,  # pyright: ignore[reportPrivateUsage]
)
from .stock_observations import read_stock_observation_v1
from .storage_root_lease import StorageRootLease

CONTRACT_VERSION: Final = "scan-decision-evidence@v1"
ENVELOPE_SCHEMA: Final = "scan-decision-evidence-envelope@v1"
_NAMESPACE: Final = "scan-decision-evidence-v1"
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_MAX_BYTES: Final = 4 * 1024 * 1024
_MAX_LISTED_RECORDS: Final = 4096
_MAX_DEPTH: Final = 64
_SCAN_SCHEMA_V1: Final = "swing-trade-scan@v1"
_SCAN_SCHEMA_V2: Final = "swing-trade-scan@v2"
_SCAN_KEYS_V1: Final = frozenset(
    {
        "schema",
        "scan_timestamp",
        "storage_root_sha256",
        "universe_type",
        "universe_evidence",
        "nifty100_validated_candidate_count",
        "nifty500_fallback_triggered",
        "market_regime",
        "benchmark_median_return_20d",
        "total_stocks_scanned",
        "evaluated_symbols",
        "candidate_count",
        "eligible_count",
        "ineligible_count",
        "unknown_count",
        "candidates",
        "other_stocks",
        "runtime_code_identity_sha256",
        "result_identity_sha256",
    }
)
_SCAN_KEYS_V2: Final = frozenset(
    {
        "schema",
        "scan_timestamp",
        "storage_root_sha256",
        "universe_type",
        "universe_evidence",
        "priority_validated_candidate_count",
        "tier2_fallback_triggered",
        "market_regime",
        "benchmark_median_return_20d",
        "total_stocks_scanned",
        "evaluated_symbols",
        "candidate_count",
        "eligible_count",
        "ineligible_count",
        "unknown_count",
        "candidates",
        "other_stocks",
        "runtime_code_identity_sha256",
        "result_identity_sha256",
    }
)
_SCAN_KEYS: Final = {
    _SCAN_SCHEMA_V1: _SCAN_KEYS_V1,
    _SCAN_SCHEMA_V2: _SCAN_KEYS_V2,
}
_UNIVERSE_TYPES: Final = {
    _SCAN_SCHEMA_V1: frozenset({"EXPLICIT", "NIFTY_100_PRIORITY_NIFTY_500"}),
    _SCAN_SCHEMA_V2: frozenset(
        {"EXPLICIT", "NIFTY_50", "NIFTY_NEXT_50", "NIFTY_100", "NIFTY_200"}
    ),
}
_UNIVERSE_TOTALS: Final = {
    "NIFTY_100_PRIORITY_NIFTY_500": frozenset({500, 501}),
    "NIFTY_50": frozenset({50}),
    "NIFTY_NEXT_50": frozenset({50}),
    "NIFTY_100": frozenset({100}),
    "NIFTY_200": frozenset({200}),
}


class ScanDecisionEvidenceUnavailable(ValueError):
    """A retained scanner decision cannot be safely admitted."""


def _canonical(value: object) -> bytes:
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
    return hashlib.sha256(_canonical(value)).hexdigest()


def _closed(raw: bytes) -> dict[str, object]:
    if len(raw) > _MAX_BYTES:
        raise ValueError("record too large")
    parsed: object = json.loads(raw)
    if type(parsed) is not dict:
        raise ValueError("noncanonical record")
    value = cast(dict[str, object], parsed)
    if _canonical(value) != raw:
        raise ValueError("noncanonical record")
    _depth(value)
    return value


def _depth(value: object, level: int = 0) -> None:
    if level > _MAX_DEPTH:
        raise ValueError("record too deep")
    if type(value) is dict:
        for child in cast(dict[str, object], value).values():
            _depth(child, level + 1)
    elif type(value) is list:
        for child in cast(list[object], value):
            _depth(child, level + 1)


def _lease(root: object) -> StorageRootLease:
    if not isinstance(root, Path) or not root.is_absolute():
        raise ValueError("invalid evidence root")
    lease = legacy._acquire_root(root)  # pyright: ignore[reportPrivateUsage]
    if lease is None:
        raise ValueError("evidence root unavailable")
    return lease


def _validate_scan(scan: object) -> dict[str, object]:
    if type(scan) is not dict:
        raise ValueError("invalid scan")
    value = cast(dict[str, object], scan)
    schema = value.get("schema")
    if type(schema) is not str or schema not in _SCAN_KEYS:
        raise ValueError("invalid scan schema")
    if set(value) != set(_SCAN_KEYS[schema]):
        raise ValueError("invalid scan schema")
    if value.get("runtime_code_identity_sha256") != _scanner_runtime_identity():
        raise ValueError("scanner runtime mismatch")
    identity = value.get("result_identity_sha256")
    if type(identity) is not str or _DIGEST.fullmatch(identity) is None:
        raise ValueError("invalid scan identity")
    unsigned = dict(value)
    unsigned.pop("result_identity_sha256")
    if _digest(unsigned) != identity:
        raise ValueError("unadmitted scan")
    _validate_scan_shape(value)
    return value


def _validate_scan_shape(scan: dict[str, object]) -> None:
    raw_symbols = scan["evaluated_symbols"]
    raw_candidates = scan["candidates"]
    raw_other = scan["other_stocks"]
    total = scan["total_stocks_scanned"]
    if (
        type(total) is not int
        or type(raw_symbols) is not list
        or type(raw_candidates) is not list
        or type(raw_other) is not list
    ):
        raise ValueError("invalid scan shape")
    symbols = cast(list[object], raw_symbols)
    candidates = cast(list[object], raw_candidates)
    other = cast(list[object], raw_other)
    if (
        any(type(symbol) is not str for symbol in symbols)
        or len(symbols) != total
        or len(set(cast(list[str], symbols))) != total
        or scan["candidate_count"] != len(candidates)
        or any(type(item) is not dict for item in candidates + other)
    ):
        raise ValueError("invalid scan shape")
    schema = scan["schema"]
    universe_type = scan["universe_type"]
    if universe_type not in _UNIVERSE_TYPES[cast(str, schema)]:
        raise ValueError("invalid universe type")
    if universe_type == "EXPLICIT":
        if not 1 <= total <= 100 or scan["universe_evidence"] is not None:
            raise ValueError("invalid explicit selection")
        return
    if (
        total not in _UNIVERSE_TOTALS[cast(str, universe_type)]
        or type(scan["universe_evidence"]) is not dict
    ):
        raise ValueError("invalid universe selection")


def _rows(  # noqa: C901 - complete fail-closed evidence binding
    root: Path, scan: dict[str, object], rows: object
) -> list[dict[str, object]]:
    raw_symbols = scan.get("evaluated_symbols")
    raw_candidates = scan.get("candidates")
    raw_other = scan.get("other_stocks")
    if (
        type(rows) is not list
        or type(raw_symbols) is not list
        or type(raw_candidates) is not list
        or type(raw_other) is not list
    ):
        raise ValueError("invalid evidence rows")
    symbols = cast(list[object], raw_symbols)
    candidates = cast(list[object], raw_candidates)
    other = cast(list[object], raw_other)
    evidence_rows = cast(list[object], rows)
    if len(symbols) != scan.get("total_stocks_scanned"):
        raise ValueError("invalid evidence rows")
    outcomes: dict[str, tuple[str, str]] = {}
    for item in candidates:
        if type(item) is not dict:
            raise ValueError("invalid candidate")
        candidate = cast(dict[str, object], item)
        symbol = candidate.get("symbol")
        decision = candidate.get("decision")
        safety = candidate.get("safety_eligibility")
        if (
            type(symbol) is not str
            or type(decision) is not str
            or type(safety) is not dict
        ):
            raise ValueError("invalid candidate")
        safety_value = cast(dict[str, object], safety)
        status = safety_value.get("status")
        if type(status) is not str:
            raise ValueError("invalid candidate")
        outcomes[symbol] = (decision, status)
    for item in other:
        if type(item) is not dict:
            raise ValueError("invalid stock")
        stock = cast(dict[str, object], item)
        symbol = stock.get("symbol")
        decision = stock.get("decision")
        safety = stock.get("safety_status")
        if (
            type(symbol) is not str
            or type(decision) is not str
            or type(safety) is not str
        ):
            raise ValueError("invalid stock")
        outcomes[symbol] = (decision, safety)
    if (
        any(type(symbol) is not str for symbol in symbols)
        or len(set(cast(list[str], symbols))) != len(symbols)
        or set(cast(list[str], symbols)) != set(outcomes)
    ):
        raise ValueError("selection binding mismatch")
    admitted: list[dict[str, object]] = []
    for position, item in enumerate(evidence_rows):
        if type(item) is not dict:
            raise ValueError("invalid evidence row")
        row = cast(dict[str, object], item)
        if set(row) != {"symbol", "decision", "safety_status", "observation_handle"}:
            raise ValueError("invalid evidence row")
        symbol, decision, safety, handle = (
            row.get("symbol"),
            row.get("decision"),
            row.get("safety_status"),
            row.get("observation_handle"),
        )
        if (
            type(symbol) is not str
            or type(decision) is not str
            or type(safety) is not str
            or position >= len(symbols)
            or symbol != symbols[position]
            or outcomes.get(symbol) != (decision, safety)
        ):
            raise ValueError("evidence binding mismatch")
        if handle is None:
            if decision != "UNKNOWN" or safety != "UNKNOWN":
                raise ValueError("terminal state mismatch")
        else:
            if type(handle) is not str or _DIGEST.fullmatch(handle) is None:
                raise ValueError("invalid evidence handle")
            observation = read_stock_observation_v1(root, handle)
            if (
                observation.question != "CURRENT_STRUCTURE"
                or observation.status != "READY"
                or observation.symbol != symbol
            ):
                raise ValueError("observation binding mismatch")
        admitted.append(row)
    if len(admitted) != len(symbols):
        raise ValueError("evidence count mismatch")
    return admitted


def _record_scan_decision_evidence_v1(  # pyright: ignore[reportUnusedFunction]
    root: Path, scan: dict[str, object], rows: list[dict[str, object]]
) -> str:
    """Persist scanner-owned state only after every admitted observation revalidates."""
    try:
        admitted_scan = _validate_scan(scan)
        admitted_rows = _rows(root, admitted_scan, rows)
        raw = _canonical(
            {
                "contract_version": CONTRACT_VERSION,
                "scan": admitted_scan,
                "scan_result_identity_sha256": admitted_scan["result_identity_sha256"],
                "symbol_evidence": admitted_rows,
            }
        )
        _closed(raw)
        handle = hashlib.sha256(raw).hexdigest()
        with (
            _lease(root) as lease,
            lease.root_operation(root) as operation,
            private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                operation, operation.descriptor, _NAMESPACE, create=True
            ) as directory,
        ):
            private_store.publish_capture_bytes(
                operation, directory, f"{handle}.json", raw
            )
        return handle
    except Exception as error:  # noqa: BLE001 - closed persistence boundary
        raise ScanDecisionEvidenceUnavailable(
            "DECISION_EVIDENCE_UNAVAILABLE"
        ) from error


def _admitted_handle(
    directory: private_store._PrivateDirectory,  # pyright: ignore[reportPrivateUsage]
    name: str,
) -> str:
    handle = name.removesuffix(".json")
    if not name.endswith(".json") or _DIGEST.fullmatch(handle) is None:
        raise ValueError("unexpected decision evidence entry")
    try:
        info = os.stat(name, dir_fd=directory.descriptor, follow_symlinks=False)
    except OSError as error:
        raise ValueError("decision evidence entry unreadable") from error
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o400
        or not 1 <= info.st_size <= _MAX_BYTES
    ):
        raise ValueError("unsafe decision evidence entry")
    return handle


def list_scan_decision_evidence_handles_v1(root: Path) -> tuple[str, ...]:
    """List retained immutable decision-evidence handles in deterministic order.

    A missing namespace means no retained evidence. Any foreign, unsafe, or
    oversized entry fails closed instead of being silently skipped.
    """
    try:
        with _lease(root) as lease, ExitStack() as stack:
            operation = stack.enter_context(lease.read_operation(root))
            try:
                directory = stack.enter_context(
                    private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                        operation, operation.descriptor, _NAMESPACE, create=False
                    )
                )
            except FileNotFoundError:
                return ()
            names = os.listdir(directory.descriptor)
            if len(names) > _MAX_LISTED_RECORDS:
                raise ValueError("decision evidence store exceeded")
            handles = sorted(_admitted_handle(directory, name) for name in names)
            directory.ensure_live()
        return tuple(handles)
    except ScanDecisionEvidenceUnavailable:
        raise
    except Exception as error:  # noqa: BLE001 - redacted public read boundary
        raise ScanDecisionEvidenceUnavailable(
            "DECISION_EVIDENCE_UNAVAILABLE"
        ) from error


def read_scan_decision_evidence_v1(root: Path, handle: str) -> dict[str, object]:
    """Re-admit a selected immutable decision record without provider access."""
    try:
        if type(handle) is not str or _DIGEST.fullmatch(handle) is None:
            raise ValueError("invalid evidence handle")
        with _lease(root) as lease, ExitStack() as stack:
            operation = stack.enter_context(lease.read_operation(root))
            directory = stack.enter_context(
                private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                    operation, operation.descriptor, _NAMESPACE, create=False
                )
            )
            raw = private_store.read_exact_capture_file(
                operation, directory, f"{handle}.json", _MAX_BYTES
            )
            directory.ensure_live()
        saved = _closed(raw)
        if (
            hashlib.sha256(raw).hexdigest() != handle
            or set(saved)
            != {
                "contract_version",
                "scan",
                "scan_result_identity_sha256",
                "symbol_evidence",
            }
            or saved["contract_version"] != CONTRACT_VERSION
        ):
            raise ValueError("unsupported evidence record")
        scan = _validate_scan(saved["scan"])
        if saved["scan_result_identity_sha256"] != scan["result_identity_sha256"]:
            raise ValueError("scan binding mismatch")
        _rows(root, scan, saved["symbol_evidence"])
        return {
            "schema": ENVELOPE_SCHEMA,
            "decision_evidence_handle": handle,
            "scan": scan,
        }
    except Exception as error:  # noqa: BLE001 - redacted public read boundary
        raise ScanDecisionEvidenceUnavailable(
            "DECISION_EVIDENCE_UNAVAILABLE"
        ) from error
