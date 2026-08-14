# Sprint records

Linear is the operational source of truth for backlog, hierarchy, status, and
sprint assignment. This directory preserves concise sprint goals, outcomes,
review evidence, carryover, and retrospective decisions with the codebase.

Use one file per sprint. Do not duplicate every issue description; link or list
issue identifiers and capture only information needed to understand the shipped
increment and future process decisions.

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
  In Progress for the corrected 2026-08-13 through 2026-08-19 window. Its
  provider-free in-process reducer accepts trusted verified Market Regime facts
  and a resolved snapshot, then derives and consumes the exact-50 private
  handoff internally in the same call; callers have no handoff authority. A
  label containing a full constituent ISIN case-insensitively or matching a
  constituent symbol case-insensitively as a complete `[A-Z0-9.&_-]` token now
  returns whole-result `SECTOR_CLASSIFICATION_CORRUPT` with no sector rows.
  Non-identity singleton groups remain allowed solely within the authenticated
  nonanonymous owner-private boundary; no public delivery exists. Exact SHA
  `25d889a` received **REQUEST_CHANGES** for the identity-label defect and is
  superseded by its TDD repair. The prior complete two-file focused run was
  **49 passed**; the identity-regression run was **4 passed**, and the subsequent
  complete two-file run is **53 passed**, with Ruff **PASS** and focused Pyright
  **0 errors, 0 warnings**.
  ARK-175 through ARK-178 remain Done historical specification work, ARK-179
  remains the integrated In Progress goal, ARK-180 is Done with implementation
  evidence, and ARK-181 is the sole active child, In Progress pending integrated
  review. The repaired repository gate is Ruff/format/Vulture **PASS**, Pyright
  **0 errors, 0 warnings**, and **2,443 passed** at **92.97%** coverage. A sealed
  exact-revision review, publication, and closure remain pending. PR #102
  remains immutable planning evidence; no official
  taxonomy, provider, delivery transport, recommendation, live result,
  effectiveness, approval, merge, or publication claim is made.
