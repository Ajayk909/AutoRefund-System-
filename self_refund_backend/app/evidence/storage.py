"""
Evidence images received from the kiosk agent.

The Core API never trusts a file name or path from a client. It validates the
bytes, generates its own name and records a SHA-256 hash. Phase 5 replaces the
local folder with S3 behind these same functions.
"""
import hashlib
import os
import secrets

from app.errors import DomainError

JPEG_MAGIC = b"\xff\xd8\xff"


def store_jpeg(data, capture_dir, max_bytes):
    """Validate and save an evidence JPEG. Returns (relative_path, sha256)."""
    if not data:
        raise DomainError("INVALID_EVIDENCE", "The item photo could not be read.", 400)
    if len(data) > max_bytes:
        raise DomainError("EVIDENCE_TOO_LARGE", "The item photo is too large.", 413)
    if not data.startswith(JPEG_MAGIC):
        raise DomainError("INVALID_EVIDENCE", "The item photo must be a JPEG image.", 400)
    os.makedirs(str(capture_dir), exist_ok=True)
    filename = f"evidence_{secrets.token_hex(16)}.jpg"
    with open(os.path.join(str(capture_dir), filename), "wb") as fh:
        fh.write(data)
    return f"captures/{filename}", hashlib.sha256(data).hexdigest()


def delete_stored(relative_path, capture_dir):
    """Remove a stored evidence file (used when the return is not created)."""
    if not relative_path:
        return
    try:
        os.remove(os.path.join(str(capture_dir), os.path.basename(relative_path)))
    except OSError:
        pass
