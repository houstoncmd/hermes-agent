#!/usr/bin/env python3
"""Validate that portable/hermes.spec executes without error, using stubbed
PyInstaller globals (Analysis/PYZ/EXE). Catches spec-level bugs fast on Linux
without needing a real PyInstaller Windows build."""
import sys
import types
import traceback
from pathlib import Path

spec_path = Path(__file__).resolve().parent / 'hermes.spec'
src = spec_path.read_text(encoding='utf-8')


class FakeAnalysis:
    def __init__(self, *a, **k):
        self.pure = []
        self.binaries = []
        self.zipped_data = None
        self.scripts = []
        self.datas = k.get('datas', [])


class FakePYZ:
    def __init__(self, *a, **k):
        pass


class FakeEXE:
    def __init__(self, *a, **k):
        pass


class FakeCOLLECT:
    def __init__(self, *a, **k):
        pass


fake_hooks = types.ModuleType("PyInstaller.utils.hooks")
fake_hooks.collect_all = lambda pkg: ([], [], [])
fake_utils = types.ModuleType("PyInstaller.utils")
fake_utils.hooks = fake_hooks
fake_pi = types.ModuleType("PyInstaller")
fake_pi.utils = fake_utils
sys.modules['PyInstaller'] = fake_pi
sys.modules['PyInstaller.utils'] = fake_utils
sys.modules['PyInstaller.utils.hooks'] = fake_hooks

g = {'Analysis': FakeAnalysis, 'PYZ': FakePYZ, 'EXE': FakeEXE,
     'COLLECT': FakeCOLLECT, '__file__': str(spec_path)}

try:
    exec(compile(src, str(spec_path), 'exec'), g)
    print("SPEC EXECUTED OK")
    print("hidden_imports:", len(g.get('hidden_imports', [])))
    print("datas:", len(g.get('datas', [])))
except Exception:
    print("SPEC FAILED:")
    traceback.print_exc()
    sys.exit(1)
