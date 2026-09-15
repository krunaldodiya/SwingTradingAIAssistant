"""Closed public API for independent current raw price context (Issue #188)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.market_data.current_industry_archive_reader import (
    AdmittedCurrentIndustryProjectionV1,
    CurrentIndustryReadFailureV1,
    read_current_industry_archive_exact_v1,
)
from swing_trading_ai_assistant.market_data.current_industry_archive_reader import (
    CurrentIndustryArchiveReferenceV1 as ArchivedIndustryReferenceV1,
)
from swing_trading_ai_assistant.market_data.current_raw_acquisition import (
    acquire_missing_current_raw_evidence_v1,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextClockV1,
    CurrentPriceContextMemberV1,
    CurrentRawInvocationControlV1,
    CurrentRawPriceContextInputV1,
    read_retained_current_raw_context_v1,
    validate_admitted_current_raw_context_v1,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.research_packet.current_price_context_runtime_identity_manifest import (
    CURRENT_PRICE_CONTEXT_RUNTIME_SOURCE_SHA256_V1,
)
from swing_trading_ai_assistant.sector_analysis.current_raw_industry_participation import (
    CurrentRawIndustryGroupV1,
    RawIndustryDirectionV1,
    reduce_current_raw_industry_participation_v1,
)

_REQUEST_CONTRACT = "current-price-context-request@v1"
_RESULT_CONTRACT = "current-price-context@v1"
_QUESTIONS = (
    "RAW_MARKET_STRUCTURE",
    "RAW_20_SESSION_DIRECTION",
    "RAW_COHORT_BREADTH",
    "RAW_INDUSTRY_PARTICIPATION",
)
_IST = ZoneInfo("Asia/Kolkata")
_MAX_REQUEST_BYTES = 64 * 1024
_MAX_RESULT_BYTES = 1_048_576


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
            or self.data_selection_time.astimezone(_IST).date()
            != self.admission_deadline.astimezone(_IST).date()
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
        if any(
            not member.valid_from
            <= self.data_selection_time.astimezone(_IST).date()
            <= member.valid_through
            for member in self.members
        ):
            raise ValueError("current price context member is not valid at selection")
        if self.request_identity_sha256 not in ("", identity):
            raise ValueError("current price context request identity is invalid")
        object.__setattr__(self, "request_identity_sha256", identity)
        if len(_canonical(_wire(_without_request_identity(self)))) > _MAX_REQUEST_BYTES:
            raise ValueError("current price context request exceeds its bound")

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
        "OBSERVED",
        "UNSUPPORTED",
        "DEPENDENCY_BLOCKED",
        "INSUFFICIENT_EVIDENCE",
        "NOT_ATTEMPTED",
    ]
    reasons: tuple[str, ...]
    support: Literal["SUPPORTED", "UNSUPPORTED"] = "SUPPORTED"
    readiness: Literal["READY", "WITHHELD"] = "WITHHELD"

    def __post_init__(self) -> None:
        if (
            self.question not in _QUESTIONS
            or self.support not in ("SUPPORTED", "UNSUPPORTED")
            or self.readiness not in ("READY", "WITHHELD")
            or (
                self.state == "OBSERVED" and (self.reasons or self.readiness != "READY")
            )
            or (
                self.state != "OBSERVED"
                and (not self.reasons or self.readiness != "WITHHELD")
            )
            or (self.state == "UNSUPPORTED") != (self.support == "UNSUPPORTED")
        ):
            raise ValueError("current price context feature is invalid")


@dataclass(frozen=True, slots=True)
class CurrentPriceContextResultV1:
    contract_version: Literal["current-price-context@v1"]
    request_identity_sha256: str
    schedule_identity_sha256: str
    ordered_selection_identity_sha256: str
    acquisition_mode: Literal["RETAINED_ONLY", "ACQUIRE_MISSING"]
    acquisition_outcome: Literal[
        "NOT_ATTEMPTED", "CALENDAR_PREREQUISITE_MISSING", "RETAINED_EVIDENCE_READY"
    ]
    features: tuple[CurrentPriceContextFeatureV1, ...]
    limitations: tuple[str, ...]
    runtime_code_identity_sha256: str
    industry_evidence_state: Literal[
        "OBSERVED", "NOT_ATTEMPTED", "INSUFFICIENT_EVIDENCE"
    ] = "NOT_ATTEMPTED"
    industry_groups: tuple[CurrentRawIndustryGroupV1, ...] = ()
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
            or not _digest(self.runtime_code_identity_sha256)
            or self.industry_evidence_state
            not in ("OBSERVED", "NOT_ATTEMPTED", "INSUFFICIENT_EVIDENCE")
            or type(self.industry_groups) is not tuple
            or any(
                type(item) is not CurrentRawIndustryGroupV1
                for item in self.industry_groups
            )
            or (self.industry_evidence_state == "OBSERVED")
            != bool(self.industry_groups)
        ):
            raise ValueError("current price context result is invalid")
        identity = _digest_value(_without_identity(self))
        if self.result_identity_sha256 not in ("", identity):
            raise ValueError("current price context result identity is invalid")
        object.__setattr__(self, "result_identity_sha256", identity)

    def canonical_json_bytes(self) -> bytes:
        raw = _canonical(_wire(self))
        if len(raw) > _MAX_RESULT_BYTES:
            raise ValueError("current price context result exceeds its bound")
        return raw


def current_price_context_request_from_canonical_json_bytes_v1(
    raw: bytes,
) -> CurrentPriceContextRequestV1:
    """Decode only the closed canonical owner-supplied request representation."""
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_REQUEST_BYTES:
        raise ValueError("current price context request is invalid")
    try:
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError):
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
    except (KeyError, TypeError, ValueError, RecursionError):
        raise ValueError("current price context request is invalid") from None


def research_current_price_context_v1(  # noqa: C901 -- fixed one-lease composition order
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
        clock is not None and not callable(getattr(clock, "now", None))
    ):
        raise ValueError("current price context options are invalid")
    observed_now = datetime.now(UTC) if clock is None else clock.now()
    if not _utc(observed_now):
        raise ValueError("current price context clock is invalid")
    if observed_now > request.admission_deadline:
        raise ValueError("current price context deadline exceeded")
    if (
        observed_now.astimezone(_IST).date()
        != request.data_selection_time.astimezone(_IST).date()
    ):
        raise ValueError("current price context IST date changed")
    # Retained-only is the default and never constructs an acquisition client or
    # token provider.  A failed existing-root admission is an explicit missing
    # prerequisite, not permission to create a root or catalog.
    runtime_identity = current_price_context_runtime_code_identity_v1()
    raw_input = CurrentRawPriceContextInputV1(
        request.request_identity_sha256,
        request.data_selection_time,
        request.admission_deadline,
        request.schedule_identity_sha256,
        request.members,
    )
    active_clock = _SystemClock() if clock is None else clock
    control = CurrentRawInvocationControlV1(
        active_clock,
        selection=request.data_selection_time,
        deadline=request.admission_deadline,
    )
    acquisition_outcome: Literal[
        "NOT_ATTEMPTED", "CALENDAR_PREREQUISITE_MISSING", "RETAINED_EVIDENCE_READY"
    ] = "NOT_ATTEMPTED"
    if acquire_missing:
        acquisition_outcome = acquire_missing_current_raw_evidence_v1(
            raw_input, storage_root, control=control
        ).outcome
    industry_state: Literal["OBSERVED", "NOT_ATTEMPTED", "INSUFFICIENT_EVIDENCE"] = (
        "NOT_ATTEMPTED"
    )
    industry_reasons: tuple[str, ...] = ("INDUSTRY_REFERENCE_NOT_PROVIDED",)
    industry_groups: tuple[CurrentRawIndustryGroupV1, ...] = ()
    admitted = StorageRootLease.try_admit_read_existing(storage_root)
    if admitted.lease is None:
        feature_state: Literal[
            "OBSERVED", "UNSUPPORTED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"
        ] = "DEPENDENCY_BLOCKED"
        reasons = ("CALENDAR_PREREQUISITE_MISSING",)
    else:
        with admitted.lease as lease:
            retained = read_retained_current_raw_context_v1(
                storage_root, request=raw_input, lease=lease, control=control
            )
            if retained.admitted is not None:
                raw_projection = validate_admitted_current_raw_context_v1(
                    retained.admitted
                )
                if request.industry_archive_reference is not None:
                    archive = read_current_industry_archive_exact_v1(
                        ArchivedIndustryReferenceV1(
                            request.industry_archive_reference.contract_version,
                            request.industry_archive_reference.snapshot_identity_sha256,
                            request.industry_archive_reference.retained_identity_sha256,
                        ),
                        storage_root=storage_root,
                        lease=lease,
                        cutoff=raw_projection.evidence_cutoff,
                    )
                    if type(archive) is CurrentIndustryReadFailureV1:
                        industry_state = "INSUFFICIENT_EVIDENCE"
                        industry_reasons = (archive.reason,)
                    else:
                        classification = cast(
                            AdmittedCurrentIndustryProjectionV1, archive
                        )
                        directions = {
                            (
                                member.isin,
                                member.exchange,
                                member.effective_symbol,
                            ): member.direction
                            for member in raw_projection.members
                        }
                        grouped = reduce_current_raw_industry_participation_v1(
                            tuple(
                                RawIndustryDirectionV1(
                                    isin,
                                    cast(Literal["NSE"], exchange),
                                    symbol,
                                    industry,
                                    cast(
                                        Literal["ADVANCE", "DECLINE", "UNCHANGED"]
                                        | None,
                                        directions.get((isin, exchange, symbol)),
                                    ),
                                )
                                for isin, exchange, symbol, industry in classification.rows
                            ),
                            requested_count=len(raw_projection.members),
                        )
                        if grouped.evidence_state == "OBSERVED":
                            industry_state = "OBSERVED"
                            industry_reasons = ()
                            industry_groups = grouped.groups
                        else:
                            industry_state = "INSUFFICIENT_EVIDENCE"
                            industry_reasons = grouped.reasons
            feature_state = retained.state
            reasons = retained.reasons
    acquisition_mode: Literal["RETAINED_ONLY", "ACQUIRE_MISSING"] = (
        "ACQUIRE_MISSING" if acquire_missing else "RETAINED_ONLY"
    )
    return CurrentPriceContextResultV1(
        contract_version=_RESULT_CONTRACT,
        request_identity_sha256=request.request_identity_sha256,
        schedule_identity_sha256=request.schedule_identity_sha256,
        ordered_selection_identity_sha256=raw_input.ordered_selection_identity_sha256,
        acquisition_mode=acquisition_mode,
        acquisition_outcome=acquisition_outcome,
        features=tuple(
            CurrentPriceContextFeatureV1(
                question,
                feature_state
                if question != "RAW_INDUSTRY_PARTICIPATION"
                else industry_state,
                reasons
                if question != "RAW_INDUSTRY_PARTICIPATION"
                else industry_reasons,
                readiness="READY"
                if (
                    feature_state == "OBSERVED"
                    and question != "RAW_INDUSTRY_PARTICIPATION"
                )
                or (
                    question == "RAW_INDUSTRY_PARTICIPATION"
                    and industry_state == "OBSERVED"
                )
                else "WITHHELD",
            )
            for question in _QUESTIONS
        ),
        limitations=("UPSTOX_RAW_ONLY", "RETAINED_EVIDENCE_REQUIRED"),
        runtime_code_identity_sha256=runtime_identity,
        industry_evidence_state=industry_state,
        industry_groups=industry_groups,
    )


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


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


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field")
        value[key] = item
    return value


def _without_request_identity(value: CurrentPriceContextRequestV1) -> dict[str, object]:
    return {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if item.name != "request_identity_sha256"
    }


def _digest_value(value: object) -> str:
    return hashlib.sha256(_canonical(_wire(value))).hexdigest()


def _without_identity(value: CurrentPriceContextResultV1) -> dict[str, object]:
    return {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if item.name != "result_identity_sha256"
    }
