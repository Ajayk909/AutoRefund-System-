# AI photo check: test results

The AI photo check (`IMAGE_VERIFIER=bedrock`, code in
`self_refund_backend/app/verification/bedrock_verifier.py`) sends the
product's reference photo and the kiosk photo to an Amazon Bedrock model, and
asks if it is the same, complete, undamaged product.

These are the results of real Bedrock calls with our demo items (receipt
RCP-2001), on 2026-10-07.

## Setup

- **Photos:** each kiosk webcam photo (`camera/test/`) was checked against the
  product's uploaded reference photo (`camera/MAIN/`).
- **Settings:** one call per test, `temperature` 0, the app's 5-second timeout.
- **Region:** the calls were made from ca-central-1.
- **Price used for cost:**
  - Nova Lite: $0.06 per 1M input tokens, $0.24 per 1M output tokens.
  - Nova 2 Lite (`us.`): $0.33 per 1M input tokens, $2.75 per 1M output tokens.

| Test | Kiosk photo shows | Should be |
|---|---|---|
| 1 | Somersby can, correct | match |
| 2 | CeraVe bottle, **pump missing** (only the neck shows) | mismatch or uncertain |
| 3 | Shoe box with **one shoe** instead of two | mismatch |
| 4 | CeraVe bottle, checked against the **Somersby** reference | mismatch |

## Prompt versions

- **v1:** the model answers `same_product`, `obvious_damage` (which also had to
  cover missing parts), `confidence` and `reason`.
- **v2:** the model must first write `differences`, then answer
  `same_product`, a separate `missing_part`, `obvious_damage`, `confidence`
  and `reason`. A missing part (high/medium confidence) counts as a mismatch.

Both prompts name a few example parts: "a pump, cap or lid, or one item of a
pair".

## Results

| Test | Should be | Nova Lite + v1 | Nova Lite + v2 | Nova 2 Lite + v2 |
|---|---|---|---|---|
| 1 Somersby OK | match | ✅ match | ✅ match | ✅ match |
| 2 CeraVe, no pump | mismatch / uncertain | ❌ match | ❌ match | ❌ match |
| 3 One shoe in box | mismatch | ❌ match ¹ | ✅ mismatch | ❌ match |
| 4 Wrong product | mismatch | ✅ mismatch | ✅ mismatch | ✅ mismatch |
| **Correct** | | **2 / 4** | **3 / 4** | **2 / 4** |

¹ The model's own reason said "shows a single shoe, but the reference photo
shows a pair", yet it answered `obvious_damage: false`. This is why v2 has a
separate `missing_part` field.

### Time, tokens and cost per check

| Run | Model ID | Time per check | Input tokens | Output tokens | Cost per check |
|---|---|---|---|---|---|
| Nova Lite + v1 | `ca.amazon.nova-lite-v1:0` | 0.9–1.5 s | ~4,375 | 28–42 | ~$0.00027 |
| Nova Lite + v2 | `ca.amazon.nova-lite-v1:0` | 0.9–1.4 s | ~4,415 | 52–80 | ~$0.00028 |
| Nova 2 Lite + v2 | `us.amazon.nova-2-lite-v1:0` | 1.5–1.9 s | ~695 | 68–105 | ~$0.00046 |

"Time per check" is measured in our app, including the network. The first
call of each run is the slowest because it also opens the connection.

All 12 calls together cost less than half a US cent.

## What we learned

- **Wrong product:** detected by both models, every time.
- **The prompt matters:** asking for the differences first, and for a separate
  `missing_part` answer, fixed the one-shoe case on Nova Lite.
- **The missing pump:** no model noticed it. It is a small detail at the top
  of the bottle.
- **Nova 2 Lite was not better here:** it is newer but did worse. It used about
  7x fewer input tokens, which suggests it looks at the photos in less detail.
  Its `us.` profile also sends the photos to the US instead of keeping them
  in Canada.
- **The AI never approves alone:** only a weight match can approve. In test 3
  the weight is far too low anyway, so the kiosk declines that return on
  weight (more than `WEIGHT_DECLINE_PERCENT` off).
  In test 2 the weight passes, so the AI's wrong "match" means **the return is
  approved**. That case is not caught yet.
- **This is a small test:** 4 photos, one call each, so it is not a full
  accuracy measurement.

## Decision for now

- **Default model:** was `ca.amazon.nova-lite-v1:0` with prompt v3 until
  2026-10-08 (see the decision at the end of this page): best
  result, cheapest, and the photos stay in Canada.
- **Default setting:** `IMAGE_VERIFIER` stays `none` locally (`.env.example`);
  in dev it is switched on (`bedrock`) through Terraform.
- **Ideas for the missing-pump case** (not done yet):
  - a reference photo that shows the pump close up;
  - asking about the parts of each product specifically;
  - testing a stronger model.

## Prompt v3 and automatic declines (2026-10-08)

Since this cycle the kiosk may decline a return on its own in obvious cases
(rules in `self_refund_backend/app/returns/rules.py`). For the AI that means:

- **v3:** the model first says what the kiosk photo shows (`kiosk_item`, a
  few words), then the `differences`. `same_product` now means a different
  *kind* of product; a missing part or damage does not count.
- Only a high-confidence "different product", with no missing part or
  damage, may decline, and only when the weight matched. The customer then
  sees the AI's item phrase (at most 60 characters, plain text), e.g. "This
  doesn't look like <product>. It looks like <item>."
- A missing part, damage, medium/low confidence or an AI error still send
  the return to an employee.

### How to run it

From `self_refund_backend`:

    .\.venv\Scripts\python.exe evaluate_ai.py <model-id>

It uses the app's own `BedrockVerifier` (same prompt, same 5-second
timeout) on the photos in the `camera` folder next to the repo (`MAIN/` =
reference photos, `test/` = kiosk photos). Each run makes 4 real, paid
Bedrock calls.

### Results

"Kiosk should" assumes the weight matched, so it shows what the AI alone
decides.

| Test | Kiosk should | Nova Lite + v3 | Claude Haiku 4.5 + v3 |
|---|---|---|---|
| 1 Somersby OK ³ | approve | ✅ approve (match, high) | ❌ review (damage: "the can has been opened", high) |
| 2 CeraVe, no pump | review | ❌ approve (match, high) | ❌ approve (match, high: "pump cap intact") |
| 3 One shoe in box | review ¹ | ✅ review (missing part, high) | ✅ review (missing part, high) |
| 4 CeraVe vs Somersby reference | decline | ✅ decline (different product, high) | ✅ decline (different product, high) |
| **Correct** | | **3 / 4** | **2 / 4** |

What each model said the kiosk photo shows (`kiosk_item`):

| Test | Nova Lite + v3 | Claude Haiku 4.5 + v3 |
|---|---|---|
| 1 | a can of cider | a can of Somersby Blackberry Cider |
| 2 | CeraVe Acne Control Cleanser | CeraVe Acne Control Cleanser bottle |
| 3 | NavyWhite Sneakers (in New Balance box) ² | Navy/White sneakers in New Balance box |
| 4 | bottle of CeraVe Acne Control Cleanser | CeraVe Acne Control Cleanser bottle |

¹ With the real one-shoe box the weight is about 75% too low, so the kiosk
declines it on weight before the AI is asked.
² This run removed the "/" from the phrase; the code keeps it since
commit `5750c6c` (the Haiku run was after that fix).
³ The "OK" kiosk photo actually shows an **opened** can (the drink opening
in the lid is visible); the reference photo shows the can from the side, so
its lid can't be seen. Haiku reported the opening as damage, Nova Lite did
not notice it. Whether an opened can should be refused is a store policy
question, so this row is still scored against the original label.

| Run | Model ID | Called from | Time per check | Input tokens | Output tokens | Cost per check |
|---|---|---|---|---|---|---|
| Nova Lite + v3 | `ca.amazon.nova-lite-v1:0` | ca-central-1 | 1.1–1.6 s | ~4,473 | 67–106 | ~$0.00029 |
| Claude Haiku 4.5 + v3 | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | us-east-1 | 1.5–2.5 s | ~3,410 | 113–141 | ~$0.0045 ⁴ |

⁴ Estimated with $1.10 per 1M input and $5.50 per 1M output tokens: the
global price ($1 / $5) plus the ~10% AWS charges for geographic (`us.`)
cross-Region profiles. Check the Amazon Bedrock pricing page before relying
on it. That is about 15x the Nova Lite cost; the 4 Haiku calls together
cost about $0.02.

### What we learned (v3)

- **Wrong product:** detected again, now flagged as a different product
  with high confidence, so the kiosk declines it. The AI read the label of
  the real item ("CeraVe"), which was not in the prompt.
- **The missing pump:** still not noticed. The model answered "match" with
  high confidence, so with a matching weight **this return is approved**.
  Same as v1 and v2.
- **One shoe:** correctly a missing part, not a different product, so the AI
  alone would send it to review, not decline it.
- **The item phrase:** for the correct product the model often repeats the
  product name from the prompt instead of describing the photo (tests 2 and
  3). It also leaves out "a" sometimes ("It looks like bottle of ...").

### What we learned (Claude Haiku 4.5)

- **The missing pump:** not caught either. Haiku said the "pump cap
  intact", which is not what the photo shows.
- **The opened can:** Haiku noticed it (test 1); Nova Lite did not.
- **Item phrases:** more natural ("a can of Somersby Blackberry Cider"),
  but it also repeats the product name from the prompt for the right product.
- **Speed:** 1.5–2.5 s per check, within the 5-second timeout, but slower
  than Nova Lite.
- **Cost:** about 15x Nova Lite per check (still under half a cent).

### Claude Haiku 4.5: access and region

Until 2026-10-08 the AWS account was on the Free plan, so the Bedrock
Marketplace agreement for Anthropic models was not available. After the
upgrade to the Paid plan and the Anthropic use-case form, a read-only check
(`aws bedrock get-foundation-model-availability`) showed the agreement
`AVAILABLE` and the model `AUTHORIZED`.

Note for the comparison: Claude Haiku 4.5 on Bedrock is only available
through the `us.` or `global.` inference profiles, so **the photos may be
processed in the US**. Called from ca-central-1 (like the app), the `us.`
profile can run a request in ca-central-1, us-east-1, us-east-2 or
us-west-2; AWS picks. Nova Lite's `ca.` profile keeps them in Canada.

## Experiment: a product note for the missing pump (2026-10-08)

Idea: give the AI product-specific knowledge. For the CeraVe tests only, one
extra line was added to prompt v3 (a throwaway script, not in the app).

- **Note 1:** "Required parts for this product: the white pump dispenser on
  top of the bottle. If it is not clearly visible in the kiosk photo,
  missing_part must be true."
- **Note 2 (sharper):** "Required parts for this product: the pump. A pump
  has a tall head with a nozzle sticking out sideways. If the top of the
  bottle is only a short white screw collar, with no tall head and no
  nozzle, the pump is missing and missing_part must be true."

`cerave_nopump_close.jpg` is a second no-pump photo (closer, better light),
so the note is not tuned to one photo. "With pump" is the reference photo
itself used as the kiosk photo.

| Kiosk photo | Should be | Nova Lite + note 1 | Haiku 4.5 + note 1 | Haiku 4.5 + note 2 |
|---|---|---|---|---|
| `cerave_nopump.jpg` | review | ❌ match (high) | ❌ match (high) | ❌ match (high) |
| `cerave_nopump_close.jpg` | review | not run | not run | ❌ match (high) |
| `MAIN/Cerave.jpg` (with pump) | match | ✅ match (high) | ✅ match (high) | ✅ match (high) |

Both models answer "pump intact" / "same pump present". Where the pump
should be, the bottle has a short white screw collar, and the models take
it for the pump even when the note describes exactly that case.

### Known limit

**A missing pump (a small part on top of the right product) is not
detected.** With a matching weight, such a return is approved
automatically. The weight check only catches it if the pump weighs more
than the weight tolerance (10%, about 42 g for this 416 g product). A product note does not help with these models, so we
do not add per-product notes for now. Staff can still see the kiosk photo of
every return.

## Experiment: more reference photos and a close-up (2026-10-08)

Two more ideas for the missing pump, tested with Claude Haiku 4.5 (`us.`
profile called from ca-central-1, prompt v3 unchanged, throwaway scripts,
not in the app). The crop is the middle 50% of the photo's width at full
height: cropping the height as well would cut the top of the pump off.

**A and B: an official product photo as a second reference.** The official
photos were downloaded from the manufacturer/retailer site. In B the kiosk
photo was also replaced by its crop. One call each.

| Kiosk photo | Should be | A: kiosk reference + official photo | B: A, with the cropped kiosk photo |
|---|---|---|---|
| `cerave_nopump.jpg` | review | ❌ match | ✅ mismatch (pump missing) |
| `cerave_nopump_close.jpg` | review | ❌ match | ❌ match |
| `MAIN/Cerave.jpg` (with pump) | match | ✅ match | ✅ match |
| `somersby_ok.jpg` | match | ❌ **different product** | ❌ **different product** |

Time 1.5–2.4 s, about $0.005–0.006 per check.

**A reference photo must show the exact packaging the store sells.** The
official Somersby photo shows the newer English "BLACKBERRY" label; our can
has the bilingual "Cidre aromatisé MÛRE" label (mûre is French for
blackberry). Haiku answered "Mûre (Mulberry), not the Blackberry variant"
with high confidence, so with a matching weight the kiosk would **decline
a correct item**. A re-run gave the same answer. So: no official or
marketing photos as references, only photos of the packaging we sell.

**C: the full kiosk photo plus a close-up.** Only the kiosk reference
photo. The kiosk photo is sent twice: the full photo, then its crop with
the text "Close-up of the same kiosk photo (the middle part of the photo
above, enlarged)". The full photo keeps big items safe (the crop cuts the
shoe box off). Each test was run twice.

| Kiosk photo | Should be | Run 1 | Run 2 |
|---|---|---|---|
| `cerave_nopump.jpg` | review | ❌ match ("intact pump") | ❌ match |
| `cerave_nopump_close.jpg` | review | ❌ match | ❌ match |
| `MAIN/Cerave.jpg` (with pump) | match | ✅ match | ✅ match |
| `nb_emptybox.jpg` (one shoe) | review, not a different product | ✅ missing part | ✅ missing part |

Time 1.5–2.7 s, ~4,800 input / 113–120 output tokens, about $0.0059 per
check (vs ~$0.0045 with one kiosk photo).

**Result:** none of these catches the missing pump reliably, so the
missing pump stays a known limit (see above) and we stop experimenting.
The app keeps one kiosk reference photo and one kiosk photo per check.

## Experiment: describe the kiosk photo first (2026-10-08)

Last pump idea, Claude Haiku 4.5, one call per step (throwaway script).

- **Step 1:** only the kiosk photo and the product name, no reference, and
  a neutral question: "List the visible parts of this item and describe
  the top of the bottle. Is anything that normally belongs on this product
  missing?"
- **Step 2:** the same conversation continues with the reference photo and
  the normal prompt v3 question.

| Kiosk photo | Should be | Step 1 alone | Steps 1 + 2 |
|---|---|---|---|
| `cerave_nopump.jpg` | pump missing | ✅ "simple white screw-on cap... the pump dispenser appears to be missing" | ✅ mismatch (pump missing) |
| `cerave_nopump_close.jpg` | pump missing | ❌ sees a "white pump dispenser"; says a "protective pump cap" is missing (no such part) | ⚠️ mismatch, for the wrong reason (the made-up cap) |
| `MAIN/Cerave.jpg` (see the correction) | pump missing | ❌ sees a pump, then says the made-up cap is missing | ⚠️ mismatch (medium), for the wrong reason (the made-up cap) |

**Correction:** shortly before this run, `MAIN/Cerave.jpg` had been
replaced by a photo of the bottle **without** its pump. So all three kiosk
photos had no pump, and step 2 compared them with a no-pump reference. This
run had no photo with the pump, so it shows nothing about false alarms on a
complete item.

The two steps take 5.1–6.0 s together (more than the 5-second timeout) and
cost about $0.008 per check. Step 1 spotted the missing pump on only 1 of
the 3 no-pump photos; on the other two it saw a pump and named a missing
part that does not exist.

**Result:** the pump experiments stop here. The missing pump is a known
limit (see above).

## New photo set at 1920x1080, 3 runs each (2026-10-08)

**Camera:** until now the kiosk agent captured at **640x480**
(`CAMERA_WIDTH`/`CAMERA_HEIGHT` in `kiosk_agent/.env`). The webcam (Logitech
C920) can do up to 2304x1536, but Claude scales big images down to about
1.15 megapixels (a 1920x1080 photo costs ~1,600 input tokens), so
**1920x1080** is enough: ~210 ms and ~210 KB per photo. The kiosk's
`kiosk_agent/.env` is now set to 1920x1080 (a local, git-ignored file).

**Photos:** all new, taken with the kiosk webcam at 1920x1080 with the same
OpenCV settings as the agent (`camera/reference/` and `camera/test/`; the
older photos are in `camera/old/`). Each test photo was taken after lifting
the item and placing it again, so no test photo is a copy of its
reference. `wrong_item.jpg` is the CeraVe bottle, checked against the
Somersby reference.

**Setups** (Claude Haiku 4.5, `us.` profile called from ca-central-1, each
case run 3 times):

- **A:** prompt v3, as in the app (`evaluate_ai.py <model-id> 3`).
- **C:** A, plus for CeraVe only a separate closed question on the kiosk
  photo alone: "Look at the top of the bottle. Is a pump head with a side
  nozzle present? Answer pump_present: true/false." `false` would send the
  return to review.
- **B (Claude Sonnet):** not tested. No Sonnet model is enabled for this
  account on Bedrock (Sonnet 5.5: AccessDenied, "contact AWS Sales").

| Case | Should be | A: correct | C: correct |
|---|---|---|---|
| `somersby_ok.jpg` | approve | 3/3 | 3/3 (same as A) |
| `cerave_ok.jpg` (with pump) | approve | 3/3 | 3/3 (pump_present true 3/3) |
| `cerave_nopump.jpg` | review (missing part) | **0/3**: "all components intact... with pump" | **0/3**: pump_present **true** 3/3 |
| `shoes_ok.jpg` | approve | 3/3 | 3/3 (same as A) |
| `shoes_one.jpg` | review (missing part) | 3/3 | 3/3 (same as A) |
| `wrong_item.jpg` | decline (different product) | 3/3 | 3/3 (same as A) |
| **False alarms on the 3 OK photos** | | 0/9 | 0/9 |

The answers were word for word the same in all 3 runs (temperature 0).

| Setup | Time per check | Tokens in / out | Cost per check (est.) |
|---|---|---|---|
| A | 1.3–2.0 s | ~3,410 / 112–149 | ~$0.0045 |
| C, extra pump question | +0.7–1.2 s | ~1,615 / 15 | +$0.0019 |

All 24 calls together cost about $0.09.

**Result:** sharper, larger photos do not change the pump result. Haiku
handles the wrong product, the missing shoe and the correct items every
time, but it reads the short white screw collar of the bottle as a pump,
even when asked about the pump directly. The missing pump stays a known
limit.

## Decision (2026-10-08): Claude Haiku 4.5

- **Default model in dev:** `us.anthropic.claude-haiku-4-5-20251001-v1:0`
  with prompt v3. The cost (about $0.0045 per return) is acceptable for us.
- **Region:** the app keeps calling Bedrock in ca-central-1. A test run from
  ca-central-1 gave the same answers as from us-east-1 (1.5–2.1 s per check).
  Photos may be processed in Canada or the US (see above).
- **To switch model:** change only `bedrock_model_id` and
  `bedrock_model_regions` in `infra/terraform/environments/dev/main.tf`
  (`aws bedrock get-inference-profile` lists the regions).
- **Locally:** `IMAGE_VERIFIER` stays `none` by default; set
  `BEDROCK_MODEL_ID` in your own `.env` to try a model.
- **Known limit:** the missing pump (see the experiment above).

## Known issue: reference photos expire after 90 days

The S3 lifecycle rule on the evidence bucket (`expire-evidence`,
`infra/terraform/modules/evidence_s3/main.tf`) has an empty filter, so it
deletes **every** object after 90 days, including the reference photos
under `reference/`. After that the AI check has no reference and answers
"uncertain", so every return goes to employee review. Fix later: limit the
rule to the `evidence/` prefix. Terraform is unchanged for now.
