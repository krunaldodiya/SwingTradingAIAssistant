# Current supplied-cohort Industry Analysis contract

Status: **IN PROGRESS — RECEIPT-PERSISTED CANDIDATE LOCALLY VERIFIED; FRESH EXACT-SHA REVIEW AND DELIVERY PENDING** — [Issue #117](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/117)

Contract revisions:

- `current-supplied-cohort-industry-classification@v1`
- `current-supplied-cohort-industry-participation@v1`

Risk: **R3 / High** — current financial-research fact integrity, immutable owner-private evidence, source/licence limits, and a new aggregate public fact contract

Outcome owner and acceptance authority: **repository owner through Issue #117 and its recorded source and first-working-boundary decisions**

Depends on: [Plan 20](20-current-supplied-cohort-market-regime-contract.md), the closed Sprint 11 Market Regime V2 comparability result, and the owner-private retained-data boundary

Preserves: frozen [Plan 14](14-sector-participation-contract.md) `nifty50-sector-participation@v1`, historical exact-50 evidence, and future [Plan 23](23-instrument-agnostic-feature-boundary-and-coupling-audit.md) migrations

## Authority and lifecycle

Issue #117 authorizes the first current supplied-cohort classification and
participation slice. Its 2026-08-22 source decision accepts one operator-acquired
official NSE Indices artifact for owner-private noncommercial research and rejects
a network scraper, redirect, alternate source, and fallback. Its later owner
decision selects **official NSE Indices `Industry` labels, current same-session
only**.

This contract uses the source field's literal `Industry` meaning. It never calls
that field the official NSE Indices `Sector` tier and never claims that an
Industry label is one of an official 22-value Sector taxonomy. The architecture
module remains Sector Analysis because that is the locked pipeline module; the
new data and result contracts are named **Industry classification** and
**Industry participation** so their evidence claim remains truthful.

Sprint 12 and Issue #117 are **IN PROGRESS — RECEIPT-PERSISTED CANDIDATE
LOCALLY VERIFIED; FRESH EXACT-SHA REVIEW AND DELIVERY PENDING**. The prior
exact-SHA R3 review returned `REQUEST_CHANGES` / `FAIL` for missing deterministic
receipt persistence/recovery and stale lifecycle records. All earlier
repair-round reviews and gate evidence are superseded trace. The seventh repair
persists one deterministic canonical retained receipt binding `known_at`, all
required identities, and the exact private rows; a retry in a new process
reconstructs the original retained evidence and rejects a missing, corrupt, or
spliced receipt.

Focused verification passed 105 tests. Full local gates passed 2,982 tests at
90.82% coverage, Ruff format/check, Pyright, Vulture 80, and build. The unchanged
official parser smoke admitted the exact current 100-row, 6,610-byte artifact
with SHA-256 `5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85`
under classification schema
`7bc49d5eac26551c9ae0b76b4dd7b9edf9861ccca7d73fb7ea04f6c4f72f0415`;
it is parser provenance only, not live participation or effectiveness evidence.
Fresh exact-SHA independent quality `APPROVE` and security `PASS` and delivery
remain pending. The exact reviewed SHA will be recorded externally after review;
this contract intentionally contains no self-referential candidate SHA. Pull
request, hosted CI/GitGuardian, merge, live participation result, and Issue
closure remain pending.

## Accepted source evaluation

1. **Expected value:** official current NSE Indices Industry labels enable deterministic participation counts for the exact current supplied cohort.
2. **Scope fit:** NSE/NSE Indices is the classification authority; Upstox's instrument master has no Industry field, and yfinance and Angel One are not accepted taxonomy authorities for this slice.
3. **Material risk:** bounded personal/noncommercial use with attribution is accepted for the owner-private workflow, but automated harvesting and redistribution authority are not established; raw rows remain private and uncommitted.
4. **Smallest alternative:** parse and retain one operator-acquired exact official CSV, project its rows to the supplied cohort, and expose aggregate Industry counts only.
5. **Decision — accepted:** build the provider-neutral current-only core and exact artifact parser; defer automated acquisition, alternate sources, official Sector taxonomy, and all historical classification work.

## Outcome and non-claims

The working slice answers one current question: for the exact `1..50` member
cohort admitted by current Market Regime V2, how many `ADVANCE`, `DECLINE`, and
`UNCHANGED` member directions fall under each official NSE Indices `Industry`
label in one artifact known before the decision cutoff on the same IST exchange
session date?

It produces either:

- one immutable retained private exact-cohort Industry classification plus one
  deterministic aggregate-only observed Industry Participation report; or
- one whole-result `MALFORMED_EVIDENCE`, `UNSUPPORTED_CAPABILITY`, or
  `INSUFFICIENT_EVIDENCE` result with closed ordered reasons and no Industry
  rows.

It does not claim:

- official NSE Indices Sector classification;
- historical or point-in-time-before-acquisition taxonomy;
- Nifty 50, Nifty Next 50, or Nifty 100 membership for the supplied cohort;
- coverage for every listed equity;
- a ranking, score, forecast, signal, recommendation, order, or effectiveness
  result; or
- permission to publish or redistribute the source artifact or member rows.

## Exact source and artifact contract

### Fixed source

The only admitted source location is the exact literal URL:

```text
https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv
```

The source authority is exactly `NSE_INDICES`, the source domain is exactly
`www.niftyindices.com`, and acquisition method is exactly
`OPERATOR_ACQUIRED`. The runtime receives already-acquired bytes; it has no URL
client or transport port. It must not request the URL, follow a redirect, accept
a URL variant, normalize to another host/path, retry, scrape a page, or use an
alternate source.

The URL and owner acquisition assertion establish the approved owner-private
workflow boundary; they are not cryptographic publisher-origin attestation. The
artifact SHA-256 binds the supplied bytes but proves neither publisher authority
nor publication time.

### Exact CSV shape

The admitted artifact is a bounded UTF-8 comma-delimited CSV with no byte-order
mark. Its first record contains exactly these five fields in this order and with
this spelling:

```text
Company Name,Industry,Symbol,Series,ISIN Code
```

Admission requires:

1. exactly one header record and exactly 100 data records;
2. exactly five fields in every record, with no missing or extra field;
3. no malformed quoting, undecodable byte, NUL, character outside the strict
   versioned Unicode profile, embedded record break, duplicate header, or
   trailing non-record content;
4. a nonempty trimmed `Company Name`, `Industry`, `Symbol`, and `Series` in every
   row, where the parsed value equals its source spelling after the contract's
   exact surrounding-space rejection—values are not silently trimmed or
   rewritten;
5. `Series == "EQ"` for every admitted row;
6. one syntactically and checksum-valid uppercase ISIN in `ISIN Code`;
7. 100 unique ISINs and 100 unique `(Symbol, Series)` pairs;
8. no conflicting duplicate identity or Industry assignment; and
9. raw bytes within the versioned maximum byte bound and parsed text/field
   lengths within versioned finite bounds.

The exact numeric byte and field limits must be frozen in the RED tests and
schema identity before implementation; they may not be read from caller input.
The parser uses the standard-library CSV capability only. No dataframe,
spreadsheet formula evaluation, schema inference, locale transform, fuzzy
header match, label mapping, or new dependency is admitted.

`Industry` is copied as an opaque official source label after strict lexical
admission. The parser does not map it to Sector, combine labels, split labels,
infer a hierarchy, or repair spelling. Cross-row privacy admission rejects an
Industry label containing any admitted source row's full ISIN, complete symbol
token, or Company Name. Company Name matching is boundary-free containment across
all 100 source rows after this exact privacy key:
`unicodedata.normalize("NFKC", value.casefold())`. The same deep identity-label
check is reused when retained private rows are revalidated. Complete Company Name
rejection occurs before private-row projection and is frozen in classification
schema identity `7bc49d5eac26551c9ae0b76b4dd7b9edf9861ccca7d73fb7ea04f6c4f72f0415`.

### Artifact identity and revision

The owner-private input binds:

- exact source URL, authority, domain, acquisition method, and `INDUSTRY` tier;
- raw artifact byte count;
- `artifact_sha256 = SHA-256(raw artifact bytes)`;
- `artifact_revision = "sha256:<artifact_sha256>"`;
- literal null publisher publication/effective fields; and
- the classification schema, licence-policy, and input identities.

Trusted `known_at` is not classification input or projection evidence. Retention
creates and binds it only after final archive verification.

`artifact_revision` is a local immutable content revision, not a publisher
revision. No publisher revision is invented. A hash mismatch, byte-count
mismatch, wrong fixed source binding, or unsupported tier prevents projection.

## Temporal and freshness contract

The official CSV supplies no admitted publisher publication timestamp and no
admitted effective interval. These fields remain explicit and literal:

```text
publisher_published_at = null
publisher_effective_from = null
publisher_effective_through = null
publisher_revision = null
```

`known_at` is a conservative trusted UTC archive-completion timestamp generated
only by `FileCurrentIndustryArchiveV1` after final archive verification. The
implementation/spec chooses archive completion—not an owner-approved
acquisition-time assertion—for fail-closed look-ahead safety. Classification
input, parsing, and projected snapshots are timeless: they neither accept nor
expose `known_at`, `decision_session`, or `decision_cutoff`. Retention alone adds
`known_at`; it is not renamed or copied into any publisher field.

The current Market Regime V2 report owns the already validated
`decision_session` and `decision_cutoff`. The Industry Participation boundary
compares those fields with the retained classification:

```text
known_at <= decision_cutoff
IST_DATE(known_at) == IST_DATE(decision_cutoff)
IST_DATE(known_at) == decision_session
```

`IST_DATE` means conversion of an aware UTC instant to `Asia/Kolkata` followed
by its local calendar date. A natural Market Regime V2
`INSUFFICIENT_EVIDENCE` result retains a trustworthy common envelope: its
contract/schema/calculation/runtime/report/raw-report identities, cohort
identity and size, decision session and cutoff, and nonempty reasons remain
valid, while comparison session, regime label, and direction counts are null
and no private handoff exists. Common-envelope admission is independent of
observed-success admission. When that envelope is valid, the participation
reducer merges `MARKET_REGIME_UNAVAILABLE` with independently applicable
retained-classification `COHORT_BINDING_MISMATCH`,
`CLASSIFICATION_FUTURE_KNOWN`, and `CLASSIFICATION_SESSION_STALE` reasons.
Classification does not choose a session, cutoff, or calendar.

Because trusted `known_at` records final archive completion, acquisition before
the decision cutoff alone has no temporal authority. A retention that completes
after the cutoff produces `known_at > decision_cutoff` and is therefore rejected
as `CLASSIFICATION_FUTURE_KNOWN` even when acquisition preceded the cutoff. A
`known_at` on any earlier or later IST date is
`CLASSIFICATION_SESSION_STALE`. Neither case permits a prior artifact, retry,
reduced denominator, or inferred effective date. This conservative consequence
is intentional: only final verified retention can establish when the evidence
became usable.

This is a deliberately narrow current-observation rule. Evidence can never
support a decision before `known_at`, another exchange date, a historical
reconstruction, or a backtest. Future historical work must use a separately
approved source and versioned availability/effective-time contract.

## Exact supplied-cohort projection

The classification core consumes the exact current Market Regime V2 cohort
identity and finite member set. Its bound is the current Market Regime V2 exact
cohort bound:

```text
1 <= cohort_size <= 50
```

The core performs no Nifty membership resolution or check. The fixed official
artifact contains its complete 100-row source coverage; rows not requested by
the supplied cohort remain private source rows and are not output or treated as
an error. The projected snapshot, however, must contain exactly one row for
every supplied member and no row outside that supplied cohort.

Admission is exact:

- join by uppercase ISIN only;
- the Market Regime private handoff remains the authority for the already-admitted
  member identity, exchange, effective symbol, and cohort binding;
- every supplied member must have exactly one matching source row;
- every projected ISIN must belong to the supplied cohort exactly once;
- source symbol is supporting consistency evidence only, must bind exactly to
  the already-admitted effective symbol, and is never a fallback join key;
- BSE members are `CLASSIFICATION_MEMBER_UNSUPPORTED` because this source is the
  NSE `EQ` capability; and
- an absent ISIN, including an explicitly supplied supported equity outside the
  artifact's coverage, is `CLASSIFICATION_MEMBER_UNSUPPORTED` without an index
  membership claim.

Unsupported or unusable members are never dropped. The denominator is never
reduced. There is no partial snapshot or partial aggregate.

A successful immutable private projected snapshot binds:

- contract/schema/parser-code identities;
- complete owner input and fixed-source descriptor identity;
- artifact byte count, digest, and local revision;
- literal `INDUSTRY` tier;
- explicit null publisher fields;
- cohort identity and size;
- canonical sorted `(isin, industry)` private rows; and
- its complete snapshot identity.

## Immutable private archive

Raw artifact bytes and the canonical exact-cohort snapshot must be retained under
one already-admitted owner-private storage root before an observed participation
report can exist. They are uncommitted runtime evidence, not repository fixtures
or package data.

The archive is content-addressed and immutable:

- raw object identity is its SHA-256;
- canonical snapshot identity binds the raw object identity and every snapshot
  field;
- the admitted storage root and archive directory are owner-private, files are
  private regular single-link objects, and all opens are no-follow through
  `StorageRootLease.root_operation(root)`;
- the first archive verifies raw and snapshot bindings, samples trusted UTC
  completion time, seals a retained result, and publishes under the deterministic
  no-replace name `retained-<snapshot_identity_sha256>.json` a private canonical
  receipt binding `known_at`, archive-receipt, retained, schema, runtime, input,
  artifact, snapshot, and archive identities plus every exact private cohort row
  required for reconstruction;
- writes use private temporary objects, flush data, fsync newly accepted
  directories and their owner-private root binding, publish without replacement,
  then stable-read and revalidate raw, snapshot, and receipt named bindings, the
  directory binding, and live lease before success;
- a retry or new archive process reads and deeply validates that exact receipt
  before returning its original `known_at` and identities; a missing, corrupt,
  or spliced deterministic receipt is `CLASSIFICATION_ARCHIVE_FAILED`; and
- publishing identical bytes is idempotent, including concurrent acceptance;
- an existing different object, unsafe link/type/mode, path replacement,
  unstable read, size violation, failed flush, or failed final verification is
  `CLASSIFICATION_ARCHIVE_FAILED`; and
- no directory scan, nearest-object selection, mutable current pointer, overwrite,
  deletion, or fallback archive is allowed.

Retention is the sole owner of trusted `known_at`; it binds that timestamp into
the retained identity only after successful final archive verification.

Archive paths, descriptors, raw bytes, raw rows, member classifications, and
member identities never enter the aggregate result or sanitized diagnostics.
The public result may expose only the opaque artifact, snapshot, and archive
object identities required for provenance.

## Private same-pass Market Regime V2 handoff

The existing public
`evaluate_current_supplied_cohort_market_regime_v2` returns an aggregate-only
report. Sprint 12 adds one private paired evaluator inside
`market_regime/current_supplied_cohort_v2.py`:

```python
def _evaluate_current_supplied_cohort_market_regime_with_handoff_v2(
    raw_v1_report: CurrentSuppliedCohortMarketRegimeReportV1,
    raw_private_grid: PrivateCurrentCohortArchiveGridProjectionV1,
    retained_screen: PublishedCurrentCorporateActionScreenV1,
    adjusted_handoff: AdjustedDailyCloseHandoffV2,
) -> tuple[
    CurrentSuppliedCohortMarketRegimeReportV2,
    _CurrentSuppliedCohortMemberDirectionHandoffV2 | None,
]: ...
```

The existing public evaluator delegates to that private function and discards
the handoff. Sector Analysis calls the same private function and consumes the
pair immediately. It must not call the public evaluator and then recompute
member directions.

The private handoff exists only when the paired V2 report is `OBSERVED`. It is
immutable, canonically sorted by ISIN, contains exactly `cohort_size` unique
members, carries only `ADVANCE`, `DECLINE`, and `UNCHANGED`, and binds:

- paired Market Regime report, calculation, runtime, raw-report, screen, and
  adjusted-handoff identities;
- cohort identity and size;
- decision/comparison sessions and cutoff;
- each already-admitted member's ISIN, exchange, effective symbol, and direction;
- exact reconciliation to the paired public advances, declines, and unchanged;
  and
- its own canonical handoff identity.

A V2 insufficiency produces `handoff = None`. The handoff has no public parser,
serializer, package-root export, caller input, file representation, archive, CLI,
API, or MCP surface. A caller-supplied or reconstructed handoff is never
accepted.

The public V2 report schema and calculation remain the Plan-20 contract. Its
source-at-rest runtime identity and therefore report identity legitimately
change when reviewed source bytes and the runtime manifest change; no byte
identity across implementations is claimed. Frozen Market Regime V1 and Sector
Participation V1 code, canonical bytes, identities, and historical evidence
remain unchanged.

## Deterministic Industry Participation

For each exact Industry label `i`:

```text
N_i = A_i + D_i + U_i
sum_i N_i = cohort_size
sum_i A_i = market_regime.advances
sum_i D_i = market_regime.declines
sum_i U_i = market_regime.unchanged
```

`IndustryCountV1` contains exactly `industry`, `member_count`, `advances`,
`declines`, and `unchanged`. Rows are unique and sorted ascending by the exact
Industry string. Equivalent permitted source/cohort input permutations preserve
the canonical aggregate order and counts; the raw artifact identity still binds
the exact acquired bytes.

An observed `CurrentIndustryParticipationReportV1` contains:

- contract, schema, calculation, and runtime code identities;
- Market Regime report and private-handoff identities;
- classification input, artifact, snapshot, and archive identities;
- cohort identity and size;
- decision/comparison sessions and cutoff;
- exact source URL and `NSE_INDICES` attribution;
- `classification_tier = "INDUSTRY"`;
- artifact revision and `known_at`;
- explicit null publisher publication/effective/revision fields;
- `evidence_state = "OBSERVED"`;
- canonical aggregate Industry rows;
- no reasons; and
- complete report identity.

It contains no ISIN, symbol, exchange, provider mapping, member direction, raw
row, company name, raw artifact, archive path, or private handoff representation.
Aggregate output is not claimed anonymous. No public delivery transport is added
in this slice.

## Failure states, closed reasons, and precedence

After structural boundary admission, the public result uses exactly these states:

```text
OBSERVED
MALFORMED_EVIDENCE
UNSUPPORTED_CAPABILITY
INSUFFICIENT_EVIDENCE
```

Every non-observed result has `industries = null`, a nonempty ordered reason
tuple, and no partial count or member detail. Structural misuse before a domain
result exists—wrong top-level Python type, invalid canonical owner input,
unsupported contract/schema version, unsafe storage-root authority, or runtime
identity failure—raises a sanitized `TypeError` or `ValueError`; it is not
laundered into missing evidence.

Applicable reasons are deduplicated and rendered in this exact order:

```text
1.  MARKET_REGIME_UNAVAILABLE
2.  CLASSIFICATION_ARTIFACT_MISSING
3.  CLASSIFICATION_ARTIFACT_MALFORMED
4.  CLASSIFICATION_SOURCE_UNSUPPORTED
5.  CLASSIFICATION_TIER_UNSUPPORTED
6.  CLASSIFICATION_MEMBER_UNSUPPORTED
7.  CLASSIFICATION_AMBIGUOUS
8.  CLASSIFICATION_CONFLICTING
9.  COHORT_BINDING_MISMATCH
10. MEMBER_IDENTITY_MISMATCH
11. CLASSIFICATION_FUTURE_KNOWN
12. CLASSIFICATION_SESSION_STALE
13. CLASSIFICATION_ARCHIVE_FAILED
```

Reason-to-state mapping is closed:

| Reasons | Result state |
| --- | --- |
| `CLASSIFICATION_ARTIFACT_MALFORMED`, `CLASSIFICATION_AMBIGUOUS`, `CLASSIFICATION_CONFLICTING`, `COHORT_BINDING_MISMATCH`, `MEMBER_IDENTITY_MISMATCH` | `MALFORMED_EVIDENCE` |
| `CLASSIFICATION_SOURCE_UNSUPPORTED`, `CLASSIFICATION_TIER_UNSUPPORTED`, `CLASSIFICATION_MEMBER_UNSUPPORTED` | `UNSUPPORTED_CAPABILITY` |
| `MARKET_REGIME_UNAVAILABLE`, `CLASSIFICATION_ARTIFACT_MISSING`, `CLASSIFICATION_FUTURE_KNOWN`, `CLASSIFICATION_SESSION_STALE`, `CLASSIFICATION_ARCHIVE_FAILED` | `INSUFFICIENT_EVIDENCE` |

When reasons from different states are independently applicable, result-state
precedence is `MALFORMED_EVIDENCE`, then `UNSUPPORTED_CAPABILITY`, then
`INSUFFICIENT_EVIDENCE`. Reason rendering always follows the global order above.
Stages suppress dependent noise: absent bytes do not also claim malformed
content; malformed content is not projected; unsupported members do not also
claim an identity mismatch; archive publication runs only after a valid exact
snapshot; participation runs only after verified retention.

## Authoritative Python surface

The implementation candidate's classification surface is only
`swing_trading_ai_assistant.market_data.current_industry_classification`:

```python
class CurrentIndustryClassificationInputV1:
    @classmethod
    def from_canonical_json_bytes(
        cls, raw: bytes
    ) -> CurrentIndustryClassificationInputV1: ...

    def canonical_json_bytes(self) -> bytes: ...


def parse_current_industry_artifact_v1(
    input: CurrentIndustryClassificationInputV1,
    artifact: bytes | None,
) -> ParsedCurrentIndustryArtifactV1 | CurrentIndustryClassificationFailureV1: ...


def project_current_supplied_cohort_industry_v1(
    parsed: ParsedCurrentIndustryArtifactV1,
    cohort_identity_sha256: str,
    cohort_members: tuple[CurrentIndustryCohortMemberV1, ...],
) -> PrivateCurrentIndustrySnapshotV1 | CurrentIndustryClassificationFailureV1: ...


class FileCurrentIndustryArchiveV1:
    def __init__(self, root: Path) -> None: ...


class CurrentIndustryArchivePortV1(Protocol):
    def archive_exact(
        self,
        input: CurrentIndustryClassificationInputV1,
        artifact: bytes,
        snapshot: PrivateCurrentIndustrySnapshotV1,
        lease: StorageRootLease,
    ) -> RetainedCurrentIndustrySnapshotV1 | CurrentIndustryClassificationFailureV1: ...
```

At this structural boundary, `artifact` is exact `bytes` or literal `None`.
`None` returns typed `CLASSIFICATION_ARTIFACT_MISSING`; every other top-level
artifact type raises sanitized `TypeError` before domain classification.

`CurrentIndustryCohortMemberV1` is a narrow private projection of already-admitted
Market Regime V2 member identity. It carries ISIN, exchange, and effective symbol
only; it is not a second provider mapping or universal canonical-equity model.

The implementation candidate's aggregate surface is only
`swing_trading_ai_assistant.sector_analysis.current_industry_participation`:

```python
def reduce_current_industry_participation_v1(
    raw_v1_report: CurrentSuppliedCohortMarketRegimeReportV1,
    raw_private_grid: PrivateCurrentCohortArchiveGridProjectionV1,
    retained_screen: PublishedCurrentCorporateActionScreenV1,
    adjusted_handoff: AdjustedDailyCloseHandoffV2,
    classification: RetainedCurrentIndustrySnapshotV1
        | CurrentIndustryClassificationFailureV1,
) -> CurrentIndustryParticipationReportV1
    | CurrentIndustryParticipationFailureV1: ...
```

Before paired Market Regime evaluation, the reducer exact-type guards all five
top-level arguments shown above. A wrong top-level type raises sanitized
`TypeError` before evaluation and never returns a domain report; separately,
invalid canonical owner input raises sanitized `ValueError` at its owning
structural boundary.

The reducer accepts neither a caller-supplied Market Regime V2 report nor a
caller-supplied member-direction handoff. It performs no source, provider,
network, filesystem, archive, clock, universe, or index-membership operation.
No compatibility alias, alternate parser, generic source registry, or package-root
Market Regime handoff export is permitted.

## Exact implementation candidate file set

The implementation candidate is limited to:

```text
src/swing_trading_ai_assistant/market_data/current_industry_classification.py
src/swing_trading_ai_assistant/market_data/current_industry_classification_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py
src/swing_trading_ai_assistant/market_data/runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_v2.py
src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_v2_runtime_identity_manifest.py
src/swing_trading_ai_assistant/sector_analysis/current_industry_participation.py
src/swing_trading_ai_assistant/sector_analysis/current_industry_participation_runtime_identity_manifest.py
src/swing_trading_ai_assistant/sector_analysis/__init__.py
tests/market_data/test_current_industry_classification.py
tests/market_regime/test_current_supplied_cohort_v2.py
tests/sector_analysis/test_current_industry_participation.py

No dependency or provider-adapter file is added. No CLI/API/MCP transport is in
scope. Any additional production file requires a concrete contract obligation
and an update to this plan before implementation.

## Runtime code identity

Classification snapshots and aggregate reports bind independently reviewed
source-at-rest runtime identities. Each manifest is a nonrecursive exact mapping
from every and only its ordered inventory paths to lowercase SHA-256 values. The
manifest does not map itself; the composite includes the verified manifest file
digest as the final path-NUL-digest entry.

The classification inventory binds its classification module, shared
runtime-source verifier, and storage-root lease boundary; its composite
additionally binds the verified classification manifest digest. Separately, the
global market-data inventory binds every added market-data file, including the
classification module, its manifest, and the shared verifier. One shared verifier
opens a descriptor stack at filesystem `/` and retains every descriptor through
the named package root, intermediate directories, and source leaf. It uses
no-follow opens at every edge and compares full device/inode/size/mode/uid/link/
time metadata before and after each bounded read, preventing a named package-root
or intermediate path-tree replacement from being admitted. All `OSError` and
internal `ValueError` paths normalize to `ValueError("runtime source identity
invalid") from None` while closing every opened descriptor. Every named runtime
source is also bound to its expected package root, exact relative path, loaded
module, and manifest digest before its identity is admitted. The classification,
Market Regime V2, and participation runtime identities all use this one shared
`market_data/runtime_source_verifier.py`; frozen V1 verifier semantics remain
unchanged.

The participation identity is precomputed before reduction; the reducer
performs no runtime identity I/O. The participation inventory covers the
classification module, shared verifier, Market Regime V2 paired evaluator,
adjusted-handoff and corporate-screen validation dependencies, participation
reducer, package export, and participation manifest. The existing Market Regime
V2 inventory and manifest are regenerated because its source bytes change.

A missing, extra, unordered, malformed, unsafe, shadowed, or byte-mismatched
source/manifest is a sanitized pre-report structural failure. Runtime identity is
source-at-rest drift evidence only; it is not publisher authenticity, executed-byte
attestation, licence authority, or protection against an actor able to replace
code before verification.

## R3 hardening and current review-ready state

The first through sixth independent `REQUEST_CHANGES` / `FAIL` rounds drove
test-first hardening of trusted retention-time ownership, deep sealed-evidence
validation, causal closed reasons, strict Unicode admission, immutable archive
publication, complete canonical identities, deterministic fault merging,
complete runtime inventories, sanitized runtime-verifier failures, deterministic
receipt persistence/recovery, and related lifecycle corrections. All earlier
repair-round reviews and gate evidence remain superseded trace.

The prior exact-SHA review found that the candidate did not persist the receipt
needed to recover original evidence across a new-process retry and that lifecycle
records were stale. The seventh repair persists one deterministic canonical
retained receipt binding `known_at`, all required identities, and every exact
private cohort row required for reconstruction. A retry or new archive process
deeply validates that receipt, reconstructs the original retained evidence, and
rejects a missing, corrupt, or spliced receipt.

Focused verification passed 105 tests. Full local gates passed 2,982 tests at
90.82% coverage, Ruff format/check, Pyright, Vulture 80, and build. The unchanged
official parser smoke admitted the exact current 100-row, 6,610-byte artifact
with SHA-256 `5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85`
under classification schema
`7bc49d5eac26551c9ae0b76b4dd7b9edf9861ccca7d73fb7ea04f6c4f72f0415`;
it is parser provenance only, not live participation or effectiveness evidence.

Fresh exact-SHA independent quality `APPROVE` and security `PASS` and delivery
remain pending. The exact reviewed SHA will be recorded externally after review;
this contract contains no self-referential candidate SHA. Pull request, hosted
CI/GitGuardian, merge, and Issue closure remain pending.

## Licence, privacy, and provenance limits

The accepted use is owner-private personal/noncommercial research with source
attribution. The slice does not establish automated access, API use, scraping,
bulk harvesting, redistribution, sublicensing, public dataset publication, or
commercial-use authority. Raw bytes and raw/member rows remain outside Git,
packages, fixtures, logs, issues, pull requests, CI artifacts, and public result
surfaces.

The public artifact hash and source URL provide reproducibility and attribution
without publishing the artifact. They do not prove origin, publisher timestamp,
effective date, licence, correctness, or continued availability. The explicit
null publisher fields and same-session known-at rule are material limitations,
not optional diagnostics.

## Explicit deferrals

- official NSE Indices Sector taxonomy and any Industry-to-Sector mapping;
- automated acquisition, scraping, redirects, refresh, polling, retries,
  credentials, or network transport;
- yfinance, Angel One, Upstox, or another taxonomy authority or fallback;
- alternate artifacts, generic source registries, and multi-source reconciliation;
- publisher publication/effective-time inference;
- historical classification acquisition, revisions, reconstruction, backfill,
  availability studies, and backtests;
- projecting a current Industry label to any earlier cutoff or exchange date;
- Nifty membership selection/checks inside the classification or participation
  core;
- partial cohorts, member dropping, reduced denominators, and silent neutral;
- taxonomy hierarchies, weights, ranks, scores, recommendations, effectiveness,
  or public member transport;
- CLI, API, MCP, source-artifact publication, and raw-row publication;
- news/events, Market Structure, Price Action, Liquidity/SMC, recommendation,
  position sizing, broker execution, and orders; and
- renaming, aliasing, deleting, or reinterpreting frozen V1 contracts or their
  historical evidence.
