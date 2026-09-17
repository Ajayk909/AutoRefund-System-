"""
Finding stored evidence images for staff.

Photos are taken by the kiosk agent and stored by evidence/storage.py.
Phase 5 moves the files to S3; the rest of the application only uses these
functions.
"""
import os


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
