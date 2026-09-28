"""Closed Volume requests reject ambiguity before touching retained evidence."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from swing_trading_ai_assistant.volume_analysis.request import (
    VolumeRequest,
    volume_request_from_json,
)


def request_value():
    return {
        "contract_version": "current-volume-context-request@v1",
        "data_selection_time": "2026-09-15T09:00:00.000000Z",
        "admission_deadline": "2026-09-15T09:20:00.000000Z",
        "schedule_identity_sha256": "a" * 64,
        "members": [
            {
                "isin": "INE467B01029",
                "exchange": "NSE",
                "instrument_type": "EQUITY",
                "segment": "EQ",
                "effective_symbol": "TCS",
                "valid_from": "2020-01-01",
                "valid_through": "2030-01-01",
            }
        ],
    }


def test_request_has_canonical_identity_independent_of_json_whitespace():
    value = request_value()
    one = volume_request_from_json(json.dumps(value).encode())
    two = volume_request_from_json(json.dumps(value, indent=2).encode())
    assert one == two
    assert len(one.request_identity_sha256) == 64
    assert json.loads(one.canonical_bytes) == value


@pytest.mark.parametrize(
    "key,value",
    [
        ("extra", 1),
        ("contract_version", "wrong"),
        ("members", []),
        ("members", None),
        ("schedule_identity_sha256", "A" * 64),
        ("admission_deadline", "2026-09-15T09:31:00.000000Z"),
        ("admission_deadline", "2026-09-15T09:00:00.000000Z"),
        ("data_selection_time", "2026-09-15T09:00:00+05:30"),
    ],
)
def test_invalid_closed_fields(key, value):
    raw = request_value()
    raw[key] = value
    with pytest.raises(ValueError):
        volume_request_from_json(json.dumps(raw).encode())


def test_duplicate_json_keys_and_member_keys_rejected():
    raw = json.dumps(request_value())
    for bad in (
        raw.replace('"members":', '"members": [], "members":'),
        raw.replace('"isin":', '"isin": "bad", "isin":'),
    ):
        with pytest.raises(ValueError):
            volume_request_from_json(bad.encode())


@pytest.mark.parametrize("count", [2, 50, 51])
def test_duplicate_member_identity_rejected(count):
    raw = request_value()
    raw["members"] *= count
    with pytest.raises(ValueError):
        volume_request_from_json(json.dumps(raw).encode())


@pytest.mark.parametrize("raw", [b"", b"null", b"[]", b"NaN", b"\xff", b" " * 65537])
def test_bad_or_oversized_json(raw):
    with pytest.raises(ValueError):
        volume_request_from_json(raw)


def test_sdk_revalidates_members_and_temporal_bounds():
    request = volume_request_from_json(json.dumps(request_value()).encode())
    late = datetime(2026, 9, 15, 18, 20, tzinfo=UTC)
    with pytest.raises(ValueError):
        VolumeRequest(late, late + timedelta(minutes=20), "a" * 64, request.members)
    with pytest.raises(ValueError):
        VolumeRequest(
            request.data_selection_time,
            request.admission_deadline,
            "a" * 64,
            list(request.members),
        )
