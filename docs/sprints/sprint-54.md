# Sprint 54: G03 source-and-criteria admission

Live status is owned by [Issue #296](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/296),
Milestone 46, and the private Delivery Project. [Plan 68](../plans/68-g03-source-and-criteria-admission.md)
defines this documentation-only Sprint. Owner and risk owner: Krunal Dodiya.
Risk tier: R3 financial-research provenance and safety-policy design. Base main:
`a826f530e2d9dde7757e7245edbafd3ba90200e2`.

## Goal

Freeze the source-capability and criterion-evidence boundary required before a
later G03 eligibility implementation can make a stock-specific safety decision.
The delivery makes the next source and policy question inspectable without
turning source categories, staged bytes, existing OHLCV, or event-snapshot
absence into a clearance.

## Frozen scope

Plan 68 documents current listing/tradability, price/volume/turnover, existing
event, identity, and owner-staged source capabilities; their source/use/time
limits; the evidence a later listing-duration, execution-liquidity,
price-integrity, or event-risk rule must establish; and the fail-closed handoff.

No market data is acquired. No source, downloader, browser automation,
credential, provider, threshold, policy value, runtime, CLI, test, workflow,
package, source manifest, AI, broker, or Future issue is included. Existing
`UNKNOWN` eligibility and `NO_TRADE` decision behavior remains unchanged.

## Delivery evidence

The exact candidate receives independent R3 functional/domain and
security/privacy/provenance review, direct contract/source inspection, and
`git diff --check`. The Markdown-only path uses the repository's normal PR and
applicable lightweight security check, then exact merge/readback and live
tracker closeout. It does not run or claim the long quality, build,
main-admission, OCI-publication, or market-qualification gates reserved for
runtime changes.

## Explicit later boundary

G03/G04 remain open. A successor must separately adopt and prove any source,
permission/use basis, acquisition method, source/effective/retrieval/known time,
claim-specific criterion, output precedence, and adversarial test matrix before
it can change a stock eligibility or signal result. This Sprint cannot turn an
owner-staged package, source digest, current list row, turnover observation, or
missing event notice into `ELIGIBLE` or `ACTIONABLE`.
