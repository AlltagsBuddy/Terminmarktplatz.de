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
from models import Base, Provider, Slot, Booking, Review


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _seed_booking(*, confirmed: bool, ended: bool) -> str:
    with Session(app_module.engine) as s:
        provider = Provider(
            email="review@example.com",
            pw_hash="x",
            company_name="Review GmbH",
            branch="Friseur",
            street="Teststrasse",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        s.add(provider)
        s.flush()

        if ended:
            start_at = app_module._to_db_utc_naive(app_module._now() - timedelta(days=2))
            end_at = start_at + timedelta(hours=1)
        else:
            start_at = app_module._to_db_utc_naive(app_module._now() + timedelta(days=2))
            end_at = start_at + timedelta(hours=1)

        slot = Slot(
            provider_id=provider.id,
            title="Termin Bewertung",
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
            status="confirmed" if confirmed else "hold",
        )
        s.add(booking)
        s.commit()
        return str(booking.id)


def test_review_page_invalid_token(test_client):
    r = test_client.get("/bewertung?token=invalid")
    assert r.status_code == 200
    assert "Ungültiger Bewertungslink." in r.get_data(as_text=True)


def test_review_page_requires_confirmed_booking(test_client):
    booking_id = _seed_booking(confirmed=False, ended=True)
    token = app_module._review_token(booking_id)
    r = test_client.get(f"/bewertung?token={token}")
    assert r.status_code == 200
    assert "nicht bestätigt" in r.get_data(as_text=True)


def test_review_page_requires_past_end_time(test_client):
    booking_id = _seed_booking(confirmed=True, ended=False)
    token = app_module._review_token(booking_id)
    r = test_client.get(f"/bewertung?token={token}")
    assert r.status_code == 200
    assert "erst nach dem Stattfinden" in r.get_data(as_text=True)


def test_review_submit_invalid_rating(test_client):
    booking_id = _seed_booking(confirmed=True, ended=True)
    token = app_module._review_token(booking_id)
    r = test_client.post("/bewertung", data={"token": token, "rating": "6"})
    assert r.status_code == 200
    assert "Bewertung von 1 bis 5" in r.get_data(as_text=True)


def test_review_submit_success(test_client):
    booking_id = _seed_booking(confirmed=True, ended=True)
    token = app_module._review_token(booking_id)
    r = test_client.post("/bewertung", data={"token": token, "rating": "5", "comment": "Top"})
    assert r.status_code == 200
    assert "Bewertung wurde gespeichert" in r.get_data(as_text=True)

    with Session(app_module.engine) as s:
        row = s.query(Review).filter_by(booking_id=booking_id).first()
        assert row is not None
        assert row.rating == 5
