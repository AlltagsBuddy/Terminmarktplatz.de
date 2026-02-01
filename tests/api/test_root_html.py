import os
import tempfile

import pytest

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")

import app as app_module


@pytest.fixture(scope="function")
def test_client():
    return app_module.app.test_client()


def test_root_is_reachable(test_client) -> None:
    response = test_client.get("/")
    assert response.status_code == 200
    assert "Terminmarktplatz" in response.get_data(as_text=True)
