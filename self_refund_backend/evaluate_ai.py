"""
Try the real AI photo check on our demo photos (results: docs/ai-evaluation.md).

    python evaluate_ai.py <model-id> [photo-folder]

Uses the app's own BedrockVerifier (same prompt, same 5-second limit), so
this tests exactly what the kiosk does. The photo folder (default: the
`camera` folder next to the repo) holds MAIN/ (reference photos) and test/
(kiosk photos). Every run makes real, paid AWS calls: one per test.
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

# (kiosk photo, product on the receipt, its reference photo, what the kiosk should do)
TESTS = [
    ("somersby_ok.jpg", SOMERSBY, "Somersby.jpg", "approve"),
    ("cerave_nopump.jpg", CERAVE, "Cerave.jpg", "review"),    # pump missing
    ("nb_emptybox.jpg", SHOES, "NB.jpg", "review"),            # one shoe; weight declines first
    ("cerave_nopump.jpg", SOMERSBY, "Somersby.jpg", "decline"),  # wrong product
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


def main(model_id, photo_folder):
    verifier = BedrockVerifier(FolderStorage(os.path.join(photo_folder, "MAIN")), model_id,
                               region=os.getenv("AWS_REGION"), timeout_seconds=TIMEOUT_SECONDS)
    verifier.client = RecordingClient(verifier.client)
    print(f"Model {model_id}, region {verifier.client.client.meta.region_name}\n")

    for number, (photo, product, reference, expected) in enumerate(TESTS, start=1):
        with open(os.path.join(photo_folder, "test", photo), "rb") as f:
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
    default_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "camera")
    main(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else default_folder)
