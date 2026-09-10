# Plan 33: efficient continuous Nifty 100 adjusted-capture contract

> Successor work (2026-09-10):
> [Issue #184](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/184)
> owns the [unreleased BharatStock cutover](../roadmap.md#bharatstock-migration-direction).
> `current-nifty100-bharatstock-capture@v2` selects the same official list
> through versioned current-observation evidence and composes Plan30 V2.
> The old Yahoo-specific pool, cadence, session and acknowledgement below
> describe historical V1 only; they are not BharatStock requirements.

V2 must retain and validate exact Nifty50, Next50 and Nifty100 witness bytes,
source identities and retrieval times, then bind the ordered 100-member union
and source observation to the exact capture request. Reuse must resolve that
retained request/selection/revision binding before any source or provider call.
Later observations of the same membership have distinct source provenance;
they must not overwrite prior evidence or manufacture earlier knowledge.
An incomplete capture still accounts for all 100 members, with no claim that
99 observations constitute complete Nifty100 research. The public surface stays
sanitized; source/member evidence stays private. Provider replacement alone
does not satisfy #183, and no V1 approval transfers to this successor.

> Harness portability: historical named-model review choices below record the
> original delivery. New work follows the [canonical agent policy](../mandatory-agent-instructions.md)
> and [portable review procedure](../agent-workflow.md); independent exact-byte
> review and every product acceptance criterion remain required.

**Issue:** [#154](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/154)
**Status:** accepted implementation contract
**Risk:** R3
**Contract:** `efficient-current-nifty100-adjusted-capture@v1`

## Authority and outcome

Issue #154 decides and benchmarks the smallest truthful way to acquire one completed daily adjusted-OHLCV window for the current official Nifty 50 plus Nifty Next 50 selection without 100 sequential downloads. This planning Issue changes no runtime, store, scheduler, source profile, market calculation, or historical qualification.

The selected implementation design uses two explicit disjoint 50-member cohorts. Before yfinance is imported, the operator process creates and verifies one named `multitasking==0.0.13` thread pool with exactly eight permits and one supplied bounded curl-cffi session. The session spaces all HTTP request starts at least 125 milliseconds apart, bounds every request target and response body, and stops an observed HTTP 429 before yfinance can issue its dependency-internal alternate-cookie request. Each cohort then makes one yfinance `download` invocation against that same pool and session, the two invocations run sequentially, and each result is independently validated and retained under the existing immutable adjusted-capture rules. A higher-level Nifty 100 outcome is available only when both exact cohorts are present and compatible. One valid narrower cohort may remain retained after the other fails, but no partial result may be represented as a complete Nifty 100 capture.

The public NSE Indices constituent CSVs establish only the exact current bytes known at retrieval. They contain no internal publication or effective timestamp. Therefore this contract labels the selection `CURRENT_OFFICIAL_LIST_AT_RETRIEVAL`; it does not relabel those bytes as historical point-in-time membership. Capture-forward retention can prove what the system knew from the recorded retrieval onward. Historical membership before that instant still requires separately retained dated release/effective evidence.

## Five-line evaluation

1. **Expected value:** reduce a complete 100-member adjusted daily acquisition from an hours-scale sequential operator experience to a bounded seconds-scale path.
2. **Scope fit:** composes two existing `1..50` adjusted-capture cohorts for the default current Nifty 50 plus Nifty Next 50 focus without changing reusable feature cores.
3. **Material risk:** yfinance is an unofficial per-ticker Yahoo client with no published batch/rate guarantee; unbounded threads, missing mappings, current-list relabelling, partial publication, or raw/adjusted mixing would make the result unsafe or misleading.
4. **Smallest alternative:** two sequential 50-ticker yfinance calls with eight internal workers, one fixed-cadence bounded curl-cffi session, existing adjusted settings, existing immutable cohort retention, and a read-time complete-union check; no provider framework, queue, scheduler, database, adaptive rate controller, or cross-cohort transaction subsystem.
5. **Decision:** **accepted** as the Plan 33 implementation contract after fresh functional/domain/temporal **APPROVE** and security/privacy/provenance **PASS** review; runtime delivery prerequisite [#155](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/155) is delivered by its governing merge, while [#156](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/156) and its governing pull request own the separate bounded implementation lifecycle.

## Source verification and decision

### Authorization and enablement

The operator command is disabled unless its exact versioned configuration
sets `enabled=true` for
`efficient-current-nifty100-adjusted-capture@v1`. Every invocation also
requires the nonpersistent CLI acknowledgement
`--ack-owner-private-yfinance-research`. The acknowledgement records only that
the repository owner invoked this owner-private research capability with the
unofficial, revised/non-PIT, personal-use, and terms limitations understood.
It is not Yahoo permission, endorsement, exchange authority, or redistribution
authorization.

Disabled configuration returns `DISABLED/ADAPTER_DISABLED`. A missing, false,
wrongly typed, duplicated, or malformed acknowledgement returns
`AUTHORIZATION_DENIED/OWNER_PRIVATE_USE_NOT_ACKNOWLEDGED`. Both return a
sanitized bounded result after a standard-library-only duplicate-key and
enablement preflight but before any executable third-party import, constituent
retrieval, yfinance import/cache initialization, provider/session work, store
lookup/write, or dependency logging. Clean-process no-effect invocation tests
are the authority evidence; no ambient
authorization subsystem is added.

### Current selection inputs

The current selection sources are the pair of official NSE Indices constituent
CSV endpoints:

- `https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv`; and
- `https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv`.

The official
`https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv`
artifact is acquired in the same bounded source step as a union-consistency
witness. It is not a second membership authority or a timestamp.

Each retrieval reads at most 262,144 response-body bytes and retains the exact
admitted bytes, URL, response receipt, retrieval time, content SHA-256,
parser/schema identity, and resulting canonical rows. A larger response is
stopped at the bounded reader before CSV parsing or retention.
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

Pinned `multitasking==0.0.13` creates its default CPU-sized pool when yfinance's threaded function is decorated, and `set_max_threads()` affects only new pools. Therefore `threads=8` alone does not impose an eight-worker ceiling. Plan 33 requires a fresh single-purpose operator process to import `multitasking`, call `createPool(name="plan33_yfinance_8", threads=8, engine="thread")`, assert the active pool name/engine/count, construct the bounded session, and only then import yfinance. The same assertions run immediately before each cohort call. An earlier yfinance import, another active pool, concurrent Plan 33 invocation in the same process, default/`True` threads, debug logging, or any pool value other than eight is a configuration failure before provider work.

Before the enabled core import executes a provider dependency, the CLI requires
a fresh process with no preloaded admitted dependency or transitive child
module. It admits the exact locked yfinance runtime closure: `yfinance==1.6.0`,
`beautifulsoup4==4.15.0`, `certifi==2026.7.22`, `cffi==2.1.1`,
`charset-normalizer==3.5.1`, `curl-cffi==0.16.1`, `idna==3.19`,
`lxml==6.1.2`, `multitasking==0.0.13`, `numpy==2.4.6`,
`pandas==3.0.5`, `peewee==4.3.0`, `platformdirs==4.11.3`,
`protobuf==7.36.0`, `pycparser==3.0`, `python-dateutil==2.9.0.post0`,
`pytz==2026.3.post1`, `requests==2.34.2`, `six==1.17.0`,
`soupsieve==2.9.2`, `typing-extensions==4.16.0`, `urllib3==2.7.0`,
and `websockets==17.0.1` distributions beneath the running interpreter's
resolved `purelib`/`platlib`. Exact aggregates are admitted only for CPython
3.11 x86-64 on Darwin or Linux with the bound SOABI; every other runtime fails
closed. The Linux identity and native-companion path are exercised in the
locked Debian/Ubuntu-compatible CPython 3.11 environment used by hosted CI.
The Requests family is admitted because pinned yfinance imports it for its
dual-backend session-type compatibility surface; it is not an admitted
provider transport.

Import admission is positive rather than an enumeration of known optional
probes. The public console bootstrap first replaces itself with the same
interpreter under `-I -S`, restores only the exact package and environment
site-package roots needed by the installed runtime, and immediately imports
the CLI. The enabled preload guard refuses to run without both isolated and
no-site flags. Ambient `sitecustomize`, user-site, `PYTHONPATH`, and parent
process module objects therefore cannot seed the retained initialization set.

Only built-in and standard-library prefixes, the project prefix, the
descriptor-admitted dependency prefixes, and the exact path-import prefixes
required by this capture boundary may resolve. Every other top-level prefix is
rejected before a later finder can execute it. An initialized built-in,
frozen, standard-library, project, or interpreter-bootstrap module is accepted
only when its exact standard loader, canonical specification name and origin,
module file, and package search path match the module. Package search paths
must equal the directory implied by the module origin, not merely a sibling
directory beneath the same trusted root. Only the explicit interpreter aliases
for `os.path` and importlib bootstrap modules may use a distinct specification
name.

The accepted module must also be the exact non-null object retained when the
isolated CLI initialization completed; matching metadata cannot substitute a
later module object or cross-name alias. Root discovery must not add any module
after that snapshot, and request-authority support is loaded during the same
isolated initialization rather than through a later open-ended retention
window. The boundary then replaces ambient meta-path finders and path hooks
with the standard built-in, frozen, source, and native-extension machinery,
clears ambient path-finder cache entries, and restores the prior import state
only after the verified lifetime ends. Known optional probes remain explicitly
denied as defense in depth.

Every distribution-owned package file is bound into an allowlisted aggregate,
and every Python module executes from descriptor-read admitted bytes. Dependency
admission allows at most 67,108,864 bytes per file and 67,108,864 bytes across
one package tree. Installed Python source may be hard-linked by the package
installer; link count is not treated as authenticity. Admission still requires
the pathname and held descriptor to retain the same complete file identity
before and after the bounded read, and the descriptor-read bytes must contribute
to an allowlisted distribution aggregate.
Each native extension and package-owned native companion is held by a
shared-locked descriptor whose full metadata and content identity match the
admitted distribution object. The extension loader receives only the verified
`/dev/fd` or `/proc/self/fd` alias to that held object, never a second lookup of
its mutable package pathname. Required companion libraries are loaded from the
same descriptor aliases with global native visibility and retained for the
verified import lifetime. This includes cffi's top-level `_cffi_backend` native
object, curl-cffi's package extensions and companions, and NumPy/Pandas native
extensions and companion libraries. Loaded Python file/spec origins bind to
their admitted absolute paths, while a loaded native file/spec origin binds to
that verified descriptor alias and remains live through the operation. The
cffi-generated `curl_cffi._wrapper.lib` object has no file/spec; it is admitted
only when it is the exact `lib` object exported by the separately
descriptor-bound `curl_cffi._wrapper` extension.
The admitted certifi CA bundle is descriptor-bound before the enabled core
import, so dependency import cannot reopen that resource through the custom
source loader.

The CLI proves that the exported and inherited `Session` class is the admitted
`curl_cffi.requests.session` class. The core retains the exact admitted
`curl_cffi.requests` module object used to obtain that class.
`YF_DISABLE_CURL_CFFI` is rejected as ambient transport authority, and provider
preparation requires the current `sys.modules` entry plus pinned yfinance's
active `_http` backend and exported `requests` object to remain that same
non-null admitted object before a provider effect. Ambient import paths are
removed for the duration of the operation. A package, coherent
package-plus-metadata, preloaded transitive or optional module, ambient optional
module, native pathname substitution, missing/replaced backend object, or
Requests transport fallback is not executed.

The CLI revalidates every retained native descriptor, every loaded dependency
origin, the complete yfinance distribution and loaded-module set, and the exact
curl-cffi backend immediately before each provider effect, after each adapter
response, and before final success.

The official-source opener installs no proxy handler and uses a fresh
client-verifying TLS context populated only from the same admitted immutable CA
bytes. The provider session copies those exact bytes into each thread-local
native curl handle through `CURLOPT_CAINFO_BLOB`, explicitly restores peer and
hostname verification after curl-cffi option preparation, and accepts only
`GET` requests to the exact `fc.yahoo.com`, `query1.finance.yahoo.com`, and
`query2.finance.yahoo.com` hosts. Consent hosts, non-`GET` methods, request-level
transport overrides, ambient proxy variables, and mutable system trust roots
are not authorities.

The supplied session is one `curl_cffi.requests.Session(impersonate="chrome", retry=0)` subtype with a shared locked transport ledger and a non-overtakable call-start boundary. A worker holds that boundary from ledger admission through entry into the superclass HTTP call and releases it only at the first response-body callback or terminal return/failure. Thus concurrent scheduling cannot reorder admissions or cluster actual HTTP-call starts. It admits only:


- a minimum 125-millisecond monotonic-clock interval between actual HTTP-call
  starts across all workers;
- at most 256 HTTP starts per 50-member cohort;
- at most 16,384 UTF-8 bytes for method plus URL plus encoded query target;
- at most 2,097,152 response-body bytes for one HTTP response; and
- at most 134,217,728 aggregate response-body bytes per cohort.

The response-body callback stops the transfer at the first limit violation
before yfinance JSON/frame decoding. A resource-limit violation remains sticky
for all later starts and active-response body admissions. A cohort reset is
rejected while any response remains active; only after every response is closed
may the next explicit cohort reset clear the violation. The session intercepts
the first observed HTTP 429, records `PROVIDER_RATE_LIMITED`, and raises before
yfinance's alternate-cookie request.
Pinned yfinance may issue exactly one dependency-internal alternate-cookie
request after a non-429 HTTP status `>=400`; that request is accepted as part of
the single adapter invocation and is subject to the same start, cadence, target,
and body bounds. There is no operator retry, fallback, second provider, or
curl-cffi retry. The two cohort calls run sequentially. The exact adjusted call is:

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
    session=bounded_yahoo_session,
    multi_level_index=True,
)
```

The canonical caller request and sanitized result are each at most 262,144
bytes. Provider/session counters are sanitized aggregates only. Dependency
debug logging is rejected; dependency stdout/stderr is not a public result and
must not expose ticker symbols, URLs, cookies, payloads, or paths.

Production does not derive yfinance symbols by appending `.NS`. Every member must arrive with canonical ISIN, NSE exchange, effective symbol interval, and a versioned cutoff-valid yfinance mapping. The benchmark-only suffix composition tested throughput and is not mapping authority.

### Rejected Upstox substitution

Upstox V3 historical candles remain the primary raw/current alternative, but its documented path accepts one `instrument_key` per request. Its standard-API limits are 50 requests/second, 500/minute, and 2,000/30 minutes. A bounded concurrent Upstox design could avoid sequential latency, but it would produce the separate Upstox raw basis, require authenticated per-instrument requests, and would not be a drop-in replacement for this yfinance adjusted capture. Provider substitution or raw/adjusted mixing is rejected for Plan 33.

## Measured benchmark

The nonpublishing benchmark history and every correction are recorded in
[Issue #154](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/154).
The first nominal `threads=8` run used `multitasking`'s already-created
CPU-sized pool, so its 5.072-second observation is superseded for the exact
worker claim. The fresh named-pool correction completed in 5.992 seconds, but
independent review correctly found that it did not exercise deterministic
request cadence or byte bounds. It remains only an unthrottled exact-pool
baseline.

The accepted execution-path benchmark was separately
[predeclared](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/154#issuecomment-5480774224)
and [recorded](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/154#issuecomment-5480803457).
It used:

- a fresh process with one named eight-thread pool before yfinance import;
- pinned yfinance `1.6.0`, `multitasking==0.0.13`, and a supplied curl-cffi
  session with built-in retry zero;
- the exact eight-starts/second, 256-start/cohort, 16-KiB request-target,
  2-MiB response-body, and 128-MiB cohort-body bounds frozen above;
- first-observed-429 stop and bounded non-429 alternate-cookie behaviour;
- two sequential 50-member cohorts;
- the retained official Nifty 50 snapshot and retained official Nifty 100
  artifact, whose exact disjoint set difference produced 50 plus 50 benchmark
  members;
- the retained composed NSE schedule for 21 completed sessions from
  `2026-08-03` through `2026-08-31`;
- an isolated temporary yfinance cache that was removed after the run; and
- in-memory normalization with no retained bars, private-store mutation,
  public member payload, operator retry, or fallback.

A malformed preflight that supplied schedule objects instead of date strings
and a later superseded session experiment are excluded from acceptance; neither
retained a valid frame or mutated the private root. The accepted bounded result
was:

| Cohort | Complete | Failed | Sessions | HTTP starts | Response body | Time | Timezone |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Nifty 50 | 50/50 | 0 | 21 | 102 | 206,371 B | 13.381 s | `Asia/Kolkata` |
| Nifty Next 50 | 50/50 | 0 | 21 | 100 | 200,760 B | 12.561 s | `Asia/Kolkata` |
| **Complete union** | **100/100** | **0** | **21** | **202** | **407,131 B** | **25.942 s total** | `Asia/Kolkata` |

This is one source-behaviour observation on the reference workstation and
network, not a provider SLA or guaranteed future speed. It proves the selected
fixed-cadence, exact-eight, bounded transport path for this completed window.

The implementation qualification budget is:

- no more than eight in-flight yfinance ticker tasks;
- at least 125 milliseconds between HTTP starts and at most 256 starts per cohort;
- the exact request/source/provider/result byte bounds above;
- one adapter invocation per unresolved cohort and no operator retry;
- at most 30 seconds per valid 50-member cohort in the focused reference benchmark;
- at most 60 seconds total for the two provider/normalization calls in that benchmark; and
- at most 180 seconds for the complete operator command including input admission, validation, immutable writes/reuse checks, and sanitized output.

A candidate that misses these qualification budgets is not accepted. The
10-second yfinance request timeout, cadence, byte bounds, and finite
worker/request counts bound ordinary failure behaviour, but Plan 33 does not
claim a process-level hard kill against a defective dependency. Process
isolation and forced termination remain a later resilience improvement.

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

### Separately tracked implementation slices
The first implementation Issue may deliver only one repeatable operator-triggered completed-session capture:

1. enforce the exact enabled configuration and per-invocation owner-private
   acknowledgement before every effect;
2. admit a canonical caller request of at most 262,144 bytes;
3. acquire through bounded readers and retain the two exact official
   constituent artifacts plus the exact Nifty 100 consistency witness;
4. validate exact cardinality, schema, disjointness, witness equality, fixed
   cohort order, and canonical row order;
5. admit the two exact 50-member canonical cohorts and their yfinance mappings;
6. use one admitted composed schedule and completed decision session;
7. create and verify the named eight-permit pool and bounded transport before
   importing yfinance;
8. resolve valid existing revisions for both cohorts;
9. acquire, validate, and retain/reuse every unresolved cohort in fixed
   `NIFTY_50`, `NIFTY_NEXT_50` order, continuing after provider/frame failure
   but stopping new effects after a retention failure or immutable-evidence
   conflict;
10. return complete Nifty 100 only when both revisions bind the same selection,
    schedule, decision session, source profile, configuration, and compatible
    retrieval boundary; and
11. emit at most 262,144 sanitized bytes containing the ordered cohort
    states/reasons, aggregate counts/identities/timing, and no member symbols,
    ISINs, bars, provider payloads, URLs, paths, cookies, cache content, or
    dependency logs.

The implementation reuses the existing yfinance/curl-cffi source boundary and
immutable capture rules. Each Plan 33 receipt key binds the selection identity,
low-level request identity, cohort, and high-level configuration so a valid
official-source transition preserves both old and new receipts. A newly captured
low-level revision publishes one immutable receipt binding its selection,
request, schedule, revision, source, and retrieval time. An exact reused
low-level revision may recover a missing receipt only after every bound identity
and the immutable revision are revalidated; conflicting bytes fail closed before
provider work. Every successful reused or captured cohort must then yield
exactly one detached, exact-identity binding snapshot that remains live through
cleanup and finalization. A missing, renamed, or replaced successful binding is
`EVIDENCE_CONFLICT`; completion cannot omit its snapshot. The changed pool,
supplied session, cadence, and byte-bound configuration is versioned rather than
weakening or silently mutating the delivered `threads=False` contract.

Before reading the private request or performing any source, cache, provider,
or store effect, the CLI rejects the request file, schedule root, or either
cohort storage root when it equals or is below the reserved cache boundary.
The reusable core independently repeats the evidence-root separation check.
The shared private-request reader returns the admitted bytes and the exact
device/inode/metadata identity from the same held descriptor after final name
and parent revalidation. The CLI carries that identity through the enabled
handoff and rejects a later name substitution; it does not restat the pathname
to derive a different identity.

The provider cache uses one fixed owner-private directory beneath the
descriptor-admitted selection root. Every admitted invocation clears private
content through held file and directory descriptors before resolving cohort
outcomes, including an all-`REUSED` invocation that never imports yfinance.
Request and existing selection, schedule, and cohort-store device/inode
identities are captured before the first source effect, passed into cache
admission before provider import, and remain protected during recursive
cleanup. The cache directory's own identity is also rejected if it aliases a
protected object.
Before provider use, the pinned yfinance timezone, cookie, and ISIN cache
managers are bound to their in-memory no-op cache implementations and all three
SQLite managers must remain unopened. If an unexpected database was opened,
session shutdown must close it and report it closed before any file is
content-cleared. Failure releases the cache authority without truncating its
live database files and returns configuration insufficiency.

Cleanup never unlinks or removes an entry through a mutable pathname. Regular
files must be single-linked, are opened without following symlinks, are
identity-revalidated from the held descriptor, and are truncated and synced
through that descriptor. Directories are recursively content-cleared through
held descriptors and retained. Symlinks, special files, hard-linked regular
files, a changed name identity, or any protected identity fail closed without
destructive cleanup. Every close revalidates the held and named cache
identities, the content-cleared state, and the protected names before success.
Zero-length regular files and content-cleared directories may remain for the
next invocation; no cookie, provider response, or other cache payload bytes are
retained. This avoids a stat-to-delete race because POSIX pathname removal
cannot atomically bind the removed object to the previously checked identity.

The governing [Issue #155](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/155)
merge ports the exact reviewed actionable Plan 30 runtime from source candidate
`54f8b7c8246d6bd302ca729c01686f635c9809c7` onto current main. Issue #147
subsequently completed its separate historical lane through PR #166.
[Issue #156](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/156)
owns only this bounded Plan 33 implementation. It must not copy unreviewed
quarantine bytes, consume #147's retained historical evidence as current Plan 33
input, or imply a qualification state not established by #147's exact evidence.

### Later improvements

The following do not block Issue #154 or the first implementation slice:

- an in-process or OS scheduler, laptop wake guarantee, remote runner, alerting, queue, daemon, or hosted service;
- process isolation, hard termination, generalized retry/backoff, circuit breaker, adaptive rate control, or telemetry;
- a provider framework, alternative adjusted provider, Upstox raw substitution, or dual-source reconciliation;
- cross-cohort atomic transaction, generalized multi-cohort store, archive replay, durable orchestration state, or recovery engine;
- historical constituent reconstruction, dated release ingestion, effective-notice composition, backfill, or pre-retrieval point-in-time membership claims;
- more than 100 instruments, arbitrary index composition, ETF/F&O/crypto/multi-asset support, intraday capture, or tick data;
- public payload/API/UI/MCP delivery, redistribution, signal, score, recommendation, order, or financial-adviser behaviour.

Adding any later item triggers the scope-expansion circuit breaker.

## Closed outcomes and composition

Shared admission returns exactly one of:

- `DISABLED/ADAPTER_DISABLED`;
- `AUTHORIZATION_DENIED/OWNER_PRIVATE_USE_NOT_ACKNOWLEDGED`;
- `MALFORMED_INPUT` for invalid caller-owned fields or bounds;
- `UNSUPPORTED_CAPABILITY` for an unsupported canonical instrument or missing
  mapping capability; or
- `INSUFFICIENT_EVIDENCE` with exactly one of
  `CONSTITUENT_SOURCE_INVALID`, `CONSTITUENT_SOURCE_CONFLICT`,
  `MAPPING_EVIDENCE_INVALID`, `SCHEDULE_INVALID`, `EVIDENCE_CONFLICT`, or
  `RETENTION_FAILED`.

After shared admission, each cohort returns exactly one ordered outcome:

- `REUSED`: the exact admitted request already resolves to a valid immutable revision;
- `INSERTED`: one new valid immutable revision was committed;
- `UNSUPPORTED_CAPABILITY`;
- `NOT_ATTEMPTED/BLOCKED_BY_PRIOR_RETENTION_FAILURE`; or
- `INSUFFICIENT_EVIDENCE` with exactly one of `CONFIGURATION_INVALID`,
  `RESOURCE_LIMIT_EXCEEDED`, `PROVIDER_RATE_LIMITED`, `PROVIDER_ERROR`,
  `PROVIDER_FRAME_INCOMPLETE`, `PROVIDER_BASIS_INVALID`, or
  `RETENTION_FAILED`.

Under [Issue #176](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/176),
each serialized cohort also carries nullable `provider_frame_reason`. For
`INSUFFICIENT_EVIDENCE/PROVIDER_FRAME_INCOMPLETE`, it preserves only an exact
plain-string member of this closed lower-level reason set:

- `FRAME_COVERAGE_INCOMPLETE`, `FRAME_SCHEMA_INVALID`, `FRAME_VALUE_INVALID`;
- `PROVIDER_EMPTY`;
- `RETRIEVED_AFTER_DECISION_CUTOFF`, `RETRIEVED_BEFORE_OFFICIAL_CLOSE`; or
- `CORRECTION_CONTENT_UNCHANGED`.

An unknown, missing, non-string, or string-subclass detail becomes the fixed
`UNCLASSIFIED_FRAME_REJECTION` marker. Every other outcome carries null,
including resource/rate-limit failures that take precedence over a frame
failure and successful/reused outcomes. Public serialization independently
enforces this rule; it never echoes arbitrary lower-level detail.

This additive diagnostic does not change the coarse outcome, request or
immutable revision representation, admission, continuation, retry, resource,
or output-byte rules. It identifies the existing rejection category, not an
offending member, private value, or proven root cause. No rejected frame or
dependency log is published or retained by this extension. A new diagnostic
must not be retroactively attributed to an earlier capture that lacked it.

All diagnostic fields require exact plain-string coarse `code` and `reason`;
subclass-defined equality never decides their eligibility.

The owner-approved Issue #176 continuation adds nullable `provider_value_check`
only when the outcome is `INSUFFICIENT_EVIDENCE/PROVIDER_FRAME_INCOMPLETE`
and `provider_frame_reason` is the exact plain string `FRAME_VALUE_INVALID`.
Its closed vocabulary is:

- each of `OPEN`, `HIGH`, `LOW`, and `CLOSE` followed by `_NOT_NUMERIC`,
  `_NOT_FINITE`, or `_NOT_POSITIVE`;
- `VOLUME_NOT_NUMERIC`, `VOLUME_NOT_FINITE`, `VOLUME_NEGATIVE`, or
  `VOLUME_NONINTEGRAL`; and
- `OHLC_ORDER_INVALID`.

Missing, unclassified, forged, non-string, or string-subclass detail becomes
`UNCLASSIFIED_VALUE_REJECTION` in that context; every other context emits null.
Public serialization independently checks both the context and the finite
plain-string value. A field label identifies a failed check, not a stock,
session coordinate, observed price, or proven provider/adapter root cause.

Value-check diagnosis uses the same invocation's already-normalized response after
the authoritative low-level call reports `FRAME_VALUE_INVALID`. It scans within
the admitted request's bounds in canonical member/session order. In the first
rejected row, precedence is price-number conversion in open/high/low/close
order, volume-number/integrality checks, price positivity in that order, then
OHLC ordering. It reuses the existing low-level numeric validators. Its scalar
comparisons explain an already-rejected bar; they never decide data acceptance.
An unavailable or nonmatching observation remains unclassified.

The provider may hold one transient reference to its already-created response,
without copying it, during the per-cohort call. A `finally` handoff clears that
provider-owned reference on every call exit and completes any bounded failure
diagnosis before the next cohort. No rejected frame, value, identifier, session
coordinate, private row count, path, URL, exception text, or dependency log is
archived or emitted. Successful, reused, transport-failed, and exceptional
paths cannot inherit a previous frame's diagnostic. Low-level source, request
identities, writer compatibility, immutable revisions, effect precedence, and
no-retry/no-fallback rules remain unchanged.

The separately owner-approved source-stage continuation adds nullable
`provider_value_origin` only when all four plain-string contexts above resolve
to `INSUFFICIENT_EVIDENCE/PROVIDER_FRAME_INCOMPLETE/FRAME_VALUE_INVALID/OPEN_NOT_FINITE`.
It correlates source evidence with the same canonical first rejected
member/session, never with an unrelated bad value elsewhere in the cohort.
Its closed source vocabulary is:

- `SOURCE_OPEN_MISSING_OR_NONFINITE`: the corresponding raw opening value is
  missing or non-finite under the pinned provider's float conversion;
- `SOURCE_ADJUSTMENT_INPUT_INVALID`: the corresponding close or adjusted close
  is non-finite, or close is a zero divisor;
- `SOURCE_ADJUSTMENT_RESULT_NONFINITE`: finite inputs produce a non-finite
  opening under the pinned `open * (adjusted_close / close)` calculation;
- `SOURCE_EXPECTED_SESSION_MISSING`: the matching chart quote series lacks the
  expected session, regardless of whether a later event merge or batch
  alignment creates its empty price row; and
- `SOURCE_ADJUSTED_OPEN_FINITE`: the corresponding source projection is finite.
  This alone does not prove a downstream defect or that other prices are valid.

Missing, malformed, unsupported, conflicting, mismatched, or forged source
observations produce `UNCLASSIFIED_SOURCE_ORIGIN` in that exact eligible
context; all other contexts emit null. Serialization independently rechecks
every context's exact type and the closed origin vocabulary.

The source observer consumes only already-admitted HTTP 200 response bytes
from the existing query1/query2 Yahoo daily chart path. It matches the exact
requested provider symbol, interval, start/end epochs, response symbol, and
`Asia/Kolkata` timezone. It rejects duplicate JSON keys and session dates,
ambiguous query parameters, more than 32 query fields, more than the expected
session count plus one source timestamp, and inconsistent array lengths.
Source timestamps at local minute zero in hours 22 or 23 make the projection
unclassified: the pinned provider shifts those quotes into the next session.
The observer must not borrow a neighboring raw-date row's category after that
correction, and does not change or reproduce the provider's date repair.
Unsupported scalar shapes or numeric strings longer than 64 characters remain
unclassified. Absent `adjclose` follows the pinned parser's use of `close`
solely for this diagnostic calculation; no capture input or price is replaced.

Existing 2 MiB response and 128 MiB aggregate transport limits still apply.
Only categorical projections for the current request's at-most-50 members and
at-most-366 sessions may survive the response inspection. Raw decoded values
are not retained by the observer. Conflicting matching responses remain
unclassified rather than choosing a convenient response. A transport request
holds its entry-time observer; completion cannot attach evidence to a later
invocation. The provider detaches it in `finally`, and the same-invocation
frame/observation handoff closes and clears both before diagnosis or the next
cohort. Late observations after closure are ignored.

This continuation adds no provider effect, retry, data repair, source switch,
logging/archive mechanism, or change to immutable evidence admission. A live
diagnostic invocation still requires its own explicit owner authority and
current-byte verification/review. Synthetic source projections must not be
attributed to the four earlier capture attempts.

The higher-level outcome is:

- `COMPLETE_CURRENT_NIFTY100_CAPTURE` only when both ordered cohort outcomes
  resolve to valid compatible revisions; or
- `INCOMPLETE_CURRENT_NIFTY100_CAPTURE` with an exact two-row
  `(NIFTY_50, NIFTY_NEXT_50)` outcome tuple. Both failures are retained when
  both cohorts fail; a successful row carries its valid revision reference.
  `union_reason` is absent when at least one cohort failed or was not attempted
  and is exactly `UNION_INCOMPATIBLE` when both cohort revisions are
  individually valid but cannot be composed.

`REUSED` and `INSERTED` are equally valid revision references. Member facts
are never dropped to turn 99 members into success. A valid independently
retained cohort is not deleted when the other cohort fails, but it is labelled
only by its own cohort identity and cannot authorize the union claim.

## Adversarial acceptance matrix

| Case | Observable result | Prohibited effects | Evidence method |
| --- | --- | --- | --- |
| Enabled exact configuration and per-invocation acknowledgement; two exact disjoint 50-member lists; exact 100-member witness; mappings; schedule; bounded session; complete frames | Two valid revision references; complete union; sanitized bounded output | Raw/member publication; fallback | Focused positive plus one completed-session smoke |
| Disabled configuration or missing/false/wrong/duplicate acknowledgement | `DISABLED/ADAPTER_DISABLED` or `AUTHORIZATION_DENIED/OWNER_PRIVATE_USE_NOT_ACKNOWLEDGED` before executable third-party import and all source/cache/provider/store/log effects | Ambient acknowledgement; dependency import; network/cache/store effect | CLI parser and clean-process shadow-dependency no-effect tests |
| Caller request is 262,145 bytes or has malformed fields/bounds | `MALFORMED_INPUT` before source/provider/store effects | Source fetch; provider call; publication | 262,144 and limit-plus-one admission tests |
| Any constituent response body is 262,145 bytes; fetched list/witness has 49/51/101 rows, duplicate, overlap, non-`EQ`, blank identity, or wrong header | `INSUFFICIENT_EVIDENCE/CONSTITUENT_SOURCE_INVALID` before yfinance/store effects | Full-body allocation/parse; member repair; substitution | Bounded-reader and source composition tests |
| Pair union and official witness disagree, identity is substituted, or bytes change during paired admission | `INSUFFICIENT_EVIDENCE/CONSTITUENT_SOURCE_CONFLICT` before yfinance/store effects | Either cohort provider call or publication | Conflict/substitution test |
| Official source bytes validly change on the next run | New selection/request identity; old selection and revisions remain immutable | Mutation, append under old identity, or historical relabelling | Membership-transition test |
| Current CSV lacks publisher-effective time | Current-at-retrieval label only | Historical/pre-retrieval membership claim | Serialization/nonclaim test |
| Mapping capability is absent | `UNSUPPORTED_CAPABILITY` before provider call | `.NS` inference; wrong ticker call | Missing-capability test |
| Mapping evidence is stale, conflicting, or substituted | `INSUFFICIENT_EVIDENCE/MAPPING_EVIDENCE_INVALID` before provider call | Mapping repair or wrong ticker call | Mapping interval/identity tests |
| Invalid schedule, incomplete decision session, wrong close/cutoff, selection retrieved after the decision cutoff, or schedule identity substitution | `INSUFFICIENT_EVIDENCE/SCHEDULE_INVALID` before provider call | Partial-session capture; inferred calendar; untyped temporal failure | Schedule/temporal tests |
| Parent process preloads a metadata-cloned standard module, `sitecustomize`, user-site, or `PYTHONPATH` shadow before invoking the public command | Public bootstrap replaces the process with immediate `-I -S` initialization; enabled preload admission proceeds only there | Parent module execution inside the capture runtime; inherited module object trust; later open-ended retention | Parent pre-import marker test plus isolated positive dependency import |
| Pool/session was not created before yfinance import; any admitted, optional, or otherwise unapproved external dependency module is preloaded; an unapproved import is requested; ambient meta-path/path-hook/cache machinery survives inside the verified lifetime; the admitted distribution, any loaded Python origin, native descriptor origin/content/identity, exact exported/inherited `Session` class, retained active backend module object, pool metadata, retry value, cadence, bounds, worker value, or debug/concurrency state differs | `INSUFFICIENT_EVIDENCE/CONFIGURATION_INVALID` before provider work | `PYTHONPATH` package or coherent metadata substitution; preloaded transitive or optional-module substitution; ambient optional-code execution; native pathname reopen/substitution; missing/replaced backend accepted through `None` identity; CPU-derived, unbounded, silently sequential, or raced execution | Clean-process package/metadata/preloaded-child substitution, hostile unapproved meta-path/site-root/path-hook/cache, missing/replaced backend, and import-order/pool/session/configuration/native-descriptor tests |
| Concurrent actual HTTP-call starts are less than 125 milliseconds apart, the 257th cohort start is requested, the request target is 16,385 bytes, one response body reaches 2,097,153 bytes, or aggregate cohort response bodies reach 134,217,729 bytes | Sticky `INSUFFICIENT_EVIDENCE/RESOURCE_LIMIT_EXCEEDED`; no later start, active-response body admission, or cohort reset until every active response closes; callback stops before frame decode; no partial publish | Admission overtake; clustered real calls; limit bypass after first violation; reset with active response; full oversized decode; retry | Concurrent superclass-entry cadence plus clock-controlled bound, limit-plus-one, active-reset, and post-violation tests |
| First transport response is HTTP 429 | Session stops it before yfinance alternate-cookie handling; `INSUFFICIENT_EVIDENCE/PROVIDER_RATE_LIMITED`; second unresolved cohort still follows precedence | Dependency/operator retry; fallback; partial publish | Session interception/rate-limit test |
| Non-429 HTTP `>=400` occurs | At most one pinned yfinance alternate-cookie request, within every same bound; complete valid frame may succeed, otherwise exact provider/frame insufficiency | Unbounded or operator retry | Transport-ledger tests |
| Provider raises an ordinary non-rate exception or timeout | `INSUFFICIENT_EVIDENCE/PROVIDER_ERROR` for that cohort | Operator retry; fallback; partial cohort publish | Adapter failure tests |
| Empty/unexpected-schema frame, missing/duplicated session or ticker, NaN/non-finite/non-positive price, negative/non-integral volume, or wrong timezone | `INSUFFICIENT_EVIDENCE/PROVIDER_FRAME_INCOMPLETE` for that cohort | Invented 429; member/session dropping; value repair | Frame matrix tests |
| Distinct real schema, coverage, value, or retrieval-time frame failures | Existing incomplete cohort outcome plus its allowlisted `provider_frame_reason`; second cohort still follows existing precedence | New provider call, partial publication, changed failure classification | Real normalized-frame rejection through outcome composition and public serialization |
| Unknown/forged private diagnostic, non-string or string-subclass value, or diagnostic attached to a non-frame/success outcome | Fixed `UNCLASSIFIED_FRAME_REJECTION` only for frame failure; null otherwise | Raw detail echo, diagnostic overriding resource/rate-limit failure, unbounded payload | Serialization redaction and combined-failure precedence regressions |
| A rejected row has competing price-conversion, volume, positivity, or OHLC-order faults | One allowlisted `provider_value_check` in the frozen order, attached only to exact `FRAME_VALUE_INVALID` | Changed admission, invented value diagnosis for another frame reason, values or member/session coordinates | Real normalizer rejection through both ordered cohort outcomes; competing-failure regressions |
| A value diagnostic or its frame context is missing, unknown, non-string, or a masquerading string subclass | `UNCLASSIFIED_VALUE_REJECTION` only in the exact eligible context; null otherwise | Private canary echo; hash/equality masquerade; diagnostic on rate-limited or reused output | Public serializer context/forgery regressions |
| A rejected or exceptional first cohort is followed by another cohort; a valid zero-volume/flat-price capture succeeds | Transient response released before the next cohort and session close; later diagnosis comes only from its own response; valid immutable revisions read back with null diagnostic | Raw response retention; inherited diagnostic; rejection of valid zero volume or equality bounds | Weak-reference lifetime checks, exceptional-exit regression, and real low-level capture/readback |
| Complete yfinance-adjusted window crosses a provider-reported corporate action | Capture remains one adjusted revision; volume remains source-reported unadjusted; limitation retained | Upstox/raw substitution; local adjustment inference | Corporate-action basis test |
| A later authorized request observes revised adjusted bytes, including when its admitted parent was written by an explicitly compatible historical runtime | New immutable revision/lineage; old revision and writer identity unchanged; writer upgrade alone is not changed provider content | Overwrite, historical-writer rejection, spurious correction, or relabelling old known-at | Revision/correction and compatible-writer lineage tests |
| First cohort has provider/frame failure; second is unresolved | Second is still attempted; ordered tuple carries both exact rows | Nondeterministic short-circuit | Combined-failure precedence test |
| First cohort retention fails; second is unresolved | First is `RETENTION_FAILED`; second is `NOT_ATTEMPTED/BLOCKED_BY_PRIOR_RETENTION_FAILURE`; no later provider/store effect | Use of potentially unsafe store; missing second row | Retention-stop test |
| First cohort retention fails; second was already validly reused | Failed first row plus valid reused second row; no new effect | Deletion or relabelling of reused revision | Mixed reuse/retention test |
| Interruption or write failure during second cohort retention | `INSUFFICIENT_EVIDENCE/RETENTION_FAILED` for second; existing rollback/recovery semantics; ordered incomplete union | Partial revision admission; overwrite | Existing atomic-store interruption tests plus orchestration test |
| The canonical `selections` or `plan33_bindings` child name is replaced after descriptor admission during a missing read or immutable publish, or a successful cohort binding disappears before detached snapshot/finalization | `INSUFFICIENT_EVIDENCE/EVIDENCE_CONFLICT`; the replacement remains untouched and no success is returned | Publication into, deletion of, trust in the substituted sibling, or completion without exactly one live successful-cohort binding snapshot | Descriptor/name identity race and successful-binding-disappearance tests |
| Both cohorts are validly `REUSED` while the fixed cache contains residue from an earlier cleanup failure | Cache contents are descriptor-cleared without importing yfinance or calling the provider; cleanup failure makes both rows `CONFIGURATION_INVALID` | Retained cookie/response data; provider work on an all-reuse invocation | All-reuse cache-residue regression |
| Request, schedule, or cohort storage root equals/descends from the fixed provider-cache boundary; the cache directory aliases a protected identity; or a validated protected object is moved there before/during cleanup or provider import failure | Static overlap is `MALFORMED_INPUT`/`request_invalid`; later aliasing is `CONFIGURATION_INVALID`; protected identity is not deleted and no complete result is returned | Deletion of retained evidence; publication followed by cache deletion; dangling success | Core/CLI static-overlap, own-cache-alias, import-failure movement, root-before-source snapshot, descriptor-bound content-clear, and final-delete-substitution regressions |
| Exact retry | Same revision identity and `REUSED`; no provider call/write | Duplicate revision; changed known-at | Retry test |
| The request pathname is replaced after descriptor admission, or either request identity points to invalid/conflicting bytes | The descriptor-bound identity follows the admitted bytes; later name substitution is `CONFIGURATION_INVALID`; conflicting domain bytes are `INSUFFICIENT_EVIDENCE/EVIDENCE_CONFLICT`; no new provider/store effect | Identity handoff from replacement bytes; repair, overwrite, or masking provider call | Request-reader handoff-swap and conflict/substitution tests |
| Raw Upstox or another provider appears in either cohort | `INSUFFICIENT_EVIDENCE/PROVIDER_BASIS_INVALID` | Raw/adjusted mixing; silent fallback | Provider/price-basis substitution tests |
| One cohort uses another selection, schedule, decision session, configuration, source profile, or incompatible retrieval boundary | Both cohort rows remain exact; `INCOMPLETE_CURRENT_NIFTY100_CAPTURE/UNION_INCOMPATIBLE` | Cross-context composition | Union binding tests |
| Source/canonical rows or publication attempts arrive in another order | Canonical source rows `(ISIN Code, Symbol)`; canonical members `(isin, exchange, effective_symbol, provider_symbol)`; cohorts/publication `NIFTY_50` then `NIFTY_NEXT_50` | Input-order identity drift; nondeterministic output/write order | Permutation/publication-order tests |
| Benchmark or smoke exceeds frozen budgets | Candidate fails performance acceptance | Hours-scale qualification presented as success | Timed focused benchmark/smoke |
| Public result is 262,145 bytes or dependency output contains member/provider/private detail | Fail closed before public serialization; bounded sanitized result only | Symbols, ISINs, OHLCV, URLs, paths, cookies, payloads, cache/log content | Bound/redaction/stdout/stderr tests |

Combined validation and effect precedence is:

1. exact feature enablement and per-invocation owner-private acknowledgement;
2. caller request type, structure, and 262,144-byte bound;
3. all three constituent bounded reads, identities, schemas, cardinalities,
   disjointness, witness equality, and canonical order;
4. canonical identity and mapping support;
5. schedule and completed-session temporal admission;
6. both existing request/revision lookups in fixed cohort order;
7. any existing-byte conflict, which stops all new provider/store effects;
8. when at least one cohort remains unresolved, named-pool, bounded-session,
   import-order, cadence, byte-bound, and logging configuration admission;
9. unresolved cohort provider, frame, and immutable-retention processing in
   fixed `NIFTY_50`, `NIFTY_NEXT_50` order; and
10. cross-cohort union compatibility and bounded sanitized serialization.

An earlier shared failure prevents every later effect. After shared admission,
a provider or frame failure does not short-circuit the second unresolved
cohort: both exact rows are produced in fixed order. A retention failure stops
all later provider/store effects because store safety is no longer established;
an unresolved later cohort becomes
`NOT_ATTEMPTED/BLOCKED_BY_PRIOR_RETENTION_FAILURE`, while an already valid
reused row remains valid. Union evaluation occurs only after the ordered pair
is closed.

## Acceptance and review boundary

Issue #154 is complete when this contract records source evidence and the measured benchmark, an independent Sol/high exact-byte review approves the decision, a bounded implementation Issue is created from the frozen contract, applicable documentation and repository gates pass, and the planning PR is reviewed and merged.

The implementation Issue must add discriminating failing checks for every applicable matrix row before changing runtime. It requires a completed-session current smoke because it will claim real provider acquisition behaviour, but it does not require four distinct sessions or unchanged Plan 29. Sprint 17 remains a separate nonblocking historical qualification lane.
