# Support Level Finder

Analyzes options chains to identify put/call open interest walls — the strike prices where large numbers of contracts are sitting, which act as support (put walls) and resistance (call walls).

Generates a visual HTML report in seconds. Replaces hours of manual sorting.

## Usage

```bash
# Analyze SPY using free Yahoo Finance data (no account needed)
python3 analyze.py SPY

# Analyze AAPL
python3 analyze.py AAPL

# Use Schwab API instead (see setup below)
python3 analyze.py AAPL --source schwab
```

Output: an HTML file (`AAPL_support_levels.html`) that opens automatically in your browser showing:
- Bar chart of put/call OI at every strike
- Tabs for: This Week / Month End / Year End expirations
- Top 5 support levels (highest put OI below current price)
- Top 5 resistance levels (highest call OI above current price)

## Install

```bash
pip3 install yfinance plotly
```

## Schwab API Setup (optional — for real-time data)

The free Yahoo Finance source (yfinance) works without any account. If you want real-time Schwab data:

1. Go to https://developer.schwab.com and sign in with your Schwab brokerage account
2. Create a new app → you'll get a **Client ID** and **Client Secret**
3. Set the redirect URI to `https://127.0.0.1`
4. Create `schwab_config.json` in this folder:

```json
{
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET",
  "redirect_uri": "https://127.0.0.1"
}
```

5. Run `python3 schwab_auth.py` once to complete OAuth login (opens browser)
6. After that, `python3 analyze.py AAPL --source schwab` works

## How to Read the Output

- **Green bars = Put OI** → where bearish bets are concentrated → acts as *support* (stock tends to bounce off these)
- **Red bars = Call OI** → where bullish bets are concentrated → acts as *resistance* (stock tends to stall here)
- **White dotted line** = current stock price
- **Bigger bar = stronger level**

The theory: market makers who sold these options hedge by buying/selling the underlying stock near these strikes, which creates price gravity at high-OI levels.
