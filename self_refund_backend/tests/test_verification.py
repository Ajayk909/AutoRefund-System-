"""
Phase 4 tests: the image verifier slot, the verification signals and how
decide() combines them. The first half needs no database; the second half
submits real returns through the kiosk agent (needs TEST_DATABASE_URL).
"""
import math
import threading
import time
import uuid

import pytest

from app.models import AuditLog, VerificationSignal
from app.returns import rules
from app.returns.policy import ReturnPolicy
from app.returns.states import APPROVED, PENDING_REVIEW
from app.verification.image_verifier import (MATCH, MISMATCH, UNCERTAIN, ExpectedProduct,
                                             ImageVerifier, NoAIVerifier, VerificationResult,
                                             build_verifier, verify_safely)
from tests.test_workflows import _item, _submit, _transaction

COLA = ExpectedProduct("p-1", "Coca Cola Can", "Beverage")
JPEG = b"\xff\xd8\xff fake jpeg"


# --- Fake verifiers (tests only: the app itself has no fake checks) ----------
class FixedVerifier(ImageVerifier):
    """Always gives the same answer, and remembers what it was asked."""
    name = "test-fixed"

    def __init__(self, result, confidence=0.9, reason="Test verifier answer"):
        self.answer = VerificationResult(result, confidence, reason)
        self.calls = []

    def verify(self, photo, expected):
        self.calls.append((photo, expected))
        return self.answer


class CrashingVerifier(ImageVerifier):
    name = "test-crash"

    def verify(self, photo, expected):
        raise RuntimeError("model server is down")


class SlowVerifier(ImageVerifier):
    """Hangs until the test lets it go, like an AI service that stopped answering."""
    name = "test-slow"

    def __init__(self):
        self.release = threading.Event()

    def verify(self, photo, expected):
        self.release.wait(timeout=10)
        return VerificationResult(MATCH, 0.99, "Too late to count")


class RawAnswerVerifier(ImageVerifier):
    """Returns whatever it is given, even nonsense."""
    name = "test-raw"

    def __init__(self, answer):
        self.answer = answer

    def verify(self, photo, expected):
        return self.answer


# --- NoAIVerifier and choosing a verifier -------------------------------------
def test_no_ai_verifier_is_clearly_not_a_real_check():
    verifier = NoAIVerifier()
    answer = verifier.verify(JPEG, COLA)
    assert answer == VerificationResult(UNCERTAIN, None, "No AI verifier configured")
    assert verifier.is_real_check is False and verifier.name == "none"


def test_build_verifier_defaults_to_no_ai():
    assert isinstance(build_verifier({}), NoAIVerifier)
    assert isinstance(build_verifier({"IMAGE_VERIFIER": " None "}), NoAIVerifier)


def test_build_verifier_refuses_an_unknown_name():
    # A typo must stop the app, not silently turn AI checks off.
    with pytest.raises(RuntimeError, match="Unknown IMAGE_VERIFIER"):
        build_verifier({"IMAGE_VERIFIER": "gpt-vision"})


# --- verify_safely --------------------------------------------------------------
def test_verify_safely_passes_a_good_answer_through():
    verifier = FixedVerifier(MISMATCH, 0.8, "Looks like a bottle, not a can")
    answer = verify_safely(verifier, JPEG, COLA, timeout_seconds=1)
    assert answer == VerificationResult(MISMATCH, 0.8, "Looks like a bottle, not a can")
    assert verifier.calls == [(JPEG, COLA)]


def test_verify_safely_turns_a_crash_into_uncertain():
    answer = verify_safely(CrashingVerifier(), JPEG, COLA, timeout_seconds=1)
    assert answer == VerificationResult(UNCERTAIN, None, "Image check failed")


def test_verify_safely_does_not_wait_for_a_slow_verifier():
    verifier = SlowVerifier()
    started = time.monotonic()
    try:
        answer = verify_safely(verifier, JPEG, COLA, timeout_seconds=0.1)
        elapsed = time.monotonic() - started
    finally:
        verifier.release.set()  # let the background thread finish
    assert answer == VerificationResult(UNCERTAIN, None, "Image check took too long")
    assert elapsed < 2


@pytest.mark.parametrize("bad_answer", [
    None,
    "match",
    VerificationResult("approved", 0.9, "not one of the three words"),
    VerificationResult(MATCH, 1.5, "confidence above 1"),
    VerificationResult(MATCH, -0.1, "confidence below 0"),
    VerificationResult(MATCH, math.nan, "confidence not a number"),
    VerificationResult(MATCH, True, "True is not a confidence"),
    VerificationResult(MATCH, "0.9", "confidence as text"),
    VerificationResult(MATCH, 0.9, None),
])
def test_verify_safely_turns_a_nonsense_answer_into_uncertain(bad_answer):
    answer = verify_safely(RawAnswerVerifier(bad_answer), JPEG, COLA, timeout_seconds=1)
    assert answer == VerificationResult(UNCERTAIN, None, "Image check gave an invalid answer")


def test_verify_safely_shortens_a_very_long_reason():
    long_reason = VerificationResult(MATCH, 0.9, "x" * 5000)
    answer = verify_safely(RawAnswerVerifier(long_reason), JPEG, COLA, timeout_seconds=1)
    assert answer.result == MATCH and len(answer.reason) == 500


# --- decide() -------------------------------------------------------------------
PHOTO_REQUIRED = ReturnPolicy(window_days=30, retry_limit_after_rejection=1,
                              require_photo_for_auto_approval=True)
PHOTO_OPTIONAL = ReturnPolicy(window_days=30, retry_limit_after_rejection=1,
                              require_photo_for_auto_approval=False)


def _weight(match):
    return rules.weight_signal({"match": match})


def _real_ai(result, reason="AI says so"):
    return rules.ai_signal(VerificationResult(result, 0.95, reason), FixedVerifier(result))


def _no_ai():
    return rules.ai_signal(NoAIVerifier().verify(JPEG, COLA), NoAIVerifier())


def test_all_checks_match_approves():
    signals = [_weight(True), rules.photo_signal(True), _real_ai(MATCH)]
    assert rules.decide(signals, PHOTO_REQUIRED) == \
        (APPROVED, "Weight matched expected product tolerance")


def test_weight_mismatch_goes_to_review():
    signals = [_weight(False), rules.photo_signal(True), _no_ai()]
    assert rules.decide(signals, PHOTO_REQUIRED) == \
        (PENDING_REVIEW, "Weight outside allowed tolerance")


@pytest.mark.parametrize("ai_result", [MISMATCH, UNCERTAIN])
def test_real_ai_mismatch_or_uncertain_goes_to_review(ai_result):
    signals = [_weight(True), rules.photo_signal(True), _real_ai(ai_result, "Not sure it's a can")]
    assert rules.decide(signals, PHOTO_REQUIRED) == (PENDING_REVIEW, "Not sure it's a can")


def test_no_ai_configured_does_not_change_the_decision():
    # Option A: the "no AI" row is saved for staff, but it isn't a check.
    signals = [_weight(True), rules.photo_signal(True), _no_ai()]
    assert rules.decide(signals, PHOTO_REQUIRED)[0] == APPROVED


def test_ai_match_can_never_approve_on_its_own():
    wrong_weight = [_weight(False), rules.photo_signal(True), _real_ai(MATCH)]
    assert rules.decide(wrong_weight, PHOTO_REQUIRED)[0] == PENDING_REVIEW

    no_weight = [rules.photo_signal(True), _real_ai(MATCH)]
    assert rules.decide(no_weight, PHOTO_REQUIRED) == (PENDING_REVIEW, "Weight was not checked")


def test_missing_photo_follows_the_policy():
    signals = [_weight(True), rules.photo_signal(False), _no_ai()]
    assert rules.decide(signals, PHOTO_REQUIRED) == \
        (PENDING_REVIEW, "No item photo could be captured")
    assert rules.decide(signals, PHOTO_OPTIONAL)[0] == APPROVED


def test_reason_comes_from_the_first_failing_check_in_a_fixed_order():
    # Given in a different order on purpose: weight is still reported first.
    signals = [_real_ai(MISMATCH, "Wrong product"), rules.photo_signal(False), _weight(False)]
    assert rules.decide(signals, PHOTO_REQUIRED) == \
        (PENDING_REVIEW, "Weight outside allowed tolerance")


def test_barcode_signal_only_when_a_barcode_was_sent():
    assert rules.barcode_signal(None) is None
    assert rules.barcode_signal("") is None
    assert rules.barcode_signal("111111").result == MATCH


# --- Real returns through the kiosk agent (database) -------------------------------
def _signals_of(refund_json):
    refund_id = uuid.UUID(refund_json["refund_id"])
    rows = VerificationSignal.query.filter_by(refund_id=refund_id).all()
    return {row.signal_type: row for row in rows}


def test_return_saves_its_checks_when_no_ai_is_configured(client):
    tx = _transaction(client)
    r = _submit(client, tx, _item(tx, "111111"), 250)
    refund = r.get_json()["refund"]
    assert r.status_code == 201 and refund["decision_status"] == "approved"

    signals = _signals_of(refund)
    assert set(signals) == {"weight", "photo", "ai"}  # no barcode was sent
    assert (signals["weight"].result, signals["weight"].confidence) == (MATCH, None)
    assert signals["photo"].result == MATCH
    ai = signals["ai"]
    assert (ai.result, ai.confidence, ai.source) == (UNCERTAIN, None, "none")
    assert ai.reason == "No AI verifier configured"

    audit = AuditLog.query.filter_by(event_type="refund_started").one()
    assert audit.details["verification_signals"] == \
        {"weight": "match", "photo": "match", "ai": "uncertain"}


def test_barcode_signal_saved_when_the_kiosk_sends_a_barcode(client):
    tx = _transaction(client)
    refund = _submit(client, tx, _item(tx, "111111"), 250, barcode="111111").get_json()["refund"]
    barcode = _signals_of(refund)["barcode"]
    assert (barcode.result, barcode.source) == (MATCH, "receipt-lookup")


def test_real_verifier_gets_the_photo_and_the_expected_product(client, app):
    app.image_verifier = FixedVerifier(MATCH, 0.97, "Red can, matches")
    tx = _transaction(client)
    refund = _submit(client, tx, _item(tx, "111111"), 250).get_json()["refund"]
    assert refund["decision_status"] == "approved"

    (photo, expected), = app.image_verifier.calls
    assert photo.startswith(b"\xff\xd8\xff")
    assert (expected.name, expected.category) == ("Coca Cola Can", "Beverage")
    ai = _signals_of(refund)["ai"]
    assert (ai.result, float(ai.confidence), ai.source) == (MATCH, 0.97, "test-fixed")


def test_ai_mismatch_sends_the_return_to_review(client, app, staff_headers):
    app.image_verifier = FixedVerifier(MISMATCH, 0.9, "Photo shows chips, not a can")
    tx = _transaction(client)
    refund = _submit(client, tx, _item(tx, "111111"), 250).get_json()["refund"]
    assert refund["decision_status"] == "pending_review"
    assert refund["weight_match"] is True
    assert refund["decision_reason"] == "Photo shows chips, not a can"

    # Staff see every check, in the order the rules read them.
    pending = client.get("/api/refunds/pending", headers=staff_headers).get_json()["refunds"]
    shown = pending[0]["verification_signals"]
    assert [s["signal_type"] for s in shown] == ["weight", "photo", "ai"]
    assert shown[2] == {"signal_type": "ai", "result": "mismatch", "confidence": 0.9,
                        "reason": "Photo shows chips, not a can", "source": "test-fixed"}


def test_ai_match_cannot_approve_a_wrong_weight(client, app):
    app.image_verifier = FixedVerifier(MATCH, 1.0)
    tx = _transaction(client)
    refund = _submit(client, tx, _item(tx, "222222"), 999).get_json()["refund"]
    assert refund["decision_status"] == "pending_review"
    assert refund["decision_reason"] == "Weight outside allowed tolerance"


def test_crashing_verifier_sends_the_return_to_review(client, app):
    app.image_verifier = CrashingVerifier()
    tx = _transaction(client)
    r = _submit(client, tx, _item(tx, "111111"), 250)
    assert r.status_code == 201  # the customer still gets an answer
    assert r.get_json()["refund"]["decision_status"] == "pending_review"
    assert r.get_json()["refund"]["decision_reason"] == "Image check failed"


def test_slow_verifier_sends_the_return_to_review(client, app):
    app.image_verifier = SlowVerifier()
    app.config["IMAGE_VERIFIER_TIMEOUT_SECONDS"] = 0.2
    tx = _transaction(client)
    try:
        refund = _submit(client, tx, _item(tx, "111111"), 250).get_json()["refund"]
    finally:
        app.image_verifier.release.set()
    assert refund["decision_status"] == "pending_review"
    assert refund["decision_reason"] == "Image check took too long"


def test_real_verifier_is_not_called_without_a_photo(client, app):
    app.image_verifier = FixedVerifier(MATCH)
    app.mock_camera.connected = False
    tx = _transaction(client)
    refund = _submit(client, tx, _item(tx, "111111"), 250).get_json()["refund"]
    assert app.image_verifier.calls == []
    assert refund["decision_status"] == "pending_review"
    ai = _signals_of(refund)["ai"]
    assert (ai.result, ai.reason) == (UNCERTAIN, "No photo to check")


def test_idempotent_replay_does_not_save_the_checks_twice(client):
    tx = _transaction(client)
    item = _item(tx, "111111")
    key = {"Idempotency-Key": "verify-replay-0001"}
    first = _submit(client, tx, item, 250, headers=key).get_json()["refund"]
    _submit(client, tx, item, 250, headers=key)
    assert len(_signals_of(first)) == 3
