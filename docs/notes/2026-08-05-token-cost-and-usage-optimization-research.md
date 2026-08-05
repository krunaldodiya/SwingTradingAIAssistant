# Token cost and usage optimization research

Date: 2026-08-05
Status: accepted (ARK-41 policy); rejected where outside subscription scope

## Context

The project owner asked whether common Codex/Claude usage advice could lower
waste without reducing correctness, research integrity, or delivered outcomes.
ARK-41 narrows the approved result to a Codex **subscription-only** workflow
policy. It does not change the locked research pipeline, market logic, model
configuration, automation, or agent/API boundary.

## Evidence and rationale

The cited videos suggested fresh chats, concise handoffs, focused repository
context, bounded terminal output, routing, API caching/Batch techniques, quota
resets, and upgrades. The current Codex manual supports clear scoped prompts,
concise reusable `AGENTS.md` routing, fresh scheduled runs for independent
work, and parallel agents only for independent tasks; it also notes that each
subagent consumes additional tokens. These support reducing repeated reading,
tool noise, and unnecessary delegation without promising a percentage saving.

The repository already requires atomic issues, strict TDD, bounded output,
role-based routing, and independent review. ARK-41 records the missing
subscription-specific operating details in
[the development workflow](../development-workflow.md) and its linked concise
[handoff template](../templates/codex-subscription-handoff.md).

## Accepted policy

- Start a fresh task only at an atomic issue boundary and carry a concise,
  evidence-bearing handoff; do not interrupt an unresolved TDD cycle for a
  context reset.
- Use targeted `rg`, relevant file sections, focused tests, and bounded tool
  output that retains command, exit status, and concise failure evidence.
- Reuse known relevant guidance rather than rereading whole documents; make
  targeted rereads only after required instructions and specifications are read
  at their current revision. Required full reads and quality gates remain
  mandatory.
- Delegate only independent, non-overlapping, materially useful
  responsibilities; intentionally independent mandatory verification and review
  remain required.
- Compare each accepted atomic outcome with a representative before/after
  sample, visible observation source, and invariant quality gates. Observe turns,
  elapsed time, retries, rework, findings, acceptance, and user-visible quota.

## Rejected or omitted

ARK-41 explicitly excludes ChatGPT/OpenAI API integration, API keys, API
billing/token/cache/reasoning telemetry, API prompt caching, Batch,
persisted-response tactics, quota resets, trials, and upgrades. These either
belong to a different product boundary or change availability rather than
reducing waste per accepted outcome. No savings claim is accepted without
representative, quality-preserving evidence.

## Consequences and open questions

The policy is deliberately observational: user-visible quota is a coarse signal
and cannot establish token or monetary cost. A future external AI/API harness
would require a separately approved, specification-backed issue that assesses
agent-boundary, provenance, security, maintenance, and evaluation impacts.

## References

- Codex manual, local current cache: targeted sections “Best practices”,
  “Multi-agent operations”, “Projects and chats”, “Scheduled tasks”, and
  “Custom instructions with AGENTS.md” (consulted 2026-08-05).
- <https://www.youtube.com/watch?v=Ww3Z_R2KWTk>
- <https://www.youtube.com/watch?v=F-NzvB4WHA0>
- <https://www.youtube.com/watch?v=eA39fIlMiu8>
- <https://www.youtube.com/watch?v=96LqaW9-7GY>
- <https://www.youtube.com/watch?v=qC2ipjdszPA>
