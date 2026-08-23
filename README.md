# Swing Trading Research Tool for AI Assistants

This repository is building a trustworthy, deterministic research and analysis
tool for listed-equity swing trading. Product research, qualification, and
default workflows focus on the point-in-time Nifty 50 plus Nifty Next 50 (the
Nifty 100). It supplies structured, traceable market facts to an external AI
assistant so the assistant can explain research, compare setups, monitor
supported holdings, and return an explicit `NO_TRADE`, unsupported, or
insufficient-evidence result.

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
orders, guarantee returns, or support intraday trading, futures, options,
crypto, long-term investing, or a generic multi-asset platform. Explicitly
supplied listed stocks outside the Nifty 100 may use a capability only when
their canonical identity and that capability's required evidence are supported;
they are not the primary roadmap, qualification, or default-workflow focus.

## Locked research pipeline

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

External boundary:

Structured research facts
  -> AI reasoning
  -> Explainable recommendation or no-trade decision
```

Universe selection and point-in-time index membership are higher-level policy.
Reusable feature cores consume explicit bounded canonical equity identities and
declare their required data capabilities; they return unsupported or
insufficient evidence instead of deciding index membership.

The planned product includes reproducible market-data ingestion, deterministic
research modules, bias-aware backtesting, risk validation, structured facts,
and read-only monitoring of supported listed-equity holdings. Default discovery,
research qualification, and validation concentrate on the point-in-time Nifty
100. Each module is specified, implemented, and validated separately in
pipeline order.

## Current implementation status

The repository contains the Nifty 50 market-data foundation and the first two
provider-free research cores. Delivered behavior includes:

- the persistent downloader-v1 workflow for one, several, or all retained
  point-in-time Nifty 50 members, with Upstox raw historical/current candles,
  bounded shared resources, immutable monthly/provisional storage, provider-free
  coverage and `1m` through `1d` queries, and point-in-time universe, schedule,
  instrument, and corporate-action evidence;
- the Plan-19 current supplied-cohort path for bounded current price/volume
  facts and immutable temporal-availability records;
- the provider-neutral Plan-21 corporate-action screen, merged through PR #128
  as `cdb9ab1c2796356a3e9f604bdd5aeb404cf7519b`,
  with an Upstox retained-snapshot adapter and explicit nonexhaustive coverage;
- the separate Issue-127 adjusted-daily MVP, merged through
  [PR #129](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/129)
  as `c530ae3d6dc43714a71c1f874fe81ecb6b4944c6`, using explicit
  `YFINANCE` / `ADJUSTED` selection and supplied
  `isin`/`project_symbol`/`provider_symbol` mappings without changing Upstox raw
  candles;
- the Issue-132 canonical explicit-stock adjusted-close input, merged through
  [PR #133](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/133)
  as `847dfbdf7b6114cb736e00abf9126c995d30e828`;
- implemented `nifty50-market-regime@v1` deterministic exact-50 reduction and
  its fail-closed evidence boundary;
- Sprint 11 current Market Regime V2 comparability, with
  [Issue #116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116)
  closed/completed after [PR #124](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/124)
  merged reviewed head `d56120fb5966dffea32207b59f1edf0673b2e51b` as
  `f03edf3690e34e25a57b58a15450129e3bf9a5e9`, with 296 focused tests,
  2,867 full tests, 91.03% coverage, Ruff, Pyright, Vulture, build, sealed
  no-network and live current-prospective smokes, hosted Quality/build, and
  GitGuardian passed; and
- implemented `nifty50-sector-participation@v1` provider-free exact-50
  aggregation over the same-pass Market Regime handoff and point-in-time opaque
  sector labels.

The Market Regime and Sector Participation implementations preserve their
frozen Nifty 50 V1 cardinalities and contracts. They do not establish an
observed live result, effectiveness, or instrument-agnostic support. The
adjusted-daily MVP likewise remains a supplied Plan-19/Nifty-50-composed
boundary with incomplete canonical listed-equity identity.

[Plan 23](docs/plans/23-instrument-agnostic-feature-boundary-and-coupling-audit.md)
owns separate future migrations toward reusable listed-equity feature
boundaries. It does not reinterpret historical exact-50 V1 evidence, reopen
completed Issues #125/#127/#132, or extend the delivered Sprint 11 V2
comparability semantics.
Sprint 12 / [Issue #117](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/117)
is **closed/completed** under
[Plan 24](docs/plans/24-current-supplied-cohort-sector-analysis-contract.md).
[PR #135](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/135)
merged exact reviewed head `b8c416709ebae82879c5dceae603b141b0dd1fa8`
as merge commit `4dfa8ecd1854aec4b4b2181cf2d0310072f65b49`.
Independent exact-revision quality review returned **APPROVE** and security
review returned **PASS**. Local gates passed 2,991 tests at 90.82% coverage,
Ruff format/check, Pyright, Vulture 80, and build; hosted Quality/build and
GitGuardian also passed. Issue #117 is closed and its Project item is **Done**.

The delivered slice preserves the source's literal NSE Indices `Industry`
field; it does not claim official `Sector` taxonomy, Industry-to-Sector mapping,
historical classification, supplied-cohort index membership, live
participation, effectiveness, recommendation, order placement, or authority to
publish raw/member evidence. The official parser smoke admitted the exact
current 100-row, 6,610-byte artifact with SHA-256
`5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85`;
that result is parser provenance only.

Sprint 13 / [Issue #118](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/118)
is **ACTIVE / IN PROGRESS** under
[Plan 25](docs/plans/25-current-supplied-cohort-event-notice-contract.md).
Its first working slice is one operator-acquired official NSE Equity `1D`
corporate-announcement CSV for owner-private current/prospective evidence.
Automated acquisition, general news, historical backfill, sentiment, and extra
providers or delivery surfaces remain later improvements.

Upstox remains primary for live/raw OHLCV and retained corporate-action
screening. yfinance is a separate adjusted-daily research provider, not a
silent fallback, live broker feed, or strict point-in-time authority.
`NSE_EQ` is an Upstox exchange-segment identifier, not a second NSE API
integration. A caller-supplied canonical universe snapshot establishes
historical Nifty 50 membership and sector provenance; it does not supply prices
or make network requests.

The package has no built-in exchange-calendar feed. Persistent market-data
workflows require provenance-complete supplied NSE schedule evidence and fail
closed when it is unavailable. Strategy rules, recommendations, and broker
execution are not implemented.


## Sprint 4 historical evidence census

The provider-free `historical-census` command consumes an explicit retained evidence seal and emits the canonical strict point-in-time census. It never downloads data. The retained Sprint 4 sample is classified `EXPLORATORY_DEVELOPMENT`; its result cannot support prediction, claimed accuracy, strategy or profitability acceptance, or a trade recommendation.

```bash
uv run historical-census \
  --seal /path/to/retained-nifty50-evidence-seal-v1.json \
  --evidence-seal-sha256 <64-hex-seal-file-digest> \
  --universe /path/to/nifty50-universe.json \
  --schedule /path/to/july-schedule.json \
  --schedule /path/to/august-schedule.json \
  --data-manifest /path/to/coverage-all50-provider-free.json \
  --observation-cutoff 2026-08-12T15:30:00Z \
  --code-sha <40-hex-git-sha> \
  --configuration-sha256 <64-hex-configuration-digest>
```

The command fails closed when the seal is missing or malformed and reports zero provider attempts on successful output. Exact semantics and evidence limitations are frozen in [Plan 10](docs/plans/10-five-session-opportunity-census-contract.md).

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

Credentials, broker sessions, generated datasets, and private market data must never be committed.

## Project documentation

- [Architecture freeze](docs/architecture-freeze-v1.md): authoritative mission,
  module boundaries, and exclusions.
- [Roadmap](docs/roadmap.md): phased product direction.
- [Data foundation and Upstox ingestion plan](docs/plans/01-data-foundation-and-upstox-ingestion.md):
  downloader milestones and acceptance gates.
- [Sprint records](docs/sprints/README.md): committed work and retrospectives.
- [Plan 23 — Instrument-agnostic feature boundary and coupling audit](docs/plans/23-instrument-agnostic-feature-boundary-and-coupling-audit.md):
  owner decision, current coupling evidence, and ordered remediation slices.
- [Project notes](docs/notes/README.md): curated decisions, hypotheses, and
  external-reference assessments.
