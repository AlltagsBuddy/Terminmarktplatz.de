import re
import time

import pytest
from playwright.sync_api import Page, expect


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


def test_provider_portal_requires_login(app_base_url: str, page: Page) -> None:
    _goto_with_retry(page, f"{app_base_url}/anbieter-portal.html")
    expect(page).to_have_url(re.compile(r"/login\.html\?next=/anbieter-portal\.html"))
    expect(page.locator("#login-form")).to_be_visible()


def test_provider_portal_login_fields_visible(app_base_url: str, page: Page) -> None:
    _goto_with_retry(page, f"{app_base_url}/anbieter-portal.html")
    expect(page.locator("#login-email")).to_be_visible()
    expect(page.locator("#login-password")).to_be_visible()


def test_provider_portal_after_login(provider_login, page: Page) -> None:
    provider_login()
    expect(page.locator("#form-slot")).to_be_visible()


def _enable_slot_fields(page: Page) -> None:
    page.evaluate("document.getElementById('slot-fields').disabled = false;")


def _set_category(page: Page, value: str = "Friseur") -> None:
    page.evaluate(
        "(val) => { const el = document.getElementById('sl-cat'); if (el) el.value = val; }",
        value,
    )


def test_provider_portal_slot_required_fields_validation(provider_login, page: Page) -> None:
    provider_login()
    page.wait_for_selector("#form-slot", timeout=20_000)
    _enable_slot_fields(page)
    page.click("#slot-submit-btn")
    msg = page.locator("#msg-slot")
    expect(msg).to_contain_text("Bitte alle Pflichtfelder")


def test_provider_portal_slot_zip_validation(provider_login, page: Page) -> None:
    provider_login()
    page.wait_for_selector("#form-slot", timeout=20_000)
    _enable_slot_fields(page)
    _set_category(page, "Friseur")

    page.fill("#sl-title", "Test Slot")
    page.fill("#sl-date", "2026-01-20")
    page.fill("#sl-start", "09:00")
    page.fill("#sl-duration", "30")
    page.fill("#sl-street", "Musterstraße 12")
    page.fill("#sl-zip", "1234")
    page.fill("#sl-city", "Hallstadt")

    page.click("#slot-submit-btn")
    msg = page.locator("#msg-slot")
    expect(msg).to_contain_text("PLZ muss 5-stellig sein.")
