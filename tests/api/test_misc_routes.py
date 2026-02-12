"""
Tests für diverse Routen: favicon, healthz, auth/verify, any_page catch-all.
"""
import os
import tempfile
from uuid import uuid4

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


def test_favicon_redirects(test_client):
    """GET /favicon.ico leitet auf static um."""
    r = test_client.get("/favicon.ico", follow_redirects=False)
    assert r.status_code == 302
    assert "/static/" in r.location


def test_healthz_returns_json(test_client):
    """GET /healthz liefert JSON mit db-Status."""
    r = test_client.get("/healthz")
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert data.get("ok") is True
    assert data.get("service") == "api"
    assert "time" in data
    assert data.get("db") == "ok"


def test_auth_verify_invalid_token_redirects(test_client):
    """GET /auth/verify?token=invalid leitet mit verified=0 um."""
    r = test_client.get("/auth/verify?token=invalid-token-xyz", follow_redirects=False)
    assert r.status_code == 302
    assert r.location and "verified=0" in r.location


def test_auth_verify_invalid_token_debug_returns_json(test_client):
    """GET /auth/verify?token=invalid&debug=1 liefert JSON."""
    r = test_client.get("/auth/verify?token=invalid&debug=1")
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert data.get("ok") is False
    assert "redirect" in data


def test_auth_verify_empty_token_redirects(test_client):
    """GET /auth/verify ohne Token leitet mit verified=0 um."""
    r = test_client.get("/auth/verify", follow_redirects=False)
    assert r.status_code == 302
    assert "verified=0" in (r.location or "")


def test_any_page_hilfe_returns_html(test_client):
    """Catch-all /hilfe liefert hilfe.html."""
    r = test_client.get("/hilfe")
    assert r.status_code == 200
    html = r.get_data(as_text=True).lower()
    assert "<html" in html
    assert "hilfe" in html


def test_any_page_anbieter_returns_html(test_client):
    """Catch-all /anbieter liefert anbieter.html."""
    r = test_client.get("/anbieter")
    assert r.status_code == 200
    html = r.get_data(as_text=True).lower()
    assert "<html" in html


def test_any_page_admin_slug_returns_404(test_client):
    """Catch-all /admin/xyz liefert 404 (API-Routen nicht abfangen)."""
    r = test_client.get("/admin/xyz")
    assert r.status_code == 404


def test_any_page_api_like_slug_returns_404(test_client):
    """Catch-all für api-ähnliche Slugs liefert 404."""
    r = test_client.get("/api")
    assert r.status_code == 404


def test_any_page_nonexistent_returns_404(test_client):
    """Catch-all für nicht existierende Datei liefert 404."""
    r = test_client.get("/gibt-es-nicht-12345")
    assert r.status_code == 404


def test_sitemap_returns_xml(test_client):
    """GET /sitemap.xml liefert XML."""
    r = test_client.get("/sitemap.xml")
    assert r.status_code == 200
    body = r.get_data(as_text=True).lower()
    assert "<urlset" in body or "xml" in body
