# Current supplied-cohort research-packet contract

Status: **SUPERSEDED BEFORE DELIVERY — HISTORICAL WIP; 101 FOCUSED TESTS PASSED**
Contract revision: `current-supplied-cohort-research-packet@v1` (**unpublished WIP**)
Issue: [#119 — Sprint 14: integrated current research packet](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119)
Risk: **R3 / High — financial and evidence impact**

## Superseded before delivery

The owner replaced this unpublished packet `@v1` direction with the exact
successor authority in
[Plan 27](27-current-same-pass-market-regime-contract.md):

- `current-same-pass-raw-daily-grid@v1`;
- `current-supplied-cohort-market-regime@v3`;
- `current-supplied-cohort-industry-participation@v2`; and
- `current-supplied-cohort-research-packet@v2`.

Packet `@v1` will not ship. Its WIP implementation path
`src/swing_trading_ai_assistant/research_packet/current_supplied_cohort.py` is
replaced in place by the Plan-27 V2 contract; the exact empty package marker is
`src/swing_trading_ai_assistant/research_packet/__init__.py`. No alias,
compatibility shim, dual contract, second packet module, or second archive
implementation is authorized.

The following `@v1` specification, 101 focused-test result, and repair-oriented
contract detail remain truthful historical WIP evidence. They do not authorize
the Plan-27 candidate, transfer test or review evidence to `@v2`, or establish
delivery. Applicable assertions must be migrated and rerun from RED under Plan
27. Reviews, smokes, gates, lifecycle claims, and file authority for a future
candidate must address Plan 27's exact bytes, closed successor schemas, and
**Exact implementation file set**.

## Authority and lifecycle

Issue #119 originally authorized one current/live owner-private local Python
packet over the exact delivered Sprint 10–13 component contracts. This plan
records the resulting unpublished `@v1` WIP and is no longer implementation
authority. Plan 27 is the active Sprint 14 implementation contract; neither plan
reopens or reinterprets delivered Plan-20 V1/V2 contracts.

The last `@v1` WIP evidence was **101 focused research-packet tests passed with
`--no-cov`**. This remains supporting historical test/repair evidence only.
Packet `@v1` had no completed smoke, independent review, full repository/hosted
gate, delivery, exact-SHA pull request, merge, tracker completion, or closeout.

R3 applies because a cross-component evidence splice can change financial
research context and what an external AI is allowed to know. R4 does not apply:
this slice makes no execution or financial-advice claim, performs no destructive
action, and grants no broker or real-money authority. The repository owner is
the risk owner. The prior WIP test/review state is invalid for a future `@v2`
candidate; Plan 27 requires fresh independent functional and security review.

## Five-line new-module evaluation

1. **Expected value:** integrates delivered facts into one reproducible current research packet.
2. **Scope fit:** directly satisfies Issue #119.
3. **Material data/research risk:** cohort/cutoff/identity splicing and private narrative leakage.
4. **Smallest alternative:** a transient dictionary fails immutable reproducibility.
5. **Decision:** **ACCEPTED**.

This is a module decision, not a provider or source decision. Sprint 14 adds no
provider, acquisition path, source, licence interpretation, or fallback.
Source-use fields come only from an admitted public component value; the
owner-private use restriction comes from the frozen delivered Plan 24/25
contract policy. Every row distinguishes those origins and binds its exact
identities.

## Working-feature-first partition

### FIRST_WORKING_SLICE

- one owner-private local Python
  `current-supplied-cohort-research-packet@v1` contract;
- one explicit exact `1..50` canonical NSE listed-equity cohort, supplied by the
  caller independently of index membership;
- exact Sprint 10 `CurrentCohortMarketDataReportV1` current market-data V1;
- exact Sprint 11 `CurrentSuppliedCohortMarketRegimeReportV2` aggregate;
- exact Sprint 12 literal `INDUSTRY`
  `CurrentIndustryParticipationReportV1` aggregate or its exact typed failure;
- exact Sprint 13 `RetainedCurrentEventNoticeSnapshotV1` or its exact typed
  failure;
- one exact UTC `decision_cutoff` and one exact `decision_session` for every
  admitted component;
- an AI projection containing completed daily close and volume only, Market
  Regime aggregate, Industry aggregate, and per-member retained event notices
  or `NO_MATCHING_NOTICE_IN_SNAPSHOT`;
- event notices as the sole bounded `news_events` capability; no general-news
  claim;
- whole-result insufficiency for missing, stale, future, conflicting,
  cross-cohort, cross-cutoff, unauthorized, or partial-as-complete evidence;
- packet-owned immutable content-addressed retain-before-return storage beneath
  one real `StorageRootLease`;
- retention of both observed and admitted-insufficiency results before either is
  returned to a consumer;
- facts-only consumer policy: an insufficient packet requires explicit
  insufficient information / `NO_TRADE` and cannot be overridden;
- focused RED tests, the required positive observed archive/retry smoke and
  separate retained mandatory-`NO_TRADE` insufficiency smoke, independent
  functional and security review, repository and hosted gates, and
  exact-SHA delivery; and
- local/private use only, with no CLI, API, MCP, UI, notification, or public
  transport.

### LATER_IMPROVEMENTS

- general news, additional providers, or attachment retrieval/content;
- automated acquisition;
- official Sector taxonomy or Industry-to-Sector mapping;
- sentiment, materiality, ranking, or scoring;
- history, backfill, or generalized replay;
- external attestation;
- ordinal-bearing, versioned Plan-25 public event-observation output;
- partial-session AI projection;
- generalized packet, component, provider, feed, archive, or source
  abstractions;
- API, MCP, CLI, UI, notification, or other delivery surfaces;
- Market Structure;
- signals, recommendations, position sizing, orders, or effectiveness claims.

A review finding blocks this first slice only when it identifies a violated
Issue #119 acceptance condition, R3 control, or concrete current safety,
correctness, usability, authorization, privacy, or evidence-integrity failure.
The scope-expansion circuit breaker applies before any later item is added.

## Existing component authority

The projector consumes exact existing result objects. It does not call an
upstream evaluator, acquire data, read an upstream archive, reconstruct a
private handoff, or accept a substitute dictionary.

| Component | Exact admitted type | Required admitted outcome | Packet use |
| --- | --- | --- | --- |
| Sprint 10 current market data | `CurrentCohortMarketDataReportV1` | `COMPLETE` | Exact completed `decision_session` close and volume per member; report/request/source-receipt identities. Open, high, low, and partial snapshots are excluded. |
| Sprint 11 Market Regime V2 | `CurrentSuppliedCohortMarketRegimeReportV2` | `OBSERVED` | Aggregate label, advances, declines, unchanged, comparison session, and exact report/dependency identities. No private member directions. |
| Sprint 12 Industry Participation V1 | `CurrentIndustryParticipationReportV1` or `CurrentIndustryParticipationFailureV1` | `OBSERVED` report | Literal `INDUSTRY` aggregate rows and exact classification/archive/report identities. A failure becomes whole-packet insufficiency. |
| Sprint 13 retained event notices V1 | `RetainedCurrentEventNoticeSnapshotV1` or `CurrentEventNoticeFailureV1` | `RETAINED` snapshot | One result per request member, with admitted notices or `NO_MATCHING_NOTICE_IN_SNAPSHOT`, and exact source/licence/archive identities. A failure becomes whole-packet insufficiency. |

A Sprint 10 or Sprint 11 natural insufficiency remains an exact component result
and becomes one retained whole-packet insufficiency. Industry or event typed
failure behaves the same. No component failure is replaced, retried, neutralized,
or dropped inside this module.

No concrete acceptance blocker currently requires changing a frozen Sprint
10–13 component file. If implementation establishes such a blocker, work stops
and this plan records the violated current acceptance condition before any
component edit. Convenience, broader hardening, or a desire for a common base
type is not a blocker.

## Request, canonical cohort, and closed canonical model

The only request is an immutable Python value:

```python
@dataclass(frozen=True, slots=True, init=False, repr=False)
class CurrentSuppliedCohortResearchPacketRequestV1:
    contract_version: Literal["current-supplied-cohort-research-packet@v1"]
    schema_identity_sha256: str
    configuration_identity_sha256: str
    decision_cutoff: datetime
    decision_session: date
    members: tuple[CurrentEventCohortMemberV1, ...]
    request_identity_sha256: str

    def __init__(
        self,
        *,
        decision_cutoff: datetime,
        decision_session: date,
        members: tuple[CurrentEventCohortMemberV1, ...],
    ) -> None: ...
```

Admission is closed:

- `decision_cutoff` is timezone-aware, uses the UTC singleton, and serializes as
  `YYYY-MM-DDTHH:MM:SS.ffffffZ`;
- `decision_session` is a real `LocalDate` and equals
  `IST_DATE(decision_cutoff)`;
- `members` contains `1..50` exact `CurrentEventCohortMemberV1` values, sorted by
  ISIN, with unique ISIN and symbol;
- every member has `exchange == "NSE"`,
  `listed_equity_segment == "EQUITY"`, and an effective interval covering
  `decision_session`;
- the tuple retains ISIN, exchange, listed-equity segment, symbol, effective
  interval, and provider-mapping revision; and
- no field carries an index name, index-membership assertion, path, provider
  credential, raw payload, component result, or consumer prompt.

This is a supplied-cohort capability check, not a Nifty 50, Nifty Next 50, or
Nifty 100 membership check. The composing workflow remains responsible for any
index-scope claim.

The following aliases govern every new representation:

```text
Sha256       = str matching [0-9a-f]{64}
UtcInstant   = str matching YYYY-MM-DDTHH:MM:SS.ffffffZ
LocalDate    = str matching YYYY-MM-DD and round-tripping through date
DecimalText  = finite positive Decimal rendered without exponent or redundant zeroes
UInt         = JSON integer, not bool, >= 0
PositiveInt  = JSON integer, not bool, >= 1
```

Canonical JSON is UTF-8, lexicographically sorted object keys, compact
separators, `ensure_ascii=false`, `allow_nan=false`, no duplicate keys, and
exactly one trailing LF. JSON object key order is therefore lexical; the field
lists below are declaration/projection order, and every tuple has the explicit
semantic order stated below. `CJ(x)` means those exact canonical bytes.
`SHA(x)` means lowercase `sha256(CJ(x)).hexdigest()`. Every closed object rejects
unknown keys. Every identity formula excludes only the identity field it names.

The request canonical projection has these fields in declaration order:

| Field | Exact JSON type and nullability |
| --- | --- |
| `contract_version` | literal string `current-supplied-cohort-research-packet@v1` |
| `schema_identity_sha256` | `Sha256`, non-null |
| `configuration_identity_sha256` | `Sha256`, non-null |
| `decision_cutoff` | `UtcInstant`, non-null |
| `decision_session` | `LocalDate`, non-null |
| `members` | array of `1..50` exact member objects, non-null, sorted by `isin` |
| `request_identity_sha256` | `Sha256`, non-null |

Each member object contains, in declaration order, `isin: str`,
`exchange: "NSE"`, `listed_equity_segment: "EQUITY"`, `symbol: str`,
`effective_from: LocalDate`, `effective_through: LocalDate`, and
`provider_mapping_revision: str`. The request identity is
`SHA(request fields through members)`.

## Cohort reconciliation: unequal identities by design

Sprint 10 hashes its manifest revision, `selected_at`, and sorted `(isin,
symbol)` members. Sprint 11 and Sprint 12 bind that opaque Sprint-10 cohort
identity. Sprint 13 instead hashes the richer member projection:

```text
(isin, exchange, listed_equity_segment, symbol,
 effective_from, effective_through, provider_mapping_revision)
```

These two cohort hashes are not compared for equality. Equality would equate
incompatible projections and is a closed failure.

The module establishes the join as follows:

1. validate the full request member tuple;
2. project it to sorted `(isin, symbol)` pairs;
3. require exact equality with the complete Sprint-10 report member tuple;
4. require one common Sprint-10 cohort identity and size across market data,
   Market Regime V2, and Industry Participation V1;
5. require exact equality between the full request tuple and every retained
   Sprint-13 member value, including provider-mapping revision and effective
   interval;
6. recompute and verify the Sprint-13 richer cohort identity under its delivered
   projection; and
7. compute `cohort_projection_binding_identity_sha256` as
   `SHA({"contract_version":"current-supplied-cohort-cohort-binding@v1",
   "event_notice_cohort_identity_sha256":event cohort SHA,
   "market_data_cohort_identity_sha256":Sprint-10 cohort SHA,
   "market_data_members":[{"isin":...,"symbol":...}],
   "request_members":[full member objects]})`.

No symbol-only join, hash-equality shortcut, member dropping, denominator
reduction, alternate mapping, or fallback is allowed.

## Retain-before-return API

The projector and candidate are module-private. There is no public
`project_*`, candidate constructor, candidate serializer, or unretained
fact-bearing return:

```python
def _project_current_supplied_cohort_research_packet_v1(
    request: CurrentSuppliedCohortResearchPacketRequestV1,
    market_data: CurrentCohortMarketDataReportV1,
    market_regime: CurrentSuppliedCohortMarketRegimeReportV2,
    industry_participation: (
        CurrentIndustryParticipationReportV1 | CurrentIndustryParticipationFailureV1
    ),
    event_notices: (RetainedCurrentEventNoticeSnapshotV1 | CurrentEventNoticeFailureV1),
) -> _CurrentSuppliedCohortResearchPacketCandidateV1: ...


def build_and_retain_current_supplied_cohort_research_packet_v1(
    request: CurrentSuppliedCohortResearchPacketRequestV1,
    market_data: CurrentCohortMarketDataReportV1,
    market_regime: CurrentSuppliedCohortMarketRegimeReportV2,
    industry_participation: (
        CurrentIndustryParticipationReportV1 | CurrentIndustryParticipationFailureV1
    ),
    event_notices: (RetainedCurrentEventNoticeSnapshotV1 | CurrentEventNoticeFailureV1),
    archive: CurrentResearchPacketArchivePortV1,
    lease: StorageRootLease,
) -> (
    RetainedCurrentSuppliedCohortResearchPacketV1
    | CurrentResearchPacketArchiveFailureV1
): ...
```

The public builder exact-type guards the request and four component values,
requires an explicit archive capability and a real live `StorageRootLease`,
builds one private candidate, and immediately passes it to the archive. The
archive port and file implementation remain directly testable as an effect
boundary, but their packet parameter is the module-private candidate type and
they cannot mint or return an unretained public packet.

Wrong top-level types, subclasses, malformed request values, unsupported
contract/schema versions, or packet runtime-identity failure raise sanitized
`TypeError` or `ValueError` before a candidate exists. Projection performs no
filesystem, network, provider, clock, environment, randomness, subprocess,
logging, or mutation work. It accepts same-owner in-process exact component
values, not caller-supplied canonical JSON or generic mappings, and neither
calls an upstream evaluator nor imports or reconstructs a private handoff.

## Time and no-future-data admission

The request owns the sole decision boundary:

```text
knowledge_cutoff == decision_cutoff
IST_DATE(decision_cutoff) == decision_session
```

An observed packet requires all of the following:

- Sprint-10 `invocation_cutoff == decision_cutoff`;
- every Sprint-10 completed fact has `session == decision_session`,
  `freshness_state == FRESH`, and `data_cutoff`, `published_at`, and `known_at`
  at or before `decision_cutoff`;
- no partial snapshot supplies or modifies close, volume, session, or freshness.
- Market Regime V2 has exact `decision_cutoff` and `decision_session` equality;
- Industry Participation V1 has exact `decision_cutoff` and
  `decision_session` equality, `known_at <= decision_cutoff`, and its existing
  same-IST-date rule remains true;
- the retained event snapshot has `known_at <= decision_cutoff`, its
  `IST_DATE(known_at)` equals its exact source filename date, and that filename
  date equals `IST_DATE(decision_cutoff)` under the delivered Sprint-13 grammar;
  every admitted notice's parsed broadcast, receipt, and dissemination date is
  in inclusive `[source_date - 1 day, source_date]`; and every admitted member
  interval covers that source date; and
- every component identity and component-owned timestamp remains internally
  valid under its delivered contract.

A valid Sprint-10 `COMPLETE` report may contain prior completed facts and a
current `PARTIAL_CURRENT_SESSION`. That upstream combination cannot satisfy this
packet's same-session `OBSERVED` contract: the partial session is the
`IST_DATE(invocation_cutoff)`, while every completed fact must equal
`decision_session == IST_DATE(decision_cutoff)`. The packet is therefore
whole-result `INSUFFICIENT_EVIDENCE` with
`DECISION_SESSION_MISMATCH`; its four AI facts are null, the partial is omitted,
and it never substitutes for or modifies completed evidence. This is not
`PARTIAL_AS_COMPLETE`, which applies only to malformed or forged evidence that
uses a partial to supply or alter completed facts.

`packet_retained_at` is archive-owned and is not a knowledge cutoff, publisher
time, component `known_at`, decision time, or market time. First archive success
samples this exact UTC retention instant only after the full packet object is
stably published, then publishes and verifies the receipt and completion marker
before return. It also requires `decision_cutoff <= packet_retained_at`. Retry
returns the original retained value and never replaces its timestamp.

## States, reasons, precedence, suppression, and exact upstream mapping

The packet has exactly two domain states:

```text
CurrentResearchPacketEvidenceStateV1 = Literal[
  "OBSERVED",
  "INSUFFICIENT_EVIDENCE",
]
```

`OBSERVED` has four non-null fact projections, an empty reason tuple, and
`required_consumer_outcome = null`. `INSUFFICIENT_EVIDENCE` has the same closed
AI-projection object with all four fact fields `null`, a nonempty ordered reason
tuple, and
`required_consumer_outcome =
"INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"`. Component and source ledgers
remain present; no partial fact projection remains.

Closed packet reasons, in rendering order, are:

```text
1.  MARKET_DATA_UNAVAILABLE
2.  MARKET_REGIME_UNAVAILABLE
3.  INDUSTRY_PARTICIPATION_UNAVAILABLE
4.  EVENT_NOTICES_UNAVAILABLE
5.  SOURCE_USE_UNAUTHORIZED
6.  COMPONENT_IDENTITY_INVALID
7.  COHORT_PROJECTION_MISMATCH
8.  DECISION_CUTOFF_MISMATCH
9.  DECISION_SESSION_MISMATCH
10. COMPONENT_FUTURE_KNOWN
11. COMPONENT_STALE
12. COMPONENT_CONFLICTED
13. PARTIAL_AS_COMPLETE
```

The mapping below is exhaustive over the delivered closed Sprint 10–13 result
states and reasons. Every non-success component also contributes its component
`*_UNAVAILABLE` reason. Exact upstream reasons remain in the component-ledger
row; the packet adds only the listed packet reasons:

| Component outcome or exact reason | Additional packet reason |
| --- | --- |
| Sprint 10 `COMPLETE` with `reasons == ()` | none |
| Sprint 10 `INSUFFICIENT_EVIDENCE` | `MARKET_DATA_UNAVAILABLE` |
| `COHORT_INVALID`, `OUT_OF_COHORT` | `COHORT_PROJECTION_MISMATCH` |
| `IDENTITY_AMBIGUOUS` | `COMPONENT_CONFLICTED` |
| `IDENTITY_STALE`, `FRESHNESS_STALE` | `COMPONENT_STALE` |
| `IDENTITY_UNRESOLVED`, `DAILY_BAR_MISSING`, `DAILY_BAR_INVALID`, `SOURCE_RECEIPT_MISSING`, `REQUEST_BOUND_EXCEEDED`, `PROVIDER_UNAVAILABLE`, `CANCELLED` | no reason beyond `MARKET_DATA_UNAVAILABLE` |
| valid Sprint-10 `COMPLETE` report with prior completed facts and a current `PARTIAL_CURRENT_SESSION` | `DECISION_SESSION_MISMATCH` from the completed facts; no `PARTIAL_AS_COMPLETE` |
| malformed or forged evidence that uses `PARTIAL_CURRENT_SESSION` to supply or alter completed facts | `PARTIAL_AS_COMPLETE` |
| Sprint 11 V2 `OBSERVED` with `reasons == ()` | none |
| Sprint 11 V2 `INSUFFICIENT_EVIDENCE` | `MARKET_REGIME_UNAVAILABLE` |
| `RAW_V1_CLOSURE_INVALID`, `ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID` | `COMPONENT_IDENTITY_INVALID` |
| `CORPORATE_ACTION_SCREEN_INSUFFICIENT` | no reason beyond `MARKET_REGIME_UNAVAILABLE` |
| `RAW_ADJUSTED_DIRECTION_CONFLICT` | `COMPONENT_CONFLICTED` |
| Sprint 12 `OBSERVED` report with `reasons == ()` | none |
| Sprint 12 `MALFORMED_EVIDENCE`, `UNSUPPORTED_CAPABILITY`, or `INSUFFICIENT_EVIDENCE` failure | `INDUSTRY_PARTICIPATION_UNAVAILABLE` |
| `MARKET_REGIME_UNAVAILABLE` | `MARKET_REGIME_UNAVAILABLE` |
| `CLASSIFICATION_ARTIFACT_MALFORMED` | `COMPONENT_IDENTITY_INVALID` |
| `CLASSIFICATION_AMBIGUOUS`, `CLASSIFICATION_CONFLICTING` | `COMPONENT_CONFLICTED` |
| `COHORT_BINDING_MISMATCH`, `MEMBER_IDENTITY_MISMATCH` | `COHORT_PROJECTION_MISMATCH` |
| `CLASSIFICATION_FUTURE_KNOWN` | `COMPONENT_FUTURE_KNOWN` |
| `CLASSIFICATION_SESSION_STALE` | `COMPONENT_STALE` |
| `CLASSIFICATION_ARTIFACT_MISSING`, `CLASSIFICATION_SOURCE_UNSUPPORTED`, `CLASSIFICATION_TIER_UNSUPPORTED`, `CLASSIFICATION_MEMBER_UNSUPPORTED`, `CLASSIFICATION_ARCHIVE_FAILED` | no reason beyond `INDUSTRY_PARTICIPATION_UNAVAILABLE` |
| Sprint 13 `RETAINED` snapshot | none |
| Sprint 13 `MALFORMED_EVIDENCE`, `UNSUPPORTED_CAPABILITY`, `INSUFFICIENT_EVIDENCE`, or `CONFLICTED_EVIDENCE` failure | `EVENT_NOTICES_UNAVAILABLE` |
| `EVENT_SOURCE_UNAUTHORIZED`, `EVENT_SOURCE_MISMATCH` | `SOURCE_USE_UNAUTHORIZED` |
| `EVENT_ARTIFACT_IDENTITY_MISMATCH`, `EVENT_ARTIFACT_MALFORMED`, `EVENT_HEADER_MISMATCH`, `EVENT_BOUNDS_EXCEEDED`, `EVENT_TIME_MALFORMED`, `EVENT_RUNTIME_IDENTITY_INVALID` | `COMPONENT_IDENTITY_INVALID` |
| `EVENT_SOURCE_DATE_FUTURE` | `COMPONENT_FUTURE_KNOWN` |
| `EVENT_SOURCE_DATE_STALE` | `COMPONENT_STALE` |
| `EVENT_COHORT_INVALID`, `EVENT_EXCHANGE_UNSUPPORTED`, `EVENT_OUT_OF_COHORT` | `COHORT_PROJECTION_MISMATCH` |
| `EVENT_SYMBOL_AMBIGUOUS`, `EVENT_DUPLICATE`, `EVENT_CONFLICTED` | `COMPONENT_CONFLICTED` |
| `CORRECTION_LINEAGE_UNAVAILABLE`, `EVENT_ARCHIVE_FAILED`, `EVENT_ARTIFACT_MISSING` | no reason beyond `EVENT_NOTICES_UNAVAILABLE` |

Only the accepted public result types participate in this table. Sprint-13
`PARSED` and `PROJECTED` private intermediates and Sprint-11 V1/private-grid
values are not accepted inputs and fail stage 0 exact-type admission.

Upstream state-to-reason admission is also exact. Sprint-10 insufficiency
requires one or more declaration-ordered `CurrentCohortReasonV1` values, while
complete requires none. Sprint-11 V2 insufficiency requires exactly one of its
four listed reasons, while observed requires none. Sprint-12 failure state is
`MALFORMED_EVIDENCE` for artifact-malformed, ambiguous, conflicting,
cohort-binding, or member-identity reasons; `UNSUPPORTED_CAPABILITY` for
source-, tier-, or member-unsupported reasons; otherwise
`INSUFFICIENT_EVIDENCE`, with state precedence malformed, unsupported, then
insufficient. Sprint-13 reason state is exact: missing/future/stale/correction-
lineage/runtime/archive reasons are `INSUFFICIENT_EVIDENCE`; unauthorized,
source-mismatch, or exchange-unsupported reasons are
`UNSUPPORTED_CAPABILITY`; artifact-identity/malformed/header/bounds/time/cohort/
symbol/out-of-cohort reasons are `MALFORMED_EVIDENCE`; duplicate/conflicted
reasons are `CONFLICTED_EVIDENCE`. Multi-reason Sprint-13 state precedence is
malformed, unsupported, conflicted, then insufficient. Any other state/reason
pair is a packet-side component-identity failure.

`EVENT_EXCHANGE_UNSUPPORTED` maps to cohort mismatch because the packet request
admits only exact NSE `EQUITY` members; it does not reinterpret that reason as
source authorization. An otherwise success-state component that fails the
packet's exact public-contract revalidation contributes
`COMPONENT_IDENTITY_INVALID`; this is distinct from a valid typed upstream
failure reporting malformed source evidence.

Processing and suppression are frozen:

| Stage | Checks | Suppression |
| --- | --- | --- |
| 0 | exact request/component/lease types, explicit archive capability, and packet schema/config/runtime constants | failure raises before any packet; no later stage |
| 1 | for each exact admitted component type, only its delivered outcome discriminator, reason membership/order/uniqueness, outcome nullability, and typed-failure `cohort_size` shape | an invalid outcome shape becomes that slot's fixed sanitized `PACKET_INVALID_COMPONENT` ledger projection and suppresses all later checks for that component; a valid Sprint-12/13 typed failure maps above, skips stage 2, and suppresses only later checks that require success fields; an admitted non-null Sprint-13 failure `cohort_size` still reaches stage 3; a Sprint-10/11 report outcome remains pending until stage 2 |
| 2 | every Sprint-10/11 report outcome, including natural insufficiency, and every Sprint-12/13 success result: exact public structure, delivered constants, canonical digest or retained identity, and self-consistency | an invalid value becomes that slot's fixed sanitized `PACKET_INVALID_COMPONENT` ledger projection; no malformed upstream field is serialized; a valid Sprint-10/11 natural insufficiency maps above and suppresses only later checks that require success fields; its admitted cohort identity and non-null failure cohort size still reach stage 3; other valid successes continue |
| 3 | surviving request-to-Sprint-10 and request-to-Sprint-13 joins plus admitted common Sprint-10 cohort identities/sizes; absent failure fields are not invented | cohort failure adds `COHORT_PROJECTION_MISMATCH` and suppresses dependent time and aggregate reconciliation, not independent component checks |
| 4 | exact cutoff and decision-session cross-bindings, recording each surviving component's `cutoff_and_session_match` | a mismatch adds the matching cutoff/session reason and suppresses dependent temporal interpretation for that component |
| 5 | no-future, freshness, source-date, and partial exclusion | runs only when that component's stage-4 `cutoff_and_session_match` is true; a future-known finding suppresses stale classification of that same clock |
| 6 | Market Regime counts/label and Industry-to-Regime equalities | failure adds `COMPONENT_IDENTITY_INVALID`; no partial aggregate is retained |
| 7 | closed observed/insufficient projection and canonical packet-object construction | any domain reason selects the insufficient projection; packet-size/archive-structure failure is not a domain reason |
| 8 | immutable archive, receipt, marker, final re-read, and retained-result reconstruction | any failure returns only `CurrentResearchPacketArchiveFailureV1` |

Reasons are collected only from checks whose prerequisites survived, then
deduplicated and rendered in the global order. This suppression is part of the
configuration identity.

## Trust model and component reconciliation

The boundary is same-owner, same-process composition. It does not establish
which evaluator created a Python value. For every publicly available exact
component type the packet revalidates:

- exact Python type with subclasses rejected;
- delivered contract/schema/calculation/runtime constants that the type exposes;
- every public field's exact structure, enum membership, ordering, uniqueness,
  type, nullability, timestamp/Decimal grammar, and bound;
- canonical bytes and every publicly recomputable report, request, artifact,
  snapshot, archive, receipt, retained, cohort, and runtime/source-at-rest digest;
- success/failure state-to-reason and success/failure nullability;
- member, count, source/fact identity, and temporal self-consistency; and
- all cross-component bindings listed here.

Plan 25's event-observation identity preimage includes a private ordinal that
`RetainedCurrentEventNoticeSnapshotV1` does not expose. Sprint 14 therefore
treats `observation_identity_sha256` as an opaque upstream binding: it validates
exact digest syntax and global uniqueness across admitted notices, but does not
recompute it, recover an ordinal, or claim producer authenticity. Brute-forcing
ordinals `1..10,000` per notice is not a first-slice requirement.
`deduplication_identity_sha256` remains publicly derivable from the exact notice
fields and is recomputed. The packet also recomputes every publicly derivable
event outer identity—cohort, snapshot, archive, receipt, and retained—and
requires those formulas to bind the exact notice narrative, member, source, and
date values. Duplicate opaque observation or deduplication identities are
rejected globally.

It does not claim evaluator origin, reread any upstream archive, verify private
handoffs or seals, prove upstream archive authenticity, attest executed bytes,
or resist a same-owner actor that coherently constructs a replacement value and
recomputes every public deterministic identity. Stronger producer
authentication/attestation, including ordinal-bearing versioned Plan-25 output,
is later-only. Frozen Sprint 10–13 component files are unchanged.

An observed Market Regime V2 report additionally requires
`advances + declines + unchanged == cohort_size` and the delivered label rule:
`BROAD_ADVANCE` iff advances meet the inclusive 60% threshold,
`BROAD_DECLINE` iff declines meet it, otherwise `MIXED_PARTICIPATION`.

Industry-to-Market-Regime reconciliation requires every equality below:

```text
industry.market_regime_report_identity_sha256 == regime.report_identity_sha256
industry.cohort_identity_sha256               == regime.cohort_identity_sha256
industry.cohort_size                          == regime.cohort_size
industry.decision_cutoff                      == regime.decision_cutoff
industry.decision_session                     == regime.decision_session
industry.comparison_session                   == regime.comparison_session
industry.market_regime_advances               == regime.advances
industry.market_regime_declines               == regime.declines
industry.market_regime_unchanged               == regime.unchanged
sum(row.member_count)                         == industry.cohort_size
sum(row.advances)                             == regime.advances
sum(row.declines)                             == regime.declines
sum(row.unchanged)                            == regime.unchanged
row.member_count                              == row.advances + row.declines
                                                  + row.unchanged
```

Industry rows must also be nonempty, exact `IndustryCountV1` values, unique and
ascending by exact Industry string; the report must retain literal
`classification_tier == "INDUSTRY"`, `source_authority == "NSE_INDICES"`, its
exact delivered source URL, four null publisher fields, `evidence_state ==
"OBSERVED"`, and `reasons == ()`. The packet validates the public
`market_regime_handoff_identity_sha256` only as a non-null digest; without the
private handoff it does not claim to re-prove that handoff's origin or contents.

## Exact packet and AI projections

The module-private candidate's canonical projection is the full packet object
stored in `packet-*.json`. It contains these fields in declaration order:

| Field | Exact JSON type and nullability |
| --- | --- |
| `contract_version` | packet contract literal, non-null |
| `schema_identity_sha256` | `Sha256`, non-null |
| `configuration_identity_sha256` | `Sha256`, non-null |
| `runtime_code_identity_sha256` | `Sha256`, non-null |
| `request_identity_sha256` | `Sha256`, non-null |
| `decision_cutoff` | `UtcInstant`, non-null |
| `decision_session` | `LocalDate`, non-null |
| `knowledge_cutoff` | `UtcInstant`, non-null and equal to `decision_cutoff` |
| `cohort_size` | `PositiveInt` in `1..50` |
| `market_data_cohort_identity_sha256` | `Sha256` when the supplied report exposes a valid digest, otherwise null |
| `event_notice_cohort_identity_sha256` | `Sha256` for retained event input, otherwise null |
| `cohort_projection_binding_identity_sha256` | `Sha256` when cohort reconciliation succeeds, otherwise null |
| `component_ledger` | exactly four component-ledger rows in fixed order |
| `source_attributions` | exactly four source-attribution rows in fixed order |
| `evidence_state` | `OBSERVED` or `INSUFFICIENT_EVIDENCE` |
| `reasons` | ordered unique array of closed packet reason strings |
| `required_consumer_outcome` | null for observed; required literal for insufficient |
| `ai_projection` | exact observed or insufficient projection, non-null |
| `packet_identity_sha256` | `Sha256`, non-null |

`packet_identity_sha256 = SHA(all preceding packet fields)`. The fixed ledger
and attribution order is `MARKET_DATA_V1`, `MARKET_REGIME_V2`,
`INDUSTRY_PARTICIPATION_V1`, `EVENT_NOTICES_V1`.

Each component-ledger row has, in order:

```text
component_name: one fixed component literal
contract_version: nonempty str | null
component_state: exact delivered state str | "PACKET_INVALID_COMPONENT"
schema_identity_sha256: Sha256 | null
runtime_code_identity_sha256: Sha256 | null
result_identity_kind: "UPSTREAM_RESULT" | "PACKET_FAILURE_PROJECTION"
result_identity_sha256: Sha256
failure_cohort_size: PositiveInt | null
identity_bindings: array[NamedIdentityV1]
maximum_known_at: UtcInstant | null
component_reasons: array[exact delivered reason str]
packet_validation_reasons: array[closed packet reason str]
component_ledger_row_identity_sha256: Sha256
```

`NamedIdentityV1` is the closed object `{name: nonempty str,
identity_sha256: Sha256}`. Names are unique. `UPSTREAM(x)` means the exact
public identity `x`, is always non-null, and uses
`result_identity_kind = "UPSTREAM_RESULT"`. `FAILURE_PROJECTION` means
`result_identity_kind = "PACKET_FAILURE_PROJECTION"` and the non-null packet
identity:

```text
SHA({
  "component_name": component_name,
  "component_state": component_state,
  "component_reasons": component_reasons,
  "failure_cohort_size": failure_cohort_size,
  "packet_validation_reasons": packet_validation_reasons
})
```

It is never labelled as an upstream result identity. `UNAVAILABLE(component)`
is `MARKET_DATA_UNAVAILABLE`, `MARKET_REGIME_UNAVAILABLE`,
`INDUSTRY_PARTICIPATION_UNAVAILABLE`, or `EVENT_NOTICES_UNAVAILABLE` for the
matching component. `MAPPED(component, reasons)` is the ordered unique result
of `UNAVAILABLE(component)` plus exactly the additional packet reasons assigned
to those delivered reasons by the exhaustive mapping above, rendered in the
global packet-reason order.

The matrix below is the closed component-ledger projection. A slash-separated
schema/runtime cell gives the exact values of those two row fields. Bracketed
binding names are the entire array in that order; `[]` means exactly empty.
`ATTR(component)` is the ordered unique subset of later surviving stage 3–6
findings attributed as follows: `COHORT_PROJECTION_MISMATCH` is attached to
every component row whose request/member/cohort-size assertion failed and to
both rows of any failed component-to-component cohort equality;
`DECISION_CUTOFF_MISMATCH` or `DECISION_SESSION_MISMATCH` is attached to each
row that exposes the unequal cutoff or session; `COMPONENT_FUTURE_KNOWN` and
`COMPONENT_STALE` are attached only to the row owning the offending public
clock or source date; `PARTIAL_AS_COMPLETE` is attached only to
`MARKET_DATA_V1`; and a stage-6 `COMPONENT_IDENTITY_INVALID` is attached to
every row participating in the failed Market-Regime/Industry equality. No
suppressed check contributes an attribution. `ATTR(component)` is empty when
all surviving checks pass and is always rendered in global packet-reason order.

| Component and outcome | `contract_version` | `component_state` | schema/runtime | result kind and exact identity | exact cohort-size rule | exact `identity_bindings` | `maximum_known_at` | `component_reasons` | `packet_validation_reasons` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `MARKET_DATA_V1` success report | `"current-supplied-cohort-market-data@v1"` | `"COMPLETE"` | delivered `CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1` / `current_cohort_runtime_code_identity_v1()` copied from `schema_identity_sha256` / `code_identity` | `UPSTREAM(report.report_identity_sha256)` | `failure_cohort_size = null`; `len(report.members)` is `1..50` and must equal request size | `[REQUEST, REPORT, SOURCE_RECEIPT:<isin>...]`; receipts are one per member in request order | `MAX(member.completed_daily.known_at)` | `[]` | `ATTR(MARKET_DATA_V1)` |
| `MARKET_DATA_V1` natural insufficiency report | `"current-supplied-cohort-market-data@v1"` | `"INSUFFICIENT_EVIDENCE"` | same delivered non-null values as the success row | `UPSTREAM(report.report_identity_sha256)` | `failure_cohort_size = null`; the delivered report exposes no cohort size and `members = null` | `[REQUEST, REPORT]`; both identities are non-null `Sha256`, so the array is never empty | `null` | one or more unique `CurrentCohortReasonV1` strings in declaration order | ordered unique union of `MAPPED(MARKET_DATA_V1, component_reasons)` and surviving `ATTR(MARKET_DATA_V1)` |
| `MARKET_REGIME_V2` success report | `"current-supplied-cohort-market-regime@v2"` | `"OBSERVED"` | delivered `SCHEMA_IDENTITY_SHA256` / `current_supplied_cohort_market_regime_runtime_code_identity_v2()` copied from the report | `UPSTREAM(report.report_identity_sha256)` | `failure_cohort_size = null`; `report.cohort_size` is `1..50` and must equal request/Sprint-10 size | `[RAW_REPORT, CORPORATE_ACTION_SCREEN, ADJUSTED_HANDOFF, REPORT]`; all are non-null `Sha256` | `null`; the public V2 report exposes no `known_at` | `[]` | `ATTR(MARKET_REGIME_V2)` |
| `MARKET_REGIME_V2` natural insufficiency report | `"current-supplied-cohort-market-regime@v2"` | `"INSUFFICIENT_EVIDENCE"` | same delivered non-null values as the success row | `UPSTREAM(report.report_identity_sha256)` | if `cohort_size` is `1..50`, `cohort_identity_sha256` must be `Sha256`, `failure_cohort_size = cohort_size`, and both admitted values participate in stage 3; the delivered raw-closure-invalid sentinel is exactly `cohort_size == 0`, `cohort_identity_sha256 == ""`, and `failure_cohort_size = null` | take `[RAW_REPORT, CORPORATE_ACTION_SCREEN, ADJUSTED_HANDOFF]` in that order, omit each exact `""` dependency identity, reject any other non-`Sha256`, then append non-null `REPORT`; therefore the array is never empty and an empty string is never serialized as `Sha256` | `null`; the public V2 report exposes no `known_at` | exactly one of `RAW_V1_CLOSURE_INVALID`, `CORPORATE_ACTION_SCREEN_INSUFFICIENT`, `ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID`, `RAW_ADJUSTED_DIRECTION_CONFLICT` | ordered unique union of `MAPPED(MARKET_REGIME_V2, component_reasons)` and surviving `ATTR(MARKET_REGIME_V2)` |
| `INDUSTRY_PARTICIPATION_V1` success report | `"current-supplied-cohort-industry-participation@v1"` | `"OBSERVED"` | delivered `SCHEMA_IDENTITY_SHA256` / `current_industry_participation_runtime_code_identity_v1()` copied from the report | `UPSTREAM(report.report_identity_sha256)` | `failure_cohort_size = null`; `report.cohort_size` is `1..50` and must equal request/Sprint-10/Market-Regime size | `[MARKET_REGIME_REPORT, MARKET_REGIME_HANDOFF, CLASSIFICATION_INPUT, ARTIFACT, SNAPSHOT, ARCHIVE, ARCHIVE_RECEIPT, REPORT]`; all are non-null `Sha256` | exact `report.known_at` | `[]` | `ATTR(INDUSTRY_PARTICIPATION_V1)` |
| `INDUSTRY_PARTICIPATION_V1` typed failure | `null`; the delivered failure type exposes no contract version | exactly one of `"MALFORMED_EVIDENCE"`, `"UNSUPPORTED_CAPABILITY"`, `"INSUFFICIENT_EVIDENCE"` as derived from its reasons under the precedence above | `null` / `null`; the delivered failure exposes neither identity | `FAILURE_PROJECTION`; no upstream result identity exists | `failure_cohort_size = null`; the delivered failure exposes no cohort size | `[]` | `null` | one or more unique Sprint-12 reasons in delivered `_REASON_ORDER` | `MAPPED(INDUSTRY_PARTICIPATION_V1, component_reasons)`; no later component check has a surviving prerequisite |
| `EVENT_NOTICES_V1` retained success | `"current-supplied-cohort-event-notice@v1"` | `"RETAINED"` | delivered `EVENT_NOTICE_SCHEMA_IDENTITY_SHA256` / `current_event_notice_runtime_code_identity_v1()` copied from the retained value | `UPSTREAM(retained.retained_identity_sha256)` | `failure_cohort_size = null`; `cohort_size == member_count == len(members) == request size` in `1..50` | `[ARTIFACT, SNAPSHOT, ARCHIVE, RECEIPT, RETAINED]`; all are non-null `Sha256` | exact `retained.known_at` | `[]` | `ATTR(EVENT_NOTICES_V1)` |
| `EVENT_NOTICES_V1` typed failure | `null`; the delivered failure type exposes no contract version | exactly one of `"MALFORMED_EVIDENCE"`, `"UNSUPPORTED_CAPABILITY"`, `"INSUFFICIENT_EVIDENCE"`, `"CONFLICTED_EVIDENCE"` as derived from its reasons under the precedence above | `null` / `null`; the delivered failure exposes neither identity | `FAILURE_PROJECTION`; no upstream result identity exists | `failure_cohort_size = failure.cohort_size`; it is either `null` or an exact non-bool integer in `1..50`, and a non-null value participates in the request-size stage-3 equality | `[]` | `null` | one or more unique Sprint-13 reasons in delivered `_REASON_ORDER` | ordered unique union of `MAPPED(EVENT_NOTICES_V1, component_reasons)` and surviving `ATTR(EVENT_NOTICES_V1)`; only the non-null failure-cohort-size stage-3 check can add to the mapped reasons |
| any `MARKET_DATA_V1` packet-invalid value | `null` | `"PACKET_INVALID_COMPONENT"` | `null` / `null` | `FAILURE_PROJECTION` over this fixed row | `null` | `[]` | `null` | `[]` | `[MARKET_DATA_UNAVAILABLE, COMPONENT_IDENTITY_INVALID]` |
| any `MARKET_REGIME_V2` packet-invalid value | `null` | `"PACKET_INVALID_COMPONENT"` | `null` / `null` | `FAILURE_PROJECTION` over this fixed row | `null` | `[]` | `null` | `[]` | `[MARKET_REGIME_UNAVAILABLE, COMPONENT_IDENTITY_INVALID]` |
| any `INDUSTRY_PARTICIPATION_V1` packet-invalid value | `null` | `"PACKET_INVALID_COMPONENT"` | `null` / `null` | `FAILURE_PROJECTION` over this fixed row | `null` | `[]` | `null` | `[]` | `[INDUSTRY_PARTICIPATION_UNAVAILABLE, COMPONENT_IDENTITY_INVALID]` |
| any `EVENT_NOTICES_V1` packet-invalid value | `null` | `"PACKET_INVALID_COMPONENT"` | `null` / `null` | `FAILURE_PROJECTION` over this fixed row | `null` | `[]` | `null` | `[]` | `[EVENT_NOTICES_UNAVAILABLE, COMPONENT_IDENTITY_INVALID]` |

The four packet-invalid rows above are the only case-4 representation. The
packet copies no contract version, state, reason, cohort size, identity,
timestamp, or binding from the invalid upstream value. This applies whether
stage 1 rejects its outcome shape or stage 2 rejects its public contract or
identity. The component-ledger-row identity is
`SHA(all row fields before component_ledger_row_identity_sha256)`.

Each source-attribution row has, in order:

```text
component_name: one fixed component literal
attribution_state: "BOUND" | "UNAVAILABLE"
source_kind: "OPAQUE_RETAINED_MARKET_DATA_RECEIPTS"
           | "DETERMINISTIC_DERIVED_MARKET_REGIME"
           | "NSE_INDICES_INDUSTRY_CLASSIFICATION"
           | "NSE_EQUITY_EVENT_NOTICES"
source_authority: str | null
source_url: str | null
source_segment: str | null
source_window: str | null
licence_policy_identity: str | null
use_boundary: "OWNER_PRIVATE_PERSONAL_NONCOMMERCIAL_LOCAL_ONLY" | null
identity_bindings: array[NamedIdentityV1]
source_attribution_row_identity_sha256: Sha256
```

The row identity is `SHA(all row fields before that identity)`. Market data
retains only its opaque source-receipt identities; provider, authority, URL,
segment, window, licence, and use boundary remain null. Market Regime identifies
only deterministic derivation and its raw-report/screen/adjusted-handoff/report
bindings; source fields remain null. An observed Industry row copies the exact
public `NSE_INDICES`, URL, and artifact/snapshot/archive/receipt/report bindings
and applies Plan 24's fixed owner-private personal/noncommercial use boundary;
an observed event row copies exact public `NSE`, URL, `Equity`, `1D`,
`nse-manual-download-owner-private-v1`,
artifact/snapshot/archive/receipt/retained bindings, and applies the same
owner-private boundary.

A component failure with no admitted source-bearing public result uses
`UNAVAILABLE`, the component's fixed `source_kind`, null source/use fields, and
an empty identity tuple. No row infers missing provider/publisher facts or
claims origin, source completeness, official Sector taxonomy, commercial use,
publication, redistribution, or general news.

The observed AI projection has five non-null fields in this order:

1. `market_data`: one row per request member, sorted by ISIN, containing
   `isin`, `exchange`, `symbol`, `decision_session`, canonical completed
   `close: DecimalText`, `volume: UInt`, `data_cutoff`, `published_at`,
   `known_at`, and `source_receipt_sha256`;
2. `market_regime`: `report_identity_sha256`, `regime_label`,
   `advances: UInt`, `declines: UInt`, `unchanged: UInt`, and
   `comparison_session`;
3. `industry_participation`: `report_identity_sha256`,
   `classification_tier: "INDUSTRY"`, and rows sorted by Industry, each with
   `industry`, `member_count`, `advances`, `declines`, and `unchanged`;
4. `event_notices`: one row per request member sorted by ISIN, containing the
   full affected member object, exact outcome, and notices. Each notice contains
   `source_symbol`, `source_company_name`, `subject`, `details`, literal
   `broadcast_at`, `receipt_at`, `dissemination_at`, `difference`,
   `observation_identity_sha256`, and `deduplication_identity_sha256`; and
5. `ai_projection_identity_sha256: Sha256`.

The observed projection identity is `SHA(the first four fields)`. The
insufficient AI projection has those same first four keys in the same order,
each exactly null, followed by `ai_projection_identity_sha256 =
SHA(the four-null projection)`. It contains no partial member, aggregate, source
narrative, or notice. Source attributions and the component ledger remain
separate top-level packet evidence.

The AI projection excludes open, high, low, partial-session price/volume,
member-level Market Regime directions, Industry member classification, raw
artifacts/rows, unrelated full-market event rows, attachment URL or content,
archive paths, filesystem metadata, provider credentials, diagnostics,
exception text, prompts, model output, sentiment, materiality, rank, score,
signal, recommendation, position size, entry/exit, and order.

`NO_MATCHING_NOTICE_IN_SNAPSHOT` retains its Sprint-13 meaning only: no matching
row existed in the exact retained snapshot. It never means no real-world event,
no general news, no notice outside the retained window, or neutral evidence.

## Configuration, schema, and runtime identities

`configuration_identity_sha256` is `SHA` of one closed object containing the
contract revision, ordered component revisions, exact cohort projections and
joins, cutoff/session/comparison equalities, completed-close/volume exclusion,
the Market-Regime count/label formulas, Industry identity/count/session/equation/
sum/order/source/publisher-null rules, event date/member/source joins, reason
mapping/order, stage order/suppression/attribution, source order/use boundary,
bounds, and retain-before-return/exact-retry policy. Its ordered reconciliation
lists are normative executable preimages, not descriptive summaries.

`schema_identity_sha256` is `SHA` of one closed schema object with canonical
encoding aliases; declaration-ordered, typed, nullable, grammar- and bound-
specified request-member, Market-data row, Market-Regime, Industry aggregate/
row, event member/outcome/notice, observed-AI, insufficient-AI, packet,
component-ledger, source-attribution, archive-failure, retention-receipt,
retained-result, and completion-marker objects. Every listed identity formula is
the exact `SHA` preimage excluding only its named identity field. Field-name-only
lists and unspecified nested projections are not schema definitions.

`runtime_code_identity_sha256` follows the existing source-at-rest manifest
pattern. It binds the new packet module, its manifest, the shared runtime-source
verifier, `StorageRootLease`, and exact public component modules projected here.
Component-owned runtime identities remain separately in the ledger.
Source-at-rest identity is drift evidence, not evaluator-origin, executed-byte,
archive-authenticity, or external-attestation evidence.

## Structural bounds

Bounds are part of the configuration and schema identities:

```text
request canonical bytes                         1..4_194_304
cohort members                                  1..50
event notice rows across an observed packet     0..10_000
Industry aggregate rows when observed           1..cohort_size
event decoded text field                        1..32_768 Unicode code points
full packet object / packet-*.json               1..37_748_736 (36 MiB)
small retained receipt / retained-*.json         1..16_384
completion marker / completion-*.json            1..4_096
archive failure canonical bytes                  1..1_024
retained result canonical bytes                  1..37_769_216
JSON nesting                                     1..32
```

The 36 MiB archive read/write ceiling is a conservative structural limit, not a
domain outcome. Sprint 13 caps its complete canonical event snapshot at 32 MiB;
the remaining 4 MiB covers the bounded request-member identity projection,
completed close/volume rows, at most 50 Industry aggregates, Market Regime, and
the component/source ledgers. The packet does not copy the upstream event
snapshot, raw component artifacts, attachments, open/high/low, or private
handoffs, so this is deliberately conservative. Text is never truncated.

There is no `PACKET_BOUNDS_EXCEEDED` domain reason and no supposedly valid
36-MiB-plus-one packet. A candidate whose packet object cannot be serialized
within the structural ceiling, or any existing archived packet object larger
than the ceiling, produces the sanitized archive failure and no retained result.
Acceptance tests construct a representative maximum valid projection respecting
all upstream and packet bounds and separately place an oversized archived
object to prove structural archive failure.

## Immutable packet archive, exact objects, and retry

The testable effect boundary is:

```python
class CurrentResearchPacketArchivePortV1(Protocol):
    def archive_exact(
        self,
        request: CurrentSuppliedCohortResearchPacketRequestV1,
        packet: _CurrentSuppliedCohortResearchPacketCandidateV1,
        lease: StorageRootLease,
    ) -> (
        RetainedCurrentSuppliedCohortResearchPacketV1
        | CurrentResearchPacketArchiveFailureV1
    ): ...


class FileCurrentResearchPacketArchiveV1:
    def __init__(self, root: Path) -> None: ...

    def archive_exact(
        self,
        request: CurrentSuppliedCohortResearchPacketRequestV1,
        packet: _CurrentSuppliedCohortResearchPacketCandidateV1,
        lease: StorageRootLease,
    ) -> (
        RetainedCurrentSuppliedCohortResearchPacketV1
        | CurrentResearchPacketArchiveFailureV1
    ): ...
```

`CurrentResearchPacketArchiveFailureV1` is a closed, redacted immutable value
with exactly, in declaration order, `contract_version:
"current-research-packet-archive-failure@v1"`, `evidence_state:
"ARCHIVE_FAILED"`, `reason: "PACKET_ARCHIVE_FAILED"`, and
`archive_failure_identity_sha256: Sha256`.
`archive_failure_identity_sha256 = SHA(the first three fields)`. It carries no
request, packet, component, source, path, exception, or fact identity. Its
canonical bytes are bounded above. Wrong archive argument types raise sanitized
`TypeError`; invalid root/lease authority or packet runtime identity raises
sanitized `ValueError` before mutation. Expected archive
read/write/publication/verification failures return this value.

The production archive accepts only a real exact `StorageRootLease`; a fake,
duck-typed, closed, read-only, mismatched-root, or replaced-root lease is
rejected. All mutation occurs inside `lease.root_operation(root)` with
descriptor-relative no-follow operations and live-lease checks at publication
and final verification.

Archive directory and deterministic names are exactly:

```text
.current-research-packet-v1/
packet-<packet_identity_sha256>.json
retained-<packet_identity_sha256>.json
completion-<packet_identity_sha256>.json
```

`packet-*.json` is the full canonical packet object defined above.
`packet_object_sha256 = sha256(exact packet file bytes).hexdigest()`; it differs
from `packet_identity_sha256`, whose formula excludes its own field.

`archive_identity_sha256` is:

```text
SHA({
  "archive_protocol": "current-research-packet-archive@v1",
  "archive_directory": ".current-research-packet-v1",
  "packet_filename": exact packet filename,
  "packet_identity_sha256": packet identity,
  "packet_object_sha256": exact packet-file byte SHA
})
```

`retained-*.json` is a small receipt, never a second copy of packet facts. Its
fields, in declaration order, are:

```text
receipt_version: "retained-current-research-packet-receipt@v1"
packet_filename: exact basename str
packet_identity_sha256: Sha256
packet_object_sha256: Sha256
packet_size_bytes: PositiveInt <= 37_748_736
archive_identity_sha256: Sha256
packet_retained_at: UtcInstant
receipt_identity_sha256: Sha256
retained_result_identity_sha256: Sha256
```

Let `receipt_core` be the first seven fields.
`receipt_identity_sha256 = SHA(receipt_core)`.
`retained_result_identity_sha256 = SHA({"archive_identity_sha256": archive SHA,
"packet_identity_sha256": packet identity, "packet_object_sha256": packet-file
SHA, "packet_retained_at": retained instant,
"receipt_identity_sha256": receipt identity})`.

The in-memory `RetainedCurrentSuppliedCohortResearchPacketV1` is the only
fact-bearing public result. Its canonical representation has exactly two
non-null fields: `packet`, the fully revalidated decoded full packet object, and
`retention`, the fully revalidated decoded small receipt. Its immutable Python
attributes expose those exact packet and receipt fields; it has no archive path
or mutable handle. Its `retained_result_identity_sha256` must equal the receipt
formula above. Its canonical-byte ceiling is the packet ceiling plus the
receipt/marker allowance stated above.

`completion-*.json` has, in declaration order:

```text
marker_version: "retained-current-research-packet-complete@v1"
packet_filename: exact basename str
packet_identity_sha256: Sha256
packet_object_sha256: Sha256
receipt_filename: exact basename str
receipt_identity_sha256: Sha256
retained_result_identity_sha256: Sha256
archive_identity_sha256: Sha256
packet_retained_at: UtcInstant
completion_marker_identity_sha256: Sha256
```

`completion_marker_identity_sha256 = SHA(all preceding marker fields)`. The
marker is the sole completion assertion; a packet or receipt without the exact
verified marker is incomplete and never returned.

The archive:

1. revalidates the exact request, private candidate, packet bytes/identities,
   state/nullability, component/source ledgers, bounds, redaction, and runtime;
2. publishes the full packet object create-only and stably re-reads it;
3. samples one archive-owned `packet_retained_at` only after packet stability
   and requires `decision_cutoff <= packet_retained_at`;
4. constructs and publishes the small receipt, then the completion marker;
5. fsyncs new files and directories and revalidates root/directory/file
   identity, owner-private mode, regular single-link objects, sizes, names,
   exact bytes, every cross-object formula, and the live lease; and
6. reconstructs and returns the retained result only from those final verified
   archived bytes.

Publication is content-addressed, create-only, owner-private, no-follow, and
idempotent. There is no overwrite, deletion, directory scan, nearest packet,
mutable current pointer, caller-selected final name, alternate root, fallback,
or recovery by accepting different bytes. Separate files are not claimed
atomic: interruption may leave an orphan packet or receipt, but only the exact
marker completes the transaction.

An exact retry derives the same names from `packet_identity_sha256`, verifies all
three exact objects and bindings without sampling a replacement retention
timestamp, and returns byte-identical retained canonical bytes with the original
timestamp and identities. A changed cutoff, member projection, component
identity/reason, or packet fact creates a different packet identity and new
immutable names.

Both observed and admitted insufficiency packets must complete this archive
before return. Archive failure, runtime/structural failure, or incomplete
publication exposes no AI-consumable facts.

## Consumer and source-use boundary

The deterministic tool returns facts, provenance, closed reasons, and required
consumer disposition only. It does not write a narrative, suggestion, score,
signal, or trade action.

“External AI” means external to the deterministic research core but still
inside the same owner's private personal/noncommercial local workflow. It may
consume only a verified
`RetainedCurrentSuppliedCohortResearchPacketV1`:

- `OBSERVED` permits explainable contextual research over supplied fields only;
- `INSUFFICIENT_EVIDENCE` requires explicit insufficient information or
  `NO_TRADE`;
- component or packet reasons cannot be waived, reweighted, filled,
  neutralized, or overridden;
- it cannot read raw OHLC, infer omitted open/high/low/partial values,
  recalculate Market Regime or Industry aggregates, fetch attachments or
  general news, manufacture missing values, or use later knowledge; and
- `knowledge_cutoff` cannot be replaced by model training cutoff, invocation
  time, packet retention time, or a component timestamp.

NSE-derived source narrative, event-notice material, and Industry material must
not be sent to a hosted, third-party, public, shared, or multi-user model or
service without a separate owner authorization and source-use review. This
slice authorizes no such transfer. A private candidate, archive failure,
structural failure, raw component result, or unverified JSON is not an
AI-consumable packet.

## Historical `@v1` file set and exact successor reference

The following 11-file set records only the superseded Plan-26 `@v1` WIP
candidate:

```text
src/swing_trading_ai_assistant/research_packet/__init__.py (empty package marker)
src/swing_trading_ai_assistant/research_packet/current_supplied_cohort.py
src/swing_trading_ai_assistant/research_packet/current_supplied_cohort_runtime_identity_manifest.py
tests/research_packet/test_current_research_packet.py
README.md
docs/architecture-freeze-v1.md
docs/roadmap.md
docs/upcoming_sprints_overview.md
docs/sprints/README.md
docs/plans/26-current-supplied-cohort-research-packet-contract.md
docs/sprints/sprint-14.md
```

It is not current implementation authority. The sole exact successor file
authority is Plan 27's
[**Exact implementation file set**](27-current-same-pass-market-regime-contract.md#exact-implementation-file-set),
which expressly includes this historical plan, the delivered-boundary-only
correction to
`docs/plans/22-provider-neutral-adjusted-daily-close-contract.md`, and the empty
`research_packet/__init__.py` marker. The packet implementation and test paths
remain the same physical paths for clean replacement; their contract,
schemas, runtime identity, tests, and archive names become V2 only.

The package marker exports no symbol. There is no package-root export and no
change to `swing_trading_ai_assistant/__init__.py`. Plan-26 details below remain
historical evidence only and cannot expand, narrow, or contradict the exact
Plan-27 successor set.

## RED acceptance tests

Tests first fail because the packet module does not exist. They then defend:

1. exact request type, closed canonical projection, UTC/date/member admission,
   schema/config/request identities, bounds, and redacted representation;
2. exact `1..50` NSE `EQUITY` capability admission with no index-membership
   check;
3. the single public build-and-retain entry point and absence of a public
   projector, candidate constructor/serializer, or unretained fact result;
4. exact-type-only component inputs and rejection of mappings, subclasses,
   alternate revisions, forged digests, and malformed public structures;
5. revalidation of every publicly exposed constant, field, nullability,
   canonical digest, self-consistency rule, and cross-binding without claiming
   evaluator origin or private-handoff/archive authenticity; event
   `deduplication_identity_sha256`, cohort, snapshot, archive, receipt, and
   retained formulas bind exact public notice/member/source/date narrative,
   while ordinal-omitted `observation_identity_sha256` is opaque, exact-digest
   syntactically valid, globally unique, and never recovered or recomputed;
   a 10,000-notice deterministic call-count regression proves linear validation;
6. exact reconciliation of the full Sprint-13 member tuple to Sprint-10
   `(isin, symbol)` members while proving the two cohort hashes are not equated;
7. exhaustive Sprint 10–13 state/reason mapping, packet reason precedence, and
   frozen stage suppression exactly as specified above;
8. exact cutoff/session equality and no-future/freshness/source-date admission;
9. a valid Sprint-10 report with prior completed facts and a current partial
   retains whole-result `INSUFFICIENT_EVIDENCE` with the deterministic
   `DECISION_SESSION_MISMATCH`, four null AI facts, mandatory `NO_TRADE`, and
   no partial serialization; only malformed or forged partial-as-complete
   evidence maps to `PARTIAL_AS_COMPLETE`;
10. observed completed close/volume-only rows and aggregate-only Market Regime;
11. every Industry-to-Regime equality, row equation/order/uniqueness, literal
    `INDUSTRY`, exact source fields, and null publisher fields;
12. every request member has retained notices or
    `NO_MATCHING_NOTICE_IN_SNAPSHOT`, with no member dropping, unrelated row,
    attachment, or general-news claim;
13. exact observed/insufficient AI projection nullability and
    `required_consumer_outcome` null for observed versus mandatory
    `INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED` for insufficient;
14. exact component-ledger and source-attribution row field sets, order,
    failure-projection formulas, source/fact bindings, and row identities;
15. exact full-packet, small-receipt, retained-result, archive-failure, and
    completion-marker key sets, canonical bytes, filenames, bounds, and every
    identity formula;
16. a representative maximum valid upstream-and-packet projection remains
    within the 36 MiB packet-object ceiling; a pre-existing oversized archived
    packet object fails structurally with no domain packet reason;
17. retain-before-return for both observed and admitted-insufficiency packets
    through the public builder with a real `StorageRootLease`;
18. create-only immutable publication, stable verification, exact retry byte
    identity, original retention timestamp/identities, and distinct immutable
    output for any changed cutoff/component/reason/fact;
19. missing/corrupt/replaced/linked/unsafe/oversized/spliced packet, receipt,
    marker, directory, named binding, lease, or runtime evidence fails closed
    with no AI-consumable packet;
20. redaction excludes raw artifacts/rows, unrelated full-market notices,
    attachments, paths, descriptors, credentials, diagnostics, exception text,
    prompts, model output, and private handoffs; and
21. both required focused current/paper smokes below pass without a broker call,
    real money, recommendation, or effectiveness claim.

Tests assert observable contracts and exact bytes/identities, not private helper
structure. Frozen Sprint 10–13 tests remain unchanged unless a concrete current
acceptance blocker is recorded.

## Focused current/paper smokes

Completion requires two separately retained owner-private local packets:

1. **Positive current observation.** Use real-current exact component values for
   one same cohort after the market close, with one common IST decision session,
   one exact cutoff, and every observed admission satisfied. The returned packet
   must be `OBSERVED`. Archive the exact request again through the same real
   `StorageRootLease` and prove byte-identical returned canonical bytes plus the
   original retention timestamp and all identities.
2. **Mandatory negative disposition.** Use an admitted real component
   insufficiency, retain the resulting packet through a real lease, and prove
   all four AI fact fields are null and the consumer produces explicit
   insufficient information / `NO_TRADE` because
   `required_consumer_outcome` mandates it.

The positive smoke cannot pass with an insufficiency result, and the negative
smoke cannot substitute for the positive. If real-current same-cohort,
post-close, same-IST-session observed inputs are unavailable, Sprint 14
completion is blocked; the limitation must be recorded rather than relabelled
as success.

Both smokes record exact cohort size, cutoff/session, packet/component
identities, state, byte count, and retry equality without exposing NSE-derived
private narrative, Industry material, paths, or raw artifacts outside the
owner-private local evidence record.

These are freshness, cross-component binding, retention, reproducibility, and
consumer-boundary evidence only. They are not source-completeness, general-news,
strategy-quality, recommendation, live-trade, historical, or effectiveness
claims and perform no broker or real-money action.

## Verification, review, and delivery

Before completion, the exact candidate requires:

```text
focused current research-packet tests
ruff format --check .
ruff check .
pyright
vulture src --min-confidence 80
full pytest with repository coverage threshold
uv build
required positive observed archive/retry and separate retained insufficiency smokes
independent functional/domain review
independent security/privacy/provenance review
exact-SHA commit and fresh review
PR hosted Quality/build
GitGuardian
merge and lifecycle closeout against the exact reviewed revision
```

Functional review must challenge component state/binding, cohort projection,
cutoff/session, no-future, partial exclusion, aggregate reconciliation,
consumer disposition, retry identity, and the no-general-news/non-advice claims.
Security review must challenge `StorageRootLease` authority, descriptor-relative
publication, immutable object and marker binding, source-at-rest runtime identity,
private narrative/redaction, forged/spliced/replaced objects, and sanitized
failures. Any candidate change after review invalidates that review.

## Changed and nonchanged boundaries

The superseded Plan-26 `@v1` WIP candidate was limited to the historical exact
11-file set stated above. That statement is not current Plan-27 authority.

It did not change dependencies, lockfiles, workflows, provider/source
decisions, frozen Sprint 10–13 component files, architecture policy, roadmap
scope, upcoming-sprint or sprint-index historical records, commits, branches,
pull requests, hosted checks, or tracker state.

Current successor lifecycle state: Sprint 14 / Issue #119 is **IN PROGRESS —
TWO PR #140 P2 BLOCKERS FIXED; ALL REQUIRED CURRENT SMOKES AND ALL
EXACT-CURRENT LOCAL GATES PASSED (852 FOCUSED; 3,400 FULL AT 89.53%
COVERAGE; RUFF FORMAT/CHECK 275, PYRIGHT 0/0, VULTURE 80, DIFF, BUILD, WHEEL,
CLEAN INSTALLED-WHEEL IMPORTS/RUNTIME); CANDIDATE COMMIT CREATED; EXACT-CURRENT REVIEWS,
PUSH/HOSTED/MERGE/CLOSEOUT PENDING; NO COMPLETION/DELIVERY** under Plan 27.

Official acquisition automation retained and validated the current exact
schedule, mapping, Industry, event, raw, and Plan-21 evidence. Fresh post-close
evidence passed with schedule SHA-256
`f50e7853ce91e3868678b40b5ece79beea0aa469317d348129e96b1c3b71b0a0`,
Industry SHA-256
`1a40e33a0febf458986a178bc76f7b0051f163718f2a8bc11a726ba70a39c0a9`,
and Event SHA-256
`fe77c222ccf73c9a90b7c94641f6e39055c5a4956467729fabda4c8a9ea4b297`.
The final 14-file focused portfolio passed **852 tests** with `--no-cov`; the
strict one-lease post-close `RELIANCE` positive passed with 21 raw bars; Market
Regime, Industry, and Packet `OBSERVED`; partial `NOT_APPLICABLE`; Plan 21
`SCREENED`; Plan 22 `SUCCESS`; and guarded retries preserving exact bytes,
identities, and original times.

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

PR #140's two P2 blockers are fixed on the exact current source candidate 66-path
set. Active-session partial acquisition now requires canonical identity and an
effective provider mapping valid on the active date before any partial query;
expired canonical or mapping validity performs zero partial queries. Industry V2
preserves the schema-specific legacy/current source URL and Packet attribution.

The mandatory Aug-27 market-hours `RELIANCE` positive rerun **PASSED** on exact
current source candidate 66-path fingerprint
`3940ffe433887360c2744507c4075ac2404ffcd1482b2799380d26776623229e` at cutoff
`2026-08-27T08:18:59Z`. Raw, Market Regime, Industry, and Packet were
`OBSERVED`; Plan 21 was `SCREENED`; Plan 22 was `SUCCESS`. Active-date canonical
and mapping validity passed before the partial path returned `UNAVAILABLE` /
`PARTIAL_MEMBER_MISSING` with zero rows. Industry and Packet retained the current
`nsearchives.nseindia.com` URL attribution. Exact retries preserved bytes,
identities, and original times and caused zero provider effects. The prior
post-close positive, earlier Aug-27 market-hours positive, genuine IRCTC
negative, and exact 66-path set remain preserved.

The exact-current full suite passed **3,400 tests at 89.53% total coverage**
against the **87%** threshold, and the 14-file focused portfolio passed 852 tests.
All exact-current local gates pass: Ruff format/check over 275 files, Pyright 0/0,
Vulture at 80%, `git diff --check`, `uv build` producing sdist and wheel, and clean
installed-wheel imports/runtime checks. Installed runtime identities are raw
`8d99ebe8781d48d6a45a331878ff3a730bd23237c152e5837797c003c71d047b`,
Industry V2 `e8e4c5408afe49e4f99484c0ab8a23cc897dfb3a34b84d00f7230405e7d93f29`,
Market Regime V3 `74928b2b190e0e676ebb88fd4df5ae3d3856edaf8a08694da325393543a3542a`,
and Packet V2 `a36e3f42a773f0d533dcfbc3726b83c800028bdf9f11bcae299e176eb020a4ea`.
A candidate commit has been created. Exact-current reviews, push, hosted checks,
merge, and closeout remain pending. No acceptance, completion, or delivery is claimed.

Ten review blockers are fixed locally without a new subsystem: the two PR #140
P2 fixes for active-date partial canonical/mapping validity and schema-specific
Industry/Packet URL attribution; late
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
other. The two PR #140 P2 blockers are fixed. All exact-current local gates pass. A candidate commit has been created; exact-current reviews, push, hosted checks, merge, and closeout remain pending. This Plan-26 `@v1` candidate remains
superseded before delivery; its 101 focused tests remain historical superseded
WIP evidence only. It will not ship, and no alias is authorized. No Plan-27
acceptance, completion, delivery, or closeout is claimed here until the
lifecycle is complete.
