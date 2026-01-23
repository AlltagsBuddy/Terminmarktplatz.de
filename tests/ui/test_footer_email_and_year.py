import time
from datetime import datetime

import pytest
from playwright.sync_api import Page, expect


PAGES = [
    "/",
    "/anbieter.html",
    "/suchende.html",
    "/preise.html",
    "/suche.html",
    "/kategorien.html",
    "/kontakt.html",
    "/hilfe.html",
    "/technik.html",
    "/login.html",
    "/impressum.html",
    "/datenschutz.html",
    "/agb.html",
    "/widerruf.html",
    "/anbieter-profil.html",
    "/anbieter-portal.html",
    "/anbieter-bewertungen.html",
    "/cookie-einstellungen.html",
]


def _goto_with_retry(page: Page, url: str, attempts: int = 3) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            page.goto(url, wait_until="domcontentloaded")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(1.5)
    if last_error:
        raise last_error


@pytest.mark.parametrize("path", PAGES)
def test_footer_email_link_present(app_base_url: str, page: Page, path: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _goto_with_retry(page, f"{app_base_url}{path}")

    footer = page.locator("footer")
    expect(footer).to_be_visible()

    mailto = footer.locator("a[href^='mailto:']")
    expect(mailto.first).to_be_visible()
    expect(mailto.first).to_have_attribute("href", "mailto:info@terminmarktplatz.de")


@pytest.mark.parametrize("path", PAGES)
def test_footer_copyright_year(app_base_url: str, page: Page, path: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _goto_with_retry(page, f"{app_base_url}{path}")

    footer = page.locator("footer")
    expect(footer).to_be_visible()

    year = str(datetime.now().year)
    copyright_el = footer.locator(".copyright")
    expect(copyright_el).to_be_visible()
    expect(copyright_el).to_contain_text(year)
