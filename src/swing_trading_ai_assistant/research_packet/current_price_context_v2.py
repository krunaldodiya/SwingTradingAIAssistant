"""One-shot current raw price context with separately labelled provisional facts."""

from __future__ import annotations

import hashlib
import json
import re
from calendar import monthrange
from contextlib import suppress
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.current_raw_acquisition import (
    CurrentRawAcquisitionResultV1,
    acquire_missing_current_raw_evidence_v1,
    inspect_current_raw_evidence_v1,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextClockV1,
    CurrentPriceContextMemberV1,
    CurrentRawCancellationV1,
    CurrentRawInvocationControlV1,
    CurrentRawInvocationStoppedV1,
    CurrentRawPriceContextInputV1,
)
from swing_trading_ai_assistant.market_data.open_month import (
    open_month_schedule_digest,
    open_month_schedule_from_evidence,
)
from swing_trading_ai_assistant.market_data.provisional_store import (
    ProvisionalPartitionUnavailableV1,
    load_provisional_partition,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ScheduleEvidenceStore,
    ScheduleSession,
    exact_nse_schedule_source_release_pair_v1,
    schedule_covers_full_calendar_range,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    RootAuthorityV1,
    StorageRootLease,
    StorageRootLeaseError,
)
from swing_trading_ai_assistant.research_packet.current_price_context import (
    CurrentIndustryArchiveReferenceV1,
    CurrentPriceContextRequestV1,
    CurrentPriceContextResultV1,
    _research_current_price_context_v1,  # pyright: ignore[reportPrivateUsage]
    current_price_context_result_from_canonical_json_bytes_v1,
    current_price_context_runtime_code_identity_v1,
)
from swing_trading_ai_assistant.research_packet.current_price_context_v2_runtime_identity_manifest import (
    CURRENT_PRICE_CONTEXT_RUNTIME_SOURCE_SHA256_V2,
)

_REQUEST_CONTRACT = "current-price-context-request@v2"
_RESULT_CONTRACT = "current-price-context@v2"
_QUESTIONS = (
    "RAW_MARKET_STRUCTURE",
    "RAW_20_SESSION_DIRECTION",
    "RAW_COHORT_BREADTH",
    "RAW_INDUSTRY_PARTICIPATION",
)
_MODES = ("RETAINED_ONLY", "ACQUIRE_MISSING", "REFRESH_ONCE")
_MAX_REQUEST_BYTES = 64 * 1024
_MAX_RESULT_BYTES = 1_048_576
_IST = ZoneInfo("Asia/Kolkata")
_DIGEST_LENGTH = 64
_PRICE_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,18})?")
_PROVISIONAL_REASONS = {
    "NOT_APPLICABLE": frozenset({"CURRENT_SESSION_NOT_APPLICABLE"}),
    "NOT_REQUESTED": frozenset({"NOT_REQUESTED"}),
    "UNAVAILABLE": frozenset(
        {
            "CALENDAR_PREREQUISITE_MISSING",
            "NO_FULLY_COMPLETED_MINUTE",
            "PROVISIONAL_EVIDENCE_UNAVAILABLE",
            "PROVISIONAL_EVIDENCE_STALE",
        }
    ),
    "CONFLICTED": frozenset({"PROVISIONAL_EVIDENCE_CONFLICTED"}),
}
# V1 clears Mapping receipt fields after these downstream failures, but each proves
# that Mapping admission succeeded and therefore binds its shared ledger state.
_MAPPING_ADMITTED_DOWNSTREAM_REASONS = frozenset(
    {
        "RAW_PARTITION_CORRUPT",
        "RAW_BAR_MISSING",
        "RAW_BAR_CONFLICTED",
        "RAW_BAR_INVALID",
        "SCREEN_UNAVAILABLE",
        "ACTION_IN_WINDOW",
    }
)
_LEDGER_SOURCES = frozenset(
    {
        "CALENDAR",
        "MAPPING",
        "CLOSED_MONTH",
        "CURRENT_HISTORY",
        "CURRENT_SESSION",
        "CORPORATE_ACTION",
        "INDUSTRY",
    }
)
_LEDGER_STATES = frozenset(
    {
        "REUSED",
        "ACQUIRED",
        "REFRESHED",
        "APPENDED",
        "CONFLICTED",
        "UNAVAILABLE",
        "NOT_REQUESTED",
    }
)
_CORRECTION_BY_SOURCE = {
    "CALENDAR": "RETAINED_EXACT_CALENDAR",
    "MAPPING": "SELECTION_DATE_MAPPING",
    "CLOSED_MONTH": "IMMUTABLE_CLOSED_MONTH_REUSE",
    "CURRENT_HISTORY": (
        "CURRENT_MONTH_IDENTICAL_OVERLAP_OR_INTRADAY_TO_HISTORICAL_FINALIZATION"
    ),
    "CURRENT_SESSION": "CURRENT_SESSION_IDENTICAL_OVERLAP_APPEND_OR_CONFLICT",
    "CORPORATE_ACTION": "LATEST_RETAINED_ACTION_AT_CUTOFF",
    "INDUSTRY": "RETAINED_ONLY_EXACT_INDUSTRY",
}
_CORRECTION_RULES = frozenset(_CORRECTION_BY_SOURCE.values())
_ABSENT_PLANNING_WITNESS_REASONS = frozenset(
    {
        "CALENDAR_PREREQUISITE_MISSING",
        "CALENDAR_FUTURE_KNOWN",
        "CALENDAR_UNSUPPORTED",
        "COMPLETED_SESSION_WINDOW_UNAVAILABLE",
        "RAW_WINDOW_LIMIT_EXCEEDED",
        "SCHEDULE_AUTHORITY_CHANGED",
    }
)


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def _utc(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def _digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _DIGEST_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _instant(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _wire(value: object) -> object:
    if isinstance(value, datetime):
        return _instant(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _wire(getattr(value, field.name)) for field in fields(value)
        }
    if isinstance(value, tuple):
        return [_wire(item) for item in cast(tuple[object, ...], value)]
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        return {str(key): _wire(item) for key, item in mapping.items()}
    return value


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            _wire(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        + b"\n"
    )


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate field")
        value[key] = item
    return value


def _parse_instant(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if not _utc(parsed) or _instant(parsed) != value:
        raise ValueError
    return parsed


def _parse_date(value: object) -> date:
    if type(value) is not str:
        raise ValueError
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError
    return parsed


def _valid_price_text(value: object) -> bool:
    if type(value) is not str or _PRICE_PATTERN.fullmatch(value) is None:
        return False
    try:
        parsed = Decimal(value)
        return parsed.is_finite() and 0 <= parsed <= Decimal("1000000000000000000")
    except DecimalException:
        return False


def _valid_observed_values(
    last_completed_minute: object,
    observed_price: object,
    cumulative_source_volume: object,
    source_version: object,
    partition_checksum_sha256: object,
    source_cutoff: object,
    published_at: object,
    known_at: object,
) -> bool:
    return (
        _utc(last_completed_minute)
        and _valid_price_text(observed_price)
        and type(cumulative_source_volume) is int
        and cumulative_source_volume >= 0
        and source_version == "upstox-intraday-v3"
        and _digest(partition_checksum_sha256)
        and _utc(source_cutoff)
        and _utc(published_at)
        and _utc(known_at)
        and cast(datetime, last_completed_minute)
        <= cast(datetime, source_cutoff)
        <= cast(datetime, published_at)
        <= cast(datetime, known_at)
    )


def _valid_acquisition_window(
    started_at: object,
    completed_at: object,
    inspection_time: datetime,
    evidence_cutoff: datetime,
) -> bool:
    return (
        _utc(started_at)
        and _utc(completed_at)
        and inspection_time
        <= cast(datetime, started_at)
        <= cast(datetime, completed_at)
        <= evidence_cutoff
    )


def current_price_context_runtime_code_identity_v2() -> str:
    """Fail closed unless every reviewed runtime source byte still matches."""
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in CURRENT_PRICE_CONTEXT_RUNTIME_SOURCE_SHA256_V2.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("current price context V2 runtime identity is invalid")
        observed[relative] = actual
    return _hash(observed)


@dataclass(frozen=True, slots=True)
class CurrentPriceContextRequestV2:
    contract_version: Literal["current-price-context-request@v2"]
    data_selection_time: datetime
    admission_deadline: datetime
    schedule_identity_sha256: str
    members: tuple[CurrentPriceContextMemberV1, ...]
    questions: tuple[str, ...]
    industry_archive_reference: CurrentIndustryArchiveReferenceV1 | None
    execution_mode: Literal["RETAINED_ONLY", "ACQUIRE_MISSING", "REFRESH_ONCE"]
    include_current_session: bool
    request_identity_sha256: str = ""

    def __post_init__(self) -> None:
        if (
            self.contract_version != _REQUEST_CONTRACT
            or not _utc(self.data_selection_time)
            or not _utc(self.admission_deadline)
            or not self.data_selection_time < self.admission_deadline
            or self.admission_deadline - self.data_selection_time
            > timedelta(minutes=30)
            or self.data_selection_time.astimezone(_IST).date()
            != self.admission_deadline.astimezone(_IST).date()
            or not _digest(self.schedule_identity_sha256)
            or type(self.members) is not tuple
            or not 1 <= len(self.members) <= 50
            or any(
                type(item) is not CurrentPriceContextMemberV1 for item in self.members
            )
            or len({item.isin for item in self.members}) != len(self.members)
            or len({item.effective_symbol for item in self.members})
            != len(self.members)
            or self.questions != _QUESTIONS
            or type(self.industry_archive_reference)
            not in (CurrentIndustryArchiveReferenceV1, type(None))
            or self.execution_mode not in _MODES
            or type(self.include_current_session) is not bool
        ):
            raise ValueError("current price context V2 request is invalid")
        selection_date = self.data_selection_time.astimezone(_IST).date()
        if any(
            not item.valid_from <= selection_date <= item.valid_through
            for item in self.members
        ):
            raise ValueError(
                "current price context V2 member is not valid at selection"
            )
        identity = self.identity_of(self)
        if self.request_identity_sha256 not in ("", identity):
            raise ValueError("current price context V2 request identity is invalid")
        object.__setattr__(self, "request_identity_sha256", identity)
        if len(self.canonical_json_bytes()) > _MAX_REQUEST_BYTES:
            raise ValueError("current price context V2 request exceeds its bound")

    @staticmethod
    def identity_of(value: CurrentPriceContextRequestV2) -> str:
        if type(value) is not CurrentPriceContextRequestV2:
            raise ValueError("current price context V2 request is invalid")
        return _hash(
            {
                "contract_version": value.contract_version,
                "data_selection_time": value.data_selection_time,
                "admission_deadline": value.admission_deadline,
                "schedule_identity_sha256": value.schedule_identity_sha256,
                "members": value.members,
                "questions": value.questions,
                "industry_archive_reference": value.industry_archive_reference,
                "execution_mode": value.execution_mode,
                "include_current_session": value.include_current_session,
            }
        )

    def canonical_json_bytes(self) -> bytes:
        value = {
            "contract_version": self.contract_version,
            "data_selection_time": self.data_selection_time,
            "admission_deadline": self.admission_deadline,
            "schedule_identity_sha256": self.schedule_identity_sha256,
            "members": self.members,
            "questions": self.questions,
            "industry_archive_reference": self.industry_archive_reference,
            "execution_mode": self.execution_mode,
            "include_current_session": self.include_current_session,
        }
        return _canonical(value)


@dataclass(frozen=True, slots=True)
class CurrentSessionPriceContextMemberV2:
    position: int
    isin: str
    exchange: Literal["NSE"]
    effective_symbol: str
    state: Literal[
        "OBSERVED", "NOT_APPLICABLE", "NOT_REQUESTED", "UNAVAILABLE", "CONFLICTED"
    ]
    label: Literal["PARTIAL_CURRENT_SESSION"] | None
    reason: str | None
    last_completed_minute: datetime | None = None
    observed_price: str | None = None
    cumulative_source_volume: int | None = None
    source_version: Literal["upstox-intraday-v3"] | None = None
    partition_checksum_sha256: str | None = None
    source_cutoff: datetime | None = None
    published_at: datetime | None = None
    known_at: datetime | None = None

    def __post_init__(self) -> None:
        observed = self.state == "OBSERVED"
        provenance = (
            self.last_completed_minute,
            self.observed_price,
            self.cumulative_source_volume,
            self.source_version,
            self.partition_checksum_sha256,
            self.source_cutoff,
            self.published_at,
            self.known_at,
        )
        if (
            type(self.position) is not int
            or self.position < 0
            or type(self.isin) is not str
            or not self.isin
            or self.exchange != "NSE"
            or type(self.effective_symbol) is not str
            or not self.effective_symbol
            or self.state
            not in {
                "OBSERVED",
                "NOT_APPLICABLE",
                "NOT_REQUESTED",
                "UNAVAILABLE",
                "CONFLICTED",
            }
            or (observed and (self.label != "PARTIAL_CURRENT_SESSION" or self.reason))
            or (
                not observed
                and (
                    self.label is not None
                    or type(self.reason) is not str
                    or self.reason not in _PROVISIONAL_REASONS[self.state]
                )
            )
            or (observed and any(item is None for item in provenance))
            or (not observed and any(item is not None for item in provenance))
            or (
                observed
                and not _valid_observed_values(
                    self.last_completed_minute,
                    self.observed_price,
                    self.cumulative_source_volume,
                    self.source_version,
                    self.partition_checksum_sha256,
                    self.source_cutoff,
                    self.published_at,
                    self.known_at,
                )
            )
        ):
            raise ValueError("current-session price context member is invalid")


@dataclass(frozen=True, slots=True)
class CurrentPriceContextFreshnessEntryV2:
    source: Literal[
        "CALENDAR",
        "MAPPING",
        "CLOSED_MONTH",
        "CURRENT_HISTORY",
        "CURRENT_SESSION",
        "CORPORATE_ACTION",
        "INDUSTRY",
    ]
    slot: str
    position: int | None
    isin: str | None
    effective_symbol: str | None
    physical_identity_sha256: str | None
    state: Literal[
        "REUSED",
        "ACQUIRED",
        "REFRESHED",
        "APPENDED",
        "CONFLICTED",
        "UNAVAILABLE",
        "NOT_REQUESTED",
    ]
    source_cutoff: datetime | None
    prior_source_cutoff: datetime | None
    published_at: datetime | None
    known_at: datetime | None
    provider_calls_attempted: int
    provider_calls_completed: int
    correction_rule: Literal[
        "RETAINED_EXACT_CALENDAR",
        "SELECTION_DATE_MAPPING",
        "IMMUTABLE_CLOSED_MONTH_REUSE",
        "CURRENT_MONTH_IDENTICAL_OVERLAP_OR_INTRADAY_TO_HISTORICAL_FINALIZATION",
        "CURRENT_SESSION_IDENTICAL_OVERLAP_APPEND_OR_CONFLICT",
        "LATEST_RETAINED_ACTION_AT_CUTOFF",
        "RETAINED_ONLY_EXACT_INDUSTRY",
    ]

    def __post_init__(self) -> None:
        member_scoped = self.source not in {"CALENDAR", "MAPPING", "INDUSTRY"}
        clocks = (
            self.prior_source_cutoff,
            self.source_cutoff,
            self.published_at,
            self.known_at,
        )
        present_clocks = tuple(item for item in clocks if item is not None)
        if (
            self.source not in _LEDGER_SOURCES
            or type(self.slot) is not str
            or not 1 <= len(self.slot) <= 32
            or re.fullmatch(r"[a-z0-9-]+", self.slot) is None
            or (member_scoped and (type(self.position) is not int or self.position < 0))
            or (not member_scoped and self.position is not None)
            or member_scoped != (type(self.isin) is str and bool(self.isin))
            or member_scoped
            != (type(self.effective_symbol) is str and bool(self.effective_symbol))
            or (
                self.physical_identity_sha256 is not None
                and not _digest(self.physical_identity_sha256)
            )
            or self.state not in _LEDGER_STATES
            or any(not _utc(item) for item in present_clocks)
            or (
                self.prior_source_cutoff is not None
                and (
                    self.source != "CURRENT_SESSION"
                    or self.source_cutoff is None
                    or self.prior_source_cutoff > self.source_cutoff
                )
            )
            or any(
                left > right
                for left, right in zip(present_clocks, present_clocks[1:], strict=False)
            )
            or type(self.provider_calls_attempted) is not int
            or not 0
            <= self.provider_calls_attempted
            <= (2 if self.source == "CURRENT_HISTORY" else 1)
            or type(self.provider_calls_completed) is not int
            or not 0 <= self.provider_calls_completed <= self.provider_calls_attempted
            or self.state in {"ACQUIRED", "REFRESHED", "APPENDED"}
            and not (
                1
                <= self.provider_calls_completed
                <= (2 if self.source == "CURRENT_HISTORY" else 1)
            )
            or self.state in {"REUSED", "NOT_REQUESTED"}
            and self.provider_calls_attempted != 0
            or self.state == "NOT_REQUESTED"
            and (self.physical_identity_sha256 is not None or present_clocks)
            or self.source in {"CALENDAR", "INDUSTRY"}
            and self.provider_calls_attempted != 0
            or self.state in {"REFRESHED", "APPENDED"}
            and self.source != "CURRENT_SESSION"
            or self.correction_rule not in _CORRECTION_RULES
            or self.correction_rule != _CORRECTION_BY_SOURCE.get(self.source)
        ):
            raise ValueError("current price context freshness entry is invalid")


def _freshness_ledger_is_bound(  # noqa: C901 -- closed ledger provenance matrix
    value: CurrentPriceContextResultV2,
) -> bool:
    ledger = value.freshness_ledger
    expected = _expected_physical_plan(
        CurrentPriceContextRequestV2(
            _REQUEST_CONTRACT,
            value.data_selection_time,
            value.admission_deadline,
            value.schedule_identity_sha256,
            value.request_members,
            value.questions,
            value.industry_archive_reference,
            value.execution_mode,
            value.include_current_session,
            value.request_identity_sha256,
        ),
        value.planning_witness,
    )
    if (
        tuple((item.source, item.slot, item.position) for item in ledger)
        != tuple((item.source, item.slot, item.position) for item in expected)
        or ledger[0].source != "CALENDAR"
        or ledger[-1].source != "INDUSTRY"
        or any(
            item.source == "CURRENT_HISTORY"
            and item.provider_calls_attempted > 1
            and (
                not value.planning_witness.completed_sessions
                or value.planning_witness.completed_sessions[-1].trade_date
                != value.data_selection_time.astimezone(_IST).date()
            )
            for item in ledger
        )
    ):
        return False
    member_positions = tuple(
        item.position for item in ledger if item.position is not None
    )
    if member_positions != tuple(sorted(member_positions)):
        return False

    calendar = ledger[0]
    if (
        calendar.slot != "calendar"
        or calendar.physical_identity_sha256 != value.schedule_identity_sha256
        or calendar.state
        != (
            "REUSED"
            if value.completed_context.schedule_as_of is not None
            else "UNAVAILABLE"
        )
        or calendar.source_cutoff != value.completed_context.schedule_as_of
        or calendar.prior_source_cutoff is not None
        or calendar.published_at is not None
        or calendar.known_at is not None
        or calendar.provider_calls_attempted != 0
        or calendar.provider_calls_completed != 0
    ):
        return False

    mapping_entries = tuple(item for item in ledger if item.source == "MAPPING")
    mapping = None if len(mapping_entries) != 1 else mapping_entries[0]
    if (
        mapping is None
        or mapping.slot != "mapping"
        or mapping.position is not None
        or mapping.isin is not None
        or mapping.effective_symbol is not None
        or mapping.physical_identity_sha256 is not None
        or mapping.source_cutoff is not None
        or mapping.prior_source_cutoff is not None
        or mapping.published_at is not None
        or mapping.known_at is not None
        or mapping.provider_calls_completed > mapping.provider_calls_attempted
    ):
        return False
    mapping_admitted = any(
        item.mapping_observation_sha256 is not None
        or item.reason in _MAPPING_ADMITTED_DOWNSTREAM_REASONS
        for item in value.completed_context.members
    ) or any(item.state == "OBSERVED" for item in value.current_session)
    mapping_failed = all(
        item.state == "DEPENDENCY_BLOCKED"
        and item.reason in {"RAW_MAPPING_MISSING", "RAW_MAPPING_UNSUPPORTED"}
        for item in value.completed_context.members
    ) and not any(item.state == "OBSERVED" for item in value.current_session)
    expected_mapping_state = (
        "REUSED"
        if (mapping.provider_calls_attempted, mapping.provider_calls_completed)
        == (0, 0)
        else "ACQUIRED"
        if (mapping.provider_calls_attempted, mapping.provider_calls_completed)
        == (1, 1)
        else None
    )
    if not value.planning_witness.completed_sessions or mapping_failed:
        if mapping.state != "UNAVAILABLE":
            return False
    elif mapping_admitted:
        if mapping.state != expected_mapping_state:
            return False
    elif mapping.state not in {"UNAVAILABLE", expected_mapping_state}:
        return False

    for position, completed_member in enumerate(value.completed_context.members):
        scoped = tuple(item for item in ledger if item.position == position)
        if not scoped:
            return False
        partitions = tuple(
            item
            for item in scoped
            if item.source in {"CLOSED_MONTH", "CURRENT_HISTORY"}
        )
        slot_months: list[date] = []
        sources: list[str] = []
        for partition in partitions:
            matched = re.fullmatch(r"(\d{4})-(\d{2})", partition.slot)
            if matched is None:
                return False
            try:
                slot_month = date(int(matched.group(1)), int(matched.group(2)), 1)
            except ValueError:
                return False
            slot_months.append(slot_month)
            sources.append(partition.source)
        selection_month = (
            value.data_selection_time.astimezone(_IST).date().replace(day=1)
        )
        earliest_month = (
            value.data_selection_time.astimezone(_IST).date() - timedelta(days=63)
        ).replace(day=1)
        if (
            slot_months != sorted(slot_months)
            or len(set(slot_months)) != len(slot_months)
            or any(
                month < earliest_month or month > selection_month
                for month in slot_months
            )
            or any(
                (source == "CURRENT_HISTORY") != (month == selection_month)
                for source, month in zip(sources, slot_months, strict=True)
            )
            or sources
            != ["CLOSED_MONTH"] * sources.count("CLOSED_MONTH")
            + ["CURRENT_HISTORY"] * sources.count("CURRENT_HISTORY")
            or sources.count("CURRENT_HISTORY") > 1
        ):
            return False
        if completed_member.state == "OBSERVED":
            expected = tuple(
                zip(
                    completed_member.partition_checksums,
                    completed_member.raw_source_times,
                    strict=True,
                )
            )
            actual = tuple(
                (item.physical_identity_sha256, item.source_cutoff)
                for item in partitions
            )
            if actual != expected or any(
                item.prior_source_cutoff is not None
                or item.published_at is not None
                or item.known_at is not None
                or item.state not in {"REUSED", "ACQUIRED"}
                or (item.state == "REUSED" and item.provider_calls_attempted != 0)
                for item in partitions
            ):
                return False
        elif any(
            item.physical_identity_sha256 is not None
            or item.source_cutoff is not None
            or item.prior_source_cutoff is not None
            or item.published_at is not None
            or item.known_at is not None
            or item.state != "UNAVAILABLE"
            for item in partitions
        ):
            return False
        actions = tuple(item for item in scoped if item.source == "CORPORATE_ACTION")
        if len(actions) != 1:
            return False
        action = actions[0]
        action_evidence_retained = completed_member.screen_knowledge_at is not None
        if action_evidence_retained:
            expected_action_state = (
                "REUSED"
                if (
                    action.provider_calls_attempted,
                    action.provider_calls_completed,
                )
                == (0, 0)
                else "ACQUIRED"
                if (
                    action.provider_calls_attempted,
                    action.provider_calls_completed,
                )
                == (1, 1)
                else None
            )
            if action.state != expected_action_state:
                return False
        elif (
            action.state != "UNAVAILABLE"
            or action.physical_identity_sha256 is not None
            or action.source_cutoff is not None
            or action.prior_source_cutoff is not None
            or action.published_at is not None
            or action.known_at is not None
        ):
            return False
    industry = ledger[-1]
    reference = value.industry_archive_reference
    expected_industry_state = (
        "NOT_REQUESTED"
        if reference is None
        else "REUSED"
        if value.completed_context.industry_evidence_state == "OBSERVED"
        else "CONFLICTED"
        if value.completed_context.industry_evidence_state == "CONFLICTED"
        else "UNAVAILABLE"
    )
    if (
        industry.slot != "industry"
        or industry.physical_identity_sha256
        != (None if reference is None else reference.retained_identity_sha256)
        or industry.state != expected_industry_state
        or industry.source_cutoff is not None
        or industry.prior_source_cutoff is not None
        or industry.published_at is not None
        or industry.known_at != value.completed_context.industry_known_at
        or industry.provider_calls_attempted != 0
        or industry.provider_calls_completed != 0
    ):
        return False
    return not (
        value.completed_context.industry_evidence_state == "OBSERVED"
        and (
            reference is None
            or value.completed_context.industry_snapshot_identity_sha256
            != reference.snapshot_identity_sha256
            or value.completed_context.industry_retained_identity_sha256
            != reference.retained_identity_sha256
        )
    )


@dataclass(frozen=True, slots=True)
class CurrentPriceContextPlanningSessionV2:
    """Bounded public projection of one retained schedule session."""

    trade_date: date
    open_at: datetime
    close_at: datetime
    kind: Literal["REGULAR", "SPECIAL"]

    def __post_init__(self) -> None:
        if (
            type(self.trade_date) is not date
            or not _utc(self.open_at)
            or not _utc(self.close_at)
            or self.open_at >= self.close_at
            or self.kind not in {"REGULAR", "SPECIAL"}
            or self.open_at.second != 0
            or self.open_at.microsecond != 0
            or self.close_at.second != 0
            or self.close_at.microsecond != 0
            or self.open_at.astimezone(_IST).date() != self.trade_date
            or self.close_at.astimezone(_IST).date() != self.trade_date
        ):
            raise ValueError("current price context planning session is invalid")


@dataclass(frozen=True, slots=True)
class CurrentPriceContextPlanningWitnessV2:
    """Structural schedule rebinding evidence; not calendar attestation."""

    schedule_as_of: datetime | None
    completed_sessions: tuple[CurrentPriceContextPlanningSessionV2, ...]
    selection_session: CurrentPriceContextPlanningSessionV2 | None

    def __post_init__(self) -> None:
        if (
            (self.schedule_as_of is not None and not _utc(self.schedule_as_of))
            or type(self.completed_sessions) is not tuple
            or any(
                type(item) is not CurrentPriceContextPlanningSessionV2
                for item in self.completed_sessions
            )
            or (
                self.selection_session is not None
                and type(self.selection_session)
                is not CurrentPriceContextPlanningSessionV2
            )
            or (not self.completed_sessions and self.selection_session is not None)
        ):
            raise ValueError("current price context planning witness is invalid")


@dataclass(frozen=True, slots=True)
class _PhysicalPlanSlotV2:
    key: str
    kind: str


@dataclass(frozen=True, slots=True)
class CurrentPriceContextPhysicalPlanEntryV2:
    """One public, schedule-derived physical ledger key; not an attestation."""

    source: Literal[
        "CALENDAR",
        "MAPPING",
        "CLOSED_MONTH",
        "CURRENT_HISTORY",
        "CURRENT_SESSION",
        "CORPORATE_ACTION",
        "INDUSTRY",
    ]
    slot: str
    position: int | None

    def __post_init__(self) -> None:
        if (
            self.source not in _LEDGER_SOURCES
            or type(self.slot) is not str
            or not 1 <= len(self.slot) <= 32
            or re.fullmatch(r"[a-z0-9-]+", self.slot) is None
            or (
                self.position is not None
                and (type(self.position) is not int or self.position < 0)
            )
        ):
            raise ValueError("current price context physical plan entry is invalid")


def _planning_session(value: ScheduleSession) -> CurrentPriceContextPlanningSessionV2:
    return CurrentPriceContextPlanningSessionV2(
        value.trade_date,
        value.open_at,
        value.close_at,
        cast(Literal["REGULAR", "SPECIAL"], value.kind),
    )


def _absent_planning_witness(
    schedule_as_of: datetime | None = None,
) -> CurrentPriceContextPlanningWitnessV2:
    return CurrentPriceContextPlanningWitnessV2(schedule_as_of, (), None)


def _planning_witness_from_retained(
    request: CurrentPriceContextRequestV2,
    raw_request: CurrentRawPriceContextInputV1,
    storage_root: Path,
    control: CurrentRawInvocationControlV1,
    root_authority: RootAuthorityV1,
) -> CurrentPriceContextPlanningWitnessV2:
    lease = StorageRootLease.admit_read_authority(storage_root, root_authority)
    if lease is None:
        return _absent_planning_witness()
    with lease:
        resolved = ScheduleEvidenceStore(storage_root, lease).resolve(
            request.schedule_identity_sha256, deadline=control
        )
        if resolved.schedule is None:
            return _absent_planning_witness()
        selected = tuple(
            item
            for item in resolved.schedule.sessions
            if item.close_at <= raw_request.data_selection_time
        )[-21:]
        months = tuple(
            dict.fromkeys(
                (item.trade_date.year, item.trade_date.month) for item in selected
            )
        )
        if (
            len(selected) != 21
            or sum(
                int((item.close_at - item.open_at).total_seconds() // 60)
                for item in selected
            )
            > 10_000
            or not exact_nse_schedule_source_release_pair_v1(
                resolved.schedule.source, resolved.schedule.source_release
            )
            or resolved.schedule.as_of > control.now()
            or selected[-1].trade_date - selected[0].trade_date > timedelta(days=63)
            or not 1 <= len(months) <= 3
            or any(item.kind not in {"REGULAR", "SPECIAL"} for item in selected)
            or any(
                not schedule_covers_full_calendar_range(
                    resolved.schedule,
                    date(year, month, 1),
                    selected[-1].trade_date
                    if (year, month)
                    == (
                        raw_request.data_selection_time.astimezone(_IST).year,
                        raw_request.data_selection_time.astimezone(_IST).month,
                    )
                    else date(year, month, monthrange(year, month)[1]),
                )
                for year, month in months
            )
        ):
            return _absent_planning_witness(resolved.schedule.as_of)
        completed = tuple(_planning_session(item) for item in selected)
        selection_day = request.data_selection_time.astimezone(_IST).date()
        selection = next(
            (
                _planning_session(item)
                for item in resolved.schedule.sessions
                if item.trade_date == selection_day
                and item.trade_date not in {row.trade_date for row in completed}
            ),
            None,
        )
        return CurrentPriceContextPlanningWitnessV2(
            resolved.schedule.as_of, completed, selection
        )


def _witness_is_bound(
    witness: CurrentPriceContextPlanningWitnessV2,
    request: CurrentPriceContextRequestV2,
    completed: CurrentPriceContextResultV1,
) -> bool:
    sessions = witness.completed_sessions
    if not sessions:
        return (
            witness.selection_session is None
            and (
                witness.schedule_as_of == completed.schedule_as_of
                or (
                    witness.schedule_as_of is not None
                    and completed.schedule_as_of is None
                )
            )
            and all(
                item.reason in _ABSENT_PLANNING_WITNESS_REASONS
                for item in completed.members
            )
        )
    selection_day = request.data_selection_time.astimezone(_IST).date()
    dates = tuple(item.trade_date for item in sessions)
    months = tuple(
        dict.fromkeys(
            (item.trade_date.year, item.trade_date.month) for item in sessions
        )
    )
    selection = witness.selection_session
    return (
        len(sessions) == 21
        and dates == tuple(sorted(dates))
        and len(set(dates)) == len(dates)
        and all(item.close_at <= request.data_selection_time for item in sessions)
        and sum(
            int((item.close_at - item.open_at).total_seconds() // 60)
            for item in sessions
        )
        <= 10_000
        and dates[-1] - dates[0] <= timedelta(days=63)
        and 1 <= len(months) <= 3
        and witness.schedule_as_of == completed.schedule_as_of
        and witness.schedule_as_of is not None
        and (
            selection is None
            or (
                selection.trade_date == selection_day
                and selection.trade_date not in set(dates)
                and request.data_selection_time < selection.close_at
            )
        )
    )


def _expected_physical_plan(
    request: CurrentPriceContextRequestV2,
    witness: CurrentPriceContextPlanningWitnessV2,
) -> tuple[CurrentPriceContextPhysicalPlanEntryV2, ...]:
    entries = [
        CurrentPriceContextPhysicalPlanEntryV2("CALENDAR", "calendar", None),
        CurrentPriceContextPhysicalPlanEntryV2("MAPPING", "mapping", None),
    ]
    completed_months = tuple(
        dict.fromkeys(
            f"{item.trade_date.year:04d}-{item.trade_date.month:02d}"
            for item in witness.completed_sessions
        )
    )
    selection_month = request.data_selection_time.astimezone(_IST).strftime("%Y-%m")
    active = witness.selection_session
    active_slot = (
        f"{active.trade_date.year:04d}-{active.trade_date.month:02d}"
        if request.include_current_session
        and active is not None
        and active.open_at + timedelta(minutes=1)
        <= request.data_selection_time
        < active.close_at
        else "current-session"
    )
    for position in range(len(request.members)):
        entries.extend(
            CurrentPriceContextPhysicalPlanEntryV2(
                "CURRENT_HISTORY" if month == selection_month else "CLOSED_MONTH",
                month,
                position,
            )
            for month in completed_months
        )
        entries.append(
            CurrentPriceContextPhysicalPlanEntryV2(
                "CORPORATE_ACTION", "action", position
            )
        )
        entries.append(
            CurrentPriceContextPhysicalPlanEntryV2(
                "CURRENT_SESSION", active_slot, position
            )
        )
    entries.append(CurrentPriceContextPhysicalPlanEntryV2("INDUSTRY", "industry", None))
    return tuple(entries)


def _observed_current_session_is_bound(  # noqa: C901 -- closed provisional phase matrix
    value: CurrentPriceContextResultV2,
) -> bool:
    """Bind every finite provisional phase to its witness, evidence, and ledger."""
    selection = value.planning_witness.selection_session
    has_witness = bool(value.planning_witness.completed_sessions)
    active = selection is not None and (
        selection.open_at + timedelta(minutes=1)
        <= value.data_selection_time
        < selection.close_at
    )
    target = (
        None
        if not active or selection is None
        else min(
            value.data_selection_time.replace(second=0, microsecond=0)
            - timedelta(minutes=1),
            selection.close_at - timedelta(minutes=1),
        )
    )
    active_slot = (
        None
        if selection is None
        else f"{selection.trade_date.year:04d}-{selection.trade_date.month:02d}"
    )
    for member in value.current_session:
        entries = tuple(
            item
            for item in value.freshness_ledger
            if item.source == "CURRENT_SESSION" and item.position == member.position
        )
        if len(entries) != 1:
            return False
        entry = entries[0]
        if not value.include_current_session:
            if member.state != "NOT_REQUESTED" or entry.state != "NOT_REQUESTED":
                return False
            continue
        if not has_witness:
            expected = {("UNAVAILABLE", "CALENDAR_PREREQUISITE_MISSING")}
            if value.planning_witness.schedule_as_of is not None:
                expected.add(("NOT_APPLICABLE", "CURRENT_SESSION_NOT_APPLICABLE"))
            if (
                member.state,
                member.reason,
            ) not in expected or entry.state != "UNAVAILABLE":
                return False
            continue
        if selection is None or value.data_selection_time < selection.open_at:
            if (
                member.state != "NOT_APPLICABLE"
                or member.reason != "CURRENT_SESSION_NOT_APPLICABLE"
                or entry.state != "UNAVAILABLE"
            ):
                return False
            continue
        if not active:
            if (
                member.state != "UNAVAILABLE"
                or member.reason != "NO_FULLY_COMPLETED_MINUTE"
                or entry.state != "UNAVAILABLE"
            ):
                return False
            continue
        if member.state == "OBSERVED":
            final_source_cutoff = member.source_cutoff
            if final_source_cutoff is None:
                return False
            if (
                target is None
                or entry.slot != active_slot
                or member.last_completed_minute != target
                or member.source_cutoff != target
                or entry.state
                not in {
                    "REUSED",
                    "ACQUIRED",
                    "REFRESHED",
                    "APPENDED",
                }
                or (
                    entry.state == "REUSED"
                    and (
                        (entry.provider_calls_attempted, entry.provider_calls_completed)
                        != (0, 0)
                        or entry.prior_source_cutoff != final_source_cutoff
                    )
                )
                or (
                    entry.state == "ACQUIRED"
                    and (
                        (entry.provider_calls_attempted, entry.provider_calls_completed)
                        != (1, 1)
                        or entry.prior_source_cutoff is not None
                    )
                )
                or (
                    entry.state == "REFRESHED"
                    and (
                        value.execution_mode != "REFRESH_ONCE"
                        or (
                            entry.provider_calls_attempted,
                            entry.provider_calls_completed,
                        )
                        != (1, 1)
                        or entry.prior_source_cutoff != final_source_cutoff
                    )
                )
                or (
                    entry.state == "APPENDED"
                    and (
                        value.execution_mode != "REFRESH_ONCE"
                        or (
                            entry.provider_calls_attempted,
                            entry.provider_calls_completed,
                        )
                        != (1, 1)
                        or entry.prior_source_cutoff is None
                        or entry.prior_source_cutoff >= final_source_cutoff
                    )
                )
                or (value.execution_mode == "RETAINED_ONLY" and entry.state != "REUSED")
                or (
                    value.execution_mode == "ACQUIRE_MISSING"
                    and entry.state not in {"REUSED", "ACQUIRED"}
                )
            ):
                return False
        elif member.state == "UNAVAILABLE":
            if (
                member.reason
                not in {
                    "PROVISIONAL_EVIDENCE_UNAVAILABLE",
                    "PROVISIONAL_EVIDENCE_STALE",
                }
                or entry.state != "UNAVAILABLE"
                or entry.prior_source_cutoff is not None
            ):
                return False
        elif member.state == "CONFLICTED":
            if (
                member.reason != "PROVISIONAL_EVIDENCE_CONFLICTED"
                or entry.state != "CONFLICTED"
                or entry.prior_source_cutoff is not None
            ):
                return False
        else:
            return False
    return True


@dataclass(frozen=True, slots=True)
class CurrentPriceContextResultV2:
    contract_version: Literal["current-price-context@v2"]
    request_identity_sha256: str
    execution_mode: Literal["RETAINED_ONLY", "ACQUIRE_MISSING", "REFRESH_ONCE"]
    data_selection_time: datetime
    admission_deadline: datetime
    schedule_identity_sha256: str
    request_members: tuple[CurrentPriceContextMemberV1, ...]
    questions: tuple[str, ...]
    industry_archive_reference: CurrentIndustryArchiveReferenceV1 | None
    include_current_session: bool
    inspection_time: datetime
    acquisition_started_at: datetime | None
    acquisition_completed_at: datetime | None
    evidence_cutoff: datetime
    provider_calls_attempted: int
    provider_calls_completed: int
    provider_call_budget: int
    reused_physical_objects: int
    refreshed_physical_objects: int
    completed_context: CurrentPriceContextResultV1
    current_session: tuple[CurrentSessionPriceContextMemberV2, ...]
    planning_witness: CurrentPriceContextPlanningWitnessV2
    physical_plan: tuple[CurrentPriceContextPhysicalPlanEntryV2, ...]
    freshness_ledger: tuple[CurrentPriceContextFreshnessEntryV2, ...]
    runtime_code_identity_sha256: str
    result_identity_sha256: str = ""

    def __post_init__(self) -> None:
        calls = self.provider_calls_attempted
        bound_request: CurrentPriceContextRequestV2 | None = None
        with suppress(ValueError):
            bound_request = CurrentPriceContextRequestV2(
                _REQUEST_CONTRACT,
                self.data_selection_time,
                self.admission_deadline,
                self.schedule_identity_sha256,
                self.request_members,
                self.questions,
                self.industry_archive_reference,
                self.execution_mode,
                self.include_current_session,
                self.request_identity_sha256,
            )
        target_minute = self.data_selection_time.replace(
            second=0, microsecond=0
        ) - timedelta(minutes=1)
        if (
            self.contract_version != _RESULT_CONTRACT
            or bound_request is None
            or bound_request.request_identity_sha256 != self.request_identity_sha256
            or not _utc(self.inspection_time)
            or not _utc(self.evidence_cutoff)
            or self.inspection_time < self.data_selection_time
            or self.evidence_cutoff < self.inspection_time
            or self.evidence_cutoff >= self.admission_deadline
            or (
                (calls == 0)
                != (
                    self.acquisition_started_at is None
                    and self.acquisition_completed_at is None
                )
            )
            or (
                calls > 0
                and not _valid_acquisition_window(
                    self.acquisition_started_at,
                    self.acquisition_completed_at,
                    self.inspection_time,
                    self.evidence_cutoff,
                )
            )
            or type(calls) is not int
            or not 0 <= calls <= self.provider_call_budget
            or type(self.provider_calls_completed) is not int
            or not 0 <= self.provider_calls_completed <= calls
            or type(self.provider_call_budget) is not int
            or self.provider_call_budget != min(5 * len(self.request_members) + 1, 251)
            or type(self.reused_physical_objects) is not int
            or self.reused_physical_objects < 0
            or type(self.refreshed_physical_objects) is not int
            or not 0 <= self.refreshed_physical_objects <= calls
            or type(self.completed_context) is not CurrentPriceContextResultV1
            or self.completed_context.request_identity_sha256
            != _v1_request(bound_request).request_identity_sha256
            or self.completed_context.data_selection_time != self.data_selection_time
            or self.completed_context.schedule_identity_sha256
            != self.schedule_identity_sha256
            or self.completed_context.questions != self.questions
            or self.completed_context.requested_count != len(self.request_members)
            or tuple(
                (item.isin, item.exchange, item.effective_symbol)
                for item in self.completed_context.members
            )
            != tuple(
                (item.isin, item.exchange, item.effective_symbol)
                for item in self.request_members
            )
            or self.completed_context.evidence_cutoff > self.evidence_cutoff
            or type(self.current_session) is not tuple
            or len(self.current_session) != len(self.request_members)
            or any(
                type(item) is not CurrentSessionPriceContextMemberV2
                for item in self.current_session
            )
            or tuple(item.position for item in self.current_session)
            != tuple(range(len(self.current_session)))
            or tuple(
                (item.isin, item.exchange, item.effective_symbol)
                for item in self.current_session
            )
            != tuple(
                (item.isin, item.exchange, item.effective_symbol)
                for item in self.request_members
            )
            or any(
                item.last_completed_minute is not None
                and item.last_completed_minute > target_minute
                for item in self.current_session
            )
            or any(
                item.source_cutoff is not None
                and item.source_cutoff > self.data_selection_time
                for item in self.current_session
            )
            or any(
                clock is not None and clock > self.evidence_cutoff
                for item in self.current_session
                for clock in (item.source_cutoff, item.published_at, item.known_at)
            )
            or type(self.planning_witness) is not CurrentPriceContextPlanningWitnessV2
            or not _witness_is_bound(
                self.planning_witness, bound_request, self.completed_context
            )
            or type(self.physical_plan) is not tuple
            or len(self.physical_plan) != len(self.freshness_ledger)
            or any(
                type(item) is not CurrentPriceContextPhysicalPlanEntryV2
                for item in self.physical_plan
            )
            or self.physical_plan
            != _expected_physical_plan(bound_request, self.planning_witness)
            or tuple(
                (item.source, item.slot, item.position) for item in self.physical_plan
            )
            != tuple(
                (item.source, item.slot, item.position)
                for item in self.freshness_ledger
            )
            or type(self.freshness_ledger) is not tuple
            or not 2 <= len(self.freshness_ledger) <= 5 * len(self.request_members) + 3
            or any(
                type(item) is not CurrentPriceContextFreshnessEntryV2
                for item in self.freshness_ledger
            )
            or sum(item.provider_calls_attempted for item in self.freshness_ledger)
            != calls
            or sum(item.provider_calls_completed for item in self.freshness_ledger)
            != self.provider_calls_completed
            or self.reused_physical_objects
            != sum(item.state == "REUSED" for item in self.freshness_ledger)
            or self.refreshed_physical_objects
            != sum(
                item.state in {"REFRESHED", "APPENDED"}
                for item in self.freshness_ledger
            )
            or any(
                clock is not None and clock > self.evidence_cutoff
                for item in self.freshness_ledger
                for clock in (
                    item.prior_source_cutoff,
                    item.source_cutoff,
                    item.published_at,
                    item.known_at,
                )
            )
            or len(
                {
                    (item.source, item.slot, item.position)
                    for item in self.freshness_ledger
                }
            )
            != len(self.freshness_ledger)
            or sum(item.source == "CALENDAR" for item in self.freshness_ledger) != 1
            or sum(item.source == "INDUSTRY" for item in self.freshness_ledger) != 1
            or sum(item.source == "MAPPING" for item in self.freshness_ledger) != 1
            or any(
                sum(
                    item.source == source and item.position == position
                    for item in self.freshness_ledger
                )
                != 1
                for source in ("CURRENT_SESSION", "CORPORATE_ACTION")
                for position in range(len(self.request_members))
            )
            or any(
                item.position is not None
                and (
                    item.position >= len(self.request_members)
                    or item.isin != self.request_members[item.position].isin
                    or item.effective_symbol
                    != self.request_members[item.position].effective_symbol
                )
                for item in self.freshness_ledger
            )
            or not _freshness_ledger_is_bound(self)
            or any(
                item.source == "CORPORATE_ACTION"
                and (
                    item.physical_identity_sha256
                    != self.completed_context.members[
                        cast(int, item.position)
                    ].screen_identity_sha256
                    or item.known_at
                    != self.completed_context.members[
                        cast(int, item.position)
                    ].screen_knowledge_at
                )
                for item in self.freshness_ledger
            )
            or any(
                item.source == "CURRENT_SESSION"
                and (
                    (not self.include_current_session and item.state != "NOT_REQUESTED")
                    or (self.include_current_session and item.state == "NOT_REQUESTED")
                    or item.physical_identity_sha256
                    != self.current_session[
                        cast(int, item.position)
                    ].partition_checksum_sha256
                    or item.source_cutoff
                    != self.current_session[cast(int, item.position)].source_cutoff
                    or item.published_at
                    != self.current_session[cast(int, item.position)].published_at
                    or item.known_at
                    != self.current_session[cast(int, item.position)].known_at
                    or (
                        self.current_session[cast(int, item.position)].state
                        == "CONFLICTED"
                        and item.state != "CONFLICTED"
                    )
                    or (
                        self.current_session[cast(int, item.position)].state
                        == "OBSERVED"
                        and item.state
                        not in {"REUSED", "ACQUIRED", "REFRESHED", "APPENDED"}
                    )
                )
                for item in self.freshness_ledger
            )
            or not _observed_current_session_is_bound(self)
            or self.runtime_code_identity_sha256
            != current_price_context_runtime_code_identity_v2()
            or (self.execution_mode == "RETAINED_ONLY" and calls != 0)
        ):
            raise ValueError("current price context V2 result is invalid")
        identity = _hash(_result_without_identity(self))
        if self.result_identity_sha256 not in ("", identity):
            raise ValueError("current price context V2 result identity is invalid")
        object.__setattr__(self, "result_identity_sha256", identity)

    def canonical_json_bytes(self) -> bytes:
        raw = _canonical(self)
        if len(raw) > _MAX_RESULT_BYTES:
            raise ValueError("current price context V2 result exceeds its bound")
        return raw


def _result_without_identity(value: CurrentPriceContextResultV2) -> dict[str, object]:
    return {
        field.name: getattr(value, field.name)
        for field in fields(value)
        if field.name != "result_identity_sha256"
    }


def _member_from_value(value: object) -> CurrentPriceContextMemberV1:
    if type(value) is not dict:
        raise ValueError
    member = cast(dict[str, object], value)
    if set(member) != {
        "isin",
        "exchange",
        "instrument_type",
        "segment",
        "effective_symbol",
        "valid_from",
        "valid_through",
    }:
        raise ValueError
    return CurrentPriceContextMemberV1(
        cast(str, member["isin"]),
        cast(Literal["NSE"], member["exchange"]),
        cast(Literal["EQUITY"], member["instrument_type"]),
        cast(Literal["EQ"], member["segment"]),
        cast(str, member["effective_symbol"]),
        _parse_date(member["valid_from"]),
        _parse_date(member["valid_through"]),
    )


def _reference_from_value(value: object) -> CurrentIndustryArchiveReferenceV1 | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise ValueError
    reference = cast(dict[str, object], value)
    if set(reference) != {
        "contract_version",
        "snapshot_identity_sha256",
        "retained_identity_sha256",
    }:
        raise ValueError
    return CurrentIndustryArchiveReferenceV1(
        cast(
            Literal["current-industry-archive-reference@v1"],
            reference["contract_version"],
        ),
        cast(str, reference["snapshot_identity_sha256"]),
        cast(str, reference["retained_identity_sha256"]),
    )


def current_price_context_request_from_canonical_json_bytes_v2(
    raw: bytes,
) -> CurrentPriceContextRequestV2:
    """Decode only the closed canonical V2 owner request."""
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_REQUEST_BYTES:
        raise ValueError("current price context V2 request is invalid")
    try:
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if type(decoded) is not dict:
            raise ValueError
        value = cast(dict[str, object], decoded)
        if _canonical(value) != raw or set(value) != {
            "contract_version",
            "data_selection_time",
            "admission_deadline",
            "schedule_identity_sha256",
            "members",
            "questions",
            "industry_archive_reference",
            "execution_mode",
            "include_current_session",
        }:
            raise ValueError
        members = value["members"]
        questions = value["questions"]
        if type(members) is not list or type(questions) is not list:
            raise ValueError
        return CurrentPriceContextRequestV2(
            cast(
                Literal["current-price-context-request@v2"], value["contract_version"]
            ),
            _parse_instant(value["data_selection_time"]),
            _parse_instant(value["admission_deadline"]),
            cast(str, value["schedule_identity_sha256"]),
            tuple(_member_from_value(item) for item in cast(list[object], members)),
            tuple(cast(list[str], questions)),
            _reference_from_value(value["industry_archive_reference"]),
            cast(
                Literal["RETAINED_ONLY", "ACQUIRE_MISSING", "REFRESH_ONCE"],
                value["execution_mode"],
            ),
            cast(bool, value["include_current_session"]),
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        OverflowError,
        RecursionError,
        TypeError,
        ValueError,
    ):
        raise ValueError("current price context V2 request is invalid") from None


def _v1_request(request: CurrentPriceContextRequestV2) -> CurrentPriceContextRequestV1:
    return CurrentPriceContextRequestV1(
        "current-price-context-request@v1",
        request.data_selection_time,
        request.admission_deadline,
        request.schedule_identity_sha256,
        request.members,
        cast(Any, request.questions),
        request.industry_archive_reference,
    )


def _unavailable_member(
    position: int,
    member: CurrentPriceContextMemberV1,
    state: Literal["NOT_APPLICABLE", "NOT_REQUESTED", "UNAVAILABLE", "CONFLICTED"],
    reason: str,
) -> CurrentSessionPriceContextMemberV2:
    return CurrentSessionPriceContextMemberV2(
        position,
        member.isin,
        "NSE",
        member.effective_symbol,
        state,
        None,
        reason,
    )


def _uniform_current_session(
    request: CurrentPriceContextRequestV2,
    state: Literal["NOT_APPLICABLE", "NOT_REQUESTED", "UNAVAILABLE", "CONFLICTED"],
    reason: str,
) -> tuple[CurrentSessionPriceContextMemberV2, ...]:
    return tuple(
        _unavailable_member(position, member, state, reason)
        for position, member in enumerate(request.members)
    )


def _read_current_session(  # noqa: C901 -- one bounded read/admission pass
    request: CurrentPriceContextRequestV2,
    storage_root: Path,
    *,
    control: CurrentRawInvocationControlV1,
    evidence_cutoff: datetime,
    inspection: CurrentRawAcquisitionResultV1,
    planning_witness: CurrentPriceContextPlanningWitnessV2,
    root_authority: RootAuthorityV1,
) -> tuple[CurrentSessionPriceContextMemberV2, ...]:
    if not request.include_current_session:
        return _uniform_current_session(request, "NOT_REQUESTED", "NOT_REQUESTED")
    lease = StorageRootLease.admit_read_authority(storage_root, root_authority)
    if lease is None:
        return _uniform_current_session(
            request, "UNAVAILABLE", "CALENDAR_PREREQUISITE_MISSING"
        )
    with lease:
        resolved = ScheduleEvidenceStore(storage_root, lease).resolve(
            request.schedule_identity_sha256, deadline=control
        )
        if resolved.schedule is None or resolved.schedule.as_of > evidence_cutoff:
            return _uniform_current_session(
                request, "UNAVAILABLE", "CALENDAR_PREREQUISITE_MISSING"
            )
        schedule = resolved.schedule
        active = next(
            (
                item
                for item in schedule.sessions
                if item.trade_date
                == request.data_selection_time.astimezone(_IST).date()
                and item.open_at <= request.data_selection_time < item.close_at
            ),
            None,
        )
        if active is None:
            return _uniform_current_session(
                request, "NOT_APPLICABLE", "CURRENT_SESSION_NOT_APPLICABLE"
            )
        if not planning_witness.completed_sessions:
            return _uniform_current_session(
                request, "UNAVAILABLE", "CALENDAR_PREREQUISITE_MISSING"
            )
        target = min(
            request.data_selection_time.replace(second=0, microsecond=0)
            - timedelta(minutes=1),
            active.close_at - timedelta(minutes=1),
        )
        if target < active.open_at:
            return _uniform_current_session(
                request, "UNAVAILABLE", "NO_FULLY_COMPLETED_MINUTE"
            )
        schedule_digest = open_month_schedule_digest(
            open_month_schedule_from_evidence(schedule)
        )
        results: list[CurrentSessionPriceContextMemberV2] = []
        plans = None if inspection.plan is None else cast(Any, inspection.plan).members
        with DuckDBCatalog(storage_root, read_only=True, lease=lease) as catalog:
            for position, member in enumerate(request.members):
                instrument_key = None if plans is None else plans[position].provider_key
                if instrument_key is None:
                    results.append(
                        _unavailable_member(
                            position,
                            member,
                            "UNAVAILABLE",
                            "PROVISIONAL_EVIDENCE_UNAVAILABLE",
                        )
                    )
                    continue
                metadata = catalog.latest_provisional_partition_for_security_id(
                    segment="NSE_EQ",
                    security_id=member.isin,
                    year=active.trade_date.year,
                    month=active.trade_date.month,
                    cutoff_lte=target,
                    published_at_lte=evidence_cutoff,
                    schedule_digest_sha256=schedule_digest,
                )
                if metadata is None:
                    results.append(
                        _unavailable_member(
                            position,
                            member,
                            "UNAVAILABLE",
                            "PROVISIONAL_EVIDENCE_UNAVAILABLE",
                        )
                    )
                    continue
                if (
                    metadata.security_id != member.isin
                    or metadata.instrument_key != instrument_key
                    or metadata.schedule_digest_sha256 != schedule_digest
                    or metadata.cutoff > target
                    or metadata.published_at > evidence_cutoff
                ):
                    results.append(
                        _unavailable_member(
                            position,
                            member,
                            "CONFLICTED",
                            "PROVISIONAL_EVIDENCE_CONFLICTED",
                        )
                    )
                    continue
                try:
                    rows = load_provisional_partition(storage_root, lease, metadata)
                except ProvisionalPartitionUnavailableV1:
                    results.append(
                        _unavailable_member(
                            position,
                            member,
                            "CONFLICTED",
                            "PROVISIONAL_EVIDENCE_CONFLICTED",
                        )
                    )
                    continue
                current_rows = tuple(
                    row
                    for row in rows
                    if active.open_at <= row.ts <= target
                    and row.ts.astimezone(_IST).date() == active.trade_date
                )
                expected = tuple(
                    active.open_at + timedelta(minutes=offset)
                    for offset in range(
                        int((target - active.open_at).total_seconds() // 60) + 1
                    )
                )
                if tuple(row.ts for row in current_rows) != expected or any(
                    row.source_version != "upstox-intraday-v3" for row in current_rows
                ):
                    results.append(
                        _unavailable_member(
                            position,
                            member,
                            "UNAVAILABLE",
                            "PROVISIONAL_EVIDENCE_STALE",
                        )
                    )
                    continue
                last = current_rows[-1]
                results.append(
                    CurrentSessionPriceContextMemberV2(
                        position,
                        member.isin,
                        "NSE",
                        member.effective_symbol,
                        "OBSERVED",
                        "PARTIAL_CURRENT_SESSION",
                        None,
                        last.ts,
                        format(Decimal(str(last.close)), "f"),
                        sum(row.volume for row in current_rows),
                        "upstox-intraday-v3",
                        metadata.checksum_sha256,
                        metadata.cutoff,
                        metadata.published_at,
                        max(
                            metadata.published_at,
                            *(row.ingested_at for row in current_rows),
                        ),
                    )
                )
            catalog.ensure_read_identity()
        control.ensure_live()
        return tuple(results)


def _current_session_cutoff_identities(
    request: CurrentPriceContextRequestV2,
    storage_root: Path,
    *,
    control: CurrentRawInvocationControlV1,
    evidence_cutoff: datetime,
    inspection: CurrentRawAcquisitionResultV1,
    root_authority: RootAuthorityV1,
) -> tuple[tuple[datetime, str] | None, ...]:
    """Read validated pre-pass provisional cutoffs without accepting stale rows."""
    unavailable: tuple[tuple[datetime, str] | None, ...] = (None,) * len(
        request.members
    )
    if not request.include_current_session or inspection.plan is None:
        return unavailable
    lease = StorageRootLease.admit_read_authority(storage_root, root_authority)
    if lease is None:
        return unavailable
    with lease:
        resolved = ScheduleEvidenceStore(storage_root, lease).resolve(
            request.schedule_identity_sha256, deadline=control
        )
        if resolved.schedule is None or resolved.schedule.as_of > evidence_cutoff:
            return unavailable
        active = next(
            (
                item
                for item in resolved.schedule.sessions
                if item.trade_date
                == request.data_selection_time.astimezone(_IST).date()
                and item.open_at + timedelta(minutes=1)
                <= request.data_selection_time
                < item.close_at
            ),
            None,
        )
        if active is None:
            return unavailable
        target = min(
            request.data_selection_time.replace(second=0, microsecond=0)
            - timedelta(minutes=1),
            active.close_at - timedelta(minutes=1),
        )
        schedule_digest = open_month_schedule_digest(
            open_month_schedule_from_evidence(resolved.schedule)
        )
        plans = cast(Any, inspection.plan).members
        identities: list[tuple[datetime, str] | None] = []
        with DuckDBCatalog(storage_root, read_only=True, lease=lease) as catalog:
            for position, member in enumerate(request.members):
                member_plan = plans[position]
                instrument_key = member_plan.provider_key
                metadata = catalog.latest_provisional_partition_for_security_id(
                    segment="NSE_EQ",
                    security_id=member.isin,
                    year=active.trade_date.year,
                    month=active.trade_date.month,
                    cutoff_lte=target,
                    published_at_lte=evidence_cutoff,
                    schedule_digest_sha256=schedule_digest,
                )
                if (
                    metadata is None
                    or instrument_key is None
                    or metadata.security_id != member.isin
                    or metadata.instrument_key != instrument_key
                    or metadata.schedule_digest_sha256 != schedule_digest
                    or not active.open_at <= metadata.cutoff <= target
                    or metadata.published_at > evidence_cutoff
                ):
                    identities.append(None)
                    continue
                try:
                    rows = load_provisional_partition(storage_root, lease, metadata)
                except ProvisionalPartitionUnavailableV1:
                    identities.append(None)
                    continue
                current_rows = tuple(
                    row
                    for row in rows
                    if active.open_at <= row.ts <= metadata.cutoff
                    and row.ts.astimezone(_IST).date() == active.trade_date
                )
                expected = tuple(
                    active.open_at + timedelta(minutes=offset)
                    for offset in range(
                        int((metadata.cutoff - active.open_at).total_seconds() // 60)
                        + 1
                    )
                )
                if tuple(row.ts for row in current_rows) != expected or any(
                    row.source_version != "upstox-intraday-v3" for row in current_rows
                ):
                    identities.append(None)
                    continue
                identities.append((metadata.cutoff, metadata.checksum_sha256))
            catalog.ensure_read_identity()
        control.ensure_live()
        return tuple(identities)


def _conflicted_positions(
    result: CurrentRawAcquisitionResultV1 | None,
) -> frozenset[int]:
    if result is None or result.accounting is None:
        return frozenset()
    return frozenset(
        position
        for position, slots in enumerate(result.accounting.members)
        if any(slot.reason == "CONFLICTED_EVIDENCE" for slot in slots)
    )


def _failed_current_positions(
    result: CurrentRawAcquisitionResultV1 | None,
) -> frozenset[int]:
    """Project a failed attempted current slot without rewriting retained bytes."""
    if result is None or result.accounting is None:
        return frozenset()
    return frozenset(
        position
        for position, slots in enumerate(result.accounting.members)
        if any(
            ":intraday:" in slot.key
            and slot.attempts == 1
            and slot.disposition.value
            not in {"RETAINED", "RETAINED_INCOMPLETE", "REUSED"}
            for slot in slots
        )
    )


def _root_identity_guard(storage_root: Path) -> RootAuthorityV1:
    """Capture exactly one invocation-owned authority, including true absence."""
    return StorageRootLease.capture_root_authority(storage_root)


def _ensure_root_identity(storage_root: Path, authority: RootAuthorityV1) -> None:
    try:
        StorageRootLease.ensure_root_authority(storage_root, authority)
    except StorageRootLeaseError:
        raise StorageRootLeaseError(
            "current price context V2 root authority unavailable"
        ) from None


class _CancellationClockV2:
    def __init__(
        self,
        clock: CurrentPriceContextClockV1,
        cancellation: CurrentRawCancellationV1 | None,
    ) -> None:
        self._clock = clock
        self._cancellation = cancellation
        self._cancelled = False

    def now(self) -> datetime:
        try:
            cancelled = (
                False
                if self._cancellation is None
                else self._cancellation.is_cancelled()
            )
            if type(cancelled) is not bool:
                raise ValueError("current price context V2 callback is invalid")
            self._cancelled = self._cancelled or cancelled
            if self._cancelled:
                raise CurrentRawInvocationStoppedV1("CANCELLATION_REQUESTED")
            return self._clock.now()
        except CurrentRawInvocationStoppedV1:
            raise
        except Exception as error:
            raise ValueError("current price context V2 callback is invalid") from error


def _accounting_slots(
    result: CurrentRawAcquisitionResultV1 | None,
) -> tuple[object, ...]:
    if result is None or result.accounting is None:
        return ()
    return (result.accounting.mapping,) + tuple(
        slot for member in result.accounting.members for slot in member
    )


def _merged_accounting_slots(
    *results: CurrentRawAcquisitionResultV1 | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for result in results:
        for opaque in _accounting_slots(result):
            slot = cast(Any, opaque)
            previous = merged.get(slot.key)
            if (
                previous is None
                or slot.attempts > previous.attempts
                or (
                    slot.attempts == previous.attempts == 0
                    and slot.disposition.value == "REUSED"
                    and previous.disposition.value != "REUSED"
                )
            ):
                # A current-session-only reinspection may mark an otherwise
                # reusable historical slot not required.  That must not erase
                # the completed-context provenance from the combined ledger.
                merged[slot.key] = slot
    return merged


def _acquisition_window(
    *results: CurrentRawAcquisitionResultV1 | None,
) -> tuple[datetime | None, datetime | None]:
    slots = tuple(
        slot for slot in _merged_accounting_slots(*results).values() if slot.attempts
    )
    if not slots:
        return None, None
    starts = tuple(slot.attempted_at for slot in slots)
    ends = tuple(slot.settled_at for slot in slots)
    if any(value is None for value in (*starts, *ends)):
        raise ValueError("current price context acquisition accounting is invalid")
    return min(cast(tuple[datetime, ...], starts)), max(
        cast(tuple[datetime, ...], ends)
    )


def _ledger_state(  # noqa: C901 -- closed source-state projection
    slot: Any,
    *,
    source: str,
    execution_mode: str,
    initial_source_cutoff: datetime | None = None,
    final_source_cutoff: datetime | None = None,
    current_observed: bool = True,
) -> str:
    disposition = slot.disposition.value
    if (
        slot.reason == "CONFLICTED_EVIDENCE"
        or disposition == "FAILED"
        and "CONFLICT" in str(slot.reason)
    ):
        return "CONFLICTED"
    if source == "CURRENT_SESSION":
        if not current_observed:
            return "UNAVAILABLE"
        if slot.attempts == 0:
            return "REUSED"
    if disposition == "REUSED":
        return "REUSED"
    if disposition in {"RETAINED", "RETAINED_INCOMPLETE"}:
        if source == "CURRENT_SESSION":
            if execution_mode == "ACQUIRE_MISSING":
                return "ACQUIRED"
            if execution_mode == "REFRESH_ONCE":
                if initial_source_cutoff is None:
                    return "ACQUIRED"
                if (
                    final_source_cutoff is not None
                    and final_source_cutoff > initial_source_cutoff
                ):
                    return "APPENDED"
                return "REFRESHED"
        return "ACQUIRED"
    return "UNAVAILABLE"


def _freshness_ledger(  # noqa: C901 -- finite source-by-source projection
    request: CurrentPriceContextRequestV2,
    completed: CurrentPriceContextResultV1,
    current_session: tuple[CurrentSessionPriceContextMemberV2, ...],
    completed_inspection: CurrentRawAcquisitionResultV1,
    current_inspection: CurrentRawAcquisitionResultV1,
    completed_acquisition: CurrentRawAcquisitionResultV1 | None,
    current_acquisition: CurrentRawAcquisitionResultV1 | None,
    initial_current_identities: tuple[tuple[datetime, str] | None, ...],
    planning_witness: CurrentPriceContextPlanningWitnessV2,
) -> tuple[CurrentPriceContextFreshnessEntryV2, ...]:
    entries: list[CurrentPriceContextFreshnessEntryV2] = [
        CurrentPriceContextFreshnessEntryV2(
            "CALENDAR",
            "calendar",
            None,
            None,
            None,
            request.schedule_identity_sha256,
            "REUSED" if completed.schedule_as_of is not None else "UNAVAILABLE",
            completed.schedule_as_of,
            None,
            None,
            None,
            0,
            0,
            "RETAINED_EXACT_CALENDAR",
        )
    ]
    accounts = _merged_accounting_slots(
        completed_inspection,
        current_inspection,
        completed_acquisition,
        current_acquisition,
    )
    public_plan = _expected_physical_plan(request, planning_witness)
    completed_plan_result = (
        completed_acquisition
        if completed_acquisition is not None and completed_acquisition.plan is not None
        else completed_inspection
    )
    current_plan_result = (
        current_acquisition
        if current_acquisition is not None and current_acquisition.plan is not None
        else current_inspection
    )
    mapping = accounts.get("mapping")
    mapping_state = (
        "UNAVAILABLE"
        if not planning_witness.completed_sessions
        else _ledger_state(
            mapping,
            source="MAPPING",
            execution_mode=request.execution_mode,
        )
        if mapping is not None
        else "UNAVAILABLE"
    )
    entries.append(
        CurrentPriceContextFreshnessEntryV2(
            "MAPPING",
            "mapping",
            None,
            None,
            None,
            None,
            cast(Any, mapping_state),
            None,
            None,
            None,
            None,
            0 if mapping is None else mapping.attempts,
            0 if mapping is None else int(mapping.completed),
            "SELECTION_DATE_MAPPING",
        )
    )
    for position, member in enumerate(request.members):
        completed_member = completed.members[position]
        completed_member_plan = None
        if completed_plan_result.plan is not None:
            completed_member_plan = cast(Any, completed_plan_result.plan).members[
                position
            ]
        physical = (
            ()
            if completed_member_plan is None
            else (
                *completed_member_plan.closed,
                completed_member_plan.current_history,
                completed_member_plan.action,
            )
        )
        expected_completed = tuple(
            entry
            for entry in public_plan
            if entry.position == position
            and entry.source in {"CLOSED_MONTH", "CURRENT_HISTORY", "CORPORATE_ACTION"}
        )
        available_physical = {
            (
                {
                    "CLOSED": "CLOSED_MONTH",
                    "CURRENT_HISTORY": "CURRENT_HISTORY",
                    "ACTION": "CORPORATE_ACTION",
                }[item.kind],
                "action"
                if item.key.rsplit(":", maxsplit=1)[-1] == "singleton"
                else item.key.rsplit(":", maxsplit=1)[-1],
            ): item
            for item in physical
            if item is not None
        }
        physical = tuple(
            available_physical.get(
                (entry.source, entry.slot),
                _PhysicalPlanSlotV2(
                    f"{position}:unavailable:{entry.slot}",
                    {
                        "CLOSED_MONTH": "CLOSED",
                        "CURRENT_HISTORY": "CURRENT_HISTORY",
                        "CORPORATE_ACTION": "ACTION",
                    }[entry.source],
                ),
            )
            for entry in expected_completed
        )
        emitted_sources: set[str] = set()
        completed_partition_plans = tuple(
            item
            for item in physical
            if item is not None and item.kind in {"CLOSED", "CURRENT_HISTORY"}
        )
        partition_admitted = completed_member.state == "OBSERVED"
        partition_evidence = (
            tuple(
                zip(
                    completed_member.partition_checksums,
                    completed_member.raw_source_times,
                    strict=True,
                )
            )
            if partition_admitted
            else ()
        )
        if partition_admitted and len(partition_evidence) != len(
            completed_partition_plans
        ):
            raise ValueError("completed partition freshness evidence is invalid")
        partition_index = 0
        for planned in (item for item in physical if item is not None):
            account = accounts.get(planned.key)
            logical_accounts = () if account is None else (account,)
            kind = planned.kind
            if kind == "CLOSED":
                source = "CLOSED_MONTH"
                correction = "IMMUTABLE_CLOSED_MONTH_REUSE"
                evidence = (
                    partition_evidence[partition_index]
                    if partition_index < len(partition_evidence)
                    else (None, None)
                )
                partition_index += 1
                physical_identity, partition_source = evidence
            elif kind == "CURRENT_HISTORY":
                source = "CURRENT_HISTORY"
                correction = "CURRENT_MONTH_IDENTICAL_OVERLAP_OR_INTRADAY_TO_HISTORICAL_FINALIZATION"
                evidence = (
                    partition_evidence[partition_index]
                    if partition_index < len(partition_evidence)
                    else (None, None)
                )
                partition_index += 1
                physical_identity, partition_source = evidence
            else:
                source = "CORPORATE_ACTION"
                correction = "LATEST_RETAINED_ACTION_AT_CUTOFF"
                physical_identity = completed_member.screen_identity_sha256
                partition_source = None
            slot = planned.key.rsplit(":", maxsplit=1)[-1]
            if (
                source == "CURRENT_HISTORY"
                and planning_witness.completed_sessions
                and planning_witness.completed_sessions[-1].trade_date
                == request.data_selection_time.astimezone(_IST).date()
            ):
                intraday_account = accounts.get(f"{position}:intraday:{slot}")
                if intraday_account is not None:
                    logical_accounts = (*logical_accounts, intraday_account)
            account_states = tuple(
                _ledger_state(
                    item, source=source, execution_mode=request.execution_mode
                )
                for item in logical_accounts
            )
            state = (
                "CONFLICTED"
                if "CONFLICTED" in account_states
                else "ACQUIRED"
                if "ACQUIRED" in account_states
                else "REUSED"
                if account_states and all(item == "REUSED" for item in account_states)
                else "REUSED"
                if not account_states
                and (
                    partition_admitted
                    and source in {"CLOSED_MONTH", "CURRENT_HISTORY"}
                    or source == "CORPORATE_ACTION"
                    and completed_member.screen_knowledge_at is not None
                )
                else "UNAVAILABLE"
            )
            if source in {"CLOSED_MONTH", "CURRENT_HISTORY"} and not partition_admitted:
                physical_identity = None
                partition_source = None
                state = "UNAVAILABLE"
            if (
                source == "CORPORATE_ACTION"
                and completed_member.screen_knowledge_at is None
            ):
                state = "UNAVAILABLE"
            emitted_sources.add(source)
            entries.append(
                CurrentPriceContextFreshnessEntryV2(
                    cast(Any, source),
                    slot if slot != "singleton" else "action",
                    position,
                    member.isin,
                    member.effective_symbol,
                    physical_identity,
                    cast(Any, state),
                    partition_source,
                    None,
                    None,
                    (
                        completed_member.screen_knowledge_at
                        if source == "CORPORATE_ACTION"
                        else None
                    ),
                    sum(item.attempts for item in logical_accounts),
                    sum(int(item.completed) for item in logical_accounts),
                    cast(Any, correction),
                )
            )

        current_member_plan = None
        if planning_witness.completed_sessions and current_plan_result.plan is not None:
            current_member_plan = cast(Any, current_plan_result.plan).members[position]
        intraday = None if current_member_plan is None else current_member_plan.intraday
        if intraday is not None:
            account = accounts.get(intraday.key)
            current = current_session[position]
            pre_identity = initial_current_identities[position]
            initial_cutoff = None if pre_identity is None else pre_identity[0]
            state = (
                _ledger_state(
                    account,
                    source="CURRENT_SESSION",
                    execution_mode=request.execution_mode,
                    initial_source_cutoff=initial_cutoff,
                    final_source_cutoff=current.source_cutoff,
                    current_observed=current.state == "OBSERVED",
                )
                if account is not None
                else "UNAVAILABLE"
            )
            emitted_sources.add("CURRENT_SESSION")
            entries.append(
                CurrentPriceContextFreshnessEntryV2(
                    "CURRENT_SESSION",
                    intraday.key.rsplit(":", maxsplit=1)[-1],
                    position,
                    member.isin,
                    member.effective_symbol,
                    current.partition_checksum_sha256,
                    cast(Any, state),
                    current.source_cutoff,
                    initial_cutoff if current.state == "OBSERVED" else None,
                    current.published_at,
                    current.known_at,
                    0 if account is None else account.attempts,
                    0 if account is None else int(account.completed),
                    "CURRENT_SESSION_IDENTICAL_OVERLAP_APPEND_OR_CONFLICT",
                )
            )
        fallback_current_slot = next(
            entry.slot
            for entry in public_plan
            if entry.source == "CURRENT_SESSION" and entry.position == position
        )
        for source, slot, correction in (
            ("CORPORATE_ACTION", "action", "LATEST_RETAINED_ACTION_AT_CUTOFF"),
            (
                "CURRENT_SESSION",
                fallback_current_slot,
                "CURRENT_SESSION_IDENTICAL_OVERLAP_APPEND_OR_CONFLICT",
            ),
        ):
            if source in emitted_sources:
                continue
            entries.append(
                CurrentPriceContextFreshnessEntryV2(
                    cast(Any, source),
                    slot,
                    position,
                    member.isin,
                    member.effective_symbol,
                    None,
                    "NOT_REQUESTED"
                    if source == "CURRENT_SESSION"
                    and not request.include_current_session
                    else "CONFLICTED"
                    if source == "CURRENT_SESSION"
                    and current_session[position].state == "CONFLICTED"
                    else "UNAVAILABLE",
                    None,
                    None,
                    None,
                    None,
                    0,
                    0,
                    cast(Any, correction),
                )
            )
    reference = request.industry_archive_reference
    entries.append(
        CurrentPriceContextFreshnessEntryV2(
            "INDUSTRY",
            "industry",
            None,
            None,
            None,
            None if reference is None else reference.retained_identity_sha256,
            (
                "NOT_REQUESTED"
                if reference is None
                else "REUSED"
                if completed.industry_evidence_state == "OBSERVED"
                else "CONFLICTED"
                if completed.industry_evidence_state == "CONFLICTED"
                else "UNAVAILABLE"
            ),
            None,
            None,
            None,
            completed.industry_known_at,
            0,
            0,
            "RETAINED_ONLY_EXACT_INDUSTRY",
        )
    )
    return tuple(entries)


def research_current_price_context_v2(
    request: CurrentPriceContextRequestV2,
    storage_root: Path,
    *,
    clock: CurrentPriceContextClockV1 | None = None,
    cancellation: CurrentRawCancellationV1 | None = None,
) -> CurrentPriceContextResultV2:
    """Execute one bounded pass and keep provisional facts separate."""
    if (
        type(request) is not CurrentPriceContextRequestV2
        or (clock is not None and not callable(getattr(clock, "now", None)))
        or (
            cancellation is not None
            and not callable(getattr(cancellation, "is_cancelled", None))
        )
    ):
        raise ValueError("current price context V2 input is invalid")
    base_clock = _SystemClock() if clock is None else clock
    trusted_clock = _CancellationClockV2(base_clock, cancellation)
    inspection_time = trusted_clock.now()
    if (
        not _utc(inspection_time)
        or not request.data_selection_time
        <= inspection_time
        < request.admission_deadline
        or inspection_time.astimezone(_IST).date()
        != request.data_selection_time.astimezone(_IST).date()
    ):
        raise ValueError("current price context V2 deadline exceeded")
    runtime_identity = current_price_context_runtime_code_identity_v2()
    current_price_context_runtime_code_identity_v1()
    root_identity = _root_identity_guard(storage_root)
    _ensure_root_identity(storage_root, root_identity)
    request_v1 = _v1_request(request)
    raw_request = CurrentRawPriceContextInputV1(
        request_v1.request_identity_sha256,
        request.data_selection_time,
        request.admission_deadline,
        request.schedule_identity_sha256,
        request.members,
    )
    planning_control = CurrentRawInvocationControlV1(
        trusted_clock,
        selection=request.data_selection_time,
        deadline=request.admission_deadline,
        cancellation=None,
        accounting_clock=base_clock,
    )
    planning_witness = _planning_witness_from_retained(
        request,
        raw_request,
        storage_root,
        planning_control,
        root_identity,
    )
    _ensure_root_identity(storage_root, root_identity)
    inspection_control = CurrentRawInvocationControlV1(
        trusted_clock,
        selection=request.data_selection_time,
        deadline=request.admission_deadline,
        cancellation=None,
        accounting_clock=base_clock,
    )
    completed_inspection = inspect_current_raw_evidence_v1(
        raw_request,
        storage_root,
        control=inspection_control,
        root_authority=root_identity,
    )
    _ensure_root_identity(storage_root, root_identity)
    current_inspection = (
        inspect_current_raw_evidence_v1(
            raw_request,
            storage_root,
            control=inspection_control,
            include_current_session=True,
            root_authority=root_identity,
        )
        if request.include_current_session
        else completed_inspection
    )
    _ensure_root_identity(storage_root, root_identity)
    prepass_cutoff = trusted_clock.now()
    prepass_control = CurrentRawInvocationControlV1(
        trusted_clock,
        selection=request.data_selection_time,
        deadline=request.admission_deadline,
        cancellation=None,
        accounting_clock=base_clock,
    )
    initial_current_identities = _current_session_cutoff_identities(
        request,
        storage_root,
        control=prepass_control,
        evidence_cutoff=prepass_cutoff,
        inspection=current_inspection,
        root_authority=root_identity,
    )
    _ensure_root_identity(storage_root, root_identity)
    acquisition_started_at: datetime | None = None
    acquisition_completed_at: datetime | None = None
    completed_acquisition: CurrentRawAcquisitionResultV1 | None = None
    current_acquisition: CurrentRawAcquisitionResultV1 | None = None
    completed_acquisition_calls = 0
    if request.execution_mode != "RETAINED_ONLY":
        _ensure_root_identity(storage_root, root_identity)
        acquisition_started_at = trusted_clock.now()
        completed_control = CurrentRawInvocationControlV1(
            trusted_clock,
            selection=request.data_selection_time,
            deadline=request.admission_deadline,
            cancellation=None,
            accounting_clock=base_clock,
        )
        completed_acquisition = acquire_missing_current_raw_evidence_v1(
            raw_request,
            storage_root,
            control=completed_control,
            root_authority=root_identity,
        )
        completed_acquisition_calls = completed_acquisition.provider_calls
        if (
            request.include_current_session
            and completed_acquisition.outcome
            not in {"STOPPED", "CALENDAR_PREREQUISITE_MISSING"}
            and completed_acquisition_calls < min(5 * len(request.members) + 1, 251)
        ):
            current_control = CurrentRawInvocationControlV1(
                trusted_clock,
                selection=request.data_selection_time,
                deadline=request.admission_deadline,
                cancellation=None,
                accounting_clock=base_clock,
            )
            current_acquisition = acquire_missing_current_raw_evidence_v1(
                raw_request,
                storage_root,
                control=current_control,
                include_current_session=True,
                refresh_once=request.execution_mode == "REFRESH_ONCE",
                current_session_only=True,
                provider_call_budget=min(5 * len(request.members) + 1, 251)
                - completed_acquisition_calls,
                root_authority=root_identity,
            )
        acquisition_completed_at = trusted_clock.now()
        _ensure_root_identity(storage_root, root_identity)
    completed = _research_current_price_context_v1(
        request_v1,
        storage_root,
        acquire_missing=False,
        clock=trusted_clock,
        root_authority=root_identity,
    )
    _ensure_root_identity(storage_root, root_identity)
    evidence_cutoff = trusted_clock.now()
    if evidence_cutoff >= request.admission_deadline:
        raise ValueError("current price context V2 deadline exceeded")
    control = CurrentRawInvocationControlV1(
        trusted_clock,
        selection=request.data_selection_time,
        deadline=request.admission_deadline,
        cancellation=None,
        accounting_clock=base_clock,
    )
    final_current_inspection = (
        current_acquisition
        if current_acquisition is not None and current_acquisition.plan is not None
        else current_inspection
    )
    current_session = _read_current_session(
        request,
        storage_root,
        control=control,
        evidence_cutoff=evidence_cutoff,
        inspection=final_current_inspection,
        planning_witness=planning_witness,
        root_authority=root_identity,
    )
    _ensure_root_identity(storage_root, root_identity)
    conflicted = _conflicted_positions(current_acquisition)
    failed_current = _failed_current_positions(current_acquisition)
    if conflicted or failed_current:
        current_session = tuple(
            _unavailable_member(
                item.position,
                request.members[item.position],
                "CONFLICTED",
                "PROVISIONAL_EVIDENCE_CONFLICTED",
            )
            if item.position in conflicted
            else _unavailable_member(
                item.position,
                request.members[item.position],
                "UNAVAILABLE",
                "PROVISIONAL_EVIDENCE_UNAVAILABLE",
            )
            if item.position in failed_current
            else item
            for item in current_session
        )
    control.ensure_live()
    ledger = _freshness_ledger(
        request,
        completed,
        current_session,
        completed_inspection,
        current_inspection,
        completed_acquisition,
        current_acquisition,
        initial_current_identities,
        planning_witness,
    )
    attempted = sum(item.provider_calls_attempted for item in ledger)
    completed_calls = sum(item.provider_calls_completed for item in ledger)
    acquisition_started_at, acquisition_completed_at = _acquisition_window(
        completed_inspection,
        current_inspection,
        completed_acquisition,
        current_acquisition,
    )
    reused = sum(item.state == "REUSED" for item in ledger)
    refreshed = sum(item.state in {"REFRESHED", "APPENDED"} for item in ledger)
    _ensure_root_identity(storage_root, root_identity)
    final_planning_control = CurrentRawInvocationControlV1(
        trusted_clock,
        selection=request.data_selection_time,
        deadline=request.admission_deadline,
        cancellation=None,
        accounting_clock=base_clock,
    )
    if (
        _planning_witness_from_retained(
            request,
            raw_request,
            storage_root,
            final_planning_control,
            root_identity,
        )
        != planning_witness
    ):
        raise ValueError("current price context V2 planning witness changed")
    result = CurrentPriceContextResultV2(
        _RESULT_CONTRACT,
        request.request_identity_sha256,
        request.execution_mode,
        request.data_selection_time,
        request.admission_deadline,
        request.schedule_identity_sha256,
        request.members,
        request.questions,
        request.industry_archive_reference,
        request.include_current_session,
        inspection_time,
        acquisition_started_at,
        acquisition_completed_at,
        evidence_cutoff,
        attempted,
        completed_calls,
        min(5 * len(request.members) + 1, 251),
        reused,
        refreshed,
        completed,
        current_session,
        planning_witness,
        _expected_physical_plan(request, planning_witness),
        ledger,
        runtime_identity,
    )
    final_planning_control.ensure_live()
    _ensure_root_identity(storage_root, root_identity)
    return result


def _planning_session_from_value(value: object) -> CurrentPriceContextPlanningSessionV2:
    if type(value) is not dict:
        raise ValueError
    item = cast(dict[str, object], value)
    if set(item) != {"trade_date", "open_at", "close_at", "kind"}:
        raise ValueError
    return CurrentPriceContextPlanningSessionV2(
        _parse_date(item["trade_date"]),
        _parse_instant(item["open_at"]),
        _parse_instant(item["close_at"]),
        cast(Literal["REGULAR", "SPECIAL"], item["kind"]),
    )


def _planning_witness_from_value(value: object) -> CurrentPriceContextPlanningWitnessV2:
    if type(value) is not dict:
        raise ValueError
    item = cast(dict[str, object], value)
    if set(item) != {"schedule_as_of", "completed_sessions", "selection_session"}:
        raise ValueError
    sessions = item["completed_sessions"]
    if type(sessions) is not list:
        raise ValueError
    selection = item["selection_session"]
    return CurrentPriceContextPlanningWitnessV2(
        None
        if item["schedule_as_of"] is None
        else _parse_instant(item["schedule_as_of"]),
        tuple(
            _planning_session_from_value(row) for row in cast(list[object], sessions)
        ),
        None if selection is None else _planning_session_from_value(selection),
    )


def _physical_plan_entry_from_value(
    value: object,
) -> CurrentPriceContextPhysicalPlanEntryV2:
    if type(value) is not dict:
        raise ValueError
    item = cast(dict[str, object], value)
    if set(item) != {"source", "slot", "position"}:
        raise ValueError
    return CurrentPriceContextPhysicalPlanEntryV2(
        cast(Any, item["source"]),
        cast(str, item["slot"]),
        cast(int | None, item["position"]),
    )


def _freshness_entry_from_value(
    value: object,
) -> CurrentPriceContextFreshnessEntryV2:
    if type(value) is not dict:
        raise ValueError
    item = cast(dict[str, object], value)
    if set(item) != {
        field.name for field in fields(CurrentPriceContextFreshnessEntryV2)
    }:
        raise ValueError

    def optional_instant(name: str) -> datetime | None:
        raw = item[name]
        return None if raw is None else _parse_instant(raw)

    return CurrentPriceContextFreshnessEntryV2(
        cast(Any, item["source"]),
        cast(str, item["slot"]),
        cast(int | None, item["position"]),
        cast(str | None, item["isin"]),
        cast(str | None, item["effective_symbol"]),
        cast(str | None, item["physical_identity_sha256"]),
        cast(Any, item["state"]),
        optional_instant("source_cutoff"),
        optional_instant("prior_source_cutoff"),
        optional_instant("published_at"),
        optional_instant("known_at"),
        cast(int, item["provider_calls_attempted"]),
        cast(int, item["provider_calls_completed"]),
        cast(Any, item["correction_rule"]),
    )


def current_price_context_result_from_canonical_json_bytes_v2(
    raw: bytes,
) -> CurrentPriceContextResultV2:
    """Decode and revalidate one bounded V2 response."""
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_RESULT_BYTES:
        raise ValueError("current price context V2 result is invalid")
    try:
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if type(decoded) is not dict:
            raise ValueError
        value = cast(dict[str, object], decoded)
        if _canonical(value) != raw:
            raise ValueError
        expected = {field.name for field in fields(CurrentPriceContextResultV2)}
        if set(value) != expected:
            raise ValueError
        completed_raw = _canonical(value["completed_context"])
        completed = current_price_context_result_from_canonical_json_bytes_v1(
            completed_raw
        )
        current = value["current_session"]
        member_values = value["request_members"]
        question_values = value["questions"]
        ledger_values = value["freshness_ledger"]
        physical_plan_values = value["physical_plan"]
        planning_witness_value = value["planning_witness"]
        if (
            type(current) is not list
            or type(member_values) is not list
            or type(question_values) is not list
            or type(ledger_values) is not list
            or type(physical_plan_values) is not list
            or type(planning_witness_value) is not dict
        ):
            raise ValueError
        provisional = tuple(
            _current_session_member_from_value(item)
            for item in cast(list[object], current)
        )
        request_members = tuple(
            _member_from_value(item) for item in cast(list[object], member_values)
        )
        planning_witness = _planning_witness_from_value(
            cast(dict[str, object], planning_witness_value)
        )
        physical_plan = tuple(
            _physical_plan_entry_from_value(item)
            for item in cast(list[object], physical_plan_values)
        )
        freshness_ledger = tuple(
            _freshness_entry_from_value(item)
            for item in cast(list[object], ledger_values)
        )
        result = CurrentPriceContextResultV2(
            cast(Literal["current-price-context@v2"], value["contract_version"]),
            cast(str, value["request_identity_sha256"]),
            cast(
                Literal["RETAINED_ONLY", "ACQUIRE_MISSING", "REFRESH_ONCE"],
                value["execution_mode"],
            ),
            _parse_instant(value["data_selection_time"]),
            _parse_instant(value["admission_deadline"]),
            cast(str, value["schedule_identity_sha256"]),
            request_members,
            tuple(cast(list[str], question_values)),
            _reference_from_value(value["industry_archive_reference"]),
            cast(bool, value["include_current_session"]),
            _parse_instant(value["inspection_time"]),
            None
            if value["acquisition_started_at"] is None
            else _parse_instant(value["acquisition_started_at"]),
            None
            if value["acquisition_completed_at"] is None
            else _parse_instant(value["acquisition_completed_at"]),
            _parse_instant(value["evidence_cutoff"]),
            cast(int, value["provider_calls_attempted"]),
            cast(int, value["provider_calls_completed"]),
            cast(int, value["provider_call_budget"]),
            cast(int, value["reused_physical_objects"]),
            cast(int, value["refreshed_physical_objects"]),
            completed,
            provisional,
            planning_witness,
            physical_plan,
            freshness_ledger,
            cast(str, value["runtime_code_identity_sha256"]),
            cast(str, value["result_identity_sha256"]),
        )
        if result.canonical_json_bytes() != raw:
            raise ValueError
        return result
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        DecimalException,
        OverflowError,
        RecursionError,
        TypeError,
        ValueError,
    ):
        raise ValueError("current price context V2 result is invalid") from None


def _current_session_member_from_value(
    value: object,
) -> CurrentSessionPriceContextMemberV2:
    if type(value) is not dict:
        raise ValueError
    item = cast(dict[str, object], value)
    if set(item) != {
        field.name for field in fields(CurrentSessionPriceContextMemberV2)
    }:
        raise ValueError
    return CurrentSessionPriceContextMemberV2(
        cast(int, item["position"]),
        cast(str, item["isin"]),
        cast(Literal["NSE"], item["exchange"]),
        cast(str, item["effective_symbol"]),
        cast(
            Literal[
                "OBSERVED",
                "NOT_APPLICABLE",
                "NOT_REQUESTED",
                "UNAVAILABLE",
                "CONFLICTED",
            ],
            item["state"],
        ),
        cast(Literal["PARTIAL_CURRENT_SESSION"] | None, item["label"]),
        cast(str | None, item["reason"]),
        None
        if item["last_completed_minute"] is None
        else _parse_instant(item["last_completed_minute"]),
        cast(str | None, item["observed_price"]),
        cast(int | None, item["cumulative_source_volume"]),
        cast(Literal["upstox-intraday-v3"] | None, item["source_version"]),
        cast(str | None, item["partition_checksum_sha256"]),
        None
        if item["source_cutoff"] is None
        else _parse_instant(item["source_cutoff"]),
        None if item["published_at"] is None else _parse_instant(item["published_at"]),
        None if item["known_at"] is None else _parse_instant(item["known_at"]),
    )
