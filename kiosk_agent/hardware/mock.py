"""
MOCK hardware for development and automated tests ONLY.

These classes never pretend to be real devices:
* ``is_mock = True`` is reported by ``/api/hardware/status``
* every captured image is stamped "MOCK CAMERA"
* the backend logs a warning at startup when a mock is active

Enable with ``HARDWARE_MODE=mock`` (or ``CAMERA_MODE`` / ``SCALE_MODE``).
Never use mock mode on a kiosk that processes real refunds.
"""
import os
import threading
import time
import uuid
from datetime import datetime

from .base import CameraDevice, HardwareError, ScaleDevice, ScaleReading


class MockScale(ScaleDevice):
    name = "mock-scale"
    is_mock = True

    def __init__(self, weight_grams=250.0):
        self._lock = threading.Lock()
        self.weight_grams = float(weight_grams)
        self.connected = True

    def set_weight(self, grams):
        with self._lock:
            self.weight_grams = float(grams)

    def read(self) -> ScaleReading:
        with self._lock:
            if not self.connected:
                raise HardwareError("Mock scale disconnected")
            grams = round(self.weight_grams, 2)
        return ScaleReading(grams, grams > 0, True, message="MOCK")

    def read_live(self, samples=3, delay_s=0.0) -> ScaleReading:
        return self.read()


class MockCamera(CameraDevice):
    name = "mock-camera"
    is_mock = True

    def __init__(self, capture_dir, width=640, height=480):
        self.capture_dir = str(capture_dir)
        os.makedirs(self.capture_dir, exist_ok=True)
        self.width = width
        self.height = height
        self.connected = True
        self.streaming = False
        #: barcode value returned by scan_barcode() (None = nothing in view)
        self.next_barcode = None

    @property
    def current_source(self):
        return "mock" if self.connected else None

    def ensure_camera(self):
        return self.connected

    def get_frame(self):
        if not self.connected:
            return None
        import cv2
        import numpy as np

        frame = np.full((self.height, self.width, 3), 40, dtype=np.uint8)
        cv2.putText(frame, "MOCK CAMERA", (40, self.height // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 200, 255), 3)
        cv2.putText(frame, datetime.now().isoformat(timespec="seconds"),
                    (40, self.height // 2 + 50), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (200, 200, 200), 2)
        return frame

    def scan_barcode(self):
        if not self.connected or not self.next_barcode:
            return None
        return {"barcode": self.next_barcode, "type": "MOCK"}

    def capture_image(self):
        import cv2

        frame = self.get_frame()
        if frame is None:
            raise RuntimeError("Mock camera disconnected")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"mock_capture_{stamp}_{uuid.uuid4().hex[:6]}.jpg"
        path = os.path.join(self.capture_dir, filename)
        cv2.imwrite(path, frame)
        return {"filename": filename, "relative_path": f"captures/{filename}",
                "full_path": path}

    def generate_mjpeg_frames(self):
        import cv2

        self.streaming = True
        try:
            while self.streaming:
                frame = self.get_frame()
                if frame is None:
                    time.sleep(0.1)
                    continue
                ok, buf = cv2.imencode(".jpg", frame)
                if ok:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                           + buf.tobytes() + b"\r\n")
                time.sleep(0.2)
        finally:
            self.streaming = False

    def release_camera(self):
        self.streaming = False
