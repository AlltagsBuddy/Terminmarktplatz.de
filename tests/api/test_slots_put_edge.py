"""Tests für PUT /slots/<id> Edge-Cases: not_found, invalid_status_transition."""
import os
import tempfile
from datetime import date, timedelta
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


def _create_provider(plan: str | None = None) -> str:
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"put-edge-{uuid4()}@example.com",
            pw_hash="test",
            company_name="Test GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
            plan=plan,
            plan_valid_until=(date.today() + timedelta(days=30)) if plan else None,
            free_slots_per_month=500 if plan == "profi" else 3,
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


def test_slots_put_not_found(test_client):
    provider_id = _create_provider()
    res = test_client.put(
        f"/slots/{uuid4()}",
        json={"title": "Test"},
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_slots_put_forbidden_other_provider(test_client):
    provider_id = _create_provider()
    other_id = _create_provider()
    slot_id = _create_slot(other_id)
    res = test_client.put(
        f"/slots/{slot_id}",
        json={"title": "Test"},
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_slots_put_invalid_status_transition(test_client):
    provider_id = _create_provider()
    slot_id = _create_slot(provider_id)
    res = test_client.put(
        f"/slots/{slot_id}",
        json={"status": "EXPIRED"},
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data.get("error") == "invalid_status_transition"


def test_slots_put_end_before_start(test_client):
    provider_id = _create_provider()
    slot_id = _create_slot(provider_id)
    now = app_module._now()
    start = (now + timedelta(days=2)).isoformat()
    end = (now + timedelta(days=2) + timedelta(hours=1)).isoformat()
    res = test_client.put(
        f"/slots/{slot_id}",
        json={"start_at": end, "end_at": start},
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "end_before_start"


def test_slots_duplicate_not_found(test_client):
    provider_id = _create_provider(plan="profi")
    res = test_client.post(
        f"/slots/{uuid4()}/duplicate",
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"
