import os
import tempfile

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("EMAILS_ENABLED", "false")

import app as app_module
from models import Base, AlertSubscription


def _ensure_public_schema_on_connect():
    def _attach(dbapi_conn, _):
        try:
            cur = dbapi_conn.cursor()
            try:
                cur.execute("ATTACH DATABASE ':memory:' AS public")
            except Exception:
                pass
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.alert_subscription (
                  id TEXT PRIMARY KEY,
                  email TEXT,
                  manage_key TEXT,
                  notification_limit INTEGER,
                  created_at DATETIME
                );
                """
            )
            cur.close()
        except Exception:
            pass

    event.listen(app_module.engine, "connect", _attach)


@pytest.fixture(scope="function")
def test_client():
    _ensure_public_schema_on_connect()
    app_module.engine.dispose()
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    app_module._ensure_geo_tables()
    return app_module.app.test_client()


def test_alert_stats_requires_email(test_client):
    r = test_client.get("/api/alerts/stats")
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "email_required"


def test_alert_stats_invalid_email(test_client):
    r = test_client.get("/api/alerts/stats?email=invalid-email")
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_email"


def test_alert_stats_counts_existing(test_client):
    with Session(app_module.engine) as s:
        a1 = AlertSubscription(email="a@example.com", zip="12345", active=True, email_confirmed=True, verify_token="v1")
        a2 = AlertSubscription(email="a@example.com", zip="12345", active=False, email_confirmed=False, verify_token="v2")
        s.add_all([a1, a2])
        s.commit()

    r = test_client.get("/api/alerts/stats?email=a@example.com")
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True
    assert data.get("used") == 2


def test_create_alert_invalid_zip(test_client):
    payload = {
        "email": "a@example.com",
        "zip": "12",
        "categories": "friseur",
        "via_email": True,
    }
    r = test_client.post("/api/alerts", json=payload)
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "invalid_zip"


def test_create_alert_category_required(test_client):
    payload = {
        "email": "a@example.com",
        "zip": "12345",
        "categories": "",
        "via_email": True,
    }
    r = test_client.post("/api/alerts", json=payload)
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "category_required"


def test_create_alert_requires_channel(test_client):
    payload = {
        "email": "a@example.com",
        "zip": "12345",
        "categories": "friseur",
        "via_email": False,
        "via_sms": False,
    }
    r = test_client.post("/api/alerts", json=payload)
    assert r.status_code == 400
    data = r.get_json() or {}
    assert data.get("error") == "channel_required"


def test_create_alert_success(test_client):
    payload = {
        "email": "a@example.com",
        "zip": "12345",
        "categories": "friseur",
        "via_email": True,
    }
    r = test_client.post("/api/alerts", json=payload)
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("ok") is True
    assert data.get("manage_key")
    stats = data.get("stats") or {}
    assert stats.get("used") == 1
