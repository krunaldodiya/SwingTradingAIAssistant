# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false, reportOperatorIssue=false, reportOptionalMemberAccess=false, reportOptionalOperand=false, reportReturnType=false
"""Aggregate-only current supplied-cohort Industry Participation V4.

The reducer consumes only the sealed V4 context's already-calculated private
handoff.  It never evaluates direction, reads an archive, or acquires evidence.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal, cast

from swing_trading_ai_assistant.market_data.bharatstock import (
    price_basis_for_adjustment,
)
from swing_trading_ai_assistant.market_data.current_industry_classification import (
    _PARSED_SEAL,  # pyright: ignore[reportPrivateUsage]
    CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
    LEGACY_CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
    CurrentIndustryClassificationFailureV1,
    RetainedCurrentIndustrySnapshotV1,
    _archive_minted_retained,  # pyright: ignore[reportPrivateUsage]
    _field,  # pyright: ignore[reportPrivateUsage]
    _identity_labels_safe,  # pyright: ignore[reportPrivateUsage]
    _industry,  # pyright: ignore[reportPrivateUsage]
    _PrivateIndustryRow,  # pyright: ignore[reportPrivateUsage]
    _valid_isin,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.market_regime.current_supplied_cohort_v4 import (
    CurrentSamePassMarketRegimeReportV4,
    RetainedCurrentSamePassMarketContextV4,
    _CurrentSamePassMemberDirectionCandidateV4,  # pyright: ignore[reportPrivateUsage]
    _CurrentSamePassMemberDirectionRowV4,  # pyright: ignore[reportPrivateUsage]
    _industry_projection_from_retained_context_v4,  # pyright: ignore[reportPrivateUsage]
)

CONTRACT_VERSION: Final = "current-supplied-cohort-industry-participation@v4"
_FAILURE_CONTRACT_VERSION: Final = (
    "current-supplied-cohort-industry-participation-failure@v4"
)
_CALCULATION_CONTRACT_VERSION: Final = (
    "current-supplied-cohort-industry-participation-calculation@v4"
)
_RUNTIME_MANIFEST_VERSION: Final = "plan27-source-at-rest@v1"
_RUNTIME_MANIFEST_MODULE: Final = (
    "swing_trading_ai_assistant.sector_analysis."
    "current_industry_participation_v4_runtime_identity_manifest"
)
_RUNTIME_MANIFEST_PATH: Final = (
    "src/swing_trading_ai_assistant/sector_analysis/"
    "current_industry_participation_v4_runtime_identity_manifest.py"
)
_SOURCE_PATH: Final = (
    "src/swing_trading_ai_assistant/sector_analysis/"
    "current_industry_participation_v4.py"
)
_RUNTIME_SOURCES: Final = (_SOURCE_PATH, _RUNTIME_MANIFEST_PATH)
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_REASON_ORDER: Final = (
    "MARKET_REGIME_UNAVAILABLE",
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
_MALFORMED_REASONS: Final = frozenset(
    {
        "CLASSIFICATION_ARTIFACT_MALFORMED",
        "CLASSIFICATION_AMBIGUOUS",
        "CLASSIFICATION_CONFLICTING",
        "COHORT_BINDING_MISMATCH",
        "MEMBER_IDENTITY_MISMATCH",
    }
)
_UNSUPPORTED_REASONS: Final = frozenset(
    {
        "CLASSIFICATION_SOURCE_UNSUPPORTED",
        "CLASSIFICATION_TIER_UNSUPPORTED",
        "CLASSIFICATION_MEMBER_UNSUPPORTED",
    }
)
_INSUFFICIENT_REASONS: Final = frozenset(
    {
        "MARKET_REGIME_UNAVAILABLE",
        "CLASSIFICATION_ARTIFACT_MISSING",
        "CLASSIFICATION_FUTURE_KNOWN",
        "CLASSIFICATION_SESSION_STALE",
        "CLASSIFICATION_ARCHIVE_FAILED",
    }
)
_IST: Final = timezone(timedelta(hours=5, minutes=30))
_CURRENT_CLASSIFICATION_SOURCE_URL: Final = (
    "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv"
)
_LEGACY_CLASSIFICATION_SOURCE_URL: Final = (
    "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"
)
_CLASSIFICATION_SCHEMA_IDENTITIES: Final = frozenset(
    {
        LEGACY_CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
        CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
    }
)


def _classification_source_url(schema_identity: str) -> str:
    if schema_identity == LEGACY_CLASSIFICATION_SCHEMA_IDENTITY_SHA256:
        return _LEGACY_CLASSIFICATION_SOURCE_URL
    if schema_identity == CLASSIFICATION_SCHEMA_IDENTITY_SHA256:
        return _CURRENT_CLASSIFICATION_SOURCE_URL
    raise ValueError("unsupported classification schema")


def _admitted_classification_source_url(schema_identity: object) -> str | None:
    if type(schema_identity) is not str:
        return None
    try:
        return _classification_source_url(schema_identity)
    except ValueError:
        return None


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _identity(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _instant(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _valid_digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _plain(value: object, *, excluded: frozenset[str] = frozenset()) -> object:
    if isinstance(value, datetime):
        return _instant(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if is_dataclass(value):
        return {
            item.name: _plain(getattr(value, item.name))
            for item in fields(value)
            if item.name not in excluded and item.name != "_archive_seal"
        }
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def _object_identity_without(value: object, *names: str) -> str:
    return _identity(_plain(value, excluded=frozenset(names)))


def _runtime_source_sha256(relative_path: str) -> str:
    modules = {
        _SOURCE_PATH: __name__,
        _RUNTIME_MANIFEST_PATH: _RUNTIME_MANIFEST_MODULE,
    }
    try:
        return runtime_source_sha256(
            modules[relative_path],
            Path(__file__).resolve().parents[1],
            relative_path,
        )
    except (KeyError, OSError, ValueError):
        raise ValueError("industry participation v2 runtime identity invalid") from None


def current_industry_participation_runtime_code_identity_v4() -> str:
    try:
        raw = importlib.import_module(
            _RUNTIME_MANIFEST_MODULE
        ).CURRENT_INDUSTRY_PARTICIPATION_V4_RUNTIME_SOURCE_DIGESTS
    except (AttributeError, ImportError):
        raise ValueError("industry participation v2 runtime identity invalid") from None
    if type(raw) is not dict or tuple(raw) != (_SOURCE_PATH,):
        raise ValueError("industry participation v2 runtime identity invalid")
    mapping = cast(dict[str, object], raw)
    digest = mapping[_SOURCE_PATH]
    if (
        type(digest) is not str
        or not _valid_digest(digest)
        or digest != _runtime_source_sha256(_SOURCE_PATH)
    ):
        raise ValueError("industry participation v2 runtime identity invalid")
    return _identity(
        {
            "runtime_manifest_version": _RUNTIME_MANIFEST_VERSION,
            "modules": [
                {
                    "relative_path": relative_path,
                    "source_sha256": _runtime_source_sha256(relative_path),
                }
                for relative_path in _RUNTIME_SOURCES
            ],
        }
    )


_RUNTIME_CODE_IDENTITY: Final = (
    current_industry_participation_runtime_code_identity_v4()
)


def _schema_field(
    name: str,
    semantic_type: str,
    unit: str,
    nullability: str,
    bounds: str,
) -> dict[str, str]:
    return {
        "name": name,
        "semantic_type": semantic_type,
        "unit": unit,
        "nullability": nullability,
        "bounds": bounds,
    }


_SCHEMA_TYPE_ROWS: Final = (
    {
        "name": "CurrentIndustryCountV4",
        "ordered_fields": (
            _schema_field(
                "industry", "SAFE_TEXT", "NOT_APPLICABLE", "REQUIRED", "LENGTH[1,512]"
            ),
            _schema_field("member_count", "UINT", "MEMBERS", "REQUIRED", "[1,50]"),
            _schema_field("advances", "UINT", "MEMBERS", "REQUIRED", "[0,50]"),
            _schema_field("declines", "UINT", "MEMBERS", "REQUIRED", "[0,50]"),
            _schema_field("unchanged", "UINT", "MEMBERS", "REQUIRED", "[0,50]"),
            _schema_field(
                "row_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    },
    {
        "name": "CurrentIndustryParticipationReportV4",
        "ordered_fields": (
            _schema_field(
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-supplied-cohort-industry-participation@v4"]',
            ),
            _schema_field(
                "schema_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            _schema_field(
                "calculation_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            _schema_field(
                "runtime_code_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            _schema_field(
                "evidence_state",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["OBSERVED"]',
            ),
            _schema_field(
                "market_regime_report_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            _schema_field(
                "direction_candidate_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            _schema_field(
                "classification_input_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            _schema_field(
                "artifact_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            _schema_field(
                "snapshot_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            _schema_field(
                "archive_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            _schema_field(
                "archive_receipt_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            _schema_field(
                "retained_classification_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            _schema_field(
                "canonical_cohort_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            _schema_field("cohort_size", "UINT", "MEMBERS", "REQUIRED", "[1,50]"),
            _schema_field(
                "decision_session",
                "LOCAL_DATE",
                "ISO_8601_DATE",
                "REQUIRED",
                "YYYY_MM_DD",
            ),
            _schema_field(
                "comparison_session",
                "LOCAL_DATE",
                "ISO_8601_DATE",
                "REQUIRED",
                "YYYY_MM_DD",
            ),
            _schema_field(
                "decision_cutoff",
                "UTC_INSTANT",
                "UTC",
                "REQUIRED",
                "AWARE_UTC_MICROSECOND",
            ),
            _schema_field(
                "source_url",
                "SAFE_TEXT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LENGTH[1,2048]",
            ),
            _schema_field(
                "source_attribution",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["NSE_INDICES"]',
            ),
            _schema_field(
                "classification_tier",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["INDUSTRY"]',
            ),
            _schema_field(
                "artifact_revision",
                "SAFE_REVISION",
                "NOT_APPLICABLE",
                "REQUIRED",
                "SAFE_REVISION",
            ),
            _schema_field(
                "known_at", "UTC_INSTANT", "UTC", "REQUIRED", "AWARE_UTC_MICROSECOND"
            ),
            _schema_field(
                "publisher_published_at", "NULL", "NOT_APPLICABLE", "REQUIRED", "None"
            ),
            _schema_field(
                "publisher_effective_from", "NULL", "NOT_APPLICABLE", "REQUIRED", "None"
            ),
            _schema_field(
                "publisher_effective_through",
                "NULL",
                "NOT_APPLICABLE",
                "REQUIRED",
                "None",
            ),
            _schema_field(
                "publisher_revision", "NULL", "NOT_APPLICABLE", "REQUIRED", "None"
            ),
            _schema_field(
                "industries",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[CurrentIndustryCountV4,1..N]",
            ),
            _schema_field(
                "reasons", "ORDERED_TUPLE", "NOT_APPLICABLE", "REQUIRED", "tuple[(),0]"
            ),
            _schema_field(
                "report_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    },
    {
        "name": "CurrentIndustryParticipationFailureV4",
        "ordered_fields": (
            _schema_field(
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-supplied-cohort-industry-participation-failure@v4"]',
            ),
            _schema_field(
                "evidence_state",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["MALFORMED_EVIDENCE","UNSUPPORTED_CAPABILITY","INSUFFICIENT_EVIDENCE"]',
            ),
            _schema_field(
                "canonical_cohort_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            _schema_field("cohort_size", "UINT", "MEMBERS", "REQUIRED", "[1,50]"),
            _schema_field(
                "decision_session",
                "LOCAL_DATE",
                "ISO_8601_DATE",
                "REQUIRED",
                "YYYY_MM_DD",
            ),
            _schema_field(
                "decision_cutoff",
                "UTC_INSTANT",
                "UTC",
                "REQUIRED",
                "AWARE_UTC_MICROSECOND",
            ),
            _schema_field(
                "market_regime_report_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "NULLABLE",
                "LOWERCASE_64_HEX",
            ),
            _schema_field(
                "classification_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "NULLABLE",
                "LOWERCASE_64_HEX",
            ),
            _schema_field(
                "known_at", "UTC_INSTANT", "UTC", "NULLABLE", "AWARE_UTC_MICROSECOND"
            ),
            _schema_field("industries", "NULL", "NOT_APPLICABLE", "REQUIRED", "None"),
            _schema_field(
                "reasons",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[IndustryReason,1..13]",
            ),
            _schema_field(
                "failure_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    },
)
_SCHEMA_STATE_PROJECTIONS: Final = (
    (
        "CurrentIndustryParticipationFailureV4",
        (
            ("MALFORMED_EVIDENCE", "industries=NONE,reasons=NONEMPTY"),
            ("UNSUPPORTED_CAPABILITY", "industries=NONE,reasons=NONEMPTY"),
            ("INSUFFICIENT_EVIDENCE", "industries=NONE,reasons=NONEMPTY"),
        ),
    ),
    (
        "CurrentIndustryParticipationReportV4",
        (("OBSERVED", "industries=REQUIRED,reasons=EMPTY"),),
    ),
)


def _industry_schema_metadata_v4() -> dict[str, object]:
    return {
        "contract_version": CONTRACT_VERSION,
        "type_rows": _SCHEMA_TYPE_ROWS,
        "state_projections": _SCHEMA_STATE_PROJECTIONS,
        "unknown_key_policy": "REJECT",
    }


def current_industry_participation_schema_metadata_v4() -> dict[str, object]:
    return _industry_schema_metadata_v4()


def current_industry_participation_schema_metadata_digest_v4(metadata: object) -> str:
    if type(metadata) is not dict or set(metadata) != {
        "contract_version",
        "type_rows",
        "state_projections",
        "unknown_key_policy",
    }:
        raise ValueError("unknown Industry schema metadata key")
    return _identity(metadata)


def current_industry_participation_schema_identity_from_metadata_v4(
    metadata: object,
) -> str:
    if _canonical(metadata) != _canonical(_industry_schema_metadata_v4()):
        raise ValueError("Industry schema metadata differs from frozen contract")
    return current_industry_participation_schema_metadata_digest_v4(metadata)


SCHEMA_IDENTITY_SHA256: Final = (
    current_industry_participation_schema_identity_from_metadata_v4(
        _industry_schema_metadata_v4()
    )
)
CALCULATION_IDENTITY_SHA256: Final = _identity(
    {
        "contract_version": _CALCULATION_CONTRACT_VERSION,
        "classification_tier": "INDUSTRY",
        "directions": ["ADVANCE", "DECLINE", "UNCHANGED"],
        "row_order": "ascending exact industry",
        "equations": [
            "member_count=advances+declines+unchanged",
            "sum(member_count)=cohort_size",
            "sum(row counts)=market-regime counts",
        ],
        "reason_order": list(_REASON_ORDER),
        "precedence": [
            "MALFORMED_EVIDENCE",
            "UNSUPPORTED_CAPABILITY",
            "INSUFFICIENT_EVIDENCE",
        ],
        "suppression": "whole-result",
    }
)


@dataclass(frozen=True, slots=True)
class CurrentIndustryCountV4:
    industry: str
    member_count: int
    advances: int
    declines: int
    unchanged: int
    row_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.industry) is not str
            or not 1 <= len(self.industry.encode("utf-8")) <= 512
            or any(
                type(value) is not int or not 0 <= value <= 50
                for value in (self.advances, self.declines, self.unchanged)
            )
            or type(self.member_count) is not int
            or not 1 <= self.member_count <= 50
            or self.member_count != self.advances + self.declines + self.unchanged
            or not _valid_digest(self.row_identity_sha256)
            or self.row_identity_sha256
            != hashlib.sha256(
                self.canonical_json_bytes(include_identity=False)
            ).hexdigest()
        ):
            raise ValueError("industry participation v2 row invalid")

    def canonical_json_bytes(self, *, include_identity: bool = True) -> bytes:
        value: dict[str, object] = {
            "advances": self.advances,
            "declines": self.declines,
            "industry": self.industry,
            "member_count": self.member_count,
            "unchanged": self.unchanged,
        }
        if include_identity:
            value["row_identity_sha256"] = self.row_identity_sha256
        return _canonical(value)


@dataclass(frozen=True, slots=True, init=False)
class CurrentIndustryParticipationReportV4:
    contract_version: Literal["current-supplied-cohort-industry-participation@v4"]
    schema_identity_sha256: str
    calculation_identity_sha256: str
    runtime_code_identity_sha256: str
    evidence_state: Literal["OBSERVED"]
    market_regime_report_identity_sha256: str
    direction_candidate_identity_sha256: str
    classification_input_identity_sha256: str
    artifact_sha256: str
    snapshot_identity_sha256: str
    archive_identity_sha256: str
    archive_receipt_identity_sha256: str
    retained_classification_identity_sha256: str
    canonical_cohort_identity_sha256: str
    cohort_size: int
    decision_session: date
    comparison_session: date
    decision_cutoff: datetime
    source_url: str
    source_attribution: Literal["NSE_INDICES"]
    classification_tier: Literal["INDUSTRY"]
    artifact_revision: str
    known_at: datetime
    publisher_published_at: None
    publisher_effective_from: None
    publisher_effective_through: None
    publisher_revision: None
    industries: tuple[CurrentIndustryCountV4, ...]
    reasons: tuple[()]
    report_identity_sha256: str
    _reducer_seal: object = field(repr=False, compare=False, hash=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("industry participation v2 report constructor unavailable")

    def canonical_json_bytes(self, *, include_identity: bool = True) -> bytes:
        value: dict[str, object] = {
            "archive_identity_sha256": self.archive_identity_sha256,
            "archive_receipt_identity_sha256": self.archive_receipt_identity_sha256,
            "artifact_revision": self.artifact_revision,
            "artifact_sha256": self.artifact_sha256,
            "calculation_identity_sha256": self.calculation_identity_sha256,
            "canonical_cohort_identity_sha256": self.canonical_cohort_identity_sha256,
            "classification_input_identity_sha256": self.classification_input_identity_sha256,
            "classification_tier": self.classification_tier,
            "cohort_size": self.cohort_size,
            "comparison_session": self.comparison_session.isoformat(),
            "contract_version": self.contract_version,
            "decision_cutoff": _instant(self.decision_cutoff),
            "decision_session": self.decision_session.isoformat(),
            "direction_candidate_identity_sha256": self.direction_candidate_identity_sha256,
            "evidence_state": self.evidence_state,
            "industries": [
                json.loads(row.canonical_json_bytes().decode("utf-8"))
                for row in self.industries
            ],
            "known_at": _instant(self.known_at),
            "market_regime_report_identity_sha256": self.market_regime_report_identity_sha256,
            "publisher_effective_from": None,
            "publisher_effective_through": None,
            "publisher_published_at": None,
            "publisher_revision": None,
            "reasons": [],
            "retained_classification_identity_sha256": self.retained_classification_identity_sha256,
            "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
            "schema_identity_sha256": self.schema_identity_sha256,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "source_attribution": self.source_attribution,
            "source_url": self.source_url,
        }
        if include_identity:
            value["report_identity_sha256"] = self.report_identity_sha256
        return _canonical(value)


@dataclass(frozen=True, slots=True, init=False)
class CurrentIndustryParticipationFailureV4:
    contract_version: Literal[
        "current-supplied-cohort-industry-participation-failure@v4"
    ]
    evidence_state: Literal[
        "MALFORMED_EVIDENCE", "UNSUPPORTED_CAPABILITY", "INSUFFICIENT_EVIDENCE"
    ]
    canonical_cohort_identity_sha256: str
    cohort_size: int
    decision_session: date
    decision_cutoff: datetime
    market_regime_report_identity_sha256: str | None
    classification_identity_sha256: str | None
    known_at: datetime | None
    industries: None
    reasons: tuple[str, ...]
    failure_identity_sha256: str
    _reducer_seal: object = field(repr=False, compare=False, hash=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("industry participation v2 failure constructor unavailable")

    def canonical_json_bytes(self, *, include_identity: bool = True) -> bytes:
        value: dict[str, object] = {
            "canonical_cohort_identity_sha256": self.canonical_cohort_identity_sha256,
            "classification_identity_sha256": self.classification_identity_sha256,
            "cohort_size": self.cohort_size,
            "contract_version": self.contract_version,
            "decision_cutoff": _instant(self.decision_cutoff),
            "decision_session": self.decision_session.isoformat(),
            "evidence_state": self.evidence_state,
            "industries": None,
            "known_at": _instant(self.known_at) if self.known_at is not None else None,
            "market_regime_report_identity_sha256": self.market_regime_report_identity_sha256,
            "reasons": list(self.reasons),
        }
        if include_identity:
            value["failure_identity_sha256"] = self.failure_identity_sha256
        return _canonical(value)


def _reduce_current_industry_participation_unsealed_v4(  # noqa: C901 - closed failure precedence is intentional.
    market_context: RetainedCurrentSamePassMarketContextV4,
    classification: RetainedCurrentIndustrySnapshotV1
    | CurrentIndustryClassificationFailureV1,
) -> CurrentIndustryParticipationReportV4 | CurrentIndustryParticipationFailureV4:
    """Reduce literal Industry membership with the sealed, precomputed V4 directions."""

    def failure(
        report: CurrentSamePassMarketRegimeReportV4,
        classification_identity: str | None,
        known_at: datetime | None,
        reasons: tuple[str, ...],
    ) -> CurrentIndustryParticipationFailureV4:
        ordered = _ordered(reasons)
        values: dict[str, object] = {
            "contract_version": _FAILURE_CONTRACT_VERSION,
            "evidence_state": _state(ordered),
            "canonical_cohort_identity_sha256": report.canonical_cohort_identity_sha256,
            "cohort_size": report.cohort_size,
            "decision_session": report.decision_session,
            "decision_cutoff": report.decision_cutoff,
            "market_regime_report_identity_sha256": report.report_identity_sha256,
            "classification_identity_sha256": classification_identity,
            "known_at": known_at,
            "industries": None,
            "reasons": ordered,
        }
        identity = _identity(_plain(values))
        result = object.__new__(CurrentIndustryParticipationFailureV4)
        for name, value in (values | {"failure_identity_sha256": identity}).items():
            object.__setattr__(result, name, value)
        return result

    def observed(
        report: CurrentSamePassMarketRegimeReportV4,
        candidate: _CurrentSamePassMemberDirectionCandidateV4,
        retained: RetainedCurrentIndustrySnapshotV1,
        industries: tuple[CurrentIndustryCountV4, ...],
    ) -> CurrentIndustryParticipationReportV4:
        values: dict[str, object] = {
            "contract_version": CONTRACT_VERSION,
            "schema_identity_sha256": SCHEMA_IDENTITY_SHA256,
            "calculation_identity_sha256": CALCULATION_IDENTITY_SHA256,
            "runtime_code_identity_sha256": _RUNTIME_CODE_IDENTITY,
            "evidence_state": "OBSERVED",
            "market_regime_report_identity_sha256": report.report_identity_sha256,
            "direction_candidate_identity_sha256": candidate.direction_candidate_identity_sha256,
            "classification_input_identity_sha256": retained.input_identity_sha256,
            "artifact_sha256": retained.artifact_sha256,
            "snapshot_identity_sha256": retained.snapshot_identity_sha256,
            "archive_identity_sha256": retained.archive_identity_sha256,
            "archive_receipt_identity_sha256": retained.archive_receipt_identity_sha256,
            "retained_classification_identity_sha256": retained.retained_identity_sha256,
            "canonical_cohort_identity_sha256": report.canonical_cohort_identity_sha256,
            "cohort_size": report.cohort_size,
            "decision_session": report.decision_session,
            "comparison_session": report.comparison_session,
            "decision_cutoff": report.decision_cutoff,
            "source_url": _classification_source_url(retained.schema_identity_sha256),
            "source_attribution": "NSE_INDICES",
            "classification_tier": "INDUSTRY",
            "artifact_revision": retained.artifact_revision,
            "known_at": retained.known_at,
            "publisher_published_at": None,
            "publisher_effective_from": None,
            "publisher_effective_through": None,
            "publisher_revision": None,
            "industries": industries,
            "reasons": (),
        }
        identity = _identity(_plain(values))
        result = object.__new__(CurrentIndustryParticipationReportV4)
        for name, value in (values | {"report_identity_sha256": identity}).items():
            object.__setattr__(result, name, value)
        return result

    if type(market_context) is not RetainedCurrentSamePassMarketContextV4:
        raise TypeError("industry participation v2 context invalid")
    if type(classification) not in (
        RetainedCurrentIndustrySnapshotV1,
        CurrentIndustryClassificationFailureV1,
    ):
        raise TypeError("industry participation v2 classification invalid")
    report, candidate = _admit_context(market_context)
    if type(classification) is CurrentIndustryClassificationFailureV1:
        reasons = _ordered(
            (("MARKET_REGIME_UNAVAILABLE",) if candidate is None else ())
            + _classification_failure_reasons(classification)
        )
        return failure(report, None, None, reasons)
    retained = cast(RetainedCurrentIndustrySnapshotV1, classification)
    classification_is_structurally_valid = _valid_retained_classification(retained)
    reasons = list(("MARKET_REGIME_UNAVAILABLE",) if candidate is None else ())
    if not classification_is_structurally_valid:
        reasons.append("COHORT_BINDING_MISMATCH")
    else:
        if (
            retained.known_at.astimezone(_IST).date()
            != report.decision_cutoff.astimezone(_IST).date()
        ):
            reasons.append("CLASSIFICATION_SESSION_STALE")
        if retained.known_at > report.decision_cutoff:
            reasons.append("CLASSIFICATION_FUTURE_KNOWN")
        if (
            retained.cohort_identity_sha256 != report.canonical_cohort_identity_sha256
            or retained.cohort_size != report.cohort_size
        ):
            reasons.append("COHORT_BINDING_MISMATCH")
    ordered = _ordered(tuple(reasons))
    if ordered:
        return failure(
            report,
            retained.retained_identity_sha256
            if classification_is_structurally_valid
            else None,
            retained.known_at if classification_is_structurally_valid else None,
            ordered,
        )
    if candidate is None:
        raise AssertionError("validated observed context missing direction candidate")
    industries, aggregate_reason = _aggregate(retained, candidate, report)
    if aggregate_reason is not None:
        return failure(
            report,
            retained.retained_identity_sha256,
            retained.known_at,
            (aggregate_reason,),
        )
    return observed(report, candidate, retained, industries)


def _admit_context(
    context: RetainedCurrentSamePassMarketContextV4,
) -> tuple[
    CurrentSamePassMarketRegimeReportV4,
    _CurrentSamePassMemberDirectionCandidateV4 | None,
]:
    try:
        report, candidate = cast(Any, _industry_projection_from_retained_context_v4)(
            context
        )
    except (AttributeError, TypeError, ValueError):
        raise ValueError("industry participation v2 context invalid") from None
    if type(
        report
    ) is not CurrentSamePassMarketRegimeReportV4 or not _valid_market_regime_report(
        report
    ):
        raise ValueError("industry participation v2 context invalid")
    if report.evidence_state == "INSUFFICIENT_EVIDENCE":
        return report, None
    if not _valid_candidate(candidate, context, report):
        raise ValueError("industry participation v2 context invalid")
    return report, candidate


def _valid_retained_context(context: RetainedCurrentSamePassMarketContextV4) -> bool:
    """Require V4's closure-owned minimal projection before private reduction."""
    try:
        cast(Any, _industry_projection_from_retained_context_v4)(context)
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def _valid_market_regime_report(report: CurrentSamePassMarketRegimeReportV4) -> bool:
    if (
        report.contract_version != "current-supplied-cohort-market-regime@v4"
        or report.evidence_state not in ("OBSERVED", "INSUFFICIENT_EVIDENCE")
        or not all(
            _valid_digest(value)
            for value in (
                report.schema_identity_sha256,
                report.calculation_identity_sha256,
                report.runtime_code_identity_sha256,
                report.request_identity_sha256,
                report.canonical_cohort_identity_sha256,
                report.market_data_report_identity_sha256,
                report.report_identity_sha256,
            )
        )
        or type(report.cohort_size) is not int
        or not 1 <= report.cohort_size <= 50
        or not _utc(report.decision_cutoff)
        or type(report.decision_session) is not date
        or type(report.comparison_session) is not date
    ):
        return False
    observed = report.evidence_state == "OBSERVED"
    if observed != (
        report.regime is not None
        and type(report.advances) is int
        and type(report.declines) is int
        and type(report.unchanged) is int
        and report.reasons == ()
    ):
        return False
    if observed and (
        report.advances < 0
        or report.declines < 0
        or report.unchanged < 0
        or report.advances + report.declines + report.unchanged != report.cohort_size
    ):
        return False
    if not observed and (
        report.regime is not None
        or report.advances is not None
        or report.declines is not None
        or report.unchanged is not None
        or not report.reasons
    ):
        return False
    try:
        return report.report_identity_sha256 == _object_identity_without(
            report, "report_identity_sha256"
        )
    except (TypeError, ValueError):
        return False


def _industry_value_is_exact_unsealed_v4(
    value: object,
    market_context: object,
    classification_schema_identity: str | None,
) -> bool:
    """Revalidate a V4 report/failure against its sealed V4 upstream context."""
    if type(market_context) is not RetainedCurrentSamePassMarketContextV4:
        return False
    try:
        report, candidate = _admit_context(market_context)
    except (AttributeError, TypeError, ValueError):
        return False
    expected_source_url = _admitted_classification_source_url(
        classification_schema_identity
    )
    if type(value) is CurrentIndustryParticipationReportV4:
        if candidate is None or (
            value.contract_version != CONTRACT_VERSION
            or value.schema_identity_sha256 != SCHEMA_IDENTITY_SHA256
            or value.calculation_identity_sha256 != CALCULATION_IDENTITY_SHA256
            or value.runtime_code_identity_sha256 != _RUNTIME_CODE_IDENTITY
            or value.evidence_state != "OBSERVED"
            or value.market_regime_report_identity_sha256
            != report.report_identity_sha256
            or value.direction_candidate_identity_sha256
            != candidate.direction_candidate_identity_sha256
            or value.canonical_cohort_identity_sha256
            != report.canonical_cohort_identity_sha256
            or value.cohort_size != report.cohort_size
            or value.decision_session != report.decision_session
            or value.comparison_session != report.comparison_session
            or value.decision_cutoff != report.decision_cutoff
            or value.source_url != expected_source_url
            or value.source_attribution != "NSE_INDICES"
            or value.classification_tier != "INDUSTRY"
            or value.publisher_published_at is not None
            or value.publisher_effective_from is not None
            or value.publisher_effective_through is not None
            or value.publisher_revision is not None
            or not _utc(value.known_at)
            or value.known_at > report.decision_cutoff
            or value.reasons != ()
            or type(value.industries) is not tuple
            or not 1 <= len(value.industries) <= value.cohort_size
            or not all(
                _valid_digest(item)
                for item in (
                    value.classification_input_identity_sha256,
                    value.artifact_sha256,
                    value.snapshot_identity_sha256,
                    value.archive_identity_sha256,
                    value.archive_receipt_identity_sha256,
                    value.retained_classification_identity_sha256,
                    value.report_identity_sha256,
                )
            )
            or value.artifact_revision != f"sha256:{value.artifact_sha256}"
        ):
            return False
        rows = value.industries
        if (
            tuple(row.industry for row in rows)
            != tuple(sorted(row.industry for row in rows))
            or len({row.industry for row in rows}) != len(rows)
            or any(
                type(row) is not CurrentIndustryCountV4
                or not _industry(row.industry)
                or not all(
                    type(number) is int and 0 <= number <= value.cohort_size
                    for number in (
                        row.member_count,
                        row.advances,
                        row.declines,
                        row.unchanged,
                    )
                )
                or row.advances + row.declines + row.unchanged != row.member_count
                or row.row_identity_sha256
                != _identity(
                    {
                        "advances": row.advances,
                        "declines": row.declines,
                        "industry": row.industry,
                        "member_count": row.member_count,
                        "unchanged": row.unchanged,
                    }
                )
                for row in rows
            )
            or (
                sum(row.member_count for row in rows),
                sum(row.advances for row in rows),
                sum(row.declines for row in rows),
                sum(row.unchanged for row in rows),
            )
            != (report.cohort_size, report.advances, report.declines, report.unchanged)
        ):
            return False
        return value.report_identity_sha256 == _object_identity_without(
            value, "report_identity_sha256", "_reducer_seal"
        )
    if type(value) is CurrentIndustryParticipationFailureV4:
        try:
            reasons = _ordered(value.reasons)
            state = _state(reasons)
        except (TypeError, ValueError):
            return False
        return (
            bool(reasons)
            and value.contract_version == _FAILURE_CONTRACT_VERSION
            and value.evidence_state == state
            and value.canonical_cohort_identity_sha256
            == report.canonical_cohort_identity_sha256
            and value.cohort_size == report.cohort_size
            and value.decision_session == report.decision_session
            and value.decision_cutoff == report.decision_cutoff
            and value.market_regime_report_identity_sha256
            == report.report_identity_sha256
            and value.industries is None
            and (
                value.classification_identity_sha256 is None
                or _valid_digest(value.classification_identity_sha256)
            )
            and (
                value.known_at is None
                or (
                    _utc(value.known_at)
                    and (
                        value.known_at <= report.decision_cutoff
                        or (
                            value.evidence_state == "INSUFFICIENT_EVIDENCE"
                            and "CLASSIFICATION_FUTURE_KNOWN" in reasons
                        )
                    )
                )
            )
            and value.failure_identity_sha256
            == _object_identity_without(
                value, "failure_identity_sha256", "_reducer_seal"
            )
        )
    return False


def _valid_candidate(
    candidate: _CurrentSamePassMemberDirectionCandidateV4 | None,
    context: RetainedCurrentSamePassMarketContextV4,
    report: CurrentSamePassMarketRegimeReportV4,
) -> bool:
    if candidate is None or (
        not all(
            _valid_digest(value)
            for value in (
                candidate.request_identity_sha256,
                candidate.raw_grid_identity_sha256,
                candidate.corporate_action_screen_identity_sha256,
                candidate.adjusted_handoff_identity_sha256,
                candidate.market_regime_report_identity_sha256,
                candidate.canonical_cohort_identity_sha256,
                candidate.schedule_identity_sha256,
                candidate.direction_candidate_identity_sha256,
            )
        )
        or type(candidate.apply_adjustment) is not bool
        or candidate.price_basis
        != price_basis_for_adjustment(candidate.apply_adjustment)
        or not _utc(candidate.decision_cutoff)
        or candidate.request_identity_sha256 != report.request_identity_sha256
        or candidate.market_regime_report_identity_sha256
        != report.report_identity_sha256
        or candidate.canonical_cohort_identity_sha256
        != report.canonical_cohort_identity_sha256
        or candidate.decision_cutoff != report.decision_cutoff
        or type(candidate.rows) is not tuple
        or len(candidate.rows) != report.cohort_size
    ):
        return False
    if context.context_identity_sha256 == candidate.direction_candidate_identity_sha256:
        return False
    rows = candidate.rows
    if (
        context.market_data_report.rows is None
        or tuple(row.isin for row in rows)
        != tuple(row.isin for row in context.market_data_report.rows)
        or len({(row.isin, row.exchange, row.effective_symbol) for row in rows})
        != len(rows)
        or any(not _valid_direction_row(row) for row in rows)
    ):
        return False
    candidate_value = {
        "adjusted_handoff_identity_sha256": candidate.adjusted_handoff_identity_sha256,
        "canonical_cohort_identity_sha256": candidate.canonical_cohort_identity_sha256,
        "corporate_action_screen_identity_sha256": candidate.corporate_action_screen_identity_sha256,
        "decision_cutoff": _instant(candidate.decision_cutoff),
        "market_regime_report_identity_sha256": candidate.market_regime_report_identity_sha256,
        "raw_grid_identity_sha256": candidate.raw_grid_identity_sha256,
        "request_identity_sha256": candidate.request_identity_sha256,
        "schedule_identity_sha256": candidate.schedule_identity_sha256,
        "apply_adjustment": candidate.apply_adjustment,
        "price_basis": candidate.price_basis,
        "rows": [
            {
                "direction": row.direction,
                "effective_symbol": row.effective_symbol,
                "exchange": row.exchange,
                "isin": row.isin,
                "row_identity_sha256": row.row_identity_sha256,
            }
            for row in rows
        ],
    }
    if candidate.direction_candidate_identity_sha256 != _identity(candidate_value):
        return False
    return (
        sum(row.direction == "ADVANCE" for row in rows) == report.advances
        and sum(row.direction == "DECLINE" for row in rows) == report.declines
        and sum(row.direction == "UNCHANGED" for row in rows) == report.unchanged
    )


def _valid_direction_row(row: object) -> bool:
    if type(row) is not _CurrentSamePassMemberDirectionRowV4:
        return False
    if (
        row.exchange != "NSE"
        or row.direction not in ("ADVANCE", "DECLINE", "UNCHANGED")
        or not _valid_isin(row.isin)
        or not _field(row.effective_symbol)
        or not _valid_digest(row.row_identity_sha256)
    ):
        return False
    return row.row_identity_sha256 == _identity(
        {
            "direction": row.direction,
            "effective_symbol": row.effective_symbol,
            "exchange": row.exchange,
            "isin": row.isin,
        }
    )


def _classification_failure_reasons(
    classification: CurrentIndustryClassificationFailureV1,
) -> tuple[str, ...]:
    reasons = _ordered(classification.reasons)
    if classification.evidence_state != _state(reasons) or not reasons:
        raise ValueError("industry participation v2 classification invalid")
    return reasons


def _valid_retained_classification(value: RetainedCurrentIndustrySnapshotV1) -> bool:
    rows = getattr(value, "_private_rows", None)
    if (
        not _archive_minted_retained(value)
        or value.evidence_state != "RETAINED"
        or value.schema_identity_sha256 not in _CLASSIFICATION_SCHEMA_IDENTITIES
        or not all(
            _valid_digest(item)
            for item in (
                value.input_identity_sha256,
                value.artifact_sha256,
                value.snapshot_identity_sha256,
                value.archive_identity_sha256,
                value.archive_receipt_identity_sha256,
                value.retained_identity_sha256,
                value.snapshot_runtime_code_identity_sha256,
                value.cohort_identity_sha256,
            )
        )
        or value.artifact_revision != f"sha256:{value.artifact_sha256}"
        or type(value.cohort_size) is not int
        or not 1 <= value.cohort_size <= 50
        or any(
            item is not None
            for item in (
                value.publisher_published_at,
                value.publisher_effective_from,
                value.publisher_effective_through,
                value.publisher_revision,
            )
        )
        or not _utc(value.known_at)
        or type(rows) is not tuple
        or len(rows) != value.cohort_size
        or tuple(row.isin for row in rows) != tuple(sorted(row.isin for row in rows))
        or len({(row.isin, row.exchange, row.effective_symbol) for row in rows})
        != value.cohort_size
        or not _identity_labels_safe(rows)
        or any(
            type(row) is not _PrivateIndustryRow
            or getattr(row, "_seal", None) is not _PARSED_SEAL
            or row.exchange != "NSE"
            or row.effective_symbol != row.symbol
            or not _valid_isin(row.isin)
            or not _industry(row.industry)
            or not _field(row.symbol)
            for row in rows
        )
    ):
        return False
    return _retained_classification_identity_matches(value, rows)


def _retained_classification_identity_matches(
    value: RetainedCurrentIndustrySnapshotV1,
    rows: tuple[_PrivateIndustryRow, ...],
) -> bool:
    snapshot = {
        "artifact_sha256": value.artifact_sha256,
        "artifact_revision": value.artifact_revision,
        "cohort_identity_sha256": value.cohort_identity_sha256,
        "cohort_size": value.cohort_size,
        "evidence_state": "PROJECTED",
        "input_identity_sha256": value.input_identity_sha256,
        "private_rows": [
            {
                "effective_symbol": row.effective_symbol,
                "exchange": row.exchange,
                "industry": row.industry,
                "isin": row.isin,
                "symbol": row.symbol,
            }
            for row in rows
        ],
        "runtime_code_identity_sha256": value.snapshot_runtime_code_identity_sha256,
        "schema_identity_sha256": value.schema_identity_sha256,
    }
    archive_identity = _identity(
        {
            "raw_artifact_sha256": value.artifact_sha256,
            "snapshot_identity_sha256": value.snapshot_identity_sha256,
        }
    )
    receipt = _identity(
        {
            "archive_identity_sha256": archive_identity,
            "artifact_sha256": value.artifact_sha256,
            "input_identity_sha256": value.input_identity_sha256,
            "known_at": _instant(value.known_at),
            "snapshot_identity_sha256": value.snapshot_identity_sha256,
        }
    )
    retained = {
        "archive_identity_sha256": value.archive_identity_sha256,
        "archive_receipt_identity_sha256": value.archive_receipt_identity_sha256,
        "artifact_revision": value.artifact_revision,
        "artifact_sha256": value.artifact_sha256,
        "cohort_identity_sha256": value.cohort_identity_sha256,
        "cohort_size": value.cohort_size,
        "evidence_state": "RETAINED",
        "input_identity_sha256": value.input_identity_sha256,
        "known_at": _instant(value.known_at),
        "publisher_effective_from": None,
        "publisher_effective_through": None,
        "publisher_published_at": None,
        "publisher_revision": None,
        "schema_identity_sha256": value.schema_identity_sha256,
        "snapshot_identity_sha256": value.snapshot_identity_sha256,
        "snapshot_runtime_code_identity_sha256": value.snapshot_runtime_code_identity_sha256,
    }
    return (
        value.snapshot_identity_sha256 == _identity(snapshot)
        and value.archive_identity_sha256 == archive_identity
        and value.archive_receipt_identity_sha256 == receipt
        and value.retained_identity_sha256 == _identity(retained)
    )


def _aggregate(
    retained: RetainedCurrentIndustrySnapshotV1,
    candidate: _CurrentSamePassMemberDirectionCandidateV4,
    report: CurrentSamePassMarketRegimeReportV4,
) -> tuple[tuple[CurrentIndustryCountV4, ...], str | None]:
    classifications = {
        (row.isin, row.exchange, row.effective_symbol): row.industry
        for row in cast(tuple[_PrivateIndustryRow, ...], retained._private_rows)  # pyright: ignore[reportPrivateUsage]
    }
    directions = {
        (row.isin, row.exchange, row.effective_symbol): row.direction
        for row in candidate.rows
    }
    if len(classifications) != retained.cohort_size or set(classifications) != set(
        directions
    ):
        return (), "MEMBER_IDENTITY_MISMATCH"
    totals: dict[str, list[int]] = {}
    for identity, direction in directions.items():
        values = totals.setdefault(classifications[identity], [0, 0, 0, 0])
        values[0] += 1
        values[{"ADVANCE": 1, "DECLINE": 2, "UNCHANGED": 3}[direction]] += 1
    industries = tuple(
        _industry_row(industry, *totals[industry]) for industry in sorted(totals)
    )
    if (
        sum(row.member_count for row in industries),
        sum(row.advances for row in industries),
        sum(row.declines for row in industries),
        sum(row.unchanged for row in industries),
    ) != (report.cohort_size, report.advances, report.declines, report.unchanged):
        return (), "COHORT_BINDING_MISMATCH"
    return industries, None


def _industry_row(
    industry: str, member_count: int, advances: int, declines: int, unchanged: int
) -> CurrentIndustryCountV4:
    value = {
        "advances": advances,
        "declines": declines,
        "industry": industry,
        "member_count": member_count,
        "unchanged": unchanged,
    }
    return CurrentIndustryCountV4(
        industry, member_count, advances, declines, unchanged, _identity(value)
    )


def _ordered(reasons: tuple[str, ...]) -> tuple[str, ...]:
    if (
        type(reasons) is not tuple
        or len(reasons) > len(_REASON_ORDER)
        or any(
            type(reason) is not str or reason not in _REASON_ORDER for reason in reasons
        )
    ):
        raise ValueError("industry participation v2 reasons invalid")
    return tuple(reason for reason in _REASON_ORDER if reason in reasons)


def _state(
    reasons: tuple[str, ...],
) -> Literal["MALFORMED_EVIDENCE", "UNSUPPORTED_CAPABILITY", "INSUFFICIENT_EVIDENCE"]:
    if any(reason in _MALFORMED_REASONS for reason in reasons):
        return "MALFORMED_EVIDENCE"
    if any(reason in _UNSUPPORTED_REASONS for reason in reasons):
        return "UNSUPPORTED_CAPABILITY"
    if any(reason in _INSUFFICIENT_REASONS for reason in reasons):
        return "INSUFFICIENT_EVIDENCE"
    raise ValueError("industry participation v2 reasons invalid")


def _sealed_industry_boundary() -> tuple[object, object]:  # noqa: C901
    """Create the reducer-owned authority for nonserializable Plan-27 evidence."""
    minted_seals: set[object] = set()

    @dataclass(frozen=True, slots=True)
    class _ReducerBinding:
        result: (
            CurrentIndustryParticipationReportV4 | CurrentIndustryParticipationFailureV4
        )
        context_identity_sha256: str
        result_sha256: str
        classification_identity_sha256: str | None
        classification_schema_identity_sha256: str | None

    bindings: dict[object, _ReducerBinding] = {}

    @dataclass(frozen=True, slots=True, init=False, repr=False, eq=False)
    class ReducerSeal:
        def __init__(self, *_: object, **__: object) -> None:
            raise TypeError("industry reducer seals are closure-minted only")

    def minted(seal: object) -> bool:
        return any(item is seal for item in minted_seals)

    def seal(
        result: CurrentIndustryParticipationReportV4
        | CurrentIndustryParticipationFailureV4,
        market_context: RetainedCurrentSamePassMarketContextV4,
        classification: (
            RetainedCurrentIndustrySnapshotV1 | CurrentIndustryClassificationFailureV1
        ),
    ) -> CurrentIndustryParticipationReportV4 | CurrentIndustryParticipationFailureV4:
        copy = object.__new__(type(result))
        local_seal = object.__new__(ReducerSeal)
        minted_seals.add(local_seal)
        classification_identity = (
            result.retained_classification_identity_sha256
            if type(result) is CurrentIndustryParticipationReportV4
            else result.classification_identity_sha256
        )
        classification_schema_identity = (
            classification.schema_identity_sha256
            if type(classification) is RetainedCurrentIndustrySnapshotV1
            else None
        )
        for item in fields(type(result)):
            if item.name != "_reducer_seal":
                object.__setattr__(copy, item.name, getattr(result, item.name))
        object.__setattr__(copy, "_reducer_seal", local_seal)
        bindings[local_seal] = _ReducerBinding(
            copy,
            market_context.retained_context_identity_sha256,
            _sha(copy.canonical_json_bytes()),
            classification_identity,
            classification_schema_identity,
        )
        return copy

    def reduce(
        market_context: RetainedCurrentSamePassMarketContextV4,
        classification: RetainedCurrentIndustrySnapshotV1
        | CurrentIndustryClassificationFailureV1,
    ) -> CurrentIndustryParticipationReportV4 | CurrentIndustryParticipationFailureV4:
        return seal(
            _reduce_current_industry_participation_unsealed_v4(
                market_context, classification
            ),
            market_context,
            classification,
        )

    def exact(value: object, market_context: object) -> bool:
        if type(value) not in {
            CurrentIndustryParticipationReportV4,
            CurrentIndustryParticipationFailureV4,
        }:
            return False
        seal_value = value._reducer_seal
        binding = bindings.get(seal_value)
        classification_identity = (
            value.retained_classification_identity_sha256
            if type(value) is CurrentIndustryParticipationReportV4
            else value.classification_identity_sha256
        )
        return (
            type(seal_value) is ReducerSeal
            and minted(seal_value)
            and binding is not None
            and binding.result is value
            and binding.result_sha256 == _sha(value.canonical_json_bytes())
            and binding.classification_identity_sha256 == classification_identity
            and binding.context_identity_sha256
            == getattr(market_context, "retained_context_identity_sha256", None)
            and _industry_value_is_exact_unsealed_v4(
                value,
                market_context,
                binding.classification_schema_identity_sha256,
            )
        )

    return reduce, exact


(
    reduce_current_industry_participation_v4,
    current_industry_participation_is_exact_valid_v4,
) = _sealed_industry_boundary()


def _utc(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is UTC
