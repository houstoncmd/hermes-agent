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
    ├── hermes-portable-win64-v0.16.0.zip
    │   ├── hermes.exe
    │   ├── hermes-payload.zip
    │   └── README.txt
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

    # Check if PyInstaller is available (for exe build)
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
    from build_payload import download_wheels, CORE_DEPS, MESSAGING_DEPS

    wheels_dir = PORTABLE_DIR / 'wheels'
    if wheels_dir.exists() and list(wheels_dir.glob('*.whl')):
        print_step("Wheels already downloaded, skipping...")
        return wheels_dir

    deps = CORE_DEPS[:]
    if include_messaging:
        deps.extend(MESSAGING_DEPS)

    download_wheels(deps, wheels_dir)
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
    from build_payload import build_payload as _build_payload

    return _build_payload(
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

    # Find payload zip
    payload_files = list(DIST_DIR.glob('hermes-payload-*.zip'))
    if payload_files:
        payload_path = sorted(payload_files)[-1]
        files_to_include.append(('hermes-payload.zip', payload_path))

    # Create README
    readme_content = f"""Hermes Agent Portable v{APP_VERSION}
{'='*40}

Installation:
1. Extract this zip to a folder
2. Run hermes-setup.exe (or hermes.exe on first run)
3. Follow the installer prompts

First Run:
1. The installer will create a virtual environment
2. Edit hermes-home/.env to add your API keys
3. Run hermes.exe to start chatting

Directory Structure:
  hermes.exe          - Main application
  hermes-payload.zip  - Supporting files (auto-extracted)
  hermes-home/        - Configuration and data
    config.yaml       - Settings
    .env              - API keys
    sessions/         - Chat sessions
    skills/           - Installed skills
    memories/         - Agent memory

More Info: https://hermes-agent.nousresearch.com/docs
"""
    readme_path = DIST_DIR / 'README.txt'
    readme_path.write_text(readme_content, encoding='utf-8')
    files_to_include.append(('README.txt', readme_path))

    # Create zip
    import zipfile
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for arcname, filepath in files_to_include:
            zf.write(filepath, arcname)

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print_success(f"Created: {zip_path} ({size_mb:.1f} MB)")

    return zip_path


def cleanup():
    """Clean up temporary build files."""
    print_step("Cleaning up...")
    build_dirs = [REPO_ROOT / 'build', REPO_ROOT / '*.spec']
    for d in build_dirs:
        if d.exists():
            shutil.rmtree(d)
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

    print_header(f"Hermes Agent vAPP_VERSION — Portable Build")

    # Check prerequisites
    if not check_prerequisites():
        sys.exit(1)

    # Ensure dist directory exists
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # Download wheels
    wheels_dir = download_wheels(args.include_messaging)

    # Build exe
    if not args.skip_exe:
        if sys.platform == 'win32':
            build_exe()
        else:
            print("\n  ⚠  Skipping exe build (not on Windows)")
            print("     Run this script on Windows to build the exe")

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
  Output: {zip_path}

  Files included:
    - hermes.exe (Windows executable)
    - hermes-payload.zip (skills, plugins, wheels)
    - README.txt (installation guide)

  To distribute:
    1. Share the zip file
    2. User extracts and runs hermes.exe
    3. Installer handles the rest
""")


if __name__ == '__main__':
    main()
