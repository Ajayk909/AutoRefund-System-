"""Phase 3: S3 evidence backend, exercised entirely against a fake/stub S3
client - no real AWS is contacted, and boto3 need not even be installed
locally (it is only imported when no client is injected)."""
import io
import sys
import types

import pytest

from app.errors import DomainError
from app.evidence.storage import LocalEvidenceStorage, S3EvidenceStorage, build_storage

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200


class FakeS3Client:
    """Enough of boto3's S3 client surface to exercise S3EvidenceStorage."""

    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType=None, ServerSideEncryption=None):
        assert Bucket == "bucket"
        assert ServerSideEncryption == "AES256", "evidence objects must be encrypted"
        self.objects[Key] = (Body, ContentType)

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)
        body, content_type = self.objects[Key]
        return {"Body": io.BytesIO(body), "ContentType": content_type}


def _storage():
    return S3EvidenceStorage("bucket", client=FakeS3Client())


def test_store_read_delete_round_trip():
    storage = _storage()
    key, digest = storage.store_jpeg(JPEG, max_bytes=10_000)
    assert key.startswith("evidence/")
    assert len(digest) == 64
    assert storage.exists(key)

    data, content_type = storage.read(key)
    assert data == JPEG and content_type == "image/jpeg"

    storage.delete_stored(key)
    assert not storage.exists(key)
    assert storage.read(key) is None


def test_store_jpeg_validates_bytes_before_touching_s3():
    storage = _storage()
    with pytest.raises(DomainError):
        storage.store_jpeg(b"not a jpeg", max_bytes=10_000)
    assert storage.client.objects == {}


def test_store_jpeg_rejects_oversized_data():
    storage = _storage()
    with pytest.raises(DomainError):
        storage.store_jpeg(JPEG, max_bytes=10)
    assert storage.client.objects == {}


def test_delete_and_read_of_missing_key_do_not_raise():
    storage = _storage()
    storage.delete_stored("evidence/does-not-exist.jpg")  # no error
    assert storage.read("evidence/does-not-exist.jpg") is None
    assert not storage.exists("evidence/does-not-exist.jpg")
    assert storage.read(None) is None


def test_build_storage_defaults_to_local(tmp_path):
    storage = build_storage({"CAPTURE_DIR": tmp_path})
    assert isinstance(storage, LocalEvidenceStorage)


def test_build_storage_requires_bucket_for_s3():
    with pytest.raises(RuntimeError, match="EVIDENCE_S3_BUCKET"):
        build_storage({"EVIDENCE_BACKEND": "s3", "CAPTURE_DIR": "unused"})


def test_build_storage_selects_s3_backend(monkeypatch):
    """Faking the boto3 module itself proves build_storage's wiring without
    requiring boto3 to be installed or contacting real AWS."""
    fake_client = FakeS3Client()
    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.client = lambda service, region_name=None: fake_client
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    storage = build_storage({"EVIDENCE_BACKEND": "s3", "EVIDENCE_S3_BUCKET": "bucket",
                            "AWS_REGION": "ca-central-1"})
    assert isinstance(storage, S3EvidenceStorage)
    assert storage.bucket == "bucket"
    assert storage.client is fake_client
