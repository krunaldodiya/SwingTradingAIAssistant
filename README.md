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

## Research responsibilities and dependencies

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

The diagram describes product responsibilities, not a requirement that every
module succeed before any fact is visible.
[Issue #172](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/172)
governs the versioned migration to question-specific dependencies. Each fact
still requires its own identity, data, time, authority and integrity evidence;
unrelated missing context must not suppress an independently admitted result.

Universe selection and point-in-time index membership are higher-level policy.
Reusable feature cores consume explicit bounded canonical equity identities and
declare their required data capabilities; they return unsupported or
insufficient evidence instead of deciding index membership.

The planned product includes reproducible market-data ingestion, deterministic
research modules, bias-aware backtesting, risk validation, structured facts,
and read-only monitoring of supported listed-equity holdings. Default discovery,
research qualification, and validation concentrate on the point-in-time Nifty
100. Each module is specified, implemented, and validated separately; its
actual evidence dependencies govern execution rather than a universal chain.

## Current implementation status

**Current delivery baseline:** [PR #185](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/185)
merged on September 11, 2026; #183 and #184 are closed/completed. It delivered
source-preserving BharatStock acquisition, exact capture reuse and independently
available member/feature facts. Historical Yahoo records below remain historical
delivery evidence, not an active Yahoo acquisition path.

**Current working slice, not yet released:**
[#187](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/187)
adds an explicit V2 current-stock research result under #172. It keeps the
unversioned V1 command while independently admitting one-, two- and 21-session
BharatStock evidence into an integrated V5 envelope. Fresh regime, Industry and
event context are not acquired by this command; #188, #189 and #190 retain their
independent price-context, refresh and efficiency scope. This does not claim a
live PNB result, completed #172, new analytical modules or better trading returns.

Use V2 only with an explicit closed question:

```bash
market-data research-current --symbol PNB \
  --storage-root /absolute/private/research-root \
  --contract-version v2 --question PRICE_BEHAVIOR --output json
```

`LATEST_COMPLETED_CANDLE` requires one completed official session;
`PRICE_BEHAVIOR` requires geometry plus two consecutive completed official
sessions; `CURRENT_STRUCTURE` requires exactly 21 completed official sessions;
and `INTEGRATED_CURRENT_RESEARCH` requires all of those price facts plus
independently retained Event, Market Regime, and Industry evidence. Missing
context or a local long-window failure makes only its dependent question/fact
not ready. V2 emits readiness facts, not a recommendation; it preserves the
invocation selection time separately from later evidence acquisition time.

## Current raw price context (Issue #188 candidate)

The additive, unreleased `current-price-context@v1` command accepts an
owner-private closed request for an explicit 1–50 canonical NSE-equity cohort:

```bash
market-data price-context-current \
  --input-file /absolute/private/current-price-context-request.json \
  --storage-root /absolute/private/research-root \
  --output json
```

The equivalent SDK is
`research_current_price_context_v1(request, storage_root, acquire_missing=False)`.
Both the absolute request file and the existing absolute owner-private storage
root are required; neither belongs in a public repository or command output.
Retained-only is the default and does not read credentials or call a provider.
`--acquire-missing` is the explicit, serial, bounded opt-in; it still requires
already-retained exact calendar coverage for the selected 21 sessions and the
physical download plan, otherwise it returns a typed calendar-prerequisite
outcome before any provider or credential effect. Results use only retained
Upstox raw completed-session provenance (`UPSTOX / RAW / 1d-derived-from-retained-1m`),
not BharatStock or adjusted prices. Literal `INDUSTRY` participation is local:
missing or unsupported retained Industry evidence does not suppress independent
raw facts. The command emits research facts, never an analytic recommendation,
live/provider proof, or a claim that missing evidence is neutral.

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

**BharatStock source path — #184 / #183:**
[Issue #184](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/184)
governs the complete daily-provider cutover;
[Issue #183](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/183)
governs independent member outcomes.
[PR #185](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/185)
records exact-byte review, verification and delivery evidence.
The commands below describe source behavior, not a claimed PyPI publication.
See the [migration scope and evidence limits](docs/roadmap.md#bharatstock-migration-direction).
Historical Yahoo evidence retains its original labels and supported readers.

Upstox remains primary for live/raw OHLCV and retained corporate-action
screening. Direct BharatStock acquisition supplies separately labelled daily
prices under the accepted as-provided assumption, not a silent fallback, live
broker feed, total-return series, or strict point-in-time authority.
`NSE_EQ` is an Upstox exchange-segment identifier, not a second NSE API
integration. A caller-supplied canonical universe snapshot establishes
historical Nifty 50 membership and sector provenance; it does not supply prices
or make network requests.

Legacy persistent market-data commands require provenance-complete supplied NSE
schedule evidence and fail closed when it is unavailable. Current evidence
acquisition uses the explicitly approved NSE/Upstox composition policy, not a
generic exchange-calendar fallback. Strategy rules, recommendations, and broker
execution are not implemented.

## Single-stock current research candidate

[#186](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/186) adds
`current-stock-research@v1`; this candidate is not yet released or live-qualified.
Use an existing empty owner-private directory (`0700`), or an admitted private
storage root. The command does not create the root or repair permissions:

```bash
market-data research-current \
  --symbol PNB \
  --storage-root /absolute/private/research-root \
  --output json
```

A cold invocation acquires the approved official calendar and Upstox BOD
mapping, then verifies the canonical stock through BharatStock. PNB is an
example, not a claim that its current evidence or trade eligibility is admitted.
The command selects the latest two officially completed sessions at invocation
time within a 32-calendar-day lookback. Its acquisition/publication ceiling is
30 minutes, capped before the next IST date; that future deadline never selects
a future close and is not a latency promise or forcible-cancellation guarantee.

Warm reuse validates exact retained evidence, current source/configuration
identities, same-day mapping/calendar freshness and the unchanged session
window before price access. `--refresh` forces the full two-session price
refresh. A changed day/window revalidates the bounded requirement; this is not
suffix-only incremental acquisition. Immutable captures and receipts survive
replacement of the private current-result locator.

JSON contains feature-local Price Action, source/basis labels, exact references,
actual knowledge times and scoped reasons—not raw bars, an observed whole
report, a corporate-action qualification or a trade recommendation. Exit `0`
means observed Price Action; `1` means a structured unavailable/insufficient
result. Invalid arguments or an unexpected internal failure return `2` with a
sanitized stderr code. Live provider use and real-stock validation still require
their exact authority; deterministic synthetic checks do not establish them.

## Structured daily OHLCV downloader

**Accepted operating assumption — 2026-09-10.** Use supplied BharatStock OHLCV
unchanged by default, assuming for now that the provider has adjusted it
correctly. The [owner decision](docs/roadmap.md#accepted-as-provided-ohlcv-decision-and-member-isolation)
supersedes waiting for field clarification before implementing this mode.
The earlier extra-factor finding remains historical evidence, not proof that
unchanged provider prices are wrong. Current review and delivery status belongs
to PR #185; independent review and release gates remain required.

This source revision exposes one `equity_data_downloader`
implementation for bounded direct BharatStock daily acquisition. Its CLI and
Python API use the same core. Parquet is the sole
persisted OHLCV source of truth. Persistent output never uses `Downloads` or an
arbitrary caller-selected file. Every invocation writes beneath one configured
structured-data root, whose default is:

```text
~/SwingTradingAIAssistantData
```

The derived layout is:

```text
adjusted_daily/provider=bharatstock/request=<request-sha256>/data.parquet
```

DuckDB is the SQL query engine over those Parquet files; it is not a second
OHLCV copy. PyArrow is only the Parquet reader/writer library. Feather is not
used. There is no Yahoo cookie/timezone cache or Yahoo fallback. The utility
accepts between 1 and 100 explicit canonical ISIN/exchange/effective-symbol
identities and one inclusive date range. Each stock uses an identity lookup
followed by bounded price pages; acquisition is serial and does not retry.
It does not infer exchange calendars, canonical mappings, decision
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

Run from this source checkout with its locked dependencies:

```bash
uv sync
```

Provide the authorized account key through `BHARATSTOCK_API_KEY`; do not put
credentials in request files, command arguments, retained evidence, or logs.
Repeat `--instrument ISIN:EXCHANGE:SYMBOL` for each stock:

```bash
uv run equity-data-download \
  --instrument INE062A01020:NSE:SBIN \
  --instrument INE002A01018:NSE:RELIANCE \
  --start 2026-08-01 \
  --end 2026-08-28
```

Use `--storage-root /absolute/path` to configure a different single structured
data root. The selected root must be an existing absolute directory owned by the
invoking user with mode `0700`; relative, symlinked, shared, or extra-linked
storage is rejected before any provider call. The complete derived dataset
remains under that root; there is no arbitrary output-file option.

The downloader preserves supplied OHLCV unchanged and labels prices
`BHARATSTOCK_SOURCE_REPORTED_OHLC`. It does not apply `adjustment_factor` to
OHLC or volume. The former `apply_adjustment` API argument and
`--apply-adjustment` CLI flag are retired, not accepted as ignored options.
Original OHLC and separate optional adjustment fields remain retained as exact
decimal strings in the `source_*` columns. Processed OHLC columns use float64;
reuse validates them against the exact original source values.
The single volume field is never rescaled and is labelled `SOURCE_REPORTED`;
this does not certify exchange-raw units. No total-return equivalence is claimed.
The exact request identity binds ordered canonical instruments, dates,
provider `bharatstock-api@v1`, source-preserving configuration, and
schema/contract V5. Earlier schema identities cannot be reused as this contract.
An existing dataset is reused only
after its owner, permissions, singleton identity, metadata, complete schema, and
all OHLCV values pass validation; `REUSED` performs zero provider requests and
zero file writes. A different or expanded request, provider version, call
configuration, or schema is a new coherent adjusted-price snapshot; the
downloader never appends a new adjustment vintage to old rows.

The same behavior is available as a Python API:

```python
from datetime import date

from equity_data_downloader import download_daily_ohlcv
from swing_trading_ai_assistant.market_data.bharatstock import BharatStockInstrument

receipt = download_daily_ohlcv(
    (
        BharatStockInstrument("INE062A01020", "NSE", "SBIN"),
        BharatStockInstrument("INE002A01018", "NSE", "RELIANCE"),
    ),
    date(2026, 8, 1),
    date(2026, 8, 28),
)
```

The receipt reports canonical instruments, request identity, requested period,
row count, per-instrument row counts, provider version, retrieval time, and
derived Parquet path. A member-local missing history contributes zero rows;
shared authentication, authorization, quota, transport, or provider failures
stop the run. This transport receipt is not a claim of complete research.

Existing Yahoo V2 Parquet remains readable through
`equity_data_downloader.read_retained_yahoo_daily_ohlcv_v2(symbols, start, end,
storage_root=None, *, provider_version="1.6.0")`. Supply the original symbol
tuple, inclusive dates, storage root, and provider version. Its distinct
`RetainedYahooDatasetReceiptV2` preserves the original request identity, Yahoo
price/volume labels, retrieval time, counts, and path. This is a read-only
operation: no provider client, cache creation, download, repair, conversion, or
BharatStock identity is involved. Missing or corrupt evidence fails closed.



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
candle data. Recognized provider, payload, and credential failures produce only
`probe_failed` on stderr and exit code `2`; exception-class suffixes are not
published. An unexpected implementation failure produces only `internal_error`
on stderr, empty stdout, and exit code `2`. Argument-parser rejection produces
only `request_invalid`; existing command-specific admission diagnostics remain
sanitized.

An internal error does not mean that retained market evidence is missing or
corrupt. Do not delete or relabel evidence, silently switch providers, or publish
a partial result. Preserve the private inputs and report only the command name,
software version, and fixed failure code—not arguments, paths, exception text,
tracebacks, credentials, or provider payloads. The complete
[internal-error policy](docs/architecture-freeze-v1.md#internal-errors-and-operator-diagnostics)
also defines the unchanged V1 coverage/query generic-failure envelope.

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
