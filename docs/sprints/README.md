# Sprint records

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
- [Sprint 3 — Nifty 50 downloader v1](sprint-3.md) — the seven-slice preview is
  accepted historical evidence and the downloader-v1 release candidate is in
  final publication verification; Plan 01 continues to block research-module
  implementation until that release closes.

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

  Historical work is deferred: Plan 18 supports Sprints 15–16 (#120/#122);
  historical news/events/sectors are not-yet-evaluated, not permanently
  removed. Issues #111 and #115 are **closed / not planned** with no published
  implementation. Plans 12 and 17 and their exact evidence remain preserved
  historical records without a claim they were wrong when made.
  Current/live-first is sequencing only. Sprint 15 preserves the historical
  store and point-in-time evidence/availability ledgers; Sprint 16 preserves the
  validation and pre-Market-Structure gate. Their scope still includes
  historical backtests; look-ahead, survivorship, selection, and data-snooping
  controls; separate in-sample, walk-forward, out-of-sample, and untouched-test
  regions; forward/paper testing; realistic costs/slippage; and point-in-time
  membership, sector, corporate-action, and source provenance. Unavailable
  features remain explicit at each cutoff without fabrication or later
  backfill, and do not block unrelated declared study profiles. No initially
  planned feature is removed.
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
  unsupported/insufficient before proven coverage. Automated/licensed
  acquisition, general news, other providers/types/surfaces, semantic correction
  graphs, external attestation, licensed history, sentiment/ranking, and Sprint
  14 packet integration remain deferred. Sprint 14 /
  [Issue #119](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119)
  is next and unblocked but **NOT STARTED**; no Sprint 14 planning, source, or
  implementation decision is recorded by this closeout.

- Future packaging outside the sprint/WIP-one sequence —
  [Issue #126](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/126)
  is open, low priority, and standalone. It may later publish one authoritative
  market-data codebase as `swing-trading-market-data` while the full application
  remains installable. It must not duplicate implementation, reopen completed
  Issues #125/#127/#132, Sprint 11, or completed Sprint 12, alter future
  Plan-23 migrations, or pre-empt the closed Sprint 13 record.
