"""
Tests für GET /auth/verify mit gültigem Token (Erfolgsfall).
"""
import os
import tempfile
from datetime import timedelta

import jwt
import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("FRONTEND_URL", "http://testserver")

import app as app_module
from models import Base, Provider


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _create_provider(unverified: bool = True) -> str:
    with Session(app_module.engine) as s:
        p = Provider(
            email="verify-test@example.com",
            pw_hash="test",
            company_name="Verify GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
            email_verified_at=None if unverified else app_module._now(),
        )
        s.add(p)
        s.commit()
        return str(p.id)


def _verify_token(provider_id: str) -> str:
    payload = {
        "sub": provider_id,
        "aud": "verify",
        "iss": app_module.JWT_ISS,
        "exp": int((app_module._now() + timedelta(days=2)).timestamp()),
    }
    return jwt.encode(
        payload,
        app_module.SECRET,
        algorithm="HS256",
    )


def test_auth_verify_valid_token_success(test_client):
    """GET /auth/verify mit gültigem Token verifiziert E-Mail und leitet um."""
    provider_id = _create_provider(unverified=True)
    token = _verify_token(provider_id)
    r = test_client.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert r.status_code == 302
    assert r.location and "verified=1" in r.location

    with Session(app_module.engine) as s:
        p = s.get(Provider, provider_id)
        assert p is not None
        assert p.email_verified_at is not None


def test_auth_verify_valid_token_debug_returns_json(test_client):
    """GET /auth/verify?token=valid&debug=1 liefert JSON."""
    provider_id = _create_provider(unverified=True)
    token = _verify_token(provider_id)
    r = test_client.get(f"/auth/verify?token={token}&debug=1")
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert data.get("ok") is True
    assert "redirect" in data
    assert "verified=1" in data.get("redirect", "")


def test_auth_verify_provider_not_found(test_client):
    """GET /auth/verify mit Token für nicht existierenden Provider."""
    from uuid import uuid4
    fake_id = str(uuid4())
    token = _verify_token(fake_id)
    r = test_client.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert r.status_code == 302
    assert r.location and "verified=0" in r.location


def test_auth_refresh_invalid_token(test_client):
    """POST /auth/refresh mit ungültigem Token liefert 401."""
    r = test_client.post(
        "/auth/refresh",
        headers={"Authorization": "Bearer invalid-token-xyz"},
    )
    assert r.status_code == 401
    data = r.get_json() or {}
    assert data.get("error") == "unauthorized"
