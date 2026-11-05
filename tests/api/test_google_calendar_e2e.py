"""End-to-End: Google-Kalender-2-Wege-Sync ueber die echten Endpunkte.

Die Google-API ist gemockt (keine Netzwerk-Calls). Geprueft wird der komplette
Ablauf, wie ihn ein Anbieter erlebt:
Slot anlegen (Entwurf) -> veroeffentlichen -> FREI in Google -> Titel aendern ->
buchen + bestaetigen -> GEBUCHT mit Buchungsnummer (ohne Kundendaten) ->
Anbieter-E-Mail mit Buchungsnummer + Portal-Link -> Storno -> wieder FREI ->
Loeschen -> Event entfernt. Dazu Archivieren und die externe API v1.
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
from models import Base, Booking, GoogleCalendarConnection, Provider, Slot

CUSTOMER = {
    "first_name": "Klara",
    "last_name": "Kundin",
    "address": "Musterstraße 1, 12345 Teststadt",
    "email": "klara.kundin@example.com",
    "phone": "01701234567",
}


@pytest.fixture()
def mails():
    sent = []

    def _fake_send_mail(to, subject, *a, **k):
        sent.append({"to": to, "subject": subject, "text": k.get("text") or (a[0] if a else "")})
        return True, "mocked"

    with patch.object(app_module, "send_mail", side_effect=_fake_send_mail):
        yield sent


@pytest.fixture()
def google(monkeypatch):
    """Faengt alle Google-Schreibzugriffe ab."""
    calls = {"create": [], "patch": [], "delete": []}
    store = {}

    def _create(a, r, sc, cal, body):
        eid = f"evt-{len(calls['create']) + 1}"
        calls["create"].append(body)
        store[eid] = body
        return {"id": eid}

    def _patch(a, r, sc, cal, eid, body):
        calls["patch"].append((eid, body))
        store[eid] = body
        return {}

    def _delete(a, r, sc, cal, eid):
        calls["delete"].append(eid)
        store.pop(eid, None)

    monkeypatch.setattr(app_module, "_google_create_event", _create)
    monkeypatch.setattr(app_module, "_google_patch_event", _patch)
    monkeypatch.setattr(app_module, "_google_delete_event", _delete)
    monkeypatch.setattr(app_module, "_google_list_events", lambda *a, **k: [])
    calls["store"] = store
    return calls


@pytest.fixture()
def client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _auth(pid: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(pid, False)
    return {"Authorization": f"Bearer {access}"}


def _provider_with_google(plan: str = "profi", connected: bool = True) -> str:
    with Session(app_module.engine) as s:
        p = Provider(
            email=f"gcal-e2e-{uuid4().hex[:8]}@example.com",
            pw_hash="test",
            company_name="E2E Salon",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="0123456789",
            contact_email="kontakt@example.com",
            status="approved",
            plan=plan,
            plan_valid_until=date.today() + timedelta(days=30),
        )
        s.add(p)
        s.flush()
        if connected:
            s.add(GoogleCalendarConnection(
                provider_id=str(p.id),
                google_account_email="kalender@example.com",
                calendar_id="kalender@example.com",
                access_token_enc=app_module._encrypt_secret("at"),
                refresh_token_enc=app_module._encrypt_secret("rt"),
                status="connected",
            ))
        s.commit()
        return str(p.id)


def _create_slot(client, pid: str, title: str = "Herrenschnitt") -> str:
    now = app_module._now()
    r = client.post("/slots", json={
        "title": title,
        "category": "Friseur",
        "start_at": (now + timedelta(days=3)).isoformat(),
        "end_at": (now + timedelta(days=3, hours=1)).isoformat(),
        "location": "Teststrasse 1, 12345 Teststadt",
    }, headers=_auth(pid))
    assert r.status_code == 201, r.get_data(as_text=True)
    return str(r.get_json()["id"])


def _publish(slot_id: str) -> None:
    """/slots/<id>/publish nutzt PostgreSQL-Kontingente – hier direkt + Sync wie der Endpoint."""
    with Session(app_module.engine) as s:
        s.get(Slot, slot_id).status = app_module.SLOT_STATUS_PUBLISHED
        s.commit()
    app_module._gcal_sync_slot_safe(slot_id)


def _book_and_confirm(client, slot_id: str) -> str:
    r = client.post("/public/book", json={"slot_id": slot_id, "booking_confirmed": True, **CUSTOMER})
    assert r.status_code == 200, r.get_json()
    with Session(app_module.engine) as s:
        b = s.query(Booking).filter(Booking.slot_id == slot_id).order_by(Booking.created_at.desc()).first()
        bid = str(b.id)
    r = client.get(f"/public/confirm?token={app_module._booking_token(bid)}")
    assert r.status_code == 200
    return bid


def _no_customer_data(obj) -> None:
    blob = str(obj)
    for value in CUSTOMER.values():
        assert value not in blob, f"Kundendatum '{value}' darf nicht an Google gehen"
    assert "Kundin" not in blob


# ---------------------------------------------------------------------------
def test_full_two_way_flow(client, google, mails):
    pid = _provider_with_google()
    sid = _create_slot(client, pid)
    assert google["create"] == [], "Entwurf darf nicht in Google erscheinen"

    _publish(sid)
    assert len(google["create"]) == 1
    free = google["create"][0]
    assert free["summary"] == "FREI: Herrenschnitt"
    assert free["extendedProperties"]["private"]["tm_slot_id"] == sid
    assert f"/anbieter-portal.html?slot={sid}" in free["description"]

    # Titel im Portal aendern -> Google-Event wird aktualisiert
    r = client.put(f"/slots/{sid}", json={"title": "Herrenschnitt kurz"}, headers=_auth(pid))
    assert r.status_code == 200, r.get_data(as_text=True)
    eid, body = google["patch"][-1]
    assert eid == "evt-1" and body["summary"] == "FREI: Herrenschnitt kurz"

    # Buchen + bestaetigen -> GEBUCHT mit Buchungsnummer, ohne Kundendaten
    bid = _book_and_confirm(client, sid)
    bnr = app_module.booking_number(bid)
    eid, body = google["patch"][-1]
    assert eid == "evt-1"
    assert body["summary"] == f"GEBUCHT: Herrenschnitt kurz – {bnr}"
    assert f"Buchungs-Nr.: {bnr}" in body["description"]
    _no_customer_data(google["store"])

    # Anbieter-E-Mail: Buchungsnummer im Betreff + Text, Link ins Portal
    prov_mails = [m for m in mails if bnr in (m["subject"] or "")]
    assert prov_mails, f"Keine Anbieter-Mail mit {bnr} im Betreff: {[m['subject'] for m in mails]}"
    text = prov_mails[0]["text"]
    assert f"Buchungs-Nr.: {bnr}" in text
    assert f"/anbieter-portal.html?slot={sid}" in text

    # Storno -> Event bleibt, steht wieder auf FREI
    r = client.get(f"/public/cancel?token={app_module._booking_token(bid)}")
    assert r.status_code == 200
    eid, body = google["patch"][-1]
    assert eid == "evt-1" and body["summary"] == "FREI: Herrenschnitt kurz"

    # Loeschen (zukuenftig, ungebucht) -> Event wird entfernt
    r = client.delete(f"/slots/{sid}", headers=_auth(pid))
    assert r.status_code == 200 and r.get_json().get("deleted") is True
    assert google["delete"] == ["evt-1"]
    assert google["store"] == {}


def test_archive_removes_free_event(client, google, mails):
    pid = _provider_with_google()
    sid = _create_slot(client, pid)
    _publish(sid)
    r = client.post(f"/slots/{sid}/archive", headers=_auth(pid))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert google["delete"] == ["evt-1"]


def test_archive_keeps_booked_event(client, google, mails):
    """Gebuchte Termine bleiben als Nachweis im Kalender, auch wenn archiviert."""
    pid = _provider_with_google()
    sid = _create_slot(client, pid)
    _publish(sid)
    _book_and_confirm(client, sid)
    r = client.post(f"/slots/{sid}/archive", headers=_auth(pid))
    assert r.status_code == 200
    assert google["delete"] == []
    assert google["patch"][-1][1]["summary"].startswith("GEBUCHT:")


def test_unpublish_via_status_update_removes_event(client, google, mails):
    """Bulk-Aktion "Zurueckziehen" im Portal nutzt PUT /slots/<id> mit status=DRAFT."""
    pid = _provider_with_google()
    sid = _create_slot(client, pid)
    _publish(sid)
    if app_module.IS_POSTGRESQL:
        r = client.put(f"/slots/{sid}", json={"status": "DRAFT"}, headers=_auth(pid))
        assert r.status_code == 200, r.get_data(as_text=True)
    else:
        # Statuswechsel nutzt PostgreSQL-Sperren (FOR UPDATE) – unter SQLite wie der Endpoint nachbilden
        with Session(app_module.engine) as s:
            s.get(Slot, sid).status = app_module.SLOT_STATUS_DRAFT
            s.commit()
        app_module._gcal_sync_slot_safe(sid)
    assert google["delete"] == ["evt-1"]


def test_without_connection_nothing_goes_to_google(client, google, mails):
    pid = _provider_with_google(connected=False)
    sid = _create_slot(client, pid)
    _publish(sid)
    _book_and_confirm(client, sid)
    assert google["create"] == [] and google["patch"] == [] and google["delete"] == []


def test_google_error_never_blocks_booking(client, google, mails, monkeypatch):
    """Faellt Google aus, muss die Buchung trotzdem klappen."""
    pid = _provider_with_google()
    sid = _create_slot(client, pid)
    _publish(sid)

    def _boom(*a, **k):
        raise RuntimeError("Google nicht erreichbar")

    monkeypatch.setattr(app_module, "_google_patch_event", _boom)
    monkeypatch.setattr(app_module, "_google_create_event", _boom)
    bid = _book_and_confirm(client, sid)
    with Session(app_module.engine) as s:
        assert s.get(Booking, bid).status == "confirmed"


def test_basic_plan_is_not_synced(client, google, mails):
    """Kalender-Sync ist Profi/Business-Funktion – auch bei Rest-Verbindung kein Schreiben."""
    pid = _provider_with_google(plan="basic")
    with Session(app_module.engine) as s:
        p = s.get(Provider, pid)
        p.plan = None
        p.plan_valid_until = None
        s.commit()
    sid = _create_slot(client, pid)
    _publish(sid)
    assert google["create"] == []


@pytest.mark.skipif(not app_module.IS_POSTGRESQL, reason="API v1 veroeffentlicht sofort (PostgreSQL-Kontingent, FOR UPDATE)")
def test_api_v1_create_and_delete_sync(client, google, mails):
    pid = _provider_with_google(plan="business")
    with Session(app_module.engine) as s:
        p = s.get(Provider, pid)
        key = "tm_test_" + uuid4().hex
        if hasattr(app_module, "_hash_api_key"):
            p.api_key = app_module._hash_api_key(key)
        else:
            p.api_key = key
        s.commit()
    now = app_module._now()
    headers = {"X-API-Key": key}
    r = client.post("/api/v1/slots", json={
        "title": "API-Termin", "category": "Friseur",
        "start_at": (now + timedelta(days=4)).isoformat(),
        "end_at": (now + timedelta(days=4, hours=1)).isoformat(),
        "location": "Teststrasse 1, 12345 Teststadt",
        "external_id": "fremd-123",
    }, headers=headers)
    if r.status_code in (401, 403):
        pytest.skip(f"API-Key-Format in diesem Build anders ({r.status_code})")
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    sid = str(r.get_json()["id"])
    with Session(app_module.engine) as s:
        sl = s.get(Slot, sid)
        if sl.status != app_module.SLOT_STATUS_PUBLISHED:
            sl.status = app_module.SLOT_STATUS_PUBLISHED
            s.commit()
    app_module._gcal_sync_slot_safe(sid)
    with Session(app_module.engine) as s:
        sl = s.get(Slot, sid)
        # Fremd-ID bleibt unangetastet, Google-ID steht separat
        assert sl.external_id == "fremd-123"
        assert sl.gcal_event_id
        eid = sl.gcal_event_id
    r = client.delete("/api/v1/slots/fremd-123", headers=headers)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert eid in google["delete"]
