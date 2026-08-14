# Sector Participation v1 TDD and validation protocol

Status: **GREEN — REVIEWED AND PUBLISHED**

Contract under validation: `nifty50-sector-participation@v1`

Normative implementation contract: [Plan 14](14-sector-participation-contract.md).

Focused tests:

- `tests/market_data/test_universe_snapshot.py`
- `tests/market_regime/test_observed_reducer.py`
- `tests/sector_analysis/test_participation.py`

Implementation under test:

- `src/swing_trading_ai_assistant/market_data/universe_snapshot.py`
- `src/swing_trading_ai_assistant/market_regime/observed.py`
- `src/swing_trading_ai_assistant/sector_analysis/participation.py`

## Validation objective

Validate only the implemented provider-free, in-process vertical slice:

1. the public reducer accepts exact verified Market Regime facts and one
   already-resolved PIT opaque-label snapshot;
2. in that same call, it privately derives the unchanged public Market Regime
   report and exact-50 direction handoff, consumes the pair, and exposes neither
   as caller authority;
3. a valid join emits deterministic aggregate counts; and
4. every admitted invalid domain state emits one redacted whole-result
   insufficiency, while an inconsistent internal pair stops structurally.

The protocol does not validate an official taxonomy, data acquisition, a live
market result, a delivery runtime, a transport, a recommendation, or
investment effectiveness.

## RED to GREEN evidence

The integrated implementation followed the requested TDD order. The original
RED tests named the missing same-pass private handoff, trusted-facts public
boundary, and Sector Participation happy-path/fail-closed contracts. They
failed before the producer, reducer, types, exports, reason mappings, and
security boundary existed. The smallest production changes made the prior
complete two-file focused run GREEN at **49 passed**, with Ruff **PASS** and
focused Pyright **0 errors, 0 warnings**.

Exact-SHA review of `25d889a` then found a privacy defect: a syntactically safe
label could still carry a constituent identity. Review returned
**REQUEST_CHANGES**. Identity-focused RED cases drove the repair that rejects
any label containing a full constituent ISIN case-insensitively or matching a
constituent symbol case-insensitively as a complete `[A-Z0-9.&_-]` token. The
observed focused identity-regression run is **4 passed**, covering exact and
wrapped ISINs, a complete symbol token, and the allowed non-identity singleton
boundary.

The four identity cases were added after the prior 49-test complete run. The
subsequent complete two-file run was **53 passed**, with Ruff **PASS** and
focused Pyright **0 errors, 0 warnings**. `25d889a` is superseded, not approved.

A second exact-SHA review of `d79eecc` returned **REQUEST_CHANGES** after finding
that aggregate snapshot construction did not re-run every invariant of every
exact constituent. The focused defect reproduction was **2 failing**. The
repair deep-revalidates all exact-50 members at aggregate construction, and the
direct repaired regression is **2 passed**.

The final combined universe-snapshot, observed-reducer, and Sector Participation
focused gate is **96 passed**, with Ruff **PASS** and Pyright **0 errors, 0
warnings**. `d79eecc` is superseded; it is not approval, publication, or
final-candidate evidence. The final repaired repository gate is
Ruff/format/Vulture **PASS**, Pyright **0 errors, 0 warnings**, and **2,445
passed** at **92.96%** coverage. Documentation evidence is **60 passed**.

Final reviewed head `411b21d4874206563b64d03ce8024953430660d2`
received independent exact-SHA quality **APPROVE** and security **PASS**.
[PR #103](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/103)
merged to `main` at **2026-08-14T19:39:18Z** as
`b6e34d3cdc598e1cd6dc50c50d517481d26e1391`. Hosted CI
[run 31832620021](https://github.com/krunaldodiya/SwingTradingAIAssistant/actions/runs/31832620021)
and GitGuardian both passed. The local focused and repository gates are not
themselves hosted, live-market, or effectiveness evidence; the separately
identified hosted checks are publication evidence only.

## Current behavioral matrix

| Case | Implemented result | Focused evidence |
|---|---|---|
| Exact verified Market Regime facts + resolved exact-50 snapshot | Public reducer privately derives and consumes the same-pass report/handoff, then returns canonical `SectorParticipationReportV1` with opaque-label counts | Counts, inherited sessions/identities, equations, sorted rows, and canonical JSON asserted |
| Same Market Regime facts through existing public reducer versus private same-pass producer | Public Market Regime report and canonical bytes remain identical | Regression assertion in Market Regime focused test |
| Internally produced exact-50 handoff | 50 unique ISIN-sorted immutable `_MemberDirectionV1` rows; direction totals equal public totals | Shape, sorting, immutability, identity binding, and total reconciliation asserted |
| Snapshot constituent permutation | Equal report and byte-identical canonical output | Permutation metamorphism asserted |
| Exact aggregate snapshot construction | Re-runs every constituent invariant across all 50 exact members before accepting the aggregate | Focused defect reproduction was 2 failing; direct repaired regression is 2 passed |
| Deep snapshot inconsistency reaches Sector Participation | Only expected `TypeError` or `ValueError` is translated to bounded `ValueError("resolved universe snapshot is inconsistent")`; no private value or domain report escapes | Direct repaired regression asserts the sanitized structural boundary |
| Market Regime absent or insufficient | `MARKET_REGIME_UNAVAILABLE`; upstream reason suppressed | Both branches asserted |
| Snapshot absent or not found | `SECTOR_CLASSIFICATION_MISSING` | Both branches asserted |
| Snapshot stale, ambiguous, or corrupt | Matching closed classification reason | All three branches asserted |
| Any label contains a full constituent ISIN case-insensitively, including inside otherwise safe text | Whole-result `SECTOR_CLASSIFICATION_CORRUPT` with `sectors = None`; no identity-bearing row | Exact and wrapped lowercase-ISIN regressions passed in the observed 4-test identity run |
| Any label matches a constituent symbol case-insensitively as a complete `[A-Z0-9.&_-]` token | Whole-result `SECTOR_CLASSIFICATION_CORRUPT` with `sectors = None`; no identity-bearing row | Lowercase wrapped-symbol regression passed in the observed 4-test identity run |
| Singleton group with a non-identity opaque label | Observed aggregate remains allowed solely within the authenticated nonanonymous owner-private boundary | Singleton boundary regression passed in the observed 4-test identity run; no public delivery exists |
| Decision session outside snapshot interval | `SECTOR_EFFECTIVE_SCOPE_MISMATCH` and no rows | Asserted |
| Any membership/sector publication or retrieval timestamp after cutoff | `EVIDENCE_CUTOFF_MISMATCH` and no rows | All four clocks asserted at cutoff + 1 microsecond |
| Snapshot substitutes one ISIN while retaining cardinality 50 | `MEMBER_IDENTITY_MISMATCH` and no joined rows | Asserted with identifier redaction |
| Multiple constructible domain defects | One insufficiency with three unique reasons in declaration order | Effective-scope, evidence-cutoff, then member-identity precedence asserted |
| Rehashed same-total cross-sector direction substitution submitted as legacy report + handoff + snapshot | Rejected with `TypeError`; forged handoff cannot enter the two-input public API | Regression swaps advance/decline members across labels, recomputes the handoff SHA-256, and asserts the exact public signature |
| Wrong top-level type, inconsistent resolved structure, or inconsistent internally produced report/handoff pair | Sanitized `TypeError` or `ValueError`; no domain result | Public slots and internal producer boundary are fail-stop; sensitive value absent and message bounded |
| Impossible internal handoff cardinality | Private constructor rejects it before aggregate reduction | 49-member construction asserted |
| Any insufficiency | `evidence_state = INSUFFICIENT_EVIDENCE`, `sectors = None`, closed reasons only | Common shape helper used across fail-closed cases |

## Oracles and invariants

For every observed row `s`, the independent assertions use:

```text
member_count_s = advances_s + declines_s + unchanged_s
sum_s member_count_s = 50
sum_s advances_s = market_report.advances
sum_s declines_s = market_report.declines
sum_s unchanged_s = market_report.unchanged
```

The private handoff oracle separately reconstructs expected directions from the
admitted Market Regime facts and proves that their three totals equal the
unchanged public report. Sector Participation derives and consumes that handoff
inside the same public call, joins by exact ISIN, and never derives a direction
from prices downstream.

The output oracle requires exact ascending label order, unique labels, canonical
JSON-plus-LF serialization, and a report identity derived from the complete
identity projection. It treats labels as opaque strings and makes no taxonomy
authority assertion.

## Boundaries

The implemented boundaries are:

- the internally produced handoff has exact cardinality 50; uniqueness and ISIN
  ordering are mandatory;
- its accepted directions are exactly `ADVANCE`, `DECLINE`, and `UNCHANGED`;
- callers supply exact verified facts, an upstream insufficiency, or `None` in
  the first public slot—not a report or handoff;
- the snapshot/report effective interval is inclusive;
- each of the four snapshot knowledge timestamps may equal, but not exceed, the
  report evidence cutoff;
- the internally joined handoff and snapshot ISIN sets must be identical and
  exact-50;
- aggregate snapshot construction must re-run every invariant for each of its
  exact 50 constituents before the snapshot can be accepted;
- each label must contain no full constituent ISIN case-insensitively and no
  constituent symbol case-insensitively as a complete `[A-Z0-9.&_-]` token;
- one non-identity label has 1 through 64 safe characters and one row may have 1
  through 50 members only inside the authenticated nonanonymous owner-private
  boundary;
- sector counts and global totals must reconcile exactly;
- observed reports have no reasons; insufficiencies have no sector rows; and
- canonical report serialization is capped at 64 KiB.

Boundary validation distinguishes malformed structure from usable structure
with insufficient domain evidence. A wrong public-input type, a constituent
that fails deep aggregate revalidation, an internally inconsistent resolved
object, or an inconsistent pair from the private producer is a sanitized
programming-boundary exception. Sector Participation translates only expected
`TypeError` and `ValueError` from resolved-snapshot consistency validation to
the bounded `ValueError("resolved universe snapshot is inconsistent")`; it does
not swallow unexpected exceptions. A typed missing, stale, ambiguous, corrupt,
cross-effective, late, or cohort-invalid outcome is a redacted domain
insufficiency.

An identity-bearing label is usable structure with corrupt domain evidence. It
therefore produces one whole-result `SECTOR_CLASSIFICATION_CORRUPT`
insufficiency with `sectors = None`, rather than a structural exception or a
partially redacted aggregate. Non-identity singleton groups remain allowed only
inside the approved owner-private boundary; no public delivery surface is
implemented or validated.

## Metamorphisms

The current focused suite proves the highest-value metamorphism: permuting
constituents before snapshot construction does not change the resolved snapshot,
aggregate object, canonical bytes, or report identity.

The following relationships also define review expectations for the implemented
algorithm:

- callers cannot reorder, replace, or rehash private handoff members because no
  handoff is accepted by the public API;
- changing one admitted direction in the trusted facts changes exactly the
  affected label count, corresponding aggregate total, and bound identities;
- changing an opaque label changes the affected row grouping and report identity
  without changing the 50-member total; and
- adding a second independent domain defect may add only its closed reason at
  global declaration precedence and can never reveal partial rows.

The focused suite directly covers permutation, the three-reason multi-fault
precedence case, and rejection of a same-total cross-sector substitution even
after its private handoff hash is recomputed. It does not claim an exhaustive
generated-property campaign for every possible label partition or direction
vector.

## Redaction and zero-I/O review

For the observed path, canaries include all 50 ISINs and symbols plus private
class names, member-direction syntax, raw-close provenance, and upstream source
identifiers. They must be absent from the public Market Regime report and from
the Sector Participation report serialization and representation. Admission
also prevents an opaque aggregate label from carrying a full constituent ISIN
or complete constituent-symbol token. A caller has no public parameter through
which to submit the private handoff.

For insufficiency and structural-error paths, upstream reason detail, snapshot
exception detail, substituted identifiers, and malformed private values must be
absent. Structural error messages must remain nonempty and at most 128
characters in the exercised cases.

The reducer implementation contains no file, network, provider, resolver,
storage, logging, or publication operation. Review must reject any future
change that turns the pure in-memory reducer into an I/O boundary. The focused
suite validates redacted surfaces; the completed exact-SHA reviews also
inspected the reducer for zero-I/O preservation.

## Historical PR #102 boundary

[PR #102](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/102)
is immutable planning/specification evidence. It shipped no Sector Participation
runtime. Its proposed post-merge nonce P1 belonged to an oversized Layer B
private-delivery design that has been removed from this implemented-core
contract and deferred with Layer B.

Therefore the nonce item is neither a shipped vulnerability nor an unresolved
issue in the provider-free in-process core. No nonce, cryptographic delivery
protocol, readiness service, or private-delivery runtime is implemented or
claimed here.

## Completed review and publication evidence

| Evidence | Final result |
|---|---|
| Final reviewed head | `411b21d4874206563b64d03ce8024953430660d2` |
| Independent exact-SHA reviews | Quality **APPROVE**; security **PASS** |
| Focused gate | **96 passed**; Ruff **PASS**; Pyright **0 errors, 0 warnings** |
| Repository gate | Ruff/format/Vulture **PASS**; Pyright **0 errors, 0 warnings**; **2,445 passed** at **92.96%** coverage |
| Documentation evidence | **60 passed** |
| Hosted checks | CI [run 31832620021](https://github.com/krunaldodiya/SwingTradingAIAssistant/actions/runs/31832620021) **PASS**; GitGuardian **PASS** |
| Publication | [PR #103](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/103) merged at **2026-08-14T19:39:18Z** as `b6e34d3cdc598e1cd6dc50c50d517481d26e1391` |

Repository implementation, review, and publication are complete. ARK-179 and
ARK-181 remain In Progress pending Linear reconciliation rather than being
represented here as Done; repository Sprint delivery is complete, and Linear
closeout is next.
The completed publication does not turn the removed Layer B design into an
implemented-core defect and does not claim a real-data run, observed Sector
Participation result, or effectiveness evidence.
