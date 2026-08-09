# Subagents and top-level Codex threads

Date: 2026-08-09
Status: accepted clarification; no policy change

## Context

This note distinguishes an internal subagent from a user-owned top-level Codex
task or thread. It clarifies the operating model already accepted in the
development workflow; it does not change runtime behavior, tooling,
configuration, architecture, Sprint scope, or publication authority. Current
Sprint 2 work remains in its existing top-level Goal thread.

Duplicate review: `docs/notes/` was searched for subagent, top-level, thread,
fork, resume, archive, and routing material. Existing routing and orchestration
notes govern the writer/reviewer/publisher split, but do not make this explicit
distinction.

## Accepted clarification

An **internal subagent** is a delegated, bounded worker inside the parent
thread's already accepted finite Goal. The parent/root retains product authority,
scope synthesis, routing, and evidence judgment; the subagent receives only its
assigned node and must return evidence to its parent. It does not become a new
user-owned task merely because it has a separate model turn or working context.

A **top-level Codex thread** is a user-owned conversation/session with its own
visible lifecycle. It may contain a Goal and delegated subagents, but it does
not automatically inherit another thread's Goal, authority envelope, active
writer, worktree, exact base, or completion evidence. Similar subject matter is
not sufficient continuity: a formal handoff is required before a new top-level
thread continues approved work.

| Concern | Internal subagent | User-owned top-level thread |
| --- | --- | --- |
| Ownership and authority | Parent delegates a bounded responsibility inside its accepted Goal; the parent retains authority and judgment. | The user owns the conversation; a new Goal, scope, or continuation must be explicitly established. |
| Context and forking | It receives the task context and any selected/forked parent context needed for its assigned node; it should rely on explicit handoff evidence rather than unstated history. | It has an independent conversation lifecycle. A CLI session fork can copy prior interactive-session context, but does not by itself authorize a new Goal or transfer project authority. |
| Goal continuity | Same-Goal delegation is possible only within the parent’s finite authority envelope. | Topic similarity or resuming a session does not prove Goal continuity; a formal authoritative handoff must identify the predecessor, exact state, and next authorized action. |
| Visibility | Parent/coordinator visibility supports routing and evidence handoff; it does not make the subagent an independent owner. | It is separately user-visible as a conversation/session; visibility does not grant repository, Linear, GitHub, or publisher authority. |
| Model and reasoning | The project may configure a default or assign a role/model/reasoning effort for the delegated task. | A separate top-level thread is not inherently more capable, more reliable, or more isolated. Model choice and reasoning effort are explicit configuration or session choices, not a quality guarantee. |
| Filesystem and worktrees | A shared checkout can collide with other writers. A subagent needs an explicitly created isolated worktree and branch when it writes. | A new top-level thread also does not automatically receive filesystem or Git isolation; it needs the same explicit clean-worktree, exact-base, and branch checks. |
| Evidence and handoff | Return the bounded result, files, exact commit/tree/base, gate evidence, risks, and stop state to the parent. | Before continuation, consume a formal handoff carrying the active Goal, authority envelope, predecessor, candidate/tree, scoped status, evidence, and exact next action. |
| External authority | It cannot mutate Linear, GitHub, or publication state unless it is the separately authorized delivery publisher. | A new thread does not widen those permissions; the publisher still needs the exact independently approved candidate and bounded handoff. |
| Collision and stale-main risk | Concurrent writers or an assumed base can create conflicts, overwrite user work, or produce stale evidence. | Separate threads can create the same risks. Verify the exact hosted base and clean isolated worktree rather than relying on thread boundaries. |

## Local capability check

The local `codex-cli 0.146.0` help was inspected read-only on 2026-08-09. It
describes `fork` as starting from a previous interactive session, `resume` as
continuing a saved interactive session, and `archive` as archiving a saved
session by id or name. `exec` is the non-interactive command and has its own
resume subcommand. These are session-lifecycle capabilities, not evidence of
project authority, repository isolation, user ownership, model-quality
improvement, or a new workflow policy. `codex app --help` only describes opening
a workspace path in the Desktop app; it does not establish a top-level-thread
governance contract.

The checked project configuration enables agents, sets a maximum of two
concurrent threads per session, and provides Terra/high defaults. The active
parent permission selection can override those defaults. Neither setting permits
a second repository writer, bypasses the one-executable-WIP rule, or changes the
authoritative writer/reviewer/publisher roles.

## Owner-accepted recommendation

Use one top-level Goal thread per Sprint or other cohesive major outcome. Within
it, use isolated delegated subagents and worktrees for atomic Linear issues. A
new top-level thread is appropriate only for genuinely independent, long-lived
work or at a Sprint boundary, and only after a formal authoritative handoff.

The handoff must preserve the Goal, authority envelope, execution epoch,
predecessor, writer/reviewer/publisher identities, exact base and candidate
commit/tree, scoped worktree status, gate/review evidence, publication state,
remaining repair authority, known collision or stale-main risk, and the one
already authorized next action. It does not permit a thread to self-review,
publish, mutate Linear or GitHub, or infer a new scope.

## Lifecycle and consequences

Resume restores a saved session for conversation continuity; fork creates a
separate interactive-session branch; archive changes saved-session lifecycle.
None of those actions creates a worktree, preserves a clean tree, resolves a
conflict, publishes a candidate, or completes an issue. Exact Git evidence and
the accepted workflow remain authoritative at every transition.

This clarification preserves the single writer and active mutator limits,
strict TDD, deterministic gate, independent review, exact-SHA publication
requirements, and user-controlled product decisions. It adds no runtime/tool or
configuration change and does not move or extend Sprint 2.

## References

- [Development workflow](../development-workflow.md), read 2026-08-09.
- [Project autonomous orchestration](2026-08-08-project-autonomous-orchestration.md), read 2026-08-09.
- [Quota-efficient agent-routing pilot (historical)](2026-08-06-quota-efficient-agent-routing-pilot.md), read 2026-08-09.
- Local read-only capability evidence: `codex --version`, `codex --help`, and
  `codex fork|resume|archive|exec|app --help`, observed 2026-08-09.
- Project agent configuration: [`.codex/config.toml`](../../.codex/config.toml)
  and `.codex/agents/`, read 2026-08-09.
