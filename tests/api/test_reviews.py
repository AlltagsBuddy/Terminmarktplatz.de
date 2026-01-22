import os
import tempfile
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("FRONTEND_URL", "http://testserver")

import app as app_module
from models import Base, Provider, Slot, Booking, Review


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _seed_booking(confirmed=True, ended=True):
    with Session(app_module.engine) as s:
        provider = Provider(
            email="review@example.com",
            pw_hash="test",
            company_name="Review GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
            provider_number=123,
        )
        s.add(provider)
        s.flush()

        now = app_module._now()
        if ended:
            start_at = app_module._to_db_utc_naive(now - timedelta(days=2))
        else:
            start_at = app_module._to_db_utc_naive(now + timedelta(days=2))
        end_at = start_at + timedelta(hours=1)

        slot = Slot(
            provider_id=provider.id,
            title="Review Slot",
            category="Friseur",
            start_at=start_at,
            end_at=end_at,
            location="Teststrasse 1, 12345 Teststadt",
            capacity=1,
            status="PUBLISHED",
        )
        s.add(slot)
        s.flush()

        booking = Booking(
            slot_id=slot.id,
            provider_id=provider.id,
            customer_name="Max Mustermann",
            customer_email="max@example.com",
            status="confirmed" if confirmed else "hold",
            confirmed_at=now if confirmed else None,
        )
        s.add(booking)
        s.commit()

        return provider.id, slot.id, booking.id


def test_review_page_requires_past_confirmed_booking(test_client):
    _, _, booking_id = _seed_booking(confirmed=True, ended=False)
    token = app_module._review_token(str(booking_id))
    res = test_client.get(f"/bewertung?token={token}")
    assert res.status_code == 200
    assert b"nach dem Stattfinden" in res.data


def test_review_submit_creates_review_once(test_client):
    _, _, booking_id = _seed_booking(confirmed=True, ended=True)
    token = app_module._review_token(str(booking_id))

    res = test_client.get(f"/bewertung?token={token}")
    assert res.status_code == 200
    assert b"Bewertung absenden" in res.data

    res2 = test_client.post(
        "/bewertung",
        data={"token": token, "rating": "5", "comment": "Super!"},
        follow_redirects=True,
    )
    assert res2.status_code == 200
    assert b"Bewertung wurde gespeichert" in res2.data

    res3 = test_client.post(
        "/bewertung",
        data={"token": token, "rating": "4", "comment": "Noch mal"},
        follow_redirects=True,
    )
    assert res3.status_code == 200
    assert b"bereits gespeichert" in res3.data

    with Session(app_module.engine) as s:
        count = (
            s.execute(select(Review).where(Review.booking_id == str(booking_id)))
            .scalars()
            .all()
        )
        assert len(count) == 1


def test_provider_can_reply_to_review(test_client):
    provider_id, _, booking_id = _seed_booking(confirmed=True, ended=True)
    with Session(app_module.engine) as s:
        review = Review(
            provider_id=provider_id,
            booking_id=str(booking_id),
            reviewer_name="Max Mustermann",
            rating=4,
            comment="Gut",
        )
        s.add(review)
        s.commit()
        review_id = str(review.id)

    res = test_client.post(
        f"/provider/reviews/{review_id}/reply",
        json={"reply_text": "Danke für dein Feedback!"},
        headers=_auth_headers(str(provider_id)),
    )
    assert res.status_code == 200
    data = res.get_json() or {}
    assert data.get("review", {}).get("reply_text") == "Danke für dein Feedback!"


def test_public_profile_shows_reviews(test_client):
    provider_id, _, booking_id = _seed_booking(confirmed=True, ended=True)
    with Session(app_module.engine) as s:
        review = Review(
            provider_id=provider_id,
            booking_id=str(booking_id),
            reviewer_name="Max Mustermann",
            rating=5,
            comment="Top Service",
        )
        s.add(review)
        s.commit()

    res = test_client.get("/anbieter/123")
    assert res.status_code == 200
    assert b"Max M." in res.data
    assert b"Top Service" in res.data
