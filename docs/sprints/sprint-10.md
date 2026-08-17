# Sprint 10 — Current supplied-cohort market data

Status: **LOCAL IMPLEMENTATION — GitHub Issue #121; exact-revision review and publication pending**
Tracking: [GitHub Issue #121](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/121)
Milestone: **Sprint 10**
Plan: [Plan 19](../plans/19-current-supplied-cohort-market-data-contract.md)
Risk: **R3** — current market-data integrity, provider effects, and research boundary

## Goal

Make the existing `market-data` tool usable for current/live swing research over
an explicit owner-supplied cohort of 1–50 Nifty 50 equities. A canonical
manifest binds the cohort identities, selection instant,
and SHA-256 identity without asserting historical membership. Every member must
occur in the cutoff-eligible retained Nifty 50 universe snapshot and resolve
through retained instrument identity; missing, duplicate, ambiguous, stale, or
out-of-cohort identity fails closed.

One bounded request returns the latest completed daily OHLCV and, only when
explicitly requested and available, a current-session partial price/volume
snapshot with `PARTIAL_CURRENT_SESSION` state and a knowledge timestamp. A
partial current-session snapshot is never a completed daily bar or a historical
close. Complete outputs bind the cohort, invocation cutoff, source receipt/
provenance, freshness, bar state, and code/schema identity; incomplete required
evidence is one whole-cohort insufficiency.

## Provider and deterministic boundary

Provider-backed calls retain credential ownership, rate-limit, attempt,
concurrency, byte, duration, cancellation, private-storage, and sanitized-error
controls. No effect occurs before request/cohort admission. New sources require
the required evaluation and separate execution authority; this sprint does not
adopt a new source or claim provider acquisition.

Every admitted live fact is immutably archived from now with `published_at`,
`known_at`, source, revision, and affected identities. A per-feature/instrument/
interval ledger records only `AVAILABLE`, `NOT_PUBLISHED`, `NOT_RETAINED`,
`SOURCE_GAP`, `STALE`, `CONFLICTED`, or `UNLICENSED`. Predeclared coverage keeps
unavailable dates visible; later/current facts never substitute for unavailable
history.

The deterministic tool emits market facts only. It does not calculate Market
Regime, sectors, news/events, trade signals, recommendations, entries/exits,
position size, or orders. Current Market Regime, Sector Analysis, news/events,
and the integrated packet are the separately gated Sprints 11–14 sequence.
An external AI may later produce explainable research or `NO_TRADE`; it cannot
turn the tool into an autonomous recommender or execution system.

## Acceptance

Sprint 10 may proceed to an ordinary completion decision only when Issue #121's
exact contract demonstrates the canonical 1–50 cohort, retained-instrument
resolution, bounded request admission before provider effect, completed-daily
versus `PARTIAL_CURRENT_SESSION` separation, no partial-as-close conversion,
whole-cohort insufficiency, full provenance/freshness/bar-state/schema identity
binding, and immutable archive/availability-ledger behavior. Focused local
checks are recorded below. Full repository/hosted gates, independent
exact-revision review, merge, and publication evidence remain pending and are
not claimed here.

## Operational current-data usage

Prepare one canonical UTF-8 JSON manifest with sorted keys, compact separators,
and one trailing newline:

```json
{"contract_version":"current-supplied-cohort-market-data@v1","members":[{"isin":"INE002A01018","symbol":"RELIANCE"}],"selected_at":"2026-08-17T03:00:00.000000Z"}
```

Run the retained-data path with absolute owner-private paths and an explicit UTC
knowledge cutoff:

```text
market-data cohort-current \
  --cohort-file /absolute/private/cohort.json \
  --storage-root /absolute/private/market-data \
  --cutoff 2026-08-17T10:00:00.000000Z \
  --output json
```

The command reads retained evidence only. Exit `0` emits one canonical
`COMPLETE` report; exit `1` emits one canonical whole-cohort
`INSUFFICIENT_EVIDENCE` report with `members: null`; exit `2` rejects malformed
CLI or cohort input before retained-root access. A complete result also publishes
one content-addressed immutable fact/availability-ledger object below the
protected retained root. This command does not authorize provider access.

Local behavioral evidence:

```text
uv run pytest -q -o addopts='' tests/market_data/test_current_cohort.py
# 22 passed

# Empty retained root smoke: canonical INSUFFICIENT_EVIDENCE,
# reason PROVIDER_UNAVAILABLE, process exit 1; no provider call.
```

Final local repository gate: Ruff format/check and Vulture passed; Pyright
reported 0 errors and 0 warnings; 2,554 tests passed at 91.61% coverage; source
and wheel distributions built successfully; `git diff --check` passed.
Exact revision review, hosted checks, merge, and publication remain pending.

## Deferred historical lane and preserved records

Fixed-cohort historical OHLCV storage is deferred to Sprint 15 / Issue #120;
historical validation and the pre-structure gate are deferred to Sprint 16 /
Issue #122. Historical news, events, and sector inputs are deferred/not-yet-
evaluated, not permanently removed or silently neutral. Deferred Plan 18 is not
this sprint's plan.

Issues #111 and #115 are **closed / not planned** with no published
implementation. Plans 12 and 17 and their exact evidence remain historical
records; this does not claim their decisions were wrong when made. The former
blocked baseline remains historical evidence only: `origin/main`
`2d5cb3734a35a77d107c21147a50c120555cdfab`, incomplete manifest
`53717e75d9e93344d7df55ea2a5e94e48e133ff0ad673f27e38ba040cc91bb2f`, and
blocked report `dbbc0bdf32cf081d491a119c05571bebf4dbd274bae858dd0e3d418b96bd1408`.

The contemplated official-inquiry content SHA-256
`a2d762cd93dfca56d5623e260816c1aee0a6ae2a9a400097cc6f2d51c77f6412` and
authorization-payload SHA-256
`84797b9c424aa6da36d46b1b516f3cbe08d8205801d296953a5edf474d2ffe85` were
revoked before send. No inquiry email, provider contact, provider call,
credential use, or acquisition occurred. They are distinct from Plan 11's
historical public-page research receipt hashes.

## Non-goals

Sprint 10 does not implement historical/backtest storage or validation,
historical membership reconstruction, historical corporate-action/dividend/news/
event/sector backfill, Market Structure, Price Action, Liquidity/SMC, autonomous
signal/recommendation, financial advice, broker order, or a claim of completed
review, hosted validation, merge, or publication.

## Preserved original Sprint 10 readiness plan

The current/live-first priority reset did not delete the former Sprint 10 plan.
The complete original readiness record follows as historical evidence. It is no
longer the active dependency, but every outcome, blocker, identity, gate, and
conditional next step remains preserved.

# Sprint 10 — Market Regime Layer B evidence acquisition readiness

Status: **BLOCKED / CAPABILITY_EVIDENCE_MISSING**
Tracking: [parent acquisition goal — GitHub Issue #111](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/111), [planning/publication task — GitHub Issue #112](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/112)
Milestone: **2 (Sprint 10)**
Plan: [Plan 17](../plans/17-market-regime-layer-b-evidence-acquisition.md)
Risk: **R3** — point-in-time data integrity and release trust

## Goal and lifecycle state

Sprint 10 records the readiness contract for a future, separately authorized
acquisition of the complete predeclared point-in-time evidence range required by
frozen `nifty50-market-regime@v1`. Planning has started. Acquisition has not
started, and no provider access, runtime implementation, acquisition test,
persistence, label, validation, evidence publication, or execution authorization
has occurred.

This record is R3 planning evidence, not acquisition authority. It does not
select a provider, source endpoint, licence, date range, budget, credential, or
approval identity. Frozen Plans 05, 09, 11, 12, 13, and 16 remain unchanged.

## Observed blocked baseline

The canonical observed baseline is `origin/main`
`2d5cb3734a35a77d107c21147a50c120555cdfab`. The installed offline
`market-regime-acquisition-decision decide` command was given a structurally
valid caller payload and returned exit `1`: one canonical `BLOCKED` report on
stdout and empty stderr. The result is exactly `BLOCKED /
CAPABILITY_EVIDENCE_MISSING`.

| Evidence | Exact identity or result |
| --- | --- |
| Sealed incomplete manifest | `53717e75d9e93344d7df55ea2a5e94e48e133ff0ad673f27e38ba040cc91bb2f` |
| Canonical blocked report | `dbbc0bdf32cf081d491a119c05571bebf4dbd274bae858dd0e3d418b96bd1408` |
| Command result | exit `1`; canonical `BLOCKED` report on stdout; empty stderr |

The sealed manifest has no admissible capability projection. No source/PIT
evidence bundle, terms/use approval, operational-scope approval, owner
full-acquisition authorization, or trusted authorization-validation receipt
exists. The manifest and report identities identify this blocked evidence; they
do not grant provider access, acquisition, readiness, admission, label,
verification, publication, or later execution authority.

## Readiness disposition

Plan 16's current canonical decision remains authoritative: a later phase may
be considered only if an exact reviewed and published manifest build returns
`APPROVED_TO_ACQUIRE`. That planning state still would not authorize a future
executor; it must independently validate its own bounded execution-start
authorization before any side effect. Until then, Sprint 10 remains blocked and
must not substitute a source, current constituent list, inferred schedule,
49-name denominator, imputed fact, adjusted price, caller assertion, or
credential for missing evidence.

The unresolved blocker is **capability evidence missing**. The owner decision
and independently reviewable evidence required to resume are defined by Plan 17:
an exact reviewed manifest decision and the separate source/PIT, terms/use,
operational-scope, authorization, trusted-clock, bounded-scope, expiry, and
revocation evidence it requires. No authority identity is assumed or invented
in this record.

## Conditional next work

If—and only if—the Plan 17 entry gate is met, the next work begins with
discriminating RED contracts, then a private bounded adapter, independent
retained-byte/range verification, and authorized publication. Each phase fails
closed on missing, expired, revoked, out-of-scope, incomplete, substituted,
ambiguous, corrupt, late, or unsealed evidence. Sprint 11 remains blocked unless
the complete range is independently verified and every ordered Plan 13
region—development, embargo 1, validation, embargo 2, and untouched test—remains
sealed against labels and downstream outcomes. Any premature exposure invokes
the governing Plan 17/Plan 13 quarantine rule and requires a versioned manifest
with genuinely new unexposed dates and holdout.
