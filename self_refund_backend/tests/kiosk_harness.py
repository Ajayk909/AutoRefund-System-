"""
Test harness: the real kiosk agent in front of the real Core API.

In production the browser talks to two servers:

    kiosk screens  -> kiosk agent (127.0.0.1:5100) -> Core API /api/kiosk/*
    staff screens  -> Core API (127.0.0.1:5000)

``app.test_client()`` returns a client that does the same: staff paths go to
the Core API, everything else to an in-process kiosk agent with mock hardware.
The agent reaches the Core API through ``FlaskTestTransport`` (no network),
which can also simulate an outage.

The agent's kiosk identity follows ``core_app.config["KIOSK_ID"]`` so tests can
"reconfigure the kiosk" by changing that value; a development key is issued
for that kiosk on first use, exactly as manage_tenancy.py would.
"""
import io
import os
import re
import sys
import threading

import requests
from flask.testing import FlaskClient

AGENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "kiosk_agent"))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from agent import create_agent_app  # noqa: E402
from agent.core_client import CoreApiClient  # noqa: E402
from agent.identity import KioskIdentity  # noqa: E402

CORE_PATHS = re.compile(
    r"^/api/(staff/|kiosk/(me|receipts|products|returns)|captures/|refunds/(pending|logs)$"
    r"|refunds/[^/]+/(approve|reject|mark-refunded|image)$)")


class FlaskTestTransport:
    """Agent -> Core API over a Flask test client. ``down`` simulates an outage,
    ``fail_status`` a broken server."""

    def __init__(self, core_app):
        self.core = FlaskClient(core_app)
        self.down = False
        self.fail_status = None
        self.lose_response_once = False
        self.calls = []

    def send(self, method, path, headers=None, json=None, data=None, files=None):
        self.calls.append({"method": method, "path": path, "headers": dict(headers or {}),
                           "data": dict(data or {}), "files": sorted(files or {})})
        if self.down:
            raise requests.ConnectionError("simulated Core API outage")
        if self.fail_status:
            return self.fail_status, None
        kwargs = {"headers": headers}
        if files or data:
            form = dict(data or {})
            for name, (filename, content, mime) in (files or {}).items():
                form[name] = (io.BytesIO(content), filename, mime)
            kwargs.update(data=form, content_type="multipart/form-data")
        elif json is not None:
            kwargs["json"] = json
        response = self.core.open(path, method=method, **kwargs)
        if self.lose_response_once:  # the Core API did the work, the answer never arrived
            self.lose_response_once = False
            raise requests.ReadTimeout("simulated lost response")
        return response.status_code, response.get_json(silent=True)


class HarnessIdentity(KioskIdentity):
    """Development-key identity for whatever kiosk core_app.config["KIOSK_ID"] names."""

    def __init__(self, core_app):
        self.core_app = core_app
        self._keys = {}
        self._lock = threading.Lock()

    @property
    def expected_kiosk_code(self):
        return self.core_app.config["KIOSK_ID"]

    def auth_headers(self):
        code = self.expected_kiosk_code
        with self._lock:
            if code not in self._keys:
                self._keys[code] = self._issue(code)
        return {"Authorization": f"AutoRefund-Dev-Key {self._keys[code]}"}

    def _issue(self, code):
        from app import db
        from app.tenancy import device_auth, repository

        with self.core_app.app_context():
            kiosk = repository.get_kiosk_by_code(code)
            if not kiosk:
                return "ardev_not-registered"
            key = device_auth.issue_development_key(kiosk)
            db.session.commit()
            return key


class KioskSystemClient(FlaskClient):
    """Routes staff/Core paths to the Core API and kiosk paths to the agent."""

    def open(self, *args, **kwargs):
        path = args[0] if args and isinstance(args[0], str) else kwargs.get("path")
        if isinstance(path, str) and not CORE_PATHS.match(path.split("?", 1)[0]):
            agent = self.application.kiosk_agent
            return agent.test_client().open(*args, **kwargs)
        return super().open(*args, **kwargs)


def attach_kiosk_system(core_app, tmp_path, camera, scale):
    """Create the agent for ``core_app`` and make app.test_client() route like a kiosk."""
    import hardware

    transport = FlaskTestTransport(core_app)
    agent = create_agent_app(
        {
            "TESTING": True,
            "AGENT_DB_PATH": str(tmp_path / "agent.sqlite3"),
            # Shared with the Core API's folder so tests can inspect files.
            "CAPTURE_DIR": core_app.config["CAPTURE_DIR"],
            "LOG_DIR": str(tmp_path / "agent_logs"),
            "HARDWARE_MODE": "mock", "CAMERA_MODE": "mock", "SCALE_MODE": "mock",
        },
        core_client=CoreApiClient(transport=transport),
        identity=HarnessIdentity(core_app),
    )
    hardware.reset_devices()
    hardware.set_devices(camera=camera, scale=scale)
    core_app.kiosk_agent = agent
    core_app.core_transport = transport
    core_app.test_client_class = KioskSystemClient
    return agent
