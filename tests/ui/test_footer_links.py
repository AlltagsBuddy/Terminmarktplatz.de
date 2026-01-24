import time

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


def _normalize_href(href: str | None) -> str:
    if not href:
        return ""
    return href.split("?", 1)[0].split("#", 1)[0]


@pytest.mark.parametrize("path", PAGES)
def test_footer_legal_links_present(app_base_url: str, page: Page, path: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _goto_with_retry(page, f"{app_base_url}{path}")

    footer = page.locator("footer")
    expect(footer).to_be_visible()

    links = footer.locator("a")
    expect(links.first).to_be_visible()

    hrefs = links.evaluate_all("els => els.map(el => el.getAttribute('href'))")
    normalized = {_normalize_href(href) for href in hrefs}
    for expected in [
        "impressum.html",
        "datenschutz.html",
        "agb.html",
        "widerruf.html",
        "cookie-einstellungen.html",
    ]:
        assert expected in normalized
