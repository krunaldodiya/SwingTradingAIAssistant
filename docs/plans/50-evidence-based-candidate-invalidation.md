# Plan 50: evidence-based candidate invalidation

Status: accepted bounded specification within the owner's October 5, 2026
Sprint 36 direction. Outcome and risk owner: Krunal Dodiya. R3: financial
research interpretation, causal timing and provenance. Base:
`9da48feb94e172223582503070a9cc4865d68181`.

Governing Issue: [#254](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/254).

## Necessity and independently derived condition

1. Value: answer whether later confirmed structure contradicts the continuation premise of one earlier upward BOS candidate.
2. Fit: bounded descriptive candidate invalidation, without trade eligibility, a recommendation, expiry or profitability.
3. Risk: arbitrary opposite events, revised inputs or window loss falsely treated as contradiction; future-confirmed lows smuggled into the original premise.
4. Smallest alternative: use the already admitted Plan31/47/49 facts and one original supporting low; no raw-OHLC calculation, new provider, threshold or catalogue.
5. Disposition: accepted, exactly one stock and two observations. A fixed anchored contradiction rule adds a distinct factual relationship that event representation alone cannot answer.

Under Plan31, UPTREND at an upward BOS is supported by the latest confirmed
HH high and HL low strictly before the breaking session. Freeze that latest
confirmed SWING_LOW/HL from the original calculation. A later admitted DOWN
CHOCH with prior_trend UPTREND, strictly after the original BOS session and
breaking this **same low**, supplies close-confirmed violation of that original
supporting structure. This is the only INVALIDATED condition in this version.
It contradicts the versioned continuation premise, not the historical fact
that the upward BOS occurred. A down BOS, a CHOCH at a different low, a wick,
a neutral trend or absence is insufficient for this particular criterion.
The low must have been confirmed strictly before the original BOS; a low
confirmed on or after that session cannot become the original anchor.

Plan34 admission: the unmet decision is anchored structural contradiction.
Existing facts provide all required capabilities in a finite 21-session window.
Cost is two finite scans. Expect evidence only while the original event and
supporting low remain represented unchanged. Synthetic evidence establishes
contract correctness, not market frequency, usefulness, filter improvement or
returns. This is additive interpretation, not a new scanner filter.

## Frozen observable contract

Pure SDK `observe_setup_invalidation_v1(previous, current)` accepts exactly two
typed CURRENT_STRUCTURE `CurrentStockResearchResultV2` observations. Call
Plan49 continuity first, retaining its complete Plan48/47 admission, integrity,
metadata bounds, compatibility, deadlines and knowledge ordering. No authored
candidate JSON, network, acquisition, clock, storage writes or persistent state.
Existing source-at-rest verification remains the runtime trust mechanism.

Resolve the unique original event and latest low confirmed strictly before its
session. Require SWING_LOW, HL, no unclassified reason, causal positions bound
to admitted sessions. Original and current low locus is kind, session and
confirmation session. Factual equality includes that locus plus price, relation
and unclassified reason; it excludes rolling positions and revision digests.
Require the original BOS and its high anchor unchanged under Plan49 before an
invalidation claim. Require the low also represented unchanged. Changed source
retrieval alone is compatible and both revisions remain visible. Duplicate
anchor/witness, inconsistent positions or types are terminal integrity failures.
Exactly one witness is possible under Plan31 first-crossing consumption.

Ordered outcomes after both complete inputs are admitted. Resolve original
event continuity first; supporting-low outcomes are examined only when the
original event is unchanged (SAME_EVENT):

- NON_COMPARABLE, UNKNOWN, NO_BASELINE: preserve Plan49 outcome/reason.
- REPLAY: identical admitted observations with a baseline; no later evidence.
- OUTSIDE_WINDOW: original event locus or supporting-low session/confirmation is outside the current admitted window.
- NOT_REPRESENTED: original event is no longer represented despite its sessions remaining; no contradiction inferred.
- REVISED_EVIDENCE: original event/high anchor or supporting low has changed factual evidence; reason distinguishes event from low revision.
- UNKNOWN: supporting low missing despite its sessions remaining, or unavailable original supporting anchor; fixed reason identifies this limitation.
- INVALIDATED: one strictly later causal DOWN CHOCH breaks the unchanged original supporting low while prior trend is UPTREND.
- NO_CONTRADICTION_OBSERVED: required original evidence remains unchanged but this specific witness is absent in the current admitted calculation. Never VALID, active, eligible or profitable.

Output `causal-setup-invalidation@v1`, criterion
`LATER_DOWN_CHOCH_OF_ORIGINAL_CONFIRMED_HL@v1`, own runtime identity, both full
observation hashes and Plan47 rows, Plan49 identity/status, status/reason,
original/current supporting-low projections and optional contradiction witness.
Projections expose only kind/relation, pivot/confirmation/event sessions, event
type/direction/prior trend and admitted identities. No numerical prices, bars,
source bodies, private paths, limitation payloads or arbitrary diagnostics.
Canonical sorted compact JSON plus LF, SHA256 over unsigned report, max 1 MiB.

Injected actual CLI `setup-invalidation --symbol SYMBOL --storage-root ABSOLUTE_ROOT
--previous-selection-time UTC --current-selection-time UTC --output json`
uses the existing observation port. Validate request before two serial
CURRENT_STRUCTURE calls and bind selectors before evaluation. No historical
provider reader or backdating. Exit 0 INVALIDATED/NO_CONTRADICTION_OBSERVED/
REPLAY/NO_BASELINE; 1 all inconclusive evidence outcomes; 2 malformed, integrity
or interruption with fixed diagnostic and no partial stdout. A guarded runnable
synthetic demo uses the real producer and actual CLI with fixed dates explicitly
labelled as synthetic; it denies network and hidden-directory effects.

## Ownership, sequence and adversarial matrix

Coordinator is sole writer: new invalidation SDK/CLI/manifest under
`research_comparison`, focused tests, synthetic demo, existing Linux distribution
verifier and its focused regressions, Plan50/Sprint36 and small related docs.
Only mechanically bound manifests may otherwise change. Existing Plan31/47/48/49
mathematics, APIs and historical facts retain behavior. No dependency or storage
migration. Tooling is the existing approved owner-checkout `.venv` outside the
worktree; official uv only if needed, no environment copy/installation.

First working path: discriminating actual CLI red, then real-producer anchored
contradiction through SDK/CLI/demo. Complete all remaining matrix rows before
candidate freeze. Installed-wheel acceptance exercises INVALIDATED and
NO_CONTRADICTION_OBSERVED plus UNKNOWN from isolated installed SDK/CLI imports,
retaining identities through the existing verifier. No new entrypoint/mount.

| Risk/adversarial matrix | Required evidence |
| --- | --- |
| Positive/causal | Later close-confirmed down CHOCH at original pre-BOS HL; witness and both revisions visible |
| Negative | Wick-only, equality at low, unrelated/down BOS or other-low CHOCH and later-confirmed low cannot invalidate |
| Revision/absence | Source-only refresh compatible; event/low revision, unknown, no baseline, window loss, absence and replay distinct |
| Integrity/precedence | Wrong type/runtime/diagnostic/packet/anchor/time or duplicate witness terminal even combined with unknown/incompatibility |
| Bounds/privacy | One stock/two observations, existing metadata bounds, 1 MiB/plus-one; no numerical/body/path output |
| Timing | Strict event ordering; supporting-low confirmation before original event; Plan48 selectors/knowledge/deadlines preserved |
| Retry/interruption/concurrency | Stable repeated/concurrent pure calls without input/file mutation; second-call interruption no stdout |
| Compatibility/recovery | Existing setup/continuity regressions and prior-wheel checks; no data change, ordinary source rollback |
| Installed/delivery | Isolated installed SDK/actual CLI new behavior and existing native/OCI/adversarial checks; exact receipts |
| Independent review | Two fresh read-only full base-to-clean-committed-candidate domain and security/privacy/provenance reviews, pre/post SHA/tree/clean checks |
| Final gates | Hosted-only full selected tests, 87% aggregate coverage, static, sdist/wheel, installed/OCI and GitGuardian; exact main admission and private publication/pull |

Reviews use native separate fresh-context agents without nested delegation.
Reviewers do not write candidate bytes; each returns complete PASS/BLOCKERS with
paths, violated acceptance, checks and limits. Settings inherited unless task
complexity requires an authorized override; unavailable telemetry is recorded.
Handbook core/specification/TDD fallback used because no trusted original
procedure content identity was established. Local checks are lightweight static
or explicit focused synthetic repair evidence only. No local heavy CI/build/
container run. Fresh shared allowance and Actions/Packages account $0 Stop usage
Yes precede every hosted trigger; no automatic reruns or paid capacity.

Goal starts after Issue, Sprint36 milestone and Project field readback. The owner
explicitly authorizes normal implementation/review/PR merge/private publication/
closeout without redundant approval. All gates remain mandatory. Stop only the
dependent action for an unsafe/unjustifiable rule, unavailable prerequisite,
scope/provider/credential/host restriction, protected out-of-scope effect,
conflicting mutation, failed review/gate or residual risk beyond authorization.

Expiry, persistence/monitoring, new sources/providers/formulas/catalogues,
broker effects and money/risk/capital expansion are excluded. All Future issues
stay excluded; CI retirement/Windows qualification stay separate. All eight
Plan47 phase outcomes remain: detection; necessary analytical coverage;
generation responsibility/identity; confirmation/invalidation/expiry/duplicates;
observable lifecycle; context/safety; correctness/interpretation/effectiveness;
verified phase closeout. This slice advances one invalidation condition only.
No signal-phase or product completion claim follows from sprint completion.
