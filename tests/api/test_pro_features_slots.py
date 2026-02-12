import os
import tempfile
from uuid import uuid4
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("FRONTEND_URL", "http://testserver")

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


def _create_provider(plan: str | None):
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"{plan or 'basic'}-{uuid4()}@example.com",
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
            free_slots_per_month=50 if plan else 3,
        )
        s.add(p)
        s.commit()
        return p.id


def _create_slot(provider_id: str, title: str = "Test Slot"):
    with Session(app_module.engine) as s:
        now = app_module._now()
        start = app_module._to_db_utc_naive(now + timedelta(days=2))
        end = start + timedelta(hours=1)
        slot = Slot(
            provider_id=provider_id,
            title=title,
            category="Friseur",
            start_at=start,
            end_at=end,
            location="Teststrasse 1, 12345 Teststadt",
            capacity=2,
            status="DRAFT",
            description="Beschreibung",
            notes="Intern",
        )
        s.add(slot)
        s.commit()
        return slot.id


def test_pro_features_require_plan(test_client):
    provider_id = _create_provider(None)
    slot_id = _create_slot(provider_id)
    headers = _auth_headers(provider_id)

    res_dup = test_client.post(f"/slots/{slot_id}/duplicate", headers=headers)
    assert res_dup.status_code == 403
    assert res_dup.get_json()["error"] == "plan_required"

    res_arch = test_client.post(f"/slots/{slot_id}/archive", headers=headers)
    assert res_arch.status_code == 403
    assert res_arch.get_json()["error"] == "plan_required"

    res_export = test_client.get("/slots/export", headers=headers)
    assert res_export.status_code == 403
    assert res_export.get_json()["error"] == "plan_required"


def test_pro_can_duplicate_slot(test_client):
    provider_id = _create_provider("profi")
    slot_id = _create_slot(provider_id, title="Original")
    headers = _auth_headers(provider_id)

    res = test_client.post(f"/slots/{slot_id}/duplicate", headers=headers)
    assert res.status_code == 201
    data = res.get_json()
    assert data["id"] != slot_id
    assert data["title"] == "Original"
    assert data["status"] == "DRAFT"
    assert data["archived"] is False


def test_pro_can_archive_slot(test_client):
    provider_id = _create_provider("profi")
    slot_id = _create_slot(provider_id)
    headers = _auth_headers(provider_id)

    res = test_client.post(f"/slots/{slot_id}/archive", headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True


def test_pro_can_export_slots_csv(test_client):
    provider_id = _create_provider("profi")
    active_id = _create_slot(provider_id, title="Aktiv")

    # Archivierten Slot manuell markieren (Export soll standardmäßig nur aktive liefern)
    with Session(app_module.engine) as s:
        slot = s.get(Slot, active_id)
        archived_slot = Slot(
            provider_id=provider_id,
            title="Archiv",
            category="Friseur",
            start_at=slot.start_at,
            end_at=slot.end_at,
            location="Teststrasse 1, 12345 Teststadt",
            capacity=1,
            status="EXPIRED",
            archived=True,
        )
        s.add(archived_slot)
        s.commit()

    headers = _auth_headers(provider_id)
    res = test_client.get("/slots/export", headers=headers)
    assert res.status_code == 200
    assert res.mimetype == "text/csv"

    content = res.data.decode("utf-8")
    lines = [line for line in content.splitlines() if line.strip()]
    assert len(lines) >= 2
    assert lines[0].startswith("id,title,category,start_at,end_at,status,archived,capacity,booked,available")
    assert "Aktiv" in content
    assert "Archiv" not in content

    res_archived = test_client.get("/slots/export?archived=true", headers=headers)
    assert res_archived.status_code == 200
    content_archived = res_archived.data.decode("utf-8")
    assert "Archiv" in content_archived
