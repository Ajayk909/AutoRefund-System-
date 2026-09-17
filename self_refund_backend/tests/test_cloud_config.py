"""Phase 3: ENVIRONMENT, database URL assembly, proxy trust and fail-fast
cloud configuration checks. Pure config tests: no database needed."""
import pytest

from config import _database_url, validate_cloud_config


# --- database URL assembly --------------------------------------------------------------
def test_database_url_prefers_explicit_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://explicit/db")
    monkeypatch.setenv("DB_HOST", "ignored-host")
    assert _database_url() == "postgresql://explicit/db"


def test_database_url_built_from_parts_when_no_explicit_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_HOST", "db.internal")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "refund_kiosk")
    monkeypatch.setenv("DB_USER", "refund_user")
    monkeypatch.setenv("DB_PASSWORD", "p@ss/w:ord")
    url = _database_url()
    assert url == "postgresql://refund_user:p%40ss%2Fw%3Aord@db.internal:5432/refund_kiosk"


def test_database_url_is_none_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_HOST", raising=False)
    assert _database_url() is None


# --- validate_cloud_config ---------------------------------------------------------------
def test_local_without_database_url_fails_with_local_hint():
    with pytest.raises(RuntimeError, match="Copy self_refund_backend/.env.example"):
        validate_cloud_config({"ENVIRONMENT": "local"})


def test_dev_without_database_config_fails_with_cloud_hint():
    with pytest.raises(RuntimeError, match="DB_HOST/DB_NAME/DB_USER/DB_PASSWORD"):
        validate_cloud_config({"ENVIRONMENT": "dev"})


def test_dev_with_s3_backend_requires_bucket():
    with pytest.raises(RuntimeError, match="EVIDENCE_S3_BUCKET"):
        validate_cloud_config({"ENVIRONMENT": "dev",
                              "SQLALCHEMY_DATABASE_URI": "postgresql://x/y",
                              "EVIDENCE_BACKEND": "s3"})


def test_unknown_environment_is_refused():
    with pytest.raises(RuntimeError, match="Unknown ENVIRONMENT"):
        validate_cloud_config({"ENVIRONMENT": "production-ish"})


def test_valid_cloud_config_passes():
    validate_cloud_config({"ENVIRONMENT": "dev",
                          "SQLALCHEMY_DATABASE_URI": "postgresql://x/y",
                          "EVIDENCE_BACKEND": "s3", "EVIDENCE_S3_BUCKET": "bucket"})


def test_local_evidence_backend_needs_no_bucket_in_cloud():
    validate_cloud_config({"ENVIRONMENT": "staging",
                          "SQLALCHEMY_DATABASE_URI": "postgresql://x/y",
                          "EVIDENCE_BACKEND": "local"})


# --- proxy trust -------------------------------------------------------------------------
def test_local_app_does_not_trust_proxy_headers(app):
    from werkzeug.middleware.proxy_fix import ProxyFix
    assert not isinstance(app.wsgi_app, ProxyFix)


def test_cloud_app_wraps_wsgi_app_with_proxyfix(app):
    from werkzeug.middleware.proxy_fix import ProxyFix

    from app import create_app
    cloud_app = create_app({
        "SQLALCHEMY_DATABASE_URI": app.config["SQLALCHEMY_DATABASE_URI"],
        "CAPTURE_DIR": app.config["CAPTURE_DIR"],
        "ENVIRONMENT": "dev",
        "TRUST_PROXY": True,
    })
    assert isinstance(cloud_app.wsgi_app, ProxyFix)
