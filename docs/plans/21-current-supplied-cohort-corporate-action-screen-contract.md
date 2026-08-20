# Current supplied-cohort corporate-action screen contract

Status: **IMPLEMENTATION CANDIDATE — provider-neutral Plan-21 source and focused
tests are in the working tree. Current focused verification is 192 passed
(77 screen, corporate-actions, schedule-evidence, and current-cohort/runtime
identity); no commit, review, full suite/build, CI, release, or merge is claimed.**

Contract revision: `current-supplied-cohort-corporate-action-screen@v1`

Schema revision: `current-supplied-cohort-corporate-action-screen-schema@v1`

Risk: **R3 / High** — financial-research integrity, immutable private evidence,
and a reusable public comparability-screen contract.

Outcome owner, acceptance authority, and residual-risk owner: **repository owner
through GitHub Issue #125**.

Depends on: [Plan 19](19-current-supplied-cohort-market-data-contract.md),
retained provider snapshots under [Plan 09](09-corporate-action-provenance-contract.md),
and retained official schedule evidence. Preserves: frozen
[Plan 12](12-market-regime-contract.md), Plan 09 raw-candle immutability, and
deferred Plans 18/Sprints 15–16.

## Outcome, authority, and lifecycle

Issue #125 authorizes one reusable, provider-neutral **screen**, not a Market
Regime contract or provider platform. For an exact owner-supplied Plan-19 cohort
and inclusive `S[0]..S[20]`, it derives the completed-session relation and
official `S[20]` close from a supplied retained schedule binding. It then uses
one explicitly injected provider adapter, whose `provider_id` exactly matches
the request, to screen existing retained snapshots by exact ISIN and cutoff.

A successful public report emits only generic states:

```text
screen_state = SCREENED
coverage_limitation = PROVIDER_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE
```

An unsuccessful report emits only:

```text
screen_state = null
reason = CORPORATE_ACTION_SCREEN_INSUFFICIENT
coverage_limitation = PROVIDER_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE
```

Neither result emits `NSE_CM`, `NO_BREAK_PROVEN`,
`RAW_CLOSE_NO_BREAK_PROVEN`, a provider outcome, an event, or an ISIN. An empty
provider response is nonexhaustive provider-screened evidence, never an
authoritative negative or no-break proof.

This remains R3 because a false screen pass can later distort financial-research
facts, private retained evidence is consumed, and later correction cannot repair
a former report. Owner authority is
[Issue #125 comment 5354886149](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/125#issuecomment-5354886149).
It authorizes neither provider/NSE calls, acquisition, credentials, adjusted
prices, a second parser/store/attempt representation, PR #124 merge, Issue #116
closure, nor Sprint 12.

| Lifecycle area | Impact | Disposition |
| --- | --- | --- |
| Upstream requirements | Affected | Exact Plan-19 manifest, retained schedule evidence, and the selected adapter's already-authorized retained source are the only inputs. No unmerged Market Regime type is inherited. |
| Consumers and compatibility | Affected | This standalone capability merges first. PR #124 later rebases and consumes it atomically in a separate current-regime v2 cutover. |
| Evidence/provenance | Affected | Provider descriptor, source/snapshot-schema/policy identities, schedule, screen schema/policy, input/request/code/selected-set/report identities bind replay. |
| Privacy/security | Affected | ISINs, events, snapshot identities, retrieval times, bytes/digests, store/schedule outcomes, paths, and diagnostics stay private. Public reports expose only `provider_id` and opaque provenance identities. |
| Operations/recovery | Affected | Bounded read-only/no-network resolution fails closed. Later retained data creates a new identity and never rewrites prior evidence. |
| Historical availability | Future only | Sprints 15/16 govern historical point-in-time availability. Plan 21 creates no historical evaluator, backfill, acceptance test, or runtime output. |
| Third-party authority | Not affected by runtime | Existing Plan-09 retention only; no new retention/use authority, provider call, sandbox call, or NSE automation. |

## Source qualification history and provider disposition

Plan 09 selected immutable Upstox Fundamentals ISIN-keyed observations for
Dividend, Bonus, Split, and Rights. Plan 11 records that the source does not
prove exhaustive empty-result meaning, finality/correction lineage, same-issue
continuity, historical revision identity, historical symbol change, or
adjusted-price semantics. The earlier #125 NSE qualification remains source
history; this smaller provider screen does not rewrite it.

The five-line evaluation remains exact:

1. **Expected value:** identify common price-breaking Dividend/Bonus/Split/Rights events for exact ISINs across the 20-session comparison window.
2. **Scope fit:** fits current/live supplied-cohort screening and reuses the already-authorized retained Upstox boundary through a narrow adapter.
3. **Material risk:** no documented exhaustive empty-result meaning, finality/correction lineage, same-issue continuity, or coverage of every restructuring class.
4. **Smallest alternative:** use direct completed closes, fail on any returned/unknown event or unavailable snapshot, and expose the limited provider-screened state.
5. **Decision:** **accepted for provider-screened current research only; rejected as authoritative no-break proof**.

NSE public UI/announcement material is optional manual positive corroboration. It
is never automated, never required to pass this screen, and an empty NSE result
never proves no action.

**Upstox is the first implementation adapter.** It is not a public-contract
prefix or a claim that every capability must have an Upstox implementation.

**Angel One is deferred, not implemented or selected.** The currently inspected
official SmartAPI contract documents historical raw OHLCV only. It documents no
adjusted-price flag or basis and no qualified corporate-action endpoint.
Accordingly it is a future raw-OHLCV qualification candidate; it is
**REJECTED/UNPROVEN** as an adjusted-price source and as a corporate-action
screening provider under the inspected contract. This specification authorizes
no Angel One credential, sandbox, or production call.

A future provider may be added only after a separately reviewed qualification
record supplies: official capability documentation; raw versus adjusted price
basis; event and timestamp semantics; retrieval and knowledge-time behavior;
retention/licence authority; payload and query bounds; and adapter tests proving
its mapping, failures, canonical identities, and no public leakage. Passing that
gate adds one concrete adapter and its descriptor; it does not authorize a
registry, reflection, source scanning, or speculative adapters.

## Standalone scope and later integration

The screen itself computes no close value, direction, threshold, breadth, trend,
higher-high/lower-low structure, range, market label, Market Structure, or price
adjustment. The retained schedule resolver must prove that supplied `S[0]` and
`S[20]` are exactly 20 completed official NSE Capital Market positions apart and
derive the exact official `S[20]` close instant. The screen accepts no owner-
supplied close timestamp.

Direct completed raw closes are normal market-data inputs. Adjustment or a skip
is required only when a detected price-changing corporate action would cross the
comparison. This v1 **skips detected events rather than adjusting prices**: a
supported in-window event makes this screen generically insufficient, so its
consumer must not compare across that event under this report. It neither
reconstructs nor labels adjusted, total-return, or economic-return prices.

Sprint 11 remains the later direct raw `S[0]`/`S[20]` close cohort-breadth
comparison. After this screen independently merges, rebased PR #124 may add a
separate Market Regime v2 that consumes only a successful screen report; its
unscreened v1 must never merge, select, or fall back. Market Structure remains
separate higher-high/higher-low work. A later approved Market Structure contract
may reuse this screen and define its own event-window skip/reset policy; Plan 21
neither starts nor specifies it.

## Canonical profile and re-frozen identities

All external objects are immutable closed JSON: UTF-8, no BOM, lexicographic
keys, compact separators, `allow_nan=false`, no duplicate keys, and one trailing
LF. Arrays retain declared order. `UtcInstant` is six-fraction UTC, `LocalDate`
is a real date, `Sha256` is 64 lowercase hex, `Sha256Prefixed` is
`sha256:<64 lowercase hex>`, `ProviderId` is lowercase ASCII `[a-z0-9-]{1,32}`,
and ISIN uses existing uppercase Luhn validation. Unknown/missing keys, wrong
types/nullability, malformed/noncanonical bytes, excess depth, or a bound failure
reject before a report. Every identity hashes canonical bytes excluding only that
object's self-identity field.

The existing Upstox source identity remains `3853a15b853b73a945065486ca96b48d4ee3625e4ed7c6e4927579e2b0b372a2`:

```json
{"adapter_release":"corporate-actions-v1","corporate_action_source":"upstox-fundamentals-v2","endpoint_template":"https://api.upstox.com/v2/fundamentals/{isin}/corporate-actions","plan09_contract":"corporate-action-provenance@v1"}
```

The exact reused Plan-09 snapshot/event contract identity remains
`de03833b00d0d286fc3d0116f7ce81b8694547d43b13250f7415d6c95fdbbf8a`.

The concrete Upstox provider-policy identity is
`55c66a5f53433231122c12be34f076d42d418fdb1dc8e98b2221622ef49aab03`:

```json
{"adapter_contract":"corporate-action-screen-provider@v1","adapter_type":"UpstoxCorporateActionScreenProviderV1","adapter_version":"upstox-corporate-action-screen-provider@v1","effects":{"directory_scan_attempts":0,"network_attempts":0,"storage_write_attempts":0},"plan09_store":{"contract":"corporate-action-provenance@v1","exceptions":[["CorporateActionMissingError","MISSING"],["CorporateActionStaleError","STALE"],["CorporateActionAmbiguousError","AMBIGUOUS"],["CorporateActionCorruptError","CORRUPT"]],"resolve_signature":"CorporateActionSnapshotStoreV1.resolve(*,isin:Isin,knowledge_cutoff:UtcInstant)->tuple[CorporateActionSnapshotMetadataV1,CorporateActionSnapshotV1]","success_tuple":{"metadata_fields":["isin","source","source_release","retrieved_at","snapshot_sha256","byte_count","event_count"],"snapshot_fields":["isin","source","source_release","retrieved_at","events"],"types":["CorporateActionSnapshotMetadataV1","CorporateActionSnapshotV1"],"validation":"metadata_and_snapshot_isin_source_source_release_retrieved_at_equal; metadata.snapshot_sha256==sha256(snapshot.canonical_json_bytes()); metadata.byte_count==len(snapshot.canonical_json_bytes()); metadata.event_count==len(snapshot.events)"}},"supported_event_mapping":{"normalized_fields":["kind","effective_date"],"source_type":"CorporateActionEventV1","supported_kinds":["DIVIDEND","BONUS","SPLIT","RIGHTS"]}}
```

The first-adapter capability identity is `a78a06576d293a8aa805772c376286b6d15ca6cbcbdc2804c64f1d4dadbf30eb`:

```json
{"adapter_contract":"corporate-action-screen-provider@v1","adapter_type":"UpstoxCorporateActionScreenProviderV1","adapter_version":"upstox-corporate-action-screen-provider@v1","capability":"current-supplied-cohort-corporate-action-screen","policy_identity_sha256":"55c66a5f53433231122c12be34f076d42d418fdb1dc8e98b2221622ef49aab03","provider_id":"upstox","snapshot_schema_identity_sha256":"de03833b00d0d286fc3d0116f7ce81b8694547d43b13250f7415d6c95fdbbf8a","source_identity_sha256":"3853a15b853b73a945065486ca96b48d4ee3625e4ed7c6e4927579e2b0b372a2"}
```

The complete v1 schema-bundle identity is `19171eebc3bd8421e782b7de9e54ecb52cc02a18a68f6c6dcd8d3858f26491f7`:

```json
{"aggregate_member_result":{"fields":[["provider_result","PrivateCorporateActionScreenProviderResultV1",false],["row_outcome","AggregateMemberOutcomeV1",false]]},"aggregate_private_result":{"fields":[["contract_version","Literal[current-supplied-cohort-corporate-action-screen@v1]",false],["input_identity_sha256","Sha256",false],["request_identity_sha256","Sha256",false],["runtime_code_identity_sha256","Sha256",false],["cohort_identity_sha256","Sha256",false],["comparison_session","LocalDate",false],["decision_session","LocalDate",false],["decision_session_close_at","UtcInstant",true],["decision_cutoff","UtcInstant",false],["schedule_evidence_sha256","Sha256",false],["schedule_source","Literal[nse-authoritative-calendar]",false],["schedule_source_release","Sha256Prefixed",false],["provider_id","ProviderId",false],["provider_capability_identity_sha256","Sha256",false],["provider_source_identity_sha256","Sha256",false],["provider_snapshot_schema_identity_sha256","Sha256",false],["provider_policy_identity_sha256","Sha256",false],["member_results","Array[PrivateCorporateActionScreenMemberResultV1]",false],["outcome","PrivateCorporateActionScreenOutcomeV1",false],["selected_snapshot_set_identity_sha256","Sha256",true],["private_result_identity_sha256","Sha256",false]]},"canonical_json":{"allow_nan":false,"encoding":"UTF-8","object_keys":"LEXICOGRAPHIC","separators":[",",":"],"trailing_lf":true},"conditional_invariants":{"aggregate_member_result":"store_outcome_MISSING_STALE_AMBIGUOUS_or_CORRUPT_is_preserved; AVAILABLE_with_retrieved_at_lt_derived_close_is_STALE_before_event_inspection; otherwise_AVAILABLE_with_any_effective_date_in_S0_through_S20_is_ACTION_OBSERVED; otherwise_AVAILABLE_is_SCREENED_NO_SUPPORTED_ACTION_OBSERVED","aggregate_private_result":"schedule_failure_precedes_provider_resolution_and_member_results_empty; otherwise_exactly_one_member_result_per_sorted_manifest_isin; aggregate_outcome_uses_precedence_MISSING_then_STALE_then_AMBIGUOUS_then_CORRUPT_then_ACTION_OBSERVED_then_SCREENED_NO_SUPPORTED_ACTION_OBSERVED; selected_set_non_null_iff_outcome_SCREENED_NO_SUPPORTED_ACTION_OBSERVED; private_result_identity_sha256_hashes_all_preceding_fields","input_identity_sha256":"sha256_of_all_preceding_input_fields","per_member_provider_result":"snapshot_identity_sha256_snapshot_byte_count_and_retrieved_at_non_null_iff_outcome_AVAILABLE; knowledge_cutoff_equals_request.decision_cutoff; outcome_not_AVAILABLE_implies_normalized_events_empty; normalized_events_sorted_by_effective_date_then_kind","public_report":"SCREENED_iff_decision_session_close_at_screen_state_and_selected_set_non_null_and_reason_null; otherwise_those_three_null_and_reason_CORPORATE_ACTION_SCREEN_INSUFFICIENT; report_identity_sha256_hashes_all_preceding_fields","request_identity_sha256":"sha256_of_all_preceding_request_fields","runtime_code_identity_sha256":"computed_once_at_aggregate_resolve_start_as_sha256_of_canonical_sorted_json_manifest_mapping_plus_lf_and_reused_unchanged"},"contract_version":"current-supplied-cohort-corporate-action-screen@v1","enums":{"AggregateMemberOutcomeV1":["SCREENED_NO_SUPPORTED_ACTION_OBSERVED","MISSING","STALE","AMBIGUOUS","CORRUPT","ACTION_OBSERVED"],"CorporateActionScreenCoverageLimitationV1":["PROVIDER_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE"],"CorporateActionScreenReasonV1":["CORPORATE_ACTION_SCREEN_INSUFFICIENT"],"CorporateActionScreenStateV1":["SCREENED"],"PrivateCorporateActionScreenOutcomeV1":["SCREENED_NO_SUPPORTED_ACTION_OBSERVED","MISSING","STALE","AMBIGUOUS","CORRUPT","ACTION_OBSERVED","SCHEDULE_UNAVAILABLE","SCHEDULE_LATE","SCHEDULE_CONTINUITY_UNPROVEN"],"ProviderObservationOutcomeV1":["AVAILABLE","MISSING","STALE","AMBIGUOUS","CORRUPT"],"SupportedCorporateActionKindV1":["DIVIDEND","BONUS","SPLIT","RIGHTS"]},"input":{"fields":[["contract_version","Literal[current-supplied-cohort-corporate-action-screen@v1]",false],["cohort_manifest","CurrentSuppliedCohortManifestV1",false],["comparison_session","LocalDate",false],["decision_session","LocalDate",false],["decision_cutoff","UtcInstant",false],["schedule_evidence_sha256","Sha256",false],["schedule_source","Literal[nse-authoritative-calendar]",false],["schedule_source_release","Sha256Prefixed",false],["provider_id","ProviderId",false],["screen_schema_identity_sha256","Sha256",false],["screen_policy_identity_sha256","Sha256",false],["input_identity_sha256","Sha256",false]]},"normalized_supported_event":{"fields":[["kind","SupportedCorporateActionKindV1",false],["effective_date","LocalDate",false]]},"per_member_provider_result":{"fields":[["isin","Isin",false],["provider_id","ProviderId",false],["provider_capability_identity_sha256","Sha256",false],["provider_source_identity_sha256","Sha256",false],["provider_snapshot_schema_identity_sha256","Sha256",false],["provider_policy_identity_sha256","Sha256",false],["snapshot_identity_sha256","Sha256",true],["snapshot_byte_count","Integer[1..1048576]",true],["retrieved_at","UtcInstant",true],["knowledge_cutoff","UtcInstant",false],["normalized_supported_events","Array[NormalizedSupportedCorporateActionEventV1]",false],["outcome","ProviderObservationOutcomeV1",false]]},"provider_descriptor":{"fields":[["provider_id","ProviderId",false],["capability_identity_sha256","Sha256",false],["source_identity_sha256","Sha256",false],["snapshot_schema_identity_sha256","Sha256",false],["policy_identity_sha256","Sha256",false]]},"public_report":{"fields":[["contract_version","Literal[current-supplied-cohort-corporate-action-screen@v1]",false],["input_identity_sha256","Sha256",false],["request_identity_sha256","Sha256",false],["runtime_code_identity_sha256","Sha256",false],["cohort_identity_sha256","Sha256",false],["comparison_session","LocalDate",false],["decision_session","LocalDate",false],["decision_session_close_at","UtcInstant",true],["decision_cutoff","UtcInstant",false],["schedule_evidence_sha256","Sha256",false],["schedule_source","Literal[nse-authoritative-calendar]",false],["schedule_source_release","Sha256Prefixed",false],["provider_id","ProviderId",false],["provider_capability_identity_sha256","Sha256",false],["provider_source_identity_sha256","Sha256",false],["provider_snapshot_schema_identity_sha256","Sha256",false],["provider_policy_identity_sha256","Sha256",false],["screen_schema_identity_sha256","Sha256",false],["screen_policy_identity_sha256","Sha256",false],["screen_state","CorporateActionScreenStateV1",true],["selected_snapshot_set_identity_sha256","Sha256",true],["coverage_limitation","CorporateActionScreenCoverageLimitationV1",false],["reason","CorporateActionScreenReasonV1",true],["report_identity_sha256","Sha256",false]]},"request":{"fields":[["contract_version","Literal[current-supplied-cohort-corporate-action-screen@v1]",false],["input_identity_sha256","Sha256",false],["cohort_manifest","CurrentSuppliedCohortManifestV1",false],["comparison_session","LocalDate",false],["decision_session","LocalDate",false],["decision_cutoff","UtcInstant",false],["schedule_evidence_sha256","Sha256",false],["schedule_source","Literal[nse-authoritative-calendar]",false],["schedule_source_release","Sha256Prefixed",false],["provider_id","ProviderId",false],["screen_schema_identity_sha256","Sha256",false],["screen_policy_identity_sha256","Sha256",false],["request_identity_sha256","Sha256",false]]}}
```

The complete generic screen-policy identity is `52656e4b209d4d350397a42913d85ad6f74df15351fe0ce2af54fa9d443bef20`:

```json
{"aggregate_classification":{"aggregate_outcome_precedence":["MISSING","STALE","AMBIGUOUS","CORRUPT","ACTION_OBSERVED","SCREENED_NO_SUPPORTED_ACTION_OBSERVED"],"row_classification":[["provider_outcome_MISSING","MISSING"],["provider_outcome_STALE","STALE"],["provider_outcome_AMBIGUOUS","AMBIGUOUS"],["provider_outcome_CORRUPT","CORRUPT"],["provider_outcome_AVAILABLE_and_retrieved_at_lt_derived_decision_session_close_at","STALE"],["provider_outcome_AVAILABLE_and_retrieved_at_gte_derived_decision_session_close_at_and_any_normalized_event.effective_date_inclusive_in_S0_through_S20","ACTION_OBSERVED"],["provider_outcome_AVAILABLE_and_retrieved_at_gte_derived_decision_session_close_at_and_no_in_window_normalized_event","SCREENED_NO_SUPPORTED_ACTION_OBSERVED"]],"schedule_precedence":"schedule_failure_precedes_provider_resolution"},"contract_version":"current-supplied-cohort-corporate-action-screen@v1","invariants":{"adjustment_attempts":0,"directory_scan_attempts":0,"network_attempts":0,"public_member_event_path_details":false,"storage_write_attempts":0},"provider_resolution":{"call_count":"exactly_once_per_sorted_manifest_isin_after_schedule_admission","order":"ascending_isin","result_validation":"each_result.isin_and_descriptor_exactly_equal_isin_argument_and_injected_descriptor"},"provider_selection":{"adapter_match":"input.provider_id==injected_provider.descriptor.provider_id","mismatch":"ValueError_no_report","mode":"one_explicitly_injected_adapter","registry_reflection_attempts":0,"runtime_configuration":"may_select_one_provider_per_capability_before_construction","silent_fallback_attempts":0},"runtime_code_identity":{"manifest":"canonical_sorted_json_mapping_relative_module_path_to_source_sha256_plus_lf","manifest_entries":"lexicographically_sorted_unique_relative_module_path_to_sha256","manifest_self_entry":"forbidden_nonrecursive","runtime_code_identity":"sha256(canonical_manifest_mapping_bytes)"},"schedule":{"derived_close":"ScheduleEvidenceStore.resolve(schedule_evidence_sha256)_under_admitted_root_lease_then_exact_source_and_source_release_equality","outcomes":["SCHEDULE_UNAVAILABLE","SCHEDULE_LATE","SCHEDULE_CONTINUITY_UNPROVEN"],"rule":"S0_and_S20_are_exactly_20_completed_positions_apart"},"screen":{"current_raw_close_rule":"direct_completed_close_is_normal_except_across_detected_price_changing_actions","detected_price_changing_action_rule":"skip_detected_events_in_v1_never_adjust","empty_provider_result":"nonexhaustive_provider_screened_evidence_not_authoritative_negative"}}
```

The selected-snapshot-set projection format is frozen under identity
`74c2e55bddcdc886f2aaf2d5db13fa76d28fc242e9546756fa9a3e3529220816`:

```json
{"header_fields":["contract_version","input_identity_sha256","request_identity_sha256","runtime_code_identity_sha256","cohort_identity_sha256","comparison_session","decision_cutoff","decision_session","schedule_evidence_sha256","schedule_source","schedule_source_release","provider_id","provider_capability_identity_sha256","provider_source_identity_sha256","provider_snapshot_schema_identity_sha256","provider_policy_identity_sha256","screen_schema_identity_sha256","screen_policy_identity_sha256"],"invariants":{"all_member_outcomes":"AVAILABLE","all_row_outcomes":"SCREENED_NO_SUPPORTED_ACTION_OBSERVED","knowledge_cutoff":"equals_decision_cutoff","retrieved_at_snapshot_identity_and_snapshot_byte_count":"non_null","rows_cover":"every_and_only_manifest_isin"},"normalized_supported_event_fields":["kind","effective_date"],"normalized_supported_events_sorted_by":["effective_date","kind"],"row_fields":["isin","provider_id","provider_capability_identity_sha256","provider_source_identity_sha256","provider_snapshot_schema_identity_sha256","provider_policy_identity_sha256","snapshot_identity_sha256","snapshot_byte_count","retrieved_at","knowledge_cutoff","normalized_supported_events"],"rows_sorted_by":"isin"}
```

For each successful result, `selected_snapshot_set_identity_sha256` is SHA-256
of one canonical value with the frozen header fields and one `snapshots` array,
strictly sorted by ISIN. It exists only when every and only manifest ISIN has an
`AVAILABLE` provider observation that the aggregate classifies as
`SCREENED_NO_SUPPORTED_ACTION_OBSERVED`. Each row then has non-null snapshot
identity, byte count, and retrieval timestamp; its `knowledge_cutoff` exactly
equals `decision_cutoff`. Each normalized supported event is one of `DIVIDEND`,
`BONUS`, `SPLIT`, or `RIGHTS`, has a non-null `effective_date`, and is sorted by
`(effective_date, kind)`. The public report exposes only the computed set hash,
never this projection or its rows.

## Ordered V1 types, adapter boundary, and nullability

The complete schema projection above is authoritative: it freezes the exact
input, request, provider descriptor, normalized event, per-member provider
result, aggregate private result, public report, enum/literal values, field
order/types/nullability, and conditional invariants. The prose below explains it
without creating a second representation.

### Generic owner-private input and request

`CurrentSuppliedCohortCorporateActionScreenInputV1` has exactly the ordered
`input` fields in the frozen schema. Its `provider_id` is a required request
selection, not a source name. `input_identity_sha256` hashes all preceding input
fields. It contains no close time, storage path, URL, credential, event,
snapshot identity, raw payload/OHLC, or claim that an action is absent.

At aggregate resolve start, the resolver computes one
`runtime_code_identity_sha256` as
`SHA256(canonical sorted JSON manifest mapping + LF)`. The closed manifest maps
unique relative module paths to source SHA-256 values; canonical JSON sorts its
keys lexicographically. It has no self-entry or self-hash, so the construction
is nonrecursive. That one value is reused unchanged in the selected-set,
aggregate-private, and public-report identities.

The generic resolver next validates that the explicitly injected descriptor has
exactly `input.provider_id`. A mismatch is structural `ValueError` before
request construction, schedule/provider reads, private result, public report, or
report hash. It is not an outcome and cannot become generic public insufficiency;
therefore every emitted private/public provenance field is coherent with one
admitted adapter.

`CurrentSuppliedCohortCorporateActionScreenRequestV1` copies exactly the frozen
input values and adds only `request_identity_sha256`, which hashes all preceding
request fields. It has no derived close and no caller may provide a close. The
aggregate resolver alone resolves the schedule and derives the official close.

`CorporateActionScreenProviderDescriptorV1` contains exactly the five non-null
descriptor fields: `provider_id`, `capability_identity_sha256`,
`source_identity_sha256`, `snapshot_schema_identity_sha256`, and
`policy_identity_sha256`. The Upstox descriptor binds the frozen Upstox
provider-policy identity above. These are opaque identities to generic
consumers; only `provider_id` is provider-specific public data.

`NormalizedSupportedCorporateActionEventV1` is private and contains exactly
non-null `kind: SupportedCorporateActionKindV1` and `effective_date: LocalDate`.
It holds no provider wording, ratio, amount, announcement time, record date,
event digest, or raw event.

### Narrow provider port and exact invocation

```text
CorporateActionScreenProviderPortV1
  .descriptor: CorporateActionScreenProviderDescriptorV1
  .resolve_exact(
      request: CurrentSuppliedCohortCorporateActionScreenRequestV1,
      isin: Isin,
      lease: StorageRootLease
  ) -> PrivateCorporateActionScreenProviderResultV1
```

The port resolves only one exact retained observation at `request.decision_cutoff`.
It neither receives nor derives the schedule close, and it makes no stale,
action-observed, or ready screen decision. Its typed result is one observation/
store outcome plus validated metadata/snapshot identity and normalized events.

After matching-descriptor and schedule admission,
`CurrentSuppliedCohortCorporateActionScreenResolverV1` calls
`resolve_exact(request, isin, lease)` **exactly once for every manifest ISIN in
ascending ISIN order**. It validates every returned ISIN and descriptor against
that call's `isin` argument and the injected descriptor, then alone classifies
the aggregate. It does not instantiate adapters, inspect a registry, reflect
over modules, scan the filesystem, probe another provider, or silently fall
back. Runtime configuration may select one provider **per capability before
resolver construction**; it cannot weaken descriptor equality.

### First concrete adapter — `UpstoxCorporateActionScreenProviderV1`

`UpstoxCorporateActionScreenProviderV1` is the sole first adapter. For its one
`isin` argument, it calls the existing Plan-09 store exactly as frozen in its
provider-policy projection:

```text
CorporateActionSnapshotStoreV1.resolve(
  *, isin=isin, knowledge_cutoff=request.decision_cutoff
) -> tuple[CorporateActionSnapshotMetadataV1, CorporateActionSnapshotV1]
```

The adapter maps only these four existing Plan-09 exceptions:

```text
CorporateActionMissingError   -> MISSING
CorporateActionStaleError     -> STALE
CorporateActionAmbiguousError -> AMBIGUOUS
CorporateActionCorruptError   -> CORRUPT
```

A success tuple maps to `AVAILABLE`, never to a screen-ready state. Before it
returns `AVAILABLE`, the adapter requires exact equality of metadata/snapshot
ISIN, source, source-release, and retrieval timestamp; validates
`metadata.snapshot_sha256 == SHA256(snapshot.canonical_json_bytes())`; validates
`metadata.byte_count == len(snapshot.canonical_json_bytes())`; and validates
`metadata.event_count == len(snapshot.events)`. It writes the exact metadata
snapshot digest and byte count to the private result. It does **not** name or map
a nonexistent Plan-09 `SCREENED` state.

For an `AVAILABLE` result it normalizes only Plan-09 `DIVIDEND`, `BONUS`,
`SPLIT`, and `RIGHTS` into private kind/effective-date pairs, sorted by
`(effective_date, kind)`. It maps no other provider event type. Snapshot digest,
byte count, and retrieval timestamp are non-null exactly for `AVAILABLE`; all
three are null for the four store outcomes. `knowledge_cutoff` is always
non-null and exactly `request.decision_cutoff`. A non-`AVAILABLE` result has an
empty normalized-event array; an `AVAILABLE` result may have an empty or
nonempty array. No post-close or in-window action decision belongs to the
adapter.

Schedule failure precedes every provider resolution and produces the schedule
private outcome with no member rows. After schedule admission, the aggregate
resolver classifies each member row in this exact order: preserve store
`MISSING`, `STALE`, `AMBIGUOUS`, or `CORRUPT`; for `AVAILABLE`, classify `STALE`
when `retrieved_at < derived_decision_session_close_at` **before inspecting
events**; otherwise classify `ACTION_OBSERVED` when any normalized event
effective date lies inclusively in `S[0]..S[20]`; otherwise classify
`SCREENED_NO_SUPPORTED_ACTION_OBSERVED`.

The aggregate's mixed-member private outcome uses this exact precedence:
`MISSING`, `STALE`, `AMBIGUOUS`, `CORRUPT`, `ACTION_OBSERVED`, then
`SCREENED_NO_SUPPORTED_ACTION_OBSERVED`. Thus only every ready row produces a
screened aggregate; every earlier outcome maps to the single generic public
`CORPORATE_ACTION_SCREEN_INSUFFICIENT`. An empty available Upstox event list is
nonexhaustive provider-screened evidence, never exhaustive negative proof.

The adapter and resolver are bounded read-only operations: 1–50 exact ISIN
resolutions and the existing Plan-09 bounds (1 MiB, 1,000 events, depth 64).
They perform zero network/provider calls, writes, refreshes, retries, background
work, scans/listing/globs, latest-now selection, adjustments, gap inference,
NSE access, or public detail emission. Existing descriptor-relative private-root
controls remain required: no-follow components; root/directory attachment
revalidation before, during, and after reads; owner-private mode; regular file;
single link; stable metadata; canonical bytes; and digest. Attachment loss
discards private projections.

### Generic aggregate and public report

`PrivateCorporateActionScreenResultV1` is the ordered aggregate-private result
in the frozen schema. It binds contract/input/request/runtime identities,
cohort/schedule/provider identities, the aggregate-derived nullable official
close, exactly sorted per-member aggregate rows (each binding a provider result
to its frozen `AggregateMemberOutcomeV1`), aggregate outcome, optional
selected-set hash, and `private_result_identity_sha256`. Its member results are
empty only for a schedule outcome; otherwise there is exactly one row for every
sorted manifest ISIN. Its aggregate outcome uses the frozen precedence above;
its selected-set hash is non-null only for aggregate
`SCREENED_NO_SUPPORTED_ACTION_OBSERVED`.

`CurrentSuppliedCohortCorporateActionScreenReportV1` has exactly the frozen
`public_report` fields. Its `decision_session_close_at` can come only from the
aggregate's admitted schedule resolution; it is absent on public insufficiency.
Provider data is limited to `provider_id` and opaque
capability/source/snapshot-schema/policy identities; it contains no provider-
specific class/type/source literal, member, ISIN, event, store/schedule outcome,
close value, byte, payload, path, catalog row, or free-form diagnostic. All
input, request, runtime, provider, schedule, screen-schema, screen-policy, and
coverage fields are non-null on both report outcomes. `coverage_limitation` is
always exactly `PROVIDER_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE`.

| Public state | `decision_session_close_at` | `screen_state` | selected-set hash | `reason` |
| --- | --- | --- | --- | --- |
| successful screen | non-null aggregate-derived close | `SCREENED` | non-null | null |
| generic insufficiency after matching adapter | null | null | null | `CORPORATE_ACTION_SCREEN_INSUFFICIENT` |

## Compatibility, release sequence, and future checks

This revision deliberately replaces the prior Upstox-specific public contract.
There are no old `CurrentSuppliedCohortUpstoxActionScreen*`,
`PrivateUpstoxActionScreenResultV1`,
`PrivateUpstoxActionScreenResolverPortV1`, Upstox-specific public state, source
literal, alias, re-export, compatibility serializer, or dual public report path.
Implementation must clean-rename every affected source/test caller before merge;
the old representation must not coexist. The exact Upstox adapter remains
private behind the generic port, except for `provider_id` and opaque identities
required for provenance.

Plan 21 merges as the standalone screen before PR #124. It accepts/inherits no
`CurrentSuppliedCohortMarketRegime` input/request/report, archive, breadth, or
market label, and changes none of Plans 09, 11, 12, or 19. Then PR #124 rebases
and adds the separate Market Regime v2 cutover that accepts only a successful
screen report. Unscreened v1 cannot merge, select, or fall back. V2 preserves
Plan 20/v1 replay history without claiming historical v1 reports were screened.

Sprints 15/16, not Plan 21, later govern historical no-backfill availability.
This plan has no historical output, test, or gate.

A future candidate must verify N=1/5/50; exact schedule 20-position and
close/cutoff boundaries; all schedule outcomes; structural descriptor-mismatch `ValueError` with no report; every legal
Plan-09 success tuple, metadata digest/byte-count validation, and exception mapping; all four normalized kinds; empty nonexhaustive evidence; exact
provider/selected-set schema and per-result hash; canonical input/request/report
round trips; every frozen identity; attachment/binding failures; zero effects and
public leakage; standalone absence of Market Regime imports; clean removal of
Upstox-specific public names; and later separate v2 integration with no v1
fallback. Owner acceptance also requires exact-candidate focused/full/release
gates, installed-wheel/CLI smoke, hosted CI/security, and independent exact-
revision R3 functional, security/provenance, and temporal review.

## Non-goals

Plan 21 does not implement source/tests; alter PR #124; create Market Regime v2;
create an Angel One adapter or general all-capability framework; call
Upstox/Angel One/NSE/SEBI; use credentials; use a sandbox; acquire/retain
evidence; add dependencies; automate NSE UI; adjust/reconstruct prices; infer
events from gaps; prove no action; create a historical evaluator; start Sprint
12; recommend; or trade. Issue #116 and PR #124 remain blocked until this
standalone capability merges and later v2 integration passes its own gates.
