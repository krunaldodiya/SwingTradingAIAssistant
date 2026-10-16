# Plan 75: Anti-Manipulation and Asset Quality Filter

Status: **ACCEPTED BOUNDED SPECIFICATION**
Owner: repository owner and product direction authority
Governing Issue: [#320](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/320)
Milestone: `Sprint 61: anti-manipulation and asset quality filter`

## 1. Outcome and Purpose
Enforce a dedicated, deterministic **Anti-Manipulation and Asset Quality Filter** stage in the swing trading research candidate admission lifecycle.
Any stock that passes preliminary safety and market structure must ALSO pass strict asset-quality rules to eliminate pump-and-dump, operator manipulation, and post-IPO volatility risks:
1. **Listing Track Record Floor:** Rejects newly listed stocks with fewer than 120 historical trading sessions (< 6 months of continuous history).
2. **Safe Price Floor:** Rejects penny and low-priced stocks with price < INR 50.00.
3. **Institutional Scale & Turnover Floor:** Rejects illiquid operator small-caps with 20-day median turnover < INR 25,00,00,000 (INR 25 Crore / day).
4. **Circuit Proximity Buffer:** Rejects circuit-locked stocks within 2.0% of upper/lower price bands.

## 2. Canonical Portfolio Basket Hierarchy
- **Target Size:** A swing trading basket / portfolio contains **5 to 10 stocks**.
- **Tier 1 (Nifty 100 - Top Priority):** Every validated Nifty 100 candidate fills
  the basket first, up to all 10 slots.
- **One-Pass Current Nifty 500 Scan:** Each current Nifty 500 member is evaluated
  once and its Nifty 100 membership is tagged; no Nifty 100 provider or data work
  is repeated.
- **Tier 2 (Nifty 500 Ex-Nifty 100 - Conditional Gap Fill):** Only when fewer than
  five Nifty 100 candidates validate, Nifty 500-only candidates fill remaining
  slots toward the 5–10 target. They never displace a validated Nifty 100 candidate
  and must pass every existing safety and anti-manipulation gate.
