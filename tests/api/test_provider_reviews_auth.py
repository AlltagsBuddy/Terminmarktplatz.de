import os
import tempfile

import pytest
from uuid import uuid4
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("EMAILS_ENABLED", "false")

import app as app_module
from models import Base, Provider, Review


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _seed_review() -> tuple[str, str]:
    with Session(app_module.engine) as s:
        uniq = str(uuid4())[:8]
        provider = Provider(
            email=f"auth-review-{uniq}@example.com",
            pw_hash="x",
            company_name="Auth GmbH",
            branch="Friseur",
            street="Teststrasse",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        s.add(provider)
        s.flush()

        review = Review(
            provider_id=provider.id,
            booking_id=str(uuid4()),
            reviewer_name="Max",
            rating=5,
            comment="Top",
        )
        s.add(review)
        s.commit()
        provider_id = str(provider.id)
        review_id = str(review.id)
        return provider_id, review_id


def test_provider_reviews_requires_auth(test_client):
    r = test_client.get("/provider/reviews")
    assert r.status_code == 401


def test_provider_reviews_reply_not_found_for_other_provider(test_client):
    provider_id, review_id = _seed_review()
    other_provider_id = _seed_review()[0]
    r = test_client.post(
        f"/provider/reviews/{review_id}/reply",
        json={"reply_text": "Hi"},
        headers=_auth_headers(other_provider_id),
    )
    assert r.status_code == 404
    data = r.get_json() or {}
    assert data.get("error") == "not_found"
