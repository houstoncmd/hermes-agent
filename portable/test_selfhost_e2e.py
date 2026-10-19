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

# Prepend the REPO ROOT (not just portable/) so `import hermes_cli` resolves to
# THIS repo's engine, not a globally-installed hermes. Without this the test
# silently imports ~/.hermes/hermes-agent (a different version, possibly with
# its own production dashboard already bound on 9119) and becomes flaky.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, str(Path(__file__).parent))
import app_shell


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='hp-e2e-'))
    install = tmp / 'hermes'
    install.mkdir(parents=True)
    os.environ['HERMES_PORTABLE_INSTALL_DIR'] = str(install)

    # Minimal web_dist so the SPA mount has something to serve. mount_spa()
    # requires an assets/ subdir to exist or it refuses to start.
    wd = install / 'hermes_cli' / 'web_dist'
    (wd / 'assets').mkdir(parents=True)
    (wd / 'index.html').write_text(
        '<!doctype html><html><body><h1>Hermes E2E</h1></body></html>',
        encoding='utf-8')
    (wd / 'assets' / 'placeholder.js').write_text('// placeholder\n',
                                                  encoding='utf-8')

    # hermes-home so the engine has a HOME to write to.
    home = install / 'hermes-home'
    home.mkdir(exist_ok=True)

    # Pin a random isolated high port. The dev box runs a production hermes on
    # 9119 and prior test processes can leave sockets in TIME_WAIT on 9120+/fixed
    # ports, which would make find_free_port() pick a colliding port and make
    # this test flaky (engine preflight then exits 75 = PORT_IN_USE).
    import random
    _test_port = str(random.randint(20000, 29999))
    os.environ['HERMES_PORT'] = _test_port

    print(f'[e2e] install dir = {install} (port {_test_port})')
    try:
        port = app_shell.ensure_selfhost()
    except Exception:
        import traceback
        print('[e2e] ensure_selfhost failed — full traceback:')
        if 'exc' in app_shell._SERVER_ERROR:
            traceback.print_exception(
                type(app_shell._SERVER_ERROR['exc']),
                app_shell._SERVER_ERROR['exc'],
                app_shell._SERVER_ERROR['exc'].__traceback__)
        traceback.print_exc()
        raise
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
