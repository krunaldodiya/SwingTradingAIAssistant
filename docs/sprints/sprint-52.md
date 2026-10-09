# Sprint 52: source-bound supported-decision repair

October 9, 2026. [Issue #292](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/292),
Milestone 44, private Delivery Project. Owner and risk owner: Krunal Dodiya.
Risk tier: R3 financial-research provenance, safety gating, and decision policy.
Base: `ee61272f84afe108b4e7101a31ee4d72083e29e8` (`main`).

## Status

The first Sprint 52 implementation was blocked during independent functional
and security/provenance review. It accepted caller-authored JSON and could emit
an actionable result from forged evidence. That unmerged path is retained for
review evidence only.

The active corrective scope is [Plan 66](../plans/66-source-bound-supported-decision-repair.md).
The repaired candidate is under local validation before a new full independent
review. This record does not claim G03 or G04 as closed.

## Delivered boundary under review

`signal-decisions` is being reduced to an offline, read-only retained-observation
workflow:

1. `check-eligibility` accepts only an absolute Sprint 51 storage root and one
   immutable current-structure observation handle. It re-admits producer-owned
   evidence and returns `stock-eligibility@v2` with `UNKNOWN`.
2. `evaluate` accepts the root and two retained handles. It derives causal
   setup facts from those admitted records and returns
   `stock-signal-decision@v2` with `NO_TRADE` and
   `ELIGIBILITY_EVIDENCE_UNAVAILABLE`.
3. Neither command accepts raw JSON facts, bars, mappings, event notices,
   eligibility states, levels, prices, stops, or a caller-supplied known time.
   Neither command can emit `ELIGIBLE` or `ACTIONABLE`.

The result retains evidence that existing sources genuinely establish: canonical
mapping linkage, official completed-session linkage, source-reported OHLCV and
positive observed volume, and producer-known time. It intentionally refuses
listing/tradability, execution-liquidity, price currency/low-price-policy, and
event-risk coverage because no admitted contract establishes them.

## Acceptance for this corrective slice

- Raw caller-authored G03/G04 input and every actionability path are removed.
- The installed CLI accepts only absolute storage roots and observation handles.
- A genuine re-admitted observation produces `UNKNOWN` with the four fixed
  missing-capability reasons and without raw price data.
- A genuinely matching causal pair still produces `NO_TRADE`; all causal facts
  are derived internally and bound to retained handles.
- Malformed, forged, truncated, unavailable, or unadmitted records fail closed.
  The public CLI envelope does not expose storage paths or retained raw data.
- Runtime identity, focused adversarial checks, full independent R3 reviews,
  GitHub-hosted gates, merge, main admission, private publication, and live
  tracker closeout remain required before this sprint can be marked delivered.

## Explicit boundary and follow-on

G03 and G04 remain open outcome gaps. This slice proves a safe decision boundary
on exact retained evidence; it does not clear a stock for trading or generate a
swing recommendation. Any follow-on that adds `ELIGIBLE` or `ACTIONABLE` must
separately source, admit, and govern the missing capabilities before reuse of
these retained facts.

Evidence, including the blocked review reports and the corrective candidate
receipts, is retained under
`/home/krunaldodiya/Documents/Codex/2026-10-08/sprint52-evidence`.
