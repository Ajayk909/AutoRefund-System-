# AutoRefund architecture

This document explains how the code is organised today (after **Phase 1**)
and where it is heading. It is written for the development team: read it
before changing the backend.

---

## 1. Where we are

| Phase | Goal | Status |
|---|---|---|
| 0 | Stabilise the Windows kiosk, fix security and business-rule problems | Done |
| **1** | **Domain structure + tenant-ready database** | **Done** |
| 2 | Kiosk agent: device identity, local session, trusted hardware service | Next |
| 3+ | Cloud API (AWS), Cognito, S3 evidence, AI verification, retailer integrations | Later |

Everything still runs on **one Windows PC**: React kiosk UI, Flask backend,
local PostgreSQL, USB camera, DYMO scale and barcode scanner.

```
┌──────────────────────────── Windows kiosk PC ─────────────────────────────┐
│                                                                            │
│  React UI (customer + employee)  ──HTTP──►  Flask backend  ──►  PostgreSQL │
│                                              │                             │
│                                              └──► hardware/  ──► camera,   │
│                                                                  scale     │
│  USB barcode scanner ──(keyboard input)──► React UI                        │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Backend structure: a modular monolith

One Flask application, organised by **business domain**. There are no
microservices: one process, one database, one deployment. Each domain is a
normal Python package with the same small set of files.

```
self_refund_backend/
├─ app/
│  ├─ api/            HTTP only: read the request, call a service, return JSON
│  │   ├─ kiosk.py        receipts, product lookup, submit a return
│  │   ├─ hardware.py     scale, camera, receipt barcode scan
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
│  ├─ tenancy/        retailers, stores, kiosks; KioskContext + StaffScope
│  ├─ identity/       staff login, sessions, @require_staff
│  ├─ evidence/       item photos (capture ids, previews, files)
│  ├─ audit/          audit event recording
│  ├─ models/         SQLAlchemy models, one file per domain
│  ├─ errors.py       DomainError (customer-safe message + code + HTTP status)
│  ├─ ids.py, timeutil.py
│  └─ __init__.py     create_app()
├─ hardware/          device interfaces + real USB and mock implementations
├─ migrations/        Alembic
├─ tests/
├─ seed.py            demo data
└─ manage_tenancy.py  add retailers / stores / kiosks
```

### The layers

```
api/  ──►  service  ──►  rules          (pure decisions)
                    ──►  repository     ──►  models  ──►  PostgreSQL
                    ──►  hardware interfaces
```

| Layer | Does | Must not |
|---|---|---|
| `api/*.py` | Parse the request, pick the tenant context, call a service, format JSON | Contain business rules or SQL |
| `service.py` | Run a use case in order (validate, read hardware, lock, decide, save, audit) | Know about HTTP |
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
* A new device model → a new class in `hardware/` implementing the interface

---

## 3. Tenant model

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

Retailer integrations (Phase 8) will map a retailer's catalog feed into these
tables through an adapter; nothing is Walmart- or retailer-specific.

### Kiosk identity (today)

`KIOSK_ID` in `.env` must match a row in `kiosks`. Every kiosk request
resolves it to kiosk → store → retailer. An unknown or disabled kiosk gets
a friendly "not set up" message and cannot look up receipts or create
returns. **This is configuration, not security**: anyone who can edit `.env`
can change it. Phase 2 replaces it with kiosk enrollment and device keys.

```bat
python manage_tenancy.py list
python manage_tenancy.py add-kiosk DEMO STORE-001 KIOSK-002
```

### Staff scope (today)

A staff member belongs to one retailer. `staff.store_id` empty = all stores
of that retailer; set = only that store. Usernames stay globally unique so
login needs no retailer field. Full role assignments (several stores,
regions, roles per scope) come with Cognito in Phase 4.

---

## 4. Returns: rules that must not regress

| Rule | Where |
|---|---|
| Weight read by the backend from the scale, never from the browser | `returns/service.py` |
| Kiosk identity from configuration, never from the browser | `api/kiosk.py`, `tenancy/context.py` |
| Photo must be a recent, unused capture from this backend, else backend takes it | `evidence/captures.py` |
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
AI verification runs asynchronously (Phase 6/7).

---

## 5. Migrations

Alembic, one migration per logical change, never editing an applied one.

| Revision | Change |
|---|---|
| `7050467d79b3` | Initial schema (Raspberry Pi prototype) |
| `8c6babcc8841` | Unique receipt number |
| `b3f1c2d4e5a6` | Phase 0: quantity, idempotency, `refunded`, staff sessions |
| `c7d2e8f1a9b0` | Phase 1: retailers, store groups, stores, kiosks + DEFAULT tenant |
| `d4a1b6c3e2f5` | Phase 1: tenant ownership, product identifiers, per-retailer receipts |

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

## 6. Deliberately deferred

| Item | Why not now | Planned |
|---|---|---|
| `kiosk_devices` table | Devices are reported live by `/hardware/status`; nothing to store yet | With heartbeats/monitoring |
| `product_reference_images` | Only needed for AI image comparison | AI verification phase |
| `verification_signals` table | Only weight + photo exist; kept on the return row | AI verification phase |
| Evidence metadata table | Photos are local files; path on the return row is enough | S3 phase |
| `review_decisions` table | One decision per return; stored on the return + audit log | When multi-step review is needed |
| `role_assignments` | One retailer (+ optional store) per staff member is enough today | Cognito phase |
| `return_policies` table | One policy from `.env`; code already goes through `policy_for()` | When a second real retailer needs different rules |
| PostgreSQL Row-Level Security | App scoping + composite FKs cover today's single app | Cloud phase |
| Renaming `refunds` → `returns` | Rename churn with no functional gain | Possibly with the cloud API |
| Kiosk enrollment / device keys, offline outbox, AWS, AI, POS | Out of Phase 1 scope | Phases 2+ |
