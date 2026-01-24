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
def test_menu_toggle_and_static_items_visible(app_base_url: str, page: Page, path: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _goto_with_retry(page, f"{app_base_url}{path}")

    menu_btn = page.locator("#userMenuBtn")
    if menu_btn.count() == 0:
        pytest.skip("Kein Menü-Button vorhanden")
    expect(menu_btn).to_be_visible()

    menu = page.locator("#userMenu")
    expect(menu).to_be_hidden()

    menu_btn.click()
    expect(menu).to_be_visible()
    expect(menu.locator("text=Kontakt")).to_be_visible()
    expect(menu.locator("text=Hilfe")).to_be_visible()

    page.keyboard.press("Escape")
    expect(menu).to_be_hidden()
