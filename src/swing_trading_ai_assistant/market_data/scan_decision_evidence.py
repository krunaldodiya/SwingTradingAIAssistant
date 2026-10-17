"""Immutable, source-bound scanner decision evidence for later G09 qualification."""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import ExitStack
from pathlib import Path
from typing import Final, cast

from . import capture_forward_adjusted_ohlcv as private_store
from . import current_stock_research as legacy
from .stock_observations import read_stock_observation_v1
from .storage_root_lease import StorageRootLease

CONTRACT_VERSION: Final = "scan-decision-evidence@v1"
ENVELOPE_SCHEMA: Final = "scan-decision-evidence-envelope@v1"
_NAMESPACE: Final = "scan-decision-evidence-v1"
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_MAX_BYTES: Final = 4 * 1024 * 1024


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
    return value


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
    identity = value.get("result_identity_sha256")
    if type(identity) is not str or _DIGEST.fullmatch(identity) is None:
        raise ValueError("invalid scan identity")
    unsigned = dict(value)
    unsigned.pop("result_identity_sha256", None)
    if _digest(unsigned) != identity or value.get("schema") != "swing-trade-scan@v1":
        raise ValueError("unadmitted scan")
    return value


def _rows(root: Path, scan: dict[str, object], rows: object) -> list[dict[str, object]]:
    if type(rows) is not list or not rows:
        raise ValueError("invalid evidence rows")
    expected: dict[str, tuple[str, str]] = {}
    for item in cast(list[object], rows):
        if type(item) is not dict:
            raise ValueError("invalid evidence row")
        row = cast(dict[str, object], item)
        symbol, decision, safety, handle = (
            row.get("symbol"),
            row.get("decision"),
            row.get("safety_status"),
            row.get("observation_handle"),
        )
        if not all(type(value) is str for value in (symbol, decision, safety)):
            raise ValueError("invalid evidence row")
        if handle is not None and (
            type(handle) is not str or _DIGEST.fullmatch(handle) is None
        ):
            raise ValueError("invalid evidence handle")
        if cast(str, symbol) in expected:
            raise ValueError("duplicate evidence symbol")
        if handle is not None:
            observation = read_stock_observation_v1(root, handle)
            if (
                observation.question != "CURRENT_STRUCTURE"
                or observation.symbol != symbol
            ):
                raise ValueError("observation binding mismatch")
        expected[cast(str, symbol)] = (cast(str, decision), cast(str, safety))
    if len(expected) != scan.get("total_stocks_scanned"):
        raise ValueError("evidence count mismatch")
    return [cast(dict[str, object], item) for item in cast(list[object], rows)]


def record_scan_decision_evidence_v1(
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
            rows = _rows(root, scan, saved["symbol_evidence"])
            directory.ensure_live()
            return {
                "schema": ENVELOPE_SCHEMA,
                "decision_evidence_handle": handle,
                "scan": scan,
                "symbol_evidence": rows,
            }
    except Exception as error:  # noqa: BLE001 - redacted public read boundary
        raise ScanDecisionEvidenceUnavailable(
            "DECISION_EVIDENCE_UNAVAILABLE"
        ) from error
