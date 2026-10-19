# คู่มือ Build & ใช้งาน Hermes Portable (GUI Shell) บน Windows

> สร้าง `hermes.exe` ไฟล์เดียว double-click ครั้งแรก = ติดตั้งเอง,
> ครั้งถัดไป = เปิด UI ตรง ๆ, gateway อยู่ที่ taskbar (tray),
> ปิดต้องพิมพ์ `shutdown` ยืนยัน

---

## 1. เงื่อนไขพรีเรค (Build Machine)

ต้อง build **บน Windows 10/11 64-bit** (PyInstaller ไม่ cross-compile):

| สิ่งที่ต้องมี | ตรวจสอบ / ติดตั้ง |
|---|---|
| Python 3.11+ | `python --version` (ติ๊ก "Add to PATH" ตอนติดตั้ง) |
| Git | `git --version` |
| Node.js 18+ (สำหรับ build web UI) | `node --version` |
| WebView2 Runtime | มีติดมากับ Win10/11 อยู่แล้ว (ถ้า UI ว่างเปล่าค่อยลงเพิ่ม) |

---

## 2. Build Step-by-Step

### 2.1 Clone + เตรียมสภาพแวดล้อม

```powershell
git clone https://github.com/houstoncmd/hermes-agent -b feature/portable-build
cd hermes-agent

python -m venv .venv
.venv\Scripts\activate

# ติดตั้ง dependencies ของ hermes + เครื่องมือ build + GUI deps
pip install -e .
pip install pyinstaller pywebview pystray pillow
```

### 2.2 Build Web UI (dashboard assets)

`hermes.exe` ต้องมี `hermes_cli/web_dist` (ไฟล์ dashboard) ถ้าไม่มี UI จะ 404:

```powershell
# IMPORTANT: repo นี้เป็น npm workspace monorepo — package-lock.json และ
# toolchain (tsc/vite) อยู่ที่ ROOT และถูก hoist ไปที่ root\\node_modules\\.bin
# ห้าม cd web แล้ว npm ci (จะไม่เจอ tsc) ให้รันที่ ROOT แบบนี้:
if (-not (Test-Path hermes_cli\\web_dist)) {
    npm ci --include=dev --workspace web --include-workspace-root
    npm run build --workspace web   # output ไปที่ hermes_cli\\web_dist
}
```

> ถ้า `npm ci` fail (lockfile drift บน fork/WIP) ให้ใช้
> `npm install --no-save --include=dev --workspace web --include-workspace-root`
> แล้วค่อย `npm run build --workspace web`
> ถ้าข้ามขั้นตอนนี้ ตัว dashboard จะพยายาม build เองตอนรันครั้งแรก
> (ต้องมี Node) หรือไม่ก็แสดง 404 — แนะนำอย่าข้าม

### 2.3 Build ทุกอย่างในคำสั่งเดียว

```powershell
python portable\build.py
```

สคริปต์จะ:
1. ดาวน์โหลด wheels สำหรับ offline (`--include-messaging` ถ้าต้องการ Telegram/Discord/Slack)
2. Build `hermes.exe` ด้วย PyInstaller (`portable\hermes.spec`)
3. สร้าง `hermes-payload.zip` (skills + plugins + web_dist + wheels)
4. แพ็กเป็น distributable zip พร้อม README.txt

**ไฟล์เอาต์พุต:**

```
dist\
├── hermes-portable-win64-v0.16.0-YYYYMMDD.zip   ← ส่งไฟล์นี้
│   ├── hermes.exe           (~80–100 MB, self-installing GUI)
│   ├── hermes-payload.zip   (skills + plugins + wheels)
│   └── README.txt
```

**Flag เสริม:**

| Flag | ใช้เมื่อไหร่ |
|---|---|
| `--skip-exe` | build payload อย่างเดียว (รันบน Linux/Mac ได้) |
| `--skip-payload` | build exe อย่างเดียว |
| `--include-messaging` | ต้องการ deps พวก Telegram/Discord/Slack |
| `--no-cleanup` | เก็บ `build\` ไว้ดีบัก |

---

## 3. ทดสอบ (Test Machine ที่สะอาด)

> แนะนำใช้ VM หรือเครื่องที่ไม่มี Python — เพื่อให้แน่ใจว่า
> exe ทำงานจริงแบบไม่พึ่ง Python ที่ติดตั้งไว้

1. ก๊อป zip ไปเครื่อง target แล้ว extract ที่โฟลเดอร์ใดก็ได้
2. **ห้ามย้าย `hermes.exe` ออกจาก `hermes-payload.zip`** (ต้องอยู่โฟลเดอร์เดียวกันตอน first run)
3. **Double-click `hermes.exe`** → ครั้งแรกมันจะติดตั้งเอง:
   - แตก payload + คัดลอก engine → `D:\hermes` (หรือ `%LOCALAPPDATA%\Hermes` ถ้าไม่มี D:)
   - สร้าง shortcut **"Hermes Agent"** บน Desktop
   - seed `hermes-home` (config + .env template)
   - เสร็จแล้วเปิด gateway + UI ให้เอง
4. ใส่ API key ครั้งเดียว: แก้ `D:\hermes\hermes-home\.env`
   ```
   OPENROUTER_API_KEY=***
   ```
   (หรือ ANTHROPIC / GOOGLE / DEEPSEEK)
5. Restart จาก tray (เมนู → ปิด แล้ว double-click Desktop icon)

### พฤติกรรมที่ต้องทดสอบ

| การกระทำ | ผลที่ควรเป็น |
|---|---|
| Double-click Desktop icon | เปิด UI (dashboard) ตรง ๆ |
| Tray icon (มุมล่างขวา) | มี "เปิด UI" / "ปิด Hermes Gateway ..." |
| กด minimize | หน้าต่างหายไป tray (process ยังอยู่) |
| คลิก tray / เลือกเปิด UI | หน้าต่างกลับมา |
| กดปิด (X) | popup ให้พิมพ์ `shutdown` |
| พิมพ์ `shutdown` | gateway หยุด + app ออก |
| พิมพ์อย่างอื่น / ยกเลิก | gateway ยังทำงานต่อ |
| เปิด CMD รัน `D:\hermes\hermes.exe chat -q "hi"` | ใช้ CLI ได้ปกติ |

---

## 4. Troubleshooting

| อาการ | สาเหตุ / วิธีแก้ |
|---|---|
| SmartScreen "Windows protected your PC" | กด **More info → Run anyway** (exe ไม่มี code sign) |
| UI ว่างเปล่า / ไม่ขึ้น | ติดตั้ง **Microsoft Edge WebView2 Runtime** |
| "API key not set" | แก้ `.env` ใน `hermes-home` แล้ว restart จาก tray |
| UI ค้างตอน "กำลังเชื่อมต่อ gateway" | ดู log: `D:\hermes\logs\backend-console.log` |
| Port 9119 ถูกใช้ | shell จะเลือก port ถัดไปให้เอง (9119–9128) |
| อยากเริ่มใหม่สะอาด | ลบ `D:\hermes` + Desktop shortcut แล้ว double-click exe ใหม่ |

---

## 5. Uninstall

ลบ `D:\hermes` (หรือ `%LOCALAPPDATA%\Hermes`) และ Desktop shortcut "Hermes Agent"

---

## 6. สถาปัตยกรรม (สำหรับ dev)

```
hermes.exe  (PyInstaller onefile, entry = portable/app_shell.py)
│
├── ไม่มี args (double-click) ──► GUI mode
│     ├─ ตรวจ marker .installed
│     ├─ ยังไม่ติดตั้ง ──► first-run installer (แตก payload + shortcut)
│     ├─ spawn backend: <exe> __backend__ <port>  (hidden, CREATE_NO_WINDOW)
│     ├─ เปิด pywebview → http://127.0.0.1:<port>
│     ├─ tray (pystray) + minimize-to-tray
│     └─ close(X) → dialog พิมพ์ "shutdown" → kill backend tree + exit
│
├── __backend__ [port] ──► รัน `hermes dashboard --no-open` (ซ่อน console)
│
└── มี args อื่น ──► CLI passthrough (chat/setup/model/...)
      (Windows: re-attach parent console ด้วย AttachConsole)
```

- **Install dir**: `D:\hermes` → fallback `%LOCALAPPDATA%\Hermes`
- **HERMES_HOME**: `<install_dir>\hermes-home` (sessions, memories, .env)
- **Backend log**: `<install_dir>\logs\backend-console.log`
- **PID file**: `<install_dir>\backend.pid`
- **Test logic (Linux ได้)**: `python portable/test_app_shell.py`
