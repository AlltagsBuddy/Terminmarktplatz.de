"""
Tests für geschützte Endpoints: 401 ohne Token.
"""
import os
import tempfile
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("FRONTEND_URL", "http://testserver")

import app as app_module
from models import Base, Provider


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _create_provider() -> str:
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"protected-{uuid4()}@example.com",
            pw_hash="test",
            company_name="Test GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        s.add(p)
        s.commit()
        return p.id


@pytest.mark.parametrize("path", ["/me", "/slots", "/provider/reviews"])
def test_protected_endpoints_return_401_without_token(test_client, path):
    """GET /me, /slots, /provider/reviews liefern 401 ohne Auth."""
    res = test_client.get(path)
    assert res.status_code == 401
    data = res.get_json() or {}
    assert data.get("error") == "unauthorized"


def test_me_post_returns_401_without_token(test_client):
    res = test_client.put("/me", json={"company_name": "X"})
    assert res.status_code == 401
    assert (res.get_json() or {}).get("error") == "unauthorized"


def test_slots_post_returns_401_without_token(test_client):
    res = test_client.post("/slots", json={"title": "X", "category": "Y", "start_at": "2026-01-01T10:00:00Z", "end_at": "2026-01-01T11:00:00Z", "location": "Z"})
    assert res.status_code == 401
    assert (res.get_json() or {}).get("error") == "unauthorized"


def test_auth_logout_returns_401_without_token(test_client):
    res = test_client.post("/auth/logout")
    assert res.status_code == 401
    assert (res.get_json() or {}).get("error") == "unauthorized"
