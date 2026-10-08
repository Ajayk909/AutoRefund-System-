"""
Try the real AI photo check on our demo photos (results: docs/ai-evaluation.md).

    python evaluate_ai.py <model-id> [runs]

Uses the app's own BedrockVerifier (same prompt, same 5-second limit), so
this tests exactly what the kiosk does. The photos are in the `camera`
folder next to the repo: reference/ (reference photos) and test/ (kiosk
photos). Every run makes real, paid AWS calls: one per test, and `runs`
(default 1) repeats all tests to show how consistent the answers are.
"""
import os
import sys
import time

from app.verification.bedrock_verifier import BedrockVerifier
from app.verification.image_verifier import MATCH, ExpectedProduct, verify_safely

TIMEOUT_SECONDS = 5

SOMERSBY = "Somersby Blackberry Cider Can"
CERAVE = "CeraVe Acne Control Cleanser"
SHOES = "Navy/White Sneakers (in New Balance box)"

PHOTOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "camera")

# (kiosk photo, product on the receipt, its reference photo, what the kiosk should do)
TESTS = [
    ("somersby_ok.jpg", SOMERSBY, "somersby.jpg", "approve"),
    ("cerave_ok.jpg", CERAVE, "cerave.jpg", "approve"),
    ("cerave_nopump.jpg", CERAVE, "cerave.jpg", "review"),     # missing part
    ("shoes_ok.jpg", SHOES, "shoes.jpg", "approve"),
    ("shoes_one.jpg", SHOES, "shoes.jpg", "review"),           # missing part
    ("wrong_item.jpg", SOMERSBY, "somersby.jpg", "decline"),   # a CeraVe bottle
]


class FolderStorage:
    """Reads reference photos from a folder, like the app's photo storage."""

    def __init__(self, folder):
        self.folder = folder

    def read(self, key):
        with open(os.path.join(self.folder, key), "rb") as f:
            return f.read(), "image/jpeg"


class RecordingClient:
    """Passes calls to the real Bedrock client and keeps the last answer,
    so we can print its token counts."""

    def __init__(self, client):
        self.client = client
        self.last = None

    def converse(self, **request):
        self.last = self.client.converse(**request)
        return self.last


def kiosk_outcome(answer):
    """What the kiosk does with this AI answer, if the weight matched."""
    if answer.different_product:
        return "decline"
    return "approve" if answer.result == MATCH else "review"


def main(model_id, runs):
    # Stop before any paid call if a photo is missing.
    missing = [path for photo, _, reference, _ in TESTS
               for path in (os.path.join(PHOTOS, "test", photo),
                            os.path.join(PHOTOS, "reference", reference))
               if not os.path.exists(path)]
    if missing:
        sys.exit(f"Missing photos, no calls made: {missing}")

    verifier = BedrockVerifier(FolderStorage(os.path.join(PHOTOS, "reference")), model_id,
                               region=os.getenv("AWS_REGION"), timeout_seconds=TIMEOUT_SECONDS)
    verifier.client = RecordingClient(verifier.client)
    print(f"Model {model_id}, region {verifier.client.client.meta.region_name}\n")
    for run in range(1, runs + 1):
        print(f"===== Run {run} of {runs} =====")
        run_tests(verifier)


def run_tests(verifier):
    for number, (photo, product, reference, expected) in enumerate(TESTS, start=1):
        with open(os.path.join(PHOTOS, "test", photo), "rb") as f:
            kiosk_photo = f.read()
        verifier.client.last = None
        start = time.perf_counter()
        answer = verify_safely(verifier, kiosk_photo,
                               ExpectedProduct(f"test-{number}", product, None, (reference,)),
                               TIMEOUT_SECONDS)
        seconds = time.perf_counter() - start
        usage = (verifier.client.last or {}).get("usage", {})

        outcome = kiosk_outcome(answer)
        print(f"Test {number}: {photo} vs {reference} ({product})")
        print(f"  expected {expected}, got {outcome} -> {'OK' if outcome == expected else 'WRONG'}")
        print(f"  AI result {answer.result}, different product {answer.different_product}, "
              f"kiosk item: {answer.detected_item}")
        print(f"  reason: {answer.reason}")
        print(f"  {seconds:.2f} s, {usage.get('inputTokens')} input tokens, "
              f"{usage.get('outputTokens')} output tokens\n")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) == 3 else 1)
