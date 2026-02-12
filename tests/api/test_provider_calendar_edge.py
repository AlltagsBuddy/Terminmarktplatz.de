import os
import tempfile
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("EMAILS_ENABLED", "false")

import app as app_module
from models import Base, Provider, Slot


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _seed_provider() -> str:
    with Session(app_module.engine) as s:
        provider = Provider(
            email="calendar-edge@example.com",
            pw_hash="x",
            company_name="Edge GmbH",
            branch="Friseur",
            street="Teststrasse",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
            plan="profi",
            plan_valid_until=date.today() + timedelta(days=30),
        )
        s.add(provider)
        s.commit()
        return str(provider.id)


def test_provider_calendar_not_found(test_client):
    from uuid import uuid4
    provider_id = _seed_provider()
    missing_provider_id = str(uuid4())
    token = app_module._provider_calendar_token(missing_provider_id)
    r = test_client.get(f"/public/provider/{missing_provider_id}/calendar.ics?token={token}")
    assert r.status_code == 404
    data = r.get_json() or {}
    assert data.get("error") == "not_found"


def test_provider_calendar_empty_still_valid_ics(test_client):
    provider_id = _seed_provider()
    token = app_module._provider_calendar_token(provider_id)
    r = test_client.get(f"/public/provider/{provider_id}/calendar.ics?token={token}")
    assert r.status_code == 200
    assert r.headers.get("Content-Type", "").startswith("text/calendar")
    body = r.get_data(as_text=True)
    assert "BEGIN:VCALENDAR" in body
    assert "END:VCALENDAR" in body


def test_provider_calendar_plan_required_for_non_profi(test_client):
    """Provider ohne Profi/Business-Plan erhält 403 plan_required."""
    with Session(app_module.engine) as s:
        provider = Provider(
            email="basic@example.com",
            pw_hash="x",
            company_name="Basic GmbH",
            branch="Friseur",
            street="Teststrasse",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
            plan="starter",  # kein Profi
            plan_valid_until=date.today() + timedelta(days=30),
        )
        s.add(provider)
        s.commit()
        provider_id = str(provider.id)

    token = app_module._provider_calendar_token(provider_id)
    r = test_client.get(f"/public/provider/{provider_id}/calendar.ics?token={token}")
    assert r.status_code == 403
    data = r.get_json() or {}
    assert data.get("error") == "plan_required"


def test_provider_calendar_ignores_past_slots(test_client):
    provider_id = _seed_provider()
    with Session(app_module.engine) as s:
        start_at = app_module._to_db_utc_naive(app_module._now() - timedelta(days=2))
        end_at = start_at + timedelta(hours=1)
        slot = Slot(
            provider_id=provider_id,
            title="Vergangen",
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

    token = app_module._provider_calendar_token(provider_id)
    r = test_client.get(f"/public/provider/{provider_id}/calendar.ics?token={token}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Vergangen" not in body
