# AutoRefund architecture

This document explains how the code is organised today (after **Phase 3**)
and where it is heading. It is written for the development team: read it
before changing the backend.

---

## 1. Where we are

| Phase | Goal | Status |
|---|---|---|
| 0 | Stabilise the Windows kiosk, fix security and business-rule problems | Done |
| 1 | Domain structure + tenant-ready database | Done |
| 2 | Windows kiosk agent + Core API boundary | Done |
| **3** | **Cloud (AWS) deployment, S3 evidence, CI/CD** | **Done** |
| 4 | AI verification | Not started |
| Later | Cognito, retailer integrations | Not started |

Three programs run on the kiosk PC in local development. In the AWS dev
environment (Phase 3) the Core API and its database run in AWS instead; the
kiosk agent and the UI stay on the kiosk. See
[`aws-deployment.md`](aws-deployment.md).

```
┌───────────────────────────────── Windows kiosk PC ─────────────────────────────────┐
│                                                                                    │
│  Browser: React UI (self_refund_frontend, :5173)                                   │
│    │ customer screens                         │ employee screens                   │
│    ▼ http://127.0.0.1:5100/api                ▼ http://127.0.0.1:5000/api          │
│  ┌───────────────────────────┐   device key   ┌─────────────────────────────────┐  │
│  │ Kiosk agent (kiosk_agent) │ ─────────────► │ Core API (self_refund_backend)  │  │
│  │ • camera, DYMO scale,     │  /api/kiosk/*  │ • tenants, receipts, catalog    │  │
│  │   barcode decoding        │                │ • return rules, state machine   │  │
│  │ • kiosk identity + key    │                │ • staff auth, review, audit     │  │
│  │ • SQLite: session,        │                │ • evidence storage              │  │
│  │   captures, outbox        │                └───────────────┬─────────────────┘  │
│  └───────┬───────────────────┘                                │                    │
│          ▼ USB                                                ▼                    │
│   webcam · DYMO M10 · (scanner types into the browser)    PostgreSQL               │
└────────────────────────────────────────────────────────────────────────────────────┘
          AWS dev (Phase 3): the Core API + PostgreSQL run in AWS behind HTTPS
```

---

## 2. Kiosk agent and Core API boundary (Phase 2)

### Who does what

| Part | Responsible for | Must NOT be trusted for / must NOT do |
|---|---|---|
| **React UI** | Screens, navigation, instructions, showing weight/preview/results | Weight, kiosk identity, authorization, eligibility, decisions |
| **Kiosk agent** | Hardware, kiosk identity + credential, reading the authoritative weight, taking/sending the photo, local session, outbox, talking to the Core API | Deciding anything about a return; approving or refunding (even offline) |
| **Core API** | Tenant/kiosk resolution, receipts, products, eligibility, window, quantity, duplicates, idempotency, weight verification, state machine, evidence, staff auth, audit | Touching hardware; trusting browser values |

Anything that decides money is in the Core API. The agent only measures and
forwards; the browser only displays and lets the customer choose.

### Hardware ownership

Only the agent imports the `hardware` package (`kiosk_agent/hardware/`:
OpenCV camera, hidapi DYMO scale, pyzbar barcode, mock devices). The Core API
has no hardware code and no hardware packages. The handheld scanner is a USB
keyboard and still types into the browser.

### Local communication: React → agent

Plain HTTP on `127.0.0.1:5100`, same paths the screens used before Phase 2:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | agent alive |
| GET | `/api/kiosk/status` | identity (kiosk → store → retailer), Core API reachability, hardware, outbox counts, session |
| GET | `/api/transactions/<receipt>` | receipt via Core API (starts a session) |
| GET | `/api/products/lookup/<barcode>` | product via Core API |
| POST | `/api/refunds/start` | submit a return (browser sends only receipt line + quantity + capture id) |
| POST | `/api/session/end` | customer finished |
| POST | `/api/outbox/reconcile` | ask the Core API about unconfirmed submissions |
| GET | `/api/scale/live`, `/api/scale/read` | weight **for display** |
| GET | `/api/camera/stream`, `/preview`, `/health`; POST `/api/camera/capture` | camera |
| GET | `/api/receipt/scan`, `/api/hardware/status` | camera barcode scan, diagnostics |

Local protections: the agent only listens on loopback (it refuses to start
otherwise), POSTs from any other web page origin are refused, and browser
headers (e.g. a staff token) are never forwarded.

### API communication: agent → Core API

HTTP to `CORE_API_URL` (`http://127.0.0.1:5000` locally, HTTPS to AWS in the
dev environment).
Every call carries the kiosk credential.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/kiosk/me` | which kiosk this credential is (kiosk, store, retailer) |
| GET | `/api/kiosk/receipts/<receipt>` | receipt + eligibility, own retailer only |
| GET | `/api/kiosk/products/<barcode>` | product in own retailer's catalog |
| POST | `/api/kiosk/returns` | multipart: `metadata` JSON + optional `image` JPEG; `Idempotency-Key` required |
| GET | `/api/kiosk/returns/by-key/<key>` | status of a submission this kiosk made |

`metadata` = `transaction_id`/`receipt_number`, `item_id`/`product_id`/`barcode`,
`quantity`, `scale: {weight_grams, stable, device, mock}`, `camera: {device, mock}`.
The Core API re-checks the reading (stable, positive, finite), validates the
JPEG (magic bytes, size limit), stores it under its own name with a SHA-256,
and applies every Phase 0/1 rule. Evidence is only stored when the cheap
eligibility checks pass and is deleted if the return is not created.

The browser can no longer reach return creation at all: the old
`/api/refunds/start`, `/api/transactions`, `/api/products/lookup` and hardware
routes are gone from the Core API, and `/api/kiosk/*` needs a kiosk credential.

### Kiosk identity and device authentication

```
agent: KioskIdentity ──► DevelopmentKeyIdentity (KIOSK_ID + KIOSK_DEV_KEY in kiosk_agent\.env, ardev_ key)
                     └─► StagingKeyIdentity     (KIOSK_ID + KIOSK_DEV_KEY holding an arstg_ key; AWS dev)
core : DeviceAuthenticator ──► DevelopmentKeyAuthenticator (DEVICE_AUTH_MODE=development, loopback only)
                           └─► StagingKeyAuthenticator     (DEVICE_AUTH_MODE=staging-key, HTTPS only)
      both check hashed keys in the kiosk_credentials table
```

The agent picks its identity class from the key's prefix (`ardev_` or
`arstg_`); the Core API uses the one authenticator selected by
`DEVICE_AUTH_MODE`.

* The **Core API decides the kiosk from the credential alone**. Headers, query
  strings and body fields claiming another kiosk are ignored.
* The agent's `KIOSK_ID` is what it *expects* to be. It checks `/api/kiosk/me`
  and refuses to take returns on a mismatch (`KIOSK_IDENTITY_MISMATCH`).
* Unknown/expired/revoked key → customer sees "This kiosk is not set up yet";
  disabled kiosk/store/retailer → "not accepting returns right now".

**Development keys (temporary, deliberately not production-grade)**

| Property | Value |
|---|---|
| Header | `Authorization: AutoRefund-Dev-Key ardev_<random>` |
| Secret | 256-bit random, shown once; only SHA-256 stored in `kiosk_credentials` |
| Scope | one kiosk; expires after `DEV_KEY_MAX_DAYS` (30); revocable; last use recorded |
| Guard | Core API **refuses to start** with `DEVICE_AUTH_MODE=development` unless `FLASK_HOST` is loopback |
| Create | `python manage_tenancy.py issue-dev-key KIOSK-001 --write-env ..\kiosk_agent\.env` (or `init-database.bat`) |
| Revoke | `python manage_tenancy.py revoke-keys KIOSK-001` |

It is a bearer secret over localhost HTTP, stored in a plain `.env` file, with
no enrollment, rotation or hardware binding. That is acceptable only because
everything runs on one PC. Production replaces both classes (see "Moving to
AWS"); the rest of the code does not change.

### Local SQLite store (kiosk agent)

`kiosk_agent\data\kiosk_agent.sqlite3` - not a business database.

| Table | Holds | Never holds |
|---|---|---|
| `kiosk_config` | identity snapshot confirmed by the Core API | keys, passwords |
| `sessions` | receipt number / transaction id, timestamps (expire after 15 min) | names, emails, payment |
| `captures` | capture id, local file name, created/used time | – |
| `outbox` | idempotency key, status, attempts, transaction/item id, Core API answer code, refund id | prices, amounts, product names, customer data |

Outbox status: `sending → accepted | rejected | unconfirmed`, and after
reconciliation `unconfirmed → accepted | not_received`.

### Failure behaviour

| Situation | Customer sees | What happens | Refund created? |
|---|---|---|---|
| Normal | Approved / Under review | agent → Core API → decision | per rules |
| Core API down, timeout, 5xx, garbage | "We can't reach the returns service right now. **Nothing has been refunded.** Please try again…" (503 `CORE_UNAVAILABLE`) | outbox `unconfirmed`; same idempotency key kept for retry | **No** (never assumed) |
| Core API did the work but the answer was lost | same message | retry with same key → Core API returns the **same** return (replay) | exactly one |
| Scale disconnected | "The scale isn't responding…" (503) | Core API not contacted | No |
| Item not on scale / moving | "Place your item on the scale and keep it still…" (409) | Core API not contacted | No |
| Camera unavailable | normal result, usually "Under review" | sent without photo → employee review | per rules |
| Kiosk agent not running | "The kiosk isn't ready right now. Nothing has been refunded…" | – | No |
| Key missing/revoked, kiosk disabled, identity mismatch | "not set up" / "not accepting returns" | nothing sent | No |
| Already returned, window expired, … | Core API's message | outbox `rejected` | No |

The agent never re-sends a return on its own and never approves anything
offline. `/api/outbox/reconcile` only asks the Core API what happened.

### Security boundaries

| Boundary | Protection |
|---|---|
| Browser → agent | loopback only; other origins refused; only line + quantity + capture id accepted |
| Agent → Core API | kiosk credential; identity from credential only; Idempotency-Key required |
| Browser → Core API | only staff endpoints (server-side sessions, tenant scope) and public health |
| Evidence | agent sends bytes; Core API names, hashes and stores; staff-only, tenant-scoped viewing |
| Secrets | DB password only in `self_refund_backend\.env`; kiosk key only in `kiosk_agent\.env`; nothing in React |

### Temporary for development

* development kiosk keys and `DEVICE_AUTH_MODE=development`
* HTTP (not HTTPS) between agent and Core API on the same PC
* Core API, PostgreSQL and evidence folder on the kiosk PC
* employee screens served from the kiosk UI build

### Moving to AWS (Phase 3 and later)

| Local development | Target | Status (AWS dev environment) |
|---|---|---|
| `CORE_API_URL=http://127.0.0.1:5000` | HTTPS endpoint in AWS (load balancer + WAF) | HTTPS load balancer done; no WAF yet |
| Development key in `.env` | `EnrolledDeviceIdentity`: key pair in the Windows key store, one-time enrollment code, short-lived tokens, revocation | Not done; dev uses interim staging keys (`arstg_`, `StagingKeyIdentity`) |
| `DevelopmentKeyAuthenticator` | token/certificate authenticator; development mode disabled | Not done; dev uses `StagingKeyAuthenticator` (`DEVICE_AUTH_MODE=staging-key`, HTTPS only) |
| Evidence in `captures\` | S3 (the agent's upload stays the same shape; storage module changes) | Done (`EVIDENCE_BACKEND=s3`) |
| PostgreSQL on the kiosk | RDS | Done |
| Staff login in the Core API | Cognito | Not done |
| Staff screens in the kiosk UI | separate staff portal | Not done |

The agent's UI endpoints, the outbox and the Core API's return rules stay.

---

## 3. Core API structure: a modular monolith

The Core API is one Flask application, organised by **business domain**. There are no
microservices: one process, one database, one deployment. Each domain is a
normal Python package with the same small set of files.

```
self_refund_backend/
├─ app/
│  ├─ api/            HTTP only: read the request, call a service, return JSON
│  │   ├─ kiosk_device.py kiosk agent endpoints (device credential required)
│  │   ├─ kiosk.py        public health check
│  │   ├─ staff.py        login, review queue, decisions, evidence
│  │   └─ serializers.py  JSON shapes
│  ├─ returns/        the heart of AutoRefund
│  │   ├─ rules.py        eligibility, quantity accounting, weight check, decision
│  │   ├─ states.py       legal status transitions
│  │   ├─ policy.py       return window, retry limit, photo requirement
│  │   ├─ service.py      submit a customer return
│  │   ├─ review.py       staff approve / reject / mark refunded
│  │   └─ repository.py   database queries
│  ├─ receipts/       receipt lookup (service + repository)
│  ├─ catalog/        products and identifiers (repository)
│  ├─ tenancy/        retailers, stores, kiosks; KioskContext + StaffScope;
│  │                  device_auth.py (kiosk credentials)
│  ├─ identity/       staff login, sessions, @require_staff
│  ├─ evidence/       storing uploaded photos, finding them for staff
│  ├─ audit/          audit event recording
│  ├─ models/         SQLAlchemy models, one file per domain
│  ├─ errors.py       DomainError (customer-safe message + code + HTTP status)
│  ├─ ids.py, timeutil.py
│  └─ __init__.py     create_app()
├─ migrations/        Alembic
├─ tests/
├─ seed.py            demo data
└─ manage_tenancy.py  add retailers / stores / kiosks
```

### The layers

```
api/  ──►  service  ──►  rules          (pure decisions)
                    ──►  repository     ──►  models  ──►  PostgreSQL
```

Hardware is not part of the Core API; measurements arrive from the kiosk agent.

```
kiosk_agent/
├─ agent/
│  ├─ routes.py, hardware_routes.py   HTTP for the kiosk UI
│  ├─ submissions.py                  submit a return, reconcile the outbox
│  ├─ identity.py, identity_check.py  kiosk identity + confirmation
│  ├─ core_client.py                  Core API client (CoreUnavailable)
│  ├─ store.py, captures.py           SQLite store, local photos
│  └─ config.py                       kiosk_agent\.env
├─ hardware/                          camera, DYMO scale, barcode, mocks
├─ scripts/import_backend_settings.py
├─ check_camera.py, test_scale.py, run_agent.py
└─ tests/                             unit tests (no database)
```

| Layer | Does | Must not |
|---|---|---|
| `api/*.py` | Parse the request, pick the tenant context, call a service, format JSON | Contain business rules or SQL |
| `service.py` | Run a use case in order (validate, take measurements, lock, decide, save, audit) | Know about HTTP or hardware |
| `rules.py` | Decide (eligible? weight OK? approve or review?) | Commit or talk to hardware |
| `repository.py` | Query the database, always scoped to a tenant | Decide business outcomes |
| `models/` | Table definitions | Contain behaviour |

Errors: a service raises `DomainError(code, message, status)`. One handler in
`api/__init__.py` rolls back the transaction and returns
`{"success": false, "code": ..., "message": ...}`. The `message` is always
safe to show a customer; technical detail goes to the log.

### Where do I put new code?

* A new rule about returns → `returns/rules.py` (+ a test)
* A new step in submitting a return → `returns/service.py`
* A new query → the domain's `repository.py`, **taking a retailer id or scope**
* A new endpoint → `api/`, calling a service
* A new device model → a new class in `kiosk_agent/hardware/` implementing the interface
* Something the kiosk screen needs from hardware → `kiosk_agent/agent/`

---

## 4. Tenant model

AutoRefund is designed to serve many retailers. The hierarchy is:

```
Retailer (tenant)              e.g. DEMO
 └─ Store group (optional)     e.g. Canada ─► Ontario   (nestable)
     └─ Store                  e.g. STORE-001
         └─ Kiosk              e.g. KIOSK-001   (= KIOSK_ID in .env)
             └─ Return  ──►  Transaction (receipt) ──► Transaction items ──► Product
```

### Tables

| Table | Owned by | Key uniqueness |
|---|---|---|
| `retailers` | – | `code` |
| `store_groups` | retailer | `(retailer_id, code)`; parent group must be the same retailer |
| `stores` | retailer | `(retailer_id, code)` |
| `kiosks` | retailer + store | `code` (global: it is the device's KIOSK_ID) |
| `products` | retailer | internal `product_id` |
| `product_identifiers` | retailer + product | `(retailer_id, value)`; one primary per product |
| `transactions` | retailer + purchase store | `(retailer_id, receipt_number)` |
| `transaction_items` | retailer | – |
| `refunds` (returns) | retailer + return store + kiosk | `idempotency_key` |
| `staff` | retailer (+ optional store) | `username` |
| `staff_sessions` | staff | token hash |
| `audit_logs` | retailer/store when known | – |

### Why shared-schema multi-tenancy?

All retailers share the same tables; every tenant-owned row has `retailer_id`.

| Option | Why not (for us) |
|---|---|
| Database per kiosk | Kiosks would each hold business data; no central view; sync nightmare |
| Database per store / retailer | Many databases to migrate, back up and monitor; hard to report across them |
| Schema per retailer | Every migration runs N times; connection pooling gets awkward |
| **Shared schema + `retailer_id`** | **One migration, one backup, simple queries, scales to thousands of kiosks** |

A very large retailer that contractually needs its own database can still be
given one later, because all code already works through a tenant context.

### How isolation is enforced (two layers)

1. **Application.** Kiosk requests run in a `KioskContext`; staff requests
   in a `StaffScope`. Repository functions require the retailer id / scope,
   so receipt, product and return queries cannot ignore the tenant. Another
   retailer's data is answered with **404 (not found)**, never 403, so its
   existence isn't revealed.
2. **Database.** Composite foreign keys such as
   `(retailer_id, product_id) → products(retailer_id, product_id)` mean
   PostgreSQL refuses a row that links two retailers, even if application
   code has a bug. A return's kiosk must belong to the return's store.

PostgreSQL Row-Level Security is **not** used yet. It adds most value once
several services or reporting users connect directly to the database (cloud
phases); the schema is ready for it.

### Products and identifiers

`products.product_id` is AutoRefund's own identity. Barcodes, SKUs and PLUs
are **external identifiers** in `product_identifiers`, unique per retailer:

```
Retailer DEMO : barcode 111111 → Coca Cola Can
Retailer OTHER: barcode 111111 → Other Retailer Soda      (allowed)
Retailer DEMO : barcode 111111 → anything else            (refused)
```

Retailer integrations (a later phase) will map a retailer's catalog feed into these
tables through an adapter; nothing is Walmart- or retailer-specific.

### Kiosk identity

A kiosk agent's credential (`kiosk_credentials`) resolves to kiosk → store →
retailer on every Core API call (section 2). An unknown, revoked or disabled
kiosk cannot look up receipts or create returns.

```bat
python manage_tenancy.py list
python manage_tenancy.py add-kiosk DEMO STORE-001 KIOSK-002
python manage_tenancy.py issue-dev-key KIOSK-002 --write-env ..\kiosk_agent\.env
```

### Staff scope (today)

A staff member belongs to one retailer. `staff.store_id` empty = all stores
of that retailer; set = only that store. Usernames stay globally unique so
login needs no retailer field. Full role assignments (several stores,
regions, roles per scope) come with Cognito in a later phase.

---

## 5. Returns: rules that must not regress

| Rule | Where |
|---|---|
| Weight read by the kiosk agent from the scale, never from the browser; re-validated by the Core API | `kiosk_agent/agent/submissions.py`, `returns/service.py` |
| Kiosk identity from the device credential, never from the request | `tenancy/device_auth.py` |
| Photo must be a recent, unused capture, else the agent takes one; Core API validates and names it | `kiosk_agent/agent/captures.py`, `evidence/storage.py` |
| Communication failure is never success; no offline refunds | `kiosk_agent/agent/submissions.py` |
| No photo → employee review (configurable) | `returns/rules.py::decide` |
| Quantity accounting per receipt line; rejected units released | `returns/rules.py` |
| Retry limit after rejection | `returns/service.py` |
| 30-day window (configurable) | `returns/rules.py`, `returns/policy.py` |
| Row lock on the receipt line while checking | `receipts/repository.py::lock_line` |
| Idempotency key, unique in the database | `returns/service.py`, `models/returns.py` |
| States: `pending_review → approved/rejected`, `approved → refunded` | `returns/states.py` |
| Staff endpoints require a server-side session | `identity/auth.py` |
| Evidence only for staff who may see that return | `api/staff.py` |

Status note: returns are verified synchronously today, so the conceptual
*verifying* step has no stored status. It will become a stored state when
AI verification runs asynchronously (Phase 4).

---

## 6. Migrations

Alembic, one migration per logical change, never editing an applied one.

| Revision | Change |
|---|---|
| `7050467d79b3` | Initial schema (Raspberry Pi prototype) |
| `8c6babcc8841` | Unique receipt number |
| `b3f1c2d4e5a6` | Phase 0: quantity, idempotency, `refunded`, staff sessions |
| `c7d2e8f1a9b0` | Phase 1: retailers, store groups, stores, kiosks + DEFAULT tenant |
| `d4a1b6c3e2f5` | Phase 1: tenant ownership, product identifiers, per-retailer receipts |
| `e5b9c0d7f3a1` | Phase 2: kiosk credentials, evidence SHA-256 |

Upgrading a Phase 0 database puts all existing data into retailer
`DEFAULT` / store `DEFAULT-STORE` and creates a kiosk row for every kiosk code
already used by a return, plus `KIOSK-001`. Nothing is deleted.

```bat
cd self_refund_backend
.venv\Scripts\python -m alembic upgrade head      & REM apply
.venv\Scripts\python -m alembic current           & REM show version
.venv\Scripts\python -m alembic downgrade -1      & REM undo one step
```

Downgrading below Phase 1 refuses to run if two retailers share a barcode or
receipt number, because Phase 0 cannot store that.

---

## 7. Deliberately deferred

| Item | Why not now | Planned |
|---|---|---|
| `kiosk_devices` table | Devices are reported live by `/hardware/status`; nothing to store yet | With heartbeats/monitoring |
| `product_reference_images` | Only needed for AI image comparison | AI verification phase |
| `verification_signals` table | Only weight + photo exist; kept on the return row | AI verification phase |
| Evidence metadata table | Nothing needs to query evidence by metadata yet; the path and SHA-256 on the return row are enough | When retention or audit queries need it |
| `review_decisions` table | One decision per return; stored on the return + audit log | When multi-step review is needed |
| `role_assignments` | One retailer (+ optional store) per staff member is enough today | Cognito phase |
| `return_policies` table | One policy from `.env`; code already goes through `policy_for()` | When a second real retailer needs different rules |
| PostgreSQL Row-Level Security | Composite foreign keys and app scoping already enforce isolation; RLS only earns its cost when a second application connects to the same database, which isn't on the roadmap | Not planned for the capstone |
| Renaming `refunds` → `returns` | Rename churn with no functional gain; would break migrations and docs for nothing | Not planned |
| Production kiosk enrollment, key pairs, token rotation | Needs PKI decisions that the cloud API existing doesn't make for us | Before production; the AWS dev environment uses interim staging keys |
| HTTPS between agent and Core API | Both on one PC in local development | Done for the AWS dev environment (staging keys require HTTPS) |
| Automatic outbox re-sending | Would act without the customer present | Not planned for returns |
| Moving all UI flow state into the agent | Screens still keep display data in localStorage (no personal data) | When the UI is reworked |
| Heartbeats / fleet monitoring | Only `/api/kiosk/status` locally | Monitoring phase |
| AI, POS, payments | Out of scope so far | Phase 4 (AI); later (POS, payments) |
