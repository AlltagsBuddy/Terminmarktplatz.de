"""
Smoke-/Integrationstests gegen Postgres „terminmarktplatz_test“.

Ausführung: pytest tests/terminmarktplatz_test -q
"""

from __future__ import annotations

from unittest.mock import MagicMock

import jwt
import pytest

# ---------- Seiten ----------


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/suche",
        "/login",
        "/preise",
        "/impressum",
        "/datenschutz",
        "/agb",
    ],
)
def test_html_pages_no_server_error(client, path):
    """Statische/HTML-Routen liefern keinen HTTP 500."""
    rv = client.get(path)
    assert rv.status_code != 500, f"{path} -> {rv.status_code}"


# ---------- Health / API ----------


@pytest.mark.parametrize("path", ["/healthz", "/api/health"])
def test_health_endpoints_return_200(client, path):
    rv = client.get(path)
    assert rv.status_code == 200
    data = rv.get_json()
    assert isinstance(data, dict)
    assert data.get("ok") is True


def test_health_alias_not_routed(client):
    """Es gibt keine /health-Route; Betrieb nutzt /healthz oder /api/health."""
    rv = client.get("/health")
    assert rv.status_code in (404, 405)


def test_public_slots_returns_json_list(client):
    """Öffentliche Slot-Suche antwortet mit JSON (Liste)."""
    rv = client.get("/public/slots?q=Friseur")
    assert rv.status_code == 200
    data = rv.get_json()
    assert isinstance(data, list)


def test_auth_login_invalid_returns_401(client):
    rv = client.post(
        "/auth/login",
        json={"email": "nicht-registriert@example.com", "password": "falschpasswort"},
    )
    assert rv.status_code == 401
    body = rv.get_json() or {}
    assert body.get("error") == "invalid_credentials"


# ---------- JWT ----------


def test_issue_tokens_roundtrip(app_module):
    """JWT Access-/Refresh-Token werden ausgestellt und mit gleichen Claims dekodierbar."""
    pid = "00000000-0000-4000-8000-000000000001"
    access, refresh = app_module.issue_tokens(pid, is_admin=False)

    payload_access = jwt.decode(
        access,
        app_module.SECRET,
        algorithms=["HS256"],
        audience=app_module.JWT_AUD,
        issuer=app_module.JWT_ISS,
    )
    assert payload_access["sub"] == pid
    assert payload_access.get("adm") is False

    payload_refresh = jwt.decode(
        refresh,
        app_module.SECRET,
        algorithms=["HS256"],
        audience=app_module.JWT_AUD,
        issuer=app_module.JWT_ISS,
    )
    assert payload_refresh["sub"] == pid
    assert payload_refresh.get("typ") == "refresh"


def test_invalid_bearer_token_rejected(client):
    rv = client.get(
        "/me",
        headers={"Authorization": "Bearer totally.invalid.token"},
    )
    assert rv.status_code == 401
    assert (rv.get_json() or {}).get("error") == "unauthorized"


# ---------- Mail (Mock) ----------


def test_public_contact_calls_send_mail_mock(monkeypatch, client, app_module):
    mock_send = MagicMock(return_value=(True, "mock"))
    monkeypatch.setattr(app_module, "send_mail", mock_send)
    rv = client.post(
        "/public/contact",
        json={
            "name": "Test Nutzer",
            "email": "kunde@example.com",
            "subject": "Pytest Kontakt",
            "message": "Nachricht aus automatisiertem Test.",
            "consent": True,
        },
    )
    assert rv.status_code == 200
    data = rv.get_json() or {}
    assert data.get("ok") is True
    assert mock_send.call_count >= 1
