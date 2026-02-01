import os
import tempfile
from datetime import timedelta
from decimal import Decimal

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


def _seed_slot() -> tuple[str, str]:
    with Session(app_module.engine) as s:
        provider = Provider(
            email="book-success@example.com",
            pw_hash="test",
            company_name="Book GmbH",
            branch="Friseur",
            street="Teststrasse",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
            booking_fee_eur=Decimal("3.50"),
        )
        s.add(provider)
        s.flush()

        start_at = app_module._to_db_utc_naive(app_module._now() + timedelta(days=2))
        end_at = start_at + timedelta(hours=1)
        slot = Slot(
            provider_id=provider.id,
            title="Termin X",
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
        s.commit()
        return str(slot.id), str(provider.id)


def test_public_book_requires_phone_for_whatsapp(test_client):
    slot_id, _ = _seed_slot()
    r = test_client.post(
        "/public/book",
        json={
            "slot_id": slot_id,
            "name": "Max",
            "email": "max@example.com",
            "reminder_channel": "whatsapp",
        },
    )
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "missing_phone_for_whatsapp"


def test_public_book_success_creates_hold_booking(test_client):
    slot_id, provider_id = _seed_slot()
    r = test_client.post(
        "/public/book",
        json={
            "slot_id": slot_id,
            "name": "Max",
            "email": "max@example.com",
            "phone": "01701234567",
            "reminder_opt_in": True,
            "reminder_channel": "whatsapp",
        },
    )
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True

    with Session(app_module.engine) as s:
        booking = (
            s.query(Booking)
            .filter_by(slot_id=slot_id, provider_id=provider_id)
            .order_by(Booking.created_at.desc())
            .first()
        )
        assert booking is not None
        assert booking.status == "hold"
        assert booking.customer_phone == "01701234567"
        assert booking.reminder_channel == "whatsapp"
        assert booking.reminder_opt_in is True
        assert str(booking.provider_fee_eur) == "3.50"
