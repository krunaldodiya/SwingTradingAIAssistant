# Nifty 100 universe-expansion hypothesis

Date: 2026-08-09
Status: open research hypothesis; not an approved product, architecture, Sprint,
strategy, data, or implementation change

## Context and current boundary

The production architecture, data contracts, and research scope remain limited
to point-in-time Nifty 50 equities. `NO_TRADE`, insufficient data, and hard-risk
rejection are valid outcomes, not defects to be optimized away. This note only
records a future research question raised by scarcity-caused `NO_TRADE`; it does
not authorize an experiment, backtest, data acquisition, code change, or a
change to the architecture freeze or Sprint 2.

The Nifty 50 is the baseline universe. A possible incremental sleeve would be
the point-in-time Nifty Next 50. Nifty Indices describes Next 50 as the balance
50 companies from Nifty 100 after excluding Nifty 50, while Nifty 100 tracks the
combined Nifty 50 and Next 50 portfolios [1][2]. The intended comparison
universe is therefore the union `Nifty 50 ∪ Nifty Next 50 = 100` names at each
effective point in time—not 150 names and not a duplicated Nifty 50 sleeve.
Nifty Indices states that the two component sets are synchronized and disjoint
at a point in time [3].

## Problem and do-nothing baseline

**Open problem.** A larger universe may be worth studying only if a review can
show that otherwise-valid candidate capacity is scarce because the Nifty 50 is
too small after the same predeclared eligibility filters are applied. It cannot
fix `NO_TRADE` caused by an unsuitable regime, missing or stale data, a risk
failure, inadequate liquidity, concentration, capital limits, or no valid entry
thesis. Those outcomes remain `NO_TRADE` in every arm.

The do-nothing baseline is to retain the point-in-time Nifty 50 universe and its
current scope. The hypothesis is not that a larger list improves returns, trade
count, or decision quality. It is only that a separately validated Next 50
sleeve might add qualifying opportunities in specifically documented
scarcity-caused periods without weakening the same risk or capital constraints.

## Risks, data, and provenance requirements

Nifty Indices characterizes Next 50 as the second rung of large, liquid stocks
but notes that it is not as liquid and its information is not as noise-free as
Nifty 50 [3]. A future study must therefore explicitly measure and disclose,
rather than assume away:

- liquidity, gaps, spread/impact, slippage, transaction costs, and capacity;
- false-breakout/noise and event risk;
- sector and issuer concentration, including concentration introduced by the
  incremental sleeve; and
- whether a shared capital constraint displaces a Nifty 50 candidate rather than
  adding an independent opportunity.

Every historical row would require point-in-time constituent evidence with
effective date and source version, plus auditable ISIN-to-symbol/instrument
lineage, sector classification, corporate-action and symbol-change treatment,
licensing/redistribution status, retrieval time, and provenance. Current index
composition, a current symbol list, or a post-event mapping must never be used
to reconstruct a past universe. The index methodology and constituent source
must be retained under an approved license and versioned alongside any future
research record [1][2][4].

## Future study design, if separately approved

Any future program needs explicit owner approval, an approved specification,
and a locked plan before work begins. Its preregistered protocol must compare:

- a point-in-time Nifty 50 arm; and
- a point-in-time Nifty 50 plus Next 50 arm, formed as the disjoint Nifty 100
  union.

Both arms must use identical entry, exit, invalidation, holding-horizon,
position-sizing, risk, capital, liquidity, cost, and concentration rules. They
must share the same capital budget and portfolio limits; the expanded arm may
not receive extra capital or relaxed controls. Results must attribute each
eligible opportunity to Nifty 50 or Next 50 and record displacement whenever a
Next 50 selection consumes capital or a portfolio slot that the baseline arm
could have used.

The protocol must pre-register hypotheses, the scarcity definition, universe
snapshots, features, metrics, decision rules, exclusions, and promotion gates
before inspecting outcomes. It must control multiple testing and data snooping,
separate in-sample work from out-of-sample and walk-forward evaluation, split
results by market regime, and report uncertainty rather than a single headline
result. A durable trial ledger must use immutable, append-only or equivalently
tamper-evident records preserving the code/configuration/data and membership
versions, run dates, universe snapshots, candidate and exclusion counts,
fills/cost assumptions, deviations, failures, decisions, timestamps, and
provenance.

Operational feasibility is also an acceptance question: the program must show
bounded request, storage, catalog, memory, runtime, retry, and review costs;
the data-quality and lineage workload scales with every added name. It must not
reuse a current Nifty 50 snapshot as evidence that Next 50 history is ready.

## Promotion gates and non-authority

No promotion may occur merely because the expanded arm finds more candidates or
has an attractive historical interval. Before any future scope decision, the
owner must approve a locked plan and independently assess whether the evidence
shows a repeatable, out-of-sample, regime-aware incremental benefit after costs
and uncertainty, without worse risk, drawdown, concentration, capacity, data
quality, or operational controls. The evidence must distinguish added Next 50
opportunities from displaced Nifty 50 opportunities and must show that the
tested `NO_TRADE` cases were truly scarcity-caused.

Failure to meet any gate preserves the Nifty 50 baseline. Meeting them would
still require a separate owner product/architecture decision, point-in-time data
and licensing approval, risk specification, atomic work, deterministic tests,
and review before implementation. This note makes no guarantee of improvement
and does not change the current Sprint 2 exclusions.

## References

1. [Nifty Indices — Nifty 100](https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-100), reverified 2026-08-09.
2. [Nifty Indices — Nifty Next 50](https://www.niftyindices.com/indices/equity/broad-based-indices/NIFTY-Next-50), reverified 2026-08-09.
3. [Nifty Indices — Index concepts FAQ](https://www.niftyindices.com/resources/index-concepts/faqs), reverified 2026-08-09.
4. [Nifty Indices — Equity indices methodology](https://www.niftyindices.com/Methodology/Method_NIFTY_Equity_Indices.pdf), reverified 2026-08-09.
