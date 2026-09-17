"""
Kiosk agent configuration, from kiosk_agent/.env (see .env.example).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name, default=False):
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


def _int(name, default):
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else int(value, 0)


def _dir(value, default):
    path = Path(value) if value else default
    return path if path.is_absolute() else BASE_DIR / path


class Config:
    # --- Local HTTP for the kiosk UI (loopback only) ---------------------------
    AGENT_HOST = os.getenv("AGENT_HOST", "127.0.0.1")
    AGENT_PORT = _int("AGENT_PORT", 5100)
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")

    # --- Core API ---------------------------------------------------------------
    CORE_API_URL = os.getenv("CORE_API_URL", "http://127.0.0.1:5000").rstrip("/")
    CORE_API_TIMEOUT_SECONDS = float(os.getenv("CORE_API_TIMEOUT_SECONDS", "10"))

    # --- Kiosk identity (development) -----------------------------------------
    # KIOSK_ID must match the kiosk registered in the Core API and the key
    # issued with:  python manage_tenancy.py issue-dev-key <KIOSK_ID> --write-env ...
    KIOSK_ID = os.getenv("KIOSK_ID", "KIOSK-001")
    KIOSK_DEV_KEY = os.getenv("KIOSK_DEV_KEY", "")

    # --- Local storage -------------------------------------------------------------
    AGENT_DB_PATH = str(_dir(os.getenv("AGENT_DB_PATH"), BASE_DIR / "data" / "kiosk_agent.sqlite3"))
    CAPTURE_DIR = _dir(os.getenv("CAPTURE_DIR"), BASE_DIR / "captures")
    LOG_DIR = _dir(os.getenv("LOG_DIR"), BASE_DIR / "logs")
    # A photo must be used within this many seconds of being taken.
    CAPTURE_MAX_AGE_SECONDS = _int("CAPTURE_MAX_AGE_SECONDS", 900)
    # Kiosk session expires after this many seconds without activity.
    SESSION_TIMEOUT_SECONDS = _int("SESSION_TIMEOUT_SECONDS", 900)

    # --- Hardware (same settings as before Phase 2) ------------------------------
    HARDWARE_MODE = os.getenv("HARDWARE_MODE", "real").strip().lower()
    CAMERA_MODE = os.getenv("CAMERA_MODE", HARDWARE_MODE).strip().lower()
    SCALE_MODE = os.getenv("SCALE_MODE", HARDWARE_MODE).strip().lower()
    CAMERA_INDEX = os.getenv("CAMERA_INDEX", "").strip()
    CAMERA_BACKEND = os.getenv("CAMERA_BACKEND", "auto").strip().lower()
    CAMERA_WIDTH = _int("CAMERA_WIDTH", 640)
    CAMERA_HEIGHT = _int("CAMERA_HEIGHT", 480)
    SCALE_VENDOR_ID = _int("SCALE_VENDOR_ID", 0x0922)
    SCALE_PRODUCT_ID = _int("SCALE_PRODUCT_ID", 0x8003)
    SCALE_READ_TIMEOUT_MS = _int("SCALE_READ_TIMEOUT_MS", 2000)
    MOCK_SCALE_GRAMS = float(os.getenv("MOCK_SCALE_GRAMS", "250"))
