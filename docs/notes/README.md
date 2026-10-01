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

**Status: selected-source reconciliation in progress, 2026-10-01.**
[#234](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/234) retains
private source-integrity, disposition and conflict evidence for the September 25
backup. Prior passes report full-text reads of 145 of 1,327 documents, 956 of
14,208 memory units and all eight current mental models. These are read-coverage
counts, not proof that every claim is reconciled: one large document still has
a pending claim crosswalk. Follow-up of the first decision pass's 13 unresolved
rows resolved nine historical findings, retained two duplicate rows as one open
SDK exception-boundary question and kept historical #198 tracker lineage open;
the capture-timing correction was verified without granting current operational
authority. These are evidence dispositions, not fresh runtime test results.
The remaining 1,182 documents and
13,252 memory units have no complete semantic disposition; inventory, hashes
and keyword screening cannot supply one. History and graph records have no
blanket semantic-review claim. No complete migration or independence from the
unreviewed recovery source is claimed.

The dated additions below retain selected missing rationale and supersession
links. Recovered harness, model, tracker and provider instructions do not replace
the [canonical adapter](../mandatory-agent-instructions.md), accepted Plans or
live GitHub. In particular, old “Sprint 28 unapproved” audit text predates Plans
42/43 and closed Issues #235/#237. Current delivery authority wins; the original
source and historical notes remain unchanged except for explicit dated overlays.

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
