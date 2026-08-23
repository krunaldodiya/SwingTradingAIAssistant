# Architecture Freeze v1.0

## Goal

Build an agent-agnostic Swing Trading Research Tool that supplies trustworthy,
structured evidence to AI assistants researching safe, consistent, and
explainable listed-equity swing-trading opportunities. Product research,
qualification, and default workflows focus on the point-in-time Nifty 50 plus
Nifty Next 50 (the Nifty 100).

## Owner decision: listed-equity feature boundary

[GitHub Issue #130](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/130)
establishes the following architecture decision:

1. A reusable feature core accepts an explicit bounded list of canonical
   listed-equity instruments. It does not decide whether an instrument belongs
   to an index.
2. Point-in-time index membership, universe discovery, and default cohort
   selection belong to a separate higher-level policy. The product-default
   policy selects the point-in-time Nifty 50 plus Nifty Next 50.
3. Canonical identity is ISIN and exchange, with effective symbol history and
   versioned provider mappings. A symbol or provider token alone is not durable
   identity.
4. Every feature contract declares its required data capabilities, bounds,
   freshness, and evidence. A missing or unqualified capability returns a typed
   unsupported or insufficient-evidence outcome; an index check is not a
   substitute for capability admission.
5. An explicitly supplied listed stock outside the Nifty 100 may use a reusable
   capability when canonical identity and all capability-specific evidence
   exist. Such stocks are not the primary roadmap, research-qualification, or
   default-workflow focus.

Existing Nifty 50 V1 contract names and exact historical rules remain valid
records. They are not evidence that current implementations already satisfy
this boundary. Migration is incremental and versioned under
[Plan 23](plans/23-instrument-agnostic-feature-boundary-and-coupling-audit.md);
there is no big-bang rename or reinterpretation of frozen evidence.

## Delivery priority overlay

The architecture, locked modules, pipeline, exclusions, and historical plan
below remain intact. The owner has changed delivery priority only:

1. make the current/live research path usable first through current
   price/volume, Market Regime, Sector Analysis, news/events, and one integrated
   packet for an external AI;
2. retain every admitted current fact with point-in-time provenance so future
   evaluation cannot invent what was knowable;
3. complete the deferred historical store and backtest validation after the
   current packet is usable.

This ordering removes no feature or gate. Historical work is deferred, not
deleted. [Upcoming Sprints Overview](upcoming_sprints_overview.md) owns the
current Sprint 10–16 dependency sequence; it does not change the module order
or authorize autonomous signals, recommendations, or broker execution.
For current/live Market Regime, raw completed-close comparison is allowed only
when its versioned comparability contract states the evidence basis and limits.
[Issue #125](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/125)
and [Plan 21](plans/21-current-supplied-cohort-corporate-action-screen-contract.md)
merged through PR #128 as `cdb9ab1c2796356a3e9f604bdd5aeb404cf7519b`;
the narrower Issue #127 adjusted-daily MVP merged through PR #129 as
`c530ae3d6dc43714a71c1f874fe81ecb6b4944c6`; and
[Issue #132](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/132)
merged its canonical explicit-stock adjusted-close input through PR #133 as
`847dfbdf7b6114cb736e00abf9126c995d30e828`.

Those dependencies are complete. Sprint 11
[Issue #116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116)
is closed/completed after
[PR #124](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/124)
merged exact reviewed head `d56120fb5966dffea32207b59f1edf0673b2e51b`
as merge commit `f03edf3690e34e25a57b58a15450129e3bf9a5e9`.
The delivered V2 comparability semantics passed 296 focused tests, 2,867 full
tests, 91.03% coverage, Ruff format/check, Pyright, Vulture 80, build, sealed
no-network and live current-prospective smokes, hosted Quality/build, and
GitGuardian. Historical exact-50 V1 semantics remain frozen; future Plan-23
migrations remain separate.

Sprint 12 / [Issue #117](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/117)
is **closed/completed**. [PR #135](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/135)
merged exact reviewed head `b8c416709ebae82879c5dceae603b141b0dd1fa8`
as merge commit `4dfa8ecd1854aec4b4b2181cf2d0310072f65b49`.
Independent exact-revision quality review returned **APPROVE** and security
review returned **PASS**. Local gates passed 2,991 tests at 90.82% coverage,
Ruff format/check, Pyright, Vulture 80, and build; hosted Quality/build and
GitGuardian passed. Issue #117 is closed and its Project item is **Done**.

The delivered current-only contract uses the source's literal NSE Indices
`Industry` field inside the architecture-locked Sector Analysis module. It
does not claim official `Sector` taxonomy or mapping, historical
classification, index membership for the supplied cohort, live participation,
effectiveness, recommendation, order placement, or raw/member publication.
The official parser smoke admitted the exact current 100-row, 6,610-byte
artifact with SHA-256
`5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85`;
it is parser provenance only.

Sprint 12 also records an MVP/working-feature-first process correction: keep
the first working slice limited to current acceptance blockers, separate later
improvements, and apply the scope-expansion circuit breaker before adding
unplanned hardening or subsystems. The corresponding handbook revision is
`93210ed3c28df90fdb971f6b8fd7c96ce71cd240`.

Sprint 13 / [Issue #118](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/118)
is **ACTIVE / IN PROGRESS** under
[Plan 25](plans/25-current-supplied-cohort-event-notice-contract.md). Its first
working slice admits one operator-acquired official NSE Equity `1D`
corporate-announcement CSV for owner-private current/prospective evidence.
Historical backfill, automated acquisition, general news, sentiment, additional
providers, and delivery surfaces remain deferred.

## Repository identity

This repository implements the research-tool layer, not a particular AI agent.
Any compatible agent harness may consume its contracts. AI reasoning happens
outside the deterministic analysis core, which makes the tool testable,
reusable, and independent of one model or agent framework.

The primary objective is not maximum return. The system optimizes for:

- capital preservation;
- consistency;
- high-quality setups;
- low drawdown; and
- repeatability.

"No trade" is a valid and desirable result when the evidence is insufficient,
conflicting, stale, or fails risk validation.

## Explicit exclusions

- Algo or automated order execution
- Intraday trading
- Futures and options
- Forex and crypto
- Long-term investing or portfolio advisory
- A generic multi-asset or generic trading platform
- Any fact, feature, or instrument whose required identity, data capability, or
  point-in-time evidence is unsupported or insufficient
- Automatic product qualification of every listed equity merely because a
  reusable core can accept its canonical identity

These are product and research exclusions. They do not require reusable
listed-equity feature cores to encode Nifty index membership.

## Instrument extensibility boundary

The architecture is listed-equity reusable while the product focus remains
narrow. Shared point-in-time data, provenance, validation, orchestration,
backtesting, risk-evidence, and application-contract primitives should avoid
unnecessary coupling to an index, broker, provider, AI harness, or symbol
convention when a current listed-equity requirement demonstrates the
abstraction.

Index-universe snapshots remain explicit policy evidence. They select or prove
a point-in-time cohort for workflows that make an index-scope claim; they do
not authorize a provider adapter, alter a market fact, or gate an explicitly
supplied stock whose workflow makes no index-membership claim.

Equity fundamentals, corporate actions, promoter/shareholding evidence, and
exchange disclosures stay in explicit equity capabilities. A feature advertises
which of those capabilities it requires. Unsupported identity mappings,
price basis, schedule, sector, corporate-action, news, event, or freshness
evidence remains typed unsupported or insufficient evidence, never an inferred
value or silent neutral.

This decision does not imply futures, options, forex, crypto, another asset
family, or a generic platform. A future non-equity instrument family still
requires a separately approved scope, data model, market-microstructure and
risk contract, point-in-time validation, and implementation. Do not build
speculative non-equity adapters or abstractions.

## External consumer: AI agent harness

Responsibilities:

- research and contextual reasoning;
- explainable recommendations;
- researching the default point-in-time Nifty 100 cohort or an explicitly
  supplied supported listed equity;
- reviewing supported listed-equity holdings through a read-only portfolio
  snapshot;
- monitoring existing swing trades; and
- reviewing completed swing trades.

It must never:

- read raw OHLC data directly;
- calculate indicators;
- calculate or infer market structure;
- perform deterministic market calculations; or
- silently manufacture missing facts.

It reasons only over versioned, structured facts supplied by this tool.

For historical validation of AI reasoning, the harness may consume a sealed,
point-in-time research packet and emit a versioned structured decision before
future data is revealed. The deterministic simulator then reveals and scores
the later outcome under approved execution, cost, and risk rules. This sampled
replay evaluates the consumer boundary; it does not move LLM reasoning into the
deterministic core or replace reproducible full-history baselines. Model version,
prompt/contract version, contamination risk, and out-of-sample status remain
part of the evidence.

## This repository: Swing Trading Research Tool

Responsibilities:

- historical and live market data;
- deterministic analysis and calculations;
- backtesting;
- rule and data validation; and
- returning structured facts with timestamps and provenance.

It must never:

- place or manage broker orders;
- make autonomous buy or sell decisions;
- generate opinions; or
- perform LLM-style reasoning.

## Locked pipeline

```text
Higher-level universe policy
  -> default point-in-time Nifty 50 + Nifty Next 50
     or an explicitly supplied supported listed equity
  -> bounded canonical listed-equity cohort
  -> Market regime
  -> Sector analysis
  -> Market structure
  -> Price action
  -> Liquidity / SMC
  -> Volume
  -> Relative strength
  -> Risk validation
  -> Structured research facts

External AI boundary:

Structured research facts
  -> AI reasoning
  -> Explainable recommendation or no-trade decision
```

## Locked modules

1. Market Regime
2. Sector Analysis
3. Market Structure
4. Price Action
5. Liquidity / SMC
6. Volume
7. Relative Strength
8. Risk Validation
9. Trade Recommendation Support
10. Portfolio Monitoring

No module should be added without an explicit architecture decision.

## Risk-first decision support

Capital preservation, position risk, aggregate portfolio exposure, drawdown,
liquidity, gaps, costs, slippage, invalidation, and insufficient evidence are
first-class facts. The deterministic tool owns their calculations and policy
versions; the external AI may explain them but cannot override a hard risk
failure or manufacture a position size. Exact risk limits, holding horizon, and
bar frequency must be approved in the relevant module specification rather than
being inferred from conversation.

Portfolio analysis is read-only and limited to supported listed-equity holdings.
The point-in-time Nifty 100 is the default product focus; an explicitly supplied
stock outside it requires the same canonical identity and capability-specific
evidence as every other supported instrument. Portfolio analysis may assess
evidence, concentration, risk, performance, and candidate hold/exit conditions,
but it does not place or manage broker orders and is not long-term portfolio
advisory.

## Indicator minimization policy

Indicators are not default research inputs. Prefer directly observable,
explainable price action, market structure, liquidity, volume, relative
strength, event, and risk facts when they answer the research question.

An indicator may be introduced only when an approved module specification
demonstrates that it is mandatory for a defined decision, documents its exact
formula and version, identifies its point-in-time inputs, and includes a
validation reason that simpler facts cannot satisfy the requirement. Indicator
proliferation, redundant transforms, and unvalidated signal combinations are
out of scope. The external AI harness never computes indicators itself; it may
reason over an explicitly versioned indicator fact supplied by the tool.

Trade Recommendation Support produces validated evidence, candidate plans, and
risk facts. The external AI harness owns the contextual recommendation.

## Domain boundaries

Market Structure owns:

- swing highs and lows;
- HH, HL, LH, and LL;
- trend;
- BOS; and
- CHoCH.

Liquidity / SMC owns only:

- liquidity;
- order blocks; and
- fair-value gaps.

## Module contract boundary

Before a module is implemented or activated, its approved contract must define:

1. purpose;
2. business requirements;
3. inputs;
4. outputs;
5. deterministic rules;
6. edge cases;
7. validation approach;
8. acceptance criteria; and
9. integration boundary.

For a reusable listed-equity feature, the input contract must also state the
maximum cohort bound, canonical ISIN/exchange/effective-symbol identity,
required provider mappings, and required data-capability profile. Index
membership may appear only in the composing universe policy or in a
deliberately index-specific versioned contract. Unsupported capability and
insufficient evidence must remain distinct from malformed input and from a
successful fact.

A module advances only after its requirements and validation are complete.

Prior repositories are non-authoritative references. Their concepts may be
studied, but logic must be independently specified, tested, and validated for
this project's equity-only scope before adoption.
