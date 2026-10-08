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

- **Default model:** stays `ca.amazon.nova-lite-v1:0` with prompt v3: best
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
through the `us.` or `global.` inference profiles, so **the photos are
processed in the US** (this run used `us.`, called from us-east-1). Nova
Lite's `ca.` profile keeps them in Canada.

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
