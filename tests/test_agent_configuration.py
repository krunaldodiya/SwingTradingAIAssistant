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
PUBLISHER_REQUIREMENTS = (
    "worktree/branch/epoch",
    "scoped linear",
    "push exact handed-off sha",
    "pr create/update",
    "async ci monitoring",
    "merge exact independently approved sha",
    "verify hosted publication",
    "final linear sync",
    "never edit/format/test-as-review/create candidate commit/resolve conflicts/"
    "force-push/bypass gates/make scope decisions/use provider credentials/"
    "self-review",
    "tree change/conflict/stale sha/missing approval/ci failure returns to root",
    "one mutating actor and execution epoch",
    "owner interrupt => quiescing and stop proof before successor",
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
    assert "sole implementation and repair worker" in str(terra["description"])

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


def test_lead_architect_enforces_single_writer_and_risk_based_routing() -> None:
    lead_architect = read_toml(AGENTS / "lead-architect.toml")
    assert "risk-based routing" in str(lead_architect["description"]).lower()

    instructions = " ".join(
        str(lead_architect["developer_instructions"]).lower().split()
    )
    for required in (
        "terra high as the sole repository writer",
        "luna may be selected only for explicit low-risk, repeatable, read-only",
        "dynamic session concurrency does not permit a second repository writer",
        "architecture conflicts",
        "security-sensitive changes",
        "failed quality gates",
    ):
        assert required in instructions


def test_ark_95_delivery_publisher_is_the_only_external_mutation_actor() -> None:
    publisher = read_toml(AGENTS / "delivery-publisher.toml")

    assert publisher["name"] == "delivery_publisher"
    assert publisher["model"] == "gpt-5.6-terra"
    assert publisher["model_reasoning_effort"] == "high"
    assert publisher["sandbox_mode"] == "workspace-write"
    assert "sole external mutation" in str(publisher["description"])

    instructions = " ".join(str(publisher["developer_instructions"]).lower().split())
    assert all(requirement in instructions for requirement in PUBLISHER_REQUIREMENTS)


def test_ark_95_publisher_lifecycle_authority_stays_narrow_and_review_isolation_is_external() -> (
    None
):
    publisher = " ".join(
        str(read_toml(AGENTS / "delivery-publisher.toml")["developer_instructions"])
        .lower()
        .split()
    )
    for required in (
        "bounded root handoff",
        "todo/ready/in progress/in review/blocked",
        "material-edge evidence",
        "before implementation or review",
        "one-active-mutator epoch",
        "does not authorize content mutation",
        "push, pr, merge, or final closure requires an exact sha and independent approval",
    ):
        assert required in publisher

    for filename in ("terra-verifier.toml", "high-risk-reviewer.toml"):
        instructions = " ".join(
            str(read_toml(AGENTS / filename)["developer_instructions"]).lower().split()
        )
        assert "does not prove effective isolation" in instructions
        assert "os-enforced read-only" in instructions


def test_cross_provider_target_is_accepted_but_not_falsely_activated() -> None:
    decision = (
        ROOT / "docs" / "notes" / "2026-08-13-cross-provider-model-routing-decision.md"
    ).read_text()
    config = read_toml(ROOT / ".codex" / "config.toml")

    normalized_decision = " ".join(decision.split())
    for required in (
        "Claude Fable 5",
        "Claude Opus 5",
        "GPT-5.6 Sol",
        "20% planning / 55% execution / 25% review",
        "deterministic tools and hosted CI",
        "activation pending provider qualification",
        "Catalogue visibility is not proof of access",
        "separately billed extra usage",
        "three bounded qualification tasks",
        "no task may require more than one material repair cycle",
    ):
        assert required in normalized_decision

    agents = config["agents"]
    assert isinstance(agents, dict)
    assert agents["default_subagent_model"] == "gpt-5.6-terra"
    assert read_toml(AGENTS / "terra-implementer.toml")["model"] == "gpt-5.6-terra"
    assert read_toml(AGENTS / "high-risk-reviewer.toml")["model"] == "gpt-5.6-sol"


def test_subscription_transition_is_dated_but_does_not_grant_commercial_authority() -> (
    None
):
    decision = " ".join(
        (
            ROOT
            / "docs"
            / "notes"
            / "2026-08-13-cross-provider-model-routing-decision.md"
        )
        .read_text()
        .split()
    )
    for required in (
        "USD 200 plan",
        "2026-09-04",
        "downgrade GPT to the USD 100 plan",
        "purchase the USD 100 Anthropic plan",
        "owner-supplied planning facts",
        "does not authorize the agent to purchase, cancel, downgrade, renew",
        "does not activate cross-provider routing automatically",
        "separately billed extra usage",
        "retain the GPT-only fallback",
    ):
        assert required in decision
