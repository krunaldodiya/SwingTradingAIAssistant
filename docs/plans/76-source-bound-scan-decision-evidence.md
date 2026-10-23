# Plan 76: source-bound scan decision evidence

Status: accepted bounded implementation contract under [Issue #326](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/326), Milestone 54. Owner and risk owner: Krunal Dodiya. Risk tier: R3 financial-research provenance and decision-support qualification. Base: `818c10c3f67db1595361363043672e0d44f6777d`.

## Outcome and smallest working slice

A human analyst or later external AI qualification process can retain one completed
scanner result as an immutable private `scan-decision-evidence@v1` record, then
read it only after every referenced retained observation is re-admitted. This
preserves the exact deterministic decision input without accepting copied or
caller-authored scan JSON.

The slice answers one concrete question: *what did this installed scanner decide
from which admitted observations at that time?* Existing scans expose an output,
but do not retain a source-bound scan-level decision record. The least adequate
correction is an opt-in record built in the scan invocation and a validated
readback path. It does not build historic acquisition, replay, performance
measurement, or AI-model evaluation.

## Public interface

```bash
signal-decisions scan --storage-root ROOT --symbol SYMBOL [--symbol SYMBOL ...] \
  --retain-decision-evidence --output json
signal-decisions scan --storage-root ROOT --nifty200 \
  --retain-decision-evidence --output table
signal-decisions read-decision-evidence --storage-root ROOT \
  --decision-evidence SHA256 --output json
```

`--retain-decision-evidence` is opt-in. Without it, `scan` retains its exact
existing `swing-trade-scan@v2` output and behavior (the validator still admits
historical `swing-trade-scan@v1` records for readback). With it, JSON is a closed
`scan-decision-evidence-envelope@v1` containing the unchanged scan object and a
64-hex `decision_evidence_handle`; table output renders the existing table plus
that handle. The envelope is not a replacement scan schema.

`read-decision-evidence` accepts only an absolute root, one lowercase 64-hex
handle, and JSON output. It has no provider, refresh, historical-date, input
file, or network option. Invalid arguments fail before opening the root with
`request_invalid`. An unavailable, corrupt, incompatible, or unadmitted record
returns a fixed redacted unavailable envelope and exit 1. Successful readback
returns the same closed evidence envelope and exit 0.

## Evidence record and admission

The private namespace is `scan-decision-evidence-v1`. A canonical record has:

- `contract_version: "scan-decision-evidence@v1"`;
- scanner runtime identity and the complete canonical `swing-trade-scan@v2`
  object (historical `swing-trade-scan@v1` records remain readable), including
  its result identity;
- an ordered row for every requested/evaluated symbol containing its canonical
  symbol, public decision, safety status, and either exactly one retained
  `CURRENT_STRUCTURE` observation handle or a fixed terminal `UNAVAILABLE`
  marker;
- the exact scan universe/selection provenance already present in the scan
  result; and
- no raw OHLCV, provider body, credentials, private path, exception string, or
  user-supplied fact.

The record handle is SHA-256 of its canonical bytes. Publication reuses the
existing private-root lease, descriptor-based private store, restrictive modes,
immutable name, atomic publication, and exact-byte idempotency behavior from
stock observations. The record is written only from scanner-owned execution
state; no public SDK or CLI accepts a dictionary/JSON scan result for retention.

Before publication, every non-null handle is re-admitted with
`read_stock_observation_v1`. Its canonical symbol must match the ordered scan
row. Missing/duplicate/unexpected symbols, a handle reused for another symbol,
a record with a non-`CURRENT_STRUCTURE` question, source/runtime mismatch, or
any malformed identity is terminal. A scan row with no admitted observation is
retained only as its explicit `UNAVAILABLE` terminal state; it cannot be
relabeled as `NO_TRADE` or `RESEARCH_CANDIDATE`.

Readback verifies canonical JSON, size/depth, exact handle, contract version,
runtime identity, scan-result identity, closed key sets, selection/order/count
binding, and every row before returning anything. It re-admits every non-null
observation and repeats the symbol/question validation. It never fetches a
provider, writes evidence, chooses a latest record, substitutes an observation,
or reconstructs missing history.

## Failure precedence and bounds

1. Invalid request fails before root access.
2. Unsafe, unavailable, malformed, oversized, noncanonical, wrong-version, or
   hash-mismatched record is unavailable.
3. Record schema/scan identity/order/count violation is unavailable.
4. Referenced observation unavailability, wrong question, runtime/source
   incompatibility, symbol substitution, duplicate handle, or terminal-state
   inconsistency is unavailable.
5. Only after all admission checks may the original scan object be returned.

The record is limited to the existing private-record safe size/depth envelope
and the scan’s existing 1–100 explicit-symbol bound or its retained Nifty
universe bound. A Nifty 200 scan retains exactly one ordered row for every
physical evaluation; Nifty 100 priority and conditional Nifty 200 ex-Nifty 100
tier-2 fallback remain scan policy, not evidence-record policy.

## Frozen adversarial matrix

| Case | Required result |
| --- | --- |
| Complete explicit scan | Record is immutable; readback returns exact scan bytes and every observation is re-admitted. |
| Per-stock unavailable source | Ordered terminal `UNAVAILABLE` row is retained honestly; it is never a negative/candidate. |
| Tampered record, self-hash, scan identity, runtime, order, count, symbol, handle, or terminal state | Readback fails closed with the fixed unavailable envelope. |
| Missing, wrong-question, stale-runtime, substituted, or duplicate observation handle | Readback fails closed before output. |
| Invalid root/handle/flag/output and bound-plus-one symbols | `request_invalid`, no record read, write, or provider effect. |
| Retry/interruption and immutable-name conflict | No partial usable record; exact retry reuses exact bytes; conflicting bytes refuse. |
| Existing scan paths | No `--retain-decision-evidence` behavior/schema changes; previous scan, eligibility, evaluation, paper-tracking, and observation contracts remain usable. |
| Privacy/resource limits | No raw OHLCV, source body, credential, private path, or exception leakage; size/depth limits reject before public output. |

## Qualification boundary

This record is a G09 prerequisite, **not G09 closure**. It provides neither
per-decision-date historical backfill (Future #139), a generic replay engine,
out-of-sample or walk-forward evidence, execution/cost/slippage evidence,
AI-model replay/evaluation, a return/profit claim, a broker action, nor capital
allocation. A later claim requiring any of those must obtain its own accepted
source, time, policy, and measurement contract.

Issue #316 and Plan 73 delivered G11’s paper-observation workflow. The live
ledger after this slice remains G09 and G12; this document changes neither
outcome’s closure predicate.

## Amendment 1 — 2026-10-22 (#342): retained-evidence compatibility wording

The earlier sentence in “Evidence record and admission” that historical
`swing-trade-scan@v1` records “remain readable” overstates the retained-evidence
guarantee. This dated amendment supersedes that compatibility claim only; the
original plan text remains historical evidence.

Retained `scan-decision-evidence@v1` records are bound to the scanner runtime
identity that produced them. What remains admissible is the historical
`swing-trade-scan@v1` **shape** — its closed key set, universe types, and
required universe totals — and
only when every current runtime-identity, result-identity, selection-binding,
and observation-admission check still matches. This amendment promises no
universal readability for arbitrary historical v1 records, performs no
migration, and changes no executable behavior.

## Amendment 2 — 2026-10-23 (#348): carry-policy runtime segment

`supported-signal-decision-policy@v2` changes candidate selection and adds the
`CAUSAL_EXTENSION` rule, so the scanner and decision runtime identities change.
Consistent with Amendment 1:

- Retained pages produced before this change remain the historical V1 record;
  their policy identifier, result identity, and decisions are unchanged.
- They are not re-admissible under the new runtime identity, and no migration or
  rewrite is performed.
- The forward diary starts a new evaluation segment at the first page produced
  after this change. No completed 10-session window existed before it, so no
  completed-window evidence is lost.
- G09 series-level qualification still requires real completed windows under the
  new segment; this amendment makes no effectiveness claim.


## Amendment 3 — 2026-10-23 (#356): producer-identity reset and retained-evidence scope

The observation producer identity is no longer pinned to the decision projection
(`setup_screen.py`), so future decision-layer changes do not start a new pair-state
generation. This identity change itself starts one deliberate fresh generation.

- Observations recorded under the previous producer identity are not readable by
  the new producer; nothing is migrated or rewritten.
- Retained decision-evidence pages that reference those observations report the
  existing unavailable admission rather than re-deriving a decision. Their recorded
  bytes and identities remain unchanged.
- The forward diary starts a new segment at the first page produced after this
  change. No completed 10-session window exists across the boundary.
- The first scan of the new generation must use `--refresh`; a no-refresh first
  scan with an unreadable/stale retained handle reports
  `OBSERVATION_PAIR_BOOTSTRAP_REQUIRES_REFRESH`.
