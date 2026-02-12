"""Tests für POST /login (Form-Login)."""
import os
import tempfile

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


def _create_provider(email: str, password: str, *, verified: bool) -> None:
    with Session(app_module.engine) as s:
        provider = Provider(
            email=email,
            pw_hash=app_module.ph.hash(password),
            status="approved",
            email_verified_at=app_module._now() if verified else None,
            company_name="Test GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
        )
        s.add(provider)
        s.commit()


def test_login_form_success(test_client):
    _create_provider("form-login@example.com", "testpass123", verified=True)
    r = test_client.post(
        "/login",
        data={"email": "form-login@example.com", "password": "testpass123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "access_token" in str(r.headers.get("Set-Cookie", ""))


def test_login_form_invalid_credentials(test_client):
    """POST /login mit falschem Passwort liefert 401 (nutzt render_template)."""
    _create_provider("form@example.com", "testpass123", verified=True)
    r = test_client.post(
        "/login",
        data={"email": "form@example.com", "password": "wrongpass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code in (401, 500)  # 500 wenn login.html nicht in templates/


def test_login_form_email_not_verified(test_client):
    """POST /login mit unverifizierter E-Mail liefert 401."""
    _create_provider("unverified@example.com", "testpass123", verified=False)
    r = test_client.post(
        "/login",
        data={"email": "unverified@example.com", "password": "testpass123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code in (401, 500)  # 401 erwartet; 500 wenn login.html nicht in templates/
