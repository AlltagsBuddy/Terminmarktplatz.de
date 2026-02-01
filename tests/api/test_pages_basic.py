import os
import tempfile

import pytest

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")

import app as app_module


@pytest.fixture(scope="function")
def test_client():
    return app_module.app.test_client()


@pytest.mark.parametrize(
    ("path", "expected_title"),
    [
        ("/", "Terminmarktplatz"),
        ("/agb", "AGB | Terminmarktplatz"),
        ("/anbieter", "Für Anbieter:innen | Terminmarktplatz"),
        ("/hilfe", "Hilfe & FAQ | Terminmarktplatz"),
        ("/impressum", "Impressum | Terminmarktplatz"),
        ("/kontakt", "Kontakt | Terminmarktplatz"),
        ("/login", "Anbieter – Anmelden & Registrieren | Terminmarktplatz"),
        ("/suchende", "Für Suchende | Terminmarktplatz"),
        ("/preise", "Preise für Anbieter:innen | Terminmarktplatz"),
        ("/datenschutz", "Datenschutzerklärung | Terminmarktplatz"),
        ("/widerruf", "Widerruf & Widerrufsbelehrung | Terminmarktplatz"),
        ("/cookie-einstellungen", "Cookie-Einstellungen | Terminmarktplatz"),
    ],
)
def test_pages_are_reachable(test_client, path: str, expected_title: str) -> None:
    response = test_client.get(path)
    assert response.status_code == 200
    html = response.get_data(as_text=True).lower()
    assert "<html" in html
    assert expected_title.lower() in html
