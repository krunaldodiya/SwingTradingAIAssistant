# Capability-aware historical validation contract

Status: **DELIVERED HISTORICAL CONTRACT — Sprint 16 / Issue #122 closed**
Contract revision: `capability-aware-historical-validation-gate@v1`
Risk: **R3** — financial-research integrity, point-in-time evidence admission,
holdout protection, reproducibility, and historical profile qualification.

## Decision and authority

1. **Expected value:** determine exactly which historical study claims the retained
evidence supports.
2. **Scope fit:** one explicit supplied cohort, immutable evidence revisions, a
closed availability ledger, versioned study profiles, and one fail-closed
historical qualification result.
3. **Material risk:** look-ahead, survivorship, available-only selection, raw-price
comparability, late context, or exposed holdouts could create false research claims.
4. **Smallest alternative:** reduce already-supplied immutable evidence without
provider, acquisition, market-calculation, recommendation, or execution authority.
5. **Decision:** **accepted and delivered** — the closed reducer and one operator
CLI preserve missing evidence explicitly and return a blocked historical result
when qualification evidence is absent.

GitHub Issue #122 in the Sprint 16 milestone governed the delivered work. Sprint
15 / Issue #120 supplied the first exact-read adapter. The result qualifies only
the historical profile represented by its supplied evidence; its legacy outcome
name does not authorize or gate current/live Market Structure work, a trading
strategy, recommendation, execution, or financial outcome.

## Current source decision

No new provider, source, download, credential, HTTP, or acquisition path is
adopted. The first adapter consumes only an exact successful read from
`HistoricalOhlcvRevisionStoreV1`. Sprint 15's delivered `UPSTOX_RAW` evidence is
`REVISED_NON_PIT`, with corporate actions `NOT_EVALUATED` and comparability
`NOT_ESTABLISHED`; Sprint 16 must preserve those facts and must not inherit the
older Plan-18 adjusted-price assumption.

## Working-feature-first boundary

### First working slice

- one pure bounded reducer under `historical_evaluation`;
- one exact adapter from a named Sprint-15 revision;
- one canonical request containing the declared decision grid, four protected
  research regions, three required study profiles, and the complete availability
  ledger;
- complete profile reports and the exact historical qualification result;
- one sanitized zero-provider operator CLI;
- a real Sprint-15 `UPSTOX_RAW` path that truthfully returns `BLOCKED` when its
  point-in-time or comparability evidence is not proven.

### Remaining required Sprint-16 completion

- all eight availability states and all three profiles;
- cutoff, coverage, region, cohort, revision, identity, and no-dropped-date rules;
- positive generic point-in-time behavior plus malformed, unsupported,
  insufficient, conflicting, limit-plus-one, combined-failure, replay, and
  substitution behavior;
- exact runtime/configuration/report identities, independent R3 review, repository
  and hosted gates, installed-artifact smoke, merge, and Issue #122 closure.

### Later improvements outside Sprint 16

Historical membership, sector, news, event, or corporate-action acquisition;
adjusted-price providers; yfinance composition; provider routing; generalized
replay; persistence or discovery of validation reports; dashboards; automated
paper-validation operations; Market Structure; recommendations; and orders.
Issue #145 remains separate cross-module internal-error work unless a concrete
Sprint-16 acceptance blocker requires an explicitly approved dependency change.

## Closed execution boundary

The reusable core is:

```text
evaluate_capability_aware_historical_validation_v1(
    request: HistoricalValidationRequestV1,
    evidence: HistoricalEvidenceRevisionV1,
) -> HistoricalValidationReportV1
```

It is pure and zero-I/O. It does not read a clock, filesystem, environment,
provider, network, database, market feed, or model. It does not calculate Market
Structure, indicators, returns, fills, costs, labels, recommendations, or scores.

`HistoricalValidationServiceV1` is the only Sprint-15 adapter. It performs one
exact named read through `HistoricalOhlcvRevisionStoreV1`, converts a successful
revision into the generic immutable evidence contract, and invokes the reducer.
It never discovers a latest revision, retries a different revision, changes the
request, reads source partitions directly, or mutates either store.

The CLI is exactly:

```text
historical-validation-gate --request-file ABSOLUTE_PATH \
  --storage-root ABSOLUTE_PATH --output json
```

The canonical request names its exact `evidence_revision_sha256`. The CLI performs
no provider action. Exit `0` means an `APPROVED_TO_START_MARKET_STRUCTURE` report,
exit `1` means a valid `BLOCKED` report, and exit `2` emits exactly
`request_invalid` or `internal_error` plus LF on stderr with no stdout. This is a
local Sprint-16 boundary, not the cross-module migration deferred to Issue #145.

## Closed vocabulary

```text
AvailabilityStateV1 =
  AVAILABLE | NOT_PUBLISHED | NOT_RETAINED | SOURCE_GAP |
  STALE | CONFLICTED | UNSUPPORTED | UNLICENSED

HistoricalStudyProfileV1 =
  OHLCV_ONLY | OHLCV_PLUS_SECTOR | OHLCV_PLUS_NEWS_EVENTS

HistoricalEvidenceFeatureV1 =
  DAILY_OHLCV | CORPORATE_ACTION_COMPARABILITY |
  SECTOR_CLASSIFICATION | NEWS_EVENTS

HistoricalStudyRegionV1 =
  DEVELOPMENT | OUT_OF_SAMPLE | UNTOUCHED_TEST | WALK_FORWARD

ProfileQualificationOutcomeV1 =
  QUALIFIED | INSUFFICIENT_EVIDENCE | UNSUPPORTED_CAPABILITY

MarketStructureReadinessGateV1 =
  APPROVED_TO_START_MARKET_STRUCTURE | BLOCKED
```

The profile requirements are immutable:

| Profile | Required features for every member and decision session |
|---|---|
| `OHLCV_ONLY` | `DAILY_OHLCV`, `CORPORATE_ACTION_COMPARABILITY` |
| `OHLCV_PLUS_SECTOR` | OHLCV-only features plus `SECTOR_CLASSIFICATION` |
| `OHLCV_PLUS_NEWS_EVENTS` | OHLCV-only features plus `NEWS_EVENTS` |

Corporate-action comparability is OHLCV integrity metadata, not contextual alpha.
Missing sector or news/events evidence therefore does not block the OHLCV-only
profile. It blocks only the profile that requires it.

## Bounds and canonical types

- cohort: `1..50` unique canonical `(ISIN, exchange, effective_symbol,
  symbol_history_identity_sha256, provider_mapping_identity_sha256)` members,
  strictly sorted;
- decision sessions: `4..366`, unique and strictly increasing;
- study profiles: exactly the three closed profiles, sorted in enum order;
- regions: each of the four closed regions appears in one nonempty contiguous
  block, ordered `DEVELOPMENT`, `OUT_OF_SAMPLE`, `UNTOUCHED_TEST`, `WALK_FORWARD`;
- availability cells: at most `50 * 366 * 4 = 73,200`;
- request bytes: at most 64 MiB; report bytes: at most 4 MiB;
- identifiers: printable bounded tokens or lowercase 64-character SHA-256;
- dates: canonical `YYYY-MM-DD`; instants: aware UTC rendered with `Z`;
- coverage: integer basis points in `1..10,000`, never float or rounded tolerance;
- symbol-history identity: SHA-256 of the canonical complete effective-symbol
  descriptor, including its effective range;
- provider-mapping identity: SHA-256 of the canonical versioned provider-mapping
  descriptor, including its provider instrument, effective range, evidence time,
  and evidence identity;
- input JSON: canonical UTF-8, sorted keys, compact separators, no duplicate or
  unknown fields, floats, NaN/infinity, or nesting beyond the closed limit.

The request's canonical bytes exclude only its own `request_identity_sha256` when
that identity is computed. The report's canonical bytes exclude only its own
`report_identity_sha256`. Every tuple order is semantic and validated.

## Evidence revision

`HistoricalEvidenceRevisionV1` binds:

- revision contract and revision SHA-256;
- explicit supplied cohort and its independently computed cohort SHA-256, binding
  ISIN, exchange, effective symbol, symbol-history identity, and versioned
  provider-mapping identity;
- exact ordered decision-session-capable grid and daily-bar knowledge time for
  each `(canonical member, session)`;
- interval, source profile, price basis, temporal status, corporate-action status,
  comparability status, permitted use, source/schema/runtime/config identities,
  and fixed-cohort retrospective limitation;
- an exact content identity over the complete generic projection.

The Sprint-15 adapter accepts only an exact successful store read whose embedded
`revision_sha256` equals the requested name and whose request/cohort/grid/bar
projection remains internally valid. It derives the symbol-history and
provider-mapping identities from the exact complete Sprint-15 cohort descriptors.
It never projects only ISIN and exchange or accepts a symbol/mapping substitution
under an unchanged cohort identity. It preserves:

```text
research_scope = FIXED_COHORT_RETROSPECTIVE
source_profile = UPSTOX_RAW
price_basis = RAW
temporal_status = REVISED_NON_PIT
corporate_action_status = NOT_EVALUATED
comparability_status = NOT_ESTABLISHED
limitation = FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION
```

It does not relabel those values. A future evidence profile requires a separate
source decision and adapter; the generic core does not grant that authority.

## Decision grid and protected regions

Each `HistoricalDecisionPointV1` contains one exact revision session, its trusted
`decision_cutoff`, and one region. The grid is strictly increasing and is fixed
before availability reduction. It may not contain a date outside the evidence
revision or omit a date because of its availability state.

All four regions are predeclared as nonempty contiguous blocks. The reducer
accepts no label, future return, strategy result, score, outcome, or region-change
instruction. Unknown fields are invalid. An unavailable decision point stays in
its original region and denominator.

Opening, sealing, or operationally enforcing one-time holdout access belongs to a
future execution workflow. This contract proves only that the region allocation
was supplied, canonical, identity-bound, and not changed during reduction. It
must not claim that an already exposed historical period is untouched.

## Availability ledger

`HistoricalAvailabilityEntryV1` is one exact cell keyed by:

```text
(feature, canonical member, session, interval)
```

It binds the matching decision cutoff, availability state, affected-cell identity,
classification receipt identity, source identity, optional immutable evidence
revision identity, optional publication and known times, and a canonical entry
identity. The interval is `1d` for OHLCV/comparability and `as_of` for sector or
news/events.

State invariants:

- `AVAILABLE`: source, evidence revision, publication, and known time are present;
  publication is no later than known time and known time is no later than the
  cell's decision cutoff.
- `STALE`: the same identities and times are present, but the evidence fails its
  predeclared freshness requirement.
- `CONFLICTED`: source and a digest of the exact conflicting revision set are
  present; no candidate is selected.
- `UNSUPPORTED`: the canonical member or source cannot supply the required
  feature; it never carries a selected usable revision and yields the distinct
  `UNSUPPORTED_CAPABILITY` profile outcome.
- `NOT_PUBLISHED`, `NOT_RETAINED`, `SOURCE_GAP`, and `UNLICENSED`: remain explicit
  limitations and never carry a selected usable revision.

For `DAILY_OHLCV/AVAILABLE`, both the ledger evidence-revision and source
identities must equal the supplied historical revision, the cell must exist in
that exact revision, and its ledger known time must equal the stored bar's
knowledge time. A later-known bar cannot be made available by changing only the
ledger state. For raw OHLCV, `CORPORATE_ACTION_COMPARABILITY` requires separate
point-in-time evidence admitted through an authorized adapter and bound into the
evidence revision; request-authored source, receipt, or revision digests are not
proof. V1 therefore fails closed whenever the supplied revision declares Sprint
15's `NOT_EVALUATED`/`NOT_ESTABLISHED` states.

The ledger contains exactly one cell for every member, decision session, and
feature required by at least one declared profile. Missing, duplicate, conflicting,
or extra cells are invalid or insufficient according to the frozen precedence;
they are never dropped. The ledger identity binds the complete ordered set.

## Profile qualification

Every profile is reduced independently over its exact required cell set.
`ProfileValidationResultV1` contains:

- profile and declaration identity;
- total required cells;
- available cells;
- exact coverage basis points using integer floor division;
- counts for all eight availability states, including zeroes;
- `QUALIFIED`, `INSUFFICIENT_EVIDENCE`, or `UNSUPPORTED_CAPABILITY`;
- a closed ordered reason tuple;
- result identity.

A profile is `QUALIFIED` only when available coverage meets its predeclared
threshold and every `AVAILABLE` cell passes cutoff, identity, and revision
binding. Any nonavailable cell remains counted. A threshold below 100% may produce
a qualified descriptive profile if predeclared, but it cannot qualify the
protected 100% historical profile.
If any required cell is `UNSUPPORTED`, the profile outcome is
`UNSUPPORTED_CAPABILITY`, including when other insufficiency reasons are also
present. This distinguishes a capability that cannot be supplied from remediable
missing evidence. It does not contaminate profiles that do not require that
feature.

A nonqualified profile has no partial market claim, feature values, labels,
counts of advances/declines, returns, scores, or recommendations. Availability
accounting is evidence about the limitation, not a partial research result.

## Historical qualification result

The historical result depends only on the `OHLCV_ONLY` profile. Sector and
news/event insufficiency or unsupported capability cannot block a historical
profile whose declared core does not require those facts.

The unchanged V1 enum `APPROVED_TO_START_MARKET_STRUCTURE` is a legacy result
label. It now means only that the supplied historical profile is qualified; it
grants no current/live module authorization.

`APPROVED_TO_START_MARKET_STRUCTURE` requires all of the following:

1. the OHLCV-only declaration threshold is exactly 10,000 basis points;
2. its result is `QUALIFIED` with every required cell `AVAILABLE`;
3. every daily bar is proven known by its decision cutoff from the exact evidence
   revision;
4. point-in-time corporate-action/comparability evidence is available for every
   cell;
5. all four protected regions are present and identity-bound;
6. cohort, revision, request, ledger, study, schema, runtime, configuration, and
   report identities are valid; and
7. the supplied-cohort selection/survivorship limitation is disclosed.

Otherwise the gate is `BLOCKED` with exact ordered reasons. Failure adds a
replacement sprint or prospective/paper-validation path; it never weakens the
criteria or fabricates evidence. Following the owner's 2026-08-30 priority
correction, this gate qualifies only historical point-in-time/backtest evidence.
Its historical result name does not gate planning, implementation, delivery,
activation, or use of a current/live Market Structure module. Current/live
Market Structure requires a separate accepted contract and truthful current
same-pass inputs; it makes no inherited historical qualification claim.

## Failure precedence and privacy

Structural type, canonicalization, bound, closed-field, enum, region-order, and
identity errors are invalid request/evidence and produce no domain report. After
structural admission, report reasons are ordered:

1. evidence revision unavailable or identity mismatch;
2. cohort or grid mismatch;
3. revision not point in time;
4. corporate-action comparability evidence not proven;
5. future-known evidence;
6. evidence-revision substitution;
7. bar known-time mismatch;
8. ledger incomplete;
9. `UNSUPPORTED`;
10. `UNLICENSED`;
11. `CONFLICTED`;
12. `STALE`;
13. `NOT_PUBLISHED`;
14. `NOT_RETAINED`;
15. `SOURCE_GAP`;
16. coverage below the predeclared threshold;
17. gate threshold below 100%;
18. OHLCV-only profile not qualified.

Public reports expose aggregate state counts, bounded reason codes, and identities.
They never expose paths, symbols, ISINs, source payloads, bars, context facts,
credentials, environment values, stacks, or raw exceptions. The CLI maps a
structural request failure to `request_invalid` and an unexpected implementation
fault to `internal_error`; neither is mislabeled as market evidence.

## Reproducibility and side effects

Equal admitted evidence and request bytes produce an equal canonical report and
report identity regardless of input object allocation or process time. Exact
retries read the same named revision and produce byte-identical output. A later
correction uses a different revision identity and report identity; it never
rewrites the prior report or claims replay nondeterminism.

The core has zero side effects. The service and CLI are read-only. Missing, held,
unsafe, replaced, corrupt, or lineage-invalid storage returns a blocked
revision-unavailable result when a trustworthy request identity exists, or the
sanitized structural/internal CLI outcome otherwise. They never create, repair,
quarantine, rename, delete, or publish storage objects.

## Frozen adversarial acceptance matrix

| Case family | Required observable result | Prohibited effects |
|---|---|---|
| Generic PIT revision; exact complete ledger; three profiles; four regions; OHLCV threshold 100% | all applicable profiles qualified; exact aggregate accounting; gate approved; canonical retry bytes | no market calculation, provider, clock, write, or private cell leakage |
| Exact Sprint-15 `UPSTOX_RAW` revision with truthful unavailable PIT/comparability cells | affected profiles insufficient; gate blocked with exact reasons; survivorship/raw limitations retained | no PIT, adjustment, continuity, membership, or approval relabel |
| Sector or news/events unavailable or unsupported with OHLCV complete | only requiring profile insufficient or `UNSUPPORTED_CAPABILITY` respectively; OHLCV-only and final gate unaffected | no unsupported-to-missing relabel, neutral context, or cross-profile contamination |
| Zero/51 members; 3/367 decision points; missing region; reordered/overlapping region; zero/10,001 threshold; 73,201 cells; oversized/deep/noncanonical JSON | structural rejection and CLI `request_invalid` | no store read beyond admitted request, report, or provider effect |
| Missing, duplicate, or extra ledger cell; wrong feature interval; cell/cohort/cutoff/affected identity mismatch | exact invalid/insufficient precedence; no dropped denominator | no nearest cell, dedupe, inferred cutoff, or partial claim |
| `AVAILABLE` without required provenance; publication after known; known after cutoff; bar known-time mismatch | future-known or invalid evidence; profile insufficient or structural rejection as frozen | no timestamp clipping, state rewrite, or substitution |
| Every nonavailable state at first/middle/last decision session and in each region | exact state count and reason; unchanged total denominator and region | no date migration or available-only selection |
| Revision/cohort/effective-symbol/symbol-history/provider-mapping/source/receipt/code/config substitution; later correction under old request; legacy adjusted assumption applied to raw | blocked or rejected before claim; changed identities remain visible | no fallback, alias, old-report overwrite, or mixed basis |
| Combined revision, future-known, conflict, stale, missing, and coverage failures | exact global and profile reason order | no first-observed nondeterminism or swallowed failure |
| Missing/unsafe/held/corrupt store; interrupted exact read; exact retry | blocked unavailable or sanitized internal outcome; retry is byte-identical when evidence is restored | no storage mutation, latest discovery, repair, or misleading success |
| Unknown exception at CLI boundary | exit 2, stdout empty, stderr exactly `internal_error` | no stack, path, secret, raw exception, or evidence misclassification |
| Report aggregate or identity replay after 0/1/7/30 inactive days | byte-identical report | no wall-clock dependence |
| Historical exact read of delivered Sprint-15 revision after runtime update | unchanged validated historical evidence identity; new report binds current Sprint-16 runtime identity | no revision rewrite or inherited approval |

## Acceptance evidence

- focused contract tests defend positive behavior, all eight states, three profiles,
  four regions, bounds and limit-plus-one, combined precedence, cutoff and complete
  canonical-equity identity substitution, replay, exact Sprint-15 adaptation,
  sanitized CLI behavior, and
  zero provider/storage mutation;
- one current retained Sprint-15 revision is evaluated without provider activity;
  its truthful gate result is retained even when `BLOCKED`;
- runtime identity is refreshed from formatted source bytes and the installed wheel
  imports and runs the CLI;
- independent exact-byte functional/domain and security/privacy/provenance review
  pass the immutable candidate;
- repository format, lint, type, dead-code, focused, full-suite, coverage,
  diff-check, build, hosted, and secret-scanning gates pass before merge;
- the final Issue #122 record names the exact reviewed revision, evidence, gate
  outcome, limitations, replacement work when blocked, and lifecycle state.

## Explicit non-goals

No index-membership reconstruction, historical context acquisition, provider
selection, network, credentials, source mutation, adjusted-price construction,
corporate-action engine, Market Structure, Price Action, Liquidity/SMC, AI replay,
recommendation, position sizing, order, autonomous trading, guaranteed result, or
financial-adviser claim. A blocked gate is a successful truthful Sprint-16 outcome,
not permission to narrow or bypass the missing evidence.
