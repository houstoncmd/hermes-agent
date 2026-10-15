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

    # Create install.bat (one-click installer)
    install_bat_content = f"""@echo off
chcp 65001 >nul 2>&1
title Hermes Agent v{APP_VERSION} Installer

echo.
echo ========================================
echo   Hermes Agent v{APP_VERSION} - Installer
echo ========================================
echo.
echo Install location: D:\\hermes
echo.

REM Create D:\\hermes directory
if not exist "D:\\hermes" (
    echo [1/4] Creating D:\\hermes directory...
    mkdir "D:\\hermes"
) else (
    echo [1/4] D:\\hermes directory already exists
)

REM Copy hermes.exe
echo [2/4] Copying hermes.exe...
copy /Y "hermes.exe" "D:\\hermes\\hermes.exe" >nul 2>&1

REM Extract payload
echo [3/4] Extracting payload to D:\\hermes...
powershell -command "Expand-Archive -Path 'hermes-payload.zip' -DestinationPath 'D:\\hermes' -Force" >nul 2>&1

REM Create desktop shortcut
echo [4/4] Creating desktop shortcut...
powershell -command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut([System.Environment]::GetFolderPath('Desktop') + '\\Hermes Agent.lnk'); $Shortcut.TargetPath = 'D:\\hermes\\hermes.exe'; $Shortcut.WorkingDirectory = 'D:\\hermes'; $Shortcut.Description = 'Hermes Agent - AI Assistant'; $Shortcut.Save()" >nul 2>&1

echo.
echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo Installed to: D:\\hermes
echo Desktop shortcut: "Hermes Agent"
echo.
echo NEXT STEPS:
echo   1. Edit D:\\hermes\\hermes-home\\.env
echo      Add your API key (OPENROUTER_API_KEY=***)
echo   2. Double-click "Hermes Agent" on Desktop
echo      Or open CMD and run: D:\\hermes\\hermes.exe
echo.
pause
"""

    install_bat_path = DIST_DIR / 'install.bat'
    install_bat_path.write_text(install_bat_content, encoding='utf-8')
    files_to_include.append(('install.bat', install_bat_path))
    print_success("  ✓ install.bat")

    # Create README.txt
    readme_content = f"""╔══════════════════════════════════════════════════════╗
║         Hermes Agent Portable v{APP_VERSION}            ║
╚══════════════════════════════════════════════════════╝

QUICK INSTALL:
  1. Double-click install.bat
  2. Done! Files installed to D:\\hermes

MANUAL INSTALL:
  1. Copy hermes.exe to D:\\hermes\\
  2. Extract hermes-payload.zip to D:\\hermes\\

AFTER INSTALL:
  1. Edit D:\\hermes\\hermes-home\\.env
     Add your API key:
       OPENROUTER_API_KEY=***  or
       ANTHROPIC_API_KEY=***  or
       GOOGLE_API_KEY=***  or
       DEEPSEEK_API_KEY=***

  2. Start using:
     - Double-click "Hermes Agent" on Desktop
     - Or open CMD/PowerShell and run: D:\\hermes\\hermes.exe

DIRECTORY STRUCTURE:
  D:\\hermes\\
  ├── hermes.exe              Main application (30 MB)
  ├── skills\\                 Built-in skills
  ├── optional-skills\\        Heavy/niche skills
  ├── plugins\\                Plugin modules
  ├── wheels\\                 Python packages (offline install)
  ├── config.yaml.example     Configuration example
  └── hermes-home\\            Your data (created on first run)
      ├── config.yaml         Settings
      ├── .env                API keys (EDIT THIS!)
      ├── sessions\\           Chat history
      ├── skills\\             Installed skills
      └── memories\\           Agent memory

COMMANDS (CMD / PowerShell):
  D:\\hermes\\hermes.exe                Interactive chat
  D:\\hermes\\hermes.exe chat -q "..."    Single query
  D:\\hermes\\hermes.exe setup           Setup wizard
  D:\\hermes\\hermes.exe model           Change model/provider
  D:\\hermes\\hermes.exe gateway run     Start messaging gateway
  D:\\hermes\\hermes.exe sessions list   List chat sessions
  D:\\hermes\\hermes.exe cron list       List scheduled jobs
  D:\\hermes\\hermes.exe doctor          Check installation

REQUIREMENTS:
  - Windows 10/11 (64-bit)
  - Python 3.11+ (https://python.org/downloads/)
  - Internet connection (for API calls)

TROUBLESHOOTING:
  - "Python not found": Install Python 3.11+ and check "Add to PATH"
  - "API key not set": Edit D:\\hermes\\hermes-home\\.env
  - More help: https://hermes-agent.nousresearch.com/docs

UNINSTALL:
  Delete D:\\hermes\\ and the desktop shortcut.
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
    ├── install.bat         (one-click install to D:\\hermes)
    └── README.txt          (instructions)

  To use on Windows:
    1. Copy zip to Windows machine
    2. Extract to any folder
    3. Double-click install.bat
    4. Edit D:\\hermes\\hermes-home\\.env (add API key)
    5. Double-click "Hermes Agent" on Desktop
""")


if __name__ == '__main__':
    main()
