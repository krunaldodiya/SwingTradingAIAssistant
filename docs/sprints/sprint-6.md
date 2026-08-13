# Sprint 6 — Market Regime v1 specification

Status: **DELIVERED SPECIFICATION CANDIDATE — ARK-168 RELEASE GATE IN PROGRESS**
Planned window: 2026-08-14 through 2026-08-20
Confidence date for review/CI wait: 2026-08-21
Authoritative planning base: `21cd9f9acbb976e9f29298e0f45dbcdf83167897`

## Goal

Freeze an implementation-ready, deterministic, point-in-time
`nifty50-market-regime@v1` specification for end-of-day Nifty 50 equity swing
research. The specification must define the first locked research module without
claiming an observed regime, implementing a classifier, admitting a new market
source, or weakening missing-evidence outcomes.

The usable increment is an independently reviewed contract and validation handoff
that makes the following implementation sprint unambiguous. Sprint 6 is complete
when the specification can be implemented without inventing labels, formulas,
cutoffs, evidence semantics, or validation rules.

## Proposed-boundary evaluation

- Expected value: define the market-context fact required by every downstream module and move the product beyond foundation plumbing.
- Scope fit: accepted candidate for locked Module 1 and Roadmap Phase 2; Nifty 50 equities, end-of-day facts, and insufficient evidence only.
- Material risk: premature labels, an opaque indicator proxy, current-constituent backdating, raw corporate-action distortion, or the short retained sample could manufacture confidence.
- Smallest alternative: freeze purpose, labels, typed contracts, deterministic baseline candidates, and a falsifiable data/validation protocol without classifier code.
- Decision: **proposed for specification-only Sprint 6; implementation and market-effectiveness claims remain deferred pending owner approval and the frozen handoff.**

## Product decisions proposed for owner approval

1. Sprint 6 is **specification-only**. It does not implement or run a Market
   Regime classifier.
2. Market Regime is an end-of-day descriptive context fact for the existing
   Nifty 50 equity pipeline. It is not a signal, forecast, strategy, opportunity
   score, recommendation, or risk override.
3. Daily official-session facts are the proposed canonical bar-frequency
   boundary. Any regime lookback is context and does not redefine the preferred
   approximately 5–10 trading-session swing horizon or guarantee an exit date.
4. The smallest baseline to evaluate is exact-50 cross-sectional participation
   derived from directly observable, comparable session facts. Lookback,
   thresholds, labels, and corporate-action comparability must be preregistered
   in the specification; none is approved by this planning record.
5. Nifty/index-level or India VIX data is not admitted. A new index, options,
   volatility, macro, or provider source needs a separate source evaluation and
   owner-approved scope change.

## Required specification output

The Sprint 6 contract must complete the nine fields required by the architecture:

1. **Purpose** — the single research question and explicit non-claims.
2. **Business requirements** — Nifty 50-only, end-of-day, post-close, exact-50
   denominator, consumer/tool ownership, and first-class insufficiency.
3. **Inputs** — typed private facts, official-session cutoff, point-in-time
   universe, freshness, corporate-action comparability, source/revision and
   canonical identity requirements; no public raw OHLC.
4. **Outputs** — a closed label set or null label, evidence state, bounded typed
   reasons, contributing identities, calculation/policy versions, and canonical
   report identity; no probability or confidence theatre.
5. **Deterministic rules** — simplest direct-fact baseline, exact ordering and
   threshold boundaries, version-change rules, and no hidden weights or magic
   score.
6. **Edge cases** — missing/late/ambiguous/corrupt evidence, incomplete sessions,
   membership changes, symbol/ISIN mismatch, holidays/special sessions,
   incomparable raw prices, and corporate-action revisions.
7. **Validation** — synthetic contract/property/metamorphic tests plus a
   preregistered future full-history, in-sample/out-of-sample and walk-forward
   protocol. Fixtures may prove mechanics only.
8. **Acceptance** — independent exact-SHA contract review, no-look-ahead and
   survivorship attacks, repository documentation tests, full quality gate,
   hosted CI, and explicit residual blockers.
9. **Implementation handoff** — package/application boundary, dependency order,
   typed fixtures, smallest coding slices, and a stop condition if evidence
   admission cannot be satisfied.

## Candidate baseline to evaluate, not an approved rule

The specification issue may evaluate a pure cross-sectional participation
baseline over two official-session endpoints for all 50 point-in-time members.
Potential observed outputs are broad advance, broad decline, or mixed
participation; any mandatory evidence gap yields `INSUFFICIENT_EVIDENCE` and no
label. A 20-session comparison and 30-of-50 boundary are review hypotheses only.
They must be justified against simpler alternatives and preregistered before any
outcome analysis if selected.

The specification must reject partial-denominator success: 49 available members
cannot become an observed 49-name regime. It must also separate descriptive
participation from stock trend, swing structure, sector analysis, volatility,
liquidity, volume, relative strength, risk validation, and recommendations owned
by later modules.

## Data-readiness truth

The retained Sprint 4/5 evidence cannot validate or honestly produce an observed
Market Regime result:

- it covers only 31 official sessions from 2026-07-01 through 2026-08-12;
- the retained universe was retrieved on 2026-08-12 and cannot prove earlier
  historical membership;
- all 1,550 Sprint 4 stock/session pairs remain insufficient;
- corporate-action status, negative completeness, and revision semantics are
  unproven; and
- prices are raw, while adjusted-price and historical symbol-change authority
  are unsupported.

Even if mechanics used a 20-session lookback, the retained window would yield at
most 11 highly overlapping endpoints in one short period. This cannot support a
regime taxonomy, accuracy, stability, prediction, strategy, profitability, or
decision-support claim. Synthetic fixtures can validate a future contract but
cannot cure these evidence blockers.

## Delivery sequence and WIP

Exactly one issue may be `In Progress`. All issues are forecast at one point and
no more than one working day. No stretch work is committed.

| Order | Planned issue | Outcome | Exit evidence |
| --- | --- | --- | --- |
| 1 | ARK-165 — Approve Market Regime v1 scope and input policy | Freeze purpose, proposed labels, daily cutoff, factor/source evaluations, insufficiency and non-claims | Owner-approved decision record; no code |
| 2 | ARK-166 — Freeze `nifty50-market-regime@v1` fact contract | Complete request/output/provenance/identity/rule/edge-case contract and executable documentation tests | Independent contract review candidate |
| 3 | ARK-167 — Preregister validation and data-readiness protocol | Freeze synthetic tests, bias attacks, future historical partitions/metrics, data gate, and implementation handoff | Reproducible validation matrix; blockers explicit |
| 4 | ARK-168 — Publish the reviewed Sprint 6 specification | Exact-SHA independent approval, full gate, PR, hosted CI, merge and sprint actuals | One merged specification increment |

If Issue 1 cannot freeze a truthful input/source policy, the sprint stops with a
reviewed blocked decision package. It must not substitute conventional indicators,
a new data source, a smaller denominator, or invented evidence.

## Milestones

- **M7 — Market Regime scope and frozen fact contract:** Issues 1–2; target
  2026-08-17.
- **M8 — Validated implementation handoff:** Issues 3–4; target 2026-08-20,
  confidence date 2026-08-21.

## Validation and release plan

During specification work, use focused documentation/contract tests without
coverage for red-green feedback. Before merge, run the unchanged authoritative
five-tool gate: Ruff format, Ruff lint, strict Pyright, Vulture at 80%, and the
configured full pytest profile. Because this is a published market-logic
contract, require independent exact-SHA adversarial review before the PR is
merged. GitHub owns hosted CI/review/merge evidence; Linear owns issue/milestone
state and actuals.

The review must attack look-ahead, current-constituent backdating, 49-name
success, schedule inference, future revisions, same-close knowledge, raw-price
comparability, indicator smuggling, caller-authored labels, mutable/free-form
public diagnostics, and unsupported performance claims.

## Explicit exclusions

- Market Regime implementation, runtime application, or observed labels;
- provider/API calls, credentials, downloads, acquisition executors, or
  market-data-root mutation;
- Market Regime effectiveness, accuracy, stability, prediction, strategy,
  profitability, opportunity, recommendation, or trade claims;
- Sector Analysis or any later locked module;
- SMA/EMA, Bollinger Bands, RSI, MACD, stochastic, ATR rules, ADX, VIX, opaque
  volatility proxies, hidden weights, or a composite score;
- Nifty Next 50, combined Nifty 100, F&O, indices as a new instrument dataset,
  forex, crypto, portfolio/account connection, or broker execution; and
- ARK-152, ARK-153, and ARK-154, which remain separate debt/direction work.

## Planning approval gate — satisfied

The owner approved the five product decisions in Prime session
`019fec82-f298-7015-840f-541ab4c9a33f` before ARK-165 started. This approval
covered the specification increment only and did not authorize classifier
implementation, new sources, evidence acquisition, portfolios, or orders.

## Delivery evidence and actuals

- ARK-165: `2026-08-13T09:29:56.044Z`–`09:35:08.711Z` (scope/input policy).
- ARK-166: `09:35:11.433Z`–`09:45:42.327Z` in Linear; subsequent adversarial
  remediation was retained through exact approved SHA
  `ac60ca9e6ec623fd36e8a1ab14caf464bd4260b0`.
- ARK-167: `09:45:57.984Z`–`10:09:42.820Z`; independently approved at exact SHA
  `c309d452ca831954d9fc44bb396b09e6971fcec1`.
- ARK-168 started at `2026-08-13T10:09:46.655Z`; release/CI/merge actuals are
  recorded after completion.

Rework was concentrated in ARK-166 and was scientifically material rather than
cosmetic: independent review caught an unreachable close-time evidence cutoff,
an unrepresentable insufficiency path, opaque evidence semantics, ambiguous
canonicalization, incomplete cross-bindings, and duplicate schema definitions.
All were corrected before approval. ARK-167 review then separated external
future-data mutation from injected late evidence, bounded Decimal
metamorphisms, and froze exact cutoff boundary tests.

No provider/API call, credential access, download, market-data-root write,
portfolio/account access, order operation, classifier implementation, runtime
classification, observed label, or effectiveness claim occurred.
