import os
import tempfile
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")

import app as app_module
from models import Base, Provider, Slot


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


@pytest.fixture(scope="module")
def seeded_slots():
    with Session(app_module.engine) as s:
        provider = Provider(
            email="book@example.com",
            pw_hash="test",
            company_name="Book GmbH",
            branch="Friseur",
            street="Teststrasse",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        s.add(provider)
        s.flush()

        now = app_module._now()
        start_at = app_module._to_db_utc_naive(now + timedelta(days=2))
        end_at = start_at + timedelta(hours=1)

        slot1 = Slot(
            provider_id=provider.id,
            title="Termin A",
            category="Friseur",
            start_at=start_at,
            end_at=end_at,
            location="Teststrasse 1, 12345 Teststadt",
            city="Teststadt",
            zip="12345",
            capacity=1,
            status="PUBLISHED",
        )
        slot2 = Slot(
            provider_id=provider.id,
            title="Termin B",
            category="Friseur",
            start_at=start_at,
            end_at=end_at,
            location="Teststrasse 2, 12345 Teststadt",
            city="Teststadt",
            zip="12345",
            capacity=1,
            status="PUBLISHED",
        )
        s.add_all([slot1, slot2])
        s.commit()

        return slot1.id, slot2.id


def test_public_book_blocks_same_time_same_email(test_client, seeded_slots):
    slot1_id, slot2_id = seeded_slots
    slot1_id = str(slot1_id)
    slot2_id = str(slot2_id)

    r1 = test_client.post(
        "/public/book",
        json={"slot_id": slot1_id, "name": "Max", "email": "max@gmail.com"},
    )
    assert r1.status_code == 200, f"status={r1.status_code} payload={r1.get_json()}"

    r2 = test_client.post(
        "/public/book",
        json={"slot_id": slot2_id, "name": "Max", "email": "max@gmail.com"},
    )
    assert r2.status_code == 409
    data = r2.get_json() or {}
    assert "nur ein Termin" in (data.get("error") or "")
