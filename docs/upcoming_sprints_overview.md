# Upcoming Sprints Overview

This document records the owner-level **current/live/realtime first** dependency
status and remaining sequence. Completed lifecycle claims below are tied to
their linked Issues and pull requests; future rows are a minimum dependency
plan, not authorization, delivery promise, acquisition plan, or publication
claim. Each remaining sprint requires its own accepted contract, focused
evidence, exact reviewed revision, and applicable repository/hosted gates.
Failed or insufficient evidence requires a replacement sprint rather than
automatic progression.

## Shared lane rule

Current/live/realtime work starts with current supplied-cohort price/volume,
then current Market Regime, Sector Analysis, news/events, and an integrated
current packet. The product-default selection policy focuses on the
point-in-time Nifty 50 plus Nifty Next 50; a reusable feature receives only the
explicit bounded canonical listed-equity cohort selected above it. The
deterministic tool supplies facts only; a consuming AI may produce explainable
research or `NO_TRADE` only within the applicable owner-private/source-use
boundary, never a tool-invented autonomous signal, recommendation, position
size, entry/exit, or order.

Index membership and feature capability are separate gates. Membership evidence
is required when the workflow claims a Nifty 50, Nifty Next 50, or combined
Nifty 100 cohort. Feature admission instead requires canonical ISIN/exchange
identity, effective symbol and provider mappings, plus that feature's declared
data capabilities. An explicitly supplied supported listed stock outside the
Nifty 100 may use the same feature when those requirements are met; it does not
become part of the default research or validation universe.

Existing Sprint 1–10 and frozen V1 records keep their original Nifty 50 names,
cardinalities, and evidence. They are historical exact-50 records, not
instrument-agnostic claims. Issues #125, #127, and
[#132](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/132) are
merged Sprint-11 dependencies.
[Plan 23](plans/23-instrument-agnostic-feature-boundary-and-coupling-audit.md)
owns separate future migrations; it does not reopen those dependencies or
reinterpret frozen evidence. Sprint 11
[#116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116) is
closed/completed after
[PR #124](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/124)
merged the V2 comparability semantics.

Historical/backtest work is deferred, not deleted. It uses an explicit supplied
cohort and versioned OHLCV revision, makes no inferred historical index
membership claim, identifies `FIXED_COHORT_RETROSPECTIVE`, and discloses
selection/survivorship limits. Historical news, events, and sector inputs are
deferred/not-yet-evaluated, not permanently removed or silently neutral.

Every admitted live fact is immutably archived from now with required
`known_at`, source, revision, affected identities, and the publisher
publication/effective fields actually supplied by that feature's admitted
source. An unavailable publisher field remains explicit null/unavailable
provenance; acquisition time is never relabelled as publisher time. A
per-feature/instrument/interval ledger records only `AVAILABLE`,
`NOT_PUBLISHED`, `NOT_RETAINED`, `SOURCE_GAP`, `STALE`, `CONFLICTED`, or
`UNLICENSED`. Coverage/windows are predeclared; no later fact substitutes for
unavailable history and unavailable dates are never dropped.
Point-in-time backtests and forward tests use only evidence available by their
historical cutoff. An unavailable factor is explicitly unavailable/not applied;
it is never fabricated or backfilled from later evidence, and it does not block
unrelated available-feature research. The current/live contract may instead
require a factor as a whole-result gate for the specific claim it makes.

Current same-pass availability is independent of prior tool runs. For one bounded
cutoff, it resolves the latest 21 completed official sessions and admits exact
approved retained/provider bars available now with truthful current `known_at`.
Equal current inputs produce the same packet after 0/1/7/30 inactive days;
missing prospective envelopes is not a current reason or historical backfill.
Optional `PARTIAL_CURRENT_SESSION` context is separately labelled and excluded
from completed facts, Market Regime/Industry direction, signals, and orders.

Sprint 15 / Issue #120 and Sprint 16 / Issue #122 are **closed/completed** and
their Delivery Project items are **Done**. Plan 28 delivered the bounded
source-backed fixed-cohort raw daily revision store, and Plan 29 preserved the
capability-aware historical validation boundary. Sprint 17 / Issue #147
retained all `4/4` predeclared completed-session captures under Plan 30,
passed unchanged Plan 29 for `OHLCV_ONLY`, and closed through PR #166 with
Project status **Done**. That historical result remains separate from active
current/live WIP.

Sprint 18 / Issue #148 delivered current supplied-cohort Market Structure
under Plan 31 through merged PR #149. Sprint 19 / Issue #152 delivered
current supplied-cohort Price Action under Plan 32 through merged PR #153.
Both Issues are closed/completed and their Delivery Project items are
**Done**. Issue #154 closed/completed through merged PR #157 as a bounded
planning and benchmark record under Plan 33; it changed no runtime. Issue #155's
governing merge delivers the runtime prerequisite, while Issue #156 retains the
separate bounded Plan 33 production implementation.

Sprints 15–19 do not automatically own point-in-time membership, sector or
classification, news, event, or corporate-action snapshot construction or
acquisition. Missing historical evidence remains explicit and is neither
fabricated nor treated as neutral. Broader bounded per-decision-date as-of
research snapshot construction belongs to Issue #139 and a separate accepted
contract; it depends on #120/#122 unless the owner changes the ordering and does
not expand either issue. The architecture sequence, historical validation
controls, forward/paper path, costs/slippage requirements, and Plan 18
fixed-cohort limitation remain intact.

**Provider direction update — 2026-09-10:** the owner approved
[#184](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/184)
to replace active yfinance daily acquisition with direct BharatStock access.
The [migration record](roadmap.md#bharatstock-migration-direction) distinguishes
the scoped 100-stock input-data check from implementation and release evidence.
The owner withdrew only the old pre-implementation scheduling dependency;
review limitations and protected release gates remain explicit.
Issue #183 remains open for its separate member-isolation behavior.

Provider routing is capability-based, explicit, and provenance-bound. Upstox is
primary for current/live raw OHLCV and the Plan-21 corporate-action screen.
The unreleased Plan22 V3 candidate follows the
[accepted as-provided decision](roadmap.md#accepted-as-provided-ohlcv-decision-and-member-isolation):
keep supplied BharatStock prices unchanged by default, assume their adjustment
is correct for now, and apply the factor once only under explicit opt-in.
Source volume never changes. This replaces the provider-clarification wait for
new-mode implementation, not the historical evidence or protected release gates.
Every fact binds its mode, provider, basis and retrieval provenance. These records
do not establish exchange-raw volume, total return or historical availability.
No provider is a silent fallback.
Historical Yahoo records remain readable under their original identities;
their acquisition path is retired by #184. Angel One remains deferred.

Raw Upstox OHLCV remains separate. No adjusted provider value fills an Upstox
candle. Market Structure uses a complete raw OHLC series or a complete adjusted
OHLC series consistently, never mixed bases.

| Sprint | Tracker and lifecycle | Atomic outcome | Minimum dependency and gate | Explicit non-goals |
| --- | --- | --- | --- | --- |
| 10 | [#121](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/121) — Closed/completed; High priority/risk | Current supplied-cohort `market-data` foundation: bounded current price/volume facts for 1–50 Nifty 50 identities and immutable archive records. | Canonical cohort identity/selection SHA; retained instrument resolution; latest completed daily OHLCV and optional `PARTIAL_CURRENT_SESSION`; provenance/availability ledger; whole-cohort insufficiency; no effect before admission. | Historical/backtest implementation, Market Regime, sectors, news/events, signals, recommendations, entries/exits, position sizing, orders. |
| 11 | [#116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116) — Closed/completed; High priority/risk | Current Market Regime V2 comparability over admitted archived current facts, a successful provider-neutral corporate-action screen, and separate adjusted daily close facts. | Issues [#125](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/125), [#127](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/127), and [#132](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/132) merged. [PR #124](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/124) merged reviewed head `d56120fb5966dffea32207b59f1edf0673b2e51b` as `f03edf3690e34e25a57b58a15450129e3bf9a5e9`; 296 focused / 2,867 full / 91.03%, Ruff/Pyright/Vulture/build, sealed no-network and live current-prospective smokes, hosted Quality/build, and GitGuardian passed. | Historical/backtest implementation, generic adjustment engine, mixed-basis OHLC, Market Structure, signals, recommendations, entries/exits, position sizing, orders. |
| 12 | [#117](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/117) — Closed/completed; Project **Done**; High priority/risk | Current exact supplied-cohort Industry classification and deterministic aggregate Industry Participation from one operator-acquired official NSE Indices Nifty 100 CSV. | [Plan 24](plans/24-current-supplied-cohort-sector-analysis-contract.md); [PR #135](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/135) merged reviewed head `b8c416709ebae82879c5dceae603b141b0dd1fa8` as `4dfa8ecd1854aec4b4b2181cf2d0310072f65b49`; quality **APPROVE**, security **PASS**; 2,991 tests / 90.82%, Ruff/Pyright/Vulture/build, hosted Quality/build, and GitGuardian passed. The 100-row / 6,610-byte parser smoke at SHA-256 `5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85` is provenance only. | Automated acquisition, alternate sources, official Sector taxonomy or mapping, historical classification, index-membership claim, live participation/effectiveness claim, recommendation, raw/member publication, or broker order placement. |
| 13 | [#118](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/118) — Closed/completed; Project **Done**; Sprint 13 milestone; High priority/risk | Delivered current owner-private supplied-cohort event notices from one operator-acquired official NSE Equity unfiltered `1D` corporate-announcement CSV. | [Plan 25](plans/25-current-supplied-cohort-event-notice-contract.md); [PR #137](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/137) merged independently reviewed head `2b65aa46f3f67552bf600675c6f1a5c09d363e12` as `75ca9c3d3302f6d0a46ac772099c7b4d65e041c3`; independent functional **APPROVE** and security **PASS**; exact committed Ruff format/check, Pyright 0/0, Vulture 80, `uv build`, `git diff --check`, 3,038 tests at 90.68% coverage; hosted Quality/build and GitGuardian passed on the reviewed head; exact 8,016-byte, 20-row artifact SHA-256 `a395f454dd39b3befd14ac2f1b3e0dce312c8ba0441098b80e596be172749210`; exact cohort/provenance, typed failures, immutable archive-owned `known_at`, retain-before-return; production parse/project/real `StorageRootLease` archive-and-retry: `GODREJCP` / `INE102D01028` one notice, `TCS` / `INE467B01029` `NO_MATCHING_NOTICE_IN_SNAPSHOT`. Parser/projection/retention evidence only. | Automated collection/attachment fetch/redistribution; source completeness, live participation, historical coverage, commercial permission, publisher correction lineage, sentiment/ranking, recommendation, signal, order, effectiveness; automated/licensed acquisition, general news, other providers/types/surfaces, semantic correction graph, external attestation, licensed history, Sprint 14 packet integration. |
| 14 | [#119](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119) — **DELIVERED/CLOSED — PR #140 MERGED; ISSUE #119 CLOSED/COMPLETED; DELIVERY PROJECT ITEM DONE; SPRINT 14 MILESTONE; EXACT REVIEWED HEAD APPROVED/PASSED; ALL REQUIRED CURRENT SMOKES, 852 FOCUSED, 3,400 FULL AT 89.53% COVERAGE, ALL EXACT-CURRENT LOCAL GATES, HOSTED QUALITY/BUILD, AND GITGUARDIAN PASSED**; High priority/risk | Owner-private current same-pass raw grid `@v1`, Market Regime V3, Industry Participation V2, and clean-cutover Packet V2; latest completed official S20, optional separately labelled partial context, facts-only same-owner local AI research, or mandatory insufficient information / `NO_TRADE`. | [Plan 27](plans/27-current-same-pass-market-regime-contract.md); ten review blockers fixed without a new subsystem, including both PR #140 P2 blockers; all required current smokes passed, including the mandatory Aug-27 market-hours `RELIANCE` positive rerun on exact current source candidate 66-path fingerprint `3940ffe433887360c2744507c4075ac2404ffcd1482b2799380d26776623229e`; 852-test focused portfolio and 3,400-test full suite at 89.53% coverage recorded; all exact-current local gates passed, including Ruff format/check 275, Pyright 0/0, Vulture 80, diff, build, wheel, and clean installed-wheel imports/runtime; PR #140 merged exact reviewed head `0236942ced7127bc7220282d71e2cc35f0ff0c05` as `893c2127fac6ab7a2f3f416e315aee26d8b06b4f`; exact reviews returned APPROVE/PASS; hosted Quality/build and GitGuardian passed; Issue #119 closed/completed; Delivery Project item Done; Sprint 14 milestone delivered/closed as research-only with no autonomous-trading or advice claim. | Historical replay/backfill, polling, generic provider framework, additional providers/fallback, attachments, general news, Sector mapping, signals, recommendations, orders, hosted/shared/public delivery. |
| 15 | [#120](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/120) — Closed/completed; Project **Done**; High priority/risk | Source-backed fixed-cohort historical daily raw OHLCV revisions under Plan 28. | Complete retained Upstox one-minute source evidence projected to immutable daily `INITIAL`/`APPEND`/`CORRECTION` revisions. | Provider download, adjustment, historical validation, Market Structure, signals, or orders. |
| 16 | [#122](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/122) — Closed/completed; Project **Done**; High priority/risk | Capability-aware historical validation under unchanged Plan 29. | Explicit study profile, cutoff-valid evidence, availability ledger, reproducible identities, and separated evaluation regions. | Evidence acquisition, fabricated historical context, Market Structure implementation, recommendations, or orders. |
| 17 | [#147](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/147) — Closed/completed; Project **Done**; High priority; estimate 1 | Capture-forward adjusted OHLC historical qualification under Plan 30. | Plan-30 runtime and all four distinct completed-session captures retained; unchanged Plan 29 approved `OHLCV_ONLY`; independently reviewed PR #166 merged. | Blocking current/live work, retrospective point-in-time relabelling, raw/adjusted mixing, Market Structure implementation, or orders. |
| 18 | [#148](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/148) — Closed/completed; Project **Done**; High priority/risk; estimate 1 | Delivered current supplied-cohort Market Structure under Plan 31. | [PR #149](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/149) merged exact reviewed head `981b387f30f154be2ce837227132d16a48df4cb9` as `fa999408ae1318ea40e38ab566b728bec286438f`; exact 21-session raw grid, Plan-21 screen, pivots, HH/HL/LH/LL, trend, BOS/CHoCH, retained-current smoke, hosted and security gates passed. | Historical/backtest qualification, adjusted-price mixing, Price Action, SMC, signals, recommendations, API/UI, or orders. |
| 19 | [#152](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/152) — Closed/completed; Project **Done**; High priority/risk; estimate 1 | Delivered current supplied-cohort Price Action under Plan 32. | [PR #153](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/153) merged exact reviewed head `aaaade762b1b633cd67fd0ab7c5e8fec55deebac` as `80efbec7b8af3fad125312ef919a18137840d3df`; exact S19/S20 facts, retained-current smoke, independent reviews, local/hosted gates, and GitGuardian passed. | Named patterns, thresholds, historical/backtest claims, adjusted-price mixing, Liquidity/SMC, Volume, Relative Strength, signals, recommendations, delivery surfaces, or orders. |
| Planning | [#154](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/154) — Closed/completed; Project **Done**; PR #157 merged | Accepted Plan 33 source decision, benchmark, and closed implementation contract for efficient current Nifty 50 plus Nifty Next 50 adjusted capture. | Source-verified yfinance execution; named eight-permit pool before yfinance import; fixed 125-millisecond request-start cadence and bounded session; 100/100 members over 21 sessions in 25.942 seconds; functional **APPROVE**, security/privacy/provenance **PASS**, hosted Quality/build and GitGuardian **SUCCESS**. | Production runtime, retained Nifty 100 bars, scheduler, signals, recommendations, orders, or historical qualification. |

Sprint 11 is closed after all three dependencies and PR #124 merged. Sprint 12 /
Issue #117 is **closed/completed** under Plan 24 after PR #135 merged exact
reviewed head `b8c416709ebae82879c5dceae603b141b0dd1fa8` as
`4dfa8ecd1854aec4b4b2181cf2d0310072f65b49`. Independent quality review
returned **APPROVE** and security review returned **PASS**. Local gates passed
2,991 tests at 90.82% coverage, Ruff format/check, Pyright, Vulture 80, and
build; hosted Quality/build and GitGuardian passed. Issue #117 is closed and
its Project item is **Done**.

The delivered source tier is literal `Industry`, not an official NSE Indices
Sector taxonomy or Industry-to-Sector mapping. Historical classification,
supplied-cohort index membership, live participation, effectiveness,
recommendation, raw/member publication, and order placement remain nonclaims
or deferrals. The official parser smoke admitted the exact current 100-row,
6,610-byte artifact with SHA-256
`5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85`;
it is parser provenance only.

The Sprint 12 closeout records the MVP/working-feature-first process correction
and handbook revision `93210ed3c28df90fdb971f6b8fd7c96ce71cd240`:
separate the first working slice from later improvements and stop before
unplanned scope expansion. Sprint 13 / Issue #118 is **closed/completed** under
[Plan 25](plans/25-current-supplied-cohort-event-notice-contract.md) after
[PR #137](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/137)
merged independently reviewed head `2b65aa46f3f67552bf600675c6f1a5c09d363e12`
as `75ca9c3d3302f6d0a46ac772099c7b4d65e041c3`. Independent functional review
returned **APPROVE** and security review returned **PASS**; exact committed local
Ruff format/check, Pyright 0/0, Vulture 80, `uv build`, `git diff --check`, and
3,038 tests at 90.68% coverage passed, as did hosted Quality/build and
GitGuardian on the reviewed head. Issue #118 is closed, its Delivery Project
item is **Done**, and it is the Sprint 13 milestone. The delivered
operator-acquired unfiltered official NSE Equity `1D` CSV path is attributed
owner-private personal/noncommercial local use only, with exact
cohort/provenance, typed failures, immutable archive-owned `known_at`, and
retain-before-return. The official 8,016-byte, 20-row artifact SHA-256 is
`a395f454dd39b3befd14ac2f1b3e0dce312c8ba0441098b80e596be172749210`;
production parse/project/real `StorageRootLease` archive-and-retry returned one
`GODREJCP` / `INE102D01028` notice and
`NO_MATCHING_NOTICE_IN_SNAPSHOT` for `TCS` / `INE467B01029`. This is
parser/projection/retention evidence only, not source completeness, live
participation, historical coverage, commercial permission, publisher correction
lineage, recommendation quality, or effectiveness. The 2026-08-26 amendment
adds one bounded current schedule/Industry/event acquisition edge; it adds no
polling, systematic history, attachment fetch, redistribution, sentiment,
recommendation, signal, or order. Plan-25 event archives remain prospective and
unavailable event history remains explicit. Sprint 14 /
[Issue #119](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119)
is **DELIVERED/CLOSED — PR #140 MERGED; ISSUE #119 CLOSED/COMPLETED; DELIVERY PROJECT ITEM DONE; SPRINT 14 MILESTONE; EXACT REVIEWED HEAD APPROVED/PASSED; ALL REQUIRED CURRENT SMOKES, 852 FOCUSED, 3,400 FULL AT 89.53% COVERAGE, ALL EXACT-CURRENT LOCAL GATES, HOSTED QUALITY/BUILD, AND GITGUARDIAN PASSED** under
[Plan 27](plans/27-current-same-pass-market-regime-contract.md). Operational
evidence showed zero usable Plan-20 21-object prospective inputs, and the owner
selected the prior-run-independent current same-pass successor. Plan-20 V1/V2
remain frozen/delivered. Plan-26 packet `@v1` is unpublished WIP superseded
before delivery, will not ship, and has no alias; its 101 focused tests remain
historical WIP/repair evidence only.

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

Future [Issue #139](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/139)
is unassigned bounded per-decision-date as-of research snapshot construction.
It depends on
[#120](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/120) and
[#122](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/122)
unless the owner later changes ordering. It requires a separate accepted
contract and does not automatically expand either Sprint 15 / #120 or Sprint 16
/ #122.

## Delivered boundaries and necessary-only future features

Current/live Market Structure was delivered by Sprint 18 / Issue #148 under
[Plan 31](plans/31-current-supplied-cohort-market-structure-contract.md) and
merged PR #149. It uses one complete Upstox raw OHLC basis for the exact
21-session window; a yfinance adjusted close never fills or changes an Upstox
candle.

Sprint 19 / Issue #152 delivered threshold-free S19/S20 Price Action under
[Plan 32](plans/32-current-supplied-cohort-price-action-contract.md) and merged
PR #153. Named patterns, levels, lines, channels, formations, zones, Volume,
Relative Strength, Liquidity/SMC, signals, historical qualification, and
delivery surfaces remain outside that delivered slice.

Issue #154 closed/completed through PR #157 after accepting
[Plan 33](plans/33-efficient-continuous-nifty100-capture-contract.md). Issue #156
owns that separately bounded implementation. Owner-prioritized maintenance
Issue #145 implements the
[cross-module internal-error policy](architecture-freeze-v1.md#internal-errors-and-operator-diagnostics)
without adding a product module, provider acquisition, or evidence vocabulary.
Its review and release evidence are tracked in the Issue before another product
module starts.
Sprint 17 / Issue #147 has completed its separate `4/4` temporal captures. Its
final historical qualification no longer waits on future-session evidence.

[Plan 34](plans/34-swing-research-feature-map.md) records the necessary-only
future-feature gate. A possible Price Action, Volume, Relative Strength, or
Liquidity/SMC fact is not a promised backlog feature. It must first prove a
distinct unmet and practical listed-equity swing-research, analysis, scanning,
or screening need; prefer the smallest direct causal fact and otherwise do not
build it.
Optional analytical facts remain additive by default. They do not silently form
an all-feature `NO_TRADE` filter; any later mandatory filter must demonstrate
incremental value without collapsing useful candidate coverage.

## Future packaging outside current WIP

[Issue #126](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/126)
is future low-priority work for a standalone `swing-trading-market-data` PyPI
distribution while the full application remains installable. Both distributions
must consume one authoritative market-data codebase with no copied provider
logic. This packaging outcome is not part of Sprints 11–18 and must not reopen
completed Issues #125/#127/#132, Sprint 11, Sprint 12, or Sprint 13, alter
future Plan-23 migrations, or expand the delivered Sprint 14 scope.

## Deferred and superseded historical records

Issue #121 is closed/completed and supplies the current foundation. Issues #111 and #115 are **closed /
not planned** with no published implementation. Plans 12 and 17 retain their
original evidence and conclusions as historical records; deferred Plan 18 is
linked to #120/#122. None are declared wrong at the time.

The former contemplated official-inquiry content SHA-256
`a2d762cd93dfca56d5623e260816c1aee0a6ae2a9a400097cc6f2d51c77f6412` and
authorization-payload SHA-256
`84797b9c424aa6da36d46b1b516f3cbe08d8205801d296953a5edf474d2ffe85` were
revoked before send. No inquiry email, provider contact, provider call,
credential use, or acquisition occurred. These are not Plan 11's historical
public-page research receipt hashes.
