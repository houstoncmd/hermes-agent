#!/usr/bin/env python3
"""
Hermes Agent Portable — Qt window backend (Electron-like).

Why Qt/QWebEngineView instead of pywebview:
    pywebview on Windows relies on the SYSTEM WebView2 (Edge/Chromium) runtime
    being installed. On locked-down (bank) machines it often is not — the window
    simply never appears and the app degrades to a browser fallback. QWebEngineView
    bundles its OWN Chromium inside the exe, so the native window works with zero
    system dependencies — the "Electron-like, works entirely in one" property.

    Critically it also sidesteps the corporate PAC proxy: a real browser on those
    machines routes 127.0.0.1 through the proxy (which blocks localhost). We launch
    Chromium with --no-proxy-server so the embedded view reaches our loopback
    server directly.

This module is imported lazily by app_shell so a missing/broken PySide6 never
breaks the pywebview or browser fallback paths.
"""
import os
import threading

# Must be set BEFORE QApplication/QWebEngineProfile is created — Chromium reads
# it at process start. Forces DIRECT connections (no system/PAC proxy) so the
# embedded view can reach 127.0.0.1 on proxy-only bank networks.
os.environ.setdefault(
    'QTWEBENGINE_CHROMIUM_FLAGS',
    '--no-proxy-server --disable-features=Translate --no-first-run',
)


def qt_available() -> bool:
    """True if PySide6 + WebEngine can be imported on this machine."""
    try:
        import PySide6  # noqa: F401
        from PySide6 import QtWebEngineWidgets  # noqa: F401
        return True
    except Exception:
        return False


def _tray_icon_image():
    """Render the same 12x12 'H' mark app_shell uses, as a QImage."""
    from PySide6.QtGui import QColor, QImage, QPainter, QPen

    grid = [
        '.XX.....XX.',
        '.XX.....XX.',
        '.XX.....XX.',
        '.XXXXXXXXXX.',
        '.XXXXXXXXXX.',
        '.XX.....XX.',
        '.XX.....XX.',
    ]
    scale = 8
    size = 12 * scale
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(108, 92, 231)))
    p.setBrush(QColor(108, 92, 231))
    p.drawRoundedRect(0, 0, size - 1, size - 1, 3 * scale, 3 * scale)
    p.setBrush(QColor(255, 255, 255))
    for y, row in enumerate(grid):
        for x, cell in enumerate(row):
            if cell == 'X':
                p.drawRect(x * scale, y * scale, scale, scale)
    p.end()
    return img


class _ShutdownDialog:
    """Typed-confirmation dialog: must type SHUTDOWN_WORD to actually close."""

    def __init__(self, parent, word, on_confirm):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (QDialog, QLabel, QLineEdit, QPushButton,
                                       QVBoxLayout, QHBoxLayout, QWidget)

        self._word = word
        self._on_confirm = on_confirm
        dlg = QDialog(parent)
        dlg.setWindowTitle('ยืนยันการปิด')
        dlg.setFixedSize(420, 220)
        lay = QVBoxLayout(dlg)
        title = QLabel('ปิด Hermes Gateway?')
        title.setStyleSheet('font-size:16px;font-weight:600;')
        hint = QLabel(f'พิมพ์ <b>{word}</b> เพื่อยืนยันการปิดระบบ')
        hint.setStyleSheet('color:#9a9ab0;')
        self._input = QLineEdit()
        self._input.setPlaceholderText(f'พิมพ์ {word} ที่นี่')
        self._input.setEchoMode(QLineEdit.Normal)
        self._err = QLabel('')
        self._err.setStyleSheet('color:#e74c3c;font-size:12px;')
        row = QWidget()
        h = QHBoxLayout(row)
        cancel = QPushButton('ยกเลิก')
        confirm = QPushButton('ปิดระบบ')
        confirm.setStyleSheet('background:#e74c3c;color:#fff;')
        h.addWidget(cancel)
        h.addWidget(confirm)
        lay.addWidget(title)
        lay.addWidget(hint)
        lay.addWidget(self._input)
        lay.addWidget(self._err)
        lay.addWidget(row)

        cancel.clicked.connect(dlg.reject)
        confirm.clicked.connect(self._try)
        self._input.returnPressed.connect(self._try)
        self._dialog = dlg

    def _try(self):
        if (self._input.text() or '').strip().lower() == self._word:
            self._on_confirm()
        else:
            self._err.setText(f'คำไม่ถูกต้อง — พิมพ์ {self._word} เพื่อยืนยัน')

    def exec(self):
        self._dialog.exec()


def run_qt_gui(app_name, loading_html, shutdown_word, install_and_start,
               on_shutdown, progress=None):
    """Bring up the native Qt window, self-host, tray, and shutdown guard.

    Args:
        app_name: window/tray title.
        loading_html: HTML shown while the server boots.
        shutdown_word: word required in the close-confirm dialog.
        install_and_start(progress_cb) -> port: first-run install + start the
            in-process dashboard server, returns the bound port.
        on_shutdown(): kill/cleanup + os._exit — called when the user confirms.
        progress(msg): optional UI progress callback.
    Returns: never returns (runs the Qt event loop) unless startup fails, in
        which case it raises so app_shell can fall back.
    """
    from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
    from PySide6.QtGui import QAction, QIcon
    from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow,
                                   QSystemTrayIcon, QMenu, QVBoxLayout,
                                   QWidget, QHBoxLayout, QPushButton)
    from PySide6.QtWebEngineWidgets import QWebEngineView

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)   # tray keeps us alive when hidden

    state = {'port': 0, 'window': None, 'tray': None, 'confirming': False}

    class _Win(QMainWindow):
        def closeEvent(self, event):
            # Intercept X: show typed-confirm instead of closing.
            if state['confirming']:
                event.accept()
                return
            state['window'].hide()
            _show_confirm()
            event.ignore()

    # ── Loading page (shown until the server is up) ────────────────────────
    host = QWidget()
    v = QVBoxLayout(host)
    title = QLabel(app_name)
    title.setStyleSheet('font-size:20px;font-weight:600;color:#e8e8f0;')
    title.setAlignment(Qt.AlignCenter)
    status = QLabel('กำลังเริ่มต้น ...')
    status.setObjectName('status')
    status.setStyleSheet('color:#9a9ab0;')
    status.setAlignment(Qt.AlignCenter)
    retry = QPushButton('ลองใหม่')
    retry.setVisible(False)
    retry.setStyleSheet('padding:8px 18px;border-radius:8px;')
    v.addStretch()
    v.addWidget(title)
    v.addWidget(status)
    v.addWidget(retry, alignment=Qt.AlignCenter)
    v.addStretch()
    host.setStyleSheet('background:#12121a;')

    win = _Win()
    win.setWindowTitle(app_name)
    win.setCentralWidget(host)
    win.resize(1180, 760)
    state['window'] = win

    view = QWebEngineView()
    view.setStyleSheet('background:#12121a;')

    def _set_status(msg):
        status.setText(msg)
        if progress:
            progress(msg)

    # ── Server bootstrap on a worker thread ────────────────────────────────
    class _Boot(QThread):
        ready = Signal(int)
        failed = Signal(str)

        def run(self):
            try:
                port = install_and_start(_set_status)
                self.ready.emit(port)
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(str(exc))

    boot = _Boot()

    @Slot(int)
    def _on_ready(port):
        state['port'] = port
        win.setCentralWidget(view)
        scheme = 'http'
        netloc = '127.0.0.1' if port == 80 else f'127.0.0.1:{port}'
        view.load(f'{scheme}://{netloc}/')

    @Slot(str)
    def _on_failed(err):
        status.setText(f'เกิดข้อผิดพลาด: {err}')
        status.setStyleSheet('color:#e74c3c;')
        retry.setVisible(True)

    boot.ready.connect(_on_ready)
    boot.failed.connect(_on_failed)
    retry.clicked.connect(lambda: (retry.setVisible(False),
                                   status.setText('กำลังเริ่มต้น ...'),
                                   boot.start()))
    boot.start()

    # ── System tray ────────────────────────────────────────────────────────
    icon = QIcon(_tray_icon_image())
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip(app_name)
    menu = QMenu()

    def _show(_checked=False):
        win.show()
        win.raise_()
        win.activateWindow()

    def _show_confirm():
        state['confirming'] = True
        dlg = _ShutdownDialog(win, shutdown_word, on_shutdown)
        dlg.exec()
        state['confirming'] = False

    def _show_then_confirm():
        _show()
        QTimer.singleShot(300, _show_confirm)

    act_show = QAction(f'{app_name} (เปิด UI)')
    act_show.triggered.connect(_show)
    menu.addAction(act_show)
    menu.addSeparator()
    act_quit = QAction('ปิด Hermes Gateway ...')
    act_quit.triggered.connect(_show_then_confirm)
    menu.addAction(act_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: _show() if reason == QSystemTrayIcon.Trigger else None)
    tray.show()

    app.exec()
