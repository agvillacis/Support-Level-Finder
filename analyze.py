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

def get_target_expirations():
    """Return the 3 target expiration date strings: nearest Friday, month-end, year-end."""
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

    return [
        nearest_friday.strftime("%Y-%m-%d"),
        month_end.strftime("%Y-%m-%d"),
        year_end.strftime("%Y-%m-%d"),
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
        calls = chain.calls[["strike", "openInterest"]].rename(columns={"openInterest": "call_oi"})
        puts  = chain.puts[["strike", "openInterest"]].rename(columns={"openInterest": "put_oi"})

        import pandas as pd
        merged = pd.merge(calls, puts, on="strike", how="outer").fillna(0)
        merged = merged.sort_values("strike").reset_index(drop=True)

        results[best] = {
            "label": expiration_label(target, best),
            "expiration": best,
            "strikes": merged["strike"].tolist(),
            "call_oi": merged["call_oi"].astype(int).tolist(),
            "put_oi":  merged["put_oi"].astype(int).tolist(),
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


def build_html(ticker: str, current_price: float, chains: dict, output_file: str):
    """Generate a self-contained HTML file with Plotly charts."""

    expiration_keys = list(chains.keys())
    exp_labels = ["This Week", "Month End", "Year End"]

    tabs_html = ""
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
        })

    charts_json = json.dumps(charts_data)

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
  header {{ padding: 20px 30px; border-bottom: 1px solid #222; display: flex; align-items: baseline; gap: 16px; }}
  header h1 {{ font-size: 1.6rem; color: #fff; }}
  .price-badge {{ background: #1a1a2e; border: 1px solid #3a3a5c; padding: 4px 12px; border-radius: 20px; font-size: 0.9rem; }}
  .price-badge span {{ color: #7eb8f7; font-weight: 600; }}
  .tabs {{ display: flex; gap: 4px; padding: 16px 30px 0; border-bottom: 1px solid #222; }}
  .tab {{ padding: 8px 20px; border-radius: 6px 6px 0 0; cursor: pointer; font-size: 0.9rem; color: #888; border: 1px solid transparent; border-bottom: none; transition: all 0.15s; }}
  .tab:hover {{ color: #ccc; background: #1a1a1a; }}
  .tab.active {{ color: #fff; background: #1a1a2e; border-color: #333; }}
  .panel {{ display: none; padding: 24px 30px; }}
  .panel.active {{ display: block; }}
  .chart-wrap {{ background: #111; border: 1px solid #222; border-radius: 8px; padding: 12px; }}
  .summary {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 20px; }}
  .summary-box {{ background: #111; border: 1px solid #222; border-radius: 8px; padding: 16px; }}
  .summary-box h3 {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 12px; }}
  .support h3 {{ color: #4caf50; }}
  .resistance h3 {{ color: #ef5350; }}
  .level {{ display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #1a1a1a; font-size: 0.9rem; }}
  .level:last-child {{ border-bottom: none; }}
  .level .strike {{ font-weight: 600; color: #fff; }}
  .level .oi {{ color: #888; font-size: 0.8rem; }}
  .level .bar {{ height: 4px; border-radius: 2px; margin-top: 4px; }}
  .support .bar {{ background: #4caf50; }}
  .resistance .bar {{ background: #ef5350; }}
  footer {{ padding: 16px 30px; color: #444; font-size: 0.75rem; border-top: 1px solid #1a1a1a; margin-top: 20px; }}
</style>
</head>
<body>

<header>
  <h1>{ticker} — Put/Call OI Walls</h1>
  <div class="price-badge">Current price: <span>${current_price:.2f}</span></div>
</header>

<div class="tabs" id="tabs"></div>
<div id="panels"></div>

<footer>Data via Yahoo Finance · Generated {date.today().strftime("%B %d, %Y")} · OI = Open Interest contracts</footer>

<script>
const TICKER = "{ticker}";
const CURRENT_PRICE = {current_price:.2f};
const CHAINS = {charts_json};

function formatOI(n) {{
  if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n/1000).toFixed(1) + 'K';
  return n.toString();
}}

function topLevels(strikes, oi, side, n=5) {{
  let pairs = strikes.map((s,i) => ({{strike: s, oi: oi[i]}}));
  if (side === 'support') pairs = pairs.filter(p => p.strike <= CURRENT_PRICE);
  else pairs = pairs.filter(p => p.strike >= CURRENT_PRICE);
  pairs.sort((a,b) => b.oi - a.oi);
  return pairs.slice(0, n);
}}

function buildChart(container, data) {{
  const traces = [
    {{
      name: 'Put OI (Support)',
      x: data.strikes,
      y: data.put_oi,
      type: 'bar',
      marker: {{ color: data.strikes.map(s => s <= CURRENT_PRICE ? '#4caf50' : '#2a5c2a') }},
      hovertemplate: 'Strike $%{{x}}<br>Put OI: %{{y:,}}<extra></extra>'
    }},
    {{
      name: 'Call OI (Resistance)',
      x: data.strikes,
      y: data.call_oi,
      type: 'bar',
      marker: {{ color: data.strikes.map(s => s >= CURRENT_PRICE ? '#ef5350' : '#5c2a2a') }},
      hovertemplate: 'Strike $%{{x}}<br>Call OI: %{{y:,}}<extra></extra>'
    }}
  ];

  const layout = {{
    barmode: 'group',
    paper_bgcolor: '#111',
    plot_bgcolor: '#111',
    font: {{ color: '#ccc', size: 11 }},
    xaxis: {{
      title: 'Strike Price ($)',
      gridcolor: '#1f1f1f',
      tickformat: '$.0f',
    }},
    yaxis: {{
      title: 'Open Interest (contracts)',
      gridcolor: '#1f1f1f',
    }},
    legend: {{ bgcolor: 'transparent', x: 0.01, y: 0.99 }},
    margin: {{ t: 20, r: 20, b: 60, l: 70 }},
    shapes: [{{
      type: 'line',
      x0: CURRENT_PRICE, x1: CURRENT_PRICE,
      y0: 0, y1: 1,
      yref: 'paper',
      line: {{ color: '#fff', width: 1.5, dash: 'dot' }}
    }}],
    annotations: [{{
      x: CURRENT_PRICE, y: 1, yref: 'paper',
      text: ' $' + CURRENT_PRICE.toFixed(2),
      showarrow: false, xanchor: 'left',
      font: {{ color: '#fff', size: 11 }}
    }}]
  }};

  Plotly.newPlot(container, traces, layout, {{responsive: true, displayModeBar: false}});
}}

function buildSummary(container, data) {{
  const supports = topLevels(data.strikes, data.put_oi, 'support');
  const resistances = topLevels(data.strikes, data.call_oi, 'resistance');
  const maxOI = Math.max(...data.put_oi, ...data.call_oi);

  function levelsHtml(levels, cls) {{
    return levels.map(l => {{
      const pct = Math.round((l.oi / maxOI) * 100);
      return `<div class="level">
        <div>
          <div class="strike">${{l.strike.toFixed(2)}}</div>
          <div class="bar" style="width:${{pct}}%; min-width:4px"></div>
        </div>
        <div class="oi">${{formatOI(l.oi)}} contracts</div>
      </div>`;
    }}).join('');
  }}

  container.innerHTML = `
    <div class="summary">
      <div class="summary-box support">
        <h3>Top Support Levels (Put Walls)</h3>
        ${{levelsHtml(supports, 'support')}}
      </div>
      <div class="summary-box resistance">
        <h3>Top Resistance Levels (Call Walls)</h3>
        ${{levelsHtml(resistances, 'resistance')}}
      </div>
    </div>`;
}}

// Build tabs and panels
const tabsEl = document.getElementById('tabs');
const panelsEl = document.getElementById('panels');

CHAINS.forEach((data, i) => {{
  const tab = document.createElement('div');
  tab.className = 'tab' + (i === 0 ? ' active' : '');
  tab.textContent = ['This Week', 'Month End', 'Year End'][i] || data.expiration;
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

  panelsEl.appendChild(panel);

  // Render chart (slight delay for non-active panels)
  setTimeout(() => {{
    buildChart(chartDiv, data);
    buildSummary(summaryDiv, data);
  }}, i * 100);
}});
</script>
</body>
</html>"""

    with open(output_file, "w") as f:
        f.write(html)


def main():
    parser = argparse.ArgumentParser(description="Support Level Finder — Options OI Visualizer")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g. AAPL, SPY)")
    parser.add_argument("--source", choices=["yfinance", "schwab"], default="yfinance",
                        help="Data source (default: yfinance)")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    print(f"Fetching options chain for {ticker}...")

    targets = get_target_expirations()
    print(f"Target expirations: {', '.join(targets)}")

    if args.source == "schwab":
        current_price, chains = fetch_schwab(ticker, targets)
    else:
        current_price, chains = fetch_yfinance(ticker, targets)

    print(f"Current price: ${current_price:.2f}")
    print(f"Found data for {len(chains)} expiration(s): {', '.join(chains.keys())}")

    output_file = f"{ticker}_support_levels.html"
    build_html(ticker, current_price, chains, output_file)

    abs_path = os.path.abspath(output_file)
    print(f"\nReport saved: {abs_path}")

    if not args.no_open:
        webbrowser.open(f"file://{abs_path}")
        print("Opened in browser.")


if __name__ == "__main__":
    main()
