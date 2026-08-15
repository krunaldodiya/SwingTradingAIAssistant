# Architecture Freeze v1.0

## Goal

Build an agent-agnostic Swing Trading Research Tool that supplies trustworthy,
structured evidence to AI assistants researching safe, consistent, and
explainable swing-trading opportunities in Nifty 50 equity stocks.

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
- Generic equity research
- Stocks outside the Nifty 50 universe

These are v1 implementation and research exclusions. They do not require shared
infrastructure to encode equity assumptions unnecessarily.

## Instrument extensibility boundary

The architecture is extensible, while the product implementation is narrow.
Shared point-in-time data, provenance, validation, orchestration, backtesting,
risk-evidence, and application-contract primitives should avoid unnecessary
coupling to one broker, AI harness, or equity symbol convention when a current
equity requirement demonstrates the abstraction.

All v1 provider adapters, persisted datasets, market facts, validation,
research modules, backtests, and decision support remain limited to point-in-time
Nifty 50 equities. Equity fundamentals, corporate actions, promoter/shareholding
evidence, and exchange disclosures stay in explicit equity modules rather than
being presented as universal research concepts.

Supporting another instrument is a future architecture extension, not an
existing capability. It requires a separately approved scope decision,
instrument-specific data and risk contracts, point-in-time validation, and
separately authorized implementation. Do not build speculative adapters or
abstractions for futures, options, forex, crypto, or other instruments in v1.

## External consumer: AI agent harness

Responsibilities:

- research and contextual reasoning;
- explainable recommendations;
- researching any requested security inside the supported point-in-time Nifty
  50 universe;
- reviewing supported Nifty 50 holdings through a read-only portfolio snapshot;
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
Nifty 50 universe
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

Portfolio analysis is read-only and limited to supported Nifty 50 equity
holdings in v1. It may assess evidence, concentration, risk, performance, and
candidate hold/exit conditions, but it does not place or manage broker orders
and is not long-term portfolio advisory.

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

Before a module enters product scope, its approved contract must define:

1. purpose;
2. business requirements;
3. inputs;
4. outputs;
5. deterministic rules;
6. edge cases;
7. validation approach;
8. acceptance criteria; and
9. implementation boundary.

A module advances only after its requirements and validation are complete.

Prior repositories are non-authoritative references. Their concepts may be
studied, but logic must be independently specified, tested, and validated for
this project's equity-only scope before adoption.
