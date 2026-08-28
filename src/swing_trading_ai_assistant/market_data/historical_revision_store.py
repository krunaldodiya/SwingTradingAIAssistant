"""Strict local immutable storage for fixed-cohort historical daily OHLCV V1."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from contextlib import ExitStack, suppress
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, cast
from uuid import uuid4

from .runtime_source_verifier import runtime_source_sha256
from .storage_root_lease import (
    LeaseFailureCode,
    LeaseOutcome,
    LeaseResult,
    StorageRootLease,
)

_CONTRACT_VERSION: Final = "fixed-cohort-historical-ohlcv-revision-store@v1"
_SCOPE: Final = "FIXED_COHORT_RETROSPECTIVE"
_INTERVAL: Final = "1d"
_PRICE_BASIS: Final = "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED"
_PERMITTED_USE: Final = "OWNER_PRIVATE_RESEARCH"
_MAPPING_PROVIDER: Final = "OPERATOR_LOCAL_IMPORT"
_ROOT_DIRECTORY: Final = "historical_ohlcv_revisions"
_SCHEMA_DIRECTORY: Final = "v1"
_OBJECT_DIRECTORY: Final = "objects"
_REVISION_DIRECTORY: Final = "revisions"
_RUNTIME_SOURCE: Final = (
    "src/swing_trading_ai_assistant/market_data/historical_revision_store.py"
)
_DIGEST_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
_ISIN_RE: Final = re.compile(r"[A-Z0-9]{12}\Z")
_SAFE_TEXT_RE: Final = re.compile(r"[ -~]{1,64}\Z")
_LIMITS: Final = {
    "max_members": 50,
    "max_sessions": 10_000,
    "max_rows": 500_000,
    "max_artifact_bytes": 134_217_728,
    "max_source_policy_bytes": 1_048_576,
    "max_receipt_bytes": 1_048_576,
    "max_revision_bytes": 134_217_728,
    "max_lineage_depth": 128,
}
_OPERATION_LITERALS: Final = ("APPEND", "CORRECTION", "INITIAL")
_CORRECTION_MUTABLE_FIELDS: Final = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "known_at",
)
_DIRECTORY_MODE: Final = 0o700
_INGESTION_LOCK_NAME: Final = ".ingestion.lock"
_INGESTION_LOCK_MODE: Final = 0o600
_JSON_MAX_DEPTH: Final = 64
_IMMUTABLE_FILE_MODE: Final = 0o400
_SCHEDULE_SCHEMA_VERSION: Final = "fixed-cohort-historical-ohlcv-schedule@v1"
_REQUEST_FIELDS: Final = (
    "contract_version",
    "research_scope",
    "operation",
    "parent_revision_sha256",
    "correction_coordinates",
    "cohort",
    "from_session",
    "to_session",
    "interval",
    "expected_sessions",
    "schedule_evidence_sha256",
    "source_policy_sha256",
    "source_artifact_sha256",
    "receipt_sha256",
    "acquired_at",
    "known_at_cutoff",
    "permitted_use",
    "price_basis",
    "schema_identity_sha256",
    "runtime_code_identity_sha256",
    "configuration_identity_sha256",
    "limits",
)
_REVISION_FIELDS: Final = frozenset(
    {
        *_REQUEST_FIELDS,
        "request_identity_sha256",
        "lineage_depth",
        "context_status",
        "limitation",
        "bars",
        "revision_sha256",
    }
)


def _complete_schema_identity_preimage(
    preimage: dict[str, Any],
) -> dict[str, Any]:
    """State every leaf's closed contract fields in the hashed metadata."""
    objects = cast(dict[str, dict[str, Any]], preimage["objects"])
    request_fields = cast(
        dict[str, dict[str, Any]],
        objects["FixedCohortHistoricalOhlcvRequestV1"]["field_contracts"],
    )
    revision_fields = cast(
        dict[str, dict[str, Any]],
        objects["HistoricalOhlcvRevisionV1"]["field_contracts"],
    )
    revision_fields.update(
        {field: deepcopy(request_fields[field]) for field in _REQUEST_FIELDS}
    )
    for object_contract in objects.values():
        field_contracts = cast(
            dict[str, dict[str, Any]], object_contract["field_contracts"]
        )
        for field_contract in field_contracts.values():
            field_contract.setdefault("nullable", False)
            field_contract.setdefault(
                "bounds",
                {
                    name: field_contract[name]
                    for name in (
                        "exclusive_minimum",
                        "minimum",
                        "maximum",
                        "minimum_items",
                        "maximum_items",
                    )
                    if name in field_contract
                }
                or None,
            )
            field_contract.setdefault("literal", None)
            field_contract.setdefault("literals", None)
            field_contract.setdefault("ordering", None)
    return preimage


_SCHEMA_IDENTITY_PREIMAGE: Final = _complete_schema_identity_preimage(
    {
        "metadata_version": "fixed-cohort-historical-ohlcv-schema-identity@v1",
        "canonical_json": {
            "encoding": "UTF-8",
            "root": "object",
            "unique_string_keys": True,
            "sorted_keys": True,
            "separators": [",", ":"],
            "floats": "rejected",
            "json_constants": "rejected",
            "received_bytes": "equal_canonical_encoding",
            "unknown_fields": "rejected",
            "integers": "built_in_only",
            "maximum_depth": "configuration.json_max_depth",
            "container_depth": {
                "counted_containers": ["object", "list"],
                "scalar_depth_effect": "none",
                "maximum_accepted": _JSON_MAX_DEPTH,
                "first_rejected": _JSON_MAX_DEPTH + 1,
            },
        },
        "scalar_types": {
            "Sha256": {"grammar": "lowercase [0-9a-f]{64}", "nullable": False},
            "ISIN": {"grammar": "uppercase [A-Z0-9]{12}", "nullable": False},
            "SafeAscii64": {
                "grammar": "printable ASCII [ -~]{1,64}",
                "nullable": False,
            },
            "Date": {"grammar": "exact ISO YYYY-MM-DD round trip", "nullable": False},
            "UtcInstant": {
                "grammar": "exact YYYY-MM-DDTHH:MM:SSZ",
                "nullable": False,
            },
            "CanonicalDecimal": {
                "grammar": "no sign/exponent/leading-zero/insignificant-trailing-zero",
                "nullable": False,
            },
            "PositiveDecimal": {
                "base": "CanonicalDecimal",
                "finite": True,
                "exclusive_minimum": "0",
            },
            "VolumeDecimal": {
                "base": "CanonicalDecimal",
                "finite": True,
                "minimum": "0",
                "integral": True,
            },
            "BuiltInInteger": {
                "grammar": "type(value) is int excluding bool",
                "nullable": False,
            },
        },
        "objects": {
            "ProviderMappingV1": {
                "fields": [
                    "provider",
                    "provider_instrument_id",
                    "mapping_effective_from",
                    "mapping_effective_to",
                    "mapping_evidence_sha256",
                ],
                "field_contracts": {
                    "provider": {"type": "SafeAscii64", "literal": _MAPPING_PROVIDER},
                    "provider_instrument_id": {"type": "SafeAscii64"},
                    "mapping_effective_from": {"type": "Date"},
                    "mapping_effective_to": {
                        "type": "Date",
                        "nullable": True,
                        "ordering": "not before mapping_effective_from",
                    },
                    "mapping_evidence_sha256": {"type": "Sha256"},
                },
                "unknown_fields": "rejected",
            },
            "CanonicalListedEquityMemberV1": {
                "fields": [
                    "isin",
                    "exchange",
                    "listed_equity_segment",
                    "effective_symbol",
                    "symbol_effective_from",
                    "symbol_effective_to",
                    "provider_mapping",
                ],
                "field_contracts": {
                    "isin": {"type": "ISIN"},
                    "exchange": {"type": "literal", "literal": "NSE"},
                    "listed_equity_segment": {"type": "literal", "literal": "EQUITY"},
                    "effective_symbol": {"type": "SafeAscii64"},
                    "symbol_effective_from": {"type": "Date"},
                    "symbol_effective_to": {
                        "type": "Date",
                        "nullable": True,
                        "ordering": "not before symbol_effective_from",
                    },
                    "provider_mapping": {"type": "ProviderMappingV1"},
                },
                "ordering": "cohort sorted unique by isin/exchange",
                "unknown_fields": "rejected",
            },
            "CorrectionCoordinateV1": {
                "fields": ["isin", "exchange", "session"],
                "field_contracts": {
                    "isin": {"type": "ISIN"},
                    "exchange": {"type": "literal", "literal": "NSE"},
                    "session": {
                        "type": "Date",
                        "cross_reference": "candidate full-grid and CORRECTION parent row",
                    },
                },
                "ordering": "strictly sorted unique for CORRECTION",
                "unknown_fields": "rejected",
            },
            "LimitsV1": {
                "fields": list(_LIMITS),
                "field_contracts": {
                    name: {"type": "BuiltInInteger", "literal": value}
                    for name, value in _LIMITS.items()
                },
                "unknown_fields": "rejected",
            },
            "FixedCohortHistoricalOhlcvRequestV1": {
                "fields": list(_REQUEST_FIELDS),
                "field_contracts": {
                    "contract_version": {
                        "type": "literal",
                        "literal": _CONTRACT_VERSION,
                    },
                    "research_scope": {"type": "literal", "literal": _SCOPE},
                    "operation": {
                        "type": "enum",
                        "literals": list(_OPERATION_LITERALS),
                    },
                    "parent_revision_sha256": {"type": "Sha256", "nullable": True},
                    "correction_coordinates": {
                        "type": "list CorrectionCoordinateV1",
                        "operation_grammar": "INITIAL/APPEND empty; CORRECTION nonempty sorted unique",
                    },
                    "cohort": {
                        "type": "list CanonicalListedEquityMemberV1",
                        "minimum_items": 1,
                        "maximum_items": _LIMITS["max_members"],
                        "ordering": "strict unique isin/exchange",
                    },
                    "from_session": {"type": "Date"},
                    "to_session": {
                        "type": "Date",
                        "ordering": "not before from_session",
                    },
                    "interval": {"type": "literal", "literal": _INTERVAL},
                    "expected_sessions": {
                        "type": "list Date",
                        "minimum_items": 1,
                        "maximum_items": _LIMITS["max_sessions"],
                        "ordering": "strict increasing within from/to",
                    },
                    "schedule_evidence_sha256": {
                        "type": "Sha256",
                        "identity": "ScheduleIdentityPreimageV1",
                    },
                    "source_policy_sha256": {"type": "Sha256"},
                    "source_artifact_sha256": {"type": "Sha256"},
                    "receipt_sha256": {"type": "Sha256"},
                    "acquired_at": {"type": "UtcInstant"},
                    "known_at_cutoff": {
                        "type": "UtcInstant",
                        "ordering": "not before acquired_at",
                    },
                    "permitted_use": {"type": "literal", "literal": _PERMITTED_USE},
                    "price_basis": {"type": "literal", "literal": _PRICE_BASIS},
                    "schema_identity_sha256": {"type": "Sha256", "identity": "schema"},
                    "runtime_code_identity_sha256": {
                        "type": "Sha256",
                        "identity": "loaded runtime",
                    },
                    "configuration_identity_sha256": {
                        "type": "Sha256",
                        "identity": "configuration",
                    },
                    "limits": {"type": "LimitsV1"},
                },
                "unknown_fields": "rejected",
            },
            "SourcePolicyV1": {
                "fields": [
                    "schema_version",
                    "source_name",
                    "permitted_use",
                    "ohlcv_adjustment_semantics",
                    "artifact_sha256",
                ],
                "field_contracts": {
                    "schema_version": {
                        "type": "literal",
                        "literal": "operator-local-historical-ohlcv-source-policy@v1",
                    },
                    "source_name": {"type": "SafeAscii64"},
                    "permitted_use": {"type": "literal", "literal": _PERMITTED_USE},
                    "ohlcv_adjustment_semantics": {
                        "type": "literal",
                        "literal": _PRICE_BASIS,
                    },
                    "artifact_sha256": {
                        "type": "Sha256",
                        "cross_reference": "request source_artifact_sha256",
                    },
                },
                "unknown_fields": "rejected",
            },
            "ReceiptV1": {
                "fields": [
                    "schema_version",
                    "source_policy_sha256",
                    "source_artifact_sha256",
                    "acquired_at",
                    "known_at",
                    "permitted_use",
                    "ohlcv_adjustment_semantics",
                ],
                "field_contracts": {
                    "schema_version": {
                        "type": "literal",
                        "literal": "operator-local-historical-ohlcv-receipt@v1",
                    },
                    "source_policy_sha256": {
                        "type": "Sha256",
                        "cross_reference": "request source_policy_sha256",
                    },
                    "source_artifact_sha256": {
                        "type": "Sha256",
                        "cross_reference": "request source_artifact_sha256",
                    },
                    "acquired_at": {
                        "type": "UtcInstant",
                        "cross_reference": "request acquired_at",
                    },
                    "known_at": {
                        "type": "UtcInstant",
                        "ordering": "not after request known_at_cutoff",
                    },
                    "permitted_use": {"type": "literal", "literal": _PERMITTED_USE},
                    "ohlcv_adjustment_semantics": {
                        "type": "literal",
                        "literal": _PRICE_BASIS,
                    },
                },
                "unknown_fields": "rejected",
            },
            "HistoricalOhlcvBarV1": {
                "fields": [
                    "isin",
                    "exchange",
                    "session",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "known_at",
                    "price_basis",
                ],
                "field_contracts": {
                    "isin": {"type": "ISIN", "cross_reference": "cohort"},
                    "exchange": {"type": "literal", "literal": "NSE"},
                    "session": {"type": "Date", "cross_reference": "expected_sessions"},
                    "open": {"type": "PositiveDecimal"},
                    "high": {"type": "PositiveDecimal"},
                    "low": {"type": "PositiveDecimal"},
                    "close": {"type": "PositiveDecimal"},
                    "volume": {"type": "VolumeDecimal"},
                    "known_at": {
                        "type": "UtcInstant",
                        "ordering": "not after known_at_cutoff",
                    },
                    "price_basis": {"type": "literal", "literal": _PRICE_BASIS},
                },
                "ordering": "member-major/session-major exact grid",
                "invariants": ["low <= min(open, close) <= max(open, close) <= high"],
                "unknown_fields": "rejected",
            },
            "SourceArtifactV1": {
                "fields": ["schema_version", "bars"],
                "field_contracts": {
                    "schema_version": {
                        "type": "literal",
                        "literal": "operator-local-historical-ohlcv-artifact@v1",
                    },
                    "bars": {
                        "type": "list HistoricalOhlcvBarV1",
                        "maximum_items": _LIMITS["max_rows"],
                    },
                },
                "unknown_fields": "rejected",
            },
            "ScheduleIdentityPreimageV1": {
                "fields": [
                    "schema_version",
                    "from_session",
                    "to_session",
                    "expected_sessions",
                ],
                "field_contracts": {
                    "schema_version": {
                        "type": "literal",
                        "literal": _SCHEDULE_SCHEMA_VERSION,
                    },
                    "from_session": {"type": "Date"},
                    "to_session": {"type": "Date"},
                    "expected_sessions": {"type": "list Date"},
                },
                "unknown_fields": "rejected",
            },
            "HistoricalOhlcvRevisionV1": {
                "fields": sorted(_REVISION_FIELDS),
                "field_contracts": {
                    **{
                        field: {
                            "type": "request projection",
                            "source_field": field,
                        }
                        for field in _REQUEST_FIELDS
                    },
                    "request_identity_sha256": {
                        "type": "Sha256",
                        "identity": "canonical complete request projection",
                    },
                    "lineage_depth": {
                        "type": "BuiltInInteger",
                        "minimum": 0,
                        "maximum": _LIMITS["max_lineage_depth"],
                    },
                    "context_status": {
                        "type": "literal",
                        "literal": "HISTORICAL_CONTEXT_NOT_EVALUATED",
                    },
                    "limitation": {
                        "type": "literal",
                        "literal": "FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION",
                    },
                    "bars": {"type": "list HistoricalOhlcvBarV1"},
                    "revision_sha256": {
                        "type": "Sha256",
                        "identity": "canonical revision excluding revision_sha256",
                    },
                },
                "unknown_fields": "rejected",
            },
        },
        "identity_preimages": {
            "schedule": {
                "algorithm": "SHA-256",
                "canonical_object": "ScheduleIdentityPreimageV1",
            },
            "request": {
                "algorithm": "SHA-256",
                "canonical_object": "complete FixedCohortHistoricalOhlcvRequestV1",
            },
            "schema": {"algorithm": "SHA-256", "canonical_object": "this metadata"},
            "runtime": {
                "algorithm": "SHA-256",
                "formula": "runtime_source_sha256(_RUNTIME_SOURCE) at module load",
                "source": _RUNTIME_SOURCE,
                "mutable_path_read": "never",
            },
            "configuration": {
                "algorithm": "SHA-256",
                "canonical_object": "configuration metadata",
            },
            "source": {
                "algorithm": "SHA-256",
                "inputs": "exact source policy/artifact/receipt bytes",
            },
            "revision": {
                "algorithm": "SHA-256",
                "canonical_object": "revision excluding revision_sha256",
            },
        },
        "state_transitions": {
            "INITIAL": {
                "parent_revision_sha256": "null",
                "correction_coordinates": "empty",
                "candidate_grid": "complete full grid",
                "existing_root": "identity-pinned exact readable candidate replay only",
                "lineage_depth": 0,
            },
            "APPEND": {
                "parent": "exact readable compatible V1 parent",
                "parent_revision_sha256": "Sha256",
                "correction_coordinates": "empty",
                "expected_sessions": "nonempty strict suffix after exact parent sequence and parent inclusive to_session",
                "to_session": "not before parent inclusive to_session and at or after final expected session; inclusive upper bound may be non-session",
                "bars": "parent canonical preservation plus suffix rows only",
                "lineage_depth": "parent depth plus one through configured maximum",
            },
            "CORRECTION": {
                "parent": "exact readable compatible V1 parent",
                "parent_revision_sha256": "Sha256",
                "expected_sessions": "exact parent sequence",
                "coordinates": "nonempty sorted unique candidate full-grid coordinates",
                "unnamed_rows": "canonically identical to parent",
                "named_rows": "differ in at least one and only mutable fields",
                "mutable_fields": list(_CORRECTION_MUTABLE_FIELDS),
                "lineage_depth": "parent depth plus one through configured maximum",
            },
        },
        "cross_object_invariants": [
            "all request source digests equal exact retained bytes",
            "revision filename embedded and recomputed identities equal",
            "historical identity values are syntactic and never compared to current",
            "INITIAL null parent and empty corrections",
            "APPEND digest parent, empty corrections, contiguous suffix strictly after parent inclusive upper range, parent preservation",
            "CORRECTION digest parent, named sorted unique changes only",
            "lineage is acyclic and increases by one through depth limit",
            "no partial bars or parent fallback on failure",
            "stored read corruption maps to publication uncertainty",
            "invalid import parent maps to parent lineage conflict",
        ],
        "failure_grammar": {
            "outcomes": [
                "MALFORMED_INPUT",
                "UNSUPPORTED_CAPABILITY",
                "INVALID_EVIDENCE",
                "PARENT_LINEAGE_CONFLICT",
                "PUBLICATION_UNCERTAIN_OR_CONFLICT",
                "SUCCESS",
            ],
            "passes": [
                "MALFORMED_STRUCTURE",
                "UNSUPPORTED_PROFILE",
                "INVALID_EVIDENCE",
                "PARENT_LINEAGE",
                "STORAGE",
            ],
        },
    }
)
_CONFIGURATION_IDENTITY_PREIMAGE: Final = {
    "metadata_version": "fixed-cohort-historical-ohlcv-configuration-identity@v1",
    "contract_version": _CONTRACT_VERSION,
    "research_scope": _SCOPE,
    "interval": _INTERVAL,
    "operation_literals": list(_OPERATION_LITERALS),
    "exchange": "NSE",
    "listed_equity_segment": "EQUITY",
    "mapping_provider": _MAPPING_PROVIDER,
    "permitted_use": _PERMITTED_USE,
    "price_basis": _PRICE_BASIS,
    "schedule_schema_version": _SCHEDULE_SCHEMA_VERSION,
    "source_schema_versions": {
        "policy": "operator-local-historical-ohlcv-source-policy@v1",
        "artifact": "operator-local-historical-ohlcv-artifact@v1",
        "receipt": "operator-local-historical-ohlcv-receipt@v1",
    },
    "limits": _LIMITS,
    "max_request_bytes": _LIMITS["max_source_policy_bytes"],
    "json_max_depth": _JSON_MAX_DEPTH,
    "digest_algorithm": "SHA-256",
    "immutable_file_mode": _IMMUTABLE_FILE_MODE,
    "storage_layout": {
        "root_directory": _ROOT_DIRECTORY,
        "schema_directory": _SCHEMA_DIRECTORY,
        "object_directory": _OBJECT_DIRECTORY,
        "revision_directory": _REVISION_DIRECTORY,
        "revision_suffix": ".json",
    },
    "disclosures": {
        "context_status": "HISTORICAL_CONTEXT_NOT_EVALUATED",
        "limitation": "FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION",
    },
    "correction_mutable_fields": list(_CORRECTION_MUTABLE_FIELDS),
    "storage_authority": {
        "lease_name": _INGESTION_LOCK_NAME,
        "lease_mode": _INGESTION_LOCK_MODE,
        "visible_directory_mode": _DIRECTORY_MODE,
        "visible_file_mode": _IMMUTABLE_FILE_MODE,
        "path_resolution": "no-follow",
        "initial_existing_root": "identity-pinned exact replay only",
        "cli_admitted_root_identity": "required for supplied domain read/write authority",
    },
    "durability": {
        "file_fsync_before_link": True,
        "parent_directory_fsync_after_link_or_exact_existing": True,
        "existing_directory_retry_parent_fsync": True,
        "existing_directory_parent_fsync_before_open": True,
        "initial_exact_replay_hierarchy_parent_fsync": True,
        "sibling_directory_failure_closes_open_descriptors": True,
        "exact_readback_after_publication": True,
        "uncertainty_on_cleanup_or_fsync_or_readback_failure": True,
    },
}


class HistoricalOhlcvImportOutcomeV1(StrEnum):
    SUCCESS = "SUCCESS"
    MALFORMED_INPUT = "MALFORMED_INPUT"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"
    PARENT_LINEAGE_CONFLICT = "PARENT_LINEAGE_CONFLICT"
    PUBLICATION_UNCERTAIN_OR_CONFLICT = "PUBLICATION_UNCERTAIN_OR_CONFLICT"


@dataclass(frozen=True, slots=True)
class HistoricalOhlcvImportResultV1:
    outcome: HistoricalOhlcvImportOutcomeV1
    revision_sha256: str | None = None
    revision: dict[str, Any] | None = None


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _schedule_identity(
    from_session: object, to_session: object, expected_sessions: object
) -> str:
    return _sha(
        _canonical(
            {
                "schema_version": _SCHEDULE_SCHEMA_VERSION,
                "from_session": from_session,
                "to_session": to_session,
                "expected_sessions": expected_sessions,
            }
        )
    )


def _runtime_root() -> Path:
    source = Path(__file__)
    root = source.parent.parent
    if not source.is_absolute() or root.name != "swing_trading_ai_assistant":
        raise ValueError("historical revision runtime identity invalid")
    return root


def _loaded_runtime_code_identity() -> str:
    try:
        return runtime_source_sha256(__name__, _runtime_root(), _RUNTIME_SOURCE)
    except ValueError:
        raise ValueError("historical revision runtime identity invalid") from None


_SCHEMA_IDENTITY_SHA256: Final = _sha(_canonical(_SCHEMA_IDENTITY_PREIMAGE))
_LOADED_RUNTIME_CODE_IDENTITY_SHA256: Final = _loaded_runtime_code_identity()
_CONFIGURATION_IDENTITY_SHA256: Final = _sha(
    _canonical(_CONFIGURATION_IDENTITY_PREIMAGE)
)


def _required_identities() -> tuple[str, str, str]:
    return (
        _SCHEMA_IDENTITY_SHA256,
        _LOADED_RUNTIME_CODE_IDENTITY_SHA256,
        _CONFIGURATION_IDENTITY_SHA256,
    )


def _closed_json(  # noqa: C901 - one closed untrusted JSON boundary
    raw: object, maximum: int
) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > maximum:
        raise ValueError

    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if type(key) is not str or key in value:
                raise ValueError
            value[key] = item
        return value

    def reject_float(_: str) -> object:
        raise ValueError

    value = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=reject_pairs,
        parse_float=reject_float,
        parse_constant=reject_float,
    )
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        current, container_depth = pending.pop()
        if type(current) is dict:
            next_depth = container_depth + 1
            if next_depth > _JSON_MAX_DEPTH:
                raise ValueError
            object_value = cast(dict[str, Any], current)
            pending.extend((item, next_depth) for item in object_value.values())
        elif type(current) is list:
            next_depth = container_depth + 1
            if next_depth > _JSON_MAX_DEPTH:
                raise ValueError
            list_value = cast(list[Any], current)
            pending.extend((item, next_depth) for item in list_value)
    if type(value) is not dict:
        raise ValueError
    object_value = cast(dict[str, Any], value)
    if _canonical(object_value) != raw:
        raise ValueError
    return object_value


def _only(value: dict[str, Any], fields: frozenset[str]) -> bool:
    return frozenset(value) == fields


def _digest(value: object) -> str | None:
    return value if type(value) is str and _DIGEST_RE.fullmatch(value) else None


def _date_text(value: object) -> date | None:
    if type(value) is not str or len(value) != 10:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _instant(value: object) -> datetime | None:
    if type(value) is not str or len(value) != 20:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None
    return parsed if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value else None


def _decimal(value: object, *, positive: bool, integral: bool = False) -> str | None:
    if (
        type(value) is not str
        or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value)
        or (integral and "." in value)
        or ("." in value and value.endswith("0"))
    ):
        return None
    try:
        decimal = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    if not decimal.is_finite() or (positive and decimal <= 0):
        return None
    return value


def _result(outcome: HistoricalOhlcvImportOutcomeV1) -> HistoricalOhlcvImportResultV1:
    return HistoricalOhlcvImportResultV1(outcome)


def _parse_member(value: object) -> dict[str, Any] | None:
    if type(value) is not dict:
        return None
    member = cast(dict[str, Any], value)
    member_fields = frozenset(
        {
            "isin",
            "exchange",
            "listed_equity_segment",
            "effective_symbol",
            "symbol_effective_from",
            "symbol_effective_to",
            "provider_mapping",
        }
    )
    if (
        not _only(member, member_fields)
        or type(member["isin"]) is not str
        or not _ISIN_RE.fullmatch(member["isin"])
        or member["exchange"] != "NSE"
        or member["listed_equity_segment"] != "EQUITY"
        or type(member["effective_symbol"]) is not str
        or not _SAFE_TEXT_RE.fullmatch(member["effective_symbol"])
        or _date_text(member["symbol_effective_from"]) is None
        or (
            member["symbol_effective_to"] is not None
            and _date_text(member["symbol_effective_to"]) is None
        )
        or type(member["provider_mapping"]) is not dict
    ):
        return None
    mapping = cast(dict[str, Any], member["provider_mapping"])
    mapping_fields = frozenset(
        {
            "provider",
            "provider_instrument_id",
            "mapping_effective_from",
            "mapping_effective_to",
            "mapping_evidence_sha256",
        }
    )
    mapping_start = _date_text(mapping.get("mapping_effective_from"))
    mapping_end_raw = mapping.get("mapping_effective_to")
    mapping_end = _date_text(mapping_end_raw) if mapping_end_raw is not None else None
    member_start = _date_text(member["symbol_effective_from"])
    member_end = (
        _date_text(member["symbol_effective_to"])
        if member["symbol_effective_to"] is not None
        else None
    )
    if (
        not _only(mapping, mapping_fields)
        or type(mapping["provider"]) is not str
        or type(mapping["provider_instrument_id"]) is not str
        or not _SAFE_TEXT_RE.fullmatch(mapping["provider_instrument_id"])
        or mapping_start is None
        or (mapping_end_raw is not None and mapping_end is None)
        or (mapping_end is not None and mapping_end < mapping_start)
        or (
            member_end is not None
            and member_start is not None
            and member_end < member_start
        )
        or _digest(mapping["mapping_evidence_sha256"]) is None
    ):
        return None
    return member


def _parse_request_structure(raw: object) -> dict[str, Any] | None:  # noqa: C901
    try:
        request = _closed_json(raw, _LIMITS["max_source_policy_bytes"])
    except (
        RecursionError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return None
    if not _only(request, frozenset(_REQUEST_FIELDS)):
        return None
    if (
        type(request["operation"]) is not str
        or request["contract_version"] != _CONTRACT_VERSION
        or request["research_scope"] != _SCOPE
        or request["operation"] not in _OPERATION_LITERALS
        or request["interval"] != _INTERVAL
        or request["limits"] != _LIMITS
        or any(
            _digest(request[field]) is None
            for field in (
                "schedule_evidence_sha256",
                "source_policy_sha256",
                "source_artifact_sha256",
                "receipt_sha256",
                "schema_identity_sha256",
                "runtime_code_identity_sha256",
                "configuration_identity_sha256",
            )
        )
        or _instant(request["acquired_at"]) is None
        or _instant(request["known_at_cutoff"]) is None
        or type(request["permitted_use"]) is not str
        or type(request["price_basis"]) is not str
        or type(request["parent_revision_sha256"]) not in {str, type(None)}
        or (
            request["parent_revision_sha256"] is not None
            and _digest(request["parent_revision_sha256"]) is None
        )
        or type(request["correction_coordinates"]) is not list
        or type(request["cohort"]) is not list
        or type(request["expected_sessions"]) is not list
    ):
        return None
    acquired = _instant(request["acquired_at"])
    cutoff = _instant(request["known_at_cutoff"])
    lower = _date_text(request["from_session"])
    upper = _date_text(request["to_session"])
    sessions = cast(list[Any], request["expected_sessions"])
    if (
        acquired is None
        or cutoff is None
        or lower is None
        or upper is None
        or lower > upper
        or not sessions
        or len(sessions) > _LIMITS["max_sessions"]
        or any(_date_text(item) is None for item in sessions)
    ):
        return None
    parsed_sessions = cast(list[date], [_date_text(item) for item in sessions])
    if (
        any(
            parsed_sessions[index] >= parsed_sessions[index + 1]
            for index in range(len(parsed_sessions) - 1)
        )
        or parsed_sessions[0] < lower
        or parsed_sessions[-1] > upper
        or request["schedule_evidence_sha256"]
        != _schedule_identity(
            request["from_session"], request["to_session"], cast(list[str], sessions)
        )
        or cutoff < acquired
    ):
        return None
    cohort = cast(list[Any], request["cohort"])
    if not 1 <= len(cohort) <= _LIMITS["max_members"]:
        return None
    members = [_parse_member(member) for member in cohort]
    if any(member is None for member in members):
        return None
    resolved_members = cast(list[dict[str, Any]], members)
    keys = [(member["isin"], member["exchange"]) for member in resolved_members]
    if (
        keys != sorted(keys)
        or len(keys) != len(set(keys))
        or len(keys) * len(sessions) > _LIMITS["max_rows"]
    ):
        return None
    for coordinate_value in cast(list[Any], request["correction_coordinates"]):
        if type(coordinate_value) is not dict:
            return None
        coordinate = cast(dict[str, Any], coordinate_value)
        if (
            not _only(coordinate, frozenset({"isin", "exchange", "session"}))
            or type(coordinate["isin"]) is not str
            or not _ISIN_RE.fullmatch(coordinate["isin"])
            or coordinate["exchange"] != "NSE"
            or _date_text(coordinate["session"]) is None
        ):
            return None
    coordinate_keys = [
        (coordinate["isin"], coordinate["exchange"], coordinate["session"])
        for coordinate in cast(list[dict[str, str]], request["correction_coordinates"])
    ]
    if coordinate_keys != sorted(coordinate_keys) or len(coordinate_keys) != len(
        set(coordinate_keys)
    ):
        return None
    return request


def _parse_source_structure(
    policy_raw: object, artifact_raw: object, receipt_raw: object
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    try:
        policy = _closed_json(policy_raw, _LIMITS["max_source_policy_bytes"])
        artifact = _closed_json(artifact_raw, _LIMITS["max_artifact_bytes"])
        receipt = _closed_json(receipt_raw, _LIMITS["max_receipt_bytes"])
    except (
        RecursionError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return None
    if not (
        _only(
            policy,
            frozenset(
                {
                    "schema_version",
                    "source_name",
                    "permitted_use",
                    "ohlcv_adjustment_semantics",
                    "artifact_sha256",
                }
            ),
        )
        and _only(
            receipt,
            frozenset(
                {
                    "schema_version",
                    "source_policy_sha256",
                    "source_artifact_sha256",
                    "acquired_at",
                    "known_at",
                    "permitted_use",
                    "ohlcv_adjustment_semantics",
                }
            ),
        )
        and _only(artifact, frozenset({"schema_version", "bars"}))
        and all(type(policy[field]) is str for field in policy)
        and all(type(receipt[field]) is str for field in receipt)
        and type(artifact["schema_version"]) is str
        and type(artifact["bars"]) is list
    ):
        return None
    bar_fields = frozenset(
        {
            "isin",
            "exchange",
            "session",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "known_at",
            "price_basis",
        }
    )
    for row_value in cast(list[Any], artifact["bars"]):
        if type(row_value) is not dict:
            return None
        row = cast(dict[str, Any], row_value)
        if not _only(row, bar_fields) or any(
            type(row[field]) is not str for field in row
        ):
            return None
    return policy, artifact, receipt


def _parse_import_candidate_structure(
    request_raw: object,
    policy_raw: object,
    artifact_raw: object,
    receipt_raw: object,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    request = _parse_request_structure(request_raw)
    source = _parse_source_structure(policy_raw, artifact_raw, receipt_raw)
    if request is None or source is None:
        return None
    policy, artifact, receipt = source
    if len(cast(list[Any], artifact["bars"])) > request["limits"]["max_rows"]:
        return None
    return request, policy, artifact, receipt


def _validate_current_request_identity(request: dict[str, Any]) -> bool:
    schema_identity, runtime_identity, configuration_identity = _required_identities()
    return (
        request["schema_identity_sha256"] == schema_identity
        and request["runtime_code_identity_sha256"] == runtime_identity
        and request["configuration_identity_sha256"] == configuration_identity
    )


def _find_unsupported_capability(
    request: dict[str, Any],
    policy: dict[str, Any],
    artifact: dict[str, Any],
    receipt: dict[str, Any],
) -> bool:
    return any(
        (
            request["permitted_use"] != _PERMITTED_USE,
            request["price_basis"] != _PRICE_BASIS,
            any(
                member["provider_mapping"]["provider"] != _MAPPING_PROVIDER
                for member in cast(list[dict[str, Any]], request["cohort"])
            ),
            policy["schema_version"]
            != "operator-local-historical-ohlcv-source-policy@v1",
            policy["permitted_use"] != _PERMITTED_USE,
            policy["ohlcv_adjustment_semantics"] != _PRICE_BASIS,
            receipt["schema_version"] != "operator-local-historical-ohlcv-receipt@v1",
            receipt["permitted_use"] != _PERMITTED_USE,
            receipt["ohlcv_adjustment_semantics"] != _PRICE_BASIS,
            artifact["schema_version"] != "operator-local-historical-ohlcv-artifact@v1",
            any(
                row["price_basis"] != _PRICE_BASIS
                for row in cast(list[dict[str, Any]], artifact["bars"])
            ),
        )
    )


def _validate_bars(
    request: dict[str, Any], artifact: dict[str, Any]
) -> list[dict[str, Any]] | None:
    expected_members = [
        (member["isin"], member["exchange"])
        for member in cast(list[dict[str, Any]], request["cohort"])
    ]
    expected_sessions = cast(list[str], request["expected_sessions"])
    expected_keys = [
        (isin, exchange, session)
        for isin, exchange in expected_members
        for session in expected_sessions
    ]
    rows = cast(list[Any], artifact["bars"])
    cutoff = _instant(request["known_at_cutoff"])
    if (
        len(rows) != len(expected_keys)
        or len(rows) > _LIMITS["max_rows"]
        or cutoff is None
    ):
        return None
    normalized: list[dict[str, Any]] = []
    for row_value, expected_key in zip(rows, expected_keys, strict=True):
        row = cast(dict[str, Any], row_value)
        key = (row["isin"], row["exchange"], row["session"])
        values = {
            field: _decimal(row[field], positive=True)
            for field in ("open", "high", "low", "close")
        }
        volume = _decimal(row["volume"], positive=False, integral=True)
        known_at = _instant(row["known_at"])
        if (
            key != expected_key
            or _date_text(row["session"]) is None
            or None in values.values()
            or volume is None
            or known_at is None
            or known_at > cutoff
        ):
            return None
        prices = cast(dict[str, str], values)
        low, open_value, close, high = (
            Decimal(prices["low"]),
            Decimal(prices["open"]),
            Decimal(prices["close"]),
            Decimal(prices["high"]),
        )
        if not low <= min(open_value, close) <= max(open_value, close) <= high:
            return None
        normalized.append(dict(row))
    return normalized


def _validate_candidate_evidence(
    request: dict[str, Any],
    policy_raw: bytes,
    artifact_raw: bytes,
    receipt_raw: bytes,
    policy: dict[str, Any],
    artifact: dict[str, Any],
    receipt: dict[str, Any],
) -> list[dict[str, Any]] | None:
    if (
        _sha(policy_raw) != request["source_policy_sha256"]
        or _sha(artifact_raw) != request["source_artifact_sha256"]
        or _sha(receipt_raw) != request["receipt_sha256"]
        or request["schedule_evidence_sha256"]
        != _schedule_identity(
            request["from_session"],
            request["to_session"],
            request["expected_sessions"],
        )
        or not _SAFE_TEXT_RE.fullmatch(policy["source_name"])
        or _digest(policy["artifact_sha256"]) is None
        or policy["artifact_sha256"] != request["source_artifact_sha256"]
        or _digest(receipt["source_policy_sha256"]) is None
        or _digest(receipt["source_artifact_sha256"]) is None
        or receipt["source_policy_sha256"] != request["source_policy_sha256"]
        or receipt["source_artifact_sha256"] != request["source_artifact_sha256"]
        or receipt["acquired_at"] != request["acquired_at"]
    ):
        return None
    known_at = _instant(receipt["known_at"])
    cutoff = _instant(request["known_at_cutoff"])
    if known_at is None or cutoff is None or known_at > cutoff:
        return None
    bars = _validate_bars(request, artifact)
    if bars is None:
        return None
    candidate_coordinates = {_coordinate(row) for row in bars}
    if request["operation"] == "CORRECTION" and any(
        _coordinate(coordinate) not in candidate_coordinates
        for coordinate in cast(list[dict[str, Any]], request["correction_coordinates"])
    ):
        return None
    return bars


def _request_projection_from_revision(value: dict[str, Any]) -> dict[str, Any]:
    if not _only(value, _REVISION_FIELDS):
        raise RuntimeError
    return {field: value[field] for field in _REQUEST_FIELDS}


def _revision_value(
    request: dict[str, Any], bars: list[dict[str, Any]], depth: int
) -> dict[str, Any]:
    value = {field: request[field] for field in _REQUEST_FIELDS}
    value.update(
        {
            "request_identity_sha256": _sha(_canonical(request)),
            "lineage_depth": depth,
            "context_status": "HISTORICAL_CONTEXT_NOT_EVALUATED",
            "limitation": "FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION",
            "bars": bars,
        }
    )
    value["revision_sha256"] = _sha(_canonical(value))
    return value


def _coordinate(row: dict[str, Any]) -> tuple[str, str, str]:
    return cast(str, row["isin"]), cast(str, row["exchange"]), cast(str, row["session"])


def _validate_transition(  # noqa: C901 - one closed lineage boundary
    request: dict[str, Any],
    bars: list[dict[str, Any]],
    parent: dict[str, Any] | None,
) -> tuple[int | None, HistoricalOhlcvImportOutcomeV1]:
    coordinates = cast(list[dict[str, Any]], request["correction_coordinates"])
    coordinate_keys = [
        (item["isin"], item["exchange"], item["session"]) for item in coordinates
    ]
    if request["operation"] == "INITIAL":
        if request["parent_revision_sha256"] is not None or coordinates:
            return None, HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT
        return 0, HistoricalOhlcvImportOutcomeV1.SUCCESS
    if (
        _digest(request["parent_revision_sha256"]) is None
        or request["operation"] == "APPEND"
        and coordinates
        or request["operation"] == "CORRECTION"
        and (
            not coordinates
            or coordinate_keys != sorted(coordinate_keys)
            or len(coordinate_keys) != len(set(coordinate_keys))
        )
        or parent is None
    ):
        return None, HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT
    depth = parent.get("lineage_depth")
    parent_bars_value = parent.get("bars")
    parent_sessions_value = parent.get("expected_sessions")
    if (
        type(depth) is not int
        or depth < 0
        or depth >= _LIMITS["max_lineage_depth"]
        or type(parent_bars_value) is not list
        or type(parent_sessions_value) is not list
        or request["cohort"] != parent.get("cohort")
        or request["price_basis"] != parent.get("price_basis")
        or request["from_session"] != parent.get("from_session")
    ):
        return None, HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT
    parent_bars = cast(list[dict[str, Any]], parent_bars_value)
    parent_sessions = cast(list[str], parent_sessions_value)
    sessions = cast(list[str], request["expected_sessions"])
    parent_by_coordinate = {_coordinate(row): row for row in parent_bars}
    child_by_coordinate = {_coordinate(row): row for row in bars}
    if len(parent_by_coordinate) != len(parent_bars) or len(child_by_coordinate) != len(
        bars
    ):
        return None, HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT
    if request["operation"] == "APPEND":
        if (
            len(sessions) <= len(parent_sessions)
            or sessions[: len(parent_sessions)] != parent_sessions
            or request["to_session"] < parent["to_session"]
            or sessions[len(parent_sessions)] <= parent["to_session"]
            or sessions[-1] > request["to_session"]
            or any(
                child_by_coordinate.get(coordinate) != parent_row
                for coordinate, parent_row in parent_by_coordinate.items()
            )
        ):
            return None, HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT
    else:
        if (
            request["to_session"] != parent.get("to_session")
            or sessions != parent_sessions
            or len(bars) != len(parent_bars)
            or set(child_by_coordinate) != set(parent_by_coordinate)
        ):
            return None, HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT
        named = set(coordinate_keys)
        if named - set(parent_by_coordinate):
            return None, HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT
        mutable = frozenset(_CORRECTION_MUTABLE_FIELDS)
        differences: set[tuple[str, str, str]] = set()
        for coordinate, parent_row in parent_by_coordinate.items():
            child_row = child_by_coordinate[coordinate]
            if child_row == parent_row:
                continue
            if coordinate not in named or any(
                child_row[field] != parent_row[field]
                for field in child_row
                if field not in mutable
            ):
                return None, HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT
            differences.add(coordinate)
        if named != differences:
            return None, HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT
    return depth + 1, HistoricalOhlcvImportOutcomeV1.SUCCESS


def _open_directory(parent: int, name: str) -> int:
    try:
        os.mkdir(name, mode=_DIRECTORY_MODE, dir_fd=parent)
        os.fsync(parent)
    except FileExistsError:
        os.fsync(parent)
    descriptor = os.open(
        name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
    )
    info = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != _DIRECTORY_MODE
    ):
        os.close(descriptor)
        raise RuntimeError
    return descriptor


def _open_existing_directory(parent: int, name: str) -> int:
    os.fsync(parent)
    descriptor = os.open(
        name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
    )
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != _DIRECTORY_MODE
        ):
            raise RuntimeError
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _assert_owner_private_directory(descriptor: int) -> None:
    info = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise RuntimeError


def _read_object(parent: int, name: str, maximum: int) -> bytes:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent
    )
    try:
        before = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != _IMMUTABLE_FILE_MODE
            or before.st_nlink != 1
            or before.st_size > maximum
            or (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise RuntimeError
        raw = bytearray()
        while len(raw) <= maximum:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(descriptor)
        named_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (
            len(raw) != before.st_size
            or before.st_mode != after.st_mode
            or before.st_uid != after.st_uid
            or before.st_nlink != after.st_nlink
            or before.st_size != after.st_size
            or (after.st_dev, after.st_ino) != (named_after.st_dev, named_after.st_ino)
        ):
            raise RuntimeError
        return bytes(raw)
    finally:
        os.close(descriptor)


def _publish_object(parent: int, name: str, raw: bytes) -> bool:
    try:
        if _read_object(parent, name, len(raw)) == raw:
            os.fsync(parent)
            return False
        raise RuntimeError
    except FileNotFoundError:
        pass
    temporary = f".{name}.{uuid4().hex}.tmp"
    descriptor: int | None = None
    linked = False
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent,
        )
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise RuntimeError
            offset += written
        os.fchmod(descriptor, _IMMUTABLE_FILE_MODE)
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
            linked = True
        except FileExistsError:
            pass
        os.unlink(temporary, dir_fd=parent)
        os.fsync(parent)
        if _read_object(parent, name, len(raw)) != raw:
            raise RuntimeError
        return linked
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=parent)


@dataclass(frozen=True, slots=True)
class HistoricalOhlcvRevisionStoreV1:
    """Own strict V1 revision publication and exact named readback."""

    storage_root: Path
    admitted_root_identity: tuple[int, int] | None = None

    def _acquire_private_empty_lease(self) -> LeaseResult:
        if self.admitted_root_identity is None:
            return StorageRootLease.try_acquire_private_empty(self.storage_root)
        return StorageRootLease._try_acquire(  # pyright: ignore[reportPrivateUsage]
            self.storage_root,
            create_lock=True,
            require_private_empty=True,
            expected_root_identity=self.admitted_root_identity,
        )

    def _acquire_existing_writer_lease(self) -> LeaseResult:
        root_identity = self.admitted_root_identity
        if root_identity is None:
            root_identity = StorageRootLease.admit_existing_private_identity(
                self.storage_root
            )
        if root_identity is None:
            return LeaseResult(
                LeaseOutcome.FAILED,
                LeaseFailureCode.STORAGE_UNSAFE,
                None,
            )
        return StorageRootLease.try_acquire_existing_identity(
            self.storage_root, root_identity
        )

    def _acquire_writer_lease(self, operation: str) -> LeaseResult:
        if operation == "INITIAL":
            first = self._acquire_private_empty_lease()
            if first.outcome is LeaseOutcome.ACQUIRED:
                return first
        return self._acquire_existing_writer_lease()

    def _read_initial_exact_replay(
        self,
        operation_descriptor: int,
        revision_id: str,
        revision_raw: bytes,
        source_objects: tuple[tuple[str, bytes], ...],
    ) -> dict[str, Any]:
        root = _open_existing_directory(operation_descriptor, _ROOT_DIRECTORY)
        try:
            version = _open_existing_directory(root, _SCHEMA_DIRECTORY)
            try:
                with ExitStack() as directories:
                    objects = _open_existing_directory(version, _OBJECT_DIRECTORY)
                    directories.callback(os.close, objects)
                    revisions = _open_existing_directory(version, _REVISION_DIRECTORY)
                    directories.callback(os.close, revisions)
                    exact_revision = self._read_stored_exact_from_directories(
                        revision_id, objects, revisions
                    )
                    if _canonical(exact_revision) != revision_raw:
                        raise RuntimeError
                    for name, raw in source_objects:
                        if _read_object(objects, name, len(raw)) != raw:
                            raise RuntimeError
                    os.fsync(objects)
                    if (
                        _read_object(
                            revisions,
                            f"{revision_id}.json",
                            _LIMITS["max_revision_bytes"],
                        )
                        != revision_raw
                    ):
                        raise RuntimeError
                    os.fsync(revisions)
                    return exact_revision
            finally:
                os.close(version)
        finally:
            os.close(root)

    def import_exact(  # noqa: C901 - one publication transaction boundary
        self,
        request_raw: object,
        source_policy_raw: object,
        source_artifact_raw: object,
        receipt_raw: object,
    ) -> HistoricalOhlcvImportResultV1:
        candidate = _parse_import_candidate_structure(
            request_raw, source_policy_raw, source_artifact_raw, receipt_raw
        )
        if candidate is None:
            return _result(HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT)
        request, policy, artifact, receipt = candidate
        if not _validate_current_request_identity(request):
            return _result(HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT)
        if _find_unsupported_capability(request, policy, artifact, receipt):
            return _result(HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY)
        source_policy = cast(bytes, source_policy_raw)
        source_artifact = cast(bytes, source_artifact_raw)
        source_receipt = cast(bytes, receipt_raw)
        bars = _validate_candidate_evidence(
            request,
            source_policy,
            source_artifact,
            source_receipt,
            policy,
            artifact,
            receipt,
        )
        if bars is None:
            return _result(HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE)
        parent: dict[str, Any] | None = None
        if request["operation"] != "INITIAL":
            parent_result = self.read_exact(request["parent_revision_sha256"])
            if (
                parent_result.outcome is not HistoricalOhlcvImportOutcomeV1.SUCCESS
                or parent_result.revision is None
            ):
                return _result(HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT)
            parent = parent_result.revision
        depth, outcome = _validate_transition(request, bars, parent)
        if depth is None:
            return _result(outcome)
        revision = _revision_value(request, bars, depth)
        revision_raw = _canonical(revision)
        revision_id = cast(str, revision["revision_sha256"])
        if len(revision_raw) > _LIMITS["max_revision_bytes"]:
            return _result(HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT)
        initial_replay_only = request["operation"] == "INITIAL"
        if initial_replay_only:
            first = self._acquire_private_empty_lease()
            lease_result = (
                first
                if first.outcome is LeaseOutcome.ACQUIRED
                else self._acquire_existing_writer_lease()
            )
            initial_replay_only = first.outcome is not LeaseOutcome.ACQUIRED
        else:
            lease_result = self._acquire_writer_lease(cast(str, request["operation"]))
        if (
            lease_result.outcome is not LeaseOutcome.ACQUIRED
            or lease_result.lease is None
        ):
            return _result(
                HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
            )
        try:
            with (
                lease_result.lease as lease,
                lease.root_operation(self.storage_root) as operation,
            ):
                _assert_owner_private_directory(operation.descriptor)
                if initial_replay_only:
                    exact_revision = self._read_initial_exact_replay(
                        operation.descriptor,
                        revision_id,
                        revision_raw,
                        (
                            (request["source_policy_sha256"], source_policy),
                            (request["source_artifact_sha256"], source_artifact),
                            (request["receipt_sha256"], source_receipt),
                        ),
                    )
                    return HistoricalOhlcvImportResultV1(
                        HistoricalOhlcvImportOutcomeV1.SUCCESS,
                        revision_id,
                        exact_revision,
                    )
                root = _open_directory(operation.descriptor, _ROOT_DIRECTORY)
                try:
                    version = _open_directory(root, _SCHEMA_DIRECTORY)
                    try:
                        with ExitStack() as directories:
                            objects = _open_directory(version, _OBJECT_DIRECTORY)
                            directories.callback(os.close, objects)
                            revisions = _open_directory(version, _REVISION_DIRECTORY)
                            directories.callback(os.close, revisions)
                            if request["operation"] != "INITIAL":
                                verified_parent = (
                                    self._read_stored_exact_from_directories(
                                        cast(str, request["parent_revision_sha256"]),
                                        objects,
                                        revisions,
                                    )
                                )
                                verified_depth, verified_outcome = _validate_transition(
                                    request, bars, verified_parent
                                )
                                if (
                                    verified_depth != depth
                                    or verified_outcome
                                    is not HistoricalOhlcvImportOutcomeV1.SUCCESS
                                ):
                                    return _result(
                                        HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT
                                    )
                            try:
                                existing_revision = _read_object(
                                    revisions,
                                    f"{revision_id}.json",
                                    _LIMITS["max_revision_bytes"],
                                )
                            except FileNotFoundError:
                                existing_revision = None
                            if existing_revision is not None:
                                if existing_revision != revision_raw:
                                    raise RuntimeError
                                self._read_stored_exact_from_directories(
                                    revision_id, objects, revisions
                                )
                            try:
                                for name, raw in (
                                    (request["source_policy_sha256"], source_policy),
                                    (
                                        request["source_artifact_sha256"],
                                        source_artifact,
                                    ),
                                    (request["receipt_sha256"], source_receipt),
                                ):
                                    _publish_object(objects, name, raw)
                                _publish_object(
                                    revisions, f"{revision_id}.json", revision_raw
                                )
                            except Exception:
                                # A linked immutable name may already be visible when
                                # temp cleanup, directory sync, or exact readback
                                # reports uncertainty. Preserve that exact object:
                                # it is independently content-addressed and a retry
                                # can safely revalidate it. Unlinking by name here
                                # could delete a publication another writer retained.
                                raise
                            if existing_revision is not None:
                                exact_revision = (
                                    self._read_stored_exact_from_directories(
                                        revision_id, objects, revisions
                                    )
                                )
                                return HistoricalOhlcvImportResultV1(
                                    HistoricalOhlcvImportOutcomeV1.SUCCESS,
                                    revision_id,
                                    exact_revision,
                                )
                    finally:
                        os.close(version)
                finally:
                    os.close(root)
        except Exception:
            return _result(
                HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
            )
        return self.read_exact(revision_id)

    def read_exact(self, revision_sha256: object) -> HistoricalOhlcvImportResultV1:
        revision_id = _digest(revision_sha256)
        if revision_id is None:
            return _result(HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT)
        root_identity = self.admitted_root_identity
        if root_identity is None:
            root_identity = StorageRootLease.admit_existing_private_identity(
                self.storage_root
            )
        if root_identity is None:
            return _result(
                HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
            )
        lease_result = StorageRootLease.try_acquire_existing_identity(
            self.storage_root, root_identity
        )
        if (
            lease_result.outcome is not LeaseOutcome.ACQUIRED
            or lease_result.lease is None
        ):
            return _result(
                HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
            )
        try:
            with (
                lease_result.lease as lease,
                lease.read_operation(self.storage_root) as operation,
            ):
                _assert_owner_private_directory(operation.descriptor)
                root = _open_existing_directory(operation.descriptor, _ROOT_DIRECTORY)
                try:
                    version = _open_existing_directory(root, _SCHEMA_DIRECTORY)
                    try:
                        with ExitStack() as directories:
                            objects = _open_existing_directory(
                                version, _OBJECT_DIRECTORY
                            )
                            directories.callback(os.close, objects)
                            revisions = _open_existing_directory(
                                version, _REVISION_DIRECTORY
                            )
                            directories.callback(os.close, revisions)
                            value = self._read_stored_exact_from_directories(
                                revision_id, objects, revisions
                            )
                            return HistoricalOhlcvImportResultV1(
                                HistoricalOhlcvImportOutcomeV1.SUCCESS,
                                revision_id,
                                value,
                            )
                    finally:
                        os.close(version)
                finally:
                    os.close(root)
        except Exception:
            return _result(
                HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
            )

    def _validate_stored_revision_local(
        self, revision_id: str, objects: int, revisions: int
    ) -> dict[str, Any]:
        raw = _read_object(
            revisions, f"{revision_id}.json", _LIMITS["max_revision_bytes"]
        )
        value = _closed_json(raw, _LIMITS["max_revision_bytes"])
        if (
            not _only(value, _REVISION_FIELDS)
            or value["revision_sha256"] != revision_id
            or _digest(value["revision_sha256"]) is None
        ):
            raise RuntimeError
        preimage = dict(value)
        preimage.pop("revision_sha256")
        if _sha(_canonical(preimage)) != revision_id:
            raise RuntimeError
        request = _request_projection_from_revision(value)
        if any(
            _digest(request[field]) is None
            for field in (
                "schema_identity_sha256",
                "runtime_code_identity_sha256",
                "configuration_identity_sha256",
            )
        ):
            raise RuntimeError
        parsed = _parse_request_structure(_canonical(request))
        if (
            parsed is None
            or value["request_identity_sha256"] != _sha(_canonical(parsed))
            or value["context_status"] != "HISTORICAL_CONTEXT_NOT_EVALUATED"
            or value["limitation"]
            != "FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION"
            or type(value["lineage_depth"]) is not int
            or not 0 <= value["lineage_depth"] <= _LIMITS["max_lineage_depth"]
        ):
            raise RuntimeError
        policy_raw = _read_object(
            objects, parsed["source_policy_sha256"], _LIMITS["max_source_policy_bytes"]
        )
        artifact_raw = _read_object(
            objects,
            parsed["source_artifact_sha256"],
            _LIMITS["max_artifact_bytes"],
        )
        receipt_raw = _read_object(
            objects, parsed["receipt_sha256"], _LIMITS["max_receipt_bytes"]
        )
        source = _parse_source_structure(policy_raw, artifact_raw, receipt_raw)
        if source is None:
            raise RuntimeError
        policy, artifact, receipt = source
        if _find_unsupported_capability(parsed, policy, artifact, receipt):
            raise RuntimeError
        bars = _validate_candidate_evidence(
            parsed,
            policy_raw,
            artifact_raw,
            receipt_raw,
            policy,
            artifact,
            receipt,
        )
        if bars is None or bars != value["bars"]:
            raise RuntimeError
        return value

    def _validate_stored_lineage_iterative(
        self, target_id: str, objects: int, revisions: int
    ) -> dict[str, Any]:
        current_id = target_id
        child: dict[str, Any] | None = None
        visited: set[str] = set()
        hop = 0
        while True:
            if hop > _LIMITS["max_lineage_depth"] or current_id in visited:
                raise RuntimeError
            visited.add(current_id)
            current = self._validate_stored_revision_local(
                current_id, objects, revisions
            )
            if child is not None:
                child_request = _request_projection_from_revision(child)
                depth, outcome = _validate_transition(
                    child_request, cast(list[dict[str, Any]], child["bars"]), current
                )
                if (
                    outcome is not HistoricalOhlcvImportOutcomeV1.SUCCESS
                    or depth != child["lineage_depth"]
                ):
                    raise RuntimeError
                child = None
            if current["operation"] == "INITIAL":
                if (
                    current["parent_revision_sha256"] is not None
                    or current["correction_coordinates"] != []
                    or current["lineage_depth"] != 0
                ):
                    raise RuntimeError
                break
            parent_id = _digest(current["parent_revision_sha256"])
            if parent_id is None:
                raise RuntimeError
            child = current
            current_id = parent_id
            hop += 1
        return self._validate_stored_revision_local(target_id, objects, revisions)

    def _read_stored_exact_from_directories(
        self, revision_id: str, objects: int, revisions: int
    ) -> dict[str, Any]:
        return self._validate_stored_lineage_iterative(revision_id, objects, revisions)
