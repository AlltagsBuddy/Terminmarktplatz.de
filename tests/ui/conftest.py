import os
import re
from typing import Any, Callable, Generator

import pytest
from playwright.sync_api import Page, Playwright, sync_playwright


@pytest.fixture(autouse=True)
def screenshot_on_failure(request: pytest.FixtureRequest, page: Page) -> Generator[None, None, None]:
    yield
    report = request.node.stash.get("call_report", None)
    if report and report.failed:
        os.makedirs("test-artifacts", exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", request.node.nodeid)
        page.screenshot(path=os.path.join("test-artifacts", f"{safe_name}.png"), full_page=True)


@pytest.fixture(scope="session")
def playwright() -> Generator[Playwright, None, None]:
    try:
        pw = sync_playwright().start()
    except Exception as e:
        pytest.skip(f"Playwright nicht verfügbar: {e}")
    try:
        yield pw
    finally:
        pw.stop()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Generator[None, None, None]:
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        item.stash["call_report"] = report


@pytest.fixture()
def provider_login(page: Page, app_base_url: str) -> Callable[[], None]:
    email = os.getenv("TEST_PROVIDER_EMAIL")
    password = os.getenv("TEST_PROVIDER_PASSWORD")
    if not email or not password:
        pytest.skip("TEST_PROVIDER_EMAIL/TEST_PROVIDER_PASSWORD not set")

    def _login() -> None:
        page.goto(
            f"{app_base_url}/login.html?tab=login&next=/anbieter-portal.html",
            wait_until="domcontentloaded",
        )
        page.fill("#login-email", email)
        page.fill("#login-password", password)
        page.locator("#login-form button[type='submit']").click()
        page.wait_for_url(re.compile(r"/anbieter-portal\.html"), timeout=20_000)

    return _login
