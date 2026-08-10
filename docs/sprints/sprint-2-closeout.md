# Sprint 2 closeout and Milestone 2 disposition

Status: **CLOSEOUT CANDIDATE — MILESTONE 2 BLOCKED**

This record becomes the Sprint 2 closeout when its exact reviewed revision is
merged, hosted checks pass, and ARK-72 is synchronized to Done in Linear. It
closes the one-week delivery timebox with explicit carryover; it does not waive
Plan 03, accept a rejected candidate, or claim that Milestone 2 is complete.

## Outcome

- Sprint goal: prove the existing RELIANCE one-minute pipeline's deterministic
  correctness, recovery, request-minimal behavior, query boundary, and bounded
  measurement support before scaling.
- Frozen denominator: **24 executable tasks**.
- Completed before ARK-72 publication: **20/24 (83.3%)**.
- Final delivery result: **21/24 (87.5%)**, conditional only on this exact
  ARK-72 closeout candidate completing its review, hosted checks, merge, and
  Linear synchronization.
- Carryover: **ARK-92, ARK-93, ARK-69**.
- Milestone 2 disposition: **BLOCKED / NOT ACCEPTED**.
- Exact accepted `main` starting point for this dossier:
  `323e40baed4abf420610c7affa6d4fa170ba9207`.

The three carryover tasks retain their historical Sprint 2 labels so the
denominator and schedule variance remain honest. They are Backlog work, not
completed work or silent denominator removal.

## Mandatory Plan 03 acceptance crosswalk

A blocked row is not partial acceptance. It remains a named prerequisite for
Milestone 2 and any later threshold, live-provider, scaling, or release claim.

| Milestone 2 requirement | Status | Evidence and disposition |
| --- | --- | --- |
| Repeated download is idempotent | PASS | ARK-70 proves verified skip and local recovery with zero historical requests; accepted evidence is contained in the starting `main` revision. |
| Interruption is safe | PASS | ARK-83 proves the frozen cancellation and crash-state mapping with no later request. |
| Corrupt/incomplete partition is detected and repaired | PASS | ARK-85 and ARK-73 prove exact invalidation and target-only disposable repair. |
| Internal gaps are detected; no `MAX(ts)` shortcut | PASS | ARK-84/85 prove schedule-bound coverage failure without a maximum-timestamp shortcut. |
| Duplicates and impossible OHLC fail correctly | PASS | ARK-86 proves exact duplicate normalization and conflicting/impossible input failure. |
| Empty successful response is explicit | PASS | ARK-86 proves `EMPTY_RESPONSE` without publication or fabricated evidence. |
| Raw candle files remain immutable | PASS | ARK-87 proves unchanged bytes and checksum without overwrite. |
| Holidays and special sessions are explicit | PASS | ARK-84 proves supplied schedule evidence governs sessions and closures. |
| Late listing / legitimate no-trade handling | BLOCKED | Deterministic handling fails closed, but no authoritative live observation or approved exception contract exists. |
| No forward fill | PASS | ARK-84 proves missing scheduled bars stay missing and fail visibly. |
| Random/monthly sample matches direct response | BLOCKED | ARK-69 was not run; no live response or same-response comparison exists. |
| Query proof | PASS | ARK-91 proves the configured DuckDB direct-Parquet aggregate without a candle copy. |
| Request minimal and zero-request resume | PASS | ARK-70 and the reconciliation proofs retain zero-request local paths and bounded request selection. |
| Resource/performance evidence | BLOCKED | ARK-92 has no accepted durable five-sample artifact and ARK-93 has no threshold decision. No threshold was invented. |
| Live representative proof | BLOCKED | ARK-69 remains unexecuted. No live Upstox request was made and no credential or private response was retained. |

## ARK-92 terminal evidence

The last exceptional persistence candidate was
`44f589444a5e7cfd883a210c19308b7a19720aae`. Its attached deterministic gate
passed Ruff, Pyright, Vulture, and **1,131 passed in 351.88s** with **88.26%**
coverage. Native Sol review session
`019fe9da-4654-7290-9b69-fd2614c7a774` nevertheless rejected it because
non-success record matrices, protocol-invalid pairing, obfuscated SQL
sanitization, and work-root substitution defenses remained incomplete.

Automated success therefore did not override the static acceptance findings.
The one-shot benchmark collection remains unused: no benchmark artifact,
provider call, credential action, PR, or merge came from the rejected
candidate.

ARK-111 is the one cohesive redesign of that persistence boundary. It is
planning/specification work outside this Sprint 2 denominator. Later work must
approve the smaller contract before implementation, preserve smoke-first
hostile checks, and keep no issue-per-finding fragmentation.

## Delivered increment

Sprint 2 delivered the deterministic offline evidence for admission, storage
ownership, catalog failure, recovery, cancellation, schedule coverage,
normalization/quality, immutable Parquet storage, request-minimal range
reconciliation, benchmark instrumentation, and direct-Parquet queries. These
are meaningful operational foundations for the downloader, but they are not a
fully accepted live downloader milestone because the durable benchmark,
threshold, and one-attempt live proof remain incomplete.

Nothing in this closeout authorizes multi-instrument scaling, a public package,
strategy logic, backtesting, recommendations, order placement, F&O, or another
provider integration.

## Retrospective

### What worked

- Atomic deterministic cases found boundary defects without provider use.
- Isolated worktrees, exact revisions, independent review, and hosted checks
  protected user-owned work and prevented a green test suite from being
  mistaken for complete acceptance.
- Typed failures, immutable files, schedule provenance, and zero-request paths
  now have strong reusable evidence.

### What did not work

- ARK-92 combined measurement collection, durable serialization, sanitization,
  hostile filesystem publication, and one-shot operational evidence into one
  acceptance surface. The review surface was too large.
- Repeated full six-minute gates occurred before the hostile persistence matrix
  was fully closed, producing avoidable elapsed time and rework.
- The raw five-sample report was initially kept only in memory, so ARK-93 did
  not receive an immutable accepted input.

### Corrective actions

- Apply the merged smoke-first ladder: static and adversarial unit checks,
  affected suite, then one full gate on a sealed candidate.
- Use ARK-111 to freeze one smaller persistence specification before any code or
  collection. Keep one cohesive redesign and no issue-per-finding fragmentation.
- Pre-register the eventual one-shot command and durable artifact boundary
  before executing any expensive collection.
- Ground Sprint 3 capacity in the 21/24 delivery result and the three explicit
  carryover tasks rather than the earlier throughput rate.

## Next planning gate

ARK-106 may prepare Sprint 3 only after this closeout is reviewed, merged, and
ARK-72 is Done. Sprint 3 planning must decide where ARK-111, ARK-92, ARK-93,
and ARK-69 fit against capacity. It must not treat Milestone 2 as accepted or
start ARK-12 scaling merely because the Sprint 2 timebox is closed.
