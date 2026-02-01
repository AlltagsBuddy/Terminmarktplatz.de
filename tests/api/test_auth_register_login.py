import os
import tempfile

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("EMAILS_ENABLED", "false")

import app as app_module
from models import Base, Provider


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _create_provider(email: str, password: str, *, verified: bool) -> Provider:
    with Session(app_module.engine) as s:
        provider = Provider(
            email=email,
            pw_hash=app_module.ph.hash(password),
            status="approved",
            email_verified_at=app_module._now() if verified else None,
        )
        s.add(provider)
        s.commit()
        return provider


def test_register_success(test_client):
    r = test_client.post(
        "/auth/register",
        json={"email": "neu@example.com", "password": "testpass123"},
    )
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True
    assert data.get("mail_sent") is True


def test_register_duplicate_email(test_client):
    _create_provider("dup@example.com", "testpass123", verified=False)
    r = test_client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "testpass123"},
    )
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "email_exists"


def test_register_invalid_email(test_client):
    r = test_client.post(
        "/auth/register",
        json={"email": "invalid-email", "password": "testpass123"},
    )
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_email"


def test_register_password_too_short(test_client):
    r = test_client.post(
        "/auth/register",
        json={"email": "short@example.com", "password": "short"},
    )
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "password_too_short"


def test_login_success(test_client):
    _create_provider("login@example.com", "testpass123", verified=True)
    r = test_client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "testpass123"},
    )
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True
    assert data.get("access")


def test_login_requires_verified_email(test_client):
    _create_provider("verify@example.com", "testpass123", verified=False)
    r = test_client.post(
        "/auth/login",
        json={"email": "verify@example.com", "password": "testpass123"},
    )
    assert r.status_code == 403
    data = r.get_json() or {}
    assert data.get("error") == "email_not_verified"


def test_login_invalid_credentials(test_client):
    _create_provider("invalid@example.com", "testpass123", verified=True)
    r = test_client.post(
        "/auth/login",
        json={"email": "invalid@example.com", "password": "wrongpass"},
    )
    assert r.status_code == 401
    data = r.get_json() or {}
    assert data.get("error") == "invalid_credentials"
