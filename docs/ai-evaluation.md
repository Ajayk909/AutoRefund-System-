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
  the weight is far too low anyway, so that return goes to review either way.
  In test 2 the weight passes, so the AI's wrong "match" means **the return is
  approved**. That case is not caught yet.
- **This is a small test:** 4 photos, one call each, so it is not a full
  accuracy measurement.

## Decision for now

- **Default model:** stays `ca.amazon.nova-lite-v1:0` with prompt v2: best
  result, cheapest, and the photos stay in Canada.
- **Default setting:** `IMAGE_VERIFIER` stays `none` until we switch it on.
- **Ideas for the missing-pump case** (not done yet):
  - a reference photo that shows the pump close up;
  - asking about the parts of each product specifically;
  - testing a stronger model.
