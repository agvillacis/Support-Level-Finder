#!/usr/bin/env python3
"""
Web server wrapper for Support Level Finder.
Deploy to Railway or Vercel — user enters a ticker, gets the HTML chart back.
"""

import os
import sys
import json
import tempfile
from flask import Flask, request, render_template_string, Response

sys.path.insert(0, os.path.dirname(__file__))
from analyze import get_target_expirations, fetch_yfinance, build_html

app = Flask(__name__)

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Support Level Finder</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f0f0f; color: #e0e0e0; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; padding: 20px; }
  .card { background: #111; border: 1px solid #222; border-radius: 12px;
          padding: 40px 48px; max-width: 540px; width: 100%; text-align: center; }
  h1 { font-size: 1.6rem; color: #fff; margin-bottom: 8px; }
  p.sub { color: #888; margin-bottom: 28px; font-size: 0.95rem; line-height: 1.5; }
  .row { display: flex; gap: 10px; margin-bottom: 10px; }
  input, select { flex: 1; background: #1a1a1a; border: 1px solid #333; color: #fff;
          padding: 12px 16px; border-radius: 8px; font-size: 1rem; outline: none; }
  input[name=ticker] { text-transform: uppercase; letter-spacing: 0.05em; }
  input:focus, select:focus { border-color: #555; }
  .levels-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; text-align: left; }
  .levels-grid label { font-size: 0.75rem; color: #666; display: block; margin-bottom: 3px; text-transform: uppercase; letter-spacing: 0.05em; }
  .levels-grid input { padding: 8px 12px; font-size: 0.9rem; }
  .section-label { font-size: 0.75rem; color: #555; text-transform: uppercase; letter-spacing: 0.08em; margin: 16px 0 8px; text-align: left; }
  button { background: #2563eb; color: #fff; border: none; padding: 12px 24px;
           border-radius: 8px; font-size: 1rem; cursor: pointer; font-weight: 600;
           transition: background 0.15s; width: 100%; }
  button:hover { background: #1d4ed8; }
  button:disabled { background: #333; cursor: not-allowed; }
  .examples { margin-top: 20px; color: #555; font-size: 0.8rem; }
  .examples a { color: #3b82f6; text-decoration: none; margin: 0 6px; }
  .examples a:hover { color: #60a5fa; }
  .error { color: #ef5350; margin-top: 16px; font-size: 0.9rem; }
  details { margin-top: 16px; text-align: left; }
  summary { font-size: 0.8rem; color: #555; cursor: pointer; padding: 6px 0; }
  summary:hover { color: #888; }
</style>
</head>
<body>
<div class="card">
  <h1>📊 Support Level Finder</h1>
  <p class="sub">Enter a ticker to see put/call open interest walls, top support &amp; resistance levels, and an options strategy calculator.</p>
  <form method="GET" action="/analyze">
    <div class="row">
      <input type="text" name="ticker" placeholder="NVDA, AAPL, SPY…" required autofocus>
    </div>

    <details>
      <summary>⚙️ Advanced options (key levels, custom expiration)</summary>
      <div style="padding: 12px 0 4px;">
        <div class="section-label">Key Levels (optional — shown as lines on chart)</div>
        <div class="levels-grid">
          <div><label>Support 1 ($)</label><input type="number" name="support1" placeholder="e.g. 152" step="0.5"></div>
          <div><label>Support 2 ($)</label><input type="number" name="support2" placeholder="e.g. 147" step="0.5"></div>
          <div><label>Eject / Stop ($)</label><input type="number" name="eject" placeholder="e.g. 145" step="0.5"></div>
          <div><label>Breakout Target ($)</label><input type="number" name="target" placeholder="e.g. 203" step="0.5"></div>
        </div>
        <div class="section-label">Custom 3rd Expiration (default: year-end)</div>
        <div class="row">
          <input type="date" name="exp" placeholder="YYYY-MM-DD">
        </div>
      </div>
    </details>

    <div style="margin-top: 14px;">
      <button type="submit">Analyze</button>
    </div>
  </form>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <div class="examples">
    Try: <a href="/analyze?ticker=NVDA">NVDA</a> <a href="/analyze?ticker=SPY">SPY</a> <a href="/analyze?ticker=AAPL">AAPL</a> <a href="/analyze?ticker=QQQ">QQQ</a>
  </div>
</div>
<script>
  document.querySelector('form').addEventListener('submit', function() {
    document.querySelector('button').disabled = true;
    document.querySelector('button').textContent = 'Loading…';
  });
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(INDEX_HTML, error=None)


@app.route("/analyze")
def analyze():
    ticker = request.args.get("ticker", "").strip().upper()
    if not ticker:
        return render_template_string(INDEX_HTML, error="Please enter a ticker symbol.")

    # Parse optional key levels
    key_levels = []
    level_defs = [
        ("support1", "Support 1", "support", "#4caf50", "dot"),
        ("support2", "Support 2", "support", "#81c784", "dot"),
        ("eject",    "Eject",     "eject",   "#ff9800", "dash"),
        ("target",   "Target",    "target",  "#64b5f6", "dashdot"),
    ]
    for param, label, ktype, color, dash in level_defs:
        val = request.args.get(param, "").strip()
        if val:
            try:
                key_levels.append({"price": float(val), "label": label, "type": ktype, "color": color, "dash": dash})
            except ValueError:
                pass

    custom_exp = request.args.get("exp", "").strip() or None

    # Derive a readable label for custom expiration
    custom_exp_label = None
    if custom_exp:
        try:
            from datetime import date as _date
            d = _date.fromisoformat(custom_exp)
            custom_exp_label = d.strftime("%b %d")  # e.g. "Dec 24"
        except Exception:
            custom_exp_label = custom_exp

    try:
        targets = get_target_expirations(custom_date=custom_exp)
        current_price, chains = fetch_yfinance(ticker, targets)

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            tmp_path = f.name

        build_html(ticker, current_price, chains, tmp_path,
                   key_levels=key_levels or None,
                   custom_exp_label=custom_exp_label)

        with open(tmp_path, "r") as f:
            html_content = f.read()

        os.unlink(tmp_path)
        return Response(html_content, mimetype="text/html")

    except SystemExit:
        return render_template_string(INDEX_HTML, error=f"No options data found for '{ticker}'. Check the ticker and try again.")
    except Exception as e:
        return render_template_string(INDEX_HTML, error=f"Error fetching data for '{ticker}': {str(e)}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
