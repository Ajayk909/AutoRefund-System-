# Phase 0 – Windows kiosk hardware and workflow test checklist

These tests need the **real kiosk PC** (Windows, USB webcam, DYMO M10 scale,
handheld USB barcode scanner). They could not be run in the cloud session
that wrote the Phase 0 code, so every item below is currently **NOT TESTED**.

Fill in the *Result* column (PASS / FAIL + note). For every FAIL, copy the
matching lines from `self_refund_backend\logs\autorefund.log` and the console
window, and note what was on screen.

Tester: ____________  Date: ____________  Commit: `git rev-parse --short HEAD` → ________

---

## 0. Before you start

| # | Step | Expected | Result |
|---|---|---|---|
| 0.1 | `git pull`, then `git log --oneline -6` | top commits are the Phase 0 commits | |
| 0.2 | Back up the database if it has data you want: `pg_dump -U refund_user -h localhost refund_kiosk > backup.sql` | file created | |
| 0.3 | `self_refund_backend\.env`: `HARDWARE_MODE=real`, compare with `.env.example` and add the new Phase 0 settings | settings present | |

## 1. Windows scripts

| # | Step | Expected | Result |
|---|---|---|---|
| 1.1 | Run `setup-autorefund.bat` | finishes without `[ERROR]`; `.venv` created; `npm` packages installed | |
| 1.2 | Run `init-database.bat`, answer **N** to creating the DB if it already exists | `Running upgrade 8c6babcc8841 -> b3f1c2d4e5a6` (or "already at head") | |
| 1.3 | Same script, answer **y** to demo data (test PC only) | seed prints receipts `RCP-1001`, `RCP-1002`, `RCP-0900` | |
| 1.4 | Run `check-hardware.bat` | camera photo saved, scale readings printed | |
| 1.5 | Run `start-autorefund.bat` | backend + frontend windows open, browser opens `http://127.0.0.1:5173` | |
| 1.6 | Open `http://127.0.0.1:5000/api/hardware/status` | `"mock": false` for camera **and** scale | |
| 1.7 | Run `stop-autorefund.bat` | both windows close; port 5000 and 5173 free | |
| 1.8 | Automated tests on Windows (README §8, `TEST_DATABASE_URL` set) | **63 passed** | |

## 2. Webcam

| # | Step | Expected | Result |
|---|---|---|---|
| 2.1 | Weigh screen: live preview | real camera image, not "MOCK CAMERA" | |
| 2.2 | Press **Capture Now** | photo appears in the preview, button says *Captured ✓* | |
| 2.3 | `self_refund_backend\captures\` | new `capture_..._<32 hex>.jpg` file | |
| 2.4 | Open `http://127.0.0.1:5000/api/captures/<that file>` in a browser | **401** (evidence is not public) | |
| 2.5 | Lighting: photo of a dark item and a shiny item | item recognisable in both | |

## 3. DYMO M10 scale

| # | Step | Expected | Result |
|---|---|---|---|
| 3.1 | Empty scale, weigh screen | ~0 g, submit button waits | |
| 3.2 | Known weight (e.g. 250 g can) | reading within ±2 g, becomes *stable* | |
| 3.3 | Switch the scale to **oz** mode, same item | still shown in grams correctly | |
| 3.4 | Press on the scale while submitting | "Place your item on the scale and keep it still" | |
| 3.5 | DYMO auto-off (wait ~3 min idle), then submit | clear message, recovers after switching on | |

## 4. Handheld barcode scanner

| # | Step | Expected | Result |
|---|---|---|---|
| 4.1 | Receipt screen, text box focused, scan `RCP-1001` | receipt loads | |
| 4.2 | Tap elsewhere on the screen, scan again | receipt still loads (keyboard-wedge hook) | |
| 4.3 | Scanner with/without Enter suffix | both work | |
| 4.4 | Hold receipt barcode to the camera | auto-scan loads the receipt | |

## 5. Customer return flow (real hardware)

| # | Step | Expected | Result |
|---|---|---|---|
| 5.1 | `RCP-1001` → Coca Cola Can → weigh a ~250 g item → submit | **Approved**, amount $2.99 | |
| 5.2 | Go back to the item list | Coca Cola Can shows *Already returned* | |
| 5.3 | `RCP-1001` → Potato Chips → put a clearly wrong weight → submit | **Under review** | |
| 5.4 | Try Potato Chips again | *Waiting for an employee to review* | |
| 5.5 | `RCP-1002` (Yogurt Cup ×3) → return one | approved $1.25; list shows *2 of 3 can be returned* | |
| 5.6 | Return yogurt two more times | third return then *Already returned* | |
| 5.7 | `RCP-0900` | item shows *Outside the return period* and can't be selected | |
| 5.8 | Double-tap **Submit** quickly | only **one** refund in the employee logs | |
| 5.9 | Stop the backend window right after pressing Submit, restart it, press Submit again | at most one refund for that item | |
| 5.10 | Time a normal return from receipt scan to result | under ~60 s (write the time) | |

## 6. Employee workflow

| # | Step | Expected | Result |
|---|---|---|---|
| 6.1 | Open `http://127.0.0.1:5173/employee/pending` without logging in | redirected to login | |
| 6.2 | Wrong password 5 times, then the right one | "Too many failed attempts" | |
| 6.3 | Wait 15 min (or restart backend), log in as `admin1` | dashboard shows *Welcome Back, Demo Admin* | |
| 6.4 | Pending: Potato Chips card | shows *Why flagged*, photo, weights, kiosk | |
| 6.5 | Reject with a reason | card disappears; logs show *rejected*, reason, reviewer name | |
| 6.6 | Customer tries Potato Chips again, wrong weight, employee rejects again, customer tries a third time | third attempt: *Please visit customer service* | |
| 6.7 | Logs → an approved return → **Mark refunded at POS** with reference `TEST-1` | status *refunded*, reference shown | |
| 6.8 | Two browser tabs on the same pending card: approve in one, reject in the other | second action shows "This return is already approved" | |
| 6.9 | Sign out, press browser Back | redirected to login; data not shown | |
| 6.10 | Close the browser, reopen `/employee/dashboard` | login required (sessionStorage) | |

## 7. Hardware disconnection and failure

| # | Step | Expected | Result |
|---|---|---|---|
| 7.1 | Unplug the **scale** on the weigh screen | "Scale not responding" message | |
| 7.2 | Submit while unplugged | "The scale isn't responding. Please ask an employee for help." No refund created | |
| 7.3 | Plug the scale back in | readings resume without restarting | |
| 7.4 | Unplug the **camera**, press Capture Now | "Camera unavailable. Please try again." | |
| 7.5 | Submit with a good weight while the camera is unplugged | **Under review** (no photo), not approved | |
| 7.6 | Plug the camera back in | preview and capture work again (restart only if not) | |
| 7.7 | Unplug the **barcode scanner** | typing the receipt number still works | |
| 7.8 | Stop PostgreSQL service, try a receipt | friendly error, no crash; works after restart | |
| 7.9 | Check `logs\autorefund.log` | hardware errors logged with technical detail | |

---

### Results summary

| Area | PASS | FAIL | Notes |
|---|---|---|---|
| Scripts | | | |
| Webcam | | | |
| Scale | | | |
| Scanner | | | |
| Customer flow | | | |
| Employee flow | | | |
| Failure cases | | | |
