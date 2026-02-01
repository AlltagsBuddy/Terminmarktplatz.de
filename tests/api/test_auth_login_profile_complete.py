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


def _create_provider(email: str, password: str, *, complete: bool) -> None:
    kwargs = {
        "email": email,
        "pw_hash": app_module.ph.hash(password),
        "status": "approved",
        "email_verified_at": app_module._now(),
    }
    if complete:
        kwargs.update(
            {
                "company_name": "Firma",
                "branch": "Friseur",
                "street": "Teststrasse 1",
                "zip": "12345",
                "city": "Teststadt",
                "phone": "1234567",
            }
        )
    with Session(app_module.engine) as s:
        s.add(Provider(**kwargs))
        s.commit()


def test_login_profile_complete_true(test_client):
    _create_provider("complete@example.com", "testpass123", complete=True)
    r = test_client.post(
        "/auth/login",
        json={"email": "complete@example.com", "password": "testpass123"},
    )
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True
    assert data.get("profile_complete") is True


def test_login_profile_complete_false(test_client):
    _create_provider("incomplete@example.com", "testpass123", complete=False)
    r = test_client.post(
        "/auth/login",
        json={"email": "incomplete@example.com", "password": "testpass123"},
    )
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True
    assert data.get("profile_complete") is False
