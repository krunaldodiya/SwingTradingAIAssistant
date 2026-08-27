# Current same-pass Market Regime contract

Status: **IN PROGRESS — ALL REQUIRED CURRENT SMOKES AND EXACT CURRENT LOCAL GATES PASSED (844 FOCUSED; 3,392 FULL AT 89.52% COVERAGE; RUFF/PYRIGHT/VULTURE/DIFF/BUILD/WHEEL); CANDIDATE COMMIT CREATED; EXACT-SHA FUNCTIONAL/PROVENANCE APPROVAL REQUIRES RERUN; PR/HOSTED/MERGE/CLOSEOUT PENDING**
Issue: [#119 — Sprint 14: integrated current research packet](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119)
Risk: **R3 / High — financial, temporal, and evidence impact**
Decision owner and residual-risk owner: **repository owner**

## Authority, problem, and lifecycle

The owner selected Design A: one bounded current decision cutoff, one exact
canonical supplied cohort, one current acquisition/read of the latest 21
completed official sessions, one immutable same-pass context retained before
return, and pure Market Regime and Industry reductions over that context.

Operational evidence showed that the delivered Plan-20 prospective chain had
zero usable 21-object inputs. Current/live feature availability therefore MUST
NOT depend on this tool having run on prior sessions. For a current cutoff, the
service admits exact approved retained or provider raw bars available now,
retains their complete grid now with truthful current `known_at`, and makes no
claim that those values were available at their historical session cutoffs.
Missing Plan-20 prospective envelopes, including after 0, 1, 7, or 30 inactive
days, is never a current-domain failure.

This plan is the authoritative implementation contract for these successors:

- `current-same-pass-raw-daily-grid@v1`;
- `current-supplied-cohort-market-regime@v3`;
- `current-supplied-cohort-industry-participation@v2`; and
- `current-supplied-cohort-research-packet@v2`.

Plan-20 `current-supplied-cohort-market-regime@v1` and `@v2` remain frozen,
delivered, byte/value/API compatible historical records. They are not renamed,
reinterpreted, aliased, or used by this path. Plan-26 packet `@v1` was
unpublished work in progress and is superseded before delivery by packet `@v2`.
It MUST be cleanly replaced; no `@v1` alias or dual public path may ship.
Plan-26's 101 focused-test result and its specification/repair record remain
truthful WIP history, not acceptance evidence for this successor.

Lifecycle is **IN PROGRESS — ALL REQUIRED CURRENT SMOKES AND EXACT CURRENT
LOCAL GATES PASSED (844 FOCUSED; 3,392 FULL AT 89.52% COVERAGE;
RUFF/PYRIGHT/VULTURE/DIFF/BUILD/WHEEL); CANDIDATE COMMIT CREATED; EXACT-SHA
FUNCTIONAL/PROVENANCE APPROVAL REQUIRES RERUN;
PR/HOSTED/MERGE/CLOSEOUT PENDING**. Raw query
defects found by prior smokes remain fixed and behavior-tested, including
within-current-month, cross-month, and closed-only retained-minute queries; the
per-member ceiling;
OHLCV aggregation; missing/duplicate rejection; exact provisional source-plan
replay; and provisional provenance.

Official acquisition automation is implemented. Current exact schedule, mapping,
Industry, event, raw, and Plan-21 evidence was retained and validated. Fresh
post-close evidence passed with schedule SHA-256
`f50e7853ce91e3868678b40b5ece79beea0aa469317d348129e96b1c3b71b0a0`,
Industry SHA-256
`1a40e33a0febf458986a178bc76f7b0051f163718f2a8bc11a726ba70a39c0a9`,
and Event SHA-256
`fe77c222ccf73c9a90b7c94641f6e39055c5a4956467729fabda4c8a9ea4b297`.
The Plan-21/22/24/25 cohort bridge projections and equality mappings remain
implemented. The first-class adjusted `NOT_ATTEMPTED` /
`UPSTREAM_INSUFFICIENT_EVIDENCE` projection truthfully suppresses Plan-22
acquisition after upstream raw or screen insufficiency; it is not a delivered
Plan-22 failure.

The final 14-file focused portfolio passed **844 tests** with intentional
`--no-cov`. On these current bytes, the strict one-lease post-close `RELIANCE`
positive passed for the 2026-08-26 decision session: 21 raw bars; Market Regime,
Industry, and Packet `OBSERVED`; partial `NOT_APPLICABLE`; Plan 21 `SCREENED`;
Plan 22 `SUCCESS`; and guarded retries preserved exact bytes, identities, and
original times.

The mandatory Aug-27 market-hours `RELIANCE` positive passed on frozen
fingerprint
`61d5574bc6ae034cab471d3cc30b1b6d7aa891859c6c48c6eaf60f65224c541d`
during the actual active session. The decision cutoff was
`2026-08-27T04:29:06.612060Z` (`09:59:06` IST), and the effect deadline was
`2026-08-27T04:28:36.612060Z`. Composed schedule SHA-256
`fb4e60b4c9e62887211cd5083403a4b0dfca2ab4b95f1c7415b27c0c8e1ac9ae`
defined 2026-08-27 as `REGULAR`, 09:15–15:30 IST, with S0 2026-07-29 and S20
2026-08-26; the 2026-08-27 mapping observation was
`02e150b0b910f9ebe825b1c77f48126e4a0046073bf24ae767211fe66480bbf3`.

Raw was 21/21 `OBSERVED`; Plan 21 was `SCREENED`; live Plan 22 was `SUCCESS`
before the deadline; Market Data, Market Regime, Industry, and Packet were
`OBSERVED`; Event was `RETAINED`. Packet identity SHA-256 was
`cc3619cddcd2a35c73500947f40db863a5cb56df5a6aa377c2b0d91261556474`,
and context identity SHA-256 was
`e8b0371527994b39d6c905967c7814fce792fee627221cfd54cc51f65285153a`.
The requested partial was truthfully `UNAVAILABLE` /
`PARTIAL_MEMBER_MISSING` with zero rows, separately labelled
`PARTIAL_CURRENT_SESSION`, excluded from the completed grid and Market Regime,
nonfatal, and never substituted. Exact retries preserved bytes, identities, and
original times and caused zero effects; source remained unchanged and all
resources were closed.

The final full suite passed **3,392 tests at 89.52% total coverage** against the
**87%** threshold. Ruff format/lint and Pyright currently pass. Vulture at 80% reports no findings and `git diff --check` passes. `uv build` produced the sdist and wheel. A clean installed-wheel smoke outside the checkout passed on CPython 3.13.7, with all 12 current runtime identities SHA256-shaped.

Eight review blockers are fixed locally without a new subsystem: late
completion-marker retry guards; zero-redirect enforcement; restored global
`ScheduleSession` kind compatibility with the exact `REGULAR`/`SPECIAL` gate
kept Plan-27-only; Industry V1 compatibility; Event legacy adoption; 62-day
month-start acquisition; pre-Plan-22 deadline enforcement; and corrected
Plan-24 wording.

The directory-edge `st_nlink` portability fix remains in place without
weakening leaf metadata checks; exact source-file checks remain enforced and
the dependent runtime identity manifests remain current. The native supported
target remains POSIX-style macOS and Linux; Native Windows is unsupported, WSL2
or Docker is the stated Windows path, and exact-candidate Linux hosted CI has
not run and is not claimed.

The fresh current-byte genuine IRCTC production negative passed with the exact
`NO_TRADE` outcome: raw `INSUFFICIENT` / `RAW_ACQUISITION_UNAVAILABLE`; Market
Regime V3 insufficient; Plan 22 `NOT_ATTEMPTED` upstream; Industry V2
`UNSUPPORTED` with `MARKET_REGIME_UNAVAILABLE` and
`CLASSIFICATION_MEMBER_UNSUPPORTED`; and Packet insufficient with the exact
ledger, five null AI facts, and mandatory `NO_TRADE`. Guarded V3, Industry,
event, and Packet retries preserved exact bytes, identities, and original times.
All required current smokes have passed: the retained post-close `RELIANCE`
positive, mandatory market-hours `RELIANCE` positive, and genuine IRCTC
negative. The two positive modes remain separate; neither substitutes for the
other. A candidate commit has been created. Exact-SHA functional and provenance approval requires rerun; PR, hosted checks, merge, and closeout remain pending. No acceptance, completion, or
delivery is claimed until the lifecycle is complete.

The 2026-08-26 acquisition, parser, schedule-source, source-manifest, test, and
runtime-manifest changes invalidate the following 461-test/full-gate/wheel and
34-file worktree review evidence for the current bytes. It remains truthful
historical evidence for the immediately preceding candidate only and must not
be used as current acceptance or release evidence.

The four Plan-27 focused suites passed with intentional `--no-cov`: raw 111,
Market Regime V3 71, Industry Participation V2 31, and Research Packet V2 53
(**266 total**). The directly affected frozen event, classification, V2-regime,
and V1-Industry suites—including the verifier directory-edge regression—also
passed with intentional `--no-cov` (**195 total**): **461 focused tests**.

Full local gates passed: Ruff format checked **272 files already formatted**;
Ruff lint passed; Pyright reported **0 errors and 0 warnings**; Vulture at
minimum confidence **80** reported no findings; full pytest passed **3,306 tests
at 89.77% coverage** against the **87%** threshold; `git diff --check` passed;
and `uv build` produced both sdist and wheel.

The clean Python 3.13 installed-wheel runtime smoke passed with exact runtime
identities: raw
`84af15929411dcd3ff05ff7b29cf618ef3ac0cf185b76719b65a0caa7a8d5a72`;
Market Regime V3
`5a0a7d6ed45caafac02ba64bbc31242fc6ce8c7e031c7b10c2ab6844a78a6053`;
Industry Participation V2
`160a017d72997249a357417c9f4cc8b92ccd3d54de19bc19c0bcc47f044d6235`;
Research Packet V2
`db8eceb9f6dc451e7bb6c697db5afcd1adacad545bbbe3889e22b7ec57ba5715`;
event
`a953e8d1fa8b051838bb65cdf94a1a423bac980f40829c30f51c64a0b77f98a0`;
classification
`284d9c62d03c589fdd5ee40fb8c610fb75489e5ec2efb047c2ecb03404b3a925`;
Market Regime V2
`fe71669f643401e2c5dd84e4db0fc6b768620d18ecec359e8ebfbe6ae451b20f`;
and Industry Participation V1
`6200f5503df29c778c45f9a756fe85acee38db1c04afcfd53660d50dd88d4ec6`.
The verifier directory-edge race is fixed, exact source-file checks remain
enforced, and the global runtime identity manifest is corrected. Plan-27 cohort
bridge mappings remain implemented, including truthful Plan-22 suppression
after upstream raw or screen insufficiency.

Fresh resumed review of the unchanged 34-file final worktree candidate returned
functional/domain/temporal **APPROVE**. Its reviewed-set aggregate is
`4782d16f2e867601c976e936bd2200c12db072434e70bf0045c07d05359ffd8f`,
using listed-order `path + NUL + file-SHA-256 + LF` framing. Fresh resumed R3
provenance/privacy/evidence-integrity review returned **PASS** with aggregate
`cd271d3ce22400fc5e69ff83d2e9cc2e0c4716dfa726246ff46c795cd5fa2e82`,
using sorted `path + NUL + 8-byte length + exact bytes` framing. Both reviews
observed all 34 files unchanged throughout review; all direct and global runtime
identity manifests matched their bound sources. These worktree reviews are not
the final committed exact-SHA review. Any source or test change invalidates them
and requires fresh worktree reviews.

Official acquisition automation has exercised and retained the current exact
schedule, mapping, Industry, event, raw, and Plan-21 evidence. The strict
one-lease post-close `RELIANCE` positive, mandatory Aug-27 market-hours
`RELIANCE` positive, and genuine IRCTC production negative passed with the
state projections recorded above. All required current smokes and exact current
local gates have passed; the positive modes remain separate and neither
substitutes for the other. A candidate commit has been created. Exact-SHA
functional and provenance approval requires rerun; PR, hosted checks, merge,
and closeout remain **PENDING**. No acceptance, completion, or delivery is
claimed until the lifecycle is complete.

## Five-line evaluation

1. **Expected value:** provide usable current Market Regime and packet evidence without waiting 21 future exchange sessions or requiring prior tool runs.
2. **Scope fit:** exact current-only `1..50` canonical NSE equities, 21 completed daily raw sessions, optional provisional current-session context, delivered Industry/events, and owner-private local Python consumption.
3. **Material risk:** current retrieval can be mislabeled as historical availability, while cohort/schedule/mapping/source/price-basis or partial/completed splicing can create a false financial-research fact.
4. **Smallest alternative:** retain one complete current same-pass context and reuse Plan-21/22/24/25 capabilities instead of adding replay, another provider, an adjustment engine, or another delivery surface.
5. **Decision:** **ACCEPTED — Design A**, subject to RED tests, real current smokes, exact-revision R3 reviews, repository/hosted gates, and owner acceptance.

### Owner-authorized smallest acquisition correction

1. **Expected value:** current repeatable evidence and smoke unblock.
2. **Scope fit:** the default workflow is the current Nifty 100, while every
   reusable core admits an explicit bounded `1..50` canonical supported NSE
   equity list independently of index membership.
3. **Material risk:** source drift, Akamai, composed calendar, and corrections.
4. **Smallest alternative:** three bounded official fetch capabilities feeding
   existing parsers, with no generic provider framework.
5. **Decision:** **ACCEPTED by owner**.

The correction is limited to one no-retry/no-fallback acquisition edge. It
initializes the official NSE announcements page and fetches the unfiltered
Equity `1D` CSV, fetches the exact NSE Indices Nifty 100 Industry CSV, and
fetches the bounded Upstox plus official NSE Capital Market evidence used by the
pure schedule composer. The Industry CSV is only a classification capability:
an explicit supported NSE equity absent from it returns
`CLASSIFICATION_MEMBER_UNSUPPORTED` without rejecting price, event, or schedule
capabilities. No core equates the supplied cohort with an index or admits by
provider identity. The edge adds no polling, attachment fetch, filter,
normalization, provider registry, credential path, or narrative logging.

The event response must have exactly one `Content-Disposition`; its publisher
filename must be the exact requested one-day range and is passed unchanged.
The current edge admits UTF-8 with either exact publisher-returned BOM state and
the current `BOUNDED_OFFICIAL_FETCH` licence only. Legacy filename and manual
licence support remain parser/archive replay compatibility and require a BOM;
they are not another current fetch path. An exact header-only CSV is zero
announcements and projects
`NO_MATCHING_NOTICE_IN_SNAPSHOT` for every member.

## Working-feature-first partition

### FIRST_WORKING_SLICE

For one exact owner-supplied canonical cohort of `1..50` supported NSE `EQ`
listed equities, return either:

- a retained Market Regime V3 `OBSERVED` aggregate, same-pass Industry
  Participation V2 aggregate, and retained Research Packet V2; or
- retained whole-result insufficiency with closed reasons and mandatory
  `INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED`.

The slice includes:

- prior-run-independent current availability from exact approved retained or
  provider raw bars available now;
- composed-source latest-completed-session resolution for any admitted UTC
  cutoff, including market-hours and finalized post-close modes;
- exactly 21 completed official-session raw daily bars per member;
- an optional separately labelled `PARTIAL_CURRENT_SESSION` price/volume
  snapshot for current swing-research context;
- existing Plan-21 screened corporate-action evidence and Plan-22 V2 adjusted
  S0/S20 comparison;
- one prearchive private member-direction candidate embedded in the immutable
  context and consumed only through the archive seal by Industry V2;
- packet V2 clean cutover, facts-only same-owner local AI consumption,
  retain-before-return, exact retry, redaction, and mandatory `NO_TRADE`; and
- R3 tests, real smokes, exact-revision reviews, gates, and delivery controls.

### LATER_IMPROVEMENTS

- historical point-in-time availability ledgers, replay, backtest, backfill,
  revised-source lineage, and correction graphs;
- capture-first/post-acquisition cutoff Design B or another Plan-22 lifecycle;
- measured parallel acquisition, another provider, provider fallback, BSE, or a
  generic provider/component/archive registry;
- full deferred Plan-22 hardening, external attestation, a hostile-dependency
  sandbox, or a generalized tamper model;
- recurring polling, additional acquisition sources, official Sector mapping,
  general news, attachments, sentiment, materiality, rank, or score;
- CLI, API, MCP, UI, notification, hosted/shared/public delivery, or another
  model-transfer boundary; and
- Market Structure, indicators, signal, recommendation, position size, order,
  broker integration, or effectiveness claims.

A later item enters this slice only when it is the least costly adequate fix for
a cited current acceptance, R3, safety, correctness, usability, authorization,
privacy, or evidence-integrity blocker, or the owner explicitly changes scope.

## Current-only temporal contract

### Cutoff and latest completed session

`decision_cutoff` is one exact six-fraction UTC instant and is the authoritative
current knowledge and context-commit deadline. The builder samples one trusted
`invocation_started_at`; admission and the effect deadline are:

```text
invocation_started_at + 60 seconds <= decision_cutoff
decision_cutoff <= invocation_started_at + 30 minutes
acquisition_effect_deadline = decision_cutoff - 30 seconds
```

The bounded lead and reserved 30-second archive window are after invocation,
not after market close. There is no after-close-only rule and no
`decision_session == IST_DATE(decision_cutoff)` rule.

From one retained schema-v3 composed NSE Capital Market schedule, resolve:

```text
decision_session = max(session where session.close_at <= decision_cutoff)
S[20] = decision_session
S[0] = the official session exactly 20 positions before S[20]
```

The schedule MUST prove strict `S[0] < ... < S[20]`, official open/close times,
weekends, closures, special sessions, source/release, timezone, and coverage
through the cutoff-local date. During an active official market session,
`S[20]` is the prior completed official session. Once today's official close is
at or before the cutoff, `S[20]` may be today. A missing current raw bar never
silently moves `S[20]` backward; it is a genuine current evidence failure.

`decision_session` is derived, not caller-selected. It appears in retained and
public results and is bound into identities. Equality at cutoff is admitted;
one microsecond later is future-known or deadline failure as applicable.

### Bounded schedule acquisition and composition

The schedule acquisition edge covers at most 45 calendar dates and at most two
years. It performs exactly one current-year Upstox holiday GET, exactly one
official NSE `holiday-master?type=trading&year=<YYYY>` GET for each covered
year, and one Upstox date-specific market-timings GET for every covered
prior-year date that the current-year holiday response cannot prove. This gives
an exact maximum of 50 named observations for the complete acquisition bundle.

Each observation binds the exact request/final URL, status, exact body
bytes/count/SHA-256, trusted UTC `known_at`, bounded cookie count/aggregate
bytes, and only the arrival-ordered allowlist `Content-Type`,
`Content-Encoding`, `Content-Length`, `Content-Disposition`, `Date`, `ETag`,
and `Last-Modified`. Cookie names/values, `Set-Cookie`, and all other response
headers are private and absent from observation, manifest, and identity
projections. Every allowlisted field is singleton; a duplicate fails closed.
Hosts, URLs, response media types, body/header/cookie/cardinality/depth/node/time
bounds, timeout, and zero redirects are fixed. There is no retry, fallback,
decompression, empty-set substitution, or credential-bearing request.

`Content-Type` uses one closed grammar per endpoint. The required media types
are `text/csv` for Industry and event CSV, `text/html` for the NSE
announcements initializer, and `application/json` for schedule endpoints.
Media type comparison is ASCII case-insensitive. The only admitted forms are
the required media type alone or that media type followed exactly by `; `, the
ASCII case-insensitive parameter name `charset`, `=`, and the charset token
`utf-8` modulo ASCII case. Media aliases, `utf8`, ISO-8859-1, unknown or
duplicate parameters, malformed tokens, and duplicate header fields are
rejected. `Content-Encoding` is absent or exactly `identity`. Every
body must decode exactly as UTF-8 before endpoint parsing. The event input's
`source_encoding` must equal the `UTF-8` derived from this response metadata.
The current event BOM state is derived from the exact response bytes, may be
present or absent, and remains identity-bound through every downstream boundary.

Observations, named observation sets, and acquisition bundles are minted only
through closure-private weak registries whose mint-time bindings are not stored
as readable object capabilities. `object.__new__`, caller `setattr`, a
recomputed forged hash, or a set/bundle spliced from separately minted objects
does not create registry membership. Before composition, every named
observation is revalidated for exact registry membership, identity, URL,
allowlisted singleton headers, body bytes/hash/size/UTF-8 decoding, trusted
time, cookie bounds, and endpoint media profile. The pure composer accepts only
that exact revalidated acquisition-minted named set.

`validate_current_sprint14_evidence_bundle_v1` is the downstream adoption
validator. It requires the bundle's closure-private mint registration, then
replays the source manifest and composed schedule from the named observations,
recomputes manifest/schedule/runtime identities, reparses the exact Industry and
event artifacts, and rebinds both parser inputs to their named observation
bodies and response metadata. A forged object, mutated field/hash, stale
manifest, mismatched schedule, or mixed artifact/input/bundle is rejected.
The composer strictly rejects duplicate JSON keys, nonstandard constants,
floating-point numbers, excessive JSON depth/nodes/array cardinality,
semantically empty current-year Upstox data, empty NSE `CM`, timestamp overflow,
and unknown CM row keys. The NSE holiday-master root has exactly `CBM`, `CD`,
`CM`, `CMOT`, `COM`, `EGR`, `FO`, `IRD`, `MF`, `NDM`, `NTRP`, and `SLBS`.
Every segment value is a bounded list, but only `CM` is interpreted for the cash
market. Every `CM` row has exactly `tradingDate`, `weekDay`, `description`,
`morning_session`, and `evening_session`; the publisher does not supply
`Sr_no`.

The composer validates unique dates/exchanges, recognized holiday types,
local-date-consistent minute-aligned epoch milliseconds, and never admits NSE
as both open and closed. Prior-year weekdays require complete date-specific
timing evidence or an exact NSE closure; missing evidence fails closed. Date
precedence is exactly:

1. explicit Upstox NSE open/closed evidence;
2. official NSE `CM` closure;
3. named Saturday/Sunday closure policy; then
4. named regular-weekday `09:15..15:30 Asia/Kolkata` policy for the current
   year only.

Every explicit regular NSE opening must equal exactly `09:15..15:30
Asia/Kolkata`. Any explicit non-regular opening, including `SPECIAL_TIMING`, is
`SPECIAL_SESSION_UNCORROBORATED` until exact bounded official circular bytes
are fetched, parsed, and sealed. No caller assertion or inferred special timing
exists. An Upstox weekday closure absent from NSE `CM`, an Upstox NSE open
against an NSE `CM` closure, duplicate/conflicting rows, invalid/nonlocal times,
or an unrecognized type fails closed. Every covered date is exactly one session
or closure.

The observed 2026-08-26 composition has an Upstox
`SETTLEMENT_HOLIDAY` row with NSE explicitly open `09:15..15:30` and no
2026-08-26 closure in NSE `CM`. Entries dated 2026-08-26 in other NSE root
segments are not cash-market closures. The composed result is therefore one
regular NSE cash-market session for 2026-08-26.

The canonical source manifest is replayed from the same named schedule
observations that mint the schedule. It binds every yearly holiday master,
every prior-year date-specific timing response, official regular-session
policy, coverage, timezone, precedence/fail-closed rules, and acquisition
runtime identity. Its SHA-256 defines `source_release =
"composed-calendar@v1=<manifest_sha256>"`. The schema-v3 schedule source is
`nse-upstox-composed-calendar`; it is never relabelled
`nse-authoritative-calendar`.

### Prior-run independence and gap recovery

The current path MUST behave identically for 0-, 1-, 7-, and 30-day tool
inactivity when the current admitted request, schedule, cohort, mappings, source
bytes/receipts, `known_at` values, and other component inputs are equal. Tool
inactivity duration is not an input, persisted state, identity field, reason,
or admission gate.

For the resolved `S[0]..S[20]`, the raw port MAY use already retained exact
approved bars or invoke the approved Upstox acquisition now for any missing
range, including all 21 historical session dates after a long gap. Newly
observed rows retain the actual current ingestion/publication evidence and
current `known_at`. They MUST NOT inherit a session timestamp as `known_at`, be
backdated to a missed cutoff, or manufacture the 21 prospective Plan-20 archive
objects. Equal price values observed under different current receipts or
knowledge times are different evidence and may have different identities.

A current result is blocked only by a genuine current capability/evidence
failure: unavailable, missing, stale, conflicting, malformed, future-known, or
unlicensed schedule, mapping, raw bar/source evidence, corporate-action screen,
adjusted comparability, classification, event evidence, retention, or deadline.
There is no `TOOL_INACTIVE`, `PROSPECTIVE_ENVELOPE_MISSING`,
`HISTORICAL_ARCHIVE_MISSING`, or equivalent reason.

### Truthful knowledge time

Session/bar timestamps are market times, not knowledge times. Existing retained
source retrieval, publication, coverage, and checksum times are preserved
exactly. A provider publication time absent from admitted evidence is null,
never inferred.

Every admitted mapping/source observation, raw row, Plan-21 selected snapshot,
Plan-22 `retrieved_at`, retained Industry `known_at`, retained event `known_at`,
optional partial `known_at`, and same-pass context `known_at` MUST be no later
than `decision_cutoff`. The context exposes:

```text
temporal_scope = "CURRENT_SAME_PASS_ONLY"
historical_availability_claim = false
replay_capability = "NONE"
```

Historical dates in the grid prove only which completed sessions are compared
now. They do not prove that any bar, mapping, schedule revision, corporate-action
screen, adjusted value, Industry label, or event notice was available at a
historical cutoff.

Industry V2 is an explicit current-only successor composition, not Plan-24 V1
historical/session equivalence. It admits structurally exact retained current
classification only when `known_at <= decision_cutoff` and
`IST_DATE(known_at) == IST_DATE(decision_cutoff)`. During market hours,
`decision_session` may be the prior completed session; V2 never backdates a
classification to that session or claims historical classification availability.
An older date is `CLASSIFICATION_SESSION_STALE`; a future time/date is
`CLASSIFICATION_FUTURE_KNOWN` with the closed stale precedence where applicable.
Plan-24 V1 remains frozen.

Packet V2 admits a retained Plan-25 event snapshot as current success only when
its filename/source date, `IST_DATE(event.known_at)`, and
`IST_DATE(request.decision_cutoff)` are equal and `known_at <= decision_cutoff`.
An older exact snapshot is `EVENT_SOURCE_DATE_STALE`, mapped to
`COMPONENT_STALE` and the all-null `NO_TRADE` packet projection; a newer/future
snapshot is `EVENT_SOURCE_DATE_FUTURE`, mapped to
`COMPONENT_FUTURE_KNOWN`.

## Canonical cohort and completed raw grid

The request contains exactly `1..50` members sorted canonically by
`(isin, exchange, effective_symbol)`. Each
`CurrentSamePassEquityMemberV1` binds the closed ordered fields:

```python
class CurrentSamePassEquityMemberV1:
    isin: str
    exchange: Literal["NSE"]
    instrument_type: Literal["EQUITY"]
    segment: Literal["EQ"]
    effective_symbol: str
    valid_from: date
    valid_through: date
    provider_symbol: str
    mapping_version: Literal["yfinance-symbol-mapping@v1"]
    mapping_valid_from: date
    mapping_valid_through: date | None
    mapping_identity: str
    provider_mapping_revision: str
```

`provider_symbol` through `mapping_identity` are the exact owner-supplied
Plan-22 V2 mapping surface. `provider_mapping_revision` is the distinct exact
Plan-25 cohort-mapping revision; neither value is inferred from the other. All
effective intervals cover `S[0]..S[20]`; `valid_through` is non-null because
the Plan-25 bridge requires an exact closed interval. No index name or
membership assertion exists in the reusable core. A supported explicit stock
outside the Nifty 100 is admitted when its canonical identity and all required
evidence exist. BSE or another unsupported capability is typed
unsupported/insufficient evidence, not an index-membership failure.

For every member and every `S[j]`, the grid contains exactly one completed raw
daily OHLCV row: `21 * cohort_size`, maximum 1,050. No omitted, duplicate, extra,
partial, inferred, adjusted, mixed-basis, fallback-provider, stale, malformed,
future-known, or conflicting row is admissible. Raw provider/basis is exactly
`UPSTOX` / `RAW`.

Market Regime uses only exact Decimal `close(S0)` and `close(S20)`. The other 19
sessions are retained to prove the official grid and reproducibility; they do
not add another factor. Direction is `ADVANCE`, `DECLINE`, or `UNCHANGED`.

## Optional `PARTIAL_CURRENT_SESSION`

The request field `include_partial_current_session: bool` controls an auxiliary
snapshot. It does not alter `S[0]..S[20]`, completed facts, Market Regime,
Industry direction, or required packet-component admission.

The closed public shape is:

```text
label: "PARTIAL_CURRENT_SESSION"
state: "NOT_REQUESTED" | "NOT_APPLICABLE" | "OBSERVED" |
       "UNAVAILABLE" | "CONFLICTED"
session: LocalDate | null
as_of: UtcInstant | null
known_at: UtcInstant | null
rows: tuple[PartialCurrentSessionRowV1, ...] | null
reasons: tuple[PartialCurrentSessionReasonV1, ...]
partial_snapshot_identity_sha256: Sha256
```

An `OBSERVED` row contains only canonical member identity, session, exact last
completed retained one-minute close as provisional `price`, cumulative volume
through the same `as_of`, source/basis, row source receipt, row `known_at`, and
row identity. It requires an active official session with
`session.open_at <= as_of <= known_at <= decision_cutoff < session.close_at`,
exactly one row per cohort member, and `session > S[20]`. It is provisional even
when every row is present.
The private raw result retains the exact mapping receipt and
`CurrentSamePassPartialOfficialSessionV1` used for every observed partial row.
Its row source receipt is the canonical hash of that mapping identity, the
official-active-session identity, `session`, `as_of`, and query `known_at`; a
replay rejects a different member order, completed minute, active session,
mapping, or receipt.

`NOT_REQUESTED` has no session/time/rows/reasons. `NOT_APPLICABLE` has no rows
when no active official current session exists at the cutoff, including a
finalized post-close mode. Requested but missing, stale/future, malformed, or
partly unavailable data yields `UNAVAILABLE`; more than one distinct admissible
value for a member/scope yields `CONFLICTED`. Closed partial reasons render in
this order:

1. `PARTIAL_SOURCE_UNAVAILABLE`;
2. `PARTIAL_SESSION_MISMATCH`;
3. `PARTIAL_MEMBER_MISSING`;
4. `PARTIAL_MEMBER_CONFLICTED`;
5. `PARTIAL_SNAPSHOT_INVALID`;
6. `PARTIAL_FUTURE_KNOWN`.

Partial failure is non-fatal to an otherwise valid completed context and packet
because this capability is optional. It remains visible under its own state and
identity; it never replaces or neutralizes a completed fact. Query invocation,
payload access, Decimal/integer arithmetic, and row/snapshot projection
exceptions are partial-capability failures. They produce visible `UNAVAILABLE`
partial evidence with a closed partial reason while an otherwise valid completed
raw grid, Market Regime, Industry result, and packet remain valid.

Any use of partial price/volume as a completed S20 close/volume, Market Regime
input, Industry input, historical fact, signal, or recommendation makes the
whole packet insufficient with `PARTIAL_AS_COMPLETE` and no AI fact projection.

## Provider-neutral raw snapshot/acquisition boundary

Existing `QueryRequestV1`/`QueryReportV1` is insufficient as the successor
contract. It is one-symbol/calendar-range oriented; `PublicQueryRowV1` contains
only OHLCV; its publication/knowledge/checksum metadata is coverage-level rather
than row-level; and it cannot prove one exact cohort-atomic official
`S[0]..S[20]` grid. `CurrentCohortMarketDataRequestV1` is also insufficient: its
built-in seven-calendar-day `1m` query selects one newest completed daily fact
per member, not a 21-session series. Neither V1 contract is changed.

The narrow provider-neutral boundary is:

```python
class CurrentSamePassMarketRegimeRequestV3:
    contract_version: Literal["current-supplied-cohort-market-regime@v3"]
    decision_cutoff: datetime
    cohort_selected_at: datetime
    members: tuple[CurrentSamePassEquityMemberV1, ...]
    schedule_evidence_sha256: str
    schedule_source: Literal["nse-upstox-composed-calendar"]
    schedule_source_release: ComposedCalendarReleaseV1
    include_partial_current_session: bool
    plan21_cohort_identity_sha256: str
    canonical_cohort_identity_sha256: str
    plan22_request_identity_sha256: str
    request_identity_sha256: str


class CurrentSamePassRawDailyPortV1(Protocol):
    def acquire_exact(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        sessions: tuple[CurrentSamePassRawSessionV1, ...],
        lease: StorageRootLease,
    ) -> PrivateCurrentSamePassRawDailyResultV1: ...


class UpstoxCurrentSamePassRawDailyV1:
    """The only first-slice implementation; no registry or fallback."""
```

A complete private result retains its exact resolved 21-session sequence, closed
row-level mapping receipts, coverage source rows, and—when partial context is
requested and an official active session exists—the closed official active-session
evidence. It retains explicit null retained-coverage publication/knowledge fields,
actual current row `known_at`, manifest/partition/checksum/source-receipt/bar
identities, exact resolved schedule identity, and whole-grid identity specified
below. Coverage metadata is attributed to each derived daily row only as evidence
for the retained partition from which the row was queried. It MUST NOT be
described as provider publication of that daily row. An insufficiency serializes
no partial completed grid.

`UpstoxCurrentSamePassRawDailyV1` reuses one concrete existing path, under the
same caller-supplied live `StorageRootLease`, with no provider or transport
addition:

1. reconstruct the exact Plan-21 reduced manifest and admit the full supplied
   cohort; resolve every member through
   `RetainedCurrentCohortInstrumentResolverV1` and the exact retained
   `InstrumentSnapshotMetadataV1` projection
   `(schema_version, source, observation_date, retrieved_at,
   observation_sha256, compressed_sha256, decompressed_sha256,
   compressed_byte_count, decompressed_byte_count, relative_object_path,
   relative_metadata_path, etag, last_modified)` plus the exact resolved
   `Instrument` projection `(instrument_key, security_id, symbol, exchange,
   segment, instrument_type, isin)`;
2. require all mappings before a download effect, retain their current
   `retrieved_at/known_at`, and keep `instrument_key`, `security_id`, and paths
   private;
   Missing retained snapshots or missing equities map to `RAW_MAPPING_MISSING`;
   corrupt/stale snapshots map to `RAW_MAPPING_STALE`; ambiguous resolutions,
   identity conflicts, and other unsafe resolver/catalog outcomes map to
   `RAW_MAPPING_CONFLICTED`. The default resolver never collapses these closed
   outcomes through a catch-all missing reason.
3. for each missing bounded symbol/range, construct the exact
   `SingleSymbolDownloadRequestV1` and call
   `_default_download_service(...).download_under_lease(request, lease)`
   directly on the current-aware `PublicDownloadPortV1`; the call does not pass
   through `BoundedNifty50DownloadServiceV1.download_single`, does not reacquire
   the root lease, and adds no CLI command, service, provider, or transport;

   The factory call supplies the exact authoritative open/closed schedule files,
   the full-cohort `CurrentSuppliedCohortAdmissionPolicyV1`, and the one Plan-27
   deadline gate. The factory's default preview admission policy is forbidden.
   Those arguments are reused for every member; no per-symbol policy or gate is
   constructed.
   Coverage discovery returns the exact missing per-symbol month/range requests.
   A missing manifest may authorize only its corresponding request. A malformed,
   unverified, conflicted, or unreadable catalog/coverage result fails closed
   with a raw-bar reason and starts no download; a false/error result never
   expands into a full-cohort download.
4. query each member once through the existing current-aware retained
   `PublicQueryPortV1` with `timeframe="1m"` and `max_rows=10_000`, under the
   same lease. A cross-month range uses its existing closed plus current-aware
   composition; no generic service change, provider, backfill, or query route is
   added;
5. form each daily OHLCV only from the exact official minute grid
   `[open_at, close_at)` for every one of the 21 selected sessions. Each expected
   minute must appear once with all OHLCV values; any off-grid, duplicate,
   missing, invalid, open/close, or aggregate invariant failure fails closed;
   and
6. bind every closed-month bar to the existing exact verified-manifest projection
   and verified `PublicCoverageMonthV1`; bind every current-month bar to the
   exact `ProvisionalPartitionMetadataV1` and matching provisional coverage
   projection. The latter retains its schema, cutoff, completion flag, byte
   size, immutable path/checksum, instrument-snapshot digest/retrieval time,
   attempt counts, publication and knowledge time. A mixed or mismatched
   manifest/provisional/query/schedule/mapping projection fails closed.

The source receipt hashes the exact discriminated
`CurrentSamePassRawCoverageSourceRowV1` projection excluding only its own
identity. Verified rows retain null coverage publication/knowledge and use
`manifest_updated_at`; provisional rows retain `evidence_published_at ==
evidence_known_at` and use that exact provisional evidence time. The derived
row knowledge formula is:

```text
bar.published_at = null
bar.known_at =
  max(mapping_receipt.retrieved_at,
      coverage_source.manifest_updated_at
        or coverage_source.evidence_known_at,
      coverage_source.query_completed_at)
```

All inputs are actual retained/current UTC evidence times and must be
`<= decision_cutoff`; no session time, provider time, file mtime, or guessed
publication substitutes. `raw_bar_identity_sha256` binds exact raw OHLCV,
mapping, source receipt, schedule, source policy, interval, null publication,
and `known_at`. Raw and adjusted evidence remain independent.

Acquisition remains an explicit effect before retained read; the read port does
not hide a provider call. The existing factory surface is exact:
`_default_download_service` accepts a caller-supplied `PublicationGateV1`, its
`UrllibHttpTransport` uses the existing 30-second per-call timeout, and its
`IngestionCoordinator` creates an internal default `CancellationToken`. The
factory exposes no caller-owned cancellation or completion signal, and
`PublicationGateV1` is only a synchronous context-manager seam. Those existing
objects therefore do not prove forcible cancellation or quiescence of a
detached worker.

The first slice consequently forbids a thread, task, subprocess, future, or any
other background download worker. The raw port calls
`_default_download_service(...).download_under_lease(request, lease)`
synchronously on its owning thread and retains the same caller-owned lease
until that call and every subsequent reread/archive step have returned. A
Plan-27 deadline gate implementing the existing `PublicationGateV1` protocol is
injected into the factory; on every gate entry it samples the same trusted clock
and rejects entry at or after `acquisition_effect_deadline`. It is a cooperative
start-of-publication gate, not a claim that an already-entered filesystem or
provider operation can be forcibly stopped.

The owning thread samples `download_call_completed_at` immediately after the
direct call returns. A conforming acquisition requires
`download_call_completed_at <= acquisition_effect_deadline`; synchronous return
is the completion and quiescence proof because no background work exists.
After return, no acquisition code retains authority to write. If there is
insufficient time to make that bounded synchronous call, the call is not
started and `ACQUISITION_DEADLINE_EXCEEDED` may be retained inside the archive
window. If a started call returns after the deadline, or completion/quiescence
cannot be proved, only `CurrentSamePassArchiveFailureV1` may return and a new
request/cutoff is required; the contract makes no no-late-write or forcible-stop
claim for that failed invocation. Implementation stops before editing a frozen
component if the direct leased call, injected gate, or synchronous completion
proof cannot be implemented in the authorized new market-data file.

## Closed successor schema bundle

This section is the sole Plan-27 schema authority. It freezes only the four
successor contracts named above; it is not a reusable schema framework.
`UtcInstant` is an aware UTC `datetime` rendered with exactly six fractional
digits and `Z`; `LocalDate` is ISO `YYYY-MM-DD`; `Sha256` is lowercase
64-hex; `DecimalText` is finite, non-exponent canonical decimal text with no
leading plus, negative zero, or redundant leading/trailing zero; `UInt64` is
`0..18_446_744_073_709_551_615`; `PositiveDecimalText` is `DecimalText > 0`.
`ComposedCalendarReleaseV1` matches exactly
`composed-calendar@v1=<64 lowercase hex>` with no alternate prefix or suffix.
ISIN is uppercase Luhn-valid 12 ASCII characters; NSE symbol and safe revision
strings use the existing admitted grammars and are `1..64` and `1..128` UTF-8
bytes respectively. Every tuple is immutable; member/session/row tuples are
sorted by the key stated below and reject duplicates.

For every type in the following tables, the listed field sequence is the exact
constructor/dataclass/value-projection order. Serialized objects are closed:
missing, duplicate, additional, renamed, wrong-order-at-construction,
wrong-type, wrong-unit, wrong-nullability, noncanonical, or out-of-bound values
are rejected before identity calculation. Canonical JSON still emits object
keys lexicographically as specified under **Canonical identities**. `null`
appears only where `or None` is written in a table or `| None` in a Python
sketch.

### Raw daily, Market Regime, and context types

| Type | Exact ordered fields |
| --- | --- |
| `CurrentSamePassEquityMemberV1` | `isin:Isin`; `exchange:Literal["NSE"]`; `instrument_type:Literal["EQUITY"]`; `segment:Literal["EQ"]`; `effective_symbol:NseSymbol`; `valid_from:LocalDate`; `valid_through:LocalDate`; `provider_symbol:SafeText[1..64]`; `mapping_version:Literal["yfinance-symbol-mapping@v1"]`; `mapping_valid_from:LocalDate`; `mapping_valid_through:LocalDate or None`; `mapping_identity:Sha256`; `provider_mapping_revision:SafeRevision` |
| `CurrentSamePassMarketRegimeRequestV3` | `contract_version:Literal["current-supplied-cohort-market-regime@v3"]`; `decision_cutoff:UtcInstant`; `cohort_selected_at:UtcInstant`; `members:tuple[CurrentSamePassEquityMemberV1,1..50]`; `schedule_evidence_sha256:Sha256`; `schedule_identity_sha256:Sha256`; `plan22_schedule_identity_sha256:Sha256`; `schedule_source:Literal["nse-upstox-composed-calendar"]`; `schedule_source_release:ComposedCalendarReleaseV1`; `include_partial_current_session:bool`; `plan21_cohort_identity_sha256:Sha256`; `canonical_cohort_identity_sha256:Sha256`; `plan22_request_identity_sha256:Sha256`; `request_identity_sha256:Sha256` |

| `CurrentSamePassPreflightFailureV1` | `contract_version:Literal["current-same-pass-preflight-failure@v1"]`; `evidence_state:Literal["INSUFFICIENT_EVIDENCE"]`; `request_identity_sha256:Sha256`; `canonical_cohort_identity_sha256:Sha256`; `reasons:tuple[SchedulePreflightReason,1..5]`; `consumer_disposition:Literal["INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"]`; `failure_identity_sha256:Sha256` |
| `CurrentSamePassRawSessionV1` | `position:int[0..20]`; `session:LocalDate`; `open_at:UtcInstant`; `close_at:UtcInstant`; `kind:Literal["REGULAR","SPECIAL"]`; `session_identity_sha256:Sha256` |
| `CurrentSamePassPartialOfficialSessionV1` | `session:LocalDate`; `open_at:UtcInstant`; `close_at:UtcInstant`; `kind:Literal["REGULAR","SPECIAL"]`; `schedule_identity_sha256:Sha256`; `partial_official_session_identity_sha256:Sha256` |
| `CurrentSamePassRawMappingReceiptV1` | `contract_version:Literal["current-same-pass-raw-mapping-receipt@v1"]`; `member:CurrentSamePassEquityMemberV1`; `snapshot_schema_version:Literal[1]`; `snapshot_source:Literal["upstox-bod-nse"]`; `observation_date:LocalDate`; `retrieved_at:UtcInstant`; `observation_sha256:Sha256`; `compressed_sha256:Sha256`; `decompressed_sha256:Sha256`; `compressed_byte_count:int[0..4_000_000]`; `decompressed_byte_count:int[0..50_000_000]`; `relative_object_path:SafeRelativePath[1..255]`; `relative_metadata_path:SafeRelativePath[1..255]`; `etag:SafeHeader or None`; `last_modified:SafeHeader or None`; `instrument_key:SafeText[1..128]` **private**; `security_id:Isin` **private**; `resolved_symbol:NseSymbol`; `resolved_exchange:Literal["NSE"]`; `resolved_segment:Literal["NSE_EQ"]`; `resolved_instrument_type:Literal["EQ"]`; `resolved_isin:Isin`; `known_at:UtcInstant`; `raw_mapping_projection_identity_sha256:Sha256` |
| `CurrentSamePassRawCoverageSourceRowV1` | Exact field sequence, semantic types, units, nullability, bounds, and the mutually exclusive verified/provisional projections are frozen in the dedicated table below. |
| `CurrentSamePassRawBarV1` | `isin:Isin`; `session:LocalDate`; `open:PositiveDecimalText`; `high:PositiveDecimalText`; `low:PositiveDecimalText`; `close:PositiveDecimalText`; `volume:UInt64`; `provider:Literal["UPSTOX"]`; `price_basis:Literal["RAW"]`; `interval:Literal["1d-derived-from-retained-1m"]`; `published_at:None`; `known_at:UtcInstant`; `raw_mapping_projection_identity_sha256:Sha256`; `source_receipt_identity_sha256:Sha256`; `schedule_identity_sha256:Sha256`; `raw_source_policy_identity_sha256:Sha256`; `raw_bar_identity_sha256:Sha256` |
| `CurrentSamePassRawGridV1` | `contract_version:Literal["current-same-pass-raw-daily-grid@v1"]`; `schema_identity_sha256:Sha256`; `configuration_identity_sha256:Sha256`; `runtime_code_identity_sha256:Sha256`; `request_identity_sha256:Sha256`; `canonical_cohort_identity_sha256:Sha256`; `schedule_identity_sha256:Sha256`; `latest_completed_session_resolution_identity_sha256:Sha256`; `raw_mapping_set_identity_sha256:Sha256`; `raw_source_policy_identity_sha256:Sha256`; `sessions:tuple[CurrentSamePassRawSessionV1,21]`; `source_rows:tuple[CurrentSamePassRawCoverageSourceRowV1,21*N]`; `bars:tuple[CurrentSamePassRawBarV1,21*N]`; `raw_grid_identity_sha256:Sha256` |
| `PartialCurrentSessionRowV1` | `isin:Isin`; `session:LocalDate`; `as_of:UtcInstant`; `price:PositiveDecimalText`; `cumulative_volume:UInt64`; `provider:Literal["UPSTOX"]`; `price_basis:Literal["RAW"]`; `source_receipt_identity_sha256:Sha256`; `known_at:UtcInstant`; `partial_current_session_row_identity_sha256:Sha256` |
| `PartialCurrentSessionSnapshotV1` | `label:Literal["PARTIAL_CURRENT_SESSION"]`; `state:PartialState`; `session:LocalDate or None`; `as_of:UtcInstant or None`; `known_at:UtcInstant or None`; `rows:tuple[PartialCurrentSessionRowV1,N] or None`; `reasons:tuple[PartialReason,0..6]`; `partial_snapshot_identity_sha256:Sha256` |
| `PrivateCurrentSamePassRawDailyResultV1` | `evidence_state:Literal["OBSERVED","INSUFFICIENT_EVIDENCE"]`; `request_identity_sha256:Sha256`; `canonical_cohort_identity_sha256:Sha256`; `decision_session:LocalDate`; `comparison_session:LocalDate`; `resolved_sessions:tuple[CurrentSamePassRawSessionV1,21]`; `mapping_receipts:tuple[CurrentSamePassRawMappingReceiptV1,N] or None`; `official_active_session:CurrentSamePassPartialOfficialSessionV1 or None`; `raw_grid:CurrentSamePassRawGridV1 or None`; `partial_current_session:PartialCurrentSessionSnapshotV1`; `reasons:tuple[RawDailyReason,0..11]`; `raw_result_identity_sha256:Sha256` |
| `CurrentSamePassDecisionMarketDataRowV1` | `isin:Isin`; `session:LocalDate`; `close:PositiveDecimalText`; `volume:UInt64`; `provider:Literal["UPSTOX"]`; `price_basis:Literal["RAW"]`; `published_at:None`; `known_at:UtcInstant`; `raw_bar_identity_sha256:Sha256`; `row_identity_sha256:Sha256` |
| `CurrentSamePassDecisionMarketDataReportV1` | `contract_version:Literal["current-same-pass-decision-market-data@v1"]`; `schema_identity_sha256:Sha256`; `evidence_state:Literal["OBSERVED","INSUFFICIENT_EVIDENCE"]`; `request_identity_sha256:Sha256`; `canonical_cohort_identity_sha256:Sha256`; `decision_session:LocalDate`; `comparison_session:LocalDate`; `raw_grid_identity_sha256:Sha256 or None`; `rows:tuple[CurrentSamePassDecisionMarketDataRowV1,N] or None`; `partial_current_session:PartialCurrentSessionSnapshotV1`; `reasons:tuple[RawDailyReason,0..11]`; `report_identity_sha256:Sha256` |
| `CurrentSamePassMarketRegimeReportV3` | `contract_version:Literal["current-supplied-cohort-market-regime@v3"]`; `schema_identity_sha256:Sha256`; `calculation_identity_sha256:Sha256`; `runtime_code_identity_sha256:Sha256`; `evidence_state:Literal["OBSERVED","INSUFFICIENT_EVIDENCE"]`; `request_identity_sha256:Sha256`; `canonical_cohort_identity_sha256:Sha256`; `cohort_size:int[1..50]`; `decision_cutoff:UtcInstant`; `decision_session:LocalDate`; `comparison_session:LocalDate`; `market_data_report_identity_sha256:Sha256`; `corporate_action_screen_identity_sha256:Sha256 or None`; `adjusted_handoff_identity_sha256:Sha256 or None`; `regime:Literal["BROAD_ADVANCE","BROAD_DECLINE","MIXED_PARTICIPATION"] or None`; `advances:int[0..50] or None`; `declines:int[0..50] or None`; `unchanged:int[0..50] or None`; `reasons:tuple[MarketRegimeReason,0..14]`; `report_identity_sha256:Sha256` |
| `CurrentSamePassAdjustedDailyCloseFailureProjectionV1` | `contract_version:Literal["provider-neutral-adjusted-daily-close@v2"]`; `plan22_request_identity_sha256:Sha256`; `code:AdjustedFailureCode`; `reason:AdjustedFailureReason`; `failure_projection_identity_sha256:Sha256` |
| `CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1` | `contract_version:Literal["current-same-pass-adjusted-daily-close-not-attempted@v1"]`; `plan22_request_identity_sha256:Sha256`; `evidence_state:Literal["NOT_ATTEMPTED"]`; `reason:Literal["UPSTREAM_INSUFFICIENT_EVIDENCE"]`; `not_attempted_projection_identity_sha256:Sha256` |
| `_CurrentSamePassAdjustedSuccessV1` | `adjusted_handoff:AdjustedDailyCloseHandoffV2`; `adjusted_failure:None`; `adjusted_not_attempted:None` |
| `_CurrentSamePassAdjustedFailureV1` | `adjusted_handoff:None`; `adjusted_failure:CurrentSamePassAdjustedDailyCloseFailureProjectionV1`; `adjusted_not_attempted:None` |
| `_CurrentSamePassAdjustedNotAttemptedV1` | `adjusted_handoff:None`; `adjusted_failure:None`; `adjusted_not_attempted:CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1` |
| `_CurrentSamePassMemberDirectionRowV3` | `isin:Isin`; `exchange:Literal["NSE"]`; `effective_symbol:NseSymbol`; `direction:Literal["ADVANCE","DECLINE","UNCHANGED"]`; `row_identity_sha256:Sha256` |
| `_CurrentSamePassMemberDirectionCandidateV3` | `request_identity_sha256:Sha256`; `raw_grid_identity_sha256:Sha256`; `corporate_action_screen_identity_sha256:Sha256`; `adjusted_handoff_identity_sha256:Sha256`; `market_regime_report_identity_sha256:Sha256`; `canonical_cohort_identity_sha256:Sha256`; `schedule_identity_sha256:Sha256`; `decision_cutoff:UtcInstant`; `rows:tuple[_CurrentSamePassMemberDirectionRowV3,N]`; `direction_candidate_identity_sha256:Sha256` |
| `CurrentSamePassContextComponentLedgerRowV1` | `position:int[0..3]`; `component:Literal["RAW_GRID_V1","CORPORATE_ACTION_SCREEN_V1","ADJUSTED_DAILY_CLOSE_V2","MARKET_REGIME_V3"]`; `contract_version:SafeRevision`; `evidence_state:SafeRevision`; `schema_identity_sha256:Sha256 or None`; `runtime_code_identity_sha256:Sha256 or None`; `primary_identity_sha256:Sha256`; `known_at:UtcInstant or None`; `reasons:tuple[SafeRevision,0..32]`; `ledger_row_identity_sha256:Sha256` |
| `PrivateCurrentSamePassMarketContextObjectV3` | `contract_version:Literal["current-same-pass-market-context-archive@v1"]`; `schema_identity_sha256:Sha256`; `configuration_identity_sha256:Sha256`; `runtime_code_identity_sha256:Sha256`; `request:CurrentSamePassMarketRegimeRequestV3`; `raw_result:PrivateCurrentSamePassRawDailyResultV1`; `market_data_report:CurrentSamePassDecisionMarketDataReportV1`; `corporate_action_screen:PublishedCurrentCorporateActionScreenV1`; `adjusted_handoff:AdjustedDailyCloseHandoffV2 or None`; `adjusted_failure:CurrentSamePassAdjustedDailyCloseFailureProjectionV1 or None`; `adjusted_not_attempted:CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1 or None`; `market_regime_report:CurrentSamePassMarketRegimeReportV3`; `direction_candidate:_CurrentSamePassMemberDirectionCandidateV3 or None`; `component_ledger:tuple[CurrentSamePassContextComponentLedgerRowV1,4]`; `temporal_scope:Literal["CURRENT_SAME_PASS_ONLY"]`; `historical_availability_claim:Literal[false]`; `replay_capability:Literal["NONE"]`; `context_identity_sha256:Sha256`; `context_object_sha256:Sha256` |
| `_CurrentSamePassMarketContextCandidateV3` | `context_object:PrivateCurrentSamePassMarketContextObjectV3`; `candidate_identity_sha256:Sha256`; `_seal:object` **in-memory only, never serialized or hashed; closure-minted registry member with no readable token or capability** |
| `CurrentSamePassArchiveFailureV1` | `contract_version:Literal["current-same-pass-market-context-archive-failure@v1"]`; `evidence_state:Literal["ARCHIVE_FAILED"]`; `reason:Literal["SAME_PASS_CONTEXT_ARCHIVE_FAILED"]`; `request_identity_sha256:Sha256`; `context_identity_sha256:Sha256 or None`; `archive_failure_identity_sha256:Sha256` |
| `CurrentSamePassContextReceiptV1` | `contract_version:Literal["current-same-pass-market-context-receipt@v1"]`; `context_identity_sha256:Sha256`; `context_object_sha256:Sha256`; `context_byte_count:int[1..4_194_304]`; `context_filename:SafeText[1..128]`; `archive_known_at:UtcInstant`; `context_receipt_identity_sha256:Sha256` |
| `CurrentSamePassContextCompletionMarkerV1` | `contract_version:Literal["current-same-pass-market-context-marker@v1"]`; `context_identity_sha256:Sha256`; `context_object_sha256:Sha256`; `context_receipt_identity_sha256:Sha256`; `receipt_sha256:Sha256`; `archive_known_at:UtcInstant`; `completion_marker_identity_sha256:Sha256` |
| `RetainedCurrentSamePassMarketContextV3` | `evidence_state:Literal["RETAINED"]`; `context_identity_sha256:Sha256`; `context_object_sha256:Sha256`; `context_receipt_identity_sha256:Sha256`; `completion_marker_identity_sha256:Sha256`; `archive_known_at:UtcInstant`; `market_data_report:CurrentSamePassDecisionMarketDataReportV1`; `market_regime_report:CurrentSamePassMarketRegimeReportV3`; `partial_current_session:PartialCurrentSessionSnapshotV1`; `retained_context_identity_sha256:Sha256`; `_archive_seal:object` **in-memory only, never serialized or hashed; closure-minted registry member with no readable token or capability** |

After the composed schedule resolves, typed preflight recomputes the sole
public Plan-27 `schedule_identity_sha256` as
`H(schedule_evidence_sha256,schedule_source,schedule_source_release,
timezone:"Asia/Kolkata",coverage_through,ordered 21 full session projections
excluding session identities)` and requires exact equality to the request.
Mismatch is `SCHEDULE_EVIDENCE_CONFLICTED`; no raw acquisition starts.

After authoritative sessions exist, V3 compares a raw result's
`resolved_sessions` byte-for-value to its just-resolved authoritative S0..S20,
requires `comparison_session=S0` and `decision_session=S20`, and rejects a raw
grid unless its `schedule_identity_sha256` equals that validated public Plan-27
identity. Raw acquisition never substitutes a local schedule-identity rehash.

Before sessions exist, V3 returns `CurrentSamePassPreflightFailureV1`; it does
not mint a raw result, market-data report, Market Regime report, context,
receipt, marker, Industry result, or Packet. Its closed reasons are ordered
`SCHEDULE_EVIDENCE_MISSING`, `SCHEDULE_EVIDENCE_STALE`,
`SCHEDULE_EVIDENCE_CONFLICTED`, `SCHEDULE_CONTINUITY_UNPROVEN`, and
`LATEST_COMPLETED_SESSION_UNRESOLVED`. Stored multi-reason tuples MUST already
use that canonical order, and `failure_identity_sha256` MUST hash those exact
stored canonical values; reordered storage or a canonical JSON/identity mismatch
is rejected. No placeholder session, rollback, or inferred date is permitted.

Every V3, Industry, and Packet retained seal is opaque: it has no readable
context, candidate, classification, event, raw, root, receipt, marker, token,
or binding attribute. A closure-private registry maps the exact seal object to
an immutable process-local record. It MAY retain exact private candidate and
upstream objects only because downstream reductions require them; those objects
remain unreachable from seals/results, unexported, and unserialized. Every use
revalidates their canonical hashes and identities. Hostile closure introspection
is outside this slice. Repr and serialization remain redacted.

Context-ledger positions are exactly `0=RAW_GRID_V1`,
`1=CORPORATE_ACTION_SCREEN_V1`, `2=ADJUSTED_DAILY_CLOSE_V2`, and
`3=MARKET_REGIME_V3`.

`CurrentSamePassAdjustedCompositionResultV1` is the closed union
`_CurrentSamePassAdjustedSuccessV1 | _CurrentSamePassAdjustedFailureV1 |
_CurrentSamePassAdjustedNotAttemptedV1`. Exactly one of `adjusted_handoff`,
`adjusted_failure`, and `adjusted_not_attempted` is non-null in both the union
and the retained private context. `AdjustedFailureCode` /
`AdjustedFailureReason` admit only these exact delivered V2 pairs:

| `code` | admitted `reason` literals |
| --- | --- |
| `INVALID_REQUEST` | `REQUEST_SHAPE_INVALID`, `PROVIDER_SELECTION_INVALID`, `PRICE_BASIS_INVALID`, `DECISION_CUTOFF_INVALID`, `SCHEDULE_INVALID`, `DECISION_SESSION_AFTER_CUTOFF`, `SCHEDULE_IDENTITY_INVALID`, `INSTRUMENT_COUNT_INVALID`, `INSTRUMENT_IDENTITY_INVALID`, `SYMBOL_EFFECTIVE_FOR_FACT_WINDOW_REQUIRED`, `MAPPING_IDENTITY_INVALID`, `MAPPING_EFFECTIVE_FOR_FACT_WINDOW_REQUIRED`, `CANONICAL_IDENTITY_OVERLAP`, `EFFECTIVE_SYMBOL_OVERLAP`, `PROVIDER_MAPPING_OVERLAP`, `REQUEST_IDENTITY_INVALID` |
| `UNSUPPORTED_CAPABILITY` | `EXCHANGE_UNSUPPORTED`, `INSTRUMENT_TYPE_UNSUPPORTED`, `SEGMENT_UNSUPPORTED`, `PROVIDER_MAPPING_UNSUPPORTED`, `MAPPING_VERSION_UNSUPPORTED` |
| `INSUFFICIENT_DATA` | `PROVIDER_EMPTY`, `FRAME_INDEX_INVALID`, `FRAME_COVERAGE_INCOMPLETE`, `FRAME_SCHEMA_INVALID` |
| `PROVIDER_FAILURE` | `PROVIDER_CALL_FAILED` |

The context selects exactly one closed row at each fixed position. Positions
0, 1, and 3 each admit success or insufficiency; position 2 additionally admits
the successor-owned deliberate non-call projection:

| Position/component | Success row | Non-success row(s) |
| --- | --- | --- |
| `0 / RAW_GRID_V1` | `contract_version="current-same-pass-raw-daily-grid@v1"`; `evidence_state="OBSERVED"`; schema/runtime equal `raw_grid.schema_identity_sha256` / `raw_grid.runtime_code_identity_sha256`; primary identity is `raw_grid_identity_sha256`; `known_at=max(all bar known_at, non-null partial known_at)`; empty reasons | same contract; schema equals the raw successor schema identity formula and runtime equals the raw component runtime-manifest identity; `evidence_state="INSUFFICIENT_EVIDENCE"`; primary identity is `raw_result_identity_sha256`; `known_at=partial_current_session.known_at` or null; reasons equal `raw_result.reasons` |
| `1 / CORPORATE_ACTION_SCREEN_V1` | `contract_version="current-supplied-cohort-corporate-action-screen@v1"`; `evidence_state="SCREENED"`; schema/runtime equal `public_report.screen_schema_identity_sha256` / `public_report.runtime_code_identity_sha256`; primary identity is `public_report.report_identity_sha256`; `known_at=max(non-null private member provider retrieved_at)`; empty reasons | same exact contract/schema/runtime and primary report identity; `evidence_state="INSUFFICIENT_EVIDENCE"`; `known_at=max(non-null private member provider retrieved_at)` or null; reasons exactly `(CORPORATE_ACTION_SCREEN_INSUFFICIENT,)` |
| `2 / ADJUSTED_DAILY_CLOSE_V2` | `contract_version="provider-neutral-adjusted-daily-close@v2"`; `evidence_state="SUCCESS"`; schema/runtime null because delivered V2 exposes neither identity; primary identity is `handoff_identity_sha256`; `known_at=handoff.retrieved_at`; empty reasons | An invoked exact delivered failure uses the same component contract, null schema/runtime/known-at, `evidence_state=adjusted_failure.code`, primary `failure_projection_identity_sha256`, and exactly `(adjusted_failure.reason,)`. A deliberate non-call after raw or screen insufficiency uses the same component contract, null schema/runtime/known-at, `evidence_state="NOT_ATTEMPTED"`, primary `not_attempted_projection_identity_sha256`, and exactly `("UPSTREAM_INSUFFICIENT_EVIDENCE",)`. The latter is not a Plan-22 result or provider failure. |
| `3 / MARKET_REGIME_V3` | `contract_version="current-supplied-cohort-market-regime@v3"`; `evidence_state="OBSERVED"`; schema/runtime equal the V3 report fields; primary identity is V3 `report_identity_sha256`; `known_at=max(non-null known_at from positions 0..2)`; empty reasons | same exact contract/schema/runtime and primary report identity; `evidence_state="INSUFFICIENT_EVIDENCE"`; `known_at=max(non-null known_at from positions 0..2)` or null; reasons equal the V3 report reasons |

The row state selects the projection; nullability is not inferred. Every row
identity is recalculated from all displayed row fields except its own identity.
An invalid upstream object or any other state/contract/schema/runtime/primary
identity/time/reason/nullability combination is pre-domain structural failure
and no context is minted.

`N` is the request cohort size. Raw sessions are ordered by `position`; source
rows and bars by `(isin, session)`; decision rows and direction rows by `isin`.
`PartialState` and `PartialReason` are exactly the literals and order under
**Optional `PARTIAL_CURRENT_SESSION`**.

State projections are closed. Raw result/report `OBSERVED` requires non-null
grid/rows, empty reasons, `21*N` source rows/bars, and exactly `N` decision
rows; `INSUFFICIENT_EVIDENCE` requires null grid/rows and nonempty reasons.
Market Regime `OBSERVED` requires the admitted `CURRENT_PROSPECTIVE`
adjusted-success union, both upstream identities, non-null regime/counts, empty
reasons, and a non-null direction candidate. Market Regime insufficiency
requires null regime/counts/candidate and nonempty reasons. An adjusted-failure
union requires null `adjusted_handoff_identity_sha256` and retains only its
failure projection in the private context. An adjusted-not-attempted union also
requires null `adjusted_handoff_identity_sha256`, retains only its closed
not-attempted projection, and is valid exactly when raw or screen evidence is
insufficient. Other upstream identities are null only when that upstream
produced no admitted identity. Partial-state nullability remains the separate
closed projection already specified.

#### `CurrentSamePassRawCoverageSourceRowV1` exact schema

The field order below is the sole constructor/dataclass/value-projection order.
`CONDITIONAL` means the closed `source_kind` projection below determines
required versus null; it does not permit caller-selected nullability.

| Field | Semantic type | Unit | Nullability | Closed bound |
| --- | --- | --- | --- | --- |
| `contract_version` | `LITERAL` | `NOT_APPLICABLE` | `REQUIRED` | `Literal["current-same-pass-raw-coverage-source@v1"]` |
| `isin` | `ISIN` | `NOT_APPLICABLE` | `REQUIRED` | `NSE_ISIN_LUHN_12` |
| `session` | `LOCAL_DATE` | `ISO_8601_DATE` | `REQUIRED` | `YYYY_MM_DD` |
| `source_kind` | `LITERAL` | `NOT_APPLICABLE` | `REQUIRED` | `Literal["VERIFIED_MANIFEST","PROVISIONAL_PARTITION"]` |
| `manifest_schema_version` | `INTEGER_OR_NONE` | `VERSION` | `CONDITIONAL` | `None or [1,2147483647]` |
| `plan_provider` | `LITERAL` | `NOT_APPLICABLE` | `REQUIRED` | `Literal["upstox"]` |
| `plan_instrument_key` | `SAFE_TEXT` | `NOT_APPLICABLE` | `REQUIRED` | `UTF8_BYTES[1..128]` |
| `plan_security_id` | `ISIN` | `NOT_APPLICABLE` | `REQUIRED` | `NSE_ISIN_LUHN_12` |
| `plan_symbol` | `NSE_SYMBOL` | `NOT_APPLICABLE` | `REQUIRED` | `UTF8_BYTES[1..64]` |
| `plan_exchange` | `LITERAL` | `NOT_APPLICABLE` | `REQUIRED` | `Literal["NSE"]` |
| `plan_segment` | `LITERAL` | `NOT_APPLICABLE` | `REQUIRED` | `Literal["NSE_EQ"]` |
| `plan_instrument_type` | `LITERAL` | `NOT_APPLICABLE` | `REQUIRED` | `Literal["EQ"]` |
| `plan_interval` | `LITERAL` | `NOT_APPLICABLE` | `REQUIRED` | `Literal["1m"]` |
| `plan_year` | `INTEGER` | `CALENDAR_YEAR` | `REQUIRED` | `[2022..9999]` |
| `plan_month` | `INTEGER` | `CALENDAR_MONTH` | `REQUIRED` | `[1..12]` |
| `plan_from_date` | `LOCAL_DATE` | `ISO_8601_DATE` | `REQUIRED` | `YYYY_MM_DD` in `plan_year`/`plan_month` |
| `plan_to_date` | `LOCAL_DATE` | `ISO_8601_DATE` | `REQUIRED` | `YYYY_MM_DD` in `plan_year`/`plan_month`, not before `plan_from_date` |
| `ingestion_run_id` | `SAFE_TEXT_OR_NONE` | `NOT_APPLICABLE` | `CONDITIONAL` | `None or UTF8_BYTES[1..128]` |
| `candle_schema_version` | `INTEGER_OR_NONE` | `VERSION` | `CONDITIONAL` | `None or [1,2147483647]` |
| `state` | `LITERAL_OR_NONE` | `NOT_APPLICABLE` | `CONDITIONAL` | `None or Literal["VERIFIED"]` |
| `validation_outcome` | `LITERAL_OR_NONE` | `NOT_APPLICABLE` | `CONDITIONAL` | `None or Literal["PASSED"]` |
| `validation_policy_version` | `SAFE_REVISION_OR_NONE` | `NOT_APPLICABLE` | `CONDITIONAL` | `None or UTF8_BYTES[1..128]` |
| `actual_from_ts` | `UTC_INSTANT` | `UTC` | `REQUIRED` | `AWARE_UTC_MICROSECOND` |
| `actual_to_ts` | `UTC_INSTANT` | `UTC` | `REQUIRED` | `AWARE_UTC_MICROSECOND`, not before `actual_from_ts` |
| `row_count` | `INTEGER` | `ROWS` | `REQUIRED` | `[1,2147483647]`; provisional projection narrows to `[1,10000]` |
| `checksum_sha256` | `SHA256` | `NOT_APPLICABLE` | `REQUIRED` | `LOWERCASE_64_HEX` |
| `canonical_path` | `SAFE_RELATIVE_PATH` | `NOT_APPLICABLE` | `REQUIRED` | `UTF8_BYTES[1..1024]`; provisional path must be the retained legacy or checksum-addressed projection of the exact plan/cutoff/schedule/checksum |
| `source_version` | `SAFE_REVISION_OR_NONE` | `NOT_APPLICABLE` | `CONDITIONAL` | `None or UTF8_BYTES[1..128]` |
| `manifest_created_at` | `UTC_INSTANT_OR_NONE` | `UTC` | `CONDITIONAL` | `None or AWARE_UTC_MICROSECOND` |
| `attempt_started_at` | `UTC_INSTANT_OR_NONE` | `UTC` | `CONDITIONAL` | `None or AWARE_UTC_MICROSECOND` |
| `manifest_updated_at` | `UTC_INSTANT_OR_NONE` | `UTC` | `CONDITIONAL` | `None or AWARE_UTC_MICROSECOND` |
| `failure_category` | `EXACT_NONE` | `NOT_APPLICABLE` | `REQUIRED` | `LITERAL_NONE` |
| `coverage_state` | `LITERAL` | `NOT_APPLICABLE` | `REQUIRED` | `Literal["VERIFIED","PROVISIONAL"]` selected by `source_kind` |
| `schedule_digest_sha256` | `SHA256` | `NOT_APPLICABLE` | `REQUIRED` | `LOWERCASE_64_HEX` |
| `evidence_published_at` | `UTC_INSTANT_OR_NONE` | `UTC` | `CONDITIONAL` | `None or AWARE_UTC_MICROSECOND` |
| `evidence_known_at` | `UTC_INSTANT_OR_NONE` | `UTC` | `CONDITIONAL` | `None or AWARE_UTC_MICROSECOND` |
| `provisional_schema_version` | `INTEGER_OR_NONE` | `VERSION` | `CONDITIONAL` | `None or Literal[1]` |
| `provisional_cutoff` | `UTC_INSTANT_OR_NONE` | `UTC` | `CONDITIONAL` | `None or AWARE_UTC_MINUTE`; when present equals `actual_to_ts` |
| `provisional_session_complete` | `BOOLEAN_OR_NONE` | `NOT_APPLICABLE` | `CONDITIONAL` | `None or BOOLEAN` |
| `provisional_byte_size` | `INTEGER_OR_NONE` | `BYTES` | `CONDITIONAL` | `None or [1,67108864]` |
| `provisional_instrument_snapshot_digest_sha256` | `SHA256_OR_NONE` | `NOT_APPLICABLE` | `CONDITIONAL` | `None or LOWERCASE_64_HEX` |
| `provisional_instrument_snapshot_retrieved_at` | `UTC_INSTANT_OR_NONE` | `UTC` | `CONDITIONAL` | `None or AWARE_UTC_MICROSECOND` |
| `provisional_historical_attempt_count` | `INTEGER_OR_NONE` | `ATTEMPTS` | `CONDITIONAL` | `None or [0,1]` |
| `provisional_intraday_attempt_count` | `INTEGER_OR_NONE` | `ATTEMPTS` | `CONDITIONAL` | `None or [0,1]` |
| `query_completed_at` | `UTC_INSTANT` | `UTC` | `REQUIRED` | `AWARE_UTC_MICROSECOND` |
| `source_receipt_identity_sha256` | `SHA256` | `NOT_APPLICABLE` | `REQUIRED` | `LOWERCASE_64_HEX` |

The state projection is closed:

| `source_kind` | Required projection | Null projection | Additional bounds |
| --- | --- | --- | --- |
| `VERIFIED_MANIFEST` | `manifest_schema_version`, `ingestion_run_id`, `candle_schema_version`, `state="VERIFIED"`, `validation_outcome="PASSED"`, `validation_policy_version`, `source_version`, `manifest_created_at`, `attempt_started_at`, `manifest_updated_at`, `coverage_state="VERIFIED"` | `evidence_published_at`, `evidence_known_at`, and every `provisional_*` field | `row_count=[1,2147483647]` |
| `PROVISIONAL_PARTITION` | `coverage_state="PROVISIONAL"`, equal non-null `evidence_published_at=evidence_known_at`, `provisional_schema_version=1`, `provisional_cutoff`, `provisional_session_complete`, `provisional_byte_size`, `provisional_instrument_snapshot_digest_sha256`, `provisional_instrument_snapshot_retrieved_at`, `provisional_historical_attempt_count`, `provisional_intraday_attempt_count` | every verified-manifest-only field from `manifest_schema_version` through `manifest_updated_at` | `row_count=[1,10000]`; `provisional_byte_size=[1,67108864]`; both attempt counts `[0,1]`; cutoff not after publication |

### Industry Participation V2 types

| Type | Exact ordered fields |
| --- | --- |
| `CurrentIndustryCountV2` | `industry:SafeText[1..512]`; `member_count:int[1..50]`; `advances:int[0..50]`; `declines:int[0..50]`; `unchanged:int[0..50]`; `row_identity_sha256:Sha256` |
| `CurrentIndustryParticipationReportV2` | `contract_version:Literal["current-supplied-cohort-industry-participation@v2"]`; `schema_identity_sha256:Sha256`; `calculation_identity_sha256:Sha256`; `runtime_code_identity_sha256:Sha256`; `evidence_state:Literal["OBSERVED"]`; `market_regime_report_identity_sha256:Sha256`; `direction_candidate_identity_sha256:Sha256`; `classification_input_identity_sha256:Sha256`; `artifact_sha256:Sha256`; `snapshot_identity_sha256:Sha256`; `archive_identity_sha256:Sha256`; `archive_receipt_identity_sha256:Sha256`; `retained_classification_identity_sha256:Sha256`; `canonical_cohort_identity_sha256:Sha256`; `cohort_size:int[1..50]`; `decision_session:LocalDate`; `comparison_session:LocalDate`; `decision_cutoff:UtcInstant`; `source_url:SafeText[1..2048]`; `source_attribution:Literal["NSE_INDICES"]`; `classification_tier:Literal["INDUSTRY"]`; `artifact_revision:SafeRevision`; `known_at:UtcInstant`; publisher fields `None`; `industries:tuple[CurrentIndustryCountV2,1..N]`; `reasons:tuple[(),0]`; `report_identity_sha256:Sha256`; `_reducer_seal:object` **in-memory only, never serialized or hashed** |
| `CurrentIndustryParticipationFailureV2` | `contract_version:Literal["current-supplied-cohort-industry-participation-failure@v2"]`; `evidence_state:Literal["MALFORMED_EVIDENCE","UNSUPPORTED_CAPABILITY","INSUFFICIENT_EVIDENCE"]`; `canonical_cohort_identity_sha256:Sha256`; `cohort_size:int[1..50]`; `decision_session:LocalDate`; `decision_cutoff:UtcInstant`; `market_regime_report_identity_sha256:Sha256 or None`; `classification_identity_sha256:Sha256 or None`; `known_at:UtcInstant or None`; `industries:None`; `reasons:tuple[IndustryReason,1..13]`; `failure_identity_sha256:Sha256`; `_reducer_seal:object` **in-memory only, never serialized or hashed** |

Industry rows are unique and ascending by exact `industry`.
`sum(member_count)=cohort_size`, and row/count sums equal the V3 public counts.
The failure has no row, member direction, private classification, or source
narrative projection.

### Research Packet V2 types

| Type | Exact ordered fields |
| --- | --- |
| `CurrentSuppliedCohortResearchPacketRequestV2` | `contract_version:Literal["current-supplied-cohort-research-packet@v2"]`; `decision_cutoff:UtcInstant`; `cohort_selected_at:UtcInstant`; `members:tuple[CurrentSamePassEquityMemberV1,1..50]`; `plan21_cohort_identity_sha256:Sha256`; `canonical_cohort_identity_sha256:Sha256`; `market_context_identity_sha256:Sha256`; `request_identity_sha256:Sha256` |
| `CurrentResearchPacketComponentLedgerRowV2` | `position:int[0..3]`; `component:PacketComponent`; `contract_version:SafeRevision or None`; `evidence_state:SafeRevision`; `schema_identity_sha256:Sha256 or None`; `runtime_code_identity_sha256:Sha256 or None`; `primary_identity_sha256:Sha256 or None`; `failure_cohort_size:int[1..50] or None`; `identity_bindings:tuple[NamedIdentityV2,0..16]`; `known_at:UtcInstant or None`; `component_reasons:tuple[SafeRevision,0..32]`; `packet_reasons:tuple[PacketReason,0..13]`; `ledger_row_identity_sha256:Sha256` |
| `CurrentResearchPacketSourceAttributionRowV2` | `position:int[0..3]`; `component:PacketComponent`; `source_state:Literal["BOUND","UNAVAILABLE"]`; `provider_id:SafeRevision or None`; `source_name:SafeText[1..128] or None`; `source_url:SafeText[1..2048] or None`; `source_release:SafeRevision or None`; `price_basis:Literal["RAW","ADJUSTED"] or None`; `publisher_published_at:UtcInstant or None`; `known_at:UtcInstant or None`; `licence_policy_identity:SafeRevision or None`; `primary_identity_sha256:Sha256 or None`; `source_row_identity_sha256:Sha256` |
| `CurrentResearchPacketMarketDataProjectionV2` | `decision_session:LocalDate`; `rows:tuple[CurrentSamePassDecisionMarketDataRowV1,N]`; `projection_identity_sha256:Sha256` |
| `CurrentResearchPacketMarketRegimeProjectionV2` | `decision_session:LocalDate`; `comparison_session:LocalDate`; `regime:Literal["BROAD_ADVANCE","BROAD_DECLINE","MIXED_PARTICIPATION"]`; `advances:int[0..50]`; `declines:int[0..50]`; `unchanged:int[0..50]`; `projection_identity_sha256:Sha256` |
| `CurrentResearchPacketIndustryProjectionV2` | `classification_tier:Literal["INDUSTRY"]`; `industries:tuple[CurrentIndustryCountV2,1..N]`; `known_at:UtcInstant`; `projection_identity_sha256:Sha256` |
| `CurrentResearchPacketRedactedEventNoticeV2` | `observation_identity_sha256:Sha256`; `deduplication_identity_sha256:Sha256` |
| `CurrentResearchPacketRedactedEventMemberV2` | `isin:Isin`; `symbol:NseSymbol`; `outcome:Literal["NOTICES_ADMITTED","NO_MATCHING_NOTICE_IN_SNAPSHOT"]`; `notices:tuple[CurrentResearchPacketRedactedEventNoticeV2,0..10_000]` |
| `CurrentResearchPacketEventProjectionV2` | `known_at:UtcInstant`; `members:tuple[CurrentResearchPacketRedactedEventMemberV2,N]`; `projection_identity_sha256:Sha256` |
| `CurrentResearchPacketAIObservedV2` | `evidence_state:Literal["OBSERVED"]`; `market_data:CurrentResearchPacketMarketDataProjectionV2`; `market_regime:CurrentResearchPacketMarketRegimeProjectionV2`; `industry_participation:CurrentResearchPacketIndustryProjectionV2`; `event_notices:CurrentResearchPacketEventProjectionV2`; `partial_current_session:PartialCurrentSessionSnapshotV1`; `consumer_disposition:None`; `ai_projection_identity_sha256:Sha256` |
| `CurrentResearchPacketAIInsufficientV2` | `evidence_state:Literal["INSUFFICIENT_EVIDENCE"]`; `market_data:None`; `market_regime:None`; `industry_participation:None`; `event_notices:None`; `partial_current_session:None`; `consumer_disposition:Literal["INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"]`; `ai_projection_identity_sha256:Sha256` |
| `CurrentSuppliedCohortResearchPacketV2` | `contract_version:Literal["current-supplied-cohort-research-packet@v2"]`; `schema_identity_sha256:Sha256`; `configuration_identity_sha256:Sha256`; `runtime_code_identity_sha256:Sha256`; `request_identity_sha256:Sha256`; `canonical_cohort_identity_sha256:Sha256`; `market_context_identity_sha256:Sha256`; `decision_cutoff:UtcInstant`; `decision_session:LocalDate`; `component_known_at_max:UtcInstant or None`; `evidence_state:Literal["OBSERVED","INSUFFICIENT_EVIDENCE"]`; `component_ledger:tuple[CurrentResearchPacketComponentLedgerRowV2,4]`; `source_attribution:tuple[CurrentResearchPacketSourceAttributionRowV2,4]`; `reasons:tuple[PacketReason,0..13]`; `ai_projection:CurrentResearchPacketAIObservedV2 or CurrentResearchPacketAIInsufficientV2`; `packet_identity_sha256:Sha256`; `packet_object_sha256:Sha256` |
| `_CurrentSuppliedCohortResearchPacketCandidateV2` | `packet:CurrentSuppliedCohortResearchPacketV2`; `candidate_identity_sha256:Sha256`; `market_context:RetainedCurrentSamePassMarketContextV3`; `industry_participation:CurrentIndustryParticipationReportV2 or CurrentIndustryParticipationFailureV2`; `event_notices:RetainedCurrentEventNoticeSnapshotV1 or CurrentEventNoticeFailureV1`; `_seal:object`; upstream fields and `_seal` are **in-memory only, never serialized or hashed; `_seal` is a closure-minted registry member with no readable token or capability** |
| `CurrentResearchPacketArchiveFailureV2` | `contract_version:Literal["current-supplied-cohort-research-packet-archive-failure@v2"]`; `evidence_state:Literal["ARCHIVE_FAILED"]`; `reason:Literal["RESEARCH_PACKET_ARCHIVE_FAILED"]`; `request_identity_sha256:Sha256`; `packet_identity_sha256:Sha256 or None`; `archive_failure_identity_sha256:Sha256` |
| `CurrentResearchPacketReceiptV2` | `contract_version:Literal["current-supplied-cohort-research-packet-receipt@v2"]`; `packet_identity_sha256:Sha256`; `packet_object_sha256:Sha256`; `packet_byte_count:int[1..37_748_736]`; `packet_filename:SafeText[1..128]`; `archive_known_at:UtcInstant`; `receipt_identity_sha256:Sha256` |
| `CurrentResearchPacketCompletionMarkerV2` | `contract_version:Literal["current-supplied-cohort-research-packet-marker@v2"]`; `packet_identity_sha256:Sha256`; `packet_object_sha256:Sha256`; `receipt_identity_sha256:Sha256`; `receipt_sha256:Sha256`; `archive_known_at:UtcInstant`; `completion_marker_identity_sha256:Sha256` |
| `RetainedCurrentSuppliedCohortResearchPacketV2` | `evidence_state:Literal["RETAINED"]`; `packet:CurrentSuppliedCohortResearchPacketV2`; `receipt_identity_sha256:Sha256`; `completion_marker_identity_sha256:Sha256`; `archive_known_at:UtcInstant`; `retained_identity_sha256:Sha256`; `_archive_seal:object` **in-memory only, never serialized or hashed; closure-minted registry member with no readable token or capability** |

Packet adoption requires the exact current candidate capability, not equality
of candidate or packet values. A returned retained value is accepted only after
the closure revalidates its exact candidate/public packet against the current
live lease and seal-bound archive root; a prior no-I/O result and deleted or
corrupt archive files are rejected.

`PacketComponent` is exactly, in order,
`MARKET_DATA_SAME_PASS_V1`, `MARKET_REGIME_V3`,
`INDUSTRY_PARTICIPATION_V2`, `EVENT_NOTICES_V1`.
`NamedIdentityV2` is the closed two-field object
`name:SafeRevision, identity_sha256:Sha256`, ordered by the component-specific
name order. Source rows use `BOUND` only with all component-applicable source
fields populated and `UNAVAILABLE` only with all source detail fields null;
opaque local receipt identities are provenance bindings, not claims of
publisher authenticity.

The component ledger admits 14 exact behavioral projections. The Packet schema
groups both event-failure origins under `typed_failure`; no open state or
component-specific ad hoc row exists:

| Component | Projection | Exact ledger constraints |
| --- | --- | --- |
| `MARKET_DATA_SAME_PASS_V1` | success | `contract_version="current-same-pass-decision-market-data@v1"`; `evidence_state="OBSERVED"`; schema/runtime and primary Market-data report identities non-null; `failure_cohort_size=null`; bindings exactly `[CONTEXT,RAW_RESULT,RAW_GRID,MARKET_DATA_REPORT]`; `known_at=max(decision rows known_at, non-null partial known_at)`; empty component/packet reasons |
| `MARKET_DATA_SAME_PASS_V1` | natural insufficiency | same contract/schema/runtime; `evidence_state="INSUFFICIENT_EVIDENCE"`; primary report identity non-null; `failure_cohort_size=N`; bindings exactly `[CONTEXT,RAW_RESULT,MARKET_DATA_REPORT]`; `known_at` equals context position 0 `known_at`; exact raw reasons; packet reasons contain `MARKET_DATA_UNAVAILABLE` plus independently applicable cross-component reasons |
| `MARKET_DATA_SAME_PASS_V1` | invalid | contract/schema/runtime/primary/failure size/known-at null; `evidence_state="PACKET_INVALID_COMPONENT"`; no bindings; component reason exactly `PACKET_INVALID_COMPONENT`; packet reason exactly `COMPONENT_IDENTITY_INVALID` |
| `MARKET_REGIME_V3` | success | V3 contract/schema/runtime; `evidence_state="OBSERVED"`; primary V3 report identity; `failure_cohort_size=null`; bindings exactly `[CONTEXT,MARKET_REGIME_REPORT,DIRECTION_CANDIDATE]`; `known_at` equals context position 3 `known_at`; empty reasons |
| `MARKET_REGIME_V3` | natural insufficiency after an adjusted attempt | same contract/schema/runtime; `evidence_state="INSUFFICIENT_EVIDENCE"`; primary report identity; `failure_cohort_size=N`; bindings exactly `[CONTEXT,MARKET_REGIME_REPORT]`; `known_at` equals context position 3 `known_at`; exact V3 reasons; packet reasons contain `MARKET_REGIME_UNAVAILABLE` plus independently applicable cross-component reasons |
| `MARKET_REGIME_V3` | natural adjusted not attempted | same report contract/schema/runtime/state/primary/failure size/known-at; bindings exactly `[CONTEXT,MARKET_REGIME_REPORT,ADJUSTED_NOT_ATTEMPTED]`, with the last identity equal to the closure-validated context position-2 primary identity; component reasons are the exact V3 reasons followed by `UPSTREAM_INSUFFICIENT_EVIDENCE`; packet reasons contain `MARKET_REGIME_UNAVAILABLE` plus independently applicable mappings, with no provider-failure reason |
| `MARKET_REGIME_V3` | invalid | same invalid projection rule as Market data, with this component name |
| `INDUSTRY_PARTICIPATION_V2` | success | V2 contract/schema/runtime; `evidence_state="OBSERVED"`; primary Industry report identity; `failure_cohort_size=null`; bindings exactly `[MARKET_REGIME_REPORT,DIRECTION_CANDIDATE,CLASSIFICATION_INPUT,ARTIFACT,SNAPSHOT,ARCHIVE,ARCHIVE_RECEIPT,RETAINED_CLASSIFICATION,INDUSTRY_REPORT]`; `known_at=report.known_at`; empty reasons |
| `INDUSTRY_PARTICIPATION_V2` | typed failure | failure contract; state exactly the V2 failure state; schema/runtime null when not present on the failure; primary identity is its `failure_identity_sha256`; `failure_cohort_size=N`; bindings exactly `[INDUSTRY_FAILURE]`; `known_at` is the exact admitted classification time or null when unavailable; exact Industry reasons; packet reasons contain `INDUSTRY_PARTICIPATION_UNAVAILABLE` plus independently applicable cross-component reasons |
| `INDUSTRY_PARTICIPATION_V2` | invalid | same invalid projection rule, with this component name |
| `EVENT_NOTICES_V1` | success | delivered V1 contract/schema/runtime; `evidence_state="RETAINED"`; primary retained identity; `failure_cohort_size=null`; bindings exactly `[ARTIFACT,SNAPSHOT,ARCHIVE,RECEIPT,RETAINED]`; `known_at=retained.known_at`; empty reasons |
| `EVENT_NOTICES_V1` | delivered typed failure | contract/schema/runtime/primary null because the delivered failure exposes none; exact delivered failure state; `failure_cohort_size=N`; bindings exactly `[FAILURE_PROJECTION]`, whose identity is `H({component,state,reasons})`; `known_at=null`; exact delivered reasons; packet reasons contain `EVENT_NOTICES_UNAVAILABLE` plus independently applicable cross-component reasons |
| `EVENT_NOTICES_V1` | retained stale/future temporal failure | `contract_version`, schema, runtime, ledger primary, and `known_at` are null; `evidence_state="INSUFFICIENT_EVIDENCE"`; `failure_cohort_size=N`; the privacy-safe `[FAILURE_PROJECTION]` identity binds retained identity, original `known_at`, source date, artifact, snapshot, archive, and receipt identities without narrative/source-path publication; exact stale/future component reason and mapped packet reason |
| `EVENT_NOTICES_V1` | invalid | same invalid projection rule, with this component name |

Positions are fixed by `PacketComponent`. Every binding name above is a
`NamedIdentityV2` and its identity is revalidated against the component before
the ledger row is hashed.

The matching source-attribution projection is also closed:

| Component success | Exact `BOUND` source fields |
| --- | --- |
| `MARKET_DATA_SAME_PASS_V1` | `provider_id="UPSTOX"`; `source_name="UPSTOX_RETAINED_RAW_DAILY"`; `source_url=null`; `source_release=raw_source_policy_identity_sha256`; `price_basis="RAW"`; `publisher_published_at=null` because verified retained coverage exposes no publication time; `known_at=ledger.known_at`; `licence_policy_identity=null`; `primary_identity_sha256=market-data report identity` |
| `MARKET_REGIME_V3` | `provider_id=null`; `source_name="DETERMINISTIC_SAME_PASS_MARKET_REGIME"`; `source_url=null`; `source_release="current-supplied-cohort-market-regime@v3"`; `price_basis=null`; `publisher_published_at=null`; `known_at=ledger.known_at`; `licence_policy_identity=null`; `primary_identity_sha256=V3 report identity` |
| `INDUSTRY_PARTICIPATION_V2` | `provider_id="NSE_INDICES"`; `source_name="NSE_INDICES_INDUSTRY_CLASSIFICATION"`; exact report `source_url`; `source_release=artifact_revision`; `price_basis=null`; all publisher times remain null; `known_at=report.known_at`; `licence_policy_identity=null` because Plan 24 exposes no such field; `primary_identity_sha256=Industry report identity` |
| `EVENT_NOTICES_V1` | `provider_id="NSE"`; `source_name="NSE_EQUITY_CORPORATE_ANNOUNCEMENTS"`; exact retained `source_url`; `source_release=source_filename`; `price_basis=null`; `publisher_published_at=null`; `known_at=retained.known_at`; exact retained `licence_policy_identity`; `primary_identity_sha256=retained identity` |

Every natural failure or invalid component uses `source_state="UNAVAILABLE"` and
null source narrative/provider/time fields. Primary identity is also null except
for a validated retained stale/future event snapshot, whose source row carries
only the same privacy-safe failure-projection identity used by its ledger
binding. This does not erase the component ledger's private reason or identity
bindings. The packet source row never republishes a provider row, mapping,
Industry member row, event attachment, raw path, or event narrative.

An observed packet requires four success ledger rows, four bound source rows,
empty reasons, `component_known_at_max <= decision_cutoff`, and
`CurrentResearchPacketAIObservedV2`. Any packet reason requires the insufficient
AI projection; all five fact fields are null and the mandatory disposition is
non-null. Archive failure is outside the domain packet and exposes no
AI projection.

### Exact bridge projections and equality

The request constructor deterministically creates these closed values before
any effect:

1. **Plan 21 reduced manifest:** exact
   `CurrentSuppliedCohortManifestV1` value
   `{contract_version:"current-supplied-cohort-market-data@v1",
   selected_at:cohort_selected_at,
   members:[{isin,symbol:effective_symbol}]}` with members sorted by
   `(isin,symbol)`. Its SHA-256 is
   `plan21_cohort_identity_sha256`.
2. **Plan 22 full member and independent schedule/request identities:** exact
   `{isin,exchange,instrument_type,segment,effective_symbol,valid_from,
   valid_through,provider_symbol,mapping_version,mapping_valid_from,
   mapping_valid_through,mapping_identity}` for every request member. The
   delivered `adjusted_daily_schedule_identity_v2` result is carried only as
   `plan22_schedule_identity_sha256`. It is separately recomputed from the exact
   21 dates, S20 official close, schedule evidence digest, source, and release
   after typed preflight; it MUST NOT equal by alias or definition the public
   Plan-27 `schedule_identity_sha256`.
   Before calculating the V3 request identity, the constructor computes
   `plan22_request_identity_sha256` by calling the delivered
   `adjusted_daily_request_identity_v2` with
   `cohort_identity_sha256=canonical_cohort_identity_sha256`, the exact
   `decision_cutoff`,
   `schedule_identity_sha256=plan22_schedule_identity_sha256`, and the
   canonically ordered full Plan-22 members. The bridge request passes
   `plan22_schedule_identity_sha256` as its
   `plan21_schedule.schedule_identity_sha256`; it never passes or aliases the
   public Plan-27 schedule identity. `plan22_request_identity_sha256` is not,
   and must never equal by definition or field alias,
   `CurrentSamePassMarketRegimeRequestV3.request_identity_sha256`.

An exact delivered success freezes handoff equality, not merely hash syntax:
`handoff.contract_version == "provider-neutral-adjusted-daily-close@v2"`,
`handoff.provider_id == "YFINANCE"`, `handoff.price_basis == "ADJUSTED"`,
`handoff.provider_source == "yfinance==1.6.0"`, and
`handoff.temporal_label == "CURRENT_PROSPECTIVE"` exactly when
`handoff.retrieved_at <= decision_cutoff`, otherwise exactly
`"REVISED_NON_PIT"`. It also requires
`handoff.cohort_identity_sha256 == canonical_cohort_identity_sha256`,
`handoff.request_identity_sha256 == plan22_request_identity_sha256`, and
`handoff.decision_cutoff == decision_cutoff`. Every schedule evidence/source/
release/official-close/session/identity field equals the bridge, comparison and
decision sessions equal `S[0]` and `S[20]`, and every handoff member equals the
full canonically ordered Plan-22 member projection plus only its exact S0/S20
facts. `adjusted_daily_close_handoff_identity_v2(handoff)` must equal
`handoff.handoff_identity_sha256`. Equality to the V3 request identity is
rejected. The union retains either exact temporal label; only
`CURRENT_PROSPECTIVE` is admitted to the V3 calculation.

3. **Plan 24 reduced member:** exact
   `{isin,exchange,effective_symbol}` plus the same
   `canonical_cohort_identity_sha256`, cohort size, decision/comparison
   sessions, and cutoff used by the sealed direction candidate and retained
   classification. There is no symbol fallback or denominator reduction.

4. **Plan 25 full member:** exact
   `{isin,exchange,listed_equity_segment:instrument_type,
   symbol:effective_symbol,effective_from:valid_from,
   effective_through:valid_through,provider_mapping_revision}` plus the same
   `canonical_cohort_identity_sha256` and cohort size.
   `listed_equity_segment == instrument_type == "EQUITY"` is frozen equality.
   It is never derived from `segment`, whose distinct Plan-22/Upstox literal is
   `"EQ"`.

Full-member equality means exact value and order equality of every request
field. Reduced equality means exact equality of the displayed projection for
all and only request members; it never asserts that omitted fields are equal.
The Plan-21 selected time is exactly `cohort_selected_at`; it is not
`decision_cutoff`, invocation time, or archive time. `cohort_selected_at`, all
four bridge bytes, and their identities are stable across an exact retry.
Changed selected time, member field, Plan-22 mapping field, Plan-25
`provider_mapping_revision`, schedule, or cutoff creates a new request.

Effect order is fixed. After schedule preflight succeeds, raw mapping and raw
acquisition run first, then Plan-21 admission. Only an `OBSERVED` exact raw
result plus an exact screened Plan-21 result permits one
`acquire_adjusted_daily_close_v2` call with the frozen bridge. Raw or screen
insufficiency performs zero yfinance/Plan-22 calls and creates the successor-owned
`CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1`; it is not converted
to any delivered failure code. An exact `AdjustedDailyCloseSuccessV2` supplies
its non-null handoff; an exact invoked `AdjustedDailyCloseFailure` supplies the
closed failure projection bound to `plan22_request_identity_sha256` and forces
`ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID`. Wrong result type, code/reason pair, or
projection identity is pre-domain structural failure. The pure builder receives
the closed three-state union by value, revalidates the state against raw/screen
evidence, never receives an `AdjustedDailyDownloadAdapter`, and performs no
network work or replacement acquisition during archive retry.

## Market Regime V3 API and comparability

Contract literals are:

```text
current-same-pass-raw-daily-grid@v1
current-supplied-cohort-market-regime@v3
current-supplied-cohort-market-regime-schema@v3
current-supplied-cohort-market-regime-calculation@v3
current-same-pass-market-context-archive@v1
```

The public/effect surfaces are:

```python
class CurrentSamePassMarketContextArchivePortV1(Protocol):
    def archive_exact(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        candidate: _CurrentSamePassMarketContextCandidateV3,
        lease: StorageRootLease,
        *,
        trusted_clock: _TrustedClockV1 | None = None,
    ) -> RetainedCurrentSamePassMarketContextV3 | CurrentSamePassArchiveFailureV1: ...


class FileCurrentSamePassMarketContextArchiveV1: ...


class RetainedCurrentSamePassMarketContextV3:
    @property
    def market_data_report(self) -> CurrentSamePassDecisionMarketDataReportV1: ...
    @property
    def market_regime_report(self) -> CurrentSamePassMarketRegimeReportV3: ...
    @property
    def partial_current_session(self) -> PartialCurrentSessionSnapshotV1: ...
    @property
    def retention(self) -> dict[str, object]: ...
    def canonical_json_bytes(self) -> bytes: ...


class CurrentSamePassArchiveFailureV1: ...


def acquire_build_and_retain_current_supplied_cohort_market_regime_v3(
    request: CurrentSamePassMarketRegimeRequestV3,
    schedule_store: ScheduleEvidenceStore,
    raw_daily: CurrentSamePassRawDailyPortV1,
    corporate_action_resolver: CurrentSuppliedCohortCorporateActionScreenResolverV1,
    adjusted_provider: AdjustedDailyDownloadAdapter,
    archive: CurrentSamePassMarketContextArchivePortV1,
    lease: StorageRootLease,
    *,
    clock: _TrustedClockV1 | None = None,
) -> (
    RetainedCurrentSamePassMarketContextV3
    | CurrentSamePassArchiveFailureV1
    | CurrentSamePassPreflightFailureV1
): ...


def build_and_retain_current_supplied_cohort_market_regime_v3(
    request: CurrentSamePassMarketRegimeRequestV3,
    schedule_store: ScheduleEvidenceStore,
    raw_daily: CurrentSamePassRawDailyPortV1,
    corporate_action_resolver: CurrentSuppliedCohortCorporateActionScreenResolverV1,
    adjusted: CurrentSamePassAdjustedCompositionResultV1,
    archive: CurrentSamePassMarketContextArchivePortV1,
    lease: StorageRootLease,
    *,
    trusted_clock: _TrustedClockV1 | None = None,
) -> RetainedCurrentSamePassMarketContextV3 | CurrentSamePassArchiveFailureV1: ...
```

The builder returns a retained context for both `OBSERVED` and admitted
`INSUFFICIENT_EVIDENCE`. After candidate creation, the archive-port union is
closed: it returns only an exactly adopted retained context or an exactly
revalidated archive failure whose literal fields, request identity, candidate
context identity, and failure identity are exact. Any other result, including a
private context or candidate, raises and never becomes a public return. Wrong
exact types, unsupported contract/schema, unsafe lease/root, runtime-identity
failure, or structural bounds fail before a domain context. Archive failure
exposes no facts.

Comparability reuses exact delivered boundaries:

- `PublishedCurrentCorporateActionScreenV1` and
  `published_current_corporate_action_screen_is_exact_valid_v1`, bound to the
  same cohort, S0, S20, cutoff, schedule, and ISINs. Plan 21 remains a
  nonexhaustive provider screen, never authoritative no-action proof.
- exact delivered `AdjustedDailyCloseSuccessV2` or `AdjustedDailyCloseFailure`,
  acquired once by the outer composition only after exact raw observation and
  Plan-21 screening. Success is admitted only as `YFINANCE` / `ADJUSTED` /
  `CURRENT_PROSPECTIVE` with exact full-member mapping, S0/S20, cutoff, schedule,
  `handoff.request_identity_sha256 == plan22_request_identity_sha256`, and
  handoff identity. It is never compared to the distinct V3 request identity.
  `REVISED_NON_PIT` or an invoked exact failure projection is retained
  insufficiency. Raw or screen insufficiency instead retains the closed
  `NOT_ATTEMPTED` projection with no adjusted handoff, failure, provider call,
  or adjusted source attribution. The builder has no adjusted provider/effect
  and archive retry never reacquires.
- No adjusted value populates an Upstox raw bar. Raw and adjusted S0/S20
  directions MUST agree per member. A disagreement is whole-result
  insufficiency.

The aggregate rule remains inclusive integer arithmetic:

```text
BROAD_ADVANCE if advances * 5 >= cohort_size * 3
else BROAD_DECLINE if declines * 5 >= cohort_size * 3
else MIXED_PARTICIPATION
```

`advances + declines + unchanged == cohort_size`; no reduced denominator exists.
Partial current-session values are not read by this calculation.

## Private same-pass Industry candidate and Industry V2

Market Regime V3 calculates member direction once and creates the prearchive
`_CurrentSamePassMemberDirectionCandidateV3`. It is sorted by ISIN, contains
exactly `cohort_size` directions, reconciles to public counts, and binds only
request/grid/screen/adjusted/report/cohort/schedule/cutoff identities. It does
not bind a context, receipt, marker, retained identity, archive time, or seal.
The candidate is embedded by value in the private context object and therefore
enters `context_identity_sha256` and `context_object_sha256`. Successful archive
completion attaches only a nonserializable opaque in-memory `_archive_seal`; it
does not mint or mutate a fact, timestamp, candidate, context byte, or digest.
Industry V2 obtains only the closure-validated minimal direction projection; it
does not traverse a retained seal or retain the private context or
classification. Packet V2 receives only exact public V3 reports plus a
closure-validated identity/time projection, never the private raw payload.
There is no public constructor, parser, serializer, package-root export,
CLI/API/MCP field, or caller-supplied substitute.

```python
def reduce_current_industry_participation_v2(
    market_context: RetainedCurrentSamePassMarketContextV3,
    classification: RetainedCurrentIndustrySnapshotV1
        | CurrentIndustryClassificationFailureV1,
) -> CurrentIndustryParticipationReportV2
    | CurrentIndustryParticipationFailureV2: ...
```

The reducer accepts no effect capability and never recomputes direction. It
preserves Plan-24 literal `INDUSTRY`, source/null-publisher fields, current
freshness, row equations, canonical ordering, aggregate-only output, privacy,
and failure precedence. An insufficient Market Regime yields
`MARKET_REGIME_UNAVAILABLE` with no Industry rows. Industry V1 is unchanged.

## Research Packet V2 clean cutover

```python
class CurrentSuppliedCohortResearchPacketRequestV2:
    def __init__(
        self,
        *,
        decision_cutoff: datetime,
        cohort_selected_at: datetime,
        members: tuple[CurrentSamePassEquityMemberV1, ...],
        market_context_identity_sha256: str,
    ) -> None: ...

def build_and_retain_current_supplied_cohort_research_packet_v2(
    request: CurrentSuppliedCohortResearchPacketRequestV2,
    market_context: RetainedCurrentSamePassMarketContextV3,
    industry_participation: CurrentIndustryParticipationReportV2
        | CurrentIndustryParticipationFailureV2,
    event_notices: RetainedCurrentEventNoticeSnapshotV1
        | CurrentEventNoticeFailureV1,
    archive: CurrentResearchPacketArchivePortV2,
    lease: StorageRootLease,
    *,
    trusted_clock: _TrustedPacketClockV2 | None = None,
) -> RetainedCurrentSuppliedCohortResearchPacketV2
    | CurrentResearchPacketArchiveFailureV2: ...
```

`decision_session` is derived from the exact sealed market context. The packet
request does not let a caller select it. The context supplies completed current
market data, Market Regime V3, and the optional partial snapshot; separate
caller-supplied market-data/regime/partial values are forbidden. Projector and
candidate stay module-private. No unretained fact-bearing public return exists.

The component/source ledger has exactly four rows in this order:

1. `MARKET_DATA_SAME_PASS_V1`;
2. `MARKET_REGIME_V3`;
3. `INDUSTRY_PARTICIPATION_V2`;
4. `EVENT_NOTICES_V1`.

The partial snapshot is an auxiliary projection inside the sealed
`MARKET_DATA_SAME_PASS_V1` component, not a fifth required component.

An observed AI projection contains, in order:

1. `market_data`: one completed S20 close/volume row per member;
2. `market_regime`: aggregate label/counts/comparison session;
3. `industry_participation`: aggregate literal-Industry rows;
4. `event_notices`: retained Plan-25 member results; and
5. `partial_current_session`: the separately labelled status object and, only
   when `OBSERVED`, provisional price/volume rows;
6. `ai_projection_identity_sha256` over the preceding five fields.

An insufficient packet has those five fact fields null and requires
`INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED`. The component/source ledgers remain
present. The projection excludes the other 20 completed raw sessions, raw OHLC,
member directions, adjusted values, mappings, private corporate-action details,
classification artifacts, source paths, credentials, diagnostics, prompt/model
output, signal, recommendation, and order.

## Canonical identities

`CJ(x)` is exact UTF-8 canonical JSON with lexicographically sorted object keys,
compact separators, `ensure_ascii=false`, `allow_nan=false`, no duplicate or
unknown keys, and one trailing LF. `H(x) = SHA256(CJ(x))`. Timestamps and
decimals use the exact closed forms above. For an object identity, “all fields”
means the exact schema-table order and values, excluding only that named
identity field, any later object-content digest field, and an in-memory seal.
The following formulas are exhaustive:

`type_rows` is an ordered sequence of rows containing only the schema-table
`name` and its ordered field rows. Every field row contains exactly `name`,
`semantic_type`, `unit`, `nullability`, and normalized `bounds`; all state
projections are the separate top-level closed projection table. An in-memory
candidate or retained seal is never a type-row field, state projection, or
schema-preimage value. Configuration rules, reason orders, retention labels,
and in-memory-only upstream references are likewise not schema-preimage keys
unless an exact serialized schema-table field requires them.

| Identity | Exact preimage or cross-object formula |
| --- | --- |
| every successor `schema_identity_sha256` | `H({contract_version,type_rows:[exact schema-table names, ordered field names, types, units, nullability, bounds],state_projections,unknown_key_policy:"REJECT"})` for that contract only |

| every successor `configuration_identity_sha256` | `H({contract_version,structural_bounds,canonicalization,reason_order,precedence,raw_source_policy,partial_policy,retention_names_and_limits})` for that contract only; this is the exhaustive key set, so runtime-manifest fields and retention-name substitutes are rejected |
| every successor `runtime_code_identity_sha256` | `H({runtime_manifest_version:"plan27-source-at-rest@v1",modules:[{relative_path,source_sha256}]})`, with each `relative_path` the exact full repository-relative path, modules exactly the component's reviewed production file and runtime-identity-manifest file from the exact file set, lexicographically sorted by `relative_path`; it is source-at-rest drift evidence, not executed-byte attestation |
| `plan21_cohort_identity_sha256` | `H({contract_version:"current-supplied-cohort-market-data@v1",members:[{isin,symbol}],selected_at:cohort_selected_at})` |
| `canonical_cohort_identity_sha256` | `H({contract_version:"current-same-pass-canonical-cohort@v1",cohort_selected_at,members:[full CurrentSamePassEquityMemberV1]})` |
| `plan22_schedule_identity_sha256` | exact return of delivered `adjusted_daily_schedule_identity_v2` over the ordered 21 session dates, S20 official close, schedule evidence digest, source, and release; this Plan-22-only identity is distinct from and never aliases the public Plan-27 schedule identity |
| `plan22_request_identity_sha256` | exact return of delivered `adjusted_daily_request_identity_v2(cohort_identity_sha256=canonical_cohort_identity_sha256, decision_cutoff=decision_cutoff, schedule_identity_sha256=plan22_schedule_identity_sha256, members=full ordered Plan-22 projections)`; its internal preimage includes the Plan-22 contract/provider/price-basis literals |
| V3 `request_identity_sha256` | `H(all CurrentSamePassMarketRegimeRequestV3 fields before request_identity_sha256)`, including both distinct schedule identities and the separate `plan22_request_identity_sha256` |
| `session_identity_sha256` | `H(position,session,open_at,close_at,kind)` |
| public Plan-27 `schedule_identity_sha256` | `H(schedule_evidence_sha256,schedule_source,schedule_source_release,timezone:"Asia/Kolkata",coverage_through,ordered 21 full session projections excluding session identities)` |
| `latest_completed_session_resolution_identity_sha256` | `H(decision_cutoff,schedule_identity_sha256,decision_session,S0,S20)` |
| `raw_mapping_projection_identity_sha256` | `H(all CurrentSamePassRawMappingReceiptV1 fields except its identity)` |
| `raw_mapping_set_identity_sha256` | `H({request_identity_sha256,mappings:[raw_mapping_projection_identity_sha256 in member order]})` |
| `raw_source_policy_identity_sha256` | `H({provider:"UPSTOX",price_basis:"RAW",download_contract,query_contract,current_aware_retained_interval:"1m",daily_calculation,candle_schema,manifest_schema,provisional_partition_schema,validation_policy,adapter_runtime_identity})` with exact implementation literals frozen in configuration |
| `source_receipt_identity_sha256` | `H(all CurrentSamePassRawCoverageSourceRowV1 fields except its identity)` |
| `raw_bar_identity_sha256` | `H(all CurrentSamePassRawBarV1 fields except its identity)` |
| `raw_grid_identity_sha256` | `H(all CurrentSamePassRawGridV1 fields except its identity)` |
| `partial_current_session_row_identity_sha256` | `H(all PartialCurrentSessionRowV1 fields except its identity)` |
| `partial_snapshot_identity_sha256` | `H(all PartialCurrentSessionSnapshotV1 fields except its identity)` |
| `raw_result_identity_sha256` | `H(all PrivateCurrentSamePassRawDailyResultV1 fields except its identity)` |
| decision-row `row_identity_sha256` | `H(all CurrentSamePassDecisionMarketDataRowV1 fields except its identity)` |
| Market-data `report_identity_sha256` | `H(all CurrentSamePassDecisionMarketDataReportV1 fields except its identity)` |
| `calculation_identity_sha256` | `H({contract_version:"current-supplied-cohort-market-regime-calculation@v3",comparison:"Decimal(close(S20)) cmp Decimal(close(S0))",raw_adjusted_direction_equality:true,adjusted_admission:"current-prospective-success-only; not-attempted-preserves-upstream-insufficiency",advance_formula:"advances*5>=cohort_size*3",decline_formula:"declines*5>=cohort_size*3",reason_order:[the 14 frozen post-session reasons],suppression:"whole-result"})` |
| V3 `report_identity_sha256` | `H(all CurrentSamePassMarketRegimeReportV3 fields except its identity)` |
| direction-row `row_identity_sha256` | `H(all _CurrentSamePassMemberDirectionRowV3 fields except its identity)` |
| `direction_candidate_identity_sha256` | `H(all _CurrentSamePassMemberDirectionCandidateV3 fields except its identity)`; context/archive identities are absent |
| `failure_identity_sha256` | `H(all CurrentSamePassPreflightFailureV1 fields except its identity)` |
| `failure_projection_identity_sha256` | `H(all CurrentSamePassAdjustedDailyCloseFailureProjectionV1 fields except its identity)` |
| `not_attempted_projection_identity_sha256` | `H(all CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1 fields except its identity)` |
| context `ledger_row_identity_sha256` | `H(all CurrentSamePassContextComponentLedgerRowV1 fields except its identity)` |
| `context_identity_sha256` | `H(contract/schema/config/runtime identities, request_identity_sha256, raw_result_identity_sha256, market-data report identity, screen identity, adjusted_handoff_identity_sha256 or null, adjusted_failure_projection_identity_sha256 or null, adjusted_not_attempted_projection_identity_sha256 or null, V3 report identity, direction_candidate_identity_sha256 or null, ordered context-ledger-row identities, temporal_scope, historical_availability_claim, replay_capability)`; exactly one adjusted identity is non-null |
| `context_object_sha256` | raw SHA-256 of exact `PrivateCurrentSamePassMarketContextObjectV3` canonical bytes containing `context_identity_sha256` and excluding only `context_object_sha256`; no archive time exists in those bytes |
| `candidate_identity_sha256` | `H({context_identity_sha256,context_object_sha256})` |
| `context_receipt_identity_sha256` | `H(all CurrentSamePassContextReceiptV1 fields except its identity)`, including `archive_known_at` |
| context `completion_marker_identity_sha256` | `H(all CurrentSamePassContextCompletionMarkerV1 fields except its identity)`, including the receipt identity/hash and same `archive_known_at` |
| `retained_context_identity_sha256` | `H(all serialized RetainedCurrentSamePassMarketContextV3 fields except its identity)`, including receipt, marker, public projections, and `archive_known_at`; excluding `_archive_seal` |
| Industry row `row_identity_sha256` | `H(all CurrentIndustryCountV2 fields except its identity)` |
| Industry `report_identity_sha256` | `H(all CurrentIndustryParticipationReportV2 fields except its identity)` |
| Industry `failure_identity_sha256` | `H(all CurrentIndustryParticipationFailureV2 fields except its identity)` |
| packet `request_identity_sha256` | `H(all CurrentSuppliedCohortResearchPacketRequestV2 fields except its identity)` |
| packet `ledger_row_identity_sha256` | `H(all CurrentResearchPacketComponentLedgerRowV2 fields except its identity)` |
| `source_row_identity_sha256` | `H(all CurrentResearchPacketSourceAttributionRowV2 fields except its identity)` |
| each packet projection identity | `H(all fields of that exact MarketData/MarketRegime/Industry/Event projection except its identity)` |
| `ai_projection_identity_sha256` | `H(all fields of the selected exact observed or insufficient AI projection except its identity)` |
| `packet_identity_sha256` | `H(contract/schema/config/runtime identities, packet request/cohort/context identities, cutoff/session/component_known_at_max/state, ordered ledger-row identities, ordered source-row identities, reasons, ai_projection_identity_sha256)` |
| `packet_object_sha256` | raw SHA-256 of exact `CurrentSuppliedCohortResearchPacketV2` canonical bytes containing `packet_identity_sha256` and excluding only `packet_object_sha256`; no packet archive time exists in those bytes |
| packet `candidate_identity_sha256` | `H({packet_identity_sha256,packet_object_sha256})` |
| packet `archive_failure_identity_sha256` | `H(all CurrentResearchPacketArchiveFailureV2 fields except its identity)` |
| packet `receipt_identity_sha256` | `H(all CurrentResearchPacketReceiptV2 fields except its identity)`, including `archive_known_at` |
| packet `completion_marker_identity_sha256` | `H(all CurrentResearchPacketCompletionMarkerV2 fields except its identity)`, including receipt identity/hash and same `archive_known_at` |
| packet `retained_identity_sha256` | `H(all serialized RetainedCurrentSuppliedCohortResearchPacketV2 fields except its identity)`, including packet, receipt, marker, and `archive_known_at`; excluding `_archive_seal` |

The existing Plan-21 screen and delivered Plan-22 request/handoff formulas are
revalidated exactly, not rehashed under a successor approximation. In
particular, the bridge and handoff carry `plan22_request_identity_sha256`, never
the distinct V3 request identity. `component_known_at_max` is the maximum
admitted component knowledge time, not packet archive time. Context and packet
archive `known_at` are sampled once only for their receipts and are copied
exactly to marker and retained identities. No digest depends on itself, on a
later digest that depends back on it, or on a post-publication mutation.

Inactivity duration and historical session `known_at` guesses are absent from
all identities. Digests prove integrity bindings, not publisher authenticity,
historical availability, executed-byte attestation, licence authority, or
provider completeness.

## States, reasons, precedence, and suppression

Pre-domain structural precedence is:

0. exact Python types and closed contract/schema/config/runtime constants;
1. live `StorageRootLease`, root equality, and owner-private/no-follow authority;
2. request/cohort bounds and identity syntax; and
3. structural byte/depth/resource bounds.

Failure raises sanitized `TypeError` or `ValueError`; no domain report is
created, and no provider effect occurs before admission completes. The sole
domain exception is a schedule preflight failure: after an admitted request and
lease but before any provider, adjusted, raw, or archive effect, it returns the
typed all-no-trade `CurrentSamePassPreflightFailureV1`.

Schedule preflight reasons render only in this order:

1. `SCHEDULE_EVIDENCE_MISSING`;
2. `SCHEDULE_EVIDENCE_STALE`;
3. `SCHEDULE_EVIDENCE_CONFLICTED`;
4. `SCHEDULE_CONTINUITY_UNPROVEN`;
5. `LATEST_COMPLETED_SESSION_UNRESOLVED`.

Once all 21 authoritative sessions exist, Market Regime V3 reasons render
globally in this separate order:

1. `COHORT_BINDING_MISMATCH`;
2. `RAW_MAPPING_MISSING`;
3. `RAW_MAPPING_STALE`;
4. `RAW_MAPPING_CONFLICTED`;
5. `RAW_ACQUISITION_UNAVAILABLE`;
6. `ACQUISITION_DEADLINE_EXCEEDED`;
7. `RAW_BAR_MISSING`;
8. `RAW_BAR_STALE`;
9. `RAW_BAR_CONFLICTED`;
10. `RAW_BAR_INVALID`;
11. `RAW_BAR_FUTURE_KNOWN`;
12. `CORPORATE_ACTION_SCREEN_INSUFFICIENT`;
13. `ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID`;
14. `RAW_ADJUSTED_DIRECTION_CONFLICT`.

`RawDailyReason` is exactly post-session reasons 1 through 11 in the same
order. `MarketRegimeReason` is all 14 post-session reasons. All five schedule
preflight reasons are rejected by raw-result, market-data-report, V3-report,
context-ledger, Packet mapping/admission, and Packet ledger/source-row
validation. They can exist only in `CurrentSamePassPreflightFailureV1`. Raw
acquisition cannot emit either component-comparability reason or
`RAW_ADJUSTED_DIRECTION_CONFLICT`.

Schedule authority/shape/timeliness runs before mapping/provider effects.
Missing schedule retention maps to `SCHEDULE_EVIDENCE_MISSING`; an `as_of` or
coverage deficiency maps to `SCHEDULE_EVIDENCE_STALE`; a digest/source/release
conflict maps to `SCHEDULE_EVIDENCE_CONFLICTED`; incomplete classified calendar
coverage maps to `SCHEDULE_CONTINUITY_UNPROVEN`; and fewer than 21 completed
official sessions maps to `LATEST_COMPLETED_SESSION_UNRESOLVED`. Each returns
the typed preflight no-trade result and suppresses all session-dependent
retention. Conflict suppresses session selection. Cohort admission precedes all
mappings. All mappings resolve under one lease before download; a failed member
mapping suppresses that member's provider effect and all grid calculation. Raw
failures are collected independently, deduplicated, and rendered globally.
Missing is not also invalid; future-known suppresses stale for the same clock;
conflict forbids latest-wins. Exactly `21 * N` rows are required before
direction.

A missing prior Plan-20 envelope is never inspected and has no reason. Current
approved provider/retained bars do not become invalid because this tool did not
previously retain them.

Raw mapping/acquisition and Plan-21 admission precede Plan-22. Any raw
insufficiency remains in the raw/Market-data reasons; any Plan-21 non-screened
result maps publicly only to `CORPORATE_ACTION_SCREEN_INSUFFICIENT`, retaining
its exact private reason. Either condition suppresses the yfinance call and
retains the closed `NOT_ATTEMPTED / UPSTREAM_INSUFFICIENT_EVIDENCE` adjusted
projection. This is deliberate non-execution, never `PROVIDER_FAILURE`.

When Plan 22 is invoked, an exact delivered `AdjustedDailyCloseFailure` or an
exact success carrying `REVISED_NON_PIT` maps to
`ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID`. The exact delivered failure uses the
closed private failure projection; `REVISED_NON_PIT` retains the handoff and no
failure projection. Successful-result contract/member/mapping/schedule/cutoff/
endpoint/identity mismatch is not an exact success: it is pre-domain structural
failure and no context is minted. The V3 calculation is invoked only for the
exact admitted `CURRENT_PROSPECTIVE` success union. Raw-adjusted conflict runs
only after both closures are exact and suppresses the aggregate and direction
candidate.

`OBSERVED` requires empty Market Regime reasons, exact completed grid, screened
Plan-21 result, exact current-prospective adjusted handoff, equal directions,
non-null aggregate, and a non-null prearchive direction candidate.
`INSUFFICIENT_EVIDENCE` has null aggregate/counts/candidate and nonempty
reasons. The archive seal is retention authority only, never a domain state or
fact identity. Optional partial state does not change either state unless
partial is used as complete.

Industry V2 inherits these exact reasons and order:

1. `MARKET_REGIME_UNAVAILABLE`;
2. `CLASSIFICATION_ARTIFACT_MISSING`;
3. `CLASSIFICATION_ARTIFACT_MALFORMED`;
4. `CLASSIFICATION_SOURCE_UNSUPPORTED`;
5. `CLASSIFICATION_TIER_UNSUPPORTED`;
6. `CLASSIFICATION_MEMBER_UNSUPPORTED`;
7. `CLASSIFICATION_AMBIGUOUS`;
8. `CLASSIFICATION_CONFLICTING`;
9. `COHORT_BINDING_MISMATCH`;
10. `MEMBER_IDENTITY_MISMATCH`;
11. `CLASSIFICATION_FUTURE_KNOWN`;
12. `CLASSIFICATION_SESSION_STALE`;
13. `CLASSIFICATION_ARCHIVE_FAILED`.

Malformed state owns reasons 3, 7, 8, 9, and 10; unsupported state owns 4, 5,
and 6; insufficient state owns 1, 2, 11, 12, and 13. Cross-state precedence is
`MALFORMED_EVIDENCE`, then `UNSUPPORTED_CAPABILITY`, then
`INSUFFICIENT_EVIDENCE`; rendering always follows the global order.

Packet V2 reasons retain Plan-26 order with successor mappings:

1. `MARKET_DATA_UNAVAILABLE`;
2. `MARKET_REGIME_UNAVAILABLE`;
3. `INDUSTRY_PARTICIPATION_UNAVAILABLE`;
4. `EVENT_NOTICES_UNAVAILABLE`;
5. `SOURCE_USE_UNAUTHORIZED`;
6. `COMPONENT_IDENTITY_INVALID`;
7. `COHORT_PROJECTION_MISMATCH`;
8. `DECISION_CUTOFF_MISMATCH`;
9. `DECISION_SESSION_MISMATCH`;
10. `COMPONENT_FUTURE_KNOWN`;
11. `COMPONENT_STALE`;
12. `COMPONENT_CONFLICTED`;
13. `PARTIAL_AS_COMPLETE`.

An invalid completed grid adds `MARKET_DATA_UNAVAILABLE`; Market Regime
insufficiency adds `MARKET_REGIME_UNAVAILABLE`; stale/future/conflict/cohort
findings add their matching cross-component reason; private seal or identity
failure adds `COMPONENT_IDENTITY_INVALID`; raw-adjusted disagreement adds
`COMPONENT_CONFLICTED`. Exact upstream reasons remain in the component ledger.
`UPSTREAM_INSUFFICIENT_EVIDENCE` is appended only to the Market Regime ledger
when the closure-validated adjusted component state is `NOT_ATTEMPTED`; it adds
no provider-failure or additional cross-component reason.

| Exact upstream component reason | Packet cross-component reason |
| --- | --- |
| `RAW_BAR_FUTURE_KNOWN`, `CLASSIFICATION_FUTURE_KNOWN`, `EVENT_SOURCE_DATE_FUTURE` | `COMPONENT_FUTURE_KNOWN` |
| `RAW_MAPPING_STALE`, `RAW_BAR_STALE`, `CLASSIFICATION_SESSION_STALE`, `EVENT_SOURCE_DATE_STALE` | `COMPONENT_STALE` |
| `RAW_MAPPING_CONFLICTED`, `RAW_BAR_CONFLICTED`, `RAW_ADJUSTED_DIRECTION_CONFLICT`, `CLASSIFICATION_CONFLICTING`, `EVENT_DUPLICATE`, `EVENT_CONFLICTED` | `COMPONENT_CONFLICTED` |
| `CLASSIFICATION_SOURCE_UNSUPPORTED`, `EVENT_SOURCE_UNAUTHORIZED`, `EVENT_SOURCE_MISMATCH` | `SOURCE_USE_UNAUTHORIZED` |
| `COHORT_BINDING_MISMATCH`, `EVENT_COHORT_INVALID`, `EVENT_OUT_OF_COHORT` | `COHORT_PROJECTION_MISMATCH` |
| `UPSTREAM_INSUFFICIENT_EVIDENCE` | no additional Packet reason; the applicable `MARKET_DATA_UNAVAILABLE` and/or `MARKET_REGIME_UNAVAILABLE` remains authoritative |

This table is closed after context creation. Schedule-preflight reasons have no
context or Packet ledger entry because no context or Packet exists. An upstream
reason remains verbatim in its component ledger; any mapped Packet reason is
additive and mandates the all-null AI projection and
`INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED`.
A missing/conflicting optional partial remains only in its auxiliary partial
state. `PARTIAL_AS_COMPLETE` is reserved for leakage/substitution into completed
facts or calculations.

Any domain reason selects the all-null packet AI projection. Archive failure is
not a domain reason and returns only the typed archive failure with no
AI-consumable facts.

## Retention, deadline, logical commit, and retry

The context archive uses deterministic names:

```text
.current-same-pass-market-regime-v3/
context-<context_identity_sha256>.json
retained-<context_identity_sha256>.json
completion-<context_identity_sha256>.json
```

The immutable private context object stores the request's full/reduced bridge
projections, resolved schedule, the exact raw result (`21 * N` bars/source
receipts when observed and a null grid with closed reasons when insufficient),
optional partial state/rows, Plan-21 screen, exactly one of the pre-acquired
Plan-22 handoff or its closed failure projection, public reports, an
observed-only direction candidate, component ledger, context identity, and
object digest. It has no archive time or seal. Public retained bytes redact the
raw grid, provider keys, private screen, adjusted facts/failure details, and
member directions.

Publication is create-only, descriptor-relative, no-follow, owner-private,
single-link, stable-read verified, fsynced, and bound to one live lease. Each
named context/receipt/marker member binds its exact filename and opened inode,
raw bytes/hash, and filesystem identity: `st_dev`, `st_ino`, `st_uid`, full
`st_mode` for a regular owner-private `0600` file, `st_nlink == 1`, and
`st_size`.
Separate files are not physically atomic; only the exact completion marker is
the logical commit. Orphan context or receipt is incomplete. No overwrite,
delete, scan, nearest result, mutable current pointer, fallback root, or
alternate name exists.
The full context/receipt/marker transaction is serialized by a module lock for
callers sharing a process. `StorageRootLease` remains the cross-process
authority. A concurrent first caller revalidates the winner's exact
context/receipt/marker and returns (or waits for) that original retained result;
it does not return an archive failure merely because publication raced.


First context success is exactly:

1. validate the closed candidate, acyclic identities, and full private context
   bytes;
2. publish those unchanged context bytes and stable-reread them;
3. sample one `archive_known_at = trusted_utc_now + 30 seconds`; do not write it
   into or mutate the context object;
4. build and publish the closed receipt containing that time, context identity,
   object digest, byte count, and deterministic filename;
5. stable-reread context and receipt, verify root/file/bytes/time/lease no later
   than `archive_known_at`, then publish the completion marker binding the same
   time plus exact receipt identity and receipt-byte hash;
6. stable-reread all three objects and marker filesystem binding no later than
   `archive_known_at`;
7. wait until trusted time reaches `archive_known_at`, require
   `archive_known_at <= decision_cutoff`, and reverify the live lease; and
8. reconstruct the retained projection from exact persisted bytes and attach
   only an opaque in-memory private archive seal. The closure registry keeps
   exact current candidate/upstream objects only as inaccessible process-local
   state for required downstream reductions; they remain unreachable from
   seals/results, unexported, unserialized, and canonically revalidated on every
   use. No persisted/public byte or identity changes after publication.

This retain-before-return rule begins only after composed schedule
resolution has yielded all 21 sessions. A schedule preflight failure returns
directly with no context candidate or archive effect.

The effect-deadline outcome is governed by the direct synchronous rule under the
raw boundary. A call not started for insufficient remaining time may yield and
retain `ACQUISITION_DEADLINE_EXCEEDED` inside the archive window. A started call
must return, with `download_call_completed_at <= acquisition_effect_deadline`,
before any domain context can be retained. A late return or any
not-provably-quiescent effect yields only `CurrentSamePassArchiveFailureV1` and
a new request/cutoff; no claim of forcible cancellation or absence of writes
during that failed overrun is made. The caller-owned lease remains live through
synchronous return and archive completion. If context publication/verification
cannot complete with `archive_known_at <= decision_cutoff`, the same archive
failure is returned; no context or packet fact escapes and no time is backdated.

Packet V2 uses the same acyclic sequence under
`.current-research-packet-v2/`: immutable `packet-<packet_identity_sha256>.json`
contains no archive time; `retained-<packet_identity_sha256>.json` is the closed
receipt; `completion-<packet_identity_sha256>.json` is the sole logical commit.
Its `archive_known_at` is sampled only after stable packet publication and is
included only in receipt, marker, and retained identity. Packet retention
finishes before return.

After an archive port returns a retained V3 context or Packet V2 value, its
outer builder MUST adopt it only by reopening the complete logical commit under
the caller-supplied live `StorageRootLease`. The closure-held binding contains
the current candidate object, exact leased root identity, the exact outer
invocation trusted-clock authority, fixed archive directory and filenames,
exact context/packet, receipt, and marker bytes with hashes, and each member's
stored filesystem identity. Descriptor-relative adoption requires the currently
named object to be the opened object and to match that complete identity. It
rejects an unrelated root or lease and any post-delegation deletion,
byte-identical unlink/recreate, permission mutation, replacement, or corruption;
downstream public self-validation remains lease-free.
The public V3 and Packet file facades have no readable or writable inner archive
delegate attribute. Each exact facade instance is bound to its descriptor archive
only inside the same closure-owned registry; assignment (including
`object.__setattr__`) of `_archive` is rejected before any archive effect or seal
mint. Consequently a same-root backdated replacement delegate cannot publish
files and have the facade rebind them to the outer trusted clock. An arbitrary
caller-supplied archive port remains subject to the separate outer adoption
checks above.

The outer invocation passes its one trusted clock into V3 and Packet file
archives. File publication, receipt/marker time, retained-seal minting, and
outer adoption MUST bind to that exact authority. The outer builders reparse
the receipt and marker from reopened files after every archive-port return and
require the parsed shared `archive_known_at` no later than that clock's current
UTC time and the decision cutoff. A same-root delegate that ignores the outer
clock and uses a backdated clock may create complete genuine files and its own
genuine local seal, but outer adoption rejects the different clock binding. A
future-dated delegate likewise waits through the outer boundary or is rejected.

If Packet marker publication has completed and directory fsync reveals trusted
time is later than its recorded `archive_known_at`, the invocation stable-rereads
and removes only that marker when it is the exact marker it just created, then
fsyncs the directory and returns archive failure. The packet and receipt remain
an interrupted receipt-only archive; a retry never adopts or completes it.

Exact retry derives the same names from identities only for a complete,
exactly verified receipt-and-marker logical commit. A receipt without its
completion marker is interrupted/incomplete and fails closed as an archive
failure; retry never recovers it into a commit. A complete retry waits only for
the recorded original `archive_known_at` and returns byte-identical public bytes
with original times/identities. It never samples a replacement time, reacquires
the adjusted result, or mutates an existing context/packet. Changed cutoff,
member projection, mapping revision, either request identity, schedule, source
receipt, bar, partial state, screen, adjusted handoff/failure projection, reason,
or result creates a new identity and immutable names. A failed deadline uses a
new request.

## Structural bounds

Bounds are part of configuration and schema identities:

```text
cohort members                                      1..50
completed sessions                                  exactly 21
completed raw bars                                  21 * cohort_size; max 1,050
partial current-session rows                        0 or cohort_size; max 50
same-pass private context / context-*.json           1..4_194_304
context receipt / retained-*.json                    1..16_384
context completion marker                            1..4_096
packet request canonical bytes                       1..4_194_304
event notice rows across observed packet             0..10_000
Industry aggregate rows                              1..cohort_size
full packet object / packet-*.json                    1..37_748_736
packet receipt / retained-*.json                      1..16_384
packet completion marker                              1..4_096
packet archive failure canonical bytes                1..1_024
packet retained-result canonical bytes                1..37_769_216
JSON nesting                                          1..32
```
The raw configuration preimage independently freezes the cohort interval,
exact completed-session count, exact mapping count for observed results, both
`21 * cohort_size` completed source-row/bar formulas and ranges, and the
optional partial `0 or cohort_size` interval. Its independent JSON fixture and
fixed digest must match production; the schema metadata repeats the exact
cardinality bounds rather than using an unbounded `N`.

Implementation MUST construct representative maximum valid context and packet
objects, including the optional partial projection, and prove they fit. A valid
maximum-plus-one object is structural archive failure. If the representative
valid context exceeds 4 MiB, the bound must be raised and independently
re-reviewed before implementation; truncation or weakening inherited bounds is
forbidden. No unbounded retry, scan, text, member output, or partial-member
output exists.

## Source-use and consumer boundary

The raw completed/partial capability reuses Upstox under existing source policy.
The adjusted boundary remains explicitly yfinance `ADJUSTED` personal/research
use and is not strict as-published point-in-time authority. Plan 21 remains
nonexhaustive. Plans 24 and 25 retain their exact official NSE/NSE Indices
attribution and owner-private personal/noncommercial restrictions as amended on
2026-08-26. This plan adds only the owner-authorized bounded current
schedule/Industry/event acquisition edge. It adds no provider, alternate
source, polling, fallback, attachment fetch, redistribution authority, or
general transport/framework.

Only a verified retained packet is AI-consumable. NSE-derived event narrative
and Industry material remain inside the same owner's private local workflow and
must not be sent to a hosted, third-party, public, shared, or multi-user model or
service without separate owner authorization and source-use review. The
deterministic tool emits facts, provenance, closed reasons, and required
consumer disposition only. It does not write a narrative, score, suggestion,
signal, recommendation, position, or order.

The optional partial snapshot is live swing-research context, not intraday
trading authority. A consuming AI may describe its provisional status but may
not recompute completed market facts, infer missing rows, project it as a close,
or convert it into a signal/recommendation/order.

## Exact implementation file set

Implementation is limited to exactly these files.

Production:

```text
src/swing_trading_ai_assistant/market_data/http.py
src/swing_trading_ai_assistant/market_data/download_preparation.py
src/swing_trading_ai_assistant/market_data/open_month.py
src/swing_trading_ai_assistant/market_data/provisional_validation.py
src/swing_trading_ai_assistant/market_data/current_evidence_acquisition.py
src/swing_trading_ai_assistant/market_data/current_evidence_acquisition_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_data/current_event_notice.py
src/swing_trading_ai_assistant/market_data/current_industry_classification.py
src/swing_trading_ai_assistant/market_data/current_corporate_action_screen.py
src/swing_trading_ai_assistant/market_data/current_corporate_action_screen_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_data/adjusted_daily/service.py
src/swing_trading_ai_assistant/market_data/current_same_pass_daily.py
src/swing_trading_ai_assistant/market_data/current_same_pass_daily_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_data/runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py
src/swing_trading_ai_assistant/market_data/schedule_evidence.py
src/swing_trading_ai_assistant/market_data/current_event_notice_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_data/current_industry_classification_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_regime/current_supplied_cohort.py
src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_v3.py
src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_v3_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_v2_runtime_identity_manifest.py
src/swing_trading_ai_assistant/sector_analysis/current_industry_participation.py
src/swing_trading_ai_assistant/sector_analysis/current_industry_participation_v2.py
src/swing_trading_ai_assistant/sector_analysis/current_industry_participation_v2_runtime_identity_manifest.py
src/swing_trading_ai_assistant/sector_analysis/current_industry_participation_runtime_identity_manifest.py
src/swing_trading_ai_assistant/research_packet/__init__.py
src/swing_trading_ai_assistant/research_packet/current_supplied_cohort.py
src/swing_trading_ai_assistant/research_packet/current_supplied_cohort_runtime_identity_manifest.py
```

Tests:

```text
tests/market_data/test_current_evidence_acquisition.py
tests/market_data/test_open_month.py
tests/market_data/test_provisional_validation.py
tests/market_data/test_public_preview_preparation.py
tests/market_data/test_current_event_notice.py
tests/market_data/test_current_industry_classification.py
tests/market_data/test_current_corporate_action_screen.py
tests/market_data/test_adjusted_daily_close_v2.py
tests/test_sprint3_release_readiness.py
tests/market_data/test_current_same_pass_daily.py
tests/market_data/data/plan27_raw_v1_configuration_preimage.json
tests/market_data/data/plan27_raw_v1_schema_preimage.json
tests/market_regime/test_current_supplied_cohort_v3.py
tests/market_regime/test_current_supplied_cohort_v2.py
tests/market_regime/test_current_supplied_cohort.py
tests/sector_analysis/test_current_industry_participation_v2.py
tests/sector_analysis/test_current_industry_participation.py
tests/research_packet/test_current_research_packet.py
tests/market_regime/data/plan27_v3_schema_preimage.json
tests/sector_analysis/data/plan27_industry_v2_schema_preimage.json
tests/research_packet/data/plan27_packet_v2_schema_preimage.json

```

These independent fixtures are immutable acceptance evidence. They are reviewed
with their corresponding tests and their canonical bytes and fixed schema
digests must match the production metadata.

Governing/lifecycle records:

```text
docs/plans/27-current-same-pass-market-regime-contract.md
docs/plans/21-current-supplied-cohort-corporate-action-screen-contract.md
docs/plans/22-provider-neutral-adjusted-daily-close-contract.md
docs/plans/24-current-supplied-cohort-sector-analysis-contract.md
docs/plans/25-current-supplied-cohort-event-notice-contract.md
docs/plans/26-current-supplied-cohort-research-packet-contract.md
docs/architecture-freeze-v1.md
docs/roadmap.md
docs/upcoming_sprints_overview.md
docs/sprints/sprint-12.md
docs/sprints/sprint-14.md
docs/sprints/README.md
README.md
AGENTS.md
docs/herdr-multi-agent-workflow.md
```

The verifier, its deterministic regression suite, and the direct legacy-manifest
bindings above are blocker-authorized integration dependencies. They preserve
no-follow descriptor traversal, named directory-edge reopen binding, complete
regular-file checks, and the reviewed directory-edge metadata projection.

The global market-data manifest edit is inventory regeneration only. The frozen
V1 `sector_analysis/__init__.py` package surface is unchanged; Industry V2 is
imported only from its direct submodule. The packet import contract is exactly
`swing_trading_ai_assistant.research_packet.current_supplied_cohort`.
`src/swing_trading_ai_assistant/research_packet/__init__.py` is intentionally
empty and exports no symbol; importing packet contracts from the package root
is not supported. The research-packet module is a clean WIP `@v1` to `@v2`
replacement using one archive implementation and no dual public path.

The current blocker corrections are affirmative changes, not no-change claims:
Plan 21 adopts the exact source/release pair predicate and refrozen schema in
its source, serialization/publication boundaries, tests, contract, and direct
and transitive runtime manifests; Plan 22 applies the same predicate at its
delivered integration boundary; Plan 24/Industry V2 and Plan 25/event
acquisition receive only the listed bounded integration and contract
corrections; Plan 26 is updated only to point truthfully at the current
Plan-27-authorized amendment. `AGENTS.md` and
`docs/herdr-multi-agent-workflow.md` are governing/workflow records, not runtime
surfaces.

No change is authorized to dependencies, `uv.lock`, workflows, Plan-20 V1/V2,
CLI, API, MCP, UI, notifications, broker, signal, recommendation,
historical/backtest modules, or provider selection. Any additional source file
edit requires a blocker review that cites the violated current acceptance
condition, updates this exact 66-path file set, and obtains owner scope
authority before editing.

## RED acceptance tests

RED MUST fail for missing V3/V2 behavior before production code. Tests defend:

### Request, cohort, schedule, and time

- `N=1,5,50`; permutation invariance; duplicate ISIN/symbol; invalid interval;
  unsupported exchange/capability; supported outside-Nifty NSE equity admission;
- exact UTC cutoff; trusted invocation boundary; 60-second minimum and
  30-minute maximum lead; effect deadline exactly 30 seconds before cutoff;
  equality and one-microsecond failures; no after-close coupling;
- market-hours cutoff resolves prior official session; post-close cutoff resolves
  today's completed session; pre-open/weekend/holiday resolution; no
  `IST_DATE(cutoff)` invariant;
- exact 21 sessions across weekend, holiday, closure, special-session, and month
  boundaries; authoritative identity binds evidence/source/release/timezone/
  coverage/full session projections; omitted, duplicate, conflicting, stale,
  late, wrong-source, wrong-release, wrong-timezone, or conflicting public
  identity is typed preflight failure;
- missing current S20 raw data does not roll the decision session backward.

### Prior-run independence and raw evidence

- parameterized 0-, 1-, 7-, and 30-day inactivity yields byte-identical current
  contexts/packets and identities when all current admitted inputs are equal;
- zero Plan-20 prospective archive objects plus complete current approved inputs
  yields an observed current context; inactivity/prospective-envelope reasons do
  not exist;
- retained exact bars and newly acquired exact bars are both admitted under the
  same current contract; newly acquired historical-date bars retain current
  `known_at` and no historical-availability field;
- exact mappings per member; missing/stale/ambiguous/conflicting/wrong identity,
  interval, key, or source release preserve distinct closed reasons; zero
  provider effects before full admission;
- exactly `21 * N` raw rows; missing, duplicate, extra, partial, provisional,
  mixed provider/basis, malformed, stale, conflict, future-known, wrong receipt,
  or unproven row; untrusted input order and canonical output order;
- catalog/coverage errors fail closed without download, while each genuinely
  missing manifest downloads only its exact symbol/month range and never expands
  into a full-cohort range;
- no denominator reduction, no backdated time, no replay resolver, and no
  Plan-20 object manufacture.

### Optional partial snapshot

- not requested, active-market observed, pre-open/holiday/post-close not
  applicable, unavailable, and conflicted states with exact nullability/reasons;
- one exact current active-session row per member, completed-minute price,
  cumulative volume, `as_of <= known_at <= cutoff`, identity and order;
- missing/conflicting partial and representative query, payload, arithmetic, or
  projection failures remain visible `UNAVAILABLE` partial evidence and non-fatal
  to valid completed Market Regime, Industry, and packet components;
- no partial value enters S20, raw grid, Market Regime, Industry direction, or
  completed market-data projection;
- any partial-as-complete substitution yields packet `PARTIAL_AS_COMPLETE`, all
  AI fact fields null, and mandatory `NO_TRADE`.

### Comparability and Industry

- every Plan-21 screened seal/insufficiency path and nonexhaustive limitation;
- exact Plan-21 manifest bytes, `cohort_selected_at`, reduced-member equality,
  and exact Plan-22/24/25 full/reduced bridges, including Plan-25
  `listed_equity_segment == instrument_type == "EQUITY"` and proof that Plan-22
  `segment == "EQ"` is never substituted, plus the independent Plan-25
  `provider_mapping_revision`;
- exact Plan-22 V2 owner mapping/schedule/request/handoff projections;
  `plan22_schedule_identity_sha256` is the exact delivered schedule-identity
  result passed only to Plan 22, differs from and never aliases the public
  Plan-27 schedule identity; `plan22_request_identity_sha256` is the exact
  delivered request-identity result, differs from and is never aliased to the V3
  request identity, and exactly equals the handoff request identity;
- `CURRENT_PROSPECTIVE` accepted, `REVISED_NON_PIT` and one-microsecond-late
  retrieval rejected; exact adjusted success and every delivered failure
  code/reason pair exercise the closed invoked-result union, while raw and
  screen insufficiency prove zero Plan-22 calls, the separate
  `NOT_ATTEMPTED / UPSTREAM_INSUFFICIENT_EVIDENCE` projection, handoff/failure/
  not-attempted XOR, retained insufficiency, forged-state rejection, and archive
  retry with zero adjusted acquisition;
- all raw/adjusted direction combinations and inclusive `3/5` and `30/50`
  breadth boundaries run through production acquisition/composition; equality
  is unchanged and disagreement is retained insufficiency;
- prearchive direction-candidate binding excludes context/archive identities;
  exact count reconciliation, embedded context-byte inclusion, seal-only
  archive completion, absence of a public constructor/parser/serializer/export,
  and Industry consumption without recomputation;
- Plan-24 cohort/source/row/count equality and failure precedence, with V2's
  explicit current-cutoff-date classification rule instead of V1
  historical/session equivalence;

### Retention and packet

- every safely admitted post-session insufficiency retains before return under
  one real lease; schedule preflight failures return before retention;
- exact closed key/type/order/nullability/state/bound checks for every schema
  table above and unknown-key rejection, including independently authored,
  complete ordered V3/Industry/Packet expected schema preimages and the raw
  configuration preimage with fixed digests; the raw fixture binds every frozen
  structural cardinality and none of these fixtures call or copy production
  metadata;
- exact context/receipt/marker fields, acyclic formulas, deterministic names,
  a representative maximum valid 50-member/1,050-row context including 50
  optional partial rows within 4 MiB, the exact 4 MiB byte gate, and
  max-plus-one rejection;
- no post-publication mutation; context/packet archive time appears only in
  receipt/marker/retained identities; every in-memory seal is absent from
  bytes/hash/schema type rows;
- missing/corrupt/replaced/linked/unsafe/spliced/late/interrupted objects,
  mismatched root/lease/runtime-clock authority, runtime drift, exact retry,
  changed-input identity, delegated byte-identical unlink/recreate, and delegated
  `chmod` for each context/packet, receipt, and marker member;
- custom complete three-file V3 and Packet delegates using future or backdated
  clocks are rejected by the same outer invocation-clock binding; both public
  file facades reject same-root mutable inner-delegate replacement before any
  effect or seal; two concurrent first callers return the same object bytes,
  receipt, marker, original archive time, and retained identity;
- a late just-created Packet marker is removed after post-fsync trusted-time
  detection and retry observes receipt-only failure with no marker;
- archive-port private-context/candidate exfiltration and malformed archive
  failure request/context/identity bindings are rejected before any public
  return;
- raw acquisition calls
  `_default_download_service(...).download_under_lease(request, lease)`
  directly and never `BoundedNifty50DownloadServiceV1.download_single`; one
  caller-owned lease remains live through synchronous return and archive;
- the injected `PublicationGateV1` deadline gate rejects entries at/after the
  effect deadline; no background worker exists; synchronous
  `download_call_completed_at` proves completion/quiescence; pre-call
  insufficiency and late/unproven archive failure are distinguished without
  claiming forcible cancellation or no late writes for a failed overrun;
- exact four-row context ledger projections cover every state/contract/schema/
  runtime/primary identity/known-at/reason/nullability and row identity,
  including adjusted success, invoked adjusted failure, and the first-class
  adjusted `NOT_ATTEMPTED` non-call;
- Packet V2 exact context seal; no separate market-data/regime/partial splice;
  exact four-row ledger/source attribution; `ADJUSTED_NOT_ATTEMPTED` identity
  binding with unavailable adjusted source and no raw/private leakage;
  exhaustive successor reason mappings, including mapping/bar stale/conflict,
  classification cases, and privacy-safe stale/future event failure identity;
  packet-wide 10,000 notices distributed across members, 10,001 rejection, a
  representative 50-member/10,000-event production archive, the exact 36
  MiB/max-plus-one byte gate, retry, suppression, redaction, and mandatory
  `NO_TRADE`;
- real Plan-25 archive current-cutoff-date event success and prior-date stale
  event mapping to `EVENT_SOURCE_DATE_STALE`, `COMPONENT_STALE`, and all-null
  `NO_TRADE`;
- observed projection contains completed S20 close/volume, aggregate regime,
  aggregate Industry, retained events, and separately labelled partial state
  only; all private/raw/adjusted/signal/order material remains excluded;
- frozen Plan-20 V1/V2 and Industry V1 regression suites remain unchanged.

Tests assert observable contracts and exact bytes/identities, not private helper
structure. Plan-26 `@v1` assertions are migrated where applicable and rerun from
RED; its 101-test WIP result is not transferred to V2.

## Real current smokes

### Current smoke record and release blockers

Before the production composer existed, the owner supplied a temporary
pre-code composition trace: source-manifest SHA-256
`d485d452dcb25da3c9f8d2c3d8b054f24fcb7703dbd32f3bff1e8448971288be`
and schema-v3 schedule digest
`f4153e628b935be226e807ee241d14471d658ece2102f4d9d9e472431cda9b19`.
That temporary manifest/digest pair is superseded historical repair input. It
is not current acceptance evidence, not a runtime identity, and not an executed
integrated smoke.

Current composer acceptance comes only from fresh tests against the current
production code and mint registries. The replay regression reuses the exact
current acquisition-minted named observations, recomposes the manifest and
schedule, and requires byte-identical manifest bytes plus equal schedule and
identities, including the two-year/prior-date branch. Those tests remain in the
exact 14-suite portfolio and must be rerun after any composer/source/manifest
change.

The fresh current post-close evidence is bound to schedule SHA-256
`f50e7853ce91e3868678b40b5ece79beea0aa469317d348129e96b1c3b71b0a0`,
the 6,611-byte Industry artifact at SHA-256
`1a40e33a0febf458986a178bc76f7b0051f163718f2a8bc11a726ba70a39c0a9`,
and the exact current unfiltered Event artifact at SHA-256
`fe77c222ccf73c9a90b7c94641f6e39055c5a4956467729fabda4c8a9ea4b297`.
The Industry and Event artifacts were parsed, retained, and validated under the
current runtimes together with the exact mapping, raw, and Plan-21 evidence.

The strict one-lease post-close `RELIANCE` positive passed on current bytes for
the 2026-08-26 decision session with 21 raw bars; Market Regime, Industry, and
Packet `OBSERVED`; partial `NOT_APPLICABLE`; Plan 21 `SCREENED`; Plan 22
`SUCCESS`; and guarded retries preserving exact bytes, identities, and original
times.

The mandatory Aug-27 market-hours `RELIANCE` positive passed on frozen
fingerprint
`61d5574bc6ae034cab471d3cc30b1b6d7aa891859c6c48c6eaf60f65224c541d`
during the actual active session. The decision cutoff was
`2026-08-27T04:29:06.612060Z` (`09:59:06` IST), and the effect deadline was
`2026-08-27T04:28:36.612060Z`. Composed schedule SHA-256
`fb4e60b4c9e62887211cd5083403a4b0dfca2ab4b95f1c7415b27c0c8e1ac9ae`
defined 2026-08-27 as `REGULAR`, 09:15–15:30 IST, with S0 2026-07-29 and S20
2026-08-26; the 2026-08-27 mapping observation was
`02e150b0b910f9ebe825b1c77f48126e4a0046073bf24ae767211fe66480bbf3`.

Raw was 21/21 `OBSERVED`; Plan 21 was `SCREENED`; live Plan 22 was `SUCCESS`
before the deadline; Market Data, Market Regime, Industry, and Packet were
`OBSERVED`; Event was `RETAINED`. Packet identity SHA-256 was
`cc3619cddcd2a35c73500947f40db863a5cb56df5a6aa377c2b0d91261556474`,
and context identity SHA-256 was
`e8b0371527994b39d6c905967c7814fce792fee627221cfd54cc51f65285153a`.
The requested partial was truthfully `UNAVAILABLE` /
`PARTIAL_MEMBER_MISSING` with zero rows, separately labelled
`PARTIAL_CURRENT_SESSION`, excluded from the completed grid and Market Regime,
nonfatal, and never substituted. Exact retries preserved bytes, identities, and
original times and caused zero effects; source remained unchanged and all
resources were closed.

The final 14-file focused portfolio passed **844 tests** with `--no-cov`; the
final full suite passed **3,392 tests at 89.52% total coverage** against the
**87%** threshold. Ruff format/lint and Pyright currently pass. Vulture at 80% reports no findings and `git diff --check` passes. `uv build` produced the sdist and wheel. A clean installed-wheel smoke outside the checkout passed on CPython 3.13.7, with all 12 current runtime identities SHA256-shaped.

Eight review blockers are fixed locally without a new subsystem: late
completion-marker retry guards; zero-redirect enforcement; restored global
`ScheduleSession` kind compatibility with the exact `REGULAR`/`SPECIAL` gate
kept Plan-27-only; Industry V1 compatibility; Event legacy adoption; 62-day
month-start acquisition; pre-Plan-22 deadline enforcement; and corrected
Plan-24 wording.

The fresh current-byte genuine IRCTC production negative passed with the exact
`NO_TRADE` outcome: raw `INSUFFICIENT` / `RAW_ACQUISITION_UNAVAILABLE`; Market
Regime V3 insufficient; Plan 22 `NOT_ATTEMPTED` upstream; Industry V2
`UNSUPPORTED` with `MARKET_REGIME_UNAVAILABLE` and
`CLASSIFICATION_MEMBER_UNSUPPORTED`; and Packet insufficient with the exact
ledger, five null AI facts, and mandatory `NO_TRADE`. Guarded V3, Industry,
event, and Packet retries preserved exact bytes, identities, and original times.
All required current smokes have passed: the retained post-close `RELIANCE`
positive, mandatory market-hours `RELIANCE` positive, and genuine IRCTC
negative. The two positive modes remain separate; neither substitutes for the
other. A candidate commit has been created. Exact-SHA functional and provenance approval requires rerun; PR, hosted checks, merge, and closeout remain pending. No acceptance, completion, or
delivery is claimed until the lifecycle is complete. No history/backfill,
provider expansion,
fallback, schedule-source relabeling, or weakening of current-session admission
is authorized.

### Positive current modes

The minimum completion evidence includes one real market-hours observed context:

- exact production schedule, mapping, existing Upstox raw acquisition/query,
  Plan-21 resolver, Plan-22 adapter, retained Industry/event evidence, real
  context/packet archives, and one real lease;
- market-hours cutoff with `S20` equal to the prior completed official session;
- exact `21 * N` completed grid, observed Market Regime, observed Industry, and
  observed packet;
- partial requested and its actual `PARTIAL_CURRENT_SESSION` outcome recorded.
  `OBSERVED` proves its provisional projection; a genuine unavailable/conflicted
  outcome remains non-fatal and must prove the exact non-substitution semantics;
- exact context/packet retry with byte-identical public bytes, original times,
  and all identities.

A second positive post-close/finalized mode SHOULD prove `S20` may be today and
partial is `NOT_APPLICABLE`. If aligned real inputs cannot support that second
mode, the market-hours positive plus explicit partial semantics is the minimum
authorized positive smoke; the missing second mode is recorded as a limit, not
silently claimed.

The positive smoke cannot pass with Market Regime, Industry, or packet
insufficiency. Tool inactivity or missing Plan-20 prospective objects cannot be
used to force a negative result when current approved inputs are complete.

### Negative current disposition

Use one genuine real-current missing/stale/unsupported capability through the
same production request/admission/archive path, without fixtures, fake provider,
provider mutation, or corrupted user data. Prove retained context and packet
`INSUFFICIENT_EVIDENCE`, exact closed reason/ledger attribution, five null AI
fact fields, mandatory `INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED`, and retry
equality. If no genuine negative capability exists, this smoke is `BLOCKED`; a
synthetic test does not replace it.

Smokes record only redacted cohort size, cutoff/resolved session, modes,
source/component/context/packet identities, byte counts, state, partial state,
and retry equality. They do not publish private NSE narrative, Industry rows,
paths, mappings, raw bars, or credentials. They prove current freshness,
temporal integrity, binding, retention, and reproducibility only.

## Gates, reviews, and delivery

Required sequence on the exact candidate:

1. focused RED evidence, then GREEN/refactor focused suites;
2. `ruff format --check .`;
3. `ruff check .`;
4. `pyright`;
5. `vulture src --min-confidence 80`;
6. focused same-pass/Market Regime/Industry/packet tests;
7. full `pytest` with repository 87% coverage threshold;
8. `git diff --check`;
9. `uv build` producing sdist and wheel;
10. installed-wheel/import smoke for exact public Python surfaces, with no CLI;
11. required real positive and negative smokes;
12. author self-review against this first slice and exact file set;
13. independent R3 functional/domain/temporal review;
14. independent security/privacy/provenance review;
15. exact-SHA commit and fresh review after any candidate change;
16. PR hosted Quality/build and GitGuardian;
17. merge only while reviewed SHA and hosted gates match; and
18. lifecycle closeout with reviewed head, merge SHA, artifacts, gates, smokes,
    limits, and residual risk.

Functional review challenges prior-run independence, latest-completed-session
resolution, cutoff/known-at, market-hours/post-close modes, optional partial
suppression, no historical claim, exact 21-session grid, mapping/source
identities, raw/adjusted equality, reason order, prearchive direction candidate,
seal-only retention, Industry reconciliation, packet splicing, mandatory
`NO_TRADE`, and V1/V2 compatibility.
Security/provenance review challenges lease/root authority, no-follow
publication, object/receipt/marker splicing, retry, runtime identities, bounds,
private raw/narrative redaction, credentials, and sanitized failures.

Any source byte change after review invalidates the review. A green build alone
does not authorize release. No direct push to `main`.

## Circuit breaker and remaining lifecycle gates

Required now and not breaker trips: the same-pass private context, Market Regime
V3, Industry V2, packet V2 clean cutover, and the one exact Upstox raw adapter.
They are the least costly correction that makes current availability independent
of prospective Plan-20 objects without changing delivered contracts.

Stop before adding another provider/fallback, generalized registry, historical
availability/replay/backfill, another adjusted lifecycle, unmeasured parallel
orchestration, new delivery surface, attestation subsystem, general news,
Sector mapping, signal, recommendation, position, order, or broker behavior.

Implementation evidence conditions retained by this contract:

1. implementation must prove the frozen row-level current
   receipt/knowledge/mapping/checksum/schedule projections through the existing
   leased effects; otherwise stop before editing a frozen component;
2. the representative maximum valid private context, including optional partial
   rows, must fit 4 MiB or the bound must be re-frozen and independently
   reviewed;
3. the current-byte strict one-lease post-close `RELIANCE` positive has passed;
4. the mandatory Aug-27 market-hours `RELIANCE` positive has separately passed
   on frozen fingerprint
   `61d5574bc6ae034cab471d3cc30b1b6d7aa891859c6c48c6eaf60f65224c541d`,
   with the truthful unavailable partial excluded and no substitution; and
5. the fresh current-byte genuine IRCTC production negative has passed on the
   final source with raw `INSUFFICIENT` / `RAW_ACQUISITION_UNAVAILABLE`, Market
   Regime V3 insufficient, Plan 22 `NOT_ATTEMPTED` upstream, Industry V2
   `UNSUPPORTED` with `MARKET_REGIME_UNAVAILABLE` and
   `CLASSIFICATION_MEMBER_UNSUPPORTED`, Packet insufficient with the exact
   ledger, five null AI facts, mandatory `NO_TRADE`, and all
   V3/Industry/event/Packet retries and original times preserved.

All required current smokes have passed. A candidate commit has been created. Exact-SHA functional and provenance approval requires rerun; PR, hosted checks, merge, and closeout remain pending. No acceptance, completion, or delivery is claimed until the lifecycle
is complete.

## Nonclaims

This current-only design does not claim that historical bars, mappings,
schedules, corporate-action screens, adjusted values, Industry labels, event
notices, or current partial values were available at historical cutoffs. It does
not create a replay, backtest, backfill availability ledger, historical
constituent claim, or as-published revised-source history.

It does not establish provider completeness, authoritative no-corporate-action
proof, strict as-published yfinance authority, absent publisher time, official
Sector taxonomy, general news, automated advice, signal, recommendation,
position, order, broker execution, intraday trading, or effectiveness. Approved
current data means exact admitted evidence only, never a partial-as-complete
bar, mixed price basis, silent provider fallback, inferred value, or unproven
row. `NO_TRADE`, unsupported capability, and insufficient evidence remain
first-class outcomes.
