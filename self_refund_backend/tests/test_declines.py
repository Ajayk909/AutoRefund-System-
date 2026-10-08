"""
Phase 4: when the kiosk may decline a return on its own.

A weight far away from the expected weight (more than WEIGHT_DECLINE_PERCENT)
can't be the right item. The customer is asked once to place the item again;
if it is still far off, the return is declined (status rejected, no staff
member) without paying for an AI check.

The AI may decline too, but only when the weight matched and it is sure the
photo shows a different kind of product. Anything subtler goes to review.
"""
import glob
import os
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models import Refund
from app.returns import rules
from app.returns.states import PENDING_REVIEW, REJECTED
from app.verification.bedrock_verifier import BedrockVerifier
from app.verification.image_verifier import MATCH, MISMATCH, plain_item
from tests.test_bedrock_verifier import MODEL, REFERENCE, FakeBedrockClient, _reply
from tests.test_reference_images import _product, _upload
from tests.test_verification import PHOTO_REQUIRED, FixedVerifier, _real_ai, _signals_of
from tests.test_workflows import _item, _submit, _transaction

CHIPS = SimpleNamespace(expected_weight_grams=150, weight_tolerance_percent=10)


def _far_off(grams):
    return rules.weight_check(CHIPS, 1, Decimal(grams), decline_percent=40)["far_off"]


# --- rules (no database) ---------------------------------------------------------
def test_far_off_starts_just_past_the_decline_percent():
    assert _far_off("90") is False and _far_off("210") is False  # exactly 40% off
    assert _far_off("89") is True and _far_off("211") is True
    assert _far_off("999") is True  # far too heavy counts too


def test_a_far_off_weight_declines_even_if_the_ai_says_match():
    weight = rules.weight_signal({"match": False, "far_off": True})
    signals = [weight, rules.photo_signal(True), _real_ai(MATCH)]
    assert rules.decide(signals, PHOTO_REQUIRED) == (REJECTED, rules.WEIGHT_DECLINE_MESSAGE)


def _ai_decline():
    return rules.Signal(rules.AI, MISMATCH, "Different product", "bedrock:test",
                        decline_message="Please visit the customer service desk.")


def test_the_ai_can_decline_when_the_weight_matched():
    signals = [rules.weight_signal({"match": True, "far_off": False}),
               rules.photo_signal(True), _ai_decline()]
    assert rules.decide(signals, PHOTO_REQUIRED) == (REJECTED, "Please visit the customer service desk.")


def test_the_ai_cannot_decline_when_the_weight_is_slightly_off():
    signals = [rules.weight_signal({"match": False, "far_off": False}),
               rules.photo_signal(True), _ai_decline()]
    assert rules.decide(signals, PHOTO_REQUIRED) == (PENDING_REVIEW, "Weight outside allowed tolerance")


# --- real returns through the kiosk agent (database) ------------------------------
def test_first_far_off_weight_asks_to_place_the_item_again(client, app):
    app.image_verifier = FixedVerifier(MATCH)
    tx = _transaction(client)
    r = _submit(client, tx, _item(tx, "222222"), 10)

    assert r.status_code == 409 and r.get_json()["code"] == "WEIGHT_CHECK_AGAIN"
    assert Refund.query.count() == 0
    assert app.image_verifier.calls == []
    # No evidence photo is kept for an attempt that created nothing.
    assert glob.glob(os.path.join(str(app.config["CAPTURE_DIR"]), "evidence_*")) == []


def test_still_far_off_after_placing_again_is_declined_without_ai(client, app, staff_headers):
    app.image_verifier = FixedVerifier(MATCH)
    tx = _transaction(client)
    r = _submit(client, tx, _item(tx, "222222"), 10, weight_rechecked=True)

    refund = r.get_json()["refund"]
    assert r.status_code == 201
    assert refund["decision_status"] == "rejected"
    assert refund["decision_reason"] == rules.WEIGHT_DECLINE_MESSAGE
    assert app.image_verifier.calls == []  # the AI was not paid for
    signals = _signals_of(refund)
    assert set(signals) == {"weight", "photo"}
    assert signals["weight"].reason == "Weight far outside the allowed range (declined)"

    # Staff see it in the log as a rejection that no employee made.
    logs = client.get("/api/refunds/logs", headers=staff_headers).get_json()["refunds"]
    assert (logs[0]["decision_status"], logs[0]["reviewed_by"]) == ("rejected", None)


def test_slightly_wrong_weight_still_goes_to_review(client, app):
    app.image_verifier = FixedVerifier(MATCH)
    tx = _transaction(client)
    refund = _submit(client, tx, _item(tx, "222222"), 180).get_json()["refund"]  # 20% off
    assert refund["decision_status"] == "pending_review"
    assert len(app.image_verifier.calls) == 1


def test_a_kiosk_decline_counts_as_an_attempt(client):
    tx = _transaction(client)
    item = _item(tx, "222222")
    assert _submit(client, tx, item, 10, weight_rechecked=True).status_code == 201
    assert _submit(client, tx, item, 10, weight_rechecked=True).status_code == 201  # retry limit 1
    r = _submit(client, tx, item, 150)
    assert r.status_code == 400 and r.get_json()["code"] == "TOO_MANY_ATTEMPTS"


# --- the AI's item phrase in the customer message ---------------------------------
def test_customer_message_uses_the_ai_item_phrase():
    assert rules.different_product_message("Coca Cola Can", "a bottle of face wash") == (
        "This doesn't look like Coca Cola Can. It looks like a bottle of face wash. "
        "This return can't be completed here. Please visit the customer service desk.")


def test_customer_message_without_an_item_phrase():
    assert rules.different_product_message("Coca Cola Can", None).startswith(
        "This doesn't look like the item on your receipt. ")


@pytest.mark.parametrize("raw, clean", [
    ("a bottle of face wash.", "a bottle of face wash"),
    ("Navy/White Sneakers", "Navy/White Sneakers"),  # a real Nova Lite answer
    ("<b>a *shiny*\n can</b>", "ba shiny can/b"),  # no markup or line breaks
    ("x" * 100, "x" * 60),
    ("  ", None),
    (None, None),
    (42, None),
])
def test_item_phrase_is_short_plain_text(raw, clean):
    assert plain_item(raw) == clean


# --- real returns with the (fake) Bedrock AI check ----------------------------------
DIFFERENT = dict(same=False, item="a bottle of face wash")


@pytest.mark.parametrize("grams, reply, status", [
    (250, _reply(**DIFFERENT), "rejected"),                          # sure: other product
    (250, _reply(confidence="medium", **DIFFERENT), "pending_review"),
    (250, _reply(missing=True, item="a can"), "pending_review"),
    (250, _reply(damage=True, item="a can"), "pending_review"),
    (287, _reply(**DIFFERENT), "pending_review"),                   # weight ~15% off
    (250, _reply(item="a can of cola"), "approved"),
])
def test_ai_declines_only_a_sure_different_product(client, app, staff_headers, grams, reply,
                                                   status):
    cola = _product("Coca Cola Can")
    assert _upload(client, staff_headers, cola.product_id, REFERENCE, "ref.png").status_code == 201
    app.image_verifier = BedrockVerifier(app.evidence_storage, MODEL,
                                         client=FakeBedrockClient(reply))
    tx = _transaction(client)
    refund = _submit(client, tx, _item(tx, "111111"), grams).get_json()["refund"]

    assert refund["decision_status"] == status
    if status == "rejected":
        assert refund["decision_reason"] == rules.different_product_message(
            "Coca Cola Can", "a bottle of face wash")
        # Staff still see the AI's own words.
        assert "Kiosk photo shows: a bottle of face wash." in _signals_of(refund)["ai"].reason
