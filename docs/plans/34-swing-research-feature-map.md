# Plan 34: necessary-only swing-research feature map

**Issue:** [#158](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/158)
**Status:** accepted planning taxonomy; candidate features remain unapproved
**Risk:** R3 planning; no runtime or market calculation changes

## Authority and outcome

This plan records what the project has delivered, which narrowly bounded future
feature families may be evaluated, and where each responsibility belongs. It
prevents a named trading concept, conversational explanation, or roadmap mention
from being mistaken for accepted implementation scope.

The product remains a research, analysis, scanning, and screening tool for
listed-equity swing trading. Default research and qualification focus on the
point-in-time Nifty 100. Reusable feature cores remain bounded to explicit
canonical listed-equity cohorts and do not embed index-membership policy.

This document accepts the taxonomy and admission process only. It is not an
implementation contract. Every possible feature below remains **deferred** until
an owner-prioritized GitHub Issue proves that it is necessary for a concrete
swing-research decision and freezes the smallest working slice.

## Necessary-only rule

Relevance is not enough. A feature enters the roadmap only when it is among the
smallest useful facts required for a named swing-research, analysis, scan, or
screening decision.

The default decision is **do not build it**. Reject or defer a feature when any
of these is true:

- delivered facts already answer the research question;
- the external AI can explain the supplied structured facts without another
  deterministic market calculation;
- the feature is merely popular terminology, catalogue completeness, visual
  decoration, or a renamed version of an existing fact;
- its rules require hindsight line fitting, repainting, unsupported intent, or
  subjective tolerance changes;
- the required source, granularity, point-in-time identity, corporate-action
  treatment, or completed-bar evidence is unavailable;
- it cannot be evaluated separately from overlapping features;
- it is too rare, unstable, or operationally expensive for the expected
  screening value; or
- it adds a score, signal, recommendation, or return claim before separate
  historical and prospective evidence supports that claim.

Prefer one direct fact over a pattern family, one causal level over a drawing
engine, and one separately measurable confirmation over a composite score.

## Signal preservation and filter budget

Useful independent facts must not become an accidental conjunction in which a
stock qualifies only when every Price Action, Market Structure, Volume,
Relative Strength, and Liquidity/SMC condition agrees. Adding more filters does
not imply better research and can erase the opportunity set through correlated
or redundant confirmation.

The default integration is additive context, not a mandatory gate:

- safety, authorization, identity, provenance, completed-bar, price-basis, and
  required-evidence failures remain fail-closed;
- a neutral, absent, unsupported, or insufficient **optional analytical fact**
  does not become `NO_TRADE` unless an accepted strategy or screening contract
  demonstrates why that fact is mandatory;
- each strategy or screen names its smallest mandatory conditions explicitly;
- additional facts begin as research dimensions, explanations, ranking context,
  or separately testable confirmations rather than hidden hard filters; and
- correlated facts must not be counted repeatedly as independent confirmation.

No research plan targets 100% signal accuracy in isolation. Perfect accuracy on
zero or an impractically small number of observations is not useful evidence.
When a later strategy or scanner evaluates a filter, it must compare the simple
baseline with the added filter and report at least candidate coverage, retained
opportunity count, no-trade frequency, marginal error change, and out-of-sample
behavior. Performance claims additionally require realistic costs and slippage.

A filter is retained only when evidence shows a material benefit without an
unacceptable collapse in usable opportunities. The accepted strategy contract
must define that tradeoff; Plan 34 does not invent a universal threshold. If the
simpler rule is adequate, keep it simple and reject the extra filter.

## Current delivery lanes

Issue #155's governing merge completes the reviewed adjusted-capture runtime
delivery prerequisite without claiming historical closure. The remaining
ordered current/live delivery lane is:

1. Issue #156 — implement bounded current-at-retrieval Nifty 100 adjusted
   capture under Plan 33; and
2. Issue #145 — define the cross-module internal-error taxonomy and privacy-safe
   operator diagnostics before another product module starts.

Issue #147 completed its separate parallel temporal-evidence lane at `4/4`,
passed unchanged Plan 29 for `OHLCV_ONLY`, and closed through PR #166. Its
historical result remains separate from the ordered current/live lane.

No possible feature in this plan automatically enters either lane.

## Delivered factual boundaries

| Module | Delivered authority | Delivered facts | Explicit boundary |
| --- | --- | --- | --- |
| Market Structure | [Plan 31](31-current-supplied-cohort-market-structure-contract.md), Issue #148 | Confirmed swing highs/lows, `HH`/`HL`/`LH`/`LL`, trend, close-confirmed first-crossing BOS and CHoCH | BOS and CHoCH are structural facts, not an SMC implementation, signal, recommendation, or proof of institutional activity. |
| Price Action v1 | [Plan 32](32-current-supplied-cohort-price-action-contract.md), Issue #152 | Completed S20 candle direction, range state, exact range/body/upper-wick/lower-wick sizes, and exact S19-close-to-S20-open/close relations and distances | No named pattern, level, line, zone, threshold, score, signal, effectiveness, or Volume fact. |
| Current raw market data | Plans 19, 21, and 27 | Provenance-bound completed-session raw OHLCV, source-reported volume, schedule, and corporate-action admission | Volume in an admitted grid does not make Price Action or Market Structure a Volume Analysis module. |

“Price action” may be used broadly outside this project. Inside this repository,
the versioned contracts above control classification. Market Structure, Price
Action, Volume Analysis, Relative Strength, and any Liquidity/SMC facts remain
separate evidence producers.

## Bounded evaluation shortlist

This is an evaluation shortlist, not a promised backlog. It deliberately omits
catalogue-style feature expansion.

| Possible slice | Concrete swing-research use | Smallest adequate candidate | Default decision |
| --- | --- | --- | --- |
| Level and breakout context | Screen for price approaching, rejecting, or closing through a causally confirmed level and observe a later retest. | Reuse confirmed Market Structure pivots; add one explicit level relation, later-bar breakout, or later-bar retest fact only if existing BOS/CHoCH facts are insufficient. | **deferred** pending a demonstrated gap. |
| Volume context | Distinguish price movement with ordinary, expanding, or contracting participation. | One provenance-bound relative-volume or expansion/contraction fact on comparable completed sessions. | **deferred** pending source and baseline evaluation. |
| Relative Strength | Compare a stock with an explicit benchmark or cohort for screening without making a recommendation. | One exact bounded benchmark relation with point-in-time identity and one price basis. | **deferred** pending benchmark and temporal evaluation. |
| Selected candle context | Describe a recurring completed-bar condition not already expressible from Price Action v1 facts. | One direct previous-high/low, inside/outside, or range relation; use a named pattern only if the name adds necessary screening value. | **deferred**; default to direct facts instead of names. |
| Liquidity lifecycle | Test whether one objective liquidity event adds distinct swing context beyond Market Structure and level facts. | At most one confirmed sweep/reclaim lifecycle with explicit invalidation, if evidence establishes need. | **deferred** and lower priority than simpler facts. |

Trend-line engines, channels, wedges, triangles, flags, head-and-shoulders,
double tops/bottoms, broad candlestick catalogues, order-block catalogues,
fair-value-gap catalogues, and generalized supply/demand-zone systems are **not
planned features**. They remain outside the roadmap unless a later owner-
approved evaluation proves one narrowly defined fact is necessary, objective,
non-duplicative, and worth its evidence and maintenance cost.

## Price Action extension boundary

A future Price Action slice may be considered only when it answers a concrete
screening question that Price Action v1 and Market Structure cannot already
answer.

Potential direct facts are limited to:

- previous-high/low relations;
- inside/outside or range expansion/contraction relations;
- price distance from a causally confirmed structural level;
- a close-confirmed breakout or breakdown not already represented adequately by
  BOS/CHoCH; and
- a retest occurring on a later completed bar under explicit time, price,
  first-touch, and invalidation rules.

A delivered BOS is not automatically a generic breakout setup. A CHoCH is not a
reversal signal. Neither implies a successful retest.

Named candle or chart patterns are disfavored. A label such as doji, hammer,
engulfing, wedge, flag, or triangle has no accepted meaning here until a
necessary-only evaluation demonstrates value beyond direct geometry and freezes
its arithmetic, anchors, tolerance, context, timing, overlap, and ambiguous
outcome. Hindsight-adjusted anchors and tolerances are prohibited.

## Separate Volume Analysis boundary

Volume Analysis is an independent evidence module. It may eventually provide
one or more facts beside Price Action, Market Structure, breakout/retest,
Relative Strength, or a liquidity fact, but those modules do not silently
recalculate or embed Volume facts.

The smallest plausible candidates are:

- volume relative to one explicitly defined prior-session baseline;
- volume expansion or contraction; and
- price direction paired with a separately reported Volume fact.

A future contract must preserve source-reported volume semantics and reject or
classify missing, non-integral, negative, stale, corporate-action-affected, or
incomparable values. Adjusted prices do not permit relabelling source-reported
volume as adjusted volume.

Volume profile, bid/ask delta, footprint, depth, and order-flow claims need
different data capabilities. They are unsupported unless a later source and
contract prove the required granularity and provenance. Daily volume does not
prove institutional activity.

## Separate Relative Strength boundary

Relative Strength remains independent from absolute price direction and Volume.
A future contract must name the exact benchmark, cohort, point-in-time identity,
price basis, schedule, window, cutoff, missing-member behavior, and corporate-
action treatment. It must not silently substitute an index, provider, or later
constituent set.

“Relative Strength” here would mean a deterministic comparative market fact,
not RSI, a recommendation, a ranking promise, or evidence of future return.

## Separate Liquidity/SMC boundary

BOS and CHoCH remain in delivered Market Structure. The project does not need a
broad SMC module merely because the terminology is popular.

Only a narrowly defined liquidity fact may be evaluated when it is necessary
and adds information not already supplied by pivots, trend, BOS/CHoCH, level
relations, Volume, or Relative Strength. A confirmed sweep/reclaim is the
smallest candidate. Equal-level pools, fair-value gaps, order blocks,
supply/demand zones, and multi-timeframe alignment remain unsupported unless a
later evaluation independently proves a concrete need.

The product will not claim smart-money participation, stop hunting,
manipulation, institutional intent, or profitable execution from an SMC label.

## Admission gate for every future capability

A possible feature enters implementation only when all applicable rows below
are resolved in its governing Issue and accepted contract.

1. **Necessary swing use** — name the exact listed-equity swing-research,
   analysis, scanning, or screening decision that cannot be answered adequately
   by delivered facts. “Commonly used” is not sufficient.
2. **Distinct information** — prove what the fact adds beyond delivered Market
   Regime, Industry Participation, Market Structure, Price Action, and any
   admitted Volume or Relative Strength fact. Reject aliases and double-counting.
3. **Smallest alternative** — compare the proposal with exposing or combining
   an existing direct fact. Select the least costly fact that answers the need.
4. **Practical utility** — state expected coverage, frequency, explainability,
   and operational cost. Reject rare or fragile features whose maintenance and
   evidence cost exceeds likely screening value.
5. **Deterministic definition** — freeze inputs, formulas, windows, anchors,
   thresholds or threshold-free rules, ties, tolerances, ordering, precedence,
   invalidation, expiry, and insufficient or ambiguous outcomes.
6. **Causal timing** — use only completed evidence known by the decision cutoff.
   Freeze confirmation timing and prohibit repainting, future anchors, and
   same-bar knowledge that was not genuinely available.
7. **Data capability** — bind canonical equity identity, point-in-time universe
   policy where applicable, schedule, provider mapping, price and volume basis,
   corporate-action treatment, provenance, and resource bounds. Unsupported
   evidence returns an explicit unsupported or insufficient result.
8. **Research claim** — initial delivery returns explainable facts, not a score,
   signal, recommendation, or return claim. Effectiveness requires separately
   authorized point-in-time, out-of-sample, walk-forward, costs, and prospective
   evidence.
9. **Working slice** — implement one smallest useful fact family. Additional
   patterns, timeframes, providers, tuning, persistence, replay, delivery
   surfaces, and resilience remain later slices.
10. **Verification and review** — use discriminating checks for a new observable
    contract; cover malformed, unsupported, insufficient, conflicting,
    boundary, limit-plus-one, temporal, substitution, interruption, retry, and
    combined failures as applicable; run exact-candidate repository gates and
    independent domain/security review.

Failure at gates 1–4 normally rejects the proposal before formulas or code are
written. Before an accepted proposal enters implementation, its governing Issue
must also record, in at most five lines: expected value, scope fit, material
data or research risk, the smallest adequate alternative, and exactly one
disposition—`accepted`, `deferred`, or `rejected`. Deferred and rejected
proposals stop; acceptance authorizes only the separately frozen working slice.

## Candidate lifecycle and scheduling

A roadmap mention means only `POSSIBLE_EVALUATION`. It does not create active
WIP, a backlog promise, or an implementation commitment.

```text
concrete unmet swing-research need
  -> owner-prioritized governing GitHub Issue
  -> at-most-five-line evaluation: expected value, scope fit, material risk,
     smallest adequate alternative, and accepted/deferred/rejected disposition
  -> reject/defer, or accepted working/later partition
  -> accepted versioned contract and adversarial matrix when applicable
  -> implementation and observed verification
  -> exact-byte independent review
  -> PR, hosted gates, merge, and truthful delivery record
```

No formula, threshold, pattern name, module order after #145, or effectiveness
claim is frozen by this plan. The owner selects the next product direction after
the current ordered lane. External temporal waiting in #147 does not consume
that WIP.

## Documentation acceptance

Plan 34 is complete when the authoritative architecture, roadmap, and upcoming-
sprints overview link this necessary-only taxonomy; Issue #154's merged
lifecycle is truthful; repository documentation checks and independent exact-
byte review pass; and the change is delivered through a reviewed PR. No runtime
smoke, market-data call, private-store mutation, or historical qualification is
required or authorized for this planning-only change.
