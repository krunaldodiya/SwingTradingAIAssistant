# Plan 61: first-use reconciliation and next working research path

October 6, 2026. [Issue #278](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/278),
Sprint 47 / milestone 39, private Delivery Project. Owner and risk owner: Krunal
Dodiya. R3 planning/provenance. Base `03ba7e1b921da8bbdef1c4b4de46d1d4472f30ce`.
Authority: the owner continued after roadmap PR #277. Sprint 47 planning was
delivered through PR #281 / main `15c007111b4706d5a4fea2627d15766cde9f0698`.
The frozen G01 contract below was subsequently implemented and qualified by
[Sprint 48](../sprints/sprint-48.md) / Issue #282 / PR #283. The original planning
boundaries and acceptance matrix remain the contract, not a whole-tool claim.

## Evidence boundary

The current-main source, accepted contracts and live GitHub state control this
reconciliation. Older Plan/Sprint status prose is retained history. Live reads
confirm Issues #172, #183, #186–#190, #213, #226, #230, #235 and #248–#274's
selected delivered slices closed; #250 remains open for CI migration closeout.
Issue #246 owns the delivered detection slice. No old checkpoint is reopened.

The exact runtime inherited from Sprint 46 is unchanged by roadmap PR #277.
Sprint 46's retained evidence proves its selected 8400-test/87.84%-coverage,
installed/native OCI, recovery, independent-review and private-release scope.
It is not a new Sprint 47 execution or proof of real AI quality, a usable
Nifty 100 suggestion workflow, eligibility or market effectiveness. Source
inspection proves a callable path or limitation, not successful live use.

The task evidence retains live Issue reads, source observations, identities and
the completed roadmap handoff. No provider, private market store or AI service
is executed for this reconciliation. Source/model/disclosure authority must be
resolved for the later claim that needs it. In particular, Plans 37–38's
NSE-derived context stays owner-private, including redacted counts/provenance;
an installed cloud assistant is not automatically an authorized destination.

## Delivered foundation and exact remaining boundary

| Foundation in current main | Contract/source to reuse | Proven boundary and remaining gap |
| --- | --- | --- |
| Current official Nifty 100 capture selection | Plan 33 successor; `market_data/efficient_current_nifty100_adjusted_capture.py` | Exact current-at-retrieval witnesses and 100-member capture accounting; not historical membership before retrieval, an eligibility policy or a 100-stock agent report. |
| Explicit stock research | #186–#190; `market_data/current_stock_research_v2.py`; `market_data/agent_research_run.py` | Public explicit 1–10-stock report; each admitted price/structure fact survives independent insufficiency. V2 report has an explicit one-session fallback. Neither list scope nor READY means trade eligibility. |
| Necessary Structure and Price Action | Plans 31–32; `market_structure/current_live.py`; `price_action/current_live.py` | Confirmed pivots/trend/BOS/CHoCH and candle/previous-close facts. The compact agent report currently projects only candle direction, previous-close relation and structure state/trend, not the candidate anchors. |
| Volume and stock-reference Relative Strength | Plans 39, 41–42; `volume_analysis/current.py`; `relative_strength/current.py`; `market_data/agent_analysis_context.py` | Agent V5 already integrates both. RAW retained Upstox facts have independent dates/bases/cutoffs from BharatStock dossiers; no common snapshot, liquidity adequacy or effectiveness is inferred. No need to build this integration again. |
| Events, regime and literal Industry context | Plans 37–38; `market_data/agent_event_context.py`; `market_data/agent_cohort_context.py` | Existing additive V3/V4/V5 context; separate observations and source-use limits. No notice in one snapshot is not absence of event risk; an explicit comparison cohort is not an official market/index. |
| Latest causal candidate detection | Plan 47 / #246; `market_data/setup_screen.py`; `market_data/cli.py` | Real public `market-data setup-screen-current`, 1–10 stocks, latest UP BOS MATCH/NO_MATCH/UNKNOWN, confirmed anchor, observation identity. Separate from the agent dossier and not active signal/entry confirmation. |
| Pair evidence and factual response checking | Plans 48–60; `research_comparison/setup_evidence_v4.py`; `setup_first_inclusion_close.py`; `setup_interpretation_v4.py` | Typed SDK and injected CLI pair paths, finite-window continuity/invalidation/age/level/inclusion facts. Response checker binds caller-supplied facts; narrative truth/authorship/eligibility/effectiveness remain unassessed. |
| Production pair access limitation | `research_comparison/setup_evidence_v4_cli.py`; `current_stock_observation_comparison_cli.py`; `pyproject.toml` | Pair CLI requires an injected observation service. No installed production selector/replay path is established by those demos. A requested past selection time cannot be supplied by newly acquired evidence. |
| Historical/prospective foundations | Plans 10–11, 18, 28–30; `historical_evaluation/` | Existing evidence/readiness/validation capabilities remain reusable, with their exact admitted profiles. They are not a strategy-specific backtest, evaluated real AI policy or paper observation of a not-yet-frozen suggestion contract. |
| Loss scenarios and release machinery | Plans 43–46; current hosted workflows and Sprint 46 receipts | Delivered caller-assumed loss/cost/exit facts are not a sizing or portfolio policy. Existing release controls remain mandatory for later executable work; #250/Windows/local CI retirement remain separately governed. |

## Eight first-use outcomes reconciled

Every row is **PARTIAL**, not finished as a whole-tool outcome. The foundation
above is reusable; the named gap's closure evidence supplies the missing claim.

| Roadmap outcome | Reuse now | Remaining gap IDs |
| --- | --- | --- |
| 1. Choose exact stocks | Current-at-retrieval selector/capture; bounded explicit research and canonical mappings | G02, G03; no 10-to-100 extrapolation or membership-as-eligibility. |
| 2. Coherent current research | Agent V1–V5 plus delivered G01 same-observation bridge, independent price/Structure/Volume/RS/context | G06, G07, G08; retain independent bases rather than manufacture comparability. |
| 3. Explainable candidates | Public latest detection, delivered G01 same-observation bridge and bounded pair facts | G04, G05; facts alone do not define generation or active validity. |
| 4. Safety and eligibility | Existing identity, mapping, data/price and source admission | G03; missing listing/history/liquidity/price/event requirements need an evidence-backed contract. |
| 5. Understandable external-AI output | Agent fact reports and structured pair-response checkers | G06, G09; synthetic caller responses do not qualify a real suggestion policy. |
| 6. Practical end-to-end workflow | Installed bounded explicit-list commands and private source workflows | G02, G08, G10; default and explicit lists both need their declared success/negative/unknown paths. |
| 7. Qualified first usable release | Exact current hosted/review/package/receipt mechanisms | G09, G10; existing component delivery is not whole-workflow qualification. |
| 8. Observe and improve | Retained data/evidence and bounded comparisons | G11, G12; actual opportunity/decision/outcome observation is still missing. |

## Finite remaining outcomes

October 9 Sprint 52 checkpoint: [Issue #292](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/292)
is repairing the initial decision implementation under
[Plan 66](66-source-bound-supported-decision-repair.md). The active slice is a
source-bound `UNKNOWN`/`NO_TRADE` boundary; G03 eligibility and G04 actionability
remain open until their missing evidence capabilities are separately admitted.

October 7 Sprint 51 delivery: Issue #290 / PR #291 delivered the retained
observation and comparison workflow under Plan 64.

October7 next-sprint checkpoint: [Sprint50](../sprints/sprint-50.md) /
[Plan63](63-stock-eligibility-safety-readiness.md) / Issue288 reconciles the
existing and missing G03 safety evidence and the independent G05 observation
access prerequisite. It is a bounded design delivery; it selects no numerical
eligibility rule, new source or persistence implementation. G03 remains open,
and the count remains ten. The Sprint49 delivery below remains verified history.

October7 delivery checkpoint: [Sprint49](../sprints/sprint-49.md) /
[Issue285](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/285)
closes G02 under all twelve frozen
[Plan62 rows](62-exact-selection-whole-list-research.md). Both complete exact
independent reviews, 8,513 tests / 87.88% coverage, build/installed/native/security,
normal merge, strict main admission, private publication/fresh pulls and live
Issue/Project/milestone closeout pass. Code main is
`c7f4b77c8e43e7c7e2e05514fbf5f0ee2bcbfe9b`; the Sprint49 record retains exact
receipts and earlier failures. Synthetic qualification does not close G08/G09
or the product. Earlier Sprint47/48 contracts retain their dated scope.

As of October 7, Sprint48 closes G01 and Sprint49 closes G02 with the exact
evidence in their delivery records. The original baseline was 12 open outcomes;
**10 distinct outcome gaps remain open (G03–G12)**, counted once despite appearing
in several checklist rows. G01 and G02 remain below as CLOSED for an auditable
countdown. BEFORE means before the full first-use claim named in
that row. OWNER means a required contract/disposition decision for that claim,
not optional safety. AFTER can follow qualified research use, with its own
before-real-money/performance/phase-completion gates intact. A research-only
prefix does not satisfy the complete signal/suggestion product goal.

| ID / stage | Exact outcome still required | Dependencies | Observable closure evidence |
| --- | --- | --- | --- |
| G01 / CLOSED — Sprint 48 | One same-observation current research report with existing causal candidate facts | Existing current producer/report and Plan 47 | SDK/installed public CLI, all nine adversarial rows, two exact reviews, 8453 tests / 87.85% coverage, main/private release and tracker receipts verified; see the Sprint 48 record. Synthetic qualification does not close G08/G09. |
| G02 / CLOSED — Sprint49 | Exact retained CURRENT_AT_RETRIEVAL Nifty100 selection into whole-list research, plus explicit 1–100-stock bounds | Existing selector/capture; G01 | All twelve Plan62 rows; exact complete reviews, 8,513 tests / 87.88% coverage, installed/native/prior-wheel/security, main/private release and tracker receipts verified; see the Sprint49 record. Every member/order/unknown accounted for; no averaged batch verdict or shared acquisition cutoff. Synthetic qualification does not close G08/G09. |
| G03 / OWNER, before actionable suggestion | Objective capability-specific eligibility/safety evidence | Existing canonical/source admission | Accepted listing/history, mappings, data quality, liquidity/turnover, price integrity and event-risk requirements, source authority/knowledge times, fail-closed implementation and adversarial evidence. No arbitrary threshold or exemption here. |
| G04 / OWNER, before active/actionable signal | Generation, confirmation, validity/expiry, correction and duplicate policy | G03; existing detection/pair facts | One explicit versioned decision policy with causal accepted transitions, no-trade/unknown rules and demonstrated information need; independently qualified without promoting age or level inclusion into a trade rule. |
| G05 / BEFORE production lifecycle use | Obtain/revisit exact producer-admitted observations for the existing pair workflow | Existing typed comparison contracts; G04 for policy transitions | Real installed observation selection/readback across actual observations, exact source/known-time/revision binding, retry/correction and missing-baseline behavior. Specify persistence only if necessary; never backdate fresh acquisition. |
| G06 / BEFORE supported AI suggestions | One admitted factual input and checked external response covering the chosen working policy | G01, G03–G05 as applicable; existing V5/pair checker | Versioned closed response/evidence contract, authorized destination/source use, real prompt/model-bounded interpretation evaluation and unsupported-claim behavior. Keep deterministic facts, untrusted explanation and authorship limits distinct. |
| G07 / OWNER, before selected-policy qualification | Explicit necessary analytical-family disposition | Plan 34; G03/G04's concrete decision | Reuse delivered families; record the necessary-only acceptance/defer/reject decision for any missing fact. Fundamentals/source and liquidity adequacy/SMC questions remain explicit; Future scope is not imported. |
| G08 / BEFORE practical first use | Actual authorized source and workflow qualification | G01/G02; existing source-use contracts | Current approved source success, no-match/no-trade where the selected contract defines it, insufficient/unavailable and failure paths with actual timing/provenance/effect limits. Synthetic/closed Issue evidence alone cannot close it. |
| G09 / OWNER, before decision-support claims | Claim-specific historical and real-AI qualification | G03/G04/G06/G07 | Reproducible causal baseline and applicable historical coverage, opportunity retention/no-trade, out-of-sample/walk-forward, execution/cost/slippage and AI-replay evidence; documented pass rule/limits. Broader research may follow research-only use; mandatory evidence before decision support is not deferred. |
| G10 / BEFORE complete first use | Integrated supported workflow, instructions and exact release qualification | Required G01–G09 outcomes for the advertised claim | Default/explicit-list onboarding and real success/negative/unknown/failure scenarios, independent final reviews and every applicable test/coverage/build/installed/private-release/main/tracker receipt. This is an acceptance outcome, not a new framework. |
| G11 / AFTER research use; before real-money/performance claim | Authorized paper observation and measured improvement | Qualified G10; chosen versioned policy | Retained opportunities, decisions/no-trade and later outcomes with contemporaneous evidence, corrections, timing/execution/costs and a stated observation interval. No return claim from synthetic or incomplete observations. |
| G12 / AFTER; before signal-phase closeout | Every Plan 47 outcome delivered or explicitly owner-dispositioned | All applicable preceding gaps | Exact eight-outcome audit, remaining analytical/research/AI obligations resolved, independent review/gates and live tracker agree. Capital/portfolio expansion remains a separate segment, not silently removed. |

The remaining gaps have four BEFORE primary stages, four OWNER and two AFTER.
The original six BEFORE stages included the now-closed G01 and G02.
Dependencies are for the affected claim: G03–G09 do not block G01's explicitly
descriptive research-only bridge. They do block claims that need their evidence.
G01 and G02 are delivered. Remaining eligibility/safety, decision-policy,
real-workflow and AI dependencies are refined at their decision point; this
closeout freezes no new policy, source authority or implementation sprint.
This plan does not pretend to specify those outstanding contracts.

This is an evidence-backed outcome ledger, **not a promised sprint count**.
Sprint 47 planning closed no working-behavior gap. Verified Sprint 48 G01
delivery reduced the original baseline from 12 to 11; verified Sprint49 G02
delivery reduces 11 to 10. No gap was added or removed by rescoping. A gap closes
only on its named evidence, not because a document or helper exists.
Splitting work preserves its parent gap; merging slices does not hide unresolved
outcomes. Additions identify source, necessity and owner/Issue before the count
changes. No next implementation sprint is allocated by this closeout; a
defensible whole-tool sprint estimate requires the remaining contract decisions
and slice sizes. The old 20–30 forecast is not refreshed or repeated as a countdown.

## All eight signal-phase obligations retained

| Plan 47 outcome | Current disposition / remaining evidence |
| --- | --- |
| 1. Causal public detection | Delivered narrow latest-BOS path and G01 current-research bridge; G08 still qualifies actual use. No broad setup catalogue. |
| 2. Necessary analytical coverage | Delivered Structure/Price Action/Volume/RS/context reused; G03/G07 explicitly resolve remaining family needs. |
| 3. Generation responsibility/identity | Observation-bound identity delivered, external reasoning ownership unchanged; G04/G06 remain. |
| 4. Confirmation/invalidation/expiry/duplicates | Pivot/BOS timing and descriptive anchored facts delivered; G04/G05 own actual policy and correction/duplicate semantics. |
| 5. Observable lifecycle | Pair facts are delivered in-process; G05/G11 must prove production observation and authorized lifecycle use. |
| 6. Coherent context/safety | Existing additive contexts remain; G03/G06/G07 resolve mandatory safety, evidence and source-use boundaries. |
| 7. Correctness/AI/effectiveness separation | Component correctness remains delivered; G08/G09/G11 provide distinct real-workflow, AI and effectiveness evidence. |
| 8. Verified phase closeout | G12 remains open. Planning, research-only use or an isolated green suite cannot close the phase. |

## Analytical-family disposition

Structure, Price Action, Volume, stock-reference RS and current regime/Industry/
event facts are **REUSE** within their exact existing contracts. Technical
analysis needs no separate indicator collection for G01. Liquidity adequacy is
a **REQUIRED SAFETY QUESTION** under G03; daily volume is not adequacy. A new
sweep/reclaim or other SMC fact is **UNSELECTED**, with no distinct G01 need.
Fundamentals is an **OPEN OWNER DISPOSITION** under G07 for the chosen decision;
there is no admitted company-data source or threshold in this sprint. This does
not adopt or indirectly reactivate Future #178. Future #126, #139, #144, #177
and #178 all remain excluded. Additional patterns/indicators/ranking, portfolio
and capital expansion are not G01 scope. Delivered loss assumptions remain
supported; they cannot become risk approval or sizing by implication.

## Smallest next working path: current research plus causal detection

1. Value: an external consumer can read current price/structure context and the existing latest upward-BOS observation in one source-bound report.
2. Fit: a descriptive explicit-list research path, connecting delivered capabilities instead of adding another calculation or signal rule.
3. Risk: separate requests mix revisions; a copied report becomes evidence; missing optional facts hide candidates; a BOS label is mistaken for eligibility or advice.
4. Smallest alternative: reuse the current typed producer, compact report and Plan 47 selector on the same captured results. Manual joining two commands cannot establish that same-result binding; external AI may not recalculate the criterion from raw bars.
5. Disposition: selected for the next separately governed implementation sprint; no source/model, strategy, eligibility, fallback or persistence expansion.

### Interface, admission and composition

Add `market-data setup-research-current --symbol SYMBOL [--symbol SYMBOL ...]
--storage-root ABSOLUTE_PRIVATE_ROOT --output json` and SDK
`run_agent_setup_research_current(symbols, storage_root, *, research)`.
Production dispatch uses the existing `research_current_stock_v2`; SDK injection
is the established testing seam, not admission of caller-authored fact JSON.

Accept the existing 1–10 distinct valid symbol tuple and absolute owner-private
root. Requested duplicates, malformed symbols, 0/11, wrong types and relative
roots fail before producer effects. Canonical alias collisions discovered by
admitted mapping fail before output, without claiming they were knowable before
acquisition. Preserve requested order and every missing/unsupported member.

Delegate once to unchanged `run_agent_research_current` through an invocation-
local capture wrapper: exactly one serial real V2 producer result per stock,
`question=INTEGRATED_CURRENT_RESEARCH`, `refresh=False`. Keep precisely those
typed results for the candidate projection; do not invoke `setup-screen-current`
as a second acquisition. The captured objects are not a persistent archive.
Do not change the producer's question on an object or reconstruct it from JSON.

Reuse complete V2 result/packet/runtime/mapping/source/known-time admission.
Extract Plan 47's existing latest UP BOS predicate through one shared internal
projection accepting the explicitly bound integrated profile for this new path.
The old screen must still require CURRENT_STRUCTURE. Preserve its public schema,
criterion, causal rules and identities; factor the selector rather than duplicate
market arithmetic. Check canonical identity, packet/result/source/basis/session
binding against the base report before attaching each candidate. A supplied
digest or a compact dossier alone is not an admitted Structure result.

### Output and factual outcomes

Return closed `agent-current-setup-research@v1` with runtime identity; unchanged
base report under `research`; `base_research_report_identity_sha256`; Plan 47
criterion; requested/canonical order identities; ordered `members` containing
the existing descriptive candidate-row projection; `candidate_jointly_comparable`
with Plan 47's exact scope; fixed limitations; and `result_identity_sha256`.
The base-report digest binds its existing canonical bytes; the final digest
binds the new report excluding its own digest using the existing canonical
serialization convention. Bound complete UTF-8 compact sorted JSON plus LF to
1 MiB before emission. No raw bars, numerical prices, bodies, paths or exceptions.

Every candidate is MATCH, NO_MATCH or UNKNOWN by unchanged Plan 47 admission,
including its earlier-confirmed high anchor. Candidate identity uses its existing
criterion/canonical/basis/source/revision/event/pivot binding. Identical admitted
Structure anchors/source produce the same candidate identity; no durable signal
identity or cross-window duplicate policy is inferred. Preserve all original
base fields, per-feature insufficiency and provenance. Its price-only comparison
does not expand to optional analysis, and candidate comparability is not a shared
acquisition cutoff. Same typed producer result is the composition guarantee.

Missing Geometry/previous-close or unacquired context cannot hide a valid admitted
Structure candidate. Insufficient Structure is UNKNOWN, not NO_MATCH; invalid
source/runtime/typed response/anchor/identity/order binding is terminal even if
another fact is missing. MATCH/NO_MATCH describes detection, never BUY/SELL,
ACTIVE/ELIGIBLE or a tool-generated NO_TRADE recommendation. The report explicitly
states eligibility, entry confirmation, validity/expiry, lifecycle, AI quality and
effectiveness are not assessed. No scoring/ranking or new interpretation text.

Exit 0: all base price/structure facts available and all candidate rows MATCH or
NO_MATCH. Exit 1: at least one required projection unavailable/UNKNOWN, with the
complete honest report. All-NO_MATCH may exit 0; exit 0 is availability, not trade
approval. Exit 2: request invalid or terminal admission/internal/interruption/
overflow failure, no partial JSON. Use sanitized fixed diagnostics
`request_invalid` / `setup_research_failed`; never private exception content.

### Effects, compatibility and acceptance

Only the existing producer's admitted current acquisition/retention and root
lease/deadline controls may occur in an authorized real invocation. The new
composition adds no provider, context request, credential read, retry, refresh,
hidden directory, archive or write. Invalid input makes zero producer calls.
This plan makes no live call and grants no new source/disclosure authority.
No fallback is added: this first path is latest-completed-session research;
the existing V2 fallback command stays independently available. Do not report
a lagged observation as latest or fabricate a historical baseline.

Rollback removes the additive entry point and leaves all stores and old commands
usable; no migration or new persistence. Future owned executable paths are
`market_data/agent_setup_research.py`, its runtime manifest, minimal shared selector
factoring in `setup_screen.py`, CLI dispatch, behavior tests/installed qualifier
and mechanically affected source manifests. Sources are formatted before bound
manifests update. V1–V6, existing standalone screen, pair contracts, Structure
mathematics and historical source identities remain supported.

| Acceptance case | Exact evidence for the next implementation |
| --- | --- |
| Working same-result path | Actual producer fixture, SDK and real installed public CLI; price context plus latest UP BOS with earlier-confirmed anchor, one serial integrated call/member, no second capture. |
| Negative / unknown / optional absence | Down/older BOS, CHoCH, no event; insufficient/missing Structure; Geometry/previous-close missing with valid candidate; optional context not acquired; complete rows, correct 0/1, no eligibility inference. |
| Inputs / bounds / aliases | 1/10 accepted, 0/11 and malformed/duplicate/relative/type rejected before effects; admitted canonical collision terminal before output; request order exact. |
| Admission and precedence | Wrong profile/symbol/runtime/packet/member/order/source/known time/anchor or authored JSON rejected; corruption wins over simultaneous missing fact. No relabelled result or copied dossier admission. |
| Identity and comparability | Identical observation stable; changed source/revision/order changes appropriate identities; base hash exact; candidate/base source links exact; independent producer dates retain truthful comparison limits. |
| Resource / privacy | Whole 1-MiB and plus-one before stdout; excluded private payloads and numeric prices absent from success and failure. |
| Interruption / retry / concurrency | Interrupted second stock emits no partial stdout; explicit identical retry revalidates; capture wrapper invocation-local, existing lease safety preserved. No background monitor. |
| Compatibility / recovery | Old screen projection semantics and agent V1–V6/pair contracts remain; source/runtime inventories complete; installed current SDK/CLI and prior wheel verified; no stored-state rollback. |
| Full qualification | Two fresh independent exact-candidate reviews, all applicable full selected tests/87% coverage/statics/sdist/wheel/installed/native OCI/security, normal merge/exact main/private publication/pulls/logs and tracker closeout under current authority. Synthetic success is not G08/G09. |

## Sprint 47 execution and completion

Only this Plan, Sprint 47 record and related current roadmap/overview Markdown
are changed. Root is sole writer. Source/execution receipts, old contracts,
tests/manifests/workflows/dependencies, owner checkouts and historical bodies
are preserved. Same saved-project numbered context reset is read back through
supported listing; no new conversation is created. Native Goal starts after
the seven-criterion Issue/Project/milestone/scope freeze.

Verification requires local `git diff --check`, inspection and both independent
exact-source domain and privacy/provenance reviews. The owner's October 6
correction permits lightweight GitGuardian, including the existing hosted App,
without a per-PR exception; it restricts long-running CI/CD for documentation.
[Issue #279](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/279)
delivers the dedicated canonical-policy correction and directly affected
procedure prose before this sprint's ordinary publication. The previous
all-GitGuardian prohibition and requested one-PR exception are superseded; their
receipts remain historical, not current requirements. No heavy test/build/release
pipeline, settings/access/budget change or bypass is introduced. Corrected bytes
need both new exact-candidate verdicts; the original complete reviews provide
bounded correction context, never approval of changed source. Ordinary PR,
exact merge equivalence, ancestry-safe main and live Issue/Project/milestone
readbacks close this sprint; source/spec completion alone does not.
Implementation of G01 and Sprint 48 are separate work.
