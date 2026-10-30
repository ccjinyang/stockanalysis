"""Deterministic, inspectable screening rules; no execution functionality."""
import calendar
import datetime as dt
import math
import random

WATCHLIST = ['QQQ', 'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'NVDA', 'TSLA', 'SOXX', 'AVGO']
TIERS = [(0.05, 0.10, 'Very conservative'), (0.10, 0.15, 'Conservative'),
         (0.15, 0.25, 'Balanced'), (0.25, 0.35, 'Aggressive'), (0.35, 0.45, 'Very aggressive')]


def three_months(today):
    month = today.month + 3
    year = today.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return dt.date(year, month, min(today.day, calendar.monthrange(year, month)[1]))


def bucket(days):
    return '14–30 days' if days <= 30 else '31–60 days' if days <= 60 else '61 days–3 months'


def settings(data):
    symbols = list(dict.fromkeys(str(s).strip().upper() for s in data.get('symbols', WATCHLIST)))
    if not symbols or len(symbols) > 25 or any(not s.replace('.', '').isalpha() or len(s) > 8 for s in symbols):
        raise ValueError('Choose 1–25 valid US ticker symbols (up to 8 letters, with optional dots).')
    # Exchange dates use America/New_York, including daylight saving time.
    from zoneinfo import ZoneInfo
    today = dt.datetime.now(ZoneInfo('America/New_York')).date()
    maximum = (three_months(today) - today).days
    out = {'symbols': symbols, 'today': today, 'min_dte': int(data.get('minDte', 14)),
           'max_dte': min(int(data.get('maxDte', maximum)), maximum),
           'fee': float(data.get('fee', 0.65)), 'min_oi': int(data.get('minOi', 100)),
           'max_spread': float(data.get('maxSpread', 20)) / 100,
           'events': data.get('events', {}), 'exclude_events': bool(data.get('excludeEvents', False))}
    if not 14 <= out['min_dte'] <= out['max_dte'] or not 0 <= out['fee'] <= 100 or not 0 <= out['min_oi'] <= 1000000 or not 0 < out['max_spread'] <= 1:
        raise ValueError('Check expiration, fee, open interest, and spread limits.')
    if not isinstance(out['events'], dict): raise ValueError('Invalid event calendar.')
    normalized = {}
    for symbol, dates in out['events'].items():
        if not isinstance(dates, dict): raise ValueError('Invalid event dates.')
        normalized[symbol] = {}
        for key in ('earnings', 'dividend'):
            value = dates.get(key)
            if value:
                event_date = dt.date.fromisoformat(value)
                # A past manual date is stale, not proof of no upcoming event.
                if event_date >= today: normalized[symbol][key] = value
    out['events'] = normalized
    return out


def screen(raw, config, source):
    rows, rejected = [], {}
    def reject(reason):
        rejected[reason] = rejected.get(reason, 0) + 1
    for q in raw:
        try:
            spot, strike, bid, ask = (float(q[k]) for k in ('spot', 'strike', 'bid', 'ask'))
            delta, oi = abs(float(q['delta'])), int(q.get('oi', 0))
            days = (dt.date.fromisoformat(q['expiry']) - config['today']).days
            if not all(math.isfinite(x) for x in (spot, strike, bid, ask, delta)) or min(spot, strike, bid) <= 0 or ask < bid:
                reject('Invalid or missing quote'); continue
            if q.get('multiplier', 100) != 100:
                reject('Nonstandard contract'); continue
            if source == 'paper' and (q.get('dataType') != 1 or q.get('age', 9999) > 90):
                reject('Quote is not fresh live data'); continue
            if not config['min_dte'] <= days <= config['max_dte']:
                reject('Outside expiration range'); continue
            if oi < config['min_oi']:
                reject('Open interest below minimum'); continue
            spread = (ask - bid) / ((ask + bid) / 2)
            if spread > config['max_spread']:
                reject('Spread too wide'); continue
            if (q['right'] == 'P' and strike >= spot) or (q['right'] == 'C' and strike <= spot):
                reject('Not out of the money'); continue
            tier = next((label for low, high, label in TIERS if low <= delta < high), None)
            if tier is None:
                reject('Delta outside 0.05–0.45'); continue
            events = config['events'].get(q['symbol'], {})
            event = events.get('earnings', '')
            ex_dividend = events.get('dividend', '')
            earnings_in = bool(event and config['today'] <= dt.date.fromisoformat(event) <= dt.date.fromisoformat(q['expiry']))
            dividend_in = bool(ex_dividend and config['today'] <= dt.date.fromisoformat(ex_dividend) <= dt.date.fromisoformat(q['expiry']))
            if config['exclude_events'] and (not event or earnings_in):
                reject('Earnings inside window or unknown'); continue
            net = bid * 100 - config['fee']
            if net <= 0:
                reject('Premium does not cover fee'); continue
            capital = strike * 100 if q['right'] == 'P' else spot * 100
            annual = net / capital * 365 / days * 100
            distance = abs(spot - strike) / spot * 100
            row = dict(q, delta=delta, oi=oi, dte=days, tier=tier, window=bucket(days), spread=spread * 100,
                       net=round(net, 2), capital=capital, annual=annual, distance=distance,
                       breakeven=strike - net / 100 if q['right'] == 'P' else None,
                       earnings=event or None, earningsIn=earnings_in, dividend=ex_dividend or None,
                       dividendIn=dividend_in, source=source)
            row['id'] = f"{q['symbol']}-{q['expiry']}-{strike:g}-{q['right']}"
            # Expiration-adjusted income is a heuristic, not an expected return.
            row['incomeMetric'] = (net / capital * 100) / (days / 30) ** 0.75
            rows.append(row)
        except (ValueError, KeyError, TypeError, OverflowError):
            reject('Incomplete contract data')
    groups = {}
    for row in rows:
        groups.setdefault((row['symbol'], row['right'], row['tier'], row['window']), []).append(row)
    for group in groups.values():
        max_income = max(r['incomeMetric'] for r in group)
        for r in group:
            income = 55 * r['incomeMetric'] / max_income
            liquidity = 15 * max(0, 1 - r['spread'] / (config['max_spread'] * 100))
            oi_score = 10 * min(r['oi'] / 1000, 1)
            iv, rv = r.get('iv'), r.get('rv')
            vrp = 10 * max(0, min(1, 0.5 + (iv - rv) / 0.4)) if iv is not None and rv is not None else 5
            trend = 10 * max(0, min(1, 0.5 + r['trend'] / 0.2)) if r.get('trend') is not None else 5
            multiplier = 0.6 if r['earningsIn'] else 0.9 if not r['earnings'] else 1
            r['factors'] = {'Income': round(income, 1), 'Spread': round(liquidity, 1),
                            'Open interest': round(oi_score, 1), 'IV vs realized': round(vrp, 1), 'Trend': round(trend, 1)}
            r['eventMultiplier'] = multiplier
            r['score'] = round((income + liquidity + oi_score + vrp + trend) * multiplier, 1)
            r['notes'] = ['Bid-based premium; midpoint shown for comparison only.',
                          'Earnings inside contract window: score ×0.60.' if r['earningsIn'] else
                          'Earnings date unknown: score ×0.90; no automatic event clearance.' if not r['earnings'] else
                          'No earnings inside window according to your manual date.',
                          'Dividend schedule unknown; early assignment has not been cleared.' if not r['dividend'] else
                          'Ex-dividend date inside window; review early assignment.' if r['dividendIn'] else
                          'Manual ex-dividend date is outside window.']
            if rv is None: r['notes'].append('Realized volatility unavailable: neutral factor used.')
            if r.get('trend') is None: r['notes'].append('Trend unavailable: neutral factor used.')
        group.sort(key=lambda r: (-r['score'], r['spread'], -r['oi'], r['expiry'], r['strike']))
        for n, r in enumerate(group): r['groupRank'] = n + 1
    return {'rows': sorted(rows, key=lambda r: (-r['score'], r['id'])), 'rejected': rejected,
            'rawCount': len(raw), 'eligibleCount': len(rows), 'groups': len(groups)}


def examples(config):
    """Synthetic fixtures for exploring the interface. These are NOT market prices."""
    prices = [500, 220, 430, 200, 180, 570, 140, 260, 230, 180]
    raw = []
    for n, symbol in enumerate(config['symbols']):
        rng = random.Random(symbol)
        spot = prices[WATCHLIST.index(symbol)] if symbol in WATCHLIST else 100
        iv = 0.24 + (n % 4) * 0.09
        for days in [14, 21, 28, 35, 45, 56, 63, 77, 89]:
            for right in ['P', 'C']:
                for d in [0.075, 0.125, 0.175, 0.225, 0.275, 0.325, 0.375, 0.425]:
                    distance = (0.48 - d) * iv * math.sqrt(days / 365) * 2.7
                    strike = round(spot * (1 - distance if right == 'P' else 1 + distance), 0)
                    bid = round(max(.05, spot * iv * math.sqrt(days / 365) * d * .68), 2)
                    raw.append({'symbol': symbol, 'spot': spot, 'strike': strike, 'right': right,
                                'bid': bid, 'ask': round(bid * (1.025 + rng.random() * .10) + .01, 2),
                                'expiry': (config['today'] + dt.timedelta(days=days)).isoformat(),
                                'delta': d, 'iv': iv, 'rv': iv - .03 - rng.random() * .04,
                                'oi': rng.randint(80, 3200), 'volume': rng.randint(0, 600),
                                'trend': .02 + rng.random() * .08, 'multiplier': 100,
                                'dataType': None, 'quoteAt': None})
    return raw
