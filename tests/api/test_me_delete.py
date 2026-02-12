"""Tests für DELETE /me."""
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


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _create_provider() -> str:
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"delete-me-{uuid4()}@example.com",
            pw_hash="test",
            company_name="Lösch GmbH",
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


def test_me_delete_success(test_client):
    provider_id = _create_provider()
    res = test_client.delete("/me", headers=_auth_headers(provider_id))
    assert res.status_code == 200
    data = res.get_json()
    assert data.get("ok") is True
    assert data.get("deleted") is True

    with Session(app_module.engine) as s:
        p = s.get(Provider, provider_id)
        assert p is None


def test_me_delete_requires_auth(test_client):
    res = test_client.delete("/me")
    assert res.status_code == 401
    assert (res.get_json() or {}).get("error") == "unauthorized"
