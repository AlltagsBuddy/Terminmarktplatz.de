"""
Erweiterte Validierungstests für slots API: PUT bad_datetime, capacity, etc.
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
            email=f"slot-val-{uuid4()}@example.com",
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
            title="Test Slot",
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


def test_slots_put_bad_datetime(test_client):
    """PUT /slots/<id> mit ungültigem Datumsformat liefert bad_datetime."""
    provider_id = _create_provider()
    slot_id = _create_slot(provider_id)
    r = test_client.put(
        f"/slots/{slot_id}",
        json={"start_at": "2026-13-99T10:00:00Z", "end_at": "2026-01-01T11:00:00Z"},
        headers=_auth_headers(provider_id),
    )
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "bad_datetime"


def test_slots_put_bad_datetime_end(test_client):
    """PUT /slots/<id> mit ungültigem end_at Format."""
    provider_id = _create_provider()
    slot_id = _create_slot(provider_id)
    now = app_module._now()
    start = (now + timedelta(days=2)).isoformat()
    r = test_client.put(
        f"/slots/{slot_id}",
        json={"start_at": start, "end_at": "kein-datum"},
        headers=_auth_headers(provider_id),
    )
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "bad_datetime"


def test_slots_put_invalid_status(test_client):
    """PUT /slots/<id> mit ungültigem Status."""
    provider_id = _create_provider()
    slot_id = _create_slot(provider_id)
    r = test_client.put(
        f"/slots/{slot_id}",
        json={"status": "UNGUELTIG"},
        headers=_auth_headers(provider_id),
    )
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_status"


def test_slots_archive_requires_pro_features(test_client):
    """POST /slots/<id>/archive ohne Pro-Plan liefert 403."""
    provider_id = _create_provider()
    slot_id = _create_slot(provider_id)
    r = test_client.post(
        f"/slots/{slot_id}/archive",
        headers=_auth_headers(provider_id),
    )
    assert r.status_code == 403
    data = r.get_json() or {}
    assert data.get("error") == "plan_required"


def test_slots_duplicate_requires_pro_features(test_client):
    """POST /slots/<id>/duplicate ohne Pro-Plan liefert 403."""
    provider_id = _create_provider()
    slot_id = _create_slot(provider_id)
    r = test_client.post(
        f"/slots/{slot_id}/duplicate",
        headers=_auth_headers(provider_id),
    )
    assert r.status_code == 403
    data = r.get_json() or {}
    assert data.get("error") == "plan_required"
