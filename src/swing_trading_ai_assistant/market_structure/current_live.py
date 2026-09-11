"""Deterministic current/live Market Structure over one exact 21-session grid.

This module only classifies supplied, completed daily bars. It performs no I/O,
provider access, historical qualification, forecasting, or trade advice.
"""

from __future__ import annotations

import importlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Final, Literal, TypeAlias, cast

from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)

EvidenceState: TypeAlias = Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
PivotKind: TypeAlias = Literal["SWING_HIGH", "SWING_LOW"]
PivotRelation: TypeAlias = Literal["HH", "LH", "HL", "LL"]
UnclassifiedReason: TypeAlias = Literal["INITIAL", "EQUAL_PRICE"]
Trend: TypeAlias = Literal[
    "UPTREND", "DOWNTREND", "RANGE_OR_TRANSITION", "INSUFFICIENT_STRUCTURE"
]
StructureState: TypeAlias = Literal["CONFIRMED", "INSUFFICIENT_STRUCTURE"]
BreakEvent: TypeAlias = Literal["BOS", "CHOCH"]
Direction: TypeAlias = Literal["UP", "DOWN"]

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_SESSIONS = 21
_MAX_COHORT_SIZE = 50
_PIVOT_RADIUS = 2


def _require_digest(value: str, name: str) -> None:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, datetime):
        return (
            value.astimezone(UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _json_value(getattr(value, item.name))
            for item in fields(value)
            if hasattr(value, item.name)
        }
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {str(key): _json_value(item) for key, item in mapping.items()}
    if isinstance(value, (tuple, list)):
        sequence = cast(tuple[object, ...] | list[object], value)
        return [_json_value(item) for item in sequence]
    return value


def _canonical_bytes(value: object, *, omit: frozenset[str] = frozenset()) -> bytes:
    projected = _json_value(value)
    if not isinstance(projected, dict):
        raise TypeError("canonical identity root must be a dataclass or mapping")
    document = cast(dict[str, object], projected)
    for key in omit:
        document.pop(key, None)
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def current_market_structure_identity_sha256_v1(
    value: object, *, omit: frozenset[str]
) -> str:
    return sha256(_canonical_bytes(value, omit=omit)).hexdigest()


CONTRACT_VERSION_V1: Final = "current-supplied-cohort-market-structure@v1"
_RUNTIME_MANIFEST_MODULE: Final = (
    "swing_trading_ai_assistant.market_structure.current_live_runtime_identity_manifest"
)
_RUNTIME_MANIFEST: Final = (
    "src/swing_trading_ai_assistant/market_structure/"
    "current_live_runtime_identity_manifest.py"
)
_RUNTIME_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/current_corporate_action_screen.py",
    "src/swing_trading_ai_assistant/market_data/current_same_pass_daily_v4.py",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
    "src/swing_trading_ai_assistant/market_structure/__init__.py",
    "src/swing_trading_ai_assistant/market_structure/current_live.py",
    "src/swing_trading_ai_assistant/market_structure/current_same_pass_v4.py",
)


def _runtime_source_sha(relative: str) -> str:
    names = {
        _RUNTIME_SOURCES[0]: (
            "swing_trading_ai_assistant.market_data.current_corporate_action_screen"
        ),
        _RUNTIME_SOURCES[1]: (
            "swing_trading_ai_assistant.market_data.current_same_pass_daily_v4"
        ),
        _RUNTIME_SOURCES[2]: (
            "swing_trading_ai_assistant.market_data.runtime_source_verifier"
        ),
        _RUNTIME_SOURCES[3]: "swing_trading_ai_assistant.market_structure",
        _RUNTIME_SOURCES[4]: __name__,
        _RUNTIME_SOURCES[5]: (
            "swing_trading_ai_assistant.market_structure.current_same_pass_v4"
        ),
        _RUNTIME_MANIFEST: _RUNTIME_MANIFEST_MODULE,
    }
    source = Path(__file__)
    root = source.parent.parent
    if not source.is_absolute() or root.name != "swing_trading_ai_assistant":
        raise ValueError("Market Structure runtime identity invalid")
    try:
        return runtime_source_sha256(names[relative], root, relative)
    except (KeyError, ValueError):
        raise ValueError("Market Structure runtime identity invalid") from None


def current_market_structure_runtime_code_identity_v1() -> str:
    """Verify the reviewed closed source map and return its composite identity."""

    try:
        raw = importlib.import_module(
            _RUNTIME_MANIFEST_MODULE
        ).CURRENT_MARKET_STRUCTURE_RUNTIME_SOURCE_DIGESTS_V1
    except (AttributeError, ImportError):
        raise ValueError("Market Structure runtime identity invalid") from None
    if type(raw) is not dict:
        raise ValueError("Market Structure runtime identity invalid")
    mapping = cast(dict[str, object], raw)
    if tuple(mapping) != _RUNTIME_SOURCES or any(
        type(digest) is not str
        or _DIGEST_RE.fullmatch(digest) is None
        or _runtime_source_sha(path) != digest
        for path, digest in mapping.items()
    ):
        raise ValueError("Market Structure runtime identity invalid")
    manifest_digest = _runtime_source_sha(_RUNTIME_MANIFEST)
    composite = b"".join(
        path.encode() + b"\0" + cast(str, mapping[path]).encode() + b"\0"
        for path in _RUNTIME_SOURCES
    )
    return sha256(
        composite
        + _RUNTIME_MANIFEST.encode()
        + b"\0"
        + manifest_digest.encode()
        + b"\0"
    ).hexdigest()


MARKET_STRUCTURE_REASON_ORDER_V1: Final = (
    "REQUEST_BINDING_MISMATCH",
    "RAW_EVIDENCE_INSUFFICIENT",
    "RAW_RESULT_BINDING_MISMATCH",
    "RAW_GRID_BINDING_MISMATCH",
    "SESSION_WINDOW_INVALID",
    "MEMBER_GRID_INCOMPLETE",
    "RAW_BAR_FUTURE_KNOWN",
    "CORPORATE_ACTION_SCREEN_INSUFFICIENT",
    "CORPORATE_ACTION_SCREEN_BINDING_MISMATCH",
)


def _schema_identity_preimage_v1() -> dict[str, object]:
    return {
        "contract_version": CONTRACT_VERSION_V1,
        "canonical_serialization": {
            "json": "UTF-8; sorted keys; compact separators; ensure_ascii=false",
            "terminator": "single-LF",
            "decimal": "exact finite fixed-point string; no exponent or ambient rounding",
            "datetime": "UTC; six fractional digits; Z suffix",
            "date": "ISO-8601",
            "enum": "string value",
            "tuple": "ordered JSON array",
            "identity": "SHA-256 over canonical bytes excluding named identity field",
        },
        "report": {
            "contract_version": "literal current-supplied-cohort-market-structure@v1",
            "schema_identity_sha256": "sha256",
            "calculation_identity_sha256": "sha256",
            "configuration_identity_sha256": "sha256",
            "runtime_code_identity_sha256": "sha256",
            "evidence_state": "OBSERVED|INSUFFICIENT_EVIDENCE",
            "temporal_scope": "literal CURRENT_SAME_PASS_ONLY",
            "historical_availability_claim": "literal false",
            "request_identity_sha256": "sha256",
            "canonical_cohort_identity_sha256": "sha256",
            "schedule_identity_sha256": "sha256",
            "decision_cutoff": "UTC datetime",
            "comparison_session": "date",
            "decision_session": "date",
            "raw_grid_identity_sha256": "sha256|null",
            "corporate_action_screen_identity_sha256": "sha256|null",
            "members": "ordered tuple[member] nonempty for OBSERVED; null for insufficient",
            "reasons": "ordered tuple[reason]; OBSERVED empty; insufficient nonempty",
            "report_identity_sha256": "sha256",
            "construction": "public constructor rejects; private exact-boundary mint only",
        },
        "member": {
            "isin": "12-character canonical ISIN",
            "exchange": "literal NSE",
            "effective_symbol": "1..64 byte NSE symbol",
            "input_bar_identities_sha256": "ordered tuple[sha256]; exactly 21",
            "structure_state": "CONFIRMED|INSUFFICIENT_STRUCTURE",
            "trend": ("UPTREND|DOWNTREND|RANGE_OR_TRANSITION|INSUFFICIENT_STRUCTURE"),
            "pivots": "ordered tuple[pivot]; zero or more",
            "events": "ordered tuple[event]; zero or more",
            "member_identity_sha256": "sha256",
        },
        "pivot": {
            "kind": "SWING_HIGH|SWING_LOW",
            "position": "integer 2..18",
            "confirmation_position": "integer position+2; 4..20",
            "session": "date at position",
            "confirmation_session": "date at confirmation_position",
            "price": "positive finite Decimal price",
            "relation": "HH|LH|HL|LL|null",
            "unclassified_reason": "INITIAL|EQUAL_PRICE|null",
            "source_bar_identity_sha256": "sha256",
            "comparison_bar_identities_sha256": "four ordered sha256 values",
            "pivot_identity_sha256": "sha256",
        },
        "event": {
            "event": "BOS|CHOCH",
            "direction": "UP|DOWN",
            "position": "integer 1..20",
            "session": "date at position",
            "close": "positive finite Decimal price",
            "broken_pivot_identity_sha256": "sha256",
            "broken_level": "positive finite Decimal price",
            "prior_trend": "UPTREND|DOWNTREND",
            "previous_close_bar_identity_sha256": "sha256",
            "current_close_bar_identity_sha256": "sha256",
            "event_identity_sha256": "sha256",
        },
        "outcome_projection": {
            "OBSERVED": "members nonempty; reasons empty; both upstream identities set",
            "INSUFFICIENT_EVIDENCE": (
                "members null; ordered reasons nonempty; raw-grid and screen "
                "identities both null"
            ),
        },
        "reason_order": list(MARKET_STRUCTURE_REASON_ORDER_V1),
        "cohort_size": [1, _MAX_COHORT_SIZE],
        "pivot_radius": _PIVOT_RADIUS,
        "session_count": _EXPECTED_SESSIONS,
    }


SCHEMA_IDENTITY_SHA256_V1: Final = current_market_structure_identity_sha256_v1(
    _schema_identity_preimage_v1(),
    omit=frozenset(),
)


def _calculation_identity_preimage_v1() -> dict[str, object]:
    return {
        "session_count": 21,
        "pivot_radius": 2,
        "pivot_comparison": "strict-two-left-two-right",
        "confirmation": "candidate-position-plus-two",
        "relation": "same-kind-previous-confirmed-pivot",
        "trend": {
            "as_of": "confirmation_position<=requested-position",
            "HH+HL": "UPTREND",
            "LH+LL": "DOWNTREND",
            "other": "RANGE_OR_TRANSITION",
            "fewer-than-two-each": "INSUFFICIENT_STRUCTURE",
        },
        "break": {
            "basis": "close-only-strict-first-crossing",
            "eligible_pivot": "confirmation_position<break_position",
            "trend_basis": "trend as of break_position-1",
            "level": "latest-confirmed-unconsumed pivot by direction",
            "consume": "a crossed level is unavailable to later lookup",
            "range_or_insufficient": "consume-without-public-event",
        },
        "event_table": {
            "UPTREND+UP": "BOS",
            "UPTREND+DOWN": "CHOCH",
            "DOWNTREND+DOWN": "BOS",
            "DOWNTREND+UP": "CHOCH",
        },
        "current_state": "trend as of position 20; pivots confirmed at 20 are eligible",
    }


CALCULATION_IDENTITY_SHA256_V1: Final = current_market_structure_identity_sha256_v1(
    _calculation_identity_preimage_v1(),
    omit=frozenset(),
)
CONFIGURATION_IDENTITY_SHA256_V1: Final = current_market_structure_identity_sha256_v1(
    {
        "request_contract": "current-supplied-cohort-market-regime@v3",
        "raw_grid_contract": "current-same-pass-raw-daily-grid@v1",
        "screen_contract": "current-supplied-cohort-corporate-action-screen@v1",
        "provider": "UPSTOX",
        "price_basis": "RAW",
        "interval": "1d-derived-from-retained-1m",
        "temporal_scope": "CURRENT_SAME_PASS_ONLY",
        "partial_current_session": "IGNORED",
    },
    omit=frozenset(),
)


def ordered_market_structure_reasons_v1(reasons: set[str]) -> tuple[str, ...]:
    if not reasons <= set(MARKET_STRUCTURE_REASON_ORDER_V1):
        raise ValueError("invalid Market Structure reason")
    return tuple(
        reason for reason in MARKET_STRUCTURE_REASON_ORDER_V1 if reason in reasons
    )


def _positive_finite_decimal(value: Decimal, name: str) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True, slots=True)
class _MarketStructureBarV1:
    """One completed, raw, locally aggregated daily bar."""

    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    raw_bar_identity_sha256: str

    def __post_init__(self) -> None:
        if type(self.session) is not date:
            raise ValueError("market structure bar session must be a date")
        for name in ("open", "high", "low", "close"):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise ValueError(f"market structure bar {name} must be Decimal")
            _positive_finite_decimal(value, f"market structure bar {name}")
        if self.low > self.high:
            raise ValueError("market structure bar low exceeds high")
        if not self.low <= self.open <= self.high:
            raise ValueError("market structure bar open is outside low/high")
        if not self.low <= self.close <= self.high:
            raise ValueError("market structure bar close is outside low/high")
        if type(self.volume) is not int or self.volume < 0:
            raise ValueError(
                "market structure bar volume must be a non-negative integer"
            )
        _require_digest(self.raw_bar_identity_sha256, "raw_bar_identity_sha256")


@dataclass(frozen=True, slots=True)
class MarketStructureMathBarV1:
    """Provider-neutral completed bar for deterministic structure mathematics."""

    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source_bar_identity_sha256: str

    def __post_init__(self) -> None:
        if type(self.session) is not date:
            raise ValueError("market structure bar session must be a date")
        for name in ("open", "high", "low", "close"):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise ValueError(f"market structure bar {name} must be Decimal")
            _positive_finite_decimal(value, f"market structure bar {name}")
        if self.low > self.high:
            raise ValueError("market structure bar low exceeds high")
        if not self.low <= self.open <= self.high:
            raise ValueError("market structure bar open is outside low/high")
        if not self.low <= self.close <= self.high:
            raise ValueError("market structure bar close is outside low/high")
        if type(self.volume) is not int or self.volume < 0:
            raise ValueError(
                "market structure bar volume must be a non-negative integer"
            )
        _require_digest(self.source_bar_identity_sha256, "source_bar_identity_sha256")


@dataclass(frozen=True, slots=True)
class MarketStructureMathMemberInputV1:
    """Provider-neutral member and exact completed bar grid for structure math."""

    isin: str
    exchange: str
    effective_symbol: str
    bars: tuple[MarketStructureMathBarV1, ...]

    def __post_init__(self) -> None:
        if (
            type(self.isin) is not str
            or type(self.exchange) is not str
            or type(self.effective_symbol) is not str
            or not self.isin
            or not self.exchange
            or not self.effective_symbol
            or type(self.bars) is not tuple
            or any(type(bar) is not MarketStructureMathBarV1 for bar in self.bars)
        ):
            raise ValueError("market structure math-member identity is incomplete")
        if len(self.bars) != _EXPECTED_SESSIONS:
            raise ValueError("market structure math-member requires exactly 21 bars")
        sessions = tuple(bar.session for bar in self.bars)
        if sessions != tuple(sorted(sessions)) or len(set(sessions)) != len(sessions):
            raise ValueError(
                "market structure math-member sessions must be unique and ordered"
            )


_StructureMathBarV1: TypeAlias = _MarketStructureBarV1 | MarketStructureMathBarV1


def _source_bar_identity(bar: _StructureMathBarV1) -> str:
    if isinstance(bar, _MarketStructureBarV1):
        return bar.raw_bar_identity_sha256
    return bar.source_bar_identity_sha256


@dataclass(frozen=True, slots=True)
class _CurrentMarketStructureMemberInputV1:
    """Canonical member and its exact completed 21-session bar grid."""

    isin: str
    exchange: str
    effective_symbol: str
    bars: tuple[_MarketStructureBarV1, ...]

    def __post_init__(self) -> None:
        if (
            type(self.isin) is not str
            or type(self.exchange) is not str
            or type(self.effective_symbol) is not str
            or not self.isin
            or not self.exchange
            or not self.effective_symbol
            or type(self.bars) is not tuple
            or any(type(bar) is not _MarketStructureBarV1 for bar in self.bars)
        ):
            raise ValueError("market structure member input identity is incomplete")
        if len(self.bars) != _EXPECTED_SESSIONS:
            raise ValueError("market structure member input requires exactly 21 bars")
        sessions = tuple(bar.session for bar in self.bars)
        if sessions != tuple(sorted(sessions)) or len(set(sessions)) != len(sessions):
            raise ValueError(
                "market structure member input sessions must be unique and ordered"
            )


_StructureMathMemberInputV1: TypeAlias = (
    _CurrentMarketStructureMemberInputV1 | MarketStructureMathMemberInputV1
)


@dataclass(frozen=True, slots=True)
class _CurrentMarketStructureInputV1:
    """Provider-neutral, exact current-same-pass evidence projection."""

    decision_cutoff: datetime
    comparison_session: date
    decision_session: date
    request_identity_sha256: str
    canonical_cohort_identity_sha256: str
    schedule_identity_sha256: str
    raw_grid_identity_sha256: str
    corporate_action_screen_identity_sha256: str
    members: tuple[_CurrentMarketStructureMemberInputV1, ...]
    input_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.decision_cutoff) is not datetime
            or self.decision_cutoff.tzinfo is None
            or self.decision_cutoff.utcoffset() is None
        ):
            raise ValueError("market structure decision cutoff must be timezone-aware")
        if (
            type(self.comparison_session) is not date
            or type(self.decision_session) is not date
            or self.comparison_session >= self.decision_session
        ):
            raise ValueError("market structure session window is invalid")
        for name in (
            "request_identity_sha256",
            "canonical_cohort_identity_sha256",
            "schedule_identity_sha256",
            "raw_grid_identity_sha256",
            "corporate_action_screen_identity_sha256",
        ):
            _require_digest(getattr(self, name), name)
        if type(self.members) is not tuple or any(
            type(member) is not _CurrentMarketStructureMemberInputV1
            for member in self.members
        ):
            raise ValueError("market structure input members are malformed")
        if not 1 <= len(self.members) <= _MAX_COHORT_SIZE:
            raise ValueError("market structure input requires 1 to 50 members")
        ordered = tuple(
            sorted(
                self.members,
                key=lambda member: (
                    member.isin,
                    member.exchange,
                    member.effective_symbol,
                ),
            )
        )
        identities = tuple(
            (member.isin, member.exchange, member.effective_symbol)
            for member in ordered
        )
        if len(set(identities)) != len(identities):
            raise ValueError(
                "market structure input contains duplicate canonical members"
            )
        expected_sessions = tuple(bar.session for bar in ordered[0].bars)
        if (
            expected_sessions[0] != self.comparison_session
            or expected_sessions[-1] != self.decision_session
            or any(
                tuple(bar.session for bar in member.bars) != expected_sessions
                for member in ordered
            )
        ):
            raise ValueError(
                "market structure input members do not share the exact session window"
            )
        object.__setattr__(self, "members", ordered)
        object.__setattr__(
            self,
            "input_identity_sha256",
            current_market_structure_identity_sha256_v1(
                self, omit=frozenset({"input_identity_sha256"})
            ),
        )


@dataclass(frozen=True, slots=True)
class MarketStructurePivotV1:
    kind: PivotKind
    position: int
    confirmation_position: int
    session: date
    confirmation_session: date
    price: Decimal
    relation: PivotRelation | None
    unclassified_reason: UnclassifiedReason | None
    source_bar_identity_sha256: str
    comparison_bar_identities_sha256: tuple[str, str, str, str]
    pivot_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if self.kind not in ("SWING_HIGH", "SWING_LOW"):
            raise ValueError("invalid Market Structure pivot kind")
        if self.confirmation_position != self.position + _PIVOT_RADIUS:
            raise ValueError("Market Structure pivot confirmation position is invalid")
        if self.relation is None and self.unclassified_reason is None:
            raise ValueError("unclassified Market Structure pivot requires a reason")
        if self.relation is not None and self.unclassified_reason is not None:
            raise ValueError(
                "classified Market Structure pivot cannot have an unclassified reason"
            )
        _positive_finite_decimal(self.price, "Market Structure pivot price")
        _require_digest(self.source_bar_identity_sha256, "source_bar_identity_sha256")
        for digest in self.comparison_bar_identities_sha256:
            _require_digest(digest, "comparison_bar_identity_sha256")
        object.__setattr__(
            self,
            "pivot_identity_sha256",
            current_market_structure_identity_sha256_v1(
                self, omit=frozenset({"pivot_identity_sha256"})
            ),
        )


@dataclass(frozen=True, slots=True)
class MarketStructureEventV1:
    event: BreakEvent
    direction: Direction
    position: int
    session: date
    close: Decimal
    broken_pivot_identity_sha256: str
    broken_level: Decimal
    prior_trend: Trend
    previous_close_bar_identity_sha256: str
    current_close_bar_identity_sha256: str
    event_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if self.event not in ("BOS", "CHOCH"):
            raise ValueError("invalid Market Structure event")
        if self.direction not in ("UP", "DOWN"):
            raise ValueError("invalid Market Structure event direction")
        if self.prior_trend not in ("UPTREND", "DOWNTREND"):
            raise ValueError(
                "Market Structure event requires a directional prior trend"
            )
        _positive_finite_decimal(self.close, "Market Structure event close")
        _positive_finite_decimal(self.broken_level, "Market Structure broken level")
        for digest in (
            self.broken_pivot_identity_sha256,
            self.previous_close_bar_identity_sha256,
            self.current_close_bar_identity_sha256,
        ):
            _require_digest(digest, "Market Structure event source identity")
        object.__setattr__(
            self,
            "event_identity_sha256",
            current_market_structure_identity_sha256_v1(
                self, omit=frozenset({"event_identity_sha256"})
            ),
        )


@dataclass(frozen=True, slots=True)
class CurrentMarketStructureMemberV1:
    isin: str
    exchange: str
    effective_symbol: str
    input_bar_identities_sha256: tuple[str, ...]
    structure_state: StructureState
    trend: Trend
    pivots: tuple[MarketStructurePivotV1, ...]
    events: tuple[MarketStructureEventV1, ...]
    member_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if len(self.input_bar_identities_sha256) != _EXPECTED_SESSIONS:
            raise ValueError(
                "Market Structure member input-bar identity set is invalid"
            )
        for digest in self.input_bar_identities_sha256:
            _require_digest(digest, "Market Structure member input-bar identity")
        object.__setattr__(
            self,
            "member_identity_sha256",
            current_market_structure_identity_sha256_v1(
                self, omit=frozenset({"member_identity_sha256"})
            ),
        )


@dataclass(frozen=True, slots=True, init=False)
class CurrentMarketStructureReportV1:
    contract_version: Literal["current-supplied-cohort-market-structure@v1"]
    schema_identity_sha256: str
    calculation_identity_sha256: str
    configuration_identity_sha256: str
    runtime_code_identity_sha256: str
    evidence_state: EvidenceState
    temporal_scope: Literal["CURRENT_SAME_PASS_ONLY"]
    historical_availability_claim: Literal[False]
    request_identity_sha256: str
    canonical_cohort_identity_sha256: str
    schedule_identity_sha256: str
    decision_cutoff: datetime
    comparison_session: date
    decision_session: date
    raw_grid_identity_sha256: str | None
    corporate_action_screen_identity_sha256: str | None
    members: tuple[CurrentMarketStructureMemberV1, ...] | None
    reasons: tuple[str, ...]
    report_identity_sha256: str = field(init=False)

    def __init__(self, *arguments: object, **keywords: object) -> None:
        del arguments, keywords
        raise ValueError(
            "Market Structure reports are minted only by the exact evidence boundary"
        )

    def __post_init__(self) -> None:
        if (
            self.contract_version != CONTRACT_VERSION_V1
            or self.schema_identity_sha256 != SCHEMA_IDENTITY_SHA256_V1
            or self.calculation_identity_sha256 != CALCULATION_IDENTITY_SHA256_V1
            or self.configuration_identity_sha256 != CONFIGURATION_IDENTITY_SHA256_V1
        ):
            raise ValueError("Market Structure report contract identity is invalid")
        for name in (
            "runtime_code_identity_sha256",
            "request_identity_sha256",
            "canonical_cohort_identity_sha256",
            "schedule_identity_sha256",
        ):
            _require_digest(getattr(self, name), name)
        success_identities = (
            self.raw_grid_identity_sha256,
            self.corporate_action_screen_identity_sha256,
        )
        if (
            type(self.reasons) is not tuple
            or any(type(reason) is not str for reason in self.reasons)
            or ordered_market_structure_reasons_v1(set(self.reasons)) != self.reasons
        ):
            raise ValueError("Market Structure report reasons are invalid")
        if self.evidence_state == "OBSERVED":
            if (
                self.members is None
                or not self.members
                or self.reasons
                or any(value is None for value in success_identities)
            ):
                raise ValueError("observed Market Structure report is inconsistent")
            for value in success_identities:
                _require_digest(cast(str, value), "Market Structure success identity")
        elif self.evidence_state == "INSUFFICIENT_EVIDENCE":
            if (
                self.members is not None
                or not self.reasons
                or any(value is not None for value in success_identities)
            ):
                raise ValueError("insufficient Market Structure report is inconsistent")
        else:
            raise ValueError("invalid Market Structure evidence state")
        object.__setattr__(
            self,
            "report_identity_sha256",
            current_market_structure_identity_sha256_v1(
                self, omit=frozenset({"report_identity_sha256"})
            ),
        )

    def canonical_json_bytes(self) -> bytes:
        """Return stable full-report bytes, including the report identity."""

        return _canonical_bytes(self)


def _mint_current_market_structure_report_v1(
    *,
    evidence_state: EvidenceState,
    request_identity_sha256: str,
    canonical_cohort_identity_sha256: str,
    schedule_identity_sha256: str,
    decision_cutoff: datetime,
    comparison_session: date,
    decision_session: date,
    raw_grid_identity_sha256: str | None,
    corporate_action_screen_identity_sha256: str | None,
    members: tuple[CurrentMarketStructureMemberV1, ...] | None,
    reasons: tuple[str, ...],
) -> CurrentMarketStructureReportV1:
    value = object.__new__(CurrentMarketStructureReportV1)
    values: dict[str, object] = {
        "contract_version": CONTRACT_VERSION_V1,
        "schema_identity_sha256": SCHEMA_IDENTITY_SHA256_V1,
        "calculation_identity_sha256": CALCULATION_IDENTITY_SHA256_V1,
        "configuration_identity_sha256": CONFIGURATION_IDENTITY_SHA256_V1,
        "runtime_code_identity_sha256": RUNTIME_CODE_IDENTITY_SHA256_V1,
        "evidence_state": evidence_state,
        "temporal_scope": "CURRENT_SAME_PASS_ONLY",
        "historical_availability_claim": False,
        "request_identity_sha256": request_identity_sha256,
        "canonical_cohort_identity_sha256": canonical_cohort_identity_sha256,
        "schedule_identity_sha256": schedule_identity_sha256,
        "decision_cutoff": decision_cutoff,
        "comparison_session": comparison_session,
        "decision_session": decision_session,
        "raw_grid_identity_sha256": raw_grid_identity_sha256,
        "corporate_action_screen_identity_sha256": (
            corporate_action_screen_identity_sha256
        ),
        "members": members,
        "reasons": reasons,
    }
    for name, field_value in values.items():
        object.__setattr__(value, name, field_value)
    value.__post_init__()
    return value


def _relation(
    kind: PivotKind, price: Decimal, previous: MarketStructurePivotV1 | None
) -> tuple[PivotRelation | None, UnclassifiedReason | None]:
    if previous is None:
        return None, "INITIAL"
    if price == previous.price:
        return None, "EQUAL_PRICE"
    if kind == "SWING_HIGH":
        return ("HH" if price > previous.price else "LH"), None
    return ("HL" if price > previous.price else "LL"), None


def _detect_pivots(
    bars: tuple[_StructureMathBarV1, ...],
) -> tuple[MarketStructurePivotV1, ...]:
    pivots: list[MarketStructurePivotV1] = []
    latest: dict[PivotKind, MarketStructurePivotV1 | None] = {
        "SWING_HIGH": None,
        "SWING_LOW": None,
    }
    for position in range(_PIVOT_RADIUS, len(bars) - _PIVOT_RADIUS):
        current = bars[position]
        neighbors = (
            bars[position - 2],
            bars[position - 1],
            bars[position + 1],
            bars[position + 2],
        )
        kinds: list[PivotKind] = []
        if all(current.high > neighbor.high for neighbor in neighbors):
            kinds.append("SWING_HIGH")
        if all(current.low < neighbor.low for neighbor in neighbors):
            kinds.append("SWING_LOW")
        for kind in kinds:
            price = current.high if kind == "SWING_HIGH" else current.low
            relation, reason = _relation(kind, price, latest[kind])
            pivot = MarketStructurePivotV1(
                kind=kind,
                position=position,
                confirmation_position=position + _PIVOT_RADIUS,
                session=current.session,
                confirmation_session=bars[position + _PIVOT_RADIUS].session,
                price=price,
                relation=relation,
                unclassified_reason=reason,
                source_bar_identity_sha256=_source_bar_identity(current),
                comparison_bar_identities_sha256=(
                    _source_bar_identity(neighbors[0]),
                    _source_bar_identity(neighbors[1]),
                    _source_bar_identity(neighbors[2]),
                    _source_bar_identity(neighbors[3]),
                ),
            )
            pivots.append(pivot)
            latest[kind] = pivot
    return tuple(pivots)


def _trend_at(pivots: tuple[MarketStructurePivotV1, ...], position: int) -> Trend:
    confirmed = tuple(
        pivot for pivot in pivots if pivot.confirmation_position <= position
    )
    highs = tuple(pivot for pivot in confirmed if pivot.kind == "SWING_HIGH")
    lows = tuple(pivot for pivot in confirmed if pivot.kind == "SWING_LOW")
    if len(highs) < 2 or len(lows) < 2:
        return "INSUFFICIENT_STRUCTURE"
    high_relation = highs[-1].relation
    low_relation = lows[-1].relation
    if high_relation == "HH" and low_relation == "HL":
        return "UPTREND"
    if high_relation == "LH" and low_relation == "LL":
        return "DOWNTREND"
    return "RANGE_OR_TRANSITION"


def _latest_confirmed(
    pivots: tuple[MarketStructurePivotV1, ...],
    kind: PivotKind,
    position: int,
    consumed: set[str],
) -> MarketStructurePivotV1 | None:
    candidates = tuple(
        pivot
        for pivot in pivots
        if (
            pivot.kind == kind
            and pivot.confirmation_position <= position
            and pivot.pivot_identity_sha256 not in consumed
        )
    )
    return candidates[-1] if candidates else None


def _detect_events(
    bars: tuple[_StructureMathBarV1, ...],
    pivots: tuple[MarketStructurePivotV1, ...],
) -> tuple[MarketStructureEventV1, ...]:
    events: list[MarketStructureEventV1] = []
    consumed: set[str] = set()
    for position in range(1, len(bars)):
        previous_close = bars[position - 1].close
        close = bars[position].close
        prior_position = position - 1
        trend = _trend_at(pivots, prior_position)
        high = _latest_confirmed(pivots, "SWING_HIGH", prior_position, consumed)
        low = _latest_confirmed(pivots, "SWING_LOW", prior_position, consumed)
        crossed: tuple[MarketStructurePivotV1, Direction] | None = None
        if high is not None and previous_close <= high.price and close > high.price:
            crossed = high, "UP"
        elif low is not None and previous_close >= low.price and close < low.price:
            crossed = low, "DOWN"
        if crossed is None:
            continue
        pivot, direction = crossed
        consumed.add(pivot.pivot_identity_sha256)
        if trend not in ("UPTREND", "DOWNTREND"):
            continue
        event: BreakEvent
        if (trend == "UPTREND" and direction == "UP") or (
            trend == "DOWNTREND" and direction == "DOWN"
        ):
            event = "BOS"
        else:
            event = "CHOCH"
        events.append(
            MarketStructureEventV1(
                event=event,
                direction=direction,
                position=position,
                session=bars[position].session,
                close=close,
                broken_pivot_identity_sha256=pivot.pivot_identity_sha256,
                broken_level=pivot.price,
                prior_trend=trend,
                previous_close_bar_identity_sha256=_source_bar_identity(
                    bars[position - 1]
                ),
                current_close_bar_identity_sha256=_source_bar_identity(bars[position]),
            )
        )
    return tuple(events)


def _evaluate_member(
    value: _StructureMathMemberInputV1,
) -> CurrentMarketStructureMemberV1:
    pivots = _detect_pivots(value.bars)
    trend = _trend_at(pivots, len(value.bars) - 1)
    structure_state: StructureState = (
        "INSUFFICIENT_STRUCTURE" if trend == "INSUFFICIENT_STRUCTURE" else "CONFIRMED"
    )
    return CurrentMarketStructureMemberV1(
        isin=value.isin,
        exchange=value.exchange,
        effective_symbol=value.effective_symbol,
        input_bar_identities_sha256=tuple(
            _source_bar_identity(bar) for bar in value.bars
        ),
        structure_state=structure_state,
        trend=trend,
        pivots=pivots,
        events=_detect_events(value.bars, pivots),
    )


def evaluate_market_structure_math_member_v1(
    value: MarketStructureMathMemberInputV1,
) -> CurrentMarketStructureMemberV1:
    """Evaluate one provider-neutral, immutable 21-session math input."""
    if type(value) is not MarketStructureMathMemberInputV1:
        raise ValueError("market structure math-member input is invalid")
    return _evaluate_member(value)


def _evaluate_current_market_structure_v1(
    value: _CurrentMarketStructureInputV1,
) -> CurrentMarketStructureReportV1:
    """Classify supplied current-session evidence without external effects."""

    members = tuple(_evaluate_member(member) for member in value.members)
    return _mint_current_market_structure_report_v1(
        evidence_state="OBSERVED",
        request_identity_sha256=value.request_identity_sha256,
        canonical_cohort_identity_sha256=value.canonical_cohort_identity_sha256,
        schedule_identity_sha256=value.schedule_identity_sha256,
        decision_cutoff=value.decision_cutoff,
        comparison_session=value.comparison_session,
        decision_session=value.decision_session,
        raw_grid_identity_sha256=value.raw_grid_identity_sha256,
        corporate_action_screen_identity_sha256=(
            value.corporate_action_screen_identity_sha256
        ),
        members=members,
        reasons=(),
    )


def evaluate_current_market_structure_v1(
    value: _CurrentMarketStructureInputV1,
) -> CurrentMarketStructureReportV1:
    """Evaluate one exact raw-evidence cohort input without external effects."""
    return _evaluate_current_market_structure_v1(value)


RUNTIME_CODE_IDENTITY_SHA256_V1: Final = (
    current_market_structure_runtime_code_identity_v1()
)
