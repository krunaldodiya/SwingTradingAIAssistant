# Architecture Freeze v1.0

## Goal

Build an AI Swing Trading Assistant that helps generate safe, consistent, and
explainable swing-trading opportunities in Nifty 50 equity stocks.

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

## Project A: AI Swing Trading Assistant

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

It reasons only over versioned, structured facts supplied by Project B.

## Project B: Swing Trading Research Tool

Responsibilities:

- historical and live market data;
- deterministic analysis and calculations;
- backtesting;
- rule and data validation; and
- returning structured facts with timestamps and provenance.

It must never:

- make buy or sell decisions;
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
  -> AI reasoning
  -> Recommendation
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
9. Trade Recommendation
10. Portfolio Monitoring

No module should be added without an explicit architecture decision.

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

