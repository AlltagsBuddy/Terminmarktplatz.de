import os
import tempfile
from datetime import date, timedelta
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
from models import Base, Provider, PlanPurchase


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _create_provider(plan: str | None = None):
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"plan-{uuid4()}@example.com",
            pw_hash="test",
            company_name="Test GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
            plan=plan,
            plan_valid_until=(date.today() + timedelta(days=30)) if plan else None,
            free_slots_per_month=50 if plan == "starter" else 500 if plan == "profi" else 3,
        )
        s.add(p)
        s.commit()
        return p.id


def test_cancel_plan_requires_active_plan(test_client):
    provider_id = _create_provider("basic")
    res = test_client.post("/me/cancel_plan", headers=_auth_headers(provider_id))
    assert res.status_code == 400
    assert res.get_json()["error"] == "no_active_plan"


def test_cancel_plan_success(test_client):
    provider_id = _create_provider("profi")
    res = test_client.post("/me/cancel_plan", headers=_auth_headers(provider_id))
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    with Session(app_module.engine) as s:
        p = s.get(Provider, provider_id)
        assert p.plan == "basic"
        assert p.plan_valid_until is None
        assert p.free_slots_per_month == 3


def test_paket_buchen_unknown_plan(test_client):
    provider_id = _create_provider(None)
    res = test_client.post(
        "/paket-buchen",
        json={"plan": "unknown"},
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "unknown_plan"


def test_paket_buchen_manual_updates_provider_and_purchase(test_client):
    provider_id = _create_provider(None)
    res = test_client.post(
        "/paket-buchen",
        json={"plan": "starter"},
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["plan"] == "starter"
    assert data["mode"] == "manual_no_stripe"

    with Session(app_module.engine) as s:
        p = s.get(Provider, provider_id)
        assert p.plan == "starter"
        assert p.free_slots_per_month == app_module.PLANS["starter"]["free_slots"]
        purchase = (
            s.query(PlanPurchase)
            .filter(PlanPurchase.provider_id == provider_id, PlanPurchase.plan == "starter")
            .first()
        )
        assert purchase is not None
