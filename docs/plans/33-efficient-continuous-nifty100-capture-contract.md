# Plan 33: efficient continuous Nifty 100 adjusted-capture contract

**Issue:** [#154](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/154)  
**Status:** decision candidate  
**Risk:** R3  
**Contract:** `efficient-current-nifty100-adjusted-capture@v1`

## Authority and outcome

Issue #154 decides and benchmarks the smallest truthful way to acquire one completed daily adjusted-OHLCV window for the current official Nifty 50 plus Nifty Next 50 selection without 100 sequential downloads. This planning Issue changes no runtime, store, scheduler, source profile, market calculation, or historical qualification.

The selected implementation design uses two explicit disjoint 50-member cohorts. Each cohort makes one yfinance `download` invocation with exactly eight library-managed workers, the two invocations run sequentially, and each result is independently validated and retained under the existing immutable adjusted-capture rules. A higher-level Nifty 100 outcome is available only when both exact cohorts are present and compatible. One valid narrower cohort may remain retained after the other fails, but no partial result may be represented as a complete Nifty 100 capture.

The public NSE Indices constituent CSVs establish only the exact current bytes known at retrieval. They contain no internal publication or effective timestamp. Therefore this contract labels the selection `CURRENT_OFFICIAL_LIST_AT_RETRIEVAL`; it does not relabel those bytes as historical point-in-time membership. Capture-forward retention can prove what the system knew from the recorded retrieval onward. Historical membership before that instant still requires separately retained dated release/effective evidence.

## Five-line evaluation

1. **Expected value:** reduce a complete 100-member adjusted daily acquisition from an hours-scale sequential operator experience to a bounded seconds-scale path.
2. **Scope fit:** composes two existing `1..50` adjusted-capture cohorts for the default current Nifty 50 plus Nifty Next 50 focus without changing reusable feature cores.
3. **Material risk:** yfinance is an unofficial per-ticker Yahoo client with no published batch/rate guarantee; unbounded threads, missing mappings, current-list relabelling, partial publication, or raw/adjusted mixing would make the result unsafe or misleading.
4. **Smallest alternative:** two sequential 50-ticker yfinance calls with eight internal workers, existing fixed adjusted settings, existing immutable cohort retention, and a read-time complete-union check; no provider framework, queue, scheduler, database, or cross-cohort transaction subsystem.
5. **Decision:** **accepted as the Plan 33 candidate** for independent exact review; production implementation remains a separate bounded Issue.

## Source verification and decision

### Current selection inputs

The current selection source is the pair of official NSE Indices CSV endpoints:

- `https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv`; and
- `https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv`.

Each retrieval must retain exact bytes, URL, response receipt, retrieval time, content SHA-256, parser/schema identity, and the resulting ordered canonical rows. Admission requires:

- exact header `Company Name,Industry,Symbol,Series,ISIN Code`;
- exactly 50 data rows in each artifact;
- `Series == EQ` for every row;
- nonempty unique ISIN and symbol values within each artifact;
- disjoint ISIN sets across the two artifacts; and
- exactly 100 unique ISINs in the union.

The CSV `Industry` field is not a membership timestamp or canonical provider mapping. HTTP transport metadata is not promoted to publisher-effective evidence. A missing, malformed, duplicated, overlapping, or conflicted list returns insufficient evidence and prevents a complete Nifty 100 outcome.

### Adjusted daily provider

yfinance `1.6.0` remains the already accepted owner-private adjusted daily research provider. Its documentation states that the tool is intended for research and educational purposes, the underlying Yahoo Finance API is intended for personal use only, and users must consult Yahoo's terms. No payload is redistributed. yfinance is not a broker feed, official Yahoo client, strict point-in-time authority, or final/revision authority.

The documented `download` boundary accepts a ticker list and `threads: bool | int`. Source inspection of pinned `yfinance/multi.py` proves that this is not one provider-side batch request: with `threads=False`, yfinance loops through tickers and calls `_download_one` sequentially; with an integer, it bounds library-managed `_download_one_threaded` work to that count. The delivered adjusted-close adapter currently passes `threads=False`, so its multi-ticker call is sequential internally.

Plan 33 freezes `threads=8`. It does not use `threads=True`, CPU-derived worker counts, multiple concurrent cohort calls, an external executor, retries, or a second provider. The two 50-member calls run sequentially so total in-flight work never intentionally exceeds eight tickers. yfinance debug logging is rejected before the call because pinned source silently forces `threads=False` when debug logging is enabled. The exact adjusted call remains:

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

The nonpublishing benchmark was predeclared in [Issue #154](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/154#issuecomment-5479726269). It used:

- pinned yfinance `1.6.0`;
- exact eight-worker configuration above;
- two sequential 50-member cohorts;
- the retained official Nifty 50 snapshot and retained official Nifty 100 artifact, whose exact disjoint set difference produced 50 Nifty 50 plus 50 Nifty Next 50 benchmark members;
- the retained composed NSE schedule for 21 completed sessions from `2026-08-03` through `2026-08-31`;
- an isolated temporary yfinance cache outside `~/SwingTradingAIAssistantData`;
- in-memory normalization only; and
- no retained bars, private-store mutation, raw payload publication, retry, or fallback.

A harness preflight passed schedule objects instead of date strings and failed before producing a frame. It is excluded from all timing and completeness figures and retained no output. The corrected benchmark result was:

| Cohort | Members | Complete | Failed | Sessions | Time | Timezone |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Nifty 50 | 50 | 50 | 0 | 21 | 1.988 s | `Asia/Kolkata` |
| Nifty Next 50 | 50 | 50 | 0 | 21 | 2.882 s | `Asia/Kolkata` |
| **Complete union** | **100** | **100** | **0** | **21** | **5.072 s total** | `Asia/Kolkata` |

This is one source-behaviour observation on the reference workstation and network, not a provider SLA or guaranteed future speed. It proves that bounded concurrency removes the observed sequential bottleneck for this exact completed window.

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

1. acquire and retain both exact official current constituent CSV artifacts;
2. admit the two exact disjoint 50-member canonical cohorts and their yfinance mappings;
3. use one admitted composed schedule and completed decision session;
4. acquire the Nifty 50 cohort with `threads=8`;
5. validate and retain/reuse its immutable adjusted-capture revision;
6. acquire, validate, and retain/reuse the Nifty Next 50 cohort the same way;
7. return complete Nifty 100 only when both revisions bind the same selection, schedule, decision session, source profile, configuration, and compatible retrieval boundary; and
8. emit a sanitized counts/identities/timing result without member symbols, ISINs, bars, provider payloads, paths, cookies, or cache content.

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

Each cohort returns exactly one of:

- `REUSED`: the exact admitted request already resolves to a valid immutable revision;
- `INSERTED`: one new valid immutable revision was committed;
- `MALFORMED_INPUT`;
- `UNSUPPORTED_CAPABILITY`; or
- `INSUFFICIENT_EVIDENCE` with one closed reason.

The higher-level outcome is:

- `COMPLETE_CURRENT_NIFTY100_CAPTURE` only when both cohort outcomes resolve to valid compatible revisions; or
- `INCOMPLETE_CURRENT_NIFTY100_CAPTURE` with the exact failed cohort and closed reason.

`REUSED` and `INSERTED` are equally valid revision references. Member facts are never dropped to turn 99 members into success. A valid independently retained cohort is not deleted when the other cohort fails, but it is labelled only by its own cohort identity and cannot authorize the union claim.

## Adversarial acceptance matrix

| Case | Observable result | Prohibited effects | Evidence method |
| --- | --- | --- | --- |
| Two exact disjoint 50-member lists, mappings, schedule, and complete frames | Two valid revision references; complete union; sanitized timing/counts | Raw/member publication; fallback | Focused positive plus one completed-session smoke |
| Either list has 49, 51, duplicate, overlap, non-`EQ`, blank identity, wrong header, or limit-plus-one bytes | `MALFORMED_INPUT` or source insufficiency before yfinance | Provider call; store/cache publication | Discriminating parser/admission tests |
| Current CSV lacks publisher-effective time | Current-at-retrieval label only | Historical/pre-retrieval membership claim | Serialization/nonclaim test |
| Missing, stale, conflicting, or substituted canonical/yfinance mapping | `UNSUPPORTED_CAPABILITY` or `INSUFFICIENT_EVIDENCE` | `.NS` inference; wrong ticker call | Mapping interval/identity tests |
| Invalid schedule, incomplete decision session, wrong close/cutoff, or identity substitution | Insufficient before provider call | Partial-session capture; inferred calendar | Schedule/temporal tests |
| Worker value is default, `True`, zero, negative, or above eight; or yfinance debug logging is enabled | Configuration rejection | Unbounded, CPU-derived, or silently sequential execution | Configuration/logging tests |
| Provider exception, ordinary timeout, empty frame, or unexpected schema | Exact cohort insufficiency | Retry; fallback; partial publish | Adapter failure tests |
| Missing/duplicated session or ticker; NaN/non-finite/non-positive price; negative/non-integral volume; wrong timezone | Exact cohort insufficiency | Member/session dropping; value repair | Frame matrix tests |
| First cohort retained; second cohort fails | Incomplete union; first cohort remains narrowly valid | Complete Nifty 100 claim; deletion of valid revision | Interruption/combined-failure test |
| Interruption after preparation but before one cohort commit | Existing store rollback/recovery semantics; incomplete union | Partial revision admission; overwrite | Existing atomic-store interruption tests plus orchestration test |
| Exact retry | Same revision identity and `REUSED`; no provider call/write | Duplicate revision; changed known-at | Retry test |
| Same request identity points to invalid/conflicting bytes | Fail closed | Repair, overwrite, or provider call that masks conflict | Conflict/substitution tests |
| Raw Upstox or another provider appears in either cohort | Unsupported/insufficient union | Raw/adjusted mixing; silent fallback | Provider/price-basis substitution tests |
| One cohort uses another selection, schedule, decision session, configuration, or source profile | Incomplete union | Cross-context composition | Union binding tests |
| Benchmark or smoke exceeds frozen budgets | Candidate fails performance acceptance | Hours-scale qualification presented as success | Timed focused benchmark/smoke |
| Public serialization | Counts, states, identities, timing only | Symbols, ISINs, OHLCV, paths, cookies, payloads | Redaction tests |

Combined validation precedence is:

1. authorization and enablement;
2. malformed request and bounds;
3. constituent-source identity/schema/cardinality/disjointness;
4. canonical identity and mapping support;
5. schedule and completed-session temporal admission;
6. existing request/revision conflict or reusable exact revision;
7. configuration and concurrency admission;
8. provider/frame evidence;
9. immutable retention; and
10. cross-cohort union compatibility.

An earlier failure prevents every later effect for that cohort. Union evaluation occurs only from retained/reused cohort outcomes.

## Acceptance and review boundary

Issue #154 is complete when this contract records source evidence and the measured benchmark, an independent Sol/high exact-byte review approves the decision, a bounded implementation Issue is created from the frozen contract, applicable documentation and repository gates pass, and the planning PR is reviewed and merged.

The implementation Issue must add discriminating failing checks for every applicable matrix row before changing runtime. It requires a completed-session current smoke because it will claim real provider acquisition behaviour, but it does not require four distinct sessions or unchanged Plan 29. Sprint 17 remains a separate nonblocking historical qualification lane.
