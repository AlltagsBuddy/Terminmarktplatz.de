import time
from urllib.parse import quote

import pytest
from playwright.sync_api import Page, expect


def _normalize(val: str | None) -> str:
    return (val or "").strip()


def _fetch_slots(page: Page, app_base_url: str) -> list[dict]:
    last_status = None
    for _ in range(3):
        try:
            resp = page.request.get(
                f"{app_base_url}/public/slots?include_full=1",
                timeout=60_000,
            )
        except Exception:
            time.sleep(1.5)
            continue
        last_status = resp.status
        if resp.ok:
            return resp.json() or []
        time.sleep(1.5)
    pytest.skip(f"public slots API not reachable (last status {last_status})")


def _open_search(page: Page, app_base_url: str, title: str, ort: str | None = None) -> None:
    url = f"{app_base_url}/suche.html?q={quote(title)}"
    if ort:
        url += f"&ort={quote(ort)}"
    page.goto(url, wait_until="domcontentloaded")


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


def test_search_filters_visible(app_base_url: str, page: Page) -> None:
    page.goto(f"{app_base_url}/suche.html", wait_until="domcontentloaded")
    page.wait_for_selector("#filters", timeout=20_000)
    expect(page.locator("#filters")).to_be_visible()
    expect(page.locator("#f-q")).to_be_visible()
    expect(page.locator("#f-ort")).to_be_visible()
    expect(page.locator("#search-day-from")).to_be_visible()
    expect(page.locator("#search-day-to")).to_be_visible()
    expect(page.locator("#sort")).to_be_visible()


def test_search_time_filter_options(app_base_url: str, page: Page) -> None:
    _goto_with_retry(page, f"{app_base_url}/suche.html")
    page.wait_for_selector("#f-zeit", timeout=20_000)
    options = page.locator("#f-zeit option")
    expect(options).to_contain_text(
        ["Beliebig", "Morgens (6–11)", "Mittags (11–16)", "Abends (16–22)", "Nachts (22–6)"]
    )


def test_search_radius_requires_location(app_base_url: str, page: Page) -> None:
    _goto_with_retry(page, f"{app_base_url}/suche.html")
    page.wait_for_selector("#filters", timeout=20_000)
    page.select_option("#f-radius", "10")
    page.locator("#filters button[type='submit']").click()
    err = page.locator("#filter-error")
    expect(err).to_be_visible()
    expect(err).to_contain_text("Umkreis kann nur mit Ort/PLZ verwendet werden.")


def test_search_date_range_validation(app_base_url: str, page: Page) -> None:
    _goto_with_retry(page, f"{app_base_url}/suche.html")
    page.wait_for_selector("#filters", timeout=20_000)
    page.fill("#search-day-from", "2025-05-10")
    page.fill("#search-day-to", "2025-05-01")
    page.locator("#filters button[type='submit']").click()
    err = page.locator("#filter-error")
    expect(err).to_be_visible()
    expect(err).to_contain_text("Bitte gültigen Datumsbereich wählen")


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
