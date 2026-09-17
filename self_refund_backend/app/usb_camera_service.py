import cv2
import os
import threading
import time
from datetime import datetime
from pyzbar.pyzbar import decode

CAPTURE_DIR = os.path.join(os.getcwd(), "captures")
os.makedirs(CAPTURE_DIR, exist_ok=True)


class USBCameraService:
    def __init__(self, camera_source=None):
        self.candidates = []
        if camera_source is not None:
            self.candidates.append(camera_source)

        self.candidates.extend([
            "/dev/video0",
            "/dev/video1",
            "/dev/video2",
            "/dev/video3",
            0,
            1,
            2,
            3,
        ])

        seen = set()
        cleaned = []
        for c in self.candidates:
            if str(c) not in seen:
                cleaned.append(c)
                seen.add(str(c))
        self.candidates = cleaned

        self.cap = None
        self.current_source = None
        self.lock = threading.Lock()
        self.streaming = False

    def _try_open_source(self, source):
        cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
        if cap is None or not cap.isOpened():
            return None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            return None

        return cap

    def scan_barcode(self):
        frame = self.get_frame()
        if frame is None:
            return None

        barcodes = decode(frame)
        for barcode in barcodes:
            barcode_data = barcode.data.decode("utf-8").strip()
            if barcode_data:
                return {
                    "barcode": barcode_data,
                    "type": barcode.type
                }

        return None

    def _open_camera(self):
        self._release_camera_no_lock()

        for source in self.candidates:
            try:
                cap = self._try_open_source(source)
                if cap is not None:
                    self.cap = cap
                    self.current_source = source
                    print(f"Camera opened successfully using source: {source}")
                    return True
            except Exception as e:
                print(f"Failed opening camera source {source}: {e}")

        print("Could not open any USB camera source")
        self.cap = None
        self.current_source = None
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
            self.current_source = None

    def release_camera(self):
        with self.lock:
            self.streaming = False
            self._release_camera_no_lock()

    def get_frame(self):
        with self.lock:
            if self.cap is None or not self.cap.isOpened():
                if not self._open_camera():
                    return None

            ok, frame = self.cap.read()
            if not ok or frame is None:
                self._release_camera_no_lock()
                if not self._open_camera():
                    return None
                ok, frame = self.cap.read()
                if not ok or frame is None:
                    return None

            return frame.copy()

    def capture_image(self):
        with self.lock:
            self.streaming = False
            time.sleep(0.15)

            if self.cap is None or not self.cap.isOpened():
                if not self._open_camera():
                    raise RuntimeError("Could not open USB camera")

            ok, frame = self.cap.read()
            if not ok or frame is None:
                self._release_camera_no_lock()
                if not self._open_camera():
                    raise RuntimeError("Could not reopen USB camera for capture")
                ok, frame = self.cap.read()
                if not ok or frame is None:
                    raise RuntimeError("Could not capture image from USB camera")

            frame = frame.copy()

            filename = f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            filepath = os.path.join(CAPTURE_DIR, filename)

            saved = cv2.imwrite(filepath, frame)
            if not saved:
                raise RuntimeError("Could not save captured image")

            self._release_camera_no_lock()

            return {
                "filename": filename,
                "relative_path": f"captures/{filename}",
                "full_path": filepath,
            }

    def generate_mjpeg_frames(self):
        self.streaming = True

        while self.streaming:
            frame = self.get_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            ok, buffer = cv2.imencode(".jpg", frame)
            if not ok:
                time.sleep(0.05)
                continue

            jpg_bytes = buffer.tobytes()

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                jpg_bytes +
                b"\r\n"
            )

            time.sleep(0.08)

        self.release_camera()