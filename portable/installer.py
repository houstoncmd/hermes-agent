#!/usr/bin/env python3
"""
Hermes Agent Portable — Windows Installer

This script runs after hermes.exe is extracted. It:
1. Extracts the payload.zip to the install directory
2. Creates a Python virtual environment from bundled wheels
3. Sets up configuration files
4. Creates a desktop shortcut

Usage:
    python installer.py [--install-dir PATH] [--payload PATH]
"""

import os
import sys
import json
import shutil
import zipfile
import hashlib
import argparse
import subprocess
import winreg
from pathlib import Path
from datetime import datetime

# ─── Constants ─────────────────────────────────────────────────────────────
APP_NAME = 'Hermes Agent'
APP_VERSION = '0.16.0'
# Default install to D:\hermes (as requested)
DEFAULT_INSTALL_DIR = Path('D:/hermes')
HERMES_HOME_NAME = 'hermes-home'
DESKTOP_DIR = Path(os.environ.get('USERPROFILE', Path.home())) / 'Desktop'

# ─── Helper Functions ──────────────────────────────────────────────────────

def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_step(text: str):
    """Print a step."""
    print(f"\n▸ {text}")


def print_success(text: str):
    """Print success message."""
    print(f"  ✓ {text}")


def print_warning(text: str):
    """Print warning message."""
    print(f"  ⚠ {text}")


def print_error(text: str):
    """Print error message."""
    print(f"  ✗ {text}")


def find_python() -> Path:
    """Find Python 3.11+ executable."""
    # Check common locations
    candidates = [
        Path(sys.executable),
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Python' / 'Python311' / 'python.exe',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Python' / 'Python311-64' / 'python.exe',
        Path('C:/Python311/python.exe'),
        Path('C:/Python311-64/python.exe'),
        Path('C:/Program Files/Python311/python.exe'),
    ]

    # Check PATH
    for name in ['python3.11', 'python3', 'python']:
        path = shutil.which(name)
        if path:
            candidates.insert(0, Path(path))

    for candidate in candidates:
        if candidate.exists():
            # Verify version
            try:
                result = subprocess.run(
                    [str(candidate), '--version'],
                    capture_output=True, text=True, timeout=5
                )
                if '3.11' in result.stdout or '3.12' in result.stdout or '3.13' in result.stdout:
                    return candidate
            except Exception:
                continue

    return None


def create_virtual_environment(python_path: Path, install_dir: Path,
                                wheels_dir: Path) -> bool:
    """Create a virtual environment and install bundled wheels."""
    venv_dir = install_dir / '.venv'

    print_step("Creating Python virtual environment...")
    try:
        result = subprocess.run(
            [str(python_path), '-m', 'venv', str(venv_dir)],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print_error(f"Failed to create venv: {result.stderr}")
            return False
        print_success(f"Created venv at {venv_dir}")
    except Exception as e:
        print_error(f"Failed to create venv: {e}")
        return False

    # Install wheels
    pip_path = venv_dir / 'Scripts' / 'pip.exe'
    if not pip_path.exists():
        pip_path = venv_dir / 'bin' / 'pip'

    print_step("Installing dependencies from bundled wheels...")
    wheel_files = list(wheels_dir.glob('*.whl'))
    if not wheel_files:
        print_warning("No wheel files found, skipping installation")
        return True

    try:
        # Upgrade pip first
        subprocess.run(
            [str(pip_path), 'install', '--upgrade', 'pip'],
            capture_output=True, text=True, timeout=60
        )

        # Install all wheels
        cmd = [str(pip_path), 'install', '--no-index', '--find-links', str(wheels_dir)]
        cmd += [str(w) for w in wheel_files]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print_warning(f"Some packages may have failed: {result.stderr[:200]}")
        else:
            print_success(f"Installed {len(wheel_files)} packages")
    except Exception as e:
        print_warning(f"Wheel installation encountered issues: {e}")

    return True


def extract_payload(payload_path: Path, install_dir: Path) -> bool:
    """Extract payload.zip to install directory."""
    print_step("Extracting payload...")

    if not payload_path.exists():
        print_error(f"Payload not found: {payload_path}")
        return False

    try:
        with zipfile.ZipFile(payload_path, 'r') as zf:
            # Read manifest
            if 'MANIFEST.json' in zf.namelist():
                manifest = json.loads(zf.read('MANIFEST.json'))
                print(f"  📋 Payload version: {manifest.get('version', 'unknown')}")
                print(f"  📋 Created: {manifest.get('created_at', 'unknown')}")

            # Extract files
            zf.extractall(install_dir)
            print_success(f"Extracted to {install_dir}")
    except Exception as e:
        print_error(f"Failed to extract payload: {e}")
        return False

    return True


def setup_config(install_dir: Path) -> bool:
    """Set up initial configuration files."""
    print_step("Setting up configuration...")

    hermes_home = install_dir / HERMES_HOME_NAME
    hermes_home.mkdir(parents=True, exist_ok=True)

    # Create config.yaml if not exists
    config_path = hermes_home / 'config.yaml'
    if not config_path.exists():
        config_template = install_dir / 'config_templates' / 'config.yaml'
        if config_template.exists():
            shutil.copy2(config_template, config_path)
        else:
            # Create minimal config
            config_content = f"""# Hermes Agent Configuration
# Generated by portable installer on {datetime.now().isoformat()}

model:
  default: openrouter/auto
  provider: openrouter

agent:
  max_turns: 90

terminal:
  backend: local
  timeout: 180

display:
  skin: default
  show_reasoning: false
"""
            config_path.write_text(config_content, encoding='utf-8')
        print_success(f"Created {config_path}")

    # Create .env if not exists
    env_path = hermes_home / '.env'
    if not env_path.exists():
        env_example = install_dir / '.env.example'
        if env_example.exists():
            shutil.copy2(env_example, env_path)
        else:
            env_path.write_text("# Hermes Agent Environment Variables\n", encoding='utf-8')
        print_success(f"Created {env_path}")

    # Create directories
    for subdir in ['sessions', 'skills', 'memories', 'logs', 'auth']:
        (hermes_home / subdir).mkdir(parents=True, exist_ok=True)

    print_success("Configuration ready")
    return True


def create_desktop_shortcut(install_dir: Path) -> bool:
    """Create a desktop shortcut for Hermes."""
    print_step("Creating desktop shortcut...")

    hermes_exe = install_dir / 'hermes.exe'
    shortcut_path = DESKTOP_DIR / 'Hermes Agent.lnk'

    try:
        # Use PowerShell to create shortcut
        ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{shortcut_path}')
$Shortcut.TargetPath = '{hermes_exe}'
$Shortcut.WorkingDirectory = '{install_dir}'
$Shortcut.Description = 'Hermes Agent - AI Assistant'
$Shortcut.Save()
"""
        result = subprocess.run(
            ['powershell', '-Command', ps_script],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print_success(f"Created shortcut: {shortcut_path}")
        else:
            print_warning(f"Could not create shortcut: {result.stderr}")
    except Exception as e:
        print_warning(f"Could not create shortcut: {e}")

    return True


def add_to_path(install_dir: Path) -> bool:
    """Add install directory to user PATH."""
    print_step("Adding to PATH...")

    try:
        # Get current PATH
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment', 0,
                             winreg.KEY_ALL_ACCESS)
        try:
            current_path, _ = winreg.QueryValueEx(key, 'Path')
        except FileNotFoundError:
            current_path = ''

        install_str = str(install_dir)
        if install_str.lower() not in current_path.lower():
            new_path = f"{current_path};{install_str}" if current_path else install_str
            winreg.SetValueEx(key, 'Path', 0, winreg.REG_EXPAND_SZ, new_path)
            print_success(f"Added {install_str} to PATH")
        else:
            print_success("Already in PATH")

        winreg.CloseKey(key)
    except Exception as e:
        print_warning(f"Could not modify PATH: {e}")

    return True


def main():
    parser = argparse.ArgumentParser(description='Hermes Agent Portable Installer')
    parser.add_argument('--install-dir', type=Path, default=DEFAULT_INSTALL_DIR,
                        help=f'Installation directory (default: {DEFAULT_INSTALL_DIR})')
    parser.add_argument('--payload', type=Path, default=None,
                        help='Path to hermes-payload.zip')
    parser.add_argument('--no-shortcut', action='store_true',
                        help='Skip desktop shortcut creation')
    parser.add_argument('--no-path', action='store_true',
                        help='Skip PATH modification')
    args = parser.parse_args()

    print_header(f"Hermes Agent v{APP_VERSION} — Portable Installer")

    # Find payload
    payload_path = args.payload
    if payload_path is None:
        # Look in same directory as this script
        script_dir = Path(__file__).parent
        candidates = [
            script_dir / 'hermes-payload.zip',
            script_dir / f'hermes-payload-*.zip',
        ]
        for candidate in candidates:
            if '*' in str(candidate):
                matches = list(script_dir.glob('hermes-payload-*.zip'))
                if matches:
                    payload_path = sorted(matches)[-1]
                    break
            elif candidate.exists():
                payload_path = candidate
                break

    if payload_path is None or not payload_path.exists():
        print_error("Payload file not found!")
        print("  Please provide --payload PATH to hermes-payload.zip")
        sys.exit(1)

    print(f"  Install directory: {args.install_dir}")
    print(f"  Payload: {payload_path}")

    # Create install directory
    args.install_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Extract payload
    if not extract_payload(payload_path, args.install_dir):
        sys.exit(1)

    # Step 2: Find Python
    print_step("Looking for Python 3.11+...")
    python_path = find_python()
    if python_path:
        print_success(f"Found: {python_path}")
    else:
        print_warning("Python 3.11+ not found!")
        print("  Please install Python 3.11+ from https://python.org")
        print("  Or set PYTHON environment variable to python.exe path")

    # Step 3: Create venv and install dependencies
    wheels_dir = args.install_dir / 'wheels'
    if wheels_dir.exists() and python_path:
        if not create_virtual_environment(python_path, args.install_dir, wheels_dir):
            print_warning("Venv setup had issues, but installation can continue")

    # Step 4: Setup config
    if not setup_config(args.install_dir):
        sys.exit(1)

    # Step 5: Create shortcut
    if not args.no_shortcut:
        create_desktop_shortcut(args.install_dir)

    # Step 6: Add to PATH
    if not args.no_path:
        add_to_path(args.install_dir)

    # Done!
    print_header("Installation Complete! 🎉")
    print(f"""
  Hermes Agent has been installed to:
    {args.install_dir}

  To get started:
    1. Edit {args.install_dir / HERMES_HOME_NAME / '.env'}
       Add your API keys (OPENROUTER_API_KEY, ANTHROPIC_API_KEY, etc.)
    2. Run: {args.install_dir / 'hermes.exe'}
       Or double-click 'Hermes Agent' on your Desktop

  For more information:
    https://hermes-agent.nousresearch.com/docs
""")


if __name__ == '__main__':
    main()
