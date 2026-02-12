import os
import tempfile
from datetime import timedelta
from decimal import Decimal
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


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _create_provider() -> str:
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"prov-{uuid4()}@example.com",
            pw_hash="test",
            company_name="Test GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        s.add(p)
        s.commit()
        return p.id


def _create_booking(provider_id: str, status: str = "confirmed") -> str:
    with Session(app_module.engine) as s:
        now = app_module._now()
        start = app_module._to_db_utc_naive(now + timedelta(days=2))
        end = start + timedelta(hours=1)
        slot = Slot(
            provider_id=provider_id,
            title="Beratung",
            category="Friseur",
            start_at=start,
            end_at=end,
            location="Teststrasse 1, 12345 Teststadt",
            capacity=1,
            status="PUBLISHED",
        )
        s.add(slot)
        s.flush()

        booking = Booking(
            slot_id=slot.id,
            provider_id=provider_id,
            customer_name="Max",
            customer_email="max@example.com",
            status=status,
            provider_fee_eur=Decimal("2.00"),
        )
        s.add(booking)
        s.commit()
        return booking.id


def test_provider_cancel_booking_not_found(test_client):
    provider_id = _create_provider()
    res = test_client.post(
        f"/provider/bookings/{uuid4()}/cancel",
        headers=_auth_headers(provider_id),
        json={},
    )
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_provider_cancel_booking_forbidden(test_client):
    provider_id = _create_provider()
    other_provider_id = _create_provider()
    booking_id = _create_booking(other_provider_id)
    res = test_client.post(
        f"/provider/bookings/{booking_id}/cancel",
        headers=_auth_headers(provider_id),
        json={},
    )
    assert res.status_code == 403
    assert res.get_json()["error"] == "forbidden"


def test_provider_cancel_booking_success(test_client):
    provider_id = _create_provider()
    booking_id = _create_booking(provider_id, status="confirmed")
    res = test_client.post(
        f"/provider/bookings/{booking_id}/cancel",
        headers=_auth_headers(provider_id),
        json={"reason": "Termin nicht verfügbar"},
    )
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    with Session(app_module.engine) as s:
        b = s.get(Booking, booking_id)
        assert b.status == "canceled"


def test_provider_cancel_booking_already_canceled(test_client):
    provider_id = _create_provider()
    booking_id = _create_booking(provider_id, status="canceled")
    res = test_client.post(
        f"/provider/bookings/{booking_id}/cancel",
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 409
    assert res.get_json()["error"] == "already_canceled"
