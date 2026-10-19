# -*- mode: python ; coding: utf-8 -*-
"""
Hermes Agent Portable Build — PyInstaller Spec File
Build the GUI app shell (tray + webview + first-run installer) as a
single-file windowed .exe for Windows.

Usage (on Windows):
    pip install pyinstaller
    pyinstaller hermes.spec

Output: dist/hermes.exe (~80-100 MB with GUI deps)
"""

import os
import sys
import importlib
from pathlib import Path

# PyInstaller execs this spec with SPECPATH set to the spec's directory
# (portable/). The old code referenced an undefined SPECBOX, which raised
# NameError the moment PyInstaller loaded the spec → the exe never built.
_SPEC_DIR = Path(SPECPATH) if 'SPECPATH' in dir() else Path(__file__).resolve().parent
SPEC_ROOT = _SPEC_DIR
REPO_ROOT = _SPEC_DIR.parent   # portable/ sits directly under the repo root

# ─── Collect all tool modules (auto-discovered) ───────────────────────────
tools_dir = REPO_ROOT / 'tools'
hidden_imports = []
for py_file in sorted(tools_dir.glob('*.py')):
    if py_file.name.startswith('_') or py_file.name == 'registry.py':
        continue
    hidden_imports.append(f'tools.{py_file.stem}')

# Add tool subdirectories (environments, etc.)
for sub in tools_dir.iterdir():
    if sub.is_dir() and not sub.name.startswith('_'):
        for py_file in sub.glob('*.py'):
            if not py_file.name.startswith('_'):
                hidden_imports.append(f'tools.{sub.name}.{py_file.stem}')

# Add gateway platform adapters
gateway_platforms = REPO_ROOT / 'gateway' / 'platforms'
if gateway_platforms.exists():
    for py_file in sorted(gateway_platforms.glob('*.py')):
        if not py_file.name.startswith('_'):
            hidden_imports.append(f'gateway.platforms.{py_file.stem}')

# Add plugin modules
plugins_dir = REPO_ROOT / 'plugins'
if plugins_dir.exists():
    for plugin_sub in plugins_dir.iterdir():
        if plugin_sub.is_dir() and not plugin_sub.name.startswith('_'):
            for py_file in plugin_sub.glob('*.py'):
                if not py_file.name.startswith('_'):
                    hidden_imports.append(f'plugins.{plugin_sub.name}.{py_file.stem}')

# Add agent submodules
agent_dir = REPO_ROOT / 'agent'
if agent_dir.exists():
    for py_file in sorted(agent_dir.glob('*.py')):
        if not py_file.name.startswith('_'):
            hidden_imports.append(f'agent.{py_file.stem}')

# Add hermes_cli submodules
hermes_cli_dir = REPO_ROOT / 'hermes_cli'
for py_file in sorted(hermes_cli_dir.glob('*.py')):
    if not py_file.name.startswith('_'):
        hidden_imports.append(f'hermes_cli.{py_file.stem}')

# Add cron modules
cron_dir = REPO_ROOT / 'cron'
if cron_dir.exists():
    for py_file in sorted(cron_dir.glob('*.py')):
        if not py_file.name.startswith('_'):
            hidden_imports.append(f'cron.{py_file.stem}')

# Add acp_adapter modules
acp_dir = REPO_ROOT / 'acp_adapter'
if acp_dir.exists():
    for py_file in sorted(acp_dir.glob('*.py')):
        if not py_file.name.startswith('_'):
            hidden_imports.append(f'acp_adapter.{py_file.stem}')

# Core hidden imports that might not be auto-discovered
core_hidden = [
    'hermes_bootstrap',
    'hermes_constants',
    'hermes_logging',
    'hermes_time',
    'hermes_state',
    'hermes_state_common',
    'hermes_state_portability',
    'hermes_state_schema',
    'hermes_state_search',
    'model_tools',
    'toolsets',
    'toolset_distributions',
    'trajectory_compressor',
    'batch_runner',
    'utils',
    'run_agent',
    'cli',
    'mcp_serve',
    'registration_lifecycle',
    # Prompt toolkit (used by CLI)
    'prompt_toolkit',
    'prompt_toolkit.bindings',
    'prompt_toolkit.layout',
    'prompt_toolkit.styles',
    # Provider adapters
    'openai',
    'httpx',
    'httpcore',
    'pydantic',
    'rich',
    'rich.console',
    'rich.markdown',
    'rich.table',
    'rich.panel',
    'rich.text',
    'rich.progress',
    'rich.theme',
    'rich.live',
    'rich.spinner',
    'ruamel.yaml',
    'ruamel.yaml.comments',
    'yaml',
    'dotenv',
    'fire',
    'tenacity',
    'jinja2',
    'croniter',
    'markdown',
    'jwt',
    'psutil',
    'pathspec',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'fastapi',
    'uvicorn',
    'starlette',
    # GUI shell deps (tray + webview window)
    'pywebview',
    'webview',
    'pystray',
    'pystray._win32',
    'PIL',
    # Qt window backend (Electron-like: bundles its own Chromium, so the native
    # window works even with no WebView2 runtime on locked-down machines).
    'qt_window',
    'PySide6',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineCore',
    'PySide6.QtNetwork',
    # SQLite (used by hermes_state)
    'sqlite3',
    # Windows-specific
    'pywinpty',
    'win32api',
    'win32com',
    'win32com.client',
    'pythoncom',
]

hidden_imports = list(set(hidden_imports + core_hidden))

# ─── Data files to bundle ──────────────────────────────────────────────────
# Skills, plugins, dist assets — these are the "payload" that ships with the exe
datas = []

# Built-in skills
skills_dir = REPO_ROOT / 'skills'
if skills_dir.exists():
    datas.append((str(skills_dir), 'skills'))

# Optional skills
optional_skills_dir = REPO_ROOT / 'optional-skills'
if optional_skills_dir.exists():
    datas.append((str(optional_skills_dir), 'optional-skills'))

# Plugins
plugins_data = REPO_ROOT / 'plugins'
if plugins_data.exists():
    datas.append((str(plugins_data), 'plugins'))

# Web dist (dashboard)
web_dist = REPO_ROOT / 'hermes_cli' / 'web_dist'
if web_dist.exists():
    datas.append((str(web_dist), 'hermes_cli/web_dist'))

# TUI dist
tui_dist = REPO_ROOT / 'hermes_cli' / 'tui_dist'
if tui_dist.exists():
    datas.append((str(tui_dist), 'hermes_cli/tui_dist'))

# Config templates
config_dir = REPO_ROOT / 'config_templates'
if config_dir.exists():
    datas.append((str(config_dir), 'config_templates'))

# .env.example
env_example = REPO_ROOT / '.env.example'
if env_example.exists():
    datas.append((str(env_example), '.'))

# Bundled wheels for offline install
wheels_dir = REPO_ROOT / 'portable' / 'wheels'
if wheels_dir.exists():
    datas.append((str(wheels_dir), 'bundled_wheels'))

# pywebview (import name 'webview') + pystray ship submodules/data that static
# analysis cannot follow (dynamic platform backends). Collect BEFORE Analysis
# and feed the results into the CORRECT Analysis params. collect_all returns
# (datas, binaries, hiddenimports) — appending datas (2-tuples) into a.pure
# (needs 3-tuples) crashes PYZ with "not enough values to unpack".
from PyInstaller.utils.hooks import collect_all as _collect_all

_gui_binaries = []
# pythonnet + clr_loader: pywebview's Windows backends import clr → pythonnet
# → clr_loader, which loads Python.Runtime.dll at runtime. PyInstaller misses
# their runtime DLLs/data without collect_all ("Failed to resolve
# Python.Runtime.Loader.Initialize"). Best-effort; app also has a browser
# fallback if the native window still fails.
for _pkg in ('webview', 'pystray', 'pythonnet', 'clr_loader',
             'PySide6', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore',
             'PySide6.QtNetwork', 'PySide6.QtGui', 'PySide6.QtWidgets',
             'PySide6.QtCore'):
    try:
        _c_datas, _c_binaries, _c_hidden = _collect_all(_pkg)
        datas += _c_datas
        _gui_binaries += _c_binaries
        hidden_imports += _c_hidden
    except Exception:
        pass

# ─── Analysis ──────────────────────────────────────────────────────────────
a = Analysis(
    [str(REPO_ROOT / 'portable' / 'app_shell.py')],
    # portable/ must be on pathex so `import qt_window` (app_shell's Qt backend,
    # which lives NEXT to app_shell.py in portable/) resolves at build time —
    # otherwise PyInstaller silently omits it and the exe always falls back to
    # pywebview/browser with no Qt window.
    pathex=[str(REPO_ROOT), str(REPO_ROOT / 'portable')],
    binaries=_gui_binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy unused modules
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'pytest',
        '_pytest',
        'unittest',
        'doctest',
        'xmlrpc',
        'pydoc',
        'pdb',
        'profile',
        'cProfile',
        'lib2to3',
        'ensurepip',
        'idlelib',
        'turtledemo',
        'test',
        'tests',
        # NOTE: do NOT exclude asyncio/anyio/trio — uvicorn + starlette
        # (dashboard server) require them at runtime.
    ],
    noarchive=False,
    optimize=1,  # -O1 for smaller size
)

# ─── PYZ (compressed Python archive) ──────────────────────────────────────
pyz = PYZ(a.pure, a.zipped_data)

# ─── EXE + COLLECT (onedir) ────────────────────────────────────────────────
# Build as ONEDIR, not onefile. A onefile exe extracts its bundled DLLs to
# %TEMP%\_MEIxxxx on EVERY launch; corporate antivirus (this app runs on bank
# machines) hooks that temp extraction and blocks the OpenSSL DLLs, so
# `import ssl` dies with "DLL load failed while importing _ssl: Invalid
# access to memory location" (Win32 error 998). In onedir the DLLs sit in a
# normal `_internal\` folder and load normally — no temp extraction, no AV
# hook. Also much faster startup (no re-extract of an 88 MB payload each run).
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # keep binaries in _internal\, not inside the exe
    name='hermes',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,        # stripping can break some Windows binaries
    upx=False,          # UPX corrupts OpenSSL/pyd binaries — keep off
    console=False,      # GUI app (windowed); CLI re-attaches parent console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,          # Can add hermes.ico later
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='hermes',      # output folder: dist\hermes\ (exe + _internal\)
)
