# Quota-efficient agent-routing pilot

Status: **accepted pilot**

## Context

After roughly one and a half days of development, the project owner observed
that more than half of the weekly ChatGPT Pro allowance had been consumed. The
largest avoidable pattern was not a missing engineering gate; it was repeated
multi-agent implementation and review passes on partial candidate states.

Current OpenAI guidance states that every subagent performs its own model and
tool work and therefore consumes more tokens than comparable single-agent work.
It positions GPT-5.6 Luna for clear, focused, repeatable, high-volume tasks and
GPT-5.6 Terra for broader production work. The published credit rate is ten
times lower for Luna than Terra for input, cached input, and output tokens as of
this decision; no unsupported intelligence percentage is assumed.

Sources:

- <https://learn.chatgpt.com/docs/agent-configuration/subagents>
- <https://learn.chatgpt.com/docs/models>
- <https://learn.chatgpt.com/docs/pricing>

## Decision

Pilot one persistent Luna High implementation subagent per approved Sprint 1
task. Preserve one repository writer, strict TDD, the full deterministic gate,
independent review, high-risk review, and every existing code-quality and
market-data safeguard. Use one research/analysis subagent by default and no more
than two.

Normal tasks receive one Terra High verifier. High-risk tasks receive one Sol
High reviewer that also performs independent verification, avoiding duplicate
Terra and Sol passes on the same candidate. The same implementer repairs review
findings for at most two rounds. If Luna cannot clear the contract, stop
automatic iteration and transfer the preserved state to Terra or seek owner
direction. Terra is a correctness/design fallback, not a cosmetic refactorer.

## Quality invariants

- A cheaper model never weakens acceptance criteria or the Definition of Done.
- Tests are written before production behavior changes.
- The complete deterministic gate runs before review and completion.
- Reviewers remain read-only and independent from the writer.
- High-risk storage, security, concurrency, provenance, and crash-recovery work
  still requires Sol approval.
- Failed work remains incomplete; quota pressure cannot authorize acceptance.

## Evaluation

Apply the pilot to ARK-35, ARK-36, and ARK-37. At Sprint 1 close, compare
visible subscription usage, reviewer findings, repair rounds, quality-gate
results, elapsed time, and unresolved defects. Record a new decision before
making the routing permanent.

## Accepted correction: ARK-48 routing and scorecard

Status: **accepted**

This correction preserves the pilot intent and all quality invariants above. It
does not rewrite the historical ARK-47 decision.

Unspecified subagents default to Terra Medium with concurrency two. Luna High
is available only through the explicit `luna_implementer` role for an approved,
bounded pilot task. Terra takeover is Terra High. When approval is withheld,
the subagent routes the decision through its parent rather than assuming
authority.

For each candidate, the parent keeps an evidence ledger containing writer
identity, reviewer identity, model-effort, candidate commit and tree, repair
rounds, takeover state, gate evidence, findings, and effective sandbox evidence.
A read-only review records pre/post identical tree and clean scoped status; a
reviewer rejects unexplained mutation or unverifiable read-only isolation.

The scorecard uses ARK-34 only as an available-artifact baseline. Any
unavailable metric or artifact is recorded as unknown. In a fixed 7-calendar-day
post-merge window, it records the identities, model-effort, tree, rounds,
takeover, gates, findings, Linear elapsed time, and linked defects. The
scorecard does not infer token/quota telemetry from routing, model choice, or
elapsed time.

The root coordinator records one scorecard comment on each ARK-35, ARK-36, and
ARK-37 Linear issue. Each comment is the evidence location and includes the
available-artifact baseline, unknowns, spawned-agent count, and the fields
above. Aggregate the scorecards at Sprint 1 close; no token or quota data is
invented when it is unavailable.

Keep only when all gates are unwaived, there is no unresolved blocking review
finding, there is no confirmed linked high-severity defect in each
7-calendar-day post-merge window, and there is usable evidence of cost
improvement. Revise when quality holds but efficiency evidence is unknown or
inconclusive, or takeover/repair behavior shows adjustment is needed. Supersede
if any quality gate is weakened or waived, a blocking finding remains, or a
linked high-severity escaped defect is confirmed.
