"""
USB / web camera implementation based on OpenCV.

Raspberry Pi prototype: ``cv2.VideoCapture("/dev/video0", cv2.CAP_V4L2)``.
V4L2 and ``/dev/video*`` only exist on Linux, so on Windows we open the camera
by numeric index using DirectShow (fast to open, works with almost every USB
webcam) and fall back to Media Foundation. The capture / stream / release
behaviour is unchanged from the prototype.
"""
import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime

import cv2

from .barcode import decode_barcodes
from .base import CameraDevice

log = logging.getLogger("autorefund.hardware.camera")

_BACKENDS = {
    "dshow": getattr(cv2, "CAP_DSHOW", None),
    "msmf": getattr(cv2, "CAP_MSMF", None),
    "v4l2": getattr(cv2, "CAP_V4L2", None),
    "avfoundation": getattr(cv2, "CAP_AVFOUNDATION", None),
    "any": cv2.CAP_ANY,
}


def default_backends():
    """Preferred OpenCV capture APIs for the current operating system."""
    if sys.platform.startswith("win"):
        return ["dshow", "msmf", "any"]
    if sys.platform.startswith("linux"):
        return ["v4l2", "any"]
    if sys.platform == "darwin":
        return ["avfoundation", "any"]
    return ["any"]


class OpenCVCamera(CameraDevice):
    name = "opencv-usb-camera"

    def __init__(self, capture_dir, camera_index=None, backend="auto",
                 width=640, height=480):
        self.capture_dir = str(capture_dir)
        os.makedirs(self.capture_dir, exist_ok=True)

        if camera_index in (None, ""):
            self.indexes = [0, 1, 2, 3]
        else:
            self.indexes = [int(camera_index)]

        backend = (backend or "auto").lower()
        names = default_backends() if backend == "auto" else [backend]
        self.backends = [(n, _BACKENDS.get(n)) for n in names
                         if _BACKENDS.get(n) is not None]
        if not self.backends:
            raise ValueError(f"Unsupported CAMERA_BACKEND '{backend}'")

        self.width = width
        self.height = height

        self.cap = None
        self._current_source = None
        self.lock = threading.Lock()
        self.streaming = False

    @property
    def current_source(self):
        return self._current_source

    # -- open / release -----------------------------------------------------
    def _try_open_source(self, index, api):
        cap = cv2.VideoCapture(index, api)
        if cap is None or not cap.isOpened():
            return None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # ignored by some backends

        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            return None

        return cap

    def _open_camera(self):
        self._release_camera_no_lock()

        for backend_name, api in self.backends:
            for index in self.indexes:
                try:
                    cap = self._try_open_source(index, api)
                except Exception as exc:
                    log.warning("Failed opening camera %s via %s: %s",
                                index, backend_name, exc)
                    continue
                if cap is not None:
                    self.cap = cap
                    self._current_source = f"{index} ({backend_name})"
                    log.info("Camera opened: index %s via %s",
                             index, backend_name)
                    return True

        log.error("Could not open any USB camera (indexes=%s, backends=%s)",
                  self.indexes, [b for b, _ in self.backends])
        self.cap = None
        self._current_source = None
        return False

    def ensure_camera(self):
        with self.lock:
            if self.cap is not None and self.cap.isOpened():
                return True
            return self._open_camera()

    def _release_camera_no_lock(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
            self._current_source = None

    def release_camera(self):
        with self.lock:
            self.streaming = False
            self._release_camera_no_lock()

    # -- frames ---------------------------------------------------------------
    def _read_frame_no_lock(self):
        if self.cap is None or not self.cap.isOpened():
            if not self._open_camera():
                return None

        ok, frame = self.cap.read()
        if not ok or frame is None:
            # camera unplugged or stalled -> reopen once
            self._release_camera_no_lock()
            if not self._open_camera():
                return None
            ok, frame = self.cap.read()
            if not ok or frame is None:
                return None
        return frame.copy()

    def get_frame(self):
        with self.lock:
            return self._read_frame_no_lock()

    def scan_barcode(self):
        frame = self.get_frame()
        if frame is None:
            return None
        results = decode_barcodes(frame)
        return results[0] if results else None

    def capture_image(self):
        with self.lock:
            self.streaming = False
            time.sleep(0.15)

            frame = self._read_frame_no_lock()
            if frame is None:
                raise RuntimeError("Could not capture image from USB camera")

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"capture_{stamp}_{uuid.uuid4().hex[:6]}.jpg"
            filepath = os.path.join(self.capture_dir, filename)

            if not cv2.imwrite(filepath, frame):
                raise RuntimeError("Could not save captured image")

            self._release_camera_no_lock()

            return {
                "filename": filename,
                "relative_path": f"captures/{filename}",
                "full_path": filepath,
            }

    def generate_mjpeg_frames(self):
        self.streaming = True
        try:
            while self.streaming:
                frame = self.get_frame()
                if frame is None:
                    time.sleep(0.1)
                    continue

                ok, buffer = cv2.imencode(".jpg", frame)
                if not ok:
                    time.sleep(0.05)
                    continue

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + buffer.tobytes()
                    + b"\r\n"
                )
                time.sleep(0.08)
        finally:
            # also runs when the browser disconnects from the stream
            self.release_camera()
