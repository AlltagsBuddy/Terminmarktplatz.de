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


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def test_refresh_requires_token(test_client):
    r = test_client.post("/auth/refresh")
    assert r.status_code == 401
    data = r.get_json() or {}
    assert data.get("error") == "unauthorized"


def test_refresh_accepts_bearer_refresh_token(test_client):
    provider_id = _create_provider("refresh@example.com", "testpass123")
    _, refresh = app_module.issue_tokens(provider_id, False)
    r = test_client.post("/auth/refresh", headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True
    assert data.get("access")


def test_refresh_rejects_access_token(test_client):
    provider_id = _create_provider("refresh2@example.com", "testpass123")
    access, _ = app_module.issue_tokens(provider_id, False)
    r = test_client.post("/auth/refresh", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 401
    data = r.get_json() or {}
    assert data.get("error") == "unauthorized"


def test_change_password_requires_fields(test_client):
    provider_id = _create_provider("cp1@example.com", "oldpass123")
    r = test_client.post("/auth/change-password", json={}, headers=_auth_headers(provider_id))
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "missing_fields"


def test_change_password_invalid_old_password(test_client):
    provider_id = _create_provider("cp2@example.com", "oldpass123")
    r = test_client.post(
        "/auth/change-password",
        json={"old_password": "wrong", "password": "newpass123"},
        headers=_auth_headers(provider_id),
    )
    assert r.status_code == 401
    data = r.get_json() or {}
    assert data.get("error") == "invalid_old_password"


def test_change_password_too_short(test_client):
    provider_id = _create_provider("cp2b@example.com", "oldpass123")
    r = test_client.post(
        "/auth/change-password",
        json={"old_password": "oldpass123", "password": "short"},
        headers=_auth_headers(provider_id),
    )
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "password_too_short"


def test_change_password_success(test_client):
    provider_id = _create_provider("cp3@example.com", "oldpass123")
    r = test_client.post(
        "/auth/change-password",
        json={"old_password": "oldpass123", "password": "newpass123"},
        headers=_auth_headers(provider_id),
    )
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True

    with Session(app_module.engine) as s:
        provider = s.get(Provider, provider_id)
        assert provider is not None
        assert app_module.ph.verify(provider.pw_hash, "newpass123")


def test_logout_ok(test_client):
    provider_id = _create_provider("logout@example.com", "oldpass123")
    r = test_client.post("/auth/logout", headers=_auth_headers(provider_id))
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True


def test_delete_me_removes_provider(test_client):
    provider_id = _create_provider("deleteme@example.com", "oldpass123")
    headers = _auth_headers(provider_id)
    r = test_client.delete("/me", headers=headers)
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True

    r_me = test_client.get("/me", headers=headers)
    assert r_me.status_code == 404
    data_me = r_me.get_json() or {}
    assert data_me.get("error") == "not_found"
