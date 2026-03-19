import os

import pytest


def _get_base_url() -> str:
    # TEST_BASE_URL hat Vorrang (z. B. http://127.0.0.1:5000 für lokale UI-Tests)
    preferred = os.getenv("TEST_BASE_URL") or os.getenv("BASE_URL")
    if preferred:
        return preferred.rstrip("/")
    return "https://testsystem-terminmarktplatz-de.onrender.com"


@pytest.fixture(scope="session")
def app_base_url() -> str:
    return _get_base_url()
