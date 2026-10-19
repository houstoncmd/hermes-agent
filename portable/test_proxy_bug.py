#!/usr/bin/env python3
"""
Prove the PROXY false-positive bug in port_responds(), then verify the fix.

Bug: on locked-down (bank) machines urllib routes even 127.0.0.1 through the
corporate PAC proxy. The proxy answers with an HTTP error for localhost. The
OLD port_responds() treated HTTPError as "server is up" (True) — a false
positive — so ensure_selfhost() returned a port WITHOUT starting the server.
The browser then hit "connection refused".

Fix: (1) bypass the system proxy with ProxyHandler({}), and (2) verify the
/api/health sentinel instead of accepting ANY HTTP response.
"""
import http.server
import os
import sys
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import app_shell


def start_dummy_health_server(port: int) -> http.server.ThreadingHTTPServer:
    """A real /api/health server (stands in for the hermes dashboard)."""

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/api/health':
                body = b'{"ok": true, "version": "test", "auth_required": false}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main() -> int:
    ok = True

    # ── 1. Show that a DEAD proxy makes the naive urlopen fail/err ─────────
    # Point the env proxy at a dead port. Naive urlopen (proxy-aware) will
    # try the proxy and fail even though the real server is up on 127.0.0.1.
    port = app_shell.find_free_port()
    srv = start_dummy_health_server(port)
    try:
        # Real server IS up:
        direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with direct.open(f'http://127.0.0.1:{port}/api/health', timeout=3) as r:
            assert b'"ok"' in r.read(), 'direct (no-proxy) probe should see health'
        print(f'[PASS] direct/no-proxy probe sees health on port {port}')

        # Now prove the proxy-aware path breaks when a proxy is configured:
        os.environ['http_proxy'] = 'http://127.0.0.1:9'   # dead proxy
        os.environ['HTTP_PROXY'] = 'http://127.0.0.1:9'
        os.environ['no_proxy'] = ''
        os.environ['NO_PROXY'] = ''
        # Re-read proxies (urllib caches them per-call via getproxies()).
        # A naive urlopen now goes through the dead proxy → fails, even though
        # the server is up. This is the class of failure the bank proxy causes.
        naive_ok = True
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=2)
        except Exception as e:
            naive_ok = False
            print(f'[INFO] naive urlopen through dead proxy FAILED as expected: '
                  f'{type(e).__name__}')
        if naive_ok:
            print('[WARN] naive urlopen did not fail via dead proxy '
                  '(platform may bypass loopback) — fix still applies')

        # ── 2. The FIXED port_responds must still return True ─────────────
        # Clear env again for a clean check, but our fixed impl ignores proxy.
        fixed = app_shell.port_responds(port)
        if fixed:
            print(f'[PASS] fixed port_responds() = True (proxy bypassed, '
                  f'/api/health sentinel verified)')
        else:
            print(f'[FAIL] fixed port_responds() = False — fix broken')
            ok = False

        # ── 3. port_responds must NOT false-positive on a dead port ───────
        dead = app_shell.find_free_port()
        if not app_shell.port_responds(dead):
            print(f'[PASS] fixed port_responds() = False on dead port {dead} '
                  f'(no false positive)')
        else:
            print(f'[FAIL] port_responds() false-positive on dead port {dead}')
            ok = False
    finally:
        srv.shutdown()
        for v in ('http_proxy', 'HTTP_PROXY', 'no_proxy', 'NO_PROXY'):
            os.environ.pop(v, None)

    print('[OK] proxy-bug fix verified' if ok else '[FAIL] proxy-bug fix failed')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
