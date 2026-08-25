# Hermes Agent Portable Build

Build Hermes Agent as a portable Windows application — no Python installation required.

## Architecture

```
hermes-portable/
├── hermes.exe              ← PyInstaller single-file (~30-35 MB)
│   └── Python runtime + Core deps + Hermes engine
│
├── hermes-payload.zip      ← Supporting files (~10-15 MB)
│   ├── skills/             Built-in skills
│   ├── optional-skills/    Heavy/niche skills
│   ├── plugins/            Plugin modules
│   ├── wheels/             Bundled Python packages
│   └── config_templates/   Default configuration
│
└── After first run:
    └── hermes-home/        ← User data
        ├── config.yaml
        ├── .env
        ├── sessions/
        └── memories/
```

## Quick Start

### Build on Windows

```bash
# 1. Install build dependencies
pip install pyinstaller

# 2. Run the build script
cd hermes-agent
python portable/build.py

# 3. Find the output
ls dist/hermes-portable-win64-v*.zip
```

### Build on Linux/Mac (payload only)

```bash
# Only builds the payload zip (no exe)
python portable/build.py --skip-exe
```

## Build Options

| Flag | Description |
|------|-------------|
| `--skip-exe` | Skip exe build, only build payload |
| `--skip-payload` | Skip payload build, only build exe |
| `--include-messaging` | Include Telegram/Discord/Slack dependencies |
| `--no-cleanup` | Keep temporary build files |

## Files

| File | Purpose |
|------|---------|
| `build.py` | Main build orchestrator |
| `hermes.spec` | PyInstaller specification |
| `build_payload.py` | Creates payload zip |
| `installer.py` | Windows installer (runs after extraction) |

## How It Works

### Build Process

1. **Download wheels** — Python packages are downloaded as .whl files
2. **Build exe** — PyInstaller bundles Python + deps + source into single .exe
3. **Create payload** — Skills, plugins, and wheels are packaged into zip
4. **Package** — Final distributable zip is created

### Install Process (End User)

1. **Extract** — User extracts the zip
2. **Run installer** — hermes.exe detects first run and shows installer
3. **Setup venv** — Installer creates Python venv from bundled wheels
4. **Configure** — User sets API keys in .env
5. **Desktop shortcut** — Installer creates .lnk on Desktop

## Size Estimates

| Component | Size |
|-----------|------|
| hermes.exe | ~30-35 MB |
| hermes-payload.zip | ~10-15 MB |
| **Total download** | **~40-50 MB** |
| After install (on disk) | ~130-150 MB |

## Requirements

### Build Machine
- Python 3.11+
- PyInstaller (`pip install pyinstaller`)
- Windows (for exe build)
- Internet connection (for downloading wheels)

### Target Machine
- Windows 10/11
- Python 3.11+ (optional — installer can use bundled wheels)
- ~150 MB disk space

## Customization

### Adding Dependencies

Edit `build_payload.py` and add to `CORE_DEPS` or `MESSAGING_DEPS`:

```python
CORE_DEPS = [
    'openai==2.24.0',
    'your-new-package==1.0.0',
    ...
]
```

### Excluding Features

Edit `hermes.spec` to exclude unwanted modules:

```python
excludes = [
    'tkinter',
    'matplotlib',
    ...
]
```

### Custom Icon

Place `hermes.ico` in `portable/` and update `hermes.spec`:

```python
exe = EXE(
    ...
    icon='hermes.ico',
)
```

## Troubleshooting

### Build fails on Linux

The exe can only be built on Windows. On Linux, use `--skip-exe` to build payload only.

### Missing wheels

If `pip download` fails, check your internet connection and try:
```bash
python -m pip download --platform win_amd64 --python-version 3.11 openai==2.24.0
```

### Installer can't find Python

The installer looks for Python in:
1. Current process (`sys.executable`)
2. `%LOCALAPPDATA%\Programs\Python\Python311`
3. `C:\Python311`
4. PATH

Install Python 3.11+ from https://python.org if not found.

## License

MIT — Same as Hermes Agent
