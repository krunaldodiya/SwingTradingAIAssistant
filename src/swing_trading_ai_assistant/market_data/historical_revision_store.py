"""Strict local immutable storage for fixed-cohort historical daily OHLCV V1."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from calendar import monthrange
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, cast
from zoneinfo import ZoneInfo

from .historical_upstox_raw_runtime_identity_manifest import (
    HISTORICAL_UPSTOX_RAW_RUNTIME_SOURCE_SHA256_V1,
)
from .runtime_source_verifier import read_runtime_source
from .schedule_evidence import parse_canonical_schedule_bytes
from .storage_root_lease import (
    LeaseFailureCode,
    LeaseOutcome,
    LeaseResult,
    StorageRootLease,
    StorageRootLeaseOperation,
)

_CONTRACT_VERSION: Final = "fixed-cohort-historical-ohlcv-upstox-raw-revision-store@v1"
_SCOPE: Final = "FIXED_COHORT_RETROSPECTIVE"
_INTERVAL: Final = "1d"
_PRICE_BASIS: Final = "RAW"
_PERMITTED_USE: Final = "OWNER_PRIVATE_RESEARCH"
_MAPPING_PROVIDER: Final = "UPSTOX"
_ROOT_DIRECTORY: Final = "historical_ohlcv_revisions"
_PROFILE_DIRECTORY: Final = "upstox-raw"
_SCHEMA_DIRECTORY: Final = "v1"
_OBJECT_DIRECTORY: Final = "objects"
_REVISION_DIRECTORY: Final = "revisions"
_DIGEST_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
_ISIN_RE: Final = re.compile(r"[A-Z0-9]{12}\Z")
_SAFE_TEXT_RE: Final = re.compile(r"[ -~]{1,64}\Z")
_SNAPSHOT_HEADER_RE: Final = re.compile(r"[ -~]{1,512}\Z")
_LIMITS: Final = {
    "max_members": 50,
    "max_calendar_months": 12,
    "max_sessions": 366,
    "max_rows": 18_300,
    "max_source_partitions": 600,
    "max_query_months_per_call": 12,
    "max_query_rows_per_call": 366,
    "max_artifact_bytes": 134_217_728,
    "max_source_policy_bytes": 1_048_576,
    "max_receipt_bytes": 1_048_576,
    "max_revision_bytes": 134_217_728,
    "max_lineage_depth": 128,
}
_MAX_DAILY_VOLUME: Final = 2**63 - 1
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
_JSON_MAX_DEPTH: Final = 64
_IMMUTABLE_FILE_MODE: Final = 0o400
_AGGREGATION_VERSION: Final = "nse-session-ohlcv@v1"
_ADJUSTMENT_STATE: Final = "raw"
_TEMPORAL_STATUS: Final = "REVISED_NON_PIT"
_CORPORATE_ACTION_STATUS: Final = "NOT_EVALUATED"
_COMPARABILITY_STATUS: Final = "NOT_ESTABLISHED"
_CONTEXT_STATUS: Final = "HISTORICAL_CONTEXT_NOT_EVALUATED"
_LIMITATION: Final = "FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION"
_IST: Final = ZoneInfo("Asia/Kolkata")
_REQUEST_FIELDS: Final = (
    "contract_version",
    "research_scope",
    "source_profile",
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
    "observed_at",
    "permitted_use",
    "price_basis",
    "adjustment_state",
    "aggregation_version",
    "temporal_status",
    "corporate_action_status",
    "comparability_status",
    "schema_identity_sha256",
    "runtime_code_identity_sha256",
    "configuration_identity_sha256",
    "limits",
)
_REVISION_FIELDS: Final = frozenset(
    {
        *_REQUEST_FIELDS,
        "completion_request_identity_sha256",
        "lineage_depth",
        "context_status",
        "limitation",
        "bars",
        "revision_sha256",
    }
)
_MAPPING_RECEIPT_FIELDS: Final = frozenset(
    {
        "contract_version",
        "isin",
        "exchange",
        "effective_symbol",
        "requested_provider_instrument_id",
        "snapshot_schema_version",
        "snapshot_source",
        "observation_date",
        "retrieved_at",
        "observation_sha256",
        "compressed_sha256",
        "decompressed_sha256",
        "compressed_byte_count",
        "decompressed_byte_count",
        "relative_object_path",
        "relative_metadata_path",
        "etag",
        "last_modified",
        "resolved_instrument_key",
        "resolved_security_id",
        "resolved_symbol",
        "resolved_exchange",
        "resolved_segment",
        "resolved_instrument_type",
        "mapping_known_at",
        "mapping_receipt_identity_sha256",
    }
)
_PARTITION_RECEIPT_FIELDS: Final = frozenset(
    {
        "contract_version",
        "isin",
        "manifest_schema_version",
        "plan_provider",
        "plan_instrument_key",
        "plan_security_id",
        "plan_symbol",
        "plan_exchange",
        "plan_segment",
        "plan_instrument_type",
        "plan_interval",
        "plan_year",
        "plan_month",
        "plan_from_date",
        "plan_to_date",
        "ingestion_run_id",
        "candle_schema_version",
        "state",
        "validation_outcome",
        "validation_policy_version",
        "actual_from_ts",
        "actual_to_ts",
        "row_count",
        "parquet_sha256",
        "canonical_path",
        "source_version",
        "manifest_created_at",
        "attempt_started_at",
        "manifest_updated_at",
        "failure_category",
        "schedule_digest_sha256",
        "partition_receipt_identity_sha256",
    }
)

_SOURCE_RECEIPT_FIELDS: Final = frozenset(
    {
        "schema_version",
        "source_profile",
        "source_policy_sha256",
        "source_artifact_sha256",
        "mapping_receipts_identity_sha256",
        "partition_receipts_identity_sha256",
        "schedule_evidence_sha256",
        "observed_at",
        "known_at",
        "permitted_use",
        "price_basis",
        "adjustment_state",
        "temporal_status",
        "corporate_action_status",
        "comparability_status",
    }
)


_SCHEMA_IDENTITY_PREIMAGE: Final = {
    "metadata_version": "fixed-cohort-historical-ohlcv-schema-identity@v2",
    "canonical_representation": {
        "encoding": "UTF-8",
        "sorted_keys": True,
        "unique_keys": True,
        "separators": [",", ":"],
        "received_bytes": "exact canonical encoding",
        "unknown_fields": "rejected",
        "floats_constants_nan_infinity": "rejected",
        "maximum_containers": 64,
        "digest": "lowercase SHA-256",
        "date": "YYYY-MM-DD",
        "operator_instant": "YYYY-MM-DDTHH:MM:SSZ",
        "retained_instant": "whole-second Z or exactly six fractional digits",
        "price": "canonical non-exponent positive decimal",
        "volume": "canonical nonnegative integral decimal",
        "daily_volume_maximum": 9223372036854775807,
    },
    "objects": {
        "UpstoxRawHistoricalOhlcvCompletionRequestV1": {
            "field_rows": [
                {
                    "name": "contract_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["upstox-raw-fixed-cohort-historical-ohlcv-completion@v1"]',
                },
                {
                    "name": "revision_contract_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["fixed-cohort-historical-ohlcv-upstox-raw-revision-store@v1"]',
                },
                {
                    "name": "research_scope",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["FIXED_COHORT_RETROSPECTIVE"]',
                },
                {
                    "name": "source_profile",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["UPSTOX_RAW"]',
                },
                {
                    "name": "operation",
                    "semantic_type": "ENUM",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["INITIAL","APPEND","CORRECTION"]',
                },
                {
                    "name": "parent_revision_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "NULLABLE",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "correction_coordinates",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "COORDINATES",
                    "nullability": "REQUIRED",
                    "bounds": "CorrectionCoordinateV1,0..18300",
                },
                {
                    "name": "cohort",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "MEMBERS",
                    "nullability": "REQUIRED",
                    "bounds": "CanonicalListedEquityMemberV1,1..50",
                },
                {
                    "name": "from_session",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "to_session",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "interval",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["1d"]',
                },
                {
                    "name": "expected_sessions",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "SESSIONS",
                    "nullability": "REQUIRED",
                    "bounds": "LOCAL_DATE,1..366",
                },
                {
                    "name": "schedule_evidence_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "observed_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z",
                },
                {
                    "name": "permitted_use",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["OWNER_PRIVATE_RESEARCH"]',
                },
                {
                    "name": "price_basis",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["RAW"]',
                },
                {
                    "name": "schema_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "runtime_code_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "configuration_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "limits",
                    "semantic_type": "CLOSED_OBJECT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "CompletionLimitsV1",
                },
            ]
        },
        "CorrectionCoordinateV1": {
            "field_rows": [
                {
                    "name": "isin",
                    "semantic_type": "ISIN",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "UPPERCASE_ALNUM_12",
                },
                {
                    "name": "exchange",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["NSE"]',
                },
                {
                    "name": "session",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
            ]
        },
        "CanonicalListedEquityMemberV1": {
            "field_rows": [
                {
                    "name": "isin",
                    "semantic_type": "ISIN",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "UPPERCASE_ALNUM_12",
                },
                {
                    "name": "exchange",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["NSE"]',
                },
                {
                    "name": "listed_equity_segment",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["EQUITY"]',
                },
                {
                    "name": "effective_symbol",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "CHARACTERS",
                    "nullability": "REQUIRED",
                    "bounds": "PRINTABLE_ASCII_1_TO_64",
                },
                {
                    "name": "symbol_effective_from",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "symbol_effective_to",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "NULLABLE",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "provider_mapping",
                    "semantic_type": "CLOSED_OBJECT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "ProviderMappingV1",
                },
            ]
        },
        "ProviderMappingV1": {
            "field_rows": [
                {
                    "name": "provider",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["UPSTOX"]',
                },
                {
                    "name": "provider_instrument_id",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "CHARACTERS",
                    "nullability": "REQUIRED",
                    "bounds": "PRINTABLE_ASCII_1_TO_64",
                },
                {
                    "name": "mapping_effective_from",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "mapping_effective_to",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "NULLABLE",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "mapping_evidence_known_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z_OR_SIX_FRACTIONAL_DIGITS",
                },
                {
                    "name": "mapping_evidence_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
            ]
        },
        "CompletionLimitsV1": {
            "field_rows": [
                {
                    "name": "max_members",
                    "semantic_type": "INTEGER",
                    "unit": "COUNT",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[50]",
                },
                {
                    "name": "max_calendar_months",
                    "semantic_type": "INTEGER",
                    "unit": "COUNT",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[12]",
                },
                {
                    "name": "max_sessions",
                    "semantic_type": "INTEGER",
                    "unit": "COUNT",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[366]",
                },
                {
                    "name": "max_rows",
                    "semantic_type": "INTEGER",
                    "unit": "COUNT",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[18300]",
                },
                {
                    "name": "max_source_partitions",
                    "semantic_type": "INTEGER",
                    "unit": "COUNT",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[600]",
                },
                {
                    "name": "max_query_months_per_call",
                    "semantic_type": "INTEGER",
                    "unit": "COUNT",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[12]",
                },
                {
                    "name": "max_query_rows_per_call",
                    "semantic_type": "INTEGER",
                    "unit": "COUNT",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[366]",
                },
                {
                    "name": "max_artifact_bytes",
                    "semantic_type": "INTEGER",
                    "unit": "BYTES",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[134217728]",
                },
                {
                    "name": "max_source_policy_bytes",
                    "semantic_type": "INTEGER",
                    "unit": "BYTES",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[1048576]",
                },
                {
                    "name": "max_receipt_bytes",
                    "semantic_type": "INTEGER",
                    "unit": "BYTES",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[1048576]",
                },
                {
                    "name": "max_revision_bytes",
                    "semantic_type": "INTEGER",
                    "unit": "BYTES",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[134217728]",
                },
                {
                    "name": "max_lineage_depth",
                    "semantic_type": "INTEGER",
                    "unit": "COUNT",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[128]",
                },
            ]
        },
        "SourcePolicyV1": {
            "field_rows": [
                {
                    "name": "schema_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["upstox-retained-raw-historical-ohlcv-source-policy@v1"]',
                },
                {
                    "name": "source_profile",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["UPSTOX_RAW"]',
                },
                {
                    "name": "source_name",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["UPSTOX_RETAINED_VERIFIED_1M"]',
                },
                {
                    "name": "provider",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["UPSTOX"]',
                },
                {
                    "name": "source_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["upstox-historical-v3"]',
                },
                {
                    "name": "source_interval",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["1m"]',
                },
                {
                    "name": "output_interval",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["1d"]',
                },
                {
                    "name": "aggregation_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["nse-session-ohlcv@v1"]',
                },
                {
                    "name": "price_basis",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["RAW"]',
                },
                {
                    "name": "adjustment_state",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["raw"]',
                },
                {
                    "name": "temporal_status",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["REVISED_NON_PIT"]',
                },
                {
                    "name": "corporate_action_status",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["NOT_EVALUATED"]',
                },
                {
                    "name": "comparability_status",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["NOT_ESTABLISHED"]',
                },
                {
                    "name": "permitted_use",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["OWNER_PRIVATE_RESEARCH"]',
                },
                {
                    "name": "artifact_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
            ]
        },
        "SourceArtifactV1": {
            "field_rows": [
                {
                    "name": "schema_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["upstox-retained-raw-historical-ohlcv-artifact@v1"]',
                },
                {
                    "name": "source_profile",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["UPSTOX_RAW"]',
                },
                {
                    "name": "schedule",
                    "semantic_type": "CLOSED_OBJECT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "CanonicalScheduleEnvelopeV1|V2|V3",
                },
                {
                    "name": "mapping_receipts",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "RECEIPTS",
                    "nullability": "REQUIRED",
                    "bounds": "MappingReceiptV1,1..50",
                },
                {
                    "name": "partition_receipts",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "RECEIPTS",
                    "nullability": "REQUIRED",
                    "bounds": "PartitionReceiptV1,1..600",
                },
                {
                    "name": "bars",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "BARS",
                    "nullability": "REQUIRED",
                    "bounds": "HistoricalOhlcvBarV1,1..18300",
                },
            ]
        },
        "CanonicalScheduleEnvelopeV1": {
            "field_rows": [
                {
                    "name": "schema_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[1]",
                },
                {
                    "name": "source",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "CHARACTERS",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_ASCII",
                },
                {
                    "name": "source_release",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "CHARACTERS",
                    "nullability": "REQUIRED",
                    "bounds": "sha256:LOWERCASE_64_HEX",
                },
                {
                    "name": "as_of",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "SIX_FRACTIONAL_DIGITS_Z",
                },
                {
                    "name": "timezone",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["Asia/Kolkata"]',
                },
                {
                    "name": "covered_from",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "covered_to",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "sessions",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "SESSIONS",
                    "nullability": "REQUIRED",
                    "bounds": "CanonicalScheduleSessionV1,1..UNBOUNDED",
                },
            ]
        },
        "CanonicalScheduleEnvelopeV2": {
            "field_rows": [
                {
                    "name": "schema_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[2]",
                },
                {
                    "name": "source",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "CHARACTERS",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_ASCII",
                },
                {
                    "name": "source_release",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "CHARACTERS",
                    "nullability": "REQUIRED",
                    "bounds": "composed-calendar@v1=LOWERCASE_64_HEX",
                },
                {
                    "name": "as_of",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "SIX_FRACTIONAL_DIGITS_Z",
                },
                {
                    "name": "timezone",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["Asia/Kolkata"]',
                },
                {
                    "name": "covered_from",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "covered_to",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "sessions",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "SESSIONS",
                    "nullability": "REQUIRED",
                    "bounds": "CanonicalScheduleSessionV1,0..UNBOUNDED",
                },
                {
                    "name": "closures",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "CLOSURES",
                    "nullability": "REQUIRED",
                    "bounds": "CanonicalScheduleClosureV1,0..UNBOUNDED",
                },
            ]
        },
        "CanonicalScheduleEnvelopeV3": {
            "field_rows": [
                {
                    "name": "schema_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[3]",
                },
                {
                    "name": "source",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "CHARACTERS",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_ASCII",
                },
                {
                    "name": "source_release",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "CHARACTERS",
                    "nullability": "REQUIRED",
                    "bounds": "composed-calendar@v1=LOWERCASE_64_HEX",
                },
                {
                    "name": "as_of",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "SIX_FRACTIONAL_DIGITS_Z",
                },
                {
                    "name": "timezone",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["Asia/Kolkata"]',
                },
                {
                    "name": "covered_from",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "covered_to",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "sessions",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "SESSIONS",
                    "nullability": "REQUIRED",
                    "bounds": "CanonicalScheduleSessionV1,0..UNBOUNDED",
                },
                {
                    "name": "closures",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "CLOSURES",
                    "nullability": "REQUIRED",
                    "bounds": "CanonicalScheduleClosureV1,0..UNBOUNDED",
                },
            ]
        },
        "CanonicalScheduleSessionV1": {
            "field_rows": [
                {
                    "name": "trade_date",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "open_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "SIX_FRACTIONAL_DIGITS_Z_MINUTE_ALIGNED",
                },
                {
                    "name": "close_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "SIX_FRACTIONAL_DIGITS_Z_MINUTE_ALIGNED",
                },
                {
                    "name": "kind",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "CHARACTERS",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_ASCII",
                },
            ]
        },
        "CanonicalScheduleClosureV1": {
            "field_rows": [
                {
                    "name": "trade_date",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "reason",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "CHARACTERS",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_ASCII",
                },
            ]
        },
        "MappingReceiptV1": {
            "field_rows": [
                {
                    "name": "contract_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["upstox-retained-raw-mapping-receipt@v1"]',
                },
                {
                    "name": "isin",
                    "semantic_type": "ISIN",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "UPPERCASE_ALNUM_12",
                },
                {
                    "name": "exchange",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["NSE"]',
                },
                {
                    "name": "effective_symbol",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "requested_provider_instrument_id",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "snapshot_schema_version",
                    "semantic_type": "INTEGER",
                    "unit": "VERSION",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[1]",
                },
                {
                    "name": "snapshot_source",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "observation_date",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "retrieved_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z_OR_SIX_FRACTIONAL_DIGITS",
                },
                {
                    "name": "observation_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "compressed_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "decompressed_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "compressed_byte_count",
                    "semantic_type": "INTEGER",
                    "unit": "BYTES",
                    "nullability": "REQUIRED",
                    "bounds": "0..4000000",
                },
                {
                    "name": "decompressed_byte_count",
                    "semantic_type": "INTEGER",
                    "unit": "BYTES",
                    "nullability": "REQUIRED",
                    "bounds": "0..50000000",
                },
                {
                    "name": "relative_object_path",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "relative_metadata_path",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "etag",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "CHARACTERS",
                    "nullability": "NULLABLE",
                    "bounds": "PRINTABLE_ASCII_1_TO_512",
                },
                {
                    "name": "last_modified",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "CHARACTERS",
                    "nullability": "NULLABLE",
                    "bounds": "PRINTABLE_ASCII_1_TO_512",
                },
                {
                    "name": "resolved_instrument_key",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "resolved_security_id",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "resolved_symbol",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "resolved_exchange",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "resolved_segment",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "resolved_instrument_type",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "mapping_known_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z_OR_SIX_FRACTIONAL_DIGITS",
                },
                {
                    "name": "mapping_receipt_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
            ]
        },
        "PartitionReceiptV1": {
            "field_rows": [
                {
                    "name": "contract_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["upstox-retained-verified-partition-receipt@v1"]',
                },
                {
                    "name": "isin",
                    "semantic_type": "ISIN",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "UPPERCASE_ALNUM_12",
                },
                {
                    "name": "manifest_schema_version",
                    "semantic_type": "INTEGER",
                    "unit": "VERSION",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[1]",
                },
                {
                    "name": "plan_provider",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "plan_instrument_key",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "plan_security_id",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "plan_symbol",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "plan_exchange",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "plan_segment",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "plan_instrument_type",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "plan_interval",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "plan_year",
                    "semantic_type": "INTEGER",
                    "unit": "YEAR",
                    "nullability": "REQUIRED",
                    "bounds": "ISO_8601_YEAR",
                },
                {
                    "name": "plan_month",
                    "semantic_type": "INTEGER",
                    "unit": "MONTH",
                    "nullability": "REQUIRED",
                    "bounds": "1..12",
                },
                {
                    "name": "plan_from_date",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "plan_to_date",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "ingestion_run_id",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "candle_schema_version",
                    "semantic_type": "INTEGER",
                    "unit": "VERSION",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[1]",
                },
                {
                    "name": "state",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "validation_outcome",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "validation_policy_version",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "actual_from_ts",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z_OR_SIX_FRACTIONAL_DIGITS",
                },
                {
                    "name": "actual_to_ts",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z_OR_SIX_FRACTIONAL_DIGITS",
                },
                {
                    "name": "row_count",
                    "semantic_type": "INTEGER",
                    "unit": "ROWS",
                    "nullability": "REQUIRED",
                    "bounds": "POSITIVE_NO_INVENTED_UPPER_BOUND",
                },
                {
                    "name": "parquet_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "canonical_path",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "source_version",
                    "semantic_type": "ASCII_TEXT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "NONEMPTY_CANONICAL",
                },
                {
                    "name": "manifest_created_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z_OR_SIX_FRACTIONAL_DIGITS",
                },
                {
                    "name": "attempt_started_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z_OR_SIX_FRACTIONAL_DIGITS",
                },
                {
                    "name": "manifest_updated_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z_OR_SIX_FRACTIONAL_DIGITS",
                },
                {
                    "name": "failure_category",
                    "semantic_type": "NULL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "Literal[null]",
                },
                {
                    "name": "schedule_digest_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "partition_receipt_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
            ]
        },
        "SourceReceiptV1": {
            "field_rows": [
                {
                    "name": "schema_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["upstox-retained-raw-historical-ohlcv-receipt@v1"]',
                },
                {
                    "name": "source_profile",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["UPSTOX_RAW"]',
                },
                {
                    "name": "source_policy_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "source_artifact_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "mapping_receipts_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "partition_receipts_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "schedule_evidence_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "observed_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z",
                },
                {
                    "name": "known_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z_OR_SIX_FRACTIONAL_DIGITS",
                },
                {
                    "name": "permitted_use",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["OWNER_PRIVATE_RESEARCH"]',
                },
                {
                    "name": "price_basis",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["RAW"]',
                },
                {
                    "name": "adjustment_state",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["raw"]',
                },
                {
                    "name": "temporal_status",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["REVISED_NON_PIT"]',
                },
                {
                    "name": "corporate_action_status",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["NOT_EVALUATED"]',
                },
                {
                    "name": "comparability_status",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["NOT_ESTABLISHED"]',
                },
            ]
        },
        "HistoricalOhlcvBarV1": {
            "field_rows": [
                {
                    "name": "isin",
                    "semantic_type": "ISIN",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "UPPERCASE_ALNUM_12",
                },
                {
                    "name": "exchange",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["NSE"]',
                },
                {
                    "name": "session",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "open",
                    "semantic_type": "DECIMAL",
                    "unit": "PRICE",
                    "nullability": "REQUIRED",
                    "bounds": "CANONICAL_FINITE_POSITIVE_NONEXPONENT",
                },
                {
                    "name": "high",
                    "semantic_type": "DECIMAL",
                    "unit": "PRICE",
                    "nullability": "REQUIRED",
                    "bounds": "CANONICAL_FINITE_POSITIVE_NONEXPONENT",
                },
                {
                    "name": "low",
                    "semantic_type": "DECIMAL",
                    "unit": "PRICE",
                    "nullability": "REQUIRED",
                    "bounds": "CANONICAL_FINITE_POSITIVE_NONEXPONENT",
                },
                {
                    "name": "close",
                    "semantic_type": "DECIMAL",
                    "unit": "PRICE",
                    "nullability": "REQUIRED",
                    "bounds": "CANONICAL_FINITE_POSITIVE_NONEXPONENT",
                },
                {
                    "name": "volume",
                    "semantic_type": "INTEGER",
                    "unit": "SHARES",
                    "nullability": "REQUIRED",
                    "bounds": "0..9223372036854775807",
                },
                {
                    "name": "known_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z_OR_SIX_FRACTIONAL_DIGITS",
                },
                {
                    "name": "price_basis",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["RAW"]',
                },
            ]
        },
        "GeneratedRevisionRequestV1": {
            "field_rows": [
                {
                    "name": "contract_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "research_scope",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "source_profile",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "operation",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "parent_revision_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "NULLABLE",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "correction_coordinates",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "COORDINATES",
                    "nullability": "REQUIRED",
                    "bounds": "CorrectionCoordinateV1,0..18300",
                },
                {
                    "name": "cohort",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "MEMBERS",
                    "nullability": "REQUIRED",
                    "bounds": "CanonicalListedEquityMemberV1,1..50",
                },
                {
                    "name": "from_session",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "to_session",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "interval",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "expected_sessions",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "SESSIONS",
                    "nullability": "REQUIRED",
                    "bounds": "LOCAL_DATE,1..366",
                },
                {
                    "name": "schedule_evidence_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "source_policy_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "source_artifact_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "receipt_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "observed_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z",
                },
                {
                    "name": "permitted_use",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "price_basis",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "adjustment_state",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "aggregation_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "temporal_status",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "corporate_action_status",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "comparability_status",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "schema_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "runtime_code_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "configuration_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "limits",
                    "semantic_type": "CLOSED_OBJECT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "CompletionLimitsV1",
                },
            ]
        },
        "HistoricalOhlcvRevisionV1": {
            "field_rows": [
                {
                    "name": "contract_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "research_scope",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "source_profile",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "operation",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "parent_revision_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "NULLABLE",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "correction_coordinates",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "COORDINATES",
                    "nullability": "REQUIRED",
                    "bounds": "CorrectionCoordinateV1,0..18300",
                },
                {
                    "name": "cohort",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "MEMBERS",
                    "nullability": "REQUIRED",
                    "bounds": "CanonicalListedEquityMemberV1,1..50",
                },
                {
                    "name": "from_session",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "to_session",
                    "semantic_type": "LOCAL_DATE",
                    "unit": "ISO_8601_DATE",
                    "nullability": "REQUIRED",
                    "bounds": "YYYY_MM_DD",
                },
                {
                    "name": "interval",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "expected_sessions",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "SESSIONS",
                    "nullability": "REQUIRED",
                    "bounds": "LOCAL_DATE,1..366",
                },
                {
                    "name": "schedule_evidence_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "source_policy_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "source_artifact_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "receipt_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "observed_at",
                    "semantic_type": "UTC_INSTANT",
                    "unit": "UTC",
                    "nullability": "REQUIRED",
                    "bounds": "WHOLE_SECOND_Z",
                },
                {
                    "name": "permitted_use",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "price_basis",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "adjustment_state",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "aggregation_version",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "temporal_status",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "corporate_action_status",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "comparability_status",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "FROZEN_RAW_DISCLOSURE_OR_CONTRACT_LITERAL",
                },
                {
                    "name": "schema_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "runtime_code_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "configuration_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "limits",
                    "semantic_type": "CLOSED_OBJECT",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "CompletionLimitsV1",
                },
                {
                    "name": "completion_request_identity_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
                {
                    "name": "lineage_depth",
                    "semantic_type": "INTEGER",
                    "unit": "REVISIONS",
                    "nullability": "REQUIRED",
                    "bounds": "0..128",
                },
                {
                    "name": "context_status",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["HISTORICAL_CONTEXT_NOT_EVALUATED"]',
                },
                {
                    "name": "limitation",
                    "semantic_type": "LITERAL",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": 'Literal["FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION"]',
                },
                {
                    "name": "bars",
                    "semantic_type": "ORDERED_ARRAY",
                    "unit": "BARS",
                    "nullability": "REQUIRED",
                    "bounds": "HistoricalOhlcvBarV1,1..18300",
                },
                {
                    "name": "revision_sha256",
                    "semantic_type": "SHA256",
                    "unit": "NOT_APPLICABLE",
                    "nullability": "REQUIRED",
                    "bounds": "LOWERCASE_64_HEX",
                },
            ]
        },
    },
    "literals": {
        "completion_contract_version": "upstox-raw-fixed-cohort-historical-ohlcv-completion@v1",
        "revision_contract_version": "fixed-cohort-historical-ohlcv-upstox-raw-revision-store@v1",
        "research_scope": "FIXED_COHORT_RETROSPECTIVE",
        "source_profile": "UPSTOX_RAW",
        "provider": "UPSTOX",
        "exchange": "NSE",
        "listed_equity_segment": "EQUITY",
        "interval": "1d",
        "price_basis": "RAW",
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
        "adjustment_state": "raw",
        "aggregation_version": "nse-session-ohlcv@v1",
        "temporal_status": "REVISED_NON_PIT",
        "corporate_action_status": "NOT_EVALUATED",
        "comparability_status": "NOT_ESTABLISHED",
        "context_status": "HISTORICAL_CONTEXT_NOT_EVALUATED",
        "limitation": "FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION",
    },
    "field_closure": {
        "all_serialized_objects": "exact fields only; unknown keys rejected",
        "mapping_receipt_nullable_fields": ["etag", "last_modified"],
        "partition_receipt_failure_category": "required exact null",
        "source_policy_and_receipt": "all fields required non-null",
        "identity_fields": "self identity excluded only from its stated preimage",
    },
    "ordering_cardinality": {
        "cohort": "strictly sorted unique by (isin,exchange), 1..50",
        "expected_sessions": "strictly increasing unique and within inclusive "
        "range, 1..366",
        "correction_coordinates": "sorted unique (isin,exchange,session), 0..18300",
        "mapping_receipts": "cohort order, exactly one per member, 1..50",
        "partition_receipts": "member-major then touched year/month-major, "
        "exactly cohort x months, 1..600",
        "bars": "member-major then session-major complete grid, 1..18300",
        "schedule_sessions": "strict trade-date/open order, unique dates, non-overlap",
        "schedule_closures": "strict trade-date order, unique and disjoint from "
        "sessions",
    },
    "cross_field_state_transitions": {
        "request_operations": {
            "INITIAL": "parent null and corrections empty",
            "APPEND": "parent SHA-256 and corrections empty",
            "CORRECTION": "parent SHA-256 and "
            "nonempty coordinates "
            "within candidate grid",
        },
        "intervals": "symbol and mapping effective intervals cover "
        "inclusive request range; nullable end is "
        "open-ended",
        "grid": "cohort x expected_sessions equals complete bar grid",
        "bar_envelope": "low <= min(open,close) <= max(open,close) <= high",
        "known_at": "mapping evidence at or before observed; bar "
        "known_at at or before observed; source receipt "
        "known_at is maximum bar known_at",
        "partition": "VERIFIED/PASSED with exact null failure_category, nonempty "
        "canonical run/policy text, retained actual bounds in order, and ordered "
        "lifecycle timestamps",
        "lineage": {
            "INITIAL": "depth 0",
            "APPEND": "later contiguous suffix and "
            "byte-identical inherited bars/source",
            "CORRECTION": "same grid; named rows only; immutable parent",
        },
    },
    "identity_preimages_exclusions": {
        "cohort": "SHA-256 canonical ordered complete cohort",
        "completion_request": "SHA-256 exact canonical operator request bytes",
        "mapping_receipt": "SHA-256 canonical receipt excluding "
        "mapping_receipt_identity_sha256",
        "partition_receipt": "SHA-256 canonical receipt excluding "
        "partition_receipt_identity_sha256",
        "mapping_receipts": "SHA-256 canonical ordered receipt-identity list",
        "partition_receipts": "SHA-256 canonical ordered receipt-identity list",
        "schedule": "SHA-256 exact retained canonical schedule bytes",
        "source_artifact": "SHA-256 exact canonical source artifact",
        "source_policy": "SHA-256 exact canonical source policy",
        "source_receipt": "SHA-256 exact canonical source receipt",
        "revision": "SHA-256 canonical revision excluding revision_sha256",
        "schema": "SHA-256 canonical complete schema metadata",
        "configuration": "SHA-256 canonical complete configuration metadata",
        "runtime": "SHA-256 ordered repository-relative runtime manifest",
        "execution_result": "outside persisted schema identity",
    },
    "schedule_version_projections": {
        "v1": {
            "schema_version": 1,
            "fields": [
                "schema_version",
                "source",
                "source_release",
                "as_of",
                "timezone",
                "covered_from",
                "covered_to",
                "sessions",
            ],
            "source_release": "sha256:<64 lowercase hex>",
            "closures": "absent",
            "coverage": "at least one session",
        },
        "v2": {
            "schema_version": 2,
            "fields": [
                "schema_version",
                "source",
                "source_release",
                "as_of",
                "timezone",
                "covered_from",
                "covered_to",
                "sessions",
                "closures",
            ],
            "source_release": "composed-calendar@v1=<64 lowercase hex>",
            "closures": "required list",
            "coverage": "at least one session or closure",
        },
        "v3": {
            "schema_version": 3,
            "fields": [
                "schema_version",
                "source",
                "source_release",
                "as_of",
                "timezone",
                "covered_from",
                "covered_to",
                "sessions",
                "closures",
            ],
            "source_release": "composed-calendar@v1=<64 lowercase hex>",
            "closures": "required list",
            "coverage": "at least one session or closure; "
            "same-local-date future close allowed",
        },
    },
    "failure_precedence": [
        "MALFORMED_INPUT",
        "UNSUPPORTED_CAPABILITY",
        "CONFLICTING_EVIDENCE",
        "INVALID_EVIDENCE",
        "INSUFFICIENT_EVIDENCE",
        "PARENT_LINEAGE_CONFLICT",
        "PUBLICATION_UNCERTAIN_OR_CONFLICT",
        "SUCCESS",
    ],
    "byte_ceilings": {
        "completion_request": 1048576,
        "source_policy": 1048576,
        "source_receipt": 1048576,
        "source_artifact": 134217728,
        "revision": 134217728,
        "schedule": 1000000,
        "mapping_compressed": 4000000,
        "mapping_decompressed": 50000000,
    },
}
_CONFIGURATION_IDENTITY_PREIMAGE: Final = {
    "metadata_version": "fixed-cohort-historical-ohlcv-configuration-identity@v1",
    "limits": _LIMITS,
    "source_profile": {
        "name": "UPSTOX_RAW",
        "source": "UPSTOX_RETAINED_VERIFIED_1M",
        "provider": "UPSTOX",
        "source_version": "upstox-historical-v3",
        "input_interval": "1m",
        "output_interval": "1d",
        "aggregation": _AGGREGATION_VERSION,
        "price_basis": _PRICE_BASIS,
        "adjustment_state": _ADJUSTMENT_STATE,
        "disclosures": {
            "temporal_status": _TEMPORAL_STATUS,
            "corporate_action_status": _CORPORATE_ACTION_STATUS,
            "comparability_status": _COMPARABILITY_STATUS,
            "context_status": _CONTEXT_STATUS,
            "limitation": _LIMITATION,
        },
    },
    "filesystem": {
        "roots": "absolute existing owner-private no-follow source and destination, lexical containment and admitted inode equality rejected",
        "source": "existing lock only and no source mutation",
        "destination": "captured admitted inode for INITIAL and existing writer operations",
        "directory_mode": "0700",
        "lock_mode": "0600",
        "immutable_object_mode": "0400",
        "publication": "create final content-addressed name with O_EXCL at 0600; resume only stable exact-prefix 0600 inode; fchmod immutable 0400; fsync file and parent after visibility; never link, rename, replace, truncate, or unlink visible names; identity-bound exact readback",
        "final_recheck": "source root/catalog/schedule/snapshots/manifests/partition descriptor/checksum/links revalidated before source release",
    },
    "lineage": {
        "mutable_correction_fields": list(_CORRECTION_MUTABLE_FIELDS),
        "append": "full bounded reprojected grid with byte-identical inherited bars",
        "maximum_depth": _LIMITS["max_lineage_depth"],
    },
    "outcomes": [
        "MALFORMED_INPUT",
        "UNSUPPORTED_CAPABILITY",
        "CONFLICTING_EVIDENCE",
        "INVALID_EVIDENCE",
        "INSUFFICIENT_EVIDENCE",
        "PARENT_LINEAGE_CONFLICT",
        "PUBLICATION_UNCERTAIN_OR_CONFLICT",
        "SUCCESS",
    ],
    "cli": {
        "completion": "historical-ohlcv-upstox-raw --request-file ABSOLUTE_PATH [--source-storage-root ABSOLUTE_PATH] --storage-root ABSOLUTE_PATH --output json",
        "read": "historical-ohlcv-upstox-raw-read --storage-root ABSOLUTE_PATH --revision-sha256 LOWERCASE_SHA256 --output json",
        "aliases": "none",
    },
}


class HistoricalOhlcvImportOutcomeV1(StrEnum):
    SUCCESS = "SUCCESS"
    MALFORMED_INPUT = "MALFORMED_INPUT"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
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


def _runtime_root() -> Path:
    source = Path(__file__)
    root = source.parent.parent
    if not source.is_absolute() or root.name != "swing_trading_ai_assistant":
        raise ValueError("historical revision runtime identity invalid")
    return root


def _loaded_runtime_code_identity() -> str:
    try:
        root = _runtime_root()
        pairs: list[tuple[str, str]] = []
        for relative, expected in sorted(
            HISTORICAL_UPSTOX_RAW_RUNTIME_SOURCE_SHA256_V1.items()
        ):
            actual = _sha(read_runtime_source(root, relative))
            if actual != expected:
                raise ValueError
            pairs.append((relative, actual))
        return _sha(_canonical(pairs))
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


def historical_upstox_raw_current_identities_v1() -> tuple[str, str, str]:
    """Return the current raw-store schema, runtime, and configuration identities."""
    return _required_identities()


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
    if type(value) is not str:
        return None
    for pattern in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            parsed = datetime.strptime(value, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
        if parsed.strftime(pattern) == value:
            return parsed
    return None


def _nonempty_canonical_text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _operator_instant(value: object) -> datetime | None:
    return _instant(value) if type(value) is str and len(value) == 20 else None


def _ist_date_text(value: object) -> str | None:
    instant = _instant(value)
    return instant.astimezone(_IST).date().isoformat() if instant is not None else None


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
            "mapping_evidence_known_at",
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
        or mapping.get("provider") != _MAPPING_PROVIDER
        or type(mapping.get("provider_instrument_id")) is not str
        or not _SAFE_TEXT_RE.fullmatch(cast(str, mapping["provider_instrument_id"]))
        or mapping_start is None
        or (mapping_end_raw is not None and mapping_end is None)
        or (mapping_end is not None and mapping_end < mapping_start)
        or (
            member_end is not None
            and member_start is not None
            and member_end < member_start
        )
        or _instant(mapping.get("mapping_evidence_known_at")) is None
        or _digest(mapping.get("mapping_evidence_sha256")) is None
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
        type(request.get("operation")) is not str
        or request.get("contract_version") != _CONTRACT_VERSION
        or request.get("research_scope") != _SCOPE
        or type(request.get("source_profile")) is not str
        or request.get("operation") not in _OPERATION_LITERALS
        or request.get("interval") != _INTERVAL
        or request.get("limits") != _LIMITS
        or type(request.get("permitted_use")) is not str
        or type(request.get("price_basis")) is not str
        or type(request.get("adjustment_state")) is not str
        or type(request.get("aggregation_version")) is not str
        or type(request.get("temporal_status")) is not str
        or type(request.get("corporate_action_status")) is not str
        or type(request.get("comparability_status")) is not str
        or any(
            _digest(request.get(field)) is None
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
        or _operator_instant(request.get("observed_at")) is None
        or type(request.get("parent_revision_sha256")) not in {str, type(None)}
        or (
            request["parent_revision_sha256"] is not None
            and _digest(request["parent_revision_sha256"]) is None
        )
        or type(request.get("correction_coordinates")) is not list
        or type(request.get("cohort")) is not list
        or type(request.get("expected_sessions")) is not list
    ):
        return None
    lower = _date_text(request.get("from_session"))
    upper = _date_text(request.get("to_session"))
    sessions = cast(list[Any], request["expected_sessions"])
    if (
        lower is None
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
        or ((upper.year - lower.year) * 12 + upper.month - lower.month + 1)
        > _LIMITS["max_calendar_months"]
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
    for member in resolved_members:
        symbol_start = _date_text(member["symbol_effective_from"])
        symbol_end = _date_text(member["symbol_effective_to"])
        mapping = cast(dict[str, Any], member["provider_mapping"])
        mapping_start = _date_text(mapping["mapping_effective_from"])
        mapping_end = _date_text(mapping["mapping_effective_to"])
        if (
            symbol_start is None
            or mapping_start is None
            or symbol_start > lower
            or mapping_start > lower
            or (symbol_end is not None and symbol_end < upper)
            or (mapping_end is not None and mapping_end < upper)
        ):
            return None
    for coordinate_value in cast(list[Any], request["correction_coordinates"]):
        if type(coordinate_value) is not dict:
            return None
        coordinate = cast(dict[str, Any], coordinate_value)
        if (
            not _only(coordinate, frozenset({"isin", "exchange", "session"}))
            or type(coordinate.get("isin")) is not str
            or not _ISIN_RE.fullmatch(cast(str, coordinate["isin"]))
            or coordinate.get("exchange") != "NSE"
            or _date_text(coordinate.get("session")) is None
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
    candidate_grid = {
        (member["isin"], member["exchange"], session)
        for member in resolved_members
        for session in cast(list[str], request["expected_sessions"])
    }
    if request["operation"] == "INITIAL" and (
        request["parent_revision_sha256"] is not None or coordinate_keys
    ):
        return None
    if request["operation"] == "APPEND" and (
        request["parent_revision_sha256"] is None or coordinate_keys
    ):
        return None
    if request["operation"] == "CORRECTION" and (
        request["parent_revision_sha256"] is None
        or not coordinate_keys
        or any(coordinate not in candidate_grid for coordinate in coordinate_keys)
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
    policy_fields = frozenset(
        {
            "schema_version",
            "source_profile",
            "source_name",
            "provider",
            "source_version",
            "source_interval",
            "output_interval",
            "aggregation_version",
            "price_basis",
            "adjustment_state",
            "temporal_status",
            "corporate_action_status",
            "comparability_status",
            "permitted_use",
            "artifact_sha256",
        }
    )
    receipt_fields = frozenset(
        {
            "schema_version",
            "source_profile",
            "source_policy_sha256",
            "source_artifact_sha256",
            "mapping_receipts_identity_sha256",
            "partition_receipts_identity_sha256",
            "schedule_evidence_sha256",
            "observed_at",
            "known_at",
            "permitted_use",
            "price_basis",
            "adjustment_state",
            "temporal_status",
            "corporate_action_status",
            "comparability_status",
        }
    )
    artifact_fields = frozenset(
        {
            "schema_version",
            "source_profile",
            "schedule",
            "mapping_receipts",
            "partition_receipts",
            "bars",
        }
    )
    if not (
        _only(policy, policy_fields)
        and _only(receipt, receipt_fields)
        and _only(artifact, artifact_fields)
        and all(type(value) is str for value in policy.values())
        and all(type(value) is str for value in receipt.values())
        and type(artifact.get("schema_version")) is str
        and type(artifact.get("source_profile")) is str
        and type(artifact.get("schedule")) is dict
        and type(artifact.get("mapping_receipts")) is list
        and type(artifact.get("partition_receipts")) is list
        and type(artifact.get("bars")) is list
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
    for collection, identity_field in (
        (artifact["mapping_receipts"], "mapping_receipt_identity_sha256"),
        (artifact["partition_receipts"], "partition_receipt_identity_sha256"),
    ):
        for value in cast(list[Any], collection):
            if (
                type(value) is not dict
                or type(cast(dict[str, Any], value).get(identity_field)) is not str
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
            request["source_profile"] != "UPSTOX_RAW",
            request["permitted_use"] != _PERMITTED_USE,
            request["price_basis"] != _PRICE_BASIS,
            request["adjustment_state"] != _ADJUSTMENT_STATE,
            request["aggregation_version"] != _AGGREGATION_VERSION,
            any(
                member["provider_mapping"]["provider"] != _MAPPING_PROVIDER
                for member in cast(list[dict[str, Any]], request["cohort"])
            ),
            policy["schema_version"]
            != "upstox-retained-raw-historical-ohlcv-source-policy@v1",
            policy["source_profile"] != "UPSTOX_RAW",
            policy["source_name"] != "UPSTOX_RETAINED_VERIFIED_1M",
            policy["provider"] != "UPSTOX",
            policy["source_version"] != "upstox-historical-v3",
            request["adjustment_state"] != _ADJUSTMENT_STATE,
            request["aggregation_version"] != _AGGREGATION_VERSION,
            request["temporal_status"] != _TEMPORAL_STATUS,
            request["corporate_action_status"] != _CORPORATE_ACTION_STATUS,
            request["comparability_status"] != _COMPARABILITY_STATUS,
            policy["source_interval"] != "1m",
            policy["output_interval"] != _INTERVAL,
            policy["aggregation_version"] != _AGGREGATION_VERSION,
            policy["price_basis"] != _PRICE_BASIS,
            policy["adjustment_state"] != _ADJUSTMENT_STATE,
            policy["permitted_use"] != _PERMITTED_USE,
            policy["temporal_status"] != _TEMPORAL_STATUS,
            policy["corporate_action_status"] != _CORPORATE_ACTION_STATUS,
            policy["comparability_status"] != _COMPARABILITY_STATUS,
            artifact["schema_version"]
            != "upstox-retained-raw-historical-ohlcv-artifact@v1",
            artifact["source_profile"] != "UPSTOX_RAW",
            receipt["schema_version"]
            != "upstox-retained-raw-historical-ohlcv-receipt@v1",
            receipt["source_profile"] != "UPSTOX_RAW",
            receipt["permitted_use"] != _PERMITTED_USE,
            receipt["price_basis"] != _PRICE_BASIS,
            receipt["adjustment_state"] != _ADJUSTMENT_STATE,
            receipt["temporal_status"] != _TEMPORAL_STATUS,
            receipt["corporate_action_status"] != _CORPORATE_ACTION_STATUS,
            receipt["comparability_status"] != _COMPARABILITY_STATUS,
            any(
                row["price_basis"] != _PRICE_BASIS
                for row in cast(list[dict[str, Any]], artifact["bars"])
            ),
        )
    )


def _validate_closed_receipts(  # noqa: C901 - one closed source-evidence boundary
    request: dict[str, Any], artifact: dict[str, Any], receipt: dict[str, Any]
) -> bool:
    if (
        not _only(receipt, _SOURCE_RECEIPT_FIELDS)
        or receipt.get("schema_version")
        != "upstox-retained-raw-historical-ohlcv-receipt@v1"
        or receipt.get("source_profile") != "UPSTOX_RAW"
        or any(
            _digest(receipt.get(field)) is None
            for field in (
                "source_policy_sha256",
                "source_artifact_sha256",
                "mapping_receipts_identity_sha256",
                "partition_receipts_identity_sha256",
                "schedule_evidence_sha256",
            )
        )
        or receipt.get("schedule_evidence_sha256")
        != request["schedule_evidence_sha256"]
        or receipt.get("observed_at") != request["observed_at"]
        or _operator_instant(receipt.get("observed_at")) is None
        or _instant(receipt.get("known_at")) is None
        or receipt.get("permitted_use") != _PERMITTED_USE
        or receipt.get("price_basis") != _PRICE_BASIS
        or receipt.get("adjustment_state") != _ADJUSTMENT_STATE
        or receipt.get("temporal_status") != _TEMPORAL_STATUS
        or receipt.get("corporate_action_status") != _CORPORATE_ACTION_STATUS
        or receipt.get("comparability_status") != _COMPARABILITY_STATUS
    ):
        return False
    try:
        schedule = parse_canonical_schedule_bytes(
            _canonical(cast(dict[str, Any], artifact["schedule"]))
        )
    except (TypeError, ValueError):
        return False
    observed = _operator_instant(request["observed_at"])
    if observed is None or schedule.as_of > observed:
        return False
    expected_sessions = cast(list[str], request["expected_sessions"])
    lower = _date_text(request["from_session"])
    upper = _date_text(request["to_session"])
    if lower is None or upper is None:
        return False
    if [
        session.trade_date.isoformat()
        for session in schedule.sessions
        if lower <= session.trade_date <= upper
    ] != expected_sessions:
        return False
    cohort = cast(list[dict[str, Any]], request["cohort"])
    mappings = cast(list[Any], artifact["mapping_receipts"])
    if len(mappings) != len(cohort):
        return False
    for mapping_value, member in zip(mappings, cohort, strict=True):
        if type(mapping_value) is not dict:
            return False
        mapping = cast(dict[str, Any], mapping_value)
        if (
            not _only(mapping, _MAPPING_RECEIPT_FIELDS)
            or mapping.get("contract_version")
            != "upstox-retained-raw-mapping-receipt@v1"
            or mapping.get("isin") != member["isin"]
            or mapping.get("exchange") != member["exchange"]
            or mapping.get("effective_symbol") != member["effective_symbol"]
            or mapping.get("requested_provider_instrument_id")
            != member["provider_mapping"]["provider_instrument_id"]
            or mapping.get("mapping_known_at")
            != member["provider_mapping"]["mapping_evidence_known_at"]
            or mapping.get("observation_sha256")
            != member["provider_mapping"]["mapping_evidence_sha256"]
            or mapping.get("snapshot_source") != "upstox-bod-nse"
            or mapping.get("resolved_instrument_key")
            != mapping.get("requested_provider_instrument_id")
            or mapping.get("resolved_security_id") != member["isin"]
            or mapping.get("resolved_symbol") != member["effective_symbol"]
            or mapping.get("resolved_exchange") != member["exchange"]
            or mapping.get("resolved_segment") != "NSE_EQ"
            or mapping.get("resolved_instrument_type") != "EQ"
            or mapping.get("observation_date")
            != str(mapping.get("mapping_known_at"))[:10]
            or _instant(mapping.get("retrieved_at")) is None
            or _instant(mapping.get("mapping_known_at")) is None
            or cast(datetime, _instant(mapping.get("retrieved_at"))) > observed
            or mapping.get("retrieved_at") != mapping.get("mapping_known_at")
            or any(
                _digest(mapping.get(field)) is None
                for field in (
                    "observation_sha256",
                    "compressed_sha256",
                    "decompressed_sha256",
                    "mapping_receipt_identity_sha256",
                )
            )
            or mapping.get("snapshot_schema_version") != 1
            or mapping.get("relative_object_path")
            != "instrument_snapshots/sha256="
            + str(mapping.get("compressed_sha256"))
            + "/snapshot.json.gz"
            or mapping.get("relative_metadata_path")
            != "instrument_snapshots/sha256="
            + str(mapping.get("compressed_sha256"))
            + "/observations/sha256="
            + str(mapping.get("observation_sha256"))
            + ".json"
            or type(mapping.get("compressed_byte_count")) is not int
            or type(mapping.get("decompressed_byte_count")) is not int
            or not 0 <= mapping["compressed_byte_count"] <= 4_000_000
            or not 0 <= mapping["decompressed_byte_count"] <= 50_000_000
            or mapping.get("observation_date")
            != _ist_date_text(mapping.get("mapping_known_at"))
            or any(
                type(mapping.get(field)) is not str
                for field in (
                    "snapshot_source",
                    "observation_date",
                    "relative_object_path",
                    "relative_metadata_path",
                    "resolved_instrument_key",
                    "resolved_security_id",
                    "resolved_symbol",
                    "resolved_exchange",
                    "resolved_segment",
                    "resolved_instrument_type",
                )
            )
            or any(
                value is not None
                and (
                    type(value) is not str
                    or _SNAPSHOT_HEADER_RE.fullmatch(value) is None
                )
                for value in (mapping.get("etag"), mapping.get("last_modified"))
            )
        ):
            return False
        identity = mapping["mapping_receipt_identity_sha256"]
        projection = dict(mapping)
        del projection["mapping_receipt_identity_sha256"]
        if _sha(_canonical(projection)) != identity:
            return False
    expected_months = [
        (year, month)
        for year in range(lower.year, upper.year + 1)
        for month in range(1, 13)
        if (year, month) >= (lower.year, lower.month)
        and (year, month) <= (upper.year, upper.month)
    ]
    partitions = cast(list[Any], artifact["partition_receipts"])
    if len(partitions) != len(cohort) * len(expected_months):
        return False
    for partition_value, (member, (year, month)) in zip(
        partitions,
        ((member, month_key) for member in cohort for month_key in expected_months),
        strict=True,
    ):
        if type(partition_value) is not dict:
            return False
        partition = cast(dict[str, Any], partition_value)
        timestamps = [
            _instant(partition.get(field))
            for field in (
                "manifest_created_at",
                "attempt_started_at",
                "manifest_updated_at",
            )
        ]
        actual_from = _instant(partition.get("actual_from_ts"))
        actual_to = _instant(partition.get("actual_to_ts"))
        if (
            not _only(partition, _PARTITION_RECEIPT_FIELDS)
            or partition.get("contract_version")
            != "upstox-retained-verified-partition-receipt@v1"
            or partition.get("isin") != member["isin"]
            or partition.get("plan_security_id") != member["isin"]
            or partition.get("plan_provider") != "upstox"
            or partition.get("plan_instrument_key")
            != member["provider_mapping"]["provider_instrument_id"]
            or partition.get("plan_symbol") != member["effective_symbol"]
            or partition.get("plan_exchange") != "NSE"
            or partition.get("plan_segment") != "NSE_EQ"
            or partition.get("plan_instrument_type") != "EQ"
            or partition.get("plan_interval") != "1m"
            or partition.get("plan_year") != year
            or partition.get("plan_month") != month
            or partition.get("state") != "VERIFIED"
            or partition.get("validation_outcome") != "PASSED"
            or partition.get("failure_category") is not None
            or partition.get("source_version") != "upstox-historical-v3"
            or request["operation"] == "INITIAL"
            and partition.get("schedule_digest_sha256")
            != request["schedule_evidence_sha256"]
            or any(timestamp is None for timestamp in timestamps)
            or cast(list[datetime], timestamps)
            != sorted(cast(list[datetime], timestamps))
            or cast(list[datetime], timestamps)[-1] > observed
            or any(
                _digest(partition.get(field)) is None
                for field in (
                    "parquet_sha256",
                    "schedule_digest_sha256",
                    "partition_receipt_identity_sha256",
                )
            )
            or partition.get("manifest_schema_version") != 1
            or partition.get("candle_schema_version") != 1
            or partition.get("plan_from_date") != f"{year:04d}-{month:02d}-01"
            or partition.get("plan_to_date")
            != f"{year:04d}-{month:02d}-{monthrange(year, month)[1]:02d}"
            or partition.get("canonical_path")
            != f"candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
            f"instrument_type=EQ/security_id={member['isin']}/interval=1m/"
            f"year={year:04d}/month={month:02d}/bars.parquet"
            or any(
                type(partition.get(field)) is not str
                for field in (
                    "plan_security_id",
                    "plan_from_date",
                    "plan_to_date",
                    "ingestion_run_id",
                    "validation_policy_version",
                    "actual_from_ts",
                    "actual_to_ts",
                    "canonical_path",
                )
            )
            or any(
                not _nonempty_canonical_text(partition.get(field))
                for field in ("ingestion_run_id", "validation_policy_version")
            )
            or actual_from is None
            or actual_to is None
            or actual_from > actual_to
            or type(partition.get("row_count")) is not int
            or partition["row_count"] <= 0
        ):
            return False
        identity = partition["partition_receipt_identity_sha256"]
        projection = dict(partition)
        del projection["partition_receipt_identity_sha256"]
        if _sha(_canonical(projection)) != identity:
            return False
    return _receipt_aggregate_matches(
        mappings,
        "mapping_receipt_identity_sha256",
        receipt["mapping_receipts_identity_sha256"],
    ) and _receipt_aggregate_matches(
        partitions,
        "partition_receipt_identity_sha256",
        receipt["partition_receipts_identity_sha256"],
    )


def validate_generated_source_candidate_v1(
    request: object,
    policy: object,
    artifact: object,
    receipt: object,
    completion_request_identity_sha256: object,
) -> bool:
    """Validate a generated raw candidate without destination authority."""
    if (
        type(request) is not dict
        or type(policy) is not dict
        or type(artifact) is not dict
        or type(receipt) is not dict
        or _digest(completion_request_identity_sha256) is None
    ):
        return False
    request_value = cast(dict[str, Any], request)
    policy_value = cast(dict[str, Any], policy)
    artifact_value = cast(dict[str, Any], artifact)
    receipt_value = cast(dict[str, Any], receipt)
    policy_fields = {
        "schema_version": "upstox-retained-raw-historical-ohlcv-source-policy@v1",
        "source_profile": "UPSTOX_RAW",
        "source_name": "UPSTOX_RETAINED_VERIFIED_1M",
        "provider": "UPSTOX",
        "source_version": "upstox-historical-v3",
        "source_interval": "1m",
        "output_interval": "1d",
        "aggregation_version": "nse-session-ohlcv@v1",
        "price_basis": "RAW",
        "adjustment_state": "raw",
        "temporal_status": "REVISED_NON_PIT",
        "corporate_action_status": "NOT_EVALUATED",
        "comparability_status": "NOT_ESTABLISHED",
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
    }
    if (
        frozenset(policy_value) != frozenset({*policy_fields, "artifact_sha256"})
        or any(
            policy_value.get(field) != value for field, value in policy_fields.items()
        )
        or _digest(policy_value.get("artifact_sha256")) is None
        or frozenset(artifact_value)
        != frozenset(
            {
                "schema_version",
                "source_profile",
                "schedule",
                "mapping_receipts",
                "partition_receipts",
                "bars",
            }
        )
        or artifact_value.get("schema_version")
        != "upstox-retained-raw-historical-ohlcv-artifact@v1"
        or artifact_value.get("source_profile") != "UPSTOX_RAW"
        or receipt_value.get("source_policy_sha256") != _sha(_canonical(policy_value))
        or receipt_value.get("source_artifact_sha256")
        != _sha(_canonical(artifact_value))
        or receipt_value.get("schedule_evidence_sha256")
        != request_value.get("schedule_evidence_sha256")
        or receipt_value.get("observed_at") != request_value.get("observed_at")
        or receipt_value.get("source_profile") != policy_value.get("source_profile")
        or policy_value.get("artifact_sha256") != _sha(_canonical(artifact_value))
        or not _validate_closed_receipts(request_value, artifact_value, receipt_value)
    ):
        return False
    bars = _validate_bars(request_value, artifact_value)
    if bars is None:
        return False
    known_at = [_instant(row["known_at"]) for row in bars]
    return all(value is not None for value in known_at) and _instant(
        receipt_value.get("known_at")
    ) == max(cast(list[datetime], known_at))


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
    observed = _instant(request["observed_at"])
    if (
        len(rows) != len(expected_keys)
        or len(rows) > _LIMITS["max_rows"]
        or observed is None
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
            or int(volume) > _MAX_DAILY_VOLUME
            or known_at is None
            or known_at > observed
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
        or _digest(policy["artifact_sha256"]) is None
        or policy["artifact_sha256"] != request["source_artifact_sha256"]
        or receipt["source_policy_sha256"] != request["source_policy_sha256"]
        or receipt["source_artifact_sha256"] != request["source_artifact_sha256"]
        or receipt["schedule_evidence_sha256"] != request["schedule_evidence_sha256"]
        or receipt["observed_at"] != request["observed_at"]
        or receipt["schema_version"]
        != "upstox-retained-raw-historical-ohlcv-receipt@v1"
        or receipt["source_profile"] != "UPSTOX_RAW"
    ):
        return None
    bars = _validate_bars(request, artifact)
    if bars is None or not _validate_closed_receipts(request, artifact, receipt):
        return None
    bar_known_at = [_instant(row["known_at"]) for row in bars]
    if any(value is None for value in bar_known_at) or _instant(
        receipt["known_at"]
    ) != max(cast(list[datetime], bar_known_at)):
        return None
    candidate_coordinates = {_coordinate(row) for row in bars}
    if request["operation"] == "CORRECTION" and any(
        _coordinate(coordinate) not in candidate_coordinates
        for coordinate in cast(list[dict[str, Any]], request["correction_coordinates"])
    ):
        return None
    return bars


def _receipt_aggregate_matches(
    values: list[Any], identity_field: str, expected: object
) -> bool:
    if _digest(expected) is None:
        return False
    identities: list[str] = []
    for value in values:
        if type(value) is not dict:
            return False
        receipt = cast(dict[str, Any], value)
        identity = receipt.get(identity_field)
        if _digest(identity) is None:
            return False
        preimage = dict(receipt)
        preimage.pop(identity_field, None)
        if _sha(_canonical(preimage)) != identity:
            return False
        identities.append(cast(str, identity))
    return _sha(_canonical(identities)) == expected


def _request_projection_from_revision(value: dict[str, Any]) -> dict[str, Any]:
    if not _only(value, _REVISION_FIELDS):
        raise RuntimeError
    return {field: value[field] for field in _REQUEST_FIELDS}


def _revision_value(
    request: dict[str, Any],
    bars: list[dict[str, Any]],
    depth: int,
    completion_request_identity_sha256: str,
) -> dict[str, Any]:
    value = {field: request[field] for field in _REQUEST_FIELDS}
    value.update(
        {
            "completion_request_identity_sha256": completion_request_identity_sha256,
            "lineage_depth": depth,
            "context_status": _CONTEXT_STATUS,
            "limitation": _LIMITATION,
            "bars": bars,
        }
    )
    value["revision_sha256"] = _sha(_canonical(value))
    return value


def _coordinate(row: dict[str, Any]) -> tuple[str, str, str]:
    return cast(str, row["isin"]), cast(str, row["exchange"]), cast(str, row["session"])


def _partition_receipts_by_coordinate(
    artifact: dict[str, Any],
) -> dict[tuple[str, int, int], dict[str, Any]] | None:
    receipts = artifact.get("partition_receipts")
    if type(receipts) is not list:
        return None
    result: dict[tuple[str, int, int], dict[str, Any]] = {}
    for candidate in cast(list[Any], receipts):
        if type(candidate) is not dict:
            return None
        value = cast(dict[str, Any], candidate)
        if (
            type(value.get("isin")) is not str
            or type(value.get("plan_year")) is not int
            or type(value.get("plan_month")) is not int
        ):
            return None
        key = (
            cast(str, value["isin"]),
            cast(int, value["plan_year"]),
            cast(int, value["plan_month"]),
        )
        if key in result:
            return None
        result[key] = value
    return result


def _same_inherited_partition_receipt(
    parent: dict[str, Any], child: dict[str, Any]
) -> bool:
    return _canonical(parent) == _canonical(child)


def _inherited_receipts_match(
    request: dict[str, Any],
    parent_artifact: dict[str, Any],
    artifact: dict[str, Any],
    coordinate_keys: list[tuple[str, str, str]],
) -> bool:
    parent_mappings = parent_artifact.get("mapping_receipts")
    mappings = artifact.get("mapping_receipts")
    parent_partitions = _partition_receipts_by_coordinate(parent_artifact)
    partitions = _partition_receipts_by_coordinate(artifact)
    if (
        type(parent_mappings) is not list
        or type(mappings) is not list
        or _canonical(cast(list[Any], parent_mappings))
        != _canonical(cast(list[Any], mappings))
        or parent_partitions is None
        or partitions is None
    ):
        return False
    if request["operation"] == "APPEND":
        return all(
            key in partitions
            and _same_inherited_partition_receipt(parent_receipt, partitions[key])
            for key, parent_receipt in parent_partitions.items()
        ) and all(
            partition["schedule_digest_sha256"] == request["schedule_evidence_sha256"]
            for key, partition in partitions.items()
            if key not in parent_partitions
        )
    if set(parent_partitions) != set(partitions):
        return False
    mutable_coordinates = {
        (isin, date.fromisoformat(session).year, date.fromisoformat(session).month)
        for isin, _, session in coordinate_keys
    }
    return all(
        _same_inherited_partition_receipt(parent_receipt, partitions[key])
        or (
            key in mutable_coordinates
            and partitions[key]["schedule_digest_sha256"]
            == request["schedule_evidence_sha256"]
        )
        for key, parent_receipt in parent_partitions.items()
    )


def _validate_transition(  # noqa: C901 - one closed lineage boundary
    request: dict[str, Any],
    bars: list[dict[str, Any]],
    parent: dict[str, Any] | None,
    parent_artifact: dict[str, Any] | None = None,
    artifact: dict[str, Any] | None = None,
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
    if (parent_artifact is None) != (artifact is None) or (
        parent_artifact is not None
        and artifact is not None
        and not _inherited_receipts_match(
            request, parent_artifact, artifact, coordinate_keys
        )
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
    try:
        _assert_directory_edge(parent, name, descriptor)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_existing_directory(parent: int, name: str) -> int:
    os.fsync(parent)
    descriptor = os.open(
        name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
    )
    try:
        _assert_directory_edge(parent, name, descriptor)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _assert_directory_edge(parent: int, name: str, descriptor: int) -> None:
    held = os.fstat(descriptor)
    named = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (
        not stat.S_ISDIR(held.st_mode)
        or held.st_uid != os.geteuid()
        or stat.S_IMODE(held.st_mode) != _DIRECTORY_MODE
        or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)
    ):
        raise RuntimeError


def _assert_owner_private_directory(descriptor: int) -> None:
    info = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise RuntimeError


def _read_object(
    parent: int,
    name: str,
    maximum: int,
    expected_identity: tuple[int, int] | None = None,
) -> bytes:
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
            or (
                expected_identity is not None
                and (before.st_dev, before.st_ino) != expected_identity
            )
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
            or (
                expected_identity is not None
                and (after.st_dev, after.st_ino) != expected_identity
            )
        ):
            raise RuntimeError
        return bytes(raw)
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, raw[offset:])
        if written <= 0:
            raise RuntimeError
        offset += written


def _assert_final_descriptor(
    parent: int,
    name: str,
    descriptor: int,
    *,
    mode: int,
    size: int,
    identity: tuple[int, int] | None = None,
) -> tuple[int, int]:
    held = os.fstat(descriptor)
    named = os.stat(name, dir_fd=parent, follow_symlinks=False)
    actual_identity = (held.st_dev, held.st_ino)
    if (
        not stat.S_ISREG(held.st_mode)
        or held.st_uid != os.geteuid()
        or stat.S_IMODE(held.st_mode) != mode
        or held.st_nlink != 1
        or held.st_size != size
        or actual_identity != (named.st_dev, named.st_ino)
        or (identity is not None and actual_identity != identity)
    ):
        raise RuntimeError
    return actual_identity


def _admit_final_name(
    parent: int, name: str, maximum: int
) -> tuple[int, tuple[int, int], int]:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent
    )
    try:
        held = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        identity = (held.st_dev, held.st_ino)
        mode = stat.S_IMODE(held.st_mode)
        if (
            not stat.S_ISREG(held.st_mode)
            or held.st_uid != os.geteuid()
            or mode not in (0o600, _IMMUTABLE_FILE_MODE)
            or held.st_nlink != 1
            or held.st_size > maximum
            or identity != (named.st_dev, named.st_ino)
        ):
            raise RuntimeError
        return mode, identity, descriptor
    except Exception:
        os.close(descriptor)
        raise


def _fsync_immutable_object(
    parent: int,
    name: str,
    descriptor: int,
    size: int,
    identity: tuple[int, int],
) -> None:
    _assert_final_descriptor(
        parent,
        name,
        descriptor,
        mode=_IMMUTABLE_FILE_MODE,
        size=size,
        identity=identity,
    )
    os.fsync(descriptor)
    _assert_final_descriptor(
        parent,
        name,
        descriptor,
        mode=_IMMUTABLE_FILE_MODE,
        size=size,
        identity=identity,
    )


def _accept_existing_immutable(
    parent: int,
    name: str,
    raw: bytes,
    identity: tuple[int, int],
    descriptor: int,
) -> bool:
    if _read_object(parent, name, len(raw), identity) != raw:
        raise RuntimeError
    _fsync_immutable_object(parent, name, descriptor, len(raw), identity)
    os.fsync(parent)
    return False


def _resume_direct_final(
    parent: int, name: str, raw: bytes, admitted_identity: tuple[int, int]
) -> bool:
    descriptor = os.open(
        name, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent
    )
    try:
        before = os.fstat(descriptor)
        identity = _assert_final_descriptor(
            parent,
            name,
            descriptor,
            mode=0o600,
            size=before.st_size,
            identity=admitted_identity,
        )
        if before.st_size > len(raw):
            raise RuntimeError
        observed = bytearray()
        while len(observed) <= len(raw):
            chunk = os.read(descriptor, min(65_536, len(raw) + 1 - len(observed)))
            if not chunk:
                break
            observed.extend(chunk)
        existing = bytes(observed)
        if len(existing) != before.st_size or not raw.startswith(existing):
            raise RuntimeError
        _assert_final_descriptor(
            parent,
            name,
            descriptor,
            mode=0o600,
            size=len(existing),
            identity=identity,
        )
        if os.lseek(descriptor, len(existing), os.SEEK_SET) != len(existing):
            raise RuntimeError
        _write_all(descriptor, raw[len(existing) :])
        os.fchmod(descriptor, _IMMUTABLE_FILE_MODE)
        _assert_final_descriptor(
            parent,
            name,
            descriptor,
            mode=_IMMUTABLE_FILE_MODE,
            size=len(raw),
            identity=identity,
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.fsync(parent)
    if _read_object(parent, name, len(raw), identity) != raw:
        raise RuntimeError
    return True


def _accept_admitted_final(
    parent: int,
    name: str,
    raw: bytes,
    mode: int,
    identity: tuple[int, int],
    descriptor: int,
) -> bool:
    try:
        if mode == _IMMUTABLE_FILE_MODE:
            return _accept_existing_immutable(parent, name, raw, identity, descriptor)
        if mode == 0o600:
            return _resume_direct_final(parent, name, raw, identity)
        raise RuntimeError
    finally:
        os.close(descriptor)


def _publish_object(parent: int, name: str, raw: bytes) -> bool:
    try:
        mode, identity, admitted_descriptor = _admit_final_name(parent, name, len(raw))
    except FileNotFoundError:
        pass
    else:
        return _accept_admitted_final(
            parent, name, raw, mode, identity, admitted_descriptor
        )
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent,
        )
    except FileExistsError:
        mode, identity, admitted_descriptor = _admit_final_name(parent, name, len(raw))
        return _accept_admitted_final(
            parent, name, raw, mode, identity, admitted_descriptor
        )
    try:
        identity = _assert_final_descriptor(
            parent, name, descriptor, mode=0o600, size=0
        )
        _write_all(descriptor, raw)
        os.fchmod(descriptor, _IMMUTABLE_FILE_MODE)
        _assert_final_descriptor(
            parent,
            name,
            descriptor,
            mode=_IMMUTABLE_FILE_MODE,
            size=len(raw),
            identity=identity,
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.fsync(parent)
    if _read_object(parent, name, len(raw), identity) != raw:
        raise RuntimeError
    return True


def _initial_root_allows_hierarchy(root: int) -> bool:
    entries = set(os.listdir(root))
    return entries in (
        {".ingestion.lock"},
        {".ingestion.lock", _ROOT_DIRECTORY},
    )


def _assert_hierarchy_live(
    operation: StorageRootLeaseOperation,
    root: int,
    profile: int,
    version: int,
    objects: int,
    revisions: int,
) -> None:
    operation.ensure_live()
    _assert_directory_edge(operation.descriptor, _ROOT_DIRECTORY, root)
    _assert_directory_edge(root, _PROFILE_DIRECTORY, profile)
    _assert_directory_edge(profile, _SCHEMA_DIRECTORY, version)
    _assert_directory_edge(version, _OBJECT_DIRECTORY, objects)
    _assert_directory_edge(version, _REVISION_DIRECTORY, revisions)


def _storage_root_is_exact(root: int) -> bool:
    return set(os.listdir(root)) == {".ingestion.lock", _ROOT_DIRECTORY}


def _initial_hierarchy_is_exact(root: int, profile: int, version: int) -> bool:
    return (
        set(os.listdir(root)) == {_PROFILE_DIRECTORY}
        and set(os.listdir(profile)) == {_SCHEMA_DIRECTORY}
        and set(os.listdir(version)) == {_OBJECT_DIRECTORY, _REVISION_DIRECTORY}
    )


def _initial_exact_replay_objects_match(
    objects: int,
    revisions: int,
    candidate_objects: tuple[tuple[str, bytes], ...],
    revision_name: str,
) -> bool:
    expected = dict(candidate_objects)
    return (
        set(os.listdir(revisions)) == {revision_name}
        and set(os.listdir(objects)) == set(expected)
        and all(
            _read_object(objects, name, len(raw)) == raw
            for name, raw in expected.items()
        )
    )


def _initial_partial_source_objects_match(
    objects: int,
    revisions: int,
    candidate_objects: tuple[tuple[str, bytes], ...],
    revision_name: str,
) -> bool:
    return set(os.listdir(revisions)) <= {revision_name} and set(
        os.listdir(objects)
    ) <= {name for name, _ in candidate_objects}


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

    def _preflight_parent_lineage(
        self, request: dict[str, Any], bars: list[dict[str, Any]]
    ) -> HistoricalOhlcvImportOutcomeV1:
        if request["operation"] == "INITIAL":
            return _validate_transition(request, bars, None)[1]
        parent_result = self.read_exact(request["parent_revision_sha256"])
        if (
            parent_result.outcome is not HistoricalOhlcvImportOutcomeV1.SUCCESS
            or parent_result.revision is None
        ):
            return HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT
        return _validate_transition(request, bars, parent_result.revision)[1]

    def _artifact_for_revision(
        self, revision: dict[str, Any], objects: int
    ) -> dict[str, Any]:
        raw = _read_object(
            objects,
            cast(str, revision["source_artifact_sha256"]),
            _LIMITS["max_artifact_bytes"],
        )
        artifact = _closed_json(raw, _LIMITS["max_artifact_bytes"])
        if type(artifact) is not dict:
            raise RuntimeError
        return artifact

    def _publish_generated_source(  # noqa: C901 - one publication transaction boundary
        self,
        request_raw: object,
        source_policy_raw: object,
        source_artifact_raw: object,
        receipt_raw: object,
        *,
        completion_request_identity_sha256: object,
    ) -> HistoricalOhlcvImportResultV1:
        candidate = _parse_import_candidate_structure(
            request_raw, source_policy_raw, source_artifact_raw, receipt_raw
        )
        if candidate is None:
            return _result(HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT)
        request, policy, artifact, receipt = candidate
        if (
            not _validate_current_request_identity(request)
            or _digest(completion_request_identity_sha256) is None
        ):
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
        revision = _revision_value(
            request,
            bars,
            depth,
            cast(str, completion_request_identity_sha256),
        )
        revision_raw = _canonical(revision)
        revision_id = cast(str, revision["revision_sha256"])
        if len(revision_raw) > _LIMITS["max_revision_bytes"]:
            return _result(HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT)
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
                if request[
                    "operation"
                ] == "INITIAL" and not _initial_root_allows_hierarchy(
                    operation.descriptor
                ):
                    return _result(
                        HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
                    )
                root = _open_directory(operation.descriptor, _ROOT_DIRECTORY)
                try:
                    profile = _open_directory(root, _PROFILE_DIRECTORY)
                    try:
                        version = _open_directory(profile, _SCHEMA_DIRECTORY)
                        try:
                            with ExitStack() as directories:
                                objects = _open_directory(version, _OBJECT_DIRECTORY)
                                directories.callback(os.close, objects)
                                revisions = _open_directory(
                                    version, _REVISION_DIRECTORY
                                )
                                directories.callback(os.close, revisions)
                                if not _storage_root_is_exact(operation.descriptor):
                                    return _result(
                                        HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
                                    )
                                candidate_source_objects = (
                                    (request["source_policy_sha256"], source_policy),
                                    (
                                        request["source_artifact_sha256"],
                                        source_artifact,
                                    ),
                                    (request["receipt_sha256"], source_receipt),
                                )
                                if request[
                                    "operation"
                                ] == "INITIAL" and not _initial_hierarchy_is_exact(
                                    root, profile, version
                                ):
                                    return _result(
                                        HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
                                    )
                                if request["operation"] != "INITIAL":
                                    verified_parent = (
                                        self._read_stored_exact_from_directories(
                                            cast(
                                                str,
                                                request["parent_revision_sha256"],
                                            ),
                                            objects,
                                            revisions,
                                        )
                                    )
                                    parent_artifact = self._artifact_for_revision(
                                        verified_parent, objects
                                    )
                                    verified_depth, verified_outcome = (
                                        _validate_transition(
                                            request,
                                            bars,
                                            verified_parent,
                                            parent_artifact,
                                            artifact,
                                        )
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
                                except (FileNotFoundError, RuntimeError):
                                    existing_revision = None
                                if (
                                    request["operation"] == "INITIAL"
                                    and existing_revision is None
                                    and not _initial_partial_source_objects_match(
                                        objects,
                                        revisions,
                                        candidate_source_objects,
                                        f"{revision_id}.json",
                                    )
                                ):
                                    return _result(
                                        HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
                                    )
                                if existing_revision is not None:
                                    if existing_revision != revision_raw:
                                        raise RuntimeError
                                    if (
                                        request["operation"] == "INITIAL"
                                        and not _initial_exact_replay_objects_match(
                                            objects,
                                            revisions,
                                            candidate_source_objects,
                                            f"{revision_id}.json",
                                        )
                                    ):
                                        return _result(
                                            HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
                                        )
                                    self._read_stored_exact_from_directories(
                                        revision_id, objects, revisions
                                    )
                                if not _storage_root_is_exact(operation.descriptor):
                                    return _result(
                                        HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
                                    )
                                _assert_hierarchy_live(
                                    operation,
                                    root,
                                    profile,
                                    version,
                                    objects,
                                    revisions,
                                )
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
                                if existing_revision is not None:
                                    exact_revision = (
                                        self._read_stored_exact_from_directories(
                                            revision_id, objects, revisions
                                        )
                                    )
                                    _assert_hierarchy_live(
                                        operation,
                                        root,
                                        profile,
                                        version,
                                        objects,
                                        revisions,
                                    )
                                    return HistoricalOhlcvImportResultV1(
                                        HistoricalOhlcvImportOutcomeV1.SUCCESS,
                                        revision_id,
                                        exact_revision,
                                    )
                        finally:
                            os.close(version)
                    finally:
                        os.close(profile)
                finally:
                    os.close(root)
        except Exception:
            return _result(
                HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
            )
        return self.read_exact(revision_id)

    def _read_exact_source_artifact(
        self, revision_sha256: object
    ) -> dict[str, Any] | None:
        revision_id = _digest(revision_sha256)
        if revision_id is None:
            return None
        root_identity = self.admitted_root_identity
        if root_identity is None:
            root_identity = StorageRootLease.admit_existing_private_identity(
                self.storage_root
            )
        if root_identity is None:
            return None
        lease_result = StorageRootLease.try_acquire_existing_identity(
            self.storage_root, root_identity
        )
        if (
            lease_result.outcome is not LeaseOutcome.ACQUIRED
            or lease_result.lease is None
        ):
            return None
        try:
            with (
                lease_result.lease as lease,
                lease.read_operation(self.storage_root) as operation,
            ):
                _assert_owner_private_directory(operation.descriptor)
                root = _open_existing_directory(operation.descriptor, _ROOT_DIRECTORY)
                try:
                    profile = _open_existing_directory(root, _PROFILE_DIRECTORY)
                    try:
                        version = _open_existing_directory(profile, _SCHEMA_DIRECTORY)
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
                                current = self._validate_stored_revision_local(
                                    revision_id, objects, revisions
                                )
                                artifact = self._artifact_for_revision(current, objects)
                                _assert_hierarchy_live(
                                    operation,
                                    root,
                                    profile,
                                    version,
                                    objects,
                                    revisions,
                                )
                                return artifact
                        finally:
                            os.close(version)
                    finally:
                        os.close(profile)
                finally:
                    os.close(root)
        except Exception:
            return None

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
                    profile = _open_existing_directory(root, _PROFILE_DIRECTORY)
                    try:
                        version = _open_existing_directory(profile, _SCHEMA_DIRECTORY)
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
                                _assert_hierarchy_live(
                                    operation,
                                    root,
                                    profile,
                                    version,
                                    objects,
                                    revisions,
                                )
                                return HistoricalOhlcvImportResultV1(
                                    HistoricalOhlcvImportOutcomeV1.SUCCESS,
                                    revision_id,
                                    value,
                                )
                        finally:
                            os.close(version)
                    finally:
                        os.close(profile)
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
        parsed = _parse_request_structure(_canonical(request))
        if any(
            _digest(request[field]) is None
            for field in (
                "schema_identity_sha256",
                "runtime_code_identity_sha256",
                "configuration_identity_sha256",
            )
        ):
            raise RuntimeError
        if (
            parsed is None
            or _digest(value["completion_request_identity_sha256"]) is None
            or value["context_status"] != _CONTEXT_STATUS
            or value["limitation"] != _LIMITATION
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
                    child_request,
                    cast(list[dict[str, Any]], child["bars"]),
                    current,
                    self._artifact_for_revision(current, objects),
                    self._artifact_for_revision(child, objects),
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
