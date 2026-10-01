# Swing-trading return and loss-exit risk decision

Date: 2026-08-08
Status: proposed/open inputs, rejected approaches, and an accepted direction
pending a strategy specification

**Later scope clarification — 2026-10-01.** Nifty 50 references below preserve
the August scope. [The current architecture](../architecture-freeze-v1.md#owner-decision-listed-equity-feature-boundary)
sets point-in-time Nifty 100 as the default focus; historical membership and
all capability-specific evidence gates remain necessary. [Plan 43](../plans/43-single-stock-loss-scenario.md)
now specifies caller-supplied loss-scenario arithmetic and expressly prohibits
maximum-loss, safe-size or trade-eligibility claims. It does not accept a strategy.

## Context

The owner is evaluating a future Nifty 50 delivery-equity swing strategy. The
scope excludes F&O, crypto, forex, intraday activity, and order execution. This
note records decision inputs; it neither approves a strategy nor changes the
current Sprint 2 scope.

Duplicate review: `docs/notes/` was searched for return, loss-exit, time-stop,
invalidation, position-risk, holding-period, and `NO_TRADE` material. Related
notes describe the risk-first direction and open strategy questions, but no
existing note records this return and loss-exit decision.

## Proposed and open inputs

### Holding window

**Status: proposed/open.** A 5–10 trading-day holding window is an owner
direction and input, not an approved rule. A formal strategy specification and
empirical validation must define the exact horizon, entry, exit, data frequency,
and exception handling before implementation.

### Return hypotheses

**Status: proposed/open.** A 2–3% weekly outcome and an 8–12% monthly outcome
are upside hypotheses and validation targets only. They are not promises,
guaranteed outcomes, base forecasts, or position-sizing assumptions. SEBI's
investor education material notes that share returns are subject to risk and
volatility and are not guaranteed [1][2].

### Reading historical broker-verified P&L

**Status: open analytical limitation.** Historical broker-verified P&L can
establish the displayed account/report period and the report's displayed
activity. It does not, by itself, establish total-capital ROI, full-cycle
sustainability, drawdown, all accounts, or future expectancy. These are
analytical limits of a displayed report, not an accusation about any person or
platform. For example, Zerodha describes its Verified P&L as a configurable
public report with selected date ranges and segments; it is therefore a
platform-specific reporting capability, not a complete strategy evaluation [3].

## Rejected approaches

**Status: rejected.** The following approaches are intentionally not selected:

- A default rule to never sell at a loss.
- An automatic exit merely because a position is red, without reference to a
  predeclared invalidation or time rule.
- A 100% realized win rate as a success KPI.
- Converting a failed swing into an indefinite investment ad hoc merely to avoid
  realizing the loss.

## Accepted direction pending a strategy specification

**Status: accepted direction pending strategy specification.** Any future
strategy proposal must be evaluated with:

- a predeclared entry thesis;
- price, volatility, fundamental, and regime invalidation conditions;
- a time stop tied to the expected holding horizon;
- position and portfolio risk bounds;
- a fresh, separate re-underwriting and capital mandate before any extended
  hold; and
- `NO_TRADE` as a first-class result when evidence or risk validation fails.

Economic and unrealized loss, as well as the capital opportunity cost of a
position, must be recognized in evaluation. This direction aligns with the
architecture's capital-preservation, risk-validation, and no-trade boundaries;
it does not set numerical limits or authorize a trading rule.

## Required evidence before strategy acceptance

The future specification and validation package must include:

- net expectancy using win rate together with average win and average loss;
- costs, taxes, and slippage;
- maximum drawdown, loss streak, and time underwater;
- capital utilization and opportunity cost;
- exposure and concentration;
- point-in-time Nifty 50 membership;
- regime-separated out-of-sample and walk-forward results; and
- a comparison of predefined exits with the never-realize-loss policy.

The evidence must prevent look-ahead, survivorship, and data-snooping bias. It
must use point-in-time Nifty 50 membership because Nifty 50 constituents are
reviewed and may be replaced or reconstituted [4].

## Open research: implied-volatility and forensic-evidence limits

**Status: open research/supporting rationale.** This section records a boundary
for interpreting options-market observations; it does not add an options
strategy, option analytics, a strategy specification, architecture work, or a
Sprint 2 requirement. The accepted no-F&O/no-option-analytics product direction
remains unchanged.

An implied-volatility (IV) decline can hurt a long-vega option buyer (often
called IV crush), while an IV rise can hurt a short-vega option seller even when
spot remains range-bound. Those effects are option-position mechanics, not a
signal or recommendation for this delivery-equity swing tool. NSE describes
India VIX as a near-term expected-volatility measure calculated from best
bid-ask quotes in the NIFTY options order book [5]. Expected-volatility
repricing, order-book liquidity, and event risk can therefore explain observed
IV movement without establishing a directional spot view.

IV movement alone does not prove intent, manipulation, or a particular
counterparty relationship. NSE publishes a Reversal Trade Cancellation
Mechanism under surveillance resources [6]. SEBI has also issued an
adjudication order concerning three-way reversals in illiquid stock-options
contracts [7]. That regulatory evidence establishes that reversal-based
manipulation allegations and findings have existed in that specific illiquid
contract context; it cannot be generalized to every liquid NIFTY move, IV
change, or ordinary market trade.

A retail last-traded-price feed or chart cannot establish counterparties, order
intent, coordination, or whether an observed sequence was abusive. Any future
forensic question would require appropriately authorized, complete evidence
such as timestamped order and trade audit trails, order modifications and
cancellations, market-wide order-book and liquidity context, contract details,
and the relevant exchange or regulatory record. This is an evidence boundary,
not a request to collect or process those data in the current product.

## Recovered research rationale — reconciled 2026-10-01

**Status: deferred research and rejected defaults; no strategy approval.** The
August 20 discussion retained these alternatives for later specification:

- A fixed-percentage trailing exit may be researched later. The proposed small
  comparison is structural invalidation plus a time stop versus one
  preregistered fixed-percentage trail, with gap/slippage treatment. ATR,
  SuperTrend and moving-average trailing exits were rejected as defaults:
  extra parameters introduce tuning risk, and the discussion did not validate
  any exit family.
- Five positions, equal 20% weights and a one-in-one-out rule were rejected as
  diversification defaults. Shared Industry, market and event exposure can
  leave the basket concentrated. Those numbers are research candidates only;
  a nominal 1:3 target is not evidence of profitability. The net-expectancy and
  concentration requirements above remain the evaluation basis.
- A generic factor/alpha signal module was rejected. Factor attribution remains
  a possible later evaluation metric with explicit benchmark/model definitions;
  unexplained return is not automatically alpha. This adds no input factor or
  implementation item under [Plan 34](../plans/34-swing-research-feature-map.md).

Provenance: recovered document `01a01d42-f289-7000-9d9a-c9025138589d`, August 20
research discussion (trailing exits, portfolio concentration and factor
interpretation), with decision memories `eccb11d6-c442-4b52-9230-e8592783435c`,
`f1665182-b623-4417-a3fe-d496b548de23` and
`ac56eff7-c407-46f7-b69c-13da5b45e3d1`. These are retained discussion rationale,
not independent validation of the cited research or permission to implement.

## Consequences and next steps

Before implementation, a future strategy specification must freeze exact entry,
exit, invalidation, time, risk, and position-sizing rules. The deterministic
tool remains a source of structured facts and validation; it cannot guarantee
returns or autonomously trade.

## References

1. [SEBI Investor — Understanding Shares](https://investor.sebi.gov.in/understandings_shares.html), accessed 2026-08-08.
2. [SEBI Investor — Avenues for Investments](https://investor.sebi.gov.in/investment-assetclasses.html), accessed 2026-08-08.
3. [Zerodha Support — What is Verified P&L and how to use it?](https://support.zerodha.com/category/console/reports/other-queries/articles/verified-p-l), accessed 2026-08-08. Cited only for the platform-specific capability statement above.
4. [NSE Indices — Methodology Document for Equity Indices](https://www.niftyindices.com/Methodology/Method_Nifty_50.pdf), accessed 2026-08-08.
5. [NSE India — India VIX Index](https://www.nseindia.com/static/products-services/indices-indiavix-index), reverified 2026-08-09.
6. [NSE India — FAQs: Reversal Trade Cancellation Mechanism](https://www.nseindia.com/static/resources/faqs), reverified 2026-08-09.
7. [SEBI — Adjudication Order: three-way reversals in illiquid stock-options contracts on NSE](https://www.sebi.gov.in/enforcement/orders/jan-2026/adjudication-order-in-the-matter-of-execution-of-three-way-reversals-by-certain-entities-in-illiquid-stock-options-segment-contract-on-nse_99424.html), reverified 2026-08-09.
