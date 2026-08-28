# Fixed-cohort historical OHLCV revision store contract

Status: **ACCEPTED — Sprint 15 / GitHub Issue #120 first-working slice**  
Contract revision: `fixed-cohort-historical-ohlcv-revision-store@v1`  
Risk: **R3** — financial research integrity, historical evidence, and immutable publication

## Purpose and scope

This contract admits one operator-supplied, owner-private daily OHLCV evidence
package for a supplied canonical listed-equity cohort, retains its declared
source material, and publishes one exact immutable revision. It also admits an
exact successor that appends sessions or corrects named coordinates without
rewriting the predecessor.

Every success and failure is scoped literally as
`FIXED_COHORT_RETROSPECTIVE`. The supplied cohort is not evidence of historical
Nifty 50, Nifty Next 50, or Nifty 100 membership. The store retains OHLCV and
provenance only; it does not evaluate a study, context, Market Structure, a
recommendation, sizing, entry/exit, or an order.

The only admitted price basis is the literal
`SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED`: every open, high, low, and close is
split-adjusted and dividend-unadjusted. No raw bar, automatic adjustment,
yfinance adjusted-close composition, mixed basis, inferred source semantics, or
fallback is admitted.

## First-working-slice boundary

### Included

- One local, operator-supplied JSON request manifest and exact source-policy,
  source-artifact, and receipt files.
- A 1–50 member canonical listed-equity cohort, one inclusive daily session
  range, and an explicit ordered schedule.
- Exact-`Decimal` full daily OHLCV grid admission before any storage effect.
- Immutable content-addressed objects and one full materialized immutable
  revision for `INITIAL`, `APPEND`, and `CORRECTION`.
- Exact retry, exact named-revision readback, parent preservation, and
  owner-private no-follow storage-root authority.
- CLI import and read composition over the same domain service.

### Later only

- Provider or network download, credentials, source discovery, alternative
  import formats, provider routing, or any fallback.
- Revision enumeration, mutable latest pointers, delta compaction, generalized
  replay, replication, retention tiers, or attestation.
- Historical membership, sector, news, event, corporate-action, dividend, or
  fundamental acquisition; Sprint-16 study-profile/availability-ledger
  qualification; point-in-time historical studies; or Issue #139 snapshots.
- Raw one-minute schema/table changes, catalog migration, Market Structure, or
  any downstream trading behavior.

## Closed schema, configuration, and canonical encoding

Every JSON object is UTF-8, contains unique keys, uses no floats, and is encoded
as compact sorted-key JSON (`separators=(',', ':')`, `sort_keys=True`). The
received bytes must equal that exact canonical encoding; duplicate keys,
noncanonical whitespace/order/escapes, floats/constants, wrong-shaped scalars,
and structures with more than 64 containers are rejected before any effect.
Only object and list containers count; a scalar adds no depth. Exactly 64
containers are accepted and 65 are rejected. Digests are lowercase SHA-256
hexadecimal text. Dates are ISO `YYYY-MM-DD`; instants are UTC
`YYYY-MM-DDTHH:MM:SSZ` with no fractional seconds; JSON integer values are
built-in integers; and decimal values are canonical non-exponent decimal
strings. Canonical decimal strings have no leading `+`, no exponent, no leading
zero except `0`, and no insignificant trailing fractional zero.

Schema identity is computed once from a deterministic JSON-safe closed preimage:
canonical encoding; scalar grammar and nullability; exact per-field type,
nullability, literal/enum set, bounds, ordering, unknown-field rejection, and
cross-reference rules for mappings, members, correction coordinates, limits,
requests, policy, receipt, bars, artifact, schedule, and the full revision.
Every revision request-projection field is a deep-copied exact request-field
contract, including type, nullability, literals, bounds, ordering, and
cross-references. The preimage also covers every identity formula; complete
`INITIAL`/`APPEND`/`CORRECTION` transition semantics including `INITIAL`
existing-root exact-replay-only admission, an `APPEND` child upper bound not
before its parent's inclusive upper bound, and a first suffix session strictly
later than that parent bound; the child upper bound may be a non-session;
correction full-grid membership and its exact mutable fields; and the ordered
failure grammar. Configuration identity is computed once from a separate
closed preimage containing every contract literal,
source/schedule version, individual limit including JSON depth, immutable and
visible-directory modes, storage layout, `.ingestion.lock` name and mode,
no-follow path control, CLI-admitted root-identity propagation, existing-directory
and initial-exact-replay hierarchy owning-parent fsync-before-open controls,
durability/fsync controls, disclosures, and correction mutable fields. Runtime identity is
`runtime_source_sha256(_RUNTIME_SOURCE)` as captured at module load from the
verified loaded store module; it is never reread from a mutable `Path(__file__)`.

A decimal string is parsed directly as `Decimal`; binary float inputs are never
coerced or ambient-context-normalized. A `Decimal` used for OHLC is finite and
strictly positive. `volume` is a finite nonnegative integral decimal string
serialized canonically as a base-10 integer string.

### `CanonicalListedEquityMemberV1`

```json
{
  "isin": "INE002A01018",
  "exchange": "NSE",
  "listed_equity_segment": "EQUITY",
  "effective_symbol": "RELIANCE",
  "symbol_effective_from": "2020-01-01",
  "symbol_effective_to": null,
  "provider_mapping": {
    "provider": "OPERATOR_LOCAL_IMPORT",
    "provider_instrument_id": "RELIANCE-EQ",
    "mapping_effective_from": "2020-01-01",
    "mapping_effective_to": null,
    "mapping_evidence_sha256": "<64 lowercase hex>"
  }
}
```

`isin` is exactly 12 uppercase ASCII alphanumeric characters. `exchange` is
exactly `NSE`; `listed_equity_segment` is exactly `EQUITY`; symbols and provider
IDs are nonempty printable ASCII strings of at most 64 characters. Intervals
are inclusive when `*_to` is non-null and must not end before their start. Every
non-null effective endpoint must be a valid exact ISO date; malformed values
are `MALFORMED_INPUT` before effects. A member is identified by `(isin,
exchange)`; each member must occur once, and members are canonically sorted by
that tuple. `provider_mapping.provider` is exactly `OPERATOR_LOCAL_IMPORT`; it
names this import profile, not a provider adapter or a source-quality claim.

### `FixedCohortHistoricalOhlcvRequestV1`

```json
{
  "contract_version": "fixed-cohort-historical-ohlcv-revision-store@v1",
  "research_scope": "FIXED_COHORT_RETROSPECTIVE",
  "operation": "INITIAL",
  "parent_revision_sha256": null,
  "correction_coordinates": [],
  "cohort": ["CanonicalListedEquityMemberV1"],
  "from_session": "2024-01-02",
  "to_session": "2024-01-03",
  "interval": "1d",
  "expected_sessions": ["2024-01-02", "2024-01-03"],
  "schedule_evidence_sha256": "<64 lowercase hex>",
  "source_policy_sha256": "<64 lowercase hex>",
  "source_artifact_sha256": "<64 lowercase hex>",
  "receipt_sha256": "<64 lowercase hex>",
  "acquired_at": "2024-01-04T00:00:00Z",
  "known_at_cutoff": "2024-01-04T00:00:00Z",
  "permitted_use": "OWNER_PRIVATE_RESEARCH",
  "price_basis": "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED",
  "schema_identity_sha256": "<64 lowercase hex>",
  "runtime_code_identity_sha256": "<64 lowercase hex>",
  "configuration_identity_sha256": "<64 lowercase hex>",
  "limits": {
    "max_members": 50,
    "max_sessions": 10000,
    "max_rows": 500000,
    "max_artifact_bytes": 134217728,
    "max_source_policy_bytes": 1048576,
    "max_receipt_bytes": 1048576,
    "max_revision_bytes": 134217728,
    "max_lineage_depth": 128
  }
}
```

The request is closed: the exact literal contract revision, scope, interval,
permitted-use value, and price basis are required. `known_at_cutoff >=
acquired_at`. Its cohort contains 1–50 members and has no duplicate canonical
identity. `from_session <= to_session`; `expected_sessions` is nonempty,
strictly increasing, within that inclusive range, and is the complete claimed
session grid. It has at most 10,000 sessions. `limits` must equal the literal
contract ceilings shown above; callers cannot relax bounds by supplying a larger
number. `max_rows` is a defensive ceiling and the rectangular grid must also
fit `len(cohort) * len(expected_sessions)`; `max_revision_bytes` separately
bounds the final materialized revision before publication. The schedule identity
is not a caller label: it is SHA-256 of the canonical
`{"schema_version":"fixed-cohort-historical-ohlcv-schedule@v1","from_session",
"to_session","expected_sessions"}` preimage with those exact request values.
Schema, runtime, and configuration identities supplied for a **new import** must
equal the current values computed above. The request must supply each exact
derived identity or is rejected. Historical readback instead requires retained
identity fields to be syntactically valid lowercase SHA-256 values, recomputes
the complete stored request identity, and never compares those historical values
with the current executable. Source policy/artifact/receipt digests bind their
exact bytes and semantics below.

The canonical request preimage is this complete object without
`request_identity_sha256`; `request_identity_sha256` is SHA-256 of its
canonical JSON bytes. Any successful request materializes its exact validated
request projection in the revision envelope. A mutation of any preimage field
changes the request identity or causes admission failure.

### Source material

The CLI receives three exact local regular files: a source-policy JSON object,
a source-artifact byte file, and a receipt JSON object. Their supplied SHA-256
values must match their bytes before lease acquisition. Policy and receipt are
bounded to 1 MiB; artifact bytes are bounded to 128 MiB. All three file paths
must resolve without following any path link, be strictly outside the admitted
storage root, and be opened once as regular files with an enforced byte ceiling.
Containment rejection occurs before the domain service can obtain a lease or
mutate storage. Neither the domain service nor CLI contacts a provider or uses
a credential.

The closed source-policy object is:

```json
{
  "schema_version": "operator-local-historical-ohlcv-source-policy@v1",
  "source_name": "<nonempty printable ASCII>",
  "permitted_use": "OWNER_PRIVATE_RESEARCH",
  "ohlcv_adjustment_semantics": "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED",
  "artifact_sha256": "<same source_artifact_sha256>"
}
```

The closed receipt object is:

```json
{
  "schema_version": "operator-local-historical-ohlcv-receipt@v1",
  "source_policy_sha256": "<same source_policy_sha256>",
  "source_artifact_sha256": "<same source_artifact_sha256>",
  "acquired_at": "<same acquired_at>",
  "known_at": "<known_at <= known_at_cutoff>",
  "permitted_use": "OWNER_PRIVATE_RESEARCH",
  "ohlcv_adjustment_semantics": "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED"
}
```

No unknown source-policy or receipt field, alternate basis, absent semantics,
incorrect cross-reference, future-known receipt, or disallowed permitted-use
can publish a revision. These files prove only the declared import boundary;
they do not prove point-in-time availability for a later study.

### Candidate bars and full snapshots

The source-artifact bytes must decode as one closed JSON object:

```json
{
  "schema_version": "operator-local-historical-ohlcv-artifact@v1",
  "bars": [
    {
      "isin": "INE002A01018",
      "exchange": "NSE",
      "session": "2024-01-02",
      "open": "100",
      "high": "101",
      "low": "99",
      "close": "100.5",
      "volume": "10",
      "known_at": "2024-01-03T00:00:00Z",
      "price_basis": "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED"
    }
  ]
}
```

Each row must bind one exact supplied `(isin, exchange)` and one expected
session, appear in canonical member-major/session-major order, and have a
unique key. It has no symbol fallback. `known_at <= known_at_cutoff`. The OHLC
envelope is `low <= min(open, close) <= max(open, close) <= high`; volume is
finite, nonnegative, and integral. `len(bars) <= limits.max_rows` is a
structural bound: exactly 500,000 rows are structurally admitted and 500,001
rows are `MALFORMED_INPUT`, before capability or evidence classification. The
artifact must contain exactly one row for every cohort/session coordinate. The
importer never sorts, deduplicates, repairs, imputes, re-bases, or omits a row.
Duplicate rows, including bytewise equal duplicates, are invalid.

The request source artifact always carries a full materialized candidate grid.
For successors it is the intended full snapshot, not a delta. This keeps V1
readback and lineage auditable without a second replay subsystem.

## Revision identity and immutable representation

`HistoricalOhlcvRevisionV1` is one canonical JSON object persisted under its
SHA-256. Its `revision_sha256` is SHA-256 of the object without that field.
The preimage includes all of the following, with no generated time or path:

```text
contract_version, research_scope, operation, parent_revision_sha256,
correction_coordinates, cohort, from_session, to_session, interval,
expected_sessions, schedule_evidence_sha256, source_policy_sha256,
source_artifact_sha256, receipt_sha256, acquired_at, known_at_cutoff,
permitted_use, price_basis, schema_identity_sha256, runtime_code_identity_sha256,
configuration_identity_sha256, limits, request_identity_sha256, lineage_depth,
context_status, limitation, and canonical full bars.
```

`correction_coordinates` is a canonical strictly increasing sequence of unique
`{"isin", "exchange", "session"}` objects. Duplicate or unsorted coordinates
are malformed request structure, before unsupported capability, evidence, or
parent-lineage checks. A well-formed `CORRECTION` coordinate outside the
candidate full grid is `INVALID_EVIDENCE` before any parent read; every remaining
coordinate must name an exact parent row. It is empty for `INITIAL` and
`APPEND`.
The revision’s literal `context_status` is `HISTORICAL_CONTEXT_NOT_EVALUATED`,
and its literal limitation is
`FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION`.

The revision object resides at
`historical_ohlcv_revisions/v1/revisions/<revision_sha256>.json`. Source
objects reside at `historical_ohlcv_revisions/v1/objects/<sha256>` and are the
exact supplied bytes. Every location is derived only from a validated digest.
Publication is create-only, mode `0400`, no-follow under `StorageRootLease`, and
directory-fsynced after visibility. An existing-directory retry fsyncs that
directory's owning parent before it opens or succeeds; `INITIAL` exact replay
applies this to every existing root/v1/objects/revisions hierarchy edge. An fsync
failure remains publication uncertainty. An exact matching existing source object
or revision must also fsync its owning directory before retry can return success;
an fsync failure remains publication uncertainty.
If temporary unlink, parent fsync, or exact readback fails after a link becomes
visible, the importer returns publication uncertainty but preserves the exact
content-addressed name; it never unlinks a visible name during error handling.
The retained object/revision is independently revalidated on exact retry, so no
visible revision can retain removed source objects and no other writer's name
can be removed by rollback. A matching existing object/revision is exact replay;
a missing, nonregular, mismatched, unreadable, or divergent existing
object/revision is a terminal publication conflict/uncertainty. There is no
mutable latest pointer.

## State transitions and lineage

### `INITIAL`

`parent_revision_sha256` is null and `correction_coordinates` is empty. A
complete rectangular candidate grid produces lineage depth `0`.

### `APPEND`

An exact readable parent is required. The child cohort and its identity mappings,
price basis, date lower bound, and all parent expected sessions must equal the
parent. The child independently binds its new source policy, artifact, receipt,
and schema/code/config identities. The child `to_session` must not precede the
parent inclusive `to_session`. New expected sessions are a nonempty strict
contiguous suffix after the parent’s final session and its inclusive `to_session`
in the supplied child schedule; no overlap, gap, replacement, retroactive
session, or reordering is allowed. The inclusive child `to_session` may be later
than the final expected session, including a weekend or exchange closure; every
expected session still remains within that bound.
Parent rows must be semantically and canonically identical in the child; only
rows for the suffix may be new. Lineage depth is parent depth plus one and
cannot exceed 128.

### `CORRECTION`

An exact readable parent is required. The expected sessions equal the parent’s
exact session sequence; no session is appended or omitted.
`correction_coordinates` is nonempty, sorted, unique, and every coordinate
occurs in the full candidate grid and parent. Every row not named is canonically
identical to its parent. Every named row must differ from its parent in at least
one of exactly open, high, low, close, volume, or known-at, and must not alter
any other field. Lineage depth is parent depth plus one and cannot exceed 128.

A successor validates an exact compatible V1 historical parent using that
parent's retained historical identity fields. The successor independently binds
the currently loaded verified runtime and current schema/configuration identities.

A parent is never changed by a successor. Exact retry of any transition returns
the same revision bytes and identity. A request that resolves to an existing
identity with different bytes, or encounters an unsafe parent/object/revision,
fails closed rather than selecting a different revision.

## Effect order and failure precedence

Validation completes five whole-candidate passes before any writer effect:

1. **Malformed structure and request admission:** every request, policy,
   artifact, receipt, member, mapping, coordinate, and bar is bounded, canonical,
   closed, and shape-checked. Request literals, limits—including the structural
   `max_rows` artifact bound—ordering—including sorted-unique correction
   coordinates—schedule, and current import identities are checked here. A
   malformed later bar beats an earlier unsupported value.
2. **Unsupported capability:** scan request permitted use/basis, every mapping
   provider, policy/receipt profile and semantics, artifact version, and every
   bar basis. A future-known receipt plus unsupported basis is unsupported; an
   earlier invalid numeric bar plus later mixed basis is unsupported.
3. **Invalid evidence:** verify source digests and cross-references, receipt
   cutoff, full grid/order/coordinates, including correction candidate-grid
   membership before any parent read, Decimal grammar, OHLC envelope, volume,
   and all bar cutoffs. Empty correction plus invalid source is invalid evidence.
4. **Parent and lineage:** validate operation grammar, remaining exact parent
   coordinate membership, historical parent readability, preservation/suffix/
   correction semantics, depth, and cycles.
5. **Storage:** construct the candidate revision identity, then acquire writer
   authority. A fresh `INITIAL` obtains an empty owner-private root atomically
   through `try_acquire_private_empty`; if that admission is unavailable, it
   identity-pins an existing private root, acquires its pre-existing lease, and
   before creating any hierarchy or object proves the candidate revision and
   every candidate source object already exist, validate exactly, and are
   directory-synced. An absent or divergent candidate fails without a new
   hierarchy, object, or lock. `APPEND` and `CORRECTION` revalidate their parent
   under authority, then perform exact-replay check, create-only
   publication/fsync, and exact readback.

Malformed input wins before unsupported capability, which wins before invalid
evidence, parent/lineage conflict, and publication uncertainty. No failure
returns partial bars or a parent/previous revision as requested success.

The first fresh `INITIAL` obtains an empty owner-private root atomically through
`try_acquire_private_empty`; request/source files are outside that root. An
`INITIAL` on an existing root is permitted only for the exact replay described
above. Replay and successors first admit an existing private `(st_dev, st_ino)`
identity then use `try_acquire_existing_identity`. The CLI carries its admitted
root identity into the domain store; supplied domain read and write authority
requires that identity, including private-empty initial admission. Unpinned
`try_acquire` is not used. `.ingestion.lock` is the lease file, and every invalid
pre-storage input leaves it and the historical directory absent.

The domain outcome categories are `SUCCESS`, `MALFORMED_INPUT`,
`UNSUPPORTED_CAPABILITY`, `INVALID_EVIDENCE`, `PARENT_LINEAGE_CONFLICT`, and
`PUBLICATION_UNCERTAIN_OR_CONFLICT`. They retain bounded machine-safe detail;
they do not echo source payloads or local paths.

## Exact readback

`HistoricalOhlcvRevisionStoreV1.read_exact(revision_sha256)` has no discovery
behavior: it accepts one 64-character lowercase SHA-256 identity, acquires
owner-private read authority, and reads only the derived revision path. Each
local revision validates its closed complete request projection, syntactic
historical identities, request/revision digests, retained source objects,
cross-references, bars, and disclosures without comparing identities to the
current process. An iterative child/parent pass checks depth and visited IDs
before every read, retains at most two lineage snapshots, validates every
transition, and rereads the exact target for return. It must not follow a latest
pointer, silently use a parent, repair storage, or reach a
provider/network/credential boundary.

## Acceptance

Focused owned tests must prove:

1. pinned loaded-runtime identity, no empty-digest fallback, historical-runtime
   read compatibility, current successor identity binding, complete 22-field
   retained request projection, and exact deep-copied request-field metadata in
   the revision schema;
2. canonical hostile request/policy/artifact/receipt rejection—including
   duplicate, noncanonical, float/constant, exact-depth, wrong-root,
   missing/unknown, wrong-primitive, empty, oversize, malformed non-null
   mapping effective endpoints, and the 500,000/500,001 structural artifact-row
   boundary—every named source digest/cross-reference failure, and Decimal
   grammar/envelope boundaries;
3. whole-candidate malformed, unsupported, invalid-evidence, lineage, and
   unsafe-storage precedence, including malformed correction ISIN/exchange/date
   coordinates, out-of-cohort and out-of-session correction coordinates before
   both missing and existing parent reads, and later-row cases;
4. `INITIAL`, exact replay/divergent-content conflict, rejection of an unrelated
   existing nonempty root without hierarchy mutation, 50-member/member-major
   append including an inclusive weekend/closure upper bound, rejection of
   overlap/gap/reorder, retroactive suffix inside a parent inclusive range, and
   child-range shrink, plus duplicate/unsorted correction coordinates, correction
   and grandparent tampering, source/parent loss, and predecessor preservation;
5. independent policy/artifact/receipt source-reference substitution,
   depth-128 acceptance, depth-129 and cycle pre-read rejection, bounded
   two-snapshot iteration, target reread, and writer parent reverification
   through the iterative reader;
6. root substitution rejection, CLI admission-to-domain root substitution
   rejection for both import and read with no effect, fresh private-empty
   `.ingestion.lock` mode `0600`, group-accessible root no-effect, real
   lease-file no-effect assertions for all domain and CLI rejections, and CLI
   read unsafe-root and live-lock negatives;
7. import-level `INITIAL` exact-replay root/v1/objects/revisions hierarchy
   owning-parent-fsync-before-open order observation and fault injection,
   repeated sibling-directory second-open and owning-parent-fsync failures
   closing every previously opened descriptor, plus source and revision post-link
   temporary-unlink, parent-fsync, and exact-read fault injection: each returns
   publication uncertainty; only a fully preserved candidate revalidates as an
   exact retry, while an incomplete retained `INITIAL` fails closed; and
8. only this accepted first-working slice and its later boundaries.

A final real-source smoke requires an owner-approved exact source policy,
source artifact, receipt, full OHLCV adjustment proof, schedule evidence, and
permitted-use evidence. Synthetic fixtures prove contract behavior only and
cannot be described as that smoke.
