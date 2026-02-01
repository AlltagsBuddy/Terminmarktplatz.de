import os
import tempfile
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("EMAILS_ENABLED", "false")

import app as app_module
from models import Base, Provider, Slot, Booking


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _seed_booking(*, status: str) -> str:
    with Session(app_module.engine) as s:
        provider = Provider(
            email="confirm@example.com",
            pw_hash="x",
            company_name="Confirm GmbH",
            branch="Friseur",
            street="Teststrasse",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        s.add(provider)
        s.flush()

        start_at = app_module._to_db_utc_naive(app_module._now() + timedelta(days=2))
        end_at = start_at + timedelta(hours=1)
        slot = Slot(
            provider_id=provider.id,
            title="Termin Test",
            category="Friseur",
            start_at=start_at,
            end_at=end_at,
            location="Teststrasse 1, 12345 Teststadt",
            city="Teststadt",
            zip="12345",
            capacity=1,
            status="PUBLISHED",
        )
        s.add(slot)
        s.flush()

        booking = Booking(
            slot_id=slot.id,
            provider_id=provider.id,
            customer_name="Max",
            customer_email="max@example.com",
            status=status,
            created_at=app_module._to_db_utc_naive(app_module._now()),
        )
        s.add(booking)
        s.commit()
        return str(booking.id)


def test_public_confirm_success(test_client):
    booking_id = _seed_booking(status="hold")
    token = app_module._booking_token(booking_id)
    r = test_client.get(f"/public/confirm?token={token}")
    assert r.status_code == 200
    assert "Buchung erfolgreich" in r.get_data(as_text=True)

    with Session(app_module.engine) as s:
        booking = s.get(Booking, booking_id)
        assert booking.status == "confirmed"
        assert booking.confirmed_at is not None


def test_public_confirm_invalid_token(test_client):
    r = test_client.get("/public/confirm?token=invalid")
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_token"


def test_public_cancel_success(test_client):
    booking_id = _seed_booking(status="hold")
    token = app_module._booking_token(booking_id)
    r = test_client.get(f"/public/cancel?token={token}")
    assert r.status_code == 200
    assert "Buchung storniert" in r.get_data(as_text=True)

    with Session(app_module.engine) as s:
        booking = s.get(Booking, booking_id)
        assert booking.status == "canceled"


def test_public_cancel_invalid_token(test_client):
    r = test_client.get("/public/cancel?token=invalid")
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_token"
