"""
Manual hardware check for the USB camera (run on the kiosk PC):

    python check_camera.py

Tries camera indexes 0-3 with every capture backend available on this OS
(Windows: DirectShow and Media Foundation), saves one test photo per working
camera into captures/, and prints the CAMERA_INDEX / CAMERA_BACKEND values to
put in .env. Also reports which barcode decoder is available.
"""
import cv2

from config import Config
from hardware import barcode
from hardware.camera_service import OpenCVCamera, default_backends

print(f"OpenCV {cv2.__version__}")
print(f"Barcode decoder: {barcode.backend_name()}")
print(f"Capture folder: {Config.CAPTURE_DIR}")
print()

found = False
for backend in default_backends():
    if backend == "any":
        continue
    for index in range(4):
        cam = OpenCVCamera(Config.CAPTURE_DIR, camera_index=index, backend=backend)
        if not cam.ensure_camera():
            print(f"  index {index} via {backend}: not available")
            continue
        frame = cam.get_frame()
        if frame is None:
            print(f"  index {index} via {backend}: opened but no image")
            continue
        found = True
        h, w = frame.shape[:2]
        result = cam.capture_image()  # releases the camera afterwards
        print(f"  index {index} via {backend}: OK {w}x{h} -> {result['full_path']}")
        codes = barcode.decode_barcodes(frame)
        if codes:
            print(f"      barcode in view: {codes}")

print()
if found:
    print("Set CAMERA_INDEX=<index> and CAMERA_BACKEND=<backend> in .env "
          "(or leave them as auto).")
else:
    print("No camera could be opened. Check the USB cable, Windows camera "
          "privacy settings (Settings > Privacy & security > Camera > "
          "'Let desktop apps access your camera') and that no other app "
          "(Teams, Zoom, Camera app) is using it.")
    raise SystemExit(1)
