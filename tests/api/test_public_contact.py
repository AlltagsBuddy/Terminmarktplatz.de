import os
import tempfile

import pytest

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("EMAILS_ENABLED", "false")

import app as app_module


@pytest.fixture(scope="function")
def test_client():
    return app_module.app.test_client()


def test_public_contact_requires_fields(test_client):
    r = test_client.post("/public/contact", json={"name": "Max"})
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "missing_fields"


def test_public_contact_invalid_email(test_client):
    payload = {
        "name": "Max",
        "email": "invalid-email",
        "subject": "Test",
        "message": "Hallo",
        "consent": True,
    }
    r = test_client.post("/public/contact", json=payload)
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_email"


def test_public_contact_requires_consent(test_client):
    payload = {
        "name": "Max",
        "email": "max@example.com",
        "subject": "Test",
        "message": "Hallo",
        "consent": False,
    }
    r = test_client.post("/public/contact", json=payload)
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "consent_required"


def test_public_contact_success(test_client):
    payload = {
        "name": "Max",
        "email": "max@example.com",
        "subject": "Frage",
        "message": "Hallo Terminmarktplatz",
        "consent": True,
    }
    r = test_client.post("/public/contact", json=payload)
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True
    assert data.get("delivered") is True
