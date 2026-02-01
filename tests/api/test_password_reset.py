import os
import tempfile
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("EMAILS_ENABLED", "false")

import app as app_module
from models import Base, Provider, PasswordReset


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _create_provider(email: str, password: str) -> str:
    with Session(app_module.engine) as s:
        provider = Provider(
            email=email,
            pw_hash=app_module.ph.hash(password),
            status="approved",
            email_verified_at=app_module._now(),
        )
        s.add(provider)
        s.commit()
        return str(provider.id)


def test_forgot_password_invalid_email(test_client):
    r = test_client.post("/auth/forgot-password", json={"email": "invalid"})
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_email"


def test_forgot_password_unknown_email_returns_ok(test_client):
    r = test_client.post("/auth/forgot-password", json={"email": "unknown@example.com"})
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True


def test_forgot_password_creates_token(test_client):
    provider_id = _create_provider("reset@example.com", "testpass123")
    r = test_client.post("/auth/forgot-password", json={"email": "reset@example.com"})
    assert r.status_code == 200

    with Session(app_module.engine) as s:
        token_row = s.query(PasswordReset).filter_by(provider_id=provider_id).first()
        assert token_row is not None
        assert token_row.used_at is None


def test_reset_password_missing_token(test_client):
    r = test_client.post("/auth/reset-password", json={"password": "newpass123"})
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "missing_token"


def test_reset_password_too_short(test_client):
    r = test_client.post("/auth/reset-password", json={"token": "t", "password": "short"})
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "password_too_short"


def test_reset_password_invalid_token(test_client):
    r = test_client.post("/auth/reset-password", json={"token": "invalid", "password": "newpass123"})
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_token"


def test_reset_password_expired_token(test_client):
    provider_id = _create_provider("expired@example.com", "testpass123")
    with Session(app_module.engine) as s:
        reset = PasswordReset(
            provider_id=provider_id,
            token="expired-token",
            expires_at=app_module._to_db_utc_naive(app_module._now() - timedelta(minutes=1)),
        )
        s.add(reset)
        s.commit()

    r = test_client.post("/auth/reset-password", json={"token": "expired-token", "password": "newpass123"})
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "token_expired"


def test_reset_password_success(test_client):
    provider_id = _create_provider("ok@example.com", "oldpass123")
    with Session(app_module.engine) as s:
        reset = PasswordReset(
            provider_id=provider_id,
            token="valid-token",
            expires_at=app_module._to_db_utc_naive(app_module._now() + timedelta(minutes=30)),
        )
        s.add(reset)
        s.commit()

    r = test_client.post("/auth/reset-password", json={"token": "valid-token", "password": "newpass123"})
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True

    with Session(app_module.engine) as s:
        updated = s.get(Provider, provider_id)
        assert updated is not None
        assert app_module.ph.verify(updated.pw_hash, "newpass123")
        reset_row = s.query(PasswordReset).filter_by(token="valid-token").first()
        assert reset_row.used_at is not None


def test_reset_password_provider_not_found(test_client):
    from uuid import uuid4
    with Session(app_module.engine) as s:
        reset = PasswordReset(
            provider_id=str(uuid4()),
            token="missing-provider-token",
            expires_at=app_module._to_db_utc_naive(app_module._now() + timedelta(minutes=30)),
        )
        s.add(reset)
        s.commit()

    r = test_client.post("/auth/reset-password", json={"token": "missing-provider-token", "password": "newpass123"})
    assert r.status_code == 404
    data = r.get_json() or {}
    assert data.get("error") == "provider_not_found"
