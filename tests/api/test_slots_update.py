import os
import tempfile
from datetime import timedelta

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


@pytest.fixture(scope="module")
def provider_and_slots():
    with Session(app_module.engine) as s:
        provider = Provider(
            email="slot-test@example.com",
            pw_hash="test",
            company_name="Test GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        s.add(provider)
        s.flush()

        now = app_module._now()
        past_start = app_module._to_db_utc_naive(now - timedelta(days=1))
        future_start = app_module._to_db_utc_naive(now + timedelta(days=1))

        slot_past = Slot(
            provider_id=provider.id,
            title="Past Slot",
            category="Friseur",
            start_at=past_start,
            end_at=past_start + timedelta(hours=1),
            location="Teststrasse 1, 12345 Teststadt",
            capacity=1,
            status="DRAFT",
        )
        slot_future = Slot(
            provider_id=provider.id,
            title="Future Slot",
            category="Friseur",
            start_at=future_start,
            end_at=future_start + timedelta(hours=1),
            location="Teststrasse 1, 12345 Teststadt",
            capacity=1,
            status="DRAFT",
        )

        s.add_all([slot_past, slot_future])
        s.commit()

        return provider.id, slot_past.id, slot_future.id


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def test_slots_update_allows_past_slot_without_time_change(test_client, provider_and_slots):
    provider_id, past_slot_id, _ = provider_and_slots
    res = test_client.put(
        f"/slots/{past_slot_id}",
        json={"notes": "Nur Notizen ändern"},
        headers=_auth_headers(provider_id),
    )
    data = res.get_json()
    assert res.status_code == 200
    assert data["ok"] is True


def test_slots_update_rejects_past_start_change(test_client, provider_and_slots):
    provider_id, _, future_slot_id = provider_and_slots
    now = app_module._now()
    past_start = (now - timedelta(days=1)).isoformat()
    past_end = (now - timedelta(days=1) + timedelta(hours=1)).isoformat()
    res = test_client.put(
        f"/slots/{future_slot_id}",
        json={"start_at": past_start, "end_at": past_end},
        headers=_auth_headers(provider_id),
    )
    data = res.get_json()
    assert res.status_code == 409
    assert data["error"] == "start_in_past"
