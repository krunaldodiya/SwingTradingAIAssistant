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

Sprint 3 is complete in seven coherent slices. It proves the controlled
single-symbol persistent workflow, zero-request repeat, retained coverage,
bounded `1m`, local session-aware `1d`, clean installation, and sanitized JSON.
See the [Sprint 3 closeout](docs/sprints/sprint-3.md) for accepted revisions,
gate evidence, and held release boundaries.

Sprint 3 adds an installable single-symbol preview for `NSE_EQ` `RELIANCE`:
`market-data download`, `coverage`, and bounded `query` commands for verified
one-minute data and locally derived daily OHLCV. The canonical store remains
immutable monthly Parquet with a metadata-only DuckDB catalog at an explicit
external root. This is an offline/controlled preview, not a live-release or
multi-symbol Nifty 50 claim.

The package composition deliberately has no built-in exchange-calendar feed.
The persistent download service accepts authoritative, provenance-complete NSE
schedule evidence as an injected dependency; the default CLI fails closed with
`SCHEDULE_EVIDENCE_UNAVAILABLE` until an approved application composition
supplies it. Coverage and query are provider-free and use only retained
point-in-time evidence.

Research modules, strategy rules, recommendations, and broker execution are not
implemented.

## Persistent RELIANCE preview quickstart

Requirements:

- Python 3.11 or newer;
- [`uv`](https://docs.astral.sh/uv/); and
- only for the diagnostic or a separately authorized live attempt, a current
  Upstox access token or read-only Analytics Token. The controlled proof below
  needs no credential.

Install the locked development environment:

```bash
uv sync --extra dev
```

Run the credential-free controlled end-to-end proof. It creates an external
disposable root, supplies deterministic authoritative schedule and provider
responses, persists verified one-minute data, repeats with zero requests, and
then exercises coverage plus `1m` and `1d` queries:

```bash
uv run --extra dev pytest \
  tests/market_data/test_sprint3_quickstart.py \
  --no-cov -q
```

Prove the distributable artifact independently of the source checkout:

```bash
uv build
uv venv /var/tmp/swing-preview-venv
uv pip install --python /var/tmp/swing-preview-venv/bin/python \
  dist/swing_trading_ai_assistant-0.1.0-py3-none-any.whl
/var/tmp/swing-preview-venv/bin/market-data --help
```

For an application composition that supplies the approved schedule source and
environment-only provider credential, the closed-range workflow is:

```bash
uv run market-data download \
  --segment NSE_EQ --symbol RELIANCE \
  --from 2026-07-01 --to 2026-07-31 \
  --storage-root /var/tmp/swing-market-data --output json

uv run market-data coverage \
  --segment NSE_EQ --symbol RELIANCE \
  --from 2026-07-01 --to 2026-07-31 \
  --storage-root /var/tmp/swing-market-data --output json

uv run market-data query \
  --segment NSE_EQ --symbol RELIANCE \
  --from 2026-07-01 --to 2026-07-01 --timeframe 1m \
  --fields ts,open,high,low,close,volume --max-rows 1000 \
  --storage-root /var/tmp/swing-market-data --output json

uv run market-data query \
  --segment NSE_EQ --symbol RELIANCE \
  --from 2026-07-01 --to 2026-07-31 --timeframe 1d \
  --fields ts,open,high,low,close,volume --max-rows 31 \
  --storage-root /var/tmp/swing-market-data --output json
```

Dates are inclusive and must describe closed months. The storage root must be
an explicit absolute path outside the source tree. Read the JSON `status`,
`failure`, and typed month evidence before retrying. Do not edit or delete
catalog, manifest, schedule, snapshot, or Parquet files to repair an error;
retain the root, correct the missing dependency or unsafe path, and rerun the
same command. A verified repeat reports zero provider attempts. `1d` is derived
only from complete authoritative sessions in verified `1m` data.

The controlled proof contains no credential or private market data. A real
closed-range Upstox attempt remains a separate, explicitly authorized gate, so
passing this quickstart must not be described as live release readiness.

## Run the Upstox diagnostic

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
