#!/usr/bin/env python3
"""
Hermes Agent Portable — Main Build Script

Orchestrates the entire portable build process:
1. Downloads and prepares bundled wheels
2. Builds the PyInstaller exe
3. Creates the payload zip
4. Packages everything into a distributable

Usage:
    python build.py [--skip-exe] [--skip-payload] [--include-messaging]

Output:
    dist/
    └── hermes-portable-win64-v0.16.0-YYYYMMDD.zip
        ├── hermes.exe          (Windows executable)
        ├── hermes-payload.zip  (skills, plugins, wheels)
        ├── install.bat         (One-click installer to D:\hermes)
        └── README.txt
"""

import os
import sys
import shutil
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# ─── Configuration ─────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.resolve()
PORTABLE_DIR = REPO_ROOT / 'portable'
DIST_DIR = REPO_ROOT / 'dist'
APP_VERSION = '0.16.0'


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def print_step(text: str):
    """Print a step."""
    print(f"\n▸ {text}")


def print_success(text: str):
    """Print success message."""
    print(f"  ✓ {text}")


def print_error(text: str):
    """Print error message."""
    print(f"  ✗ {text}")


def check_prerequisites():
    """Check if required tools are available."""
    print_step("Checking prerequisites...")

    issues = []

    # Check Python version
    if sys.version_info < (3, 11):
        issues.append(f"Python 3.11+ required (found {sys.version})")

    # Check if PyInstaller is available (only needed for exe build on Windows)
    if sys.platform == 'win32':
        try:
            import PyInstaller
            print_success(f"PyInstaller {PyInstaller.__version__} available")
        except ImportError:
            issues.append("PyInstaller not installed (pip install pyinstaller)")

    # Check if we're on Windows (for Windows build)
    if sys.platform != 'win32':
        print(f"  ⚠  Building on {sys.platform} (Windows exe requires Windows build)")
        print(f"     For Windows exe, run this script on Windows")
        print(f"     Linux/Mac: Only payload.zip will be built")

    if issues:
        print_error("Prerequisites not met:")
        for issue in issues:
            print(f"    - {issue}")
        return False

    print_success("All prerequisites met")
    return True


def download_wheels(include_messaging: bool = False):
    """Download Python package wheels."""
    from build_payload import download_wheels as _download, CORE_DEPS, MESSAGING_DEPS

    wheels_dir = PORTABLE_DIR / 'wheels'
    if wheels_dir.exists() and list(wheels_dir.glob('*.whl')):
        print_step("Wheels already downloaded, skipping...")
        return wheels_dir

    deps = CORE_DEPS[:]
    if include_messaging:
        deps.extend(MESSAGING_DEPS)

    _download(deps, wheels_dir)
    return wheels_dir


def build_exe():
    """Build the PyInstaller exe."""
    print_step("Building hermes.exe with PyInstaller...")

    spec_file = PORTABLE_DIR / 'hermes.spec'
    if not spec_file.exists():
        print_error(f"Spec file not found: {spec_file}")
        return False

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        str(spec_file),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        print_error("PyInstaller build failed")
        print(f"  {result.stderr[:500]}")
        return False

    exe_path = DIST_DIR / 'hermes.exe'
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / 1024 / 1024
        print_success(f"Built: {exe_path} ({size_mb:.1f} MB)")
        return True
    else:
        print_error("exe not found after build")
        return False


def build_payload(include_messaging: bool = False):
    """Build the payload zip."""
    from build_payload import build_payload as _build

    return _build(
        output_dir=DIST_DIR,
        include_messaging=include_messaging,
        download_wheels_flag=False,
    )


def create_distributable():
    """Create the final distributable zip."""
    print_step("Creating distributable package...")

    timestamp = datetime.now().strftime('%Y%m%d')
    zip_name = f'hermes-portable-win64-v{APP_VERSION}-{timestamp}.zip'
    zip_path = DIST_DIR / zip_name

    # Collect files to include
    files_to_include = []

    exe_path = DIST_DIR / 'hermes.exe'
    if exe_path.exists():
        files_to_include.append(('hermes.exe', exe_path))
        print_success(f"  ✓ hermes.exe ({exe_path.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        print(f"  ⚠  hermes.exe not found (build on Windows to create it)")

    # Find payload zip
    payload_files = list(DIST_DIR.glob('hermes-payload-*.zip'))
    if payload_files:
        payload_path = sorted(payload_files)[-1]
        files_to_include.append(('hermes-payload.zip', payload_path))
        print_success(f"  ✓ hermes-payload.zip ({payload_path.stat().st_size / 1024 / 1024:.1f} MB)")

    # NOTE: install.bat is retired. The exe is now self-installing —
    # first double-click extracts payload, copies the engine, creates the
    # desktop shortcut, and writes the marker. See app_shell.py.

    # Create README.txt
    readme_content = f"""╔══════════════════════════════════════════════════════╗
║         Hermes Agent Portable v{APP_VERSION}            ║
╚══════════════════════════════════════════════════════╝

HOW TO INSTALL (just ONE double-click):
  1. Keep hermes.exe next to hermes-payload.zip (same folder).
  2. Double-click hermes.exe  (first run = it installs itself):
       - extracts payload + copies engine to D:\\\\hermes (or %LOCALAPPDATA%\\\\Hermes)
       - creates a "Hermes Agent" shortcut on your Desktop
       - starts the gateway + opens the UI automatically
  3. Done. Later runs: double-click the Desktop icon → straight to the UI.

HOW IT RUNS:
  - The gateway runs hidden in the background; its icon sits in the
    system tray (taskbar corner).
  - Tray:  left-click / "เปิด UI"  → show the window
          minimize  → window hides back to the tray
          "ปิด Hermes Gateway ..." → asks for confirmation
  - Closing the window (X) pops a dialog. Type  shutdown  to actually
    stop the gateway; anything else cancels and keeps it running.

FIRST-TIME SETUP:
  Edit D:\\\\hermes\\\\hermes-home\\\\.env (or %LOCALAPPDATA%\\\\Hermes\\\\hermes-home\\\\.env)
  and add ONE API key, e.g.:
       OPENROUTER_API_KEY=***     (or ANTHROPIC/GOOGLE/DEEPSEEK)

DIRECTORY STRUCTURE:
  D:\\\\hermes\\\\
  ├── hermes.exe              The app (double-click to run)
  ├── skills\\\\  optional-skills\\\\  plugins\\\\   bundled capabilities
  ├── hermes-cli\\\\             engine files
  ├── logs\\\\backend-console.log  gateway log
  └── hermes-home\\\\            Your data
      ├── config.yaml  .env    settings + API keys
      ├── sessions\\\\           chat history
      └── memories\\\\           agent memory

CLI (optional, from CMD/PowerShell):
  D:\\\\hermes\\\\hermes.exe chat -q "..."    single query
  D:\\\\hermes\\\\hermes.exe setup           setup wizard
  D:\\\\hermes\\\\hermes.exe doctor          check installation

REQUIREMENTS:
  - Windows 10/11 (64-bit) — no Python install needed
  - Internet connection (for API calls)

TROUBLESHOOTING:
  - No UI / blank window: install Microsoft Edge WebView2 Runtime
  - "API key not set": edit the .env in hermes-home, then restart from tray
  - Log: D:\\\\hermes\\\\logs\\\\backend-console.log
  - Docs: https://hermes-agent.nousresearch.com/docs

UNINSTALL:
  Delete D:\\\\hermes\\\\ and the Desktop shortcut.
"""

    readme_path = DIST_DIR / 'README.txt'
    readme_path.write_text(readme_content, encoding='utf-8')
    files_to_include.append(('README.txt', readme_path))
    print_success("  ✓ README.txt")

    # Create the zip
    import zipfile
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for arcname, filepath in files_to_include:
            zf.write(filepath, arcname)

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print_step(f"Distributable created: {zip_path}")
    print_success(f"Total size: {size_mb:.1f} MB")

    return zip_path


def cleanup():
    """Clean up temporary build files."""
    print_step("Cleaning up build artifacts...")
    build_dir = REPO_ROOT / 'build'
    if build_dir.exists():
        shutil.rmtree(build_dir)
    # Remove spec from build
    for spec_file in (DIST_DIR / '*.spec', REPO_ROOT / '*.spec'):
        for f in [spec_file] if isinstance(spec_file, Path) else list(Path(REPO_ROOT).glob('*.spec')):
            if f.exists() and f.name == 'hermes.spec':
                pass  # Keep our spec
            elif f.exists():
                f.unlink()
    print_success("Cleanup complete")


def main():
    parser = argparse.ArgumentParser(description='Build Hermes Agent Portable')
    parser.add_argument('--skip-exe', action='store_true',
                        help='Skip exe build (build payload only)')
    parser.add_argument('--skip-payload', action='store_true',
                        help='Skip payload build (build exe only)')
    parser.add_argument('--include-messaging', action='store_true',
                        help='Include messaging platform dependencies')
    parser.add_argument('--no-cleanup', action='store_true',
                        help='Skip cleanup after build')
    args = parser.parse_args()

    print_header(f"Hermes Agent v{APP_VERSION} — Portable Build")

    # Check prerequisites
    if not check_prerequisites():
        print_error("Cannot continue without prerequisites")
        sys.exit(1)

    # Ensure dist directory exists
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # Download wheels
    wheels_dir = download_wheels(args.include_messaging)

    # Build exe (Windows only)
    if not args.skip_exe:
        if sys.platform == 'win32':
            build_exe()
        else:
            print_step("Skipping exe build (not on Windows)")
            print("  To build the exe, run this script on Windows")
            print("  Payload will still be built...")

    # Build payload
    if not args.skip_payload:
        build_payload(args.include_messaging)

    # Create distributable
    zip_path = create_distributable()

    # Cleanup
    if not args.no_cleanup:
        cleanup()

    # Final summary
    print_header("Build Complete! 🎉")
    print(f"""
  📦 Output: {zip_path}

  Contents:
    ├── hermes.exe          (if built on Windows)
    ├── hermes-payload.zip  (skills + plugins + wheels)
    └── README.txt          (instructions)

  To use on Windows:
    1. Copy zip to Windows machine
    2. Extract to any folder
    3. Double-click hermes.exe  (first run installs itself + opens UI)
    4. Edit D:\\\\hermes\\\\hermes-home\\\\.env (add API key) — one time
    5. Later runs: double-click "Hermes Agent" on Desktop → straight to UI

  GUI shell: tray icon + webview window + typed-shutdown confirm.
  See portable/app_shell.py for the flow.
""")


if __name__ == '__main__':
    main()
