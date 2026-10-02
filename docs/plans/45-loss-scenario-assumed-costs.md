# Plan 45: hypothetical loss including caller-assumed costs

Status: accepted bounded implementation contract; implementation and review pending.
Owner and risk owner: Krunal Dodiya. Sprint 31 / [#242](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/242), milestone 23.
Risk R3: financial arithmetic,
public CLI/SDK contract, assumption provenance and private-input handling.
Authority: October 2, 2026 owner request to finish Sprint 31 planning and start
implementation, within the accepted descriptive Risk Validation direction.
The coordinator selected this slice after read-only planning and code inspection.
Baseline: `07704641aff54f8b0d56cfa99d0f882dd93422ad`.
Plans 34, 43 and 44 remain authoritative for their existing boundaries.

## Observable question and admission

For a supplied entry, stop, quantity and aggregate round-trip cost assumption,
what loss does this hypothetical stop scenario imply including those costs?
Plan 43's closed request and calculator expose only gross loss and explicitly
exclude costs; Plan 44 reuses that result. The consuming AI must not perform the
missing deterministic calculation itself. This is usable for any valid supplied
scenario, requires constant bounded arithmetic and needs no market observation.

1. Value: expose exact hypothetical loss including one explicit aggregate cost assumption.
2. Fit: descriptive Risk Validation for one caller-declared LONG NSE equity.
3. Risk: false cost completeness, assumptions treated as facts, arithmetic error or private-input disclosure.
4. Smallest alternative: extend the existing standalone calculator and CLI using integer paise.
5. Disposition: accepted for opt-in V2; fee schedules, adverse execution, eligibility and strategy remain deferred.

Having the AI add the amount conflicts with the deterministic-tool boundary.
Adopting broker/tax rates would need sources and a separate completeness contract.
Adding an adverse exit price answers a different question. Immediate V7 dossier
composition is unnecessary because the AI already has the standalone CLI/SDK.
No future backlog item is promoted: #178, #177, #144, #139 and #126 remain
unassigned. No new source, scoring factor or architecture module is introduced.

## Closed request and interface

Add `market-data loss-scenario --contract-version v2 --input-file ABSOLUTE_PRIVATE_JSON`.
Default and explicit `--contract-version v1` use the existing V1 contract.
Unknown versions fail before effects. Add public functions
`loss_scenario_request_v2_from_json(bytes)` and
`calculate_loss_scenario_v2(request)` in the existing `loss_scenario.py` module.
The V1 functions retain their names, schema and semantics. Research V6 continues
accepting only Plan 43 V1 scenarios and rejects V2 before research/storage effects.

V2 schema is `equity-loss-scenario-request@v2`. Its exact fields are the complete
Plan 43 request (`schema`, `instrument`, `side`, `currency`, `bar_frequency`,
`holding_sessions`, `entry_price`, `stop_price`, `quantity`) plus required
`round_trip_costs`. Inherit all Plan 43 restrictions: valid Indian ISIN check
digit, exact NSE identity and bounded uppercase symbol, LONG, INR, 1d, strict
integer 2–20 holding sessions and 1–1,000,000 shares, positive two-decimal price
strings at most `999999999.99`, and stop strictly below entry. No inferred fields.

`round_trip_costs` is a caller-assumed aggregate INR amount for entry and exit
of the entire position; it excludes slippage. It is not a per-share amount.
Require a plain decimal string with exactly two fractional digits from `0.00`
through `999999999.99`, no sign, whitespace, exponent or leading zeros except
`0.xx`. Explicit zero is valid; missing is invalid. This is a representation
bound, not a fee threshold. A cost above entry notional is allowed; do not clamp
or invent plausibility policy. Completeness and accuracy are not verified.

Reuse the 64-KiB owner-private no-follow regular-file reader. Reject missing,
relative, public, symlinked, hardlinked, nonregular or oversized input; reject
malformed UTF-8/JSON, duplicate keys at any depth, missing/unknown fields, wrong
schema, unsupported types/enums and invalid bounds. Revalidate SDK objects,
including mutations after parsing. No parser silently converts V1 into V2.

## Exact output and labels

Calculate in integer paise, independent of ambient Decimal precision/rounding:

- `entry_notional = entry_price * quantity`;
- `stop_proceeds = stop_price * quantity`;
- `loss_per_share = entry_price - stop_price`;
- `gross_scenario_loss = (entry_price - stop_price) * quantity`;
- `assumed_round_trip_costs = round_trip_costs`;
- `scenario_loss_including_assumed_costs = gross_scenario_loss + round_trip_costs`.

All six amounts are canonical fixed-two-decimal INR strings in `amounts`.
First working path: entry `100.00`, stop `95.00`, quantity `10`, costs `12.34`
returns gross `50.00`, supplied costs `12.34` and total `62.34` through both
the SDK and actual CLI. Complete every matrix row before acceptance.

Result schema: `equity-loss-scenario@v2`. Include normalized complete
`assumptions`, `currency=INR`, `input_basis=CALLER_SUPPLIED_ASSUMPTIONS`,
`instrument_verification=NOT_PERFORMED`, `market_evidence=NOT_USED`,
`risk_eligibility=NOT_ASSESSED`, `costs_basis=CALLER_SUPPLIED_AGGREGATE`,
`cost_completeness=NOT_VERIFIED`, and `slippage=EXCLUDED`.
V2 omits V1's combined `costs_and_slippage=EXCLUDED` label because it would be
false for this contract. V1 retains it. Limitations explicitly state:
no fee/tax schedule was calculated or verified; costs are caller assumptions
whose completeness is unverified; slippage is excluded; stop execution is not
guaranteed and actual losses may exceed the scenario; no liquidity, event, gap,
portfolio or trade suitability assessment was performed.

Use `calculation_version=integer-paise-long-loss-with-costs@v2`, current verified
`runtime_code_identity_sha256`, canonical `request_identity_sha256`, and
`result_identity_sha256` over the complete result excluding itself. Reuse sorted
compact JSON plus LF. Input ordering cannot change identity; changing any
assumption must change request/result identity. Current runtime hashes naturally
change with source bytes; compatibility does not require false old hashes.
Refresh every active directly/transitively bound manifest after formatting.
Preserve historical frozen producer identities and records.

Bound complete canonical output to 16 KiB before the existing single emission.
Successful CLI returns 0. Invalid input, runtime-integrity or unexpected failure
returns sanitized stderr and exit 2 with no partial JSON. Input validation wins
over runtime corruption when both occur. Interrupts retain existing process
semantics and cannot become successful partial output. Existing unsupported
types/enums are input failures; there is no invented market-evidence readiness
state for these caller assumptions.

## Effects, recovery and scope boundary

Only the explicit input and package/runtime verification are read. No provider,
credential, network, market data, store, archive, persisted receipt or fabricated
timestamp is used. No new dependencies, installation or hidden directories.
Retries are deterministic and effect-free; concurrent invocations share no new
mutable state. Rollback selects V1 or removes additive V2 dispatch; no migration,
retained-evidence cleanup or owner-data deletion is needed.

Later improvements and non-goals: V7 integration, multiple scenarios, adverse
exit/slippage calculation, verified fees/taxes, cost schedules, automatic stops,
position sizing, portfolio rules, risk eligibility, signals/recommendations,
maximum-loss guarantees, performance evaluation and historical qualification.
No provider activation, recurring capture, source adoption, merge or release is
authorized. Any eventual PR remains draft pending separate release authority.

## Frozen adversarial acceptance matrix

| Case | Observable result / prohibited effects | Evidence method |
| --- | --- | --- |
| First SDK/actual CLI path | Exact six amounts, `62.34` total, truthful labels and identities; no external effects | Independent expected amounts, real command subprocess and effect sentinels |
| Cost zero/one paise/maximum, maximum price and quantity, carry, cost above notional | Exact unrounded amounts; ambient Decimal changes cannot alter them | Boundary cases with independently stated expectations |
| Negative/max-plus-one/float/bool/null/exponent/huge digits/leading zeros | Sanitized input failure, no calculation success or effects | Parser, direct SDK and CLI cases |
| Existing Plan 43 invalid identity, price, quantity, horizon and enums | Original bounds remain enforced in V2 | Reused invalid-case table against V2 |
| Missing/unknown/duplicate keys, malformed UTF-8/JSON, wrong schema/version | Rejection at the input boundary, empty stdout | Nested duplicates, parser and actual CLI checks |
| Missing/relative/public/link/nonregular/oversized file | Existing private-reader rejection before calculation | Temporary visible synthetic paths and metadata cases |
| Malformed input plus runtime corruption | Input rejection takes precedence; no calculation or leaked diagnostics | Fault injection with stage/effect sentinels |
| Valid input plus runtime substitution or unexpected exception | Terminal failure, sanitized diagnostic, no partial JSON | Runtime tamper and injected-error cases |
| Interruption before emission, explicit retry, rollback | No retained effects; source/input unchanged; retry identical; V1 usable | Controlled interrupt and file inventories; V1 regression |
| Request key permutation, parsed-object mutation, cost change | Stable identity only for same assumptions; SDK revalidation | Independently computed canonical hashes and mutated objects |
| Output 16 KiB and plus one | Bound enforced before one emission | Serialization boundary and actual dispatch checks |
| Concurrent invocations | Same input/runtime yields identical output without shared writes | Independent concurrent command processes |
| V1/default/explicit V1 and research V6 | Existing schema/arithmetic/labels; V1 and V6 reject V2 request, V6 before research effects | Existing regressions and rejection sentinel |
| Private marker/path/exception content | No unintended value in diagnostics or output | Privacy assertions |
| Temporal/source authority | No live-market test, acquisition or current-fact claim | Contract/output inspection and effect sentinels |
| Stable integrated candidate | Complete gates and both independent verdicts apply to exact committed bytes | Commit/tree/clean pre/post checks and retained complete reports |

## Ownership, execution and verification

Coordinator owns this contract, Sprint 31 tracker, roadmap checkpoint, review
assignments, integration and final gates. One native implementation executor
owns `src/swing_trading_ai_assistant/market_data/loss_scenario.py`, minimal
`market_data/cli.py` wiring, `tests/market_data/test_loss_scenario.py`, necessary
V6 rejection cases in `tests/market_data/test_agent_loss_context.py`,
`docs/workflows/loss-scenario.md`, and mechanically identified affected active
runtime manifests. No nested delegation or concurrent shared-file writer.

Dependencies are existing private reader -> version-specific validation ->
exact calculation/runtime verification -> bounded serialization -> CLI output.
The executor first demonstrates a discriminating V2 CLI failure on old behavior,
then implements and covers all matrix rows. It owns focused checks and retained
red/green evidence. Coordinator owns expensive integrated checks after review.
Required gates: Ruff format/check, Pyright, Vulture 80, full configured
`not private_source` suite with branch coverage >=87%, sdist/wheel, clean
installed-wheel V2 command smoke and V1 compatibility, runtime-manifest checks,
and `git diff --check`. Use only the approved official uv CLI and canonical
project `.venv`, locked dependencies and Python 3.11.16; no manual environment
internals or removed sibling tooling. Avoid wrappers that install new tools.

Synthetic fixtures use visible temporary paths. Prior hidden-fixture approvals
do not transfer; a check requiring a newly created hidden directory must stop
only that check and report the exact path/need. No owner-private market data is
part of acceptance. Full/hosted/distribution evidence remains distinct from
focused checks and must satisfy the existing configured admission path.

Two fresh independent native reviewers inspect the full base-to-candidate
change, functional/domain and security/privacy/provenance respectively. They
are read-only, do not author the implementation and receive exact commit/tree,
contracts, complete diff and observed evidence. Resolve current blockers before
expensive final checks; changes require fresh exact-candidate verdicts.

Routing uses inherited model/effort for the bounded executor; actual host
telemetry and Fast control are unavailable/unverified. Handbook requirements-
planning and TDD fallbacks apply because no approved original skill is exposed.
Persistent Goal is available after this contract and tracker freeze. It grants
continuation only. Pause dependent work for genuine authority/consequential
ambiguity, source adoption, protected effects, scope expansion, conflicting
mutation or review/release freeze. Never convert a missing gate into a pass.
