"""
Tests für die Security-Härtung:
- Security-Header (X-Content-Type-Options, X-Frame-Options, Referrer-Policy,
  Content-Security-Policy, Permissions-Policy, HSTS nur über HTTPS)
- Abgeriegelte Diagnose-Endpunkte (/_debug*, /api/alerts/debug*) -> 404
- Rate-Limiting am Login (Brute-Force-Bremse) -> 429 nach zu vielen Versuchen
"""
import os
import tempfile

import pytest

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("BASE_URL", "http://testserver")

import app as app_module
from models import Base


@pytest.fixture(scope="function")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


# --------------------------------------------------------
# Security-Header
# --------------------------------------------------------
def test_basis_security_header_gesetzt(test_client):
    r = test_client.get("/api/health")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_permissions_policy_restriktiv(test_client):
    r = test_client.get("/api/health")
    perms = r.headers.get("Permissions-Policy", "")
    # Kamera/Mikrofon vollständig gesperrt, Geolocation/Payment nur self
    assert "camera=()" in perms
    assert "microphone=()" in perms
    assert "geolocation=(self)" in perms
    assert "payment=(self)" in perms


def test_csp_kern_direktiven_und_drittdienste(test_client):
    r = test_client.get("/api/health")
    csp = r.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp
    # Stripe-Redirect muss weiterhin erlaubt sein (Anzahlung/Checkout)
    assert "https://js.stripe.com" in csp
    assert "https://checkout.stripe.com" in csp
    # Google Maps (Kartensuche) und GTM/Analytics müssen als Quellen bestehen bleiben
    assert "https://maps.googleapis.com" in csp
    assert "https://www.googletagmanager.com" in csp


def test_hsts_nur_ueber_https(test_client):
    # Ohne HTTPS darf HSTS nicht gesendet werden
    r_plain = test_client.get("/api/health")
    assert "Strict-Transport-Security" not in r_plain.headers
    # Über HTTPS (simuliert) muss HSTS gesetzt sein
    r_secure = test_client.get("/api/health", base_url="https://testserver")
    assert (
        r_secure.headers.get("Strict-Transport-Security")
        == "max-age=31536000; includeSubDomains"
    )


# --------------------------------------------------------
# Diagnose-Endpunkte abgeriegelt (DSGVO: keine PII/Tokens öffentlich)
# --------------------------------------------------------
def test_debug_endpunkt_gesperrt(test_client):
    r = test_client.get("/_debug/irgendwas")
    assert r.status_code == 404
    assert r.get_json() == {"error": "not_found"}


def test_alerts_debug_endpunkt_gesperrt(test_client):
    r = test_client.get("/api/alerts/debug/by-zip")
    assert r.status_code == 404


# --------------------------------------------------------
# Rate-Limiting am Login (Brute-Force-Bremse)
# --------------------------------------------------------
def test_login_rate_limit_greift(test_client):
    # Saubere Ausgangslage: Bucket leeren (In-Memory, pro Prozess geteilt)
    with app_module._RATE_LOCK:
        app_module._RATE_BUCKETS.clear()
    try:
        statuses = []
        for _ in range(12):
            r = test_client.post(
                "/auth/login",
                json={"email": "brute@example.com", "password": "falsch"},
            )
            statuses.append(r.status_code)
        # Limit ist 10 pro 300s: die ersten 10 Versuche dürfen NICHT durch das
        # Rate-Limit blockiert sein (sie scheitern regulär an falschen Zugangsdaten).
        assert 429 not in statuses[:10]
        # Ab dem 11. Versuch muss das Limit greifen.
        assert 429 in statuses[10:]
    finally:
        # Bucket wieder leeren, damit andere Tests nicht fälschlich blockiert werden.
        with app_module._RATE_LOCK:
            app_module._RATE_BUCKETS.clear()


def test_rate_limit_antwort_hat_message(test_client):
    with app_module._RATE_LOCK:
        app_module._RATE_BUCKETS.clear()
    try:
        last = None
        for _ in range(12):
            last = test_client.post(
                "/auth/login",
                json={"email": "brute2@example.com", "password": "falsch"},
            )
        assert last is not None
        assert last.status_code == 429
        body = last.get_json()
        assert body.get("error") == "rate_limited"
        assert "message" in body
    finally:
        with app_module._RATE_LOCK:
            app_module._RATE_BUCKETS.clear()
