"""
Tests für OPTIONS Preflight und CORS-Header.
"""
import os
import tempfile

import pytest

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("BASE_URL", "http://testserver")

import app as app_module
from models import Base


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def test_options_auth_login_returns_200(test_client):
    """OPTIONS /auth/login mit Origin liefert 200."""
    r = test_client.options(
        "/auth/login",
        headers={"Origin": "http://localhost:3000"},
    )
    assert r.status_code == 200


def test_options_slots_returns_200(test_client):
    """OPTIONS /slots mit Origin liefert 200."""
    r = test_client.options(
        "/slots",
        headers={"Origin": "http://localhost:3000"},
    )
    assert r.status_code == 200


def test_options_public_slots_returns_200(test_client):
    """OPTIONS /public/slots mit Origin liefert 200."""
    r = test_client.options(
        "/public/slots",
        headers={"Origin": "https://example.com"},
    )
    assert r.status_code == 200


def test_options_auth_login_includes_cors_headers(test_client):
    """OPTIONS /auth/login setzt CORS-Header wenn Origin gesendet."""
    r = test_client.options(
        "/auth/login",
        headers={"Origin": "http://127.0.0.1:5000"},
    )
    assert r.status_code == 200
    # Lokale IPs werden im before_request/after_request erlaubt
    assert "Access-Control-Allow-Origin" in r.headers
    assert "Access-Control-Allow-Methods" in r.headers
    assert "OPTIONS" in r.headers.get("Access-Control-Allow-Methods", "")
