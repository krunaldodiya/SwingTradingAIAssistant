"""Composite capture writes both stores per cohort and independently."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.market_data.historical_nifty_universe import (
    build_historic_nifty_universe,
    retain_historic_nifty_universe,
)

_ROOT = Path(__file__).parents[1]
SCRIPT = _ROOT / "scripts" / "capture_provider_data.sh"
_PLANNER_SPEC = importlib.util.spec_from_file_location(
    "capture_adjusted_cohorts",
    _ROOT / "scripts" / "capture_adjusted_cohorts.py",
)
assert _PLANNER_SPEC is not None and _PLANNER_SPEC.loader is not None
planner = importlib.util.module_from_spec(_PLANNER_SPEC)
_PLANNER_SPEC.loader.exec_module(planner)
STAMP = "2026-11-14"
STAGE_START = "2026-10-01"
_NIFTY50 = tuple(f"A{index:03d}" for index in range(50))
_NIFTYNEXT50 = tuple(f"B{index:03d}" for index in range(50))
_NIFTY100 = _NIFTY50 + _NIFTYNEXT50
_NIFTY200 = _NIFTY100 + tuple(f"C{index:03d}" for index in range(100))
_URLS = {
    "nifty50": "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
    "niftynext50": (
        "https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv"
    ),
    "nifty100": "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
    "nifty200": "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv",
}


def _csv(symbols: tuple[str, ...], *, isin_base: int) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(("Company Name", "Industry", "Symbol", "Series", "ISIN Code"))
    for offset, symbol in enumerate(symbols):
        writer.writerow(
            (
                f"Company {symbol}",
                "Industry",
                symbol,
                "EQ",
                f"INE{isin_base + offset:09d}",
            )
        )
    return buffer.getvalue().encode()


def _governed_snapshot(store: Path) -> None:
    store.mkdir(mode=0o700, parents=True, exist_ok=True)
    store.chmod(0o700)
    universe = build_historic_nifty_universe(
        _csv(_NIFTY50, isin_base=0),
        _csv(_NIFTYNEXT50, isin_base=50),
        _csv(_NIFTY100, isin_base=0),
        _csv(_NIFTY200, isin_base=0),
        window_start=date(2026, 1, 1),
        window_end=date(2026, 12, 31),
        nifty50_source_url=_URLS["nifty50"],
        niftynext50_source_url=_URLS["niftynext50"],
        nifty100_source_url=_URLS["nifty100"],
        nifty200_source_url=_URLS["nifty200"],
        retrieved_at=datetime(2026, 11, 14, tzinfo=UTC),
    )
    retain_historic_nifty_universe(store, universe)


def _member_keys() -> tuple[tuple[str, str], ...]:
    return tuple((f"INE{index:09d}", symbol) for index, symbol in enumerate(_NIFTY200))


def _key(index: int) -> str:
    isin, symbol = _member_keys()[index]
    return f"{isin}:NSE:{symbol}"


def _cohort_keys(index: int) -> tuple[str, ...]:
    return tuple(_key(position) for position in range(index * 100, (index + 1) * 100))


def _identity_columns(keys: tuple[str, ...]) -> dict[str, list[str]]:
    return {
        "isin": [key.split(":")[0] for key in keys],
        "exchange": [key.split(":")[1] for key in keys],
        "symbol": [key.split(":")[2] for key in keys],
    }


def _adjusted(store: Path, keys: tuple[str, ...], session: str) -> None:
    """Write the production adjusted schema: separate identity columns."""
    import pyarrow as pa  # noqa: PLC0415 - test-only optional dependency
    import pyarrow.parquet as pq  # noqa: PLC0415

    identity = hashlib.sha256(",".join(keys).encode()).hexdigest()
    directory = (
        store / "adjusted_daily" / "provider=bharatstock" / f"request={identity}"
    )
    directory.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table(
            {
                **_identity_columns(keys),
                "session": pa.array(
                    [date.fromisoformat(session)] * len(keys), type=pa.date32()
                ),
                "open": [100.0] * len(keys),
                "high": [101.0] * len(keys),
                "low": [99.0] * len(keys),
                "close": [100.5] * len(keys),
                "volume": [1000] * len(keys),
            }
        ),
        directory / "data.parquet",
    )


def _raw_script(
    path: Path,
    *,
    status: str = "COMPLETE",
    exit_code: int = 0,
    failed: int = 0,
    remaining_pending: int = 0,
    requests_used: int = 101,
    configured_max: int = 2400,
    latest_session: str = "2026-11-13",
) -> None:
    complete = status == "COMPLETE"
    payload = {
        "schema": "raw-session-capture@v1",
        "status": status,
        "members": 200,
        "completed": 200 if complete else 199,
        "skipped": 0,
        "failed": failed,
        "failed_isins": [] if failed == 0 else ["INE000000000"],
        "requests_used": requests_used,
        "requests_configured_max": configured_max,
        "no_newer_session": 1,
        "requests_configured_max_basis": (
            "MAX_REQUESTS_PER_MEMBER * PER_MEMBER_ATTEMPTS * symbols_considered"
        ),
        "max_requests_per_member": 8,
        "sessions_written": 101,
        "latest_session": latest_session,
        "remaining_pending": remaining_pending,
        "start": STAGE_START,
        "end": STAMP,
        "universe": {
            "path": "universe.json",
            "sha256": "f" * 64,
            "schema": "retained-nifty-universe@v3",
            "members": 200,
        },
        "universe_snapshot": "universe.json",
        "universe_snapshot_sha256": "f" * 64,
        "runtime": {"path": str(path), "sha256": "e" * 64, "python": "3.14.0"},
        "started_at": "2026-11-14T14:40:00Z",
        "completed_at": "2026-11-14T14:45:00Z",
        "symbols": {
            "S0": {"status": "FAILED" if failed else "COMPLETE", "requests_used": 1},
            "S1": {"status": "SKIPPED", "requests_used": 0},
            "S2": {"status": "NO_NEWER_SESSION", "requests_used": 1},
        },
    }
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"print(json.dumps({payload!r}))\n"
        f"raise SystemExit({exit_code})\n"
    )
    path.chmod(0o755)


_DOWNLOADER = """#!{python}
import json
import os
import sys
from datetime import date

args = sys.argv[1:]
instruments = [args[index + 1] for index, value in enumerate(args) if value == "--instrument"]
end = [args[index + 1] for index, value in enumerate(args) if value == "--end"][0]
root = [args[index + 1] for index, value in enumerate(args) if value == "--storage-root"][0]
with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as handle:
    handle.write(" ".join(args) + "\\n")
count_path = os.environ["STUB_COUNT"]
count = int(open(count_path, encoding="utf-8").read()) if os.path.exists(count_path) else 0
count += 1
open(count_path, "w", encoding="utf-8").write(str(count))
limit = int(os.environ.get("STUB_WRITE_LIMIT", "0"))
written = instruments[:limit] if limit else instruments
if os.environ.get("STUB_WRITE", "1") == "1" and written:
    import pyarrow as pa
    import pyarrow.parquet as pq

    directory = os.path.join(
        root,
        "adjusted_daily",
        "provider=bharatstock",
        "request=" + format(count, "064d"),
    )
    os.makedirs(directory, exist_ok=True)
    parts = [value.split(":") for value in written]
    pq.write_table(
        pa.table(
            {{
                "isin": [part[0] for part in parts],
                "exchange": [part[1] for part in parts],
                "symbol": [part[2] for part in parts],
                "session": pa.array(
                    [date.fromisoformat(end)] * len(written), type=pa.date32()
                ),
                "open": [100.0] * len(written),
                "high": [101.0] * len(written),
                "low": [95.0] * len(written),
                "close": [99.0] * len(written),
                "volume": [1000] * len(written),
            }}
        ),
        os.path.join(directory, "data.parquet"),
    )
if {exit_code} == 0 and os.environ.get("STUB_EMPTY", "0") != "1":
    print(
        json.dumps(
            {{
                "outcome": "INSERTED",
                "provider_requests_used": {requests},
            }}
        )
    )
message = os.environ.get("STUB_FAIL_MESSAGE", "")
if message:
    sys.stderr.write("download failed: " + message + "\\n")
raise SystemExit(int(os.environ.get("STUB_EXIT", "{exit_code}")))
"""


def _downloader(
    path: Path,
    *,
    provider_requests: int = 4,
    exit_code: int = 0,
) -> None:
    path.write_text(
        _DOWNLOADER.format(
            python=sys.executable,
            requests=provider_requests,
            exit_code=exit_code,
        )
    )
    path.chmod(0o755)


def _doppler(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env bash\n"
        'while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do shift; done\n'
        "shift\n"
        'exec "$@"\n'
    )
    path.chmod(0o755)


def _run(
    root: Path,
    raw: Path,
    downloader: Path,
    doppler: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ | {
        "SWING_REPO": str(SCRIPT.parents[1]),
        "SWING_STORAGE_ROOT": str(root / "store"),
        "SWING_LOG_DIR": str(root / "log"),
        "SWING_DATE_OVERRIDE": STAMP,
        "SWING_CAPTURE_START": STAGE_START,
        "SWING_CAPTURE_PYTHON": sys.executable,
        "SWING_CAPTURE_RAW_SCRIPT": str(raw),
        "SWING_CAPTURE_DOWNLOADER": str(downloader),
        "DOPPLER_BIN": str(doppler),
        "STUB_LOG": str(root / "calls.log"),
        "STUB_COUNT": str(root / "calls.count"),
    }
    if extra_env:
        env |= extra_env
    return subprocess.run(  # noqa: S603 - trusted repository test script
        [str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )


def _calls(root: Path) -> list[str]:
    path = root / "calls.log"
    return path.read_text().splitlines() if path.exists() else []


def _receipt(root: Path) -> dict[str, object]:
    return json.loads((root / "log" / f"capture-{STAMP}.json").read_text())


def _fixture(
    tmp_path: Path,
) -> tuple[Path, Path, Path]:
    _governed_snapshot(tmp_path / "store")
    raw = tmp_path / "raw.py"
    downloader = tmp_path / "downloader"
    doppler = tmp_path / "doppler"
    _raw_script(raw)
    _downloader(downloader)
    _doppler(doppler)
    return raw, downloader, doppler


def test_one_current_cohort_and_one_partially_stale_cohort(
    tmp_path: Path,
) -> None:
    raw, downloader, doppler = _fixture(tmp_path)
    _adjusted(tmp_path / "store", _cohort_keys(0), STAMP)
    # The second cohort is mixed: ten instruments are current, ninety are not.
    _adjusted(tmp_path / "store", _cohort_keys(1)[:10], STAMP)
    _adjusted(tmp_path / "store", _cohort_keys(1)[10:], "2026-11-10")

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 0, result.stderr
    calls = _calls(tmp_path)
    assert len(calls) == 1
    call = calls[0]
    # Only the stale cohort's missing members are requested, from the range
    # after its oldest missing instrument's retained session.
    assert call.count("--instrument") == 90
    assert all(key not in call for key in _cohort_keys(0))
    assert all(key not in call for key in _cohort_keys(1)[:10])
    assert all(key in call for key in _cohort_keys(1)[10:])
    assert "--start 2026-11-11" in call
    receipt = _receipt(tmp_path)
    adjusted = cast(dict[str, object], receipt["adjusted"])
    cohorts = cast(list[dict[str, object]], adjusted["cohorts"])
    assert cohorts[0]["status"] == "SKIPPED"
    assert cohorts[0]["start"] is None
    assert cohorts[1]["status"] == "COMPLETE"
    assert cohorts[1]["missing"] == 90
    assert cohorts[1]["oldest_missing"] == _cohort_keys(1)[10]
    assert cohorts[1]["missing_after_batch"] == 0
    assert receipt["status"] == "COMPLETE"
    # A second run has both cohorts current and makes no downloader call.
    result = _run(tmp_path, raw, downloader, doppler)
    assert result.returncode == 0, result.stderr
    assert len(_calls(tmp_path)) == 1
    again = _receipt(tmp_path)
    assert again["status"] == "COMPLETE"
    assert cast(dict[str, object], again["adjusted"])["status"] == "SKIPPED"
    assert cast(dict[str, object], again["adjusted"])["cohorts_skipped"] == 2


def test_partial_cohort_batch_is_incomplete_and_rerun_requests_only_missing(
    tmp_path: Path,
) -> None:
    raw, downloader, doppler = _fixture(tmp_path)
    _adjusted(tmp_path / "store", _cohort_keys(0), STAMP)
    _adjusted(tmp_path / "store", _cohort_keys(1), "2026-11-10")

    first = _run(
        tmp_path,
        raw,
        downloader,
        doppler,
        extra_env={"STUB_WRITE_LIMIT": "10"},
    )

    assert first.returncode == 1
    receipt = _receipt(tmp_path)
    assert receipt["status"] == "INCOMPLETE"
    adjusted = cast(dict[str, object], receipt["adjusted"])
    assert adjusted["status"] == "INCOMPLETE"
    cohorts = cast(list[dict[str, object]], adjusted["cohorts"])
    assert cohorts[1]["status"] == "INCOMPLETE"
    assert cohorts[1]["error"] == "COHORT_INCOMPLETE_AFTER_BATCH"
    assert cohorts[1]["missing_after_batch"] == 90
    assert "--start 2026-11-11" in _calls(tmp_path)[0]

    second = _run(tmp_path, raw, downloader, doppler)

    assert second.returncode == 0, second.stderr
    calls = _calls(tmp_path)
    assert len(calls) == 2
    second_call = calls[1]
    assert second_call.count("--instrument") == 90
    for key in _cohort_keys(1)[:10]:
        assert key not in second_call
    after = _receipt(tmp_path)
    assert after["status"] == "COMPLETE"
    assert cast(dict[str, object], after["adjusted"])["status"] == "COMPLETE"


def test_all_cohorts_current_make_no_downloader_call(tmp_path: Path) -> None:
    raw, downloader, doppler = _fixture(tmp_path)
    _adjusted(tmp_path / "store", _cohort_keys(0), STAMP)
    _adjusted(tmp_path / "store", _cohort_keys(1), STAMP)

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 0, result.stderr
    assert _calls(tmp_path) == []
    receipt = _receipt(tmp_path)
    adjusted = cast(dict[str, object], receipt["adjusted"])
    assert adjusted["status"] == "SKIPPED"
    assert adjusted["cohorts_skipped"] == 2
    assert adjusted["instruments_submitted"] == 0
    assert adjusted["provider_requests_used"] == 0
    assert adjusted["provider_request_budget"] == 0
    assert receipt["status"] == "COMPLETE"


def test_quota_labels_requests_and_instruments_separately(tmp_path: Path) -> None:
    raw, downloader, doppler = _fixture(tmp_path)
    _adjusted(tmp_path / "store", _cohort_keys(0), STAMP)

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 0, result.stderr
    receipt = _receipt(tmp_path)
    assert "requests_used" not in receipt
    quota = cast(dict[str, dict[str, object]], receipt["quota"])
    assert quota["raw"]["provider_requests_used"] == 101
    assert quota["raw"]["basis"] == "PROVIDER_REQUESTS_INCLUDING_FAILED_ATTEMPTS"
    assert quota["adjusted"]["provider_requests_used"] == 4
    assert quota["adjusted"]["provider_requests_complete"] is True
    assert quota["adjusted"]["provider_request_budget"] == 2000
    assert quota["adjusted"]["instruments_submitted"] == 100
    assert quota["adjusted"]["basis"] == "DOWNLOADER_CLI_RECEIPT"
    adjusted = cast(dict[str, object], receipt["adjusted"])
    assert "requests_used" not in adjusted
    raw_stage = cast(
        dict[str, object], cast(dict[str, object], receipt["stages"])["raw"]
    )
    assert raw_stage["no_newer_session"] == 1
    assert receipt["symbols_no_newer_session"] == 1
    runtime = cast(dict[str, object], receipt["runtime"])
    adjusted_runtime = cast(dict[str, object], runtime["adjusted"])
    planner_runtime = cast(dict[str, object], adjusted_runtime["planner"])
    downloader_runtime = cast(dict[str, object], adjusted_runtime["downloader"])
    assert (
        planner_runtime["sha256"]
        == hashlib.sha256(
            (_ROOT / "scripts" / "capture_adjusted_cohorts.py").read_bytes()
        ).hexdigest()
    )
    assert (
        downloader_runtime["sha256"]
        == hashlib.sha256(
            (_ROOT / "src" / "equity_data_downloader" / "core.py").read_bytes()
        ).hexdigest()
    )


def test_raw_failure_is_an_incomplete_nonzero_receipt(tmp_path: Path) -> None:
    raw, downloader, doppler = _fixture(tmp_path)
    _raw_script(raw, status="INCOMPLETE", exit_code=1, failed=1, remaining_pending=1)
    _adjusted(tmp_path / "store", _cohort_keys(0), STAMP)
    _adjusted(tmp_path / "store", _cohort_keys(1), STAMP)

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 1
    receipt = _receipt(tmp_path)
    assert receipt["status"] == "INCOMPLETE"
    assert receipt["failed"] == 1
    assert receipt["remaining_pending"] == 1
    assert receipt["failed_isins"] == ["INE000000000"]
    assert cast(dict[str, object], receipt["adjusted"])["status"] == "SKIPPED"


def test_adjusted_failure_preserves_raw_and_fails_the_receipt(
    tmp_path: Path,
) -> None:
    raw, downloader, doppler = _fixture(tmp_path)
    _downloader(downloader, exit_code=1)
    _adjusted(tmp_path / "store", _cohort_keys(0), STAMP)
    _adjusted(tmp_path / "store", _cohort_keys(1), "2026-11-10")

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 1
    receipt = _receipt(tmp_path)
    assert receipt["status"] == "INCOMPLETE"
    assert cast(dict[str, object], receipt["sessions"])["status"] == "COMPLETE"
    assert (tmp_path / "log" / f"capture-sessions-{STAMP}.json").is_file()
    adjusted = cast(dict[str, object], receipt["adjusted"])
    assert adjusted["status"] == "INCOMPLETE"
    assert adjusted["provider_requests_used"] is None
    assert adjusted["provider_requests_complete"] is False
    cohorts = cast(list[dict[str, object]], adjusted["cohorts"])
    assert cohorts[1]["batch_exit_code"] == 1
    assert cohorts[1]["error"] == "COHORT_BATCH_FAILED"


def test_invalid_universe_snapshot_fails_before_any_provider_call(
    tmp_path: Path,
) -> None:
    raw, downloader, doppler = _fixture(tmp_path)
    snapshot = tmp_path / "store" / "universe_snapshots" / "nifty-universe-v3.json"
    payload = json.loads(snapshot.read_text())
    payload["schema"] = "retained-nifty-universe@v2"
    snapshot.write_text(json.dumps(payload))

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 2
    assert "capture_invalid" in result.stderr
    assert _calls(tmp_path) == []
    assert not (tmp_path / "log" / f"capture-{STAMP}.json").exists()


def test_planner_reads_the_production_identity_columns(tmp_path: Path) -> None:
    """The retained store stores bare symbols plus isin/exchange, not keys."""
    _governed_snapshot(tmp_path / "store")
    _adjusted(tmp_path / "store", _cohort_keys(0), STAMP)

    retained = planner.retained_sessions(tmp_path / "store")

    assert retained[_key(0)] == date.fromisoformat(STAMP)
    # A bare symbol is not a universe key on its own.
    assert "C000" not in retained
    value = planner.plan(
        tmp_path / "store",
        date.fromisoformat(STAMP),
        date.fromisoformat(STAGE_START),
    )
    cohorts = cast(list[dict[str, object]], value["cohorts"])
    assert cohorts[0]["status"] == "SKIPPED"
    assert cohorts[1]["status"] == "PENDING"
    assert (
        cast(dict[str, object], value["runtime"])["sha256"]
        == hashlib.sha256(
            (_ROOT / "scripts" / "capture_adjusted_cohorts.py").read_bytes()
        ).hexdigest()
    )


def test_mixed_age_cohort_uses_the_oldest_missing_start(tmp_path: Path) -> None:
    """Only missing members ship; the bounded overlap re-fetch is explicit."""
    raw, downloader, doppler = _fixture(tmp_path)
    _adjusted(tmp_path / "store", _cohort_keys(0), STAMP)
    _adjusted(tmp_path / "store", _cohort_keys(1)[:10], STAMP)
    _adjusted(tmp_path / "store", _cohort_keys(1)[10:15], "2026-11-12")
    _adjusted(tmp_path / "store", _cohort_keys(1)[15:], "2026-11-10")

    result = _run(tmp_path, raw, downloader, doppler)

    assert result.returncode == 0, result.stderr
    calls = _calls(tmp_path)
    assert len(calls) == 1
    call = calls[0]
    # The oldest missing member is 2026-11-10, so the cohort request starts at
    # 2026-11-11 for every missing member, including the five newer at
    # 2026-11-12 (bounded overlap re-fetch, never the full stage window).
    assert "--start 2026-11-11" in call
    assert call.count("--instrument") == 90
    assert _cohort_keys(1)[10] in call
    assert _cohort_keys(1)[15] in call
    receipt = _receipt(tmp_path)
    adjusted = cast(dict[str, object], receipt["adjusted"])
    cohorts = cast(list[dict[str, object]], adjusted["cohorts"])
    assert cohorts[1]["start"] == "2026-11-11"
    assert cast(dict[str, object], adjusted["range"])["start"] == "2026-11-11"


def test_adjusted_no_newer_session_is_a_typed_noop(tmp_path: Path) -> None:
    """A stamp with no published session is a no-op, not a data failure."""
    raw, downloader, doppler = _fixture(tmp_path)
    # Every member already has the previous session; the stamp is a non-trading
    # day, so the only requested session (the stamp itself) returns no rows.
    _adjusted(tmp_path / "store", _cohort_keys(0), "2026-11-13")
    _adjusted(tmp_path / "store", _cohort_keys(1), "2026-11-13")

    result = _run(
        tmp_path,
        raw,
        downloader,
        doppler,
        extra_env={
            "STUB_WRITE": "0",
            "STUB_EXIT": "1",
            "STUB_FAIL_MESSAGE": (
                "provider returned no valid requested member history"
            ),
        },
    )

    assert result.returncode == 0, result.stderr
    receipt = _receipt(tmp_path)
    assert receipt["status"] == "COMPLETE"
    adjusted = cast(dict[str, object], receipt["adjusted"])
    assert adjusted["status"] == "COMPLETE"
    assert adjusted["cohorts_no_newer_session"] == 2
    assert adjusted["cohorts_incomplete"] == 0
    cohorts = cast(list[dict[str, object]], adjusted["cohorts"])
    assert all(cohort["status"] == "NO_NEWER_SESSION" for cohort in cohorts)
    assert all(cohort["error"] is None for cohort in cohorts)
    assert all(cohort["missing_after_batch"] == 100 for cohort in cohorts)


def test_adjusted_failure_with_an_older_gap_is_not_a_noop(tmp_path: Path) -> None:
    raw, downloader, doppler = _fixture(tmp_path)
    _adjusted(tmp_path / "store", _cohort_keys(0), "2026-11-12")

    result = _run(
        tmp_path,
        raw,
        downloader,
        doppler,
        extra_env={
            "STUB_WRITE": "0",
            "STUB_EXIT": "1",
            "STUB_FAIL_MESSAGE": (
                "provider returned no valid requested member history"
            ),
        },
    )

    assert result.returncode == 1
    adjusted = cast(dict[str, object], _receipt(tmp_path)["adjusted"])
    assert adjusted["status"] == "INCOMPLETE"
    cohorts = cast(list[dict[str, object]], adjusted["cohorts"])
    # Cohort 0 starts at 2026-11-13 (older gap), not the stamp: a real failure.
    assert cohorts[0]["status"] == "INCOMPLETE"
    assert cohorts[0]["batch_exit_code"] == 1


def test_no_newer_noop_requires_the_raw_stage_to_see_no_stamp_session(
    tmp_path: Path,
) -> None:
    """A failed raw stage must not let a provider outage look like a no-op."""
    raw, downloader, doppler = _fixture(tmp_path)
    _raw_script(raw, latest_session=STAMP)
    _adjusted(tmp_path / "store", _cohort_keys(0), "2026-11-13")
    _adjusted(tmp_path / "store", _cohort_keys(1), "2026-11-13")

    result = _run(
        tmp_path,
        raw,
        downloader,
        doppler,
        extra_env={
            "STUB_WRITE": "0",
            "STUB_EXIT": "1",
            "STUB_FAIL_MESSAGE": (
                "provider returned no valid requested member history"
            ),
        },
    )

    assert result.returncode == 1
    adjusted = cast(dict[str, object], _receipt(tmp_path)["adjusted"])
    assert adjusted["status"] == "INCOMPLETE"
    assert adjusted["cohorts_no_newer_session"] == 0
