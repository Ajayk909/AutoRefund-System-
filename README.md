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
2. **Select item**: the receipt's items are listed with how many can still be returned. Items already returned, waiting for review, or outside the return window (default 30 days) can't be selected, and the screen says why.
3. **Weigh and photo**: put the item on the scale. A live weight is shown for guidance and the camera takes a photo. When the customer submits, **the kiosk agent reads the scale itself** and sends the reading and photo to the Core API; the browser never sends the weight.
4. **Result**
   - *Approved* when the weight is within the product's tolerance (for example ±10 %) **and** a photo was captured.
   - *Pending review* when the weight is outside the tolerance or no photo could be taken. An employee then decides.
   - Returning more units than were bought is **blocked** and logged. A rejected unit may be tried again once (configurable).
   - *Approved* does not mean the money has moved: there is no payment integration yet.
   - If the returns service can't be reached, the screen says **nothing has been refunded** and the customer can try again. A retry never creates a second return.

**Employee flow**: log in (server-side session), then use the dashboard.

- **Pending refunds**: see why the return was flagged, the photo, and expected vs measured weight, then approve or reject (with a reason). The employee's name is recorded.
- **Refund logs**: full history, filterable by date. For an approved return, issue the refund at the POS and record its reference with **Mark refunded at POS** (`approved → refunded`).

**Return states**: `pending_review → approved | rejected`, `approved → refunded`. Any other change is refused by the server.

## 2. Architecture

Three programs run on the kiosk PC. **Read [`docs/architecture.md`](docs/architecture.md) before changing the code.**

```
┌───────────────────────────── Windows kiosk PC ──────────────────────────────┐
│                                                                             │
│  Browser: React kiosk UI (self_refund_frontend)   http://127.0.0.1:5173     │
│     │ customer screens                     │ employee screens               │
│     ▼                                      ▼                                │
│  Kiosk agent (kiosk_agent)          Core API (self_refund_backend)          │
│  http://127.0.0.1:5100/api  ─────►  http://127.0.0.1:5000/api  ──► PostgreSQL│
│   • camera, DYMO scale,     device   • receipts, catalog, tenants           │
│     barcode decoding          key    • return rules, state machine          │
│   • kiosk identity + key             • staff login, review, audit           │
│   • SQLite: session, outbox          • evidence photos                      │
│     │ USB                                                                   │
│     ▼                                                                       │
│  webcam · DYMO M10       USB barcode scanner ──(keyboard)──► browser        │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Part | Role |
|---|---|
| **React UI** | Screens only. Customer screens talk to the kiosk agent; employee screens talk to the Core API. It is never trusted for weight, identity or decisions. |
| **Kiosk agent** | Owns the hardware and the kiosk's credential. Reads the authoritative weight, takes the photo, sends them to the Core API, and records each attempt in a local outbox. Never approves or refunds anything itself. |
| **Core API** | Makes every decision: which kiosk/store/retailer is calling, receipt and product validation, eligibility, quantity, duplicates, idempotency, weight check, state machine, staff authorization, audit. |

| Folder / file | Purpose |
|---|---|
| `self_refund_backend/` | Core API: Flask app, database models, Alembic migrations, tests |
| `kiosk_agent/` | Windows kiosk agent: hardware layer, local store, Core API client, tests |
| `self_refund_frontend/` | React kiosk UI (customer + employee) |
| `setup-autorefund.bat` | One-time install of the Core API, kiosk agent and UI |
| `init-database.bat` | Creates the DB user/database, runs migrations, optional demo data, kiosk agent key |
| `check-hardware.bat` | Camera and scale diagnostics (uses the kiosk agent) |
| `start-autorefund.bat` / `stop-autorefund.bat` | Start/stop all three programs |
| `self_refund_backend/manage_tenancy.py` | List / add retailers, stores, kiosks; issue / revoke kiosk agent keys |
| `docs/architecture.md` | Roles, boundary, failure behaviour, tenant model, migrations, deferred work |
| `push-to-github.bat` | One-time: turns the original capstone folder into this Git repository and pushes it (no force-push) |

**Tenants**: data is organised as **Retailer → (optional store groups) → Store → Kiosk**. All retailers share one database; every tenant-owned row carries `retailer_id`, and composite foreign keys stop data of two retailers from being linked. Barcodes and receipt numbers are unique **per retailer**.

**Kiosk identity**: the kiosk agent proves which kiosk it is with a **development key** (`KIOSK_DEV_KEY` in `kiosk_agent\.env`). The Core API decides the kiosk, store and retailer from that key alone. Development keys are temporary: they expire, can be revoked, and only work while the Core API listens on `127.0.0.1`.

**Database tables** (PostgreSQL): `retailers`, `store_groups`, `stores`, `kiosks`, `kiosk_credentials`, `products`, `product_identifiers`, `transactions`, `transaction_items`, `refunds` (returns), `staff`, `staff_sessions`, `audit_logs`.

**Photos**: taken by the agent, uploaded to the Core API, and stored as `self_refund_backend\captures\evidence_<random>.jpg` with a SHA-256 hash. The agent deletes its local copy once the Core API has answered.

**Kiosk agent endpoints** (for the customer screens, `http://127.0.0.1:5100/api`)

| Method | Path | Use |
|---|---|---|
| GET | `/health`, `/kiosk/status` | agent alive; identity, Core API reachability, hardware, outbox |
| GET | `/transactions/<receipt>`, `/products/lookup/<barcode>` | receipt / product (from the Core API) |
| POST | `/refunds/start` | submit a return (agent reads scale + photo) |
| GET | `/scale/live`, `/scale/read` | weight for display |
| GET | `/camera/stream`, `/camera/preview`, `/camera/health`; POST `/camera/capture` | camera |
| GET | `/receipt/scan`, `/hardware/status` | camera barcode scan, device diagnostics |
| POST | `/session/end`, `/outbox/reconcile` | end session; check unconfirmed submissions |

**Core API endpoints** (`http://127.0.0.1:5000/api`)

| Method | Path | Use |
|---|---|---|
| GET | `/health` | Core API alive |
| GET | `/kiosk/me`, `/kiosk/receipts/<receipt>`, `/kiosk/products/<barcode>`, `/kiosk/returns/by-key/<key>` | **kiosk agent only** (device key) |
| POST | `/kiosk/returns` | **kiosk agent only**: create a return (metadata + photo, idempotency key) |
| POST | `/staff/login`, `/staff/logout`; GET `/staff/me` | employee session |
| GET | `/refunds/pending`, `/refunds/logs` | employee views (own retailer / store only) |
| POST | `/refunds/<id>/approve`, `/refunds/<id>/reject`, `/refunds/<id>/mark-refunded` | employee decisions |
| GET | `/refunds/<id>/image`, `/captures/<file>` | evidence image (staff, same tenant) |

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

REM 2. install the Core API, kiosk agent and UI; creates both .env files
setup-autorefund.bat

REM 3. edit self_refund_backend\.env (at least the DATABASE_URL password)
notepad self_refund_backend\.env

REM 4. tables, optional demo data, and the kiosk agent's key
init-database.bat

REM 5. check camera/scale settings for the agent
notepad kiosk_agent\.env
```

`init-database.bat` can create the `refund_user` login and `refund_kiosk` database for you (it asks for the `postgres` password). The password you choose must match the one in `DATABASE_URL`. At the end it offers to **create the kiosk agent key**; answer **Y**. It writes `KIOSK_ID` and `KIOSK_DEV_KEY` into `kiosk_agent\.env`.

**Demo data**: the `seed.py` step **deletes all existing data**, then creates retailer `DEMO` → group `Ontario` → store `STORE-001` → kiosk `KIOSK-001`, four products, receipts `RCP-1001`, `RCP-1002` (quantity 3) and `RCP-0900` (outside the return window), and employee `admin1` / `admin123`. Change or remove that account before any real use.

### Upgrading an existing kiosk PC (keeps your data)

1. `stop-autorefund.bat`
2. Get the new code (`git pull`, or apply the bundle you were given).
3. `setup-autorefund.bat`. It installs the kiosk agent and creates `kiosk_agent\.env`, copying your existing camera and scale settings (for example `CAMERA_INDEX`) from `self_refund_backend\.env`. It never copies the database password.
4. `init-database.bat`: answer **N** to creating the database, **N** to demo data, **Y** to the kiosk agent key, and accept `KIOSK-001` (or type your kiosk code).
5. Check `kiosk_agent\.env`, then `start-autorefund.bat`.

Hardware settings left in `self_refund_backend\.env` are no longer used and can be deleted.

A Phase 0 database moves into retailer `DEFAULT` / store `DEFAULT-STORE`, and a kiosk row is created for `KIOSK-001` and every kiosk code already used. If your kiosk code is something else, add it first: `.venv\Scripts\python manage_tenancy.py add-kiosk DEFAULT DEFAULT-STORE <code>`.

> **Coming from the Raspberry Pi folder?** Its `self_refund_frontend\node_modules` holds Linux ARM binaries, and `self_refund_backend\.venv` is a Linux environment. `setup-autorefund.bat` replaces both: `npm ci` reinstalls `node_modules`, and the old `.venv` is renamed to `.venv-raspberrypi-old`.

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

cd ..\kiosk_agent
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env
cd ..\self_refund_backend
.venv\Scripts\python manage_tenancy.py issue-dev-key KIOSK-001 --write-env ..\kiosk_agent\.env

cd ..\self_refund_frontend
npm ci
```
</details>

## 5. Configuration

Each program has its own `.env` (git-ignored, never commit it). See the `.env.example` files for the full lists.

**Core API**: `self_refund_backend\.env`

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | – | `postgresql://refund_user:<password>@localhost:5432/refund_kiosk` |
| `FLASK_HOST` / `FLASK_PORT` | `127.0.0.1` / `5000` | must stay loopback while `DEVICE_AUTH_MODE=development` |
| `FLASK_DEBUG` | `false` | Never `true` on a kiosk (the debugger allows remote code execution) |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | origins allowed for the employee screens |
| `DEVICE_AUTH_MODE` | `development` | how kiosk agents authenticate (only `development` exists) |
| `DEV_KEY_MAX_DAYS` | `30` | lifetime of a kiosk agent development key |
| `MAX_EVIDENCE_BYTES` | `5242880` | largest photo the agent may upload |
| `RETURN_WINDOW_DAYS` | `30` | days after purchase a return is accepted |
| `RETURN_RETRY_LIMIT_AFTER_REJECTION` | `1` | times a customer may try again after a rejection (`0` = never) |
| `REQUIRE_PHOTO_FOR_AUTO_APPROVAL` | `true` | no photo → employee review |
| `STAFF_SESSION_HOURS` | `8` | employee login lifetime |
| `CAPTURE_DIR` / `LOG_DIR` | `captures` / `logs` | evidence photos and logs |

**Kiosk agent**: `kiosk_agent\.env`

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_HOST` / `AGENT_PORT` | `127.0.0.1` / `5100` | the agent refuses any non-loopback host |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | the kiosk UI; POSTs from other origins are refused |
| `CORE_API_URL` | `http://127.0.0.1:5000` | Core API address |
| `CORE_API_TIMEOUT_SECONDS` | `10` | after this the customer gets the "nothing has been refunded" message |
| `KIOSK_ID` | `KIOSK-001` | the kiosk this agent expects to be |
| `KIOSK_DEV_KEY` | – | development key (`manage_tenancy.py issue-dev-key` / `init-database.bat`) |
| `AGENT_DB_PATH` | `data\kiosk_agent.sqlite3` | local session / captures / outbox |
| `CAPTURE_DIR` / `LOG_DIR` | `captures` / `logs` | photos waiting to be sent; `kiosk-agent.log` |
| `CAPTURE_MAX_AGE_SECONDS` | `900` | a photo must be used within this time |
| `SESSION_TIMEOUT_SECONDS` | `900` | kiosk session expiry |
| `HARDWARE_MODE` | `real` | `real` or `mock` (simulated devices, **development only**) |
| `CAMERA_MODE` / `SCALE_MODE` | = `HARDWARE_MODE` | override per device |
| `CAMERA_INDEX` | empty (auto 0–3) | Windows camera number |
| `CAMERA_BACKEND` | `auto` | `auto` (DirectShow → Media Foundation), `dshow`, `msmf`, `any` |
| `CAMERA_WIDTH` / `CAMERA_HEIGHT` | `640` / `480` | |
| `SCALE_VENDOR_ID` / `SCALE_PRODUCT_ID` | `0x0922` / `0x8003` | USB IDs of the scale |
| `SCALE_READ_TIMEOUT_MS` | `2000` | |
| `MOCK_SCALE_GRAMS` | `250` | weight reported by the mock scale |

**Kiosk UI**: only needed if an address differs from the default. Create `self_refund_frontend\.env.local` with `VITE_API_ORIGIN=...` (Core API) and/or `VITE_AGENT_ORIGIN=...` (kiosk agent).

Per-product weight tolerance is stored in the database (`products.weight_tolerance_percent`), not in code.

## 6. Connecting the hardware

Plug everything in, **stop AutoRefund** (`stop-autorefund.bat`; only one program may use the camera and scale at a time), then run **`check-hardware.bat`**. All camera and scale settings go in `kiosk_agent\.env`.

### Barcode scanner (USB HID keyboard)

1. Plug in the scanner. Windows installs it as a keyboard automatically.
2. Open Notepad and scan a barcode. The code should appear, followed by a new line. If there is no new line, program the scanner's **"Enter/CR suffix"** using the setup barcodes in its manual.
3. Make sure the scanner's keyboard layout matches Windows (usually *US English*). Otherwise characters like `-` can come out wrong.
4. On the receipt screen, a scan works whether or not the text box has focus. The UI detects the fast keystroke burst (`src/hooks/useBarcodeScanner.js`).

Scanners that only work in serial/COM (RS-232/USB-CDC) mode are **not** supported. Switch the scanner to USB HID keyboard mode using its manual.

### Camera

1. Plug in the webcam and close any app that uses it (Camera, Teams, Zoom).
2. Go to Windows **Settings → Privacy & security → Camera** and turn on *Camera access* and *Let desktop apps access your camera*.
3. `check-hardware.bat` tries indexes 0–3 with DirectShow and Media Foundation and saves a test photo to `kiosk_agent\captures\`.
4. If the PC has more than one camera (a built-in webcam, or **OBS Studio's virtual camera**), set `CAMERA_INDEX` to the real camera's index. Never use a virtual camera for evidence.
5. The camera also reads receipt barcodes. Code-128 receipts (such as `RCP-1001`) need pyzbar and the VC++ 2013 runtime. Without them, the camera can only read EAN/UPC codes. The handheld scanner is the recommended method.

### Scale (USB HID)

1. Plug in the scale and switch it on. Windows lists it under *Human Interface Devices*. No driver is needed.
2. `check-hardware.bat` (or, in `kiosk_agent`, `.venv\Scripts\python test_scale.py --list`) lists all HID devices. Find the scale's VID/PID and set `SCALE_VENDOR_ID` / `SCALE_PRODUCT_ID` if they differ from DYMO M10 (`0x0922` / `0x8003`; the DYMO M25 is `0x8004`).
3. `test_scale.py` prints 10 readings. Put a known item on the scale and compare.
4. Supported report format: 6-byte HID POS scale report (status, unit, exponent, weight). DYMO M5/M10/M25 use it. Grams, kg, oz and lb are converted to grams.
5. Use **grams** mode on the scale for 1 g precision (ounce mode works but is coarser).
6. DYMO scales switch off automatically after a few minutes. Disable auto-off if the model allows it. Otherwise the kiosk shows "Scale not responding" until someone presses the power button.

## 7. Starting AutoRefund

| Command | What it does |
|---|---|
| `start-autorefund.bat` | starts the Core API, the kiosk agent, builds the UI, serves it at <http://127.0.0.1:5173> and opens the browser |
| `start-autorefund.bat kiosk` | same, but in full-screen Microsoft Edge kiosk mode (Alt+F4 to exit) |
| `start-autorefund.bat dev` | Vite dev server with hot reload (for development) |
| `stop-autorefund.bat` | closes the Core API, kiosk agent and UI windows |

Windows: *AutoRefund Backend*, *AutoRefund Kiosk Agent*, *AutoRefund Frontend*.
Logs: `self_refund_backend\logs\autorefund.log` and `kiosk_agent\logs\kiosk-agent.log` (rotated at 2 MB).

**Is the kiosk set up correctly?** Open <http://127.0.0.1:5100/api/kiosk/status>. `"state": "OK"` with your store and retailer means the agent's key works; `"mock": false` means real hardware.

**Start automatically at logon (demo kiosk)**: press `Win+R`, type `shell:startup`, and put a shortcut to `start-autorefund.bat kiosk` in that folder.

**Development without hardware**: set `HARDWARE_MODE=mock` in `kiosk_agent\.env`. The camera then returns a frame stamped **MOCK CAMERA**, and the scale returns `MOCK_SCALE_GRAMS`. The agent logs a warning, `/api/hardware/status` reports `"mock": true`, and the audit log records `hardware_mock`. Never process real refunds in mock mode.

## 8. Testing

**Core API tests** use a real PostgreSQL database. Kiosk requests go through a real kiosk agent with mock hardware, running in the same process (`tests/kiosk_harness.py`):

```bat
cd self_refund_backend
REM use an EMPTY throw-away database - its tables are dropped and recreated
psql -U postgres -h localhost -c "CREATE DATABASE refund_kiosk_test OWNER refund_user"
set TEST_DATABASE_URL=postgresql://refund_user:YOUR_PASSWORD@localhost:5432/refund_kiosk_test
.venv\Scripts\python -m pytest
```

**Migration tests** need a *second* empty database (all its tables are dropped). They build a real Phase 0 database, upgrade it, use it through the app, then downgrade:

```bat
psql -U postgres -h localhost -c "CREATE DATABASE refund_migration_test OWNER refund_user"
set MIGRATION_TEST_DATABASE_URL=postgresql://refund_user:YOUR_PASSWORD@localhost:5432/refund_migration_test
.venv\Scripts\python -m pytest
```

Without them, the database tests are skipped.

**Kiosk agent tests** need no database (a fake Core API and mock devices):

```bat
cd kiosk_agent
.venv\Scripts\python -m pytest
```

Covered scenarios (Core API 126 tests, kiosk agent 41 tests):

- normal return → approved, with a photo; tolerance boundary; weight mismatch → pending review
- weight read by the kiosk agent; weight, kiosk, store or retailer values sent by the browser are ignored; empty/unstable scale refused; scale disconnected → no refund
- duplicate return blocked and logged; product not on the receipt
- quantity > 1 (partial returns, amount and expected weight scale, over-return blocked, invalid quantities)
- pending review blocks resubmission; retry after rejection within the limit; limit reached is logged
- return window enforced and configurable
- idempotency: retry returns the same return, key reuse for another item refused
- **parallel submissions** (real PostgreSQL row locks): 5 simultaneous submissions → exactly 1 return
- photos: expired/re-used capture ids not accepted; no photo → employee review; stored evidence is byte-identical to the photo the customer saw
- receipt lookup does not expose customer email or payment method
- staff endpoints and evidence images require login; forged, expired and logged-out tokens refused; login rate limit
- approve/reject record the employee, reason and audit entry; illegal state changes → 409
- `approved → refunded` requires a POS reference and cannot happen before approval
- camera failure → 503 with a friendly message; scale failure → 503; camera receipt scan; log date filter
- **tenancy** and **cross-tenant isolation** (retailer/store/kiosk links, database-level refusal of cross-retailer data, per-retailer barcodes and receipts, staff scope)
- **migrations**: Phase 0 data survives the upgrade, the app works on it, downgrade restores it, unsafe downgrade refused
- **device authentication**: missing, wrong, expired and revoked keys refused; staff tokens are not kiosk keys; the key alone decides the kiosk (impersonation attempts ignored); disabled kiosk refused; development mode refuses a non-loopback host; keys stored hashed
- **agent ↔ Core API boundary**: Core API no longer serves browser kiosk or hardware routes; returns carry the device key, not browser headers; Core API validates scale readings and JPEG evidence, stores nothing for blocked returns
- **failure safety**: Core API down, timeout, 5xx or garbage → "nothing has been refunded", no return, outbox `unconfirmed`; retry with the same key creates exactly one return, including when the first response was lost; reconciliation never re-sends
- **kiosk agent**: identity mismatch / disabled / not configured block everything; other web origins refused; loopback only; captures single use and expiring; local store holds no customer data; settings import never copies secrets

**Frontend**

```bat
cd self_refund_frontend
npm run build
npm run lint
```

`npm run lint` still reports the issues the original prototype already had (mostly `react-hooks/purity` for the `Math.random()` background particles). The build works.

**Manual hardware test checklist**: follow [`docs/phase0-hardware-test-checklist.md`](docs/phase0-hardware-test-checklist.md) on the kiosk PC. Since Phase 2, hardware settings are in `kiosk_agent\.env`.

## 9. Known limitations

- **Development kiosk keys are not production security.** A bearer key in a plain `.env` file over localhost HTTP, with no enrollment, rotation or hardware binding. It is refused unless the Core API runs on `127.0.0.1`. Production enrollment comes with the cloud API.
- **HTTP between the agent and the Core API** (same PC). HTTPS comes when the Core API moves off the kiosk.
- **The kiosk agent's local endpoints are unauthenticated** on `127.0.0.1`. Only pages from the kiosk UI origin may POST to it, but any program running on the PC could call it. It still cannot create returns without the Core API's rules.
- **A blocked return still weighs and photographs the item.** The agent measures before the Core API checks eligibility; the Core API stores no evidence for blocked returns and the agent deletes its local photo.
- **No receipt lookup rate limit.** Planned with the cloud API (WAF + per-kiosk limits).
- **Staff roles are not differentiated yet.** All three roles may review returns; the `@require_staff(...)` decorator is ready for narrower rules.
- **One return policy for all retailers** (from `.env`). The code asks `policy_for(retailer)`, so per-retailer policies can be added without changing the rules.
- **Usernames are unique across all retailers**, so login needs no retailer field.
- **Login rate limit is in memory** (per Core API process) and resets when it restarts.
- **Customer screens still keep display data in `localStorage`** (receipt items and selection, no personal data). The agent tracks the session (receipt number, timestamps).
- **No payment integration.** `approved` means verified; staff record the POS refund with *Mark refunded at POS*.
- **Development servers.** Both Flask programs use the built-in server, fine for a single kiosk demo. For production, use a WSGI server such as `waitress`.
- **Dates.** Return times are stored in UTC without a timezone marker, so the logs page may show them offset from local time.
- **Weight is the only automatic check.** Photos are stored as evidence, but no computer-vision check is done yet.
- **Camera scanning of Code-128 receipts** needs pyzbar and the VC++ 2013 runtime.
- **Unsupported scales.** Only USB HID POS scales are supported. Serial/RS-232 scales would need a new `ScaleDevice` implementation in `kiosk_agent\hardware\`.

### Verification status

| Area | Status | How |
|---|---|---|
| Core API rules, tenancy, device auth, agent boundary, migrations (126 tests) | PASS | pytest, PostgreSQL 16, Linux (Phase 1: 94 also passed on Windows) |
| Kiosk agent (41 tests) | PASS | pytest, Linux, no database |
| Separate Core API + kiosk agent processes, including Core API outage and retry | PASS | Linux, mock hardware |
| Frontend production build | PASS | `vite build` |
| Webcam, DYMO M10, pyzbar, `setup` / `init-database` / `start` scripts before Phase 2 | PASS | Windows kiosk PC (Phase 0/1) |
| Phase 2 on the Windows kiosk PC (updated scripts, agent with real webcam/DYMO/scanner, full flows) | NOT YET TESTED | needs the kiosk PC |

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
