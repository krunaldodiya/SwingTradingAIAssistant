# Spec-driven development workflow assessment

Date: 2026-08-08
Status: superseded

Superseded by [2026-08-08 project autonomous orchestration](2026-08-08-project-autonomous-orchestration.md).
Its reference assessment remains useful historical research, but the proposed
pilot is replaced by the accepted finite-Goal, writer/reviewer/publisher model.

## Context

The project already requires an approved module specification before code,
strict red-green-refactor TDD, atomic Linear work, one executable WIP, one
repository writer, independent risk-based review, deterministic quality gates,
and exact-revision graph-lite checkpoints.  Nine external references were
reviewed to determine whether a spec-driven development (SDD) tool or practice
could improve delivery speed and autonomy without duplicating the source of
truth or weakening the frozen market-data architecture.

## Source validation

| Supplied reference | Reliability and disposition |
| --- | --- |
| `cameronsjo/spec-compare` | Useful secondary research and discovery index, with cited sources and an MIT license.  It is not authoritative for the compared tools, and its own matrix flags stale versions.  Validate every adopted claim against the tool's current official repository. |
| Jettro Coenradie's Codex + Backlog.md article | Useful personal case study.  The official Backlog.md repository confirms Markdown tasks, acceptance criteria, dependencies, local-first operation, Codex integration, and the spec/plan/code review loop.  The author's two-hour result is anecdotal, not productivity evidence. |
| Marcos's practical Codex article | Useful secondary account of common failure modes: vague specifications, missing acceptance criteria, invented requirements, and spec/code drift.  Its prescribed architecture, coverage target, and claim that manual code edits break SDD are opinions, not general requirements. |
| Reddit `codex-spec` launch post | Community announcement only.  The linked repository confirms the workflow, but it is a small prototype with four commits, no releases, default workspace-write execution, an API-key requirement, and inconsistent license presentation between README and repository metadata.  Do not install it here. |
| Hashnode discussion link | The supplied page exposes no substantive article or verifiable technical evidence.  Ignore it. |
| LinkedIn post | The supplied page did not expose a stable, attributable post body and returned unrelated feed content.  Ignore it. |
| Martin Fowler site article | Credible practitioner analysis, but still experiential rather than an official tool contract.  Retain its cautions: SDD is not one method, tool fit depends on problem size and clarity, and spec-as-source can combine model-driven-development rigidity with LLM non-determinism. |
| CodeSignal course | The official course page validates only its curriculum: when specs are valuable, ambiguity analysis, constitutions, persistent PRDs, critical review, and task decomposition.  It provides no evidence that a particular workflow improves this repository. |
| GitHub Spec Kit launch article | Primary historical source for GitHub's Spec Kit intent.  Its 2025 command examples are superseded by the current official repository, which now defines the `speckit.constitution` -> `speckit.specify` -> `speckit.plan` -> `speckit.tasks` -> `speckit.implement` flow plus optional clarify, checklist, and cross-artifact analysis commands. |

## Findings

The project already implements the high-value SDD core:

- durable governing principles in `AGENTS.md` and the architecture freeze;
- separate intent/specification, technical plan, atomic tasks, implementation,
  verification, and publication phases;
- acceptance criteria, typed failures, dependency order, security boundaries,
  and explicit stop conditions;
- Linear as the single issue/Kanban system instead of a second Markdown task
  database;
- exact candidate revisions, tests, independent review, CI, and merge evidence;
  and
- isolated worktrees plus graph-lite checkpoint/resume control.

Full adoption of Spec Kit would add a second set of constitutions, specs, plans,
tasks, commands, and generated directories around an already mature brownfield
workflow.  Backlog.md would duplicate Linear and create reconciliation risk.
`codex-spec` adds an unnecessary API-key and execution surface.  None currently
offers enough incremental value to justify migration, dependency, security,
training, and maintenance cost.

Three lightweight practices can add value without adopting a framework:

1. **Stable traceability IDs.** Give every executable acceptance criterion a
   stable ID and require a direct mapping from spec criterion to Linear child,
   failing test, implementation evidence, and PR/merge evidence.
2. **Cross-artifact consistency analysis.** Before implementation and again
   before review, check spec, plan, tasks, tests, and issue dependencies for
   missing coverage, contradictions, stale paths, and orphaned requirements.
   This borrows the useful intent of Spec Kit's analysis/checklist commands
   without installing or generating a parallel workflow.
3. **Standing task authorization.** Moving an approved bounded task to Ready
   should authorize its safe normal lifecycle: implementation, reviewer-directed
   in-scope repairs, gates, commits, Linear checkpoints, PR publication, merge,
   and verification.  Owner interruption is reserved for scope/architecture or
   product decisions, live provider/credential use, destructive or
   non-recoverable action, coordinator transfer, security/licensing exceptions,
   and the mandatory repeated-failure circuit breaker.  A per-repair owner
   approval is not the default.

## Recommendation

Accepted finding: the repository is already spec-driven and should remain
tool-agnostic.

Rejected for the current workflow: installing Backlog.md, `codex-spec`, or the
full Spec Kit workflow; replacing Linear; treating generated specs as a code
generator; or adding a second task/source-of-truth hierarchy.

Proposed for Sprint 2 planning: a small workflow-only pilot covering the three
practices above.  Measure owner interruptions per task, review-repair rounds,
spec-drift findings, repeated gates on unchanged revisions, context-restart
time, and issue-to-merge elapsed time over two or three atomic tasks.  Retain a
practice only if it reduces rework or owner waiting without weakening the
existing gates.

## References

- [Spec-compare research repository](https://github.com/cameronsjo/spec-compare)
- [Backlog.md official repository](https://github.com/MrLesk/Backlog.md)
- [Codex-spec official repository](https://github.com/shenli/codex-spec)
- [GitHub Spec Kit official repository](https://github.com/github/spec-kit)
- [GitHub Spec Kit documentation](https://github.github.com/spec-kit/)
- [GitHub's Spec Kit launch article](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)
- [Understanding SDD: Kiro, spec-kit, and Tessl](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html)
- [CodeSignal SDD with Codex course overview](https://codesignal.com/learn/courses/foundations-of-spec-driven-development-with-codex)
- [Jettro Coenradie's Codex + Backlog.md case study](https://jettro.dev/spec-driven-development-using-codex-and-backlog-md-1de89cd229d5)
- [Marcos's Codex SDD case study](https://mmarcosab.medium.com/a-practical-path-to-spec-driven-development-with-codex-a3cec3ef554a)
- [Reddit codex-spec launch post](https://www.reddit.com/r/OpenaiCodex/comments/1nf7v9j/codexspec_specificationdriven_development_tool/)
