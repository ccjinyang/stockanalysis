"""Loopback-only local server; python3 server.py. All scans are read-only."""
import datetime as dt
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import uuid

import engine
import ibkr

ROOT = Path(__file__).parent / 'dist'
JOBS = {}
LOCK = threading.Lock()


def run_scan(job, body):
    try:
        config = engine.settings(body)
        source = body.get('source', 'example')
        if source not in ('example', 'paper'): raise ValueError('Choose example or paper data.')
        warnings = []
        def progress(message): job['message'] = message
        if source == 'paper':
            raw, warnings = ibkr.collect(config, int(body.get('port', 7497)), progress)
        else:
            raw = engine.examples(config)
        result = engine.screen(raw, config, source)
        job.update(state='done', message='Scan complete', result=dict(result, source=source, warnings=warnings,
                   scannedAt=dt.datetime.now(dt.timezone.utc).isoformat(),
                   coverage='Representative scan: up to 3 expirations nearest 21, 45, and 75 days; up to 6 OTM strikes per side per expiration.' if source == 'paper' else
                   'Synthetic examples only. Prices, Greeks, dates and liquidity are fictional; not valid trades.',
                   rules={'minOi': config['min_oi'], 'maxSpread': config['max_spread'] * 100,
                          'fee': config['fee'], 'minDte': config['min_dte'], 'maxDte': config['max_dte']}))
    except Exception as exc:
        job.update(state='error', message=str(exc))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(ROOT), **kwargs)

    def allowed(self):
        return self.headers.get('Host') in ('127.0.0.1:8765', 'localhost:8765')

    def respond(self, status, data):
        payload = json.dumps(data, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def do_GET(self):
        if not self.allowed(): return self.respond(403, {'error': 'Local access only.'})
        if self.path == '/api/status':
            return self.respond(200, {'sdkInstalled': ibkr.available(), 'mode': 'paper-only', 'connected': False})
        if self.path.startswith('/api/jobs/'):
            job = JOBS.get(self.path.split('/')[-1])
            return self.respond(200 if job else 404, job or {'error': 'Scan not found.'})
        return super().do_GET()

    def do_POST(self):
        if not self.allowed() or self.headers.get('Origin') not in ('http://127.0.0.1:8765', 'http://localhost:8765'):
            return self.respond(403, {'error': 'Local same-origin requests only.'})
        if self.path != '/api/scan': return self.respond(404, {'error': 'Unknown endpoint.'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.respond(415, {'error': 'Expected application/json.'})
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 100000: raise ValueError('Request is too large or empty.')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict): raise ValueError('Expected a JSON object.')
            engine.settings(body)
            if body.get('source', 'example') not in ('example', 'paper'): raise ValueError('Invalid source.')
            if body.get('source') == 'paper' and int(body.get('port', 7497)) not in (7497, 4002): raise ValueError('Paper ports only: 7497 or 4002.')
        except (ValueError, TypeError, AttributeError) as exc:
            return self.respond(400, {'error': str(exc)})
        with LOCK:
            if any(j['state'] == 'running' for j in JOBS.values()):
                return self.respond(409, {'error': 'A scan is already running. Wait for it to finish.'})
            if len(JOBS) > 20: JOBS.pop(next(iter(JOBS)))
            ident = uuid.uuid4().hex
            job = {'state': 'running', 'message': 'Preparing scan…'}
            JOBS[ident] = job
        threading.Thread(target=run_scan, args=(job, body), daemon=True).start()
        return self.respond(202, {'id': ident})


if __name__ == '__main__':
    print('Wheelhouse → http://127.0.0.1:8765', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
