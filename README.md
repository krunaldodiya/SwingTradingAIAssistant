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

## Developing with an AI agent

Start with [AGENTS.md](AGENTS.md) and the [mandatory project instructions](docs/mandatory-agent-instructions.md).
The [portable development workflow](docs/agent-workflow.md) applies to Pi,
Oh My Pi, Codex, OpenCode, and other capable harnesses. If your harness does not
auto-load repository instructions, explicitly read those links before work.
No particular harness, model, terminal manager, or unrestricted permission mode
is required.

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
is **closed/completed** under
[Plan 25](docs/plans/25-current-supplied-cohort-event-notice-contract.md).
[PR #137](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/137)
merged independently reviewed head `2b65aa46f3f67552bf600675c6f1a5c09d363e12`
as merge commit `75ca9c3d3302f6d0a46ac772099c7b4d65e041c3`.
Independent functional review returned **APPROVE** and security review returned
**PASS**. Exact committed local gates passed Ruff format/check, Pyright 0/0,
Vulture 80, `uv build`, `git diff --check`, and 3,038 tests at 90.68%
coverage; hosted Quality/build and GitGuardian passed on the reviewed head.
Issue #118 is closed, its Delivery Project item is **Done**, and it is the
Sprint 13 milestone.

The delivered first slice accepts one operator-acquired, unfiltered official
NSE Equity `1D` corporate-announcement CSV only for attributed owner-private
personal/noncommercial local use. It binds the exact supplied canonical cohort,
provenance, typed failures, immutable archive-owned `known_at`, and
retain-before-return behavior; it has no automated collection, attachment fetch,
redistribution, sentiment, recommendation, signal, or order. The exact
8,016-byte, 20-row official artifact has SHA-256
`a395f454dd39b3befd14ac2f1b3e0dce312c8ba0441098b80e596be172749210`.
Production parse/project/real `StorageRootLease` archive-and-retry admitted one
`GODREJCP` / `INE102D01028` notice and returned
`NO_MATCHING_NOTICE_IN_SNAPSHOT` for `TCS` / `INE467B01029`; this is
parser/projection/retention evidence only, not source completeness, live
participation, historical coverage, commercial permission, correction lineage,
recommendation quality, or effectiveness.

Plan-25 event evidence remains prospectively archived and unavailable event
history remains explicit. Sprint 14 / [Issue #119](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119)
is **DELIVERED/CLOSED — PR #140 MERGED; ISSUE #119 CLOSED/COMPLETED; DELIVERY PROJECT ITEM DONE; SPRINT 14 MILESTONE; EXACT REVIEWED HEAD APPROVED/PASSED; ALL REQUIRED CURRENT SMOKES, 852 FOCUSED, 3,400 FULL AT 89.53% COVERAGE, ALL EXACT-CURRENT LOCAL GATES, HOSTED QUALITY/BUILD, AND GITGUARDIAN PASSED** under
[Plan 27](docs/plans/27-current-same-pass-market-regime-contract.md). The owner
selected the current-only same-pass correction after operational evidence showed
zero usable Plan-20 21-object prospective inputs.

Official acquisition automation retained and validated the current exact
schedule, mapping, Industry, event, raw, and Plan-21 evidence. Fresh post-close
evidence passed with schedule SHA-256
`f50e7853ce91e3868678b40b5ece79beea0aa469317d348129e96b1c3b71b0a0`,
Industry SHA-256
`1a40e33a0febf458986a178bc76f7b0051f163718f2a8bc11a726ba70a39c0a9`,
and Event SHA-256
`fe77c222ccf73c9a90b7c94641f6e39055c5a4956467729fabda4c8a9ea4b297`.
The final 14-file focused portfolio passed **852 tests** with `--no-cov`.
The strict one-lease post-close `RELIANCE` positive passed for the 2026-08-26
decision session: 21 raw bars; Market Regime, Industry, and Packet `OBSERVED`;
partial `NOT_APPLICABLE`; Plan 21 `SCREENED`; Plan 22 `SUCCESS`; and guarded
retries preserved exact bytes, identities, and original times.

The mandatory Aug-27 market-hours `RELIANCE` positive passed on frozen
fingerprint
`61d5574bc6ae034cab471d3cc30b1b6d7aa891859c6c48c6eaf60f65224c541d`
during the actual active session. The decision cutoff was
`2026-08-27T04:29:06.612060Z` (`09:59:06` IST), and the effect deadline was
`2026-08-27T04:28:36.612060Z`. Composed schedule SHA-256
`fb4e60b4c9e62887211cd5083403a4b0dfca2ab4b95f1c7415b27c0c8e1ac9ae`
defined 2026-08-27 as `REGULAR`, 09:15–15:30 IST, with S0 2026-07-29 and S20
2026-08-26; the 2026-08-27 mapping observation was
`02e150b0b910f9ebe825b1c77f48126e4a0046073bf24ae767211fe66480bbf3`.

Raw was 21/21 `OBSERVED`; Plan 21 was `SCREENED`; live Plan 22 was `SUCCESS`
before the deadline; Market Data, Market Regime, Industry, and Packet were
`OBSERVED`; Event was `RETAINED`. Packet identity SHA-256 was
`cc3619cddcd2a35c73500947f40db863a5cb56df5a6aa377c2b0d91261556474`,
and context identity SHA-256 was
`e8b0371527994b39d6c905967c7814fce792fee627221cfd54cc51f65285153a`.
The requested partial was truthfully `UNAVAILABLE` /
`PARTIAL_MEMBER_MISSING` with zero rows, separately labelled
`PARTIAL_CURRENT_SESSION`, excluded from the completed grid and Market Regime,
nonfatal, and never substituted. Exact retries preserved bytes, identities, and
original times and caused zero effects; source remained unchanged and all
resources were closed.

Current Market Regime availability will not depend on prior tool runs. For each
bounded cutoff it resolves the latest 21 completed official sessions, admits
exact approved raw evidence available now, and retains the full grid with
truthful current `known_at` and `CURRENT_SAME_PASS_ONLY`; 0/1/7/30-day inactivity
cannot itself cause insufficiency. During market hours S20 is the prior completed
session; after the official close it may be today. An optional separately
labelled `PARTIAL_CURRENT_SESSION` is provisional context only and never a
completed close, Market Regime/Industry input, historical claim, signal,
recommendation, or order.

Plan-26 packet `@v1` is unpublished WIP superseded before delivery by Packet V2;
its 101 focused-test result remains historical WIP/repair evidence only. It will
not ship and no alias is authorized.

PR #140's two P2 blockers are fixed on the exact current source candidate 66-path
set. Active-session partial acquisition now requires canonical identity and an
effective provider mapping valid on the active date before any partial query;
expired canonical or mapping validity performs zero partial queries. Industry V2
preserves the schema-specific legacy/current source URL and Packet attribution.

The mandatory Aug-27 market-hours `RELIANCE` positive rerun **PASSED** on exact
current source candidate 66-path fingerprint
`3940ffe433887360c2744507c4075ac2404ffcd1482b2799380d26776623229e` at cutoff
`2026-08-27T08:18:59Z`. Raw, Market Regime, Industry, and Packet were
`OBSERVED`; Plan 21 was `SCREENED`; Plan 22 was `SUCCESS`. Active-date canonical
and mapping validity passed before the partial path returned `UNAVAILABLE` /
`PARTIAL_MEMBER_MISSING` with zero rows. Industry and Packet retained the current
`nsearchives.nseindia.com` URL attribution. Exact retries preserved bytes,
identities, and original times and caused zero provider effects. The prior
post-close positive, earlier Aug-27 market-hours positive, genuine IRCTC
negative, and exact 66-path set remain preserved.

The exact-current full suite passed **3,400 tests at 89.53% total coverage**
against the **87%** threshold, and the 14-file focused portfolio passed 852 tests.
All exact-current local gates pass: Ruff format/check over 275 files, Pyright 0/0,
Vulture at 80%, `git diff --check`, `uv build` producing sdist and wheel, and clean
installed-wheel imports/runtime checks. Installed runtime identities are raw
`8d99ebe8781d48d6a45a331878ff3a730bd23237c152e5837797c003c71d047b`,
Industry V2 `e8e4c5408afe49e4f99484c0ab8a23cc897dfb3a34b84d00f7230405e7d93f29`,
Market Regime V3 `74928b2b190e0e676ebb88fd4df5ae3d3856edaf8a08694da325393543a3542a`,
and Packet V2 `a36e3f42a773f0d533dcfbc3726b83c800028bdf9f11bcae299e176eb020a4ea`.
PR #140 merged exact reviewed head
`0236942ced7127bc7220282d71e2cc35f0ff0c05` to `main` as merge commit
`893c2127fac6ab7a2f3f416e315aee26d8b06b4f`. Exact functional review returned
**APPROVE** and exact privacy/provenance review returned **PASS**. Hosted
Quality/build and GitGuardian passed. Issue #119 is closed/completed, its
Delivery Project item is **Done**, and this is the Sprint 14 milestone. Sprint
14 is delivered and closed as a research-only capability: no autonomous trading,
financial advice, guaranteed outcome, or broker order placement is delivered.

Ten review blockers are fixed locally without a new subsystem: the two PR #140
P2 fixes for active-date partial canonical/mapping validity and schema-specific
Industry/Packet URL attribution; late
completion-marker retry guards; zero-redirect enforcement; restored global
`ScheduleSession` kind compatibility with the exact `REGULAR`/`SPECIAL` gate
kept Plan-27-only; Industry V1 compatibility; Event legacy adoption; 62-day
month-start acquisition; pre-Plan-22 deadline enforcement; and corrected
Plan-24 wording.

The directory-edge `st_nlink` portability fix remains in place without
weakening leaf metadata checks; exact source-file checks remain enforced and
the dependent runtime identity manifests remain current. Plan-27 cohort bridge
mappings remain implemented, including truthful Plan-22 suppression after
upstream raw or screen insufficiency.

Owner platform boundary: the native supported target is POSIX-style macOS and
Linux with identical evidence guarantees. Native Windows is unsupported and not
claimed; Windows users use Linux through WSL2 or Docker. Hosted Quality/build and GitGuardian passed on the exact reviewed head.

The fresh current-byte genuine IRCTC production negative passed with the exact
`NO_TRADE` outcome: raw `INSUFFICIENT` / `RAW_ACQUISITION_UNAVAILABLE`; Market
Regime V3 insufficient; Plan 22 `NOT_ATTEMPTED` upstream; Industry V2
`UNSUPPORTED` with `MARKET_REGIME_UNAVAILABLE` and
`CLASSIFICATION_MEMBER_UNSUPPORTED`; and Packet insufficient with the exact
ledger, five null AI facts, and mandatory `NO_TRADE`. Guarded V3, Industry,
event, and Packet retries preserved exact bytes, identities, and original times.
All required current smokes have passed: the retained post-close `RELIANCE`
positive, mandatory market-hours `RELIANCE` positive, and genuine IRCTC
negative. The two positive modes remain separate; neither substitutes for the
other. The two PR #140 P2 blockers are fixed. All exact-current local gates pass. PR #140 is merged; exact reviews and hosted gates passed; Issue #119 is closed/completed; its Delivery Project item is Done; Sprint 14 is delivered/closed as the research-only milestone, with no autonomous trading or financial-advice claim.

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

## Structured daily OHLCV downloader

The installed distribution exposes one `equity_data_downloader` implementation
for bounded daily yfinance acquisition. Its CLI and Python API are adapters over
the same core; they do not create separate data sources. Parquet is the sole
persisted OHLCV source of truth. Persistent output never uses `Downloads` or an
arbitrary caller-selected file. Every invocation writes beneath one configured
structured-data root, whose default is:

```text
~/SwingTradingAIAssistantData
```

The derived layout is:

```text
adjusted_daily/provider=yfinance/request=<request-sha256>/data.parquet
```

DuckDB is the SQL query engine over those Parquet files; it is not a second
OHLCV copy. PyArrow is only the Parquet reader/writer library. Feather is not
used. yfinance's internal cookie/timezone SQLite cache is redirected beneath
`<storage-root>/.cache/yfinance`; it is auxiliary provider state, never an OHLCV
source or research input. The utility accepts between 1 and 100
explicit provider symbols and one inclusive date range in a multi-ticker
request. It does not infer exchange calendars, canonical mappings, decision
cutoffs, capture revisions, or project evidence, so the resulting dataset
remains transport/research data rather than automatically qualified
capture-forward evidence.

Dataset publication is direct and mode-gated: the canonical `data.parquet` name
is created without replacement as mode 0600, written and validated through its
held descriptor, file- and directory-synced, then committed to immutable mode
0400. Reuse rejects mode-0600 content unless the complete Parquet schema,
schema and field metadata, rows, and request identity validate exactly.
Successful recovery syncs and commits that same held inode, then rereads and
revalidates its exact physical digest and full table before returning.
Publication never renames or unlinks a path, so canonical-name substitution
fails without moving or deleting another file.

Install from PyPI:

```bash
python -m pip install swing-trading-ai-assistant
```

Download one or several stocks. Repeat `--symbol` for each provider symbol:

```bash
equity-data-download \
  --symbol SBIN.NS \
  --symbol RELIANCE.NS \
  --start 2026-08-01 \
  --end 2026-08-28
```

Use `--storage-root /absolute/path` to configure a different single structured
data root. The selected root must be an existing absolute directory owned by the
invoking user with mode `0700`; relative, symlinked, shared, or extra-linked
storage is rejected before any provider call. The complete derived dataset
remains under that root; there is no arbitrary output-file option.

Prices use yfinance's auto-adjusted OHLC semantics, while volume remains the
source-reported volume. The exact request identity binds normalized symbols and
dates, adjusted basis, yfinance release, fixed provider-call configuration, and
the exact Parquet schema/contract version. An existing dataset is reused only
after its owner, permissions, singleton identity, metadata, complete schema, and
all OHLCV values pass validation; `REUSED` performs zero provider requests and
zero file writes. A different or expanded request, provider version, call
configuration, or schema is a new coherent adjusted-price snapshot; the
downloader never appends a new adjustment vintage to old rows.

The same behavior is available as a Python API:

```python
from datetime import date

from equity_data_downloader import download_daily_ohlcv

receipt = download_daily_ohlcv(
    ("SBIN.NS", "RELIANCE.NS"),
    date(2026, 8, 1),
    date(2026, 8, 28),
)
```

The receipt reports the normalized symbols, request identity, requested period,
row count, per-symbol row counts, provider version, retrieval time, and derived
Parquet path under the shared root.



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
