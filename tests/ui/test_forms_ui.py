from playwright.sync_api import Page, expect


def test_contact_form_fields(app_base_url: str, page: Page) -> None:
    page.goto(f"{app_base_url}/kontakt", wait_until="domcontentloaded")
    expect(page.locator("#contact-form")).to_be_visible()
    expect(page.locator("#cf-name")).to_be_visible()
    expect(page.locator("#cf-email")).to_be_visible()
    expect(page.locator("#cf-subject")).to_be_visible()
    expect(page.locator("#cf-message")).to_be_visible()
    expect(page.locator("#cf-submit")).to_be_visible()


def test_login_forms_exist(app_base_url: str, page: Page) -> None:
    page.goto(f"{app_base_url}/login", wait_until="domcontentloaded")
    expect(page.locator("#login-form")).to_be_visible()
    expect(page.locator("#register-form")).to_have_count(1)
    expect(page.locator("#forgot-password-form")).to_have_count(1)
    expect(page.locator("#profile-form")).to_have_count(1)


def test_cookie_settings_toggle_exists(app_base_url: str, page: Page) -> None:
    page.goto(f"{app_base_url}/cookie-einstellungen", wait_until="domcontentloaded")
    toggles = page.locator("input[type='checkbox']")
    assert toggles.count() >= 1
    expect(toggles.first).to_be_visible()
