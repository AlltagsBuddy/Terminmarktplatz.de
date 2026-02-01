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


def _seed_confirmed_booking() -> tuple[str, str]:
    with Session(app_module.engine) as s:
        provider = Provider(
            email="ics@example.com",
            pw_hash="x",
            company_name="ICS GmbH",
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
            title="Termin ICS",
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
            status="confirmed",
        )
        s.add(booking)
        s.commit()
        return str(booking.id), str(slot.id)


def test_booking_calendar_requires_valid_token(test_client):
    booking_id, _ = _seed_confirmed_booking()
    r = test_client.get(f"/public/booking/{booking_id}/calendar.ics?token=invalid")
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_token"


def test_booking_calendar_returns_ics(test_client):
    booking_id, _ = _seed_confirmed_booking()
    token = app_module._booking_token(booking_id)
    r = test_client.get(f"/public/booking/{booking_id}/calendar.ics?token={token}")
    assert r.status_code == 200
    assert r.headers.get("Content-Type", "").startswith("text/calendar")
    body = r.get_data(as_text=True)
    assert "BEGIN:VCALENDAR" in body
    assert "SUMMARY:" in body
