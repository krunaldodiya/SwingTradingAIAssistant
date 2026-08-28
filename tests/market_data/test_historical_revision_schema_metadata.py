"""Independent frozen schema-identity metadata contract for Plan 28."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, cast

import pytest

from swing_trading_ai_assistant.market_data import historical_revision_store as store

_EXPECTED_SCHEMA_DIGEST_V2 = (
    "97974bbe56885a032b0ffad83dc8c1e0b41c999b84ee748c680613eeecb091e5"
)
_EXPECTED_SCHEMA_METADATA_V2: dict[str, object] = {
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


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def test_schema_identity_metadata_is_the_frozen_v2_contract() -> None:
    metadata = cast(dict[str, Any], store._SCHEMA_IDENTITY_PREIMAGE)  # pyright: ignore[reportPrivateUsage]

    assert metadata == _EXPECTED_SCHEMA_METADATA_V2
    assert (
        metadata["metadata_version"]
        == "fixed-cohort-historical-ohlcv-schema-identity@v2"
    )
    assert _digest(metadata) == _EXPECTED_SCHEMA_DIGEST_V2
    assert store._SCHEMA_IDENTITY_SHA256 == _EXPECTED_SCHEMA_DIGEST_V2  # pyright: ignore[reportPrivateUsage]


def test_schema_metadata_digest_is_sensitive_to_every_field_row_attribute() -> None:
    metadata = cast(dict[str, Any], store._SCHEMA_IDENTITY_PREIMAGE)  # pyright: ignore[reportPrivateUsage]
    objects = cast(dict[str, dict[str, list[dict[str, str]]]], metadata["objects"])
    for object_name, definition in objects.items():
        for index, _row in enumerate(definition["field_rows"]):
            for key in ("name", "semantic_type", "unit", "nullability", "bounds"):
                mutated: dict[str, Any] = deepcopy(metadata)
                mutated["objects"][object_name]["field_rows"][index][key] = "MUTATED"
                assert _digest(mutated) != _EXPECTED_SCHEMA_DIGEST_V2


@pytest.mark.parametrize(
    ("object_name", "field_name", "key", "expected"),
    (
        (
            "UpstoxRawHistoricalOhlcvCompletionRequestV1",
            "parent_revision_sha256",
            "nullability",
            "NULLABLE",
        ),
        (
            "UpstoxRawHistoricalOhlcvCompletionRequestV1",
            "correction_coordinates",
            "bounds",
            "CorrectionCoordinateV1,0..18300",
        ),
        ("MappingReceiptV1", "etag", "nullability", "NULLABLE"),
        (
            "MappingReceiptV1",
            "etag",
            "bounds",
            "PRINTABLE_ASCII_1_TO_512",
        ),
        (
            "MappingReceiptV1",
            "last_modified",
            "bounds",
            "PRINTABLE_ASCII_1_TO_512",
        ),
        (
            "UpstoxRawHistoricalOhlcvCompletionRequestV1",
            "observed_at",
            "bounds",
            "WHOLE_SECOND_Z",
        ),
        (
            "SourceReceiptV1",
            "observed_at",
            "bounds",
            "WHOLE_SECOND_Z",
        ),
        (
            "GeneratedRevisionRequestV1",
            "observed_at",
            "bounds",
            "WHOLE_SECOND_Z",
        ),
        (
            "HistoricalOhlcvRevisionV1",
            "observed_at",
            "bounds",
            "WHOLE_SECOND_Z",
        ),
        (
            "CanonicalScheduleEnvelopeV2",
            "as_of",
            "bounds",
            "SIX_FRACTIONAL_DIGITS_Z",
        ),
        (
            "CanonicalScheduleSessionV1",
            "open_at",
            "bounds",
            "SIX_FRACTIONAL_DIGITS_Z_MINUTE_ALIGNED",
        ),
        (
            "CanonicalScheduleSessionV1",
            "close_at",
            "bounds",
            "SIX_FRACTIONAL_DIGITS_Z_MINUTE_ALIGNED",
        ),
        ("MappingReceiptV1", "compressed_byte_count", "bounds", "0..4000000"),
        (
            "MappingReceiptV1",
            "decompressed_byte_count",
            "bounds",
            "0..50000000",
        ),
        (
            "PartitionReceiptV1",
            "failure_category",
            "nullability",
            "REQUIRED",
        ),
        (
            "PartitionReceiptV1",
            "row_count",
            "bounds",
            "POSITIVE_NO_INVENTED_UPPER_BOUND",
        ),
        (
            "HistoricalOhlcvBarV1",
            "open",
            "bounds",
            "CANONICAL_FINITE_POSITIVE_NONEXPONENT",
        ),
        (
            "HistoricalOhlcvBarV1",
            "volume",
            "bounds",
            "0..9223372036854775807",
        ),
        ("HistoricalOhlcvRevisionV1", "lineage_depth", "bounds", "0..128"),
    ),
)
def test_schema_metadata_binds_named_blocker_sensitivities(
    object_name: str, field_name: str, key: str, expected: str
) -> None:
    metadata = cast(dict[str, Any], store._SCHEMA_IDENTITY_PREIMAGE)  # pyright: ignore[reportPrivateUsage]
    rows = cast(list[dict[str, str]], metadata["objects"][object_name]["field_rows"])
    row = next(item for item in rows if item["name"] == field_name)
    assert row[key] == expected

    mutated: dict[str, Any] = deepcopy(metadata)
    mutated_rows = mutated["objects"][object_name]["field_rows"]
    mutated_row = next(item for item in mutated_rows if item["name"] == field_name)
    mutated_row[key] = "MUTATED"
    assert _digest(mutated) != _EXPECTED_SCHEMA_DIGEST_V2


def test_schema_metadata_binds_exact_object_set_and_field_row_order() -> None:
    metadata = cast(dict[str, Any], store._SCHEMA_IDENTITY_PREIMAGE)  # pyright: ignore[reportPrivateUsage]
    actual = cast(dict[str, dict[str, list[dict[str, str]]]], metadata["objects"])
    expected = cast(
        dict[str, dict[str, list[dict[str, str]]]],
        _EXPECTED_SCHEMA_METADATA_V2["objects"],
    )

    assert tuple(actual) == tuple(expected)
    for object_name, expected_definition in expected.items():
        assert [row["name"] for row in actual[object_name]["field_rows"]] == [
            row["name"] for row in expected_definition["field_rows"]
        ]

    first_object = next(iter(actual))
    first_row = actual[first_object]["field_rows"][0]
    mutations: list[dict[str, Any]] = []

    removed = deepcopy(metadata)
    removed["objects"][first_object]["field_rows"].pop()
    mutations.append(removed)

    added = deepcopy(metadata)
    added["objects"][first_object]["field_rows"].append(dict(first_row))
    mutations.append(added)

    renamed = deepcopy(metadata)
    renamed["objects"][first_object]["field_rows"][0]["name"] = "renamed"
    mutations.append(renamed)

    reordered = deepcopy(metadata)
    reordered_rows = reordered["objects"][first_object]["field_rows"]
    reordered_rows[0], reordered_rows[1] = reordered_rows[1], reordered_rows[0]
    mutations.append(reordered)

    assert all(_digest(mutated) != _EXPECTED_SCHEMA_DIGEST_V2 for mutated in mutations)


@pytest.mark.parametrize(
    ("section", "key"),
    (
        ("canonical_representation", "unknown_fields"),
        ("ordering_cardinality", "bars"),
        ("cross_field_state_transitions", "request_operations"),
        ("identity_preimages_exclusions", "mapping_receipt"),
        ("schedule_version_projections", "v3"),
    ),
)
def test_schema_metadata_binds_state_and_formula_rules(section: str, key: str) -> None:
    metadata = cast(dict[str, Any], store._SCHEMA_IDENTITY_PREIMAGE)  # pyright: ignore[reportPrivateUsage]
    mutated: dict[str, Any] = deepcopy(metadata)
    mutated[section][key] = "MUTATED"

    assert _digest(mutated) != _EXPECTED_SCHEMA_DIGEST_V2


@pytest.mark.parametrize(
    "section",
    (
        "literals",
        "canonical_representation",
        "field_closure",
        "ordering_cardinality",
        "cross_field_state_transitions",
        "identity_preimages_exclusions",
        "schedule_version_projections",
        "failure_precedence",
        "byte_ceilings",
    ),
)
def test_schema_metadata_digest_binds_all_non_field_sections(section: str) -> None:
    metadata = cast(dict[str, Any], store._SCHEMA_IDENTITY_PREIMAGE)  # pyright: ignore[reportPrivateUsage]
    mutated: dict[str, Any] = deepcopy(metadata)
    value = mutated[section]
    if isinstance(value, dict):
        first = next(iter(value))
        value[first] = "MUTATED"
    else:
        value[0] = "MUTATED"

    assert _digest(mutated) != _EXPECTED_SCHEMA_DIGEST_V2
