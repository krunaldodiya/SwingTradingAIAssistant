# Sector Participation v1 implementation contract

Status: **IMPLEMENTED CORE — REVIEW AND PUBLICATION PENDING**

Contract: `nifty50-sector-participation@v1`

Implementation:

- `src/swing_trading_ai_assistant/market_regime/observed.py`
- `src/swing_trading_ai_assistant/sector_analysis/participation.py`
- `src/swing_trading_ai_assistant/sector_analysis/__init__.py`

## Accepted module evaluation

- **Expected value:** deterministic source-label participation counts.
- **Scope fit:** locked Module 2 / Nifty 50.
- **Risk:** an opaque label is not an official taxonomy, and the private handoff could leak member-level evidence.
- **Smallest alternative:** a provider-free in-process aggregate with a fail-closed result.
- **Decision:** accept the implemented core; defer official taxonomy and Layer B.

## Purpose and non-claims

V1 answers one question: for the exact 50 members already classified by one
observed `nifty50-market-regime@v1` analysis pass, how many `ADVANCE`, `DECLINE`,
and `UNCHANGED` directions fall under each opaque label in one already-resolved
point-in-time Nifty 50 universe snapshot?

The labels are copied as opaque source labels. V1 does not claim that they are an
official NSE Sector tier, infer a taxonomy, rank sectors, recommend a trade,
produce a live market result, or establish predictive or investment
effectiveness. The contract adds no source acquisition, provider integration,
CLI, API, MCP, or public member-level surface.

The aggregate remains owner-private because its upstream handoff contains exact
member identities and directions. Only the aggregate report or one redacted
whole-result insufficiency may leave the reducer boundary.

## Existing inputs

The public reducer is deliberately small:

```python
reduce_sector_participation_v1(
    market_regime_facts_or_insufficiency: object,
    resolved_snapshot: object,
) -> SectorParticipationReportV1 | SectorParticipationInsufficiencyV1
```

It accepts these two already-constructed outcomes and no others:

| Slot | Accepted types | Meaning |
|---|---|---|
| `market_regime_facts_or_insufficiency` | Exact `VerifiedMarketRegimeFactsV1`, exact `MarketRegimeInsufficiencyV1`, or `None` | Trusted observed facts to reduce in this call, or an unavailable upstream result. |
| `resolved_snapshot` | Exact `ResolvedNifty50UniverseSnapshotV1`, `UniverseSnapshotNotFoundError`, `UniverseSnapshotStaleError`, `UniverseSnapshotAmbiguousError`, `UniverseSnapshotCorruptError`, or `None` | One already-resolved PIT snapshot outcome. |

Exact verified facts cause the unchanged public Market Regime report and its
private handoff to be derived and consumed internally in the same reducer call.
An insufficiency or `None` maps to unavailable Market Regime evidence. A caller
cannot submit a report or handoff, including a private handoff reconstructed
from internal types.

The reducer does not accept paths, bytes, requests, provider clients, storage
roots, caller-created untyped mappings, or a caller-supplied report/handoff.

## Same-pass private handoff

`_reduce_observed_market_regime_with_sector_handoff_v1` is a private producer
used only inside `reduce_sector_participation_v1`. For exact verified facts, it
produces the public `MarketRegimeReportV1` and private
`_MarketRegimeSectorHandoffV1` from the same underlying observed reduction pass;
the public reducer consumes that pair immediately and does not recompute or
reread member directions downstream.

A valid handoff is immutable and must:

- contain exactly 50 unique members, canonically sorted by ISIN;
- carry only the closed directions `ADVANCE`, `DECLINE`, and `UNCHANGED`;
- bind the report/input/policy/code identities, comparison and decision
  sessions, decision close, and evidence cutoff to the paired report;
- reconcile each direction total exactly to the corresponding Market Regime
  total; and
- have a valid canonical SHA-256 handoff identity.

The handoff is not a public input. If the private producer ever returns a
malformed or inconsistent report/handoff pair, reduction stops with a sanitized
structural `ValueError`; this is not a domain insufficiency reason. An
impossible handoff shape cannot be constructed.

## Resolved PIT opaque-label snapshot

The second public input is the existing
`ResolvedNifty50UniverseSnapshotV1`, containing validated metadata plus a
`Nifty50UniverseSnapshotV1`. Each constituent already
has an ISIN and a syntactically safe opaque `sector` label. Sector Participation
does not resolve, refresh, download, reinterpret, or assign those labels.

Admission requires all of the following:

1. metadata and snapshot are the exact existing types;
2. metadata byte count and SHA-256 match the snapshot's canonical bytes;
3. metadata fields bind exactly to the snapshot fields;
4. the report decision session lies inside the snapshot effective interval;
5. membership and sector publication/retrieval timestamps are not after the
   report evidence cutoff; and
6. the snapshot and handoff contain the same exact set of 50 ISINs.

The join key is exact ISIN. There is no symbol join, aliasing, label inference,
or partial join.

## Deterministic output and equations

For every distinct opaque label `s`, define:

- `M_s`: exact joined members whose snapshot label is `s`;
- `A_s`, `D_s`, `U_s`: members of `M_s` whose handoff direction is respectively
  `ADVANCE`, `DECLINE`, or `UNCHANGED`; and
- `N_s = |M_s|`.

The reducer must satisfy:

```text
N_s = A_s + D_s + U_s
sum_s N_s = 50
sum_s A_s = market_report.advances
sum_s D_s = market_report.declines
sum_s U_s = market_report.unchanged
```

`SectorCountV1` contains `label`, `member_count`, `advances`, `declines`, and
`unchanged`. Rows are unique and sorted ascending by the exact label string.
Every label has length 1 through 64 and matches the implemented safe-label
alphabet; every count is an integer within 0 through 50, and `member_count` is
within 1 through 50.

An observed `SectorParticipationReportV1` contains:

- contract/calculation versions;
- request and Market Regime report identities;
- the implemented deterministic SHA-256 identity fields that bind accepted
  inputs, inherited policies, calculation code, and the complete report;
- comparison/decision sessions, decision close, and evidence cutoff;
- `required_member_count = 50`, `evidence_state = "OBSERVED"`;
- the canonical sector rows; and
- `primary_reason = None`, `additional_reasons = ()`.

All identities are SHA-256 values over domain-separated canonical JSON-plus-LF
projections of the accepted in-memory inputs and output. The report identity
covers the complete report projection other than its own identity.
`canonical_json_bytes()` enforces the existing 64 KiB serialized-report bound.
These digests make no external authority, runtime, or publication claim.

## Whole-result insufficiency

A well-typed but unusable input returns exactly one
`SectorParticipationInsufficiencyV1`:

```text
evidence_state = "INSUFFICIENT_EVIDENCE"
sectors = None
primary_reason = first applicable reason in declaration order
additional_reasons = remaining unique applicable reasons in declaration order
```

The closed global order is:

1. `MARKET_REGIME_UNAVAILABLE`
2. `SECTOR_CLASSIFICATION_MISSING`
3. `SECTOR_CLASSIFICATION_STALE`
4. `SECTOR_CLASSIFICATION_AMBIGUOUS`
5. `SECTOR_CLASSIFICATION_CORRUPT`
6. `SECTOR_EFFECTIVE_SCOPE_MISMATCH`
7. `EVIDENCE_CUTOFF_MISMATCH`
8. `MEMBER_IDENTITY_MISMATCH`

No invalid case emits a partial sector row, upstream reason, member identifier,
direction, source exception detail, or observed-result implication.

## Structural boundary versus domain failure

These outcomes are intentionally distinct:

| Class | Examples | Result |
|---|---|---|
| Structural misuse | wrong top-level type; malformed typed object; inconsistent resolved metadata/snapshot structure or digest; inconsistent internally produced report/handoff pair | sanitized `TypeError` or `ValueError`; no domain report |
| Domain insufficiency | unavailable Market Regime; missing/stale/ambiguous/corrupt snapshot outcome; effective/cutoff mismatch; exact-50 ISIN-set mismatch | one redacted whole-result insufficiency |
| Accepted observation | exact verified facts, reduced internally to a paired same-pass report and private handoff, plus one valid resolved snapshot | one canonical aggregate-only observed report |

Structural exceptions contain stable boundary text rather than the rejected
private value. Domain insufficiency deliberately collapses upstream detail into
the closed Sector Participation reason set.

## Purity, privacy, and redaction

The reducer is a zero-I/O in-process function. It performs validation, exact
joining, counting, sorting, canonical serialization for identities, and hashing
only. It does not read or write files, resolve a snapshot, access a provider,
use the network, mutate a data root, log private evidence, or publish a result.

Observed serialization and `repr` expose aggregate rows, inherited session
metadata, versions, and digests, but not ISINs, symbols, per-member directions,
raw closes, upstream fact objects, or private handoff objects. Insufficiency
exposes only its state and closed reasons.

## Implemented acceptance

The implemented core is accepted for review when all of these remain true:

- exact verified Market Regime facts internally produce an unchanged public
  report plus one exact-50 immutable private handoff, and that pair is consumed
  in the same public reducer call;
- no caller can submit a report or handoff through the public API;
- one already-resolved PIT snapshot maps the same 50 ISINs exactly once;
- output rows are deterministic opaque-label counts satisfying every equation;
- input permutations preserve canonical output;
- every admitted domain defect fails closed with `sectors = None`;
- malformed structure raises a sanitized boundary error rather than becoming a
  misleading insufficiency;
- no member-level value appears in report, insufficiency, or error surfaces; and
- the reducer adds no I/O or external integration.

## Explicitly deferred

The following are not part of the implemented core:

- proof or acquisition of an official historical NSE Sector taxonomy;
- any provider, download, refresh, storage, or retained-evidence workflow;
- Layer B acquisition/readiness and its private-delivery controls;
- CLI, API, MCP, or another delivery transport;
- a recommendation, ranking, live observed market result, backtest, or
  effectiveness claim; and
- publication or Sprint 8 closure evidence.
