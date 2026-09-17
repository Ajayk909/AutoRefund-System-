"""
AutoRefund Windows kiosk agent.

Runs on the kiosk PC next to the browser. It owns the physical hardware
(scale, camera, barcode decoding), the kiosk's identity and credential, a
small local SQLite store, and all communication with the Core API.

    React kiosk UI --HTTP 127.0.0.1:5100--> kiosk agent --HTTP(S)--> Core API
                                              └─ camera / DYMO scale / barcode

See docs/architecture.md.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask
from flask_cors import CORS

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _setup_logging(config):
    log = logging.getLogger("autorefund")
    if log.handlers:
        return
    os.makedirs(config["LOG_DIR"], exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handler = RotatingFileHandler(os.path.join(config["LOG_DIR"], "kiosk-agent.log"),
                                  maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    log.addHandler(handler)
    log.addHandler(console)
    log.setLevel(logging.INFO)


def create_agent_app(overrides=None, core_client=None, identity=None):
    from agent.config import Config

    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)

    host = str(app.config["AGENT_HOST"]).strip().lower()
    if host not in LOOPBACK_HOSTS:
        raise RuntimeError("The kiosk agent holds the kiosk credential and must only listen on "
                           "127.0.0.1, localhost or ::1.")

    _setup_logging(app.config)
    os.makedirs(app.config["CAPTURE_DIR"], exist_ok=True)

    import hardware
    hardware.configure(_HardwareSettings(app.config))

    from agent.core_client import CoreApiClient
    from agent.identity import identity_from_config
    from agent.store import AgentStore

    app.extensions["agent_store"] = AgentStore(app.config["AGENT_DB_PATH"])
    app.extensions["agent_identity"] = identity or identity_from_config(app.config)
    app.extensions["core_client"] = core_client or CoreApiClient(
        app.config["CORE_API_URL"], timeout=app.config["CORE_API_TIMEOUT_SECONDS"])

    origins = [o.strip() for o in app.config["CORS_ORIGINS"].split(",") if o.strip()]
    app.config["ALLOWED_ORIGINS"] = origins
    CORS(app, origins=origins)

    from agent.routes import agent_bp
    app.register_blueprint(agent_bp, url_prefix="/api")
    return app


class _HardwareSettings:
    """Adapter so the hardware layer can read the agent's settings."""

    def __init__(self, config):
        self._config = config

    def __getattr__(self, name):
        try:
            return self._config[name]
        except KeyError as exc:
            raise AttributeError(name) from exc
