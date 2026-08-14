# Sector Participation v1 Fact Contract

Status: **OWNER APPROVED — FROZEN SPECIFICATION ONLY**
Owner decision: **approved on 2026-08-13 IST**
Contract version: `nifty50-sector-participation@v1`
Architecture placement: minimal V1 fact contract inside locked Module 2,
**Sector Analysis**
Depends on: `nifty50-market-regime@v1`, Plan 05, Plan 11, and Plan 12

This document freezes a future deterministic Sector Analysis fact boundary. It
adds no module and does not rename Sector Analysis: Sector Participation is the
smallest V1 fact contract for the architecture-locked second module, not an
added or renamed eleventh module. It approves documentation only. No
implementation, source, acquisition, provider, credential, retained-data run,
runtime surface, or observed Sector Participation report exists.

## Proposed-boundary evaluation

- Expected value: describe the exact observed Market Regime directions by authoritative point-in-time sector without another price calculation.
- Scope fit: minimal V1 fact for locked Module 2 Sector Analysis, limited to the same Nifty 50 end-of-day cohort.
- Material risk: current-map backfill, taxonomy substitution, incomplete lineage, and singleton counts can manufacture or disclose a fact.
- Smallest alternative: count all 50 private upstream directions by exact official Sector-tier labels and fail the whole report closed on any evidence gap.
- Decision: **accepted for specification only**; implementation, sources, acquisition, private-delivery runtime, and observed research remain separately unauthorized.

## Purpose, boundary, and non-claims

Sector Participation answers only: _for the exact 50 decision-session members
in one observed `nifty50-market-regime@v1` fact, how many `ADVANCE`, `DECLINE`,
and `UNCHANGED` member directions fall in each exact point-in-time official
Sector label?_ It is an end-of-day descriptive composition fact. It does not
reclassify Market Regime and is not a broad Sector Analysis platform.

V1 explicitly rejects claims of returns, ranks, scores, leadership, rotation,
relative strength, signals, recommendations, usefulness, and profitability. It
also computes no percentage, strength, leader, laggard, performance,
effectiveness, forecast, trade permission, confidence, trend, or AI narrative.
It adds no price, index candle, weight, volume, indicator, benchmark,
threshold search, or second data family. Canonical row order is serialization,
not rank. `NO_TRADE` remains owned by later decision logic.

Only point-in-time Nifty 50 cash equities and the inherited daily official
session boundary are in scope. Intraday, derivatives, other universes, broker
execution, public/anonymous aggregates, adjusted returns, and autonomous
trading remain excluded.

## Frozen upstream boundary and discriminated envelope

Let `S[0] < ... < S[20] < S[21]` retain Plan 12's exact meaning:

```text
comparison_session = S[0]
decision_session = S[20]
decision_market_close = S[20].close_at
evidence_cutoff = S[21].open_at
knowledge_cutoff = evidence_cutoff
required_member_count = 50
```

Sector Participation never reads closes, derives a direction, resolves or
corrects a schedule, interprets a corporate action, substitutes membership, or
moves an endpoint. Those responsibilities remain upstream. Downstream verifies
only the identity-bound upstream report and handoff; it never recomputes their
schedule corrections, corporate-action completeness, member directions, or
Market Regime label.

The upstream input is a closed discriminated union. The `envelope_state` value
pins the only legal fields and nullability:

```text
MarketRegimeObservedEnvelopeV1 {
  envelope_state: Literal["OBSERVED"]
  report_canonical_bytes_hex: HexBytes[1..65536]
  report_identity_sha256: Sha256
  handoff_canonical_bytes_hex: HexBytes[1..65536]
  handoff_identity_sha256: Sha256
}

MarketRegimeUnobservedEnvelopeV1 {
  envelope_state: Literal["UNOBSERVED"]
  observation: Literal["ABSENT", "INSUFFICIENT_EVIDENCE"]
  report_canonical_bytes_hex: HexBytes[1..65536] | null
  report_identity_sha256: Sha256 | null
}

MarketRegimeEnvelopeV1 =
  MarketRegimeObservedEnvelopeV1 | MarketRegimeUnobservedEnvelopeV1
```

`ABSENT` requires both report fields null. Its downstream report has
`comparison_session = decision_market_close = evidence_cutoff = null` and
`MARKET_REGIME_NOT_OBSERVED`; it carries no handoff. `INSUFFICIENT_EVIDENCE`
requires canonical Plan 12 report bytes and their recomputed identity, copies
that report's exact nullable endpoints, and yields
`MARKET_REGIME_NOT_OBSERVED`; it carries no handoff. The copied endpoint shapes
must be exactly one of Plan 12's three stages:

| Upstream endpoint stage | Downstream nullable endpoints |
|---|---|
| `SCHEDULE_UNVERIFIED` | comparison, close, and cutoff are null |
| `ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED` | comparison and close non-null; cutoff null |
| `CUTOFF_VERIFIED` | comparison, close, and cutoff non-null |

Only `OBSERVED` may contain a handoff. Its Plan 12 report must be canonical,
identity-valid, version-correct, `OBSERVED`, non-null at all three endpoints,
and total exactly 50. A foreign version, digest mismatch, inconsistent
discriminator, forbidden handoff in an unobserved branch, or absent handoff in
an observed branch is structural admission failure and produces no
`SectorParticipationReportV1`. A well-formed upstream absent or insufficient
branch is a domain insufficiency result, not a parse failure.

## Private observed-only Market Regime handoff

The reviewed future Market Regime application is the only producer of this
private handoff after it has emitted the corresponding observed report:

```text
MemberDirectionV1 {
  isin: Isin
  direction: Literal["ADVANCE", "DECLINE", "UNCHANGED"]
}

MarketRegimeSectorHandoffV1 {
  contract_version: Literal["nifty50-market-regime-sector-handoff@v1"]
  market_regime_contract_version: Literal["nifty50-market-regime@v1"]
  market_regime_report_identity_sha256: Sha256
  market_regime_input_identity_sha256: Sha256
  source_policy_identity_sha256: Sha256
  validation_policy_identity_sha256: Sha256
  policy_identity_sha256: Sha256
  code_identity_sha256: Sha256
  comparison_session: LocalDate
  decision_session: LocalDate
  next_official_session: LocalDate
  decision_market_close: UtcInstant
  evidence_cutoff: UtcInstant
  members: tuple[MemberDirectionV1, 50]
  handoff_identity_sha256: Sha256
}
```

The handoff rows are strictly ISIN-sorted and unique. Its endpoints and all
Market Regime identities equal the observed report; its direction totals equal
the report's `advances`, `declines`, and `unchanged`. Its identity is recomputed
from every field except only `handoff_identity_sha256`. Sector Participation
validates these equations but does not redo the upstream close comparisons.

This immutable, in-process, owner-private value is not a public report, stored
export, provider payload, request argument, CLI flag, API body, or MCP argument.
Raw closes never enter it. ISINs and member directions never enter a Sector
Participation report, log, exception, telemetry event, or free-form diagnostic.
The handoff cannot exist before the Market Regime implementation and its
observed same-input reduction; planning must never claim a circular same-input
handoff as an already available prerequisite.

## Point-in-time taxonomy and source policy

NSE Indices Limited (`NSE_INDICES`) is the sole V1 taxonomy authority. V1 uses
the exact **Sector** tier in the official four-level structure
`Macro Economic Sector / Sector / Industry / Basic Industry`. Industry, Basic
Industry, Macro Economic Sector, provider categories, symbols, company names,
row positions, aliases, and local rollups are not substitutes. ISIN is the only
join key.

A selected assignment is eligible only when immutable candidate bytes prove all
of the following:

1. the sealed source-policy binding derives `NSE_INDICES`, exact source identity,
   schema version, classification release, selector grammar, and identity
   projections;
2. an official taxonomy-release object proves the exact Sector tier;
3. exactly one assignment for each of the 50 upstream ISINs is effective on
   `decision_session`;
4. required publication, response completion, retrieval, and immutable retention
   clocks are trusted and no later than `knowledge_cutoff`;
5. the selected revision is checked through exactly `knowledge_cutoff`, and the
   complete revision graph and acquisition manifest prove no omitted current,
   superseded, or conflicting object known by that cutoff; and
6. a sealed licence proof permits immutable retention and owner-private
   aggregate use for the selected source/release at the decision session.

A current download cannot establish historical effective time, publication, or
revision truth. No current-map backfill, inferred label, nearest-date fill,
latest-wins rule, cross-release union, symbol join, provider fallback, or
post-cutoff repair is admitted. Original and revised bytes remain separately
immutable.

## Lexical types and structural request

Every schema in this contract is closed. Unknown or missing fields, duplicate
JSON keys, wrong types, invalid union discriminators, invalid nullability,
over-depth data, oversize bytes, and enum values outside a declared literal are
structural admission failures and produce no report. Exact lexical contracts
are:

- `Sha256`: `^[0-9a-f]{64}$`.
- `LocalDate`: a real zero-padded Gregorian `YYYY-MM-DD`.
- `UtcInstant`: `YYYY-MM-DDTHH:MM:SS.ffffffZ` with exactly six fractional digits.
- `Isin`: Plan 12's 12-character ISO 6166 lexical and check-digit contract.
- `BoundedText`: NFC UTF-8, 1 through 256 bytes, with no control character or surrounding whitespace.
- `CandidateText`: exact JSON Unicode-scalar text from 0 through 512 UTF-8 bytes; it deliberately permits empty, non-NFC, padded, control-character, and otherwise semantically corrupt claims so pure validation can return insufficiency rather than make them unrepresentable.
- `HexBytes[a..b]`: lowercase even-length hex encoding of `a..b` decoded bytes.
- `tuple[T, a..b]`: an immutable tuple within the inclusive bound.

The bounded request is minimal and contains no supplied cutoff, comparison
session, cohort, taxonomy label, counts, source, provider, endpoint, or
conclusion:

```text
SectorParticipationRequestV1 {
  contract_version: Literal["nifty50-sector-participation@v1"]
  segment: Literal["NSE_EQ"]
  decision_session: LocalDate
  delivery_class: Literal["OWNER_PRIVATE"]
  request_identity_sha256: Sha256
}
```

The request identity is SHA-256 of canonical request content excluding only its
own field. A malformed or noncanonical request is `REQUEST_INVALID` at
application admission and produces no report; `REQUEST_INVALID` is not a domain
reason.

## Evidence candidate, attempt, and immutable-byte trace

Structural parsing is deliberately wider than verified facts. The following
closed candidate layer preserves well-formed missing, late, zero-row, 49-row,
51-row, duplicate, ambiguous, corrupt, wrong-tier, wrong-clock, licence, and
revision defects as domain insufficiency. More than 51 assignment candidates,
more than 64 lineage nodes, or malformed external bytes are structural failures
and produce no report.

```text
SectorEvidenceRequestIdentityV1 {
  authority: Literal["NSE_INDICES"]
  scope: Literal["DECISION_COHORT_SECTOR_ASSIGNMENTS"]
  decision_session: LocalDate
  member_isins: tuple[Isin, 50]
}

EvidenceClockCandidateV1 {
  publication_requirement_text: CandidateText
  published_at_text: CandidateText | null
  response_completed_at_text: CandidateText | null
  retrieved_at_text: CandidateText | null
  retained_at_text: CandidateText | null
  clock_authority_text: CandidateText
}

SectorProvenanceCandidateV1 {
  source_object_identity_sha256: Sha256
  source_row_selector: CandidateText
  authority_text: CandidateText
  source_identity_text: CandidateText
  schema_version_text: CandidateText
  classification_release_identity_sha256_text: CandidateText
  object_identity_sha256_text: CandidateText | null
  revision_identity_sha256_text: CandidateText | null
  supersedes_identity_sha256_text: CandidateText | null
  clock: EvidenceClockCandidateV1
}

TaxonomyReleaseCandidateV1 {
  tier_path_text: CandidateText
  sector_tier_name_text: CandidateText
  release_effective_from_text: CandidateText
  release_effective_through_text: CandidateText | null
  provenance: SectorProvenanceCandidateV1
}

SectorAssignmentCandidateRowV1 {
  isin_text: CandidateText
  sector_label_text: CandidateText
  taxonomy_tier_text: CandidateText
  effective_from_text: CandidateText
  effective_through_text: CandidateText | null
  provenance: SectorProvenanceCandidateV1
}

RevisionNodeCandidateV1 {
  revision_identity_sha256_text: CandidateText
  supersedes_identity_sha256_text: CandidateText | null
  object_identity_sha256_text: CandidateText
  status_text: CandidateText
  provenance: SectorProvenanceCandidateV1
}

RevisionLineageCandidateV1 {
  selected_revision_identity_sha256_text: CandidateText
  checked_through_text: CandidateText
  lineage_status_text: CandidateText
  nodes: tuple[RevisionNodeCandidateV1, 0..64]
  provenance: SectorProvenanceCandidateV1
}

CoverageManifestEntryCandidateV1 {
  isin_text: CandidateText
  assignment_source_object_identity_sha256: Sha256
  assignment_source_row_selector: CandidateText
}

CoverageManifestCandidateV1 {
  decision_session_text: CandidateText
  required_member_count_text: CandidateText
  entries: tuple[CoverageManifestEntryCandidateV1, 0..51]
  completeness_text: CandidateText
  provenance: SectorProvenanceCandidateV1
}

LicenceProofCandidateV1 {
  licence_identity_sha256_text: CandidateText
  source_identity_text: CandidateText
  classification_release_identity_sha256_text: CandidateText
  retention_permission_text: CandidateText
  owner_private_aggregate_permission_text: CandidateText
  redistribution_permission_text: CandidateText
  effective_from_text: CandidateText
  effective_through_text: CandidateText | null
  review_status_text: CandidateText
  provenance: SectorProvenanceCandidateV1
}

SectorClassificationCandidatePayloadV1 {
  taxonomy_release: TaxonomyReleaseCandidateV1 | null
  received_rows: tuple[SectorAssignmentCandidateRowV1, 0..51]
  revision_lineage: RevisionLineageCandidateV1 | null
  coverage_manifest: CoverageManifestCandidateV1 | null
  licence_proof: LicenceProofCandidateV1 | null
}

SectorEvidenceAttemptFailureV1 = Literal[
  "NOT_RETURNED", "AFTER_EVIDENCE_CUTOFF", "INVALID_SOURCE_ROW",
  "IDENTITY_MISMATCH", "UNAUTHORIZED_AUTHORITY", "PUBLICATION_UNPROVEN",
  "CLOCK_UNTRUSTED", "LICENCE_UNRESOLVED", "REVISION_UNPROVEN"
]

SectorEvidenceAttemptV1 {
  requested_identity: SectorEvidenceRequestIdentityV1
  payload: SectorClassificationCandidatePayloadV1 | null
  failure: SectorEvidenceAttemptFailureV1 | null
  attempt_identity_sha256: Sha256
}

SourceObjectReceiptV1 {
  source_object_identity_sha256: Sha256
  canonical_object_bytes_hex: HexBytes[1..1048576]
  media_type: BoundedText
}
```

In an observed upstream branch, exactly one attempt is expected. At least one of
its `payload` and `failure` is non-null. A null payload with `NOT_RETURNED` is
missing. A late or invalid attempt may preserve its bounded payload and typed
failure. In an unobserved upstream branch no classification attempt is expected
or permitted: classification is dependency-blocked, and its absence adds no
classification-missing reason.

Every candidate provenance references one present receipt. Pure admission
recomputes the receipt digest, parses the sealed source-policy-selected schema,
applies `source_row_selector`, and requires the selected immutable bytes to
reproduce every candidate field exactly. It then derives authority, source,
schema, release, object identity, revision identity, supersession edge, clock
requirement, and clock authority from the sealed source binding. Candidate text
is only a claim. A selector may select exactly one value/object; zero, multiple,
out-of-range, or mutable selection is insufficient or structural according to
the truth table below, never silently repaired.

The taxonomy release, every assignment, every revision node, the lineage proof,
every coverage-manifest entry, and the licence proof each have an explicit
receipt/selector trace. Unconsumed candidate provenance is forbidden. The
coverage manifest must list the same 50 upstream ISINs and exact assignment
receipt/selector pairs. The lineage graph must include every revision named by
the manifest and source objects, have one selected current node, preserve every
supersession edge, be acyclic, have no fork with two current children, and be
checked through exactly the trusted knowledge cutoff. The licence proof must be
content-derived from immutable bytes; a digest alone cannot prove permission.

## Candidate-to-reason truth table

The reducer evaluates every applicable row and proof so one failure does not
hide lower-precedence reasons. These mappings are exact:

| Structurally valid candidate or attempt condition | Domain reason |
|---|---|
| expected attempt absent; null payload/`NOT_RETURNED`; taxonomy or manifest absent; 0 rows | `SECTOR_CLASSIFICATION_MISSING` |
| 1..49 rows, missing requested ISIN, or incomplete manifest | `SECTOR_CLASSIFICATION_MISSING` |
| 51 rows or any extra ISIN | `SECTOR_CLASSIFICATION_CORRUPT` |
| duplicate ISIN; overlapping effective rows; two selected assignments; conflicting labels/releases | `SECTOR_CLASSIFICATION_AMBIGUOUS` |
| invalid ISIN/date/label/effective interval; selector selects zero/multiple values; selected bytes disagree with candidate; `INVALID_SOURCE_ROW` | `SECTOR_CLASSIFICATION_CORRUPT` |
| candidate or failure is after cutoff; any required clock is after cutoff | `SECTOR_CLASSIFICATION_LATE` |
| authority/source/schema/release is not the sealed source-policy binding; `UNAUTHORIZED_AUTHORITY` | `SOURCE_NOT_AUTHORITATIVE` |
| required publication is null or not established by the selected official bytes | `PUBLICATION_UNPROVEN` |
| response/retrieval/retention clock missing, untrusted, rollback-conflicting, or derived from HTTP/filesystem/report/replay time | `CLOCK_UNTRUSTED` |
| exact tier is not official `Sector`, or release does not prove the four-tier path | `SECTOR_TIER_INVALID` |
| selected assignment interval or taxonomy release misses `decision_session` | `SECTOR_EFFECTIVE_SCOPE_MISMATCH` |
| lineage/manifest absent or incomplete; selected revision absent; checked-through differs from cutoff; gap, orphan, fork, cycle, conflicting current nodes, missing supersession, or post-cutoff node selected | `SECTOR_CLASSIFICATION_REVISION_UNPROVEN` |
| licence proof absent, digest-only, wrong source/release/scope/date, unresolved, or lacks retention or owner-private aggregate permission | `LICENCE_UNRESOLVED` |
| receipt/attempt/bundle identity, handoff/report binding, selected object/revision projection, manifest selector, or sealed policy/build claim mismatches | `EVIDENCE_IDENTITY_MISMATCH` |
| all above pass but exact assignment-to-handoff join or global equations fail | `SECTOR_TOTALS_INCONSISTENT` |
| owner proof is expired, replayed, wrong-owner, wrong-purpose, unauthenticated, anonymous, public, or does not match sealed privacy policy | `PRIVACY_POLICY_UNSATISFIED` |

Malformed UTF-8/JSON, duplicate object keys, unknown fields, noncanonical bytes,
invalid union shape, more than 51 assignment rows, or a bound violation is
structural admission failure: no report. By contrast, a structurally valid
candidate's bad market/taxonomy value remains representable through bounded
text and returns the table's insufficiency reason with null sectors.

## Verified facts reconstructed by admission

Only pure candidate-to-fact validation may construct these immutable facts:

```text
EvidenceClockV1 {
  publication_requirement: Literal["REQUIRED"]
  published_at: UtcInstant
  response_completed_at: UtcInstant
  retrieved_at: UtcInstant
  retained_at: UtcInstant
}

SectorProvenanceV1 {
  authority: Literal["NSE_INDICES"]
  source_identity: BoundedText
  schema_version: BoundedText
  classification_release_identity_sha256: Sha256
  source_object_identity_sha256: Sha256
  source_row_selector: BoundedText
  object_identity_sha256: Sha256
  revision_identity_sha256: Sha256
  supersedes_identity_sha256: Sha256 | null
  clock: EvidenceClockV1
}

TaxonomyReleaseFactV1 {
  authority: Literal["NSE_INDICES"]
  tier_path: Literal["MACRO_ECONOMIC_SECTOR/SECTOR/INDUSTRY/BASIC_INDUSTRY"]
  sector_tier_name: Literal["SECTOR"]
  effective_from: LocalDate
  effective_through: LocalDate | null
  provenance: SectorProvenanceV1
}

SectorAssignmentV1 {
  isin: Isin
  sector_label: SectorLabel
  taxonomy_tier: Literal["SECTOR"]
  effective_from: LocalDate
  effective_through: LocalDate | null
  provenance: SectorProvenanceV1
}

RevisionNodeV1 {
  revision_identity_sha256: Sha256
  supersedes_identity_sha256: Sha256 | null
  object_identity_sha256: Sha256
  status: Literal["SUPERSEDED", "SELECTED_CURRENT"]
  provenance: SectorProvenanceV1
}

RevisionLineageProofV1 {
  selected_revision_identity_sha256: Sha256
  checked_through: UtcInstant
  lineage_status: Literal["COMPLETE_CURRENT_AT_KNOWLEDGE_CUTOFF"]
  nodes: tuple[RevisionNodeV1, 1..64]
  provenance: SectorProvenanceV1
}

CoverageManifestEntryV1 {
  isin: Isin
  assignment_source_object_identity_sha256: Sha256
  assignment_source_row_selector: BoundedText
}

CoverageManifestV1 {
  decision_session: LocalDate
  required_member_count: Literal[50]
  entries: tuple[CoverageManifestEntryV1, 50]
  completeness: Literal["COMPLETE"]
  provenance: SectorProvenanceV1
}

LicenceProofV1 {
  licence_identity_sha256: Sha256
  source_identity: BoundedText
  classification_release_identity_sha256: Sha256
  retention_permission: Literal["PERMITTED"]
  owner_private_aggregate_permission: Literal["PERMITTED"]
  redistribution_permission: Literal["NOT_GRANTED"]
  effective_from: LocalDate
  effective_through: LocalDate | null
  review_status: Literal["APPROVED"]
  provenance: SectorProvenanceV1
}

VerifiedSectorClassificationFactsV1 {
  taxonomy_release: TaxonomyReleaseFactV1
  assignments: tuple[SectorAssignmentV1, 50]
  revision_lineage: RevisionLineageProofV1
  coverage_manifest: CoverageManifestV1
  licence_proof: LicenceProofV1
  input_identity_sha256: Sha256
}
```

`SectorLabel` is exact authoritative text after NFC validation, 1 through 128
UTF-8 bytes, without surrounding whitespace or control characters. It is opaque:
no trim, case-fold, alias, merge, abbreviation, translation, or interpretation
is permitted.

The reducer reparses the canonical evidence bundle, replays every selector over
the supplied immutable receipt bytes, reconstructs the candidate payload,
reconstructs every eligible verified fact and proof, and compares any supplied
admission trace byte-for-byte with that reconstruction. Caller-created
`VerifiedSectorClassificationFactsV1`, verified clocks, authority, release,
manifest completeness, licence approval, or digests are never trusted inputs.

## Closed owner-private audience proof

The audience proof is a closed sanitized application attestation, not a
credential:

```text
OwnerPrivateAudienceProofV1 {
  proof_version: Literal["nifty50-owner-private-audience@v1"]
  audience: Literal["OWNER_PRIVATE"]
  owner_identity_sha256: Sha256
  authenticated_capability_identity_sha256: Sha256
  authentication_verifier_identity_sha256: Sha256
  privacy_policy_identity_sha256: Sha256
  purpose: Literal["SECTOR_PARTICIPATION_RESEARCH"]
  issued_at: UtcInstant
  expires_at: UtcInstant
  request_identity_sha256: Sha256
  nonce_identity_sha256: Sha256
  proof_identity_sha256: Sha256
}
```

The application authenticates outside the reducer, consumes a nonce exactly
once, removes all credentials/secrets, and serializes this proof into the
private bundle. The reducer recomputes its identity; requires `issued_at <=
trusted_evaluation_at < expires_at`; binds request, owner, purpose, verifier,
and privacy policy to sealed expected values; and checks the nonce against a
sanitized immutable admission decision already captured before reducer entry.
The reducer reads no current clock or credential and cannot accept a caller's
boolean such as `authenticated = true`.

Because `sector_total == 1` can disclose one member's direction, an observed
aggregate is deliverable only to this authenticated, nonanonymous owner-private
boundary. Any proof failure suppresses the whole aggregate with
`PRIVACY_POLICY_UNSATISFIED`. Selective row suppression is forbidden. Even valid
output contains sector labels/counts only, never ISINs, symbols, company names,
member directions, closes, source rows, paths, credentials, licence text, or
free-form errors.

## Evidence bundle, reducer input, and trusted manifests

```text
SectorParticipationEvidenceBundleV1 {
  request: SectorParticipationRequestV1
  upstream: MarketRegimeEnvelopeV1
  source_objects: tuple[SourceObjectReceiptV1, 0..128]
  classification_attempt: SectorEvidenceAttemptV1 | null
  audience_proof: OwnerPrivateAudienceProofV1
  source_policy_identity_sha256: Sha256
  validation_policy_identity_sha256: Sha256
  privacy_policy_identity_sha256: Sha256
  policy_identity_sha256: Sha256
  code_identity_sha256: Sha256
  input_identity_sha256: Sha256
}

SectorParticipationReducerInputV1 {
  evidence_bundle_canonical_bytes_hex: HexBytes[1..2097152]
  evidence_bundle_identity_sha256: Sha256
  trusted_evaluation_at: UtcInstant
  reconstructed_facts: VerifiedSectorClassificationFactsV1 | null
}
```

There is exactly one non-circular identity projection.
`CanonicalSectorParticipationBundleIdentityProjectionV1(bundle)` contains every
closed `SectorParticipationEvidenceBundleV1` field except only
`input_identity_sha256`, with all nested values unchanged. It is serialized with
the one canonical profile; no second field omission, digest blanking, or
alternate reducer or reconstructed-facts projection is permitted:

```text
expected_bundle_identity =
  SHA256(canonical_json_lf(
    CanonicalSectorParticipationBundleIdentityProjectionV1(bundle)
  ))
bundle.input_identity_sha256 == expected_bundle_identity
reducer_input.evidence_bundle_identity_sha256 == expected_bundle_identity
reducer_input.reconstructed_facts.input_identity_sha256 ==
  expected_bundle_identity  # when reconstructed_facts is non-null
```

At construction and again at reducer admission, the full canonical bundle bytes
are parsed without normalization, the named projection is recomputed, and all
applicable equalities above are checked. `reconstructed_facts` is either null or
the deterministic candidate-to-fact projection re-derived from those exact full
bundle bytes. Its `input_identity_sha256` is assigned only from the recomputed
`expected_bundle_identity`; no caller-supplied fact, identity, alternate digest,
or matching-looking value is trusted. Any mismatch is structural rejection.

The reviewed application closes over these closed trust schemas:

```text
SectorSourcePolicyManifestV1 {
  manifest_version: Literal["nifty50-sector-source-policy@v1"]
  authority: Literal["NSE_INDICES"]
  source_identity: BoundedText
  schema_version: BoundedText
  release_identity_projection: BoundedText
  object_identity_projection: BoundedText
  revision_identity_projection: BoundedText
  supersession_projection: BoundedText
  selector_profile: Literal["NIFTY50_SECTOR_SELECTORS_V1"]
  trusted_clock_authority_identity_sha256: Sha256
}
SectorValidationPolicyManifestV1 {
  manifest_version: Literal["nifty50-sector-validation@v1"]
  canonical_profile: Literal["nifty50-canonical-json@v1"]
  reason_precedence: tuple[SectorParticipationReasonV1, 16]
  bounds_profile: Literal["nifty50-sector-participation-bounds@v1"]
}
SectorPrivacyPolicyManifestV1 {
  manifest_version: Literal["nifty50-sector-privacy@v1"]
  owner_identity_sha256: Sha256
  authentication_verifier_identity_sha256: Sha256
  audience: Literal["OWNER_PRIVATE"]
  purpose: Literal["SECTOR_PARTICIPATION_RESEARCH"]
}
SectorLicencePolicyManifestV1 {
  manifest_version: Literal["nifty50-sector-licence-policy@v1"]
  required_permissions: Literal["RETENTION_AND_OWNER_PRIVATE_AGGREGATE"]
  public_redistribution: Literal["NOT_AUTHORIZED"]
}
SectorSemanticPolicyManifestV1 {
  contract_version: Literal["nifty50-sector-participation@v1"]
  calculation_version: Literal["nifty50-sector-participation-counter@v1"]
  projection: Literal["OBSERVED-MARKET-REGIME-ISIN-TO-OFFICIAL-SECTOR-COUNTS@v1"]
}
SectorCodeBuildManifestV1 {
  manifest_version: Literal["nifty50-sector-build@v1"]
  source_tree_identity_sha256: Sha256
  dependency_lock_identity_sha256: Sha256
  build_recipe_identity_sha256: Sha256
  reducer_entrypoint: BoundedText
}
ExpectedReviewedBuildV1 {
  source_policy_manifest_canonical_bytes_hex: HexBytes[1..65536]
  validation_policy_manifest_canonical_bytes_hex: HexBytes[1..65536]
  privacy_policy_manifest_canonical_bytes_hex: HexBytes[1..65536]
  licence_policy_manifest_canonical_bytes_hex: HexBytes[1..65536]
  semantic_policy_manifest_canonical_bytes_hex: HexBytes[1..65536]
  code_build_manifest_canonical_bytes_hex: HexBytes[1..65536]
  source_policy_identity_sha256: Sha256
  validation_policy_identity_sha256: Sha256
  privacy_policy_identity_sha256: Sha256
  licence_policy_identity_sha256: Sha256
  policy_identity_sha256: Sha256
  code_identity_sha256: Sha256
}
```

Every adjacent identity is recomputed from the exact named canonical manifest
bytes. `ExpectedReviewedBuildV1` is sealed into the reviewed build, not supplied
by a request or bundle. The source manifest selects one authority/source/schema
and the release, object, revision, supersession, selector, and trusted-clock
projections; it does not contain one caller-chosen release value. Coordinated
replacement and rehashing of candidate bytes, bundle, manifests, and claimed
digests cannot replace these sealed trust roots.

The reducer accepts parsed immutable values and performs zero network, provider,
filesystem, database, environment, wall-clock, credential, randomness, logging,
telemetry, subprocess, or storage-write I/O.

## Frozen aggregation and cross-fact equations

For each of the 50 unique upstream handoff ISINs, join exactly one reconstructed
assignment by exact ISIN. For each distinct exact sector label `s`, in canonical
UTF-8 byte order:

```text
sector_advances[s] = count(sector == s and direction == ADVANCE)
sector_declines[s] = count(sector == s and direction == DECLINE)
sector_unchanged[s] = count(sector == s and direction == UNCHANGED)
sector_total[s] = sector_advances[s] + sector_declines[s] + sector_unchanged[s]

sum(sector_total[s] for s in sectors) = 50
sum(sector_advances[s] for s in sectors) = upstream.advances
sum(sector_declines[s] for s in sectors) = upstream.declines
sum(sector_unchanged[s] for s in sectors) = upstream.unchanged
upstream.advances + upstream.declines + upstream.unchanged = 50
```

Each member contributes once to one direction and one sector. Every emitted
`sector_total` is 1..50; each directional count is 0..50. There is no unknown
bucket, partial denominator, percentage, weight, score, or residual. Any failed
join/equation produces null sectors; no unaffected sector may leak.

The reducer validates these additional invariants:

```text
request.decision_session == upstream.report.decision_session
upstream observed report identities == handoff identities
upstream observed endpoints == handoff endpoints
handoff direction totals == upstream observed counts
classification requested ISINs == handoff ISINs
assignment ISINs == manifest ISINs == handoff ISINs
all assignment and taxonomy effective intervals cover decision_session
all source and proof clocks <= knowledge_cutoff
lineage.checked_through == knowledge_cutoff
licence source/release == taxonomy and assignment source/release
all receipt digests, selectors, objects, revisions, manifests, and policy identities recompute
```

## Owner-private report and exact nullability

```text
SectorCountV1 {
  sector_label: SectorLabel
  sector_total: Integer[1..50]
  advances: Integer[0..50]
  declines: Integer[0..50]
  unchanged: Integer[0..50]
}

SectorParticipationReportV1 {
  contract_version: Literal["nifty50-sector-participation@v1"]
  calculation_version: Literal["nifty50-sector-participation-counter@v1"]
  request_identity_sha256: Sha256
  market_regime_report_identity_sha256: Sha256 | null
  input_identity_sha256: Sha256
  source_policy_identity_sha256: Sha256
  validation_policy_identity_sha256: Sha256
  privacy_policy_identity_sha256: Sha256
  policy_identity_sha256: Sha256
  code_identity_sha256: Sha256
  decision_session: LocalDate
  comparison_session: LocalDate | null
  decision_market_close: UtcInstant | null
  evidence_cutoff: UtcInstant | null
  required_member_count: Literal[50]
  evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
  sectors: tuple[SectorCountV1, 1..50] | null
  primary_reason: SectorParticipationReasonV1 | null
  additional_reasons: tuple[SectorParticipationReasonV1, 0..15]
  report_identity_sha256: Sha256
}
```

An observed report requires the observed upstream branch, all endpoints
non-null, 1..50 sector rows, every equation satisfied, and no reasons. An
insufficient report has `sectors = null` and at least one reason. For upstream
`ABSENT`, the Market Regime report identity and all three nullable endpoints are
null. For upstream `INSUFFICIENT_EVIDENCE`, its report identity is non-null and
its exact endpoint stage is copied. Classification defects can never advance an
endpoint. The report identity hashes every field except only itself.

## Closed reasons and precedence

Exact first-match precedence is declaration order. The closed type is the
following literal sequence and has no other value:

```text
SectorParticipationReasonV1 = Literal[
  "EVIDENCE_IDENTITY_MISMATCH",
  "MARKET_REGIME_NOT_OBSERVED",
  "SOURCE_NOT_AUTHORITATIVE",
  "PUBLICATION_UNPROVEN",
  "CLOCK_UNTRUSTED",
  "LICENCE_UNRESOLVED",
  "SECTOR_CLASSIFICATION_MISSING",
  "SECTOR_CLASSIFICATION_LATE",
  "SECTOR_CLASSIFICATION_AMBIGUOUS",
  "SECTOR_CLASSIFICATION_CORRUPT",
  "SECTOR_CLASSIFICATION_REVISION_UNPROVEN",
  "SECTOR_EFFECTIVE_SCOPE_MISMATCH",
  "SECTOR_TIER_INVALID",
  "MEMBER_DIRECTION_HANDOFF_INVALID",
  "SECTOR_TOTALS_INCONSISTENT",
  "PRIVACY_POLICY_UNSATISFIED",
]
```

Observed output has no reasons. Insufficient output chooses the earliest
applicable reason as primary and lists each other applicable reason once in
declaration order. Discovery, source-row, map, and fault-injection order cannot
change it. `MEMBER_DIRECTION_HANDOFF_INVALID` applies only to a structurally
valid observed envelope whose handoff violates exact row/order/count/cross-field
semantics; forbidden/missing union fields remain structural no-report errors.
Privacy is evaluated even when another domain defect applies.

## Edge-case truth table

| Case | Required result |
|---|---|
| observed upstream, 50 assignments, all proofs, valid owner proof | `OBSERVED`; exact full counts |
| upstream absent | `INSUFFICIENT_EVIDENCE / MARKET_REGIME_NOT_OBSERVED`; all endpoints null |
| upstream insufficient at schedule-unverified stage | same reason; all endpoints null |
| upstream insufficient with endpoints but unresolved next open | same reason; comparison/close copied, cutoff null |
| upstream insufficient with cutoff resolved | same reason; all three endpoints copied |
| upstream unobserved envelope carries a handoff | structural rejection; no report |
| observed envelope omits a handoff or has foreign/noncanonical report | structural rejection; no report |
| expected classification attempt missing, 0 rows, 49 rows, or one missing ISIN | whole-report insufficiency; null sectors |
| 51 rows, extra ISIN, malformed candidate field, or selector mismatch | whole-report insufficiency; null sectors |
| duplicate ISIN, overlapping effective assignments, or conflicting labels | `SECTOR_CLASSIFICATION_AMBIGUOUS`; null sectors |
| wrong taxonomy tier or release path | `SECTOR_TIER_INVALID`; null sectors |
| late publication/retrieval/retention or untrusted clock | exact clock/timeliness reason; null sectors |
| unresolved retention/private-use licence | `LICENCE_UNRESOLVED`; null sectors |
| lineage gap, fork, cycle, conflicting current revision, unchecked cutoff, or missing manifest entry | `SECTOR_CLASSIFICATION_REVISION_UNPROVEN`; null sectors |
| schedule correction or corporate-action completeness changes upstream | downstream verifies new bound upstream report/handoff only; never recomputes the change |
| one 50-member sector | one exact row reconciling to 50 |
| fifty singleton sectors | 50 owner-private rows; never public |
| one singleton plus one 49-member sector | two owner-private rows; never selectively suppress |
| malformed JSON, duplicate JSON key, unknown field, >51 rows, or oversize bundle | structural rejection; no report |
| unchanged sealed old input replay after any external post-cutoff change | byte-identical old report |
| separately sealed input containing a post-cutoff revision | new input/report identities and its newly derived outcome; no cross-input byte-identity requirement |

Schedule corrections and corporate-action completeness are adversaries of the
upstream boundary only. Sector Participation checks that the supplied observed
report and handoff remain mutually bound; it must not reinterpret schedules,
prices, actions, or identity continuity.

## Canonical replay, metamorphism, and versioning

All external bytes use Plan 12's canonical UTF-8 JSON-plus-one-LF profile:
closed schemas, sorted object keys, compact separators, minimal escaping,
canonical integers, exact tuple order, no duplicate keys, and no normalization
after receipt. Verified semantic strings are NFC. `CandidateText` is the one
intentional attempted-evidence exception: its exact Unicode scalar sequence is
preserved and hashed without normalization so non-NFC or otherwise corrupt
candidate claims can yield domain insufficiency. Candidate assignment order is retained and hashed
so duplicates and noncanonical semantic order remain inspectable; verified
assignments/handoff rows are strictly ISIN-sorted and report sectors are sorted
by label UTF-8 bytes.

Replay of the unchanged, sealed old input never reads external state. Even if a
source publishes a correction after the cutoff, the old canonical input and
sealed policies produce a byte-identical old report. A separately sealed input
that explicitly contains the post-cutoff revision has new source, revision,
manifest, bundle, input, and report identities and a newly derived outcome
(usually late or revision-insufficient for the old cutoff). Byte identity is
never demanded across changed inputs.

A change to taxonomy tier/authority, endpoint, cohort, direction, audience,
field, nullability, evidence/revision/licence rule, reason precedence, equation,
identity projection, canonical profile, or bound is breaking and requires a new
contract version.

## Bounds and future implementation stop

Exact limits are: request 4 KiB; private bundle 2 MiB; report and each policy
manifest 64 KiB; source objects 1 MiB each and at most 128; assignment and
manifest candidate rows 0..51; verified assignments/handoff rows exactly 50;
lineage nodes 0..64 candidates and 1..64 verified; sector rows 1..50; sector
labels 1..128 UTF-8 bytes; nesting at most 16; additional reasons at most 15.
Limit-plus-one is always tested.

This slice authorizes documentation edits and review only. Per the owner
clarification, it adds no documentation assertion and no test file. The feasible
future order is fixed and non-circular:

1. obtain separate owner authorization for implementation and for any source or
   private-delivery work;
2. approve source, licence, acquisition, retention, budget, and bounded manifest,
   then immutably retain candidate bytes without reducing sector counts;
3. implement/review the Market Regime observed-only handoff prerequisite and the
   Sector Participation pure schemas/admission/reducer with strict TDD Layer A;
4. independently review that implementation, then seal code, evidence, source,
   validation, semantic, privacy, licence, selector, and audience policies;
5. run readiness over one sealed bundle without computing or disclosing sector
   counts; and
6. only if readiness is `READY`, reduce exactly that one bundle once and deliver
   its aggregate through the owner-private boundary.

Failure stops the sequence. There is no same-input handoff before implementation,
no source contact under this plan, no readiness shortcut, and no tuning loop.
