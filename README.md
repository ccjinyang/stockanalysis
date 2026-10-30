# Wheelhouse

A local personal options research workspace for a watchlist-based wheel strategy.

## Stock charts with volume

A separate, standard-library Python service generates interactive charts for a stock ticker:

```sh
python3 chart_service.py --ticker AMZN --port 8766
```

Open **http://127.0.0.1:8766/**. No package installation or frontend build is required for this service (Python 3.9+, internet access, and a modern browser). It runs until stopped with Ctrl-C and can coexist with the options workspace on port 8765. To run it detached on your computer:

```sh
nohup python3 -u chart_service.py --ticker AMZN --port 8766 > /tmp/volume-atlas.log 2>&1 &
```

This detached command survives closing the terminal, but does not automatically start after a reboot. Run the foreground command under your preferred process manager for unattended hosting. The service binds to loopback for personal use.

- Enter a ticker, including exchange suffixes such as `SHOP.TO` or symbols such as `BRK-B`, then choose 3 months through 10 years of daily history. Bookmark ticker-specific views, e.g. `http://127.0.0.1:8766/?ticker=AMZN&range=5y`.
- Daily OHLC candles appear above daily share-volume bars. Hover for OHLCV, scroll or use +/− to zoom, drag or use arrow keys to pan, and double-click or press Home to reset. Linear/log price scales and PNG downloads are included. Recent bars also appear in an accessible table.
- The **Candles** dropdown switches immediately between daily, weekly (Monday-start weeks), and monthly candles. Weekly/monthly bars use the first open, highest high, lowest low, last close, and summed daily volume. Boundary periods may be partial. The profile continues to use underlying daily bars in the visible date range. The selected interval is preserved in the URL and PNG export. Hover shows an OHLCV tooltip and the cursor price on the right axis, including in logarithmic mode.
- The left-hand volume profile recalculates for the **visible date range**. Each day's volume is distributed uniformly across its low–high range, allocated to price bins by overlap. Flat days allocate all volume to one bin. The gold point-of-control line marks the center of the largest estimated bin. This conserves volume but **is not exact volume-at-price**; exact profiles require intraday/trade-level data. Candle colors reflect close versus open, not buy/sell aggressor flow.
- Data comes from Yahoo Finance's public chart endpoint without an API key. It may be delayed, unavailable, or rate-limited. This endpoint is unofficial and can change; it is intended here for personal research. Use a licensed provider before deploying a commercial/public market-data service. The provider adapter is `fetch_history()` in `chart_service.py`.
- Prices use provider split-adjusted OHLC without dividend adjustment. The latest daily bar may be incomplete. The page shows the last bar's exchange-local date and retrieval timestamp. No fabricated prices or overnight quotes are added. Data is cached in memory for five minutes (up to 32 ticker/range combinations); optional refresh runs every five minutes while the page is visible. A failed refresh retains the old chart with an explicit error.
- HTTP API: `GET /api/chart?ticker=AMZN&range=5y` returns daily bars, metadata, source, and retrieval time. `GET /api/health` checks the process, not upstream data availability. Invalid inputs return 400; upstream failures return 502.

Chart checks:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_chart_service.py' -v
node tests/test_chart_math.js
node --check chart_web/chart.js
```

## Start

Python 3.9+ and a browser are sufficient for synthetic examples. No frontend build is needed.

```sh
cd /Users/yangjin/YangDevelop/investment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python server.py
```

Open **http://127.0.0.1:8765/** and select **Run example scan**. All example contracts, prices, Greeks, expirations and liquidity are fictional. Example expirations may not be listed trading dates. Do not use examples for trading.

The server binds only to loopback. Stop with Ctrl-C. No account credentials are requested or stored. No orders are submitted by this project.

## What is included

- Editable initial watchlist: QQQ, AAPL, MSFT, AMZN, GOOGL, META, NVDA, TSLA, SOXX, AVGO.
- Put and covered-call screens, five delta tiers, and expiration ranges through three calendar months.
- Configurable quote eligibility, estimated fees, earnings policy, and deterministic ranking.
- Up to four contracts compared side by side, with source and timestamps retained.
- Manual share holdings, reserved shares and gross put cash commitments. No automatic account-position synchronization.
- Manual next earnings and ex-dividend dates. Unknown or past earnings dates are not interpreted as event clearance.
- Three browser-local scan snapshots. These store shortlist winners, not the full chain, and are not backtests.
- Six tutorial chapters, context explanations, and an interactive expiration payoff lab.

Watchlists, holdings, manual events, preferences and scan history are saved in localStorage in the current browser profile. They are not shared with a cloud service. Do not clear browser site data if you want to retain them. Scans and comparison selections remain in memory while the page is open. Saved history can be reopened after a refresh.

## IBKR paper setup

1. Create/activate an IBKR paper account and sign in to **paper Trader Workstation** or **paper IB Gateway** yourself.
2. In TWS API settings, enable **ActiveX and Socket Clients** / socket API and **Read-Only API**. Use paper port **7497** for TWS or **4002** for IB Gateway. Allow connections from localhost. Client ID 71 must be free.
3. Run this website using `.venv/bin/python server.py` so the installed `ibapi` package is available.
4. Open **IBKR connection**, select the application, then choose **Connect & scan paper account**.
5. Confirm appropriate underlying and options market-data subscriptions/API entitlements in IBKR. Paper access alone does not guarantee live data. The reader requests live data and excludes delayed, frozen, missing or stale quotes.

The adapter verifies all reported account identifiers start with `DU` and disconnects otherwise. Only paper default ports are supported. Account identifiers are used in memory for that check, not returned to the UI or persisted. The app requests market data and historical bars, not holdings or order execution. Enable TWS Read-Only API as a further configuration measure.

A scan opens a temporary connection and closes it when finished. Results are timestamped captured quotes, **not continuously streaming prices**. During closed markets, expect no qualifying live results. Quotes must be valid, live and at most 90 seconds old at collection. Older entries in a completed scan remain historical snapshots.

### Coverage and limitations

For each underlying, the adapter resolves a standard SMART chain and selects up to three listed expirations closest to **21, 45 and 75 days**, within your range and no later than three calendar months from the New York exchange date. Per expiration and option side, it selects up to six OTM strikes nearest **1%, 3%, 5%, 8%, 12% and 18%** from spot. This is a representative scan, **not a full-chain optimizer**. Some risk-tier/window cells may be empty.

The initial adapter uses the pinned PyPI `ibapi` SDK for a reproducible environment. That distribution is older than IBKR's current SDK downloads. Compatibility with the user's installed TWS/Gateway must be checked in a real session; if an API version error occurs, install the matching official SDK from IBKR and repeat the integration test. The `error` and Greeks callbacks accept the known signature variants. This implementation has not yet been validated against an authenticated TWS/Gateway session.

The paper adapter requests options open interest and volume and daily underlying bars. Realized volatility is the annualized sample standard deviation of up to 30 daily log returns (at least 20 required). Trend is spot relative to a 50-close moving average. These are context inputs; neither is a validated trading edge. No fundamental stock-quality assessment is made.

Earnings and ex-dividend schedules are **manual** in this version. Dates must be maintained after each event. Unknown dates remain visible. Dividend flags are not a complete early-exercise model, and ETF constituent earnings are not assessed. IBKR fees vary: the default $0.65 per contract is only an editable opening-fee estimate, not an account-specific commission quote.

## Ranking

Eligibility: positive two-sided quotes, out of the money, standard multiplier 100, absolute delta `[0.05, 0.45)`, expiration within settings, OI ≥ 100 and spread/midpoint ≤ 20% by default. Net opening premium must be positive. Limits are configurable in Scan settings.

Contracts are grouped by **symbol × put/call × delta tier × expiration band**. Only the top contract per group is shortlisted. Scores are not directly comparable between groups.

Delta tiers: `[.05,.10)`, `[.10,.15)`, `[.15,.25)`, `[.25,.35)`, `[.35,.45)`. Expiration bands: 14–30, 31–60, and 61 days through three calendar months by default.

```
capital = strike * 100                       # puts
capital = current stock price * 100          # calls
net premium = bid * 100 - estimated opening fee
annualized income % = net premium / capital * 365 / DTE * 100
income metric = (net premium / capital * 100) / (DTE / 30)^0.75

income points = 55 * income metric / best income metric in group
spread points = 15 * max(0, 1 - spread / configured spread limit)
OI points = 10 * min(OI / 1000, 1)
VRP points = 10 * clamp(0.5 + (IV - RV) / 0.4, 0, 1)
trend points = 10 * clamp(0.5 + trend / 0.2, 0, 1)
score = sum(points) * earnings multiplier
```

IV and RV are decimals. Missing RV or trend gets neutral 5 points, disclosed in contract details. Earnings inside the contract window multiplies by .60; unknown next earnings multiplies by .90; a manual future earnings date after expiry uses 1.00. Exclude-events mode removes inside-window and unknown dates. Dividend dates flag context but do not alter scores. Ties break on spread, OI, expiration and strike.

These are initial transparent heuristics inspired by PutFinder's general approach, not its unpublished model. The score is not a probability or expected return. Annualized premium excludes stock P/L, closing costs, taxes and dividends. Stock purchase basis in the planning ledger is not reduced by premiums. Covered-call P/L if called away uses 100 shares at the entered actual purchase basis plus net opening premium. It excludes stock transaction costs, prior premiums, taxes, dividends and early assignment.

## Verification

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check dist/app.js
```

Engine checks cover net cash/yield, call denominators, quote freshness/types, liquidity, nonstandard contracts, calendar boundaries, earnings, missing-factor handling, and deterministic grouping.

Browser verification covers example scanning, expiration filters, contract comparison, tutorial navigation and put/call payoff scenarios. Live end-to-end verification requires an authenticated paper session and appropriate market-data subscriptions.

## Primary references

- [IBKR option chains](https://www.interactivebrokers.com/docs/tws-api/doc/contracts/option-chains)
- [IBKR quotes and Greeks](https://www.interactivebrokers.com/docs/tws-api/doc/md/option-greeks)
- [OIC cash-secured puts](https://www.optionseducation.org/strategies/all-strategies/cash-secured-put)
- [OIC covered calls](https://www.optionseducation.org/strategies/all-strategies/covered-call-buy-write)
- [OIC assignment](https://www.optionseducation.org/referencelibrary/faq/options-assignment)
