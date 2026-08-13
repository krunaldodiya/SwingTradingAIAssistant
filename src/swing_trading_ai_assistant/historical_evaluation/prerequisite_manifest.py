"""Fail-closed admission manifest for retained Sprint 4 evidence.

This application deliberately stops before the ARK-163 evaluator.  The retained
Sprint 4 bundle has no genuine prospective declaration receipt, so manufacturing
one from CLI or filesystem timestamps would violate the frozen time model.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, cast

from swing_trading_ai_assistant.market_data.schedule_evidence import (
    canonical_schedule_bytes,
    parse_canonical_schedule_bytes,
)
from swing_trading_ai_assistant.market_data.universe_snapshot import (
    Nifty50UniverseSnapshotV1,
)

PREREQUISITE_MANIFEST_CONTRACT_VERSION_V1: Final = (
    "evidence-readiness-prerequisite-manifest@v1"
)
READINESS_CONTRACT_VERSION_V1: Final = "forward-pit-evidence-readiness@v1"
SOURCE_POLICY_VERSION_V1: Final = "prospective-pit-evidence-source-policy@v1"
# Both labels are defined by the exact canonical Plan 11 repository bytes.
_PLAN11_CONTRACT_SHA256: Final = (
    "4430c270c236660e04c30fa9cccd053c742eeb49b0f6c70724b93218121ec6ae"
)
READINESS_CONTRACT_IDENTITY_SHA256_V1: Final = _PLAN11_CONTRACT_SHA256
SOURCE_POLICY_IDENTITY_SHA256_V1: Final = _PLAN11_CONTRACT_SHA256

_RETAINED_SEAL_SHA256: Final = (
    "3c0450aa4885dcfbf7f1e94673a2b4fec402b184dd7d224d849b4a44e537d809"
)
_RETAINED_UNIVERSE_SHA256: Final = (
    "936a32c8dee5d852221a159434064be79380fe75a40029c1e0b506c0086e0b30"
)
_RETAINED_JULY_SCHEDULE_SHA256: Final = (
    "7c8cdef86c3874f9542a9544821805bfc23787975e29d0f297164776b5816db9"
)
_RETAINED_AUGUST_SCHEDULE_SHA256: Final = (
    "09f7e6b8477d4588668957f3d063acd3982d4cb7c7f1ebcde49f3dbc496e5930"
)
_RETAINED_COVERAGE_SHA256: Final = (
    "ee0425ecbe7e4a269b40f92a895023d7b75a986531d1b9638403e8382e3a2fab"
)
_RETAINED_DATASET_IDENTITY_SHA256: Final = (
    "60e308121fb462283ed0295b02d71272ee13eed8e300f01420358cd0c2b5ae34"
)
_RETAINED_ACCOUNTING_SHA256: Final = (
    "4ba819520e904929fc3fcdb977ab3d767e9f2f9bb4dfeba610571a3337b05762"
)
_RETAINED_EQUITY_IDENTITIES: Final = (
    ("INE002A01018", "RELIANCE"),
    ("INE009A01021", "INFY"),
    ("INE018A01030", "LT"),
    ("INE019A01038", "JSWSTEEL"),
    ("INE021A01026", "ASIANPAINT"),
    ("INE027H01010", "MAXHEALTH"),
    ("INE030A01027", "HINDUNILVR"),
    ("INE038A01020", "HINDALCO"),
    ("INE040A01034", "HDFCBANK"),
    ("INE044A01036", "SUNPHARMA"),
    ("INE047A01021", "GRASIM"),
    ("INE059A01026", "CIPLA"),
    ("INE062A01020", "SBIN"),
    ("INE066A01021", "EICHERMOT"),
    ("INE075A01022", "WIPRO"),
    ("INE081A01020", "TATASTEEL"),
    ("INE089A01031", "DRREDDY"),
    ("INE090A01021", "ICICIBANK"),
    ("INE101A01026", "M&M"),
    ("INE123W01016", "SBILIFE"),
    ("INE154A01025", "ITC"),
    ("INE155A01022", "TMPV"),
    ("INE192A01025", "TATACONSUM"),
    ("INE213A01029", "ONGC"),
    ("INE237A01036", "KOTAKBANK"),
    ("INE238A01034", "AXISBANK"),
    ("INE239A01024", "NESTLEIND"),
    ("INE263A01024", "BEL"),
    ("INE280A01028", "TITAN"),
    ("INE296A01032", "BAJFINANCE"),
    ("INE397D01024", "BHARTIARTL"),
    ("INE423A01024", "ADANIENT"),
    ("INE437A01024", "APOLLOHOSP"),
    ("INE467B01029", "TCS"),
    ("INE481G01011", "ULTRACEMCO"),
    ("INE522F01014", "COALINDIA"),
    ("INE585B01010", "MARUTI"),
    ("INE646L01027", "INDIGO"),
    ("INE669C01036", "TECHM"),
    ("INE721A01047", "SHRIRAMFIN"),
    ("INE733E01010", "NTPC"),
    ("INE742F01042", "ADANIPORTS"),
    ("INE752E01010", "POWERGRID"),
    ("INE758E01017", "JIOFIN"),
    ("INE758T01015", "ETERNAL"),
    ("INE795G01014", "HDFCLIFE"),
    ("INE849A01020", "TRENT"),
    ("INE860A01027", "HCLTECH"),
    ("INE917I01010", "BAJAJ-AUTO"),
    ("INE918I01026", "BAJAJFINSV"),
)
_MAX_SEAL_BYTES: Final = 128 * 1024
_MAX_UNIVERSE_BYTES: Final = 64 * 1024
_MAX_SCHEDULE_BYTES: Final = 1_000_000
_MAX_COVERAGE_BYTES: Final = 128 * 1024
_MAX_JSON_DEPTH: Final = 16
_MAX_JSON_LIST: Final = 512
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_CODE_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}\Z")

_RETAINED_OBJECTS: Final = (
    ("AUGUST_SCHEDULE", _RETAINED_AUGUST_SCHEDULE_SHA256),
    ("COVERAGE_MANIFEST", _RETAINED_COVERAGE_SHA256),
    ("JULY_SCHEDULE", _RETAINED_JULY_SCHEDULE_SHA256),
    ("SPRINT4_SEAL", _RETAINED_SEAL_SHA256),
    ("UNIVERSE", _RETAINED_UNIVERSE_SHA256),
)

_PREREQUISITES: Final = (
    (
        "GENUINE_DECLARATION_RECEIPT",
        (
            "DECLARED_AT",
            "RETAINED_AT",
            "TRUSTED_CLOCK_IDENTITY_SHA256",
            "RECEIPT_IDENTITY_SHA256",
        ),
        "MISSING",
    ),
    (
        "MEMBERSHIP_PUBLICATION_RETRIEVAL_PROOF_TERMS",
        (
            "AUTHORITATIVE_PUBLICATION_BYTES",
            "PUBLIC_AVAILABILITY_PROOF",
            "RETRIEVAL_RECEIPT",
            "REVISION_LINEAGE",
            "TERMS_LICENCE_REVIEW",
        ),
        "MISSING",
    ),
    (
        "SECTOR_PUBLICATION_RETRIEVAL_PROOF_TERMS",
        (
            "AUTHORITATIVE_CLASSIFICATION_BYTES",
            "PUBLIC_AVAILABILITY_PROOF",
            "RETRIEVAL_RECEIPT",
            "REVISION_LINEAGE",
            "TERMS_LICENCE_REVIEW",
        ),
        "MISSING",
    ),
    (
        "SCHEDULE_PUBLICATION_RETRIEVAL_PROOF_TERMS",
        (
            "NSE_CAPITAL_MARKET_SOURCE_BYTES",
            "PUBLIC_AVAILABILITY_PROOF",
            "RETRIEVAL_RECEIPT",
            "REVISION_OVERLAYS",
            "TERMS_LICENCE_REVIEW",
        ),
        "MISSING",
    ),
    (
        "LATER_APPROVED_EVIDENCE_CAPABILITIES",
        (
            "MEMBERSHIP_CAPABILITY_APPROVAL",
            "SECTOR_CAPABILITY_APPROVAL",
            "SCHEDULE_CAPABILITY_APPROVAL",
            "CORPORATE_ACTION_CAPABILITY_APPROVAL",
            "ANCHOR_SESSION_CAPABILITY_APPROVAL",
        ),
        "NOT_APPROVED",
    ),
    (
        "SEPARATE_EVIDENCE_EXECUTION_AUTHORIZATION",
        (
            "OWNER_DECISION_IDENTITY",
            "EXACT_MANIFEST_SCOPE",
            "BOUNDED_ATTEMPTS_AND_BYTES",
            "EXPIRY",
            "TRUSTED_VALIDATION_RECEIPT",
        ),
        "NOT_PRESENT",
    ),
)


_ROLE_BOUNDARIES: Final = (
    "UPSTOX_MARKET_DATA_ONLY",
    "UPSTOX_NOT_MEMBERSHIP_SECTOR_SCHEDULE_OR_CORPORATE_ACTION_COMPLETENESS_AUTHORITY",
    "FUTURE_PER_ACCOUNT_READ_ONLY_PORTFOLIO_CONNECTOR_MAY_USE_OTHER_BROKERS_AND_IS_OUT_OF_SCOPE",
    "FUTURE_DISTINCT_ORDER_CONNECTOR_MAY_USE_OTHER_BROKERS_AND_IS_OUT_OF_SCOPE",
    "NO_BROKER_ORDERS",
    "NO_PREDICTION_SIGNAL_OPPORTUNITY_ACCURACY_STRATEGY_PROFITABILITY_OR_RECOMMENDATION_CLAIM",
)

_CORPORATE_ACTION_BLOCKERS: Final = (
    "UPSTOX_CANNOT_PROVE_AUTHORITATIVE_ACTION_STATUS_OR_TERMS",
    "UPSTOX_CANNOT_PROVE_NEGATIVE_CORPORATE_ACTION_COMPLETENESS",
    "UPSTOX_HAS_NO_DOCUMENTED_COMPLETENESS_THROUGH_OR_REVISION_SEMANTICS",
)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _valid_digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _reject_constant(_: str) -> object:
    raise ValueError("invalid JSON constant")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _check_json_bounds(value: object, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("JSON depth exceeded")
    if type(value) is list:
        items = cast(list[object], value)
        if len(items) > _MAX_JSON_LIST:
            raise ValueError("JSON list exceeded")
        for item in items:
            _check_json_bounds(item, depth + 1)
    elif type(value) is dict:
        for item in cast(dict[str, object], value).values():
            _check_json_bounds(item, depth + 1)


def _strict_json(raw: bytes, *, sorted_keys: bool) -> dict[str, object]:
    value = json.loads(
        raw,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )
    _check_json_bounds(value)
    if type(value) is not dict:
        raise ValueError("JSON object required")
    parsed = cast(dict[str, object], value)
    if sorted_keys and _canonical(parsed) != raw:
        raise ValueError("noncanonical JSON")
    return parsed


def _bounded_regular_file(path: Path, maximum: int) -> bytes:
    """Descriptor-walk parents and read a bounded regular leaf without symlinks."""
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory is None:
        raise ValueError("safe path traversal unavailable")
    parts = path.parts
    if not parts or path.name in ("", ".", "..") or ".." in parts:
        raise ValueError("inadmissible path")
    directory_flags = os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0)
    parent = os.open("/" if path.is_absolute() else ".", directory_flags)
    try:
        parent_parts = parts[1:-1] if path.is_absolute() else parts[:-1]
        for component in parent_parts:
            if component in ("", ".", ".."):
                raise ValueError("inadmissible path component")
            child = os.open(component, directory_flags, dir_fd=parent)
            os.close(parent)
            parent = child
        flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0) | nofollow
        descriptor = os.open(path.name, flags, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
            raise ValueError("inadmissible file")
        raw = bytearray()
        while len(raw) <= before.st_size:
            chunk = os.read(descriptor, min(64 * 1024, before.st_size + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(descriptor)
        if (
            len(raw) != before.st_size
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
        ):
            raise ValueError("file changed")
        return bytes(raw)
    finally:
        os.close(descriptor)


def _exact_string(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if type(value) is not str:
        raise ValueError("invalid retained field")
    return value


def _seal_identity(seal: dict[str, object]) -> str:
    keys = (
        "contract_version",
        "code_commit",
        "knowledge_cutoff",
        "requested_from",
        "requested_to",
        "universe_snapshot_sha256",
        "schedule_digests_sha256",
        "selections",
    )
    return _sha(_canonical({key: seal.get(key) for key in keys}).rstrip(b"\n"))


def _validate_seal_header(seal: dict[str, object]) -> list[object]:
    selections = seal.get("selections")
    schedules = seal.get("schedule_digests_sha256")
    source = seal.get("source_evidence")
    if (
        type(selections) is not list
        or type(schedules) is not list
        or type(source) is not dict
        or seal.get("contract_version") != "retained-nifty50-evidence-seal-v1"
        or seal.get("classification") != "EXPLORATORY_DEVELOPMENT_EVIDENCE_ONLY"
        or seal.get("status") != "SEALED_PROVIDER_FREE_WITH_DECLARED_CATALOG_LIMITATION"
        or seal.get("provider_attempt_count") != 0
        or seal.get("stock_count") != 50
        or seal.get("partition_count") != 100
        or seal.get("requested_from") != "2026-07-01"
        or seal.get("requested_to") != "2026-08-12"
        or seal.get("universe_snapshot_sha256") != _RETAINED_UNIVERSE_SHA256
        or seal.get("dataset_identity_sha256") != _RETAINED_DATASET_IDENTITY_SHA256
        or seal.get("dataset_identity_sha256") != _seal_identity(seal)
        or schedules
        != [_RETAINED_JULY_SCHEDULE_SHA256, _RETAINED_AUGUST_SCHEDULE_SHA256]
        or cast(dict[str, object], source).get("bounded_coverage_report_sha256")
        != _RETAINED_COVERAGE_SHA256
        or len(cast(list[object], selections)) != 100
    ):
        raise ValueError("invalid retained seal")
    return cast(list[object], selections)


def _selection_accounting(
    selections: list[object], identities: tuple[tuple[str, str], ...]
) -> tuple[dict[str, tuple[str, str]], tuple[dict[str, object], ...]]:
    expected = dict(identities)
    selected: dict[tuple[str, str], dict[str, object]] = {}
    for raw_item in selections:
        if type(raw_item) is not dict:
            raise ValueError("invalid selection")
        item = cast(dict[str, object], raw_item)
        isin = _exact_string(item, "isin")
        symbol = _exact_string(item, "symbol")
        month = _exact_string(item, "month")
        checksum = _exact_string(item, "checksum_sha256")
        schedule = _exact_string(item, "schedule_digest_sha256")
        expected_schedule = {
            "2026-07": _RETAINED_JULY_SCHEDULE_SHA256,
            "2026-08": _RETAINED_AUGUST_SCHEDULE_SHA256,
        }.get(month)
        key = (isin, month)
        if (
            expected.get(isin) != symbol
            or expected_schedule is None
            or schedule != expected_schedule
            or not _valid_digest(checksum)
            or key in selected
            or item.get("adjustment_state") != "raw"
            or item.get("row_count") not in (3000, 8625)
        ):
            raise ValueError("invalid selection accounting")
        selected[key] = item
    required = {(isin, month) for isin in expected for month in ("2026-07", "2026-08")}
    if set(selected) != required:
        raise ValueError("incomplete selection accounting")
    by_symbol = {
        expected[isin]: (
            _exact_string(selected[(isin, "2026-07")], "checksum_sha256"),
            _exact_string(selected[(isin, "2026-08")], "checksum_sha256"),
        )
        for isin in expected
    }
    accounting: tuple[dict[str, object], ...] = tuple(
        {
            "candle_object_sha256": list(by_symbol[symbol]),
            "isin": isin,
            "months": ["2026-07", "2026-08"],
            "symbol": symbol,
        }
        for isin, symbol in identities
    )
    return by_symbol, accounting


def _validate_coverage(  # noqa: C901
    coverage: dict[str, object],
    identities: tuple[tuple[str, str], ...],
    by_symbol: dict[str, tuple[str, str]],
) -> None:
    results = coverage.get("results")
    expected_symbols = [symbol for _, symbol in identities]
    if (
        type(results) is not list
        or coverage.get("command") != "coverage"
        or coverage.get("contract_version") != "v1"
        or coverage.get("scope") != "nifty50"
        or coverage.get("status") != "PARTIAL"
        or coverage.get("provider_attempt_count") != 0
        or coverage.get("worker_count") != 1
        or coverage.get("universe_snapshot_sha256") != _RETAINED_UNIVERSE_SHA256
        or len(cast(list[object], results)) != 50
    ):
        raise ValueError("invalid coverage manifest")
    observed_symbols: list[str] = []
    for raw_result in cast(list[object], results):
        if type(raw_result) is not dict:
            raise ValueError("invalid coverage result")
        result = cast(dict[str, object], raw_result)
        symbol = _exact_string(result, "symbol")
        report = result.get("report")
        if type(report) is not dict:
            raise ValueError("invalid coverage report")
        report_value = cast(dict[str, object], report)
        payload = report_value.get("payload")
        if payload is None:
            if (
                symbol != "M&M"
                or report_value.get("status") != "FAILED"
                or report_value.get("provider_attempt_count") != 0
            ):
                raise ValueError("invalid coverage payload")
            observed_symbols.append(symbol)
            continue
        if type(payload) is not dict:
            raise ValueError("invalid coverage payload")
        payload_value = cast(dict[str, object], payload)
        request = payload_value.get("request")
        months = payload_value.get("months")
        if (
            type(request) is not dict
            or type(months) is not list
            or len(cast(list[object], months)) != 2
        ):
            raise ValueError("invalid coverage payload")
        month_checksums: list[str] = []
        month_names: list[str] = []
        for raw_month in cast(list[object], months):
            if type(raw_month) is not dict:
                raise ValueError("invalid coverage month")
            month = cast(dict[str, object], raw_month)
            month_names.append(_exact_string(month, "month"))
            month_checksums.append(_exact_string(month, "checksum_sha256"))
        if (
            report_value.get("provider_attempt_count") != 0
            or report_value.get("status") != "SUCCEEDED"
            or cast(dict[str, object], request).get("symbol") != symbol
            or cast(dict[str, object], request).get("segment") != "NSE_EQ"
            or month_names != ["2026-07", "2026-08"]
            or tuple(month_checksums) != by_symbol.get(symbol)
            or payload_value.get("planned_count") != 2
        ):
            raise ValueError("coverage identity mismatch")
        observed_symbols.append(symbol)
    if observed_symbols != expected_symbols or len(set(observed_symbols)) != 50:
        raise ValueError("coverage symbol mismatch")


def _accounting_value(
    accounting: tuple[Mapping[str, object], ...],
) -> list[dict[str, object]]:
    return [
        {
            "candle_object_sha256": list(
                cast(tuple[str, str], row["candle_object_sha256"])
            ),
            "isin": row["isin"],
            "months": list(cast(tuple[str, str], row["months"])),
            "symbol": row["symbol"],
        }
        for row in accounting
    ]


def _validate_accounting(accounting: object) -> tuple[Mapping[str, object], ...]:
    if type(accounting) is not tuple:
        raise ValueError("invalid retained accounting")
    unknown_rows = cast(tuple[object, ...], accounting)
    if len(unknown_rows) != 50:
        raise ValueError("invalid retained accounting")
    rows: list[Mapping[str, object]] = []
    observed: list[tuple[str, str]] = []
    exact_keys = {"candle_object_sha256", "isin", "months", "symbol"}
    for unknown_row in unknown_rows:
        if type(unknown_row) is not MappingProxyType:
            raise ValueError("invalid retained accounting row")
        row = cast(Mapping[str, object], unknown_row)
        if set(row) != exact_keys:
            raise ValueError("invalid retained accounting row")
        hashes_value = row["candle_object_sha256"]
        months = row["months"]
        isin = row["isin"]
        symbol = row["symbol"]
        if type(hashes_value) is not tuple:
            raise ValueError("invalid retained accounting row")
        hashes = cast(tuple[object, ...], hashes_value)
        if (
            len(hashes) != 2
            or not all(_valid_digest(item) for item in hashes)
            or months != ("2026-07", "2026-08")
            or type(isin) is not str
            or type(symbol) is not str
        ):
            raise ValueError("invalid retained accounting row")
        rows.append(row)
        observed.append((isin, symbol))
    if tuple(observed) != _RETAINED_EQUITY_IDENTITIES or len(set(observed)) != 50:
        raise ValueError("retained universe mismatch")
    if _sha(_canonical(_accounting_value(tuple(rows)))) != _RETAINED_ACCOUNTING_SHA256:
        raise ValueError("retained accounting mismatch")
    return tuple(rows)


def _manifest_value(
    value: EvidenceReadinessPrerequisiteManifestV1, *, include_identity: bool
) -> dict[str, object]:
    result: dict[str, object] = {
        "admission_state": value.admission_state,
        "authorization_state": value.authorization_state,
        "authority_bindings": {
            "application_contract_version": PREREQUISITE_MANIFEST_CONTRACT_VERSION_V1,
            "plan11_contract_repository_bytes": {
                "sha256": READINESS_CONTRACT_IDENTITY_SHA256_V1,
                "version": READINESS_CONTRACT_VERSION_V1,
            },
            "plan11_source_policy_repository_bytes": {
                "sha256": SOURCE_POLICY_IDENTITY_SHA256_V1,
                "version": SOURCE_POLICY_VERSION_V1,
            },
            "retained_dataset_identity_sha256": _RETAINED_DATASET_IDENTITY_SHA256,
            "retained_objects": [
                {"role": role, "sha256": digest} for role, digest in _RETAINED_OBJECTS
            ],
        },
        "operator_claims": {
            "classification": "UNVERIFIED_NOT_AUTHORITY",
            "code_version_label": value.code_version_label,
            "configuration_record_state": "ABSENT_UNVERIFIED_PREREQUISITE",
            "validation_policy_record_state": "ABSENT_UNVERIFIED_PREREQUISITE",
        },
        "corporate_action_blockers": list(_CORPORATE_ACTION_BLOCKERS),
        "evaluator_state": value.evaluator_state,
        "execution_state": value.execution_state,
        "prerequisite_state": value.prerequisite_state,
        "prerequisites": [
            {
                "code": item[0],
                "required_evidence": list(item[1]),
                "state": item[2],
            }
            for item in _PREREQUISITES
        ],
        "provider_classification": "RETAINED_PROVIDER_FREE_EVIDENCE_ONLY",
        "provider_attempts": 0,
        "network_attempts": 0,
        "storage_write_attempts": 0,
        "readiness_state": value.readiness_state,
        "report_row_count": 0,
        "report_rows": [],
        "request_descriptor_count": 0,
        "request_descriptors": [],
        "retained_equity_accounting": _accounting_value(
            value.retained_equity_accounting
        ),
        "retained_equity_count": 50,
        "role_boundaries_and_nonclaims": list(_ROLE_BOUNDARIES),
        "sprint4_result": {
            "classification": "INSUFFICIENT_EVIDENCE",
            "eligible_pairs": 0,
            "insufficient_pairs": 1550,
            "provider_attempts": 0,
            "requested_pairs": 1550,
            "result_is_immutable": True,
        },
    }
    if include_identity:
        result["manifest_identity_sha256"] = value.manifest_identity_sha256
    return result


@dataclass(frozen=True, slots=True)
class PrerequisiteManifestRequestV1:
    contract_path: Path
    sprint4_seal_path: Path
    universe_path: Path
    july_schedule_path: Path
    august_schedule_path: Path
    coverage_manifest_path: Path
    code_version_label: str

    def __post_init__(self) -> None:
        paths = (
            self.contract_path,
            self.sprint4_seal_path,
            self.universe_path,
            self.july_schedule_path,
            self.august_schedule_path,
            self.coverage_manifest_path,
        )
        if (
            len(set(paths)) != 6
            or type(self.code_version_label) is not str
            or _CODE_IDENTITY.fullmatch(self.code_version_label) is None
        ):
            raise ValueError("invalid prerequisite manifest request")


_SERVICE_CONSTRUCTION_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False)
class EvidenceReadinessPrerequisiteManifestV1:
    code_version_label: str
    retained_equity_accounting: tuple[Mapping[str, object], ...]
    prerequisite_state: str
    admission_state: str
    evaluator_state: str
    readiness_state: str
    authorization_state: str
    execution_state: str
    _construction_token: object

    def __init__(
        self,
        *,
        code_version_label: str,
        retained_equity_accounting: tuple[Mapping[str, object], ...],
        _construction_token: object,
    ) -> None:
        if _construction_token is not _SERVICE_CONSTRUCTION_TOKEN:
            raise TypeError("service-only manifest construction")
        frozen_rows = tuple(
            MappingProxyType(
                {
                    "candle_object_sha256": tuple(
                        cast(list[str], row["candle_object_sha256"])
                    ),
                    "isin": row["isin"],
                    "months": tuple(cast(list[str], row["months"])),
                    "symbol": row["symbol"],
                }
            )
            for row in retained_equity_accounting
        )
        object.__setattr__(self, "code_version_label", code_version_label)
        object.__setattr__(self, "retained_equity_accounting", frozen_rows)
        object.__setattr__(self, "prerequisite_state", "DECLARATION_RECEIPT_MISSING")
        object.__setattr__(self, "admission_state", "NOT_EVALUATED")
        object.__setattr__(self, "evaluator_state", "NOT_EVALUATED")
        object.__setattr__(self, "readiness_state", "NOT_ASSESSED")
        object.__setattr__(self, "authorization_state", "NOT_ASSESSED")
        object.__setattr__(self, "execution_state", "NOT_REQUESTED")
        object.__setattr__(self, "_construction_token", _construction_token)
        self._validate()

    def _validate(self) -> None:
        if (
            self._construction_token is not _SERVICE_CONSTRUCTION_TOKEN
            or type(self.code_version_label) is not str
            or _CODE_IDENTITY.fullmatch(self.code_version_label) is None
            or self.prerequisite_state != "DECLARATION_RECEIPT_MISSING"
            or self.admission_state != "NOT_EVALUATED"
            or self.evaluator_state != "NOT_EVALUATED"
            or self.readiness_state != "NOT_ASSESSED"
            or self.authorization_state != "NOT_ASSESSED"
            or self.execution_state != "NOT_REQUESTED"
        ):
            raise ValueError("invalid prerequisite manifest")
        _validate_accounting(self.retained_equity_accounting)

    @property
    def manifest_identity_sha256(self) -> str:
        self._validate()
        return _sha(_canonical(_manifest_value(self, include_identity=False)))

    def canonical_json_bytes(self) -> bytes:
        self._validate()
        payload = _manifest_value(self, include_identity=True)
        if (
            payload["report_row_count"] != 0
            or payload["request_descriptor_count"] != 0
            or payload["provider_attempts"] != 0
            or payload["network_attempts"] != 0
            or payload["storage_write_attempts"] != 0
        ):
            raise ValueError("invalid prerequisite manifest")
        return _canonical(payload)


class PrerequisiteManifestServiceV1:
    """Validate exact retained objects and emit a sealed fail-closed manifest."""

    def run(
        self, request: PrerequisiteManifestRequestV1
    ) -> EvidenceReadinessPrerequisiteManifestV1:
        try:
            return self._run(request)
        except Exception:
            raise ValueError(
                "evidence readiness prerequisite manifest unavailable"
            ) from None

    def _run(
        self, request: PrerequisiteManifestRequestV1
    ) -> EvidenceReadinessPrerequisiteManifestV1:
        if type(request) is not PrerequisiteManifestRequestV1:
            raise ValueError("invalid request")
        contract_raw = _bounded_regular_file(request.contract_path, _MAX_SEAL_BYTES)
        seal_raw = _bounded_regular_file(request.sprint4_seal_path, _MAX_SEAL_BYTES)
        universe_raw = _bounded_regular_file(request.universe_path, _MAX_UNIVERSE_BYTES)
        july_raw = _bounded_regular_file(
            request.july_schedule_path, _MAX_SCHEDULE_BYTES
        )
        august_raw = _bounded_regular_file(
            request.august_schedule_path, _MAX_SCHEDULE_BYTES
        )
        coverage_raw = _bounded_regular_file(
            request.coverage_manifest_path, _MAX_COVERAGE_BYTES
        )
        supplied = (
            _sha(contract_raw),
            _sha(seal_raw),
            _sha(universe_raw),
            _sha(july_raw),
            _sha(august_raw),
            _sha(coverage_raw),
        )
        expected = (
            _PLAN11_CONTRACT_SHA256,
            _RETAINED_SEAL_SHA256,
            _RETAINED_UNIVERSE_SHA256,
            _RETAINED_JULY_SCHEDULE_SHA256,
            _RETAINED_AUGUST_SCHEDULE_SHA256,
            _RETAINED_COVERAGE_SHA256,
        )
        if supplied != expected:
            raise ValueError("retained digest mismatch")
        seal = _strict_json(seal_raw, sorted_keys=True)
        _strict_json(universe_raw, sorted_keys=False)
        _strict_json(july_raw, sorted_keys=False)
        _strict_json(august_raw, sorted_keys=False)
        coverage = _strict_json(coverage_raw, sorted_keys=True)
        universe = Nifty50UniverseSnapshotV1.from_canonical_json_bytes(universe_raw)
        july = parse_canonical_schedule_bytes(july_raw)
        august = parse_canonical_schedule_bytes(august_raw)
        if (
            universe.canonical_json_bytes() != universe_raw
            or canonical_schedule_bytes(july) != july_raw
            or canonical_schedule_bytes(august) != august_raw
            or july.covered_from.isoformat() != "2026-07-01"
            or july.covered_to.isoformat() != "2026-07-31"
            or july.source != "nse-authoritative-calendar"
            or august.covered_from.isoformat() != "2026-08-01"
            or august.covered_to.isoformat() != "2026-08-12"
            or august.source != "upstox-market-timings"
            or len(july.sessions) + len(august.sessions) != 31
        ):
            raise ValueError("retained evidence semantics mismatch")
        identities = tuple((item.isin, item.symbol) for item in universe.constituents)
        if len(identities) != 50 or len(set(identities)) != 50:
            raise ValueError("invalid universe accounting")
        selections = _validate_seal_header(seal)
        by_symbol, accounting = _selection_accounting(selections, identities)
        _validate_coverage(coverage, identities, by_symbol)
        return EvidenceReadinessPrerequisiteManifestV1(
            code_version_label=request.code_version_label,
            retained_equity_accounting=accounting,
            _construction_token=_SERVICE_CONSTRUCTION_TOKEN,
        )


EvidenceReadinessPrerequisiteRequestV1 = PrerequisiteManifestRequestV1
EvidenceReadinessPrerequisiteServiceV1 = PrerequisiteManifestServiceV1

__all__ = [
    "PREREQUISITE_MANIFEST_CONTRACT_VERSION_V1",
    "READINESS_CONTRACT_IDENTITY_SHA256_V1",
    "READINESS_CONTRACT_VERSION_V1",
    "SOURCE_POLICY_IDENTITY_SHA256_V1",
    "SOURCE_POLICY_VERSION_V1",
    "EvidenceReadinessPrerequisiteManifestV1",
    "EvidenceReadinessPrerequisiteRequestV1",
    "EvidenceReadinessPrerequisiteServiceV1",
    "PrerequisiteManifestRequestV1",
    "PrerequisiteManifestServiceV1",
]
