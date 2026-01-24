import time

import pytest
from playwright.sync_api import Page, expect


CTA_PAGES = [
    "/",
    "/anbieter.html",
    "/suchende.html",
    "/preise.html",
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


@pytest.mark.parametrize("path", CTA_PAGES)
def test_hero_has_primary_cta(app_base_url: str, page: Page, path: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _goto_with_retry(page, f"{app_base_url}{path}")

    hero = page.locator(".hero")
    if hero.count() == 0:
        pytest.skip("Kein Hero vorhanden")
    expect(hero).to_be_visible()
    expect(hero.locator(".btn.primary").first).to_be_visible()
