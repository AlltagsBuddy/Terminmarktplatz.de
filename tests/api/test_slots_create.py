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
from models import Base, Provider


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _create_provider(complete: bool = True) -> str:
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"slot-create-{uuid4()}@example.com",
            pw_hash="test",
            company_name="Test GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        if not complete:
            p.street = None
        s.add(p)
        s.commit()
        return p.id


def _valid_slot_payload():
    now = app_module._now()
    start = (now + timedelta(days=2)).isoformat()
    end = (now + timedelta(days=2, hours=1)).isoformat()
    return {
        "title": "Beratung",
        "category": "Friseur",
        "start_at": start,
        "end_at": end,
        "location": "Teststrasse 1, 12345 Teststadt",
    }


def test_slots_create_missing_fields(test_client):
    provider_id = _create_provider()
    res = test_client.post(
        "/slots",
        json={"title": "X", "location": "Y"},
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_fields"


def test_slots_create_bad_datetime(test_client):
    provider_id = _create_provider()
    payload = _valid_slot_payload()
    payload["start_at"] = "invalid"
    res = test_client.post("/slots", json=payload, headers=_auth_headers(provider_id))
    assert res.status_code == 400
    assert res.get_json()["error"] == "bad_datetime"


def test_slots_create_end_before_start(test_client):
    provider_id = _create_provider()
    now = app_module._now()
    payload = _valid_slot_payload()
    payload["start_at"] = (now + timedelta(days=2)).isoformat()
    payload["end_at"] = (now + timedelta(days=2, hours=-1)).isoformat()
    res = test_client.post("/slots", json=payload, headers=_auth_headers(provider_id))
    assert res.status_code == 400
    assert res.get_json()["error"] == "end_before_start"


def test_slots_create_start_in_past(test_client):
    provider_id = _create_provider()
    now = app_module._now()
    payload = _valid_slot_payload()
    payload["start_at"] = (now - timedelta(days=1)).isoformat()
    payload["end_at"] = (now - timedelta(days=1) + timedelta(hours=1)).isoformat()
    res = test_client.post("/slots", json=payload, headers=_auth_headers(provider_id))
    assert res.status_code == 409
    assert res.get_json()["error"] == "start_in_past"


def test_slots_create_missing_location(test_client):
    provider_id = _create_provider()
    payload = _valid_slot_payload()
    payload["location"] = ""
    res = test_client.post("/slots", json=payload, headers=_auth_headers(provider_id))
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_location"


def test_slots_create_bad_capacity(test_client):
    provider_id = _create_provider()
    payload = _valid_slot_payload()
    payload["capacity"] = -1
    res = test_client.post("/slots", json=payload, headers=_auth_headers(provider_id))
    assert res.status_code == 400
    assert res.get_json()["error"] == "bad_capacity"


def test_slots_create_profile_incomplete(test_client):
    provider_id = _create_provider(complete=False)
    res = test_client.post(
        "/slots",
        json=_valid_slot_payload(),
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "profile_incomplete"


def test_slots_create_success(test_client):
    provider_id = _create_provider()
    res = test_client.post(
        "/slots",
        json=_valid_slot_payload(),
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 201
    data = res.get_json()
    assert data["title"] == "Beratung"
    assert data["category"] == "Friseur"
    assert data["status"] == "DRAFT"
    assert "id" in data
