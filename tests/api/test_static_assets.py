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


def test_robots_txt(test_client) -> None:
    response = test_client.get("/robots.txt", follow_redirects=True)
    assert response.status_code == 200
    body = response.get_data(as_text=True).lower()
    assert "user-agent" in body


def test_sitemap_xml(test_client) -> None:
    response = test_client.get("/sitemap.xml")
    assert response.status_code == 200
    body = response.get_data(as_text=True).lower()
    assert "<urlset" in body


def test_main_stylesheet_is_reachable(test_client) -> None:
    response = test_client.get("/static/style.css")
    assert response.status_code == 200
    assert "body" in response.get_data(as_text=True).lower()
