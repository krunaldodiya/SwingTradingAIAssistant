from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from types import ModuleType

import pytest

from swing_trading_ai_assistant.market_data import (
    historical,
    historical_upstox_raw,
    instrument_snapshot,
    instruments,
    schedule_evidence,
)
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    InstrumentSnapshotCorruptError,
    InstrumentSnapshotMetadataV1,
)
from swing_trading_ai_assistant.market_data.instruments import (
    InstrumentCatalog,
    InstrumentCatalogPayloadError,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleEvidenceValidationError,
    ScheduleSession,
    canonical_schedule_bytes,
)

_HISTORICAL_SUCCESS_BYTES = b'{"status":"success","data":{"candles":[]}}'
_RAW_CANONICAL_BYTES = b'{"schema_version":1}'
_CATALOG_BYTES = (
    b'[{"instrument_key":"NSE_EQ|INE002A01018","segment":"NSE_EQ",'
    b'"trading_symbol":"RELIANCE"}]'
)


def _schedule_bytes() -> bytes:
    return canonical_schedule_bytes(
        ExpectedSessionSchedule(
            schema_version=1,
            source="nse",
            source_release="2026-01",
            as_of=datetime(2026, 2, 1, tzinfo=UTC),
            timezone="Asia/Kolkata",
            covered_from=date(2026, 1, 1),
            covered_to=date(2026, 1, 31),
            sessions=(
                ScheduleSession(
                    date(2026, 1, 2),
                    datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
                    datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
                    "regular",
                ),
            ),
        )
    )


def _journal_bytes() -> bytes:
    compressed_digest = "b" * 64
    observation_digest = "a" * 64
    return instrument_snapshot._canonical_journal_bytes(
        InstrumentSnapshotMetadataV1(
            1,
            "upstox-bod-nse",
            date(2026, 1, 2),
            datetime(2026, 1, 2, tzinfo=UTC),
            observation_digest,
            compressed_digest,
            "c" * 64,
            1,
            1,
            f"instrument_snapshots/sha256={compressed_digest}/snapshot.json.gz",
            "instrument_snapshots/"
            f"sha256={compressed_digest}/observations/sha256={observation_digest}.json",
            None,
            None,
        )
    )


@pytest.mark.parametrize(
    ("module", "parse", "payload"),
    (
        pytest.param(
            historical,
            historical._decode_success_candles,
            _HISTORICAL_SUCCESS_BYTES,
            id="historical-success",
        ),
        pytest.param(
            schedule_evidence,
            schedule_evidence._parse_canonical_bytes,
            _schedule_bytes(),
            id="schedule-canonical",
        ),
        pytest.param(
            historical_upstox_raw,
            lambda value: historical_upstox_raw._closed_json(value, 1_000_000),
            _RAW_CANONICAL_BYTES,
            id="raw-closed",
        ),
        pytest.param(
            instrument_snapshot,
            instrument_snapshot._parse_canonical_journal,
            _journal_bytes(),
            id="snapshot-journal",
        ),
        pytest.param(
            instruments,
            InstrumentCatalog.from_json_bytes,
            _CATALOG_BYTES,
            id="instrument-catalog",
        ),
    ),
)
def test_json_boundaries_preserve_unexpected_load_value_error(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    parse: Callable[[bytes], object],
    payload: bytes,
) -> None:
    failure = ValueError("injected decoder implementation fault")

    def fail_loads(*_args: object, **_kwargs: object) -> object:
        raise failure

    monkeypatch.setattr(module.json, "loads", fail_loads)

    with pytest.raises(ValueError) as raised:
        parse(payload)

    assert raised.value is failure


def test_historical_decoder_preserves_memory_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = MemoryError("injected decoder exhaustion")

    def fail_loads(*_args: object, **_kwargs: object) -> object:
        raise failure

    monkeypatch.setattr(historical.json, "loads", fail_loads)

    with pytest.raises(MemoryError) as raised:
        historical._decode_success_candles(_HISTORICAL_SUCCESS_BYTES)

    assert raised.value is failure


@pytest.mark.parametrize(
    ("parse", "payload", "error_type"),
    (
        pytest.param(
            historical._decode_success_candles,
            b'{"status":"success","data":{"candles":' + b"9" * 5000 + b"}}",
            None,
            id="historical-success",
        ),
        pytest.param(
            schedule_evidence.parse_canonical_schedule_bytes,
            b'{"schema_version":' + b"9" * 5000 + b"}",
            ScheduleEvidenceValidationError,
            id="schedule-canonical",
        ),
        pytest.param(
            lambda value: historical_upstox_raw._closed_json(value, 1_000_000),
            b'{"schema_version":' + b"9" * 5000 + b"}",
            historical_upstox_raw._MalformedSourceJson,
            id="raw-closed",
        ),
        pytest.param(
            instrument_snapshot._parse_canonical_journal,
            _journal_bytes().replace(
                b'"schema_version":1', b'"schema_version":' + b"9" * 5000
            ),
            InstrumentSnapshotCorruptError,
            id="snapshot-journal",
        ),
        pytest.param(
            InstrumentCatalog.from_json_bytes,
            b'[{"instrument_key":' + b"9" * 5000 + b"}]",
            InstrumentCatalogPayloadError,
            id="instrument-catalog",
        ),
    ),
)
def test_json_boundaries_retain_long_integer_rejection(
    parse: Callable[[bytes], object],
    payload: bytes,
    error_type: type[Exception] | None,
) -> None:
    prior_limit = sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(4300)
        if error_type is None:
            assert historical._decode_success_candles(payload) == (
                historical._SuccessDecodeStatus.MALFORMED_JSON,
                [],
            )
        else:
            with pytest.raises(error_type):
                parse(payload)
    finally:
        sys.set_int_max_str_digits(prior_limit)
