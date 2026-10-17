from fastapi.testclient import TestClient

from app.api import health
from app.main import app
from app import main
from app.core.config import settings


client = TestClient(app)


def test_liveness_is_available_without_database(monkeypatch) -> None:
    monkeypatch.setattr(health, "is_database_ready", lambda: False)

    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_reports_database_connection(monkeypatch) -> None:
    monkeypatch.setattr(health, "is_database_ready", lambda: True)

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}


def test_readiness_fails_when_database_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(health, "is_database_ready", lambda: False)

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "status": "not_ready",
        "database": "unavailable",
    }


def test_production_security_requires_clamav(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "app_encryption_key", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    monkeypatch.setattr(settings, "app_encryption_key_backup_confirmed", True)
    monkeypatch.setattr(settings, "advocate_email", "advocate@example.test")
    monkeypatch.setattr(settings, "advocate_password_hash", "scrypt$placeholder")
    monkeypatch.setattr(settings, "session_secret", "test-session-secret")
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:password@example.test/db?sslmode=verify-full")
    monkeypatch.setattr(settings, "clamav_command", None)

    import pytest

    with pytest.raises(RuntimeError, match="ClamAV clamscan"):
        main._validate_production_security()
