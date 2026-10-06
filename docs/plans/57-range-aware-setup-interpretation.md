# Plan 57: coherent range-aware external candidate interpretation

Status: accepted bounded Sprint43 specification under the owner's October6,
2026 next-sprint same-workflow/approach/process direction and standing full
routine delivery authorization. Outcome and risk owner: Krunal Dodiya.
R3 public financial-research consumer interface, privacy and provenance.
Base `6415ff7e0bf5584458f2e9065f25196245377614`, published Sprint42 main.
Live Issue/milestone/private Project identifiers belong in the freeze receipt.

## Necessary question and smallest first working slice

1. Value: can an external consumer acknowledge the delivered latest completed range alongside continuity, invalidation, age and close relation for one exact admitted pair, with false structured claims rejected?
2. Fit: coherent signal-generation research evidence; reasoning stays external and eligibility/effectiveness unassessed.
3. Risk: independently acquired revisions joined, range omitted/substituted, inclusion promoted to exact traded tick/successful retest/confirmation, or previous closed contracts silently changed.
4. Smallest alternative: combine unchanged Plan55 v2 evidence and Plan56 range on the same two typed observations and extend the checker in a separate v3 contract. No new market calculation, source, model, store or policy.
5. Disposition: accepted after actual guarded synthetic producer pairs retain identical SAME_EVENT/no-contradiction/age1/closeABOVE facts but opposite range relations, while the current v2 checker correctly rejects an extra range claim.

Plan34 necessity is coherence and checked consumer binding, not another
analytical calculation or market usefulness claim. Existing revision hashes
differ correctly but are not semantic range facts. Separate commands require
the consumer to reconcile acquisition identities; v3 owns one exact pair and
checks its acknowledgment. All five Future issues remain excluded.

First working path: both spans and clear-above pairs through real admitted
SDK and injected CLI, preserving existing four components verbatim and rejecting
a false range claim. Then complete every matrix row below in this same sprint.
Later retest/expiry/eligibility/monitoring/model-evaluation policies are excluded.

## Closed SDK contracts

`assemble_setup_evidence_v3(previous, current)` accepts exactly two typed
CURRENT_STRUCTURE CurrentStockResearchResultV2 observations. Call unchanged
`assemble_setup_evidence_v2` once and unchanged `observe_setup_level_range_v1`
once on that same pair. Preserve complete producer/packet/runtime/source/bar/
diagnostic/time/canonical mapping/basis admission even on inconclusive inputs;
no authored JSON component or bundle may substitute for typed admission.

Require equal previous/current observation hashes and full redacted rows in
all five components. Verify range unsigned identity, its exact continuity
identity/status and level result reference, and the preserved level witness.
Any inconsistent join is terminal, including UNKNOWN/replay inputs.

Output `causal-setup-evidence@v3` retains exactly the unchanged four v2 full
components `continuity`, `invalidation`, `age`, `level` and adds the complete
unchanged `level_range`. Retain existing criterion, observation references and
legacy v1 reference; add `legacy_evidence_v2_identity_sha256` referencing the
regenerated v2 bundle. Own runtime and unsigned result identities bind the
whole report. No aggregate verdict. Fixed limitations preserve earlier limits
and explicitly state inclusive low/high containment is descriptive, proves no
exact traded tick, successful retest, confirmation, validity or eligibility.
Sorted compact JSON plus LF; canonical whole output <=1MiB atomically.

`setup_interpretation_request_v3_from_json(raw)` and
`check_setup_interpretation_v3(previous, current, response)` preserve Plan53/55
parser, narrative/posture, bounds and validation precedence. Exact schema
`external-setup-interpretation-request@v3`; exact five facts are `continuity`,
`invalidation`, `age`, `level`, `level_range`. Original four claims retain exact
fields/types. New range claim has exactly `result_identity_sha256`, `status`,
`range_relation`; relation is CONTAINS_LEVEL/ENTIRELY_ABOVE/ENTIRELY_BELOW or
null, without coercion. Reuse unchanged v2 normalization for the original four.

Validate complete response before observation/source access; regenerate v3
bundle once and require exact bundle identity and every structured claim.
Changed status/relation/null/hash, omitted/extra/swapped facts, wrong canonical
stock/revision, count/bool substitution and v1/v2/v3 substitution are terminal.
The consumer cannot supply a trusted precomputed bundle.

Output `external-setup-interpretation-check@v3` retains Plan53/55 labels, full
v3 evidence, normalized caller response/hash and own runtime/result identity.
STRUCTURED_BINDING_ONLY; narrative truth/authorship, actionable recommendation,
eligibility and effectiveness NOT_ASSESSED. RESEARCH_ONLY/NO_TRADE remain caller
postures on every factual state. Narrative is untrusted caller text, never a
market fact/diagnostic. Canonical whole output <=1MiB before stdout write.

New closed source-at-rest manifests bind new v3 SDK/CLI files and unchanged
reused v2/v1 validation helpers/private input-reader source as applicable.
Include unchanged v2 evidence and range runtime identities transitively.
Missing/extra/changed inventory/source is terminal even on inconclusive inputs.
Format changed sources before refreshing manifests. Old source/manifests stay.

## Injected CLI, bounds and failure effects

New `setup-evidence-v3` and `setup-interpretation-v3` adapters retain the existing
symbol, absolute storage root, exact previous/current selection timestamps,
CURRENT_STRUCTURE port and output=json selectors. Interpretation retains the
absolute --interpretation-file and unchanged owner-private no-follow bounded
single-link regular-file reader. Read one response once, acquire exactly two
serial selector-bound observations, compose/check once. No additional acquisition,
provider/network/model/credential/write/backdating/automatic retry authority.

Request/file/parser error exit2 request_invalid with zero service calls and
empty stdout. Read interruption uses fixed setup_interpretation_failed.
Observation/admission/runtime/join/binding/serialization/overflow/interruption
error exit2 fixed setup_evidence_failed or setup_interpretation_failed, empty
stdout. Successful exit1 if any of the five components is inconclusive under
unchanged v1/v2/range status sets; otherwise0. Replay/no-baseline/no-later are
not process failures; exit0 never grants eligibility or narrative truth.

Finite limits: one stock, two observations, existing21-session windows, one
latest completed bar; response1..65536bytes, unchanged2048-character narrative
bounds and parser rules; whole output1MiB. No tolerance, new price arithmetic,
inferred within-bar order or transaction guarantee for OS stdout write failures.
Pure repeat/concurrent calls are deterministic, input-preserving and write-free.

## Frozen adversarial and full delivery matrix

| Case | Required observable proof |
| --- | --- |
| Distinct working path | Actual admitted spans/clear-above pairs with identical old semantic facts; five coherent components; SDK and actual injected CLI byte equality; exactly two calls |
| Preserved range semantics | Contains/above/below/low-equal/high-equal and exact original witness/reference; no close-driven verdict, tick/retest/eligibility interpretation |
| Independent facts/states | Invalidation/age/close remain independent; replay/no-baseline/no-later/unknown/revised/absent/window/noncomparable and null range preserve original contracts; caller NO_TRADE remains optional posture |
| False response | Wrong bundle/component/stock/revision identity, range status/relation/null, omitted/extra/swapped fact, bool/count substitution, schema v1/v2/v3 and actionable posture rejected |
| Complete admission/precedence | Malformed response before effects; complete typed packet/source/runtime/diagnostic/time/anchor admission before successful output even unknown; authored component rejected |
| Composition integrity | Changed component rows/observation hashes/continuity/level reference/witness/unsigned identity terminal; no partial or relabelled UNKNOWN; original four components exact |
| Parser/resource bounds | 1/65536/plus-one bytes, nested duplicate/nonfinite/deep/UTF8/schema/type errors; narrative2048/plus-one/blank/control/surrogate; canonical1MiB/plus-one atomic |
| Private reader/effects | Owner/private/no-follow/single-link/regular/size/change checks retained; request invalid zero calls, no network/model/write/secret/raw market/path leak |
| Interruption/retry/concurrency | Reader/second observation/component/serialization interruption empty output; explicit retry deterministic, concurrent pure calls/input immutability, prior wheel rollback |
| Source/compatibility | New closed manifests and unchanged transitive closures; all prior public sources/manifests/contracts/dependencies/workflows unchanged; all eight prior installed maps retained verbatim |
| Actual installed distribution | Isolated installed -I SDK/injected CLI contains/above/below/low-equal/high-equal/replay/unknown plus independent invalidation and NO_TRADE; false range claim rejected; strict nested envelope/hash/witness/canonical privacy/provenance closure and original component equality |
| Full lifecycle | Both complete independent exact-candidate domain/privacy-provenance reviews; GitGuardian/full hosted tests>=87% branch/static/sdist/wheel/nativeOCI/adversarial/interruption/priorwheel; normal merge/exact main/private immutable publication/fresh pulls/full archives/live tracker/localmain then final full original-scope audit and Goal complete |

## Ownership, Goal and delivery authority

Coordinator is sole writer/integrator/tracker owner; no nested delegation.
Owned: new v3 evidence/interpretation SDK/CLI/manifests, new focused tests and
guarded actual-producer demo, append-only new Linux verifier definitions/calls/
receipt fields and focused verifier tests, Plan57/Sprint43/operator/small related
roadmap docs. No old SDK/parser/private-reader/producer/market calculation,
old manifest, dependency, workflow, retained-data or global setting edit.
Existing verifier definitions/tests preserved; new acceptance closes every
nested component under the current PROV1 contract, including independently
verified original Plan54/56 references; no resealed qualifier bypass.

Handbook typed-contract sections plus TDD/governance/GCS controls and requirements
specification fallback apply; no trusted original procedure identity established.
Use approved owner .venv outside worktrees with candidate imports; no installs,
copies or heavy local qualification. Tests first/focused/static feedback then
stable committed candidate, two independent read-only fresh complete R3 reviews
with exact base/head/tree/full diff/matrix and all observed evidence. Verify
pre/post clean identities and complete native results; no inherited approval.
Submit long reviews asynchronously and return foreground control; consume actual
native completion events, do not poll/sleep/callback-message reviewers.

Start persistent Goal only after this exact Plan/Issue/private Project/Sprint43
freeze and supported field/project/context readback. Standing owner authority
covers routine implementation/repairs/review/draft-ready PR and gated normal
merge, exact main/private publication/fresh pulls/archives/tracker/localmain
closeout. No redundant approval. One initial stable reviewed hosted qualification
for Sprint43 is authorized under that same workflow; no automatic rerun.

Issue250's current hosted-only zero-overage controls and retained accepted
90-minute/compact diagnostic workflow supersede the historical self-hosted
paragraph for this slice. Preserve that exact current workflow. Fresh shared
included allowance/storage/reset and Actions AND Packages$0 StopusageYes,
whole-account no-active-run/no-error inventory and reserve>=300minutes are
required before every hosted trigger and merge. No paid/public/access/settings/
heavy-local/self-hosted workaround, longer cap, lowered gate, admin/directmain,
cleanup/deletion or unapproved repeat. Failed execution remains failed; stop
only dependent release until bounded evidenced correction or owner direction.

Preserve all10 previous checkouts and all prior evidence. Actual new source/
review/gates/release/live tracker/localmain/full13requirements/8criteria/12matrix
must agree before Goal complete. All eight Plan47 obligations remain distinct;
overall signal phase/product qualification incomplete. Windows/historical
private_source cases/CI retirement remain separately governed. No Future, new
source/model/policy/store/history/first-or-any-contact/tick/retest confirmation/
expiry/eligibility/monitoring/broker/money/risk/capital/position expansion.
