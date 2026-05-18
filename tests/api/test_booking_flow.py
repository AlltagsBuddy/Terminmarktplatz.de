"""End-to-End: Slot anlegen, suchen, buchen, bestätigen, stornieren (SQLite-freundlich)."""

from __future__ import annotations

import os
import tempfile
from datetime import timedelta
from unittest.mock import patch
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
from models import Base, Booking, Provider, Slot

_UNIQUE = uuid4().hex[:12]


@pytest.fixture(autouse=True)
def _mock_send_mail():
    with patch.object(app_module, "send_mail", return_value=(True, "mocked")):
        yield


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _sqlite_publish(slot_id: str) -> None:
    """POST /slots/<id>/publish ist bei SQLite geskippt — Slot für Tests veröffentlichen."""
    with Session(app_module.engine) as s:
        slot = s.get(Slot, slot_id)
        assert slot is not None
        slot.status = app_module.SLOT_STATUS_PUBLISHED
        s.commit()


def test_full_booking_flow_create_search_book_confirm_cancel(test_client):
    provider_email = f"flow-{_UNIQUE}@example.com"
    with Session(app_module.engine) as s:
        p = Provider(
            email=provider_email,
            pw_hash="test",
            company_name="Flow Salon",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Flowstadt",
            phone="0123456789",
            status="approved",
        )
        s.add(p)
        s.commit()
        provider_id = str(p.id)

    marker = f"FlowMarker{_UNIQUE}"
    now = app_module._now()
    payload = {
        "title": marker,
        "category": "Friseur",
        "start_at": (now + timedelta(days=3)).isoformat(),
        "end_at": (now + timedelta(days=3, hours=1)).isoformat(),
        "location": "Teststrasse 1, 12345 Flowstadt",
    }
    r_create = test_client.post("/slots", json=payload, headers=_auth_headers(provider_id))
    assert r_create.status_code == 201, r_create.get_data(as_text=True)
    slot_id = str(r_create.get_json()["id"])

    _sqlite_publish(slot_id)

    r_search = test_client.get(f"/public/slots?q={marker}&include_full=1")
    assert r_search.status_code == 200
    items = r_search.get_json() or []
    ids = {str(x["id"]) for x in items}
    assert slot_id in ids

    cust_mail = f"kunde-{_UNIQUE}@example.com"
    r_book = test_client.post(
        "/public/book",
        json={"slot_id": slot_id, "name": "Klara Kunde", "email": cust_mail},
    )
    assert r_book.status_code == 200, r_book.get_json()

    with Session(app_module.engine) as s:
        booking = (
            s.query(Booking)
            .filter(Booking.slot_id == slot_id, Booking.customer_email == cust_mail)
            .order_by(Booking.created_at.desc())
            .first()
        )
        assert booking is not None
        assert booking.status == "hold"
        booking_id = str(booking.id)

    token = app_module._booking_token(booking_id)
    r_confirm = test_client.get(f"/public/confirm?token={token}")
    assert r_confirm.status_code == 200
    assert "Buchung erfolgreich" in r_confirm.get_data(as_text=True)

    with Session(app_module.engine) as s:
        booking = s.get(Booking, booking_id)
        assert booking.status == "confirmed"

    r_cancel = test_client.get(f"/public/cancel?token={token}")
    assert r_cancel.status_code == 200
    assert "storniert" in r_cancel.get_data(as_text=True).lower()

    with Session(app_module.engine) as s:
        booking = s.get(Booking, booking_id)
        assert booking.status == "canceled"
