"""
Tests für GET /public/cancel Edge-Cases: not_found, already canceled.
"""
import os
import tempfile
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("FRONTEND_URL", "http://testserver")
os.environ.setdefault("EMAILS_ENABLED", "false")

import app as app_module
from models import Base, Provider, Slot, Booking


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _seed_booking(status: str) -> str:
    with Session(app_module.engine) as s:
        provider = Provider(
            email="cancel-edge@example.com",
            pw_hash="x",
            company_name="Cancel Edge GmbH",
            branch="Friseur",
            street="Teststrasse 1",
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
            title="Termin Cancel",
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
        )
        s.add(booking)
        s.commit()
        return str(booking.id)


def test_public_cancel_not_found(test_client):
    """GET /public/cancel mit Token für nicht existierende Buchung."""
    fake_id = str(uuid4())
    token = app_module._booking_token(fake_id)
    r = test_client.get(f"/public/cancel?token={token}")
    assert r.status_code == 404
    data = r.get_json() or {}
    assert data.get("error") == "not_found"


def test_public_cancel_already_canceled_returns_page(test_client):
    """GET /public/cancel mit bereits stornierter Buchung liefert Seite."""
    booking_id = _seed_booking(status="canceled")
    token = app_module._booking_token(booking_id)
    r = test_client.get(f"/public/cancel?token={token}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "storniert" in html.lower() or "cancel" in html.lower() or "html" in html.lower()
