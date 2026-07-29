"""
Regressionstest für den Such-Endpunkt /public/slots.

Hintergrund: Ein Deploy ohne DB-Migration (fehlende Spalte ``slot.external_id``)
führte dazu, dass /public/slots einen Fehler statt einer Slot-Liste lieferte und
damit die komplette Suche ausfiel. Diese Tests sichern den Antwort-Vertrag ab:
- Antwort ist immer eine JSON-Liste (auch bei leerer DB -> []),
- serialisierte Slots enthalten das Feld ``external_id``.
"""
import os
import tempfile
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("BASE_URL", "http://testserver")

import app as app_module
from models import Base, Provider, Slot


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def test_leere_db_liefert_leere_liste(test_client):
    r = test_client.get("/public/slots")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert data == []


def test_slot_serialisierung_enthaelt_external_id(test_client):
    with Session(app_module.engine) as s:
        provider = Provider(
            email="contract@example.com",
            pw_hash="test",
            company_name="Contract GmbH",
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
        start = app_module._to_db_utc_naive(now + timedelta(days=2))
        end = start + timedelta(hours=1)
        s.add(
            Slot(
                provider_id=provider.id,
                title="Vertrag-Termin",
                category="Friseur",
                start_at=start,
                end_at=end,
                location="Teststrasse 1, 12345 Teststadt",
                city="Teststadt",
                zip="12345",
                capacity=1,
                status="PUBLISHED",
                external_id="ext-123",
            )
        )
        s.commit()

    r = test_client.get("/public/slots?include_full=1")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    row = next((x for x in data if x.get("title") == "Vertrag-Termin"), None)
    assert row is not None
    # Das Feld, dessen fehlende DB-Spalte den Such-Ausfall verursacht hat:
    assert "external_id" in row
    assert row["external_id"] == "ext-123"
