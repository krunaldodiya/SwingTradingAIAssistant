"""Input-only boundary for the opt-in agent cohort context workflow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from datetime import date
from pathlib import Path
from typing import Any, NoReturn, cast

from .adjusted_daily.service_v3 import mapping_identity_v3
from .agent_research_run import validate_agent_research_request
from .current_same_pass_daily_v4 import CurrentSamePassEquityMemberV4
from .current_stock_research import CurrentStockResearchInputError


def validate_agent_cohort_request(
    symbols: tuple[str, ...],
    storage_root: Path,
    context_symbols: tuple[str, ...],
    context_purpose: str,
) -> None:
    """Validate both ordered lists and caller purpose before any effects.

    Cohort bounds are independent of research-stock bounds. A caller description
    or the processing minimum of two members establishes no representativeness.
    Canonical alias rejection additionally requires the retained mapping boundary.
    """
    validate_agent_research_request(symbols, storage_root)
    if (
        type(context_symbols) is not tuple
        or not 2 <= len(context_symbols) <= 50
        or any(type(symbol) is not str for symbol in context_symbols)
        or len(set(context_symbols)) != len(context_symbols)
        or type(context_purpose) is not str
        or not context_purpose.strip()
        or len(context_purpose) > 160
        or not context_purpose.isprintable()
    ):
        raise CurrentStockResearchInputError("invalid agent cohort request")
    # The existing symbol syntax remains authoritative for both request lists.
    for offset in range(0, len(context_symbols), 10):
        validate_agent_research_request(
            context_symbols[offset : offset + 10], storage_root
        )


@dataclass(frozen=True, slots=True)
class AgentCohortMappings:
    """Parsed caller assertions, not independent proof of historical validity."""

    members: tuple[CurrentSamePassEquityMemberV4, ...]
    input_sha256: str


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise CurrentStockResearchInputError("invalid cohort mappings")
        value[key] = item
    return value


def _reject_constant(value: str) -> NoReturn:
    del value
    raise CurrentStockResearchInputError("invalid cohort mappings")


def parse_agent_cohort_mappings(
    raw: bytes, symbols: tuple[str, ...]
) -> AgentCohortMappings:
    """Admit the closed dated mapping document before any provider/storage effects."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 64 * 1024:
        raise CurrentStockResearchInputError("invalid cohort mappings")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object,
            parse_constant=_reject_constant,
        )
        if (
            type(value) is not dict
            or set(cast(dict[str, Any], value)) != {"contract_version", "members"}
            or value["contract_version"] != "agent-current-cohort-mappings@v1"
            or type(cast(dict[str, Any], value)["members"]) is not list
            or not 2 <= len(cast(list[Any], value["members"])) <= 50
        ):
            raise CurrentStockResearchInputError("invalid cohort mappings")
        members = tuple(
            _mapping_member(row) for row in cast(list[Any], value["members"])
        )
        if (
            tuple(m.effective_symbol for m in members) != symbols
            or len({m.isin for m in members}) != len(members)
            or len({m.effective_symbol for m in members}) != len(members)
        ):
            raise CurrentStockResearchInputError("invalid cohort mappings")
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
        TypeError,
    ):
        raise CurrentStockResearchInputError("invalid cohort mappings") from None
    return AgentCohortMappings(members, hashlib.sha256(raw).hexdigest())


def _mapping_member(row: object) -> CurrentSamePassEquityMemberV4:
    names = {field.name for field in fields(CurrentSamePassEquityMemberV4)}
    if type(row) is not dict or set(cast(dict[str, Any], row)) != names:
        raise CurrentStockResearchInputError("invalid cohort mapping member")
    values = cast(dict[str, Any], row).copy()
    for name, value in values.items():
        if value is None and name == "mapping_valid_through":
            continue
        if type(value) is not str:
            raise CurrentStockResearchInputError("invalid cohort mapping member")
        if name in {
            "valid_from",
            "valid_through",
            "mapping_valid_from",
            "mapping_valid_through",
        }:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise CurrentStockResearchInputError("invalid cohort mapping date")
            values[name] = parsed
    member = CurrentSamePassEquityMemberV4(**values)
    if member.mapping_identity != mapping_identity_v3(
        isin=member.isin,
        exchange=member.exchange,
        instrument_type=member.instrument_type,
        segment=member.segment,
        effective_symbol=member.effective_symbol,
        provider_symbol=member.provider_symbol,
        mapping_valid_from=member.mapping_valid_from,
        mapping_valid_through=member.mapping_valid_through,
    ):
        raise CurrentStockResearchInputError("invalid cohort mapping identity")
    return member
