# Project Notes

This directory preserves useful reasoning from project discussions without
turning chat transcripts into documentation.

Notes may contain proposed ideas, alternatives, assumptions, research findings,
rejected approaches, and open questions. They are not automatically approved
requirements. Every note must label the status of its important conclusions.

Use the following structure when practical:

```text
# Topic

Date:
Status:

## Context
## Durable insights
## Decisions and rationale
## Open questions
## Consequences / next steps
## References
```

Status vocabulary:

- `proposed`: worth exploring, not approved;
- `open`: unresolved question or trade-off;
- `accepted`: approved and reflected in the relevant source of truth;
- `rejected`: considered and intentionally not selected; and
- `superseded`: replaced by a later note or decision.

Authoritative scope and architecture still live in
`docs/architecture-freeze-v1.md`, approved module specifications, and executable
plans under `docs/plans/`. When a discussion changes an approved direction,
update those documents as well as the note.

## Recovered-context reconciliation

**Status: recovered-knowledge reconciliation prepared, 2026-10-01; delivery
tracked in [#234](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/234).**
Private source-integrity and per-record disposition evidence covers semantic
reading of all 14,208 recovered memory units and all eight current mental models.
There are attributed complete reads of 164 of 1,327 original source documents,
plus selected excerpts used to corroborate consequential claims. Sensitive
values were excluded from relevant reading displays and from these notes.

Useful missing rationale is retained below; other records are already covered
by current or version-scoped contracts, superseded, historical, or transient.
“Covered” includes explicitly documented proposals and open questions; it does
not mean implemented, newly validated or resolved. The large conversation's
46-family crosswalk and later corrections preserve actual discussion dates and
owner-retention versus implementation-approval distinctions. Earlier review
findings were checked against later accepted contracts and delivery evidence;
old test counts and approvals are not transferred to current code.

The remaining 1,163 original documents have no attributed whole-document read.
Memory-unit reading does not establish every original conversation's recovery;
history and graph records have no blanket semantic-review claim. Preserve the
backup and private audit evidence. Routine planning should use current project
docs and GitHub, without requiring a Hindsight installation, while historical
source-recovery questions remain bounded by this coverage limit.

One recovered reference to a separate `live_gate` cleanup finding lacks its
actual defect details or resolution. The private conflict register preserves
that lineage question; current code alone proves neither a bug nor closure.
The SDK question below, unrecovered exact fundamentals criteria, paused
correction-attempt lineage and recurring-capture activation remain explicitly
open. This reconciliation does not authorize implementing those items or claim
complete independence from every unreviewed original source.

The dated additions below retain selected missing rationale and supersession
links. Recovered harness, model, tracker and provider instructions do not replace
the [canonical adapter](../mandatory-agent-instructions.md), accepted Plans or
live GitHub. In particular, old “Sprint 28 unapproved” audit text predates Plans
42/43 and closed Issues #235/#237. Current delivery authority wins; the original
source and historical notes remain unchanged except for explicit dated overlays.

**Open diagnostic-boundary question.** Recovered records
`35b85461-9a4e-4647-a97c-f13ab8309498` and
`dcce8f4b-04a4-41b5-9cfa-9938f08c1517` describe the same V2 SDK callback
exception concern. Current `_CancellationClockV2.now()` retains the callback
exception as the cause of its fixed-message `ValueError`; this observation does
not establish a CLI disclosure. The architecture requires caller/operator
sanitization while allowing internal fault propagation, and Plan 36's public
ledger/result privacy rules do not explicitly settle transitive SDK exception
sanitization. Retain that precise contract question rather than asserting a
confirmed Plan 36 violation or claiming the cause was removed. Any selected
code follow-up needs its own governed scope and discriminating reproduction;
the recovery notes authorize no repair or new disclosure exception.

## Notes index

- [2026-09-28 — Project completion map and provisional effort](2026-09-28-project-completion-map.md) — historical estimate, not current delivery status.
- [2026-09-26 — Next sprint readiness: event notices](2026-09-26-next-sprint-readiness.md)
- [2026-09-23 — Completed-session fallback](2026-09-23-swing-completed-session-fallback.md)

- [2026-09-22 — Next research-assistant priorities and Linux handoff](2026-09-22-next-sprint-and-linux-handoff.md)
- [2026-09-21 — Current-workflow efficiency investigation](2026-09-21-current-workflow-efficiency.md)

- [2026-08-10 — ARK-112 disposition and Sprint 3 scope exchange](2026-08-10-ark-112-disposition-and-scope-exchange.md)
- [2026-08-09 — Provider, account, and execution connector separation](2026-08-09-provider-account-and-execution-connector-separation-hypothesis.md)
- [2026-08-04 — Data foundation and agent-tool boundary](2026-08-04-data-foundation-and-agent-tool-boundary.md)
- [2026-08-07 — Indicator minimization](2026-08-07-indicator-minimization.md)
- [2026-08-07 — Research vision, validation, and instrument extensibility](2026-08-07-research-vision-validation-and-instrument-extensibility.md)
- [2026-08-08 — psutil benchmark sampler assessment](2026-08-08-psutil-benchmark-sampler-assessment.md)
- [2026-08-08 — Swing-trading return and loss-exit risk decision](2026-08-08-swing-trading-return-and-loss-exit-risk-decision.md)
- [2026-08-09 — Nifty 100 universe-expansion hypothesis](2026-08-09-nifty-100-universe-expansion-hypothesis.md)
- [2026-08-09 — Precious-metals equity-hedge hypothesis](2026-08-09-precious-metals-equity-hedge-hypothesis.md)

- [Live-first contract preservation crosswalk](2026-09-21-live-first-contract-crosswalk.md) — #172 named-plan dispositions and historical evidence boundaries; parent acceptance remains open.
