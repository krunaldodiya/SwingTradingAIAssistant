"""Contract checks for the ARK-48 agent-routing pilot configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / ".codex" / "agents"


def read_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as file:
        return tomllib.load(file)


def test_ark_48_routes_default_and_pilot_writers_deterministically() -> None:
    config = read_toml(ROOT / ".codex" / "config.toml")
    agents = config["agents"]
    assert isinstance(agents, dict)
    assert agents["max_concurrent_threads_per_session"] == 2
    assert agents["default_subagent_model"] == "gpt-5.6-terra"
    assert agents["default_subagent_reasoning_effort"] == "medium"

    luna = read_toml(AGENTS / "luna-implementer.toml")
    assert luna["model"] == "gpt-5.6-luna"
    assert luna["model_reasoning_effort"] == "high"
    assert luna["sandbox_mode"] == "workspace-write"
    assert "approved, bounded pilot task" in luna["description"]

    terra = read_toml(AGENTS / "terra-implementer.toml")
    assert terra["model"] == "gpt-5.6-terra"
    assert terra["model_reasoning_effort"] == "high"
    assert terra["sandbox_mode"] == "workspace-write"


def test_ark_48_reviewer_roles_have_read_only_sandbox_contracts() -> None:
    expected_roles = {
        "terra-verifier.toml": ("gpt-5.6-terra", "high"),
        "high-risk-reviewer.toml": ("gpt-5.6-sol", "high"),
        "lead-architect.toml": ("gpt-5.6-sol", "high"),
    }
    for filename, (model, effort) in expected_roles.items():
        role = read_toml(AGENTS / filename)
        assert role["model"] == model
        assert role["model_reasoning_effort"] == effort
        assert role["sandbox_mode"] == "read-only"


def test_ark_48_handoffs_are_traceable_and_read_only_reviews_are_enforced() -> None:
    role_text = "\n".join(
        str(read_toml(AGENTS / name)["developer_instructions"])
        for name in (
            "lead-architect.toml",
            "luna-implementer.toml",
            "terra-implementer.toml",
            "terra-verifier.toml",
            "high-risk-reviewer.toml",
        )
    ).lower()
    for required in (
        "writer identity",
        "reviewer identity",
        "candidate commit",
        "head^{tree}",
        "repair round",
        "gate evidence",
        "effective sandbox",
        "pre/post identical tree",
        "clean scoped status",
    ):
        assert required in role_text

    reviewer_text = "\n".join(
        str(read_toml(AGENTS / name)["developer_instructions"])
        for name in ("terra-verifier.toml", "high-risk-reviewer.toml")
    ).lower()
    assert "reject unexplained mutation" in reviewer_text
    assert "unverifiable read-only isolation" in reviewer_text

    high_risk_reviewer = " ".join(
        str(read_toml(AGENTS / "high-risk-reviewer.toml")["developer_instructions"])
        .lower()
        .split()
    )
    assert "whenever approval is withheld, return findings to the parent" in (
        high_risk_reviewer
    )
    assert "only the parent routes remediation or takeover" in high_risk_reviewer
    assert "otherwise route" not in high_risk_reviewer


def test_ark_48_workflow_and_scorecard_preserve_evidence_limits() -> None:
    workflow = (ROOT / "docs" / "development-workflow.md").read_text().lower()
    assert "exact role selection" in workflow
    assert "evidence ledger" in workflow
    assert "withheld approval" in workflow
    assert "through the parent" in workflow
    assert "| default worker | terra, medium" in workflow
    assert "| pilot implementer | luna, high" in workflow
    assert "explicit, approved, bounded pilot implementation" in workflow
    assert "| fallback/takeover implementer | terra, high" in workflow

    note = " ".join(
        (ROOT / "docs" / "notes" / "2026-08-06-quota-efficient-agent-routing-pilot.md")
        .read_text()
        .lower()
        .split()
    )
    for required in (
        "ark-34",
        "available-artifact baseline",
        "unknown",
        "writer identity",
        "reviewer identity",
        "model-effort",
        "tree",
        "round",
        "takeover",
        "gate",
        "finding",
        "linear elapsed time",
        "linked defect",
        "7-calendar-day post-merge window",
        "does not infer token/quota telemetry",
        "root coordinator records one scorecard comment on each ark-35, ark-36, and ark-37 linear issue",
        "aggregate the scorecards at sprint 1 close",
        "spawned-agent count",
        "keep only when all gates are unwaived",
        "no unresolved blocking review finding",
        "no confirmed linked high-severity defect",
        "usable evidence of cost improvement",
        "revise when quality holds but efficiency evidence is unknown or inconclusive",
        "supersede if any quality gate is weakened or waived",
        "a blocking finding remains",
        "linked high-severity escaped defect is confirmed",
    ):
        assert required in note
