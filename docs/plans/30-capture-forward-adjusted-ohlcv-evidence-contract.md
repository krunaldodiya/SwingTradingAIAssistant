# Capture-forward adjusted OHLCV evidence contract

**Status:** ACCEPTED — Sprint 17 / Issue #147
**Parent:** Issue #139
**Prerequisites:** Issues #120 and #122 closed/completed
**Risk:** R3 — financial-research evidence, immutable persistence, temporal and release trust

## Delivery provenance

Issue #155 ports the actionable runtime from exact independently reviewed
baseline candidate `54f8b7c8246d6bd302ca729c01686f635c9809c7` onto current-main
base `5147292fca2d6d2faf0bc7ca83b0fbfe308f7ea0`. The current candidate consists
of that baseline port plus lifecycle-wording corrections in
`5d1052c6cbed327811a15e71db5d36656c9120ac`, bounded FIFO no-hang fixes,
regressions, and transitive runtime-manifest refresh in
`00d32406f6684c378aad68cdb986ec5562c8ef64`, and this provenance
clarification. These post-baseline bytes require fresh exact-byte review before
merge and are not attributed to the baseline candidate review.

This is a delivery-only provenance record. It authorizes no provider call or new
temporal capture and does not relabel later-acquired values as historical
point-in-time evidence. Issue #147 later retained all `4/4` predeclared
completed-session captures. No future-session capture remains; the final
qualification still uses unchanged Plan 29.

## Decision and authority

1. **Expected value:** qualify exact capture-forward point-in-time/comparability evidence for a deferred historical study profile without scheduling or blocking current/live Market Structure.
2. **Scope fit:** one explicit bounded canonical equity cohort, complete adjusted daily OHLC plus source-reported volume, capture-forward cutoffs, and the existing `OHLCV_ONLY` gate.
3. **Material risk:** yfinance is unofficial, personal/research-use, and revision-prone; later data must never be presented as known at an earlier cutoff.
4. **Smallest alternative:** capture exact adjusted OHLCV as known after completed sessions and retain immutable receipts; do not build a corporate-action engine or retrospective backfill.
5. **Decision:** **accepted** for owner-private capture-forward evidence; broader Issue #139 snapshot construction and alternative sources are **deferred**.

The owner approved the Sprint 17 goal, capture-forward adjusted-OHLC strategy, bounded qualification slice, failure rules, continuous-progress rule, and non-goals on 2026-08-29. This extends the accepted Plan 22 yfinance boundary from adjusted close to adjusted OHLC only for exact capture-forward evidence. It does not adopt Yahoo as an authoritative, affiliated, final, institutional, redistribution, or historical-revision source.

Approval of this contract authorizes Issue #147 implementation and owner-private yfinance calls with the frozen arguments below. Following the owner's 2026-08-30 priority correction, this is an independent deferred historical-qualification lane. It does not authorize or gate current/live Market Structure. Current/live Market Structure may proceed only under a separate accepted contract using truthful current same-pass evidence.

The separately packaged `equity_data_downloader` is a deliberately bounded
transport utility, not an implementation of this evidence contract. Its CLI
and Python API call the same core and therefore are not separate acquisition
implementations. It accepts 1–100 provider symbols plus an inclusive date range
and makes one multi-ticker yfinance request. Following the owner's 2026-08-30
storage correction, Parquet below one configured structured-data root is the
utility's sole persisted OHLCV source of truth. The default root is
`~/SwingTradingAIAssistantData`; an explicit absolute root may configure a
different shared or isolated deployment. It has no arbitrary output-file, CSV,
Feather, or duplicate DuckDB row store. DuckDB may query the Parquet directly;
PyArrow is only the reader/writer library. yfinance's internal cookie/timezone
SQLite cache is redirected beneath `<storage-root>/.cache/yfinance` and is
auxiliary provider state, never an OHLCV source or research input. Exact
normalized downloader requests are insert-if-absent: an existing Parquet
dataset is validated and returned with zero provider request or file write. A
different provider version, call configuration, schema, or adjusted-price
request remains a new coherent snapshot; partial append across yfinance
adjustment vintages is prohibited. The operator-facing utility receipt
intentionally reports its normalized provider symbols and derived destination;
the capture serializer's stricter evidence redaction does not govern this
separate local transport receipt.

The utility does not accept ISINs, exchanges, effective canonical symbols,
canonical mappings, exchange schedules, decision cutoffs, capture revisions,
qualification, or Plan 29 semantics. Its Parquet file is not capture-forward
evidence merely because it was downloaded. Conversely, Plan 30's immutable
content-addressed JSON revisions are purpose-specific evidence objects, not a
second downloader catalog or transport format. Completion of the downloader
does not satisfy or replace any Plan 30 acceptance condition; the Plan 30
capture layer remains responsible for every identity, temporal, authority,
validation, and immutable evidence control.


## Working-feature-first boundary

### First working slice

- a provider-specific adjusted-daily OHLCV adapter using the already pinned yfinance dependency;
- one canonical bounded capture request for 1–50 supplied listed-equity identities;
- one immutable owner-private revision store with atomic publication, exact read, content reuse, and conflict-preserving lineage;
- one provider-neutral projection from exact retained captures to Plan 29 point-in-time OHLCV and adjusted-price comparability evidence;
- one operator CLI/service path that captures one requested completed decision session or evaluates an exact set of retained captures;
- deterministic red/green checks for the frozen adversarial matrix;
- a real one-stock qualification lane with four predeclared capture-forward decision sessions and all four protected regions.

The first real cohort is one explicitly supplied supported equity. The reusable feature core accepts 1–50 members and embeds no Nifty-membership check. This preserves the repository mission without making a broader real-cohort claim.

### Later improvements outside Sprint 17

- wider real cohorts or more decision sessions than the accepted qualification set;
- point-in-time index membership, sector, Industry, news, events, or a broad corporate-action archive;
- official-source or commercial-provider alternatives;
- a corporate-action adjustment engine;
- generalized provider routing, concurrent acquisition, replay orchestration, backtest integration, optimization, or public delivery;
- Market Structure, Price Action, Liquidity/SMC, signal, recommendation, position sizing, or order behavior.

Adding any deferred item triggers the scope-expansion circuit breaker.

## Closed source and pricing semantics

The sole adapter is `YfinanceCaptureForwardAdjustedOhlcvAdapterV1`. It invokes the reviewed pinned yfinance version once with:

```text
interval="1d"
actions=False
threads=False
ignore_tz=False
group_by="ticker"
auto_adjust=True
back_adjust=False
repair=False
keepna=True
progress=False
prepost=False
rounding=False
timeout=10
multi_level_index=True
```

The explicit `start` is the first supplied schedule session and the exclusive `end` is one calendar day after the decision session. Every provider mapping effective interval must cover that complete inclusive schedule window, not only the decision session. Provider symbols come only from exact admitted canonical mappings. No retry, fallback, ticker search, inferred symbol, alternate source, pre/post bar, rounding, repair, or provider cache result may fill a cell.

Under the reviewed yfinance implementation, `auto_adjust=True` derives adjusted open, high, and low by multiplying each raw value by `Adj Close / Close`, replaces close with `Adj Close`, and leaves source-reported volume unchanged. Therefore:

- `price_basis = ADJUSTED_YFINANCE_RATIO` applies only to OHLC within one exact capture revision;
- `volume_basis = SOURCE_REPORTED_UNADJUSTED` is explicit and must never be relabelled adjusted;
- raw Upstox values never fill or validate a yfinance adjusted-price cell;
- values from different capture revisions never form one comparable price window;
- retained bytes prove what this owner-private system knew at retrieval, not Yahoo finality or timeless historical truth.

## Closed request and bounds

`CaptureForwardAdjustedOhlcvRequestV1` is canonical sorted-key UTF-8 JSON and
binds:

- `contract_version`;
- 1–50 unique sorted canonical members with ISIN, exchange, effective symbol, symbol-history identity, `YAHOO_FINANCE` provider symbol, mapping version/effective interval, and mapping identity;
- 4–366 supplied official NSE schedule sessions for the requested daily window;
- exact schedule evidence, source, source release, schedule identity, and decision-session official close;
- one decision session equal to the final requested session;
- one aware decision cutoff and one aware evaluation time supplied by the operator;
- fixed provider call configuration identity;
- schema, runtime-source, and configuration identities;
- request identity over the complete canonical evidence preimage.

The owner-private store root is a separate invocation authority: it must be an
absolute path, is identity-pinned by the storage lease, and is never emitted by
the public result. It is deliberately excluded from the portable evidence
request identity so moving the same immutable evidence between separately
admitted owner-private stores neither exposes a private path nor changes its
market/provenance identity.

The decision session must be an admitted completed official session. Its official close must be no later than request evaluation time. The provider retrieval time is generated at the adapter boundary after the response is materialized. A capture can qualify for a decision snapshot only if:

```text
decision_session_official_close_at <= retrieved_at <= decision_cutoff
```

A Saturday retrieval for the preceding Friday session is truthful when the Saturday cutoff is explicit. It is not relabelled as Friday-close knowledge.

The request is decoded, closed-field validated, bounded, canonicalized, and identity-checked before a filesystem lease, provider call, or write. Invalid input has no domain result and no effect.

## Normalized capture revision

`AdjustedOhlcvCaptureRevisionV1` binds:

- contract and request identities;
- exact sorted cohort and schedule identities;
- decision session, official close, retrieval `known_at`, and decision cutoff;
- provider `YAHOO_FINANCE`, exact yfinance library version, adapter/source identity, and fixed call-configuration identity;
- `ADJUSTED_YFINANCE_RATIO` OHLC and `SOURCE_REPORTED_UNADJUSTED` volume bases;
- for every member/session, finite positive decimal open/high/low/close and integral nonnegative volume;
- `low <= min(open, close) <= max(open, close) <= high`;
- exact complete cohort × requested-session grid, with no missing, duplicate, extra, unordered, or out-of-window row;
- canonical mapping, schema, runtime-source, and configuration identities;
- `OWNER_PRIVATE_RESEARCH` permitted use and the fixed source/revision/survivorship limitations;
- parent revision identity when the same request key receives changed provider content;
- canonical content identity and revision SHA-256.

The provider frame must have one `Asia/Kolkata` daily index, exact schedule dates, and the expected ordered MultiIndex columns for every ticker. After a provider response exists, the pinned provider/library identity is checked before interpreting its frame; a non-DataFrame, flat/inverted/reordered/duplicated column structure, or invalid timestamp structure is `FRAME_SCHEMA_INVALID`, while a structurally valid column set with missing or extra coverage is `FRAME_COVERAGE_INCOMPLETE`. NaN, infinity, boolean-as-number, nondecimal value, zero/negative price, fractional/negative volume, timezone mismatch, or provider exception is insufficiency and publishes nothing.

A revision is capture-forward evidence only for the decision snapshot whose cutoff contains its actual retrieval time. Bars in its historical window are source facts known at retrieval; no earlier cutoff is inferred from their session dates.

## Immutable store and effect order

The retained schedule store and capture store use the repository's no-follow, exact-owner, exact-mode, exact-link-count, no-symlink, bounded-root, descriptor-relative, owner-private conventions. Retained schedule evidence is read through separately leased root and child-directory descriptors, bounded exact bytes, and post-read authority revalidation. Every held root and child-directory descriptor is matched to its named path before and after provider and filesystem effects, including the provider-exception path. Public names are derived only from validated lowercase SHA-256 identities. Private paths never appear in public results.

Effect order is:

1. parse, bound, canonicalize, and identity-check the request in memory;
2. verify current runtime identities;
3. exact-resolve the named retained composed-schedule digest from a separately leased owner-private schedule root and match its source, release, `as_of`, complete covered calendar range, exact sessions, and final official close;
4. acquire the capture-store lease and identity-pin the root plus `prepared`, `revisions`, and `requests` directory edges;
5. exact-read the request completion pointer and its content-addressed revision; return `REUSED` without a provider call or write only when the revision matches the complete current request;
6. exact-read any explicitly named correction parent through its completion pointer;
7. when no completion pointer exists and any correction parent is currently admitted, exact-read a request-keyed prepared revision and finish its revision and pointer publication without another provider call;
8. otherwise perform one provider call, revalidating the admitted authority and all directory edges on both response and exception paths;
9. normalize and validate the complete response in memory and build canonical revision bytes and identities;
10. exclusively create the canonical request-keyed prepared revision as owner-private mode 0600, sync and exact-read it through the held descriptor, then commit it to immutable mode 0400;
11. apply the same direct mode-gated publication to the content-addressed revision;
12. after all remaining authority checks and root syncs, create or recover the request completion pointer as mode 0600; hold the referenced revision and every correction-ancestor revision and pointer descriptor while exact-checking each held/name binding immediately before the pointer commit; then mode-commit only the held request pointer inode;
13. return `CAPTURED` only after exact-checking every held revision and pointer binding again after the pointer commit; no later mutating effect changes admission.

No partial revision is admitted. Publication never renames or unlinks a pathname. Each canonical target is created without replacement as mode 0600, which exact readers reject. Canonical bytes are written through its held descriptor, file-fsynced, directory-fsynced, rebound to the same canonical name and exact-read while still mode 0600, then committed by changing only that held inode to mode 0400. A post-commit held-inode exact read detects rebinding without moving, deleting, or modifying the substitute. A complete interrupted mode-0600 prepared record is durable recovery state, not evidence: retry keeps its descriptor open, parses and validates it against the complete request and, for a correction, an exact admitted parent chain, then syncs and mode-commits that same inode without a second provider response. An interrupted content-addressed revision is recovered only from that exact prepared content. A fresh or interrupted request pointer remains mode 0600 while its canonical bytes and complete current request are validated and held descriptors retain the referenced mode-0400 revision plus every mode-0400 correction-ancestor revision and pointer. Every held/name binding is exact-checked immediately before committing that held request-pointer inode and again after commit before success. A precommit mismatch leaves the pointer mode 0600. Malformed, partial, substituted, unsafe, request-mismatched, missing-revision, or ancestor-invalid canonical content remains untouched and fails closed. Cleanup never scans, renames, or deletes storage objects. A changed provider response requires an explicit correction request naming the exact admitted parent; it creates a new immutable revision without overwriting the prior revision. `latest` discovery is not an input to capture or evidence evaluation.

## Point-in-time evidence composition

`CaptureForwardHistoricalEvidenceComposerV1` consumes only explicitly named, exact-read capture revisions. It performs no provider call and no store discovery.

A qualification request supplies 4–366 strictly increasing unique decision points. Each point names:

- one decision session and cutoff;
- exactly one retained capture revision whose decision session matches;
- one protected region: `DEVELOPMENT`, `OUT_OF_SAMPLE`, `UNTOUCHED_TEST`, or `WALK_FORWARD`.

All four regions are nonempty, contiguous, and appear exactly in that order. The exact cohort, mapping, composed schedule source, pricing bases, schema, and configuration must match across captures. Daily composed-schedule releases MAY differ because each decision session retains its own exact acquisition; every capture's schedule identity, source, and release MUST be independently valid and the complete ordered per-capture schedule lineage MUST be bound into the composed source identity. Runtime identity may advance only through an explicitly supported compatible reader; every capture retains its writer identity. The composed evidence source and `runtime_code_identity_sha256` bind one current composer identity calculated from both the capture-forward composer runtime identity and the unchanged Plan 29 runtime identity; the Plan 29 request and report continue to bind the Plan 29 runtime identity itself.

For each member and decision session the composer emits:

- `HistoricalBarKnowledgeV1.known_at = capture.retrieved_at`;
- `DAILY_OHLCV = AVAILABLE`, bound to the exact capture revision and source identity;
- `CORPORATE_ACTION_COMPARABILITY = AVAILABLE`, bound to an adjusted-price classification receipt that hashes the exact member/session adjusted OHLC values, yfinance adjustment-source identity, price basis, retrieval time, and capture revision;
- `published_at = known_at = capture.retrieved_at` for that retained receipt. Retrieval is sampled only after the provider response has materialized, so it is a conservative observation bound for source availability and knowledge; it is not the local repository's later durable-write time or a claim about Yahoo's original publication time.

The composed `HistoricalEvidenceRevisionV1` uses:

```text
temporal_status = POINT_IN_TIME
corporate_action_status = EVALUATED
comparability_status = ESTABLISHED
source_profile = YFINANCE_CAPTURE_FORWARD_ADJUSTED_OHLCV
price_basis = ADJUSTED_YFINANCE_RATIO
permitted_use = OWNER_PRIVATE_RESEARCH
```

These statuses mean only that one exact adjusted-price representation was captured and comparable by the declared provider formula at each cutoff. They do not claim exhaustive corporate-action event coverage, an adjustment engine, economic finality, or reproducibility from a later provider response.

The composer creates no market fact, factor, trend, swing, signal, performance metric, or recommendation.

## Unchanged Plan 29 historical result

Sprint 17 does not modify the Plan 29 reducer, threshold, reason precedence, or
legacy outcome enum. For the deferred historical profile,
`APPROVED_TO_START_MARKET_STRUCTURE` still requires:

1. `OHLCV_ONLY.minimum_coverage_bps == 10_000`;
2. every required `DAILY_OHLCV` and `CORPORATE_ACTION_COMPARABILITY` cell is `AVAILABLE`;
3. every retained receipt is known no later than its exact decision cutoff;
4. exact cohort, decision-grid, capture, source, mapping, schedule, schema, runtime, configuration, ledger, request, evidence, and report identities;
5. all four protected regions; and
6. the explicit fixed supplied-cohort, yfinance, capture-forward, and no-performance limitations.

A pass qualifies only that supplied historical point-in-time profile. The
legacy enum name grants no authorization and is not a prerequisite for a
separately governed current/live Market Structure Issue or specification.
Current/live Market Structure must still choose one truthful complete price
basis for its full current window and may not mix yfinance adjusted prices with
Upstox raw OHLC.

## Failure vocabulary and precedence

Structural type, closed-field, enum, bound, canonicalization, digest, request-identity, schedule-identity, mapping-identity, and runtime-identity failures reject before a domain effect. Every mapping interval must span the complete requested schedule window. A request whose supplied official close is after its evaluation time is structurally invalid.

After admission, one capture result uses this deterministic precedence:

1. retained schedule unavailable, unsafe, held, corrupt, substituted, or mismatched;
2. capture store unavailable, unsafe, held, corrupt, substituted, complete-request mismatch, or exact-read mismatch;
3. provider unavailable or exception, unless post-provider authority revalidation exposes a higher-precedence store failure;
4. provider/library/source identity mismatch, checked before response-frame interpretation;
5. frame timestamp type, timezone, row schema, or column schema invalid;
6. duplicate, missing, extra, unordered, or out-of-window session/member coverage;
7. invalid price or volume value/envelope;
8. retrieval before the retained official close or after the decision cutoff;
9. publication interruption or exact-readback failure.

Composition and gate failures retain Plan 29 precedence. Combined failures never depend on dictionary, filesystem, provider-column, or first-observed order.

Public capture output is limited to a result code, contract version, source profile, price/volume bases, request identity, revision identity when admitted, and bounded reason code. It exposes no store path, symbol, ISIN, bar, source frame, URL, cookie, environment value, stack, or raw exception. CLI structural failures write exactly `request_invalid`; unknown boundary faults write exactly `internal_error` with empty stdout and exit 2.

## Frozen adversarial acceptance matrix

| Case family | Required observable result | Prohibited effects |
|---|---|---|
| One valid member; complete adjusted OHLCV frame; completed session; retrieval before cutoff | immutable revision `CAPTURED`; exact read succeeds; public result redacted | no raw/adjusted mixing, extra provider call, private payload, or market claim |
| Exact retry with existing identical full-request revision | byte-identical `REUSED`; same identities | no provider call, rewrite, timestamp refresh, mismatched-request reuse, or new lineage node |
| Explicit correction request naming a currently admitted parent and returning changed provider content | new immutable revision linked to the exact parent; prepared recovery rechecks the parent | no overwrite, orphaned correction, hidden correction, or old-identity reuse |
| Zero/51 members; 3/367 decision points; 3/367 window sessions; oversized/deep/noncanonical JSON | structural rejection / `request_invalid` | no lease, provider, store read, staging object, or report |
| Session still open, non-session date, wrong official close, schedule/source/release substitution | exact insufficiency or structural rejection before publication | no partial-current bar, weekend inference, schedule fallback, or timestamp clipping |
| Empty/provider exception/wrong yfinance version/wrong call metadata | typed insufficiency with provider identity checked before frame interpretation and store authority rechecked on exception | no retry, fallback, cache relabel, raw exception, swallowed authority failure, or write |
| Wrong timezone; non-DataFrame; flat, inverted, reordered, or duplicate MultiIndex; duplicate/missing/extra/reordered session or ticker | exact schema or coverage reason; no revision | no column guessing, nearest-date selection, dedupe, or partial grid |
| NaN/infinity/bool/zero/negative price; invalid OHLC envelope; negative/fractional volume | exact value reason; no revision | no rounding, repair, coercion, imputation, or dropped cell |
| Retrieved after cutoff; historical session downloaded later and assigned earlier cutoff | blocked future-known evidence | no point-in-time relabel or cutoff widening |
| Mapping interval not spanning the full window, or ISIN/effective-symbol/source/config/schema/runtime/composer/capture/receipt substitution | rejected or Plan 29 blocked with exact identity reason | no alias, latest discovery, fallback, mixed revision, or unbound composer |
| Four exact captures, all protected regions, complete ledger, 100% threshold | canonical composed evidence and Plan 29 approval | no Market Structure calculation or broader authorization |
| Region missing/reordered/noncontiguous; capture/cohort/basis mismatch; ledger cell missing/stale/conflicted | invalid or exact Plan 29 blocked report | no denominator shrink, date migration, neutral missing cell, or approval |
| Combined provider, coverage, future-known, substitution, and store failures | frozen deterministic reason precedence | no first-observed nondeterminism or swallowed failure |
| Interruption before or after the mode commit of the prepared revision, content-addressed revision, or request pointer; canonical-name substitution at any held-inode validation boundary; exact retry | mode-0600 content is never admitted; complete exact content is recovered and committed without another provider call; substitution fails without moving, deleting, or modifying the substitute; only an exact mode-0400 pointer admits its revision and exact parent chain | no pathname rename, unlink, scan, repair, sibling effect, partial admission, or misleading success |
| Symlink, hardlink/unexpected link count, owner/mode/type/device/inode swap, held root, root replacement, child-directory replacement, or replacement combined with provider exception | fail closed before trust or publication | no path following, destructive cleanup, swallowed authority failure, or leaked path |
| Unknown CLI exception | exit 2, empty stdout, stderr exactly `internal_error` | no stack, secret, payload, path, or evidence misclassification |
| Historical exact read after reader/runtime update | old revision bytes and writer identities unchanged; compatible reader identity separately bound | no rewrite or inherited approval |

## Temporal acceptance gate

The real qualification set is predeclared before its values are inspected:

- one exact supplied canonical stock;
- four capture-forward decision sessions;
- unchanged Plan 29 region order `DEVELOPMENT`, `OUT_OF_SAMPLE`, `UNTOUCHED_TEST`, `WALK_FORWARD`;
- each capture occurs only after the supplied official close and before its explicit decision cutoff;
- the final Plan 29 invocation uses exactly 10,000 basis points.

The earliest valid observation for each row is after that session's official close and provider response materialization. Four distinct completed sessions cannot be fabricated or replaced by four regions applied to one capture. Past sessions acquired now may support current/live development without a historical point-in-time claim, but they cannot satisfy this deferred historical qualification.
The temporal gate blocks only evidence-dependent Plan 29 historical qualification. It does not block current/live Market Structure planning, implementation, deterministic validation, delivery, activation, or use. Issue #147 may wait for real captures without consuming current-development WIP while the next owner-approved current/live goal proceeds.

## Acceptance evidence

- focused tests defend every matrix row, including bounds and limit-plus-one, combined precedence, no-effect invalid input, capture exact retry/correction lineage, atomic interruption, identity substitution, cutoff truth, four-region composition, and unchanged Plan 29 integration;
- tests begin with discriminating failures for the frozen matrix before implementation;
- one real owner-private retained capture smoke is recorded for each predeclared session without exposing bars, symbols, paths, or provider payloads;
- the exact four-capture evidence revision produces `APPROVED_TO_START_MARKET_STRUCTURE` from unchanged Plan 29, or the deferred historical point-in-time qualification remains truthfully blocked without blocking current/live Market Structure;
- formatted runtime source bytes refresh every directly and transitively bound runtime-identity manifest;
- Ruff format/check, Pyright, Vulture, focused tests, full suite with coverage, `git diff --check`, sdist/wheel build, and clean installed-wheel import/runtime smoke pass;
- independent exact-byte functional/domain and security/privacy/provenance review pass before merge;
- Issue #147 records exact reviewed revision, capture/evidence/report identities, temporal observations, limitations, hosted gates, and final lifecycle state.

## Explicit non-goals

No retrospective point-in-time backfill, current-data slicing into fake historical states, authoritative Yahoo claim, redistribution, source fallback, arbitrary provider injection, raw/adjusted mixing, volume-adjustment claim, index-membership reconstruction, sector/news/event acquisition, corporate-action event engine, generalized snapshot framework, Market Structure implementation, strategy validation, return claim, recommendation, financial advice, broker order, or autonomous trading.
