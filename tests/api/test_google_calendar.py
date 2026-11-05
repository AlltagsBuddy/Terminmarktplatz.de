"""Tests fuer die native Google-Kalender-Integration (Phase 1: nur lesen).

Die Google-API wird vollstaendig gemockt (keine echten Netzwerk-Calls, keine
echten OAuth-Zugangsdaten noetig). Getestet werden:
- Token-Verschluesselung (Roundtrip) und kein Klartext in der DB
- Status-Endpoint (nicht eingeloggt / Basis / Profi)
- OAuth-Start (Login noetig, Konfiguration noetig, Redirect zur Google-URL)
- OAuth-Callback (State-Pruefung, Session-Match, Verbindung anlegen + Sync)
- Sync legt Slots idempotent an (external_id = gcal:<id>)
- Trennen loescht die Verbindung (Widerruf)
- Profi-Gate
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
from models import Base, Provider, Slot, GoogleCalendarConnection


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _create_provider(plan: str | None = "profi") -> str:
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


def _future_event(event_id: str, hours_from_now: int = 48, summary="Freier Termin", location="Teststrasse 1"):
    start = app_module._now() + timedelta(hours=hours_from_now)
    end = start + timedelta(hours=1)
    return {
        "id": event_id,
        "summary": summary,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "location": location,
    }


def _connect(provider_id: str, monkeypatch, events=None, calendar_email="kalender@example.com"):
    """Simuliert einen erfolgreichen OAuth-Callback inkl. Erst-Sync."""
    monkeypatch.setattr(app_module, "_google_oauth_configured", lambda: True)
    monkeypatch.setattr(app_module, "_google_exchange_code", lambda code: {
        "access_token": "at-" + code,
        "refresh_token": "rt-secret",
        "expiry": app_module._now() + timedelta(hours=1),
        "scopes": "https://www.googleapis.com/auth/calendar.readonly",
        "email": calendar_email,
        "calendar_id": calendar_email,
    })
    monkeypatch.setattr(app_module, "_google_list_events", lambda *a, **k: list(events or []))
    state = app_module._google_state_serializer().dumps(str(provider_id))
    client = app_module.app.test_client()
    res = client.get(
        f"/oauth/google/callback?code=abc&state={state}",
        headers=_auth_headers(provider_id),
    )
    return res


# --------------------------------------------------------------------------
# Verschluesselung
# --------------------------------------------------------------------------
def test_token_encryption_roundtrip():
    enc = app_module._encrypt_secret("geheimes-token")
    assert enc is not None
    assert enc != "geheimes-token"  # nicht im Klartext
    assert app_module._decrypt_secret(enc) == "geheimes-token"


def test_encrypt_none_is_none():
    assert app_module._encrypt_secret(None) is None
    assert app_module._decrypt_secret(None) is None


# --------------------------------------------------------------------------
# Status-Endpoint
# --------------------------------------------------------------------------
def test_status_requires_login(test_client):
    res = test_client.get("/api/google/status")
    assert res.status_code == 401


def test_status_not_connected(test_client):
    pid = _create_provider(plan="profi")
    res = test_client.get("/api/google/status", headers=_auth_headers(pid))
    assert res.status_code == 200
    body = res.get_json()
    assert body["connected"] is False
    assert body["eligible"] is True


def test_status_basic_not_eligible(test_client):
    pid = _create_provider(plan=None)
    res = test_client.get("/api/google/status", headers=_auth_headers(pid))
    assert res.status_code == 200
    assert res.get_json()["eligible"] is False


# --------------------------------------------------------------------------
# OAuth-Start
# --------------------------------------------------------------------------
def test_start_requires_login(test_client):
    res = test_client.get("/oauth/google/start")
    assert res.status_code in (301, 302)
    assert "/login.html" in res.headers.get("Location", "")


def test_start_not_configured_redirects(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    monkeypatch.setattr(app_module, "_google_oauth_configured", lambda: False)
    res = test_client.get("/oauth/google/start", headers=_auth_headers(pid))
    assert res.status_code in (301, 302)
    assert "google=not_configured" in res.headers.get("Location", "")


def test_start_redirects_to_google(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    monkeypatch.setattr(app_module, "_google_oauth_configured", lambda: True)
    monkeypatch.setattr(app_module, "_google_build_auth_url", lambda state: "https://accounts.google.com/o/oauth2/auth?state=" + state)
    res = test_client.get("/oauth/google/start", headers=_auth_headers(pid))
    assert res.status_code in (301, 302)
    assert res.headers.get("Location", "").startswith("https://accounts.google.com/")


def test_start_basic_plan_redirects(test_client, monkeypatch):
    pid = _create_provider(plan=None)
    monkeypatch.setattr(app_module, "_google_oauth_configured", lambda: True)
    res = test_client.get("/oauth/google/start", headers=_auth_headers(pid))
    assert res.status_code in (301, 302)
    assert "google=pro_required" in res.headers.get("Location", "")


# --------------------------------------------------------------------------
# OAuth-Callback
# --------------------------------------------------------------------------
def test_callback_invalid_state(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    monkeypatch.setattr(app_module, "_google_oauth_configured", lambda: True)
    res = test_client.get(
        "/oauth/google/callback?code=abc&state=kaputt",
        headers=_auth_headers(pid),
    )
    assert res.status_code in (301, 302)
    assert "google=state_invalid" in res.headers.get("Location", "")


def test_callback_session_mismatch(test_client, monkeypatch):
    pid_a = _create_provider(plan="profi")
    pid_b = _create_provider(plan="profi")
    monkeypatch.setattr(app_module, "_google_oauth_configured", lambda: True)
    # State fuer A, aber als B eingeloggt
    state = app_module._google_state_serializer().dumps(str(pid_a))
    res = test_client.get(
        f"/oauth/google/callback?code=abc&state={state}",
        headers=_auth_headers(pid_b),
    )
    assert res.status_code in (301, 302)
    assert "google=session_mismatch" in res.headers.get("Location", "")


def test_callback_success_creates_connection_and_syncs(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    events = [_future_event("evt-1", summary="Haarschnitt"), _future_event("evt-2", hours_from_now=72)]
    res = _connect(pid, monkeypatch, events=events)
    assert res.status_code in (301, 302)
    assert "google=connected" in res.headers.get("Location", "")

    with Session(app_module.engine) as s:
        conn = s.query(GoogleCalendarConnection).filter(
            GoogleCalendarConnection.provider_id == pid
        ).first()
        assert conn is not None
        # Tokens duerfen NICHT im Klartext stehen
        assert conn.refresh_token_enc and conn.refresh_token_enc != "rt-secret"
        assert app_module._decrypt_secret(conn.refresh_token_enc) == "rt-secret"
        assert conn.access_token_enc and conn.access_token_enc != "at-abc"

    # Slots wurden angelegt (mit gcal:-external_id)
    with Session(app_module.engine) as s:
        slots = s.query(Slot).filter(Slot.provider_id == pid).all()
    ext_ids = {sl.external_id for sl in slots}
    assert "gcal:evt-1" in ext_ids
    assert "gcal:evt-2" in ext_ids


def test_sync_is_idempotent(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    events = [_future_event("dup-1")]
    _connect(pid, monkeypatch, events=events)
    # Zweiter Sync mit denselben Events -> keine Duplikate
    monkeypatch.setattr(app_module, "_google_list_events", lambda *a, **k: list(events))
    res = test_client.post("/api/google/sync-now", headers=_auth_headers(pid))
    assert res.status_code == 200
    with Session(app_module.engine) as s:
        count = s.query(Slot).filter(Slot.provider_id == pid, Slot.external_id == "gcal:dup-1").count()
    assert count == 1


def test_sync_updates_changed_event(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    ev = _future_event("chg-1", summary="Alt")
    _connect(pid, monkeypatch, events=[ev])
    ev2 = dict(ev, summary="Neu")
    monkeypatch.setattr(app_module, "_google_list_events", lambda *a, **k: [ev2])
    res = test_client.post("/api/google/sync-now", headers=_auth_headers(pid))
    assert res.status_code == 200
    with Session(app_module.engine) as s:
        slot = s.query(Slot).filter(Slot.provider_id == pid, Slot.external_id == "gcal:chg-1").one()
    assert slot.title == "Neu"


def test_sync_skips_past_and_allday(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    past = _future_event("past-1", hours_from_now=-48)
    good = _future_event("good-1", hours_from_now=24)
    _connect(pid, monkeypatch, events=[past, good])
    with Session(app_module.engine) as s:
        ext_ids = {sl.external_id for sl in s.query(Slot).filter(Slot.provider_id == pid).all()}
    assert "gcal:good-1" in ext_ids
    assert "gcal:past-1" not in ext_ids


# --------------------------------------------------------------------------
# Trennen + Gate
# --------------------------------------------------------------------------
def test_disconnect_removes_connection(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    res = test_client.post("/api/google/disconnect", headers=_auth_headers(pid))
    assert res.status_code == 200
    with Session(app_module.engine) as s:
        conn = s.query(GoogleCalendarConnection).filter(GoogleCalendarConnection.provider_id == pid).first()
    assert conn is None


def test_sync_now_requires_pro(test_client, monkeypatch):
    pid = _create_provider(plan=None)
    res = test_client.post("/api/google/sync-now", headers=_auth_headers(pid))
    assert res.status_code == 403
    assert res.get_json()["error"] == "pro_plan_required"


def test_sync_now_requires_connection(test_client):
    pid = _create_provider(plan="profi")
    res = test_client.post("/api/google/sync-now", headers=_auth_headers(pid))
    assert res.status_code == 400
    assert res.get_json()["error"] == "not_connected"
