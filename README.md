# AutoRefund-System-

A solution to long queues and wait times at shopping malls for returned products.

AutoRefund is a self-service return and refund kiosk. A customer scans the receipt, picks the item, puts it on a scale and has it photographed. The system checks the weight against the product's expected weight. Matching returns are approved automatically. Anything uncertain goes to an employee, who approves or rejects it. Every decision is recorded with its evidence.

The first prototype (Sheridan College capstone, 2026) ran on a **Raspberry Pi**. This repository contains the **Windows version**. The whole system runs on one Windows PC with a monitor, a USB camera, a USB barcode scanner and a USB scale, and no Raspberry Pi is needed.

---

## Contents

1. [How it works](#1-how-it-works)
2. [Architecture](#2-architecture)
3. [Requirements](#3-requirements)
4. [Installation (Windows)](#4-installation-windows)
5. [Configuration](#5-configuration)
6. [Connecting the hardware](#6-connecting-the-hardware)
7. [Starting AutoRefund](#7-starting-autorefund)
8. [Testing](#8-testing)
9. [Known limitations](#9-known-limitations)
10. [Raspberry Pi → Windows migration notes](#10-raspberry-pi--windows-migration-notes)

---

## 1. How it works

**Customer flow** (touch screen)

1. **Receipt**: scan the receipt barcode with the handheld scanner, hold it up to the camera, or type the number.
2. **Select item**: the receipt's items are listed. Items that were already returned can't be selected.
3. **Weigh and photo**: put the item on the scale. A live weight is shown next to the expected weight, and the camera takes a photo.
4. **Result**
   - *Approved* when the weight is within the product's tolerance (for example ±10 %).
   - *Pending review* when the weight is outside the tolerance. An employee then decides.
   - A second return of the same item from the same receipt is **blocked** and logged.

**Employee flow**: log in, then use the dashboard.

- **Pending refunds**: see the photo plus expected and measured weight, then approve or reject.
- **Refund logs**: full history, filterable by date.

## 2. Architecture

```
┌──────────── Windows PC ──────────────────────────────────────────────┐
│                                                                      │
│  Browser (Edge/Chrome, kiosk mode)                                   │
│   └─ self_refund_frontend  React 19 + Vite   http://127.0.0.1:5173  │
│        │  axios (REST)            ▲ keyboard input                   │
│        ▼                          │                                  │
│  self_refund_backend  Flask 3     │   http://127.0.0.1:5000/api      │
│   ├─ app/routes.py      business rules: receipts, weight tolerance,  │
│   │                     duplicate check, review, audit log           │
│   ├─ app/models.py      SQLAlchemy models ──► PostgreSQL (local)     │
│   └─ hardware/          hardware abstraction layer                   │
│        ├─ base.py            CameraDevice / ScaleDevice interfaces   │
│        ├─ camera_service.py  OpenCV (DirectShow / Media Foundation)──► USB camera
│        ├─ barcode.py         pyzbar (ZBar) / OpenCV fallback         │
│        ├─ scale_service.py   hidapi, USB HID postal scale ─────────► USB scale
│        └─ mock.py            SIMULATED devices (dev/tests only)      │
│                                                                      │
│  USB barcode scanner ──(acts as a keyboard)──► browser ──────────────┘
└──────────────────────────────────────────────────────────────────────┘
```

| Folder / file | Purpose |
|---|---|
| `self_refund_backend/` | Flask API, database models, Alembic migrations, hardware layer, tests |
| `self_refund_frontend/` | React kiosk UI (customer + employee) |
| `setup-autorefund.bat` | One-time install of Python/Node dependencies |
| `init-database.bat` | Creates the DB user/database, runs migrations, optional demo data |
| `check-hardware.bat` | Camera and scale diagnostics |
| `start-autorefund.bat` / `stop-autorefund.bat` | Start/stop the whole system |
| `push-to-github.bat` | One-time: turns the original capstone folder into this Git repository and pushes it (no force-push) |

**Database tables** (PostgreSQL): `products`, `transactions`, `transaction_items`, `refunds`, `staff`, `audit_logs`.

Photos are saved as JPEG files in `self_refund_backend/captures/`. Only the relative path `captures/<file>` is stored in `refunds.image_path`.

**Main API endpoints** (all under `/api`)

| Method | Path | Use |
|---|---|---|
| GET | `/health` | backend alive |
| GET | `/hardware/status` | shows which devices are real or mocked, and whether they're connected |
| GET | `/transactions/<receipt>` | receipt + items (with `is_refundable`) |
| GET | `/products/lookup/<barcode>` | product info |
| GET | `/scale/live`, `/scale/read` | weight in grams (`503` if the scale is unavailable) |
| GET | `/camera/stream`, `/camera/preview`, `/camera/health` | live MJPEG / single frame / status |
| POST | `/camera/capture` | save a photo, returns `image_path` |
| GET | `/receipt/scan` | decode a barcode from the camera |
| POST | `/refunds/start` | create a refund (weight check + duplicate check) |
| GET | `/refunds/pending`, `/refunds/logs` | employee views |
| POST | `/refunds/<id>/approve`, `/refunds/<id>/reject` | employee decision |
| POST | `/staff/login` | employee login |
| GET | `/captures/<file>` | evidence image |

## 3. Requirements

**Software**

| | Version | Notes |
|---|---|---|
| Windows | 10 or 11, 64-bit | |
| Python | 3.11 – 3.13 (64-bit) | tick *Add python.exe to PATH* |
| Node.js | 20 LTS or newer (22 recommended) | includes npm |
| PostgreSQL | 14 or newer | [EDB installer](https://www.postgresql.org/download/windows/), remember the `postgres` password |
| Visual C++ 2013 Redistributable (x64) | | only for **camera** barcode scanning with pyzbar ([Microsoft download page](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist)) |
| Microsoft Edge or Chrome | | the kiosk display |

**Hardware**

| Device | Used in the prototype | Interface on Windows |
|---|---|---|
| USB webcam | yes | UVC webcam through DirectShow / Media Foundation (no driver needed) |
| USB barcode scanner | new (the Pi read barcodes through the camera only) | **USB HID keyboard mode** (the factory default on almost all scanners) |
| USB scale | DYMO M10 (VID `0x0922`, PID `0x8003`) | USB HID Point-of-Sale scale through `hidapi` (no driver needed) |
| Monitor (touch screen recommended) | yes | any |

## 4. Installation (Windows)

```bat
REM 1. get the code
git clone https://github.com/Ajayk909/AutoRefund-System-.git
cd AutoRefund-System-

REM 2. install Python + Node dependencies, create self_refund_backend\.env
setup-autorefund.bat

REM 3. edit self_refund_backend\.env (at least the DATABASE_URL password)
notepad self_refund_backend\.env

REM 4. create the database + tables (+ optional demo data)
init-database.bat
```

`init-database.bat` can create the `refund_user` login and `refund_kiosk` database for you (it asks for the `postgres` password). The password you choose must match the one in `DATABASE_URL`.

> **Coming from the Raspberry Pi folder?** Its `self_refund_frontend\node_modules` holds Linux ARM binaries, and `self_refund_backend\.venv` is a Linux environment. `setup-autorefund.bat` replaces both: `npm ci` reinstalls `node_modules`, and the old `.venv` is renamed to `.venv-raspberrypi-old`.

**Demo data**: the `seed.py` step **deletes all existing data**, then loads 3 products, receipt `RCP-1001` and employee `admin1` / `admin123`. Change or remove that account before any real use.

<details>
<summary>Manual installation (without the .bat files)</summary>

```bat
cd self_refund_backend
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env
psql -U postgres -h localhost -v db_password=YOUR_PASSWORD -f scripts\create_database.sql
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python seed.py

cd ..\self_refund_frontend
npm ci
```
</details>

## 5. Configuration

All backend settings live in `self_refund_backend/.env`. See `.env.example` for the full list. `.env` is git-ignored, so never commit it.

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | – | `postgresql://refund_user:<password>@localhost:5432/refund_kiosk` |
| `FLASK_HOST` / `FLASK_PORT` | `127.0.0.1` / `5000` | Use `0.0.0.0` only if other PCs must reach the API |
| `FLASK_DEBUG` | `false` | Never `true` on a kiosk (the debugger allows remote code execution) |
| `CORS_ORIGINS` | `*` | e.g. `http://localhost:5173,http://127.0.0.1:5173` |
| `KIOSK_ID` | `KIOSK-001` | stored on every refund |
| `CAPTURE_DIR` / `LOG_DIR` | `captures` / `logs` | relative to `self_refund_backend\` or absolute (`D:\AutoRefund\captures`) |
| `HARDWARE_MODE` | `real` | `real` or `mock` (simulated devices, **development only**) |
| `CAMERA_MODE` / `SCALE_MODE` | = `HARDWARE_MODE` | override per device |
| `CAMERA_INDEX` | empty (auto 0–3) | Windows camera number |
| `CAMERA_BACKEND` | `auto` | `auto` (DirectShow → Media Foundation), `dshow`, `msmf`, `any` |
| `CAMERA_WIDTH` / `CAMERA_HEIGHT` | `640` / `480` | |
| `SCALE_VENDOR_ID` / `SCALE_PRODUCT_ID` | `0x0922` / `0x8003` | USB IDs of the scale |
| `SCALE_READ_TIMEOUT_MS` | `2000` | |
| `MOCK_SCALE_GRAMS` | `250` | weight reported by the mock scale |

Per-product weight tolerance is stored in the database (`products.weight_tolerance_percent`), not in code.

Frontend: only if the backend is **not** at `http://127.0.0.1:5000`, create `self_refund_frontend/.env.local` with `VITE_API_ORIGIN=http://<host>:5000`.

## 6. Connecting the hardware

Plug everything in, then run **`check-hardware.bat`**.

### Barcode scanner (USB HID keyboard)

1. Plug in the scanner. Windows installs it as a keyboard automatically.
2. Open Notepad and scan a barcode. The code should appear, followed by a new line. If there is no new line, program the scanner's **"Enter/CR suffix"** using the setup barcodes in its manual.
3. Make sure the scanner's keyboard layout matches Windows (usually *US English*). Otherwise characters like `-` can come out wrong.
4. On the receipt screen, a scan works whether or not the text box has focus. The UI detects the fast keystroke burst (`src/hooks/useBarcodeScanner.js`).

Scanners that only work in serial/COM (RS-232/USB-CDC) mode are **not** supported. Switch the scanner to USB HID keyboard mode using its manual.

### Camera

1. Plug in the webcam and close any app that uses it (Camera, Teams, Zoom).
2. Go to Windows **Settings → Privacy & security → Camera** and turn on *Camera access* and *Let desktop apps access your camera*.
3. `check-hardware.bat` tries indexes 0–3 with DirectShow and Media Foundation and saves a test photo to `self_refund_backend\captures\`.
4. If the PC has a built-in camera too, set `CAMERA_INDEX` to the USB camera's index.
5. The camera also reads receipt barcodes. Code-128 receipts (such as `RCP-1001`) need pyzbar and the VC++ 2013 runtime. Without them, the camera can only read EAN/UPC codes. The handheld scanner is the recommended method.

### Scale (USB HID)

1. Plug in the scale and switch it on. Windows lists it under *Human Interface Devices*. No driver is needed.
2. `check-hardware.bat` (or `.venv\Scripts\python test_scale.py --list`) lists all HID devices. Find the scale's VID/PID and set `SCALE_VENDOR_ID` / `SCALE_PRODUCT_ID` if they differ from DYMO M10 (`0x0922` / `0x8003`; the DYMO M25 is `0x8004`).
3. `test_scale.py` prints 10 readings. Put a known item on the scale and compare.
4. Supported report format: 6-byte HID POS scale report (status, unit, exponent, weight). DYMO M5/M10/M25 use it. Grams, kg, oz and lb are converted to grams.
5. DYMO scales switch off automatically after a few minutes. Disable auto-off if the model allows it. Otherwise the kiosk shows "Scale not responding" until someone presses the power button.

## 7. Starting AutoRefund

| Command | What it does |
|---|---|
| `start-autorefund.bat` | starts the backend, builds the UI, serves it at <http://127.0.0.1:5173> and opens the browser |
| `start-autorefund.bat kiosk` | same, but in full-screen Microsoft Edge kiosk mode (Alt+F4 to exit) |
| `start-autorefund.bat dev` | Vite dev server with hot reload (for development) |
| `stop-autorefund.bat` | closes the backend and frontend windows |

Logs: `self_refund_backend\logs\autorefund.log` (rotated at 2 MB).

**Start automatically at logon (demo kiosk)**: press `Win+R`, type `shell:startup`, and put a shortcut to `start-autorefund.bat kiosk` in that folder.

**Development without hardware**: set `HARDWARE_MODE=mock` in `.env`. The camera then returns a frame stamped **MOCK CAMERA**, and the scale returns `MOCK_SCALE_GRAMS`. The backend logs a warning, and `/api/hardware/status` reports `"mock": true`. Never process real refunds in mock mode.

## 8. Testing

**Automated backend tests** use a real PostgreSQL database and mock hardware:

```bat
cd self_refund_backend
REM use an EMPTY throw-away database - its tables are dropped and recreated
psql -U postgres -h localhost -c "CREATE DATABASE refund_kiosk_test OWNER refund_user"
set TEST_DATABASE_URL=postgresql://refund_user:YOUR_PASSWORD@localhost:5432/refund_kiosk_test
.venv\Scripts\python -m pytest
```

Without `TEST_DATABASE_URL`, only the hardware unit tests run (scale packet decoding, camera and scale failure handling, barcode decoding).

Covered scenarios:

- normal return → approved, with a photo
- tolerance boundary
- weight mismatch → pending review
- duplicate return blocked and logged
- product not on the receipt
- invalid weight
- fake image path not stored
- employee approve and reject
- staff login
- camera failure → 503 with a friendly message
- scale failure → 503
- camera receipt scan
- log date filter

**Frontend**

```bat
cd self_refund_frontend
npm run build
npm run lint
```

`npm run lint` still reports the issues the original prototype already had (mostly `react-hooks/purity` for the `Math.random()` background particles). The build works.

**Manual hardware test checklist** (run on the kiosk PC):

- [ ] `check-hardware.bat`: camera photo saved, scale readings correct (compare with a known weight in g and in oz mode)
- [ ] Scan `RCP-1001` with the handheld scanner, once with the text box focused and once after tapping elsewhere
- [ ] Hold a printed receipt barcode in front of the camera (auto-scan)
- [ ] Weigh screen: live stream visible, weight updates, *Capture Now* shows the photo
- [ ] Submit a matching item → approved. Submit a wrong weight → pending. Try the same item again → blocked.
- [ ] Employee: pending list shows the photo, approve/reject works, logs show the history
- [ ] Unplug the camera or scale during use → friendly message. Plug it back in → it recovers.

## 9. Known limitations

- **Employee API endpoints are not authenticated on the server.** `/refunds/pending`, `/refunds/logs`, approve/reject and `/captures/*` can be called without logging in. The login only stores the staff user in the browser's `localStorage`, so hiding the pages is not real protection. The Pi prototype had the same problem. Add token or session authentication before any deployment outside a demo. Keep `FLASK_HOST=127.0.0.1` so only the kiosk PC can reach the API.
- **Staff decisions are not linked to a staff member.** `staff_id` is `NULL` for the same reason.
- **Development server.** The backend uses Flask's built-in server, which is fine for a single kiosk demo. For production, use a WSGI server such as `waitress`.
- **Dates.** Refund times are stored in UTC without a timezone marker, so the logs page may show them offset from local time.
- **Weight is the only automatic check.** Photos are stored as evidence, but no computer-vision check is done yet.
- **Camera scanning of Code-128 receipts** needs pyzbar and the VC++ 2013 runtime.
- **Unsupported scales.** Only USB HID POS scales are supported. Serial/RS-232 scales would need a new `ScaleDevice` implementation in `hardware/`.
- **Scale buffering.** If a scale sends reports only when the weight changes, the last value is reused until a new report arrives.
- **Tested on Linux only so far.** The Windows `.bat` scripts and the real camera and scale code have **not been run on Windows or with the physical devices yet**. See the table below.

### Test status of this migration

| Area | Status | How |
|---|---|---|
| Backend API and business rules (15 workflow tests) | PASS | pytest against PostgreSQL 16 on Linux, mock hardware |
| Scale report decoding, error handling, camera-absent handling, barcode decoding (12 tests) | PASS | pytest (no devices) |
| Alembic migrations + `create_database.sql` + seed | PASS | fresh PostgreSQL 16 database |
| Frontend production build | PASS | `vite build` |
| Customer + employee flow in a real browser (HID-style keystroke scan, approve, pending, duplicate, scale-offline message) | MOCKED | Playwright + Chromium, mock camera/scale |
| All Python packages have Windows x64 wheels (Python 3.12/3.13) | PASS | `pip download --platform win_amd64` |
| `.bat` scripts on Windows | NOT TESTED | needs a Windows PC |
| USB webcam through DirectShow/MSMF | NOT TESTED | needs physical hardware on Windows |
| DYMO scale through hidapi on Windows | NOT TESTED | needs physical hardware |
| Handheld USB barcode scanner | NOT TESTED | needs physical hardware (keyboard input was simulated in the browser) |
| pyzbar DLL loading on Windows | NOT TESTED | needs Windows |

## 10. Raspberry Pi → Windows migration notes

**What the Pi prototype depended on, and what replaced it**

| Pi prototype | Windows version |
|---|---|
| `cv2.VideoCapture("/dev/video0", cv2.CAP_V4L2)` (V4L2 and `/dev/video*` exist only on Linux) | `hardware/camera_service.py`: numeric index with DirectShow → Media Foundation (V4L2 is still used automatically on Linux) |
| `USBCameraService("/dev/video0")` hard-coded in `routes.py` | `CAMERA_INDEX` / `CAMERA_BACKEND` in `.env`, created through `hardware.get_camera()` |
| Receipt barcodes read **only** by the camera (pyzbar) | Camera scanning kept, plus USB HID keyboard scanner support in the UI, plus an OpenCV decoder fallback |
| DYMO scale through `hidapi` (Linux hidraw); VID/PID hard-coded; errors silently returned `0 g` | Same `hidapi` package (Windows HID API). VID/PID configurable. Errors are reported (`503`, "Scale not responding"). Status byte handled (zero, motion, over-weight). Signed exponent bug fixed (`>= 128`). |
| `captures/` relative to the current working directory | `CAPTURE_DIR` resolved relative to `self_refund_backend\`; filenames made unique |
| `app.run(host="0.0.0.0", debug=True)` | `FLASK_HOST`/`FLASK_PORT`/`FLASK_DEBUG`, default `127.0.0.1` with debug off |
| DB password hard-coded in `alembic.ini` | Alembic reads `DATABASE_URL` from `.env` |
| Linux `.venv` (`/home/aman/...`, `bin/`) | recreated by `setup-autorefund.bat`; the old one is renamed `.venv-raspberrypi-old`, not deleted |
| `requirements.txt` missing opencv, pyzbar, hidapi, numpy | pinned, with Windows wheels verified |
| Frontend: `127.0.0.1:5000` / `localhost:5000` / `window.location.hostname:5000` spread over 4 files | one setting, `VITE_API_ORIGIN` (`src/services/api.js`) |
| Frontend sent `image_path: "mock_images/test.jpg"` when no photo was taken, and the backend stored it as if it were real evidence | sends `null`; the backend only stores paths of files that exist, and the audit log records `image_captured` |
| `print()` debugging | rotating log file plus console; duplicate attempts, staff decisions, failed logins and hardware errors are logged |
| `seed.py` wiped the database without asking | asks for confirmation (`--yes` to skip) |

**No Raspberry Pi specifics found** for GPIO, `picamera`, serial `ttyUSB`/`ttyACM`, systemd/cron, shell scripts, or Pi IP addresses/hostnames.

**Unchanged**: the database schema and migrations, the models, the refund decision rules (tolerance %, approve vs. pending, duplicate check), the API response formats, and all UI pages and styles.

**Moving existing data from the Pi** (optional). The Pi's refund history lives in the Pi's PostgreSQL, not in this repository.

```bash
# on the Pi
pg_dump -U refund_user -h localhost -Fc refund_kiosk > refund_kiosk.dump
```

```bat
REM on Windows, after init-database.bat created an EMPTY database (skip the demo data)
pg_restore -U refund_user -h localhost -d refund_kiosk --clean --if-exists refund_kiosk.dump
```

Then copy the Pi's `self_refund_backend/captures/` folder into `self_refund_backend\captures\` so the evidence photos still resolve.
