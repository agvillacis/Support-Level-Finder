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

# Reuse logic from analyze.py
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
         justify-content: center; min-height: 100vh; }
  .card { background: #111; border: 1px solid #222; border-radius: 12px;
          padding: 40px 48px; max-width: 480px; width: 100%; text-align: center; }
  h1 { font-size: 1.6rem; color: #fff; margin-bottom: 8px; }
  p { color: #888; margin-bottom: 28px; font-size: 0.95rem; line-height: 1.5; }
  .row { display: flex; gap: 10px; }
  input { flex: 1; background: #1a1a1a; border: 1px solid #333; color: #fff;
          padding: 12px 16px; border-radius: 8px; font-size: 1rem;
          text-transform: uppercase; letter-spacing: 0.05em; outline: none; }
  input:focus { border-color: #555; }
  button { background: #2563eb; color: #fff; border: none; padding: 12px 24px;
           border-radius: 8px; font-size: 1rem; cursor: pointer; font-weight: 600;
           transition: background 0.15s; }
  button:hover { background: #1d4ed8; }
  button:disabled { background: #333; cursor: not-allowed; }
  .examples { margin-top: 20px; color: #555; font-size: 0.8rem; }
  .examples a { color: #3b82f6; text-decoration: none; margin: 0 6px; }
  .examples a:hover { color: #60a5fa; }
  .error { color: #ef5350; margin-top: 16px; font-size: 0.9rem; }
</style>
</head>
<body>
<div class="card">
  <h1>📊 Support Level Finder</h1>
  <p>Enter a ticker to generate a put/call open interest chart showing support &amp; resistance levels for 3 expirations.</p>
  <form method="GET" action="/analyze">
    <div class="row">
      <input type="text" name="ticker" placeholder="NVDA, AAPL, SPY…" required autofocus>
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

    try:
        targets = get_target_expirations()
        current_price, chains = fetch_yfinance(ticker, targets)

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            tmp_path = f.name

        build_html(ticker, current_price, chains, tmp_path)

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
