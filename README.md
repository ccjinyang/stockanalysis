# Stock Analysis — Volume Atlas

Interactive stock charts with daily, weekly, and monthly candles, daily volume, and an estimated volume profile.

## Run

A separate, standard-library Python service generates interactive charts for a stock ticker:

```sh
python3 chart_service.py --ticker AMZN --port 8766
```

Open **http://127.0.0.1:8766/**. No package installation or frontend build is required for this service (Python 3.9+, internet access, and a modern browser). It runs until stopped with Ctrl-C. To run it detached on your computer:

```sh
nohup python3 -u chart_service.py --ticker AMZN --port 8766 > /tmp/volume-atlas.log 2>&1 &
```

This detached command survives closing the terminal, but does not automatically start after a reboot. Run the foreground command under your preferred process manager for unattended hosting. The service binds to loopback for personal use.

- Enter a ticker and press **Enter**, including exchange suffixes such as `SHOP.TO` or symbols such as `BRK-B`. Changing the History or Candles dropdown automatically updates the chart. Choose 3 months through 10 years of daily history. Bookmark ticker-specific views, e.g. `http://127.0.0.1:8766/?ticker=AMZN&range=5y`.
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

## Historical forward P/E

The additional valuation panel loads automatically with the ticker and history range, follows price-chart zoom/pan, and offers hover details and keyboard inspection (focus the panel and use Left/Right). Its units are earnings multiples (`×`); the latest value shows its observation date. The separate forward P/E request does not block the price chart.

Source: Yahoo Finance's historical valuation endpoint, using **monthlyForwardPeRatio** supplemented by **quarterlyForwardPeRatio**. Monthly values take precedence on overlapping dates. The chart draws reported observations and dotted connectors, without creating daily values or extending a value beyond its observation date. It never substitutes trailing P/E or divides old prices by today's earnings estimate. Nonpositive or missing ratios are omitted. Coverage may be shorter than the requested history, and ETFs such as SOXX may not have this series. Empty coverage and connection errors are displayed separately; errors offer a retry button.

The provider can revise historical values, so this is **not a point-in-time backtest dataset**. The provider's forward earnings basis is retained without relabeling it as next-twelve-month or next-fiscal-year earnings. No paid API or extra dependency is required.

`GET /api/forward-pe?ticker=AMZN&range=5y` returns dated observations, frequency, source, retrieval time, and coverage status. Results are cached separately for one hour (32 ticker/range combinations). Endpoint failures return 502, while a successful response with no observations returns 200 and `status: "unavailable"`.

