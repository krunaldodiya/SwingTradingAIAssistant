# Development workflow

This workflow is project-scoped. It supports the repository's architecture
freeze and does not change the locked research pipeline or market logic.
Apply the cross-cutting [engineering standards](engineering-standards.md) to
every implementation and review; this workflow defines the issue flow and
quality-gate process.

## Issue flow

Use Linear as the project Kanban when it is connected and authorized. One issue
represents one bounded outcome in the current locked-pipeline module. Move it
through `Backlog` → `Ready` → `In Progress` → `In Review` → `Done`; use
`Blocked` whenever an approval, specification, dependency, or quality gate
prevents progress.

An issue may enter `Ready` only with a linked approved specification containing
purpose, inputs, outputs, deterministic rules, edge cases, validation, and
acceptance criteria. Keep architecture decisions in the authoritative docs and
record durable, non-duplicative discussion outcomes under `docs/notes/` when
required by `AGENTS.md`.

## Agile hierarchy and product backlog

Use this hierarchy consistently in Linear:

| Level | Purpose | Implementation rule |
| --- | --- | --- |
| Project | One durable product or subsystem outcome. | Holds the roadmap, milestones, and backlog. |
| Saga | A large outcome spanning multiple epics and sprints. | Tracking-only; decompose before scheduling. |
| Epic | A coherent capability containing multiple stories. | Tracking-only; never implement directly. |
| Story | One independently valuable, testable user or system behavior. | May enter a sprint only when Ready. |
| Task | One atomic implementation, research, review, or operational action. | One owner, one primary outcome, one focused commit where code changes. |

Apply exactly one `Work Item` child label (`Saga`, `Epic`, `Story`, or `Task`)
to every Linear issue. Use parent/child relationships to express the hierarchy
and explicit blocker links to express ordering. A technical milestone describes
the delivered capability; a sprint describes when committed work is attempted.
Do not substitute one for the other.

The product backlog contains every unscheduled saga, epic, story, and task. Keep
it ordered by value, dependency, risk, and learning value. Backlog refinement
splits oversized work, confirms acceptance criteria, identifies dependencies,
and moves only sufficiently specified stories/tasks to `Ready`/`Todo`. Backlog
items are not implementation commitments.

## Sprint workflow

Use one-week sprints initially, numbered `Sprint 0`, `Sprint 1`, and so on.
Sprint 0 is the retrospective foundation baseline for all work performed before
this rule was adopted. Track sprint scope in Linear with exactly one `Sprint N`
child label until native Linear Cycles are enabled for the team; when Cycles are
enabled, migrate the same assignments to Cycles and retain labels only for
historical reports.

Each sprint has:

1. **Planning:** state one sprint goal, review capacity and dependencies, and
   commit only Ready stories/tasks that fit the timebox and WIP limit.
2. **Execution:** maintain one implementation item In Progress, update blockers
   immediately, and preserve strict red-green-refactor TDD.
3. **Backlog refinement:** prepare future work without silently expanding the
   active sprint.
4. **Review/demo:** verify acceptance evidence and demonstrate the completed
   increment at the end of the sprint.
5. **Retrospective:** record what worked, what did not, corrective actions, and
   any evidence-based change to capacity or process.

Do not add work to an active sprint without explicitly recording why it is an
urgent scope exchange. Incomplete work remains incomplete and is explicitly
carried into a later sprint during planning; never silently change its sprint
label. A sprint closes with a concise record under `docs/sprints/` and a matching
Linear project document or status update.

## Progress reporting

Send a concise user update whenever an executable story or task reaches `Done`,
becomes materially blocked, needs user input, or changes the sprint goal. Use the
current Codex task and the configured Slack DM for completion/blocker updates so
the user can follow progress away from the workstation. Do not send notifications
for individual commands, ordinary red-green iterations, or unchanged status.

Every sprint update reports:

- the sprint goal and executable completion count/percentage;
- stories/tasks completed since the previous update;
- the single active item and its evidence-backed state;
- remaining committed work, blockers, and explicit carryover risk; and
- the latest relevant quality-gate result when code changed.

Calculate progress from executable `Story` and `Task` items only. Exclude
tracking `Saga`/`Epic` items and canceled work from the completion denominator.
Linear remains the live source of truth; repository sprint records are updated
at meaningful milestones and sprint close.

## Atomic incremental delivery

Epics and parent issues are tracking containers only; do not implement them
directly. Every executable child issue must deliver one observable behavior,
have one primary reason to change, fit one red-green-refactor cycle, be
independently verifiable, and be small enough for one focused commit. Its
completion must be expressible in one sentence.

Split an issue before implementation when it contains unrelated behaviors or
changes across unrelated layers, cannot state `Done` in one sentence, uses a
broad list joined by “and,” creates a large review surface, or is expected to be
long-running. Link children to their tracking parent and record blocking or
ordering relationships explicitly; do not rely on issue numbering or prose to
imply dependencies.

The implementation WIP limit is one executable issue. Finish that child's TDD
cycle, relevant test and coverage gates, required review, and `Done` evidence
before starting the next child. A blocked issue moves to `Blocked` and does not
authorize parallel implementation unless the main agent explicitly re-routes
the work while preserving the one-issue limit. Prefer slow, steady, correct
delivery over throughput, batching, or partially completed work.

## Routing and handoff

The main agent owns issue state, scope, integration, and the final result.

| Role | Model and effort | Sandbox | Responsibility |
| --- | --- | --- | --- |
| Default worker | Terra, medium | Workspace write | Bounded implementation work. |
| Implementer | Terra, medium | Workspace write | Strict TDD implementation and evidence handoff. |
| Verifier | Terra, high | Read-only | Independent focused checks. |
| Lead architect/team lead | Sol, high | Read-only | Decomposition, architecture, risk routing, and escalation. |
| High-risk reviewer | Sol, high | Read-only | Independent final review of high-risk or cross-cutting work. |
| Documentation/inventory helper | Luna, low | Read-only | Explicit low-risk, repeatable factual support only. |

Each implementation handoff must state the issue and acceptance criteria,
files changed, tests added first, commands and results, residual risks, and
the exact decision needed next. A reviewer must not review its own change; a
failed review returns to a separate implementer through the main agent.

Project configuration provides these defaults, but an active Codex session's
permission selection is inherited by subagents and can override a custom
agent's sandbox setting.

## Strict TDD

For every behavior change, use red-green-refactor:

1. Add one focused failing test that expresses the approved behavior, including
   a failure or bias case where applicable.
2. Make the smallest implementation change that makes it pass.
3. Refactor only while the relevant tests remain green.
4. Run the relevant suite and any required project-wide checks before handoff.

Do not merge speculative implementation, test-after code, or an unapproved
rule change. A test does not substitute for an approved module specification.

## Quality gates and Sol escalation

Before `Done`, verify scope, approved acceptance criteria, TDD evidence,
relevant tests, deterministic behavior, validation at boundaries, provenance,
and bounded-resource expectations. For market-data work, also check missing or
stale evidence and relevant look-ahead, survivorship, selection, and
data-snooping risks.

Escalate to Sol before implementation or release when requirements are
ambiguous; a change crosses modules; architecture conflicts; market logic,
data contracts, provenance, corporate actions, calendars, or bias controls are
affected; security or credentials are involved; representative performance
regresses; or a Terra verification cannot resolve a material finding. Sol's
high-risk review is independent and is required before closing any such issue.

## Deterministic Python quality gate

Install the locked development tools with `uv sync --extra dev`. Before
handoff, run this single gate from the repository root:

```sh
uv run --extra dev ruff format --check . && uv run --extra dev ruff check . && uv run --extra dev pyright && uv run --extra dev vulture src --min-confidence 80 && uv run --extra dev pytest
```

This is deliberately one small stack: Ruff formats code and checks imports,
correctness, complexity, performance, maintainability, and security patterns;
Pyright strictly checks the production source; Vulture detects confidently dead
production code; and pytest enforces branch coverage. Do not add overlapping
formatters, import sorters, linters, or complexity tools without a demonstrated
gap. The formatter may be run without `--check` only as a mechanical change;
inspect its diff and run the full gate afterwards.

## Current Luna limitation

Luna is not an implementation, architecture, verification, or final-review
role in this workflow. Use it only when the main agent explicitly delegates a
clear, repeatable, read-only documentation or inventory task. If the task
requires judgment, changes, or a quality decision, route it to Terra or Sol.
