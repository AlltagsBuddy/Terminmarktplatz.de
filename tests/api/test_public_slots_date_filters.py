import os
import tempfile
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")

import app as app_module
from models import Base, Provider, Slot


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _seed_slots():
    with Session(app_module.engine) as s:
        provider = Provider(
            email="slots-date@example.com",
            pw_hash="test",
            company_name="Date GmbH",
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
        start_a = app_module._to_db_utc_naive(now + timedelta(days=2))
        end_a = start_a + timedelta(hours=1)
        start_b = app_module._to_db_utc_naive(now + timedelta(days=5))
        end_b = start_b + timedelta(hours=1)

        slot_a = Slot(
            provider_id=provider.id,
            title="Termin A",
            category="Friseur",
            start_at=start_a,
            end_at=end_a,
            location="Teststrasse 1, 12345 Teststadt",
            city="Teststadt",
            zip="12345",
            capacity=1,
            status="PUBLISHED",
        )
        slot_b = Slot(
            provider_id=provider.id,
            title="Termin B",
            category="Friseur",
            start_at=start_b,
            end_at=end_b,
            location="Nebenweg 2, 99999 Anderstadt",
            city="Anderstadt",
            zip="99999",
            capacity=1,
            status="PUBLISHED",
        )
        s.add_all([slot_a, slot_b])
        s.commit()
        return slot_a.start_at, slot_b.start_at, str(slot_a.id), str(slot_b.id)


def test_public_slots_day_from_only(test_client):
    start_a, start_b, slot_a_id, slot_b_id = _seed_slots()
    day_from = app_module._as_utc_aware(start_b).astimezone(app_module.BERLIN).strftime("%Y-%m-%d")
    r = test_client.get(f"/public/slots?day_from={day_from}&include_full=1")
    assert r.status_code == 200
    ids = {item["id"] for item in (r.get_json() or [])}
    assert slot_b_id in ids
    assert slot_a_id not in ids


def test_public_slots_day_to_only(test_client):
    start_a, start_b, slot_a_id, slot_b_id = _seed_slots()
    day_to = app_module._as_utc_aware(start_a).astimezone(app_module.BERLIN).strftime("%Y-%m-%d")
    r = test_client.get(f"/public/slots?day_to={day_to}&include_full=1")
    assert r.status_code == 200
    ids = {item["id"] for item in (r.get_json() or [])}
    assert slot_a_id in ids
    assert slot_b_id not in ids


def test_public_slots_from_to_iso(test_client):
    start_a, start_b, slot_a_id, slot_b_id = _seed_slots()
    from_iso = app_module._as_utc_aware(start_a).isoformat()
    to_iso = app_module._as_utc_aware(start_a + timedelta(hours=2)).isoformat()
    r = test_client.get(f"/public/slots?from={from_iso}&to={to_iso}&include_full=1")
    assert r.status_code == 200
    ids = {item["id"] for item in (r.get_json() or [])}
    assert slot_a_id in ids
    assert slot_b_id not in ids
