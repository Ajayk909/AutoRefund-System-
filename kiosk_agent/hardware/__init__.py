"""
Hardware access layer.

    Flask routes  ->  hardware.get_camera() / get_scale() / decode_barcodes()
                  ->  real USB implementation  (camera_service, scale_service)
                      or MOCK implementation   (mock)  -- dev/testing only

The concrete classes are selected from configuration (the kiosk agent's
agent/config.py, or settings passed to ``configure()``), so the
application never imports a device-specific library directly.
"""
import logging
import threading

from .base import CameraDevice, HardwareError, ScaleDevice, ScaleReading  # noqa: F401
from .barcode import decode_barcodes  # noqa: F401

log = logging.getLogger("autorefund.hardware")

_lock = threading.Lock()
_camera = None
_scale = None


_settings = None


def configure(settings):
    """Give the hardware layer its settings (the kiosk agent's config object).
    Devices already created are kept; call reset_devices() to rebuild them."""
    global _settings
    _settings = settings


def _config():
    if _settings is None:
        from agent.config import Config

        return Config
    return _settings


def get_camera() -> CameraDevice:
    global _camera
    with _lock:
        if _camera is None:
            cfg = _config()
            if cfg.CAMERA_MODE == "mock":
                from .mock import MockCamera

                log.warning("*** MOCK CAMERA ACTIVE - not for real refunds ***")
                _camera = MockCamera(cfg.CAPTURE_DIR, cfg.CAMERA_WIDTH,
                                     cfg.CAMERA_HEIGHT)
            else:
                from .camera_service import OpenCVCamera

                _camera = OpenCVCamera(
                    cfg.CAPTURE_DIR,
                    camera_index=cfg.CAMERA_INDEX or None,
                    backend=cfg.CAMERA_BACKEND,
                    width=cfg.CAMERA_WIDTH,
                    height=cfg.CAMERA_HEIGHT,
                )
        return _camera


def get_scale() -> ScaleDevice:
    global _scale
    with _lock:
        if _scale is None:
            cfg = _config()
            if cfg.SCALE_MODE == "mock":
                from .mock import MockScale

                log.warning("*** MOCK SCALE ACTIVE - not for real refunds ***")
                _scale = MockScale(cfg.MOCK_SCALE_GRAMS)
            else:
                from .scale_service import HidPostalScale

                _scale = HidPostalScale(cfg.SCALE_VENDOR_ID,
                                        cfg.SCALE_PRODUCT_ID,
                                        cfg.SCALE_READ_TIMEOUT_MS)
        return _scale


def set_devices(camera=None, scale=None):
    """Inject devices (used by automated tests)."""
    global _camera, _scale
    with _lock:
        if camera is not None:
            _camera = camera
        if scale is not None:
            _scale = scale


def reset_devices():
    global _camera, _scale
    with _lock:
        for dev in (_camera,):
            if dev is not None:
                try:
                    dev.release_camera()
                except Exception:
                    pass
        if _scale is not None:
            try:
                _scale.close()
            except Exception:
                pass
        _camera = None
        _scale = None
