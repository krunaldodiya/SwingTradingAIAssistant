# Initial Roadmap

## Current delivery priority

All phases and module outcomes below remain planned. Only their delivery
priority changes: make the current/live/realtime path usable first, then perform
historical storage and backtest validation. Nothing in the original roadmap is
removed.

The immediate sequence is current price/volume, current Market Regime, current
Sector Analysis, current news/events, and one integrated current packet for an
external AI. Historical fixed-cohort OHLCV storage and validation follow. The
tool continues to retain point-in-time provenance from now so later work cannot
project current knowledge backward.

[Upcoming Sprints Overview](upcoming_sprints_overview.md) maps this priority to
the current sprint dependency sequence. It preserves the locked module order,
historical work, release gates, `NO_TRADE`, and all explicit exclusions.

## Listed-equity feature boundary and Nifty 100 focus

[Issue #130](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/130)
sets the owner-approved direction. Reusable feature cores consume an explicit
bounded list of canonical listed-equity instruments independently of index
membership. Point-in-time membership, discovery, and universe selection are a
separate policy layer. Product research, source qualification, validation, and
default workflows prioritize the point-in-time Nifty 50 plus Nifty Next 50.

Canonical identity is ISIN and exchange with effective symbol history and
versioned provider mappings. Each feature declares its data-capability profile
and fails with typed unsupported or insufficient evidence when identity,
mapping, schedule, price basis, freshness, corporate-action, sector, news, or
event evidence required by that feature is absent. An explicitly supplied
supported stock outside the Nifty 100 may use the same capability when all of
its required identity and evidence exist, but it is not the primary roadmap or
qualification focus.

Existing `Nifty50*` names, exact-50 contracts, and historical sprint evidence
remain truthful V1 records. They are not described as already generic.
[Plan 23](plans/23-instrument-agnostic-feature-boundary-and-coupling-audit.md)
owns separate future incremental migrations; there is no big-bang refactor,
reinterpretation of historical exact-50 V1 evidence, or reopening of completed
Issues #125/#127/#132.

Sprint 11 / [Issue #116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116)
is closed/completed. Its publication dependencies merged first:

1. [Issue #125](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/125)
   and the standalone provider-neutral Upstox-first screen in
   [Plan 21](plans/21-current-supplied-cohort-corporate-action-screen-contract.md)
   merged through [PR #128](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/128)
   as `cdb9ab1c2796356a3e9f604bdd5aeb404cf7519b`;
2. [Issue #127](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/127)
   and its adjusted-daily MVP merged through
   [PR #129](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/129)
   as `c530ae3d6dc43714a71c1f874fe81ecb6b4944c6`; and
3. [Issue #132](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/132)
   and its canonical explicit-stock adjusted-close input merged through
   [PR #133](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/133)
   as `847dfbdf7b6114cb736e00abf9126c995d30e828`.

[PR #124](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/124)
then delivered Market Regime V2 comparability and merged exact reviewed head
`d56120fb5966dffea32207b59f1edf0673b2e51b` as merge commit
`f03edf3690e34e25a57b58a15450129e3bf9a5e9`. Local evidence was 296 focused
tests, 2,867 full tests, 91.03% coverage, Ruff format/check, Pyright, Vulture
80, build, and sealed no-network and live current-prospective smokes. Hosted
Quality/build and GitGuardian passed.

Sprint 12 / [Issue #117](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/117)
is **closed/completed** under
[Plan 24](plans/24-current-supplied-cohort-sector-analysis-contract.md).
[PR #135](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/135)
merged exact reviewed head `b8c416709ebae82879c5dceae603b141b0dd1fa8`
as merge commit `4dfa8ecd1854aec4b4b2181cf2d0310072f65b49`.
Independent exact-revision quality review returned **APPROVE** and security
review returned **PASS**. Local gates passed 2,991 tests at 90.82% coverage,
Ruff format/check, Pyright, Vulture 80, and build; hosted Quality/build and
GitGuardian passed. Issue #117 is closed and its Project item is **Done**.

The slice delivers current exact supplied-cohort Industry classification and
aggregate Industry Participation. `Industry` is the literal source field, not
an official `Sector` claim or Industry-to-Sector mapping. Historical
classification, supplied-cohort index membership, live participation,
effectiveness, recommendation, order placement, and raw/member publication
remain explicit nonclaims or deferrals. The official parser smoke admitted the
exact current 100-row, 6,610-byte artifact with SHA-256
`5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85`;
it is parser provenance only.

The closeout records the working-feature-first MVP correction and its handbook
revision `93210ed3c28df90fdb971f6b8fd7c96ce71cd240`: separate the first
working slice from later improvements and stop before unplanned scope expansion.
Sprint 13 / [Issue #118](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/118)
is **closed/completed** under
[Plan 25](plans/25-current-supplied-cohort-event-notice-contract.md).
[PR #137](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/137)
merged independently reviewed head `2b65aa46f3f67552bf600675c6f1a5c09d363e12`
as merge commit `75ca9c3d3302f6d0a46ac772099c7b4d65e041c3`.
Independent functional review returned **APPROVE** and security review returned
**PASS**. Exact committed local gates passed Ruff format/check, Pyright 0/0,
Vulture 80, `uv build`, `git diff --check`, and 3,038 tests at 90.68%
coverage; hosted Quality/build and GitGuardian passed on the reviewed head.
Issue #118 is closed, its Delivery Project item is **Done**, and it is the
Sprint 13 milestone.

The delivered first slice admits one operator-acquired, unfiltered official NSE
Equity `1D` corporate-announcement CSV for attributed owner-private
personal/noncommercial local use. The 2026-08-26 owner amendment additionally
permits one bounded current official acquisition edge, legacy/current
publisher filenames, and exact UTF-8 bytes with or without BOM. Both preserve
exact cohort/provenance, typed failure, immutable archive-owned `known_at`, and
retain-before-return behavior, without polling, systematic history, attachment
fetch, redistribution, sentiment, recommendation, signal, or order. The
historical exact 8,016-byte, 20-row artifact SHA-256
is `a395f454dd39b3befd14ac2f1b3e0dce312c8ba0441098b80e596be172749210`;
production parse/project/real `StorageRootLease` archive-and-retry returned one
`GODREJCP` / `INE102D01028` notice and
`NO_MATCHING_NOTICE_IN_SNAPSHOT` for `TCS` / `INE467B01029`. This is
parser/projection/retention evidence only, not source completeness, live
participation, historical coverage, commercial permission, publisher correction
lineage, recommendation quality, or effectiveness.

Plan-25 event archives remain prospective and unavailable event history remains
explicit. Polling/systematic history, general news, other
providers/types/surfaces, semantic correction graphs, external attestation,
licensed history, and sentiment/ranking remain deferred.

Sprint 14 / [Issue #119](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119)
is **DELIVERED/CLOSED — PR #140 MERGED; ISSUE #119 CLOSED/COMPLETED; DELIVERY PROJECT ITEM DONE; SPRINT 14 MILESTONE; EXACT REVIEWED HEAD APPROVED/PASSED; ALL REQUIRED CURRENT SMOKES, 852 FOCUSED, 3,400 FULL AT 89.53% COVERAGE, ALL EXACT-CURRENT LOCAL GATES, HOSTED QUALITY/BUILD, AND GITGUARDIAN PASSED** under
[Plan 27](plans/27-current-same-pass-market-regime-contract.md). The owner
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

Current/live Market Regime availability will not depend on prior tool runs. For
one bounded cutoff, the successor resolves the latest 21 completed official
sessions and admits exact approved retained/provider raw bars available now,
retaining the complete grid with truthful current `known_at` and
`CURRENT_SAME_PASS_ONLY`. Equal current inputs produce the same packet after
0/1/7/30 inactive days. Missing prospective envelopes is not a failure and
current acquisition does not backfill historical availability.

During market hours S20 is the prior completed official session; after the
official close it may be today. Optional `PARTIAL_CURRENT_SESSION` price/volume
is provisional and cannot enter completed facts, Market Regime, Industry
direction, historical claims, signals, recommendations, or orders. Only genuine
current capability/evidence failures block the result.

Plan-20 V1/V2 remain frozen/delivered. Plan-26 packet `@v1` is unpublished WIP
superseded before delivery by Packet V2, will not ship, and has no alias. Its
101 focused-test result remains historical WIP/repair evidence only.

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

Plan 21 remains a nonexhaustive provider screen, not authoritative no-break
proof or an adjustment engine. Plan-22 adjusted close remains separate from
Upstox raw OHLCV and does not make yfinance strict point-in-time authority.

## Provider and price-basis overlay

Provider routing is by narrow capability, selected explicitly before use, and
bound into fact provenance. Upstox is primary for live/current raw OHLCV and its
retained corporate-action screen. yfinance is accepted only for adjusted daily
research, with explicit provider and adjusted price basis; it is never a silent
fallback or a live broker feed. Angel One is not implemented now and remains a
future adapter candidate requiring separate qualification.

yfinance supplies long daily history, but its intraday history is limited to the
latest 60 days. It is an unofficial Yahoo client for personal/research use, and
retrospectively retrieved adjusted series can be revised; they are not
as-published point-in-time authority. Every admitted fact must bind provider,
price basis, source/schema/policy identity, timestamps, and retained
receipt/object identity. No generic silent fallback is permitted.

Existing Upstox raw OHLCV remains unchanged. A yfinance adjusted close must never
be inserted into or used to populate an Upstox raw candle. A future Market
Structure contract must use one complete, consistent raw-OHLC basis or one
complete, consistent adjusted-OHLC basis and remains separate from Sprint 11.
Historical/backtest studies use only evidence available by the declared cutoff;
unavailable features are explicitly omitted/not applied, never later-backfilled,
and do not block unrelated research whose declared profile does not require
them.

Current/live-first is sequencing only, never scope removal. Sprint 15 /
[Issue #120](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/120)
owns the source-backed fixed-cohort historical daily OHLCV store. Its accepted
first-working slice is [Plan 28](plans/28-fixed-cohort-historical-ohlcv-revision-store-contract.md):
one closed `UPSTOX_RAW` retained-source profile, daily raw OHLCV derived from
verified retained one-minute Upstox partitions, immutable revisions, and exact
`INITIAL`/`APPEND`/`CORRECTION` lineage. It makes no adjustment, corporate-action
continuity, cross-session comparability, provider-download, or inferred
historical-index-membership claim.

### Swing-research timeframe acquisition and retention policy

For the default five-to-ten-session swing horizon, validated daily OHLCV is the
full-history research dataset. Daily evidence is sufficient for end-of-day
Market Regime, Industry Participation, Market Structure, and strategies whose
decision is made after a completed session and whose execution rule uses a
later explicitly available price. Realistic evaluation still requires gaps,
costs, slippage, liquidity, corporate actions, and conservative handling when a
daily bar cannot establish the order of two intraday events.

Lower-timeframe retention is capability-driven rather than universal:

- retain validated daily OHLCV for the full declared cohort and research range;
- acquire or retain 15-minute evidence only for bounded execution-sensitive
  studies, such as resolving same-session stop/target ordering or explicitly
  timed entries and exits;
- acquire or retain one-minute evidence only for bounded recent windows,
  shortlisted entry/exit sessions, current-session monitoring, source-quality
  audits, or separately accepted execution/slippage research; and
- do not treat a one-minute backtest as tick-accurate execution evidence:
  minute candles do not prove within-minute price order, queue position,
  available quantity, or bid/ask fills.

Existing verified retained Upstox one-minute partitions remain valid source
evidence and are not destructively removed or reinterpreted. Plan 28 and the
current/live Market Structure slice may continue deriving complete raw daily
bars from those partitions. Changing future downloader cadence, retention
windows, compaction, or archive policy is a separate bounded optimization: it
must compare acquisition time, stored bytes, daily aggregate equivalence,
auditability, and observable backtest differences before replacing the current
source path. Hourly, five-minute, or other intervals are adopted only when an
accepted study declares why daily or 15-minute evidence is insufficient.

Sprint 16 /
[Issue #122](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/122)
owns capability-aware validation over the supplied cohort and immutable evidence
revisions under
[Plan 29](plans/29-capability-aware-historical-validation-gate-contract.md),
the required availability-ledger checks for each declared study profile, and the
pre-Market-Structure gate. It validates evidence proven available at the
applicable cutoff; it does not construct or acquire missing evidence.

Neither sprint automatically owns point-in-time membership, sector or
classification, news, event, or corporate-action snapshot construction.
Unavailable features remain explicit without fabrication, later backfill,
silent neutralization, or dropped dates. Look-ahead, survivorship, selection,
and data-snooping controls; development, walk-forward, out-of-sample, and
untouched-test separation; forward/paper validation; and realistic costs and
slippage remain required where applicable. Market Structure remains after the
Sprint 16 gate, preserving the locked architecture sequence.

The live tracker has advanced beyond that dependency statement. Sprint 15 /
#120 and Sprint 16 / #122 are closed/completed with Project status **Done**.
Sprint 17 / #147 retained all `4/4` predeclared completed-session captures,
passed unchanged Plan 29 for `OHLCV_ONLY`, and closed/completed through PR #166
with Project status **Done**. That historical result remains separate from
current/live delivery. Sprint 18 / #148 delivered current/live Market Structure through
[Plan 31](plans/31-current-supplied-cohort-market-structure-contract.md) and
merged PR #149; the Issue is closed/completed and its Project item is **Done**.

Sprint 19 / #152 delivered the bounded current supplied-cohort Price Action
first working slice under
[Plan 32](plans/32-current-supplied-cohort-price-action-contract.md).
[PR #153](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/153)
merged exact reviewed head `aaaade762b1b633cd67fd0ab7c5e8fec55deebac`
as `80efbec7b8af3fad125312ef919a18137840d3df`; the Issue is
closed/completed and its Project item is **Done**.

[Issue #154](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/154)
and [Plan 33](plans/33-efficient-continuous-nifty100-capture-contract.md)
own only the bounded source decision, complete nonpublishing benchmark, and
implementation contract for efficient current Nifty 50 plus Nifty Next 50
adjusted capture. The measured two-cohort, eight-worker acquisition completed
100/100 members over 21 sessions in 25.942 seconds on the fixed-cadence bounded
path. Issue #154 closed through merged PR #157 and its Delivery Project item is
**Done**. It changed no runtime, scheduler, store, provider profile, or
historical qualification.
[Issue #155](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/155)
delivered the reviewed Plan 30 runtime prerequisite. Sprint 17 / Issue #147
subsequently completed its `4/4` temporal captures, passed unchanged Plan 29,
and closed through PR #166. [Issue #156](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/156)
owns the separately bounded Plan 33 implementation.

Owner-prioritized Issue #145 remains open **Todo** and follows #156 before
another product module starts.

[Plan 34](plans/34-swing-research-feature-map.md) owns the necessary-only future
feature taxonomy. Delivered Market Structure and Price Action remain separate
from possible Volume, Relative Strength, and Liquidity/SMC facts. Named patterns,
levels, breakouts/retests, lines, channels, formations, zones, and SMC labels are
not promised backlog features. A possible fact advances only when a separate
owner-prioritized Issue proves a concrete unmet swing-research, analysis,
scanning, or screening need; establishes distinct practical value beyond
delivered facts; and accepts the smallest deterministic causal working slice.
Otherwise the default decision is not to build it.
Possible analytical facts are additive context by default, not hidden mandatory
filters. Safety and required-evidence failures remain fail-closed, but an
optional neutral, unsupported, or insufficient fact does not become `NO_TRADE`
without an accepted strategy contract. Every proposed hard filter must compare
its marginal benefit with candidate coverage, retained opportunities, no-trade
frequency, and out-of-sample behavior; 100% accuracy on no useful signals is not
an objective.

Future [Issue #139](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/139)
separately owns the broader bounded per-decision-date as-of research snapshot
outcome. It depends on #120 and #122 unless the owner changes the ordering,
requires its own accepted contract, and does not automatically expand either
issue. This clarification does not reinterpret frozen/delivered Plan-20 V1/V2
or the historical non-shipping Plan-26 `@v1` record.

## Phase 0: Foundation

- Freeze product scope and terminology.
- Define measurable success and risk criteria.
- Decide supported trading horizon and data frequency.
- Evaluate market-data sources for adjusted listed-equity OHLCV, corporate
  actions, point-in-time Nifty 50 and Nifty Next 50 membership, and sector
  classification.
- Select the implementation stack only after the data and research requirements
  are clear.

Detailed execution plan:
[Plan 01: Data Foundation and Upstox Ingestion](plans/01-data-foundation-and-upstox-ingestion.md).

## Phase 1: Research platform skeleton

- Define versioned schemas for market data, module facts, validation errors,
  evidence, confidence, freshness, and provenance.
- Separate reusable listed-equity data capabilities, point-in-time validation,
  backtesting, risk, and application contracts from higher-level universe
  selection. A feature core accepts bounded canonical instruments; the default
  product policy selects the point-in-time Nifty 100.
- Build reproducible data ingestion and quality checks.
- Create a backtesting boundary that includes costs, slippage, liquidity,
  corporate actions, and point-in-time universes.
- Establish a deterministic full-history baseline and a separate sampled,
  sealed point-in-time replay boundary for evaluating external AI reasoning.
- Establish unit, property, regression, and no-look-ahead tests.
- Define an agent-neutral boundary without committing prematurely to API, CLI,
  MCP, or another transport.

## Phase 2: First module — Market Regime

Write and approve the Market Regime specification before coding it:

- purpose and supported regime labels;
- required inputs and freshness rules;
- deterministic classification rules;
- confidence or evidence representation;
- edge cases and insufficient-data behavior;
- output contract;
- validation experiments; and
- acceptance criteria.

Implement and validate the module only after that specification is frozen.

Sprint 9 records terminal decision
`BLOCKED / CAPABILITY_EVIDENCE_MISSING`. It is one test-first learning/decision
slice for the point-in-time evidence required by Market Regime Layer B.
[Plan 16](plans/16-market-regime-layer-b-acquisition-decision.md)
extends frozen [Plan 12](plans/12-market-regime-contract.md) and
[Plan 13](plans/13-market-regime-validation-protocol.md) without changing their
facts, labels, cutoffs, reasons, or validation sequence.

Plan 16 replaces caller-authored gate/authorization payloads with one canonical
evidence/authorization manifest sealed in the build. The capability state,
identity, and assessment time are one atomic optional group. The corrected build
seals all three null because no admissible capability
evidence exists; all later evidence, approval, authorization, and
validation-receipt identities are also null. Its required source-controlled
prerequisite assessment instant records when those absences were assessed and
grants no authority.

The incomplete manifest is content-addressed by scope projection identity
`07f235b246e88d30404ddf1574e13907f436c937144e40abf4766c4463cb759e`
and final identity
`53717e75d9e93344d7df55ea2a5e94e48e133ff0ad673f27e38ba040cc91bb2f`.
The canonical blocked report identity is
`dbbc0bdf32cf081d491a119c05571bebf4dbd274bae858dd0e3d418b96bd1408`;
it exposes the sealed manifest identity and null authenticated capability,
receipt, and assessment-time outputs. A literal `None` remains a distinct
fail-closed `SEALED_MANIFEST_MISSING` path. Neither input nor the sealing instant
can supply authority.

The owner authorized one supervised release invocation containing one
credential-free `GET` of the fixed candidate PDF. The consumed invocation
emitted a sanitized historical receipt, but its old worker could attempt another
resolved address. Its one-call/one-attempt counters are unverified; the receipt
is inadmissible as capability evidence and no provider-independent projection
was retained or reconstructed. It was not rerun. HTTP success, media type,
`%PDF-`, or a digest proves no publisher authority, content, history, licence,
or permitted use.

[PR #107](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/107)
merged the historical implementation to `main` at **2026-08-15T15:40:16Z** as
`c74ee4788aa6d03864eb8c21f111afe7025ad9cc`. Its exact-revision reviews, checks,
and builds remain historical implementation publication evidence; PR #107 did
not contain this corrective seal or closeout. Linear ARK-183, ARK-184, and
ARK-185 remain historically **Done** with PR #107 attached. Those tracker states
grant no technical or decision authority and do not publish the correction.

Commit identity, exact-revision reviews, hosted checks, merge, and publication
for the correction are external lifecycle evidence; this roadmap asserts no
current lifecycle state for them. No source/PIT evidence bundle, terms/use
approval, operational-scope approval, owner full-acquisition authorization, or
trusted authorization-validation receipt exists. Work stops before acquisition,
readiness/admission, Market Regime labels, counts, outcomes, recommendations, or
later execution authority.

The former Sprint 10 R3 readiness proposal remains preserved as historical
**`BLOCKED / CAPABILITY_EVIDENCE_MISSING`** evidence in
[Plan 17](plans/17-market-regime-layer-b-evidence-acquisition.md). Its parent
acquisition goal,
[GitHub Issue #111](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/111),
is closed as not planned after the current-first reprioritization; the associated
planning context remains in
[Issue #112](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/112).
No provider access, acquisition, or historical runtime implementation started.
This historical blocked record grants no authority and is not the active Sprint
10 direction. The current Sprint 10–18 sequence is the one stated at the top of
this roadmap and in the Upcoming Sprints Overview.

## Phase 3: Second module — Sector Analysis

Sprint 8 delivered the first atomic vertical slice inside architecture-locked
Module 2, Sector Analysis, in the corrected 2026-08-13 through 2026-08-19
window. `nifty50-sector-participation@v1` accepts exact verified Market Regime
facts and one already-resolved PIT Nifty 50 snapshot, then derives and consumes
the report/private handoff internally in the same call. It emits deterministic
participation counts by opaque source label or one whole-result insufficiency;
callers have no report or handoff authority.

Label admission rejects any full constituent ISIN case-insensitively and any
constituent symbol matched case-insensitively as a complete
`[A-Z0-9.&_-]` token. Either defect returns whole-result
`SECTOR_CLASSIFICATION_CORRUPT` with no sector rows. A non-identity singleton
group remains allowed solely inside the authenticated nonanonymous owner-private
boundary required by the approved historical specification; no public delivery
surface exists.

Aggregate snapshot construction now revalidates every invariant of all 50 exact
constituents. At the Sector Participation boundary, expected deep-consistency
`TypeError` or `ValueError` failures are translated to the stable bounded
`resolved universe snapshot is inconsistent` structural error; unexpected
exceptions are not swallowed.

[Plan 14](plans/14-sector-participation-contract.md) records the implemented
contract, and [Plan 15](plans/15-sector-participation-validation-protocol.md)
records the focused TDD and validation evidence. The provider-free in-process
core is implemented in
`src/swing_trading_ai_assistant/market_data/universe_snapshot.py`,
`src/swing_trading_ai_assistant/market_regime/observed.py`, and
`src/swing_trading_ai_assistant/sector_analysis/participation.py`; focused
coverage is in `tests/market_data/test_universe_snapshot.py`,
`tests/market_regime/test_observed_reducer.py`, and
`tests/sector_analysis/test_participation.py`. Historical focused evidence
includes the prior **49 passed** two-file run, the **4 passed** identity
regressions, and the subsequent **53 passed** two-file run.

The final combined universe/observed/sector focused gate is **96 passed**, with
Ruff **PASS** and Pyright **0 errors, 0 warnings**. The repository gate is
Ruff/format/Vulture **PASS**, Pyright **0 errors, 0 warnings**, and **2,445
passed** at **92.96%** coverage; documentation evidence is **60 passed**.
Final reviewed head `411b21d4874206563b64d03ce8024953430660d2`
received independent exact-SHA quality **APPROVE** and security **PASS**.
Hosted CI [run 31832620021](https://github.com/krunaldodiya/SwingTradingAIAssistant/actions/runs/31832620021)
and GitGuardian both passed.

[PR #103](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/103)
merged the slice to `main` at **2026-08-14T19:39:18Z** as
`b6e34d3cdc598e1cd6dc50c50d517481d26e1391`; repository Sprint 8 delivery,
review, and publication are complete. Linear records ARK-175 through ARK-181
as Done; they now remain read-only historical evidence and are not copied into
the active GitHub backlog.

Exact SHA `25d889a` received **REQUEST_CHANGES** for the identity-bearing-label
privacy defect. Exact SHA `d79eecc` received **REQUEST_CHANGES** for the deep
constituent-revalidation defect. Both are superseded and are not approval or
publication evidence. The focused defect reproduction was **2 failing**, and
the direct repaired regression is **2 passed**.
[PR #102](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/102)
remains immutable historical planning/specification evidence, not implementation
or publication evidence.

The opaque labels are not claimed as an official NSE Sector taxonomy. Official
taxonomy work and Layer B are deferred. This slice adds no provider, acquisition
or retained-data workflow, delivery transport, recommendation, live observed
result, ranking, or effectiveness claim.

Sprint 12 / Issue #117 is closed/completed after PR #135 merged exact reviewed
head `b8c416709ebae82879c5dceae603b141b0dd1fa8` as
`4dfa8ecd1854aec4b4b2181cf2d0310072f65b49`. Quality review returned
**APPROVE**, security review returned **PASS**, local gates passed 2,991 tests
at 90.82% coverage plus Ruff/Pyright/Vulture/build, and hosted Quality/build
and GitGuardian passed.

This delivered current-only slice preserves literal `Industry` semantics and
does not claim official Sector taxonomy, historical classification, supplied
cohort membership, live participation, effectiveness, recommendation, order
placement, or raw/member publication. The 100-row, 6,610-byte official parser
smoke with SHA-256
`5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85`
is parser provenance only.

Sprint 13 / Issue #118 is closed/completed under Plan 25 after PR #137 merged
exact independently reviewed head `2b65aa46f3f67552bf600675c6f1a5c09d363e12`
as `75ca9c3d3302f6d0a46ac772099c7b4d65e041c3`. The delivered current/prospective
official NSE Equity corporate-announcement evidence preserves the accepted
owner-private source boundary; historical reconstruction and broader
news/provider work remain deferred.

## Later modules

Proceed in locked pipeline order, integrating and validating one module at a
time. Do not build an LLM implementation in this repository. External AI agents
will consume the deterministic fact contracts after they are dependable.

## Future packaging

[Issue #126](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/126)
is a future **low-priority** standalone packaging outcome. The working PyPI
distribution name is `swing-trading-market-data`, subject to name, licence,
support, release-ownership, and publication review. One authoritative
market-data codebase must produce the standalone wheel/sdist and remain
consumable by the installable full `swing-trading-ai-assistant` distribution;
there is no copied implementation or duplicated provider logic.

The standalone distribution may expose the existing `market-data` CLI and
provider-neutral market-data API without research/AI modules. It must preserve
capability-specific adapters, environment-owned credentials, explicit optional
provider dependencies, isolated wheel/sdist verification, and publication
provenance. It does not add a provider or change a market calculation. It does
not reopen completed Issues #125/#127/#132, Sprint 11, Sprint 12, or Sprint 13,
alter future Plan-23 migrations, or expand the delivered Sprint 14 scope.

## Release gates

Before any result can be treated as decision support, require:

- no known look-ahead or survivorship bias;
- reproducible backtests;
- strategy-specific historical coverage long enough to include materially
  different market regimes; five years is an example, not a universal literal
  minimum, and any selected duration and limitations must be documented;
- a deterministic full-history baseline plus separately identified, sampled
  point-in-time AI-reasoning replay when the AI decision layer is evaluated;
- realistic costs and slippage;
- out-of-sample and walk-forward validation;
- explicit handling of stale or missing data;
- traceable evidence for every recommendation; and
- paper-trading observation before real-money use.
