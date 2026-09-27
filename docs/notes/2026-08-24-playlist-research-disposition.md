# Retained playlist research and disposition

Discussion date: 2026-08-24
Recovered from Hindsight: 2026-09-27
Owner: Krunal Dodiya
Status: retained research; candidate rules remain proposed/deferred, with the
rejected interpretations recorded below. Retention was explicitly requested;
implementation and strategy approval were not granted.

## Context and authority

The owner asked to validate two Zerodha / In The Money playlists and then save
the combined response for future use. It was saved only in project memory
because adding a repository document would have changed Sprint 14's independently
reviewed candidate. This note recovers that missing record.

The original conclusion was that the material provides an idea catalogue and
research checklist, not evidence of a profitable Indian-equity swing strategy
or validated example parameters. No roadmap, architecture, or code change was
authorized from the videos alone. The prior review used automatic transcripts;
visual TradingView/Pine behavior was not verified. Its paper comparisons are
historical research conclusions, not a new literature review in this recovery.

The original Sprint 14 → historical storage → historical validation → Market
Structure sequence is historical. Current sequencing and feature admission are
owned by [Plan 34](../plans/34-swing-research-feature-map.md) and the
[roadmap](../roadmap.md). Completing an old prerequisite does not automatically
approve a candidate below. Later current-first direction and the independent
research-logic policy remain authoritative.

## Material reviewed

The recovered source identifies these five videos:

- [What Is Swing Trading? — Ep. 42](https://www.youtube.com/watch?v=wQml7CVNcMU)
- [The Easiest Way to Find Swing Trading Stocks — Ep. 43](https://www.youtube.com/watch?v=26PmC6w_054)
- [Build a Complete Swing Trading System — Ep. 44](https://www.youtube.com/watch?v=dNiSHl1lfcI)
- [Foundational market papers](https://www.youtube.com/watch?v=GbXYgYz7tL8)
- [Research papers about alpha](https://www.youtube.com/watch?v=S0qoD2-QCJQ)

## Deferred ideas and the rationale worth preserving

These are comparisons to consider within existing responsibilities, not new
modules or a promised backlog. Plan 34 already covers the broad feature
families; the table preserves the more specific hypotheses missing there.

| Candidate | Recovered hypothesis and unresolved requirements |
| --- | --- |
| Cross-sectional Relative Strength | Preregister one ranking definition within an exact point-in-time peer group. “Strongest stock in the strongest sector” needs separate evaluation of Industry exposure, turnover, costs, and momentum crashes. It is not established by a general momentum paper. |
| N-day breakout | A candidate formulation was completed close above the maximum **prior** N-session high. Values such as 7, 10, 15, or 21 were examples, not selected defaults. Freeze lookback exclusion, price basis, corporate actions, knowledge time, next-tradable execution, gaps, invalidation, costs, and slippage before evaluation; first establish that delivered BOS/CHoCH facts do not already answer the question. |
| Liquidity sufficiency | Average share volume alone cannot establish executability. Evaluate dated traded value, trading frequency, spread/depth or explicit evidence limitations, order-size-dependent impact, price bands, partial fills, and stale evidence. This is a safety/capacity question, not proof of ranking edge. |
| Industry-conditioned ranking | Compare a defined rank with and without Industry conditioning, using classifications actually available at the decision time. Current constituent or classification lists cannot reconstruct an earlier basket. |
| Exit comparison | Compare structural invalidation plus a time stop with **one** preregistered fixed-percentage trail, including gaps and slippage. No trailing percentage was approved; the comparison does not justify adding a collection of indicator exits. |
| Concentration and sizing | Investigate single-name and Industry exposure before covariance-heavy portfolio optimization. Five positions, 20% allocations, one-in/one-out replacement, and 1% risk were examples, not approved parameters. Risk-based sizing needs an entry/invalidation contract, gap assumptions, liquidity/capacity, costs, and portfolio limits first. |

The existing [return and loss-exit decision](2026-08-08-swing-trading-return-and-loss-exit-risk-decision.md)
already owns expectancy, time-stop, loss-streak, and gap-risk reasoning. The
playlist does not supply a replacement risk contract or a guaranteed loss cap.

## Research-paper interpretations retained from the audit

This table preserves the prior audit's interpretation limits and project
dispositions. It does not promote historical results into present-day performance
claims or implementation authority.

| Reference | Retained interpretation and disposition |
| --- | --- |
| [Markowitz (1952)](https://doi.org/10.1111/j.1540-6261.1952.tb01525.x) | Portfolio risk depends on variances and covariances. Stock count or equal weighting does not prove diversification or outperformance. Possible later use: concentration and portfolio-risk evaluation. |
| [Sharpe (1964)](https://doi.org/10.1111/j.1540-6261.1964.tb02865.x) | Beta is covariance with the benchmark divided by benchmark variance, not a literal multiplier for each day's price move. Possible evaluation/attribution context, not a swing-entry signal. |
| [Fama (1970)](https://doi.org/10.2307/2325486) and [Fama (1991)](https://doi.org/10.1111/j.1540-6261.1991.tb04636.x) | Efficiency is a framework, not proof that every price is correct. The joint-hypothesis problem requires an explicit expected-return model and benchmark before interpreting unexplained returns. |
| [Fama–French (1992)](https://doi.org/10.1111/j.1540-6261.1992.tb04398.x) | Long-horizon size/value research does not establish a daily swing rule. The audit rejected a generic factor module; attribution could be evaluated later without becoming an input signal. |
| [Jensen (1968)](https://doi.org/10.1111/j.1540-6261.1968.tb00815.x) | Alpha is relative to a stated model and benchmark. Its possible role is later validation, not an unexplained “alpha” factor fed into stock selection. |
| [De Bondt–Thaler (1985)](https://doi.org/10.1111/j.1540-6261.1985.tb05004.x) | The reversal construction used multi-year horizons, with seasonality and distressed/delisted-stock treatment material to interpretation. Rejected for the days-to-weeks swing scope. |
| [Jegadeesh–Titman (1993)](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x) | The roughly 12% historical result discussed in the audit was gross long–short momentum with multi-month formation/holding periods. It did not validate an after-cost, long-only, one-week Nifty 100 rule. Relative Strength remains a deferred hypothesis. |
| [Coval–Shumway (2001)](https://doi.org/10.1111/0022-1082.00352) | The roughly −3% weekly result discussed applied to a particular zero-beta at-the-money straddle, not all option buyers or a free premium for sellers. Options remain outside scope. |
| [Moskowitz–Ooi–Pedersen (2012)](https://doi.org/10.1016/j.jfineco.2011.11.003) | The strategy used futures, volatility scaling, rolls, long/short positions, and cross-market diversification. It was not simply “positive 12-month equity return means buy.” No separate Time-Series Momentum module was approved. |

## Rejected interpretations and open questions

The audit rejected replacing the delivered Market Regime with moving-average
filters, adding Renko, taking ATR/SuperTrend/moving-average exits as defaults,
subjective flags/pennants or AI chart inspection, a fixed 1:3 profitability
claim, indefinite trailing/holding, and a generic factor/alpha platform. An
indicator bundle or portfolio optimizer was not justified by the playlists.
The existing architecture already excludes the proposed options, short
execution, futures, ETF/commodity/gold, and multi-asset expansion; the audit
does not create exceptions to those boundaries.

No ranking window, breakout period, trail percentage, position count, allocation,
risk percentage, or performance threshold was approved. Any renewed evaluation
needs a concrete unmet research question and a separately governed, necessary-only
contract. Educational sources do not replace independent definitions and
project-specific evidence.

## Recovery provenance

Bank: `pi-projects`.

- Original retained summary: `dbd7aa99-f2a9-41b7-93f8-2ae9e8d1ea12`
  (content SHA-256 `a58a0d27ee748994da5ba1662e81247d92d1a33a94935aacbf68762767ecd2f3`).
- Corroborating summaries: `59de6b76-d867-47da-80b9-df9380c4c5eb` and
  `4267983d-52d7-4d33-91ab-4b543a61b34d`.
- Original conversation document: `01a01d42-f289-7000-9d9a-c9025138589d`;
  owner retention requests at `2026-08-24T04:06:44.682Z` and
  `2026-08-24T04:07:03.857Z`; assistant's memory-only explanation at
  `2026-08-24T04:44:47.653Z`.

The historical `/tmp/youtube-playlist-audit/` reports were temporary. This
recovery used the retrievable summary and original conversation, not an assumed
surviving copy of those reports. No complete transcript is copied into the repo.
