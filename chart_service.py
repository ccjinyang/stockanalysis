"""Stock chart web service. Python 3.9+, standard library only.

Run: python3 chart_service.py --ticker AMZN --port 8766
"""
import argparse
from collections import OrderedDict
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parent / 'chart_web'
RANGES = ('3mo', '6mo', '1y', '2y', '5y', '10y')
CACHE = OrderedDict()
CACHE_LOCK = threading.Lock()
CACHE_SECONDS = 300


class DataUnavailable(Exception):
    pass


def validate(symbol, period):
    symbol = symbol.strip().upper()
    if not re.fullmatch(r'[A-Z0-9^][A-Z0-9.^=\-]{0,19}', symbol):
        raise ValueError('Enter a ticker such as AMZN, BRK-B, or SHOP.TO (up to 20 characters).')
    if period not in RANGES:
        raise ValueError('Choose a supported history range.')
    return symbol


def normalize(payload, symbol):
    """Drop incomplete/invalid bars; retain exchange-local trading dates."""
    chart = payload.get('chart', {})
    if chart.get('error') or not chart.get('result'):
        raise DataUnavailable('No history found. Check the ticker and exchange suffix.')
    result = chart['result'][0]
    meta = result.get('meta', {})
    try:
        tz = ZoneInfo(meta.get('exchangeTimezoneName', 'UTC'))
    except (ZoneInfoNotFoundError, ValueError):
        tz = timezone.utc
    quotes = result.get('indicators', {}).get('quote', [])
    if not quotes:
        raise DataUnavailable('The provider returned no price bars.')
    series = quotes[0]
    by_date = {}
    for i, timestamp in enumerate(result.get('timestamp', [])):
        try:
            values = [series[key][i] for key in ('open', 'high', 'low', 'close', 'volume')]
            if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in values):
                continue
            o, h, l, c, v = values
            if min(o, h, l, c) <= 0 or v < 0 or l > min(o, c) or h < max(o, c) or l > h:
                continue
            date = datetime.fromtimestamp(timestamp, tz).date().isoformat()
            by_date[date] = dict(date=date, open=o, high=h, low=l, close=c, volume=int(v))
        except (KeyError, IndexError, TypeError, ValueError, OverflowError, OSError):
            continue
    bars = [by_date[d] for d in sorted(by_date)]
    if len(bars) < 2:
        raise DataUnavailable('Not enough valid daily bars to draw this chart.')
    return dict(symbol=symbol, name=meta.get('longName') or meta.get('shortName') or symbol,
                currency=meta.get('currency', ''), exchange=meta.get('exchangeName', ''),
                timezone=meta.get('exchangeTimezoneName', 'UTC'), bars=bars,
                source='Yahoo Finance · daily OHLCV',
                fetchedAt=datetime.now(timezone.utc).isoformat(),
                priceBasis='Provider OHLC, split-adjusted; not dividend-adjusted. Latest daily bar may be incomplete.')


def fetch_history(symbol, period):
    key = (symbol, period)
    # A single flight prevents parallel tabs from hammering the free provider.
    with CACHE_LOCK:
        cached = CACHE.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            CACHE.move_to_end(key)
            return dict(cached[1], cached=True)
        query = urlencode(dict(range=period, interval='1d', includePrePost='false'))
        last_error = None
        for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
            request = Request(f'https://{host}/v8/finance/chart/{quote(symbol, safe="")}?{query}',
                              headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
            try:
                with urlopen(request, timeout=15) as response:
                    payload = json.load(response)
                data = normalize(payload, symbol)
                CACHE[key] = (time.monotonic(), data)
                CACHE.move_to_end(key)
                while len(CACHE) > 32:
                    CACHE.popitem(last=False)
                return dict(data, cached=False)
            except HTTPError as exc:
                if exc.code == 404:
                    raise DataUnavailable('Ticker not found. Check the symbol and exchange suffix.') from exc
                last_error = f'provider HTTP {exc.code}'
            except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as exc:
                last_error = type(exc).__name__
        raise DataUnavailable(f'Cannot retrieve market data ({last_error}). Check internet access or retry later.')


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def respond(self, code, data):
        payload = json.dumps(data, allow_nan=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        port = self.server.server_address[1]
        if self.headers.get('Host') not in (f'127.0.0.1:{port}', f'localhost:{port}'):
            return self.respond(403, {'error': 'Local access only.'})
        path = urlsplit(self.path)
        if path.path == '/api/health':
            return self.respond(200, {'status': 'ok', 'defaultTicker': self.server.default_ticker})
        if path.path == '/api/chart':
            params = parse_qs(path.query, keep_blank_values=True)
            try:
                period = params.get('range', ['5y'])[0]
                symbol = validate(params.get('ticker', [self.server.default_ticker])[0], period)
                return self.respond(200, fetch_history(symbol, period))
            except ValueError as exc:
                return self.respond(400, {'error': str(exc)})
            except DataUnavailable as exc:
                return self.respond(502, {'error': str(exc)})
        if path.path not in ('/', '/index.html', '/chart.js', '/math.js', '/styles.css'):
            return self.respond(404, {'error': 'Not found.'})
        return super().do_GET()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--ticker', default='AMZN')
    args = parser.parse_args()
    try:
        symbol = validate(args.ticker, '5y')
        if not 1 <= args.port <= 65535:
            raise ValueError('Port must be between 1 and 65535.')
    except ValueError as exc:
        parser.error(str(exc))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.default_ticker = symbol
    print(f'Volume Atlas → http://127.0.0.1:{args.port}/ · default {symbol}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
