"""Inspect a fixed owner-staged NSE safety-evidence package without clearance."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockResearchPacketV2,
    validate_bharatstock_research_packet_v2,
)

from .current_stock_research_v2 import CurrentStockResearchResultV2
from .owner_staged_nse_safety_evidence_runtime_identity_manifest import (
    OWNER_STAGED_NSE_SAFETY_EVIDENCE_RUNTIME_SOURCE_SHA256_V1,
)
from .runtime_source_verifier import runtime_source_sha256, same_metadata
from .stock_observations import read_stock_observation_v1
from .storage_root_lease import StorageRootLease, StorageRootLeaseOperation

SCHEMA: Final = "stock-safety-evidence@v1"
MAX_ARTIFACT_BYTES_V1: Final = 1024 * 1024
MAX_ROWS_V1: Final = 10_000
MAX_FIELD_CHARACTERS_V1: Final = 1_024
MAX_RESULT_BYTES_V1: Final = 64 * 1024
_PACKAGE_NAME: Final = "nse-safety-evidence-v1"
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_LISTING_DATE: Final = re.compile(r"([0-9]{2})-([A-Za-z]{3})-([0-9]{4})\Z")
_MONTHS: Final = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
_REFUSAL_REASONS: Final = (
    "OPERATOR_STAGED_EVIDENCE_NOT_SOURCE_AUTHENTICATED",
    "LISTING_DURATION_POLICY_UNAVAILABLE",
    "EXECUTION_LIQUIDITY_POLICY_UNAVAILABLE",
    "PRICE_CURRENCY_AND_LOW_PRICE_POLICY_UNAVAILABLE",
    "EVENT_RISK_COVERAGE_UNAVAILABLE",
)
_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/owner_staged_nse_safety_evidence.py",
    "src/swing_trading_ai_assistant/market_data/owner_staged_nse_safety_evidence_cli.py",
    "src/swing_trading_ai_assistant/entrypoints/stock_safety_evidence.py",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py",
)
_MANIFEST: Final = (
    "src/swing_trading_ai_assistant/market_data/"
    "owner_staged_nse_safety_evidence_runtime_identity_manifest.py"
)


class OwnerStagedNseSafetyEvidenceUnavailableV1(ValueError):
    """The selected staged package cannot produce a public staging report."""


@dataclass(frozen=True, slots=True)
class _ArtifactSpec:
    name: str
    kind: str
    reference_page: str


_ARTIFACTS: Final = (
    _ArtifactSpec(
        "equity-trading.csv",
        "EQUITY_TRADING",
        "https://www.nseindia.com/market-data/securities-available-for-trading",
    ),
    _ArtifactSpec(
        "asm.csv",
        "ASM",
        "https://www.nseindia.com/regulations/additional-surveillance-measure",
    ),
    _ArtifactSpec(
        "gsm.csv",
        "GSM",
        "https://www.nseindia.com/regulations/graded-surveillance-measure",
    ),
)
_EXPECTED_NAMES: Final = frozenset(item.name for item in _ARTIFACTS)
_EQUITY_COLUMNS: Final = frozenset(
    {"SYMBOL", "SERIES", "ISIN_NUMBER", "DATE_OF_LISTING"}
)
_SURVEILLANCE_COLUMNS: Final = frozenset({"SYMBOL"})


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _runtime_identity() -> str:
    if tuple(OWNER_STAGED_NSE_SAFETY_EVIDENCE_RUNTIME_SOURCE_SHA256_V1) != _SOURCES:
        raise ValueError("safety evidence runtime inventory invalid")
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for (
        relative,
        expected,
    ) in OWNER_STAGED_NSE_SAFETY_EVIDENCE_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("safety evidence runtime identity invalid")
        observed[relative] = actual
    observed[_MANIFEST] = runtime_source_sha256(
        "swing_trading_ai_assistant.market_data."
        "owner_staged_nse_safety_evidence_runtime_identity_manifest",
        root,
        _MANIFEST,
    )
    return _digest(observed)


def _valid_request(storage_root: object, observation: object) -> tuple[Path, str]:
    if (
        not isinstance(storage_root, Path)
        or not storage_root.is_absolute()
        or type(observation) is not str
        or _DIGEST.fullmatch(observation) is None
    ):
        raise ValueError("invalid safety evidence request")
    return storage_root, observation


def _admitted_structure_identity(
    observation: CurrentStockResearchResultV2,
) -> tuple[str, str]:
    if (
        type(observation) is not CurrentStockResearchResultV2
        or observation.question != "CURRENT_STRUCTURE"
        or observation.status != "READY"
        or type(observation.packet) is not BharatStockResearchPacketV2
    ):
        raise ValueError("current structure observation required")
    packet = validate_bharatstock_research_packet_v2(observation.packet)
    if len(packet.members) != 1 or len(packet.mapping_projection.members) != 1:
        raise ValueError("current structure mapping invalid")
    mapping = packet.mapping_projection.members[0]
    member = packet.members[0]
    if (
        mapping.instrument_type != "EQUITY"
        or mapping.segment != "EQ"
        or mapping.exchange != "NSE"
        or mapping.effective_symbol != observation.symbol
        or (mapping.isin, mapping.exchange, mapping.effective_symbol)
        != (member.member.isin, member.member.exchange, member.member.symbol)
    ):
        raise ValueError("current structure mapping invalid")
    return mapping.effective_symbol, mapping.isin


def _private_package(info: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(info.st_mode)
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == 0o700
    )


def _private_artifact(info: os.stat_result) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) in {0o400, 0o600}
        and info.st_nlink == 1
        and 1 <= info.st_size <= MAX_ARTIFACT_BYTES_V1
    )


def _package_binding(
    parent: int, descriptor: int
) -> tuple[os.stat_result, os.stat_result]:
    named = os.stat(_PACKAGE_NAME, dir_fd=parent, follow_symlinks=False)
    opened = os.fstat(descriptor)
    if (
        not _private_package(named)
        or not _private_package(opened)
        or not same_metadata(named, opened)
    ):
        raise ValueError("unsafe staged package")
    return named, opened


def _checked_entries(descriptor: int) -> None:
    entries = os.listdir(descriptor)
    if len(entries) != len(_EXPECTED_NAMES) or frozenset(entries) != _EXPECTED_NAMES:
        raise ValueError("unexpected staged package entry")


def _read_exact_artifact(parent: int, name: str) -> bytes:
    descriptor: int | None = None
    try:
        named_before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent,
        )
        opened_before = os.fstat(descriptor)
        if (
            not _private_artifact(named_before)
            or not _private_artifact(opened_before)
            or not same_metadata(named_before, opened_before)
        ):
            raise ValueError("unsafe staged artifact")
        remaining = opened_before.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                raise ValueError("short staged artifact")
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        named_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        opened_after = os.fstat(descriptor)
        if (
            len(raw) != opened_before.st_size
            or not same_metadata(named_before, named_after)
            or not same_metadata(opened_before, opened_after)
            or not _private_artifact(named_after)
        ):
            raise ValueError("staged artifact changed")
        return raw
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _fixed_package_bytes(operation: StorageRootLeaseOperation) -> dict[str, bytes]:
    package: int | None = None
    try:
        operation.ensure_live()
        parent = operation.descriptor
        named_before = os.stat(_PACKAGE_NAME, dir_fd=parent, follow_symlinks=False)
        package = os.open(
            _PACKAGE_NAME,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent,
        )
        opened_before = os.fstat(package)
        if (
            not _private_package(named_before)
            or not _private_package(opened_before)
            or not same_metadata(named_before, opened_before)
        ):
            raise ValueError("unsafe staged package")
        _checked_entries(package)
        artifacts: dict[str, bytes] = {}
        for spec in _ARTIFACTS:
            operation.ensure_live()
            artifacts[spec.name] = _read_exact_artifact(package, spec.name)
            _package_binding(parent, package)
        _checked_entries(package)
        named_after = os.stat(_PACKAGE_NAME, dir_fd=parent, follow_symlinks=False)
        opened_after = os.fstat(package)
        if not same_metadata(named_before, named_after) or not same_metadata(
            opened_before, opened_after
        ):
            raise ValueError("staged package changed")
        operation.ensure_live()
        return artifacts
    finally:
        if package is not None:
            os.close(package)


def _decode_rows(raw: bytes) -> list[list[str]]:
    try:
        text = raw.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except (UnicodeDecodeError, csv.Error) as error:
        raise ValueError("invalid staged csv") from error
    if not rows:
        raise ValueError("staged csv missing header")
    return rows


def _controlled(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _field(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > MAX_FIELD_CHARACTERS_V1
        or _controlled(value)
        or value != value.strip()
        or value[0] in "=+-@"
    ):
        raise ValueError("invalid staged csv field")
    return value


def _header(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > MAX_FIELD_CHARACTERS_V1
        or _controlled(value)
    ):
        raise ValueError("invalid staged csv header")
    normalized = "_".join(value.strip().upper().replace("-", " ").split())
    if re.fullmatch(r"[A-Z][A-Z0-9_]*", normalized) is None:
        raise ValueError("invalid staged csv header")
    return normalized


def _rows_with_columns(raw: bytes, expected: frozenset[str]) -> list[dict[str, str]]:
    rows = _decode_rows(raw)
    headers = tuple(_header(value) for value in rows[0])
    if len(headers) != len(expected) or frozenset(headers) != expected:
        raise ValueError("unsupported staged csv headers")
    if len(set(headers)) != len(headers):
        raise ValueError("duplicate staged csv header")
    result: list[dict[str, str]] = []
    for row in rows[1:]:
        if len(result) >= MAX_ROWS_V1 or len(row) != len(headers):
            raise ValueError("invalid staged csv row")
        result.append(dict(zip(headers, (_field(value) for value in row), strict=True)))
    return result


def _listing_date(value: str) -> None:
    parsed = _LISTING_DATE.fullmatch(value)
    month = None if parsed is None else _MONTHS.get(parsed.group(2).upper())
    if parsed is None or month is None:
        raise ValueError("invalid staged listing date")
    try:
        date(int(parsed.group(3)), month, int(parsed.group(1)))
    except ValueError as error:
        raise ValueError("invalid staged listing date") from error


def _equity_listing_observed(raw: bytes, symbol: str, isin: str) -> bool:
    selected = 0
    identities: set[tuple[str, str, str]] = set()
    for row in _rows_with_columns(raw, _EQUITY_COLUMNS):
        identity = (row["SYMBOL"], row["SERIES"], row["ISIN_NUMBER"])
        if identity in identities:
            raise ValueError("duplicate staged equity identity")
        identities.add(identity)
        if (
            row["SERIES"] == "EQ"
            and row["SYMBOL"] == symbol
            and row["ISIN_NUMBER"] == isin
        ):
            _listing_date(row["DATE_OF_LISTING"])
            selected += 1
    if selected != 1:
        raise ValueError("selected staged equity row unavailable")
    return True


def _surveillance_membership(raw: bytes, symbol: str) -> str:
    seen: set[str] = set()
    matched = False
    for row in _rows_with_columns(raw, _SURVEILLANCE_COLUMNS):
        item = row["SYMBOL"]
        if item in seen:
            raise ValueError("duplicate staged surveillance symbol")
        seen.add(item)
        matched = matched or item == symbol
    return "OBSERVED_IN_STAGED_LIST" if matched else "NOT_OBSERVED_IN_STAGED_LIST"


def _read_staged_artifacts(
    root: Path, root_identity: tuple[int, int]
) -> dict[str, bytes]:
    admitted = StorageRootLease.try_admit_read_existing(root, root_identity)
    lease = admitted.lease
    if lease is None:
        raise ValueError("staged root unavailable")
    with lease, lease.read_operation(root) as operation:
        return _fixed_package_bytes(operation)


def _result(
    *,
    symbol: str,
    observation: str,
    runtime: str,
    artifact_bytes: dict[str, bytes],
    listing_date_observed: bool,
    asm_membership: str,
    gsm_membership: str,
) -> dict[str, object]:
    artifacts = [
        {
            "kind": spec.kind,
            "reference_page": spec.reference_page,
            "artifact_sha256": hashlib.sha256(artifact_bytes[spec.name]).hexdigest(),
        }
        for spec in _ARTIFACTS
    ]
    package_identity = _digest(
        {
            "contract_version": SCHEMA,
            "package": _PACKAGE_NAME,
            "artifacts": artifacts,
        }
    )
    result: dict[str, object] = {
        "schema": SCHEMA,
        "status": "STAGED",
        "eligibility_status": "UNKNOWN",
        "symbol": symbol,
        "observation_identity_sha256": observation,
        "operator_staged_evidence": {
            "package_identity_sha256": package_identity,
            "artifacts": artifacts,
            "listing_date_observed": listing_date_observed,
            "asm_membership": asm_membership,
            "gsm_membership": gsm_membership,
        },
        "refusal_reasons": list(_REFUSAL_REASONS),
        "runtime_code_identity_sha256": runtime,
    }
    result["result_identity_sha256"] = _digest(result)
    if len(_canonical(result)) > MAX_RESULT_BYTES_V1:
        raise ValueError("staged result too large")
    return result


def inspect_owner_staged_nse_safety_evidence_v1(
    storage_root: Path, observation: str
) -> dict[str, object]:
    """Re-admit one retained observation and inspect fixed private staged bytes.

    A successful report only proves that the local package matched this bounded
    shape. It deliberately retains ``eligibility_status: UNKNOWN``.
    """
    root, handle = _valid_request(storage_root, observation)
    try:
        root_identity = StorageRootLease.admit_existing_private_identity(root)
        if root_identity is None:
            raise ValueError("staged root unavailable")
        observed = read_stock_observation_v1(root, handle)
        if StorageRootLease.admit_existing_private_identity(root) != root_identity:
            raise ValueError("staged root changed")
        symbol, isin = _admitted_structure_identity(observed)
        runtime = _runtime_identity()
        artifact_bytes = _read_staged_artifacts(root, root_identity)
        return _result(
            symbol=symbol,
            observation=handle,
            runtime=runtime,
            artifact_bytes=artifact_bytes,
            listing_date_observed=_equity_listing_observed(
                artifact_bytes["equity-trading.csv"], symbol, isin
            ),
            asm_membership=_surveillance_membership(artifact_bytes["asm.csv"], symbol),
            gsm_membership=_surveillance_membership(artifact_bytes["gsm.csv"], symbol),
        )
    except Exception as error:  # noqa: BLE001 - complete staged-evidence boundary
        raise OwnerStagedNseSafetyEvidenceUnavailableV1(
            "STAGED_EVIDENCE_UNAVAILABLE"
        ) from error


__all__ = [
    "MAX_ARTIFACT_BYTES_V1",
    "MAX_FIELD_CHARACTERS_V1",
    "MAX_ROWS_V1",
    "OwnerStagedNseSafetyEvidenceUnavailableV1",
    "SCHEMA",
    "inspect_owner_staged_nse_safety_evidence_v1",
]
