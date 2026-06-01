"""Tests für die Profi-Gates (Profi-/Business-exklusive Funktionen).

Geprüft wird, dass ohne aktives Profi-/Business-Paket die Endpunkte
- Slot duplizieren/kopieren
- Slot archivieren
- CSV-Export
- Kalender-Sync (ICS-Feed)
- Anzahlungen (deposit_cents)
abgelehnt werden, und dass sie mit Profi-Paket funktionieren.

Alle Gate-Prüfungen laufen, bevor PostgreSQL-spezifisches SQL erreicht wird,
daher sind diese Tests auch auf SQLite lauffähig.
"""
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
from models import Base, Provider, Slot


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _create_provider(plan: str | None = None) -> str:
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
            plan=plan,
            plan_valid_until=(date.today() + timedelta(days=30)) if plan else None,
        )
        s.add(p)
        s.commit()
        return p.id


def _create_slot(provider_id: str, status: str = "DRAFT") -> str:
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
            capacity=1,
            status=status,
        )
        s.add(slot)
        s.commit()
        return slot.id


# ----------------------------------------------------------------------
# Ohne Profi-Paket -> abgelehnt
# ----------------------------------------------------------------------
def test_duplicate_requires_pro(test_client):
    pid = _create_provider(plan=None)
    slot_id = _create_slot(pid)
    res = test_client.post(f"/slots/{slot_id}/duplicate", headers=_auth_headers(pid))
    assert res.status_code == 403
    assert res.get_json()["error"] == "plan_required"


def test_archive_requires_pro(test_client):
    pid = _create_provider(plan=None)
    slot_id = _create_slot(pid)
    res = test_client.post(f"/slots/{slot_id}/archive", headers=_auth_headers(pid))
    assert res.status_code == 403
    assert res.get_json()["error"] == "plan_required"


def test_export_requires_pro(test_client):
    pid = _create_provider(plan=None)
    res = test_client.get("/slots/export", headers=_auth_headers(pid))
    assert res.status_code == 403
    assert res.get_json()["error"] == "plan_required"


def test_deposit_on_create_requires_pro(test_client):
    pid = _create_provider(plan=None)
    now = app_module._now()
    start = (now + timedelta(days=2))
    payload = {
        "title": "Mit Anzahlung",
        "category": "Friseur",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=1)).isoformat(),
        "location": "Teststrasse 1, 12345 Teststadt",
        "capacity": 1,
        "deposit_cents": 1000,
    }
    res = test_client.post("/slots", json=payload, headers=_auth_headers(pid))
    assert res.status_code == 400
    assert res.get_json()["error"] == "profi_plan_required"


def test_calendar_ics_requires_pro(test_client):
    pid = _create_provider(plan=None)
    token = app_module._provider_calendar_token(str(pid))
    res = test_client.get(f"/public/provider/{pid}/calendar.ics?token={token}")
    assert res.status_code == 403
    assert res.get_json()["error"] == "plan_required"


def test_me_has_no_calendar_url_for_basic(test_client):
    pid = _create_provider(plan=None)
    res = test_client.get("/me", headers=_auth_headers(pid))
    assert res.status_code == 200
    assert res.get_json().get("calendar_ics_url") is None


# ----------------------------------------------------------------------
# Mit Profi-Paket -> erlaubt
# ----------------------------------------------------------------------
def test_pro_can_duplicate(test_client):
    pid = _create_provider(plan="profi")
    slot_id = _create_slot(pid)
    res = test_client.post(f"/slots/{slot_id}/duplicate", headers=_auth_headers(pid))
    assert res.status_code == 201
    assert "id" in res.get_json()


def test_pro_can_archive(test_client):
    pid = _create_provider(plan="profi")
    slot_id = _create_slot(pid)
    res = test_client.post(f"/slots/{slot_id}/archive", headers=_auth_headers(pid))
    assert res.status_code == 200
    assert res.get_json().get("archived") is True


def test_pro_can_export(test_client):
    pid = _create_provider(plan="profi")
    _create_slot(pid)
    res = test_client.get("/slots/export", headers=_auth_headers(pid))
    assert res.status_code == 200


def test_pro_has_calendar_url(test_client):
    pid = _create_provider(plan="profi")
    res = test_client.get("/me", headers=_auth_headers(pid))
    assert res.status_code == 200
    url = res.get_json().get("calendar_ics_url")
    assert url and "/calendar.ics" in url
