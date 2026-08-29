# Fixed-cohort historical Upstox RAW OHLCV revision store contract

Status: **ACCEPTED CONTRACT — Sprint 15 / Issue #120 in progress; the implementation candidate is complete, with fresh exact-byte review and delivery gates pending.**
Completion profile: `UPSTOX_RAW`
Revision contract: `fixed-cohort-historical-ohlcv-upstox-raw-revision-store@v1`
Risk: **R3** — persisted financial-research evidence, immutable lineage, source identity, filesystem authority, and concurrency.

## Purpose and scope

This is one retained-source, owner-private historical evidence profile. It projects
already-retained verified Upstox one-minute Parquet partitions into complete daily
raw OHLCV and publishes immutable, exact revisions for a supplied 1–50 canonical
listed-equity cohort. Every result is `FIXED_COHORT_RETROSPECTIVE`; supplied
identity is not a historical Nifty 50, Nifty Next 50, or Nifty 100 claim.

The profile is deliberately **raw and retrospective**:

- provider in persisted research evidence: `UPSTOX`; physical plan provider: `upstox`;
- source name/version/interval: `UPSTOX_RETAINED_VERIFIED_1M`,
  `upstox-historical-v3`, `1m`;
- daily aggregation: `nse-session-ohlcv@v1`; revision interval: `1d`;
- price basis / physical adjustment state: `RAW` / `raw`;
- temporal status: `REVISED_NON_PIT`;
- corporate-action status: `NOT_EVALUATED`;
- comparability status: `NOT_ESTABLISHED`;
- context status: `HISTORICAL_CONTEXT_NOT_EVALUATED`;
- limitation: `FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION`.

A successful revision does **not** establish adjusted continuity, corporate-action
handling, cross-session comparability, point-in-time availability, index
membership, study qualification, recommendation, sizing, entry/exit, or order
behavior.

## First-working-slice boundary

Included: one closed source profile; already-retained verified closed Upstox
partitions; retained schedules, instrument snapshots, DuckDB manifests, coverage,
and daily aggregation; source/destination root separation; immutable
`INITIAL`/`APPEND`/`CORRECTION`; exact retry/readback; and complete rectangular
source-backed grids.

Later only: provider download, credentials, HTTP, fallback or routing; yfinance;
adjusted OHLCV; automatic old-manifest revalidation; schedule-equivalence
reconciliation; cross-module internal-error taxonomy and operator diagnostics;
corporate-action/comparability work; listings/latest pointers, deltas,
compaction, or generalized replay; membership, sector, events, news,
fundamentals, Sprint-16 qualification, Market Structure, recommendations, or
orders.

## Closed input and output

The sole operator input is canonical UTF-8 sorted-key JSON
`UpstoxRawHistoricalOhlcvCompletionRequestV1`:

```json
{
  "contract_version": "upstox-raw-fixed-cohort-historical-ohlcv-completion@v1",
  "revision_contract_version": "fixed-cohort-historical-ohlcv-upstox-raw-revision-store@v1",
  "research_scope": "FIXED_COHORT_RETROSPECTIVE",
  "source_profile": "UPSTOX_RAW",
  "operation": "INITIAL",
  "parent_revision_sha256": null,
  "correction_coordinates": [],
  "cohort": ["canonical listed-equity member with UPSTOX mapping evidence"],
  "from_session": "2026-07-01",
  "to_session": "2026-07-31",
  "interval": "1d",
  "expected_sessions": ["2026-07-01"],
  "schedule_evidence_sha256": "lowercase SHA-256",
  "observed_at": "2026-08-28T00:00:00Z",
  "permitted_use": "OWNER_PRIVATE_RESEARCH",
  "price_basis": "RAW",
  "schema_identity_sha256": "lowercase SHA-256",
  "runtime_code_identity_sha256": "lowercase SHA-256",
  "configuration_identity_sha256": "lowercase SHA-256",
  "limits": {
    "max_members": 50,
    "max_sessions": 366,
    "max_rows": 18300,
    "max_calendar_months": 12,
    "max_source_partitions": 600,
    "max_query_months_per_call": 12,
    "max_query_rows_per_call": 366,
    "max_artifact_bytes": 134217728,
    "max_source_policy_bytes": 1048576,
    "max_receipt_bytes": 1048576,
    "max_revision_bytes": 134217728,
    "max_lineage_depth": 128
  }
}
```

Members are ordered by `(isin, exchange)` and contain an effective NSE/EQUITY
symbol plus an `UPSTOX` provider mapping. Symbol and mapping intervals cover the
whole requested range. `mapping_evidence_known_at` and
`mapping_evidence_sha256` select exactly one retained snapshot observation; it
must resolve the same ISIN, symbol, instrument key, exchange, segment, and
instrument type. `expected_sessions` is nonempty, strictly increasing, bounded,
and exactly the retained schedule projection for the inclusive range.
`observed_at` is when this derived artifact is first claimed known, not a
historical publication time; every selected source timestamp is no later than it.
Each bar `known_at` is the maximum of the retained schedule `as_of`, selected
mapping retrieval, selected partition manifest update, and every contributing
minute candle ingestion timestamp; it never copies the request wall-clock.

Canonical JSON rejects duplicate keys, unknown fields, floats, NaN/infinity,
noncanonical bytes, and container depth 65. It permits at most 64 containers.
Dates are `YYYY-MM-DD`; operator instants are UTC whole-second `Z` instants;
retained source timestamps may carry exactly six UTC fractional digits. Prices
are canonical non-exponent decimal strings, volumes canonical nonnegative base-10
integer strings, and every digest is lowercase SHA-256.

The generated source policy is
`upstox-retained-raw-historical-ohlcv-source-policy@v1`; it binds source profile,
source/provider/version/interval, output interval, aggregation, raw basis/state,
temporal/corporate-action/comparability disclosures, permitted use, and exact
artifact digest. The generated artifact is
`upstox-retained-raw-historical-ohlcv-artifact@v1` with exact retained schedule,
member-major mapping receipts, member-major/month-major partition receipts, and
member-major/session-major raw bars. The generated receipt is
`upstox-retained-raw-historical-ohlcv-receipt@v1` and binds policy, artifact,
ordered receipt aggregates, schedule, observed/known time, and disclosures.

A mapping receipt binds the exact snapshot metadata, object paths and hashes,
resolved identity, and mapping time. A partition receipt binds the exact manifest
and physical plan, verification state, row count, Parquet checksum/path, source
version, lifecycle timestamps, failure state, and schedule digest. Admission
requires `VERIFIED` / `PASSED`, no failure category, `upstox`/`1m`, exact mapping,
exact path/checksum, source version, raw physical candles, complete retained
minutes/sessions, and no later ingestion. No dedupe, fill, adjustment, source
fallback, prior-session fallback, or inferred calendar is permitted.

The revision contains the closed request projection plus source policy/artifact/
receipt digests, raw disclosures, `completion_request_identity_sha256`, lineage
depth, context status, limitation, full bars, and `revision_sha256`. Every identity
is SHA-256 over the corresponding exact canonical preimage. The current write
schema identity is `fixed-cohort-historical-ohlcv-schema-identity@v2`: it binds
every field's semantic type, unit, nullability, and bounds alongside closed-object,
ordering, state, schedule, failure-precedence, byte-ceiling, and identity-exclusion
metadata. Writes and retries require current schema/runtime/configuration identities;
historical exact reads retain any structurally valid historical identity and bytes.

## Authority, filesystem, and lineage

1. Decode and validate the bounded request before a lock, tree mutation, provider,
   credential, or network access.
2. Admit distinct existing owner-private absolute no-follow source/destination
   roots; equality and ancestor/descendant relations are conflicts.
3. Acquire only the pre-existing source `.ingestion.lock`; never create source
   state.
4. Under that lease resolve the exact schedule/snapshot/manifests, verify pinned
   Parquet and aggregate bounded daily chunks.
5. Recheck root/catalog/schedule/partition identity; release the source lease.
6. Whole-candidate validation precedes destination authority. Publish with
   no-follow create-only no-clobber names and fsync each visibility transition;
   exact-read target lineage before success.

`INITIAL` has no parent/corrections and uses an empty destination or exact replay.
`APPEND` has a parent, byte-identical inherited cohort/mappings/basis/source and a
nonempty strictly later contiguous schedule suffix. `CORRECTION` has the same grid,
sorted unique nonempty coordinates, changed named rows only, replacement partition
proof, and immutable parent/source objects. Depth 128 is allowed; 129 and cycles
fail. Exact retry needs identical request, source identities/bytes, observed time,
and parent. Visible content-addressed names are never unlinked during cleanup.

Outcomes, in precedence order: `MALFORMED_INPUT`, `UNSUPPORTED_CAPABILITY`,
`CONFLICTING_EVIDENCE`, `INVALID_EVIDENCE`, `INSUFFICIENT_EVIDENCE`,
`PARENT_LINEAGE_CONFLICT`, `PUBLICATION_UNCERTAIN_OR_CONFLICT`, `SUCCESS`.
Malformed later input beats earlier missing evidence; unsupported profile/basis
beats invalid/missing source; conflict beats invalid/missing; invalid beats
missing; source insufficiency beats missing parent; parent conflict beats
destination contention.

CLI commands are exactly:

```text
historical-ohlcv-upstox-raw --request-file ABSOLUTE_PATH \
  [--source-storage-root ABSOLUTE_PATH] --storage-root ABSOLUTE_PATH --output json
historical-ohlcv-upstox-raw-read --storage-root ABSOLUTE_PATH \
  --revision-sha256 LOWERCASE_SHA256 --output json
```

The source root defaults to `~/SwingTradingAIAssistantData`; destination is a
separate existing owner-private root. The unreleased arbitrary-byte
`historical-ohlcv-import` and generic historical read commands do not exist.

## Frozen adversarial acceptance matrix

| Case family | Required result and prohibited effect |
|---|---|
| Valid one-member and homogeneous 50-member `INITIAL`; exact retry; exact read | Success, canonical member/session order, depth 0, exact bytes/revision; no duplicate publication, latest fallback, provider, yfinance, or source mutation. |
| Valid `APPEND` and `CORRECTION` | Success only for exact suffix or named changed coordinates; parent and unnamed bars remain byte-identical. |
| Canonical hostile input; duplicate/unsorted cohort/sessions/coordinates; zero/51 members; every bound and bound+1 | `MALFORMED_INPUT`; no source/destination lease, allocation beyond bound, or publication. |
| Wrong profile/provider/interval/source version; adjusted/legacy basis; yfinance or mixed raw/adjusted candidate | `UNSUPPORTED_CAPABILITY`; no alias, fallback, yfinance call, or partial raw revision. |
| Missing snapshot/schedule/manifest/closed partition/minute/session; in-progress/failed/provisional partition; held source lock | `INSUFFICIENT_EVIDENCE`; no guessed calendar, download, repair, promotion, credentials, destination work, or source mutation. |
| ISIN/symbol/key/snapshot-digest/manifest/checksum/path/source-version/schedule substitution; duplicate minute/session/bar; root/catalog identity change | `CONFLICTING_EVIDENCE`; no fallback, dedupe, quarantine, repair, equivalence override, candidate, or publication. |
| Mixed physical states | `UNSUPPORTED_CAPABILITY`; no partial raw subset. Nonfinite/negative/envelope-invalid price or nonintegral/overflow volume | `INVALID_EVIDENCE`; no tolerance, rounding, clipping, or repair. |
| Combined malformed/unsupported/conflict/invalid/missing/parent cases | Apply the stated global precedence; no partial output. |
| Missing/divergent parent; append overlap/gap/reorder/shrink/old change; invalid correction; depth/cycle | `PARENT_LINEAGE_CONFLICT` (or malformed at structural stage); parent remains unchanged. |
| Source/destination root equality/containment, symlink/group-access/substitution, held destination lock, projection/publication faults/retry | Conflict or publication-uncertain outcome as classified; no traversal, unsafe unlink, misleading success, or partial new revision. Retain any already-visible content-addressed object. |
| Historical compatibility | Pre-owner adjusted artifact remains unsupported; later runtime exact-reads raw historical revision; successor binds current identities without changing parent. |
| Retained real evidence | RELIANCE July succeeds with 23 rows including 2026-07-01 `1298.9/1312.2/1296.5/1306.5/6999059` and 2026-07-31 `1295/1309.7/1293.6/1305/8622344`; current July full-50 fails `CONFLICTING_EVIDENCE` for the 49/1 schedule digest split; current August fails `INSUFFICIENT_EVIDENCE` because only provisional evidence exists. |

The profile runtime identity is a source-at-rest closed manifest over at least the
raw projector, revision store, daily/coverage/query contracts, catalog, instrument
snapshot, schedule evidence, lifecycle/planner, Parquet/candles, lease, and
runtime verifier. It is refreshed only from formatted final source bytes.
