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
  migrations remain separate. Sprint 12 is now active under Issue #117; the
  Sprint 11 closeout grants no Sprint 12 implementation or completion evidence.

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
  **IN PROGRESS — NFKC-PRIVATE CANDIDATE LOCALLY VERIFIED; EXACT-SHA REVIEW
  AND DELIVERY PENDING** under
  [Issue #117](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/117).
  [Plan 24](../plans/24-current-supplied-cohort-sector-analysis-contract.md)
  owns the exact contract. The sixth independent R3 quality/security review
  returned `REQUEST_CHANGES` / `FAIL` and drove NFKC(casefold) boundary-free
  Company Name privacy, exact top-level structural guards, conservative
  archive-completion `known_at` clarification, and the Plan 20 lifecycle
  correction. The repaired candidate passed 331 focused tests plus 34
  documentation checks and all full local gates: 2,978 tests at 90.88%
  coverage, Ruff format/check, Pyright, Vulture 80, and build. The saved
  official artifact admitted exactly 100 rows and 6,610 bytes with SHA-256
  `5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85`,
  schema identity
  `7bc49d5eac26551c9ae0b76b4dd7b9edf9861ccca7d73fb7ea04f6c4f72f0415`,
  null publisher fields, and a redacted repr as parser provenance only. Trusted
  `known_at` is final archive-completion time, so retention completed after the
  decision cutoff remains future-known even if acquisition preceded it. All
  prior rounds are superseded trace. Commit the exact candidate next, then
  obtain fresh independent `APPROVE` / `PASS` against that exact SHA. Pull
  request, hosted CI/GitGuardian, merge, and Issue closure remain pending. All
  source/licence limits, frozen V1 preservation, and explicit deferrals remain
  in force.

- Future packaging outside the sprint/WIP-one sequence —
  [Issue #126](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/126)
  is open, low priority, and standalone. It may later publish one authoritative
  market-data codebase as `swing-trading-market-data` while the full application
  remains installable. It must not duplicate implementation, reopen completed
  Issues #125/#127/#132 or Sprint 11, alter future Plan-23 migrations, or alter
  active Sprint 12 scope.
