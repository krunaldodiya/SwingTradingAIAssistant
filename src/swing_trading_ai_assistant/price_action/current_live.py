"""Deterministic current/live Price Action facts over exact S19 and S20 bars.

The core evaluates explicit already-admitted evidence only. It performs no I/O,
provider access, historical qualification, forecasting, or trade advice.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
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
DirectionV1: TypeAlias = Literal["UP", "DOWN", "UNCHANGED"]
SessionRangeStateV1: TypeAlias = Literal["FLAT", "NON_FLAT"]

CONTRACT_VERSION_V1: Final = "current-supplied-cohort-price-action@v1"
PRICE_ACTION_SESSION_COUNT_V1: Final = 21
PRICE_ACTION_COHORT_SIZE_MIN_V1: Final = 1
PRICE_ACTION_COHORT_SIZE_MAX_V1: Final = 50
_MAX_DECIMAL_COEFFICIENT_DIGITS: Final = 128
_MIN_DECIMAL_EXPONENT: Final = -128
_MAX_DECIMAL_EXPONENT: Final = 128
_MAX_CANONICAL_DECIMAL_CHARACTERS: Final = 258
PRICE_ACTION_DECIMAL_OBJECT_BYTES_MAX_V1: Final = 192
PRICE_ACTION_GRAPH_DEPTH_MAX_V1: Final = 32
PRICE_ACTION_GRAPH_NODES_MAX_V1: Final = 200_000
PRICE_ACTION_TUPLE_ITEMS_MAX_V1: Final = 1_050
PRICE_ACTION_STRING_BYTES_MAX_V1: Final = 4_096
PRICE_ACTION_STRING_CHARACTERS_MAX_V1: Final = 4_096
PRICE_ACTION_BYTES_MAX_V1: Final = 4_194_304
PRICE_ACTION_INTEGER_BITS_MAX_V1: Final = 256
PRICE_ACTION_MARKET_STRUCTURE_PIVOTS_PER_MEMBER_MAX_V1: Final = 34
PRICE_ACTION_MARKET_STRUCTURE_EVENTS_PER_MEMBER_MAX_V1: Final = 20
_DIGEST_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_RUNTIME_MANIFEST_MODULE: Final = (
    "swing_trading_ai_assistant.price_action.current_live_runtime_identity_manifest"
)
_RUNTIME_MANIFEST: Final = (
    "src/swing_trading_ai_assistant/price_action/"
    "current_live_runtime_identity_manifest.py"
)
_RUNTIME_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/current_corporate_action_screen.py",
    "src/swing_trading_ai_assistant/market_data/current_same_pass_daily_v4.py",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
    "src/swing_trading_ai_assistant/market_structure/__init__.py",
    "src/swing_trading_ai_assistant/market_structure/current_live.py",
    "src/swing_trading_ai_assistant/market_structure/current_same_pass_v4.py",
    "src/swing_trading_ai_assistant/price_action/__init__.py",
    "src/swing_trading_ai_assistant/price_action/current_live.py",
    "src/swing_trading_ai_assistant/price_action/current_same_pass_v4.py",
)

PRICE_ACTION_REASON_ORDER_V1: Final = (
    "RAW_EVIDENCE_INSUFFICIENT",
    "RAW_RESULT_BINDING_MISMATCH",
    "RAW_GRID_BINDING_MISMATCH",
    "SESSION_WINDOW_INVALID",
    "MEMBER_GRID_INCOMPLETE",
    "RAW_BAR_FUTURE_KNOWN",
    "CORPORATE_ACTION_SCREEN_INSUFFICIENT",
    "CORPORATE_ACTION_SCREEN_BINDING_MISMATCH",
    "MARKET_STRUCTURE_INSUFFICIENT",
    "MARKET_STRUCTURE_BINDING_MISMATCH",
)


def _require_digest(value: object, name: str) -> None:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _valid_isin(value: object) -> bool:
    if type(value) is not str or re.fullmatch(r"[A-Z0-9]{12}", value) is None:
        return False
    digits = "".join(
        character if character.isdigit() else str(ord(character) - 55)
        for character in value
    )
    total = 0
    for position, character in enumerate(reversed(digits)):
        digit = int(character)
        if position % 2:
            digit *= 2
            digit = digit - 9 if digit > 9 else digit
        total += digit
    return total % 10 == 0


def _valid_effective_symbol(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= 64
        and len(value.encode("utf-8")) <= 64
    )


def _finite_decimal_parts(value: Decimal) -> tuple[int, tuple[int, ...], int]:
    if (
        type(value) is not Decimal
        or sys.getsizeof(value) > PRICE_ACTION_DECIMAL_OBJECT_BYTES_MAX_V1
        or not value.is_finite()
    ):
        raise ValueError("exact Decimal must be finite and storage-bounded")
    sign, digits, exponent = value.as_tuple()
    if (
        type(exponent) is not int
        or len(digits) > _MAX_DECIMAL_COEFFICIENT_DIGITS
        or not _MIN_DECIMAL_EXPONENT <= exponent <= _MAX_DECIMAL_EXPONENT
    ):
        raise ValueError("exact Decimal exceeds the bounded representation")
    fixed_characters = (
        len(digits) + exponent
        if exponent >= 0
        else len(digits) + 1
        if -exponent < len(digits)
        else 2 - exponent
    ) + sign
    if fixed_characters > _MAX_CANONICAL_DECIMAL_CHARACTERS:
        raise ValueError("exact Decimal fixed-point representation is too large")
    return sign, digits, exponent


def _scaled_coefficient_digit_count(
    parts: tuple[int, tuple[int, ...], int], target_exponent: int
) -> int:
    _, digits, exponent = parts
    first_nonzero = next(
        (position for position, digit in enumerate(digits) if digit), len(digits)
    )
    if first_nonzero == len(digits):
        return 1
    return len(digits) - first_nonzero + exponent - target_exponent


def _positive_exact_difference_is_bounded(  # pyright: ignore[reportUnusedFunction]
    left: Decimal, right: Decimal
) -> bool:
    try:
        left_parts = _finite_decimal_parts(left)
        right_parts = _finite_decimal_parts(right)
        if left <= 0 or right <= 0:
            return False
        target_exponent = min(left_parts[2], right_parts[2])
        return (
            _scaled_coefficient_digit_count(left_parts, target_exponent)
            <= _MAX_DECIMAL_COEFFICIENT_DIGITS
            and _scaled_coefficient_digit_count(right_parts, target_exponent)
            <= _MAX_DECIMAL_COEFFICIENT_DIGITS
        )
    except ValueError:
        return False


def _decimal_text(value: Decimal) -> str:
    sign, digits, exponent = _finite_decimal_parts(value)
    coefficient = "".join(str(digit) for digit in digits).lstrip("0") or "0"
    if coefficient == "0":
        return "0"
    if exponent >= 0:
        rendered = coefficient + "0" * exponent
    else:
        point = len(coefficient) + exponent
        rendered = (
            "0." + "0" * (-point) + coefficient
            if point <= 0
            else coefficient[:point] + "." + coefficient[point:]
        )
        rendered = rendered.rstrip("0").rstrip(".")
    return ("-" if sign else "") + rendered


def _json_value(value: object) -> object:
    if type(value) is Decimal:
        return _decimal_text(value)
    if type(value) is datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical datetime must be timezone-aware")
        return (
            value.astimezone(UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if type(value) is date:
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _json_value(getattr(value, item.name))
            for item in fields(value)
            if hasattr(value, item.name)
        }
    if type(value) is dict:
        mapping = cast(dict[object, object], value)
        return {str(key): _json_value(item) for key, item in mapping.items()}
    if isinstance(value, Mapping):
        raise ValueError("canonical mappings must be plain dictionaries")
    if type(value) in (tuple, list):
        sequence = cast(tuple[object, ...] | list[object], value)
        return [_json_value(item) for item in sequence]
    if type(value) in (str, int, bool) or value is None:
        return value
    raise ValueError("canonical value has an unsupported type")


def _canonical_bytes(value: object, *, omit: frozenset[str] = frozenset()) -> bytes:
    projected = _json_value(value)
    if type(projected) is not dict:
        raise ValueError("canonical identity root must be a dataclass or mapping")
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


def current_price_action_identity_sha256_v1(
    value: object, *, omit: frozenset[str]
) -> str:
    """Return the Price Action contract's canonical object identity."""

    return sha256(_canonical_bytes(value, omit=omit)).hexdigest()


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
        _RUNTIME_SOURCES[4]: "swing_trading_ai_assistant.market_structure.current_live",
        _RUNTIME_SOURCES[5]: (
            "swing_trading_ai_assistant.market_structure.current_same_pass_v4"
        ),
        _RUNTIME_SOURCES[6]: "swing_trading_ai_assistant.price_action",
        _RUNTIME_SOURCES[7]: __name__,
        _RUNTIME_SOURCES[8]: (
            "swing_trading_ai_assistant.price_action.current_same_pass_v4"
        ),
        _RUNTIME_MANIFEST: _RUNTIME_MANIFEST_MODULE,
    }
    source = Path(__file__)
    root = source.parent.parent
    if not source.is_absolute() or root.name != "swing_trading_ai_assistant":
        raise ValueError("Price Action runtime identity invalid")
    try:
        return runtime_source_sha256(names[relative], root, relative)
    except (KeyError, ValueError):
        raise ValueError("Price Action runtime identity invalid") from None


def current_price_action_runtime_code_identity_v1() -> str:
    """Verify the reviewed closed source map and return its composite identity."""

    try:
        raw = importlib.import_module(
            _RUNTIME_MANIFEST_MODULE
        ).CURRENT_PRICE_ACTION_RUNTIME_SOURCE_DIGESTS_V1
    except (AttributeError, ImportError):
        raise ValueError("Price Action runtime identity invalid") from None
    if type(raw) is not dict:
        raise ValueError("Price Action runtime identity invalid")
    mapping = cast(dict[str, object], raw)
    if tuple(mapping) != _RUNTIME_SOURCES or any(
        type(digest) is not str
        or _DIGEST_RE.fullmatch(digest) is None
        or _runtime_source_sha(path) != digest
        for path, digest in mapping.items()
    ):
        raise ValueError("Price Action runtime identity invalid")
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


def ordered_price_action_reasons_v1(reasons: set[str]) -> tuple[str, ...]:
    if not reasons <= set(PRICE_ACTION_REASON_ORDER_V1):
        raise ValueError("invalid Price Action reason")
    return tuple(reason for reason in PRICE_ACTION_REASON_ORDER_V1 if reason in reasons)


def _schema_identity_preimage_v1() -> dict[str, object]:
    return {
        "contract_version": CONTRACT_VERSION_V1,
        "canonical_serialization": {
            "json": "UTF-8; sorted keys; compact separators; ensure_ascii=false",
            "terminator": "single-LF",
            "decimal": "exact finite fixed-point string; no exponent or ambient rounding",
            "datetime": "UTC; six fractional digits; Z suffix",
            "date": "ISO-8601",
            "identity": "SHA-256 over canonical bytes excluding named identity field",
        },
        "report": {
            "contract_version": CONTRACT_VERSION_V1,
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
            "comparison_session": "S0 date",
            "previous_session": "S19 date",
            "decision_session": "S20 date",
            "raw_grid_identity_sha256": "sha256|null",
            "corporate_action_screen_identity_sha256": "sha256|null",
            "market_structure_report_identity_sha256": "sha256|null",
            "members": "ordered tuple[member] nonempty for OBSERVED; null otherwise",
            "reasons": "ordered tuple[reason]; OBSERVED empty; insufficient nonempty",
            "report_identity_sha256": "sha256",
            "construction": "public constructor rejects; private exact-boundary mint only",
        },
        "member": {
            "isin": "12-character canonical ISIN",
            "exchange": "literal NSE",
            "effective_symbol": "1..64 byte NSE symbol",
            "previous_session": "S19 date",
            "session": "S20 date",
            "previous_bar_identity_sha256": "sha256",
            "current_bar_identity_sha256": "sha256",
            "market_structure_member_identity_sha256": "sha256",
            "candle_direction": "UP|DOWN|UNCHANGED",
            "session_range_state": "FLAT|NON_FLAT",
            "range_size": "exact nonnegative Decimal",
            "body_size": "exact nonnegative Decimal",
            "upper_wick_size": "exact nonnegative Decimal",
            "lower_wick_size": "exact nonnegative Decimal",
            "open_vs_previous_close": "UP|DOWN|UNCHANGED",
            "open_to_previous_close_distance": "exact nonnegative Decimal",
            "close_vs_previous_close": "UP|DOWN|UNCHANGED",
            "close_to_previous_close_distance": "exact nonnegative Decimal",
            "member_identity_sha256": "sha256",
        },
        "reason_order": list(PRICE_ACTION_REASON_ORDER_V1),
        "cohort_size": [1, PRICE_ACTION_COHORT_SIZE_MAX_V1],
        "decimal_bounds": {
            "coefficient_digits_max": _MAX_DECIMAL_COEFFICIENT_DIGITS,
            "exponent_min": _MIN_DECIMAL_EXPONENT,
            "exponent_max": _MAX_DECIMAL_EXPONENT,
            "canonical_characters_max": _MAX_CANONICAL_DECIMAL_CHARACTERS,
        },
        "caller_bounds": {
            "cohort_size_min": PRICE_ACTION_COHORT_SIZE_MIN_V1,
            "cohort_size_max": PRICE_ACTION_COHORT_SIZE_MAX_V1,
            "graph_depth_max": PRICE_ACTION_GRAPH_DEPTH_MAX_V1,
            "graph_nodes_max": PRICE_ACTION_GRAPH_NODES_MAX_V1,
            "tuple_items_max": PRICE_ACTION_TUPLE_ITEMS_MAX_V1,
            "string_bytes_max": PRICE_ACTION_STRING_BYTES_MAX_V1,
            "bytes_max": PRICE_ACTION_BYTES_MAX_V1,
            "integer_bits_max": PRICE_ACTION_INTEGER_BITS_MAX_V1,
            "market_structure_pivots_per_member_max": (
                PRICE_ACTION_MARKET_STRUCTURE_PIVOTS_PER_MEMBER_MAX_V1
            ),
            "market_structure_events_per_member_max": (
                PRICE_ACTION_MARKET_STRUCTURE_EVENTS_PER_MEMBER_MAX_V1
            ),
        },
        "session_count": PRICE_ACTION_SESSION_COUNT_V1,
    }


SCHEMA_IDENTITY_SHA256_V1: Final = current_price_action_identity_sha256_v1(
    _schema_identity_preimage_v1(), omit=frozenset()
)


def _calculation_identity_preimage_v1() -> dict[str, object]:
    return {
        "session_positions": {"previous": 19, "current": 20},
        "direction": {"greater": "UP", "less": "DOWN", "equal": "UNCHANGED"},
        "range_state": {"high_equals_low": "FLAT", "high_greater_low": "NON_FLAT"},
        "facts": {
            "range_size": "H20-L20",
            "body_size": "abs(C20-O20)",
            "upper_wick_size": "H20-max(O20,C20)",
            "lower_wick_size": "min(O20,C20)-L20",
            "open_relation": "O20 cmp C19",
            "open_distance": "abs(O20-C19)",
            "close_relation": "C20 cmp C19",
            "close_distance": "abs(C20-C19)",
        },
        "arithmetic": "integer-scaled Decimal; no float/division/rounding/context",
        "geometry": "range=upper_wick+body+lower_wick in scaled integers",
    }


CALCULATION_IDENTITY_SHA256_V1: Final = current_price_action_identity_sha256_v1(
    _calculation_identity_preimage_v1(), omit=frozenset()
)


def _configuration_identity_preimage_v1() -> dict[str, object]:
    return {
        "session_count": PRICE_ACTION_SESSION_COUNT_V1,
        "cohort_size_min": PRICE_ACTION_COHORT_SIZE_MIN_V1,
        "cohort_size_max": PRICE_ACTION_COHORT_SIZE_MAX_V1,
        "decimal_bounds": {
            "coefficient_digits_max": _MAX_DECIMAL_COEFFICIENT_DIGITS,
            "exponent_min": _MIN_DECIMAL_EXPONENT,
            "exponent_max": _MAX_DECIMAL_EXPONENT,
            "canonical_characters_max": _MAX_CANONICAL_DECIMAL_CHARACTERS,
            "object_bytes_max": PRICE_ACTION_DECIMAL_OBJECT_BYTES_MAX_V1,
        },
        "request_contract": "current-supplied-cohort-market-regime@v3",
        "raw_grid_contract": "current-same-pass-raw-daily-grid@v1",
        "screen_contract": "current-supplied-cohort-corporate-action-screen@v1",
        "market_structure_contract": "current-supplied-cohort-market-structure@v1",
        "provider": "UPSTOX",
        "price_basis": "RAW",
        "interval": "1d-derived-from-retained-1m",
        "temporal_scope": "CURRENT_SAME_PASS_ONLY",
        "partial_current_session": "IGNORED",
        "caller_bounds": {
            "graph_depth_max": PRICE_ACTION_GRAPH_DEPTH_MAX_V1,
            "graph_nodes_max": PRICE_ACTION_GRAPH_NODES_MAX_V1,
            "tuple_items_max": PRICE_ACTION_TUPLE_ITEMS_MAX_V1,
            "string_characters_max": PRICE_ACTION_STRING_CHARACTERS_MAX_V1,
            "string_bytes_max": PRICE_ACTION_STRING_BYTES_MAX_V1,
            "bytes_max": PRICE_ACTION_BYTES_MAX_V1,
            "integer_bits_max": PRICE_ACTION_INTEGER_BITS_MAX_V1,
            "market_structure_pivots_per_member_max": (
                PRICE_ACTION_MARKET_STRUCTURE_PIVOTS_PER_MEMBER_MAX_V1
            ),
            "market_structure_events_per_member_max": (
                PRICE_ACTION_MARKET_STRUCTURE_EVENTS_PER_MEMBER_MAX_V1
            ),
        },
    }


CONFIGURATION_IDENTITY_SHA256_V1: Final = current_price_action_identity_sha256_v1(
    _configuration_identity_preimage_v1(),
    omit=frozenset(),
)


def _scaled_integer(value: Decimal, exponent: int) -> int:
    sign, digits, value_exponent = _finite_decimal_parts(value)
    coefficient = int("".join(str(digit) for digit in digits) or "0")
    scaled = coefficient * 10 ** (value_exponent - exponent)
    return -scaled if sign else scaled


def _decimal_from_scaled(value: int, exponent: int) -> Decimal:
    if value == 0:
        return Decimal(0)
    sign = int(value < 0)
    digits = tuple(int(character) for character in str(abs(value)))
    return Decimal((sign, digits, exponent))


def _exact_difference(left: Decimal, right: Decimal) -> Decimal:
    exponent = min(_finite_decimal_parts(left)[2], _finite_decimal_parts(right)[2])
    return _decimal_from_scaled(
        _scaled_integer(left, exponent) - _scaled_integer(right, exponent), exponent
    )


def _absolute_exact_difference(  # pyright: ignore[reportUnusedFunction]
    left: Decimal, right: Decimal
) -> Decimal:
    difference = _exact_difference(left, right)
    exponent = _finite_decimal_parts(difference)[2]
    return _decimal_from_scaled(
        abs(_scaled_integer(difference, exponent)),
        exponent,
    )


def _geometry_is_exact(
    range_size: Decimal,
    upper_wick_size: Decimal,
    body_size: Decimal,
    lower_wick_size: Decimal,
) -> bool:
    exponent = min(
        _finite_decimal_parts(range_size)[2],
        _finite_decimal_parts(upper_wick_size)[2],
        _finite_decimal_parts(body_size)[2],
        _finite_decimal_parts(lower_wick_size)[2],
    )
    return _scaled_integer(range_size, exponent) == (
        _scaled_integer(upper_wick_size, exponent)
        + _scaled_integer(body_size, exponent)
        + _scaled_integer(lower_wick_size, exponent)
    )


def _direction(  # pyright: ignore[reportUnusedFunction]
    left: Decimal, right: Decimal
) -> DirectionV1:
    if left > right:
        return "UP"
    if left < right:
        return "DOWN"
    return "UNCHANGED"


def _positive_finite_decimal(  # pyright: ignore[reportUnusedFunction]
    value: object, name: str
) -> None:
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a finite positive Decimal")


@dataclass(frozen=True, slots=True)
class CurrentPriceActionMemberV1:
    isin: str
    exchange: str
    effective_symbol: str
    previous_session: date
    session: date
    previous_bar_identity_sha256: str
    current_bar_identity_sha256: str
    market_structure_member_identity_sha256: str
    candle_direction: DirectionV1
    session_range_state: SessionRangeStateV1
    range_size: Decimal
    body_size: Decimal
    upper_wick_size: Decimal
    lower_wick_size: Decimal
    open_vs_previous_close: DirectionV1
    open_to_previous_close_distance: Decimal
    close_vs_previous_close: DirectionV1
    close_to_previous_close_distance: Decimal
    member_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not _valid_isin(self.isin)
            or type(self.exchange) is not str
            or self.exchange != "NSE"
            or _valid_effective_symbol(self.effective_symbol) is False
            or type(self.previous_session) is not date
            or type(self.session) is not date
            or self.previous_session >= self.session
            or type(self.candle_direction) is not str
            or self.candle_direction not in ("UP", "DOWN", "UNCHANGED")
            or type(self.session_range_state) is not str
            or self.session_range_state not in ("FLAT", "NON_FLAT")
            or type(self.open_vs_previous_close) is not str
            or self.open_vs_previous_close not in ("UP", "DOWN", "UNCHANGED")
            or type(self.close_vs_previous_close) is not str
            or self.close_vs_previous_close not in ("UP", "DOWN", "UNCHANGED")
        ):
            raise ValueError("Price Action member fields are invalid")
        for name in (
            "previous_bar_identity_sha256",
            "current_bar_identity_sha256",
            "market_structure_member_identity_sha256",
        ):
            _require_digest(getattr(self, name), name)
        values = (
            self.range_size,
            self.body_size,
            self.upper_wick_size,
            self.lower_wick_size,
            self.open_to_previous_close_distance,
            self.close_to_previous_close_distance,
        )
        if any(
            type(value) is not Decimal or not value.is_finite() or value < 0
            for value in values
        ):
            raise ValueError("Price Action sizes must be finite nonnegative Decimals")
        for value in values:
            _finite_decimal_parts(value)
        if not _geometry_is_exact(
            self.range_size,
            self.upper_wick_size,
            self.body_size,
            self.lower_wick_size,
        ):
            raise ValueError("Price Action geometry is inconsistent")
        if (
            self.session_range_state == "FLAT"
            and any(value != 0 for value in values[:4])
        ) or (self.session_range_state == "NON_FLAT" and self.range_size <= 0):
            raise ValueError("Price Action range state is inconsistent")
        object.__setattr__(
            self,
            "member_identity_sha256",
            current_price_action_identity_sha256_v1(
                self, omit=frozenset({"member_identity_sha256"})
            ),
        )


@dataclass(frozen=True, slots=True, init=False)
class CurrentPriceActionReportV1:
    contract_version: Literal["current-supplied-cohort-price-action@v1"]
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
    previous_session: date
    decision_session: date
    raw_grid_identity_sha256: str | None
    corporate_action_screen_identity_sha256: str | None
    market_structure_report_identity_sha256: str | None
    members: tuple[CurrentPriceActionMemberV1, ...] | None
    reasons: tuple[str, ...]
    report_identity_sha256: str = field(init=False)

    def __init__(self, *arguments: object, **keywords: object) -> None:
        del arguments, keywords
        raise ValueError(
            "Price Action reports are minted only by the exact evidence boundary"
        )

    def _validate_projection(self) -> None:
        if type(self.evidence_state) is not str:
            raise ValueError("invalid Price Action evidence state")
        success_identities = (
            self.raw_grid_identity_sha256,
            self.corporate_action_screen_identity_sha256,
            self.market_structure_report_identity_sha256,
        )
        if self.evidence_state == "OBSERVED":
            if (
                type(self.members) is not tuple
                or not PRICE_ACTION_COHORT_SIZE_MIN_V1
                <= len(self.members)
                <= PRICE_ACTION_COHORT_SIZE_MAX_V1
                or any(
                    type(member) is not CurrentPriceActionMemberV1
                    for member in self.members
                )
                or any(
                    member.previous_session != self.previous_session
                    or member.session != self.decision_session
                    for member in self.members
                )
                or self.reasons
                or any(value is None for value in success_identities)
            ):
                raise ValueError("observed Price Action report is inconsistent")
            if not (
                self.comparison_session < self.previous_session < self.decision_session
            ):
                raise ValueError("observed Price Action sessions are inconsistent")
            identities = tuple(
                (member.isin, member.exchange, member.effective_symbol)
                for member in self.members
            )
            if identities != tuple(sorted(identities)) or len(set(identities)) != len(
                identities
            ):
                raise ValueError("Price Action members are not canonical")
            for value in success_identities:
                _require_digest(value, "Price Action success identity")
            return
        if self.evidence_state != "INSUFFICIENT_EVIDENCE" or (
            self.members is not None
            or not self.reasons
            or any(value is not None for value in success_identities)
        ):
            raise ValueError("insufficient Price Action report is inconsistent")

    def __post_init__(self) -> None:
        if (
            self.contract_version != CONTRACT_VERSION_V1
            or self.schema_identity_sha256 != SCHEMA_IDENTITY_SHA256_V1
            or self.calculation_identity_sha256 != CALCULATION_IDENTITY_SHA256_V1
            or self.configuration_identity_sha256 != CONFIGURATION_IDENTITY_SHA256_V1
            or self.temporal_scope != "CURRENT_SAME_PASS_ONLY"
            or self.historical_availability_claim is not False
            or type(self.decision_cutoff) is not datetime
            or self.decision_cutoff.tzinfo is not UTC
            or type(self.comparison_session) is not date
            or type(self.previous_session) is not date
            or type(self.decision_session) is not date
            or not self.comparison_session < self.decision_session
        ):
            raise ValueError("Price Action report contract identity is invalid")
        for name in (
            "runtime_code_identity_sha256",
            "request_identity_sha256",
            "canonical_cohort_identity_sha256",
            "schedule_identity_sha256",
        ):
            _require_digest(getattr(self, name), name)
        if (
            type(self.reasons) is not tuple
            or any(type(reason) is not str for reason in self.reasons)
            or ordered_price_action_reasons_v1(set(self.reasons)) != self.reasons
        ):
            raise ValueError("Price Action report reasons are invalid")
        self._validate_projection()
        object.__setattr__(
            self,
            "report_identity_sha256",
            current_price_action_identity_sha256_v1(
                self, omit=frozenset({"report_identity_sha256"})
            ),
        )

    def canonical_json_bytes(self) -> bytes:
        """Return stable full-report bytes, including the report identity."""

        return _canonical_bytes(self)


def _mint_current_price_action_report_v1(  # pyright: ignore[reportUnusedFunction]
    *,
    evidence_state: EvidenceState,
    request_identity_sha256: str,
    canonical_cohort_identity_sha256: str,
    schedule_identity_sha256: str,
    decision_cutoff: datetime,
    comparison_session: date,
    previous_session: date,
    decision_session: date,
    raw_grid_identity_sha256: str | None,
    corporate_action_screen_identity_sha256: str | None,
    market_structure_report_identity_sha256: str | None,
    members: tuple[CurrentPriceActionMemberV1, ...] | None,
    reasons: tuple[str, ...],
) -> CurrentPriceActionReportV1:
    value = object.__new__(CurrentPriceActionReportV1)
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
        "previous_session": previous_session,
        "decision_session": decision_session,
        "raw_grid_identity_sha256": raw_grid_identity_sha256,
        "corporate_action_screen_identity_sha256": corporate_action_screen_identity_sha256,
        "market_structure_report_identity_sha256": market_structure_report_identity_sha256,
        "members": members,
        "reasons": reasons,
    }
    for name, field_value in values.items():
        object.__setattr__(value, name, field_value)
    value.__post_init__()
    return value


RUNTIME_CODE_IDENTITY_SHA256_V1: Final = current_price_action_runtime_code_identity_v1()
