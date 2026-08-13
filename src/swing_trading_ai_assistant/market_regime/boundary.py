"""Pure canonical boundary for the frozen Market Regime V1 contract."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar, TypeVar, cast


class BoundaryAdmissionError(ValueError):
    pass


class SchemaAdmissionError(BoundaryAdmissionError):
    pass


class BoundsAdmissionError(BoundaryAdmissionError):
    pass


class CanonicalJsonAdmissionError(BoundaryAdmissionError):
    pass


class IdentityAdmissionError(BoundaryAdmissionError):
    pass


_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ISIN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]\Z")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9&.\-]{0,31}\Z")
_ASCII = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,255}\Z")
_DECIMAL = re.compile(r"(?:0\.[0-9]*[1-9]|[1-9][0-9]*(?:\.[0-9]*[1-9])?)\Z")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")


class AuthorityIdentityV1(StrEnum):
    NSE_INDICES = "NSE_INDICES"
    NSE_CM = "NSE_CM"
    ADMITTED_EQUITY_FACT_PIPELINE = "ADMITTED_EQUITY_FACT_PIPELINE"


class EvidenceKindV1(StrEnum):
    MEMBERSHIP = "MEMBERSHIP"
    SESSION_SCHEDULE = "SESSION_SCHEDULE"
    PRIOR_CLOSES = "PRIOR_CLOSES"
    CURRENT_CLOSES = "CURRENT_CLOSES"
    CORPORATE_COMPARABILITY = "CORPORATE_COMPARABILITY"


class EvidenceScopeV1(StrEnum):
    DECISION_MEMBERSHIP = "DECISION_MEMBERSHIP"
    TWENTY_PREDECESSORS_DECISION_NEXT = "TWENTY_PREDECESSORS_DECISION_NEXT"
    PRIOR_ENDPOINT_CLOSE = "PRIOR_ENDPOINT_CLOSE"
    CURRENT_ENDPOINT_CLOSE = "CURRENT_ENDPOINT_CLOSE"
    COMPARABILITY_INTERVAL = "COMPARABILITY_INTERVAL"


class EvidenceAttemptFailureV1(StrEnum):
    NOT_RETURNED = "NOT_RETURNED"
    AFTER_EVIDENCE_CUTOFF = "AFTER_EVIDENCE_CUTOFF"
    INVALID_SOURCE_ROW = "INVALID_SOURCE_ROW"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    UNAUTHORIZED_AUTHORITY = "UNAUTHORIZED_AUTHORITY"
    PUBLICATION_UNPROVEN = "PUBLICATION_UNPROVEN"
    CLOCK_UNTRUSTED = "CLOCK_UNTRUSTED"
    LICENCE_UNRESOLVED = "LICENCE_UNRESOLVED"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise SchemaAdmissionError(f"{name} must be a string")
    return value


def validate_sha256(value: object) -> str:
    value = _text(value, "sha256")
    if not _SHA.fullmatch(value):
        raise SchemaAdmissionError("invalid Sha256")
    return value


def validate_local_date(value: object) -> str:
    value = _text(value, "date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise SchemaAdmissionError("invalid LocalDate") from exc
    if parsed.isoformat() != value:
        raise SchemaAdmissionError("noncanonical LocalDate")
    return value


def validate_utc_instant(value: object) -> str:
    value = _text(value, "instant")
    if not _UTC.fullmatch(value):
        raise SchemaAdmissionError("invalid UtcInstant")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise SchemaAdmissionError("invalid UtcInstant") from exc
    return value


def _luhn_isin(value: str) -> bool:
    expanded = "".join(str(ord(c) - 55) if c.isalpha() else c for c in value)
    total = 0
    parity = len(expanded) % 2
    for i, ch in enumerate(expanded):
        n = int(ch)
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def validate_isin(value: object) -> str:
    value = _text(value, "isin")
    if not _ISIN.fullmatch(value) or not _luhn_isin(value):
        raise SchemaAdmissionError("invalid Isin")
    return value


def validate_canonical_symbol(value: object) -> str:
    value = _text(value, "symbol")
    if not _SYMBOL.fullmatch(value):
        raise SchemaAdmissionError("invalid CanonicalSymbol")
    return value


def validate_bounded_ascii(value: object) -> str:
    value = _text(value, "bounded ascii")
    if not _ASCII.fullmatch(value):
        raise SchemaAdmissionError("invalid BoundedAscii")
    return value


def validate_hex_bytes(value: object, *, min_bytes: int, max_bytes: int) -> str:
    value = _text(value, "hex bytes")
    if len(value) % 2 or re.fullmatch(r"[0-9a-f]*", value) is None:
        raise SchemaAdmissionError("invalid HexBytes")
    size = len(value) // 2
    if not min_bytes <= size <= max_bytes:
        raise BoundsAdmissionError("HexBytes outside bounds")
    return value


def validate_canonical_decimal(value: object) -> Decimal:
    value = _text(value, "decimal")
    if len(value) > 32 or not _DECIMAL.fullmatch(value):
        raise SchemaAdmissionError("invalid CanonicalDecimal")
    digits = value.replace(".", "").lstrip("0")
    scale = len(value.split(".", 1)[1]) if "." in value else 0
    if len(digits) > 20 or scale > 10:
        raise SchemaAdmissionError("CanonicalDecimal outside precision")
    return Decimal(value)


def _plain(value: object) -> object:
    if dataclasses.is_dataclass(value):
        return {
            f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)
        }
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_plain(x) for x in cast("Sequence[object]", value)]
    if isinstance(value, dict):
        items = cast("dict[object, object]", value).items()
        if any(not isinstance(key, str) for key, _ in items):
            raise CanonicalJsonAdmissionError("object key must be string")
        return {cast("str", key): _plain(item) for key, item in items}
    if value is None or type(value) in (str, int, bool):
        return value
    raise SchemaAdmissionError(f"unsupported canonical type: {type(value).__name__}")


def _validate_tree(value: object, depth: int = 0) -> None:
    if depth > 16:
        raise BoundsAdmissionError("JSON nesting exceeds 16")
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value or any(
            ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value
        ):
            raise CanonicalJsonAdmissionError("invalid string normalization/control")
    elif isinstance(value, list):
        for x in cast("list[object]", value):
            _validate_tree(x, depth + 1)
    elif isinstance(value, dict):
        for k, v in cast("dict[object, object]", value).items():
            if not isinstance(k, str):
                raise CanonicalJsonAdmissionError("object key must be string")
            _validate_tree(k, depth + 1)
            _validate_tree(v, depth + 1)
    elif value is not None and type(value) not in (int, bool):
        raise CanonicalJsonAdmissionError("floats are forbidden")


def canonical_json_lf(value: Any) -> bytes:
    plain = _plain(value)
    _validate_tree(plain)
    try:
        body = json.dumps(
            plain,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CanonicalJsonAdmissionError("not canonicalizable") from exc
    try:
        return (body + "\n").encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CanonicalJsonAdmissionError("invalid Unicode scalar") from exc


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in pairs:
        if k in out:
            raise CanonicalJsonAdmissionError("duplicate object key")
        out[k] = v
    return out


def _reject_number(_: str) -> None:
    raise CanonicalJsonAdmissionError("JSON floats are forbidden")


def _reject_constant(_: str) -> None:
    raise CanonicalJsonAdmissionError("JSON nonfinite numbers are forbidden")


def parse_canonical_json_lf(  # noqa: C901
    raw: object, *, max_bytes: int, max_depth: int = 16
) -> object:
    if not isinstance(raw, bytes):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise SchemaAdmissionError("canonical bytes required")
    if len(raw) > max_bytes:
        raise BoundsAdmissionError("canonical input too large")
    if (
        raw.startswith(b"\xef\xbb\xbf")
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
    ):
        raise CanonicalJsonAdmissionError("invalid UTF-8/LF profile")
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_constant,
        )
    except CanonicalJsonAdmissionError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalJsonAdmissionError("malformed JSON") from exc
    _validate_tree(value)

    def depth(v: object, d: int = 0) -> int:
        children: Sequence[object]
        if isinstance(v, dict):
            children = tuple(cast("dict[object, object]", v).values())
        elif isinstance(v, list):
            children = cast("list[object]", v)
        else:
            return d
        return max((depth(x, d + 1) for x in children), default=d)

    if depth(value) > max_depth:
        raise BoundsAdmissionError("JSON nesting exceeds bound")
    if canonical_json_lf(value) != raw:
        raise CanonicalJsonAdmissionError("noncanonical JSON bytes")
    return value


def _closed(obj: object, fields: set[str]) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise SchemaAdmissionError("object required")
    result = cast("dict[str, Any]", obj)
    if set(result) != fields:
        raise SchemaAdmissionError("unknown or missing fields")
    return result


def _enum(cls: type[StrEnum], value: Any) -> Any:
    if not isinstance(value, str):
        raise SchemaAdmissionError("enum must be string")
    try:
        return cls(value)
    except ValueError as exc:
        raise SchemaAdmissionError("unknown enum") from exc


@dataclass(frozen=True, slots=True)
class ProvenanceCandidateV1:
    source_object_identity_sha256: str
    source_row_selector: str
    authority_text: str
    source_identity: str
    schema_version_text: str
    object_identity_sha256: str | None
    revision_identity_sha256_text: str | None
    supersedes_identity_sha256_text: str | None
    publication_requirement_text: str
    published_at_text: str | None
    response_completed_at_text: str | None
    retrieved_at_text: str | None
    retained_at_text: str | None

    def __post_init__(self) -> None:
        validate_sha256(self.source_object_identity_sha256)
        validate_bounded_ascii(self.source_row_selector)
        validate_bounded_ascii(self.authority_text)
        validate_bounded_ascii(self.source_identity)
        validate_bounded_ascii(self.schema_version_text)
        validate_bounded_ascii(self.publication_requirement_text)
        if self.object_identity_sha256 is not None:
            validate_sha256(self.object_identity_sha256)
        for v in (
            self.revision_identity_sha256_text,
            self.supersedes_identity_sha256_text,
            self.published_at_text,
            self.response_completed_at_text,
            self.retrieved_at_text,
            self.retained_at_text,
        ):
            if v is not None:
                validate_bounded_ascii(v)

    @classmethod
    def from_dict(cls, o: Any) -> ProvenanceCandidateV1:
        return cls(**_closed(o, {f.name for f in dataclasses.fields(cls)}))


@dataclass(frozen=True, slots=True)
class MembershipCandidateRowV1:
    isin_text: str
    symbol_text: str
    effective_from_text: str
    effective_through_text: str | None
    row_provenance: ProvenanceCandidateV1

    def __post_init__(self) -> None:
        for v in (self.isin_text, self.symbol_text, self.effective_from_text):
            validate_bounded_ascii(v)
        if self.effective_through_text is not None:
            validate_bounded_ascii(self.effective_through_text)
        _require_instance(self.row_provenance, ProvenanceCandidateV1, "row provenance")

    @classmethod
    def from_dict(cls, o: Any) -> MembershipCandidateRowV1:
        d = _closed(o, {f.name for f in dataclasses.fields(cls)})
        d["row_provenance"] = ProvenanceCandidateV1.from_dict(d["row_provenance"])
        return cls(**d)


@dataclass(frozen=True, slots=True)
class DailyCloseCandidateRowV1:
    isin_text: str
    symbol_text: str
    session_date_text: str
    close_text: str
    row_provenance: ProvenanceCandidateV1

    def __post_init__(self) -> None:
        for v in (
            self.isin_text,
            self.symbol_text,
            self.session_date_text,
            self.close_text,
        ):
            validate_bounded_ascii(v)
        _require_instance(self.row_provenance, ProvenanceCandidateV1, "row provenance")

    @classmethod
    def from_dict(cls, o: Any) -> DailyCloseCandidateRowV1:
        d = _closed(o, {f.name for f in dataclasses.fields(cls)})
        d["row_provenance"] = ProvenanceCandidateV1.from_dict(d["row_provenance"])
        return cls(**d)


@dataclass(frozen=True, slots=True)
class MembershipCandidatePayloadV1:
    received_rows: tuple[MembershipCandidateRowV1, ...]

    def __init__(self, received_rows: Sequence[object]):
        rows = _candidate_tuple(
            received_rows, MembershipCandidateRowV1, 51, "membership rows"
        )
        object.__setattr__(self, "received_rows", rows)

    @classmethod
    def from_dict(cls, o: Any) -> MembershipCandidatePayloadV1:
        data = _closed(o, {"received_rows"})
        return cls(_record_array(data["received_rows"], MembershipCandidateRowV1))


@dataclass(frozen=True, slots=True)
class DailyCloseCandidatePayloadV1:
    received_rows: tuple[DailyCloseCandidateRowV1, ...]

    def __init__(self, received_rows: Sequence[object]):
        rows = _candidate_tuple(
            received_rows, DailyCloseCandidateRowV1, 51, "close rows"
        )
        object.__setattr__(self, "received_rows", rows)

    @classmethod
    def from_dict(cls, o: Any) -> DailyCloseCandidatePayloadV1:
        data = _closed(o, {"received_rows"})
        return cls(_record_array(data["received_rows"], DailyCloseCandidateRowV1))


@dataclass(frozen=True, slots=True)
class EvidenceRequestIdentityV1:
    evidence_kind: EvidenceKindV1
    authority: AuthorityIdentityV1
    decision_session: str
    scope: EvidenceScopeV1
    subject_isin: str | None
    subject_session: str | None

    def __post_init__(self) -> None:
        _require_instance(self.evidence_kind, EvidenceKindV1, "evidence kind")
        _require_instance(self.authority, AuthorityIdentityV1, "authority")
        _require_instance(self.scope, EvidenceScopeV1, "scope")
        validate_local_date(self.decision_session)
        if self.subject_isin is not None:
            validate_isin(self.subject_isin)
        if self.subject_session is not None:
            validate_local_date(self.subject_session)

    @classmethod
    def from_dict(cls, o: Any) -> EvidenceRequestIdentityV1:
        d = _closed(o, {f.name for f in dataclasses.fields(cls)})
        d["evidence_kind"] = _enum(EvidenceKindV1, d["evidence_kind"])
        d["authority"] = _enum(AuthorityIdentityV1, d["authority"])
        d["scope"] = _enum(EvidenceScopeV1, d["scope"])
        return cls(**d)

    def key(self) -> tuple[str, ...]:
        return tuple(
            "" if x is None else str(x)
            for x in (
                self.evidence_kind,
                self.authority,
                self.decision_session,
                self.scope,
                self.subject_isin,
                self.subject_session,
            )
        )


@dataclass(frozen=True, slots=True)
class MarketRegimeRequestV1:
    contract_version: str
    segment: str
    decision_session: str
    request_identity_sha256: str
    VERSION: ClassVar[str] = "nifty50-market-regime@v1"

    @classmethod
    def build(cls, decision_session: str) -> MarketRegimeRequestV1:
        validate_local_date(decision_session)
        projection = {
            "contract_version": cls.VERSION,
            "decision_session": decision_session,
            "segment": "NSE_EQ",
        }
        identity = hashlib.sha256(canonical_json_lf(projection)).hexdigest()
        return cls(cls.VERSION, "NSE_EQ", decision_session, identity)

    def __post_init__(self) -> None:
        if self.contract_version != self.VERSION or self.segment != "NSE_EQ":
            raise SchemaAdmissionError("invalid request constants")
        validate_local_date(self.decision_session)
        validate_sha256(self.request_identity_sha256)
        projection = {
            "contract_version": self.VERSION,
            "decision_session": self.decision_session,
            "segment": "NSE_EQ",
        }
        if (
            hashlib.sha256(canonical_json_lf(projection)).hexdigest()
            != self.request_identity_sha256
        ):
            raise IdentityAdmissionError("request identity mismatch")

    def to_dict(self) -> dict[str, Any]:
        return cast("dict[str, Any]", _plain(self))

    def canonical_json_bytes(self) -> bytes:
        raw = canonical_json_lf(self)
        if len(raw) > 4096:
            raise BoundsAdmissionError("request exceeds 4 KiB")
        return raw

    @classmethod
    def from_canonical_json_bytes(cls, raw: bytes) -> MarketRegimeRequestV1:
        d = _closed(
            parse_canonical_json_lf(raw, max_bytes=4096),
            {f.name for f in dataclasses.fields(cls)},
        )
        obj = cls(**d)
        expected = cls.build(obj.decision_session)
        if obj.request_identity_sha256 != expected.request_identity_sha256:
            raise IdentityAdmissionError("request identity mismatch")
        return obj


@dataclass(frozen=True, slots=True)
class ScheduleCandidateRowV1:
    session_date_text: str
    open_at_text: str
    close_at_text: str
    row_provenance: ProvenanceCandidateV1

    def __post_init__(self) -> None:
        for value in (self.session_date_text, self.open_at_text, self.close_at_text):
            validate_bounded_ascii(value)
        _require_instance(self.row_provenance, ProvenanceCandidateV1, "row provenance")

    @classmethod
    def from_dict(cls, obj: Any) -> ScheduleCandidateRowV1:
        data = _closed(obj, {field.name for field in dataclasses.fields(cls)})
        data["row_provenance"] = ProvenanceCandidateV1.from_dict(data["row_provenance"])
        return cls(**data)


@dataclass(frozen=True, slots=True)
class ScheduleBaseCandidateV1:
    received_rows: tuple[ScheduleCandidateRowV1, ...]
    base_schedule_provenance: ProvenanceCandidateV1

    def __init__(
        self,
        received_rows: Sequence[ScheduleCandidateRowV1],
        base_schedule_provenance: ProvenanceCandidateV1,
    ):
        rows = _candidate_tuple(
            received_rows, ScheduleCandidateRowV1, 51, "schedule rows"
        )
        provenance = _require_instance(
            base_schedule_provenance, ProvenanceCandidateV1, "base schedule provenance"
        )
        object.__setattr__(self, "received_rows", rows)
        object.__setattr__(self, "base_schedule_provenance", provenance)

    @classmethod
    def from_dict(cls, obj: Any) -> ScheduleBaseCandidateV1:
        data = _closed(obj, {field.name for field in dataclasses.fields(cls)})
        rows = _record_array(data["received_rows"], ScheduleCandidateRowV1)
        return cls(
            rows, ProvenanceCandidateV1.from_dict(data["base_schedule_provenance"])
        )


@dataclass(frozen=True, slots=True)
class ScheduleCorrectionCandidateV1:
    affected_session_text: str
    correction_kind_text: str
    corrected_open_at_text: str | None
    corrected_close_at_text: str | None
    row_provenance: ProvenanceCandidateV1

    def __post_init__(self) -> None:
        validate_bounded_ascii(self.affected_session_text)
        validate_bounded_ascii(self.correction_kind_text)
        for value in (self.corrected_open_at_text, self.corrected_close_at_text):
            if value is not None:
                validate_bounded_ascii(value)
        _require_instance(self.row_provenance, ProvenanceCandidateV1, "row provenance")

    @classmethod
    def from_dict(cls, obj: Any) -> ScheduleCorrectionCandidateV1:
        data = _closed(obj, {field.name for field in dataclasses.fields(cls)})
        data["row_provenance"] = ProvenanceCandidateV1.from_dict(data["row_provenance"])
        return cls(**data)


_T = TypeVar("_T")


def _require_instance(value: object, item_type: type[_T], name: str) -> _T:
    if not isinstance(value, item_type):
        raise SchemaAdmissionError(f"invalid {name}")
    return value


def _candidate_tuple(
    values: object, item_type: type[_T], maximum: int, name: str
) -> tuple[_T, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise SchemaAdmissionError(f"{name} must be a sequence")
    copied = tuple(cast("Sequence[object]", values))
    if len(copied) > maximum:
        raise BoundsAdmissionError(f"{name} exceed {maximum}")
    if any(not isinstance(item, item_type) for item in copied):
        raise SchemaAdmissionError(f"invalid {name}")
    return cast("tuple[_T, ...]", copied)


def _record_array(value: object, item_type: type[_T]) -> tuple[_T, ...]:
    if not isinstance(value, list):
        raise SchemaAdmissionError("candidate rows must be an array")
    parser = cast("Any", item_type).from_dict
    return tuple(cast("_T", parser(item)) for item in cast("list[object]", value))


@dataclass(frozen=True, slots=True)
class ScheduleCandidatePayloadV1:
    base_schedule: ScheduleBaseCandidateV1 | None
    corrections: tuple[ScheduleCorrectionCandidateV1, ...]

    def __init__(
        self,
        base_schedule: ScheduleBaseCandidateV1 | None,
        corrections: Sequence[ScheduleCorrectionCandidateV1],
    ):
        if base_schedule is not None:
            _require_instance(base_schedule, ScheduleBaseCandidateV1, "base schedule")
        object.__setattr__(self, "base_schedule", base_schedule)
        object.__setattr__(
            self,
            "corrections",
            _candidate_tuple(
                corrections, ScheduleCorrectionCandidateV1, 32, "schedule corrections"
            ),
        )

    @classmethod
    def from_dict(cls, obj: Any) -> ScheduleCandidatePayloadV1:
        data = _closed(obj, {"base_schedule", "corrections"})
        base = (
            None
            if data["base_schedule"] is None
            else ScheduleBaseCandidateV1.from_dict(data["base_schedule"])
        )
        return cls(
            base, _record_array(data["corrections"], ScheduleCorrectionCandidateV1)
        )


@dataclass(frozen=True, slots=True)
class CorporateActionEventCandidateV1:
    event_identity_sha256_text: str
    isin_text: str
    event_kind_text: str
    effective_session_text: str
    row_provenance: ProvenanceCandidateV1

    def __post_init__(self) -> None:
        for value in (
            self.event_identity_sha256_text,
            self.isin_text,
            self.event_kind_text,
            self.effective_session_text,
        ):
            validate_bounded_ascii(value)
        _require_instance(self.row_provenance, ProvenanceCandidateV1, "row provenance")

    @classmethod
    def from_dict(cls, obj: Any) -> CorporateActionEventCandidateV1:
        data = _closed(obj, {field.name for field in dataclasses.fields(cls)})
        data["row_provenance"] = ProvenanceCandidateV1.from_dict(data["row_provenance"])
        return cls(**data)


@dataclass(frozen=True, slots=True)
class CorporateActionStatusProofCandidateV1:
    authority_text: str
    isin_text: str
    interval_from_text: str
    interval_through_text: str
    status_text: str
    checked_events: tuple[CorporateActionEventCandidateV1, ...]
    proof_provenance: ProvenanceCandidateV1

    def __init__(
        self,
        authority_text: str,
        isin_text: str,
        interval_from_text: str,
        interval_through_text: str,
        status_text: str,
        checked_events: Sequence[CorporateActionEventCandidateV1],
        proof_provenance: ProvenanceCandidateV1,
    ):
        for value in (
            authority_text,
            isin_text,
            interval_from_text,
            interval_through_text,
            status_text,
        ):
            validate_bounded_ascii(value)
        object.__setattr__(self, "authority_text", authority_text)
        object.__setattr__(self, "isin_text", isin_text)
        object.__setattr__(self, "interval_from_text", interval_from_text)
        object.__setattr__(self, "interval_through_text", interval_through_text)
        object.__setattr__(self, "status_text", status_text)
        object.__setattr__(
            self,
            "checked_events",
            _candidate_tuple(
                checked_events, CorporateActionEventCandidateV1, 16, "checked events"
            ),
        )
        object.__setattr__(
            self,
            "proof_provenance",
            _require_instance(
                proof_provenance, ProvenanceCandidateV1, "proof provenance"
            ),
        )

    @classmethod
    def from_dict(cls, obj: Any) -> CorporateActionStatusProofCandidateV1:
        data = _closed(obj, {field.name for field in dataclasses.fields(cls)})
        data["checked_events"] = _record_array(
            data["checked_events"], CorporateActionEventCandidateV1
        )
        data["proof_provenance"] = ProvenanceCandidateV1.from_dict(
            data["proof_provenance"]
        )
        return cls(**data)


@dataclass(frozen=True, slots=True)
class NegativeCompletenessProofCandidateV1:
    authority_text: str
    isin_text: str
    interval_from_text: str
    interval_through_text: str
    covered_event_classes_text: str
    completeness_text: str
    proof_provenance: ProvenanceCandidateV1

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            if field.name != "proof_provenance":
                validate_bounded_ascii(getattr(self, field.name))
        _require_instance(
            self.proof_provenance, ProvenanceCandidateV1, "proof provenance"
        )

    @classmethod
    def from_dict(cls, obj: Any) -> NegativeCompletenessProofCandidateV1:
        data = _closed(obj, {field.name for field in dataclasses.fields(cls)})
        data["proof_provenance"] = ProvenanceCandidateV1.from_dict(
            data["proof_provenance"]
        )
        return cls(**data)


@dataclass(frozen=True, slots=True)
class RevisionLineageProofCandidateV1:
    authority_text: str
    isin_text: str
    interval_from_text: str
    interval_through_text: str
    selected_revision_identity_sha256_text: str
    checked_through_text: str
    lineage_status_text: str
    proof_provenance: ProvenanceCandidateV1

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            if field.name != "proof_provenance":
                validate_bounded_ascii(getattr(self, field.name))
        _require_instance(
            self.proof_provenance, ProvenanceCandidateV1, "proof provenance"
        )

    @classmethod
    def from_dict(cls, obj: Any) -> RevisionLineageProofCandidateV1:
        data = _closed(obj, {field.name for field in dataclasses.fields(cls)})
        data["proof_provenance"] = ProvenanceCandidateV1.from_dict(
            data["proof_provenance"]
        )
        return cls(**data)


@dataclass(frozen=True, slots=True)
class IdentityContinuityProofCandidateV1:
    authority_text: str
    isin_text: str
    interval_from_text: str
    interval_through_text: str
    prior_symbol_text: str
    current_symbol_text: str
    continuity_status_text: str
    proof_provenance: ProvenanceCandidateV1

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            if field.name != "proof_provenance":
                validate_bounded_ascii(getattr(self, field.name))
        _require_instance(
            self.proof_provenance, ProvenanceCandidateV1, "proof provenance"
        )

    @classmethod
    def from_dict(cls, obj: Any) -> IdentityContinuityProofCandidateV1:
        data = _closed(obj, {field.name for field in dataclasses.fields(cls)})
        data["proof_provenance"] = ProvenanceCandidateV1.from_dict(
            data["proof_provenance"]
        )
        return cls(**data)


@dataclass(frozen=True, slots=True)
class ComparabilityCandidateRowV1:
    isin_text: str
    interval_from_text: str
    interval_through_text: str
    comparison_basis_text: str
    status_text: str
    status_proof: CorporateActionStatusProofCandidateV1
    negative_completeness_proof: NegativeCompletenessProofCandidateV1
    revision_proof: RevisionLineageProofCandidateV1
    identity_continuity_proof: IdentityContinuityProofCandidateV1
    row_provenance: ProvenanceCandidateV1

    def __post_init__(self) -> None:
        for value in (
            self.isin_text,
            self.interval_from_text,
            self.interval_through_text,
            self.comparison_basis_text,
            self.status_text,
        ):
            validate_bounded_ascii(value)
        for value, item_type, name in (
            (self.status_proof, CorporateActionStatusProofCandidateV1, "status proof"),
            (
                self.negative_completeness_proof,
                NegativeCompletenessProofCandidateV1,
                "negative completeness proof",
            ),
            (self.revision_proof, RevisionLineageProofCandidateV1, "revision proof"),
            (
                self.identity_continuity_proof,
                IdentityContinuityProofCandidateV1,
                "identity continuity proof",
            ),
            (self.row_provenance, ProvenanceCandidateV1, "row provenance"),
        ):
            _require_instance(value, item_type, name)

    @classmethod
    def from_dict(cls, obj: Any) -> ComparabilityCandidateRowV1:
        data = _closed(obj, {field.name for field in dataclasses.fields(cls)})
        data["status_proof"] = CorporateActionStatusProofCandidateV1.from_dict(
            data["status_proof"]
        )
        data["negative_completeness_proof"] = (
            NegativeCompletenessProofCandidateV1.from_dict(
                data["negative_completeness_proof"]
            )
        )
        data["revision_proof"] = RevisionLineageProofCandidateV1.from_dict(
            data["revision_proof"]
        )
        data["identity_continuity_proof"] = (
            IdentityContinuityProofCandidateV1.from_dict(
                data["identity_continuity_proof"]
            )
        )
        data["row_provenance"] = ProvenanceCandidateV1.from_dict(data["row_provenance"])
        return cls(**data)


@dataclass(frozen=True, slots=True)
class ComparabilityCandidatePayloadV1:
    received_rows: tuple[ComparabilityCandidateRowV1, ...]

    def __init__(self, received_rows: Sequence[ComparabilityCandidateRowV1]):
        object.__setattr__(
            self,
            "received_rows",
            _candidate_tuple(
                received_rows, ComparabilityCandidateRowV1, 51, "comparability rows"
            ),
        )

    @classmethod
    def from_dict(cls, obj: Any) -> ComparabilityCandidatePayloadV1:
        data = _closed(obj, {"received_rows"})
        return cls(_record_array(data["received_rows"], ComparabilityCandidateRowV1))


Payload = (
    MembershipCandidatePayloadV1
    | ScheduleCandidatePayloadV1
    | DailyCloseCandidatePayloadV1
    | ComparabilityCandidatePayloadV1
)


@dataclass(frozen=True, slots=True)
class EvidenceAttemptV1:
    evidence_kind: EvidenceKindV1
    requested_identities: tuple[EvidenceRequestIdentityV1, ...]
    payload: Payload | None
    failure: EvidenceAttemptFailureV1 | None
    attempt_identity_sha256: str

    def __post_init__(self) -> None:  # noqa: C901
        if not isinstance(self.evidence_kind, EvidenceKindV1):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise SchemaAdmissionError("invalid evidence kind")
        if type(self.requested_identities) is not tuple:
            raise SchemaAdmissionError(
                "requested identities must be an immutable tuple"
            )
        if not 1 <= len(self.requested_identities) <= 50:
            raise BoundsAdmissionError("requested identities outside bounds")
        if any(
            not isinstance(item, EvidenceRequestIdentityV1)  # pyright: ignore[reportUnnecessaryIsInstance]
            for item in self.requested_identities
        ):
            raise SchemaAdmissionError("invalid requested identity")
        if (
            tuple(sorted(self.requested_identities, key=lambda item: item.key()))
            != self.requested_identities
        ):
            raise CanonicalJsonAdmissionError("requested identities are not canonical")
        if len(set(self.requested_identities)) != len(self.requested_identities) or any(
            item.evidence_kind is not self.evidence_kind
            for item in self.requested_identities
        ):
            raise SchemaAdmissionError("invalid requested identities")
        expected: type[Payload] = {
            EvidenceKindV1.MEMBERSHIP: MembershipCandidatePayloadV1,
            EvidenceKindV1.SESSION_SCHEDULE: ScheduleCandidatePayloadV1,
            EvidenceKindV1.PRIOR_CLOSES: DailyCloseCandidatePayloadV1,
            EvidenceKindV1.CURRENT_CLOSES: DailyCloseCandidatePayloadV1,
            EvidenceKindV1.CORPORATE_COMPARABILITY: ComparabilityCandidatePayloadV1,
        }[self.evidence_kind]
        if self.payload is not None and not isinstance(self.payload, expected):
            raise SchemaAdmissionError("payload variant does not match kind")
        if self.failure is not None and not isinstance(
            self.failure,
            EvidenceAttemptFailureV1,  # pyright: ignore[reportUnnecessaryIsInstance]
        ):
            raise SchemaAdmissionError("invalid attempt failure")
        if self.payload is None and self.failure is None:
            raise SchemaAdmissionError("payload and failure cannot both be null")
        validate_sha256(self.attempt_identity_sha256)
        projection = {
            "evidence_kind": self.evidence_kind,
            "failure": self.failure,
            "payload": self.payload,
            "requested_identities": self.requested_identities,
        }
        if (
            hashlib.sha256(canonical_json_lf(projection)).hexdigest()
            != self.attempt_identity_sha256
        ):
            raise IdentityAdmissionError("attempt identity mismatch")

    @classmethod
    def build(
        cls,
        evidence_kind: object,
        requested_identities: object,
        payload: object | None,
        failure: object | None,
    ) -> EvidenceAttemptV1:
        if not isinstance(evidence_kind, EvidenceKindV1):
            raise SchemaAdmissionError("invalid evidence kind")
        payload_types = (
            MembershipCandidatePayloadV1,
            ScheduleCandidatePayloadV1,
            DailyCloseCandidatePayloadV1,
            ComparabilityCandidatePayloadV1,
        )
        if payload is not None and not isinstance(payload, payload_types):
            raise SchemaAdmissionError("invalid payload type")
        if failure is not None and not isinstance(failure, EvidenceAttemptFailureV1):
            raise SchemaAdmissionError("invalid attempt failure")
        identities = _candidate_tuple(
            requested_identities,
            EvidenceRequestIdentityV1,
            50,
            "requested identities",
        )
        ids = tuple(sorted(identities, key=lambda x: x.key()))
        if not 1 <= len(ids) <= 50:
            raise BoundsAdmissionError("requested identities outside bounds")
        if len(set(ids)) != len(ids) or any(
            x.evidence_kind is not evidence_kind for x in ids
        ):
            raise SchemaAdmissionError("invalid requested identities")
        if payload is None and failure is None:
            raise SchemaAdmissionError("payload and failure cannot both be null")
        expected: type[Payload] = {
            EvidenceKindV1.MEMBERSHIP: MembershipCandidatePayloadV1,
            EvidenceKindV1.SESSION_SCHEDULE: ScheduleCandidatePayloadV1,
            EvidenceKindV1.PRIOR_CLOSES: DailyCloseCandidatePayloadV1,
            EvidenceKindV1.CURRENT_CLOSES: DailyCloseCandidatePayloadV1,
            EvidenceKindV1.CORPORATE_COMPARABILITY: ComparabilityCandidatePayloadV1,
        }[evidence_kind]
        if payload is not None and not isinstance(payload, expected):
            raise SchemaAdmissionError("payload variant does not match kind")
        projection = {
            "evidence_kind": evidence_kind,
            "failure": failure,
            "payload": payload,
            "requested_identities": ids,
        }
        identity = hashlib.sha256(canonical_json_lf(projection)).hexdigest()
        return cls(evidence_kind, ids, payload, failure, identity)

    def to_dict(self) -> dict[str, Any]:
        return cast("dict[str, Any]", _plain(self))

    def canonical_json_bytes(self) -> bytes:
        return canonical_json_lf(self)

    @classmethod
    def from_canonical_json_bytes(cls, raw: bytes) -> EvidenceAttemptV1:
        d = _closed(
            parse_canonical_json_lf(raw, max_bytes=2 * 1024 * 1024),
            {f.name for f in dataclasses.fields(cls)},
        )
        kind = _enum(EvidenceKindV1, d["evidence_kind"])
        ids = _record_array(d["requested_identities"], EvidenceRequestIdentityV1)
        if tuple(x.key() for x in ids) != tuple(sorted(x.key() for x in ids)):
            raise CanonicalJsonAdmissionError(
                "external identity array is not canonical"
            )
        p = d["payload"]
        payload_types: dict[EvidenceKindV1, type[Payload]] = {
            EvidenceKindV1.MEMBERSHIP: MembershipCandidatePayloadV1,
            EvidenceKindV1.SESSION_SCHEDULE: ScheduleCandidatePayloadV1,
            EvidenceKindV1.PRIOR_CLOSES: DailyCloseCandidatePayloadV1,
            EvidenceKindV1.CURRENT_CLOSES: DailyCloseCandidatePayloadV1,
            EvidenceKindV1.CORPORATE_COMPARABILITY: ComparabilityCandidatePayloadV1,
        }
        payload = None if p is None else payload_types[kind].from_dict(p)
        failure = (
            None
            if d["failure"] is None
            else _enum(EvidenceAttemptFailureV1, d["failure"])
        )
        validate_sha256(d["attempt_identity_sha256"])
        built = cls.build(kind, ids, payload, failure)
        if d["attempt_identity_sha256"] != built.attempt_identity_sha256:
            raise IdentityAdmissionError("attempt identity mismatch")
        return built


@dataclass(frozen=True, slots=True)
class SourceObjectReceiptV1:
    source_object_identity_sha256: str
    canonical_object_bytes_hex: str
    media_type: str

    def __post_init__(self) -> None:
        validate_sha256(self.source_object_identity_sha256)
        body = bytes.fromhex(
            validate_hex_bytes(
                self.canonical_object_bytes_hex, min_bytes=1, max_bytes=1_048_576
            )
        )
        validate_bounded_ascii(self.media_type)
        if hashlib.sha256(body).hexdigest() != self.source_object_identity_sha256:
            raise IdentityAdmissionError("source object identity mismatch")

    @classmethod
    def build(cls, body: object, media_type: str) -> SourceObjectReceiptV1:
        if not isinstance(body, bytes):
            raise SchemaAdmissionError("source bytes required")
        if not 1 <= len(body) <= 1_048_576:
            raise BoundsAdmissionError("source object outside bounds")
        return cls(hashlib.sha256(body).hexdigest(), body.hex(), media_type)
