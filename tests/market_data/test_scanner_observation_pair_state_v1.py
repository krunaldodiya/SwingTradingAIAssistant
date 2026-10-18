"""Adversarial tests for the scanner observation pair state store."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import cast

import pytest
from test_stock_eligibility_v3 import _structure_observation

import swing_trading_ai_assistant.market_data.scanner_observation_pair_state_v1 as pair_state_module
from swing_trading_ai_assistant.market_data import current_stock_research_v2 as producer
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)
from swing_trading_ai_assistant.market_data.scanner_observation_pair_state_v1 import (
    CONTRACT_VERSION_V1,
    ScannerPairStateConflictV1,
    ScannerPairStateUnavailableV1,
    _canonical,
    _digest,
    _generation_name,
    _state_runtime_identity,
    advance_scanner_pair_state_v1,
    read_scanner_pair_state_v1,
)
from swing_trading_ai_assistant.market_data.stock_observations import (
    record_stock_observation_v1,
)

_ABSENT = "f" * 64


def _record(root: Path, *, later: bool) -> str:
    observation = cast(
        CurrentStockResearchResultV2, _structure_observation(root, later=later)
    )
    return record_stock_observation_v1(root, observation)


def _chain_directory(
    root: Path, symbol: str = "RELIANCE", *, create: bool = False
) -> Path:
    directory = root
    for part in ("scanner-pair-state-v1", _generation_name(), symbol):
        directory = directory / part
        if create:
            directory.mkdir(mode=0o700, exist_ok=True)
            os.chmod(directory, 0o700)
    return directory


def _publish_crafted(
    root: Path, name: str, raw: bytes, mode: int = 0o400, symbol: str = "RELIANCE"
) -> None:
    path = _chain_directory(root, symbol, create=True) / name
    path.write_bytes(raw)
    os.chmod(path, mode)


def _craft_state(
    *,
    symbol: str = "RELIANCE",
    sequence: int = 1,
    previous: str | None = None,
    current: str,
    runtime: str | None = None,
    producer_runtime: str | None = None,
) -> bytes:
    unsigned: dict[str, object] = {
        "contract_version": CONTRACT_VERSION_V1,
        "sequence": sequence,
        "symbol": symbol,
        "previous_observation_identity_sha256": previous,
        "current_observation_identity_sha256": current,
        "state_runtime_identity_sha256": runtime or _state_runtime_identity(),
        "producer_runtime_identity_sha256": (
            producer_runtime or producer._runtime_identity()  # pyright: ignore[reportPrivateUsage]
        ),
    }
    unsigned["state_identity_sha256"] = _digest(unsigned)
    return _canonical(unsigned)


def test_absent_state_reads_as_none(tmp_path: Path) -> None:
    assert read_scanner_pair_state_v1(tmp_path, "RELIANCE") is None


def test_first_admission_seeds_then_distinct_advances(tmp_path: Path) -> None:
    first = _record(tmp_path, later=False)
    second = _record(tmp_path, later=True)

    seeded = advance_scanner_pair_state_v1(
        tmp_path,
        "RELIANCE",
        expected_current_observation_identity_sha256=None,
        new_current_observation_identity_sha256=first,
    )
    assert seeded.sequence == 1
    assert seeded.previous_observation_identity_sha256 is None
    assert seeded.current_observation_identity_sha256 == first
    assert read_scanner_pair_state_v1(tmp_path, "RELIANCE") == seeded

    advanced = advance_scanner_pair_state_v1(
        tmp_path,
        "RELIANCE",
        expected_current_observation_identity_sha256=first,
        new_current_observation_identity_sha256=second,
    )
    assert advanced.sequence == 2
    assert advanced.previous_observation_identity_sha256 == first
    assert advanced.current_observation_identity_sha256 == second
    assert read_scanner_pair_state_v1(tmp_path, "RELIANCE") == advanced


def test_advance_rejects_stale_or_missing_expectation(tmp_path: Path) -> None:
    first = _record(tmp_path, later=False)
    second = _record(tmp_path, later=True)

    with pytest.raises(ScannerPairStateConflictV1, match="predecessor missing"):
        advance_scanner_pair_state_v1(
            tmp_path,
            "RELIANCE",
            expected_current_observation_identity_sha256=_ABSENT,
            new_current_observation_identity_sha256=first,
        )

    advance_scanner_pair_state_v1(
        tmp_path,
        "RELIANCE",
        expected_current_observation_identity_sha256=None,
        new_current_observation_identity_sha256=first,
    )

    with pytest.raises(ScannerPairStateConflictV1, match="moved since evaluation"):
        advance_scanner_pair_state_v1(
            tmp_path,
            "RELIANCE",
            expected_current_observation_identity_sha256=second,
            new_current_observation_identity_sha256=first,
        )


def test_advance_rejects_unchanged_handle(tmp_path: Path) -> None:
    first = _record(tmp_path, later=False)
    with pytest.raises(ScannerPairStateUnavailableV1, match="unchanged"):
        advance_scanner_pair_state_v1(
            tmp_path,
            "RELIANCE",
            expected_current_observation_identity_sha256=first,
            new_current_observation_identity_sha256=first,
        )


def test_advance_validates_the_new_record(tmp_path: Path) -> None:
    _record(tmp_path, later=False)
    with pytest.raises(ScannerPairStateUnavailableV1, match="observation unavailable"):
        advance_scanner_pair_state_v1(
            tmp_path,
            "RELIANCE",
            expected_current_observation_identity_sha256=None,
            new_current_observation_identity_sha256=_ABSENT,
        )
    with pytest.raises(ScannerPairStateUnavailableV1, match="digest"):
        advance_scanner_pair_state_v1(
            tmp_path,
            "RELIANCE",
            expected_current_observation_identity_sha256=None,
            new_current_observation_identity_sha256="not-a-digest",
        )


def test_read_rejects_ambiguous_committed_sequence(tmp_path: Path) -> None:
    first = _record(tmp_path, later=False)
    advance_scanner_pair_state_v1(
        tmp_path,
        "RELIANCE",
        expected_current_observation_identity_sha256=None,
        new_current_observation_identity_sha256=first,
    )
    _publish_crafted(
        tmp_path,
        f"00000002.{'a' * 64}.json",
        _craft_state(sequence=2, previous=first, current=first),
    )
    _publish_crafted(
        tmp_path,
        f"00000002.{'c' * 64}.json",
        _craft_state(sequence=2, previous=first, current=first),
    )
    with pytest.raises(ScannerPairStateUnavailableV1, match="ambiguous"):
        read_scanner_pair_state_v1(tmp_path, "RELIANCE")


def test_read_rejects_gap_in_chain(tmp_path: Path) -> None:
    first = _record(tmp_path, later=False)
    second = _record(tmp_path, later=True)
    advance_scanner_pair_state_v1(
        tmp_path,
        "RELIANCE",
        expected_current_observation_identity_sha256=None,
        new_current_observation_identity_sha256=first,
    )
    advanced = advance_scanner_pair_state_v1(
        tmp_path,
        "RELIANCE",
        expected_current_observation_identity_sha256=first,
        new_current_observation_identity_sha256=second,
    )
    chain = sorted(_chain_directory(tmp_path).glob("*.json"))
    assert len(chain) == 2
    os.unlink(chain[0])
    with pytest.raises(ScannerPairStateUnavailableV1, match="incomplete"):
        read_scanner_pair_state_v1(
            tmp_path,
            "RELIANCE",
        )
    assert advanced.sequence == 2


def test_read_rejects_tampered_symbol_binding(tmp_path: Path) -> None:
    first = _record(tmp_path, later=False)
    advance_scanner_pair_state_v1(
        tmp_path,
        "RELIANCE",
        expected_current_observation_identity_sha256=None,
        new_current_observation_identity_sha256=first,
    )
    chain = next(_chain_directory(tmp_path).glob("*.json"))
    raw = _craft_state(symbol="TCS", current=first)
    os.unlink(chain)
    _publish_crafted(tmp_path, f"00000001.{hashlib.sha256(raw).hexdigest()}.json", raw)
    with pytest.raises(ScannerPairStateUnavailableV1, match="binding"):
        read_scanner_pair_state_v1(tmp_path, "RELIANCE")


def test_read_rejects_unavailable_referenced_observation(tmp_path: Path) -> None:
    _record(tmp_path, later=False)
    raw = _craft_state(current=_ABSENT)
    _publish_crafted(tmp_path, f"00000001.{hashlib.sha256(raw).hexdigest()}.json", raw)
    with pytest.raises(ScannerPairStateUnavailableV1, match="observation unavailable"):
        read_scanner_pair_state_v1(tmp_path, "RELIANCE")


def test_read_rejects_record_admitted_for_another_symbol(tmp_path: Path) -> None:
    first = _record(tmp_path, later=False)
    raw = _craft_state(symbol="TCS", current=first)
    _publish_crafted(
        tmp_path,
        f"00000001.{hashlib.sha256(raw).hexdigest()}.json",
        raw,
        symbol="TCS",
    )
    with pytest.raises(ScannerPairStateUnavailableV1, match="mismatch"):
        read_scanner_pair_state_v1(tmp_path, "TCS")


def test_read_rejects_noncanonical_record(tmp_path: Path) -> None:
    first = _record(tmp_path, later=False)
    raw = _craft_state(current=first)
    _publish_crafted(tmp_path, f"00000001.{hashlib.sha256(raw).hexdigest()}.json", raw)
    path = next(_chain_directory(tmp_path).glob("*.json"))
    os.chmod(path, 0o600)
    path.write_bytes(raw + b" ")
    os.chmod(path, 0o400)
    with pytest.raises(ScannerPairStateUnavailableV1, match="identity invalid"):
        read_scanner_pair_state_v1(tmp_path, "RELIANCE")


def test_interrupted_commit_recovers_identical_retry(tmp_path: Path) -> None:
    first = _record(tmp_path, later=False)
    second = _record(tmp_path, later=True)
    advance_scanner_pair_state_v1(
        tmp_path,
        "RELIANCE",
        expected_current_observation_identity_sha256=None,
        new_current_observation_identity_sha256=first,
    )
    advance_scanner_pair_state_v1(
        tmp_path,
        "RELIANCE",
        expected_current_observation_identity_sha256=first,
        new_current_observation_identity_sha256=second,
    )
    latest = max(_chain_directory(tmp_path).glob("*.json"))
    os.chmod(latest, 0o600)

    reverted = read_scanner_pair_state_v1(tmp_path, "RELIANCE")
    assert reverted is not None
    assert reverted.sequence == 1

    recovered = advance_scanner_pair_state_v1(
        tmp_path,
        "RELIANCE",
        expected_current_observation_identity_sha256=first,
        new_current_observation_identity_sha256=second,
    )
    assert recovered.sequence == 2
    assert os.stat(latest).st_mode & 0o777 == 0o400
    assert read_scanner_pair_state_v1(tmp_path, "RELIANCE") == recovered


def test_uncommitted_partial_attempt_is_ignored(tmp_path: Path) -> None:
    first = _record(tmp_path, later=False)
    second = _record(tmp_path, later=True)
    advance_scanner_pair_state_v1(
        tmp_path,
        "RELIANCE",
        expected_current_observation_identity_sha256=None,
        new_current_observation_identity_sha256=first,
    )
    _publish_crafted(tmp_path, f"00000002.{'b' * 64}.json", b"partial", mode=0o600)

    reverted = read_scanner_pair_state_v1(tmp_path, "RELIANCE")
    assert reverted is not None and reverted.sequence == 1

    advanced = advance_scanner_pair_state_v1(
        tmp_path,
        "RELIANCE",
        expected_current_observation_identity_sha256=first,
        new_current_observation_identity_sha256=second,
    )
    assert advanced.sequence == 2
    assert read_scanner_pair_state_v1(tmp_path, "RELIANCE") == advanced


def test_root_and_symbol_validation(tmp_path: Path) -> None:
    with pytest.raises(ScannerPairStateUnavailableV1, match="root"):
        read_scanner_pair_state_v1(Path("relative"), "RELIANCE")
    with pytest.raises(ScannerPairStateUnavailableV1, match="symbol"):
        read_scanner_pair_state_v1(tmp_path, "not a symbol")
    first = _record(tmp_path, later=False)
    with pytest.raises(ScannerPairStateUnavailableV1, match="symbol"):
        advance_scanner_pair_state_v1(
            tmp_path,
            "bad symbol!",
            expected_current_observation_identity_sha256=None,
            new_current_observation_identity_sha256=first,
        )


def test_read_rejects_referenced_observation_with_wrong_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = _record(tmp_path, later=False)
    raw = _craft_state(current=handle)
    _publish_crafted(tmp_path, f"00000001.{hashlib.sha256(raw).hexdigest()}.json", raw)

    class _SubstitutedObservation:
        question = "CURRENT_STRUCTURE_SUMMARY"
        status = "READY"
        symbol = "RELIANCE"

    monkeypatch.setattr(
        pair_state_module,
        "read_stock_observation_v1",
        lambda *_args, **_kwargs: _SubstitutedObservation(),
    )

    with pytest.raises(ScannerPairStateUnavailableV1, match="observation mismatch"):
        read_scanner_pair_state_v1(tmp_path, "RELIANCE")
