# Plan 48: bounded candidate observation comparison

Status: accepted under the owner's October 3, 2026 selection of the bounded
candidate comparison slice. Owner and risk owner: Krunal Dodiya. Risk R3:
public financial-research contract, causal knowledge and provenance. Sprint 34.
Base: 9d30fa6083cbed95c1bd96866237dd01ee8c78dc.

## Need and finite phase baseline

Answer whether two admitted observations of one stock describe the same latest
upward BOS event, changed event evidence, a distinct event, absence or unknown.
Plan 47 candidate hashes bind capture revisions, so hash inequality cannot
establish a new opportunity. Existing observation comparison requires advancing
sessions and does not answer same-session retry/correction questions.

Value: distinguish repeated detection from changed evidence for research users.
Fit: deterministic factual comparison, with AI interpretation outside the tool.
Risk: revision mistaken for new opportunity; absence mistaken for invalidation.
Alternative: manual comparison of already admitted event and provenance fields.
Accepted: one-stock, two-observation comparison; no new trading calculation.

[Plan 47's complete eight-row baseline](47-causal-setup-detection.md#signal-phase-completion-baseline-and-ordered-gaps)
remains visible and authoritative: detection; necessary analytical coverage;
generation responsibility/identity; confirmation/invalidation/expiry/duplicates;
observable lifecycle; coherent context/safety; correctness/interpretation/effectiveness;
verified phase closeout. This slice advances duplicate/revision explanation only.
Liquidity adequacy, source-backed fundamentals, generation policy, validity,
invalidation, expiry, monitoring/persistence, eligibility and effectiveness remain
open; no family is removed or declared complete. Current owner ordering is signal
and research first, risk/capital/money management/position sizing later. Preserve
delivered risk capabilities and all integrity guards. No Future issue is selected
or borrowed, directly or indirectly.

## Frozen input, admission and output

SDK `compare_setup_observations_v1(previous, current)` accepts exactly two
`CurrentStockResearchResultV2` objects for CURRENT_STRUCTURE. Reuse Plan 47's
typed result/packet/runtime/diagnostic/knowledge/source/anchor validation, before
comparison. Do not accept caller-authored setup JSON as admitted evidence.
Pure SDK: no network, acquisition, persistence, clock, or storage writes.
Before serialization bound envelope metadata: 1–32 limitation strings of
1–1024 characters, stage <=64 and code <=128 characters; symbol uses existing
1–32 uppercase public grammar. Each packet retains its existing producer bounds.
These bounds reject oversized caller metadata rather than allocating it merely
for an identity; no limitation text is exported.

Public CLI adapter `setup-compare --symbol SYMBOL --storage-root ABSOLUTE_ROOT
--previous-selection-time UTC --current-selection-time UTC --output json`
accepts an explicitly supplied observation service, like the existing research
comparison adapter. Exactly two calls with CURRENT_STRUCTURE and explicit
selection times; validate the request before calls, validate selector/result
binding before comparison. Equal selection times allow exact replay only.
This is an SDK/CLI integration boundary, not a new automatic historical reader.
Guarded runnable example demonstrates real synthetic producer admission and
states that its fixed observations are not current market data. No provider
effects are authorized. No arbitrary historical-time acquisition or backdating.

Output version `causal-setup-comparison@v1`, criterion, runtime identity,
previous/current full observation SHA256, both Plan 47 projected rows and status,
reason and canonical result SHA256. Sorted compact canonical JSON plus LF;
maximum 1 MiB. Closed statuses:

1. REPLAY: exactly equal canonical full observation bytes after both admissions.
2. NON_COMPARABLE: missing/different canonical stock or incompatible source profile,
   price basis, semantic mapping, symbol or temporal order. Fixed reason only.
   Semantic mapping compares ISIN/exchange/effective symbol/provider symbol,
   mapping version. Each observation independently admits its own mapping validity;
   differing observation-scoped validity windows do not alone imply remapping. Discovery observations/retrieval
   times and their revision-bound digests may differ; retain both row identities.
   This clarification follows the first real-producer matrix failure: fresh
   discovery alone changes mapping digest without changing mapping meaning.
3. UNKNOWN: either independently admitted row is UNKNOWN, after compatibility checks
   that can be established. Missing canonical/source evidence never becomes absence.
4. NO_MATCH: both rows have supported NO_MATCH.
5. APPEARED: previous NO_MATCH, current MATCH. This is observation appearance only.
6. ABSENT: previous MATCH, current NO_MATCH; not invalidation or expiry.
7. DIFFERENT_EVENT: both MATCH with different event locus.
8. REVISED_EVENT: both MATCH, same locus but different admitted event/anchor factual values.
9. SAME_EVENT: both MATCH, same locus and equal admitted event/anchor factual values; capture/research
   revision may differ and remains independently bound and visible.

Event locus is the tuple of event type/direction, event session, pivot session
and pivot confirmation session, within the admitted same canonical stock and
criterion. Event equality reads existing event type/direction/session/close/broken level/prior
trend and anchor kind/session/confirmation session/price/relation/unclassified
reason. No mathematics is recomputed and numerical values stay private. Source-bar,
event and pivot digests also bind history retrieval time, so their inequality alone
cannot establish revised factual values. Both original digests remain visible.
This clarification follows the real source-refresh red discriminator. Equality is
not exchange correction lineage. Window positions are not compared.
Every changed-event status is descriptive, never a new trading opportunity claim.

For non-replay require strictly increasing selection times, nondecreasing
completed sessions when both known, and nondecreasing evidence/feature knowledge
times when both known. Enforce known time within each acquisition deadline.
Same-session refreshed observations are permitted; later-acquired old evidence
retains its current knowledge time. Reversed time returns NON_COMPARABLE.
Source profile/basis/mapping mismatches return NON_COMPARABLE, not UNKNOWN.
Integrity failure is terminal even combined with unknown or incompatible data.
Validate both inputs before any semantic verdict. No prices, bars, source bodies,
private paths or arbitrary diagnostics leave the projection.

CLI exit 0 for factual statuses including REPLAY, 1 UNKNOWN/NON_COMPARABLE,
2 malformed input, integrity or interruption; exit 2 has fixed diagnostic and
no partial stdout. No retry effects within the SDK; identical inputs stable.

## First working path, later scope and ownership

First: real admitted MATCH replay through SDK and actual CLI; then all closed
statuses/adversaries, compatibility, manifest integrity and independent reviews.
Coordinator sole writer of new `research_comparison/setup_observation_comparison.py`,
manifest and CLI, tests, example, this Plan/sprint documentation and mechanically
affected source manifests. Existing setup V1/comparison V1/math retain behavior.
No new dependency/store. Approved environment remains outside worktree; use
official uv CLI only. Format source before refreshing all bound manifests.

Later non-goals: new signal formula, liquidity or fundamental source adoption,
validity/expiry/invalidation, entry confirmation, ranking, persistent lifecycle,
scheduler, effectiveness, eligibility, risk/position scope and broker actions.
Merge/release/provider/destructive/protected verification authority stays separate.

## Frozen matrix and acceptance

| Matrix | Required observable evidence |
| --- | --- |
| Positive and retry | Real synthetic producer SDK/CLI replay, same-event revision and distinct-event cases; repeat bytes stable |
| Negative/unknown | NO_MATCH/APPEARED/ABSENT/UNKNOWN remain distinct; absence never invalidation |
| Revision | Same locus changed event/anchor gives REVISED_EVENT; source-only change SAME_EVENT |
| Causal timing | Equal selector non-replay, reversed selection/session/knowledge, deadline violation; present knowledge never historical |
| Compatibility | Wrong stock/mapping/basis/profile distinct NON_COMPARABLE; old APIs unchanged |
| Integrity/precedence | Forged type/runtime/packet/anchor/known-time/diagnostic terminal even with missing fact or mismatch |
| Bounds | Two observations/one stock; malformed times/symbol/root rejected before service; 1 MiB and plus-one failure |
| Interruption | Second call interrupted yields no partial stdout; fixed private-safe diagnostic |
| Concurrency | Concurrent pure SDK stable/no mutation; acquisition lease remains producer-owned |
| Privacy | No raw bars/prices/paths/errors; both provenance revisions visible |
| Final | Two independent exact-current whole-slice PASS verdicts; applicable full/static/package/installed/hosted evidence |

Tests-first permanent contracts, focused checks `pytest -o addopts='' --no-cov`
with explicit file selection through approved environment, Ruff check/format,
Pyright and Vulture before final full suite (configured 87% branch coverage).
Full gates include sdist/wheel, installed-wheel actual public behavior outside
checkout, configured self-hosted CI/security and rollback within separate
protected-effect authority. No interim hosted pushes before stable reviews.
Pure Markdown changes use exactly git diff --check; executable work justifies
the later executable gates.

Independent domain and security/privacy/provenance reviewers inspect clean
committed exact base-to-candidate bytes read-only, with fresh assignment identities,
full results and pre/post SHA/tree/clean checks retained. No nested delegation.
Coordinator retains failures and finding dispositions; no prior verdict transfers.
Goal starts after governing tracker/readback freeze. Stop only dependent work at
consequential ambiguity, source/credential/protected/destructive effects, shared
mutation, scope expansion, exact-byte review/merge/release or residual-risk gates.
Completion means accepted evidence, not merely implementation or a green focused run.
