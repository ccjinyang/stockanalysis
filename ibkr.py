"""On-demand IBKR paper market-data reader using the official Python SDK.

No order endpoints. Each scan closes its connection when complete.
"""
import datetime as dt
import importlib.util
import math
import statistics
import threading
import time


def available():
    return importlib.util.find_spec('ibapi') is not None


def collect(config, port, progress):
    if port not in (7497, 4002):
        raise ValueError('Use paper TWS port 7497 or paper IB Gateway port 4002.')
    if not available():
        raise RuntimeError('IBKR SDK is not installed. Follow the Connection page setup instructions, then restart the server.')
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract

    class Reader(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self.ready = threading.Event()
            self.accounts_ready = threading.Event()
            self.accounts = []
            self.results = {}
            self.ends = {}
            self.errors = []
            self.next_id = 1000

        def alloc(self, value=None):
            self.next_id += 1
            self.results[self.next_id] = value if value is not None else {}
            self.ends[self.next_id] = threading.Event()
            return self.next_id

        def nextValidId(self, orderId): self.ready.set()

        def managedAccounts(self, accountsList):
            self.accounts = [a for a in accountsList.split(',') if a]
            self.accounts_ready.set()

        def error(self, reqId, *args):
            # Official SDK releases differ in whether errorTime precedes code.
            code, message = (args[1], args[2]) if len(args) >= 3 and isinstance(args[1], int) else args[:2]
            if code not in (2104, 2106, 2158):
                self.errors.append({'code': code, 'message': str(message)[:250]})
            if reqId in self.ends and code in (200, 354, 10089, 10167, 10168):
                self.ends[reqId].set()

        def contractDetails(self, reqId, details): self.results[reqId] = details.contract
        def contractDetailsEnd(self, reqId): self.ends[reqId].set()

        def securityDefinitionOptionParameter(self, reqId, exchange, underlyingConId, tradingClass, multiplier, expirations, strikes):
            if exchange == 'SMART' and multiplier == '100':
                self.results[reqId].append({'class': tradingClass, 'expiries': sorted(expirations), 'strikes': sorted(strikes)})

        def securityDefinitionOptionParameterEnd(self, reqId): self.ends[reqId].set()

        def tickPrice(self, reqId, tickType, price, attrib):
            if reqId not in self.results or not isinstance(self.results[reqId], dict): return
            field = {1: 'bid', 2: 'ask', 4: 'last', 66: 'bid', 67: 'ask', 68: 'last'}.get(tickType)
            if tickType in (66, 67, 68): self.results[reqId]['dataType'] = 3
            if field and price > 0:
                self.results[reqId][field] = price
                self.results[reqId][field + 'At'] = time.time()

        def tickSize(self, reqId, tickType, size):
            if reqId not in self.results or not isinstance(self.results[reqId], dict): return
            field = {27: 'oi', 28: 'oi', 29: 'volume', 30: 'volume', 8: 'volume'}.get(tickType)
            if field: self.results[reqId][field] = int(size)

        def marketDataType(self, reqId, marketDataType):
            if reqId in self.results: self.results[reqId]['dataType'] = marketDataType

        def tickOptionComputation(self, reqId, tickType, *args):
            # tickAttrib was added in API 9.81; allow both callback signatures.
            vals = args[1:] if len(args) == 9 else args
            if len(vals) < 8 or reqId not in self.results: return
            iv, delta, _, _, _, _, _, under = vals[:8]
            q = self.results[reqId]
            if tickType in (80, 81, 82, 83): q['dataType'] = 3
            if iv is not None and 0 < iv < 10: q['iv'] = iv
            if delta is not None and abs(delta) <= 1: q['delta'] = delta
            if under is not None and 0 < under < 1000000:
                q['spot'] = under
                q['spotAt'] = time.time()

        def historicalData(self, reqId, bar): self.results[reqId].append(float(bar.close))
        def historicalDataEnd(self, reqId, start, end): self.ends[reqId].set()

    app, collected, warnings = Reader(), [], []
    try:
        progress('Connecting to IBKR paper…')
        app.connect('127.0.0.1', port, clientId=71)
        worker = threading.Thread(target=app.run, daemon=True)
        worker.start()
        if not app.ready.wait(8):
            raise RuntimeError('IBKR did not complete the API handshake. Check paper login, socket API, port, and client ID 71.')
        app.reqManagedAccts()
        if not app.accounts_ready.wait(5) or not app.accounts or not all(a.startswith('DU') for a in app.accounts):
            raise RuntimeError('Could not verify a paper account (DU prefix). Connection closed; this app only accepts paper sessions.')
        app.reqMarketDataType(1)
        for index, symbol in enumerate(config['symbols']):
            progress(f'Reading {symbol} · {index + 1}/{len(config["symbols"])}')
            stock = Contract()
            stock.symbol, stock.secType, stock.exchange, stock.currency = symbol, 'STK', 'SMART', 'USD'
            rid = app.alloc()
            app.reqContractDetails(rid, stock)
            app.ends[rid].wait(6)
            qualified = app.results[rid]
            if not isinstance(qualified, Contract):
                warnings.append(f'{symbol}: could not resolve underlying.'); continue
            uid = app.alloc({'dataType': 1})
            app.reqMktData(uid, qualified, '', False, False, [])
            hid = app.alloc([])
            app.reqHistoricalData(hid, qualified, '', '3 M', '1 day', 'TRADES', 1, 1, False, [])
            cid = app.alloc([])
            app.reqSecDefOptParams(cid, symbol, '', 'STK', qualified.conId)
            app.ends[cid].wait(8)
            end = time.time() + 5
            while time.time() < end and not app.results[uid].get('last') and not app.results[uid].get('bid'):
                time.sleep(.1)
            uq = app.results[uid]
            spot = ((uq['bid'] + uq['ask']) / 2) if uq.get('bid') and uq.get('ask') else uq.get('last')
            spot_at = min(uq.get('bidAt', time.time()), uq.get('askAt', time.time())) if uq.get('bid') and uq.get('ask') else uq.get('lastAt', 0)
            if not spot or uq.get('dataType') != 1 or time.time() - spot_at > 90:
                warnings.append(f'{symbol}: no fresh live underlying quote. Check market hours and subscriptions.')
                app.cancelMktData(uid); app.cancelHistoricalData(hid); continue
            chains = app.results[cid]
            chain = next((c for c in chains if c['class'] == symbol), chains[0] if chains else None)
            if not chain:
                warnings.append(f'{symbol}: no standard SMART option chain.')
                app.cancelMktData(uid); app.cancelHistoricalData(hid); continue
            dates = []
            for exp in chain['expiries']:
                d = dt.datetime.strptime(exp[:8], '%Y%m%d').date()
                days = (d - config['today']).days
                if config['min_dte'] <= days <= config['max_dte']: dates.append((exp, days))
            # Bounded representative scan, explicitly surfaced in the UI.
            chosen = list(dict.fromkeys(min(dates, key=lambda x: abs(x[1] - target))[0] for target in (21, 45, 75))) if dates else []
            if not chosen: warnings.append(f'{symbol}: no listed expirations within the selected range.')
            active = []
            for exp in chosen:
                for right in ('P', 'C'):
                    valid = [s for s in chain['strikes'] if (s < spot if right == 'P' else s > spot)]
                    if not valid: continue
                    strikes = sorted(set(min(valid, key=lambda s: abs(s - spot * (1 + (-1 if right == 'P' else 1) * pct))) for pct in (.01, .03, .05, .08, .12, .18)))
                    for strike in strikes:
                        option = Contract()
                        option.symbol, option.secType, option.exchange, option.currency = symbol, 'OPT', 'SMART', 'USD'
                        option.lastTradeDateOrContractMonth, option.strike, option.right = exp, strike, right
                        option.multiplier, option.tradingClass = '100', chain['class']
                        oid = app.alloc({'symbol': symbol, 'right': right, 'strike': strike,
                                         'expiry': dt.datetime.strptime(exp[:8], '%Y%m%d').date().isoformat(),
                                         'spot': spot, 'spotAt': spot_at, 'dataType': 1, 'multiplier': 100})
                        active.append(oid)
                        app.reqMktData(oid, option, '100,101', False, False, [])
                        time.sleep(.04)
            deadline = time.time() + 12
            while time.time() < deadline:
                if active and all(all(k in app.results[i] for k in ('bid', 'ask', 'delta', 'oi')) or app.ends[i].is_set() for i in active): break
                time.sleep(.2)
            app.ends[hid].wait(1)
            closes = list(app.results[hid])
            returns = [math.log(b / a) for a, b in zip(closes, closes[1:]) if min(a, b) > 0]
            rv = statistics.stdev(returns[-30:]) * math.sqrt(252) if len(returns) >= 20 else None
            trend = spot / statistics.mean(closes[-50:]) - 1 if len(closes) >= 50 else None
            for oid in active:
                app.cancelMktData(oid)
                q = dict(app.results[oid])
                q.update(rv=rv, trend=trend)
                quote_time = min(q.get('bidAt', 0), q.get('askAt', 0), q.get('spotAt', 0))
                q['age'] = time.time() - quote_time
                q['quoteAt'] = dt.datetime.fromtimestamp(quote_time, dt.timezone.utc).isoformat() if quote_time else None
                collected.append(q)
            app.cancelMktData(uid)
            app.cancelHistoricalData(hid)
        warnings.extend(f'IBKR {e["code"]}: {e["message"]}' for e in app.errors[-8:])
        return collected, list(dict.fromkeys(warnings))
    finally:
        app.disconnect()
