# Swing Trading Research Tool for AI Assistants

An agent-agnostic research and analysis tool for Nifty 50 equity swing trading.
It gives AI assistants trustworthy, structured market facts they can use to
research opportunities, reason about setups, support development, monitor
positions, and review outcomes.

The system optimizes for capital preservation, consistency, low drawdown,
high-quality setups, and repeatability. It is not an execution bot, a collection
of fixed buy/sell scripts, or an AI-agent implementation. It does not cover
intraday trading, derivatives, or long-term investing.

## Architecture

The wider product has two strict layers:

1. **This repository: Swing Trading Research Tool** — reads market data, performs
   deterministic calculations, backtests and validates research rules, and
   exposes versioned structured facts with evidence and provenance.
2. **External AI agent harness** — consumes those facts to research, reason,
   explain, recommend, monitor, review, or help develop trading logic.

The tool must not place orders or turn deterministic facts into an autonomous
buy/sell decision. The consuming AI must not recalculate facts from raw OHLC data
or invent missing evidence.

The eventual integration surface may be an API, CLI, MCP server, or a combination.
That choice remains open until the data and domain contracts are specified.

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
  -> Structured research facts

External boundary:

Structured research facts
  -> AI reasoning
  -> Explainable recommendation or no-trade decision
```

See [docs/architecture-freeze-v1.md](docs/architecture-freeze-v1.md) for the
authoritative scope, [docs/reference-repositories.md](docs/reference-repositories.md)
for prior-work references, and [docs/roadmap.md](docs/roadmap.md) for the initial
roadmap. The first executable workstream is documented in
[Plan 01: Data Foundation and Upstox Ingestion](docs/plans/01-data-foundation-and-upstox-ingestion.md).
Useful brainstorming, design rationale, alternatives, and open questions are
curated in the [project notes](docs/notes/README.md). The [development
workflow](docs/development-workflow.md) defines Agile issue handling, strict
TDD, model routing, and review gates.

Development is organized into one-week sprints with a Linear-backed hierarchy
of saga → epic → story → atomic task. Sprint goals and retrospectives are
preserved under [docs/sprints](docs/sprints/README.md); all work completed or
actively worked so far spans Sprint 0 and Sprint 1.

## Current status

The repository is in its data-foundation phase. Sprint 0 completed a
credential-safe, non-persistent instrument capability probe against Upstox
Historical Candle V3. Sprint 1 then implemented the deliberately narrow
persistent one-minute candle storage increment. The caller supplies a segment
and symbol, which are resolved through the Upstox master instrument catalog.
Indicators, strategies, and trading rules remain later roadmap work.

The live RELIANCE proof of capability returned 375 one-minute candles for
2026-08-03 (09:15 through 15:29 Asia/Kolkata) with a valid seven-field schema.
The runtime accepts Upstox's one-year read-only Analytics Token through the same
portable environment variable as a standard OAuth token; production code has
no browser, TOTP, or operating-system Keychain dependency.

Run deterministic checks with:

```bash
uv run pytest
```

Create a local `.env` from `.env.example`, set a current Upstox token, and run
the diagnostic:

```dotenv
UPSTOX_ACCESS_TOKEN=your-current-token
```

```bash
uv run market-data probe-upstox \
  --segment NSE_EQ \
  --symbol RELIANCE \
  --from YYYY-MM-DD \
  --to YYYY-MM-DD
```

The command keeps all candles in memory and emits only HTTP status, row count,
first/last timestamp, and schema validity. It never prints the token or writes
candle data. `.env` is ignored by Git; `.env.example` contains variable names
only. The application has no operating-system keychain dependency.
