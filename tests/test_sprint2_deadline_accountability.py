"""Contract tests for the Sprint 2 deadline-accountability record."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

SPRINT_RECORD = Path(__file__).parents[1] / "docs" / "sprints" / "sprint-2.md"
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


def _record() -> dict[str, Any]:
    document = SPRINT_RECORD.read_text(encoding="utf-8")
    match = re.search(
        r"## Deadline accountability\n.*?```json\n(?P<record>.*?)\n```",
        document,
        flags=re.DOTALL,
    )
    assert match is not None, "Sprint 2 deadline-accountability JSON record is required"
    result = json.loads(match.group("record"))
    assert isinstance(result, dict)
    return result


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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


def test_record_preserves_provenance_and_pending_snapshot_structure() -> None:
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
    assert snapshot["status"] == "pending_until_cutoff"
    assert set(snapshot) >= {
        "completed_baseline_ids",
        "completed_baseline_count",
        "unfinished_baseline_ids",
        "unfinished_baseline_count",
        "observed_state_or_blocker",
        "added_work_rows",
    }
    assert snapshot["completed_baseline_ids"] is None
    assert snapshot["unfinished_baseline_ids"] is None
    assert snapshot["added_work_rows"] is None


def test_cutoff_and_post_cutoff_rules_preserve_evidence_and_all_gates() -> None:
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
    assert ledger["final_schedule_variance_rule"] == (
        "null until all 24 baseline tasks have Definition-of-Done evidence"
    )

    assert record["post_cutoff_interpretation"] == (
        "continuing committed work is carryover/schedule overrun; only newly added work is expansion"
    )
    assert set(record["deadline_never_waives"]) >= {
        "specification",
        "strict red-green-refactor TDD",
        "deterministic quality gates",
        "independent review",
        "hosted CI/security",
        "exact-SHA merge/publication",
        "ordering/WIP",
        "ARK-69 owner live authority",
        "Sprint Done/closure",
    }
