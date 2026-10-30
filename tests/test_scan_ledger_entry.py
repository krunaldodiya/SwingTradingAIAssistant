from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))


def _load(name: str):
    path = Path(__file__).parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


writer = _load("write_scan_ledger_entry")
checker = _load("check_ledger_coverage")


def _scan_payload(**overrides: object) -> dict[str, object]:
    scan: dict[str, object] = {
        "schema": "swing-trade-scan@v3",
        "scan_timestamp": "2026-10-29T14:38:06.817545Z",
        "latest_completed_session": "2026-10-29",
        "total_stocks_scanned": 200,
        "candidate_count": 1,
        "eligible_count": 175,
        "ineligible_count": 13,
        "unknown_count": 11,
        "priority_validated_candidate_count": 1,
        "tier2_fallback_triggered": True,
        "benchmark_median_return_20d": "-3.51%",
        "market_regime": {"regime": "RANGE_OR_TRANSITION", "uptrend_percent": "13.0%"},
        "candidates": [
            {
                "symbol": "BSE",
                "universe_tier": "NIFTY_100",
                "decision": "RESEARCH_CANDIDATE",
                "safety_eligibility": {"status": "ELIGIBLE"},
                "policy_decision": {"disposition": "RESEARCH_CANDIDATE"},
                "candidate_summary": {
                    "industry": "Financial Services",
                    "setup_event": "BOS",
                    "setup_direction": "UP",
                    "event_session": "2026-10-28",
                    "age_completed_sessions": 1,
                    "current_price_inr": "3502",
                    "broken_high_level_inr": "3455",
                    "supporting_stop_reference_inr": "3190",
                    "risk_per_share_inr": "312",
                    "price_action_quality": {
                        "body_percent": "53.13",
                        "candle_direction": "BULLISH",
                        "quality": "DECISIVE_BODY",
                    },
                },
            }
        ],
        "other_stocks": [
            {"symbol": "ABC", "decision": "UNKNOWN", "failed_rule": "SOME_RULE"}
        ],
    }
    scan.update(overrides)
    return {"schema": "scan-decision-evidence-envelope@v1", "scan": scan}


def test_degenerate_page_is_refused() -> None:
    """A page where no member reached a safety outcome is not a market result."""
    scan = _scan_payload(
        candidate_count=0,
        eligible_count=0,
        ineligible_count=0,
        unknown_count=200,
        candidates=[],
        other_stocks=[
            {"symbol": f"S{index}", "failed_rule": "OBSERVATION_STRUCTURE_NOT_READY"}
            for index in range(3)
        ],
    )
    reason = writer.degenerate_reason(writer._scan_section(scan))
    assert reason is not None
    assert "no member reached a safety outcome" in reason


def test_rejected_safety_credential_is_refused() -> None:
    """A distinct eligibility-layer failure must not look like a market result.

    The scan's failed_rule is the first eligibility rule id, and safety uses a
    different provider from observation, so an allowlist of observation codes
    would miss this case and record a failed pass as a zero-candidate day.
    """
    scan = _scan_payload(
        candidate_count=0,
        eligible_count=0,
        ineligible_count=0,
        unknown_count=200,
        candidates=[],
        other_stocks=[
            {"symbol": f"S{index}", "failed_rule": "CURRENT_UPSTOX_QUOTE_BINDING"}
            for index in range(3)
        ],
    )
    reason = writer.degenerate_reason(writer._scan_section(scan))
    assert reason is not None
    assert "CURRENT_UPSTOX_QUOTE_BINDING" in reason


def test_empty_pass_is_refused() -> None:
    scan = _scan_payload(
        total_stocks_scanned=0, candidate_count=0, candidates=[], other_stocks=[]
    )
    assert writer.degenerate_reason(writer._scan_section(scan)) is not None


def test_mixed_failure_page_is_a_real_pass() -> None:
    """Genuine mixed outcomes stay recordable even with zero candidates."""
    scan = _scan_payload(
        candidate_count=0,
        eligible_count=175,
        ineligible_count=13,
        candidates=[],
    )
    assert writer.degenerate_reason(writer._scan_section(scan)) is None


def test_entry_renders_candidate_facts_and_reasons() -> None:
    text = writer.build_entry(
        scan_envelope=_scan_payload(),
        analysis=None,
        research=None,
        lifecycle=None,
        now=datetime(2026, 10, 29, 20, 45, tzinfo=IST),
        status="recorded",
        commands=["signal-decisions scan --nifty200"],
    )
    assert "date: 2026-10-29 20:45 IST" in text
    assert "completed session 2026-10-29" in text
    assert "### BSE - RESEARCH_CANDIDATE" in text
    assert "broken high INR 3455" in text
    assert "| 1 | UNKNOWN / SOME_RULE |" in text
    assert "53.13% of range" in text


def test_backfill_states_the_method_is_not_restated() -> None:
    """A backfilled entry must not claim a command sequence it does not know."""
    text = writer.build_entry(
        scan_envelope=_scan_payload(),
        analysis=None,
        research=None,
        lifecycle=None,
        now=datetime(2026, 10, 29, 20, 45, tzinfo=IST),
        status="recorded",
        commands=[],
        backfill_note="Backfilled 2026-10-29 20:45 IST from the retained page.",
    )
    assert "Backfilled 2026-10-29 20:45 IST" in text
    assert "original command sequence was not recorded" in text


def test_entry_is_appended_once_per_handle(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger"
    (ledger / "entries" / "2026").mkdir(parents=True)
    scan_path = tmp_path / "scan.json"
    scan_path.write_text(json.dumps(_scan_payload()))

    def run() -> int:
        return writer.main(
            [
                "--scan-json",
                str(scan_path),
                "--ledger-root",
                str(ledger),
                "--status",
                "unconfirmed",
            ]
        )

    assert run() == 0
    entries = sorted((ledger / "entries" / "2026").glob("*.md"))
    assert len(entries) == 1
    assert entries[0].name.startswith("2026-10-29-")
    assert run() == 0
    assert len(sorted((ledger / "entries" / "2026").glob("*.md"))) == 1


def test_checker_reports_missing_and_ignores_degenerate(
    tmp_path: Path,
) -> None:
    storage = tmp_path / "storage"
    evidence = storage / "scan-decision-evidence-v1"
    evidence.mkdir(parents=True)
    real = _scan_payload()
    (evidence / "real.json").write_text(
        json.dumps({**real, "decision_evidence_handle": "a" * 64})
    )
    degenerate = _scan_payload(
        candidate_count=0,
        eligible_count=0,
        ineligible_count=0,
        unknown_count=200,
        latest_completed_session="2026-10-28",
        candidates=[],
        other_stocks=[
            {"symbol": "ABC", "failed_rule": "OBSERVATION_STRUCTURE_NOT_READY"}
        ],
    )
    (evidence / "bad.json").write_text(
        json.dumps({**degenerate, "decision_evidence_handle": "b" * 64})
    )
    ledger = tmp_path / "ledger"
    (ledger / "entries" / "2026").mkdir(parents=True)

    report = checker.build_report(storage_root=storage, ledger_root=ledger, since=None)
    states = {row["session"]: row["state"] for row in report}
    assert states == {"2026-10-28": "DEGENERATE_ONLY", "2026-10-29": "MISSING"}

    (ledger / "entries" / "2026" / "2026-10-29-manual.md").write_text(
        f"evidence: decision-evidence handle {'a' * 64}"
    )
    report = checker.build_report(storage_root=storage, ledger_root=ledger, since=None)
    states = {row["session"]: row["state"] for row in report}
    assert states["2026-10-29"] == "OK"
    assert states["2026-10-28"] == "DEGENERATE_ONLY"


def test_schedule_installer_tracks_every_unit() -> None:
    """Both schedules must be restorable from the repository alone."""
    root = Path(__file__).parents[1] / "scripts"
    units = {
        "swing-daily-scan.service",
        "swing-daily-scan.timer",
        "research-ledger-sync.service",
        "research-ledger-sync.timer",
    }
    present = {path.name for path in (root / "systemd").glob("*")}
    assert units <= present
    installer = (root / "install_research_schedule.sh").read_text()
    for unit in units:
        assert unit in installer
    for placeholder in ("@REPO@", "@STORE@", "@LEDGER@", "@LOGDIR@"):
        assert placeholder in installer


def test_completed_session_stays_unestablished_without_admitted_evidence() -> None:
    """The run timestamp is a label, not the market session."""
    scan = _scan_payload()["scan"]
    scan.pop("latest_completed_session", None)
    scan.pop("candidates")
    assert writer.completed_session(scan) == (None, "unestablished")


def test_completed_session_comes_from_candidate_safety_ledger() -> None:
    scan = _scan_payload()["scan"]
    scan.pop("latest_completed_session", None)
    candidate = scan["candidates"][0]
    candidate["safety_eligibility"] = {
        "status": "ELIGIBLE",
        "explanation_ledger": [
            {"derived_measurements": {"latest_completed_session": "2026-10-28"}}
        ],
    }
    assert writer.completed_session(scan) == ("2026-10-28", "candidate_safety_ledger")


def test_entry_never_labels_run_timestamp_as_completed_session() -> None:
    scan = _scan_payload()["scan"]
    scan.pop("latest_completed_session", None)
    scan.pop("candidates")
    text = writer.build_entry(
        scan_envelope={"scan": scan},
        analysis=None,
        research=None,
        lifecycle=None,
        now=datetime(2026, 10, 29, 20, 45, tzinfo=IST),
        status="recorded",
        commands=[],
    )
    assert "completed session unestablished (research-run label 2026-10-29)" in text


def test_ledger_filename_disambiguates_a_shared_prefix(tmp_path: Path) -> None:
    """Two handles sharing an eight-character prefix must not collide."""
    ledger = tmp_path / "ledger"
    (ledger / "entries" / "2026").mkdir(parents=True)
    first = "a" * 8 + "0" * 56
    second = "a" * 8 + "1" * 56
    one = writer.resolve_target(ledger, "2026-10-29", first)
    one.write_text(f"handle {first}")
    two = writer.resolve_target(ledger, "2026-10-29", second)
    assert two != one
    assert two.name.endswith("-nifty200-scan.md")


def test_concurrent_writers_record_one_entry(tmp_path: Path) -> None:
    """Two simultaneous passes over the same page must not duplicate entries."""
    ledger = tmp_path / "ledger"
    (ledger / "entries" / "2026").mkdir(parents=True)
    scan_path = tmp_path / "scan.json"
    scan_path.write_text(json.dumps(_scan_payload()))
    script = Path(__file__).parents[1] / "scripts" / "write_scan_ledger_entry.py"
    command = [
        sys.executable,
        str(script),
        "--scan-json",
        str(scan_path),
        "--ledger-root",
        str(ledger),
        "--status",
        "recorded",
    ]
    procs = [
        subprocess.Popen(  # noqa: S603 - trusted repository script under test
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        for _ in range(4)
    ]
    for proc in procs:
        proc.communicate(timeout=60)
        assert proc.returncode == 0
    entries = sorted((ledger / "entries" / "2026").glob("*.md"))
    assert len(entries) == 1


def test_writer_discards_partial_entry_on_failure(tmp_path: Path, monkeypatch) -> None:
    """A half-written or wrongly-permissioned entry must not survive."""
    ledger = tmp_path / "ledger"
    (ledger / "entries" / "2026").mkdir(parents=True)
    scan_path = tmp_path / "scan.json"
    scan_path.write_text(json.dumps(_scan_payload()))

    def fail_chmod(*_args: object, **_kwargs: object) -> None:
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(writer.os, "chmod", fail_chmod)
    code = writer.main(["--scan-json", str(scan_path), "--ledger-root", str(ledger)])
    assert code == 2
    assert list((ledger / "entries" / "2026").glob("*.md")) == []


def test_publish_is_atomic_and_leaves_no_staging_file(tmp_path: Path) -> None:
    """Only the finished, correctly permissioned entry becomes visible."""
    ledger = tmp_path / "ledger"
    (ledger / "entries" / "2026").mkdir(parents=True)
    scan_path = tmp_path / "scan.json"
    scan_path.write_text(json.dumps(_scan_payload()))
    assert (
        writer.main(["--scan-json", str(scan_path), "--ledger-root", str(ledger)]) == 0
    )
    files = list((ledger / "entries" / "2026").iterdir())
    assert [path.suffix for path in files] == [".md"]
    assert not any(path.name.startswith(".staged-") for path in files)
    assert files[0].stat().st_mode & 0o777 == 0o600
    assert "status: unconfirmed" in files[0].read_text()


def test_staging_leftover_is_not_treated_as_a_record(tmp_path: Path) -> None:
    """A stranded temporary file must never satisfy the duplicate check."""
    ledger = tmp_path / "ledger"
    directory = ledger / "entries" / "2026"
    directory.mkdir(parents=True)
    handle = "a" * 64
    (directory / ".staged-abandoned.md").write_text(f"handle {handle}")
    scan_path = tmp_path / "scan.json"
    payload = _scan_payload()
    payload["decision_evidence_handle"] = handle
    scan_path.write_text(json.dumps(payload))
    assert (
        writer.main(["--scan-json", str(scan_path), "--ledger-root", str(ledger)]) == 0
    )
    published = [path for path in directory.iterdir() if path.name.endswith(".md")]
    assert len(published) == 2  # the stranded temp file plus the real entry
    assert any(handle in path.read_text() for path in published)


def test_staging_files_are_excluded_from_off_device_mirror() -> None:
    """A stranded staging file must never become a permanent remote object."""
    root = Path(__file__).parents[1]
    runner = (root / "scripts" / "daily_after_close_scan.sh").read_text()
    unit = (root / "scripts" / "systemd" / "research-ledger-sync.service").read_text()
    assert "--exclude" in runner and ".staged-*" in runner
    assert "--exclude" in unit and ".staged-*" in unit
