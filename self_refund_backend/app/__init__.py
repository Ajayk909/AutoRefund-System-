import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from config import Config

db = SQLAlchemy()


def _setup_logging(app):
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s")

    root = logging.getLogger("autorefund")
    if root.handlers:  # already configured (tests / reloader)
        return
    root.setLevel(logging.DEBUG if app.config["DEBUG"] else logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # Containers have no persistent disk and are read by CloudWatch from
    # stdout/stderr only; the rotating file log is a local-machine concern.
    if app.config.get("ENVIRONMENT", "local") == "local":
        os.makedirs(app.config["LOG_DIR"], exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(app.config["LOG_DIR"], "autorefund.log"),
            maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)


def create_app(config_overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    from config import validate_cloud_config
    validate_cloud_config(app.config)

    from app.tenancy.device_auth import check_startup_safety
    check_startup_safety(app.config)

    _setup_logging(app)

    if app.config.get("TRUST_PROXY"):
        # Behind the ALB in the cloud only: trust exactly one hop for the
        # client's real scheme/address/host. Never applied locally - nothing
        # sits in front of the Flask dev server there.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    origins = app.config.get("CORS_ORIGINS", "*")
    CORS(app, origins="*" if origins == "*" else
         [o.strip() for o in origins.split(",") if o.strip()])
    db.init_app(app)

    from app.evidence.storage import build_storage
    app.evidence_storage = build_storage(app.config)

    with app.app_context():
        from app import models  # noqa: F401
        from app.api import api_bp
        app.register_blueprint(api_bp, url_prefix="/api")

    return app
