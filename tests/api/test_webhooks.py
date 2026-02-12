"""
Tests für Webhook-Endpoints (Stripe, CopeCart).
"""
import os
import tempfile

import pytest

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("FRONTEND_URL", "http://testserver")

# Stripe und CopeCart nicht konfiguriert → 501 bzw. 200 (no-op)
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
os.environ.pop("COPECART_WEBHOOK_SECRET", None)

import app as app_module
from models import Base


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


def test_stripe_webhook_returns_501_when_not_configured(test_client):
    # Stripe-Check erfolgt zur Laufzeit; ggf. wurden Env-Vars beim Import gesetzt
    orig = getattr(app_module, "STRIPE_WEBHOOK_SECRET", None)
    app_module.STRIPE_WEBHOOK_SECRET = None
    try:
        res = test_client.post(
            "/webhook/stripe",
            data=b"{}",
            content_type="application/json",
        )
        assert res.status_code == 501
        data = res.get_json() or {}
        assert data.get("error") == "stripe_not_configured"
    finally:
        app_module.STRIPE_WEBHOOK_SECRET = orig


def test_copecart_webhook_returns_200_when_no_secret(test_client):
    """Ohne COPECART_WEBHOOK_SECRET: Webhook antwortet mit 200 (no-op)."""
    orig = getattr(app_module, "COPECART_WEBHOOK_SECRET", None)
    app_module.COPECART_WEBHOOK_SECRET = None
    try:
        res = test_client.post(
            "/webhook/copecart",
            data=b"{}",
            content_type="application/json",
        )
        assert res.status_code == 200
    finally:
        app_module.COPECART_WEBHOOK_SECRET = orig
