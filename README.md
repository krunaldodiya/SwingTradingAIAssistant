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

The repository is completing the market-data foundation before research modules
begin. The downloader-v1 candidate is symbol-agnostic for retained point-in-time
Nifty 50 members and supports one symbol, several symbols, or the full retained
universe. It provides:

- Upstox instrument resolution plus historical and current-session candle
  requests behind provider-independent contracts;
- bounded shared rate limiting, `1..8` workers, retries, output, memory, and
  date ranges;
- immutable monthly Parquet, provisional current-month snapshots, a
  metadata-only DuckDB catalog, recovery, and zero-request resume;
- provider-free coverage and bounded queries for `1m`, `3m`, `5m`, `15m`,
  `30m`, `1h`, and `1d` data; and
- immutable point-in-time universe, schedule, instrument, and Upstox
  corporate-action evidence with explicit raw/adjusted/symbol-change states.

Sprint 2 closed at **21/24 executable tasks (87.5%)** after establishing
immutable Parquet publication. Its carried evidence is now implemented in the
Sprint 3 release chain, but Milestone 2 remains **blocked / not accepted** until
the exact candidates pass publication review and merge. The sprint is extended
through that gate. Its public surface is `market-data download`, `coverage`, and
bounded `query` commands over the same versioned application contracts.

Upstox is the only runtime candle and corporate-action provider.
`NSE_EQ` is an Upstox exchange-segment identifier, not a second NSE API
integration. A caller-
supplied canonical universe snapshot establishes historical Nifty 50 membership
and sector provenance; it does not supply prices or make network requests.

The package deliberately has no built-in exchange-calendar feed. The persistent
download service accepts authoritative, provenance-complete NSE schedule
evidence as an injected dependency. The default CLI accepts the same canonical
evidence through `--schedule-file` and otherwise fails closed with
`SCHEDULE_EVIDENCE_UNAVAILABLE`. Coverage and query are provider-free and use
only retained point-in-time evidence.

Research modules, strategy rules, recommendations, and broker execution are not
implemented.

## Downloader v1 quickstart

Requirements:

- Python 3.11 or newer;
- [`uv`](https://docs.astral.sh/uv/); and
- for real provider requests, a current Upstox access token or read-only
  Analytics Token supplied through `UPSTOX_ACCESS_TOKEN`. The controlled proof
  below needs no credential.

Install the locked development environment:

```bash
uv sync --extra dev
```

Run the credential-free controlled end-to-end proof. It persists verified
one-minute data, repeats with zero requests, and exercises provider-free
coverage plus `1m`, `5m`, and `1d` queries:

```bash
uv run --extra dev pytest \
  tests/market_data/test_sprint3_quickstart.py \
  --no-cov -q
```

Prove the distributable artifact independently of the source checkout. Use a
fresh path for each proof:

```bash
uv build
uv venv /var/tmp/swing-downloader-v1-venv
uv pip install --python /var/tmp/swing-downloader-v1-venv/bin/python \
  dist/swing_trading_ai_assistant-0.1.0-py3-none-any.whl
/var/tmp/swing-downloader-v1-venv/bin/market-data --help
```

For approved canonical universe/schedule files and an environment-only Upstox
credential, a bounded multi-symbol closed-month workflow is:

```bash
uv run market-data download \
  --segment NSE_EQ --symbols RELIANCE,SBIN,TCS --workers 3 \
  --from 2026-07-01 --to 2026-07-31 \
  --universe-file /var/tmp/nifty50-universe.json \
  --universe-as-of 2026-07-31 \
  --schedule-file /var/tmp/nse-schedule.json \
  --output json

uv run market-data coverage \
  --segment NSE_EQ --symbols RELIANCE,SBIN,TCS --workers 3 \
  --from 2026-07-01 --to 2026-07-31 \
  --output json

uv run market-data query \
  --segment NSE_EQ --symbols RELIANCE,SBIN,TCS --workers 3 \
  --from 2026-07-01 --to 2026-07-01 --timeframe 1m \
  --fields ts,open,high,low,close,volume --max-rows 1000 \
  --output json

uv run market-data query \
  --segment NSE_EQ --symbol SBIN \
  --from 2026-07-01 --to 2026-07-01 --timeframe 15m \
  --fields ts,open,high,low,close,volume --max-rows 100 \
  --output json
```

Use `--universe nifty50-current` instead of `--symbols` to operate on all 50
members retained for the request's point-in-time cutoff. Dates are inclusive.
Persistent commands default to `~/SwingTradingAIAssistantData` and create that
directory recursively when it is missing. Override it with
`--storage-root /absolute/path`; a missing override is also created recursively.
Read each JSON `outcome`, per-symbol result, and typed month evidence before
retrying. Never manually edit catalog, manifest, schedule, snapshot, or Parquet
files; correct the dependency or unsafe path and rerun the same command.
Verified repeats and all coverage/query commands make zero provider requests.

### Current month through the latest completed minute

A range ending in the current month is supported. Closed months remain
immutable; the current month is explicitly `PROVISIONAL` and advances only
through the latest completed authoritative session minute. A later invocation
fetches only the suffix after the last persisted point and atomically
publishes a new snapshot rather than overwriting the previously retained one.

```bash
uv run market-data download \
  --segment NSE_EQ --symbol RELIANCE \
  --from 2026-08-01 --to 2026-08-12 \
  --schedule-file /var/tmp/nse-current-schedule.json \
  --output json

uv run market-data query \
  --segment NSE_EQ --symbol RELIANCE \
  --from 2026-08-01 --to 2026-08-12 --timeframe 5m \
  --fields ts,open,high,low,close,volume --max-rows 5000 \
  --output json
```

If the range crosses from closed months into the current month, also pass
`--closed-schedule-file` for the closed-month evidence. Coverage and query stay
available while another process owns the exclusive writer; they read the last
atomically published snapshot. No current month is falsely labelled as a fully
verified closed month.

`1d` and the approved higher intraday views are derived only from complete
authoritative sessions in verified/provisional `1m` evidence. They never make a
second historical request. Raw candles are never rewritten for corporate
actions; the Python provenance boundary reports adjusted prices and historical
symbol changes as unsupported until separate versioned specifications exist.

The controlled proof contains no credential or private market data. The Sprint
3 release record distinguishes deterministic tests, sanitized Upstox live
evidence, clean package installation, and hosted CI; none substitutes for
another.

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

Use the native pytest feedback profiles during strict TDD:

```bash
# Focused red/green (replace the placeholder with one pytest node ID)
uv run --extra dev pytest <test-node> --no-cov -q -x

# Affected tests (replace the placeholder with relevant test paths)
uv run --extra dev pytest <test-paths> --no-cov -q

# Authoritative full profile with configured branch coverage
uv run --extra dev pytest
```

The focused and affected profiles are local feedback only and never merge
evidence. Do not set `PYTEST_ADDOPTS` to disable coverage. The full five-tool
gate above and hosted CI remain mandatory; independent review remains
risk-triggered by the development workflow. Credentials, broker sessions,
generated datasets, and private market data must never be committed.

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
