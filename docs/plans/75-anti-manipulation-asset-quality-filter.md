# Plan 75: Anti-Manipulation and Asset Quality Filter

Status: **ACCEPTED BOUNDED SPECIFICATION**
Owner: repository owner and product direction authority
Governing Issue: [#320](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/320)
Milestone: `Sprint 61: anti-manipulation and asset quality filter`

## 1. Outcome and Purpose
Enforce a dedicated, deterministic **Anti-Manipulation and Asset Quality Filter** stage in the swing trading research candidate admission lifecycle.
Any stock that passes preliminary safety and market structure must ALSO pass strict asset-quality rules to eliminate pump-and-dump, operator manipulation, and post-IPO volatility risks:
1. **Listing Track Record Floor:** Rejects newly listed stocks with fewer than 120 historical trading sessions (< 6 months of continuous history).
2. **Safe Price Floor:** Rejects penny and low-priced stocks with price < INR 100.00.
3. **Institutional Scale & Turnover Floor:** Rejects illiquid operator small-caps with 20-day median turnover < INR 50,00,00,000 (INR 50 Crore / day).
4. **Circuit Proximity Buffer:** Rejects circuit-locked stocks within 2.0% of upper/lower price bands.

## 2. Canonical Portfolio Basket Hierarchy
- **Target Size:** A swing trading basket / portfolio contains **5 to 10 stocks**.
- **Tier 1 (Nifty 100 - Top Priority):** The primary universe is always Nifty 100. All validated candidates from Nifty 100 are admitted first.
- **Tier 2 (Nifty 500 Ex-Nifty 100 - Conditional Gap Fill):**
  Only when Nifty 100 yields fewer than 5 candidates, the scanner expands to the Nifty 500 excluding the 100 already-scanned Nifty 100 stocks.
  Ex-Nifty 100 midcaps are admitted only if they strictly clear all Anti-Manipulation and Asset Quality gates.
