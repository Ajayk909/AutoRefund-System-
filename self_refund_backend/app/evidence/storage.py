"""
Evidence images received from the kiosk agent.

The Core API never trusts a file name or path from a client. It validates the
bytes, generates its own object key, and records a SHA-256 hash.

Two backends, chosen by ``EVIDENCE_BACKEND``:

* ``local`` (default): files under ``CAPTURE_DIR``. Used for local Windows
  development and all tests.
* ``s3``: a private S3 bucket. ECS containers have no persistent disk, so
  dev/staging/production use this one. Credentials come from the ECS task
  role (boto3's default credential chain) - no static AWS keys anywhere.

Both expose the same three operations so callers do not know which backend is
active. ``build_storage()`` is called once, in ``create_app()``.
"""
import hashlib
import os
import secrets
from abc import ABC, abstractmethod

from app.errors import DomainError

JPEG_MAGIC = b"\xff\xd8\xff"


def _validate_jpeg(data, max_bytes):
    if not data:
        raise DomainError("INVALID_EVIDENCE", "The item photo could not be read.", 400)
    if len(data) > max_bytes:
        raise DomainError("EVIDENCE_TOO_LARGE", "The item photo is too large.", 413)
    if not data.startswith(JPEG_MAGIC):
        raise DomainError("INVALID_EVIDENCE", "The item photo must be a JPEG image.", 400)


class EvidenceStorage(ABC):
    @abstractmethod
    def store_jpeg(self, data, max_bytes):
        """Validate and save a JPEG. Returns (key, sha256)."""

    @abstractmethod
    def delete_stored(self, key):
        """Remove a stored object (used when the return is not created)."""

    @abstractmethod
    def exists(self, key):
        """True if a stored object is present for this key."""

    @abstractmethod
    def read(self, key):
        """Return (bytes, content_type), or None if the key does not exist."""


class LocalEvidenceStorage(EvidenceStorage):
    """Files under ``CAPTURE_DIR``. Keys look like ``captures/evidence_<hex>.jpg``."""

    def __init__(self, capture_dir):
        self.capture_dir = str(capture_dir)

    def _path(self, key):
        return os.path.join(self.capture_dir, os.path.basename(key))

    def store_jpeg(self, data, max_bytes):
        _validate_jpeg(data, max_bytes)
        os.makedirs(self.capture_dir, exist_ok=True)
        filename = f"evidence_{secrets.token_hex(16)}.jpg"
        with open(os.path.join(self.capture_dir, filename), "wb") as fh:
            fh.write(data)
        return f"captures/{filename}", hashlib.sha256(data).hexdigest()

    def delete_stored(self, key):
        if not key:
            return
        try:
            os.remove(self._path(key))
        except OSError:
            pass

    def exists(self, key):
        return bool(key) and os.path.isfile(self._path(key))

    def read(self, key):
        if not self.exists(key):
            return None
        with open(self._path(key), "rb") as fh:
            return fh.read(), "image/jpeg"


class S3EvidenceStorage(EvidenceStorage):
    """A private S3 bucket. Keys look like ``evidence/<hex>.jpg``.

    Credentials come from the ECS task role; ``client`` is only overridden in
    tests, with a stub/fake - no real AWS is contacted from unit tests.
    """

    def __init__(self, bucket, region=None, client=None):
        self.bucket = bucket
        if client is not None:
            self.client = client
        else:
            import boto3
            self.client = boto3.client("s3", region_name=region)

    def store_jpeg(self, data, max_bytes):
        _validate_jpeg(data, max_bytes)
        digest = hashlib.sha256(data).hexdigest()
        key = f"evidence/{secrets.token_hex(16)}.jpg"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data,
                               ContentType="image/jpeg", ServerSideEncryption="AES256")
        return key, digest

    def delete_stored(self, key):
        if not key:
            return
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception:
            pass

    def exists(self, key):
        if not key:
            return False
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def read(self, key):
        if not key:
            return None
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception:
            return None
        return obj["Body"].read(), obj.get("ContentType") or "image/jpeg"


def build_storage(config):
    """Choose the evidence backend from config."""
    backend = str(config.get("EVIDENCE_BACKEND", "local")).strip().lower()
    if backend == "s3":
        bucket = config.get("EVIDENCE_S3_BUCKET")
        if not bucket:
            raise RuntimeError("EVIDENCE_BACKEND=s3 requires EVIDENCE_S3_BUCKET.")
        return S3EvidenceStorage(bucket, region=config.get("AWS_REGION"))
    return LocalEvidenceStorage(config["CAPTURE_DIR"])
