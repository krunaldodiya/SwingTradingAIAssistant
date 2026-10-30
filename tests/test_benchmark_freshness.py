from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet
import pytest

spec = importlib.util.spec_from_file_location(
    "check_benchmark_freshness",
    Path(__file__).parents[1] / "scripts" / "check_benchmark_freshness.py",
)
assert spec is not None and spec.loader is not None
freshness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(freshness)


def _store(tmp_path: Path, sessions: list[date]) -> None:
    directory = tmp_path / "adjusted_daily" / "provider=bharatstock"
    directory.mkdir(parents=True)
    parquet.write_table(
        pa.table({"session": sessions, "symbol": ["AAA"] * len(sessions)}),
        directory / "part.parquet",
    )


def test_store_older_than_bound_session_is_stale(tmp_path: Path) -> None:
    """A store that stops before the scanned session cannot support the claim."""
    _store(tmp_path, [date(2026, 10, 22), date(2026, 10, 23)])

    report = freshness.check(storage_root=tmp_path, expected="2026-10-29")

    assert report["state"] == "STALE"
    assert report["store_last_session"] == "2026-10-23"
    assert report["lag_sessions_approx"] == 6


def test_store_covering_bound_session_is_fresh(tmp_path: Path) -> None:
    _store(tmp_path, [date(2026, 10, 23), date(2026, 10, 29)])

    report = freshness.check(storage_root=tmp_path, expected="2026-10-29")

    assert report["state"] == "FRESH"


def test_missing_store_is_unknown_not_stale(tmp_path: Path) -> None:
    """Absence of the store is a missing fact, not a verdict about the market."""
    report = freshness.check(storage_root=tmp_path, expected="2026-10-29")

    assert report["state"] == "UNKNOWN"
    assert report["reason"] == "benchmark store is unavailable"


def test_unresolvable_bound_session_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store(tmp_path, [date(2026, 10, 29)])
    monkeypatch.setattr(freshness, "_bound_session", lambda root, handle=None: None)

    report = freshness.check(storage_root=tmp_path, expected=None)

    assert report["state"] == "UNKNOWN"
    assert report["reason"] == "bound session is unavailable"


def test_exit_codes_distinguish_states(tmp_path: Path) -> None:
    """The runner records the code without failing, so each state must be distinct."""
    _store(tmp_path, [date(2026, 10, 23)])

    assert (
        freshness.main(
            [
                "--storage-root",
                str(tmp_path),
                "--expected-session",
                "2026-10-23",
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert (
        freshness.main(
            [
                "--storage-root",
                str(tmp_path),
                "--expected-session",
                "2026-10-29",
                "--output",
                "json",
            ]
        )
        == 3
    )
    assert (
        freshness.main(
            ["--storage-root", str(tmp_path / "missing"), "--output", "json"]
        )
        == 2
    )


def test_invalid_expected_session_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _store(tmp_path, [date(2026, 10, 29)])

    code = freshness.main(
        ["--storage-root", str(tmp_path), "--expected-session", "29-10-2026"]
    )

    assert code == 2
    assert "expected session must be YYYY-MM-DD" in capsys.readouterr().err


def test_report_states_the_claim_rule(tmp_path: Path) -> None:
    _store(tmp_path, [date(2026, 10, 23)])

    report = freshness.check(storage_root=tmp_path, expected="2026-10-29")

    caveat = report["caveat"]
    assert isinstance(caveat, str) and "do not restate" in caveat
    assert json.loads(json.dumps(report))["state"] == "STALE"


def test_handle_binds_to_that_pages_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A concurrent historical page must not decide this page's session."""
    _store(tmp_path, [date(2026, 10, 23)])
    monkeypatch.setattr(
        freshness,
        "read_scan_decision_evidence_completed_session_v1",
        lambda root, handle: {"completed_session": "2026-10-29"},
    )

    report = freshness.check(
        storage_root=tmp_path, expected=None, evidence_handle="a" * 64
    )

    assert report["state"] == "STALE"
    assert report["expected_session"] == "2026-10-29"


def test_unreadable_handle_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store(tmp_path, [date(2026, 10, 29)])

    def refuse(root: Path, handle: str) -> dict[str, object]:
        raise freshness.ScanDecisionEvidenceUnavailable("DECISION_EVIDENCE_UNAVAILABLE")

    monkeypatch.setattr(
        freshness, "read_scan_decision_evidence_completed_session_v1", refuse
    )

    report = freshness.check(
        storage_root=tmp_path, expected=None, evidence_handle="a" * 64
    )

    assert report["state"] == "UNKNOWN"
    assert report["reason"] == "bound session is unavailable"
