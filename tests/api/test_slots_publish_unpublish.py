"""Tests für POST /slots/<id>/publish und /slots/<id>/unpublish.
Publish/Unpublish nutzt PostgreSQL-spezifisches SQL (public.slot, FOR UPDATE, etc.).
Bei SQLite werden die Tests übersprungen.
"""
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
os.environ.setdefault("EMAILS_ENABLED", "false")

import app as app_module
from models import Base, Provider, Slot


pytestmark = pytest.mark.skipif(
    "sqlite" in os.environ.get("DATABASE_URL", "").lower(),
    reason="Publish/Unpublish nutzt PostgreSQL-spezifisches SQL",
)


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
            email=f"pub-{uuid4()}@example.com",
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


def _create_slot(provider_id: str, status: str = "DRAFT") -> str:
    with Session(app_module.engine) as s:
        now = app_module._now()
        start = app_module._to_db_utc_naive(now + timedelta(days=2))
        end = start + timedelta(hours=1)
        slot = Slot(
            provider_id=provider_id,
            title="Test Slot",
            category="Friseur",
            start_at=start,
            end_at=end,
            location="Teststrasse 1, 12345 Teststadt",
            capacity=1,
            status=status,
        )
        s.add(slot)
        s.commit()
        return slot.id


def test_slots_publish_success(test_client):
    provider_id = _create_provider()
    slot_id = _create_slot(provider_id, status="DRAFT")
    res = test_client.post(f"/slots/{slot_id}/publish", headers=_auth_headers(provider_id))
    assert res.status_code == 200
    data = res.get_json()
    assert data.get("ok") is True
    assert "quota" in data


def test_slots_publish_not_found(test_client):
    provider_id = _create_provider()
    res = test_client.post(
        f"/slots/{uuid4()}/publish",
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_slots_publish_not_draft(test_client):
    provider_id = _create_provider()
    slot_id = _create_slot(provider_id, status="PUBLISHED")
    res = test_client.post(f"/slots/{slot_id}/publish", headers=_auth_headers(provider_id))
    assert res.status_code == 409
    assert res.get_json()["error"] == "not_draft"


def test_slots_publish_forbidden_other_provider(test_client):
    provider_id = _create_provider()
    other_id = _create_provider()
    slot_id = _create_slot(other_id, status="DRAFT")
    res = test_client.post(f"/slots/{slot_id}/publish", headers=_auth_headers(provider_id))
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_slots_unpublish_success(test_client):
    provider_id = _create_provider()
    slot_id = _create_slot(provider_id, status="DRAFT")
    test_client.post(f"/slots/{slot_id}/publish", headers=_auth_headers(provider_id))
    res = test_client.post(f"/slots/{slot_id}/unpublish", headers=_auth_headers(provider_id))
    assert res.status_code == 200
    data = res.get_json()
    assert data.get("ok") is True
    assert "quota" in data


def test_slots_unpublish_not_found(test_client):
    provider_id = _create_provider()
    res = test_client.post(
        f"/slots/{uuid4()}/unpublish",
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_slots_unpublish_not_published(test_client):
    provider_id = _create_provider()
    slot_id = _create_slot(provider_id, status="DRAFT")
    res = test_client.post(f"/slots/{slot_id}/unpublish", headers=_auth_headers(provider_id))
    assert res.status_code == 409
    assert res.get_json()["error"] == "not_published"
