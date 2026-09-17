"""
Finding stored evidence images for staff.

Photos are taken by the kiosk agent and stored by evidence/storage.py, behind
whichever backend (local folder or S3) ``app.evidence_storage`` was built
with. Callers never touch the filesystem or S3 directly.
"""


def has_image(image_path, storage):
    return bool(image_path) and storage.exists(image_path)
