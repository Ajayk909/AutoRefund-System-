"""
Tenancy: retailers, store groups, stores and kiosks.

Every request that touches tenant data runs inside a context:

* KioskContext  - kiosk agent requests. Resolved from the agent's device
                  credential (device_auth.py).
* StaffScope    - staff requests. Resolved from the logged-in staff member.

Repositories take the context/scope and filter by it, so a query cannot
"forget" the tenant.
"""
