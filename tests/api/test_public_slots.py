import os
import tempfile
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session


_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")

import app as app_module
from models import Base, Provider, Slot, Booking


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


@pytest.fixture(scope="module")
def seeded_data():
    with Session(app_module.engine) as s:
        provider = Provider(
            email="public-slots@example.com",
            pw_hash="test",
            company_name="Public GmbH",
            branch="Friseur",
            street="Teststrasse",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        provider2 = Provider(
            email="public-slots-2@example.com",
            pw_hash="test",
            company_name="Public 2 GmbH",
            branch="Kosmetik",
            street="Nebenweg",
            zip="99999",
            city="Anderstadt",
            phone="1234567",
            status="approved",
        )
        s.add_all([provider, provider2])
        s.flush()

        now = app_module._now()
        start1 = app_module._to_db_utc_naive(now + timedelta(days=2))
        end1 = start1 + timedelta(hours=1)
        start2 = app_module._to_db_utc_naive(now + timedelta(days=3))
        end2 = start2 + timedelta(hours=1)

        slot1 = Slot(
            provider_id=provider.id,
            title="Termin A",
            category="Friseur",
            start_at=start1,
            end_at=end1,
            location="Teststrasse 1, 12345 Teststadt",
            city="Teststadt",
            zip="12345",
            capacity=1,
            status="PUBLISHED",
        )
        slot2 = Slot(
            provider_id=provider2.id,
            title="Termin B",
            category="Kosmetik",
            start_at=start2,
            end_at=end2,
            location="Nebenweg 2, 99999 Anderstadt",
            city="Anderstadt",
            zip="99999",
            capacity=1,
            status="PUBLISHED",
        )
        s.add_all([slot1, slot2])
        s.flush()

        booking = Booking(
            slot_id=slot1.id,
            provider_id=provider.id,
            customer_name="Max",
            customer_email="max@example.com",
            status="confirmed",
        )
        s.add(booking)
        s.commit()

        return slot1.id, slot2.id


def test_public_slots_filter_city(test_client, seeded_data):
    r = test_client.get("/public/slots?location=Teststadt&include_full=1")
    assert r.status_code == 200
    data = r.get_json()
    assert all(item["city"] == "Teststadt" for item in data)


def test_public_slots_category_filter(test_client, seeded_data):
    r = test_client.get("/public/slots?category=Kosmetik&include_full=1")
    assert r.status_code == 200
    data = r.get_json()
    assert all(item["category"] == "Kosmetik" for item in data)


def test_public_slots_exclude_full_by_default(test_client, seeded_data):
    r = test_client.get("/public/slots")
    assert r.status_code == 200
    data = r.get_json()
    # Slot1 ist voll (capacity=1 und 1 booking) und sollte fehlen
    assert all(item["title"] != "Termin A" for item in data)


def test_public_slots_radius_filter(test_client, seeded_data):
    slot1_id, slot2_id = seeded_data
    with Session(app_module.engine) as s:
        s.execute(
            text(
                "INSERT INTO geocode_cache(key, lat, lon) VALUES(:k,:lat,:lon)"
                " ON CONFLICT (key) DO UPDATE SET lat=EXCLUDED.lat, lon=EXCLUDED.lon"
            ),
            {"k": "zip:12345", "lat": 50.0, "lon": 10.0},
        )
        s.execute(
            text(
                "INSERT INTO geocode_cache(key, lat, lon) VALUES(:k,:lat,:lon)"
                " ON CONFLICT (key) DO UPDATE SET lat=EXCLUDED.lat, lon=EXCLUDED.lon"
            ),
            {"k": "zip:99999", "lat": 60.0, "lon": 10.0},
        )
        s.commit()

    r = test_client.get("/public/slots?location=12345&radius=50&include_full=1")
    assert r.status_code == 200
    data = r.get_json()
    ids = {item["id"] for item in data}
    assert slot1_id in ids
    assert slot2_id not in ids
