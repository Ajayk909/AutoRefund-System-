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
    CORS_ORIGINS = os.getenv("CORS_ORIGINS",
                             "http://localhost:5173,http://127.0.0.1:5173")

    # --- Return rules (Phase 0: global; Phase 1 moves these to per-retailer
    #     versioned policies) ---------------------------------------------
    RETURN_WINDOW_DAYS = _int("RETURN_WINDOW_DAYS", 30)
    # How many times a customer may try again after a rejected return.
    RETURN_RETRY_LIMIT_AFTER_REJECTION = _int("RETURN_RETRY_LIMIT_AFTER_REJECTION", 1)
    # Without a photo, a weight match goes to employee review instead of
    # being approved automatically.
    REQUIRE_PHOTO_FOR_AUTO_APPROVAL = _bool("REQUIRE_PHOTO_FOR_AUTO_APPROVAL", True)

    # --- Kiosk agent -> Core API ----------------------------------------------
    # How kiosk agents authenticate. Only "development" exists in Phase 2 and
    # it is refused unless FLASK_HOST is a loopback address.
    DEVICE_AUTH_MODE = os.getenv("DEVICE_AUTH_MODE", "development").strip().lower()
    DEV_KEY_MAX_DAYS = _int("DEV_KEY_MAX_DAYS", 30)
    # Largest evidence photo the agent may upload (bytes).
    MAX_EVIDENCE_BYTES = _int("MAX_EVIDENCE_BYTES", 5 * 1024 * 1024)

    # --- Staff authentication ----------------------------------------------
    STAFF_SESSION_HOURS = _int("STAFF_SESSION_HOURS", 8)

    # --- Storage ------------------------------------------------------------
    CAPTURE_DIR = _resolve_dir(os.getenv("CAPTURE_DIR"), BASE_DIR / "captures")
    LOG_DIR = _resolve_dir(os.getenv("LOG_DIR"), BASE_DIR / "logs")
