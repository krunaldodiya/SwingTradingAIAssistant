# Plan 44: agent hypothetical loss-scenario context

Status: frozen local implementation contract; not released.
Owner and risk owner: Krunal Dodiya. Sprint 30 / [#240](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/240), milestone 22. Risk R3.
Authority: October 2, 2026 request for Sprint 30 planning and implementation,
within the accepted agent-first research and descriptive risk direction.
Baseline: ade1ea4989a922e013c00f1d67c67878878482de.
Plans 42 and 43 remain authoritative for their reused producers. No release,
provider activation, live capture or strategy approval follows from this plan.

## Outcome and scope

An AI consumer can read one explicitly supplied hypothetical LONG NSE-equity
loss scenario beside its existing research dossier. Reuse Plan 43 arithmetic;
never infer entry, stop, quantity, holding period or a policy. First working
path: one synthetic stock through the actual V6 CLI with entry 100.00, stop
95.00, quantity 10, yielding gross scenario loss 50.00 INR. Complete the entire
bounded acceptance matrix after that path. Later: costs, sizing, automatic stops,
portfolio analysis, multiple scenarios and monitoring remain outside this slice.

## Interface and invariants

Add opt-in `market-data research-run-current --contract-version v6` and SDK
`run_agent_loss_research_current`. V6 keeps every required V5 input and adds
required `--loss-scenario-input-file ABSOLUTE_PRIVATE_JSON`, exactly the closed
Plan 43 request. Reuse the 64-KiB no-follow owner-private reader and parser.
V1–V5 reject this new option before effects, and retain existing meaning.
Revalidate direct SDK inputs. Validate the loss request and exact match of its
ISIN/NSE/symbol to precisely one requested analysis target before storage or
research effects; reference-only or unknown stocks are invalid. No implied
membership, listing, price or risk admission follows from this match.

V6 invokes the unchanged V5 preparation boundary and real loss calculator.
Before V5 effects, verify the loss runtime and validate the full analysis
request with its existing validator. Preserve V5's full invocation deadline,
root-authority checks, malformed/unsupported/insufficient states and sanitized
error semantics, including the final check immediately before emission.

Return `agent-current-research-run@v6` with all V5 facts and exit readiness
unchanged. Add `loss_scenario_context` containing the full Plan 43 result,
`observation_scope=CALLER_SUPPLIED_ASSUMPTIONS`, and
`jointly_comparable_with_market_evidence=false`. The matching dossier references
that result with request identity alignment and separate dossier identity
alignment (canonical match or unavailable). Other dossiers explicitly say
`NOT_REQUESTED`. Canonical mismatch is terminal. A missing dossier identity or
unavailable price fact does not suppress valid arithmetic or imply market
admission. No dates are invented for assumptions and no scenario can satisfy a
market-readiness requirement or alter stock exit status.

All Plan 43 limitations remain visible: costs/slippage excluded, instrument
verification not performed, market evidence not used, eligibility not assessed,
stop execution not guaranteed and actual loss may exceed the scenario.
Recompute the V6 canonical result identity excluding its own identity; retain
the original V5 result identity in an explicit source field. Bind changed code
and its dependencies in the active runtime manifests after formatting; preserve
historical frozen identities. Bound final canonical output to 4 MiB before one
write. No new archive, provider, dependency, persistence or delivery surface.

## Acceptance and adversarial matrix

- Actual CLI and SDK, exact 50.00 result, real retained analysis fixture and real
  V4/V5 composition; independent expected arithmetic, identity hash and labels.
- One and ten target bounds, matching first/last target, every other target
  explicit NOT_REQUESTED; invalid/reordered/duplicate/eleven target cases reuse
  V5 admission. Scenario for reference, unknown symbol, wrong ISIN/exchange,
  invalid fields/bounds, mutated SDK request, malformed/duplicate JSON and
  private-file violations fail before storage/research effects.
- Missing identity, unavailable optional analysis and unavailable stock research
  preserve independent scenario labels and original exit/readiness semantics.
- Runtime substitution, mismatched dossier, deadline expiry/clock regression,
  root substitution, unexpected failure and interruption cannot emit success or
  partial JSON. Combined invalid inputs cannot cause provider effects.
- V6 result/request identity changes with assumptions; deterministic retry,
  source/input preservation, complete output bound and limit-plus-one.
- Default V1 and explicit V2–V5 compatibility; new option rejected there.
- Focused checks, full Ruff format/lint, Pyright, Vulture 80, complete non-private
  test selection with branch coverage >=87%, sdist/wheel and clean installed
  smoke. Existing hosted/security/distribution gates remain pending until
  separately authorized push/draft PR; local evidence cannot replace them.
- Two independent read-only functional/domain and security/privacy/provenance
  reviews of the complete clean committed candidate; resolve concrete blockers
  before expensive final gates. Review pre/post commit/tree/clean checks.

## Execution and boundaries

Coordinator is sole writer and owns integration, scope and local validation.
Two native independent reviewers receive exact base/candidate/tree and complete
contracts; no nested delegation. Inherited model/effort; actual host telemetry
and a Fast-tier switch are unavailable. Persistent Goal is not exposed; use the
bounded ordinary workflow. Evidence and caches use visible Sprint30 workspace
paths; no new hidden folder is authorized. Existing Python 3.11 tooling may be
reused without changing it. All fixtures are synthetic; no live/provider call,
credentials, retained owner market data, Hindsight/recovery material, Samsung
drive, external publication, merge or deployment. Rollback is selecting V1–V5
or removing the additive V6 branch; no migration or evidence deletion.
