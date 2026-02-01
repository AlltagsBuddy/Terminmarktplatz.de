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
from models import Base, Provider, Slot, Review


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _seed_provider_profile() -> int:
    with Session(app_module.engine) as s:
        provider = Provider(
            email="public-profile@example.com",
            pw_hash="x",
            company_name="Public GmbH",
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

        start_at = app_module._to_db_utc_naive(app_module._now() + timedelta(days=2))
        end_at = start_at + timedelta(hours=1)
        slot = Slot(
            provider_id=provider.id,
            title="Termin Profil",
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

        review = Review(
            provider_id=provider.id,
            booking_id=str(uuid4()),
            reviewer_name="Max Mustermann",
            rating=4,
            comment="Gut",
        )
        s.add(review)
        s.commit()
        return provider.provider_number


def test_public_provider_profile_not_found(test_client):
    r = test_client.get("/anbieter/abc")
    assert r.status_code == 404


def test_public_provider_profile_success(test_client):
    provider_number = _seed_provider_profile()
    r = test_client.get(f"/anbieter/{provider_number}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Public GmbH" in html
    assert "Termin Profil" in html
    assert "Bewertungen" in html or "Bewertung" in html
