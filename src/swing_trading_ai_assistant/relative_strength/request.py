"""Closed, bounded Plan 41 request and explicit reference/target identities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import cast

from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextMemberV1,
    CurrentRawPriceContextInputV1,
)

_IST = timezone(timedelta(hours=5, minutes=30))
_FIELDS = {
    "contract_version",
    "data_selection_time",
    "admission_deadline",
    "schedule_identity_sha256",
    "reference",
    "members",
}
_MEMBER_FIELDS = {
    "isin",
    "exchange",
    "instrument_type",
    "segment",
    "effective_symbol",
    "valid_from",
    "valid_through",
}


def canonical_bytes(value: object) -> bytes:
    """Canonical JSON encoding; never serialize arbitrary objects implicitly."""
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def identity(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def instant(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def member_value(member: CurrentPriceContextMemberV1) -> dict[str, object]:
    return {
        **asdict(member),
        "valid_from": member.valid_from.isoformat(),
        "valid_through": member.valid_through.isoformat(),
    }


@dataclass(frozen=True, slots=True)
class RelativeStrengthRequest:
    data_selection_time: datetime
    admission_deadline: datetime
    schedule_identity_sha256: str
    reference: CurrentPriceContextMemberV1
    members: tuple[CurrentPriceContextMemberV1, ...]

    def __post_init__(self) -> None:
        if (
            type(self.reference) is not CurrentPriceContextMemberV1
            or type(self.members) is not tuple
            or not 1 <= len(self.members) <= 49
        ):
            raise ValueError("invalid relative strength selection")
        # The producer list is an explicit transformation, with reference first.
        raw = CurrentRawPriceContextInputV1(
            "0" * 64,
            self.data_selection_time,
            self.admission_deadline,
            self.schedule_identity_sha256,
            (self.reference, *self.members),
        )
        if (
            self.admission_deadline - self.data_selection_time > timedelta(minutes=30)
            or self.admission_deadline.astimezone(_IST).date()
            != self.data_selection_time.astimezone(_IST).date()
        ):
            raise ValueError("invalid relative strength request interval")
        for member in raw.members:
            CurrentPriceContextMemberV1(**asdict(member))
            if (
                not member.valid_from
                <= self.data_selection_time.astimezone(_IST).date()
                <= member.valid_through
            ):
                raise ValueError("relative strength member is not valid at selection")
        if len(self.canonical_bytes) > 64 * 1024:
            raise ValueError("relative strength request too large")

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_bytes(
            {
                "contract_version": "current-relative-strength-request@v1",
                "data_selection_time": instant(self.data_selection_time),
                "admission_deadline": instant(self.admission_deadline),
                "schedule_identity_sha256": self.schedule_identity_sha256,
                "reference": member_value(self.reference),
                "members": [member_value(member) for member in self.members],
            }
        )

    @property
    def request_identity_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    def raw_input(self) -> CurrentRawPriceContextInputV1:
        return CurrentRawPriceContextInputV1(
            self.request_identity_sha256,
            self.data_selection_time,
            self.admission_deadline,
            self.schedule_identity_sha256,
            (self.reference, *self.members),
        )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate relative strength request key")
        result[key] = value
    return result


def _parse_instant(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("invalid relative strength request instant")
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    if instant(parsed) != value:
        raise ValueError("invalid relative strength request instant")
    return parsed


def _parse_member(value: object) -> CurrentPriceContextMemberV1:
    if type(value) is not dict or set(cast(dict[str, object], value)) != _MEMBER_FIELDS:
        raise ValueError("invalid relative strength member")
    raw = cast(dict[str, object], value)
    if any(type(item) is not str for item in raw.values()):
        raise ValueError("invalid relative strength member")
    fields = cast(dict[str, str], raw)
    start, end = (
        date.fromisoformat(fields["valid_from"]),
        date.fromisoformat(fields["valid_through"]),
    )
    if (
        start.isoformat() != fields["valid_from"]
        or end.isoformat() != fields["valid_through"]
    ):
        raise ValueError("invalid relative strength member interval")
    if (fields["exchange"], fields["instrument_type"], fields["segment"]) != (
        "NSE",
        "EQUITY",
        "EQ",
    ):
        raise ValueError("unsupported relative strength instrument")
    return CurrentPriceContextMemberV1(
        fields["isin"], "NSE", "EQUITY", "EQ", fields["effective_symbol"], start, end
    )


def relative_strength_request_from_json(raw: bytes) -> RelativeStrengthRequest:
    """Decode without effects. Unknown/duplicate fields fail before admission."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 64 * 1024:
        raise ValueError("invalid relative strength request bytes")
    try:
        decoded: object = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("nonfinite JSON")
            ),
        )
        if (
            type(decoded) is not dict
            or set(cast(dict[str, object], decoded)) != _FIELDS
        ):
            raise ValueError("invalid relative strength request fields")
        value = cast(dict[str, object], decoded)
        if value["contract_version"] != "current-relative-strength-request@v1":
            raise ValueError("invalid relative strength request contract")
        members = value["members"]
        digest = value["schedule_identity_sha256"]
        if type(members) is not list or type(digest) is not str:
            raise ValueError("invalid relative strength request selection")
        return RelativeStrengthRequest(
            _parse_instant(value["data_selection_time"]),
            _parse_instant(value["admission_deadline"]),
            digest,
            _parse_member(value["reference"]),
            tuple(_parse_member(item) for item in cast(list[object], members)),
        )
    except (UnicodeError, TypeError, KeyError, RecursionError) as error:
        raise ValueError("invalid relative strength request") from error
