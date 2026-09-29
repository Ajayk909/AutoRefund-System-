# AutoRefund

## Code style

The whole codebase is explained in class, so every file must be easy to follow
for a 2nd-year student.

- Keep code simple and beginner-friendly.
- Write only what the current task needs. No "just in case" code, speculative
  abstractions, extra config options or unused helpers.
- Prefer plain functions and clear names over clever patterns. Small functions,
  one job each.
- Reuse what already exists in the repo (storage code, migrations, auth
  decorators, test setup). Don't add new libraries without asking first.
- Short comments that explain WHY, not what. No giant docstrings.
- If something can be done in 10 clear lines instead of 40 "proper" lines, do
  the 10.

## Working rules

- Run tests from `self_refund_backend` with `.\.venv\Scripts\python.exe -m pytest`,
  with `TEST_DATABASE_URL` pointing at `refund_kiosk_test`. Never point it at
  `refund_kiosk`: the tests drop all tables.
- Git: small logical commits, no history rewrites or force-push, push only
  after tests pass.
- Never create or change AWS resources without asking first.
