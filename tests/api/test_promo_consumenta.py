"""
Tests für das Promo-Code-System (CONSUMENTA26).
Benötigt die PostgreSQL-Testdatenbank (gen_random_uuid() ist PG-spezifisch).

Ausføhren (aus App-Verzeichnis):
    cd /opt/terminmarktplatz-test
    DATABASE_URL="postgresql://terminmarktplatz_user:Abc1234.@localhost/terminmarktplatz_test" \\
      venv/bin/pytest tests/api/test_promo_consumenta.py -v

Hinweis: Nicht zusammen mit SQLite-Tests ausführen, da DATABASE_URL konfliktiert.
"""
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from sqlalchemy import text
from sqlalchemy.orm import Session

# PostgreSQL-Testdatenbank — muss vor app-Import gesetzt sein.
# Beim Ausführen via DATABASE_URL=... pytest ... wird diese Zeile von setdefault
# nicht øberschrieben, da die Env-Var bereits gesetzt ist.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://terminmarktplatz_user:Abc1234.@localhost/terminmarktplatz_test",
)
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("FRONTEND_URL", "http://testserver")
os.environ.setdefault("EMAILS_ENABLED", "false")

import app as app_module
from models import Provider

# PostgreSQL-only: gen_random_uuid()/timestamptz sind PG-spezifisch. Auf anderen
# Backends (z. B. SQLite in der CI) wird das gesamte Modul sauber uebersprungen,
# statt mit Fehlern abzubrechen.
pytestmark = pytest.mark.skipif(
    app_module.engine.url.get_backend_name() != "postgresql",
    reason="Promo-Tests benoetigen PostgreSQL (gen_random_uuid/timestamptz).",
)

# Eindeutiger Prefix før alle Test-Daten → sauberes Cleanup
TEST_PREFIX = f"pytest_promo_{uuid.uuid4().hex[:6]}_"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_mail():
    """Alle Mail-Versandaufrufe werden gestubt."""
    with patch.object(app_module, "send_mail", return_value=(True, "mocked")):
        yield


@pytest.fixture(scope="module")
def client():
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def _cleanup():
    """Test-Daten nach jedem Test aus der DB entfernen."""
    yield
    with app_module.engine.begin() as conn:
        conn.execute(text(
            "DELETE FROM promo_redemptions WHERE provider_id IN "
            "(SELECT id FROM provider WHERE email LIKE :p)"
        ), {"p": f"{TEST_PREFIX}%"})
        conn.execute(text(
            "DELETE FROM slot WHERE provider_id IN "
            "(SELECT id FROM provider WHERE email LIKE :p)"
        ), {"p": f"{TEST_PREFIX}%"})
        conn.execute(text(
            "DELETE FROM plan_purchase WHERE provider_id IN "
            "(SELECT id FROM provider WHERE email LIKE :p)"
        ), {"p": f"{TEST_PREFIX}%"})
        conn.execute(text(
            "DELETE FROM provider WHERE email LIKE :p"
        ), {"p": f"{TEST_PREFIX}%"})
        conn.execute(text(
            "DELETE FROM promo_codes WHERE code LIKE 'PYTEST_%'"
        ))


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_provider(plan: str = "free") -> str:
    """Erstellt Test-Provider, gibt str(uuid) zurück."""
    email = f"{TEST_PREFIX}{uuid.uuid4().hex[:8]}@example.com"
    with Session(app_module.engine) as s:
        p = Provider(
            email=email,
            pw_hash=app_module.ph.hash("testpass123"),
            company_name="Pytest GmbH",
            branch="Friseur",
            street="Teststr. 1",
            zip="12345",
            city="Teststadt",
            phone="0911000001",
            status="approved",
            email_verified_at=app_module._now(),
        )
        p.plan = plan
        p.free_slots_per_month = 3  # NOT NULL im Schema
        s.add(p)
        s.commit()
        return str(p.id)


def _auth(pid: str) -> dict:
    """Gibt Authorization-Header før gegebene Provider-ID zurück."""
    access, _ = app_module.issue_tokens(pid, False)
    return {"Authorization": f"Bearer {access}"}


def _make_admin() -> str:
    """Erstellt einen Admin-Provider (is_admin=True), gibt str(uuid) zurück."""
    email = f"{TEST_PREFIX}admin_{uuid.uuid4().hex[:8]}@example.com"
    with Session(app_module.engine) as s:
        p = Provider(
            email=email,
            pw_hash=app_module.ph.hash("testpass123"),
            company_name="Pytest Admin GmbH",
            branch="Friseur",
            street="Teststr. 1",
            zip="12345",
            city="Teststadt",
            phone="0911000009",
            status="approved",
            email_verified_at=app_module._now(),
            is_admin=True,
        )
        p.plan = "basic"
        p.free_slots_per_month = 3
        s.add(p)
        s.commit()
        return str(p.id)


def _insert_promo(code: str, valid_until: str, test_end: str,
                  active: bool = True, plan: str = "profi"):
    """Føgd Testcode in promo_codes ein (ON CONFLICT → UPDATE)."""
    with app_module.engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO promo_codes (code, plan, valid_until, test_end, active)
            VALUES (:code, :plan, CAST(:valid_until AS date), CAST(:test_end AS date), :active)
            ON CONFLICT (code) DO UPDATE
              SET valid_until = EXCLUDED.valid_until,
                  test_end    = EXCLUDED.test_end,
                  active      = EXCLUDED.active
        """), {"code": code, "plan": plan,
               "valid_until": valid_until, "test_end": test_end, "active": active})


def _insert_redemption(pid: str, test_end, code: str = "CONSUMENTA26"):
    """Føgd Redemption-Eintrag før den Provider ein."""
    with app_module.engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO promo_redemptions (id, provider_id, code, test_end)
            VALUES (gen_random_uuid(), :pid, :code, :test_end)
        """), {"pid": pid, "code": code, "test_end": test_end})


def _insert_slots(pid: str, count: int, status: str = "PUBLISHED"):
    """Erstellt N Slots mit gegebenem Status før Provider."""
    with app_module.engine.begin() as conn:
        for i in range(count):
            slot_dt = datetime(2027, 4, 1, 10 + i, 0, tzinfo=timezone.utc)
            conn.execute(text("""
                INSERT INTO slot (id, provider_id, title, category, start_at, end_at, status, created_at)
                VALUES (gen_random_uuid(), :pid, 'Testtermin', 'Test', :start, :start + interval '60 minutes', :status, NOW())
            """), {"pid": pid, "start": slot_dt, "status": status})


def _count_published(pid: str) -> int:
    with app_module.engine.connect() as conn:
        return conn.execute(text(
            "SELECT COUNT(*) FROM slot WHERE provider_id = :pid AND status = 'PUBLISHED'"
        ), {"pid": pid}).scalar()


# ---------------------------------------------------------------------------
# /api/promo/check
# ---------------------------------------------------------------------------

class TestPromoCheck:

    def test_valid_code_returns_ok(self, client):
        """/api/promo/check?code=CONSUMENTA26 → valid=True."""
        r = client.get("/api/promo/check?code=CONSUMENTA26")
        assert r.status_code == 200
        data = r.get_json() or {}
        assert data.get("ok") is True, f"Erwartet ok=True, bekam: {data}"
        assert "plan" in data, f"Kein plan-Key: {data}"

    def test_unknown_code_returns_invalid(self, client):
        """/api/promo/check mit unbekanntem Code → valid=False."""
        r = client.get("/api/promo/check?code=UNKNOWN_XYZ_12345")
        assert r.status_code == 400

    def test_missing_code_param_returns_400(self, client):
        """/api/promo/check ohne ?code → 400."""
        r = client.get("/api/promo/check")
        assert r.status_code == 400

    def test_expired_code_returns_invalid(self, client):
        """Abgelaufener Code (valid_until in Vergangenheit) → valid=False."""
        _insert_promo("PYTEST_EXPIRED", "2020-01-01", "2020-04-01")
        r = client.get("/api/promo/check?code=PYTEST_EXPIRED")
        data = r.get_json() or {}
        assert "error" in data, f"Abgelaufener Code sollte ungøltig sein: {data}"

    def test_inactive_code_returns_invalid(self, client):
        """Inaktiver Code → valid=False."""
        _insert_promo("PYTEST_INACTIVE", "2099-01-01", "2099-04-01", active=False)
        r = client.get("/api/promo/check?code=PYTEST_INACTIVE")
        data = r.get_json() or {}
        assert "error" in data, f"Inaktiver Code sollte ungøltig sein: {data}"


# ---------------------------------------------------------------------------
# /api/promo/redeem
# ---------------------------------------------------------------------------

class TestPromoRedeem:

    def test_redeem_success_returns_ok(self, client):
        """Einlôsen von CONSUMENTA26 → ok=True."""
        pid = _make_provider("free")
        r = client.post("/api/promo/redeem",
                        json={"code": "CONSUMENTA26"},
                        headers=_auth(pid))
        assert r.status_code == 200
        assert (r.get_json() or {}).get("ok") is True

    def test_redeem_upgrades_plan(self, client):
        """Nach Einlôsen ist Provider nicht mehr auf 'free'."""
        pid = _make_provider("free")
        client.post("/api/promo/redeem",
                    json={"code": "CONSUMENTA26"},
                    headers=_auth(pid))
        with Session(app_module.engine) as s:
            p = s.get(Provider, uuid.UUID(pid))
            assert p.plan != "free", f"Plan sollte aktualisiert sein, ist: {p.plan}"

    def test_redeem_creates_redemption_record(self, client):
        """Nach Einlôsen existiert Eintrag in promo_redemptions."""
        pid = _make_provider("free")
        client.post("/api/promo/redeem",
                    json={"code": "CONSUMENTA26"},
                    headers=_auth(pid))
        with app_module.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT test_end FROM promo_redemptions WHERE provider_id = :pid"
            ), {"pid": pid}).fetchone()
        assert row is not None, "Kein Eintrag in promo_redemptions"
        assert row.test_end is not None, "test_end ist NULL"

    def test_redeem_test_end_matches_promo_code(self, client):
        """test_end in promo_redemptions entspricht dem Datum aus promo_codes."""
        pid = _make_provider("free")
        client.post("/api/promo/redeem",
                    json={"code": "CONSUMENTA26"},
                    headers=_auth(pid))
        with app_module.engine.connect() as conn:
            redemption = conn.execute(text(
                "SELECT test_end FROM promo_redemptions WHERE provider_id = :pid"
            ), {"pid": pid}).fetchone()
            code_row = conn.execute(text(
                "SELECT test_end FROM promo_codes WHERE code = 'CONSUMENTA26'"
            )).fetchone()
        assert redemption.test_end == code_row.test_end, (
            f"test_end stimmt nicht überein: {redemption.test_end} != {code_row.test_end}"
        )

    def test_duplicate_redeem_rejected(self, client):
        """Zweites Einlôsen desselben Codes → 400 oder 409."""
        pid = _make_provider("free")
        headers = _auth(pid)
        r1 = client.post("/api/promo/redeem",
                         json={"code": "CONSUMENTA26"}, headers=headers)
        assert r1.status_code == 200

        r2 = client.post("/api/promo/redeem",
                         json={"code": "CONSUMENTA26"}, headers=headers)
        assert r2.status_code in (400, 409), (
            f"Zweites Einlôsen sollte abgelehnt werden, Status: {r2.status_code}"
        )
        assert (r2.get_json() or {}).get("ok") is not True

    def test_redeem_requires_auth(self, client):
        """Einlôsen ohne Bearer-Token → 401."""
        r = client.post("/api/promo/redeem", json={"code": "CONSUMENTA26"})
        assert r.status_code == 401

    def test_redeem_invalid_code_rejected(self, client):
        """Ungøltiger Code → 400 oder 404."""
        pid = _make_provider("free")
        r = client.post("/api/promo/redeem",
                        json={"code": "FAKE_XYZ_999"},
                        headers=_auth(pid))
        assert r.status_code in (400, 404)
        assert (r.get_json() or {}).get("ok") is not True

    def test_redeem_expired_code_rejected(self, client):
        """Abgelaufener Code kann nicht eingelôst werden → 400 oder 410."""
        _insert_promo("PYTEST_OLD", "2020-01-01", "2020-04-01", active=True)
        pid = _make_provider("free")
        r = client.post("/api/promo/redeem",
                        json={"code": "PYTEST_OLD"},
                        headers=_auth(pid))
        assert r.status_code in (400, 410)
        assert (r.get_json() or {}).get("ok") is not True

    def test_redeem_rejected_for_paid_plan(self, client):
        """Provider mit aktivem bezahltem Abo kann keinen Promo-Code einlôsen."""
        _insert_promo("PYTEST_PAID", "2099-01-01", "2099-04-01")
        pid = _make_provider("profi")
        with app_module.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO plan_purchase (id, provider_id, plan, price_eur, period_start, status, period_end, created_at) "
                "VALUES (gen_random_uuid(), :pid, 'profi', 9.90, CURRENT_DATE, 'paid', CURRENT_DATE + 30, NOW())"
            ), {"pid": pid})
        r = client.post("/api/promo/redeem",
                        json={"code": "PYTEST_PAID"},
                        headers=_auth(pid))
        assert r.status_code in (400, 409)
        assert (r.get_json() or {}).get("ok") is not True

    def test_redeem_sends_confirmation_mail(self, client):
        """Nach erfolgreichem Einlôsen wird genau eine Bestaetigungs-Mail ausgelôst."""
        _insert_promo("PYTEST_MAIL", "2099-01-01", "2099-04-01")
        pid = _make_provider("free")
        with patch.object(app_module, "_send_promo_confirmation_mail") as m:
            r = client.post("/api/promo/redeem",
                            json={"code": "PYTEST_MAIL"},
                            headers=_auth(pid))
        assert r.status_code == 200
        assert m.call_count == 1, f"Erwartet 1 Bestaetigungs-Mail, war: {m.call_count}"


# ---------------------------------------------------------------------------
# /api/admin/promo-overview
# ---------------------------------------------------------------------------

class TestPromoAdminOverview:

    def test_requires_auth(self, client):
        """Ohne Login → 401."""
        r = client.get("/api/admin/promo-overview")
        assert r.status_code == 401

    def test_forbidden_for_non_admin(self, client):
        """Normaler Provider (kein Admin) → 403."""
        pid = _make_provider("free")
        r = client.get("/api/admin/promo-overview", headers=_auth(pid))
        assert r.status_code == 403

    def test_admin_sees_redemption(self, client):
        """Admin sieht eingelôste Codes inkl. E-Mail des Providers."""
        _insert_promo("PYTEST_OVR", "2099-01-01", "2099-04-01")
        admin_id = _make_admin()

        # Normaler Provider lôst ein
        user_id = _make_provider("free")
        client.post("/api/promo/redeem",
                    json={"code": "PYTEST_OVR"},
                    headers=_auth(user_id))

        with Session(app_module.engine) as s:
            user_email = s.get(Provider, uuid.UUID(user_id)).email

        r = client.get("/api/admin/promo-overview", headers=_auth(admin_id))
        assert r.status_code == 200
        data = r.get_json() or {}
        assert data.get("total", 0) >= 1
        emails = [e.get("email") for e in data.get("entries", [])]
        assert user_email in emails, f"Einlôsung des Providers fehlt in der Uebersicht: {emails}"


# ---------------------------------------------------------------------------
# _promo_downgrade_job
# ---------------------------------------------------------------------------

class TestPromoDowngradeJob:

    def test_expired_provider_slots_get_limited(self, client):
        """Nach test_end: überzählige Slots werden auf DRAFT gesetzt (max. 3 PUBLISHED)."""
        pid = _make_provider("profi")
        _insert_slots(pid, count=5)
        _insert_redemption(pid, "2027-02-28")

        with freeze_time("2027-03-01 03:00:00"):
            app_module._promo_downgrade_job()

        published = _count_published(pid)
        assert published <= 3, f"Zu viele PUBLISHED Slots nach Downgrade: {published}"

    def test_provider_with_paid_plan_not_touched(self, client):
        """Provider mit aktivem Kauf-Abo wird nicht herabgestuft."""
        pid = _make_provider("profi")
        _insert_slots(pid, count=2)
        _insert_redemption(pid, "2027-02-28")

        # Aktiver bezahlter Plan → soll Job überspringen
        with app_module.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO plan_purchase (id, provider_id, plan, price_eur, period_start, status, period_end, created_at)
                VALUES (gen_random_uuid(), :pid, 'profi', 0.00, CURRENT_DATE, 'paid', '2028-01-01', NOW())
            """), {"pid": pid})

        with freeze_time("2027-03-01 03:00:00"):
            app_module._promo_downgrade_job()

        published = _count_published(pid)
        assert published == 2, (
            f"Zahlender Kunde darf nicht herabgestuft werden, published={published}"
        )

    def test_active_test_provider_not_touched(self, client):
        """Provider mit noch aktivem test_end wird nicht berührt."""
        pid = _make_provider("profi")
        _insert_slots(pid, count=5)
        _insert_redemption(pid, "2027-06-30")  # test_end in der Zukunft

        with freeze_time("2027-03-01 03:00:00"):
            app_module._promo_downgrade_job()

        published = _count_published(pid)
        assert published == 5, (
            f"Noch aktiver Test-Provider darf nicht herabgestuft werden, published={published}"
        )


# ---------------------------------------------------------------------------
# _promo_reminder_job
# ---------------------------------------------------------------------------

class TestPromoReminderJob:

    def test_reminder_sent_14_days_before_end(self, client):
        """14 Tage vor test_end wird Erinnerungs-Mail ausgelôst."""
        pid = _make_provider("profi")
        test_end = datetime(2027, 3, 15, 12, 0, tzinfo=timezone.utc)
        _insert_redemption(pid, test_end)

        sent = []

        def _capture(email, *_):
            sent.append(email)

        with patch.object(app_module, "_send_promo_reminder_mail", side_effect=_capture):
            with freeze_time("2027-03-01 09:00:00"):
                app_module._promo_reminder_job()

        assert len(sent) == 1, f"Genau 1 Erinnerung erwartet, gesendet: {len(sent)}"

    def test_no_reminder_outside_window(self, client):
        """Außerhalb des 14-Tage-Fensters keine Mail (10 Tage vorher)."""
        pid = _make_provider("profi")
        test_end = datetime(2027, 3, 15, 12, 0, tzinfo=timezone.utc)
        _insert_redemption(pid, test_end)

        sent = []

        def _capture(email, *_):
            sent.append(email)

        with patch.object(app_module, "_send_promo_reminder_mail", side_effect=_capture):
            with freeze_time("2027-03-05 09:00:00"):  # 10 Tage vor test_end → zu frøh
                app_module._promo_reminder_job()

        assert len(sent) == 0, f"Keine Mail erwartet außerhalb des Fensters, gesendet: {len(sent)}"

    def test_no_reminder_after_test_end(self, client):
        """Nach test_end wird keine Erinnerungs-Mail mehr gesendet."""
        pid = _make_provider("profi")
        test_end = datetime(2027, 3, 15, 12, 0, tzinfo=timezone.utc)
        _insert_redemption(pid, test_end)

        sent = []

        def _capture(email, *_):
            sent.append(email)

        with patch.object(app_module, "_send_promo_reminder_mail", side_effect=_capture):
            with freeze_time("2027-04-01 09:00:00"):  # Nach test_end
                app_module._promo_reminder_job()

        assert len(sent) == 0, f"Keine Mail nach test_end erwartet, gesendet: {len(sent)}"
