#!/usr/bin/env python3
"""
Hermes Agent Portable — Payload Builder

Creates hermes-payload.zip containing skills, plugins, dist assets,
config templates, and bundled wheels for offline dependency installation.

Usage:
    python build_payload.py [--output-dir dist/] [--wheels-dir wheels/]

Output:
    hermes-payload.zip (~10-15 MB)
"""

import os
import sys
import json
import shutil
import zipfile
import hashlib
import argparse
from pathlib import Path
from datetime import datetime

# ─── Configuration ─────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.resolve()

PAYLOAD_ITEMS = {
    # (source_path, destination_in_zip, description)
    'skills': ('skills', 'skills/', 'Built-in skills'),
    'optional-skills': ('optional-skills', 'optional-skills/', 'Optional/heavy skills'),
    'plugins': ('plugins', 'plugins/', 'Plugin modules'),
    'web_dist': ('hermes_cli/web_dist', 'hermes_cli/web_dist/', 'Web dashboard assets'),
    'tui_dist': ('hermes_cli/tui_dist', 'hermes_cli/tui_dist/', 'TUI (Ink React) assets'),
    'config_example': ('cli-config.yaml.example', 'config.yaml.example', 'Configuration example'),
    'env_example': ('.env.example', '.env.example', 'Environment file template'),
}

# Core Python dependencies that need to be bundled as wheels
CORE_DEPS = [
    'openai==2.24.0',
    'python-dotenv==1.2.2',
    'fire==0.7.1',
    'httpx[socks]==0.28.1',
    'rich==14.3.3',
    'tenacity==9.1.4',
    'pyyaml==6.0.3',
    'ruamel.yaml==0.18.17',
    'requests==2.33.0',
    'jinja2==3.1.6',
    'pydantic==2.13.4',
    'prompt_toolkit==3.0.52',
    'croniter==6.0.0',
    'Markdown==3.10.2',
    'PyJWT[crypto]==2.12.1',
    'psutil==7.2.2',
    'pathspec==1.1.1',
    'fastapi>=0.104.0,<1',
    'uvicorn[standard]>=0.24.0,<1',
    'Pillow==12.2.0',
]

# Messaging deps (optional, for gateway mode)
MESSAGING_DEPS = [
    'python-telegram-bot[webhooks]==22.6',
    'discord.py[voice]==2.7.1',
    'aiohttp==3.13.3',
    'brotlicffi==1.2.0.1',
    'slack-bolt==1.27.0',
    'slack-sdk==3.40.1',
    'qrcode==7.4.2',
]


def download_wheels(deps: list, output_dir: Path, platform: str = 'win_amd64',
                    python_version: str = '3.11') -> list:
    """Download wheel files for the given dependencies."""
    import subprocess

    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, '-m', 'pip', 'download',
        '-d', str(output_dir),
        '--platform', platform,
        '--python-version', python_version,
        '--only-binary=:all:',
        '-q',
    ] + deps

    print(f"📦 Downloading {len(deps)} packages...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"⚠️  Some packages may not have binary wheels for {platform}")
        print(f"   Falling back to source distribution download...")
        # Retry without --only-binary
        cmd_no_binary = [
            sys.executable, '-m', 'pip', 'download',
            '-d', str(output_dir),
            '-q',
        ] + deps
        result = subprocess.run(cmd_no_binary, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Failed to download wheels: {result.stderr}")
            return []

    wheels = list(output_dir.glob('*.whl')) + list(output_dir.glob('*.tar.gz'))
    print(f"✅ Downloaded {len(wheels)} packages")
    return wheels


def calculate_file_hash(filepath: Path) -> str:
    """Calculate SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def build_payload(output_dir: Path, wheels_dir: Path = None,
                  include_messaging: bool = False,
                  download_wheels_flag: bool = True) -> Path:
    """
    Build the hermes-payload.zip file.

    Args:
        output_dir: Directory to write the output zip
        wheels_dir: Directory containing pre-downloaded wheels (optional)
        include_messaging: Include messaging platform dependencies
        download_wheels_flag: Download wheels if not provided

    Returns:
        Path to the created zip file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_name = f'hermes-payload-{timestamp}.zip'
    zip_path = output_dir / zip_name

    # Handle wheels
    if wheels_dir is None:
        wheels_dir = REPO_ROOT / 'portable' / 'wheels'

    if download_wheels_flag and not any(wheels_dir.glob('*.whl')):
        print("📥 No wheels found, downloading...")
        deps = CORE_DEPS + (MESSAGING_DEPS if include_messaging else [])
        download_wheels(deps, wheels_dir)

    print(f"\n📦 Building payload: {zip_path}")

    manifest = {
        'version': '0.16.0',
        'created_at': datetime.now().isoformat(),
        'platform': 'win_amd64',
        'items': {},
        'wheels': {},
    }

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # Add payload items
        for key, (src_rel, dst_prefix, desc) in PAYLOAD_ITEMS.items():
            src_path = REPO_ROOT / src_rel
            if not src_path.exists():
                print(f"  ⚠️  Skipping {key} (not found: {src_path})")
                continue

            print(f"  📁 Adding {desc}: {src_rel} → {dst_prefix}")
            file_count = 0

            if src_path.is_file():
                zf.write(src_path, dst_prefix)
                file_count = 1
            else:
                for file in sorted(src_path.rglob('*')):
                    if file.is_file():
                        arcname = os.path.join(dst_prefix, str(file.relative_to(src_path)))
                        zf.write(file, arcname)
                        file_count += 1

            manifest['items'][key] = {
                'path': dst_prefix,
                'description': desc,
                'file_count': file_count,
            }

        # Add wheels
        if wheels_dir.exists():
            wheel_files = list(wheels_dir.glob('*.whl')) + list(wheels_dir.glob('*.tar.gz'))
            print(f"  📦 Adding {len(wheel_files)} wheel packages...")
            for wheel in sorted(wheel_files):
                zf.write(wheel, f'wheels/{wheel.name}')
                manifest['wheels'][wheel.name] = {
                    'hash': calculate_file_hash(wheel),
                    'size': wheel.stat().st_size,
                }

        # Add manifest
        manifest_json = json.dumps(manifest, indent=2)
        zf.writestr('MANIFEST.json', manifest_json)
        print(f"  📋 Added manifest ({len(manifest_json)} bytes)")

    # Print summary
    zip_size = zip_path.stat().st_size
    print(f"\n✅ Payload created: {zip_path}")
    print(f"   Size: {zip_size / 1024 / 1024:.1f} MB")
    print(f"   Items: {len(manifest['items'])}")
    print(f"   Wheels: {len(manifest['wheels'])}")

    return zip_path


def main():
    parser = argparse.ArgumentParser(description='Build Hermes Agent portable payload')
    parser.add_argument('--output-dir', type=Path, default=REPO_ROOT / 'dist',
                        help='Output directory (default: dist/)')
    parser.add_argument('--wheels-dir', type=Path, default=None,
                        help='Pre-downloaded wheels directory')
    parser.add_argument('--include-messaging', action='store_true',
                        help='Include messaging platform dependencies')
    parser.add_argument('--no-download', action='store_true',
                        help='Skip wheel download (use existing wheels)')
    args = parser.parse_args()

    build_payload(
        output_dir=args.output_dir,
        wheels_dir=args.wheels_dir,
        include_messaging=args.include_messaging,
        download_wheels_flag=not args.no_download,
    )


if __name__ == '__main__':
    main()
