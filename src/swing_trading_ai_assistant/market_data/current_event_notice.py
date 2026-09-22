"""Owner-private current supplied-cohort NSE event notices V1."""

from __future__ import annotations

import csv
import hashlib
import importlib
import io
import json
import os
import re
import stat
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Final, Literal, TypeAlias, TypeGuard, cast
from urllib.parse import urlsplit

from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
    same_metadata,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

CONTRACT_VERSION: Final = "current-supplied-cohort-event-notice@v1"
CURRENT_EVENT_NOTICE_LICENCE_POLICY_IDENTITY_V1: Final = (
    "nse-bounded-official-fetch-owner-private-v1"
)
LEGACY_EVENT_NOTICE_LICENCE_POLICY_IDENTITY_V1: Final = (
    "nse-manual-download-owner-private-v1"
)
CURRENT_EVENT_NOTICE_ACQUISITION_METHOD_V1: Final = "BOUNDED_OFFICIAL_FETCH"
LEGACY_EVENT_NOTICE_ACQUISITION_METHOD_V1: Final = "OPERATOR_ACQUIRED"
_SOURCE_URL: Final = "https://www.nseindia.com/companies-listing/corporate-filings-announcements?tabIndex=equity"
_LICENCE_POLICY_IDENTITIES: Final = (
    LEGACY_EVENT_NOTICE_LICENCE_POLICY_IDENTITY_V1,
    CURRENT_EVENT_NOTICE_LICENCE_POLICY_IDENTITY_V1,
)
_HEADER: Final = (
    "SYMBOL",
    "COMPANY NAME",
    "SUBJECT",
    "DETAILS",
    "BROADCAST DATE/TIME",
    "RECEIPT",
    "DISSEMINATION",
    "DIFFERENCE",
    "ATTACHMENT",
)
_MAX_ARTIFACT_BYTES: Final = 4_194_304
_MAX_ROWS: Final = 10_000
_MAX_FIELD_CHARS: Final = 32_768
_MAX_ARCHIVE_SNAPSHOT_BYTES: Final = 33_554_432
_MAX_ARCHIVE_RECEIPT_BYTES: Final = 16_384
_MAX_ARCHIVE_MARKER_BYTES: Final = 4_096
_ARCHIVE_PROTOCOL_VERSION: Final = "current-event-notice-archive@v1"
_RECEIPT_VERSION: Final = "retained-current-event-notice-receipt@v1"
_MARKER_VERSION: Final = "retained-current-event-notice-complete@v1"
_IST: Final = timezone(timedelta(hours=5, minutes=30))
_NSE_SYMBOL: Final = re.compile(r"[A-Z0-9](?:[A-Z0-9.&_-]{0,30}[A-Z0-9])?\Z")
_ISIN: Final = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]\Z")
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_LEGACY_FILENAME: Final = re.compile(r"CF-AN-equities-(\d{2}-[A-Za-z]{3}-\d{4})\.csv\Z")
_RANGE_FILENAME: Final = re.compile(
    r"CF-AN-equities-(\d{2}-\d{2}-\d{4})-to-(\d{2}-\d{2}-\d{4})\.csv\Z"
)
_EVENT_TIME: Final = re.compile(r"\d{2}-[A-Z][a-z]{2}-\d{4} \d{2}:\d{2}:\d{2}\Z")
_RECEIPT_TIME: Final = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\Z")
_DIFFERENCE: Final = re.compile(r"\d{2}:\d{2}:\d{2}\Z")
_ARCHIVE_DIRECTORY: Final = ".current-event-notice-v1"
_MANIFEST_MODULE: Final = "swing_trading_ai_assistant.market_data.current_event_notice_runtime_identity_manifest"
_MANIFEST_PATH: Final = "src/swing_trading_ai_assistant/market_data/current_event_notice_runtime_identity_manifest.py"
_RUNTIME_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/current_event_notice.py",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
    "src/swing_trading_ai_assistant/market_data/storage_root_lease.py",
)
_REASON_ORDER: Final = (
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
FailureEvidenceState: TypeAlias = Literal[
    "MALFORMED_EVIDENCE",
    "UNSUPPORTED_CAPABILITY",
    "INSUFFICIENT_EVIDENCE",
    "CONFLICTED_EVIDENCE",
]

_FAILURE_STATE: Final[dict[str, FailureEvidenceState]] = {
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
_ARCHIVE_LOCK: Final = Lock()
_EVENT_NOTICE_RUNTIME_IDENTITY: str | None = None


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


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


_SCHEMA_BINDING: Final = {
    "contract_version": CONTRACT_VERSION,
    "header": list(_HEADER),
    "source": {
        "url": _SOURCE_URL,
        "segment": "Equity",
        "window": "1D",
        "filename_grammars": [
            _LEGACY_FILENAME.pattern,
            _RANGE_FILENAME.pattern,
        ],
        "licence_policy_identities": list(_LICENCE_POLICY_IDENTITIES),
        "exact_source_cases": [
            {
                "acquisition_method": LEGACY_EVENT_NOTICE_ACQUISITION_METHOD_V1,
                "licence_policy_identity": (
                    LEGACY_EVENT_NOTICE_LICENCE_POLICY_IDENTITY_V1
                ),
                "filename_grammar": _LEGACY_FILENAME.pattern,
                "encoding": "UTF-8",
                "bom_states": ["PRESENT"],
                "use": "LEGACY_REPLAY_ONLY",
            },
            {
                "acquisition_method": CURRENT_EVENT_NOTICE_ACQUISITION_METHOD_V1,
                "licence_policy_identity": (
                    CURRENT_EVENT_NOTICE_LICENCE_POLICY_IDENTITY_V1
                ),
                "filename_grammar": _RANGE_FILENAME.pattern,
                "encoding": "UTF-8",
                "bom_states": ["ABSENT", "PRESENT"],
                "use": "CURRENT_LIVE",
            },
        ],
        "row_date_window": {
            "range_end_is_source_date": True,
            "range_start_is_previous_calendar_date": True,
            "legacy_source_filename_date": True,
            "prior_calendar_days": 1,
        },
    },
    "csv": {
        "encoding": "UTF-8",
        "bom_states": ["ABSENT", "PRESENT"],
        "decode_after_optional_bom": True,
        "string_io_newline": "",
        "reader_strict": True,
        "decoded_header_exact": list(_HEADER),
    },
    "bounds": {
        "artifact_bytes": [1, _MAX_ARTIFACT_BYTES],
        "rows": [1, _MAX_ROWS],
        "fields": 9,
        "field_code_points": [1, _MAX_FIELD_CHARS],
        "archive_snapshot_bytes": _MAX_ARCHIVE_SNAPSHOT_BYTES,
        "archive_receipt_bytes": _MAX_ARCHIVE_RECEIPT_BYTES,
        "archive_marker_bytes": _MAX_ARCHIVE_MARKER_BYTES,
    },
    "grammars": {
        "symbol": _NSE_SYMBOL.pattern,
        "isin": _ISIN.pattern,
        "attachment_prefix": "https://nsearchives.nseindia.com/corporate/",
        "attachment_absent_sentinel": "-",
        "workflow_time": _EVENT_TIME.pattern,
        "receipt_time": _RECEIPT_TIME.pattern,
        "difference": _DIFFERENCE.pattern,
        "english_months": (
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ),
        "month_mapping": {
            "Jan": 1,
            "Feb": 2,
            "Mar": 3,
            "Apr": 4,
            "May": 5,
            "Jun": 6,
            "Jul": 7,
            "Aug": 8,
            "Sep": 9,
            "Oct": 10,
            "Nov": 11,
            "Dec": 12,
        },
        "calendar_component_validation": {
            "workflow": "Gregorian-date-hour-minute-second",
            "receipt": "Gregorian-date-hour-minute-second",
        },
        "difference_hour_range": [0, 99],
        "difference_minute_range": [0, 59],
        "difference_second_range": [0, 59],
    },
    "text_policy": {
        "unicode": "no-Cc-Cf-Zl-Zp",
        "formula_prefixes": ["=", "+", "-", "@"],
        "canonicalization": "json-sort-keys-utf8-newline",
    },
    "correction": {
        "normalization": "NFKC-casefold-maximal-ascii-alnum",
        "subject_tokens": sorted(
            (
                "clarification",
                "correction",
                "withdrawal",
                "cancellation",
                "supersession",
            )
        ),
        "details_phrases": [
            "correction to our earlier announcement",
            "clarification to our earlier announcement",
            "withdrawal of our earlier announcement",
            "cancellation of our earlier announcement",
            "supersedes our earlier announcement",
            "correction to our previous disclosure",
            "clarification to our previous disclosure",
        ],
    },
    "archive": {
        "protocol": _ARCHIVE_PROTOCOL_VERSION,
        "receipt_version": _RECEIPT_VERSION,
        "marker_version": _MARKER_VERSION,
        "publication": "create-only-0600-no-follow-stable-binding-fsync",
        "known_at_ownership": "archive-trusted-utc-at-first-publication",
        "current_request_admission": (
            "original-known-at-and-current-trusted-utc-must-map-to-"
            "source-filename-ist-date"
        ),
        "current_request_date_failures": {
            "before": "EVENT_SOURCE_DATE_FUTURE",
            "after": "EVENT_SOURCE_DATE_STALE",
        },
    },
}
EVENT_NOTICE_SCHEMA_IDENTITY_SHA256: Final = _identity(_SCHEMA_BINDING)
LEGACY_EVENT_NOTICE_SCHEMA_IDENTITY_SHA256: Final = (
    "b5c87ca73362cfb3b17fdfd16565ca5de3a7fac7d82749f87107e303c2f3d841"
)
_EVENT_NOTICE_SCHEMA_IDENTITIES: Final = frozenset(
    {
        LEGACY_EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
        EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
    }
)
_DELIVERED_EVENT_NOTICE_RUNTIME_IDENTITY_V1: Final = (
    "09c3b50461c3f02a4f61b0b2ecab9493016d7d7ee96d8ed996f6a6f02068632f"
)


def _ordered(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(reason for reason in _REASON_ORDER if reason in reasons)


def _failure(
    reason: str, cohort_size: int | None = None
) -> CurrentEventNoticeFailureV1:
    return CurrentEventNoticeFailureV1(
        _FAILURE_STATE[reason], _ordered((reason,)), cohort_size
    )


def _valid_digest(value: object) -> TypeGuard[str]:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _string_object_mapping(value: object) -> TypeGuard[dict[str, object]]:
    if type(value) is not dict:
        return False
    mapping = cast(dict[object, object], value)
    return all(type(key) is str for key in mapping)


def _is_isin(value: object) -> bool:
    if type(value) is not str or _ISIN.fullmatch(value) is None:
        return False
    converted = (
        "".join(
            str(ord(character) - 55) if character.isalpha() else character
            for character in value[:-1]
        )
        + value[-1]
    )
    total = 0
    for position, character in enumerate(reversed(converted)):
        number = int(character) * (2 if position % 2 else 1)
        total += number if number < 10 else number - 9
    return total % 10 == 0


def _safe_text(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= _MAX_FIELD_CHARS
        and not value.startswith(("=", "+", "-", "@"))
        and not any(
            unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
            for character in value
        )
    )


_MONTHS: Final = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def _event_datetime(value: str) -> datetime | None:
    if _EVENT_TIME.fullmatch(value) is None:
        return None
    day = int(value[0:2])
    month = _MONTHS.get(value[3:6])
    year = int(value[7:11])
    hour = int(value[12:14])
    minute = int(value[15:17])
    second = int(value[18:20])
    if month is None:
        return None
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def _receipt_datetime(value: str) -> datetime | None:
    if _RECEIPT_TIME.fullmatch(value) is None:
        return None
    try:
        return datetime(
            int(value[0:4]),
            int(value[5:7]),
            int(value[8:10]),
            int(value[11:13]),
            int(value[14:16]),
            int(value[17:19]),
        )
    except ValueError:
        return None


def _parse_filename_range(value: object) -> tuple[date, date] | None:
    if type(value) is not str:
        return None
    legacy = _LEGACY_FILENAME.fullmatch(value)
    if legacy is not None:
        parsed = _event_datetime(f"{legacy.group(1)} 00:00:00")
        return None if parsed is None else (parsed.date(), parsed.date())
    current = _RANGE_FILENAME.fullmatch(value)
    if current is None:
        return None
    try:
        range_from = datetime.strptime(current.group(1), "%d-%m-%Y").date()
        range_to = datetime.strptime(current.group(2), "%d-%m-%Y").date()
    except ValueError:
        return None
    if range_to - range_from != timedelta(days=1):
        return None
    return range_from, range_to


def _parse_filename(value: object) -> date | None:
    parsed = _parse_filename_range(value)
    return None if parsed is None else parsed[1]


def _source_date(value: str, receipt: bool = False) -> date | None:
    parsed = _receipt_datetime(value) if receipt else _event_datetime(value)
    return None if parsed is None else parsed.date()


def _valid_difference(value: str) -> bool:
    if _DIFFERENCE.fullmatch(value) is None:
        return False
    return int(value[0:2]) <= 99 and int(value[3:5]) <= 59 and int(value[6:8]) <= 59


_CORRECTION_SUBJECT_TOKENS: Final = frozenset(
    {"clarification", "correction", "withdrawal", "cancellation", "supersession"}
)
_CORRECTION_PHRASES: Final = (
    ("correction", "to", "our", "earlier", "announcement"),
    ("clarification", "to", "our", "earlier", "announcement"),
    ("withdrawal", "of", "our", "earlier", "announcement"),
    ("cancellation", "of", "our", "earlier", "announcement"),
    ("supersedes", "our", "earlier", "announcement"),
    ("correction", "to", "our", "previous", "disclosure"),
    ("clarification", "to", "our", "previous", "disclosure"),
)


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", value).casefold())
    )


def _correction_candidate(subject: str, details: str) -> bool:
    subject_tokens = _tokens(subject)
    if subject_tokens and subject_tokens[0] in _CORRECTION_SUBJECT_TOKENS:
        return True
    tokens = _tokens(details)
    return any(
        tokens[index : index + len(phrase)] == phrase
        for phrase in _CORRECTION_PHRASES
        for index in range(len(tokens))
    )


def _archive_runtime_root() -> Path:
    root = Path(__file__).parent.parent
    if not root.is_absolute() or root.name != "swing_trading_ai_assistant":
        raise ValueError("event runtime identity invalid")
    return root


def _runtime_digest(module: str, path: str) -> str:
    try:
        return runtime_source_sha256(module, _archive_runtime_root(), path)
    except ValueError:
        raise ValueError("event runtime identity invalid") from None


def _runtime_manifest_digests() -> dict[str, str]:
    try:
        manifest = importlib.import_module(_MANIFEST_MODULE)
        mapping: object = manifest.CURRENT_EVENT_NOTICE_RUNTIME_SOURCE_DIGESTS_V1
    except (AttributeError, ImportError):
        raise ValueError("event runtime identity invalid") from None
    if not _string_object_mapping(mapping) or len(mapping) != len(_RUNTIME_SOURCES):
        raise ValueError("event runtime identity invalid")
    digests: dict[str, str] = {}
    for path in _RUNTIME_SOURCES:
        digest = mapping.get(path)
        if not _valid_digest(digest):
            raise ValueError("event runtime identity invalid")
        digests[path] = digest
    return digests


def _verified_runtime_source_digests() -> dict[str, str]:
    digests = _runtime_manifest_digests()
    modules: Final[dict[str, str]] = {
        _RUNTIME_SOURCES[0]: __name__,
        _RUNTIME_SOURCES[1]: (
            "swing_trading_ai_assistant.market_data.runtime_source_verifier"
        ),
        _RUNTIME_SOURCES[2]: (
            "swing_trading_ai_assistant.market_data.storage_root_lease"
        ),
    }
    if any(
        _runtime_digest(modules[path], path) != digests[path]
        for path in _RUNTIME_SOURCES
    ):
        raise ValueError("event runtime identity invalid")
    return digests


def current_event_notice_runtime_code_identity_v1() -> str:
    mapping = _verified_runtime_source_digests()
    manifest_digest = _runtime_digest(_MANIFEST_MODULE, _MANIFEST_PATH)
    return _sha(
        b"".join(
            path.encode() + b"\0" + mapping[path].encode() + b"\0"
            for path in _RUNTIME_SOURCES
        )
        + _MANIFEST_PATH.encode()
        + b"\0"
        + manifest_digest.encode()
        + b"\0"
    )


def _exact_event_source_case_v1(
    schema_identity_sha256: object,
    acquisition_method: object,
    licence_policy_identity: object,
    source_filename: object,
    source_encoding: object,
    source_has_bom: object,
) -> bool:
    if (
        type(schema_identity_sha256) is not str
        or schema_identity_sha256 not in _EVENT_NOTICE_SCHEMA_IDENTITIES
        or type(acquisition_method) is not str
        or type(licence_policy_identity) is not str
        or type(source_filename) is not str
        or type(source_encoding) is not str
        or type(source_has_bom) is not bool
        or source_encoding != "UTF-8"
    ):
        return False
    return (
        schema_identity_sha256 == EVENT_NOTICE_SCHEMA_IDENTITY_SHA256
        and acquisition_method == CURRENT_EVENT_NOTICE_ACQUISITION_METHOD_V1
        and licence_policy_identity == CURRENT_EVENT_NOTICE_LICENCE_POLICY_IDENTITY_V1
        and _RANGE_FILENAME.fullmatch(source_filename) is not None
        and _parse_filename_range(source_filename) is not None
    ) or (
        schema_identity_sha256 == LEGACY_EVENT_NOTICE_SCHEMA_IDENTITY_SHA256
        and acquisition_method == LEGACY_EVENT_NOTICE_ACQUISITION_METHOD_V1
        and licence_policy_identity == LEGACY_EVENT_NOTICE_LICENCE_POLICY_IDENTITY_V1
        and _LEGACY_FILENAME.fullmatch(source_filename) is not None
        and _parse_filename(source_filename) is not None
        and source_has_bom is True
    )


@dataclass(frozen=True, slots=True, init=False, repr=False)
class CurrentEventNoticeInputV1:
    schema_identity_sha256: str
    source_url: str
    source_segment: str
    source_window: str
    source_filename: str
    artifact_identity_sha256: str
    acquisition_method: Literal["BOUNDED_OFFICIAL_FETCH", "OPERATOR_ACQUIRED"]
    licence_policy_identity: str
    source_encoding: Literal["UTF-8"]
    source_has_bom: bool

    def __init__(
        self,
        *,
        schema_identity_sha256: str,
        source_url: str,
        source_segment: str,
        source_window: str,
        source_filename: str,
        artifact_identity_sha256: str,
        acquisition_method: str,
        licence_policy_identity: str,
        source_encoding: str = "UTF-8",
        source_has_bom: bool = True,
    ) -> None:
        if (
            not _valid_digest(schema_identity_sha256)
            or not _valid_digest(artifact_identity_sha256)
            or any(
                type(value) is not str
                for value in (
                    source_url,
                    source_segment,
                    source_window,
                    source_filename,
                    acquisition_method,
                    licence_policy_identity,
                    source_encoding,
                )
            )
            or type(source_has_bom) is not bool
            or not _exact_event_source_case_v1(
                schema_identity_sha256,
                acquisition_method,
                licence_policy_identity,
                source_filename,
                source_encoding,
                source_has_bom,
            )
        ):
            raise ValueError("event notice input invalid")
        for name, value in locals().items():
            if name != "self":
                object.__setattr__(self, name, value)


def event_notice_licence_policy_identity_is_replay_compatible_v1(
    value: object,
) -> TypeGuard[str]:
    """Admit current fetches and retained legacy snapshots without live fallback."""
    return type(value) is str and value in _LICENCE_POLICY_IDENTITIES


def _input_failure(input: CurrentEventNoticeInputV1) -> str | None:
    if not event_notice_licence_policy_identity_is_replay_compatible_v1(
        input.licence_policy_identity
    ):
        return "EVENT_SOURCE_UNAUTHORIZED"
    if (
        input.source_url != _SOURCE_URL
        or input.source_segment != "Equity"
        or input.source_window != "1D"
        or not _exact_event_source_case_v1(
            input.schema_identity_sha256,
            input.acquisition_method,
            input.licence_policy_identity,
            input.source_filename,
            input.source_encoding,
            input.source_has_bom,
        )
    ):
        return "EVENT_SOURCE_MISMATCH"
    return None


@dataclass(frozen=True, slots=True, repr=False)
class CurrentEventCohortMemberV1:
    isin: str
    exchange: str
    listed_equity_segment: str
    symbol: str
    effective_from: date
    effective_through: date
    provider_mapping_revision: str

    def __post_init__(self) -> None:
        if (
            not _is_isin(self.isin)
            or not _safe_text(self.exchange)
            or not _safe_text(self.listed_equity_segment)
            or type(self.symbol) is not str
            or _NSE_SYMBOL.fullmatch(self.symbol) is None
            or type(self.effective_from) is not date
            or type(self.effective_through) is not date
            or self.effective_from > self.effective_through
            or not _safe_text(self.provider_mapping_revision)
        ):
            raise ValueError("event cohort member invalid")


@dataclass(frozen=True, slots=True, init=False, repr=False)
class _PrivateEventNoticeRow:
    ordinal: int
    fields: tuple[str, ...]
    artifact_identity_sha256: str
    observation_identity_sha256: str
    deduplication_identity_sha256: str
    publisher_timezone: None
    event_at: None
    publisher_event_id: None
    publisher_revision_id: None
    correction_of: None

    def __init__(self) -> None:
        raise TypeError("private event row constructor unavailable")

    @property
    def symbol(self) -> str:
        return self.fields[0]

    @property
    def company_name(self) -> str:
        return self.fields[1]

    @property
    def subject(self) -> str:
        return self.fields[2]

    @property
    def details(self) -> str:
        return self.fields[3]

    @property
    def broadcast_at(self) -> str:
        return self.fields[4]

    @property
    def receipt_at(self) -> str:
        return self.fields[5]

    @property
    def dissemination_at(self) -> str:
        return self.fields[6]

    @property
    def difference(self) -> str:
        return self.fields[7]

    @property
    def attachment_url(self) -> str:
        return self.fields[8]


def _row(
    ordinal: int, fields: tuple[str, ...], artifact: str
) -> _PrivateEventNoticeRow:
    value = object.__new__(_PrivateEventNoticeRow)
    deduplication = _identity({"fields": list(fields)})
    values = {
        "ordinal": ordinal,
        "fields": fields,
        "artifact_identity_sha256": artifact,
        "observation_identity_sha256": _identity(
            {
                "artifact_identity_sha256": artifact,
                "ordinal": ordinal,
                "fields": list(fields),
            }
        ),
        "deduplication_identity_sha256": deduplication,
        "publisher_timezone": None,
        "event_at": None,
        "publisher_event_id": None,
        "publisher_revision_id": None,
        "correction_of": None,
    }
    for name, item in values.items():
        object.__setattr__(value, name, item)
    return value


@dataclass(frozen=True, slots=True, init=False, repr=False)
class ParsedCurrentEventNoticeArtifactV1:
    evidence_state: Literal["PARSED"]
    schema_identity_sha256: str
    input: CurrentEventNoticeInputV1
    artifact_identity_sha256: str
    private_rows: tuple[_PrivateEventNoticeRow, ...]

    def __init__(self) -> None:
        raise TypeError("parsed event artifact constructor unavailable")


@dataclass(frozen=True, slots=True)
class CurrentEventNoticeFailureV1:
    evidence_state: Literal[
        "MALFORMED_EVIDENCE",
        "UNSUPPORTED_CAPABILITY",
        "INSUFFICIENT_EVIDENCE",
        "CONFLICTED_EVIDENCE",
    ]
    reasons: tuple[str, ...]
    cohort_size: int | None = None


@dataclass(frozen=True, slots=True, repr=False)
class CurrentEventNoticeV1:
    member: CurrentEventCohortMemberV1
    source_symbol: str
    source_company_name: str
    subject: str
    details: str
    broadcast_at: str
    receipt_at: str
    dissemination_at: str
    difference: str
    attachment_url: str | None
    observation_identity_sha256: str
    deduplication_identity_sha256: str
    publisher_timezone: None = None
    event_at: None = None
    publisher_event_id: None = None
    publisher_revision_id: None = None
    correction_of: None = None

    def value(self) -> dict[str, object]:
        return {
            "affected_identity": {
                "isin": self.member.isin,
                "exchange": self.member.exchange,
                "symbol": self.member.symbol,
                "provider_mapping_revision": self.member.provider_mapping_revision,
            },
            "source_symbol": self.source_symbol,
            "source_company_name": self.source_company_name,
            "subject": self.subject,
            "details": self.details,
            "broadcast_at": self.broadcast_at,
            "receipt_at": self.receipt_at,
            "dissemination_at": self.dissemination_at,
            "difference": self.difference,
            "attachment_url": self.attachment_url,
            "observation_identity_sha256": self.observation_identity_sha256,
            "deduplication_identity_sha256": self.deduplication_identity_sha256,
            "publisher_timezone": None,
            "event_at": None,
            "publisher_event_id": None,
            "publisher_revision_id": None,
            "correction_of": None,
        }


@dataclass(frozen=True, slots=True, repr=False)
class CurrentEventNoticeMemberResultV1:
    member: CurrentEventCohortMemberV1
    outcome: Literal["NOTICES_ADMITTED", "NO_MATCHING_NOTICE_IN_SNAPSHOT"]
    notices: tuple[CurrentEventNoticeV1, ...]

    def value(self) -> dict[str, object]:
        return {
            "member": {
                "isin": self.member.isin,
                "exchange": self.member.exchange,
                "listed_equity_segment": self.member.listed_equity_segment,
                "symbol": self.member.symbol,
                "effective_from": self.member.effective_from.isoformat(),
                "effective_through": self.member.effective_through.isoformat(),
                "provider_mapping_revision": self.member.provider_mapping_revision,
            },
            "outcome": self.outcome,
            "notices": [notice.value() for notice in self.notices],
        }


@dataclass(frozen=True, slots=True, init=False, repr=False)
class PrivateCurrentEventNoticeSnapshotV1:
    evidence_state: Literal["PROJECTED"]
    schema_identity_sha256: str
    artifact_identity_sha256: str
    source_filename: str
    source_url: str
    source_segment: str
    source_window: str
    source_encoding: Literal["UTF-8"]
    source_has_bom: bool
    acquisition_method: Literal["BOUNDED_OFFICIAL_FETCH", "OPERATOR_ACQUIRED"]
    licence_policy_identity: str
    cohort_size: int
    members: tuple[CurrentEventNoticeMemberResultV1, ...]
    snapshot_identity_sha256: str

    def __init__(self) -> None:
        raise TypeError("private event snapshot constructor unavailable")

    def canonical_json_bytes(self) -> bytes:
        return _canonical(_snapshot_value(self))


def _snapshot_value(snapshot: PrivateCurrentEventNoticeSnapshotV1) -> dict[str, object]:
    return {
        "contract_version": CONTRACT_VERSION,
        "schema_identity_sha256": snapshot.schema_identity_sha256,
        "artifact_identity_sha256": snapshot.artifact_identity_sha256,
        "source_url": snapshot.source_url,
        "source_segment": snapshot.source_segment,
        "source_window": snapshot.source_window,
        "source_filename": snapshot.source_filename,
        "source_encoding": snapshot.source_encoding,
        "source_has_bom": snapshot.source_has_bom,
        "acquisition_method": snapshot.acquisition_method,
        "licence_policy_identity": snapshot.licence_policy_identity,
        "cohort_size": snapshot.cohort_size,
        "members": [member.value() for member in snapshot.members],
    }


def _snapshot(**values: object) -> PrivateCurrentEventNoticeSnapshotV1:
    result = object.__new__(PrivateCurrentEventNoticeSnapshotV1)
    for name, value in values.items():
        object.__setattr__(result, name, value)
    return result


def _records(artifact: bytes, source_has_bom: bool) -> list[list[str]]:
    actual_has_bom = artifact.startswith(b"\xef\xbb\xbf")
    if actual_has_bom is not source_has_bom:
        raise ValueError("malformed")
    if not 1 <= len(artifact) <= _MAX_ARTIFACT_BYTES:
        raise OverflowError("bounds")
    try:
        text = artifact[3 if source_has_bom else 0 :].decode("utf-8")
        records = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except (UnicodeDecodeError, csv.Error):
        raise ValueError("malformed") from None
    if not records or tuple(records[0]) != _HEADER:
        raise LookupError("header")
    if len(records) - 1 > _MAX_ROWS:
        raise OverflowError("bounds")
    for record in records[1:]:
        if len(record) != 9:
            raise ValueError("malformed")
        if any(len(field) > _MAX_FIELD_CHARS for field in record):
            raise OverflowError("bounds")
        if any(
            not _safe_text(field)
            for position, field in enumerate(record)
            if not (position == 8 and field == "-")
        ):
            raise ValueError("malformed")
    return records


def _row_dates(fields: tuple[str, ...]) -> tuple[date, date, date]:
    broadcast = _source_date(fields[4])
    receipt = _source_date(fields[5], True)
    dissemination = _source_date(fields[6])
    if broadcast is None or receipt is None or dissemination is None:
        raise RuntimeError("time")
    return broadcast, receipt, dissemination


def _admit_rows(
    records: list[list[str]], artifact_identity: str, filename_date: date
) -> tuple[_PrivateEventNoticeRow, ...]:
    rows: list[_PrivateEventNoticeRow] = []
    for ordinal, record in enumerate(records[1:], 1):
        fields = tuple(record)
        if (
            _NSE_SYMBOL.fullmatch(fields[0]) is None
            or _EVENT_TIME.fullmatch(fields[4]) is None
            or _RECEIPT_TIME.fullmatch(fields[5]) is None
            or _EVENT_TIME.fullmatch(fields[6]) is None
            or not _valid_difference(fields[7])
            or (
                fields[8] != "-"
                and (
                    urlsplit(fields[8]).geturl() != fields[8]
                    or not fields[8].startswith(
                        "https://nsearchives.nseindia.com/corporate/"
                    )
                )
            )
        ):
            raise RuntimeError("time")
        dates = _row_dates(fields)
        if any(value > filename_date for value in dates):
            raise RuntimeError("future")
        if any(value < filename_date - timedelta(days=1) for value in dates):
            raise RuntimeError("stale")
        rows.append(_row(ordinal, fields, artifact_identity))
    return tuple(rows)


def _parse_admitted_rows(
    input: CurrentEventNoticeInputV1, artifact: bytes
) -> tuple[_PrivateEventNoticeRow, ...] | CurrentEventNoticeFailureV1:
    filename_date = _parse_filename(input.source_filename)
    if filename_date is None:
        return _failure("EVENT_SOURCE_MISMATCH")
    try:
        return _admit_rows(
            _records(artifact, input.source_has_bom),
            input.artifact_identity_sha256,
            filename_date,
        )
    except LookupError:
        return _failure("EVENT_HEADER_MISMATCH")
    except OverflowError:
        return _failure("EVENT_BOUNDS_EXCEEDED")
    except RuntimeError as error:
        return _failure(
            {
                "future": "EVENT_SOURCE_DATE_FUTURE",
                "stale": "EVENT_SOURCE_DATE_STALE",
                "time": "EVENT_TIME_MALFORMED",
            }[str(error)]
        )
    except ValueError:
        return _failure("EVENT_ARTIFACT_MALFORMED")


def _parsed_artifact(
    input: CurrentEventNoticeInputV1, rows: tuple[_PrivateEventNoticeRow, ...]
) -> ParsedCurrentEventNoticeArtifactV1:
    result = object.__new__(ParsedCurrentEventNoticeArtifactV1)
    object.__setattr__(result, "evidence_state", "PARSED")
    object.__setattr__(result, "schema_identity_sha256", input.schema_identity_sha256)
    object.__setattr__(result, "input", input)
    object.__setattr__(
        result, "artifact_identity_sha256", input.artifact_identity_sha256
    )
    object.__setattr__(result, "private_rows", rows)
    return result


def parse_current_event_notice_artifact_v1(
    input: CurrentEventNoticeInputV1, artifact: bytes | None
) -> ParsedCurrentEventNoticeArtifactV1 | CurrentEventNoticeFailureV1:
    if type(input) is not CurrentEventNoticeInputV1:
        raise TypeError("event notice input invalid")
    input_failure = _input_failure(input)
    if input_failure is not None:
        return _failure(input_failure)
    if artifact is None:
        return _failure("EVENT_ARTIFACT_MISSING")
    if type(artifact) is not bytes:
        raise TypeError("event artifact invalid")
    if _sha(artifact) != input.artifact_identity_sha256:
        return _failure("EVENT_ARTIFACT_IDENTITY_MISMATCH")
    rows = _parse_admitted_rows(input, artifact)
    if isinstance(rows, CurrentEventNoticeFailureV1):
        return rows
    return _parsed_artifact(input, rows)


def _projection_failure(
    parsed: ParsedCurrentEventNoticeArtifactV1,
    members: tuple[CurrentEventCohortMemberV1, ...],
) -> CurrentEventNoticeFailureV1 | None:
    if not 1 <= len(members) <= 50 or any(
        type(member) is not CurrentEventCohortMemberV1 for member in members
    ):
        raise ValueError("event cohort invalid")
    if any(member.exchange != "NSE" for member in members):
        return _failure("EVENT_EXCHANGE_UNSUPPORTED", len(members))
    if any(
        member.listed_equity_segment != "EQUITY"
        or not _safe_text(member.provider_mapping_revision)
        for member in members
    ):
        return _failure("EVENT_COHORT_INVALID", len(members))
    observation_date = _parse_filename(parsed.input.source_filename)
    if observation_date is None or any(
        not member.effective_from <= observation_date <= member.effective_through
        for member in members
    ):
        return _failure("EVENT_COHORT_INVALID", len(members))
    if len({member.symbol for member in members}) != len(members):
        return _failure("EVENT_SYMBOL_AMBIGUOUS", len(members))
    if len({member.isin for member in members}) != len(members):
        return _failure("EVENT_COHORT_INVALID", len(members))
    return None


def _relevant_row_failure(
    rows: tuple[_PrivateEventNoticeRow, ...], symbols: frozenset[str]
) -> str | None:
    duplicates: set[tuple[str, ...]] = set()
    conflicts: dict[tuple[str, str, str], tuple[str, ...]] = {}
    for row in rows:
        if row.symbol not in symbols:
            continue
        if _correction_candidate(row.subject, row.details):
            return "CORRECTION_LINEAGE_UNAVAILABLE"
        if row.fields in duplicates:
            return "EVENT_DUPLICATE"
        duplicates.add(row.fields)
        key = (row.symbol, row.broadcast_at, row.attachment_url)
        existing = conflicts.get(key)
        if existing is not None and existing != row.fields:
            return "EVENT_CONFLICTED"
        conflicts[key] = row.fields
    return None


def _member_result(
    member: CurrentEventCohortMemberV1,
    rows: tuple[_PrivateEventNoticeRow, ...],
) -> CurrentEventNoticeMemberResultV1:
    notices = tuple(
        CurrentEventNoticeV1(
            member,
            row.symbol,
            row.company_name,
            row.subject,
            row.details,
            row.broadcast_at,
            row.receipt_at,
            row.dissemination_at,
            row.difference,
            None if row.attachment_url == "-" else row.attachment_url,
            row.observation_identity_sha256,
            row.deduplication_identity_sha256,
        )
        for row in rows
        if row.symbol == member.symbol
    )
    return CurrentEventNoticeMemberResultV1(
        member,
        "NOTICES_ADMITTED" if notices else "NO_MATCHING_NOTICE_IN_SNAPSHOT",
        notices,
    )


def _projected_snapshot(
    parsed: ParsedCurrentEventNoticeArtifactV1,
    results: tuple[CurrentEventNoticeMemberResultV1, ...],
) -> PrivateCurrentEventNoticeSnapshotV1:
    base = {
        "contract_version": CONTRACT_VERSION,
        "schema_identity_sha256": parsed.schema_identity_sha256,
        "artifact_identity_sha256": parsed.artifact_identity_sha256,
        "source_url": parsed.input.source_url,
        "source_segment": parsed.input.source_segment,
        "source_window": parsed.input.source_window,
        "source_filename": parsed.input.source_filename,
        "source_encoding": parsed.input.source_encoding,
        "source_has_bom": parsed.input.source_has_bom,
        "acquisition_method": parsed.input.acquisition_method,
        "licence_policy_identity": parsed.input.licence_policy_identity,
        "cohort_size": len(results),
        "members": [result.value() for result in results],
    }
    return _snapshot(
        evidence_state="PROJECTED",
        schema_identity_sha256=parsed.schema_identity_sha256,
        artifact_identity_sha256=parsed.artifact_identity_sha256,
        source_filename=parsed.input.source_filename,
        source_url=parsed.input.source_url,
        source_segment=parsed.input.source_segment,
        source_window=parsed.input.source_window,
        source_encoding=parsed.input.source_encoding,
        source_has_bom=parsed.input.source_has_bom,
        acquisition_method=parsed.input.acquisition_method,
        licence_policy_identity=parsed.input.licence_policy_identity,
        cohort_size=len(results),
        members=results,
        snapshot_identity_sha256=_identity(base),
    )


def project_current_supplied_cohort_event_notices_v1(
    parsed: ParsedCurrentEventNoticeArtifactV1,
    members: tuple[CurrentEventCohortMemberV1, ...],
) -> PrivateCurrentEventNoticeSnapshotV1 | CurrentEventNoticeFailureV1:
    if (
        type(parsed) is not ParsedCurrentEventNoticeArtifactV1
        or type(members) is not tuple
    ):
        raise TypeError("event projection invalid")
    failure = _projection_failure(parsed, members)
    if failure is not None:
        return failure
    relevant_failure = _relevant_row_failure(
        parsed.private_rows, frozenset(member.symbol for member in members)
    )
    if relevant_failure is not None:
        return _failure(relevant_failure, len(members))
    results = tuple(
        _member_result(member, parsed.private_rows)
        for member in sorted(members, key=lambda item: item.isin)
    )
    return _projected_snapshot(parsed, results)


@dataclass(frozen=True, slots=True, repr=False)
class RetainedCurrentEventNoticeSnapshotV1:
    evidence_state: Literal["RETAINED"]
    contract_version: str
    schema_identity_sha256: str
    source_url: str
    nse_attribution: str
    source_segment: str
    source_window: str
    source_filename: str
    source_encoding: Literal["UTF-8"]
    source_has_bom: bool
    acquisition_method: Literal["BOUNDED_OFFICIAL_FETCH", "OPERATOR_ACQUIRED"]
    licence_policy_identity: str
    artifact_identity_sha256: str
    snapshot_identity_sha256: str
    archive_identity_sha256: str
    receipt_identity_sha256: str
    runtime_code_identity_sha256: str
    retained_identity_sha256: str
    cohort_identity_sha256: str
    cohort_size: int
    member_count: int
    known_at: datetime
    members: tuple[CurrentEventNoticeMemberResultV1, ...]


def _trusted_utc_now() -> datetime:
    return datetime.now(UTC)


def _cohort_identity(members: tuple[CurrentEventNoticeMemberResultV1, ...]) -> str:
    return _identity({"members": [member.value()["member"] for member in members]})


def _snapshot_out_of_cohort(
    snapshot: PrivateCurrentEventNoticeSnapshotV1,
) -> str | None:
    if type(snapshot.members) is not tuple:
        return "EVENT_ARCHIVE_FAILED"
    cohort_members = {
        member_result.member
        for member_result in snapshot.members
        if type(member_result) is CurrentEventNoticeMemberResultV1
    }
    for member_result in snapshot.members:
        if type(member_result) is not CurrentEventNoticeMemberResultV1:
            return "EVENT_ARCHIVE_FAILED"
        if member_result.member not in cohort_members:
            return "EVENT_OUT_OF_COHORT"
        if (
            member_result.outcome
            not in {
                "NOTICES_ADMITTED",
                "NO_MATCHING_NOTICE_IN_SNAPSHOT",
            }
            or type(member_result.notices) is not tuple
            or (
                member_result.outcome == "NO_MATCHING_NOTICE_IN_SNAPSHOT"
                and member_result.notices
            )
            or (
                member_result.outcome == "NOTICES_ADMITTED"
                and not member_result.notices
            )
        ):
            return "EVENT_ARCHIVE_FAILED"
        for notice in member_result.notices:
            if (
                type(notice) is not CurrentEventNoticeV1
                or notice.member != member_result.member
                or notice.member not in cohort_members
                or notice.source_symbol != member_result.member.symbol
            ):
                return "EVENT_OUT_OF_COHORT"
    return None


def _validated_snapshot(
    input: CurrentEventNoticeInputV1,
    artifact: bytes,
    snapshot: PrivateCurrentEventNoticeSnapshotV1,
) -> str | None:
    if (
        snapshot.evidence_state != "PROJECTED"
        or snapshot.schema_identity_sha256 != input.schema_identity_sha256
        or snapshot.artifact_identity_sha256 != input.artifact_identity_sha256
        or snapshot.source_filename != input.source_filename
        or snapshot.source_url != input.source_url
        or snapshot.source_segment != input.source_segment
        or snapshot.source_window != input.source_window
        or snapshot.source_encoding != input.source_encoding
        or snapshot.source_has_bom is not input.source_has_bom
        or snapshot.acquisition_method != input.acquisition_method
        or not _exact_event_source_case_v1(
            snapshot.schema_identity_sha256,
            snapshot.acquisition_method,
            snapshot.licence_policy_identity,
            snapshot.source_filename,
            snapshot.source_encoding,
            snapshot.source_has_bom,
        )
        or snapshot.licence_policy_identity != input.licence_policy_identity
        or type(snapshot.cohort_size) is not int
        or snapshot.cohort_size != len(snapshot.members)
        or not 1 <= snapshot.cohort_size <= 50
    ):
        return "EVENT_ARCHIVE_FAILED"
    out_of_cohort = _snapshot_out_of_cohort(snapshot)
    if out_of_cohort is not None:
        return out_of_cohort
    if snapshot.snapshot_identity_sha256 != _identity(_snapshot_value(snapshot)):
        return "EVENT_ARCHIVE_FAILED"
    members = tuple(member_result.member for member_result in snapshot.members)
    parsed = parse_current_event_notice_artifact_v1(input, artifact)
    if isinstance(parsed, CurrentEventNoticeFailureV1):
        return "EVENT_ARCHIVE_FAILED"
    projected = project_current_supplied_cohort_event_notices_v1(parsed, members)
    if isinstance(projected, CurrentEventNoticeFailureV1):
        return "EVENT_ARCHIVE_FAILED"
    if (
        projected.snapshot_identity_sha256 != snapshot.snapshot_identity_sha256
        or projected.canonical_json_bytes() != snapshot.canonical_json_bytes()
    ):
        return "EVENT_ARCHIVE_FAILED"
    return None


def _archive_identity(snapshot: PrivateCurrentEventNoticeSnapshotV1) -> str:
    return _identity(
        {
            "artifact_identity_sha256": snapshot.artifact_identity_sha256,
            "snapshot_identity_sha256": snapshot.snapshot_identity_sha256,
            "contract_version": CONTRACT_VERSION,
            "archive_protocol": _ARCHIVE_PROTOCOL_VERSION,
        }
    )


def _archive_names(
    snapshot: PrivateCurrentEventNoticeSnapshotV1, archive_identity: str
) -> tuple[str, str, str, str]:
    return (
        f"{snapshot.artifact_identity_sha256}.raw.csv",
        f"{snapshot.snapshot_identity_sha256}.snapshot.json",
        f"{archive_identity}.receipt.json",
        f"{archive_identity}.complete.json",
    )


def _private_regular(info: os.stat_result, size: int) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == 0o600
        and info.st_nlink == 1
        and info.st_size == size
    )


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
            or not _private_regular(opened_before, opened_before.st_size)
            or not same_metadata(named_before, opened_before)
        ):
            raise ValueError("unsafe archive object")
        chunks: list[bytes] = []
        remaining = opened_before.st_size
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                raise ValueError("short archive object")
            chunks.append(chunk)
            remaining -= len(chunk)
        opened_after = os.fstat(descriptor)
        named_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        raw = b"".join(chunks)
        if (
            not same_metadata(opened_before, opened_after)
            or not same_metadata(named_before, named_after)
            or not same_metadata(opened_after, named_after)
            or not _private_regular(named_after, len(raw))
        ):
            raise ValueError("changed archive object")
        return raw, named_after
    finally:
        os.close(descriptor)


def _stable_object(parent: int, name: str, raw: bytes) -> os.stat_result | None:
    value = _read_stable_private_object(parent, name, len(raw))
    if value is None or value[0] != raw:
        return None
    return value[1]


def _publish_object(parent: int, name: str, raw: bytes, maximum_size: int) -> bool:
    if len(raw) > maximum_size:
        raise ValueError("archive object bounds")
    existing = _stable_object(parent, name, raw)
    if existing is not None:
        os.fsync(parent)
        return False
    temporary = f".{name}.pending"
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
            if _stable_object(parent, name, raw) is None:
                raise
        os.unlink(temporary, dir_fd=parent)
        os.fsync(parent)
        if _stable_object(parent, name, raw) is None:
            raise ValueError("archive publication changed")
        return True
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=parent)


def _validate_archive_root(root: int) -> None:
    info = os.fstat(root)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise ValueError("unsafe archive root")


def _validate_archive_directory(root: int, directory: int) -> None:
    opened = os.fstat(directory)
    named = os.stat(_ARCHIVE_DIRECTORY, dir_fd=root, follow_symlinks=False)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or stat.S_IMODE(opened.st_mode) != 0o700
        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
    ):
        raise ValueError("unsafe archive directory")


def _open_existing_archive(root: int) -> int:
    """Open an existing private archive without creating evidence directories."""
    _validate_archive_root(root)
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


def _open_archive(root: int) -> int:
    _validate_archive_root(root)
    with suppress(FileExistsError):
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


def _verify_archive_binding(
    operation: object,
    root: int,
    directory: int,
    raw_name: str,
    artifact: bytes,
    snapshot_name: str,
    snapshot_raw: bytes,
) -> None:
    if (
        _stable_object(directory, raw_name, artifact) is None
        or _stable_object(directory, snapshot_name, snapshot_raw) is None
    ):
        raise ValueError("archive binding")
    _validate_archive_directory(root, directory)
    _validate_archive_root(root)
    ensure_live = getattr(operation, "ensure_live", None)
    if not callable(ensure_live):
        raise ValueError("archive operation")
    ensure_live()


def _known_at_text(value: object) -> tuple[str, datetime]:
    if type(value) is not str:
        raise ValueError("receipt known_at")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("receipt known_at") from None
    if parsed.tzinfo is not UTC or parsed.utcoffset() != timedelta(0):
        raise ValueError("receipt known_at")
    known_at = parsed.astimezone(UTC)
    canonical = known_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if canonical != value:
        raise ValueError("receipt known_at")
    return value, known_at


def _receipt_core(
    snapshot: PrivateCurrentEventNoticeSnapshotV1,
    archive_identity: str,
    runtime: str,
    known_text: str,
) -> dict[str, object]:
    return {
        "version": _RECEIPT_VERSION,
        "artifact_identity_sha256": snapshot.artifact_identity_sha256,
        "snapshot_identity_sha256": snapshot.snapshot_identity_sha256,
        "archive_identity_sha256": archive_identity,
        "runtime_code_identity_sha256": runtime,
        "known_at": known_text,
        "acquisition_method": snapshot.acquisition_method,
        "licence_policy_identity": snapshot.licence_policy_identity,
        "source_filename": snapshot.source_filename,
        "source_encoding": snapshot.source_encoding,
        "source_has_bom": snapshot.source_has_bom,
    }


def _retained_core(
    receipt_core: dict[str, object], receipt_identity: str
) -> dict[str, object]:
    return {**receipt_core, "receipt_identity_sha256": receipt_identity}


def _marker_bytes(
    archive_identity: str,
    receipt_identity: str,
    known_text: str,
    retained_identity: str,
) -> bytes:
    return _canonical(
        {
            "version": _MARKER_VERSION,
            "archive_identity_sha256": archive_identity,
            "receipt_identity_sha256": receipt_identity,
            "retained_identity_sha256": retained_identity,
            "known_at": known_text,
        }
    )


def _receipt_value(
    raw: bytes,
    snapshot: PrivateCurrentEventNoticeSnapshotV1,
    archive_identity: str,
    runtime: str,
) -> tuple[datetime, str, str, str]:
    if len(raw) > _MAX_ARCHIVE_RECEIPT_BYTES:
        raise ValueError("receipt bounds")
    try:
        decoded: object = json.loads(raw)
    except (TypeError, ValueError):
        raise ValueError("receipt json") from None
    if not _string_object_mapping(decoded):
        raise ValueError("receipt type")
    receipt = decoded
    expected_keys = {
        "version",
        "artifact_identity_sha256",
        "snapshot_identity_sha256",
        "archive_identity_sha256",
        "runtime_code_identity_sha256",
        "known_at",
        "acquisition_method",
        "licence_policy_identity",
        "source_filename",
        "source_encoding",
        "source_has_bom",
        "receipt_identity_sha256",
        "retained_identity_sha256",
    }
    if set(receipt) != expected_keys or _canonical(receipt) != raw:
        raise ValueError("receipt canonical")
    known_text, known_at = _known_at_text(receipt["known_at"])
    receipt_identity = receipt["receipt_identity_sha256"]
    retained_identity = receipt["retained_identity_sha256"]
    if not _valid_digest(receipt_identity) or not _valid_digest(retained_identity):
        raise ValueError("receipt identity")
    if not _exact_event_source_case_v1(
        snapshot.schema_identity_sha256,
        receipt.get("acquisition_method"),
        receipt.get("licence_policy_identity"),
        receipt.get("source_filename"),
        receipt.get("source_encoding"),
        receipt.get("source_has_bom"),
    ):
        raise ValueError("receipt source binding")
    core = _receipt_core(snapshot, archive_identity, runtime, known_text)
    if (
        any(receipt[key] != value for key, value in core.items())
        or receipt_identity != _identity(core)
        or retained_identity != _identity(_retained_core(core, receipt_identity))
    ):
        raise ValueError("receipt binding")
    return known_at, known_text, receipt_identity, retained_identity


class _CurrentRequestDateFailure(ValueError):
    def __init__(
        self, reason: Literal["EVENT_SOURCE_DATE_FUTURE", "EVENT_SOURCE_DATE_STALE"]
    ) -> None:
        super().__init__(reason)
        self.reason = reason


def _require_source_ist_date(
    snapshot: PrivateCurrentEventNoticeSnapshotV1, observed_at: datetime
) -> None:
    filename_date = _parse_filename(snapshot.source_filename)
    if (
        filename_date is None
        or type(observed_at) is not datetime
        or observed_at.tzinfo is not UTC
        or observed_at.utcoffset() != timedelta(0)
    ):
        raise ValueError("freshness")
    observed_date = observed_at.astimezone(_IST).date()
    if observed_date < filename_date:
        raise _CurrentRequestDateFailure("EVENT_SOURCE_DATE_FUTURE")
    if observed_date > filename_date:
        raise _CurrentRequestDateFailure("EVENT_SOURCE_DATE_STALE")


def _retained_snapshot(
    snapshot: PrivateCurrentEventNoticeSnapshotV1,
    archive_identity: str,
    runtime: str,
    known_at: datetime,
    receipt_identity: str,
    retained_identity: str,
    *,
    snapshot_identity: str | None = None,
) -> RetainedCurrentEventNoticeSnapshotV1:
    return RetainedCurrentEventNoticeSnapshotV1(
        "RETAINED",
        CONTRACT_VERSION,
        snapshot.schema_identity_sha256,
        snapshot.source_url,
        "NSE",
        snapshot.source_segment,
        snapshot.source_window,
        snapshot.source_filename,
        snapshot.source_encoding,
        snapshot.source_has_bom,
        snapshot.acquisition_method,
        snapshot.licence_policy_identity,
        snapshot.artifact_identity_sha256,
        snapshot.snapshot_identity_sha256
        if snapshot_identity is None
        else snapshot_identity,
        archive_identity,
        receipt_identity,
        runtime,
        retained_identity,
        _cohort_identity(snapshot.members),
        snapshot.cohort_size,
        len(snapshot.members),
        known_at,
        snapshot.members,
    )


def _legacy_snapshot_value(
    snapshot: PrivateCurrentEventNoticeSnapshotV1,
) -> dict[str, object]:
    return {
        "contract_version": CONTRACT_VERSION,
        "schema_identity_sha256": LEGACY_EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
        "artifact_identity_sha256": snapshot.artifact_identity_sha256,
        "source_url": snapshot.source_url,
        "source_segment": snapshot.source_segment,
        "source_window": snapshot.source_window,
        "source_filename": snapshot.source_filename,
        "licence_policy_identity": snapshot.licence_policy_identity,
        "cohort_size": snapshot.cohort_size,
        "members": [member.value() for member in snapshot.members],
    }


def _adopt_delivered_legacy_archive(
    root: Path,
    lease: StorageRootLease,
    snapshot: PrivateCurrentEventNoticeSnapshotV1,
    artifact: bytes,
) -> RetainedCurrentEventNoticeSnapshotV1 | None:
    if snapshot.schema_identity_sha256 != LEGACY_EVENT_NOTICE_SCHEMA_IDENTITY_SHA256:
        return None
    if not artifact.startswith(b"\xef\xbb\xbf") or not _exact_event_source_case_v1(
        snapshot.schema_identity_sha256,
        snapshot.acquisition_method,
        snapshot.licence_policy_identity,
        snapshot.source_filename,
        snapshot.source_encoding,
        snapshot.source_has_bom,
    ):
        raise ValueError("legacy event source binding")
    snapshot_raw = _canonical(_legacy_snapshot_value(snapshot))
    snapshot_identity = _sha(snapshot_raw)
    archive_identity = _identity(
        {
            "artifact_identity_sha256": snapshot.artifact_identity_sha256,
            "snapshot_identity_sha256": snapshot_identity,
            "contract_version": CONTRACT_VERSION,
            "archive_protocol": _ARCHIVE_PROTOCOL_VERSION,
        }
    )
    raw_name = f"{snapshot.artifact_identity_sha256}.raw.csv"
    snapshot_name = f"{snapshot_identity}.snapshot.json"
    receipt_name = f"{archive_identity}.receipt.json"
    marker_name = f"{archive_identity}.complete.json"
    with _ARCHIVE_LOCK, lease.root_operation(root) as operation:
        try:
            directory = _open_existing_archive(operation.descriptor)
        except FileNotFoundError:
            return None
        try:
            receipt_entry = _read_stable_private_object(
                directory, receipt_name, _MAX_ARCHIVE_RECEIPT_BYTES
            )
            if receipt_entry is None:
                return None
            _verify_archive_binding(
                operation,
                operation.descriptor,
                directory,
                raw_name,
                artifact,
                snapshot_name,
                snapshot_raw,
            )
            receipt_raw = receipt_entry[0]
            decoded: object = json.loads(receipt_raw)
            expected_keys = {
                "version",
                "artifact_identity_sha256",
                "snapshot_identity_sha256",
                "archive_identity_sha256",
                "runtime_code_identity_sha256",
                "known_at",
                "receipt_identity_sha256",
                "retained_identity_sha256",
            }
            if (
                not _string_object_mapping(decoded)
                or set(decoded) != expected_keys
                or _canonical(decoded) != receipt_raw
            ):
                raise ValueError("legacy event receipt")
            receipt = decoded
            known_text, known_at = _known_at_text(receipt["known_at"])
            core: dict[str, object] = {
                "version": _RECEIPT_VERSION,
                "artifact_identity_sha256": snapshot.artifact_identity_sha256,
                "snapshot_identity_sha256": snapshot_identity,
                "archive_identity_sha256": archive_identity,
                "runtime_code_identity_sha256": (
                    _DELIVERED_EVENT_NOTICE_RUNTIME_IDENTITY_V1
                ),
                "known_at": known_text,
            }
            receipt_identity = receipt["receipt_identity_sha256"]
            retained_identity = receipt["retained_identity_sha256"]
            if (
                not _valid_digest(receipt_identity)
                or not _valid_digest(retained_identity)
                or any(receipt.get(key) != value for key, value in core.items())
                or receipt_identity != _identity(core)
                or retained_identity
                != _identity(_retained_core(core, receipt_identity))
            ):
                raise ValueError("legacy event receipt binding")
            marker = _read_stable_private_object(
                directory, marker_name, _MAX_ARCHIVE_MARKER_BYTES
            )
            if marker is None or marker[0] != _marker_bytes(
                archive_identity,
                receipt_identity,
                known_text,
                retained_identity,
            ):
                raise ValueError("legacy event completion")
            _require_source_ist_date(snapshot, known_at)
            _require_source_ist_date(snapshot, _trusted_utc_now())
            operation.ensure_live()
            os.fsync(directory)
        finally:
            os.close(directory)
    return _retained_snapshot(
        snapshot,
        archive_identity,
        _DELIVERED_EVENT_NOTICE_RUNTIME_IDENTITY_V1,
        known_at,
        receipt_identity,
        retained_identity,
        snapshot_identity=snapshot_identity,
    )


def _archive_snapshot(
    root: Path,
    lease: StorageRootLease,
    snapshot: PrivateCurrentEventNoticeSnapshotV1,
    artifact: bytes,
    runtime: str,
    archive_identity: str,
) -> RetainedCurrentEventNoticeSnapshotV1:
    raw_name, snapshot_name, receipt_name, marker_name = _archive_names(
        snapshot, archive_identity
    )
    snapshot_raw = snapshot.canonical_json_bytes()
    if len(snapshot_raw) > _MAX_ARCHIVE_SNAPSHOT_BYTES:
        raise ValueError("snapshot bounds")
    with _ARCHIVE_LOCK, lease.root_operation(root) as operation:
        directory = _open_archive(operation.descriptor)
        try:
            existing = _read_stable_private_object(
                directory, receipt_name, _MAX_ARCHIVE_RECEIPT_BYTES
            )
            if existing is not None:
                _verify_archive_binding(
                    operation,
                    operation.descriptor,
                    directory,
                    raw_name,
                    artifact,
                    snapshot_name,
                    snapshot_raw,
                )
                receipt_raw, _ = existing
                known_at, known_text, receipt_identity, retained_identity = (
                    _receipt_value(receipt_raw, snapshot, archive_identity, runtime)
                )
                marker = _read_stable_private_object(
                    directory, marker_name, _MAX_ARCHIVE_MARKER_BYTES
                )
                if marker is None or marker[0] != _marker_bytes(
                    archive_identity,
                    receipt_identity,
                    known_text,
                    retained_identity,
                ):
                    raise ValueError("existing completion")
                _require_source_ist_date(snapshot, known_at)
                _require_source_ist_date(snapshot, _trusted_utc_now())
            else:
                _publish_object(directory, raw_name, artifact, _MAX_ARTIFACT_BYTES)
                _publish_object(
                    directory, snapshot_name, snapshot_raw, _MAX_ARCHIVE_SNAPSHOT_BYTES
                )
                _verify_archive_binding(
                    operation,
                    operation.descriptor,
                    directory,
                    raw_name,
                    artifact,
                    snapshot_name,
                    snapshot_raw,
                )
                known_at = _trusted_utc_now()
                _require_source_ist_date(snapshot, known_at)
                known_text = known_at.isoformat(timespec="microseconds").replace(
                    "+00:00", "Z"
                )
                core = _receipt_core(snapshot, archive_identity, runtime, known_text)
                receipt_identity = _identity(core)
                retained_identity = _identity(_retained_core(core, receipt_identity))
                receipt_raw = _canonical(
                    {
                        **core,
                        "receipt_identity_sha256": receipt_identity,
                        "retained_identity_sha256": retained_identity,
                    }
                )
                marker_raw = _marker_bytes(
                    archive_identity, receipt_identity, known_text, retained_identity
                )
                _publish_object(
                    directory, receipt_name, receipt_raw, _MAX_ARCHIVE_RECEIPT_BYTES
                )
                _publish_object(
                    directory, marker_name, marker_raw, _MAX_ARCHIVE_MARKER_BYTES
                )
            _verify_archive_binding(
                operation,
                operation.descriptor,
                directory,
                raw_name,
                artifact,
                snapshot_name,
                snapshot_raw,
            )
            receipt = _read_stable_private_object(
                directory, receipt_name, _MAX_ARCHIVE_RECEIPT_BYTES
            )
            marker = _read_stable_private_object(
                directory, marker_name, _MAX_ARCHIVE_MARKER_BYTES
            )
            if receipt is None or marker is None:
                raise ValueError("incomplete archive")
            known_at, known_text, receipt_identity, retained_identity = _receipt_value(
                receipt[0], snapshot, archive_identity, runtime
            )
            if marker[0] != _marker_bytes(
                archive_identity, receipt_identity, known_text, retained_identity
            ):
                raise ValueError("completion marker")
            _require_source_ist_date(snapshot, known_at)
            os.fsync(directory)
        finally:
            os.close(directory)
    return _retained_snapshot(
        snapshot,
        archive_identity,
        runtime,
        known_at,
        receipt_identity,
        retained_identity,
    )


def _set_runtime_identity(runtime: str) -> None:
    globals()["_EVENT_NOTICE_RUNTIME_IDENTITY"] = runtime


def _verified_runtime(
    cohort_size: int | None,
) -> str | CurrentEventNoticeFailureV1:
    try:
        runtime = current_event_notice_runtime_code_identity_v1()
    except ValueError:
        return _failure("EVENT_RUNTIME_IDENTITY_INVALID", cohort_size)
    if (
        _EVENT_NOTICE_RUNTIME_IDENTITY is not None
        and runtime != _EVENT_NOTICE_RUNTIME_IDENTITY
    ):
        return _failure("EVENT_RUNTIME_IDENTITY_INVALID", cohort_size)
    _set_runtime_identity(runtime)
    return runtime


class FileCurrentEventNoticeArchiveV1:
    def __init__(self, root: object) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("event archive invalid")
        self._root = root

    def archive_exact(
        self,
        input: CurrentEventNoticeInputV1,
        artifact: bytes,
        snapshot: PrivateCurrentEventNoticeSnapshotV1,
        lease: StorageRootLease,
    ) -> RetainedCurrentEventNoticeSnapshotV1 | CurrentEventNoticeFailureV1:
        if (
            type(input) is not CurrentEventNoticeInputV1
            or type(artifact) is not bytes
            or type(snapshot) is not PrivateCurrentEventNoticeSnapshotV1
            or type(lease) is not StorageRootLease
        ):
            raise TypeError("event archive input invalid")
        cohort_size = (
            snapshot.cohort_size if type(snapshot.cohort_size) is int else None
        )
        snapshot_failure = _validated_snapshot(input, artifact, snapshot)
        if snapshot_failure is not None:
            return _failure(snapshot_failure, cohort_size)
        runtime = _verified_runtime(cohort_size)
        if isinstance(runtime, CurrentEventNoticeFailureV1):
            return runtime
        try:
            legacy = _adopt_delivered_legacy_archive(
                self._root,
                lease,
                snapshot,
                artifact,
            )
            if legacy is not None:
                return legacy
            return _archive_snapshot(
                self._root,
                lease,
                snapshot,
                artifact,
                runtime,
                _archive_identity(snapshot),
            )
        except _CurrentRequestDateFailure as error:
            return _failure(error.reason, cohort_size)
        except Exception:
            return _failure("EVENT_ARCHIVE_FAILED", cohort_size)


def validate_retained_current_event_notice_v1(  # noqa: C901
    root: Path,
    lease: StorageRootLease,
    retained: RetainedCurrentEventNoticeSnapshotV1,
    *,
    archive_objects: bool = False,
) -> (
    RetainedCurrentEventNoticeSnapshotV1
    | tuple[RetainedCurrentEventNoticeSnapshotV1, tuple[bytes, bytes, bytes, bytes]]
):
    """Re-read archive objects and re-parse the retained projection exactly."""
    if (
        not root.is_absolute()
        or type(lease) is not StorageRootLease
        or type(retained) is not RetainedCurrentEventNoticeSnapshotV1
        or retained.evidence_state != "RETAINED"
    ):
        raise ValueError("retained event notice invalid")
    raw_name = f"{retained.artifact_identity_sha256}.raw.csv"
    snapshot_name = f"{retained.snapshot_identity_sha256}.snapshot.json"
    receipt_name = f"{retained.archive_identity_sha256}.receipt.json"
    marker_name = f"{retained.archive_identity_sha256}.complete.json"
    with _ARCHIVE_LOCK, lease.root_operation(root) as operation:
        directory = _open_existing_archive(operation.descriptor)
        try:
            raw_entry = _read_stable_private_object(
                directory, raw_name, _MAX_ARTIFACT_BYTES
            )
            snapshot_entry = _read_stable_private_object(
                directory, snapshot_name, _MAX_ARCHIVE_SNAPSHOT_BYTES
            )
            receipt_entry = _read_stable_private_object(
                directory, receipt_name, _MAX_ARCHIVE_RECEIPT_BYTES
            )
            marker_entry = _read_stable_private_object(
                directory, marker_name, _MAX_ARCHIVE_MARKER_BYTES
            )
        finally:
            os.close(directory)
    if any(
        item is None
        for item in (raw_entry, snapshot_entry, receipt_entry, marker_entry)
    ):
        raise ValueError("retained event notice archive incomplete")
    raw = cast(tuple[bytes, os.stat_result], raw_entry)[0]
    snapshot_raw = cast(tuple[bytes, os.stat_result], snapshot_entry)[0]
    receipt_raw = cast(tuple[bytes, os.stat_result], receipt_entry)[0]
    marker_raw = cast(tuple[bytes, os.stat_result], marker_entry)[0]
    event_input = CurrentEventNoticeInputV1(
        schema_identity_sha256=retained.schema_identity_sha256,
        source_url=retained.source_url,
        source_segment=retained.source_segment,
        source_window=retained.source_window,
        source_filename=retained.source_filename,
        artifact_identity_sha256=retained.artifact_identity_sha256,
        acquisition_method=retained.acquisition_method,
        licence_policy_identity=retained.licence_policy_identity,
        source_encoding=retained.source_encoding,
        source_has_bom=retained.source_has_bom,
    )
    parsed = parse_current_event_notice_artifact_v1(event_input, raw)
    if isinstance(parsed, CurrentEventNoticeFailureV1):
        raise ValueError("retained event notice raw artifact invalid")
    projected = project_current_supplied_cohort_event_notices_v1(
        parsed, tuple(item.member for item in retained.members)
    )
    if isinstance(projected, CurrentEventNoticeFailureV1):
        raise ValueError("retained event notice projection invalid")
    if retained.schema_identity_sha256 == LEGACY_EVENT_NOTICE_SCHEMA_IDENTITY_SHA256:
        expected_snapshot = _canonical(_legacy_snapshot_value(projected))
        adopted = _adopt_delivered_legacy_archive(root, lease, projected, raw)
        if adopted != retained:
            raise ValueError("retained legacy event notice invalid")
    else:
        expected_snapshot = projected.canonical_json_bytes()
        if (
            _validated_snapshot(event_input, raw, projected) is not None
            or projected.snapshot_identity_sha256 != retained.snapshot_identity_sha256
            or _archive_identity(projected) != retained.archive_identity_sha256
        ):
            raise ValueError("retained event notice projection invalid")
        known_at, known_text, receipt_identity, retained_identity = _receipt_value(
            receipt_raw,
            projected,
            retained.archive_identity_sha256,
            retained.runtime_code_identity_sha256,
        )
        if (
            known_at != retained.known_at
            or receipt_identity != retained.receipt_identity_sha256
            or retained_identity != retained.retained_identity_sha256
            or marker_raw
            != _marker_bytes(
                retained.archive_identity_sha256,
                receipt_identity,
                known_text,
                retained_identity,
            )
        ):
            raise ValueError("retained event notice receipt invalid")
    if (
        _sha(raw) != retained.artifact_identity_sha256
        or _sha(snapshot_raw) != retained.snapshot_identity_sha256
        or snapshot_raw != expected_snapshot
        or projected.members != retained.members
        or _cohort_identity(projected.members) != retained.cohort_identity_sha256
        or retained.cohort_size != len(retained.members)
        or retained.member_count != len(retained.members)
    ):
        raise ValueError("retained event notice bytes invalid")
    if archive_objects:
        # The caller must compare these V1-validated bytes again inside its
        # own final authorized operation; they never grant archive admission.
        return retained, (raw, snapshot_raw, receipt_raw, marker_raw)
    return retained
