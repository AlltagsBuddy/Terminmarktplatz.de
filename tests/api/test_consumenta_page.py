"""
Tests für die /consumenta Landingpage (Consumenta-Messe-Angebot 2026).
Prüft Route-Verfügbarkeit, HTML-Inhalt und rechtlich relevante Angaben.

Ausführen (aus App-Verzeichnis):
    cd /opt/terminmarktplatz-test
    venv/bin/pytest tests/api/test_consumenta_page.py -v
"""
import os
import tempfile

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("FRONTEND_URL", "http://testserver")

import app as app_module
from models import Base

import pytest


@pytest.fixture(scope="module")
def client():
    # Niemals Tabellen loeschen - DB kann die echte Test-DB sein
    if app_module.engine.url.get_backend_name() == "sqlite":
        Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


class TestConsumetaPage:

    def test_route_returns_200(self, client):
        """GET /consumenta → HTTP 200."""
        r = client.get("/consumenta")
        assert r.status_code == 200, f"Erwartet 200, bekam {r.status_code}"

    def test_content_type_is_html(self, client):
        """GET /consumenta → Content-Type: text/html."""
        r = client.get("/consumenta")
        assert "text/html" in r.content_type

    def test_noindex_present(self, client):
        """Seite enthält noindex (nicht von Suchmaschinen indexiert)."""
        html = client.get("/consumenta").get_data(as_text=True)
        assert "noindex" in html, "Fehlt: meta robots noindex"

    def test_promo_code_visible(self, client):
        """Aktionscode CONSUMENTA26 ist auf der Seite sichtbar."""
        html = client.get("/consumenta").get_data(as_text=True)
        assert "CONSUMENTA26" in html, "Fehlt: Aktionscode CONSUMENTA26"

    def test_redeem_deadline_visible(self, client):
        """Einlöse-Deadline 30. November 2026 ist sichtbar."""
        html = client.get("/consumenta").get_data(as_text=True)
        assert "30. November 2026" in html, "Fehlt: Einlöse-Deadline 30.11.2026"

    def test_test_end_date_visible(self, client):
        """Testende-Datum 28. Februar 2027 ist sichtbar."""
        html = client.get("/consumenta").get_data(as_text=True)
        assert "28. Februar 2027" in html, "Fehlt: Testende-Datum 28.02.2027"

    def test_no_autoabo_notice(self, client):
        """Seite enthält Hinweis auf kein automatisches Abo."""
        html = client.get("/consumenta").get_data(as_text=True).lower()
        assert "automatisch" in html, "Fehlt: Hinweis 'endet automatisch'"

    def test_transaction_fee_disclosed(self, client):
        """2€ Transaktionsgebühr ist transparent ausgewiesen (UWG-Pflicht)."""
        html = client.get("/consumenta").get_data(as_text=True)
        assert "Transaktionsgebühr" in html, "Fehlt: Hinweis Transaktionsgebühr"
        assert "2" in html and "€" in html, "Fehlt: Betrag 2 €"

    def test_cta_links_to_register_with_code(self, client):
        """CTA-Button enthält Link zur Registrierung mit Promo-Code."""
        html = client.get("/consumenta").get_data(as_text=True)
        assert "tab=register" in html, "Fehlt: CTA Register-Link"
        assert "CONSUMENTA26" in html, "Fehlt: Promo-Code im CTA-Link"

    def test_header_contains_brand(self, client):
        """Seite enthält Markenname Terminmarktplatz im Header."""
        html = client.get("/consumenta").get_data(as_text=True).lower()
        assert "terminmarktplatz" in html, "Fehlt: Markenname im Header"

    def test_footer_impressum_link(self, client):
        """Seite enthält Link zum Impressum (Anbieterkennzeichnung §5 DDG)."""
        html = client.get("/consumenta").get_data(as_text=True).lower()
        assert "impressum" in html, "Fehlt: Impressum-Link im Footer"

    def test_footer_datenschutz_link(self, client):
        """Seite enthält Link zur Datenschutzerklärung (DSGVO Art. 13)."""
        html = client.get("/consumenta").get_data(as_text=True).lower()
        assert "datenschutz" in html, "Fehlt: Datenschutz-Link im Footer"
