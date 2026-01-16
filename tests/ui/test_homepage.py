import re

from playwright.sync_api import Page, expect


def test_homepage_title(app_base_url: str, page: Page) -> None:
    page.goto(f"{app_base_url}/", wait_until="domcontentloaded")
    expect(page).to_have_title(re.compile("Terminmarktplatz"))
