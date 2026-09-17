"""Agent unit tests: no database, no Core API. A FakeCore stands in for the
Core API and mock devices stand in for the hardware."""
import os
import sys

import pytest

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AGENT_DIR)

import hardware  # noqa: E402
from hardware.mock import MockCamera, MockScale  # noqa: E402
from agent import create_agent_app  # noqa: E402
from agent.core_client import CoreApiClient  # noqa: E402
from agent.identity import DevelopmentKeyIdentity  # noqa: E402

KIOSK = {"kiosk_code": "KIOSK-001", "store_code": "STORE-001", "retailer_code": "DEMO",
         "kiosk_name": "KIOSK-001", "store_name": "S", "retailer_name": "R", "active": True}


class FakeCore:
    """Canned Core API. ``routes[(method, path)] = (status, body)`` or an exception."""

    def __init__(self):
        self.calls = []
        self.routes = {("GET", "/api/kiosk/me"): (200, {"success": True, "kiosk": dict(KIOSK)})}

    def send(self, method, path, headers=None, json=None, data=None, files=None):
        self.calls.append({"method": method, "path": path, "headers": dict(headers or {}),
                           "data": dict(data or {}), "files": dict(files or {})})
        answer = self.routes.get((method, path), (404, {"success": False, "code": "NOT_FOUND"}))
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture()
def fake_core():
    return FakeCore()


@pytest.fixture()
def devices(tmp_path):
    camera, scale = MockCamera(tmp_path / "captures"), MockScale(250)
    hardware.reset_devices()
    hardware.set_devices(camera=camera, scale=scale)
    yield camera, scale
    hardware.reset_devices()


@pytest.fixture()
def agent(tmp_path, fake_core, devices):
    return create_agent_app(
        {"TESTING": True, "AGENT_DB_PATH": str(tmp_path / "agent.sqlite3"),
         "CAPTURE_DIR": tmp_path / "captures", "LOG_DIR": str(tmp_path / "logs")},
        core_client=CoreApiClient(transport=fake_core),
        identity=DevelopmentKeyIdentity("KIOSK-001", "ardev_unit-test-key"))
