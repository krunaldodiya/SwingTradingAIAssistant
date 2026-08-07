# Research vision, validation, and instrument extensibility

Date: 2026-08-07

Status: mixed; each conclusion is labelled below

## Context

The owner wants an AI-assisted research system, not an autonomous trading bot.
The deterministic tool supplies reproducible market and risk facts; a compatible
external AI harness acts as the contextual research, analysis, and explanation
layer. Current trading and implementation focus is Nifty 50 equity swing
research. The architecture should remain extensible without pretending that one
universal research method applies unchanged to every instrument.

Private financial circumstances discussed as motivation are intentionally not
recorded here. Only durable product and risk-design consequences are preserved.

## Accepted decisions

### Deterministic tool with an external reasoning layer

Status: **accepted**

The tool owns data access, point-in-time calculations, validation, backtesting,
timestamps, provenance, and structured research packets. The external AI owns
contextual reasoning and explanation. It must not silently recompute facts from
raw OHLC, invent missing evidence, or override hard validation and risk failures.
Library, CLI, API, skill, connector, and MCP interfaces should eventually wrap
the same versioned application contracts rather than creating separate logic.

### Narrow product, instrument-extensible architecture

Status: **accepted**

V1 implements and validates only point-in-time Nifty 50 equity swing research.
Shared infrastructure may be instrument-neutral when an immediate equity use
proves the abstraction. Equity-specific fundamentals, corporate actions,
promoter/shareholding data, disclosures, and research rules remain in explicit
equity modules. No futures, options, forex, crypto, or other instrument support
is implied or scheduled by this decision.

A future instrument module needs a new approved scope decision, data model,
market microstructure and risk specification, point-in-time evidence, validation
plan, and atomic implementation work. Up-front abstractions that serve only a
hypothetical future instrument are rejected.

### Risk and capital preservation before opportunity count

Status: **accepted direction; exact thresholds remain open**

The system optimizes for capital preservation, decision quality, explainability,
low drawdown, and repeatability rather than maximum trade frequency or headline
return. `NO_TRADE`, insufficient data, and hard-risk rejection are normal
outcomes. Position risk, aggregate portfolio heat, concentration, liquidity,
gaps, costs, slippage, drawdown, and invalidation belong in deterministic,
versioned risk evidence. The external AI explains those facts but cannot waive a
hard failure. Exact per-position, portfolio, and drawdown limits require an
approved Risk Validation specification.

### Requested-security and portfolio research

Status: **accepted product capability, not yet specified**

The eventual tool should support both opportunity discovery and a direct request
to research any security inside the supported point-in-time Nifty 50 universe.
It should also support a read-only snapshot of supported Nifty 50 holdings so the
tool can calculate performance, concentration, evidence freshness, risk, and
candidate hold/exit conditions. Broker order placement, autonomous position
management, and long-term portfolio advisory remain excluded.

### Historical validation of deterministic and AI behavior

Status: **accepted direction; experiment protocol still requires specification**

Deterministic rules run across the complete approved historical sample. External
AI reasoning is evaluated separately through sampled sealed-time replay: give
the harness only the research packet available at an historical cutoff, record a
versioned decision, then reveal later data and score the outcome under realistic
execution, costs, slippage, and risk rules. Record model and contract versions,
contamination limitations, data/config/code identity, and whether the observation
is in-sample, out-of-sample, or walk-forward.

Historical coverage must be long enough to include materially different regimes
and be justified per strategy and available point-in-time data. Five years was
an illustrative duration, not a universal literal acceptance threshold. Longer
history adds confidence only when membership, corporate actions, disclosures,
costs, and other evidence can be reconstructed without look-ahead or survivorship
bias.

### Indicator minimization and reference material

Status: **accepted**

Indicators are excluded by default and may enter only when an approved
specification proves one mandatory for a defined decision and validates it
against simpler observable facts. Trading books and reference repositories are
hypothesis sources, not specifications. Concepts must be localized to Indian
market structure, accounting, disclosures, promoter/shareholding practices,
corporate actions, exchange calendars, settlement, price bands, costs, taxes,
and liquidity, then tested point-in-time and out-of-sample.

The proposed reading list is David Aronson's *Evidence-Based Technical
Analysis*, Adam Grimes's *The Art and Science of Technical Analysis*, Mark
Minervini's *Trade Like a Stock Market Wizard*, Lee Freeman-Shor's *The Art of
Execution*, and William O'Neil's *How to Make Money in Stocks*. The first three
are the initial priorities if legally owned or authorized copies are available.
For each book, retain a research ledger containing the concept, expected value,
required data, assumptions, conflict with indicator minimization, deterministic
formulation, validation method, and accepted/rejected/proposed status. No book
rule becomes product logic merely because it is popular or successful in a
different market.

## Proposed research design

### Nifty 50 opportunity scanner

Status: **proposed; criteria and cadence are not approved**

A deterministic scanner may reduce the point-in-time Nifty 50 universe through
hard eligibility, data-quality, liquidity, event-risk, and portfolio constraints,
then produce ranked evidence dossiers. Candidate evidence may include market and
sector context, price action, market structure, liquidity/SMC, volume, relative
strength, fundamental change, exchange filings, news/events, institutional
context, and risk. The AI reviews dossiers contextually and returns research,
watch, avoid, `NO_TRADE`, or insufficient-data outcomes.

Do not implement one opaque "magic score." Hard disqualifiers remain visible and
cannot be overridden by the AI. Evidence ranking, scan cadence, holding horizon,
bar frequency, and acceptance thresholds remain open until specified and
validated. An end-of-day scan and a 5-to-30-trading-session horizon were
brainstorming examples only, not approved requirements.

### Institutional, news, and event context

Status: **proposed contextual evidence; data contracts not approved**

FII/DII aggregate flows describe market context, not a complete stock-level
ownership signal. Quarterly shareholding patterns and bulk/block deals may offer
stock-level evidence. AIF information is commonly aggregate, and no complete,
official real-time HNI activity feed should be assumed. Missing evidence must be
`UNKNOWN`, not neutral or fabricated.

For company-specific events, prefer exchange/company filings, regulator records,
credit-rating actions, and company presentations before reputable news. Social
media is an unverified lead only. Every retained item needs source, publication
and effective timestamps, affected security, freshness, and point-in-time
availability.

## Rejected interpretations

- **Rejected:** one fixed script should make every research decision. The tool
  supplies deterministic facts and workflows; the external AI selects the
  relevant supported workflow and reasons over its structured output.
- **Rejected:** the AI should dynamically inspect raw OHLC and calculate whatever
  it wants. That breaks reproducibility, provenance, and bias controls.
- **Rejected:** changing from a high-risk instrument automatically creates a
  profitable process. Product scope, position sizing, validation, and drawdown
  controls remain necessary.
- **Rejected:** large-cap equities are immune to adverse market microstructure.
  Liquidity, gaps, event shocks, institutional flows, and false breakouts still
  require explicit risk treatment.
- **Rejected:** copying price-action, SMC, scanner, or backtest code from a
  reference repository. Concepts require an independent specification and
  validation for this project.

## Open questions

- Exact swing holding horizon and canonical research bar frequencies.
- Risk-per-position, aggregate portfolio heat, concentration, and drawdown-stop
  policies.
- Scanner cadence, hard gates, ranking evidence, and candidate-count limits.
- Fundamental, filing, news, and institutional data sources, licensing, and
  point-in-time retention.
- Portfolio snapshot contract and broker read-only integration boundary.
- Sampling design, evaluation metrics, and cost budget for historical AI replay.
- Evidence required before any future non-equity instrument module is proposed.

## Consequences

1. Complete and package the equity market-data foundation before implementing
   research modules.
2. Specify and validate one locked-pipeline module at a time.
3. Keep shared contracts extensible but add only abstractions exercised by the
   current Nifty 50 equity implementation.
4. Treat risk policy, point-in-time integrity, and reproducible validation as
   release gates, not later enhancements.
5. Update this note and the authoritative architecture whenever an open decision
   becomes accepted, rejected, or superseded.

## Related documents

- [Architecture freeze v1](../architecture-freeze-v1.md)
- [Roadmap](../roadmap.md)
- [Indicator minimization](2026-08-07-indicator-minimization.md)
- [Reference repositories](../reference-repositories.md)
