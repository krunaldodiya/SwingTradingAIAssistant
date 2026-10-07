# Plan 62: exact selection and whole-list current research

October 7, 2026. Sprint 49; owner/risk owner Krunal Dodiya. R3 public
research/provenance contract. Base `d301db57358aa5aef3873b64c1282dd3148e8cb2`.
The owner requested the next sprint under the same Goal/review/delivery process.
This refines [Plan 61](61-first-use-gap-reconciliation.md)'s G02 only.

## Question and necessary boundary

Can an owner obtain the existing same-observation current research and candidate
facts for every stock of an exact admitted Nifty 100 selection, or an explicit
supported list, without omissions, duplicate acquisitions or identity changes?

Reuse G01 and the existing official three-witness selector/capture store. A
manual concatenation loses whole-selection identity and cross-partition alias
checks. Enlarging the reusable ten-stock core changes an accepted bound without
need. The selected solution is one versioned higher-level serial orchestrator.
It retains the original child reports, validates global identities and recomputes
only existing comparability predicates over the complete list. It adds no
analytical calculation, ranking, eligibility or trading rule.

Default selection means the exact **retained current-at-retrieval** Nifty 100
selection, not a discovery of today's latest membership. Existing capture must
first retain its official Nifty 50, Next 50 and Nifty 100 CSV witnesses and
request binding. A new read-only public selector entry validates those exact
bytes using the existing guarded reader. It never acquires, repairs or replaces
missing selection evidence. This avoids a new store or persistence model.
Actual authorized fresh source/workflow qualification remains G08.

## Frozen interface and authority

New SDK `run_setup_research_selection_current(symbols, storage_root, *, research,
selection_request=None, selection_root=None, clock=None)` and installed
`market-data setup-research-selection --storage-root ABSOLUTE_ROOT --output json`.
With repeated `--symbol`, explicit mode accepts a tuple of 1–100 distinct symbols
under the existing symbol grammar; selector arguments are forbidden. Without
symbols, default mode requires `--selection-request-file` and `--selection-root`.
The file is the existing canonical **current V3 capture request**, privately read
with the existing 8 MiB limit; unsupported request revisions fail closed.
SDK uses the exact current `CaptureRequestV2`, not an authored membership/fact
JSON or an `OfficialSelectionV2` supplied as evidence. All roots are absolute.

Before producer effects, default admission validates the request, 100-member
bound, exact retained witnesses/order/membership/request/source identities,
guarded storage authority, and timestamps. Witness retrieval must be no later
than the request cutoff, which must be no later than the trusted invocation
clock. The production clock is UTC now; injection is a deterministic testing
seam. No expiry threshold or historical membership before retrieval is invented.
The capture cutoff binds selector knowledge; it is not a current-research cutoff.
The selector lease ends before research acquires any store lease, including when
roots coincide. Existing source-use restrictions keep the report owner-private;
this sprint authorizes no external AI destination or source disclosure.

## Whole-selection contract

Contract `agent-current-setup-research-selection@v1`. Preserve exact requested
order. Partition into consecutive chunks of at most ten, delegating unchanged
G01 exactly once per chunk. Each member gets one serial real V2 call with
`INTEGRATED_CURRENT_RESEARCH`, `refresh=False`; no second candidate acquisition.
No parallelism or automatic retry. Bounds 1–100 are orchestration resources,
not an eligibility or index algorithm. Default is exactly 100.

The closed outer report contains version/runtime identity; selection metadata;
requested and actual canonical order identities; ordered original G01 reports;
global base/candidate comparability flags and explicit limitations; final result
identity. Default metadata binds `CURRENT_AT_RETRIEVAL`, witness known time,
source identity, capture request identity and exact expected canonical members.
Explicit metadata records `EXPLICIT_SYMBOLS` with no official membership/source
claim. Expected selected identity is distinct from actual admitted identity.
Missing mapping leaves the latter null, while every requested member survives.

Validate admitted canonical `(ISIN, exchange)` uniqueness across **all** chunks.
Default admitted ISIN/exchange/effective symbol must equal its selected witness
member; mismatches are terminal even when another fact is missing. Preserve
child reports and hashes unchanged. Global identity uses the complete ordered
list; never average per-batch metrics or combine local boolean claims. Recompute
the existing session/price-basis/schedule/source-profile equality across all
admitted base features and separately across all candidate rows. Missing facts
make their applicable global comparability false. Equal descriptive tuples never
establish a shared acquisition cutoff. No cohort-dependent calculation is added.

Final compact UTF-8 JSON plus LF is buffered and bounded at **11 MiB**, enough
for at most ten existing 1 MiB child reports plus bounded selection metadata.
Each child retains its independent bound. Exact bound is admitted; bound+1 is
terminal before stdout. No raw CSV/bars, numerical prices, private paths or
exception text is emitted. Report/result identity hashes canonical bytes with
its own result identity excluded, using existing canonical hash conventions.

CLI exits 0 when every required G01 fact/candidate is available, 1 for a complete
report with unknown/insufficient members, 2 for invalid/integrity/internal or
interrupted execution. Missing/unsafe/corrupt selector evidence returns 1 with
fixed `selection_unavailable` and no report, before producer effects; malformed
inputs/future cutoff return 2 `request_invalid`. Other terminal failures return
2 `selection_research_failed`. Invalid input precedes selector unavailability;
terminal producer/mapping integrity precedes missing facts. There is no partial
stdout if any later chunk fails. Already retained producer effects survive
interruption; explicit retry revalidates selection and existing producer caches.
No rollback deletion or new persistent state is needed.

## Full acceptance matrix, frozen before implementation

| Row | Observable result | Prohibited effects | Evidence method |
| --- | --- | --- | --- |
| A1 default positive | All 100 exact ordered witness members, ten original child reports, one call each; truthful global identity | Omission, extra provider/candidate call, membership as eligibility | Real V2 synthetic collaborators + installed SDK/CLI |
| A2 explicit bounds | 1, 10, 11, 100 supported; 0/101, malformed/type/duplicate/relative roots and mixed modes reject | Producer/selector effects on invalid inputs | Boundary SDK/actual CLI tests |
| A3 selector admission | Exact current canonical request, three witnesses, hash/order/member/knowledge binding | Authored member input, new acquisition, repair or fallback | Existing retained-store tests plus integrated default tests |
| A4 insufficiency | Preserve every unknown/missing/unsupported member and independent facts; exit1 | Drop/replace member, hide valid Structure through optional absence | Real producer per-feature cases across chunk boundary |
| A5 conflict/provenance | Global aliases and default canonical mismatch terminal; wrong typed profile/source/revision/request rejected | Partial report, invalid facts winning over missing facts | Real producer adversarial and existing G01 regression |
| A6 global semantics | Full-list order/canonical/result identities; source/order/revision changes appropriate identity; equal local booleans cannot mask cross-chunk mismatch | Fake global comparison/shared cutoff, batch averaging | Different admitted sessions/profiles across partitions, independent hash oracle |
| A7 temporal authority | Retrieval<=capture cutoff<=trusted now; no retrospective membership or research-cutoff claim | Future/backdated evidence or expiry rule | Exact equality and plus-one time cases |
| A8 limits/privacy | 11 MiB exact/plus-one before stdout; old child bound retained; fixed errors, no raw prices/CSV/paths/leaks | Unbounded/partial output or disclosure | Canonical serialized boundary and actual CLI captures |
| A9 interruption/retry | Later member/chunk exception and KeyboardInterrupt produce no report; retry revalidates/cache reuse | Auto-retry, deletion/rollback of retained evidence | Deterministic interruption/recovery tests |
| A10 shared authority | Concurrent invocations isolated; held/unsafe selection root fails before producer; same-root lease released before research | Shared mutable invocation state, lease bypass | Existing lease reader cases + integrated invocation tests |
| A11 compatibility | G01 ten-stock bound/schema and standalone screen remain unchanged; existing capture/store/read-only contracts supported within existing window | Old artifact relabeling, state migration, wider core bound | Existing regressions, installed/native and prior-wheel qualification |
| A12 delivery | Two exact independent complete reviews; all applicable full tests/87% coverage/statics/build/installed/native/security; normal merge/main/private pull/tracker receipts | Gate waiver, local heavy work, paid/public/access changes, false whole-tool claim | Hosted exact-candidate and complete closeout evidence |

Root is the sole implementation writer/coordinator; independent domain and
privacy/provenance reviewers inspect a clean committed complete candidate and
do not mutate or delegate. Owned paths: new selection orchestrator/manifest,
minimal public retained-selector reader, CLI, meaningful focused tests and
existing installed qualifier, necessary inventory/golden updates and all
mechanically bound manifests, Plan62/Sprint49/current roadmap G02 documentation.

The **first working slice** is actual explicit 11-stock SDK/CLI plus exact
default 100-stock orchestration. All A1–A12 remain mandatory for full delivery.
Later improvements are live-source G08, AI G06/G09, eligibility G03, policy G04,
persistence/revisit G05 and broader integration/observation G10–G12. No new
provider/model, analytical family, threshold, fallback, replay/store, automatic
research/AI transmission, Future issue, portfolio/capital or CI-policy rewrite.

Cheap deterministic focused/static checks first; no heavy local suite/build/OCI.
Owner standing October7 approval covers routine in-scope hosted/GitGuardian and
normal merge after exact gates. Fresh account allowance and Actions/Packages $0
paid-budget StopYes readback precedes ready CI. One full90-minute hosted run,
exact main admission and private60-minute publication; no blind reruns/new
capacity/settings/access/visibility/bypass/deletion. Genuine changed authority,
scope, unavailable allowance or invalid evidence blocks only dependent effects.

G02 remains open until full delivery. Verified closure decreases Plan61's finite
remaining outcomes **11→10**, not a promised sprint count. G08/G09, complete
product/signal phase, Windows and Issue250 remain separate.
