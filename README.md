# Swing Trading AI Assistant

An explainable decision-support system for identifying, validating, monitoring,
and reviewing swing-trading opportunities in Nifty 50 equity stocks.

The system optimizes for capital preservation, consistency, low drawdown,
high-quality setups, and repeatability. It is not an execution bot and does not
cover intraday trading, derivatives, or long-term investing.

## Architecture

The product is split into two strict layers:

1. **Swing Trading Research Tool** — reads market data, performs deterministic
   calculations, backtests rules, validates results, and returns structured facts.
2. **AI Swing Trading Assistant** — reasons only over those structured facts to
   explain, recommend, monitor, and review trades.

The LLM must not calculate indicators, infer market structure from raw OHLC data,
or invent missing market facts.

## Locked research pipeline

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

See [docs/architecture-freeze-v1.md](docs/architecture-freeze-v1.md) for the
authoritative scope and [docs/roadmap.md](docs/roadmap.md) for the initial plan.

## Current status

The repository is at foundation stage. Architecture Freeze v1.0 is documented;
no technology stack, data provider, trading thresholds, or strategy rules have
been selected yet.

