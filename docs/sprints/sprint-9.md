# Sprint 9 — Market Regime Layer B acquisition decision

Status: **TERMINAL DECISION `BLOCKED / CAPABILITY_EVIDENCE_MISSING`**
Historical planning and original implementation parent: `b8359f5cffded6122511c3ee8ebe290893007672`
Corrective change-series base: `c74ee4788aa6d03864eb8c21f111afe7025ad9cc`

## Goal and architecture placement

Deliver one test-first learning/decision slice that answers whether later Market
Regime Layer B evidence acquisition may proceed. The slice implements the pure
decision and bounded market-data probe, performs the one owner-authorized
supervised probe invocation, seals the reviewed evidence/authorization manifest
in the candidate build, and publishes the evidence-driven terminal decision.
It is not a documentation-only sprint.

[Plan 16](../plans/16-market-regime-layer-b-acquisition-decision.md) is the
implementation-ready contract. Its only terminal states are
`APPROVED_TO_ACQUIRE` and typed `BLOCKED`. Approval is distinct from acquisition,
execution authority, retained evidence, `READY`, admission, `OBSERVED`,
validation, and Market Regime computation. Plans 12 and 13 remain frozen.

## Accepted five-line source evaluation

1. Expected value: test whether one candidate artifact can be reached within a tightly bounded receipt path.
2. Scope fit: the candidate could inform later point-in-time Nifty 50 membership-source research for Market Regime Layer B.
3. Material risk: reachability, status `200`, media type, `%PDF-`, or one digest proves no publisher authority, membership content, historical completeness, correction semantics, identifiers, licence, or permitted use.
4. Smallest alternative: one supervised credential-free GET; no retry, parsing, persistence, catalogue write, acquisition, label, count, or outcome.
5. Decision: the probe may create capability evidence only; the sealed manifest separately determines whether later acquisition may proceed.

The PDF is a **candidate artifact**, not a pre-attested official membership
artifact. `%PDF-` proves only a five-byte prefix.

## Owner authority and supervised probe

Krunal authorized one supervised release invocation containing exactly one
credential-free `GET` of:

```text
https://www.niftyindices.com/Press_Release/ind_prs21022025.pdf
```

The invocation has one attempt, concurrency `1`, a 1,048,576-byte body cap with
one detection byte, a hard 30-second wall-clock cap, zero retries, zero followed
redirects, no credentials, no parsing, no persistence/catalogue writes, and
sanitized receipt output only. An outer monotonic watchdog force-terminates the
probe child process at the deadline; bounded transport waits alone are not the
authorization control.

Exactly-once is operationally enforced by owner supervision and retained release
run evidence. The adapter is not authorization and does not claim replay
prevention. There is no installable live-probe CLI. A failure consumes the
invocation, and a second invocation is forbidden without a new owner
authorization record and new supervised-run evidence.

Probe URL/status/header/body metadata remains only in the `market_data` receipt.
The pure decision sees only an authenticated provider-independent capability
state and identity that must match the reviewed build-sealed manifest.

## One authenticated manifest boundary

Sprint 9 does not accept caller-authored per-gate assessments or caller-supplied
full-acquisition authorization. Plan 16 defines one canonical
`AcquisitionAuthorizationManifestV1` containing:

- frozen Plans 12/13 and exact acquisition-scope identities;
- the reviewed provider-independent capability state/identity;
- one source/PIT evidence-bundle identity;
- one terms/use approval identity;
- one operational-scope approval identity;
- one owner acquisition-authorization binding; and
- one trusted authorization-validation receipt identity.

The sole runtime source is the exact canonical manifest literal sealed in the
`historical_evaluation` build. A literal `None` fails closed as
`SEALED_MANIFEST_MISSING`, while a valid incomplete seal proceeds to its first
missing prerequisite. Neither stdin, environment, configuration, writable files,
nor matching caller-selected digests can replace the seal. A future approval is
impossible without a reviewed build change sealing the exact complete manifest
bytes and identity.

The trusted validation receipt is content-addressed by the manifest and bound to
a code-pinned trusted clock source. Capability and prerequisite assessment times
must not be later than the receipt's trusted decision-assessment time, and every
assessment/validation instant must fall within the acquisition authorization's
inclusive/exclusive `[not_before, expires_at)` interval. Replay wall time and
caller time grant no authority. A later executor must validate fresh
execution-start authority independently.

## Smallest decision taxonomy

The reducer stops at the first applicable value in this closed order:

1. `SEALED_MANIFEST_MISSING`
2. `SEALED_MANIFEST_INVALID`
3. `CAPABILITY_EVIDENCE_MISSING`
4. `SOURCE_AND_PIT_EVIDENCE_UNPROVEN`
5. `TERMS_AND_USE_UNAPPROVED`
6. `OPERATIONAL_SCOPE_UNAPPROVED`
7. `OWNER_AUTHORIZATION_NOT_IN_FORCE`

There is one primary blocker and no redundant additional-blocker or per-gate
matrix. This still identifies the first missing acquisition prerequisite while
keeping malformed or unauthenticated authority distinct.

## Plausible one-week atomic sequence

| Order | Slice | Required exit | Current state |
|---|---|---|---|
| 1 | Freeze Plan 16 and Sprint 9 summaries; write RED decision tests | Missing/invalid seal, all seven blockers, both states, identities, temporal boundaries, bounded stdin, and no-side-effect/dependency failures are discriminatory | **COMPLETE** |
| 2 | Implement pure reducer and offline decision CLI | Initial `None` seal fails closed; stdin cannot supply authority; `16 KiB + 1` is rejected before allocation/parse amplification | **COMPLETE** |
| 3 | Write RED probe tests and implement fixed worker/supervisor | Exact receipt rows, media normalization, byte bounds, no redirect/retry/write, outer watchdog, and local slow-stream termination are green; no live-probe CLI exists | **COMPLETE** |
| 4 | Verify deterministic candidate build, then perform one supervised probe invocation | Retained owner authority/run evidence and one sanitized receipt/projection; no retry or raw-byte retention | **STOPPED — invocation consumed; receipt retained, projection absent** |
| 5 | Review the seal disposition; reduce and publish the actual decision | Seal the truthful complete or incomplete manifest; never invent missing evidence | **CORRECTED SEAL — `BLOCKED / CAPABILITY_EVIDENCE_MISSING`** |

A phase boundary is not sprint completion. Missing evidence is never filled by
inference. The current incomplete sealed manifest produces its first honest
blocker and grants no authority.

## Test-first acceptance evidence

RED precedes production implementation. Focused tests must prove:

- the initial missing seal is byte-stable `BLOCKED`, and no input can replace it;
- manifest/capability/receipt mutation and code-pin mismatch cannot approve;
- both terminal states and each first blocker follow the closed precedence;
- assessed and validated times reject before/not-before, future, inverted,
  equal, before-expiry, and at/after-expiry boundaries exactly as Plan 16 states;
- provider HTTP metadata never crosses the `market_data` receipt boundary;
- the fixed URL, one request, one attempt, concurrency `1`, one body cap,
  no retries/redirects/credentials/writes, and every deterministic receipt row;
- exact minimal media-type normalization without an unspecified parser;
- a local slow stream that keeps yielding bytes is force-terminated by the outer
  monotonic watchdog and produces no body hash or second request;
- the offline CLI reads at most `16 KiB + 1`, does not consume or buffer beyond
  that bound, and emits only fixed redacted structural errors; and
- fail-on-call sentinels for Market Regime/Sector reducers and every provider,
  network, filesystem, clock, random, storage, acquisition, and label side effect
  remain untouched; dependency tests reject those reducer imports.

No public label counter or equivalent field exists.
No-label behavior is proven at dependencies and side-effect ports, not asserted
by a caller-visible zero.

The one real probe is release evidence, not a test fixture. Final evidence must
identify the exact candidate revision and distinguish run, pass, fail, blocked,
and not run. Any repair invalidates earlier exact-revision review.

## Candidate actuals

The owner-authorized invocation ran once at
`2026-08-15T14:14:23.152972Z` and completed at
`2026-08-15T14:14:23.606209Z`. Its retained sanitized receipt reported status
`200`, normalized media type `application/pdf`, 775,528 body bytes, a matching
`%PDF-` prefix, body SHA-256
`1b3a52abf5954f4b213f5b555ee8776ff596f0adde0612cfdd5409b109195370`,
zero redirects, credentials, parser calls, filesystem writes, or storage writes,
and receipt identity
`20911a88188cb83b2630c90c0abbbad7f74aaff8b442afc142133bfd12d8babb`.
No raw response body was retained.

That historical run used worker identity
`e83bb1dabeccc3abe676294ba65210eaea2fa26f5c4fff2eda1491104d4e6430`.
That worker could fall through to another resolved address, so its reported one
network call and attempt are unverified. The receipt remains retained historical
output but is inadmissible as capability evidence. The current fixed worker pin
`65026c3d26fd266a9ae92c98cee286825b33023bfefc669753fe6261d6fc41d7`
was not used for the consumed probe, and no rerun occurred. No
provider-independent capability projection was retained or reconstructed.

No admissible capability projection, source/PIT evidence bundle, terms/use
approval, operational-scope approval, owner full-acquisition authorization, or
trusted authorization-validation receipt was supplied. The corrected build
therefore seals each of those later fields as null. Its source-controlled
`prerequisites_assessed_at` is `2026-08-15T16:03:40.000000Z`; this records the
assessment of those absences and grants no authority.

The independently authored canonical manifest binds the exact current file bytes
and finite sealing projections:

| Identity | SHA-256 |
|---|---|
| Plan 12 exact bytes / market-regime contract | `b5b54bed2d4224fb496755c8e9d6a190d6cbb7fc8bd13a53feded72450af12af` |
| Plan 13 exact bytes / Layer B protocol | `e8e2c712e4fba5cfe24fd51c6d9985df23e2e714c12e01c7f9f9d30ab670e19d` |
| Final corrected Plan 16 exact bytes / acquisition scope | `71f54a9f89b8b77cfe5800312461dd1c3dbd189df5ff7fee2a760229b27da835` |
| Manifest scope projection | `07f235b246e88d30404ddf1574e13907f436c937144e40abf4766c4463cb759e` |
| Final sealed manifest | `53717e75d9e93344d7df55ea2a5e94e48e133ff0ad673f27e38ba040cc91bb2f` |
| Canonical terminal report | `dbbc0bdf32cf081d491a119c05571bebf4dbd274bae858dd0e3d418b96bd1408` |

The offline reducer now returns canonical `BLOCKED` with primary blocker
`CAPABILITY_EVIDENCE_MISSING`, sealed manifest identity
`53717e75d9e93344d7df55ea2a5e94e48e133ff0ad673f27e38ba040cc91bb2f`,
and null authenticated capability, validation-receipt, and assessment-time
outputs. This is the truthful corrected outcome. It grants no
acquisition or execution authority.

The following publication evidence is historical and applies to the original
implementation candidate, not to this corrective seal:

| Evidence | Historical result |
|---|---|
| Candidate parent | `b8359f5cffded6122511c3ee8ebe290893007672` |
| Final reviewed head | `80d309ced4823c326b25f374a69b34566c647716` |
| Independent exact-SHA reviews | Code **APPROVE**; security **APPROVE** |
| Focused gate | **119 passed** |
| Repository gate | **2,512 passed** at **92.16%** coverage; format/Ruff/Pyright/Vulture/diff **PASS** |
| Builds | Source distribution **PASS**; wheel **PASS** |
| Hosted checks | CI [run 31892711460](https://github.com/krunaldodiya/SwingTradingAIAssistant/actions/runs/31892711460) **PASS**; GitGuardian **PASS** |
| Publication | [PR #107](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/107) merged to `main` at **2026-08-15T15:40:16Z** as `c74ee4788aa6d03864eb8c21f111afe7025ad9cc` |

Those gates establish historical delivery of the implementation and its former
missing-seal result. They do not verify, review, commit, or publish this
correction, turn the historical probe receipt into admissible
capability evidence, or supply any missing prerequisite.

## Lifecycle and later handoff

Sprint 9 creates no market-data migration, no retained PDF, no production source
replacement, no bulk acquisition, and no Market Regime fact. It may retain only
the sanitized probe receipt, provider-independent capability record, supervised
run evidence, reviewed manifest, validation receipt, and terminal report.

A blocked handoff preserves the immutable report, authenticated identities that
exist, the first missing prerequisite group, and retained review/run evidence.
Later work needs new evidence and a new reviewed manifest/build and may not rerun
the Sprint 9 probe without new owner authority.

An approved handoff preserves the immutable report and exact sealed manifest but
still performs no acquisition. A separate executor must authenticate fresh
execution-start authority, remain inside the approved scope and ceilings, and
seal acquired evidence under Plan 13 before any Layer B computation.

## Current repository and tracker truth

Sprint 8 repository delivery remains complete and its historical sprint record
remains immutable evidence of what was known at closeout. Linear now records
ARK-179 and ARK-181 as **Done**; this Sprint 9 record reconciles that current
operational truth without rewriting Sprint 8 history.

PR #107 remains immutable historical implementation publication evidence. It
merged at `2026-08-15T15:40:16Z` as
`c74ee4788aa6d03864eb8c21f111afe7025ad9cc`; it did not contain the corrective
incomplete manifest.

Linear reconciliation also remains historical:

| Issue | Sprint 9 role | Historical state and evidence |
|---|---|---|
| ARK-183 | Parent acquisition-decision task | **Done**; PR #107 attached; one completion comment |
| ARK-184 | Contract story | **Done**; PR #107 attached; one completion comment |
| ARK-185 | Implementation story | **Done**; PR #107 attached; one completion comment |

Those Done states record the published implementation; they do not establish
authority or publication of this correction. Commit identity, exact-revision
reviews, hosted checks, merge, and publication for the correction are external
lifecycle evidence; this source snapshot asserts no current lifecycle state for
them. The sealed result is
`BLOCKED / CAPABILITY_EVIDENCE_MISSING` with a valid incomplete seal. No
admissible capability projection, source/PIT evidence bundle, terms/use approval,
operational-scope approval, owner full-acquisition authorization, or trusted
authorization-validation receipt exists. The historical receipt remains
inadmissible, the authorized invocation remains consumed, and no rerun occurred.

Sprint 10 and the separate GitHub workflow migration plan remain explicitly
deferred until tomorrow, **2026-08-16**. Neither starts in this correction.

## Explicit exclusions and stop conditions

Sprint 9 does not authorize bulk, alternate-source, retried, credentialed, paid,
or persistent acquisition; PDF parsing or membership extraction; raw-byte
retention; source/content/licence inference; Layer B admission; Market Regime
labels/counts/outcomes; Sector Participation work; recommendations; or changes
to frozen Plans 12/13.

Stop before the supervised invocation if owner authority, fixed scope, outer
watchdog, byte cap, no-redirect/no-retry policy, or redaction cannot be enforced.
Stop after the authorized invocation regardless of outcome. Do not invoke again
without new owner authority. Stop before acquisition and before labels regardless
of the terminal decision.

## Sprint completion gate and residual risk

The implementation, consumed-probe disposition, historical PR #107 publication,
and historical Linear ARK-183/184/185 Done states remain recorded, but they do
not cover this corrected seal. Commit identity, exact-revision reviews, hosted
checks, merge, and publication for the correction are external lifecycle
evidence; this source snapshot asserts no current lifecycle state for them.

The truthful terminal result is `BLOCKED / CAPABILITY_EVIDENCE_MISSING` with a
content-addressed incomplete manifest. There is no admissible capability
projection, source/PIT evidence bundle, acquisition/readiness/admission/label
authority, or later execution authority; the historical receipt remains
inadmissible, the one authorized invocation is consumed, and no rerun occurred.

Remaining risk is explicit: exactly-once depends on supervision and retained run
evidence rather than technical replay prevention; the HTTP/PDF envelope proves
no candidate semantics; and a retained validation receipt establishes only its
historical decision instant, never later execution authority.
