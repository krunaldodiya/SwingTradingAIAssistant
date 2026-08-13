# Market Regime v1 Scope and Input Policy

Status: **ARK-165 APPROVED — SCOPE AND INPUT POLICY ONLY**  
Decision: ARK-165  
Contract destination: `nifty50-market-regime@v1`

This record approves the source-policy and scope half of the Market Regime
specification. It is not the frozen fact contract. ARK-166 must resolve and
freeze labels, request/output fields, deterministic ordering, formulas,
thresholds, reason precedence, canonical identity, and edge-case behavior before
implementation may begin.

## Proposed module evaluation

- Expected value: Market Regime supplies one reproducible market-context fact before downstream equity research.
- Scope fit: Market Regime is the first locked module in the existing Nifty 50 pipeline; this activates that boundary and adds no module.
- Material risk: a proxy index, indicator bundle, backdated membership, partial cohort, or incomparable prices could manufacture a regime.
- Smallest alternative: use only direct, verified daily equity facts for the exact point-in-time 50-name cohort and fail closed.
- Decision: **accepted for specification; implementation remains deferred until the complete contract and validation handoff are frozen.**

## Proposed participation-factor evaluation

- Expected value: direct cross-sectional participation answers whether price movement is broadly shared without an opaque score.
- Scope fit: it is an end-of-day descriptive market-context fact, not stock trend, sector analysis, volatility, or a trading signal.
- Material risk: an arbitrary lookback or threshold can overfit a short sample, while a reduced denominator can hide missing evidence.
- Smallest alternative: compare comparable daily equity facts at two official-session endpoints and count all 50 members equally.
- Decision: **accepted as the sole baseline factor family for ARK-166 to specify; no lookback, threshold, or label is approved here.**

## Proposed no-new-source evaluation

- Expected value: no new feed is required to define mechanics that existing, retained, verified equity facts can eventually support.
- Scope fit: direct daily Nifty 50 equity facts preserve the equity-only module and the frozen provider-independent domain boundary.
- Material risk: index, VIX, options, macro, or convenient third-party data would expand authority, licensing, provenance, and bias risk.
- Smallest alternative: consume only admitted point-in-time membership, session, equity-fact, and comparability evidence through existing contracts.
- Decision: **accepted — No new market-data source is admitted by ARK-165; any later source requires a separate evaluation and approval.**

## Purpose and non-claims

Market Regime answers one bounded question: *at a declared completed Nifty
Capital Market session, what does approved deterministic participation logic say
about the breadth of comparable daily price movement among exactly the 50 Nifty
50 equities that were members for that session?*

The result is an end-of-day descriptive market-context fact for the locked
pipeline. It is not a signal, forecast, strategy, opportunity score,
recommendation, or risk override. It neither selects nor ranks an equity, sets
entry/exit or position size, changes a later module's evidence, nor permits the
AI consumer to compute missing market facts. It makes no claim of accuracy,
stability, prediction, profitability, trade timing, future return, or market
safety. `NO_TRADE` and risk decisions remain outside this module; an observed
context never overrides insufficient evidence or hard risk failure.

This policy covers Nifty 50 cash equities only. Intraday classification, index
instruments, derivatives, India VIX, other universes, portfolio advice, and
broker execution remain excluded.

## Daily post-close time boundary

The only approved bar-frequency input is daily official-session equity facts. One
evaluation names one authoritative Nifty Capital Market decision session and
occurs post-close, only after that session's exact authoritative close. Its `knowledge_cutoff` is the exact official-session close
reconstructed from applicable retained NSE schedule bytes; callers cannot supply
an independent convenient timestamp. Running later does not move the cutoff.

Every input must have been publicly available or retained as applicable no later
than the cutoff and must apply to the evaluated session/endpoint. Retrieval,
filesystem, report-generation, replay-wall-clock, HTTP transport, and later
revision times do not establish earlier knowledge. A bar containing activity
after the close, an incomplete/special session treated as standard, or evidence
first known after the cutoff is inadmissible. A post-close report may therefore
remain `INSUFFICIENT_EVIDENCE` when complete cutoff-safe facts were not available
at the close.

The approved frequency does not set a holding period. A historical comparison
window, if later approved, provides context only and does not redefine the
preferred approximately 5–10 trading-session swing horizon.

## Exact point-in-time cohort and denominator

The denominator is exactly 50 unique point-in-time Nifty 50 members, identified
ISIN-first, whose authoritative membership effective interval covers the
specified decision session. The membership artifact and its public-availability
receipt must themselves be known by the cutoff. A current constituent list
cannot supply current constituents for a historical session or prove historical
membership.

Every admitted member contributes exactly one equally weighted observation to a
future participation rule. No substitution, imputation, survivorship filtering,
sector weighting, free-float weighting, duplicate symbol, or caller-selected
cohort is allowed. Missing one member does not produce 49-of-49, 49-of-50, a
rescaled percentage, or any other partial denominator. A cohort other than
exactly 50 valid rows yields `INSUFFICIENT_EVIDENCE` and no observed label.
Membership changes are applied by effective session, not announcement cadence;
ambiguous or unavailable effective membership fails closed.

## Admitted evidence classes, freshness, and authority

ARK-165 admits no raw public candles and no caller-authored market conclusion.
The future deterministic module may consume only typed private facts with source
identity, retrieval/publication time, applicable interval, immutable digest,
revision lineage, and calculation/policy version. The mandatory classes are:

1. **Point-in-time membership evidence.** NSE Indices Limited is the
   authoritative Nifty 50 methodology and reconstitution authority. Retained
   notice/release bytes must prove all 50 ISINs, effective scope, and actual
   availability by cutoff. A current CSV or HTTP `Last-Modified` is not
   historical authority.
2. **Official-session evidence.** NSE is the authoritative exchange authority
   for Capital Market sessions, closures, special sessions, timing changes, and
   corrections. The annual holiday publication is a base only; applicable
   retained overlays must establish exact bounds without unresolved conflict.
3. **Daily equity-fact evidence.** The only admitted price input is the existing
   provider-independent `nse-session-ohlcv@v1` daily fact for each exact member
   and required endpoint: one complete, unique, verified official-session fact
   derived from closed retained evidence. It remains private; the Market Regime
   output must not publish raw OHLC or invite the AI to recompute participation.
4. **Corporate-action comparability evidence.** Each member must have cutoff-safe
   evidence proving that the selected endpoint values are economically
   comparable under an approved policy. Raw observations alone cannot silently
   bridge a split, bonus, rights event, symbol/ISIN discontinuity, or other price
   discontinuity.
5. **Provenance and revision evidence.** Every consumed fact retains source and
   release identity, applicable/effective time, knowledge/retrieval time, digest,
   upstream calculation version, and supersession lineage. A later correction
   creates new replay evidence and never rewrites what was knowable at cutoff.

Freshness is semantic rather than an invented maximum-age duration. Membership,
schedule, and corporate-action evidence must cover the relevant session or
comparison interval; the current daily fact must be for the exact decision
session; a comparison fact must be for the exact earlier official-session
endpoint ARK-166 eventually selects. Evidence that is missing, late, stale for
its effective scope, ambiguous, corrupt, incomplete, conflicting, or from an
unapproved authority is insufficient.

## Corporate-action comparability policy

Participation is not permitted to treat an unadjusted mechanical price jump as
market breadth. The future contract must choose one explicit, versioned path per
member: either authoritative cutoff-safe evidence proves no relevant
comparability-breaking event across the comparison interval, or a separately
approved comparable-price fact and exact adjustment authority/formula is
available. Mixing paths or silently calculating adjustments is forbidden.

Plan 09 Upstox corporate-action observations remain discovery evidence, not
exchange/company action-status authority and not negative-completeness proof.
An empty response does not prove absence. Current evidence also lacks adjusted
OHLC and historical symbol-change authority. Thus missing authoritative positive
status, negative completeness, revision lineage, terms, or adjustment authority
requires `INSUFFICIENT_EVIDENCE`; raw prices remain raw and immutable.

## Rejected inputs and shortcuts

ARK-165 rejects conventional technical-indicator proxies or combinations: SMA,
EMA, Bollinger Bands, RSI, MACD, stochastic, ATR, and ADX. It also rejects hidden
weights, composite or confidence scores, opaque volatility proxies, inferred
market structure, volume or liquidity factors, relative strength, sector
breadth, and caller-supplied labels. Those either duplicate direct evidence or
belong to later locked modules.

No index-level price series, Nifty 50 index candle, India VIX/options series,
macro source, new provider, web scrape, built-in calendar, or external sentiment
feed is admitted. Availability or convenience is not authority or licence.
Neither an index proxy nor a smaller available stock cohort may replace the
exact point-in-time 50-equity participation question.

## Insufficiency and data-readiness truth

`INSUFFICIENT_EVIDENCE` is a successful, first-class descriptive outcome with no
observed regime label. It is mandatory for an invalid cohort; a missing, late,
stale, ambiguous, corrupt, conflicting, incomplete, incomparable, or
unauthorized mandatory fact; unresolved cutoff/authority/licence/revision
status; or inability to establish exact membership, session, or corporate-action
comparability. No confidence score, best effort, inferred value, previous label,
or partial denominator may convert it into an observed regime.

The retained Sprint 4/5 evidence is not ready. It covers only 31 official
sessions from 2026-07-01 through 2026-08-12; the universe retained on 2026-08-12
cannot prove historical membership; all 1,550 evaluated stock/session pairs were
insufficient; corporate-action status, negative completeness, and revision
semantics are unproven; and prices are raw while adjusted-price and historical
symbol-change authority are unsupported. It therefore cannot produce an
observed Market Regime label or validate a taxonomy, factor, threshold,
effectiveness, or performance claim. Synthetic fixtures may later prove
mechanics only; they cannot cure these evidence blockers.

## Deferred to ARK-166

A 20-session comparison and 30-of-50 boundary are candidates only. Neither is
approved by ARK-165. ARK-166 must resolve and freeze the comparison-session
selection, endpoint comparison operator, equality/tie handling, threshold
inclusivity, label set, null-label behavior, output/evidence schema, bounded
reason inventory and precedence, canonical identity, replay semantics, and all
edge cases. It must justify the chosen rule against simpler alternatives before
outcome analysis and must preserve equal weighting and the exact-50 denominator.

Until that second half is approved, there is no executable classifier and no
valid observed output. No implementation, provider adapter, acquisition, or
observed classification is authorized by this policy.
