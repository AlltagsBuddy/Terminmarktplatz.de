import pytest
from playwright.sync_api import Page, expect


@pytest.mark.parametrize(
    ("path", "expected_h1"),
    [
        ("/", "Freie Termine in Minuten bereitstellen, füllen – oder finden."),
        ("/agb", "Allgemeine Geschäftsbedingungen (AGB)"),
        ("/anbieter", "Lücken füllen statt Umsatz verlieren."),
        ("/hilfe", "Wie können wir dir helfen?"),
        ("/impressum", "Impressum"),
        ("/kontakt", "Schreib uns eine Nachricht."),
        ("/login", "Anmelden & registrieren"),
        ("/suchende", "Freie Termine finden – ohne Anmeldung."),
        ("/preise", "Kostenlos starten. Nur bei Erfolg zahlen."),
        ("/datenschutz", "Datenschutzerklärung"),
        ("/widerruf", "Widerruf & Widerrufsbelehrung"),
        ("/cookie-einstellungen", "Cookie-Einstellungen"),
    ],
)
def test_pages_have_expected_h1(app_base_url: str, page: Page, path: str, expected_h1: str) -> None:
    page.goto(f"{app_base_url}{path}", wait_until="domcontentloaded")
    heading = page.locator("h1").first
    expect(heading).to_be_visible()
    expect(heading).to_have_text(expected_h1)
