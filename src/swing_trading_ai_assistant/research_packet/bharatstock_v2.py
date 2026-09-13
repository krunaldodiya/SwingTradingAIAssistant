"""Retained BharatStock price-feature projection for Issue #187.

The V2 producer accepts only closure-bound revisions returned by the capture
archive reader.  It represents every 1/2/21 feature input explicitly and keeps
member/feature comparability local.
"""

from __future__ import annotations

import hashlib
import json
import re
import weakref
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from pathlib import Path
from typing import Final, Literal, TypeAlias, cast

from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockInstrument,
    BharatStockPriceBasis,
)
from swing_trading_ai_assistant.market_data.bharatstock_capture import (
    RetainedCaptureBindingV2,
    RetainedCaptureRevisionV2,
    selection_identity_v2,
    validate_retained_capture_binding_v2,
)
from swing_trading_ai_assistant.market_data.current_research_binding_v2 import (
    AdmittedCurrentResearchBindingV2,
    validate_current_research_binding_v2,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.market_structure.current_live import (
    CALCULATION_IDENTITY_SHA256_V1 as STRUCTURE_CALCULATION_IDENTITY_SHA256_V1,
)
from swing_trading_ai_assistant.market_structure.current_live import (
    SCHEMA_IDENTITY_SHA256_V1 as STRUCTURE_SCHEMA_IDENTITY_SHA256_V1,
)
from swing_trading_ai_assistant.market_structure.current_live import (
    current_market_structure_runtime_code_identity_v1,
)
from swing_trading_ai_assistant.research_packet.bharatstock import (
    BharatStockAdjustedBarV1,
    BharatStockAdjustedMarketStructureFactV1,
    _adjusted_bars,  # pyright: ignore[reportPrivateUsage]
    _direction,  # pyright: ignore[reportPrivateUsage]
    _market_structure,  # pyright: ignore[reportPrivateUsage]
)

from .bharatstock_v2_runtime_identity_manifest import (
    BHARATSTOCK_RESEARCH_RUNTIME_SOURCE_SHA256_V2,
)

_CONTRACT: Final = "bharatstock-retained-research-packet@v2"
_SCHEMA_IDENTITY: Final = hashlib.sha256(
    b"bharatstock-retained-research-packet-schema@v2\n"
).hexdigest()
_CONFIGURATION_IDENTITY: Final = hashlib.sha256(
    b"independent-1-2-21-source-reported-member-local-comparability@v2\n"
).hexdigest()
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_FEATURES: Final = (
    "CANDLE_GEOMETRY",
    "PREVIOUS_CLOSE_COMPARISON",
    "MARKET_STRUCTURE",
)
_EXPECTED_SESSIONS: Final = {
    "CANDLE_GEOMETRY": 1,
    "PREVIOUS_CLOSE_COMPARISON": 2,
    "MARKET_STRUCTURE": 21,
}
_Availability: TypeAlias = Literal[
    "OBSERVED",
    "UNSUPPORTED_CAPABILITY",
    "DEPENDENCY_BLOCKED",
    "INSUFFICIENT_EVIDENCE",
    "NOT_ATTEMPTED",
]
_Support: TypeAlias = Literal[
    "SUPPORTED", "UNSUPPORTED", "CONFLICTED", "NOT_ESTABLISHED"
]
_Comparability: TypeAlias = Literal["SUPPORTED", "CONFLICTED", "NOT_ESTABLISHED"]
_RetainedPriceBasis: TypeAlias = (
    BharatStockPriceBasis | Literal["BHARATSTOCK_SPLIT_BONUS_FACTOR_ADJUSTED_OHLC"]
)


def _wire(value: object) -> object:
    if type(value) is Decimal:
        return format(value, "f")
    if type(value) is datetime:
        return (
            value.astimezone(UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if type(value) is date:
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _wire(getattr(value, item.name))
            for item in fields(value)
            if not item.name.startswith("_")
        }
    if type(value) is tuple:
        return [_wire(item) for item in cast(tuple[object, ...], value)]
    if type(value) is dict:
        return {
            str(key): _wire(item)
            for key, item in cast(dict[object, object], value).items()
        }
    return value


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            _wire(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _valid_digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(None)
    ):
        raise ValueError("invalid BharatStock V2 timestamp")
    return value.astimezone(UTC)


def _decimal_text_size(value: object) -> int:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError("invalid BharatStock V2 decimal")
    sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int) or not -256 <= exponent <= 256:
        raise ValueError("invalid BharatStock V2 decimal")
    digit_count = max(1, len(digits))
    if exponent >= 0:
        size = digit_count + exponent
    else:
        size = max(digit_count, -exponent + 1) + 1
    return size + int(bool(sign))


def _bounded_nonnegative_decimal(value: object) -> bool:
    try:
        return (
            type(value) is Decimal
            and value.is_finite()
            and value >= 0
            and _decimal_text_size(value) <= 258
        )
    except (ArithmeticError, ValueError):
        return False


def bharatstock_research_runtime_code_identity_v2() -> str:
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in BHARATSTOCK_RESEARCH_RUNTIME_SOURCE_SHA256_V2.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("BharatStock V2 runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


@dataclass(frozen=True, slots=True)
class BharatStockCandleGeometryFactV2:
    session: date
    candle_direction: Literal["UP", "DOWN", "UNCHANGED"]
    session_range_state: Literal["FLAT", "NON_FLAT"]
    range_size: Decimal
    body_size: Decimal
    upper_wick_size: Decimal
    lower_wick_size: Decimal
    source_bar_identity_sha256: str

    def __post_init__(self) -> None:
        values = (
            self.range_size,
            self.body_size,
            self.upper_wick_size,
            self.lower_wick_size,
        )
        if (
            type(self.session) is not date
            or self.candle_direction not in {"UP", "DOWN", "UNCHANGED"}
            or self.session_range_state not in {"FLAT", "NON_FLAT"}
            or any(not _bounded_nonnegative_decimal(value) for value in values)
            or (self.range_size == 0) != (self.session_range_state == "FLAT")
            or (self.body_size == 0) != (self.candle_direction == "UNCHANGED")
            or self.body_size + self.upper_wick_size + self.lower_wick_size
            != self.range_size
            or not _valid_digest(self.source_bar_identity_sha256)
        ):
            raise ValueError("invalid BharatStock V2 geometry fact")


@dataclass(frozen=True, slots=True)
class BharatStockPreviousCloseComparisonFactV2:
    previous_session: date
    session: date
    open_vs_previous_close: Literal["UP", "DOWN", "UNCHANGED"]
    open_to_previous_close_distance: Decimal
    close_vs_previous_close: Literal["UP", "DOWN", "UNCHANGED"]
    close_to_previous_close_distance: Decimal
    source_bar_identities_sha256: tuple[str, str]

    def __post_init__(self) -> None:
        if (
            type(self.previous_session) is not date
            or type(self.session) is not date
            or self.previous_session >= self.session
            or self.open_vs_previous_close not in {"UP", "DOWN", "UNCHANGED"}
            or self.close_vs_previous_close not in {"UP", "DOWN", "UNCHANGED"}
            or not _bounded_nonnegative_decimal(self.open_to_previous_close_distance)
            or not _bounded_nonnegative_decimal(self.close_to_previous_close_distance)
            or (self.open_to_previous_close_distance == 0)
            != (self.open_vs_previous_close == "UNCHANGED")
            or (self.close_to_previous_close_distance == 0)
            != (self.close_vs_previous_close == "UNCHANGED")
            or type(self.source_bar_identities_sha256) is not tuple
            or len(self.source_bar_identities_sha256) != 2
            or any(
                not _valid_digest(item) for item in self.source_bar_identities_sha256
            )
        ):
            raise ValueError("invalid BharatStock V2 comparison fact")


@dataclass(frozen=True, slots=True)
class BharatStockFeatureInputV2:
    """One explicit retained, attempted, shared-stop, or unrequested input slot."""

    feature: Literal["CANDLE_GEOMETRY", "PREVIOUS_CLOSE_COMPARISON", "MARKET_STRUCTURE"]
    state: Literal[
        "RETAINED_REVISION",
        "ATTEMPTED_NO_REVISION",
        "NOT_ATTEMPTED_SHARED_STOP",
        "UNREQUESTED",
    ]
    requested_sessions: tuple[date, ...]
    retained_capture: RetainedCaptureBindingV2 | None = field(
        default=None, repr=False, compare=False
    )
    failure_code: str | None = None
    failure_reason: str | None = None
    executed_at: datetime | None = None
    stop_reference: str | None = None

    def __post_init__(self) -> None:
        if self.feature not in _FEATURES or self.state not in {
            "RETAINED_REVISION",
            "ATTEMPTED_NO_REVISION",
            "NOT_ATTEMPTED_SHARED_STOP",
            "UNREQUESTED",
        }:
            raise ValueError("invalid BharatStock V2 input slot")
        expected = _EXPECTED_SESSIONS[self.feature]
        if (
            type(self.requested_sessions) is not tuple
            or any(type(item) is not date for item in self.requested_sessions)
            or self.requested_sessions != tuple(sorted(self.requested_sessions))
            or len(set(self.requested_sessions)) != len(self.requested_sessions)
            or (
                self.state == "UNREQUESTED"
                and (
                    self.requested_sessions
                    or self.retained_capture is not None
                    or self.failure_code is not None
                    or self.failure_reason is not None
                    or self.executed_at is not None
                    or self.stop_reference is not None
                )
            )
            or (
                self.state != "UNREQUESTED"
                and len(self.requested_sessions) != expected
                and not (
                    self.state == "ATTEMPTED_NO_REVISION"
                    and self.failure_code == "INSUFFICIENT_COMPLETED_SESSIONS"
                    and len(self.requested_sessions) < expected
                )
            )
            or (
                self.state == "RETAINED_REVISION"
                and (
                    type(self.retained_capture) is not RetainedCaptureBindingV2
                    or self.failure_code is not None
                    or self.failure_reason is not None
                    or self.executed_at is not None
                    or self.stop_reference is not None
                )
            )
            or (
                self.state == "ATTEMPTED_NO_REVISION"
                and (
                    self.retained_capture is not None
                    or type(self.failure_code) is not str
                    or not self.failure_code
                    or type(self.failure_reason) is not str
                    or not self.failure_reason
                    or self.executed_at is None
                    or self.stop_reference is not None
                )
            )
            or (
                self.state == "NOT_ATTEMPTED_SHARED_STOP"
                and (
                    self.retained_capture is not None
                    or self.failure_code != "NOT_ATTEMPTED"
                    or self.failure_reason != "BLOCKED_BY_SHARED_FAILURE"
                    or self.executed_at is None
                    or type(self.stop_reference) is not str
                    or not self.stop_reference
                )
            )
        ):
            raise ValueError("invalid BharatStock V2 input slot")
        if self.executed_at is not None:
            object.__setattr__(self, "executed_at", _utc(self.executed_at))


@dataclass(frozen=True, slots=True)
class BharatStockFeatureSourceV2:
    feature: str
    capture_contract_version: str
    capture_schema_identity_sha256: str
    capture_configuration_identity_sha256: str
    capture_runtime_code_identity_sha256: str
    capture_request_identity_sha256: str
    capture_revision_identity_sha256: str
    projection_contract_version: str
    projection_schema_identity_sha256: str
    projection_configuration_identity_sha256: str
    projection_runtime_code_identity_sha256: str
    schedule_evidence_sha256: str
    schedule_identity_sha256: str
    selection_identity_sha256: str
    requested_sessions: tuple[date, ...]
    admitted_sessions: tuple[date, ...]
    provider_source: str
    source_profile: str
    price_basis: _RetainedPriceBasis
    volume_basis: str
    known_at: datetime
    decision_cutoff: datetime
    source_identity_sha256: str
    source_projection_identity_sha256: str

    def __post_init__(self) -> None:
        known = _utc(self.known_at)
        cutoff = _utc(self.decision_cutoff)
        if (
            self.feature not in _FEATURES
            or self.projection_contract_version != _CONTRACT
            or self.projection_schema_identity_sha256 != _SCHEMA_IDENTITY
            or self.projection_configuration_identity_sha256 != _CONFIGURATION_IDENTITY
            or any(
                not _valid_digest(value)
                for value in (
                    self.capture_schema_identity_sha256,
                    self.capture_configuration_identity_sha256,
                    self.capture_runtime_code_identity_sha256,
                    self.capture_request_identity_sha256,
                    self.capture_revision_identity_sha256,
                    self.projection_runtime_code_identity_sha256,
                    self.schedule_evidence_sha256,
                    self.schedule_identity_sha256,
                    self.selection_identity_sha256,
                    self.source_identity_sha256,
                    self.source_projection_identity_sha256,
                )
            )
            or type(self.capture_contract_version) is not str
            or not self.capture_contract_version
            or type(self.requested_sessions) is not tuple
            or len(self.requested_sessions) != _EXPECTED_SESSIONS[self.feature]
            or self.admitted_sessions != self.requested_sessions
            or known > cutoff
            or any(
                type(value) is not str or not value
                for value in (
                    self.provider_source,
                    self.source_profile,
                    self.price_basis,
                    self.volume_basis,
                )
            )
        ):
            raise ValueError("invalid BharatStock V2 feature source")
        expected = _digest(
            {
                item.name: getattr(self, item.name)
                for item in fields(self)
                if item.name != "source_projection_identity_sha256"
            }
        )
        if self.source_projection_identity_sha256 != expected:
            raise ValueError("invalid BharatStock V2 feature source")
        object.__setattr__(self, "known_at", known)
        object.__setattr__(self, "decision_cutoff", cutoff)


@dataclass(frozen=True, slots=True)
class BharatStockFeatureSlotV2:
    feature: str
    state: Literal[
        "RETAINED_REVISION",
        "ATTEMPTED_NO_REVISION",
        "NOT_ATTEMPTED_SHARED_STOP",
        "UNREQUESTED",
    ]
    requested_sessions: tuple[date, ...]
    source: BharatStockFeatureSourceV2 | None
    failure_code: str | None
    failure_reason: str | None
    executed_at: datetime | None
    stop_reference: str | None
    slot_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            self.feature not in _FEATURES
            or self.state
            not in {
                "RETAINED_REVISION",
                "ATTEMPTED_NO_REVISION",
                "NOT_ATTEMPTED_SHARED_STOP",
                "UNREQUESTED",
            }
            or type(self.requested_sessions) is not tuple
            or (
                self.state == "UNREQUESTED"
                and (
                    self.requested_sessions
                    or self.source is not None
                    or self.failure_code is not None
                    or self.failure_reason is not None
                    or self.executed_at is not None
                    or self.stop_reference is not None
                )
            )
            or (
                self.state != "UNREQUESTED"
                and len(self.requested_sessions) != _EXPECTED_SESSIONS[self.feature]
                and not (
                    self.state == "ATTEMPTED_NO_REVISION"
                    and self.failure_code == "INSUFFICIENT_COMPLETED_SESSIONS"
                    and len(self.requested_sessions) < _EXPECTED_SESSIONS[self.feature]
                )
            )
            or (self.state == "RETAINED_REVISION")
            != (type(self.source) is BharatStockFeatureSourceV2)
            or (
                self.state == "ATTEMPTED_NO_REVISION"
                and (
                    type(self.failure_code) is not str
                    or not self.failure_code
                    or type(self.failure_reason) is not str
                    or not self.failure_reason
                    or self.executed_at is None
                    or self.stop_reference is not None
                )
            )
            or (
                self.state == "NOT_ATTEMPTED_SHARED_STOP"
                and (
                    self.failure_code != "NOT_ATTEMPTED"
                    or self.failure_reason != "BLOCKED_BY_SHARED_FAILURE"
                    or self.executed_at is None
                    or type(self.stop_reference) is not str
                    or not self.stop_reference
                )
            )
            or (
                self.source is not None
                and (
                    self.source.feature != self.feature
                    or self.source.requested_sessions != self.requested_sessions
                )
            )
            or not _valid_digest(self.slot_identity_sha256)
        ):
            raise ValueError("invalid BharatStock V2 feature slot")
        expected = _digest(
            {
                item.name: getattr(self, item.name)
                for item in fields(self)
                if item.name != "slot_identity_sha256"
            }
        )
        if self.slot_identity_sha256 != expected:
            raise ValueError("invalid BharatStock V2 feature slot")


@dataclass(frozen=True, slots=True)
class BharatStockFeatureCoverageV2:
    feature: str
    requested: int
    observed: int
    unsupported: int
    dependency_blocked: int
    insufficient: int
    not_attempted: int

    def __post_init__(self) -> None:
        if (
            self.feature not in _FEATURES
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.requested,
                    self.observed,
                    self.unsupported,
                    self.dependency_blocked,
                    self.insufficient,
                    self.not_attempted,
                )
            )
            or self.requested
            != self.observed
            + self.unsupported
            + self.dependency_blocked
            + self.insufficient
            + self.not_attempted
        ):
            raise ValueError("invalid BharatStock V2 feature coverage")


V2Fact = (
    BharatStockCandleGeometryFactV2
    | BharatStockPreviousCloseComparisonFactV2
    | BharatStockAdjustedMarketStructureFactV1
)


@dataclass(frozen=True, slots=True)
class BharatStockMemberFeatureV2:
    feature: str
    availability: _Availability
    support: _Support
    comparability: _Comparability
    reason: str | None
    fact: V2Fact | None

    def __post_init__(self) -> None:
        expected = {
            "CANDLE_GEOMETRY": BharatStockCandleGeometryFactV2,
            "PREVIOUS_CLOSE_COMPARISON": BharatStockPreviousCloseComparisonFactV2,
            "MARKET_STRUCTURE": BharatStockAdjustedMarketStructureFactV1,
        }.get(self.feature)
        if (
            expected is None
            or self.availability
            not in {
                "OBSERVED",
                "UNSUPPORTED_CAPABILITY",
                "DEPENDENCY_BLOCKED",
                "INSUFFICIENT_EVIDENCE",
                "NOT_ATTEMPTED",
            }
            or self.support
            not in {"SUPPORTED", "UNSUPPORTED", "CONFLICTED", "NOT_ESTABLISHED"}
            or self.comparability not in {"SUPPORTED", "CONFLICTED", "NOT_ESTABLISHED"}
            or (self.availability == "OBSERVED") != (self.fact is not None)
            or (
                self.availability == "OBSERVED"
                and (self.reason is not None or self.support != "SUPPORTED")
            )
            or (
                self.availability != "OBSERVED"
                and (
                    self.fact is not None
                    or type(self.reason) is not str
                    or not self.reason
                )
            )
            or (self.fact is not None and type(self.fact) is not expected)
        ):
            raise ValueError("invalid BharatStock V2 member feature")


@dataclass(frozen=True, slots=True)
class BharatStockResearchMemberV2:
    member: BharatStockInstrument
    price_basis: _RetainedPriceBasis | None
    features: tuple[BharatStockMemberFeatureV2, ...]

    def __post_init__(self) -> None:
        if (
            type(self.member) is not BharatStockInstrument
            or self.price_basis
            not in {
                None,
                "BHARATSTOCK_SOURCE_REPORTED_OHLC",
                "BHARATSTOCK_SPLIT_BONUS_FACTOR_ADJUSTED_OHLC",
            }
            or type(self.features) is not tuple
            or any(
                type(item) is not BharatStockMemberFeatureV2 for item in self.features
            )
            or tuple(item.feature for item in self.features)
            != tuple(
                feature
                for feature in _FEATURES
                if any(x.feature == feature for x in self.features)
            )
            or len({item.feature for item in self.features}) != len(self.features)
        ):
            raise ValueError("invalid BharatStock V2 research member")

    def feature(self, name: str) -> BharatStockMemberFeatureV2 | None:
        return next((item for item in self.features if item.feature == name), None)

    @property
    def geometry(self) -> BharatStockCandleGeometryFactV2 | None:
        item = self.feature("CANDLE_GEOMETRY")
        return (
            None
            if item is None
            else cast(BharatStockCandleGeometryFactV2 | None, item.fact)
        )

    @property
    def comparison(self) -> BharatStockPreviousCloseComparisonFactV2 | None:
        item = self.feature("PREVIOUS_CLOSE_COMPARISON")
        return (
            None
            if item is None
            else cast(BharatStockPreviousCloseComparisonFactV2 | None, item.fact)
        )

    @property
    def structure(self) -> BharatStockAdjustedMarketStructureFactV1 | None:
        item = self.feature("MARKET_STRUCTURE")
        return (
            None
            if item is None
            else cast(BharatStockAdjustedMarketStructureFactV1 | None, item.fact)
        )


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True)
class BharatStockResearchPacketV2:
    contract_version: Literal["bharatstock-retained-research-packet@v2"]
    schema_identity_sha256: str
    configuration_identity_sha256: str
    runtime_code_identity_sha256: str
    selection_identity_sha256: str
    execution_state: Literal["COMPLETED", "STOPPED"]
    shared_stop_code: str | None
    shared_stop_time: datetime | None
    feature_slots: tuple[BharatStockFeatureSlotV2, ...]
    coverage: tuple[BharatStockFeatureCoverageV2, ...]
    members: tuple[BharatStockResearchMemberV2, ...]
    result_identity_sha256: str
    _admission_seal: object = field(repr=False, compare=False, hash=False)

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("BharatStock V2 packet constructor unavailable")

    @property
    def admitted(self) -> bool:
        return _admission_digest(self) is not None

    @property
    def admission_identity_sha256(self) -> str:
        digest = _admission_digest(self)
        if digest is None:
            raise ValueError("BharatStock V2 packet is not admitted evidence")
        return digest

    @property
    def requested_features(self) -> tuple[str, ...]:
        return tuple(
            slot.feature for slot in self.feature_slots if slot.state != "UNREQUESTED"
        )

    def source(self, feature: str) -> BharatStockFeatureSourceV2 | None:
        slot = next(
            (item for item in self.feature_slots if item.feature == feature), None
        )
        return None if slot is None else slot.source

    @property
    def geometry_source(self) -> BharatStockFeatureSourceV2 | None:
        return self.source("CANDLE_GEOMETRY")

    @property
    def comparison_source(self) -> BharatStockFeatureSourceV2 | None:
        return self.source("PREVIOUS_CLOSE_COMPARISON")

    @property
    def structure_source(self) -> BharatStockFeatureSourceV2 | None:
        return self.source("MARKET_STRUCTURE")

    @property
    def price_basis(self) -> _RetainedPriceBasis | None:
        return self.members[0].price_basis

    def canonical_json_bytes(self) -> bytes:
        return _canonical_bytes(self)


_ADMISSIONS: dict[
    int,
    tuple[weakref.ReferenceType[BharatStockResearchPacketV2], bytes, object],
] = {}


def _admit(packet: BharatStockResearchPacketV2) -> None:
    packet_id = id(packet)
    seal = object.__getattribute__(packet, "_admission_seal")

    def discard(reference: weakref.ReferenceType[BharatStockResearchPacketV2]) -> None:
        entry = _ADMISSIONS.get(packet_id)
        if entry is not None and entry[0] is reference:
            _ADMISSIONS.pop(packet_id, None)

    _ADMISSIONS[packet_id] = (
        weakref.ref(packet, discard),
        packet.canonical_json_bytes(),
        seal,
    )


def _admission_digest(packet: BharatStockResearchPacketV2) -> str | None:
    entry = _ADMISSIONS.get(id(packet))
    if (
        entry is None
        or entry[0]() is not packet
        or entry[1] != packet.canonical_json_bytes()
        or entry[2] is not object.__getattribute__(packet, "_admission_seal")
    ):
        return None
    return hashlib.sha256(entry[1]).hexdigest()


def _validate_packet(packet: BharatStockResearchPacketV2) -> bool:
    requested = packet.requested_features
    if (
        packet.contract_version != _CONTRACT
        or packet.schema_identity_sha256 != _SCHEMA_IDENTITY
        or packet.configuration_identity_sha256 != _CONFIGURATION_IDENTITY
        or packet.runtime_code_identity_sha256
        != bharatstock_research_runtime_code_identity_v2()
        or tuple(slot.feature for slot in packet.feature_slots) != _FEATURES
        or len(packet.members) < 1
        or tuple(item.member for item in packet.members)
        != tuple(item.member for item in packet.members)
        or packet.selection_identity_sha256
        != selection_identity_v2(tuple(item.member for item in packet.members))
        or tuple(item.feature for item in packet.coverage) != requested
        or any(
            tuple(feature.feature for feature in member.features) != requested
            for member in packet.members
        )
        or packet.execution_state
        != (
            "STOPPED"
            if any(
                slot.state == "NOT_ATTEMPTED_SHARED_STOP"
                for slot in packet.feature_slots
            )
            else "COMPLETED"
        )
        or (packet.execution_state == "STOPPED")
        != (packet.shared_stop_code is not None and packet.shared_stop_time is not None)
    ):
        return False
    if packet.shared_stop_time is not None:
        try:
            _utc(packet.shared_stop_time)
        except ValueError:
            return False
    expected_coverage = tuple(
        _coverage(feature, packet.members) for feature in requested
    )
    if packet.coverage != expected_coverage:
        return False
    preimage = {
        item.name: getattr(packet, item.name)
        for item in fields(packet)
        if item.name not in {"result_identity_sha256", "_admission_seal"}
    }
    return packet.result_identity_sha256 == _digest(preimage)


def bharatstock_research_packet_semantics_are_valid_v2(packet: object) -> bool:
    """Validate canonical producer semantics without minting retention admission."""
    if type(packet) is not BharatStockResearchPacketV2:
        return False
    try:
        for slot in packet.feature_slots:
            slot.__post_init__()
            if slot.source is not None:
                slot.source.__post_init__()
        for coverage in packet.coverage:
            coverage.__post_init__()
        for member in packet.members:
            member.__post_init__()
            for feature in member.features:
                feature.__post_init__()
                if feature.fact is not None:
                    feature.fact.__post_init__()
        return _validate_packet(packet)
    except (ArithmeticError, TypeError, ValueError):
        return False


def validate_bharatstock_research_packet_v2(
    packet: object,
) -> BharatStockResearchPacketV2:
    if (
        type(packet) is not BharatStockResearchPacketV2
        or not bharatstock_research_packet_semantics_are_valid_v2(packet)
        or _admission_digest(packet) is None
    ):
        raise ValueError("BharatStock V2 packet is not admitted evidence")
    return packet


def _bars_for(
    revision: RetainedCaptureRevisionV2, position: int
) -> tuple[BharatStockAdjustedBarV1, ...] | None:
    result = revision.members[position]
    if result.evidence_state != "OBSERVED":
        return None
    if result.history is None:
        raise ValueError("observed BharatStock capture member lacks history")
    return _adjusted_bars(
        result.member, result.history, revision.request.sessions, revision
    )


def _geometry(bar: BharatStockAdjustedBarV1) -> BharatStockCandleGeometryFactV2:
    range_size = bar.high - bar.low
    return BharatStockCandleGeometryFactV2(
        bar.session,
        _direction(bar.close, bar.open),
        "FLAT" if range_size == 0 else "NON_FLAT",
        range_size,
        abs(bar.close - bar.open),
        bar.high - max(bar.open, bar.close),
        min(bar.open, bar.close) - bar.low,
        bar.source_row_identity_sha256,
    )


def _comparison(
    bars: tuple[BharatStockAdjustedBarV1, ...],
) -> BharatStockPreviousCloseComparisonFactV2:
    previous, current = bars[-2:]
    return BharatStockPreviousCloseComparisonFactV2(
        previous.session,
        current.session,
        _direction(current.open, previous.close),
        abs(current.open - previous.close),
        _direction(current.close, previous.close),
        abs(current.close - previous.close),
        (previous.source_row_identity_sha256, current.source_row_identity_sha256),
    )


def _semantic_bar_value(bar: BharatStockAdjustedBarV1) -> tuple[object, ...]:
    return (bar.session, bar.open, bar.high, bar.low, bar.close, bar.volume)


def _comparability(  # noqa: C901 - closed three-feature comparison matrix
    feature: str,
    position: int,
    revisions: dict[str, RetainedCaptureRevisionV2],
) -> _Comparability:
    current = revisions.get(feature)
    if current is None or _bars_for(current, position) is None:
        return "NOT_ESTABLISHED"
    if feature == "CANDLE_GEOMETRY":
        return "SUPPORTED"
    current_bars = _bars_for(current, position)
    if current_bars is None:
        return "NOT_ESTABLISHED"
    required_sessions = set(current.request.sessions)
    if feature == "PREVIOUS_CLOSE_COMPARISON":
        required_sessions = set(current.request.sessions[-2:])
    compared = False
    for other_feature, other in revisions.items():
        if other_feature == feature:
            continue
        other_bars = _bars_for(other, position)
        if other_bars is None:
            continue
        other_by_session = {bar.session: bar for bar in other_bars}
        for bar in current_bars:
            if bar.session not in required_sessions:
                continue
            overlap = other_by_session.get(bar.session)
            if overlap is None:
                continue
            compared = True
            if _semantic_bar_value(bar) != _semantic_bar_value(overlap):
                return "CONFLICTED"
    return "SUPPORTED" if compared or len(revisions) == 1 else "NOT_ESTABLISHED"


def _source(
    feature: str, revision: RetainedCaptureRevisionV2, runtime: str
) -> BharatStockFeatureSourceV2:
    request = revision.request
    source_identity = _digest(
        {
            "provider_source": revision.provider_source,
            "source_profile": revision.source_profile,
            "revision_identity_sha256": revision.revision_identity_sha256,
            "price_basis": revision.price_basis,
            "volume_basis": revision.volume_basis,
        }
    )
    values = {
        "feature": feature,
        "capture_contract_version": request.contract_version,
        "capture_schema_identity_sha256": request.schema_identity_sha256,
        "capture_configuration_identity_sha256": request.configuration_identity_sha256,
        "capture_runtime_code_identity_sha256": request.runtime_code_identity_sha256,
        "capture_request_identity_sha256": request.request_identity_sha256,
        "capture_revision_identity_sha256": revision.revision_identity_sha256,
        "projection_contract_version": _CONTRACT,
        "projection_schema_identity_sha256": _SCHEMA_IDENTITY,
        "projection_configuration_identity_sha256": _CONFIGURATION_IDENTITY,
        "projection_runtime_code_identity_sha256": runtime,
        "schedule_evidence_sha256": request.schedule_evidence_sha256,
        "schedule_identity_sha256": request.schedule_identity_sha256,
        "selection_identity_sha256": request.selection_identity_sha256,
        "requested_sessions": request.sessions,
        "admitted_sessions": request.sessions,
        "provider_source": revision.provider_source,
        "source_profile": revision.source_profile,
        "price_basis": cast(_RetainedPriceBasis, revision.price_basis),
        "volume_basis": revision.volume_basis,
        "known_at": revision.observed_at,
        "decision_cutoff": request.decision_cutoff,
        "source_identity_sha256": source_identity,
    }
    return BharatStockFeatureSourceV2(
        feature,
        request.contract_version,
        request.schema_identity_sha256,
        request.configuration_identity_sha256,
        request.runtime_code_identity_sha256,
        request.request_identity_sha256,
        revision.revision_identity_sha256,
        _CONTRACT,
        _SCHEMA_IDENTITY,
        _CONFIGURATION_IDENTITY,
        runtime,
        request.schedule_evidence_sha256,
        request.schedule_identity_sha256,
        request.selection_identity_sha256,
        request.sessions,
        request.sessions,
        revision.provider_source,
        revision.source_profile,
        cast(_RetainedPriceBasis, revision.price_basis),
        revision.volume_basis,
        revision.observed_at,
        request.decision_cutoff,
        source_identity,
        _digest(values),
    )


def _slot(input: BharatStockFeatureInputV2, runtime: str) -> BharatStockFeatureSlotV2:
    source: BharatStockFeatureSourceV2 | None = None
    if input.state == "RETAINED_REVISION":
        source = _source(
            input.feature,
            validate_retained_capture_binding_v2(input.retained_capture),
            runtime,
        )
    values = {
        "feature": input.feature,
        "state": input.state,
        "requested_sessions": input.requested_sessions,
        "source": source,
        "failure_code": input.failure_code,
        "failure_reason": input.failure_reason,
        "executed_at": input.executed_at,
        "stop_reference": input.stop_reference,
    }
    return BharatStockFeatureSlotV2(
        input.feature,
        input.state,
        input.requested_sessions,
        source,
        input.failure_code,
        input.failure_reason,
        input.executed_at,
        input.stop_reference,
        _digest(values),
    )


def _coverage(
    feature: str, members: tuple[BharatStockResearchMemberV2, ...]
) -> BharatStockFeatureCoverageV2:
    values = [
        cast(BharatStockMemberFeatureV2, item.feature(feature)).availability
        for item in members
    ]
    return BharatStockFeatureCoverageV2(
        feature,
        len(values),
        values.count("OBSERVED"),
        values.count("UNSUPPORTED_CAPABILITY"),
        values.count("DEPENDENCY_BLOCKED"),
        values.count("INSUFFICIENT_EVIDENCE"),
        values.count("NOT_ATTEMPTED"),
    )


def _failure_member_feature(
    slot: BharatStockFeatureSlotV2,
) -> BharatStockMemberFeatureV2:
    if slot.state == "NOT_ATTEMPTED_SHARED_STOP":
        return BharatStockMemberFeatureV2(
            slot.feature,
            "NOT_ATTEMPTED",
            "NOT_ESTABLISHED",
            "NOT_ESTABLISHED",
            "BLOCKED_BY_SHARED_FAILURE",
            None,
        )
    return BharatStockMemberFeatureV2(
        slot.feature,
        "INSUFFICIENT_EVIDENCE",
        "NOT_ESTABLISHED",
        "NOT_ESTABLISHED",
        slot.failure_reason or slot.failure_code or "PRICE_EVIDENCE_UNAVAILABLE",
        None,
    )


def build_bharatstock_research_packet_v2(  # noqa: C901 - explicit slot matrix
    inputs: tuple[BharatStockFeatureInputV2, ...],
    mapping_binding: AdmittedCurrentResearchBindingV2,
) -> BharatStockResearchPacketV2:
    """Build one admitted packet from explicit archive-bound feature slots."""
    if (
        type(inputs) is not tuple
        or len(inputs) != 3
        or tuple(item.feature for item in inputs) != _FEATURES
        or any(type(item) is not BharatStockFeatureInputV2 for item in inputs)
    ):
        raise ValueError("invalid BharatStock V2 feature inputs")
    mapping = validate_current_research_binding_v2(mapping_binding)
    expected_members = tuple(item.instrument for item in mapping.members)
    retained: dict[str, RetainedCaptureRevisionV2] = {}
    for item in inputs:
        if item.state == "RETAINED_REVISION":
            revision = validate_retained_capture_binding_v2(item.retained_capture)
            if (
                revision.request.sessions != item.requested_sessions
                or revision.request.members != expected_members
                or revision.request.selection_identity_sha256
                != mapping.ordered_selection_identity_sha256
                or revision.request.schedule_identity_sha256
                != mapping.schedule_identity_sha256
                or revision.request.decision_cutoff != mapping.decision_cutoff
            ):
                raise ValueError("BharatStock V2 feature window substitution")
            retained[item.feature] = revision
    first = next(iter(retained.values()), None)
    for revision in retained.values():
        if (
            first is None
            or revision.request.members != first.request.members
            or revision.request.selection_identity_sha256
            != first.request.selection_identity_sha256
            or revision.request.schedule_identity_sha256
            != first.request.schedule_identity_sha256
            or revision.request.decision_cutoff != first.request.decision_cutoff
            or revision.price_basis != first.price_basis
            or revision.provider_source != first.provider_source
            or revision.source_profile != first.source_profile
        ):
            raise ValueError("BharatStock V2 feature revision substitution")
    shared_inputs = [
        item for item in inputs if item.state == "NOT_ATTEMPTED_SHARED_STOP"
    ]
    stop_references = {item.stop_reference for item in shared_inputs}
    stop_times = {item.executed_at for item in shared_inputs}
    if len(stop_references) > 1 or len(stop_times) > 1:
        raise ValueError("BharatStock V2 shared-stop substitution")
    runtime = bharatstock_research_runtime_code_identity_v2()
    slots = tuple(_slot(item, runtime) for item in inputs)
    requested = tuple(slot.feature for slot in slots if slot.state != "UNREQUESTED")
    projected: list[BharatStockResearchMemberV2] = []
    with localcontext(Context(prec=64, rounding=ROUND_HALF_EVEN)):
        for position, member in enumerate(expected_members):
            features: list[BharatStockMemberFeatureV2] = []
            for slot in slots:
                if slot.state == "UNREQUESTED":
                    continue
                if slot.state != "RETAINED_REVISION":
                    features.append(_failure_member_feature(slot))
                    continue
                revision = retained[slot.feature]
                result = revision.members[position]
                bars = _bars_for(revision, position)
                comparison = _comparability(slot.feature, position, retained)
                if result.evidence_state != "OBSERVED" or bars is None:
                    availability: _Availability = (
                        "NOT_ATTEMPTED"
                        if result.evidence_state == "NOT_ATTEMPTED"
                        else "INSUFFICIENT_EVIDENCE"
                    )
                    features.append(
                        BharatStockMemberFeatureV2(
                            slot.feature,
                            availability,
                            "NOT_ESTABLISHED",
                            "NOT_ESTABLISHED",
                            result.reason or "PRICE_EVIDENCE_UNAVAILABLE",
                            None,
                        )
                    )
                    continue
                if comparison == "CONFLICTED" and slot.feature != "CANDLE_GEOMETRY":
                    features.append(
                        BharatStockMemberFeatureV2(
                            slot.feature,
                            "DEPENDENCY_BLOCKED",
                            "CONFLICTED",
                            "CONFLICTED",
                            "CROSS_SESSION_COMPARABILITY_CONFLICT",
                            None,
                        )
                    )
                    continue
                fact: V2Fact
                if slot.feature == "CANDLE_GEOMETRY":
                    fact = _geometry(bars[-1])
                elif slot.feature == "PREVIOUS_CLOSE_COMPARISON":
                    fact = _comparison(bars)
                else:
                    fact = _market_structure(
                        result.member,
                        bars,
                        cast(_RetainedPriceBasis, revision.price_basis),
                    )
                features.append(
                    BharatStockMemberFeatureV2(
                        slot.feature,
                        "OBSERVED",
                        "SUPPORTED",
                        comparison,
                        None,
                        fact,
                    )
                )
            projected.append(
                BharatStockResearchMemberV2(
                    member,
                    None
                    if first is None
                    else cast(_RetainedPriceBasis, first.price_basis),
                    tuple(features),
                )
            )
    members = tuple(projected)
    coverage = tuple(_coverage(feature, members) for feature in requested)
    stopped = bool(shared_inputs)
    stop_code = next(iter(stop_references)) if stopped else None
    stop_time = next(iter(stop_times)) if stopped else None
    preimage = {
        "contract_version": _CONTRACT,
        "schema_identity_sha256": _SCHEMA_IDENTITY,
        "configuration_identity_sha256": _CONFIGURATION_IDENTITY,
        "runtime_code_identity_sha256": runtime,
        "selection_identity_sha256": mapping.ordered_selection_identity_sha256,
        "execution_state": "STOPPED" if stopped else "COMPLETED",
        "shared_stop_code": stop_code,
        "shared_stop_time": stop_time,
        "feature_slots": slots,
        "coverage": coverage,
        "members": members,
    }
    packet = object.__new__(BharatStockResearchPacketV2)
    for name, value in {
        **preimage,
        "result_identity_sha256": _digest(preimage),
        "_admission_seal": object(),
    }.items():
        object.__setattr__(packet, name, value)
    if not _validate_packet(packet):
        raise ValueError("invalid BharatStock V2 packet")
    _admit(packet)
    return packet


__all__ = [
    "BharatStockCandleGeometryFactV2",
    "BharatStockFeatureCoverageV2",
    "BharatStockFeatureInputV2",
    "BharatStockFeatureSlotV2",
    "BharatStockFeatureSourceV2",
    "BharatStockMemberFeatureV2",
    "BharatStockPreviousCloseComparisonFactV2",
    "BharatStockResearchMemberV2",
    "BharatStockResearchPacketV2",
    "STRUCTURE_CALCULATION_IDENTITY_SHA256_V1",
    "STRUCTURE_SCHEMA_IDENTITY_SHA256_V1",
    "bharatstock_research_packet_semantics_are_valid_v2",
    "bharatstock_research_runtime_code_identity_v2",
    "build_bharatstock_research_packet_v2",
    "current_market_structure_runtime_code_identity_v1",
    "validate_bharatstock_research_packet_v2",
]
