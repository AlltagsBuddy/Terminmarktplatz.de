"""
Tests für HTML-Routen (suche, bewertung, reset-password, agb, paket-buchen, etc.).
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


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _create_provider(plan: str | None = None) -> str:
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"html-{uuid4()}@example.com",
            pw_hash="test",
            company_name="Test GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        if plan:
            p.plan = plan
        s.add(p)
        s.commit()
        return p.id


# --- Öffentliche HTML-Routen ohne Auth ---


def test_suche_page_returns_html(test_client):
    """GET /suche liefert HTML mit Suche."""
    r = test_client.get("/suche")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "suche" in html.lower() or "<html" in html.lower()


def test_suche_html_page_returns_html(test_client):
    """GET /suche.html liefert HTML."""
    r = test_client.get("/suche.html")
    assert r.status_code == 200
    assert "text/html" in r.content_type


def test_reset_password_page_returns_html(test_client):
    """GET /reset-password und /reset-password.html liefern HTML."""
    for path in ["/reset-password", "/reset-password.html"]:
        r = test_client.get(path)
        assert r.status_code == 200
        assert "<html" in r.get_data(as_text=True).lower()


def test_agb_page_returns_html(test_client):
    """GET /agb liefert AGB-Seite."""
    r = test_client.get("/agb")
    assert r.status_code == 200
    html = r.get_data(as_text=True).lower()
    assert "agb" in html or "html" in html


def test_impressum_page_returns_html(test_client):
    """GET /impressum liefert Impressum."""
    r = test_client.get("/impressum")
    assert r.status_code == 200
    assert "impressum" in r.get_data(as_text=True).lower()


def test_datenschutz_page_returns_html(test_client):
    """GET /datenschutz liefert Datenschutz-Seite."""
    r = test_client.get("/datenschutz")
    assert r.status_code == 200
    assert "datenschutz" in r.get_data(as_text=True).lower()


# --- Bewertung GET/POST mit ungültigem Token ---


def test_bewertung_get_without_token_shows_error(test_client):
    """GET /bewertung ohne Token zeigt Fehlermeldung."""
    r = test_client.get("/bewertung")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "ungültig" in html.lower() or "error" in html.lower()


def test_bewertung_get_with_invalid_token_shows_error(test_client):
    """GET /bewertung mit ungültigem Token zeigt Fehlermeldung."""
    r = test_client.get("/bewertung?token=invalid-token-xyz")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "ungültig" in html.lower() or "error" in html.lower()


def test_bewertung_post_without_token_shows_error(test_client):
    """POST /bewertung ohne Token zeigt Fehlermeldung."""
    r = test_client.post(
        "/bewertung",
        data={"rating": "5", "comment": "Test"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "ungültig" in html.lower() or "error" in html.lower()


def test_bewertung_post_invalid_rating_shows_error(test_client):
    """POST /bewertung mit ungültiger Bewertung (0) zeigt Fehlermeldung."""
    r = test_client.post(
        "/bewertung",
        data={"token": "any", "rating": "0", "comment": "Test"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "1 bis 5" in html or "ungültig" in html.lower() or "error" in html.lower()


# --- Geschützte HTML-Routen (auth_required) ---
# HTML-Routen leiten bei fehlender Auth auf /login.html um (302), nicht 401.


def test_anbieter_portal_requires_auth(test_client):
    """GET /anbieter-portal leitet ohne Token auf Login um."""
    r = test_client.get("/anbieter-portal", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in (r.location or "")


def test_anbieter_portal_html_requires_auth(test_client):
    """GET /anbieter-portal.html leitet ohne Token auf Login um."""
    r = test_client.get("/anbieter-portal.html", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in (r.location or "")


def test_anbieter_profil_requires_auth(test_client):
    """GET /anbieter-profil leitet ohne Token auf Login um."""
    r = test_client.get("/anbieter-profil", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in (r.location or "")


def test_anbieter_bewertungen_requires_auth(test_client):
    """GET /anbieter-bewertungen leitet ohne Token auf Login um."""
    r = test_client.get("/anbieter-bewertungen", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in (r.location or "")


def test_paket_buchen_requires_auth(test_client):
    """GET /paket-buchen leitet ohne Token auf Login um."""
    r = test_client.get("/paket-buchen", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in (r.location or "")


def test_anbieter_portal_with_auth_returns_html(test_client):
    """GET /anbieter-portal mit Token liefert HTML."""
    provider_id = _create_provider()
    r = test_client.get("/anbieter-portal", headers=_auth_headers(provider_id))
    assert r.status_code == 200
    assert "html" in (r.content_type or "").lower()


def test_business_dashboard_html_requires_auth(test_client):
    """GET /business-dashboard.html ohne Login → Redirect zum Login."""
    r = test_client.get("/business-dashboard.html", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in (r.location or "")


def test_business_dashboard_html_redirects_non_business(test_client):
    """Business-Dashboard nur mit Business-Paket."""
    pid = _create_provider(plan="profi")
    r = test_client.get(
        "/business-dashboard.html",
        headers=_auth_headers(pid),
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "preise" in (r.location or "").lower()


def test_business_dashboard_html_ok_for_business(test_client):
    """GET /business-dashboard.html mit Business-Paket liefert HTML."""
    pid = _create_provider(plan="business")
    r = test_client.get("/business-dashboard.html", headers=_auth_headers(pid))
    assert r.status_code == 200
    assert "html" in (r.content_type or "").lower()


def test_business_dashboard_api_requires_business(test_client):
    """GET /business/dashboard ist ohne Business-Paket nicht erlaubt."""
    pid = _create_provider(plan="starter")
    r = test_client.get("/business/dashboard", headers=_auth_headers(pid))
    assert r.status_code == 403

    pid_biz = _create_provider(plan="business")
    r2 = test_client.get("/business/dashboard", headers=_auth_headers(pid_biz))
    assert r2.status_code == 200
    data = r2.get_json()
    assert data is not None
    assert "bookings_per_month" in data
    assert "revenue_per_month" in data

