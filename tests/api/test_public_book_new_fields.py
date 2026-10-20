"""Tests für die neuen Pflichtfelder im Buchungsformular.

Seit 2026-10-20 sind folgende Felder Pflicht:
  first_name, last_name, address, phone, email, booking_confirmed
"""
import os
import tempfile
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")

import app as app_module
from models import Base, Provider, Slot, Booking

# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _mock_send_mail():
    with patch.object(app_module, "send_mail", return_value=(True, "mocked")):
        yield


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _seed_slot() -> str:
    with Session(app_module.engine) as s:
        provider = Provider(
            email="newfields@example.com",
            pw_hash="test",
            company_name="Fields GmbH",
            branch="Friseur",
            street="Teststr. 1",
            zip="12345",
            city="Teststadt",
            phone="030123456",
            status="approved",
        )
        s.add(provider)
        s.flush()
        start_at = app_module._to_db_utc_naive(app_module._now() + timedelta(days=3))
        slot = Slot(
            provider_id=provider.id,
            title="Neues Formular Test",
            category="Friseur",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            location="Teststr. 1, 12345 Teststadt",
            city="Teststadt",
            zip="12345",
            capacity=1,
            status="PUBLISHED",
        )
        s.add(slot)
        s.commit()
        return str(slot.id)


VALID = {
    "first_name": "Maria",
    "last_name": "Mustermann",
    "address": "Hauptstr. 5, 10115 Berlin",
    "phone": "01711234567",
    "email": "maria@example.com",
    "booking_confirmed": True,
}

# ── Pflichtfeld-Tests ────────────────────────────────────────────────────────

@pytest.mark.parametrize("missing_field", [
    "first_name", "last_name", "address", "phone", "email",
])
def test_missing_required_field_returns_400(test_client, missing_field):
    """Jedes fehlende Pflichtfeld → 400 missing_fields."""
    slot_id = _seed_slot()
    payload = {"slot_id": slot_id, **VALID}
    del payload[missing_field]
    r = test_client.post("/public/book", json=payload)
    assert r.status_code == 400, f"Erwartet 400 wenn '{missing_field}' fehlt, got {r.status_code}"
    data = r.get_json() or {}
    assert data.get("error") == "missing_fields"


def test_booking_not_confirmed_returns_400(test_client):
    """booking_confirmed=False → 400 booking_not_confirmed."""
    slot_id = _seed_slot()
    payload = {"slot_id": slot_id, **VALID, "booking_confirmed": False}
    r = test_client.post("/public/book", json=payload)
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "booking_not_confirmed"


def test_booking_confirmed_missing_returns_400(test_client):
    """booking_confirmed fehlt komplett → 400 booking_not_confirmed."""
    slot_id = _seed_slot()
    payload = {"slot_id": slot_id, **VALID}
    del payload["booking_confirmed"]
    r = test_client.post("/public/book", json=payload)
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "booking_not_confirmed"


def test_all_fields_present_creates_booking(test_client):
    """Vollständiges Payload → 200 ok."""
    slot_id = _seed_slot()
    payload = {"slot_id": slot_id, **VALID}
    r = test_client.post("/public/book", json=payload)
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True


def test_customer_data_stored_in_db(test_client):
    """Vorname, Nachname und Adresse werden korrekt in der DB gespeichert."""
    slot_id = _seed_slot()
    payload = {"slot_id": slot_id, **VALID}
    r = test_client.post("/public/book", json=payload)
    assert r.status_code == 200

    with Session(app_module.engine) as s:
        booking = s.query(Booking).filter_by(customer_email=VALID["email"]).first()
        assert booking is not None
        assert booking.customer_first_name == VALID["first_name"]
        assert booking.customer_last_name == VALID["last_name"]
        assert booking.customer_address == VALID["address"]
        assert booking.customer_phone == VALID["phone"]
        assert booking.customer_name == f"{VALID['first_name']} {VALID['last_name']}"
