"""Öffentliche Suche: keine vergangenen oder ausgebuchten Slots."""

import os
import tempfile
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")

import app as app_module
from models import Base, Booking, Provider, Slot


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


@pytest.fixture(scope="module")
def seeded_past_and_future():
    with Session(app_module.engine) as s:
        provider = Provider(
            email="past-future@example.com",
            pw_hash="test",
            company_name="Zeit GmbH",
            branch="Friseur",
            street="Weg 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        s.add(provider)
        s.flush()

        now = app_module._now()
        past_start = app_module._to_db_utc_naive(now - timedelta(days=1))
        past_end = past_start + timedelta(hours=1)
        future_start = app_module._to_db_utc_naive(now + timedelta(days=2))
        future_end = future_start + timedelta(hours=1)

        slot_past = Slot(
            provider_id=provider.id,
            title="Vergangen",
            category="Friseur",
            start_at=past_start,
            end_at=past_end,
            city="Teststadt",
            zip="12345",
            capacity=1,
            status="PUBLISHED",
        )
        slot_future = Slot(
            provider_id=provider.id,
            title="Zukunft frei",
            category="Friseur",
            start_at=future_start,
            end_at=future_end,
            city="Teststadt",
            zip="12345",
            capacity=1,
            status="PUBLISHED",
        )
        s.add_all([slot_past, slot_future])
        s.commit()
        return str(slot_past.id), str(slot_future.id)


def test_public_slots_excludes_past_start(test_client, seeded_past_and_future):
    past_id, future_id = seeded_past_and_future
    r = test_client.get("/public/slots?location=Teststadt")
    assert r.status_code == 200
    data = r.get_json() or []
    ids = {item["id"] for item in data}
    assert past_id not in ids
    assert future_id in ids


def test_public_slots_day_from_in_past_still_clamps_to_now(test_client, seeded_past_and_future):
    past_id, future_id = seeded_past_and_future
    past_day = (app_module._now() - timedelta(days=5)).strftime("%Y-%m-%d")
    r = test_client.get(f"/public/slots?day_from={past_day}&location=Teststadt")
    assert r.status_code == 200
    data = r.get_json() or []
    ids = {item["id"] for item in data}
    assert past_id not in ids
    assert future_id in ids
