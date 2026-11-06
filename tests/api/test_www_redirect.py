"""www.terminmarktplatz.de leitet dauerhaft auf terminmarktplatz.de um."""

import os
import tempfile

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")

import pytest

import app as app_module


@pytest.fixture()
def client():
    return app_module.app.test_client()


@pytest.mark.parametrize("path,expected", [
    ("/suche.html", "https://terminmarktplatz.de/suche.html"),
    ("/suche.html?ort=96103&q=", "https://terminmarktplatz.de/suche.html?ort=96103&q="),
    ("/", "https://terminmarktplatz.de/"),
    ("/public/slots", "https://terminmarktplatz.de/public/slots"),
])
def test_www_get_redirects_permanently(client, path, expected):
    r = client.get(path, headers={"Host": "www.terminmarktplatz.de"})
    assert r.status_code == 301
    assert r.headers["Location"] == expected


def test_www_post_is_not_redirected(client):
    """Webhooks/Formulare per POST duerfen nicht umgeleitet werden."""
    r = client.post("/public/book", json={}, headers={"Host": "www.terminmarktplatz.de"})
    assert r.status_code != 301


@pytest.mark.parametrize("host", ["terminmarktplatz.de", "test.terminmarktplatz.de", "localhost"])
def test_other_hosts_not_redirected(client, host):
    r = client.get("/suche.html", headers={"Host": host})
    assert r.status_code != 301
