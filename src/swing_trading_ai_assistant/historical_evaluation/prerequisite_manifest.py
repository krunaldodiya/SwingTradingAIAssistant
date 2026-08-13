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
from dataclasses import dataclass
from pathlib import Path
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
READINESS_CONTRACT_IDENTITY_SHA256_V1: Final = hashlib.sha256(
    READINESS_CONTRACT_VERSION_V1.encode("ascii")
).hexdigest()
SOURCE_POLICY_IDENTITY_SHA256_V1: Final = hashlib.sha256(
    SOURCE_POLICY_VERSION_V1.encode("ascii")
).hexdigest()

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
    {
        "code": "GENUINE_DECLARATION_RECEIPT",
        "required_evidence": (
            "DECLARED_AT",
            "RETAINED_AT",
            "TRUSTED_CLOCK_IDENTITY_SHA256",
            "RECEIPT_IDENTITY_SHA256",
        ),
        "state": "MISSING",
    },
    {
        "code": "MEMBERSHIP_PUBLICATION_RETRIEVAL_PROOF_TERMS",
        "required_evidence": (
            "AUTHORITATIVE_PUBLICATION_BYTES",
            "PUBLIC_AVAILABILITY_PROOF",
            "RETRIEVAL_RECEIPT",
            "REVISION_LINEAGE",
            "TERMS_LICENCE_REVIEW",
        ),
        "state": "MISSING",
    },
    {
        "code": "SECTOR_PUBLICATION_RETRIEVAL_PROOF_TERMS",
        "required_evidence": (
            "AUTHORITATIVE_CLASSIFICATION_BYTES",
            "PUBLIC_AVAILABILITY_PROOF",
            "RETRIEVAL_RECEIPT",
            "REVISION_LINEAGE",
            "TERMS_LICENCE_REVIEW",
        ),
        "state": "MISSING",
    },
    {
        "code": "SCHEDULE_PUBLICATION_RETRIEVAL_PROOF_TERMS",
        "required_evidence": (
            "NSE_CAPITAL_MARKET_SOURCE_BYTES",
            "PUBLIC_AVAILABILITY_PROOF",
            "RETRIEVAL_RECEIPT",
            "REVISION_OVERLAYS",
            "TERMS_LICENCE_REVIEW",
        ),
        "state": "MISSING",
    },
    {
        "code": "LATER_APPROVED_EVIDENCE_CAPABILITIES",
        "required_evidence": (
            "MEMBERSHIP_CAPABILITY_APPROVAL",
            "SECTOR_CAPABILITY_APPROVAL",
            "SCHEDULE_CAPABILITY_APPROVAL",
            "CORPORATE_ACTION_CAPABILITY_APPROVAL",
            "ANCHOR_SESSION_CAPABILITY_APPROVAL",
        ),
        "state": "NOT_APPROVED",
    },
    {
        "code": "SEPARATE_EVIDENCE_EXECUTION_AUTHORIZATION",
        "required_evidence": (
            "OWNER_DECISION_IDENTITY",
            "EXACT_MANIFEST_SCOPE",
            "BOUNDED_ATTEMPTS_AND_BYTES",
            "EXPIRY",
            "TRUSTED_VALIDATION_RECEIPT",
        ),
        "state": "NOT_PRESENT",
    },
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
    """Read a bounded regular file without following the final path symlink."""
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError("no-follow unavailable")
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0) | nofollow
    descriptor = os.open(path, flags)
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


def _manifest_value(
    value: EvidenceReadinessPrerequisiteManifestV1, *, include_identity: bool
) -> dict[str, object]:
    result: dict[str, object] = {
        "admission_state": value.admission_state,
        "authorization_state": value.authorization_state,
        "bindings": {
            "application_contract_version": PREREQUISITE_MANIFEST_CONTRACT_VERSION_V1,
            "code_identity": value.code_identity,
            "configuration_sha256": value.configuration_sha256,
            "readiness_contract_identity_sha256": READINESS_CONTRACT_IDENTITY_SHA256_V1,
            "readiness_contract_version": READINESS_CONTRACT_VERSION_V1,
            "retained_dataset_identity_sha256": _RETAINED_DATASET_IDENTITY_SHA256,
            "retained_objects": [
                {"role": role, "sha256": digest} for role, digest in _RETAINED_OBJECTS
            ],
            "source_policy_identity_sha256": SOURCE_POLICY_IDENTITY_SHA256_V1,
            "source_policy_version": SOURCE_POLICY_VERSION_V1,
            "validation_policy_sha256": value.validation_policy_sha256,
        },
        "corporate_action_blockers": list(_CORPORATE_ACTION_BLOCKERS),
        "evaluator_state": value.evaluator_state,
        "execution_state": value.execution_state,
        "prerequisite_state": value.prerequisite_state,
        "prerequisites": [
            {
                "code": item["code"],
                "required_evidence": list(
                    cast(tuple[str, ...], item["required_evidence"])
                ),
                "state": item["state"],
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
        "retained_equity_accounting": list(value.retained_equity_accounting),
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
    sprint4_seal_path: Path
    universe_path: Path
    july_schedule_path: Path
    august_schedule_path: Path
    coverage_manifest_path: Path
    code_identity: str
    configuration_sha256: str
    validation_policy_sha256: str

    def __post_init__(self) -> None:
        paths = (
            self.sprint4_seal_path,
            self.universe_path,
            self.july_schedule_path,
            self.august_schedule_path,
            self.coverage_manifest_path,
        )
        if (
            len(set(paths)) != 5
            or type(self.code_identity) is not str
            or _CODE_IDENTITY.fullmatch(self.code_identity) is None
            or not _valid_digest(self.configuration_sha256)
            or not _valid_digest(self.validation_policy_sha256)
        ):
            raise ValueError("invalid prerequisite manifest request")


@dataclass(frozen=True, slots=True)
class EvidenceReadinessPrerequisiteManifestV1:
    code_identity: str
    configuration_sha256: str
    validation_policy_sha256: str
    retained_equity_accounting: tuple[dict[str, object], ...]
    prerequisite_state: str = "DECLARATION_RECEIPT_MISSING"
    admission_state: str = "NOT_EVALUATED"
    evaluator_state: str = "NOT_EVALUATED"
    readiness_state: str = "NOT_ASSESSED"
    authorization_state: str = "NOT_ASSESSED"
    execution_state: str = "NOT_REQUESTED"

    def __post_init__(self) -> None:
        if (
            _CODE_IDENTITY.fullmatch(self.code_identity) is None
            or not _valid_digest(self.configuration_sha256)
            or not _valid_digest(self.validation_policy_sha256)
            or type(self.retained_equity_accounting) is not tuple
            or len(self.retained_equity_accounting) != 50
            or self.prerequisite_state != "DECLARATION_RECEIPT_MISSING"
            or self.admission_state != "NOT_EVALUATED"
            or self.evaluator_state != "NOT_EVALUATED"
            or self.readiness_state != "NOT_ASSESSED"
            or self.authorization_state != "NOT_ASSESSED"
            or self.execution_state != "NOT_REQUESTED"
        ):
            raise ValueError("invalid prerequisite manifest")
        payload = _manifest_value(self, include_identity=False)
        if (
            payload["report_row_count"] != 0
            or payload["request_descriptor_count"] != 0
            or payload["provider_attempts"] != 0
        ):
            raise ValueError("invalid prerequisite manifest")

    @property
    def manifest_identity_sha256(self) -> str:
        return _sha(_canonical(_manifest_value(self, include_identity=False)))

    def canonical_json_bytes(self) -> bytes:
        return _canonical(_manifest_value(self, include_identity=True))


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
            _sha(seal_raw),
            _sha(universe_raw),
            _sha(july_raw),
            _sha(august_raw),
            _sha(coverage_raw),
        )
        expected = (
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
            code_identity=request.code_identity,
            configuration_sha256=request.configuration_sha256,
            validation_policy_sha256=request.validation_policy_sha256,
            retained_equity_accounting=accounting,
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
