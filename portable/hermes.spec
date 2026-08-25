# -*- mode: python ; coding: utf-8 -*-
"""
Hermes Agent Portable Build — PyInstaller Spec File
Build the core engine as a single-file .exe for Windows.

Usage (on Windows):
    pip install pyinstaller
    pyinstaller hermes.spec

Output: dist/hermes.exe (~30-35 MB)
"""

import os
import sys
import importlib
from pathlib import Path

SPEC_ROOT = Path(os.path.abspath(SPECBOX)).parent if '__file__' in dir() else Path('.')
REPO_ROOT = Path(os.path.abspath(os.path.dirname(SPECBOX))) if '__file__' in dir() else Path('..')

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

# ─── Analysis ──────────────────────────────────────────────────────────────
a = Analysis(
    [str(REPO_ROOT / 'hermes_cli' / 'main.py')],
    pathex=[str(REPO_ROOT)],
    binaries=[],
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
        # Exclude async frameworks we don't use
        'asyncio',
        'trio',
        'anyio',
    ],
    noarchive=False,
    optimize=1,  # -O1 for smaller size
)

# ─── PYZ (compressed Python archive) ──────────────────────────────────────
pyz = PYZ(a.pure, a.zipped_data)

# ─── EXE ──────────────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='hermes',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,         # Strip debug symbols
    upx=True,           # Compress with UPX if available
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # CLI application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,          # Can add hermes.ico later
)
