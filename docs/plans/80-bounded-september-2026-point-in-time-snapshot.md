# Plan 80: bounded point-in-time research evidence snapshot

Status: accepted bounded implementation contract under [Issue #335](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/335), slice 1 of Future [#139](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/139). Owner and risk owner: Krunal Dodiya. Risk tier: R3 financial-research evidence, immutable persistence, temporal trust. Base: `9c405ca007f20949a90ecfffb7844e168548777c`.

## Context

Owner direction (2026-10-18, recorded on [#332](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/332)) authorizes a point-in-time historical test for September 2026 over the Nifty 100. The evidence audit for this contract established, from retained capture-forward sessions only:

- Retained per-session capture revision stores cover sessions 2026-08-19 through 2026-09-25 for the Nifty 100 (history-backfill retrieved 2026-09-18; daily sessions 2026-09-11..2026-09-17 including the escalation session 2026-09-17; backfill sessions 2026-09-18, 22..25 retrieved 2026-09-26).
- For decision sessions 2026-09-21..2026-09-25, every one of the 100 selection members has one admissible bar per session for the exact 21-session window ending at that session at admission cutoff `2026-09-26T12:00:00Z`.
- No duplicate or conflicting cell exists for those members; the 100 complete members equal the retained capture selection exactly.

## Outcome and smallest working slice

The deterministic tool can assemble and immutably retain one `point-in-time-research-evidence-snapshot@v1` per bounded request — an ordered decision-session grid, a cohort resolved from retained selection evidence, and one admission cutoff — from retained capture-forward evidence only. Every admitted bar binds its capture revision, request identity, observed-at, retrieved-at, raw response identity, session, and member identity. Missing, late, conflicting, or absent evidence produces an explicit typed insufficiency. Current-vintage values are never relabelled as point-in-time evidence.

The slice answers one concrete question: *which point-in-time 21-session evidence windows for the declared decision sessions and cohort are fully retained by the cutoff, and which are not?*

## Non-goals (typed boundaries, no expansion inside this slice)

Market-structure facts, setup or policy evaluation, observation pairs, decisions, candidates, outcomes, returns, walk-forward evidence, AI evaluation, providers/credentials/network use, Nifty 500 or other cohorts, generalized replay, and any relabelling of current-vintage values as historical point-in-time evidence. The decision layer additionally requires a same-session bound quote/circuit/book evidence class that is not retained for September; this slice reports that boundary fail-closed and never fills it.

## Evidence sources (read-only)

All sources are retained immutable stores under the storage root. Each session store exposes its namespaces either directly (`<session>/<namespace>/…`) or under its `evidence/` directory (`<session>/evidence/<namespace>/…`); both layouts are admitted.

- Capture revisions: `<session>/[evidence/]capture/bharatstock-capture-v3/revisions/<revision_identity>.json`, each a `bharatstock-capture@v3` revision with `revision_identity_sha256`, `observed_at`, `price_basis`, `volume_basis`, `provider_source`, `source_profile`, `request` (request identity, members, decision cutoff, identities), and per-member `history` (`retrieved_at`, `response_sha256s`, `rows`).
- Official schedule evidence: `<session>/[evidence/]schedule/calendar-schedules/sha256/<sha>.json` with `sessions` (trade date, kind, open/close times), `closures`, and covered range.
- Selection evidence: `<session>/[evidence/]selection/nifty100-selection-v3/requests/<request_identity>.json` → `sources/<source_identity>.json` with `members`, `selection_identity_sha256`, `retrieved_at`, `source_urls`, and the exact retained NSE source bodies (`source_bytes_b64`).

The module never writes to these stores and never reads outside the storage root.

## Window rule

For a decision session `D`, the required window is the 21 most recent official sessions `<= D` from the union of retained schedule evidence. The window is certified before use:

- every window session appears in retained schedule `sessions` and in no `closures`;
- for every consecutive window pair there exists one retained schedule record whose covered range contains both dates and which lists no session strictly between them.

An uncertified pair or a window shorter than 21 sessions blocks the whole decision session with a typed insufficiency.

## Admission rule

For each cohort member and each window session, candidate bars come from candidate revisions whose members report a bar for that session. A bar is admitted only when:

- its bar session is the revision's single reported session and lies in the window;
- the revision's `observed_at` and the member history `retrieved_at` are both `<= cutoff`;
- the revision file is a regular, single-link, owner-owned, non-symlink file within size bounds and its content identity validates internally.

When several admissible records exist for one cell, they are admitted only if their bar values and adjustment data agree exactly; the provenance then lists every agreeing source. Any disagreement produces `CONFLICTING_DUPLICATE_BARS` and the member/date is unavailable.

Revisions in the scanned scope whose session lies outside every requested decision window are recorded as `sources` with their provenance and counted in the report (`sources_outside_window`); they can never supply a window cell, because only requested window sessions are queried. No out-of-window bar is ever admitted as window evidence.

## Source safety and canonical revalidation (implemented)

Every source read fails closed: entries are refused unless they are regular files, single-link (`st_nlink == 1`), not symlinks, owned by the same owner as the storage root, size-bounded, and named as canonical lowercase SHA-256 digests (`.json`). Symlinked directories are refused; non-`session-*` directories inside a batch directory are skipped. Discovery scans `daily-capture/` to depth two and bounds visited directories, stores, revisions, schedule records, and selection bytes.

Every admitted revision is revalidated from the retained bytes alone, without trusting recorded identities and without gating on the current runtime's code identity:

- the file bytes must equal the canonical re-serialization of the parsed revision value (byte-line equality) and the recomputed revision identity (`sha256` of the canonical bytes of the revision value without `revision_identity_sha256`) must equal both the file name and the recorded field;
- the request is revalidated structurally and its identity recomputed; member binding, single-session binding, preparation basis, and coverage identity are recomputed (`selection_identity_v2`, coverage identity) rather than trusted;
- the revision's schedule evidence must be one retained canonical record whose recomputed schedule identity equals the recorded `schedule_identity_sha256`;
- the cohort selection source is revalidated by re-parsing the exact retained NSE source bodies and recomputing the source identity, the selection identity, the 50/50/100 member binding, and the N50/NN50/N100 URL lock, and the binding must name the chosen revision's request identity, with `retrieved_at <= cutoff`;
- recorded runtime/release identities are reported as provenance only; revisions whose contract version is not `@v3` are ignored, and canonically valid empty revisions (no observed rows) are ignored, both counted in the report.

## Snapshot contract

Canonical JSON (`sort_keys`, compact separators, trailing newline) with contract version, request identity inputs (ordered decision sessions, window size, cutoff, permitted use, limitation, source profile lock, price/volume basis, provider source), cohort binding (members, selection identity when retained), resolved windows with certification results, per-date per-member availability with per-bar provenance, insufficiency ledger, and availability scale in ten-thousandths. Identity is the SHA-256 of the canonical bytes. The snapshot is retained under a private namespace as `<identity>.json` with the repository's immutable publication semantics (write-once to `0o600`, committed readback to `0o400`, conflict refusal, no rewrite). An exact retry returns the identical identity and bytes; any identity collision refuses.

## Bounds

Decision sessions: 1..31, ordered, distinct, `date` values. Window size: exactly 21. Cohort size: 1..100; the declared cohort size must equal the resolved cohort member count, and a mismatch is a typed refusal with no retention. Source revisions scanned: at most 512. Schedule records: at most 64. Selection sources per store: at most 4. Snapshot bytes: at most 4 MiB. Depth: at most 64. Cutoff must be timezone-aware UTC text.

## Failure precedence (closed)

1. Invalid request (bounds, ordering, types, cutoff) → `ValueError`, no retention.
2. Storage root unavailable/unleased → unavailable error, no retention.
3. Unsafe source entry (symlink, wrong mode/owner/link count, oversize, unreadable, non-canonical) → typed refusal, no partial snapshot.
4. Schedule certification failure → date-level typed insufficiency, snapshot still retained.
5. Missing/absent/late/conflicting cells → member-level typed insufficiency, snapshot still retained.
6. Identity collision with different bytes → refusal, no rewrite.

## Adversarial matrix (frozen)

1. Bar retrieved after cutoff → excluded; if the window then has a hole, typed insufficiency; never admitted.
2. Current-vintage duplicate of an old session (later retrieval) → excluded by retrieval bound even when the session is in the window.
3. Two admissible sources disagree on one cell → `CONFLICTING_DUPLICATE_BARS`; member unavailable; snapshot retained with the conflict recorded.
4. Two admissible sources agree exactly → single cell, both provenances recorded deterministically.
5. Missing seventh session in the window → window certification or member-level insufficiency; no silent shorter window.
6. Request with unordered/duplicate decision sessions or window size ≠ 21 → `ValueError`.
7. Cohort member absent from the decision session's revision → member-level typed insufficiency.
8. Symlinked, oversized, non-regular, or foreign-owned source entry → typed refusal.
9. Exact retry → identical snapshot identity and bytes; no new file; no rewrite.
10. Same identity with different bytes (tamper) → refusal.
11. Bar session inconsistent across members of one revision, or outside the revision request's declared sessions → typed refusal, no partial snapshot; a revision whose session lies outside the requested decision windows is recorded, counted (`sources_outside_window`), and never admitted as window evidence.
12. No clock, environment, network, or provider access exists on the build path.

## Realized September run (2026-10-18)

Frozen request: decision sessions `2026-09-21`..`2026-09-25`, window 21, admission cutoff `2026-09-26T12:00:00Z`, cohort size 100, executed by `point-in-time-snapshots` against the owner's storage root with no provider or network access.

Result: snapshot identity `f4f164d22261e14e2b45291d4af7abd569ef8fd3dea17b5445934be00ef1a7bd`, 1,038,773 canonical bytes, retained under `point-in-time-evidence-snapshots-v1/<identity>.json` with mode `0o400`; all five decision sessions certified with 100/100 members available and 2500/2500 member-session cells admissible at the cutoff (10,000 bps per date); 29 revision files discovered, 27 admitted, 2 canonically valid empty revisions ignored, 0 selection mismatches; cohort bound from the last decision session's retained selection evidence (identity `7a1d…`, source identity `9443…`). The snapshot records every admitted source's revision, request, schedule, selection, configuration, and runtime identities, `observed_at`, store, and the raw response identities per bar. An immediate retry returned the identical identity and bytes, and CLI readback reproduced the retained document.

## Correction record (2026-10-18, #335 delivery)

The independent R3 functional review held matrix row 11 against the realized artifact. Row 11 now states the enforced behavior explicitly: bar sessions inconsistent across members of one revision, or outside the revision request's declared sessions, are a typed refusal with no partial snapshot, while revisions whose session lies outside the requested decision windows are recorded as sources and counted as `sources_outside_window` — they can never supply a window cell. The declared cohort size is now cross-checked against the resolved cohort member count (typed refusal on mismatch). Re-running the frozen request after these corrections returned the identical retained snapshot identity and no new file or rewrite; only the report's `revision_counts` gained the `sources_outside_window` key (`2`).

## Slice 2 — Market Structure projection (2026-10-25)

Status: implemented as a report-only projection under Future #139. No new
retained artifact and no policy/decision/return claim.

The `point-in-time-snapshots --structure <snapshot_handle>` command re-admits
one retained evidence snapshot and computes Market Structure facts for every
admitted decision date/member from exactly its 21 window bars:

- bars are matched by member symbol and official window session; a missing bar
  yields `INSUFFICIENT_WINDOW_BARS`;
- every bar's source identity is the SHA-256 of its canonical retained bar
  record;
- the existing provider-neutral
  `evaluate_market_structure_math_member_v1` calculation is reused; no second
  structure engine;
- a member unavailable in the evidence snapshot remains unavailable; its
  structured insufficiency mapping and missing sessions are preserved;
- blocked/uncertified dates retain `certified`, availability counts, coverage,
  and insufficiency counts; they are never flattened to an empty date;
- output schema is `point-in-time-research-structure@v2`, with report identity,
  bar/member/pivot/event identities, trend, structure state, pivots and events.

The September 2026 run produced 5 decision dates × 100 members with 100/100
structure results per date. Slice-2 v1 report identity was `126669cb9257…`; the
v2 boundary run identity is `c3f1ac6a47c1…` for retained snapshot
`f4f164d22261…`. No provider, clock, network, or storage mutation is used.

The v2 `policy_feasibility` block names the blocked policy
(`supported-signal-safety-policy@v1`), the missing evidence classes and rules,
why they cannot be reconstructed, the earliest valid observation point, and the
blocked scope. It is covered by `report_identity_sha256`.

Non-goals remain: policy decisions, candidate pairs, returns, walk-forward,
costs, AI evaluation, and any relabelling of later-known facts.

## Acceptance evidence

- Focused behavior and adversarial tests for every matrix row.
- One real run over the frozen September request on the owner's storage root, with the report and retained snapshot identity recorded on #335 and #332.
- Independent R3 functional/domain and security/privacy/provenance review on the exact candidate bytes, repository gates, hosted CI, and merge.

## Provenance

Slice 1 of #139 under owner authorization recorded on #332 and #139. Contract aligned with the capture-forward evidence boundary (Plan 30) and the source-bound evidence boundary (Plan 76). No market-structure or policy logic is duplicated or newly authored here.
