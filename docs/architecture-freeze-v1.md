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
- Long-term investing or portfolio advisory
- Generic equity research
- Stocks outside the Nifty 50 universe

## Generalized data boundary

The market-data ingestion foundation may catalog and persist factual candles for
indices, futures, and options when their individual adapter specifications and
entitlements are approved. This is a storage and provenance capability only.
The v1 research universe, locked pipeline, and any decision-support facts remain
limited to point-in-time Nifty 50 equities; stored F&O data must not silently
enter v1 research, analysis, backtests, or recommendations.

## External consumer: AI agent harness

Responsibilities:

- research and contextual reasoning;
- explainable recommendations;
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
future data is revealed. The deterministic simulator then scores that decision
using the approved execution and risk rules. This replay workflow validates the
consumer boundary; it does not move LLM reasoning into the deterministic core,
and it must document model-version, contamination, and out-of-sample limits.

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

Trade Recommendation Support produces validated evidence, candidate plans, and
risk facts. The external AI harness owns the contextual recommendation.

Portfolio and arbitrary-security analysis remain deliberately bounded in v1:
the tool may expose reusable contracts that can later support read-only
portfolio snapshots and additional supported securities, but the approved
research universe remains point-in-time Nifty 50 equities. Such expansions need
an explicit scope decision and specification before implementation.

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

## Development contract

Develop one module at a time. Before implementation, each module must define:

1. purpose;
2. business requirements;
3. inputs;
4. outputs;
5. deterministic rules;
6. edge cases;
7. validation approach;
8. acceptance criteria; and
9. implementation handoff.

A module advances only after its requirements and validation are complete.

Prior repositories are non-authoritative references. Their concepts may be
studied, but logic must be independently specified, tested, and validated for
this project's equity-only scope before adoption.
