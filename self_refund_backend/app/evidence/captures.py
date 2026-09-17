"""
Item photos.

A photo is stored as ``captures/<camera name>_<capture_id>.jpg``. The
32-hex-character capture_id is unguessable, is given to the kiosk screen,
and is accepted only once, only if recent. Phase 5 moves the files to S3;
the rest of the application only uses these functions.
"""
import base64
import glob
import os
import re
import secrets
import time

from app.returns import repository as returns_repository

CAPTURE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def take_photo(camera, capture_dir):
    """Capture with the kiosk camera and register an unguessable capture id."""
    result = camera.capture_image()
    capture_id = secrets.token_hex(16)
    stem, _ = os.path.splitext(result["filename"])
    filename = f"{stem}_{capture_id}.jpg"
    dst = os.path.join(str(capture_dir), filename)
    os.replace(os.path.join(str(capture_dir), result["filename"]), dst)
    return {"capture_id": capture_id, "file_name": filename,
            "relative_path": f"captures/{filename}"}


def preview_data_url(capture_dir, filename):
    with open(os.path.join(str(capture_dir), filename), "rb") as fh:
        return "data:image/jpeg;base64," + base64.b64encode(fh.read()).decode("ascii")


def resolve_capture(capture_id, capture_dir, max_age_seconds):
    """Map a kiosk capture id to its image, only if it was taken by this
    backend recently and has not already been used as evidence."""
    if not capture_id or not CAPTURE_ID_RE.match(str(capture_id)):
        return None
    matches = glob.glob(os.path.join(str(capture_dir), f"*_{capture_id}.jpg"))
    if len(matches) != 1:
        return None
    path = matches[0]
    if time.time() - os.path.getmtime(path) > max_age_seconds:
        return None
    relative = f"captures/{os.path.basename(path)}"
    if returns_repository.image_in_use(relative):
        return None
    return relative


def normalize_capture_path(image_path):
    if not image_path:
        return None
    normalized = str(image_path).replace("\\", "/").strip()
    if normalized.startswith("captures/"):
        return normalized
    return f"captures/{os.path.basename(normalized)}"


def evidence_file(image_path, capture_dir):
    """Absolute path of a stored evidence image, or None if missing."""
    normalized = normalize_capture_path(image_path)
    if not normalized:
        return None
    path = os.path.join(str(capture_dir), os.path.basename(normalized))
    return path if os.path.isfile(path) else None
