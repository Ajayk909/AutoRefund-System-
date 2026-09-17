"""Hardware-independent unit tests (no database, no devices)."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hardware.base import HardwareError  # noqa: E402
from hardware.scale_service import HidPostalScale, decode_dymo_packet  # noqa: E402
from hardware import barcode  # noqa: E402
from hardware.camera_service import OpenCVCamera, default_backends  # noqa: E402


def test_decode_grams_stable():
    r = decode_dymo_packet([3, 4, 2, 0, 0xFA, 0x00])  # 250 g
    assert r.weight_grams == 250.0 and r.stable and r.raw_unit == "g"


def test_decode_ounces_with_negative_exponent():
    r = decode_dymo_packet([3, 4, 11, 0xFF, 88, 0])  # 8.8 oz
    assert r.weight_grams == pytest.approx(249.48, abs=0.01)
    assert r.raw_unit == "oz"


def test_decode_pounds():
    r = decode_dymo_packet([3, 4, 12, 0xFE, 100, 0])  # 1.00 lb
    assert r.weight_grams == pytest.approx(453.59, abs=0.01)


def test_decode_zero_motion_and_errors():
    assert decode_dymo_packet([3, 2, 2, 0, 0, 0]).weight_grams == 0
    moving = decode_dymo_packet([3, 3, 2, 0, 100, 0])
    assert moving.weight_grams == 100 and moving.stable is False
    assert decode_dymo_packet([3, 5, 2, 0, 10, 0]).weight_grams == 0
    with pytest.raises(HardwareError):
        decode_dymo_packet([3, 6, 2, 0, 0, 0])
    with pytest.raises(HardwareError):
        decode_dymo_packet([3, 4])


def test_real_scale_absent_raises_hardware_error():
    # A VID/PID that is never attached -> clean HardwareError, not a crash
    scale = HidPostalScale(0xFFFF, 0xFFFE, timeout_ms=10)
    with pytest.raises(HardwareError):
        scale.read()
    assert scale.status()["connected"] is False


class _FakeHid:
    def __init__(self, packets):
        self.packets = list(packets)

    def read(self, size, timeout_ms=0):
        return self.packets.pop(0) if self.packets else []

    def close(self):
        pass


def test_scale_timeout_reuses_last_reading():
    scale = HidPostalScale()
    scale._device = _FakeHid([[3, 4, 2, 0, 100, 0]])
    assert scale.read().weight_grams == 100
    assert scale.read().weight_grams == 100  # no new report -> last value
    scale._device = _FakeHid([])
    scale._last_reading = None
    with pytest.raises(HardwareError):
        scale.read()


def test_default_backends_per_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert default_backends()[:2] == ["dshow", "msmf"]
    monkeypatch.setattr(sys, "platform", "linux")
    assert default_backends()[0] == "v4l2"


def test_camera_absent_is_graceful(tmp_path):
    cam = OpenCVCamera(tmp_path, camera_index=9, backend="any")
    assert cam.ensure_camera() is False
    assert cam.get_frame() is None
    with pytest.raises(RuntimeError):
        cam.capture_image()


@pytest.mark.parametrize("use_zbar", [True, False])
def test_barcode_decoder_reads_ean13(monkeypatch, use_zbar):
    cv2 = pytest.importorskip("cv2")
    if not hasattr(cv2, "barcode"):
        pytest.skip("OpenCV built without barcode module")
    # Render an EAN-13 barcode for 4006381333931 and decode it
    code = "4006381333931"
    L = ["0001101", "0011001", "0010011", "0111101", "0100011",
         "0110001", "0101111", "0111011", "0110111", "0001011"]
    G = ["0100111", "0110011", "0011011", "0100001", "0011101",
         "0111001", "0000101", "0010001", "0001001", "0010111"]
    R = ["1110010", "1100110", "1101100", "1000010", "1011100",
         "1001110", "1010000", "1000100", "1001000", "1110100"]
    parity = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
              "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"][int(code[0])]
    bits = "101"
    for i, ch in enumerate(code[1:7]):
        bits += (L if parity[i] == "L" else G)[int(ch)]
    bits += "01010"
    for ch in code[7:]:
        bits += R[int(ch)]
    bits += "101"
    module = 2
    img = np.full((300, (len(bits) + 40) * module, 3), 255, dtype=np.uint8)
    for i, b in enumerate(bits):
        if b == "1":
            x = (i + 20) * module
            img[50:250, x:x + module] = 0
    img = cv2.copyMakeBorder(img, 100, 100, 100, 100, cv2.BORDER_CONSTANT,
                             value=(255, 255, 255))
    if use_zbar and barcode._zbar_decode is None:
        pytest.skip("pyzbar/ZBar not installed on this machine")
    if not use_zbar:
        monkeypatch.setattr(barcode, "_zbar_decode", None)  # OpenCV fallback
    results = barcode.decode_barcodes(img)
    assert results and results[0]["barcode"] == code
