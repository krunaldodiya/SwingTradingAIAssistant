# Bounded current raw price-context refresh contract

Status: **DELIVERED — Issue #189 closed through merged PR #200; deterministic acceptance evidence below; no live-provider or production-latency claim**
Risk: **R3** — public temporal truth, provenance, provider effects, and immutable publication.

## Purpose and public boundary

`current-price-context@v2` is an additive one-request/one-response SDK and CLI
contract over the accepted `current-price-context@v1` workflow. It preserves an
exact V1 completed-session result and, when requested, reports separately
labelled current-session observations. It is not a poller, stream, scheduler,
cache service, source profile, recommendation, or order interface.

The closed `current-price-context-request@v2` contains the V1 selection time,
deadline, retained schedule identity, ordered 1–50 canonical NSE equity
members, four fixed questions, and optional exact Industry archive reference,
plus:

- `execution_mode`: `RETAINED_ONLY`, `ACQUIRE_MISSING`, or `REFRESH_ONCE`;
- `include_current_session`: an exact boolean.

Unknown and duplicate JSON fields, unsupported modes/versions, and malformed
nested values fail before storage, credential, or provider access. The request
is bounded to 64 KiB. The response is bounded to 1 MiB. V1 request/result
schemas, canonical decoders and bytes, CLI default, and `--acquire-missing`
meaning remain unchanged. The one narrow additive V1 reader change is that a
current-month provisional object is now selected by canonical security ID rather
than current symbol, then admitted only when its exact provider instrument key,
retained schedule, and knowledge/data cutoffs match the current mapping.

The SDK entry point is `research_current_price_context_v2(request,
storage_root, *, clock=None, cancellation=None)`. The optional cancellation
hook is the existing `CurrentRawCancellationV1` protocol and is passed through
every acquisition/read control in the one pass. The CLI selects V2 only with
`price-context-current --contract-version v2`; the default remains `v1`.
For V2, mode is request-owned and combining `--acquire-missing` with V2 is
invalid before effects.

## Result and temporal accounting

The V2 response embeds the admitted `CurrentPriceContextResultV1` as
`completed_context`; no provisional value may alter its members, breadth,
Structure, direction, Industry state, or evidence cutoff. Top-level accounting binds the complete owner request (deadline, exact ordered
member identities and aliases, schedule, questions, Industry reference, mode,
and provisional inclusion), query/data-selection time, inspection time,
optional acquisition start/end, final evidence cutoff, attempted/completed
provider calls, reused physical objects, refreshed physical objects, and the
per-invocation hard budget. A bounded public `freshness_ledger` emits one
sanitized source/slot entry for each relevant Calendar, Mapping, closed-month,
current-history, current-session, corporate-action, and Industry source. Each
entry carries only the requested member identity where applicable, an immutable
physical digest when available, a closed state (`REUSED`, `ACQUIRED`,
`REFRESHED`, `APPENDED`, `CONFLICTED`, `UNAVAILABLE`, or `NOT_REQUESTED`),
source/publication/knowledge clocks, bounded attempted/completed call counts,
and its closed correction rule. The single global `MAPPING` entry is
accounting-only: its state and call counts are truthful, while its physical
digest and all provenance/time fields are null. Available per-member mapping
identity and retrieval time remain in the embedded V1 member evidence. A
`CURRENT_SESSION` entry also carries a nullable `prior_source_cutoff`: it is
present only for an observed retained prefix, equals the final cutoff for
`REUSED` and `REFRESHED`, and is strictly less than the final cutoff for
`APPENDED`; `ACQUIRED` and all non-observed or non-current entries leave it
null. Counts are exactly zero or one except that a
`CURRENT_HISTORY` entry may aggregate zero, one, or two completed-context
provider calls when the retained schedule proves that the 21-session window
ends on the completed selection-day session. This narrow exception represents
the existing Plan-06 split of prior-day Historical V3 evidence and the completed
selection-day Intraday V3 evidence in one current-month physical partition;
`CURRENT_SESSION` remains exclusively active/provisional. It never exposes
paths, URLs, credentials, provider bodies, or private archive contents. Ledger
call totals must equal top-level totals and its size is at most `5N+3`. A shared
mapping acquisition is one global `MAPPING` ledger entry, not one entry per
member.
Decoder validation rebinds completed partition digest/cutoff order, source
correction rule, chronological unique month slots, and the 64-day bound. The
response also carries the exact ordered `physical_plan`; runtime constructs it
from the retained calendar/planning rules before effects and revalidates the
same plan against the schedule before return. It is never inferred merely from
ledger keys or a schedule digest.

Nullable clocks are emitted only when the corresponding event occurred; all
non-null clocks are UTC, monotonic within the pass, and at or before the request
deadline. Acquisition start is the first opener attempt and completion is the
settlement of the last attempted opener. A terminal non-success status is an
attempted and completed transport call but never reads its body; the
body-success callback runs only after the bounded body read succeeds. A failed
current-session attempt overlays that member as `UNAVAILABLE` without changing
retained provisional bytes or catalog rows.

There is exactly one current-session result per requested member, in input
order. Its state is one of `OBSERVED`, `NOT_APPLICABLE`, `NOT_REQUESTED`,
`UNAVAILABLE`, or `CONFLICTED`. `OBSERVED` is labelled
`PARTIAL_CURRENT_SESSION` and includes only the last fully completed scheduled
one-minute bar, its raw close as current observed price, cumulative
source-reported session volume through that minute, exact source time/version,
immutable partition checksum, publication time, and knowledge time. Other
states contain no price, volume, or evidence provenance and carry one closed,
sanitized reason. Pre-open, holidays, and weekends are `NOT_APPLICABLE`;
explicit exclusion is `NOT_REQUESTED`. The in-progress minute is never emitted.

The response says `request`/`response` and `refresh once`; it has no polling,
stream, subscription, interval, or background-work field. Runtime source bytes
are bound by a V2 manifest and result identity.

## Acquisition, reuse, and immutable publication

All modes first inspect under the existing private-root and exact retained
calendar authorities. `RETAINED_ONLY` performs zero provider effects.
`ACQUIRE_MISSING` invokes the existing serial V1 acquisition only for missing
admissible completed evidence and may fill a missing admissible current-session
slot. `REFRESH_ONCE` first performs exactly that missing completed-evidence work;
it does **not** force-refresh reusable Mapping, closed-month, current-history,
corporate-action, Calendar, or Industry evidence. When current-session evidence
is requested and its dependencies remain admissible, it then performs at most
one Intraday V3 current-session acquisition per member and revalidates the
mutable overlap even when a prior provisional prefix is reusable. It may append
newly completed minutes and does not claim suffix-only fetching. Provider
concurrency is one, retry/redirect/fallback/poll/stream count is zero.

Verified immutable closed months are reused when the logical 21-session window
moves. Mutable current-month evidence must match the exact retained schedule,
minute grid, and canonical ISIN/security identity. Retained provisional lookup
is keyed by the canonical security ID and validates the provider instrument key,
schedule, cutoffs, immutable object, and row grid; therefore a retained old-symbol
artifact may satisfy a newly admitted alias without migration or a dual write.
Identical overlap may be revalidated. `APPENDED` requires a strictly advanced
validated source cutoff; an identical no-new-minute response is `REFRESHED`.
Changed already-completed same-source overlap is `CONFLICTED_EVIDENCE`; the old
immutable generation and catalog row remain untouched and no conflicting
generation is published. The only accepted source transition is the existing
Intraday V3 to Historical V3 finalization after a complete historical grid; it
publishes a new immutable generation and never rewrites prior bytes.

Current-session provisional planning derives its target exclusively from the
request-owned selection time (never a later clock), begins only after the first
full scheduled minute, and ends strictly before the exact sourced close. At or
after exact close, the day enters completed facts only through the existing
Plan-06 `session_complete` admission with every scheduled minute present; its
completed-context acquisition may use the Plan-06 Historical-prior-days plus
Intraday-selection-day split, but no separate provisional Intraday pass is
planned. When that completed split requires two openers, both are projected onto
the one `CURRENT_HISTORY` physical-partition entry under the bounded exception
above and remain separate in private opener accounting. After IST rollover,
prior Intraday V3 rows must first finalize to Historical V3. No correction epoch
or negative-completeness claim is invented.

Mapping and corporate-action handling retain V1 identity and cutoff rules.
Alias-only drift may reuse physical evidence only when canonical/security
identity is unchanged; new effects use the currently admitted alias. Canonical
or security-ID drift cannot select the old artifact and blocks. Industry is exact
retained-only and local: its absence or failure does not erase admitted raw
completed or provisional facts. Completed partition ledger entries come only
from the completed-session plan and bind its V1 digest/source-time tuples in
order; the separately planned Intraday entry comes only from the active plan.

## Precedence, cancellation, and bounds

Fatal precedence is: malformed/unsupported request; selection/deadline/IST or
cancellation; root/catalog authority; retained calendar; mapping; shared
auth/authorization/rate/deadline stop; member-local provider/data failure;
optional provisional state; local Industry; final root/schedule/source reread.
Shared stops prevent later openers but do not erase earlier completed facts that
still revalidate. Root or catalog loss remains fatal. One invocation-owned root device/inode
identity (including absent-root semantics) is checked at every V2 inspection,
acquisition, final read, publication boundary, and return; a replacement is
never adopted. Cancellation is checked before each opener, after each response,
before publication, and before return.

The accepted bounds remain: exactly 21 completed sessions, at most 64 inclusive
calendar days, at most three physical months, and at most 10,000 selected
minutes per member (rejected before any credential or provider effect), 1–50
members, one exclusive writer, and an invocation deadline no later than 30
minutes or IST rollover. Provider accounting is per invocation and process only.
The existing `5N+1` budget, hard-capped at 251, includes V2 current-session
effects and is checked before every opener; aggregating the two authorized
exact-close completed-context calls does not increase this budget or the public
ledger cardinality. The implementation makes no cross-process quota claim.

### Accepted response-only authenticity boundary (Issue #189 owner decision)

On 2026-09-20, the repository owner accepted the response-only boundary identified
in Issue #189 review. The canonical V2 decoder enforces canonical encoding,
supported values, request/cross-field consistency, finite state/accounting, and
runtime identity. It does not authenticate a wholly self-consistent price/volume
reseal against retained partition bytes. The SDK runtime derives and validates
retained-row price and cumulative-volume values under captured storage-root
authority; that runtime binding is the accepted protection. No response-only
anti-substitution claim is made without an authenticated value-to-partition
attestation.

On 2026-09-21, the repository owner additionally accepted the equally narrow
V2 response-only limitation for a self-consistent `CURRENT_SESSION`
`APPENDED`→`REFRESHED` reseal whose `prior_source_cutoff` is changed to the
final cutoff. Direct runtime truth remains derived from captured pre-pass
retained evidence; the decoder enforces canonical/internal consistency, not
authentication of that exact retained-history transition. This is not a
broader waiver, signing scheme, dependency adoption, or trusted-input redesign.

### Accepted exact-close accounting amendment

On 2026-09-19 the repository owner authorized the narrow exception above after
reconciling Plan 36 with the retained Plan-06 provider boundary. The alternatives
were to add a new public completed-session opener entry, which would enlarge the
source vocabulary and ledger bounds, or to claim Historical V3 supplies the
selection-day session, which contradicts Plan 06 and was rejected. The selected
option keeps one public row per physical current-month partition, preserves
separate private opener records and exact top-level totals, and permits two calls
only when schedule-owned planning proves the completed-selection-day case. The
amendment must be reconsidered if Plan-06 provider routing or the one-row-per-
physical-object ledger contract changes.

## Compatibility, evidence, and rollback

Historical Upstox, Yahoo, BharatStock, current-stock-research, regime, Structure,
price-action, Industry, V1 public schemas/canonical encoding and decoder, the
default V1 CLI, and old retained evidence remain compatible; none is a fallback
or substitute. V1 results retain their existing runtime-source identity binding,
so otherwise identical output may legitimately carry a different runtime identity
across reviewed source revisions; this does not promise that an old V1 binary can
decode a V2 response with unknown fields.
The internal V1 current-month reader has the same narrow additive security-ID
alias lookup and exact provider-instrument/cutoff validation described above.
This is neither a retained-data migration nor a dual write. Deterministic
temporary-root, controlled-clock, and provider-substitute tests may prove
one-shot semantics, exact minute boundaries, immutable conflict refusal,
accounting, failure isolation, bounds, and V1 compatibility. They cannot prove
live credentials, provider behavior, private retained observations, throughput,
deployment, or market correctness.

Rollback removes only the additive V2 module/export/CLI selector and V2 runtime
manifest. It does not delete or rewrite valid retained evidence and leaves all
V1 entry points and historical readers intact.

## Adversarial acceptance matrix

The matrix is the review-candidate acceptance boundary, not live-provider or
release evidence. `DIRECT PASS` means the V2 public workflow has relevant output
and prohibited-effect assertions. `INHERITED` is narrower: V2 constructs the
exact V1 owner request, embeds the exact V1 result, and its result validator
rebinds selection time, schedule, ordered canonical members/aliases, questions,
cutoff, and result identity. Therefore named V1 tests are transitive only for
that unchanged completed-context machinery; they do not prove V2-only
provisional timing. `INSPECTION` names a static contract limit rather than an
executed provider claim.

| Frozen scenario | Observable invariant and prohibited claim | Exact evidence | Status |
|---|---|---|---|
| Retained exact 1 and 50 members | Exact V1 completed context, order and denominator; zero provider effects in retained-only; no truncation/restamp | `test_v2_retained_only_preserves_completed_result_and_never_opens_provider`; V1 `test_public_n50_success_and_n51_request_rejection_are_effect_bounded`, `test_public_retained_member_fact_is_immutable_deterministic_and_private` | DIRECT PASS + INHERITED |
| Cohort 0/51; session 20/22; day 64/65; minute 10,000/10,001; budget exact/+1; request/result size exact/+1 | Accept exact bounds and reject limit-plus-one before widened work; no clipping or padding | V1 `test_public_request_is_closed_bounded_and_preserves_order`, `test_public_n50_success_and_n51_request_rejection_are_effect_bounded`, `test_n50_has_exact_three_month_251_bound_and_n51_is_rejected_before_effects`, `test_four_month_64_day_schedule_stops_before_credentials_or_provider_effects`, `test_public_request_decoder_rejects_malformed_oversize_nested_and_enum_values`; Plan-06 `test_inputs_are_bounded_and_exact_typed`; strict V2 request/result constructors | INHERITED + INSPECTION |
| Unknown/duplicate fields, unsupported mode/version, malformed enums/reasons/decimals/clocks/counters/nested values | Closed pre-effect rejection normalized to `ValueError`; no root/provider access | `test_v2_request_decoder_is_closed_and_publicly_exported`, `test_v2_request_accepts_only_the_three_one_shot_modes`, `test_v2_result_decoder_rejects_resealed_request_reason_price_and_time_mutations`; V1 decoder limit tests | DIRECT PASS |
| Strict result rebinding and canonical round trip | Exact request identity, schedule, ordered canonical members/aliases, questions, mode, inclusion, deadline, embedded V1 result, Calendar/Industry identity and state, ordered partition digests/clocks, freshness accounting, and result identity rebind; no unsupported member/reason/price/time mutation, duplicate, omission, or reorder. The decoder does not authenticate only (1) a wholly self-consistent provisional **price/volume** reseal against retained partition bytes, or (2) a `CURRENT_SESSION` `APPENDED`→`REFRESHED` reseal whose `prior_source_cutoff` is changed to the final cutoff against captured retained history. No other member, reason, time, state, cutoff, provenance, or accounting substitution is waived. | `test_v2_result_decoder_rejects_resealed_request_reason_price_and_time_mutations`, `test_v2_refresh_once_appends_full_minutes_and_refuses_changed_overlap`, `test_v2_cross_month_ledger_uses_completed_plan_partition_order`, `test_v2_retained_only_preserves_completed_result_and_never_opens_provider`; V1 `test_public_result_decoder_rejects_rehashed_cross_field_and_nested_violations` | DIRECT PASS + INHERITED |
| Missing completed evidence | Only V1-planned missing physical slots are acquired serially and revalidated; no V2 parallel/fallback fetch or force-refresh of reusable completed slots | `test_v2_refresh_once_appends_full_minutes_and_refuses_changed_overlap`; V1 `test_acquire_missing_establishes_cutoff_only_after_effects`, acquisition planner/accounting tests | DIRECT PASS + INHERITED |
| Public freshness/accounting disclosure | Entries are typed, bounded, request ordered, partition-order paired, additive, and total completed responses never exceed calls. The one shared global Mapping row is accounting-only: its truthful state/calls are public and its provenance/time fields are null; available identity/time remain in embedded V1 member evidence. Later mapped members reuse it; exact `5N+1` budget remains; no private root/header/token. | `test_v2_retained_only_preserves_completed_result_and_never_opens_provider`, `test_v2_acquire_missing_shares_one_mapping_call_for_two_members`, `test_v2_refresh_once_appends_full_minutes_and_refuses_changed_overlap`, `test_v2_cross_month_ledger_uses_completed_plan_partition_order` | DIRECT PASS |
| Pre-open | Prior completed context remains the embedded V1 result; provisional `NOT_APPLICABLE`; zero Intraday calls | `test_v2_retained_schedule_boundaries_never_open_intraday[pre-open]` | DIRECT PASS |
| In-session before first full minute | Completed context remains separate; provisional has no open candle and no Intraday effect | `test_v2_retained_schedule_boundaries_never_open_intraday[before-first-full-minute]` | DIRECT PASS |
| In-session after completed minutes | Last emitted minute is fully completed; one current-session pass at most; no in-progress minute or suffix-only claim | `test_v2_refresh_once_appends_full_minutes_and_refuses_changed_overlap`; Plan-06 `test_in_progress_provider_candle_after_target_is_discarded` | DIRECT PASS |
| Exact close and close+epsilon | No provisional Intraday pass; provisional `NOT_APPLICABLE`; completion remains solely V1/Plan-06 `session_complete` | `test_v2_exact_close_uses_only_v1_completed_session_admission[exact-close]`, `[close-plus-epsilon]` | DIRECT PASS |
| Holiday, weekend, and special session | Actual retained grid controls selection/target; no weekday or regular-hours inference | `test_v2_retained_schedule_boundaries_never_open_intraday[weekend]`; special-session assertions in `test_v2_refresh_once_appends_full_minutes_and_refuses_changed_overlap`; V1 `test_holiday_selection_uses_the_previous_actual_sessions` exercises the retained schedule primitive | DIRECT PASS + INHERITED |
| IST date/year/month rollover | Prior Intraday finalizes through Historical V3; closed months remain immutable; at most three months | `test_v2_cross_month_ledger_uses_completed_plan_partition_order`; Plan-06 `test_next_day_rollover_minimally_finalizes_intraday_rows_without_mutating_old_bytes`, `test_rollover_replaces_only_prior_day_intraday_rows_with_complete_history`; V1 IST rollover assertions in `test_advancing_clock_pins_retained_cutoff_without_freezing_liveness` | DIRECT PASS + INHERITED |
| 0/1/7/30 inactive days | Each request revalidates current calendar/mapping/overlap without a prior-run requirement or backdated knowledge | V1 completed-context revalidation is embedded exactly; existing acquisition primitive `test_inactivity_revalidates_the_bounded_window_without_mutating_old_evidence`; no V2 cache or prior-run state exists by inspection | INHERITED + INSPECTION |
| Shifted unchanged overlap | Shared immutable evidence and identical mutable overlap remain reusable; no blanket redownload or suffix-only statement | Identical-response `REFRESHED` and advanced-cutoff `APPENDED` assertions in `test_v2_refresh_once_appends_full_minutes_and_refuses_changed_overlap`; Plan-06 `test_identical_cutoff_rerun_is_zero_append_idempotent` | DIRECT PASS |
| Changed completed same-source overlap | `CONFLICTED`; prior bytes/catalog survive; no correction winner/publication | Conflict and retained-repeat assertions in `test_v2_refresh_once_appends_full_minutes_and_refuses_changed_overlap`; Plan-06 `test_changed_previously_persisted_bar_fails_without_replacement` | DIRECT PASS |
| Intraday-to-Historical finalization | New immutable generation only after complete Historical grid; repeat is effect-free; no overwrite/relabel | Plan-06 `test_next_day_rollover_minimally_finalizes_intraday_rows_without_mutating_old_bytes`, `test_incomplete_historical_finalization_writes_no_parquet_or_catalog_entry` | INHERITED |
| Provisional unavailable, malformed, or slow | Completed V1 context is not erased; provisional is closed unavailable/conflicted; no live claim | Direct unavailable assertions in retained schedule tests; V1 `test_current_history_local_refusals_do_not_publish_a_partial_current_snapshot`, `test_public_industry_failures_never_suppress_retained_raw_facts`; transport time bound inspection | DIRECT PASS + INHERITED |
| Stale/future calendar, mapping, partition, action, or provisional evidence | Precise scoped refusal and cutoff enforcement; no future evidence or backdating | V1 `test_public_mint_rechecks_real_mapping_and_raw_partition_authority`, `test_public_mint_rechecks_real_provisional_catalog_metadata`, `test_preexisting_action_defects_are_explicit_and_never_repaired`; `test_latest_provisional_selection_respects_data_and_knowledge_cutoffs` | INHERITED |
| Alias-only drift versus canonical/security-ID drift | Old alias object reuses only through same security ID and validated provider key; identity drift cannot select it; no migration/dual write | `test_v2_alias_only_reuses_canonical_provisional_but_identity_drift_blocks`; `test_latest_security_id_selection_reuses_an_admitted_physical_alias` | DIRECT PASS |
| Corporate action missing, conflict, or observed action | Existing V1 comparison/member refusal remains scoped; completed partitions mint no provenance after member non-admission, independently admitted provisional facts survive, and no no-action/comparability result is fabricated | `test_v2_action_non_admission_preserves_provisional_and_truthful_ledger[action-acquisition-fails-locally]`, `[action-observed]`; V1 `test_public_action_observed_withholds_only_affected_member_comparison`, `test_action_acquisition_retains_singleton_screen_and_reuses_it`, `test_preexisting_action_defects_are_explicit_and_never_repaired` | DIRECT PASS + INHERITED |
| Member-local 404 or malformed data | Local result; later independent members continue; no shared-stop inflation | V1 `test_two_members_continue_after_local_failure`, `test_closed_month_local_provider_refusals_never_retry_or_retain` | INHERITED |
| 401/403/429 or shared deadline | Shared stop prevents later openers while prior independently valid facts remain subject to final reread | V1 `test_two_members_shared_provider_stops_prevent_every_later_opener`, `test_closed_month_shared_provider_stops_preserve_opened_slot_accounting`, `test_two_members_deadline_or_cancellation_stops_before_every_later_opener` | INHERITED |
| Cancellation before opener, during/after response, before publication | Zero-call or completed-call accounting is truthful; no false synchronous cancellation claim | `test_v2_sdk_cancellation_is_public_sticky_and_normalizes_callback_defects`; V1 `test_initial_deadline_or_cancellation_is_zero_effect`, `test_interrupted_action_retry_reuses_valid_raw_without_restamping_or_admitting_stage`, `test_two_members_deadline_or_cancellation_stops_before_every_later_opener` | DIRECT PASS + INHERITED |
| Root held/replaced; catalog/storage failure before/after facts | Fatal bounded result and no mutation of replacement; no fallback root or unverifiable success | V1 `test_current_root_replacement_before_publication_stops_without_catalog_commit`, `test_public_mint_rechecks_real_provisional_catalog_metadata`, `test_public_deadline_cancellation_and_unsafe_root_stop_before_effects` | INHERITED |
| Combined local defect, shared auth, and optional failure | Frozen precedence is applied in the explicit orchestration order; later effects stop and earlier facts still require final reread; no dictionary/exception-order winner | V1 ordered local/shared tests above plus V2 orchestration inspection; no single test is represented as proving all three injected faults simultaneously | INHERITED + INSPECTION |
| Industry absent, malformed, or slow | Raw completed/provisional facts survive; Industry remains local and retained-only | V1 `test_public_industry_failures_never_suppress_retained_raw_facts`, `test_industry_reader_closes_real_malformed_receipt_and_marker_bytes`, `test_industry_reader_rejects_substitution_after_initial_real_object_read`; exact embedded V1 result | INHERITED |
| Request/response terminology | One request/response and refresh-once fields only; no poll/stream/subscription field or claim | `test_v2_request_accepts_only_the_three_one_shot_modes`; schema/Plan/README inspection | DIRECT PASS + INSPECTION |
| V1 old request/result/reader/CLI | Canonical encoding/decoder and semantic compatibility plus the default V1 selector remain; runtime identity remains revision-sensitive; no alias/migration/dual write | `test_price_context_cli_adds_v2_selector_without_changing_v1_default`, V1 `test_sdk_and_inprocess_cli_emit_identical_retained_public_facts`, decoder golden/adversary tests | DIRECT PASS + INHERITED |
| Historical Upstox, Yahoo, and BharatStock readers/calculations | Existing evidence remains readable and uninterpreted; no fallback/backdating | `test_real_retained_reliance_july_initial_and_exact_retry`, `test_price_correction_keeps_original_immutable_evidence_readable`, plus unchanged-source inspection | INHERITED + INSPECTION |
| Interruption after retained-write preparation | No partial publication; clean retry/recovery; no mutable overwrite or sticky false success | V1 `test_current_interruption_discards_all_staged_current_rows`, `test_interrupted_action_retry_reuses_valid_raw_without_restamping_or_admitting_stage`; Plan-06 interruption/finalization tests | INHERITED |
| Runtime/provenance substitution | Runtime/import/public binding fails closed before provider effects; no type/display-text substitution | `test_v2_runtime_manifest_rejects_source_substitution_before_effects`; V1 `test_public_runtime_identity_rejects_representative_copied_source_substitutions` | DIRECT PASS + INHERITED |
| Live provider/credentials unavailable | Deterministic evidence is explicitly not live integration, throughput, deployment, or provider qualification | This Plan's compatibility/evidence limit and delivery report | INSPECTION — LIVE PROOF NOT CLAIMED |
