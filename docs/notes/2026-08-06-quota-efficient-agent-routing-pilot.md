# Quota-efficient agent-routing pilot (historical)

Status: **superseded by ARK-63 quality-first routing**

## Supersession

This note preserves historical pilot evidence only; it does not select an
active implementation writer. The authoritative current routing is Terra High
as the sole implementation and repair writer. Luna is limited to explicitly
delegated low-risk, read-only documentation or inventory support. See the
[development workflow](../development-workflow.md) and the Sprint 1
[reconciliation note](2026-08-07-sprint1-workflow-reconciliation.md).

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

## Historical pilot decision

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

## Historical evaluation plan

The pilot intended to cover ARK-35, ARK-36, and ARK-37 and to compare visible
subscription usage, reviewer findings, repair rounds, quality-gate results,
elapsed time, and unresolved defects at Sprint 1 close. This paragraph records
the historical evaluation plan; it does not select current routing.

## Closure outcome

Sprint 1 closed at 21/21 executable items. Reliable token or cache telemetry
was unavailable, so the project does not claim a measured token saving from the
Luna implementation pilot. ARK-63 replaced the pilot with the quality-first
Terra/Sol routing recorded in the authoritative development workflow. No open
scorecard or future-tense Sprint 1 close action from this historical note can
reopen the sprint or select an implementation model.

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

The historical plan asked the root coordinator to record one scorecard comment
on each ARK-35, ARK-36, and ARK-37 Linear issue, including available evidence,
unknowns, spawned-agent count, and the fields above. The sprint-close outcome is
the supersession recorded above; no token or quota data is invented where it is
unavailable.

The historical decision rule was to keep the pilot only when all gates remained
unwaived, no blocking review finding or confirmed linked high-severity defect
remained, and usable cost-improvement evidence existed. Unknown efficiency or
extra takeover/repair would require revision; a weakened gate, unresolved
finding, or escaped high-severity defect would require supersession. ARK-63 has
already supplied that supersession.

## Accepted adjustment: deterministic specification compatibility matrix

Status: **accepted**

ARK-49 showed that a broad, high-risk specification can consume repair rounds
when a formal reviewer finds contract mismatches that a deterministic comparison
could have found before review. Before the one formal Sol High review of such a
specification, the coordinator now completes a matrix against the exact
candidate commit. It checks each touched frozen contract, physical identity,
lifecycle transition, exhaustive typed outcome, provenance retention, bounded
resource/wait rule, crash/concurrency ownership, and atomic child boundary. It
also enumerates before/during/between/after cancellation and other stateful
boundaries, and proves each required read/write/query has an available existing
callable contract or is isolated as an approved atomic child.

This adds no subagent, reviewer, or model pass. It is coordinator preparation
only: incompatible rows return to the one writer before review. The sole writer,
strict TDD, deterministic gate, one final OS-enforced Sol High review, and all
quality standards remain unchanged. This adjustment follows the practical
guidance behind the pilot: use the lowest sufficient routing and avoid parallel
write/review coordination cost without accepting weaker evidence.

The owner later approved one narrow ARK-49 correction for boundary-state and
identical-schedule-evidence precision, followed by one OS-enforced Sol High
recheck of that exact corrected candidate. It does not reopen automatic repair
rounds or add a reviewer/model pass.
