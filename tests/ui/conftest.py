import os
import re
from typing import Any, Generator

import pytest
from playwright.sync_api import Page


@pytest.fixture(autouse=True)
def screenshot_on_failure(request: pytest.FixtureRequest, page: Page) -> Generator[None, None, None]:
    yield
    report = request.node.stash.get("call_report")
    if report and report.failed:
        os.makedirs("test-artifacts", exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", request.node.nodeid)
        page.screenshot(path=os.path.join("test-artifacts", f"{safe_name}.png"), full_page=True)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Generator[None, None, None]:
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        item.stash["call_report"] = report
