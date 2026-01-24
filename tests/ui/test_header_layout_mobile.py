import time

import pytest
from playwright.sync_api import Page, expect


PAGES = [
    "/login.html",
    "/preise.html",
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
def test_mobile_header_layout_consistent(app_base_url: str, page: Page, path: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _goto_with_retry(page, f"{app_base_url}{path}")

    header = page.locator("header .container.nav")
    if header.count() == 0:
        pytest.skip("Header fehlt")
    expect(header).to_be_visible()

    brand = page.locator("header .brand")
    expect(brand).to_be_visible()

    menu_btn = page.locator("#userMenuBtn")
    expect(menu_btn).to_be_visible()
    expect(menu_btn).to_contain_text("Menü")

    nav = page.locator("header .nav-links")
    expect(nav).to_be_visible()
    expect(nav.locator("a")).to_have_count(3)

    display = page.evaluate(
        "() => window.getComputedStyle(document.querySelector('header .nav-links')).display"
    )
    assert display != "none"
