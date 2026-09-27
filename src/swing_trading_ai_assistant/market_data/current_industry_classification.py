"""Owner-private current supplied-cohort Industry classification V1."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import importlib
import io
import json
import os
import re
import stat
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Final, Literal, Protocol, cast
from uuid import uuid4

from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

CONTRACT_VERSION: Final = "current-supplied-cohort-industry-classification@v1"
_SOURCE_URL: Final = (
    "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv"
)
_LEGACY_SOURCE_URL: Final = (
    "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"
)
_HEADER: Final = ("Company Name", "Industry", "Symbol", "Series", "ISIN Code")
_MAX_ARTIFACT_BYTES: Final = 1_048_576
_MAX_FIELD_CHARS: Final = 512
_IST: Final = timezone(timedelta(hours=5, minutes=30))
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_NSE_SYMBOL: Final = re.compile(r"[A-Z0-9](?:[A-Z0-9.&_-]{0,30}[A-Z0-9])?\Z")
_ISIN: Final = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]\Z")
_ARCHIVE_DIRECTORY: Final = ".current-industry-classification-v1"
_RETENTION_RECEIPT_VERSION: Final = "retained-current-industry-receipt@v1"
_COMPLETION_MARKER_VERSION: Final = "retained-current-industry-completion@v1"
_MAX_RETENTION_RECEIPT_BYTES: Final = 262_144
_MAX_COMPLETION_MARKER_BYTES: Final = 4_096
_RETENTION_COMPLETION_SAFETY_MARGIN: Final = timedelta(seconds=30)
_RUNTIME_MANIFEST_MODULE: Final = "swing_trading_ai_assistant.market_data.current_industry_classification_runtime_identity_manifest"
_RUNTIME_MANIFEST: Final = "src/swing_trading_ai_assistant/market_data/current_industry_classification_runtime_identity_manifest.py"
_RUNTIME_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/current_industry_classification.py",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
    "src/swing_trading_ai_assistant/market_data/storage_root_lease.py",
)
_REASON_ORDER: Final = (
    "CLASSIFICATION_ARTIFACT_MISSING",
    "CLASSIFICATION_ARTIFACT_MALFORMED",
    "CLASSIFICATION_SOURCE_UNSUPPORTED",
    "CLASSIFICATION_TIER_UNSUPPORTED",
    "CLASSIFICATION_MEMBER_UNSUPPORTED",
    "CLASSIFICATION_AMBIGUOUS",
    "CLASSIFICATION_CONFLICTING",
    "COHORT_BINDING_MISMATCH",
    "MEMBER_IDENTITY_MISMATCH",
    "CLASSIFICATION_FUTURE_KNOWN",
    "CLASSIFICATION_SESSION_STALE",
    "CLASSIFICATION_ARCHIVE_FAILED",
)
_PARSED_SEAL: Final = object()
_SNAPSHOT_SEAL: Final = object()
_RETAINED_SEAL: Final = object()
_ARCHIVE_RETAINED_SEAL: Final = object()
_ARCHIVE_LOCK: Final = Lock()


class CurrentIndustryRetentionClockErrorV1(RuntimeError):
    """Trusted retention time cannot precede a just-observed source."""

    def __init__(self) -> None:
        super().__init__("classification retention clock reversed")


class CurrentIndustryRetentionTimeErrorV1(RuntimeError):
    """The exact retained knowledge cannot precede the incoming observation."""

    code = "CLASSIFICATION_OBSERVATION_AFTER_RETENTION"

    def __init__(self) -> None:
        super().__init__("classification observation after retention")


class _AmbiguousArtifactIdentity(ValueError):
    pass


class _ConflictingArtifactIdentity(ValueError):
    pass


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )


def _identity(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


CLASSIFICATION_SCHEMA_IDENTITY_SHA256: Final = _identity(
    {
        "canonicalization": "json-utf8-sort-keys-compact-newline",
        "contract_version": CONTRACT_VERSION,
        "fixed_header": list(_HEADER),
        "fixed_source": {
            "acquisition_methods": [
                "OPERATOR_ACQUIRED",
                "BOUNDED_OFFICIAL_FETCH",
            ],
            "authority": "NSE_INDICES",
            "domain": "nsearchives.nseindia.com",
            "tier": "INDUSTRY",
            "url": _SOURCE_URL,
        },
        "grammars": {
            "formula_prefixes_rejected": ["=", "+", "-", "@"],
            "isin": _ISIN.pattern,
            "symbol": _NSE_SYMBOL.pattern,
            "unicode_rejected_categories": ["Cc", "Cf", "Zl", "Zp"],
        },
        "privacy": {
            "industry_labels_reject": [
                "case-insensitive-full-isin",
                "case-insensitive-complete-symbol-token",
                "source-company-name-boundary-free-unicode-containment",
            ],
            "source_company_name_normalization": (
                'unicodedata.normalize("NFKC", value.casefold())'
            ),
            "source_company_name_rule": (
                "normalized_company_name in normalized_industry"
            ),
        },
        "limits": {
            "artifact_bytes": _MAX_ARTIFACT_BYTES,
            "field_characters": _MAX_FIELD_CHARS,
            "records": 100,
            "retention_receipt_bytes": _MAX_RETENTION_RECEIPT_BYTES,
        },
        "retention": {
            "completion_marker_version": _COMPLETION_MARKER_VERSION,
            "completion_safety_margin_seconds": int(
                _RETENTION_COMPLETION_SAFETY_MARGIN.total_seconds()
            ),
            "receipt_version": _RETENTION_RECEIPT_VERSION,
        },
        "null_publisher_fields": [
            "publisher_published_at",
            "publisher_effective_from",
            "publisher_effective_through",
            "publisher_revision",
        ],
        "ordering": {
            "parsed_rows": "isin-ascending",
            "snapshot_rows": "isin-ascending",
        },
        "seals_and_identity_rules": {
            "parsed": "sealed-private-rows",
            "retained": "archive-minted-private-read-capability-and-canonical-identity",
            "snapshot": "sealed-canonical-identity",
        },
    }
)
LEGACY_CLASSIFICATION_SCHEMA_IDENTITY_SHA256: Final = (
    "29b292b6d8f6f048ca4a86ef3b5185b6be5a903770fd8f2be5818c76932b2552"
)
CURRENT_INDUSTRY_LICENCE_POLICY_IDENTITY_SHA256: Final = hashlib.sha256(
    b"nse-indices-bounded-official-fetch-owner-private-v1"
).hexdigest()
_CLASSIFICATION_SCHEMA_IDENTITIES: Final = frozenset(
    {
        LEGACY_CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
        CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
    }
)


def _exact_classification_source_case(
    schema_identity: object,
    source_url: object,
    source_authority: object,
    source_domain: object,
    acquisition_method: object,
    licence_policy_identity: object,
) -> bool:
    legacy = (
        schema_identity == LEGACY_CLASSIFICATION_SCHEMA_IDENTITY_SHA256
        and source_url == _LEGACY_SOURCE_URL
        and source_authority == "NSE_INDICES"
        and source_domain == "www.niftyindices.com"
        and acquisition_method == "OPERATOR_ACQUIRED"
        and _valid_digest(licence_policy_identity)
    )
    current = (
        schema_identity == CLASSIFICATION_SCHEMA_IDENTITY_SHA256
        and source_url == _SOURCE_URL
        and source_authority == "NSE_INDICES"
        and source_domain == "nsearchives.nseindia.com"
        and acquisition_method == "BOUNDED_OFFICIAL_FETCH"
        and licence_policy_identity == CURRENT_INDUSTRY_LICENCE_POLICY_IDENTITY_SHA256
    )
    return legacy or current


def _instant(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _failure_state(
    reasons: tuple[str, ...],
) -> Literal["MALFORMED_EVIDENCE", "UNSUPPORTED_CAPABILITY", "INSUFFICIENT_EVIDENCE"]:
    if any(
        reason
        in {
            "CLASSIFICATION_ARTIFACT_MALFORMED",
            "CLASSIFICATION_AMBIGUOUS",
            "CLASSIFICATION_CONFLICTING",
            "COHORT_BINDING_MISMATCH",
            "MEMBER_IDENTITY_MISMATCH",
        }
        for reason in reasons
    ):
        return "MALFORMED_EVIDENCE"
    if any(
        reason
        in {
            "CLASSIFICATION_SOURCE_UNSUPPORTED",
            "CLASSIFICATION_TIER_UNSUPPORTED",
            "CLASSIFICATION_MEMBER_UNSUPPORTED",
        }
        for reason in reasons
    ):
        return "UNSUPPORTED_CAPABILITY"
    return "INSUFFICIENT_EVIDENCE"


def _ordered(reasons: object) -> tuple[str, ...]:
    if type(reasons) is not tuple or not reasons:
        raise ValueError("classification reasons invalid")
    typed_reasons = cast(tuple[object, ...], reasons)
    if any(
        type(reason) is not str or reason not in _REASON_ORDER
        for reason in typed_reasons
    ):
        raise ValueError("classification reasons invalid")
    return tuple(reason for reason in _REASON_ORDER if reason in typed_reasons)


def _valid_digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _seal_is(value: object, expected: object) -> bool:
    return getattr(value, "_seal", None) is expected


def _runtime_root() -> Path:
    source = Path(__file__)
    root = source.parent.parent
    if not source.is_absolute() or root.name != "swing_trading_ai_assistant":
        raise ValueError("classification runtime identity invalid")
    return root


def _runtime_source_sha256(module_name: str, relative: str) -> str:
    try:
        return runtime_source_sha256(module_name, _runtime_root(), relative)
    except ValueError:
        raise ValueError("classification runtime identity invalid") from None


def current_industry_classification_runtime_code_identity_v1() -> str:
    try:
        manifest = importlib.import_module(_RUNTIME_MANIFEST_MODULE)
        raw_mapping = manifest.CURRENT_INDUSTRY_CLASSIFICATION_RUNTIME_SOURCE_DIGESTS_V1
    except (AttributeError, ImportError):
        raise ValueError("classification runtime identity invalid") from None
    if type(raw_mapping) is not dict:
        raise ValueError("classification runtime identity invalid")
    mapping = cast(dict[str, object], raw_mapping)
    modules = {
        _RUNTIME_SOURCES[0]: __name__,
        _RUNTIME_SOURCES[
            1
        ]: "swing_trading_ai_assistant.market_data.runtime_source_verifier",
        _RUNTIME_SOURCES[
            2
        ]: "swing_trading_ai_assistant.market_data.storage_root_lease",
    }
    if tuple(mapping) != _RUNTIME_SOURCES or any(
        not _valid_digest(digest)
        or _runtime_source_sha256(modules[path], path) != digest
        for path, digest in mapping.items()
    ):
        raise ValueError("classification runtime identity invalid")
    manifest_digest = _runtime_source_sha256(
        _RUNTIME_MANIFEST_MODULE, _RUNTIME_MANIFEST
    )
    composite = b"".join(
        path.encode() + b"\0" + cast(str, mapping[path]).encode() + b"\0"
        for path in _RUNTIME_SOURCES
    )
    return _sha(
        composite
        + _RUNTIME_MANIFEST.encode()
        + b"\0"
        + manifest_digest.encode()
        + b"\0"
    )


_CLASSIFICATION_RUNTIME_IDENTITY: Final = (
    current_industry_classification_runtime_code_identity_v1()
)


@dataclass(frozen=True, slots=True, init=False)
class CurrentIndustryClassificationInputV1:
    schema_identity_sha256: str
    source_url: str
    source_authority: str
    source_domain: str
    acquisition_method: str
    artifact_byte_count: int
    artifact_sha256: str
    artifact_revision: str
    classification_tier: str
    publisher_published_at: None
    publisher_effective_from: None
    publisher_effective_through: None
    publisher_revision: None
    licence_policy_identity_sha256: str
    input_identity_sha256: str

    def __init__(self, value: dict[str, object]) -> None:
        expected = {
            "contract_version",
            "schema_identity_sha256",
            "source_url",
            "source_authority",
            "source_domain",
            "acquisition_method",
            "artifact_byte_count",
            "artifact_sha256",
            "artifact_revision",
            "classification_tier",
            "publisher_published_at",
            "publisher_effective_from",
            "publisher_effective_through",
            "publisher_revision",
            "licence_policy_identity_sha256",
        }
        if (
            type(value) is not dict
            or set(value) != expected
            or value["contract_version"] != CONTRACT_VERSION
            or value["schema_identity_sha256"] not in _CLASSIFICATION_SCHEMA_IDENTITIES
        ):
            raise ValueError("classification input invalid")
        artifact_byte_count = value["artifact_byte_count"]
        if type(artifact_byte_count) is not int or artifact_byte_count < 0:
            raise ValueError("classification input invalid")
        if any(
            value[field] is not None
            for field in (
                "publisher_published_at",
                "publisher_effective_from",
                "publisher_effective_through",
                "publisher_revision",
            )
        ):
            raise ValueError("classification input invalid")
        string_fields = (
            "schema_identity_sha256",
            "source_url",
            "source_authority",
            "source_domain",
            "acquisition_method",
            "artifact_sha256",
            "artifact_revision",
            "classification_tier",
            "licence_policy_identity_sha256",
        )
        if (
            any(type(value[field]) is not str for field in string_fields)
            or not _valid_digest(value["artifact_sha256"])
            or not _valid_digest(value["licence_policy_identity_sha256"])
        ):
            raise ValueError("classification input invalid")
        for name in string_fields:
            object.__setattr__(self, name, value[name])
        object.__setattr__(self, "artifact_byte_count", artifact_byte_count)
        object.__setattr__(self, "publisher_published_at", None)
        object.__setattr__(self, "publisher_effective_from", None)
        object.__setattr__(self, "publisher_effective_through", None)
        object.__setattr__(self, "publisher_revision", None)
        object.__setattr__(self, "input_identity_sha256", _identity(self.value()))

    @classmethod
    def from_canonical_json_bytes(
        cls, raw: bytes
    ) -> CurrentIndustryClassificationInputV1:
        if type(raw) is not bytes or len(raw) > 16_384:
            raise ValueError("classification input invalid")
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            raise ValueError("classification input invalid") from None
        if _canonical(value) != raw:
            raise ValueError("classification input invalid")
        return cls(value)

    def value(self) -> dict[str, object]:
        return {
            "acquisition_method": self.acquisition_method,
            "artifact_byte_count": self.artifact_byte_count,
            "artifact_revision": self.artifact_revision,
            "artifact_sha256": self.artifact_sha256,
            "classification_tier": self.classification_tier,
            "contract_version": CONTRACT_VERSION,
            "schema_identity_sha256": self.schema_identity_sha256,
            "licence_policy_identity_sha256": self.licence_policy_identity_sha256,
            "publisher_effective_from": None,
            "publisher_effective_through": None,
            "publisher_published_at": None,
            "publisher_revision": None,
            "source_authority": self.source_authority,
            "source_domain": self.source_domain,
            "source_url": self.source_url,
        }

    def canonical_json_bytes(self) -> bytes:
        return _canonical(self.value())


@dataclass(frozen=True, slots=True, repr=False)
class CurrentIndustryCohortMemberV1:
    isin: str
    exchange: str
    effective_symbol: str

    def __post_init__(self) -> None:
        if (
            not _valid_isin(self.isin)
            or self.exchange not in {"NSE", "BSE"}
            or not _field(self.effective_symbol)
        ):
            raise ValueError("classification cohort member invalid")


@dataclass(frozen=True, slots=True, init=False, repr=False)
class _PrivateIndustryRow:
    isin: str
    industry: str
    symbol: str
    exchange: str
    effective_symbol: str
    _seal: object = field(repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("private industry row constructor unavailable")


@dataclass(frozen=True, slots=True, init=False, repr=False)
class ParsedCurrentIndustryArtifactV1:
    evidence_state: Literal["PARSED"]
    schema_identity_sha256: str
    source_url: str
    source_authority: str
    source_domain: str
    acquisition_method: str
    classification_tier: Literal["INDUSTRY"]
    artifact_byte_count: int
    artifact_sha256: str
    artifact_revision: str
    publisher_published_at: None
    publisher_effective_from: None
    publisher_effective_through: None
    publisher_revision: None
    input_identity_sha256: str
    private_rows: tuple[_PrivateIndustryRow, ...]
    _seal: object = field(repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("parsed classification constructor unavailable")


@dataclass(frozen=True, slots=True)
class CurrentIndustryClassificationFailureV1:
    evidence_state: Literal[
        "MALFORMED_EVIDENCE", "UNSUPPORTED_CAPABILITY", "INSUFFICIENT_EVIDENCE"
    ]
    reasons: tuple[str, ...]
    cohort_size: int | None = None

    def __post_init__(self) -> None:
        reasons = _ordered(self.reasons)
        if self.evidence_state != _failure_state(reasons) or (
            self.cohort_size is not None
            and (type(self.cohort_size) is not int or not 1 <= self.cohort_size <= 50)
        ):
            raise ValueError("classification failure invalid")
        object.__setattr__(self, "reasons", reasons)

    def canonical_json_bytes(self) -> bytes:
        return _canonical(
            {"evidence_state": self.evidence_state, "reasons": list(self.reasons)}
        )


@dataclass(frozen=True, slots=True, init=False, repr=False)
class PrivateCurrentIndustrySnapshotV1:
    evidence_state: Literal["PROJECTED"]
    schema_identity_sha256: str
    runtime_code_identity_sha256: str
    input_identity_sha256: str
    artifact_sha256: str
    artifact_revision: str
    cohort_identity_sha256: str
    cohort_size: int
    private_rows: tuple[_PrivateIndustryRow, ...]
    snapshot_identity_sha256: str
    _seal: object = field(repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("private snapshot constructor unavailable")

    def canonical_json_bytes(self) -> bytes:
        return _canonical(
            {
                "artifact_sha256": self.artifact_sha256,
                "artifact_revision": self.artifact_revision,
                "cohort_identity_sha256": self.cohort_identity_sha256,
                "cohort_size": self.cohort_size,
                "evidence_state": self.evidence_state,
                "input_identity_sha256": self.input_identity_sha256,
                "schema_identity_sha256": self.schema_identity_sha256,
                "private_rows": [
                    {
                        "industry": row.industry,
                        "isin": row.isin,
                        "symbol": row.symbol,
                        "exchange": row.exchange,
                        "effective_symbol": row.effective_symbol,
                    }
                    for row in self.private_rows
                ],
                "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
            }
        )


@dataclass(frozen=True, slots=True, init=False, repr=False)
class RetainedCurrentIndustrySnapshotV1:
    evidence_state: Literal["RETAINED"]
    schema_identity_sha256: str
    input_identity_sha256: str
    artifact_sha256: str
    artifact_revision: str
    snapshot_identity_sha256: str
    archive_identity_sha256: str
    archive_receipt_identity_sha256: str
    retained_identity_sha256: str
    snapshot_runtime_code_identity_sha256: str
    cohort_identity_sha256: str
    cohort_size: int
    known_at: datetime
    publisher_published_at: None
    publisher_effective_from: None
    publisher_effective_through: None
    publisher_revision: None
    _private_rows: tuple[_PrivateIndustryRow, ...]
    _archive_seal: object = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("retained classification constructor unavailable")

    def canonical_json_bytes(self, *, include_identity: bool = True) -> bytes:
        return _retained_canonical_json_bytes(self, include_identity=include_identity)

    @property
    def raw_artifact_sha256(self) -> str:
        """Expose only the content address of the retained private raw object."""
        return self.artifact_sha256


@dataclass(frozen=True, slots=True, repr=False)
class _RetainedCurrentIndustryCandidateV1:
    evidence_state: Literal["RETAINED"]
    schema_identity_sha256: str
    input_identity_sha256: str
    artifact_sha256: str
    artifact_revision: str
    snapshot_identity_sha256: str
    archive_identity_sha256: str
    archive_receipt_identity_sha256: str
    retained_identity_sha256: str
    snapshot_runtime_code_identity_sha256: str
    cohort_identity_sha256: str
    cohort_size: int
    known_at: datetime
    publisher_published_at: None
    publisher_effective_from: None
    publisher_effective_through: None
    publisher_revision: None
    _private_rows: tuple[_PrivateIndustryRow, ...]

    def canonical_json_bytes(self, *, include_identity: bool = True) -> bytes:
        return _retained_canonical_json_bytes(self, include_identity=include_identity)


def _retained_canonical_json_bytes(
    value: RetainedCurrentIndustrySnapshotV1 | _RetainedCurrentIndustryCandidateV1,
    *,
    include_identity: bool,
) -> bytes:
    result = {
        "archive_identity_sha256": value.archive_identity_sha256,
        "archive_receipt_identity_sha256": value.archive_receipt_identity_sha256,
        "artifact_revision": value.artifact_revision,
        "artifact_sha256": value.artifact_sha256,
        "cohort_identity_sha256": value.cohort_identity_sha256,
        "cohort_size": value.cohort_size,
        "evidence_state": value.evidence_state,
        "input_identity_sha256": value.input_identity_sha256,
        "schema_identity_sha256": value.schema_identity_sha256,
        "known_at": _instant(value.known_at),
        "publisher_effective_from": None,
        "publisher_effective_through": None,
        "publisher_published_at": None,
        "publisher_revision": None,
        "snapshot_identity_sha256": value.snapshot_identity_sha256,
        "snapshot_runtime_code_identity_sha256": (
            value.snapshot_runtime_code_identity_sha256
        ),
    }
    if include_identity:
        result["retained_identity_sha256"] = value.retained_identity_sha256
    return _canonical(result)


@dataclass(frozen=True, slots=True, repr=False)
class _IndustryArchiveBinding:
    root: Path
    root_identity: tuple[int, int]
    directory_identity: tuple[int, int]
    objects: tuple[tuple[str, bytes, os.stat_result], ...]


@dataclass(frozen=True, slots=True, init=False, repr=False)
class _ArchiveRetainedSeal:
    binding: _IndustryArchiveBinding
    archive_identity_sha256: str
    archive_receipt_identity_sha256: str
    retained_identity_sha256: str
    snapshot_identity_sha256: str
    _seal: object = field(repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("archive retained seal unavailable")


def _archive_minted_retained(value: object) -> bool:
    if type(value) is not RetainedCurrentIndustrySnapshotV1 or not _seal_is(
        value, _RETAINED_SEAL
    ):
        return False
    retained_seal = getattr(value, "_archive_seal", None)
    return (
        type(retained_seal) is _ArchiveRetainedSeal
        and _seal_is(retained_seal, _ARCHIVE_RETAINED_SEAL)
        and (
            retained_seal.archive_identity_sha256,
            retained_seal.archive_receipt_identity_sha256,
            retained_seal.retained_identity_sha256,
            retained_seal.snapshot_identity_sha256,
        )
        == (
            value.archive_identity_sha256,
            value.archive_receipt_identity_sha256,
            value.retained_identity_sha256,
            value.snapshot_identity_sha256,
        )
    )


def _private_row(
    isin: str,
    industry: str,
    symbol: str,
    exchange: str = "NSE",
    effective_symbol: str | None = None,
) -> _PrivateIndustryRow:
    row = object.__new__(_PrivateIndustryRow)
    for name, value in (
        ("isin", isin),
        ("industry", industry),
        ("symbol", symbol),
        ("exchange", exchange),
        ("effective_symbol", symbol if effective_symbol is None else effective_symbol),
    ):
        object.__setattr__(row, name, value)
    object.__setattr__(row, "_seal", _PARSED_SEAL)
    return row


def _parsed(**values: object) -> ParsedCurrentIndustryArtifactV1:
    result = object.__new__(ParsedCurrentIndustryArtifactV1)
    for name, value in values.items():
        object.__setattr__(result, name, value)
    object.__setattr__(result, "_seal", _PARSED_SEAL)
    return result


def _snapshot(**values: object) -> PrivateCurrentIndustrySnapshotV1:
    result = object.__new__(PrivateCurrentIndustrySnapshotV1)
    for name, value in values.items():
        object.__setattr__(result, name, value)
    object.__setattr__(result, "_seal", _SNAPSHOT_SEAL)
    return result


class CurrentIndustryArchivePortV1(Protocol):
    def archive_exact(
        self,
        input: CurrentIndustryClassificationInputV1,
        artifact: bytes,
        snapshot: PrivateCurrentIndustrySnapshotV1,
        lease: StorageRootLease,
    ) -> RetainedCurrentIndustrySnapshotV1 | CurrentIndustryClassificationFailureV1: ...


def _artifact_or_missing(artifact: object) -> bytes | None:
    if artifact is None or type(artifact) is bytes:
        return artifact
    raise TypeError("classification artifact invalid")


def parse_current_industry_artifact_v1(
    input: CurrentIndustryClassificationInputV1, artifact: bytes | None
) -> ParsedCurrentIndustryArtifactV1 | CurrentIndustryClassificationFailureV1:
    if type(input) is not CurrentIndustryClassificationInputV1:
        raise TypeError("classification input invalid")
    artifact = _artifact_or_missing(artifact)
    unsupported: list[str] = []
    if not _exact_classification_source_case(
        input.schema_identity_sha256,
        input.source_url,
        input.source_authority,
        input.source_domain,
        input.acquisition_method,
        input.licence_policy_identity_sha256,
    ):
        unsupported.append("CLASSIFICATION_SOURCE_UNSUPPORTED")
    if input.classification_tier != "INDUSTRY":
        unsupported.append("CLASSIFICATION_TIER_UNSUPPORTED")
    if unsupported:
        return _failure(tuple(unsupported))
    if artifact is None:
        return _failure(("CLASSIFICATION_ARTIFACT_MISSING",))
    if (
        type(artifact) is not bytes
        or len(artifact) > _MAX_ARTIFACT_BYTES
        or len(artifact) != input.artifact_byte_count
        or _sha(artifact) != input.artifact_sha256
        or input.artifact_revision != f"sha256:{input.artifact_sha256}"
    ):
        return _failure(("CLASSIFICATION_ARTIFACT_MALFORMED",))
    try:
        rows = _parse_rows(artifact)
    except _AmbiguousArtifactIdentity:
        return _failure(("CLASSIFICATION_AMBIGUOUS",))
    except _ConflictingArtifactIdentity:
        return _failure(("CLASSIFICATION_CONFLICTING",))
    except (csv.Error, UnicodeError, ValueError):
        return _failure(("CLASSIFICATION_ARTIFACT_MALFORMED",))
    return _parsed(
        evidence_state="PARSED",
        schema_identity_sha256=input.schema_identity_sha256,
        source_url=input.source_url,
        source_authority=input.source_authority,
        source_domain=input.source_domain,
        acquisition_method=input.acquisition_method,
        classification_tier="INDUSTRY",
        artifact_byte_count=input.artifact_byte_count,
        artifact_sha256=input.artifact_sha256,
        artifact_revision=input.artifact_revision,
        publisher_published_at=None,
        publisher_effective_from=None,
        publisher_effective_through=None,
        publisher_revision=None,
        input_identity_sha256=input.input_identity_sha256,
        private_rows=rows,
    )


def project_current_supplied_cohort_industry_v1(
    parsed: ParsedCurrentIndustryArtifactV1,
    cohort_identity_sha256: str,
    cohort_members: tuple[CurrentIndustryCohortMemberV1, ...],
) -> PrivateCurrentIndustrySnapshotV1 | CurrentIndustryClassificationFailureV1:
    if (
        type(parsed) is not ParsedCurrentIndustryArtifactV1
        or not _seal_is(parsed, _PARSED_SEAL)
        or not _valid_parsed(parsed)
        or not _valid_digest(cohort_identity_sha256)
        or type(cohort_members) is not tuple
        or not 1 <= len(cohort_members) <= 50
        or any(
            type(member) is not CurrentIndustryCohortMemberV1
            for member in cohort_members
        )
    ):
        raise ValueError("classification cohort invalid")
    if len({member.isin for member in cohort_members}) != len(cohort_members):
        raise ValueError("classification cohort invalid")
    if any(member.exchange != "NSE" for member in cohort_members):
        return _failure(("CLASSIFICATION_MEMBER_UNSUPPORTED",), len(cohort_members))
    source = {row.isin: row for row in parsed.private_rows}
    if any(member.isin not in source for member in cohort_members):
        return _failure(("CLASSIFICATION_MEMBER_UNSUPPORTED",), len(cohort_members))
    if any(
        source[member.isin].symbol != member.effective_symbol
        for member in cohort_members
    ):
        return _failure(("MEMBER_IDENTITY_MISMATCH",), len(cohort_members))
    private_rows = tuple(
        sorted(
            (
                _private_row(
                    member.isin,
                    source[member.isin].industry,
                    source[member.isin].symbol,
                    member.exchange,
                    member.effective_symbol,
                )
                for member in cohort_members
            ),
            key=lambda row: row.isin,
        )
    )
    runtime = _CLASSIFICATION_RUNTIME_IDENTITY
    return _snapshot_with_identity(
        _snapshot(
            evidence_state="PROJECTED",
            schema_identity_sha256=parsed.schema_identity_sha256,
            runtime_code_identity_sha256=runtime,
            input_identity_sha256=parsed.input_identity_sha256,
            artifact_sha256=parsed.artifact_sha256,
            artifact_revision=parsed.artifact_revision,
            cohort_identity_sha256=cohort_identity_sha256,
            cohort_size=len(cohort_members),
            private_rows=private_rows,
            snapshot_identity_sha256="",
        )
    )


def _valid_parsed(parsed: ParsedCurrentIndustryArtifactV1) -> bool:
    rows = parsed.private_rows
    return (
        parsed.evidence_state == "PARSED"
        and parsed.schema_identity_sha256 in _CLASSIFICATION_SCHEMA_IDENTITIES
        and (
            (
                parsed.schema_identity_sha256
                == LEGACY_CLASSIFICATION_SCHEMA_IDENTITY_SHA256
                and parsed.source_url == _LEGACY_SOURCE_URL
                and parsed.source_domain == "www.niftyindices.com"
                and parsed.acquisition_method == "OPERATOR_ACQUIRED"
            )
            or (
                parsed.schema_identity_sha256 == CLASSIFICATION_SCHEMA_IDENTITY_SHA256
                and parsed.source_url == _SOURCE_URL
                and parsed.source_domain == "nsearchives.nseindia.com"
                and parsed.acquisition_method == "BOUNDED_OFFICIAL_FETCH"
            )
        )
        and parsed.source_authority == "NSE_INDICES"
        and parsed.classification_tier == "INDUSTRY"
        and type(parsed.artifact_byte_count) is int
        and 0 < parsed.artifact_byte_count <= _MAX_ARTIFACT_BYTES
        and _valid_digest(parsed.artifact_sha256)
        and parsed.artifact_revision == f"sha256:{parsed.artifact_sha256}"
        and all(
            value is None
            for value in (
                parsed.publisher_published_at,
                parsed.publisher_effective_from,
                parsed.publisher_effective_through,
                parsed.publisher_revision,
            )
        )
        and _valid_digest(parsed.input_identity_sha256)
        and type(rows) is tuple
        and len(rows) == 100
        and tuple(row.isin for row in rows) == tuple(sorted(row.isin for row in rows))
        and len({row.isin for row in rows}) == 100
        and len({(row.symbol, "EQ") for row in rows}) == 100
        and all(
            type(row) is _PrivateIndustryRow
            and _seal_is(row, _PARSED_SEAL)
            and row.exchange == "NSE"
            and row.effective_symbol == row.symbol
            and _valid_isin(row.isin)
            and _industry(row.industry)
            and _nse_symbol(row.symbol)
            for row in rows
        )
        and _identity_labels_safe(rows)
    )


def _snapshot_with_identity(
    snapshot: PrivateCurrentIndustrySnapshotV1,
) -> PrivateCurrentIndustrySnapshotV1:
    if type(snapshot) is not PrivateCurrentIndustrySnapshotV1:
        raise TypeError("classification snapshot invalid")
    return _snapshot(
        evidence_state=snapshot.evidence_state,
        schema_identity_sha256=snapshot.schema_identity_sha256,
        runtime_code_identity_sha256=snapshot.runtime_code_identity_sha256,
        input_identity_sha256=snapshot.input_identity_sha256,
        artifact_sha256=snapshot.artifact_sha256,
        artifact_revision=snapshot.artifact_revision,
        cohort_identity_sha256=snapshot.cohort_identity_sha256,
        cohort_size=snapshot.cohort_size,
        private_rows=snapshot.private_rows,
        snapshot_identity_sha256=_sha(snapshot.canonical_json_bytes()),
    )


def _check_observation_prepublication(
    directory: int,
    raw_name: str,
    artifact: bytes,
    snapshot_name: str,
    snapshot_raw: bytes,
    receipt_name: str,
    marker_name: str,
    observed_at: datetime,
) -> None:
    """Check relevant existing bytes before a timing-only fresh-write rejection."""
    for name, expected in ((raw_name, artifact), (snapshot_name, snapshot_raw)):
        existing = _read_stable_private_object(directory, name, len(expected))
        if existing is not None and existing[0] != expected:
            raise ValueError("classification archive conflict")
    receipt = _read_stable_private_object(
        directory, receipt_name, _MAX_RETENTION_RECEIPT_BYTES
    )
    if receipt is None:
        # Existing snapshot without receipt is already a failed publication under
        # this archive's immutable recovery contract; expiry must not mask it.
        if (
            _read_stable_private_object(directory, snapshot_name, len(snapshot_raw))
            is not None
            or _read_stable_private_object(
                directory, marker_name, _MAX_COMPLETION_MARKER_BYTES
            )
            is not None
        ):
            raise ValueError("classification archive incomplete")
        sampled_at = _trusted_utc_now()
        if not _trusted_utc(sampled_at):
            raise ValueError("classification clock invalid")
        if sampled_at < observed_at:
            raise CurrentIndustryRetentionClockErrorV1()


class FileCurrentIndustryArchiveV1:
    def __init__(self, root: object) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("classification archive invalid")
        self._root = root

    def archive_exact(
        self,
        input: CurrentIndustryClassificationInputV1,
        artifact: bytes,
        snapshot: PrivateCurrentIndustrySnapshotV1,
        lease: StorageRootLease,
        *,
        observed_at: datetime | None = None,
    ) -> RetainedCurrentIndustrySnapshotV1 | CurrentIndustryClassificationFailureV1:
        if observed_at is not None and not _trusted_utc(observed_at):
            raise TypeError("classification observation time invalid")
        if not _valid_archive_input(input, artifact, snapshot, lease):
            raise TypeError("classification archive input invalid")
        try:
            snapshot_raw = snapshot.canonical_json_bytes()
            raw_name = f"raw-{snapshot.artifact_sha256}.csv"
            snapshot_name = f"snapshot-{snapshot.snapshot_identity_sha256}.json"
            receipt_name = f"retained-{snapshot.snapshot_identity_sha256}.json"
            marker_name = f"completion-{snapshot.snapshot_identity_sha256}.json"
            with _ARCHIVE_LOCK, lease.root_operation(self._root) as operation:
                root = operation.descriptor
                _validate_archive_root(root)
                directory = _open_archive_directory(root)
                try:
                    if observed_at is not None:
                        _check_observation_prepublication(
                            directory,
                            raw_name,
                            artifact,
                            snapshot_name,
                            snapshot_raw,
                            receipt_name,
                            marker_name,
                            observed_at,
                        )
                        operation.ensure_live()
                    _publish_object(directory, raw_name, artifact)
                    snapshot_published = _publish_object(
                        directory, snapshot_name, snapshot_raw
                    )
                    _verify_archive_binding(
                        operation,
                        root,
                        directory,
                        raw_name,
                        artifact,
                        snapshot_name,
                        snapshot_raw,
                    )
                    return self._retain_verified(
                        operation,
                        root,
                        directory,
                        raw_name,
                        artifact,
                        snapshot_name,
                        snapshot_raw,
                        snapshot,
                        snapshot_published,
                        receipt_name,
                        marker_name,
                        observed_at,
                    )
                except (
                    CurrentIndustryRetentionTimeErrorV1,
                    CurrentIndustryRetentionClockErrorV1,
                ):
                    operation.ensure_live()
                    _validate_archive_root(root)
                    _validate_archive_directory(root, directory)
                    raise
                finally:
                    os.close(directory)
        except (
            CurrentIndustryRetentionTimeErrorV1,
            CurrentIndustryRetentionClockErrorV1,
        ):
            with lease.root_operation(self._root) as operation:
                operation.ensure_live()
            raise
        except Exception:
            return _failure(("CLASSIFICATION_ARCHIVE_FAILED",), snapshot.cohort_size)

    def _retain_verified(  # noqa: C901 -- one ordered archive completion transaction
        self,
        operation: object,
        root: int,
        directory: int,
        raw_name: str,
        artifact: bytes,
        snapshot_name: str,
        snapshot_raw: bytes,
        snapshot: PrivateCurrentIndustrySnapshotV1,
        snapshot_published: bool,
        receipt_name: str,
        marker_name: str,
        observed_at: datetime | None,
    ) -> RetainedCurrentIndustrySnapshotV1:
        existing = _read_stable_private_object(
            directory, receipt_name, _MAX_RETENTION_RECEIPT_BYTES
        )
        first_completion = existing is None
        if first_completion:
            if not snapshot_published:
                raise ValueError
            sampled_at = _trusted_utc_now()
            if not _trusted_utc(sampled_at):
                raise ValueError
            if observed_at is not None and sampled_at < observed_at:
                raise CurrentIndustryRetentionClockErrorV1()
            candidate = _candidate_from_snapshot(
                snapshot, sampled_at + _RETENTION_COMPLETION_SAFETY_MARGIN
            )
            receipt_raw = _retention_receipt_bytes(candidate)
            if len(receipt_raw) > _MAX_RETENTION_RECEIPT_BYTES:
                raise ValueError
            _publish_object(directory, receipt_name, receipt_raw)
            _verify_receipt_binding(
                operation,
                root,
                directory,
                raw_name,
                artifact,
                snapshot_name,
                snapshot_raw,
                receipt_name,
                receipt_raw,
            )
            candidate = _retained_candidate_from_receipt(receipt_raw)
            if not _candidate_matches_snapshot(candidate, snapshot):
                raise ValueError
            completed_at = _trusted_utc_now()
            if not _trusted_utc(completed_at) or completed_at > candidate.known_at:
                raise ValueError
            marker_raw = _completion_marker_bytes(candidate, receipt_raw)
            if len(marker_raw) > _MAX_COMPLETION_MARKER_BYTES:
                raise ValueError
            _publish_object(directory, marker_name, marker_raw)
        else:
            receipt_raw, _ = existing
            marker = _read_stable_private_object(
                directory, marker_name, _MAX_COMPLETION_MARKER_BYTES
            )
            if marker is None:
                raise ValueError
            marker_raw, _ = marker
            candidate = _retained_candidate_from_receipt(receipt_raw)

        if (
            not _candidate_matches_snapshot(candidate, snapshot)
            or _completion_marker_known_at(marker_raw, receipt_raw, snapshot)
            != candidate.known_at
        ):
            raise ValueError
        _verify_completion_marker(
            operation,
            root,
            directory,
            raw_name,
            artifact,
            snapshot_name,
            snapshot_raw,
            receipt_name,
            receipt_raw,
            marker_name,
            marker_raw,
            candidate.known_at,
        )
        # Replays keep their original knowledge time. Complete integrity checks
        # above before classifying a later observation as temporally inadmissible.
        if observed_at is not None and candidate.known_at < observed_at:
            # The complete binding was checked immediately above; the caller also
            # rechecks its typed root operation before publishing this outcome.
            raise CurrentIndustryRetentionTimeErrorV1()
        retained_seal = object.__new__(_ArchiveRetainedSeal)
        for name in (
            "archive_identity_sha256",
            "archive_receipt_identity_sha256",
            "retained_identity_sha256",
            "snapshot_identity_sha256",
        ):
            object.__setattr__(retained_seal, name, getattr(candidate, name))
        bound_objects: list[tuple[str, bytes, os.stat_result]] = []
        for name, raw in (
            (raw_name, artifact),
            (snapshot_name, snapshot_raw),
            (receipt_name, receipt_raw),
            (marker_name, marker_raw),
        ):
            info = _stable_object(directory, name, raw)
            if info is None:
                raise ValueError("classification archive binding invalid")
            bound_objects.append((name, raw, info))
        root_info, directory_info = os.fstat(root), os.fstat(directory)
        object.__setattr__(
            retained_seal,
            "binding",
            _IndustryArchiveBinding(
                self._root,
                (root_info.st_dev, root_info.st_ino),
                (directory_info.st_dev, directory_info.st_ino),
                tuple(bound_objects),
            ),
        )
        object.__setattr__(retained_seal, "_seal", _ARCHIVE_RETAINED_SEAL)
        retained = object.__new__(RetainedCurrentIndustrySnapshotV1)
        for name in RetainedCurrentIndustrySnapshotV1.__dataclass_fields__:
            if name not in {"_archive_seal", "_seal"}:
                object.__setattr__(retained, name, getattr(candidate, name))
        object.__setattr__(retained, "_archive_seal", retained_seal)
        object.__setattr__(retained, "_seal", _RETAINED_SEAL)
        if not _archive_minted_retained(retained):
            raise ValueError
        return retained


def revalidate_retained_current_industry_snapshot_v1(
    retained: RetainedCurrentIndustrySnapshotV1,
    root: Path,
    lease: StorageRootLease,
) -> None:
    """Read-only check of the original archive binding before later publication.

    No object is created, restored, or republished. The seal retains the exact
    bytes and filesystem identities admitted when the archive originally minted
    this object, including its original knowledge time.
    """
    if not _archive_minted_retained(retained):
        raise ValueError("retained Industry archive invalid")
    seal = cast(_ArchiveRetainedSeal, getattr(retained, "_archive_seal", None))
    binding = seal.binding
    if (
        binding.root != root
        or _retention_receipt_bytes(retained) != binding.objects[2][1]
    ):
        raise ValueError("retained Industry archive invalid")
    with lease.read_operation(root) as operation:
        operation.ensure_live()
        descriptor = operation.descriptor
        _validate_archive_root(descriptor)
        root_info = os.fstat(descriptor)
        if (root_info.st_dev, root_info.st_ino) != binding.root_identity:
            raise ValueError("retained Industry root invalid")
        directory = os.open(
            _ARCHIVE_DIRECTORY,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=descriptor,
        )
        try:
            _validate_archive_directory(descriptor, directory)
            directory_info = os.fstat(directory)
            if (
                directory_info.st_dev,
                directory_info.st_ino,
            ) != binding.directory_identity:
                raise ValueError("retained Industry directory invalid")
            for name, expected, admitted in binding.objects:
                current = _read_stable_private_object(directory, name, len(expected))
                if (
                    current is None
                    or current[0] != expected
                    or not _same_metadata(current[1], admitted)
                ):
                    raise ValueError("retained Industry archive invalid")
            for name, _raw, admitted in binding.objects:
                if not _named_binding_matches(directory, name, admitted):
                    raise ValueError("retained Industry archive invalid")
            _validate_archive_directory(descriptor, directory)
            _validate_archive_root(descriptor)
            operation.ensure_live()
        finally:
            os.close(directory)


def _valid_archive_input(
    input: CurrentIndustryClassificationInputV1,
    artifact: bytes,
    snapshot: PrivateCurrentIndustrySnapshotV1,
    lease: StorageRootLease,
) -> bool:
    return all(
        (
            type(input) is CurrentIndustryClassificationInputV1,
            _valid_input(input),
            type(artifact) is bytes,
            type(snapshot) is PrivateCurrentIndustrySnapshotV1,
            _seal_is(snapshot, _SNAPSHOT_SEAL),
            type(lease) is StorageRootLease,
            _valid_snapshot(snapshot),
            _sha(artifact) == snapshot.artifact_sha256,
            input.input_identity_sha256 == snapshot.input_identity_sha256,
            input.artifact_revision == snapshot.artifact_revision,
            input.artifact_sha256 == snapshot.artifact_sha256,
            input.schema_identity_sha256 == snapshot.schema_identity_sha256,
        )
    )


def _archive_identity(snapshot: PrivateCurrentIndustrySnapshotV1) -> str:
    return _identity(
        {
            "raw_artifact_sha256": snapshot.artifact_sha256,
            "snapshot_identity_sha256": snapshot.snapshot_identity_sha256,
        }
    )


def _archive_receipt_identity(
    archive_identity: str,
    artifact_sha256: str,
    input_identity_sha256: str,
    known_at: datetime,
    snapshot_identity_sha256: str,
) -> str:
    return _identity(
        {
            "archive_identity_sha256": archive_identity,
            "artifact_sha256": artifact_sha256,
            "input_identity_sha256": input_identity_sha256,
            "known_at": _instant(known_at),
            "snapshot_identity_sha256": snapshot_identity_sha256,
        }
    )


def _candidate_from_snapshot(
    snapshot: PrivateCurrentIndustrySnapshotV1,
    known_at: datetime,
) -> _RetainedCurrentIndustryCandidateV1:
    archive_identity = _archive_identity(snapshot)
    archive_receipt_identity = _archive_receipt_identity(
        archive_identity,
        snapshot.artifact_sha256,
        snapshot.input_identity_sha256,
        known_at,
        snapshot.snapshot_identity_sha256,
    )
    provisional = _RetainedCurrentIndustryCandidateV1(
        evidence_state="RETAINED",
        schema_identity_sha256=snapshot.schema_identity_sha256,
        input_identity_sha256=snapshot.input_identity_sha256,
        artifact_sha256=snapshot.artifact_sha256,
        artifact_revision=snapshot.artifact_revision,
        snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        archive_identity_sha256=archive_identity,
        archive_receipt_identity_sha256=archive_receipt_identity,
        retained_identity_sha256="",
        snapshot_runtime_code_identity_sha256=snapshot.runtime_code_identity_sha256,
        cohort_identity_sha256=snapshot.cohort_identity_sha256,
        cohort_size=snapshot.cohort_size,
        known_at=known_at,
        publisher_published_at=None,
        publisher_effective_from=None,
        publisher_effective_through=None,
        publisher_revision=None,
        _private_rows=snapshot.private_rows,
    )
    return _RetainedCurrentIndustryCandidateV1(
        evidence_state=provisional.evidence_state,
        schema_identity_sha256=provisional.schema_identity_sha256,
        input_identity_sha256=provisional.input_identity_sha256,
        artifact_sha256=provisional.artifact_sha256,
        artifact_revision=provisional.artifact_revision,
        snapshot_identity_sha256=provisional.snapshot_identity_sha256,
        archive_identity_sha256=provisional.archive_identity_sha256,
        archive_receipt_identity_sha256=provisional.archive_receipt_identity_sha256,
        retained_identity_sha256=_sha(
            provisional.canonical_json_bytes(include_identity=False)
        ),
        snapshot_runtime_code_identity_sha256=(
            provisional.snapshot_runtime_code_identity_sha256
        ),
        cohort_identity_sha256=provisional.cohort_identity_sha256,
        cohort_size=provisional.cohort_size,
        known_at=provisional.known_at,
        publisher_published_at=None,
        publisher_effective_from=None,
        publisher_effective_through=None,
        publisher_revision=None,
        _private_rows=provisional._private_rows,  # pyright: ignore[reportPrivateUsage]
    )


def _retention_receipt_bytes(
    retained: RetainedCurrentIndustrySnapshotV1 | _RetainedCurrentIndustryCandidateV1,
) -> bytes:
    return _canonical(
        {
            "archive_identity_sha256": retained.archive_identity_sha256,
            "archive_receipt_identity_sha256": (
                retained.archive_receipt_identity_sha256
            ),
            "artifact_revision": retained.artifact_revision,
            "artifact_sha256": retained.artifact_sha256,
            "cohort_identity_sha256": retained.cohort_identity_sha256,
            "cohort_size": retained.cohort_size,
            "evidence_state": retained.evidence_state,
            "input_identity_sha256": retained.input_identity_sha256,
            "known_at": _instant(retained.known_at),
            "private_rows": [
                {
                    "effective_symbol": row.effective_symbol,
                    "exchange": row.exchange,
                    "industry": row.industry,
                    "isin": row.isin,
                    "symbol": row.symbol,
                }
                for row in retained._private_rows  # pyright: ignore[reportPrivateUsage]
            ],
            "publisher_effective_from": None,
            "publisher_effective_through": None,
            "publisher_published_at": None,
            "publisher_revision": None,
            "receipt_version": _RETENTION_RECEIPT_VERSION,
            "retained_identity_sha256": retained.retained_identity_sha256,
            "schema_identity_sha256": retained.schema_identity_sha256,
            "snapshot_identity_sha256": retained.snapshot_identity_sha256,
            "snapshot_runtime_code_identity_sha256": (
                retained.snapshot_runtime_code_identity_sha256
            ),
        }
    )


def _completion_marker_bytes(
    retained: RetainedCurrentIndustrySnapshotV1 | _RetainedCurrentIndustryCandidateV1,
    receipt_raw: bytes,
) -> bytes:
    return _canonical(
        {
            "completion_marker_version": _COMPLETION_MARKER_VERSION,
            "known_at": _instant(retained.known_at),
            "receipt_sha256": _sha(receipt_raw),
            "snapshot_identity_sha256": retained.snapshot_identity_sha256,
        }
    )


def _completion_marker_known_at(
    raw: bytes, receipt_raw: bytes, snapshot: PrivateCurrentIndustrySnapshotV1
) -> datetime:
    if type(raw) is not bytes or len(raw) > _MAX_COMPLETION_MARKER_BYTES:
        raise ValueError("classification completion marker invalid")
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        raise ValueError("classification completion marker invalid") from None
    if type(decoded) is not dict:
        raise ValueError("classification completion marker invalid")
    value = cast(dict[str, object], decoded)
    if (
        set(value)
        != {
            "completion_marker_version",
            "known_at",
            "receipt_sha256",
            "snapshot_identity_sha256",
        }
        or _canonical(value) != raw
        or value["completion_marker_version"] != _COMPLETION_MARKER_VERSION
        or value["receipt_sha256"] != _sha(receipt_raw)
        or value["snapshot_identity_sha256"] != snapshot.snapshot_identity_sha256
    ):
        raise ValueError("classification completion marker invalid")
    return _retention_receipt_known_at(value["known_at"])


def _retained_candidate_from_receipt(
    raw: bytes,
) -> _RetainedCurrentIndustryCandidateV1:
    value = _retention_receipt_value(raw)
    artifact_revision = value["artifact_revision"]
    artifact_sha256 = cast(str, value["artifact_sha256"])
    archive_identity = cast(str, value["archive_identity_sha256"])
    archive_receipt_identity = cast(str, value["archive_receipt_identity_sha256"])
    cohort_identity = cast(str, value["cohort_identity_sha256"])
    cohort_size = value["cohort_size"]
    input_identity = cast(str, value["input_identity_sha256"])
    known_at = _retention_receipt_known_at(value["known_at"])
    retained_identity = cast(str, value["retained_identity_sha256"])
    schema_identity = cast(str, value["schema_identity_sha256"])
    snapshot_identity = cast(str, value["snapshot_identity_sha256"])
    runtime_identity = cast(str, value["snapshot_runtime_code_identity_sha256"])
    private_rows = _retention_receipt_private_rows(value["private_rows"])
    snapshot = _snapshot_with_identity(
        _snapshot(
            evidence_state="PROJECTED",
            schema_identity_sha256=schema_identity,
            runtime_code_identity_sha256=runtime_identity,
            input_identity_sha256=input_identity,
            artifact_sha256=artifact_sha256,
            artifact_revision=artifact_revision,
            cohort_identity_sha256=cohort_identity,
            cohort_size=cohort_size,
            private_rows=private_rows,
            snapshot_identity_sha256="",
        )
    )
    candidate = _candidate_from_snapshot(snapshot, known_at)
    if (
        not _valid_snapshot(snapshot)
        or snapshot.snapshot_identity_sha256 != snapshot_identity
        or candidate.archive_identity_sha256 != archive_identity
        or candidate.archive_receipt_identity_sha256 != archive_receipt_identity
        or candidate.retained_identity_sha256 != retained_identity
    ):
        raise ValueError("classification retained receipt invalid")
    return candidate


def _retention_receipt_value(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes or len(raw) > _MAX_RETENTION_RECEIPT_BYTES:
        raise ValueError("classification retained receipt invalid")
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        raise ValueError("classification retained receipt invalid") from None
    if type(decoded) is not dict:
        raise ValueError("classification retained receipt invalid")
    value = cast(dict[str, object], decoded)
    expected = {
        "archive_identity_sha256",
        "archive_receipt_identity_sha256",
        "artifact_revision",
        "artifact_sha256",
        "cohort_identity_sha256",
        "cohort_size",
        "evidence_state",
        "input_identity_sha256",
        "known_at",
        "private_rows",
        "publisher_effective_from",
        "publisher_effective_through",
        "publisher_published_at",
        "publisher_revision",
        "receipt_version",
        "retained_identity_sha256",
        "schema_identity_sha256",
        "snapshot_identity_sha256",
        "snapshot_runtime_code_identity_sha256",
    }
    if (
        set(value) != expected
        or _canonical(value) != raw
        or value["receipt_version"] != _RETENTION_RECEIPT_VERSION
        or value["evidence_state"] != "RETAINED"
        or value["schema_identity_sha256"] not in _CLASSIFICATION_SCHEMA_IDENTITIES
        or any(
            value[field] is not None
            for field in (
                "publisher_effective_from",
                "publisher_effective_through",
                "publisher_published_at",
                "publisher_revision",
            )
        )
        or any(
            not _valid_digest(value[field])
            for field in (
                "archive_identity_sha256",
                "archive_receipt_identity_sha256",
                "artifact_sha256",
                "cohort_identity_sha256",
                "input_identity_sha256",
                "retained_identity_sha256",
                "schema_identity_sha256",
                "snapshot_identity_sha256",
                "snapshot_runtime_code_identity_sha256",
            )
        )
        or type(value["artifact_revision"]) is not str
        or value["artifact_revision"] != f"sha256:{value['artifact_sha256']}"
        or type(value["cohort_size"]) is not int
        or type(value["known_at"]) is not str
        or type(value["private_rows"]) is not list
    ):
        raise ValueError("classification retained receipt invalid")
    return value


def _retention_receipt_known_at(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("classification retained receipt invalid")
    try:
        known_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("classification retained receipt invalid") from None
    if not _trusted_utc(known_at) or _instant(known_at) != value:
        raise ValueError("classification retained receipt invalid")
    return known_at


def _retention_receipt_private_rows(value: object) -> tuple[_PrivateIndustryRow, ...]:
    if type(value) is not list:
        raise ValueError("classification retained receipt invalid")
    rows: list[_PrivateIndustryRow] = []
    try:
        for private_row_value in cast(list[object], value):
            if type(private_row_value) is not dict:
                raise ValueError
            row = cast(dict[str, object], private_row_value)
            if set(row) != {
                "effective_symbol",
                "exchange",
                "industry",
                "isin",
                "symbol",
            } or any(type(row[field]) is not str for field in row):
                raise ValueError
            rows.append(
                _private_row(
                    cast(str, row["isin"]),
                    cast(str, row["industry"]),
                    cast(str, row["symbol"]),
                    cast(str, row["exchange"]),
                    cast(str, row["effective_symbol"]),
                )
            )
    except (KeyError, TypeError, ValueError):
        raise ValueError("classification retained receipt invalid") from None
    return tuple(rows)


def _candidate_matches_snapshot(
    candidate: _RetainedCurrentIndustryCandidateV1,
    snapshot: PrivateCurrentIndustrySnapshotV1,
) -> bool:
    return (
        candidate.schema_identity_sha256 == snapshot.schema_identity_sha256
        and candidate.input_identity_sha256 == snapshot.input_identity_sha256
        and candidate.artifact_sha256 == snapshot.artifact_sha256
        and candidate.artifact_revision == snapshot.artifact_revision
        and candidate.snapshot_identity_sha256 == snapshot.snapshot_identity_sha256
        and candidate.snapshot_runtime_code_identity_sha256
        == snapshot.runtime_code_identity_sha256
        and candidate.cohort_identity_sha256 == snapshot.cohort_identity_sha256
        and candidate.cohort_size == snapshot.cohort_size
        and candidate._private_rows  # pyright: ignore[reportPrivateUsage]
        == snapshot.private_rows
    )


def _trusted_utc_now() -> datetime:
    return datetime.now(UTC)


def _valid_input(value: CurrentIndustryClassificationInputV1) -> bool:
    return (
        _exact_classification_source_case(
            value.schema_identity_sha256,
            value.source_url,
            value.source_authority,
            value.source_domain,
            value.acquisition_method,
            value.licence_policy_identity_sha256,
        )
        and value.classification_tier == "INDUSTRY"
        and type(value.artifact_byte_count) is int
        and value.artifact_byte_count >= 0
        and _valid_digest(value.artifact_sha256)
        and value.artifact_revision == f"sha256:{value.artifact_sha256}"
        and _valid_digest(value.licence_policy_identity_sha256)
        and all(
            item is None
            for item in (
                value.publisher_published_at,
                value.publisher_effective_from,
                value.publisher_effective_through,
                value.publisher_revision,
            )
        )
        and value.input_identity_sha256 == _identity(value.value())
    )


def _trusted_utc(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is UTC
        and value.utcoffset() == timedelta()
    )


def _valid_snapshot(snapshot: PrivateCurrentIndustrySnapshotV1) -> bool:
    return (
        snapshot.evidence_state == "PROJECTED"
        and snapshot.schema_identity_sha256 in _CLASSIFICATION_SCHEMA_IDENTITIES
        and snapshot.runtime_code_identity_sha256 == _CLASSIFICATION_RUNTIME_IDENTITY
        and _valid_digest(snapshot.input_identity_sha256)
        and _valid_digest(snapshot.artifact_sha256)
        and snapshot.artifact_revision == f"sha256:{snapshot.artifact_sha256}"
        and _valid_digest(snapshot.cohort_identity_sha256)
        and type(snapshot.cohort_size) is int
        and 1 <= snapshot.cohort_size <= 50
        and type(snapshot.private_rows) is tuple
        and len(snapshot.private_rows) == snapshot.cohort_size
        and tuple(row.isin for row in snapshot.private_rows)
        == tuple(sorted(row.isin for row in snapshot.private_rows))
        and len(
            {
                (row.isin, row.exchange, row.effective_symbol)
                for row in snapshot.private_rows
            }
        )
        == snapshot.cohort_size
        and all(
            type(row) is _PrivateIndustryRow
            and _seal_is(row, _PARSED_SEAL)
            and row.exchange == "NSE"
            and row.effective_symbol == row.symbol
            and _valid_isin(row.isin)
            and _industry(row.industry)
            and _nse_symbol(row.symbol)
            for row in snapshot.private_rows
        )
        and _identity_labels_safe(snapshot.private_rows)
        and snapshot.snapshot_identity_sha256 == _sha(snapshot.canonical_json_bytes())
    )


def _validate_archive_root(root: int) -> None:
    info = os.fstat(root)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise ValueError


def _validate_archive_directory(root: int, directory: int) -> None:
    opened = os.fstat(directory)
    named = os.stat(_ARCHIVE_DIRECTORY, dir_fd=root, follow_symlinks=False)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or stat.S_IMODE(opened.st_mode) != 0o700
        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
    ):
        raise ValueError


def _verify_archive_binding(
    operation: object,
    root: int,
    directory: int,
    raw_name: str,
    raw: bytes,
    snapshot_name: str,
    snapshot_raw: bytes,
) -> None:
    raw_info = _stable_object(directory, raw_name, raw)
    snapshot_info = _stable_object(directory, snapshot_name, snapshot_raw)
    if (
        raw_info is None
        or snapshot_info is None
        or not _named_binding_matches(directory, raw_name, raw_info)
        or not _named_binding_matches(directory, snapshot_name, snapshot_info)
    ):
        raise ValueError
    _validate_archive_directory(root, directory)
    _validate_archive_root(root)
    ensure_live = getattr(operation, "ensure_live", None)
    if not callable(ensure_live):
        raise ValueError
    ensure_live()


def _verify_receipt_binding(
    operation: object,
    root: int,
    directory: int,
    raw_name: str,
    raw: bytes,
    snapshot_name: str,
    snapshot_raw: bytes,
    receipt_name: str,
    receipt_raw: bytes,
) -> None:
    _verify_archive_binding(
        operation,
        root,
        directory,
        raw_name,
        raw,
        snapshot_name,
        snapshot_raw,
    )
    receipt_info = _stable_object(directory, receipt_name, receipt_raw)
    if receipt_info is None or not _named_binding_matches(
        directory, receipt_name, receipt_info
    ):
        raise ValueError
    os.fsync(directory)
    _verify_archive_binding(
        operation,
        root,
        directory,
        raw_name,
        raw,
        snapshot_name,
        snapshot_raw,
    )
    receipt_info = _stable_object(directory, receipt_name, receipt_raw)
    if receipt_info is None or not _named_binding_matches(
        directory, receipt_name, receipt_info
    ):
        raise ValueError


def _verify_completion_marker(
    operation: object,
    root: int,
    directory: int,
    raw_name: str,
    raw: bytes,
    snapshot_name: str,
    snapshot_raw: bytes,
    receipt_name: str,
    receipt_raw: bytes,
    marker_name: str,
    marker_raw: bytes,
    known_at: datetime,
) -> None:
    _verify_receipt_binding(
        operation,
        root,
        directory,
        raw_name,
        raw,
        snapshot_name,
        snapshot_raw,
        receipt_name,
        receipt_raw,
    )
    marker_info = _stable_object(directory, marker_name, marker_raw)
    if (
        marker_info is None
        or not _named_binding_matches(directory, marker_name, marker_info)
        or not _marker_mtime_at_or_before(marker_info, known_at)
    ):
        raise ValueError
    _validate_archive_directory(root, directory)
    _validate_archive_root(root)
    ensure_live = getattr(operation, "ensure_live", None)
    if not callable(ensure_live):
        raise ValueError
    ensure_live()


def _marker_filesystem_mtime_ns(info: os.stat_result) -> int:
    """Return the marker's latest write-or-link metadata time."""
    return max(info.st_mtime_ns, info.st_ctime_ns)


def _marker_mtime_at_or_before(info: os.stat_result, known_at: datetime) -> bool:
    if not _trusted_utc(known_at):
        return False
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = known_at - epoch
    deadline_ns = (
        delta.days * 86_400 + delta.seconds
    ) * 1_000_000_000 + delta.microseconds * 1_000
    marker_mtime_ns = _marker_filesystem_mtime_ns(info)
    return type(marker_mtime_ns) is int and marker_mtime_ns <= deadline_ns


def _read_stable_private_object(
    parent: int, name: str, maximum_size: int
) -> tuple[bytes, os.stat_result] | None:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent,
        )
    except FileNotFoundError:
        return None
    try:
        named_before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        opened_before = os.fstat(descriptor)
        if (
            maximum_size < 0
            or opened_before.st_size > maximum_size
            or not _private_regular_object(opened_before, opened_before.st_size)
            or not _same_metadata(named_before, opened_before)
        ):
            raise ValueError
        chunks: list[bytes] = []
        remaining = opened_before.st_size
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                raise ValueError
            chunks.append(chunk)
            remaining -= len(chunk)
        opened_after = os.fstat(descriptor)
        named_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        raw = b"".join(chunks)
        if (
            not _same_metadata(opened_before, opened_after)
            or not _same_metadata(named_before, named_after)
            or not _same_metadata(opened_after, named_after)
            or not _private_regular_object(named_after, len(raw))
        ):
            raise ValueError
        return raw, named_after
    finally:
        os.close(descriptor)


def _open_archive_directory(root: int) -> int:
    with contextlib.suppress(FileExistsError):
        os.mkdir(_ARCHIVE_DIRECTORY, 0o700, dir_fd=root)
    directory = os.open(
        _ARCHIVE_DIRECTORY,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=root,
    )
    try:
        _validate_archive_directory(root, directory)
        os.fsync(root)
        return directory
    except Exception:
        os.close(directory)
        raise


def _publish_object(parent: int, name: str, raw: bytes) -> bool:
    try:
        if _object_matches(parent, name, raw):
            os.fsync(parent)
            return False
    except FileNotFoundError:
        pass
    temporary = f".{name}.{uuid4().hex}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent,
        )
        offset = 0
        while offset < len(raw):
            count = os.write(descriptor, raw[offset:])
            if count <= 0:
                raise OSError
            offset += count
        os.fchmod(descriptor, 0o400)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(
                temporary,
                name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
        except FileExistsError:
            if not _object_matches(parent, name, raw):
                raise
        os.unlink(temporary, dir_fd=parent)
        os.fsync(parent)
        if not _object_matches(parent, name, raw):
            raise ValueError
        return True
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=parent)


def _object_matches(parent: int, name: str, raw: bytes) -> bool:
    return _stable_object(parent, name, raw) is not None


def _stable_object(parent: int, name: str, raw: bytes) -> os.stat_result | None:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent
    )
    try:
        named_before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        opened_before = os.fstat(descriptor)
        if not _private_regular_object(opened_before, len(raw)) or not _same_metadata(
            named_before, opened_before
        ):
            return None
        chunks: list[bytes] = []
        remaining = len(raw) + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        opened_after = os.fstat(descriptor)
        named_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (
            b"".join(chunks) != raw
            or not _same_metadata(opened_before, opened_after)
            or not _same_metadata(named_before, named_after)
            or not _same_metadata(opened_after, named_after)
        ):
            return None
        return named_after
    finally:
        os.close(descriptor)


def _named_binding_matches(parent: int, name: str, expected: os.stat_result) -> bool:
    try:
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return _same_metadata(named, expected) and _private_regular_object(
        named, expected.st_size
    )


def _private_regular_object(info: os.stat_result, size: int) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == 0o400
        and info.st_nlink == 1
        and info.st_size == size
    )


def _same_metadata(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        first.st_dev,
        first.st_ino,
        first.st_size,
        first.st_mode,
        first.st_uid,
        first.st_nlink,
        first.st_mtime_ns,
        first.st_ctime_ns,
    ) == (
        second.st_dev,
        second.st_ino,
        second.st_size,
        second.st_mode,
        second.st_uid,
        second.st_nlink,
        second.st_mtime_ns,
        second.st_ctime_ns,
    )


def _failure(
    reasons: tuple[str, ...], cohort_size: int | None = None
) -> CurrentIndustryClassificationFailureV1:
    return CurrentIndustryClassificationFailureV1(
        _failure_state(reasons), reasons, cohort_size
    )


def _parse_rows(artifact: bytes) -> tuple[_PrivateIndustryRow, ...]:
    rows = _admit_rows(_records(artifact))
    if not _identity_labels_safe(rows):
        raise ValueError
    return rows


def _records(artifact: bytes) -> list[list[str]]:
    if artifact.startswith(b"\xef\xbb\xbf"):
        raise ValueError
    text = artifact.decode("utf-8")
    if "\x00" in text:
        raise ValueError
    records = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    if (
        len(records) != 101
        or tuple(records[0]) != _HEADER
        or any(len(record) != 5 for record in records)
    ):
        raise ValueError
    return records


def _admit_rows(records: list[list[str]]) -> tuple[_PrivateIndustryRow, ...]:
    rows: list[_PrivateIndustryRow] = []
    isins: dict[str, tuple[str, str]] = {}
    symbols: dict[tuple[str, str], str] = {}
    for company, industry, symbol, series, isin in records[1:]:
        _admit_row(company, industry, symbol, series, isin, isins, symbols)
        rows.append(_private_row(isin, industry, symbol))
    if len(isins) != 100 or len(symbols) != 100 or not _company_names_safe(records[1:]):
        raise ValueError
    return tuple(sorted(rows, key=lambda row: row.isin))


def _admit_row(
    company: str,
    industry: str,
    symbol: str,
    series: str,
    isin: str,
    isins: dict[str, tuple[str, str]],
    symbols: dict[tuple[str, str], str],
) -> None:
    if (
        not all(_field(value) for value in (company, symbol, series, isin))
        or not _industry(industry)
        or not _nse_symbol(symbol)
        or series != "EQ"
        or not _valid_isin(isin)
    ):
        raise ValueError
    _admit_identity(isin, industry, symbol, series, isins, symbols)
    isins[isin] = (industry, symbol)
    symbols[(symbol, series)] = isin


def _admit_identity(
    isin: str,
    industry: str,
    symbol: str,
    series: str,
    isins: dict[str, tuple[str, str]],
    symbols: dict[tuple[str, str], str],
) -> None:
    prior_isin = isins.get(isin)
    prior_symbol = symbols.get((symbol, series))
    if prior_isin is not None:
        if prior_isin == (industry, symbol):
            raise _AmbiguousArtifactIdentity
        raise _ConflictingArtifactIdentity
    if prior_symbol is not None:
        if prior_symbol == isin:
            raise _AmbiguousArtifactIdentity
        raise _ConflictingArtifactIdentity


def _field(value: object) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= _MAX_FIELD_CHARS
        and value == value.strip()
        and not value.startswith(("=", "+", "-", "@"))
        and not any(
            unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"} for char in value
        )
    )


def _nse_symbol(value: object) -> bool:
    return _field(value) and _NSE_SYMBOL.fullmatch(cast(str, value)) is not None


def _industry(value: object) -> bool:
    return _field(value)


def _valid_isin(value: object) -> bool:
    if type(value) is not str or _ISIN.fullmatch(value) is None:
        return False
    digits = "".join(str(ord(char) - 55) if char.isalpha() else char for char in value)
    return (
        sum(
            number if index % 2 == 0 else (number * 2 - 9 if number > 4 else number * 2)
            for index, number in enumerate(map(int, reversed(digits)))
        )
        % 10
        == 0
    )


def _company_names_safe(records: list[list[str]]) -> bool:
    return not any(
        _company_name_bearing(label[1], candidate[0])
        for label in records
        for candidate in records
    )


def _company_name_bearing(industry: str, company_name: str) -> bool:
    return _privacy_key(company_name) in _privacy_key(industry)


def _privacy_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value.casefold())


def _identity_labels_safe(rows: tuple[_PrivateIndustryRow, ...]) -> bool:
    return not any(
        _identity_bearing(label.industry, candidate.isin, candidate.symbol)
        for label in rows
        for candidate in rows
    )


def _identity_bearing(industry: str, isin: str, symbol: str) -> bool:
    return (
        re.search(re.escape(isin), industry, flags=re.ASCII | re.IGNORECASE) is not None
        or re.search(
            rf"(?<![A-Z0-9.&_-]){re.escape(symbol)}(?![A-Z0-9.&_-])",
            industry,
            flags=re.ASCII | re.IGNORECASE,
        )
        is not None
    )
