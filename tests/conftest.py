import os

import pytest


def _get_base_url() -> str:
    return os.getenv("BASE_URL", "https://testsystem-terminmarktplatz-de.onrender.com").rstrip("/")


@pytest.fixture(scope="session")
def app_base_url() -> str:
    return _get_base_url()
