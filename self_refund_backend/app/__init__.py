import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from config import Config

db = SQLAlchemy()


def _setup_logging(app):
    os.makedirs(app.config["LOG_DIR"], exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s")

    root = logging.getLogger("autorefund")
    if root.handlers:  # already configured (tests / reloader)
        return
    root.setLevel(logging.DEBUG if app.config["DEBUG"] else logging.INFO)

    file_handler = RotatingFileHandler(
        os.path.join(app.config["LOG_DIR"], "autorefund.log"),
        maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)


def create_app(config_overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError(
            "DATABASE_URL is not set. Copy self_refund_backend/.env.example "
            "to .env and fill in your PostgreSQL connection string.")

    _setup_logging(app)

    origins = app.config.get("CORS_ORIGINS", "*")
    CORS(app, origins="*" if origins == "*" else
         [o.strip() for o in origins.split(",") if o.strip()])
    db.init_app(app)

    with app.app_context():
        from app import models  # noqa: F401
        from app.routes import api_bp
        app.register_blueprint(api_bp, url_prefix="/api")

    return app
