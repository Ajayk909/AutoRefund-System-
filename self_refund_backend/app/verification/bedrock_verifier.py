"""
The real AI photo check (IMAGE_VERIFIER=bedrock). It sends the product's
reference photo(s) and the kiosk photo to an Amazon Bedrock model and asks:
is this the same product, is a part missing, and is it damaged?
Test results with real photos: docs/ai-evaluation.md.

It uses Bedrock's Converse API, which works the same for every model, so
switching model (e.g. Nova -> Claude) is only a change of BEDROCK_MODEL_ID.
AWS credentials come from the normal AWS chain: the AWS CLI profile locally,
the ECS task role in the cloud. No keys in code or .env.
"""
import json
import logging

from app.verification.image_verifier import (MATCH, MISMATCH, UNCERTAIN, ExpectedProduct,
                                             ImageVerifier, VerificationResult)

log = logging.getLogger("autorefund.verification")

# Every photo costs tokens and time; a few good reference photos are enough.
MAX_REFERENCE_IMAGES = 3
IMAGE_FORMATS = {"image/jpeg": "jpeg", "image/png": "png"}
CONFIDENCES = ("high", "medium", "low")

# "differences" comes first on purpose: the model has to compare the photos
# before it gives its true/false answers.
QUESTION = """You check returned items at a self-service return kiosk.
The reference photo(s) show the correct product, complete and undamaged: "{name}".
Compare the kiosk photo with the reference photo(s) carefully: the product,
the number of items, and every part (for example a pump, cap or lid, or one
item of a pair).
Reply ONLY with JSON, no other text, with the fields in this order:
{{"differences": "every visible difference, or none",
"same_product": true or false,
"missing_part": true or false (a part or item in the reference photo is not in the kiosk photo),
"obvious_damage": true or false,
"confidence": "high" or "medium" or "low",
"reason": "one short sentence for the store employee"}}"""


class BedrockVerifier(ImageVerifier):
    def __init__(self, storage, model_id, region=None, timeout_seconds=5.0, client=None):
        self.storage = storage
        self.model_id = model_id
        # Saved as the AI signal's source, so staff see which model checked.
        # The database column holds 50 characters.
        self.name = f"bedrock:{model_id}"[:50]
        if client is not None:
            self.client = client  # tests pass a fake client: no real AWS calls
        else:
            import boto3
            from botocore.config import Config
            # Give up when verify_safely() gives up, and don't retry: a retry
            # would only finish after its answer is already thrown away.
            self.client = boto3.client("bedrock-runtime", region_name=region, config=Config(
                connect_timeout=timeout_seconds, read_timeout=timeout_seconds,
                retries={"total_max_attempts": 1}))

    def verify(self, photo: bytes, expected: ExpectedProduct) -> VerificationResult:
        references = self._load_references(expected.reference_keys)
        if not references:
            return VerificationResult(UNCERTAIN, None, "No reference photo for this product")

        content = []
        for data, image_format in references:
            content.append({"text": "Reference photo of the correct product:"})
            content.append(_image(data, image_format))
        content.append({"text": "Photo taken at the return kiosk:"})
        content.append(_image(photo, "jpeg"))  # kiosk photos are always JPEG
        content.append({"text": QUESTION.format(name=expected.name)})

        # AWS errors are not caught here: verify_safely() logs them and
        # turns them into "uncertain".
        response = self.client.converse(
            modelId=self.model_id,
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": 400, "temperature": 0})
        usage = response.get("usage", {})
        log.info("Bedrock %s: %s ms, %s input tokens, %s output tokens", self.model_id,
                 response.get("metrics", {}).get("latencyMs"), usage.get("inputTokens"),
                 usage.get("outputTokens"))
        return answer_to_result(response["output"]["message"]["content"][0]["text"])

    def _load_references(self, keys):
        """[(bytes, "jpeg"/"png"), ...] for the reference photos we can read."""
        references = []
        for key in keys[:MAX_REFERENCE_IMAGES]:
            stored = self.storage.read(key)
            if stored is None:
                log.warning("Reference photo %s is missing from storage", key)
                continue
            data, content_type = stored
            references.append((data, IMAGE_FORMATS.get(content_type, "jpeg")))
        return references


def _image(data, image_format):
    return {"image": {"format": image_format, "source": {"bytes": data}}}


def answer_to_result(text: str) -> VerificationResult:
    """Turn the model's JSON reply into match / mismatch / uncertain."""
    answer = _parse_answer(text)
    if answer is None:
        log.warning("Bedrock reply was not the JSON we asked for: %r", text)
        return VerificationResult(UNCERTAIN, None, "AI answer could not be read")

    confidence = answer["confidence"]
    problem = (not answer["same_product"] or answer["missing_part"]
               or answer["obvious_damage"])
    # The model only says high/medium/low, so we keep that word for staff
    # instead of inventing a percentage.
    reason = f"{answer['reason'].strip()} (AI confidence: {confidence})"
    if not problem and confidence == "high":
        return VerificationResult(MATCH, None, reason)
    if problem and confidence in ("high", "medium"):
        return VerificationResult(MISMATCH, None, reason)
    return VerificationResult(UNCERTAIN, None, reason)


def _parse_answer(text):
    """The reply as a dict, or None if it isn't exactly the shape we asked for."""
    # Models often wrap JSON in ```json ... ``` anyway, so take only the {...}.
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        return None
    try:
        answer = json.loads(text[start:end + 1])
    except ValueError:
        return None
    if not isinstance(answer, dict):
        return None
    for field in ("same_product", "missing_part", "obvious_damage"):
        if not isinstance(answer.get(field), bool):
            return None
    for field in ("differences", "reason"):
        if not isinstance(answer.get(field), str):
            return None
    if answer.get("confidence") not in CONFIDENCES:
        return None
    return answer
