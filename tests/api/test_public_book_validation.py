import os
import tempfile
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")

import app as app_module
from models import Base, Provider, Slot, Booking


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _make_provider(session: Session) -> Provider:
    provider = Provider(
        email="book-validate@example.com",
        pw_hash="test",
        company_name="Validate GmbH",
        branch="Friseur",
        street="Teststrasse",
        zip="12345",
        city="Teststadt",
        phone="1234567",
        status="approved",
    )
    session.add(provider)
    session.flush()
    return provider


def _make_slot(session: Session, provider: Provider, *, days=2, status="PUBLISHED") -> Slot:
    start_at = app_module._to_db_utc_naive(app_module._now() + timedelta(days=days))
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
        status=status,
    )
    session.add(slot)
    session.flush()
    return slot


def test_public_book_missing_fields(test_client):
    r = test_client.post("/public/book", json={"slot_id": "x", "email": "max@gmail.com"})
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "missing_fields"


def test_public_book_invalid_email(test_client):
    with Session(app_module.engine) as s:
        provider = _make_provider(s)
        slot = _make_slot(s, provider)
        s.commit()
        slot_id = str(slot.id)

    r = test_client.post(
        "/public/book",
        json={"slot_id": slot_id, "name": "Max", "email": "invalid-email"},
    )
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_email"


def test_public_book_not_found(test_client):
    r = test_client.post(
        "/public/book",
        json={"slot_id": "00000000-0000-0000-0000-000000000000", "name": "Max", "email": "max@gmail.com"},
    )
    assert r.status_code == 404
    data = r.get_json() or {}
    assert data.get("error") == "not_found"


def test_public_book_not_bookable_past(test_client):
    with Session(app_module.engine) as s:
        provider = _make_provider(s)
        slot = _make_slot(s, provider, days=-1)
        s.commit()
        slot_id = str(slot.id)

    r = test_client.post(
        "/public/book",
        json={"slot_id": slot_id, "name": "Max", "email": "max@gmail.com"},
    )
    assert r.status_code == 409
    data = r.get_json() or {}
    assert data.get("error") == "not_bookable"


def test_public_book_slot_full(test_client):
    with Session(app_module.engine) as s:
        provider = _make_provider(s)
        slot = _make_slot(s, provider)
        booking = Booking(
            slot_id=slot.id,
            provider_id=provider.id,
            customer_name="Max",
            customer_email="max@gmail.com",
            status="confirmed",
        )
        s.add(booking)
        s.commit()
        slot_id = str(slot.id)

    r = test_client.post(
        "/public/book",
        json={"slot_id": slot_id, "name": "Max", "email": "max@gmail.com"},
    )
    assert r.status_code == 409
    data = r.get_json() or {}
    assert data.get("error") == "slot_full"
