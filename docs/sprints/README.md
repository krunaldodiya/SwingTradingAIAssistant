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
  ARK-175 through ARK-181 now remain Done in Linear. The
  [Sprint 8 record](sprint-8.md) preserves its historical pending-reconciliation
  snapshot; this index records the current operational truth without rewriting
  the delivered evidence.
  Exact SHAs `25d889a` and `d79eecc` remain superseded rejected revisions, not
  final evidence. PR #102 remains immutable historical planning/specification
  evidence. Official taxonomy, Layer B, provider/public transport, live results,
  recommendation, ranking, and effectiveness remain deferred or unclaimed.
- [Sprint 9 — Market Regime Layer B acquisition decision](sprint-9.md) —
  **IMPLEMENTED / VERIFIED** with terminal decision `BLOCKED`; publication is pending.
  Linear records parent Task `ARK-183` as **In Progress**; its child contract
  Story `ARK-184` is **In Progress** and blocks its child implementation Story
  `ARK-185`, which is **Todo**.
  Plan 16 specifies a provider-independent pure reducer whose only authority is one
  reviewed canonical manifest sealed in the candidate build; the initial absent
  seal fails closed and stdin cannot supply authorization. One owner-supervised
  release invocation may issue one credential-free GET of the fixed candidate
  PDF within a 1,048,576-byte cap and an outer monotonic 30-second watchdog.
  Exactly-once is supervision plus retained run evidence, not adapter replay
  prevention; no live-probe CLI exists. Provider HTTP metadata remains in
  `market_data`, while the decision sees only a manifest-authenticated capability
  identity/state.
  The one authorized invocation emitted a sanitized historical receipt whose old
  worker could attempt another resolved address. Its one-call/one-attempt
  counters are unverified, so the receipt is inadmissible as capability evidence;
  no provider-independent projection was retained. The invocation is consumed.
  With the build seal still `None`, the terminal result is `BLOCKED`
  with first blocker `SEALED_MANIFEST_MISSING`; it grants no acquisition,
  readiness, admission, Market Regime label, or later execution authority.
