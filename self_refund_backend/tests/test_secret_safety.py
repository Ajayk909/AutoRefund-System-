"""Phase 3: secrets issued for the cloud kiosk must never be logged or
printed - only written into a Secrets Manager secret. Exercised against a
fake Secrets Manager client; no real AWS is contacted."""
from cloud_secrets import store_secret


class ResourceNotFoundException(Exception):
    pass


class FakeSecretsClient:
    def __init__(self, existing=None):
        self.secrets = dict(existing or {})
        self.exceptions = type("Exceptions", (),
                               {"ResourceNotFoundException": ResourceNotFoundException})()

    def put_secret_value(self, SecretId, SecretString):
        if SecretId not in self.secrets:
            raise self.exceptions.ResourceNotFoundException()
        self.secrets[SecretId] = SecretString

    def create_secret(self, Name, SecretString):
        self.secrets[Name] = SecretString


def test_store_secret_creates_when_missing():
    client = FakeSecretsClient()
    store_secret("autorefund/dev/admin-password", "s3cr3t", client=client)
    assert client.secrets["autorefund/dev/admin-password"] == "s3cr3t"


def test_store_secret_updates_when_present():
    client = FakeSecretsClient(existing={"name": "old-value"})
    store_secret("name", "new-value", client=client)
    assert client.secrets["name"] == "new-value"


def test_issue_staging_key_command_never_prints_the_secret(app, capsys, monkeypatch):
    import manage_tenancy
    from flask.testing import FlaskClient

    monkeypatch.setattr(manage_tenancy, "create_app", lambda: app)
    captured = {}

    def fake_store_secret(name, value, client=None):
        captured["name"] = name
        captured["value"] = value

    monkeypatch.setattr(manage_tenancy, "store_secret", fake_store_secret)

    secret_name = "autorefund/dev/kiosk/KIOSK-001"
    assert manage_tenancy.main(["issue-staging-key", "KIOSK-001",
                               "--secret-name", secret_name]) == 0
    out = capsys.readouterr().out

    assert captured["name"] == secret_name
    assert captured["value"].startswith("arstg_")
    assert captured["value"] not in out
    assert secret_name in out and "not printed" in out

    app.config["DEVICE_AUTH_MODE"] = "staging-key"
    core = FlaskClient(app)
    r = core.get("/api/kiosk/me", headers={
        "Authorization": f"AutoRefund-Staging-Key {captured['value']}",
        "X-Forwarded-Proto": "https"})
    assert r.status_code == 200


def test_issue_staging_key_defaults_to_the_predictable_terraform_name(app, monkeypatch):
    """Matches ecs_service module's dev_kiosk_key secret:
    autorefund/<environment>/kiosk/<code> - so no --secret-name is needed for
    the single dev kiosk Terraform already pre-created a placeholder for."""
    import manage_tenancy

    app.config["ENVIRONMENT"] = "dev"
    monkeypatch.setattr(manage_tenancy, "create_app", lambda: app)
    captured = {}
    monkeypatch.setattr(manage_tenancy, "store_secret",
                        lambda name, value, client=None: captured.update(name=name, value=value))

    assert manage_tenancy.main(["issue-staging-key", "KIOSK-001"]) == 0
    assert captured["name"] == "autorefund/dev/kiosk/KIOSK-001"


def test_issue_staging_key_unknown_kiosk(app, monkeypatch):
    import manage_tenancy
    monkeypatch.setattr(manage_tenancy, "create_app", lambda: app)
    assert manage_tenancy.main(["issue-staging-key", "NOPE",
                               "--secret-name", "whatever"]) == 1
