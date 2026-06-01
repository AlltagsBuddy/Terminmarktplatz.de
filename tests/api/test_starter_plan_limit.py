"""Tests für das Starter-Paket: 50-Slots-Limit und 2-€-Erfolgsprovision.

Die reine Konfiguration/Logik (PLANS, _effective_monthly_limit, Default-Fee)
wird DB-unabhängig getestet. Die tatsächliche Limit-Durchsetzung beim
Veröffentlichen nutzt PostgreSQL-spezifisches SQL (public.slot, FOR UPDATE,
ON CONFLICT) und wird daher auf SQLite übersprungen.
"""
import os
import tempfile
from datetime import timedelta
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
from models import Base, Provider, Slot


# ----------------------------------------------------------------------
# DB-unabhängig: Konfiguration & Limit-Logik
# ----------------------------------------------------------------------
def test_starter_plan_config():
    starter = app_module.PLANS["starter"]
    assert starter["free_slots"] == 50
    assert starter["price_eur"] == Decimal("9.90")
    assert starter["booking_fee_eur"] == Decimal("2.00")


def test_all_plans_have_two_euro_fee():
    for key in ("starter", "profi", "business"):
        assert app_module.PLANS[key]["booking_fee_eur"] == Decimal("2.00")


def test_default_booking_fee_constant():
    assert app_module.DEFAULT_BOOKING_FEE_EUR == Decimal("2.00")


def test_effective_monthly_limit_starter():
    # Starter: genau 50, nicht unbegrenzt
    assert app_module._effective_monthly_limit(50) == (50, False)


def test_effective_monthly_limit_basic_default():
    # Ohne Paket (None/0) -> Basislimit 3, nicht unbegrenzt
    assert app_module._effective_monthly_limit(None) == (3, False)
    assert app_module._effective_monthly_limit(0) == (3, False)


# ----------------------------------------------------------------------
# Durchsetzung beim Veröffentlichen (nur PostgreSQL)
# ----------------------------------------------------------------------
_IS_SQLITE = "sqlite" in os.environ.get("DATABASE_URL", "").lower()

pg_only = pytest.mark.skipif(
    _IS_SQLITE,
    reason="Publish-Quota nutzt PostgreSQL-spezifisches SQL",
)


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _create_starter_provider() -> str:
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"starter-{uuid4()}@example.com",
            pw_hash="test",
            company_name="Starter GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
            plan="starter",
            free_slots_per_month=50,
            booking_fee_eur=Decimal("2.00"),
        )
        s.add(p)
        s.commit()
        return p.id


def _create_draft_slot(provider_id: str, capacity: int) -> str:
    with Session(app_module.engine) as s:
        now = app_module._now()
        start = app_module._to_db_utc_naive(now + timedelta(days=2))
        end = start + timedelta(hours=1)
        slot = Slot(
            provider_id=provider_id,
            title="Test Slot",
            category="Friseur",
            start_at=start,
            end_at=end,
            location="Teststrasse 1, 12345 Teststadt",
            capacity=capacity,
            status="DRAFT",
        )
        s.add(slot)
        s.commit()
        return slot.id


@pg_only
def test_starter_limit_boundary(test_client):
    """Genau 50 Kapazitätsplätze dürfen veröffentlicht werden, der 51. nicht."""
    provider_id = _create_starter_provider()

    # Slot mit Kapazität 50 -> füllt das Monatslimit exakt aus
    slot_full = _create_draft_slot(provider_id, capacity=50)
    res_ok = test_client.post(
        f"/slots/{slot_full}/publish", headers=_auth_headers(provider_id)
    )
    assert res_ok.status_code == 200

    # Ein weiterer Slot (Kapazität 1) -> über dem Limit -> 409
    slot_over = _create_draft_slot(provider_id, capacity=1)
    res_over = test_client.post(
        f"/slots/{slot_over}/publish", headers=_auth_headers(provider_id)
    )
    assert res_over.status_code == 409
    assert res_over.get_json()["error"] == "monthly_publish_limit_reached"
