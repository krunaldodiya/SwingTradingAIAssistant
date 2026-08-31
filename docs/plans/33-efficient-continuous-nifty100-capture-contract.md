# Plan 33: efficient continuous Nifty 100 adjusted-capture contract

**Issue:** [#154](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/154)  
**Status:** decision candidate  
**Risk:** R3  
**Contract:** `efficient-current-nifty100-adjusted-capture@v1`

## Authority and outcome

Issue #154 decides and benchmarks the smallest truthful way to acquire one completed daily adjusted-OHLCV window for the current official Nifty 50 plus Nifty Next 50 selection without 100 sequential downloads. This planning Issue changes no runtime, store, scheduler, source profile, market calculation, or historical qualification.

The selected implementation design uses two explicit disjoint 50-member cohorts. Before yfinance is imported, the operator process creates and verifies one named `multitasking==0.0.13` thread pool with exactly eight permits. Each cohort then makes one yfinance `download` invocation against that same verified pool, the two invocations run sequentially, and each result is independently validated and retained under the existing immutable adjusted-capture rules. A higher-level Nifty 100 outcome is available only when both exact cohorts are present and compatible. One valid narrower cohort may remain retained after the other fails, but no partial result may be represented as a complete Nifty 100 capture.

The public NSE Indices constituent CSVs establish only the exact current bytes known at retrieval. They contain no internal publication or effective timestamp. Therefore this contract labels the selection `CURRENT_OFFICIAL_LIST_AT_RETRIEVAL`; it does not relabel those bytes as historical point-in-time membership. Capture-forward retention can prove what the system knew from the recorded retrieval onward. Historical membership before that instant still requires separately retained dated release/effective evidence.

## Five-line evaluation

1. **Expected value:** reduce a complete 100-member adjusted daily acquisition from an hours-scale sequential operator experience to a bounded seconds-scale path.
2. **Scope fit:** composes two existing `1..50` adjusted-capture cohorts for the default current Nifty 50 plus Nifty Next 50 focus without changing reusable feature cores.
3. **Material risk:** yfinance is an unofficial per-ticker Yahoo client with no published batch/rate guarantee; unbounded threads, missing mappings, current-list relabelling, partial publication, or raw/adjusted mixing would make the result unsafe or misleading.
4. **Smallest alternative:** two sequential 50-ticker yfinance calls with eight internal workers, existing fixed adjusted settings, existing immutable cohort retention, and a read-time complete-union check; no provider framework, queue, scheduler, database, or cross-cohort transaction subsystem.
5. **Decision:** **accepted as the Plan 33 candidate** for independent exact review; production implementation remains a separate bounded Issue.

## Source verification and decision

### Current selection inputs

The current selection sources are the pair of official NSE Indices constituent
CSV endpoints:

- `https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv`; and
- `https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv`.

The official
`https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv`
artifact is acquired in the same bounded source step as a union-consistency
witness. It is not a second membership authority or a timestamp.

Each retrieval must retain exact bytes, URL, response receipt, retrieval time,
content SHA-256, parser/schema identity, and the resulting canonical rows.
Source rows are sorted by `(ISIN Code, Symbol)`; the fixed cohort order is
`NIFTY_50`, then `NIFTY_NEXT_50`. Admission requires:

- exact header `Company Name,Industry,Symbol,Series,ISIN Code`;
- exactly 50 data rows in each constituent artifact and exactly 100 in the
  witness;
- `Series == EQ` for every row;
- nonempty unique ISIN and symbol values within each artifact;
- disjoint ISIN sets across the two constituent artifacts;
- exactly 100 unique ISINs in their union; and
- exact equality between that union and the witness ISIN/symbol set.

The CSV `Industry` field is not a membership timestamp or canonical provider
mapping. HTTP transport metadata is not promoted to publisher-effective
evidence. Malformed caller-owned request fields return `MALFORMED_INPUT`.
A missing, malformed, wrongly sized, duplicated, overlapping, or non-`EQ`
source artifact returns
`INSUFFICIENT_EVIDENCE/CONSTITUENT_SOURCE_INVALID`. A witness/union mismatch,
identity substitution, or bytes that change during paired admission returns
`INSUFFICIENT_EVIDENCE/CONSTITUENT_SOURCE_CONFLICT`. Both occur before
yfinance or store effects.

### Adjusted daily provider

yfinance `1.6.0` remains the already accepted owner-private adjusted daily research provider. Its documentation states that the tool is intended for research and educational purposes, the underlying Yahoo Finance API is intended for personal use only, and users must consult Yahoo's terms. No payload is redistributed. yfinance is not a broker feed, official Yahoo client, strict point-in-time authority, or final/revision authority.

The documented `download` boundary accepts a ticker list and `threads: bool | int`. Source inspection of pinned `yfinance/multi.py` proves that this is not one provider-side batch request: with `threads=False`, yfinance loops through tickers and calls `_download_one` sequentially; with an integer, it submits `_download_one_threaded` work through `multitasking`.

Pinned `multitasking==0.0.13` creates its default CPU-sized pool when yfinance's threaded function is decorated, and `set_max_threads()` affects only new pools. Therefore `threads=8` alone does not impose an eight-worker ceiling. Plan 33 requires a fresh single-purpose operator process to import `multitasking`, call `createPool(name="plan33_yfinance_8", threads=8, engine="thread")`, assert the active pool name/engine/count, and only then import yfinance. The same assertion runs immediately before each cohort call. An earlier yfinance import, another active pool, concurrent Plan 33 invocation in the same process, default/`True` threads, debug logging, or any pool value other than eight is a configuration failure before provider work. The two calls run sequentially, with no external executor, retry, or second provider. The exact adjusted call remains:

```python
yfinance.download(
    tickers=provider_ticker_sequence,
    start=S0.isoformat(),
    end=(S20 + timedelta(days=1)).isoformat(),
    interval="1d",
    actions=False,
    threads=8,
    ignore_tz=False,
    group_by="ticker",
    auto_adjust=True,
    back_adjust=False,
    repair=False,
    keepna=True,
    progress=False,
    prepost=False,
    rounding=False,
    timeout=10,
    multi_level_index=True,
)
```

Production does not derive yfinance symbols by appending `.NS`. Every member must arrive with canonical ISIN, NSE exchange, effective symbol interval, and a versioned cutoff-valid yfinance mapping. The benchmark-only suffix composition tested throughput and is not mapping authority.

### Rejected Upstox substitution

Upstox V3 historical candles remain the primary raw/current alternative, but its documented path accepts one `instrument_key` per request. Its standard-API limits are 50 requests/second, 500/minute, and 2,000/30 minutes. A bounded concurrent Upstox design could avoid sequential latency, but it would produce the separate Upstox raw basis, require authenticated per-instrument requests, and would not be a drop-in replacement for this yfinance adjusted capture. Provider substitution or raw/adjusted mixing is rejected for Plan 33.

## Measured benchmark

The nonpublishing benchmark was predeclared in [Issue #154](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/154#issuecomment-5479726269). Independent review found that the first nominal `threads=8` run still used `multitasking`'s already-created CPU-sized pool, so its 5.072-second observation is explicitly superseded for the exact-worker claim. The accepted corrected benchmark was predeclared again and used:

- a fresh process state;
- pinned `multitasking==0.0.13`;
- one named `issue154_exact_eight` pool created with `engine=thread` and
  `threads=8` before importing pinned yfinance `1.6.0`;
- active pool name/engine/count assertions before both calls;
- two sequential 50-member cohorts;
- the retained official Nifty 50 snapshot and retained official Nifty 100 artifact, whose exact disjoint set difference produced 50 Nifty 50 plus 50 Nifty Next 50 benchmark members;
- the retained composed NSE schedule for 21 completed sessions from `2026-08-03` through `2026-08-31`;
- an isolated temporary yfinance cache outside `~/SwingTradingAIAssistantData`;
- in-memory normalization only; and
- no retained bars, private-store mutation, raw payload publication, retry, or fallback.

A harness preflight passed schedule objects instead of date strings and failed before producing a frame. It is excluded from all timing and completeness figures and retained no output. The corrected exact-eight result was:

| Cohort | Members | Complete | Failed | Sessions | Time | Timezone |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Nifty 50 | 50 | 50 | 0 | 21 | 3.388 s | `Asia/Kolkata` |
| Nifty Next 50 | 50 | 50 | 0 | 21 | 2.408 s | `Asia/Kolkata` |
| **Complete union** | **100** | **100** | **0** | **21** | **5.992 s total** | `Asia/Kolkata` |

This is one source-behaviour observation on the reference workstation and network, not a provider SLA or guaranteed future speed. It proves that the explicitly created eight-permit pool removes the observed sequential bottleneck for this exact completed window.

The implementation qualification budget is:

- no more than eight in-flight yfinance ticker tasks;
- one attempt per member and no retry loop;
- at most 30 seconds per valid 50-member cohort in the focused reference benchmark;
- at most 60 seconds total for the two provider/normalization calls in that benchmark; and
- at most 180 seconds for the complete operator command including input admission, validation, immutable writes/reuse checks, and sanitized output.

A candidate that misses these qualification budgets is not accepted. The 10-second yfinance request timeout and finite worker/task counts bound ordinary failure behaviour, but Plan 33 does not claim a process-level hard kill against a defective dependency. Process isolation and forced termination remain a later resilience improvement rather than an invented first-slice subsystem.

## Working-feature-first partition

### Issue #154 planning slice

Issue #154 completes only:

- authority and source verification;
- existing-path and concurrency inspection;
- one complete nonpublishing Nifty 100 benchmark;
- this closed source/runtime/failure contract;
- independent exact planning review;
- one separately bounded implementation Issue; and
- documentation, local gates, PR, hosted checks, and merge.

It makes no production provider call after the benchmark, implements no runtime, and changes no existing market-data semantics.

### Separately tracked implementation slice

The first implementation Issue may deliver only one repeatable operator-triggered completed-session capture:

1. acquire and retain the two exact official constituent artifacts plus the
   exact Nifty 100 consistency witness;
2. validate exact cardinality, schema, disjointness, witness equality, fixed
   cohort order, and canonical row order;
3. admit the two exact 50-member canonical cohorts and their yfinance mappings;
4. use one admitted composed schedule and completed decision session;
5. create and verify the named eight-permit pool before importing yfinance;
6. resolve valid existing revisions for both cohorts;
7. acquire, validate, and retain/reuse every unresolved cohort in fixed
   `NIFTY_50`, `NIFTY_NEXT_50` order, attempting the second unresolved cohort
   even when the first has a provider/frame failure;
8. return complete Nifty 100 only when both revisions bind the same selection,
   schedule, decision session, source profile, configuration, and compatible
   retrieval boundary; and
9. emit a sanitized ordered pair of cohort states/reasons plus
   counts/identities/timing without member symbols, ISINs, bars, provider
   payloads, paths, cookies, or cache content.

The implementation reuses the existing yfinance/curl-cffi source boundary and immutable capture rules. It versions the changed `threads=8` configuration rather than weakening or silently mutating the delivered `threads=False` contract.

The reviewed Plan 30 capture-forward runtime candidate is not present on the
current main branch. The implementation Issue must make that dependency
explicit: it may target a separately merged equivalent capture runtime or own
an authorized delivery split of the already reviewed actionable Plan 30
runtime while leaving #147 open for its three remaining temporal observations.
It must not wait for those future sessions, copy unreviewed quarantine bytes,
or imply that #147's historical qualification has passed.

### Later improvements

The following do not block Issue #154 or the first implementation slice:

- an in-process or OS scheduler, laptop wake guarantee, remote runner, alerting, queue, daemon, or hosted service;
- process isolation, hard termination, generalized retry/backoff, circuit breaker, adaptive rate control, or telemetry;
- a provider framework, alternative adjusted provider, Upstox raw substitution, or dual-source reconciliation;
- cross-cohort atomic transaction, generalized multi-cohort store, archive replay, durable orchestration state, or recovery engine;
- historical constituent reconstruction, dated release ingestion, effective-notice composition, backfill, or pre-retrieval point-in-time membership claims;
- more than 100 instruments, arbitrary index composition, ETF/F&O/crypto/multi-asset support, intraday capture, or tick data;
- public payload/API/UI/MCP delivery, redistribution, signal, score, recommendation, order, or financial-adviser behaviour; and
- Sprint 17's remaining three future-session captures or unchanged Plan 29 qualification.

Adding any later item triggers the scope-expansion circuit breaker.

## Closed outcomes and composition

Shared admission returns exactly one of:

- `MALFORMED_INPUT` for invalid caller-owned fields or bounds;
- `UNSUPPORTED_CAPABILITY` for an unsupported canonical instrument or missing
  mapping capability; or
- `INSUFFICIENT_EVIDENCE` with exactly one of
  `CONSTITUENT_SOURCE_INVALID`, `CONSTITUENT_SOURCE_CONFLICT`,
  `MAPPING_EVIDENCE_INVALID`, `SCHEDULE_INVALID`, or `EVIDENCE_CONFLICT`.

After shared admission, each cohort returns exactly one ordered outcome:

- `REUSED`: the exact admitted request already resolves to a valid immutable revision;
- `INSERTED`: one new valid immutable revision was committed;
- `UNSUPPORTED_CAPABILITY`; or
- `INSUFFICIENT_EVIDENCE` with exactly one of `CONFIGURATION_INVALID`,
  `PROVIDER_RATE_LIMITED`, `PROVIDER_ERROR`, `PROVIDER_FRAME_INCOMPLETE`,
  `PROVIDER_BASIS_INVALID`, or `RETENTION_FAILED`.

The higher-level outcome is:

- `COMPLETE_CURRENT_NIFTY100_CAPTURE` only when both ordered cohort outcomes
  resolve to valid compatible revisions; or
- `INCOMPLETE_CURRENT_NIFTY100_CAPTURE` with an exact two-row
  `(NIFTY_50, NIFTY_NEXT_50)` outcome tuple. Both failures are retained when
  both cohorts fail; a successful row carries its valid revision reference.
  `union_reason` is absent when at least one cohort failed and is exactly
  `UNION_INCOMPATIBLE` when both cohort revisions are individually valid but
  cannot be composed.

`REUSED` and `INSERTED` are equally valid revision references. Member facts
are never dropped to turn 99 members into success. A valid independently
retained cohort is not deleted when the other cohort fails, but it is labelled
only by its own cohort identity and cannot authorize the union claim.

## Adversarial acceptance matrix

| Case | Observable result | Prohibited effects | Evidence method |
| --- | --- | --- | --- |
| Two exact disjoint 50-member lists, exact 100-member witness, mappings, schedule, named pool, and complete frames | Two valid revision references; complete union; sanitized timing/counts | Raw/member publication; fallback | Focused positive plus one completed-session smoke |
| Caller request has malformed fields, bounds, or limit-plus-one bytes | `MALFORMED_INPUT` before source/provider/store effects | Source fetch; provider call; publication | Request admission tests |
| A fetched list/witness has 49/51/101 rows, duplicate, overlap, non-`EQ`, blank identity, wrong header, or limit-plus-one bytes | `INSUFFICIENT_EVIDENCE/CONSTITUENT_SOURCE_INVALID` before yfinance/store effects | Member repair; source substitution; partial selection | Source parser/composition tests |
| Pair union and official witness disagree, identity is substituted, or bytes change during paired admission | `INSUFFICIENT_EVIDENCE/CONSTITUENT_SOURCE_CONFLICT` before yfinance/store effects | Either cohort provider call or publication | Conflict/substitution test |
| Official source bytes validly change on the next run | New selection/request identity; old selection and revisions remain immutable | Mutation, append under old identity, or historical relabelling | Membership-transition test |
| Current CSV lacks publisher-effective time | Current-at-retrieval label only | Historical/pre-retrieval membership claim | Serialization/nonclaim test |
| Mapping capability is absent | `UNSUPPORTED_CAPABILITY` before provider call | `.NS` inference; wrong ticker call | Missing-capability test |
| Mapping evidence is stale, conflicting, or substituted | `INSUFFICIENT_EVIDENCE/MAPPING_EVIDENCE_INVALID` before provider call | Mapping repair or wrong ticker call | Mapping interval/identity tests |
| Invalid schedule, incomplete decision session, wrong close/cutoff, or schedule identity substitution | `INSUFFICIENT_EVIDENCE/SCHEDULE_INVALID` before provider call | Partial-session capture; inferred calendar | Schedule/temporal tests |
| Pool was not created before yfinance import; active pool name/engine/count differs; worker value is default/`True`/invalid; concurrent same-process invocation or debug logging exists | `INSUFFICIENT_EVIDENCE/CONFIGURATION_INVALID` for every unresolved cohort before provider work | CPU-derived, unbounded, silently sequential, or pool-raced execution | Import-order/pool/configuration/logging tests |
| Provider explicitly reports rate limiting | `INSUFFICIENT_EVIDENCE/PROVIDER_RATE_LIMITED` for that cohort; second unresolved cohort still follows fixed order; no retry | Retry, fallback, or partial cohort publish | Adapter rate-limit/combined-failure test |
| Provider raises an ordinary non-rate exception or timeout | `INSUFFICIENT_EVIDENCE/PROVIDER_ERROR` for that cohort | Retry; fallback; partial cohort publish | Adapter failure tests |
| Provider rate limiting is not observable but the returned frame is incomplete | `INSUFFICIENT_EVIDENCE/PROVIDER_FRAME_INCOMPLETE`; do not infer HTTP 429 | Invented rate-limit evidence; retry; partial publish | Observable-evidence test |
| Empty/unexpected-schema frame, missing/duplicated session or ticker, NaN/non-finite/non-positive price, negative/non-integral volume, or wrong timezone | `INSUFFICIENT_EVIDENCE/PROVIDER_FRAME_INCOMPLETE` for that cohort | Member/session dropping; value repair | Frame matrix tests |
| Complete yfinance-adjusted window crosses a provider-reported corporate action | Capture remains one adjusted revision; volume remains source-reported unadjusted; limitation retained | Upstox/raw substitution; local adjustment inference | Corporate-action basis test |
| A later authorized request observes revised adjusted bytes | New immutable revision/lineage; old revision unchanged | Overwrite or relabelling old known-at | Revision/correction test |
| First cohort retained; second cohort fails | Ordered incomplete tuple with valid first revision and exact second reason | Complete Nifty 100 claim; deletion of valid revision | Interruption/combined-failure test |
| Both cohorts fail differently | Ordered two-row incomplete tuple containing both exact reasons | Single ambiguous reason; nondeterministic short-circuit | Combined-failure precedence test |
| Interruption or write failure after preparation but before one cohort commit | `INSUFFICIENT_EVIDENCE/RETENTION_FAILED` for that cohort; existing store rollback/recovery semantics; ordered incomplete union | Partial revision admission; overwrite | Existing atomic-store interruption tests plus orchestration test |
| Exact retry | Same revision identity and `REUSED`; no provider call/write | Duplicate revision; changed known-at | Retry test |
| Either request identity points to invalid/conflicting bytes | `INSUFFICIENT_EVIDENCE/EVIDENCE_CONFLICT`; no new provider/store effect | Repair, overwrite, or provider call that masks conflict | Conflict/substitution tests |
| Raw Upstox or another provider appears in either cohort | `INSUFFICIENT_EVIDENCE/PROVIDER_BASIS_INVALID` | Raw/adjusted mixing; silent fallback | Provider/price-basis substitution tests |
| One cohort uses another selection, schedule, decision session, configuration, source profile, or incompatible retrieval boundary | Both cohort rows remain exact; `INCOMPLETE_CURRENT_NIFTY100_CAPTURE/UNION_INCOMPATIBLE` | Cross-context composition | Union binding tests |
| Source/canonical rows or publication attempts arrive in another order | Canonical source rows `(ISIN Code, Symbol)`; canonical members `(isin, exchange, effective_symbol, provider_symbol)`; cohorts/publication `NIFTY_50` then `NIFTY_NEXT_50` | Input-order identity drift; nondeterministic output/write order | Permutation/publication-order tests |
| Benchmark or smoke exceeds frozen budgets | Candidate fails performance acceptance | Hours-scale qualification presented as success | Timed focused benchmark/smoke |
| Public serialization | Ordered states/reasons, counts, identities, timing only | Symbols, ISINs, OHLCV, paths, cookies, payloads | Redaction tests |

Combined validation and effect precedence is:

1. authorization and enablement;
2. malformed caller request and bounds;
3. all three constituent-source identities, schemas, cardinalities,
   disjointness, witness equality, and canonical order;
4. canonical identity and mapping support;
5. schedule and completed-session temporal admission;
6. both existing request/revision lookups in fixed cohort order;
7. any existing-byte conflict, which stops all new provider/store effects;
8. when at least one cohort remains unresolved, named-pool import-order and
   configuration admission;
9. unresolved cohort provider, frame, and immutable-retention processing in
   fixed `NIFTY_50`, `NIFTY_NEXT_50` order; and
10. cross-cohort union compatibility.

An earlier shared failure prevents every later effect. After shared admission,
provider/frame failures do not short-circuit the second unresolved cohort:
both exact cohort rows are produced in fixed order. A valid existing or newly
retained cohort remains narrowly valid. Union evaluation occurs only after the
ordered pair is complete.

## Acceptance and review boundary

Issue #154 is complete when this contract records source evidence and the measured benchmark, an independent Sol/high exact-byte review approves the decision, a bounded implementation Issue is created from the frozen contract, applicable documentation and repository gates pass, and the planning PR is reviewed and merged.

The implementation Issue must add discriminating failing checks for every applicable matrix row before changing runtime. It requires a completed-session current smoke because it will claim real provider acquisition behaviour, but it does not require four distinct sessions or unchanged Plan 29. Sprint 17 remains a separate nonblocking historical qualification lane.
