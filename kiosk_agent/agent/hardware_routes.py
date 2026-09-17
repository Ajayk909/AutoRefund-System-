"""Kiosk hardware endpoints served by the agent: scale, camera, barcode.

Moved from the Core API in Phase 2: only the agent touches hardware. Device
access goes through the ``hardware`` package interfaces, so a camera or scale
model can be replaced without touching these routes. Values returned here are
for DISPLAY; the agent reads the scale again itself when a return is submitted.
"""
import base64
import logging

import cv2
from flask import Response, current_app, jsonify

from agent import captures
from agent.routes import agent_bp as api_bp, store
from hardware import HardwareError, get_camera, get_scale
from hardware.barcode import backend_name as barcode_backend_name

log = logging.getLogger("autorefund.agent.hardware")


@api_bp.get("/scale/read")
def read_scale():
    try:
        reading = get_scale().read()
        return jsonify({
            "success": True,
            "connected": True,
            "weight_grams": reading.weight_grams,
            "stable": reading.stable,
        })
    except HardwareError as e:
        log.warning("Scale read failed: %s", e)
        return jsonify({
            "success": False,
            "connected": False,
            "weight_grams": 0,
            "stable": False,
            "message": "Scale unavailable"
        }), 503


@api_bp.get("/scale/live")
def get_live_scale():
    try:
        reading = get_scale().read_live()
        return jsonify({
            "success": True,
            "connected": True,
            "weight_grams": float(reading.weight_grams or 0),
            "stable": bool(reading.stable),
            "message": "Live weight fetched"
        })
    except HardwareError as e:
        log.warning("Live scale read failed: %s", e)
        return jsonify({
            "success": False,
            "connected": False,
            "message": "Scale unavailable",
            "weight_grams": 0,
            "stable": False
        }), 503


@api_bp.get("/hardware/status")
def hardware_status():
    """Diagnostics for setup/testing (which devices are real or mocked)."""
    camera = get_camera()
    scale = get_scale()
    return jsonify({
        "success": True,
        "camera": camera.status(),
        "scale": scale.status(),
        "barcode_decoder": barcode_backend_name(),
        "keyboard_scanner": "handled by the kiosk UI (USB HID keyboard mode)",
    })


@api_bp.get("/camera/health")
def camera_health():
    try:
        if not get_camera().ensure_camera():
            return jsonify({
                "success": False,
                "message": "USB camera could not be opened"
            }), 500

        return jsonify({
            "success": True,
            "message": "USB camera is working",
            "source": str(get_camera().current_source)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@api_bp.get("/camera/preview")
def camera_preview():
    try:
        frame = get_camera().get_frame()
        if frame is None:
            return jsonify({
                "success": False,
                "message": "Could not read frame from camera"
            }), 500

        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            return jsonify({
                "success": False,
                "message": "Could not encode frame"
            }), 500

        return Response(buffer.tobytes(), mimetype="image/jpeg")
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@api_bp.get("/camera/stream")
def camera_stream():
    try:
        if not get_camera().ensure_camera():
            return jsonify({
                "success": False,
                "message": "Could not open USB camera"
            }), 500

        return Response(
            get_camera().generate_mjpeg_frames(),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )
    except Exception as e:
        log.exception("/camera/stream failed: %s", e)
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@api_bp.post("/camera/capture")
def camera_capture():
    """Take the item photo.

    Returns an unguessable capture_id (the kiosk screen sends it with the
    return) and an inline preview; the file stays on this PC until sent.
    """
    capture_dir = current_app.config["CAPTURE_DIR"]
    try:
        photo = captures.take_photo(get_camera(), capture_dir, store())
        log.info("Image captured: %s", photo["file_name"])
        with open(f"{capture_dir}/{photo['file_name']}", "rb") as fh:
            preview = base64.b64encode(fh.read()).decode("ascii")
        return jsonify({
            "success": True,
            "capture_id": photo["capture_id"],
            "file_name": photo["file_name"],
            "preview_data_url": f"data:image/jpeg;base64,{preview}",
        })
    except Exception as e:
        log.error("/camera/capture failed: %s", e)
        return jsonify({
            "success": False,
            "message": "Camera unavailable. Please try again."
        }), 503


@api_bp.get("/receipt/scan")
def scan_receipt():
    try:
        result = get_camera().scan_barcode()

        if result:
            return jsonify({
                "success": True,
                "found": True,
                "barcode": result["barcode"],
                "barcode_type": result["type"]
            })

        return jsonify({
            "success": True,
            "found": False,
            "message": "No barcode detected"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
