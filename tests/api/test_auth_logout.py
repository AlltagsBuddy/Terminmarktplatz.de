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
            email=f"logout-{uuid4()}@example.com",
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


def test_auth_logout_clears_cookies_and_returns_ok(test_client):
    provider_id = _create_provider()
    res = test_client.post("/auth/logout", headers=_auth_headers(provider_id))
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
    # Set-Cookie should clear access/refresh tokens
    set_cookie = res.headers.getlist("Set-Cookie")
    assert any("access_token=" in c and "Max-Age=0" in c for c in set_cookie)
    assert any("refresh_token=" in c and "Max-Age=0" in c for c in set_cookie)
