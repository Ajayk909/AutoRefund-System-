"""
Tenancy: retailers, store groups, stores and kiosks.

Every request that touches tenant data runs inside a context:

* KioskContext  - customer kiosk requests. Resolved from KIOSK_ID in .env
                  (Phase 2 replaces this with device authentication).
* StaffScope    - staff requests. Resolved from the logged-in staff member.

Repositories take the context/scope and filter by it, so a query cannot
"forget" the tenant.
"""
