"""Tests für die externe REST-API ``/api/v1/slots`` (Business, Auth via API-Key).

Auth, Validierung, Gating und Idempotenz laufen DB-unabhängig (SQLite).
Das tatsächliche Anlegen+Veröffentlichen nutzt PostgreSQL-spezifisches SQL
(public.slot, FOR UPDATE, ON CONFLICT) und wird auf SQLite übersprungen.
"""

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
from models import Base, Provider, Slot

_IS_SQLITE = "sqlite" in os.environ.get("DATABASE_URL", "").lower()
pg_only = pytest.mark.skipif(
    _IS_SQLITE,
    reason="Publish-Quota nutzt PostgreSQL-spezifisches SQL",
)


@pytest.fixture(autouse=True)
def _mock_send_mail():
    with patch.object(app_module, "send_mail", return_value=(True, "mocked")):
        yield


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _provider(*, business: bool, api_key: str | None, complete: bool = True) -> str:
    until = date.today() + timedelta(days=60)
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"api-{uuid4()}@example.com",
            pw_hash="test",
            company_name="API GmbH" if complete else None,
            branch="Friseur" if complete else None,
            street="Teststrasse 1" if complete else None,
            zip="12345" if complete else None,
            city="Teststadt" if complete else None,
            phone="030123456" if complete else None,
            status="approved",
            plan="business" if business else "profi",
            plan_valid_until=until,
            free_slots_per_month=500 if business else 100,
            api_key=api_key,
        )
        s.add(p)
        s.commit()
        return str(p.id)


def _api(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def _future_iso(days: int = 2, hours_len: int = 1):
    now = app_module._now()
    start = now + timedelta(days=days)
    end = start + timedelta(hours=hours_len)
    return start.isoformat(), end.isoformat()


def _valid_payload(**overrides):
    start, end = _future_iso()
    payload = {
        "title": "Testtermin",
        "category": "Friseur",
        "start_at": start,
        "end_at": end,
        "location": "Teststrasse 1, 12345 Teststadt",
    }
    payload.update(overrides)
    return payload


def _insert_slot(provider_id: str, *, external_id: str | None = None, status: str = "DRAFT", days: int = 3) -> str:
    now = app_module._now()
    start = app_module._to_db_utc_naive(now + timedelta(days=days))
    end = start + timedelta(hours=1)
    with Session(app_module.engine) as s:
        slot = Slot(
            provider_id=provider_id,
            title="Bestehend",
            category="Friseur",
            start_at=start,
            end_at=end,
            location="Teststrasse 1, 12345 Teststadt",
            capacity=1,
            status=status,
            external_id=external_id,
        )
        s.add(slot)
        s.commit()
        return str(slot.id)


# ----------------------------------------------------------------------
# Authentifizierung
# ----------------------------------------------------------------------
def test_create_requires_api_key(test_client):
    r = test_client.post("/api/v1/slots", json=_valid_payload())
    assert r.status_code == 401
    assert (r.get_json() or {}).get("error") == "missing_api_key"


def test_create_invalid_api_key(test_client):
    _provider(business=True, api_key="business-key-1234567890")
    r = test_client.post(
        "/api/v1/slots", json=_valid_payload(), headers=_api("falscher-key-1234567890")
    )
    assert r.status_code == 401
    assert (r.get_json() or {}).get("error") == "invalid_api_key"


def test_create_business_plan_required(test_client):
    # Profi-Provider mit gesetztem Key -> kein Business -> 403
    _provider(business=False, api_key="profi-key-1234567890")
    r = test_client.post(
        "/api/v1/slots", json=_valid_payload(), headers=_api("profi-key-1234567890")
    )
    assert r.status_code == 403
    assert (r.get_json() or {}).get("error") == "business_plan_required"


def test_bearer_header_also_accepted(test_client):
    _provider(business=True, api_key="business-key-bearer-123456")
    # Ohne Pflichtfelder, aber Auth muss durchgehen -> 400 missing_fields (nicht 401)
    r = test_client.post(
        "/api/v1/slots",
        json={},
        headers={"Authorization": "Bearer business-key-bearer-123456"},
    )
    assert r.status_code == 400
    assert (r.get_json() or {}).get("error") == "missing_fields"


# ----------------------------------------------------------------------
# Validierung
# ----------------------------------------------------------------------
def test_create_missing_fields(test_client):
    _provider(business=True, api_key="k-missing-1234567890")
    r = test_client.post(
        "/api/v1/slots",
        json={"title": "Nur Titel"},
        headers=_api("k-missing-1234567890"),
    )
    assert r.status_code == 400
    body = r.get_json() or {}
    assert body.get("error") == "missing_fields"
    assert "category" in body.get("fields", [])


def test_create_bad_datetime(test_client):
    _provider(business=True, api_key="k-baddate-1234567890")
    r = test_client.post(
        "/api/v1/slots",
        json=_valid_payload(start_at="keindatum", end_at="auch nicht"),
        headers=_api("k-baddate-1234567890"),
    )
    assert r.status_code == 400
    assert (r.get_json() or {}).get("error") == "bad_datetime"


def test_create_end_before_start(test_client):
    _provider(business=True, api_key="k-order-1234567890")
    start, end = _future_iso()
    r = test_client.post(
        "/api/v1/slots",
        json=_valid_payload(start_at=end, end_at=start),
        headers=_api("k-order-1234567890"),
    )
    assert r.status_code == 400
    assert (r.get_json() or {}).get("error") == "end_before_start"


def test_create_start_in_past(test_client):
    _provider(business=True, api_key="k-past-1234567890")
    now = app_module._now()
    start = (now - timedelta(days=1)).isoformat()
    end = (now - timedelta(days=1) + timedelta(hours=1)).isoformat()
    r = test_client.post(
        "/api/v1/slots",
        json=_valid_payload(start_at=start, end_at=end),
        headers=_api("k-past-1234567890"),
    )
    assert r.status_code == 409
    assert (r.get_json() or {}).get("error") == "start_in_past"


def test_create_profile_incomplete(test_client):
    _provider(business=True, api_key="k-incomplete-1234567890", complete=False)
    r = test_client.post(
        "/api/v1/slots", json=_valid_payload(), headers=_api("k-incomplete-1234567890")
    )
    assert r.status_code == 400
    assert (r.get_json() or {}).get("error") == "profile_incomplete"


# ----------------------------------------------------------------------
# Idempotenz (vor dem Publish-Schritt -> auch auf SQLite testbar)
# ----------------------------------------------------------------------
def test_create_idempotent_returns_existing(test_client):
    pid = _provider(business=True, api_key="k-idem-1234567890")
    existing_id = _insert_slot(pid, external_id="ext-42", status="PUBLISHED")
    r = test_client.post(
        "/api/v1/slots",
        json=_valid_payload(external_id="ext-42"),
        headers=_api("k-idem-1234567890"),
    )
    assert r.status_code == 200
    body = r.get_json() or {}
    assert body.get("idempotent") is True
    assert body.get("id") == existing_id
    assert body.get("external_id") == "ext-42"


# ----------------------------------------------------------------------
# PATCH / DELETE (auf DRAFT-Slots ohne Publish -> SQLite-tauglich)
# ----------------------------------------------------------------------
def test_patch_updates_draft_by_internal_id(test_client):
    pid = _provider(business=True, api_key="k-patch-1234567890")
    sid = _insert_slot(pid, status="DRAFT")
    r = test_client.patch(
        f"/api/v1/slots/{sid}",
        json={"title": "Neuer Titel", "notes": "Hinweis"},
        headers=_api("k-patch-1234567890"),
    )
    assert r.status_code == 200, r.get_json()
    body = r.get_json() or {}
    assert body.get("title") == "Neuer Titel"
    assert body.get("notes") == "Hinweis"


def test_patch_by_external_id(test_client):
    pid = _provider(business=True, api_key="k-patchext-1234567890")
    _insert_slot(pid, external_id="ext-patch", status="DRAFT")
    r = test_client.patch(
        "/api/v1/slots/ext-patch",
        json={"title": "Per External-ID geaendert"},
        headers=_api("k-patchext-1234567890"),
    )
    assert r.status_code == 200, r.get_json()
    assert (r.get_json() or {}).get("title") == "Per External-ID geaendert"


def test_patch_unknown_slot_404(test_client):
    _provider(business=True, api_key="k-patch404-1234567890")
    r = test_client.patch(
        "/api/v1/slots/nichtvorhanden",
        json={"title": "x"},
        headers=_api("k-patch404-1234567890"),
    )
    assert r.status_code == 404


def test_delete_future_unbooked_slot(test_client):
    pid = _provider(business=True, api_key="k-del-1234567890")
    sid = _insert_slot(pid, status="DRAFT")
    r = test_client.delete(
        f"/api/v1/slots/{sid}", headers=_api("k-del-1234567890")
    )
    assert r.status_code == 200
    assert (r.get_json() or {}).get("deleted") is True


def test_delete_by_external_id(test_client):
    pid = _provider(business=True, api_key="k-delext-1234567890")
    _insert_slot(pid, external_id="ext-del", status="DRAFT")
    r = test_client.delete(
        "/api/v1/slots/ext-del", headers=_api("k-delext-1234567890")
    )
    assert r.status_code == 200
    assert (r.get_json() or {}).get("deleted") is True


# ----------------------------------------------------------------------
# Anlegen + Veröffentlichen (nur PostgreSQL)
# ----------------------------------------------------------------------
@pg_only
def test_create_and_publish(test_client):
    pid = _provider(business=True, api_key="k-pub-1234567890")
    r = test_client.post(
        "/api/v1/slots",
        json=_valid_payload(external_id="ext-pub-1"),
        headers=_api("k-pub-1234567890"),
    )
    assert r.status_code == 201, r.get_json()
    body = r.get_json() or {}
    assert body.get("status") == app_module.SLOT_STATUS_PUBLISHED
    assert body.get("external_id") == "ext-pub-1"

    # Zweiter Aufruf mit gleicher external_id -> idempotent
    r2 = test_client.post(
        "/api/v1/slots",
        json=_valid_payload(external_id="ext-pub-1"),
        headers=_api("k-pub-1234567890"),
    )
    assert r2.status_code == 200
    assert (r2.get_json() or {}).get("idempotent") is True


@pg_only
def test_create_publish_limit_reached(test_client):
    until = date.today() + timedelta(days=60)
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"api-limit-{uuid4()}@example.com",
            pw_hash="test",
            company_name="Limit GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="030123456",
            status="approved",
            plan="business",
            plan_valid_until=until,
            free_slots_per_month=1,
            api_key="k-limit-1234567890",
        )
        s.add(p)
        s.commit()

    r1 = test_client.post(
        "/api/v1/slots",
        json=_valid_payload(external_id="lim-1"),
        headers=_api("k-limit-1234567890"),
    )
    assert r1.status_code == 201, r1.get_json()

    r2 = test_client.post(
        "/api/v1/slots",
        json=_valid_payload(external_id="lim-2"),
        headers=_api("k-limit-1234567890"),
    )
    assert r2.status_code == 409
    assert (r2.get_json() or {}).get("error") == "monthly_publish_limit_reached"
