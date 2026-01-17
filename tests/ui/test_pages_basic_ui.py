import pytest
from playwright.sync_api import Page, expect


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
def test_pages_are_reachable_ui(app_base_url: str, page: Page, path: str, expected_title: str) -> None:
    response = page.goto(f"{app_base_url}{path}", wait_until="domcontentloaded")
    assert response is not None and response.ok
    expect(page.locator("html")).to_be_visible()
    expect(page).to_have_title(expected_title)
