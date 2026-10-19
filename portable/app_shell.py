#!/usr/bin/env python3
"""
Hermes Agent Portable — GUI App Shell (PyInstaller entry point)

Modes:
    (no args, double-click)  → GUI mode: first-run installer + tray + webview UI
    <any CLI args>           → passthrough to hermes CLI (chat, setup, ...)

Flow (GUI mode):
    1. First run  (no marker in install dir):
       - extract payload zip (next to exe, or bundled in exe)
       - copy engine exe to install dir
       - create desktop shortcut
       - write .installed marker
    2. Every run:
       - self-host the dashboard server IN-PROCESS (daemon thread, no subprocess)
       - open pywebview window → http://127.0.0.1:<port>
       - tray icon: left-click / menu → show window
       - minimize → hide window (tray keeps running)
       - close (X) → confirm dialog: type "shutdown" → exit (daemon thread dies with process)

Install dir resolution:
    D:\\hermes  (if D: exists)  else  %LOCALAPPDATA%\\Hermes
Override: HERMES_PORTABLE_INSTALL_DIR env var (used by tests).
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

APP_NAME = 'Hermes Agent'
APP_VERSION = '0.16.0'
MARKER_NAME = '.installed'
PORTABLE_DIR_NAME = 'hermes'
HERMES_HOME_NAME = 'hermes-home'
BASE_PORT = 9119
PORT_PROBE_RANGE = 10          # try BASE_PORT .. BASE_PORT+9
BACKEND_READY_TIMEOUT = 120    # seconds
SHUTDOWN_WORD = 'shutdown'

CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0


# ─── Paths ─────────────────────────────────────────────────────────────────

def is_frozen() -> bool:
    return getattr(sys, 'frozen', False)


def resource_path(name: str) -> Path:
    """Bundled data path (PyInstaller _MEIPASS or script dir)."""
    base = Path(sys._MEIPASS) if is_frozen() else Path(__file__).parent
    return base / name


def original_exe() -> Path:
    """Path of the REAL downloaded exe (not the _MEI temp extraction)."""
    if is_frozen():
        argv0 = sys.argv[0] if sys.argv else ''
        if argv0.lower().endswith('.exe'):
            p = Path(argv0).resolve()
            if '_MEI' not in str(p) and p.exists():
                return p
        return Path(sys.executable).resolve()
    return Path(sys.executable).resolve()


def engine_exe_name() -> str:
    """Installed engine filename — mirror the real running file's suffix."""
    suffix = original_exe().suffix
    return f'hermes{suffix}' if suffix else 'hermes'


def install_dir() -> Path:
    override = os.environ.get('HERMES_PORTABLE_INSTALL_DIR')
    if override:
        return Path(override)
    if os.name == 'nt' and Path('D:/').exists():
        return Path('D:/') / PORTABLE_DIR_NAME
    local = os.environ.get('LOCALAPPDATA')
    base = Path(local) if local else Path.home() / 'AppData' / 'Local'
    return base / APP_NAME


def hermes_home() -> Path:
    return install_dir() / HERMES_HOME_NAME


def marker_file() -> Path:
    return install_dir() / MARKER_NAME


def log_file() -> Path:
    return install_dir() / 'logs' / 'backend-console.log'


def is_installed() -> bool:
    return marker_file().exists()


# ─── Backend process management ────────────────────────────────────────────

def _port_candidates() -> list:
    """Ports to try, in order. Port 80 first — some locked-down (bank) machines
    only allow 80/443, and on Windows a raw Winsock bind to 127.0.0.1:80 does
    NOT need admin (the <1024 restriction is a Unix rule; Windows only reserves
    low ports via http.sys/IIS). Skip 443 (implies TLS). HERMES_PORT env
    overrides everything."""
    env = os.environ.get('HERMES_PORT')
    if env:
        try:
            return [int(env)]
        except ValueError:
            pass
    return [80] + list(range(BASE_PORT, BASE_PORT + PORT_PROBE_RANGE))


def find_free_port() -> int:
    for port in _port_candidates():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return BASE_PORT


def dashboard_url(port: int) -> str:
    """URL for the dashboard. Omit :80 (default http port) so the link is clean."""
    if port == 80:
        return 'http://127.0.0.1'
    return f'http://127.0.0.1:{port}'


def port_responds(port: int) -> bool:
    import urllib.request
    import urllib.error
    try:
        urllib.request.urlopen(dashboard_url(port) + '/', timeout=2)
        return True
    except urllib.error.HTTPError:
        return True   # any HTTP response = server is up (auth redirects etc.)
    except Exception:
        return False


def start_selfhost_server(port: int) -> None:
    """Run the hermes dashboard server IN-PROCESS on a daemon thread.

    Self-hosting replaces the old "spawn a hidden subprocess and wait for the
    port" approach: the shell exe itself hosts the dashboard. Benefits: no port
    race between probe and bind, no stale backend.pid, no CREATE_NO_WINDOW
    quirks, and shutdown is just os._exit(0) (daemon threads die with the
    process). uvicorn's capture_signals() is a no-op off the main thread, so
    serving from a worker thread is safe.
    """
    home = hermes_home()
    os.environ['HERMES_HOME'] = str(home)
    # ALWAYS set HERMES_WEB_DIST — without it cmd_dashboard tries to rebuild
    # the SPA with npm, which does not exist on a portable install.
    web_dist = install_dir() / 'hermes_cli' / 'web_dist'
    if not web_dist.is_dir():
        web_dist = resource_path('hermes_cli') / 'web_dist'
    os.environ['HERMES_WEB_DIST'] = str(web_dist)

    import argparse

    from hermes_cli.main import cmd_dashboard

    args = argparse.Namespace(
        host='127.0.0.1',
        port=port,
        no_open=True,           # we open our own webview window
        status=False,
        stop=False,
        headless_backend=False,
        ssh_session_token_file=None,
        ssh_owner_nonce=None,
        insecure=False,
        open_profile='',
        skip_build=False,
    )
    cmd_dashboard(args)


# In-process dashboard server state (self-hosting).
_SERVER_ERROR: dict = {}
_SERVER_THREAD: dict = {'thread': None}


# ─── First-run installer ───────────────────────────────────────────────────


def ensure_selfhost() -> int:
    """Start the in-process dashboard server (self-hosting). Returns the port.

    Unlike the old spawn_backend() this does NOT exec a subprocess: the server
    runs on a daemon thread inside THIS process. Faster, no port race, no
    stale pidfile — and shutdown is a plain os._exit(0).
    """
    # Already serving? (another shell instance already bound the port)
    for port in _port_candidates():
        if port_responds(port):
            return port

    port = find_free_port()

    def _run():
        try:
            start_selfhost_server(port)
        except BaseException as exc:  # noqa: BLE001 — surface to GUI thread
            _SERVER_ERROR['exc'] = exc

    t = threading.Thread(target=_run, name='hermes-dashboard', daemon=True)
    _SERVER_THREAD['thread'] = t
    t.start()

    deadline = time.time() + BACKEND_READY_TIMEOUT
    while time.time() < deadline:
        if 'exc' in _SERVER_ERROR:
            raise RuntimeError(
                f'Dashboard server failed to start: {_SERVER_ERROR["exc"]}'
            ) from _SERVER_ERROR['exc']
        if port_responds(port):
            return port
        time.sleep(0.5)

    raise RuntimeError(
        f'Dashboard did not become ready within {BACKEND_READY_TIMEOUT}s — '
        f'check {log_file()}'
    )


def find_payload_zip() -> Path | None:
    """Payload next to the original exe, or bundled inside the exe."""
    candidates = [
        original_exe().parent / 'hermes-payload.zip',
        resource_path('hermes-payload.zip'),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def extract_payload(dest: Path, progress) -> bool:
    pz = find_payload_zip()
    if not pz:
        return False
    progress('กำลังแตกไฟล์ payload ...')
    with zipfile.ZipFile(pz) as zf:
        members = zf.namelist()
        for i, member in enumerate(members):
            zf.extract(member, dest)
            if i % 200 == 0:
                pct = int(i / max(len(members), 1) * 100)
                progress(f'กำลังแตกไฟล์ payload ... {pct}%')
    return True


def copy_engine_exe(dest: Path, progress) -> Path:
    """Copy the running exe (and its `_internal\` folder in onedir mode)
    into the install dir. Idempotent — skips if already in place."""
    src = original_exe()
    target = dest / engine_exe_name()

    # Onedir mode: the exe needs its `_internal\` sibling (all DLLs + PYZ).
    # Without it the exe won't start at all.
    src_internal = src.parent / '_internal'
    if src_internal.is_dir():
        tgt_internal = dest / '_internal'
        if not tgt_internal.exists():
            progress('กำลังคัดลอก runtime (onedir) ...')
            shutil.copytree(src_internal, tgt_internal, dirs_exist_ok=True)

    if src.resolve() == target.resolve() or not src.exists():
        return target
    progress('กำลังคัดลอก engine ...')
    shutil.copy2(src, target)
    return target


def copy_bundled_data(dest: Path, progress) -> None:
    """Fallback when no payload zip: copy bundled skills/plugins/web_dist."""
    for name in ('skills', 'optional-skills', 'plugins'):
        src = resource_path(name)
        if src.is_dir() and not (dest / name).exists():
            progress(f'กำลังคัดลอก {name} ...')
            shutil.copytree(src, dest / name, dirs_exist_ok=True)
    web_src = resource_path('hermes_cli') / 'web_dist'
    if web_src.is_dir():
        target = dest / 'hermes_cli' / 'web_dist'
        if not target.exists():
            progress('กำลังคัดลอก web dashboard ...')
            shutil.copytree(web_src, target, dirs_exist_ok=True)


def seed_homes(dest: Path, progress) -> None:
    """Create hermes-home with config/env templates."""
    progress('กำลังสร้าง hermes-home ...')
    home = dest / HERMES_HOME_NAME
    home.mkdir(parents=True, exist_ok=True)
    (home / 'sessions').mkdir(exist_ok=True)
    (home / 'memories').mkdir(exist_ok=True)
    (home / 'skills').mkdir(exist_ok=True)
    (home / 'logs').mkdir(exist_ok=True)

    env_tpl = resource_path('.env.example')
    if env_tpl.exists() and not (home / '.env').exists():
        shutil.copy2(env_tpl, home / '.env')
    cfg_tpl = resource_path('config.yaml.example')
    if not cfg_tpl.exists():
        cfg_tpl = resource_path('cli-config.yaml.example')
    if cfg_tpl.exists() and not (home / 'config.yaml').exists():
        shutil.copy2(cfg_tpl, home / 'config.yaml')


def create_desktop_shortcut(exe_path: Path, progress) -> None:
    if os.name != 'nt':
        return
    progress('กำลังสร้าง Desktop shortcut ...')
    ps = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=New-Object -ComObject WScript.Shell;"
        "$l=$s.CreateShortcut($d + '\\Hermes Agent.lnk');"
        f"$l.TargetPath='{exe_path}';"
        f"$l.WorkingDirectory='{install_dir()}';"
        "$l.Description='Hermes Agent - AI Assistant';"
        "$l.Save()"
    )
    try:
        subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       capture_output=True, timeout=30)
    except Exception:
        pass  # shortcut is nice-to-have, never block install


def run_first_install(progress) -> Path:
    dest = install_dir()
    dest.mkdir(parents=True, exist_ok=True)

    if not extract_payload(dest, progress):
        copy_bundled_data(dest, progress)

    exe_path = copy_engine_exe(dest, progress)
    seed_homes(dest, progress)
    create_desktop_shortcut(exe_path, progress)

    marker_file().write_text(json.dumps({
        'version': APP_VERSION,
        'installed_at': datetime.now().isoformat(),
        'install_dir': str(dest),
    }, indent=2))
    progress('ติดตั้งเสร็จเรียบร้อย ✔')
    return exe_path


# ─── GUI mode ──────────────────────────────────────────────────────────────

TRAY_ICON_SPEC = {
    # 16x16 "H" mark on rounded purple tile, scaled to 64 at runtime
    'grid': [
        '.XX.....XX.',
        '.XX.....XX.',
        '.XX.....XX.',
        '.XXXXXXXXXX.',
        '.XXXXXXXXXX.',
        '.XX.....XX.',
        '.XX.....XX.',
    ],
    'tile': (108, 92, 231),     # soft purple
    'mark': (255, 255, 255),
}


def make_tray_image():
    from PIL import Image, ImageDraw
    scale = 8
    size = 12 * scale
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, size - 1, size - 1],
                           radius=3 * scale, fill=TRAY_ICON_SPEC['tile'] + (255,))
    for y, row in enumerate(TRAY_ICON_SPEC['grid']):
        for x, cell in enumerate(row):
            if cell == 'X':
                draw.rectangle(
                    [x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1],
                    fill=TRAY_ICON_SPEC['mark'] + (255,))
    return img


LOADING_HTML = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  body {{ margin:0; height:100vh; display:flex; align-items:center; justify-content:center;
         background:#12121a; color:#e8e8f0; font-family:'Segoe UI',sans-serif; }}
  .card {{ text-align:center; }}
  h1 {{ font-weight:600; letter-spacing:.5px; margin:0 0 8px; }}
  #status {{ color:#9a9ab0; font-size:14px; min-height:20px; }}
  .spin {{ width:36px; height:36px; margin:18px auto; border:3px solid #2c2c3c;
          border-top-color:#6c5ce7; border-radius:50%; animation:sp 1s linear infinite; }}
  @keyframes sp {{ to {{ transform:rotate(360deg); }} }}
</style></head>
<body><div class="card">
  <h1>{APP_NAME}</h1>
  <div class="spin"></div>
  <div id="status">กำลังเริ่มต้น ...</div>
</div>
<script>
  window.setProgress = function(msg) {{
    document.getElementById('status').textContent = msg || '';
  }};
</script>
</body></html>"""

SHUTDOWN_DIALOG_HTML = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  body {{ margin:0; height:100vh; display:flex; align-items:center; justify-content:center;
         background:#1a1a24; color:#e8e8f0; font-family:'Segoe UI',sans-serif; }}
  .card {{ width:320px; text-align:center; }}
  h2 {{ font-size:17px; font-weight:600; margin:0 0 6px; }}
  p  {{ font-size:13px; color:#9a9ab0; margin:0 0 16px; }}
  input {{ width:100%; box-sizing:border-box; padding:9px 12px; font-size:14px;
          border:1px solid #3a3a4c; border-radius:8px; background:#12121a;
          color:#e8e8f0; outline:none; text-align:center; }}
  input:focus {{ border-color:#6c5ce7; }}
  .row {{ display:flex; gap:8px; margin-top:14px; }}
  button {{ flex:1; padding:9px 0; font-size:14px; border:0; border-radius:8px;
           cursor:pointer; }}
  .danger {{ background:#e74c3c; color:#fff; }}
  .ghost  {{ background:#2c2c3c; color:#e8e8f0; }}
  #err {{ color:#e74c3c; font-size:12px; min-height:16px; margin-top:8px; }}
</style></head>
<body><div class="card">
  <h2>ปิด Hermes Gateway?</h2>
  <p>พิมพ์ <b>shutdown</b> เพื่อยืนยันการปิดระบบ</p>
  <input id="word" placeholder="พิมพ์ shutdown ที่นี่" autofocus
         autocomplete="off" spellcheck="false">
  <div class="err" id="err"></div>
  <div class="row">
    <button class="ghost" onclick="cancel()">ยกเลิก</button>
    <button class="danger" onclick="confirmShutdown()">ปิดระบบ</button>
  </div>
</div>
<script>
  var input = document.getElementById('word');
  input.focus();
  input.addEventListener('keydown', function(e) {{
    if (e.key === 'Enter') confirmShutdown();
    if (e.key === 'Escape') cancel();
  }});
  async function confirmShutdown() {{
    var ok = await pywebview.api.try_shutdown(input.value);
    if (!ok) document.getElementById('err').textContent =
      'คำไม่ถูกต้อง — พิมพ์ shutdown เพื่อยืนยัน';
  }}
  async function cancel() {{
    await pywebview.api.cancel_shutdown();
  }}
</script>
</body></html>"""


class ShellState:
    def __init__(self):
        self.window = None        # main pywebview window
        self.dialog = None        # shutdown confirm dialog
        self.tray = None
        self.port = 0
        self.shutting_down = False
        self.installing = False


STATE = ShellState()


def gui_progress(msg: str) -> None:
    if STATE.window is not None:
        try:
            STATE.window.evaluate_js(f'window.setProgress({json.dumps(msg)})')
        except Exception:
            pass


class ShellApi:
    """JS bridge for the shutdown confirm dialog."""

    def try_shutdown(self, word: str) -> bool:
        if (word or '').strip().lower() != SHUTDOWN_WORD:
            return False
        threading.Thread(target=do_shutdown, daemon=True).start()
        return True

    def cancel_shutdown(self):
        try:
            if STATE.dialog is not None:
                STATE.dialog.hide()
            if STATE.window is not None:
                STATE.window.show()
        except Exception:
            pass
        return True


def do_shutdown() -> None:
    if STATE.shutting_down:
        return
    STATE.shutting_down = True
    # Self-hosted: the dashboard server runs on a daemon thread inside THIS
    # process, so no subprocess to kill — os._exit(0) tears everything down.
    if STATE.tray is not None:
        try:
            STATE.tray.stop()
        except Exception:
            pass
    os._exit(0)


def on_window_closing() -> bool:
    """Intercept X: show typed-confirmation dialog instead of closing."""
    if STATE.shutting_down:
        return True
    try:
        if STATE.dialog is not None:
            STATE.dialog.show()
        if STATE.window is not None:
            STATE.window.hide()
    except Exception:
        pass
    return False   # cancel the real close


def on_window_minimized():
    try:
        STATE.window.hide()
    except Exception:
        pass


def start_tray() -> None:
    import pystray
    from pystray import Menu, MenuItem

    def show(_item=None):
        try:
            STATE.window.show()
            STATE.window.restore()
        except Exception:
            pass

    def shutdown(_item=None):
        show()
        on_window_closing()

    menu = Menu(
        MenuItem(f'{APP_NAME} (เปิด UI)', show, default=True),
        Menu.SEPARATOR,
        MenuItem('ปิด Hermes Gateway ...', shutdown),
    )
    STATE.tray = pystray.Icon('hermes', make_tray_image(), APP_NAME, menu)
    STATE.tray.run_detached()


def _install_and_start_backend(progress) -> int:
    """Shared first-run install + self-hosted server start. Returns the port."""
    if STATE.installing:
        run_first_install(progress)
    progress('กำลังเริ่มต้น dashboard ...')
    return ensure_selfhost()


def _browser_fallback(exc: Exception) -> None:
    """pywebview failed (pythonnet/.NET backend is fragile in frozen apps).
    Fall back to opening the dashboard in the default browser so the app is
    still fully usable — tray + shutdown still work."""
    import webbrowser

    print(f'[hermes] native window failed ({exc}); falling back to browser')
    try:
        if STATE.installing:
            run_first_install(lambda m: None)
        STATE.port = ensure_selfhost()
        start_tray()
        webbrowser.open(dashboard_url(STATE.port))
        # Keep the process alive so the tray + backend stay up.
        while True:
            time.sleep(3600)
    except Exception as fatal:
        # Even the browser path failed — surface it.
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f'Hermes ไม่สามารถเริ่มได้:\\n\\n{fatal}\\n\\n'
                f'ดู log: {log_file()}',
                'Hermes Agent',
                0x10,
            )
        except Exception:
            pass
        raise


def run_gui() -> None:
    STATE.installing = not is_installed()

    try:
        import webview

        # Loading / installer window (also used as the main window shell)
        STATE.window = webview.create_window(
            APP_NAME,
            html=LOADING_HTML,
            width=1180, height=760,
            min_size=(720, 480),
            background_color='#12121a',
        )
        STATE.dialog = webview.create_window(
            'ยืนยันการปิด',
            html=SHUTDOWN_DIALOG_HTML,
            width=430, height=290,
            resizable=False,
            frameless=False,
            js_api=ShellApi(),
            hidden=True,
            on_top=True,
            background_color='#1a1a24',
        )

        STATE.window.events.closing += on_window_closing
        try:
            STATE.window.events.minimized += on_window_minimized
        except AttributeError:
            pass  # older pywebview: minimize-to-tray unavailable, harmless

        def bootstrap():
            """Runs on a worker thread once the GUI is up."""
            try:
                STATE.port = _install_and_start_backend(gui_progress)
                gui_progress('กำลังเปิด dashboard ...')
                STATE.window.load_url(dashboard_url(STATE.port))
                start_tray()
            except Exception as exc:
                try:
                    STATE.window.load_html(
                        f'<body style="background:#12121a;color:#e8e8f0;'
                        f'font-family:sans-serif;display:flex;align-items:center;'
                        f'justify-content:center;height:100vh"><div>'
                        f'<h2>เกิดข้อผิดพลาด</h2><pre>{exc}</pre></div></body>')
                except Exception:
                    pass

        webview.start(func=bootstrap)
    except Exception as exc:
        # pywebview import/start failed (e.g. pythonnet/.NET backend not
        # loadable in the frozen app). Degrade to a browser window so the
        # app still works end-to-end.
        _browser_fallback(exc)


# ─── Entry ─────────────────────────────────────────────────────────────────

def cli_passthrough() -> None:
    """Forward normal CLI args to the hermes CLI (chat, setup, model, ...)."""
    # Windowed exe (console=False): re-attach the parent console so
    # `hermes.exe chat "..."` from CMD/PowerShell shows output again.
    if os.name == 'nt':
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            ATTACH_PARENT_PROCESS = 0xFFFFFFFF
            if k32.AttachConsole(ATTACH_PARENT_PROCESS):
                sys.stdout = open('CONOUT$', 'w', encoding='utf-8', errors='replace')
                sys.stderr = open('CONOUT$', 'w', encoding='utf-8', errors='replace')
                sys.stdin = open('CONIN$', 'r', encoding='utf-8', errors='replace')
        except Exception:
            pass
    os.environ.setdefault('HERMES_HOME', str(hermes_home()))
    web_dist = install_dir() / 'hermes_cli' / 'web_dist'
    if web_dist.is_dir():
        os.environ.setdefault('HERMES_WEB_DIST', str(web_dist))
    sys.argv[0] = 'hermes'
    from hermes_cli.main import main as cli_main
    cli_main()


def main() -> None:
    if len(sys.argv) > 1:
        cli_passthrough()
        return
    run_gui()


if __name__ == '__main__':
    main()
