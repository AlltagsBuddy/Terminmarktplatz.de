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


def _admin_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, True)
    return {"Authorization": f"Bearer {access}"}


def _create_provider(status: str, is_admin: bool = False) -> str:
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"{status}-{uuid4()}@example.com",
            pw_hash="test",
            company_name="Test GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status=status,
            is_admin=is_admin,
        )
        s.add(p)
        s.commit()
        return p.id


def test_admin_providers_list_by_status(test_client):
    admin_id = _create_provider("approved", is_admin=True)
    pending_id = _create_provider("pending")
    approved_id = _create_provider("approved")

    res_pending = test_client.get("/admin/providers?status=pending", headers=_admin_headers(admin_id))
    assert res_pending.status_code == 200
    data_pending = res_pending.get_json()
    assert any(p["id"] == pending_id for p in data_pending)
    assert all(p["status"] == "pending" for p in data_pending)

    res_approved = test_client.get("/admin/providers?status=approved", headers=_admin_headers(admin_id))
    assert res_approved.status_code == 200
    data_approved = res_approved.get_json()
    assert any(p["id"] == approved_id for p in data_approved)
    assert all(p["status"] == "approved" for p in data_approved)


def test_admin_provider_approve_and_reject(test_client):
    admin_id = _create_provider("approved", is_admin=True)
    pending_id = _create_provider("pending")
    approved_id = _create_provider("approved")

    res_approve = test_client.post(
        f"/admin/providers/{pending_id}/approve",
        headers=_admin_headers(admin_id),
    )
    assert res_approve.status_code == 200
    assert res_approve.get_json()["ok"] is True

    res_reject = test_client.post(
        f"/admin/providers/{approved_id}/reject",
        headers=_admin_headers(admin_id),
    )
    assert res_reject.status_code == 200
    assert res_reject.get_json()["ok"] is True

    with Session(app_module.engine) as s:
        p_pending = s.get(Provider, pending_id)
        p_approved = s.get(Provider, approved_id)
        assert p_pending.status == "approved"
        assert p_approved.status == "rejected"
