"""
The "slot" an AI photo checker plugs into. A verifier looks at the item photo
and says whether it shows the expected product: match, mismatch or uncertain.
The default is NoAIVerifier, which checks nothing. IMAGE_VERIFIER=bedrock
switches on the real AI check (bedrock_verifier.py).
"""
import logging
import re
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

log = logging.getLogger("autorefund.verification")

MATCH = "match"
MISMATCH = "mismatch"
UNCERTAIN = "uncertain"
RESULTS = (MATCH, MISMATCH, UNCERTAIN)

# Same length as verification_signals.reason, so a chatty verifier can't
# make saving the return fail.
MAX_REASON_LENGTH = 500
# The AI's item phrase ("a can of cider") can be shown to the customer, so
# it is kept short.
MAX_ITEM_LENGTH = 60


@dataclass(frozen=True)
class ExpectedProduct:
    """What the photo should show.

    Plain data instead of the database Product: the verifier runs in its own
    thread, and database objects must not be used from another thread.
    """
    product_id: str
    name: str
    category: str | None
    # Storage keys of the product's reference photos (plain strings, so they
    # are safe to use from the verifier's thread).
    reference_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerificationResult:
    result: str               # match | mismatch | uncertain
    confidence: float | None  # 0.0 to 1.0; None when nothing was measured
    reason: str               # short, for staff
    # What the AI says the kiosk photo shows ("a can of cider"), or None.
    detected_item: str | None = None
    # True only when the AI is sure the photo shows a different KIND of
    # product. The one AI answer that may decline a return.
    different_product: bool = False


class ImageVerifier(ABC):
    # Saved with every result, so staff can see exactly what did the check.
    name: str = "unnamed"
    # False only for NoAIVerifier. The return rules ignore results from a
    # verifier that isn't a real check.
    is_real_check: bool = True

    @abstractmethod
    def verify(self, photo: bytes, expected: ExpectedProduct) -> VerificationResult:
        """Say whether the JPEG ``photo`` shows the ``expected`` product."""


class NoAIVerifier(ImageVerifier):
    """NOT A REAL CHECK. Used when no AI verifier is configured.

    It never looks at the photo. It always answers "uncertain", so a result
    from it can never be mistaken for a pass. Project rule: never pretend a
    check happened when it didn't.
    """
    name = "none"
    is_real_check = False

    def verify(self, photo: bytes, expected: ExpectedProduct) -> VerificationResult:
        return VerificationResult(UNCERTAIN, None, "No AI verifier configured")


VERIFIER_NAMES = ("none", "bedrock")


def build_verifier(config, storage=None) -> ImageVerifier:
    """Choose the verifier from the IMAGE_VERIFIER setting (default "none").
    ``storage`` is where the Bedrock verifier reads reference photos from."""
    name = str(config.get("IMAGE_VERIFIER", "none")).strip().lower()
    if name == "none":
        return NoAIVerifier()
    if name == "bedrock":
        model_id = config.get("BEDROCK_MODEL_ID")
        if not model_id:
            raise RuntimeError("IMAGE_VERIFIER=bedrock requires BEDROCK_MODEL_ID.")
        # Imported here because bedrock_verifier.py imports this file.
        from app.verification.bedrock_verifier import BedrockVerifier
        return BedrockVerifier(storage, model_id, region=config.get("AWS_REGION"),
                               timeout_seconds=config.get("IMAGE_VERIFIER_TIMEOUT_SECONDS", 5))
    # Refuse to start rather than quietly using "none": someone who
    # thinks AI checks are on must not be misled.
    raise RuntimeError(f"Unknown IMAGE_VERIFIER={name!r}. Must be one of {VERIFIER_NAMES}.")


def verify_safely(verifier: ImageVerifier, photo: bytes, expected: ExpectedProduct,
                  timeout_seconds: float) -> VerificationResult:
    """Run the verifier, turning a crash, a timeout or a nonsense answer
    into "uncertain". The return then goes to an employee, never approved."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(verifier.verify, photo, expected)
        answer = future.result(timeout=timeout_seconds)
    except TimeoutError:
        log.warning("Image verifier %r took longer than %ss", verifier.name, timeout_seconds)
        return VerificationResult(UNCERTAIN, None, "Image check took too long")
    except Exception:
        log.exception("Image verifier %r failed", verifier.name)
        return VerificationResult(UNCERTAIN, None, "Image check failed")
    finally:
        # Don't wait for a stuck verifier. Python can't stop the thread, so it
        # finishes in the background and its late answer is thrown away.
        executor.shutdown(wait=False)
    return _checked_answer(verifier, answer)


def _checked_answer(verifier: ImageVerifier, answer) -> VerificationResult:
    """Accept only a well-formed answer. A plug-in is outside code, so we
    don't trust it to follow the rules."""
    if not _is_well_formed(answer):
        log.warning("Image verifier %r gave an invalid answer: %r", verifier.name, answer)
        return VerificationResult(UNCERTAIN, None, "Image check gave an invalid answer")
    reason = answer.reason.strip()[:MAX_REASON_LENGTH] or "No reason given"
    return VerificationResult(answer.result, answer.confidence, reason,
                              plain_item(answer.detected_item), answer.different_product)


def plain_item(text) -> str | None:
    """The AI's item phrase as short plain text, or None. The customer may
    see it, so only letters, digits, spaces and simple punctuation are kept."""
    if not isinstance(text, str):
        return None
    text = re.sub(r"[^\w\s',.&()/-]", "", text)
    text = " ".join(text.split()).strip(" .")
    return text[:MAX_ITEM_LENGTH].strip() or None


def _is_well_formed(answer) -> bool:
    if not isinstance(answer, VerificationResult):
        return False
    if answer.result not in RESULTS or not isinstance(answer.reason, str):
        return False
    if answer.detected_item is not None and not isinstance(answer.detected_item, str):
        return False
    if not isinstance(answer.different_product, bool):
        return False
    # A different product is always a mismatch; anything else is a mix-up.
    if answer.different_product and answer.result != MISMATCH:
        return False
    if answer.confidence is None:
        return True
    # bool is a kind of int in Python, but True is not a confidence.
    if isinstance(answer.confidence, bool) or not isinstance(answer.confidence, (int, float)):
        return False
    return 0.0 <= answer.confidence <= 1.0
