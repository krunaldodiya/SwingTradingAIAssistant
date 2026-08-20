# Upstox current corporate-action screen contract

Status: **CAPABILITY SPECIFICATION ONLY — no implementation, test, review,
release, source acquisition, or retained-evidence availability is claimed**
Contract revision: `current-supplied-cohort-upstox-action-screen@v1`
Schema revision: `current-supplied-cohort-upstox-action-screen-schema@v1`
Risk: **R3 / High** — financial-research integrity, immutable private evidence,
and a reusable public comparability-screen contract
Outcome owner, acceptance authority, and residual-risk owner: **repository owner
through GitHub Issue #125**
Depends on: [Plan 19](19-current-supplied-cohort-market-data-contract.md),
retained Upstox snapshots under [Plan 09](09-corporate-action-provenance-contract.md),
and retained official schedule evidence.
Preserves: frozen [Plan 12](12-market-regime-contract.md), Plan 09 raw-candle
immutability, and deferred Plans 18/Sprints 15–16.

## Outcome, authority, and lifecycle

Issue #125 authorizes one reusable, provider-limited **screen**, not a Market
Regime contract. For an exact owner-supplied Plan-19 cohort and inclusive
`S[0]..S[20]`, it derives the completed-session relation and official `S[20]`
close from a supplied retained schedule binding, then reads existing retained
Upstox corporate-action snapshots by exact ISIN and cutoff. A pass emits only:

```text
UPSTOX_SCREENED_NO_SUPPORTED_ACTION_OBSERVED
UPSTOX_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE
```

It never emits `NSE_CM`, `NO_BREAK_PROVEN`, or `RAW_CLOSE_NO_BREAK_PROVEN`.
An empty Upstox result is not authoritative negative/no-break proof.

This is R3 because a false screen pass can later distort financial-research
facts, private retained evidence is consumed, and later correction cannot repair
a former report. Owner authority is
[Issue #125 comment 5354886149](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/125#issuecomment-5354886149).
It authorizes neither provider/NSE calls, acquisition, credentials, adjusted
prices, a second parser/store/attempt representation, PR #124 merge, Issue #116
closure, or Sprint 12.

| Lifecycle area | Impact | Disposition |
| --- | --- | --- |
| Upstream requirements | Affected | Exact Plan-19 manifest, existing Plan-09 store, and owner-bound retained schedule evidence are the only inputs. No unmerged Market Regime type is inherited. |
| Consumers and compatibility | Affected | This standalone capability merges first. PR #124 later rebases and consumes it atomically in a separate current-regime v2 cutover. |
| Evidence/provenance | Affected | Source, Plan-09 snapshot schema, schedule, screen schema/policy, input/request/code/selected-set/report identities bind replay. |
| Privacy/security | Affected | ISINs, events, bytes/digests, store/schedule outcomes, paths, and diagnostics stay private. Public reports are aggregate/opaque. |
| Operations/recovery | Affected | Bounded read-only/no-network resolution fails closed. Later retained data creates new identity and never rewrites prior evidence. |
| Historical availability | Future only | Sprints 15/16 govern historical point-in-time availability. Plan 21 creates no historical evaluator, backfill, acceptance test, or runtime output. |
| Third-party authority | Not affected by runtime | Existing Plan-09 retention only; no new retention/use authority or NSE automation. |

## Source qualification history and exact evaluation

Plan 09 selected immutable Upstox Fundamentals ISIN-keyed observations for
Dividend, Bonus, Split, and Rights. Plan 11 records that this source does not
prove exhaustive empty-result meaning, finality/correction lineage, same-issue
continuity, historical revision identity, historical symbol change, or
adjusted-price semantics. The earlier #125 NSE qualification remains source
history; this smaller provider screen does not rewrite it.

The five-line evaluation is exact:

1. **Expected value:** identify common price-breaking Dividend/Bonus/Split/Rights events for exact ISINs across the 20-session comparison window.
2. **Scope fit:** fits current/live supplied-cohort screening and reuses the already-authorized retained Upstox boundary.
3. **Material risk:** no documented exhaustive empty-result meaning, finality/correction lineage, same-issue continuity, or coverage of every restructuring class.
4. **Smallest alternative:** use direct completed closes, fail on any returned/unknown event or unavailable snapshot, and expose the limited provider-screened state.
5. **Decision:** **accepted for provider-screened current research only; rejected as authoritative no-break proof**.

NSE public UI/announcement material is optional manual positive corroboration. It
is never automated, never required to pass this screen, and an empty NSE result
never proves no action.

## Standalone scope and later integration

The screen itself computes no close, direction, threshold, breadth, trend,
higher-high/lower-low structure, range, market label, Market Structure, or price
adjustment. The retained schedule resolver must prove that supplied `S[0]` and
`S[20]` are exactly 20 completed official NSE Capital Market positions apart and
derive the exact official `S[20]` close instant. The screen accepts no owner-
supplied close timestamp.

Sprint 11 remains the later direct raw `S[0]`/`S[20]` close cohort-breadth
comparison. After this screen independently merges, rebased PR #124 may add a
separate Market Regime v2 that consumes only a successful screen report; its
unscreened v1 must never merge, select, or fall back. When the screen passes, raw
OHLC remains normal input for that consumer only. It is not adjusted, total-
return, economic-return, or no-break proof. Future Market Structure may reuse
the screen and define its own approved event-window skip/reset policy; Plan 21
neither starts nor specifies Market Structure.

## Canonical profile and frozen identities

All external objects are immutable closed JSON: UTF-8, no BOM, lexicographic
keys, compact separators, `allow_nan=false`, no duplicate keys, and one trailing
LF. Arrays retain declared order. `UtcInstant` is six-fraction UTC, `LocalDate`
is a real date, `Sha256` is 64 lowercase hex, `Sha256Prefixed` is
`sha256:<64 lowercase hex>`, and ISIN uses existing uppercase Luhn validation.
Unknown/missing keys, wrong types/nullability, malformed/noncanonical bytes,
excess depth, or bound failure reject before a report. Every identity hashes
canonical bytes excluding only that object's self-identity field.

The fixed source identity is
`3853a15b853b73a945065486ca96b48d4ee3625e4ed7c6e4927579e2b0b372a2`:

```json
{"adapter_release":"corporate-actions-v1","corporate_action_source":"upstox-fundamentals-v2","endpoint_template":"https://api.upstox.com/v2/fundamentals/{isin}/corporate-actions","plan09_contract":"corporate-action-provenance@v1"}
```

The exact reused Plan-09 snapshot/event contract identity is
`de03833b00d0d286fc3d0116f7ce81b8694547d43b13250f7415d6c95fdbbf8a`:

```json
{"canonical_json":{"allow_nan":false,"encoding":"UTF-8","object_keys":"LEXICOGRAPHIC","separators":[",",":"],"trailing_lf":false},"event":{"fields":[["event_digest_sha256","Sha256",false],["kind","Literal[DIVIDEND,BONUS,SPLIT,RIGHTS]",false],["announced_at","UtcInstant",false],["effective_date","LocalDate",false],["record_date","LocalDate",true],["cash_amount_inr","CanonicalPositiveDecimal",true],["ratio_numerator","Integer[1..999999]",true],["ratio_denominator","Integer[1..999999]",true]],"invariants":["sorted_unique_event_digest","announced_at_ist_date<=effective_date","record_date==null_or_record_date>=effective_date","DIVIDEND=>cash_amount_inr!=null_and_ratios==null","BONUS|SPLIT|RIGHTS=>cash_amount_inr==null_and_ratios!=null","event_digest_recomputed"]},"snapshot":{"fields":[["events","tuple[CorporateActionEventV1,0..1000]",false],["isin","UppercaseLuhnIsin",false],["retrieved_at","UtcInstant",false],["schema_version","Literal[1]",false],["source","Literal[upstox-fundamentals-v2]",false],["source_release","Literal[corporate-actions-v1]",false]],"invariants":["events_sorted_unique_by_event_digest","announced_at<=retrieved_at","canonical_bytes<=1048576","json_depth<=64"]},"type":"CorporateActionSnapshotV1"}
```

The complete v1 schema-bundle identity is
`a789cbdd1c554ddd0e5029d02e263491af73c1b23754366cd78e2b2f3d75dbde`:

```json
{"canonical_json":{"allow_nan":false,"encoding":"UTF-8","object_keys":"LEXICOGRAPHIC","separators":[",",":"],"trailing_lf":true},"contract_version":"current-supplied-cohort-upstox-action-screen@v1","input":{"fields":[["contract_version","Literal[current-supplied-cohort-upstox-action-screen@v1]",false],["cohort_manifest","CurrentSuppliedCohortManifestV1",false],["comparison_session","LocalDate",false],["decision_session","LocalDate",false],["decision_cutoff","UtcInstant",false],["schedule_evidence_sha256","Sha256",false],["schedule_source","Literal[nse-authoritative-calendar]",false],["schedule_source_release","Sha256Prefixed",false],["corporate_action_source","Literal[upstox-fundamentals-v2]",false],["corporate_action_source_identity_sha256","Sha256",false],["snapshot_schema_identity_sha256","Sha256",false],["screen_schema_identity_sha256","Sha256",false],["screen_policy_identity_sha256","Sha256",false],["input_identity_sha256","Sha256",false]],"max_bytes":16384,"self_identity":"input_identity_sha256"},"private_result":{"fields":[["cohort_identity_sha256","Sha256",false],["comparison_session","LocalDate",false],["decision_session","LocalDate",false],["decision_session_close_at","UtcInstant",true],["decision_cutoff","UtcInstant",false],["schedule_evidence_sha256","Sha256",false],["schedule_source","Literal[nse-authoritative-calendar]",false],["schedule_source_release","Sha256Prefixed",false],["source_identity_sha256","Sha256",false],["snapshot_schema_identity_sha256","Sha256",false],["outcome","Enum[SCREENED_NO_SUPPORTED_ACTION_OBSERVED,MISSING,STALE,AMBIGUOUS,CORRUPT,ACTION_OBSERVED,SCHEDULE_MISSING,SCHEDULE_AMBIGUOUS,SCHEDULE_LATE,SCHEDULE_CONTINUITY_UNPROVEN]",false],["selected_snapshot_set_identity_sha256","Sha256",true]],"invariants":["ready=>outcome=SCREENED_NO_SUPPORTED_ACTION_OBSERVED_and_selected_snapshot_set_identity_sha256!=null","nonready=>selected_snapshot_set_identity_sha256=null","schedule_failure=>decision_session_close_at=null","nonschedule_failure=>decision_session_close_at!=null"],"type":"PrivateUpstoxActionScreenResultV1"},"report":{"fields":[["contract_version","Literal[current-supplied-cohort-upstox-action-screen@v1]",false],["input_identity_sha256","Sha256",false],["request_identity_sha256","Sha256",false],["cohort_identity_sha256","Sha256",false],["comparison_session","LocalDate",false],["decision_session","LocalDate",false],["decision_session_close_at","UtcInstant",true],["decision_cutoff","UtcInstant",false],["schedule_evidence_sha256","Sha256",false],["schedule_source","Literal[nse-authoritative-calendar]",false],["schedule_source_release","Sha256Prefixed",false],["corporate_action_source","Literal[upstox-fundamentals-v2]",false],["corporate_action_source_identity_sha256","Sha256",false],["snapshot_schema_identity_sha256","Sha256",false],["screen_schema_identity_sha256","Sha256",false],["screen_policy_identity_sha256","Sha256",false],["code_identity_sha256","Sha256",false],["evidence_state","Enum[SCREENED,INSUFFICIENT_EVIDENCE]",false],["screen_state","Literal[UPSTOX_SCREENED_NO_SUPPORTED_ACTION_OBSERVED]",true],["coverage_limitation","Literal[UPSTOX_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE]",false],["selected_snapshot_set_identity_sha256","Sha256",true],["reason","Literal[CORPORATE_ACTION_SCREEN_INSUFFICIENT]",true],["report_identity_sha256","Sha256",false]],"invariants":["SCREENED=>decision_session_close_at!=null_and_screen_state!=null_and_selected_snapshot_set_identity_sha256!=null_and_reason=null","INSUFFICIENT_EVIDENCE=>decision_session_close_at=null_and_screen_state=null_and_selected_snapshot_set_identity_sha256=null_and_reason=CORPORATE_ACTION_SCREEN_INSUFFICIENT","coverage_limitation_nonnull"],"type":"CurrentSuppliedCohortUpstoxActionScreenReportV1"},"request":{"fields":[["contract_version","Literal[current-supplied-cohort-upstox-action-screen@v1]",false],["input_identity_sha256","Sha256",false],["cohort_manifest","CurrentSuppliedCohortManifestV1",false],["comparison_session","LocalDate",false],["decision_session","LocalDate",false],["decision_cutoff","UtcInstant",false],["schedule_evidence_sha256","Sha256",false],["schedule_source","Literal[nse-authoritative-calendar]",false],["schedule_source_release","Sha256Prefixed",false],["corporate_action_source","Literal[upstox-fundamentals-v2]",false],["corporate_action_source_identity_sha256","Sha256",false],["snapshot_schema_identity_sha256","Sha256",false],["screen_schema_identity_sha256","Sha256",false],["screen_policy_identity_sha256","Sha256",false],["request_identity_sha256","Sha256",false]],"self_identity":"request_identity_sha256","type":"CurrentSuppliedCohortUpstoxActionScreenRequestV1"},"reused_plan09_snapshot_contract":{"canonical_json":{"allow_nan":false,"encoding":"UTF-8","object_keys":"LEXICOGRAPHIC","separators":[",",":"],"trailing_lf":false},"event":{"fields":[["event_digest_sha256","Sha256",false],["kind","Literal[DIVIDEND,BONUS,SPLIT,RIGHTS]",false],["announced_at","UtcInstant",false],["effective_date","LocalDate",false],["record_date","LocalDate",true],["cash_amount_inr","CanonicalPositiveDecimal",true],["ratio_numerator","Integer[1..999999]",true],["ratio_denominator","Integer[1..999999]",true]],"invariants":["sorted_unique_event_digest","announced_at_ist_date<=effective_date","record_date==null_or_record_date>=effective_date","DIVIDEND=>cash_amount_inr!=null_and_ratios==null","BONUS|SPLIT|RIGHTS=>cash_amount_inr==null_and_ratios!=null","event_digest_recomputed"]},"snapshot":{"fields":[["events","tuple[CorporateActionEventV1,0..1000]",false],["isin","UppercaseLuhnIsin",false],["retrieved_at","UtcInstant",false],["schema_version","Literal[1]",false],["source","Literal[upstox-fundamentals-v2]",false],["source_release","Literal[corporate-actions-v1]",false]],"invariants":["events_sorted_unique_by_event_digest","announced_at<=retrieved_at","canonical_bytes<=1048576","json_depth<=64"]},"type":"CorporateActionSnapshotV1"},"schema_revision":"current-supplied-cohort-upstox-action-screen-schema@v1"}
```

The complete screen-policy identity is
`36d3c8ed4ce51acf4c9373bcc39d8e45b72621ea222abafa6468df9e31b20020`:

```json
{"contract_version":"current-supplied-cohort-upstox-action-screen@v1","invariants":{"adjustment_attempts":0,"directory_scan_attempts":0,"network_attempts":0,"public_member_event_path_details":false,"storage_write_attempts":0},"schedule":{"derived_close":"ScheduleEvidenceStore.resolve(schedule_evidence_sha256)_under_admitted_root_lease_then_exact_source_and_source_release_equality","outcomes":["SCHEDULE_MISSING","SCHEDULE_AMBIGUOUS","SCHEDULE_LATE","SCHEDULE_CONTINUITY_UNPROVEN"],"rule":"S0_and_S20_are_exactly_20_completed_positions_apart"},"selected_snapshot_set_projection":{"cohort_identity_sha256":"Sha256","comparison_session":"LocalDate","decision_cutoff":"UtcInstant","decision_session":"LocalDate","schedule_evidence_sha256":"Sha256","schedule_source":"nse-authoritative-calendar","schedule_source_release":"sha256:<64-lowercase-hex>","snapshot_fields":["isin","snapshot_digest_sha256","source","source_release","snapshot_schema_identity_sha256","retrieved_at"],"snapshots_sorted_by":"isin"},"selection":{"exact_isin":true,"latest_before_or_at":"decision_cutoff","minimum_retrieved_at":"derived_decision_session_close_at","store_outcomes":["MISSING","STALE","AMBIGUOUS","CORRUPT"],"window":"comparison_session<=effective_date<=decision_session"},"source":{"identity":"upstox-fundamentals-v2","supported_actions":["DIVIDEND","BONUS","SPLIT","RIGHTS"]},"states":{"evidence":["SCREENED","INSUFFICIENT_EVIDENCE"],"limitation":"UPSTOX_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE","private_action_outcome":"ACTION_OBSERVED","public_insufficient_reason":"CORPORATE_ACTION_SCREEN_INSUFFICIENT","screen":["UPSTOX_SCREENED_NO_SUPPORTED_ACTION_OBSERVED"]}}
```

The selected-snapshot-set projection format is frozen under identity
`a655abdd1ee44337ad28d9b6f9d148927d831d9eeb7cdeccdde68f90945d0775`:

```json
{"cohort_identity_sha256":"Sha256","comparison_session":"LocalDate","decision_cutoff":"UtcInstant","decision_session":"LocalDate","schedule_evidence_sha256":"Sha256","schedule_source":"nse-authoritative-calendar","schedule_source_release":"sha256:<64-lowercase-hex>","snapshot_fields":["isin","snapshot_digest_sha256","source","source_release","snapshot_schema_identity_sha256","retrieved_at"],"snapshots_sorted_by":"isin"}
```

For each successful result, `selected_snapshot_set_identity_sha256` is SHA-256
of one canonical value with those named header fields and one `snapshots` array,
strictly sorted by ISIN. Each row contains exactly the six declared snapshot
fields. The public report exposes only that computed hash, never the projection
or its rows.

## Ordered V1 types and nullability

The schema projection above is authoritative. The following tables aid review;
they do not alter its order/type/nullability constraints.

### Owner-private input — `CurrentSuppliedCohortUpstoxActionScreenInputV1`

| Field | Rule |
| --- | --- |
| `contract_version`, `cohort_manifest`, `comparison_session`, `decision_session`, `decision_cutoff` | Non-null exact standalone contract, Plan-19 manifest, S0/S20 dates, and UTC knowledge cutoff. |
| `schedule_evidence_sha256`, `schedule_source`, `schedule_source_release` | Non-null exact retained schedule digest, literal `nse-authoritative-calendar`, and source-release identity. |
| `corporate_action_source`, `corporate_action_source_identity_sha256`, `snapshot_schema_identity_sha256` | Non-null fixed Upstox literal/source hash/reused Plan-09 contract hash. |
| `screen_schema_identity_sha256`, `screen_policy_identity_sha256`, `input_identity_sha256` | Non-null runtime-constant identities; final field hashes all prior input fields. |

The 16 KiB input contains no close time, storage path, URL, credential, event,
snapshot digest, raw payload/OHLC, or claim that an action is absent.

### Immutable request — `CurrentSuppliedCohortUpstoxActionScreenRequestV1`

It deep-copies the admitted input fields in the schema order after
`input_identity_sha256`, adds only `request_identity_sha256`, and has no
caller-provided schedule close. The schedule resolver derives the close under
the private lease.

### Private result — `PrivateUpstoxActionScreenResultV1`

It has the schema-ordered non-null cohort/date/cutoff/schedule/source/snapshot
bindings, nullable derived `decision_session_close_at`, a non-null private
outcome, and nullable selected-set hash. Outcomes are exactly:

```text
SCREENED_NO_SUPPORTED_ACTION_OBSERVED
MISSING | STALE | AMBIGUOUS | CORRUPT | ACTION_OBSERVED
SCHEDULE_MISSING | SCHEDULE_AMBIGUOUS | SCHEDULE_LATE |
SCHEDULE_CONTINUITY_UNPROVEN
```

Only the ready outcome has a selected-set hash; every nonready outcome has null
set hash. Every non-schedule-failure outcome—including ready and every store or
action outcome after schedule success—has a non-null exact derived close. Only
the four schedule-failure outcomes have null derived close. These private
outcomes never serialize to the public report.

### Public report — `CurrentSuppliedCohortUpstoxActionScreenReportV1`

All schema-ordered identity/source/schedule fields are non-null on both outcomes.
`decision_session_close_at`, `screen_state`, selected-set hash, and `reason` have
the conditional nullability stated in the frozen schema: `SCREENED` has derived
close, exact passing state and selected-set hash, and null reason;
`INSUFFICIENT_EVIDENCE` has null close/state/set hash and only
`CORPORATE_ACTION_SCREEN_INSUFFICIENT`. `coverage_limitation` is always non-null
and exactly `UPSTOX_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE`. No public output
contains a member, ISIN, event, store/schedule outcome, close, byte, payload,
path, catalog row, or free-form diagnostic.

## Read-only resolver port and exact admission

```text
PrivateUpstoxActionScreenResolverPortV1.resolve_exact(
  request: CurrentSuppliedCohortUpstoxActionScreenRequestV1,
  lease: StorageRootLease
) -> PrivateUpstoxActionScreenResultV1
```

The port receives only frozen request and admitted private-root lease. It calls
existing `ScheduleEvidenceStore.resolve(schedule_evidence_sha256)` under that
root/lease; it does not call an invented parameterized resolver. The resolved
schedule's `source` and `source_release` must then exactly equal the request's
fixed `schedule_source` and `schedule_source_release`. Only that admitted
schedule derives `decision_session_close_at`, proves `S[0]` and `S[20]` are
exactly 20 completed positions apart, and requires the derived close no later
than `decision_cutoff`. Missing schedule is `SCHEDULE_MISSING`; binding/shape
ambiguity is `SCHEDULE_AMBIGUOUS`; cutoff-late schedule is `SCHEDULE_LATE`; an
unproved session relation/close is `SCHEDULE_CONTINUITY_UNPROVEN`. All map to
the single generic public insufficiency.

Only after schedule success, for each and only each manifest ISIN, it calls the
existing Plan-09 store resolution at `decision_cutoff`. A selected snapshot must
satisfy the exact derived interval:

```text
derived_decision_session_close_at <= snapshot.retrieved_at <= decision_cutoff
```

A selected earlier snapshot is existing private `STALE`; a later snapshot cannot
be selected. Existing store outcomes remain exactly `MISSING`, `STALE`,
`AMBIGUOUS`, and `CORRUPT`. The adapter adds only private `ACTION_OBSERVED` for
a validated retained `DIVIDEND`, `BONUS`, `SPLIT`, or `RIGHTS` whose effective
date is inclusively within `S[0]..S[20]`. An action outside that interval does
not block this screen but proves no broader continuity.

The screen reads only selected successful retained snapshots. Failed, rejected,
or malformed pre-retention acquisition attempts are outside this read-only
capability; they do not invalidate an already-admissible successful post-close
snapshot and create no hidden latest-attempt claim. If no successful post-close
snapshot is available, the existing `MISSING` or `STALE` result applies. This is
a provider-limited residual, never an inferred completeness guarantee.

Every selected object is reread through existing descriptor-relative private-root
controls: no-follow components; root/directory attachment revalidation before,
during, and after reads; owner-private mode; regular file; single link; stable
metadata; canonical bytes; and digest. Attachment loss discards private
projections. The port permits 1–50 exact ISIN resolutions and Plan-09 bounds
(1 MiB, 1,000 events, depth 64), and performs zero network/provider calls,
writes, refreshes, retries, background work, scans/listing/globs, latest-now
selection, adjustments, gap inference, NSE access, or public details.

## Compatibility, release sequence, and future checks

Plan 21 merges as the standalone screen before PR #124. It accepts/inherits no
`CurrentSuppliedCohortMarketRegime` input/request/report, archive, breadth, or
market label, and changes none of Plans 09, 11, 12, or 19. Then PR #124 rebases
and adds the separate Market Regime v2 cutover that accepts only a successful
screen report. Unscreened v1 cannot merge, select, or fall back. V2 preserves
Plan 20/v1 replay history without claiming historical v1 reports were screened.

Sprints 15/16, not Plan 21, later govern historical no-backfill availability.
This plan has no historical output/test/gate.

No test, formatter, linter, build, provider call, network call, or commit is run
by this specification change. A future candidate must verify N=1/5/50; exact
schedule 20-position and close/cutoff boundaries; all four schedule outcomes;
existing store outcomes; private action observation; exact selected-set schema
and per-result hash; canonical input/request/report round trips; every frozen
identity; attachment/binding failures; zero effects/public leakage; standalone
absence of Market Regime imports; and later separate v2 integration with no v1
fallback. Owner acceptance also requires exact-candidate focused/full/release
gates, installed-wheel/CLI smoke, hosted CI/security, and independent exact-
revision R3 functional, security/provenance, and temporal review.

## Non-goals

Plan 21 does not implement source/tests; alter PR #124; create Market Regime v2;
compute trend/Market Structure; call Upstox/NSE/SEBI; use credentials;
acquire/retain evidence; add dependencies; automate NSE UI; adjust/reconstruct
prices; infer events from gaps; prove no action; create historical evaluator;
start Sprint 12; recommend; or trade. Issue #116 and PR #124 remain blocked
until this standalone capability merges and later v2 integration passes its own
gates.
