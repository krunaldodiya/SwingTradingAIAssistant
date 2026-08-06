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
