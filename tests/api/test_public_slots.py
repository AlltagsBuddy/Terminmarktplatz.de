import os
import tempfile
from datetime import timedelta
from urllib.parse import urlencode

import pytest
from sqlalchemy import select, text
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


def _slot_dates():
    with Session(app_module.engine) as s:
        slot1 = s.scalar(select(Slot).where(Slot.title == "Termin A"))
        slot2 = s.scalar(select(Slot).where(Slot.title == "Termin B"))
        return slot1, slot2


def test_public_slots_day_from_to_range(test_client, seeded_data):
    slot1, slot2 = _slot_dates()
    start1_local = app_module._as_utc_aware(slot1.start_at).astimezone(app_module.BERLIN)
    start2_local = app_module._as_utc_aware(slot2.start_at).astimezone(app_module.BERLIN)
    day_from = start1_local.strftime("%Y-%m-%d")
    day_to = start2_local.strftime("%Y-%m-%d")

    r = test_client.get(f"/public/slots?day_from={day_from}&day_to={day_to}&include_full=1")
    assert r.status_code == 200
    data = r.get_json()
    ids = {item["id"] for item in data}
    assert slot1.id in ids
    assert slot2.id in ids


def test_public_slots_day_to_only(test_client, seeded_data):
    slot1, slot2 = _slot_dates()
    start1_local = app_module._as_utc_aware(slot1.start_at).astimezone(app_module.BERLIN)
    day_to = start1_local.strftime("%Y-%m-%d")

    r = test_client.get(f"/public/slots?day_to={day_to}&include_full=1")
    assert r.status_code == 200
    data = r.get_json()
    ids = {item["id"] for item in data}
    assert slot1.id in ids
    assert slot2.id not in ids


def test_public_slots_day_from_only(test_client, seeded_data):
    slot1, slot2 = _slot_dates()
    start2_local = app_module._as_utc_aware(slot2.start_at).astimezone(app_module.BERLIN)
    day_from = start2_local.strftime("%Y-%m-%d")

    r = test_client.get(f"/public/slots?day_from={day_from}&include_full=1")
    assert r.status_code == 200
    data = r.get_json()
    ids = {item["id"] for item in data}
    assert slot1.id not in ids
    assert slot2.id in ids


def test_public_slots_from_to_iso_range(test_client, seeded_data):
    slot1, slot2 = _slot_dates()
    start1_iso = app_module._as_utc_aware(slot1.start_at).isoformat()
    end1_iso = app_module._as_utc_aware(slot1.end_at).isoformat()

    qs = urlencode({"from": start1_iso, "to": end1_iso, "include_full": "1"})
    r = test_client.get(f"/public/slots?{qs}")
    assert r.status_code == 200
    data = r.get_json()
    ids = {item["id"] for item in data}
    assert slot1.id in ids
    assert slot2.id not in ids


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
