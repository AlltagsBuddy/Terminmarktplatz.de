"""Tests für DELETE /slots/<id> — not_found, forbidden."""
import os
import tempfile
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("FRONTEND_URL", "http://testserver")

import app as app_module
from models import Base, Provider, Slot


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
            email=f"slot-del-{uuid4()}@example.com",
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


def _create_slot(provider_id: str) -> str:
    with Session(app_module.engine) as s:
        now = app_module._now()
        start = app_module._to_db_utc_naive(now + timedelta(days=2))
        end = start + timedelta(hours=1)
        slot = Slot(
            provider_id=provider_id,
            title="Test",
            category="Friseur",
            start_at=start,
            end_at=end,
            location="Teststrasse 1",
            capacity=1,
            status="DRAFT",
        )
        s.add(slot)
        s.commit()
        return slot.id


def test_slots_delete_not_found(test_client):
    provider_id = _create_provider()
    res = test_client.delete(
        f"/slots/{uuid4()}",
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_slots_delete_forbidden(test_client):
    provider_id = _create_provider()
    other_id = _create_provider()
    slot_id = _create_slot(other_id)
    res = test_client.delete(
        f"/slots/{slot_id}",
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 404
    data = res.get_json()
    assert data["error"] == "not_found"


def test_slots_delete_success(test_client):
    provider_id = _create_provider()
    slot_id = _create_slot(provider_id)
    res = test_client.delete(
        f"/slots/{slot_id}",
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data.get("ok") is True
    assert data.get("deleted") is True
