"""
Central configuration for the AutoRefund backend.

All machine-specific values (database, hardware, paths, network) come from
environment variables, normally loaded from ``self_refund_backend/.env``.
See ``.env.example`` for every supported setting.
"""
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Always load the .env that sits next to this file, regardless of the
# working directory the backend was started from.
load_dotenv(BASE_DIR / ".env")

LOCAL = "local"
DEV = "dev"
STAGING = "staging"
PRODUCTION = "production"
ENVIRONMENTS = (LOCAL, DEV, STAGING, PRODUCTION)


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


def _database_url():
    """DATABASE_URL wins when set (local dev, tests). Otherwise build it from
    separate DB_* variables, which is how ECS injects the RDS connection: the
    password comes from a Secrets Manager secret, never from Terraform code,
    state or committed configuration."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host = os.getenv("DB_HOST")
    if not host:
        return None
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "refund_kiosk")
    user = os.getenv("DB_USER", "refund_user")
    password = os.getenv("DB_PASSWORD", "")
    return (f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
            f"@{host}:{port}/{name}")


class Config:
    # --- Deployment environment ---------------------------------------------
    # local = Windows kiosk PC. dev/staging/production = AWS. Cloud-only
    # behaviour (trusting the ALB's proxy headers, S3 evidence, staging-key
    # device auth, stdout-only logging) is gated on this, never guessed from
    # other settings.
    ENVIRONMENT = os.getenv("ENVIRONMENT", LOCAL).strip().lower()

    # --- Database -----------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Web server ---------------------------------------------------------
    HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    PORT = _int("FLASK_PORT", 5000)
    DEBUG = _bool("FLASK_DEBUG", False)
    # Comma separated list of allowed frontend origins, "*" allows all.
    CORS_ORIGINS = os.getenv("CORS_ORIGINS",
                             "http://localhost:5173,http://127.0.0.1:5173")
    # Trust X-Forwarded-Proto/-For/-Host from exactly one hop (the ALB).
    # Never trusted locally: nothing sits in front of the Flask dev server.
    TRUST_PROXY = ENVIRONMENT != LOCAL

    # --- Return rules (Phase 0: global; Phase 1 moves these to per-retailer
    #     versioned policies) ---------------------------------------------
    RETURN_WINDOW_DAYS = _int("RETURN_WINDOW_DAYS", 30)
    # How many times a customer may try again after a rejected return.
    RETURN_RETRY_LIMIT_AFTER_REJECTION = _int("RETURN_RETRY_LIMIT_AFTER_REJECTION", 1)
    # Without a photo, a weight match goes to employee review instead of
    # being approved automatically.
    REQUIRE_PHOTO_FOR_AUTO_APPROVAL = _bool("REQUIRE_PHOTO_FOR_AUTO_APPROVAL", True)

    # --- Kiosk agent -> Core API ----------------------------------------------
    # How kiosk agents authenticate: "development" (Phase 2, loopback only) or
    # "staging-key" (cloud dev/staging only, HTTPS required, refused when
    # ENVIRONMENT=production). See app/tenancy/device_auth.py.
    DEVICE_AUTH_MODE = os.getenv("DEVICE_AUTH_MODE", "development").strip().lower()
    DEV_KEY_MAX_DAYS = _int("DEV_KEY_MAX_DAYS", 30)
    STAGING_KEY_MAX_DAYS = _int("STAGING_KEY_MAX_DAYS", 14)
    # Largest evidence photo the agent may upload (bytes).
    MAX_EVIDENCE_BYTES = _int("MAX_EVIDENCE_BYTES", 5 * 1024 * 1024)

    # --- Staff authentication ----------------------------------------------
    STAFF_SESSION_HOURS = _int("STAFF_SESSION_HOURS", 8)

    # --- Storage ------------------------------------------------------------
    CAPTURE_DIR = _resolve_dir(os.getenv("CAPTURE_DIR"), BASE_DIR / "captures")
    LOG_DIR = _resolve_dir(os.getenv("LOG_DIR"), BASE_DIR / "logs")

    # --- Evidence storage backend --------------------------------------------
    # "local" (default): files under CAPTURE_DIR. "s3": a private bucket;
    # ECS containers have no persistent disk, so dev/staging/production use s3.
    EVIDENCE_BACKEND = os.getenv("EVIDENCE_BACKEND", "local").strip().lower()
    EVIDENCE_S3_BUCKET = os.getenv("EVIDENCE_S3_BUCKET")
    AWS_REGION = os.getenv("AWS_REGION")


def validate_cloud_config(config):
    """Fail fast with a clear error instead of starting half-configured."""
    environment = str(config.get("ENVIRONMENT", LOCAL)).strip().lower()
    if environment not in ENVIRONMENTS:
        raise RuntimeError(f"Unknown ENVIRONMENT={environment!r}. Must be one of {ENVIRONMENTS}.")

    if not config.get("SQLALCHEMY_DATABASE_URI"):
        if environment == LOCAL:
            raise RuntimeError(
                "DATABASE_URL is not set. Copy self_refund_backend/.env.example "
                "to .env and fill in your PostgreSQL connection string.")
        raise RuntimeError(
            "No database configuration found. Set DATABASE_URL, or all of "
            "DB_HOST/DB_NAME/DB_USER/DB_PASSWORD (the password normally comes "
            "from an RDS-managed Secrets Manager secret).")

    if environment != LOCAL and config.get("EVIDENCE_BACKEND") == "s3" \
            and not config.get("EVIDENCE_S3_BUCKET"):
        raise RuntimeError("EVIDENCE_BACKEND=s3 requires EVIDENCE_S3_BUCKET.")
