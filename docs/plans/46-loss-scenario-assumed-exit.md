# Plan 46: loss beyond the planned stop price

Status: accepted bounded implementation contract; implementation pending.
Owner/risk owner: Krunal Dodiya. Sprint32 / [#244](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/244), milestone24. R3 financial arithmetic, public contract and private-input provenance.
Authority: October 2, 2026 owner-authorized new-session planning and implementation following the “Loss Beyond the Stop Price” preview. Merge/release are separate.
Base: `27a21094187a9f1e8ad987468cdb2cc020cd00c6`.
Plans34/43/44/45 govern existing boundaries; this independently governs previously deferred adverse-exit arithmetic.

## Validated need and smallest slice

1. Value: quantify the extra hypothetical loss when caller assumes an exit worse than the planned stop.
2. Fit: descriptive Risk Validation; no risk admission, execution prediction or strategy policy.
3. Risk: arithmetic error, false maximum-loss/empirical-model claim, cost double-counting or private-input disclosure.
4. Smallest alternative: opt-in standalone calculatorV3, reusing existing integer paise and private reader; two V2 calls overload stop semantics and leave deterministic difference to AI.
5. Accepted: one caller-declared LONG NSE equity and one strictly worse assumed exit, with identical aggregate whole-position costs in both scenarios.

The first actual CLI/SDK path uses entry100.00, planned stop95.00, assumed exit93.00, quantity10 and costs12.34: planned loss including costs62.34, assumed-exit loss82.34, additional loss20.00 INR. No market observation is required. Complete every accepted case after this path.

## Closed versioned input

Add `market-data loss-scenario --contract-version v3 --input-file ABSOLUTE_PRIVATE_JSON`, SDK `loss_scenario_request_v3_from_json(bytes)` and `calculate_loss_scenario_v3(request)` in the existing module. Default/explicit V1, V2 and researchV6 retain their meanings. V6 accepts only Plan43 V1, rejecting V2/V3 before research/storage effects. No implicit conversion.

Schema `equity-loss-scenario-request@v3` has exactly Plan45's fields plus required `assumed_exit_price`. Inherit Plan43 identity, enums, strict integers and positive exact two-decimal price grammar/bounds, Plan45 cost grammar/bounds and whole-position semantics. Require `0 < assumed_exit_price < stop_price < entry_price <= 999999999.99`. Equal stop, better exits and zero exit are unsupported input, not rounded/clamped/defaulted. Quantity1–1,000,000; holding sessions2–20. Costs0.00–999999999.99; above-notional costs remain allowed.

Revalidate all direct/mutated SDK objects; reject missing/unknown/duplicate nested keys, wrong schema/type/enums/identity, malformed UTF-8/JSON, nonfinite, exponent, huge/overlong, sign/whitespace/leading-zero values. Reuse bounded64-KiB absolute owner-private no-follow regular-file reader; public/symlink/hardlink/nonregular/missing/oversized inputs fail.

## Exact result

Calculate integer paise independent of Decimal context. Result schema `equity-loss-scenario@v3`, normalized complete `assumptions`, INR and exactly these amounts:

- `entry_notional = entry * quantity`;
- `planned_stop_proceeds = stop * quantity`;
- `planned_loss_per_share = entry - stop`;
- `planned_gross_loss = (entry - stop) * quantity`;
- `assumed_exit_proceeds = assumed_exit * quantity`;
- `assumed_exit_loss_per_share = entry - assumed_exit`;
- `assumed_exit_gross_loss = (entry - assumed_exit) * quantity`;
- `assumed_round_trip_costs = costs`;
- `planned_loss_including_assumed_costs = planned_gross_loss + costs`;
- `assumed_exit_loss_including_assumed_costs = assumed_exit_gross_loss + costs`;
- `additional_loss_from_assumed_exit = (stop - assumed_exit) * quantity`.

Each canonical fixed-two-decimal amount is exact; costs are added once to each scenario and cancel from the difference. Costs are the same caller assumption in both scenarios, excluding execution-price movement; no scenario-specific fee recomputation.

Labels: `input_basis=CALLER_SUPPLIED_ASSUMPTIONS`, `instrument_verification=NOT_PERFORMED`, `market_evidence=NOT_USED`, `risk_eligibility=NOT_ASSESSED`, `costs_basis=CALLER_SUPPLIED_AGGREGATE`, `cost_completeness=NOT_VERIFIED`, `comparison_costs=SAME_ASSUMED_AGGREGATE`, `assumed_exit_basis=CALLER_SUPPLIED_PRICE`, `execution_model=NOT_USED`. Do not retain V2's `slippage=EXCLUDED` or V1's combined exclusion label in V3: the caller supplies price movement but no empirical slippage model is used.

Limitations explicitly state stop execution is not guaranteed, actual losses can exceed either scenario, assumed exit is neither a forecast nor maximum loss, no fee/tax schedule is calculated/verified, aggregate costs have unverified completeness and are identical for both scenarios, price movement is separate from costs, no empirical gap/slippage model and no liquidity/event/gap/portfolio/suitability assessment.

`calculation_version=integer-paise-long-loss-assumed-exit@v3`; verified current runtime SHA256, canonical request identity and result identity over full result except itself. Sorted compact JSON+LF, key-order invariant; every changed assumption changes identities. Format before refreshing all active direct/transitive manifests; preserve frozen historical identities. Complete output16KiB bound before one write, success0. Input validation precedes runtime verification; invalid/runtime/unexpected errors sanitize stderr, exit2 and empty stdout. Interrupts retain existing semantics, no successful partial JSON.

## Effects, recovery and boundaries

Only explicit input and package/runtime verification reads; no market/provider/network/credentials/store/archive/timestamp/new dependency/install/hidden-directory effect. Deterministic retry/concurrent invocations have no shared mutable state. Rollback selects V1/V2 or removes additive V3; no migration/deletion. Reusable architecture and researchV6 remain intact. No V7, fee schedules, sizing, eligibility, portfolio, providers/acquisition, recommendations/orders, performance qualification or maximum-loss guarantee. Future issues178/177/144/139/126 remain Todo/unassigned.

## Frozen adversarial acceptance matrix

| Case | Required observation / method |
| --- | --- |
| First actual CLI + SDK | Exact eleven amounts62.34/82.34/20.00; truthful labels and independently hashed identities |
| Exit one paise below stop, minimum prices, carry, maximum price/quantity/cost, costs above notional | Independent exact expected amounts; Decimal precision/rounding invariance; cost cancellation |
| Exit zero/equal/higher/max-plus-one/negative/sign/whitespace/exponent/leading zero/huge/float/bool/null/object | Parser/directSDK/CLI sanitized rejection, no effects |
| Inherited identity/enums/quantity/horizon/price/cost bounds | All existing invalid cases applied to V3; inclusive bounds and plus-one |
| Closed schema, duplicates any depth, malformed UTF8/JSON, wrong version and mutated SDK | Reject without success;64KiB and plus-one; no silent conversion |
| Private reader adversaries | Missing/relative/public/symlink/hardlink/nonregular/oversized rejection via real reader |
| Invalid input plus runtime corruption | Input failure wins; calculator/runtime/effect sentinels not called |
| Runtime/source substitution and unexpected exceptions | Sanitized exit2, no partial JSON, no raw input/path/exception leak |
| Interruption then explicit retry | No emission; input/source unchanged; later identical output and no retained effects |
| Complete output bound and plus-one | Bound before single CLI emission |
| Concurrency and effects | Independent actual processes yield identical output; no provider/network/credential/store effects |
| Identities/provenance | Full request/result/runtime binding; changes to every assumption alter identity; output honesty inspection |
| Compatibility/rollback | V1/default and V2 unchanged amounts/labels; cross-version rejection; V6 rejects V3 before effects; existing manifest/demo regressions |
| Stable integrated candidate | Both independent exact-byte full-slice reviews, focused/static/full/package/installed/hosted gates with explicit authority limits |

## Ownership, routing and gates

Coordinator `/root` is sole writer: this contract/tracker, `loss_scenario.py`, minimal `cli.py` wiring, `tests/market_data/test_loss_scenario.py`, necessary V6 rejection tests, `docs/workflows/loss-scenario.md`, roadmap/upcoming checkpoints and mechanically identified active manifests/demo identity expectations. No concurrent writer/nested delegation. Prior session released mutation ownership; clean sole checkout branched from revalidated main, retaining Sprint31 branch/evidence.

Dependency order: frozen contract -> discriminating real V3 CLI RED -> smallest implementation -> complete focused adversaries/static checks -> clean committed candidate -> independent functional/domain and security/privacy/provenance reviews -> correction if blocked -> stable final gates/handoff. Reviews use fresh native agents, inherited model/effort (actual telemetry unavailable), read-only full base-to-candidate/context and exact commit/tree/clean pre/post checks. Coordinator assigns bounded asynchronous reviews and owns final integration; no writer approves own candidate. Complete reports are retained visibly outside checkout.

Use official uv0.12.19, canonical existing `.venv`, locked dependencies, local Python3.11.16; existing CI3.11.14 is distinct evidence. Required gates: Ruff format/lint, Pyright, Vulture80, affected/fast regressions, complete configured non-private suite with branch coverage>=87%, sdist/wheel, clean installed-wheel V3/V1/V2 smoke, all affected manifests and whitespace check. Do not run full suite before stable reviewed candidate. Hidden fixture/installation/hosted protected effects require scoped authority; prepare concrete reviewable bytes first and pause only dependent gates. No approval carries over from Sprint31. Merge/release separate.

Persistent Goal starts after tracker/contract freeze, verified active, remains active through authorized implementation/reviews/verification. Goal continuity does not grant authority. Pause affected work for consequential ambiguity, source/protected effects, scope expansion, conflicting mutation, missing required reviewer/gate or merge/release authority. Functional acceptance and sprint closure are distinct; no missing gate is a pass.
