from urllib.parse import quote

import pytest
from playwright.sync_api import Page, expect


def _normalize(val: str | None) -> str:
    return (val or "").strip()


def _fetch_slots(page: Page, app_base_url: str) -> list[dict]:
    resp = page.request.get(f"{app_base_url}/public/slots?include_full=1")
    assert resp.ok, f"API error: {resp.status}"
    return resp.json() or []


def _open_search(page: Page, app_base_url: str, title: str, ort: str | None = None) -> None:
    url = f"{app_base_url}/suche.html?q={quote(title)}"
    if ort:
        url += f"&ort={quote(ort)}"
    page.goto(url, wait_until="domcontentloaded")


def test_search_filters_visible(app_base_url: str, page: Page) -> None:
    page.goto(f"{app_base_url}/suche.html", wait_until="domcontentloaded")
    expect(page.locator("#filters")).to_be_visible()
    expect(page.locator("#f-q")).to_be_visible()
    expect(page.locator("#f-ort")).to_be_visible()
    expect(page.locator("#search-day")).to_be_visible()
    expect(page.locator("#sort")).to_be_visible()


def test_search_card_has_booking_button(app_base_url: str, page: Page) -> None:
    data = _fetch_slots(page, app_base_url)
    slot = next((s for s in data if _normalize(s.get("title"))), None)
    if not slot:
        pytest.skip("No slot available for search test")

    title = _normalize(slot.get("title"))
    ort = _normalize(slot.get("city")) or _normalize(slot.get("zip"))
    _open_search(page, app_base_url, title, ort)

    card = page.locator(".card", has_text=title).first
    expect(card).to_be_visible()
    expect(card.locator("button[data-book]")).to_be_visible()


def test_search_card_shows_category_and_time(app_base_url: str, page: Page) -> None:
    data = _fetch_slots(page, app_base_url)
    slot = next((s for s in data if _normalize(s.get("title")) and _normalize(s.get("category"))), None)
    if not slot:
        pytest.skip("No slot with category available for search test")

    title = _normalize(slot.get("title"))
    ort = _normalize(slot.get("city")) or _normalize(slot.get("zip"))
    _open_search(page, app_base_url, title, ort)

    card = page.locator(".card", has_text=title).first
    expect(card).to_be_visible()
    expect(card).to_contain_text("Kategorie:")
    # Datum/Uhrzeit ist fett im Card-Header
    expect(card.locator("b")).to_have_count(1)


def test_search_card_shows_address_when_available(app_base_url: str, page: Page) -> None:
    data = _fetch_slots(page, app_base_url)
    slot = next((s for s in data if _normalize(s.get("location"))), None)
    if not slot:
        pytest.skip("No slot with location available for search test")

    title = _normalize(slot.get("title"))
    ort = _normalize(slot.get("city")) or _normalize(slot.get("zip"))
    _open_search(page, app_base_url, title, ort)

    card = page.locator(".card", has_text=title).first
    expect(card).to_be_visible()
    expect(card).to_contain_text("Adresse:")
