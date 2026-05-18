"""Business-Tarif: Gate, Mitarbeiter, API-Key, Premium-Suche, Statistiken."""

from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
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

_MARK = uuid4().hex[:10]


@pytest.fixture(autouse=True)
def _mock_send_mail():
    with patch.object(app_module, "send_mail", return_value=(True, "mocked")):
        yield


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _auth(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _provider(*, business: bool) -> str:
    until = date.today() + timedelta(days=60)
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"biz-{_MARK}-{uuid4()}@example.com",
            pw_hash="test",
            company_name="Biz GmbH",
            branch="Friseur",
            street="Strasse 1",
            zip="10115",
            city="Berlin",
            phone="030123456",
            status="approved",
            plan="business" if business else "profi",
            plan_valid_until=until,
            free_slots_per_month=500,
        )
        s.add(p)
        s.commit()
        return str(p.id)


def _published_slot(provider_id: str, *, title_suffix: str, start_delta_days: int = 5) -> str:
    now = app_module._now()
    start = app_module._to_db_utc_naive(now + timedelta(days=start_delta_days))
    end = start + timedelta(hours=1)
    with Session(app_module.engine) as s:
        slot = Slot(
            provider_id=provider_id,
            title=f"Premium{_MARK}{title_suffix}",
            category="Friseur",
            start_at=start,
            end_at=end,
            location="Strasse 1, 10115 Berlin",
            city="Berlin",
            zip="10115",
            capacity=1,
            status=app_module.SLOT_STATUS_PUBLISHED,
        )
        s.add(slot)
        s.commit()
        return str(slot.id)


def test_business_gate_blocks_stats_for_profi(test_client):
    pid = _provider(business=False)
    r = test_client.get("/me/stats", headers=_auth(pid))
    assert r.status_code == 403
    assert (r.get_json() or {}).get("error") == "business_plan_required"


def test_business_employees_limit_and_api_key_and_stats(test_client):
    pid = _provider(business=True)

    for i in range(5):
        r = test_client.post(
            "/me/employees",
            json={"name": f"Mitarbeiter {i}", "email": f"m{i}-{_MARK}@example.com"},
            headers=_auth(pid),
        )
        assert r.status_code == 201, r.get_json()

    r6 = test_client.post(
        "/me/employees",
        json={"name": "Sechs", "email": f"six-{_MARK}@example.com"},
        headers=_auth(pid),
    )
    assert r6.status_code == 400
    assert (r6.get_json() or {}).get("error") == "employee_limit_reached"

    r_key = test_client.get("/me/api-key", headers=_auth(pid))
    assert r_key.status_code == 200
    key1 = (r_key.get_json() or {}).get("api_key")
    assert key1 and len(key1) > 10

    r_regen = test_client.post("/me/api-key/regenerate", headers=_auth(pid))
    assert r_regen.status_code == 200
    key2 = (r_regen.get_json() or {}).get("api_key")
    assert key2 and key2 != key1

    sid = _published_slot(pid, title_suffix="StatSlot")
    with Session(app_module.engine) as s:
        b = Booking(
            slot_id=sid,
            provider_id=pid,
            customer_name="Test",
            customer_email=f"t-{_MARK}@example.com",
            status="confirmed",
        )
        s.add(b)
        s.commit()

    r_stats = test_client.get("/me/stats", headers=_auth(pid))
    assert r_stats.status_code == 200
    body = r_stats.get_json() or {}
    assert "bookings_per_month" in body
    assert "revenue_per_month" in body
    assert "popular_slots" in body
    assert "utilization_last_30d" in body


def test_premium_listing_orders_business_before_non_business(test_client):
    starter_id = _provider(business=False)
    business_id = _provider(business=True)

    _published_slot(starter_id, title_suffix="AAA")
    bid_slot = _published_slot(business_id, title_suffix="ZZZ")

    r = test_client.get(f"/public/slots?q=Premium{_MARK}&include_full=1")
    assert r.status_code == 200
    lst = r.get_json() or []
    assert len(lst) >= 2
    assert lst[0]["id"] == bid_slot
