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


def _create_provider(email: str) -> str:
    with Session(app_module.engine) as s:
        provider = Provider(
            email=email,
            pw_hash=app_module.ph.hash("testpass123"),
            status="approved",
            email_verified_at=app_module._now(),
            street="Teststrasse",
            zip="12345",
            city="Teststadt",
            phone="1234567",
        )
        s.add(provider)
        s.commit()
        return str(provider.id)


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def test_me_update_invalid_zip(test_client):
    provider_id = _create_provider("zip@example.com")
    r = test_client.put(
        "/me",
        json={"zip": "12a"},
        headers=_auth_headers(provider_id),
    )
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_zip"


def test_me_update_invalid_logo_url(test_client):
    provider_id = _create_provider("logo@example.com")
    r = test_client.put(
        "/me",
        json={"logo_url": "javascript:alert(1)"},
        headers=_auth_headers(provider_id),
    )
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_logo_url"


def test_me_update_house_number_combines_street(test_client):
    provider_id = _create_provider("hn@example.com")
    r = test_client.put(
        "/me",
        json={"street": "Neue Strasse", "house_number": "5a"},
        headers=_auth_headers(provider_id),
    )
    assert r.status_code == 200

    r_me = test_client.get("/me", headers=_auth_headers(provider_id))
    assert r_me.status_code == 200
    data = r_me.get_json() or {}
    assert data.get("street") == "Neue Strasse"
    assert data.get("house_number") == "5a"


def test_me_update_revokes_logo_consent(test_client):
    provider_id = _create_provider("consent@example.com")
    r1 = test_client.put(
        "/me",
        json={"logo_url": "https://example.com/logo.png", "consent_logo_display": True},
        headers=_auth_headers(provider_id),
    )
    assert r1.status_code == 200

    r2 = test_client.put(
        "/me",
        json={"consent_logo_display": False},
        headers=_auth_headers(provider_id),
    )
    assert r2.status_code == 200

    r_me = test_client.get("/me", headers=_auth_headers(provider_id))
    data = r_me.get_json() or {}
    assert data.get("consent_logo_display") is False
    assert data.get("logo_url") is None
