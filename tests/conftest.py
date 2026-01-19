import os

import pytest


def _get_base_url() -> str:
    preferred = os.getenv("TEST_BASE_URL") or os.getenv("BASE_URL")
    if preferred:
        preferred = preferred.rstrip("/")
        if not preferred.startswith(("http://127.0.0.1", "http://localhost")):
            return preferred
    return "https://testsystem-terminmarktplatz-de.onrender.com"


@pytest.fixture(scope="session")
def app_base_url() -> str:
    return _get_base_url()
