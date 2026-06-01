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
import services.billing_invoices as billing_invoices_module
from models import Base, Provider, Slot, Booking, Invoice


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


def _create_confirmed_booking(provider_id: str, fee: str = "2.00") -> str:
    """Bestätigte Buchung (fee_status=open) mit created_at = jetzt."""
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
            customer_name="Max Mustermann",
            customer_email="max@example.com",
            status="confirmed",
            provider_fee_eur=Decimal(fee),
            fee_status="open",
        )
        s.add(booking)
        s.commit()
        return booking.id


def _create_invoice(provider_id: str) -> str:
    with Session(app_module.engine) as s:
        inv = Invoice(
            provider_id=provider_id,
            period_start=date.today().replace(day=1) - timedelta(days=1),
            period_end=date.today(),
            total_eur=Decimal("4.00"),
            status="open",
        )
        s.add(inv)
        s.commit()
        return inv.id


def test_billing_current_requires_auth(test_client):
    res = test_client.get("/provider/billing/current")
    assert res.status_code == 401


def test_billing_current_lists_open_fees(test_client):
    provider_id = _create_provider()
    _create_confirmed_booking(provider_id, fee="2.00")
    _create_confirmed_booking(provider_id, fee="3.00")

    res = test_client.get("/provider/billing/current", headers=_auth_headers(provider_id))
    assert res.status_code == 200
    data = res.get_json()
    assert data["count"] == 2
    assert data["total_eur"] == 5.0
    assert data["open_eur"] == 5.0
    assert data["billed_eur"] == 0.0
    assert len(data["items"]) == 2


def test_billing_current_day_range_excludes_today(test_client):
    """Tagesgenau: ein Zeitraum in der Vergangenheit enthält keine heutige Buchung."""
    provider_id = _create_provider()
    _create_confirmed_booking(provider_id, fee="2.00")

    past = date.today() - timedelta(days=10)
    res = test_client.get(
        f"/provider/billing/current?from={past.isoformat()}&to={past.isoformat()}",
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["count"] == 0
    assert data["total_eur"] == 0.0


def test_billing_current_only_own_bookings(test_client):
    provider_a = _create_provider()
    provider_b = _create_provider()
    _create_confirmed_booking(provider_a, fee="2.00")

    res = test_client.get("/provider/billing/current", headers=_auth_headers(provider_b))
    assert res.status_code == 200
    assert res.get_json()["count"] == 0


def test_provider_invoices_lists_only_own(test_client):
    provider_a = _create_provider()
    provider_b = _create_provider()
    inv_id = _create_invoice(provider_a)

    res_a = test_client.get("/provider/invoices", headers=_auth_headers(provider_a))
    assert res_a.status_code == 200
    assert any(item["id"] == inv_id for item in res_a.get_json())

    res_b = test_client.get("/provider/invoices", headers=_auth_headers(provider_b))
    assert res_b.status_code == 200
    assert all(item["id"] != inv_id for item in res_b.get_json())


def test_provider_invoice_pdf_foreign_is_404(test_client):
    provider_a = _create_provider()
    provider_b = _create_provider()
    inv_id = _create_invoice(provider_a)

    res = test_client.get(
        f"/provider/invoices/{inv_id}/pdf",
        headers=_auth_headers(provider_b),
    )
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_provider_invoice_pdf_reportlab_missing(test_client):
    provider_id = _create_provider()
    inv_id = _create_invoice(provider_id)
    original = billing_invoices_module.REPORTLAB_AVAILABLE
    billing_invoices_module.REPORTLAB_AVAILABLE = False
    try:
        res = test_client.get(
            f"/provider/invoices/{inv_id}/pdf",
            headers=_auth_headers(provider_id),
        )
        assert res.status_code == 503
        assert res.get_json()["error"] == "pdf_generation_not_available"
    finally:
        billing_invoices_module.REPORTLAB_AVAILABLE = original
