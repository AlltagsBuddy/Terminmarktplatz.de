import os
import tempfile
from datetime import date, timedelta
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
from models import Base, Provider, Slot, Booking, Invoice


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _admin_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, True)
    return {"Authorization": f"Bearer {access}"}


def _create_provider():
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"admin-{uuid4()}@example.com",
            pw_hash="test",
            company_name="Admin GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
            is_admin=True,
        )
        s.add(p)
        s.commit()
        return p.id


def _create_invoice(provider_id: str):
    with Session(app_module.engine) as s:
        inv = Invoice(
            provider_id=provider_id,
            period_start=date.today() - timedelta(days=30),
            period_end=date.today(),
            total_eur=Decimal("4.00"),
            status="open",
        )
        s.add(inv)
        s.commit()
        return inv.id


def _create_slot_and_booking(provider_id: str, invoice_id: str):
    with Session(app_module.engine) as s:
        now = app_module._now()
        start = app_module._to_db_utc_naive(now + timedelta(days=3))
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
            status="confirmed",
            provider_fee_eur=Decimal("2.00"),
            invoice_id=invoice_id,
            is_billed=True,
        )
        s.add(booking)
        s.commit()
        return slot.id, booking.id


def test_admin_invoices_all_lists_invoices(test_client):
    provider_id = _create_provider()
    inv_id = _create_invoice(provider_id)

    res = test_client.get("/admin/invoices/all", headers=_admin_headers(provider_id))
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    assert any(item["id"] == inv_id for item in data)


def test_admin_invoice_detail_not_found(test_client):
    provider_id = _create_provider()
    res = test_client.get(
        f"/admin/invoices/{uuid4()}",
        headers=_admin_headers(provider_id),
    )
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_admin_invoice_detail_with_bookings(test_client):
    provider_id = _create_provider()
    inv_id = _create_invoice(provider_id)
    _, booking_id = _create_slot_and_booking(provider_id, inv_id)

    res = test_client.get(f"/admin/invoices/{inv_id}", headers=_admin_headers(provider_id))
    assert res.status_code == 200
    data = res.get_json()
    assert data["id"] == inv_id
    assert data["provider_id"] == provider_id
    assert isinstance(data["bookings"], list)
    assert any(b["id"] == booking_id for b in data["bookings"])


def test_admin_invoice_pdf_reportlab_missing(test_client):
    provider_id = _create_provider()
    inv_id = _create_invoice(provider_id)
    original = app_module.REPORTLAB_AVAILABLE
    app_module.REPORTLAB_AVAILABLE = False
    try:
        res = test_client.get(f"/admin/invoices/{inv_id}/pdf", headers=_admin_headers(provider_id))
        assert res.status_code == 503
        data = res.get_json()
        assert data["error"] == "pdf_generation_not_available"
    finally:
        app_module.REPORTLAB_AVAILABLE = original
