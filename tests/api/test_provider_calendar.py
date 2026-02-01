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


def _seed_provider_with_slots() -> str:
    with Session(app_module.engine) as s:
        provider = Provider(
            email="calendar@example.com",
            pw_hash="x",
            company_name="Kalender GmbH",
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
            title="Termin Kalender",
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

        # Booking, damit booked-Anzahl gesetzt ist
        booking = Booking(
            slot_id=slot.id,
            provider_id=provider.id,
            customer_name="Max",
            customer_email="max@example.com",
            status="confirmed",
        )
        s.add(booking)
        s.commit()

        return str(provider.id)


def test_provider_calendar_invalid_token(test_client):
    provider_id = _seed_provider_with_slots()
    r = test_client.get(f"/public/provider/{provider_id}/calendar.ics?token=invalid")
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_token"


def test_provider_calendar_success(test_client):
    provider_id = _seed_provider_with_slots()
    token = app_module._provider_calendar_token(provider_id)
    r = test_client.get(f"/public/provider/{provider_id}/calendar.ics?token={token}")
    assert r.status_code == 200
    assert r.headers.get("Content-Type", "").startswith("text/calendar")
    body = r.get_data(as_text=True)
    assert "BEGIN:VCALENDAR" in body
    assert "SUMMARY:" in body
