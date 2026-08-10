# Conversation decision capture audit

Date: 2026-08-10
Status: accepted documentation inventory; open items remain non-commitments

## Context

The owner requested confirmation that important conversation outcomes are
durably captured rather than left only in chat. This audit checks the material
product, workflow, sprint, and research decisions discussed through Sprint 2.
It is a traceability map, not a duplicate specification or conversation
transcript.

## Existing durable capture

| Durable topic | Status | Authoritative or primary record |
| --- | --- | --- |
| Owner supplies vision and feedback; agents translate it into bounded evidence-led delivery | accepted | [`AGENTS.md`](../../AGENTS.md) owner/delivery boundary and [`development-workflow.md`](../development-workflow.md) |
| General conversation is answered directly; delivery workflow starts only after explicit durable promotion | accepted | `AGENTS.md` and `development-workflow.md` conversation/delivery routing |
| One top-level Goal task per Sprint/cohesive outcome; subagents/worktrees serve atomic delegated work | accepted | [Subagents and top-level Codex threads](2026-08-09-subagents-and-top-level-codex-threads.md) |
| Smoke-first validation before an expensive full suite, benchmark, or backtest | accepted | `AGENTS.md`, `development-workflow.md`, and the [Sprint 2 closeout](../sprints/sprint-2-closeout.md) retrospective |
| Prospective ranges, raw lifecycle timestamps, gate duration, repair rounds, and honest `UNSET` evidence | accepted | `development-workflow.md`, [Sprint 2 record](../sprints/sprint-2.md), and its time-accountability ledger |
| Upstox market-data use is separate from per-account portfolio access and any future execution connector | proposed/open architecture hypothesis | [Provider, account, and execution connector separation](2026-08-09-provider-account-and-execution-connector-separation-hypothesis.md) |
| Code-smell/refactoring tools and the Rust reference repository affect workflow only, not product logic | accepted assessment; experiments deferred | [Code-smell and refactoring workflow assessment](2026-08-09-code-smell-and-refactoring-workflow-assessment.md) |
| Nifty 100 expansion and precious-metals hedging are hypotheses, not current scope | open/deferred | [Nifty 100 universe expansion](2026-08-09-nifty-100-universe-expansion-hypothesis.md) and [precious-metals hedge](2026-08-09-precious-metals-equity-hedge-hypothesis.md) |
| Sprint 2 closed honestly with ARK-92/93/69 carryover and Milestone 2 not accepted | accepted historical outcome | [Sprint 2 closeout](../sprints/sprint-2-closeout.md) |

## Gap resolved in this audit

The owner accepted value-aware holding and reprioritization: a difficult,
low-value or low-frequency issue may be paused when no valuable current task
depends on it and a materially higher-value independent Ready task exists. The
authoritative conditions, safety exceptions, checkpoint evidence, and resume
rule are now in `AGENTS.md` and `development-workflow.md`; the rationale also
extends [Project autonomous orchestration](2026-08-08-project-autonomous-orchestration.md).

The owner also asked for usable increments before the whole project is finished.
The workflow now separates one-week Sprint cadence from a target of one coherent
usable vertical slice every two to three completed Sprints. This is a planning
target, not permission to weaken gates or claim trading readiness.

## Important open planning items, not accepted commitments

- Sprint 3 content and capacity remain owned by ARK-106 planning. Sprint 2's
  21/24 result and ARK-111/92/93/69 carryover are inputs, not a silent Sprint 3
  commitment.
- The total number of Sprints for the whole product is only a rough forecast
  until module specifications, evidence, and sustainable throughput exist.
- Research-output, paper-trading, and real-money timing discussed in conversation
  remains provisional. The [roadmap](../roadmap.md) still requires research
  integrity, realistic costs/slippage, out-of-sample and walk-forward evidence,
  traceability, and paper-trading observation before real-money use.
- No conversation authorized autonomous execution, order placement, F&O,
  expanded universe, a benchmark rerun, or live Upstox access.

## Ongoing capture rule

At each material task or Sprint boundary, compare accepted conversation
decisions with authoritative documents and the notes index. Extend the existing
topical record when possible; use a new dated note only for a genuinely new
topic. Preserve hypotheses and rough estimates as `open` or `proposed`, and do
not convert them into requirements merely because they were discussed.
