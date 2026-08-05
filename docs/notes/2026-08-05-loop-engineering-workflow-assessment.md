# Loop engineering workflow assessment

Date: 2026-08-05
Status: accepted

## Context

The project owner asked whether Developers Digest's *Definitive Guide to Loop
Engineering in Claude Code and Codex* could improve this repository's
development workflow. The article distinguishes a finite goal (work until a
verified condition is true), a watched loop (repeat while a person is present),
and an unattended routine (scheduled work). It emphasizes bounded execution,
independent verification, durable state, and explicit stop conditions.

Current official Codex guidance confirms the relevant product concepts: Goal
mode accepts an outcome, constraints, and verification criteria; thread
automations provide scheduled continuity; subagents are useful for independent
work but consume additional tokens; and worktrees isolate independent changes.

## Assessment

### Accepted controls

- Atomic Linear tasks already act as verifiable goals with acceptance criteria,
  strict TDD, deterministic quality gates, and independent review.
- The root execution coordinator policy is accepted. For each active execution
  window, the project owner predesignates exactly one root coordinator: heartbeat
  target thread or active user-invoked Goal, never both. It owns one executable
  WIP, routing, integration, completion judgment, and all Linear mutations and
  other authorized project-state writes.
- Implementers, reviewers, and publishers return handoff evidence and do not
  mutate Linear. Repository writes are serial: the coordinator writes its
  authorized scope or delegates one exact file/worktree scope to one implementer.
  All write scopes, including non-overlapping scopes, are serialized. During
  delegation or any repository write, parallel agents are repository read-only;
  reviewers always are.
- Separate-worktree publishing starts only after implementer stop and a handoff
  names publisher, source revision, target worktree/branch, and operation. The
  publisher is sole repository writer until stop and handback.
- Coordinator transfer/recovery needs project-owner approval and proof the prior
  coordinator stopped: its heartbeat paused/stopped or Goal/task completed,
  canceled, interrupted, or terminated. It also needs proof that every delegated
  repository implementer and publisher from that execution window stopped,
  completed, or was explicitly terminated. If the stop or termination of any
  coordinator or delegated repository writer cannot be proven, every repository
  actor remains read-only and the issue is blocked. The recovery audit records
  prior/new coordinator, approval reference, coordinator and delegated-writer
  stop/termination evidence, time, issue state, and repository revision.
  Transfer changes ownership only; all existing gates, approvals, TDD,
  verification, circuit-breaker, and Sol review remain mandatory.
- Each executable task records its completion predicate (outcome, constraints,
  verification, stop condition) and task-appropriate iteration budget in Linear
  or active Goal/task state before the first implementation change. Amendments
  retain the original plus every reason, author, approver, and approval
  reference. Scope/predicate changes require project-owner approval. Budget
  extension/reset needs independent Sol approval, plus project-owner approval
  for a scope/predicate change or new authority; it cannot be silently reset.
  Budget exhaustion leaves the issue incomplete and triggers handoff or escalation; it
  cannot authorize a new writer or completion.
- After two materially identical verifier rejections, or two materially
  identical failures of the same gate component after remediation, a circuit
  breaker stops cosmetic retries and preserves evidence. Expected TDD red tests
  do not count. Route the incomplete issue to Sol; involve the project owner
  only for a genuine owner decision. It cannot waive gates, complete failed work,
  or weaken independent verification/high-risk review.
- Goal mode is for finite, well-specified outcomes; heartbeat is recovery and
  continuity. Handoffs record the predicate, budget, circuit-breaker outcome,
  and existing non-billing observations.

### Superseded proposals

The issue-level lease/bootstrap/forced-release/generation/fencing proposals are
superseded by the accepted root-coordinator policy. No timeout, inferred
staleness, CAS, or automatic recovery mechanism is approved.

Project Slack notifications are superseded by current ChatGPT mobile/desktop
task visibility.

### Rejected or deferred

- Reject generic frequent repository-maintenance loops. Agent-selected cleanup
  violates approved scope and one-item WIP and creates low-value churn.
- Reject arbitrary quality-streak reruns. Repeat testing only for a demonstrated
  flaky or nondeterministic failure with an approved purpose.
- Reject unattended auto-merge/log-fix loops until their inputs, permissions,
  rollback behavior, and human-approval boundaries have approved specifications.
- Reject automatic third-party loop installation. Evaluate provenance,
  permissions, maintenance, and overlap before any installation.
- Reject unlimited review loops; the circuit breaker requires escalation rather
  than repeated unchanged review cycles.
- Treat product-command details in the third-party article as non-authoritative
  and verify them against current official Codex documentation.

## Expected value and validation

These controls are accepted through the authoritative development workflow and
handoff template. Validate them on atomic outcomes using turns, elapsed time,
repeated failures, review findings, rework, final acceptance, and user-visible
subscription quota. Revisit the decision if escalation becomes premature or a
required quality gate is skipped.

## References

- <https://www.developersdigest.tech/blog/loop-engineering-definitive-guide>
- <https://learn.chatgpt.com/docs/long-running-work>
- <https://learn.chatgpt.com/docs/automations>
- <https://learn.chatgpt.com/docs/agent-configuration/subagents>
