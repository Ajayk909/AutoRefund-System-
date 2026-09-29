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
