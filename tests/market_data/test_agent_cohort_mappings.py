"""Dated owner-supplied mappings retain exact intervals and ordered identities."""

from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest
import test_current_industry_classification as identity_fixture

from swing_trading_ai_assistant.market_data import agent_cohort_request as api
from swing_trading_ai_assistant.market_data.adjusted_daily.service_v3 import (
    mapping_identity_v3,
)
from swing_trading_ai_assistant.market_data.current_stock_research import (
    CurrentStockResearchInputError,
)


def _document(count=2):
    members = []
    for i in range(count):
        symbol = f"SYM{i:03d}"
        row = {
            "isin": identity_fixture._isin(i),
            "exchange": "NSE",
            "instrument_type": "EQUITY",
            "segment": "EQ",
            "effective_symbol": symbol,
            "valid_from": "2026-01-01",
            "valid_through": "2026-12-31",
            "provider_symbol": symbol,
            "mapping_version": "bharatstock-isin-exchange-mapping@v1",
            "mapping_valid_from": "2026-01-01",
            "mapping_valid_through": None,
            "provider_mapping_revision": "owner-declared@2026-09-27",
        }
        row["mapping_identity"] = mapping_identity_v3(
            isin=row["isin"],
            exchange="NSE",
            instrument_type="EQUITY",
            segment="EQ",
            effective_symbol=symbol,
            provider_symbol=symbol,
            mapping_valid_from=date(2026, 1, 1),
            mapping_valid_through=None,
        )
        members.append(row)
    return {"contract_version": "agent-current-cohort-mappings@v1", "members": members}


def _parse(doc):
    return api.parse_agent_cohort_mappings(
        json.dumps(doc).encode(), tuple(m["effective_symbol"] for m in doc["members"])
    )


def test_supplied_mapping_intervals_survive_parsing():
    doc = _document()
    value = _parse(doc)
    assert [m.effective_symbol for m in value.members] == ["SYM000", "SYM001"]
    assert value.members[0].valid_from == date(2026, 1, 1)
    assert value.members[0].mapping_valid_through is None
    assert value.members[0].provider_mapping_revision == "owner-declared@2026-09-27"


@pytest.mark.parametrize(
    "mutation", ["digest", "unknown", "alias", "date", "nonfinite", "type"]
)
def test_malformed_supplied_mapping_rejected(mutation):
    doc = _document()
    row = doc["members"][0]
    if mutation == "digest":
        row["mapping_identity"] = "a" * 64
    elif mutation == "unknown":
        row["extra"] = "x"
    elif mutation == "alias":
        alias = doc["members"][1]
        alias["isin"] = row["isin"]
        alias["mapping_identity"] = mapping_identity_v3(
            isin=alias["isin"],
            exchange="NSE",
            instrument_type="EQUITY",
            segment="EQ",
            effective_symbol=alias["effective_symbol"],
            provider_symbol=alias["provider_symbol"],
            mapping_valid_from=date(2026, 1, 1),
            mapping_valid_through=None,
        )
    elif mutation == "date":
        row["valid_from"] = "20260101"
    elif mutation == "nonfinite":
        row["valid_from"] = float("nan")
    else:
        row["mapping_valid_through"] = 1
    with pytest.raises(CurrentStockResearchInputError):
        _parse(doc)


@pytest.mark.parametrize("count", [0, 1, 2, 50, 51])
def test_mapping_member_bounds(count):
    document = _document(count)
    if count in (2, 50):
        assert len(_parse(document).members) == count
    else:
        with pytest.raises(CurrentStockResearchInputError):
            _parse(document)


def test_exact_byte_bound_and_fingerprint():
    document = _document()
    raw = json.dumps(document).encode()
    raw += b" " * (65536 - len(raw))
    symbols = ("SYM000", "SYM001")
    admitted = api.parse_agent_cohort_mappings(raw, symbols)
    assert admitted.input_sha256 == hashlib.sha256(raw).hexdigest()
    with pytest.raises(CurrentStockResearchInputError):
        api.parse_agent_cohort_mappings(raw + b" ", symbols)


@pytest.mark.parametrize(
    "symbols", [("SYM001", "SYM000"), ("SYM000",), ("SYM000", "SYM001", "SYM002")]
)
def test_requested_membership_is_exact_and_ordered(symbols):
    with pytest.raises(CurrentStockResearchInputError):
        api.parse_agent_cohort_mappings(json.dumps(_document()).encode(), symbols)


@pytest.mark.parametrize("scope", ["envelope", "member"])
def test_duplicate_json_keys_rejected_even_with_equal_values(scope):
    raw = json.dumps(_document())
    token = (
        '"contract_version": "agent-current-cohort-mappings@v1"'
        if scope == "envelope"
        else '"exchange": "NSE"'
    )
    raw = raw.replace(token, token + ", " + token, 1)
    with pytest.raises(CurrentStockResearchInputError):
        api.parse_agent_cohort_mappings(raw.encode(), ("SYM000", "SYM001"))


@pytest.mark.parametrize("field", list(_document()["members"][0]))
def test_every_member_field_is_required(field):
    document = _document()
    del document["members"][0][field]
    with pytest.raises(CurrentStockResearchInputError):
        api.parse_agent_cohort_mappings(
            json.dumps(document).encode(), ("SYM000", "SYM001")
        )


@pytest.mark.parametrize(
    "field",
    [key for key in _document()["members"][0] if key != "mapping_valid_through"],
)
def test_only_mapping_valid_through_accepts_null(field):
    document = _document()
    document["members"][0][field] = None
    with pytest.raises(CurrentStockResearchInputError):
        api.parse_agent_cohort_mappings(
            json.dumps(document).encode(), ("SYM000", "SYM001")
        )


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\xff",
        b"[]",
        b"null",
        b"{}",
        b'{"members": NaN}',
        b'{"members": Infinity}',
    ],
)
def test_malformed_json_is_input_rejection(raw):
    with pytest.raises(CurrentStockResearchInputError):
        api.parse_agent_cohort_mappings(raw, ("SYM000", "SYM001"))


def test_structurally_valid_short_history_is_preserved_for_session_admission():
    document = _document()
    # Parsing does not silently widen the canonical interval to match history.
    document["members"][0]["valid_from"] = "2026-09-27"
    document["members"][0]["valid_through"] = "2026-09-27"
    member = _parse(document).members[0]
    assert member.valid_from == member.valid_through == date(2026, 9, 27)
