# Swing Trading Research Tool for AI Assistants

This repository is building a trustworthy, deterministic research and analysis
tool for point-in-time Nifty 50 equity swing trading. It supplies structured,
traceable market facts to an external AI assistant so the assistant can explain
research, compare setups, monitor supported holdings, and return an explicit
`NO_TRADE` result when evidence is insufficient.

The objective is capital preservation, consistency, low drawdown, explainable
high-quality setups, and repeatability—not maximum returns or frequent trades.

## What this project is—and is not

The product has two strict layers:

1. **This repository: deterministic research tool.** It owns point-in-time data,
   validation, calculations, backtesting, risk evidence, timestamps, and
   provenance.
2. **External AI assistant.** It consumes versioned structured facts and owns
   contextual reasoning and explanation. It must not invent missing facts or
   silently recompute them from raw OHLC data.

This repository is not an autonomous trading bot. It does not place broker
orders, guarantee returns, or currently support intraday trading, futures,
options, crypto, long-term investing, or stocks outside the point-in-time Nifty
50 universe.

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

The planned product includes reproducible market-data ingestion, deterministic
research modules, bias-aware backtesting, risk validation, structured facts,
and read-only monitoring of supported Nifty 50 equity holdings. Each module is
specified, implemented, and validated separately in pipeline order.

## Current implementation status

The repository is still in the market-data foundation phase. It contains
deterministic building blocks for Upstox instrument resolution and historical
requests, monthly planning, bounded retries and rate limiting, schedule-aware
validation, immutable Parquet publication, DuckDB cataloging and direct-Parquet
queries, recovery, idempotent resume, and provenance.

Sprint 2 closed at **21/24 executable tasks (87.5%)**. Its offline correctness
and recovery evidence is substantial, but Milestone 2 remains **blocked / not
accepted** until the carried-over benchmark artifact, threshold decision, and
one authorized live comparison are completed. See the
[Sprint 2 closeout](docs/sprints/sprint-2-closeout.md) for the exact evidence and
remaining work.

The public `market-data` CLI currently exposes only `probe-upstox`, a
credential-safe, non-persistent provider diagnostic. It does **not** expose the
planned persistent `market-data download` workflow yet. Therefore a successful
probe proves catalog resolution, authentication, endpoint access, and response
shape—not downloader completion or stored-data correctness.

Research modules, strategy rules, recommendations, and broker execution are not
implemented.

## Run the Upstox diagnostic

Requirements:

- Python 3.11 or newer;
- [`uv`](https://docs.astral.sh/uv/); and
- a current Upstox access token or read-only Analytics Token.

Install the locked environment:

```bash
uv sync --extra dev
```

Create a local `.env` from `.env.example` and set the token:

```dotenv
UPSTOX_ACCESS_TOKEN=your-current-token
```

Run the diagnostic with its default recent date window:

```bash
uv run market-data probe-upstox \
  --segment NSE_EQ \
  --symbol RELIANCE
```

Or supply real ISO dates explicitly:

```bash
uv run market-data probe-upstox \
  --segment NSE_EQ \
  --symbol RELIANCE \
  --from 2026-08-03 \
  --to 2026-08-03
```

`YYYY-MM-DD` describes the required format; do not pass those letters literally.
Use `uv run market-data probe-upstox --help` for the current options.

The diagnostic keeps candles in memory and emits only HTTP status, row count,
first/last timestamp, and schema validity. It never prints the token or writes
candle data. Provider and credential failures are intentionally reduced to a
sanitized `probe_failed:<ErrorType>` message.

## Development

Run the deterministic quality gate from the repository root:

```bash
uv run --extra dev ruff format --check . && \
uv run --extra dev ruff check . && \
uv run --extra dev pyright && \
uv run --extra dev vulture src --min-confidence 80 && \
uv run --extra dev pytest
```

Project work follows strict TDD, focused smoke checks before expensive suites,
independent review, and hosted CI. Credentials, broker sessions, generated
datasets, and private market data must never be committed.

## Project documentation

- [Architecture freeze](docs/architecture-freeze-v1.md): authoritative mission,
  module boundaries, and exclusions.
- [Roadmap](docs/roadmap.md): phased product direction.
- [Data foundation and Upstox ingestion plan](docs/plans/01-data-foundation-and-upstox-ingestion.md):
  downloader milestones and acceptance gates.
- [Development workflow](docs/development-workflow.md): Agile, TDD, review, and
  publication controls.
- [Engineering standards](docs/engineering-standards.md): correctness,
  performance, security, and testing rules.
- [Sprint records](docs/sprints/README.md): committed work and retrospectives.
- [Project notes](docs/notes/README.md): curated decisions, hypotheses, and
  external-reference assessments.
