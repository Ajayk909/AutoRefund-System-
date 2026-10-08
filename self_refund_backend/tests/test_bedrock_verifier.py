"""
Phase 4: the Bedrock AI photo check. Every test uses a fake Bedrock client,
so no real AWS call is ever made. The last test submits a real return
through the kiosk agent (needs TEST_DATABASE_URL).
"""
import json
import threading
import uuid

import pytest

from app.models import VerificationSignal
from app.returns import rules
from app.verification.bedrock_verifier import BedrockVerifier
from app.verification.image_verifier import (MATCH, MISMATCH, UNCERTAIN, ExpectedProduct,
                                             build_verifier, verify_safely)
from tests.test_reference_images import _product, _upload
from tests.test_workflows import _item, _submit, _transaction

MODEL = "ca.amazon.nova-lite-v1:0"
KIOSK_PHOTO = b"\xff\xd8\xff kiosk photo"
REFERENCE = b"\x89PNG\r\n\x1a\n reference photo"
CAN = ExpectedProduct("p-1", "Somersby Blackberry Cider Can", "Beverage",
                      reference_keys=("reference/can.png",))


class FakeBedrockClient:
    """Answers converse() with a fixed reply text (or raises), and remembers
    what it was sent."""

    def __init__(self, reply="", error=None):
        self.reply = reply
        self.error = error
        self.calls = []
        self.release = None  # set to a threading.Event to make it hang

    def converse(self, **request):
        self.calls.append(request)
        if self.release:
            self.release.wait(timeout=10)
        if self.error:
            raise self.error
        return {"output": {"message": {"role": "assistant", "content": [{"text": self.reply}]}},
                "usage": {"inputTokens": 1000, "outputTokens": 40},
                "metrics": {"latencyMs": 900}}


class FakeStorage:
    def __init__(self, files):
        self.files = files

    def read(self, key):
        return self.files.get(key)


def _reply(same=True, damage=False, confidence="high", reason="Looks right", missing=False,
           item=None):
    answer = {"differences": "none", "same_product": same, "missing_part": missing,
              "obvious_damage": damage, "confidence": confidence, "reason": reason}
    if item is not None:
        answer["kiosk_item"] = item
    return json.dumps(answer)


def _verifier(client):
    storage = FakeStorage({"reference/can.png": (REFERENCE, "image/png")})
    return BedrockVerifier(storage, MODEL, client=client)


def _check(reply):
    return _verifier(FakeBedrockClient(reply)).verify(KIOSK_PHOTO, CAN)


# --- Turning the model's answer into match / mismatch / uncertain ------------------
def test_same_product_without_damage_and_sure_is_a_match():
    answer = _check(_reply(reason="Same purple Somersby can"))
    assert (answer.result, answer.confidence) == (MATCH, None)
    assert answer.reason == "Same purple Somersby can (AI confidence: high)"


@pytest.mark.parametrize("same, damage, missing, confidence", [
    (False, False, False, "high"),    # clearly a different product
    (True, True, False, "high"),      # right product, but damaged
    (True, False, True, "high"),      # right product, but a part is missing
    (True, False, True, "medium"),
    (False, False, False, "medium"),
])
def test_wrong_damaged_or_incomplete_product_is_a_mismatch(same, damage, missing, confidence):
    assert _check(_reply(same, damage, confidence, missing=missing)).result == MISMATCH


@pytest.mark.parametrize("same, damage, confidence", [
    (True, False, "medium"),   # probably right, but not sure enough to count
    (True, False, "low"),
    (False, False, "low"),     # a guess is not a "clearly different"
])
def test_unsure_answer_is_uncertain(same, damage, confidence):
    assert _check(_reply(same, damage, confidence)).result == UNCERTAIN


@pytest.mark.parametrize("same, missing, damage, confidence, different", [
    (False, False, False, "high", True),     # sure it's another kind of product
    (False, False, False, "medium", False),  # not sure enough to decline
    (True, True, False, "high", False),      # missing part: a person decides
    (True, False, True, "high", False),      # damage: a person decides
    (False, True, False, "high", False),     # mixed answer: a person decides
])
def test_only_a_sure_different_product_is_flagged(same, missing, damage, confidence, different):
    answer = _check(_reply(same, damage, confidence, missing=missing, item="a bottle"))
    assert answer.different_product is different


def test_kiosk_item_is_kept_and_shown_to_staff():
    answer = _check(_reply(same=False, reason="Not a can.", item="a bottle of face wash"))
    assert answer.detected_item == "a bottle of face wash"
    assert answer.reason == ("Not a can. Kiosk photo shows: a bottle of face wash. "
                             "(AI confidence: high)")


def test_missing_kiosk_item_is_fine():
    answer = _check(_reply(same=False))
    assert answer.different_product is True and answer.detected_item is None


def test_json_wrapped_in_a_code_block_is_still_read():
    assert _check("```json\n" + _reply() + "\n```").result == MATCH


@pytest.mark.parametrize("reply", [
    "Yes, this is the same can.",                     # no JSON at all
    '{"same_product": true, "obvious_damage": fal',   # cut off
    _reply(confidence="very high"),
    _reply().replace('"same_product": true', '"same_product": "yes"'),
    json.dumps({"same_product": True, "missing_part": False, "obvious_damage": False,
                "confidence": "high", "reason": "ok"}),  # no "differences"
    _reply().replace('"missing_part": false', '"missing_part": null'),
    "[]",
])
def test_bad_reply_is_uncertain(reply):
    answer = _check(reply)
    assert (answer.result, answer.reason) == (UNCERTAIN, "AI answer could not be read")


# --- What is sent to Bedrock -------------------------------------------------------
def test_sends_reference_photo_kiosk_photo_and_product_name():
    client = FakeBedrockClient(_reply())
    _verifier(client).verify(KIOSK_PHOTO, CAN)

    (request,) = client.calls
    assert request["modelId"] == MODEL
    assert request["inferenceConfig"]["temperature"] == 0
    content = request["messages"][0]["content"]
    images = [block["image"] for block in content if "image" in block]
    assert images == [{"format": "png", "source": {"bytes": REFERENCE}},
                      {"format": "jpeg", "source": {"bytes": KIOSK_PHOTO}}]
    assert "Somersby Blackberry Cider Can" in content[-1]["text"]
    assert '"kiosk_item"' in content[-1]["text"]


@pytest.mark.parametrize("keys", [(), ("reference/deleted.jpg",)])
def test_no_reference_photo_is_uncertain_without_calling_aws(keys):
    client = FakeBedrockClient(_reply())
    expected = ExpectedProduct("p-1", "Somersby Blackberry Cider Can", "Beverage", keys)
    answer = _verifier(client).verify(KIOSK_PHOTO, expected)
    assert (answer.result, answer.reason) == (UNCERTAIN, "No reference photo for this product")
    assert client.calls == []


# --- AWS problems never crash the return -------------------------------------------
def test_aws_error_is_uncertain():
    verifier = _verifier(FakeBedrockClient(error=RuntimeError("AccessDeniedException")))
    answer = verify_safely(verifier, KIOSK_PHOTO, CAN, timeout_seconds=5)
    assert (answer.result, answer.reason) == (UNCERTAIN, "Image check failed")


def test_slow_aws_is_uncertain():
    client = FakeBedrockClient(_reply())
    client.release = threading.Event()
    try:
        answer = verify_safely(_verifier(client), KIOSK_PHOTO, CAN, timeout_seconds=0.2)
    finally:
        client.release.set()
    assert (answer.result, answer.reason) == (UNCERTAIN, "Image check took too long")


# --- Choosing Bedrock in config ----------------------------------------------------
def test_bedrock_needs_a_model_id():
    with pytest.raises(RuntimeError, match="BEDROCK_MODEL_ID"):
        build_verifier({"IMAGE_VERIFIER": "bedrock"})


def test_build_verifier_creates_the_bedrock_verifier():
    # Creating a boto3 client does not contact AWS.
    verifier = build_verifier({"IMAGE_VERIFIER": "bedrock", "BEDROCK_MODEL_ID": MODEL,
                               "AWS_REGION": "ca-central-1"}, storage=FakeStorage({}))
    assert isinstance(verifier, BedrockVerifier)
    assert verifier.name == "bedrock:ca.amazon.nova-lite-v1:0" and verifier.is_real_check


# --- A whole return, with the reference photo uploaded by an admin -----------------
def test_ai_mismatch_on_a_real_return_goes_to_review(client, app, staff_headers):
    cola = _product("Coca Cola Can")
    assert _upload(client, staff_headers, cola.product_id, REFERENCE, "ref.png").status_code == 201
    fake = FakeBedrockClient(_reply(same=False, confidence="medium",
                                    reason="Photo shows chips, not a can"))
    app.image_verifier = BedrockVerifier(app.evidence_storage, MODEL, client=fake)

    tx = _transaction(client)
    refund = _submit(client, tx, _item(tx, "111111"), 250).get_json()["refund"]

    # Weight matched, but the AI said no: an employee decides.
    assert refund["decision_status"] == "pending_review"
    assert refund["decision_reason"] == rules.AI_REVIEW_REASON
    images = [b["image"] for b in fake.calls[0]["messages"][0]["content"] if "image" in b]
    assert images[0]["source"]["bytes"] == REFERENCE  # read back from local storage

    ai = VerificationSignal.query.filter_by(refund_id=uuid.UUID(refund["refund_id"]),
                                            signal_type="ai").one()
    assert (ai.result, ai.source) == (MISMATCH, "bedrock:ca.amazon.nova-lite-v1:0")
    assert ai.reason == "Photo shows chips, not a can (AI confidence: medium)"
