# Plan 43: single-stock loss scenario

Status: accepted bounded direction; frozen implementation contract, not delivered.
Owner and risk owner: Krunal Dodiya. Sprint 29 / [#237](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/237). R3.
Authority: October 1, 2026 owner instruction to finish and close/merge the PR,
Issue and sprint, following the proposed entry/stop/quantity first slice.
Baseline: `67fe9b70ffa5058f38290817703097eaa941a8ad`.

## Outcome and admission

1. Value: the consumer can see the arithmetic loss implied by a supplied stock scenario.
2. Fit: the first descriptive Risk Validation slice, without risk eligibility or advice.
3. Risk: assumptions misrepresented as facts, false maximum-loss claims, numerical error or private-input disclosure.
4. Smallest alternative: pure bounded arithmetic behind the existing CLI; no provider, store, model or automated policy.
5. Accepted: hypothetical LONG delivery-equity loss calculation only. Full risk assessment remains deferred.

The first working path is one synthetic NSE stock through the real CLI with
entry 100.00, stop 95.00, quantity 10: entry notional 1000.00, stop proceeds
950.00, loss per share 5.00 and gross scenario loss 50.00 INR. No market claim
follows from this example. All acceptance cases below remain required.

## Closed input and exact calculation

Add `market-data loss-scenario --input-file ABSOLUTE_OWNER_PRIVATE_JSON` and a
public SDK parser/calculator in `market_data/loss_scenario.py`. Use the existing
64-KiB no-follow owner-private regular-file reader. No other command changes
meaning. No positional price inputs, storage root or provider dependency.

The closed JSON request `equity-loss-scenario-request@v1` has exactly:
`schema`, `instrument` (exactly `isin`, `exchange`, `symbol`), `side`, `currency`,
`bar_frequency`, `holding_sessions`, `entry_price`, `stop_price`, `quantity`.
`isin` is a syntactically valid 12-character Indian ISIN (IN followed by ten
uppercase alphanumeric characters, last a digit, valid ISIN check digit);
`exchange` is NSE; `symbol` uses the existing bounded uppercase symbol grammar
(1–32 characters). Identity is caller-declared, not verified listing/mapping.
`side` is LONG; `currency` INR; `bar_frequency` 1d. Holding sessions is a strict
integer 2–20: an explicit scenario assumption and bounded supported daily swing
window, not an approved strategy/time-stop policy. Quantity is a strict integer
1–1,000,000. Booleans are not integers. No short, intraday or other asset claim.

Prices are strings in plain positive decimal notation with exactly two fractional
digits, no sign, whitespace, exponent or leading zero except `0.xx`, at most
999999999.99. Stop is strictly below entry. Do not round invalid input into an
accepted price. Compute in integer paise (or provably exact isolated decimal
arithmetic); ambient decimal context cannot change results. Return canonical
fixed-two-decimal strings. Formulae: loss/share = entry − stop; entry notional =
entry × quantity; stop proceeds = stop × quantity; gross scenario loss =
(entry − stop) × quantity. No percentage, quantity recommendation or threshold.
Reject missing/unknown/duplicate keys, invalid UTF-8, nonfinite values, wrong
schema/types, arrays, overlong fields, unsupported enums and invalid bounds.
Validate SDK input too; no trust in mutable/preconstructed request objects.

## Result and honesty boundaries

Return `equity-loss-scenario@v1`, normalized request assumptions and the four
amounts above, currency INR, `input_basis=CALLER_SUPPLIED_ASSUMPTIONS`,
`instrument_verification=NOT_PERFORMED`, `market_evidence=NOT_USED`,
`risk_eligibility=NOT_ASSESSED`, and `costs_and_slippage=EXCLUDED`.
Include explicit limitations: stop execution is not guaranteed; actual losses
may exceed this scenario; fees/taxes/slippage are excluded; no liquidity,
event, gap, portfolio or trade suitability assessment was performed.
These labels prohibit presenting the amount as maximum loss, a validated stop,
a current stock fact, safe position size or authorization to trade. No current
market timestamp is fabricated. Supplied prices are scenario inputs, not OHLC.

Bind request, calculation version, runtime and result identities using existing
canonical SHA-256 conventions. Hash the complete result except its own identity.
Verify source identity consistently with existing runtime verification, and
refresh every directly/transitively affected manifest after formatting; do not
rebind historical frozen producer identities to new files. No new archive,
attestation, persisted receipt, lock or snapshot subsystem. Bound canonical
output to 16 KiB before writing once. Input failure and runtime integrity or
unexpected failure return sanitized stderr and exit 2 with empty stdout; success
returns exit 0. Interrupts may propagate with existing CLI semantics. Never echo
raw malformed input, private paths or exception text. No provider/service call,
credential reading, store creation/writing or evidence read. File input is the
only authorized read apart from package/runtime verification. Explicit retries
are deterministic and have no retained effects. Rollback removes the additive
command; all stores and V1–V5 remain usable.

## Frozen adversarial matrix

- Real SDK and actual CLI positive; independent expected amounts including 0.01
  difference, decimal carry and maximum prices/quantity. Ambient Decimal precision
  and rounding changes cannot alter results. Input permutation preserves identity;
  changing assumptions changes request/result identity.
- Quantity 0/1/1,000,000/1,000,001, holding 1/2/20/21, price minimum/maximum/plus one,
  zero/negative/equal or higher stop, huge digits/exponents, float/bool/null/object,
  unknown/duplicate nested keys, malformed UTF-8 and schema: reject without output
  or service effects. Invalid identity/check digit/symbol and unsupported asset
  enums fail. No input value is silently inferred, clamped or defaulted.
- Missing/relative/public/symlink/hardlink/nonregular/oversized files: reject via
  existing reader. Combined malformed/invalid requests cause no calculation
  emission or external effect. Output bound and plus one reject before emission.
- Runtime substitution, unexpected exception and interruption: no successful
  partial JSON; sanitized errors; retry leaves source/input unchanged.
- Privacy, labels and canonical serialization/identities remain explicit; reject
  misuse of caller assumptions as verified evidence. No market temporal gate is
  needed because no market observation or execution qualification is claimed.
- Existing CLI and V1–V5 regressions, all affected source manifests and clean
  installed-wheel command; full configured self-hosted gates and two independent
  exact-candidate reviews. No omitted check becomes a pass.

## Ownership, execution and completion

Coordinator owns this contract, tracker, integration, review assignments and final
gates. One native Codex executor owns the new loss-scenario module, minimal CLI
wiring, affected runtime manifests, targeted tests and workflow documentation.
It must test first, retain red/green/focused evidence, format before manifests,
commit the stable implementation and prohibit nested delegation. It may not
change this contract, other worktrees, CI policies or unrelated behavior.
Two fresh native read-only reviewers own functional/domain and security/privacy/
provenance verdicts after writing ends. Each reads the full base-to-candidate
change and affected context. Model/effort inherit host defaults; optional actual
telemetry is unavailable. Routine scoped execution is permitted by host controls.
Coordinator owns expensive final CI; do not duplicate the full suite locally.

Use the persistent bounded goal after Issue/Project and this plan are frozen.
Pause only the dependent work for genuine ambiguity, source adoption, protected
effects, scope expansion, shared mutation or unavailable required gates. Owner
has authorized merge and tracker/milestone closure after checks; no bypass or
public-package release. No new risk thresholds, cost model, provider capture,
portfolio rules, risk pass/fail, automatic stops, ranking, advice, orders,
historical effectiveness or broader memory reconciliation. Preserve #232/PR233,
#234 and all recovery material. Final closeout binds exact review, CI, PR merge,
main admission and existing private distribution receipt where configured.

## October 1 delivery-prerequisite correction

The configured private OCI publication is required by this sprint's closeout.
Read-only inspection of prior main publication run 36704656639, job109851943987,
shows successful Podman push followed by `manifest unknown` when pulling the
locally selected RepoDigest. Local image metadata can retain a pre-push digest;
it is not proof of the registry's uploaded manifest. The failed log is retained
privately in the Sprint29 evidence directory. No previous publication pass is
claimed and no unrelated old release is retried.

This is a concrete delivery-integrity blocker. The smallest correction stays
inside the existing disposable publication job: preserve exact tag collision
refusal, then remove only the verified current local and remote image aliases,
without force or prune, require the old image ID to be absent, pull the exact
commit-qualified remote tag afresh and recheck the expected image ID and bound
source/wheel/requirements labels. Select the registry digest using the unchanged
strict unique-repository parser, then retain the existing digest pull, smoke,
private visibility and receipt checks. Unexpected extra aliases or changed
remote bytes fail closed; no tag overwrite, identity relaxation, new credential,
new dependency or broad cleanup is allowed. This applies to both existing Docker
and Podman support. No general release subsystem is introduced.

A separate executor may own only `.github/workflows/publish-oci.yml` and a focused
publication regression test, serialized commits with the product executor.
Require a discriminating execution test against the actual extracted workflow
shell with controlled engine responses: stale local digest fails before repair;
fresh registry identity succeeds after repair; collision, extra alias/resident
image, changed pulled identity/labels and failed pulls cannot pass. This fake
engine challenges control flow, not real registry availability. Actual final
Sprint29 publication and retained receipt remain the external acceptance gate.
Both independent reviewers cover the complete combined candidate, including this
R3 release-trust correction. Coordinator owns this amendment and tracking.
