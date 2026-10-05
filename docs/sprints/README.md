# Sprint records

- [Sprint38: coherent candidate evidence](sprint-38.md) — Issue258/Plan52; pre-delivery checkpoint, live Issue owns final lifecycle.
- Sprint37 is live-verified closed through PR257, main admission and private publication; earlier checkpoints below remain historical.

- [Sprint37: candidate completed-session age](sprint-37.md) — Issue256, Plan51; pre-delivery checkpoint, live Issue owns final evidence.
- Sprint36 is live-verified closed through PR255, exact main admission and private publication37265639697. Earlier pending/current wording is historical.

- [Sprint36: evidence-based candidate invalidation](sprint-36.md) — Issue254, Plan50; live Issue owns current delivery evidence.
- Sprint35 is closed through PR253, main admission and private publication; its earlier checkpoint below is historical.

- [Sprint 35: candidate event continuity](sprint-35.md) — Issue #252, Plan49; implementation/review pending.

Current bounded delivery: [Sprint 32 — Loss Beyond the Stop Price](sprint-32.md),
[Issue #244](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/244),
[Plan 46](../plans/46-loss-scenario-assumed-exit.md). Earlier entries remain historical.

GitHub Issues and the private
[SwingTradingAIAssistant Delivery](https://github.com/users/krunaldodiya/projects/1)
Project are the operational source of truth for new backlog, hierarchy, status,
priority, estimate, work type, and risk. GitHub milestones own sprint
assignment. Existing Linear `ARK-*` records are read-only historical evidence
and are not migrated into the active GitHub backlog. This directory preserves
concise sprint goals, outcomes, review evidence, carryover, and retrospective
decisions with the codebase.

Use one file per sprint. Do not duplicate every Issue description; link or list
Issue identifiers and capture only information needed to understand the shipped
increment and future process decisions.

The owner-level minimum dependencies for Sprint 10 through the boundary before
Market Structure are in [Upcoming Sprints Overview](../upcoming_sprints_overview.md).

[Issue #130](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/130)
now separates reusable listed-equity feature cores from higher-level universe
policy. Product qualification and default workflows focus on the point-in-time
Nifty 50 plus Nifty Next 50; explicitly supplied supported stocks outside that
default may use a capability only with canonical identity and all required
evidence. Historical sprint files retain their original names, cardinalities,
scope, and evidence and must not be rewritten as if delivered features were
already generic. The evidence-based coupling audit and ordered incremental
remediation are in
[Plan 23](../plans/23-instrument-agnostic-feature-boundary-and-coupling-audit.md).

## Index

- [Sprint 29 — Single-stock loss scenario](sprint-29.md) — governed by [#237](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/237); live Issue owns delivery state.

- [Sprint 0 — Foundation](sprint-0.md) — closed by [PR #1](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/1), merged to `main` as `0a518813ec26d32945ce49d1f27999e8618f64cc`.
- [Sprint 1 — Resumable one-minute storage](sprint-1.md) — delivery closed at
  21/21 by [PR #23](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/23),
  merged to `main` as `314587e9dae9c1d96b180a7b254d94ef86295259`; documentation
  reconciliation followed in [PR #25](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/25),
  merged as `a3d2f0ccac641030f40c87076e55f5754d650b28`. PR #24 and PR #2 are
  closed, unmerged replacement/obsolete work and are not closure evidence.
- [Sprint 2 — RELIANCE operational proof](sprint-2.md) —
  [closeout candidate](sprint-2-closeout.md) for 21/24 delivered tasks with
  ARK-92, ARK-93, and ARK-69 carried over; Milestone 2 remains blocked and is
  not accepted.
- [Sprint 3 — Nifty 50 downloader v1](sprint-3.md) — closed; the downloader-v1
  release gate passed through [PR #82](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/82),
  merged as `23b07d0c6204de230e5cebe17c8f54001751b253`. The seven-slice preview
  and final publication evidence remain historical records; this completed
  prerequisite no longer blocks research-module implementation.

- Sprint 4 — Five-session opportunity census — closed by [PR #91](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/91), merged as `82f62107eb78ef696121edf096de7801d370970d`; the sealed result was 1,550/1,550 insufficient evidence and made no predictive claim.
- Sprint 5 — Prospective Evidence Readiness v1 — closed by [PR #92](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/92), merged as `21cd9f9acbb976e9f29298e0f45dbcdf83167897`; the provider-free prerequisite manifest fails closed with `DECLARATION_RECEIPT_MISSING` and zero attempts.
- [Sprint 6 — Market Regime v1 specification](sprint-6.md) — closed by [PR #93](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/93), merged as `46daa690b75ae1bedbdbb76633b167bfac5a6a1d`; Sprint 6 itself claimed no observed regime, and the later Sprint 8 slice reuses the now-implemented observed reducer.
- [Sprint 8 — Sector Analysis: atomic Sector Participation v1 slice](sprint-8.md) —
  repository delivery, review, and publication are complete for the corrected
  2026-08-13 through 2026-08-19 window. The provider-free in-process reducer
  accepts trusted verified Market Regime facts and a resolved snapshot, then
  derives and consumes the exact-50 private handoff internally in the same call;
  callers have no handoff authority and no public delivery exists.
  Final reviewed head `411b21d4874206563b64d03ce8024953430660d2`
  received independent exact-SHA quality **APPROVE** and security **PASS**.
  The final focused gate was **96 passed**; the repository gate was **2,445
  passed** at **92.96%** coverage with Ruff/format/Vulture **PASS** and Pyright
  **0 errors, 0 warnings**; documentation evidence was **60 passed**. Hosted CI
  [run 31832620021](https://github.com/krunaldodiya/SwingTradingAIAssistant/actions/runs/31832620021)
  and GitGuardian passed.
  [PR #103](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/103)
  merged to `main` at **2026-08-14T19:39:18Z** as
  `b6e34d3cdc598e1cd6dc50c50d517481d26e1391`.
  ARK-175 through ARK-181 are Done in Linear and remain read-only historical
  evidence. They are not copied into GitHub. Repository Sprint delivery is
  complete.
  Exact SHAs `25d889a` and `d79eecc` remain superseded rejected revisions, not
  final evidence. PR #102 remains immutable historical planning/specification
  evidence. Official taxonomy, Layer B, provider/public transport, live results,
  recommendation, ranking, and effectiveness remain deferred or unclaimed.
- [Sprint 9 — Market Regime Layer B acquisition decision](sprint-9.md) —
  terminal decision `BLOCKED / CAPABILITY_EVIDENCE_MISSING`.
  This is a historical record, not an active dependency after the
  current/live-first priority reset in Issue #121.
  The corrected build seals canonical incomplete manifest identity
  `53717e75d9e93344d7df55ea2a5e94e48e133ff0ad673f27e38ba040cc91bb2f`
  from scope projection identity
  `07f235b246e88d30404ddf1574e13907f436c937144e40abf4766c4463cb759e`
  and source-controlled prerequisite assessment
  `2026-08-15T16:03:40.000000Z`. Its canonical report identity is
  `dbbc0bdf32cf081d491a119c05571bebf4dbd274bae858dd0e3d418b96bd1408`.
  The capability group and all later evidence, approval, authorization, and
  validation-receipt identities are null; the assessment instant grants no
  authority.
  [PR #107](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/107)
  remains historical implementation publication evidence. It merged to `main`
  at **2026-08-15T15:40:16Z** as
  `c74ee4788aa6d03864eb8c21f111afe7025ad9cc`, but did not contain this
  correction. Linear ARK-183, ARK-184, and ARK-185 remain historically
  **Done** with PR #107 attached; those tracker states do not publish or
  authorize the correction.
  The consumed probe's historical receipt remains inadmissible as capability
  evidence because its old worker could attempt another resolved address; no
  provider-independent projection was retained or reconstructed, and no rerun
  occurred. Commit identity, exact-revision reviews, hosted checks, merge, and
  publication for the correction are external lifecycle evidence; this index
  asserts no current lifecycle state for them. The correction grants no
  acquisition, readiness, admission, label, or later execution authority.
- Former Sprint 10 proposal — Market Regime Layer B evidence-acquisition
  readiness — [Plan 17](../plans/17-market-regime-layer-b-evidence-acquisition.md)
  preserves the historical **`BLOCKED / CAPABILITY_EVIDENCE_MISSING`** record.
  GitHub Issues
  [#111](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/111)
  and
  [#112](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/112)
  retain the earlier planning context; #111 is closed as not planned after the
  current-first reprioritization. No acquisition or implementation started, and
  this historical record grants no provider access or runtime authority. It is
  not the current Sprint 10 record and does not link to `sprint-10.md`.
- [Sprint 10 — Current supplied-cohort market data](sprint-10.md) —
  [GitHub Issue #121](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/121)
  is **closed/completed** and supplies the current foundation. It makes existing
  `market-data` usable for a supplied 1–50 Nifty 50 equity cohort, returning
  bounded current price/volume facts: latest completed daily OHLCV and only
  explicit/available `PARTIAL_CURRENT_SESSION` context. Every admitted fact is
  immutably archived with temporal availability metadata; invalid identity or
  incomplete required evidence fails closed, and a partial session is never a
  completed daily bar or historical close. It does not calculate Market Regime,
  sector, news/events, signals, recommendations, or orders.
  [Plan 19](../plans/19-current-supplied-cohort-market-data-contract.md) is the
  Sprint 10 specification.

- [Sprint 11 — Current supplied-cohort Market Regime](sprint-11.md) is
  **closed/completed** under
  [Issue #116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116).
  Its dependencies [#125](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/125),
  [#127](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/127), and
  [#132](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/132)
  merged before
  [PR #124](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/124)
  delivered V2 comparability semantics and merged reviewed head
  `d56120fb5966dffea32207b59f1edf0673b2e51b` as merge commit
  `f03edf3690e34e25a57b58a15450129e3bf9a5e9`.
  Local evidence was 296 focused tests, 2,867 full tests, 91.03% coverage, Ruff
  format/check, Pyright, Vulture 80, build, and sealed no-network and live
  current-prospective smokes. Hosted Quality/build and GitGuardian passed.
  Frozen exact-50 V1 records remain historical; future
  [Plan 23](../plans/23-instrument-agnostic-feature-boundary-and-coupling-audit.md)
  migrations remain separate. Sprint 12 subsequently closed under Issue #117;
  the Sprint 11 closeout itself granted no Sprint 12 completion evidence.

  Historical Sprints 15 and 16 are closed/completed. Plan 28 delivered the
  bounded source-backed retained-Upstox raw daily revision store for #120, and
  Plan 29 preserved capability-aware validation over supplied immutable
  evidence for #122. Historical news/events/sectors remain not-yet-evaluated,
  not permanently removed. Neither sprint inferred historical index membership
  or automatically owned point-in-time membership, sector/classification,
  news, event, or corporate-action snapshot construction or acquisition.
  Missing evidence remains explicit at each cutoff, without fabrication, later
  backfill, silent neutralization, or dropped dates. Sprint 17 / #147 completed
  its four capture-forward sessions and `OHLCV_ONLY` qualification through
  PR #166; other profile limitations remain explicit in its closeout.
  Sprint 18 / #148 and Sprint 19 / #152 are closed/completed current/live deliveries.

  Broader bounded per-decision-date as-of research snapshot construction belongs
  to Issue #139 and a separate accepted contract; it depends on #120/#122 unless
  the owner changes the ordering and does not expand either issue. Issues #111
  and #115 remain **closed / not planned** with no published implementation.
  Plans 12 and 17 retain their exact historical evidence. The architecture
  sequence, Plan-20 V1/V2 freeze, and Plan-26 non-shipping historical WIP rules
  remain unchanged.
  The contemplated official-inquiry content SHA-256
  `a2d762cd93dfca56d5623e260816c1aee0a6ae2a9a400097cc6f2d51c77f6412` and
  authorization-payload SHA-256
  `84797b9c424aa6da36d46b1b516f3cbe08d8205801d296953a5edf474d2ffe85` were
  revoked before send. No inquiry email, provider contact, provider call,
  credential use, or acquisition occurred. They are distinct from Plan 11's
  historical public-page research receipts.

- [Sprint 12 — Current supplied-cohort Industry Analysis](sprint-12.md) is
  **closed/completed** under
  [Issue #117](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/117)
  and [Plan 24](../plans/24-current-supplied-cohort-sector-analysis-contract.md).
  [PR #135](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/135)
  merged exact reviewed head `b8c416709ebae82879c5dceae603b141b0dd1fa8`
  as merge commit `4dfa8ecd1854aec4b4b2181cf2d0310072f65b49`.
  Independent quality review returned **APPROVE** and security review returned
  **PASS**. Local gates passed 2,991 tests at 90.82% coverage, Ruff
  format/check, Pyright, Vulture 80, and build; hosted Quality/build and
  GitGuardian passed. Issue #117 is closed and its Project item is **Done**.
  The exact 100-row, 6,610-byte official parser smoke has SHA-256
  `5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85`;
  it is parser provenance only, not live participation or effectiveness
  evidence. The delivered contracts use literal `Industry`, not official
  Sector taxonomy, and all source/licence limits, nonclaims, frozen V1
  preservation, and explicit deferrals remain in force.

- [Sprint 13 — Current supplied-cohort event notices](sprint-13.md) /
  [Issue #118](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/118)
  is **closed/completed** under
  [Plan 25](../plans/25-current-supplied-cohort-event-notice-contract.md).
  [PR #137](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/137)
  merged independently reviewed head `2b65aa46f3f67552bf600675c6f1a5c09d363e12`
  as merge commit `75ca9c3d3302f6d0a46ac772099c7b4d65e041c3`.
  Independent functional review returned **APPROVE** and security review
  returned **PASS**. Exact committed local gates passed Ruff format/check,
  Pyright 0/0, Vulture 80, `uv build`, `git diff --check`, and 3,038 tests at
  90.68% coverage; hosted Quality/build and GitGuardian passed on the reviewed
  head. Issue #118 is closed, its Delivery Project item is **Done**, and it is
  the Sprint 13 milestone. The delivered operator-acquired unfiltered official
  NSE Equity `1D` CSV path is attributed owner-private personal/noncommercial
  local use only, with exact cohort/provenance, typed failures, immutable
  archive-owned `known_at`, and retain-before-return; no automated collection,
  attachment fetch, redistribution, sentiment, recommendation, signal, or order.
  The 8,016-byte, 20-row official artifact SHA-256 is
  `a395f454dd39b3befd14ac2f1b3e0dce312c8ba0441098b80e596be172749210`.
  Production parse/project/real `StorageRootLease` archive-and-retry produced
  one `GODREJCP` / `INE102D01028` notice and
  `NO_MATCHING_NOTICE_IN_SNAPSHOT` for `TCS` / `INE467B01029`; this is
  parser/projection/retention evidence only, not source completeness, live
  participation, historical coverage, commercial permission, correction lineage,
  recommendation quality, or effectiveness. Prospective archive only and
  explicit unavailable history remain policy: `OHLCV_ONLY` cannot validate
  news/event behavior, and `OHLCV_PLUS_NEWS_EVENTS` fails
  unsupported/insufficient before proven coverage. Polling/systematic history,
  general news, other providers/types/surfaces, semantic correction graphs,
  external attestation, licensed history, and sentiment/ranking remain
  deferred.

- [Sprint 14 — Current supplied-cohort research packet](sprint-14.md) /
  [Issue #119](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119)
  is **DELIVERED/CLOSED — PR #140 MERGED; ISSUE #119 CLOSED/COMPLETED; DELIVERY PROJECT ITEM DONE; SPRINT 14 MILESTONE; EXACT REVIEWED HEAD APPROVED/PASSED; ALL REQUIRED CURRENT SMOKES, 852 FOCUSED, 3,400 FULL AT 89.53% COVERAGE, ALL EXACT-CURRENT LOCAL GATES, HOSTED QUALITY/BUILD, AND GITGUARDIAN PASSED** under
  [Plan 27](../plans/27-current-same-pass-market-regime-contract.md).
  The owner selected the current same-pass successor after operational evidence
  showed zero usable Plan-20 21-object prospective inputs. Current availability
  does not depend on prior tool runs: it resolves the latest 21 completed
  official sessions, admits exact approved evidence available now with truthful
  current `known_at`, and permits only a separately labelled provisional
  `PARTIAL_CURRENT_SESSION`. Plan-20 V1/V2 remain frozen/delivered. Plan-26
  packet `@v1` is unpublished WIP superseded before delivery, will not ship, and
  has no alias; its 101 focused tests are historical WIP/repair evidence only.
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
  nonfatal, and never substituted. Exact retries preserved bytes, identities,
  and original times and caused zero effects; source remained unchanged and all
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
  Linux with identical evidence guarantees. Native Windows is unsupported and
  not claimed; Windows users use Linux through WSL2 or Docker. Hosted Quality/build and GitGuardian passed on the exact reviewed head.

  The fresh current-byte genuine IRCTC production negative passed with the exact
  `NO_TRADE` outcome: raw `INSUFFICIENT` / `RAW_ACQUISITION_UNAVAILABLE`; Market
  Regime V3 insufficient; Plan 22 `NOT_ATTEMPTED` upstream; Industry V2
  `UNSUPPORTED` with `MARKET_REGIME_UNAVAILABLE` and
  `CLASSIFICATION_MEMBER_UNSUPPORTED`; and Packet insufficient with the exact
  ledger, five null AI facts, and mandatory `NO_TRADE`. Guarded V3, Industry,
  event, and Packet retries preserved exact bytes, identities, and original
  times. All required current smokes have passed: the retained post-close
  `RELIANCE` positive, mandatory market-hours `RELIANCE` positive, and genuine
  IRCTC negative. The two positive modes remain separate; neither substitutes
  for the other. The two PR #140 P2 blockers are fixed. All exact-current local gates pass. PR #140 is merged; exact reviews and hosted gates passed; Issue #119 is closed/completed; its Delivery Project item is Done; Sprint 14 is delivered/closed as the research-only milestone, with no autonomous trading or financial-advice claim.

- Sprint 15 — source-backed fixed-cohort historical daily raw OHLCV store /
  [Issue #120](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/120)
  is **closed/completed** with Project status **Done**.
  [Plan 28](../plans/28-fixed-cohort-historical-ohlcv-revision-store-contract.md)
  delivered the bounded retained-source `UPSTOX_RAW` daily revision-store slice.

- Sprint 16 — capability-aware historical validation and pre-structure gate /
  [Issue #122](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/122)
  is **closed/completed** with Project status **Done**. Plan 29 retains its
  fail-closed study-profile, availability-ledger, identity, cutoff, and
  separated evaluation-region controls.

- Sprint 17 — capture-forward adjusted OHLC historical qualification /
  [Issue #147](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/147)
  is closed/completed with Project status **Done**. The Plan-30 runtime and all
  four distinct completed-session captures are retained; unchanged Plan 29
  approves the `OHLCV_ONLY` profile. PR #166 delivered the reviewed closeout.

- Sprint 18 — current supplied-cohort Market Structure /
  [Issue #148](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/148)
  is closed/completed with Project status **Done**. Plan 31 was delivered through
  merged PR #149.

- Sprint 19 — current supplied-cohort Price Action /
  [Issue #152](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/152)
  is closed/completed with Project status **Done**. Plan 32 was delivered through
  merged PR #153.

- Issue #155's governing merge delivered the reviewed Plan 30 runtime
  prerequisite. Issue #147 subsequently closed through PR #166. Issues #156
  and #145 are also closed; they are completed historical prerequisites, not
  the remaining delivery lane. The historical #156 refused probe remains
  `INVALID / NO VERDICT`. Parent #172's slices #186–#189 are delivered;
  #190 owns the remaining measured-efficiency delivery and parent reconciliation.
  [Plan 34](../plans/34-swing-research-feature-map.md) records the necessary-only
  gate for any later swing-research feature; no named pattern, Volume, Relative
  Strength, or Liquidity/SMC possibility is an automatic backlog commitment.

- Future packaging outside the sprint/WIP-one sequence —
  [Issue #126](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/126)
  is open, low priority, and standalone. It may later publish one authoritative
  market-data codebase as `swing-trading-market-data` while the full application
  remains installable. It must not duplicate implementation, reopen completed
  Issues #125/#127/#132, Sprint 11, or completed Sprint 12, alter future
  Plan-23 migrations, or pre-empt the closed Sprint 13 record.
