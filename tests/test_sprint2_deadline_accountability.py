"""Contract tests for the Sprint 2 deadline-accountability record."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, cast

SPRINT_RECORD = Path(__file__).parents[1] / "docs" / "sprints" / "sprint-2.md"
LEDGER = (
    Path(__file__).parents[1]
    / "docs"
    / "sprints"
    / "sprint-2-time-accountability-ledger.json"
)
EXPECTED_EMBEDDED_RECORD_SHA256 = (
    "cd2b800a642a71ea0da3a37f308592a9e416289a26eb4aa54734fecb16a07baf"
)
EXPECTED_LEDGER_SHA256 = (
    "2897219beda73c5b47ade96a1b1b7c17bb6b91430d53a6ee9bf592332ee84534"
)
EXPECTED_DENOMINATOR = [
    "ARK-74",
    "ARK-75",
    "ARK-76",
    "ARK-77",
    "ARK-78",
    "ARK-79",
    "ARK-80",
    "ARK-81",
    "ARK-82",
    "ARK-83",
    "ARK-84",
    "ARK-85",
    "ARK-86",
    "ARK-87",
    "ARK-88",
    "ARK-89",
    "ARK-90",
    "ARK-91",
    "ARK-70",
    "ARK-73",
    "ARK-92",
    "ARK-93",
    "ARK-69",
    "ARK-72",
]


def _record_bytes() -> bytes:
    document = SPRINT_RECORD.read_bytes()
    match = re.search(
        rb"## Deadline accountability\n.*?```json\n(?P<record>.*?)\n```",
        document,
        flags=re.DOTALL,
    )
    assert match is not None, "Sprint 2 deadline-accountability JSON record is required"
    return match.group("record")


def _record() -> dict[str, Any]:
    result = json.loads(_record_bytes())
    assert isinstance(result, dict)
    return cast(dict[str, Any], result)


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_historical_snapshot_bytes_are_immutable() -> None:
    assert hashlib.sha256(_record_bytes()).hexdigest() == (
        EXPECTED_EMBEDDED_RECORD_SHA256
    )
    assert hashlib.sha256(LEDGER.read_bytes()).hexdigest() == EXPECTED_LEDGER_SHA256


def test_deadline_cutoff_is_a_single_explicit_instant() -> None:
    record = _record()

    assert record["historical_timebox"] == {"start": "2026-08-08", "end": "2026-08-14"}
    assert record["deadline_id"] == "sprint-2-owner-cutoff-v1"
    assert record["timezone"] == "Asia/Kolkata"
    assert record["cutoff_local"] == "2026-08-09T22:00:00+05:30"
    assert record["cutoff_utc"] == "2026-08-09T16:30:00Z"
    assert _instant(record["cutoff_local"]) == _instant(record["cutoff_utc"])


def test_original_denominator_is_frozen_and_tracking_additions_are_excluded() -> None:
    record = _record()

    denominator = record["original_denominator"]
    assert denominator == EXPECTED_DENOMINATOR
    assert len(denominator) == 24
    assert len(set(denominator)) == 24
    assert record["original_denominator_count"] == 24

    additions = record["tracking_governance_additions"]
    assert [addition["id"] for addition in additions] == ["ARK-95", "ARK-96", "ARK-97"]
    assert all(
        not addition["included_in_original_denominator"] for addition in additions
    )
    assert not set(denominator).intersection(addition["id"] for addition in additions)


def test_record_preserves_provenance_and_captured_incomplete_snapshot() -> None:
    record = _record()

    assert record["decision_recorded_at_utc"] == "2026-08-08T07:16:18.133Z"
    assert record["decision_recorded_at_source"] == "Linear ARK-97 createdAt"
    assert record["conversation_decision_time"] == "unavailable/unproven"

    required_added_fields = {
        "id",
        "reason",
        "owner_approval_reference",
        "accepted_at",
        "created_at",
        "started_at",
        "completed_at",
        "included_in_original_denominator",
    }
    for addition in record["tracking_governance_additions"]:
        assert required_added_fields <= set(addition)

    snapshot = record["cutoff_snapshot"]
    assert snapshot["status"] == "captured_incomplete"
    assert snapshot["captured_at"] == "2026-08-10T08:25:09+05:30"
    assert snapshot["source_revision"] == "84d681de73e34459a791afbd76af80d04c7e8255"
    assert snapshot["source_timezone"] == "Asia/Kolkata"
    assert set(snapshot) >= {
        "captured_at",
        "completed_baseline_ids",
        "completed_baseline_count",
        "unfinished_baseline_ids",
        "unfinished_baseline_count",
        "observed_state_or_blocker",
        "added_work_rows",
    }
    assert snapshot["completed_baseline_ids"] == EXPECTED_DENOMINATOR[:20]
    assert snapshot["completed_baseline_count"] == 20
    assert snapshot["unfinished_baseline_ids"] == EXPECTED_DENOMINATOR[20:]
    assert snapshot["unfinished_baseline_count"] == 4
    assert snapshot["observed_state_or_blocker"] == {
        "ARK-92": "In Progress; circuit-frozen after ordinary repair budget; no offline collection consumed",
        "ARK-93": "Todo/unstarted; blocked by ARK-92",
        "ARK-69": "Todo/unstarted",
        "ARK-72": "Todo/unstarted",
    }
    assert snapshot["added_work_rows"]["completed_count"] == 13
    assert snapshot["added_work_rows"]["unfinished_count"] == 3
    assert snapshot["added_work_rows"]["unfinished"] == {
        "ARK-106": "Todo/unstarted",
        "ARK-107": "In Progress",
        "ARK-110": "In Progress",
    }
    assert set(snapshot["baseline_partition_rules"]) == {
        "completed_baseline_ids and unfinished_baseline_ids are disjoint",
        "completed_baseline_ids and unfinished_baseline_ids together equal original_denominator",
        "completed_baseline_count + unfinished_baseline_count == original_denominator_count",
    }


def test_cutoff_and_post_cutoff_rules_preserve_evidence_state() -> None:
    record = _record()

    rules = record["completion_classification_rules"]
    assert (
        rules["on_time"]
        == "every required event timestamp is less than or equal to cutoff_utc"
    )
    assert (
        rules["after_cutoff"]
        == "any required event timestamp is greater than cutoff_utc"
    )
    assert (
        rules["unproven"]
        == "missing, date-only, or coarse required timestamps are unproven"
    )
    assert set(rules["required_events"]) == {
        "successful hosted checks",
        "exact-SHA merge/publication",
        "Linear Done synchronization",
    }
    assert "updatedAt" in rules["not_evidence"]
    assert "issue age" in rules["not_evidence"]
    assert "PR age" in rules["not_evidence"]
    assert rules["human_variance"] == "may be rounded; never infer labor-hours"

    ledger = record["post_cutoff_ledger"]
    assert set(ledger) >= {
        "completed_after_ids",
        "carryover",
        "final_completion_at",
        "elapsed_overrun_as_of",
        "final_schedule_variance",
    }
    assert ledger["final_schedule_variance"] is None
    assert ledger["completed_after_ids"] == []
    assert ledger["carryover"] == ["ARK-92", "ARK-93", "ARK-69", "ARK-72"]
    assert ledger["final_completion_at"] is None
    assert ledger["elapsed_overrun_as_of"].startswith("UNSET;")
    assert ledger["final_schedule_variance_rule"] == (
        "null until all 24 baseline tasks have Definition-of-Done evidence"
    )

    assert record["post_cutoff_interpretation"] == (
        "continuing committed work is carryover/schedule overrun; only newly added work is expansion"
    )


def test_ledger_preserves_authoritative_cutoff_evidence_and_unset_honesty() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))

    assert ledger["record_status"] == "POST_CUTOFF_SNAPSHOT"
    assert ledger["snapshot"]["timezone"] == "Asia/Kolkata"
    assert (
        ledger["snapshot"]["repository_revision"]
        == "84d681de73e34459a791afbd76af80d04c7e8255"
    )
    assert ledger["cutoff"]["completed_baseline_ids"] == EXPECTED_DENOMINATOR[:20]
    assert ledger["cutoff"]["unfinished_baseline_ids"] == EXPECTED_DENOMINATOR[20:]

    evidence = ledger["authoritative_cutoff_evidence"]
    rows = {row[0]: row for row in evidence["linear_rows"]}
    assert set(rows) == set(EXPECTED_DENOMINATOR) | {
        *(f"ARK-{issue}" for issue in range(95, 111)),
    }
    assert rows["ARK-92"][-1] == "In Progress"
    assert rows["ARK-92"][-2] == "UNSET"
    assert rows["ARK-93"][-1] == rows["ARK-69"][-1] == rows["ARK-72"][-1] == "Todo"
    assert rows["ARK-106"][-1] == "Todo"
    assert rows["ARK-107"][-1] == rows["ARK-110"][-1] == "In Progress"
    assert evidence["workflow_breakdown"]["active_gate_seconds"] == "UNSET"
    assert evidence["workflow_breakdown"]["owner_or_external_wait_seconds"] == "UNSET"
