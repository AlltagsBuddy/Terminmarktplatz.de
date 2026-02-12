import os
import tempfile
from datetime import datetime, timedelta, timezone, date
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


def _create_provider(is_admin: bool = False) -> str:
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"{'admin' if is_admin else 'prov'}-{uuid4()}@example.com",
            pw_hash="test",
            company_name="Test GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
            is_admin=is_admin,
        )
        s.add(p)
        s.commit()
        return p.id


def _create_booking_in_previous_month(provider_id: str):
    with Session(app_module.engine) as s:
        now = app_module._now()
        if now.month == 1:
            year = now.year - 1
            month = 12
        else:
            year = now.year
            month = now.month - 1
        created_at = datetime(year, month, 2, 10, 0, 0, tzinfo=timezone.utc)
        start = app_module._to_db_utc_naive(created_at + timedelta(days=7))
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
            fee_status="open",
            is_billed=False,
            created_at=app_module._to_db_utc_naive(created_at),
        )
        s.add(booking)
        s.commit()
        return booking.id


def test_admin_run_billing_creates_invoice(test_client):
    admin_id = _create_provider(is_admin=True)
    provider_id = _create_provider(is_admin=False)
    booking_id = _create_booking_in_previous_month(provider_id)

    res = test_client.post("/admin/run_billing", headers=_admin_headers(admin_id))
    assert res.status_code == 200
    data = res.get_json()
    assert data["invoices_created"] >= 1
    assert any(item["provider_id"] == provider_id for item in data["items"])

    with Session(app_module.engine) as s:
        b = s.get(Booking, booking_id)
        assert b.invoice_id is not None
        assert b.fee_status == "invoiced"
        assert b.is_billed is True


def test_admin_invoice_send_email_reportlab_missing(test_client):
    admin_id = _create_provider(is_admin=True)
    provider_id = _create_provider(is_admin=False)
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
        invoice_id = inv.id

    original = app_module.REPORTLAB_AVAILABLE
    app_module.REPORTLAB_AVAILABLE = False
    try:
        res = test_client.post(
            f"/admin/invoices/{invoice_id}/send-email",
            headers=_admin_headers(admin_id),
        )
        assert res.status_code == 500
        data = res.get_json()
        assert data["error"] == "email_send_failed"
    finally:
        app_module.REPORTLAB_AVAILABLE = original
