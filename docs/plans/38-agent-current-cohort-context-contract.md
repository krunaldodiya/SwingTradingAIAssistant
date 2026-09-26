# Agent current cohort context V4

Status: frozen implementation contract for accepted Sprint 25 [#222](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/222).
Owner: Krunal Dodiya. Risk: R3. Direction accepted in the project chat on
2026-09-26, including explicit persistent goal execution. Implementation,
independent reviews and release are pending. Plans 24/27/34/37 and the current
source-preserving V4 successors govern the reused producers.

## Goal and five-line evaluation

1. Value: expose already-delivered cohort Market Regime and Industry facts beside current stock research.
2. Fit: one owner-private opt-in CLI workflow, explicit stock and context lists, completed daily evidence.
3. Risk: false cohort breadth, source/time splicing, private evidence disclosure and optional failures masking corruption.
4. Smallest alternative: wrap existing producers and retainers; do not rewrite reducers or construct another integrated packet.
5. Disposition: accepted, limited to the first working slice below; Relative Strength remains separately deferred.

## First working slice

`research-run-current --contract-version v4` preserves the full V3 price/event
workflow and adds `--context-symbol` (repeatable, 2–50 unique explicit symbols)
and `--context-purpose` (nonempty printable text, at most 160 characters).
Both are required for V4 and rejected for older versions. The normal requested
stock list remains 1–10 unique symbols. Validate both complete lists and purpose
before effects. No implicit union, index selector, stock replacement, membership
inference or shrinking of a missing cohort member is allowed. The two lists may
overlap or differ. Their independent order, identity and count remain explicit.
Purpose is a caller description, never official classification or proof of
representativeness. Two members are a processing minimum, not market breadth.

The first end-to-end path is one research stock plus a two-member cohort with
observed retained Market Regime and Industry context. Complete the accepted
2–50 cohort bounds and failure matrix after that path; neither a stub returning
unavailable nor a retained-only API replaces the complete opt-in workflow.

## Existing producers, source and temporal boundary

Reuse Market Regime V4 acquire/build/retain and Industry Participation V4, the
existing official calendar and instrument mapping acquisition/retention,
Upstox same-pass raw adapter, Plan21 corporate-action screen, BharatStock
comparison producer, fixed NSE Indices Industry source/parser/archive, and
immutable same-pass context archive. Underlying formulas, source admission,
identity equations, archive recovery and historical readers remain unchanged.
Do not use Plan35 raw-only breadth as if it were V4 comparable Market Regime.
Do not stitch the independently acquired singleton dossier bars into a cohort.
Do not use the V5 integrated packet where its exact equal-cohort assumptions
would require relabeling the separate dossier and context lists.

The context has one fresh selection time and one deadline at most 30 minutes
later, before IST rollover. All mapping, calendar, raw, action, comparison,
Industry and retention effects obey that deadline and existing stricter bounds.
The V4 builder preserves its minimum invocation lead and reserved archive time.
Reuse existing bounded calendar windows and physical-month coverage rules;
missing required calendar evidence is explicit insufficiency, not permission
to infer sessions or widen the existing acquisition contract. Resolve all exact
canonical mappings before aggregate production. Preserve each original mapping
validity and provider revision; never invent historical validity from a current
symbol lookup. No partial-current-session data or older-session search enters
the context. One Industry source fetch per context pass, zero retries/fallback,
no new provider or unrelated event fetch on the Industry edge. Reusing fixed
transport/parser helpers for a narrow Industry acquisition is in scope.

The context source profile explicitly describes Upstox raw completed daily
bars and the existing BharatStock direction-comparability evidence. This is
not the source-reported BharatStock-only stock dossier profile. Retain the
complete producer-admitted context and classification before projection.
Source observation precedes archive knowledge time; no clock clamping,
backdating, fabricated seals or provenance reconstructed from public JSON.

## Output, compatibility and failure precedence

V4 is an additive successor with one batch `cohort_context` object: caller
purpose, requested ordered symbols and canonical members when admitted,
ordered-list identity, original cohort denominator, selection/cutoff/knowledge
times, schedule and evidence identities, source/basis description, Market Regime
availability/reasons and admitted label/counts, and literal Industry
availability/reasons and admitted aggregate rows. Project only the existing
validated producer results; the agent wrapper does not recompute market facts.
A missing member suppresses the whole-cohort aggregate as required by V4.
Missing classification withholds Industry without erasing valid Market Regime.

Keep the V3 stock price/event fields and price-based exit behavior unchanged.
Each stock may refer to the batch context and state canonical membership and
whether its selected end session matches; date equality alone never establishes
joint comparability. State that context and dossier are separate observations
and are not a single same-pass price comparison. Existing price-only
`jointly_comparable` keeps its meaning. Do not backdate context into stock price
knowledge, including the one-session-lag fallback. Do not claim a member's
Industry unless exact retained classification supports that projection.

Closed source unavailability, malformed optional source, deadline and unsupported
prerequisites produce typed unavailable/unsupported/insufficient context with
null facts and closed reasons. Reuse existing producer reason sets where
possible and freeze any small new wrapper reason set with its tests. Never
classify arbitrary ValueError, unexpected faults or exception text as optional
source failures. Input rejection precedes effects; storage authority, retention
integrity and exact binding checks precede optional-failure publication.
Unsafe/held/replaced roots, corrupted retained evidence, unexpected internal
errors and interruption remain fatal, with no partial CLI JSON. Recheck storage
authority on optional failure paths. Retries are new explicit commands; preserve
existing immutable archive recovery without new polling, replay or stores.

All NSE-derived output remains owner-private, including counts, Industry names,
status and provenance. Exclude raw bars, member direction tables, classification
source rows, notice bodies, receipts, cookies, credentials and host paths.
No hosted AI disclosure or redistribution is authorized by this workflow.

## Frozen adversarial matrix and acceptance evidence

- Positive real-producer/retention synthetic end-to-end path; independently derived literal counts/labels and Industry sum reconciliation.
- 1/10 research stocks and 2/50 context stocks; 0/1/51 context rejection, duplicate and canonical-alias rejection before aggregate effects, invalid purpose and old-version option rejection.
- Complete, absent, partial, stale, unsupported and conflicting context; no denominator shrinkage; Industry-only failure preserves Market Regime and price facts.
- Wrong cohort/order/member, mapping expiry, source/basis mismatch, forged projection/seal, corrupted or substituted archive, missing calendar/physical-month coverage and malformed Industry artifact.
- Same/different price end session, lagged stock price, independent selection times, unknown publisher time, observation/retention reversal, deadline boundary/overrun, IST rollover and no older context fallback.
- Combined optional source failure plus unsafe storage/integrity error: integrity wins. Interruption before/after archive publication, retry with exact existing evidence, root lease contention and replaced root.
- One bounded Industry fetch, no provider fallback/retry, existing request/byte/time bounds, no source bodies/receipts/secrets/paths in output or sanitized errors.
- Actual CLI positive and negative synthetic invocations; preserved V1/V2/V3 outputs, price comparability and exits. Synthetic provider evidence never counts as live qualification.

Tests first for changed observable behavior. Inexpensive static/affected checks
precede full gates; stabilize exact committed bytes and resolve independent
functional/domain and security/privacy/provenance reviews before expensive final
acceptance. Format first; audit every directly/transitively bound runtime
manifest, including directory-relative manifests, and independent literal
identity examples. Run applicable full suite/coverage, static, sdist/wheel,
clean installed-wheel smoke and hosted gates on final candidates. Do not replace
or weaken required gates. Use the prepared Python3.11 environment and disk TMPDIR;
the owner's Python3.14 environment is preserved.

## Ownership, deferred work and goal boundaries

Coordinator owns this contract, shared integration files, tracking, final gates,
manifest integration, reviews and truthful closeout. A bounded implementation
agent may own the additive agent cohort module, acquisition wrapper, CLI wiring,
focused tests and workflow guide after assignment; no nested delegation. Separate
functional and security reviewers inspect clean committed exact bytes read-only
and cannot approve their own code. Use inherited model/effort unless a supported
explicit routing choice is recorded; observed telemetry is recorded separately.

Goal: implement and verify issue222 through an independently reviewed passing
candidate and PR, then complete release only with applicable authority. Stop
dependent effects at new scope/provider/architecture, credentials, protected or
destructive effects, conflicting work, unavailable external evidence, unresolved
product ambiguity or release/risk authority; continue independent authorized
work. No recurring automation or scheduled sprint execution.

Excluded: Relative Strength/Volume, new mathematical factors, discovery or
100-stock scale, index membership claims, fundamentals, backfill, rankings,
stock picking, signals, orders, generalized persistence/replay/attestation,
monitoring and source redistribution. Rollback uses unchanged V1–V3 and leaves
retained evidence and predecessor readers intact. The prior release exception
has expired; it supplies no Sprint25 authority.

## Pre-implementation seam audit

Read-only agent `context_seam_audit` confirmed the reused producer sequence and
separate-cohort wrapper are feasible. Its review is design evidence, not final
independent approval. Two required corrections at the new orchestration boundary:
prepare retained same-date Upstox mappings before the raw adapter, and never
reinterpret generic raw acquisition or archive failures as harmless source
absence. The legacy default raw downloader catches broad Exception; the new
path must use a narrow classified adapter or fail that ambiguous outcome fatally,
with discriminating storage/integrity tests. No existing reducer rewrite is
required or authorized by this correction.
