import os
import tempfile
from datetime import timedelta

import pytest
from uuid import uuid4
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


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _seed_reviews() -> tuple[str, str, str]:
    with Session(app_module.engine) as s:
        provider = Provider(
            email="reviews@example.com",
            pw_hash="x",
            company_name="Review GmbH",
            branch="Friseur",
            street="Teststrasse",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        other_provider = Provider(
            email="other@example.com",
            pw_hash="x",
            company_name="Other GmbH",
            branch="Friseur",
            street="Nebenweg",
            zip="54321",
            city="Anderstadt",
            phone="7654321",
            status="approved",
        )
        s.add_all([provider, other_provider])
        s.flush()

        start_at = app_module._to_db_utc_naive(app_module._now() - timedelta(days=2))
        end_at = start_at + timedelta(hours=1)
        slot = Slot(
            provider_id=provider.id,
            title="Termin A",
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
        s.flush()

        review = Review(
            provider_id=provider.id,
            booking_id=str(uuid4()),
            reviewer_name="Max",
            rating=5,
            comment="Top",
        )
        s.add(review)

        other_review = Review(
            provider_id=other_provider.id,
            booking_id=str(uuid4()),
            reviewer_name="Eve",
            rating=4,
            comment="Gut",
        )
        s.add(other_review)
        s.commit()
        return str(provider.id), str(review.id), str(other_review.id)


def test_provider_reviews_list_only_own(test_client):
    provider_id, review_id, other_review_id = _seed_reviews()
    r = test_client.get("/provider/reviews", headers=_auth_headers(provider_id))
    assert r.status_code == 200
    data = r.get_json() or []
    ids = {item["id"] for item in data}
    assert review_id in ids
    assert other_review_id not in ids


def test_provider_reviews_reply_too_long(test_client):
    provider_id, review_id, _ = _seed_reviews()
    r = test_client.post(
        f"/provider/reviews/{review_id}/reply",
        json={"reply_text": "x" * 1001},
        headers=_auth_headers(provider_id),
    )
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "reply_too_long"


def test_provider_reviews_reply_success_and_clear(test_client):
    provider_id, review_id, _ = _seed_reviews()
    r = test_client.post(
        f"/provider/reviews/{review_id}/reply",
        json={"reply_text": "Danke!"},
        headers=_auth_headers(provider_id),
    )
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True
    assert data.get("review", {}).get("reply_text") == "Danke!"

    r_clear = test_client.post(
        f"/provider/reviews/{review_id}/reply",
        json={"reply_text": ""},
        headers=_auth_headers(provider_id),
    )
    assert r_clear.status_code == 200
    data_clear = r_clear.get_json() or {}
    assert data_clear.get("review", {}).get("reply_text") is None
