"""Exact hypothetical LONG equity loss arithmetic; no market or eligibility claim."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, NoReturn, cast

from .loss_scenario_runtime_identity_manifest import (
    LOSS_SCENARIO_RUNTIME_SOURCE_SHA256_V1,
)
from .runtime_source_verifier import runtime_source_sha256

MAX_INPUT_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 16 * 1024
CALCULATION_VERSION = "integer-paise-long-loss@v1"
_FIELDS = {
    "schema",
    "instrument",
    "side",
    "currency",
    "bar_frequency",
    "holding_sessions",
    "entry_price",
    "stop_price",
    "quantity",
}


class LossScenarioInputError(ValueError):
    """The supplied assumptions do not satisfy the closed scenario contract."""


def _invalid() -> NoReturn:
    raise LossScenarioInputError("invalid loss scenario")


def canonical_bytes(value: object) -> bytes:
    """Canonical UTF-8 JSON plus LF, matching the repository SHA-256 convention."""
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def _identity(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            _invalid()
        value[key] = item
    return value


def _constant(value: str) -> NoReturn:
    del value
    _invalid()


def _price(value: object) -> int:
    if (
        type(value) is not str
        or re.fullmatch(r"(?:0|[1-9][0-9]{0,8})\.[0-9]{2}", value) is None
    ):
        _invalid()
    paise = int(value.replace(".", ""))
    if paise == 0:
        _invalid()
    return paise


def _instrument(value: object) -> dict[str, str]:
    if type(value) is not dict:
        _invalid()
    row = cast(dict[str, Any], value)
    if set(row) != {"isin", "exchange", "symbol"} or any(
        type(v) is not str for v in row.values()
    ):
        _invalid()
    isin: str = row["isin"]
    if (
        re.fullmatch(r"IN[A-Z0-9]{9}[0-9]", isin) is None
        or row["exchange"] != "NSE"
        or re.fullmatch(r"[A-Z0-9][A-Z0-9.&_-]{0,31}", row["symbol"]) is None
    ):
        _invalid()
    digits = "".join(str(ord(char) - 55) if char.isalpha() else char for char in isin)
    total = 0
    for offset, char in enumerate(reversed(digits)):
        digit = int(char) * (2 if offset % 2 else 1)
        total += digit // 10 + digit % 10
    if total % 10:
        _invalid()
    return {"isin": isin, "exchange": row["exchange"], "symbol": row["symbol"]}


def _validate(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        _invalid()
    row = cast(dict[str, Any], value).copy()
    if set(row) != _FIELDS:
        _invalid()
    expected = {
        "schema": "equity-loss-scenario-request@v1",
        "side": "LONG",
        "currency": "INR",
        "bar_frequency": "1d",
    }
    if any(
        type(row[key]) is not str or row[key] != required
        for key, required in expected.items()
    ):
        _invalid()
    for key, lower, upper in (("quantity", 1, 1_000_000), ("holding_sessions", 2, 20)):
        if type(row[key]) is not int or not lower <= row[key] <= upper:
            _invalid()
    row["instrument"] = _instrument(row["instrument"])
    if _price(row["stop_price"]) >= _price(row["entry_price"]):
        _invalid()
    return row


def loss_scenario_request_from_json(raw: bytes) -> dict[str, Any]:
    """Parse bounded closed JSON, rejecting duplicate keys at every depth."""
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_INPUT_BYTES:
        _invalid()
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant
        )
        return _validate(value)
    except (ValueError, TypeError, RecursionError):
        raise LossScenarioInputError("invalid loss scenario") from None


def loss_scenario_runtime_identity() -> str:
    """Verify source-at-rest identity before reporting a calculation."""
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in LOSS_SCENARIO_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        digest = runtime_source_sha256(module, root, relative)
        if digest != expected:
            raise ValueError("loss scenario runtime identity invalid")
        observed[relative] = digest
    return _identity(observed)


def _amount(paise: int) -> str:
    return f"{paise // 100}.{paise % 100:02d}"


def calculate_loss_scenario(request: object) -> dict[str, Any]:
    """Revalidate caller assumptions and compute exact, unrounded integer paise."""
    assumptions = _validate(request)
    entry = _price(assumptions["entry_price"])
    stop = _price(assumptions["stop_price"])
    quantity: int = assumptions["quantity"]
    result: dict[str, Any] = {
        "schema": "equity-loss-scenario@v1",
        "assumptions": assumptions,
        "currency": "INR",
        "input_basis": "CALLER_SUPPLIED_ASSUMPTIONS",
        "instrument_verification": "NOT_PERFORMED",
        "market_evidence": "NOT_USED",
        "risk_eligibility": "NOT_ASSESSED",
        "costs_and_slippage": "EXCLUDED",
        "calculation_version": CALCULATION_VERSION,
        "request_identity_sha256": _identity(assumptions),
        "runtime_code_identity_sha256": loss_scenario_runtime_identity(),
        "amounts": {
            "entry_notional": _amount(entry * quantity),
            "stop_proceeds": _amount(stop * quantity),
            "loss_per_share": _amount(entry - stop),
            "gross_scenario_loss": _amount((entry - stop) * quantity),
        },
        "limitations": [
            "Stop execution is not guaranteed; actual losses may exceed this scenario.",
            "Fees, taxes and slippage are excluded.",
            "No liquidity, event, gap, portfolio or trade suitability assessment was performed.",
        ],
    }
    result["result_identity_sha256"] = _identity(result)
    loss_scenario_result_bytes(result)
    return result


def loss_scenario_result_bytes(result: dict[str, Any]) -> bytes:
    """Bound complete canonical output before the CLI emits it once."""
    raw = canonical_bytes(result)
    if len(raw) > MAX_OUTPUT_BYTES:
        raise ValueError("loss scenario output bound exceeded")
    return raw
