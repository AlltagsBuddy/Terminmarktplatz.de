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


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


@pytest.fixture(scope="module")
def seeded_slots():
    with Session(app_module.engine) as s:
        provider = Provider(
            email="slots-search@example.com",
            pw_hash="test",
            company_name="Search GmbH",
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
        start_at = app_module._to_db_utc_naive(now + timedelta(days=2))
        end_at = start_at + timedelta(hours=1)

        slot_friseur = Slot(
            provider_id=provider.id,
            title="Haarschnitt Basic",
            description="Schneiden und Styling",
            category="Friseur",
            start_at=start_at,
            end_at=end_at,
            location="Teststrasse 1, 12345 Teststadt",
            city="Teststadt",
            zip="12345",
            capacity=1,
            status="PUBLISHED",
        )
        slot_kosmetik = Slot(
            provider_id=provider.id,
            title="Makeup",
            description="Beauty Paket",
            category="Kosmetik",
            start_at=start_at,
            end_at=end_at,
            location="Nebenweg 2, 54321 Anderstadt",
            city="Anderstadt",
            zip="54321",
            capacity=1,
            status="PUBLISHED",
        )
        slot_city = Slot(
            provider_id=provider.id,
            title="Styling",
            description="Teststadt Spezial",
            category="Friseur",
            start_at=start_at,
            end_at=end_at,
            location="Hauptweg 3, 12345 Teststadt",
            city="Teststadt",
            zip="12345",
            capacity=1,
            status="PUBLISHED",
        )
        s.add_all([slot_friseur, slot_kosmetik, slot_city])
        s.flush()

        # Slot voll machen (für include_full=1)
        booking = Booking(
            slot_id=slot_friseur.id,
            provider_id=provider.id,
            customer_name="Max",
            customer_email="max@example.com",
            status="confirmed",
        )
        s.add(booking)
        s.commit()

        return str(slot_friseur.id), str(slot_kosmetik.id), str(slot_city.id)


def test_public_slots_q_matches_category(test_client, seeded_slots):
    slot_friseur_id, slot_kosmetik_id, _ = seeded_slots
    r = test_client.get("/public/slots?q=friseur&include_full=1")
    assert r.status_code == 200
    data = r.get_json() or []
    ids = {item["id"] for item in data}
    assert slot_friseur_id in ids
    assert slot_kosmetik_id not in ids


def test_public_slots_location_zip_filter(test_client, seeded_slots):
    slot_friseur_id, slot_kosmetik_id, slot_city_id = seeded_slots
    r = test_client.get("/public/slots?location=12345&include_full=1")
    assert r.status_code == 200
    data = r.get_json() or []
    ids = {item["id"] for item in data}
    assert slot_friseur_id in ids
    assert slot_city_id in ids
    assert slot_kosmetik_id not in ids


def test_public_slots_location_city_filter(test_client, seeded_slots):
    slot_friseur_id, slot_kosmetik_id, slot_city_id = seeded_slots
    r = test_client.get("/public/slots?location=Teststadt&include_full=1")
    assert r.status_code == 200
    data = r.get_json() or []
    ids = {item["id"] for item in data}
    assert slot_friseur_id in ids
    assert slot_city_id in ids
    assert slot_kosmetik_id not in ids


def test_public_slots_include_full_shows_full(test_client, seeded_slots):
    slot_friseur_id, _, _ = seeded_slots
    r = test_client.get("/public/slots?include_full=1")
    assert r.status_code == 200
    data = r.get_json() or []
    ids = {item["id"] for item in data}
    assert slot_friseur_id in ids
