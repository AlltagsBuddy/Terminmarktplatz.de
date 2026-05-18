"""Login-Session: „Angemeldet bleiben“, 8h ohne Remember, abgelaufenes JWT."""

from __future__ import annotations

import os
import tempfile

import jwt
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


def _seed_verified_provider(email: str, password: str) -> str:
    with Session(app_module.engine) as s:
        p = Provider(
            email=email,
            pw_hash=app_module.ph.hash(password),
            status="approved",
            email_verified_at=app_module._now(),
            company_name="Session GmbH",
            branch="Friseur",
            street="Weg 1",
            zip="12345",
            city="Ort",
            phone="0123",
        )
        s.add(p)
        s.commit()
        return str(p.id)


def test_login_remember_me_sets_long_expiry(test_client):
    email = "rmb-session@example.com"
    _seed_verified_provider(email, "secretpass99")
    r = test_client.post(
        "/auth/login",
        json={"email": email, "password": "secretpass99", "remember_me": True},
    )
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("remember_me") is True
    exp = int(data["session_expires_at"])
    now_ts = int(app_module._now().timestamp())
    low = app_module.SESSION_REMEMBER_DAYS * 86400 - 600
    high = app_module.SESSION_REMEMBER_DAYS * 86400 + 600
    assert low <= exp - now_ts <= high


def test_login_without_remember_me_8h_session(test_client):
    email = "short-session@example.com"
    _seed_verified_provider(email, "secretpass99")
    r = test_client.post(
        "/auth/login",
        json={"email": email, "password": "secretpass99", "remember_me": False},
    )
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("remember_me") is False
    exp = int(data["session_expires_at"])
    now_ts = int(app_module._now().timestamp())
    low = app_module.SESSION_HOURS * 3600 - 120
    high = app_module.SESSION_HOURS * 3600 + 120
    assert low <= exp - now_ts <= high


def test_expired_access_token_rejected_without_refresh(test_client):
    pid = _seed_verified_provider("expired@example.com", "x")
    past = int(app_module._now().timestamp()) - 120
    bad = jwt.encode(
        {
            "sub": pid,
            "adm": False,
            "iss": app_module.JWT_ISS,
            "aud": app_module.JWT_AUD,
            "iat": past - 3600,
            "exp": past,
            "rmb": 0,
        },
        app_module.SECRET,
        algorithm="HS256",
    )
    res = test_client.get("/me", headers={"Authorization": f"Bearer {bad}"})
    assert res.status_code == 401
    assert (res.get_json() or {}).get("error") == "unauthorized"
