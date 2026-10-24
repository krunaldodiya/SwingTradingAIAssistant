# Plan 74: full analytical lifecycle integration

Status: accepted bounded specification under [Issue #318](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/318), Milestone 52. Owner and risk owner: Krunal Dodiya. Risk tier: R3 financial-research policy, multi-module analytical composition, and public decision contracts. Base: `8440bb3`.

## Outcome and consumer

Integrate all 7 architecture-locked research families into the unified scanner (`signal-decisions scan`), candidate briefing card (`swing-trade-brief@v1`), and terminal display:

1. **Market Structure (`market_structure`):** 21-day pivots, trend, close-confirmed Break of Structure (`BOS` / `CHOCH`), age 1–5 sessions, protective swing-low stop.
2. **Safety Eligibility (`market_data`):** 8-rule conservative safety screen (24/7/365 active).
3. **Price Action & SMC Retest (`price_action`):** Breakout candle body quality (body % of range), exact price relation to the broken high (`BELOW_BROKEN_HIGH`, `AT_BROKEN_HIGH`, `ABOVE_BROKEN_HIGH`) with distance percent, and the display stop span. The relation is a price-distance fact, not a completed-bar retest or an SMC zone.
4. **Volume Analysis (`volume_analysis`):** 20-day volume baseline, breakout Relative Volume (RVOL), and volume expansion confirmation ($\text{RVOL} \ge 1.0\times$).
5. **Sector / Industry Analysis (`sector_analysis`):** Official NSE Indices Industry mapping (17 industries), industry peer count, and sector breakout participation rate.
6. **Relative Strength (`relative_strength`):** 20-session stock return versus Nifty 100 median benchmark return, excess return delta %, and outperformance classification.
7. **Market Regime (`market_regime`):** Cohort-wide advance/decline breadth across all scanned stocks (`BULLISH_TRENDING`, `BEARISH_CORRECTION`, or `RANGE_OR_TRANSITION`).

## Frozen mathematical formulas

1. **Relative Volume (RVOL):**
   $$\text{RVOL} = \frac{V_{\text{breakout}}}{\frac{1}{20} \sum_{i=1}^{20} V_{\text{prior\_sessions}}}$$
   $\text{Volume Expansion} = \text{True if } \text{RVOL} \ge 1.0 \text{ else False}$.

2. **Price Action Candle Quality:**
   $$\text{Range} = \text{High} - \text{Low}, \quad \text{Body} = |\text{Close} - \text{Open}|$$
   $$\text{Body \%} = \frac{\text{Body}}{\text{Range}} \times 100$$
   $\text{Quality} = \text{DECISIVE\_BODY if } \text{Body \%} \ge 60\% \text{ else WEAK\_BODY}$.

3. **Relative Strength (RS):**
   $$R_{\text{stock}} = \frac{C_{\text{latest}} - C_{\text{20\_sessions\_ago}}}{C_{\text{20\_sessions\_ago}}} \times 100$$
   $$R_{\text{benchmark}} = \text{Median}(R_{\text{all\_scanned\_stocks}})$$
   $$\Delta_{\text{RS}} = R_{\text{stock}} - R_{\text{benchmark}}$$
   $\text{Status} = \text{OUTPERFORMING if } \Delta_{\text{RS}} > 0 \text{ else UNDERPERFORMING}$.

4. **Market Regime (Breadth):**
   $$\text{Uptrend \%} = \frac{\text{Count}(\text{UPTREND})}{\text{Total Stocks}} \times 100, \quad \text{Downtrend \%} = \frac{\text{Count}(\text{DOWNTREND})}{\text{Total Stocks}} \times 100$$
   $$\text{Regime} = \begin{cases}
   \text{BULLISH\_TRENDING} & \text{if Uptrend \%} \ge 60\% \\
   \text{BEARISH\_CORRECTION} & \text{if Downtrend \%} \ge 50\% \\
   \text{RANGE\_OR\_TRANSITION} & \text{otherwise}
   \end{cases}$$

5. **Sector Participation:**
   $$\text{Sector Participation} = \frac{\text{Count}(\text{Breakouts in Industry})}{\text{Total Stocks in Industry}} \times 100$$
