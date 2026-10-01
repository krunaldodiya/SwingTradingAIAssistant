# Sprint 29: single-stock loss scenario

Owner: Krunal Dodiya. Accepted October 1, 2026. Governing
[Issue #237](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/237),
milestone 21, [Plan 43](../plans/43-single-stock-loss-scenario.md).

The usable increment calculates gross entry notional, stop proceeds, loss per
share and scenario loss from one caller-supplied LONG NSE-equity scenario.
Amounts are exact; identity and prices are declared assumptions. Costs and
slippage are excluded, stop execution is not guaranteed, and no trade
eligibility is assessed. No new provider or data capture is needed.

This dated planning checkpoint does not claim delivery. The governing Issue
retains the final exact reviewed revision, independent verdicts, required gate
results, PR merge, main admission and configured distribution evidence. The
owner has authorized closure only after those gates pass.

Discovery confirmed Sprint 21 screening already delivered and Sprint 28
Volume/Relative Strength integration closed. Sprint 29 therefore supplies a
new bounded risk calculation rather than another analytical filter. Broader
liquidity, invalidation, gap, cost and exposure policy remains separately scoped.

Coordinator owns scope, tracker, integration and final gates; one executor owns
implementation and focused checks; two independent read-only reviewers inspect
the same committed candidate. All supplied and generated evidence is synthetic
for acceptance; no live-market or performance qualification is claimed.
