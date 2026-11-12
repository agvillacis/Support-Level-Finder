#!/usr/bin/env python3
"""
Support Level Finder
Pulls options chain data for a ticker and generates an HTML visualization
showing put/call open interest walls (support & resistance levels).

Usage:
    python3 analyze.py AAPL
    python3 analyze.py SPY --source schwab
"""

import sys
import json
import argparse
from datetime import date, timedelta
import webbrowser
import os

def get_target_expirations(custom_date=None):
    """Return the 3 target expiration date strings: nearest Friday, month-end, year-end.
    If custom_date is provided, replace year-end with it."""
    today = date.today()

    # Nearest Friday
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7  # if today is Friday, get next Friday
    nearest_friday = today + timedelta(days=days_until_friday)

    # End of this month
    if today.month == 12:
        month_end = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(today.year, today.month + 1, 1) - timedelta(days=1)
    # Walk back to nearest Friday if month-end is weekend
    while month_end.weekday() > 4:
        month_end -= timedelta(days=1)

    # End of year (last trading Friday of December)
    year_end = date(today.year, 12, 31)
    while year_end.weekday() > 4:
        year_end -= timedelta(days=1)

    third = custom_date if custom_date else year_end.strftime("%Y-%m-%d")

    return [
        nearest_friday.strftime("%Y-%m-%d"),
        month_end.strftime("%Y-%m-%d"),
        third,
    ]


def fetch_yfinance(ticker: str, target_expirations: list[str]):
    """Fetch options chain data using yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        print("Error: yfinance not installed. Run: pip3 install yfinance")
        sys.exit(1)

    stock = yf.Ticker(ticker)
    current_price = stock.fast_info.get("last_price") or stock.info.get("regularMarketPrice", 0)

    available = stock.options  # tuple of expiration date strings
    if not available:
        print(f"No options data found for {ticker}")
        sys.exit(1)

    results = {}
    for target in target_expirations:
        # Find closest available expiration to target
        best = min(available, key=lambda d: abs(
            date.fromisoformat(d) - date.fromisoformat(target)
        ))
        if best in results:
            continue  # already fetched

        chain = stock.option_chain(best)

        import pandas as pd
        calls = chain.calls[["strike", "openInterest", "lastPrice", "bid", "ask", "impliedVolatility"]].rename(columns={
            "openInterest": "call_oi",
            "lastPrice": "call_last",
            "bid": "call_bid",
            "ask": "call_ask",
            "impliedVolatility": "call_iv",
        })
        puts = chain.puts[["strike", "openInterest", "lastPrice", "bid", "ask", "impliedVolatility"]].rename(columns={
            "openInterest": "put_oi",
            "lastPrice": "put_last",
            "bid": "put_bid",
            "ask": "put_ask",
            "impliedVolatility": "put_iv",
        })

        merged = pd.merge(calls, puts, on="strike", how="outer").fillna(0)
        merged = merged.sort_values("strike").reset_index(drop=True)

        results[best] = {
            "label": best,
            "expiration": best,
            "strikes": merged["strike"].tolist(),
            "call_oi": merged["call_oi"].astype(int).tolist(),
            "put_oi":  merged["put_oi"].astype(int).tolist(),
            "call_last": merged["call_last"].round(2).tolist(),
            "call_bid":  merged["call_bid"].round(2).tolist(),
            "call_ask":  merged["call_ask"].round(2).tolist(),
            "call_iv":   (merged["call_iv"] * 100).round(1).tolist(),
            "put_last":  merged["put_last"].round(2).tolist(),
            "put_bid":   merged["put_bid"].round(2).tolist(),
            "put_ask":   merged["put_ask"].round(2).tolist(),
            "put_iv":    (merged["put_iv"] * 100).round(1).tolist(),
        }

    return current_price, results


def expiration_label(target: str, actual: str) -> str:
    labels = {0: "This Week", 1: "Month End", 2: "Year End"}
    # We'll assign labels in order
    return actual


def fetch_schwab(ticker: str, target_expirations: list[str]):
    """Fetch options chain data using Schwab API. Requires schwab_config.json."""
    try:
        from schwab_client import SchwabClient
    except ImportError:
        print("Schwab client not configured. See README for setup instructions.")
        sys.exit(1)

    client = SchwabClient()
    return client.get_options_chain(ticker, target_expirations)


def build_html(ticker: str, current_price: float, chains: dict, output_file: str,
               key_levels=None, custom_exp_label=None):
    """Generate a self-contained HTML file with Plotly charts."""

    expiration_keys = list(chains.keys())
    exp_labels = ["This Week", "Month End", custom_exp_label or "Year End"]

    charts_data = []

    for i, (exp_date, data) in enumerate(chains.items()):
        label = exp_labels[i] if i < len(exp_labels) else exp_date
        tab_id = f"tab{i}"
        charts_data.append({
            "id": tab_id,
            "label": label,
            "expiration": exp_date,
            "strikes": data["strikes"],
            "call_oi": data["call_oi"],
            "put_oi": data["put_oi"],
            "call_last": data.get("call_last", []),
            "call_bid":  data.get("call_bid", []),
            "call_ask":  data.get("call_ask", []),
            "call_iv":   data.get("call_iv", []),
            "put_last":  data.get("put_last", []),
            "put_bid":   data.get("put_bid", []),
            "put_ask":   data.get("put_ask", []),
            "put_iv":    data.get("put_iv", []),
        })

    charts_json = json.dumps(charts_data)
    key_levels_json = json.dumps(key_levels or [])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{ticker} — Support & Resistance Finder</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f0f; color: #e0e0e0; }}
  header {{ padding: 20px 30px; border-bottom: 1px solid #222; display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }}
  header h1 {{ font-size: 1.6rem; color: #fff; }}
  .price-badge {{ background: #1a1a2e; border: 1px solid #3a3a5c; padding: 4px 12px; border-radius: 20px; font-size: 0.9rem; }}
  .price-badge span {{ color: #7eb8f7; font-weight: 600; }}
  .tabs {{ display: flex; gap: 4px; padding: 16px 30px 0; border-bottom: 1px solid #222; flex-wrap: wrap; }}
  .tab {{ padding: 8px 20px; border-radius: 6px 6px 0 0; cursor: pointer; font-size: 0.9rem; color: #888; border: 1px solid transparent; border-bottom: none; transition: all 0.15s; }}
  .tab:hover {{ color: #ccc; background: #1a1a1a; }}
  .tab.active {{ color: #fff; background: #1a1a2e; border-color: #333; }}
  .panel {{ display: none; padding: 24px 30px; }}
  .panel.active {{ display: block; }}
  .chart-wrap {{ background: #111; border: 1px solid #222; border-radius: 8px; padding: 12px; min-height: 420px; }}
  .summary {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 20px; }}
  .summary-box {{ background: #111; border: 1px solid #222; border-radius: 8px; padding: 16px; }}
  .summary-box h3 {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 12px; }}
  .support h3 {{ color: #4caf50; }}
  .resistance h3 {{ color: #ef5350; }}
  .level {{ display: flex; justify-content: space-between; align-items: flex-start; padding: 8px 0; border-bottom: 1px solid #1a1a1a; font-size: 0.9rem; gap: 8px; }}
  .level:last-child {{ border-bottom: none; }}
  .level .strike {{ font-weight: 600; color: #fff; font-size: 1rem; }}
  .level .oi {{ color: #888; font-size: 0.8rem; }}
  .level .bar {{ height: 4px; border-radius: 2px; margin-top: 4px; }}
  .support .bar {{ background: #4caf50; }}
  .resistance .bar {{ background: #ef5350; }}
  .level .premium {{ text-align: right; font-size: 0.8rem; color: #aaa; line-height: 1.6; }}
  .level .premium .last {{ color: #ffd700; font-weight: 600; font-size: 0.9rem; }}
  .level .premium .iv {{ color: #888; }}

  /* Key Levels sidebar */
  .key-levels-bar {{ display: flex; gap: 10px; padding: 12px 30px; background: #0d0d0d; border-bottom: 1px solid #1a1a1a; flex-wrap: wrap; align-items: center; }}
  .key-levels-bar label {{ font-size: 0.75rem; color: #666; text-transform: uppercase; letter-spacing: 0.06em; }}
  .kl-chip {{ padding: 3px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }}
  .kl-support {{ background: #0d2b0d; border: 1px solid #2a5c2a; color: #4caf50; }}
  .kl-resistance {{ background: #2b0d0d; border: 1px solid #5c2a2a; color: #ef5350; }}
  .kl-eject {{ background: #2b1a00; border: 1px solid #5c3a00; color: #ff9800; }}
  .kl-target {{ background: #0d1a2b; border: 1px solid #1a3a5c; color: #64b5f6; }}

  /* Strategy Calculator */
  .calc-section {{ margin-top: 24px; }}
  .calc-section h2 {{ font-size: 1rem; color: #ccc; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid #222; }}
  .calc-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}
  .calc-box {{ background: #111; border: 1px solid #222; border-radius: 8px; padding: 16px; }}
  .calc-box h3 {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em; color: #888; margin-bottom: 14px; }}
  .calc-row {{ display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }}
  .calc-row label {{ font-size: 0.8rem; color: #666; width: 120px; flex-shrink: 0; }}
  .calc-row input {{ flex: 1; background: #1a1a1a; border: 1px solid #333; color: #fff; padding: 6px 10px; border-radius: 6px; font-size: 0.9rem; outline: none; width: 100px; }}
  .calc-row input:focus {{ border-color: #555; }}
  .calc-btn {{ background: #2563eb; color: #fff; border: none; padding: 8px 18px; border-radius: 6px; font-size: 0.85rem; cursor: pointer; font-weight: 600; margin-top: 4px; }}
  .calc-btn:hover {{ background: #1d4ed8; }}
  .calc-result {{ margin-top: 12px; padding: 12px; background: #0a0a0a; border-radius: 6px; border: 1px solid #1a1a1a; font-size: 0.85rem; line-height: 2; display: none; }}
  .calc-result .hl {{ color: #ffd700; font-weight: 600; }}
  .calc-result .green {{ color: #4caf50; font-weight: 600; }}
  .calc-result .red {{ color: #ef5350; font-weight: 600; }}
  .calc-result .orange {{ color: #ff9800; font-weight: 600; }}

  footer {{ padding: 16px 30px; color: #444; font-size: 0.75rem; border-top: 1px solid #1a1a1a; margin-top: 20px; }}

  @media (max-width: 1100px) {{
    .calc-grid {{ grid-template-columns: 1fr 1fr; }}
  }}
  @media (max-width: 700px) {{
    .summary, .calc-grid {{ grid-template-columns: 1fr; }}
    header, .tabs, .panel, .key-levels-bar {{ padding-left: 16px; padding-right: 16px; }}
  }}
</style>
</head>
<body>

<header>
  <h1>{ticker} — Put/Call OI Walls</h1>
  <div class="price-badge">Current price: <span>${current_price:.2f}</span></div>
  <a href="/" style="margin-left:auto; color:#3b82f6; font-size:0.85rem; text-decoration:none;">← New Search</a>
</header>

{'<div class="key-levels-bar">' + _build_key_levels_html(key_levels) + '</div>' if key_levels else ''}

<div class="tabs" id="tabs"></div>
<div id="panels"></div>

<footer>Data via Yahoo Finance · Generated {date.today().strftime("%B %d, %Y")} · OI = Open Interest contracts · Premium = last/bid/ask · IV = Implied Volatility</footer>

<script>
const TICKER = "{ticker}";
const CURRENT_PRICE = {current_price:.2f};
const CHAINS = {charts_json};
const KEY_LEVELS = {key_levels_json};

function formatOI(n) {{
  if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n/1000).toFixed(1) + 'K';
  return n.toString();
}}

function topLevels(data, side, n=20) {{
  const {{ strikes, put_oi, call_oi, put_last, put_bid, put_ask, put_iv, call_last, call_bid, call_ask, call_iv }} = data;
  const rangeMin = CURRENT_PRICE * 0.65;
  const rangeMax = CURRENT_PRICE * 1.35;
  let pairs = strikes.map((s,i) => ({{
    strike: s,
    oi: side === 'support' ? put_oi[i] : call_oi[i],
    last: side === 'support' ? put_last[i] : call_last[i],
    bid:  side === 'support' ? put_bid[i] : call_bid[i],
    ask:  side === 'support' ? put_ask[i] : call_ask[i],
    iv:   side === 'support' ? put_iv[i] : call_iv[i],
  }}));
  if (side === 'support') pairs = pairs.filter(p => p.strike <= CURRENT_PRICE && p.strike >= rangeMin);
  else pairs = pairs.filter(p => p.strike >= CURRENT_PRICE && p.strike <= rangeMax);
  pairs.sort((a,b) => b.oi - a.oi);
  return pairs.slice(0, n);
}}

function buildChart(container, data) {{
  const keyShapes = KEY_LEVELS.map(kl => ({{
    type: 'line',
    x0: 0, x1: 1, xref: 'paper',
    y0: kl.price, y1: kl.price,
    line: {{ color: kl.color, width: 1.2, dash: kl.dash || 'dot' }}
  }}));

  const keyAnnotations = KEY_LEVELS.map(kl => ({{
    x: 1, xref: 'paper',
    y: kl.price,
    text: `  ${{kl.label}} ${{kl.price}}`,
    showarrow: false,
    xanchor: 'left',
    font: {{ color: kl.color, size: 10 }},
  }}));

  // Filter chart to ±25% of current price — includes key levels while keeping bars visible
  const chartMin = CURRENT_PRICE * 0.75;
  const chartMax = CURRENT_PRICE * 1.25;
  const idx = data.strikes.map((s,i) => i).filter(i => data.strikes[i] >= chartMin && data.strikes[i] <= chartMax);
  const fStrikes  = idx.map(i => data.strikes[i]);
  const fPutOI    = idx.map(i => data.put_oi[i]);
  const fCallOI   = idx.map(i => data.call_oi[i]);
  const fPutMeta  = idx.map(i => [data.put_last[i], data.put_bid[i], data.put_ask[i], data.put_iv[i]]);
  const fCallMeta = idx.map(i => [data.call_last[i], data.call_bid[i], data.call_ask[i], data.call_iv[i]]);

  const traces = [
    {{
      name: 'Put OI (Support)',
      x: fStrikes,
      y: fPutOI,
      type: 'bar',
      marker: {{ color: fStrikes.map(s => s <= CURRENT_PRICE ? '#4caf50' : '#2a5c2a') }},
      hovertemplate: 'Strike $%{{x}}<br>Put OI: %{{y:,}}<br>Last: $%{{customdata[0]}}<br>Bid/Ask: $%{{customdata[1]}}/$%{{customdata[2]}}<br>IV: %{{customdata[3]}}%<extra></extra>',
      customdata: fPutMeta,
    }},
    {{
      name: 'Call OI (Resistance)',
      x: fStrikes,
      y: fCallOI,
      type: 'bar',
      marker: {{ color: fStrikes.map(s => s >= CURRENT_PRICE ? '#ef5350' : '#5c2a2a') }},
      hovertemplate: 'Strike $%{{x}}<br>Call OI: %{{y:,}}<br>Last: $%{{customdata[0]}}<br>Bid/Ask: $%{{customdata[1]}}/$%{{customdata[2]}}<br>IV: %{{customdata[3]}}%<extra></extra>',
      customdata: fCallMeta,
    }}
  ];

  const layout = {{
    barmode: 'group',
    height: 400,
    paper_bgcolor: '#111',
    plot_bgcolor: '#111',
    font: {{ color: '#ccc', size: 11 }},
    xaxis: {{
      title: 'Strike Price ($)',
      gridcolor: '#1f1f1f',
      tickprefix: '$',
      range: [chartMin, chartMax],
    }},
    yaxis: {{
      title: 'Open Interest (contracts)',
      gridcolor: '#1f1f1f',
    }},
    legend: {{ bgcolor: 'transparent', x: 0.01, y: 0.99 }},
    margin: {{ t: 20, r: 100, b: 60, l: 70 }},
    shapes: [
      {{
        type: 'line',
        x0: CURRENT_PRICE, x1: CURRENT_PRICE,
        y0: 0, y1: 1,
        yref: 'paper',
        line: {{ color: '#fff', width: 1.5, dash: 'dot' }},
      }},
      ...keyShapes
    ],
    annotations: [
      {{
        x: CURRENT_PRICE, y: 1, yref: 'paper',
        text: ' $' + CURRENT_PRICE.toFixed(2),
        showarrow: false, xanchor: 'left',
        font: {{ color: '#fff', size: 11 }}
      }},
      ...keyAnnotations
    ]
  }};

  Plotly.newPlot(container, traces, layout, {{responsive: true, displayModeBar: false}});
}}

function buildSummary(container, data) {{
  const supports = topLevels(data, 'support');
  const resistances = topLevels(data, 'resistance');
  const maxOI = Math.max(...data.put_oi, ...data.call_oi);

  function levelsHtml(levels, side) {{
    return levels.map(l => {{
      const pct = Math.round((l.oi / maxOI) * 100);
      const premiumHtml = l.last > 0 ? `
        <div class="premium">
          <div class="last">${{l.last.toFixed(2)}}</div>
          <div>b/a ${{l.bid.toFixed(2)}}/${{l.ask.toFixed(2)}}</div>
          <div class="iv">IV ${{l.iv.toFixed(1)}}%</div>
        </div>` : '';
      return `<div class="level">
        <div>
          <div class="strike">$${{l.strike.toFixed(2)}}</div>
          <div class="oi">${{formatOI(l.oi)}} contracts</div>
          <div class="bar" style="width:${{pct}}%; min-width:4px"></div>
        </div>
        ${{premiumHtml}}
      </div>`;
    }}).join('');
  }}

  container.innerHTML = `
    <div class="summary">
      <div class="summary-box support">
        <h3>Top Support (Put Walls) · Premium = put cost</h3>
        ${{levelsHtml(supports, 'support')}}
      </div>
      <div class="summary-box resistance">
        <h3>Top Resistance (Call Walls) · Premium = call cost</h3>
        ${{levelsHtml(resistances, 'resistance')}}
      </div>
    </div>`;
}}

function buildCalc(container, data) {{
  container.innerHTML = `
  <div class="calc-section">
    <h2>⚡ Options Strategy Calculator</h2>
    <p style="font-size:0.75rem;color:#555;margin-bottom:12px">Type a strike and press Enter — premium auto-fills from live chain data for this expiration.</p>
    <div class="calc-grid">

      <div class="calc-box">
        <h3>Long Put — Protective Hedge</h3>
        <p style="font-size:0.8rem;color:#666;margin-bottom:12px">Buy a put for downside protection. Calculates breakeven and profit zones.</p>
        <div class="calc-row"><label>Put Strike ($)</label><input class="lp_strike" type="number" placeholder="e.g. 160" step="0.5"></div>
        <div class="calc-row"><label>Premium Paid ($)</label><input class="lp_premium" type="number" placeholder="auto-fills ↑" step="0.01"></div>
        <div class="calc-row"><label>Contracts</label><input class="lp_qty" type="number" placeholder="1" value="1" step="1"></div>
        <button class="calc-btn lp_btn">Calculate</button>
        <div class="calc-result lp_result"></div>
      </div>

      <div class="calc-box">
        <h3>Sold Puts — Cost Basis if Assigned</h3>
        <p style="font-size:0.8rem;color:#666;margin-bottom:12px">Sell puts to collect premium. Shows effective cost if assigned at each strike.</p>
        <div class="calc-row"><label>Strike 1 ($)</label><input class="sp_s1" type="number" placeholder="e.g. 170" step="0.5"></div>
        <div class="calc-row"><label>Premium Recv ($)</label><input class="sp_p1" type="number" placeholder="auto-fills ↑" step="0.01"></div>
        <div class="calc-row"><label>Strike 2 ($) <small style="color:#555">(opt)</small></label><input class="sp_s2" type="number" placeholder="e.g. 165" step="0.5"></div>
        <div class="calc-row"><label>Premium Recv ($)</label><input class="sp_p2" type="number" placeholder="auto-fills ↑" step="0.01"></div>
        <button class="calc-btn sp_btn">Calculate</button>
        <div class="calc-result sp_result"></div>
      </div>

      <div class="calc-box">
        <h3>Sold Calls — Covered Call (Own Shares)</h3>
        <p style="font-size:0.8rem;color:#666;margin-bottom:12px">You own the shares and sell a call above your cost basis. Collect premium now; if stock rises above strike, shares get called away at that price.</p>
        <div class="calc-row"><label>Call Strike ($)</label><input class="sc_strike" type="number" placeholder="e.g. 190" step="0.5"></div>
        <div class="calc-row"><label>Premium Recv ($)</label><input class="sc_premium" type="number" placeholder="auto-fills ↑" step="0.01"></div>
        <div class="calc-row"><label>Your Cost Basis ($)</label><input class="sc_basis" type="number" placeholder="e.g. 165" step="0.5"></div>
        <div class="calc-row"><label>Contracts</label><input class="sc_qty" type="number" placeholder="1" value="1" step="1"></div>
        <button class="calc-btn sc_btn">Calculate</button>
        <div class="calc-result sc_result"></div>
      </div>

    </div>
  </div>`;

  function q(cls) {{ return container.querySelector('.' + cls); }}

  // Auto-fill premium when strike is entered (Enter key or blur)
  function lookupPremium(strikeVal, lastArr, bidArr, askArr) {{
    const target = parseFloat(strikeVal);
    if (isNaN(target)) return '';
    let best = -1, bestDist = Infinity;
    data.strikes.forEach((s, i) => {{
      const d = Math.abs(s - target);
      if (d < bestDist) {{ bestDist = d; best = i; }}
    }});
    if (best < 0 || bestDist > 5) return '';
    const bid = bidArr[best], ask = askArr[best], last = lastArr[best];
    if (bid > 0 && ask > 0) return ((bid + ask) / 2).toFixed(2);
    return last > 0 ? last.toFixed(2) : '';
  }}

  function wireAutoFill(strikeClass, premiumClass, lastArr, bidArr, askArr) {{
    const strikeInput = container.querySelector('.' + strikeClass);
    const premiumInput = container.querySelector('.' + premiumClass);
    if (!strikeInput || !premiumInput) return;
    const fill = () => {{
      const val = lookupPremium(strikeInput.value, lastArr, bidArr, askArr);
      if (val) {{ premiumInput.value = val; premiumInput.style.borderColor = '#2563eb'; }}
    }};
    strikeInput.addEventListener('change', fill);
    strikeInput.addEventListener('keydown', e => {{ if (e.key === 'Enter') fill(); }});
  }}

  wireAutoFill('lp_strike', 'lp_premium', data.put_last, data.put_bid, data.put_ask);
  wireAutoFill('sp_s1', 'sp_p1', data.put_last, data.put_bid, data.put_ask);
  wireAutoFill('sp_s2', 'sp_p2', data.put_last, data.put_bid, data.put_ask);
  wireAutoFill('sc_strike', 'sc_premium', data.call_last, data.call_bid, data.call_ask);

  // Scoped calculate functions — use container.querySelector so each tab is independent
  q('lp_btn').addEventListener('click', () => {{
    const strike = parseFloat(q('lp_strike').value);
    const premium = parseFloat(q('lp_premium').value);
    const qty = parseInt(q('lp_qty').value) || 1;
    if (isNaN(strike) || isNaN(premium)) {{ alert('Enter strike and premium'); return; }}
    const breakeven = strike - premium;
    const cost = premium * 100 * qty;
    const r = q('lp_result');
    r.style.display = 'block';
    r.innerHTML = `
      <div>Strike: <span class="hl">$${{strike.toFixed(2)}}</span>  ·  Premium: <span class="hl">$${{premium.toFixed(2)}}</span>  ·  Qty: ${{qty}} contract${{qty>1?'s':''}}</div>
      <div>Total Cost: <span class="red">$${{cost.toFixed(2)}}</span></div>
      <div>Break-even: <span class="hl">$${{breakeven.toFixed(2)}}</span> (stock must close below this)</div>
      <div>Drop needed from <span class="hl">$${{CURRENT_PRICE.toFixed(2)}}</span>: <span class="orange">${{((CURRENT_PRICE - breakeven)/CURRENT_PRICE*100).toFixed(1)}}%</span></div>
      <div style="margin-top:8px;font-size:0.8rem;color:#666;">P&L at various prices:</div>
      ${{[breakeven*0.98, breakeven*0.95, breakeven*0.90, breakeven*0.80].map(p => {{
        const pnl = (strike - p - premium) * 100 * qty;
        return `<div>@ $${{p.toFixed(2)}}: <span class="${{pnl>0?'green':'red'}}">+$${{pnl.toFixed(0)}}</span></div>`;
      }}).join('')}}
    `;
  }});

  q('sp_btn').addEventListener('click', () => {{
    const s1 = parseFloat(q('sp_s1').value);
    const p1 = parseFloat(q('sp_p1').value);
    const s2 = parseFloat(q('sp_s2').value);
    const p2 = parseFloat(q('sp_p2').value);
    if (isNaN(s1) || isNaN(p1)) {{ alert('Enter at least Strike 1 and its premium'); return; }}
    const r = q('sp_result');
    r.style.display = 'block';
    const totalPremium = p1 + (isNaN(p2) ? 0 : p2);
    const cost1 = s1 - p1;
    let html = `<div>Sell put @ $${{s1}}: collect <span class="green">$${{p1.toFixed(2)}}</span> → effective cost if assigned: <span class="hl">$${{cost1.toFixed(2)}}</span></div>`;
    if (!isNaN(s2) && !isNaN(p2)) {{
      const cost2 = s2 - p2;
      const avgCost = (cost1 + cost2) / 2;
      html += `<div>Sell put @ $${{s2}}: collect <span class="green">$${{p2.toFixed(2)}}</span> → effective cost if assigned: <span class="hl">$${{cost2.toFixed(2)}}</span></div>`;
      html += `<div style="margin-top:8px">Total premium collected: <span class="green">$${{totalPremium.toFixed(2)}}</span></div>`;
      html += `<div>Avg effective cost (both assigned): <span class="hl">$${{avgCost.toFixed(2)}}</span></div>`;
      html += `<div>Max profit (neither assigned): <span class="green">$${{(totalPremium * 100).toFixed(0)}} per pair of contracts</span></div>`;
    }} else {{
      html += `<div>Total premium: <span class="green">$${{p1.toFixed(2)}}</span></div>`;
      html += `<div>Max profit (not assigned): <span class="green">$${{(p1*100).toFixed(0)}} per contract</span></div>`;
    }}
    r.innerHTML = html;
  }});

  q('sc_btn').addEventListener('click', () => {{
    const strike = parseFloat(q('sc_strike').value);
    const premium = parseFloat(q('sc_premium').value);
    const basis = parseFloat(q('sc_basis').value);
    const qty = parseInt(q('sc_qty').value) || 1;
    if (isNaN(strike) || isNaN(premium)) {{ alert('Enter strike and premium'); return; }}
    const effectiveSale = strike + premium;
    const income = premium * 100 * qty;
    const r = q('sc_result');
    r.style.display = 'block';
    let html = `
      <div>Sell call @ <span class="hl">$${{strike.toFixed(2)}}</span>  ·  Premium: <span class="green">+$${{premium.toFixed(2)}}</span>  ·  Qty: ${{qty}} contract${{qty>1?'s':''}}</div>
      <div>Premium collected: <span class="green">$${{income.toFixed(0)}}</span></div>
      <div>Effective sale price if called away: <span class="hl">$${{effectiveSale.toFixed(2)}}</span></div>
      <div>Stock must stay below <span class="hl">$${{strike.toFixed(2)}}</span> to keep full premium</div>
    `;
    if (!isNaN(basis)) {{
      const profit = effectiveSale - basis;
      const profitPct = profit / basis * 100;
      const premiumYield = premium / basis * 100;
      html += `<div style="margin-top:8px;border-top:1px solid #222;padding-top:8px;">`;
      html += `<div>Your cost basis: <span class="hl">$${{basis.toFixed(2)}}</span></div>`;
      html += `<div>Profit if called away: <span class="${{profit>=0?'green':'red'}}">$${{(profit*100*qty).toFixed(0)}} (${{profitPct.toFixed(1)}}% return)</span></div>`;
      html += `<div>Premium yield on basis: <span class="green">${{premiumYield.toFixed(2)}}%</span></div>`;
      if (profit < 0) html += `<div><span class="orange">⚠ Called away below your cost basis — you'd take a loss</span></div>`;
      html += `</div>`;
    }}
    html += `<div style="margin-top:8px;font-size:0.8rem;color:#666;">P&L at various stock prices:</div>`;
    [strike*0.95, strike, strike*1.05, strike*1.15].forEach(p => {{
      const called = p >= strike;
      const pnl = called ? (effectiveSale - (isNaN(basis) ? CURRENT_PRICE : basis)) * 100 * qty : income;
      html += `<div>@ $${{p.toFixed(2)}}: ${{called ? 'called away' : 'keep premium'}} → <span class="${{pnl>=0?'green':'red'}}">$${{pnl.toFixed(0)}}</span></div>`;
    }});
    r.innerHTML = html;
  }});
}}

// Build tabs and panels
const tabsEl = document.getElementById('tabs');
const panelsEl = document.getElementById('panels');

CHAINS.forEach((data, i) => {{
  const tab = document.createElement('div');
  tab.className = 'tab' + (i === 0 ? ' active' : '');
  tab.textContent = ['This Week', 'Month End', '{custom_exp_label or "Year End"}'][i] || data.expiration;
  tab.dataset.exp = data.expiration;
  tab.addEventListener('click', () => {{
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(data.id).classList.add('active');
  }});
  tabsEl.appendChild(tab);

  const panel = document.createElement('div');
  panel.className = 'panel' + (i === 0 ? ' active' : '');
  panel.id = data.id;

  const chartDiv = document.createElement('div');
  chartDiv.className = 'chart-wrap';
  chartDiv.id = data.id + '_chart';
  panel.appendChild(chartDiv);

  const summaryDiv = document.createElement('div');
  panel.appendChild(summaryDiv);

  const calcDiv = document.createElement('div');
  panel.appendChild(calcDiv);

  panelsEl.appendChild(panel);

  setTimeout(() => {{
    buildChart(chartDiv, data);
    buildSummary(summaryDiv, data);
    buildCalc(calcDiv, data);
  }}, i * 100);
}});
</script>
</body>
</html>"""

    with open(output_file, "w") as f:
        f.write(html)


def _build_key_levels_html(key_levels):
    """Build the key levels bar HTML (called at Python render time)."""
    if not key_levels:
        return ''
    html = '<label>Key Levels:</label>'
    for kl in key_levels:
        cls_map = {'support': 'kl-support', 'resistance': 'kl-resistance', 'eject': 'kl-eject', 'target': 'kl-target'}
        cls = cls_map.get(kl.get('type', 'support'), 'kl-support')
        html += f'<span class="kl-chip {cls}">{kl["label"]} ${kl["price"]}</span>'
    return html


def main():
    parser = argparse.ArgumentParser(description="Support Level Finder — Options OI Visualizer")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g. AAPL, SPY)")
    parser.add_argument("--source", choices=["yfinance", "schwab"], default="yfinance",
                        help="Data source (default: yfinance)")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    parser.add_argument("--exp", help="Custom 3rd expiration date (YYYY-MM-DD), default is year-end")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    print(f"Fetching options chain for {ticker}...")

    targets = get_target_expirations(custom_date=args.exp)
    print(f"Target expirations: {', '.join(targets)}")

    if args.source == "schwab":
        current_price, chains = fetch_schwab(ticker, targets)
    else:
        current_price, chains = fetch_yfinance(ticker, targets)

    print(f"Current price: ${current_price:.2f}")
    print(f"Found data for {len(chains)} expiration(s): {', '.join(chains.keys())}")

    output_file = f"{ticker}_support_levels.html"
    build_html(ticker, current_price, chains, output_file, custom_exp_label=args.exp)

    abs_path = os.path.abspath(output_file)
    print(f"\nReport saved: {abs_path}")

    if not args.no_open:
        webbrowser.open(f"file://{abs_path}")
        print("Opened in browser.")


if __name__ == "__main__":
    main()
