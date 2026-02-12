"""Tests für GET /public/provider/<provider_id>/calendar.ics."""
import os
import tempfile
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("FRONTEND_URL", "http://testserver")

import app as app_module
from models import Base, Provider, Slot


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _seed_provider_with_slot() -> str:
    with Session(app_module.engine) as s:
        provider = Provider(
            email="calendar@example.com",
            pw_hash="x",
            company_name="Calendar GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        s.add(provider)
        s.flush()

        start_at = app_module._to_db_utc_naive(app_module._now() + timedelta(days=2))
        end_at = start_at + timedelta(hours=1)
        slot = Slot(
            provider_id=provider.id,
            title="Termin Cal",
            category="Friseur",
            start_at=start_at,
            end_at=end_at,
            location="Teststrasse 1, 12345 Teststadt",
            city="Teststadt",
            zip="12345",
            capacity=1,
            status="PUBLISHED",
        )
        s.add(slot)
        s.commit()
        return str(provider.id)


def test_provider_calendar_invalid_token(test_client):
    provider_id = _seed_provider_with_slot()
    r = test_client.get(f"/public/provider/{provider_id}/calendar.ics?token=invalid")
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_token"


def test_provider_calendar_missing_token(test_client):
    provider_id = _seed_provider_with_slot()
    r = test_client.get(f"/public/provider/{provider_id}/calendar.ics")
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_token"


def test_provider_calendar_valid_token_returns_ics(test_client):
    provider_id = _seed_provider_with_slot()
    token = app_module._provider_calendar_token(provider_id)
    r = test_client.get(f"/public/provider/{provider_id}/calendar.ics?token={token}")
    assert r.status_code == 200
    assert r.headers.get("Content-Type", "").startswith("text/calendar")
    body = r.get_data(as_text=True)
    assert "BEGIN:VCALENDAR" in body
    assert "Termin Cal" in body
    assert "END:VCALENDAR" in body


def test_provider_calendar_provider_not_found(test_client):
    fake_id = str(uuid4())
    token = app_module._provider_calendar_token(fake_id)
    r = test_client.get(f"/public/provider/{fake_id}/calendar.ics?token={token}")
    assert r.status_code == 404
    data = r.get_json() or {}
    assert data.get("error") == "not_found"
