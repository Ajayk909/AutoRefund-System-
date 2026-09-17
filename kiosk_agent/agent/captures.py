"""
Item photos taken by the kiosk camera and kept locally until they are sent.

A capture id is unguessable, single use and expires. The file is deleted as
soon as the Core API has answered the submission that used it.
"""
import os
import re
import secrets
from datetime import timedelta

from agent.store import now

CAPTURE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def take_photo(camera, capture_dir, store):
    result = camera.capture_image()
    capture_id = secrets.token_hex(16)
    stem, _ = os.path.splitext(result["filename"])
    file_name = f"{stem}_{capture_id}.jpg"
    os.replace(os.path.join(str(capture_dir), result["filename"]),
               os.path.join(str(capture_dir), file_name))
    store.add_capture(capture_id, file_name)
    return {"capture_id": capture_id, "file_name": file_name}


def usable_capture(capture_id, capture_dir, store, max_age_seconds):
    """The capture's file path if it exists, is unused and is recent."""
    if not capture_id or not CAPTURE_ID_RE.match(str(capture_id)):
        return None
    row = store.get_capture(capture_id)
    if not row or row["used_at"]:
        return None
    from datetime import datetime
    if datetime.fromisoformat(row["created_at"]) < now() - timedelta(seconds=max_age_seconds):
        return None
    path = os.path.join(str(capture_dir), row["file_name"])
    return path if os.path.isfile(path) else None


def consume(capture_id, path, store):
    """Mark used and delete the local file (the Core API has answered)."""
    if capture_id:
        store.mark_capture_used(capture_id)
    if path:
        try:
            os.remove(path)
        except OSError:
            pass
