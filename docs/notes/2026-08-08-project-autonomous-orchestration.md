# Project autonomous orchestration

Date: 2026-08-08
Status: accepted

## Context

The project needs faster, evidence-led delivery without granting an agent broad
or indefinite authority. Earlier graph-lite and spec-driven notes correctly
identified explicit state, durable handoffs, and specification discipline, but
left inventory contradictions about the root coordinator's mutating role and
publication lifecycle. ARK-95 resolves those process controls only.

## Value

The owner and root remain a responsive product/conversation layer: they can
receive, brainstorm, validate, synthesize, freeze a finite Goal authority
envelope, route committed Ready children, interrupt or reprioritize, and judge
evidence. The role split makes a candidate's writer, independent reviewer, and
publisher separately accountable, while completion events reactivate the root
without polling or a blocking wait.

## Accepted operating model

- Only an already-committed unblocked Ready child inside the active accepted
  finite Goal is executable. Same-Goal continuation is allowed; proposed,
  Backlog, and cross-sprint work are not executable.
- Terra implementer is the sole content writer and creates the exact candidate
  commit under strict TDD. Lead architect and reviewers are read-only and do
  not publish. Normal tasks have one Terra verification; high-risk tasks have
  one independent Sol review that also verifies.
- Delivery publisher is the sole external mutation actor for one execution
  epoch. It may checkpoint, perform scoped Linear work, push the handed-off
  SHA, create/update the PR, monitor CI asynchronously, merge only the exact
  independently approved SHA, verify hosted publication, and complete scoped
  Linear synchronization.
- A changed tree, conflict, stale SHA, missing approval, CI failure, or missing
  hosted-publication proof returns to root. Owner interruption enters quiescing
  and requires stop proof before a successor begins. The repair budget and the
  two-like-failure circuit breaker remain mandatory.
- ARK-69 stays owner-specific because its live provider/credential action is
  not part of standing delivery authority.

## Alternatives

- Retain a root that writes, tests, publishes, and waits: rejected because it
  combines product judgment with mutation and can block responsiveness.
- Permit each implementer to publish its own result: rejected because it
  collapses writer, gate, and publication accountability.
- Install a workflow runtime or persistent agent service: deferred. Existing
  Goal, Git, completion-event, and scoped publisher evidence are sufficient;
  a framework needs separate evidence, security, hosting, and maintenance
  approval.

## Cost and limits

The split adds an explicit publisher handoff and exact-SHA checks. It does not
add a provider integration, background worker, dependency, credential, polling
loop, or external state store. The root's authority is deliberately bounded:
it cannot infer a new Goal, waive a gate, self-review, or mutate repository,
Linear, hosting, or provider state.

## Failure and revocation

Publisher stops rather than repairs on conflict, changed tree, stale handoff,
missing approval, failed CI, or failed hosted verification. It returns the
evidence to root for routing. Owner revocation or interruption quiesces the
epoch; no successor acts until stop proof identifies the active actor, exact
state, and safe next action. Two materially identical review rejections or gate
failures still open the circuit breaker and route the incomplete work to Sol.

## Supersessions

This accepted note supersedes the root-as-mutating-coordinator assumptions in
[the 2026-08-07 graph engineering assessment](2026-08-07-graph-engineering-workflow-assessment.md)
and the proposed workflow-only pilot in [the 2026-08-08 spec-driven development
assessment](2026-08-08-spec-driven-development-workflow-assessment.md). The
authoritative implementation is [the development workflow](../development-workflow.md),
the role configuration under `.codex/agents/`, and the handoff template; this
note does not change the market-data architecture or product roadmap.

## Autonomous-delivery boundary

This is not autonomous trading. It never authorizes an order, investment
decision, broker session, provider credential, market-data request, or market
fact. The product remains a deterministic Nifty 50 equity swing-research tool
with the owner retaining the stated market and live-authority decisions.
