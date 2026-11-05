"""Tests fuer die native Google-Kalender-Integration (Lesen + Rueckschreiben).

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
from models import Base, Provider, Slot, Booking, GoogleCalendarConnection


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
    monkeypatch.setattr(app_module, "_google_exchange_code", lambda code, **k: {
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
    monkeypatch.setattr(app_module, "_google_build_auth_url", lambda state, **k: "https://accounts.google.com/o/oauth2/auth?state=" + state)
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


# --------------------------------------------------------------------------
# Phase 2: Rueckschreiben, Doppelbuchung, Kalenderwahl, Widerruf
# --------------------------------------------------------------------------
def _set_booking_status(booking_id, status: str) -> None:
    with Session(app_module.engine) as s:
        s.get(Booking, booking_id).status = status
        s.commit()


def _make_slot_and_booking(provider_id: str, *, external_id=None, title="Haarschnitt"):
    with Session(app_module.engine) as s:
        start_at = app_module._to_db_utc_naive(app_module._now() + timedelta(days=2))
        end_at = start_at + timedelta(hours=1)
        slot = Slot(
            provider_id=provider_id,
            title=title,
            category="Friseur",
            start_at=start_at,
            end_at=end_at,
            location="Teststrasse 1",
            city="Teststadt",
            zip="12345",
            capacity=1,
            status="PUBLISHED",
            external_id=external_id,
        )
        s.add(slot)
        s.flush()
        booking = Booking(
            slot_id=slot.id,
            provider_id=provider_id,
            customer_name="Max Mustermann",
            customer_email="max@example.com",
            customer_phone="01511234567",
            status="confirmed",
            created_at=app_module._to_db_utc_naive(app_module._now()),
        )
        s.add(booking)
        s.commit()
        return slot.id, booking.id


def test_writeback_booking_patches_imported_event(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    _sid, bid = _make_slot_and_booking(pid, external_id="gcal:evt-imported")
    captured = {}

    def _patch(*args, **kwargs):
        captured["args"] = args
        captured["body"] = args[5] if len(args) > 5 else kwargs.get("body")
        return {"id": "evt-imported"}

    monkeypatch.setattr(app_module, "_google_patch_event", _patch)
    app_module._google_writeback("booking", bid)
    body = captured.get("body") or {}
    assert body.get("summary", "").startswith("GEBUCHT:")
    blob = str(body)
    assert "Max Mustermann" not in blob
    assert "max@example.com" not in blob
    assert "01511234567" not in blob


def test_writeback_booking_creates_event_for_native_slot(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    sid, bid = _make_slot_and_booking(pid, external_id=None)

    def _create(*args, **kwargs):
        body = args[4] if len(args) > 4 else kwargs.get("body")
        assert "Max" not in str(body)
        assert "max@example.com" not in str(body)
        return {"id": "new-gcal-1"}

    monkeypatch.setattr(app_module, "_google_create_event", _create)
    app_module._google_writeback("booking", bid)
    with Session(app_module.engine) as s:
        slot = s.get(Slot, sid)
        # Eigene Events stehen in gcal_event_id (external_id bleibt frei fuer Fremd-APIs)
        assert slot.gcal_event_id == "new-gcal-1"
        assert slot.external_id is None


def test_writeback_cancel_unmarks_imported_event(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    _sid, bid = _make_slot_and_booking(pid, external_id="gcal:evt-imported", title="Haarschnitt")
    captured = {}

    def _patch(*args, **kwargs):
        captured["body"] = args[5] if len(args) > 5 else kwargs.get("body")
        return {}

    monkeypatch.setattr(app_module, "_google_patch_event", _patch)
    _set_booking_status(bid, "canceled")
    app_module._google_writeback("cancel", bid)
    assert captured["body"]["summary"] == "Haarschnitt"


def test_writeback_cancel_frees_outbound_event(test_client, monkeypatch):
    """Storno: eigenes Event bleibt bestehen und steht wieder auf FREI
    (der Slot ist weiterhin veroeffentlicht und buchbar)."""
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    sid, bid = _make_slot_and_booking(pid, external_id="gcal-out:created-1")
    captured = {}

    def _patch(*args, **kwargs):
        captured["event_id"] = args[4]
        captured["body"] = args[5]
        return {}

    monkeypatch.setattr(app_module, "_google_patch_event", _patch)
    _set_booking_status(bid, "canceled")
    app_module._google_writeback("cancel", bid)
    assert captured["event_id"] == "created-1"
    assert captured["body"]["summary"] == "FREI: Haarschnitt"
    with Session(app_module.engine) as s:
        sl = s.get(Slot, sid)
        assert sl.external_id is None  # Altbestand migriert
        assert sl.gcal_event_id == "created-1"


def test_sync_skips_booked_marker_events(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    booked = _future_event("booked-1", summary="GEBUCHT: Haarschnitt")
    free = _future_event("free-1", summary="Freier Slot")
    _connect(pid, monkeypatch, events=[booked, free])
    with Session(app_module.engine) as s:
        ext_ids = {sl.external_id for sl in s.query(Slot).filter(Slot.provider_id == pid).all()}
    assert "gcal:free-1" in ext_ids
    assert "gcal:booked-1" not in ext_ids


def test_sync_skips_overlap_with_confirmed_booking(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    _make_slot_and_booking(pid, external_id=None)
    overlap = _future_event("overlap-1", hours_from_now=48)  # gleicher Horizont wie _make_slot (~2 Tage)
    monkeypatch.setattr(app_module, "_google_list_events", lambda *a, **k: [overlap])
    res = test_client.post("/api/google/sync-now", headers=_auth_headers(pid))
    assert res.status_code == 200
    with Session(app_module.engine) as s:
        count = s.query(Slot).filter(Slot.provider_id == pid, Slot.external_id == "gcal:overlap-1").count()
    assert count == 0


def test_disconnect_revokes_google_token(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    revoked = {"n": 0}

    def _revoke(token):
        revoked["n"] += 1
        assert token  # irgendein Token, aber nicht leer

    monkeypatch.setattr(app_module, "_google_revoke_token", _revoke)
    res = test_client.post("/api/google/disconnect", headers=_auth_headers(pid))
    assert res.status_code == 200
    assert revoked["n"] == 1


def test_calendar_list_and_select(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    monkeypatch.setattr(
        app_module,
        "_google_list_calendars",
        lambda *a, **k: [
            {"id": "primary", "summary": "Haupt", "primary": True},
            {"id": "tm-cal", "summary": "Terminmarktplatz", "primary": False},
        ],
    )
    res = test_client.get("/api/google/calendars", headers=_auth_headers(pid))
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert len(body["calendars"]) == 2

    monkeypatch.setattr(app_module, "_google_list_events", lambda *a, **k: [])
    res = test_client.post(
        "/api/google/calendar",
        headers=_auth_headers(pid),
        json={"calendar_id": "tm-cal"},
    )
    assert res.status_code == 200
    with Session(app_module.engine) as s:
        conn = s.query(GoogleCalendarConnection).filter(
            GoogleCalendarConnection.provider_id == pid
        ).one()
    assert conn.calendar_id == "tm-cal"


def test_status_includes_writeback_flag(test_client):
    pid = _create_provider(plan="profi")
    res = test_client.get("/api/google/status", headers=_auth_headers(pid))
    assert res.status_code == 200
    assert res.get_json()["writeback"] is True


# --------------------------------------------------------------------------
# PKCE: code_verifier muss vom Start zum Callback gelangen
# --------------------------------------------------------------------------
def test_pkce_verifier_roundtrip(monkeypatch):
    """Regression: ohne gespeicherten Verifier lehnt Google den Code-Tausch ab
    (exchange_failed / "Missing code verifier")."""
    pid = _create_provider(plan="profi")
    monkeypatch.setattr(app_module, "_google_oauth_configured", lambda: True)
    seen = {}

    def fake_build(state, code_verifier=None):
        seen["start"] = code_verifier
        return "https://accounts.google.com/o/oauth2/auth?state=" + state

    def fake_exchange(code, code_verifier=None):
        seen["callback"] = code_verifier
        return {
            "access_token": "at", "refresh_token": "rt",
            "expiry": app_module._now() + timedelta(hours=1),
            "scopes": " ".join(app_module.GOOGLE_CALENDAR_SCOPES),
            "email": "kalender@example.com", "calendar_id": "kalender@example.com",
        }

    monkeypatch.setattr(app_module, "_google_build_auth_url", fake_build)
    monkeypatch.setattr(app_module, "_google_exchange_code", fake_exchange)
    monkeypatch.setattr(app_module, "_google_list_events", lambda *a, **k: [])

    client = app_module.app.test_client()
    res = client.get("/oauth/google/start", headers=_auth_headers(pid))
    assert res.status_code in (301, 302)
    cookie = res.headers.get("Set-Cookie", "")
    assert app_module.GOOGLE_PKCE_COOKIE in cookie
    assert "HttpOnly" in cookie
    assert seen["start"] and 43 <= len(seen["start"]) <= 128

    state = app_module._google_state_serializer().dumps(str(pid))
    res = client.get(f"/oauth/google/callback?code=abc&state={state}", headers=_auth_headers(pid))
    assert "google=connected" in res.headers.get("Location", "")
    assert seen["callback"] == seen["start"]


def test_real_flow_sends_matching_pkce():
    """Echte google-auth-oauthlib: Challenge in der URL passt zum Verifier."""
    import base64, hashlib
    from urllib.parse import urlparse, parse_qs
    old = (app_module.GOOGLE_CLIENT_ID, app_module.GOOGLE_CLIENT_SECRET, app_module.GOOGLE_OAUTH_REDIRECT)
    app_module.GOOGLE_CLIENT_ID = "cid.apps.googleusercontent.com"
    app_module.GOOGLE_CLIENT_SECRET = "secret"
    app_module.GOOGLE_OAUTH_REDIRECT = "https://test.example/oauth/google/callback"
    try:
        verifier = app_module._google_new_code_verifier()
        url = app_module._google_build_auth_url("st", code_verifier=verifier)
    finally:
        app_module.GOOGLE_CLIENT_ID, app_module.GOOGLE_CLIENT_SECRET, app_module.GOOGLE_OAUTH_REDIRECT = old
    q = parse_qs(urlparse(url).query)
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert q["code_challenge"] == [expected]
    assert q["code_challenge_method"] == ["S256"]


# --------------------------------------------------------------------------
# 2-Wege-Sync: Slots -> Google, Kundennamen (Opt-in), Aufraeumen
# --------------------------------------------------------------------------
def _make_free_slot(provider_id: str, *, status="PUBLISHED", capacity=1, title="Herrenschnitt"):
    with Session(app_module.engine) as s:
        start_at = app_module._to_db_utc_naive(app_module._now() + timedelta(days=3))
        slot = Slot(
            provider_id=provider_id, title=title, category="Friseur",
            start_at=start_at, end_at=start_at + timedelta(hours=1),
            location="Teststrasse 1", city="Teststadt", zip="12345",
            capacity=capacity, status=status,
        )
        s.add(slot)
        s.commit()
        return slot.id


def _add_booking(slot_id, provider_id, first="Erika", last="Musterfrau", status="confirmed"):
    with Session(app_module.engine) as s:
        b = Booking(
            slot_id=slot_id, provider_id=provider_id,
            customer_name=f"{first} {last}", customer_first_name=first, customer_last_name=last,
            customer_email="erika@example.com", customer_phone="0171000000",
            status=status, created_at=app_module._to_db_utc_naive(app_module._now()),
        )
        s.add(b)
        s.commit()
        return b.id


def _capture_google(monkeypatch):
    calls = {"create": [], "patch": [], "delete": []}

    def _create(a, r, sc, cal, body):
        calls["create"].append(body)
        return {"id": f"tm-evt-{len(calls['create'])}"}

    def _patch(a, r, sc, cal, eid, body):
        calls["patch"].append((eid, body))
        return {}

    def _delete(a, r, sc, cal, eid):
        calls["delete"].append(eid)

    monkeypatch.setattr(app_module, "_google_create_event", _create)
    monkeypatch.setattr(app_module, "_google_patch_event", _patch)
    monkeypatch.setattr(app_module, "_google_delete_event", _delete)
    return calls


def test_sync_pushes_published_free_slot_to_google(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    sid = _make_free_slot(pid)
    _make_free_slot(pid, status="DRAFT", title="Entwurf")
    calls = _capture_google(monkeypatch)
    with Session(app_module.engine) as s:
        conn_id = s.scalar(app_module.select(GoogleCalendarConnection.id).where(
            GoogleCalendarConnection.provider_id == pid))
    result = app_module._sync_google_connection(conn_id)
    assert result["pushed"] == 1  # Entwurf wird nicht eingetragen
    body = calls["create"][0]
    assert body["summary"] == "FREI: Herrenschnitt"
    assert body["colorId"] == app_module.GCAL_COLOR_FREE
    assert body["extendedProperties"]["private"]["tm_slot_id"] == str(sid)
    with Session(app_module.engine) as s:
        assert s.get(Slot, sid).gcal_event_id == "tm-evt-1"
    # Zweiter Lauf legt nichts doppelt an
    assert app_module._sync_google_connection(conn_id)["pushed"] == 0


def test_import_skips_own_events(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    own = _future_event("own-1", summary="FREI: Herrenschnitt")
    own["tm_slot_id"] = "irgendein-slot"
    _connect(pid, monkeypatch, events=[own])
    with Session(app_module.engine) as s:
        ext_ids = {sl.external_id for sl in s.query(Slot).filter(Slot.provider_id == pid).all()}
    assert "gcal:own-1" not in ext_ids


def test_list_events_exposes_own_marker(monkeypatch):
    class _Req:
        def __init__(self, resp): self.resp = resp
        def execute(self): return self.resp

    class _Events:
        def list(self, **k):
            start = (app_module._now() + timedelta(days=1)).isoformat()
            end = (app_module._now() + timedelta(days=1, hours=1)).isoformat()
            return _Req({"items": [{
                "id": "e1", "summary": "FREI: X",
                "start": {"dateTime": start}, "end": {"dateTime": end},
                "extendedProperties": {"private": {"tm_slot_id": "s-1"}},
            }]})

    class _Svc:
        def events(self): return _Events()

    import googleapiclient.discovery as disc
    monkeypatch.setattr(disc, "build", lambda *a, **k: _Svc())
    out = app_module._google_list_events("a", "r", None, "primary")
    assert out[0]["tm_slot_id"] == "s-1"


def test_booking_without_name_by_default(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    sid = _make_free_slot(pid)
    calls = _capture_google(monkeypatch)
    app_module._gcal_sync_slot(sid)
    bid = _add_booking(sid, pid)
    app_module._google_writeback("booking", bid)
    eid, body = calls["patch"][-1]
    assert eid == "tm-evt-1"
    assert body["summary"] == "GEBUCHT: Herrenschnitt"
    assert body["colorId"] == app_module.GCAL_COLOR_BOOKED
    blob = str(body)
    assert "Erika" not in blob and "erika@example.com" not in blob and "0171000000" not in blob


def test_settings_enable_names_relabels_booked(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    sid = _make_free_slot(pid)
    calls = _capture_google(monkeypatch)
    app_module._gcal_sync_slot(sid)
    _add_booking(sid, pid)
    res = test_client.post("/api/google/settings", json={"show_customer_names": True},
                           headers=_auth_headers(pid))
    assert res.status_code == 200 and res.get_json()["show_customer_names"] is True
    eid, body = calls["patch"][-1]
    assert body["summary"] == "GEBUCHT: Herrenschnitt – Erika Musterfrau"
    # Nie Kontaktdaten
    assert "erika@example.com" not in str(body) and "0171000000" not in str(body)
    st = test_client.get("/api/google/status", headers=_auth_headers(pid)).get_json()
    assert st["show_customer_names"] is True


def test_settings_requires_connection_and_pro(test_client):
    pid = _create_provider(plan="profi")
    res = test_client.post("/api/google/settings", json={"show_customer_names": True},
                           headers=_auth_headers(pid))
    assert res.status_code == 400
    pid2 = _create_provider(plan=None)
    res = test_client.post("/api/google/settings", json={"show_customer_names": True},
                           headers=_auth_headers(pid2))
    assert res.status_code == 403


def test_course_slot_shows_count_and_names(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    sid = _make_free_slot(pid, capacity=3, title="Yoga")
    calls = _capture_google(monkeypatch)
    with Session(app_module.engine) as s:
        s.get(GoogleCalendarConnection, s.scalar(app_module.select(GoogleCalendarConnection.id).where(
            GoogleCalendarConnection.provider_id == pid))).show_customer_names = True
        s.commit()
    app_module._gcal_sync_slot(sid)
    _add_booking(sid, pid, first="Anna", last="A")
    _add_booking(sid, pid, first="Ben", last="B")
    app_module._gcal_sync_slot(sid)
    _eid, body = calls["patch"][-1]
    assert body["summary"] == "Yoga (2/3 gebucht)"
    assert "Anna A" in body["description"] and "Ben B" in body["description"]


def test_unpublish_removes_own_event(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    sid = _make_free_slot(pid)
    calls = _capture_google(monkeypatch)
    app_module._gcal_sync_slot(sid)
    with Session(app_module.engine) as s:
        s.get(Slot, sid).status = "DRAFT"
        s.commit()
    assert app_module._gcal_sync_slot(sid) == "deleted"
    assert calls["delete"] == ["tm-evt-1"]
    with Session(app_module.engine) as s:
        assert s.get(Slot, sid).gcal_event_id is None


def test_event_deleted_in_google_is_recreated(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    sid = _make_free_slot(pid)
    calls = _capture_google(monkeypatch)
    app_module._gcal_sync_slot(sid)

    class _Gone(Exception):
        class resp:  # wie googleapiclient.errors.HttpError
            status = 404

    def _patch(*a, **k):
        raise _Gone()

    monkeypatch.setattr(app_module, "_google_patch_event", _patch)
    assert app_module._gcal_sync_slot(sid) == "created"
    with Session(app_module.engine) as s:
        assert s.get(Slot, sid).gcal_event_id == "tm-evt-2"


def test_delete_endpoint_removes_event(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    _connect(pid, monkeypatch, events=[])
    sid = _make_free_slot(pid)
    calls = _capture_google(monkeypatch)
    app_module._gcal_sync_slot(sid)
    res = test_client.delete(f"/slots/{sid}", headers=_auth_headers(pid))
    assert res.status_code == 200 and res.get_json().get("deleted") is True
    assert calls["delete"] == ["tm-evt-1"]


def test_no_google_calls_without_connection(test_client, monkeypatch):
    pid = _create_provider(plan="profi")
    sid = _make_free_slot(pid)
    calls = _capture_google(monkeypatch)
    assert app_module._gcal_sync_slot(sid) == "skipped"
    assert calls == {"create": [], "patch": [], "delete": []}
