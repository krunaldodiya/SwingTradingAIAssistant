"""Contract checks for the active quality-first agent configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / ".codex" / "agents"
REVIEWER_REQUIREMENTS = (
    "candidate commit",
    "head^{tree}",
    "effective sandbox",
    "pre/post identical tree",
    "clean scoped status",
    "reject unexplained mutation",
    "unverifiable read-only isolation",
)


def read_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as file:
        return tomllib.load(file)


def missing_reviewer_requirements(instructions: str) -> set[str]:
    normalized_instructions = " ".join(instructions.lower().split())
    return {
        requirement
        for requirement in REVIEWER_REQUIREMENTS
        if requirement not in normalized_instructions
    }


def test_reviewer_contract_checker_rejects_missing_safeguards() -> None:
    incomplete_reviewer = "candidate commit; HEAD^{tree}; effective sandbox"
    assert missing_reviewer_requirements(incomplete_reviewer) == {
        "pre/post identical tree",
        "clean scoped status",
        "reject unexplained mutation",
        "unverifiable read-only isolation",
    }


def test_each_reviewer_independently_enforces_read_only_safeguards() -> None:
    for filename in ("terra-verifier.toml", "high-risk-reviewer.toml"):
        instructions = str(read_toml(AGENTS / filename)["developer_instructions"])
        assert missing_reviewer_requirements(instructions) == set()


def test_ark_63_routes_terra_as_the_only_implementation_writer() -> None:
    config = read_toml(ROOT / ".codex" / "config.toml")
    agents = config["agents"]
    assert isinstance(agents, dict)
    assert agents["max_concurrent_threads_per_session"] == 2
    assert agents["default_subagent_model"] == "gpt-5.6-terra"
    assert agents["default_subagent_reasoning_effort"] == "high"
    assert not (AGENTS / "luna-implementer.toml").exists()

    terra = read_toml(AGENTS / "terra-implementer.toml")
    assert terra["model"] == "gpt-5.6-terra"
    assert terra["model_reasoning_effort"] == "high"
    assert terra["sandbox_mode"] == "workspace-write"
    assert "sole implementation and repair worker" in terra["description"]

    luna = read_toml(AGENTS / "luna-docs-inventory.toml")
    assert luna["model"] == "gpt-5.6-luna"
    assert luna["model_reasoning_effort"] == "low"
    assert luna["sandbox_mode"] == "read-only"


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
    ):
        assert required in role_text

    high_risk_reviewer = " ".join(
        str(read_toml(AGENTS / "high-risk-reviewer.toml")["developer_instructions"])
        .lower()
        .split()
    )
    assert "whenever approval is withheld, return findings to the parent" in (
        high_risk_reviewer
    )
    assert "only the parent routes remediation to the same terra task implementer" in (
        high_risk_reviewer
    )
    assert "otherwise route" not in high_risk_reviewer


def test_ark_63_workflow_supersedes_the_luna_implementation_pilot() -> None:
    workflow = (ROOT / "docs" / "development-workflow.md").read_text().lower()
    assert "evidence ledger" in workflow
    assert "approval is withheld" in workflow
    assert "through the parent" in workflow
    assert "| default worker | terra, high" in workflow
    assert "terra high is the sole implementation and repair writer" in workflow
    assert "luna is limited to explicitly delegated, low-risk, read-only" in workflow

    note = " ".join(
        (ROOT / "docs" / "notes" / "2026-08-06-quota-efficient-agent-routing-pilot.md")
        .read_text()
        .lower()
        .split()
    )
    for required in (
        "superseded by ark-63 quality-first routing",
        "historical pilot evidence only",
        "terra high as the sole implementation and repair writer",
        "luna is limited to explicitly delegated low-risk, read-only",
    ):
        assert required in note
