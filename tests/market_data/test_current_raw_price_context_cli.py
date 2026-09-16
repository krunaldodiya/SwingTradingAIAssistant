"""RED CLI contract for the standalone Issue #188 public command."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.cli as cli_module
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.research_packet import (
    CurrentPriceContextFeatureV1,
    CurrentPriceContextMemberResultV1,
    CurrentPriceContextMemberV1,
    CurrentPriceContextRequestV1,
)
from swing_trading_ai_assistant.research_packet import (
    CurrentPriceContextResultV1 as PublicCurrentPriceContextResultV1,
)
from swing_trading_ai_assistant.research_packet import (
    research_current_price_context_v1 as public_research_current_price_context_v1,
)
from swing_trading_ai_assistant.research_packet.current_price_context import (
    CurrentPriceContextResultV1,
    current_price_context_request_from_canonical_json_bytes_v1,
    research_current_price_context_v1,
)


def test_public_price_context_sdk_symbols_are_stable() -> None:
    assert CurrentPriceContextFeatureV1.__name__ == "CurrentPriceContextFeatureV1"
    assert (
        CurrentPriceContextMemberResultV1.__name__
        == "CurrentPriceContextMemberResultV1"
    )
    assert CurrentPriceContextMemberV1.__name__ == "CurrentPriceContextMemberV1"
    assert CurrentPriceContextRequestV1.__name__ == "CurrentPriceContextRequestV1"
    assert PublicCurrentPriceContextResultV1.__name__ == "CurrentPriceContextResultV1"
    assert public_research_current_price_context_v1 is research_current_price_context_v1


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 9, 15, 9, 15, tzinfo=UTC)


def test_price_context_current_accepts_closed_owner_file_and_emits_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = {
        "contract_version": "current-price-context-request@v1",
        "data_selection_time": "2026-09-15T09:00:00.000000Z",
        "admission_deadline": "2026-09-15T09:30:00.000000Z",
        "schedule_identity_sha256": "a" * 64,
        "members": [
            {
                "isin": "INE467B01029",
                "exchange": "NSE",
                "instrument_type": "EQUITY",
                "segment": "EQ",
                "effective_symbol": "AAA",
                "valid_from": "2020-01-01",
                "valid_through": "2030-01-01",
            }
        ],
        "questions": [
            "RAW_MARKET_STRUCTURE",
            "RAW_20_SESSION_DIRECTION",
            "RAW_COHORT_BREADTH",
            "RAW_INDUSTRY_PARTICIPATION",
        ],
        "industry_archive_reference": None,
    }
    input_file = (tmp_path / "request.json").resolve()
    input_file.write_text(
        json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    input_file.chmod(0o600)

    root = (tmp_path / "retained").resolve()
    root.mkdir(mode=0o700)
    status = main(
        [
            "price-context-current",
            "--input-file",
            str(input_file),
            "--storage-root",
            str(root),
            "--output",
            "json",
        ],
        trusted_clock=_Clock(),
    )

    captured = capsys.readouterr()
    assert status == 1
    payload = json.loads(captured.out)
    assert captured.out.encode("utf-8") == (
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    assert payload["contract_version"] == "current-price-context@v1"
    assert payload["acquisition_mode"] == "RETAINED_ONLY"
    assert captured.err == ""


def test_price_context_current_maps_invalid_and_stopped_outcomes_to_frozen_exits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = (tmp_path / "retained").resolve()
    root.mkdir(mode=0o700)
    request_file = (tmp_path / "request.json").resolve()
    request_file.write_text(
        json.dumps(
            {
                "contract_version": "current-price-context-request@v1",
                "data_selection_time": "2026-09-15T09:00:00.000000Z",
                "admission_deadline": "2026-09-15T09:30:00.000000Z",
                "schedule_identity_sha256": "a" * 64,
                "members": [
                    {
                        "isin": "INE467B01029",
                        "exchange": "NSE",
                        "instrument_type": "EQUITY",
                        "segment": "EQ",
                        "effective_symbol": "AAA",
                        "valid_from": "2020-01-01",
                        "valid_through": "2030-01-01",
                    }
                ],
                "questions": [
                    "RAW_MARKET_STRUCTURE",
                    "RAW_20_SESSION_DIRECTION",
                    "RAW_COHORT_BREADTH",
                    "RAW_INDUSTRY_PARTICIPATION",
                ],
                "industry_archive_reference": None,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    request_file.chmod(0o600)
    argv = [
        "price-context-current",
        "--input-file",
        str(request_file),
        "--storage-root",
        str(root),
        "--output",
        "json",
    ]

    assert main([*argv, "--acquire-missing", "unexpected"], trusted_clock=_Clock()) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "request_invalid\n"

    request = current_price_context_request_from_canonical_json_bytes_v1(
        request_file.read_bytes()
    )
    stopped = replace(
        research_current_price_context_v1(request, root, clock=_Clock()),
        acquisition_mode="ACQUIRE_MISSING",
        acquisition_outcome="STOPPED",
        result_identity_sha256="",
    )

    def stopped_result(
        *_args: object, **_kwargs: object
    ) -> CurrentPriceContextResultV1:
        return stopped

    monkeypatch.setattr(cli_module, "research_current_price_context_v1", stopped_result)

    assert main(argv, trusted_clock=_Clock()) == 1
    captured = capsys.readouterr()
    assert captured.out.encode("utf-8") == stopped.canonical_json_bytes()
    assert captured.err == ""


def test_price_context_current_unexpected_fault_is_the_fixed_internal_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = (tmp_path / "retained").resolve()
    root.mkdir(mode=0o700)
    input_file = (tmp_path / "request.json").resolve()
    input_file.write_text(
        json.dumps(
            {
                "contract_version": "current-price-context-request@v1",
                "data_selection_time": "2026-09-15T09:00:00.000000Z",
                "admission_deadline": "2026-09-15T09:30:00.000000Z",
                "schedule_identity_sha256": "a" * 64,
                "members": [
                    {
                        "isin": "INE467B01029",
                        "exchange": "NSE",
                        "instrument_type": "EQUITY",
                        "segment": "EQ",
                        "effective_symbol": "AAA",
                        "valid_from": "2020-01-01",
                        "valid_through": "2030-01-01",
                    }
                ],
                "questions": [
                    "RAW_MARKET_STRUCTURE",
                    "RAW_20_SESSION_DIRECTION",
                    "RAW_COHORT_BREADTH",
                    "RAW_INDUSTRY_PARTICIPATION",
                ],
                "industry_archive_reference": None,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    input_file.chmod(0o600)

    def unexpected(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("injected service defect")

    monkeypatch.setattr(cli_module, "research_current_price_context_v1", unexpected)

    assert (
        main(
            [
                "price-context-current",
                "--input-file",
                str(input_file),
                "--storage-root",
                str(root),
                "--output",
                "json",
            ],
            trusted_clock=_Clock(),
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "internal_error\n"
