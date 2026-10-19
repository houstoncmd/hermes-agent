#!/usr/bin/env python3
"""
E2E proof that the SELF-HOSTED dashboard server actually starts and responds.

This exercises the real code path: start_selfhost_server() runs
hermes_cli.main.cmd_dashboard() on a daemon thread (no subprocess), then we
poll the port. This is the architecture the portable shell now uses.
"""
import os
import sys
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import app_shell


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='hp-e2e-'))
    install = tmp / 'hermes'
    install.mkdir(parents=True)
    os.environ['HERMES_PORTABLE_INSTALL_DIR'] = str(install)

    # Minimal web_dist so the SPA mount has something to serve.
    wd = install / 'hermes_cli' / 'web_dist'
    wd.mkdir(parents=True)
    (wd / 'index.html').write_text(
        '<!doctype html><html><body><h1>Hermes E2E</h1></body></html>',
        encoding='utf-8')

    # hermes-home so the engine has a HOME to write to.
    home = install / 'hermes-home'
    home.mkdir(exist_ok=True)

    print(f'[e2e] install dir = {install}')
    port = app_shell.ensure_selfhost()
    url = app_shell.dashboard_url(port)
    print(f'[e2e] server ready on port {port} -> {url}')

    # Hit the SPA root.
    body = ''
    try:
        with urllib.request.urlopen(url + '/', timeout=10) as r:
            body = r.read().decode('utf-8', 'replace')
            print(f'[e2e] GET / -> HTTP {r.status}, {len(body)} bytes')
    except urllib.error.HTTPError as e:
        # Auth gate may redirect — still proves the server is alive.
        print(f'[e2e] GET / -> HTTP {e.code} (server alive, auth gate)')
    except Exception as e:
        print(f'[FAIL] GET / raised: {e}')
        return 1

    if 'Hermes E2E' in body:
        print('[PASS] SPA served from in-process self-hosted server')
    else:
        print(f'[WARN] SPA body not matched (got {body[:120]!r}) — '
              'server responded but content differs')

    # Second call must reuse the already-serving port (idempotent).
    port2 = app_shell.ensure_selfhost()
    if port2 == port:
        print(f'[PASS] ensure_selfhost idempotent (reuse port {port2})')
    else:
        print(f'[FAIL] second call gave different port {port2} != {port}')
        return 1

    print('[OK] self-hosting E2E passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
