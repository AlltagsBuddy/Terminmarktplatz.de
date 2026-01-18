import pytest

from tests.api.http_client import HttpClient


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
def test_pages_are_reachable(app_base_url: str, path: str, expected_title: str) -> None:
    client = HttpClient()
    response = client.get(f"{app_base_url}{path}")
    assert response.status_code == 200
    html = response.text.lower()
    assert "<html" in html
    assert expected_title.lower() in html
