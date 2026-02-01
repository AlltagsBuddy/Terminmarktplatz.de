import os
import tempfile
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")

import app as app_module
from models import Base, Provider, Slot, Booking


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _seed_slots():
    with Session(app_module.engine) as s:
        provider = Provider(
            email="slots-more@example.com",
            pw_hash="test",
            company_name="More GmbH",
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
        start_b = app_module._to_db_utc_naive(now + timedelta(days=4))
        end_b = start_b + timedelta(hours=1)

        slot_a = Slot(
            provider_id=provider.id,
            title="Kosmetik Termin",
            description="Makeup und Beauty",
            category="Kosmetik",
            start_at=start_a,
            end_at=end_a,
            location="Hauptweg 1, 12345 Teststadt",
            city="Teststadt",
            zip="12345",
            capacity=1,
            status="PUBLISHED",
        )
        slot_b = Slot(
            provider_id=provider.id,
            title="Friseur Termin",
            description="Haarschnitt",
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
        s.flush()

        booking = Booking(
            slot_id=slot_a.id,
            provider_id=provider.id,
            customer_name="Max",
            customer_email="max@example.com",
            status="confirmed",
        )
        s.add(booking)
        s.commit()

        return str(slot_a.id), str(slot_b.id)


def test_public_slots_q_matches_category(test_client):
    slot_a_id, slot_b_id = _seed_slots()
    r = test_client.get("/public/slots?q=Kosmetik&include_full=1")
    assert r.status_code == 200
    data = r.get_json() or []
    ids = {item["id"] for item in data}
    assert slot_a_id in ids
    assert slot_b_id not in ids


def test_public_slots_q_matches_description(test_client):
    slot_a_id, slot_b_id = _seed_slots()
    r = test_client.get("/public/slots?q=Beauty&include_full=1")
    assert r.status_code == 200
    data = r.get_json() or []
    ids = {item["id"] for item in data}
    assert slot_a_id in ids
    assert slot_b_id not in ids


def test_public_slots_city_param_filters(test_client):
    slot_a_id, slot_b_id = _seed_slots()
    r = test_client.get("/public/slots?city=Anderstadt&include_full=1")
    assert r.status_code == 200
    data = r.get_json() or []
    ids = {item["id"] for item in data}
    assert slot_b_id in ids
    assert slot_a_id not in ids


def test_public_slots_excludes_full_by_default(test_client):
    slot_a_id, slot_b_id = _seed_slots()
    r = test_client.get("/public/slots")
    assert r.status_code == 200
    data = r.get_json() or []
    ids = {item["id"] for item in data}
    assert slot_a_id not in ids
    assert slot_b_id in ids
