import time
from urllib.parse import quote

import pytest
from playwright.sync_api import Page, expect


def _normalize(val: str | None) -> str:
    return (val or "").strip()


def _slot_address(slot: dict) -> str:
    line1 = " ".join(p for p in [_normalize(slot.get("street")), _normalize(slot.get("house_number"))] if p)
    line2 = " ".join(p for p in [_normalize(slot.get("zip")), _normalize(slot.get("city"))] if p)
    if line1 or line2:
        return ", ".join(p for p in [line1, line2] if p)
    return _normalize(slot.get("location"))


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


def _open_search_for_slot(page: Page, app_base_url: str, slot: dict) -> None:
    title = _normalize(slot.get("title"))
    ort = _normalize(slot.get("city")) or _normalize(slot.get("zip"))
    url = f"{app_base_url}/suche.html?q={quote(title)}"
    if ort:
        url += f"&ort={quote(ort)}"
    page.goto(url, wait_until="domcontentloaded")


def test_search_shows_termin_address(app_base_url: str, page: Page) -> None:
    data = _fetch_slots(page, app_base_url)

    pick = None
    for slot in data:
        address = _slot_address(slot)
        title = _normalize(slot.get("title"))
        if address and title:
            pick = (slot, address, title)
            break

    if not pick:
        pytest.skip("No slot with termin address available for test")

    slot, expected_address, title = pick
    _open_search_for_slot(page, app_base_url, slot)

    card = page.locator(".card", has_text=title).first
    expect(card).to_be_visible()
    expect(card).to_contain_text("Adresse:")
    expect(card).to_contain_text(expected_address)


def test_search_shows_provider_row_and_logo_or_initial(app_base_url: str, page: Page) -> None:
    data = _fetch_slots(page, app_base_url)
    slot = next((s for s in data if _normalize(s.get("title"))), None)
    if not slot:
        pytest.skip("No slot available for test")

    _open_search_for_slot(page, app_base_url, slot)
    title = _normalize(slot.get("title"))
    card = page.locator(".card", has_text=title).first
    expect(card).to_be_visible()
    expect(card).to_contain_text("Anbieter:")

    logo_img = card.locator("img.provider-logo")
    logo_fallback = card.locator(".provider-logo-fallback")
    assert logo_img.count() + logo_fallback.count() >= 1


def test_search_shows_description_when_present(app_base_url: str, page: Page) -> None:
    data = _fetch_slots(page, app_base_url)
    slot = next((s for s in data if _normalize(s.get("description"))), None)
    if not slot:
        pytest.skip("No slot with description available for test")

    _open_search_for_slot(page, app_base_url, slot)
    title = _normalize(slot.get("title"))
    description = _normalize(slot.get("description"))
    card = page.locator(".card", has_text=title).first
    expect(card).to_be_visible()
    expect(card).to_contain_text(description)
