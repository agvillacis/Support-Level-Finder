# Support Level Finder — Project Context

## What This Is

A web tool that pulls live options chain data for any stock ticker and visualizes put/call open interest walls — the strike prices where large clusters of contracts sit, which act as support (put walls) and resistance (call walls). Deployed on Railway.

Built for Anthony and his friend who does active options trading with technical analysis.

---

## Anthony's Friend — How He Thinks About Trades

His friend analyzes stocks using a combination of **options OI walls** and **key price levels**. Here's the framework he uses (based on a real trade analysis he walked through):

### Price Level Framework
- **Support zone**: Where he expects the stock to find buyers and bounce
- **Breakout target**: The upside price objective if support holds and the stock rips
- **Eject/stop-loss**: The price where he exits — below major support, no questions asked

### Example levels from a trade he was analyzing:
```
$203  ← breakout target (upside if it rips)
$180  ← effective cost basis on sold puts (after premium collected)
$170  ← put strike #1 (selling for premium)
$165  ← put strike #2 (selling for premium)
$160  ← long put strike (Christmas Eve expiration, bought for $6.30)
$153.70 ← long put breakeven ($160 - $6.30)
$152  ← primary support level (key)
$147  ← secondary support level
$145  ← EJECT — hits this, he's out
$140–$150 ← general support zone (low end)
   ↓ (potential air pocket if $145 breaks)
$115  ← institutional stop loss cluster
$110  ← institutional stop loss cluster
$100  ← institutional stop loss cluster (major round number)
```

**Note on institutional stops**: His friend identified $100/$110/$115 as where institutional stop losses are stacked. If $145 breaks, there's limited support between there and $100-$115 — it could flush fast.

### Strategies He Uses

**1. Selling Cash-Secured Puts (income / bullish-neutral)**
- Sells puts at strikes below current price
- Collects premium upfront
- If stock drops to strike, he gets assigned and owns shares at that price
- Net cost basis = strike - premium received
- In the example: selling $170 and $165 puts, combined premium makes effective cost ~$180

**2. Buying Protective Puts (hedge / bearish insurance)**
- Buys a put to protect against a sharp drop
- Breakeven = strike - premium paid
- Example: $160 put expiring Christmas Eve for $6.30 → breaks even at $153.70
- The put only pays off if stock drops **below** $153.70
- Intentionally priced near the $152 support — if support breaks, the put prints

**Key insight from his friend**: "it would go up to $172" in context meant the stock was trading around $172 at time of analysis, making the $160 put out-of-the-money by ~$12 but cheap insurance given the support levels below.

---

## Features Built

### Original build
- Ticker input → fetches options chain via yfinance
- 3 expiration tabs: This Week / Month End / Year End
- Bar chart: green = put OI (support), red = call OI (resistance)
- Top 5 support levels (put walls below current price)
- Top 5 resistance levels (call walls above current price)
- Current price dotted line on chart

### Added in Nov 2026 session
- **Premium data** — bid/ask/last price + IV shown in the summary table for each top level; also shown in chart hover tooltips
- **Strategy Calculator** panel (per expiration tab):
  - **Long Put calculator**: enter strike + premium paid → shows breakeven, % drop needed from current price, P&L at various scenarios
  - **Sold Puts calculator**: enter 1-2 strikes + premiums received → shows effective cost basis if assigned, max profit if unassigned
- **Key Level annotations**: URL params (`support1`, `support2`, `eject`, `target`) draw colored horizontal lines on the OI chart
  - Support 1/2: green lines
  - Eject: orange dashed line
  - Breakout target: blue dot-dash line
- **Custom 3rd expiration**: input any date (e.g. Dec 24 for Christmas Eve), replaces the default year-end tab
- **Advanced options** collapsible section on homepage for all the above

---

## Deployment

- **Platform**: Railway
- **Repo**: `~/Documents/git/support-level-finder` (GitHub: `agvillacis/Support-Level-Finder`)
- **Stack**: Python / Flask / yfinance / Plotly
- **Entry point**: `app.py` (web server), `analyze.py` (core logic + HTML generation)
- **Data source**: Yahoo Finance via yfinance (free, no auth needed)
- **Railway CLI**: not installed locally — deployments happen via `git push origin main`
- **URL**: https://support-level-finder-production.up.railway.app/

---

## Known Issues / TODOs

- [ ] Store the Railway deployment URL in this file
- [ ] yfinance data can be delayed ~15 min during market hours; real-time would need Schwab API (skeleton exists in `analyze.py` → `fetch_schwab()`)
- [ ] The 3rd tab label logic uses a Python f-string that embeds the label at build time — if custom expiration label contains special chars it could break the JS
- [ ] No caching — every request re-fetches from Yahoo Finance (slow for high-traffic)
- [ ] Mobile layout works but the strategy calculator grid is tight on small screens

---

## Potential Future Features

- **Greeks display** (delta, theta, gamma) for each strike — his friend would likely use delta to gauge probability of assignment
- **Put/Call ratio** per expiration — a quick sentiment signal
- **Historical OI comparison** — see if walls have been building or shrinking over time
- **Pre-filled URL builder** — a form where you enter the ticker + all key levels and it generates a shareable URL with everything pre-loaded
- **Schwab integration** for real-time data (auth scaffold already in repo)
- **Profit/loss diagram** (risk graph) for the full combined position (sold puts + long put hedge)
