"""Closed public API for independent current raw price context (Issue #188)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    read_retained_current_raw_context_v1,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.research_packet.current_price_context_runtime_identity_manifest import (
    CURRENT_PRICE_CONTEXT_RUNTIME_SOURCE_SHA256_V1,
)

_REQUEST_CONTRACT = "current-price-context-request@v1"
_RESULT_CONTRACT = "current-price-context@v1"
_QUESTIONS = (
    "RAW_MARKET_STRUCTURE",
    "RAW_20_SESSION_DIRECTION",
    "RAW_COHORT_BREADTH",
    "RAW_INDUSTRY_PARTICIPATION",
)


class CurrentPriceContextClockV1(Protocol):
    def now(self) -> datetime: ...


def current_price_context_runtime_code_identity_v1() -> str:
    """Verify the reviewed source map before exposing a public result."""
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in CURRENT_PRICE_CONTEXT_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("current price context runtime identity is invalid")
        observed[relative] = actual
    return _digest_value(observed)


@dataclass(frozen=True, slots=True)
class CurrentPriceContextMemberV1:
    isin: str
    exchange: Literal["NSE"]
    instrument_type: Literal["EQUITY"]
    segment: Literal["EQ"]
    effective_symbol: str
    valid_from: date
    valid_through: date

    def __post_init__(self) -> None:
        if (
            type(self.isin) is not str
            or len(self.isin) != 12
            or not self.isin.startswith("INE")
            or self.exchange != "NSE"
            or self.instrument_type != "EQUITY"
            or self.segment != "EQ"
            or type(self.effective_symbol) is not str
            or not self.effective_symbol
            or type(self.valid_from) is not date
            or type(self.valid_through) is not date
            or self.valid_from > self.valid_through
        ):
            raise ValueError("current price context member is invalid")


@dataclass(frozen=True, slots=True)
class CurrentIndustryArchiveReferenceV1:
    contract_version: Literal["current-industry-archive-reference@v1"]
    snapshot_identity_sha256: str
    retained_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            self.contract_version != "current-industry-archive-reference@v1"
            or not _digest(self.snapshot_identity_sha256)
            or not _digest(self.retained_identity_sha256)
        ):
            raise ValueError("current Industry archive reference is invalid")


@dataclass(frozen=True, slots=True)
class CurrentPriceContextRequestV1:
    contract_version: Literal["current-price-context-request@v1"]
    data_selection_time: datetime
    admission_deadline: datetime
    schedule_identity_sha256: str
    members: tuple[CurrentPriceContextMemberV1, ...]
    questions: tuple[
        Literal[
            "RAW_MARKET_STRUCTURE",
            "RAW_20_SESSION_DIRECTION",
            "RAW_COHORT_BREADTH",
            "RAW_INDUSTRY_PARTICIPATION",
        ],
        ...,
    ]
    industry_archive_reference: CurrentIndustryArchiveReferenceV1 | None
    request_identity_sha256: str = ""

    def __post_init__(self) -> None:
        if (
            self.contract_version != _REQUEST_CONTRACT
            or not _utc(self.data_selection_time)
            or not _utc(self.admission_deadline)
            or not self.data_selection_time < self.admission_deadline
            or self.admission_deadline - self.data_selection_time
            > timedelta(minutes=30)
            or not _digest(self.schedule_identity_sha256)
            or type(self.members) is not tuple
            or not 1 <= len(self.members) <= 50
            or any(
                type(member) is not CurrentPriceContextMemberV1
                for member in self.members
            )
            or len({member.isin for member in self.members}) != len(self.members)
            or self.questions != _QUESTIONS
            or type(self.industry_archive_reference)
            not in (CurrentIndustryArchiveReferenceV1, type(None))
        ):
            raise ValueError("current price context request is invalid")
        identity = self.identity_of(self)
        if self.request_identity_sha256 not in ("", identity):
            raise ValueError("current price context request identity is invalid")
        object.__setattr__(self, "request_identity_sha256", identity)

    @staticmethod
    def identity_of(value: CurrentPriceContextRequestV1) -> str:
        if type(value) is not CurrentPriceContextRequestV1:
            raise ValueError("current price context request is invalid")
        return _digest_value(
            {
                "contract_version": value.contract_version,
                "data_selection_time": value.data_selection_time,
                "admission_deadline": value.admission_deadline,
                "schedule_identity_sha256": value.schedule_identity_sha256,
                "members": value.members,
                "questions": value.questions,
                "industry_archive_reference": value.industry_archive_reference,
            }
        )


@dataclass(frozen=True, slots=True)
class CurrentPriceContextFeatureV1:
    question: str
    state: Literal[
        "OBSERVED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE", "NOT_ATTEMPTED"
    ]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.question not in _QUESTIONS
            or (self.state == "OBSERVED" and self.reasons)
            or (self.state != "OBSERVED" and not self.reasons)
        ):
            raise ValueError("current price context feature is invalid")


@dataclass(frozen=True, slots=True)
class CurrentPriceContextResultV1:
    contract_version: Literal["current-price-context@v1"]
    request_identity_sha256: str
    schedule_identity_sha256: str
    ordered_selection_identity_sha256: str
    acquisition_mode: Literal["RETAINED_ONLY", "ACQUIRE_MISSING"]
    acquisition_outcome: Literal["NOT_ATTEMPTED", "CALENDAR_PREREQUISITE_MISSING"]
    features: tuple[CurrentPriceContextFeatureV1, ...]
    limitations: tuple[str, ...]
    result_identity_sha256: str = ""

    def __post_init__(self) -> None:
        if (
            self.contract_version != _RESULT_CONTRACT
            or not _digest(self.request_identity_sha256)
            or not _digest(self.schedule_identity_sha256)
            or not _digest(self.ordered_selection_identity_sha256)
            or type(self.features) is not tuple
            or tuple(item.question for item in self.features) != _QUESTIONS
            or any(
                type(item) is not CurrentPriceContextFeatureV1 for item in self.features
            )
            or not self.limitations
        ):
            raise ValueError("current price context result is invalid")
        identity = _digest_value(_without_identity(self))
        if self.result_identity_sha256 not in ("", identity):
            raise ValueError("current price context result identity is invalid")
        object.__setattr__(self, "result_identity_sha256", identity)

    def canonical_json_bytes(self) -> bytes:
        raw = _canonical(_wire(self))
        if len(raw) > 1_048_576:
            raise ValueError("current price context result exceeds its bound")
        return raw


def current_price_context_request_from_canonical_json_bytes_v1(
    raw: bytes,
) -> CurrentPriceContextRequestV1:
    """Decode only the closed canonical owner-supplied request representation."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 64 * 1024:
        raise ValueError("current price context request is invalid")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("current price context request is invalid") from None
    if type(decoded) is not dict:
        raise ValueError("current price context request is invalid")
    value = cast(dict[str, object], decoded)
    if _canonical(value) != raw:
        raise ValueError("current price context request is invalid")
    if set(value) != {
        "contract_version",
        "data_selection_time",
        "admission_deadline",
        "schedule_identity_sha256",
        "members",
        "questions",
        "industry_archive_reference",
    }:
        raise ValueError("current price context request is invalid")
    try:
        reference = _reference_from_value(value["industry_archive_reference"])
        members = _members_from_value(value["members"])
        questions = value["questions"]
        if type(questions) is not list:
            raise ValueError
        question_values = cast(list[object], questions)
        return CurrentPriceContextRequestV1(
            contract_version=cast(
                Literal["current-price-context-request@v1"], value["contract_version"]
            ),
            data_selection_time=_parse_instant(value["data_selection_time"]),
            admission_deadline=_parse_instant(value["admission_deadline"]),
            schedule_identity_sha256=cast(str, value["schedule_identity_sha256"]),
            members=members,
            questions=cast(
                tuple[
                    Literal[
                        "RAW_MARKET_STRUCTURE",
                        "RAW_20_SESSION_DIRECTION",
                        "RAW_COHORT_BREADTH",
                        "RAW_INDUSTRY_PARTICIPATION",
                    ],
                    ...,
                ],
                tuple(question_values),
            ),
            industry_archive_reference=reference,
        )
    except (KeyError, TypeError, ValueError):
        raise ValueError("current price context request is invalid") from None


def research_current_price_context_v1(
    request: CurrentPriceContextRequestV1,
    storage_root: Path,
    *,
    acquire_missing: bool = False,
    clock: CurrentPriceContextClockV1 | None = None,
) -> CurrentPriceContextResultV1:
    """Return admitted facts or typed withheld facts without hidden effects."""
    if type(request) is not CurrentPriceContextRequestV1:
        raise ValueError("current price context input is invalid")
    if type(acquire_missing) is not bool or (
        clock is not None and not hasattr(clock, "now")
    ):
        raise ValueError("current price context options are invalid")
    # The retained-only path intentionally never constructs a token provider.
    current_price_context_runtime_code_identity_v1()
    retained = read_retained_current_raw_context_v1(
        storage_root, schedule_identity_sha256=request.schedule_identity_sha256
    )
    reason = retained.reason or "RAW_CONTEXT_UNAVAILABLE"
    acquisition_mode: Literal["RETAINED_ONLY", "ACQUIRE_MISSING"] = (
        "ACQUIRE_MISSING" if acquire_missing else "RETAINED_ONLY"
    )
    acquisition_outcome: Literal["NOT_ATTEMPTED", "CALENDAR_PREREQUISITE_MISSING"] = (
        "CALENDAR_PREREQUISITE_MISSING" if acquire_missing else "NOT_ATTEMPTED"
    )
    return CurrentPriceContextResultV1(
        contract_version=_RESULT_CONTRACT,
        request_identity_sha256=request.request_identity_sha256,
        schedule_identity_sha256=request.schedule_identity_sha256,
        ordered_selection_identity_sha256=_digest_value(request.members),
        acquisition_mode=acquisition_mode,
        acquisition_outcome=acquisition_outcome,
        features=tuple(
            CurrentPriceContextFeatureV1(question, retained.state, (reason,))
            for question in _QUESTIONS
        ),
        limitations=("RETAINED_CALENDAR_AND_RAW_EVIDENCE_REQUIRED",),
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
        contract_version=cast(
            Literal["current-industry-archive-reference@v1"],
            reference["contract_version"],
        ),
        snapshot_identity_sha256=cast(str, reference["snapshot_identity_sha256"]),
        retained_identity_sha256=cast(str, reference["retained_identity_sha256"]),
    )


def _members_from_value(value: object) -> tuple[CurrentPriceContextMemberV1, ...]:
    if type(value) is not list:
        raise ValueError
    result: list[CurrentPriceContextMemberV1] = []
    for item in cast(list[object], value):
        if type(item) is not dict:
            raise ValueError
        member = cast(dict[str, object], item)
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
        result.append(
            CurrentPriceContextMemberV1(
                isin=cast(str, member["isin"]),
                exchange=cast(Literal["NSE"], member["exchange"]),
                instrument_type=cast(Literal["EQUITY"], member["instrument_type"]),
                segment=cast(Literal["EQ"], member["segment"]),
                effective_symbol=cast(str, member["effective_symbol"]),
                valid_from=date.fromisoformat(cast(str, member["valid_from"])),
                valid_through=date.fromisoformat(cast(str, member["valid_through"])),
            )
        )
    return tuple(result)


def _parse_instant(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError("current price context timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise ValueError("current price context timestamp is invalid") from None
    if parsed.tzinfo is not UTC:
        raise ValueError("current price context timestamp is invalid")
    return parsed


def _utc(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is UTC


def _digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _wire(value: object) -> object:
    if type(value) is datetime:
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if type(value) is date:
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        instance = cast(Any, value)
        return {
            str(item.name): _wire(getattr(instance, item.name))
            for item in fields(instance)
        }
    if type(value) is tuple:
        return [_wire(item) for item in cast(tuple[object, ...], value)]
    if type(value) is dict:
        return {
            str(key): _wire(item)
            for key, item in cast(dict[object, object], value).items()
        }
    return value


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _digest_value(value: object) -> str:
    return hashlib.sha256(_canonical(_wire(value))).hexdigest()


def _without_identity(value: CurrentPriceContextResultV1) -> dict[str, object]:
    return {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if item.name != "result_identity_sha256"
    }
