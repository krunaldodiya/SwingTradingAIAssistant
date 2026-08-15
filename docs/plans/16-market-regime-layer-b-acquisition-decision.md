# Market Regime Layer B acquisition decision v1

Status: **IMPLEMENTED — TERMINAL DECISION `BLOCKED / CAPABILITY_EVIDENCE_MISSING`**
Contract version: `market-regime-layer-b-acquisition-decision@v1`
Extends: frozen Plans 12 and 13; neither plan is amended or reinterpreted

Linear tracking: `ARK-183`, `ARK-184`, and `ARK-185` remain historically
**Done** for the implementation published through PR #107. That publication did
not include this corrective incomplete-seal change. Commit identity,
exact-revision reviews, hosted checks, merge, and publication are external
lifecycle evidence; this self-addressed document asserts no current lifecycle
state for the correction.

Sprint 9 is one learning-and-decision slice: implement the boundary test-first,
execute the one owner-authorized candidate-artifact probe under supervision,
review and seal the evidence/authorization manifest in the build, and publish the
result the sealed evidence actually produces. This file does not predeclare that
result.

## Five-line source evaluation

1. Expected value: test whether one candidate artifact can be reached within a tightly bounded receipt path.
2. Scope fit: the candidate could inform later point-in-time Nifty 50 membership-source research for Market Regime Layer B.
3. Material risk: reachability, status `200`, media type, `%PDF-`, or one digest proves no publisher authority, membership content, historical completeness, correction semantics, identifiers, licence, or permitted use.
4. Smallest alternative: one supervised credential-free GET; no retry, parsing, persistence, catalogue write, acquisition, label, count, or outcome.
5. Decision: the probe may create capability evidence only; the sealed manifest separately determines whether later acquisition may proceed.

## Candidate outcome

The one owner-authorized probe ran from `2026-08-15T14:14:23.152972Z` to
`2026-08-15T14:14:23.606209Z` under historical worker identity
`e83bb1dabeccc3abe676294ba65210eaea2fa26f5c4fff2eda1491104d4e6430`.
It emitted sanitized receipt identity
`20911a88188cb83b2630c90c0abbbad7f74aaff8b442afc142133bfd12d8babb`
and retained no raw body. That worker could attempt another resolved address, so
its one-call/one-attempt counters are unverified and the receipt is inadmissible
as capability evidence. The current fixed worker was not used for the consumed
invocation; no rerun, provider-independent projection, or reconstruction
occurred.

No admissible capability evidence, source/PIT evidence bundle, terms/use
approval, operational-scope approval, full-acquisition authorization, or trusted
validation receipt exists. The corrected build truthfully seals those
absences in one canonical incomplete manifest. Its required
`prerequisites_assessed_at` is a source-controlled sealing instant and grants no
authority. The pure decision therefore returns canonical `BLOCKED` with first
blocker `CAPABILITY_EVIDENCE_MISSING`, the sealed manifest identity present, and
all authenticated capability, receipt, and assessment-time outputs null. The
exact manifest and report identities are recorded with the correction evidence
outside this self-addressed acquisition-scope document. No missing
identity is inferred or reconstructed.

## Question, non-claims, and frozen upstream meaning

The decision answers one question: **may a later, separately implemented and
separately execution-authorized process begin acquiring the point-in-time
evidence required by Market Regime Layer B?**

Plans 12 and 13 remain authoritative and frozen. Their authority,
point-in-time, correction, identity, exact-50, continuous-range, pre-roll,
cutoff, fail-closed, and validation rules are not changed here.

The only terminal states are `APPROVED_TO_ACQUIRE` and `BLOCKED`.
`APPROVED_TO_ACQUIRE` is approval at the acquisition-planning boundary only. It
is not proof that evidence was acquired, retained, complete, admissible,
`READY`, `OBSERVED`, valid, useful, or sufficient for Layer B. It does not
authorize the later executor by itself; that executor must obtain and validate
its own execution-start authority. `BLOCKED` is a complete decision, not partial
approval or permission to substitute a source.

Neither state computes or exposes Market Regime labels, label counts, directions,
transitions, returns, performance, predictions, recommendations, or later
outcomes.

## Authority boundaries

The boundaries are deliberately separate:

1. **Specification authority** permits documentation, tests, and implementation.
2. **Capability-probe authority** is the owner's authorization for exactly one
   supervised invocation containing one credential-free GET of the fixed URL and
   the bounds below. It grants no source, content, terms, acquisition, admission,
   or risk-acceptance authority.
3. **Acquisition-decision authority** exists only in the canonical manifest whose
   exact bytes are reviewed and sealed into the candidate build. It cannot be
   supplied by standard input, environment, configuration, a digest-only
   override, or a writable file.
4. **Later execution authority** is outside Sprint 9. A future executor must
   independently authenticate an in-force execution-start authorization and all
   operational ceilings before any acquisition side effect.

Credentials, reachability, a matching caller-authored hash, code access, and a
successful probe are never authority.

## Exact bounded candidate-artifact probe

The fixed candidate-artifact URL is:

```text
https://www.niftyindices.com/Press_Release/ind_prs21022025.pdf
```

The URL is only a candidate locator. The contract does not call the unfetched or
unparsed bytes an official membership artifact.

The supervised probe has all of these simultaneous bounds:

- method `GET`; exactly one transport call and at most one HTTP request;
- one attempt, concurrency `1`, zero retries, and zero followed redirects;
- a hard wall-clock ceiling of `30` seconds from immediately before child-process
  launch through completion of the bounded body read;
- response-body ceiling `1,048,576` bytes, with at most one extra byte read only
  to detect oversize;
- no credentials, cookies, authorization headers, tokens, request body,
  pagination, alternate URL, fallback, query parameters, or caller options;
- only fixed `Accept: application/pdf` and the existing non-secret fixed user
  agent may be sent;
- status must be exactly `200`; redirects are disabled and every 3xx is rejected
  without following or emitting `Location`;
- exactly one `Content-Type` header must normalize to `application/pdf` under the
  rule below;
- body length must be `1..1,048,576`, and its first five bytes must be `%PDF-`;
- bytes are never parsed and are transient only for the cap, prefix check, and
  SHA-256; they are never printed, logged, persisted, catalogued, or included in
  the acquisition decision; and
- no provider, filesystem, catalogue, or storage write occurs.

`%PDF-` establishes only that the candidate bytes have that prefix. It does not
attest publisher authority, evidence kind, document content, dates, membership
facts, or historical capability.

### Hard deadline enforcement

A reusable transport timeout is not the 30-second authorization control. The
release-only supervisor starts the probe worker as a child process, records a
monotonic deadline of `start + 30 seconds`, and force-terminates the entire child
process group at the deadline if the bounded read has not completed. The worker
also uses bounded connect and read waits no greater than the lesser of five
seconds and the remaining monotonic budget, disables redirects, and reads at
most `1,048,577` bytes. Post-hoc elapsed-time rejection is not sufficient.

The production `30`-second value and fixed URL are not caller-configurable. A
focused behavioral test uses a local slow-stream server and a shorter injected
internal deadline to prove that a response which keeps yielding bytes is still
terminated by the outer watchdog, creates `DEADLINE_EXCEEDED`, emits no body
hash, performs no write, and makes no second request.

### Minimal media-type normalization

The worker collects `Content-Type` occurrences case-insensitively and requires
exactly one. The single value must be at most 256 bytes and contain only ASCII
SP through `~` plus HTAB; CR, LF, non-ASCII, empty, duplicate, or over-bound
values are rejected. It takes the bytes before the first `;`, removes only
leading and trailing SP and HTAB, lowercases ASCII `A..Z`, and accepts only the
exact result `application/pdf`. Any suffix after the first `;` is retained
nowhere and has no interpreted parameter semantics. This is the complete rule;
there is no dependency on an unspecified media-type parser.

## One deterministic market-data probe receipt

All URL, HTTP status, header, and body metadata remains inside `market_data` in
this receipt. No such field crosses into the pure decision layer.

```text
CapabilityProbeFailureV1 = Literal[
  "TRANSPORT_FAILURE",
  "DEADLINE_EXCEEDED",
  "HTTP_STATUS_REJECTED",
  "CONTENT_TYPE_REJECTED",
  "BODY_EMPTY",
  "BODY_TOO_LARGE",
  "CANDIDATE_PREFIX_REJECTED"
]

CapabilityProbeReceiptV1 {
  receipt_version: Literal["market-regime-layer-b-capability-probe@v1"]
  request_url: Literal["https://www.niftyindices.com/Press_Release/ind_prs21022025.pdf"]
  method: Literal["GET"]
  outcome: Literal["OBSERVED", "FAILED"]
  failure: CapabilityProbeFailureV1 | null
  request_started_at: UtcInstant
  response_completed_at: UtcInstant
  elapsed_microseconds: Integer[0..30000000]
  http_status: Integer[100..599] | null
  normalized_media_type: Literal["application/pdf"] | null
  body_bytes_observed: Integer[0..1048577] | null
  candidate_body_sha256: Sha256 | null
  candidate_prefix_matched: bool | null
  attempt_count: Literal[1]
  network_call_count: Literal[1]
  concurrency: Literal[1]
  retry_count: Literal[0]
  redirect_count: Literal[0]
  credential_count: Literal[0]
  parser_invocation_count: Literal[0]
  filesystem_write_count: Literal[0]
  storage_write_count: Literal[0]
  receipt_identity_sha256: Sha256
}
```

The receipt has exactly one of these field combinations; no partially observed
field is copied outside the specified combination:

| Outcome/failure | Exact observation fields |
|---|---|
| `OBSERVED`, `failure=null` | status `200`; media `application/pdf`; body bytes `1..1048576`; body SHA non-null; prefix `true` |
| `TRANSPORT_FAILURE` | status, media, body bytes, body SHA, and prefix all null |
| `DEADLINE_EXCEEDED` | status, media, body bytes, body SHA, and prefix all null, even if the killed child saw partial data |
| `HTTP_STATUS_REJECTED` | observed status other than `200`; media, body bytes, body SHA, and prefix null |
| `CONTENT_TYPE_REJECTED` | status `200`; media, body bytes, body SHA, and prefix null |
| `BODY_EMPTY` | status `200`; media `application/pdf`; body bytes `0`; body SHA null; prefix `false` |
| `BODY_TOO_LARGE` | status `200`; media `application/pdf`; body bytes exactly `1048577`; body SHA and prefix null |
| `CANDIDATE_PREFIX_REJECTED` | status `200`; media `application/pdf`; body bytes `1..1048576`; body SHA null; prefix `false` |

For every row, `outcome` is `FAILED` iff `failure` is non-null. The supervisor,
not the killed worker, owns the deadline receipt. Receipt instants are trusted
release-run evidence with `request_started_at <= response_completed_at`; elapsed
microseconds comes only from the supervisor's monotonic clock and must be no more
than `30,000,000`.

`receipt_identity_sha256` is lowercase SHA-256 of the canonical receipt bytes
excluding only `receipt_identity_sha256`. Raw bodies, raw headers, redirect
locations, exception text, DNS/TLS details, addresses, paths, environment values,
and secrets are forbidden.

## Exactly-once operational boundary

Exactly-once is enforced externally: the owner supervises one release invocation
and retains its run evidence, including owner-authorization record identity,
exact candidate build identity, invocation start and completion, supervisor
outcome, child exit/termination outcome, request count, and probe receipt identity
when a receipt exists. The probe adapter is not authorization and makes no
single-use, lease, deduplication, or replay-prevention claim.

There is no installable live-probe CLI or public console entry point. The fixed
worker is invoked only by the release-only supervisor after deterministic checks
and authorization inspection. A failure consumes the authorized invocation. No
second invocation is permitted without a new owner authorization record and a
new retained supervised-run record. The contract does not pretend source code
can prevent an authorized operator from launching it again.

## Provider-independent capability evidence

After the supervised run, `market_data` may derive one retained projection:

```text
CapabilityEvidenceRecordV1 {
  record_version: Literal["market-regime-layer-b-capability-evidence@v1"]
  state: Literal["OBSERVED", "NOT_OBSERVED"]
  probe_receipt_identity_sha256: Sha256
  assessed_at: UtcInstant
  evidence_identity_sha256: Sha256
}
```

`OBSERVED` is allowed only for an `OBSERVED` probe receipt; every failed receipt
maps to `NOT_OBSERVED`. The record contains no provider, URL, method, status,
header, body length, body digest, PDF, authority, or evidence-kind field.
`evidence_identity_sha256` is lowercase SHA-256 of its canonical bytes excluding
only that field.

The pure decision receives only the record's `state` and
`evidence_identity_sha256`. It does not import `market_data`, reopen the receipt,
or interpret transport details. Authentication comes from equality with the
exact capability state and identity inside the reviewed, code-sealed manifest;
a caller-supplied digest by itself proves nothing.

## Single reviewed-and-code-sealed manifest

Caller-authored per-gate assessments and caller-supplied full authorization are
prohibited. The only evidence/authorization boundary is this one closed
manifest:

```text
AcquisitionAuthorizationManifestV1 {
  manifest_version: Literal["market-regime-layer-b-acquisition-manifest@v1"]
  market_regime_contract_identity_sha256: Sha256
  layer_b_protocol_identity_sha256: Sha256
  acquisition_scope_identity_sha256: Sha256
  capability_evidence_state: Literal["OBSERVED", "NOT_OBSERVED"] | null
  capability_evidence_identity_sha256: Sha256 | null
  capability_assessed_at: UtcInstant | null
  source_and_pit_evidence_bundle_identity_sha256: Sha256 | null
  terms_and_use_approval_identity_sha256: Sha256 | null
  operational_scope_approval_identity_sha256: Sha256 | null
  prerequisites_assessed_at: UtcInstant
  acquisition_authorization: AcquisitionAuthorizationBindingV1 | null
  manifest_scope_identity_sha256: Sha256
  authorization_validation_receipt_identity_sha256: Sha256 | null
  manifest_identity_sha256: Sha256
}

AcquisitionAuthorizationBindingV1 {
  authority_role: Literal["FULL_ACQUISITION_AUTHORITY"]
  authority_identity_sha256: Sha256
  authorization_record_identity_sha256: Sha256
  issued_at: UtcInstant
  not_before: UtcInstant
  expires_at: UtcInstant
}
```
`capability_evidence_state`, `capability_evidence_identity_sha256`, and
`capability_assessed_at` are one atomic optional group. All three null means no
capability evidence exists. All three non-null retains the authenticated
capability behavior below. Any partial-null group is an invalid sealed manifest.
`prerequisites_assessed_at` remains a required UTC instant even in an incomplete
manifest; it records when the seal's prerequisite absences were assessed and
grants no evidence or authority.


The three prerequisite identities are content addresses of independently
retained reviewed records:

- `source_and_pit_evidence_bundle_identity_sha256` covers the complete proposed
  source set and Plan 12/13 authority, point-in-time, continuous history,
  schedule, close, corporate comparability, effectivity, publication clock,
  correction/revision, negative-completeness, and identity-continuity evidence;
- `terms_and_use_approval_identity_sha256` covers licence, permitted use, and
  redistribution/redaction disposition; and
- `operational_scope_approval_identity_sha256` covers the exact Plan 13 range and
  pre-roll, source identities, credentials, cost ceiling, storage,
  retention/deletion, concurrency, byte/time bounds, and stop/rollback plan.

A null prerequisite identity means that prerequisite is not approved. A wholly
null capability group means capability evidence does not exist. No individual
gate objects or caller-selected evidence identities enter the reducer.

Every retained-record `*_identity_sha256` above is lowercase SHA-256 of the
named record's exact canonical JSON-LF bytes excluding that record's identity
field. The two manifest identities instead use the explicit projections and
finite sealing sequence below. An authority identity is the content address of
the retained authority/delegation record, and
`authorization_record_identity_sha256` is the content address of the owner's
exact scope-bound grant. Those identities provide traceability; authority comes
from the reviewed seal and retained records, not from possession of a digest.
For one manifest, sealing is ordered and finite:

1. Fix the scope fields from `manifest_version` through
   `acquisition_authorization`. Set the capability group wholly null when no
   capability evidence exists, or wholly non-null when admissible capability
   evidence exists; never seal a partial group. `prerequisites_assessed_at`
   remains required. The manifest scope projection is the canonical JSON-LF
   object containing exactly those twelve fields under their original names. It
   excludes `manifest_scope_identity_sha256`,
   `authorization_validation_receipt_identity_sha256`, and
   `manifest_identity_sha256`.
2. Set `manifest_scope_identity_sha256` to SHA-256 of those exact projection
   bytes.
3. Construct any trusted validation receipt with that scope identity. Its
   identity projection is the canonical receipt object excluding only
   `receipt_identity_sha256`; hash those bytes, set `receipt_identity_sha256`,
   and then set the manifest's
   `authorization_validation_receipt_identity_sha256` to that completed receipt
   identity. For an intentionally incomplete seal with no receipt, set the
   manifest field to null and skip receipt construction.
4. The final manifest identity projection is the canonical full manifest object
   excluding only `manifest_identity_sha256`; it therefore includes the scope
   identity and the completed receipt identity or null. Hash those bytes and set
   `manifest_identity_sha256`.
5. Emit and pin the resulting full canonical manifest bytes and final manifest
   identity. No earlier digest is recomputed from a later identity.

### Trusted pin source and current fail-closed state

The sole runtime source is a literal immutable
`SEALED_ACQUISITION_MANIFEST_CANONICAL_JSON_LF` in
`historical_evaluation/acquisition_manifest.py`. The module admits no
environment, file, network, standard-input, plugin, or configuration replacement.
When non-null, the application parses the literal bytes canonically,
reconstructs both manifest projection identities and all inline bindings, and
verifies that the derived final manifest identity equals the companion literal
`SEALED_ACQUISITION_MANIFEST_IDENTITY_SHA256`.

The corrected build replaces the historical `None` pin with an incomplete
canonical seal. The three capability fields and every later evidence, approval,
authorization, and validation-receipt identity are null; only the required
prerequisite assessment instant records when those absences were assessed. The
valid seal therefore deterministically returns `BLOCKED /
CAPABILITY_EVIDENCE_MISSING` with its manifest identity present. A monkeypatched
or future literal `None` still returns `BLOCKED / SEALED_MANIFEST_MISSING`.
Changing only input bytes cannot create approval. A future
`APPROVED_TO_ACQUIRE` remains impossible unless a reviewed build change seals
all required evidence and authority. Sealing is not itself approval.

The same module pins
`TRUSTED_AUTHORIZATION_CLOCK_SOURCE_IDENTITY_SHA256`. It is a content address of
the retained trusted-clock source/binding record, not a caller name.

## Trusted validation-time receipt and temporal equations

The offline input may carry this receipt. The final manifest pins its exact
identity, the receipt binds the earlier manifest scope identity, and the build
pins its clock source:

```text
AuthorizationValidationReceiptV1 {
  receipt_version: Literal["market-regime-layer-b-authorization-validation@v1"]
  manifest_scope_identity_sha256: Sha256
  trusted_clock_source_identity_sha256: Sha256
  validation_started_at: UtcInstant
  authorization_validated_at: UtcInstant
  validation_completed_at: UtcInstant
  receipt_identity_sha256: Sha256
}
```

`receipt_identity_sha256` is lowercase SHA-256 of the receipt identity
projection defined in sealing step 3. Authentication requires all of the
following:

- its canonical bytes and receipt identity reconstruct exactly;
- the receipt identity equals the non-null identity sealed in the final
  manifest;
- its manifest scope identity equals the reconstructed sealed manifest scope
  identity; and
- its clock-source identity equals the build's trusted clock-source pin.

Caller time and replay wall time are never used for authorization. When `R`
exists for an owner-authorization outcome, the report's `assessed_at` is exactly
`validation_completed_at`; earlier blocker rows use null. For an approval, the
complete inclusive/exclusive equations are:

```text
issued_at <= not_before
not_before <= capability_assessed_at <= authorization_validated_at
not_before <= prerequisites_assessed_at <= authorization_validated_at
not_before <= validation_started_at
validation_started_at <= authorization_validated_at <= validation_completed_at
validation_completed_at < expires_at
assessed_at = validation_completed_at
```

Thus capability and prerequisite assessment times and the authorization
validation time cannot be future-dated relative to the trusted decision
assessment time, and all are inside `[not_before, expires_at)`. `expires_at` is
exclusive. Missing, inverted, future-dated, out-of-binding, identity-mismatched,
or untrusted validation evidence cannot approve. A later acquisition executor
must perform a new execution-start validation; this retained receipt approves no
later side effect.

## Pure decision input, report, and smallest blocker set

```text
CapabilityEvidenceInputV1 {
  state: Literal["OBSERVED", "NOT_OBSERVED"]
  evidence_identity_sha256: Sha256
}

AcquisitionDecisionInputV1 {
  contract_version: Literal["market-regime-layer-b-acquisition-decision@v1"]
  capability_evidence: CapabilityEvidenceInputV1 | null
  authorization_validation_receipt: AuthorizationValidationReceiptV1 | null
}

AcquisitionDecisionStateV1 = Literal["APPROVED_TO_ACQUIRE", "BLOCKED"]

AcquisitionBlockerV1 = Literal[
  "SEALED_MANIFEST_MISSING",
  "SEALED_MANIFEST_INVALID",
  "CAPABILITY_EVIDENCE_MISSING",
  "SOURCE_AND_PIT_EVIDENCE_UNPROVEN",
  "TERMS_AND_USE_UNAPPROVED",
  "OPERATIONAL_SCOPE_UNAPPROVED",
  "OWNER_AUTHORIZATION_NOT_IN_FORCE"
]

AcquisitionDecisionReportV1 {
  contract_version: Literal["market-regime-layer-b-acquisition-decision@v1"]
  decision_state: AcquisitionDecisionStateV1
  primary_blocker: AcquisitionBlockerV1 | null
  sealed_manifest_identity_sha256: Sha256 | null
  authenticated_capability_evidence_identity_sha256: Sha256 | null
  authorization_validation_receipt_identity_sha256: Sha256 | null
  assessed_at: UtcInstant | null
  report_identity_sha256: Sha256
}
```

The reducer stops at the first applicable blocker in declaration order and emits
no additional-blocker list. The five acquisition prerequisites are therefore
visible at the smallest useful grouping: candidate capability, source/PIT
evidence, terms/use, operational scope, and owner authorization. The two earlier
blockers protect the seal itself rather than pretending malformed authority is
an acquisition prerequisite.

After structural admission of the decision input, the table below exhausts every
report-producing outcome. `M` means the strictly authenticated final sealed
manifest, including enforcement that its capability group is either wholly null
or wholly non-null. `C` exists only when that group is wholly non-null, the
non-null input capability state and identity exactly equal `M`'s values, and that
common state is `OBSERVED`; when it exists, its identity source is
`M.capability_evidence_identity_sha256`. `R` exists only when a structurally
admitted non-null input receipt passes all four authentication checks above;
receipt authentication does not include the authorization temporal equations.
Its two report sources are `R.receipt_identity_sha256` and
`R.validation_completed_at`.

| First applicable condition | `decision_state` | `primary_blocker` | `sealed_manifest_identity_sha256` | `authenticated_capability_evidence_identity_sha256` | `authorization_validation_receipt_identity_sha256` | `assessed_at` |
|---|---|---|---|---|---|---|
| Manifest literal is `None` | `BLOCKED` | `SEALED_MANIFEST_MISSING` | null | null | null | null |
| Manifest literal is non-null but strict canonical parsing, either manifest projection identity, an inline binding, atomic capability-group nullability, or the companion final-identity pin fails | `BLOCKED` | `SEALED_MANIFEST_INVALID` | null | null | null | null |
| `M` exists but its capability group is wholly null or `C` otherwise does not exist | `BLOCKED` | `CAPABILITY_EVIDENCE_MISSING` | `M.manifest_identity_sha256` | null | null | null |
| `C` exists and `M.source_and_pit_evidence_bundle_identity_sha256` is null | `BLOCKED` | `SOURCE_AND_PIT_EVIDENCE_UNPROVEN` | `M.manifest_identity_sha256` | `M.capability_evidence_identity_sha256` | null | null |
| Earlier conditions are false and `M.terms_and_use_approval_identity_sha256` is null | `BLOCKED` | `TERMS_AND_USE_UNAPPROVED` | `M.manifest_identity_sha256` | `M.capability_evidence_identity_sha256` | null | null |
| Earlier conditions are false and `M.operational_scope_approval_identity_sha256` is null | `BLOCKED` | `OPERATIONAL_SCOPE_UNAPPROVED` | `M.manifest_identity_sha256` | `M.capability_evidence_identity_sha256` | null | null |
| Earlier conditions are false, but `M.acquisition_authorization` is null, `R` does not exist, or any authorization temporal equation fails | `BLOCKED` | `OWNER_AUTHORIZATION_NOT_IN_FORCE` | `M.manifest_identity_sha256` | `M.capability_evidence_identity_sha256` | `R.receipt_identity_sha256` if `R` exists; otherwise null | `R.validation_completed_at` if `R` exists; otherwise null |
| No blocker condition applies | `APPROVED_TO_ACQUIRE` | null | `M.manifest_identity_sha256` | `M.capability_evidence_identity_sha256` | `R.receipt_identity_sha256` | `R.validation_completed_at` |

The reducer does not authenticate a receipt until all six earlier blocker
conditions are false. Consequently every earlier blocked row has null receipt
identity and `assessed_at` even if receipt bytes were supplied. At the owner row,
an authenticated receipt retains its identity and trusted completion time even
when a missing authorization or failed temporal equation blocks approval; an
unauthenticated receipt contributes neither. Caller-selected identities and
times never enter a report.

`report_identity_sha256` is lowercase SHA-256 of the report's exact canonical
JSON-LF bytes excluding only `report_identity_sha256`. The fixed contract
version, declaration-order outcome selection, and the sources/nulls in the table
therefore determine one byte sequence and report identity for every outcome.
Structural admission failures produce no report.

The pure reducer performs no network, provider, filesystem, environment, clock,
random, storage, acquisition, Market Regime, or Sector Analysis action. It imports
neither `market_data` nor Market Regime/Sector reducers. No report field counts
or names labels.

## Canonicalization, bounds, and offline CLI

This contract reuses Plan 12's `Sha256`, `UtcInstant`, canonical JSON-LF, and
strict parser without changing them. Closed objects reject unknown/missing
fields, duplicate keys, wrong types, unknown enums, floats, invalid Unicode,
noncanonical ordering, invalid nullability, and identity mismatch. Canonical JSON
is UTF-8 without BOM, NFC strings, lexicographically sorted object keys, compact
separators, minimal escaping, and exactly one trailing LF included in each
digest. External bytes are accepted byte-for-byte or rejected; they are never
silently normalized.

Exact bounds are:

- sealed manifest and decision input: at most 16 KiB each;
- validation receipt: at most 4 KiB;
- decision report: at most 8 KiB;
- JSON nesting depth at most 8; and
- every identifier uses its stated lexical type.

The only installable surface is the offline
`market-regime-acquisition-decision decide` CLI. It accepts no flags and reads at
most `16,385` bytes from standard input: one bounded read of `16 KiB + 1`. If the
extra byte is present, it rejects immediately without reading or buffering more,
parsing partial content, or echoing input. It never accepts a manifest,
authorization grant, URL, path, time, source, override, credential, timeout, or
byte limit.

Exit behavior is exact:

| Exit | Output |
|---:|---|
| `0` | one canonical `APPROVED_TO_ACQUIRE` report on stdout; stderr empty |
| `1` | one canonical `BLOCKED` report on stdout; stderr empty |
| `2` | stdout empty; exactly `request_invalid` or `internal_error` plus LF on stderr |

Unknown subcommands, flags, extra input, oversize input, and structural admission
fail with exit `2` and no usage, exception, path, environment, or input echo.
There is no `probe` subcommand.

## Test-first one-week implementation and execution order

This is one plausible one-week slice, not a platform or reusable acquisition
framework:

1. Freeze this contract and the three Sprint 9 summaries. Add focused RED tests
   for manifest absence/authentication, the ordered scope/receipt/final identity
   projections, all eight decision-output rows, every temporal boundary, CLI
   `16 KiB + 1`, and zero side effects/dependencies.
2. Implement the smallest pure reducer and offline CLI under
   `historical_evaluation`, with the manifest pin initially `None`. Make the
   focused tests green.
3. Add RED tests for the one probe receipt table, exact media normalization,
   byte limit/limit-plus-one, no redirect/retry/credentials/writes, and a local
   slow stream that is killed by the outer monotonic watchdog. Implement the
   fixed `market_data` worker and release-only supervisor; expose no live-probe
   console entry point.
4. Run the applicable deterministic repository gates. Then inspect the one-call
   owner authorization and execute exactly one supervised release invocation.
   Retain only the sanitized receipt, provider-independent capability record,
   and supervised-run evidence; never retry under the same authority.
5. Review the retained prerequisite, capability, terms/use, operational-scope,
   owner-authorization, and trusted-time records. Seal the actual canonical
   manifest bytes in a reviewed candidate-build change, whether complete or
   incomplete; do not invent missing evidence.
6. Re-run exact-revision checks and independent quality/security review, run the
   offline reducer once on authenticated inputs, and publish its actual terminal
   report and limitations. Any repair invalidates prior exact-revision evidence.

The slice ends only after implementation, behavioral proof, the one supervised
probe disposition, build-sealed manifest, actual decision, review, and
publication. A documentation-only phase or unexecuted scaffold is not Sprint 9
completion.

### Discriminatory acceptance evidence

- A `None` manifest pin yields byte-stable `BLOCKED /
  SEALED_MANIFEST_MISSING`; standard input cannot replace it.
- A canonical incomplete manifest with all three capability fields null seals
  successfully and yields `BLOCKED / CAPABILITY_EVIDENCE_MISSING` with its
  manifest identity present and authenticated capability/receipt/time outputs
  null.
- Any partial-null capability group, manifest mutation, pin mismatch, or
  malformed sealed bytes yields `SEALED_MANIFEST_INVALID`.
- Changing input capability state/identity or receipt bytes cannot produce
  approval unless they match identities already sealed into the reviewed build.
- Golden canonical reports cover `APPROVED_TO_ACQUIRE` and all seven blockers
  with exactly the identity/time sources and nulls in the decision-output table,
  including authenticated-but-out-of-force versus unauthenticated receipts.
- Scope projection mutation changes the scope identity; the completed receipt
  binds that scope identity; and only then does its identity enter the final
  manifest projection, so no digest requires a later digest as input.
- Each null prerequisite selects the first of the five prerequisite blockers in
  declaration order; later missing prerequisites do not create a blocker list.
- Before/equal/after tests cover every temporal inequality, including future
  assessment/validation and exclusive expiry.
- A successful candidate probe proves only `CapabilityEvidenceRecordV1.state =
  OBSERVED`; it does not prove source authority, content, completeness, licence,
  acquisition, readiness, or Layer B admission.
- Status, duplicate/malformed content type, empty body, 1,048,576 bytes,
  1,048,577 bytes, wrong prefix, transport failure, redirect, and slow-stream
  deadline each select the exact receipt row and never persist bytes.
- The slow-stream test observes child-process termination by the outer monotonic
  watchdog before the configured test deadline can be exceeded by continuing
  body activity.
- A process/integration test replaces every Market Regime and Sector reducer
  entry point and every network/filesystem/storage/acquisition side-effect port
  with a fail-on-call sentinel; decision construction and reduction must leave
  every sentinel untouched. A dependency test rejects imports from those
  reducers. This, rather than a public label counter, proves no-label behavior.
- The offline CLI proves max, max-plus-one, fixed redaction, and that it neither
  consumes nor buffers beyond `16,385` bytes.
- Retained release evidence proves one supervised invocation occurred. The
  adapter and tests make no replay-prevention claim, and a second invocation is
  forbidden without new owner authority.

## Lifecycle and handoff

| Area | Sprint 9 disposition |
|---|---|
| Plans 12/13 and Market Regime semantics | Frozen and unchanged |
| Candidate probe bytes | Transient; never persisted or admitted |
| Provider transport metadata | Retained only in the `market_data` probe receipt |
| Evidence/authorization authority | One canonical incomplete build-sealed manifest; lifecycle evidence is external to this self-addressed document |
| Legal, terms, cost, credentials, storage, retention | All approval identities remain null; the first missing capability group blocks |
| Data migration or production source replacement | None |
| Labels, outcomes, strategy, recommendations | Forbidden and untouched |
| Later acquisition | Separate implementation and fresh execution-start authority required |

The current blocked handoff contains the immutable report, the valid sealed
manifest identity, the first missing prerequisite group, and the retained
review/run evidence. Its prerequisite assessment instant records sealing
provenance only. Later work must create new evidence and a new reviewed
manifest/build; it must not overwrite history or rerun the Sprint 9 probe without
new owner authority.

An approved handoff contains the immutable report and the exact sealed manifest.
It still performs no acquisition. A later executor must independently revalidate
execution-start authority and remain inside the sealed scope and ceilings. Only
after acquisition and Plan 13 sealing may a separately accepted Layer B run be
considered.

## Completion and residual risk

The Sprint 9 implementation, deterministic acceptance coverage, one supervised
probe disposition, and real offline decision are present. The corrective
candidate now seals a truthful incomplete manifest rather than treating absence
of evidence as absence of a seal. Because the capability group is wholly null,
the recorded result is `BLOCKED / CAPABILITY_EVIDENCE_MISSING`, with a sealed
manifest identity and no authenticated capability, receipt, time, acquisition,
readiness, admission, label, or later-execution authority. The exact document,
manifest and report identities are recorded in the build pin and Sprint 9
evidence, not embedded here where the Plan 16 byte identity would become
self-referential.

PR #107 is immutable historical implementation publication evidence, and Linear
ARK-183/184/185 remain historically Done. Commit identity, exact-revision
reviews, hosted checks, merge, and publication for the correction are external
lifecycle evidence; this self-addressed document asserts no current lifecycle
state. No approval is inferred from the successful HTTP envelope,
implementation, sealing instant, or this specification.

Residual risk remains that exactly-once depends on human/release supervision and
retained evidence rather than technical replay prevention; the candidate prefix
and HTTP envelope do not establish document semantics; and a trusted retained
validation receipt can justify only its historical assessment instant, not a
later executor's authority. These limits are explicit stop boundaries, not
approval assumptions.
