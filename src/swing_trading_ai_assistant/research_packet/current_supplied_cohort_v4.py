# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false, reportOperatorIssue=false, reportOptionalMemberAccess=false, reportOptionalOperand=false, reportOptionalSubscript=false, reportReturnType=false
"""Owner-private retained current supplied-cohort research packets V4.

The packet has one market source: an exact archive-sealed same-pass V4 context.
It never accepts a raw grid, Market Regime report, or partial-session snapshot
from a caller. Publication is create-only; current commits require the completion
marker plus an admissibility guard, and retained results are archive-minted only.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import stat
import time
from contextlib import suppress
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol, TypeAlias, cast
from weakref import WeakKeyDictionary

from swing_trading_ai_assistant.market_data.bharatstock import PRICE_BASIS
from swing_trading_ai_assistant.market_data.current_event_notice import (
    _ARCHIVE_PROTOCOL_VERSION as _EVENT_ARCHIVE_PROTOCOL,
)
from swing_trading_ai_assistant.market_data.current_event_notice import (
    _DELIVERED_EVENT_NOTICE_RUNTIME_IDENTITY_V1,
    EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
    LEGACY_EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
    current_event_notice_runtime_code_identity_v1,
)
from swing_trading_ai_assistant.market_data.current_event_notice import (
    _IST as _EVENT_IST,
)
from swing_trading_ai_assistant.market_data.current_event_notice import (
    _RECEIPT_VERSION as _EVENT_RECEIPT_VERSION,
)
from swing_trading_ai_assistant.market_data.current_event_notice import (
    _SOURCE_URL as _EVENT_SOURCE_URL,
)
from swing_trading_ai_assistant.market_data.current_event_notice import (
    CONTRACT_VERSION as _EVENT_CONTRACT,
)
from swing_trading_ai_assistant.market_data.current_event_notice import (
    CurrentEventCohortMemberV1 as _CurrentEventCohortMemberV1,
)
from swing_trading_ai_assistant.market_data.current_event_notice import (
    CurrentEventNoticeFailureV1 as _CurrentEventNoticeFailureV1,
)
from swing_trading_ai_assistant.market_data.current_event_notice import (
    CurrentEventNoticeMemberResultV1 as _CurrentEventNoticeMemberResultV1,
)
from swing_trading_ai_assistant.market_data.current_event_notice import (
    CurrentEventNoticeV1 as _CurrentEventNoticeV1,
)
from swing_trading_ai_assistant.market_data.current_event_notice import (
    RetainedCurrentEventNoticeSnapshotV1 as _RetainedCurrentEventNoticeSnapshotV1,
)
from swing_trading_ai_assistant.market_data.current_event_notice import (
    _exact_event_source_case_v1 as _event_source_case_is_exact,
)
from swing_trading_ai_assistant.market_data.current_event_notice import (
    _parse_filename as _event_filename_date,
)
from swing_trading_ai_assistant.market_data.current_same_pass_daily_v4 import (
    CurrentSamePassEquityMemberV4 as _CurrentSamePassEquityMemberV4,
)
from swing_trading_ai_assistant.market_data.current_same_pass_daily_v4 import (
    current_same_pass_raw_daily_schema_identity_v4,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256 as _runtime_source_sha256,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    same_metadata as _same_metadata,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

if TYPE_CHECKING:
    from swing_trading_ai_assistant.market_data.current_event_notice import (
        CurrentEventNoticeFailureV1,
        RetainedCurrentEventNoticeSnapshotV1,
    )
    from swing_trading_ai_assistant.market_regime.current_supplied_cohort_v4 import (
        RetainedCurrentSamePassMarketContextV4,
    )
    from swing_trading_ai_assistant.sector_analysis.current_industry_participation_v4 import (
        CurrentIndustryParticipationFailureV4,
        CurrentIndustryParticipationReportV4,
    )

_CONTRACT: Final = "current-supplied-cohort-research-packet@v4"
_FAILURE_CONTRACT: Final = "current-supplied-cohort-research-packet-archive-failure@v4"
_RECEIPT_CONTRACT: Final = "current-supplied-cohort-research-packet-receipt@v4"
_MARKER_CONTRACT: Final = "current-supplied-cohort-research-packet-marker@v4"
_ARCHIVE_DIRECTORY: Final = ".current-research-packet-v4"
_PACKET_LIMIT: Final = 37_748_736
_RECEIPT_LIMIT: Final = 16_384
_MARKER_LIMIT: Final = 4_096
_RETAINED_LIMIT: Final = 37_769_216
_REQUEST_LIMIT: Final = 4_194_304
_MAX_DEPTH: Final = 32
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_ISIN: Final = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]\Z")
_NSE_SYMBOL: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_MANIFEST_MODULE: Final = (
    "swing_trading_ai_assistant.research_packet."
    "current_supplied_cohort_v4_runtime_identity_manifest"
)
_MANIFEST_PATH: Final = (
    "src/swing_trading_ai_assistant/research_packet/"
    "current_supplied_cohort_v4_runtime_identity_manifest.py"
)
_RUNTIME_SOURCE: Final = (
    "src/swing_trading_ai_assistant/research_packet/current_supplied_cohort_v4.py"
)
_PACKET_COMPONENTS: Final = (
    "MARKET_DATA_SAME_PASS_V1",
    "MARKET_REGIME_V4",
    "INDUSTRY_PARTICIPATION_V4",
    "EVENT_NOTICES_V1",
)
PACKET_REASON_ORDER_V4: Final = (
    "MARKET_DATA_UNAVAILABLE",
    "MARKET_REGIME_UNAVAILABLE",
    "INDUSTRY_PARTICIPATION_UNAVAILABLE",
    "EVENT_NOTICES_UNAVAILABLE",
    "SOURCE_USE_UNAUTHORIZED",
    "COMPONENT_IDENTITY_INVALID",
    "COHORT_PROJECTION_MISMATCH",
    "DECISION_CUTOFF_MISMATCH",
    "DECISION_SESSION_MISMATCH",
    "COMPONENT_FUTURE_KNOWN",
    "COMPONENT_STALE",
    "COMPONENT_CONFLICTED",
    "PARTIAL_AS_COMPLETE",
)
_REASON_RANK: Final = {
    reason: index for index, reason in enumerate(PACKET_REASON_ORDER_V4)
}
_ARCHIVE_LOCK: Final = Lock()
_PACKET_BUILD_LOCK: Final = Lock()
_EVENT_FAILURE_REASON_ORDER: Final = (
    "EVENT_ARTIFACT_MISSING",
    "EVENT_SOURCE_UNAUTHORIZED",
    "EVENT_SOURCE_MISMATCH",
    "EVENT_ARTIFACT_IDENTITY_MISMATCH",
    "EVENT_ARTIFACT_MALFORMED",
    "EVENT_HEADER_MISMATCH",
    "EVENT_BOUNDS_EXCEEDED",
    "EVENT_TIME_MALFORMED",
    "EVENT_SOURCE_DATE_FUTURE",
    "EVENT_SOURCE_DATE_STALE",
    "EVENT_COHORT_INVALID",
    "EVENT_EXCHANGE_UNSUPPORTED",
    "EVENT_SYMBOL_AMBIGUOUS",
    "EVENT_OUT_OF_COHORT",
    "EVENT_DUPLICATE",
    "EVENT_CONFLICTED",
    "CORRECTION_LINEAGE_UNAVAILABLE",
    "EVENT_RUNTIME_IDENTITY_INVALID",
    "EVENT_ARCHIVE_FAILED",
)
_EVENT_FAILURE_STATES: Final = {
    "EVENT_ARTIFACT_MISSING": "INSUFFICIENT_EVIDENCE",
    "EVENT_SOURCE_UNAUTHORIZED": "UNSUPPORTED_CAPABILITY",
    "EVENT_SOURCE_MISMATCH": "UNSUPPORTED_CAPABILITY",
    "EVENT_ARTIFACT_IDENTITY_MISMATCH": "MALFORMED_EVIDENCE",
    "EVENT_ARTIFACT_MALFORMED": "MALFORMED_EVIDENCE",
    "EVENT_HEADER_MISMATCH": "MALFORMED_EVIDENCE",
    "EVENT_BOUNDS_EXCEEDED": "MALFORMED_EVIDENCE",
    "EVENT_TIME_MALFORMED": "MALFORMED_EVIDENCE",
    "EVENT_SOURCE_DATE_FUTURE": "INSUFFICIENT_EVIDENCE",
    "EVENT_SOURCE_DATE_STALE": "INSUFFICIENT_EVIDENCE",
    "EVENT_COHORT_INVALID": "MALFORMED_EVIDENCE",
    "EVENT_EXCHANGE_UNSUPPORTED": "UNSUPPORTED_CAPABILITY",
    "EVENT_SYMBOL_AMBIGUOUS": "MALFORMED_EVIDENCE",
    "EVENT_OUT_OF_COHORT": "MALFORMED_EVIDENCE",
    "EVENT_DUPLICATE": "CONFLICTED_EVIDENCE",
    "EVENT_CONFLICTED": "CONFLICTED_EVIDENCE",
    "CORRECTION_LINEAGE_UNAVAILABLE": "INSUFFICIENT_EVIDENCE",
    "EVENT_RUNTIME_IDENTITY_INVALID": "INSUFFICIENT_EVIDENCE",
    "EVENT_ARCHIVE_FAILED": "INSUFFICIENT_EVIDENCE",
}


_SCHEDULE_PREFLIGHT_REASONS: Final = frozenset(
    {
        "SCHEDULE_EVIDENCE_MISSING",
        "SCHEDULE_EVIDENCE_STALE",
        "SCHEDULE_EVIDENCE_CONFLICTED",
        "SCHEDULE_CONTINUITY_UNPROVEN",
        "LATEST_COMPLETED_SESSION_UNRESOLVED",
    }
)


_UPSTREAM_PACKET_REASON_MAP_V4: Final = {
    "RAW_MAPPING_STALE": ("COMPONENT_STALE",),
    "RAW_BAR_STALE": ("COMPONENT_STALE",),
    "CLASSIFICATION_SESSION_STALE": ("COMPONENT_STALE",),
    "EVENT_SOURCE_DATE_STALE": ("COMPONENT_STALE",),
    "RAW_BAR_FUTURE_KNOWN": ("COMPONENT_FUTURE_KNOWN",),
    "CLASSIFICATION_FUTURE_KNOWN": ("COMPONENT_FUTURE_KNOWN",),
    "EVENT_SOURCE_DATE_FUTURE": ("COMPONENT_FUTURE_KNOWN",),
    "RAW_MAPPING_CONFLICTED": ("COMPONENT_CONFLICTED",),
    "RAW_BAR_CONFLICTED": ("COMPONENT_CONFLICTED",),
    "RAW_ADJUSTED_DIRECTION_CONFLICT": ("COMPONENT_CONFLICTED",),
    "CLASSIFICATION_CONFLICTING": ("COMPONENT_CONFLICTED",),
    "EVENT_DUPLICATE": ("COMPONENT_CONFLICTED",),
    "EVENT_CONFLICTED": ("COMPONENT_CONFLICTED",),
    "CLASSIFICATION_SOURCE_UNSUPPORTED": ("SOURCE_USE_UNAUTHORIZED",),
    "EVENT_SOURCE_UNAUTHORIZED": ("SOURCE_USE_UNAUTHORIZED",),
    "EVENT_SOURCE_MISMATCH": ("SOURCE_USE_UNAUTHORIZED",),
    "COHORT_BINDING_MISMATCH": ("COHORT_PROJECTION_MISMATCH",),
    "EVENT_COHORT_INVALID": ("COHORT_PROJECTION_MISMATCH",),
    "EVENT_OUT_OF_COHORT": ("COHORT_PROJECTION_MISMATCH",),
}


def _instant(value: datetime) -> str:
    if type(value) is not datetime or value.tzinfo is not UTC:
        raise ValueError("invalid UTC instant")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _wire(value: object, *, depth: int = 0) -> object:
    """Return only canonical JSON values; private seals never cross this boundary."""
    if depth > _MAX_DEPTH:
        raise ValueError("packet nesting exceeds bound")
    if type(value) is datetime:
        return _instant(value)
    if type(value) is date:
        return value.isoformat()
    if type(value) in {str, int, float, bool} or value is None:
        return value
    if type(value) is tuple or type(value) is list:
        return [_wire(item, depth=depth + 1) for item in value]
    if type(value) is dict:
        if not all(type(key) is str for key in value):
            raise TypeError("packet object keys must be strings")
        return {key: _wire(item, depth=depth + 1) for key, item in value.items()}
    value_method = getattr(value, "value", None)
    if callable(value_method):
        return _wire(value_method(), depth=depth + 1)
    if is_dataclass(value):
        return {
            field.name: _wire(getattr(value, field.name), depth=depth + 1)
            for field in fields(value)
            if field.name != "_archive_seal"
        }
    raise TypeError("noncanonical packet value")


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            _wire(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _identity(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _safe_text(value: object, maximum: int) -> bool:
    return type(value) is str and 0 < len(value.encode("utf-8")) <= maximum


def _utc(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is UTC


def _ordered_reasons(values: set[str]) -> tuple[str, ...]:
    return tuple(reason for reason in PACKET_REASON_ORDER_V4 if reason in values)


def _object_value(value: object, *, omit: str | None = None) -> dict[str, object]:
    if not is_dataclass(value):
        raise TypeError("packet schema object required")
    return {
        field.name: _wire(getattr(value, field.name))
        for field in fields(value)
        if field.name not in {omit, "_archive_seal"}
    }


def _valid_isin(value: object) -> bool:
    if type(value) is not str or _ISIN.fullmatch(value) is None:
        return False
    digits = "".join(
        character if character.isdigit() else str(ord(character) - ord("A") + 10)
        for character in value
    )
    return (
        sum(
            int(digit) if index % 2 == 0 else sum(divmod(int(digit) * 2, 10))
            for index, digit in enumerate(reversed(digits))
        )
        % 10
        == 0
    )


def _member_value(member: object) -> dict[str, object]:
    if type(member) is not _CurrentSamePassEquityMemberV4:
        raise ValueError("invalid canonical cohort member")
    value = member.value()
    if (
        not _valid_isin(value["isin"])
        or value["exchange"] != "NSE"
        or value["instrument_type"] != "EQUITY"
        or value["segment"] != "EQ"
        or not _NSE_SYMBOL.fullmatch(str(value["effective_symbol"]))
        or type(member.valid_from) is not date
        or type(member.valid_through) is not date
        or member.valid_from > member.valid_through
        or type(member.provider_symbol) is not str
        or not 1 <= len(member.provider_symbol.encode("utf-8")) <= 64
        or member.mapping_version != "bharatstock-isin-exchange-mapping@v1"
        or type(member.mapping_valid_from) is not date
        or (
            member.mapping_valid_through is not None
            and type(member.mapping_valid_through) is not date
        )
        or (
            member.mapping_valid_through is not None
            and member.mapping_valid_from > member.mapping_valid_through
        )
        or not _digest(value["mapping_identity"])
        or not _safe_text(value["provider_mapping_revision"], 128)
    ):
        raise ValueError("invalid canonical cohort member")
    return value


def _canonical_members(members: object, cutoff: object) -> tuple[object, ...]:
    if type(members) is not tuple or not 1 <= len(members) <= 50 or not _utc(cutoff):
        raise ValueError("invalid canonical cohort")
    values = tuple(members)
    projections = tuple(_member_value(member) for member in values)
    if len({item["isin"] for item in projections}) != len(projections):
        raise ValueError("duplicate ISIN")
    if len({item["effective_symbol"] for item in projections}) != len(projections):
        raise ValueError("duplicate effective symbol")
    if any(member.valid_from > member.valid_through for member in values):
        raise ValueError("invalid member effective interval")
    return values


def _plan21_identity(selected_at: datetime, members: tuple[object, ...]) -> str:
    return _identity(
        {
            "contract_version": "current-supplied-cohort-market-data@v1",
            "selected_at": _instant(selected_at),
            "members": [
                {
                    "isin": member.isin,
                    "symbol": member.effective_symbol,
                }
                for member in sorted(members, key=lambda item: item.isin)
            ],
        }
    )


def _canonical_cohort_identity(
    selected_at: datetime, members: tuple[object, ...]
) -> str:
    return _identity(
        {
            "contract_version": "current-same-pass-canonical-cohort@v1",
            "cohort_selected_at": _instant(selected_at),
            "members": [
                _member_value(member)
                for member in sorted(members, key=lambda item: item.isin)
            ],
        }
    )


def _schema_field_from_contract(field: str) -> dict[str, str]:
    name, separator, declaration = field.partition(":")
    if not separator or not name or not declaration:
        raise ValueError("invalid packet schema field declaration")
    nullable = declaration.endswith(" or None")
    semantic_type = declaration.removesuffix(" or None")
    return {
        "name": name,
        "semantic_type": semantic_type,
        "unit": _schema_unit_v4(semantic_type),
        "nullability": "NULLABLE" if nullable else "REQUIRED",
        "bounds": _schema_bounds_v4(semantic_type),
    }


def _schema_unit_v4(semantic_type: str) -> str:  # noqa: C901
    if semantic_type.startswith('Literal["'):
        return "ENUMERATION"
    if semantic_type.startswith("int["):
        return "INTEGER_COUNT"
    if semantic_type.startswith("tuple["):
        return "ORDERED_TUPLE"
    if semantic_type == "UtcInstant":
        return "UTC_INSTANT"
    if semantic_type == "LocalDate":
        return "LOCAL_DATE"
    if semantic_type == "Sha256":
        return "SHA256_DIGEST"
    if semantic_type == "Isin":
        return "ISIN"
    if semantic_type == "NseSymbol":
        return "NSE_SYMBOL"
    if semantic_type.startswith("SafeText[") or semantic_type == "SafeRevision":
        return "UTF8_TEXT"
    if semantic_type == "None":
        return "NULL"
    if " or " in semantic_type:
        return "CLOSED_UNION"
    if semantic_type == "PacketComponent":
        return "ENUMERATION"
    return "CLOSED_OBJECT"


def _schema_bounds_v4(semantic_type: str) -> str:  # noqa: C901
    if semantic_type.startswith("Literal[") and semantic_type.endswith("]"):
        literal_values = json.loads(f"[{semantic_type[8:-1]}]")
        if (
            type(literal_values) is not list
            or not literal_values
            or any(type(value) is not str for value in literal_values)
            or len(set(literal_values)) != len(literal_values)
        ):
            raise ValueError("invalid Literal schema declaration")
        return f"ALLOWED_VALUES[{'|'.join(literal_values)}]"
    if semantic_type.startswith("int["):
        return f"CLOSED_INTEGER_RANGE[{semantic_type[4:-1]}]"
    if semantic_type.startswith("tuple["):
        element, cardinality = semantic_type[6:-1].rsplit(",", 1)
        return f"ELEMENT={element};CARDINALITY={cardinality}"
    if semantic_type == "UtcInstant":
        return "AWARE_UTC_MICROSECOND"
    if semantic_type == "LocalDate":
        return "ISO_8601_DATE"
    if semantic_type == "Sha256":
        return "LOWERCASE_64_HEX"
    if semantic_type == "Isin":
        return "UPPERCASE_LUHN_12_ASCII"
    if semantic_type == "NseSymbol":
        return "UTF8_BYTES[1..64]"
    if semantic_type.startswith("SafeText["):
        return f"UTF8_BYTES[{semantic_type[9:-1]}]"
    if semantic_type == "SafeRevision":
        return "UTF8_BYTES[1..128]"
    if semantic_type == "None":
        return "MUST_BE_NULL"
    if " or " in semantic_type:
        return f"EXACTLY_ONE[{semantic_type.replace(' or ', '|')}]"
    if semantic_type == "PacketComponent":
        return "ORDERED_PACKET_COMPONENT_SET"
    return f"EXACT_TYPE[{semantic_type}]"


def _packet_schema_type_rows(
    declarations: object,
) -> tuple[dict[str, object], ...]:
    if type(declarations) is not dict:
        raise ValueError("invalid packet schema declarations")
    rows: list[dict[str, object]] = []
    for name, field_declarations in declarations.items():
        if type(name) is not str or type(field_declarations) is not list:
            raise ValueError("invalid packet schema declaration row")
        rows.append(
            {
                "name": name,
                "ordered_fields": tuple(
                    _schema_field_from_contract(field)
                    for field in field_declarations
                    if type(field) is str
                ),
            }
        )
        if len(rows[-1]["ordered_fields"]) != len(field_declarations):
            raise ValueError("invalid packet schema field declaration")
    return tuple(rows)


_PACKET_SCHEMA_DECLARATIONS_V4: Final = {
    "contract_version": _CONTRACT,
    "unknown_key_policy": "REJECT",
    "canonical_json": {
        "encoding": "UTF-8",
        "object_keys": "lexicographically_sorted",
        "separators": [",", ":"],
        "ensure_ascii": False,
        "allow_nan": False,
        "trailing_bytes": "\\n",
        "maximum_depth": _MAX_DEPTH,
    },
    "type_rows": {
        "CurrentSuppliedCohortResearchPacketRequestV4": [
            'contract_version:Literal["current-supplied-cohort-research-packet@v4"]',
            "decision_cutoff:UtcInstant",
            "cohort_selected_at:UtcInstant",
            "members:tuple[CurrentSamePassEquityMemberV4,1..50]",
            "plan21_cohort_identity_sha256:Sha256",
            "canonical_cohort_identity_sha256:Sha256",
            "market_context_identity_sha256:Sha256",
            "request_identity_sha256:Sha256",
        ],
        "CurrentResearchPacketComponentLedgerRowV4": [
            "position:int[0..3]",
            "component:PacketComponent",
            "contract_version:SafeRevision or None",
            "evidence_state:SafeRevision",
            "schema_identity_sha256:Sha256 or None",
            "runtime_code_identity_sha256:Sha256 or None",
            "primary_identity_sha256:Sha256 or None",
            "failure_cohort_size:int[1..50] or None",
            "identity_bindings:tuple[NamedIdentityV4,0..16]",
            "known_at:UtcInstant or None",
            "component_reasons:tuple[SafeRevision,0..32]",
            "packet_reasons:tuple[PacketReason,0..13]",
            "ledger_row_identity_sha256:Sha256",
        ],
        "CurrentResearchPacketSourceAttributionRowV4": [
            "position:int[0..3]",
            "component:PacketComponent",
            'source_state:Literal["BOUND","UNAVAILABLE"]',
            "provider_id:SafeRevision or None",
            "source_name:SafeText[1..128] or None",
            "source_url:SafeText[1..2048] or None",
            "source_release:SafeRevision or None",
            'price_basis:Literal["RAW","BHARATSTOCK_SOURCE_REPORTED_OHLC"] or None',
            "publisher_published_at:UtcInstant or None",
            "known_at:UtcInstant or None",
            "licence_policy_identity:SafeRevision or None",
            "primary_identity_sha256:Sha256 or None",
            "source_row_identity_sha256:Sha256",
        ],
        "CurrentResearchPacketMarketDataProjectionV4": [
            "decision_session:LocalDate",
            "rows:tuple[CurrentSamePassDecisionMarketDataRowV1,N]",
            "projection_identity_sha256:Sha256",
        ],
        "CurrentResearchPacketMarketRegimeProjectionV4": [
            "decision_session:LocalDate",
            "comparison_session:LocalDate",
            'regime:Literal["BROAD_ADVANCE","BROAD_DECLINE","MIXED_PARTICIPATION"]',
            "advances:int[0..50]",
            "declines:int[0..50]",
            "unchanged:int[0..50]",
            "projection_identity_sha256:Sha256",
        ],
        "CurrentResearchPacketIndustryProjectionV4": [
            'classification_tier:Literal["INDUSTRY"]',
            "industries:tuple[CurrentIndustryCountV4,1..N]",
            "known_at:UtcInstant",
            "projection_identity_sha256:Sha256",
        ],
        "CurrentResearchPacketRedactedEventNoticeV4": [
            "observation_identity_sha256:Sha256",
            "deduplication_identity_sha256:Sha256",
        ],
        "CurrentResearchPacketRedactedEventMemberV4": [
            "isin:Isin",
            "symbol:NseSymbol",
            'outcome:Literal["NOTICES_ADMITTED","NO_MATCHING_NOTICE_IN_SNAPSHOT"]',
            "notices:tuple[CurrentResearchPacketRedactedEventNoticeV4,0..10_000]",
        ],
        "CurrentResearchPacketEventProjectionV4": [
            "known_at:UtcInstant",
            "members:tuple[CurrentResearchPacketRedactedEventMemberV4,N]",
            "projection_identity_sha256:Sha256",
        ],
        "CurrentResearchPacketAIObservedV4": [
            'evidence_state:Literal["OBSERVED"]',
            "market_data:CurrentResearchPacketMarketDataProjectionV4",
            "market_regime:CurrentResearchPacketMarketRegimeProjectionV4",
            "industry_participation:CurrentResearchPacketIndustryProjectionV4",
            "event_notices:CurrentResearchPacketEventProjectionV4",
            "partial_current_session:PartialCurrentSessionSnapshotV1",
            "consumer_disposition:None",
            "ai_projection_identity_sha256:Sha256",
        ],
        "CurrentResearchPacketAIInsufficientV4": [
            'evidence_state:Literal["INSUFFICIENT_EVIDENCE"]',
            "market_data:None",
            "market_regime:None",
            "industry_participation:None",
            "event_notices:None",
            "partial_current_session:None",
            'consumer_disposition:Literal["INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"]',
            "ai_projection_identity_sha256:Sha256",
        ],
        "CurrentSuppliedCohortResearchPacketV4": [
            'contract_version:Literal["current-supplied-cohort-research-packet@v4"]',
            "schema_identity_sha256:Sha256",
            "configuration_identity_sha256:Sha256",
            "runtime_code_identity_sha256:Sha256",
            "request_identity_sha256:Sha256",
            "canonical_cohort_identity_sha256:Sha256",
            "market_context_identity_sha256:Sha256",
            "decision_cutoff:UtcInstant",
            "decision_session:LocalDate",
            "component_known_at_max:UtcInstant or None",
            'evidence_state:Literal["OBSERVED","INSUFFICIENT_EVIDENCE"]',
            "component_ledger:tuple[CurrentResearchPacketComponentLedgerRowV4,4]",
            "source_attribution:tuple[CurrentResearchPacketSourceAttributionRowV4,4]",
            "reasons:tuple[PacketReason,0..13]",
            "ai_projection:CurrentResearchPacketAIObservedV4 or CurrentResearchPacketAIInsufficientV4",
            "packet_identity_sha256:Sha256",
            "packet_object_sha256:Sha256",
        ],
        "_CurrentSuppliedCohortResearchPacketCandidateV4": [
            "packet:CurrentSuppliedCohortResearchPacketV4",
            "candidate_identity_sha256:Sha256",
        ],
        "CurrentResearchPacketArchiveFailureV4": [
            'contract_version:Literal["current-supplied-cohort-research-packet-archive-failure@v4"]',
            'evidence_state:Literal["ARCHIVE_FAILED"]',
            'reason:Literal["RESEARCH_PACKET_ARCHIVE_FAILED"]',
            "request_identity_sha256:Sha256",
            "packet_identity_sha256:Sha256 or None",
            "archive_failure_identity_sha256:Sha256",
        ],
        "CurrentResearchPacketReceiptV4": [
            'contract_version:Literal["current-supplied-cohort-research-packet-receipt@v4"]',
            "packet_identity_sha256:Sha256",
            "packet_object_sha256:Sha256",
            "packet_byte_count:int[1..37_748_736]",
            "packet_filename:SafeText[1..128]",
            "archive_known_at:UtcInstant",
            "receipt_identity_sha256:Sha256",
        ],
        "CurrentResearchPacketCompletionMarkerV4": [
            'contract_version:Literal["current-supplied-cohort-research-packet-marker@v4"]',
            "packet_identity_sha256:Sha256",
            "packet_object_sha256:Sha256",
            "receipt_identity_sha256:Sha256",
            "receipt_sha256:Sha256",
            "archive_known_at:UtcInstant",
            "completion_marker_identity_sha256:Sha256",
        ],
        "RetainedCurrentSuppliedCohortResearchPacketV4": [
            'evidence_state:Literal["RETAINED"]',
            "packet:CurrentSuppliedCohortResearchPacketV4",
            "receipt_identity_sha256:Sha256",
            "completion_marker_identity_sha256:Sha256",
            "archive_known_at:UtcInstant",
            "retained_identity_sha256:Sha256",
        ],
    },
    "in_memory_only": {
        "_CurrentSuppliedCohortResearchPacketCandidateV4": {
            "fields": [
                "market_context",
                "industry_participation",
                "event_notices",
                "_seal",
            ],
            "serialization": "NEVER",
            "identity_preimages": "EXCLUDED",
        },
        "RetainedCurrentSuppliedCohortResearchPacketV4": {
            "fields": ["_archive_seal"],
            "serialization": "NEVER",
            "identity_preimages": "EXCLUDED",
        },
    },
    "state_projections": {
        "packet": ["OBSERVED", "INSUFFICIENT_EVIDENCE"],
        "ai_observed": ["OBSERVED"],
        "ai_insufficient": ["INSUFFICIENT_EVIDENCE"],
        "source": ["BOUND", "UNAVAILABLE"],
        "component_ledger": {
            "MARKET_DATA_SAME_PASS_V1": [
                "success",
                "natural_insufficiency",
                "invalid",
            ],
            "MARKET_REGIME_V4": [
                "success",
                "natural_insufficiency",
                "natural_adjusted_not_attempted",
                "invalid",
            ],
            "INDUSTRY_PARTICIPATION_V4": ["success", "typed_failure", "invalid"],
            "EVENT_NOTICES_V1": ["success", "typed_failure", "invalid"],
        },
    },
    "packet_components": list(_PACKET_COMPONENTS),
    "reason_order": list(PACKET_REASON_ORDER_V4),
}


SCHEMA_DEFINITION_V4: Final = {
    "contract_version": _CONTRACT,
    "type_rows": _packet_schema_type_rows(_PACKET_SCHEMA_DECLARATIONS_V4["type_rows"]),
    "state_projections": _PACKET_SCHEMA_DECLARATIONS_V4["state_projections"],
    "unknown_key_policy": "REJECT",
}
CONFIGURATION_DEFINITION_V4: Final = {
    "contract_version": _CONTRACT,
    "structural_bounds": {
        "cohort_members": [1, 50],
        "packet_request_bytes": [1, _REQUEST_LIMIT],
        "packet_bytes": [1, _PACKET_LIMIT],
        "receipt_bytes": [1, _RECEIPT_LIMIT],
        "marker_bytes": [1, _MARKER_LIMIT],
        "guard_bytes": [1, _MARKER_LIMIT],
        "retained_bytes": [1, _RETAINED_LIMIT],
        "json_nesting": [1, _MAX_DEPTH],
        "event_notice_rows": [0, 10_000],
    },
    "canonicalization": "CJ UTF-8 sorted keys compact no-NaN trailing-LF",
    "reason_order": list(PACKET_REASON_ORDER_V4),
    "precedence": (
        "structural-before-domain; adjusted-not-attempted-propagates-without-source; "
        "any-domain-reason-suppresses-facts"
    ),
    "raw_source_policy": "sealed-current-same-pass-market-context-v4-only",
    "partial_policy": "auxiliary-only; no-completed-substitution",
    "retention_names_and_limits": {
        "directory": _ARCHIVE_DIRECTORY,
        "packet": "packet-<identity>.json",
        "receipt": "retained-<identity>.json",
        "marker": "completion-<identity>.json",
        "pending_guard": "pending-<identity>.json",
        "admissible_guard": "admissible-<identity>.json",
    },
}


def current_research_packet_schema_metadata_v4() -> dict[str, object]:
    return dict(SCHEMA_DEFINITION_V4)


def current_research_packet_schema_metadata_digest_v4(metadata: object) -> str:
    if type(metadata) is not dict or set(metadata) != {
        "contract_version",
        "type_rows",
        "state_projections",
        "unknown_key_policy",
    }:
        raise ValueError("unknown Packet schema metadata key")
    return _identity(metadata)


def current_research_packet_schema_identity_from_metadata_v4(metadata: object) -> str:
    if _canonical(metadata) != _canonical(SCHEMA_DEFINITION_V4):
        raise ValueError("Packet schema metadata differs from frozen contract")
    return current_research_packet_schema_metadata_digest_v4(metadata)


SCHEMA_IDENTITY_SHA256: Final = (
    current_research_packet_schema_identity_from_metadata_v4(SCHEMA_DEFINITION_V4)
)
CONFIGURATION_IDENTITY_SHA256: Final = _identity(CONFIGURATION_DEFINITION_V4)


@dataclass(frozen=True, slots=True, init=False, repr=False)
class CurrentSuppliedCohortResearchPacketRequestV4:
    contract_version: Literal["current-supplied-cohort-research-packet@v4"]
    decision_cutoff: datetime
    cohort_selected_at: datetime
    members: tuple[object, ...]
    plan21_cohort_identity_sha256: str
    canonical_cohort_identity_sha256: str
    market_context_identity_sha256: str
    request_identity_sha256: str

    def __init__(
        self,
        *,
        decision_cutoff: datetime,
        cohort_selected_at: datetime,
        members: tuple[object, ...],
        market_context_identity_sha256: str,
    ) -> None:
        if (
            not _utc(decision_cutoff)
            or not _utc(cohort_selected_at)
            or cohort_selected_at > decision_cutoff
        ):
            raise ValueError("invalid packet request time")
        admitted_members = _canonical_members(members, decision_cutoff)
        if not _digest(market_context_identity_sha256):
            raise ValueError("invalid market context identity")
        plan21 = _plan21_identity(cohort_selected_at, admitted_members)
        cohort = _canonical_cohort_identity(cohort_selected_at, admitted_members)
        base = {
            "contract_version": _CONTRACT,
            "decision_cutoff": _instant(decision_cutoff),
            "cohort_selected_at": _instant(cohort_selected_at),
            "members": [_member_value(member) for member in admitted_members],
            "plan21_cohort_identity_sha256": plan21,
            "canonical_cohort_identity_sha256": cohort,
            "market_context_identity_sha256": market_context_identity_sha256,
        }
        if not 1 <= len(_canonical(base)) <= _REQUEST_LIMIT:
            raise ValueError("packet request bounds")
        object.__setattr__(self, "contract_version", _CONTRACT)
        object.__setattr__(self, "decision_cutoff", decision_cutoff)
        object.__setattr__(self, "cohort_selected_at", cohort_selected_at)
        object.__setattr__(self, "members", admitted_members)
        object.__setattr__(self, "plan21_cohort_identity_sha256", plan21)
        object.__setattr__(self, "canonical_cohort_identity_sha256", cohort)
        object.__setattr__(
            self, "market_context_identity_sha256", market_context_identity_sha256
        )
        object.__setattr__(self, "request_identity_sha256", _identity(base))

    def value(self, include_identity: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "contract_version": self.contract_version,
            "decision_cutoff": _instant(self.decision_cutoff),
            "cohort_selected_at": _instant(self.cohort_selected_at),
            "members": [_member_value(member) for member in self.members],
            "plan21_cohort_identity_sha256": self.plan21_cohort_identity_sha256,
            "canonical_cohort_identity_sha256": self.canonical_cohort_identity_sha256,
            "market_context_identity_sha256": self.market_context_identity_sha256,
        }
        if include_identity:
            value["request_identity_sha256"] = self.request_identity_sha256
        return value

    def canonical_json_bytes(self, include_identity: bool = True) -> bytes:
        return _canonical(self.value(include_identity))


@dataclass(frozen=True, slots=True, repr=False)
class CurrentResearchPacketComponentLedgerRowV4:
    position: int
    component: str
    contract_version: str | None
    evidence_state: str
    schema_identity_sha256: str | None
    runtime_code_identity_sha256: str | None
    primary_identity_sha256: str | None
    failure_cohort_size: int | None
    identity_bindings: tuple[dict[str, str], ...]
    known_at: datetime | None
    component_reasons: tuple[str, ...]
    packet_reasons: tuple[str, ...]
    ledger_row_identity_sha256: str

    def value(self, include_identity: bool = True) -> dict[str, object]:
        value = _object_value(self, omit="ledger_row_identity_sha256")
        if include_identity:
            value["ledger_row_identity_sha256"] = self.ledger_row_identity_sha256
        return value


@dataclass(frozen=True, slots=True, repr=False)
class CurrentResearchPacketSourceAttributionRowV4:
    position: int
    component: str
    source_state: Literal["BOUND", "UNAVAILABLE"]
    provider_id: str | None
    source_name: str | None
    source_url: str | None
    source_release: str | None
    price_basis: Literal["RAW", "BHARATSTOCK_SOURCE_REPORTED_OHLC"] | None
    publisher_published_at: datetime | None
    known_at: datetime | None
    licence_policy_identity: str | None
    primary_identity_sha256: str | None
    source_row_identity_sha256: str

    def value(self, include_identity: bool = True) -> dict[str, object]:
        value = _object_value(self, omit="source_row_identity_sha256")
        if include_identity:
            value["source_row_identity_sha256"] = self.source_row_identity_sha256
        return value


@dataclass(frozen=True, slots=True, repr=False)
class CurrentResearchPacketMarketDataProjectionV4:
    decision_session: date
    rows: tuple[object, ...]
    projection_identity_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class CurrentResearchPacketMarketRegimeProjectionV4:
    decision_session: date
    comparison_session: date
    regime: Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"]
    advances: int
    declines: int
    unchanged: int
    projection_identity_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class CurrentResearchPacketIndustryProjectionV4:
    classification_tier: Literal["INDUSTRY"]
    industries: tuple[object, ...]
    known_at: datetime
    projection_identity_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class CurrentResearchPacketRedactedEventNoticeV4:
    observation_identity_sha256: str
    deduplication_identity_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class CurrentResearchPacketRedactedEventMemberV4:
    isin: str
    symbol: str
    outcome: Literal["NOTICES_ADMITTED", "NO_MATCHING_NOTICE_IN_SNAPSHOT"]
    notices: tuple[CurrentResearchPacketRedactedEventNoticeV4, ...]


@dataclass(frozen=True, slots=True, repr=False)
class CurrentResearchPacketEventProjectionV4:
    known_at: datetime
    members: tuple[CurrentResearchPacketRedactedEventMemberV4, ...]
    projection_identity_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class CurrentResearchPacketAIObservedV4:
    evidence_state: Literal["OBSERVED"]
    market_data: CurrentResearchPacketMarketDataProjectionV4
    market_regime: CurrentResearchPacketMarketRegimeProjectionV4
    industry_participation: CurrentResearchPacketIndustryProjectionV4
    event_notices: CurrentResearchPacketEventProjectionV4
    partial_current_session: object
    consumer_disposition: None
    ai_projection_identity_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class CurrentResearchPacketAIInsufficientV4:
    evidence_state: Literal["INSUFFICIENT_EVIDENCE"]
    market_data: None
    market_regime: None
    industry_participation: None
    event_notices: None
    partial_current_session: None
    consumer_disposition: Literal["INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"]
    ai_projection_identity_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class CurrentSuppliedCohortResearchPacketV4:
    contract_version: Literal["current-supplied-cohort-research-packet@v4"]
    schema_identity_sha256: str
    configuration_identity_sha256: str
    runtime_code_identity_sha256: str
    request_identity_sha256: str
    canonical_cohort_identity_sha256: str
    market_context_identity_sha256: str
    decision_cutoff: datetime
    decision_session: date
    component_known_at_max: datetime | None
    evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
    component_ledger: tuple[CurrentResearchPacketComponentLedgerRowV4, ...]
    source_attribution: tuple[CurrentResearchPacketSourceAttributionRowV4, ...]
    reasons: tuple[str, ...]
    ai_projection: (
        CurrentResearchPacketAIObservedV4 | CurrentResearchPacketAIInsufficientV4
    )
    packet_identity_sha256: str
    packet_object_sha256: str

    def value(self, include_object_digest: bool = True) -> dict[str, object]:
        value = _object_value(self, omit="packet_object_sha256")
        if not include_object_digest:
            value.pop("packet_identity_sha256")
        if include_object_digest:
            value["packet_object_sha256"] = self.packet_object_sha256
        return value

    def canonical_json_bytes(self) -> bytes:
        return _canonical(self.value())


@dataclass(frozen=True, slots=True, init=False, repr=False)
class _CurrentSuppliedCohortResearchPacketCandidateV4:
    packet: CurrentSuppliedCohortResearchPacketV4
    candidate_identity_sha256: str
    market_context: RetainedCurrentSamePassMarketContextV4
    industry_participation: (
        CurrentIndustryParticipationReportV4 | CurrentIndustryParticipationFailureV4
    )
    event_notices: RetainedCurrentEventNoticeSnapshotV1 | CurrentEventNoticeFailureV1
    _seal: object = field(repr=False, compare=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("research packet candidate is projector-minted only")

    def canonical_json_bytes(self) -> bytes:
        return self.packet.canonical_json_bytes()


@dataclass(frozen=True, slots=True, repr=False)
class CurrentResearchPacketArchiveFailureV4:
    contract_version: Literal[
        "current-supplied-cohort-research-packet-archive-failure@v4"
    ]
    evidence_state: Literal["ARCHIVE_FAILED"]
    reason: Literal["RESEARCH_PACKET_ARCHIVE_FAILED"]
    request_identity_sha256: str
    packet_identity_sha256: str | None
    archive_failure_identity_sha256: str

    def canonical_json_bytes(self) -> bytes:
        return _canonical(_object_value(self))


@dataclass(frozen=True, slots=True, repr=False)
class CurrentResearchPacketReceiptV4:
    contract_version: Literal["current-supplied-cohort-research-packet-receipt@v4"]
    packet_identity_sha256: str
    packet_object_sha256: str
    packet_byte_count: int
    packet_filename: str
    archive_known_at: datetime
    receipt_identity_sha256: str

    def canonical_json_bytes(self) -> bytes:
        return _canonical(_object_value(self))


@dataclass(frozen=True, slots=True, repr=False)
class CurrentResearchPacketCompletionMarkerV4:
    contract_version: Literal["current-supplied-cohort-research-packet-marker@v4"]
    packet_identity_sha256: str
    packet_object_sha256: str
    receipt_identity_sha256: str
    receipt_sha256: str
    archive_known_at: datetime
    completion_marker_identity_sha256: str

    def canonical_json_bytes(self) -> bytes:
        return _canonical(_object_value(self))


@dataclass(frozen=True, slots=True, init=False, repr=False)
class RetainedCurrentSuppliedCohortResearchPacketV4:
    evidence_state: Literal["RETAINED"]
    packet: CurrentSuppliedCohortResearchPacketV4
    receipt_identity_sha256: str
    completion_marker_identity_sha256: str
    archive_known_at: datetime
    retained_identity_sha256: str
    _archive_seal: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("retained research packet is archive-minted only")

    def canonical_json_bytes(self) -> bytes:
        return _canonical(
            {
                "evidence_state": self.evidence_state,
                "packet": self.packet.value(),
                "receipt_identity_sha256": self.receipt_identity_sha256,
                "completion_marker_identity_sha256": self.completion_marker_identity_sha256,
                "archive_known_at": self.archive_known_at,
                "retained_identity_sha256": self.retained_identity_sha256,
            }
        )


def _runtime_root() -> Path:
    source = Path(__file__).resolve()
    root = source.parents[1]
    if not source.is_absolute() or root.name == "":
        raise ValueError("packet runtime identity invalid")
    return root


def _runtime_identity() -> str:
    try:
        manifest = importlib.import_module(_MANIFEST_MODULE)
        mapping = manifest.CURRENT_RESEARCH_PACKET_RUNTIME_SOURCE_DIGESTS_V4
        if (
            type(mapping) is not dict
            or tuple(mapping) != (_RUNTIME_SOURCE,)
            or not _digest(mapping[_RUNTIME_SOURCE])
        ):
            raise ValueError
        source_digest = _runtime_source_sha256(
            __name__, _runtime_root(), _RUNTIME_SOURCE
        )
        manifest_digest = _runtime_source_sha256(
            _MANIFEST_MODULE, _runtime_root(), _MANIFEST_PATH
        )
        if source_digest != mapping[_RUNTIME_SOURCE]:
            raise ValueError
    except (AttributeError, ImportError, OSError, ValueError):
        raise ValueError("packet runtime identity invalid") from None
    return _identity(
        {
            "runtime_manifest_version": "plan27-source-at-rest@v1",
            "modules": [
                {"relative_path": _RUNTIME_SOURCE, "source_sha256": source_digest},
                {"relative_path": _MANIFEST_PATH, "source_sha256": manifest_digest},
            ],
        }
    )


def _successor_types() -> tuple[
    type[object], type[object], type[object], type[object], type[object]
]:
    try:
        regime = importlib.import_module(
            "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v4"
        )
        industry = importlib.import_module(
            "swing_trading_ai_assistant.sector_analysis.current_industry_participation_v4"
        )
        events = importlib.import_module(
            "swing_trading_ai_assistant.market_data.current_event_notice"
        )
        return (
            regime.RetainedCurrentSamePassMarketContextV4,
            industry.CurrentIndustryParticipationReportV4,
            industry.CurrentIndustryParticipationFailureV4,
            events.RetainedCurrentEventNoticeSnapshotV1,
            events.CurrentEventNoticeFailureV1,
        )
    except (AttributeError, ImportError):
        raise ValueError("Plan27 packet dependencies unavailable") from None


def _validated_context(context: object) -> bool:
    """Require V4's closure-owned retained-context validator."""
    try:
        regime = importlib.import_module(
            "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v4"
        )
        return bool(
            regime.validate_retained_current_same_pass_market_context_v4(context)
        )
    except (AttributeError, ImportError, TypeError, ValueError):
        return False


def _named(name: str, identity: object) -> dict[str, str]:
    if not _safe_text(name, 128) or not _digest(identity):
        raise ValueError("invalid identity binding")
    return {"name": name, "identity_sha256": identity}


def _ledger(
    position: int,
    component: str,
    *,
    contract_version: str | None,
    evidence_state: str,
    schema: str | None,
    runtime: str | None,
    primary: str | None,
    failure_size: int | None,
    bindings: tuple[dict[str, str], ...],
    known_at: datetime | None,
    component_reasons: tuple[str, ...],
    packet_reasons: tuple[str, ...],
) -> CurrentResearchPacketComponentLedgerRowV4:
    core = {
        "position": position,
        "component": component,
        "contract_version": contract_version,
        "evidence_state": evidence_state,
        "schema_identity_sha256": schema,
        "runtime_code_identity_sha256": runtime,
        "primary_identity_sha256": primary,
        "failure_cohort_size": failure_size,
        "identity_bindings": bindings,
        "known_at": known_at,
        "component_reasons": component_reasons,
        "packet_reasons": packet_reasons,
    }
    return CurrentResearchPacketComponentLedgerRowV4(
        **core, ledger_row_identity_sha256=_identity(core)
    )


def _packet_reasons(
    unavailable_reason: str, component_reasons: tuple[str, ...]
) -> tuple[str, ...]:
    if any(reason in _SCHEDULE_PREFLIGHT_REASONS for reason in component_reasons):
        raise ValueError("schedule preflight reason cannot enter Packet V4")
    mapped = {
        packet_reason
        for component_reason in component_reasons
        for packet_reason in _UPSTREAM_PACKET_REASON_MAP_V4.get(component_reason, ())
    }
    return _ordered_reasons({unavailable_reason, *mapped})


def _partial_as_complete(partial: object, market: object, regime: object) -> bool:
    """Detect an observed partial session substituted into completed facts.

    Raw V4 structurally validates the partial snapshot and the raw-bar
    provenance.  Packet V4 additionally fails closed if an observed partial
    session can overlap a completed projection.
    """
    if getattr(partial, "state", None) != "OBSERVED":
        return False
    partial_session = getattr(partial, "session", None)
    if type(partial_session) is not date:
        return False
    completed_decision_sessions = (
        getattr(market, "decision_session", None),
        getattr(regime, "decision_session", None),
    )
    if any(
        type(session) is date and partial_session <= session
        for session in completed_decision_sessions
    ):
        return True
    completed_sessions = (
        getattr(market, "comparison_session", None),
        getattr(regime, "decision_session", None),
        getattr(regime, "comparison_session", None),
    )
    if any(session == partial_session for session in completed_sessions):
        return True
    rows = getattr(market, "rows", None)
    return bool(
        type(rows) is tuple
        and any(getattr(row, "session", None) == partial_session for row in rows)
    )


def _unavailable_source(
    position: int, component: str, *, primary: str | None = None
) -> CurrentResearchPacketSourceAttributionRowV4:
    core = {
        "position": position,
        "component": component,
        "source_state": "UNAVAILABLE",
        "provider_id": None,
        "source_name": None,
        "source_url": None,
        "source_release": None,
        "price_basis": None,
        "publisher_published_at": None,
        "known_at": None,
        "licence_policy_identity": None,
        "primary_identity_sha256": primary,
    }
    return CurrentResearchPacketSourceAttributionRowV4(
        **core, source_row_identity_sha256=_identity(core)
    )


def _source(
    position: int,
    component: str,
    *,
    provider_id: str | None,
    source_name: str,
    source_url: str | None,
    source_release: str,
    price_basis: str | None,
    known_at: datetime,
    licence_policy_identity: str | None,
    primary: str,
) -> CurrentResearchPacketSourceAttributionRowV4:
    core = {
        "position": position,
        "component": component,
        "source_state": "BOUND",
        "provider_id": provider_id,
        "source_name": source_name,
        "source_url": source_url,
        "source_release": source_release,
        "price_basis": price_basis,
        "publisher_published_at": None,
        "known_at": known_at,
        "licence_policy_identity": licence_policy_identity,
        "primary_identity_sha256": primary,
    }
    return CurrentResearchPacketSourceAttributionRowV4(
        **core, source_row_identity_sha256=_identity(core)
    )


def _context_seal_bindings(
    context: object, request: CurrentSuppliedCohortResearchPacketRequestV4
) -> (
    tuple[
        str,
        str | None,
        str | None,
        str,
        datetime | None,
        datetime | None,
        str | None,
        str,
        str,
        tuple[str, ...],
        str,
        bool,
    ]
    | None
):
    """Obtain only closure-validated V4 identities, states, and timestamps."""
    try:
        regime = importlib.import_module(
            "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v4"
        )
        projection = regime._packet_projection_from_retained_context_v4(
            context, request
        )
    except (AttributeError, ImportError, TypeError, ValueError):
        return None
    if type(projection) is not dict:
        return None
    values = (
        projection.get("raw_result_identity_sha256"),
        projection.get("raw_grid_identity_sha256"),
        projection.get("raw_source_policy_identity_sha256"),
        projection.get("raw_runtime_code_identity_sha256"),
        projection.get("raw_known_at"),
        projection.get("regime_known_at"),
        projection.get("direction_candidate_identity_sha256"),
        projection.get("adjusted_component_state"),
        projection.get("adjusted_component_identity_sha256"),
        projection.get("adjusted_component_reasons"),
        projection.get("price_basis"),
        projection.get("request_matches"),
    )
    adjusted_state, adjusted_reasons = values[7], values[9]
    adjusted_projection_valid = (
        adjusted_state == "SUCCESS"
        and adjusted_reasons == ()
        or adjusted_state == "NOT_ATTEMPTED"
        and adjusted_reasons == ("UPSTREAM_INSUFFICIENT_EVIDENCE",)
        or adjusted_state
        in {
            "INVALID_REQUEST",
            "UNSUPPORTED_CAPABILITY",
            "INSUFFICIENT_DATA",
            "PROVIDER_FAILURE",
        }
        and type(adjusted_reasons) is tuple
        and len(adjusted_reasons) == 1
        and _safe_text(adjusted_reasons[0], 128)
    )
    if (
        not _digest(values[0])
        or not _digest(values[3])
        or values[4] is not None
        and not _utc(values[4])
        or values[5] is not None
        and not _utc(values[5])
        or not _digest(values[8])
        or not adjusted_projection_valid
        or values[10] != PRICE_BASIS
        or type(values[11]) is not bool
    ):
        return None
    return cast(
        tuple[
            str,
            str | None,
            str | None,
            str,
            datetime | None,
            datetime | None,
            str | None,
            str,
            str,
            tuple[str, ...],
            str,
            bool,
        ],
        values,
    )


def _propagate_adjusted_not_attempted(
    component_reasons: tuple[str, ...],
    identity_bindings: tuple[dict[str, str], ...],
    adjusted_state: object,
    adjusted_identity: object,
    adjusted_reasons: object,
) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    exact = (
        component_reasons != ("PACKET_INVALID_COMPONENT",)
        and adjusted_state == "NOT_ATTEMPTED"
        and adjusted_reasons == ("UPSTREAM_INSUFFICIENT_EVIDENCE",)
        and _digest(adjusted_identity)
    )
    if not exact:
        return component_reasons, identity_bindings
    propagated_reasons = (
        component_reasons
        if "UPSTREAM_INSUFFICIENT_EVIDENCE" in component_reasons
        else (*component_reasons, "UPSTREAM_INSUFFICIENT_EVIDENCE")
    )
    return (
        propagated_reasons,
        (
            *identity_bindings,
            _named("ADJUSTED_NOT_ATTEMPTED", cast(str, adjusted_identity)),
        ),
    )


def _project_context(
    request: CurrentSuppliedCohortResearchPacketRequestV4, context: object
) -> tuple[
    CurrentResearchPacketComponentLedgerRowV4,
    CurrentResearchPacketComponentLedgerRowV4,
    CurrentResearchPacketSourceAttributionRowV4,
    CurrentResearchPacketSourceAttributionRowV4,
    CurrentResearchPacketMarketDataProjectionV4 | None,
    CurrentResearchPacketMarketRegimeProjectionV4 | None,
    object | None,
    set[str],
]:
    """Project the sealed V4 public reports and only seal-bound private identities."""
    reasons: set[str] = set()
    expected_context = request.market_context_identity_sha256
    if getattr(context, "context_identity_sha256", None) != expected_context:
        invalid = "COMPONENT_IDENTITY_INVALID"
        return (
            _ledger(
                0,
                _PACKET_COMPONENTS[0],
                contract_version=None,
                evidence_state="PACKET_INVALID_COMPONENT",
                schema=None,
                runtime=None,
                primary=None,
                failure_size=None,
                bindings=(),
                known_at=None,
                component_reasons=(invalid,),
                packet_reasons=(invalid,),
            ),
            _ledger(
                1,
                _PACKET_COMPONENTS[1],
                contract_version=None,
                evidence_state="PACKET_INVALID_COMPONENT",
                schema=None,
                runtime=None,
                primary=None,
                failure_size=None,
                bindings=(),
                known_at=None,
                component_reasons=(invalid,),
                packet_reasons=(invalid,),
            ),
            _unavailable_source(0, _PACKET_COMPONENTS[0]),
            _unavailable_source(1, _PACKET_COMPONENTS[1]),
            None,
            None,
            None,
            {invalid},
        )
    market = getattr(context, "market_data_report", None)
    regime = getattr(context, "market_regime_report", None)
    partial = getattr(context, "partial_current_session", None)
    sealed = _context_seal_bindings(context, request)
    if sealed is None:
        seal_bindings = None
        raw_known_at = None
        regime_known_at = None
        direction_identity = None
        adjusted_state = None
        adjusted_identity = None
        adjusted_reasons: tuple[str, ...] = ()
        selected_price_basis = None
        request_matches = False
    else:
        (
            raw_result_identity,
            raw_grid_identity,
            raw_source_policy,
            raw_runtime,
            raw_known_at,
            regime_known_at,
            direction_identity,
            adjusted_state,
            adjusted_identity,
            adjusted_reasons,
            selected_price_basis,
            request_matches,
        ) = sealed
        seal_bindings = (
            raw_result_identity,
            raw_grid_identity,
            raw_source_policy,
            raw_runtime,
        )
    if getattr(regime, "decision_cutoff", None) != request.decision_cutoff:
        reasons.add("DECISION_CUTOFF_MISMATCH")
    if not request_matches:
        reasons.add("COHORT_PROJECTION_MISMATCH")
    if getattr(market, "decision_session", None) != getattr(
        regime, "decision_session", None
    ) or getattr(market, "comparison_session", None) != getattr(
        regime, "comparison_session", None
    ):
        reasons.add("DECISION_SESSION_MISMATCH")
    if _partial_as_complete(partial, market, regime):
        reasons.add("PARTIAL_AS_COMPLETE")
    context_identity = expected_context
    market_observed = (
        getattr(market, "contract_version", None)
        == "current-same-pass-decision-market-data@v4"
        and getattr(market, "evidence_state", None) == "OBSERVED"
        and type(getattr(market, "rows", None)) is tuple
        and len(market.rows) == len(request.members)
        and getattr(market, "canonical_cohort_identity_sha256", None)
        == request.canonical_cohort_identity_sha256
        and _digest(getattr(market, "report_identity_sha256", None))
        and seal_bindings is not None
        and _digest(seal_bindings[1])
        and _digest(seal_bindings[2])
    )
    if market_observed:
        rows = market.rows
        known_at = raw_known_at
        projection_core = {
            "decision_session": market.decision_session,
            "rows": rows,
        }
        market_projection = CurrentResearchPacketMarketDataProjectionV4(
            **projection_core, projection_identity_sha256=_identity(projection_core)
        )
        market_ledger = _ledger(
            0,
            _PACKET_COMPONENTS[0],
            contract_version=market.contract_version,
            evidence_state="OBSERVED",
            schema=current_same_pass_raw_daily_schema_identity_v4(),
            runtime=seal_bindings[3],
            primary=market.report_identity_sha256,
            failure_size=None,
            bindings=(
                _named("CONTEXT", context_identity),
                _named("RAW_RESULT", seal_bindings[0]),
                _named("RAW_GRID", seal_bindings[1]),
                _named("MARKET_DATA_REPORT", market.report_identity_sha256),
            ),
            known_at=known_at,
            component_reasons=(),
            packet_reasons=(),
        )
        market_source = _source(
            0,
            _PACKET_COMPONENTS[0],
            provider_id="UPSTOX",
            source_name="UPSTOX_RETAINED_RAW_DAILY",
            source_url=None,
            source_release=seal_bindings[2],
            price_basis="RAW",
            known_at=known_at,
            licence_policy_identity=None,
            primary=market.report_identity_sha256,
        )
    else:
        component_reasons = (
            tuple(getattr(market, "reasons", ()))
            if getattr(market, "contract_version", None)
            == "current-same-pass-decision-market-data@v4"
            else ("PACKET_INVALID_COMPONENT",)
        )
        packet_reasons = (
            _packet_reasons("MARKET_DATA_UNAVAILABLE", component_reasons)
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else ("COMPONENT_IDENTITY_INVALID",)
        )
        reasons.update(packet_reasons)
        market_ledger = _ledger(
            0,
            _PACKET_COMPONENTS[0],
            contract_version=getattr(market, "contract_version", None)
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else None,
            evidence_state="INSUFFICIENT_EVIDENCE"
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else "PACKET_INVALID_COMPONENT",
            schema=current_same_pass_raw_daily_schema_identity_v4()
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else None,
            runtime=seal_bindings[3]
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            and seal_bindings is not None
            else None,
            primary=getattr(market, "report_identity_sha256", None)
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else None,
            failure_size=len(request.members)
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else None,
            bindings=(
                _named("CONTEXT", context_identity),
                _named("RAW_RESULT", seal_bindings[0]),
                _named("MARKET_DATA_REPORT", market.report_identity_sha256),
            )
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            and seal_bindings is not None
            and _digest(getattr(market, "report_identity_sha256", None))
            else (),
            known_at=raw_known_at
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else None,
            component_reasons=component_reasons,
            packet_reasons=packet_reasons,
        )
        market_source = _unavailable_source(0, _PACKET_COMPONENTS[0])
        market_projection = None
    regime_observed = (
        getattr(regime, "contract_version", None)
        == "current-supplied-cohort-market-regime@v4"
        and getattr(regime, "evidence_state", None) == "OBSERVED"
        and getattr(regime, "canonical_cohort_identity_sha256", None)
        == request.canonical_cohort_identity_sha256
        and getattr(regime, "market_data_report_identity_sha256", None)
        == getattr(market, "report_identity_sha256", None)
        and _digest(getattr(regime, "report_identity_sha256", None))
        and _digest(getattr(regime, "adjusted_handoff_identity_sha256", None))
        and adjusted_state == "SUCCESS"
        and selected_price_basis == PRICE_BASIS
    )
    if regime_observed:
        known_at = regime_known_at
        core = {
            "decision_session": regime.decision_session,
            "comparison_session": regime.comparison_session,
            "regime": regime.regime,
            "advances": regime.advances,
            "declines": regime.declines,
            "unchanged": regime.unchanged,
        }
        regime_projection = CurrentResearchPacketMarketRegimeProjectionV4(
            **core, projection_identity_sha256=_identity(core)
        )
        if not _digest(direction_identity):
            reasons.add("COMPONENT_IDENTITY_INVALID")
            regime_ledger = _ledger(
                1,
                _PACKET_COMPONENTS[1],
                contract_version=None,
                evidence_state="PACKET_INVALID_COMPONENT",
                schema=None,
                runtime=None,
                primary=None,
                failure_size=None,
                bindings=(),
                known_at=None,
                component_reasons=("PACKET_INVALID_COMPONENT",),
                packet_reasons=("COMPONENT_IDENTITY_INVALID",),
            )
            regime_source = _unavailable_source(1, _PACKET_COMPONENTS[1])
            regime_projection = None
        else:
            regime_ledger = _ledger(
                1,
                _PACKET_COMPONENTS[1],
                contract_version=regime.contract_version,
                evidence_state="OBSERVED",
                schema=regime.schema_identity_sha256,
                runtime=regime.runtime_code_identity_sha256,
                primary=regime.report_identity_sha256,
                failure_size=None,
                bindings=(
                    _named("CONTEXT", context_identity),
                    _named("MARKET_REGIME_REPORT", regime.report_identity_sha256),
                    _named("DIRECTION_CANDIDATE", direction_identity),
                ),
                known_at=known_at,
                component_reasons=(),
                packet_reasons=(),
            )
            regime_source = _source(
                1,
                _PACKET_COMPONENTS[1],
                provider_id=None,
                source_name="DETERMINISTIC_SAME_PASS_MARKET_REGIME",
                source_url=None,
                source_release="current-supplied-cohort-market-regime@v4",
                price_basis=selected_price_basis,
                known_at=known_at,
                licence_policy_identity=None,
                primary=regime.report_identity_sha256,
            )
    else:
        component_reasons = (
            tuple(getattr(regime, "reasons", ()))
            if getattr(regime, "contract_version", None)
            == "current-supplied-cohort-market-regime@v4"
            else ("PACKET_INVALID_COMPONENT",)
        )
        regime_bindings = (
            (
                _named("CONTEXT", context_identity),
                _named("MARKET_REGIME_REPORT", regime.report_identity_sha256),
            )
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            and _digest(getattr(regime, "report_identity_sha256", None))
            else ()
        )
        component_reasons, regime_bindings = _propagate_adjusted_not_attempted(
            component_reasons,
            regime_bindings,
            adjusted_state,
            adjusted_identity,
            adjusted_reasons,
        )
        packet_reasons = (
            _packet_reasons("MARKET_REGIME_UNAVAILABLE", component_reasons)
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else ("COMPONENT_IDENTITY_INVALID",)
        )
        reasons.update(packet_reasons)
        regime_ledger = _ledger(
            1,
            _PACKET_COMPONENTS[1],
            contract_version=getattr(regime, "contract_version", None)
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else None,
            evidence_state="INSUFFICIENT_EVIDENCE"
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else "PACKET_INVALID_COMPONENT",
            schema=getattr(regime, "schema_identity_sha256", None)
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else None,
            runtime=getattr(regime, "runtime_code_identity_sha256", None)
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else None,
            primary=getattr(regime, "report_identity_sha256", None)
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else None,
            failure_size=len(request.members)
            if component_reasons != ("PACKET_INVALID_COMPONENT",)
            else None,
            bindings=regime_bindings,
            known_at=regime_known_at,
            component_reasons=component_reasons,
            packet_reasons=packet_reasons,
        )
        regime_source = _unavailable_source(1, _PACKET_COMPONENTS[1])
        regime_projection = None
    return (
        market_ledger,
        regime_ledger,
        market_source,
        regime_source,
        market_projection,
        regime_projection,
        partial,
        reasons,
    )


def _project_industry(
    request: CurrentSuppliedCohortResearchPacketRequestV4,
    context: object,
    value: object,
) -> tuple[
    CurrentResearchPacketComponentLedgerRowV4,
    CurrentResearchPacketSourceAttributionRowV4,
    CurrentResearchPacketIndustryProjectionV4 | None,
    set[str],
]:
    reasons: set[str] = set()
    component = _PACKET_COMPONENTS[2]
    _, industry_report_type, industry_failure_type, _, _ = _successor_types()
    try:
        industry_module = importlib.import_module(
            "swing_trading_ai_assistant.sector_analysis."
            "current_industry_participation_v4"
        )
        exact_industry = (
            industry_module.current_industry_participation_is_exact_valid_v4(
                value, context
            )
        )
    except (AttributeError, ImportError, TypeError, ValueError):
        return _invalid_component(2, component)
    if (
        type(value) is industry_report_type
        and exact_industry
        and value.contract_version
        == "current-supplied-cohort-industry-participation@v4"
        and value.evidence_state == "OBSERVED"
        and value.schema_identity_sha256
        and value.runtime_code_identity_sha256
        and value.calculation_identity_sha256
        and all(
            _digest(item)
            for item in (
                value.schema_identity_sha256,
                value.runtime_code_identity_sha256,
                value.calculation_identity_sha256,
                value.report_identity_sha256,
                value.direction_candidate_identity_sha256,
                value.classification_input_identity_sha256,
                value.artifact_sha256,
                value.snapshot_identity_sha256,
                value.archive_identity_sha256,
                value.archive_receipt_identity_sha256,
                value.retained_classification_identity_sha256,
            )
        )
        and value.canonical_cohort_identity_sha256
        == request.canonical_cohort_identity_sha256
        and value.market_regime_report_identity_sha256
        == getattr(
            getattr(context, "market_regime_report", None),
            "report_identity_sha256",
            None,
        )
        and value.decision_cutoff == request.decision_cutoff
        and value.known_at <= request.decision_cutoff
        and value.classification_tier == "INDUSTRY"
        and value.source_attribution == "NSE_INDICES"
        and value.publisher_published_at is None
        and value.publisher_effective_from is None
        and value.publisher_effective_through is None
        and value.publisher_revision is None
        and type(value.industries) is tuple
        and 1 <= len(value.industries) <= len(request.members)
        and tuple(row.industry for row in value.industries)
        == tuple(sorted(row.industry for row in value.industries))
        and sum(row.member_count for row in value.industries) == len(request.members)
        and value.reasons == ()
        and value.report_identity_sha256
        == _sha(value.canonical_json_bytes(include_identity=False))
    ):
        primary = getattr(value, "report_identity_sha256", None)
        if not _digest(primary) or not _utc(getattr(value, "known_at", None)):
            return _invalid_component(2, component)
        bindings = tuple(
            _named(name, getattr(value, attr))
            for name, attr in (
                ("MARKET_REGIME_REPORT", "market_regime_report_identity_sha256"),
                ("DIRECTION_CANDIDATE", "direction_candidate_identity_sha256"),
                ("CLASSIFICATION_INPUT", "classification_input_identity_sha256"),
                ("ARTIFACT", "artifact_sha256"),
                ("SNAPSHOT", "snapshot_identity_sha256"),
                ("ARCHIVE", "archive_identity_sha256"),
                ("ARCHIVE_RECEIPT", "archive_receipt_identity_sha256"),
                ("RETAINED_CLASSIFICATION", "retained_classification_identity_sha256"),
                ("INDUSTRY_REPORT", "report_identity_sha256"),
            )
        )
        core = {
            "classification_tier": value.classification_tier,
            "industries": value.industries,
            "known_at": value.known_at,
        }
        projection = CurrentResearchPacketIndustryProjectionV4(
            **core, projection_identity_sha256=_identity(core)
        )
        ledger = _ledger(
            2,
            component,
            contract_version=value.contract_version,
            evidence_state="OBSERVED",
            schema=value.schema_identity_sha256,
            runtime=value.runtime_code_identity_sha256,
            primary=primary,
            failure_size=None,
            bindings=bindings,
            known_at=value.known_at,
            component_reasons=(),
            packet_reasons=(),
        )
        source = _source(
            2,
            component,
            provider_id="NSE_INDICES",
            source_name="NSE_INDICES_INDUSTRY_CLASSIFICATION",
            source_url=value.source_url,
            source_release=value.artifact_revision,
            price_basis=None,
            known_at=value.known_at,
            licence_policy_identity=None,
            primary=primary,
        )
        return ledger, source, projection, reasons
    if type(value) is industry_failure_type and exact_industry:
        component_reasons = value.reasons
        primary = value.failure_identity_sha256
        known_at = value.known_at
        if (
            value.contract_version
            != "current-supplied-cohort-industry-participation-failure@v4"
            or value.evidence_state
            not in {
                "MALFORMED_EVIDENCE",
                "UNSUPPORTED_CAPABILITY",
                "INSUFFICIENT_EVIDENCE",
            }
            or value.canonical_cohort_identity_sha256
            != request.canonical_cohort_identity_sha256
            or value.cohort_size != len(request.members)
            or value.decision_cutoff != request.decision_cutoff
            or value.industries is not None
            or type(component_reasons) is not tuple
            or not component_reasons
            or not _digest(primary)
            or (
                known_at is not None
                and (
                    not _utc(known_at)
                    or (
                        known_at > request.decision_cutoff
                        and "CLASSIFICATION_FUTURE_KNOWN" not in component_reasons
                    )
                )
            )
            or primary != _sha(value.canonical_json_bytes(include_identity=False))
        ):
            return _invalid_component(2, component)
        packet_reasons = _packet_reasons(
            "INDUSTRY_PARTICIPATION_UNAVAILABLE", component_reasons
        )
        reasons.update(packet_reasons)
        return (
            _ledger(
                2,
                component,
                contract_version=value.contract_version,
                evidence_state=value.evidence_state,
                schema=None,
                runtime=None,
                primary=primary,
                failure_size=len(request.members),
                bindings=(_named("INDUSTRY_FAILURE", primary),),
                known_at=known_at,
                component_reasons=component_reasons,
                packet_reasons=packet_reasons,
            ),
            _unavailable_source(2, component),
            None,
            reasons,
        )
    return _invalid_component(2, component)


def _validated_redacted_events(  # noqa: C901 - exact delivered value revalidation.
    request: CurrentSuppliedCohortResearchPacketRequestV4, value: object
) -> tuple[object, ...] | None:
    """Revalidate every identity the delivered Plan-25 retained value exposes."""
    try:
        current_runtime = current_event_notice_runtime_code_identity_v1()
    except ValueError:
        return None
    if type(value) is not _RetainedCurrentEventNoticeSnapshotV1:
        return None
    delivered_legacy = (
        value.schema_identity_sha256 == LEGACY_EVENT_NOTICE_SCHEMA_IDENTITY_SHA256
        and value.runtime_code_identity_sha256
        == _DELIVERED_EVENT_NOTICE_RUNTIME_IDENTITY_V1
    )
    runtime = (
        _DELIVERED_EVENT_NOTICE_RUNTIME_IDENTITY_V1
        if delivered_legacy
        else current_runtime
    )
    members = value.members
    known_at = value.known_at
    filename_date = _event_filename_date(value.source_filename)
    if (
        type(members) is not tuple
        or len(members) != len(request.members)
        or value.evidence_state != "RETAINED"
        or value.contract_version != _EVENT_CONTRACT
        or value.schema_identity_sha256
        not in (
            LEGACY_EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
            EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
        )
        or value.source_url != _EVENT_SOURCE_URL
        or value.nse_attribution != "NSE"
        or value.source_segment != "Equity"
        or value.source_window != "1D"
        or not _event_source_case_is_exact(
            value.schema_identity_sha256,
            value.acquisition_method,
            value.licence_policy_identity,
            value.source_filename,
            value.source_encoding,
            value.source_has_bom,
        )
        or filename_date is None
        or not _utc(known_at)
        or known_at.astimezone(_EVENT_IST).date() != filename_date
    ):
        return None
    if any(type(member) is not _CurrentEventNoticeMemberResultV1 for member in members):
        return None
    plan25_cohort_identity = _identity(
        {"members": [member.value()["member"] for member in members]}
    )
    snapshot_core = {
        "contract_version": _EVENT_CONTRACT,
        "schema_identity_sha256": value.schema_identity_sha256,
        "artifact_identity_sha256": value.artifact_identity_sha256,
        "source_url": value.source_url,
        "source_segment": value.source_segment,
        "source_window": value.source_window,
        "source_filename": value.source_filename,
        "licence_policy_identity": value.licence_policy_identity,
        "cohort_size": value.cohort_size,
        "members": [member.value() for member in members],
    }
    if not delivered_legacy:
        snapshot_core.update(
            {
                "source_encoding": value.source_encoding,
                "source_has_bom": value.source_has_bom,
                "acquisition_method": value.acquisition_method,
            }
        )
    snapshot = _identity(snapshot_core)
    archive = _identity(
        {
            "artifact_identity_sha256": value.artifact_identity_sha256,
            "snapshot_identity_sha256": snapshot,
            "contract_version": _EVENT_CONTRACT,
            "archive_protocol": _EVENT_ARCHIVE_PROTOCOL,
        }
    )
    known_text = _instant(known_at)
    receipt_core: dict[str, object] = {
        "version": _EVENT_RECEIPT_VERSION,
        "artifact_identity_sha256": value.artifact_identity_sha256,
        "snapshot_identity_sha256": snapshot,
        "archive_identity_sha256": archive,
        "runtime_code_identity_sha256": runtime,
        "known_at": known_text,
    }
    if not delivered_legacy:
        receipt_core.update(
            {
                "acquisition_method": value.acquisition_method,
                "licence_policy_identity": value.licence_policy_identity,
                "source_filename": value.source_filename,
                "source_encoding": value.source_encoding,
                "source_has_bom": value.source_has_bom,
            }
        )
    receipt = _identity(receipt_core)
    retained = _identity({**receipt_core, "receipt_identity_sha256": receipt})
    if (
        not all(
            _digest(item)
            for item in (
                value.artifact_identity_sha256,
                value.snapshot_identity_sha256,
                value.archive_identity_sha256,
                value.receipt_identity_sha256,
                value.retained_identity_sha256,
            )
        )
        or value.runtime_code_identity_sha256 != runtime
        or value.snapshot_identity_sha256 != snapshot
        or value.archive_identity_sha256 != archive
        or value.receipt_identity_sha256 != receipt
        or value.retained_identity_sha256 != retained
        or value.cohort_identity_sha256 != plan25_cohort_identity
        or value.cohort_size != len(request.members)
        or value.member_count != len(request.members)
    ):
        return None
    projection: dict[str, object] = {}
    total_notices = 0
    for requested, member_result in zip(
        sorted(request.members, key=lambda member: member.isin), members, strict=True
    ):
        if type(member_result) is not _CurrentEventNoticeMemberResultV1:
            return None
        member = member_result.member
        notices = member_result.notices
        if (
            type(member) is not _CurrentEventCohortMemberV1
            or member.isin != requested.isin
            or member.exchange != "NSE"
            or member.symbol != requested.effective_symbol
            or member.listed_equity_segment != requested.instrument_type
            or member.listed_equity_segment != "EQUITY"
            or member.effective_from != requested.valid_from
            or member.effective_through != requested.valid_through
            or member.provider_mapping_revision != requested.provider_mapping_revision
            or member_result.outcome
            not in {"NOTICES_ADMITTED", "NO_MATCHING_NOTICE_IN_SNAPSHOT"}
            or type(notices) is not tuple
            or (member_result.outcome == "NO_MATCHING_NOTICE_IN_SNAPSHOT" and notices)
            or (member_result.outcome == "NOTICES_ADMITTED" and not notices)
        ):
            return None
        total_notices += len(notices)
        if total_notices > 10_000:
            return None
        redacted_notices: list[CurrentResearchPacketRedactedEventNoticeV4] = []
        for notice in notices:
            if (
                type(notice) is not _CurrentEventNoticeV1
                or notice.member != member
                or notice.source_symbol != requested.effective_symbol
                or not _digest(notice.observation_identity_sha256)
                or not _digest(notice.deduplication_identity_sha256)
                or any(
                    value is not None
                    for value in (
                        notice.publisher_timezone,
                        notice.event_at,
                        notice.publisher_event_id,
                        notice.publisher_revision_id,
                        notice.correction_of,
                    )
                )
            ):
                return None
            redacted_notices.append(
                CurrentResearchPacketRedactedEventNoticeV4(
                    observation_identity_sha256=notice.observation_identity_sha256,
                    deduplication_identity_sha256=notice.deduplication_identity_sha256,
                )
            )
        projection[requested.isin] = CurrentResearchPacketRedactedEventMemberV4(
            isin=requested.isin,
            symbol=requested.effective_symbol,
            outcome=member_result.outcome,
            notices=tuple(redacted_notices),
        )
    return tuple(projection[member.isin] for member in request.members)


def _event_current_reason(
    request: CurrentSuppliedCohortResearchPacketRequestV4,
    value: _RetainedCurrentEventNoticeSnapshotV1,
) -> str | None:
    """Apply Packet V4's current-request boundary to a valid Plan-25 snapshot."""
    filename_date = _event_filename_date(value.source_filename)
    cutoff_date = request.decision_cutoff.astimezone(_EVENT_IST).date()
    if filename_date is None:
        raise ValueError("validated event filename date unavailable")
    if filename_date < cutoff_date:
        return "EVENT_SOURCE_DATE_STALE"
    if filename_date > cutoff_date or value.known_at > request.decision_cutoff:
        return "EVENT_SOURCE_DATE_FUTURE"
    return None


def _event_failure_projection_identity(
    component: str,
    reason: str,
    value: _RetainedCurrentEventNoticeSnapshotV1,
) -> str:
    """Bind a valid but inadmissible retained event snapshot without republishing it."""
    source_date = _event_filename_date(value.source_filename)
    if source_date is None:
        raise ValueError("validated event filename date unavailable")
    return _identity(
        {
            "component": component,
            "state": "INSUFFICIENT_EVIDENCE",
            "reasons": (reason,),
            "retained_event_evidence": {
                "retained_identity_sha256": value.retained_identity_sha256,
                "known_at": value.known_at,
                "source_date": source_date,
                "artifact_identity_sha256": value.artifact_identity_sha256,
                "snapshot_identity_sha256": value.snapshot_identity_sha256,
                "archive_identity_sha256": value.archive_identity_sha256,
                "receipt_identity_sha256": value.receipt_identity_sha256,
            },
        }
    )


def _project_events(
    request: CurrentSuppliedCohortResearchPacketRequestV4, value: object
) -> tuple[
    CurrentResearchPacketComponentLedgerRowV4,
    CurrentResearchPacketSourceAttributionRowV4,
    CurrentResearchPacketEventProjectionV4 | None,
    set[str],
]:
    reasons: set[str] = set()
    component = _PACKET_COMPONENTS[3]
    redacted_members = _validated_redacted_events(request, value)
    if (
        getattr(value, "evidence_state", None) == "RETAINED"
        and redacted_members is not None
    ):
        current_reason = _event_current_reason(request, value)
        if current_reason is not None:
            component_reasons = (current_reason,)
            packet_reasons = _packet_reasons(
                "EVENT_NOTICES_UNAVAILABLE", component_reasons
            )
            reasons.update(packet_reasons)
            failure_identity = _event_failure_projection_identity(
                component, current_reason, value
            )
            return (
                _ledger(
                    3,
                    component,
                    contract_version=None,
                    evidence_state="INSUFFICIENT_EVIDENCE",
                    schema=None,
                    runtime=None,
                    primary=None,
                    failure_size=len(request.members),
                    bindings=(_named("FAILURE_PROJECTION", failure_identity),),
                    known_at=None,
                    component_reasons=component_reasons,
                    packet_reasons=packet_reasons,
                ),
                _unavailable_source(3, component, primary=failure_identity),
                None,
                reasons,
            )
        primary = value.retained_identity_sha256
        known_at = value.known_at
        bindings = tuple(
            _named(name, getattr(value, attr))
            for name, attr in (
                ("ARTIFACT", "artifact_identity_sha256"),
                ("SNAPSHOT", "snapshot_identity_sha256"),
                ("ARCHIVE", "archive_identity_sha256"),
                ("RECEIPT", "receipt_identity_sha256"),
                ("RETAINED", "retained_identity_sha256"),
            )
        )
        core = {"known_at": known_at, "members": redacted_members}
        projection = CurrentResearchPacketEventProjectionV4(
            **core, projection_identity_sha256=_identity(core)
        )
        ledger = _ledger(
            3,
            component,
            contract_version=value.contract_version,
            evidence_state="RETAINED",
            schema=value.schema_identity_sha256,
            runtime=value.runtime_code_identity_sha256,
            primary=primary,
            failure_size=None,
            bindings=bindings,
            known_at=known_at,
            component_reasons=(),
            packet_reasons=(),
        )
        source = _source(
            3,
            component,
            provider_id="NSE",
            source_name="NSE_EQUITY_CORPORATE_ANNOUNCEMENTS",
            source_url=value.source_url,
            source_release=value.source_filename,
            price_basis=None,
            known_at=known_at,
            licence_policy_identity=value.licence_policy_identity,
            primary=primary,
        )
        return ledger, source, projection, reasons
    if type(value) is _CurrentEventNoticeFailureV1:
        component_reasons = value.reasons
        if (
            type(component_reasons) is not tuple
            or len(component_reasons) != 1
            or component_reasons
            != tuple(
                reason
                for reason in _EVENT_FAILURE_REASON_ORDER
                if reason in component_reasons
            )
            or any(
                type(reason) is not str
                or reason not in _EVENT_FAILURE_STATES
                or _EVENT_FAILURE_STATES[reason] != value.evidence_state
                for reason in component_reasons
            )
            or value.evidence_state
            not in {
                "MALFORMED_EVIDENCE",
                "UNSUPPORTED_CAPABILITY",
                "INSUFFICIENT_EVIDENCE",
                "CONFLICTED_EVIDENCE",
            }
            or value.cohort_size != len(request.members)
        ):
            return _invalid_component(3, component)
        failure_identity = _identity(
            {
                "component": component,
                "state": value.evidence_state,
                "reasons": component_reasons,
            }
        )
        packet_reasons = _packet_reasons("EVENT_NOTICES_UNAVAILABLE", component_reasons)
        reasons.update(packet_reasons)
        return (
            _ledger(
                3,
                component,
                contract_version=None,
                evidence_state=value.evidence_state,
                schema=None,
                runtime=None,
                primary=None,
                failure_size=len(request.members),
                bindings=(_named("FAILURE_PROJECTION", failure_identity),),
                known_at=None,
                component_reasons=component_reasons,
                packet_reasons=packet_reasons,
            ),
            _unavailable_source(3, component),
            None,
            reasons,
        )
    return _invalid_component(3, component)


def _invalid_component(position: int, component: str) -> tuple[Any, Any, Any, set[str]]:
    reason = "COMPONENT_IDENTITY_INVALID"
    ledger = _ledger(
        position,
        component,
        contract_version=None,
        evidence_state="PACKET_INVALID_COMPONENT",
        schema=None,
        runtime=None,
        primary=None,
        failure_size=None,
        bindings=(),
        known_at=None,
        component_reasons=("PACKET_INVALID_COMPONENT",),
        packet_reasons=(reason,),
    )
    return ledger, _unavailable_source(position, component), None, {reason}


def _packet_is_exact(
    request: CurrentSuppliedCohortResearchPacketRequestV4,
    packet: object,
    market_context: object,
    industry_participation: object,
    event_notices: object,
) -> bool:
    """Replay every packet component from the sealed candidate upstream values."""
    if (
        type(request) is not CurrentSuppliedCohortResearchPacketRequestV4
        or type(packet) is not CurrentSuppliedCohortResearchPacketV4
        or packet.contract_version != _CONTRACT
        or packet.schema_identity_sha256 != SCHEMA_IDENTITY_SHA256
        or packet.configuration_identity_sha256 != CONFIGURATION_IDENTITY_SHA256
        or packet.runtime_code_identity_sha256 != _runtime_identity()
        or packet.request_identity_sha256 != request.request_identity_sha256
        or packet.canonical_cohort_identity_sha256
        != request.canonical_cohort_identity_sha256
        or packet.market_context_identity_sha256
        != request.market_context_identity_sha256
        or packet.decision_cutoff != request.decision_cutoff
        or packet.evidence_state not in {"OBSERVED", "INSUFFICIENT_EVIDENCE"}
        or not _digest(packet.packet_identity_sha256)
        or not _digest(packet.packet_object_sha256)
    ):
        return False
    try:
        replayed = _project_packet(
            request,
            market_context,
            industry_participation,
            event_notices,
        )
        return (
            replayed.canonical_json_bytes() == packet.canonical_json_bytes()
            and replayed.packet_identity_sha256 == packet.packet_identity_sha256
            and replayed.packet_object_sha256 == packet.packet_object_sha256
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _candidate_structure_is_exact(
    request: CurrentSuppliedCohortResearchPacketRequestV4, candidate: object
) -> bool:
    if type(candidate) is not _CurrentSuppliedCohortResearchPacketCandidateV4:
        return False
    packet = candidate.packet
    return _packet_is_exact(
        request,
        packet,
        candidate.market_context,
        candidate.industry_participation,
        candidate.event_notices,
    ) and (
        candidate.candidate_identity_sha256
        == _identity(
            {
                "packet_identity_sha256": packet.packet_identity_sha256,
                "packet_object_sha256": packet.packet_object_sha256,
            }
        )
    )


def _project_packet(
    request: CurrentSuppliedCohortResearchPacketRequestV4,
    market_context: object,
    industry: object,
    events: object,
) -> CurrentSuppliedCohortResearchPacketV4:
    runtime = _runtime_identity()
    (
        market_ledger,
        regime_ledger,
        market_source,
        regime_source,
        market_projection,
        regime_projection,
        partial,
        reasons,
    ) = _project_context(request, market_context)
    industry_ledger, industry_source, industry_projection, industry_reasons = (
        _project_industry(request, market_context, industry)
    )
    event_ledger, event_source, event_projection, event_reasons = _project_events(
        request, events
    )
    reasons.update(industry_reasons)
    reasons.update(event_reasons)
    ledger = (market_ledger, regime_ledger, industry_ledger, event_ledger)
    sources = (market_source, regime_source, industry_source, event_source)
    reasons.update(reason for row in ledger for reason in row.packet_reasons)
    ordered = _ordered_reasons(reasons)
    decision_session = getattr(
        getattr(market_context, "market_regime_report", None), "decision_session", None
    )
    if type(decision_session) is not date:
        raise ValueError("sealed context decision session unavailable")
    known_times = [row.known_at for row in ledger if _utc(row.known_at)]
    component_known_at_max = max(known_times) if known_times else None
    if (
        component_known_at_max is not None
        and component_known_at_max > request.decision_cutoff
    ):
        ordered = _ordered_reasons(set(ordered) | {"COMPONENT_FUTURE_KNOWN"})
    observed = not ordered and all(
        row.evidence_state in {"OBSERVED", "RETAINED"} for row in ledger
    )
    if observed:
        if (
            market_projection is None
            or regime_projection is None
            or industry_projection is None
            or event_projection is None
            or partial is None
        ):
            raise ValueError("sealed observed projection unavailable")
        ai_core = {
            "evidence_state": "OBSERVED",
            "market_data": market_projection,
            "market_regime": regime_projection,
            "industry_participation": industry_projection,
            "event_notices": event_projection,
            "partial_current_session": partial,
            "consumer_disposition": None,
        }
        ai_projection: (
            CurrentResearchPacketAIObservedV4 | CurrentResearchPacketAIInsufficientV4
        ) = CurrentResearchPacketAIObservedV4(
            **ai_core, ai_projection_identity_sha256=_identity(ai_core)
        )
        state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"] = "OBSERVED"
    else:
        ai_core = {
            "evidence_state": "INSUFFICIENT_EVIDENCE",
            "market_data": None,
            "market_regime": None,
            "industry_participation": None,
            "event_notices": None,
            "partial_current_session": None,
            "consumer_disposition": "INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED",
        }
        ai_projection = CurrentResearchPacketAIInsufficientV4(
            **ai_core, ai_projection_identity_sha256=_identity(ai_core)
        )
        state = "INSUFFICIENT_EVIDENCE"
    core = {
        "contract_version": _CONTRACT,
        "schema_identity_sha256": SCHEMA_IDENTITY_SHA256,
        "configuration_identity_sha256": CONFIGURATION_IDENTITY_SHA256,
        "runtime_code_identity_sha256": runtime,
        "request_identity_sha256": request.request_identity_sha256,
        "canonical_cohort_identity_sha256": request.canonical_cohort_identity_sha256,
        "market_context_identity_sha256": request.market_context_identity_sha256,
        "decision_cutoff": request.decision_cutoff,
        "decision_session": decision_session,
        "component_known_at_max": component_known_at_max,
        "evidence_state": state,
        "component_ledger": ledger,
        "source_attribution": sources,
        "reasons": ordered,
        "ai_projection": ai_projection,
    }
    packet_identity = _identity(
        {
            "contract_version": core["contract_version"],
            "schema_identity_sha256": core["schema_identity_sha256"],
            "configuration_identity_sha256": core["configuration_identity_sha256"],
            "runtime_code_identity_sha256": core["runtime_code_identity_sha256"],
            "request_identity_sha256": core["request_identity_sha256"],
            "canonical_cohort_identity_sha256": core[
                "canonical_cohort_identity_sha256"
            ],
            "market_context_identity_sha256": core["market_context_identity_sha256"],
            "decision_cutoff": core["decision_cutoff"],
            "decision_session": core["decision_session"],
            "component_known_at_max": core["component_known_at_max"],
            "evidence_state": core["evidence_state"],
            "component_ledger_row_identities": tuple(
                row.ledger_row_identity_sha256 for row in ledger
            ),
            "source_row_identities": tuple(
                row.source_row_identity_sha256 for row in sources
            ),
            "reasons": core["reasons"],
            "ai_projection_identity_sha256": ai_projection.ai_projection_identity_sha256,
        }
    )
    packet_without_digest = CurrentSuppliedCohortResearchPacketV4(
        **core, packet_identity_sha256=packet_identity, packet_object_sha256="0" * 64
    )
    packet_raw_without_digest = _canonical(
        _object_value(packet_without_digest, omit="packet_object_sha256")
    )
    packet = CurrentSuppliedCohortResearchPacketV4(
        **core,
        packet_identity_sha256=packet_identity,
        packet_object_sha256=_sha(packet_raw_without_digest),
    )
    return packet


class CurrentResearchPacketArchivePortV4(Protocol):
    def archive_exact(
        self,
        request: CurrentSuppliedCohortResearchPacketRequestV4,
        candidate: _CurrentSuppliedCohortResearchPacketCandidateV4,
        lease: StorageRootLease,
        *,
        trusted_clock: _TrustedPacketClockV4 | None = None,
    ) -> (
        RetainedCurrentSuppliedCohortResearchPacketV4
        | CurrentResearchPacketArchiveFailureV4
    ): ...


_ArchiveMemberIdentity: TypeAlias = tuple[int, int, int, int, int, int, int, int]


def _archive_member_identity(info: os.stat_result) -> _ArchiveMemberIdentity:
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _private_regular(info: os.stat_result, size: int) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == 0o600
        and info.st_nlink == 1
        and info.st_size == size
    )


def _read_stable(
    parent: int, name: str, maximum: int
) -> tuple[bytes, _ArchiveMemberIdentity] | None:
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
            not 1 <= opened_before.st_size <= maximum
            or not _private_regular(opened_before, opened_before.st_size)
            or not _same_metadata(named_before, opened_before)
        ):
            raise ValueError("unsafe archive object")
        raw = b""
        while len(raw) < opened_before.st_size:
            chunk = os.read(descriptor, opened_before.st_size - len(raw))
            if not chunk:
                raise ValueError("short archive object")
            raw += chunk
        named_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        opened_after = os.fstat(descriptor)
        if (
            not _same_metadata(named_before, named_after)
            or not _same_metadata(opened_before, opened_after)
            or not _same_metadata(opened_after, named_after)
            or not _private_regular(named_after, len(raw))
        ):
            raise ValueError("archive object changed")
        return raw, _archive_member_identity(named_after)
    finally:
        os.close(descriptor)


def _parse_archive_instant(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("archive instant required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not _utc(result) or _instant(result) != value:
        raise ValueError("archive instant invalid")
    return result


def _parse_packet_archive_records(
    packet: CurrentSuppliedCohortResearchPacketV4,
    receipt_raw: bytes,
    marker_raw: bytes,
    decision_cutoff: datetime,
) -> tuple[CurrentResearchPacketReceiptV4, CurrentResearchPacketCompletionMarkerV4]:
    """Parse the immutable persisted commit records without normalizing bytes."""
    receipt_value = json.loads(receipt_raw)
    marker_value = json.loads(marker_raw)
    receipt_fields = {item.name for item in fields(CurrentResearchPacketReceiptV4)}
    marker_fields = {
        item.name for item in fields(CurrentResearchPacketCompletionMarkerV4)
    }
    if (
        type(receipt_value) is not dict
        or type(marker_value) is not dict
        or set(receipt_value) != receipt_fields
        or set(marker_value) != marker_fields
        or _canonical(receipt_value) != receipt_raw
        or _canonical(marker_value) != marker_raw
    ):
        raise ValueError("noncanonical packet archive records")
    receipt_time = _parse_archive_instant(receipt_value["archive_known_at"])
    marker_time = _parse_archive_instant(marker_value["archive_known_at"])
    receipt = CurrentResearchPacketReceiptV4(
        contract_version=receipt_value["contract_version"],
        packet_identity_sha256=receipt_value["packet_identity_sha256"],
        packet_object_sha256=receipt_value["packet_object_sha256"],
        packet_byte_count=receipt_value["packet_byte_count"],
        packet_filename=receipt_value["packet_filename"],
        archive_known_at=receipt_time,
        receipt_identity_sha256=receipt_value["receipt_identity_sha256"],
    )
    marker = CurrentResearchPacketCompletionMarkerV4(
        contract_version=marker_value["contract_version"],
        packet_identity_sha256=marker_value["packet_identity_sha256"],
        packet_object_sha256=marker_value["packet_object_sha256"],
        receipt_identity_sha256=marker_value["receipt_identity_sha256"],
        receipt_sha256=marker_value["receipt_sha256"],
        archive_known_at=marker_time,
        completion_marker_identity_sha256=marker_value[
            "completion_marker_identity_sha256"
        ],
    )
    receipt_core = {
        "contract_version": receipt.contract_version,
        "packet_identity_sha256": receipt.packet_identity_sha256,
        "packet_object_sha256": receipt.packet_object_sha256,
        "packet_byte_count": receipt.packet_byte_count,
        "packet_filename": receipt.packet_filename,
        "archive_known_at": receipt.archive_known_at,
    }
    marker_core = {
        "contract_version": marker.contract_version,
        "packet_identity_sha256": marker.packet_identity_sha256,
        "packet_object_sha256": marker.packet_object_sha256,
        "receipt_identity_sha256": marker.receipt_identity_sha256,
        "receipt_sha256": marker.receipt_sha256,
        "archive_known_at": marker.archive_known_at,
    }
    packet_raw = packet.canonical_json_bytes()
    if (
        receipt.contract_version != _RECEIPT_CONTRACT
        or marker.contract_version != _MARKER_CONTRACT
        or type(receipt.packet_byte_count) is not int
        or receipt.packet_identity_sha256 != packet.packet_identity_sha256
        or receipt.packet_object_sha256 != packet.packet_object_sha256
        or receipt.packet_byte_count != len(packet_raw)
        or receipt.packet_filename != f"packet-{packet.packet_identity_sha256}.json"
        or receipt.archive_known_at > decision_cutoff
        or receipt.receipt_identity_sha256 != _identity(receipt_core)
        or marker.packet_identity_sha256 != packet.packet_identity_sha256
        or marker.packet_object_sha256 != packet.packet_object_sha256
        or marker.receipt_identity_sha256 != receipt.receipt_identity_sha256
        or marker.receipt_sha256 != _sha(receipt_raw)
        or marker.archive_known_at != receipt.archive_known_at
        or marker.completion_marker_identity_sha256 != _identity(marker_core)
        or not all(
            _digest(item)
            for item in (
                receipt.packet_identity_sha256,
                receipt.packet_object_sha256,
                receipt.receipt_identity_sha256,
                marker.packet_identity_sha256,
                marker.packet_object_sha256,
                marker.receipt_identity_sha256,
                marker.receipt_sha256,
                marker.completion_marker_identity_sha256,
            )
        )
    ):
        raise ValueError("spliced packet archive records")
    return receipt, marker


def _publish(parent: int, name: str, raw: bytes, maximum: int) -> bool:
    if not 1 <= len(raw) <= maximum:
        raise ValueError("archive bounds")
    if _read_stable(parent, name, maximum) is not None:
        if _read_stable(parent, name, maximum)[0] != raw:  # type: ignore[index]
            raise ValueError("immutable archive name collision")
        return False
    temporary = f".{name}.pending"
    descriptor: int | None = None
    created = True
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
                raise OSError("archive write failed")
            offset += written
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
            existing = _read_stable(parent, name, maximum)
            if existing is None or existing[0] != raw:
                raise
            created = False
        os.unlink(temporary, dir_fd=parent)
        os.fsync(parent)
        existing = _read_stable(parent, name, maximum)
        if existing is None or existing[0] != raw:
            raise ValueError("archive publication changed")
        return created
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=parent)


def _open_archive(root: int) -> int:
    root_info = os.fstat(root)
    if (
        not stat.S_ISDIR(root_info.st_mode)
        or root_info.st_uid != os.geteuid()
        or stat.S_IMODE(root_info.st_mode) & 0o077
    ):
        raise ValueError("unsafe archive root")
    with suppress(FileExistsError):
        os.mkdir(_ARCHIVE_DIRECTORY, 0o700, dir_fd=root)
    directory = os.open(
        _ARCHIVE_DIRECTORY,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=root,
    )
    named = os.stat(_ARCHIVE_DIRECTORY, dir_fd=root, follow_symlinks=False)
    opened = os.fstat(directory)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or stat.S_IMODE(opened.st_mode) != 0o700
        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
    ):
        os.close(directory)
        raise ValueError("unsafe archive directory")
    os.fsync(root)
    return directory


def _archive_directory_bound(root: int, directory: int) -> bool:
    try:
        named = os.stat(_ARCHIVE_DIRECTORY, dir_fd=root, follow_symlinks=False)
        opened = os.fstat(directory)
    except OSError:
        return False
    return (
        stat.S_ISDIR(named.st_mode)
        and stat.S_ISDIR(opened.st_mode)
        and named.st_uid == os.geteuid()
        and opened.st_uid == os.geteuid()
        and stat.S_IMODE(named.st_mode) == stat.S_IMODE(opened.st_mode) == 0o700
        and (named.st_dev, named.st_ino) == (opened.st_dev, opened.st_ino)
    )


def _packet_archive_guard_bytes(
    phase: Literal["PENDING", "ADMISSIBLE"],
    *,
    packet_identity: str,
    receipt_identity: str,
    marker_raw: bytes,
    archive_known_at: datetime,
) -> bytes:
    return _canonical(
        {
            "contract_version": "current-research-packet-archive-guard@v1",
            "phase": phase,
            "packet_identity_sha256": packet_identity,
            "receipt_identity_sha256": receipt_identity,
            "completion_marker_sha256": _sha(marker_raw),
            "archive_known_at": archive_known_at,
        }
    )


def _failure(
    request: CurrentSuppliedCohortResearchPacketRequestV4, packet_identity: str | None
) -> CurrentResearchPacketArchiveFailureV4:
    core = {
        "contract_version": _FAILURE_CONTRACT,
        "evidence_state": "ARCHIVE_FAILED",
        "reason": "RESEARCH_PACKET_ARCHIVE_FAILED",
        "request_identity_sha256": request.request_identity_sha256,
        "packet_identity_sha256": packet_identity,
    }
    return CurrentResearchPacketArchiveFailureV4(
        **core, archive_failure_identity_sha256=_identity(core)
    )


class _TrustedPacketClockV4(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class _SystemPacketClockV4:
    def now(self) -> datetime:
        return datetime.now(UTC)


class _FileCurrentResearchPacketArchiveV4:
    def __init__(
        self, root: object, *, clock: _TrustedPacketClockV4 | None = None
    ) -> None:
        if type(root) is not type(Path()):
            raise TypeError("invalid packet archive root")
        self._root = root
        self._clock = clock or _SystemPacketClockV4()

    def archive_exact(  # noqa: C901 - archive commit/verification sequence is atomic.
        self,
        request: CurrentSuppliedCohortResearchPacketRequestV4,
        candidate: _CurrentSuppliedCohortResearchPacketCandidateV4,
        lease: StorageRootLease,
        *,
        trusted_clock: _TrustedPacketClockV4 | None = None,
    ) -> (
        RetainedCurrentSuppliedCohortResearchPacketV4
        | CurrentResearchPacketArchiveFailureV4
    ):
        archive_clock = trusted_clock or self._clock

        def retained_packet(
            packet: CurrentSuppliedCohortResearchPacketV4,
            receipt: CurrentResearchPacketReceiptV4,
            marker: CurrentResearchPacketCompletionMarkerV4,
        ) -> RetainedCurrentSuppliedCohortResearchPacketV4:
            core = {
                "evidence_state": "RETAINED",
                "packet": packet,
                "receipt_identity_sha256": receipt.receipt_identity_sha256,
                "completion_marker_identity_sha256": marker.completion_marker_identity_sha256,
                "archive_known_at": receipt.archive_known_at,
            }
            result = object.__new__(RetainedCurrentSuppliedCohortResearchPacketV4)
            for name, value in {
                **core,
                "retained_identity_sha256": _identity(core),
            }.items():
                object.__setattr__(result, name, value)
            if len(result.canonical_json_bytes()) > _RETAINED_LIMIT:
                raise ValueError("retained packet bounds")
            return result

        if (
            type(request) is not CurrentSuppliedCohortResearchPacketRequestV4
            or type(candidate) is not _CurrentSuppliedCohortResearchPacketCandidateV4
            or type(lease) is not StorageRootLease
        ):
            raise TypeError("invalid packet archive invocation")
        if not cast(Any, _candidate_is_exact)(request, candidate):
            raise ValueError("invalid packet candidate")
        packet = candidate.packet
        packet_raw = candidate.canonical_json_bytes()
        if not 1 <= len(packet_raw) <= _PACKET_LIMIT:
            raise ValueError("invalid packet bytes")
        identity = packet.packet_identity_sha256
        packet_name = f"packet-{identity}.json"
        receipt_name = f"retained-{identity}.json"
        marker_name = f"completion-{identity}.json"
        pending_name = f"pending-{identity}.json"
        admissible_name = f"admissible-{identity}.json"
        packet_object = packet.packet_object_sha256
        try:
            with _ARCHIVE_LOCK, lease.root_operation(self._root) as operation:
                directory = _open_archive(operation.descriptor)
                if not _archive_directory_bound(operation.descriptor, directory):
                    os.close(directory)
                    raise ValueError("archive root binding changed")
                created_receipt: tuple[bytes, _ArchiveMemberIdentity] | None = None
                try:
                    _publish(directory, packet_name, packet_raw, _PACKET_LIMIT)
                    if (_read_stable(directory, packet_name, _PACKET_LIMIT) or (None,))[
                        0
                    ] != packet_raw:
                        raise ValueError("packet stable read")
                    receipt_raw = _read_stable(directory, receipt_name, _RECEIPT_LIMIT)
                    if receipt_raw is None:
                        archive_known_at = archive_clock.now() + timedelta(seconds=30)
                        if archive_known_at > request.decision_cutoff:
                            raise ValueError("archive deadline exceeded")
                        receipt_core = {
                            "contract_version": _RECEIPT_CONTRACT,
                            "packet_identity_sha256": identity,
                            "packet_object_sha256": packet_object,
                            "packet_byte_count": len(packet_raw),
                            "packet_filename": packet_name,
                            "archive_known_at": archive_known_at,
                        }
                        receipt = CurrentResearchPacketReceiptV4(
                            **receipt_core,
                            receipt_identity_sha256=_identity(receipt_core),
                        )
                        _publish(
                            directory,
                            receipt_name,
                            receipt.canonical_json_bytes(),
                            _RECEIPT_LIMIT,
                        )
                        created_receipt = _read_stable(
                            directory, receipt_name, _RECEIPT_LIMIT
                        )
                        if (
                            created_receipt is None
                            or created_receipt[0] != receipt.canonical_json_bytes()
                        ):
                            raise ValueError("receipt publication failed")
                    receipt_entry = _read_stable(
                        directory, receipt_name, _RECEIPT_LIMIT
                    )
                    marker_entry = _read_stable(directory, marker_name, _MARKER_LIMIT)
                    if (
                        receipt_entry is None
                        or _read_stable(directory, packet_name, _PACKET_LIMIT) is None
                    ):
                        raise ValueError("incomplete packet archive")
                    if not _archive_directory_bound(operation.descriptor, directory):
                        raise ValueError("archive receipt root binding changed")
                    receipt_value = json.loads(receipt_entry[0])
                    if marker_entry is None:
                        if created_receipt is None:
                            raise ValueError("incomplete packet archive")
                        if (
                            not isinstance(receipt_value, dict)
                            or _canonical(receipt_value) != receipt_entry[0]
                        ):
                            raise ValueError("invalid packet receipt")
                        archive_known_at = datetime.fromisoformat(
                            str(receipt_value.get("archive_known_at")).replace(
                                "Z", "+00:00"
                            )
                        )
                        receipt_core = {
                            "contract_version": receipt_value.get("contract_version"),
                            "packet_identity_sha256": receipt_value.get(
                                "packet_identity_sha256"
                            ),
                            "packet_object_sha256": receipt_value.get(
                                "packet_object_sha256"
                            ),
                            "packet_byte_count": receipt_value.get("packet_byte_count"),
                            "packet_filename": receipt_value.get("packet_filename"),
                            "archive_known_at": archive_known_at,
                        }
                        if (
                            set(receipt_value)
                            != {*receipt_core, "receipt_identity_sha256"}
                            or receipt_core["contract_version"] != _RECEIPT_CONTRACT
                            or receipt_core["packet_identity_sha256"] != identity
                            or receipt_core["packet_object_sha256"] != packet_object
                            or receipt_core["packet_byte_count"] != len(packet_raw)
                            or receipt_core["packet_filename"] != packet_name
                            or receipt_value.get("receipt_identity_sha256")
                            != _identity(receipt_core)
                            or not _utc(archive_known_at)
                            or archive_known_at > request.decision_cutoff
                            or archive_clock.now() > archive_known_at
                        ):
                            raise ValueError("invalid packet receipt")
                        operation.ensure_live()
                        if not _archive_directory_bound(
                            operation.descriptor, directory
                        ):
                            raise ValueError("archive marker root binding changed")
                        marker_core = {
                            "contract_version": _MARKER_CONTRACT,
                            "packet_identity_sha256": identity,
                            "packet_object_sha256": packet_object,
                            "receipt_identity_sha256": receipt_value[
                                "receipt_identity_sha256"
                            ],
                            "receipt_sha256": _sha(receipt_entry[0]),
                            "archive_known_at": archive_known_at,
                        }
                        marker = CurrentResearchPacketCompletionMarkerV4(
                            **marker_core,
                            completion_marker_identity_sha256=_identity(marker_core),
                        )
                        marker_raw = marker.canonical_json_bytes()
                        pending_raw = _packet_archive_guard_bytes(
                            "PENDING",
                            packet_identity=identity,
                            receipt_identity=receipt_value["receipt_identity_sha256"],
                            marker_raw=marker_raw,
                            archive_known_at=archive_known_at,
                        )
                        admissible_raw = _packet_archive_guard_bytes(
                            "ADMISSIBLE",
                            packet_identity=identity,
                            receipt_identity=receipt_value["receipt_identity_sha256"],
                            marker_raw=marker_raw,
                            archive_known_at=archive_known_at,
                        )
                        _publish(
                            directory,
                            pending_name,
                            pending_raw,
                            _MARKER_LIMIT,
                        )
                        os.fsync(directory)
                        created_marker = _publish(
                            directory,
                            marker_name,
                            marker_raw,
                            _MARKER_LIMIT,
                        )
                        os.fsync(directory)
                        marker_entry = _read_stable(
                            directory, marker_name, _MARKER_LIMIT
                        )
                        if marker_entry is None or marker_entry[0] != marker_raw:
                            raise ValueError("marker publication failed")
                        operation.ensure_live()
                        trusted_now = archive_clock.now()
                        if (
                            not _utc(trusted_now)
                            or trusted_now > archive_known_at
                            or not _archive_directory_bound(
                                operation.descriptor, directory
                            )
                        ):
                            if created_marker:
                                stable_marker = _read_stable(
                                    directory, marker_name, _MARKER_LIMIT
                                )
                                if stable_marker == marker_entry:
                                    os.unlink(marker_name, dir_fd=directory)
                                    os.fsync(directory)
                            raise ValueError("late marker publication")
                        _publish(
                            directory,
                            admissible_name,
                            admissible_raw,
                            _MARKER_LIMIT,
                        )
                        os.fsync(directory)
                    marker_value = json.loads(marker_entry[0])
                    if (
                        not isinstance(receipt_value, dict)
                        or not isinstance(marker_value, dict)
                        or _canonical(receipt_value) != receipt_entry[0]
                        or _canonical(marker_value) != marker_entry[0]
                    ):
                        raise ValueError("invalid packet archive records")
                    receipt_core = {
                        "contract_version": receipt_value.get("contract_version"),
                        "packet_identity_sha256": receipt_value.get(
                            "packet_identity_sha256"
                        ),
                        "packet_object_sha256": receipt_value.get(
                            "packet_object_sha256"
                        ),
                        "packet_byte_count": receipt_value.get("packet_byte_count"),
                        "packet_filename": receipt_value.get("packet_filename"),
                        "archive_known_at": receipt_value.get("archive_known_at"),
                    }
                    marker_core = {
                        "contract_version": marker_value.get("contract_version"),
                        "packet_identity_sha256": marker_value.get(
                            "packet_identity_sha256"
                        ),
                        "packet_object_sha256": marker_value.get(
                            "packet_object_sha256"
                        ),
                        "receipt_identity_sha256": marker_value.get(
                            "receipt_identity_sha256"
                        ),
                        "receipt_sha256": marker_value.get("receipt_sha256"),
                        "archive_known_at": marker_value.get("archive_known_at"),
                    }
                    if (
                        set(receipt_value) != {*receipt_core, "receipt_identity_sha256"}
                        or set(marker_value)
                        != {*marker_core, "completion_marker_identity_sha256"}
                        or receipt_value.get("contract_version") != _RECEIPT_CONTRACT
                        or marker_value.get("contract_version") != _MARKER_CONTRACT
                        or receipt_value.get("packet_identity_sha256") != identity
                        or receipt_value.get("packet_object_sha256") != packet_object
                        or receipt_value.get("packet_byte_count") != len(packet_raw)
                        or receipt_value.get("packet_filename") != packet_name
                        or receipt_value.get("receipt_identity_sha256")
                        != _identity(receipt_core)
                        or marker_value.get("packet_identity_sha256") != identity
                        or marker_value.get("packet_object_sha256") != packet_object
                        or marker_value.get("receipt_identity_sha256")
                        != receipt_value.get("receipt_identity_sha256")
                        or marker_value.get("receipt_sha256") != _sha(receipt_entry[0])
                        or marker_value.get("archive_known_at")
                        != receipt_value.get("archive_known_at")
                        or marker_value.get("completion_marker_identity_sha256")
                        != _identity(marker_core)
                    ):
                        raise ValueError("spliced packet archive")
                    archive_known_at = datetime.fromisoformat(
                        str(receipt_value["archive_known_at"]).replace("Z", "+00:00")
                    )
                    if (
                        not _utc(archive_known_at)
                        or archive_known_at > request.decision_cutoff
                    ):
                        raise ValueError("invalid archive time")
                    pending_guard = _read_stable(directory, pending_name, _MARKER_LIMIT)
                    admissible_guard = _read_stable(
                        directory, admissible_name, _MARKER_LIMIT
                    )
                    expected_pending_guard = _packet_archive_guard_bytes(
                        "PENDING",
                        packet_identity=identity,
                        receipt_identity=receipt_value["receipt_identity_sha256"],
                        marker_raw=marker_entry[0],
                        archive_known_at=archive_known_at,
                    )
                    expected_admissible_guard = _packet_archive_guard_bytes(
                        "ADMISSIBLE",
                        packet_identity=identity,
                        receipt_identity=receipt_value["receipt_identity_sha256"],
                        marker_raw=marker_entry[0],
                        archive_known_at=archive_known_at,
                    )
                    guard_pair = (
                        None if pending_guard is None else pending_guard[0],
                        None if admissible_guard is None else admissible_guard[0],
                    )
                    if guard_pair not in (
                        (None, None),
                        (expected_pending_guard, expected_admissible_guard),
                    ):
                        raise ValueError("inadmissible packet completion marker")
                    operation.ensure_live()
                    if not _archive_directory_bound(operation.descriptor, directory):
                        raise ValueError("archive root binding changed")
                    while archive_clock.now() < archive_known_at:
                        time.sleep(0.001)
                    operation.ensure_live()
                    receipt = CurrentResearchPacketReceiptV4(
                        contract_version=receipt_value["contract_version"],
                        packet_identity_sha256=receipt_value["packet_identity_sha256"],
                        packet_object_sha256=receipt_value["packet_object_sha256"],
                        packet_byte_count=receipt_value["packet_byte_count"],
                        packet_filename=receipt_value["packet_filename"],
                        archive_known_at=archive_known_at,
                        receipt_identity_sha256=receipt_value[
                            "receipt_identity_sha256"
                        ],
                    )
                    final_packet = _read_stable(directory, packet_name, _PACKET_LIMIT)
                    final_receipt = _read_stable(
                        directory, receipt_name, _RECEIPT_LIMIT
                    )
                    final_marker = _read_stable(directory, marker_name, _MARKER_LIMIT)
                    final_pending = _read_stable(directory, pending_name, _MARKER_LIMIT)
                    final_admissible = _read_stable(
                        directory, admissible_name, _MARKER_LIMIT
                    )
                    if (
                        final_packet is None
                        or final_receipt is None
                        or final_marker is None
                        or final_packet[0] != packet_raw
                        or final_receipt[0] != receipt_entry[0]
                        or final_marker[0] != marker_entry[0]
                        or not _archive_directory_bound(operation.descriptor, directory)
                        or (
                            pending_guard is not None
                            and (
                                final_pending is None
                                or final_pending[0] != expected_pending_guard
                                or final_admissible is None
                                or final_admissible[0] != expected_admissible_guard
                            )
                        )
                    ):
                        raise ValueError("final archive binding")
                    receipt, marker = _parse_packet_archive_records(
                        packet,
                        receipt_entry[0],
                        marker_entry[0],
                        request.decision_cutoff,
                    )
                    return retained_packet(packet, receipt, marker)
                except (OSError, RuntimeError, TypeError, ValueError, KeyError):
                    raise
                finally:
                    os.close(directory)
        except (OSError, RuntimeError, TypeError, ValueError, KeyError):
            return _failure(request, identity)


def _build_and_retain_current_supplied_cohort_research_packet_unsealed_v4(
    request: CurrentSuppliedCohortResearchPacketRequestV4,
    market_context: RetainedCurrentSamePassMarketContextV4,
    industry_participation: CurrentIndustryParticipationReportV4
    | CurrentIndustryParticipationFailureV4,
    event_notices: RetainedCurrentEventNoticeSnapshotV1 | CurrentEventNoticeFailureV1,
    archive: CurrentResearchPacketArchivePortV4,
    lease: StorageRootLease,
) -> (
    RetainedCurrentSuppliedCohortResearchPacketV4
    | CurrentResearchPacketArchiveFailureV4
):
    if (
        type(request) is not CurrentSuppliedCohortResearchPacketRequestV4
        or type(lease) is not StorageRootLease
        or not callable(getattr(archive, "archive_exact", None))
    ):
        raise TypeError("invalid packet builder invocation")
    (
        context_type,
        industry_report_type,
        industry_failure_type,
        event_retained_type,
        event_failure_type,
    ) = _successor_types()
    if (
        type(market_context) is not context_type
        or type(industry_participation)
        not in {industry_report_type, industry_failure_type}
        or type(event_notices) not in {event_retained_type, event_failure_type}
    ):
        raise TypeError("invalid Plan27 packet component")
    if not _validated_context(market_context):
        raise ValueError("invalid retained same-pass market context")
    raise AssertionError("Packet V4 candidates are minted only by the closure")


def _sealed_packet_boundary() -> tuple[object, object, object, object]:  # noqa: C901
    """Create one closure-owned candidate and archive-seal authority for Packet V4."""
    minted_seals: set[object] = set()

    @dataclass(frozen=True, slots=True)
    class _CandidateBinding:
        candidate: _CurrentSuppliedCohortResearchPacketCandidateV4

    @dataclass(frozen=True, slots=True)
    class _PacketBinding:
        candidate_seal: object
        candidate: _CurrentSuppliedCohortResearchPacketCandidateV4
        retained_object_id: int
        trusted_clock: _TrustedPacketClockV4
        root: Path
        root_identity: tuple[int, int]
        archive_directory: str
        packet_name: str
        receipt_name: str
        marker_name: str
        packet_filesystem_identity: _ArchiveMemberIdentity
        receipt_filesystem_identity: _ArchiveMemberIdentity
        marker_filesystem_identity: _ArchiveMemberIdentity
        packet_bytes: bytes
        receipt_bytes: bytes
        marker_bytes: bytes
        packet_sha256: str
        receipt_sha256: str
        marker_sha256: str
        receipt_identity: str
        marker_identity: str
        archive_known_at: datetime
        retained_identity: str

    candidate_bindings: dict[object, _CandidateBinding] = {}
    packet_bindings: dict[object, _PacketBinding] = {}

    @dataclass(frozen=True, slots=True, init=False, repr=False, eq=False)
    class CandidateSeal:
        def __init__(self, *_: object, **__: object) -> None:
            raise TypeError("research packet candidate seals are closure-minted only")

    @dataclass(frozen=True, slots=True, init=False, repr=False, eq=False)
    class PacketSeal:
        def __init__(self, *_: object, **__: object) -> None:
            raise TypeError("research packet archive seals are closure-minted only")

    def minted(seal: object) -> bool:
        return any(item is seal for item in minted_seals)

    def mint_candidate(
        request: CurrentSuppliedCohortResearchPacketRequestV4,
        packet: CurrentSuppliedCohortResearchPacketV4,
        market_context: RetainedCurrentSamePassMarketContextV4,
        industry_participation: (
            CurrentIndustryParticipationReportV4 | CurrentIndustryParticipationFailureV4
        ),
        event_notices: RetainedCurrentEventNoticeSnapshotV1
        | CurrentEventNoticeFailureV1,
    ) -> _CurrentSuppliedCohortResearchPacketCandidateV4:
        if not _packet_is_exact(
            request, packet, market_context, industry_participation, event_notices
        ):
            raise ValueError("packet candidate upstream replay failed")
        result = object.__new__(_CurrentSuppliedCohortResearchPacketCandidateV4)
        local_seal = object.__new__(CandidateSeal)
        minted_seals.add(local_seal)
        candidate_bindings[local_seal] = _CandidateBinding(result)
        for name, value in {
            "packet": packet,
            "candidate_identity_sha256": _identity(
                {
                    "packet_identity_sha256": packet.packet_identity_sha256,
                    "packet_object_sha256": packet.packet_object_sha256,
                }
            ),
            "market_context": market_context,
            "industry_participation": industry_participation,
            "event_notices": event_notices,
            "_seal": local_seal,
        }.items():
            object.__setattr__(result, name, value)
        return result

    def candidate_is_exact(
        request: CurrentSuppliedCohortResearchPacketRequestV4, candidate: object
    ) -> bool:
        seal = getattr(candidate, "_seal", None)
        binding = candidate_bindings.get(seal)
        return (
            type(candidate) is _CurrentSuppliedCohortResearchPacketCandidateV4
            and type(seal) is CandidateSeal
            and minted(seal)
            and binding is not None
            and binding.candidate is candidate
            and _candidate_structure_is_exact(request, candidate)
        )

    def lease_is_live_for_root(lease: StorageRootLease, root: Path) -> bool:
        try:
            with lease.read_operation(root) as operation:
                operation.ensure_live()
        except (RuntimeError, TypeError, ValueError):
            return False
        return True

    def _persisted_packet_binding(
        candidate: _CurrentSuppliedCohortResearchPacketCandidateV4,
        lease: StorageRootLease,
        root: Path,
    ) -> (
        tuple[
            tuple[int, int],
            str,
            str,
            str,
            str,
            _ArchiveMemberIdentity,
            _ArchiveMemberIdentity,
            _ArchiveMemberIdentity,
            bytes,
            bytes,
            bytes,
        ]
        | None
    ):
        packet = candidate.packet
        packet_raw = candidate.canonical_json_bytes()
        identity = packet.packet_identity_sha256
        directory_name = ".current-research-packet-v4"
        packet_name = f"packet-{identity}.json"
        receipt_name = f"retained-{identity}.json"
        marker_name = f"completion-{identity}.json"
        try:
            with lease.read_operation(root) as operation:
                operation.ensure_live()
                root_info = os.fstat(operation.descriptor)
                directory = os.open(
                    directory_name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=operation.descriptor,
                )
                try:
                    if not _archive_directory_bound(operation.descriptor, directory):
                        return None
                    persisted_packet = _read_stable(
                        directory, packet_name, _PACKET_LIMIT
                    )
                    persisted_receipt = _read_stable(
                        directory, receipt_name, _RECEIPT_LIMIT
                    )
                    persisted_marker = _read_stable(
                        directory, marker_name, _MARKER_LIMIT
                    )
                    operation.ensure_live()
                    if (
                        persisted_packet is None
                        or persisted_receipt is None
                        or persisted_marker is None
                        or persisted_packet[0] != packet_raw
                    ):
                        return None
                    return (
                        (root_info.st_dev, root_info.st_ino),
                        directory_name,
                        packet_name,
                        receipt_name,
                        marker_name,
                        persisted_packet[1],
                        persisted_receipt[1],
                        persisted_marker[1],
                        persisted_packet[0],
                        persisted_receipt[0],
                        persisted_marker[0],
                    )
                finally:
                    os.close(directory)
        except (OSError, RuntimeError, TypeError, ValueError):
            return None

    def mint_retained(
        request: CurrentSuppliedCohortResearchPacketRequestV4,
        candidate: _CurrentSuppliedCohortResearchPacketCandidateV4,
        value: RetainedCurrentSuppliedCohortResearchPacketV4,
        lease: StorageRootLease,
        root: Path,
        trusted_clock: _TrustedPacketClockV4,
    ) -> (
        RetainedCurrentSuppliedCohortResearchPacketV4
        | CurrentResearchPacketArchiveFailureV4
    ):
        persisted = _persisted_packet_binding(candidate, lease, root)
        if not candidate_is_exact(request, candidate) or persisted is None:
            return _failure(request, candidate.packet.packet_identity_sha256)
        (
            root_identity,
            archive_directory,
            packet_name,
            receipt_name,
            marker_name,
            packet_filesystem_identity,
            receipt_filesystem_identity,
            marker_filesystem_identity,
            packet_bytes,
            receipt_bytes,
            marker_bytes,
        ) = persisted
        try:
            receipt, marker = _parse_packet_archive_records(
                candidate.packet,
                receipt_bytes,
                marker_bytes,
                request.decision_cutoff,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return _failure(request, candidate.packet.packet_identity_sha256)
        trusted_now = trusted_clock.now()
        if (
            not _utc(trusted_now)
            or receipt.archive_known_at > request.decision_cutoff
            or receipt.archive_known_at > trusted_now
        ):
            return _failure(request, candidate.packet.packet_identity_sha256)
        core = {
            "evidence_state": "RETAINED",
            "packet": candidate.packet,
            "receipt_identity_sha256": receipt.receipt_identity_sha256,
            "completion_marker_identity_sha256": marker.completion_marker_identity_sha256,
            "archive_known_at": receipt.archive_known_at,
        }
        retained_identity = _identity(core)
        if (
            type(value) is not RetainedCurrentSuppliedCohortResearchPacketV4
            or value.evidence_state != "RETAINED"
            or value.packet != candidate.packet
            or value.packet.canonical_json_bytes()
            != candidate.packet.canonical_json_bytes()
            or value.receipt_identity_sha256 != receipt.receipt_identity_sha256
            or value.completion_marker_identity_sha256
            != marker.completion_marker_identity_sha256
            or value.archive_known_at != receipt.archive_known_at
            or value.retained_identity_sha256 != retained_identity
        ):
            return _failure(request, candidate.packet.packet_identity_sha256)
        result = object.__new__(RetainedCurrentSuppliedCohortResearchPacketV4)
        local_seal = object.__new__(PacketSeal)
        minted_seals.add(local_seal)
        packet_bindings[local_seal] = _PacketBinding(
            candidate._seal,
            candidate,
            id(result),
            trusted_clock,
            root,
            root_identity,
            archive_directory,
            packet_name,
            receipt_name,
            marker_name,
            packet_filesystem_identity,
            receipt_filesystem_identity,
            marker_filesystem_identity,
            packet_bytes,
            receipt_bytes,
            marker_bytes,
            _sha(packet_bytes),
            _sha(receipt_bytes),
            _sha(marker_bytes),
            receipt.receipt_identity_sha256,
            marker.completion_marker_identity_sha256,
            receipt.archive_known_at,
            retained_identity,
        )
        for name, item in {
            **core,
            "retained_identity_sha256": retained_identity,
            "_archive_seal": local_seal,
        }.items():
            object.__setattr__(result, name, item)
        return result

    def validate(
        value: object,
        request: CurrentSuppliedCohortResearchPacketRequestV4,
        current_candidate: object,
        lease: StorageRootLease,
    ) -> bool:
        if type(value) is not RetainedCurrentSuppliedCohortResearchPacketV4:
            return False
        seal = value._archive_seal
        binding = packet_bindings.get(seal)
        if (
            type(seal) is not PacketSeal
            or not minted(seal)
            or binding is None
            or binding.retained_object_id != id(value)
            or not candidate_is_exact(request, current_candidate)
            or binding.candidate is not current_candidate
            or binding.candidate_seal is not current_candidate._seal
            or not lease_is_live_for_root(lease, binding.root)
        ):
            return False
        candidate = candidate_bindings[binding.candidate_seal].candidate
        if (
            not _packet_is_exact(
                request,
                value.packet,
                candidate.market_context,
                candidate.industry_participation,
                candidate.event_notices,
            )
            or value.packet != candidate.packet
            or value.packet.canonical_json_bytes()
            != candidate.packet.canonical_json_bytes()
        ):
            return False
        core = {
            "evidence_state": "RETAINED",
            "packet": value.packet,
            "receipt_identity_sha256": binding.receipt_identity,
            "completion_marker_identity_sha256": binding.marker_identity,
            "archive_known_at": value.archive_known_at,
        }
        return (
            value.evidence_state == "RETAINED"
            and value.receipt_identity_sha256 == binding.receipt_identity
            and value.completion_marker_identity_sha256 == binding.marker_identity
            and value.retained_identity_sha256 == binding.retained_identity
            and value.retained_identity_sha256 == _identity(core)
            and value.archive_known_at == binding.archive_known_at
        )

    def adopt(
        request: CurrentSuppliedCohortResearchPacketRequestV4,
        value: object,
        current_candidate: object,
        lease: StorageRootLease,
        trusted_clock: _TrustedPacketClockV4,
    ) -> bool:
        """Re-open the sealed logical commit under the caller's current lease."""
        if not validate(value, request, current_candidate, lease):
            return False
        binding = packet_bindings.get(value._archive_seal)
        if (
            binding is None
            or binding.candidate is not current_candidate
            or binding.trusted_clock is not trusted_clock
        ):
            return False
        try:
            with lease.read_operation(binding.root) as operation:
                operation.ensure_live()
                root_info = os.fstat(operation.descriptor)
                if (root_info.st_dev, root_info.st_ino) != binding.root_identity:
                    return False
                directory = os.open(
                    binding.archive_directory,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=operation.descriptor,
                )
                try:
                    if not _archive_directory_bound(operation.descriptor, directory):
                        return False
                    packet = _read_stable(directory, binding.packet_name, _PACKET_LIMIT)
                    receipt = _read_stable(
                        directory, binding.receipt_name, _RECEIPT_LIMIT
                    )
                    marker = _read_stable(directory, binding.marker_name, _MARKER_LIMIT)
                    operation.ensure_live()
                    if (
                        packet is None
                        or receipt is None
                        or marker is None
                        or packet[1] != binding.packet_filesystem_identity
                        or receipt[1] != binding.receipt_filesystem_identity
                        or marker[1] != binding.marker_filesystem_identity
                    ):
                        return False
                    receipt_record, marker_record = _parse_packet_archive_records(
                        binding.candidate.packet,
                        receipt[0],
                        marker[0],
                        request.decision_cutoff,
                    )
                    trusted_now = trusted_clock.now()
                    if (
                        not _utc(trusted_now)
                        or receipt_record.archive_known_at != binding.archive_known_at
                        or marker_record.archive_known_at != binding.archive_known_at
                        or binding.archive_known_at > trusted_now
                    ):
                        return False
                    return (
                        packet[0] == binding.packet_bytes
                        and receipt[0] == binding.receipt_bytes
                        and marker[0] == binding.marker_bytes
                        and _sha(packet[0]) == binding.packet_sha256
                        and _sha(receipt[0]) == binding.receipt_sha256
                        and _sha(marker[0]) == binding.marker_sha256
                    )
                finally:
                    os.close(directory)
        except (OSError, RuntimeError, TypeError, ValueError):
            return False

    file_archives: WeakKeyDictionary[object, _FileCurrentResearchPacketArchiveV4] = (
        WeakKeyDictionary()
    )

    class FileArchive:
        """Closure-sealed facade over the create-only descriptor archive."""

        __slots__ = ("__weakref__",)

        def __init__(
            self, root: object, *, clock: _TrustedPacketClockV4 | None = None
        ) -> None:
            file_archives[self] = _FileCurrentResearchPacketArchiveV4(root, clock=clock)

        def archive_exact(
            self,
            request: CurrentSuppliedCohortResearchPacketRequestV4,
            candidate: _CurrentSuppliedCohortResearchPacketCandidateV4,
            lease: StorageRootLease,
            *,
            trusted_clock: _TrustedPacketClockV4 | None = None,
        ) -> (
            RetainedCurrentSuppliedCohortResearchPacketV4
            | CurrentResearchPacketArchiveFailureV4
        ):
            inner = file_archives.get(self) if type(self) is FileArchive else None
            if inner is None:
                return _failure(request, candidate.packet.packet_identity_sha256)
            archive_clock = trusted_clock or inner._clock
            value = inner.archive_exact(
                request,
                candidate,
                lease,
                trusted_clock=archive_clock,
            )
            if type(value) is CurrentResearchPacketArchiveFailureV4:
                return value
            return mint_retained(
                request,
                candidate,
                value,
                lease,
                inner._root,
                archive_clock,
            )

    def build(
        request: CurrentSuppliedCohortResearchPacketRequestV4,
        market_context: RetainedCurrentSamePassMarketContextV4,
        industry_participation: CurrentIndustryParticipationReportV4
        | CurrentIndustryParticipationFailureV4,
        event_notices: RetainedCurrentEventNoticeSnapshotV1
        | CurrentEventNoticeFailureV1,
        archive: CurrentResearchPacketArchivePortV4,
        lease: StorageRootLease,
        *,
        trusted_clock: _TrustedPacketClockV4 | None = None,
    ) -> (
        RetainedCurrentSuppliedCohortResearchPacketV4
        | CurrentResearchPacketArchiveFailureV4
    ):
        if (
            type(request) is not CurrentSuppliedCohortResearchPacketRequestV4
            or type(lease) is not StorageRootLease
            or not callable(getattr(archive, "archive_exact", None))
        ):
            raise TypeError("invalid packet builder invocation")
        (
            context_type,
            industry_report_type,
            industry_failure_type,
            event_retained_type,
            event_failure_type,
        ) = _successor_types()
        if (
            type(market_context) is not context_type
            or type(industry_participation)
            not in {industry_report_type, industry_failure_type}
            or type(event_notices) not in {event_retained_type, event_failure_type}
        ):
            raise TypeError("invalid Plan27 packet component")
        if not _validated_context(market_context):
            raise ValueError("invalid retained same-pass market context")
        archive_clock = trusted_clock or _SystemPacketClockV4()
        with _PACKET_BUILD_LOCK:
            packet = _project_packet(
                request, market_context, industry_participation, event_notices
            )
            candidate = mint_candidate(
                request,
                packet,
                market_context,
                industry_participation,
                event_notices,
            )
            result = archive.archive_exact(
                request,
                candidate,
                lease,
                trusted_clock=archive_clock,
            )
            if type(result) is CurrentResearchPacketArchiveFailureV4:
                if (
                    result.contract_version != _FAILURE_CONTRACT
                    or result.evidence_state != "ARCHIVE_FAILED"
                    or result.reason != "RESEARCH_PACKET_ARCHIVE_FAILED"
                    or result.request_identity_sha256 != request.request_identity_sha256
                    or result.packet_identity_sha256
                    != candidate.packet.packet_identity_sha256
                    or result.archive_failure_identity_sha256
                    != _identity(
                        _object_value(result, omit="archive_failure_identity_sha256")
                    )
                ):
                    raise ValueError("invalid packet archive failure")
                return result
            if type(result) is not RetainedCurrentSuppliedCohortResearchPacketV4:
                raise ValueError("invalid retained packet archive result")
            if not adopt(
                request,
                result,
                candidate,
                lease,
                archive_clock,
            ):
                raise ValueError("invalid retained packet archive result")
            return result

    return FileArchive, build, candidate_is_exact, validate


(
    FileCurrentResearchPacketArchiveV4,
    build_and_retain_current_supplied_cohort_research_packet_v4,
    _candidate_is_exact,
    _validate_retained_packet,
) = _sealed_packet_boundary()
