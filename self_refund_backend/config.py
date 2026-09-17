"""
Central configuration for the AutoRefund backend.

All machine-specific values (database, hardware, paths, network) come from
environment variables, normally loaded from ``self_refund_backend/.env``.
See ``.env.example`` for every supported setting.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Always load the .env that sits next to this file, regardless of the
# working directory the backend was started from.
load_dotenv(BASE_DIR / ".env")


def _bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _int(name, default):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value, 0)  # accepts "0x0922" as well as "2338"


def _resolve_dir(value, default):
    path = Path(value) if value else default
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


class Config:
    # --- Database -----------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Web server ---------------------------------------------------------
    HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    PORT = _int("FLASK_PORT", 5000)
    DEBUG = _bool("FLASK_DEBUG", False)
    # Comma separated list of allowed frontend origins, "*" allows all.
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

    # --- Kiosk --------------------------------------------------------------
    KIOSK_ID = os.getenv("KIOSK_ID", "KIOSK-001")

    # --- Storage ------------------------------------------------------------
    CAPTURE_DIR = _resolve_dir(os.getenv("CAPTURE_DIR"), BASE_DIR / "captures")
    LOG_DIR = _resolve_dir(os.getenv("LOG_DIR"), BASE_DIR / "logs")

    # --- Hardware -----------------------------------------------------------
    # "real" -> talk to physical devices, "mock" -> clearly labelled simulated
    # devices for development without hardware. Can be set per device.
    HARDWARE_MODE = os.getenv("HARDWARE_MODE", "real").strip().lower()
    CAMERA_MODE = os.getenv("CAMERA_MODE", HARDWARE_MODE).strip().lower()
    SCALE_MODE = os.getenv("SCALE_MODE", HARDWARE_MODE).strip().lower()

    # Camera: index as shown by Windows (0 = first webcam). Leave empty to
    # auto-detect indexes 0-3.
    CAMERA_INDEX = os.getenv("CAMERA_INDEX", "").strip()
    # auto | dshow | msmf | v4l2 | any
    CAMERA_BACKEND = os.getenv("CAMERA_BACKEND", "auto").strip().lower()
    CAMERA_WIDTH = _int("CAMERA_WIDTH", 640)
    CAMERA_HEIGHT = _int("CAMERA_HEIGHT", 480)

    # Scale: USB HID vendor / product id (defaults = DYMO M-series scale
    # used by the original prototype).
    SCALE_VENDOR_ID = _int("SCALE_VENDOR_ID", 0x0922)
    SCALE_PRODUCT_ID = _int("SCALE_PRODUCT_ID", 0x8003)
    SCALE_READ_TIMEOUT_MS = _int("SCALE_READ_TIMEOUT_MS", 2000)
    # Mock scale only: the weight (grams) the simulated scale reports.
    MOCK_SCALE_GRAMS = float(os.getenv("MOCK_SCALE_GRAMS", "250"))
