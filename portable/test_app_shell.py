#!/usr/bin/env python3
"""Self-test for portable/app_shell.py — runs on Linux (no GUI deps needed).

Tests the pure-logic paths: path resolution, first-run install (payload
extraction, engine copy, hermes-home seeding, marker), port probing, and the
shutdown-word contract. GUI/webview/pystray imports are NOT exercised here.
"""
import os
import sys
import shutil
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'portable'))

_tmp = Path(tempfile.mkdtemp(prefix='hp-test-'))
_install = _tmp / 'D' / 'hermes'
os.environ['HERMES_PORTABLE_INSTALL_DIR'] = str(_install)

import app_shell as A  # noqa: E402

results = []


def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))


# 1. Path resolution
check('install_dir override honored', A.install_dir() == _install, str(A.install_dir()))
check('hermes_home under install', A.hermes_home() == _install / 'hermes-home')
check('not installed initially', not A.is_installed())

# 2. Fake payload zip next to a fake "original exe"
fake_src = _tmp / 'download'
fake_src.mkdir()
(fake_src / 'hermes.exe').write_bytes(b'FAKEEXE' * 100)
with zipfile.ZipFile(fake_src / 'hermes-payload.zip', 'w') as zf:
    zf.writestr('skills/demo/SKILL.md', 'test skill')
    zf.writestr('hermes_cli/web_dist/index.html', '<html>SPA</html>')
    zf.writestr('plugins/demo/__init__.py', '')

A.original_exe = lambda: fake_src / 'hermes.exe'
A.create_desktop_shortcut = lambda *a, **k: None  # no PowerShell on Linux

# 3. First install
msgs = []
exe_path = A.run_first_install(msgs.append)
check('install dir created', _install.is_dir())
check('payload skills extracted', (_install / 'skills' / 'demo' / 'SKILL.md').exists())
check('payload web_dist extracted', (_install / 'hermes_cli' / 'web_dist' / 'index.html').exists())
check('engine exe copied', (_install / 'hermes.exe').read_bytes().startswith(b'FAKEEXE'))
check('hermes-home seeded', (_install / 'hermes-home').is_dir())
check('home subdirs created', all(
    (_install / 'hermes-home' / d).is_dir() for d in ('sessions', 'memories', 'skills', 'logs')))
check('marker written', A.marker_file().exists())
check('is_installed now True', A.is_installed())
check('progress messages emitted', len(msgs) >= 3, f'{len(msgs)} msgs')

# 4. Port probing
p = A.find_free_port()
check('find_free_port in range', isinstance(p, int) and 9119 <= p < 9129, str(p))
check('port_responds False (dead port)', not A.port_responds(p))

# 5. Shutdown contract
check('shutdown word = "shutdown"', A.SHUTDOWN_WORD == 'shutdown')

# 6. Idempotency: re-run install must not crash or duplicate
A.run_first_install(lambda m: None)
check('re-install idempotent', (_install / 'hermes.exe').exists())

shutil.rmtree(_tmp, ignore_errors=True)

w = max(len(n) for n, _, _ in results)
fails = 0
for name, ok, detail in results:
    if not ok:
        fails += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {name.ljust(w)}  {detail}")
print(f'\n{len(results) - fails}/{len(results)} passed')
sys.exit(1 if fails else 0)
