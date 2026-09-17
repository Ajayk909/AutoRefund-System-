"""scripts/import_backend_settings.py: carrying a Phase 0/1 kiosk's hardware
settings over to the agent without copying secrets or overwriting choices."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))
import import_backend_settings as helper  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.example")


def test_copies_hardware_settings_only(tmp_path):
    backend = tmp_path / "backend.env"
    backend.write_text("DATABASE_URL=postgresql://refund_user:SECRET@localhost/db\n"
                       "HARDWARE_MODE=real\nCAMERA_INDEX=0\nCAMERA_BACKEND=dshow\n")
    agent = tmp_path / "agent.env"
    agent.write_text(open(TEMPLATE).read())
    helper.main(str(backend), str(agent))
    text = agent.read_text()
    assert "SECRET" not in text and "DATABASE_URL" not in text
    assert "CAMERA_INDEX=0" in text and "CAMERA_BACKEND=dshow" in text
    assert "KIOSK_DEV_KEY=" in text and "AGENT_HOST=127.0.0.1" in text


def test_never_overwrites_a_value_chosen_for_the_agent(tmp_path):
    backend = tmp_path / "backend.env"
    backend.write_text("CAMERA_BACKEND=dshow\nCAMERA_INDEX=0\n")
    agent = tmp_path / "agent.env"
    agent.write_text("CAMERA_BACKEND=msmf\nCAMERA_INDEX=2\n")
    helper.main(str(backend), str(agent))
    assert agent.read_text() == "CAMERA_BACKEND=msmf\nCAMERA_INDEX=2\n"
