"""
Camera-based barcode decoding (used for receipt scanning through the webcam).

The Raspberry Pi prototype used ``pyzbar`` (ZBar). pyzbar ships the ZBar DLLs
inside its Windows wheel, but they need the "Visual C++ Redistributable for
Visual Studio 2013" (msvcr120.dll). If pyzbar cannot load, we fall back to
OpenCV's built-in detector, which only understands EAN-8/13 and UPC-A/E
(not Code 128, which receipt numbers such as ``RCP-1001`` normally use).

A USB HID barcode scanner does NOT go through this module: it types the code
as keyboard input into the kiosk UI (see the frontend ``useBarcodeScanner``).
"""
import logging

log = logging.getLogger("autorefund.hardware.barcode")

try:
    from pyzbar.pyzbar import decode as _zbar_decode  # type: ignore
    _ZBAR_ERROR = None
except Exception as exc:  # pragma: no cover - depends on the machine
    _zbar_decode = None
    _ZBAR_ERROR = exc
    log.warning(
        "pyzbar/ZBar not available (%s). Camera barcode scanning falls back "
        "to OpenCV (EAN/UPC only). On Windows install the Visual C++ 2013 "
        "Redistributable (x64).", exc)

_cv_detector = None


def backend_name():
    if _zbar_decode is not None:
        return "pyzbar"
    return "opencv-barcode (EAN/UPC only)"


def _decode_with_opencv(frame):
    global _cv_detector
    import cv2

    if not hasattr(cv2, "barcode"):
        return []
    if _cv_detector is None:
        _cv_detector = cv2.barcode.BarcodeDetector()

    results = []
    try:
        ok, infos, types, _points = _cv_detector.detectAndDecodeWithType(frame)
    except (AttributeError, cv2.error):
        return []
    if not ok:
        return []
    for data, kind in zip(infos, types):
        if data:
            results.append({"barcode": data.strip(), "type": str(kind)})
    return results


def decode_barcodes(frame):
    """Return a list of ``{"barcode": str, "type": str}`` found in the frame."""
    if frame is None:
        return []

    if _zbar_decode is not None:
        results = []
        for barcode in _zbar_decode(frame):
            data = barcode.data.decode("utf-8", errors="replace").strip()
            if data:
                results.append({"barcode": data, "type": barcode.type})
        return results

    return _decode_with_opencv(frame)
